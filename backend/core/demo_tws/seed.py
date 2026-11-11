"""Seed da empresa de demonstração « Teste Websummit » (construpilot.pt).

Princípios
  - Tudo o que existe como funcionalidade é preenchido através dos ENDPOINTS REAIS da API
    (chamadas internas ASGI, autenticadas como o proprietário da empresa): organização, equipa,
    RH, clientes, fornecedores, biblioteca de preços, bordereau de preços da empresa, obras,
    projetos com estimativa do motor, orçamentos, faturas, pagamentos, autos de medição,
    receção, nota de crédito, planeamento, diário de obra, reservas, checklist, plantas de
    execução (PDF + DXF), despesas, encomendas de materiais e custos de obra.
    Assim os dados ficam exatamente no formato que a interface espera.
  - Só o que a API não permite criar sem um telemóvel no terreno (pontos de ponto históricos
    com selfie/GPS) é escrito diretamente, no mesmo esquema que `routes/hr.py`.
  - Idempotente: um marcador `demo_seed_state` impede re-execução; `force=True` apaga apenas
    os dados desta empresa (proprietário + membros) e recria tudo.
  - Zero palavra-passe em claro no código: impressão bcrypt (substituível pelo segredo
    TESTE_WEBSUMMIT_PASSWORD).
"""
from __future__ import annotations

import base64
import io
import logging
import os
import secrets
from datetime import date, datetime, timedelta, timezone

from core.demo_tws import data as D
from core.demo_tws.plans import build_architecture_dxf, build_execution_pdf, mep_input

logger = logging.getLogger("demo_tws")

SEED_VERSION = 1
STATE_ID = "teste_websummit"
DEMO_SOURCE = "teste_websummit_2026"
PASSWORD_ENV = "TESTE_WEBSUMMIT_PASSWORD"
# bcrypt da palavra-passe de demonstração comunicada ao fundador (nunca o texto em claro).
PASSWORD_BCRYPT = "$2b$12$zJyvrBSZ0CHcxiL0Bkzxqe7dY3ECw7TIrXwZngyE3lhsreY6USzv6"
PLAN_ID = "pro_business_monthly"   # plano histórico Pro Business: acesso total, sem limites de lugares

# coleções com documentos da empresa (apagadas só para esta empresa em caso de `force`)
_OWNED_COLLECTIONS = [
    "projects", "chantiers", "chantier_plannings", "pro_documents", "situations", "clients", "suppliers",
    "library_items", "company_price_libraries", "plans_takeoff", "plan_upload_jobs", "site_reports",
    "site_reserves", "site_checklist", "material_orders", "quote_sends", "activity_log", "notifications",
    "doc_counters", "user_sessions", "entitlements", "prorata", "roofing_analyses",
]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _password_hash(hash_password) -> str:
    pw = (os.environ.get(PASSWORD_ENV) or "").strip()
    return hash_password(pw) if pw else PASSWORD_BCRYPT


def _logo_data_url() -> str | None:
    try:
        from PIL import Image, ImageDraw, ImageFont
    except Exception:  # noqa: BLE001
        return None
    img = Image.new("RGBA", (512, 512), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((16, 16, 496, 496), radius=96, fill=(31, 107, 79, 255))
    d.rounded_rectangle((56, 352, 456, 376), radius=12, fill=(184, 115, 58, 255))
    font = None
    for path in ("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
                 "/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf"):
        if os.path.exists(path):
            font = ImageFont.truetype(path, 210)
            break
    if font is None:
        font = ImageFont.load_default()
    d.text((256, 205), "TW", fill=(250, 246, 238, 255), font=font, anchor="mm")
    try:
        small = ImageFont.truetype(font.path, 44) if hasattr(font, "path") else ImageFont.load_default()
    except Exception:  # noqa: BLE001
        small = ImageFont.load_default()
    d.text((256, 430), "WEBSUMMIT", fill=(250, 246, 238, 255), font=small, anchor="mm")
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


def _branding(logo: str | None) -> dict:
    c = D.COMPANY
    hq = c["hq"]
    out = {
        "company": c["name"], "company_name": c["name"],
        "brand_company_name": c["legal_name"],
        "brand_company_email": c["owner_email"],
        "brand_address": hq["address"], "brand_postal": hq["postal"], "brand_city": hq["city"],
        "brand_country": hq["country"],
        "brand_nif": "PT 500 000 000 (demo)",
        "brand_alvara": "Alvará IMPIC n.º 00000-PUB (demo)",
        "brand_vat": "PT500000000 (demo)",
        "brand_contact_line": "+351 210 000 110 · teste.websummit@construpilot.pt · Lisboa · Paris · London · New York",
        "brand_accent_color": c["accent"],
        "brand_tagline": "Engenharia e construção — Portugal, França, Reino Unido e Estados Unidos",
        "brand_description": (
            "A Teste Websummit é a empresa de demonstração da ConstruPilot: construtora internacional "
            "com sede em Lisboa e filiais em Paris, Londres e Nova Iorque. Moradias, reabilitação de "
            "edifícios, hotelaria e fit-out de escritórios, com equipas próprias de direção de obra, "
            "arquitetura, engenharia e mão de obra qualificada.\n\n"
            + "\n".join(f"• {b['label']}: {b['entity']} — {b['address']} — {b['phone']}" for b in c["branches"])
        ),
        "brand_header_text": "Teste Websummit — Engenharia & Construção",
        "brand_footer_text": " · ".join(f"{b['entity']}, {b['address']}" for b in c["branches"]),
        "brand_certifications": ["ISO 9001 (demo)", "Alvará classe 6 (demo)", "Qualibat (démo)"],
        "brand_doc_layout": "detaille",
        "brand_default_email_message": "Segue em anexo o documento. Ao dispor para qualquer esclarecimento. — Teste Websummit",
        "service_zones": ["Portugal", "França", "Reino Unido", "Estados Unidos"],
        "company_branches": c["branches"],
        "public_slug": c["slug"], "public_published": True, "public_show_reviews": True,
        "public_contact_phone": "+351 210 000 110",
    }
    if logo:
        out["brand_logo_b64"] = logo
    return out


class _Api:
    """Cliente interno: chama a própria app FastAPI (ASGI), autenticado por sessão."""

    def __init__(self, app, token: str):
        import httpx
        self.client = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://internal-seed",
                                        headers={"Authorization": f"Bearer {token}"}, timeout=180)
        self.errors: list[str] = []
        self.calls = 0

    async def __call__(self, method: str, path: str, *, ok_missing: bool = False, token: str | None = None, **kw):
        self.calls += 1
        headers = {"Authorization": f"Bearer {token}"} if token else None
        r = await self.client.request(method, "/api" + path, headers=headers, **kw)
        if r.status_code >= 400:
            msg = f"{method} {path} -> {r.status_code}: {r.text[:300]}"
            self.errors.append(msg)
            logger.warning("demo_tws: %s", msg)
            if ok_missing:
                return None
            raise RuntimeError(msg)
        try:
            return r.json()
        except Exception:  # noqa: BLE001
            return None

    async def close(self):
        await self.client.aclose()


# ============================================================================ helpers de dados

def _lib_by_ref() -> dict:
    return {r[0]: r for r in D.LIBRARY}


