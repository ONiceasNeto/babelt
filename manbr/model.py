"""Obtenção e conversão do modelo NMT.

O modelo é baixado do Hugging Face e convertido para CTranslate2 com
quantização int8. A conversão é cara e acontece uma vez; o resultado fica em
``~/.local/share/manbr/models/en-pt``.

A instalação é atômica. Uma conversão interrompida no meio — Ctrl-C, disco
cheio, máquina desligada — não pode deixar um modelo pela metade no destino
final, porque na próxima execução ``is_installed()`` diria que está tudo certo
e o carregamento falharia num ponto muito pior. Por isso a conversão acontece
num diretório temporário irmão e só é movida para o lugar depois de verificada.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Final

__all__ = [
    "MODEL_ID",
    "ModelError",
    "download",
    "is_installed",
    "model_path",
]

#: Modelo de origem no Hugging Face.
MODEL_ID: Final = "Helsinki-NLP/opus-mt-tc-big-en-pt"

#: Arquivos do tokenizer que precisam viajar junto com os pesos.
TOKENIZER_FILES: Final = ("source.spm", "target.spm", "tokenizer_config.json")

#: O que precisa existir para o modelo contar como instalado.
_REQUIRED: Final = ("model.bin", "source.spm", "target.spm")

#: O vocabulário compartilhado mudou de nome entre versões do CTranslate2.
_VOCABULARY: Final = ("shared_vocabulary.json", "shared_vocabulary.txt")


class ModelError(RuntimeError):
    """Falha ao baixar, converter ou verificar o modelo."""


def _data_home() -> Path:
    xdg = os.environ.get("XDG_DATA_HOME")
    if xdg:
        return Path(xdg)
    return Path.home() / ".local" / "share"


def model_path() -> Path:
    """Onde o modelo convertido mora."""
    return _data_home() / "manbr" / "models" / "en-pt"


def _verify(directory: Path) -> None:
    """Levanta :class:`ModelError` se o diretório não for um modelo usável."""
    for name in _REQUIRED:
        target = directory / name
        if not target.is_file():
            raise ModelError(f"{name} ausente em {directory}")
        if target.stat().st_size == 0:
            raise ModelError(f"{name} está vazio em {directory}")
    if not any((directory / name).is_file() for name in _VOCABULARY):
        raise ModelError(
            f"vocabulário compartilhado ausente em {directory} "
            f"(esperado um de {', '.join(_VOCABULARY)})"
        )


def is_installed(directory: Path | None = None) -> bool:
    """O modelo está instalado e íntegro?"""
    try:
        _verify(directory if directory is not None else model_path())
    except ModelError:
        return False
    return True


def _converter_command(output: Path) -> list[str]:
    executable = shutil.which("ct2-transformers-converter")
    base = (
        [executable]
        if executable
        else [sys.executable, "-m", "ctranslate2.converters.transformers"]
    )
    return [
        *base,
        "--model",
        MODEL_ID,
        "--output_dir",
        str(output),
        "--quantization",
        "int8",
        "--copy_files",
        *TOKENIZER_FILES,
    ]


def download(progress: bool = True) -> None:
    """Baixa e converte o modelo, se ainda não estiver instalado.

    Idempotente: com o modelo já no lugar, não faz nada. O progresso vai para
    stderr — stdout é a saída traduzida do programa e não pode ser poluída.
    """
    destination = model_path()
    if is_installed(destination):
        _report(progress, f"modelo já instalado em {destination}")
        return

    destination.parent.mkdir(parents=True, exist_ok=True)

    # O temporário é irmão do destino para que a movida final seja um rename
    # dentro do mesmo sistema de arquivos, e portanto atômica.
    staging = Path(
        tempfile.mkdtemp(prefix=".manbr-download-", dir=destination.parent)
    )
    converted = staging / "en-pt"

    try:
        _report(progress, f"baixando e convertendo {MODEL_ID} (int8)…")
        _report(progress, "primeira execução; pode levar alguns minutos")
        result = subprocess.run(
            _converter_command(converted),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            raise ModelError(
                f"ct2-transformers-converter falhou ({result.returncode}):\n"
                f"{result.stdout.strip()[-2000:]}"
            )

        _verify(converted)

        # Se outro processo chegou primeiro, o trabalho dele vale tanto quanto
        # o nosso; descarta o próprio em vez de sobrescrever.
        if is_installed(destination):
            _report(progress, "outro processo instalou primeiro; descartando")
            return

        os.replace(converted, destination)
        _report(progress, f"modelo instalado em {destination}")
    finally:
        shutil.rmtree(staging, ignore_errors=True)


def _report(progress: bool, message: str) -> None:
    if progress:
        print(f"manbr: {message}", file=sys.stderr)
