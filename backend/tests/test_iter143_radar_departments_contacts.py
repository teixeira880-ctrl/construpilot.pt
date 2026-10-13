"""Iteration 143 - Radar departments/contact workflows and registry validations."""
import io
import os
import sys
from pathlib import Path

import pytest
import requests
from dotenv import load_dotenv
from pydantic import ValidationError
from pymongo import MongoClient

sys.path.append(str(Path(__file__).resolve().parents[1]))

from engines.company_registry import normalize_company
from routes.radar import PostalSendIn

try:
    from tests.creds import (
        ADMIN_EMAIL,
        ADMIN_PWD,
        CLIENT_EMAIL,
        CLIENT_PWD,
        COLLEGUE_EMAIL,
        COLLEGUE_PWD,
        PRO_EMAIL,
        PRO_PWD,
    )
except ImportError:
    from creds import (  # type: ignore
        ADMIN_EMAIL,
        ADMIN_PWD,
        CLIENT_EMAIL,
        CLIENT_PWD,
        COLLEGUE_EMAIL,
        COLLEGUE_PWD,
        PRO_EMAIL,
        PRO_PWD,
    )


load_dotenv(Path(__file__).resolve().parents[1] / ".env")
load_dotenv(Path(__file__).resolve().parents[2] / "frontend" / ".env")
BASE_URL = os.environ.get("REACT_APP_BACKEND_URL")
MONGO_URL = os.environ.get("MONGO_URL")
DB_NAME = os.environ.get("DB_NAME")

if not BASE_URL:
    pytest.skip("REACT_APP_BACKEND_URL missing", allow_module_level=True)

API = f"{BASE_URL.rstrip('/')}/api"


def _login(email, password):
    r = requests.post(f"{API}/auth/login", json={"email": email, "password": password}, timeout=20)
    assert r.status_code == 200, f"login failed for {email}: {r.status_code} {r.text[:250]}"
    token = r.json().get("token")
    assert isinstance(token, str) and len(token) > 10
    return token, r


def _h(token):
    return {"Authorization": f"Bearer {token}"}


def _deep_has_object_id(obj):
    if isinstance(obj, dict):
        if "_id" in obj:
            return True
        return any(_deep_has_object_id(v) for v in obj.values())
    if isinstance(obj, list):
        return any(_deep_has_object_id(v) for v in obj)
    return False


def _mongo_db():
    assert MONGO_URL and DB_NAME, "MONGO_URL/DB_NAME required"
    return MongoClient(MONGO_URL)[DB_NAME]


