"""Dossier de Obra: percurso de demonstração completo (moradia fictícia) e garantias de segurança/compatibilidade.

Base Mongo em memória (mongomock-motor) — sem servidor, sem IA, sem produção."""
import asyncio
import io
import json
import os
import zipfile

import pytest

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "test_dossier_obra")
os.environ.setdefault("JWT_SECRET", "test")
os.environ.setdefault("STUDIES_MODEL_ANALYSIS", "test")
os.environ.setdefault("STUDIES_MODEL_LIGHT", "test")

mm = pytest.importorskip("mongomock_motor")
from fastapi import HTTPException  # noqa: E402

import routes.dossier_obra as R  # noqa: E402
from engines import dossier_obra_catalog as C  # noqa: E402

USER = {"user_id": "u_a", "account_type": "pro", "active": True, "name": "Ana"}
OTHER = {"user_id": "u_b", "account_type": "pro", "active": True}
WORKER = {"user_id": "u_a", "account_type": "pro", "active": True, "organization_id": "org", "org_role": "ouvrier"}


def run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


@pytest.fixture(autouse=True)
def fdb(monkeypatch):
    asyncio.set_event_loop(asyncio.new_event_loop())
    db = mm.AsyncMongoMockClient()["t"]
    import routes.chantiers as CH
    import routes.plans_common as PC
    monkeypatch.setattr(R, "db", db)
    monkeypatch.setattr(CH, "db", db)
    monkeypatch.setattr(PC, "db", db)
    try:
        import routes.assistant as A
        monkeypatch.setattr(A, "db", db)
    except Exception:  # noqa: BLE001
        pass
    import core.environment as E
    monkeypatch.setattr(E, "ENVIRONMENT", "development")
    run(db.users.insert_one({"user_id": "u_a", "name": "Ana"}))
    return db


def demo():
    return run(R.create_demo(user=USER))


def spec(cid, key, **kw):
    return run(R.specialty(cid, key, user=USER, **{"fase": None, "local": None, **kw}))


# ───────── percurso de demonstração (13 passos) ─────────

