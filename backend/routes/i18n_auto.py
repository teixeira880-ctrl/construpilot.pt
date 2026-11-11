"""Tradução automática COMPLETA da interface (EN / FR / PT-PT / …).

Problema resolvido: o site estava escrito diretamente numa língua e só ~600 frases tinham
tradução manual — ao mudar de língua, o resto ficava por traduzir.

Funcionamento:
  1. ``frontend/scripts/i18n-manifest.cjs`` extrai do código TODOS os textos de interface
     (textos fixos + padrões com variáveis, ex. "Poupa {0} + IVA por ano") para
     ``backend/data/i18n_manifest.json``.
  2. Este módulo traduz o manifesto inteiro com Claude, por lotes, uma única vez por língua
     (cache MongoDB ``i18n_translations``) — em segundo plano, logo no arranque.
  3. ``GET /api/i18n/dict/{lang}`` devolve o dicionário completo; o ``DomTranslator`` do
     frontend aplica-o a todo o ecrã de uma vez.
  4. ``POST /api/i18n/translate`` traduz na hora um texto do manifesto ainda sem cache.

Segurança: só textos que constam do manifesto (gerado a partir do código-fonte) são enviados
ao modelo — nunca dados introduzidos por utilizadores (nomes de clientes, moradas…).
"""
# NB: sem `from __future__ import annotations` — com o decorador do slowapi, o FastAPI 0.115
# deixaria de reconhecer o corpo JSON (TranslateIn) e responderia 422.
import asyncio
import gzip
import hashlib
import json
import logging
import os
import re
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request, Response
from pydantic import BaseModel, Field

from core.db import db
from core.rate_limit import limiter

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/i18n", tags=["i18n"])

MANIFEST_PATHS = [
    Path(__file__).resolve().parent.parent / "data" / "i18n_manifest.json",
]
# Mensagens do backend mostradas no ecrã (erros, avisos): scripts/i18n_backend_manifest.py —
# ficheiro ao lado do manifesto do frontend.
EXTRA_MANIFEST_NAME = "i18n_manifest_backend.json"
COLL = "i18n_translations"
JOBS = "i18n_jobs"

LANG_NAMES = {
    "pt": "European Portuguese (Portugal, PT-PT — never Brazilian Portuguese: use 'equipa', 'utilizador', "
          "'ecrã', 'ficheiro', 'telemóvel', 'orçamento', 'IVA', 'obra')",
    "fr": "French (France — 'devis', 'HT', 'TVA', 'chantier', 'métré', 'artisan')",
    "en": "British/International English for the construction industry ('quote', 'VAT', 'site', "
          "'take-off', 'contractor')",
    "es": "Spanish (Spain)",
    "it": "Italian",
    "de": "German",
    "ar": "Modern Standard Arabic",
    "uk": "Ukrainian (українська, standard literary Ukrainian — never Russian; construction terms: "
          "'кошторис' for quote, 'рахунок' for invoice, 'ПДВ' for VAT, 'об'єкт'/'будівельний майданчик' for site, "
          "'обміри' for take-off, 'підрядник' for contractor, 'креслення' for plans)",
}
SUPPORTED = set(LANG_NAMES)

SYSTEM = (
    "You are the professional localisation engine of ConstruPilot, a construction-industry SaaS "
    "(quotes, quantity take-off, plan reading, site management, engineering studies). "
    "You translate user-interface strings. The source strings may be in Portuguese, French or another "
    "language. Rules:\n"
    "- Translate each string into the TARGET language only; if it is already in the target language, return it unchanged.\n"
    "- Keep placeholders like {0}, {1} EXACTLY (same numbers, same count), and keep emojis, symbols, "
    "numbers, units, currency, punctuation, leading/trailing characters (→ · : • … ✓) and capitalisation style.\n"
    "- Never translate brand/product names: ConstruPilot, Aurora, Solo, Professional, Business, Enterprise, "
    "Pro, Premium, BIM Studio, Stripe, Google, DPGF/CCTP/DCE acronyms stay as they are.\n"
    "- Keep it short and natural like real UI copy (buttons stay short). No explanations.\n"
    "- Answer ONLY with a JSON object mapping each input id to its translation."
)

BATCH_ITEMS = 60
BATCH_CHARS = 5000
CONCURRENCY = int(os.environ.get("I18N_CONCURRENCY", "4"))
MODEL = os.environ.get("I18N_MODEL", "claude-haiku-5-5")
PH_RE = re.compile(r"\{\d+\}")

