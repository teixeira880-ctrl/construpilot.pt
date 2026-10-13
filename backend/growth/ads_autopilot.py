"""Piloto automático Google Ads (inclui campanhas que servem no YouTube geridas na mesma conta).

Modo TOTALMENTE AUTOMÁTICO escolhido pelo proprietário, sempre dentro de um TETO MENSAL rígido:
- sem teto definido (0 €) ou piloto desligado → não faz nada;
- gasto do mês ≥ teto → pausa TODAS as campanhas ativas (travão de emergência);
- projeção do mês acima do teto → reduz proporcionalmente os orçamentos diários;
- campanha com custo ≥ limite e 0 conversões em 14 dias → pausada;
- campanhas com CPA abaixo da média → orçamento +X %/dia (máx. configurado), se a projeção o permitir;
- campanhas "Growth …" criadas pelo ConstruPilot em PAUSED → ativadas se houver margem no teto.
Todas as ações ficam em `ads_actions`; o resumo diário vai para as notificações dos admins.
Botão "Parar tudo" (kill switch) pausa tudo e desliga o piloto.
"""
from __future__ import annotations

import calendar
import logging
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import httpx

from core.db import db
from growth.ads_connectors import GADS_V, ConnectorError, _digits, _google_token
from growth.common import env, now_iso

log = logging.getLogger("ads_autopilot")
LISBON = ZoneInfo("Europe/Lisbon")
SETTINGS_KEY = "ads_autopilot_settings"
DEFAULTS = {"enabled": False, "monthly_cap_eur": 0.0, "max_daily_increase_pct": 20,
            "pause_cost_no_conv_eur": 40.0, "min_daily_budget_eur": 3.0,
            "activate_growth_campaigns": True, "project_id": None}
MICROS = 1_000_000


async def get_settings() -> dict:
    doc = await db.app_settings.find_one({"key": SETTINGS_KEY}, {"_id": 0}) or {}
    return {**DEFAULTS, **{k: v for k, v in doc.items() if k in DEFAULTS}}


async def save_settings(patch: dict) -> dict:
    cur = await get_settings()
    for k in ("enabled", "activate_growth_campaigns"):
        if k in patch:
            cur[k] = bool(patch[k])
    for k, lo, hi in (("monthly_cap_eur", 0, 100000), ("max_daily_increase_pct", 0, 50),
                      ("pause_cost_no_conv_eur", 5, 10000), ("min_daily_budget_eur", 1, 1000)):
        if k in patch and patch[k] is not None:
            cur[k] = max(lo, min(hi, float(patch[k])))
    if "project_id" in patch:
        cur["project_id"] = patch["project_id"]
    await db.app_settings.update_one({"key": SETTINGS_KEY}, {"$set": {"key": SETTINGS_KEY, **cur}}, upsert=True)
    return cur


async def _project_id(settings: dict) -> str:
    if settings.get("project_id"):
        return settings["project_id"]
    conn = await db.growth_connections.find_one({"provider": "google_ads", "status": "connected"}, {"_id": 0, "project_id": 1})
    if not conn:
        raise ConnectorError("Google Ads não autorizado (Growth → Integrações → «Autorizar Google Ads»)")
    return conn["project_id"]


def _headers(token: str) -> dict:
    h = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    if env("GOOGLE_ADS_DEVELOPER_TOKEN"):
        h["developer-token"] = env("GOOGLE_ADS_DEVELOPER_TOKEN")
    if env("GOOGLE_ADS_LOGIN_CUSTOMER_ID"):
        h["login-customer-id"] = _digits(env("GOOGLE_ADS_LOGIN_CUSTOMER_ID"))
    return h