def test_full_demo_path(fdb):
    d = demo()                                                           # 1. abrir uma moradia
    cid, L = d["chantier_id"], d["locations"]
    ov = run(R.overview(cid, user=USER))
    arq = next(a for a in ov["areas"] if a["key"] == "arquitetura")      # 2. entrar em Arquitetura
    assert "revest_exteriores" in [s["key"] for s in arq["specialties"]]
    assert ov["config"]["global_phase"] == "execucao" and ov["pendencias_total"] >= 3 and ov["next_action"]
    s = spec(cid, "revest_exteriores", fase="execucao", local=L["fn"])  # 3–4. Revestimentos exteriores · Execução · Fachada norte
    assert s["filters"]["local_path"] == "Moradia em L · Fachada norte"
    med = s["by_kind"]["medicao"][0]                                     # 5. planta e origem da medição
    assert med["measurement"]["document"].startswith("Fachadas_P03") and med["measurement"]["page"] == "2"
    assert med["measurement"]["quantity"] == 84.0 and med["measurement"]["scale"] == "1:100" and med["source"] == "extraido"
    mat = s["by_kind"]["material"][0]                                    # 6. confirmar/corrigir um material
    assert mat["validation"] == "por_confirmar" and mat["source"] == "inferido"
    out = run(R.validate_item(cid, mat["item_id"], R.ValidationIn(action="corrigir", layer_order=1, material="Alvenaria de tijolo 15 cm"), user=USER))
    assert out["layers"][0]["material"] == "Alvenaria de tijolo 15 cm" and out["layers"][0]["validation"] == "corrigido" and out["layers"][0]["source"] == "manual"
    out = run(R.validate_item(cid, mat["item_id"], R.ValidationIn(action="confirmar", layer_order=5), user=USER))
    assert out["layers"][4]["validation"] == "confirmado"
    assert [h["action"] for h in out["history"]][-2:] == ["camada_corrigido", "camada_confirmado"]
    pend = next(i for i in s["by_kind"]["pendencia"] if i.get("related_specialty") == "agua")   # 7. pendência ligada a Engenharia
    link = next(dp for dp in s["dependencies"] if dp["other"] == "agua")
    assert link["other_area"] == "engenharia" and link["other_open"] >= 1 and pend["display_status"] == "pendente"
    s2 = spec(cid, "agua", fase="execucao", local=L["fn"])               # 8. abrir a ligação mantendo fase/local
    assert s2["filters"]["fase"] == "execucao" and s2["specialty"]["area"] == "engenharia"
    assert any(dp["other"] == "paredes" for dp in s2["dependencies"])
    ctx = run(R.assistant_context(cid, "u_a", {"specialty": "revest_exteriores", "phase": "execucao", "location_path": "Moradia em L · Fachada norte"}))  # 9.
    assert ctx["especialidade"] == "Fachadas e revestimentos exteriores" and ctx["fase_selecionada"] == "Execução"
    assert any(r.get("medicao", {}).get("quantity") == 84.0 for r in ctx["registos"]) and ctx["dependencias"]
    rep = run(R.preview(cid, R.SelectionIn(scope="especialidade", specialties=["revest_exteriores"]), user=USER))   # 10. relatório da especialidade
    assert rep["title"].startswith("Relatório da especialidade") and rep["measurements"] and rep["materials"]
    sel = R.SelectionIn(scope="global", specialties=["revest_exteriores", "agua", "paredes"])                     # 11. várias especialidades
    pv = run(R.preview(cid, sel, user=USER))                                                                    # 12. pré-visualizar e gerar
    assert [ch["key"] for ch in pv["chapters"]] == ["arquitetura", "engenharia"] and pv["summary"]["pendente"] >= 3
    em = run(R.create_emission(cid, sel, user=USER))
    assert em["version"] == 1 and em["formats"] == ["pdf", "docx", "xlsx", "zip"]
    saved = run(R.get_emission(cid, em["emission_id"], user=USER))                                               # 13. emissão guardada
    assert saved["model"]["emission"]["version"] == 1 and "P03" in " ".join(saved["model"]["revisions"])


def test_assistant_conversation_per_specialty(fdb):
    pytest.importorskip("routes.assistant")
    d = demo()
    cid = d["chantier_id"]
    a = run(R.specialty_assistant(cid, "revest_exteriores", R.AssistantCtxIn(fase="execucao", local=d["locations"]["fn"]), user=USER))
    assert a["label"] == "Assistente BTP · Fachadas e revestimentos exteriores · Execução · Moradia em L · Fachada norte"
    again = run(R.specialty_assistant(cid, "revest_exteriores", R.AssistantCtxIn(fase="execucao"), user=USER))
    other = run(R.specialty_assistant(cid, "agua", R.AssistantCtxIn(), user=USER))
    assert again["conversation_id"] == a["conversation_id"] != other["conversation_id"]
    conv = run(fdb.assistant_convs.find_one({"conversation_id": a["conversation_id"]}))
    assert conv["chantier_id"] == cid and conv["dossier_context"]["specialty"] == "revest_exteriores"
    assert "Factos" in R.ASSISTANT_RULES and "Hipóteses" in R.ASSISTANT_RULES and "pede validação" in R.ASSISTANT_RULES


# ───────── formatos reais ─────────

