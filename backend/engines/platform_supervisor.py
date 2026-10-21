"""Tenant-scoped checks and reversible repairs of derived values.

No LLM-produced number is persisted here. Inputs (geometry, scale, prices, tax
rates, descriptions) remain authoritative. A check is not a structural approval.
"""
from __future__ import annotations

import copy
import hashlib
import json
import math
import asyncio
from datetime import datetime, timezone

from fastapi import HTTPException

from core.permissions import ROLE_PERMISSIONS, permissions_for
from engines.plan_quantities import recalibrate_measurement, recompute_room

MAX_RESOURCES = 200
MAX_CHANGES = 2000


def now():
    return datetime.now(timezone.utc).isoformat()


def authorize(user):
    if not user or not user.get("user_id"):
        raise HTTPException(401, "Conta indisponível")
    if user.get("active") is False or user.get("company_active") is False:
        raise HTTPException(403, "Conta desativada")
    if user.get("organization_id") and user.get("org_role") not in ROLE_PERMISSIONS:
        raise HTTPException(403, "Função na empresa não reconhecida")


def can_check_quotes(user):
    return (user.get("account_type") in ("pro", "pro_business") or user.get("role") == "admin") and permissions_for(user)["devis"]


def number(value, minimum=0, maximum=1e12):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("valor numérico ausente ou inválido")
    if not math.isfinite(value) or not minimum <= value <= maximum:
        raise ValueError("valor fora dos limites")
    return value


def issue(code, message, path="", *, blocking=True):
    return {"code": code, "message": message, "path": path, "blocking": blocking}


def _points(points, polygon=False):
    if not isinstance(points, list) or len(points) < (3 if polygon else 2) or len(points) > 100_000:
        raise ValueError("geometria ausente ou demasiado volumosa")
    for point in points:
        if not isinstance(point, (list, tuple)) or len(point) != 2:
            raise ValueError("ponto inválido")
        for coordinate in point:
            number(coordinate, -1e9, 1e9)
    if polygon:
        from shapely.geometry import Polygon
        shape = Polygon(points)
        if not shape.is_valid or shape.area <= 0:
            raise ValueError("polígono cruzado ou de área nula")


def _openings(row):
    for opening in row.get("openings") or []:
        number(opening.get("width_m"), 0, 1e6)
        count = opening.get("count", 1)
        number(count, 1, 10000)
        if int(count) != count:
            raise ValueError("número de vãos não inteiro")
        if opening.get("height_m") is not None:
            number(opening["height_m"], 0, 1e4)
        if opening.get("points"):
            _points(opening["points"])


def _changes(before, after, prefix=""):
    """Scalar patches only; geometry and user inputs are never removed."""
    changes = []
    if isinstance(after, dict) and isinstance(before, dict):
        for key, value in after.items():
            if key in ("points", "segments", "polygons", "calibrations", "wall_height_m", "ceiling_height_m"):
                continue
            path = f"{prefix}.{key}" if prefix else key
            if key not in before:
                changes.append({"path": path, "before_exists": False, "before": None, "after": value})
            else:
                changes.extend(_changes(before[key], value, path))
    elif isinstance(after, list) and isinstance(before, list) and len(after) == len(before):
        for index, (old, new) in enumerate(zip(before, after)):
            changes.extend(_changes(old, new, f"{prefix}.{index}"))
    elif isinstance(before, float) and isinstance(after, float) and math.isnan(before) and math.isnan(after):
        pass  # An unchanged corrupt source is a finding, never a repair patch.
    elif before != after:
        changes.append({"path": prefix, "before_exists": True, "before": before, "after": after})
    return changes