async def _search(client: httpx.AsyncClient, token: str, cid: str, query: str) -> list[dict]:
    rows, page = [], None
    while True:
        body = {"query": query}
        if page:
            body["pageToken"] = page
        r = await client.post(f"https://googleads.googleapis.com/{GADS_V}/customers/{cid}/googleAds:search",
                              headers=_headers(token), json=body)
        if r.is_error:
            raise ConnectorError(f"Google Ads search HTTP {r.status_code}: {r.text[:300]}")
        data = r.json()
        rows += data.get("results") or []
        page = data.get("nextPageToken")
        if not page:
            return rows


async def _mutate(client: httpx.AsyncClient, token: str, cid: str, resource: str, ops: list[dict]) -> dict:
    r = await client.post(f"https://googleads.googleapis.com/{GADS_V}/customers/{cid}/{resource}:mutate",
                          headers=_headers(token), json={"operations": ops})
    if r.is_error:
        raise ConnectorError(f"Google Ads {resource} HTTP {r.status_code}: {r.text[:300]}")
    return r.json()


def _f(v) -> float:
    try:
        return float(v or 0)
    except (TypeError, ValueError):
        return 0.0


async def snapshot(client: httpx.AsyncClient, token: str, cid: str) -> list[dict]:
    """Uma linha por campanha (ENABLED/PAUSED) com orçamento, gasto do mês e métricas 14 dias."""
    base = await _search(client, token, cid,
        "SELECT campaign.id, campaign.name, campaign.status, campaign.advertising_channel_type, "
        "campaign_budget.resource_name, campaign_budget.amount_micros, campaign_budget.explicitly_shared "
        "FROM campaign WHERE campaign.status IN ('ENABLED', 'PAUSED')")
    month = await _search(client, token, cid,
        "SELECT campaign.id, metrics.cost_micros, metrics.conversions, metrics.clicks "
        "FROM campaign WHERE segments.date DURING THIS_MONTH AND campaign.status IN ('ENABLED', 'PAUSED')")
    last14 = await _search(client, token, cid,
        "SELECT campaign.id, metrics.cost_micros, metrics.conversions, metrics.clicks "
        "FROM campaign WHERE segments.date DURING LAST_14_DAYS AND campaign.status IN ('ENABLED', 'PAUSED')")

    def agg(rows):
        out: dict[str, dict] = {}
        for r in rows:
            cid_ = str((r.get("campaign") or {}).get("id"))
            m = r.get("metrics") or {}
            a = out.setdefault(cid_, {"cost": 0.0, "conv": 0.0, "clicks": 0.0})
            a["cost"] += _f(m.get("costMicros")) / MICROS
            a["conv"] += _f(m.get("conversions"))
            a["clicks"] += _f(m.get("clicks"))
        return out

    mo, l14 = agg(month), agg(last14)
    camps = []
    for r in base:
        c, b = r.get("campaign") or {}, r.get("campaignBudget") or {}
        k = str(c.get("id"))
        camps.append({"id": k, "name": c.get("name"), "status": c.get("status"),
                      "channel": c.get("advertisingChannelType"),
                      "resource": f"customers/{cid}/campaigns/{k}",
                      "budget_resource": b.get("resourceName"), "budget_shared": bool(b.get("explicitlyShared")),
                      "daily_budget": _f(b.get("amountMicros")) / MICROS,
                      "month_cost": mo.get(k, {}).get("cost", 0.0),
                      "cost14": l14.get(k, {}).get("cost", 0.0), "conv14": l14.get(k, {}).get("conv", 0.0)})
    return camps


