"""Testes de validate.

Esta é a rede de segurança do projeto: só uma tradução que preserve todos os
placeholders, e só uma vez cada, pode ser usada. Reordenar é permitido; perder,
duplicar, inventar ou quebrar um placeholder não é.
"""

from __future__ import annotations

import pytest

from manbr.mask import CLOSE, OPEN, mask
from manbr.validate import MAX_LENGTH_RATIO, MIN_LENGTH_RATIO, validate


def ph(index: int) -> str:
    return f"{OPEN}{index}{CLOSE}"


# --------------------------------------------------------------------------
# Casos válidos
# --------------------------------------------------------------------------


def test_traducao_valida() -> None:
    original = f"Use {ph(0)} to list {ph(1)}."
    translated = f"Use {ph(0)} para listar {ph(1)}."
    result = validate(original, translated, {0: "-l", 1: "/etc"})
    assert result.ok
    assert result.reason is None


def test_reordenacao_e_permitida() -> None:
    """A ordem das palavras muda entre inglês e português."""
    original = f"Read {ph(0)} from {ph(1)}"
    translated = f"Leia de {ph(1)} o arquivo {ph(0)}"
    assert validate(original, translated, {0: "-f", 1: "/tmp"}).ok


def test_sem_placeholders() -> None:
    assert validate("Print a summary.", "Imprime um resumo.", {}).ok


def test_chaves_escapadas_nao_sao_placeholders() -> None:
    """⟦⟦ é um ⟦ literal do texto de origem, não um placeholder quebrado."""
    original = f"a {OPEN}{OPEN} b {CLOSE}{CLOSE} {ph(0)}"
    translated = f"a {OPEN}{OPEN} b {CLOSE}{CLOSE} {ph(0)}"
    assert validate(original, translated, {0: "-v"}).ok


def test_fluxo_completo_a_partir_de_mask() -> None:
    masked = mask("Use --verbose with /etc/services.")
    translated = masked.text.replace("Use", "Use o").replace("with", "com")
    assert validate(masked.text, translated, masked.tokens).ok


# --------------------------------------------------------------------------
# Regra 1: cada índice exatamente uma vez
# --------------------------------------------------------------------------


def test_placeholder_ausente() -> None:
    original = f"{ph(0)} and {ph(1)} and {ph(2)}"
    translated = f"{ph(0)} e {ph(1)} e mais"
    result = validate(original, translated, {0: "-a", 1: "-b", 2: "-c"})
    assert not result.ok
    assert result.reason == "placeholder 2 ausente"


def test_placeholder_duplicado() -> None:
    original = f"{ph(0)} and {ph(1)}"
    translated = f"{ph(0)} e {ph(1)} e {ph(1)}"
    result = validate(original, translated, {0: "-a", 1: "-b"})
    assert not result.ok
    assert result.reason is not None
    assert result.reason.startswith("placeholder 1 duplicado")


def test_todos_os_placeholders_perdidos() -> None:
    result = validate(f"{ph(0)} x", "traduzido sem nada", {0: "-a"})
    assert not result.ok
    assert result.reason == "placeholder 0 ausente"


def test_reason_aponta_o_menor_indice_ausente() -> None:
    original = f"{ph(0)} {ph(1)} {ph(2)}"
    result = validate(original, "nada aqui além de texto", {0: "a", 1: "b", 2: "c"})
    assert result.reason == "placeholder 0 ausente"


# --------------------------------------------------------------------------
# Regra 2: nenhum índice fora de tokens
# --------------------------------------------------------------------------


def test_placeholder_extra() -> None:
    original = f"{ph(0)} only"
    translated = f"{ph(0)} e também {ph(1)}"
    result = validate(original, translated, {0: "-a"})
    assert not result.ok
    assert result.reason == "placeholder 1 inesperado"


def test_placeholder_extra_sem_nenhum_token() -> None:
    result = validate("texto puro", f"texto {ph(0)} puro", {})
    assert not result.ok
    assert result.reason == "placeholder 0 inesperado"


# --------------------------------------------------------------------------
# Regra 3: tradução vazia
# --------------------------------------------------------------------------


