"""Evaluation harness: scores plan readings against human-verified ground truth, per category. No accuracy claim without a sample.

Ground truth files live in /app/tests/fixtures/eval/*.truth.json:
{
  "document": {"revision_index": "B", "revision_date": "23/11/2021", "declared_scale": "1/50", "document_code": "COF 0100 R+1"},
  "dimensions_m": [4.0, 5.0, ...],          # explicit dimensions a person verified on the sheet (optional)
  "expected_counts": {"window": 2},         # per element type (optional)
  "non_constructive_layers": ["A-ANNO-DIMS", "HATCH"],   # layers that must never produce walls (optional)
  "rebar": {"ha_rows": 63, "ha_mass_kg": 461, "mesh_rows": 71, "mesh_mass_kg": 2476, "rows": {"2": {"total_count": 14, "unit_length_cm": 220}}},  # optional
  "notes": "who verified, when"
}
"""
import json
import os
from datetime import datetime, timezone
from pathlib import Path

from engines.plan_identity import identify_document

EVAL_DIR = Path(os.environ.get("PLAN_EVAL_DIR", Path(__file__).resolve().parents[2] / "tests/fixtures/eval"))


def score_identity(ident: dict, truth: dict) -> dict:
    fields = ["revision_index", "revision_date", "declared_scale", "document_code"]
    checked = {f: {"expected": truth.get(f), "read": ident.get(f), "ok": truth.get(f) == ident.get(f)} for f in fields if f in truth}
    return {"fields": checked, "correct": sum(1 for c in checked.values() if c["ok"]), "total": len(checked)}


def score_dimensions(read_values: list[float], truth_values: list[float], tol_m: float = 0.005) -> dict:
    """Recall of verified dimensions among native/OCR readings, duplicates and unmatched readings (false positives candidates)."""
    remaining = list(read_values)
    found = 0
    for tv in truth_values:
        match = next((rv for rv in remaining if abs(rv - tv) <= tol_m), None)
        if match is not None:
            found += 1
            remaining.remove(match)
    duplicates = len(read_values) - len({round(v, 3) for v in read_values})
    return {"expected": len(truth_values), "found": found, "recall": round(found / len(truth_values), 3) if truth_values else None,
            "unmatched_readings": len(remaining), "duplicate_readings": duplicates}


def score_counts(read_counts: dict, expected: dict) -> dict:
    rows = {k: {"expected": v, "read": read_counts.get(k, 0), "delta": read_counts.get(k, 0) - v} for k, v in expected.items()}
    return {"elements": rows, "exact": sum(1 for r in rows.values() if r["delta"] == 0), "total": len(rows)}


def score_layers(wall_layers: list[str], non_constructive: list[str]) -> dict:
    fp = [l for l in wall_layers if l in set(non_constructive)]
    return {"false_positive_layers": fp, "ok": not fp}


def score_rebar(native: dict, truth: dict, tol_kg: float = 0.5) -> dict:
    """Schedule reading vs verified totals and spot-checked rows (mark → printed values)."""
    ha, mesh, recap = native.get("ha_bars") or {}, native.get("mesh") or {}, native.get("mesh_recap") or {}
    fields = {}
    if "ha_rows" in truth:
        fields["ha_rows"] = {"expected": truth["ha_rows"], "read": ha.get("count"), "ok": ha.get("count") == truth["ha_rows"]}
    if "ha_mass_kg" in truth:
        fields["ha_mass_kg"] = {"expected": truth["ha_mass_kg"], "read": ha.get("total_mass_kg"), "ok": ha.get("total_mass_kg") is not None and abs(ha["total_mass_kg"] - truth["ha_mass_kg"]) <= tol_kg}
    if "mesh_rows" in truth:
        fields["mesh_rows"] = {"expected": truth["mesh_rows"], "read": mesh.get("count"), "ok": mesh.get("count") == truth["mesh_rows"]}
    if "mesh_mass_kg" in truth:
        read = mesh.get("rows_mass_kg")
        fields["mesh_mass_kg"] = {"expected": truth["mesh_mass_kg"], "read": read, "ok": read is not None and abs(read - truth["mesh_mass_kg"]) <= tol_kg}
    if "mass_laid_kg" in truth:
        fields["mass_laid_kg"] = {"expected": truth["mass_laid_kg"], "read": recap.get("mass_laid_kg"), "ok": recap.get("mass_laid_kg") == truth["mass_laid_kg"]}
    rows_by_mark = {str(r.get("mark")): r for r in ha.get("rows", [])}
    row_checks = {}
    for mark, expected in (truth.get("rows") or {}).items():
        r = rows_by_mark.get(str(mark))
        row_checks[mark] = {k: {"expected": v, "read": r.get(k) if r else None, "ok": bool(r) and r.get(k) == v} for k, v in expected.items()}
    marks = [str(r.get("mark")) for r in ha.get("rows", [])]
    return {"fields": fields, "rows": row_checks, "correct": sum(1 for f in fields.values() if f["ok"]) + sum(1 for rc in row_checks.values() for c in rc.values() if c["ok"]),
            "total": len(fields) + sum(len(rc) for rc in row_checks.values()), "duplicate_marks": sorted({m for m in marks if marks.count(m) > 1}),
            "arithmetic_inconsistencies": len(ha.get("inconsistencies", []))}