def plan_actions(camps: list[dict], s: dict, today: datetime) -> list[dict]:
    """Decide as ações (função pura, testável). Não chama a API."""
    cap = float(s["monthly_cap_eur"] or 0)
    if cap <= 0:
        return []
    days_in_month = calendar.monthrange(today.year, today.month)[1]
    days_left = days_in_month - today.day + 1  # inclui hoje
    spent = sum(c["month_cost"] for c in camps)
    enabled = [c for c in camps if c["status"] == "ENABLED"]
    actions: list[dict] = []

    if spent >= cap:
        return [{"type": "pause", "campaign": c, "reason": f"teto mensal atingido ({spent:.2f} € ≥ {cap:.2f} €)"}
                for c in enabled]

    # 1) pausar campanhas que gastam sem converter
    keep = []
    for c in enabled:
        if c["cost14"] >= s["pause_cost_no_conv_eur"] and c["conv14"] == 0:
            actions.append({"type": "pause", "campaign": c,
                            "reason": f"{c['cost14']:.2f} € em 14 dias sem conversões"})
        else:
            keep.append(c)

    budgets = {c["id"]: c["daily_budget"] for c in keep}
    # 2) reforçar as melhores (CPA abaixo da média), até +X %
    conv = [c for c in keep if c["conv14"] > 0]
    if conv:
        avg_cpa = sum(c["cost14"] for c in conv) / sum(c["conv14"] for c in conv)
        for c in conv:
            if c["budget_shared"]:
                continue
            cpa = c["cost14"] / c["conv14"]
            if cpa < avg_cpa:
                budgets[c["id"]] = round(c["daily_budget"] * (1 + s["max_daily_increase_pct"] / 100), 2)

    # 3) ativar campanhas Growth em pausa, se houver margem
    to_enable = []
    if s.get("activate_growth_campaigns"):
        for c in camps:
            if c["status"] == "PAUSED" and (c["name"] or "").startswith("Growth ") and c["month_cost"] == 0:
                to_enable.append(c)
                budgets[c["id"]] = c["daily_budget"]

    # 4) respeitar o teto: projeção = gasto + soma orçamentos × dias restantes
    room = cap - spent
    projected = sum(budgets.values()) * days_left
    if projected > room and budgets:
        # primeiro desistir das ativações, depois reduzir proporcionalmente
        while to_enable and sum(budgets.values()) * days_left > room:
            c = to_enable.pop()
            budgets.pop(c["id"], None)
        total = sum(budgets.values())
        if total * days_left > room and total > 0:
            factor = max(0.0, room / (total * days_left))
            for k in budgets:
                budgets[k] = round(min(budgets[k], max(s["min_daily_budget_eur"], budgets[k] * factor)), 2)
            if sum(budgets.values()) * days_left > room:  # mesmo no mínimo não cabe → pausar as piores
                for c in sorted(keep, key=lambda x: (x["conv14"], -x["cost14"])):
                    if sum(budgets.values()) * days_left <= room:
                        break
                    if c["id"] in budgets:
                        budgets.pop(c["id"])
                        actions.append({"type": "pause", "campaign": c, "reason": "teto mensal: sem margem"})

    by_id = {c["id"]: c for c in camps}
    for k, new in budgets.items():
        c = by_id[k]
        if c["budget_shared"] or not c["budget_resource"]:
            continue
        if abs(new - c["daily_budget"]) >= 0.01:
            actions.append({"type": "budget", "campaign": c, "from": c["daily_budget"], "to": new,
                            "reason": "reforço (CPA abaixo da média)" if new > c["daily_budget"] else "ajuste ao teto mensal"})
    for c in to_enable:
        if c["id"] in budgets:
            actions.append({"type": "enable", "campaign": c, "reason": "campanha Growth pronta e dentro do teto"})
    return actions


async def _apply(client, token, cid, a: dict) -> None:
    c = a["campaign"]
    if a["type"] in ("pause", "enable"):
        await _mutate(client, token, cid, "campaigns", [{"update": {"resourceName": c["resource"],
                      "status": "PAUSED" if a["type"] == "pause" else "ENABLED"}, "updateMask": "status"}])
    elif a["type"] == "budget":
        await _mutate(client, token, cid, "campaignBudgets", [{"update": {"resourceName": c["budget_resource"],
                      "amountMicros": str(round(a["to"] * MICROS))}, "updateMask": "amount_micros"}])


