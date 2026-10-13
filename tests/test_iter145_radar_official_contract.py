"""Radar official data contract tests (live API + isolated normalization/client unit checks)."""

from __future__ import annotations

import os
import asyncio
from datetime import date, timedelta
from pathlib import Path

import pytest
import requests

from backend.engines.sitadel_client import SitadelClient, SitadelSourceError
from backend.engines.sitadel_permits import official_permit


def _base_url() -> str:
    env_url = os.environ.get("REACT_APP_BACKEND_URL")
    if env_url:
        return env_url.rstrip("/")
    env_path = Path("/app/frontend/.env")
    for line in env_path.read_text(encoding="utf-8").splitlines():
        if line.startswith("REACT_APP_BACKEND_URL="):
            return line.split("=", 1)[1].strip().rstrip("/")
    pytest.skip("Missing REACT_APP_BACKEND_URL")


BASE_URL = _base_url()


@pytest.fixture(scope="session")
def api_client() -> requests.Session:
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


@pytest.fixture(scope="session")
def pro_token(api_client: requests.Session) -> str:
    resp = api_client.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": "pro@construpilot.fr", "password": "Pro2026!"},
        timeout=30,
    )
    assert resp.status_code == 200, resp.text
    token = resp.json().get("token")
    assert isinstance(token, str) and token
    return token


@pytest.fixture(scope="session")
def auth_headers(pro_token: str) -> dict:
    return {"Authorization": f"Bearer {pro_token}"}


