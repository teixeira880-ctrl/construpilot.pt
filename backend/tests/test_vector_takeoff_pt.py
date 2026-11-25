"""Medição vetorial por layers (engines/vector_takeoff) e ferramentas medir_processo / ver_layers / orcamentar_partes.

PDFs sintéticos com layers (OCG) desenhados à escala 1:100: trama de pavimento com área conhecida e legenda declarada,
alçado com réguas de revestimento e máscara de fachada, ficha de vão, layer de vegetação (ignorada com motivo).
Base em memória (FakeDB), sem IA."""
import asyncio
import base64
import hashlib
import math
import os

import pytest

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "test_vt_pt")
os.environ.setdefault("JWT_SECRET", "test")

pymupdf = pytest.importorskip("pymupdf")
shapely = pytest.importorskip("shapely")
from fake_mongo_pt import FakeDB  # noqa: E402

from engines import dossier_tool as T  # noqa: E402
from engines import vector_takeoff as V  # noqa: E402

M = 72 / 0.0254 / 100          # pontos por metro à escala 1:100
USER = {"user_id": "u_a", "organization_id": "org_x", "account_type": "pro", "active": True}


def run(coro):
    return asyncio.run(coro)


def _hatch(shape, x0, y0, w, h, spacing_m, angle=45):
    from shapely.geometry import LineString, box
    rect = box(x0, y0, x0 + w, y0 + h)
    sp = spacing_m * M
    th = math.radians(angle)
    ux, uy, nx, ny = math.cos(th), math.sin(th), -math.sin(th), math.cos(th)
    diag = w + h
    cx, cy = x0 + w / 2, y0 + h / 2
    k = -diag
    while k <= diag:
        px, py = cx + nx * k, cy + ny * k
        seg = LineString([(px - ux * diag, py - uy * diag), (px + ux * diag, py + uy * diag)]).intersection(rect)
        if not seg.is_empty and seg.length > 0:
            (a, b), (c, d) = list(seg.coords)[0], list(seg.coords)[-1]
            shape.draw_line((a, b), (c, d))
        k += sp


def plan_pdf():
    doc = pymupdf.open()
    page = doc.new_page(width=1190, height=842)
    oc_pav = doc.add_ocg("JAA_pavimento flutuante", on=True)
    oc_veg = doc.add_ocg("JAA_vegetação", on=True)
    oc_wall = doc.add_ocg("JAA_REBOCO", on=True)
    sh = page.new_shape()
    _hatch(sh, 100, 100, 5 * M, 4 * M, 0.0635)                      # 5 × 4 m = 20 m²
    sh.finish(color=(0.5, 0.25, 0), width=0.2, oc=oc_pav)
    sh.draw_rect(pymupdf.Rect(800, 600, 812, 606))                  # amostra da legenda (mesma layer)
    sh.finish(color=(0.5, 0.25, 0), fill=(0.5, 0.25, 0), oc=oc_pav)
    for i in range(30):                                             # árvores: muitos traços, a ignorar
        sh.draw_circle((400 + i * 3, 400), 5)
    sh.finish(color=(0, 0.6, 0), oc=oc_veg)
    # reboco: 2 linhas paralelas a 1,5 cm (uma face) de 6 m → 6 m de face, não 12
    sh.draw_line((100, 300), (100 + 6 * M, 300))
    sh.draw_line((100, 300 + 0.015 * M), (100 + 6 * M, 300 + 0.015 * M))
    sh.finish(color=(0, 0, 0), width=0.3, oc=oc_wall)
    sh.commit()
    page.insert_text((815, 605), "PV3- Flutuante Carvalho tipo FINSA - 20.00 M2", fontsize=6)
    page.insert_text((815, 640), "PV9 - Manto vegetal - 7.5 M2", fontsize=6)
    page.insert_text((900, 760), "PLANTA DE PAVIMENTOS E RODAPÉS - PISO 1", fontsize=7)
    page.insert_text((900, 780), "ESCALA\n1:100", fontsize=7)
    page.insert_text((900, 700), "1.Hall de entrada - 11,80m²", fontsize=6)
    page.insert_text((300, 120), "Pv3", fontsize=6)
    page.insert_text((300, 140), "2.70 m", fontsize=6)
    page.insert_text((320, 160), "Ve1", fontsize=6)
    return doc.tobytes()


