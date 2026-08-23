"""Testes da CLI.

O contrato que mais importa aqui não é a tradução — é o fluxo: texto em
stdout, tudo o mais em stderr, e nenhum caminho de erro deixando stdout vazio.
Isso é testável sem modelo.
"""

from __future__ import annotations

import io
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path

import pytest

from babelt.__main__ import (
    REASON_PREFIX,
    EXIT_ERROR,
    EXIT_INTERRUPTED,
    EXIT_NOT_FOUND,
    EXIT_OK,
    EXIT_USAGE,
    Progress,
    _decode,
    _encode,
    HELP_FLAGS,
    build_parser,
    choose_pager,
    main,
    output_width,
    emit,
    reason_family,
    report,
    read_help,
    read_source,
    rewrap,
    translate_document,
)
from babelt.cache import Cache, make_key
from babelt.model import ModelError, model_path
from babelt.segment import Segment, SegmentKind
from babelt.translate import TranslationOutcome, Translator

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


# Prosa de verdade, e não `Sentence number 3 explains one option.`: desde a
# fase 6 o documento precisa ter palavras funcionais suficientes para passar
# pela guarda de prosa, e a frase sintética antiga não tinha nenhuma.
LONG_PAGE = "DESCRIPTION\n" + "".join(
    f"       This is the option number {index}, and it tells the program what "
    f"to do with the file when there is no other one.\n\n"
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
        monkeypatch.setattr("babelt.__main__.is_installed", lambda directory: True)
        monkeypatch.setattr(
            "babelt.__main__.Translator",
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
        # Prosa de verdade: `"sockets" * 80` não tem palavra funcional nenhuma
        # e desde a fase 6 seria barrado pela guarda de prosa antes de chegar
        # à requebra.
        longa = "DESCRIPTION\n       " + " ".join(
            ["it shows the sockets that are open on the host"] * 12
        ) + "\n"
        texto, _ = translate_document(
            longa, FakeTranslator(), None, model="m", beam=1
        )
        assert max(len(linha) for linha in texto.split("\n")) <= 80


# --------------------------------------------------------------------------
# Fase 5: modo --help
# --------------------------------------------------------------------------


class FakeRun:
    """Substitui subprocess.run: devolve saída por flag pedido."""

    def __init__(self, saidas: dict[str, str]) -> None:
        self.saidas = saidas
        self.chamadas: list[list[str]] = []

    def __call__(self, argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        self.chamadas.append(argv)
        saida = self.saidas.get(argv[-1], "")
        return subprocess.CompletedProcess(argv, 1 if not saida else 0, saida, "")


class TestLeituraDeAjuda:
    def test_usa_help_quando_responde(self, monkeypatch: pytest.MonkeyPatch) -> None:
        run = FakeRun({"--help": "Usage: foo [flags]\n"})
        monkeypatch.setattr("babelt.__main__.shutil.which", lambda _: "/usr/bin/foo")
        monkeypatch.setattr("babelt.__main__.subprocess.run", run)
        assert read_help("foo") == "Usage: foo [flags]\n"
        assert run.chamadas == [["foo", "--help"]]

    def test_cai_para_h_e_depois_usage(self, monkeypatch: pytest.MonkeyPatch) -> None:
        run = FakeRun({"--usage": "uso: foo\n"})
        monkeypatch.setattr("babelt.__main__.shutil.which", lambda _: "/usr/bin/foo")
        monkeypatch.setattr("babelt.__main__.subprocess.run", run)
        assert read_help("foo") == "uso: foo\n"
        assert [c[-1] for c in run.chamadas] == list(HELP_FLAGS)

    def test_nunca_passa_argumento_alem_do_flag(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Executar o binário é a superfície de risco; ela fica no mínimo."""
        run = FakeRun({"--help": "ajuda\n"})
        monkeypatch.setattr("babelt.__main__.shutil.which", lambda _: "/usr/bin/foo")
        monkeypatch.setattr("babelt.__main__.subprocess.run", run)
        read_help("foo")
        assert all(len(argv) == 2 for argv in run.chamadas)

    def test_comando_ausente(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr("babelt.__main__.shutil.which", lambda _: None)
        with pytest.raises(FileNotFoundError):
            read_help("naoexiste")

    def test_nenhum_flag_responde(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr("babelt.__main__.shutil.which", lambda _: "/usr/bin/foo")
        monkeypatch.setattr("babelt.__main__.subprocess.run", FakeRun({}))
        with pytest.raises(LookupError):
            read_help("foo")


class TestEscolhaDaFonte:
    def test_padrao_e_man(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr("babelt.__main__.read_manpage", lambda cmd: f"man de {cmd}")
        assert read_source("ss", help_of=False, auto=False) == "man de ss"

    def test_help_of_nao_chama_man(self, monkeypatch: pytest.MonkeyPatch) -> None:
        def nunca(cmd: str) -> str:
            raise AssertionError("man não devia ser chamado")

        monkeypatch.setattr("babelt.__main__.read_manpage", nunca)
        monkeypatch.setattr("babelt.__main__.read_help", lambda cmd: f"ajuda de {cmd}")
        assert read_source("katana", help_of=True, auto=False) == "ajuda de katana"

    def test_auto_prefere_man(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr("babelt.__main__.read_manpage", lambda cmd: "a man page")
        monkeypatch.setattr("babelt.__main__.read_help", lambda cmd: "a ajuda")
        assert read_source("ss", help_of=False, auto=True) == "a man page"

    def test_auto_cai_para_help_sem_pagina(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        def sem_pagina(cmd: str) -> str:
            raise LookupError("No manual entry for katana")

        monkeypatch.setattr("babelt.__main__.read_manpage", sem_pagina)
        monkeypatch.setattr("babelt.__main__.read_help", lambda cmd: "a ajuda")
        assert read_source("katana", help_of=False, auto=True) == "a ajuda"
        assert "tentando --help" in capsys.readouterr().err

    def test_auto_nao_esconde_outro_erro_do_man(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Seção inválida é erro, e trocar de fonte esconderia isso."""

        def outro_erro(cmd: str) -> str:
            raise LookupError("man: invalid section")

        monkeypatch.setattr("babelt.__main__.read_manpage", outro_erro)
        monkeypatch.setattr("babelt.__main__.read_help", lambda cmd: "a ajuda")
        with pytest.raises(LookupError, match="invalid section"):
            read_source("foo", help_of=False, auto=True)


class TestArgumentosDoModoHelp:
    def test_help_of_sem_comando_e_uso_invalido(self) -> None:
        with pytest.raises(SystemExit) as erro:
            main(["--help-of"])
        assert erro.value.code == EXIT_USAGE

    def test_help_of_e_auto_sao_exclusivos(self) -> None:
        with pytest.raises(SystemExit) as erro:
            main(["--help-of", "--auto", "foo"])
        assert erro.value.code == EXIT_USAGE

    def test_ferramenta_ausente_da_127(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        monkeypatch.setattr("babelt.__main__.shutil.which", lambda _: None)
        monkeypatch.setattr(sys.stdout, "isatty", lambda: False)
        assert main(["--help-of", "naoexiste"]) == EXIT_NOT_FOUND
        assert "não está instalado" in capsys.readouterr().err


class TestRequebraDeColuna:
    def test_celula_quebra_dentro_da_coluna(self) -> None:
        item = Segment(
            kind=SegmentKind.COLUMNS,
            text=" ".join(["palavra"] * 30),
            indent=0,
            left="   -u, -list string[]",
            column=26,
        )
        [saida] = rewrap([item], 80)
        linhas = saida.text.split("\n")
        assert all(len(linha) + 26 <= 80 for linha in linhas)
        assert len(linhas) > 1

    def test_esquerda_e_coluna_sobrevivem_a_requebra(self) -> None:
        item = Segment(
            kind=SegmentKind.COLUMNS,
            text="curta",
            indent=0,
            left="  -a",
            column=8,
        )
        [saida] = rewrap([item], 80)
        assert saida.left == "  -a"
        assert saida.column == 8


# --------------------------------------------------------------------------
# Fase 6: pager
# --------------------------------------------------------------------------


class TestEscolhaDePager:
    def test_padrao_nao_limpa_a_tela_e_sai_sozinho(self) -> None:
        assert choose_pager() == "less -RFX"

    def test_pager_do_ambiente(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("PAGER", "more")
        assert choose_pager() == "more"

    def test_babelt_pager_tem_precedencia(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("PAGER", "more")
        monkeypatch.setenv("BABELT_PAGER", "less -R")
        assert choose_pager() == "less -R"

    def test_variavel_vazia_nao_conta(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("BABELT_PAGER", "  ")
        monkeypatch.setenv("PAGER", "more")
        assert choose_pager() == "more"


class TestQuandoPaginar:
    def _pager_espiao(self, monkeypatch: pytest.MonkeyPatch) -> list[str]:
        chamado: list[str] = []
        monkeypatch.setattr(sys.stdout, "isatty", lambda: True)
        monkeypatch.setattr("babelt.__main__.terminal_height", lambda: 24)
        monkeypatch.setattr("babelt.__main__.subprocess.Popen", _espiao(chamado))
        return chamado

    def test_saida_curta_nao_pagina(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        chamado = self._pager_espiao(monkeypatch)
        emit("uma\nduas\ntrês\n")
        assert chamado == []
        assert "duas" in capsys.readouterr().out

    def test_saida_longa_pagina(self, monkeypatch: pytest.MonkeyPatch) -> None:
        chamado = self._pager_espiao(monkeypatch)
        emit("linha\n" * 100)
        assert chamado == ["less -RFX"]

    def test_no_pager_desliga(self, monkeypatch: pytest.MonkeyPatch) -> None:
        chamado = self._pager_espiao(monkeypatch)
        emit("linha\n" * 100, paginate=False)
        assert chamado == []

    def test_fora_do_terminal_nunca_pagina(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        chamado: list[str] = []
        monkeypatch.setattr(sys.stdout, "isatty", lambda: False)
        monkeypatch.setattr("babelt.__main__.subprocess.Popen", _espiao(chamado))
        emit("linha\n" * 100)
        assert chamado == []


def _espiao(chamado: list[str]) -> Callable[..., "_PagerFalso"]:
    def abrir(cmd: str, **kwargs: object) -> "_PagerFalso":
        chamado.append(cmd)
        return _PagerFalso()

    return abrir


class _PagerFalso:
    def __init__(self) -> None:
        self.stdin = io.StringIO()

    def wait(self) -> int:
        return 0


# --------------------------------------------------------------------------
# Fase 7: falha ao obter o modelo
# --------------------------------------------------------------------------


class TestFalhaAoBaixar:
    def test_erro_de_modelo_nao_vira_traceback(
        self,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
        tmp_path: Path,
    ) -> None:
        """Build sem URL publicada, rede fora, hash errado: tudo degrada."""
        monkeypatch.setattr(sys.stdin, "isatty", lambda: True)
        monkeypatch.setattr(sys.stderr, "isatty", lambda: True)
        monkeypatch.setattr(sys.stdout, "isatty", lambda: False)
        monkeypatch.setattr("builtins.input", lambda _: "s")
        monkeypatch.setattr("babelt.__main__.is_installed", lambda directory: False)

        def falha(progress: bool = True) -> None:
            raise ModelError("esta build não tem URL de modelo publicada")

        monkeypatch.setattr("babelt.__main__.download", falha)
        # Com stdin num terminal — que é o que faz `ensure_model` perguntar —
        # a entrada precisa vir de um comando, não do pipe.
        monkeypatch.setattr("babelt.__main__.read_manpage", lambda cmd: PAGE)
        assert main(["ss", "--model-path", str(tmp_path)]) == EXIT_ERROR
        captured = capsys.readouterr()
        assert "URL de modelo publicada" in captured.err
        assert "ss - another utility" in captured.out  # degradou para o original


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
            [sys.executable, "-m", "babelt", "--no-cache"],
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
            [sys.executable, "-m", "babelt", "--stats"],
            input=PAGE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env={**_env(), "XDG_CACHE_HOME": str(tmp_path)},
            check=False,
        )
        assert "babelt:" not in result.stdout
        assert "segmentos:" in result.stderr

    def test_cache_frio_e_quente_dao_a_mesma_saida(self, tmp_path: Path) -> None:
        env = {**_env(), "XDG_CACHE_HOME": str(tmp_path)}
        first = subprocess.run(
            [sys.executable, "-m", "babelt"],
            input=PAGE, stdout=subprocess.PIPE, text=True, env=env, check=False,
        )
        second = subprocess.run(
            [sys.executable, "-m", "babelt"],
            input=PAGE, stdout=subprocess.PIPE, text=True, env=env, check=False,
        )
        assert first.stdout == second.stdout
        assert (tmp_path / "babelt" / "meta.json").is_file()


def _env() -> dict[str, str]:
    import os

    return {
        key: value
        for key, value in os.environ.items()
        if key in {"PATH", "HOME", "LANG", "LC_ALL", "XDG_DATA_HOME"}
    }


# --------------------------------------------------------------------------
# Fase 6: guarda de prosa
# --------------------------------------------------------------------------


LISTAGEM = "\n".join(
    [
        "accountsservice",
        "aclocal",
        "alsa",
        "applications",
        "backgrounds",
        "bash-completion",
        "binfmts",
        "ca-certificates",
        "dbus-1",
        "dict",
        "doc",
        "fonts",
        "Labs",
        "nuclei-templates",
        "sounds",
        "themes",
        "xml",
        "zoneinfo",
        "icons",
        "locale",
        "man",
        "pixmaps",
    ]
)


class TestGuardaDeProsa:
    def test_listagem_de_arquivos_passa_intacta(self, tmp_path: Path) -> None:
        """O caso que abriu a fase: `ls | babelt` traduzia `Labs`."""
        translator = FakeTranslator()
        texto, counters = translate_document(
            LISTAGEM, translator, None, model="m", beam=1
        )
        assert translator.calls == 0  # nenhuma inferência gasta
        assert counters["not_prose"] > 0
        assert "Labs" in texto
        assert "nuclei-templates" in texto

    def test_prosa_continua_passando(self) -> None:
        translator = FakeTranslator()
        _, counters = translate_document(
            LONG_PAGE, translator, None, model="m", beam=1
        )
        assert not counters.get("not_prose")
        assert translator.calls > 0

    def test_aviso_em_stderr(self, capsys: pytest.CaptureFixture[str]) -> None:
        translate_document(LISTAGEM, FakeTranslator(), None, model="m", beam=1)
        assert "não parece prosa" in capsys.readouterr().err

    def test_documento_curto_nao_e_julgado(self) -> None:
        """Sem amostra não há julgamento: errar para o lado de traduzir."""
        translator = FakeTranslator()
        _, counters = translate_document(
            "NAME\n       ss - a tool\n", translator, None, model="m", beam=1
        )
        assert not counters.get("not_prose")

    def test_saida_e_byte_a_byte_a_entrada(self) -> None:
        """Intacto quer dizer intacto: sem normalizar e sem requebrar.

        Passar pelo pipeline colapsaria o espaço de alinhamento de `ps aux` e
        juntaria as linhas de um `ls` num parágrafo. O documento não é prosa,
        e o pipeline inteiro é para prosa.
        """
        tabela = (
            "USER         PID %CPU %MEM    VSZ   RSS TTY      STAT START\n"
            "root           1  0.0  0.2  22836 13832 ?        Ss   Aug18\n"
            "root           2  0.0  0.0      0     0 ?        S    Aug18\n"
            "root           3  0.0  0.0      0     0 ?        S    Aug18\n"
            "avahi        712  0.0  0.0   8100  4224 ?        Ss   Aug18\n"
        )
        texto, counters = translate_document(
            tabela, FakeTranslator(), None, model="m", beam=1
        )
        assert counters["not_prose"] > 0
        assert texto == tabela

    def test_listagem_de_dez_linhas_e_barrada(self) -> None:
        """`ls | head` já tem amostra suficiente para ser julgado."""
        listagem = "\n".join(
            [
                "accountsservice", "aclocal", "alsa", "applications",
                "backgrounds", "bash-completion", "binfmts", "ca-certificates",
                "dbus-1", "dict", "doc", "fonts",
            ]
        )
        _, counters = translate_document(
            listagem, FakeTranslator(), None, model="m", beam=1
        )
        assert counters["not_prose"] > 0


# --------------------------------------------------------------------------
# Fase 9: taxa de rejeição por motivo
# --------------------------------------------------------------------------


class TestMotivoDeRejeicao:
    """`--stats` reporta *por que* um segmento ficou em inglês, não só quantos.

    A contagem por motivo só é útil se toda rejeição real cair numa família
    conhecida. Uma família "outro" que engorda é um relatório que informa cada
    vez menos, e o jeito de impedir isso é fixar aqui os motivos que
    `validate.py` sabe emitir.
    """

    def test_reason_family_agrupa_o_detalhe(self) -> None:
        """O detalhe do caso varia; a família não."""
        assert reason_family("placeholder 3 ausente") == "placeholder ausente"
        assert reason_family("placeholder 7 ausente") == "placeholder ausente"

    @pytest.mark.parametrize(
        "reason",
        [
            "tradução vazia",
            "placeholder malformado: '\\x00 3'",
            "placeholder 2 inesperado",
            "placeholder 3 ausente",
            "placeholder 1 duplicado (2 ocorrências)",
            "razão de comprimento 0.31 fora de [0.5, 2.0]",
            "token desconhecido na saída: '<unk>'",
            "contagem de sentenças mudou: 3 -> 2",
            "sentença repetida 2x: 'do not list implied entries'",
            "delimitador '[': 2 -> 1",
            "oov",
            "não processado",
        ],
    )
    def test_nenhum_motivo_conhecido_cai_em_outro(self, reason: str) -> None:
        assert reason_family(reason) != "outro"

    def test_motivo_de_frase_carrega_a_causa(self) -> None:
        """A segunda tentativa é frase a frase e resumia o motivo em número.

        `2 de 3 sentenças rejeitadas` diz quantas e não diz por quê, e era
        tudo o que chegava ao relatório — o que tornava a medição por motivo
        impossível. A causa da primeira frase rejeitada viaja junto agora.
        """
        assert reason_family("1 de 1 sentenças rejeitadas: placeholder 3 ausente") == (
            "placeholder ausente"
        )

    def test_sem_motivo_registrado_tem_familia_propria(self) -> None:
        assert reason_family(None) == "sem motivo registrado"

    def test_report_lista_os_motivos(self, capsys: pytest.CaptureFixture[str]) -> None:
        counters = {
            "cache_hits": 0,
            "translated": 8,
            "english": 2,
            "literal": 0,
            f"{REASON_PREFIX}placeholder ausente": 2,
        }
        report(counters, None)
        err = capsys.readouterr().err
        assert "rejeitados por motivo:" in err
        assert "placeholder ausente" in err

    def test_report_cala_quando_nada_foi_rejeitado(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        counters = {"cache_hits": 0, "translated": 10, "english": 0, "literal": 0}
        report(counters, None)
        assert "rejeitados por motivo:" not in capsys.readouterr().err
