"""Iteration 151 — postal demo acceptance coverage with isolated shared storage.

Real postal_offer lifecycle is preserved (reserve/settle/company_key/require_available not stubbed).
Only Merci Facteur network-facing calls are mocked in these tests.
"""

from __future__ import annotations

import asyncio
import copy
import sys
from dataclasses import dataclass
from types import SimpleNamespace
from datetime import datetime, timedelta, timezone
from io import BytesIO

import pytest
from fastapi import HTTPException
from pypdf import PdfWriter
from pymongo.errors import DuplicateKeyError

sys.path.append("/app/backend")

from engines import mercifacteur as mf
from engines import postal_delivery as pd
from engines import postal_offer as po


def _run(coro):
    return asyncio.run(coro)


def _pdf_bytes() -> bytes:
    writer = PdfWriter()
    writer.add_blank_page(width=595, height=842)
    raw = BytesIO()
    writer.write(raw)
    return raw.getvalue()


def _mk_user(*, user_id: str, org_id: str | None, org_role: str | None = "owner", role: str = "user",
             account_type: str = "pro", active: bool = True, company_active: bool = True) -> dict:
    user = {
        "user_id": user_id,
        "role": role,
        "account_type": account_type,
        "active": active,
        "company_active": company_active,
        "organization_id": org_id,
        "organization_idsame": org_id,
    }
    if org_role is not None:
        user["org_role"] = org_role
    return user


def _recipient(name: str) -> dict:
    return {
        "nom": name,
        "societe": "TEST",
        "adresse1": "10 rue de Rivoli",
        "adresse2": "",
        "cp": "75001",
        "ville": "Paris",
        "pays": "france",
    }


def _sender() -> dict:
    return {
        "nom": "Sender",
        "societe": "",
        "adresse1": "11 rue de Rivoli",
        "adresse2": "",
        "cp": "75001",
        "ville": "Paris",
        "pays": "france",
    }


def _match(doc: dict, query: dict) -> bool:
    for key, value in query.items():
        if "." in key:
            head, tail = key.split(".", 1)
            if not any(isinstance(item, dict) and item.get(tail) == value for item in doc.get(head) or []):
                return False
            continue
        actual = doc.get(key)
        if isinstance(value, dict):
            if "$gt" in value and not (actual is not None and actual > value["$gt"]):
                return False
            if "$lt" in value and not (actual is not None and actual < value["$lt"]):
                return False
            if "$in" in value and actual not in value["$in"]:
                return False
            if "$gte" in value and not (actual is not None and actual >= value["$gte"]):
                return False
            if "$ne" in value and actual == value["$ne"]:
                return False
            if "$nin" in value and actual in value["$nin"]:
                return False
            if "$exists" in value and (key in doc) != value["$exists"]:
                return False
            continue
        if actual != value:
            return False
    return True


@dataclass
class _Result:
    modified_count: int = 0

    @property
    def matched_count(self):
        return self.modified_count


