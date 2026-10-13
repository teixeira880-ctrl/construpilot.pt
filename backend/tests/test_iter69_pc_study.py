"""Iter 69 — Étude PC (gros œuvre) + catalogue construction maison."""
import io
import os
import zipfile
import pytest
import requests

def _load_backend_url():
    v = os.environ.get("REACT_APP_BACKEND_URL")
    if v: return v.rstrip("/")
    try:
        with open("/app/frontend/.env") as f:
            for ln in f:
                if ln.startswith("REACT_APP_BACKEND_URL="):
                    return ln.split("=", 1)[1].strip().rstrip("/")
    except Exception: pass
    raise RuntimeError("REACT_APP_BACKEND_URL not set")

BASE = _load_backend_url()
PLAN_ID = "plan_619e41f98d6b"
PRO = {"email": "pro@construpilot.fr", "password": "Pro2026!"}
DEMO = {"email": "demo@construpilot.fr", "password": "Demo2026!"}


@pytest.fixture(scope="module")
def pro_token():
    r = requests.post(f"{BASE}/api/auth/login", json=PRO, timeout=30)
    assert r.status_code == 200, r.text
    return r.json()["token"]


@pytest.fixture(scope="module")
def pro_h(pro_token):
    return {"Authorization": f"Bearer {pro_token}"}


# ---------------- Étude PC — GET existing ----------------
class TestPcStudyRead:
    def test_get_pc_study_existing(self, pro_h):
        r = requests.get(f"{BASE}/api/takeoffs/{PLAN_ID}/pc-study", headers=pro_h, timeout=30)
        assert r.status_code == 200, r.text
        st = r.json().get("pc_study")
        assert st, "pc_study should exist on plan_619e41f98d6b"
        # Structure
        for k in ("inputs", "input_sources", "lots", "totals", "demandes"):
            assert k in st, f"missing key {k}"
        inp = st["inputs"]
        for k in ("levels", "surface_m2", "perimeter_m", "refends_m",
                  "wall_height_m", "openings_count", "stairs_count"):
            assert k in inp, f"missing input {k}"
        tot = st["totals"]
        for k in ("beton_m3", "acier_kg", "briques_u", "ht", "tva", "ttc"):
            assert k in tot, f"missing total {k}"
        # TVA arithmetic
        assert abs(tot["ttc"] - (tot["ht"] + tot["tva"])) < 1.0, tot
        # Lot names — Terrassement & Fondations always present
        lot_names = [l.get("lot", "").lower() for l in st["lots"]]
        assert any("fondation" in n or "terrassement" in n for n in lot_names), lot_names
        assert any("plancher" in n for n in lot_names), lot_names
        assert any("élévation" in n or "elevation" in n for n in lot_names), lot_names
        # Arithmetic coherence
        perim = inp["perimeter_m"]; ref = inp["refends_m"]
        expected_sem_m3 = round((perim + ref) * 0.6 * 0.3, 2)
        expected_acier_sem = round((perim + ref) * 15, 1)
        sem_m3 = sem_acier = None
        for lot in st["lots"]:
            for ln in lot.get("lines", []):
                lib = (ln.get("designation") or "").lower()
                unit = (ln.get("unit") or "").lower()
                if "semelle" in lib and unit in ("m3", "m³") and sem_m3 is None:
                    sem_m3 = float(ln["qty"])
                if "semelle" in lib and unit == "kg" and sem_acier is None:
                    sem_acier = float(ln["qty"])
        assert sem_m3 is not None and abs(sem_m3 - expected_sem_m3) < 0.3, (sem_m3, expected_sem_m3)
        assert sem_acier is not None and abs(sem_acier - expected_acier_sem) < 1.0, (sem_acier, expected_acier_sem)
        # Total acier > semelles alone (dalle treillis adds up)
        assert tot["acier_kg"] >= sem_acier

    def test_get_pdf(self, pro_h):
        r = requests.get(f"{BASE}/api/takeoffs/{PLAN_ID}/pc-study/pdf", headers=pro_h, timeout=30)
        assert r.status_code == 200, r.text
        assert r.content.startswith(b"%PDF"), r.content[:16]
        assert len(r.content) > 3000, len(r.content)

    def test_get_docx(self, pro_h):
        r = requests.get(f"{BASE}/api/takeoffs/{PLAN_ID}/pc-study/docx", headers=pro_h, timeout=30)
        assert r.status_code == 200, r.text
        assert len(r.content) > 5000
        # docx = zip
        z = zipfile.ZipFile(io.BytesIO(r.content))
        assert "word/document.xml" in z.namelist()

    def test_xlsx_has_pc_sheet(self, pro_h):
        r = requests.get(f"{BASE}/api/takeoffs/{PLAN_ID}/export-xlsx", headers=pro_h, timeout=30)
        assert r.status_code == 200, r.text
        z = zipfile.ZipFile(io.BytesIO(r.content))
        # workbook.xml lists sheet names
        wb = z.read("xl/workbook.xml").decode("utf-8", errors="ignore")
        assert "Étude PC" in wb or "Etude PC" in wb, wb[:500]