async def run(trigger: str = "scheduler") -> dict:
    s = await get_settings()
    if not s["enabled"]:
        return {"skipped": "piloto desligado"}
    if float(s["monthly_cap_eur"] or 0) <= 0:
        return {"skipped": "teto mensal não definido"}
    if not env("GOOGLE_ADS_CUSTOMER_ID"):
        return {"skipped": "GOOGLE_ADS_CUSTOMER_ID em falta"}
    cid = _digits(env("GOOGLE_ADS_CUSTOMER_ID"))
    token = await _google_token(await _project_id(s))
    today = datetime.now(LISBON)
    async with httpx.AsyncClient(timeout=60) as client:
        camps = await snapshot(client, token, cid)
        actions = plan_actions(camps, s, today)
        done = []
        for a in actions:
            entry = {"type": a["type"], "campaign_id": a["campaign"]["id"], "campaign": a["campaign"]["name"],
                     "reason": a["reason"], "from": a.get("from"), "to": a.get("to"), "trigger": trigger,
                     "at": now_iso()}
            try:
                await _apply(client, token, cid, a)
                entry["ok"] = True
            except Exception as e:  # noqa: BLE001
                entry["ok"], entry["error"] = False, str(e)[:300]
            await db.ads_actions.insert_one(dict(entry))
            entry.pop("_id", None)
            done.append(entry)
    spent = round(sum(c["month_cost"] for c in camps), 2)
    summary = {"at": now_iso(), "trigger": trigger, "month_spend_eur": spent, "cap_eur": s["monthly_cap_eur"],
               "campaigns": len(camps), "enabled": sum(1 for c in camps if c["status"] == "ENABLED"),
               "actions": len(done), "errors": sum(1 for d in done if not d.get("ok"))}
    await db.app_settings.update_one({"key": "ads_autopilot_last"}, {"$set": {"key": "ads_autopilot_last", **summary}}, upsert=True)
    if done:
        try:
            from growth.autopilot import notify_admins
            await notify_admins(f"Google Ads (piloto automático): {len(done)} ação(ões); gasto do mês {spent:.2f} € / teto "
                                f"{s['monthly_cap_eur']:.0f} €", "/admin")
        except Exception:  # noqa: BLE001
            pass
    return {**summary, "details": done}


async def kill_switch(actor: str) -> dict:
    """Pausa todas as campanhas ativas e desliga o piloto."""
    await save_settings({"enabled": False})
    cid = _digits(env("GOOGLE_ADS_CUSTOMER_ID") or "")
    if not cid:
        return {"paused": 0, "note": "GOOGLE_ADS_CUSTOMER_ID em falta"}
    token = await _google_token(await _project_id(await get_settings()))
    paused = 0
    async with httpx.AsyncClient(timeout=60) as client:
        rows = await _search(client, token, cid, "SELECT campaign.id FROM campaign WHERE campaign.status = 'ENABLED'")
        for r in rows:
            k = str(r["campaign"]["id"])
            await _mutate(client, token, cid, "campaigns", [{"update": {"resourceName": f"customers/{cid}/campaigns/{k}",
                          "status": "PAUSED"}, "updateMask": "status"}])
            paused += 1
            await db.ads_actions.insert_one({"type": "pause", "campaign_id": k, "reason": "PARAR TUDO (manual)",
                                             "trigger": actor, "ok": True, "at": now_iso()})
    return {"paused": paused}


async def overview() -> dict:
    last = await db.app_settings.find_one({"key": "ads_autopilot_last"}, {"_id": 0, "key": 0})
    actions = await db.ads_actions.find({}, {"_id": 0}).sort("at", -1).to_list(30)
    return {"settings": await get_settings(), "last_run": last, "actions": actions,
            "configured": {"customer_id": bool(env("GOOGLE_ADS_CUSTOMER_ID")),
                           "oauth": bool(await db.growth_connections.find_one({"provider": "google_ads", "status": "connected"}, {"_id": 1}))}}
