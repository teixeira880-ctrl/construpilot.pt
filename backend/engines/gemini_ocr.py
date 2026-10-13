"""Lecture documentaire par IA (OCR / vision) — factures, CCTP, devis scannés.

Règle d'or : l'IA LIT uniquement (OCR + relevé des champs tels qu'affichés).
Elle ne calcule JAMAIS (ni somme, ni TVA, ni conversion) : les montants sont
renvoyés sous forme de chaînes, exactement comme imprimés. Les contrôles
arithmétiques restent 100 % déterministes dans `doc_intel`.

Chaîne de disponibilité (zéro coupure) :
  1. PRINCIPAL  : clé Gemini de l'utilisateur (GEMINI_API_KEY) via google-genai.
  2. REPLI      : clé universelle Emergent (EMERGENT_LLM_KEY) via emergentintegrations.
Si le principal échoue (absent, quota, erreur), on bascule automatiquement sur
le repli. Si tout échoue, on renvoie une erreur lisible (jamais de données inventées).
"""
from __future__ import annotations

import asyncio
import base64
import json
import os

from dotenv import load_dotenv

load_dotenv()

GEMINI_MODEL = os.environ.get("GEMINI_MODEL") or "gemini-3.6-flash"
FALLBACK_MODEL = os.environ.get("GEMINI_FALLBACK_MODEL") or "gemini-3.5-flash"


def _env(name: str) -> str:
    """Lecture à chaud (robuste au rechargement / mise à jour de clé)."""
    return os.environ.get(name) or ""


IMAGE_MIMES = {"image/jpeg", "image/png", "image/webp"}
MAX_FALLBACK_PAGES = 12  # limite de pages rendues en images pour le repli

PROMPT = (
    "És um OCR documental para a construção (faturas, orçamentos, cadernos de encargos, mapas de quantidades, certificados energéticos). Lê o documento fornecido e RESTITUI apenas o que é visível. PROIBIÇÃO ABSOLUTA de calcular, somar, converter, arredondar ou deduzir qualquer valor: copia os números EXATAMENTE como apresentados (cadeias). Se um campo estiver ausente ou ilegível, põe null e acrescenta um aviso curto. Nunca inventes um valor. Responde respeitando o esquema JSON pedido. Em \'pages\', põe o texto integral de cada página (conserva a ordem das linhas e as tabelas em forma de texto). Em \'document\' e \'line_items\', regista os campos do cabeçalho e as linhas do documento se se tratar de uma fatura/orçamento/mapa de quantidades."
)

# Schéma de sortie (identique entre les deux moteurs).
_SCHEMA_HINT = {
    "pages": [{"page": "int", "text": "str"}],
    "document": {
        "document_type": "str|null", "supplier_name": "str|null",
        "customer_name": "str|null", "doc_number": "str|null",
        "issue_date": "str|null", "currency": "str|null",
        "subtotal": "str|null", "tax": "str|null", "total": "str|null",
    },
    "line_items": [{"description": "str|null", "quantity": "str|null",
                    "unit": "str|null", "unit_price": "str|null", "amount": "str|null"}],
    "warnings": ["str"],
}


def available() -> bool:
    return bool(_env("GEMINI_API_KEY")) or bool(_env("EMERGENT_LLM_KEY"))


def _normalize(data: dict, engine: str, model: str) -> dict:
    """Normalise la sortie d'un moteur vers la forme interne attendue."""
    data = data or {}
    pages = []
    for i, p in enumerate(data.get("pages") or []):
        if isinstance(p, dict):
            pages.append({"page": int(p.get("page") or i + 1), "text": (p.get("text") or "").strip()})
        elif isinstance(p, str):
            pages.append({"page": i + 1, "text": p.strip()})
    doc = data.get("document") or {}
    items = []
    for it in data.get("line_items") or []:
        if isinstance(it, dict):
            items.append({k: (it.get(k) if it.get(k) not in ("", None) else None)
                          for k in ("description", "quantity", "unit", "unit_price", "amount")})
    warnings = [str(w) for w in (data.get("warnings") or []) if w]
    return {"engine": engine, "model": model, "pages": pages,
            "document": doc, "line_items": items, "warnings": warnings}


def _parse_json_text(text: str) -> dict:
    """Extrait un objet JSON d'une réponse éventuellement entourée de ```json."""
    s = (text or "").strip()
    if s.startswith("```"):
        s = s.split("```", 2)[1] if s.count("```") >= 2 else s.strip("`")
        if s.lstrip().lower().startswith("json"):
            s = s.lstrip()[4:]
    s = s.strip()
    start, end = s.find("{"), s.rfind("}")
    if start != -1 and end != -1 and end > start:
        s = s[start:end + 1]
    return json.loads(s)


# ---------------------------------------------------------------------------
# PRINCIPAL — clé Gemini de l'utilisateur (google-genai)
# ---------------------------------------------------------------------------

