"""Testes de model.py.

Nada aqui baixa nada. O caminho de download de verdade é marcado `model` e
mora em test_translate.py; estes testes cobrem a lógica de caminho, de
verificação e de atomicidade, que é onde os erros doem.
"""

from __future__ import annotations

import hashlib
import io
import os
import tarfile
import urllib.error
import urllib.request
from pathlib import Path

import pytest

import babelt.model
from babelt.model import (
    ModelError,
    download,
    is_installed,
    model_path,
    verify_archive,
)


def fake_model(directory: Path, *, vocabulary: str = "shared_vocabulary.json") -> None:
    """Cria um diretório com a cara de um modelo convertido."""
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "model.bin").write_bytes(b"pesos")
    (directory / "source.spm").write_bytes(b"spm")
    (directory / "target.spm").write_bytes(b"spm")
    (directory / vocabulary).write_text("[]", encoding="utf-8")


def make_archive(path: Path, *, complete: bool = True) -> Path:
    """Empacota um modelo de mentira do jeito que o artefato real é montado."""
    staging = path.parent / f"{path.stem}-conteudo"
    modelo = staging / "en-pt"
    modelo.mkdir(parents=True, exist_ok=True)
    if complete:
        fake_model(modelo)
    else:
        (modelo / "source.spm").write_bytes(b"spm")
    with tarfile.open(path, "w:gz") as tar:
        tar.add(modelo, arcname="en-pt")
    return path


def serve(
    monkeypatch: pytest.MonkeyPatch, archive: Path, *, sha256: str | None = None
) -> None:
    """Faz `download` baixar `archive` em vez de ir à rede."""
    payload = archive.read_bytes()
    monkeypatch.setattr(babelt.model, "MODEL_URL", "https://exemplo/modelo.tar.gz")
    monkeypatch.setattr(
        babelt.model,
        "MODEL_SHA256",
        sha256 if sha256 is not None else hashlib.sha256(payload).hexdigest(),
    )

    class Response(io.BytesIO):
        headers = {"Content-Length": str(len(payload))}

        def __enter__(self) -> "Response":
            return self

        def __exit__(self, *args: object) -> None:
            self.close()

    monkeypatch.setattr(urllib.request, "urlopen", lambda url: Response(payload))