# ── Manifesto ────────────────────────────────────────────────────────────────
_manifest: dict = {"version": "0", "exact": [], "patterns": []}
_manifest_mtime = 0.0
_exact_set: set[str] = set()
_pattern_set: set[str] = set()


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", s or "").strip()


def _read_manifest(p: Path) -> dict | None:
    try:
        data = json.loads(p.read_text("utf-8"))
    except OSError:
        return None
    except Exception as exc:  # noqa: BLE001
        logger.warning("i18n: manifesto ilegível %s: %s", p, exc)
        return None
    return {"version": str(data.get("version") or "0"),
            "exact": [_norm(x) for x in data.get("exact") or [] if isinstance(x, str) and _norm(x)],
            "patterns": [_norm(x) for x in data.get("patterns") or [] if isinstance(x, str) and _norm(x)]}


def load_manifest() -> dict:
    """Carrega (e recarrega se mudou) o manifesto do frontend + mensagens do backend."""
    global _manifest, _manifest_mtime, _exact_set, _pattern_set
    files = [p for p in MANIFEST_PATHS[:1] + [MANIFEST_PATHS[0].parent / EXTRA_MANIFEST_NAME] if p.exists()]
    try:
        mt = sum(p.stat().st_mtime for p in files)
    except OSError:
        return _manifest
    if files and mt != _manifest_mtime:
        parts = [m for m in (_read_manifest(p) for p in files) if m]
        if parts:
            exact = list(dict.fromkeys(x for m in parts for x in m["exact"]))
            ex_set = set(exact)
            pats = [x for x in dict.fromkeys(x for m in parts for x in m["patterns"]) if x not in ex_set]
            version = parts[0]["version"] if len(parts) == 1 else hashlib.sha1(
                "|".join(m["version"] for m in parts).encode()).hexdigest()[:12]
            _manifest = {"version": version, "exact": exact, "patterns": pats}
            _exact_set = ex_set
            _pattern_set = set(pats)
            _manifest_mtime = mt
    return _manifest


def _key(lang: str, src: str) -> str:
    return f"{lang}:{hashlib.sha1(src.encode('utf-8')).hexdigest()}"


# ── Modelo ───────────────────────────────────────────────────────────────────
async def _llm(system: str, prompt: str, max_tokens: int) -> str:
    """Claude direto (ANTHROPIC_API_KEY) e, na falta, a chave universal Emergent."""
    if os.environ.get("ANTHROPIC_API_KEY"):
        from anthropic import AsyncAnthropic
        client = AsyncAnthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
        msg = await client.messages.create(model=MODEL, max_tokens=max_tokens, system=system,
                                           messages=[{"role": "user", "content": prompt}])
        return "".join(getattr(b, "text", "") for b in msg.content or [] if getattr(b, "type", "") == "text")
    if os.environ.get("EMERGENT_LLM_KEY"):
        from emergentintegrations.llm.chat import LlmChat, UserMessage
        chat = LlmChat(api_key=os.environ["EMERGENT_LLM_KEY"], session_id=f"i18n-{time.time_ns()}",
                       system_message=system).with_model("anthropic", os.environ.get("I18N_MODEL_EMERGENT", "claude-sonnet-4-6"))
        out = await chat.send_message(UserMessage(text=prompt))
        return out if isinstance(out, str) else str(out)
    raise RuntimeError("Nenhuma chave de IA configurada (ANTHROPIC_API_KEY / EMERGENT_LLM_KEY)")


def _parse_json(text: str) -> dict:
    text = (text or "").strip()
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        return {}
    try:
        data = json.loads(m.group(0))
        return data if isinstance(data, dict) else {}
    except json.JSONDecodeError:
        return {}


def _valid(src: str, tgt: str) -> bool:
    if not isinstance(tgt, str) or not tgt.strip():
        return False
    if sorted(PH_RE.findall(src)) != sorted(PH_RE.findall(tgt)):
        return False
    return len(tgt) <= max(40, len(src) * 4)


async def translate_batch(lang: str, texts: list[str]) -> dict[str, str]:
    """Traduz um lote; devolve só as traduções válidas (placeholders preservados)."""
    if not texts:
        return {}
    items = {str(i): t for i, t in enumerate(texts)}
    prompt = (f"TARGET language: {LANG_NAMES[lang]}.\n"
              f"Translate the values of this JSON object (keys are ids):\n"
              f"{json.dumps(items, ensure_ascii=False)}")
    max_tokens = min(16000, 400 + sum(len(t) for t in texts))
    out: dict[str, str] = {}
    for attempt in range(2):
        try:
            data = _parse_json(await _llm(SYSTEM, prompt, max_tokens))
        except Exception as exc:  # noqa: BLE001
            logger.warning("i18n: lote %s falhou (%s): %s", lang, attempt, str(exc)[:200])
            await asyncio.sleep(2 + attempt * 5)
            continue
        for k, src in items.items():
            tgt = data.get(k)
            if isinstance(tgt, str) and _valid(src, tgt):
                out[src] = tgt.strip() if src == src.strip() else tgt
        if len(out) >= len(items) * 0.9:
            break
    return out


