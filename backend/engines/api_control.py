"""Admin → IA → «Todas as IA e API»: ligar/desligar cada IA / API externa do ConstruPilot e ver o crédito de cada uma.

Desligar uma API = a chave deixa de existir para o processo (os.environ), exatamente como se não estivesse configurada:
todo o código já trata a chave ausente (recurso ao fornecedor seguinte ou função indisponível). A chave NÃO é apagada:
fica guardada em memória e volta ao religar. O estado é guardado em app_settings «api_control» e reaplicado no arranque
e de 30 em 30 s (vários workers).

A chave universal Emergent não pode ser desligada: serve também para o armazenamento dos ficheiros."""
from __future__ import annotations

import asyncio
import logging
import os
import time
from datetime import datetime, timezone

import httpx

log = logging.getLogger(__name__)

_SETTINGS_ID = "api_control"
_STASH: dict[str, str] = {}          # chaves retiradas do ambiente por estarem desligadas
_DISABLED: set[str] = set()
_SYNC: dict = {"task": None, "at": 0.0}
_BAL_CACHE: dict[str, tuple[float, dict]] = {}

# id → descrição. «env»: variáveis da chave (todas retiradas ao desligar). «uses»: onde é usada no ConstruPilot.
PROVIDERS: dict[str, dict] = {
    "emergent": {"label": "Emergent — chave LLM universal", "cat": "IA texto e visão",
                 "env": ["EMERGENT_LLM_KEY"], "locked": True,
                 "uses": "Recurso universal de todas as IA (GPT, Claude, Gemini) e armazenamento de ficheiros",
                 "console": "https://app.emergent.sh/"},
    "openai": {"label": "OpenAI (chave da empresa)", "cat": "IA texto e visão", "env": ["OPENAI_API_KEY"],
               "uses": "Estudos (plantas, cotas, medições, orçamentos), chat GPT", "provider": "openai",
               "console": "https://platform.openai.com/settings/organization/billing"},
    "anthropic": {"label": "Anthropic Claude", "cat": "IA texto e visão", "env": ["ANTHROPIC_API_KEY"],
                  "uses": "Assistente Claude, leitura de documentos (desligar = Claude não é usado, nem pela chave Emergent)", "provider": "anthropic",
                  "console": "https://console.anthropic.com/settings/billing"},
    "gemini": {"label": "Google Gemini", "cat": "IA texto e visão", "env": ["GEMINI_API_KEY", "GOOGLE_GEMINI_API_KEY"],
               "uses": "Assistente Construção (plantas, medições), recurso do chat (desligar = Gemini não é usado, nem pela chave Emergent)", "provider": "gemini",
               "console": "https://aistudio.google.com/usage"},
    "perplexity": {"label": "Perplexity", "cat": "Pesquisa web", "env": ["PERPLEXITY_API_KEY"],
                   "uses": "Pesquisa de preços, normas e fornecedores", "console": "https://www.perplexity.ai/settings/api"},
    "tavily": {"label": "Tavily", "cat": "Pesquisa web", "env": ["TAVILY_API_KEY"],
               "uses": "Pesquisa web do Assistente", "console": "https://app.tavily.com/"},
    "apify": {"label": "Apify", "cat": "Pesquisa web", "env": ["APIFY_API_TOKEN"],
              "uses": "Recolha de dados (prospeção, preços)", "console": "https://console.apify.com/billing"},
    "kling": {"label": "Kling AI", "cat": "Imagem e vídeo", "env": ["KLING_API_KEY", "KLING_ACCESS_KEY", "KLING_SECRET_KEY"],
              "uses": "Imagens e vídeos fotorrealistas (fora dos orçamentos)", "console": "https://app.klingai.com/global/dev/api-key"},
    "runway": {"label": "Runway", "cat": "Imagem e vídeo", "env": ["RUNWAYML_API_SECRET"],
               "uses": "Vídeos de apresentação", "console": "https://dev.runwayml.com/"},
    "elevenlabs": {"label": "ElevenLabs", "cat": "Voz", "env": ["ELEVENLABS_API_KEY"],
                   "uses": "Voz do Assistente e vídeos narrados", "console": "https://elevenlabs.io/app/subscription"},
    "livekit": {"label": "LiveKit", "cat": "Voz", "env": ["LIVEKIT_API_KEY", "LIVEKIT_API_SECRET"],
                "uses": "Chamadas de voz em tempo real com o avatar", "console": "https://cloud.livekit.io/"},
    "heycatch": {"label": "HeyCatch", "cat": "Voz", "env": ["HEYCATCH_API_KEY"], "uses": "Avatar / agente de voz",
                 "console": None},
    "cloudconvert": {"label": "CloudConvert", "cat": "Conversão de ficheiros", "env": ["CLOUDCONVERT_API_KEY"],
                     "uses": "Conversão DWG → PDF/DXF das plantas", "console": "https://cloudconvert.com/dashboard/api/v2/keys"},
    "google_maps": {"label": "Google Maps", "cat": "Mapas e terreno", "env": ["GOOGLE_MAPS_API_KEY"],
                    "uses": "Mapas, moradas, análise de terreno", "console": "https://console.cloud.google.com/billing"},
    "twilio": {"label": "Twilio (SMS)", "cat": "Comunicação", "env": ["TWILIO_AUTH_TOKEN"], "critical": True,
               "uses": "Alertas e partilhas por SMS", "console": "https://console.twilio.com/us1/billing/manage-billing/billing-overview"},
    "resend": {"label": "Resend (e-mail)", "cat": "Comunicação", "env": ["RESEND_API_KEY"], "critical": True,
               "uses": "Todos os e-mails da plataforma", "console": "https://resend.com/settings/billing"},
}

