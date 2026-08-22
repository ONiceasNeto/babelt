"""Mede o cache em disco sobre o corpus inteiro.

O número que decide a fase 4 é a diferença entre a passada fria e a quente.
Se a segunda passada não for interativa, o cache não resolveu o problema que
existia para resolver.

    python tests/quality/measure_cache.py                 # corpus inteiro
    python tests/quality/measure_cache.py --limit 3       # três páginas

Escreve num diretório de cache temporário: nunca toca o cache do usuário.
"""

from __future__ import annotations

import argparse
import resource
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT))

CORPUS_DIR = _ROOT / "tests" / "corpus"


@dataclass
class PassResult:
    seconds: float = 0.0
    hits: int = 0
    lookups: int = 0
    translated: int = 0
    english: int = 0
    literal: int = 0
    per_page: list[tuple[str, float, int, int]] = field(default_factory=list)

    @property
    def hit_rate(self) -> float:
        return self.hits / self.lookups if self.lookups else 0.0


def occupied_bytes(root: Path) -> int:
    """Espaço realmente ocupado, contando blocos do sistema de arquivos.

    Entradas de cache são pequenas e cada uma paga um bloco inteiro: a
    diferença entre isto e a soma dos tamanhos é o custo de granularidade.
    """
    disk = subprocess.run(
        ["du", "-sk", str(root)], stdout=subprocess.PIPE, text=True, check=False
    )
    return int(disk.stdout.split()[0]) * 1024 if disk.stdout.strip() else 0


def run_pass(pages: list[Path], cache_dir: Path, model_dir: Path, beam: int) -> PassResult:
    from babelt.cache import Cache
    from babelt.model import MODEL_ID
    from babelt.translate import Translator
    from babelt.__main__ import translate_document

    translator = Translator(model_dir, beam_size=beam)
    result = PassResult()

    for page in pages:
        cache = Cache(cache_dir, provenance={"model": MODEL_ID, "beam": beam})
        source = page.read_text(encoding="utf-8")
        started = time.perf_counter()
        _, counters = translate_document(
            source, translator, cache, model=MODEL_ID, beam=beam
        )
        elapsed = time.perf_counter() - started

        stats = cache.stats()
        prose = counters["translated"] + counters["english"]
        result.seconds += elapsed
        result.hits += stats.hits
        result.lookups += stats.hits + stats.misses
        result.translated += counters["translated"]
        result.english += counters["english"]
        result.literal += counters["literal"]
        result.per_page.append((page.stem, elapsed, prose, counters["cache_hits"]))

    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=0, help="só as N primeiras páginas")
    parser.add_argument("--beam", type=int, default=1)
    parser.add_argument("--cache-dir", type=Path, default=None)
    args = parser.parse_args()

    from babelt.model import is_installed, model_path

    model_dir = model_path()
    if not is_installed(model_dir):
        print("modelo não instalado", file=sys.stderr)
        return 1

    pages = sorted(CORPUS_DIR.glob("*.txt"))
    if args.limit:
        pages = pages[: args.limit]

    cache_dir = args.cache_dir or Path("/tmp/babelt-measure-cache")
    shutil.rmtree(cache_dir, ignore_errors=True)
    cache_dir.mkdir(parents=True)

    print(f"páginas: {len(pages)}  beam: {args.beam}  cache: {cache_dir}", flush=True)

    cold = run_pass(pages, cache_dir, model_dir, args.beam)
    entries = sum(1 for p in (cache_dir / "entries").rglob("*") if p.is_file())
    logical = sum(p.stat().st_size for p in (cache_dir / "entries").rglob("*") if p.is_file())
    on_disk = occupied_bytes(cache_dir)

    warm = run_pass(pages, cache_dir, model_dir, args.beam)
    peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024

    prose = cold.translated + cold.english
    print()
    print("## passada fria")
    print(f"segmentos de prosa      {prose}")
    print(f"literais                {cold.literal}")
    print(f"traduzidos              {cold.translated} ({cold.translated / prose:.1%})")
    print(f"em inglês               {cold.english} ({cold.english / prose:.1%})")
    print(f"acertos de cache        {cold.hits}/{cold.lookups} ({cold.hit_rate:.1%})")
    print(f"tempo                   {cold.seconds:.0f}s ({cold.seconds / prose:.2f}s/segmento)")
    print()
    print("## passada quente")
    print(f"acertos de cache        {warm.hits}/{warm.lookups} ({warm.hit_rate:.1%})")
    print(f"tempo                   {warm.seconds:.1f}s")
    print(f"aceleração              {cold.seconds / warm.seconds:.0f}x")
    print()
    print("## cache em disco")
    print(f"entradas                {entries}")
    print(f"conteúdo                {logical / 1024:.0f} KiB")
    print(f"ocupação real           {on_disk / 1024:.0f} KiB")
    print(f"pico de memória         {peak:.0f} MB")
    print()
    print("## por página (fria)")
    for name, seconds, page_prose, hits in cold.per_page:
        print(f"{name:<12} {seconds:6.1f}s  {page_prose:4d} prosa  {hits:4d} do cache")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
