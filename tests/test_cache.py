"""Testes do cache em disco."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from babelt.cache import (
    CACHE_FORMAT,
    PIPELINE_VERSION,
    Cache,
    cache_root,
    make_key,
)


@pytest.fixture
def cache(tmp_path: Path) -> Cache:
    return Cache(tmp_path, provenance={"model": "teste", "beam": 1})


class TestLocal:
    def test_respeita_xdg_cache_home(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("XDG_CACHE_HOME", "/tmp/xdg-cache")
        assert cache_root() == Path("/tmp/xdg-cache/babelt")

    def test_padrao_sem_xdg(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("XDG_CACHE_HOME", raising=False)
        assert cache_root() == Path.home() / ".cache/babelt"


class TestChave:
    def test_estavel(self) -> None:
        a = make_key("texto", model="m", beam=1)
        b = make_key("texto", model="m", beam=1)
        assert a == b and len(a) == 64

    @pytest.mark.parametrize(
        ("kwargs_a", "kwargs_b"),
        [
            ({"model": "m", "beam": 1}, {"model": "outro", "beam": 1}),
            ({"model": "m", "beam": 1}, {"model": "m", "beam": 4}),
            (
                {"model": "m", "beam": 1},
                {"model": "m", "beam": 1, "pipeline_version": PIPELINE_VERSION + 1},
            ),
        ],
    )
    def test_muda_com_cada_fator(
        self, kwargs_a: dict[str, object], kwargs_b: dict[str, object]
    ) -> None:
        assert make_key("texto", **kwargs_a) != make_key("texto", **kwargs_b)  # type: ignore[arg-type]

    def test_texto_diferente_chave_diferente(self) -> None:
        assert make_key("a", model="m", beam=1) != make_key("b", model="m", beam=1)

    def test_nao_confunde_concatenacao(self) -> None:
        """Sem separador, ("ab","c") e ("a","bc") colidiriam."""
        assert make_key("ab", model="c", beam=1) != make_key("a", model="bc", beam=1)


class TestLeituraEEscrita:
    def test_ausente_devolve_none(self, cache: Cache) -> None:
        assert cache.get(make_key("nada", model="teste", beam=1)) is None

    def test_ida_e_volta(self, cache: Cache) -> None:
        key = make_key("Show summary.", model="teste", beam=1)
        cache.put(key, "Mostrar resumo.")
        assert cache.get(key) == "Mostrar resumo."

    def test_acentuacao_preservada(self, cache: Cache) -> None:
        key = make_key("x", model="teste", beam=1)
        cache.put(key, "opções, configuração, ⟦0⟧")
        assert cache.get(key) == "opções, configuração, ⟦0⟧"

    def test_sobrescreve(self, cache: Cache) -> None:
        key = make_key("x", model="teste", beam=1)
        cache.put(key, "primeiro")
        cache.put(key, "segundo")
        assert cache.get(key) == "segundo"

    def test_persiste_entre_instancias(self, tmp_path: Path) -> None:
        key = make_key("x", model="teste", beam=1)
        Cache(tmp_path).put(key, "valor")
        assert Cache(tmp_path).get(key) == "valor"

    def test_entrada_corrompida_conta_como_ausencia(self, cache: Cache) -> None:
        """Cache estragado faz traduzir de novo, nunca falhar."""
        key = make_key("x", model="teste", beam=1)
        cache.put(key, "valor")
        path = next(p for p in (cache.root / "entries").rglob("*") if p.is_file())
        path.write_bytes(b"\xff\xfe\x00 bytes invalidos")
        assert cache.get(key) is None


class TestAtomicidade:
    def test_nao_deixa_temporario(self, cache: Cache) -> None:
        cache.put(make_key("x", model="teste", beam=1), "valor")
        leftovers = [
            p for p in cache.root.rglob(".tmp-*") if p.is_file()
        ]
        assert not leftovers

    def test_interrupcao_nao_corrompe(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Ctrl-C no meio da escrita deixa o cache íntegro, com uma entrada
        a menos — nunca com uma entrada pela metade."""
        cache = Cache(tmp_path)
        good = make_key("bom", model="teste", beam=1)
        cache.put(good, "valor bom")

        real_replace = os.replace

        def explode(src: object, dst: object) -> None:
            raise KeyboardInterrupt

        monkeypatch.setattr(os, "replace", explode)
        with pytest.raises(KeyboardInterrupt):
            cache.put(make_key("ruim", model="teste", beam=1), "nunca chega")
        monkeypatch.setattr(os, "replace", real_replace)

        assert cache.get(good) == "valor bom"
        assert cache.get(make_key("ruim", model="teste", beam=1)) is None
        assert not [p for p in cache.root.rglob(".tmp-*") if p.is_file()]


class TestInvalidacao:
    def test_bump_de_pipeline_invalida(self, tmp_path: Path) -> None:
        cache = Cache(tmp_path)
        antigo = make_key("texto", model="m", beam=1, pipeline_version=1)
        cache.put(antigo, "traducao velha")
        novo = make_key("texto", model="m", beam=1, pipeline_version=2)
        assert cache.get(novo) is None
        assert cache.get(antigo) == "traducao velha"  # não apaga nada

    def test_modelo_diferente_nao_acerta(self, tmp_path: Path) -> None:
        cache = Cache(tmp_path)
        cache.put(make_key("t", model="a", beam=1), "x")
        assert cache.get(make_key("t", model="b", beam=1)) is None


class TestMetadados:
    def test_gravados_no_primeiro_put(self, cache: Cache) -> None:
        cache.put(make_key("x", model="teste", beam=1), "v")
        meta = cache.read_meta()
        assert meta["format"] == CACHE_FORMAT
        assert meta["pipeline_version"] == PIPELINE_VERSION
        assert meta["model"] == "teste"
        assert meta["beam"] == 1
        assert meta["created"] and meta["updated"]

    def test_created_preservado_entre_escritas(self, cache: Cache) -> None:
        cache.put(make_key("a", model="teste", beam=1), "v")
        created = cache.read_meta()["created"]
        cache.put(make_key("b", model="teste", beam=1), "v")
        assert cache.read_meta()["created"] == created

    def test_meta_e_json_valido(self, cache: Cache) -> None:
        cache.put(make_key("x", model="teste", beam=1), "v")
        json.loads((cache.root / "meta.json").read_text(encoding="utf-8"))

    def test_sem_cache_meta_vazio(self, tmp_path: Path) -> None:
        assert Cache(tmp_path).read_meta() == {}


class TestEstatisticas:
    def test_contagem(self, cache: Cache) -> None:
        key = make_key("x", model="teste", beam=1)
        assert cache.get(key) is None  # miss
        cache.put(key, "valor")
        assert cache.get(key) == "valor"  # hit
        stats = cache.stats()
        assert (stats.hits, stats.misses, stats.entries) == (1, 1, 1)
        assert stats.bytes == len("valor")
        assert stats.hit_rate == 0.5

    def test_hit_rate_sem_consultas(self, cache: Cache) -> None:
        assert cache.stats().hit_rate == 0.0

    def test_temporario_nao_conta_como_entrada(self, cache: Cache) -> None:
        cache.put(make_key("x", model="teste", beam=1), "v")
        (cache.root / "entries" / ".tmp-solto").write_text("lixo", encoding="utf-8")
        assert cache.stats().entries == 1
