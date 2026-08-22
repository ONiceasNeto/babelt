"""Testes do `babelt doctor`.

O que importa aqui é o código de saída: `doctor` existe para ser rodado por
quem não sabe o que está errado, e a diferença entre "não dá para traduzir" e
"tem algo estranho mas funciona" precisa estar no exit code, não só no texto.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path

import pytest

from babelt.cache import PIPELINE_VERSION, Cache, make_key
from babelt.doctor import Check, diagnose, run


def labels(checks: list[Check]) -> dict[str, Check]:
    return {check.label: check for check in checks}


@pytest.fixture
def instalado(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    fake_model: Callable[..., Path],
) -> Path:
    # Os dois XDG apontam para o tmp: sem isso o diagnóstico enxerga o home
    # de quem roda os testes, e o resultado passa a depender da máquina.
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    return fake_model(tmp_path / "modelo")


class TestDiagnostico:
    def test_tudo_no_lugar(self, instalado: Path) -> None:
        checks = labels(diagnose("9.9.9", instalado))
        assert checks["babelt"].detail == "9.9.9"
        assert checks["versão de pipeline"].detail == str(PIPELINE_VERSION)
        assert checks["modelo"].ok

    def test_modelo_ausente_bloqueia(self, tmp_path: Path) -> None:
        checks = labels(diagnose("9.9.9", tmp_path / "nada"))
        assert not checks["modelo"].ok
        assert checks["modelo"].blocking

    def test_dependencias_de_execucao_aparecem(self, instalado: Path) -> None:
        checks = labels(diagnose("9.9.9", instalado))
        assert checks["ctranslate2"].ok
        assert checks["sentencepiece"].ok

    def test_cache_ausente_nao_e_problema(self, instalado: Path) -> None:
        checks = labels(diagnose("9.9.9", instalado))
        assert checks["cache"].ok

    def test_cache_de_versao_antiga_avisa_sem_bloquear(
        self, instalado: Path, tmp_path: Path
    ) -> None:
        root = tmp_path / "cache" / "babelt"
        cache = Cache(root)
        cache.put(make_key("t", model="m", beam=1), "x")
        meta = json.loads((root / "meta.json").read_text(encoding="utf-8"))
        meta["pipeline_version"] = PIPELINE_VERSION - 1
        (root / "meta.json").write_text(json.dumps(meta), encoding="utf-8")

        checks = labels(diagnose("9.9.9", instalado))
        obsoleto = checks["cache: versão de pipeline"]
        assert not obsoleto.ok
        assert not obsoleto.blocking
        assert "apagadas" in obsoleto.detail

    def test_proveniencia_do_meta_json_do_modelo(self, instalado: Path) -> None:
        (instalado / "meta.json").write_text('{"model_id": "x"}', encoding="utf-8")
        checks = labels(diagnose("9.9.9", instalado))
        assert checks["modelo: proveniência"].ok
        assert "model_id" in checks["modelo: proveniência"].detail

    def test_man_ausente_e_aviso(
        self, instalado: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr("babelt.doctor.shutil.which", lambda _: None)
        checks = labels(diagnose("9.9.9", instalado))
        assert not checks["man"].ok
        assert not checks["man"].blocking


class TestOrfaosDoNomeAntigo:
    """O projeto se chamou `manbr` até a 0.5.0; 227 MB não somem sozinhos."""

    def test_cache_orfao_e_apontado(
        self, instalado: Path, tmp_path: Path
    ) -> None:
        antigo = tmp_path / "cache" / "manbr"
        antigo.mkdir(parents=True)
        (antigo / "meta.json").write_text("{}", encoding="utf-8")
        checks = labels(diagnose("9.9.9", instalado))
        assert "órfão de manbr (cache)" in checks
        assert not checks["órfão de manbr (cache)"].blocking

    def test_modelo_orfao_e_apontado(
        self, instalado: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
        antigo = tmp_path / "data" / "manbr" / "models" / "en-pt"
        antigo.mkdir(parents=True)
        (antigo / "model.bin").write_bytes(b"pesos antigos")
        checks = labels(diagnose("9.9.9", instalado))
        assert "órfão de manbr (modelo)" in checks

    def test_sem_orfaos_nao_aparece_nada(self, instalado: Path) -> None:
        checks = labels(diagnose("9.9.9", instalado))
        assert not [label for label in checks if label.startswith("órfão")]

    def test_orfao_nao_derruba_o_codigo_de_saida(
        self, instalado: Path, tmp_path: Path
    ) -> None:
        (tmp_path / "cache" / "manbr").mkdir(parents=True)
        assert run("9.9.9", instalado) == 0


class TestSaida:
    def test_exit_zero_quando_da_para_traduzir(
        self, instalado: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        assert run("9.9.9", instalado) == 0
        captured = capsys.readouterr()
        assert captured.out == ""  # stdout é só tradução
        assert "babelt" in captured.err

    def test_exit_um_com_modelo_ausente(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        assert run("9.9.9", tmp_path / "nada") == 1
        assert "impedem a tradução" in capsys.readouterr().err

    def test_aviso_sozinho_nao_derruba_o_codigo(
        self, instalado: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr("babelt.doctor.shutil.which", lambda _: None)
        assert run("9.9.9", instalado) == 0


class TestSubcomando:
    def test_doctor_pela_cli(
        self, instalado: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        from babelt.__main__ import main

        assert main(["doctor", "--model-path", str(instalado)]) == 0
        assert "versão de pipeline" in capsys.readouterr().err

    def test_help_of_doctor_e_a_ferramenta_doctor(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """`babelt --help-of doctor` é sobre um binário chamado doctor."""
        from babelt.__main__ import EXIT_NOT_FOUND, main

        monkeypatch.setattr("babelt.__main__.shutil.which", lambda _: None)
        assert main(["--help-of", "doctor"]) == EXIT_NOT_FOUND