# Feature: deterministic fixtures for zone/contact scenarios and teardown
@pytest.fixture(scope="module")
def radar_fixture_data():
    db = _mongo_db()
    now = "2026-09-13T00:00:00+00:00"
    permits = [
        {
            "id": "TEST_ITER143_DEP13_ENTREPRISE",
            "num": "PC TEST 143 13 001",
            "type": "Permis de construire",
            "nature": "neuf",
            "commune": "Marseille",
            "cp": "13001",
            "dep": "13",
            "adresse": "10 La Canebière",
            "lat": 43.2965,
            "lon": 5.3698,
            "batiment": "Bureaux logistique TEST_ITER143",
            "surf_created": 800,
            "logements": 0,
            "date_depot": "2026-05-01",
            "date_auth": "2026-06-01",
            "statut": "Autorisé",
            "mo": "ENTREPRISE",
            "promoteur": {
                "nom": "TEST Import Entreprise 13",
                "adresse1": "10 La Canebière",
                "cp": "13001",
                "ville": "Marseille",
                "siren": "123456789",
            },
            "coordonnees_status": "complet",
            "imported_at": now,
            "is_demo": False,
        },
        {
            "id": "TEST_ITER143_DEP75_PARTICULIER",
            "num": "PC TEST 143 75 001",
            "type": "Permis de construire",
            "nature": "neuf",
            "commune": "Paris",
            "cp": "75012",
            "dep": "75",
            "adresse": "12 avenue Daumesnil",
            "lat": 48.845,
            "lon": 2.382,
            "batiment": "Maison individuelle TEST_ITER143",
            "surf_created": 120,
            "logements": 1,
            "date_depot": "2026-05-03",
            "date_auth": "2026-06-03",
            "statut": "Autorisé",
            "mo": "PARTICULIER",
            "promoteur": None,
            "coordonnees_status": "absent",
            "imported_at": now,
            "is_demo": False,
        },
        {
            "id": "TEST_ITER143_DEP95_BUSINESS_PARTIAL",
            "num": "PC TEST 143 95 001",
            "type": "Permis de construire",
            "nature": "renovation",
            "commune": "Cergy",
            "cp": "95000",
            "dep": "95",
            "adresse": "1 rue de la Gare",
            "lat": 49.036,
            "lon": 2.078,
            "batiment": "Rénovation partielle TEST_ITER143",
            "surf_created": 210,
            "logements": 0,
            "date_depot": "2026-05-10",
            "date_auth": "2026-06-10",
            "statut": "Autorisé",
            "mo": "ENTREPRISE",
            "promoteur": {"nom": "TEST Partiel"},
            "coordonnees_status": "partiel",
            "imported_at": now,
            "is_demo": False,
        },
        {
            "id": "TEST_ITER143_DEMO_BUSINESS",
            "num": "PC TEST 143 DEMO 001",
            "type": "Permis de construire",
            "nature": "neuf",
            "commune": "Lyon",
            "cp": "69001",
            "dep": "69",
            "adresse": "1 place des Terreaux",
            "lat": 45.767,
            "lon": 4.834,
            "batiment": "Demo case TEST_ITER143",
            "surf_created": 500,
            "logements": 3,
            "date_depot": "2026-05-12",
            "date_auth": "2026-06-12",
            "statut": "Autorisé",
            "mo": "ENTREPRISE",
            "promoteur": None,
            "coordonnees_status": "absent",
            "imported_at": now,
            "is_demo": True,
        },
    ]
    for p in permits:
        db.radar_permits.update_one({"id": p["id"]}, {"$set": p}, upsert=True)

    pro_token, _ = _login(PRO_EMAIL, PRO_PWD)
    col_token, _ = _login(COLLEGUE_EMAIL, COLLEGUE_PWD)
    pro_profile = requests.get(f"{API}/radar/profile", headers=_h(pro_token), timeout=20).json()
    col_profile = requests.get(f"{API}/radar/profile", headers=_h(col_token), timeout=20).json()

    yield {
        "pro_profile": pro_profile,
        "col_profile": col_profile,
        "fixture_ids": [p["id"] for p in permits],
    }

    # Cleanup only iter143 fixtures + private overlays/campaign artifacts
    db.radar_contacts.delete_many({"opp_id": {"$regex": r"^TEST_ITER143_"}})
    db.radar_contact_searches.delete_many({"opp_id": {"$regex": r"^TEST_ITER143_"}})
    db.radar_prospections.delete_many({"opp_id": {"$regex": r"^TEST_ITER143_"}})
    db.radar_postal.delete_many({"opp_id": {"$regex": r"^TEST_ITER143_"}})
    db.radar_permits.delete_many({"id": {"$regex": r"^TEST_ITER143_"}})

    # Restore modified profiles
    requests.put(
        f"{API}/radar/profile",
        headers=_h(pro_token),
        json={
            "km": pro_profile.get("km"),
            "zone_mode": pro_profile.get("zone_mode"),
            "departments": pro_profile.get("departments"),
            "metiers": pro_profile.get("metiers"),
            "base": pro_profile.get("base"),
        },
        timeout=20,
    )
    requests.put(
        f"{API}/radar/profile",
        headers=_h(col_token),
        json={
            "km": col_profile.get("km"),
            "zone_mode": col_profile.get("zone_mode"),
            "departments": col_profile.get("departments"),
            "metiers": col_profile.get("metiers"),
            "base": col_profile.get("base"),
        },
        timeout=20,
    )


