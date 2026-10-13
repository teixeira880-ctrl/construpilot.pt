"""Cascade multi-provider Vision pour l'analyse d'images de plans.

Ordre de priorité (chaque étage complète le précédent) :
  1. **Claude Sonnet 4.6 Vision** (via Emergent) → analyse fine des symboles,
     annotations et cotes.
  2. **OpenAI GPT-4o Vision** → détection d'éléments architecturaux + fallback.
  3. **Gemini 1.5 Pro** (si dispo via Emergent) → seconde opinion.
  4. **Perplexity** — reçoit le texte détecté pour identifier les normes /
     DTU / matériaux applicables.

Les résultats sont *fusionnés* : on vote sur les éléments détectés (mur,
porte, fenêtre, cote) et on retient la confiance moyenne pondérée.
"""
from __future__ import annotations

import asyncio
import base64
import logging
import os
import uuid

from perplexity_plus import client as pplx

logger = logging.getLogger(__name__)


ANALYSIS_SYSTEM = (
    "Tu es expert en lecture de plans architecturaux et techniques BTP en France. "
    "Analyse l'image fournie et détecte :\n"
    "  - le type de plan (masse / niveau / coupe / façade / détail)\n"
    "  - l'échelle si visible\n"
    "  - les cotes principales et leurs valeurs\n"
    "  - les éléments présents (murs, poteaux, portes, fenêtres, escaliers, sanitaires)\n"
    "  - les annotations techniques (matériaux, sections, référentiels DTU)\n"
    "  - toute pathologie visible (fissures, humidité, désordres)\n"
    "Réponds en JSON strict :\n"
    "{\n"
    '  "plan_type": str,\n'
    '  "scale": str|null,\n'
    '  "orientation": str|null,\n'
    '  "dimensions": [ { "label": str, "value_m": number|null, "raw": str } ],\n'
    '  "elements": [ { "kind": str, "count": int, "confidence": 0..1, "notes": str|null } ],\n'
    '  "annotations": [str],\n'
    '  "pathologies": [str],\n'
    '  "text_detected": str,\n'
    '  "warnings": [str]\n'
    "}\n"
    "Ne renvoie AUCUN texte hors JSON."
)


async def _analyze_with_provider(
    *, provider: str, model: str, image_b64: str, image_mime: str = "image/png",
) -> dict | None:
    """Appel générique via emergentintegrations avec ImageContent."""
    if not os.environ.get("EMERGENT_LLM_KEY"):
        return None
    try:
        from emergentintegrations.llm.chat import ImageContent, UserMessage

        from engines.expenses.metering import MeteredChat as LlmChat
        chat = LlmChat(
            api_key=os.environ["EMERGENT_LLM_KEY"],
            session_id=f"plans-vision-{uuid.uuid4().hex[:8]}",
            expense_feature="plans_pro_vision",
            system_message=ANALYSIS_SYSTEM,
        ).with_model(provider, model)
        msg = UserMessage(
            text="Analyse cette image et renvoie le JSON demandé.",
            file_contents=[ImageContent(image_base64=image_b64)],
        )
        raw = await chat.send_message(msg)
        text = raw if isinstance(raw, str) else str(raw)
        return _extract_json(text)
    except Exception as e:
        logger.warning("Vision %s/%s failed: %s", provider, model, e)
        return None


def _to_png(data: bytes, mime: str) -> bytes:
    """ImageContent ne porte pas de MIME : on normalise JPG/WEBP en PNG."""
    if mime == "image/png" or data[:8] == b"\x89PNG\r\n\x1a\n":
        return data
    import io

    from PIL import Image
    buf = io.BytesIO()
    Image.open(io.BytesIO(data)).convert("RGB").save(buf, format="PNG")
    return buf.getvalue()


def _extract_json(text: str) -> dict | None:
    import json
    import re
    text = re.sub(r"^```(?:json)?\s*", "", text.strip())
    text = re.sub(r"\s*```\s*$", "", text)
    try:
        return json.loads(text)
    except Exception:
        pass
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1:
        return None
    try:
        return json.loads(text[start:end + 1])
    except Exception:
        return None


_KIND_ALIASES = {
    "mur": "murs", "wall": "murs", "walls": "murs", "porte": "portes", "door": "portes", "doors": "portes",
    "fenetre": "fenêtres", "fenêtre": "fenêtres", "window": "fenêtres", "windows": "fenêtres",
    "poteau": "poteaux", "column": "poteaux", "columns": "poteaux", "escalier": "escaliers", "stair": "escaliers", "stairs": "escaliers",
    "sanitaire": "sanitaires", "wc": "sanitaires",
}