_CHAT = ("openai", "anthropic", "gemini")
_CREDIT_HINT = "Este fornecedor não publica o saldo por API: consultar a consola."


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _apply(disabled: set[str]) -> None:
    """Retira / devolve as chaves no ambiente do processo conforme o estado."""
    global _DISABLED
    for pid, p in PROVIDERS.items():
        off = pid in disabled and not p.get("locked")
        for var in p["env"]:
            if off:
                if var in os.environ:
                    _STASH[var] = os.environ.pop(var)
            elif var in _STASH and var not in os.environ:
                os.environ[var] = _STASH.pop(var)
    _DISABLED = {d for d in disabled if d in PROVIDERS and not PROVIDERS[d].get("locked")}


def is_enabled(pid: str) -> bool:
    return pid not in _DISABLED


def configured(pid: str) -> bool:
    return any(os.environ.get(v) or _STASH.get(v) for v in PROVIDERS[pid]["env"])


def _key(var: str) -> str:
    return (os.environ.get(var) or _STASH.get(var) or "").strip()


async def load() -> set[str]:
    from core.db import db
    doc = await db.app_settings.find_one({"_id": _SETTINGS_ID}) or {}
    disabled = set(doc.get("disabled") or [])
    _apply(disabled)
    _SYNC["at"] = time.monotonic()
    return disabled


def start_sync() -> None:
    """Reaplica o estado guardado de 30 em 30 s (outros workers que tenham mudado o estado)."""
    t = _SYNC.get("task")
    if t and not t.done():
        return

    async def _loop():
        while True:
            try:
                await load()
            except Exception:  # noqa: BLE001
                log.debug("api_control sync failed", exc_info=True)
            await asyncio.sleep(30)

    try:
        _SYNC["task"] = asyncio.get_running_loop().create_task(_loop())
    except RuntimeError:
        pass


async def set_enabled(pid: str, enabled: bool, who: str | None = None) -> dict:
    from core.db import db
    if pid not in PROVIDERS:
        raise KeyError(pid)
    if PROVIDERS[pid].get("locked") and not enabled:
        raise ValueError("A chave universal Emergent não pode ser desligada: serve também para o armazenamento dos ficheiros.")
    disabled = await load()
    (disabled.discard if enabled else disabled.add)(pid)
    if not enabled and pid in _CHAT and all(c in disabled for c in _CHAT):
        raise ValueError("Pelo menos uma IA de conversa (OpenAI, Claude ou Gemini) tem de ficar ligada: o Assistente deixaria de responder.")
    await db.app_settings.update_one({"_id": _SETTINGS_ID}, {"$set": {"disabled": sorted(disabled), "updated_at": _now()},
                                                              "$push": {"log": {"$each": [{"provider": pid, "enabled": enabled,
                                                                                            "by": who, "at": _now()}],
                                                                                "$slice": -100}}}, upsert=True)
    _apply(disabled)
    if pid == "openai":
        try:
            from engines import llm_keys
            if enabled and llm_keys.status().get("disabled"):
                await llm_keys.reactivate_openai()
        except Exception:  # noqa: BLE001 — o disjuntor OpenAI mantém o seu estado; o painel mostra-o
            log.warning("openai reactivate after enable failed", exc_info=True)
    _BAL_CACHE.pop(pid, None)
    return await provider_status(pid)


