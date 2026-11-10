"""Regras determinísticas: respostas do diagnóstico → necessidades → capacidades → demonstração.

Nenhuma IA intervém na elegibilidade. A mesma lógica existe em JavaScript
(`frontend/src/connect/engine.js`) para o modo offline; `cases.json` garante a paridade.
"""
from __future__ import annotations

from . import catalog as C

CASE_PRIORITY = ("A", "B", "C", "D", "E")


def primary_case(pains: list[str]) -> str:
    pmap = C.pains_by_id()
    for pid in pains:
        case = (pmap.get(pid) or {}).get("case")
        if case:
            return case
    return "GENERAL"


def cases_for(pains: list[str]) -> list[str]:
    pmap = C.pains_by_id()
    out: list[str] = []
    for pid in pains:
        case = (pmap.get(pid) or {}).get("case")
        if case and case not in out:
            out.append(case)
    return out


def recommend_client(answers: dict) -> dict:
    cat = C.load()
    caps = C.caps_by_id()
    pmap = C.pains_by_id()
    act = C.activities_by_id().get(answers.get("activity") or "", {"group": "other"})
    group = act.get("group", "other")
    track = act.get("track")
    pains = [p for p in (answers.get("pains") or []) if p in pmap][:3]
    deep = answers.get("deep") or {}

    # 1. Capacidades por ordem das dores, sem duplicados; só estados públicos.
    ordered: list[str] = []
    reasons: dict[str, list[str]] = {}
    for pid in pains:
        for cid in pmap[pid]["capabilities"]:
            if caps[cid]["status"] not in C.PUBLIC_STATUSES:
                continue
            reasons.setdefault(cid, []).append(pid)
            if cid not in ordered:
                ordered.append(cid)
    if not ordered:  # «outro problema» ou sem dores → visão geral honesta
        for cid in ("cap_takeoff", "cap_quote", "cap_margin"):
            ordered.append(cid)
            reasons.setdefault(cid, [])
    if group == "private":  # particulares: medições e quantidades primeiro
        ordered.sort(key=lambda c: 0 if c in ("cap_quantities", "cap_takeoff") else 1)
    capabilities = [{"id": cid, "status": caps[cid]["status"], "pains": reasons[cid]} for cid in ordered[:5]]

    # 2. Demonstração principal e alternativas.
    case = primary_case(pains)
    demo = None
    if track and track in cat["track_demo"] and case in ("A", "B", "GENERAL"):
        demo = cat["track_demo"][track]
    if demo is None and case in cat["case_demo"]:
        demo = cat["case_demo"][case]
    if demo is None:
        demo = cat["track_demo"].get(group, "demo_quote")
    alternatives: list[str] = []
    for c in cases_for(pains):
        d = cat["case_demo"][c]
        if d != demo and d not in alternatives:
            alternatives.append(d)
    for d in ("demo_takeoff", "demo_quote", "demo_margin"):
        if len(alternatives) >= 3:
            break
        if d != demo and d not in alternatives:
            alternatives.append(d)

    # 3. Processo atual (adaptado à ferramenta indicada) vs. com ConstruPilot.
    tool = deep.get("tools") if isinstance(deep.get("tools"), str) else None
    current_key = tool if tool in cat["process"]["current"] else None
    with_key = {"D": "with_tracking", "E": "with_billing"}.get(case, "with")

    # 4. Valores de partida da calculadora (apenas dados do cliente; nada inventado).
    rng = {r["id"]: r for r in cat["ranges"]["quotes_per_month"]}
    qpm = (answers.get("volume") or {}).get("quotes_per_month")
    hours = None
    for q in cat["deep_questions"]["B"]:
        if q["id"] == "b_time":
            for o in q["options"]:
                if o["id"] == deep.get("b_time"):
                    hours = o["hours"]
    value_defaults = {
        "quotes_per_month": rng[qpm]["mid"] if qpm in rng else None,
        "hours_per_quote": hours,
        "hourly_cost": None,
    }

    return {
        "profile": "client",
        "activity": answers.get("activity"),
        "group": group,
        "track": track,
        "pains": pains,
        "primary_case": case,
        "capabilities": capabilities,
        "demo": demo,
        "alternative_demos": alternatives[:3],
        "process": {"current": current_key, "with": with_key},
        "value_defaults": value_defaults,
        "needs_human_review": "p_other" in pains or bool((answers.get("other_text") or "").strip()),
        "catalog_version": cat["version"],
    }


def recommend_investor(answers: dict) -> dict:
    return {
        "profile": "investor",
        "demo": "demo_quote",
        "alternative_demos": ["demo_takeoff", "demo_margin"],
        "sections": ["overview", "problem", "solution", "segments", "model", "traction", "risks", "meeting"],
        "catalog_version": C.load()["version"],
    }


def recommend_partner(answers: dict) -> dict:
    cat = C.load()
    caps = C.caps_by_id()
    ptype = answers.get("partner_type")
    cap = cat["partner"]["use_cases"].get(ptype, "cap_quote")
    demo = next((d["id"] for d in cat["demos"] if cap in d["capabilities"] and d["kind"] == "engine"), "demo_quote")
    return {
        "profile": "partner",
        "use_case": cap,
        "use_case_status": caps[cap]["status"],
        "demo": demo,
        "alternative_demos": [d for d in ("demo_quote", "demo_takeoff", "demo_margin") if d != demo][:2],
        "catalog_version": cat["version"],
    }


def recommend(profile: str, answers: dict) -> dict:
    if profile == "client":
        return recommend_client(answers)
    if profile == "investor":
        return recommend_investor(answers)
    if profile == "partner":
        return recommend_partner(answers)
    raise ValueError("perfil inválido")
