"""Real queue lifecycle with an in-memory store; no Mongo or AI network calls."""
import asyncio
import copy
import importlib.util
import sys
import types
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import AsyncMock, patch

from pymongo.errors import DuplicateKeyError
from test_assistant_workspace_regressions import A

spec = importlib.util.spec_from_file_location("isolated_assistant_jobs", Path(__file__).parents[1] / "engines/assistant_jobs.py")
J = importlib.util.module_from_spec(spec)
stub = types.ModuleType("core.db")
stub.db = None
with patch.dict(sys.modules, {"core.db": stub}):
    spec.loader.exec_module(J)


def matches(row, query):
    for key, value in query.items():
        if key == "$or":
            if not any(matches(row, q) for q in value):
                return False
        elif isinstance(value, dict):
            for op, expected in value.items():
                if op == "$exists":
                    ok = (key in row) == expected
                elif op == "$in":
                    ok = row.get(key) in expected
                elif op == "$lt":
                    ok = key in row and row[key] < expected
                else:
                    raise AssertionError(f"Unsupported query: {op}")
                if not ok:
                    return False
        elif row.get(key) != value:
            return False
    return True


class Cursor:
    def __init__(self, rows):
        self.rows = copy.deepcopy(rows)

    def sort(self, key, direction):
        self.rows.sort(key=lambda r: r[key], reverse=direction < 0)
        return self

    def limit(self, count):
        self.rows = self.rows[:count]
        return self

    async def to_list(self, count):
        return self.rows[:count]

    def __aiter__(self):
        async def items():
            for row in self.rows:
                yield row
        return items()


class Collection:
    def __init__(self):
        self.rows = []

    def find(self, query, projection=None):
        return Cursor([r for r in self.rows if matches(r, query)])

    async def find_one(self, query, projection=None):
        return next((copy.deepcopy(r) for r in self.rows if matches(r, query)), None)

    async def count_documents(self, query):
        return len([r for r in self.rows if matches(r, query)])

    async def insert_one(self, row):
        if row.get("job_id") and any(r.get("job_id") == row["job_id"] for r in self.rows):
            raise DuplicateKeyError("job_id")
        self.rows.append(copy.deepcopy(row))

    async def update_one(self, query, update, upsert=False):
        row = next((r for r in self.rows if matches(r, query)), None)
        found = row is not None
        if not found and upsert:
            row = copy.deepcopy(query)
            row.update(copy.deepcopy(update.get("$setOnInsert", {})))
            self.rows.append(row)
        if row is not None:
            row.update(copy.deepcopy(update.get("$set", {})))
            for key, amount in update.get("$inc", {}).items():
                row[key] = row.get(key, 0) + amount
            for key in update.get("$unset", {}):
                row.pop(key, None)
        return types.SimpleNamespace(matched_count=int(found))

    async def update_many(self, query, update):
        for row in list(self.rows):
            if matches(row, query):
                await self.update_one({"job_id": row["job_id"]} if "job_id" in row else row.copy(), update)

    async def find_one_and_update(self, query, update, return_document=False, projection=None):
        before = await self.find_one(query)
        if before is None:
            return None
        await self.update_one(query, update)
        identity = {"job_id": before["job_id"]} if "job_id" in before else {"conversation_id": before["conversation_id"]}
        return await self.find_one(identity) if return_document else before


class Database:
    def __init__(self):
        self.collections = {}

    def __getattr__(self, key):
        return self.collections.setdefault(key, Collection())