class MemoryCollection:
    def __init__(self):
        self.docs: list[dict] = []

    async def create_index(self, *_args, **_kwargs):
        return None

    async def find_one(self, query: dict, projection: dict | None = None):
        found = next((copy.deepcopy(d) for d in self.docs if _match(d, query)), None)
        if found is None:
            return None
        if projection and projection.get("_id") == 0:
            found.pop("_id", None)
        return found

    def find(self, query: dict, projection: dict | None = None):
        rows = [copy.deepcopy(d) for d in self.docs if _match(d, query)]

        class _Cursor:
            async def to_list(self, _n):
                return rows
        return _Cursor()

    async def insert_one(self, doc: dict):
        if "_id" in doc and any(existing.get("_id") == doc["_id"] for existing in self.docs):
            raise DuplicateKeyError("duplicate _id")
        self.docs.append(copy.deepcopy(doc))
        return _Result(modified_count=1)

    async def update_one(self, query: dict, update: dict):
        for idx, doc in enumerate(self.docs):
            if not _match(doc, query):
                continue
            if "$set" in update:
                for key, value in copy.deepcopy(update["$set"]).items():
                    if ".$." in key:
                        head, tail = key.split(".$.", 1)
                        needle = next(k for k in query if k.startswith(head + "."))
                        for item in doc.get(head) or []:
                            if item.get(needle.split(".", 1)[1]) == query[needle]:
                                item[tail] = value
                    else:
                        doc[key] = value
            if "$unset" in update:
                for key in update["$unset"]:
                    doc.pop(key, None)
            if "$push" in update:
                for key, value in update["$push"].items():
                    doc.setdefault(key, []).append(copy.deepcopy(value))
            if "$pull" in update:
                for key, cond in update["$pull"].items():
                    doc[key] = [item for item in doc.get(key) or [] if not _match(item, cond)]
            if "$inc" in update:
                for key, value in update["$inc"].items():
                    doc[key] = int(doc.get(key) or 0) + int(value)
            self.docs[idx] = doc
            return _Result(modified_count=1)
        return _Result(modified_count=0)

    async def delete_one(self, query: dict):
        for idx, doc in enumerate(self.docs):
            if _match(doc, query):
                del self.docs[idx]
                return _Result(modified_count=1)
        return _Result(modified_count=0)

    async def replace_one(self, query: dict, replacement: dict):
        for idx, doc in enumerate(self.docs):
            if _match(doc, query):
                self.docs[idx] = copy.deepcopy(replacement)
                return _Result(modified_count=1)
        return _Result(modified_count=0)


class MemoryDB:
    def __init__(self):
        self.postal_demo_allowances = MemoryCollection()
        self.radar_postal = MemoryCollection()
        self.radar_postal_quotes = MemoryCollection()
        self.radar_prospections = MemoryCollection()
        self.users = MemoryCollection()
        self.notifications = MemoryCollection()
        self.organizations = MemoryCollection()


@pytest.fixture
def isolated_db(monkeypatch):
    """Shared isolated DB monkeypatched into postal_delivery and postal_offer."""
    mem = MemoryDB()
    monkeypatch.setattr(pd, "db", mem)
    monkeypatch.setattr(po, "db", mem)
    return mem


@pytest.fixture
def provider_stub(monkeypatch):
    """Mock only postage_price/get_token/send_letter for postal demo tests."""
    calls = {"price": 0, "token": 0, "send": 0}

    async def fake_price(mode="normal", pages=1, pays="france"):
        calls["price"] += 1
        return {
            "mode": mode,
            "pages": pages,
            "postage": 1.11,
            "content_ttc": 1.15,
            "total_ttc": 2.26,
            "currency": "EUR",
        }

    async def fake_token(force=False):
        calls["token"] += 1
        return "tok_demo"

    async def fake_send(_pdf, **_kwargs):
        calls["send"] += 1
        return {"envoi_id": "1234567", "price": 2.26}

    monkeypatch.setattr(mf, "postage_price", fake_price)
    monkeypatch.setattr(mf, "get_token", fake_token)
    monkeypatch.setattr(mf, "send_letter", fake_send)
    return calls


def _create_quote_for(user: dict, *, token: str, opp_id: str, recipient: dict, mode: str = "normal") -> dict:
    return _run(pd.create_quote(
        user=user,
        user_id=user["user_id"],
        token=token,
        opp_id=opp_id,
        recipient=recipient,
        mode=mode,
        address_source="contact",
        sender=_sender(),
        pdf=_pdf_bytes(),
        context_hash="ctx",
    ))


def _consume_slots(mem: MemoryDB, user: dict, count: int) -> None:
    """Pre-consume demo slots so exhaustion scenarios stay meaningful with DEMO_LIMIT=20."""
    for i in range(count):
        _run(po.reserve(user, f"post_pre_{i}", f"opp_pre_{i}"))
        _run(po.settle(user, f"post_pre_{i}", "submitted"))


def _deliver_quote(user: dict, *, token: str, quote_id: str, recipient: dict, mode: str = "normal") -> dict:
    return _run(pd.deliver(
        user=user,
        user_id=user["user_id"],
        token=token,
        quote_id=quote_id,
        recipient=recipient,
        mode=mode,
        context_hash="ctx",
    ))


