"""Validação da tradução contra o texto mascarado.

Esta é a garantia real do projeto. O modelo NMT não tem obrigação nenhuma de
preservar os placeholders — ele pode apagar, duplicar, reordenar ou inventar.
Reordenar é legítimo (a ordem das palavras muda entre inglês e português);
qualquer outra coisa não é.

Uma tradução que não passe aqui deve ser descartada e a linha original
mantida em inglês. Não traduzir é sempre melhor que corromper um comando.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass
from typing import Final

from babelt.mask import CLOSE, OPEN

__all__ = [
    "MAX_LENGTH_RATIO",
    "MIN_LENGTH_RATIO",
    "UNKNOWN_MARKERS",
    "ValidationResult",
    "split_sentences",
    "validate",
    "validate_structure",
]

#: Limites da razão de comprimento traduzido/original.
MIN_LENGTH_RATIO: Final = 0.5
MAX_LENGTH_RATIO: Final = 2.5

#: Marcas de token desconhecido na saída do modelo. U+2047 é o que o
#: sentencepiece devolve para um <unk> decodificado.
UNKNOWN_MARKERS: Final = ("\u2047", "<unk>", "\ufffd")

#: Delimitadores cuja contagem tem de sobreviver à tradução.
_DELIMITERS: Final = "[]{}()"

_PLACEHOLDER_RE: Final = re.compile(f"{OPEN}(\\d+){CLOSE}")

# Corte de sentença: depois de . ! ? seguido de branco. O grupo de captura
# guarda o separador para que a junção devolva o texto original. Mora aqui, e
# não em translate.py, porque a regra de contagem de sentenças e o caminho de
# recuperação por sentença precisam cortar exatamente igual — se divergirem, a
# validação reprova o que a recuperação produziu.
_SENTENCE_RE: Final = re.compile(r"(?<=[.!?])(\s+)(?=\S)")


def split_sentences(text: str) -> list[str]:
    """Divide em sentenças, guardando os separadores.

    Devolve uma lista intercalada ``[sentença, separador, sentença, ...]``;
    ``"".join(resultado)`` reproduz a entrada caractere a caractere.

    Deve receber texto **mascarado**: o corte só acontece depois de
    ``.``/``!``/``?`` e um ``⟦n⟧`` só contém dígitos, então nenhum corte cai
    dentro de um placeholder.
    """
    return _SENTENCE_RE.split(text)


def _sentences(text: str) -> list[str]:
    """Só as sentenças, sem os separadores, normalizadas para comparação."""
    return [piece.strip() for piece in split_sentences(text)[0::2] if piece.strip()]
_ESCAPED_PAIR_RE: Final = re.compile(f"{OPEN}{OPEN}|{CLOSE}{CLOSE}")
_BRACKETED_RE: Final = re.compile(f"{OPEN}[^{OPEN}{CLOSE}]{{0,32}}{CLOSE}")
_ANY_BRACKET_RE: Final = re.compile(f"[{OPEN}{CLOSE}]")


@dataclass(frozen=True)
class ValidationResult:
    """Resultado de :func:`validate`."""

    #: A tradução pode ser usada.
    ok: bool
    #: Regra violada e índice envolvido; ``None`` se ``ok``.
    reason: str | None


_OK: Final = ValidationResult(ok=True, reason=None)


def _drop_escaped(text: str) -> str:
    """Remove os pares escapados ``⟦⟦``/``⟧⟧``, que não são placeholders."""
    return _ESCAPED_PAIR_RE.sub("", text)


def _malformed_fragment(text: str) -> str:
    """Trecho representativo do placeholder malformado, para o diagnóstico."""
    bracketed = _BRACKETED_RE.search(text)
    if bracketed is not None:
        return bracketed.group(0)
    lone = _ANY_BRACKET_RE.search(text)
    if lone is None:  # pragma: no cover - só chamado quando há bracket solto
        return text[:16]
    return text[lone.start() : lone.start() + 16]


def validate(
    original_masked: str,
    translated: str,
    tokens: dict[int, str],
) -> ValidationResult:
    """Decide se ``translated`` preserva a sintaxe de ``original_masked``.

    ``original_masked`` e ``translated`` são ambos texto mascarado: a
    restauração só acontece depois de passar por aqui.
    """
    # Regra 3: tradução vazia.
    if not translated.strip():
        return ValidationResult(ok=False, reason="tradução vazia")

    scannable = _drop_escaped(translated)

    # Regra 5: placeholder malformado (⟦ sem ⟧, ⟧ sem ⟦, ou ⟦abc⟧).
    if _ANY_BRACKET_RE.search(_PLACEHOLDER_RE.sub("", scannable)):
        fragment = _malformed_fragment(_PLACEHOLDER_RE.sub("", scannable))
        return ValidationResult(
            ok=False, reason=f"placeholder malformado: {fragment!r}"
        )

    counts: dict[int, int] = {}
    for match in _PLACEHOLDER_RE.finditer(scannable):
        index = int(match.group(1))
        counts[index] = counts.get(index, 0) + 1

    # Regra 2: placeholder inventado pelo modelo.
    for index in sorted(counts):
        if index not in tokens:
            return ValidationResult(
                ok=False, reason=f"placeholder {index} inesperado"
            )

    # Regra 1: cada índice de tokens aparece exatamente uma vez.
    for index in sorted(tokens):
        seen = counts.get(index, 0)
        if seen == 0:
            return ValidationResult(ok=False, reason=f"placeholder {index} ausente")
        if seen > 1:
            return ValidationResult(
                ok=False,
                reason=f"placeholder {index} duplicado ({seen} ocorrências)",
            )

    # Regra 4: razão de comprimento. Com original vazio não há razão a checar;
    # a regra 3 já garantiu que a tradução não é vazia.
    if original_masked:
        ratio = len(translated) / len(original_masked)
        if not MIN_LENGTH_RATIO <= ratio <= MAX_LENGTH_RATIO:
            return ValidationResult(
                ok=False,
                reason=(
                    f"razão de comprimento {ratio:.2f} fora de "
                    f"[{MIN_LENGTH_RATIO}, {MAX_LENGTH_RATIO}]"
                ),
            )

    return _OK


def validate_structure(source: str, translated: str) -> ValidationResult:
    """Confere o que :func:`validate` não vê.

    ``validate`` cuida dos placeholders. Tudo o que o modelo estraga fora
    deles passava: a fase 3 mediu ``[OPTION]`` virando ``[OP ⁇ O]`` com
    aprovação, e 11.6% dos parágrafos multi-frase voltando com número de
    frases diferente. Estas regras fecham essas classes.

    Ambos os argumentos são texto mascarado — a restauração só acontece
    depois de passar por aqui.
    """
    # Regra 2 primeiro: um <unk> na saída é o sinal mais barato e mais claro
    # de corrupção, e explica os outros sintomas quando aparece junto.
    for marker in UNKNOWN_MARKERS:
        if marker in translated:
            return ValidationResult(
                ok=False, reason=f"token desconhecido na saída: {marker!r}"
            )

    source_sentences = _sentences(source)
    translated_sentences = _sentences(translated)

    # Regra 1: o modelo não pode somir com uma frase nem inventar outra.
    if len(source_sentences) != len(translated_sentences):
        return ValidationResult(
            ok=False,
            reason=(
                f"contagem de sentenças mudou: {len(source_sentences)} -> "
                f"{len(translated_sentences)}"
            ),
        )

    # Regra 3: repetição. É o modo de falha de Marian sem </s>, e sobrevive
    # à regra 1 quando o modelo repete e omite na mesma proporção.
    source_counts = Counter(source_sentences)
    for sentence, count in Counter(translated_sentences).items():
        if count > 1 and count > source_counts.get(sentence, 0):
            return ValidationResult(
                ok=False,
                reason=f"sentença repetida {count}x: {sentence[:40]!r}",
            )

    # Regra 4: delimitadores. Pega o colchete que some sem deixar <unk>.
    for delimiter in _DELIMITERS:
        before = source.count(delimiter)
        after = translated.count(delimiter)
        if before != after:
            return ValidationResult(
                ok=False,
                reason=f"delimitador {delimiter!r}: {before} -> {after}",
            )

    return _OK
