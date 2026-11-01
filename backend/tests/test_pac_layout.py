"""Implantação de bomba de calor reversível (engines/pac_layout) : leitura das plantas, colocação, posições impostas, PDF.

Plantas sintéticas portuguesas à escala 1:50 (paredes pretas, caixilharia cinzenta, etiquetas « nome + A = xx m² » ou
« nome Área: xx m² » na mesma linha) ; o caso real francês Houilles corre em local com PAC_HOUILLES_PDF=/caminho/DCE.pdf."""
from __future__ import annotations

import asyncio
import copy
import os

import pytest

pymupdf = pytest.importorskip("pymupdf")

from engines.pac_layout import layout, plans, report  # noqa: E402
from engines.pac_layout.tool import merge_placements, run as tool_run  # noqa: E402

F = 72 / 25.4 * 20          # 1 m = 20 mm au 1:50
O = (420.0, 180.0)          # origine du bâtiment sur la planche (pt)
T = 0.20                    # épaisseur des murs (m)


def _wall(pg, x0, y0, x1, y1):
    pg.draw_rect(pymupdf.Rect(O[0] + x0 * F, O[1] + y0 * F, O[0] + x1 * F, O[1] + y1 * F), color=None, fill=(0, 0, 0))


def _hwall(pg, y, x0, x1, gaps=()):
    """Mur horizontal d'axe y de x0 à x1, avec ouvertures [(a, b, menuiserie?)]."""
    xs = [x0] + [v for g in gaps for v in g[:2]] + [x1]
    for a, b in zip(xs[::2], xs[1::2]):
        _wall(pg, a, y - T / 2, b, y + T / 2)
    for a, b, joinery in gaps:
        if joinery:
            for dy in (-0.05, 0.05):
                pg.draw_line(pymupdf.Point(O[0] + a * F, O[1] + (y + dy) * F), pymupdf.Point(O[0] + b * F, O[1] + (y + dy) * F),
                             color=(0.68, 0.68, 0.68), width=0.3)


def _vwall(pg, x, y0, y1, gaps=()):
    ys = [y0] + [v for g in gaps for v in g[:2]] + [y1]
    for a, b in zip(ys[::2], ys[1::2]):
        _wall(pg, x - T / 2, a, x + T / 2, b)
    for a, b, joinery in gaps:
        if joinery:
            for dx in (-0.05, 0.05):
                pg.draw_line(pymupdf.Point(O[0] + (x + dx) * F, O[1] + a * F), pymupdf.Point(O[0] + (x + dx) * F, O[1] + b * F),
                             color=(0.68, 0.68, 0.68), width=0.3)


def _label(pg, name, area, cx, cy):
    x, y = O[0] + cx * F, O[1] + cy * F
    pg.insert_text(pymupdf.Point(x - 8, y - 10), name, fontsize=6)
    pg.insert_text(pymupdf.Point(x - 30, y + 4), f"A = {area:.2f}".replace(".", ",") + " m2", fontsize=14)


def _label_line(pg, name, area, cx, cy):
    x, y = O[0] + cx * F, O[1] + cy * F
    pg.insert_text(pymupdf.Point(x - 40, y + 4), f"{name} Área: {area:.2f}".replace(".", ",") + " m2", fontsize=10)


