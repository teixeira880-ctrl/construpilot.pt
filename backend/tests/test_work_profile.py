"""Perfil adaptativo, motores por ofício, orçamento guiado e reutilização.

Base isolada (falsa coleção Mongo de test_platform_supervisor); nenhuma chamada a modelos de IA."""
import copy
import importlib
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from engines import trade_calcs as C
from engines import work_profile as W
from routes import documents as D, work_profile as R
from test_platform_supervisor import Database

PAINTER = {"user_id": "pintor1", "account_type": "pro", "organization_id": "org_a", "org_role": "member"}
ENGINEER = {"user_id": "eng1", "account_type": "pro", "organization_id": "org_a", "org_role": "owner"}
OTHER_ORG = {"user_id": "intruso", "account_type": "pro", "organization_id": "org_b", "org_role": "owner"}
PARTICULAR = {"user_id": "part1", "account_type": "particulier"}

SALA = {"name": "Sala", "length_m": 5, "width_m": 4, "height_m": 2.6,
        "openings": [{"width_m": 0.9, "height_m": 2.1}, {"width_m": 1.5, "height_m": 1.2}]}


# --------------------------------------------------------------------------- motores (puros)

def test_paint_formula_is_explicit_and_deducts_openings():
    r = C.paint_calc({"rooms": [SALA], "coats": 2, "yield_m2_per_l": 10, "can_size_l": 15})
    # paredes 18 m × 2,6 = 46,8 ; aberturas 1,89 + 1,8 = 3,69 → 43,11 m²
    assert r["rooms"][0]["walls_net_m2"] == 43.11
    assert r["liters"] == pytest.approx(8.6, abs=0.05)   # 43,11 × 2 ÷ 10
    assert r["cans"] == 1 and r["complete"] is True and r["pending"] == []


def test_paint_unknown_values_are_pending_not_zero():
    r = C.paint_calc({"rooms": [{"name": "Quarto 1", "length_m": 3, "width_m": "nao_sei", "height_m": 2.5}],
                      "coats": None, "yield_m2_per_l": ""})
    assert r["liters"] is None and r["surface_m2"] is None and r["complete"] is False
    assert any("Quarto 1" in p for p in r["pending"]) and "Número de demãos" in r["pending"]
    # sugestão mostrada mas NÃO aplicada
    assert r["coats"] is None and r["suggestions"]["coats"]["value"] == 2


def test_paint_ceiling_and_yield_change_result():
    a = C.paint_calc({"rooms": [{**SALA, "paint_ceiling": True}], "coats": 2, "yield_m2_per_l": 10})
    b = C.paint_calc({"rooms": [{**SALA, "paint_ceiling": True}], "coats": 2, "yield_m2_per_l": 12})
    assert a["surface_m2"] == pytest.approx(63.11)
    assert b["liters"] < a["liters"]


def test_invalid_measurements_are_rejected():
    with pytest.raises(C.CalcError):
        C.paint_calc({"rooms": [{**SALA, "height_m": -2}], "coats": 2, "yield_m2_per_l": 10})
    with pytest.raises(C.CalcError, match="aberturas"):
        C.paint_calc({"rooms": [{"name": "X", "wall_area_m2": 2, "openings": [{"width_m": 2, "height_m": 2}]}],
                      "coats": 1, "yield_m2_per_l": 10})


def test_floor_packages_with_configurable_waste():
    r = C.floor_calc({"length_m": 4, "width_m": 3, "waste_pct": 10, "piece_length_m": 0.6,
                      "piece_width_m": 0.6, "pieces_per_package": 4, "package_price": 20})
    assert r["area_with_waste_m2"] == 13.2 and r["package_m2"] == 1.44
    assert r["packages"] == 10 and r["material_cost"] == 200
    assert C.floor_calc({"area_m2": 12})["packages"] is None


def test_masonry_counts_blocks_and_states_limits():
    r = C.masonry_calc({"wall_length_m": 5, "wall_height_m": 2.5, "block_length_m": 0.5, "block_height_m": 0.2,
                        "joint_m": 0.01, "waste_pct": 5, "openings": [{"width_m": 1, "height_m": 2}]})
    assert r["net_area_m2"] == 10.5 and r["blocks"] == 103
    assert "Não verifica estabilidade" in r["limits"]


