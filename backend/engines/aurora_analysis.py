"""Análise de documentos via Aurora — Fase 1: Permis de Construire (PC).

Fluxo:
  1. PDF do PC → texto extraído localmente (pypdf).
  2. Texto + prompt de estruturação → `client.ask()` (Aurora AS1-signed).
  3. Resposta JSON parseada + normalizada.
  4. Cada trabalho é preçado por lookup na biblioteca do utilizador e, se não
     encontrado, na `shared_library_items` PT-2026.
"""
from __future__ import annotations

import json
import re
from typing import Any

from engines.aurora_client import (
    AuroraCompanyClient,
    AuroraConfig,
    AuroraKeyIdInvalid,
    AuroraNotConfigured,
)


# ---------------------------------------------------------------------------
# Prompt para estruturação
# ---------------------------------------------------------------------------
ASK_TEMPLATE_PC = """Perito em construção civil PT. Analisa o texto e devolve APENAS JSON compacto (sem markdown), formato:
{{"project_summary":{{"type":"novo|renovacao|ampliacao","area_construcao_m2":null,"num_pisos":null,"descricao":""}},"works":[{{"designation":"","category":"Estrutura|Alvenaria|Cobertura|Canalizacao|Eletricidade|Pladur|Pintura|Ceramica|Carpintaria|Piscinas|Isolamento|Vidros|AVAC|Exterior|Outros","unit":"m2|m3|un|ml|kg|forfait","quantity":0,"notes":""}}],"risks_and_notes":[]}}

Regras: PT-PT; quantity numérico; incluir riscos técnicos.

Texto PC:
---
{text}
---

Responde só JSON."""


ASK_TEMPLATE_PLAN = """Perito em construção civil PT. Analisa dados da planta {plan_type} e devolve APENAS JSON compacto:
{{"plan_summary":{{"type":"","area_total_m2":null,"num_divisoes":null,"escala":"","descricao":""}},"measurements":{{"paredes_ml":null,"portas_un":null,"janelas_un":null,"divisoes":[]}},"works":[{{"designation":"","category":"","unit":"m2|m3|un|ml|kg","quantity":0,"notes":""}}],"risks_and_notes":[]}}

Regras: PT-PT; quantity numérico.

Dados da planta:
---
{data}
---

Responde só JSON."""


# Limite de chars a enviar ao Aurora — modelo gpt-5.6-luna devolve `text:""`
# acima de ~1200 chars totais. Deixamos margem para o template (~600 chars).
AURORA_MAX_INPUT_CHARS = 700


# ---------------------------------------------------------------------------
# JSON extraction utilities
# ---------------------------------------------------------------------------
def _extract_json_from_response(text: str) -> dict | None:
    """Tenta extrair JSON de resposta LLM (com/sem markdown code fence)."""
    if not text:
        return None
    # 1) code fence
    m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(1))
        except Exception:  # noqa: BLE001
            pass
    # 2) primeiro { ... } balanceado
    start = text.find("{")
    if start >= 0:
        depth = 0
        for i in range(start, len(text)):
            c = text[i]
            if c == "{":
                depth += 1
            elif c == "}":
                depth -= 1
                if depth == 0:
                    try:
                        return json.loads(text[start:i + 1])
                    except Exception:  # noqa: BLE001
                        break
    # 3) texto direto
    try:
        return json.loads(text)
    except Exception:  # noqa: BLE001
        return None


# ---------------------------------------------------------------------------
# Aurora call
# ---------------------------------------------------------------------------
async def analyze_pc_document(*, text: str, project_id: str) -> dict[str, Any]:
    """Envia o texto do PC a Aurora e recebe análise estruturada JSON."""
    try:
        _ = AuroraConfig()
    except Exception:  # noqa: BLE001
        return {"ok": False, "error": "aurora_not_configured"}
    if not AuroraConfig().configured:
        return {"ok": False, "error": "aurora_not_configured"}

    question = ASK_TEMPLATE_PC.format(text=text[:AURORA_MAX_INPUT_CHARS])

    try:
        client = AuroraCompanyClient()
        r = await client.ask(question=question, project_id=project_id, resources=[])
    except AuroraNotConfigured:
        return {"ok": False, "error": "aurora_not_configured"}
    except AuroraKeyIdInvalid:
        return {"ok": False, "error": "aurora_invalid_key_format"}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": "aurora_exception", "detail": type(e).__name__}

    if r.status_code >= 400:
        return {"ok": False, "error": f"aurora_ask_{r.status_code}",
                "detail": r.text[:500]}

    try:
        payload = r.json()
    except Exception:  # noqa: BLE001
        payload = {"_raw": r.text[:2000]}

    answer_text = (
        payload.get("text")
        or payload.get("answer")
        or payload.get("response")
        or payload.get("message")
        or (payload.get("choices", [{}])[0].get("message", {}).get("content") if payload.get("choices") else None)
        or json.dumps(payload)
    )
    parsed = _extract_json_from_response(answer_text)
    if not parsed:
        return {"ok": False, "error": "parse_failed",
                "raw_snippet": answer_text[:1200]}

    return {
        "ok": True,
        "analysis": parsed,
        "_raw_answer_text": answer_text[:2500],  # debug temporário
        "aurora": {
            "schema": payload.get("schema"),
            "model": payload.get("model"),
            "read_only": payload.get("read_only"),
        },
    }


