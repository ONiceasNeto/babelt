"""Congela a amostra estratificada usada para medir cobertura.

A amostra é escrita em ``sample.tsv`` com o texto embutido, não só o número
da linha, para que ``annotated.tsv`` continue válido depois de um
``refresh.sh`` mexer no corpus.

O critério de seleção é de propósito independente de :func:`babelt.mask.mask`:
selecionar "as linhas onde mask encontrou algo" tornaria o recall 100% por
construção. Aqui a heurística é a presença de caracteres de sintaxe, e as
linhas são pegas espaçadas ao longo do arquivo (não as "melhores"), para
cobrir SYNOPSIS, OPTIONS, FILES e EXAMPLES em vez de só um bloco.

    python tests/coverage/build_sample.py
"""

from __future__ import annotations

import re
from pathlib import Path

COVERAGE_DIR = Path(__file__).parent
CORPUS_DIR = COVERAGE_DIR.parent / "corpus"
SAMPLE_PATH = COVERAGE_DIR / "sample.tsv"

#: Caracteres que sugerem sintaxe de comando em vez de prosa.
SYNTAX_CHARS = re.compile(r"[-/$<>=~|`]")

#: Por arquivo: linhas com sintaxe + linhas de prosa pura. As de prosa entram
#: para que a medição de falso positivo tenha onde acontecer.
SYNTAX_PER_FILE = 8
PROSE_PER_FILE = 2


def spread(items: list[tuple[int, str]], count: int) -> list[tuple[int, str]]:
    """``count`` itens espaçados uniformemente, preservando a ordem."""
    if len(items) <= count:
        return items
    step = len(items) / count
    return [items[int(i * step)] for i in range(count)]


def select(path: Path) -> list[tuple[int, str]]:
    syntax: list[tuple[int, str]] = []
    prose: list[tuple[int, str]] = []
    for number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = raw.rstrip()
        stripped = line.strip()
        if len(stripped) < 8:
            continue
        if SYNTAX_CHARS.search(stripped):
            syntax.append((number, line))
        elif len(stripped) >= 30:
            prose.append((number, line))

    chosen = spread(syntax, SYNTAX_PER_FILE) + spread(prose, PROSE_PER_FILE)
    return sorted(chosen)


def main() -> None:
    rows: list[str] = []
    for path in sorted(CORPUS_DIR.glob("*.txt")):
        for number, line in select(path):
            assert "\t" not in line, f"{path.name}:{number} contém tab"
            rows.append(f"{path.name}\t{number}\t{line}")

    SAMPLE_PATH.write_text("\n".join(rows) + "\n", encoding="utf-8")
    print(f"{len(rows)} linhas -> {SAMPLE_PATH}")


if __name__ == "__main__":
    main()