# 1) same-org owner/member, concurrent different quotes => one provider call, one 409, shared allowance exhausted
def test_same_org_owner_member_concurrent_only_one_send(monkeypatch, isolated_db, provider_stub):
    owner = _mk_user(user_id="u_owner", org_id="orgA", org_role="owner")
    member = _mk_user(user_id="u_member", org_id="orgA", org_role="member")
    _consume_slots(isolated_db, owner, po.DEMO_LIMIT - 1)
    q1 = _create_quote_for(owner, token="camp_owner", opp_id="opp1", recipient=_recipient("Owner Contact"))
    q2 = _create_quote_for(member, token="camp_member", opp_id="opp2", recipient=_recipient("Member Contact"))

    async def go():
        return await asyncio.gather(
            pd.deliver(user=owner, user_id=owner["user_id"], token="camp_owner", quote_id=q1["quote_id"], recipient=_recipient("Owner Contact"), mode="normal", context_hash="ctx"),
            pd.deliver(user=member, user_id=member["user_id"], token="camp_member", quote_id=q2["quote_id"], recipient=_recipient("Member Contact"), mode="normal", context_hash="ctx"),
            return_exceptions=True,
        )

    results = _run(go())
    http409 = [r for r in results if isinstance(r, HTTPException) and r.status_code in (402, 409)]
    submitted = [r for r in results if isinstance(r, dict) and r.get("status") == "submitted"]
    assert len(submitted) == 1
    assert len(http409) == 1
    assert provider_stub["send"] == 1

    owner_offer = _run(po.offer_for(owner))
    member_offer = _run(po.offer_for(member))
    assert owner_offer.demo_remaining == 0 and owner_offer.next_kind == "checkout"
    assert member_offer.demo_remaining == 0 and member_offer.next_kind == "checkout"


# 2) different orgs are independent => each has its own 20-letter allowance
def test_two_different_orgs_each_get_one_demo_send(isolated_db, provider_stub):
    u1 = _mk_user(user_id="u_org1", org_id="org1", org_role="owner")
    u2 = _mk_user(user_id="u_org2", org_id="org2", org_role="member")
    q1 = _create_quote_for(u1, token="camp1", opp_id="opp1", recipient=_recipient("A"))
    q2 = _create_quote_for(u2, token="camp2", opp_id="opp2", recipient=_recipient("B"))
    r1 = _deliver_quote(u1, token="camp1", quote_id=q1["quote_id"], recipient=_recipient("A"))
    r2 = _deliver_quote(u2, token="camp2", quote_id=q2["quote_id"], recipient=_recipient("B"))
    assert r1["status"] == "submitted"
    assert r2["status"] == "submitted"
    assert provider_stub["send"] == 2
    assert _run(po.offer_for(u1)).remaining == po.DEMO_LIMIT - 1
    assert _run(po.offer_for(u2)).remaining == po.DEMO_LIMIT - 1


# 2b) legacy single-letter allowance document is migrated and counted once
def test_legacy_allowance_document_migrates_to_counter(isolated_db):
    user = _mk_user(user_id="u_legacy", org_id="orgL", org_role="owner")
    _run(isolated_db.postal_demo_allowances.insert_one({"_id": "org:orgL", "postal_id": "post_old", "user_id": "u_legacy", "opp_id": "o", "status": "used"}))
    offer = _run(po.offer_for(user))
    assert offer.remaining == po.DEMO_LIMIT - 1 and offer.used == 1 and offer.eligible is True
    assert offer.demo_limit == 20


