"""Tradução de cabeçalhos de seção por tabela.

Cabeçalho de man page não é prosa livre: é vocabulário fechado com tradução
canônica. Mandar ``SEE ALSO`` para o modelo daria "VEJA TAMBÉM" numa página e
"CONSULTE TAMBÉM" na seguinte, e o leitor perde a âncora que usa para navegar
entre páginas. Por isso a tradução vem de :download:`headers.txt`, editável,
e não do NMT.

Um cabeçalho ausente da tabela fica em inglês, sem erro — falhar por omissão é
visível e corrigível acrescentando uma linha.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import replace
from pathlib import Path
from typing import Final

from manbr.segment import Segment

__all__ = ["HEADERS", "apply_headers", "load_headers", "translate_header"]

_HEADERS_PATH: Final = Path(__file__).parent / "headers.txt"


def load_headers(path: Path = _HEADERS_PATH) -> dict[str, str]:
    """Lê a tabela, ignorando comentários e linhas vazias."""
    table: dict[str, str] = {}
    for number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        entry = raw.split("#", 1)[0].strip()
        if not entry:
            continue
        if "\t" not in entry:
            raise ValueError(f"{path}:{number}: esperado INGLÊS<TAB>PORTUGUÊS")
        english, portuguese = (part.strip() for part in entry.split("\t", 1))
        if not english or not portuguese:
            raise ValueError(f"{path}:{number}: lado vazio")
        table[english] = portuguese
    return table


#: Tabela carregada no import.
HEADERS: Final = load_headers()


def translate_header(text: str) -> str:
    """Traduz um cabeçalho de seção; devolve ``text`` intacto se não conhecer.

    A busca é pelo texto sem espaço nas pontas e exata: cabeçalho de man page
    é maiúsculo e fixo, então não há por que normalizar caixa e arriscar casar
    uma linha de tabela que por acaso diga ``NAME``.
    """
    return HEADERS.get(text.strip(), text)


def apply_headers(segments: Iterable[Segment]) -> list[Segment]:
    """Troca os cabeçalhos conhecidos pela forma em pt-BR.

    Não muda a classificação de nenhum segmento — a substituição é de saída.
    Só troca quando o segmento inteiro é o cabeçalho, para não acertar uma
    linha solta dentro de um bloco literal.
    """
    out: list[Segment] = []
    for item in segments:
        translated = translate_header(item.text)
        # `replace` e não `Segment(...)`: um segmento de coluna carrega a
        # esquerda e a posição da coluna, e reconstruir campo a campo as
        # perderia silenciosamente.
        out.append(item if translated == item.text else replace(item, text=translated))
    return out
