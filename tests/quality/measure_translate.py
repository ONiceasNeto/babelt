"""Mede a tradução sobre o corpus.

O número que decide a fase é a taxa de rejeição por validação. Se for alta, o
modelo está perdendo placeholders e o mascaramento precisa de reforço antes de
qualquer CLI.

    python tests/quality/measure_translate.py            # corpus inteiro
    python tests/quality/measure_translate.py --limit 80 # amostra rápida
"""

from __future__ import annotations

import argparse
import resource
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT))

if TYPE_CHECKING:  # pragma: no cover
    from manbr.segment import Segment
    from manbr.translate import TranslationOutcome

QUALITY_DIR = Path(__file__).parent
CORPUS_DIR = _ROOT / "tests" / "corpus"
SAMPLE_PATH = QUALITY_DIR / "sample.md"
SAMPLE_COUNT = 30


@dataclass
class Timings:
    imports: float = 0.0
    load: float = 0.0
    paragraph_pass: float = 0.0
    corpus: float = 0.0
    single_page: float = 0.0


def peak_memory_mb() -> float:
    """Pico de RSS deste processo. No Linux ru_maxrss vem em KiB."""
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=0, help="máximo de segmentos")
    parser.add_argument("--no-sample", action="store_true")
    args = parser.parse_args()

    timings = Timings()

    started = time.perf_counter()
    from manbr.mask import mask
    from manbr.model import is_installed, model_path
    from manbr.normalize import normalize
    from manbr.segment import SegmentKind, segment
    from manbr.translate import Translator, split_sentences
    from manbr.validate import validate, validate_structure

    timings.imports = time.perf_counter() - started

    if not is_installed():
        print("modelo não instalado; rode manbr.model.download()", file=sys.stderr)
        return 1

    documents = {
        path.name: segment(normalize(path.read_text(encoding="utf-8")))
        for path in sorted(CORPUS_DIR.glob("*.txt"))
    }
    every = [item for items in documents.values() for item in items]
    prose = [
        item
        for item in every
        if item.kind is SegmentKind.PROSE and item.text.strip()
    ]
    if args.limit:
        prose = prose[: args.limit]

    translator = Translator(model_path())

    started = time.perf_counter()
    translator._load_engine()  # noqa: SLF001 - medir a carga é o objetivo
    timings.load = time.perf_counter() - started

    # ---- diagnóstico de vocabulário (sem inferência) --------------------
    masked_all = [mask(item.text) for item in prose]
    oov_total = 0
    oov_coverage = 0
    oov_examples: list[tuple[str, list[str]]] = []
    from manbr.translate import to_wire

    for item, result in zip(prose, masked_all, strict=True):
        pieces, coverage = translator.oov_diagnosis(to_wire(result.text))
        if not pieces:
            continue
        oov_total += 1
        oov_coverage += int(coverage)
        if len(oov_examples) < 6:
            oov_examples.append((item.text[:70], pieces[:6]))

    # ---- uma passada de modelo, dois conjuntos de regras -----------------
    # Traduz TODOS os parágrafos, inclusive os que a guarda de OOV barraria,
    # para poder responder quantos a fase 3 aprovava e a 3.1 rejeita.
    started = time.perf_counter()
    raw = translator._translate_texts(  # noqa: SLF001
        [result.text for result in masked_all]
    )
    timings.paragraph_pass = time.perf_counter() - started

    fase3_ok = 0
    fase31_ok = 0
    newly_rejected = 0
    by_rule: dict[str, int] = {}
    for item, result, output in zip(prose, masked_all, raw, strict=True):
        placeholders = validate(result.text, output, result.tokens)
        structure = validate_structure(result.text, output)
        pieces, _ = translator.oov_diagnosis(to_wire(result.text))

        if placeholders.ok:
            fase3_ok += 1
        if placeholders.ok and structure.ok and not pieces:
            fase31_ok += 1
        elif placeholders.ok:
            newly_rejected += 1
            if pieces:
                key = "guarda de vocabulário (oov)"
            else:
                assert structure.reason is not None
                key = structure.reason.split(":")[0]
            by_rule[key] = by_rule.get(key, 0) + 1

    # ---- corpus -------------------------------------------------------
    started = time.perf_counter()
    outcomes = translator.translate_all(prose)
    timings.corpus = time.perf_counter() - started

    # ---- uma página isolada -------------------------------------------
    ss_prose = [
        item
        for item in documents["ss.txt"]
        if item.kind is SegmentKind.PROSE and item.text.strip()
    ]
    # Tradutor novo de propósito: com o cache do corpus quente, esta medida
    # daria 0.0s e não diria nada sobre o custo real de abrir uma página.
    fresh = Translator(model_path())
    fresh._load_engine()  # noqa: SLF001 - tirar a carga da conta
    started = time.perf_counter()
    fresh.translate_all(ss_prose)
    timings.single_page = time.perf_counter() - started

    # ---- contabilidade -------------------------------------------------
    translated = [o for o in outcomes if o.translated]
    english = [o for o in outcomes if not o.translated]
    partial = [o for o in outcomes if o.reason is not None and o.translated]

    with_placeholder = [
        (item, outcome)
        for item, outcome in zip(prose, outcomes, strict=True)
        if mask(item.text).tokens
    ]
    ph_english = [o for _, o in with_placeholder if not o.translated]

    print("=" * 72)
    print("TRADUÇÃO DO CORPUS")
    print("=" * 72)
    print(f"segmentos PROSE traduzidos : {len(prose)}")
    print(f"  com ao menos um placeholder: {len(with_placeholder)}")
    print()
    print("-" * 72)
    print("REJEIÇÃO POR VALIDAÇÃO")
    print("-" * 72)
    rejected_paragraph = len(partial) + len(english)
    print(
        f"  parágrafos aceitos direto      : {len(translated) - len(partial):5} "
        f"({(len(translated) - len(partial)) / len(prose):6.1%})"
    )
    print(
        f"  parágrafos rejeitados          : {rejected_paragraph:5} "
        f"({rejected_paragraph / len(prose):6.1%})"
    )
    print(
        f"    recuperados por sentença     : {len(partial):5} "
        f"(parcialmente traduzidos)"
    )
    print(
        f"    sem nada aproveitável        : {len(english):5} "
        f"({len(english) / len(prose):6.1%})"
    )
    print()
    print(
        f"  segmentos que saíram em inglês : {len(english):5} "
        f"({len(english) / len(prose):6.1%})"
    )
    if with_placeholder:
        print(
            f"  dos que tinham placeholder     : {len(ph_english):5} "
            f"({len(ph_english) / len(with_placeholder):6.1%})"
        )

    reasons: dict[str, int] = {}
    for outcome in outcomes:
        if outcome.reason:
            reasons[outcome.reason] = reasons.get(outcome.reason, 0) + 1
    if reasons:
        print("\n  motivos registrados:")
        for key, value in sorted(reasons.items(), key=lambda kv: -kv[1])[:8]:
            print(f"    {value:4}  {key}")

    # ---- deriva de sentenças -------------------------------------------
    drift = 0
    multi = 0
    for item, outcome in zip(prose, outcomes, strict=True):
        before = len(split_sentences(mask(item.text).text)[0::2])
        if before < 2 or not outcome.translated:
            continue
        multi += 1
        after = len(split_sentences(mask(outcome.text).text)[0::2])
        if before != after:
            drift += 1
    print()
    print("-" * 72)
    print("GUARDA DE VOCABULÁRIO (parte A)")
    print("-" * 72)
    print(f"  segmentos com <unk> na origem     : {oov_total} "
          f"({oov_total / len(prose):.1%})")
    print(f"    buraco de cobertura do mask     : {oov_coverage}")
    print(f"    buraco de vocabulário do modelo : {oov_total - oov_coverage}")
    for text, pieces in oov_examples:
        print(f"      {pieces} | {text}")

    print()
    print("-" * 72)
    print("FASE 3 vs FASE 3.1, mesmas saídas do modelo (parte C)")
    print("-" * 72)
    print(f"  parágrafos aprovados pela fase 3  : {fase3_ok} "
          f"({fase3_ok / len(prose):.1%})")
    print(f"  parágrafos aprovados pela fase 3.1: {fase31_ok} "
          f"({fase31_ok / len(prose):.1%})")
    print(f"  APROVADOS NA 3 E REJEITADOS NA 3.1: {newly_rejected} "
          f"({newly_rejected / max(fase3_ok, 1):.1%} dos aprovados na 3)")
    print("\n  por regra:")
    for key, value in sorted(by_rule.items(), key=lambda kv: -kv[1]):
        print(f"    {value:4}  {key}")

    print()
    print("-" * 72)
    print("DERIVA DE SENTENÇAS (o que validate não via)")
    print("-" * 72)
    print(f"  parágrafos multi-frase traduzidos : {multi}")
    if multi:
        print(f"  com contagem de frases alterada   : {drift} ({drift / multi:.1%})")

    # ---- tempo e memória -----------------------------------------------
    words = sum(len(item.text.split()) for item in prose)
    print()
    print("-" * 72)
    print("TEMPO E MEMÓRIA")
    print("-" * 72)
    print(f"  import dos módulos      : {timings.imports:8.3f}s")
    print(f"  carga do modelo         : {timings.load:8.3f}s")
    print(
        f"  passada de parágrafos   : {timings.paragraph_pass:8.1f}s  <- custo real,"
        f" cache frio ({timings.paragraph_pass / len(prose):.2f}s/segmento)"
    )
    print(
        f"  translate_all ({len(prose)} seg.): {timings.corpus:8.1f}s  <- cache já"
        f" quente da passada acima; mede a recuperação por sentença"
    )
    print(
        f"  man ss ({len(ss_prose)} segmentos)   : {timings.single_page:8.1f}s"
    )
    print(f"  pico de memória         : {peak_memory_mb():8.0f} MB")
    total_lookups = translator.cache_hits + translator.cache_misses
    print(
        f"  cache: {translator.cache_hits} acertos / {total_lookups} consultas "
        f"({translator.cache_hits / max(total_lookups, 1):.1%})"
    )
    print(f"  beam_size               : {translator._beam_size}")  # noqa: SLF001

    # ---- amostra --------------------------------------------------------
    if not args.no_sample:
        write_sample(prose, outcomes)
        print(f"\namostra de {SAMPLE_COUNT} traduções em {SAMPLE_PATH}")

    return 0


def write_sample(
    prose: list[Segment], outcomes: list[TranslationOutcome]
) -> None:
    """Grava lado a lado para inspeção manual."""
    pairs = list(zip(prose, outcomes, strict=True))
    step = max(1, len(pairs) // SAMPLE_COUNT)
    chosen = pairs[::step][:SAMPLE_COUNT]

    lines = [
        "# Amostra de traduções — fase 3",
        "",
        "Gerado por `tests/quality/measure_translate.py`. Serve para inspeção",
        "manual: a validação garante que a sintaxe sobreviveu, não que o",
        "português esteja bom.",
        "",
    ]
    for number, (item, outcome) in enumerate(chosen, 1):
        status = "traduzido" if outcome.translated else "**mantido em inglês**"
        if outcome.reason:
            status += f" — {outcome.reason}"
        lines += [
            f"## {number}. {status}",
            "",
            "**EN**",
            "",
            "```",
            item.text,
            "```",
            "",
            "**pt-BR**",
            "",
            "```",
            outcome.text,
            "```",
            "",
        ]
    SAMPLE_PATH.write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