# Feature: auth baseline expectations (cookie/cors/lockout/hash)
def test_auth_cookie_cors_lockout_and_hash_policy():
    _, login_resp = _login(PRO_EMAIL, PRO_PWD)
    set_cookie = login_resp.headers.get("set-cookie", "").lower()
    assert "httponly" in set_cookie

    pre = requests.options(
        f"{API}/auth/login",
        headers={
            "Origin": BASE_URL,
            "Access-Control-Request-Method": "POST",
        },
        timeout=20,
    )
    assert pre.headers.get("access-control-allow-credentials") == "true"
    assert pre.headers.get("access-control-allow-origin") == BASE_URL

    codes = []
    for _ in range(6):
        r = requests.post(
            f"{API}/auth/login",
            json={"email": "iter143_lock@example.com", "password": "wrong"},
            timeout=20,
        )
        codes.append(r.status_code)
    assert 429 in codes

    user = _mongo_db().users.find_one({"email": PRO_EMAIL}, {"_id": 0, "password_hash": 1})
    assert user and str(user.get("password_hash", "")).startswith("$2b$")


# Feature: profile options + normalization + invalid rejection
def test_departments_count_normalization_and_invalid_rejection(radar_fixture_data):
    token, _ = _login(PRO_EMAIL, PRO_PWD)
    h = _h(token)
    p = requests.get(f"{API}/radar/profile", headers=h, timeout=20)
    assert p.status_code == 200
    opts = p.json().get("department_options", [])
    codes = {o["code"] for o in opts}
    assert len(opts) == 101
    for required in ("75", "77", "78", "91", "92", "93", "94", "95", "2A", "2B", "971", "972", "973", "974", "976"):
        assert required in codes

    put_ok = requests.put(
        f"{API}/radar/profile",
        headers=h,
        json={"zone_mode": "departments", "departments": ["75", "075", "95", "2a", "2B", "971", "971"]},
        timeout=20,
    )
    assert put_ok.status_code == 200
    assert put_ok.json().get("departments") == ["75", "95", "2A", "2B", "971"]

    put_bad = requests.put(
        f"{API}/radar/profile",
        headers=h,
        json={"departments": ["999"]},
        timeout=20,
    )
    assert put_bad.status_code == 422


# Feature: profile isolation between pro and colleague
def test_profile_persistence_is_per_user(radar_fixture_data):
    pro_t, _ = _login(PRO_EMAIL, PRO_PWD)
    col_t, _ = _login(COLLEGUE_EMAIL, COLLEGUE_PWD)

    r = requests.put(
        f"{API}/radar/profile",
        headers=_h(pro_t),
        json={"zone_mode": "departments", "departments": ["13"], "km": 10},
        timeout=20,
    )
    assert r.status_code == 200

    pro_profile = requests.get(f"{API}/radar/profile", headers=_h(pro_t), timeout=20).json()
    col_profile = requests.get(f"{API}/radar/profile", headers=_h(col_t), timeout=20).json()
    assert pro_profile["zone_mode"] == "departments"
    assert pro_profile["departments"] == ["13"]
    assert col_profile["departments"] != ["13"] or col_profile["zone_mode"] != "departments"


# Feature: opportunities/stats coherence + departments mode ignores km
def test_zone_filter_behavior_and_stats_consistency(radar_fixture_data):
    token, _ = _login(PRO_EMAIL, PRO_PWD)
    h = _h(token)

    q = "km=10&zone_mode=departments&departments=13"
    opp = requests.get(f"{API}/radar/opportunities?{q}", headers=h, timeout=20)
    st = requests.get(f"{API}/radar/stats?{q}", headers=h, timeout=20)
    assert opp.status_code == 200 and st.status_code == 200
    ids = [o["id"] for o in opp.json().get("opportunities", [])]
    assert "TEST_ITER143_DEP13_ENTREPRISE" in ids
    assert st.json().get("detected") == opp.json().get("count")

    radius = requests.get(
        f"{API}/radar/opportunities?km=10&zone_mode=radius&departments=13",
        headers=h,
        timeout=20,
    )
    assert radius.status_code == 200
    radius_ids = [o["id"] for o in radius.json().get("opportunities", [])]
    assert "TEST_ITER143_DEP13_ENTREPRISE" not in radius_ids


