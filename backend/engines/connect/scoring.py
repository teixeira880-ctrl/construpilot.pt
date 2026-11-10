"""Prioridade comercial 0–100, baseada em regras transparentes e configuráveis.

Não é uma probabilidade de compra e nunca exclui oportunidades. Não usa nacionalidade,
país, idioma nem qualquer atributo sensível ou protegido.
"""
from __future__ import annotations

from copy import deepcopy

DEFAULT_CONFIG = {
    "thresholds": {"high": 75, "medium": 45},
    "client": {
        "fit": {"builder": 25, "trade": 25, "estimator": 25, "design": 18, "owner": 18,
                "supplier": 10, "other": 10, "private": 5},
        "pain_count": {"1": 8, "2": 12, "3": 15},
        "volume": {"q0_5": 2, "q6_15": 6, "q16_40": 8, "q40p": 10,
                   "p1_2": 3, "p3_5": 6, "p6_10": 8, "p10p": 10,
                   "t1": 2, "t2_10": 5, "t11_50": 8, "t50p": 10},
        "urgency": {"immediate": 20, "d30": 16, "m3": 9, "exploring": 2},
        "decision": {"decide": 15, "evaluate": 10, "other": 4, "personal": 2},
        "next_step": {"meeting": 15, "pilot": 15, "individual_demo": 15, "report": 8, "none": 0},
        "demo_completed_bonus": 4,
    },
    "investor": {
        "fit_sector": {"contech": 15, "proptech": 12, "b2b_saas": 10, "ai": 8, "climate": 6, "other": 2},
        "fit_stage": {"pre_seed": 10, "seed": 10, "series_a": 4, "later": 1},
        "availability": {"this_week": 20, "two_weeks": 15, "later": 5},
        "collab": {"equity": 15, "strategic": 12, "advisory": 6, "learn": 3},
        "identity": {"org": 8, "website": 7},
        "next_step": {"meeting": 15, "report": 6, "none": 0},
    },
    "partner": {
        "kind": {"pilot": 12, "integration": 10, "distribution": 10, "demonstration": 8, "content": 8, "training": 6},
        "scale": {"s_lt50": 6, "s50_500": 14, "s500p": 20},
        "timeline": {"now": 20, "quarter": 14, "later": 4},
        "identity": {"org": 10, "website": 5},
        "next_step": {"meeting": 15, "report": 6, "none": 0},
    },
}

REASONS = {
    "fit_high": {"pt": "perfil alinhado com o público-alvo", "en": "profile matches the target audience", "fr": "profil aligné avec la cible"},
    "fit_low": {"pt": "perfil fora do núcleo do público-alvo", "en": "profile outside the core audience", "fr": "profil hors du cœur de cible"},
    "pains_many": {"pt": "identificou vários problemas", "en": "reported several problems", "fr": "a signalé plusieurs problèmes"},
    "volume_high": {"pt": "prepara muitos orçamentos ou gere muitas obras", "en": "handles a high volume of estimates or jobs", "fr": "gère un volume élevé de devis ou de chantiers"},
    "urgent": {"pt": "quer resolver em 30 dias ou já", "en": "wants to act within 30 days", "fr": "veut agir sous 30 jours"},
    "exploring": {"pt": "está apenas a explorar", "en": "is just exploring", "fr": "est en phase d'exploration"},
    "decider": {"pt": "é decisor", "en": "is the decision-maker", "fr": "est décideur"},
    "evaluator": {"pt": "participa na avaliação", "en": "helps evaluate", "fr": "participe à l'évaluation"},
    "asked_meeting": {"pt": "pediu reunião, demonstração individual ou piloto", "en": "asked for a meeting, individual demo or pilot", "fr": "a demandé un rendez-vous, une démo ou un pilote"},
    "asked_report": {"pt": "pediu o resumo do diagnóstico", "en": "asked for the diagnosis summary", "fr": "a demandé le résumé du diagnostic"},
    "demo_done": {"pt": "concluiu a demonstração", "en": "completed the demo", "fr": "a terminé la démo"},
    "sector_fit": {"pt": "investe em ConTech/PropTech/SaaS", "en": "invests in ConTech/PropTech/SaaS", "fr": "investit en ConTech/PropTech/SaaS"},
    "stage_fit": {"pt": "investe em fase inicial", "en": "invests at early stage", "fr": "investit en amorçage"},
    "available_soon": {"pt": "disponível para conversar em breve", "en": "available to talk soon", "fr": "disponible rapidement"},
    "equity_interest": {"pt": "interesse em investimento ou parceria estratégica", "en": "interested in equity or a strategic partnership", "fr": "intéressé par un investissement ou un partenariat stratégique"},
    "identified": {"pt": "organização identificada", "en": "organisation identified", "fr": "organisation identifiée"},
    "partner_scale": {"pt": "representa uma base de clientes relevante", "en": "represents a relevant client base", "fr": "représente une base clients significative"},
    "partner_soon": {"pt": "calendário próximo", "en": "near-term timeline", "fr": "calendrier proche"},
}


def merged_config(overrides: dict | None) -> dict:
    cfg = deepcopy(DEFAULT_CONFIG)
    for section, values in (overrides or {}).items():
        if section in cfg and isinstance(values, dict):
            for k, v in values.items():
                if isinstance(cfg[section].get(k), dict) and isinstance(v, dict):
                    cfg[section][k].update({kk: vv for kk, vv in v.items() if isinstance(vv, (int, float))})
                elif isinstance(v, (int, float)):
                    cfg[section][k] = v
    return cfg


def priority_for(score: int, cfg: dict) -> str:
    t = cfg["thresholds"]
    return "high" if score >= t["high"] else "medium" if score >= t["medium"] else "low"


