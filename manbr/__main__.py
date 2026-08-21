"""CLI do manbr.

Contrato de fluxo, que é o que separa uma ferramenta de terminal de um script:
**texto traduzido sempre em stdout, tudo o mais sempre em stderr**. Progresso,
avisos, estatísticas e perguntas vão para stderr, para que
``manbr ss > arquivo`` e ``man ss | manbr | grep -i porta`` funcionem.

Nenhum caminho de erro deixa stdout vazio. Se a tradução falhar por qualquer
motivo, o texto original sai mesmo assim — uma man page em inglês é útil, uma
tela em branco não é.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import textwrap
from dataclasses import replace
from pathlib import Path
from typing import Final, TextIO

from manbr.cache import Cache, CacheStats, PIPELINE_VERSION, cache_root, make_key
from manbr.headers import apply_headers
from manbr.model import MODEL_ID, download, is_installed, model_path
from manbr.normalize import normalize
from manbr.segment import Segment, SegmentKind, reassemble, segment
from manbr.translate import BEAM_SIZE, TranslationOutcome, Translator

__all__ = ["main"]

VERSION: Final = "0.2.0"

EXIT_OK: Final = 0
EXIT_ERROR: Final = 1
EXIT_USAGE: Final = 2
EXIT_NOT_FOUND: Final = 127
EXIT_INTERRUPTED: Final = 130

_DEFAULT_PAGER: Final = "less -R"

#: Segundos para um `<comando> --help` responder. Ajuda que não sai nesse
#: tempo não é ajuda: é um programa que entrou em execução de verdade.
HELP_TIMEOUT: Final = 10

#: Largura de saída. O `man` é lido com MANWIDTH=80, e a prosa volta do modelo
#: numa linha só — sem requebrar, 15% das linhas passariam de 80 colunas e o
#: terminal quebraria no meio da palavra, perdendo a indentação.
DEFAULT_WIDTH: Final = 80
_MIN_WIDTH: Final = 40


def warn(message: str) -> None:
    print(f"manbr: {message}", file=sys.stderr)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="manbr",
        description="Traduz saída de terminal em inglês para pt-BR, offline.",
        epilog=(
            "exemplos:\n"
            "  manbr ss                 executa `man ss` e traduz\n"
            "  man ss | manbr           traduz stdin\n"
            "  nmap --help | manbr      traduz stdin\n"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("command", nargs="?", help="comando cuja ajuda traduzir")
    origem = parser.add_mutually_exclusive_group()
    origem.add_argument(
        "--help-of",
        action="store_true",
        help="executa `<comando> --help` em vez de `man <comando>`",
    )
    origem.add_argument(
        "--auto",
        action="store_true",
        help="tenta `man`; se não houver página, cai para `--help`",
    )
    parser.add_argument(
        "--beam", type=int, default=BEAM_SIZE, metavar="N", help="feixe da busca"
    )
    parser.add_argument(
        "--no-cache", action="store_true", help="ignora o cache, na leitura e na escrita"
    )
    parser.add_argument(
        "--stats", action="store_true", help="estatísticas em stderr ao final"
    )
    parser.add_argument(
        "--model-path", type=Path, metavar="P", help="diretório do modelo"
    )
    parser.add_argument("--version", action="version", version=f"manbr {VERSION}")
    return parser


def read_manpage(command: str) -> str:
    """Saída de ``man`` para ``command``, já sem formatação de terminal."""
    if shutil.which("man") is None:
        raise FileNotFoundError("man não está instalado")
    environment = {**os.environ, "MANWIDTH": os.environ.get("MANWIDTH", "80")}
    result = subprocess.run(
        ["man", command],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=environment,
        text=True,
        errors="replace",
        check=False,
    )
    if result.returncode != 0 or not result.stdout.strip():
        raise LookupError(result.stderr.strip() or f"sem página de manual para {command}")
    return result.stdout


def output_width() -> int:
    """Colunas da saída. ``MANWIDTH`` manda, porque é o que alimentou o `man`."""
    raw = os.environ.get("MANWIDTH", "")
    if raw.isdigit() and int(raw) >= _MIN_WIDTH:
        return int(raw)
    return DEFAULT_WIDTH


def rewrap(segments: list[Segment], width: int) -> list[Segment]:
    """Requebra a prosa e as células de tabela na largura da página.

    O modelo devolve o parágrafo inteiro numa linha: para ele, as quebras de
    largura do `man` não são conteúdo. Bloco literal fica intocado — é tabela
    de saída, exemplo ou sinopse, onde a quebra é significado.

    ``break_long_words`` e ``break_on_hyphens`` desligados de propósito: um
    caminho, uma flag ou uma URL longa fica inteira, mesmo estourando a
    largura. Partir ``--exclude-from=ARQUIVO`` seria o mesmo erro que a fase 1
    gastou o mascaramento inteiro para evitar.
    """
    out: list[Segment] = []
    for item in segments:
        if item.kind is SegmentKind.LITERAL or not item.text.strip():
            out.append(item)
            continue
        # Numa linha de tabela, a largura disponível é o que sobra à direita
        # da coluna: a célula que estourar quebra dentro da própria coluna,
        # com a continuação alinhada — nunca invadindo a esquerda.
        offset = item.column if item.kind is SegmentKind.COLUMNS else item.indent
        wrapped = textwrap.fill(
            " ".join(item.text.split()),
            width=max(width - offset, _MIN_WIDTH),
            break_long_words=False,
            break_on_hyphens=False,
        )
        out.append(replace(item, text=wrapped))
    return out


#: Flags de ajuda, na ordem em que são tentadas. `--help` é o padrão de fato;
#: `-h` cobre quem só implementa a forma curta; `--usage` cobre as ferramentas
#: da AIX/IBM e alguns utilitários antigos.
HELP_FLAGS: Final = ("--help", "-h", "--usage")


def read_help(command: str) -> str:
    """Saída de ajuda de ``command``.

    **Isto executa o binário.** É diferente em espécie de ler uma man page,
    que é um arquivo: rodar `foo --help` roda `foo`. Por isso o comando é
    invocado só com o flag de ajuda, nunca com argumento nenhum a mais, e o
    modo nunca é o padrão — o usuário pede por ele.

    Metade das ferramentas escreve a ajuda em stderr e sai com código 1
    depois de imprimi-la, então nem o fluxo nem o código de saída servem de
    critério: o que decide é ter vindo texto.
    """
    if shutil.which(command) is None:
        raise FileNotFoundError(f"{command} não está instalado")

    for flag in HELP_FLAGS:
        try:
            result = subprocess.run(
                [command, flag],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                errors="replace",
                timeout=HELP_TIMEOUT,
                check=False,
            )
        except (OSError, subprocess.SubprocessError):
            continue
        if result.stdout.strip():
            return result.stdout
    raise LookupError(f"{command} não respondeu a nenhum de {', '.join(HELP_FLAGS)}")


class Progress:
    """Contador em stderr. Silencioso quando stderr não é terminal."""

    def __init__(self, total: int, stream: TextIO | None = None) -> None:
        self._total = total
        self._stream = stream if stream is not None else sys.stderr
        self._enabled = total > 0 and self._stream.isatty()
        self._done = 0

    def advance(self, count: int = 1) -> None:
        self._done += count
        if not self._enabled:
            return
        width = 24
        filled = int(width * self._done / self._total)
        bar = "#" * filled + "." * (width - filled)
        self._stream.write(
            f"\rmanbr: traduzindo [{bar}] {self._done}/{self._total}"
        )
        self._stream.flush()

    def close(self) -> None:
        if self._enabled:
            self._stream.write("\r" + " " * 60 + "\r")
            self._stream.flush()


def translate_document(
    text: str,
    translator: Translator,
    cache: Cache | None,
    *,
    model: str,
    beam: int,
) -> tuple[str, dict[str, int]]:
    """Normaliza, segmenta, traduz o que for prosa e remonta.

    O cache é consultado por segmento, antes de qualquer inferência. O que ele
    guarda é o resultado inteiro — texto, se foi traduzido e por quê não —
    para que uma segunda execução reproduza também as estatísticas.
    """
    normalized = normalize(text)
    segments = segment(normalized)

    outcomes: list[TranslationOutcome | None] = [None] * len(segments)
    pending: list[int] = []
    counters = {"cache_hits": 0, "translated": 0, "english": 0, "literal": 0}

    for index, item in enumerate(segments):
        if item.kind is SegmentKind.LITERAL or not item.text.strip():
            outcomes[index] = TranslationOutcome(item.text, False, None)
            counters["literal"] += 1
            continue
        if cache is not None:
            stored = cache.get(make_key(item.text, model=model, beam=beam))
            if stored is not None:
                outcomes[index] = _decode(stored, item.text)
                counters["cache_hits"] += 1
                continue
        pending.append(index)

    if pending:
        progress = Progress(len(pending))
        # Em blocos, para que um Ctrl-C no meio preserve o que já foi feito.
        block = 16
        for start in range(0, len(pending), block):
            chunk = pending[start : start + block]
            produced = translator.translate_all([segments[i] for i in chunk])
            for index, outcome in zip(chunk, produced, strict=True):
                outcomes[index] = outcome
                if cache is not None:
                    cache.put(
                        make_key(segments[index].text, model=model, beam=beam),
                        _encode(outcome),
                    )
            progress.advance(len(chunk))
        progress.close()

    final: list[Segment] = []
    for item, settled in zip(segments, outcomes, strict=True):
        assert settled is not None
        if item.kind is not SegmentKind.LITERAL and item.text.strip():
            counters["translated" if settled.translated else "english"] += 1
        final.append(replace(item, text=settled.text))

    return reassemble(rewrap(apply_headers(final), output_width())), counters


def _encode(outcome: TranslationOutcome) -> str:
    return json.dumps(
        {"text": outcome.text, "translated": outcome.translated, "reason": outcome.reason},
        ensure_ascii=False,
    )


def _decode(stored: str, fallback: str) -> TranslationOutcome:
    try:
        payload = json.loads(stored)
        return TranslationOutcome(
            text=str(payload["text"]),
            translated=bool(payload["translated"]),
            reason=payload.get("reason"),
        )
    except (ValueError, KeyError, TypeError):
        # Entrada estragada: trata como ausência e devolve o original.
        return TranslationOutcome(fallback, False, "cache inválido")


def emit(text: str) -> None:
    """Escreve em stdout, paginando se for terminal."""
    if not sys.stdout.isatty():
        sys.stdout.write(text)
        sys.stdout.flush()
        return

    pager = os.environ.get("PAGER", _DEFAULT_PAGER)
    try:
        process = subprocess.Popen(pager, shell=True, stdin=subprocess.PIPE, text=True)
    except OSError:
        sys.stdout.write(text)
        return
    try:
        assert process.stdin is not None
        process.stdin.write(text)
        process.stdin.close()
    except BrokenPipeError:
        pass  # o usuário saiu do pager antes do fim
    process.wait()


def ensure_model(directory: Path) -> bool:
    """Garante o modelo, perguntando se der. ``False`` se não houver."""
    if is_installed(directory):
        return True
    if not sys.stdin.isatty() or not sys.stderr.isatty():
        warn(f"modelo não instalado em {directory}")
        warn("rode `manbr` num terminal para baixar, ou veja o README")
        return False
    warn(f"o modelo {MODEL_ID} ainda não foi baixado (~230 MB depois de convertido)")
    try:
        answer = input("manbr: baixar agora? [s/N] ")
    except (EOFError, KeyboardInterrupt):
        print(file=sys.stderr)
        return False
    if answer.strip().lower() not in {"s", "sim", "y", "yes"}:
        warn("seguindo sem traduzir")
        return False
    download(progress=True)
    return is_installed(directory)


def report(counters: dict[str, int], cache_stats: CacheStats | None) -> None:
    prose = counters["translated"] + counters["english"]
    warn(f"segmentos: {prose} de prosa, {counters['literal']} literais")
    if prose:
        warn(
            f"traduzidos: {counters['translated']} "
            f"({counters['translated'] / prose:.1%}); "
            f"mantidos em inglês: {counters['english']} "
            f"({counters['english'] / prose:.1%})"
        )
    warn(f"cache: {counters['cache_hits']} acertos de segmento")
    if cache_stats is not None:
        warn(
            f"cache em disco: {cache_stats.entries} entradas, "
            f"{cache_stats.bytes / 1024:.0f} KiB"
        )


def read_source(command: str, *, help_of: bool, auto: bool) -> str:
    """Texto a traduzir: man page, saída de ajuda, ou man com queda para ajuda."""
    if help_of:
        return read_help(command)
    if not auto:
        return read_manpage(command)
    try:
        return read_manpage(command)
    except LookupError as error:
        # Só a ausência de página justifica executar o binário. `man` que
        # falhou por outro motivo — seção inválida, catman quebrado — é erro,
        # e trocar de fonte esconderia isso.
        if "No manual entry" not in str(error):
            raise
        warn(f"sem página de manual para {command}; tentando --help")
        return read_help(command)


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.beam < 1:
        parser.error("--beam precisa ser >= 1")
    if (args.help_of or args.auto) and not args.command:
        parser.error("--help-of e --auto precisam de um comando")

    # ---- entrada ---------------------------------------------------------
    if args.command:
        try:
            source = read_source(args.command, help_of=args.help_of, auto=args.auto)
        except (FileNotFoundError, LookupError) as error:
            warn(str(error))
            return EXIT_NOT_FOUND
    elif not sys.stdin.isatty():
        source = sys.stdin.read()
    else:
        parser.print_usage(sys.stderr)
        warn("informe um comando ou mande texto pela entrada padrão")
        return EXIT_USAGE

    if not source.strip():
        warn("entrada vazia")
        return EXIT_OK

    # ---- modelo ----------------------------------------------------------
    directory = args.model_path or model_path()
    if not ensure_model(directory):
        # Degradar para o original é melhor que não imprimir nada.
        emit(normalize(source))
        return EXIT_ERROR

    cache = (
        None
        if args.no_cache
        else Cache(
            cache_root(),
            provenance={"model": MODEL_ID, "beam": args.beam},
        )
    )
    translator = Translator(directory, beam_size=args.beam)

    try:
        text, counters = translate_document(
            source, translator, cache, model=MODEL_ID, beam=args.beam
        )
    except KeyboardInterrupt:
        print(file=sys.stderr)
        warn("interrompido; o que já foi traduzido ficou no cache")
        return EXIT_INTERRUPTED
    except Exception as error:  # noqa: BLE001 - degradar é o contrato
        warn(f"falha ao traduzir ({error}); devolvendo o texto original")
        emit(normalize(source))
        return EXIT_ERROR

    emit(text)
    if args.stats:
        report(counters, cache.stats() if cache else None)
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
