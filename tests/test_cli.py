"""Testes da CLI.

O contrato que mais importa aqui não é a tradução — é o fluxo: texto em
stdout, tudo o mais em stderr, e nenhum caminho de erro deixando stdout vazio.
Isso é testável sem modelo.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from manbr.__main__ import (
    EXIT_ERROR,
    EXIT_INTERRUPTED,
    EXIT_NOT_FOUND,
    EXIT_OK,
    EXIT_USAGE,
    Progress,
    _decode,
    _encode,
    build_parser,
    main,
    output_width,
    rewrap,
    translate_document,
)
from manbr.cache import Cache, make_key
from manbr.model import model_path
from manbr.segment import Segment, SegmentKind
from manbr.translate import TranslationOutcome, Translator

needs_model = pytest.mark.model

PAGE = (
    "NAME\n"
    "       ss - another utility to investigate sockets\n"
    "\n"
    "DESCRIPTION\n"
    "       Display only listening sockets.\n"
)


class FakeTranslator(Translator):
    def __init__(self) -> None:
        super().__init__(Path("/inexistente"))
        self.calls = 0

    def oov_pieces(self, text: str) -> list[str]:
        return []

    def _run_model(self, texts: list[str]) -> list[str]:
        # Prefixo sem colchete de propósito: "[pt]" desbalancearia os
        # delimitadores e a regra estrutural da fase 3.1 rejeitaria tudo.
        self.calls += len(texts)
        return [f"PT {text}" for text in texts]


# --------------------------------------------------------------------------
# Argumentos e códigos de saída
# --------------------------------------------------------------------------


class TestUso:
    def test_sem_argumento_e_sem_stdin_e_erro_de_uso(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        monkeypatch.setattr(sys.stdin, "isatty", lambda: True)
        assert main([]) == EXIT_USAGE
        captured = capsys.readouterr()
        assert captured.out == ""
        assert "entrada padrão" in captured.err

    def test_beam_invalido(self) -> None:
        with pytest.raises(SystemExit) as excinfo:
            main(["--beam", "0"])
        assert excinfo.value.code == EXIT_USAGE

    def test_pagina_inexistente(self, capsys: pytest.CaptureFixture[str]) -> None:
        assert main(["naoexisteessapaginademanual"]) == EXIT_NOT_FOUND
        assert capsys.readouterr().err

    def test_entrada_vazia(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        monkeypatch.setattr(sys.stdin, "isatty", lambda: False)
        monkeypatch.setattr(sys.stdin, "read", lambda: "   \n")
        assert main([]) == EXIT_OK

    def test_version(self) -> None:
        with pytest.raises(SystemExit) as excinfo:
            build_parser().parse_args(["--version"])
        assert excinfo.value.code == 0

    def test_modelo_ausente_degrada_para_o_original(
        self,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
        tmp_path: Path,
    ) -> None:
        """Falha nunca produz stdout vazio."""
        monkeypatch.setattr(sys.stdin, "isatty", lambda: False)
        monkeypatch.setattr(sys.stdin, "read", lambda: PAGE)
        monkeypatch.setattr(sys.stdout, "isatty", lambda: False)
        assert main(["--model-path", str(tmp_path / "vazio")]) == EXIT_ERROR
        captured = capsys.readouterr()
        assert "ss - another utility" in captured.out
        assert "modelo não instalado" in captured.err


# --------------------------------------------------------------------------
# Tradução de documento e cache
# --------------------------------------------------------------------------


class TestTraducaoDeDocumento:
    def test_literais_nao_vao_ao_modelo(self, tmp_path: Path) -> None:
        translator = FakeTranslator()
        text, counters = translate_document(
            PAGE, translator, None, model="m", beam=1
        )
        assert counters["literal"] > 0
        assert "PT " in text

    def test_cabecalhos_traduzidos(self) -> None:
        text, _ = translate_document(PAGE, FakeTranslator(), None, model="m", beam=1)
        assert "NOME" in text and "DESCRIÇÃO" in text

    def test_cache_frio_depois_quente(self, tmp_path: Path) -> None:
        cache = Cache(tmp_path)
        cold = FakeTranslator()
        first, counters_cold = translate_document(
            PAGE, cold, cache, model="m", beam=1
        )
        assert counters_cold["cache_hits"] == 0
        assert cold.calls > 0

        warm = FakeTranslator()
        second, counters_warm = translate_document(
            PAGE, warm, cache, model="m", beam=1
        )
        assert warm.calls == 0  # nada foi ao modelo
        assert counters_warm["cache_hits"] > 0
        assert first == second  # saída idêntica

    def test_no_cache_ignora_disco(self, tmp_path: Path) -> None:
        cache = Cache(tmp_path)
        translate_document(PAGE, FakeTranslator(), cache, model="m", beam=1)
        again = FakeTranslator()
        translate_document(PAGE, again, None, model="m", beam=1)
        assert again.calls > 0

    def test_bump_de_pipeline_invalida_o_documento(self, tmp_path: Path) -> None:
        cache = Cache(tmp_path)
        translate_document(PAGE, FakeTranslator(), cache, model="m", beam=1)
        outro = FakeTranslator()
        translate_document(PAGE, outro, cache, model="m", beam=4)
        assert outro.calls > 0  # beam diferente, chave diferente

    def test_entrada_de_cache_invalida_devolve_original(self, tmp_path: Path) -> None:
        cache = Cache(tmp_path)
        segment_text = "Display only listening sockets."
        cache.put(make_key(segment_text, model="m", beam=1), "{ nao é json valido")
        text, _ = translate_document(PAGE, FakeTranslator(), cache, model="m", beam=1)
        assert segment_text in text


# --------------------------------------------------------------------------
# Interrupção
# --------------------------------------------------------------------------


LONG_PAGE = "DESCRIPTION\n" + "".join(
    f"       Sentence number {index} explains one option.\n\n"
    for index in range(40)
)


class InterruptingTranslator(FakeTranslator):
    """Traduz o primeiro bloco e aborta no segundo, como um Ctrl-C real."""

    def __init__(self) -> None:
        super().__init__()
        self.blocks = 0

    def translate_all(
        self, segments: list[Segment]
    ) -> list[TranslationOutcome]:
        self.blocks += 1
        if self.blocks > 1:
            raise KeyboardInterrupt
        return super().translate_all(segments)


class TestInterrupcao:
    def test_cache_parcial_e_preservado(self, tmp_path: Path) -> None:
        """O que foi traduzido antes do Ctrl-C fica gravado."""
        cache = Cache(tmp_path)
        with pytest.raises(KeyboardInterrupt):
            translate_document(
                LONG_PAGE, InterruptingTranslator(), cache, model="m", beam=1
            )
        assert cache.stats().entries > 0

    def test_segunda_execucao_aproveita_o_parcial(self, tmp_path: Path) -> None:
        cache = Cache(tmp_path)
        with pytest.raises(KeyboardInterrupt):
            translate_document(
                LONG_PAGE, InterruptingTranslator(), cache, model="m", beam=1
            )
        gravadas = cache.stats().entries
        retomada = FakeTranslator()
        _, counters = translate_document(
            LONG_PAGE, retomada, cache, model="m", beam=1
        )
        assert counters["cache_hits"] == gravadas
        assert retomada.calls > 0  # o resto ainda precisou do modelo

    def test_codigo_de_saida_130(
        self,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
        tmp_path: Path,
    ) -> None:
        monkeypatch.setattr(sys.stdin, "isatty", lambda: False)
        monkeypatch.setattr(sys.stdin, "read", lambda: LONG_PAGE)
        monkeypatch.setattr(sys.stdout, "isatty", lambda: False)
        monkeypatch.setattr("manbr.__main__.is_installed", lambda directory: True)
        monkeypatch.setattr(
            "manbr.__main__.Translator",
            lambda directory, beam_size=1: InterruptingTranslator(),
        )
        monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path))
        assert main(["--model-path", str(tmp_path)]) == EXIT_INTERRUPTED
        captured = capsys.readouterr()
        assert "interrompido" in captured.err
        assert captured.out == ""  # o usuário mandou parar; não despeja a página


# --------------------------------------------------------------------------
# Requebra
# --------------------------------------------------------------------------


class TestRequebra:
    def test_prosa_longa_cabe_na_largura(self) -> None:
        texto = " ".join(["palavra"] * 60)
        [saida] = rewrap([Segment(kind=SegmentKind.PROSE, text=texto, indent=7)], 80)
        assert all(len(linha) + 7 <= 80 for linha in saida.text.split("\n"))
        assert saida.text.split() == texto.split()  # nada perdido

    def test_indentacao_desconta_da_largura(self) -> None:
        texto = " ".join(["palavra"] * 60)
        raso = rewrap([Segment(kind=SegmentKind.PROSE, text=texto, indent=0)], 80)[0]
        fundo = rewrap([Segment(kind=SegmentKind.PROSE, text=texto, indent=14)], 80)[0]
        assert len(fundo.text.split("\n")) > len(raso.text.split("\n"))

    def test_literal_intocado(self) -> None:
        tabela = "  -a    " + "x" * 200 + "\n  -b    outro"
        item = Segment(kind=SegmentKind.LITERAL, text=tabela, indent=3)
        assert rewrap([item], 80)[0].text == tabela

    def test_token_longo_nao_e_partido(self) -> None:
        flag = "--exclude-from=/um/caminho/absurdamente/longo/que/nao/cabe/em/oitenta"
        item = Segment(kind=SegmentKind.PROSE, text=f"Use {flag} aqui.", indent=7)
        assert flag in rewrap([item], 80)[0].text

    def test_hifen_nao_vira_quebra(self) -> None:
        texto = "Use a opção pré-existente " + " ".join(["palavra"] * 40)
        saida = rewrap([Segment(kind=SegmentKind.PROSE, text=texto, indent=0)], 80)[0]
        assert "pré-existente" in saida.text

    def test_vazio_passa_direto(self) -> None:
        item = Segment(kind=SegmentKind.PROSE, text="", indent=0)
        assert rewrap([item], 80)[0].text == ""

    def test_manwidth_manda(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("MANWIDTH", "100")
        assert output_width() == 100

    def test_manwidth_absurdo_e_ignorado(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("MANWIDTH", "3")
        assert output_width() == 80
        monkeypatch.setenv("MANWIDTH", "vinte")
        assert output_width() == 80

    def test_documento_inteiro_respeita_a_largura(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("MANWIDTH", "80")
        longa = "DESCRIPTION\n       " + " ".join(["sockets"] * 80) + "\n"
        texto, _ = translate_document(
            longa, FakeTranslator(), None, model="m", beam=1
        )
        assert max(len(linha) for linha in texto.split("\n")) <= 80


class TestSerializacao:
    def test_ida_e_volta(self) -> None:
        outcome = TranslationOutcome("texto ⟦0⟧", True, None)
        assert _decode(_encode(outcome), "fallback") == outcome

    def test_com_motivo(self) -> None:
        outcome = TranslationOutcome("t", False, "oov")
        assert _decode(_encode(outcome), "fallback").reason == "oov"

    def test_invalido_cai_no_fallback(self) -> None:
        result = _decode("nao é json", "original")
        assert result.text == "original"
        assert not result.translated


class TestProgresso:
    def test_silencioso_fora_do_terminal(self, tmp_path: Path) -> None:
        stream = (tmp_path / "err.txt").open("w")
        progress = Progress(10, stream)
        progress.advance(5)
        progress.close()
        stream.close()
        assert (tmp_path / "err.txt").read_text() == ""

    def test_total_zero_nao_quebra(self, tmp_path: Path) -> None:
        stream = (tmp_path / "err.txt").open("w")
        Progress(0, stream).close()
        stream.close()


# --------------------------------------------------------------------------
# Ponta a ponta, com o modelo
# --------------------------------------------------------------------------


@needs_model
class TestPontaAPonta:
    def test_stdin_produz_portugues(self, tmp_path: Path) -> None:
        result = subprocess.run(
            [sys.executable, "-m", "manbr", "--no-cache"],
            input=PAGE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env={**_env(), "XDG_CACHE_HOME": str(tmp_path)},
            check=False,
        )
        assert result.returncode == EXIT_OK
        assert result.stdout.strip()
        assert "NOME" in result.stdout
        assert "sockets" in result.stdout

    def test_stdout_e_stderr_nao_se_misturam(self, tmp_path: Path) -> None:
        result = subprocess.run(
            [sys.executable, "-m", "manbr", "--stats"],
            input=PAGE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env={**_env(), "XDG_CACHE_HOME": str(tmp_path)},
            check=False,
        )
        assert "manbr:" not in result.stdout
        assert "segmentos:" in result.stderr

    def test_cache_frio_e_quente_dao_a_mesma_saida(self, tmp_path: Path) -> None:
        env = {**_env(), "XDG_CACHE_HOME": str(tmp_path)}
        first = subprocess.run(
            [sys.executable, "-m", "manbr"],
            input=PAGE, stdout=subprocess.PIPE, text=True, env=env, check=False,
        )
        second = subprocess.run(
            [sys.executable, "-m", "manbr"],
            input=PAGE, stdout=subprocess.PIPE, text=True, env=env, check=False,
        )
        assert first.stdout == second.stdout
        assert (tmp_path / "manbr" / "meta.json").is_file()


def _env() -> dict[str, str]:
    import os

    return {
        key: value
        for key, value in os.environ.items()
        if key in {"PATH", "HOME", "LANG", "LC_ALL", "XDG_DATA_HOME"}
    }
