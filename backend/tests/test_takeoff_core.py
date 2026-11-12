"""Common take-off methods: the CLT method applied to every system and every company, with the same results."""
import io
import json
import os

import pytest

from engines.takeoff_core import adaptadores, desenhos, dossier, estudo, rede, sistemas

HOME_A = json.load(open(os.path.join(os.path.dirname(__file__), "fixtures", "home_a_eixos_clt.json")))
HEIGHTS = {"RDC": 3.079, "+1": 2.883}  # structural heights of the Home A review (section)


def _clt_floor(name):
    from bim_studio import clt_walls
    return clt_walls.Floor(name=name, walls=[clt_walls.WallAxis(**w, height_m=HEIGHTS[name], layers=5) for w in HOME_A[name]])


@pytest.mark.parametrize("name", ["RDC", "+1"])
def test_same_pieces_as_the_clt_engine_on_home_a(name):
    from bim_studio import clt_walls

    ref = clt_walls.analyse(_clt_floor(name), 18.0)
    floor = rede.Floor(name=name, walls=[rede.WallAxis(**w, height_m=HEIGHTS[name], layers=5, sistema="clt") for w in HOME_A[name]])
    new = rede.analyse(floor, 18.0, 3.5)
    assert [(p["id"], p["comprimento_m"], p["volume_bruto_m3"]) for p in new["pecas"]] == \
           [(p["id"], p["comprimento_m"], p["volume_bruto_m3"]) for p in ref["pecas"]]
    assert new["metodos"] == ref["metodos"]
    assert new["verificacao_volume"]["passed"] and len(new["juntas"]) == len(ref["juntas"])


def test_traditional_system_uses_the_same_geometry_as_clt():
    floors = [{"nome": n, "nivel": i, "altura_m": HEIGHTS[n], "paredes": HOME_A[n], "ligar": False} for i, n in enumerate(("RDC", "+1"))]
    clt = estudo.run(estudo.Project(nome="Home A", sistema="clt", pisos=floors))
    brick = estudo.run(estudo.Project(nome="Home A", sistema="alvenaria_tijolo", pisos=floors))
    geo = lambda r: {(x["codigo"], x["piso"]): x["quantidade"] for f in r["pisos"] for x in f["linhas"] if x["codigo"].startswith("parede_")}  # noqa: E731
    assert geo(clt) == geo(brick)
    assert clt["verificacoes_ok"] and brick["verificacoes_ok"]
    codes = {r["codigo"] for r in brick["totais"]}
    assert {"alvenaria_unidades", "alvenaria_argamassa", "reboco_area"} <= codes and "clt_volume" not in codes
    vol = {f["nome"]: sum(p["volume_bruto_m3"] for p in f["analise"]["pecas"]) for f in clt["pisos"]}
    assert vol["RDC"] == pytest.approx(rede.analyse(rede.Floor(name="RDC", walls=[rede.WallAxis(**w, height_m=3.079) for w in HOME_A["RDC"]]))["metodos"]["volume_pecas_m3"])


def _box(**floor):
    walls = [{"id": "A", "x1": 0, "y1": 0, "x2": 8, "y2": 0, "thickness_mm": 200},
             {"id": "B", "x1": 8, "y1": 0, "x2": 8, "y2": 6, "thickness_mm": 200},
             {"id": "C1", "x1": 8, "y1": 6, "x2": 5, "y2": 6, "thickness_mm": 200},
             {"id": "C2", "x1": 4, "y1": 6, "x2": 0, "y2": 6, "thickness_mm": 200},
             {"id": "D", "x1": 0, "y1": 6, "x2": 0, "y2": 0, "thickness_mm": 200,
              "openings": [{"offset_m": 2, "width_m": 1.2, "sill_m": 0.9, "height_m": 1.2}]}]
    return {"nome": "RDC", "paredes": walls, **floor}


def test_standard_heights_when_the_plan_has_none():
    r = estudo.run(estudo.Project(pisos=[_box(), {**_box(nome="Piso 1", nivel=1), "paredes": [
        {**w, "id": w["id"] + "'"} for w in _box()["paredes"]]}]))
    h = {f["nome"]: f["altura"] for f in r["pisos"]}
    assert h["RDC"]["valor_m"] == 3.0 and h["Piso 1"]["valor_m"] == 2.5 and h["RDC"]["origem"] == "standard"
    assert all(x["origem"] == "estimativa" for f in r["pisos"] for x in f["linhas"] if x["codigo"] == "parede_area_liquida")
    measured = estudo.run(estudo.Project(pisos=[_box(altura_m=2.8, altura_fonte="corte A-A")]))
    assert {x["origem"] for x in measured["pisos"][0]["linhas"] if x["codigo"] == "parede_area_liquida"} == {"medido"}