def elevation_pdf():
    doc = pymupdf.open()
    page = doc.new_page(width=1190, height=842)
    oc_mask = doc.add_ocg("JAA_REC.BRANCO", on=True)
    oc_clad = doc.add_ocg("JAA_BETAO", on=True)
    sh = page.new_shape()
    sh.draw_rect(pymupdf.Rect(100, 100, 100 + 12 * M, 100 + 4 * M))   # silhueta 12 × 4 = 48 m²
    sh.finish(color=(1, 1, 1), fill=(1, 1, 1), oc=oc_mask)
    for i in range(30):                                                # 30 réguas 10 m × 0,10 m = 30 m²
        y = 100 + i * 0.10 * M
        sh.draw_rect(pymupdf.Rect(100, y, 100 + 10 * M, y + 0.10 * M))
    sh.finish(color=(0, 0, 0), width=0.1, oc=oc_clad)
    sh.commit()
    page.insert_text((700, 760), "ALÇADO NASCENTE", fontsize=7)
    page.insert_text((700, 780), "ESCALA 1:100", fontsize=7)
    page.insert_text((700, 400), "Revestimento ACL Concrestrip", fontsize=6)
    return doc.tobytes()


def schedule_pdf():
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((50, 60), "DESIGNAÇÃO\nVe 1\nQUANTIDADES\n02\nDESCRIÇÃO E\nFUNCIONAMENTO\nPorta de correr - 2 folhas\n"
                               "MATERIAIS E\nACABAMENTO\nCaixilharia em alumínio\nDIMENSÃO\n290 x 150 cm\nLOCALIZAÇÃO\n3. Sala", fontsize=8)
    page.insert_text((50, 400), "ACABAMENTOS\nTipo Sanindusa Lavatório Ref. 136379004 - 2 Uni.", fontsize=8)
    page.insert_text((400, 780), "ESCALA 1:20", fontsize=7)
    return doc.tobytes()


# ------------------------------------------------------------------------------------------------ motor
def test_plan_hatch_area_matches_declared_legend_and_layers_are_covered():
    r = V.analyze_pdf(plan_pdf())
    assert r["ok"] and r["paginas_analisadas"] == 1
    p = r["paginas"][0]
    assert p["escala"] == 100 and p["tipo"] == "planta_pavimentos"
    assert {"codigo": "PV3", "descricao": "Flutuante Carvalho tipo FINSA", "valor": 20.0, "unidade": "M2"} in p["declared"]
    assert any(d["codigo"] == "PV9" and d["valor"] == 7.5 for d in p["declared"])
    lay = {l["layer"]: l for l in p["layers"]}
    assert lay["JAA_vegetação"]["estado"] == "ignorado" and "vegeta" in lay["JAA_vegetação"]["motivo"]
    assert lay["JAA_pavimento flutuante"]["estado"] == "medido"
    assert abs(lay["JAA_pavimento flutuante"]["trama"]["area_m2"] - 20.0) / 20 < 0.03
    assert abs(lay["JAA_REBOCO"]["comprimento_faces_m"] - 6.0) < 0.1          # 2 linhas de uma face = 1 face
    assert p["legenda_layers"]["PV3"]["layer"] == "JAA_pavimento flutuante"
    assert p["rooms"] == [{"n": 1, "nome": "Hall de entrada", "area_m2": 11.8}]
    assert p["heights"] == {"2.70": 1} and p["tags"]["PV3"] == 1 and p["tags"]["VE1"] == 1


def test_elevation_cladding_and_facade_silhouette():
    p = V.analyze_pdf(elevation_pdf())["paginas"][0]
    assert p["tipo"] == "alcado"
    lay = {l["layer"]: l for l in p["layers"]}
    assert abs(lay["JAA_BETAO"]["area_retangulos_m2"] - 30.0) < 0.3
    assert abs(lay["JAA_REC.BRANCO"]["area_contorno_m2"] - 48.0) < 0.5
    assert any("Concrestrip" in c for c in p["callouts"])


