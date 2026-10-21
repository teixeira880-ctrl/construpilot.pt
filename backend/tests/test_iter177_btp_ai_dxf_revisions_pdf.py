"""Iter177 — ConstruPilot IA BTP additions:
   (1) DXF elements + level height assumption
   (2) Revisions + diff + amendment-draft + quote impact
   (3) PDF analysis report
"""
import os
import time
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://pilot-build-demo.preview.emergentagent.com").rstrip("/")
PLAN_DXF = "plan_f44477cd6049"
PLAN_REV = "plan_619e41f98d6b"

PRO_EMAIL = "pro@construpilot.fr"
PRO_PASSWORD = "Pro2026!"
ADMIN_EMAIL = "admin@construpilot.fr"
ADMIN_PASSWORD = "Construpilot2026!"


def _login(email, password):
    r = requests.post(f"{BASE_URL}/api/auth/login", json={"email": email, "password": password}, timeout=30)
    assert r.status_code == 200, f"login {email}: {r.status_code} {r.text[:200]}"
    return r.json()["token"]


@pytest.fixture(scope="module")
def pro_hdr():
    return {"Authorization": f"Bearer {_login(PRO_EMAIL, PRO_PASSWORD)}"}


@pytest.fixture(scope="module")
def admin_hdr():
    return {"Authorization": f"Bearer {_login(ADMIN_EMAIL, ADMIN_PASSWORD)}"}


# -------------------- DXF elements --------------------
def test_dxf_analysis_shape(pro_hdr):
    r = requests.get(f"{BASE_URL}/api/btp-ai/plans/{PLAN_DXF}/analysis", headers=pro_hdr, timeout=120)
    assert r.status_code == 200, r.text[:300]
    j = r.json()
    a = j["analysis"]
    assert a.get("has_dxf") is True, f"has_dxf missing: {a}"
    elements = j["elements"]
    murs = [e for e in elements if e["type"] == "mur"]
    poutres = [e for e in elements if e["type"] == "poutre"]
    niveaux = [e for e in elements if e["type"] == "niveau"]
    assert len(murs) == 623, f"murs count {len(murs)}"
    assert len(poutres) == 29, f"poutres count {len(poutres)}"
    assert len(niveaux) == 1, f"niveaux count {len(niveaux)}"
    # dimension source & detail
    sample = murs[0]
    long_dim = (sample.get("dimensions") or {}).get("longueur_m")
    assert long_dim and long_dim.get("source") == "mesuré", long_dim
    assert (long_dim.get("detail") or "").startswith("lu dans le DXF (calque"), long_dim.get("detail")

    quantities = j["quantities"]
    rules = {q.get("rule") for q in quantities}
    assert "mur_dxf_lineaire" in rules
    assert "mur_dxf_volume" in rules
    assert "poutre_lineaire" in rules

    # mur_dxf_lineaire → to_verify ; mur_dxf_volume → undetermined + note
    lin_lines = [q for q in quantities if q["rule"] == "mur_dxf_lineaire"]
    vol_lines = [q for q in quantities if q["rule"] == "mur_dxf_volume"]
    assert lin_lines and all(q["status"] == "to_verify" for q in lin_lines)
    assert vol_lines and all(q["status"] == "undetermined" for q in vol_lines)
    assert any("hauteur du niveau à déclarer" in (q.get("note") or "") for q in vol_lines)

    # lot
    lots = {q.get("lot") for q in quantities}
    assert "Gros œuvre / béton (DXF)" in lots, lots

    # missing entries
    missing = a.get("missing") or []
    assert any("hauteur sous dalle manquante" in (m.get("message", "").lower())
               for m in missing), f"no level height missing: {missing[:3]}"
    # corps < 8 cm exclusion note somewhere
    all_msgs = " ".join(m.get("message", "") for m in missing)
    assert "corps < 8" in all_msgs, f"corps < 8 cm exclusion note absent in: {all_msgs[:400]}"


