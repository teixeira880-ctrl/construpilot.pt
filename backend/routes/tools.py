from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from engines import calculators, diy

router = APIRouter(tags=["tools"])


@router.get("/calculators")
async def list_calculators() -> list:
    return [{k: v for k, v in c.items() if k != "fn"} for c in calculators.CALCULATORS.values()]


class CalcIn(BaseModel):
    params: dict


@router.post("/calculators/{key}")
async def run_calculator(key: str, body: CalcIn):
    cfg = calculators.CALCULATORS.get(key)
    if not cfg:
        raise HTTPException(status_code=404, detail="Calculateur inconnu")
    allowed = {f["name"] for f in cfg["fields"]}
    args = {}
    for f in cfg["fields"]:
        v = body.params.get(f["name"], f.get("default"))
        if v is None or v == "":
            continue
        if f["type"] == "number":
            try:
                v = float(v)
            except (TypeError, ValueError):
                continue
        if f["type"] == "boolean":
            v = bool(v)
        args[f["name"]] = v
    args = {k: v for k, v in args.items() if k in allowed}
    return cfg["fn"](**args)


@router.get("/diy/tasks")
async def diy_tasks() -> list:
    return [{"key": t["key"], "name": t["name"], "difficulty": t["difficulty"],
             "difficulty_label": diy.DIFFICULTY[t["difficulty"]]["label"],
             "difficulty_color": diy.DIFFICULTY[t["difficulty"]]["color"],
             "duration": t["duration"], "lot": t["lot"], "steps_count": len(t["steps"]),
             "calculator": t["calculator"]} for t in diy.TASKS]


@router.post("/diy/guide/{key}")
async def diy_guide(key: str, body: CalcIn):
    try:
        return diy.build_guide(key, body.params)
    except KeyError:
        raise HTTPException(status_code=404, detail="Travail inconnu")
