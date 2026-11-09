"""iter157 — isolated safeguards for assistant quote draft idempotency, pricing, schema and tool exposure."""

import asyncio
import copy
import re
import sys
import types
from pathlib import Path

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from engines import assistant_quote_pricing as pricing
from engines import assistant_quote_schema as schema
from engines import assistant_quote_service as service
from routes import assistant as assistant_route
from routes.documents import DocLine, _compute_totals
from routes.library import auto_save_from_lines


# ---------------- fake db primitives (module/component isolated tests only) ----------------
def _match(doc: dict, query: dict) -> bool:
    for key, expected in query.items():
        actual = doc.get(key)
        if isinstance(expected, dict):
            if "$ne" in expected and actual == expected["$ne"]:
                return False
            if "$in" in expected and actual not in expected["$in"]:
                return False
            if "$regex" in expected:
                flags = re.I if "i" in str(expected.get("$options", "")).lower() else 0
                if not re.search(expected["$regex"], str(actual or ""), flags):
                    return False
        elif actual != expected:
            return False
    return True


class _Cursor:
    def __init__(self, rows):
        self.rows = copy.deepcopy(rows)

    def sort(self, *_args, **_kwargs):
        return self

    def limit(self, n):
        self.rows = self.rows[:n]
        return self

    async def to_list(self, n):
        return copy.deepcopy(self.rows[:n])


class _Collection:
    def __init__(self, rows=None):
        self.rows = copy.deepcopy(rows or [])
        self.update_calls = 0

    def find(self, query, _projection=None):
        return _Cursor([r for r in self.rows if _match(r, query)])

    async def find_one(self, query, _projection=None):
        hit = next((r for r in self.rows if _match(r, query)), None)
        return copy.deepcopy(hit) if hit else None

    async def insert_one(self, doc):
        self.rows.append(copy.deepcopy(doc))
        return types.SimpleNamespace(inserted_id=doc.get("_id"))

    async def update_one(self, query, update, upsert=False):
        self.update_calls += 1
        row = next((r for r in self.rows if _match(r, query)), None)
        matched = row is not None
        if not row and upsert:
            row = {}
            for k, v in query.items():
                if not isinstance(v, dict):
                    row[k] = v
            self.rows.append(row)
        if row is not None:
            for k, v in (update.get("$setOnInsert") or {}).items():
                row.setdefault(k, copy.deepcopy(v))
            for k, v in (update.get("$set") or {}).items():
                row[k] = copy.deepcopy(v)
        return types.SimpleNamespace(matched_count=int(matched), modified_count=int(row is not None))


class _FakeDB:
    def __init__(self, *, docs=None, users=None, library_items=None, shared_items=None):
        self.pro_documents = _Collection(docs)
        self.users = _Collection(users)
        self.library_items = _Collection(library_items)
        self.shared_library_items = _Collection(shared_items)


def _valid_args(title="DEV-1", client="Client A", *, lines=None):
    return {
        "title": title,
        "client_name": client,
        "vat_rate": 20.0,
        "notes": "",
        "lines": lines or [{
            "line_id": None,
            "description": "desc",
            "designation": "Peinture",
            "quantity": 2.0,
            "unit": "m²",
            "unit_price": 12.34,
            "price_origin": "user",
            "vat_rate": 20.0,
            "lot": "Finition",
        }],
    }


@pytest.fixture(autouse=True)
def _stub_dynamic_modules(monkeypatch):
    def fake_compute_totals(lines, deposit_pct=0):
        return _compute_totals(lines, deposit_pct)

    plans_analysis = types.SimpleNamespace(
        _build_index=lambda rows: list(rows),
        _candidates=lambda query, index, same_unit=False, k=30: [
            (0.98, r) for r in index if str(r.get("designation", "")).lower() == str(query.get("designation", "")).lower()
        ],
    )
    shared_lib = types.SimpleNamespace(
        _is_pro_business=lambda _user: asyncio.sleep(0, result=False),
        get_shared_items_for_level=lambda _level, lang=None: asyncio.sleep(0, result=[]),
        resolve_price_level=lambda _uid: asyncio.sleep(0, result="moyen"),
    )
    plans_common = types.SimpleNamespace(_resolve_branding=lambda _uid: asyncio.sleep(0, result={"country": "FR"}))
    docs_module = types.SimpleNamespace(_compute_totals=fake_compute_totals)

    monkeypatch.setitem(sys.modules, "routes.plans_analysis", plans_analysis)
    monkeypatch.setitem(sys.modules, "routes.shared_library", shared_lib)
    monkeypatch.setitem(sys.modules, "routes.plans_common", plans_common)
    monkeypatch.setitem(sys.modules, "routes.documents", docs_module)