def _primary_sync(raw: bytes, mime: str) -> dict:
    from google import genai
    from google.genai import types
    from google.genai.errors import ServerError

    client = genai.Client(api_key=_env("GEMINI_API_KEY"))
    # Liste de modèles Flash : le modèle configuré d'abord, puis repli sur 503/surcharge.
    candidates = [GEMINI_MODEL] + [m for m in ("gemini-3.6-flash", "gemini-3.5-flash")
                                   if m != GEMINI_MODEL]
    last_exc: Exception | None = None
    for model in candidates:
        try:
            resp = client.models.generate_content(
                model=model,
                contents=[types.Part.from_bytes(data=raw, mime_type=mime), PROMPT,
                          "Esquema esperado (exemplo de estrutura): " + json.dumps(_SCHEMA_HINT)],
                config=types.GenerateContentConfig(response_mime_type="application/json", temperature=0),
            )
            parsed = getattr(resp, "parsed", None)
            data = parsed if isinstance(parsed, dict) else _parse_json_text(getattr(resp, "text", "") or "")
            return {"_data": data, "_model": model}
        except ServerError as exc:  # 503 surcharge → on tente le modèle suivant
            last_exc = exc
            continue
    raise last_exc or RuntimeError("Nenhum modelo Gemini disponível")


async def _primary(raw: bytes, mime: str) -> dict:
    out = await asyncio.to_thread(_primary_sync, raw, mime)
    return _normalize(out["_data"], "gemini-user", out["_model"])


# ---------------------------------------------------------------------------
# REPLI — clé universelle Emergent (emergentintegrations), images uniquement
# ---------------------------------------------------------------------------

def _pdf_to_images(raw: bytes) -> list[bytes]:
    import fitz
    out: list[bytes] = []
    doc = fitz.open(stream=raw, filetype="pdf")
    try:
        for pno in range(min(doc.page_count, MAX_FALLBACK_PAGES)):
            pix = doc[pno].get_pixmap(dpi=170)
            out.append(pix.tobytes("png"))
    finally:
        doc.close()
    return out


async def _fallback_one(img: bytes, page_no: int) -> dict:
    """Lit UNE page/image via la clé Emergent et renvoie {text, document?, line_items?}."""
    from emergentintegrations.llm.chat import LlmChat, UserMessage, ImageContent

    chat = LlmChat(
        api_key=_env("EMERGENT_LLM_KEY"),
        session_id=f"ocr-p{page_no}",
        system_message=PROMPT,
    ).with_model("gemini", FALLBACK_MODEL).with_params(max_tokens=8000)
    msg = UserMessage(
        text=("Lê esta página e devolve APENAS um objeto JSON (nenhum texto à volta): {\"text\": \"<texto integral da página, linhas conservadas>\", \"document\": {\"document_type\":null,\"supplier_name\":null,\"customer_name\":null,\"doc_number\":null,\"issue_date\":null,\"currency\":null,\"subtotal\":null,\"tax\":null,\"total\":null}, \"line_items\": [{\"description\":null,\"quantity\":null,\"unit\":null,\"unit_price\":null,\"amount\":null}]}"),
        file_contents=[ImageContent(image_base64=base64.b64encode(img).decode("ascii"))],
    )
    text = await chat.send_message(msg)
    try:
        data = _parse_json_text(text)
    except Exception:
        data = {"text": (text or "").strip()}
    return data


async def _fallback(raw: bytes, mime: str, filename: str) -> dict:
    if mime == "application/pdf":
        images = _pdf_to_images(raw)
    else:
        images = [raw]
    if not images:
        raise RuntimeError("Nenhuma página utilizável para o recurso")

    pages, line_items = [], []
    document: dict = {}
    for i, img in enumerate(images):
        one = await _fallback_one(img, i + 1)
        pages.append({"page": i + 1, "text": (one.get("text") or "").strip()})
        for it in one.get("line_items") or []:
            if isinstance(it, dict) and any(it.get(k) for k in it):
                line_items.append(it)
        for k, v in (one.get("document") or {}).items():
            if v and not document.get(k):
                document[k] = v
    data = {"pages": pages, "document": document, "line_items": line_items, "warnings": []}
    return _normalize(data, "emergent-fallback", FALLBACK_MODEL)


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------

async def ocr(raw: bytes, mime: str, filename: str = "") -> dict:
    """Lit un PDF ou une image et renvoie texte + champs. Bascule auto si besoin."""
    errors: list[str] = []
    if _env("GEMINI_API_KEY"):
        try:
            res = await _primary(raw, mime)
            if res.get("pages"):
                return res
            errors.append("Gemini (chave pessoal): nenhuma página lida")
        except Exception as exc:  # pragma: no cover - dépend du réseau
            errors.append(f'Gemini (chave pessoal) indisponível: {type(exc).__name__}')
    if _env("EMERGENT_LLM_KEY"):
        try:
            res = await _fallback(raw, mime, filename)
            if errors:
                res.setdefault("warnings", []).insert(0, "Recurso IA utilizado — " + errors[0])
            return res
        except Exception as exc:  # pragma: no cover
            errors.append(f'Recurso Emergent indisponível: {type(exc).__name__}')
    raise RuntimeError("; ".join(errors) or "Nenhum motor OCR configurado")
