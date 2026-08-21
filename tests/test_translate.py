"""Testes de translate.

A maior parte não precisa do modelo: o fluxo de decisão (literal passa,
tradução rejeitada volta ao inglês, sentença ruim não derruba o parágrafo) é
testável com um tradutor falso, e é onde mora a garantia do projeto. Os testes
marcados `model` exercitam o modelo de verdade e são pulados sem ele.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from manbr.mask import CLOSE, OPEN, mask
from manbr.model import model_path
from manbr.segment import Segment, SegmentKind
from manbr.translate import (
    GLOSSARY,
    TranslationOutcome,
    Translator,
    apply_glossary,
    from_wire,
    load_glossary,
    split_sentences,
    to_wire,
)

needs_model = pytest.mark.model


def prose(text: str, indent: int = 7) -> Segment:
    return Segment(kind=SegmentKind.PROSE, text=text, indent=indent)


def literal(text: str, indent: int = 7) -> Segment:
    return Segment(kind=SegmentKind.LITERAL, text=text, indent=indent)


class FakeTranslator(Translator):
    """Translator com o modelo trocado por uma função.

    ``oov`` lista pedaços que o tokenizer falso deve reportar como
    desconhecidos, para exercitar a guarda de vocabulário sem modelo.
    """

    def __init__(self, behaviour: object, oov: list[str] | None = None) -> None:
        super().__init__(Path("/inexistente"))
        self._behaviour = behaviour
        self._oov = oov or []

    def _run_model(self, texts: list[str]) -> list[str]:
        return [self._behaviour(text) for text in texts]  # type: ignore[operator]

    def oov_pieces(self, text: str) -> list[str]:
        return [piece for piece in self._oov if piece in text]


# --------------------------------------------------------------------------
# Formato de fio
# --------------------------------------------------------------------------


class TestFormatoDeFio:
    def test_ida_e_volta(self) -> None:
        assert to_wire(f"a {OPEN}0{CLOSE} b {OPEN}12{CLOSE}") == "a [[0]] b [[12]]"
        assert from_wire("a [[0]] b [[12]]") == f"a {OPEN}0{CLOSE} b {OPEN}12{CLOSE}"

    def test_redondo(self) -> None:
        text = f"Use {OPEN}0{CLOSE} para {OPEN}1{CLOSE}."
        assert from_wire(to_wire(text)) == text

    def test_forma_frouxa_nao_volta(self) -> None:
        """[[ 0 ]] mexido pelo modelo não vira placeholder — validate rejeita."""
        assert from_wire("a [[ 0 ]] b") == "a [[ 0 ]] b"
        assert from_wire("a [[x]] b") == "a [[x]] b"

    def test_texto_sem_placeholder(self) -> None:
        assert to_wire("nada aqui") == "nada aqui"
        assert from_wire("nada aqui") == "nada aqui"


# --------------------------------------------------------------------------
# Divisão em sentenças
# --------------------------------------------------------------------------


class TestDivisaoEmSentencas:
    def test_junta_de_volta_exato(self) -> None:
        text = f"Use {OPEN}0{CLOSE} agora.  Depois {OPEN}1{CLOSE} aqui!  Fim?"
        assert "".join(split_sentences(text)) == text

    def test_nao_corta_dentro_do_placeholder(self) -> None:
        for piece in split_sentences(f"A {OPEN}0{CLOSE}. B {OPEN}1{CLOSE}.")[0::2]:
            assert piece.count(OPEN) == piece.count(CLOSE)

    def test_uma_sentenca_so(self) -> None:
        assert split_sentences("Sem ponto final") == ["Sem ponto final"]

    def test_ponto_de_abreviacao_nao_e_fronteira_util(self) -> None:
        """Divide em 'e.g. ' também; é aceitável — cada pedaço ainda valida."""
        parts = split_sentences("Veja e.g. isto. E aquilo.")
        assert "".join(parts) == "Veja e.g. isto. E aquilo."


# --------------------------------------------------------------------------
# Glossário
# --------------------------------------------------------------------------


class TestGlossario:
    def test_substitui_com_fronteira_de_palavra(self) -> None:
        assert apply_glossary("abra a tomada") == "abra a socket"
        assert apply_glossary("a concha expande") == "a shell expande"

    def test_nucleo_nao_esta_no_glossario(self) -> None:
        """Removido por medição: o modelo já devolve "kernel" sozinho, e a
        entrada estragava "core" (que vira "núcleo") em man pages."""
        assert "núcleo" not in GLOSSARY
        assert apply_glossary("o núcleo do sistema") == "o núcleo do sistema"

    def test_plural_tem_entrada_propria(self) -> None:
        assert apply_glossary("os soquetes abertos") == "os sockets abertos"

    def test_ignora_caixa(self) -> None:
        assert apply_glossary("Tomada aberta") == "socket aberta"

    def test_nao_pega_dentro_de_palavra(self) -> None:
        assert apply_glossary("tomadinha") == "tomadinha"

    def test_termo_ausente_fica(self) -> None:
        assert apply_glossary("um diretório") == "um diretório"

    def test_formato_invalido_falha(self, tmp_path: Path) -> None:
        bad = tmp_path / "g.txt"
        bad.write_text("sem tab\n", encoding="utf-8")
        with pytest.raises(ValueError, match="TAB"):
            load_glossary(bad)

    def test_tabela_carregada(self) -> None:
        assert GLOSSARY["tomada"] == "socket"


# --------------------------------------------------------------------------
# Fluxo de decisão
# --------------------------------------------------------------------------


class TestFluxo:
    def test_literal_passa_intacto(self) -> None:
        translator = FakeTranslator(lambda text: "NUNCA")
        item = literal("ss -tulpn")
        (outcome,) = translator.translate_all([item])
        assert outcome == TranslationOutcome("ss -tulpn", False, None)

    def test_segmento_vazio_passa_intacto(self) -> None:
        translator = FakeTranslator(lambda text: "NUNCA")
        (outcome,) = translator.translate_all([prose("   ")])
        assert not outcome.translated

    def test_traducao_boa_e_restaurada(self) -> None:
        translator = FakeTranslator(
            lambda text: text.replace("List", "Liste").replace("[[", "[[")
        )
        (outcome,) = translator.translate_all([prose("List --all now.")])
        assert outcome.translated
        assert outcome.text == "Liste --all now."
        assert outcome.reason is None

    def test_placeholder_perdido_derruba_o_paragrafo(self) -> None:
        """Uma frase só: sem sentença para recuperar, sai em inglês."""
        translator = FakeTranslator(lambda text: "traducao sem placeholder")
        item = prose("Use --all here.")
        (outcome,) = translator.translate_all([item])
        assert not outcome.translated
        assert outcome.text == item.text
        assert outcome.reason is not None

    def test_recuperacao_por_sentenca(self) -> None:
        """A segunda frase perde o placeholder; a primeira se salva.

        O fake recebe o texto mascarado com ⟦n⟧: quem troca para o formato de
        fio é `_translate_texts`, que é justamente o que ele substitui.
        """
        first, second = f"{OPEN}0{CLOSE}", f"{OPEN}1{CLOSE}"

        def behaviour(text: str) -> str:
            if first in text and second in text:
                return "lixo"  # o parágrafo inteiro falha
            if second in text:
                return "frase sem marcador nenhum"
            return text.replace("Read", "Leia")

        translator = FakeTranslator(behaviour)
        item = prose("Read --all first. Then use --now here.")
        (outcome,) = translator.translate_all([item])
        assert outcome.translated
        assert "Leia" in outcome.text
        assert "Then use --now here." in outcome.text  # frase ruim em inglês
        assert outcome.reason == "1 de 2 sentenças rejeitadas"

    def test_todas_as_sentencas_falham(self) -> None:
        translator = FakeTranslator(lambda text: "lixo")
        item = prose("Use --all here. And --now there.")
        (outcome,) = translator.translate_all([item])
        assert not outcome.translated
        assert outcome.text == item.text
        assert outcome.reason == "2 de 2 sentenças rejeitadas"

    def test_ordem_preservada_no_lote(self) -> None:
        translator = FakeTranslator(lambda text: text.upper())
        items = [prose(f"Segment number {n} here.") for n in range(12)]
        outcomes = translator.translate_all(items)
        for number, outcome in enumerate(outcomes):
            assert f"NUMBER {number} " in outcome.text

    def test_mistura_de_literal_e_prosa(self) -> None:
        translator = FakeTranslator(lambda text: text.upper())
        items = [literal("cmd -x"), prose("Some text."), literal("cmd -y")]
        outcomes = translator.translate_all(items)
        assert [o.translated for o in outcomes] == [False, True, False]
        assert outcomes[0].text == "cmd -x"

    def test_translate_segment_delega(self) -> None:
        translator = FakeTranslator(lambda text: text.upper())
        outcome = translator.translate_segment(prose("Some text."))
        assert outcome.translated

    def test_lista_vazia(self) -> None:
        assert FakeTranslator(lambda t: t).translate_all([]) == []

    def test_glossario_aplicado_antes_do_restore(self) -> None:
        """O termo volta ao inglês; o placeholder continua restaurado."""
        translator = FakeTranslator(lambda text: text.replace("Open", "abra a tomada"))
        (outcome,) = translator.translate_all([prose("Open --all now.")])
        assert "socket" in outcome.text
        assert "--all" in outcome.text


class TestGuardaDeVocabulario:
    """O exemplo mudou na fase 5, e a mudança é o resultado da fase.

    Estes testes usavam `{a|b}` como texto fora do vocabulário. A fase 3.1
    tinha medido que 64 dos 71 segmentos com pedaço desconhecido eram buraco
    de **cobertura** do mascaramento, não de vocabulário — e a fase 5 fechou
    essa cobertura: `{a|b}` agora vira placeholder e nunca chega ao tokenizer.
    O exemplo passou a ser o bullet, que é buraco de vocabulário de verdade e
    continua sem solução por mascaramento.
    """

    def test_segmento_com_oov_nao_vai_ao_modelo(self) -> None:
        """Se o tokenizer não conhece o pedaço, o modelo devolveria ⁇."""
        called: list[str] = []

        def behaviour(text: str) -> str:
            called.append(text)
            return text

        translator = FakeTranslator(behaviour, oov=["•"])
        (outcome,) = translator.translate_all([prose("Use • to pick.")])
        assert not outcome.translated
        assert outcome.reason == "oov"
        assert outcome.text == "Use • to pick."
        assert called == []  # nenhuma inferência gasta

    def test_segmento_sem_oov_passa(self) -> None:
        translator = FakeTranslator(lambda text: text.upper(), oov=["•"])
        (outcome,) = translator.translate_all([prose("Plain sentence here.")])
        assert outcome.translated

    def test_oov_nao_impede_os_outros(self) -> None:
        translator = FakeTranslator(lambda text: text.upper(), oov=["•"])
        outcomes = translator.translate_all(
            [prose("Use • now."), prose("Plain sentence here.")]
        )
        assert [o.reason for o in outcomes] == ["oov", None]
        assert [o.translated for o in outcomes] == [False, True]


class TestDiagnosticoDeOOV:
    def test_metacaractere_e_buraco_de_cobertura(self) -> None:
        # Com espaço dentro, o grupo escapa do padrão da fase 5 e continua
        # chegando ao tokenizer — é o que sobrou de buraco de cobertura.
        translator = FakeTranslator(lambda t: t, oov=["{", "|"])
        pieces, coverage = translator.oov_diagnosis("a {x | y} b")
        assert pieces and coverage

    def test_tipografia_e_buraco_de_vocabulario(self) -> None:
        """Um bullet no meio da frase não se resolve mascarando."""
        translator = FakeTranslator(lambda t: t, oov=["•"])
        pieces, coverage = translator.oov_diagnosis("• item da lista")
        assert pieces and not coverage

    def test_mistura_conta_como_vocabulario(self) -> None:
        translator = FakeTranslator(lambda t: t, oov=["{", "•"])
        _, coverage = translator.oov_diagnosis("• use {x}")
        assert not coverage

    def test_sem_oov(self) -> None:
        translator = FakeTranslator(lambda t: t)
        assert translator.oov_diagnosis("texto limpo") == ([], False)


class TestValidacaoEstruturalNoFluxo:
    def test_frase_sumida_manda_para_o_caminho_de_sentenca(self) -> None:
        """validate aprovaria o parágrafo: não há placeholder para perder.

        A regra de contagem reprova, e a recuperação por sentença salva as
        duas frases — que é exatamente o comportamento desejado.
        """

        def behaviour(text: str) -> str:
            if len(split_sentences(text)[0::2]) > 1:
                return "Só uma frase."  # o parágrafo perde uma
            return text.upper()

        translator = FakeTranslator(behaviour)
        item = prose("First sentence. Second sentence.")
        (outcome,) = translator.translate_all([item])
        assert outcome.translated
        assert "FIRST SENTENCE." in outcome.text
        assert "SECOND SENTENCE." in outcome.text

    def test_frase_sumida_sem_recuperacao_sai_em_ingles(self) -> None:
        translator = FakeTranslator(lambda text: "Só uma frase. E outra. E mais.")
        item = prose("First sentence. Second sentence.")
        (outcome,) = translator.translate_all([item])
        assert not outcome.translated
        assert outcome.text == item.text

    def test_repeticao_derruba(self) -> None:
        translator = FakeTranslator(lambda text: "Igual. Igual.")
        item = prose("First one. Second one.")
        (outcome,) = translator.translate_all([item])
        assert not outcome.translated

    def test_unk_na_saida_derruba(self) -> None:
        translator = FakeTranslator(lambda text: "Texto com \u2047 dentro.")
        (outcome,) = translator.translate_all([prose("Some text here.")])
        assert not outcome.translated

    def test_colchete_perdido_derruba(self) -> None:
        translator = FakeTranslator(lambda text: text.replace("]", ""))
        (outcome,) = translator.translate_all([prose("Use OPTION] here.")])
        assert not outcome.translated


class TestCache:
    def test_repetido_nao_vai_duas_vezes_ao_modelo(self) -> None:
        calls: list[str] = []

        def behaviour(text: str) -> str:
            calls.append(text)
            return text.upper()

        translator = FakeTranslator(behaviour)
        items = [prose("Show summary of options.") for _ in range(5)]
        outcomes = translator.translate_all(items)
        assert len(calls) == 1
        assert all(o.translated for o in outcomes)
        assert translator.cache_hits == 4
        assert translator.cache_misses == 1

    def test_cache_atravessa_chamadas(self) -> None:
        calls: list[str] = []

        def behaviour(text: str) -> str:
            calls.append(text)
            return text.upper()

        translator = FakeTranslator(behaviour)
        translator.translate_all([prose("Uma frase.")])
        translator.translate_all([prose("Uma frase.")])
        assert len(calls) == 1
        assert translator.cache_hits == 1


class TestBeam:
    def test_default_e_um(self) -> None:
        from manbr.translate import BEAM_SIZE

        assert BEAM_SIZE == 1
        assert Translator(Path("/x"))._beam_size == 1

    def test_configuravel(self) -> None:
        assert Translator(Path("/x"), beam_size=4)._beam_size == 4


class TestCargaPreguicosa:
    def test_construir_nao_carrega(self) -> None:
        translator = Translator(Path("/nao/existe"))
        assert not translator.loaded

    def test_lista_vazia_nao_carrega(self) -> None:
        translator = Translator(Path("/nao/existe"))
        translator.translate_all([])
        assert not translator.loaded

    def test_checar_oov_nao_carrega_os_pesos(self) -> None:
        """O sentencepiece é barato; os 228 MB de pesos não."""
        translator = FakeTranslator(lambda t: t, oov=["{"])
        translator.translate_all([prose("Use {x} now.")])
        assert not translator.loaded

    def test_so_literais_nao_carrega(self) -> None:
        """Uma página inteira de bloco literal não deve custar o modelo."""
        translator = Translator(Path("/nao/existe"))
        outcomes = translator.translate_all([literal("cmd -x"), literal("cmd -y")])
        assert not translator.loaded
        assert all(not o.translated for o in outcomes)


# --------------------------------------------------------------------------
# Com o modelo de verdade
# --------------------------------------------------------------------------


@pytest.fixture(scope="module")
def translator() -> Translator:
    """Um só modelo carregado para todos os testes que precisam dele."""
    return Translator(model_path())


@needs_model
class TestComModelo:
    def test_traduz_frase_simples(self, translator: Translator) -> None:
        (outcome,) = translator.translate_all([prose("Show summary of options.")])
        assert outcome.translated
        assert outcome.text != "Show summary of options."
        assert "opções" in outcome.text.lower()

    def test_preserva_placeholders(self, translator: Translator) -> None:
        item = prose("Write output to /tmp/saida.txt instead of stdout.")
        (outcome,) = translator.translate_all([item])
        assert "/tmp/saida.txt" in outcome.text

    def test_flag_sobrevive(self, translator: Translator) -> None:
        item = prose("Use --verbose to print more information.")
        (outcome,) = translator.translate_all([item])
        assert "--verbose" in outcome.text

    def test_literal_nao_passa_pelo_modelo(self, translator: Translator) -> None:
        item = literal("rsync -avz foo:src/bar/ /data/tmp")
        (outcome,) = translator.translate_all([item])
        assert outcome.text == item.text
        assert not outcome.translated