# Feature: no false matches for department filtering
def test_department_filter_returns_only_selected_department(radar_fixture_data):
    token, _ = _login(PRO_EMAIL, PRO_PWD)
    r = requests.get(
        f"{API}/radar/opportunities?zone_mode=departments&departments=75",
        headers=_h(token),
        timeout=20,
    )
    assert r.status_code == 200
    opps = r.json().get("opportunities", [])
    assert opps
    assert all(str(o.get("dep")) == "75" for o in opps)


# Feature: imported source labeling + no ObjectId leakage
def test_imported_source_unverified_and_no_objectid_leak(radar_fixture_data):
    token, _ = _login(PRO_EMAIL, PRO_PWD)
    detail = requests.get(f"{API}/radar/opportunities/PC07831126X0042", headers=_h(token), timeout=20)
    if detail.status_code == 404:
        pytest.skip("Known imported permit PC07831126X0042 not present in this preview")
    assert detail.status_code == 200
    data = detail.json()
    assert data.get("source", {}).get("type") == "import"
    assert "source à vérifier" in (data.get("source", {}).get("name", "").lower())
    assert not _deep_has_object_id(data)


# Feature: demo records clearly blocked for edits/search/generation
def test_demo_records_block_manual_search_and_generation(radar_fixture_data):
    token, _ = _login(PRO_EMAIL, PRO_PWD)
    h = _h(token)
    body = {
        "contact": {"nom": "TEST"},
        "source_note": "TEST source",
        "source_url": "https://example.com",
        "confirmed": True,
    }
    r1 = requests.put(f"{API}/radar/opportunities/TEST_ITER143_DEMO_BUSINESS/contact", headers=h, json=body, timeout=20)
    r2 = requests.post(f"{API}/radar/opportunities/TEST_ITER143_DEMO_BUSINESS/contact/search", headers=h, json={"query": "VINCI"}, timeout=20)
    r3 = requests.post(f"{API}/radar/opportunities/TEST_ITER143_DEMO_BUSINESS/prospection", headers=h, json={"message": "x"}, timeout=20)
    assert r1.status_code == 409
    assert r2.status_code == 409
    assert r3.status_code == 409


# Feature: manual contact validation + persist/reload/delete reset
def test_manual_contact_validation_persistence_and_delete(radar_fixture_data):
    token, _ = _login(PRO_EMAIL, PRO_PWD)
    h = _h(token)
    opp_id = "TEST_ITER143_DEP95_BUSINESS_PARTIAL"

    bad = requests.put(
        f"{API}/radar/opportunities/{opp_id}/contact",
        headers=h,
        json={"contact": {"nom": "X"}, "source_note": "ok", "confirmed": False},
        timeout=20,
    )
    assert bad.status_code == 422

    partial = {
        "contact": {"nom": "TEST Contact", "adresse1": "3 rue des Tests", "cp": "95000", "ville": "Cergy"},
        "source_note": "source manuelle validée",
        "source_url": "https://example.org/provenance",
        "confirmed": True,
    }
    saved = requests.put(f"{API}/radar/opportunities/{opp_id}/contact", headers=h, json=partial, timeout=20)
    assert saved.status_code == 200
    d = saved.json()
    assert d["promoteur"]["nom"] == "TEST Contact"
    assert d["contact_provenance"]["kind"] == "manual"
    assert d["contact_provenance"].get("confirmed_at")

    reloaded = requests.get(f"{API}/radar/opportunities/{opp_id}", headers=h, timeout=20)
    assert reloaded.status_code == 200
    assert reloaded.json()["promoteur"]["nom"] == "TEST Contact"

    deleted = requests.delete(f"{API}/radar/opportunities/{opp_id}/contact", headers=h, timeout=20)
    assert deleted.status_code == 200
    # Should reset to imported partial data, not manual overlay
    assert deleted.json()["promoteur"].get("nom") == "TEST Partiel"
    assert deleted.json().get("contact_provenance") is None


