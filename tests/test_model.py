"""Testes de model.py.

Nada aqui baixa nada. O caminho de download de verdade é marcado `model` e
mora em test_translate.py; estes testes cobrem a lógica de caminho, de
verificação e de atomicidade, que é onde os erros doem.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from manbr.model import (
    MODEL_ID,
    ModelError,
    download,
    is_installed,
    model_path,
)


def fake_model(directory: Path, *, vocabulary: str = "shared_vocabulary.json") -> None:
    """Cria um diretório com a cara de um modelo convertido."""
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "model.bin").write_bytes(b"pesos")
    (directory / "source.spm").write_bytes(b"spm")
    (directory / "target.spm").write_bytes(b"spm")
    (directory / vocabulary).write_text("[]", encoding="utf-8")


class TestCaminho:
    def test_respeita_xdg_data_home(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("XDG_DATA_HOME", "/tmp/xdg-teste")
        assert model_path() == Path("/tmp/xdg-teste/manbr/models/en-pt")

    def test_padrao_sem_xdg(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("XDG_DATA_HOME", raising=False)
        assert model_path() == Path.home() / ".local/share/manbr/models/en-pt"

    def test_xdg_vazio_cai_no_padrao(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("XDG_DATA_HOME", "")
        assert model_path() == Path.home() / ".local/share/manbr/models/en-pt"


class TestVerificacao:
    def test_modelo_completo(self, tmp_path: Path) -> None:
        fake_model(tmp_path)
        assert is_installed(tmp_path)

    def test_vocabulario_em_txt_tambem_serve(self, tmp_path: Path) -> None:
        fake_model(tmp_path, vocabulary="shared_vocabulary.txt")
        assert is_installed(tmp_path)

    def test_diretorio_inexistente(self, tmp_path: Path) -> None:
        assert not is_installed(tmp_path / "nada")

    @pytest.mark.parametrize(
        "missing", ["model.bin", "source.spm", "target.spm", "shared_vocabulary.json"]
    )
    def test_arquivo_faltando(self, tmp_path: Path, missing: str) -> None:
        fake_model(tmp_path)
        (tmp_path / missing).unlink()
        assert not is_installed(tmp_path)

    def test_model_bin_vazio_nao_conta(self, tmp_path: Path) -> None:
        """O caso que a atomicidade existe para evitar."""
        fake_model(tmp_path)
        (tmp_path / "model.bin").write_bytes(b"")
        assert not is_installed(tmp_path)


class TestDownload:
    def test_no_op_se_ja_instalado(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        destination = tmp_path / "manbr" / "models" / "en-pt"
        fake_model(destination)
        monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))

        def explode(*args: object, **kwargs: object) -> None:
            raise AssertionError("não deveria converter nada")

        monkeypatch.setattr("subprocess.run", explode)
        download()
        assert "já instalado" in capsys.readouterr().err

    def test_progresso_vai_para_stderr(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """stdout é a saída traduzida; não pode levar recado de progresso."""
        fake_model(tmp_path / "manbr" / "models" / "en-pt")
        monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
        download()
        captured = capsys.readouterr()
        assert captured.out == ""
        assert captured.err

    def test_silencioso_quando_pedido(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        fake_model(tmp_path / "manbr" / "models" / "en-pt")
        monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
        download(progress=False)
        assert capsys.readouterr().err == ""

    def test_conversao_falha_nao_deixa_destino(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))

        class Failed:
            returncode = 1
            stdout = "boom"

        monkeypatch.setattr("subprocess.run", lambda *a, **k: Failed())
        with pytest.raises(ModelError, match="falhou"):
            download(progress=False)
        assert not model_path().exists()

    def test_conversao_incompleta_e_rejeitada(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Converteu, mas sem model.bin: não pode virar instalação."""
        monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))

        class Ok:
            returncode = 0
            stdout = ""

        def convert(command: list[str], **kwargs: object) -> Ok:
            output = Path(command[command.index("--output_dir") + 1])
            output.mkdir(parents=True, exist_ok=True)
            (output / "source.spm").write_bytes(b"spm")
            return Ok()

        monkeypatch.setattr("subprocess.run", convert)
        with pytest.raises(ModelError, match="model.bin"):
            download(progress=False)
        assert not model_path().exists()

    def test_nao_deixa_temporario_para_tras(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))

        class Failed:
            returncode = 1
            stdout = "boom"

        monkeypatch.setattr("subprocess.run", lambda *a, **k: Failed())
        with pytest.raises(ModelError):
            download(progress=False)
        leftovers = list(model_path().parent.glob(".manbr-download-*"))
        assert not leftovers

    def test_instalacao_bem_sucedida_e_movida_inteira(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))

        class Ok:
            returncode = 0
            stdout = ""

        def convert(command: list[str], **kwargs: object) -> Ok:
            fake_model(Path(command[command.index("--output_dir") + 1]))
            return Ok()

        monkeypatch.setattr("subprocess.run", convert)
        download(progress=False)
        assert is_installed()
        assert (model_path() / "model.bin").read_bytes() == b"pesos"

    def test_comando_usa_o_modelo_e_a_quantizacao_certos(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
        seen: list[list[str]] = []

        class Ok:
            returncode = 0
            stdout = ""

        def convert(command: list[str], **kwargs: object) -> Ok:
            seen.append(command)
            fake_model(Path(command[command.index("--output_dir") + 1]))
            return Ok()

        monkeypatch.setattr("subprocess.run", convert)
        download(progress=False)
        (command,) = seen
        assert MODEL_ID in command
        assert command[command.index("--quantization") + 1] == "int8"
        assert "source.spm" in command and "target.spm" in command
