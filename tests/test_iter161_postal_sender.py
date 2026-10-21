"""No provider calls or persistent writes; sender/organization regression coverage."""
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from engines.postal_sender import require_sender_branding
from fastapi import HTTPException
from routes import phase7, plans_common, radar


@pytest.mark.parametrize("branding", [None, {}, {"address": " ", "city": "Paris", "postal_code": "75001"}])
def test_missing_sender_is_actionable_400(branding):
    with pytest.raises(HTTPException) as exc:
        require_sender_branding(branding, organization=True)
    assert exc.value.status_code == 400
    assert exc.value.detail["code"] == "sender_address_required"
    assert "address" in exc.value.detail["fields"]
    assert exc.value.detail["source"] == "organization"
    assert exc.value.detail["action_url"] == "/entreprise"


def test_complete_sender_still_works_without_fabricated_address():
    branding = {"address": "12 rue de la Paix", "city": "Paris", "postal_code": "75002"}
    assert radar._sender_from_branding(branding, "Entreprise test")["adresse1"] == branding["address"]
    with pytest.raises(HTTPException):
        radar._sender_from_branding(None, "Entreprise test")


def test_postal_context_missing_branding_does_not_raise_attribute_error(monkeypatch):
    monkeypatch.setattr(radar, "db", SimpleNamespace(radar_prospections=SimpleNamespace(find_one=AsyncMock(return_value={"opp_id": "test"}))))
    monkeypatch.setattr(radar, "_get_permits", AsyncMock(return_value=[{"id": "test", "is_demo": False}]))
    monkeypatch.setattr(radar, "_profile", AsyncMock(return_value={"base": {}, "metiers": []}))
    monkeypatch.setattr(radar, "_build", lambda *args: {})
    monkeypatch.setattr(radar, "_frontend_url", lambda: "https://example.invalid")
    monkeypatch.setattr(radar, "_pro_branding_and_user", AsyncMock(return_value=(None, {})))
    from engines import mercifacteur
    monkeypatch.setattr(mercifacteur, "configured", lambda: True)
    with pytest.raises(HTTPException) as exc:
        asyncio.run(radar._postal_context("test", {"user_id": "test"}))
    assert exc.value.status_code == 400
    assert exc.value.detail["code"] == "sender_address_required"


def projected_store(doc):
    async def find_one(_query, projection):
        assert projection.get("_id") == 0
        return {key: value for key, value in doc.items() if projection.get(key)}
    return SimpleNamespace(find_one=find_one)


def test_organization_branding_read_includes_address_and_resolver_uses_it(monkeypatch):
    db = SimpleNamespace(
        users=projected_store({"organization_id": "org_test", "org_role": "owner"}),
        organizations=projected_store({"org_id": "org_test", "name": "Test", "brand_address": "12 rue Test", "brand_city": "Paris", "brand_postal": "75002"}),
    )
    monkeypatch.setattr(phase7, "db", db)
    monkeypatch.setattr(plans_common, "db", db)
    public = asyncio.run(phase7.get_branding({"user_id": "test"}))
    resolved = asyncio.run(plans_common._resolve_branding("test"))
    for field in ("address", "postal_code", "city"):
        assert public[field] == resolved[field]
        assert public[field]
    assert public["can_edit"] is True


def test_personal_address_only_is_resolved(monkeypatch):
    monkeypatch.setattr(plans_common, "db", SimpleNamespace(users=projected_store({"brand_address": "12 rue Test", "brand_city": "Paris", "brand_postal": "75002"})))
    assert asyncio.run(plans_common._resolve_branding("test"))["address"] == "12 rue Test"