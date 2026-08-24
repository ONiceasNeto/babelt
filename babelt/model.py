"""Obtenção do modelo NMT já convertido.

Até a 0.3.0 o modelo era convertido na máquina do usuário, com
``ct2-transformers-converter``, o que exigia `transformers` e `torch` — cerca
de 2 GB de dependência para uma conversão que sempre produz o mesmo resultado.
A conversão passou a ser feita uma vez, por quem publica (ver
``scripts/build-model.sh``), e o que o usuário baixa é o artefato pronto.

Isso troca "confie na sua máquina para converter" por "confie neste arquivo",
e é por isso que o SHA-256 é obrigatório: o hash é conferido **antes** de
qualquer extração, e um artefato que não bata é apagado sem ser aberto.

A instalação é atômica. Um download interrompido no meio — Ctrl-C, disco
cheio, máquina desligada — não pode deixar um modelo pela metade no destino
final, porque na próxima execução ``is_installed()`` diria que está tudo certo
e o carregamento falharia num ponto muito pior. Por isso a extração acontece
num diretório temporário irmão e só é movida para o lugar depois de verificada.
"""

from __future__ import annotations

import hashlib
import os
import shutil
import sys
import tarfile
import tempfile
import urllib.error
import urllib.request
from pathlib import Path
from typing import Final

__all__ = [
    "MODEL_ID",
    "MODEL_SHA256",
    "MODEL_URL",
    "ModelError",
    "download",
    "is_installed",
    "model_path",
    "verify_archive",
]

#: Modelo de origem no Hugging Face. Só documental agora: o que se baixa é o
#: artefato convertido, não este repositório.
MODEL_ID: Final = "Helsinki-NLP/opus-mt-tc-big-en-pt"

MODEL_URL: Final = "https://github.com/ONiceasNeto/babelt/releases/download/v0.5.0/babelt-model-en-pt-int8.tar.gz"

MODEL_SHA256: Final = "0f4dfcc6ff9819babdf3914cca58166a73d439a10f03a3c0b48328b88a0c11ea"

#: Marca que os dois valores acima ainda não foram preenchidos.
_PLACEHOLDER: Final = "PREENCHER"

#: Arquivos do tokenizer que precisam viajar junto com os pesos.
TOKENIZER_FILES: Final = ("source.spm", "target.spm", "tokenizer_config.json")

#: O que precisa existir para o modelo contar como instalado.
_REQUIRED: Final = ("model.bin", "source.spm", "target.spm")

#: O vocabulário compartilhado mudou de nome entre versões do CTranslate2.
_VOCABULARY: Final = ("shared_vocabulary.json", "shared_vocabulary.txt")

#: Tamanho do bloco de leitura do download. 1 MiB é grande o bastante para o
#: overhead sumir e pequeno o bastante para o progresso andar visivelmente.
_CHUNK: Final = 1024 * 1024

#: Apaga do cursor até o fim da linha. Mesma razão de `CLEAR_LINE` em
#: `__main__`: um número fixo de espaços erra dos dois lados, e o resíduo
#: emenda na saída seguinte. Só sai quando o destino é terminal.
_CLEAR_LINE: Final = "\x1b[K"


class ModelError(RuntimeError):
    """Falha ao baixar, verificar ou extrair o modelo."""


def _data_home() -> Path:
    xdg = os.environ.get("XDG_DATA_HOME")
    if xdg:
        return Path(xdg)
    return Path.home() / ".local" / "share"


def model_path() -> Path:
    """Onde o modelo convertido mora."""
    return _data_home() / "babelt" / "models" / "en-pt"


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


def sha256_of(path: Path) -> str:
    """SHA-256 do arquivo, em minúsculas."""
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(_CHUNK):
            digest.update(chunk)
    return digest.hexdigest()