@pytest.mark.parametrize("translated", ["", "   ", "\n", "\t \n"])
def test_traducao_vazia(translated: str) -> None:
    result = validate(f"algo {ph(0)}", translated, {0: "-a"})
    assert not result.ok
    assert result.reason == "tradução vazia"


def test_traducao_vazia_tem_precedencia_sobre_ausente() -> None:
    """Vazio é um modo de falha mais informativo que 'placeholder ausente'."""
    assert validate("x", "", {0: "-a"}).reason == "tradução vazia"


# --------------------------------------------------------------------------
# Regra 4: razão de comprimento
# --------------------------------------------------------------------------


def test_traducao_longa_demais() -> None:
    original = "curto"
    translated = "muito " * 20 + "longo"
    result = validate(original, translated, {})
    assert not result.ok
    assert result.reason is not None
    assert result.reason.startswith("razão de comprimento")


def test_traducao_curta_demais() -> None:
    original = "uma frase bem longa que descreve uma opção em detalhe"
    result = validate(original, "opção", {})
    assert not result.ok
    assert result.reason is not None
    assert result.reason.startswith("razão de comprimento")


def test_razao_nos_limites_e_aceita() -> None:
    original = "a" * 100
    assert validate(original, "b" * int(100 * MIN_LENGTH_RATIO), {}).ok
    assert validate(original, "b" * int(100 * MAX_LENGTH_RATIO), {}).ok


def test_razao_logo_fora_dos_limites_e_rejeitada() -> None:
    original = "a" * 100
    assert not validate(original, "b" * 49, {}).ok
    assert not validate(original, "b" * 251, {}).ok


def test_reason_da_razao_traz_o_valor() -> None:
    result = validate("a" * 10, "b" * 31, {})
    assert result.reason is not None
    assert "3.10" in result.reason


def test_original_vazio_nao_divide_por_zero() -> None:
    assert validate("", "alguma coisa", {}).ok


# --------------------------------------------------------------------------
# Regra 5: placeholder malformado
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "translated",
    [
        f"texto {OPEN}0 sem fechar",
        f"texto 0{CLOSE} sem abrir",
        f"texto {OPEN}abc{CLOSE} não numérico",
        f"texto {OPEN}{CLOSE} vazio",
        f"texto {OPEN} solto",
        f"texto {CLOSE} solto",
        f"texto {OPEN}0 {OPEN}1{CLOSE}",
        f"texto {OPEN} 0 {CLOSE} com espaços",
    ],
)
def test_placeholder_malformado(translated: str) -> None:
    result = validate("texto original com espaço", translated, {})
    assert not result.ok
    assert result.reason is not None
    assert result.reason.startswith("placeholder malformado")


def test_malformado_tem_precedencia_sobre_ausente() -> None:
    """Um ⟦ quebrado é diagnóstico melhor que 'sumiu o placeholder 0'."""
    result = validate(f"{ph(0)} original", f"{OPEN}0 traduzido", {0: "-a"})
    assert result.reason is not None
    assert result.reason.startswith("placeholder malformado")


def test_reason_do_malformado_mostra_o_trecho() -> None:
    result = validate("texto original", f"texto {OPEN}abc{CLOSE}", {})
    assert result.reason is not None
    assert f"{OPEN}abc{CLOSE}" in result.reason


def test_chave_solta_junto_de_placeholder_valido() -> None:
    original = f"{ph(0)} texto"
    result = validate(original, f"{ph(0)} texto {CLOSE}", {0: "-a"})
    assert not result.ok
    assert result.reason is not None
    assert result.reason.startswith("placeholder malformado")


# --------------------------------------------------------------------------
# Detalhes da API
# --------------------------------------------------------------------------


def test_validation_result_e_imutavel() -> None:
    result = validate("a", "b", {})
    with pytest.raises(AttributeError):
        result.ok = False  # type: ignore[misc]


def test_resultado_ok_tem_reason_none() -> None:
    result = validate("uma frase", "uma frase", {})
    assert result.ok is True
    assert result.reason is None