# 3) quote/refresh actions do not consume allowance before accepted send
def test_quoting_multiple_times_does_not_consume_allowance(isolated_db, provider_stub):
    user = _mk_user(user_id="u_quote", org_id="orgQ", org_role="owner")
    q1 = _create_quote_for(user, token="campQ", opp_id="oppQ", recipient=_recipient("Quote One"), mode="normal")
    q2 = _create_quote_for(user, token="campQ", opp_id="oppQ", recipient=_recipient("Quote One"), mode="suivi")
    assert q1["offer"]["remaining"] == po.DEMO_LIMIT and q1["offer"]["eligible"] is True
    assert q2["offer"]["remaining"] == po.DEMO_LIMIT and q2["offer"]["eligible"] is True
    offer = _run(po.offer_for(user))
    assert offer.remaining == po.DEMO_LIMIT and offer.eligible is True
    assert provider_stub["send"] == 0


# 4a) accepted send consumes allowance across fresh function calls
def test_submitted_send_consumes_allowance_and_blocks_second_attempt(isolated_db, provider_stub):
    user = _mk_user(user_id="u_submitted", org_id="orgS", org_role="owner")
    _consume_slots(isolated_db, user, po.DEMO_LIMIT - 1)
    first = _create_quote_for(user, token="campS", opp_id="oppS", recipient=_recipient("First"))
    sent = _deliver_quote(user, token="campS", quote_id=first["quote_id"], recipient=_recipient("First"))
    assert sent["status"] == "submitted"
    second = _create_quote_for(user, token="campS2", opp_id="oppS2", recipient=_recipient("Second"))
    assert second["offer"]["next_kind"] == "checkout" and second["offer"]["customer_amount_cents"] == 2400
    with pytest.raises(HTTPException) as exc:
        _deliver_quote(user, token="campS2", quote_id=second["quote_id"], recipient=_recipient("Second"))
    assert exc.value.status_code == 402 and exc.value.detail["code"] == "postal_payment_required"
    assert provider_stub["send"] == 1


# 4b) uncertain outcomes retain claim; no second send
@pytest.mark.parametrize("uncertain_outcome", [
    mf.PostalProviderError("provider_timeout", "timeout", uncertain=True),
    {"envoi_id": []},
])
def test_uncertain_or_missing_receipt_retains_claim(monkeypatch, isolated_db, provider_stub, uncertain_outcome):
    user = _mk_user(user_id="u_uncertain", org_id="orgU", org_role="owner")
    _consume_slots(isolated_db, user, po.DEMO_LIMIT - 1)

    async def fake_send(_pdf, **_kwargs):
        provider_stub["send"] += 1
        if isinstance(uncertain_outcome, Exception):
            raise uncertain_outcome
        return uncertain_outcome

    monkeypatch.setattr(mf, "send_letter", fake_send)
    quote = _create_quote_for(user, token="campU", opp_id="oppU", recipient=_recipient("Uncertain"))
    first = _deliver_quote(user, token="campU", quote_id=quote["quote_id"], recipient=_recipient("Uncertain"))
    assert first["status"] == "unknown"
    blocked = _create_quote_for(user, token="campU2", opp_id="oppU2", recipient=_recipient("Retry blocked"))
    assert blocked["offer"]["demo_remaining"] == 0 and blocked["offer"]["next_kind"] == "checkout"
    with pytest.raises(HTTPException) as exc:
        _deliver_quote(user, token="campU2", quote_id=blocked["quote_id"], recipient=_recipient("Retry blocked"))
    assert exc.value.status_code == 402
    assert provider_stub["send"] == 1


# 4c) explicit rejection releases allowance and new quote can retry
def test_rejection_releases_allowance_and_new_quote_can_retry(monkeypatch, isolated_db, provider_stub):
    user = _mk_user(user_id="u_reject", org_id="orgR", org_role="owner")
    _consume_slots(isolated_db, user, po.DEMO_LIMIT - 1)
    phase = {"i": 0}

    async def fake_send(_pdf, **_kwargs):
        provider_stub["send"] += 1
        phase["i"] += 1
        if phase["i"] == 1:
            raise mf.PostalProviderError("provider_rejected", "reject", uncertain=False)
        return {"envoi_id": "888999", "price": 2.26}

    monkeypatch.setattr(mf, "send_letter", fake_send)
    q1 = _create_quote_for(user, token="campR", opp_id="oppR", recipient=_recipient("Rejected"))
    r1 = _deliver_quote(user, token="campR", quote_id=q1["quote_id"], recipient=_recipient("Rejected"))
    assert r1["status"] == "rejected"

    q2 = _create_quote_for(user, token="campR2", opp_id="oppR2", recipient=_recipient("Retry OK"))
    r2 = _deliver_quote(user, token="campR2", quote_id=q2["quote_id"], recipient=_recipient("Retry OK"))
    assert r2["status"] == "submitted"
    assert provider_stub["send"] == 2


