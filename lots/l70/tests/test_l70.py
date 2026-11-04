"""Lot 70 — TVA par défaut « à confirmer » sur les lignes générées sans taux."""
import asyncio

import routes.plans_common as pc
from routes import documents as d


def _run(lines, country, monkeypatch):
    async def fake(_uid):
        return {"country": country}
    monkeypatch.setattr(pc, "_resolve_branding", fake)
    asyncio.run(d.normalize_generated_vat({"user_id": "u_test"}, lines))
    return lines


def _expected(country):
    from core.fiscal import policy_for
    return policy_for(country)["default_rate"]


def test_stair_like_lines_get_default_vat(monkeypatch):
    lines = [{"kind": "line", "designation": "Béton C25/30 pour escalier", "vat_rate": None, "price_source": ""},
             {"kind": "section", "title": "Escalier", "vat_rate": None}]
    for c in ("FR", "PT"):
        out = _run([dict(x) for x in lines], c, monkeypatch)
        assert out[0]["vat_rate"] == _expected(c) and out[0]["vat_rate"] is not None
        assert out[0]["vat_assumed"] is True
        assert out[1].get("vat_rate") is None  # section non chiffrable


def test_user_rate_never_changed(monkeypatch):
    lines = [{"kind": "line", "vat_rate": 10, "price_source": "manual"},
             {"kind": "line", "vat_rate": None, "vat_confirmed": True, "price_source": ""},
             {"kind": "line", "vat_rate": 5.5, "price_source": ""}]
    out = _run(lines, "FR", monkeypatch)
    assert out[0]["vat_rate"] == 10 and not out[0].get("vat_assumed")
    assert out[1]["vat_rate"] is None
    assert out[2]["vat_rate"] == 5.5 and not out[2].get("vat_assumed")


def test_generator_source_still_normalised(monkeypatch):
    out = _run([{"kind": "line", "vat_rate": 7, "price_source": "plan_chiffrage"}], "FR", monkeypatch)
    assert out[0]["vat_rate"] == _expected("FR") and out[0]["vat_assumed"] is True