def synth_dce() -> bytes:
    """Maison 10 × 8 m sur 2 niveaux. RDC : séjour 6×5, cuisine 4×5, entrée 3×3, garage 7×3. R+1 : CB 1, SdB, CB 2, palier."""
    doc = pymupdf.open()
    # --- RDC
    pg = doc.new_page(width=1684, height=1191)
    pg.insert_text(pymupdf.Point(60, 50), "Planta do Rés-do-Chão", fontsize=13)
    pg.insert_text(pymupdf.Point(1500, 1150), "1:50", fontsize=12)
    _hwall(pg, 0, -T / 2, 10 + T / 2)
    _hwall(pg, 8, -T / 2, 10 + T / 2, [(4.0, 9.0, True), (1.0, 2.0, False)])          # porte de garage (vitrée/sectionnelle) + porte d'entrée
    _vwall(pg, 0, 0, 8, [(1.0, 3.5, True)])                                            # baie du séjour
    _vwall(pg, 10, 0, 8, [(1.5, 3.0, True)])
    _vwall(pg, 6, 0, 5, [(2.0, 2.9, False)])                                           # porte séjour / cuisine
    _hwall(pg, 5, 0, 10, [(1.0, 1.9, False), (7.0, 7.9, False)])                       # portes entrée / séjour, cuisine / garage
    _vwall(pg, 3, 5, 8, [(6.0, 6.9, False)])                                           # porte entrée / garage
    _label(pg, "Sala", 27.06, 3.0, 2.5)
    _label(pg, "Cozinha", 17.48, 8.0, 2.5)
    _label(pg, "Hall", 7.83, 1.5, 6.5)
    _label_line(pg, "Garagem", 19.08, 6.5, 6.5)
    # --- R+1
    pg = doc.new_page(width=1684, height=1191)
    pg.insert_text(pymupdf.Point(60, 50), "Planta do Piso 1", fontsize=13)
    pg.insert_text(pymupdf.Point(1500, 1150), "1:50", fontsize=12)
    _hwall(pg, 0, -T / 2, 10 + T / 2, [(1.0, 3.0, True), (7.0, 9.0, True)])
    _hwall(pg, 8, -T / 2, 10 + T / 2)
    _vwall(pg, 0, 0, 8)
    _vwall(pg, 10, 0, 8)
    _vwall(pg, 4.5, 0, 5)
    _vwall(pg, 6.5, 0, 5)
    _hwall(pg, 5, 0, 10, [(2.0, 2.9, False), (5.0, 5.9, False), (8.0, 8.9, False)])
    _label(pg, "Quarto 1", 19.9, 2.25, 2.5)
    _label(pg, "I.S.", 8.64, 5.5, 2.5)
    _label(pg, "Quarto 2", 15.5, 8.25, 2.5)
    _label(pg, "Corredor", 26.73, 5.0, 6.5)
    return doc.tobytes()


@pytest.fixture(scope="module")
def dce():
    return synth_dce()


@pytest.fixture(scope="module")
def levels(dce):
    return plans.read_plans(dce)


def test_pages_et_niveaux(dce):
    pp = plans.plan_pages(dce)
    assert [p["level"] for p in pp] == ["R/C", "Piso 1"]
    assert all(p["scale"] == 50 for p in pp)
    assert plans.level_key("Cave") < plans.level_key("R/C") < plans.level_key("Piso 1") < plans.level_key("Piso 2")
    assert plans.level_label("rés-do-chão") == "R/C" and plans.level_label("1º piso") == "Piso 1" and plans.level_label("piso 2") == "Piso 2"


def test_pieces_lues_a_la_surface_ecrite(levels):
    rdc, r1 = levels
    assert sorted(r.name for r in rdc.rooms) == ["Cozinha", "Garagem", "Hall", "Sala"]
    for lv in levels:
        for r in lv.rooms:
            assert r.mask is not None and r.mask.any(), r.name
            assert abs(r.area_measured - r.area_label) <= 0.15 * r.area_label, (lv.name, r.name, r.area_measured, r.area_label)
    # les pièces ne se chevauchent pas
    import numpy as np
    for lv in levels:
        tot = sum(r.mask.astype(int) for r in lv.rooms)
        assert int(np.max(tot)) == 1


def test_types_de_pieces():
    assert layout.room_type("Sala comum") == "sejour"
    assert layout.room_type("Quarto 2") == "chambre"
    assert layout.room_type("I.S.") == "sdb"
    assert layout.room_type("Instalação sanitária") == "sdb"
    assert layout.room_type("Cozinha") == "cuisine"
    assert layout.room_type("Lavandaria") == "buanderie"
    assert layout.room_type("Garagem") == "garage"
    assert layout.room_type("Arrumos") == "rangement"
    assert layout.room_type("Varanda") == "exterieur"
    assert layout.room_type("Séjour") == "sejour"
    assert layout.room_type("CB 3") == "chambre"
    assert layout.room_type("SdE 1") == "sdb"
    assert layout.room_type("LT - Buanderie") == "buanderie"
    assert layout.room_type("Dgt") == "circulation"
    assert layout.room_type("Garage") == "garage"
    assert layout.room_type("Bibliothèque") == "sejour"