def test_dxf_level_assumption_flow(pro_hdr):
    # Fetch current analysis to pick niveau element_id and one mur_dxf_volume line
    r = requests.get(f"{BASE_URL}/api/btp-ai/plans/{PLAN_DXF}/analysis", headers=pro_hdr, timeout=120)
    j = r.json()
    niveau = next(e for e in j["elements"] if e["type"] == "niveau")
    m01_vol = next((q for q in j["quantities"] if q["rule"] == "mur_dxf_volume"
                    and "M01" in (q.get("designation") or "")), None)
    # Declare 2.7
    r2 = requests.put(f"{BASE_URL}/api/btp-ai/plans/{PLAN_DXF}/elements/{niveau['element_id']}/assumptions",
                      json={"hauteur_m": 2.7, "reason": "test coupe"}, headers=pro_hdr, timeout=120)
    assert r2.status_code == 200, r2.text[:300]
    # Re-fetch
    r3 = requests.get(f"{BASE_URL}/api/btp-ai/plans/{PLAN_DXF}/analysis", headers=pro_hdr, timeout=120)
    j3 = r3.json()
    vol_lines = [q for q in j3["quantities"] if q["rule"] == "mur_dxf_volume"]
    assert vol_lines and all(q["status"] == "provisional" for q in vol_lines), \
        [q["status"] for q in vol_lines[:5]]
    # Check one M01: aire 2.824 → 7.625 (tolerance)
    if m01_vol:
        m01_after = next((q for q in vol_lines if q["quantity_id"] == m01_vol["quantity_id"]), None)
        if m01_after:
            assert m01_after.get("assumptions"), m01_after
            assert m01_after["assumptions"][0]["name"] == "hauteur du niveau", m01_after["assumptions"][0]
            # verify quantity ≈ 7.625 with wide tolerance
            qn = m01_after.get("quantity_net")
            if qn is not None:
                assert abs(qn - 7.625) < 0.5, f"M01 volume {qn} vs 7.625"
    # missing covered_by_assumption
    miss = [m for m in (j3["analysis"].get("missing") or [])
            if "level" in (m.get("kind") or "").lower() or "hauteur" in (m.get("label", "").lower())]
    if miss:
        assert any(m.get("covered_by_assumption") for m in miss), miss[:3]

    # Reset (empty)
    r4 = requests.put(f"{BASE_URL}/api/btp-ai/plans/{PLAN_DXF}/elements/{niveau['element_id']}/assumptions",
                      json={"hauteur_m": None, "reason": ""}, headers=pro_hdr, timeout=120)
    assert r4.status_code == 200
    r5 = requests.get(f"{BASE_URL}/api/btp-ai/plans/{PLAN_DXF}/analysis", headers=pro_hdr, timeout=120)
    j5 = r5.json()
    vol_lines2 = [q for q in j5["quantities"] if q["rule"] == "mur_dxf_volume"]
    assert vol_lines2 and all(q["status"] == "undetermined" for q in vol_lines2)


# -------------------- Revisions & diff --------------------
def test_revisions_list(pro_hdr):
    r = requests.get(f"{BASE_URL}/api/btp-ai/plans/{PLAN_REV}/revisions", headers=pro_hdr, timeout=30)
    assert r.status_code == 200
    revs = r.json()["revisions"]
    assert len(revs) >= 2, f"only {len(revs)} revision(s)"
    for rev in revs:
        assert "revision" in rev and "at" in rev and "count" in rev


def test_revisions_diff_invalid_returns_404(pro_hdr):
    r = requests.get(f"{BASE_URL}/api/btp-ai/plans/{PLAN_REV}/revisions/diff?a=BAD&b=NADA", headers=pro_hdr, timeout=30)
    assert r.status_code == 404


