"""Testes de normalize."""

from __future__ import annotations

from pathlib import Path

import pytest

from babelt.normalize import (
    MAX_JUSTIFICATION_RUN,
    SOFT_HYPHEN,
    expand_tabs,
    normalize,
    strip_overstrike,
)

CORPUS_DIR = Path(__file__).parent / "corpus"
FIXTURES_DIR = Path(__file__).parent / "fixtures"


def corpus_files() -> list[Path]:
    return sorted(CORPUS_DIR.glob("*.txt"))


# --------------------------------------------------------------------------
# Overstrike
# --------------------------------------------------------------------------


class TestOverstrike:
    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("N\bNA\bAM\bME\bE", "NAME"),  # negrito
            ("_\bX_\bY", "XY"),  # sublinhado
            ("X\bX\bX", "X"),  # sobreposição tripla
            ("sem nada", "sem nada"),
            ("", ""),
            ("\bA", "A"),  # backspace no início não apaga nada
        ],
    )
    def test_strip_overstrike(self, raw: str, expected: str) -> None:
        assert strip_overstrike(raw) == expected

    def test_fixture_real_tem_overstrike(self) -> None:
        raw = (FIXTURES_DIR / "overstrike_raw.txt").read_text(encoding="utf-8")
        assert raw.count("\b") > 100

    def test_equivale_a_col_bx(self) -> None:
        """A saída bruta e a passada por `col -bx` normalizam para o mesmo."""
        raw = (FIXTURES_DIR / "overstrike_raw.txt").read_text(encoding="utf-8")
        col = (FIXTURES_DIR / "overstrike_col.txt").read_text(encoding="utf-8")
        assert normalize(raw) == normalize(col)

    def test_nenhum_backspace_sobrevive(self) -> None:
        raw = (FIXTURES_DIR / "overstrike_raw.txt").read_text(encoding="utf-8")
        assert "\b" not in normalize(raw)


# --------------------------------------------------------------------------
# Tabs e controles
# --------------------------------------------------------------------------


class TestTabsEControles:
    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("a\tb", "a       b"),
            ("\tx", "        x"),
            ("12345678\ty", "12345678        y"),
            ("1234567\tz", "1234567 z"),
            ("sem tab", "sem tab"),
        ],
    )
    def test_expand_tabs(self, raw: str, expected: str) -> None:
        assert expand_tabs(raw) == expected

    def test_tab_depende_da_coluna_depois_do_overstrike(self) -> None:
        """X\\bX ocupa uma coluna, não três; o tab stop conta a coluna final."""
        assert normalize("a\bab\tc") == "ab      c"

    def test_cr_removido(self) -> None:
        assert normalize("a\r\nb\r\n") == "a\nb\n"
        assert normalize("a\rb") == "ab"

    def test_controles_removidos(self) -> None:
        assert normalize("a\x00b\x1fc\x7fd") == "abcd"

    def test_quebra_de_linha_preservada(self) -> None:
        assert normalize("a\nb\nc") == "a\nb\nc"


# --------------------------------------------------------------------------
# De-hifenização
# --------------------------------------------------------------------------


class TestDeHifenizacao:
    def test_hifen_do_groff_some(self) -> None:
        assert normalize(f"notifica{SOFT_HYPHEN}\n       tion option") == (
            "notification option"
        )

    def test_hifen_de_composto_fica(self) -> None:
        """set- + group-ID vira set-group-ID, não setgroup-ID."""
        assert normalize("set-\n       group-ID bits") == "set-group-ID bits"

    def test_palavra_quebrada_em_tres_linhas(self) -> None:
        text = f"tres li{SOFT_HYPHEN}\nnhas as{SOFT_HYPHEN}\nsim"
        assert normalize(text) == "tres linhas assim"

    @pytest.mark.parametrize(
        "text",
        [
            "----\nabc",  # régua, não hifenização
            "a -\nb",  # travessão solto no fim da linha
            f"x{SOFT_HYPHEN}\n\ny",  # linha em branco no meio
            "x-\nMAIÚSCULA segue",  # continuação não começa em minúscula
        ],
    )
    def test_nao_junta(self, text: str) -> None:
        assert "\n" in normalize(text)

    def test_indentacao_da_continuacao_some(self) -> None:
        result = normalize(f"       parte{SOFT_HYPHEN}\n              dois")
        assert result == "       partedois"


# --------------------------------------------------------------------------
# Espaço
# --------------------------------------------------------------------------


class TestEspaco:
    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("ss  is  used", "ss is used"),
            ("a   b", "a b"),
            ("a    b", "a    b"),  # 4 espaços: layout de coluna, fica
            ("a          b", "a          b"),
        ],
    )
    def test_colapsa_so_justificacao(self, raw: str, expected: str) -> None:
        assert normalize(raw) == expected

    def test_limiar_documentado(self) -> None:
        collapsed = normalize("a" + " " * MAX_JUSTIFICATION_RUN + "b")
        kept = normalize("a" + " " * (MAX_JUSTIFICATION_RUN + 1) + "b")
        assert collapsed == "a b"
        assert kept == "a" + " " * (MAX_JUSTIFICATION_RUN + 1) + "b"

    def test_indentacao_nunca_e_tocada(self) -> None:
        """A indentação é o sinal que o segmentador usa."""
        for width in (3, 7, 11, 14, 21):
            line = " " * width + "texto  aqui"
            assert normalize(line) == " " * width + "texto aqui"

    def test_espaco_no_fim_da_linha_some(self) -> None:
        assert normalize("abc   \ndef  ") == "abc\ndef"

    def test_tabela_preservada(self) -> None:
        row = "       /dev/initctl     systemd-initctl.socket      x.service"
        assert normalize(row) == row


# --------------------------------------------------------------------------
# Propriedades
# --------------------------------------------------------------------------


@pytest.mark.parametrize("path", corpus_files(), ids=lambda p: p.stem)
def test_idempotente_sobre_o_corpus(path: Path) -> None:
    once = normalize(path.read_text(encoding="utf-8"))
    assert normalize(once) == once


@pytest.mark.parametrize("path", corpus_files(), ids=lambda p: p.stem)
def test_nao_perde_linhas_demais(path: Path) -> None:
    """Só a de-hifenização pode reduzir o número de linhas."""
    text = path.read_text(encoding="utf-8")
    assert len(normalize(text).splitlines()) <= len(text.splitlines())


def test_texto_vazio() -> None:
    assert normalize("") == ""


def test_so_brancos() -> None:
    assert normalize("   \n  \n") == "\n\n"