def audit_plan(plan):
    candidate = copy.deepcopy(plan)
    issues, checked = [], 0
    calibrations = plan.get("calibrations") or {}
    for collection in ("measurements", "rooms"):
        for index, original in enumerate(plan.get(collection) or []):
            path = f"{collection}.{index}"
            row = candidate[collection][index]
            if not isinstance(row, dict):
                issues.append(issue("invalid_geometry", "Elemento de planta inválido", path))
                continue
            kind = row.get("kind")
            if collection == "measurements" and kind not in ("distance", "polyline", "cumulative", "polygon", "cumulative_area"):
                issues.append(issue("manual_measure", "Medição manual ou tipo não recalculável: conservado", path, blocking=False))
                continue
            try:
                page = row.get("page_index", 0)
                if type(page) is not int or page < 0:
                    raise ValueError("página inválida")
                ppm = number((calibrations.get(str(page)) or {}).get("pixels_per_meter"), 1e-6, 1e12)
            except (ValueError, TypeError, AttributeError):
                issues.append(issue("missing_scale", "Escala fiável em falta nesta página: recálculo bloqueado", path))
                continue
            try:
                _openings(row)
                if collection == "rooms":
                    _points(row.get("points"), polygon=True)
                    if any(o.get("height_m") is None for o in row.get("openings") or []):
                        raise ValueError("altura do vão em falta")
                    for deduction in row.get("deductions") or []:
                        if deduction.get("points"):
                            _points(deduction["points"], polygon=True)
                        else:
                            number(deduction.get("area_m2"), 0)
                    height_known = row.get("ceiling_height_m") is not None
                    if height_known:
                        number(row["ceiling_height_m"], 0.01, 1000)
                    if row.get("surface_written_m2") is not None:
                        number(row["surface_written_m2"], 0)
                    recompute_room(row, ppm)
                    if row.get("deductions_area_m2", 0) > row.get("surface_gross_m2", 0):
                        raise ValueError("deduções superiores à área")
                    if row.get("openings_area_m2", 0) > row.get("wall_area_gross_m2", 0):
                        raise ValueError("vãos superiores à área das paredes")
                    if not height_known:
                        for key in ("wall_area_gross_m2", "wall_area_net_m2", "volume_m3"):
                            if key in original:
                                row[key] = original[key]
                            else:
                                row.pop(key, None)
                        issues.append(issue("missing_height", "Altura não indicada: áreas das paredes e volume não validados", path))
                else:
                    groups = row.get("segments") if kind == "cumulative" else row.get("polygons") if kind == "cumulative_area" else [row.get("points")]
                    if not groups:
                        raise ValueError("geometria ausente")
                    for points in groups:
                        _points(points, polygon=kind in ("polygon", "cumulative_area"))
                    if row.get("wall_height_m") is not None:
                        number(row["wall_height_m"], 0, 1000)
                    recalibrate_measurement(row, ppm)
                    if row.get("gross_m") is not None:
                        deducted = sum(o["width_m"] * o.get("count", 1) for o in row.get("openings") or [])
                        if deducted > row["gross_m"] + .001:
                            raise ValueError("larguras dos vãos superiores ao linear")
                        if row.get("wall_height_m") and any(o.get("height_m") is None for o in row.get("openings") or []):
                            raise ValueError("altura do vão em falta para a parede líquida")
                        if (row.get("openings_area_m2") or 0) > (row.get("wall_area_gross_m2") or 0):
                            raise ValueError("vãos superiores à área da parede")
                checked += 1
            except (ValueError, TypeError, KeyError, AttributeError, OverflowError, ZeroDivisionError):
                candidate[collection][index] = copy.deepcopy(original)
                issues.append(issue("invalid_geometry", "Geometria, vãos ou dimensões incoerentes: correção manual necessária", path))
    if not (plan.get("rooms") or plan.get("measurements")):
        issues.append(issue("empty_plan", "Nenhuma medição guardada: ler e medir a planta antes de a validar"))
    if plan.get("studies") or plan.get("structural_metre"):
        issues.append(issue("analysis_scope", "As interpretações IA e o dimensionamento estrutural exigem o seu controlo especializado", blocking=False))
    before = {key: plan.get(key, []) for key in ("measurements", "rooms")}
    after = {key: candidate.get(key, []) for key in before}
    return {"changes": _changes(before, after), "issues": issues, "checked_elements": checked}


