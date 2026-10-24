"""Pilotage IA — co-pilote déterministe du plafond d'exploitation (500 €/mois).

Lit l'état déterministe du plafond (engines.expenses.cap.status) et en dérive, SANS
aucune IA générative ni valeur inventée : une projection de fin de mois au rythme actuel,
un score de santé, et une liste de recommandations/actions priorisées (règles explicites).
Fidèle à l'ADN ConstruPilot : les chiffres viennent du moteur déterministe ; on ne fait
que les interpréter avec des seuils connus.
"""
from __future__ import annotations

import calendar
from datetime import datetime, timezone

from engines.expenses import cap

SEV_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4, "success": 5}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _projection(st: dict) -> dict | None:
    """Projection linéaire de fin de mois au rythme actuel (mois en cours uniquement)."""
    now = _now()
    if st["month"] != now.strftime("%Y-%m"):
        return None
    days_in_month = calendar.monthrange(now.year, now.month)[1]
    day = now.day
    used = float(st.get("used_eur") or 0)
    projected = round(used / day * days_in_month, 2) if day else used
    return {
        "day": day, "days_in_month": days_in_month,
        "projected_eur": projected, "cap_eur": st["cap_eur"],
        "over_cap": projected > st["cap_eur"],
        "pace_eur_per_day": round(used / day, 2) if day else 0.0,
    }


def _recommendations(st: dict, proj: dict | None) -> list[dict]:
    recs: list[dict] = []
    cap_eur = st["cap_eur"]
    state = st["state"]

    if state == "exceeded":
        recs.append({"severity": "critical", "title": "Teto de 500 € ultrapassado",
                     "detail": f"Consumido {st['used_eur']} € de {cap_eur} €.",
                     "action": "Suspenda imediatamente qualquer compromisso não obrigatório. Reconcilie as faturas e identifique a rubrica responsável."})
    elif state == "frozen":
        recs.append({"severity": "high", "title": "Limiar de congelamento de 440 € atingido",
                     "detail": f"Consumido {st['used_eur']} €. Reserva de {st['reserve_eur']} € preservada.",
                     "action": "Autorize apenas as despesas obrigatórias ou já comprometidas até ao fim do mês."})
    elif state == "warning":
        recs.append({"severity": "medium", "title": "Alerta aos 400 €",
                     "detail": f"Consumido {st['used_eur']} € ({st['percent']} %).",
                     "action": "Priorize o essencial: ponha em pausa a publicidade e a impressão este mês."})
    else:
        recs.append({"severity": "success", "title": "Orçamento sob controlo",
                     "detail": f"Consumido {st['used_eur']} € de {cap_eur} € ({st['percent']} %).",
                     "action": "Nenhuma ação necessária. Continue a reconciliar as faturas regularmente."})

    # Source de coûts périmée → bloque les nouveaux engagements.
    cs = st.get("cost_source") or {}
    if cs.get("stale"):
        recs.append({"severity": "high", "title": "Fonte de custos desatualizada",
                     "detail": ("Nunca reconciliada." if not cs.get("last_sync")
                                else f"Última reconciliação há {cs.get('days_since')} dia(s)."),
                     "action": "Lance «Reconciliar (sincronização local)» antes de qualquer novo compromisso: os totais apresentados podem estar incompletos."})

    # Projection de fin de mois.
    if proj and proj["over_cap"]:
        recs.append({"severity": "high", "title": "Projeção de fim de mês acima do teto",
                     "detail": f"Ao ritmo de {proj['pace_eur_per_day']} €/dia, projeção ≈ {proj['projected_eur']} € no dia {proj['days_in_month']} do mês.",
                     "action": "Reduza o ritmo de despesa ou congele já as rubricas não essenciais."})

    # Enveloppes dépassées ou proches.
    for key, env in (st.get("envelopes") or {}).items():
        pct = env.get("percent")
        if env.get("over"):
            recs.append({"severity": "medium", "title": f"Envelope «{env['label']}» ultrapassado",
                         "detail": f"Utilizado {env['used_eur']} € / {env['budget_eur']} € orçamentados.",
                         "action": "Realoque a partir da reserva, reduza esta rubrica ou ajuste o envelope em «Teto 500 €»."})
        elif pct is not None and pct >= 85:
            recs.append({"severity": "low", "title": f"Envelope «{env['label']}» quase atingido",
                         "detail": f"Utilizado {env['used_eur']} € / {env['budget_eur']} € ({pct} %).",
                         "action": "Acompanhe esta rubrica: resta pouca margem este mês."})

    # Engagements réservés en attente de facture.
    holds = st.get("holds") or []
    if holds:
        recs.append({"severity": "info", "title": f'{len(holds)} compromisso(s) reservado(s) a aguardar fatura',
                     "detail": f"Total reservado {st.get('held_eur')} €.",
                     "action": "Reconcilie as faturas correspondentes para libertar a reserva e tornar fiável o disponível restante."})

    recs.sort(key=lambda r: SEV_ORDER.get(r["severity"], 9))
    return recs


def _health(st: dict, proj: dict | None) -> dict:
    """Score 0–100 (plus haut = plus sain), déterministe."""
    pct = st.get("percent") or 0
    score = max(0.0, 100.0 - float(pct))
    penalties = []
    if (st.get("cost_source") or {}).get("stale"):
        score -= 15; penalties.append("fonte de custos desatualizada (-15)")
    if proj and proj["over_cap"]:
        score -= 20; penalties.append("projeção acima do teto (-20)")
    over_env = [e["label"] for e in (st.get("envelopes") or {}).values() if e.get("over")]
    if over_env:
        score -= 5 * len(over_env); penalties.append(f'{len(over_env)} envelope(s) ultrapassado(s) (-{5 * len(over_env)})')
    score = int(max(0, min(100, round(score))))
    band = "good" if score >= 70 else "watch" if score >= 40 else "critical"
    return {"score": score, "band": band, "penalties": penalties}


def _headline(st: dict, proj: dict | None) -> str:
    if st["state"] == "exceeded":
        return "Teto ultrapassado — pare os compromissos não obrigatórios."
    if st["state"] == "frozen":
        return "Orçamento congelado a 440 € — só passam as despesas obrigatórias."
    if proj and proj["over_cap"]:
        return f"Ao ritmo atual, o mês terminaria em ≈ {proj['projected_eur']} € : ralentissez."
    if st["state"] == "warning":
        return "Alerta 400 € — priorize o essencial."
    return f"Budget sain : {st['used_eur']} € / {st['cap_eur']} € este mês."


async def pilotage(month: str | None = None) -> dict:
    st = await cap.status(month)
    proj = _projection(st)
    return {
        "month": st["month"],
        "currency": st["currency"],
        "status": st,
        "projection": proj,
        "health": _health(st, proj),
        "headline": _headline(st, proj),
        "recommendations": _recommendations(st, proj),
        "new_engagements_allowed": st.get("new_engagements_allowed"),
        "generated_at": _now().isoformat(),
    }
