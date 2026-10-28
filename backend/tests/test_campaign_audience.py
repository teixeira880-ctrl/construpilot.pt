"""Destinatários das campanhas: newsletter + contas com consentimento (sem BD real)."""
from __future__ import annotations

import asyncio

from engines.campaign_audience import campaign_recipients, consent_fields, merge_recipients


def test_merge_dedups_and_prefers_newsletter_token():
    subs = [{"email": "Ana@Mail.pt", "token": "nl-ana"}, {"email": "rui@mail.pt", "token": "nl-rui"}]
    users = [{"email": "ana@mail.pt", "marketing_unsub_token": "acc-ana"},
             {"email": "joao@mail.pt", "marketing_unsub_token": "acc-joao"}]
    out = {r["email"]: r for r in merge_recipients(subs, users)}
    assert set(out) == {"ana@mail.pt", "rui@mail.pt", "joao@mail.pt"}
    assert out["ana@mail.pt"]["token"] == "nl-ana" and out["ana@mail.pt"]["source"] == "newsletter"
    assert out["joao@mail.pt"] == {"email": "joao@mail.pt", "token": "acc-joao", "source": "account"}


def test_merge_ignores_empty_emails():
    assert merge_recipients([{"email": "", "token": "x"}], [{"email": None}]) == []


def test_consent_fields():
    f = consent_fields(True, "signup")
    assert f["marketing_consent"] is True and f["marketing_consent_source"] == "signup"
    assert consent_fields(False, "x" * 100)["marketing_consent_source"] == "x" * 40


class _Cursor:
    def __init__(self, docs):
        self.docs = docs

    async def to_list(self, _limit):
        return [dict(d) for d in self.docs]


class _Coll:
    def __init__(self, docs):
        self.docs = docs
        self.updates = []

    def find(self, query, _proj=None):
        def ok(d):
            for k, v in query.items():
                if isinstance(v, dict) and "$nin" in v:
                    if d.get(k) in v["$nin"]:
                        return False
                elif d.get(k) != v:
                    return False
            return True
        return _Cursor([d for d in self.docs if ok(d)])

    async def update_one(self, flt, upd):
        self.updates.append((flt, upd))


class _Db:
    def __init__(self, subs, users):
        self.newsletter_subscribers = _Coll(subs)
        self.users = _Coll(users)


def test_campaign_recipients_only_consenting_accounts_and_active_subscribers():
    db = _Db(
        subs=[{"email": "a@x.pt", "token": "t1", "unsubscribed_at": None},
              {"email": "gone@x.pt", "token": "t2", "unsubscribed_at": "2026-10-01"}],
        users=[{"user_id": "u1", "email": "b@x.pt", "marketing_consent": True, "marketing_unsub_token": "k1"},
               {"user_id": "u2", "email": "c@x.pt", "marketing_consent": False},
               {"user_id": "u3", "email": "d@x.pt"},  # nunca decidiu → não recebe
               {"user_id": "u4", "email": "e@x.pt", "marketing_consent": True}],  # conta antiga sem token
    )
    out = {r["email"]: r for r in asyncio.run(campaign_recipients(db))}
    assert set(out) == {"a@x.pt", "b@x.pt", "e@x.pt"}
    assert out["e@x.pt"]["token"]  # token criado
    assert db.users.updates and db.users.updates[0][0] == {"user_id": "u4"}