def audit_quote(doc):
    from routes.documents import _compute_totals
    issues = []
    for index, line in enumerate(doc.get("lines") or []):
        if line.get("kind") in ("section", "subsection", "text", "pagebreak"):
            continue
        try:
            number(line.get("qty"), 0, 1e9)
            number(line.get("unit_price_ht"), 0, 1e9)
            number(line.get("discount_pct", 0), 0, 100)
            number(line.get("cost_price_ht", 0), 0, 1e9)
            if line.get("vat_rate") is not None:
                number(line["vat_rate"], 0, 100)
        except ValueError:
            issues.append(issue("invalid_number", "Quantidade, preço, desconto ou IVA inválido", f"lines.{index}"))
        if line.get("price_missing") or line.get("quantity_missing") or line.get("vat_rate") is None:
            issues.append(issue("missing_input", "Quantidade, preço ou IVA a indicar", f"lines.{index}"))
        if line.get("price_estimated") or line.get("vat_assumed"):
            issues.append(issue("assumed_input", "Preço estimado ou IVA suposto a confirmar", f"lines.{index}"))
    try:
        number(doc.get("deposit_pct", 0), 0, 100)
    except ValueError:
        issues.append(issue("invalid_number", "Adiantamento inválido", "deposit_pct"))
    if any(i["code"] == "invalid_number" for i in issues):
        return {"changes": [], "issues": issues, "checked_elements": 0}
    totals = _compute_totals(doc.get("lines") or [], doc.get("deposit_pct", 0))
    changes = _changes({"totals": doc.get("totals") or {}}, {"totals": totals})
    if not doc.get("lines"):
        issues.append(issue("empty_quote", "Orçamento sem linhas a orçamentar"))
    if doc.get("status") != "draft" or doc.get("signed"):
        if changes:
            issues.append(issue("locked_document", "Diferença num documento emitido: alteração automática proibida"))
        changes = []
    return {"changes": changes, "issues": issues, "checked_elements": len(doc.get("lines") or [])}


def source_filter(doc, kind):
    fields = ("calibrations", "measurements", "rooms", "updated_at") if kind == "plan" else ("lines", "totals", "deposit_pct", "updated_at", "status", "signed")
    return {field: doc[field] if field in doc else {"$exists": False} for field in fields}


def resource_fingerprint(doc, kind):
    fields = ("calibrations", "measurements", "rooms") if kind == "plan" else ("lines", "totals", "deposit_pct", "status", "signed")
    data = {k: doc.get(k) for k in (*fields, "chantier_id", "trashed_at")}
    return hashlib.sha256(json.dumps(data, sort_keys=True, ensure_ascii=False, default=str, separators=(",", ":")).encode()).hexdigest()