def _quote_lines(site: dict, factor: float = 1.0) -> list[dict]:
    lib = _lib_by_ref()
    cp = D.COUNTRY_PRICING[site["country"]]
    vat = cp["vat_reno"] if site.get("reno") else cp["vat"]
    by_lot: dict[str, list] = {}
    for ref, q, mode in D.SCOPES[site["scope"]]:
        _r, lot, des, unit, pu, cost, _v = lib[ref]
        qty = q if mode == "fix" else round(q * site["surface"] * factor, 2)
        if mode == "fix" and unit != "vg":
            qty = max(1, round(q * (factor if factor < 1 else 1)))
        by_lot.setdefault(lot, []).append({
            "kind": "line", "line_kind": "ouvrage", "designation": des, "unit": unit, "qty": qty,
            "unit_price_ht": round(pu * cp["coef"], 2), "cost_price_ht": round(cost * cp["coef"], 2),
            "vat_rate": vat, "vat_confirmed": True, "category": lot,
            "price_source": "library", "price_reference": ref,
            "price_reference_label": "Biblioteca de preços Teste Websummit",
        })
    order = [lot for lot, _ in D.LOT_ORDER]
    lines = []
    for lot in sorted(by_lot, key=lambda x: order.index(x) if x in order else 99):
        lines.append({"kind": "section", "title": lot})
        lines.extend(by_lot[lot])
    return lines


def _lots_of(lines: list[dict]) -> list[str]:
    out = []
    for ln in lines:
        if ln.get("kind") == "line" and ln["category"] not in out:
            out.append(ln["category"])
    return out


def _workday(d: date, n: int) -> date:
    step = 1 if n >= 0 else -1
    while n:
        d += timedelta(days=step)
        if d.weekday() < 5:
            n -= step
    return d


def _plan_tasks(site: dict, lots: list[str]) -> tuple[list[dict], date]:
    """Tarefas do planeamento: durações por lote, paralelismo das redes (canalização/eletricidade/AVAC)."""
    base = dict(D.LOT_ORDER)
    scale = max(0.6, min(6.0, site["surface"] / 100))
    tasks = []
    prev_id = None
    network = ("Canalização", "Eletricidade", "AVAC")
    net_pred = None
    for i, lot in enumerate([lot for lot, _ in D.LOT_ORDER if lot in lots]):
        tid = f"T{i + 1:02d}"
        dur = max(2, min(90, round(base.get(lot, 1.0) * scale * 3)))
        crew = 2 if dur < 6 else 4
        preds = []
        if lot in network:
            if net_pred is None:
                net_pred = prev_id
            if net_pred:
                preds = [{"id": net_pred, "lag": 0}]
        elif prev_id:
            preds = [{"id": prev_id, "lag": 0}]
        tasks.append({"id": tid, "name": lot, "resource": lot, "duration": dur, "duration_source": "saisie",
                      "predecessors": preds, "progress": 0, "planned_hours": float(dur * 8 * crew),
                      "progress_manual": True})
        if lot in network:
            # a tarefa seguinte depende da última rede
            prev_id = tid
        else:
            prev_id = tid
            net_pred = None
    if site["status"] == "prospect":
        start = _workday(date.today(), 25)
    else:
        start = date.today() - timedelta(days=site["started_days_ago"])
    _apply_progress(tasks, site)
    return tasks, start


def _apply_progress(tasks: list[dict], site: dict) -> None:
    total = sum(t["duration"] for t in tasks) or 1
    target = site["progress"] / 100 * total
    acc = 0.0
    for t in tasks:
        if acc + t["duration"] <= target + 1e-6:
            t["progress"] = 100
        elif acc < target:
            t["progress"] = int(round((target - acc) * 100 / t["duration"]))
        else:
            t["progress"] = 0
        acc += t["duration"]


def _current_lot(tasks: list[dict]) -> str:
    for t in tasks:
        if 0 < t["progress"] < 100:
            return t["resource"]
    done = [t for t in tasks if t["progress"] == 100]
    return (done[-1] if done else tasks[0])["resource"]


# ============================================================================ limpeza (force)

async def purge(db, keep_state: bool = False) -> dict:
    owner = await db.users.find_one({"email": D.COMPANY["owner_email"]}, {"_id": 0, "user_id": 1, "organization_id": 1})
    if not owner:
        return {"purged": False}
    uid = owner["user_id"]
    members = await db.users.find({"$or": [{"employer_id": uid}, {"organization_id": owner.get("organization_id") or "__none__"}]},
                                  {"_id": 0, "user_id": 1}).to_list(1000)
    ids = list({uid, *[m["user_id"] for m in members]})
    counts = {}
    for coll in _OWNED_COLLECTIONS:
        try:
            r = await db[coll].delete_many({"user_id": {"$in": ids}})
            if r.deleted_count:
                counts[coll] = r.deleted_count
        except Exception as exc:  # noqa: BLE001
            logger.warning("demo_tws purge %s: %s", coll, exc)
    r = await db.hr_timesheets.delete_many({"employer_id": uid})
    counts["hr_timesheets"] = r.deleted_count
    if owner.get("organization_id"):
        await db.organizations.delete_one({"org_id": owner["organization_id"]})
    r = await db.users.delete_many({"user_id": {"$in": [i for i in ids if i != uid]}})
    counts["members"] = r.deleted_count
    await db.users.update_one({"user_id": uid}, {"$unset": {"organization_id": "", "org_role": "", "joined_org_at": ""}})
    if not keep_state:
        await db.demo_seed_state.delete_one({"_id": STATE_ID})
    return {"purged": True, "counts": counts}


# ============================================================================ seed

async def ensure_owner(db, hash_password, new_user_id) -> dict:
    """Conta proprietária + plano Pro Business ativo (sempre, mesmo quando o resto já foi semeado)."""
    c = D.COMPANY
    email = c["owner_email"]
    user = await db.users.find_one({"email": email}, {"_id": 0})
    now = _now()
    if not user:
        user = {
            "user_id": new_user_id(), "email": email, "name": c["owner_name"], "role": "user",
            "plan": "premium", "account_type": "pro_business", "auth_provider": "password",
            "password_hash": _password_hash(hash_password), "picture": None,
            "country": "PT", "language": "pt", "lang": "pt", "email_verified": True,
            "two_fa_enabled": False, "must_change_password": False, "active": True,
            "kyc_status": "verified", "demo_company": True, "demo_source": DEMO_SOURCE,
            "onboarding_done": True, "created_at": now,
        }
        await db.users.insert_one(dict(user))
    else:
        upd = {"account_type": "pro_business", "active": True, "email_verified": True,
               "demo_company": True, "demo_source": DEMO_SOURCE, "kyc_status": "verified"}
        if not user.get("password_hash"):
            upd["password_hash"] = _password_hash(hash_password)
        await db.users.update_one({"user_id": user["user_id"]}, {"$set": upd})
    ent_id = f"tws_demo_{user['user_id']}"
    if not await db.entitlements.find_one({"entitlement_id": ent_id}, {"_id": 1}):
        await db.entitlements.insert_one({
            "entitlement_id": ent_id, "user_id": user["user_id"], "plan_id": PLAN_ID,
            "plan_code": "PRO_BUSINESS_MONTHLY", "kind": "subscription", "audience": "pro",
            "status": "active", "granted_at": now, "source": "teste_websummit_demo_seed",
        })
    return await db.users.find_one({"user_id": user["user_id"]}, {"_id": 0})