def evaluate_plan(plan_text: str, truth: dict, *, native_dimensions: list[float] | None = None, element_counts: dict | None = None,
                  wall_layers: list[str] | None = None, rebar: dict | None = None, words=None) -> dict:
    report = {"evaluated_at": datetime.now(timezone.utc).isoformat(), "verified_by": truth.get("notes"),
              "identity": score_identity(identify_document(plan_text, words), truth.get("document", {}))}
    if truth.get("rebar") and rebar is not None:
        report["rebar"] = score_rebar(rebar, truth["rebar"])
    if truth.get("dimensions_m") is not None and native_dimensions is not None:
        report["dimensions"] = score_dimensions(native_dimensions, truth["dimensions_m"])
    if truth.get("expected_counts") and element_counts is not None:
        report["counts"] = score_counts(element_counts, truth["expected_counts"])
    if truth.get("non_constructive_layers") and wall_layers is not None:
        report["layers"] = score_layers(wall_layers, truth["non_constructive_layers"])
    return report


def load_truths() -> dict[str, dict]:
    return {p.name.replace(".truth.json", ""): json.loads(p.read_text()) for p in EVAL_DIR.glob("*.truth.json")}


def summary(reports: dict[str, dict]) -> dict:
    ident_ok = sum(r["identity"]["correct"] for r in reports.values())
    ident_total = sum(r["identity"]["total"] for r in reports.values())
    dims = [r["dimensions"] for r in reports.values() if "dimensions" in r]
    recalls = [d["recall"] for d in dims if d["recall"] is not None]
    rebar = [r["rebar"] for r in reports.values() if "rebar" in r]
    return {"plans": len(reports), "identity_fields_correct": f"{ident_ok}/{ident_total}",
            "rebar_fields_correct": f"{sum(r['correct'] for r in rebar)}/{sum(r['total'] for r in rebar)}" if rebar else None,
            "dimension_recall_mean": round(sum(recalls) / len(recalls), 3) if recalls else None,
            "duplicate_readings": sum(d["duplicate_readings"] for d in dims),
            "note": "Amostra = plantas autorizadas verificadas por uma pessoa competente; nenhuma taxa global é anunciada para além desta amostra."}


def score_quantities(readings: list[dict], truth: dict) -> dict:
    """Quantity-level agreement. Missing, duplicate and incompatible outputs fail closed.

    truth: verified, exhaustive, quantities[{quantity_id, page_index, unit, value,
    relative_tolerance (default .02), absolute_tolerance (default 0)}].
    Readings use the same keys, or quantity_net from the native engine export.
    IDs/pages must be mapped by an independent reviewer, never by the prediction.
    """
    import math
    units = {"m²": "m2", "m³": "m3", "ml": "m", "un": "u", "unité": "u"}
    def numeric(v):
        return not isinstance(v, bool) and isinstance(v, (float, int)) and math.isfinite(v)
    def key(row):
        identifier, page = row.get("quantity_id"), row.get("page_index")
        if not isinstance(identifier, str) or not identifier or isinstance(page, bool) or not isinstance(page, int) or page < 0:
            raise ValueError("Cada quantidade exige um quantity_id e um page_index (base 0)")
        return (identifier, page)
    if truth.get("verified") is not True:
        raise ValueError("A referência deve ser verificada de forma independente antes da avaliação")
    expected = truth.get("quantities")
    if not isinstance(expected, list) or not expected:
        raise ValueError("A referência deve conter quantidades verificadas")
    if len({key(row) for row in expected}) != len(expected):
        raise ValueError("A referência contém identificadores duplicados")
    grouped = {}
    for row in readings:
        grouped.setdefault(key(row), []).append(row)
    results = []
    for row in expected:
        k = key(row)
        value = row.get("value")
        unit = units.get(row.get("unit"), row.get("unit"))
        rel, absolute = row.get("relative_tolerance", 0 if unit == "u" else .02), row.get("absolute_tolerance", 0)
        if not unit or not numeric(value) or value < 0 or not numeric(rel) or not 0 <= rel <= 1 or not numeric(absolute) or absolute < 0:
            raise ValueError("Valor, unidade ou tolerância de referência inválidos")
        candidates = grouped.get(k, [])
        output = candidates[0] if len(candidates) == 1 else {}
        read = output.get("value", output.get("quantity_net"))
        state = "missing" if not candidates else "duplicate" if len(candidates) > 1 else "invalid" if not numeric(read) or read < 0 else "unit_mismatch" if units.get(output.get("unit"), output.get("unit")) != unit else "measured"
        difference = abs(read - value) if state == "measured" else None
        allowed = max(absolute, abs(value) * rel)
        ok = difference is not None and difference <= allowed + 1e-10
        results.append({"quantity_id": k[0], "page_index": k[1], "unit": unit, "expected": value,
                        "read": read if numeric(read) else None, "state": state, "within_tolerance": ok,
                        "absolute_error": difference, "relative_error": difference / abs(value) if difference is not None and value else None,
                        "tolerance": allowed})
    expected_keys = {key(row) for row in expected}
    extra = [row for row in readings if key(row) not in expected_keys]
    by_unit = {}
    for row in results:
        g = by_unit.setdefault(row["unit"], {"expected": 0, "measured": 0, "within_tolerance": 0})
        g["expected"] += 1; g["measured"] += row["state"] == "measured"; g["within_tolerance"] += row["within_tolerance"]
    matched = sum(r["state"] == "measured" for r in results)
    correct = sum(r["within_tolerance"] for r in results)
    return {"expected": len(results), "produced": len(readings), "measured": matched, "within_tolerance": correct,
            "coverage": matched / len(results), "agreement": correct / len(results),
            "precision": correct / len(readings) if readings and truth.get("exhaustive") is True else None,
            "extra_readings": len(extra), "by_unit": by_unit, "rows": results,
            "scope": "apenas amostra verificada", "exhaustive_reference": truth.get("exhaustive") is True}