class BackgroundJobs(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.db = Database()
        self.user = {"user_id": "owner", "active": True}
        self.db.users.rows = [self.user.copy()]
        self.db.assistant_convs.rows = [{"conversation_id": "ours", "user_id": "owner", "title": "Nouvelle conversation"}]
        self.enterContext(patch.object(J, "db", self.db))
        self.enterContext(patch.dict(sys.modules, {"routes.assistant": A}))

    async def enqueue(self, request="r1", **kwargs):
        return await J.enqueue(A.MsgIn(conversation_id="ours", text="Vérifie le dossier", request_id=request, **kwargs), self.user)

    async def test_retry_is_idempotent_and_changed_payload_rejected(self):
        first = await self.enqueue()
        self.assertEqual(first, await self.enqueue())
        self.assertEqual(len(self.db.assistant_msgs.rows), 1)
        self.assertEqual(self.db.assistant_convs.rows[0]["turn_sequence"], 1)
        with self.assertRaises(J.HTTPException) as error:
            await J.enqueue(A.MsgIn(conversation_id="ours", text="Autre demande", request_id="r1"), self.user)
        self.assertEqual(error.exception.status_code, 409)

    async def test_foreign_conversation_and_job_are_inaccessible(self):
        job = await self.enqueue()
        with self.assertRaises(J.HTTPException) as error:
            await J.owned_job(job["job_id"], "other")
        self.assertEqual(error.exception.status_code, 404)
        with self.assertRaises(J.HTTPException):
            await J.enqueue(A.MsgIn(conversation_id="ours", text="Read"), {"user_id": "other"})

    async def test_only_one_worker_claims_each_conversation_in_sequence(self):
        await self.enqueue("r1")
        await self.enqueue("r2")
        first = await J.claim_next("worker-a")
        self.assertEqual(first["sequence"], 1)
        self.assertIsNone(await J.claim_next("worker-b"))
        await J._finish(first, "completed", {"content": "Done"})
        self.assertEqual((await J.claim_next("worker-b"))["sequence"], 2)

    async def test_active_feed_is_owner_scoped_and_omits_private_payloads(self):
        job = await self.enqueue()
        self.db.assistant_jobs.rows.append({**self.db.assistant_jobs.rows[0], "job_id": "foreign", "user_id": "other"})
        result = await J.active_jobs("owner")
        self.assertEqual([r["job_id"] for r in result], [job["job_id"]])
        self.assertEqual(set(result[0]), {"job_id", "conversation_id", "status", "created_at"})
        await J.cancel_job(job["job_id"], "owner")
        self.assertEqual(await J.active_jobs("owner"), [])

    async def test_worker_finishes_and_notifies_without_browser_poller(self):
        await self.enqueue()
        job = await J.claim_next("worker")
        started, resume = asyncio.Event(), asyncio.Event()

        async def stream(*args, **kwargs):
            yield {"type": "delta", "text": "Lecture en cours"}
            started.set()
            await resume.wait()
            yield {"type": "done", "message": {"role": "assistant", "content": "Analyse terminée", "request_id": "r1"}}

        with patch.object(A, "_prepare", AsyncMock(return_value=({}, None, None, None))), patch.object(A, "_run_chat", stream):
            worker = asyncio.create_task(J.run_job(job))
            await asyncio.wait_for(started.wait(), 1)
            self.assertEqual(self.db.assistant_jobs.rows[0]["live"]["content"], "Lecture en cours")
            resume.set()
            await asyncio.wait_for(worker, 3)
        self.assertEqual(self.db.assistant_jobs.rows[0]["status"], "completed")
        self.assertEqual(self.db.assistant_jobs.rows[0]["live"]["content"], "Analyse terminée")
        notice = self.db.notifications.rows[0]
        self.assertTrue(notice["notif_id"])
        self.assertEqual(notice["link"], "/assistant?conversation=ours")
        await J._finish(job, "completed", {})
        self.assertEqual(len(self.db.notifications.rows), 1)

    async def test_expired_lease_is_interrupted_never_replayed(self):
        await self.enqueue()
        await J.claim_next("old-worker")
        self.db.assistant_jobs.rows[0]["lease_until"] = datetime.now(timezone.utc) - timedelta(seconds=1)
        self.db.assistant_jobs.rows[0]["live"] = {"content": "Résultat partiel"}
        self.assertIsNone(await J.claim_next("new-worker"))
        self.assertEqual(self.db.assistant_jobs.rows[0]["status"], "interrupted")
        self.assertEqual(self.db.assistant_jobs.rows[0]["live"]["content"], "Résultat partiel")
        self.assertEqual(len(self.db.notifications.rows), 1)

    async def test_explicit_cancel_removes_queued_job(self):
        job = await self.enqueue()
        self.assertEqual((await J.cancel_job(job["job_id"], "owner"))["status"], "cancelled")
        self.assertIsNone(await J.claim_next("worker"))
        self.assertTrue(self.db.assistant_msgs.rows[0]["cancelled"])

    async def test_worker_shutdown_preserves_partial_answer_and_interruption(self):
        await self.enqueue()
        job = await J.claim_next("worker")
        started = asyncio.Event()

        async def stream(*args, **kwargs):
            yield {"type": "delta", "text": "Première vérification"}
            started.set()
            await asyncio.Event().wait()

        with patch.object(A, "_prepare", AsyncMock(return_value=({}, None, None, None))), patch.object(A, "_run_chat", stream):
            worker = asyncio.create_task(J.run_job(job))
            await asyncio.wait_for(started.wait(), 1)
            worker.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await worker
        self.assertEqual(self.db.assistant_jobs.rows[0]["status"], "interrupted")
        answer = self.db.assistant_msgs.rows[-1]
        self.assertTrue(answer["interrupted"])
        self.assertEqual(answer["content"], "Première vérification")