def test_revisions_diff_and_amendment(pro_hdr):
    # Change assumption on Salon mur → creates new revision
    a0 = requests.get(f"{BASE_URL}/api/btp-ai/plans/{PLAN_REV}/analysis", headers=pro_hdr, timeout=60).json()
    mur = next(e for e in a0["elements"] if e["type"] == "mur")
    r_put = requests.put(f"{BASE_URL}/api/btp-ai/plans/{PLAN_REV}/elements/{mur['element_id']}/assumptions",
                         json={"epaisseur_m": 0.3, "reason": "test agent"}, headers=pro_hdr, timeout=60)
    assert r_put.status_code == 200

    revs = requests.get(f"{BASE_URL}/api/btp-ai/plans/{PLAN_REV}/revisions", headers=pro_hdr, timeout=30).json()["revisions"]
    assert len(revs) >= 2
    # revs sorted desc by at → newest is [0]
    newest = revs[0]["revision"]
    older = revs[-1]["revision"]

    d = requests.get(f"{BASE_URL}/api/btp-ai/plans/{PLAN_REV}/revisions/diff",
                     params={"a": older, "b": newest}, headers=pro_hdr, timeout=30)
    assert d.status_code == 200, d.text[:300]
    dj = d.json()
    assert "rows" in dj and "changed" in dj and "impact_total_ht" in dj
    assert "priced_rows" in dj and "unpriced_changes" in dj and "linked_documents" in dj and "note" in dj
    for row in dj["rows"]:
        assert row["kind"] in ("ajoutée", "supprimée", "modifiée", "inchangée", "indéterminée")

    # Look for Murs volume Salon modifiée (delta should reflect epaisseur change)
    salon_vol = [r for r in dj["rows"]
                 if "volume" in r["designation"].lower() and "salon" in r["designation"].lower()]
    if salon_vol:
        row = salon_vol[0]
        # Just verify delta exists and is positive (thickness increased)
        if row["kind"] == "modifiée" and row.get("delta") is not None:
            assert row["delta"] > 0, row

    # Amendment draft
    if dj["changed"] > 0:
        adr = requests.post(f"{BASE_URL}/api/btp-ai/plans/{PLAN_REV}/amendment-draft",
                            json={"a": older, "b": newest, "client_name": "TEST avenant agent"},
                            headers=pro_hdr, timeout=60)
        assert adr.status_code == 200, adr.text[:300]
        aj = adr.json()
        assert aj["ok"] is True and aj.get("doc_id") and aj["lines"] >= 1
        assert aj.get("editor_url", "").endswith(aj["doc_id"])
        doc_id = aj["doc_id"]

        # Fetch document
        gd = requests.get(f"{BASE_URL}/api/documents/{doc_id}", headers=pro_hdr, timeout=30)
        if gd.status_code == 200:
            doc = gd.json()
            title = (doc.get("title") or doc.get("document", {}).get("title") or "")
            assert title.startswith("Avenant —"), f"title={title}"
            lines = doc.get("lines") or doc.get("document", {}).get("lines") or []
            if lines:
                assert any((l.get("designation") or "").startswith("Avenant —") for l in lines), \
                    [l.get("designation") for l in lines[:3]]
                # description contains 'Métré q_' and 'avant 10 → après 15' (if salon vol present)
                desc_join = " || ".join(l.get("description") or "" for l in lines)
                assert "Métré q_" in desc_join, desc_join[:400]

        # Cleanup amendment draft
        requests.delete(f"{BASE_URL}/api/documents/{doc_id}", headers=pro_hdr, timeout=30)
        requests.delete(f"{BASE_URL}/api/trash/document/{doc_id}", headers=pro_hdr, timeout=30)

    # Restore assumption
    r_rst = requests.put(f"{BASE_URL}/api/btp-ai/plans/{PLAN_REV}/elements/{mur['element_id']}/assumptions",
                        json={"epaisseur_m": 0.2, "reason": "bloc béton 20 cm supposé"},
                        headers=pro_hdr, timeout=60)
    assert r_rst.status_code == 200


def test_amendment_no_changes_returns_400(pro_hdr):
    revs = requests.get(f"{BASE_URL}/api/btp-ai/plans/{PLAN_REV}/revisions", headers=pro_hdr, timeout=30).json()["revisions"]
    if not revs:
        pytest.skip("no revisions")
    same = revs[0]["revision"]
    r = requests.post(f"{BASE_URL}/api/btp-ai/plans/{PLAN_REV}/amendment-draft",
                      json={"a": same, "b": same, "client_name": "TEST"}, headers=pro_hdr, timeout=30)
    assert r.status_code == 400, r.text[:200]


# -------------------- PDF report --------------------
def test_pdf_report_plan_rev(pro_hdr):
    r = requests.get(f"{BASE_URL}/api/btp-ai/plans/{PLAN_REV}/report.pdf", headers=pro_hdr, timeout=60)
    assert r.status_code == 200
    assert "application/pdf" in r.headers.get("content-type", "").lower()
    assert len(r.content) > 5 * 1024, f"pdf size {len(r.content)}"
    # simple text-search — pypdf extraction
    try:
        from pypdf import PdfReader
        import io
        reader = PdfReader(io.BytesIO(r.content))
        text = "\n".join((p.extract_text() or "") for p in reader.pages)
        assert "ne constitue pas une note de calcul" in text, text[:800]
        assert "Hypothèses" in text or "Hypotheses" in text, text[:800]
        assert "Quantités par lot" in text or "Quantites par lot" in text, text[:800]
    except ImportError:
        pytest.skip("pypdf not installed")


def test_pdf_report_dxf(pro_hdr):
    r = requests.get(f"{BASE_URL}/api/btp-ai/plans/{PLAN_DXF}/report.pdf", headers=pro_hdr, timeout=120)
    assert r.status_code == 200
    assert "application/pdf" in r.headers.get("content-type", "").lower()
    assert len(r.content) > 5 * 1024


def test_pdf_report_other_user_404(admin_hdr):
    r = requests.get(f"{BASE_URL}/api/btp-ai/plans/{PLAN_REV}/report.pdf", headers=admin_hdr, timeout=30)
    assert r.status_code == 404