async def set_limit(pid: str, monthly_limit_eur: float | None, note: str | None) -> dict:
    from core.db import db
    if pid not in PROVIDERS:
        raise KeyError(pid)
    await db.app_settings.update_one({"_id": _SETTINGS_ID}, {"$set": {f"limits.{pid}": {
        "monthly_limit_eur": monthly_limit_eur, "note": (note or "").strip()[:200] or None, "at": _now()}}}, upsert=True)
    return await provider_status(pid)


# ---------- crédito / saldo por fornecedor ----------

async def _get(url: str, headers: dict, params: dict | None = None, auth=None) -> dict:
    async with httpx.AsyncClient(timeout=15) as c:
        r = await c.get(url, headers=headers, params=params, auth=auth)
        r.raise_for_status()
        return r.json()


def _month_start() -> datetime:
    n = datetime.now(timezone.utc)
    return n.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


async def _bal_elevenlabs() -> dict:
    d = await _get("https://api.elevenlabs.io/v1/user/subscription", {"xi-api-key": _key("ELEVENLABS_API_KEY")})
    used, lim = int(d.get("character_count") or 0), int(d.get("character_limit") or 0)
    return {"kind": "quota", "used": used, "limit": lim, "remaining": max(0, lim - used), "unit": "caracteres",
            "plan": d.get("tier"), "resets_at": datetime.fromtimestamp(d["next_character_count_reset_unix"], timezone.utc).isoformat()
            if d.get("next_character_count_reset_unix") else None}


async def _bal_runway() -> dict:
    d = await _get("https://api.dev.runwayml.com/v1/organization",
                   {"Authorization": f"Bearer {_key('RUNWAYML_API_SECRET')}", "X-Runway-Version": "2024-11-06"})
    return {"kind": "balance", "remaining": d.get("creditBalance"), "unit": "créditos"}


async def _bal_cloudconvert() -> dict:
    base = (os.environ.get("CLOUDCONVERT_API_BASE") or "https://api.cloudconvert.com/v2").rstrip("/")
    d = (await _get(f"{base}/users/me", {"Authorization": f"Bearer {_key('CLOUDCONVERT_API_KEY')}"})).get("data") or {}
    return {"kind": "balance", "remaining": d.get("credits"), "unit": "minutos de conversão"}


async def _bal_apify() -> dict:
    d = (await _get("https://api.apify.com/v2/users/me/limits", {"Authorization": f"Bearer {_key('APIFY_API_TOKEN')}"})).get("data") or {}
    used = (d.get("current") or {}).get("monthlyUsageUsd")
    lim = (d.get("limits") or {}).get("maxMonthlyUsageUsd")
    return {"kind": "quota", "used": round(used or 0, 2), "limit": lim,
            "remaining": round(lim - used, 2) if lim is not None and used is not None else None, "unit": "USD / mês"}


async def _bal_twilio() -> dict:
    sid = _key("TWILIO_ACCOUNT_SID")
    if not sid:
        raise ValueError("TWILIO_ACCOUNT_SID ausente")
    d = await _get(f"https://api.twilio.com/2010-04-01/Accounts/{sid}/Balance.json", {}, auth=(sid, _key("TWILIO_AUTH_TOKEN")))
    return {"kind": "balance", "remaining": float(d.get("balance") or 0), "unit": d.get("currency") or "USD"}


async def _bal_kling() -> dict:
    from engines import kling_client
    now = int(time.time() * 1000)
    base = (os.environ.get("KLING_API_BASE") or "https://api-singapore.klingai.com").rstrip("/")
    d = await _get(f"{base}/account/costs", {"Authorization": f"Bearer {kling_client._auth()}"},
                   {"start_time": now - 365 * 86400 * 1000, "end_time": now})
    packs = ((d.get("data") or {}).get("resource_pack_subscribe_infos") or [])
    live = [p for p in packs if str(p.get("status") or "").lower() in ("online", "active", "")]
    return {"kind": "quota", "remaining": round(sum(float(p.get("remaining_quantity") or 0) for p in live), 1),
            "limit": round(sum(float(p.get("total_quantity") or 0) for p in live), 1), "unit": "unidades (pacotes ativos)",
            "packs": [{"name": p.get("resource_pack_name"), "remaining": p.get("remaining_quantity"), "total": p.get("total_quantity"),
                       "expires": p.get("invalid_time")} for p in live][:6]}


async def _bal_openai() -> dict:
    admin = _key("OPENAI_ADMIN_KEY")
    if not admin:
        raise LookupError("A OpenAI só dá o gasto com uma chave de administração (OPENAI_ADMIN_KEY nos Secrets).")
    d = await _get("https://api.openai.com/v1/organization/costs", {"Authorization": f"Bearer {admin}"},
                   {"start_time": int(_month_start().timestamp()), "limit": 31})
    spent = sum(float(((r.get("amount") or {}).get("value")) or 0) for b in d.get("data") or [] for r in b.get("results") or [])
    return {"kind": "spend", "used": round(spent, 2), "unit": "USD gastos este mês"}


