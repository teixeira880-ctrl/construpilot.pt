"""Backend integration tests for iter170/171: native dimension chains, unified PDF w/ crops, calibration."""
import io
import os
import requests
import pytest
from PIL import Image

LOCAL = "http://localhost:8001"
PLAN_DWG = "plan_db4a3ccd5e09"
PLAN_PDF = "plan_3e4bb8efb992"
CONV_ID = open("/app/memory/.conv_dwg2").read().strip()


@pytest.fixture(scope="module")
def pro_session():
    s = requests.Session()
    r = s.post(f"{LOCAL}/api/auth/login", json={"email": "pro@construpilot.fr", "password": "Pro2026!"})
    assert r.status_code == 200, r.text
    tok = r.json().get("token")
    assert tok, r.json()
    s.headers.update({"Authorization": f"Bearer {tok}"})
    return s


# --- Native chains crop endpoint: must be a legible vector re-render, not a solid black blob ---
def test_dwg_crop_vector_render(pro_session):
    r = pro_session.get(f"{LOCAL}/api/assistant/plans/{PLAN_DWG}/crop", params={"page": 0, "box": "0.30,0.40,0.36,0.41"})
    assert r.status_code == 200, r.text[:400]
    assert r.headers.get("content-type", "").startswith("image/"), r.headers
    img = Image.open(io.BytesIO(r.content)).convert("L")
    px = list(img.getdata())
    dark_ratio = sum(1 for p in px if p < 40) / len(px)
    assert dark_ratio < 0.40, f"crop is a black blob: dark_ratio={dark_ratio:.3f}, size={img.size}"


# --- Unified PDF (annotated crops) ---
def test_conv_report_pdf_annotated(pro_session):
    r = pro_session.get(f"{LOCAL}/api/assistant/conversations/{CONV_ID}/report.pdf", timeout=180)
    assert r.status_code == 200, r.text[:400]
    assert r.headers.get("content-type", "").startswith("application/pdf")
    body = r.content
    assert len(body) > 100_000
    # extract text via pypdf
    from pypdf import PdfReader
    reader = PdfReader(io.BytesIO(body))
    assert len(reader.pages) >= 5, f"only {len(reader.pages)} pages"
    text = "\n".join((p.extract_text() or "") for p in reader.pages)
    for marker in ["Extraits annotés du plan", "CA-01", "AES_COF_0100_R+1_B.dwg", "Analyse assistée par ConstruPilot"]:
        assert marker in text, f"missing marker: {marker!r}"


# --- Calculations: ≥40 native chains records, all confirmed & coherent ---
def test_calculations_native_chains(pro_session):
    r = pro_session.get(f"{LOCAL}/api/assistant/conversations/{CONV_ID}/calculations", timeout=60)
    assert r.status_code == 200, r.text[:400]
    payload = r.json()
    items = payload.get("calculations") if isinstance(payload, dict) else payload
    assert isinstance(items, list)
    natives = [it for it in items if it.get("origin") == "read_native_dimensions"]
    assert len(natives) >= 40, f"only {len(natives)} native chains"
    for it in natives[:10]:
        assert it.get("tool") == "check_dimension_chain", it.get("tool")
        args = it.get("args") or {}
        spans = args.get("spans") or []
        assert spans, "no spans"
        for sp in spans:
            assert sp.get("plan_id") == PLAN_DWG, sp
            box = sp.get("box")
            assert isinstance(box, list) and len(box) == 4, box
            assert all(isinstance(v, (int, float)) for v in box)
        result = it.get("result") or {}
        calc = result.get("calculation") or {}
        assert calc.get("state") == "confirmed", calc
        assert not (result.get("findings") or []), result.get("findings")


# --- Regression: PDF plan crop still returns 200 ---
def test_pdf_plan_crop_still_ok(pro_session):
    r = pro_session.get(f"{LOCAL}/api/assistant/plans/{PLAN_PDF}/crop", params={"page": 0, "box": "0.20,0.30,0.30,0.40"})
    assert r.status_code == 200, r.text[:200]

# --- Correction on a native record: adds a finding for the delta, and supersedes the chain ---
def test_correct_native_chain(pro_session):
    r = pro_session.get(f"{LOCAL}/api/assistant/conversations/{CONV_ID}/calculations", timeout=60)
    assert r.status_code == 200
    items = r.json().get("calculations") or []
    natives = [it for it in items if it.get("origin") == "read_native_dimensions"]
    # Pick one that is not already superseded
    target = None
    for it in natives:
        if not it.get("superseded_by"):
            spans = (it.get("args") or {}).get("spans") or []
            if spans and spans[0].get("label") and isinstance(spans[0].get("value_m"), (int, float)):
                target = it
                break
    assert target, "no active native chain found"
    ref = target["calc_ref"]
    span = target["args"]["spans"][0]
    label = span["label"]
    new_value = round(float(span["value_m"]) + 0.05, 4)
    r2 = pro_session.post(
        f"{LOCAL}/api/assistant/calculations/{ref}/correct",
        json={"label": label, "value_m": new_value},
        timeout=60,
    )
    assert r2.status_code == 200, r2.text[:400]
    body = r2.json()
    # Response should carry an updated calculation with at least one finding
    result = body.get("result") or body.get("calculation", {}).get("result") or body
    findings = result.get("findings") if isinstance(result, dict) else None
    if findings is None:
        # Fallback: pull the newest record for that chain and inspect
        r3 = pro_session.get(f"{LOCAL}/api/assistant/conversations/{CONV_ID}/calculations", timeout=60)
        latest = [i for i in r3.json().get("calculations", []) if i.get("chain_id") == target.get("chain_id")]
        latest.sort(key=lambda x: x.get("created_at", ""), reverse=True)
        assert latest, "no chain records after correction"
        findings = ((latest[0].get("result") or {}).get("findings")) or []
    assert findings and len(findings) >= 1, f"expected finding after 5cm delta, got {findings!r}"