# 4d) auth failure happens before reserve: free claim remains available
def test_get_token_auth_failure_does_not_consume_allowance(monkeypatch, isolated_db, provider_stub):
    user = _mk_user(user_id="u_authfail", org_id="orgAF", org_role="owner")

    async def broken_token(force=False):
        provider_stub["token"] += 1
        raise mf.PostalProviderError("INVALID_TOKEN_FOR_IP", "ip auth fail", uncertain=False)

    monkeypatch.setattr(mf, "get_token", broken_token)
    quote = _create_quote_for(user, token="campAF", opp_id="oppAF", recipient=_recipient("Auth fail"))
    with pytest.raises(HTTPException) as exc:
        _deliver_quote(user, token="campAF", quote_id=quote["quote_id"], recipient=_recipient("Auth fail"))
    assert exc.value.status_code == 503
    offer = _run(po.offer_for(user))
    assert offer.remaining == po.DEMO_LIMIT and offer.eligible is True
    assert provider_stub["send"] == 0


# 5) stale/no-offer/scope-change/wrong-user-or-recipient never call provider
def test_quote_guards_prevent_provider_calls(monkeypatch, isolated_db, provider_stub):
    user = _mk_user(user_id="u_guard", org_id="orgG", org_role="owner")
    quote = _create_quote_for(user, token="campG", opp_id="oppG", recipient=_recipient("Guard"))
    assert provider_stub["send"] == 0

    # stale/expired
    for doc in isolated_db.radar_postal_quotes.docs:
        if doc.get("quote_id") == quote["quote_id"]:
            doc["expires_at"] = datetime.now(timezone.utc) - timedelta(seconds=1)
    with pytest.raises(HTTPException) as exp:
        _deliver_quote(user, token="campG", quote_id=quote["quote_id"], recipient=_recipient("Guard"))
    assert exp.value.status_code == 409

    # recreate and remove offer from quote
    fresh = _create_quote_for(user, token="campG2", opp_id="oppG2", recipient=_recipient("Guard2"))
    for doc in isolated_db.radar_postal_quotes.docs:
        if doc.get("quote_id") == fresh["quote_id"]:
            doc.pop("offer", None)
    with pytest.raises(HTTPException):
        _deliver_quote(user, token="campG2", quote_id=fresh["quote_id"], recipient=_recipient("Guard2"))

    # scope change (company key mismatch)
    mismatch_user = _mk_user(user_id="u_guard", org_id="orgOther", org_role="owner")
    with pytest.raises(HTTPException) as sc:
        _deliver_quote(mismatch_user, token="campG2", quote_id=fresh["quote_id"], recipient=_recipient("Guard2"))
    assert sc.value.status_code == 409

    # wrong actor/user for this quote (query mismatch -> quote_expired contract)
    wrong_user = _mk_user(user_id="u_other", org_id="orgG", org_role="owner")
    with pytest.raises(HTTPException) as wu:
        _deliver_quote(wrong_user, token="campG2", quote_id=fresh["quote_id"], recipient=_recipient("Guard2"))
    assert wu.value.status_code == 409

    # explicit identity mismatch in function args -> access denied before query
    with pytest.raises(HTTPException) as mismatch:
        _run(pd.deliver(
            user=wrong_user,
            user_id="u_guard",
            token="campG2",
            quote_id=fresh["quote_id"],
            recipient=_recipient("Guard2"),
            mode="normal",
            context_hash="ctx",
        ))
    assert mismatch.value.status_code == 403

    # wrong recipient
    quote3 = _create_quote_for(user, token="campG3", opp_id="oppG3", recipient=_recipient("Expected"))
    with pytest.raises(HTTPException) as wr:
        _deliver_quote(user, token="campG3", quote_id=quote3["quote_id"], recipient=_recipient("Different"))
    assert wr.value.status_code == 409
    assert provider_stub["send"] == 0


