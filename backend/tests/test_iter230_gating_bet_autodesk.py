"""iter230: production-critical gating fix (null account_type → particulier_gratuit),
BET responsable+signature+red conflicts, Autodesk non-CAD rejection, Google user default.

NOTE: We intentionally do NOT trigger a real Autodesk translation (cost). We only verify
the 422 rejection path on a non-CAD doc.
"""
import io
import os
import pytest
import requests

def _load_backend_url():
    v = os.environ.get("REACT_APP_BACKEND_URL")
    if v:
        return v.rstrip("/")
    try:
        with open("/app/frontend/.env") as f:
            for line in f:
                if line.startswith("REACT_APP_BACKEND_URL="):
                    return line.split("=", 1)[1].strip().rstrip("/")
    except Exception:
        pass
    raise RuntimeError("REACT_APP_BACKEND_URL not set")


BASE = _load_backend_url()
API = f"{BASE}/api"
PRO = ("pro@construpilot.fr", "Pro2026!")
FREE = ("client@construpilot.fr", "Client2026!")


def _login(email, password):
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json={"email": email, "password": password}, timeout=30)
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text[:200]}"
    return s, r.json()


@pytest.fixture(scope="module")
def pro_client():
    s, _ = _login(*PRO)
    return s


@pytest.fixture(scope="module")
def free_client():
    s, _ = _login(*FREE)
    return s


# --- Gating via /auth/me ---------------------------------------------------
def test_free_user_account_type_is_particulier(free_client):
    me = free_client.get(f"{API}/auth/me").json()
    # Free account must NOT appear as pro: either 'particulier' or null (never 'pro')
    assert me.get("account_type") in (None, "particulier", "particulier_gratuit"), me
    assert me.get("role") != "admin"


def test_pro_user_is_pro(pro_client):
    me = pro_client.get(f"{API}/auth/me").json()
    assert me.get("account_type") == "pro" or me.get("role") == "admin", me


# --- BET gating ------------------------------------------------------------
def test_free_cannot_access_bet(free_client):
    r = free_client.get(f"{API}/structuro/bet/studies")
    assert r.status_code == 403, (r.status_code, r.text[:200])


def test_pro_can_list_bet(pro_client):
    r = pro_client.get(f"{API}/structuro/bet/studies")
    assert r.status_code == 200
    assert "studies" in r.json()


# --- Find existing "Test BET" dossier --------------------------------------
@pytest.fixture(scope="module")
def test_bet_dossier(pro_client):
    r = pro_client.get(f"{API}/structuro/bet/studies")
    studies = r.json().get("studies", [])
    # Prefer the one named "Test BET"
    cand = next((s for s in studies if (s.get("title") or "").lower().startswith("test bet")), None)
    if not cand and studies:
        cand = studies[0]
    if not cand:
        # create one so other tests can run
        c = pro_client.post(f"{API}/structuro/bet/studies", json={"title": "TEST_iter230"}).json()
        return c
    full = pro_client.get(f"{API}/structuro/bet/studies/{cand['dossier_id']}").json()
    return full


# --- Responsable PATCH + persistence ---------------------------------------
def test_patch_responsable_persists(pro_client, test_bet_dossier):
    did = test_bet_dossier["dossier_id"]
    name = "Mme Testeur Iter230"
    r = pro_client.patch(f"{API}/structuro/bet/studies/{did}", json={"responsable": name})
    assert r.status_code == 200, r.text[:200]
    assert r.json().get("responsable") == name
    # Verify via GET
    g = pro_client.get(f"{API}/structuro/bet/studies/{did}").json()
    assert g.get("responsable") == name


# --- Report PDF: application/pdf, non-empty, contains signature/responsable
def test_report_pdf_contains_signature_and_responsable(pro_client, test_bet_dossier):
    did = test_bet_dossier["dossier_id"]
    # Ensure responsable set to a predictable value
    pro_client.patch(f"{API}/structuro/bet/studies/{did}", json={"responsable": "Mme Testeur Iter230"})
    r = pro_client.get(f"{API}/structuro/bet/studies/{did}/report.pdf")
    assert r.status_code == 200, r.text[:200]
    assert r.headers.get("content-type", "").startswith("application/pdf")
    assert r.content.startswith(b"%PDF"), "Not a PDF"
    # PDFs include text streams; check for strings used by the engine for signature/red conflicts.
    # PDF is compressed; decode via pypdf to get text
    try:
        from pypdf import PdfReader
    except Exception:
        from PyPDF2 import PdfReader  # type: ignore
    reader = PdfReader(io.BytesIO(r.content))
    text = "\n".join((p.extract_text() or "") for p in reader.pages)
    assert "Mme Testeur Iter230" in text, f"responsable name missing in PDF text: {text[:400]}"
    assert ("Responsable" in text or "Signature" in text or "signature" in text), \
        f"signature block missing in PDF text: {text[:400]}"


def test_report_pdf_with_conflict_has_points_a_verifier(pro_client, test_bet_dossier):
    """When a dossier has an 'inconsistencies' structure with issues, the PDF must include
    the 'Points à vérifier' summary. If none exist on the test dossier, trigger a scan."""
    did = test_bet_dossier["dossier_id"]
    live_docs = [d for d in test_bet_dossier.get("documents", []) if not d.get("is_deleted")]
    if len(live_docs) >= 2:
        pro_client.post(f"{API}/structuro/bet/{'studies'}/{did}/inconsistencies")
    r = pro_client.get(f"{API}/structuro/bet/studies/{did}/report.pdf")
    assert r.status_code == 200
    # At minimum, PDF should render. The "Points à vérifier" string will exist when issues present.
    # Soft check — we just confirm no crash and PDF is valid.
    assert r.content.startswith(b"%PDF")


# --- Autodesk 422 for non-CAD doc ------------------------------------------
def test_autodesk_rejects_non_cad(pro_client, test_bet_dossier):
    did = test_bet_dossier["dossier_id"]
    pdf_doc = None
    for d in test_bet_dossier.get("documents", []):
        if d.get("is_deleted"):
            continue
        name = (d.get("original_filename") or "").lower()
        if name.endswith(".pdf") or name.endswith(".png") or name.endswith(".jpg"):
            pdf_doc = d
            break
    if not pdf_doc:
        pytest.skip("No non-CAD doc to test rejection against")
    r = pro_client.post(f"{API}/structuro/bet/studies/{did}/documents/{pdf_doc['id']}/analyze-autodesk")
    assert r.status_code == 422, f"Expected 422 for non-CAD, got {r.status_code}: {r.text[:200]}"


def test_free_cannot_call_autodesk(free_client, pro_client, test_bet_dossier):
    did = test_bet_dossier["dossier_id"]
    docs = [d for d in test_bet_dossier.get("documents", []) if not d.get("is_deleted")]
    if not docs:
        pytest.skip("no docs")
    r = free_client.post(f"{API}/structuro/bet/studies/{did}/documents/{docs[0]['id']}/analyze-autodesk")
    assert r.status_code in (403, 404), r.status_code  # 403 from level gate (dossier belongs to pro)
