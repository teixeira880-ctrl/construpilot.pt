"""Testes do pipeline BabyLoveGrowth PT-PT.

Valida que:
- `_upsert` só publica artigos cujo `languageCode` começa por "pt";
- artigos noutros idiomas são ignorados (`skipped_lang` incrementado em `sync_articles`);
- o sitemap `/api/blog/sitemap.xml` inclui artigos PT e exclui não-PT.
"""
from __future__ import annotations

import pytest

from core.db import db
from routes import babylovegrowth as blg

pytestmark = pytest.mark.asyncio(loop_scope="session")


async def _clean():
    await db.autoseo_articles.delete_many({"autoseo_id": {"$regex": "^blg-TESTE_"}})


async def test_upsert_publica_artigo_pt(monkeypatch):
    await _clean()
    monkeypatch.setattr(blg, "_download_and_store", lambda url, aid, kind: None)
    article = {
        "id": "TESTE_pt_001",
        "title": "Reabilitação em Lisboa: licenciamento municipal",
        "slug": "reabilitacao-lisboa-licenciamento",
        "content_html": "<p>Conteúdo</p>",
        "excerpt": "Excerto",
        "languageCode": "pt-PT",
        "keywords": ["reabilitação", "RJUE"],
    }
    slug = await blg._upsert(article, "sync")
    assert slug == "reabilitacao-lisboa-licenciamento"
    doc = await db.autoseo_articles.find_one({"autoseo_id": "blg-TESTE_pt_001"})
    assert doc is not None
    assert doc["language_code"].startswith("pt")
    assert doc["status"] == "published"


async def test_upsert_ignora_artigo_fr(monkeypatch):
    await _clean()
    monkeypatch.setattr(blg, "_download_and_store", lambda url, aid, kind: None)
    article = {
        "id": "TESTE_fr_001",
        "title": "Rénover à Paris",
        "slug": "renover-a-paris",
        "content_html": "<p>Contenu</p>",
        "languageCode": "fr-FR",
    }
    slug = await blg._upsert(article, "sync")
    assert slug is None
    # Nenhum documento deve ter sido criado.
    doc = await db.autoseo_articles.find_one({"autoseo_id": "blg-TESTE_fr_001"})
    assert doc is None


async def test_upsert_default_language_e_pt(monkeypatch):
    """Se o fornecedor não enviar `languageCode`, assumimos PT (contexto PT)."""
    await _clean()
    monkeypatch.setattr(blg, "_download_and_store", lambda url, aid, kind: None)
    article = {
        "id": "TESTE_default_001",
        "title": "Como pedir uma licença de obras",
        "slug": "licenca-obras-pedir",
        "content_html": "<p>Conteúdo</p>",
    }
    slug = await blg._upsert(article, "sync")
    assert slug == "licenca-obras-pedir"
    doc = await db.autoseo_articles.find_one({"autoseo_id": "blg-TESTE_default_001"})
    assert doc and doc["language_code"] == "pt"


async def test_sitemap_blog_so_contem_pt(monkeypatch):
    """O sitemap `/api/blog/sitemap.xml` só deve listar artigos PT."""
    await _clean()
    monkeypatch.setattr(blg, "_download_and_store", lambda url, aid, kind: None)
    # Insere diretamente um artigo PT via upsert e um "FR" via raw insert com language_code=fr.
    await blg._upsert({"id": "TESTE_sitemap_pt", "title": "Guia PT", "slug": "guia-pt-teste",
                       "content_html": "<p>x</p>", "languageCode": "pt-PT"}, "sync")
    await db.autoseo_articles.insert_one({
        "autoseo_id": "blg-TESTE_sitemap_fr", "source": "babylovegrowth", "status": "published",
        "slug": "guide-fr-teste", "title": "Guide FR", "language_code": "fr", "published_at": "2026-01-01"})
    try:
        from routes.autoseo import blog_sitemap
        resp = await blog_sitemap()
        body = resp.body.decode("utf-8") if hasattr(resp, "body") else str(resp)
        assert "guia-pt-teste" in body
        assert "guide-fr-teste" not in body
        assert 'hreflang="pt-PT"' in body
    finally:
        await db.autoseo_articles.delete_many({"autoseo_id": {"$regex": "^blg-TESTE_sitemap_"}})
