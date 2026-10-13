"""Apprentissage IA global — exemples de référence validés (few-shot).

Un administrateur (ex. compte CM Rénov) ajoute et valide des exemples : devis réussis,
analyses de problèmes, consignes de style. Les exemples APPROUVÉS sont injectés comme
références « few-shot » dans les prompts système de TOUS les modules IA (devis, analyses,
coach, plan), pour que l'assistant produise au même niveau de détail et de rigueur.

Les prix et quantités restent déterministes (moteur de calcul) : les exemples guident le
STYLE, la STRUCTURE et la MÉTHODE, jamais les chiffres.
"""
import asyncio
import logging
import secrets
import time
from datetime import datetime, timezone

from core.db import db

logger = logging.getLogger(__name__)

COLLECTION = "ai_learning_examples"

# Portées d'un exemple. "global" s'applique à tous les modules.
SCOPES = ["global", "devis", "analyse", "coach", "plan"]

# feature (passée aux appels IA) -> groupe de portée
_FEATURE_GROUP = {
    "quote_describe": "devis", "quote_from_text": "devis", "cctp_read": "devis",
    "cctp_ocr": "devis", "doc_import": "devis", "dpgf": "devis", "assistant": "devis",
    "smart_project": "analyse", "photo_analyse": "analyse", "reno_extract": "analyse",
    "rebar": "analyse", "waterproofing": "analyse", "roofing": "analyse", "vrd": "analyse",
    "doc_compare": "analyse", "structuro": "analyse",
    "coach": "coach",
    "plan_command": "plan",
}

MAX_EXAMPLES = 6
_CTX_MAX = 1500
_CONTENT_MAX = 3000

# Cache mémoire léger (TTL court) ; invalidé à chaque écriture.
_CACHE: dict[str, tuple[float, str]] = {}
_TTL_S = 60.0


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _group_for(feature: str | None) -> str | None:
    if not feature:
        return None
    return _FEATURE_GROUP.get(feature)


def _invalidate() -> None:
    _CACHE.clear()


async def _bump_usage(ids: list[str]) -> None:
    """Incrémente le compteur d'usage des exemples injectés (métrique panneau admin)."""
    try:
        await db[COLLECTION].update_many(
            {"id": {"$in": ids}},
            {"$inc": {"used_count": 1}, "$set": {"last_used_at": _now()}})
    except Exception:  # noqa: BLE001
        pass


async def learning_block_for_scope(scope: str) -> str:
    """Bloc tel qu'il sera injecté pour une portée donnée (aperçu admin, sans incrément d'usage)."""
    feature = {"devis": "quote_from_text", "analyse": "smart_project",
               "coach": "coach", "plan": "plan_command"}.get(scope)
    scopes = ["global"] + ([scope] if scope and scope != "global" else [])
    rows = await db[COLLECTION].find(
        {"approved": True, "scope": {"$in": list(dict.fromkeys(scopes))}}, {"_id": 0}
    ).sort("created_at", -1).to_list(MAX_EXAMPLES)
    if not rows:
        return ""
    return _format_block(rows)


async def learning_block(feature: str | None = None) -> str:
    """Bloc texte (à ajouter au system prompt) des exemples validés pertinents.

    Inclut toujours les exemples « global » + ceux du groupe de la feature.
    Chaîne vide si aucun exemple approuvé.
    """
    group = _group_for(feature)
    cache_key = group or "__global_only__"
    hit = _CACHE.get(cache_key)
    if hit and (time.monotonic() - hit[0]) < _TTL_S:
        return hit[1]

    scopes = ["global"] + ([group] if group else [])
    try:
        rows = await db[COLLECTION].find(
            {"approved": True, "scope": {"$in": scopes}}, {"_id": 0}
        ).sort("created_at", -1).to_list(MAX_EXAMPLES)
    except Exception as e:  # noqa: BLE001
        logger.warning("learning_block fetch failed: %s", e)
        return ""

    if not rows:
        _CACHE[cache_key] = (time.monotonic(), "")
        return ""

    # Métrique d'usage : incrémente (fire-and-forget) le compteur des exemples réellement injectés.
    ids = [r.get("id") for r in rows if r.get("id")]
    if ids:
        try:
            asyncio.create_task(_bump_usage(ids))
        except RuntimeError:
            pass

    parts = _format_block(rows)
    text = parts
    _CACHE[cache_key] = (time.monotonic(), text)
    return text


def _format_block(rows: list[dict]) -> str:
    parts = [
        "\n\n=== EXEMPLES DE RÉFÉRENCE ConstruPilot (validés par un expert métier CM Rénov) ===",
        "Inspire-toi FORTEMENT du style, de la structure, du vocabulaire et du niveau de détail "
        "de ces exemples pour construire ta réponse (rédaction d'un devis, analyse d'un problème, "
        "méthode). Ils montrent le standard de qualité attendu. "
        "N'invente JAMAIS de prix ni de quantité à partir de ces exemples : les chiffres définitifs "
        "viennent toujours du moteur de calcul / de la bibliothèque de prix.",
    ]
    for i, r in enumerate(rows, 1):
        title = str(r.get("title") or "").strip()[:120]
        ctx = str(r.get("context") or "").strip()[:_CTX_MAX]
        content = str(r.get("content") or "").strip()[:_CONTENT_MAX]
        block = [f"\n— Exemple {i}" + (f" : {title}" if title else "")]
        if ctx:
            block.append(f"Situation / demande : {ctx}")
        block.append("Réponse / méthode de référence :\n" + content)
        parts.append("\n".join(block))
    return "\n".join(parts) + "\n=== FIN DES EXEMPLES DE RÉFÉRENCE ===\n"