def test_quote_lines_flag_missing_prices_and_never_pick_vat():
    out = C.painting_quote_lines({"rooms": [SALA], "coats": 2, "yield_m2_per_l": 10, "crack_repair": True,
                                  "crack_repair_ml": None, "prices": {"labor_per_m2": 8}})
    lines = [ln for ln in out["lines"] if ln["kind"] == "line"]
    assert all(ln["vat_rate"] is None for ln in lines)
    pintura = next(ln for ln in lines if ln["designation"].startswith("Pintura"))
    assert pintura["qty"] == 43.11 and pintura["unit_price_ht"] == 8 and not pintura["price_missing"]
    fissuras = next(ln for ln in lines if "fissuras" in ln["designation"])
    assert fissuras["quantity_missing"] and fissuras["price_missing"]
    assert any("fissuras" in x for x in out["to_confirm"])


# --------------------------------------------------------------------------- perfil

def test_profile_validation_and_no_permission_fields():
    p = W.normalize({"professions": ["engenheiro", "pintor"], "mode": "avancado", "language": "tecnica",
                     "role": "admin", "org_role": "owner", "plan": "business"})
    assert p["professions"] == ["engenheiro", "pintor"] and p["mode"] == "avancado"
    assert not {"role", "org_role", "plan"} & set(p)
    with pytest.raises(W.ProfileError):
        W.normalize({"professions": ["astronauta"]})
    with pytest.raises(W.ProfileError):
        W.normalize({"mode": "turbo"})


def test_profession_suggests_but_never_forces_mode():
    p = W.normalize({"professions": ["engenheiro"], "mode": "guiado"})
    assert p["mode"] == "guiado"
    p2 = W.normalize({"professions": ["pintor"], "mode": "avancado"})
    assert p2["mode"] == "avancado"


def test_visible_tasks_respect_permissions_and_plan():
    from engines.access import meets
    from core.permissions import permissions_for
    prof = W.normalize({"professions": ["encarregado"]})
    member = permissions_for(PAINTER)            # member: sem «chantier»
    keys = [t["key"] for t in W.visible_tasks(prof, member, "pro", meets=meets)]
    assert "obras" not in keys and "diario" not in keys
    owner = permissions_for(ENGINEER)
    keys = [t["key"] for t in W.visible_tasks(prof, owner, "pro", meets=meets)]
    assert "obras" in keys and "diario" not in keys       # diário exige Business
    assert "diario" in [t["key"] for t in W.visible_tasks(prof, owner, "business", meets=meets)]


def test_suggest_from_text_requires_confirmation_semantics():
    assert W.suggest_from_text("Faço pintura de interiores e estuque")[0] == "pintor"


# --------------------------------------------------------------------------- rotas

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
    return database


@pytest.mark.asyncio
async def test_old_account_gets_generic_profile_without_mandatory_onboarding(db):
    home = await R.home(user=PAINTER)
    assert home["profile"]["mode"] == "guiado" and home["show_onboarding"] is True
    assert home["tasks"]   # tarefas genéricas visíveis; nada bloqueado
    await R.put_profile(R.ProfileIn(onboarding="skipped"), user=PAINTER)
    assert (await R.home(user=PAINTER))["show_onboarding"] is False


@pytest.mark.asyncio
async def test_two_members_keep_different_preferences(db):
    await R.put_profile(R.ProfileIn(professions=["pintor"], mode="guiado", language="simples"), user=PAINTER)
    await R.put_profile(R.ProfileIn(professions=["engenheiro"], mode="avancado", language="tecnica"), user=ENGINEER)
    assert (await R.get_profile(user=PAINTER))["mode"] == "guiado"
    eng = await R.get_profile(user=ENGINEER)
    assert eng["mode"] == "avancado" and eng["language"] == "tecnica"
    # mudar de modo não perde o resto do perfil
    await R.put_profile(R.ProfileIn(mode="direto"), user=ENGINEER)
    assert (await R.get_profile(user=ENGINEER))["professions"] == ["engenheiro"]


@pytest.mark.asyncio
async def test_profile_change_never_touches_user_permissions(db):
    db.users.rows = [copy.deepcopy(PAINTER)]
    await R.put_profile(R.ProfileIn(professions=["empreiteiro"], responsibilities=["proprietario"]), user=PAINTER)
    assert db.users.rows[0] == PAINTER