async def _store(lang: str, pairs: dict[str, str]) -> None:
    if not pairs:
        return
    from pymongo import UpdateOne
    now = datetime.now(timezone.utc)
    ops = [UpdateOne({"_id": _key(lang, s)},
                     {"$set": {"lang": lang, "src": s, "tgt": t, "model": MODEL, "updated_at": now}},
                     upsert=True) for s, t in pairs.items()]
    await db[COLL].bulk_write(ops, ordered=False)


async def cached(lang: str, srcs: list[str] | None = None) -> dict[str, str]:
    q: dict = {"lang": lang}
    if srcs is not None:
        q["_id"] = {"$in": [_key(lang, s) for s in srcs]}
    out: dict[str, str] = {}
    async for d in db[COLL].find(q, {"src": 1, "tgt": 1}):
        out[d["src"]] = d["tgt"]
    return out


def _batches(texts: list[str]):
    cur: list[str] = []
    size = 0
    for t in texts:
        if cur and (len(cur) >= BATCH_ITEMS or size + len(t) > BATCH_CHARS):
            yield cur
            cur, size = [], 0
        cur.append(t)
        size += len(t)
    if cur:
        yield cur


# ── Pré-tradução do manifesto inteiro ────────────────────────────────────────
async def _acquire(lang: str, version: str) -> bool:
    now = datetime.now(timezone.utc)
    try:
        res = await db[JOBS].find_one_and_update(
            {"_id": lang, "$or": [{"locked_until": {"$lt": now}}, {"locked_until": {"$exists": False}}]},
            {"$set": {"locked_until": now + timedelta(minutes=20), "version": version, "started_at": now}},
            upsert=True, return_document=True)
        return bool(res)
    except Exception:  # noqa: BLE001  (DuplicateKey: outro worker já tem o bloqueio)
        return False


async def warm(lang: str) -> dict:
    """Traduz tudo o que falta do manifesto para ``lang`` (idempotente, com bloqueio entre workers)."""
    if lang not in SUPPORTED:
        return {"lang": lang, "skipped": "unsupported"}
    m = load_manifest()
    if not (m["exact"] or m["patterns"]):
        return {"lang": lang, "skipped": "no_manifest"}
    if not await _acquire(lang, m["version"]):
        return {"lang": lang, "skipped": "running"}
    done = 0
    try:
        have = await cached(lang)
        todo = [s for s in m["exact"] + m["patterns"] if s not in have]
        sem = asyncio.Semaphore(CONCURRENCY)

        async def run(batch: list[str]):
            nonlocal done
            async with sem:
                res = await translate_batch(lang, batch)
                await _store(lang, res)
                done += len(res)
                await db[JOBS].update_one({"_id": lang}, {"$set": {
                    "locked_until": datetime.now(timezone.utc) + timedelta(minutes=20), "done": done, "todo": len(todo)}})

        await asyncio.gather(*(run(b) for b in _batches(todo)))
        logger.info("i18n: %s → %s/%s traduções novas", lang, done, len(todo))
        return {"lang": lang, "translated": done, "todo": len(todo)}
    finally:
        await db[JOBS].update_one({"_id": lang}, {"$set": {
            "locked_until": datetime.now(timezone.utc) - timedelta(seconds=5),
            "finished_at": datetime.now(timezone.utc), "done": done}})


# Línguas da interface (seletor): são sempre pré-traduzidas, mesmo que I18N_WARM_LANGS não as liste.
UI_LANGS = ("pt", "en", "fr", "uk")


def warm_langs() -> list[str]:
    raw = os.environ.get("I18N_WARM_LANGS", "en,fr,pt,uk")
    out = [x.strip() for x in raw.split(",") if x.strip() in SUPPORTED]
    return out + [x for x in UI_LANGS if x not in out]


