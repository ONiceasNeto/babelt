"""Mede a cobertura de :func:`babelt.mask.mask` contra a anotação manual.

Round-trip prova que mask e restore são inversas. Não prova que mask protege
o que precisa ser protegido: uma mask que não mascara nada passa no round-trip
com 100% de falsos negativos. Este script mede a outra metade.

    python tests/coverage/measure.py

Não é teste de CI. É medição — o limiar se decide depois de ver os números.

A cobertura é medida por caractere, não por igualdade de string: um token
anotado conta como coberto quando cada caractere dele cai dentro de algum
placeholder. Isso é o que faz `$HOME/.secret` contar como coberto quando mask
o parte em dois placeholders adjacentes ($HOME + /.secret) — nada ficou
exposto — e o que faz `https://download.samba.org/...` contar como PARCIAL,
porque o `https://` sobrou de fora.
"""

from __future__ import annotations

import re
import sys
from collections import Counter
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from babelt.mask import CLOSE, OPEN, mask  # noqa: E402

COVERAGE_DIR = Path(__file__).parent
SAMPLE_PATH = COVERAGE_DIR / "sample.tsv"
ANNOTATED_PATH = COVERAGE_DIR / "annotated.tsv"

_WALK_RE = re.compile(f"{OPEN}{OPEN}|{CLOSE}{CLOSE}|{OPEN}(\\d+){CLOSE}")

Span = tuple[int, int]


class Verdict(Enum):
    COVERED = "COBERTO"
    PARTIAL = "PARCIAL"
    MISSING = "AUSENTE"


@dataclass(frozen=True)
class Annotation:
    file: str
    line: int
    token: str


@dataclass(frozen=True)
class Finding:
    annotation: Annotation
    verdict: Verdict


@dataclass(frozen=True)
class FalsePositive:
    file: str
    line: int
    literal: str


def masked_spans(line: str) -> list[Span]:
    """Spans de ``line`` cobertos por algum placeholder.

    Reconstruídos andando pelo texto mascarado, sem tocar em nada privado de
    mask: cada placeholder ⟦n⟧ vale ``len(tokens[n])`` caracteres do original,
    cada par escapado vale um.
    """
    result = mask(line)
    spans: list[Span] = []
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

    original += len(result.text) - last
    assert original == len(line), f"spans dessincronizados em {line!r}"
    return spans


def covered_indices(spans: list[Span]) -> set[int]:
    return {i for start, stop in spans for i in range(start, stop)}


#: Um token só conta como ocorrência quando não está grudado numa palavra
#: maior. Sem isso, o "-f" anotado em `-f script-file` também casaria dentro de
#: "script-file" e de "--file", e o veredito viraria artefato da medição.
_WORDISH = re.compile(r"[A-Za-z0-9_-]")


def occurrences(line: str, token: str) -> list[Span]:
    found: list[Span] = []
    start = line.find(token)
    while start != -1:
        stop = start + len(token)
        before_ok = start == 0 or not _WORDISH.match(line[start - 1])
        after_ok = stop == len(line) or not _WORDISH.match(line[stop])
        if before_ok and after_ok:
            found.append((start, stop))
        start = line.find(token, start + 1)
    return found


def judge(line: str, token: str, covered: set[int]) -> Verdict:
    """Veredito de um token anotado numa linha.

    Todas as ocorrências precisam estar cobertas: mascarar o primeiro `-L` da
    linha e deixar o segundo exposto não é proteção.
    """
    spots = occurrences(line, token)
    if not spots:
        return Verdict.MISSING

    any_char = False
    all_full = True
    for start, stop in spots:
        chars = set(range(start, stop))
        hit = chars & covered
        any_char = any_char or bool(hit)
        all_full = all_full and hit == chars

    if all_full:
        return Verdict.COVERED
    return Verdict.PARTIAL if any_char else Verdict.MISSING


def read_sample() -> dict[tuple[str, int], str]:
    lines: dict[tuple[str, int], str] = {}
    for row in SAMPLE_PATH.read_text(encoding="utf-8").splitlines():
        if not row.strip():
            continue
        name, number, text = row.split("\t", 2)
        lines[(name, int(number))] = text
    return lines


def read_annotations() -> list[Annotation]:
    found: list[Annotation] = []
    for row in ANNOTATED_PATH.read_text(encoding="utf-8").splitlines():
        if not row.strip() or row.startswith("#"):
            continue
        name, number, token = row.split("\t", 2)
        found.append(Annotation(name, int(number), token))
    return found


def main() -> int:
    sample = read_sample()
    annotations = read_annotations()

    by_line: dict[tuple[str, int], list[Annotation]] = {}
    for annotation in annotations:
        key = (annotation.file, annotation.line)
        if key not in sample:
            print(f"anotação fora da amostra: {annotation}", file=sys.stderr)
            return 1
        by_line.setdefault(key, []).append(annotation)

    findings: list[Finding] = []
    false_positives: list[FalsePositive] = []

    for key, line in sorted(sample.items()):
        spans = masked_spans(line)
        covered = covered_indices(spans)

        annotated_chars: set[int] = set()
        for annotation in by_line.get(key, []):
            findings.append(Finding(annotation, judge(line, annotation.token, covered)))
            for start, stop in occurrences(line, annotation.token):
                annotated_chars.update(range(start, stop))

        for start, stop in spans:
            if not set(range(start, stop)) & annotated_chars:
                false_positives.append(FalsePositive(key[0], key[1], line[start:stop]))

    orphans = [
        finding.annotation
        for finding in findings
        if not occurrences(sample[(finding.annotation.file, finding.annotation.line)],
                           finding.annotation.token)
    ]
    if orphans:
        print("anotações que não casam com a linha (erro de anotação):",
              file=sys.stderr)
        for orphan in orphans:
            print(f"  {orphan.file}:{orphan.line} {orphan.token!r}", file=sys.stderr)

    tally = Counter(finding.verdict for finding in findings)
    total = len(findings)
    covered_count = tally[Verdict.COVERED]

    print("=" * 72)
    print("COBERTURA DE MASCARAMENTO")
    print("=" * 72)
    print(f"linhas na amostra      : {len(sample)}")
    print(f"arquivos               : {len({name for name, _ in sample})}")
    print(f"tokens anotados        : {total}")
    print()
    print(f"cobertos               : {covered_count:3}  ({covered_count / total:.1%})")
    print(
        f"parciais               : {tally[Verdict.PARTIAL]:3}  "
        f"({tally[Verdict.PARTIAL] / total:.1%})"
    )
    print(
        f"ausentes               : {tally[Verdict.MISSING]:3}  "
        f"({tally[Verdict.MISSING] / total:.1%})"
    )
    print()
    print(f"RECALL                 : {covered_count / total:.1%}")

    for verdict, title in (
        (Verdict.PARTIAL, "PARCIAIS — parte do token ficou exposta (classe crítica)"),
        (Verdict.MISSING, "AUSENTES — nada do token foi mascarado"),
    ):
        rows = [f for f in findings if f.verdict is verdict]
        print()
        print("-" * 72)
        print(f"{title}: {len(rows)}")
        print("-" * 72)
        for finding in rows:
            location = f"{finding.annotation.file}:{finding.annotation.line}"
            print(f"  {location:<26} {finding.annotation.token}")

    print()
    print("-" * 72)
    print(f"CANDIDATOS A FALSO POSITIVO — mascarado sem anotação: "
          f"{len(false_positives)}")
    print("-" * 72)
    for item in sorted(false_positives, key=lambda f: (f.file, f.line)):
        print(f"  {f'{item.file}:{item.line}':<26} {item.literal!r}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
