"""Testes da própria medição de cobertura.

Não fixam limiar de recall — a fase 1.1 é medição, e o limiar se decide depois
de olhar os números. O que estes testes garantem é que o número medido
significa alguma coisa: que a amostra e a anotação estão sincronizadas com o
corpus e que a reconstrução de spans não escorrega.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

COVERAGE_DIR = Path(__file__).parent / "coverage"
sys.path.insert(0, str(COVERAGE_DIR))

from measure import (  # noqa: E402
    Annotation,
    masked_spans,
    occurrences,
    read_annotations,
    read_sample,
)

SAMPLE = read_sample()
ANNOTATIONS = read_annotations()
CORPUS_DIR = Path(__file__).parent / "corpus"


def test_amostra_tem_o_tamanho_pedido() -> None:
    assert len(SAMPLE) == 200


def test_amostra_cobre_todos_os_arquivos() -> None:
    assert len({name for name, _ in SAMPLE}) == 20


@pytest.mark.parametrize("annotation", ANNOTATIONS, ids=lambda a: f"{a.file}:{a.line}")
def test_anotacao_aponta_para_linha_da_amostra(annotation: Annotation) -> None:
    assert (annotation.file, annotation.line) in SAMPLE


@pytest.mark.parametrize("annotation", ANNOTATIONS, ids=lambda a: f"{a.file}:{a.line}")
def test_token_anotado_ocorre_na_linha(annotation: Annotation) -> None:
    """Uma anotação órfã contaria como falso negativo sem existir."""
    line = SAMPLE[(annotation.file, annotation.line)]
    assert occurrences(line, annotation.token), (
        f"{annotation.token!r} não ocorre (delimitado) em {line!r}"
    )


@pytest.mark.parametrize("key", sorted(SAMPLE), ids=lambda k: f"{k[0]}:{k[1]}")
def test_spans_sincronizados_com_a_linha(key: tuple[str, int]) -> None:
    """masked_spans reconstrói posições no original; o assert interno é o teste."""
    line = SAMPLE[key]
    spans = masked_spans(line)
    for start, stop in spans:
        assert 0 <= start < stop <= len(line)


def test_amostra_bate_com_o_corpus() -> None:
    """Se refresh.sh mexeu no corpus, a amostra congelada precisa ser refeita."""
    drift: list[str] = []
    for (name, number), text in sorted(SAMPLE.items()):
        lines = (CORPUS_DIR / name).read_text(encoding="utf-8").splitlines()
        if number > len(lines) or lines[number - 1].rstrip() != text:
            drift.append(f"{name}:{number}")
    assert not drift, (
        "amostra fora de sincronia com o corpus; rode build_sample.py e "
        f"revise a anotação: {drift}"
    )
