"""Offline regression checks of real calculations and route functions.

AST isolation avoids importing application startup, databases and paid services.
Run: PYTHONPATH=backend python -m unittest discover -s backend/tests -p test_audit_regressions.py -v
"""
import ast
import copy
import hashlib
import ipaddress
import math
import secrets
import socket
import unittest
from datetime import datetime, timezone, timedelta
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import AsyncMock, Mock
from urllib.parse import urlparse, urljoin

import httpx
from fastapi import HTTPException
from engines import geometry as G
from engines import plan_quantities as PQ
from engines.metre import quantities as Q
from engines.metre.heights import derive_heights, volumes_from_takeoff

ROOT = Path(__file__).parents[1]
SQUARE = [[0, 0], [100, 0], [100, 100], [0, 100]]
USER = {"user_id": "audit-user"}


def functions(path, names, **extra):
    nodes = [n for n in ast.parse((ROOT / path).read_text()).body
             if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name in names]
    assert {n.name for n in nodes} == set(names)
    for node in nodes:
        node.decorator_list = []
    module = ast.Module(body=[ast.ImportFrom(module="__future__", names=[ast.alias(name="annotations")], level=0), *nodes], type_ignores=[])
    ns = dict(G=G, math=math, secrets=secrets, hashlib=hashlib, datetime=datetime,
              timezone=timezone, timedelta=timedelta, HTTPException=HTTPException,
              Depends=lambda *a, **k: None, current_user=None, optional_user=None,
              _now=lambda: "audit-now", now_iso=lambda: "audit-now", _snapshot=AsyncMock(),
              recompute_room=PQ.recompute_room, recalibrate_measurement=PQ.recalibrate_measurement,
              _recompute_linear_sets=PQ.recompute_linear_sets, _measure_gross_m=PQ._measure_gross_m)
    ns.update(extra)
    exec(compile(ast.fix_missing_locations(module), str(ROOT / path), "exec"), ns)
    return ns


class Collection:
    def __init__(self, doc):
        self.doc = copy.deepcopy(doc)
        self.reject_write = False

    async def find_one(self, query, projection=None):
        return copy.deepcopy(self.doc) if all(self.doc.get(k) == v for k, v in query.items()) else None

    async def update_one(self, query, update):
        if self.reject_write or not all(self.doc.get(k) == v for k, v in query.items()):
            return NS(matched_count=0, modified_count=0)
        for key, value in update.get("$set", {}).items():
            target = self.doc
            parts = key.split(".")
            for part in parts[:-1]:
                target = target.setdefault(part, {})
            target[parts[-1]] = copy.deepcopy(value)
        for key in update.get("$unset", {}):
            target = self.doc
            parts = key.split(".")
            for part in parts[:-1]:
                target = target.get(part, {})
            target.pop(parts[-1], None)
        for key, value in update.get("$push", {}).items():
            items = self.doc.setdefault(key, [])
            items.extend(copy.deepcopy(value["$each"]))
            if "$slice" in value:
                n = value["$slice"]
                self.doc[key] = items[n:] if n < 0 else items[:n]
        return NS(matched_count=1, modified_count=1)


def plan():
    return {"plan_id": "p", **USER, "pages": [{"index": 0}, {"index": 1}],
            "calibrations": {"0": {"pixels_per_meter": 100}}, "rooms": [], "measurements": []}