def _norm_kind(kind: str) -> str:
    k = str(kind or "").lower().strip()
    return _KIND_ALIASES.get(k, k)


def validate_provider_result(raw: dict, provider: str) -> dict | None:
    """Validation par schéma de la réponse d'un fournisseur ; None si inexploitable."""
    if not isinstance(raw, dict):
        return None
    out = {"provider": provider, "plan_type": raw.get("plan_type") if isinstance(raw.get("plan_type"), str) else None,
           "scale": raw.get("scale") if isinstance(raw.get("scale"), str) else None,
           "orientation": raw.get("orientation") if isinstance(raw.get("orientation"), str) else None,
           "dimensions": [], "elements": [], "annotations": [], "pathologies": [], "warnings": [],
           "text_detected": str(raw.get("text_detected") or "")[:2000]}
    for d in raw.get("dimensions") or []:
        if isinstance(d, dict) and (d.get("raw") or d.get("label")):
            v = d.get("value_m")
            out["dimensions"].append({"label": str(d.get("label") or "")[:80], "raw": str(d.get("raw") or "")[:80],
                                      "value_m": float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else None})
    for el in raw.get("elements") or []:
        if not isinstance(el, dict) or not el.get("kind"):
            continue
        cnt, conf = el.get("count"), el.get("confidence")
        if isinstance(cnt, bool) or not isinstance(cnt, (int, float)) or cnt < 0:
            out["warnings"].append(f"{provider} : comptage invalide pour « {el.get('kind')} » ignoré")
            continue
        conf = float(conf) if isinstance(conf, (int, float)) and not isinstance(conf, bool) else None
        out["elements"].append({"kind": _norm_kind(el["kind"]), "count": int(cnt),
                                "declared_confidence": max(0.0, min(1.0, conf)) if conf is not None else None,
                                "notes": str(el.get("notes"))[:200] if el.get("notes") else None})
    for key in ("annotations", "pathologies", "warnings"):
        out[key].extend(str(x)[:200] for x in (raw.get(key) or []) if isinstance(x, (str, int, float)))
    if not out["elements"] and not out["plan_type"] and not out["text_detected"]:
        return None
    return out


def merge_observations(results: list[dict]) -> tuple[list[dict], bool]:
    """Fusion sans moyenne : un comptage n'est retenu que si tous les fournisseurs concordent.

    Retourne (elements, needs_review). Chaque élément conserve ses observations sources.
    """
    by_kind: dict[str, list[dict]] = {}
    for r in results:
        seen = set()
        for el in r["elements"]:
            if el["kind"] in seen:
                continue
            seen.add(el["kind"])
            by_kind.setdefault(el["kind"], []).append({"provider": r["provider"], "count": el["count"],
                                                        "declared_confidence": el["declared_confidence"], "notes": el["notes"]})
    elements, needs_review = [], False
    n_providers = len(results)
    for kind, obs in by_kind.items():
        counts = sorted({o["count"] for o in obs})
        agreed = len(counts) == 1 and len(obs) >= min(2, n_providers)
        item = {"kind": kind, "contributions": len(obs), "providers_total": n_providers, "observations": obs,
                "count": counts[0] if agreed else None, "count_range": [counts[0], counts[-1]],
                "agreed": agreed, "disagreement": len(counts) > 1, "needs_review": not agreed,
                "notes": " | ".join(o["notes"] for o in obs if o["notes"])[:400] or None}
        if len(obs) < n_providers:
            item["needs_review"] = True
            item["missing_from"] = [r["provider"] for r in results if r["provider"] not in {o["provider"] for o in obs}]
        needs_review = needs_review or item["needs_review"]
        elements.append(item)
    elements.sort(key=lambda e: (not e["disagreement"], e["kind"]))
    return elements, needs_review


PROVIDERS = [("claude", "anthropic", "claude-sonnet-4-6"), ("gpt-5.5", "openai", "gpt-5.5"), ("gemini", "gemini", "gemini-3.1-pro-preview")]