def test_implantation_automatique(levels):
    res = layout.compute(levels)
    assert res["ok"] and res["base_level"] == "R/C" and res["heated_levels"] == ["R/C", "Piso 1"]
    rdc = res["levels"]["R/C"]
    kinds = {e["kind"]: e for e in rdc["equipment"]}
    assert kinds["module"]["room"] == "Hall"                       # sem área técnica : o hall antes da garagem
    assert kinds["collecteur"]["room"] == "Hall"
    assert "pac" in kinds and "colonne" in kinds
    # garage non chauffé : ni boucle ni ventilo
    assert "Garagem" not in {lp["room"] for lp in rdc["loops"]}
    vc_rooms = [v["room"] for v in rdc["vc"]]
    assert vc_rooms.count("Sala") == 2 and vc_rooms.count("Cozinha") == 1
    r1 = res["levels"]["Piso 1"]
    assert {v["room"] for v in r1["vc"]} == {"Quarto 1", "Quarto 2"}
    assert any(e["kind"] == "collecteur" and e["room"] == "Corredor" for e in r1["equipment"])
    for lp in rdc["loops"] + r1["loops"]:
        assert lp["length"] <= layout.L_MAX
    sdb = next(lp for lp in r1["loops"] if lp["room"] == "I.S.")
    assert sdb["pitch"] == 0.10
    # condensats des chambres vers la salle de bains
    assert all(v["drain_to"] == "I.S." for v in r1["vc"])


def test_groupe_exterieur_jamais_devant_une_ouverture(levels):
    res = layout.compute(levels)
    rdc = next(lv for lv in levels if lv.name == "R/C")
    pac = next(e for e in res["levels"]["R/C"]["equipment"] if e["kind"] == "pac")
    x, y = int(pac["x"]), int(pac["y"])
    assert rdc.room_at(x, y) is None and not rdc.walls[y, x]
    import cv2
    import numpy as np
    d = cv2.distanceTransform((~rdc.openings).astype(np.uint8), cv2.DIST_L2, 3)
    assert d[y, x] >= 0.75 * rdc.px_per_m                         # à l'écart des portes, baies et porte de garage


def test_deplacements_imposes(levels):
    pl = [{"equipment": "module", "level": "R/C", "room": "Garagem", "near_room": "Hall", "side": None, "count": None},
          {"equipment": "vc", "level": "R/C", "room": "Sala", "near_room": None, "side": None, "count": 1},
          {"equipment": "groupe_exterieur", "level": None, "room": "Cozinha", "near_room": None, "side": "este", "count": None}]
    res = layout.compute(levels, pl)
    eqs = {e["kind"]: e for e in res["levels"]["R/C"]["equipment"]}
    assert eqs["module"]["room"] == "Garagem"
    assert any("anticongelamento" in c for c in res["checks"])
    assert [v["room"] for v in res["levels"]["R/C"]["vc"]].count("Sala") == 1
    rdc = levels[0]
    cu = rdc.room("Cozinha")
    assert eqs["pac"]["x"] > cu.bbox()[2]                          # côté est de la cuisine
    assert any("imposta" in d for d in res["decisions"])


def test_fusion_des_positions():
    a = [{"equipment": "module", "level": None, "room": "Entrée", "near_room": "Cuisine", "side": None, "count": None}]
    b = [{"equipment": "module", "level": None, "room": "Buanderie", "near_room": None, "side": None, "count": None},
         {"equipment": "collecteur", "level": "R+1", "room": "Palier", "near_room": None, "side": None, "count": None},
         {"equipment": "vc", "level": "RDC", "room": "Séjour", "near_room": None, "side": None, "count": 2}]
    m = merge_placements(a, b)
    assert len(m) == 3 and next(p for p in m if p["equipment"] == "module")["room"] == "Buanderie"


