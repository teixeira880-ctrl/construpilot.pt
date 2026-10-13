"""Iter221 - Tests des 4 nouvelles évolutions:
- Escalier -> devis (POST /api/stairs/to-quote)
- PDF dossier escalier coté (POST /api/stairs/dossier/generate)
- Ouvrages partagés (org) (GET/POST/DELETE /api/takeoffs/corps-etat/ouvrages)
- Projet multi-niveaux (/api/takeoffs/multilevel/groups)
- Import multi-plans avec display_name (POST /api/takeoffs/upload)
"""
import io
import os
import time
import pytest
import requests

BASE = os.environ.get("REACT_APP_BACKEND_URL", "https://pilot-build-demo.preview.emergentagent.com").rstrip("/")

PRO = ("pro@construpilot.fr", "Pro2026!")
COLL = ("collegue@construpilot.fr", "Collegue2026!")


def _login(email, password):
    r = requests.post(f"{BASE}/api/auth/login", json={"email": email, "password": password}, timeout=30)
    assert r.status_code == 200, f"login {email}: {r.status_code} {r.text[:200]}"
    return r.json()["token"]


@pytest.fixture(scope="module")
def pro_h():
    return {"Authorization": f"Bearer {_login(*PRO)}"}


@pytest.fixture(scope="module")
def coll_h():
    return {"Authorization": f"Bearer {_login(*COLL)}"}


@pytest.fixture(scope="module")
def stair_result(pro_h):
    r = requests.post(f"{BASE}/api/stairs/calculate/straight", headers=pro_h,
                      json={"floor_height_mm": 2700, "available_length_mm": 5000,
                            "available_width_mm": 1200, "stair_width_mm": 1000}, timeout=30)
    assert r.status_code == 200, r.text[:300]
    data = r.json()
    assert data.get("is_buildable") is True, f"not buildable: {list(data)[:8]}"
    return data


class TestStairToQuote:
    def test_to_quote_creates_draft_with_3_lines(self, pro_h, stair_result):
        r = requests.post(f"{BASE}/api/stairs/to-quote", headers=pro_h,
                          json={"project_name": "ZZ Escalier test", "stair_result": stair_result}, timeout=60)
        assert r.status_code == 200, r.text[:400]
        doc = r.json()
        doc_id = doc.get("doc_id") or doc.get("id") or (doc.get("document") or {}).get("doc_id")
        assert doc_id, f"no doc_id in response: {doc}"
        # fetch back
        g = requests.get(f"{BASE}/api/documents/{doc_id}", headers=pro_h, timeout=30)
        assert g.status_code == 200, g.text[:300]
        d = g.json()
        assert "Escalier" in d.get("title", "")
        lines = [l for l in d.get("lines", []) if l.get("line_kind") == "ouvrage"]
        units = sorted([l.get("unit") for l in lines])
        assert units == ["kg", "m2", "m3"], f"units mismatch: {units}"
        for l in lines:
            assert l.get("unit_price_ht") in (0, 0.0)
            assert l.get("price_missing") is True
        # cleanup
        dl = requests.delete(f"{BASE}/api/documents/{doc_id}", headers=pro_h, timeout=30)
        assert dl.status_code in (200, 204)


class TestStairDossierPDF:
    def test_dossier_pdf_generated(self, pro_h, stair_result):
        body = {
            "project_name": "ZZ Dossier PDF",
            "stair_input": {"floor_height_mm": 2700, "available_length_mm": 5000,
                            "available_width_mm": 1200, "stair_width_mm": 1000},
            "stair_result": stair_result,
        }
        r = requests.post(f"{BASE}/api/stairs/dossier/generate", headers=pro_h, json=body, timeout=90)
        assert r.status_code == 200, r.text[:300]
        assert r.content[:4] == b"%PDF", "not a PDF"
        assert len(r.content) > 1000
        cd = r.headers.get("content-disposition", "")
        assert "ZZ" in cd or "Dossier" in cd or "PDF" in cd.upper() or "escalier" in cd.lower()


class TestOuvragesShared:
    def test_shared_visibility_and_delete(self, pro_h, coll_h):
        # pro creates shared
        r = requests.post(f"{BASE}/api/takeoffs/corps-etat/ouvrages", headers=pro_h,
                          json={"name": "ZZ Cloison partagee", "poste": "cloison",
                                "params": {"with_isolation": True}, "margin_pct": 10, "shared": True}, timeout=30)
        assert r.status_code == 200, r.text[:300]
        ov = r.json()["ouvrage"]
        shared_id = ov["ouvrage_id"]
        assert ov["is_shared"] is True and ov["is_mine"] is True

        # pro creates non-shared
        r2 = requests.post(f"{BASE}/api/takeoffs/corps-etat/ouvrages", headers=pro_h,
                           json={"name": "ZZ Cloison perso", "poste": "cloison",
                                 "params": {}, "margin_pct": 5, "shared": False}, timeout=30)
        assert r2.status_code == 200, r2.text[:300]
        priv_id = r2.json()["ouvrage"]["ouvrage_id"]

        # collegue GET list
        gl = requests.get(f"{BASE}/api/takeoffs/corps-etat/ouvrages", headers=coll_h, timeout=30)
        assert gl.status_code == 200
        rows = gl.json()["ouvrages"]
        ids = {r["ouvrage_id"]: r for r in rows}
        assert shared_id in ids, "shared not visible to collegue"
        assert priv_id not in ids, "private ouvrage should NOT be visible to collegue"
        shared_row = ids[shared_id]
        assert shared_row["is_shared"] is True
        assert shared_row["is_mine"] is False
        assert shared_row.get("owner_name"), "owner_name empty"

        # collegue tries delete (no-op / non-owner)
        dl = requests.delete(f"{BASE}/api/takeoffs/corps-etat/ouvrages/{shared_id}", headers=coll_h, timeout=30)
        assert dl.status_code in (200, 204)
        # still visible to collegue
        gl2 = requests.get(f"{BASE}/api/takeoffs/corps-etat/ouvrages", headers=coll_h, timeout=30)
        assert shared_id in {r["ouvrage_id"] for r in gl2.json()["ouvrages"]}, \
            "collegue delete must be no-op; ouvrage should still be visible"

        # pro can delete
        dl2 = requests.delete(f"{BASE}/api/takeoffs/corps-etat/ouvrages/{shared_id}", headers=pro_h, timeout=30)
        assert dl2.status_code in (200, 204)
        # cleanup private
        requests.delete(f"{BASE}/api/takeoffs/corps-etat/ouvrages/{priv_id}", headers=pro_h, timeout=30)

        # confirm removed
        gl3 = requests.get(f"{BASE}/api/takeoffs/corps-etat/ouvrages", headers=coll_h, timeout=30)
        assert shared_id not in {r["ouvrage_id"] for r in gl3.json()["ouvrages"]}


