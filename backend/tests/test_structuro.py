"""StructuroPilot — tests du Lot A backbone (invariants d'honnêteté)."""
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://pilot-build-demo.preview.emergentagent.com").rstrip("/")
EMAIL = "pro@construpilot.fr"
PASSWORD = "Pro2026!"


@pytest.fixture(scope="module")
def token():
    r = requests.post(f"{BASE_URL}/api/auth/login", json={"email": EMAIL, "password": PASSWORD}, timeout=30)
    assert r.status_code == 200, r.text
    data = r.json()
    tok = data.get("token") or data.get("access_token")
    assert tok, data
    return tok


@pytest.fixture(scope="module")
def client(token):
    s = requests.Session()
    s.headers.update({"Authorization": f"Bearer {token}", "Content-Type": "application/json"})
    return s


# --- /meta : moteur verrouillé ----------------------------------------------
def test_meta_calc_engine_locked(client):
    r = client.get(f"{BASE_URL}/api/structuro/meta", timeout=30)
    assert r.status_code == 200, r.text
    m = r.json()
    assert m["calc_engine_available"] is False
    assert m["rulepack"]["status"] == "non_qualifie"


# --- POST /studies : création ------------------------------------------------
def test_create_study_from_description(client):
    desc = ("Maison vers 1850, deux niveaux sur cave, murs en pierre ~50 cm, "
            "planchers bois. Ouverture ~2,40 m entre séjour et cuisine.")
    r = client.post(f"{BASE_URL}/api/structuro/studies", json={"description": desc}, timeout=120)
    assert r.status_code == 200, r.text
    s = r.json()
    assert s["output_level"] == "exploration"
    assert isinstance(s.get("facts"), list) and len(s["facts"]) > 0
    verifs = s.get("verifications", [])
    assert len(verifs) > 0
    assert all(v["status"] == "bloquee" for v in verifs), [v["status"] for v in verifs]
    assert len(s.get("questionnaire", [])) > 0
    # cleanup
    client.delete(f"{BASE_URL}/api/structuro/studies/{s['study_id']}", timeout=30)


# --- POST /studies/demo ------------------------------------------------------
@pytest.fixture(scope="module")
def demo_study(client):
    r = client.post(f"{BASE_URL}/api/structuro/studies/demo", timeout=60)
    assert r.status_code == 200, r.text
    s = r.json()
    yield s
    client.delete(f"{BASE_URL}/api/structuro/studies/{s['study_id']}", timeout=30)


def test_demo_levels_and_unknowns(demo_study):
    s = demo_study
    assert s["title"].startswith("DÉMO")
    assert len(s.get("levels", [])) >= 2
    data = s.get("data", {})
    for k in ["mur.materiau_resistance", "sol.portance", "plancher.sens_porteur"]:
        assert data.get(k, {}).get("source") == "inconnu", (k, data.get(k))


# --- Invariant de péremption / descente_charges -----------------------------
def _dc_status(s):
    return next((v["status"] for v in s["verifications"] if v["key"] == "descente_charges"), None)


def test_descente_charges_invariant(client, demo_study):
    sid = demo_study["study_id"]
    # Documenter les 4 entrées de descente_charges en source=mesure
    answers = [
        ("plancher.sens_porteur", "N-S", None),
        ("plancher.portee", 4.2, "m"),
        ("charges.permanentes", 1.5, "kN/m²"),
        ("charges.exploitation", 1.5, "kN/m²"),
    ]
    last = None
    for key, val, unit in answers:
        body = {"datum_key": key, "value": val, "unit": unit, "source": "mesure"}
        r = client.post(f"{BASE_URL}/api/structuro/studies/{sid}/answer", json=body, timeout=30)
        assert r.status_code == 200, r.text
        last = r.json()
    # descente_charges doit être en_attente_moteur, JAMAIS satisfaisante
    status = _dc_status(last)
    assert status == "en_attente_moteur", status
    # Aucun verif ne doit être "satisfaisante"
    for v in last["verifications"]:
        assert v["status"] in {"bloquee", "en_attente_moteur", "hors_domaine", "non_calculee", "perimee"}

    rev_before = last["revision"]

    # Remettre charges.exploitation en inconnu → doit reperimer
    r = client.post(f"{BASE_URL}/api/structuro/studies/{sid}/answer",
                    json={"datum_key": "charges.exploitation", "value": None, "source": "inconnu"}, timeout=30)
    assert r.status_code == 200, r.text
    s2 = r.json()
    assert _dc_status(s2) == "bloquee"
    assert s2["revision"] > rev_before, (s2["revision"], rev_before)