def test_chaine_complete_pdf(dce):
    out = report.run(dce, [], None, "Moradia teste", "projeto.pdf")
    assert out["ok"], out
    assert out["pdf"][:4] == b"%PDF" and set(out["pngs"]) == {"R/C", "Piso 1"}
    assert all(p[:8] == b"\x89PNG\r\n\x1a\n" for p in out["pngs"].values())
    doc = pymupdf.open(stream=out["pdf"], filetype="pdf")
    text = "".join(p.get_text() for p in doc)
    assert "Circuitos de piso radiante R/C" in text and "Circuitos de piso radiante Piso 1" in text and "Pontos a validar" in text and "REH" in text


def test_document_sans_plans():
    doc = pymupdf.open()
    doc.new_page().insert_text(pymupdf.Point(50, 50), "Caderno de encargos - estruturas")
    out = report.run(doc.tobytes(), [], None, None, "ce.pdf")
    assert not out["ok"] and "Planta do R/C" in out["error"]


# ------------------------------------------------------------------------------------------------ outil Assistant
class _Coll:
    def __init__(self):
        self.docs = []

    async def find_one(self, q, proj=None):
        for d in self.docs:
            if all(d.get(k) == v for k, v in q.items()):
                return copy.deepcopy(d)
        return None

    async def update_one(self, q, upd, upsert=False):
        for d in self.docs:
            if all(d.get(k) == v for k, v in q.items()):
                d.update(upd.get("$set", {}))
                return
        if upsert:
            self.docs.append({**q, **upd.get("$set", {}), **upd.get("$setOnInsert", {})})


class _DB:
    def __init__(self):
        self.pac_layouts, self.assistant_artifacts = _Coll(), _Coll()


def test_outil_memorise_les_positions(dce):
    db = _DB()
    user, conv = {"user_id": "u1"}, {"conversation_id": "c1", "_quote_request_id": "r1"}

    async def load(ident, uid):
        assert ident == "doc_1" and uid == "u1"
        return {"pdf_bytes": dce, "filename": "dce.pdf"}

    async def go():
        r1 = await tool_run({"document_id": "doc_1", "placements": [], "reset_placements": False}, user, conv, db, load)
        assert r1["ok"] and r1["artifact"]["format"] == "pdf" and len(r1["artifacts"]) == 3
        mv = [{"equipment": "module", "level": "R/C", "room": "Cozinha", "near_room": "Hall", "side": None, "count": None}]
        r2 = await tool_run({"document_id": "", "placements": mv, "reset_placements": False}, user, conv, db, load)
        assert r2["ok"] and any("module : Cozinha" in e for e in r2["pisos"]["R/C"]["equipamentos"])
        r3 = await tool_run({"document_id": "", "placements": [], "reset_placements": False}, user, conv, db, load)
        assert r3["posicoes_impostas"] == r2["posicoes_impostas"]           # mémorisé dans la conversation
        r4 = await tool_run({"document_id": "", "placements": [], "reset_placements": True}, user, conv, db, load)
        assert r4["posicoes_impostas"] == []
        assert len(db.assistant_artifacts.docs) == 12
    asyncio.run(go())


@pytest.mark.skipif(not os.environ.get("PAC_HOUILLES_PDF"), reason="DCE Houilles privé : PAC_HOUILLES_PDF=… pour le cas réel")
def test_cas_reel_houilles():
    pdf = open(os.environ["PAC_HOUILLES_PDF"], "rb").read()
    lvs = plans.read_plans(pdf)
    assert [lv.name for lv in lvs] == ["RDC", "R+1"]
    for lv in lvs:
        assert all(r.status == "ok" for r in lv.rooms), [(r.name, r.status) for r in lv.rooms]
    res = layout.compute(lvs)
    eq = {e["kind"]: e for e in res["levels"]["RDC"]["equipment"]}
    assert eq["module"]["room"] == "Entrée" and eq["collecteur"]["room"] == "Entrée" and eq["pac"]["room"] == "Garage"
    assert any(e["kind"] == "collecteur" and e["room"] == "Dgt" for e in res["levels"]["R+1"]["equipment"])
    assert res["totals"]["loops"] == 20 and res["totals"]["vc"] == 8
