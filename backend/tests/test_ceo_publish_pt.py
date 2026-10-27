"""Fix publicação artigos PT: ao publicar um rascunho do agente CEO que ficou com
`language_code` != "pt" (vindo da migração .fr), o artigo deve ficar visível em
GET /api/blog/autoseo?lang=pt."""
from __future__ import annotations

import pytest

from core.db import db
from routes import ceo as ceo_routes
from routes import autoseo as autoseo_routes


@pytest.mark.asyncio(loop_scope="session")
async def test_publish_blog_normalises_language_to_pt_and_appears_in_pt_listing():
    aid = "ceo_pt_fix_fr_draft"
    try:
        await db.autoseo_articles.delete_one({"autoseo_id": aid})
        await db.autoseo_articles.insert_one({
            "autoseo_id": aid, "source": "ceo_agent", "status": "draft",
            "title": "Rascunho FR herdado", "slug": "rascunho-fr-herdado-pt-fix",
            "content_html": "<p>corpo</p>",
            "language_code": "fr", "audience": "particuliers",
        })

        before = await autoseo_routes.list_autoseo_articles(lang="pt")
        assert all(a["autoseo_id"] != aid for a in before["articles"])

        res = await ceo_routes.publish_blog(aid)
        assert res == {"published": True, "article_id": aid}

        doc = await db.autoseo_articles.find_one({"autoseo_id": aid}, {"_id": 0})
        assert doc["status"] == "published"
        assert doc["language_code"] == "pt"
        assert doc["published_at"]

        after = await autoseo_routes.list_autoseo_articles(lang="pt")
        assert any(a["autoseo_id"] == aid for a in after["articles"])
    finally:
        await db.autoseo_articles.delete_one({"autoseo_id": aid})


@pytest.mark.asyncio(loop_scope="session")
async def test_publish_blog_404_when_missing():
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as exc:
        await ceo_routes.publish_blog("ceo_does_not_exist_xyz")
    assert exc.value.status_code == 404