# ---------------- assistant_quote_service safeguards ----------------
@pytest.mark.anyio
async def test_idempotent_retry_same_request_returns_original_without_overwrite(monkeypatch):
    db = _FakeDB()
    monkeypatch.setattr(service, "db", db)
    user = {"user_id": "u1", "role": "owner"}
    conv = {"conversation_id": "conv1", "user_id": "u1", "_quote_request_id": "nonce-1", "_quote_create_slot": 0}

    first = await service.save_quote(_valid_args(title="FIRST"), user, conv)
    second = await service.save_quote(_valid_args(title="SECOND", lines=[{**_valid_args()["lines"][0], "designation": "Autre"}]), user, conv)

    assert second["doc_id"] == first["doc_id"]
    stored = await db.pro_documents.find_one({"doc_id": first["doc_id"], "user_id": "u1", "doc_type": "quote"})
    assert stored["title"] == "FIRST"
    assert stored["lines"][0]["designation"] == "Peinture"


@pytest.mark.anyio
async def test_idempotent_concurrent_create_same_nonce_creates_one_doc(monkeypatch):
    db = _FakeDB()
    monkeypatch.setattr(service, "db", db)
    user = {"user_id": "u1", "role": "owner"}
    conv = {"conversation_id": "conv1", "user_id": "u1", "_quote_request_id": "nonce-2", "_quote_create_slot": 0}

    async def _run(i):
        return await service.save_quote(_valid_args(title=f"T{i}"), user, conv)

    results = await asyncio.gather(*[_run(i) for i in range(6)])
    assert len({r["doc_id"] for r in results}) == 1
    assert len(db.pro_documents.rows) == 1


@pytest.mark.anyio
async def test_id_changes_for_request_session_user_and_slot(monkeypatch):
    db = _FakeDB()
    monkeypatch.setattr(service, "db", db)
    base = _valid_args()
    user1 = {"user_id": "u1", "role": "owner"}
    user2 = {"user_id": "u2", "role": "owner"}
    out = []
    out.append(await service.save_quote(base, user1, {"conversation_id": "c1", "user_id": "u1", "_quote_request_id": "r1", "_quote_create_slot": 0}))
    out.append(await service.save_quote(base, user1, {"conversation_id": "c1", "user_id": "u1", "_quote_request_id": "r2", "_quote_create_slot": 0}))
    out.append(await service.save_quote(base, user1, {"conversation_id": "c2", "user_id": "u1", "_quote_request_id": "r1", "_quote_create_slot": 0}))
    out.append(await service.save_quote(base, user2, {"conversation_id": "c1", "user_id": "u2", "_quote_request_id": "r1", "_quote_create_slot": 0}))
    out.append(await service.save_quote(base, user1, {"conversation_id": "c1", "user_id": "u1", "_quote_request_id": "r1", "_quote_create_slot": 1}))
    assert len({r["doc_id"] for r in out}) == 5


@pytest.mark.anyio
async def test_read_quote_is_owner_scoped(monkeypatch):
    doc = {
        "doc_id": "doc_x", "user_id": "u1", "doc_type": "quote", "title": "X", "status": "draft",
        "lines": [{"line_id": "ql_1", "designation": "A", "description": "", "qty": 1, "unit": "u", "unit_price_ht": 1, "vat_rate": 20}],
        "totals": {"ht": 1, "tva": 0.2, "ttc": 1.2},
    }
    db = _FakeDB(docs=[doc])
    monkeypatch.setattr(service, "db", db)
    with pytest.raises(HTTPException) as exc:
        await service.read_quote("doc_x", {"user_id": "u2", "role": "owner"})
    assert exc.value.status_code == 404