def test_generated_files_are_real(fdb):
    d = demo()
    cid = d["chantier_id"]
    em = run(R.create_emission(cid, R.SelectionIn(scope="global"), user=USER))

    def body(fmt):
        return run(R.emission_file(cid, em["emission_id"], formato=fmt, user=USER)).body
    pdf = body("pdf")
    from pypdf import PdfReader
    text = "".join(p.extract_text() for p in PdfReader(io.BytesIO(pdf)).pages)
    for needle in ("DOSSIER DE OBRA", "Índice", "Identificação da emissão", "não equivale à validação técnica", "Fachadas_P03", "EXEMPLO DEMONSTRATIVO"):
        assert needle in text, needle
    from docx import Document
    doc = Document(io.BytesIO(body("docx")))
    assert any("Identificação da emissão" in p.text for p in doc.paragraphs)
    from openpyxl import load_workbook
    wb = load_workbook(io.BytesIO(body("xlsx")))
    assert wb.sheetnames[:3] == ["Medições", "Materiais e camadas", "Pendências"]
    assert any(84.0 in [c.value for c in row] for row in wb["Medições"].iter_rows())
    z = zipfile.ZipFile(io.BytesIO(body("zip")))
    names = z.namelist()
    assert "manifesto.json" in names and sum(n.endswith((".pdf", ".docx", ".xlsx")) for n in names) == 3
    assert json.loads(z.read("manifesto.json"))["emissao"]["version"] == 1


def test_emissions_are_preserved_and_frozen(fdb):
    d = demo()
    cid = d["chantier_id"]
    e1 = run(R.create_emission(cid, R.SelectionIn(), user=USER))
    s = spec(cid, "revest_exteriores")
    item = s["by_kind"]["tarefa"][0]
    run(R.update_item(cid, item["item_id"], R.ItemPatch(title="Aprovar amostra (alterado)"), user=USER))
    e2 = run(R.create_emission(cid, R.SelectionIn(), user=USER))
    lst = run(R.list_emissions(cid, user=USER))["emissions"]
    assert [e["version"] for e in lst] == [2, 1]
    m1 = run(R.get_emission(cid, e1["emission_id"], user=USER))["model"]
    titles1 = [it["title"] for ch in m1["chapters"] for sp in ch["specialties"] for it in sp["items"]]
    assert "Aprovar amostra do material" in titles1 and "Aprovar amostra (alterado)" not in titles1
    assert e1["sha256"] != e2["sha256"]


# ───────── modos, informação incompleta, dados antigos ─────────

def test_mode_switch_keeps_same_data(fdb):
    d = demo()
    cid = d["chantier_id"]
    before = spec(cid, "agua")
    assert run(R.get_prefs(user=USER))["mode"] == "guiado"
    run(R.set_prefs(R.PrefIn(mode="tecnico"), user=USER))
    assert run(R.get_prefs(user=USER))["mode"] == "tecnico"
    after = spec(cid, "agua")
    assert before["items"] == after["items"] and run(fdb.dossier_obra_configs.count_documents({})) == 1


def test_incomplete_and_inferred_information(fdb):
    d = demo()
    cid = d["chantier_id"]
    it = run(R.create_item(cid, R.ItemIn(specialty="coberturas", kind="material", title="Telha (não sei qual)", source="inferido",
                                         validation="validado"), user=USER))
    assert it["validation"] == "por_confirmar" and it["display_status"] == "pendente"   # inferido nunca nasce validado
    with pytest.raises(HTTPException) as e:
        run(R.update_item(cid, it["item_id"], R.ItemPatch(approved=True), user=USER))
    assert e.value.status_code == 422
    unknown = run(R.create_item(cid, R.ItemIn(specialty="pavimentos", kind="pendencia", title="Tipo de pavimento: não sei", status="pendente"), user=USER))
    ov = run(R.overview(cid, user=USER))
    assert "pavimentos" in ov["enabled"] and any(p["item_id"] == unknown["item_id"] for p in ov["pendencias"])


def test_work_on_one_specialty_without_configuring_tree(fdb):
    run(fdb.chantiers.insert_one({"chantier_id": "c1", "user_id": "u_a", "name": "Obra já em curso"}))
    ov = run(R.overview("c1", user=USER))
    assert ov["enabled"] == [] and ov["config"].get("_new")
    run(R.update_specialty("c1", "eletricidade", R.SpecStateIn(status="em_curso", stage="executar"), user=USER))
    ov = run(R.overview("c1", user=USER))
    assert ov["enabled"] == ["eletricidade"]