# Feature: private overlays are isolated by user; particulier account cannot write
def test_contact_overlay_isolation_and_particulier_forbidden(radar_fixture_data):
    pro_t, _ = _login(PRO_EMAIL, PRO_PWD)
    col_t, _ = _login(COLLEGUE_EMAIL, COLLEGUE_PWD)
    cli_t, _ = _login(CLIENT_EMAIL, CLIENT_PWD)
    opp_id = "TEST_ITER143_DEP13_ENTREPRISE"

    saved = requests.put(
        f"{API}/radar/opportunities/{opp_id}/contact",
        headers=_h(pro_t),
        json={
            "contact": {"nom": "TEST Privé Pro", "adresse1": "1 rue A", "cp": "13001", "ville": "Marseille"},
            "source_note": "source pro",
            "source_url": "https://example.com/pro",
            "confirmed": True,
        },
        timeout=20,
    )
    assert saved.status_code == 200
    assert saved.json()["promoteur"]["nom"] == "TEST Privé Pro"

    colleague_view = requests.get(f"{API}/radar/opportunities/{opp_id}", headers=_h(col_t), timeout=20)
    assert colleague_view.status_code == 200
    assert colleague_view.json().get("promoteur", {}).get("nom") != "TEST Privé Pro"

    cli_write = requests.put(
        f"{API}/radar/opportunities/{opp_id}/contact",
        headers=_h(cli_t),
        json={
            "contact": {"nom": "NOPE"},
            "source_note": "xxyyzz",
            "source_url": "https://example.com",
            "confirmed": True,
        },
        timeout=20,
    )
    assert cli_write.status_code == 403


# Feature: company registry search/confirm and anti-forgery checks
def test_registry_search_confirm_and_forbidden_cases(radar_fixture_data):
    pro_t, _ = _login(PRO_EMAIL, PRO_PWD)
    col_t, _ = _login(COLLEGUE_EMAIL, COLLEGUE_PWD)
    h = _h(pro_t)
    opp_id = "TEST_ITER143_DEP13_ENTREPRISE"

    baseline = requests.get(f"{API}/radar/opportunities/{opp_id}", headers=h, timeout=20).json()
    baseline_name = (baseline.get("promoteur") or {}).get("nom")

    search = requests.post(
        f"{API}/radar/opportunities/{opp_id}/contact/search",
        headers=h,
        json={"query": "VINCI"},
        timeout=40,
    )
    assert search.status_code == 200, search.text[:250]
    payload = search.json()
    assert payload.get("search_id")
    assert isinstance(payload.get("candidates"), list)
    if payload["candidates"]:
        first = payload["candidates"][0]
        assert "annuaire-entreprises.data.gouv.fr" in first.get("source_url", "")
        # Search must not auto-save anything
        after_search = requests.get(f"{API}/radar/opportunities/{opp_id}", headers=h, timeout=20).json()
        assert (after_search.get("promoteur") or {}).get("nom") == baseline_name

        bad_siren = requests.post(
            f"{API}/radar/opportunities/{opp_id}/contact/confirm",
            headers=h,
            json={"search_id": payload["search_id"], "siren": "000000000", "confirmed": True},
            timeout=20,
        )
        assert bad_siren.status_code == 404

        other_user = requests.post(
            f"{API}/radar/opportunities/{opp_id}/contact/confirm",
            headers=_h(col_t),
            json={"search_id": payload["search_id"], "siren": first["siren"], "confirmed": True},
            timeout=20,
        )
        assert other_user.status_code in (403, 404)

        confirmed = requests.post(
            f"{API}/radar/opportunities/{opp_id}/contact/confirm",
            headers=h,
            json={"search_id": payload["search_id"], "siren": first["siren"], "confirmed": True},
            timeout=20,
        )
        assert confirmed.status_code == 200
        assert confirmed.json().get("contact_provenance", {}).get("kind") == "registry"

    particulier_forbidden = requests.post(
        f"{API}/radar/opportunities/TEST_ITER143_DEP75_PARTICULIER/contact/search",
        headers=h,
        json={"query": "VINCI"},
        timeout=20,
    )
    assert particulier_forbidden.status_code == 403


