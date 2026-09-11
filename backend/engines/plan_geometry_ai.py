"""Analyse géométrique IA d'un plan (double lecture) selon le prompt système ConstruPilot."""
from __future__ import annotations

import json
import logging
import os

from engines.plan_ai import _parse_json_response
from engines.plan_geometry_prompt import PASS1_FORMAT, PASS2_FORMAT, SYSTEM_GEOMETRY
from engines.plan_principles import CORE_PRINCIPLES

logger = logging.getLogger(__name__)

LEVELS = ["VERT", "BLEU", "JAUNE", "ORANGE", "ROUGE"]
LEVEL_LABEL = {"VERT": "Cohérent", "BLEU": "Information", "JAUNE": "À vérifier",
               "ORANGE": "Incohérence", "ROUGE": "Incohérence majeure"}


def level_for_mm(delta_mm: float) -> str:
    """Seuils de détection ConstruPilot (pas des tolérances réglementaires)."""
    a = abs(delta_mm)
    if a <= 2:
        return "VERT"
    if a <= 10:
        return "BLEU"
    if a <= 30:
        return "JAUNE"
    if a <= 100:
        return "ORANGE"
    return "ROUGE"


async def _call(image_b64: str, prompt: str) -> dict:
    from emergentintegrations.llm.chat import ImageContent, LlmChat, UserMessage
    from engines.plan_ai import plan_model
    api_key = os.environ.get("EMERGENT_LLM_KEY")
    if not api_key:
        return {"error": "EMERGENT_LLM_KEY absent"}
    provider, model = plan_model()
    chat = LlmChat(api_key=api_key, session_id="plan-geometry",
                   system_message=CORE_PRINCIPLES + "\n\n" + SYSTEM_GEOMETRY).with_model(provider, model)
    raw = await chat.send_message(UserMessage(text=prompt, file_contents=[ImageContent(image_base64=image_b64)]))
    return _parse_json_response(raw)


def _cotes_for_prompt(report: dict) -> list[dict]:
    out = []
    for it in report.get("items") or []:
        if it.get("ignored"):
            continue
        out.append({"index": it["index"], "cote_inscrite_m": it["indicated_m"], "mesure_m": it["measured_m"],
                    "ecart_cm": it["delta_cm"], "orientation": {"h": "horizontale", "v": "verticale"}.get(it["orientation"], "oblique"),
                    "position_px": [it["x1"], it["y1"], it["x2"], it["y2"]], "localisation": it.get("location"),
                    "confiance_lecture": it.get("confidence")})
    return out


def _norm_level(v: str | None, ecart_mm: float | None) -> str:
    v = (v or "").upper().strip()
    if v in LEVELS:
        return v
    return level_for_mm(ecart_mm or 0) if ecart_mm is not None else "JAUNE"


def _clean_anomalies(items: list, start: int = 1) -> list[dict]:
    out = []
    for i, a in enumerate(items or []):
        if not isinstance(a, dict):
            continue
        try:
            ecart = float(a.get("ecart_mm")) if a.get("ecart_mm") is not None else None
        except (TypeError, ValueError):
            ecart = None
        out.append({"numero": int(a.get("numero") or start + i), "localisation": a.get("localisation") or "NON INDIQUÉ",
                    "donnee_plan": a.get("donnee_plan") or "", "calcul": a.get("calcul") or "",
                    "formule": a.get("formule") or "", "resultat": a.get("resultat") or "",
                    "ecart_mm": ecart, "niveau": _norm_level(a.get("niveau"), ecart),
                    "confiance": (a.get("confiance") or "MOYEN").upper(), "explication": a.get("explication") or "",
                    "hypotheses": [str(h) for h in (a.get("hypotheses") or [])], "action": a.get("action") or "",
                    "cotes_index": [int(x) for x in (a.get("cotes_index") or []) if str(x).isdigit()],
                    "verification": None})
    return out


async def analyze_geometry(image_b64: str, report: dict, w: int, h: int) -> dict:
    """Double lecture : passage 1 (lecture + reconstruction) puis passage 2 (recalcul indépendant)."""
    cal = report.get("calibration") or {}
    p1 = await _call(image_b64, PASS1_FORMAT.format(
        cotes_json=json.dumps(_cotes_for_prompt(report), ensure_ascii=False),
        ppm=round(float(cal.get("pixels_per_meter") or 0), 2), w=w, h=h,
        source=(report.get("reading") or {}).get("source", "ai")))
    if p1.get("error"):
        return {"error": f"Passage 1 impossible : {p1['error']}"}
    anomalies = _clean_anomalies(p1.get("anomalies"))
    p2 = await _call(image_b64, PASS2_FORMAT.format(pass1_json=json.dumps(
        {"anomalies": anomalies, "fermetures": p1.get("fermetures") or []}, ensure_ascii=False)[:12000]))
    verifs = {}
    extra: list[dict] = []
    if not p2.get("error"):
        for v in p2.get("verifications") or []:
            if isinstance(v, dict) and v.get("numero") is not None:
                verifs[int(v["numero"])] = {"verdict": (v.get("verdict") or "INCERTAINE").upper(),
                                            "recalcul": v.get("recalcul") or "", "commentaire": v.get("commentaire") or ""}
        extra = _clean_anomalies(p2.get("anomalies_supplementaires"), start=100)
        for a in extra:
            a["verification"] = {"verdict": "PASSAGE 2 UNIQUEMENT", "recalcul": "", "commentaire": ""}
    for a in anomalies:
        a["verification"] = verifs.get(a["numero"]) or {"verdict": "NON REVUE", "recalcul": "", "commentaire": ""}
        if a["verification"]["verdict"] == "INFIRMÉE" and a["niveau"] in ("ORANGE", "ROUGE"):
            a["niveau_initial"] = a["niveau"]
            a["niveau"] = "JAUNE"
    all_anoms = anomalies + extra
    counts = {lv: sum(1 for a in all_anoms if a["niveau"] == lv) for lv in LEVELS}
    worst = next((lv for lv in reversed(LEVELS) if counts[lv]), "VERT")
    return {
        "document": p1.get("document") or {}, "orientation": p1.get("orientation") or {},
        "hierarchie": p1.get("hierarchie") or [], "fermetures": p1.get("fermetures") or [],
        "controles_croises": p1.get("controles_croises") or [], "facades": p1.get("facades") or [],
        "alignements": p1.get("alignements") or [], "murs": p1.get("murs") or {},
        "fondations": p1.get("fondations") or [], "matrice": p1.get("matrice") or [],
        "anomalies": all_anoms, "reponses": p1.get("reponses") or {}, "synthese": p1.get("synthese") or "",
        "donnees_extraites": p1.get("donnees_extraites") or [], "hypotheses_fermeture": p1.get("hypotheses_fermeture") or [],
        "explications": p1.get("explications") or [], "checklist": p1.get("checklist") or [],
        "conclusion": p1.get("conclusion") or "",
        "double_lecture": {"ok": not p2.get("error"), "ecarts_entre_passes": p2.get("ecarts_entre_passes") or [],
                           "conclusion": p2.get("conclusion") or p2.get("error") or "",
                           "confirmees": sum(1 for a in anomalies if a["verification"]["verdict"] == "CONFIRMÉE"),
                           "infirmees": sum(1 for a in anomalies if a["verification"]["verdict"] == "INFIRMÉE")},
        "counts": counts, "niveau_global": worst, "niveau_global_label": LEVEL_LABEL[worst],
    }