async def _bal_anthropic() -> dict:
    admin = _key("ANTHROPIC_ADMIN_KEY")
    if not admin:
        raise LookupError("A Anthropic só dá o gasto com uma chave de administração (ANTHROPIC_ADMIN_KEY nos Secrets).")
    d = await _get("https://api.anthropic.com/v1/organizations/cost_report",
                   {"x-api-key": admin, "anthropic-version": "2023-06-01"},
                   {"starting_at": _month_start().strftime("%Y-%m-%dT%H:%M:%SZ"), "limit": 31})
    cents = sum(float(r.get("amount") or 0) for b in d.get("data") or [] for r in b.get("results") or [])
    return {"kind": "spend", "used": round(cents / 100, 2), "unit": "USD gastos este mês"}


BALANCE = {"elevenlabs": _bal_elevenlabs, "runway": _bal_runway, "cloudconvert": _bal_cloudconvert, "apify": _bal_apify,
           "twilio": _bal_twilio, "kling": _bal_kling, "openai": _bal_openai, "anthropic": _bal_anthropic}


async def balance(pid: str, fresh: bool = False) -> dict:
    if not configured(pid):
        return {"kind": "none", "message": "Chave não configurada nos Secrets."}
    fn = BALANCE.get(pid)
    if fn is None:
        return {"kind": "none", "message": _CREDIT_HINT}
    hit = _BAL_CACHE.get(pid)
    if hit and not fresh and time.monotonic() - hit[0] < 600:
        return hit[1]
    try:
        res = await asyncio.wait_for(fn(), 20)
        res["checked_at"] = _now()
    except LookupError as e:
        res = {"kind": "none", "message": str(e)}
    except Exception as e:  # noqa: BLE001 — nunca mostrar a chave; só o tipo de erro e o código HTTP
        code = getattr(getattr(e, "response", None), "status_code", None)
        res = {"kind": "error", "message": f"Saldo indisponível ({type(e).__name__}{f' HTTP {code}' if code else ''})."}
    _BAL_CACHE[pid] = (time.monotonic(), res)
    return res


async def _month_calls() -> dict[str, int]:
    from core.db import db
    month = datetime.now(timezone.utc).strftime("%Y-%m")
    out: dict[str, int] = {}
    try:
        async for r in db.ai_usage_monthly.find({"month": month}):
            out[r.get("provider") or "?"] = out.get(r.get("provider") or "?", 0) + int(r.get("calls") or 0)
    except Exception:  # noqa: BLE001
        pass
    return out


def _calls_for(pid: str, calls: dict[str, int]) -> int | None:
    names = {"emergent": ("emergent",), "openai": ("openai", "openai_direct"), "anthropic": ("anthropic", "claude"),
             "gemini": ("gemini", "google", "gemini_native")}.get(pid)
    if not names:
        return None
    return sum(v for k, v in calls.items() if str(k).lower() in names)


async def provider_status(pid: str, calls: dict | None = None, limits: dict | None = None, fresh: bool = False) -> dict:
    p = PROVIDERS[pid]
    if limits is None:
        from core.db import db
        limits = ((await db.app_settings.find_one({"_id": _SETTINGS_ID})) or {}).get("limits") or {}
    if calls is None:
        calls = await _month_calls()
    st = {"id": pid, "label": p["label"], "category": p["cat"], "uses": p["uses"], "console": p.get("console"),
          "configured": configured(pid), "enabled": is_enabled(pid), "locked": bool(p.get("locked")),
          "critical": bool(p.get("critical")), "calls_month": _calls_for(pid, calls),
          "limit": limits.get(pid) or {}, "credit": await balance(pid, fresh)}
    if pid == "openai":
        try:
            from engines import llm_keys
            k = llm_keys.status()
            if k.get("disabled") and st["enabled"]:
                st["breaker"] = {"reason": k.get("reason"), "since": k.get("since")}
        except Exception:  # noqa: BLE001
            pass
    return st


async def overview(fresh: bool = False) -> dict:
    from core.db import db
    await load()
    doc = await db.app_settings.find_one({"_id": _SETTINGS_ID}) or {}
    calls = await _month_calls()
    items = await asyncio.gather(*(provider_status(pid, calls, doc.get("limits") or {}, fresh) for pid in PROVIDERS))
    return {"providers": list(items), "log": list(reversed(doc.get("log") or []))[:20],
            "month": datetime.now(timezone.utc).strftime("%Y-%m")}
