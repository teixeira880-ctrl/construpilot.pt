"""Visita à obra, registo diário, trabalhos adicionais e ferramentas de pontos / carpintaria.

Base isolada (falsa coleção Mongo); nenhuma IA nem armazenamento real."""
import importlib
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from engines import field_records as F, trade_calcs as C
from routes import documents as D, field_records as R
from test_platform_supervisor import Database

OWNER = {"user_id": "pintor1", "account_type": "pro"}
OTHER = {"user_id": "intruso", "account_type": "pro"}
WORKER = {"user_id": "ze", "account_type": "pro", "organization_id": "org_a", "org_role": "ouvrier"}
MEMBER = {"user_id": "mb", "account_type": "pro", "organization_id": "org_a", "org_role": "member"}


@pytest.fixture
def db(monkeypatch):
    database = Database()
    monkeypatch.setattr(R, "db", database)
    monkeypatch.setattr(D, "db", database)
    access = importlib.import_module("engines.access")

    async def level(user):
        return "pro" if user.get("account_type") == "pro" else "particulier_gratuit"
    monkeypatch.setattr(access, "compute_level", level)
    from engines import activity
    monkeypatch.setattr(activity, "log", AsyncMock())
    monkeypatch.setattr(D, "normalize_generated_vat", AsyncMock())
    rec = importlib.import_module("engines.activity_crm.record")
    monkeypatch.setattr(rec, "record_activity", AsyncMock())
    site = importlib.import_module("routes.site")

    async def store(photos, folder, uid):
        return [f"stored/{uid}/{folder}/{i}.jpg" for i, _ in enumerate(photos)]
    monkeypatch.setattr(site, "_store_photos", store)
    return database


# --------------------------------------------------------------------------- registo diário (sem IA)

def test_daily_example_from_spec():
    r = F.parse_daily("Hoje fomos dois, colocámos o chão da cozinha e faltou cola.")
    assert r["workers"] == 2 and r["hours"] is None                       # horas nunca inventadas
    assert r["work_done"] == ["colocámos o chão da cozinha"]
    assert r["missing_materials"] == [{"item": "cola", "quantity": None}]  # quantidade nunca inventada
    assert r["requires_confirmation"] is True


def test_daily_keeps_enumerations_and_flags_ambiguity():
    r = F.parse_daily("Estivemos na obra e pintámos a sala e o quarto")
    assert r["workers"] is None and any("pessoas" in a for a in r["ambiguous"])
    assert r["work_done"] == ["pintámos a sala e o quarto"]
    r = F.parse_daily("Eu e o Rui assentámos azulejo das 8h às 17h")
    assert r["workers"] == 2 and r["hours"] == 9 and any("pausa" in a for a in r["ambiguous"])


@pytest.mark.asyncio
async def test_daily_requires_confirmation_and_is_idempotent(db):
    body = R.DailyIn(request_id="dia-req-0001", workers=2, work_done=["Chão da cozinha"],
                     missing_materials=[{"item": "cola"}], photos=["data:image/jpeg;base64,AAAA"])
    with pytest.raises(HTTPException) as e:
        await R.create_daily(body, user=OWNER)
    assert e.value.status_code == 422
    body.confirmed = True
    a = await R.create_daily(body, user=OWNER)
    b = await R.create_daily(body, user=OWNER)
    assert b["duplicate"] and b["log_id"] == a["log_id"] and len(db.field_daily.rows) == 1
    assert a["hours"] is None and a["photos"] == ["stored/pintor1/daily/0.jpg"]
    assert await R.list_daily(user=OTHER) == []


@pytest.mark.asyncio
async def test_field_worker_can_log_but_member_without_rights_cannot(db):
    assert await R.daily_access(user=WORKER) == WORKER
    with pytest.raises(HTTPException) as e:
        await R.daily_access(user=MEMBER)
    assert e.value.status_code == 403


# --------------------------------------------------------------------------- visita

@pytest.mark.asyncio
async def test_visit_summary_and_pending_list(db):
    v = await R.create_visit(R.VisitIn(title="Moradia Manuel", address="Rua A", access="Elevador; chaves com a vizinha",
                                       measures=[{"label": "Sala comprimento", "value": 5, "source": "medido"},
                                                 {"label": "Pé-direito quarto", "value": 2.6, "source": "estimado"},
                                                 {"label": "Corredor", "value": "nao_sei"}],
                                       questions=[{"text": "Cor da tinta?"}], photos=["data:image/jpeg;base64,AAAA"]), user=OWNER)
    assert "Sala comprimento: 5 m (medido no local)" in v["summary"]
    assert "Medida em falta: Corredor" in v["to_confirm"] and "Medida estimada a confirmar: Pé-direito quarto" in v["to_confirm"]
    assert "Pergunta pendente: Cor da tinta?" in v["to_confirm"]
    assert any("proteção" in x for x in v["to_confirm"])
    # resumo editado pelo utilizador é preservado; fotos existentes mantidas
    upd = await R.update_visit(v["visit_id"], R.VisitIn(title="Moradia Manuel", address="Rua A", summary="Resumo meu",
                                                        photos=v["photos"]), user=OWNER)
    assert upd["summary"] == "Resumo meu" and upd["summary_edited"] and upd["photos"] == v["photos"]
    with pytest.raises(HTTPException) as e:
        await R.get_visit(v["visit_id"], user=OTHER)
    assert e.value.status_code == 404