def test_gap_becomes_an_opening_only_when_no_wall_crosses_it():
    r = estudo.run(estudo.Project(pisos=[_box(altura_m=2.8, inferir_vaos=True)]))
    inferred = r["pisos"][0]["vaos_inferidos"]
    assert len(inferred) == 1 and inferred[0]["largura_m"] == pytest.approx(1.0)
    assert any(p["id"] == "C2+C1" for p in r["pisos"][0]["analise"]["pecas"])
    crossed = _box(altura_m=2.8, inferir_vaos=True)
    crossed["paredes"].append({"id": "E", "x1": 4.5, "y1": 0, "x2": 4.5, "y2": 6, "thickness_mm": 100})
    assert estudo.run(estudo.Project(pisos=[crossed]))["pisos"][0]["vaos_inferidos"] == []


def test_masonry_rule_and_company_values():
    r = estudo.run(estudo.Project(pisos=[_box(altura_m=2.8)]), {"alvenaria_tijolo.perdas_pct": 0, "alvenaria_tijolo.junta_mm": 10,
                                                                 "alvenaria_tijolo.unidade_comprimento_mm": 300,
                                                                 "alvenaria_tijolo.unidade_altura_mm": 200})
    rows = {x["codigo"]: x for x in r["pisos"][0]["linhas"]}
    net = rows["alvenaria_area"]["quantidade"]
    assert rows["alvenaria_unidades"]["quantidade"] == pytest.approx(-(-net / (0.31 * 0.21) // 1))
    assert rows["alvenaria_unidades"]["origem"] == "regra"
    assert rows["alvenaria_argamassa"]["origem"] == "estimativa"  # consumption still a hypothesis
    with pytest.raises(ValueError):
        sistemas.merged({"alvenaria_tijolo.perdas_pct": -1})


def test_concrete_frame_and_partition_rules():
    for sid, codes in (("betao_armado", {"betao_volume", "cofragem_area", "aco_massa"}),
                       ("ossatura_madeira", {"montantes_un", "placas_area", "isolamento_parede_area"}),
                       ("divisoria_gesso", {"montantes_un", "travessas_comprimento", "placas_area"})):
        r = estudo.run(estudo.Project(sistema=sid, pisos=[_box(altura_m=2.8)]))
        assert codes <= {x["codigo"] for x in r["totais"]}
        assert r["verificacoes_ok"]


def test_prices_with_source_and_missing_prices_listed():
    lib = [estudo.PriceItem(codigo="alvenaria_area", preco_unitario=30, unidade="m²", fonte="tabela 2026"),
           estudo.PriceItem(codigo="reboco_area", preco_unitario=12, unidade="kg", fonte="tabela 2026")]
    r = estudo.run(estudo.Project(pais="FR", pisos=[_box(altura_m=2.8)]), library=lib)
    b = r["orcamento"]
    assert len(b["linhas"]) == 1 and b["iva_pct"] == 20.0 and "CGI" in b["iva_fonte"]
    assert any(m["codigo"] == "reboco_area" and "unidade" in m.get("motivo", "") for m in b["sem_preco"])
    assert b["total"] == pytest.approx(b["subtotal"] * 1.2, abs=0.01)


def test_dossier_with_dimensioned_annex_in_four_languages():
    from pypdf import PdfReader

    r = estudo.run(estudo.Project(nome="Casa", pisos=[_box(inferir_vaos=True, divisoes=[
        {"nome": "Sala", "poligono": [(0.1, 0.1), (7.9, 0.1), (7.9, 5.9), (0.1, 5.9)]}])]))
    for lang, word in (("pt", "Anexo A"), ("en", "Annex A"), ("uk", "Додаток A"), ("fr", "Annexe A")):
        pdf = PdfReader(io.BytesIO(dossier.build(r, lang=lang)))
        text = "".join(p.extract_text() for p in pdf.pages)
        assert word in text
        a3 = [p for p in pdf.pages if float(p.mediabox.width) > 1100]
        assert len(a3) >= 2  # plan + elevations of the floor
    dxf = desenhos.dxf(r["_redes"])
    import ezdxf
    doc = ezdxf.read(io.StringIO(dxf.decode()))
    assert len(doc.modelspace().query("DIMENSION")) > 5
    json.dumps(estudo.public(r))


def test_pilot_brand_only_when_given():
    r = estudo.run(estudo.Project(pisos=[_box()]))
    from pypdf import PdfReader
    meta = PdfReader(io.BytesIO(dossier.build(r))).metadata
    assert meta["/Author"] == "ConstruPilot"
    meta = PdfReader(io.BytesIO(dossier.build(r, brand={"nome": "CLT Rezult", "cor": (0.886, 0.078, 0.067)}))).metadata
    assert meta["/Author"] == "CLT Rezult"


def test_traditional_plan_page_adapter():
    page = {"walls_analysis": {"pt_per_m": 50.0, "px_per_pt": 2.0, "walls": [
        {"wall_id": "M01", "axis": {"x1": 0, "y1": 0, "x2": 800, "y2": 0}, "thickness_m": 0.2, "source": "vector_geometry", "confidence": 0.9},
        {"wall_id": "M02", "axis": {"x1": 800, "y1": 0, "x2": 800, "y2": 600}, "thickness_m": 0.2, "source": "vector_geometry",
         "confidence": 0.9, "ambiguous": True},
        {"wall_id": "M03", "axis": {}, "thickness_m": 0.2},
        {"wall_id": "M04", "axis": {"x1": 0, "y1": 0, "x2": 10, "y2": 10}, "thickness_m": 0.2, "is_post": True}]}}
    floor, notes = adaptadores.from_plan_page(page, name="RDC", rooms=[{"name": "Sala", "points": [[0, 0], [800, 0], [800, 600]]}])
    assert [w["id"] for w in floor["paredes"]] == ["RDC-M01", "RDC-M02"]
    assert floor["paredes"][0]["x2"] == pytest.approx(8.0) and floor["paredes"][1]["y2"] == pytest.approx(-6.0)
    assert any("M02" in n for n in notes) and any("M03" in n for n in notes)
    r = estudo.run(estudo.Project(pisos=[floor]))
    assert r["pisos"][0]["leitura"] == "vetorial" and r["verificacoes_ok"]
    with pytest.raises(ValueError):
        adaptadores.from_plan_page({"walls_analysis": {}}, name="X")


def test_http_common_methods_for_every_account(monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    monkeypatch.setenv("MONGO_URL", "mongodb://127.0.0.1:27017")
    monkeypatch.setenv("DB_NAME", "takeoff_test")
    monkeypatch.setenv("JWT_SECRET", "local-test-only")
    from routes import metodos

    class Store:
        def __init__(self):
            self.docs = {}

        async def find_one(self, q, *a):
            return self.docs.get(q.get("_id"))

        async def update_one(self, q, u, upsert=False):
            self.docs[q["_id"]] = {**self.docs.get(q["_id"], {}), **u["$set"]}

    class DB:
        takeoff_parameters, takeoff_library = Store(), Store()

    monkeypatch.setattr(metodos, "db", DB)
    monkeypatch.setattr(metodos, "require_feature", lambda user, feature: None)
    app = FastAPI()
    app.include_router(metodos.router)
    app.dependency_overrides[metodos.pro_required] = lambda: {"user_id": "zé", "organization_id": "b"}
    body = estudo.Project(nome="Casa", pisos=[_box(altura_m=2.8)]).model_dump()
    with TestClient(app) as client:
        assert client.get("/metodos/sistemas").json()["parametros"]["geral.altura_standard_rdc_m"]["valor"] == 3.0
        assert client.put("/metodos/parametros", json={"valores": {"alvenaria_tijolo.perdas_pct": 0}}).status_code == 200
        assert client.put("/metodos/biblioteca", json={"itens": [{"codigo": "alvenaria_area", "preco_unitario": 30, "unidade": "m²",
                                                                  "fonte": "tabela"}]}).status_code == 200
        r = client.post("/metodos/estudo", json=body)
        assert r.status_code == 200, r.text
        assert r.json()["orcamento"]["linhas"][0]["total"] > 0
        assert client.post("/metodos/dossier?lang=fr", json=body).content.startswith(b"%PDF")
        assert b"COTA" in client.post("/metodos/desenhos?formato=dxf", json=body).content
        assert client.post("/metodos/desenhos?formato=pdf", json=body).content.startswith(b"%PDF")
        bad = {**body, "pisos": [{**body["pisos"][0], "paredes": body["pisos"][0]["paredes"] * 2}]}
        assert client.post("/metodos/estudo", json=bad).status_code == 422
        app.dependency_overrides[metodos.pro_required] = lambda: {"user_id": "x", "active": False}
        assert client.post("/metodos/estudo", json=body).status_code == 403
