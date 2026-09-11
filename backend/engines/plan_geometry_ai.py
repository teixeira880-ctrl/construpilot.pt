"""Analyse géométrique IA d'un plan (double lecture) selon le prompt système ConstruPilot."""
from __future__ import annotations

import json
import logging
import os

from engines.plan_ai import _parse_json_response
from engines.plan_geometry_prompt import (LANG_INSTRUCTION, PASS1_FORMAT, PASS2_FORMAT, PASS3_ADVERSARIAL, PASS4_NARRATIVE,
                                          SYSTEM_GEOMETRY)
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


async def _call(image_b64: str, prompt: str, lang: str = "fr") -> dict:
    from emergentintegrations.llm.chat import ImageContent, LlmChat, UserMessage
    from engines.plan_ai import plan_model
    api_key = os.environ.get("EMERGENT_LLM_KEY")
    if not api_key:
        return {"error": "EMERGENT_LLM_KEY absent"}
    provider, model = plan_model()
    chat = LlmChat(api_key=api_key, session_id="plan-geometry",
                   system_message=CORE_PRINCIPLES + "\n\n" + SYSTEM_GEOMETRY + "\n\n" + LANG_INSTRUCTION.get(lang, LANG_INSTRUCTION["fr"])
                   ).with_model(provider, model)
    raw = await chat.send_message(UserMessage(text=prompt, file_contents=[ImageContent(image_base64=image_b64)]))
    return _parse_json_response(raw)


