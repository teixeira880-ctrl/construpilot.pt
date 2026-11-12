"""Rotas da geometria v3, de ponta a ponta, sobre uma base Mongo em memória (sem servidor nem base real).

Percurso: planta importada (PDF vetorial real do banco de ensaio) → análise → correção → aplicar às medições →
as divisões criadas usam a MESMA fórmula da app (pontos + calibração) e a calibração criada é a escala lida.
"""
import pytest

pytest.importorskip("mongomock_motor")
from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from mongomock_motor import AsyncMongoMockClient  # noqa: E402

from engines.geometria.banco import PASTA  # noqa: E402

USER = {"user_id": "u_geo", "role": "user", "email": "geo@test", "active": True}
ADMIN = {"user_id": "u_admin", "role": "admin", "email": "adm@test", "active": True}


@pytest.fixture()
def cliente(monkeypatch):
    import asyncio
    import os
    os.environ.setdefault("JWT_SECRET", "segredo-de-teste")   # só para importar core.security fora do servidor
    from core import security
    from engines.plan_processor import process_upload
    from routes import plans_common, plans_geometria
    db = AsyncMongoMockClient()["geo_test"]
    monkeypatch.setattr(plans_geometria, "db", db)
    monkeypatch.setattr(plans_common, "db", db)
    parsed = process_upload((PASTA / "casa_a.pdf").read_bytes(), "casa_a.pdf", "application/pdf")
    asyncio.get_event_loop_policy().new_event_loop().run_until_complete(db.plans_takeoff.insert_one(
        {"plan_id": "pl_geo", "user_id": USER["user_id"], "kind": "pdf", "filename": "casa_a.pdf",
         "pages": parsed["pages"], "page_count": 1, "calibrations": {}, "rooms": [], "measurements": []}))
    app = FastAPI()
    app.include_router(plans_common.router, prefix="/api")
    app.include_router(plans_geometria.admin_router, prefix="/api")
    atual = {"u": USER}
    app.dependency_overrides[security.current_user] = lambda: atual["u"]
    c = TestClient(app)
    c.atual = atual
    c.db = db
    return c


def test_percurso_completo(cliente):
    r = cliente.post("/api/takeoffs/pl_geo/geometria?page_index=0")
    assert r.status_code == 200, r.text
    a = r.json()
    assert a["ok"] and a["fonte"] == "pdf_vetorial" and a["escala"]["estado"] == "confirmada"
    assert len(a["divisoes"]) == 5 and a["confianca"]["nivel_global"] == "verde"
    assert {d["nome"] for d in a["divisoes"]} == {"Sala", "Cozinha", "Quarto 1", "Quarto 2", "Instalação sanitária"}
    # releitura guardada
    assert cliente.get("/api/takeoffs/pl_geo/geometria?page_index=0").json()["versao"] == a["versao"]
    # correção do utilizador → coleção de treino
    d0 = a["divisoes"][0]
    r = cliente.post("/api/takeoffs/pl_geo/geometria/correcao", json={"page_index": 0, "tipo": "area_errada",
                                                                       "divisao_id": d0["id"], "area_correta_m2": 12.0})
    assert r.status_code == 200, r.text
    assert cliente.post("/api/takeoffs/pl_geo/geometria/correcao", json={"page_index": 0, "tipo": "forma_errada", "divisao_id": "D99"}).status_code == 404
    # aplicar: cria as divisões e a calibração (escala lida), com a fórmula da app
    r = cliente.post("/api/takeoffs/pl_geo/geometria/aplicar", json={"page_index": 0, "divisoes": []})
    assert r.status_code == 200, r.text
    assert r.json()["aplicadas"] == 5 and r.json()["calibracao_criada"]
    import asyncio
    doc = asyncio.get_event_loop_policy().new_event_loop().run_until_complete(cliente.db.plans_takeoff.find_one({"plan_id": "pl_geo"}))
    salas = {x["name"]: x for x in doc["rooms"]}
    assert salas["Sala"]["surface_m2"] == pytest.approx(27.494, abs=.01)
    assert salas["Sala"]["origem"] == "geometria_v3" and salas["Sala"]["confianca"] == "verde"
    assert doc["calibrations"]["0"]["source"] == "geometria_v3"
    # reaplicar substitui só as divisões automáticas (não duplica)
    cliente.post("/api/takeoffs/pl_geo/geometria/aplicar", json={"page_index": 0, "divisoes": [a["divisoes"][1]["id"]]})
    doc = asyncio.get_event_loop_policy().new_event_loop().run_until_complete(cliente.db.plans_takeoff.find_one({"plan_id": "pl_geo"}))
    assert len(doc["rooms"]) == 1
    # exportação admin das correções
    assert cliente.get("/api/admin/geometria/correcoes").status_code == 403
    cliente.atual["u"] = ADMIN
    exp = cliente.get("/api/admin/geometria/correcoes").json()
    assert exp["total"] == 1 and exp["por_tipo"] == {"area_errada": 1} and "user_id" not in exp["correcoes"][0]


