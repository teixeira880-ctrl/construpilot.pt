"""Orçamento a partir do mapa DWFX : mesmas quantidades, capítulo + piso, linhas «a medir» listadas e nunca inventadas."""
import asyncio
import sys
import types

from routes import assistant as A

LINHAS = [
    {"capitulo": "Movimento de terras", "piso": "Cave", "designacao": "Escavação geral até à cota 100,40", "descricao": "395,29 × 5,34", "qtd": 2112.6, "un": "m³"},
    {"capitulo": "Estrutura", "piso": "Laje cota 103,86", "designacao": "Laje maciça — betão", "descricao": "…", "qtd": 40.5, "un": "m³"},
    {"capitulo": "Estrutura", "piso": "Laje cota 103,86", "designacao": "Reforços «Ø af. L=» sem número de varões", "descricao": "…", "qtd": None, "un": "kg"},
    {"capitulo": "Alvenarias", "piso": "R/C", "designacao": "Parede exterior (fachada)", "descricao": "…", "qtd": 120.0, "un": "m²"},
]


def _patch(monkeypatch, guardado):
    async def mapa(name, args, user, conv, db):
        return {"ok": True, "resumo": {}, "artifacts": [{"artifact_id": "art_mapa"}], "_linhas": [dict(l) for l in LINHAS],
                "_nao": [{"capitulo": "Estrutura", "designacao": "Pilares"}]}

    async def save_quote(a, user, conv):
        guardado.extend(a["lines"])
        return {"doc_id": "q1", "draft": {"lines": [{"designation": l["designation"], "price_source": "reference_cype"} for l in a["lines"]],
                                          "total_ht": 1000.0, "total_tva": 230.0, "total_ttc": 1230.0}}

    async def with_exports(res, user, conv):
        return {**res, "artifacts": [{"artifact_id": "art_orc"}]}

    monkeypatch.setattr(A, "execute_mapa_arq_tool", mapa)
    monkeypatch.setitem(sys.modules, "engines.assistant_quote_service",
                        types.SimpleNamespace(save_quote=save_quote, append_quote_lines=None))
    monkeypatch.setitem(sys.modules, "engines.assistant_quote_exports", types.SimpleNamespace(with_exports=with_exports))


def test_so_estrutura_usa_as_quantidades_do_mapa(monkeypatch):
    g = []
    _patch(monkeypatch, g)
    r = asyncio.run(A._orcamento_mapa_dwfx({"document_ids": ["doc_dw"], "documentos_estrutura": ["doc_e"], "so_estrutura": True},
                                          {"user_id": "u"}, {}))
    assert [l["designation"] for l in g] == ["Escavação geral em terreno com meios mecânicos, incluindo carga",
                                             "Betão (classe do projeto) em lajes, bombeado e vibrado"]
    assert g[0]["description"].startswith("Escavação geral até à cota 100,40 — Cave")     # o elemento do mapa fica na linha
    assert g[0]["quantity"] == 2112.6 and g[0]["unit"] == "m3" and g[0]["lot"] == "Movimento de terras — Cave"
    assert all(l["price_origin"] == "library" and l["unit_price"] is None for l in g)       # preço pela cascata, nunca inventado
    assert any("sem número de varões" in x for x in r["resumo"]["a_medir_sem_quantidade"])
    assert {a["artifact_id"] for a in r["artifacts"]} == {"art_orc", "art_mapa"}


def test_tudo_inclui_alvenarias(monkeypatch):
    g = []
    _patch(monkeypatch, g)
    asyncio.run(A._orcamento_mapa_dwfx({"document_ids": ["doc_dw"]}, {"user_id": "u"}, {}))
    assert "Parede exterior (fachada)" in [l["designation"] for l in g] and len(g) == 3


def test_artigos_de_preco_estruturais():
    assert A._artigo_preco("Pilar 0,25 × 0,50 — betão", "m3") == "Betão (classe do projeto) em pilares, bombeado e vibrado"
    assert A._artigo_preco("Muro M1 — aço Ø12 af.0,20 (L=3,2)", "kg").startswith("Aço em varão nervurado")
    assert A._artigo_preco("Sapata 1,6 × 1,6 × 0,5 m — betão de limpeza 0,10 m", "m3").startswith("Betão de limpeza")
    assert A._artigo_preco("Cofragem de laje (fundo)", "m2").startswith("Cofragem de lajes")
    assert A._artigo_preco("Escavação geral até à cota 100,40", "m3").startswith("Escavação geral")
    assert A._artigo_preco("Parede exterior (fachada)", "m2") is None


def test_quantidades_totais_antes_do_orcamento(monkeypatch):
    g = []
    _patch(monkeypatch, g)
    r = asyncio.run(A._orcamento_mapa_dwfx({"document_ids": ["doc_dw"]}, {"user_id": "u"}, {}))
    tot = {t["quantidade"]: t for t in r["quantidades_totais"]}
    assert tot["Betão"]["total"] == 40.5 and tot["Betão"]["unidade"] == "m3"
    assert "Escavação geral em terreno com meios mecânicos, incluindo carga" in tot
    assert tot["Alvenarias — Parede exterior"]["total"] == 120.0
    assert list(tot)[0].startswith("Escavação")                      # ordem : terras, betão, aço, cofragem…
    assert r["instrucao"].startswith("PRIMEIRO as quantidades")
    assert "QUANTIDADES PRIMEIRO" in A.QUANTIDADES_PRIMEIRO