def test_opportunities_default_official_snapshot_contract(auth_headers: dict):
    """Official list envelope + default initial departments counts."""
    resp = requests.get(
        f"{BASE_URL}/api/radar/opportunities?page=1&page_size=50",
        headers=auth_headers,
        timeout=60,
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["data_mode"] == "official"
    assert data["count"] == 3184
    assert data["page"] == 1
    assert data["page_size"] == 50
    assert len(data["opportunities"]) == 50
    deps = {d["department"]: (d["status"], d.get("count", 0)) for d in data["sync"]["departments"]}
    assert deps == {
        "75": ("ready", 243),
        "77": ("ready", 1341),
        "92": ("ready", 379),
        "93": ("ready", 564),
        "95": ("ready", 657),
    }
    assert data["sync"]["window_start"] == "2025-09-13"
    assert data["sync"]["window_end"] == "2026-09-13"


def test_fake_records_are_absent(auth_headers: dict):
    """Known fake ids should never be visible in official opportunities."""
    resp = requests.get(
        f"{BASE_URL}/api/radar/opportunities?departments=75,77,92,93,95&page=1&page_size=100",
        headers=auth_headers,
        timeout=60,
    )
    assert resp.status_code == 200, resp.text
    ids = {o["id"] for o in resp.json()["opportunities"]}
    assert "PC07831126X0042" not in ids
    assert all(not i.startswith("CP-2026-") for i in ids)


def test_real_permit_detail_matches_expected_key_fields(auth_headers: dict):
    """Known real permit should expose stable official fields and source metadata."""
    permit_id = "SITADEL-PC-0955002500014"
    detail = requests.get(
        f"{BASE_URL}/api/radar/opportunities/{permit_id}", headers=auth_headers, timeout=60
    )
    assert detail.status_code == 200, detail.text
    d = detail.json()
    assert d["num"] == "0955002500014"
    assert d["dep"] == "95"
    assert d["date_auth"] == "2026-01-22"
    assert d["statut"] in ("Autorisé", "Commencé")
    assert "RUE DES ECURIES" in (d.get("adresse") or "")
    assert d["source"]["millesime"] == "2026-08"
    assert d["source"]["published_at"].startswith("2026-08-28")
    assert d["source"]["coverage_end"] == "2026-07-31"
    assert "/rows?" in d["source"]["record_url"]


def test_source_record_url_contains_same_permit_identity(auth_headers: dict):
    """record_url must resolve and return row matching API permit number/dept/state/date."""
    permit_id = "SITADEL-PC-0955002500014"
    detail = requests.get(
        f"{BASE_URL}/api/radar/opportunities/{permit_id}", headers=auth_headers, timeout=60
    )
    assert detail.status_code == 200, detail.text
    d = detail.json()
    source_rows = requests.get(d["source"]["record_url"], timeout=60)
    assert source_rows.status_code == 200, source_rows.text
    payload = source_rows.json()
    assert isinstance(payload.get("data"), list)
    assert payload.get("total", 0) >= 1
    row = next((r for r in payload["data"] if str(r.get("NUM_DAU")) == d["num"]), None)
    assert row is not None
    assert str(row.get("DEP_CODE")) == d["dep"]
    assert str(row.get("DATE_REELLE_AUTORISATION"))[:10] == d["date_auth"]
    status_map = {2: "Autorisé", 5: "Commencé"}
    assert status_map.get(row.get("ETAT_DAU")) == d["statut"]
    source_addr = " ".join(
        [
            str(row.get("ADR_NUM_TER") or "").strip(),
            str(row.get("ADR_LIBVOIE_TER") or "").strip(),
        ]
    ).strip()
    assert source_addr == d["adresse"]


def test_rows_pagination_contract_page_size_100(auth_headers: dict):
    """/rows contract should keep total stable across pages and use envelope total/page/data."""
    permit_id = "SITADEL-PC-0955002500014"
    detail = requests.get(
        f"{BASE_URL}/api/radar/opportunities/{permit_id}", headers=auth_headers, timeout=60
    )
    assert detail.status_code == 200
    source = detail.json()["source"]
    source_base = source["record_url"].split("/rows?")[0]
    rid = source["rid"]
    millesime = source["millesime"]
    dep = "95"
    start = "2025-09-13"
    params = {
        "millesime": millesime,
        "DEP_CODE": f"eq:{dep}",
        "DATE_REELLE_AUTORISATION": f"gte:{start}",
        "ETAT_DAU": "in:2,5",
        "TYPE_DAU": "eq:PC",
        "pageSize": 100,
    }
    p1 = requests.get(f"{source_base}/rows", params={**params, "page": 1}, timeout=60)
    p2 = requests.get(f"{source_base}/rows", params={**params, "page": 2}, timeout=60)
    assert p1.status_code == 200 and p2.status_code == 200
    j1, j2 = p1.json(), p2.json()
    for j in (j1, j2):
        assert isinstance(j.get("data"), list)
        assert isinstance(j.get("total"), int)
        assert isinstance(j.get("page"), int)
    assert j1["total"] == j2["total"]
    assert j1["page"] == 1 and j2["page"] == 2
    assert len(j1["data"]) <= 100 and len(j2["data"]) <= 100
    assert f"/datafiles/{rid}/rows" in p1.url


def test_private_fallback_candidate_exists_and_prospection_pdf_only(auth_headers: dict):
    """Need at least one permit with null promoteur + terrain address; prospection should return PDF payload."""
    resp = requests.get(
        f"{BASE_URL}/api/radar/opportunities?page=1&page_size=100&departments=75,77,92,93,95",
        headers=auth_headers,
        timeout=60,
    )
    assert resp.status_code == 200
    opps = resp.json()["opportunities"]
    candidate = next(
        (
            o
            for o in opps
            if not o.get("promoteur")
            and bool((o.get("adresse") or "").strip())
            and bool((o.get("cp") or "").strip())
            and bool((o.get("commune") or "").strip())
        ),
        None,
    )
    assert candidate is not None
    create = requests.post(
        f"{BASE_URL}/api/radar/opportunities/{candidate['id']}/prospection",
        headers=auth_headers,
        json={"message": ""},
        timeout=60,
    )
    assert create.status_code == 200, create.text
    payload = create.json()
    assert payload.get("token", "").startswith("rop_")
    assert payload.get("public_url", "").startswith("http")
    assert payload.get("letter_b64", "").startswith("data:application/pdf;base64,")


def test_sitadel_client_pages_raises_if_total_changes(monkeypatch):
    """Isolated client contract: changing total across pages should raise SitadelSourceError."""
    monkeypatch.setenv("SITADEL_API_URL", "https://example.test")
    async def _runner():
        client = SitadelClient()
        calls = {"n": 0}

        async def fake_get(url, params=None):
            calls["n"] += 1
            if calls["n"] == 1:
                return {"total": 2, "page": 1, "data": [{"x": 1}]}
            return {"total": 3, "page": 2, "data": [{"x": 2}]}

        monkeypatch.setattr(client, "get", fake_get)
        try:
            with pytest.raises(SitadelSourceError):
                async for _rows, _page, _total in client.pages("rid", {"millesime": "2026-08"}, "95", "2025-09-13"):
                    pass
        finally:
            await client.close()

    asyncio.run(_runner())


def test_normalization_invalid_and_future_dates_skipped():
    """No invented date fallback: invalid/future auth date must be skipped."""
    meta = {"millesime": "2026-08", "published": "2026-08-28T00:00:00Z", "dataset": "x", "temporal_coverage": {"end": "2026-07-31"}}
    row_invalid = {
        "DATE_REELLE_AUTORISATION": "bad-date",
        "DEP_CODE": "95",
        "TYPE_DAU": "PC",
        "ETAT_DAU": 2,
        "NUM_DAU": "0955002500014",
    }
    assert official_permit(row_invalid, meta, "rid", "logements", "95", {}) is None

    future = (date.today() + timedelta(days=5)).isoformat()
    row_future = {
        "DATE_REELLE_AUTORISATION": future,
        "DEP_CODE": "95",
        "TYPE_DAU": "PC",
        "ETAT_DAU": 2,
        "NUM_DAU": "0955002500015",
    }
    assert official_permit(row_future, meta, "rid", "logements", "95", {}) is None


def test_normalization_excludes_wrong_status_and_non_pc():
    """Only PC and statuses 2/5 are accepted."""
    meta = {"millesime": "2026-08", "published": "2026-08-28T00:00:00Z", "dataset": "x", "temporal_coverage": {"end": "2026-07-31"}}
    common = {
        "DATE_REELLE_AUTORISATION": "2026-01-01",
        "DEP_CODE": "95",
        "NUM_DAU": "0955002500016",
    }
    row_status4 = {**common, "TYPE_DAU": "PC", "ETAT_DAU": 4}
    row_status6 = {**common, "TYPE_DAU": "PC", "ETAT_DAU": 6}
    row_dp = {**common, "TYPE_DAU": "DP", "ETAT_DAU": 2}
    assert official_permit(row_status4, meta, "rid", "logements", "95", {}) is None
    assert official_permit(row_status6, meta, "rid", "logements", "95", {}) is None
    assert official_permit(row_dp, meta, "rid", "logements", "95", {}) is None


def test_normalization_street_empty_when_only_house_number(monkeypatch):
    monkeypatch.setenv("SITADEL_API_URL", "https://example.test")
    monkeypatch.setenv("SITADEL_PORTAL_URL", "https://example.test/portal")
    monkeypatch.setenv("SITADEL_COMMUNES_URL", "https://example.test/communes")
    """Null street with house number should produce empty adresse, not fabricated street."""
    meta = {"millesime": "2026-08", "published": "2026-08-28T00:00:00Z", "dataset": "x", "temporal_coverage": {"end": "2026-07-31"}}
    row = {
        "DATE_REELLE_AUTORISATION": "2026-01-01",
        "DEP_CODE": "95",
        "TYPE_DAU": "PC",
        "ETAT_DAU": 2,
        "NUM_DAU": "0955002500017",
        "ADR_NUM_TER": "12",
        "ADR_LIBVOIE_TER": None,
        "ADR_CODPOST_TER": "95000",
        "ADR_LOCALITE_TER": "PONTOISE",
        "COMM": "95500",
    }
    permit = official_permit(row, meta, "rid", "logements", "95", {})
    assert permit is not None
    assert permit["adresse"] == ""