@pytest.mark.anyio
async def test_update_stale_expected_updated_at_conflict(monkeypatch):
    previous = {
        "doc_id": "doc_stale", "user_id": "u1", "doc_type": "quote", "title": "A", "status": "draft", "signed": False,
        "updated_at": "t1", "lines": [{"line_id": "ql_1", "designation": "A", "description": "", "qty": 1, "unit": "u", "unit_price_ht": 1,
                                            "cost_price_ht": 0, "category": "", "vat_rate": 20, "price_estimated": False, "price_missing": False}],
        "totals": {"ht": 1, "tva": 0.2, "ttc": 1.2},
    }
    db = _FakeDB(docs=[previous])
    monkeypatch.setattr(service, "db", db)
    with pytest.raises(HTTPException) as exc:
        await service.save_quote(_valid_args(), {"user_id": "u1", "role": "owner"}, {"conversation_id": "c", "user_id": "u1"},
                                 doc_id="doc_stale", expected_updated_at="older")
    assert exc.value.status_code == 409


@pytest.mark.anyio
async def test_update_atomic_concurrent_mutation_only_one_wins(monkeypatch):
    previous = {
        "doc_id": "doc_race", "user_id": "u1", "doc_type": "quote", "title": "A", "status": "draft", "signed": False,
        "updated_at": "base", "lines": [{"line_id": "ql_1", "designation": "A", "description": "", "qty": 1, "unit": "u", "unit_price_ht": 1,
                                             "cost_price_ht": 0, "category": "", "vat_rate": 20, "price_estimated": False, "price_missing": False}],
        "totals": {"ht": 1, "tva": 0.2, "ttc": 1.2},
    }
    db = _FakeDB(docs=[previous])
    monkeypatch.setattr(service, "db", db)
    user = {"user_id": "u1", "role": "owner"}
    conv = {"conversation_id": "c", "user_id": "u1"}

    async def upd(tag):
        return await service.save_quote(_valid_args(title=f"T-{tag}"), user, conv, doc_id="doc_race", expected_updated_at="base")

    ok = 0
    conflict = 0
    for result in await asyncio.gather(upd("1"), upd("2"), return_exceptions=True):
        if isinstance(result, Exception):
            assert isinstance(result, HTTPException)
            assert result.status_code == 409
            conflict += 1
        else:
            ok += 1
    assert ok == 1 and conflict == 1


@pytest.mark.anyio
async def test_update_guards_sent_or_signed(monkeypatch):
    base = {
        "doc_id": "doc_guard", "user_id": "u1", "doc_type": "quote", "title": "A", "updated_at": "t1",
        "lines": [{"line_id": "ql_1", "designation": "A", "description": "", "qty": 1, "unit": "u", "unit_price_ht": 1,
                   "cost_price_ht": 0, "category": "", "vat_rate": 20, "price_estimated": False, "price_missing": False}],
        "totals": {"ht": 1, "tva": 0.2, "ttc": 1.2},
    }
    for blocked in ({**base, "status": "sent", "signed": False}, {**base, "status": "draft", "signed": True}):
        db = _FakeDB(docs=[blocked])
        monkeypatch.setattr(service, "db", db)
        with pytest.raises(HTTPException) as exc:
            await service.save_quote(_valid_args(), {"user_id": "u1", "role": "owner"}, {"conversation_id": "c", "user_id": "u1"},
                                     doc_id="doc_guard", expected_updated_at="t1")
        assert exc.value.status_code == 409


@pytest.mark.anyio
async def test_update_blocks_crm_linked_client_rename_without_mutation(monkeypatch):
    previous = {
        "doc_id": "doc_crm", "user_id": "u1", "doc_type": "quote", "title": "A", "status": "draft", "signed": False,
        "updated_at": "t1", "client_id": "cli_1", "client": {"company": "ACME"},
        "lines": [{"line_id": "ql_1", "designation": "A", "description": "", "qty": 1, "unit": "u", "unit_price_ht": 1,
                    "cost_price_ht": 0, "category": "", "vat_rate": 20, "price_estimated": False, "price_missing": False}],
        "totals": {"ht": 1, "tva": 0.2, "ttc": 1.2},
    }
    db = _FakeDB(docs=[previous])
    monkeypatch.setattr(service, "db", db)
    with pytest.raises(HTTPException) as exc:
        await service.save_quote(_valid_args(client="Different Name"), {"user_id": "u1", "role": "owner"},
                                 {"conversation_id": "c", "user_id": "u1"}, doc_id="doc_crm", expected_updated_at="t1")
    assert exc.value.status_code == 409
    assert db.pro_documents.update_calls == 0


