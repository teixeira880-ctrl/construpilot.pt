"""Gera frontend/src/fixtures/workProfileCatalog.json (usado só no modo demonstração offline).
Executar após alterar engines/work_profile.py:  python scripts/export_work_profile_catalog.py"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from engines import work_profile as W  # noqa: E402


def export() -> dict:
    tasks = {k: {**v, "feature": list(v["feature"]) if isinstance(v["feature"], tuple) else v["feature"]} for k, v in W.TASKS.items()}
    return {**W.catalog(), "task_defs": tasks, "generic_tasks": W.GENERIC_TASKS, "default_profile": W.DEFAULT_PROFILE}


if __name__ == "__main__":
    out = Path(__file__).resolve().parents[2] / "frontend" / "src" / "fixtures" / "workProfileCatalog.json"
    out.write_text(json.dumps(export(), ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(out)
