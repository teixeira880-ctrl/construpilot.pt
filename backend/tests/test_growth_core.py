"""Growth module — unit tests on the critical, non-paid logic (brand detection, transparent metrics, SSRF guard, publish inbox auth)."""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from growth.brands import detect  # noqa: E402
from growth.campaigns import _rate  # noqa: E402
from growth.crawler import _safe_host, _same_site, _norm  # noqa: E402

BRANDS = [
    {"brand_id": "self", "name": "ConstruPilot", "variants": ["ConstruPilot", "Constru Pilot"], "domains": ["construpilot.fr", "construpilot.pt"], "is_self": True},
    {"brand_id": "obat", "name": "Obat", "variants": ["Obat"], "domains": ["obat.fr"], "is_self": False},
]


def test_detection_counts_once_and_separates_kinds():
    text = "1. Obat\n2. ConstruPilot\nJe vous recommande ConstruPilot. ConstruPilot ConstruPilot ConstruPilot."
    out = detect(text, [{"url": "https://www.construpilot.fr/metre"}], BRANDS, "fr")
    self_ = next(m for m in out if m["is_self"])
    assert len([m for m in out if m["is_self"]]) == 1
    assert self_["mention"] and self_["domain_citation"] and self_["recommendation"] and self_["rank"] == 2
    assert "ConstruPilot" in self_["evidence"]
    obat = next(m for m in out if m["name"] == "Obat")
    assert obat["rank"] == 1 and not obat["domain_citation"] and obat["rank"] is not None


def test_generic_words_are_not_brand_mentions():
    out = detect("Le pilotage de la construction demande un bon logiciel de construction.", [], BRANDS, "fr")
    assert out == []


def test_rate_with_zero_denominator_is_unavailable_not_zero():
    r = _rate(0, 0)
    assert r["value"] is None and r["display"] == "données indisponibles"
    assert _rate(1, 4)["display"] == "25.0 %"


def test_ssrf_guard_blocks_private_hosts():
    assert not _safe_host("localhost")
    assert not _safe_host("127.0.0.1")
    assert not _safe_host("10.0.0.1")
    assert not _safe_host("169.254.169.254")


def test_same_site_and_normalisation():
    assert _same_site("https://www.construpilot.fr/x", "construpilot.fr")
    assert not _same_site("https://construpilot.fr.evil.com/", "construpilot.fr")
    assert _norm("https://construpilot.fr/metre/#top") == "https://construpilot.fr/metre"


def test_publish_inbox_requires_token(monkeypatch):
    import asyncio
    from fastapi import HTTPException
    from growth.routes import publish_inbox
    monkeypatch.setenv("GROWTH_PUBLISH_TOKEN", "secret-token")
    with pytest.raises(HTTPException) as e:
        asyncio.run(publish_inbox({"autoseo_id": "growth_a", "slug": "a", "content_html": "<p>a</p>"}, authorization="Bearer wrong"))
    assert e.value.status_code == 401
    with pytest.raises(HTTPException) as e2:
        asyncio.run(publish_inbox({"autoseo_id": "evil", "slug": "a", "content_html": "<p>a</p>"}, authorization="Bearer secret-token"))
    assert e2.value.status_code == 422