# ---------------- assistant_quote_pricing + schema + documents guards ----------------
@pytest.mark.anyio
async def test_build_lines_preserves_line_id_description_cost_and_user_prices(monkeypatch):
    db = _FakeDB(users=[{"user_id": "u1"}], library_items=[])
    monkeypatch.setattr(pricing, "db", db)
    prev = {
        "lines": [{"line_id": "legacy_a", "designation": "Peinture", "description": "mur", "qty": 1, "unit": "m²", "unit_price_ht": 10,
                    "cost_price_ht": 7.7, "category": "Lot1", "vat_rate": 20, "price_estimated": True, "price_source": "company_library",
                    "price_reference": "lib1", "price_reference_label": "Peinture", "price_missing": False}]
    }
    body = schema.QuoteInput.model_validate(_valid_args(lines=[
        {"line_id": "legacy_a", "description": "mur", "designation": "Peinture", "quantity": 3.0, "unit": "m²", "unit_price": 12.34,
         "price_origin": "user", "vat_rate": 10.0, "lot": "Lot1"},
        {"line_id": None, "description": "offert", "designation": "Déplacement", "quantity": 1.0, "unit": "u", "unit_price": 0.0,
         "price_origin": "user", "vat_rate": None, "lot": "Lot2"},
    ]))
    lines = await pricing.build_lines(body, {"user_id": "u1", "role": "owner"}, prev)
    assert lines[0]["line_id"] == "legacy_a"
    assert lines[0]["description"] == "mur"
    assert lines[0]["cost_price_ht"] == 7.7
    assert lines[0]["unit_price_ht"] == 12.34
    assert lines[1]["unit_price_ht"] == 0.0
    assert lines[1]["price_source"] == "user_input"


@pytest.mark.anyio
async def test_library_match_unit_normalization_and_unknown_unit_remains_missing(monkeypatch):
    db = _FakeDB(users=[{"user_id": "u1", "price_library_mode": "shared_first", "brand_country": "FR"}],
                 library_items=[{"item_id": "lib_1", "user_id": "u1", "designation": "Peinture", "unit": "m2", "unit_price_ht": 18.75, "source": "manual"}])
    monkeypatch.setattr(pricing, "db", db)
    body = schema.QuoteInput.model_validate(_valid_args(lines=[
        {"line_id": None, "description": "", "designation": "Peinture", "quantity": 2.0, "unit": "m²", "unit_price": None,
         "price_origin": "library", "vat_rate": 20.0, "lot": "Lot1"},
        {"line_id": None, "description": "", "designation": "Inconnu", "quantity": 1.0, "unit": "kg", "unit_price": None,
         "price_origin": "library", "vat_rate": 20.0, "lot": "Lot1"},
    ]))
    lines = await pricing.build_lines(body, {"user_id": "u1", "role": "owner"}, previous=None)
    assert lines[0]["unit_price_ht"] == 18.75
    assert lines[0]["price_estimated"] is True
    assert lines[1]["price_missing"] is True
    assert lines[1]["price_source"] == "unpriced"


@pytest.mark.anyio
async def test_ambiguous_or_mismatched_candidates_are_not_priced(monkeypatch):
    db = _FakeDB(users=[{"user_id": "u1", "price_library_mode": "shared_first", "brand_country": "FR"}],
                 library_items=[
                     {"item_id": "i1", "designation": "Carrelage", "unit": "m²", "unit_price_ht": 10},
                     {"item_id": "i2", "designation": "Carrelage", "unit": "m²", "unit_price_ht": 11},
                 ])
    monkeypatch.setattr(pricing, "db", db)
    fake_pa = types.SimpleNamespace(
        _build_index=lambda rows: rows,
        _candidates=lambda query, index, same_unit=False, k=30: [(0.9, index[0]), (0.85, index[1])],
    )
    monkeypatch.setitem(sys.modules, "routes.plans_analysis", fake_pa)
    body = schema.QuoteInput.model_validate(_valid_args(lines=[
        {"line_id": None, "description": "", "designation": "Carrelage", "quantity": 3.0, "unit": "m²", "unit_price": None,
         "price_origin": "library", "vat_rate": 20.0, "lot": "Lot1"}
    ]))
    lines = await pricing.build_lines(body, {"user_id": "u1", "role": "owner"}, None)
    assert lines[0]["price_missing"] is True