async def run_supervisor(db, user, run, *, repair=False, progress=None):
    authorize(user)
    uid = user["user_id"]
    cid = run.get("chantier_id")
    if cid and not await db.chantiers.find_one({"user_id": uid, "chantier_id": cid}):
        raise HTTPException(404, "Processo inacessível para esta conta")
    report = {"kind": "supervision", "mode": "repair" if repair else "audit", "resources": [],
              "checked": 0, "corrected": 0, "corrections": 0, "needs_review": 0,
              "coverage_complete": False, "source_measurements_verified": False}
    scopes = [("plan", db.plans_takeoff, "plan_id", run.get("plan_ids") or [])]
    quote_ids = run.get("quote_ids") or []
    if quote_ids and not can_check_quotes(user):
        raise HTTPException(403, "A sua função não permite controlar os orçamentos")
    if can_check_quotes(user):
        scopes.append(("quote", db.pro_documents, "doc_id", quote_ids))
    requested = bool(run.get("plan_ids") or quote_ids)
    async def active_run():
        if run.get("worker"):
            current = await db.agent_runs.find_one({"run_id": run["run_id"], "user_id": uid, "worker": run["worker"],
                                                    "status": "running", "cancel_requested": {"$ne": True}}, {"_id": 1})
            if not current:
                raise asyncio.CancelledError()
    # Resolve the complete requested selection before the first mutation.
    selections = []
    for kind, collection, id_key, ids in scopes:
        if requested and not ids:
            continue
        query = {"user_id": uid, "trashed_at": None}
        if cid:
            query["chantier_id"] = cid
        if kind == "quote":
            query["doc_type"] = "quote"
        if ids:
            query[id_key] = {"$in": ids}
        fields = ("filename", "calibrations", "rooms", "measurements", "updated_at") if kind == "plan" else ("title", "doc_type", "lines", "totals", "deposit_pct", "status", "signed", "updated_at")
        projection = {"_id": 0, "user_id": 1, "chantier_id": 1, "trashed_at": 1, id_key: 1, **{key: 1 for key in fields}}
        # Never load raster pages, original file bytes or attachment bodies for an arithmetic audit.
        rows = await collection.find(query, projection).sort(id_key, 1).to_list(MAX_RESOURCES + 1)
        if ids and {row[id_key] for row in rows} != set(ids):
            raise HTTPException(404, "Um recurso está ausente ou inacessível para esta conta")
        if len(rows) > MAX_RESOURCES:
            raise HTTPException(422, "Mais de 200 recursos: selecione um processo ou um lote de plantas/orçamentos")
        selections.append((kind, collection, id_key, rows, projection))
    for kind, collection, id_key, rows, projection in selections:
        for doc in rows:
            await active_run()
            fresh_user = await db.users.find_one({"user_id": uid}, {"_id": 0})
            authorize(fresh_user)
            if fresh_user.get("organization_id") != user.get("organization_id"):
                raise HTTPException(403, "A associação da conta mudou")
            if kind == "quote" and not can_check_quotes(fresh_user):
                raise HTTPException(403, "Permissões sobre os orçamentos retiradas")
            check = await asyncio.to_thread(audit_plan if kind == "plan" else audit_quote, doc)
            changes = check.pop("changes")
            entry = {"kind": kind, "id": doc[id_key], "label": doc.get("filename") or doc.get("title") or doc[id_key],
                     "issues": check["issues"], "checked_elements": check["checked_elements"],
                     "checked_at": now(), "source_fingerprint": resource_fingerprint(doc, kind), "chantier_id": doc.get("chantier_id"),
                     "corrections": len(changes), "applied": False, "status": "needs_review" if check["issues"] or changes else "checked"}
            if len(changes) > MAX_CHANGES:
                entry["issues"].append(issue("large_change", "Mais de 2 000 valores a corrigir: divida a correção"))
            elif repair and changes:
                await active_run()
                guard = {id_key: doc[id_key], "user_id": uid, "trashed_at": None, **source_filter(doc, kind)}
                if cid:
                    guard["chantier_id"] = cid
                if kind == "quote":
                    guard.update(doc_type="quote", status="draft", signed={"$ne": True})
                timestamp = now()
                history = {"run_id": run["run_id"], "at": timestamp, "changes": changes}
                fields = {change["path"]: change["after"] for change in changes}
                fields.update(updated_at=timestamp, supervisor_review_required=bool(entry["issues"]))
                if kind == "quote":
                    fields.update(facturx_pdf_b64=None, facturx_validation=None, facturx_hash=None)
                result = await collection.update_one(guard, {"$set": fields, "$push": {"supervisor_history": {"$each": [history], "$slice": -20}}})
                if result.matched_count:
                    entry["applied"] = True
                    report["corrected"] += 1
                    report["corrections"] += len(changes)
                    saved = await collection.find_one({id_key: doc[id_key], "user_id": uid}, projection)
                    verified = await asyncio.to_thread(audit_plan if kind == "plan" else audit_quote, saved) if saved else None
                    if not verified or verified["changes"] or saved.get("updated_at") != timestamp:
                        entry["issues"].append(issue("changed_after_repair", "O documento mudou após a correção; novo controlo necessário"))
                    if verified:
                        entry["source_fingerprint"] = resource_fingerprint(saved, kind)
                        entry["issues"].extend(i for i in verified["issues"] if i not in entry["issues"])
                    entry["status"] = "needs_review" if entry["issues"] else "corrected"
                else:
                    entry["issues"].append(issue("conflict", "Alteração concorrente: nada foi substituído, volte a lançar o controlo"))
            report["checked"] += 1
            report["needs_review"] += entry["status"] == "needs_review"
            # Bounded run response; complete per-resource results remain owner-scoped.
            await db.agent_checks.update_one({"run_id": run["run_id"], "user_id": uid, "kind": kind, "resource_id": doc[id_key]}, {"$set": entry}, upsert=True)
            if len(report["resources"]) < 40:
                report["resources"].append(entry)
            report["details_truncated"] = report["checked"] > len(report["resources"])
            if progress:
                await progress(report)
    report["coverage_complete"] = True
    report["note"] = "Controlos aritméticos e geométricos sobre dados guardados; leitura exaustiva, preços de mercado e validação estrutural não certificados."
    return report