def test_planta_de_outro_utilizador(cliente):
    cliente.atual["u"] = {**USER, "user_id": "intruso"}
    assert cliente.post("/api/takeoffs/pl_geo/geometria").status_code == 404
    assert cliente.post("/api/takeoffs/pl_geo/geometria/aplicar", json={"page_index": 0}).status_code == 404


def test_aplicar_sem_analise(cliente):
    assert cliente.post("/api/takeoffs/pl_geo/geometria/aplicar", json={"page_index": 0}).status_code == 409


def test_calibracao_divergente_bloqueia_aplicar(cliente):
    import asyncio
    loop = asyncio.get_event_loop_policy().new_event_loop()
    cliente.post("/api/takeoffs/pl_geo/geometria")
    loop.run_until_complete(cliente.db.plans_takeoff.update_one({"plan_id": "pl_geo"},
                                                                {"$set": {"calibrations.0": {"pixels_per_meter": 50.0}}}))
    assert cliente.post("/api/takeoffs/pl_geo/geometria/aplicar", json={"page_index": 0}).status_code == 409


# ---------------------------------------------------------------- Assistente BTP / Aurora

def test_assistente_le_aplica_e_corrige(cliente):
    """As ferramentas do Assistente (usadas também pela Aurora via assistant_ask) chamam as mesmas funções que o ecrã."""
    import asyncio
    from engines import assistant_geometria as AG
    loop = asyncio.get_event_loop_policy().new_event_loop()
    run = lambda n, a: loop.run_until_complete(AG.execute(n, a, USER))  # noqa: E731
    r = run("ler_geometria_planta", {"plan_id": "pl_geo", "page_index": 0})
    assert r["ok"] and r["escala"]["estado"] == "confirmada" and len(r["divisoes"]) == 5
    assert "poligono_px" not in r["divisoes"][0]                     # resposta compacta para o modelo
    assert r["ecra"] == "/plan?open=pl_geo&tab=divisoes&page=0"
    sala = next(d for d in r["divisoes"] if d["nome"] == "Sala")
    assert sala["area_m2"] == pytest.approx(27.494, abs=.01) and sala["nivel"] == "verde"
    ap = run("aplicar_geometria_planta", {"plan_id": "pl_geo", "page_index": 0, "divisoes": [sala["id"]]})
    assert ap["ok"] and ap["aplicadas"] == 1
    c = run("corrigir_geometria_planta", {"plan_id": "pl_geo", "page_index": 0, "tipo": "area_errada", "divisao_id": sala["id"],
                                          "nome_correto": None, "area_correta_m2": 27.0, "comentario": "medido em obra"})
    assert c["ok"]
    # erros devolvidos ao modelo em vez de rebentar a conversa
    assert run("ler_geometria_planta", {"plan_id": "pl_inexistente", "page_index": 0}) == {"ok": False, "error": "Planta não encontrada"}
    assert not run("corrigir_geometria_planta", {"plan_id": "pl_geo", "page_index": 0, "tipo": "area_errada", "divisao_id": None,
                                                 "nome_correto": None, "area_correta_m2": -3, "comentario": None})["ok"]


def test_ferramentas_estritas_e_expostas():
    from engines.assistant_geometria import GEOMETRIA_TOOLS
    for t in GEOMETRIA_TOOLS:
        p = t["parameters"]
        assert t["strict"] and p["additionalProperties"] is False and set(p["required"]) == set(p["properties"])