def _job(**prices):
    return {"rooms": [SALA, {"name": "Quarto 1", "length_m": 3, "width_m": 3, "height_m": 2.5}],
            "coats": 2, "yield_m2_per_l": 10, "can_size_l": 15, "crack_repair": False,
            "prices": {"labor_per_m2": 8, "prep_per_m2": 2, "paint_per_can": 60, **prices}}


@pytest.mark.asyncio
async def test_painter_guided_quote_creates_single_draft(db):
    body = R.GuidedQuoteIn(request_id="req-0001-abc", description="O senhor Manuel quer pintar uma sala e dois quartos",
                           client_name="Manuel", address="Rua A, Lisboa", job=_job())
    first = await R.guided_create(body, user=PAINTER)
    again = await R.guided_create(body, user=PAINTER)       # reenvio
    assert again["duplicate"] is True and again["doc_id"] == first["doc_id"]
    docs = db.pro_documents.rows
    assert len(docs) == 1 and docs[0]["status"] == "draft" and docs[0]["number"] is None
    assert docs[0]["source"] == "guided" and docs[0]["project_address"] == "Rua A, Lisboa"
    assert docs[0]["totals"]["ht"] > 0


@pytest.mark.asyncio
async def test_preview_equals_saved_totals_consistency_between_modes(db):
    body = R.GuidedQuoteIn(request_id="req-0002-abc", job=_job())
    preview = await R.guided_preview(body, user=PAINTER)
    saved = await R.guided_create(body, user=PAINTER)
    assert preview["totals"]["ht"] == saved["totals"]["ht"]
    direct = await R.compute_tool("paint", {"rooms": _job()["rooms"], "coats": 2, "yield_m2_per_l": 10}, user=PAINTER)
    assert direct["surface_m2"] == preview["calc"]["surface_m2"]


@pytest.mark.asyncio
async def test_guided_quote_rejected_for_particular_and_foreign_client(db):
    body = R.GuidedQuoteIn(request_id="req-0003-abc", job=_job())
    with pytest.raises(HTTPException) as e:
        await R.guided_create(body, user=PARTICULAR)
    assert e.value.status_code == 403
    db.clients.rows = [{"client_id": "cli_b", "user_id": "intruso"}]
    with pytest.raises(HTTPException) as e:
        await R.guided_create(R.GuidedQuoteIn(request_id="req-0004-abc", client_id="cli_b", job=_job()), user=PAINTER)
    assert e.value.status_code == 404


@pytest.mark.asyncio
async def test_reuse_copies_structure_not_state_and_isolated(db):
    db.pro_documents.rows = [{
        "doc_id": "doc_src", "user_id": "pintor1", "doc_type": "quote", "number": "ORC-2026-001", "status": "signed",
        "title": "Moradia Silva", "client_id": "cli_1", "payments": [{"amount": 100}], "signature": {"name": "Silva"},
        "lines": [{"kind": "line", "designation": "Pintura", "unit": "m²", "qty": 40, "unit_price_ht": 8,
                   "vat_rate": 23, "vat_confirmed": True, "photos": [{"photo_id": "p"}], "line_id": "l1"}]}]
    out = await R.reuse_document("doc_src", user=PAINTER)
    src = db.pro_documents.rows[0]
    new = next(d for d in db.pro_documents.rows if d["doc_id"] == out["doc_id"])
    assert src["status"] == "signed" and src["number"] == "ORC-2026-001"          # original intacto
    assert new["status"] == "draft" and new["number"] is None and new["client_id"] is None
    assert "payments" not in new and "signature" not in new
    assert new["lines"][0]["photos"] == [] and new["lines"][0]["vat_confirmed"] is False
    assert "preços" in out["review_required"]
    with pytest.raises(HTTPException) as e:
        await R.reuse_document("doc_src", user=OTHER_ORG)
    assert e.value.status_code == 404


@pytest.mark.asyncio
async def test_tool_errors_are_user_readable(db):
    with pytest.raises(HTTPException) as e:
        await R.compute_tool("paint", {"rooms": []}, user=PARTICULAR)
    assert e.value.status_code == 422
    r = await R.compute_tool("floor", {"area_m2": 20, "waste_pct": 8, "package_m2": 2.2}, user=PARTICULAR)
    assert r["packages"] == 10
