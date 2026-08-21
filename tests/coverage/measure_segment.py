"""Mede a segmentação sobre o corpus.

O número que mais importa é o último: quantos segmentos PROSE passam do
orçamento prático do modelo. Se forem muitos, a estratégia
parágrafo -> sentença precisa ser revista antes da fase 3.

    python tests/coverage/measure_segment.py
"""

from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from manbr.mask import mask  # noqa: E402
from manbr.normalize import normalize  # noqa: E402
from manbr.segment import Segment, SegmentKind, reassemble, segment  # noqa: E402

CORPUS_DIR = Path(__file__).resolve().parents[1] / "corpus"

#: Orçamento prático por segmento de prosa, em tokens.
TOKEN_BUDGET = 400

#: Os oito casos que a fase 1.2 declarou intratáveis por regex de token, pela
#: linha exata em que foram anotados. A aposta da fase 2 é que a classificação
#: de bloco resolve; aqui se verifica, sem presumir.
INTRACTABLE: list[tuple[str, int, str]] = [
    ("awk.txt", 58, "-"),
    ("awk.txt", 75, "\\n"),
    ("awk.txt", 127, "\\"),
    ("chmod.txt", 29, "-"),
    ("chmod.txt", 120, "[ugoa]*([-+=]([rwxXst]*|[ugo]))+|[-+=][0-7]+"),
    ("curl.txt", 91, "\\{{"),
    ("curl.txt", 122, "{{fix:trim:url}}"),
    ("ip.txt", 75, "\\"),
]

SAMPLE_PATH = Path(__file__).parent / "sample.tsv"


def read_sample_lines() -> dict[tuple[str, int], str]:
    lines: dict[tuple[str, int], str] = {}
    for row in SAMPLE_PATH.read_text(encoding="utf-8").splitlines():
        if not row.strip():
            continue
        name, number, text = row.split("\t", 2)
        lines[(name, int(number))] = text
    return lines


def flatten(text: str) -> str:
    """Colapsa todo branco, para comparar através da normalização."""
    return " ".join(text.split())


def tokens_of(text: str) -> int:
    """Proxy de contagem de tokens: palavras separadas por branco.

    Um tokenizer NMT costuma render mais que isso, então o número aqui é um
    piso, não um teto — o que for apertado na medida está pior no modelo.
    """
    return len(text.split())


def is_blank(item: Segment) -> bool:
    return not item.text.strip()


def main() -> int:
    documents: dict[str, list[Segment]] = {}
    for path in sorted(CORPUS_DIR.glob("*.txt")):
        normalized = normalize(path.read_text(encoding="utf-8"))
        segments = segment(normalized)
        assert reassemble(segments) == normalized, f"round-trip quebrou em {path}"
        documents[path.name] = segments

    every = [item for items in documents.values() for item in items]
    content = [item for item in every if not is_blank(item)]
    prose = [item for item in content if item.kind is SegmentKind.PROSE]
    literal = [item for item in content if item.kind is SegmentKind.LITERAL]

    print("=" * 72)
    print("SEGMENTAÇÃO DO CORPUS")
    print("=" * 72)
    print(f"arquivos                 : {len(documents)}")
    print(f"segmentos (com brancos)  : {len(every)}")
    print(f"segmentos com conteúdo   : {len(content)}")
    print()

    lines_prose = sum(item.text.count("\n") + 1 for item in prose)
    lines_literal = sum(item.text.count("\n") + 1 for item in literal)
    total_lines = lines_prose + lines_literal
    for name, items, lines in (
        ("PROSE", prose, lines_prose),
        ("LITERAL", literal, lines_literal),
    ):
        share = len(items) / len(content)
        print(
            f"{name:<8} {len(items):5} segmentos ({share:5.1%})   "
            f"{lines:5} linhas ({lines / total_lines:5.1%})"
        )

    print()
    print("-" * 72)
    print("TAMANHO EM TOKENS (segmentos com conteúdo)")
    print("-" * 72)
    buckets = ((1, 10), (11, 25), (26, 50), (51, 100), (101, 200), (201, 400))
    for kind_name, items in (("PROSE", prose), ("LITERAL", literal)):
        sizes = sorted(tokens_of(item.text) for item in items)
        if not sizes:
            continue
        histogram: Counter[str] = Counter()
        for size in sizes:
            label = next(
                (f"{lo}-{hi}" for lo, hi in buckets if lo <= size <= hi),
                f">{TOKEN_BUDGET}",
            )
            histogram[label] += 1
        middle = sizes[len(sizes) // 2]
        print(
            f"{kind_name:<8} mediana={middle:4}  máximo={sizes[-1]:4}  "
            f"média={sum(sizes) / len(sizes):6.1f}"
        )
        for lo, hi in buckets:
            label = f"{lo}-{hi}"
            if histogram[label]:
                print(f"           {label:>9} tokens: {histogram[label]:4}")
        over = histogram[f">{TOKEN_BUDGET}"]
        if over:
            print(f"           {'>' + str(TOKEN_BUDGET):>9} tokens: {over:4}")

    print()
    print("-" * 72)
    print(f"SEGMENTOS PROSE ACIMA DE {TOKEN_BUDGET} TOKENS  (o número que decide)")
    print("-" * 72)
    long_prose = [item for item in prose if tokens_of(item.text) > TOKEN_BUDGET]
    print(f"  {len(long_prose)} de {len(prose)} ({len(long_prose) / len(prose):.1%})")
    biggest = sorted(prose, key=lambda item: -tokens_of(item.text))[:5]
    print("  maiores segmentos PROSE:")
    for item in biggest:
        head = " ".join(item.text.split())[:58]
        print(f"    {tokens_of(item.text):4} tokens  {head}…")

    print()
    print("-" * 72)
    print("OS OITO INTRATÁVEIS DA FASE 1.2")
    print("-" * 72)
    sample_lines = read_sample_lines()
    resolved = 0
    for name, number, needle in INTRACTABLE:
        wanted = flatten(sample_lines[(name, number)])
        probe = wanted[:60]
        hits = [
            item
            for item in documents[name]
            if not is_blank(item) and probe in flatten(item.text)
        ]
        if not hits:
            verdict = "linha não localizada"
        elif all(item.kind is SegmentKind.LITERAL for item in hits):
            verdict = "LITERAL — resolvido"
            resolved += 1
        else:
            verdict = "PROSE — continua exposto"
        print(f"  {name}:{number:<5} {needle[:28]:<30} {verdict}")
    print(f"\n  resolvidos por classificação de bloco: {resolved}/{len(INTRACTABLE)}")

    print()
    print("-" * 72)
    print("TOKENS MASCARADOS POR TIPO DE SEGMENTO")
    print("-" * 72)
    counts = {SegmentKind.PROSE: 0, SegmentKind.LITERAL: 0}
    for item in content:
        counts[item.kind] += len(mask(item.text).tokens)
    total = sum(counts.values())
    for kind, value in counts.items():
        print(f"  {kind.name:<8} {value:5} tokens mascarados ({value / total:5.1%})")
    print(
        "\n  A previsão da spec era 'a maioria em PROSE'. Não se confirmou: os\n"
        "  blocos literais são poucos mas densos, e concentram mais tokens que\n"
        "  as flags citadas no meio das frases. Os 43% em PROSE continuam sendo\n"
        "  o caso de uso de mask/validate — são eles que passam pelo modelo."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