class Quantities(unittest.TestCase):
    def test_invalid_levels_never_produce_negative_concrete(self):
        levels = {"as_plancher_haut_m": 10, "epaisseur_dalle_m": .2, "niveau_base_murs_m": 11}
        self.assertIsNone(derive_heights(levels)["h_murs_m"])
        result = volumes_from_takeoff({"elements": {"walls": {"plan_area_m2": 10}}}, levels)
        self.assertIsNone(result["total_m3"])
        self.assertTrue(all(line["net"] is None or line["net"] >= 0 for line in result["lines"]))

    def test_local_height_exception_prevents_confirmed_total(self):
        levels = {"as_plancher_haut_m": 10, "epaisseur_dalle_m": .2, "niveau_base_murs_m": 7, "exceptions": ["local height"]}
        self.assertIsNone(volumes_from_takeoff({"elements": {"walls": {"plan_area_m2": 10}}}, levels)["total_m3"])

    def test_btp_engine_counts_openings_and_floor_deductions(self):
        source = ast.parse((ROOT / "btp_ai/metre.py").read_text())
        constants = {n.targets[0].id: ast.literal_eval(n.value) for n in source.body
                     if isinstance(n, ast.Assign) and isinstance(n.targets[0], ast.Name) and n.targets[0].id in ("RULES", "RULES_VERSION")}
        ns = functions("btp_ai/metre.py", {"_id", "_shoelace", "build_elements", "compute_quantities"}, **constants)
        p = plan()
        p["rooms"] = [{"room_id": "r", "points": SQUARE, "ceiling_height_m": 3,
                       "deductions": [{"points": [[0, 0], [50, 0], [50, 50], [0, 50]], "area_m2": .25}],
                       "openings": [{"kind": "fenetre", "width_m": 1, "height_m": 2, "count": 3}]}]
        elements, _ = ns["build_elements"](p)
        q = {line["rule"]: line for line in ns["compute_quantities"](elements, {})}
        self.assertEqual(q["dalle_surface"]["quantity_net"], .75)
        self.assertEqual(q["mur_surface_nette"]["quantity_net"], 6)
        self.assertEqual(q["ouverture_unite"]["quantity_net"], 3)

    def test_partial_concrete_is_never_presented_as_complete(self):
        from collections import Counter
        from shapely.geometry import box
        from engines.metre.coupe_zones import assign_wall_zones
        takeoff = {"layers": {}, "elements": {"walls": {}, "columns": {"count": 0},
                    "beams": {"count": 1, "length_total_m": 2}, "slab": {"net_area_m2": 10}},
                    "_geometry": {"wall_bodies": [box(0, 0, 1, .2)], "unit_to_m": 1}}
        ns = functions("engines/metre/volumes_tool.py", {"compute_volumes"},
                       Counter=Counter, coffrage_takeoff=lambda *a, **k: copy.deepcopy(takeoff),
                       coupe_sheet_data=lambda c: {}, derive_heights=derive_heights,
                       assign_wall_zones=assign_wall_zones)
        result = ns["compute_volumes"](b"mock", None, None,
                 {"as_plancher_haut_m": 3.2, "epaisseur_dalle_m": .2, "niveau_base_murs_m": 0})
        self.assertIsNone(result["total_m3"])
        self.assertEqual(result["partial_total_m3"], 2.6)
        self.assertTrue(any(line["state"] == "indeterminate" for line in result["lines"]))

    def test_opening_multiplicity_and_legacy_default(self):
        self.assertEqual(G.subtract_openings(30, [{"width_m": 1, "height_m": 2, "count": 3}])["wall_area_net_m2"], 24)
        self.assertEqual(G.subtract_openings(30, [{"width_m": 1, "height_m": 2}])["wall_area_net_m2"], 28)

    def test_calibration_rejects_non_finite_and_zero_rounded_scale(self):
        for p2, distance in [((100, 0), float("nan")), ((float("inf"), 0), 2), ((.00001, 0), 10000)]:
            with self.subTest(p2=p2, distance=distance), self.assertRaises(ValueError):
                G.compute_calibration((0, 0), p2, distance)

    def test_room_holes_are_recalculated_with_scale(self):
        r = {"points": SQUARE, "ceiling_height_m": 3,
             "deductions": [{"points": [[0, 0], [50, 0], [50, 50], [0, 50]], "area_m2": .25}]}
        PQ.recompute_room(r, 50)
        self.assertEqual((r["surface_m2"], r["deductions_area_m2"], r["volume_m3"]), (3, 1, 9))

    def test_cumulative_quantities_and_drawn_openings(self):
        m = {"kind": "cumulative", "segments": [[[0, 0], [100, 0]], [[0, 0], [0, 100]]],
             "wall_height_m": 3, "openings": [{"width_m": .5, "height_m": 2, "count": 2,
                                               "points": [[0, 0], [25, 0]]}]}
        PQ.recalibrate_measurement(m, 25)
        self.assertEqual((m["gross_m"], m["length_m"], m["wall_area_net_m2"]), (8, 6, 20))
        area = {"kind": "cumulative_area", "polygons": [SQUARE, SQUARE]}
        PQ.recalibrate_measurement(area, 50)
        self.assertEqual((area["area_m2"], area["perimeter_m"]), (8, 16))

    def test_manual_dimensions_are_not_rescaled(self):
        m = {"kind": "manual_linear", "length_m": 7, "points": []}
        self.assertEqual(PQ.recalibrate_measurement(copy.deepcopy(m), 50), m)

    def test_threshold_and_opening_count(self):
        item = {"length_m": 10, "height_m": 3, "deduction_rule": "threshold",
                "openings": [{"width_m": 1, "height_m": 2, "count": 3}]}
        self.assertIsNone(Q.wall_area(item).net)
        self.assertEqual(Q.wall_area({**item, "deduction_threshold_m2": 1}).net, 24)
        self.assertEqual(Q.wall_area({**item, "deduction_threshold_m2": 3}).net, 30)

    def test_invalid_values_never_enter_confirmed_totals(self):
        items = [{"category": "roof_area", "plan_area_m2": 10, "slope_deg": 90},
                 {"category": "concrete_volume", "area_m2": float("nan"), "height_m": 1},
                 {"category": "wall_area", "length_m": -2, "height_m": 3},
                 {"category": "packaged_units", "net_quantity": 20, "units_per_measure": 2, "pack_size": 0}]
        self.assertEqual(Q.calculate_quantities(items)["totals_confirmed"], {})

    def test_impossible_deductions_are_not_confirmed(self):
        q = Q.wall_area({"length_m": 1, "height_m": 1, "deduction_rule": "full",
                         "openings": [{"width_m": 2, "height_m": 2}]})
        self.assertIsNone(q.net)
        self.assertEqual(q.state, "indeterminate")