@pytest.mark.anyio
async def test_preserve_estimated_snapshot_no_silent_reprice_for_unchanged_line(monkeypatch):
    db = _FakeDB(users=[{"user_id": "u1", "price_library_mode": "shared_first", "brand_country": "FR"}], library_items=[])
    monkeypatch.setattr(pricing, "db", db)
    prev = {"lines": [{"line_id": "ql_1", "designation": "Peinture", "description": "mur", "qty": 2, "unit": "m²", "unit_price_ht": 18.75,
                        "cost_price_ht": 0, "category": "Lot1", "vat_rate": 20, "price_estimated": True,
                        "price_source": "company_library", "price_reference": "lib_old", "price_reference_label": "Peinture", "price_missing": False}]}
    body = schema.QuoteInput.model_validate(_valid_args(lines=[
        {"line_id": "ql_1", "description": "mur", "designation": "Peinture", "quantity": 2.0, "unit": "m²", "unit_price": None,
         "price_origin": "library", "vat_rate": 20.0, "lot": "Lot1"}
    ]))
    lines = await pricing.build_lines(body, {"user_id": "u1", "role": "owner"}, prev)
    assert lines[0]["unit_price_ht"] == 18.75
    assert lines[0]["price_reference"] == "lib_old"


@pytest.mark.anyio
async def test_price_sources_respects_mode_and_shared_entitlement(monkeypatch):
    db = _FakeDB(users=[{"user_id": "u1", "price_library_mode": "company_only", "lang": "fr"}],
                 library_items=[{"user_id": "u1", "designation": "A", "unit": "u", "unit_price_ht": 1}], shared_items=[])
    monkeypatch.setattr(pricing, "db", db)
    sources = await pricing.price_sources({"user_id": "u1", "role": "owner"})
    assert [name for name, _idx in sources] == ["company_library"]


@pytest.mark.anyio
async def test_build_lines_pt_default_vat23_fr20_and_quantity_missing_partial(monkeypatch):
    db = _FakeDB(users=[{"user_id": "u1"}], library_items=[])
    monkeypatch.setattr(pricing, "db", db)
    monkeypatch.setitem(sys.modules, "routes.plans_common", types.SimpleNamespace(_resolve_branding=lambda _uid: asyncio.sleep(0, result={"country": "PT"})))

    payload = _valid_args(lines=[
        {"line_id": None, "description": "", "designation": "A", "quantity": None, "unit": "u", "unit_price": 1.01,
         "price_origin": "user", "vat_rate": None, "lot": ""},
        {"line_id": None, "description": "", "designation": "B", "quantity": 3.0, "unit": "u", "unit_price": 0.99,
         "price_origin": "user", "vat_rate": 6.0, "lot": ""},
    ])
    payload["vat_rate"] = None
    body = schema.QuoteInput.model_validate(payload)
    lines = await pricing.build_lines(body, {"user_id": "u1", "role": "owner"}, None)
    assert lines[0]["qty"] == 0 and lines[0]["quantity_missing"] is True
    assert lines[0]["vat_rate"] == 23
    assert lines[1]["vat_rate"] == 6.0
    totals = _compute_totals(lines)
    assert totals["ht"] == 2.97
    assert totals["ttc"] == 3.15


@pytest.mark.parametrize(
    "payload_patch",
    [
        {"lines": [_valid_args()["lines"][0]] * 151},
        {"lines": [{**_valid_args()["lines"][0], "quantity": True}]},
        {"lines": [{**_valid_args()["lines"][0], "quantity": float("nan")}]},
        {"lines": [{**_valid_args()["lines"][0], "unit_price": float("inf")}]},
        {"lines": [{**_valid_args()["lines"][0], "vat_rate": -1.0}]},
        {"evil": "x"},
        {"lines": [{**_valid_args()["lines"][0], "unknown_field": "hack"}]},
    ],
)
def test_schema_rejects_each_invalid_case_independently(payload_patch):
    payload = _valid_args()
    payload.update(payload_patch)
    with pytest.raises(ValidationError):
        schema.QuoteInput.model_validate(payload)


