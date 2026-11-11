"""Agente de estudo CLT do Assistente: ferramentas, cadeia de motores, verificações cruzadas e travão do dossier."""
import asyncio
import base64
import copy
import os

import fitz
import pytest
from jsonschema import Draft202012Validator

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "test")

from bim_studio.clt_economics import library_merged, merged  # noqa: E402
from engines import assistant_clt_agent as ag  # noqa: E402


def W(id, x1, y1, x2, y2, t=100):
    return {"id": id, "x1": x1, "y1": y1, "x2": x2, "y2": y2, "thickness_mm": t, "layers": 5, "height_m": 3.0, "base_z_m": 0.0,
            "openings": [], "source": "teste"}


def house_doc():
    """RDC 10 × 8 m with an interior T wall; Piso 1 over the same outline."""
    rdc = [W("R1", 0, 0, 10, 0), W("R2", 10, 0, 10, 8), W("R3", 10, 8, 0, 8), W("R4", 0, 8, 0, 0), W("R5", 5, 0, 5, 8)]
    p1 = [W("P1", 0, 0, 10, 0), W("P2", 10, 0, 10, 8), W("P3", 10, 8, 0, 8), W("P4", 0, 8, 0, 0), W("P5", 0, 4, 10, 4)]
    rooms = lambda tag: [{"nome": f"Sala {tag}", "tipo": "sala", "rect_m": [0, 0, 5, 8], "area_m2": None, "aparelhos": []},
                         {"nome": f"WC {tag}", "tipo": "casa_de_banho", "rect_m": [5, 0, 10, 8], "area_m2": None,
                          "aparelhos": ["lavatorio", "autoclismo", "chuveiro"]}]
    vaos = [{"largura_m": 1.2, "tipo": "janela", "sobre": "lintel"}]
    return {"revisao": 3, "registo": [], "pisos": {
        "RDC": {"nome": "RDC", "ordem": 0, "altura_m": None, "paredes": rdc, "linteis": [], "divisoes": rooms("0"), "vaos": vaos,
                "portas_interiores": 1},
        "Piso 1": {"nome": "Piso 1", "ordem": 1, "altura_m": None, "paredes": p1, "linteis": [], "divisoes": rooms("1"), "vaos": vaos,
                   "portas_interiores": 1}}}


def test_tool_schemas_are_strict_and_valid():
    for t in ag.TOOLS:
        Draft202012Validator.check_schema(t["parameters"])

        def strict(s):
            if s.get("properties"):
                assert set(s["required"]) == set(s["properties"]), t["name"]
                assert s.get("additionalProperties") is False, t["name"]
                for v in s["properties"].values():
                    strict(v)
            if isinstance(s.get("items"), dict):
                strict(s["items"])
        strict(t["parameters"])
    assert set(ag.STATUS) == ag.NAMES


def test_chain_on_a_clean_house_passes_with_standard_heights():
    params, lib = merged({}), library_merged({})
    out = ag.run_chain(house_doc(), params, lib)
    failed = {c["id"]: c for c in out["checks"] if not c["ok"]}
    assert not [c for c in failed.values() if c["nivel"] == "bloqueante"], failed
    floors = out["entrada"]["floors"]
    # no height on the plan → company standard (RDC 3.00 m, others 2.50 m), left empty so the estimate notes it
    assert [f["height_m"] for f in floors] == [None, None]
    assert out["orcamento"]["pisos"][0]["altura_m"] == 3.0 and out["orcamento"]["pisos"][1]["altura_m"] == 2.5
    # slab of the upper floor and roof derived from the outline, flagged as hypotheses
    kinds = {(f["name"], p["kind"]) for f in floors for p in f["panels"]}
    assert ("Piso 1", "laje") in kinds and ("Piso 1", "cobertura") in kinds and ("RDC", "cobertura") not in kinds
    assert any("laje" in h and "hipótese" in h for h in out["hipoteses_geometria"])
    assert out["orcamento"]["total"]["receita_eur"] > 0
    assert any(c["id"] == "ifc_opencascade" and c["ok"] for c in out["checks"])


def test_duplicated_wall_is_caught_by_the_cross_check():
    doc = house_doc()
    doc["pisos"]["RDC"]["paredes"].append(W("R6", 0, 0.0, 10, 0.0))   # the same façade read twice
    out = ag.run_chain(doc, merged({}), library_merged({}))
    bad = [c for c in out["checks"] if not c["ok"] and c["nivel"] == "bloqueante"]
    assert bad, "a duplicated wall must block the dossier"


def test_rooms_outside_the_outline_and_missing_windows_are_flagged():
    doc = house_doc()
    doc["pisos"]["RDC"]["divisoes"].append({"nome": "Erro", "tipo": "quarto", "rect_m": [0, 0, 10, 8], "area_m2": None, "aparelhos": []})
    doc["pisos"]["RDC"]["vaos"] = []
    out = ag.run_chain(doc, merged({}), library_merged({}))
    failed = {c["id"] for c in out["checks"] if not c["ok"]}
    assert "divisoes_dentro_do_contorno[RDC]" in failed and "vaos_definidos[RDC]" in failed


