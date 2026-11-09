"""Traduction du CONTENU d'un devis / facture (désignations, descriptions, lots, titre, notes)
pour les comptes qui exigent leurs documents dans d'autres langues (champ users.doc_langs,
ex. CLT Rezult : ["en", "uk"]).

- Les montants, quantités, numéros et le client ne sont JAMAIS envoyés ni modifiés.
- Résultat mis en cache sur le document (pro_documents.translations.<lang>) avec l'empreinte
  du contenu source : une seule traduction tant que le devis ne change pas.
- En cas d'échec IA, le PDF sort quand même (contenu d'origine, libellés traduits).
"""
from __future__ import annotations

import copy
import hashlib
import json
import logging
import re

logger = logging.getLogger("doc_translate")

LANG_NAMES = {"en": "English", "uk": "Ukrainian (українська)", "fr": "French", "pt": "European Portuguese"}
LINE_KEYS = ("designation", "description", "category", "unit")


def _payload(doc: dict) -> dict:
    out = {"title": doc.get("title") or "", "notes": doc.get("notes") or "",
           "project_duration": doc.get("project_duration") or "",
           "lines": [{k: (ln.get(k) or "") for k in LINE_KEYS} for ln in (doc.get("lines") or [])],
           "payment_schedule": [{"label": (p.get("label") or "")} for p in (doc.get("payment_schedule") or [])
                                if isinstance(p, dict)]}
    return out


def _hash(payload: dict, lang: str) -> str:
    return hashlib.sha256((lang + json.dumps(payload, ensure_ascii=False, sort_keys=True)).encode()).hexdigest()[:20]


def _apply(doc: dict, tr: dict) -> dict:
    d = copy.deepcopy(doc)
    for k in ("title", "notes", "project_duration"):
        if tr.get(k):
            d[k] = tr[k]
    tl = tr.get("lines") or []
    for ln, t in zip(d.get("lines") or [], tl):
        for k in LINE_KEYS:
            if isinstance(t, dict) and t.get(k) and ln.get(k):
                ln[k] = t[k]
    sched = [p for p in (d.get("payment_schedule") or []) if isinstance(p, dict)]
    for p, t in zip(sched, tr.get("payment_schedule") or []):
        if isinstance(t, dict) and t.get("label") and p.get("label"):
            p["label"] = t["label"]
    return d


def _parse_json(text: str) -> dict | None:
    m = re.search(r"\{.*\}", text or "", re.S)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except ValueError:
        return None


async def translate_doc(db, doc: dict, lang: str) -> dict:
    """Renvoie une COPIE du document avec le contenu traduit dans `lang` (cache en base)."""
    if lang not in LANG_NAMES:
        return doc
    payload = _payload(doc)
    if not any([payload["title"], payload["notes"], payload["lines"]]):
        return doc
    h = _hash(payload, lang)
    cached = ((doc.get("translations") or {}).get(lang) or {})
    if cached.get("hash") == h and cached.get("data"):
        return _apply(doc, cached["data"])
    system = (
        f"You are a professional construction translator. Translate every non-empty string value of the JSON "
        f"into {LANG_NAMES[lang]}, using precise building-industry terminology (CLT, cross-laminated timber, "
        "structural elements). Values of the \"unit\" key must stay SHORT abbreviations (max 6 characters: m², m³, m, pcs / шт., "
        "lump sum → LS / компл., h / год.). If a value is already in "
        "the target language keep it. Keep numbers, dimensions, product codes and brand names unchanged. "
        "Return ONLY the JSON with the exact same structure, same keys and same number of items.")
    try:
        from engines.ai import _complete
        out = await _complete(system, json.dumps(payload, ensure_ascii=False), feature="doc_translate")
        data = _parse_json(out)
        if not data or len(data.get("lines") or []) != len(payload["lines"]):
            raise ValueError("structure de traduction invalide")
    except Exception as exc:  # noqa: BLE001
        logger.warning("Traduction %s du document %s impossible : %s", lang, doc.get("doc_id"), exc)
        return doc
    try:
        await db.pro_documents.update_one({"doc_id": doc.get("doc_id")},
                                          {"$set": {f"translations.{lang}": {"hash": h, "data": data}}})
    except Exception:  # noqa: BLE001
        pass
    return _apply(doc, data)


async def localize_for_owner(db, doc: dict, owner_id: str | None) -> tuple[dict, str | None]:
    """(document traduit, langue) si le propriétaire impose ses langues (users.doc_langs), sinon (doc, None)."""
    if not owner_id:
        return doc, None
    u = await db.users.find_one({"user_id": owner_id}, {"_id": 0, "doc_langs": 1}) or {}
    langs = [x for x in (u.get("doc_langs") or []) if x in ("fr", "pt", "en", "uk")]
    if not langs:
        return doc, None
    return await translate_doc(db, doc, langs[0]), langs[0]