async def list_examples() -> list[dict]:
    return await db[COLLECTION].find({}, {"_id": 0}).sort("created_at", -1).to_list(500)


async def create_example(data: dict, created_by: str | None) -> dict:
    doc = {
        "id": "learn_" + secrets.token_hex(6),
        "scope": data["scope"] if data.get("scope") in SCOPES else "global",
        "title": str(data.get("title") or "").strip()[:120],
        "context": str(data.get("context") or "").strip()[:4000],
        "content": str(data.get("content") or "").strip()[:8000],
        "approved": bool(data.get("approved", True)),
        "used_count": 0,
        "created_by": created_by,
        "created_at": _now(),
        "updated_at": _now(),
    }
    await db[COLLECTION].insert_one({**doc})
    _invalidate()
    return doc


async def update_example(example_id: str, data: dict) -> dict | None:
    patch: dict = {"updated_at": _now()}
    if data.get("scope") in SCOPES:
        patch["scope"] = data["scope"]
    for k in ("title", "context", "content"):
        if k in data and data[k] is not None:
            patch[k] = str(data[k]).strip()[: (120 if k == "title" else 8000)]
    if "approved" in data:
        patch["approved"] = bool(data["approved"])
    res = await db[COLLECTION].find_one_and_update(
        {"id": example_id}, {"$set": patch},
        projection={"_id": 0}, return_document=True)
    _invalidate()
    return res


async def delete_example(example_id: str) -> bool:
    r = await db[COLLECTION].delete_one({"id": example_id})
    _invalidate()
    return r.deleted_count > 0



async def create_many(items: list[dict], scope: str, created_by: str | None) -> list[dict]:
    """Création en lot (paste multi-exemples / import fichier). Ignore les contenus vides."""
    scope = scope if scope in SCOPES else "global"
    created: list[dict] = []
    for it in items[:200]:
        content = str((it or {}).get("content") or "").strip()
        if not content:
            continue
        created.append(await create_example(
            {"scope": scope, "title": (it or {}).get("title") or "",
             "context": (it or {}).get("context") or "", "content": content,
             "approved": (it or {}).get("approved", True)},
            created_by))
    return created


def extract_file_text(data: bytes, filename: str) -> str:
    """Texte brut d'un fichier importé (PDF, Excel, CSV, Word, TXT) pour en faire un exemple."""
    ext = (filename.rsplit(".", 1)[-1] if "." in filename else "").lower()
    if ext == "pdf":
        try:
            import fitz  # PyMuPDF
            doc = fitz.open(stream=data, filetype="pdf")
            text = "\n".join(page.get_text("text") for page in doc)
            doc.close()
            return text[:8000]
        except Exception as exc:  # noqa: BLE001
            raise ValueError("PDF illisible") from exc
    if ext in ("xlsx", "xls", "csv", "docx", "txt"):
        from engines.office_text import extract_office_text
        return extract_office_text(data, ext)[:8000]
    raise ValueError(f"Format .{ext or '?'} non pris en charge (PDF, Excel, CSV, Word, TXT)")



def document_to_text(doc: dict) -> str:
    """Formate les lignes d'un devis signé en texte lisible pour servir d'exemple IA."""
    lines = doc.get("lines") or []
    out: list[str] = []
    for l in lines:
        if (l or {}).get("kind") in ("section", "subtotal", "page_break"):
            t = str((l or {}).get("title") or "").strip()
            if t:
                out.append(f"\n## {t}")
            continue
        d = str((l or {}).get("designation") or "").strip()
        if not d:
            continue
        q = (l or {}).get("qty") or 0
        u = (l or {}).get("unit") or "u"
        row = f"- {d} ({q} {u})"
        desc = str((l or {}).get("description") or "").strip()
        if desc:
            row += "\n    " + desc.replace("\n", "\n    ")
        out.append(row)
    return "\n".join(out).strip()


async def example_doc_ids() -> list[str]:
    rows = await db[COLLECTION].find(
        {"source_doc_id": {"$ne": None}}, {"_id": 0, "source_doc_id": 1}).to_list(2000)
    return [r["source_doc_id"] for r in rows if r.get("source_doc_id")]


async def create_from_document(doc: dict, created_by: str | None) -> tuple[dict | None, bool]:
    """Crée un exemple (portée devis) depuis un devis signé. Retourne (exemple, already)."""
    doc_id = doc.get("doc_id")
    existing = await db[COLLECTION].find_one({"source_doc_id": doc_id}, {"_id": 0})
    if existing:
        return existing, True
    content = document_to_text(doc)
    if not content:
        return None, False
    client = ""
    c = doc.get("client") or {}
    if isinstance(c, dict):
        client = (c.get("name") or "").strip()
    ex = await create_example(
        {"scope": "devis",
         "title": (doc.get("title") or doc.get("number") or "Devis signé")[:120],
         "context": f"Devis signé{(' — client ' + client) if client else ''}.",
         "content": content, "approved": True},
        created_by)
    await db[COLLECTION].update_one({"id": ex["id"]}, {"$set": {"source_doc_id": doc_id}})
    ex["source_doc_id"] = doc_id
    _invalidate()
    return ex, False
