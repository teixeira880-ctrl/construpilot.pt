"""Agente CEO — produção diária (sem chamadas reais ao LLM nem ao gerador de imagens)."""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone

import pytest

from engines import ceo_blog, ceo_daily


def test_split_counts():
    assert ceo_daily.split_counts(10) == {"pros": 5, "particuliers": 5}
    assert ceo_daily.split_counts(11) == {"pros": 5, "particuliers": 6}


def test_duplicate_detection():
    ex = [ceo_daily._norm("Quanto custa remodelar uma casa de banho em Portugal")]
    assert ceo_daily.is_duplicate("Quanto custa remodelar a casa de banho em Portugal?", ex)
    assert not ceo_daily.is_duplicate("Piscina em casa: licenciamento e custos", ex)


def test_seed_topics_unique_and_balanced():
    titles = [t for t, _ in ceo_daily.TOPICS_PROS + ceo_daily.TOPICS_PART]
    assert len(ceo_daily.TOPICS_PROS) >= 60 and len(ceo_daily.TOPICS_PART) >= 60
    seen: list[str] = []
    for t in titles:
        assert not ceo_daily.is_duplicate(t, seen), t
        seen.append(ceo_daily._norm(t))


def test_quality_flags_french_and_short():
    issues = ceo_blog.quality_issues({"content_html": "<h2>a</h2><p>devis RE2020</p>", "title": "x"})
    assert any("franceses" in i for i in issues)
    assert any("curto" in i for i in issues)


def test_schedule_times_spread_in_window():
    times = ceo_daily._schedule_times(10, datetime(2026, 10, 14, 5, 0, tzinfo=timezone.utc), [8, 20])
    hours = [datetime.fromisoformat(t).astimezone(ceo_daily.LISBON).hour for t in times]
    assert len(times) == 10 and min(hours) >= 8 and max(hours) < 20
    assert len(set(times)) == 10


@pytest.mark.asyncio
async def test_run_daily_creates_drafts_without_publishing(monkeypatch):
    from core.db import db
    created: list[dict] = []

    async def fake_generate(topic, keywords, audience, with_image=True, created_by=None, origin="manual",
                            extra_fields=None):
        aid = f"ceo_test_{len(created)}"
        doc = {"autoseo_id": aid, "source": "ceo_agent", "status": "draft", "origin": origin,
               "title": topic, "topic": topic, "audience": audience, "slug": ceo_blog.slugify(topic) + "-t",
               "cost_eur": 0.07, **(extra_fields or {})}
        await db.autoseo_articles.insert_one(dict(doc))
        created.append(doc)
        return doc

    async def no_ideation(*a, **k):
        return 0

    monkeypatch.setattr(ceo_blog, "generate_article", fake_generate)
    monkeypatch.setattr(ceo_daily, "_ideate", no_ideation)
    await db.app_settings.delete_many({"key": ceo_daily.SETTINGS_KEY})
    try:
        res = await ceo_daily.run_daily(force=True, count=10)
        assert res["created"] == 10 and res["errors"] == 0 and res["scheduled"] == 0
        auds = [d["audience"] for d in created]
        assert auds.count("pros") == 5 and auds.count("particuliers") == 5
        assert len({d["title"] for d in created}) == 10
        assert await db.autoseo_articles.count_documents(
            {"autoseo_id": {"$regex": "^ceo_test_"}, "status": "published"}) == 0
        assert await ceo_daily.publish_due() == 0  # publicação automática desligada
    finally:
        await db.autoseo_articles.delete_many({"autoseo_id": {"$regex": "^ceo_test_"}})
        await db.ceo_topics.update_many({"article_id": {"$regex": "^ceo_test_"}},
                                        {"$set": {"status": "new"}, "$unset": {"article_id": "", "used_at": ""}})
        await db.ceo_daily_runs.delete_many({"_id": {"$regex": "-manual-"}})
