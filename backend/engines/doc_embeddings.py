"""Embeddings sémantiques (complément du dictionnaire lexical déterministe).

But : rapprocher des libellés BTP FR/PT au-delà des mots-clés (synonymes, tournures,
abréviations) dans le rapprochement CCTP ↔ devis. Les embeddings NE remplacent PAS
la correspondance lexicale : ils ne font qu'AUGMENTER le rappel. Une équivalence
n'est jamais affirmée sur la seule proximité vectorielle (score « à vérifier »).

- Modèle : OpenAI text-embedding-3-small (1536 dims), via OPENAI_API_KEY.
  (La clé universelle Emergent n'expose aucun modèle d'embedding — vérifié.)
- Stockage : vecteurs mis en cache dans MongoDB (collection doc_embeddings),
  clé = sha256(modèle + texte normalisé). Similarité cosinus calculée en app
  (pas de pgvector — MongoDB only).
- Meilleur effort : toute erreur/API absente renvoie None → le moteur déterministe
  continue sans embeddings (jamais bloquant).
"""
from __future__ import annotations

import hashlib
import math
import os

from core.db import db

MODEL = "text-embedding-3-small"
_MAX_BATCH = 100


def _norm(text: str) -> str:
    return " ".join((text or "").lower().split())[:800]


def _key(text: str) -> str:
    return hashlib.sha256((MODEL + "|" + _norm(text)).encode()).hexdigest()


def available() -> bool:
    return bool(os.environ.get("OPENAI_API_KEY"))


def _client():
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        return None
    try:
        from openai import OpenAI
        return OpenAI(api_key=api_key)
    except Exception:
        return None


def cosine(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if not na or not nb:
        return 0.0
    return sum(x * y for x, y in zip(a, b)) / (na * nb)


async def get_or_embed(texts: list[str]) -> dict[str, list[float]]:
    """Renvoie {texte: vecteur} pour les textes fournis (cache Mongo + appel API
    seulement pour les manquants). Meilleur effort : renvoie {} si indisponible."""
    uniq = []
    seen = set()
    for t in texts:
        t = (t or "").strip()
        if t and t not in seen:
            seen.add(t)
            uniq.append(t)
    if not uniq:
        return {}

    out: dict[str, list[float]] = {}
    key_by_text = {t: _key(t) for t in uniq}
    keys = list(key_by_text.values())

    # 1) Cache Mongo
    cached: dict[str, list[float]] = {}
    try:
        async for d in db.doc_embeddings.find({"_id": {"$in": keys}}):
            cached[d["_id"]] = d.get("vector") or []
    except Exception:
        cached = {}
    for t, k in key_by_text.items():
        if cached.get(k):
            out[t] = cached[k]

    missing = [t for t in uniq if t not in out]
    if not missing:
        return out

    client = _client()
    if client is None:
        return out  # meilleur effort : uniquement ce qui est en cache

    # 2) Appels API par lots + upsert cache
    for i in range(0, len(missing), _MAX_BATCH):
        chunk = missing[i:i + _MAX_BATCH]
        try:
            resp = client.embeddings.create(
                model=MODEL, input=[_norm(t) for t in chunk], encoding_format="float")
            data = sorted(resp.data, key=lambda x: x.index)
        except Exception:
            break  # meilleur effort : on garde ce qu'on a
        for t, item in zip(chunk, data):
            vec = list(item.embedding)
            out[t] = vec
            try:
                await db.doc_embeddings.update_one(
                    {"_id": key_by_text[t]},
                    {"$set": {"vector": vec, "model": MODEL, "text": _norm(t)}},
                    upsert=True)
            except Exception:
                pass
    return out