# Feature: SITADEL cj mapping and dep extraction from overseas postal code
def test_admin_import_cj_mapping_and_dep_from_cp(radar_fixture_data):
    admin_t, _ = _login(ADMIN_EMAIL, ADMIN_PWD)
    h = _h(admin_t)
    csv_data = (
        "id;commune;cp;lat;lon;num;type;nature;batiment;cj_dem;siren_dem\n"
        "TEST_ITER143_CJ5710;Paris;75015;48.84;2.29;PC-CJ-1;Permis de construire;neuf;Bat A;5710;111222333\n"
        "TEST_ITER143_CJ1000;Paris;75016;48.85;2.26;PC-CJ-2;Permis de construire;neuf;Bat B;1000;444555666\n"
        "TEST_ITER143_CJ6540;Cayenne;97300;4.93;-52.33;PC-CJ-3;Permis de construire;neuf;Bat C;6540;777888999\n"
    )
    files = {"file": ("iter143_cj.csv", io.BytesIO(csv_data.encode()), "text/csv")}
    imp = requests.post(f"{API}/radar/admin/import-sitadel?replace=false", headers=h, files=files, timeout=40)
    assert imp.status_code == 200, imp.text[:250]

    pro_t, _ = _login(PRO_EMAIL, PRO_PWD)
    p = _h(pro_t)
    d1 = requests.get(f"{API}/radar/opportunities/TEST_ITER143_CJ5710", headers=p, timeout=20).json()
    d2 = requests.get(f"{API}/radar/opportunities/TEST_ITER143_CJ1000", headers=p, timeout=20).json()
    d3 = requests.get(f"{API}/radar/opportunities/TEST_ITER143_CJ6540", headers=p, timeout=20).json()
    assert d1["mo"] == "ENTREPRISE"
    assert d2["mo"] == "PARTICULIER"
    assert d3["mo"] == "SCI"
    assert d1.get("promoteur", {}).get("siren") == "111222333"
    assert d3.get("dep") == "973"

    _mongo_db().radar_permits.delete_many({"id": {"$regex": r"^TEST_ITER143_CJ"}})


# Feature: registry normalization rules (public legal entities only)
def test_company_registry_normalization_filters_ei_non_diffusion_inactive():
    active = {
        "nature_juridique": "5710",
        "siren": "123456789",
        "nom_raison_sociale": "VINCI TEST",
        "statut_diffusion": "O",
        "etat_administratif": "A",
        "siege": {
            "est_siege": True,
            "siret": "12345678900010",
            "adresse": "1 rue Test 75000 Paris",
            "statut_diffusion_etablissement": "O",
            "etat_administratif": "A",
            "numero_voie": "1",
            "type_voie": "rue",
            "libelle_voie": "Test",
            "code_postal": "75000",
            "libelle_commune": "Paris",
        },
        "complements": {"est_entrepreneur_individuel": False},
    }
    ei = {**active, "complements": {"est_entrepreneur_individuel": True}}
    hidden = {**active, "statut_diffusion": "N"}
    inactive = {**active, "etat_administratif": "F"}

    assert normalize_company(active) is not None
    assert normalize_company(ei) is None
    assert normalize_company(hidden) is None
    assert normalize_company(inactive) is None


# Feature: isolated postal validation, no physical send
def test_postal_validation_rejects_whitespace_required_fields():
    with pytest.raises(ValidationError):
        PostalSendIn.model_validate(
            {
                "recipient": {
                    "nom": "   ",
                    "adresse1": "   ",
                    "cp": "   ",
                    "ville": "   ",
                    "societe": "",
                    "adresse2": "",
                    "pays": "france",
                },
                "mode": "normal",
                "address_source": "contact",
            }
        )