# --- Approbation : 409 tant qu'une verif est bloquée -------------------------
def test_approve_blocked_when_verif_bloquee(client, demo_study):
    sid = demo_study["study_id"]
    r = client.post(f"{BASE_URL}/api/structuro/studies/{sid}/approve",
                    json={"role": "Ingénieur", "scope": "test"}, timeout=30)
    assert r.status_code == 409, (r.status_code, r.text)


# --- Approve réussi : fournir toutes les données documentées ----------------
def test_approve_success_level_preliminaire(client):
    # Nouvelle étude démo isolée
    r = client.post(f"{BASE_URL}/api/structuro/studies/demo", timeout=60)
    assert r.status_code == 200
    s = r.json()
    sid = s["study_id"]
    try:
        # Documenter toutes les clefs requises par les 4 verifs du goal
        full = {
            "plancher.sens_porteur": ("N-S", None, "mesure"),
            "plancher.portee": (4.2, "m", "mesure"),
            "charges.permanentes": (1.5, "kN/m²", "document"),
            "charges.exploitation": (1.5, "kN/m²", "document"),
            "ouverture.portee": (2.4, "m", "mesure"),
            "ouverture.charges_reprises": (12, "kN/m", "document"),
            "poutre.appuis": ("Trumeaux 40cm", None, "mesure"),
            "poutre.maintien_lateral": ("Oui", None, "mesure"),
            "mur.epaisseur": (0.5, "m", "mesure"),
            "mur.materiau_resistance": (2.0, "MPa", "essai"),
            "ouverture.position": ("RDC M1", None, "mesure"),
            "charges.sur_appuis": (20, "kN", "document"),
            "fondation.geometrie": ("Semelle 60x40", None, "document"),
            "fondation.niveau_assise": (-1.2, "m", "document"),
            "sol.portance": (200, "kPa", "essai"),
        }
        for k, (v, u, src) in full.items():
            rr = client.post(f"{BASE_URL}/api/structuro/studies/{sid}/answer",
                             json={"datum_key": k, "value": v, "unit": u, "source": src}, timeout=30)
            assert rr.status_code == 200, (k, rr.text)
            s = rr.json()
        blocked = [v for v in s["verifications"] if v["status"] == "bloquee"]
        assert blocked == [], blocked

        # approve
        r = client.post(f"{BASE_URL}/api/structuro/studies/{sid}/approve",
                        json={"role": "Ingénieur", "scope": "test"}, timeout=30)
        assert r.status_code == 200, r.text
        s = r.json()
        assert s["approvals"]
        ap = s["approvals"][-1]
        assert ap["level"] == "etude_preliminaire"
        assert ap["level"] != "execution"
    finally:
        client.delete(f"{BASE_URL}/api/structuro/studies/{sid}", timeout=30)


# --- DELETE ------------------------------------------------------------------
def test_delete_study(client):
    r = client.post(f"{BASE_URL}/api/structuro/studies/demo", timeout=60)
    sid = r.json()["study_id"]
    r = client.delete(f"{BASE_URL}/api/structuro/studies/{sid}", timeout=30)
    assert r.status_code == 200
    r = client.get(f"{BASE_URL}/api/structuro/studies/{sid}", timeout=30)
    assert r.status_code == 404