@pytest.mark.asyncio
async def test_visit_rejects_foreign_chantier_and_foreign_photo_paths(db):
    db.chantiers.rows = [{"chantier_id": "ch_b", "user_id": "intruso"}]
    with pytest.raises(HTTPException) as e:
        await R.create_visit(R.VisitIn(chantier_id="ch_b"), user=OWNER)
    assert e.value.status_code == 404
    v = await R.create_visit(R.VisitIn(photos=["stored/intruso/visits/9.jpg"]), user=OWNER)
    assert v["photos"] == []        # um caminho que não é seu nunca é associado


# --------------------------------------------------------------------------- trabalho adicional

@pytest.mark.asyncio
async def test_change_request_preserves_signed_quote(db):
    original = {"doc_id": "doc_ok", "user_id": "pintor1", "doc_type": "quote", "status": "signed", "number": "ORC-7",
                "title": "Pintura Manuel", "client_id": None, "totals": {"ht": 1000.0}, "lines": [{"designation": "x"}]}
    db.pro_documents.rows = [dict(original)]
    body = R.ChangeIn(request_id="alt-req-0001", description="Pintar também o corredor", delay_days=2,
                      lines=[R.ChangeLine(designation="Pintura do corredor", unit="m²", qty=20, unit_price_ht=8),
                             R.ChangeLine(designation="Porta", qty=1)])
    out = await R.create_change_request("doc_ok", body, user=OWNER)
    again = await R.create_change_request("doc_ok", body, user=OWNER)
    assert again["duplicate"] and again["new_doc_id"] == out["new_doc_id"]
    assert db.pro_documents.rows[0] == original                        # original intacto
    assert out["impact"] == {"original_ht": 1000.0, "extra_ht": 160.0, "new_total_ht": 1160.0, "delay_days": 2, "delay_known": True}
    assert "Preço: Porta" in out["to_confirm"]
    new = next(d for d in db.pro_documents.rows if d["doc_id"] == out["new_doc_id"])
    assert new["status"] == "draft" and new["amends_doc_id"] == "doc_ok" and "mantém-se inalterado" in new["notes"]
    assert len(await R.list_change_requests("doc_ok", user=OWNER)) == 1
    with pytest.raises(HTTPException):
        await R.create_change_request("doc_ok", R.ChangeIn(request_id="alt-req-0002", description="abc",
                                                            lines=[R.ChangeLine(designation="x")]), user=OTHER)


def test_change_impact_never_guesses_delay():
    assert F.change_impact({"ht": 100}, 50, None)["delay_known"] is False


# --------------------------------------------------------------------------- ferramentas

def test_points_takeoff_counts_and_states_limits():
    r = C.compute("points", {"trade": "eletricidade", "items": [{"type": "tomada", "qty": 6, "room": "Sala"},
                                                                {"type": "tomada", "qty": 4, "room": "Quarto"},
                                                                {"type": "ponto_luz", "qty": None}], "prices": {"Tomada": 35}})
    assert r["totals"] == {"Tomada": 10.0} and "Quantidade: Ponto de luz (Sem divisão)" in r["pending"]
    assert "Não dimensiona" in r["limits"]
    with pytest.raises(C.CalcError):
        C.compute("points", {"trade": "gas", "items": [{"type": "x", "qty": 1}]})


def test_carpentry_sheets_edges_hardware():
    r = C.compute("carpentry", {"pieces": [{"name": "Lateral", "length_m": 2, "width_m": 0.6, "qty": 2, "material": "MDF 19",
                                            "edges_m": 2.6, "hardware": [{"name": "Dobradiça", "qty": 2}]}],
                                "waste_pct": 15, "sheet_m2": 5.06})
    assert r["materials"][0]["area_with_waste_m2"] == 2.76 and r["materials"][0]["sheets"] == 1
    assert r["edge_banding_ml"] == 5.2 and r["hardware"] == {"Dobradiça": 4.0}
    assert C.compute("carpentry", {"pieces": [{"length_m": 1, "width_m": 1}]})["complete"] is False


# --------------------------------------------------------------------------- projeto → processo de obra (explícito)

@pytest.mark.asyncio
async def test_chantier_from_project_is_explicit_idempotent_and_isolated(db, monkeypatch):
    from routes import chantiers as CH
    monkeypatch.setattr(CH, "db", db)
    db.projects.rows = [{"project_id": "prj_1", "user_id": "pintor1", "name": "Moradia Manuel", "budget": 9000}]
    a = await CH.chantier_from_project("prj_1", user=OWNER)
    b = await CH.chantier_from_project("prj_1", user=OWNER)
    assert b["already_linked"] and b["chantier_id"] == a["chantier_id"] and len(db.chantiers.rows) == 1
    assert db.projects.rows[0]["budget"] == 9000 and db.projects.rows[0]["chantier_id"] == a["chantier_id"]
    with pytest.raises(HTTPException) as e:
        await CH.chantier_from_project("prj_1", user=OTHER)
    assert e.value.status_code == 404