def render_reasons(codes: list[str], lang: str = "pt") -> str:
    parts = [REASONS[c][lang if lang in ("pt", "en", "fr") else "pt"] for c in codes if c in REASONS]
    return ", ".join(parts)


def _clamp(v: float, hi: float) -> int:
    return int(max(0, min(hi, round(v))))


def score_client(answers: dict, group: str, next_step: str, demo_completed: bool, cfg: dict) -> dict:
    c = cfg["client"]
    reasons: list[str] = []
    fit = _clamp(c["fit"].get(group, 10), 25)
    reasons.append("fit_high" if fit >= 18 else "fit_low")
    pains = answers.get("pains") or []
    vol = answers.get("volume") or {}
    vol_id = next(iter(vol.values()), None) if vol else None
    vol_pts = c["volume"].get(vol_id or "", 0)
    intensity = _clamp(c["pain_count"].get(str(min(len(pains), 3)), 0) + vol_pts, 25)
    if len(pains) >= 2:
        reasons.append("pains_many")
    if vol_pts >= 8:
        reasons.append("volume_high")
    urg = answers.get("urgency") or ""
    urgency = _clamp(c["urgency"].get(urg, 0), 20)
    if urg in ("immediate", "d30"):
        reasons.append("urgent")
    elif urg == "exploring":
        reasons.append("exploring")
    dec = answers.get("decision") or ""
    decision = _clamp(c["decision"].get(dec, 0), 15)
    if dec == "decide":
        reasons.append("decider")
    elif dec == "evaluate":
        reasons.append("evaluator")
    interest = c["next_step"].get(next_step or "none", 0) + (c["demo_completed_bonus"] if demo_completed else 0)
    interest = _clamp(interest, 15)
    if next_step in ("meeting", "pilot", "individual_demo"):
        reasons.append("asked_meeting")
    elif next_step == "report":
        reasons.append("asked_report")
    if demo_completed:
        reasons.append("demo_done")
    comps = {"fit": fit, "intensity": intensity, "urgency": urgency, "decision": decision, "interest": interest}
    return _finish(comps, reasons, cfg)


def score_investor(answers: dict, next_step: str, cfg: dict) -> dict:
    c = cfg["investor"]
    reasons: list[str] = []
    sectors = answers.get("sectors") or []
    stages = answers.get("stages") or []
    fit = _clamp(max([c["fit_sector"].get(s, 0) for s in sectors] or [0])
                 + max([c["fit_stage"].get(s, 0) for s in stages] or [0]), 25)
    if any(s in ("contech", "proptech", "b2b_saas") for s in sectors):
        reasons.append("sector_fit")
    if any(s in ("pre_seed", "seed") for s in stages):
        reasons.append("stage_fit")
    urgency = _clamp(c["availability"].get(answers.get("availability") or "", 0), 20)
    if answers.get("availability") in ("this_week", "two_weeks"):
        reasons.append("available_soon")
    intensity = _clamp(c["collab"].get(answers.get("collab") or "", 0) + (10 if answers.get("investor_type") in ("vc", "angel", "cvc", "family_office") else 4), 25)
    if answers.get("collab") in ("equity", "strategic"):
        reasons.append("equity_interest")
    ident = (c["identity"]["org"] if (answers.get("organization") or "").strip() else 0) + \
            (c["identity"]["website"] if (answers.get("website") or "").strip() else 0)
    decision = _clamp(ident, 15)
    if ident:
        reasons.append("identified")
    interest = _clamp(c["next_step"].get(next_step or "none", 0), 15)
    if next_step == "meeting":
        reasons.append("asked_meeting")
    comps = {"fit": fit, "intensity": intensity, "urgency": urgency, "decision": decision, "interest": interest}
    return _finish(comps, reasons, cfg)


def score_partner(answers: dict, next_step: str, cfg: dict) -> dict:
    c = cfg["partner"]
    reasons: list[str] = ["fit_high"]
    fit = 20 if answers.get("partner_type") else 10
    kinds = answers.get("kinds") or []
    intensity = _clamp(max([c["kind"].get(k, 0) for k in kinds] or [0]) + c["scale"].get(answers.get("scale") or "", 0) * 0.65, 25)
    if answers.get("scale") in ("s50_500", "s500p"):
        reasons.append("partner_scale")
    urgency = _clamp(c["timeline"].get(answers.get("timeline") or "", 0), 20)
    if answers.get("timeline") in ("now", "quarter"):
        reasons.append("partner_soon")
    ident = (c["identity"]["org"] if (answers.get("organization") or "").strip() else 0) + \
            (c["identity"]["website"] if (answers.get("website") or "").strip() else 0)
    decision = _clamp(ident, 15)
    if ident:
        reasons.append("identified")
    interest = _clamp(c["next_step"].get(next_step or "none", 0), 15)
    if next_step == "meeting":
        reasons.append("asked_meeting")
    comps = {"fit": _clamp(fit, 25), "intensity": intensity, "urgency": urgency, "decision": decision, "interest": interest}
    return _finish(comps, reasons, cfg)


def _finish(comps: dict, reasons: list[str], cfg: dict) -> dict:
    score = int(sum(comps.values()))
    priority = priority_for(score, cfg)
    return {"score": score, "priority": priority, "components": comps, "reason_codes": reasons,
            "explanation": render_reasons(reasons, "pt")}


def score(profile: str, answers: dict, *, group: str = "other", next_step: str = "none",
          demo_completed: bool = False, overrides: dict | None = None) -> dict:
    cfg = merged_config(overrides)
    if profile == "client":
        return score_client(answers, group, next_step, demo_completed, cfg)
    if profile == "investor":
        return score_investor(answers, next_step, cfg)
    if profile == "partner":
        return score_partner(answers, next_step, cfg)
    raise ValueError("perfil inválido")
