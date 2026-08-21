"""Segmentação de saída de man em prosa e blocos literais.

O que decide a tradução não é a linha, é o bloco. Uma man page tem prosa
justificada, listas com tag e descrição pendurada, tabelas de saída de exemplo
e comandos de exemplo, e só a primeira categoria deve chegar ao modelo.

Três coisas foram medidas no corpus antes de escrever as regras, e cada uma
derrubou uma hipótese óbvia:

- **Indentação sozinha não separa nada.** O nível 7 é prosa de corpo, mas o 14
  (426 linhas) e o 21 (46 linhas) são descrição de opção — prosa também, com
  razão de sintaxe 0.06 e 0.01. Marcar "indentado 4 além do entorno" como
  literal jogaria fora quase toda a prosa útil da página.
- **O que separa é o bloco, não a linha.** Um comando de exemplo da rsync ou
  uma tabela de saída da systemctl é um bloco isolado por linhas em branco,
  indentado além do bloco anterior. Já a descrição pendurada de uma lista com
  tag mora *dentro* do mesmo bloco da tag, sem linha em branco no meio.
- **Profundidade sozinha ainda erra.** ``ts     show string "ts" ...`` é um
  bloco a 14 depois de um bloco a 7, e é prosa. Por isso a regra de bloco
  fundo também exige densidade de sintaxe.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum, auto
from typing import Final

from manbr.mask import CLOSE, OPEN, mask

__all__ = [
    "DEEP_BLOCK_INDENT",
    "DEEP_BLOCK_RATIO",
    "SYNTAX_RATIO",
    "Segment",
    "SegmentKind",
    "reassemble",
    "segment",
    "syntax_ratio",
]

#: Um bloco precisa estar ao menos isto mais fundo que o bloco anterior para
#: ser candidato a literal.
DEEP_BLOCK_INDENT: Final = 4

#: ...e ao menos esta densidade de sintaxe. Sem o segundo teste, a descrição
#: pendurada de uma lista com tag vira literal e se perde.
DEEP_BLOCK_RATIO: Final = 0.15

#: Uma linha isolada com esta densidade de sintaxe é literal por si só.
SYNTAX_RATIO: Final = 0.5

_SECTION_HEADER_RE: Final = re.compile(r"^[A-Z][A-Z0-9 ]*$")

#: Seções cujo conteúdo é sintaxe de comando por definição, não prosa.
#:
#: Descoberto na fase 4, com o binário rodando: `ss [options] [ FILTER ]` saiu
#: como `s [opções] [ FILTRO ]` — o nome do comando perdeu uma letra. A linha
#: era PROSE porque "options" e "FILTER" são palavras nuas e a densidade de
#: sintaxe deu 0.00, e passou em todas as regras de validação: um delimitador
#: para cada, uma sentença para cada, nenhum token desconhecido. Nenhuma regra
#: baseada em conteúdo pegaria isso; a seção é que diz o que a linha é.
SYNTAX_SECTIONS: Final = frozenset({"SYNOPSIS", "COMMAND SYNOPSIS", "SYNTAX"})

_WALK_RE: Final = re.compile(f"{OPEN}{OPEN}|{CLOSE}{CLOSE}|{OPEN}(\\d+){CLOSE}")


class SegmentKind(Enum):
    PROSE = auto()
    LITERAL = auto()  # não traduzir, passar intacto


@dataclass(frozen=True)
class Segment:
    kind: SegmentKind
    text: str
    indent: int


def _indent_of(line: str) -> int:
    return len(line) - len(line.lstrip(" "))


def _masked_spans(text: str) -> list[tuple[int, int]]:
    """Trechos de ``text`` cobertos por algum placeholder de :func:`mask`.

    Reconstruídos andando pelo texto mascarado: cada ⟦n⟧ vale
    ``len(tokens[n])`` caracteres do original e cada par escapado vale um.
    """
    result = mask(text)
    spans: list[tuple[int, int]] = []
    original = 0
    last = 0
    for match in _WALK_RE.finditer(result.text):
        original += match.start() - last
        index = match.group(1)
        if index is None:
            original += 1
        else:
            literal = result.tokens[int(index)]
            spans.append((original, original + len(literal)))
            original += len(literal)
        last = match.end()
    return spans


def syntax_ratio(text: str) -> float:
    """Fração dos caracteres não-brancos que :func:`manbr.mask.mask` cobre.

    É a medida de "isto é sintaxe, não frase". Zero para prosa pura, perto de
    1 para uma linha de comando. Espaços saem da conta dos dois lados, senão
    a justificação e a indentação diluiriam a razão.
    """
    dense = {index for index, char in enumerate(text) if not char.isspace()}
    if not dense:
        return 0.0
    covered = {
        index
        for start, stop in _masked_spans(text)
        for index in range(start, stop)
    }
    return len(dense & covered) / len(dense)


@dataclass(frozen=True)
class _Block:
    """Um trecho contíguo de linhas não vazias, ou um trecho de linhas vazias."""

    start: int
    lines: list[str]
    blank: bool

    @property
    def indent(self) -> int:
        indents = [_indent_of(line) for line in self.lines if line.strip()]
        return min(indents) if indents else 0


def _blocks(lines: list[str]) -> list[_Block]:
    blocks: list[_Block] = []
    index = 0
    while index < len(lines):
        blank = not lines[index].strip()
        start = index
        while index < len(lines) and (not lines[index].strip()) == blank:
            index += 1
        blocks.append(_Block(start, lines[start:index], blank))
    return blocks


def _classify(
    blocks: list[_Block],
) -> tuple[dict[int, SegmentKind], set[int]]:
    """Decide o tipo de cada linha e quais linhas são cabeçalho de seção.

    Os cabeçalhos voltam à parte porque precisam ficar sozinhos num segmento:
    é assim que `manbr.headers.apply_headers` consegue trocar DESCRIPTION por
    DESCRIÇÃO sem risco de acertar uma linha solta dentro de um bloco.
    """
    kinds: dict[int, SegmentKind] = {}
    headers: set[int] = set()
    previous_indent: int | None = None
    section: str | None = None

    for block in blocks:
        if block.blank:
            for offset in range(len(block.lines)):
                kinds[block.start + offset] = SegmentKind.LITERAL
            continue

        body = "\n".join(block.lines)
        density = syntax_ratio(body)

        # Um bloco denso em sintaxe é literal inteiro, não linha a linha. Sem
        # isso o bloco de exemplo da curl se parte: três linhas passam de 0.5
        # e a quarta (--expand-data "{{fix:trim:url}}", 0.42) fica de fora e
        # vai para tradução no meio do comando.
        dense = density >= SYNTAX_RATIO

        # Bloco recuado além do anterior e com alguma sintaxe: tabela de saída
        # da systemctl, comando de exemplo da rsync.
        deep = (
            previous_indent is not None
            and block.indent - previous_indent >= DEEP_BLOCK_INDENT
            and density >= DEEP_BLOCK_RATIO
        )

        for offset, line in enumerate(block.lines):
            stripped = line.strip()
            # Cabeçalho de seção só conta na coluna 0: uma linha de cabeçalho
            # de tabela ("LISTEN UNIT ACTIVATES", recuada 15) também é toda
            # maiúscula e não abre seção nenhuma.
            header = (
                _indent_of(line) == 0
                and _SECTION_HEADER_RE.fullmatch(stripped) is not None
            )
            if header:
                section = stripped
                headers.add(block.start + offset)

            literal = (
                header
                or section in SYNTAX_SECTIONS
                or dense
                or deep
                or syntax_ratio(line) >= SYNTAX_RATIO
            )
            kinds[block.start + offset] = (
                SegmentKind.LITERAL if literal else SegmentKind.PROSE
            )

        previous_indent = block.indent

    return kinds, headers


def segment(text: str) -> list[Segment]:
    """Divide ``text`` em segmentos de prosa e de bloco literal.

    Espera texto já passado por :func:`manbr.normalize.normalize`. Cobre todas
    as linhas, inclusive as vazias, para que :func:`reassemble` reconstrua o
    original caractere a caractere.
    """
    lines = text.split("\n")
    blocks = _blocks(lines)
    kinds, headers = _classify(blocks)

    segments: list[Segment] = []
    run: list[str] = []
    run_kind: SegmentKind | None = None
    run_indent: int | None = None

    def flush() -> None:
        if run_kind is None:
            return
        indents = [_indent_of(line) for line in run if line.strip()]
        base = min(indents) if indents else 0
        body = "\n".join(line[base:] if line.strip() else "" for line in run)
        segments.append(Segment(kind=run_kind, text=body, indent=base))

    for block in blocks:
        for offset, line in enumerate(block.lines):
            number = block.start + offset
            kind = kinds[number]
            blank = not line.strip()
            indent = None if blank else _indent_of(line)

            # Prosa agrupa por indentação igual; um bloco literal fica inteiro
            # num segmento só, porque é uma unidade de código.
            # Um cabeçalho de seção fica sempre sozinho no segmento: não
            # entra no anterior nem deixa o seguinte entrar nele.
            isolated = number in headers or (number - 1) in headers
            same = (
                not isolated
                and run_kind is kind
                and (kind is SegmentKind.LITERAL or run_indent == indent)
                and (blank == (run_indent is None))
            )
            if not same:
                flush()
                run = []
                run_kind = kind
                run_indent = indent
            run.append(line)
        flush()
        run = []
        run_kind = None
        run_indent = None

    return segments


def reassemble(segments: list[Segment]) -> str:
    """Reconstrói o texto original a partir dos segmentos."""
    out: list[str] = []
    for item in segments:
        pad = " " * item.indent
        out.extend(pad + line if line else "" for line in item.text.split("\n"))
    return "\n".join(out)