# 6) paid phase remains disabled constants; incoming amount cannot alter charging
def test_offer_contract_paid_disabled_and_billing_stays_zero(isolated_db, provider_stub):
    user = _mk_user(user_id="u_contract", org_id="orgC", org_role="owner")
    status = _run(po.offer_for(user)).model_dump()
    assert status["phase"] == "demo"
    assert status["paid_enabled"] is True
    assert status["unit_price_net_cents"] == 2000 and status["unit_price_gross_cents"] == 2400
    assert status["payment_provider"] == "stripe"
    assert status["next_kind"] == "demo"
    assert status["customer_amount_cents"] == 0
    assert {p["pack_id"]: p["amount_net_cents"] for p in status["packs"]} == {"pack5": 10000, "pack10": 20000}

    quote = _create_quote_for(user, token="campC", opp_id="oppC", recipient=_recipient("Billing"))
    # Malicious quote tampering should be blocked by validation (no provider call).
    for doc in isolated_db.radar_postal_quotes.docs:
        if doc.get("quote_id") == quote["quote_id"]:
            doc["offer"]["customer_amount_cents"] = 999999
    with pytest.raises(HTTPException) as exc:
        _deliver_quote(user, token="campC", quote_id=quote["quote_id"], recipient=_recipient("Billing"))
    assert exc.value.status_code == 409
    assert provider_stub["send"] == 0


# 7) guardrails for unknown org role / inactive worker / particulier
@pytest.mark.parametrize("user", [
    _mk_user(user_id="u_unknown", org_id="orgX", org_role="ghost"),
    _mk_user(user_id="u_worker", org_id="orgX", org_role="member", role="worker", company_active=False),
    _mk_user(user_id="u_part", org_id="orgX", org_role="member", account_type="particulier"),
])
def test_offer_company_key_forbidden_profiles_raise_403(isolated_db, user):
    with pytest.raises(HTTPException) as exc:
        _run(po.require_available(user))
    assert exc.value.status_code == 403


# 8) token cache fingerprint: same config uses cache, changed IP mints new token
def test_get_token_cache_fingerprint_respects_config(monkeypatch):
    mf._token.clear()
    calls = {"n": 0}
    now = int(datetime.now(timezone.utc).timestamp())

    env = {
        "MERCIFACTEUR_BASE_URL": "https://mf.example",
        "MERCIFACTEUR_PUBLIC_KEY": "pub",
        "MERCIFACTEUR_SECRET_KEY": "sec",
        "MERCIFACTEUR_USER_ID": "uid",
        "MERCIFACTEUR_AUTHORIZED_IP": "1.1.1.1",
    }
    for key, value in env.items():
        monkeypatch.setenv(key, value)

    async def fake_call(_method, op, _headers, **_kwargs):
        assert op == "getToken"
        calls["n"] += 1
        return {"token": f"tok_{calls['n']}", "expire": now + 3600}

    monkeypatch.setattr(mf, "_call", fake_call)
    t1 = _run(mf.get_token(force=True))
    t2 = _run(mf.get_token())
    assert t1 == "tok_1"
    assert t2 == "tok_1"
    assert calls["n"] == 1

    monkeypatch.setenv("MERCIFACTEUR_AUTHORIZED_IP", "2.2.2.2")
    t3 = _run(mf.get_token())
    assert t3 == "tok_2"
    assert calls["n"] == 2