def _tiny_png():
    # 200x200 white PNG generated with Pillow (bigger, valid)
    from PIL import Image
    buf = io.BytesIO()
    Image.new("RGB", (200, 200), "white").save(buf, format="PNG")
    return buf.getvalue()


def _upload_plan(headers, display_name):
    files = {"file": (f"{display_name}.png", _tiny_png(), "image/png")}
    data = {"display_name": display_name, "wait": "true"}
    r = requests.post(f"{BASE}/api/takeoffs/upload", headers=headers, files=files, data=data, timeout=60)
    return r


class TestUploadDisplayName:
    def test_upload_with_display_name(self, pro_h):
        r = _upload_plan(pro_h, "ZZ Plan RDC Villa")
        assert r.status_code == 200, r.text[:300]
        d = r.json()
        plan_id = d.get("plan_id")
        assert plan_id
        assert d.get("filename") == "ZZ Plan RDC Villa"
        assert d.get("kind") == "image"
        # cleanup
        requests.delete(f"{BASE}/api/takeoffs/{plan_id}", headers=pro_h, timeout=30)


class TestMultilevelGroups:
    def test_group_crud_and_consolidation(self, pro_h):
        p1 = _upload_plan(pro_h, "ZZ Fondations")
        p2 = _upload_plan(pro_h, "ZZ RDC")
        assert p1.status_code == 200 and p2.status_code == 200
        pid1 = p1.json()["plan_id"]
        pid2 = p2.json()["plan_id"]
        try:
            body = {"name": "ZZ Villa multi-niveaux",
                    "levels": [{"plan_id": pid1, "level_label": "Fondations"},
                               {"plan_id": pid2, "level_label": "RDC"}]}
            r = requests.post(f"{BASE}/api/takeoffs/multilevel/groups", headers=pro_h, json=body, timeout=30)
            assert r.status_code == 200, r.text[:300]
            group_id = r.json()["group"]["group_id"]

            # list with filenames
            lst = requests.get(f"{BASE}/api/takeoffs/multilevel/groups", headers=pro_h, timeout=30)
            assert lst.status_code == 200
            g = next((x for x in lst.json()["groups"] if x["group_id"] == group_id), None)
            assert g is not None
            fns = [lv.get("filename") for lv in g["levels"]]
            assert "ZZ Fondations" in fns and "ZZ RDC" in fns

            # consolidated
            det = requests.get(f"{BASE}/api/takeoffs/multilevel/groups/{group_id}?margin_pct=10",
                               headers=pro_h, timeout=30)
            assert det.status_code == 200, det.text[:300]
            dj = det.json()
            assert "totals" in dj
            for lv in dj["levels"]:
                assert "consolidated" in lv
                assert "metre" in lv["consolidated"]
                assert "chiffrage" in lv["consolidated"]
                assert "area_m2" in lv["consolidated"]["metre"]
                assert "length_ml" in lv["consolidated"]["metre"]
            for k in ("ht_with_margin", "ttc", "area_m2", "length_ml"):
                assert k in dj["totals"]

            # rename
            up = requests.put(f"{BASE}/api/takeoffs/multilevel/groups/{group_id}", headers=pro_h,
                              json={"name": "ZZ Villa renamed",
                                    "levels": [{"plan_id": pid1, "level_label": "Fondations"},
                                               {"plan_id": pid2, "level_label": "RDC"}]}, timeout=30)
            assert up.status_code == 200
            det2 = requests.get(f"{BASE}/api/takeoffs/multilevel/groups/{group_id}?margin_pct=0",
                                headers=pro_h, timeout=30)
            assert det2.json()["name"] == "ZZ Villa renamed"

            # delete
            dl = requests.delete(f"{BASE}/api/takeoffs/multilevel/groups/{group_id}", headers=pro_h, timeout=30)
            assert dl.status_code in (200, 204)
            got = requests.get(f"{BASE}/api/takeoffs/multilevel/groups/{group_id}", headers=pro_h, timeout=30)
            assert got.status_code == 404
        finally:
            requests.delete(f"{BASE}/api/takeoffs/{pid1}", headers=pro_h, timeout=30)
            requests.delete(f"{BASE}/api/takeoffs/{pid2}", headers=pro_h, timeout=30)
