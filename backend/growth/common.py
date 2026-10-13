"""Shared helpers for the ConstruPilot Growth module (isolated: collections prefixed `growth_`, routes under /api/growth)."""
import os
import uuid
from datetime import datetime, timezone

from fastapi import Depends, HTTPException

from core.db import db
from core.security import current_user

ROLES = ("admin", "editor", "reader")
_RANK = {"reader": 0, "editor": 1, "admin": 2}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


async def growth_role(user: dict) -> str | None:
    if user.get("role") == "admin":
        return "admin"
    m = await db.growth_members.find_one({"user_id": user["user_id"]}, {"_id": 0, "role": 1})
    return m["role"] if m else None


def require_growth(min_role: str = "reader"):
    async def dep(user=Depends(current_user)) -> dict:
        role = await growth_role(user)
        if role is None:
            raise HTTPException(403, "Acesso ao módulo Growth reservado à equipa de marketing")
        if _RANK[role] < _RANK[min_role]:
            raise HTTPException(403, f'Função «{min_role} » requis')
        return {**user, "growth_role": role}
    return dep


async def get_project(project_id: str) -> dict:
    p = await db.growth_projects.find_one({"project_id": project_id}, {"_id": 0})
    if not p:
        raise HTTPException(404, "Projeto Growth não encontrado")
    return p


async def record_cost(project_id: str, provider: str, feature: str, usd: float, ref: str = "", estimated: bool = False):
    await db.growth_costs.insert_one({"cost_id": new_id("cost"), "project_id": project_id, "provider": provider, "feature": feature,
                                      "usd": round(float(usd or 0), 6), "estimated": estimated, "ref": ref, "at": now_iso(), "day": now_iso()[:10], "month": now_iso()[:7]})


async def spent(project_id: str, period: str) -> float:
    key = "day" if period == "day" else "month"
    val = now_iso()[:10] if period == "day" else now_iso()[:7]
    agg = await db.growth_costs.aggregate([{"$match": {"project_id": project_id, key: val}}, {"$group": {"_id": None, "s": {"$sum": "$usd"}}}]).to_list(1)
    return round(agg[0]["s"], 6) if agg else 0.0


async def budget_check(project: dict, upcoming_usd: float) -> tuple[bool, str]:
    """True when the upcoming spend fits under the project's daily and monthly caps (0 = no cap)."""
    b = (project.get("settings") or {}).get("budgets") or {}
    for period, cap in (("day", b.get("daily_usd") or 0), ("month", b.get("monthly_usd") or 0)):
        if cap and await spent(project["project_id"], period) + upcoming_usd > cap:
            return False, f"Teto {('journalier' if period == 'day' else 'mensuel')} de {cap} $ atteint"
    return True, ""


def env(name: str) -> str | None:
    v = os.environ.get(name)
    return v if v and v.strip() else None
