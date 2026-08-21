"""Normalização de saída de terminal antes da segmentação.

Entrada típica: o que `man` escreve num pipe. Isso traz três sujeiras que
atrapalham tanto a segmentação quanto a tradução:

- **Overstrike do roff.** Negrito é ``X\\bX``, sublinhado é ``_\\bX``. Sem
  remover, cada letra em negrito vira três caracteres e nenhum padrão de
  :mod:`manbr.mask` reconhece mais nada.
- **Hifenização de fim de linha.** ``notifica‐`` numa linha e ``tion`` na
  seguinte. Uma palavra partida ao meio não é traduzível.
- **Justificação.** ``ss  is  used  to`` com dois e três espaços entre
  palavras, que o modelo não deve ver como estrutura.

O que este módulo **não** faz: não decide o que é prosa e o que é bloco
literal. Isso é de :mod:`manbr.segment`. A única concessão é a colagem de
espaços, que precisa acontecer aqui — ``normalize`` tem de ser o ponto fixo
que ``reassemble(segment(...))`` reproduz — e por isso usa um limiar medido
em vez de classificação: ver :data:`MAX_JUSTIFICATION_RUN`.
"""

from __future__ import annotations

import re
from typing import Final

__all__ = [
    "MAX_JUSTIFICATION_RUN",
    "SOFT_HYPHEN",
    "TAB_STOP",
    "expand_tabs",
    "normalize",
    "strip_overstrike",
]

#: Tab stop do roff.
TAB_STOP: Final = 8

#: U+2010 HYPHEN. O groff usa este caractere quando ele mesmo quebrou a
#: palavra, e U+002D quando a quebra caiu num hífen que já existia.
SOFT_HYPHEN: Final = "‐"

#: Sequências de até este tamanho, entre dois não-espaços, são justificação e
#: viram um espaço só. De 4 em diante é layout de coluna e fica intacto.
#:
#: Medido no corpus: das 2045 sequências em linhas de prosa, 87.4% têm 2
#: espaços e 6.0% têm 3 — justificação. A cauda de 19 a 27 espaços é tabela.
MAX_JUSTIFICATION_RUN: Final = 3

_CONTROL_RE: Final = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")
_JUSTIFICATION_RE: Final = re.compile(
    rf"(?<=\S) {{2,{MAX_JUSTIFICATION_RUN}}}(?=\S)"
)


def strip_overstrike(line: str) -> str:
    """Resolve ``X\\bY`` mantendo ``Y``, como ``col -b``.

    Um backspace apaga o caractere anterior, que é o que produz negrito
    (``X\\bX``) e sublinhado (``_\\bX``) em terminal burro.
    """
    if "\b" not in line:
        return line
    out: list[str] = []
    for char in line:
        if char == "\b":
            if out:
                out.pop()
        else:
            out.append(char)
    return "".join(out)


def expand_tabs(line: str, tab_stop: int = TAB_STOP) -> str:
    """Troca tabs por espaços até o próximo múltiplo de ``tab_stop``.

    Depende da coluna, então só pode rodar depois do overstrike — antes, cada
    par ``X\\b`` contaria como dois caracteres e deslocaria os tab stops.
    """
    if "\t" not in line:
        return line
    out: list[str] = []
    column = 0
    for char in line:
        if char == "\t":
            width = tab_stop - (column % tab_stop)
            out.append(" " * width)
            column += width
        else:
            out.append(char)
            column += 1
    return "".join(out)


def _joins_with_next(line: str, following: str) -> bool:
    """A linha foi quebrada no meio de uma palavra?

    Exige palavra dos dois lados do hífen: sem isso a régua ``----`` e um
    travessão solto no fim da linha virariam junção.
    """
    if len(line) < 2 or not line[-2].isalnum():
        return False
    head = following.lstrip(" ")
    return bool(head) and head[0].islower()


def _dehyphenate(lines: list[str]) -> list[str]:
    """Junta palavras quebradas no fim da linha.

    U+2010 é hifenização do groff e o hífen some. U+002D é um hífen que já
    existia na palavra composta (``set-`` + ``group-ID``) e fica. A heurística
    acerta 11 de 11 no corpus; ver README-fase2.

    O laço interno é o que trata uma palavra quebrada em três linhas.
    """
    joined: list[str] = []
    index = 0
    while index < len(lines):
        current = lines[index].rstrip()
        while (
            index + 1 < len(lines)
            and current.endswith((SOFT_HYPHEN, "-"))
            and _joins_with_next(current, lines[index + 1])
        ):
            if current.endswith(SOFT_HYPHEN):
                current = current[:-1]
            current = (current + lines[index + 1].strip()).rstrip()
            index += 1
        joined.append(current)
        index += 1
    return joined


def normalize(text: str) -> str:
    """Deixa a saída pronta para :func:`manbr.segment.segment`.

    A ordem importa: overstrike antes de tudo, porque o backspace desloca
    colunas e separa o hífen do contexto; tabs depois dele, porque dependem de
    coluna; junção de linhas antes da colagem de espaços, porque a junção cria
    sequências novas.

    Indentação de início de linha nunca é tocada — é o sinal que o
    segmentador usa.
    """
    text = text.replace("\r\n", "\n").replace("\r", "")

    lines = [
        _CONTROL_RE.sub("", expand_tabs(strip_overstrike(line)))
        for line in text.split("\n")
    ]
    lines = _dehyphenate(lines)

    return "\n".join(_JUSTIFICATION_RE.sub(" ", line).rstrip() for line in lines)
