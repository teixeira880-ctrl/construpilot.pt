"""Iteration 171 backend API tests."""
import os
import re
import io
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://pilot-build-demo.preview.emergentagent.com").rstrip("/")
ADMIN_EMAIL = "admin@construpilot.fr"
ADMIN_PASSWORD = "Construpilot2026!"


@pytest.fixture(scope="module")
def admin_session():
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}, timeout=30)
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text[:200]}"
    data = r.json()
    tok = data.get("access_token") or data.get("token")
    if tok:
        s.headers.update({"Authorization": f"Bearer {tok}"})
    return s


def test_report_pdf(admin_session):
    r = admin_session.get(f"{BASE_URL}/api/assistant/conversations/conv_eae601c4e2/report.pdf", timeout=60)
    assert r.status_code == 200, f"got {r.status_code}: {r.text[:200]}"
    assert "pdf" in r.headers.get("content-type", "").lower()
    body = r.content
    assert body.startswith(b"%PDF"), "not a PDF"
    # extract text
    try:
        import pypdf
        reader = pypdf.PdfReader(io.BytesIO(body))
        text = "\n".join((p.extract_text() or "") for p in reader.pages)
    except Exception:
        text = body.decode("latin-1", errors="ignore")
    print("PDF pages/length:", len(body))
    assert ("rebar_mass_ha" in text) or ("Nomenclature" in text), f"missing rebar/Nomenclature marker (text sample: {text[:500]})"
    assert "GO-B3-R0-302" in text, "missing GO-B3-R0-302 doc code"
    assert "Indice 0" in text and "09/06/2023" in text, "missing revision index/date"


def test_calculations(admin_session):
    r = admin_session.get(f"{BASE_URL}/api/assistant/conversations/conv_eae601c4e2/calculations", timeout=30)
    assert r.status_code == 200, f"got {r.status_code}: {r.text[:200]}"
    data = r.json()
    items = data if isinstance(data, list) else data.get("items") or data.get("calculations") or []
    print("calc items:", len(items))
    rebar = [c for c in items if c.get("tool") == "read_rebar_schedule"]
    assert rebar, "no read_rebar_schedule record found"
    rec = rebar[0]
    result = rec.get("result") or {}
    assert result.get("mode") == "native_text", f"mode={result.get('mode')}"
    native = result.get("native") or {}
    ha = native.get("ha_bars") or {}
    assert ha.get("count") == 71, f"ha count={ha.get('count')}"


def test_tool_gate_requires_vision():
    """plan_f9c41827c6ce page 5 without native text → requires_vision True, no OpenAI call."""
    import sys
    sys.path.insert(0, "/app/backend")
    from motor.motor_asyncio import AsyncIOMotorClient
    from engines.metre import rebar_tool
    import asyncio
    from dotenv import load_dotenv
    load_dotenv("/app/backend/.env")

    async def _run():
        client = AsyncIOMotorClient(os.environ["MONGO_URL"])
        db = client[os.environ["DB_NAME"]]
        try:
            r = await rebar_tool.run_read_rebar_schedule(
                db, user_id="user_1d2b550f454f", conversation_id="qa_tmp",
                plan_id="plan_f9c41827c6ce", page=5, allow_vision=False, now="x",
            )
            print("vision-gate result:", r)
            assert r.get("requires_vision") is True, f"missing requires_vision: {r}"
            assert r.get("error"), "no error field"

            # DWG plan
            r2 = await rebar_tool.run_read_rebar_schedule(
                db, user_id="user_1d2b550f454f", conversation_id="qa_tmp",
                plan_id="plan_2c335a8b9af5", page=0, allow_vision=False, now="x",
            )
            print("dwg-gate result:", r2)
            assert r2.get("error"), "no error for DWG"
            assert "read_native_dimensions" in (r2.get("error") or ""), f"missing hint: {r2}"

            # 1-based page acceptance
            r3 = await rebar_tool.run_read_rebar_schedule(
                db, user_id="user_1d2b550f454f", conversation_id="qa_tmp",
                plan_id="plan_ad337e8be1a2", page=1, allow_vision=False, now="x",
            )
            print("1based result keys:", list(r3.keys()))
            assert r3.get("result", {}).get("page") == 0 or r3.get("page") == 0 or r3.get("page_note"), f"1based normalize: {r3}"
        finally:
            # cleanup any qa_tmp records
            await db.assistant_calculations.delete_many({"conversation_id": "qa_tmp"})
            client.close()

    asyncio.get_event_loop().run_until_complete(_run())