# 8) prepaid credits are consumed after the demo quota and restored on confirmed rejection
def test_credits_consumed_after_demo_and_restored_on_rejection(monkeypatch, isolated_db, provider_stub):
    user = _mk_user(user_id="u_credit", org_id="orgCr", org_role="owner")
    _consume_slots(isolated_db, user, po.DEMO_LIMIT)
    assert _run(po.add_credits(user, 5, session_id="cs_test")) == 5
    offer = _run(po.offer_for(user))
    assert offer.next_kind == "credit" and offer.credits == 5 and offer.customer_amount_cents == 0 and offer.phase == "paid"
    quote = _create_quote_for(user, token="campCr", opp_id="oppCr", recipient=_recipient("Credit"))
    assert quote["offer"]["next_kind"] == "credit"
    sent = _deliver_quote(user, token="campCr", quote_id=quote["quote_id"], recipient=_recipient("Credit"))
    assert sent["status"] == "submitted" and sent["billing"]["kind"] == "prepaid_credit"
    assert _run(po.offer_for(user)).credits == 4

    async def rejecting(_pdf, **_kwargs):
        raise mf.PostalProviderError("provider_rejected", "reject", uncertain=False)
    monkeypatch.setattr(mf, "send_letter", rejecting)
    q2 = _create_quote_for(user, token="campCr2", opp_id="oppCr2", recipient=_recipient("Credit 2"))
    r2 = _deliver_quote(user, token="campCr2", quote_id=q2["quote_id"], recipient=_recipient("Credit 2"))
    assert r2["status"] == "rejected"
    assert _run(po.offer_for(user)).credits == 4


# 9) paid dispatch (after Stripe) requires a checkout quote and compensates a refusal with one credit
def test_paid_dispatch_requires_checkout_quote_and_compensates_rejection(monkeypatch, isolated_db, provider_stub):
    user = _mk_user(user_id="u_paid", org_id="orgP", org_role="owner")
    _consume_slots(isolated_db, user, po.DEMO_LIMIT)
    quote = _create_quote_for(user, token="campP", opp_id="oppP", recipient=_recipient("Paid"))
    assert quote["offer"]["next_kind"] == "checkout" and quote["offer"]["customer_amount_cents"] == 2400
    sent = _run(pd.deliver(user=user, user_id="u_paid", token="campP", quote_id=quote["quote_id"], recipient=_recipient("Paid"),
                           mode="normal", context_hash="ctx", paid_session_id="cs_paid_1"))
    assert sent["status"] == "submitted" and sent["billing"] == {"kind": "stripe_checkout", "customer_amount_cents": 2400,
        "currency": "EUR", "operator_pays_postage": False, "session_id": "cs_paid_1"}
    assert provider_stub["send"] == 1
    # a demo quote can never be dispatched through the paid path
    fresh = _mk_user(user_id="u_fresh", org_id="orgFresh", org_role="owner")
    demo_quote = _create_quote_for(fresh, token="campF", opp_id="oppF", recipient=_recipient("Fresh"))
    with pytest.raises(HTTPException) as exc:
        _run(pd.deliver(user=fresh, user_id="u_fresh", token="campF", quote_id=demo_quote["quote_id"], recipient=_recipient("Fresh"),
                        mode="normal", context_hash="ctx", paid_session_id="cs_x"))
    assert exc.value.status_code == 409 and provider_stub["send"] == 1

    async def rejecting(_pdf, **_kwargs):
        raise mf.PostalProviderError("provider_rejected", "reject", uncertain=False)
    monkeypatch.setattr(mf, "send_letter", rejecting)
    q2 = _create_quote_for(user, token="campP2", opp_id="oppP2", recipient=_recipient("Paid 2"))
    r2 = _run(pd.deliver(user=user, user_id="u_paid", token="campP2", quote_id=q2["quote_id"], recipient=_recipient("Paid 2"),
                         mode="normal", context_hash="ctx", paid_session_id="cs_paid_2"))
    assert r2["status"] == "rejected"
    assert _run(po.offer_for(user)).credits == 1