def test_legacy_records_go_to_por_organizar_and_are_classified_by_reference(fdb):
    run(fdb.chantiers.insert_one({"chantier_id": "c1", "user_id": "u_a", "name": "Obra antiga"}))
    run(fdb.plans_takeoff.insert_one({"plan_id": "p1", "user_id": "u_a", "chantier_id": "c1", "filename": "RDC.pdf", "trashed_at": None}))
    run(fdb.pro_documents.insert_one({"doc_id": "q1", "user_id": "u_a", "chantier_id": "c1", "title": "Orçamento", "status": "signed", "doc_type": "quote"}))
    po = run(R.unclassified("c1", user=USER))
    assert {(x["kind"], x["id"]) for x in po["items"]} == {("plan", "p1"), ("document", "q1")}
    run(R.classify("c1", R.ClassifyIn(kind="plan", id="p1", specialty="implantacao"), user=USER))
    assert [x["id"] for x in run(R.unclassified("c1", user=USER))["items"]] == ["q1"]
    plan = run(fdb.plans_takeoff.find_one({"plan_id": "p1"}, {"_id": 0}))
    assert plan == {"plan_id": "p1", "user_id": "u_a", "chantier_id": "c1", "filename": "RDC.pdf", "trashed_at": None}


# ───────── permissões e isolamento ─────────

def test_isolation_between_users(fdb):
    d = demo()
    cid = d["chantier_id"]
    for call in (lambda: R.overview(cid, user=OTHER), lambda: R.specialty(cid, "agua", fase=None, local=None, user=OTHER),
                 lambda: R.create_emission(cid, R.SelectionIn(), user=OTHER), lambda: R.list_emissions(cid, user=OTHER)):
        with pytest.raises(HTTPException) as e:
            run(call())
        assert e.value.status_code == 404
    em = run(R.create_emission(cid, R.SelectionIn(), user=USER))
    with pytest.raises(HTTPException):
        run(R.emission_file(cid, em["emission_id"], formato="pdf", user=OTHER))


def test_financial_information_respects_permissions(fdb):
    d = demo()
    cid = d["chantier_id"]
    sel = R.SelectionIn(include=["medicoes", "financeiro"])
    assert run(R.preview(cid, sel, user=USER))["finance"] is not None
    pv = run(R.preview(cid, sel, user=WORKER))
    assert pv["finance"] is None and any("financeira excluída" in w for w in pv["warnings"])


def test_demo_refused_in_production(fdb, monkeypatch):
    import core.environment as E
    monkeypatch.setattr(E, "ENVIRONMENT", "production")
    with pytest.raises(HTTPException) as e:
        demo()
    assert e.value.status_code == 403


# ───────── alterações, impactos e documentos aprovados ─────────

def test_change_with_impact_requires_confirmation_and_flags_related(fdb):
    d = demo()
    cid = d["chantier_id"]
    med = spec(cid, "revest_exteriores")["by_kind"]["medicao"][0]
    imp = run(R.item_impact(cid, med["item_id"], user=USER))
    assert any(r["specialty"] == "agua" for r in imp["related"])
    patch = R.ItemPatch(measurement=R.MeasurementIn(**{**med["measurement"], "quantity": 80.0}), revision="P04", note="Nova revisão do alçado")
    with pytest.raises(HTTPException) as e:
        run(R.update_item(cid, med["item_id"], patch, user=USER))
    assert e.value.status_code == 409 and e.value.detail["impact"]["related"]
    patch.confirm = True
    out = run(R.update_item(cid, med["item_id"], patch, user=USER))
    assert out["measurement"]["quantity"] == 80.0 and out["flagged_for_review"]
    assert out["history"][-1]["action"] == "nova_revisao" and out["history"][-1]["changes"]["measurement"][0]["quantity"] == 84.0
    flagged = run(fdb.dossier_obra_items.find_one({"item_id": out["flagged_for_review"][0]}))
    assert flagged["needs_review"] is True