async def warm_all_background() -> None:
    """Chamado no arranque: pré-traduz as línguas principais (não bloqueia o servidor)."""
    if os.environ.get("I18N_AUTOWARM", "1") == "0":
        return
    await asyncio.sleep(20)  # deixa o arranque terminar
    try:  # mensagens do backend: manifesto sempre alinhado com o código desta versão
        from scripts.i18n_backend_manifest import OUT, extract

        def _regen():
            m = extract()
            OUT.write_text(json.dumps(m, ensure_ascii=False, separators=(",", ":")), "utf-8")
            return m
        m = await asyncio.to_thread(_regen)
        logger.info("i18n: manifesto backend %s textos + %s padrões", len(m["exact"]), len(m["patterns"]))
    except Exception as exc:  # noqa: BLE001
        logger.warning("i18n: manifesto backend não regenerado (%s) — usa o ficheiro do repositório", exc)
    for lang in warm_langs():
        try:
            await warm(lang)
        except Exception as exc:  # noqa: BLE001
            logger.warning("i18n: pré-tradução %s falhou: %s", lang, exc)


# ── API ──────────────────────────────────────────────────────────────────────
_dict_cache: dict[str, tuple[float, dict]] = {}


async def build_dict(lang: str, background: BackgroundTasks | None = None) -> dict:
    m = load_manifest()
    hit = _dict_cache.get(lang)
    if hit and hit[0] > time.time() and hit[1].get("version") == m["version"]:
        return hit[1]
    have = await cached(lang)
    exact = {s: have[s] for s in m["exact"] if s in have and have[s] != s}
    patterns = [[p, have[p]] for p in m["patterns"] if p in have and have[p] != p]
    total = len(m["exact"]) + len(m["patterns"])
    covered = sum(1 for s in m["exact"] if s in have) + sum(1 for p in m["patterns"] if p in have)
    complete = covered >= total * 0.98
    payload = {"lang": lang, "version": m["version"], "complete": complete,
               "coverage": round(covered / total, 4) if total else 1.0,
               "exact": exact, "patterns": patterns}
    _dict_cache[lang] = (time.time() + (300 if complete else 30), payload)
    if not complete and background is not None:
        background.add_task(warm, lang)
    return payload


@router.get("/dict/{lang}")
async def get_dict(lang: str, request: Request, background: BackgroundTasks) -> Response:
    """Dicionário completo da interface para ``lang`` (textos fixos + padrões), comprimido."""
    lang = (lang or "").lower()[:5]
    if lang not in SUPPORTED:
        raise HTTPException(404, "Língua não suportada")
    payload = await build_dict(lang, background)
    body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    headers = {"Cache-Control": "public, max-age=300" if payload["complete"] else "no-store",
               "Vary": "Accept-Encoding"}
    if "gzip" in (request.headers.get("accept-encoding") or "").lower():
        body = gzip.compress(body, compresslevel=6)
        headers["Content-Encoding"] = "gzip"
    return Response(content=body, media_type="application/json", headers=headers, background=background)


class TranslateIn(BaseModel):
    lang: str
    texts: list[str] = Field(default_factory=list, max_length=80)


@router.post("/translate")
@limiter.limit("30/minute")
async def translate_now(request: Request, response: Response, body: TranslateIn) -> dict:
    """Tradução imediata de textos do manifesto ainda sem cache (ex.: página nova)."""
    lang = (body.lang or "").lower()[:5]
    if lang not in SUPPORTED:
        raise HTTPException(400, "Língua não suportada")
    load_manifest()
    wanted = []
    for t in body.texts[:80]:
        s = _norm(t)[:3000]
        if s and (s in _exact_set or s in _pattern_set) and s not in wanted:
            wanted.append(s)
    if not wanted:
        return {"lang": lang, "translations": {}}
    have = await cached(lang, wanted)
    missing = [s for s in wanted if s not in have]
    for b in _batches(missing):
        res = await translate_batch(lang, b)
        await _store(lang, res)
        have.update(res)
    _dict_cache.pop(lang, None)
    return {"lang": lang, "translations": {s: have[s] for s in wanted if s in have}}


@router.get("/status")
async def status() -> dict:
    m = load_manifest()
    total = len(m["exact"]) + len(m["patterns"])
    out = {"version": m["version"], "strings": total, "langs": {}}
    for lang in sorted(SUPPORTED):
        n = await db[COLL].count_documents({"lang": lang})
        job = await db[JOBS].find_one({"_id": lang}, {"_id": 0, "done": 1, "todo": 1, "finished_at": 1}) or {}
        out["langs"][lang] = {"cached": n, **{k: (v.isoformat() if hasattr(v, "isoformat") else v) for k, v in job.items()}}
    return out
