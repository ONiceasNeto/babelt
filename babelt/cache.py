"""Cache em disco de segmentos traduzidos.

A frio, uma man page custa ~27 segundos. O cache não é otimização: é o que
faz o programa ser usável. Por isso é desenhado como artefato portável — pode
ser gerado numa máquina e consumido em outra — e não como um detalhe interno.

Duas decisões que vale explicar:

**Granularidade por segmento, não por documento.** Os 46.6% de acerto medidos
na fase 3.1 só existem nesse nível: man pages repetem parágrafos inteiros
("Show summary of options.") entre páginas diferentes. Cache por documento
acertaria só quando a página inteira fosse idêntica.

**A chave é o hash do texto, não a versão do programa documentado.** Versão de
pacote muda sem a página mudar, e a página muda sem a versão mudar. O hash do
texto normalizado detecta exatamente a mudança que importa, no nível do
parágrafo. Versão, quando registrada, é metadado — nunca chave.
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Final

__all__ = [
    "CACHE_FORMAT",
    "PIPELINE_VERSION",
    "Cache",
    "CacheStats",
    "cache_root",
    "make_key",
]

#: Versão do pipeline de texto. **Incremente ao mudar `mask`, `segment`,
#: `normalize` ou `validate`**: entra na chave, então um bump invalida tudo
#: sozinho, sem apagar nada e sem migração.
#:
#: 5 — fase 9: a coluna de tabela de `segment` passou a ser eleita sobre o
#:     documento, e não sobre o bloco, o que muda a segmentação de todo
#:     `--help` com linha em branco no meio da lista de opções. Junto, o
#:     motivo de rejeição guardado passou a carregar a causa, e sem o bump
#:     `--stats` misturaria o formato velho com o novo.
#: 4 — fase 6: mask reconhece lista separada por vírgula; título de bloco de
#:     --help virou cabeçalho, isolado no próprio segmento.
#: 3 — fase 5: mask reconhece grupo isolado ({action}, [flags]), sufixo de
#:     tipo (string[]) e alternância solta; segment detecta tabela de duas
#:     colunas e a profundidade de bloco deixou de contar o cabeçalho.
#: 2 — fase 4: a seção SYNOPSIS passou a ser classificada como bloco literal.
#: 1 — fases 1 a 3.1.
PIPELINE_VERSION: Final = 5

#: Versão do formato em disco. Muda se o layout dos arquivos mudar.
CACHE_FORMAT: Final = 1

_META_NAME: Final = "meta.json"
_ENTRIES_DIR: Final = "entries"


def cache_root() -> Path:
    """``~/.cache/babelt``, respeitando ``XDG_CACHE_HOME``."""
    xdg = os.environ.get("XDG_CACHE_HOME")
    base = Path(xdg) if xdg else Path.home() / ".cache"
    return base / "babelt"


def make_key(
    text: str,
    *,
    model: str,
    beam: int,
    pipeline_version: int = PIPELINE_VERSION,
) -> str:
    """SHA-256 do texto mais tudo que muda a tradução dele.

    Modelo e beam entram porque a mesma frase traduzida por outro modelo, ou
    com outro feixe, é outro resultado. A versão do pipeline entra porque
    mudar `mask` muda o texto que chega ao modelo.
    """
    digest = hashlib.sha256()
    for part in (str(pipeline_version), model, str(beam), text):
        digest.update(part.encode("utf-8"))
        digest.update(b"\x00")
    return digest.hexdigest()


@dataclass(frozen=True)
class CacheStats:
    """Contabilidade de uma instância de :class:`Cache`."""

    hits: int
    misses: int
    entries: int
    bytes: int

    @property
    def hit_rate(self) -> float:
        total = self.hits + self.misses
        return self.hits / total if total else 0.0


class Cache:
    """Mapa persistente de chave para texto traduzido.

    Escrita atômica: cada entrada vai para um temporário no mesmo diretório e
    depois é renomeada. Um Ctrl-C no meio deixa o cache íntegro, com uma
    entrada a menos — nunca com uma entrada pela metade.
    """

    def __init__(self, root: Path, *, provenance: dict[str, Any] | None = None) -> None:
        self._root = root
        self._entries = root / _ENTRIES_DIR
        self._provenance = provenance or {}
        self._hits = 0
        self._misses = 0

    @property
    def root(self) -> Path:
        return self._root

    def _path_for(self, key: str) -> Path:
        # Um nível de shard, 256 gavetas. Dois níveis criariam milhares de
        # diretórios quase vazios: o corpus inteiro cabe em ~2 mil entradas, e
        # cada arquivo já custa um bloco do sistema de arquivos.
        return self._entries / key[:2] / key

    def get(self, key: str) -> str | None:
        """Valor guardado, ou ``None``.

        Um arquivo ilegível conta como ausência: cache corrompido faz o
        programa traduzir de novo, nunca falhar.
        """
        path = self._path_for(key)
        try:
            value = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            self._misses += 1
            return None
        self._hits += 1
        return value

    def put(self, key: str, value: str) -> None:
        """Guarda ``value``, atomicamente."""
        path = self._path_for(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        handle, temporary = tempfile.mkstemp(dir=path.parent, prefix=".tmp-")
        try:
            with os.fdopen(handle, "w", encoding="utf-8") as stream:
                stream.write(value)
            os.replace(temporary, path)
        except BaseException:
            Path(temporary).unlink(missing_ok=True)
            raise
        self._write_meta()

    def stats(self) -> CacheStats:
        entries = 0
        size = 0
        if self._entries.is_dir():
            for path in self._entries.rglob("*"):
                if path.is_file() and not path.name.startswith(".tmp-"):
                    entries += 1
                    size += path.stat().st_size
        return CacheStats(
            hits=self._hits, misses=self._misses, entries=entries, bytes=size
        )

    def _write_meta(self) -> None:
        """Proveniência do cache. Sem isto o artefato não é portável."""
        path = self._root / _META_NAME
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        meta: dict[str, Any] = {
            "format": CACHE_FORMAT,
            "pipeline_version": PIPELINE_VERSION,
            "created": now,
            **self._provenance,
        }
        try:
            existing = json.loads(path.read_text(encoding="utf-8"))
            meta["created"] = existing.get("created", now)
        except (OSError, ValueError):
            pass
        meta["updated"] = now

        path.parent.mkdir(parents=True, exist_ok=True)
        handle, temporary = tempfile.mkstemp(dir=path.parent, prefix=".tmp-")
        try:
            with os.fdopen(handle, "w", encoding="utf-8") as stream:
                json.dump(meta, stream, ensure_ascii=False, indent=2, sort_keys=True)
                stream.write("\n")
            os.replace(temporary, path)
        except BaseException:
            Path(temporary).unlink(missing_ok=True)
            raise

    def read_meta(self) -> dict[str, Any]:
        """Metadados gravados, ou vazio se o cache ainda não existe."""
        try:
            loaded: dict[str, Any] = json.loads(
                (self._root / _META_NAME).read_text(encoding="utf-8")
            )
        except (OSError, ValueError):
            return {}
        return loaded