# -------------------- Quote impact pricing --------------------
def test_quote_impact_pricing(pro_hdr):
    """Set unit_price_ht=100 on Salon volume line, verify diff impact_ht = delta × 100 and linked_documents."""
    # 1. Create quote draft
    r = requests.post(f"{BASE_URL}/api/btp-ai/plans/{PLAN_REV}/quote-draft",
                      json={"client_name": "TEST prix"}, headers=pro_hdr, timeout=60)
    assert r.status_code == 200, r.text[:300]
    doc_id = r.json()["doc_id"]

    try:
        # 2. Fetch document
        gd = requests.get(f"{BASE_URL}/api/documents/{doc_id}", headers=pro_hdr, timeout=30)
        assert gd.status_code == 200
        doc = gd.json()
        lines = doc.get("lines") or []
        # Find the Salon volume line (designation starts 'Métré' — description in save_quote becomes description; designation is q designation)
        target_idx = None
        for i, ln in enumerate(lines):
            desc = (ln.get("description") or "")
            desig = (ln.get("designation") or "")
            if desc.startswith("Métré q_") and "volume" in desig.lower() and "salon" in desig.lower():
                target_idx = i
                break
        if target_idx is None:
            pytest.skip("Salon volume line not found in doc")

        # 3. Prepare full PUT body — map back to DocLine schema
        put_lines = []
        for i, ln in enumerate(lines):
            put_lines.append({
                "line_id": ln.get("line_id"),
                "designation": ln.get("designation", ""),
                "description": ln.get("description", ""),
                "unit": ln.get("unit", "u"),
                "qty": ln.get("qty") or ln.get("quantity") or 1,
                "unit_price_ht": 100.0 if i == target_idx else (ln.get("unit_price_ht") or 0),
                "cost_price_ht": ln.get("cost_price_ht") or 0,
                "vat_rate": ln.get("vat_rate") or 10,
            })
        put_body = {
            "doc_type": doc.get("doc_type", "quote"),
            "client_id": doc.get("client_id"),
            "title": doc.get("title", ""),
            "lines": put_lines,
            "notes": doc.get("notes", ""),
            "payment_terms": doc.get("payment_terms", ""),
            "deposit_pct": doc.get("deposit_pct", 0),
        }
        up = requests.put(f"{BASE_URL}/api/documents/{doc_id}", json=put_body, headers=pro_hdr, timeout=30)
        assert up.status_code == 200, f"PUT doc failed: {up.status_code} {up.text[:300]}"

        # 4. Trigger a revision by changing assumption
        a0 = requests.get(f"{BASE_URL}/api/btp-ai/plans/{PLAN_REV}/analysis", headers=pro_hdr, timeout=60).json()
        mur = next(e for e in a0["elements"] if e["type"] == "mur")
        # Read revisions BEFORE change
        revs_before = requests.get(f"{BASE_URL}/api/btp-ai/plans/{PLAN_REV}/revisions", headers=pro_hdr, timeout=30).json()["revisions"]
        older = revs_before[0]["revision"]

        requests.put(f"{BASE_URL}/api/btp-ai/plans/{PLAN_REV}/elements/{mur['element_id']}/assumptions",
                     json={"epaisseur_m": 0.3, "reason": "test prix"}, headers=pro_hdr, timeout=60)

        revs_after = requests.get(f"{BASE_URL}/api/btp-ai/plans/{PLAN_REV}/revisions", headers=pro_hdr, timeout=30).json()["revisions"]
        newer = revs_after[0]["revision"]

        # 5. Diff
        d = requests.get(f"{BASE_URL}/api/btp-ai/plans/{PLAN_REV}/revisions/diff",
                         params={"a": older, "b": newer}, headers=pro_hdr, timeout=30).json()
        salon_vol = [row for row in d["rows"]
                     if "volume" in row["designation"].lower() and "salon" in row["designation"].lower()]
        assert salon_vol, "no salon volume in diff"
        row = salon_vol[0]
        assert row["quote"] is not None, f"quote link missing on row: {row}"
        assert row["quote"].get("unit_price_ht") == 100, row["quote"]
        expected_impact = round((row["delta"] or 0) * 100, 2)
        assert abs((row["impact_ht"] or 0) - expected_impact) < 0.01, f"impact {row['impact_ht']} vs {expected_impact}"
        # linked_documents
        linked_ids = [ld["doc_id"] for ld in d["linked_documents"]]
        assert doc_id in linked_ids, f"doc {doc_id} not in linked {linked_ids}"

        # 6. Restore assumption
        requests.put(f"{BASE_URL}/api/btp-ai/plans/{PLAN_REV}/elements/{mur['element_id']}/assumptions",
                     json={"epaisseur_m": 0.2, "reason": "bloc béton 20 cm supposé"}, headers=pro_hdr, timeout=60)
    finally:
        # Cleanup doc
        requests.delete(f"{BASE_URL}/api/documents/{doc_id}", headers=pro_hdr, timeout=30)
        requests.delete(f"{BASE_URL}/api/trash/document/{doc_id}", headers=pro_hdr, timeout=30)