def test_schedule_units_and_aggregate_cross_check():
    files = [{"doc_id": "d1", "filename": "014.pdf", "result": V.analyze_pdf(plan_pdf())},
             {"doc_id": "d2", "filename": "010.pdf", "result": V.analyze_pdf(elevation_pdf())},
             {"doc_id": "d3", "filename": "039.pdf", "result": V.analyze_pdf(schedule_pdf())},
             {"doc_id": "d4", "filename": "mau.pdf", "result": V.analyze_pdf(b"%PDF-nada")}]
    a = V.aggregate(files)
    c = a["cobertura"]
    assert c["ficheiros"] == 4 and c["lidos"] == 3 and c["com_erro"] == 1 and c["completo"] is False
    assert next(d for d in c["detalhe"] if d["ficheiro"] == "mau.pdf")["estado"] == "ERRO"
    pv3 = next(x for x in a["cruzamento_legenda_vs_desenho"] if x["codigo"] == "PV3")
    assert pv3["estado"] == "CONFERE" and pv3["declarado_m2"] == 20.0
    ve = a["quantidades_por_parte"]["vaos_exteriores"][0]
    assert ve["codigo"] == "VE1" and ve["quantidade"] == 2 and ve["area_total_m2"] == pytest.approx(8.7)
    assert ve["altura_m"] == 2.9 and ve["largura_m"] == 1.5                    # «290 x 150»: 2,90 é a altura
    assert ve["alerta"].startswith("mapa indica 2 un")                         # planta só mostra 1 etiqueta
    assert a["quantidades_por_parte"]["loucas_equipamentos"][0]["quantidade"] == 2
    assert {x["codigo"] for x in a["quantidades_por_parte"]["pavimentos"]} == {"PV3", "PV9"}
    assert a["fachadas_por_alcado"][0]["titulo"] == "ALÇADO NASCENTE"


def test_deterministic_repeat():
    a = V.analyze_pdf(plan_pdf())
    b = V.analyze_pdf(plan_pdf())
    assert a == b


def test_render_layers_only_selected_and_highlight():
    data = plan_pdf()
    png_all, _ = V.render_layers(data, 1, None, None)
    png_veg_off, info = V.render_layers(data, 1, None, ["JAA_vegetação"])
    assert png_all != png_veg_off and "JAA_vegetação" not in info["layers_visiveis"]
    png_h, info = V.render_layers(data, 1, None, None, [0.0, 0.0, 0.6, 0.6], 1200, ["JAA_pavimento flutuante"])
    assert info["objetos_destacados"] > 50 and png_h[:4] == b"\x89PNG"
    _, info = V.render_layers(data, 1, ["inexistente"], None)
    assert info["layers_desconhecidas"] == ["inexistente"]
    with pytest.raises(ValueError):
        V.render_layers(data, 3, None, None)


# ------------------------------------------------------------------------------------------------ ferramentas
@pytest.fixture
def db(monkeypatch):
    fake = FakeDB()
    from concurrent.futures import ThreadPoolExecutor
    monkeypatch.setattr(T, "_POOL", ThreadPoolExecutor(max_workers=2))
    return fake


def _seed(db, entries):
    run(db.assistant_dossiers.insert_one({"dossier_id": "dos_1", "user_id": "u_a", "name": "Moradia"}))
    for i, (name, data) in enumerate(entries):
        run(db.assistant_docs.insert_one({"doc_id": f"doc_{i}", "user_id": "u_a", "dossier_id": "dos_1", "filename": name, "path": name,
                                          "format": "pdf", "mime": "application/pdf", "sha256": hashlib.sha256(data).hexdigest(),
                                          "data_b64": base64.b64encode(data).decode()}))


def test_tools_measure_view_and_isolation(db):
    _seed(db, [("014.pdf", plan_pdf()), ("010.pdf", elevation_pdf()), ("039.pdf", schedule_pdf())])
    res = run(T.execute("medir_processo", {"dossier_id": "dos_1", "detalhe": "resumo"}, USER, {}, db))
    assert res["concluido"] and res["cobertura"]["lidos"] == 3 and res["cobertura"]["ficheiros_com_problema"] == []
    assert len(db.vector_takeoff_cache.docs) == 3                                   # memorizado por conteúdo
    again = run(T.execute("medir_processo", {"dossier_id": "dos_1", "detalhe": "resumo"}, USER, {}, db))
    assert again == res                                                             # mesmo resultado ao repetir
    other = run(T.execute("medir_processo", {"dossier_id": "dos_1", "detalhe": "resumo"}, {**USER, "user_id": "u_b"}, {}, db))
    assert other["ok"] is False
    v = run(T.execute("ver_layers", {"document_id": "doc_0", "page": 1, "mostrar": [], "esconder": ["JAA_vegetação"],
                                     "destacar": ["JAA_pavimento flutuante"], "box": None}, USER, {}, db))
    assert v["ok"] and v["_model_attachments"][1]["type"] == "input_image"
    v = run(T.execute("ver_layers", {"document_id": "014.pdf", "page": 1, "mostrar": [], "esconder": [], "destacar": [], "box": None}, USER, {}, db))
    assert v["ok"] and v["document_id"] == "doc_0"                                  # nome de ficheiro aceite
    assert run(T.execute("ver_layers", {"document_id": "doc_0", "page": 1, "mostrar": [], "esconder": [], "destacar": [], "box": None},
                         {**USER, "user_id": "u_b"}, {}, db))["ok"] is False