# ---------------- Étude PC — errors ----------------
class TestPcStudyErrors:
    def test_pdf_on_plan_without_study(self, pro_h):
        # Create a fresh plan via /api/takeoffs (empty plan without pc_study)
        # Or use any plan the user owns without pc_study. Try to find one.
        r = requests.get(f"{BASE}/api/takeoffs", headers=pro_h, timeout=15)
        if r.status_code != 200:
            pytest.skip(f"list takeoffs endpoint returned {r.status_code}")
        plans = r.json() if isinstance(r.json(), list) else r.json().get("plans", [])
        target = None
        for p in plans:
            pid = p.get("plan_id")
            if pid and pid != PLAN_ID:
                # Check if it has pc_study
                g = requests.get(f"{BASE}/api/takeoffs/{pid}/pc-study", headers=pro_h, timeout=15)
                if g.status_code == 200 and not (g.json() or {}).get("pc_study"):
                    target = pid; break
        if not target:
            pytest.skip("no plan without pc_study available")
        r = requests.get(f"{BASE}/api/takeoffs/{target}/pc-study/pdf", headers=pro_h, timeout=15)
        assert r.status_code == 400, r.status_code
        assert "Aucune" in r.text or "étude" in r.text.lower()

    def test_unknown_plan_404(self, pro_h):
        r = requests.get(f"{BASE}/api/takeoffs/plan_does_not_exist_xyz/pc-study", headers=pro_h, timeout=15)
        assert r.status_code == 404

    def test_no_auth_401(self):
        r = requests.get(f"{BASE}/api/takeoffs/{PLAN_ID}/pc-study", timeout=15)
        assert r.status_code in (401, 403), r.status_code


# ---------------- Catalogue estimation ----------------
class TestEstimationCatalog:
    def test_catalog_contains_new_types(self, pro_h):
        r = requests.get(f"{BASE}/api/estimation/catalog", headers=pro_h, timeout=15)
        assert r.status_code == 200, r.text
        data = r.json()
        # project_types
        pts = data.get("project_types") or data.get("projectTypes") or []
        if isinstance(pts, dict):
            pt_keys = list(pts.keys())
        else:
            pt_keys = [p.get("id") or p.get("key") or p.get("code") for p in pts]
        for want in ("construction_maison_neuve", "hors_eau_hors_air",
                     "gros_oeuvre", "second_oeuvre", "construction_maison_main_oeuvre"):
            assert any(want in (k or "") for k in pt_keys), (want, pt_keys)
        # lots
        lots = data.get("lots") or []
        lot_ids = [l.get("id") or l.get("key") or l.get("code") or l.get("nom", "").lower()
                   for l in lots] if isinstance(lots, list) else list(lots.keys())
        lot_str = " ".join(str(x).lower() for x in lot_ids)
        for want in ("terrassement", "charpente", "vrd", "ventilation"):
            assert want in lot_str, (want, lot_ids)

    def test_compute_labour_only(self, pro_h):
        r = requests.post(f"{BASE}/api/estimation/compute", headers=pro_h,
                          json={"project_type": "construction_maison_main_oeuvre",
                                "surface": 100, "condition": "neuf"}, timeout=30)
        assert r.status_code == 200, r.text
        d = r.json()
        br = d.get("breakdown") or {}
        mats = br.get("materials", br.get("materiaux"))
        lab = br.get("labour", br.get("main_oeuvre", br.get("labor")))
        assert mats == 0, br
        assert (lab or 0) > 0, br

    def test_compute_neuve_range(self, pro_h):
        r = requests.post(f"{BASE}/api/estimation/compute", headers=pro_h,
                          json={"project_type": "construction_maison_neuve",
                                "surface": 100, "condition": "neuf"}, timeout=30)
        assert r.status_code == 200, r.text
        d = r.json()
        tot = d.get("total_avg") or d.get("totalAvg") or (d.get("total") or {}).get("avg")
        assert tot is not None, d
        assert 120000 <= tot <= 200000, tot