class PlanRoutes(unittest.IsolatedAsyncioTestCase):
    async def test_xlsx_keeps_cumulative_manual_and_zero_quantities(self):
        from io import BytesIO
        from openpyxl import load_workbook
        from fastapi.responses import Response
        p = plan()
        p["measurements"] = [{"kind": "cumulative_area", "area_m2": 12, "perimeter_m": 14},
                             {"kind": "manual_area", "area_m2": 7}, {"kind": "distance", "value_m": 0, "length_m": 0}]
        ns = functions("routes/plans_export.py", {"export_xlsx"}, db=NS(plans_takeoff=Collection(p)), Response=Response, BytesIO=BytesIO)
        response = await ns["export_xlsx"]("p", USER)
        wb = load_workbook(BytesIO(response.body))
        self.assertEqual(wb["Mesures"]["E2"].value, 12)
        self.assertEqual(wb["Mesures"]["F2"].value, 14)
        self.assertEqual(wb["Mesures"]["E3"].value, 7)
        self.assertEqual(wb["Mesures"]["D4"].value, 0)
    async def test_manual_calibration_recomputes_only_selected_page(self):
        p = plan()
        p["rooms"] = [{"room_id": "r", "page_index": 0, "points": SQUARE, "surface_m2": 1},
                      {"room_id": "other", "page_index": 1, "points": SQUARE, "surface_m2": 17}]
        p["measurements"] = [{"kind": "distance", "page_index": 0, "points": [[0, 0], [100, 0]], "length_m": 1}]
        p["studies"] = {"0": {"old": True}, "1": {"keep": True}}
        p["cotes_checks"] = {"0": {"items": [{"edited": True, "indicated_m": 4.02}], "revision": "old"}}
        db = NS(plans_takeoff=Collection(p))
        common = functions("routes/plans_common.py", {"_apply_new_calibration"}, db=db)
        ns = functions("routes/plans_crud.py", {"calibrate_plan"}, db=db, _apply_new_calibration=common["_apply_new_calibration"])
        await ns["calibrate_plan"]("p", NS(page_index=0, p1=(0, 0), p2=(100, 0), real_distance_m=2, method="two_points"), USER)
        saved = db.plans_takeoff.doc
        self.assertEqual([r["surface_m2"] for r in saved["rooms"]], [4, 17])
        self.assertEqual(saved["measurements"][0]["length_m"], 2)
        self.assertEqual(saved["studies"], {"1": {"keep": True}})
        self.assertEqual(saved["cotes_checks"]["0"]["items"], p["cotes_checks"]["0"]["items"])
        self.assertTrue(saved["cotes_checks"]["0"]["calibration_stale"])
        self.assertNotEqual(saved["cotes_checks"]["0"]["revision"], "old")

    async def test_vector_detection_cannot_replace_manual_scale(self):
        apply = AsyncMock()
        ns = functions("routes/plans_cotes.py", {"_ensure_calibration"}, _apply_new_calibration=apply)
        for method in ["manual", "two_points", "known_dimension"]:
            p = plan()
            p["calibrations"]["0"].update(method=method)
            result, changed = await ns["_ensure_calibration"](p, {"dpi": 72}, "p", 0, [], 100, 100, {"pt_per_m": 20, "matched": 10})
            self.assertEqual(result["pixels_per_meter"], 100)
            self.assertFalse(changed)
        apply.assert_not_awaited()

    async def test_calibration_rejects_other_owner_unknown_page_and_concurrent_edit(self):
        db = NS(plans_takeoff=Collection(plan()))
        fn = functions("routes/plans_common.py", {"_apply_new_calibration"}, db=db)["_apply_new_calibration"]
        for user_id, page_index, reject, status in [("other", 0, False, 404), (USER["user_id"], 9, False, 404), (USER["user_id"], 0, True, 409)]:
            db.plans_takeoff.reject_write = reject
            with self.subTest(status=status), self.assertRaises(HTTPException) as err:
                await fn("p", user_id, page_index, {"pixels_per_meter": 50})
            self.assertEqual(err.exception.status_code, status)
        self.assertEqual(db.plans_takeoff.doc, plan())

    async def test_51_measurements_preserve_the_first(self):
        db = NS(plans_takeoff=Collection(plan()))
        fn = functions("routes/plans_analysis.py", {"measure"}, db=db)["measure"]
        first = None
        for i in range(51):
            r = await fn("p", NS(page_index=0, kind="distance", points=[[0, 0], [100, 0]], label=str(i), color=None, poste=None), USER)
            first = first or r["measurement_id"]
        saved = db.plans_takeoff.doc["measurements"]
        self.assertEqual(len(saved), 51)
        self.assertEqual(saved[0]["measurement_id"], first)

    async def test_merge_rejects_duplicates_and_mixed_pages(self):
        p = plan()
        p["measurements"] = [{"measurement_id": "a", "page_index": 0, "kind": "distance"},
                             {"measurement_id": "b", "page_index": 1, "kind": "distance"}]
        fn = functions("routes/plans_analysis.py", {"merge_measurements"}, db=NS(plans_takeoff=Collection(p)))["merge_measurements"]
        for ids in [["a", "a"], ["a", "b"]]:
            with self.subTest(ids=ids), self.assertRaises(HTTPException) as err:
                await fn("p", NS(measurement_ids=ids), USER)
            self.assertEqual(err.exception.status_code, 422)


