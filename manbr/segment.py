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

A fase 5 acrescentou uma quarta, que só apareceu quando o corpus deixou de ser
100% man page:

- **Layout de duas colunas não é bloco de prosa nem bloco literal.** A tabela
  de flags de um ``--help`` tem a coluna esquerda (a flag) que nunca pode ser
  traduzida e a direita (a descrição) que sempre deve ser. Agrupada por
  indentação, ela virava um segmento PROSE só, o modelo devolvia um parágrafo
  corrido e o alinhamento morria. É o :class:`SegmentKind.COLUMNS`.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum, auto
from typing import Final

from manbr.mask import CLOSE, OPEN, mask

__all__ = [
    "COLUMN_GAP",
    "DEEP_BLOCK_INDENT",
    "DEEP_BLOCK_RATIO",
    "MIN_COLUMN_ROWS",
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

#: Espaços mínimos entre a coluna esquerda e a direita. Dois, e não um, é o
#: que separa tabela de prosa: prosa justificada tem espaço simples entre
#: palavras, e quem alinha coluna usa mais de um.
COLUMN_GAP: Final = 2

#: Linhas com a direita na mesma coluna para o bloco contar como tabela. Duas
#: acontecem por acaso — duas flags de tamanho parecido numa sinopse. Três já
#: é alinhamento deliberado.
MIN_COLUMN_ROWS: Final = 3

_SECTION_HEADER_RE: Final = re.compile(r"^[A-Z][A-Z0-9 ]*$")

#: Primeiro intervalo de dois ou mais espaços depois de conteúdo: a fronteira
#: entre as colunas. Não-guloso de propósito — o que interessa é a primeira
#: fronteira, não a última.
_COLUMN_SPLIT_RE: Final = re.compile(r"^(\s*\S.*?)\s{%d,}(?=\S)" % COLUMN_GAP)

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
    COLUMNS = auto()  # linha de tabela: esquerda literal, direita traduzível


@dataclass(frozen=True)
class Segment:
    """Uma unidade de tradução.

    Em ``COLUMNS``, ``text`` é **só a célula da direita** — é ela que vai ao
    modelo, sozinha, com o próprio lugar no cache. A esquerda viaja em
    ``left`` e nunca é traduzida, e ``column`` guarda onde a direita começa,
    para que :func:`reassemble` recoloque a célula na coluna certa.
    """

    kind: SegmentKind
    text: str
    indent: int
    #: Coluna esquerda, com a indentação dela. Vazio fora de ``COLUMNS``.
    left: str = ""
    #: Coluna em que a direita começa. Zero fora de ``COLUMNS``.
    column: int = 0


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


@dataclass
class _Row:
    """Uma linha lógica de tabela: a esquerda, a coluna e a célula direita.

    Mutável porque cresce: uma descrição que ocupa três linhas na tela é uma
    linha lógica só, e as continuações são anexadas à célula conforme aparecem.
    """

    lines: list[int]
    left: str
    column: int
    cell: str


def _split_columns(line: str) -> tuple[str, int] | None:
    """``(esquerda, coluna_da_direita)`` da primeira fronteira de colunas."""
    match = _COLUMN_SPLIT_RE.match(line)
    if match is None:
        return None
    return match.group(1), match.end()


def _detect_columns(block: _Block) -> dict[int, _Row]:
    """Linhas do bloco que formam uma tabela de duas colunas.

    Devolve mapa de número de linha para a linha lógica, vazio se o bloco não
    é tabela. A coluna vencedora é a mais frequente: um ``--help`` mistura
    títulos de seção e linhas de flag no mesmo bloco, e só as últimas contam.

    Uma linha que começa na coluna da direita, sem nada à esquerda, é
    continuação da célula anterior — é assim que uma descrição de duas linhas
    chega ao modelo como uma frase só, em vez de duas metades.

    As continuações entram na célula com a quebra de linha original, e não
    coladas por espaço: a célula tem de reconstruir o texto de origem caractere
    a caractere, que é o invariante duro deste módulo.
    """
    positions: list[int] = []
    for line in block.lines:
        found = _split_columns(line)
        if found is not None:
            positions.append(found[1])
    if not positions:
        return {}

    column = max(set(positions), key=positions.count)
    if positions.count(column) < MIN_COLUMN_ROWS:
        return {}

    rows: dict[int, _Row] = {}
    current: _Row | None = None
    for offset, line in enumerate(block.lines):
        number = block.start + offset
        found = _split_columns(line)
        if found is not None and found[1] == column:
            current = _Row([number], found[0], column, line[column:])
            rows[number] = current
            continue
        # Continuação: nada à esquerda da coluna, e algo à direita.
        if current is not None and line.strip() and _indent_of(line) >= column:
            current.lines.append(number)
            current.cell = f"{current.cell}\n{line[column:]}"
            rows[number] = current
            continue
        current = None
    return rows


def _classify(
    blocks: list[_Block],
) -> tuple[dict[int, SegmentKind], set[int], set[int]]:
    """Decide o tipo de cada linha e quais linhas são cabeçalho de seção.

    Os cabeçalhos voltam à parte porque precisam ficar sozinhos num segmento:
    é assim que `manbr.headers.apply_headers` consegue trocar DESCRIPTION por
    DESCRIÇÃO sem risco de acertar uma linha solta dentro de um bloco.

    O terceiro retorno são os blocos literais *como bloco* — densos, fundos,
    ou dentro de uma seção de sintaxe. A detecção de colunas os respeita:
    tabela de saída de exemplo continua sendo exemplo, não vira tradução.
    """
    kinds: dict[int, SegmentKind] = {}
    headers: set[int] = set()
    whole: set[int] = set()
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

        if dense or deep or section in SYNTAX_SECTIONS:
            whole.add(block.start)

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

        # A profundidade que conta é a do corpo, não a do cabeçalho. Um bloco
        # que começa com "DESCRIPTION" na coluna 0 tem indent 0 e faria o
        # parágrafo seguinte, a 7, parecer recuado além dele — e a regra de
        # bloco fundo o marcaria literal. Foi assim que o segundo parágrafo da
        # DESCRIPTION da ssh(1) virou literal quando a fase 5 melhorou o
        # mascaramento e a densidade dele passou de 0.15.
        body_indents = [
            _indent_of(line)
            for offset, line in enumerate(block.lines)
            if line.strip() and (block.start + offset) not in headers
        ]
        previous_indent = min(body_indents) if body_indents else block.indent

    return kinds, headers, whole


def segment(text: str) -> list[Segment]:
    """Divide ``text`` em segmentos de prosa e de bloco literal.

    Espera texto já passado por :func:`manbr.normalize.normalize`. Cobre todas
    as linhas, inclusive as vazias, para que :func:`reassemble` reconstrua o
    original caractere a caractere.
    """
    lines = text.split("\n")
    blocks = _blocks(lines)
    kinds, headers, whole = _classify(blocks)

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
        # Duas guardas, e as duas foram medidas.
        #
        # Por bloco: um bloco que já era literal inteiro — denso, fundo, ou
        # dentro de SYNOPSIS — não vira tabela. Tabela de saída de exemplo tem
        # exatamente a forma de duas colunas, e traduzir a direita dela seria
        # traduzir o que o comando imprime.
        #
        # Por célula: quem decide é a **direita**, não a linha. A linha
        # `-d, --data <data>   HTTP POST data` passa de 0.5 de densidade por
        # causa da esquerda, e era isso que a fazia literal; a célula "HTTP
        # POST data" é prosa e é o que se quer traduzir. Julgar a linha
        # inteira deixaria metade da tabela da curl em inglês.
        rows = (
            {}
            if block.blank or block.start in whole
            else _detect_columns(block)
        )
        rows = {
            number: row
            for number, row in rows.items()
            if syntax_ratio(row.cell) < SYNTAX_RATIO
        }

        for offset, line in enumerate(block.lines):
            number = block.start + offset
            row = rows.get(number)
            if row is not None:
                flush()
                run = []
                run_kind = None
                run_indent = None
                # A linha lógica sai uma vez só, na última linha dela, com as
                # continuações já dentro da célula.
                if number == row.lines[-1]:
                    segments.append(
                        Segment(
                            kind=SegmentKind.COLUMNS,
                            text=row.cell,
                            indent=0,
                            left=row.left,
                            column=row.column,
                        )
                    )
                continue

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
        if item.kind is SegmentKind.COLUMNS:
            cell = item.text.split("\n")
            # Ao menos um espaço de separação: se a tradução esticou a
            # esquerda além da coluna, a célula é empurrada para a direita —
            # nunca invade a esquerda.
            gap = max(item.column - len(item.left), 1)
            out.append(f"{item.left}{' ' * gap}{cell[0]}")
            out.extend(" " * item.column + line for line in cell[1:])
            continue
        pad = " " * item.indent
        out.extend(pad + line if line else "" for line in item.text.split("\n"))
    return "\n".join(out)