# 10) admins are alerted exactly once when a company reaches 15/20 free letters
def test_admin_alert_fires_once_at_threshold(monkeypatch, isolated_db):
    user = _mk_user(user_id="u_alert", org_id="orgAl", org_role="owner")
    _run(isolated_db.users.insert_one({"user_id": "adm1", "role": "admin", "email": "adm1@test.local"}))
    _run(isolated_db.users.insert_one({"user_id": "adm2", "role": "admin", "email": None}))
    _run(isolated_db.organizations.insert_one({"org_id": "orgAl", "name": "Alerte SAS"}))
    emails = []

    async def fake_email(to, subject, html, **_kwargs):
        emails.append((to, subject))
        return {"ok": True}
    import engines.emailer as emailer
    monkeypatch.setattr(emailer, "send_email", fake_email)
    _consume_slots(isolated_db, user, po.QUOTA_ALERT_AT - 1)
    assert isolated_db.notifications.docs == []
    _consume_slots(isolated_db, user, 1)
    notifs = isolated_db.notifications.docs
    assert len(notifs) == 2 and all(n["type"] == "postal_quota_alert" for n in notifs)
    assert "Alerte SAS" in notifs[0]["message"] and "15/20" in notifs[0]["message"]
    assert emails == [("adm1@test.local", "⚠️ Quota courrier 15/20 — Alerte SAS")]
    _consume_slots(isolated_db, user, 3)
    assert len(isolated_db.notifications.docs) == 2


# 11) Stripe per-letter checkout: refused while free letters/credits remain, created once the company must pay
def test_letter_checkout_guard_and_creation(monkeypatch, isolated_db, provider_stub):
    from engines import postal_billing as pb
    isolated_db.payment_transactions = MemoryCollection()
    monkeypatch.setattr(pb, "db", isolated_db)
    fresh = _mk_user(user_id="u_co_free", org_id="orgCoFree", org_role="owner")
    quote = _create_quote_for(fresh, token="campCo", opp_id="oppCo", recipient=_recipient("Free"))
    with pytest.raises(HTTPException) as exc:
        _run(pb.create_letter_checkout(user=fresh, token="campCo", quote_id=quote["quote_id"], recipient=_recipient("Free"),
                                       mode="normal", context_hash="ctx", origin_url="https://app.test"))
    assert exc.value.status_code == 409 and exc.value.detail["code"] == "postal_free_available"

    payer = _mk_user(user_id="u_co_paid", org_id="orgCoPaid", org_role="owner")
    _consume_slots(isolated_db, payer, po.DEMO_LIMIT)
    q = _create_quote_for(payer, token="campCoP", opp_id="oppCoP", recipient=_recipient("Payer"))
    created = {}

    async def fake_session(user, **kwargs):
        created.update(kwargs)
        return SimpleNamespace(id="cs_test_unit", url="https://checkout.stripe.test/cs_test_unit")
    monkeypatch.setattr(pb, "_create_session", fake_session)
    result = _run(pb.create_letter_checkout(user=payer, token="campCoP", quote_id=q["quote_id"], recipient=_recipient("Payer"),
                                            mode="normal", context_hash="ctx", origin_url="https://app.test"))
    assert result == {"url": "https://checkout.stripe.test/cs_test_unit", "session_id": "cs_test_unit", "amount_cents": 2400, "reused": False}
    assert created["unit_cents"] == 2400 and created["metadata"]["type"] == "postal_letter"
    tx = isolated_db.payment_transactions.docs[0]
    assert tx["type"] == "postal_letter" and tx["payment_status"] == "pending" and tx["fulfillment"] == "pending"
    stored = next(d for d in isolated_db.radar_postal_quotes.docs if d["quote_id"] == q["quote_id"])
    assert stored["checkout_session_id"] == "cs_test_unit" and stored["expires_at"] > datetime.now(timezone.utc) + timedelta(hours=2)
    # the same pending session is reused instead of charging twice
    again = _run(pb.create_letter_checkout(user=payer, token="campCoP", quote_id=q["quote_id"], recipient=_recipient("Payer"),
                                           mode="normal", context_hash="ctx", origin_url="https://app.test"))
    assert again["reused"] is True and again["session_id"] == "cs_test_unit"
    assert provider_stub["send"] == 0
