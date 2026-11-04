"""Lot 51 — analyse de plan en tâche de fond, validation estimation et calculateurs."""
import os
import pathlib
import sys

import pytest

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "test_l51")
os.environ.setdefault("JWT_SECRET", "test-only-not-a-secret")
ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def test_calculator_rejects_zero_dimension():
    from engines.calculator_validation import run_validated
    with pytest.raises(ValueError):
        run_validated("paint", {"length": 0, "width": 3, "height": 2.5})
    assert run_validated("paint", {"length": 4, "width": 3, "height": 2.5})["results"]


def test_estimate_validation():
    """Fonction extraite du module (sans importer les dépendances de la route)."""
    import ast
    import types
    from fastapi import HTTPException
    tree = ast.parse((ROOT / "routes" / "estimation_routes.py").read_text(encoding="utf-8"))
    fn = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "_validate_estimate_in")
    ns = {"HTTPException": HTTPException}
    exec(compile(ast.Module(body=[fn], type_ignores=[]), "estimation_routes.py", "exec"), ns)
    check = ns["_validate_estimate_in"]

    def body(**kw):
        base = {"surface": 100.0, "project_type": "renovation_complete", "finish_level": "standard", "ceiling_height_m": 2.5}
        return types.SimpleNamespace(**{**base, **kw})
    for bad in ({"surface": -5}, {"surface": 0}, {"surface": 1e9}, {"project_type": "xxx"},
                {"finish_level": "zzz"}, {"ceiling_height_m": 0.5}):
        with pytest.raises(HTTPException) as e:
            check(body(**bad))
        assert e.value.status_code == 422
    check(body())


def test_analyze_has_background_mode():
    src = (ROOT / "routes" / "plans_analysis.py").read_text(encoding="utf-8")
    assert "background: bool = Query(False)" in src and "async def _analyze_plan_now(" in src
    fe = ROOT.parent / "frontend" / "src"
    page = (fe / "pages" / "PlanTakeoff.jsx").read_text(encoding="utf-8")
    assert page.count("await runPlanAnalysis(plan.plan_id, pageIndex)") == 2
    assert "/analyze?page_index=${pageIndex}`)" not in page
    assert "export async function runPlanAnalysis" in (fe / "lib" / "cotesJobs.js").read_text(encoding="utf-8")
