"""Tradução dos segmentos de prosa, com validação obrigatória.

A regra do projeto vale aqui inteira: **não traduzir é sempre melhor que
corromper um comando**. Toda tradução passa por
:func:`babelt.validate.validate` antes de ser aceita, e uma que não passe é
descartada — a linha sai em inglês.

A recuperação por sentença existe porque a rejeição é tudo-ou-nada por
segmento: se um parágrafo de seis frases perde um placeholder na terceira, o
parágrafo inteiro voltaria ao inglês. Dividindo, cinco frases se salvam. A
divisão acontece no texto mascarado, nunca no original, para que nenhum corte
caia dentro de um ``⟦n⟧``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, Final

from babelt.mask import CLOSE, OPEN, mask, restore
from babelt.segment import Segment, SegmentKind
from babelt.validate import split_sentences, validate, validate_structure

if TYPE_CHECKING:  # pragma: no cover
    import sentencepiece

__all__ = [
    "BEAM_SIZE",
    "GLOSSARY",
    "PROSE_TYPOGRAPHY",
    "SHELL_METACHARS",
    "TranslationOutcome",
    "Translator",
    "WIRE_CLOSE",
    "WIRE_OPEN",
    "apply_glossary",
    "from_wire",
    "load_glossary",
    "split_sentences",
    "to_wire",
]

#: Feixe da busca. Default 1 desde a fase 3.1: medido, beam 4 custa ~3x o
#: tempo (16 frases em 20.8s contra 6.6s) e a inspeção da amostra de 30 não
#: mostrou diferença que pagasse isso. Configurável no construtor.
BEAM_SIZE: Final = 1

#: Segmentos por lote. Agrupados por tamanho para reduzir padding.
MAX_BATCH_SIZE: Final = 32

_GLOSSARY_PATH: Final = Path(__file__).parent / "glossary.txt"

_PLACEHOLDER_RE: Final = re.compile(f"{OPEN}(\\d+){CLOSE}")

# Formato de fio: como o placeholder viaja até o modelo.
#
# ⟦ e ⟧ (U+27E6/U+27E7) foram escolhidos na fase 1 supondo que o tokenizer os
# preservaria como unidade. Medido nesta fase, o sentencepiece do
# opus-mt-tc-big-en-pt não tem os dois caracteres no vocabulário: cada ⟦n⟧ vira
# dois <unk> e o modelo devolve "⁇ 0 ⁇". Num teste de 10 frases, ⟦n⟧ sobreviveu
# 0 vezes e [[n]] sobreviveu 10.
#
# A conversão fica aqui, e não em mask.py, de propósito: ⟦n⟧ continua sendo o
# formato do projeto, validate continua conferindo ⟦n⟧, e só a viagem até o
# modelo usa outra roupa. Trocar de modelo é trocar estas duas constantes.
WIRE_OPEN: Final = "[["
WIRE_CLOSE: Final = "]]"

_WIRE_RE: Final = re.compile(
    re.escape(WIRE_OPEN) + r"(\d+)" + re.escape(WIRE_CLOSE)
)

# Marian espera a fonte terminada em </s>; sem isso o modelo não sabe onde
# parar e repete a frase até o limite de comprimento.
_EOS: Final = "</s>"


def to_wire(masked: str) -> str:
    """Troca ⟦n⟧ pelo formato que o tokenizer do modelo preserva."""
    return _PLACEHOLDER_RE.sub(
        lambda m: f"{WIRE_OPEN}{m.group(1)}{WIRE_CLOSE}", masked
    )


def from_wire(text: str) -> str:
    """Desfaz :func:`to_wire`.

    Deliberadamente estrito: um ``[[ 0 ]]`` com espaços não volta a ⟦0⟧, e a
    validação rejeita o segmento. Aceitar formas frouxas seria aceitar saída
    que o modelo já mexeu.
    """
    return _WIRE_RE.sub(lambda m: f"{OPEN}{m.group(1)}{CLOSE}", text)


def _has_escaped_brackets(masked: str) -> bool:
    """O texto de origem continha ⟦ ou ⟧ literais, que mask escapou.

    Nesse caso não há conversão segura para o formato de fio, então o segmento
    vai como está — o modelo provavelmente destrói os escapes, a validação
    rejeita e a linha sai em inglês. Preferir inglês a corromper é a regra do
    projeto, e o caso exige uma man page com ⟦ no texto.
    """
    return f"{OPEN}{OPEN}" in masked or f"{CLOSE}{CLOSE}" in masked

#: Metacaracteres de shell. Um <unk> aqui é buraco de cobertura de `mask`:
#: o caractere está num pedaço de sintaxe que deveria ter virado placeholder.
SHELL_METACHARS: Final = frozenset("{}|=^@`\\~$<>*[]&;%#")

#: Tipografia de prosa. Um <unk> aqui é buraco de vocabulário do modelo, e
#: mascarar não resolveria — o caractere está no meio de uma frase.
PROSE_TYPOGRAPHY: Final = frozenset("•©‐–—“”‘’…§¶«»°±×÷")


@dataclass(frozen=True)
class TranslationOutcome:
    """Resultado da tradução de um segmento."""

    #: Texto final, já restaurado. Em inglês se a tradução foi rejeitada.
    text: str
    #: ``False`` quando o original foi devolvido.
    translated: bool
    #: Motivo da rejeição, ou o resumo do que falhou por sentença.
    reason: str | None


def load_glossary(path: Path = _GLOSSARY_PATH) -> dict[str, str]:
    """Lê o glossário, ignorando comentários e linhas vazias."""
    table: dict[str, str] = {}
    for number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        entry = raw.split("#", 1)[0].strip()
        if not entry:
            continue
        if "\t" not in entry:
            raise ValueError(f"{path}:{number}: esperado TRADUZIDO<TAB>INGLÊS")
        translated, english = (part.strip() for part in entry.split("\t", 1))
        if not translated or not english:
            raise ValueError(f"{path}:{number}: lado vazio")
        table[translated.lower()] = english
    return table


GLOSSARY: Final = load_glossary()

_GLOSSARY_RE: Final = (
    re.compile(
        r"\b("
        + "|".join(sorted(map(re.escape, GLOSSARY), key=len, reverse=True))
        + r")\b",
        re.IGNORECASE,
    )
    if GLOSSARY
    else None
)


def apply_glossary(text: str, table: dict[str, str] | None = None) -> str:
    """Devolve ao inglês os termos que o modelo não deveria ter traduzido."""
    if _GLOSSARY_RE is None:
        return text
    lookup = GLOSSARY if table is None else {k.lower(): v for k, v in table.items()}
    return _GLOSSARY_RE.sub(lambda m: lookup.get(m.group(0).lower(), m.group(0)), text)


def _indices_in(text: str) -> set[int]:
    return {int(match.group(1)) for match in _PLACEHOLDER_RE.finditer(text)}


class Translator:
    """Tradutor EN->pt-BR sobre um modelo CTranslate2 já convertido.

    O modelo só é carregado no primeiro uso: construir um ``Translator`` num
    caminho que nunca vai traduzir nada não custa nem tempo nem memória.
    """

    def __init__(self, model_dir: Path, beam_size: int = BEAM_SIZE) -> None:
        self._model_dir = model_dir
        self._beam_size = beam_size
        self._engine: Any | None = None
        self._source: sentencepiece.SentencePieceProcessor | None = None
        self._target: sentencepiece.SentencePieceProcessor | None = None
        # Cache em memória, por execução. Man page repete muito: "Show summary
        # of options." aparece em quase toda página. Cache em disco é da fase 4.
        self._cache: dict[str, str] = {}
        self.cache_hits = 0
        self.cache_misses = 0

    @property
    def loaded(self) -> bool:
        """Os pesos já foram carregados para a memória?"""
        return self._engine is not None

    def _load_tokenizer(self) -> None:
        """Carrega só os sentencepiece — barato, e basta para checar OOV."""
        if self._source is not None:
            return
        import sentencepiece

        self._source = sentencepiece.SentencePieceProcessor(
            model_file=str(self._model_dir / "source.spm")
        )
        self._target = sentencepiece.SentencePieceProcessor(
            model_file=str(self._model_dir / "target.spm")
        )

    def _load_engine(self) -> None:
        """Carrega os pesos. É o que custa os 4.5s e o 1.6 GB."""
        self._load_tokenizer()
        if self._engine is not None:
            return
        import ctranslate2

        # compute_type explícito: sem ele o CTranslate2 infere int8_float16 do
        # arquivo e avisa em stderr que caiu para int8_float32 na CPU.
        self._engine = ctranslate2.Translator(
            str(self._model_dir), device="cpu", compute_type="int8"
        )

    def oov_pieces(self, text: str) -> list[str]:
        """Pedaços de ``text`` que o tokenizer do modelo não conhece.

        Barato: só o sentencepiece, sem tocar nos pesos.
        """
        self._load_tokenizer()
        assert self._source is not None
        ids = self._source.encode(text)
        pieces = self._source.encode(text, out_type=str)
        unknown = self._source.unk_id()
        return [
            piece
            for identifier, piece in zip(ids, pieces, strict=True)
            if identifier == unknown
        ]

    def oov_diagnosis(self, text: str) -> tuple[list[str], bool]:
        """Pedaços desconhecidos e se o problema é cobertura de ``mask``.

        Devolve ``(pedaços, é_buraco_de_cobertura)``. É buraco de cobertura
        quando **todo** pedaço desconhecido é metacaractere de shell — o
        caractere está num pedaço de sintaxe que deveria ter virado
        placeholder, e mascarar resolveria. Se houver tipografia de prosa
        (•, ©, travessão), mascarar não resolve: o caractere está no meio de
        uma frase, e o buraco é de vocabulário do modelo.
        """
        pieces = self.oov_pieces(text)
        if not pieces:
            return [], False
        coverage = all(
            any(char in SHELL_METACHARS for char in piece)
            and not any(char in PROSE_TYPOGRAPHY for char in piece)
            for piece in pieces
        )
        return pieces, coverage

    def _translate_texts(self, texts: list[str]) -> list[str]:
        """Traduz vários textos de uma vez, agrupados por tamanho.

        Ordenar por comprimento antes de lotar reduz o padding: um lote de
        frases de tamanhos parecidos desperdiça menos computação que um que
        mistura uma linha de três palavras com um parágrafo.
        """
        if not texts:
            return []

        pending = list(
            dict.fromkeys(text for text in texts if text not in self._cache)
        )
        # Conta trabalho poupado, não só acerto de cache entre chamadas:
        # cinco cópias da mesma frase num lote são quatro inferências que não
        # aconteceram, tanto quanto se viessem de uma chamada anterior.
        self.cache_hits += len(texts) - len(pending)
        self.cache_misses += len(pending)
        if pending:
            for text, output in zip(
                pending, self._run_model(pending), strict=True
            ):
                self._cache[text] = output
        return [self._cache[text] for text in texts]

    def _run_model(self, texts: list[str]) -> list[str]:
        """A parte cara: tokeniza, roda o modelo, decodifica."""
        self._load_engine()
        assert self._engine is not None
        assert self._source is not None
        assert self._target is not None

        prepared = [
            text if _has_escaped_brackets(text) else to_wire(text)
            for text in texts
        ]
        tokenized = [
            self._source.encode(text, out_type=str) + [_EOS] for text in prepared
        ]
        order = sorted(range(len(tokenized)), key=lambda i: len(tokenized[i]))

        results = self._engine.translate_batch(
            [tokenized[i] for i in order],
            beam_size=self._beam_size,
            max_batch_size=MAX_BATCH_SIZE,
        )

        out: list[str] = [""] * len(texts)
        for position, index in enumerate(order):
            hypothesis = results[position].hypotheses[0]
            out[index] = from_wire(self._target.decode(hypothesis))
        return out

    def translate_all(
        self, segments: list[Segment]
    ) -> list[TranslationOutcome]:
        """Traduz uma lista de segmentos, em lote.

        Faz duas passadas: uma com os parágrafos inteiros e, para os que a
        validação rejeitar, outra com as sentenças deles. Assim o custo de
        recuperar um parágrafo ruim é um lote a mais, não uma chamada por
        frase.
        """
        outcomes: list[TranslationOutcome | None] = [None] * len(segments)

        candidates: list[int] = []
        masked: dict[int, tuple[str, dict[int, str]]] = {}
        for index, item in enumerate(segments):
            if item.kind is SegmentKind.LITERAL or not item.text.strip():
                outcomes[index] = TranslationOutcome(item.text, False, None)
                continue
            result = mask(item.text)
            # Guarda de vocabulário: se o tokenizer não conhece algum pedaço,
            # o modelo devolve ⁇ no lugar dele. Não vale gastar inferência
            # para descobrir isso — e a saída seria rejeitada de qualquer
            # forma pela regra de token desconhecido.
            if self.oov_pieces(to_wire(result.text)):
                outcomes[index] = TranslationOutcome(item.text, False, "oov")
                continue
            masked[index] = (result.text, result.tokens)
            candidates.append(index)

        if candidates:
            produced = self._translate_texts(
                [masked[index][0] for index in candidates]
            )
            retry: list[int] = []
            for index, output in zip(candidates, produced, strict=True):
                source, tokens = masked[index]
                verdict = validate(source, output, tokens)
                if verdict.ok:
                    verdict = validate_structure(source, output)
                if verdict.ok:
                    outcomes[index] = TranslationOutcome(
                        restore(apply_glossary(output), tokens), True, None
                    )
                else:
                    retry.append(index)

            if retry:
                self._recover_by_sentence(retry, masked, segments, outcomes)

        return [
            outcome
            if outcome is not None
            else TranslationOutcome(segments[position].text, False, "não processado")
            for position, outcome in enumerate(outcomes)
        ]

    def _recover_by_sentence(
        self,
        indices: list[int],
        masked: dict[int, tuple[str, dict[int, str]]],
        segments: list[Segment],
        outcomes: list[TranslationOutcome | None],
    ) -> None:
        """Segunda tentativa, frase a frase, para os segmentos rejeitados."""
        plan: list[tuple[int, list[str]]] = []
        batch: list[str] = []
        for index in indices:
            parts = split_sentences(masked[index][0])
            plan.append((index, parts))
            batch.extend(parts[0::2])

        produced = self._translate_texts(batch)

        cursor = 0
        for index, parts in plan:
            tokens = masked[index][1]
            pieces = list(parts)
            failures = 0
            reasons: list[str] = []
            total = len(parts[0::2])
            for position in range(0, len(parts), 2):
                sentence = parts[position]
                output = produced[cursor]
                cursor += 1
                subset = {
                    key: value
                    for key, value in tokens.items()
                    if key in _indices_in(sentence)
                }
                verdict = validate(sentence, output, subset)
                if verdict.ok:
                    verdict = validate_structure(sentence, output)
                if verdict.ok:
                    pieces[position] = apply_glossary(output)
                else:
                    failures += 1  # a frase fica em inglês
                    if verdict.reason is not None:
                        reasons.append(verdict.reason)
            joined = restore("".join(pieces), tokens)
            # O motivo da primeira frase rejeitada viaja junto. Sem ele o
            # segmento chegava ao relatório como "N de M sentenças
            # rejeitadas", que diz quantas e não diz por quê — e medir a taxa
            # de rejeição por motivo era impossível a partir daqui.
            detail = f": {reasons[0]}" if reasons else ""
            outcomes[index] = TranslationOutcome(
                text=joined,
                translated=failures < total,
                reason=(
                    None
                    if failures == 0
                    else f"{failures} de {total} sentenças rejeitadas{detail}"
                ),
            )

    def translate_segment(self, segment: Segment) -> TranslationOutcome:
        """Traduz um segmento só."""
        return self.translate_all([segment])[0]