async def seed_teste_websummit(app, db, hash_password, new_user_id, force: bool = False) -> dict:
    """Semeia uma vez (versão SEED_VERSION). Trinco atómico em `demo_seed_state`: com vários
    workers só um executa. `force=True` (endpoint admin) apaga os dados desta empresa e recria."""
    from pymongo.errors import DuplicateKeyError
    owner = await ensure_owner(db, hash_password, new_user_id)
    try:
        await db.demo_seed_state.insert_one({"_id": STATE_ID, "status": "new", "version": 0})
    except DuplicateKeyError:
        pass
    stale = (datetime.now(timezone.utc) - timedelta(minutes=45)).isoformat()
    cond = {"_id": STATE_ID, "$or": [
        {"status": {"$in": ["new", "error"]}},
        {"status": {"$ne": "running"}, "version": {"$lt": SEED_VERSION}},
        {"status": "running", "started_at": {"$lt": stale}},
    ]}
    if force:
        cond = {"_id": STATE_ID, "$or": [{"status": {"$ne": "running"}}, {"started_at": {"$lt": stale}}]}
    claimed = await db.demo_seed_state.find_one_and_update(
        cond, {"$set": {"status": "running", "started_at": _now(), "version": SEED_VERSION}})
    if not claimed:
        st = await db.demo_seed_state.find_one({"_id": STATE_ID}, {"_id": 0, "status": 1, "version": 1}) or {}
        return {"status": "skipped", "state": st.get("status"), "version": st.get("version")}
    if force or claimed.get("status") != "new":
        # recomeço limpo (re-seed pedido, versão nova ou execução anterior interrompida) — só esta empresa
        await purge(db, keep_state=True)
        owner = await ensure_owner(db, hash_password, new_user_id)
    token = "st_seed_" + secrets.token_hex(16)
    await db.user_sessions.insert_one({"user_id": owner["user_id"], "session_token": token,
                                       "expires_at": datetime.now(timezone.utc) + timedelta(hours=2),
                                       "created_at": datetime.now(timezone.utc), "seed": True})
    api = _Api(app, token)
    summary: dict = {}
    try:
        ctx = {"owner": owner, "db": db, "hash_password": hash_password, "api": api, "summary": summary}
        for step in (_step_company, _step_team, _step_clients_suppliers, _step_library, _step_sites,
                     _step_extras, _step_tools, _step_backdate):
            try:
                await step(ctx)
            except Exception as exc:  # noqa: BLE001 — um passo falhado não impede os seguintes
                logger.exception("demo_tws step %s failed", step.__name__)
                summary.setdefault("failed_steps", []).append(f"{step.__name__}: {exc}"[:300])
        status = "done" if not summary.get("failed_steps") else "partial"
    finally:
        await api.close()
        await db.user_sessions.delete_one({"session_token": token})
    summary["api_calls"] = api.calls
    summary["api_errors"] = api.errors[:40]
    await db.demo_seed_state.update_one({"_id": STATE_ID}, {"$set": {
        "status": status, "finished_at": _now(), "version": SEED_VERSION, "summary": summary}}, upsert=True)
    logger.info("demo_tws seed %s: %s", status, {k: v for k, v in summary.items() if k != "api_errors"})
    return {"status": status, **summary}


# ---------------------------------------------------------------------------- passos

async def _step_company(ctx):
    db, api, owner = ctx["db"], ctx["api"], ctx["owner"]
    brand = _branding(_logo_data_url())
    await db.users.update_one({"user_id": owner["user_id"]}, {"$set": brand})
    org = await api("POST", "/organizations", json={"name": D.COMPANY["name"]})
    org_brand = {k: v for k, v in brand.items() if k.startswith("brand_")}
    await db.organizations.update_one({"org_id": org["org_id"]}, {"$set": {
        **org_brand, "extra_seats": 100, "countries": ["PT", "FR", "GB", "US"],
        "branches": D.COMPANY["branches"], "demo_source": DEMO_SOURCE}})
    await api("PUT", "/documents/settings/auto-deposit", json={"enabled": True, "pct": 30}, ok_missing=True)
    ctx["org_id"] = org["org_id"]
    ctx["summary"]["organization"] = org.get("org_code") or org["org_id"]


async def _step_team(ctx):
    db, api, owner = ctx["db"], ctx["api"], ctx["owner"]
    pw_hash = _password_hash(ctx["hash_password"])
    team = {"directors": [], "architect": None, "engineer": None, "masons": []}

    async def add(name, email, role, extra):
        r = await api("POST", "/company/employees", json={
            "name": name, "email": email, "password": secrets.token_urlsafe(12), "role": role})
        upd = {"password_hash": pw_hash, "must_change_password": False, "email_verified": True,
               "demo_source": DEMO_SOURCE, **extra}
        if role != "ouvrier":
            upd["account_type"] = "pro_business"
        await db.users.update_one({"user_id": r["user_id"]}, {"$set": upd})
        return {**r, **extra}

    def mail(name):
        import unicodedata
        s = unicodedata.normalize("NFKD", name.lower()).encode("ascii", "ignore").decode()
        return s.replace(" ", ".") + "@" + D.EMAIL_DOMAIN

    for name, country, poste in D.DIRECTORS:
        team["directors"].append(await add(name, mail(name), "chef_chantier", {"poste": poste, "country": country}))
    n, country, poste = D.ARCHITECT
    team["architect"] = await add(n, mail(n), "admin", {"poste": poste, "country": country})
    n, country, poste = D.ENGINEER
    team["engineer"] = await add(n, mail(n), "admin", {"poste": poste, "country": country})
    for m in D.masons():
        w = await add(m["name"], m["email"], "ouvrier", {"country": m["country"]})
        await api("PATCH", f"/hr/workers/{w['user_id']}", json={"poste": m["poste"], "hourly_rate": m["hourly_rate"]})
        team["masons"].append({**w, **m})
    ctx["team"] = team
    ctx["summary"]["team"] = {"diretores_obra": len(team["directors"]), "arquiteto": 1, "engenheiro": 1,
                              "trolhas": len(team["masons"])}


async def _step_clients_suppliers(ctx):
    api = ctx["api"]
    clients = {}
    for c in D.CLIENTS:
        body = {k: v for k, v in c.items() if k != "key"}
        r = await api("POST", "/clients", json=body)
        clients[c["key"]] = r.get("client_id") or r.get("id")
    lib = _lib_by_ref()
    suppliers = []
    for i, s in enumerate(D.SUPPLIERS):
        cats = s["categories"]
        price_list = [{"ref": ref, "designation": des, "unit": unit, "unit_price": round(cost * 0.92, 2)}
                      for ref, lot, des, unit, pu, cost, _v in D.LIBRARY if any(k.split()[0].lower() in lot.lower() for k in cats)][:12]
        r = await api("POST", "/pro/suppliers", json={**s, "price_list": price_list,
                                                      "notes": "Fornecedor de demonstração (dados fictícios)."})
        suppliers.append(r)
    ctx["clients"], ctx["suppliers"] = clients, suppliers
    ctx["summary"]["clients"], ctx["summary"]["suppliers"] = len(clients), len(suppliers)
    _ = lib


