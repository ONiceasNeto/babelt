"""Testes de segment.

O invariante duro é o round-trip: `reassemble(segment(t)) == t` para todo `t`
que saia de `normalize`. A classificação é qualidade de tradução — errar manda
prosa para o passe-livre ou manda código para o modelo — e por isso é testada
caso a caso, mas não é o que quebra a correção.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from manbr.normalize import normalize
from manbr.segment import (
    Segment,
    SegmentKind,
    reassemble,
    segment,
    syntax_ratio,
)

CORPUS_DIR = Path(__file__).parent / "corpus"


def corpus_files() -> list[Path]:
    return sorted(CORPUS_DIR.glob("*.txt"))


def kinds_of(text: str) -> list[tuple[SegmentKind, str]]:
    return [(item.kind, item.text) for item in segment(text) if item.text.strip()]


def only_kind(text: str) -> set[SegmentKind]:
    return {kind for kind, _ in kinds_of(text)}


# --------------------------------------------------------------------------
# Round-trip
# --------------------------------------------------------------------------


@pytest.mark.parametrize("path", corpus_files(), ids=lambda p: p.stem)
def test_round_trip_sobre_o_corpus(path: Path) -> None:
    normalized = normalize(path.read_text(encoding="utf-8"))
    assert reassemble(segment(normalized)) == normalized


@pytest.mark.parametrize(
    "text",
    [
        "",
        "\n",
        "uma linha",
        "uma linha\n",
        "a\n\nb\n",
        "a\n\n\n\nb\n",  # corrida de brancos maior que a do corpus
        "   indentado\n",
        "NAME\n       ss - utilitário\n\nOPTIONS\n       -a, --all\n",
        "       tabela   com    colunas\n",
        "\n\n\n",
    ],
)
def test_round_trip_casos_avulsos(text: str) -> None:
    assert reassemble(segment(text)) == text


@pytest.mark.parametrize("path", corpus_files(), ids=lambda p: p.stem)
def test_segmentos_cobrem_todas_as_linhas(path: Path) -> None:
    normalized = normalize(path.read_text(encoding="utf-8"))
    total = sum(item.text.count("\n") + 1 for item in segment(normalized))
    assert total == len(normalized.split("\n"))


def test_pipeline_e_idempotente() -> None:
    """reassemble(segment(normalize(t))) é ponto fixo de normalize."""
    for path in corpus_files():
        once = normalize(path.read_text(encoding="utf-8"))
        assert normalize(reassemble(segment(once))) == once


# --------------------------------------------------------------------------
# Classificação
# --------------------------------------------------------------------------


class TestClassificacao:
    @pytest.mark.parametrize(
        "header", ["NAME", "SYNOPSIS", "SEE ALSO", "EXIT STATUS", "OPTIONS"]
    )
    def test_cabecalho_de_secao_e_literal(self, header: str) -> None:
        assert only_kind(header + "\n") == {SegmentKind.LITERAL}

    def test_subtitulo_em_minuscula_e_prosa(self) -> None:
        """'Operation mode' deve ser traduzido; não casa o regex de seção."""
        assert only_kind("   Operation mode\n") == {SegmentKind.PROSE}

    def test_linha_de_comando_e_literal(self) -> None:
        text = "       rsync -avz foo:src/bar/ /data/tmp\n"
        assert only_kind(text) == {SegmentKind.LITERAL}

    def test_frase_comum_e_prosa(self) -> None:
        text = "       Show summary of options.\n"
        assert only_kind(text) == {SegmentKind.PROSE}

    def test_descricao_de_opcao_e_prosa(self) -> None:
        """O nível 14 é descrição, não bloco literal — são 426 linhas no corpus.

        É a hipótese que a medição derrubou: recuo sozinho não separa nada.
        """
        text = (
            "       -h, --help\n"
            "              Show summary of options and exit right away.\n"
        )
        pairs = kinds_of(text)
        assert pairs[0][0] is SegmentKind.LITERAL  # a tag com as flags
        assert pairs[1][0] is SegmentKind.PROSE  # a descrição

    def test_descricao_pendurada_continua_prosa(self) -> None:
        """Tag a 14 e descrição a 21, dentro do mesmo bloco."""
        text = (
            "              ecnseen\n"
            "                     show string if the saw ecn flag is found\n"
        )
        assert SegmentKind.PROSE in only_kind(text)

    def test_bloco_recuado_e_denso_e_literal(self) -> None:
        """Tabela de saída da systemctl: recuada além do bloco anterior."""
        text = (
            "           Produces output similar to\n"
            "\n"
            "               /dev/initctl     systemd-initctl.socket      x.service\n"
        )
        pairs = kinds_of(text)
        assert pairs[0][0] is SegmentKind.PROSE
        assert pairs[1][0] is SegmentKind.LITERAL

    def test_bloco_denso_nao_se_parte(self) -> None:
        """Uma linha mais fraca no meio de um bloco de comandos vai junto.

        É o bloco de exemplo da curl: três linhas passam do limiar e a quarta
        (0.42) ficava de fora, indo para tradução no meio do comando.
        """
        text = (
            "         --variable %HOME\n"
            "         --expand-variable fix@{{HOME}}/.secret\n"
            '         --expand-data "{{fix:trim:url}}"\n'
            "         https://example.com/\n"
        )
        assert only_kind(text) == {SegmentKind.LITERAL}


class TestSecaoDeSintaxe:
    """A seção SYNOPSIS é sintaxe por definição, não prosa.

    Descoberto com o binário rodando: `ss [options] [ FILTER ]` saiu como
    `s [opções] [ FILTRO ]` — o nome do comando perdeu uma letra. A linha era
    PROSE (densidade 0.00, porque "options" e "FILTER" são palavras nuas) e
    passou em todas as regras de validação. Só a seção diz o que a linha é.
    """

    def test_conteudo_da_synopsis_e_literal(self) -> None:
        text = "SYNOPSIS\n       ss [options] [ FILTER ]\n"
        assert only_kind(text) == {SegmentKind.LITERAL}

    def test_secao_seguinte_volta_a_ser_prosa(self) -> None:
        text = (
            "SYNOPSIS\n"
            "       ss [options] [ FILTER ]\n"
            "\n"
            "DESCRIPTION\n"
            "       ss is used to dump socket statistics.\n"
        )
        pairs = kinds_of(text)
        assert pairs[0][0] is SegmentKind.LITERAL  # SYNOPSIS + conteúdo
        assert pairs[-1][0] is SegmentKind.PROSE  # descrição

    @pytest.mark.parametrize("header", ["SYNOPSIS", "SYNTAX", "COMMAND SYNOPSIS"])
    def test_variantes_de_cabecalho(self, header: str) -> None:
        text = f"{header}\n       cmd bare words only\n"
        assert only_kind(text) == {SegmentKind.LITERAL}

    def test_cabecalho_so_conta_na_coluna_zero(self) -> None:
        """'LISTEN UNIT ACTIVATES' recuado é cabeçalho de tabela, não seção."""
        text = (
            "DESCRIPTION\n"
            "       prose here about things\n"
            "\n"
            "               LISTEN           UNIT\n"
            "\n"
            "       more prose here about things\n"
        )
        assert kinds_of(text)[-1][0] is SegmentKind.PROSE


# --------------------------------------------------------------------------
# Agrupamento
# --------------------------------------------------------------------------


class TestAgrupamento:
    def test_prosa_consecutiva_vira_um_paragrafo(self) -> None:
        text = "       linha um da frase\n       linha dois da frase\n"
        pairs = kinds_of(text)
        assert len(pairs) == 1
        assert pairs[0][1] == "linha um da frase\nlinha dois da frase"

    def test_linha_em_branco_separa(self) -> None:
        text = "       um paragrafo\n\n       outro paragrafo\n"
        assert len(kinds_of(text)) == 2

    def test_indentacao_diferente_separa_prosa(self) -> None:
        text = "       nivel sete aqui\n              nivel catorze aqui\n"
        assert len(kinds_of(text)) == 2

    def test_indent_registrado(self) -> None:
        items = [item for item in segment("       texto\n") if item.text.strip()]
        assert items[0].indent == 7
        assert items[0].text == "texto"

    def test_indentacao_relativa_preservada_em_literal(self) -> None:
        """indent guarda o recuo comum; o resto fica dentro do texto."""
        text = "       tar --create --file etc.tar\n           --verbose /etc\n"
        items = [item for item in segment(text) if item.text.strip()]
        assert len(items) == 1
        assert items[0].kind is SegmentKind.LITERAL
        assert items[0].indent == 7
        assert items[0].text.split("\n")[1] == "    --verbose /etc"
        assert reassemble(segment(text)) == text


# --------------------------------------------------------------------------
# API
# --------------------------------------------------------------------------


def test_segment_e_imutavel() -> None:
    item = Segment(kind=SegmentKind.PROSE, text="x", indent=0)
    with pytest.raises(AttributeError):
        item.text = "y"  # type: ignore[misc]


def test_syntax_ratio_limites() -> None:
    assert syntax_ratio("") == 0.0
    assert syntax_ratio("   ") == 0.0
    assert syntax_ratio("Show summary of options.") == 0.0
    assert syntax_ratio("--verbose") == 1.0


def test_reassemble_de_lista_vazia() -> None:
    assert reassemble([]) == ""