def verify_archive(path: Path, expected: str | None = None) -> None:
    """Confere o hash do arquivo baixado. **Antes** de abrir, sempre.

    ``expected`` é lido de :data:`MODEL_SHA256` na hora da chamada, e não como
    valor padrão do argumento: valor padrão é avaliado no import, e aí um
    teste que troca a constante não trocaria nada.

    Um artefato que não bate é apagado aqui mesmo: deixá-lo no disco convida a
    próxima execução a reusá-lo, e um arquivo com hash errado é ou corrupção
    de rede ou coisa pior. Nos dois casos não se abre.
    """
    wanted = MODEL_SHA256 if expected is None else expected
    actual = sha256_of(path)
    if actual != wanted.lower():
        path.unlink(missing_ok=True)
        raise ModelError(
            "o artefato baixado não confere com o SHA-256 esperado; "
            "o arquivo foi apagado sem ser aberto\n"
            f"  esperado: {wanted}\n"
            f"  obtido  : {actual}"
        )


def _extract(archive: Path, into: Path) -> Path:
    """Extrai o tar.gz e devolve o diretório que contém o modelo.

    ``filter="data"`` recusa link, dispositivo e caminho absoluto ou com `..`.
    O artefato é nosso, mas um tar que escreve fora do destino é a falha
    clássica, e a defesa custa um argumento.
    """
    with tarfile.open(archive, "r:gz") as tar:
        tar.extractall(into, filter="data")
    candidates = [child for child in into.iterdir() if child.is_dir()]
    if is_installed(into):
        return into
    for candidate in candidates:
        if is_installed(candidate):
            return candidate
    raise ModelError(f"o artefato não contém um modelo utilizável ({archive.name})")


def _fetch(url: str, destination: Path, progress: bool) -> None:
    """Baixa ``url`` para ``destination``, com contador em stderr."""
    try:
        with urllib.request.urlopen(url) as response:  # noqa: S310 - URL fixa
            total = int(response.headers.get("Content-Length") or 0)
            done = 0
            with destination.open("wb") as stream:
                while chunk := response.read(_CHUNK):
                    stream.write(chunk)
                    done += len(chunk)
                    if progress and sys.stderr.isatty():
                        share = f"{done / total:5.1%}" if total else f"{done // _CHUNK} MiB"
                        sys.stderr.write(
                            f"\rbabelt: baixando o modelo {share}{_CLEAR_LINE}"
                        )
                        sys.stderr.flush()
    except (urllib.error.URLError, OSError) as error:
        destination.unlink(missing_ok=True)
        raise ModelError(f"falha ao baixar {url}: {error}") from error
    finally:
        if progress and sys.stderr.isatty():
            sys.stderr.write(f"\r{_CLEAR_LINE}")
            sys.stderr.flush()


def download(progress: bool = True) -> None:
    """Baixa e instala o modelo convertido, se ainda não estiver instalado.

    Idempotente: com o modelo já no lugar, não faz nada. O progresso vai para
    stderr — stdout é a saída traduzida do programa e não pode ser poluída.
    """
    destination = model_path()
    if is_installed(destination):
        _report(progress, f"modelo já instalado em {destination}")
        return

    if _PLACEHOLDER in (MODEL_URL, MODEL_SHA256):
        raise ModelError(
            "esta build não tem URL de modelo publicada. "
            "Gere o artefato com scripts/build-model.sh e preencha "
            "MODEL_URL e MODEL_SHA256 em babelt/model.py, ou aponte "
            "--model-path para um modelo já convertido."
        )

    destination.parent.mkdir(parents=True, exist_ok=True)

    # O temporário é irmão do destino para que a movida final seja um rename
    # dentro do mesmo sistema de arquivos, e portanto atômica.
    staging = Path(tempfile.mkdtemp(prefix=".babelt-download-", dir=destination.parent))
    archive = staging / "model.tar.gz"

    try:
        _report(progress, f"baixando o modelo convertido ({MODEL_ID}, int8)")
        _fetch(MODEL_URL, archive, progress)

        _report(progress, "conferindo o SHA-256")
        verify_archive(archive)

        _report(progress, "extraindo")
        extracted = _extract(archive, staging / "unpacked")
        _verify(extracted)

        # Se outro processo chegou primeiro, o trabalho dele vale tanto quanto
        # o nosso; descarta o próprio em vez de sobrescrever.
        if is_installed(destination):
            _report(progress, "outro processo instalou primeiro; descartando")
            return

        os.replace(extracted, destination)
        _report(progress, f"modelo instalado em {destination}")
    finally:
        shutil.rmtree(staging, ignore_errors=True)


def _report(progress: bool, message: str) -> None:
    if progress:
        print(f"babelt: {message}", file=sys.stderr)