class TestCaminho:
    def test_respeita_xdg_data_home(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("XDG_DATA_HOME", "/tmp/xdg-teste")
        assert model_path() == Path("/tmp/xdg-teste/babelt/models/en-pt")

    def test_padrao_sem_xdg(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("XDG_DATA_HOME", raising=False)
        assert model_path() == Path.home() / ".local/share/babelt/models/en-pt"

    def test_xdg_vazio_cai_no_padrao(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("XDG_DATA_HOME", "")
        assert model_path() == Path.home() / ".local/share/babelt/models/en-pt"


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
        destination = tmp_path / "babelt" / "models" / "en-pt"
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
        fake_model(tmp_path / "babelt" / "models" / "en-pt")
        monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
        download()
        captured = capsys.readouterr()
        assert captured.out == ""
        assert captured.err

    def test_silencioso_quando_pedido(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        fake_model(tmp_path / "babelt" / "models" / "en-pt")
        monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
        download(progress=False)
        assert capsys.readouterr().err == ""

    @pytest.mark.parametrize("constante", ["MODEL_URL", "MODEL_SHA256"])
    def test_sem_url_publicada_falha_com_instrucao(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, constante: str
    ) -> None:
        """Build sem artefato publicado não sai tentando baixar do nada.

        O que se testa é a *detecção* do placeholder, não o valor que as
        constantes têm hoje: uma vez publicado o artefato, elas ficam
        preenchidas e o teste continuaria valendo. Daí o monkeypatch em
        cima do módulo — que só funciona porque ``download`` lê as duas
        constantes na hora da chamada.
        """
        monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
        monkeypatch.setattr(babelt.model, constante, babelt.model._PLACEHOLDER)

        def nao_va_a_rede(url: str) -> None:
            raise AssertionError(f"não deveria tentar baixar nada ({url})")

        monkeypatch.setattr(urllib.request, "urlopen", nao_va_a_rede)

        with pytest.raises(ModelError, match="build-model.sh"):
            download(progress=False)
        assert not model_path().exists()

    def test_download_bem_sucedido_e_movido_inteiro(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
        archive = make_archive(tmp_path / "artefato.tar.gz")
        serve(monkeypatch, archive)
        download(progress=False)
        assert is_installed()
        assert (model_path() / "model.bin").read_bytes() == b"pesos"

    def test_hash_divergente_apaga_e_falha(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """O artefato errado não é aberto, e não fica no disco."""
        monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
        archive = make_archive(tmp_path / "artefato.tar.gz")
        serve(monkeypatch, archive, sha256="0" * 64)
        with pytest.raises(ModelError, match="SHA-256"):
            download(progress=False)
        assert not model_path().exists()
        assert not list(model_path().parent.glob(".babelt-download-*"))

    def test_artefato_incompleto_e_rejeitado(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Baixou e o hash bateu, mas falta model.bin: não vira instalação."""
        monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
        archive = make_archive(tmp_path / "artefato.tar.gz", complete=False)
        serve(monkeypatch, archive)
        with pytest.raises(ModelError, match="modelo utilizável"):
            download(progress=False)
        assert not model_path().exists()

    def test_falha_de_rede_nao_deixa_temporario(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
        monkeypatch.setattr(babelt.model, "MODEL_URL", "https://exemplo/modelo.tar.gz")
        monkeypatch.setattr(babelt.model, "MODEL_SHA256", "0" * 64)

        def boom(url: str) -> object:
            raise urllib.error.URLError("sem rede")

        monkeypatch.setattr(urllib.request, "urlopen", boom)
        with pytest.raises(ModelError, match="falha ao baixar"):
            download(progress=False)
        assert not list(model_path().parent.glob(".babelt-download-*"))

    def test_outro_processo_chegou_primeiro(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """O trabalho do outro vale tanto quanto o nosso; não sobrescreve."""
        monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
        archive = make_archive(tmp_path / "artefato.tar.gz")
        serve(monkeypatch, archive)

        original = babelt.model._extract

        def extract_then_race(path: Path, into: Path) -> Path:
            result = original(path, into)
            fake_model(model_path())
            (model_path() / "model.bin").write_bytes(b"do outro")
            return result

        monkeypatch.setattr(babelt.model, "_extract", extract_then_race)
        download(progress=False)
        assert (model_path() / "model.bin").read_bytes() == b"do outro"


class TestVerificacaoDeArquivo:
    def test_hash_correto_passa(self, tmp_path: Path) -> None:
        alvo = tmp_path / "a.bin"
        alvo.write_bytes(b"conteudo")
        verify_archive(alvo, hashlib.sha256(b"conteudo").hexdigest())

    def test_maiuscula_no_hash_esperado_tambem_serve(self, tmp_path: Path) -> None:
        alvo = tmp_path / "a.bin"
        alvo.write_bytes(b"conteudo")
        verify_archive(alvo, hashlib.sha256(b"conteudo").hexdigest().upper())

    def test_hash_errado_apaga_o_arquivo(self, tmp_path: Path) -> None:
        alvo = tmp_path / "a.bin"
        alvo.write_bytes(b"conteudo")
        with pytest.raises(ModelError, match="SHA-256"):
            verify_archive(alvo, "1" * 64)
        assert not alvo.exists()


class TestExtracao:
    def test_tar_com_caminho_de_escape_e_recusado(self, tmp_path: Path) -> None:
        """`filter="data"` recusa caminho absoluto ou com `..`."""
        malicioso = tmp_path / "mau.tar.gz"
        dentro = tmp_path / "carga"
        dentro.mkdir()
        (dentro / "arquivo").write_bytes(b"x")
        with tarfile.open(malicioso, "w:gz") as tar:
            tar.add(dentro / "arquivo", arcname="../fuga")
        with pytest.raises((tarfile.TarError, ModelError, OSError)):
            babelt.model._extract(malicioso, tmp_path / "destino")
        assert not (tmp_path / "fuga").exists()
