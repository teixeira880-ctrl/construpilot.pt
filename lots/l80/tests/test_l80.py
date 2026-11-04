"""Lote 80 PT — substituições SEO: nunca um título francês em construpilot.pt."""
import asyncio

import growth.routes as G


class _Cur:
    def __init__(self, rows):
        self.rows = rows

    def __aiter__(self):
        self._it = iter(self.rows)
        return self

    async def __anext__(self):
        try:
            return next(self._it)
        except StopIteration:
            raise StopAsyncIteration


class _Coll:
    def __init__(self, rows):
        self.rows = rows

    def find(self, *a, **k):
        return _Cur(self.rows)


class _DB:
    def __init__(self, rows):
        self.growth_seo_overrides = _Coll(rows)


def _run(rows, monkeypatch):
    monkeypatch.setattr(G, "db", _DB(rows))
    return asyncio.run(G.public_seo_overrides())["overrides"]


def test_portuguese_variant_preferred(monkeypatch):
    out = _run([{"path": "/", "title": "Bureau d’études BTP en ligne avec IA · ConstruPilot", "description": "Déposez vos plans"},
                {"path": "/", "title": "Orçamentos de obras com IA · ConstruPilot", "description": "Orçamente obras"}], monkeypatch)
    assert out["/"]["title"].startswith("Orçamentos")


def test_only_french_variant_not_served(monkeypatch):
    out = _run([{"path": "/", "title": "Bureau d’études BTP en ligne avec IA · ConstruPilot", "description": "Déposez vos plans"}], monkeypatch)
    assert "title" not in out.get("/", {})


def test_neutral_pt_title_kept(monkeypatch):
    out = _run([{"path": "/blog", "title": "Blog de Construção e Remodelação 2026", "description": "Guias"}], monkeypatch)
    assert out["/blog"]["title"].startswith("Blog")