async def analyze_plan_image(
    *,
    image_bytes: bytes,
    image_mime: str = "image/png",
    include_web_check: bool = True,
) -> dict:
    """Lecture d'une image de plan : 2 fournisseurs vision, un 3ᵉ seulement en cas de désaccord.

    Contrat : ok / status ∈ {ok, needs_review, failed} / elements avec observations par fournisseur /
    warnings propagés. Aucun comptage n'est « validé » par moyenne.
    """
    image_b64 = base64.b64encode(_to_png(image_bytes, image_mime)).decode("ascii")
    image_mime = "image/png"

    async def run(spec):
        name, provider, model = spec
        raw = await _analyze_with_provider(provider=provider, model=model, image_b64=image_b64, image_mime=image_mime)
        return name, (validate_provider_result(raw, name) if raw else None)

    first = await asyncio.gather(*(run(s) for s in PROVIDERS[:2]), return_exceptions=True)
    results, providers_failed = [], []
    for spec, r in zip(PROVIDERS[:2], first):
        if isinstance(r, tuple) and r[1]:
            results.append(r[1])
        else:
            providers_failed.append(spec[0])
    escalated = False
    if len(results) < 2 or merge_observations(results)[1]:
        escalated = True
        name, third = await run(PROVIDERS[2])
        if third:
            results.append(third)
        else:
            providers_failed.append(name)
    providers_used = [r["provider"] for r in results]

    if not results:
        return {"ok": False, "status": "failed", "error": "Aucun fournisseur vision n'a répondu : lecture IA indisponible, relancez l'analyse.",
                "providers_used": [], "providers_failed": providers_failed, "elements": [], "warnings": []}

    elements, needs_review = merge_observations(results)
    warnings = []
    for r in results:
        warnings.extend(f"{r['provider']} : {w}" for w in r["warnings"])
    if len(results) < 2:
        needs_review = True
        warnings.append("Un seul fournisseur a répondu : comptages non recoupés.")
    disagreements = [e for e in elements if e["disagreement"]]
    if disagreements:
        warnings.append("Désaccord entre fournisseurs sur : " + ", ".join(f"{e['kind']} ({e['count_range'][0]}–{e['count_range'][1]})" for e in disagreements[:6]))

    def pick(field: str, default=None):
        for r in results:
            if r.get(field):
                return r[field]
        return default

    all_annotations = list(dict.fromkeys(a for r in results for a in r["annotations"]))[:20]
    all_pathologies = list(dict.fromkeys(p for r in results for p in r["pathologies"]))[:20]
    result = {
        "ok": True,
        "status": "needs_review" if needs_review else "ok",
        "needs_review": needs_review,
        "plan_type": pick("plan_type"),
        "scale": pick("scale"),
        "orientation": pick("orientation"),
        "dimensions": pick("dimensions", []),
        "elements": elements,
        "disagreements": [e["kind"] for e in disagreements],
        "annotations": all_annotations,
        "pathologies": all_pathologies,
        "warnings": list(dict.fromkeys(warnings)),
        "text_detected": " ".join(r["text_detected"] for r in results)[:2000],
        "providers_used": providers_used,
        "providers_failed": providers_failed,
        "escalated_to_third_provider": escalated,
        "provider_count": len(providers_used),
        "confidence_note": "Les confiances déclarées par les modèles ne sont pas des probabilités mesurées.",
    }

    # Étape 3 : check normes/DTU applicables via Perplexity (optionnel)
    if include_web_check and pplx.configured() and (all_annotations or all_pathologies):
        try:
            check_question = (
                "Éléments détectés sur ce plan : "
                f"annotations = {', '.join(all_annotations[:10]) or '(aucune)'} ; "
                f"pathologies = {', '.join(all_pathologies[:10]) or '(aucune)'} ; "
                f"type = {result.get('plan_type') or 'inconnu'}. "
                "Quels DTU / normes / points de vigilance réglementaires s'appliquent ?"
            )
            check = await pplx.ask(
                question=check_question,
                instructions="Réponds en français, concis, avec DTU / NF / URL. Liste maximum 8 points.",
                preset="medium",
                domain_filter=["legifrance.gouv.fr", "cstb.fr", "afnor.org", "boutique.afnor.org"],
                search_context_size="medium",
                max_results=6,
                max_output_tokens=800,
            )
            result["applicable_norms"] = {
                "text": check.get("text"),
                "citations": check.get("citations", []),
            }
        except Exception as e:
            logger.warning("Perplexity norm check failed: %s", e)

    return result