def test_item_linked_to_signed_quote_is_protected(fdb):
    run(fdb.chantiers.insert_one({"chantier_id": "c1", "user_id": "u_a", "name": "Obra"}))
    run(fdb.pro_documents.insert_one({"doc_id": "q1", "user_id": "u_a", "chantier_id": "c1", "status": "signed", "doc_type": "quote", "totals": {"ttc": 1000}}))
    it = run(R.create_item("c1", R.ItemIn(specialty="custos", kind="documento", title="Orçamento aceite", ref=R.RefIn(kind="document", id="q1"),
                                          quantities={"orcamentada": 10}), user=USER))
    with pytest.raises(HTTPException) as e:
        run(R.update_item("c1", it["item_id"], R.ItemPatch(quantities={"orcamentada": 12}), user=USER))
    assert e.value.status_code == 409 and "compromisso" in e.value.detail["message"]
    with pytest.raises(HTTPException):
        run(R.archive_item("c1", it["item_id"], user=USER))
    q = run(fdb.pro_documents.find_one({"doc_id": "q1"}, {"_id": 0}))
    assert q["status"] == "signed" and q["totals"] == {"ttc": 1000}           # o orçamento aceite nunca é tocado


def test_quantities_are_distinct_and_validated(fdb):
    run(fdb.chantiers.insert_one({"chantier_id": "c1", "user_id": "u_a", "name": "Obra"}))
    it = run(R.create_item("c1", R.ItemIn(specialty="paredes", kind="medicao", title="Tijolo",
                                          quantities={"medida": 120, "orcamentada": 126, "encomendada": 130, "executada": 60}), user=USER))
    assert it["quantities"] == {"medida": 120.0, "orcamentada": 126.0, "encomendada": 130.0, "executada": 60.0}
    with pytest.raises(HTTPException):
        run(R.create_item("c1", R.ItemIn(specialty="paredes", kind="medicao", title="x", quantities={"total": 1}), user=USER))


def test_dependencies_suggested_then_confirmed(fdb):
    d = demo()
    cid = d["chantier_id"]
    deps = run(R.list_deps(cid, user=USER))
    sug = deps["suggestions"]
    assert sug and all(s["from_specialty"] in C.SPECIALTIES for s in sug)
    proposed = next(x for x in deps["dependencies"] if x["status"] == "proposta")
    out = run(R.confirm_dep(cid, proposed["dep_id"], user=USER))
    assert out["status"] == "confirmada" and out["confirmed_by"] == "Ana"
    with pytest.raises(HTTPException):
        run(R.add_dep(cid, R.DepIn(from_specialty="agua", relation="depende_de", to_specialty="agua"), user=USER))


def test_search_custom_specialties_and_locations(fdb):
    assert C.search("capoto")[0]["key"] == "revest_exteriores"
    assert C.search("tomadas")[0]["key"] == "eletricidade"
    run(fdb.chantiers.insert_one({"chantier_id": "c1", "user_id": "u_a", "name": "Obra"}))
    cs = run(R.add_custom_specialty("c1", R.CustomSpecIn(area="arquitetura", label="Cerâmica exterior", parent="revest_exteriores"), user=USER))
    assert cs["custom"] and cs["parent"] == "revest_exteriores"
    b = run(R.add_location("c1", R.LocationIn(kind="edificio", name="Bloco A"), user=USER))
    p = run(R.add_location("c1", R.LocationIn(kind="piso", name="Piso 1", parent_id=b["location_id"]), user=USER))
    z = run(R.add_location("c1", R.LocationIn(kind="zona", name="Cozinha", parent_id=p["location_id"]), user=USER))
    assert z["path"] == "Bloco A · Piso 1 · Cozinha"
    run(R.create_item("c1", R.ItemIn(specialty=cs["key"], kind="tarefa", title="t", location_id=z["location_id"]), user=USER))
    with pytest.raises(HTTPException) as e:
        run(R.delete_location("c1", z["location_id"], user=USER))
    assert e.value.status_code == 409
    v = run(R.records_view("c1", vista="local", user=USER))
    assert v["groups"][0]["label"] == "Bloco A · Piso 1 · Cozinha"
