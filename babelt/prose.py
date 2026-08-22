"""Guarda de prosa: a entrada é texto em inglês, ou é uma lista de nomes?

O projeto sempre assumiu entrada em prosa inglesa, e nada media o que
acontecia quando a premissa era falsa. `ls | babelt` traduzia nome de
diretório — `Labs` virava `Laboratórios` — e nenhuma validação via o
problema: não há placeholder, nem sentença, nem delimitador envolvido. O texto
não estava corrompido; estava certo para uma premissa errada.

A medida é a densidade de palavras funcionais. Prosa é feita de gramática:
artigo, preposição, conjunção. Saída de comando é feita de nomes.

**A guarda é por documento, e isso foi medido, não escolhido.** Por segmento
as populações não se separam — uma célula de tabela de `--help` como
"Silent mode" tem densidade zero, igual a uma linha de `ls`. Por documento, o
corpus inteiro se separa com folga:

    nonprose   0,000 a 0,095
                      ^ vão livre de 0,086
    --help     0,181 a 0,456
    man        0,295 a 0,473

O limiar fica no meio do vão. Ver README-fase6.md para a distribuição.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from pathlib import Path
from typing import Final

from babelt.mask import mask

__all__ = [
    "FUNCTION_WORDS",
    "PROSE_DENSITY_FLOOR",
    "function_word_density",
    "is_prose",
    "load_function_words",
]

#: Densidade mínima para o documento contar como prosa inglesa. O meio do vão
#: entre 0,095 (o pior documento de saída de comando, um log do journalctl) e
#: 0,181 (o melhor... quer dizer, o pior documento de prosa, `ffmpeg --help`).
PROSE_DENSITY_FLOOR: Final = 0.14

#: Abaixo disto não há amostra para julgar, e o documento passa. Meia dúzia de
#: nomes de arquivo não é distinguível de meia dúzia de palavras de prosa sem
#: preposição — "Display current network sockets" tem densidade zero e é prosa.
#:
#: O número é um compromisso declarado, e não uma medição: com 8, `ls | head`
#: de dez linhas já é barrado e uma frase curta ainda passa. Abaixo disso o
#: sinal não existe, e o resíduo está registrado no README-fase6.
MIN_WORDS_TO_JUDGE: Final = 8

_PATH: Final = Path(__file__).parent / "function_words.txt"
_WORD_RE: Final = re.compile(r"[A-Za-z]+")


def load_function_words(path: Path = _PATH) -> frozenset[str]:
    """Lê a lista, ignorando comentários e linhas vazias."""
    words: set[str] = set()
    for raw in path.read_text(encoding="utf-8").splitlines():
        words.update(raw.split("#", 1)[0].split())
    return frozenset(word.lower() for word in words)


FUNCTION_WORDS: Final = load_function_words()


def function_word_density(texts: Iterable[str]) -> tuple[float, int]:
    """``(densidade, total de palavras)`` do conjunto de segmentos.

    Mede sobre o texto **mascarado**: uma flag, um caminho ou um IP não é
    palavra de idioma nenhum, e contá-los afundaria a densidade de uma sinopse
    tanto quanto a de uma listagem de arquivos.
    """
    total = 0
    hits = 0
    for text in texts:
        for word in _WORD_RE.findall(mask(text).text):
            total += 1
            hits += word.lower() in FUNCTION_WORDS
    return (hits / total if total else 0.0), total


def is_prose(texts: Iterable[str]) -> bool:
    """``False`` quando o documento é lista de nomes, não texto em inglês."""
    density, total = function_word_density(texts)
    if total < MIN_WORDS_TO_JUDGE:
        return True
    return density >= PROSE_DENSITY_FLOOR
