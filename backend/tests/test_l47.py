"""Lot 47 — contrôles statiques (FR et PT) + empresa demo PT avec une base factice."""
import asyncio
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
APP = ROOT.parent / "frontend"
sys.path.insert(0, str(ROOT))


def test_rooms_count_in_list():
    assert 'd["rooms_count"] = len(d.get("rooms") or [])' in (ROOT / "routes" / "plans_crud.py").read_text()


def test_business_level_and_billing_wait():
    assert 'base = "business" if at == "pro_business"' in (ROOT / "routes" / "billing.py").read_text()
    app = (APP / "src" / "App.js").read_text()
    assert app.count("billingReady === false") == 3
    assert "ready: !user || state.uid === user.user_id" in (APP / "src" / "context" / "BillingContext.jsx").read_text()


def test_popup_skips_demo():
    assert "/^\\/demo(\\/|$)/" in (APP / "public" / "construpilot-websummit-popup.js").read_text()


class _Coll:
    def __init__(self, docs=None):
        self.docs = docs or []

    def _m(self, flt):
        return next((d for d in self.docs if all(d.get(k) == v for k, v in flt.items())), None)

    async def find_one(self, flt, proj=None):
        d = self._m(flt)
        return dict(d) if d else None

    async def insert_one(self, doc):
        self.docs.append(dict(doc))

    async def update_one(self, flt, upd):
        d = self._m(flt)
        if d:
            d.update(upd["$set"])


class _DB:
    def __init__(self):
        self.users = _Coll([{"email": "demo@x.pt", "user_id": "u1", "is_demo": True,
                             "demo_source": "websummit_2026", "brand_company_name": "Construções Horizonte, Lda.",
                             "brand_postal_code": "4700-000"}])
        self.organizations = _Coll()


def test_demo_org_pt_idempotent():
    p = ROOT / "core" / "websummit_seed_pt.py"
    if not p.exists():
        return  # site .fr
    from core import websummit_seed_pt as W
    db = _DB()
    assert asyncio.run(W._ensure_demo_org_pt(db, "demo@x.pt")) == "created"
    assert asyncio.run(W._ensure_demo_org_pt(db, "demo@x.pt")) == "unchanged"
    assert len(db.organizations.docs) == 1
    org = db.organizations.docs[0]
    assert org["brand_company_name"].startswith("Construções Horizonte") and org["brand_postal"] == "4700-000"
    u = db.users.docs[0]
    assert u["organization_id"] == org["org_id"] and u["org_role"] == "owner"
    assert W._config()["pro"]["account_type"] == "pro_business"