async def _step_library(ctx):
    api = ctx["api"]
    n = 0
    for ref, lot, des, unit, pu, cost, vat in D.LIBRARY:
        await api("POST", "/library", json={"type": "ouvrage", "category": lot, "designation": des, "unit": unit,
                                            "unit_price_ht": pu, "cost_price_ht": cost, "vat_rate": vat,
                                            "notes": f"Ref. {ref} — preço de referência Portugal (×1,42 FR · ×1,58 UK · ×1,74 US)"})
        n += 1
    # Bordereau de preços da empresa (Excel) — importado pelo mesmo upload que o utilizador usa.
    import openpyxl
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Bordereau 2026"
    ws.append(["Teste Websummit — Bordereau de preços 2026 (PT · FR · UK · US)"])
    ws.append([])
    ws.append(["Ref", "Designação", "Unidade", "Preço unitário"])
    for country, cp in D.COUNTRY_PRICING.items():
        for ref, lot, des, unit, pu, cost, vat in D.LIBRARY:
            ws.append([f"{country}-{ref}", f"[{country}] {des}", unit, round(pu * cp["coef"], 2)])
    # Artigos de eletricidade/canalização usados pelo motor MEP (preços da empresa, PT e FR)
    for i, (des, unit, pu) in enumerate(_mep_articles()):
        ws.append([f"MEP-{i + 1:03d}", des, unit, pu])
    buf = io.BytesIO()
    wb.save(buf)
    r = await api("POST", "/pro/price-library/upload",
                  files={"file": ("Bordereau_precos_TesteWebsummit_2026.xlsx", buf.getvalue(),
                                  "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}, ok_missing=True)
    ctx["summary"]["library_items"] = n
    ctx["summary"]["company_price_library"] = (r or {}).get("imported")


_MEP_PRICES = [  # (palavra-chave, €/unidade) — primeira correspondência ganha
    ("cat. 6", 1.6), ("cat 6", 1.6), ("armário", 185), ("tableau", 260), ("quadro", 240), ("diferencial", 68),
    ("interrupteur différentiel", 68), ("disjunt", 14), ("disjonct", 14), ("contactor", 38), ("contacteur", 38),
    ("3g1,5", 2.1), ("3g2,5", 2.9), ("3g6", 6.2), ("1,5 mm", 2.1), ("2,5 mm", 2.9), ("6 mm", 6.2),
    ("coletor", 165), ("nourrice", 165), ("pex ø12", 4.2), ("pex ø16", 5.1), ("pex ø20", 6.3), ("per ø12", 4.2),
    ("per ø16", 5.1), ("per ø20", 6.3), ("ø32", 9.5), ("ø40", 11), ("ø50", 12.5), ("ø100", 19), ("ø110", 21),
    ("ligação", 95), ("raccordement", 95), ("sifão", 18), ("siphon", 18), ("válvula", 120), ("vanne", 120),
    ("grupo de segurança", 45), ("groupe de sécurité", 45), ("caixa de visita", 140), ("regard", 140),
    ("tomada", 9), ("prise", 9), ("interruptor", 11), ("interrupteur", 11), ("ponto de luz", 14), ("point lumineux", 14),
    ("rj45", 24), ("detetor", 32), ("daaf", 32), ("vmc", 450), ("ventila", 450), ("caixa", 6), ("boîte", 6),
]


def _mep_articles() -> list[tuple[str, str, float]]:
    """Designações exatas da nomenclatura MEP (PT e FR) com preço da empresa."""
    try:
        from engines.mep import generate
    except Exception:  # noqa: BLE001
        return []
    seen, out = set(), []
    for kind, country, levels in (("moradia", "pt", 2), ("apartamento", "fr", 1), ("edificio", "pt", 1)):
        try:
            study = generate(mep_input(kind, country, "bordereau", levels))
        except Exception:  # noqa: BLE001
            continue
        for ln in study.get("quantities") or []:
            des = ln.get("designation") or ""
            if not des or des in seen:
                continue
            low = des.lower()
            pu = next((p for k, p in _MEP_PRICES if k in low), None)
            if pu is None:
                pu = 25.0 if ln.get("unit") == "u" else 4.0
            seen.add(des)
            out.append((des, ln.get("unit") or "u", pu))
    return out


async def _new_doc(api, body: dict) -> dict:
    return await api("POST", "/documents", json=body)


async def _issue(api, doc_id: str) -> dict:
    return await api("POST", f"/documents/{doc_id}/issue", ok_missing=True) or {}


async def _status(api, doc_id: str, status: str):
    return await api("PATCH", f"/documents/{doc_id}/status", json={"status": status}, ok_missing=True)


async def _pay(api, doc_id: str, amount: float, days_ago: int, note: str):
    if amount <= 0:
        return
    return await api("POST", f"/documents/{doc_id}/payments", json={
        "amount": round(amount, 2), "method": "virement",
        "date": (date.today() - timedelta(days=max(0, days_ago))).isoformat(), "note": note}, ok_missing=True)


async def _step_sites(ctx):
    db, api, owner = ctx["db"], ctx["api"], ctx["owner"]
    uid = owner["user_id"]
    team, clients = ctx["team"], ctx["clients"]
    stats = {"obras": 0, "orcamentos": 0, "faturas": 0, "autos": 0, "plantas": 0, "pontos": 0,
             "relatorios": 0, "reservas": 0, "checklist": 0, "encomendas": 0}
    masons_by_country: dict[str, list] = {}
    for m in team["masons"]:
        masons_by_country.setdefault(m["country"], []).append(m)
    used: dict[str, int] = {}
    bd = ctx.setdefault("backdate", [])

    def mark(coll, key, ident, days_ago):
        if ident:
            bd.append((coll, key, ident, max(0, int(days_ago))))

    # ordem cronológica (obras mais antigas primeiro) para a numeração seguir as datas
    for site in sorted(D.SITES, key=lambda s: -s["started_days_ago"] if s["status"] != "prospect" else 1):
        stats["obras"] += 1
        started = site["started_days_ago"]
        end_ago = (65 if site["key"] == "martins" else 25) if site["status"] == "termine" else 2
        span = max(10, started - end_ago)
        director = team["directors"][site["director"]]
        client_id = clients[site["client"]]
        country_label = {"PT": "Portugal", "FR": "France", "GB": "United Kingdom", "US": "United States"}[site["country"]]
        est_country = "PT" if site["country"] == "PT" else "FR"
        # ---- projeto (estimativa pelo motor) + ficha de obra
        proj = await api("POST", "/projects", json={
            "name": site["name"], "description": site["description"], "project_type": site["type"],
            "surface": site["surface"], "finish_level": "premium" if site["key"] in ("miami", "kensington", "atlantico") else "standard",
            "country": est_country, "region": site["region"], "city": site["city"], "postal_code": site["postal_code"],
            "building_type": site["building"] if site["building"] in ("maison", "appartement") else "maison",
            "condition": "a_renover" if site.get("reno") else "bon"})
        pid = proj["project_id"]
        await db.projects.update_one({"project_id": pid}, {"$set": {
            "site_lat": site["lat"], "site_lng": site["lng"], "geofence_radius": 300,
            "address": f"{site['address']}, {site['postal_code']} {site['city']}", "site_country": site["country"],
            "country_label": country_label, "client_id": client_id, "director_user_id": director["user_id"],
            "director_name": director["name"], "estimation_note": (
                None if site["country"] in ("PT", "FR") else "Estimativa calculada com o referencial francês (motor PT/FR)."),
            "demo_source": DEMO_SOURCE,
            "status": "completed" if site["status"] == "termine" else ("planned" if site["status"] == "prospect" else "active")}})
        chantier = await api("POST", "/chantiers", json={
            "name": site["name"], "client_id": client_id, "address": site["address"], "postal_code": site["postal_code"],
            "city": f"{site['city']} ({country_label})", "status": site["status"],
            "notes": f"{site['description']}\nDiretor de obra: {director['name']}. Avanço físico: {site['progress']} %."})
        cid = chantier.get("chantier_id")
        await api("POST", f"/chantiers/{cid}/attach", json={"kind": "hr_project", "ref_id": pid}, ok_missing=True)
        mark("projects", "project_id", pid, started + 30 if started else 12)
        mark("chantiers", "chantier_id", cid, started + 30 if started else 12)

        # ---- orçamentos
        lines = _quote_lines(site)
        start_txt = (date.today() - timedelta(days=site["started_days_ago"])).isoformat() if site["started_days_ago"] else \
            _workday(date.today(), 25).isoformat()
        tasks, start = _plan_tasks(site, _lots_of(lines))
        weeks = max(2, round(sum(t["duration"] for t in tasks) / 5))
        qbody = {
            "doc_type": "quote", "client_id": client_id, "chantier_id": cid,
            "title": f"Empreitada — {site['name']}", "lines": lines, "deposit_pct": 30,
            "notes": f"Proposta n.º interna TWS-{site['key'].upper()} · Direção de obra: {director['name']}. "
                     f"Preços em euros (referencial {country_label}). Dados de demonstração.",
            "payment_terms": "Adiantamento de 30 % na adjudicação; autos de medição mensais a 30 dias.",
            "validity_days": 60, "project_address": f"{site['address']}, {site['postal_code']} {site['city']}",
            "project_duration": f"{weeks} semanas", "project_start": start_txt,
            "payment_schedule": [{"label": "Adjudicação", "pct": 30}, {"label": "Autos de medição", "pct": 60},
                                 {"label": "Receção provisória", "pct": 10}],
        }
        quotes = []
        if site["key"] == "miami":
            q1 = await _new_doc(api, qbody)
            await _issue(api, q1["doc_id"])
            await _status(api, q1["doc_id"], "sent")
            await _status(api, q1["doc_id"], "refused")
            q2 = await _new_doc(api, {**qbody, "title": f"Empreitada — {site['name']} (variante otimizada)",
                                      "lines": _quote_lines(site, factor=0.82),
                                      "notes": qbody["notes"] + " Variante revista após recusa: área reduzida e acabamentos otimizados."})
            quotes = [q1, q2]
            mark("pro_documents", "doc_id", q1["doc_id"], 35)
            mark("pro_documents", "doc_id", q2["doc_id"], 6)
        else:
            q = await _new_doc(api, qbody)
            await _issue(api, q["doc_id"])
            if site["status"] == "prospect":
                await _status(api, q["doc_id"], "sent")
            else:
                await _status(api, q["doc_id"], "sent")
                await _status(api, q["doc_id"], "signed")
            quotes = [q]
            mark("pro_documents", "doc_id", q["doc_id"], started + 25 if started else 9)
        stats["orcamentos"] += len(quotes)
        main_q = quotes[-1]
        q_full = await api("GET", f"/documents/{main_q['doc_id']}")
        ttc = (q_full.get("totals") or {}).get("ttc", 0)

        # trabalhos a mais (aditamento) na reabilitação
        if site["key"] == "aurora":
            add = await _new_doc(api, {**qbody, "title": "Trabalhos a mais n.º 1 — Substituição de caixilharia das partes comuns",
                                       "lines": [{"kind": "section", "title": "Caixilharia exterior"},
                                                 {"kind": "line", "line_kind": "ouvrage", "category": "Caixilharia exterior",
                                                  "designation": "Janela em alumínio com corte térmico e vidro duplo 4/16/4 — caixa de escada",
                                                  "unit": "m2", "qty": 38, "unit_price_ht": 340, "cost_price_ht": 238, "vat_rate": 6,
                                                  "vat_confirmed": True}],
                                       "payment_schedule": []})
            await _issue(api, add["doc_id"])
            mark("pro_documents", "doc_id", add["doc_id"], 60)
            await _status(api, add["doc_id"], "sent")
            await _status(api, add["doc_id"], "signed")
            stats["orcamentos"] += 1

        # ---- faturação: adiantamento + autos de medição + receção
        if site["status"] in ("en_cours", "termine"):
            dep = await api("POST", f"/documents/{main_q['doc_id']}/to-invoice", json={"mode": "acompte", "pct": 30}, ok_missing=True)
            if dep:
                stats["faturas"] += 1
                dep = await _issue(api, dep["doc_id"]) or dep
                mark("pro_documents", "doc_id", dep["doc_id"], started - 1)
                await _pay(api, dep["doc_id"], (dep.get("totals") or {}).get("ttc", 0), site["started_days_ago"] - 3,
                           "Adiantamento recebido por transferência")
            steps = [p for p in (25, 50, 75, 100) if p <= site["progress"]]
            if site["progress"] not in steps and site["progress"] > 0:
                steps.append(site["progress"])
            base_lines = q_full.get("lines") or []
            lot_rank = {lot: i for i, (lot, _) in enumerate(D.LOT_ORDER)}
            n_lots = max(1, len(_lots_of(base_lines)))
            lots_seq = _lots_of(base_lines)
            retention = 5 if site["key"] in ("jardins", "dubois") else 0
            auto_ago = [started - round((k + 1) * span / len(steps)) for k in range(len(steps))]
            for k, pct in enumerate(steps):
                sl = []
                for idx, ln in enumerate(base_lines):
                    if ln.get("kind") != "line":
                        continue
                    pos = lots_seq.index(ln.get("category")) if ln.get("category") in lots_seq else 0
                    # lotes iniciais avançam primeiro: avanço da linha coerente com a ordem de execução
                    line_pct = max(0.0, min(100.0, (pct / 100 * (n_lots + 2) - pos) / 3 * 100))
                    sl.append({"idx": idx, "pct": round(100.0 if pct >= 100 else line_pct, 1)})
                sit = await api("POST", "/situations", json={
                    "marche_id": main_q["doc_id"], "lines": sl, "retention_pct": retention,
                    "deposit_mode": "prorata"}, ok_missing=True)
                if not sit:
                    continue
                stats["autos"] += 1
                inv_id = sit["invoice_doc_id"]
                mark("pro_documents", "doc_id", inv_id, auto_ago[k])
                mark("situations", "situation_id", sit["situation_id"], auto_ago[k])
                due = (sit.get("net_due") if retention else sit.get("total_ttc")) or 0
                await _status(api, inv_id, "issued")
                await _status(api, inv_id, "sent")
                last = k == len(steps) - 1
                if not last or site["status"] == "termine":
                    await _pay(api, inv_id, due, max(1, auto_ago[k] - 18), f"Pagamento do auto n.º {k + 1}")
                elif site["key"] == "aurora":
                    await _pay(api, inv_id, round(due * 0.5, 2), 1, "Pagamento parcial (50 %)")
            if site["status"] == "termine":
                rec = date.today() - timedelta(days=20 if site["key"] == "dubois" else 60)
                await api("POST", f"/situations/{main_q['doc_id']}/reception", json={"reception_date": rec.isoformat()}, ok_missing=True)
            _ = (lot_rank, ttc)

        # ---- planeamento (Gantt) com avanço por lote + baseline
        if tasks:
            await api("PUT", f"/planning/chantiers/{cid}", json={
                "start_date": start.isoformat(), "deadline": _workday(start, int(sum(t['duration'] for t in tasks) * 0.8) + 10).isoformat(),
                "holidays": [], "workdays": [0, 1, 2, 3, 4], "capacities": {}, "client_visible": True,
                "tasks": tasks}, ok_missing=True)
            await api("POST", f"/planning/chantiers/{cid}/baseline", ok_missing=True)

        # ---- custos da obra (mão de obra + orçamentos ligados)
        avg_rate = {"PT": 11.5, "FR": 17.5, "GB": 20.0, "US": 26.0}[site["country"]]
        await api("PUT", f"/chantiers/{cid}/cost-settings", json={
            "expected_version": 0, "labor_rate": avg_rate * 1.45,
            "quote_ids": [q["doc_id"] for q in quotes if site["key"] != "miami" or q is quotes[-1]]}, ok_missing=True)

        # ---- diário de obra, reservas, checklist
        if site["status"] != "prospect":
            n_rep = 3 if site["status"] == "termine" else max(2, min(6, site["started_days_ago"] // 21))
            for r in range(n_rep):
                frac = (r + 1) / n_rep
                snap = []
                for t in tasks:
                    p = min(t["progress"], int(round(t["progress"] * frac + (0 if frac < 1 else 0))))
                    if p > 0:
                        snap.append({"name": t["name"], "progress": p})
                rep = await api("POST", "/site/reports", json={
                    "project": site["name"], "doc_id": main_q["doc_id"], "chantier_id": cid,
                    "title": f"Relatório semanal n.º {r + 1} — {director['name']}",
                    "notes": (f"Visita de obra com o cliente. Equipa de {site['masons']} trolhas em obra. "
                              f"Frente de trabalho: {_current_lot(tasks)}. Segurança: sem ocorrências. "
                              f"Meteorologia favorável."),
                    "lots": snap}, ok_missing=True)
                if rep:
                    stats["relatorios"] += 1
                    mark("site_reports", "report_id", rep.get("report_id"), started - round((r + 1) * span / n_rep))
                    await api("POST", f"/chantiers/{cid}/attach", json={"kind": "site_report", "ref_id": rep.get("report_id")}, ok_missing=True)
            reserves = [
                ("Pintura", "Retoques de pintura no hall de entrada (marcas de fita-cola)."),
                ("Carpintarias interiores", "Porta do quarto 2 roça no pavimento — afinar dobradiças."),
                ("Canalização", "Silicone da base de duche da suite a refazer."),
            ]
            for i, (lot, desc) in enumerate(reserves[: 3 if site["status"] == "termine" else 2]):
                rs = await api("POST", "/site/reserves", json={
                    "project": site["name"], "doc_id": main_q["doc_id"], "chantier_id": cid, "lot": lot,
                    "description": desc, "company": D.COMPANY["legal_name"]}, ok_missing=True)
                if rs:
                    stats["reservas"] += 1
                    mark("site_reserves", "reserve_id", rs.get("reserve_id"), end_ago + 3)
                    if site["status"] == "termine" and i < 2:
                        await api("PATCH", f"/site/reserves/{rs['reserve_id']}", ok_missing=True)
            for i, t in enumerate(tasks[:8]):
                ck = await api("POST", "/site/checklist", json={
                    "project": site["name"], "doc_id": main_q["doc_id"],
                    "label": f"Validar conclusão — {t['name']}", "lot": t["name"]}, ok_missing=True)
                if ck:
                    stats["checklist"] += 1
                    mark("site_checklist", "item_id", ck.get("item_id"), started - 5 if started else 0)
                    if t["progress"] == 100:
                        await api("PATCH", f"/site/checklist/{ck['item_id']}", ok_missing=True)

        # ---- pontos (RH): histórico das equipas afetas à obra
        if site["masons"]:
            pool = masons_by_country.get(site["country"], [])
            off = used.get(site["country"], 0)
            crew = [pool[(off + i) % len(pool)] for i in range(min(site["masons"], len(pool)))]
            used[site["country"]] = off + len(crew)
            stats["pontos"] += await _timesheets(db, uid, site, pid, tasks, crew)

        # ---- plantas de execução (PDF A3 multi-folha + DXF), via upload real
        if site["plans"] and site["status"] != "prospect" or site["key"] == "miami":
            meta = {"site": site["name"], "client": next((c.get("company") or f"{c.get('first_name')} {c.get('last_name')}")
                                                          for c in D.CLIENTS if c["key"] == site["client"]),
                    "place": f"{site['city']}, {country_label}"}
            pdf = build_execution_pdf(site["plans"], meta)
            up = await api("POST", "/takeoffs/upload", data={"project_id": pid, "display_name": f"Projeto de execução — {site['name']}"},
                           files={"file": (f"Projeto_execucao_{site['key']}.pdf", pdf, "application/pdf")}, ok_missing=True)
            if up and up.get("plan_id"):
                stats["plantas"] += 1
                await api("POST", f"/chantiers/{cid}/attach", json={"kind": "plan", "ref_id": up["plan_id"]}, ok_missing=True)
            if site["key"] in ("martins", "aurora", "atlantico", "jardins", "kensington"):
                dxf = build_architecture_dxf(site["plans"], meta)
                up = await api("POST", "/takeoffs/upload", data={"project_id": pid, "cad_unit": "m",
                                                                 "display_name": f"Planta de arquitetura (DXF) — {site['name']}"},
                               files={"file": (f"Planta_arquitetura_{site['key']}.dxf", dxf, "application/octet-stream")}, ok_missing=True)
                if up and up.get("plan_id"):
                    stats["plantas"] += 1
                    await api("POST", f"/chantiers/{cid}/attach", json={"kind": "plan", "ref_id": up["plan_id"]}, ok_missing=True)

        # ---- despesas do projeto e encomendas de materiais
        if site["status"] != "prospect":
            for label, amount, lot in (("Aluguer de grua / plataforma elevatória", 2400, "Estaleiro"),
                                       ("Licença de ocupação da via pública", 680, "Estaleiro"),
                                       ("Contentores de resíduos (RCD)", 950, "Demolição")):
                await api("POST", f"/projects/{pid}/expenses", json={"label": label, "amount": round(amount * D.COUNTRY_PRICING[site['country']]['coef'], 2), "lot": lot}, ok_missing=True)
            sup = ctx["suppliers"][{"PT": 0, "FR": 3, "GB": 4, "US": 5}[site["country"]]]
            items = [{"designation": des, "unit": unit, "qty": round(max(1, q * site["surface"] * 0.3) if mode != "fix" else q, 1),
                      "unit_price": round(cost * D.COUNTRY_PRICING[site["country"]]["coef"] * 0.85, 2)}
                     for (ref, q, mode) in D.SCOPES[site["scope"]][:6]
                     for (_r, _lot, des, unit, _pu, cost, _v) in [_lib_by_ref()[ref]]]
            order = {"order_id": "cmd_" + secrets.token_hex(6), "user_id": uid, "project": site["name"], "type": "chantier",
                     "supplier": sup, "items": items, "status": "confirmed" if site["status"] == "en_cours" else "delivered",
                     "created_at": _now(), "demo_source": DEMO_SOURCE}
            await db.material_orders.insert_one(dict(order))
            await api("POST", f"/chantiers/{cid}/attach", json={"kind": "purchase", "ref_id": order["order_id"]}, ok_missing=True)
            await api("PUT", f"/chantiers/{cid}/purchases/{order['order_id']}/delivery", json={
                "expected_version": 0, "status": "received" if site["status"] == "termine" else "partial",
                "expected_date": _workday(date.today(), 3).isoformat(),
                "notes": "Entrega parcial — restante material na próxima semana." if site["status"] == "en_cours" else "Material entregue."},
                ok_missing=True)
            stats["encomendas"] += 1
    ctx["summary"]["sites"] = stats


async def _timesheets(db, employer_id: str, site: dict, pid: str, tasks: list[dict], crew: list[dict]) -> int:
    """Histórico de pontos (mesmo esquema que POST /hr/clock-in + clock-out), sem selfie."""
    if site["status"] == "termine":
        end = date.today() - timedelta(days=65 if site["key"] == "martins" else 25)
        days = 12
    else:
        end = date.today() - timedelta(days=1)
        days = min(15, max(4, site["started_days_ago"] // 2))
    # lote trabalhado em cada dia: frente de trabalho atual e anteriores
    worked = [t["resource"] for t in tasks if t["progress"] > 0] or [tasks[0]["resource"]]
    entries = []
    d = end
    day_i = 0
    while day_i < days:
        if d.weekday() < 5:
            lot = worked[max(0, len(worked) - 1 - day_i // 5)]
            for j, m in enumerate(crew):
                start_h = 7 + (j % 2)
                hours = 8.0 if (j + day_i) % 9 else 7.5
                cin = datetime(d.year, d.month, d.day, start_h, 30 if j % 3 else 0, tzinfo=timezone.utc)
                cout = cin + timedelta(hours=hours + 1)
                recent = day_i < 2 and site["status"] != "termine"
                status = "pending" if recent else ("rejected" if (j == 0 and day_i == 6) else "validated")
                jitter = ((j * 37 + day_i * 11) % 60 - 30) / 100000
                out_zone = (j == 1 and day_i == 3)
                entries.append({
                    "entry_id": f"ts_{secrets.token_hex(6)}", "worker_id": m["user_id"], "worker_name": m["name"],
                    "employer_id": employer_id, "project_id": pid, "project_name": site["name"], "lot": lot,
                    "clock_in": cin.isoformat(), "clock_out": cout.isoformat(), "hours": hours, "status": status,
                    "selfie_in": None, "selfie_out": None,
                    "gps_in": {"lat": site["lat"] + (0.01 if out_zone else jitter), "lng": site["lng"] + jitter, "accuracy": 12},
                    "gps_out": {"lat": site["lat"] + jitter, "lng": site["lng"] - jitter, "accuracy": 15},
                    "out_of_zone": out_zone, "distance_in_m": 1100.0 if out_zone else round(abs(jitter) * 111000, 1),
                    "validation_note": "Ponto fora do horário acordado." if status == "rejected" else None,
                    "validated_by": employer_id if status != "pending" else None,
                    "validated_at": cout.isoformat() if status != "pending" else None,
                    "demo_source": DEMO_SOURCE, "created_at": cin.isoformat(),
                })
            day_i += 1
        d -= timedelta(days=1)
    if entries:
        await db.hr_timesheets.insert_many(entries)
    return len(entries)


async def _step_backdate(ctx):
    """Datas coerentes com o histórico de cada obra (os documentos foram criados agora pela API)."""
    db = ctx["db"]
    now = datetime.now(timezone.utc)
    n = 0
    for coll, key, ident, days_ago in ctx.get("backdate", []):
        when = now - timedelta(days=days_ago, hours=(hash(ident) % 8))
        iso = when.isoformat()
        upd = {"created_at": iso, "updated_at": iso}
        if coll == "pro_documents":
            doc = await db.pro_documents.find_one({key: ident}, {"_id": 0, "doc_type": 1, "issue_date": 1})
            if doc and doc.get("issue_date"):
                upd["issue_date"] = iso
            if doc and doc.get("doc_type") == "invoice":
                upd["due_date"] = (when + timedelta(days=30)).isoformat()
        r = await db[coll].update_one({key: ident, "user_id": ctx["owner"]["user_id"]}, {"$set": upd})
        n += r.modified_count
    ctx["summary"]["backdated"] = n


async def _step_extras(ctx):
    """Cliente recorrente sem obra: fatura direta, nota de crédito e refaturação; orçamento pendente."""
    api, clients = ctx["api"], ctx["clients"]
    cid = clients["lumiar"]
    line = {"kind": "line", "line_kind": "ouvrage", "category": "Pintura", "unit": "m2", "vat_rate": 23, "vat_confirmed": True}
    inv = await _new_doc(api, {"doc_type": "invoice", "client_id": cid, "title": "Manutenção — pintura do piso 2",
                               "lines": [{**line, "designation": "Pintura de paredes e tetos interiores, 2 demãos", "qty": 420,
                                          "unit_price_ht": 9.5, "cost_price_ht": 5.6}],
                               "payment_terms": "30 dias"})
    await _issue(api, inv["doc_id"])
    await _status(api, inv["doc_id"], "issued")
    cn = await api("POST", f"/documents/{inv['doc_id']}/to-credit-note", ok_missing=True)
    inv2 = await _new_doc(api, {"doc_type": "invoice", "client_id": cid, "title": "Manutenção — pintura do piso 2 (retificada)",
                                "lines": [{**line, "designation": "Pintura de paredes e tetos interiores, 2 demãos", "qty": 380,
                                           "unit_price_ht": 9.5, "cost_price_ht": 5.6}],
                                "notes": "Substitui a fatura anulada pela nota de crédito (área corrigida: 380 m²).",
                                "payment_terms": "30 dias"})
    await _issue(api, inv2["doc_id"])
    await _status(api, inv2["doc_id"], "issued")
    full = await api("GET", f"/documents/{inv2['doc_id']}")
    await _pay(api, inv2["doc_id"], (full.get("totals") or {}).get("ttc", 0), 4, "Pago por transferência")
    q = await _new_doc(api, {"doc_type": "quote", "client_id": cid, "title": "Remodelação de instalações sanitárias — piso 1",
                             "lines": [{"kind": "section", "title": "Canalização"},
                                       {**line, "category": "Canalização", "designation": "Sanita suspensa com estrutura e placa de comando",
                                        "unit": "u", "qty": 8, "unit_price_ht": 520, "cost_price_ht": 345},
                                       {"kind": "section", "title": "Revestimento cerâmico"},
                                       {**line, "category": "Revestimento cerâmico", "designation": "Revestimento cerâmico de parede em casas de banho",
                                        "qty": 96, "unit_price_ht": 44, "cost_price_ht": 29}],
                             "validity_days": 30})
    await _issue(api, q["doc_id"])
    await _status(api, q["doc_id"], "sent")
    ctx["summary"]["extras"] = {"credit_note": bool(cn), "maintenance_invoices": 2, "pending_quote": 1}


async def _step_tools(ctx):
    """Outros motores determinísticos: MEP (elétrico + canalização), estruturas, urbanismo,
    modelos de orçamento, presets das ferramentas e rentabilidade real por obra."""
    api, db, uid = ctx["api"], ctx["db"], ctx["owner"]["user_id"]
    out = {}
    # MEP — planos de execução eletricidade + canalização, com preços da biblioteca da empresa
    n = 0
    for kind, country, levels, title in (("moradia", "pt", 2, "Moradia Martins — Cascais"),
                                         ("apartamento", "fr", 1, "Appartement Dubois — Paris 9e"),
                                         ("edificio", "pt", 1, "Reabilitação Edifício Aurora — Porto (piso tipo)")):
        st = await api("POST", "/mep/studies/from-input", json={
            "input": mep_input(kind, country, title, levels), "title": f"Eletricidade & canalização — {title}"}, ok_missing=True)
        if st:
            n += 1
            await api("POST", f"/mep/studies/{st['study_id']}/price", ok_missing=True)
    out["mep_studies"] = n
    # Estruturas — os três estudos-exemplo do motor (cálculo, desenhos, automação)
    n = 0
    for flag in ("demonstration", "drawing_demonstration", "automation_demonstration"):
        if await api("POST", "/structuro/calc/studies", json={flag: True}, ok_missing=True):
            n += 1
    out["structure_studies"] = n
    # Urbanismo (licenciamento PT) — processo exemplo
    out["urbanismo"] = bool(await api("POST", "/urbanismo/processos/exemplo", ok_missing=True))
    # Modelos de orçamento reutilizáveis
    lib = _lib_by_ref()

    def tl(refs):
        lines = []
        for ref, qty in refs:
            _r, lot, des, unit, pu, cost, vat = lib[ref]
            lines.append({"kind": "line", "line_kind": "ouvrage", "category": lot, "designation": des, "unit": unit,
                          "qty": qty, "unit_price_ht": pu, "cost_price_ht": cost, "vat_rate": vat})
        return lines
    n = 0
    for name, refs in (("Casa de banho chave-na-mão", [("DEM-02", 18), ("CAN-03", 1), ("CAN-04", 1), ("CER-02", 22), ("ELE-03", 3), ("PIN-01", 12)]),
                       ("Pintura interior de apartamento T3", [("PIN-01", 320), ("PAV-03", 60), ("LIM-01", 95)]),
                       ("Cozinha completa", [("DEM-01", 8), ("CAN-01", 1), ("ELE-03", 6), ("CER-01", 14), ("CIN-03", 1)]),
                       ("Fachada ETICS + pintura", [("EST-02", 400), ("ISO-01", 380), ("PIN-02", 380)])):
        if await api("POST", "/quote-templates", json={"name": name, "title": name, "deposit_pct": 30, "validity_days": 30,
                                                        "notes": "Modelo Teste Websummit", "lines": tl(refs)}, ok_missing=True):
            n += 1
    out["quote_templates"] = n
    out["tool_presets"] = (await api("POST", "/tool-presets/seed-defaults", ok_missing=True) or {}).get("created")
    # Rentabilidade: custos reais lançados por obra (abaixo do previsto — sem alertas de derrapagem)
    n = 0
    quotes = await db.pro_documents.find({"user_id": uid, "doc_type": "quote", "status": "signed", "chantier_id": {"$ne": None}},
                                         {"_id": 0, "doc_id": 1, "lines": 1, "title": 1, "chantier_id": 1}).to_list(50)
    progress = {s["name"]: s["progress"] for s in D.SITES}
    for q in quotes:
        planned = sum((ln.get("cost_price_ht") or 0) * (ln.get("qty") or 0) for ln in q.get("lines") or [])
        ch = await db.chantiers.find_one({"chantier_id": q["chantier_id"]}, {"_id": 0, "name": 1})
        pct = progress.get((ch or {}).get("name"), 50) / 100
        if planned <= 0 or pct <= 0:
            continue
        spent = planned * pct * 0.86
        for label, kind, share, supplier in (("Materiais — betão, alvenarias, revestimentos", "achat", 0.46, "Materiais do Tejo, Lda."),
                                             ("Mão de obra própria (pontos validados)", "main_oeuvre", 0.34, None),
                                             ("Subempreitada caixilharia / AVAC", "sous_traitance", 0.14, None),
                                             ("Aluguer de equipamentos", "location", 0.06, None)):
            if await api("POST", f"/pro/profitability/{q['doc_id']}/costs", json={
                    "label": label, "amount_ht": round(spent * share, 2), "kind": kind, "supplier": supplier}, ok_missing=True):
                n += 1
    out["real_costs"] = n
    # obras concluídas: fecho da obra na rentabilidade (data de fim real)
    ends = {s["name"]: (65 if s["key"] == "martins" else 25) for s in D.SITES if s["status"] == "termine"}
    for q in quotes:
        ch = await db.chantiers.find_one({"chantier_id": q["chantier_id"]}, {"_id": 0, "name": 1})
        name = (ch or {}).get("name")
        if name in ends:
            if await api("PATCH", f"/pro/profitability/{q['doc_id']}/finish", json={"finished": True}, ok_missing=True) is not None:
                when = (datetime.now(timezone.utc) - timedelta(days=ends[name])).isoformat()
                await db.pro_documents.update_one({"doc_id": q["doc_id"], "user_id": uid}, {"$set": {"job_finished_at": when}})
                out["finished_jobs"] = out.get("finished_jobs", 0) + 1
    ctx["summary"]["tools"] = out


# ============================================================================ arranque

async def run_seed(app, db, hash_password, new_user_id, force: bool = False) -> dict:
    try:
        return await seed_teste_websummit(app, db, hash_password, new_user_id, force=force)
    except Exception as exc:  # noqa: BLE001
        logger.exception("demo_tws seed failed")
        await db.demo_seed_state.update_one({"_id": STATE_ID}, {"$set": {"status": "error", "error": str(exc)[:500]}}, upsert=True)
        return {"status": "error", "error": str(exc)}


async def run_on_startup(app, db, hash_password, new_user_id) -> dict:
    """Chamado no arranque (em segundo plano). Desligável com TESTE_WEBSUMMIT_SEED=off."""
    if (os.environ.get("TESTE_WEBSUMMIT_SEED") or "on").lower() == "off":
        return {"status": "disabled"}
    return await run_seed(app, db, hash_password, new_user_id)
