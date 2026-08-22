"""Mede a cobertura de conteúdo: a tradução perdeu palavra do original?

O caso que abriu a fase 6:

    EN  Send User-Agent <name> to server
    PT  Enviar ⟦0⟧ para o servidor

Gramatical, com o placeholder intacto, contagem de sentenças igual,
delimitadores iguais — e "User-Agent" não está lá. As quatro regras de
`validate_structure` medem estrutura; omissão de conteúdo passa por todas.

A razão medida é palavras da tradução sobre palavras da origem, ambas contadas
sobre o texto **mascarado**: flag e caminho não são palavra de idioma nenhum.

    python tests/quality/measure_omission.py            # gera o despejo e mede
    python tests/quality/measure_omission.py --dump X   # reusa um despejo

A conclusão está em README-fase6.md, e é que as populações **não se separam**:
a rotulagem manual de `omission-labels.tsv` dá precisão entre 45% e 60% em
qualquer limiar. Este script existe para que essa conclusão seja refeita — e
derrubada — com um comando.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT))

from babelt.mask import mask  # noqa: E402
from babelt.normalize import normalize  # noqa: E402
from babelt.segment import SegmentKind, segment  # noqa: E402

LABELS_PATH = Path(__file__).parent / "omission-labels.tsv"
CORPORA = {
    "man": _ROOT / "tests" / "corpus",
    "help": _ROOT / "tests" / "corpus" / "help",
}

#: Palavras de menos que isso na origem e a razão vira ruído: perder uma
#: palavra de três já derruba para 0,67 sem que nada esteja errado.
MIN_SOURCE_WORDS = 4

_WORD_RE = re.compile(r"[A-Za-zÀ-ÿ]+")


def words(text: str) -> list[str]:
    return _WORD_RE.findall(mask(text).text)


def digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:12]


def build_dump(path: Path) -> None:
    from babelt.model import is_installed, model_path
    from babelt.translate import Translator

    if not is_installed():
        raise SystemExit("modelo não instalado")
    translator = Translator(model_path())
    with path.open("w", encoding="utf-8") as stream:
        for name, directory in CORPORA.items():
            items = [
                item
                for f in sorted(directory.glob("*.txt"))
                for item in segment(normalize(f.read_text(encoding="utf-8")))
                if item.kind is not SegmentKind.LITERAL and item.text.strip()
            ]
            for item, outcome in zip(
                items, translator.translate_all(items), strict=True
            ):
                stream.write(
                    json.dumps(
                        {
                            "corpus": name,
                            "kind": item.kind.name,
                            "source": item.text,
                            "output": outcome.text,
                            "translated": outcome.translated,
                        },
                        ensure_ascii=False,
                    )
                    + "\n"
                )
            print(f"{name}: {len(items)} segmentos", file=sys.stderr)


def read_labels() -> dict[str, str]:
    labels: dict[str, str] = {}
    for row in LABELS_PATH.read_text(encoding="utf-8").splitlines():
        if row.startswith("#") or not row.strip():
            continue
        key, _, verdict, _ = row.split("\t", 3)
        labels[key] = verdict
    return labels


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dump", type=Path, default=Path("/tmp/babelt-omission.jsonl"))
    args = parser.parse_args()

    if not args.dump.exists():
        build_dump(args.dump)

    ratios: list[tuple[float, str]] = []
    for row in args.dump.read_text(encoding="utf-8").splitlines():
        record = json.loads(row)
        if not record["translated"]:
            continue
        source = words(record["source"])
        if len(source) < MIN_SOURCE_WORDS:
            continue
        ratios.append((len(words(record["output"])) / len(source), digest(record["source"])))

    ratios.sort()
    values = [value for value, _ in ratios]

    def percentile(fraction: float) -> float:
        return values[int(fraction * (len(values) - 1))]

    print("=" * 72)
    print("COBERTURA DE CONTEÚDO — razão palavras(PT) / palavras(EN)")
    print("=" * 72)
    print(f"traduções aceitas com >= {MIN_SOURCE_WORDS} palavras: {len(values)}")
    print(
        f"  min={values[0]:.2f}  p01={percentile(.01):.2f}  p05={percentile(.05):.2f}  "
        f"p10={percentile(.10):.2f}  mediana={percentile(.5):.2f}  max={values[-1]:.2f}"
    )

    labels = read_labels()
    print()
    print("-" * 72)
    print("CUSTO E GANHO POR LIMIAR (rotulagem manual da cauda abaixo de 0,90)")
    print("-" * 72)
    print(f"{'limiar':>7} {'rejeita':>8} {'omissões':>9} {'boas':>6} {'precisão':>9} {'custo':>7}")
    for threshold in (0.75, 0.78, 0.80, 0.83, 0.85, 0.88, 0.90):
        chosen = [key for value, key in ratios if value < threshold]
        omissions = sum(1 for key in chosen if labels.get(key) == "omissao")
        good = len(chosen) - omissions
        precision = omissions / len(chosen) if chosen else 0.0
        print(
            f"{threshold:7.2f} {len(chosen):8} {omissions:9} {good:6} "
            f"{precision:8.0%} {good / len(values):6.1%}"
        )
    print()
    print(
        "  A precisão não passa de 60% em nenhum limiar: as duas populações se\n"
        "  sobrepõem. Ver README-fase6.md — a regra não foi ligada."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