class Security(unittest.IsolatedAsyncioTestCase):
    def auth(self, names, consumed=1):
        now = datetime.now(timezone.utc)
        users = NS(find_one=AsyncMock(return_value={**USER, "password_hash": "old"}), update_one=AsyncMock())
        tokens = NS(find_one=AsyncMock(return_value={"_id": "reset", **USER, "expires_at": now + timedelta(hours=1)}),
                    update_one=AsyncMock(return_value=NS(modified_count=consumed)), update_many=AsyncMock())
        db = NS(users=users, password_reset_tokens=tokens, user_sessions=NS(delete_many=AsyncMock()), two_fa_codes=NS(delete_many=AsyncMock()))
        return functions("routes/auth.py", names, db=db, verify_password=lambda *a: True, hash_password=lambda s: "new-hash"), db

    async def test_password_change_revokes_jwt_and_pending_2fa(self):
        ns, db = self.auth({"change_password"})
        await ns["change_password"](NS(current_password="old", new_password="new password"), NS(cookies={"session_token": "keep"}, headers={}), USER)
        self.assertEqual(db.users.update_one.call_args.args[1]["$inc"], {"token_version": 1})
        self.assertEqual(db.user_sessions.delete_many.call_args.args[0]["session_token"], {"$ne": "keep"})
        db.two_fa_codes.delete_many.assert_awaited_once()

    async def test_reset_consumes_token_and_revokes_all_authentication(self):
        ns, db = self.auth({"reset_password"})
        await ns["reset_password"](NS(token="test", new_password="new password"), None, None)
        self.assertEqual(db.users.update_one.call_args.args[1]["$inc"], {"token_version": 1})
        self.assertIs(db.password_reset_tokens.update_one.call_args.args[0]["used"], False)
        db.user_sessions.delete_many.assert_awaited_once_with(USER)
        db.two_fa_codes.delete_many.assert_awaited_once_with(USER)

    async def test_reset_lost_race_cannot_change_password(self):
        ns, db = self.auth({"reset_password"}, consumed=0)
        with self.assertRaises(HTTPException):
            await ns["reset_password"](NS(token="test", new_password="new password"), None, None)
        db.users.update_one.assert_not_awaited()

    async def test_invalid_session_expiry_and_disabled_user(self):
        db = NS(user_sessions=NS(find_one=AsyncMock()), users=NS(find_one=AsyncMock()))
        ns = functions("core/security.py", {"_user_from_session", "current_user"}, db=db)
        for expiry in [None, "invalid", datetime.now(timezone.utc) - timedelta(seconds=1)]:
            db.user_sessions.find_one.return_value = {**USER, "expires_at": expiry}
            self.assertIsNone(await ns["_user_from_session"]("test"))
        db.users.find_one.assert_not_awaited()
        with self.assertRaises(HTTPException) as err:
            await ns["current_user"]({**USER, "active": False})
        self.assertEqual(err.exception.status_code, 403)

    async def test_unpaid_checkout_never_grants_any_credit(self):
        updates = AsyncMock()
        ns = functions("engines/monetization.py", {"_mark_paid"}, db=NS(payment_transactions=NS(update_one=updates)))
        for status in [None, "unpaid", "pending"]:
            await ns["_mark_paid"]("s", {"status": "complete", "payment_status": status})
        updates.assert_not_awaited()

    async def test_google_admin_must_complete_2fa_before_session(self):
        user = {**USER, "email": "audit@example.invalid", "role": "admin", "two_fa_enabled": True}
        client = NS(get=AsyncMock(return_value=NS(status_code=200, json=lambda: {"email": user["email"]})))
        class ClientContext:
            async def __aenter__(self): return client
            async def __aexit__(self, *args): return False
        db = NS(users=NS(find_one=AsyncMock(return_value=user), update_one=AsyncMock()))
        ns = functions("routes/auth.py", {"google_session"}, db=db,
                       httpx=NS(AsyncClient=lambda **kw: ClientContext()), _set_session=AsyncMock(),
                       _register_device=AsyncMock(), _start_2fa=AsyncMock(return_value={"two_fa_required": True}))
        result = await ns["google_session"](NS(headers={"X-Session-ID": "test"}), None)
        self.assertTrue(result["two_fa_required"])
        ns["_set_session"].assert_not_awaited()

    async def test_used_2fa_challenge_cannot_create_session(self):
        rec = {"_id": "code", **USER, "expires_at": datetime.now(timezone.utc) + timedelta(minutes=1),
               "attempts": 0, "code_hash": hashlib.sha256(b"123456").hexdigest()}
        ns = functions("routes/auth.py", {"verify_2fa"},
                       db=NS(two_fa_codes=NS(find_one=AsyncMock(return_value=rec), delete_one=AsyncMock(return_value=NS(deleted_count=0)))),
                       _set_session=AsyncMock())
        with self.assertRaises(HTTPException) as err:
            await ns["verify_2fa"](NS(pending_token="test", code="123456"), None, None)
        self.assertEqual(err.exception.status_code, 401)
        ns["_set_session"].assert_not_awaited()

    async def test_paid_and_free_trial_checkout_reach_idempotency_guard(self):
        updates = AsyncMock(return_value=NS(modified_count=0))
        ns = functions("engines/monetization.py", {"_mark_paid"}, db=NS(payment_transactions=NS(update_one=updates)))
        for status in ["paid", "no_payment_required"]:
            await ns["_mark_paid"]("s", {"payment_status": status})
        self.assertEqual(updates.await_count, 2)

    async def test_private_redirect_is_rejected_before_request(self):
        requested = []
        def handler(request):
            requested.append(str(request.url))
            return httpx.Response(302, headers={"location": "http://127.0.0.1/private"})
        real_client = httpx.AsyncClient
        client_factory = lambda **kw: real_client(transport=httpx.MockTransport(handler), **kw)
        ns = functions("engines/assistant_sources.py", {"_download"},
                       httpx=NS(AsyncClient=client_factory), TIMEOUT=1, MAX_BYTES=100,
                       urljoin=urljoin, check_url=lambda u: "private" if "127.0.0.1" in u else None)
        with self.assertRaises(PermissionError):
            await ns["_download"]("https://public.example/doc")
        self.assertEqual(requested, ["https://public.example/doc"])

    def test_malformed_url_and_private_ip_are_rejected(self):
        ns = functions("engines/assistant_sources.py", {"check_url", "_is_private"},
                       urlparse=urlparse, socket=NS(getaddrinfo=Mock(return_value=[(0, 0, 0, "", ("100.64.0.1", 80))])), ipaddress=ipaddress)
        for url in ["http://example.com:invalid/", "http://user:pass@example.com", "http://example.com"]:
            self.assertIsNotNone(ns["check_url"](url))


if __name__ == "__main__":
    unittest.main()
