"""``babelt doctor``: diz o que está instalado e o que impede o funcionamento.

O programa tem três dependências externas de estado — o modelo baixado, o
cache em disco e as bibliotecas nativas — e cada uma falha de um jeito que a
mensagem de erro normal não explica: modelo ausente parece "não traduziu",
cache de versão antiga parece "traduziu diferente ontem", ctranslate2 sem as
bibliotecas nativas parece um ImportError no meio da página.

O relatório inteiro vai para **stderr**, como todo o resto que não é a
tradução, e o código de saída separa aviso de impedimento: 0 quando dá para
traduzir, 1 quando não dá.
"""

from __future__ import annotations

import importlib
import shutil
from collections.abc import Iterator
from pathlib import Path
from typing import Final

from babelt.cache import PIPELINE_VERSION, Cache, cache_root
from babelt.model import MODEL_ID, is_installed, model_path

#: Nomes que o projeto já teve. O programa se chamou `manbr` até a 0.5.0, e
#: quem usou aquela versão tem um modelo de 227 MB e um cache parados em
#: diretórios que nada mais lê. Não são migrados de propósito — o formato do
#: cache mudou de versão de pipeline no caminho, e o modelo se rebaixa sozinho
#: —, mas ficar em silêncio sobre 227 MB órfãos seria pior.
_FORMER_NAMES: Final = ("manbr",)

__all__ = ["Check", "diagnose", "run"]

#: Bibliotecas que precisam importar para uma tradução acontecer.
_RUNTIME_MODULES: Final = ("ctranslate2", "sentencepiece")


class Check:
    """Um item do diagnóstico.

    ``blocking`` separa o que impede traduzir do que só é bom saber: cache
    obsoleto é aviso (o programa retraduz), modelo ausente é impedimento.
    """

    def __init__(self, label: str, detail: str, *, ok: bool, blocking: bool = False):
        self.label = label
        self.detail = detail
        self.ok = ok
        self.blocking = blocking

    @property
    def mark(self) -> str:
        if self.ok:
            return "ok  "
        return "ERRO" if self.blocking else "aviso"


def _directory_size(directory: Path) -> int:
    return sum(item.stat().st_size for item in directory.rglob("*") if item.is_file())


def _model_checks(directory: Path) -> Iterator[Check]:
    if not is_installed(directory):
        yield Check(
            "modelo",
            f"ausente em {directory} — rode `babelt <comando>` num terminal "
            f"para baixar ({MODEL_ID})",
            ok=False,
            blocking=True,
        )
        return
    size = _directory_size(directory) / 1024 / 1024
    yield Check("modelo", f"{directory} ({size:.0f} MiB)", ok=True)

    meta = directory / "meta.json"
    if meta.is_file():
        yield Check("modelo: proveniência", meta.read_text(encoding="utf-8").strip(), ok=True)
    else:
        # Artefatos gerados por build-model.sh trazem meta.json; um modelo
        # convertido à mão, não. Não impede nada, mas some a rastreabilidade.
        yield Check(
            "modelo: proveniência",
            "sem meta.json — não dá para saber de onde este modelo veio",
            ok=False,
        )


def _cache_checks() -> Iterator[Check]:
    root = cache_root()
    if not root.exists():
        yield Check("cache", f"{root} (ainda não criado)", ok=True)
        return

    stats = Cache(root).stats()
    yield Check(
        "cache",
        f"{root} — {stats.entries} entradas, {stats.bytes / 1024:.0f} KiB",
        ok=True,
    )

    meta = Cache(root).read_meta()
    stored = meta.get("pipeline_version")
    if stored is None:
        yield Check("cache: versão de pipeline", "sem meta.json", ok=False)
    elif stored != PIPELINE_VERSION:
        yield Check(
            "cache: versão de pipeline",
            f"entradas gravadas na versão {stored}, o programa está na "
            f"{PIPELINE_VERSION} — elas nunca mais serão lidas e podem ser "
            f"apagadas (`rm -rf {root}`)",
            ok=False,
        )
    else:
        yield Check("cache: versão de pipeline", str(stored), ok=True)


def _dependency_checks() -> Iterator[Check]:
    for name in _RUNTIME_MODULES:
        try:
            module = importlib.import_module(name)
        except Exception as error:  # noqa: BLE001 - qualquer falha é a mesma
            yield Check(name, f"não importa: {error}", ok=False, blocking=True)
            continue
        version = getattr(module, "__version__", "versão desconhecida")
        yield Check(name, str(version), ok=True)


def _orphan_checks() -> Iterator[Check]:
    """Diretórios de dados de um nome antigo do projeto."""
    for name in _FORMER_NAMES:
        for label, directory in (
            ("cache", cache_root().parent / name),
            ("modelo", model_path().parents[1].parent / name),
        ):
            if not directory.is_dir():
                continue
            size = _directory_size(directory) / 1024 / 1024
            yield Check(
                f"órfão de {name} ({label})",
                f"{directory} ({size:.0f} MiB) — de quando o programa se "
                f"chamava {name}; nada mais lê, pode remover",
                ok=False,
            )


def _man_check() -> Iterator[Check]:
    found = shutil.which("man")
    # `man` ausente não impede `babelt --help-of` nem a entrada padrão, só
    # `babelt <página>`. É aviso, não erro.
    yield Check(
        "man",
        found or "não está no PATH — `babelt <página>` não vai funcionar",
        ok=found is not None,
    )


def diagnose(version: str, model_directory: Path | None = None) -> list[Check]:
    """Roda todos os itens do diagnóstico, na ordem em que são impressos."""
    return [
        Check("babelt", version, ok=True),
        Check("versão de pipeline", str(PIPELINE_VERSION), ok=True),
        *_model_checks(model_directory or model_path()),
        *_cache_checks(),
        *_dependency_checks(),
        *_man_check(),
        *_orphan_checks(),
    ]


def run(version: str, model_directory: Path | None = None) -> int:
    """Imprime o diagnóstico em stderr. ``1`` se algo impede traduzir."""
    import sys

    checks = diagnose(version, model_directory)
    width = max(len(check.label) for check in checks)
    for check in checks:
        first, *rest = check.detail.split("\n")
        print(f"{check.mark:<5} {check.label:<{width}}  {first}", file=sys.stderr)
        for line in rest:
            print(f"{'':<5} {'':<{width}}  {line}", file=sys.stderr)

    blocking = [check for check in checks if not check.ok and check.blocking]
    if blocking:
        print(
            f"\n{len(blocking)} item(ns) impedem a tradução.",
            file=sys.stderr,
        )
        return 1
    return 0
