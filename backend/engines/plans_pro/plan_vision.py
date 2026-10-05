"""Cascade IA para análise de plantas Autodesk.

Ordem (adaptado à arquitetura PT: Opus 5.5 + OpenAI + Perplexity):
  1. OpenAI Vision (gpt-4o) analisa a thumbnail → deteta elementos visíveis.
  2. Claude Opus 5.5 recebe metadata Autodesk + observação visão → sintetiza
     relatório PT (orçamento estimado, normas, recomendações).
  3. Perplexity (opcional) → normas PT aplicáveis (RGEU, Eurocodes, REH, REBAP).

Zero dependência de emergentintegrations. Usa diretamente o `ai_router`.
"""
from __future__ import annotations

import base64
import json
import logging
import re
from typing import Any

from engines.ai_providers.router import ai_router

logger = logging.getLogger("plans_pro.vision")


VISION_SYSTEM = (
    "És perito em leitura de plantas BTP em Portugal. Analisa a imagem e devolve "
    "APENAS JSON válido com esta estrutura:\n"
    "{\n"
    '  "plan_type": "massa"|"planta"|"corte"|"alcado"|"detalhe"|"3d"|"desconhecido",\n'
    '  "scale": string|null,\n'
    '  "orientation": string|null,\n'
    '  "elements": [{"kind": string, "count": int, "notes": string|null}],\n'
    '  "dimensions": [{"label": string, "value_m": number|null, "raw": string}],\n'
    '  "annotations": [string],\n'
    '  "pathologies": [string],\n'
    '  "text_detected": string\n'
    "}\n"
    "Elementos típicos (kind): paredes, portas, janelas, pilares, vigas, lajes, escadas, "
    "coberturas, fundacoes, sanitarios, aberturas. Responde SEM texto fora do JSON."
)


SYNTHESIS_SYSTEM = (
    "És engenheiro civil português. Analisas plantas BTP e produzes relatórios em PT-PT. "
    "Recebes metadata Autodesk Model Derivative + leitura visual OpenAI. "
    "Produz APENAS JSON válido (sem markdown, sem comentários). Sê conciso: "
    "máx 10 ouvrages, nomes curtos, observações <80 car. Estrutura:\n"
    "{\n"
    '  "resumo": string (3-4 linhas),\n'
    '  "ouvrages": [{"nome": string, "quantidade": number|null, "unidade": string, "pu_eur": number|null, "total_eur": number|null, "observacoes": string}],\n'
    '  "orcamento": {"total_ht_eur": number, "iva_eur": number, "total_ttc_eur": number, "iva_rate": 0.23},\n'
    '  "normas_aplicaveis": [string max 6],\n'
    '  "pontos_atencao": [string max 5],\n'
    '  "recomendacoes": [string max 5]\n'
    "}\n"
    "Referências: Biblioteca PT 2026, RGEU, Eurocódigos, REH, REBAP, DL 220/2008. IVA 23%."
)


def _extract_json(text: str) -> dict | None:
    if not text:
        return None
    text = re.sub(r"^```(?:json)?\s*", "", text.strip())
    text = re.sub(r"\s*```\s*$", "", text)
    try:
        return json.loads(text)
    except Exception:
        pass
    s, e = text.find("{"), text.rfind("}")
    if s == -1 or e <= s:
        return None
    try:
        return json.loads(text[s:e + 1])
    except Exception:
        pass
    # Tolerante: tenta fechar JSON truncado em max_tokens.
    try:
        import ast
        snippet = text[s:]
        # Fecha brackets abertos
        opens_c = snippet.count("{") - snippet.count("}")
        opens_s = snippet.count("[") - snippet.count("]")
        patched = snippet.rstrip().rstrip(",")
        # remove último objeto incompleto
        if not patched.endswith(("}", "]", '"')):
            last_comma = patched.rfind(",")
            if last_comma > 0:
                patched = patched[:last_comma]
        patched += "]" * max(0, opens_s) + "}" * max(0, opens_c)
        return json.loads(patched)
    except Exception:
        return None


async def _vision_openai(image_bytes: bytes, mime: str) -> dict | None:
    """OpenAI gpt-4o vision via `image_url` data URI."""
    provider = ai_router.openai_vision or ai_router.openai_coach
    if not provider:
        return None
    b64 = base64.b64encode(image_bytes).decode()
    data_uri = f"data:{mime};base64,{b64}"
    try:
        r = await provider.ask(
            prompt="Analisa esta planta e devolve o JSON pedido.",
            system=VISION_SYSTEM,
            max_tokens=1200,
            temperature=0.1,
            image_url=data_uri,
            json_mode=True,
        )
        return _extract_json(r.text)
    except Exception as e:  # noqa: BLE001
        logger.warning("vision openai falhou: %s", type(e).__name__)
        return None