def test_measure_time_budget_returns_partial_then_completes(db, monkeypatch):
    _seed(db, [("014.pdf", plan_pdf()), ("010.pdf", elevation_pdf())])
    monkeypatch.setattr(T, "TIME_BUDGET_S", -1)
    monkeypatch.setattr(T, "warm_dossier", lambda *a, **k: asyncio.sleep(0))
    part = run(T.execute("medir_processo", {"dossier_id": "dos_1", "detalhe": "resumo"}, USER, {}, db))
    assert part["concluido"] is False and set(part["em_falta"]) == {"014.pdf", "010.pdf"}
    monkeypatch.setattr(T, "TIME_BUDGET_S", 100)
    assert run(T.execute("medir_processo", {"dossier_id": "dos_1", "detalhe": "completo"}, USER, {}, db))["cobertura"]["detalhe"]


def test_quote_parts_only_requested_parts(db, monkeypatch):
    _seed(db, [("014.pdf", plan_pdf()), ("039.pdf", schedule_pdf())])
    saved = {}

    async def fake_save(args, user, conv, **_):
        saved["args"] = args
        return {"ok": True, "doc_id": "doc_q"}

    async def fake_exports(result, user, conv):
        return result

    import engines.assistant_quote_exports as QE
    import engines.assistant_quote_service as QS
    monkeypatch.setattr(QS, "save_quote", fake_save)
    monkeypatch.setattr(QE, "with_exports", fake_exports)
    res = run(T.execute("orcamentar_partes", {"dossier_id": "dos_1", "partes": ["pavimentos", "fachadas"], "titulo": "Só pavimentos e fachadas",
                                              "cliente": "", "linhas_calculadas": [
                                                  {"parte": "fachadas", "designacao": "Revestimento Concrestrip", "quantidade": 30.0, "unidade": "m²",
                                                   "formula_e_origem": "alçado nascente, layer JAA_BETAO", "preco_unitario_estimado": None},
                                                  {"parte": "tetos", "designacao": "não pedido", "quantidade": 1, "unidade": "m²",
                                                   "formula_e_origem": "x", "preco_unitario_estimado": 10}]}, USER, {"user_id": "u_a"}, db))
    assert res["ok"] and res["linhas"] == 3 and res["partes_sem_linhas"] == []
    lots = {l["lot"] for l in saved["args"]["lines"]}
    assert lots == {"pavimentos", "fachadas"}                                       # vãos e tetos não entram
    pv3 = next(l for l in saved["args"]["lines"] if l["designation"].startswith("PV3"))
    assert pv3["quantity"] == 20.0 and pv3["unit"] == "m²" and pv3["price_origin"] == "library" and "014.pdf" in pv3["description"]
    none = run(T.execute("orcamentar_partes", {"dossier_id": "dos_1", "partes": ["paredes_revestimentos"], "titulo": "x", "cliente": "",
                                               "linhas_calculadas": []}, USER, {"user_id": "u_a"}, db))
    assert none["ok"] is False and none["partes_sem_quantidade_declarada"] == ["paredes_revestimentos"]


def test_tools_are_exposed_to_the_assistant():
    A = pytest.importorskip("routes.assistant")
    names = {t["name"] for t in A.tools_for({**USER, "account_type": "particulier"})}
    assert {"medir_processo", "ver_layers"} <= names and "orcamentar_partes" not in names
    assert "medir_processo" in T.INSTRUCTIONS and "FACHADAS" in T.INSTRUCTIONS