def _cotes_for_prompt(report: dict) -> list[dict]:
    out = []
    for it in report.get("items") or []:
        if it.get("ignored"):
            continue
        out.append({"index": it["index"], "cote_inscrite_m": it["indicated_m"], "mesure_m": it["measured_m"],
                    "mesure": ("EXACTE (vecteurs PDF/DXF, mm)" if it.get("source") in ("pdf", "dxf")
                               else "PIXEL NON VÉRIFIÉE" if it.get("unverified") else "pixel"),
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


async def analyze_geometry(image_b64: str, report: dict, w: int, h: int, lang: str = "fr") -> dict:
    """Double lecture : passage 1 (lecture + reconstruction) puis passage 2 (recalcul indépendant)."""
    cal = report.get("calibration") or {}
    p1 = await _call(image_b64, PASS1_FORMAT.format(
        cotes_json=json.dumps(_cotes_for_prompt(report), ensure_ascii=False),
        ppm=round(float(cal.get("pixels_per_meter") or 0), 2), w=w, h=h,
        source={"pdf_vector+ai": "vecteurs PDF exacts (mesure au mm entre lignes d'attache, fait foi) croisés avec l'IA",
                "dxf": "DXF exact", "ai": "lecture IA sur image (mesure pixel ±1-2 %)"}.get(
            (report.get("reading") or {}).get("source", "ai"), "ai")), lang)
    if p1.get("error"):
        return {"error": f"Passage 1 impossible : {p1['error']}"}
    anomalies = _clean_anomalies(p1.get("anomalies"))
    p2 = await _call(image_b64, PASS2_FORMAT.format(pass1_json=json.dumps(
        {"anomalies": anomalies, "fermetures": p1.get("fermetures") or []}, ensure_ascii=False)[:12000]), lang)
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
    # PASSAGE 3 — agent de contrôle adversarial : tente de contredire chaque anomalie avant validation
    adversarial = {"ok": False, "maintenues": 0, "contestees": 0, "rejetees": 0, "conclusion": "", "quantites_douteuses": []}
    live = [a for a in all_anoms if a["niveau"] != "VERT"]
    if live:
        p3 = await _call(image_b64, PASS3_ADVERSARIAL.format(
            anomalies_json=json.dumps([{k: a[k] for k in ("numero", "localisation", "donnee_plan", "calcul", "formule",
                                                            "resultat", "ecart_mm", "niveau")} for a in live],
                                      ensure_ascii=False)[:12000],
            cotes_json=json.dumps([{"index": c["index"], "cote_inscrite_m": c["cote_inscrite_m"], "localisation": c["localisation"]}
                                   for c in _cotes_for_prompt(report)], ensure_ascii=False)[:6000]), lang)
        if not p3.get("error"):
            by_num = {int(c["numero"]): c for c in (p3.get("contestations") or [])
                      if isinstance(c, dict) and str(c.get("numero", "")).lstrip("-").isdigit()}
            for a in live:
                c = by_num.get(a["numero"])
                if not c:
                    continue
                verdict = (c.get("verdict") or "MAINTENUE").upper()
                a["adversarial"] = {"verdict": verdict, "attaque": c.get("attaque") or "", "recalcul": c.get("recalcul") or "",
                                    "commentaire": c.get("commentaire") or "", "confiance_finale": (c.get("confiance_finale") or "").upper()}
                if verdict == "REJETÉE":
                    a["niveau_initial"] = a.get("niveau_initial") or a["niveau"]
                    a["niveau"] = "BLEU"
                    adversarial["rejetees"] += 1
                elif verdict == "CONTESTÉE":
                    if a["niveau"] in ("ORANGE", "ROUGE"):
                        a["niveau_initial"] = a.get("niveau_initial") or a["niveau"]
                        a["niveau"] = "JAUNE"
                    adversarial["contestees"] += 1
                else:
                    adversarial["maintenues"] += 1
                if a["adversarial"]["confiance_finale"] in ("TRÈS ÉLEVÉ", "ÉLEVÉ", "MOYEN", "FAIBLE"):
                    a["confiance"] = a["adversarial"]["confiance_finale"]
            adversarial.update({"ok": True, "conclusion": p3.get("conclusion") or "",
                                "quantites_douteuses": [q for q in (p3.get("quantites_douteuses") or []) if isinstance(q, dict)]})
        else:
            adversarial["conclusion"] = p3["error"]
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
        "adversarial": adversarial, "lang": lang,
    }


def _fermetures_utiles(fermetures: list, chains: list) -> list:
    """Écarte les fermetures IA « chaînes incomplètes » (écart > 10 cm) quand une chaîne exacte existe pour la même cote."""
    exact_totals = [c["total_m"] for c in chains]
    out = []
    for f in fermetures:
        try:
            err, plan_m = abs(float(f.get("erreur_m") or 0)), float(f.get("cote_plan_m") or 0)
        except (TypeError, ValueError):
            out.append(f)
            continue
        if err > 0.1 and any(abs(t - plan_m) <= 0.011 for t in exact_totals):
            continue
        out.append(f)
    return out


def _narrative_data(report: dict, geo: dict) -> dict:
    items = {it["index"]: it for it in report.get("items") or [] if not it.get("ignored")}
    cal = report.get("calibration") or {}
    rd = report.get("reading") or {}
    return {
        "document": geo.get("document") or {},
        "echelle": {"declaree": cal.get("scale_denominator"), "effective": cal.get("effective_scale_denominator"),
                    "methode": cal.get("method")},
        "lecture": {"source": rd.get("source"), "croisement": rd.get("cross"), "abstention": report.get("abstention")},
        "cotes": [{"index": i, "cote_m": it["indicated_m"], "mesure_m": it["measured_m"], "ecart_mm": round(it["delta_m"] * 1000),
                   "niveau": it.get("niveau"), "statut": it["status"], "orientation": it["orientation"],
                   "exacte": it.get("source") in ("pdf", "dxf"), "position_px": [it["x1"], it["y1"], it["x2"], it["y2"]]}
                  for i, it in items.items()],
        "chaines_exactes": [{"total_index": c["total_index"], "total_m": c["total_m"], "parties": c["parts_m"],
                             "part_indexes": c["part_indexes"], "somme_m": c["sum_m"], "ecart_mm": round(c["delta_m"] * 1000),
                             "niveau": c.get("niveau"), "statut": c["status"]} for c in report.get("chains") or []],
        "fermetures_ia": _fermetures_utiles(geo.get("fermetures") or [], report.get("chains") or []),
        "hypotheses_fermeture": geo.get("hypotheses_fermeture") or [],
        "facades": geo.get("facades") or [],
        "alignements": geo.get("alignements") or [],
        "murs": geo.get("murs") or {},
        "anomalies": [{k: a.get(k) for k in ("numero", "localisation", "donnee_plan", "calcul", "formule", "resultat",
                                             "ecart_mm", "niveau", "niveau_initial", "confiance", "explication",
                                             "hypotheses", "action", "cotes_index")}
                      | {"passage2": (a.get("verification") or {}).get("verdict"),
                         "adversarial": (a.get("adversarial") or {}).get("verdict"),
                         "adversarial_attaque": (a.get("adversarial") or {}).get("attaque")}
                      for a in geo.get("anomalies") or []],
        "niveau_global": geo.get("niveau_global"), "synthese_ia": geo.get("synthese"),
        "adversarial": geo.get("adversarial") or {},
    }


def _clean_sections(sections) -> list[dict]:
    out = []
    for i, s in enumerate(sections or []):
        if not isinstance(s, dict) or not (s.get("texte") or s.get("titre")):
            continue
        try:
            ecart = float(s["ecart_mm"]) if s.get("ecart_mm") is not None else None
        except (TypeError, ValueError):
            ecart = None
        try:
            cote = float(s["cote_plan_m"]) if s.get("cote_plan_m") is not None else None
        except (TypeError, ValueError):
            cote = None
        out.append({"numero": int(s.get("numero") or i + 1), "titre": str(s.get("titre") or f"Section {i + 1}"),
                    "cote_plan_m": cote, "texte": str(s.get("texte") or ""), "calcul": str(s.get("calcul") or ""),
                    "ecart_mm": ecart, "niveau": _norm_level(s.get("niveau"), ecart), "conclusion": str(s.get("conclusion") or ""),
                    "cotes_index": [int(x) for x in (s.get("cotes_index") or []) if str(x).isdigit()]})
    return out


async def write_narrative(image_b64: str, report: dict, geo: dict, lang: str = "fr") -> dict:
    """Passage 4 : rédaction du rapport narratif (une section par grande cote) à partir des données validées."""
    data = _narrative_data(report, geo)
    p4 = await _call(image_b64, PASS4_NARRATIVE.format(
        lang_instruction=LANG_INSTRUCTION.get(lang, LANG_INSTRUCTION["fr"]),
        data_json=json.dumps(data, ensure_ascii=False)[:40000]), lang)
    if p4.get("error"):
        return {"error": f"Rédaction impossible : {p4['error']}"}
    sections = _clean_sections(p4.get("sections"))
    if not sections:
        return {"error": "Rédaction impossible : aucune section produite"}
    return {"titre": str(p4.get("titre") or ""), "introduction": str(p4.get("introduction") or ""),
            "methode": str(p4.get("methode") or ""), "sections": sections, "facades": str(p4.get("facades") or ""),
            "synthese": str(p4.get("synthese") or ""),
            "recommandations": [str(r) for r in (p4.get("recommandations") or []) if r],
            "conclusion": str(p4.get("conclusion") or ""), "lang": lang}