async def _synthesis_claude(
    *, metadata: dict, vision: dict | None, filename: str, project_hint: str | None,
) -> dict | None:
    """Síntese Opus 5.5: metadata + visão → relatório PT estruturado."""
    if not ai_router.claude:
        # Fallback: usa OpenAI coach
        if not ai_router.openai_coach:
            return None
        provider = ai_router.openai_coach
    else:
        provider = ai_router.claude

    quantities = metadata.get("quantities") or {}
    quantities_text = json.dumps(quantities, ensure_ascii=False, indent=2)[:4000]
    vision_text = json.dumps(vision or {}, ensure_ascii=False, indent=2)[:3000]
    prompt = (
        f"Ficheiro: {filename}\n"
        f"Projeto / contexto: {project_hint or 'N/A'}\n\n"
        f"[QUANTIDADES AUTODESK]\n{quantities_text}\n\n"
        f"[LEITURA VISUAL]\n{vision_text}\n\n"
        "Produz o relatório JSON pedido no system message."
    )
    try:
        r = await provider.ask(
            prompt=prompt, system=SYNTHESIS_SYSTEM,
            max_tokens=4000, temperature=0.2,
        )
        return _extract_json(r.text)
    except Exception as e:  # noqa: BLE001
        logger.warning("synthesis claude falhou: %s", type(e).__name__)
        return None


async def _norms_perplexity(ouvrages: list[dict], pathologies: list[str]) -> dict | None:
    pplx = ai_router.perplexity
    if not pplx:
        return None
    try:
        key_ouvrages = [o.get("nome", "") for o in (ouvrages or [])[:6] if o.get("nome")]
        question = (
            "Quais são as normas portuguesas e europeias aplicáveis a uma obra que inclui: "
            f"{', '.join(key_ouvrages) or 'estrutura corrente'}? "
            f"Pathologias detetadas: {', '.join(pathologies or []) or 'nenhuma'}. "
            "Lista RGEU, Eurocódigos, REH, REBAP, DL aplicáveis. Responde em PT-PT, "
            "conciso, com referências e URLs oficiais (dre.pt, lnec.pt) quando possível. Máx 8 pontos."
        )
        r = await pplx.ask(prompt=question, system=None, max_tokens=800, temperature=0.1)
        return {
            "text": r.text,
            "citations": [c.url if hasattr(c, "url") else str(c) for c in (r.citations or [])][:10],
        }
    except Exception as e:  # noqa: BLE001
        logger.warning("norms perplexity falhou: %s", type(e).__name__)
        return None


async def full_analysis(
    *,
    filename: str,
    metadata: dict,
    thumbnail_bytes: bytes | None,
    thumbnail_mime: str = "image/png",
    project_hint: str | None = None,
    include_web_norms: bool = True,
) -> dict:
    """Pipeline IA completo. Retorna dict com `vision`, `synthesis`, `norms`, `status`."""
    out: dict[str, Any] = {
        "vision": None,
        "synthesis": None,
        "norms": None,
        "providers_used": [],
        "status": "pending",
        "warnings": [],
    }

    # 1. Vision
    if thumbnail_bytes:
        vision = await _vision_openai(thumbnail_bytes, thumbnail_mime)
        if vision:
            out["vision"] = vision
            out["providers_used"].append("openai-vision")
        else:
            out["warnings"].append("Leitura visual indisponível.")
    else:
        out["warnings"].append("Sem thumbnail Autodesk — leitura visual não executada.")

    # 2. Síntese Opus 5.5
    synth = await _synthesis_claude(
        metadata=metadata, vision=out["vision"],
        filename=filename, project_hint=project_hint,
    )
    if synth:
        out["synthesis"] = synth
        out["providers_used"].append("claude-opus-5-5" if ai_router.claude else "openai-coach")
    else:
        out["warnings"].append("Síntese IA indisponível.")

    # 3. Normas PT (opcional)
    if include_web_norms and synth:
        norms = await _norms_perplexity(
            synth.get("ouvrages", []),
            (out["vision"] or {}).get("pathologies", []),
        )
        if norms:
            out["norms"] = norms
            out["providers_used"].append("perplexity")

    out["status"] = "done" if synth else "failed"
    out["model_used"] = "claude-opus-5-5"
    return out