async def undo_correction(db, user, kind, resource_id, run_id):
    authorize(user)
    if kind not in ("plan", "quote"):
        raise HTTPException(422, "Tipo de recurso desconhecido")
    if kind == "quote" and not can_check_quotes(user):
        raise HTTPException(403, "Acesso aos orçamentos recusado")
    collection = db.plans_takeoff if kind == "plan" else db.pro_documents
    id_key = "plan_id" if kind == "plan" else "doc_id"
    query = {id_key: resource_id, "user_id": user["user_id"]}
    doc = await collection.find_one(query, {"_id": 0})
    history = (doc or {}).get("supervisor_history") or []
    if not doc or not history or history[-1].get("run_id") != run_id or history[-1].get("undone_at"):
        raise HTTPException(409, "Só a última correção não anulada pode ser restaurada")
    if doc.get("updated_at") != history[-1].get("at"):
        raise HTTPException(409, "O documento foi alterado desde a correção")
    if kind == "quote" and (doc.get("status") != "draft" or doc.get("signed")):
        raise HTTPException(409, "Documento emitido: restauro proibido")
    changes = history[-1]["changes"]
    fields, removed = {}, {}
    for change in changes:
        value = doc
        try:
            for part in change["path"].split("."):
                value = value[int(part)] if isinstance(value, list) else value[part]
        except (KeyError, IndexError, ValueError, TypeError):
            raise HTTPException(409, "O documento mudou desde a correção") from None
        if value != change["after"]:
            raise HTTPException(409, "O documento mudou desde a correção")
        if change["before_exists"]:
            fields[change["path"]] = change["before"]
        else:
            removed[change["path"]] = ""
    stamp = now()
    history[-1]["undone_at"] = stamp
    fields.update(supervisor_history=history, updated_at=stamp, supervisor_review_required=True)
    if kind == "quote":
        fields.update(facturx_pdf_b64=None, facturx_validation=None, facturx_hash=None)
    guard = {**query, **source_filter(doc, kind), "supervisor_history": doc["supervisor_history"]}
    # history above was mutated locally; compare against its unmodified stored form.
    guard["supervisor_history"] = copy.deepcopy(doc["supervisor_history"])
    guard["supervisor_history"][-1].pop("undone_at", None)
    result = await collection.update_one(guard, {"$set": fields, **({"$unset": removed} if removed else {})})
    if not result.matched_count:
        raise HTTPException(409, "Alteração concorrente: restauro anulado")
    return {"ok": True, "restored": True}