# ---------------------------------------------------------------------------
# Pricing via biblioteca ConstruPilot
# ---------------------------------------------------------------------------
_CATEGORY_ALIASES: dict[str, list[str]] = {
    "canalizacao": ["canalização", "canalizacao", "plomberie"],
    "eletricidade": ["eletricidade", "electricidade", "électricité"],
    "pladur": ["pladur", "gesso cartonado", "placoplâtre", "placoplatre"],
    "pintura": ["pintura", "peinture"],
    "ceramica": ["cerâmica", "ceramica", "azulejo", "carrelage"],
}


def _normalize(text: str) -> str:
    """Lower + strip diacritics simples."""
    t = (text or "").lower().strip()
    subs = {
        "á": "a", "à": "a", "â": "a", "ã": "a",
        "é": "e", "ê": "e",
        "í": "i", "î": "i",
        "ó": "o", "ô": "o", "õ": "o",
        "ú": "u", "û": "u",
        "ç": "c",
    }
    for k, v in subs.items():
        t = t.replace(k, v)
    return re.sub(r"\s+", " ", t)


async def price_works_from_library(
    works: list[dict[str, Any]],
    db,
    user_id: str,
) -> dict[str, Any]:
    """Cifra cada trabalho tentando `library_items` (biblioteca pessoal) e
    depois `shared_library_items` (PT-2026). Devolve resumo detalhado."""
    priced: list[dict[str, Any]] = []
    unpriced: list[dict[str, Any]] = []
    total_low = total_mid = total_high = 0.0

    for w in works:
        designation_raw = str(w.get("designation") or "").strip()
        designation = _normalize(designation_raw)
        qty = float(w.get("quantity") or 0)
        unit = (w.get("unit") or "un").strip()

        matched = None
        source = None
        # exact word tokens do designation (para regex parcial no Mongo)
        tokens = [t for t in re.split(r"[\s,;.]+", designation) if len(t) >= 4]

        # 1) library_items do utilizador (biblioteca pessoal)
        if designation and tokens:
            for tok in tokens[:3]:
                pattern = re.escape(tok)
                doc = await db.library_items.find_one({
                    "user_id": user_id,
                    "$or": [
                        {"designation": {"$regex": pattern, "$options": "i"}},
                        {"name": {"$regex": pattern, "$options": "i"}},
                    ],
                }, {"_id": 0})
                if doc:
                    matched = doc
                    source = "personal"
                    break

        # 2) fallback shared_library_items (PT-2026)
        if not matched and tokens:
            for tok in tokens[:3]:
                pattern = re.escape(tok)
                doc = await db.shared_library_items.find_one({
                    "$or": [
                        {"designation": {"$regex": pattern, "$options": "i"}},
                        {"name": {"$regex": pattern, "$options": "i"}},
                    ],
                }, {"_id": 0})
                if doc:
                    matched = doc
                    source = "shared"
                    break

        if not matched:
            unpriced.append({
                "designation": designation_raw,
                "category": w.get("category"),
                "unit": unit,
                "quantity": qty,
                "notes": w.get("notes"),
            })
            continue

        # calcular preços
        if source == "shared":
            price_low = float(matched.get("price_low") or matched.get("unit_price") or 0)
            price_mid = float(matched.get("price_mid") or matched.get("unit_price") or 0)
            price_high = float(matched.get("price_high") or matched.get("unit_price") or 0)
        else:
            unit_price = float(matched.get("unit_price") or matched.get("price_mid") or 0)
            price_low = price_mid = price_high = unit_price

        subtotal_low = qty * price_low
        subtotal_mid = qty * price_mid
        subtotal_high = qty * price_high
        total_low += subtotal_low
        total_mid += subtotal_mid
        total_high += subtotal_high

        priced.append({
            "designation": designation_raw,
            "category": w.get("category"),
            "unit": unit,
            "quantity": qty,
            "notes": w.get("notes"),
            "unit_price_low": round(price_low, 2),
            "unit_price_mid": round(price_mid, 2),
            "unit_price_high": round(price_high, 2),
            "subtotal_low": round(subtotal_low, 2),
            "subtotal_mid": round(subtotal_mid, 2),
            "subtotal_high": round(subtotal_high, 2),
            "matched_code": matched.get("code"),
            "matched_designation": matched.get("designation") or matched.get("name"),
            "source": source,
        })

    return {
        "priced_works": priced,
        "unpriced_works": unpriced,
        "totals": {
            "low": round(total_low, 2),
            "mid": round(total_mid, 2),
            "high": round(total_high, 2),
            "currency": "EUR",
        },
        "counts": {
            "priced": len(priced),
            "unpriced": len(unpriced),
            "total": len(priced) + len(unpriced),
        },
    }
