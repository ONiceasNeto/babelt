"""Configuração comum dos testes.

Os testes que carregam o modelo NMT são marcados ``@pytest.mark.model``. A
marca é declarativa — serve para `pytest -m 'not model'` numa máquina de CI
sem os 230 MB — e o pulo automático mora aqui, num lugar só, para que nenhum
arquivo de teste precise repetir a condição.
"""

from __future__ import annotations

import pytest

from manbr.model import is_installed


def pytest_collection_modifyitems(
    config: pytest.Config, items: list[pytest.Item]
) -> None:
    if is_installed():
        return
    skip = pytest.mark.skip(reason="modelo não instalado")
    for item in items:
        if "model" in item.keywords:
            item.add_marker(skip)
