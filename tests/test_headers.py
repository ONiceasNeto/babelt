"""Testes da tabela de cabeçalhos."""

from __future__ import annotations

from pathlib import Path

import pytest

from babelt.headers import HEADERS, apply_headers, load_headers, translate_header
from babelt.normalize import normalize
from babelt.segment import Segment, SegmentKind, reassemble, segment

CORPUS_DIR = Path(__file__).parent / "corpus"

MINIMO = [
    "NAME", "SYNOPSIS", "DESCRIPTION", "OPTIONS", "EXAMPLES", "FILES",
    "ENVIRONMENT", "EXIT STATUS", "RETURN VALUE", "SEE ALSO", "BUGS",
    "AUTHOR", "AUTHORS", "COPYRIGHT", "HISTORY", "NOTES", "CAVEATS",
    "REPORTING BUGS", "DIAGNOSTICS", "CONFORMING TO", "STANDARDS",
    "AVAILABILITY", "COMMANDS", "CONFIGURATION", "SECURITY", "COMPATIBILITY",
]


#: Cabeçalhos cuja forma em pt-BR é a mesma palavra.
IDENTICOS = {"BUGS"}


@pytest.mark.parametrize("header", MINIMO)
def test_cobertura_minima(header: str) -> None:
    assert header in HEADERS
    if header not in IDENTICOS:
        assert translate_header(header) != header


@pytest.mark.parametrize(
    ("english", "portuguese"),
    [
        ("NAME", "NOME"),
        ("SYNOPSIS", "SINOPSE"),
        ("DESCRIPTION", "DESCRIÇÃO"),
        ("SEE ALSO", "VEJA TAMBÉM"),
        ("REPORTING BUGS", "RELATANDO BUGS"),
        ("EXIT STATUS", "STATUS DE SAÍDA"),
    ],
)
def test_traducao_canonica(english: str, portuguese: str) -> None:
    assert translate_header(english) == portuguese


def test_ausente_fica_em_ingles() -> None:
    """Falhar por omissão, sem erro."""
    assert translate_header("THE AWK LANGUAGE") == "THE AWK LANGUAGE"
    assert translate_header("QUALQUER COISA") == "QUALQUER COISA"


def test_espaco_nas_pontas_ignorado() -> None:
    assert translate_header("   OPTIONS  ") == "OPÇÕES"


def test_busca_e_exata_em_caixa() -> None:
    """Não normaliza caixa: evita casar uma linha de tabela que diga 'Name'."""
    assert translate_header("Name") == "Name"
    assert translate_header("name") == "name"


def test_traducoes_iguais_sao_deliberadas() -> None:
    """Só 'BUGS' coincide em pt-BR; qualquer outra igualdade é esquecimento."""
    iguais = {k for k, v in HEADERS.items() if k == v}
    assert iguais <= IDENTICOS, f"entradas sem tradução: {iguais - IDENTICOS}"


class TestArquivo:
    def test_formato_invalido_falha(self, tmp_path: Path) -> None:
        bad = tmp_path / "headers.txt"
        bad.write_text("SEM TAB AQUI\n", encoding="utf-8")
        with pytest.raises(ValueError, match="TAB"):
            load_headers(bad)

    def test_lado_vazio_falha(self, tmp_path: Path) -> None:
        bad = tmp_path / "headers.txt"
        bad.write_text("NAME\t\n", encoding="utf-8")
        with pytest.raises(ValueError, match="vazio"):
            load_headers(bad)

    def test_comentarios_e_vazias_ignorados(self, tmp_path: Path) -> None:
        path = tmp_path / "headers.txt"
        path.write_text("# nota\n\nNAME\tNOME\n", encoding="utf-8")
        assert load_headers(path) == {"NAME": "NOME"}


class TestAplicacaoEmSegmentos:
    def test_substitui_preservando_tipo_e_indentacao(self) -> None:
        items = [Segment(SegmentKind.LITERAL, "DESCRIPTION", 0)]
        (result,) = apply_headers(items)
        assert result.text == "DESCRIÇÃO"
        assert result.kind is SegmentKind.LITERAL  # classificação não muda
        assert result.indent == 0

    def test_prosa_nao_e_tocada(self) -> None:
        items = [Segment(SegmentKind.PROSE, "Show summary of options.", 7)]
        assert apply_headers(items) == items

    def test_so_troca_o_segmento_inteiro(self) -> None:
        """Uma linha 'NAME' dentro de uma tabela não deve virar 'NOME'."""
        table = Segment(SegmentKind.LITERAL, "NAME    SIZE    TYPE", 7)
        assert apply_headers([table]) == [table]

    def test_lista_vazia(self) -> None:
        assert apply_headers([]) == []

    def test_no_pipeline_completo(self) -> None:
        text = "NAME\n       ss - utility\n\nSEE ALSO\n       ip(8)\n"
        out = reassemble(apply_headers(segment(normalize(text))))
        assert out.startswith("NOME\n")
        assert "VEJA TAMBÉM" in out
        assert "ss - utility" in out

    def test_cabecalhos_reais_do_corpus(self) -> None:
        traduzidos = 0
        for path in sorted(CORPUS_DIR.glob("*.txt")):
            items = segment(normalize(path.read_text(encoding="utf-8")))
            for before, after in zip(items, apply_headers(items), strict=True):
                if before.text != after.text:
                    traduzidos += 1
        assert traduzidos >= 60
