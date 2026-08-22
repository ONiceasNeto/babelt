"""Configuração comum dos testes.

Os testes que carregam o modelo NMT são marcados ``@pytest.mark.model``. A
marca é declarativa — serve para `pytest -m 'not model'` numa máquina de CI
sem os 230 MB — e o pulo automático mora aqui, num lugar só, para que nenhum
arquivo de teste precise repetir a condição.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest

from babelt.model import is_installed


def pytest_collection_modifyitems(
    config: pytest.Config, items: list[pytest.Item]
) -> None:
    if is_installed():
        return
    skip = pytest.mark.skip(reason="modelo não instalado")
    for item in items:
        if "model" in item.keywords:
            item.add_marker(skip)


@pytest.fixture
def fake_model() -> Callable[..., Path]:
    """Cria um diretório com a cara de um modelo convertido.

    Vive aqui, e não num arquivo de teste, porque dois arquivos precisam dele:
    importar de `tests.test_model` faria o mypy ver o mesmo arquivo com dois
    nomes de módulo.
    """

    def build(directory: Path, *, vocabulary: str = "shared_vocabulary.json") -> Path:
        directory.mkdir(parents=True, exist_ok=True)
        (directory / "model.bin").write_bytes(b"pesos")
        (directory / "source.spm").write_bytes(b"spm")
        (directory / "target.spm").write_bytes(b"spm")
        (directory / vocabulary).write_text("[]", encoding="utf-8")
        return directory

    return build