def test_next_step_follows_the_method():
    doc = {"revisao": 0, "pisos": {}, "registo": []}
    assert "ler_planta" in ag.next_step(doc)
    doc = house_doc()
    assert "calcular" in ag.next_step(doc)
    doc["verificacao"] = {"revisao": 3, "checks": [{"id": "x", "ok": False, "nivel": "bloqueante", "como_corrigir": "y"}]}
    assert "bloqueantes" in ag.next_step(doc)
    doc["verificacao"]["checks"] = []
    assert "dossier" in ag.next_step(doc)


class _Col:
    def __init__(self):
        self.docs = {}

    async def find_one(self, q, *a, **k):
        d = self.docs.get(q.get("_id"))
        return copy.deepcopy(d) if d and all(d.get(k2) == v for k2, v in q.items()) else None

    async def replace_one(self, q, doc, upsert=False):
        self.docs[q["_id"]] = copy.deepcopy(doc)

    async def delete_one(self, q):
        self.docs.pop(q["_id"], None)


class _DB(dict):
    def __getattr__(self, k):
        return self.setdefault(k, _Col())

    def __getitem__(self, k):
        return self.setdefault(k, _Col())


def test_execute_refuses_the_dossier_until_verified_and_keeps_tenants_apart(monkeypatch):
    import bim_studio.clt_access as access
    monkeypatch.setattr(access, "allowed", lambda user: True)
    db = _DB()
    a, b = {"user_id": "u1", "organization_id": "A"}, {"user_id": "u2", "organization_id": "B"}
    conv = {"conversation_id": "c1"}

    async def run():
        doc = house_doc()
        key = ag._key(a, conv)
        await db[ag.COLLECTION].replace_one(key, {**doc, **key, "conversation_id": "c1"})
        r = await ag.execute("clt_agente_dossier", {"titulo": "T", "local": None, "lingua": None, "empresa": None}, a, conv, db, None)
        assert not r["ok"] and "calcular" in r["error"]
        other = await ag.execute("clt_agente_estado", {"reiniciar": None}, b, conv, db, None)
        assert other["pisos"] == []                              # company B never sees company A's study
        r = await ag.execute("clt_agente_calcular", {"regime_iva": None, "inicio": None, "modo_inicio": None}, a, conv, db, None)
        assert r["ok"] and not r["bloqueantes"], r["bloqueantes"]
        r = await ag.execute("clt_agente_corrigir_paredes", {"piso": "RDC", "remover_ids": ["R5"], "acrescentar": [], "alterar": [],
                                                              "motivo": "curto"}, a, conv, db, None)
        assert not r["ok"]                                       # every correction needs the reason seen on the plan
        r = await ag.execute("clt_agente_corrigir_paredes", {"piso": "RDC", "remover_ids": ["R5"], "acrescentar": [], "alterar": [],
                                                              "motivo": "R5 é um roupeiro na planta, não parede CLT"}, a, conv, db, None)
        assert r["ok"] and r["correcoes"][-1]["removidas"] == ["R5"]
        r = await ag.execute("clt_agente_dossier", {"titulo": "T", "local": None, "lingua": None, "empresa": None}, a, conv, db, None)
        assert not r["ok"]                                       # the study changed: verify again first
    asyncio.run(run())


def _plan_pdf():
    """A 1:50 vector plan: four 100 mm walls drawn as filled rectangles (10 × 8 m outline)."""
    doc = fitz.open()
    page = doc.new_page(width=842, height=595)
    k = 1000 / 50 / (25.4 / 72)          # points per metre at 1:50
    t = 0.1 * k
    for x0, y0, x1, y1 in ((0, 0, 10, 0.1), (0, 7.9, 10, 8), (0, 0.1, 0.1, 7.9), (9.9, 0.1, 10, 7.9)):
        page.draw_rect(fitz.Rect(60 + x0 * k, 60 + y0 * k, 60 + x1 * k, 60 + y1 * k), color=(1, 0, 1), fill=(1, 0, 1))
    page.insert_text((60, 40), "PLANTA RDC 1:50")
    assert t > 0
    return doc.tobytes()


def test_read_sheet_returns_walls_and_a_control_image():
    fields, summary, png = ag.read_sheet(_plan_pdf(), "application/pdf", {"pagina": 1, "escala": None, "camadas": None}, 3.0)
    assert summary["escala"] == 50 and len(fields["paredes"]) == 4
    assert png[:8] == b"\x89PNG\r\n\x1a\n"
    total = sum(((w["x2"] - w["x1"]) ** 2 + (w["y2"] - w["y1"]) ** 2) ** .5 for w in fields["paredes"])
    assert total == pytest.approx(2 * 10 + 2 * 7.8, abs=0.01)
    assert base64.b64encode(png)