@pytest.mark.anyio
async def test_docline_roundtrip_and_autosave_skips_estimated_or_unpriced(monkeypatch):
    parsed = DocLine.model_validate({
        "line_id": "ql_1", "designation": "Pose", "description": "X", "unit": "u", "qty": 1,
        "unit_price_ht": 12.34, "cost_price_ht": 5.67, "vat_rate": 20, "category": "Lot",
        "price_source": "user_input", "price_reference": "lib_1", "price_reference_label": "Pose",
        "price_estimated": False, "price_missing": False, "quantity_missing": False, "vat_assumed": False,
    })
    assert parsed.model_dump()["price_reference"] == "lib_1"

    db = _FakeDB(library_items=[{"item_id": "lib_existing", "user_id": "u1", "designation": "Pose", "unit_price_ht": 8.0}])
    from routes import library as library_route
    monkeypatch.setattr(library_route, "db", db)
    saved = await auto_save_from_lines("u1", [
        {"designation": "Pose", "unit": "u", "unit_price_ht": 12.34, "vat_rate": 20, "price_estimated": False, "price_missing": False,
         "quantity_missing": False, "description": "valid", "cost_price_ht": 4.0, "category": "Lot"},
        {"designation": "Estimated", "unit": "u", "unit_price_ht": 99, "vat_rate": 20, "price_estimated": True, "price_missing": False,
         "quantity_missing": False},
        {"designation": "Missing", "unit": "u", "unit_price_ht": 99, "vat_rate": 20, "price_estimated": False, "price_missing": True,
         "quantity_missing": False},
    ])
    assert saved == 1
    existing = await db.library_items.find_one({"user_id": "u1", "item_id": "lib_existing"})
    assert existing["unit_price_ht"] == 12.34


# ---------------- assistant route _exec_tool quote tool exposure ----------------
@pytest.mark.anyio
async def test_exec_tool_quote_exposure_professional_allowed_worker_particular_denied(monkeypatch):
    async def _fake_save(args, user, conv, **kwargs):
        return {"ok": True, "doc_id": "doc_fake", "draft": {"doc_id": "doc_fake"}, "args": args, "uid": user["user_id"], "conv": conv["conversation_id"]}

    async def _fake_read(doc_id, user):
        return {"ok": True, "doc_id": doc_id, "uid": user["user_id"]}

    from engines import assistant_quote_service as quote_service

    monkeypatch.setattr(assistant_route, "validate_args", lambda *_a, **_k: None)
    monkeypatch.setattr(quote_service, "save_quote", _fake_save)
    monkeypatch.setattr(quote_service, "read_quote", _fake_read)

    conv = {"conversation_id": "conv_tools", "user_id": "pro1", "project_id": None}
    pro = {"user_id": "pro1", "role": "owner", "account_type": "professional", "organization_id": "org1", "org_role": "owner", "company_active": True, "active": True}
    worker = {"user_id": "w1", "role": "worker", "account_type": "professional", "company_active": True, "active": True}
    particulier = {"user_id": "p1", "role": "admin", "account_type": "particulier", "company_active": True, "active": True}

    create_payload = _valid_args()
    out = await assistant_route._exec_tool("create_quote_draft", create_payload, pro, conv)
    assert out["ok"] is True
    read = await assistant_route._exec_tool("read_quote_draft", {"doc_id": "doc_fake"}, pro, conv)
    assert read["doc_id"] == "doc_fake"
    upd = await assistant_route._exec_tool("update_quote_draft", {"doc_id": "doc_fake", "expected_updated_at": "t1", **create_payload}, pro, conv)
    assert upd["ok"] is True

    denied_worker = await assistant_route._exec_tool("create_quote_draft", create_payload, worker, {**conv, "user_id": "w1"})
    denied_particulier = await assistant_route._exec_tool("create_quote_draft", create_payload, particulier, {**conv, "user_id": "p1"})
    assert denied_worker["ok"] is False
    assert denied_particulier["ok"] is False
