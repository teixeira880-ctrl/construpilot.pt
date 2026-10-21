from datetime import datetime, timezone
import os
import secrets

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from core.db import db
from core.security import admin_user, current_user
from core.account_purge import purge_user_data
from engines.catalog import LOTS, REGIONS
from engines import price_search
from engines.postal_diagnostics import PostalDiagnostics

router = APIRouter(prefix="/admin", tags=["admin"], dependencies=[Depends(admin_user)])


@router.get("/postal/diagnostics", response_model=PostalDiagnostics)
async def postal_diagnostics():
    from engines.postal_diagnostics import diagnose
    return await diagnose()


@router.get("/inbox")
async def admin_inbox(hours: int = 168) -> dict:
    """Boîte de réception admin — vue consolidée des demandes et incidents récents.

    Renvoie leads récents + nouveaux users + devis envoyés + erreurs client
    pour permettre à l'équipe de tout suivre depuis une seule page.
    """
    from datetime import timedelta
    since = datetime.now(timezone.utc) - timedelta(hours=hours)
    since_iso = since.isoformat()

    # Leads (contact form / lead gen)
    leads_cur = db.leads.find({"created_at": {"$gte": since_iso}},
                                {"_id": 0}).sort("created_at", -1).limit(50)
    leads = await leads_cur.to_list(50)

    # Nouveaux utilisateurs (>= depuis N heures)
    users_cur = db.users.find({"created_at": {"$gte": since_iso}},
                                {"_id": 0, "user_id": 1, "email": 1, "name": 1,
                                 "role": 1, "plan": 1, "created_at": 1}
                                ).sort("created_at", -1).limit(50)
    new_users = await users_cur.to_list(50)

    # Devis envoyés (activité pros)
    sends_cur = db.quote_sends.find({"sent_at": {"$gte": since_iso}},
                                     {"_id": 0, "log_id": 1, "user_id": 1,
                                      "client_email": 1, "client_name": 1,
                                      "total_ttc": 1, "sent_at": 1,
                                      "signed": 1, "opened_at": 1}
                                     ).sort("sent_at", -1).limit(50)
    sends = await sends_cur.to_list(50)

    # Erreurs client
    errs_cur = db.client_errors.find({"created_at": {"$gte": since}},
                                       {"_id": 0}).sort("created_at", -1).limit(30)
    errs = await errs_cur.to_list(30)

    # Téléchargements du pitch deck investisseurs (leads VC)
    deck_cur = db.deck_downloads.find({"created_at": {"$gte": since_iso}},
                                       {"_id": 0}).sort("created_at", -1).limit(50)
    deck_downloads = await deck_cur.to_list(50)

    # Devis signés dans la fenêtre (à célébrer)
    signed_count = sum(1 for s in sends if s.get("signed"))
    open_count = sum(1 for s in sends if s.get("opened_at") and not s.get("signed"))

    return {
        "hours": hours,
        "counts": {
            "new_leads": len(leads),
            "new_users": len(new_users),
            "quotes_sent": len(sends),
            "quotes_signed": signed_count,
            "quotes_opened": open_count,
            "client_errors": len(errs),
            "deck_downloads": len(deck_downloads),
        },
        "leads": leads,
        "new_users": new_users,
        "recent_sends": sends,
        "deck_downloads": deck_downloads,
        "recent_errors": [
            {"created_at": (e.get("created_at").isoformat()
                             if hasattr(e.get("created_at"), "isoformat")
                             else e.get("created_at_iso")),
             "message": e.get("message"), "url": e.get("url"),
             "user_id": e.get("user_id")}
            for e in errs
        ],
    }


@router.get("/stats")
async def stats() -> dict:
    users = await db.users.count_documents({})
    projects = await db.projects.count_documents({})
    leads = await db.leads.count_documents({})
    quotes = await db.quote_analyses.count_documents({})
    top = await db.search_stats.find({}, {"_id": 0}).sort("count", -1).to_list(10)
    plans = await db.users.aggregate([{"$group": {"_id": "$plan", "count": {"$sum": 1}}}]).to_list(10)
    agg = await db.projects.aggregate([
        {"$group": {"_id": None,
                    "volume": {"$sum": {"$ifNull": ["$estimation.total_avg", 0]}}}},
    ]).to_list(1)
    volume = round((agg[0]["volume"] if agg else 0) or 0, 2)
    return {"users": users, "projects": projects, "leads": leads, "quote_analyses": quotes,
            "top_searches": top, "plans": [{"plan": p["_id"] or "free", "count": p["count"]} for p in plans],
            "estimated_volume": volume}


@router.get("/drill/{metric}")
async def drill_metric(metric: str) -> dict:
    """Détail cliquable d'un indicateur du tableau de bord admin.

    Retourne { title, description, columns:[{key,label}], rows:[...] } avec les coordonnées
    (nom, e-mail, téléphone, société) pour cibler une campagne publicitaire.
    """
    users = await db.users.find({}, {"_id": 0, "user_id": 1, "name": 1, "email": 1,
                                      "plan": 1, "role": 1, "phone": 1, "city": 1,
                                      "brand_city": 1, "company": 1, "brand_company_name": 1,
                                      "brand_phone": 1, "created_at": 1}).to_list(10000)
    umap = {u["user_id"]: u for u in users}

    def _contact(uid):
        u = umap.get(uid, {})
        return {
            "user_name": u.get("name") or "—",
            "user_email": u.get("email") or "—",
            "user_phone": u.get("phone") or u.get("brand_phone") or "—",
            "user_company": u.get("company") or u.get("brand_company_name") or "—",
            "user_plan": u.get("plan") or "free",
        }

    CONTACT_COLS = [
        {"key": "user_name", "label": "Nome"},
        {"key": "user_email", "label": "E-mail"},
        {"key": "user_phone", "label": "Telefone"},
        {"key": "user_company", "label": "Sociedade"},
        {"key": "user_plan", "label": "Planta"},
    ]

    if metric == "users":
        devs = await db.known_devices.find({}, {"_id": 0, "user_id": 1, "last_seen": 1}).to_list(50000)
        seen: dict[str, str] = {}
        for d in devs:
            uid, ls = d.get("user_id"), d.get("last_seen")
            if uid and ls and ls > seen.get(uid, ""):
                seen[uid] = ls
        rows = [{**_contact(u["user_id"]), "role": u.get("role") or "user",
                 "city": u.get("city") or u.get("brand_city") or "—",
                 "last_seen": seen.get(u["user_id"]) or "",
                 "created_at": u.get("created_at")} for u in users]
        rows.sort(key=lambda r: r.get("created_at") or "", reverse=True)
        return {"title": "Utilizadores", "description": "Todas as contas registadas — público-alvo publicitário direto.",
                "conditions": ["Coleção `users`, sem filtro de data: total acumulado desde a abertura", "Todas as funções (particular, profissional, membro de equipa, admin) e todos os planos, contas não verificadas incluídas", "As contas eliminadas deixam de ser contadas", "Cada linha = uma conta (nunca duplicada por e-mail: o e-mail é único)"],
                "columns": CONTACT_COLS + [{"key": "role", "label": "Função"},
                                           {"key": "city", "label": "Cidade"},
                                           {"key": "last_seen", "label": "Última atividade"},
                                           {"key": "created_at", "label": "Registado em"}],
                "rows": rows}

    if metric in ("projects", "estimated_volume"):
        projs = await db.projects.find({}, {"_id": 0, "estimation.lots": 0}).to_list(10000)
        rows = []
        for p in projs:
            val = round(((p.get("estimation") or {}).get("total_avg") or 0), 2)
            rows.append({**_contact(p.get("user_id")),
                         "project": p.get("name") or "Projeto",
                         "project_type": p.get("project_type") or "—",
                         "city": p.get("city") or p.get("region") or "—",
                         "value_eur": val,
                         "created_at": p.get("created_at")})
        rows.sort(key=lambda r: r["value_eur"] if metric == "estimated_volume" else (r.get("created_at") or ""),
                  reverse=True)
        title = "Volume estimado (por projeto)" if metric == "estimated_volume" else "Projetos"
        return {"title": title,
                "description": "Projetos e respetivos promotores — potencial de despesa e contactos.",
                "conditions": ["Coleção `projects` (estimador particular / projetos inteligentes), sem filtro de data", "Um projeto = uma estimativa guardada por uma conta; os rascunhos não guardados não contam"] + (["Volume = soma de `estimation.total_avg` (média baixa/alta) de todos os projetos, c/ IVA estimado, nunca orçamentos reais assinados", "Um projeto sem estimativa conta 0 €"] if metric == "estimated_volume" else ["Ordenado do mais recente para o mais antigo"]),
                "columns": [{"key": "project", "label": "Projeto"},
                            {"key": "project_type", "label": "Type"},
                            {"key": "city", "label": "Cidade"},
                            {"key": "value_eur", "label": "Valor estimado (€)"}] + CONTACT_COLS
                + [{"key": "created_at", "label": "Criado em"}],
                "rows": rows}

    if metric == "leads":
        leads = await db.leads.find({}, {"_id": 0}).sort("created_at", -1).to_list(2000)
        rows = [{"name": l.get("name") or "—", "email": l.get("email") or "—",
                 "phone": l.get("phone") or "—", "address": l.get("address") or "—",
                 "budget": l.get("budget") or "—", "status": l.get("status") or "nouveau",
                 "description": (l.get("description") or "")[:160],
                 "created_at": l.get("created_at")} for l in leads]
        return {"title": "Pedidos de orçamento",
                "description": "Potenciais clientes que pediram um orçamento — público-alvo publicitário quente.",
                "conditions": ["Coleção `leads`, sem filtro de data: todos os pedidos recebidos desde a abertura", "Fontes: formulário de contacto, página de empresa dos profissionais, estimativa com contactos, importação", "Os pedidos tratados / recusados continuam a ser contados (foram de facto recebidos)", "Apresentação limitada aos 2 000 mais recentes"],
                "columns": [{"key": "name", "label": "Nome"}, {"key": "email", "label": "E-mail"},
                            {"key": "phone", "label": "Telefone"}, {"key": "address", "label": "Morada"},
                            {"key": "budget", "label": "Orçamento"}, {"key": "status", "label": "Estado"},
                            {"key": "description", "label": "Necessidade"},
                            {"key": "created_at", "label": "Recebido em"}],
                "rows": rows}

    if metric == "quote_analyses":
        qs = await db.quote_analyses.find({}, {"_id": 0}).sort("created_at", -1).to_list(2000)
        projs = await db.projects.find({}, {"_id": 0, "project_id": 1, "name": 1}).to_list(10000)
        pmap = {p["project_id"]: p.get("name") for p in projs if p.get("project_id")}
        rows = [{**_contact(q.get("user_id")),
                 "company_analysed": q.get("company") or "—",
                 "project": pmap.get(q.get("project_id")) or "—",
                 "created_at": q.get("created_at")} for q in qs]
        return {"title": "Orçamentos analisados",
                "description": "Utilizadores que analisaram um orçamento — forte interesse no produto.",
                "conditions": ["Coleção `quote_analyses`: orçamentos PDF/foto digitalizados pela ferramenta «Analisar um orçamento», sem filtro de data", "NÃO são os orçamentos criados no editor (ver separador Pedidos → Orçamentos enviados)", "Uma análise = uma linha, o mesmo utilizador pode aparecer várias vezes"],
                "columns": [{"key": "company_analysed", "label": "Empresa analisada"},
                            {"key": "project", "label": "Projeto"}] + CONTACT_COLS
                + [{"key": "created_at", "label": "Analisado em"}],
                "rows": rows}

    if metric in ("total_revenue", "transactions"):
        q = {"payment_status": "paid"} if metric == "total_revenue" else {}
        txs = await db.payment_transactions.find(q, {"_id": 0}).sort("created_at", -1).to_list(5000)
        rows = [{**_contact(t.get("user_id")),
                 "plan_bought": t.get("plan_id") or "—",
                 "amount_eur": round((t.get("amount_cents") or 0) / 100, 2),
                 "status": t.get("payment_status") or t.get("status") or "—",
                 "created_at": t.get("created_at")} for t in txs]
        title = "Receita total (pagamentos)" if metric == "total_revenue" else "Transactions"
        return {"title": title, "description": "Clientes pagantes — público-alvo de retenção e upsell.",
                "conditions": ["Collection `payment_transactions` (Stripe)"] + (["Filtro: apenas payment_status = paid; montantes em euros, reembolsos não deduzidos"] if metric == "total_revenue" else ["Todas as transações, incluindo pendentes / falhadas (ver coluna estado)"]),
                "columns": CONTACT_COLS + [{"key": "plan_bought", "label": "Plano comprado"},
                                           {"key": "amount_eur", "label": "Montante (€)"},
                                           {"key": "status", "label": "Estado"},
                                           {"key": "created_at", "label": "Data"}],
                "rows": rows}

    if metric in ("active_subscriptions", "active_project_pass"):
        kind = "subscription" if metric == "active_subscriptions" else "one_time"
        q = {"status": "active", "kind": kind}
        if kind == "one_time":
            q["$or"] = [{"expires_at": {"$exists": False}},
                        {"expires_at": {"$gt": datetime.now(timezone.utc).isoformat()}}]
        ents = await db.entitlements.find(q, {"_id": 0}).to_list(5000)
        rows = [{**_contact(e.get("user_id")),
                 "plan_code": e.get("plan_code") or e.get("plan_id") or "—",
                 "granted_at": e.get("granted_at")} for e in ents]
        title = "Subscrições ativas" if kind == "subscription" else "Project Pass ativos"
        return {"title": title, "description": "Clientes com acesso ativo — público-alvo prioritário de upsell.",
                "conditions": ["Collection `entitlements` : status = active" + (" e kind = subscription" if kind == "subscription" else " e kind = one_time, não expirado (expires_at ausente ou futuro)"), "Um acesso oferecido manualmente pelo admin conta como ativo", "Um utilizador com vários acessos aparece várias vezes"],
                "columns": CONTACT_COLS + [{"key": "plan_code", "label": "Oferta"},
                                           {"key": "granted_at", "label": "Desde"}],
                "rows": rows}

    raise HTTPException(404, "Indicador desconhecido")


def _win_label(hours: int) -> str:
    return {24: "Últimas 24 horas", 168: "Últimos 7 dias", 720: "Últimos 30 dias"}.get(hours, f'{hours} últimas horas')


@router.get("/drill-inbox/{metric}")
async def drill_inbox(metric: str, hours: int = 168) -> dict:
    """Détail cliquable des compteurs de la boîte de réception : qui est compté, et sous quelles conditions (fenêtre, filtre)."""
    from datetime import timedelta
    hours = max(1, min(hours, 24 * 366))
    since_dt = datetime.now(timezone.utc) - timedelta(hours=hours)
    since = since_dt.isoformat()
    win = _win_label(hours)
    users = await db.users.find({}, {"_id": 0, "user_id": 1, "name": 1, "email": 1, "plan": 1, "brand_company_name": 1, "company": 1}).to_list(10000)
    umap = {u["user_id"]: u for u in users}
    pro = lambda uid: (umap.get(uid) or {}).get("email") or (uid or "—")  # noqa: E731
    base = {"window_hours": hours, "since": since}

    if metric == "new_leads":
        rows = await db.leads.find({"created_at": {"$gte": since}}, {"_id": 0}).sort("created_at", -1).to_list(50)
        return {**base, "title": f'Novos leads — {win}',
                "description": "Qualquer pedido de obras registado na coleção `leads` no período, qualquer que seja a sua origem.",
                "conditions": [f"Janela: created_at ≥ {since[:16].replace('T', ' ')} UTC ({win})",
                               "Origens incluídas: formulário de contacto do site, página de empresa (`company_page`), estimativa com contactos, importação",
                               "Um lead «tratado / recusado» continua a ser contado (foi de facto recebido no período)",
                               "Apresentação limitada aos 50 mais recentes"],
                "columns": [{"key": "created_at", "label": "Recebido em"}, {"key": "name", "label": "Nome"}, {"key": "email", "label": "E-mail"},
                            {"key": "phone", "label": "Telefone"}, {"key": "source", "label": "Fonte"}, {"key": "department", "label": "Dep."},
                            {"key": "status", "label": "Estado"}, {"key": "assigned", "label": "Profissional atribuído"}, {"key": "description", "label": "Necessidade"}],
                "rows": [{"created_at": l.get("created_at"), "name": l.get("name") or "—", "email": l.get("email") or "—", "phone": l.get("phone") or "—",
                          "source": l.get("source") or "site", "department": l.get("department") or "—",
                          "status": l.get("handling_status") or l.get("status") or "nouveau", "assigned": pro(l.get("assigned_to")) if l.get("assigned_to") else "—",
                          "description": (l.get("description") or "")[:160]} for l in rows]}

    if metric == "new_users":
        rows = await db.users.find({"created_at": {"$gte": since}}, {"_id": 0, "email": 1, "name": 1, "role": 1, "plan": 1, "created_at": 1,
                                                                        "brand_company_name": 1, "company": 1, "city": 1, "brand_city": 1, "email_verified": 1}).sort("created_at", -1).to_list(50)
        return {**base, "title": f'Novas contas — {win}',
                "description": "Contas criadas no período (registo por e-mail, Google ou convite de equipa), todas as funções e planos.",
                "conditions": [f"Janela: users.created_at ≥ {since[:16].replace('T', ' ')} UTC ({win})",
                               "Funções incluídas: particular, profissional, membro de equipa, admin — contas não verificadas incluídas",
                               "As contas eliminadas deixam de aparecer", "Apresentação limitada aos 50 mais recentes"],
                "columns": [{"key": "created_at", "label": "Criado em"}, {"key": "name", "label": "Nome"}, {"key": "email", "label": "E-mail"},
                            {"key": "role", "label": "Função"}, {"key": "plan", "label": "Planta"}, {"key": "company", "label": "Sociedade"},
                            {"key": "city", "label": "Cidade"}, {"key": "verified", "label": "E-mail verificado"}],
                "rows": [{"created_at": u.get("created_at"), "name": u.get("name") or "—", "email": u.get("email"), "role": u.get("role") or "user",
                          "plan": u.get("plan") or "free", "company": u.get("brand_company_name") or u.get("company") or "—",
                          "city": u.get("brand_city") or u.get("city") or "—", "verified": "oui" if u.get("email_verified") else "non"} for u in rows]}

    if metric in ("quotes_sent", "quotes_signed", "quotes_opened"):
        sends = await db.quote_sends.find({"sent_at": {"$gte": since}}, {"_id": 0}).sort("sent_at", -1).to_list(50)
        if metric == "quotes_signed":
            sends = [s for s in sends if s.get("signed")]
        if metric == "quotes_opened":
            sends = [s for s in sends if s.get("opened_at") and not s.get("signed")]
        titles = {"quotes_sent": "Orçamentos enviados", "quotes_signed": "Orçamentos assinados", "quotes_opened": "Orçamentos abertos (não assinados)"}
        extra = {"quotes_sent": "Qualquer envio de orçamento por e-mail a partir do editor (registo `quote_sends`).",
                 "quotes_signed": "Envios cujo cliente assinou eletronicamente (campo `signed` = verdadeiro) — a assinatura deve referir-se a um envio feito na janela.",
                 "quotes_opened": "Envios cuja ligação foi aberta pelo cliente (`opened_at` preenchido) mas ainda não assinados."}[metric]
        return {**base, "title": f"{titles[metric]} — {win}", "description": extra,
                "conditions": [f"Janela: quote_sends.sent_at ≥ {since[:16].replace('T', ' ')} UTC ({win}) — conta a data de ENVIO, não a de assinatura",
                               "Um orçamento criado mas nunca enviado por e-mail não é contado aqui (ver a coleção dos documentos profissionais)",
                               "Um mesmo orçamento enviado duas vezes conta como dois envios", "Apresentação limitada aos 50 mais recentes"],
                "columns": [{"key": "sent_at", "label": "Enviado em"}, {"key": "pro", "label": "Profissional (conta)"}, {"key": "client_name", "label": "Cliente"},
                            {"key": "client_email", "label": "E-mail cliente"}, {"key": "total_ttc", "label": "c/ IVA"}, {"key": "state", "label": "Estado"},
                            {"key": "email_status", "label": "E-mail"}, {"key": "opened_at", "label": "Aberto a"}, {"key": "signed_at", "label": "Assinado a"}],
                "rows": [{"sent_at": s.get("sent_at"), "pro": pro(s.get("user_id")), "email_status": s.get("email_status") or "en file", "client_name": s.get("client_name") or "—", "client_email": s.get("client_email") or "—",
                          "total_ttc": f"{(s.get('total_ttc') or 0):,.2f} €".replace(",", " "), "state": "signé" if s.get("signed") else "ouvert" if s.get("opened_at") else "envoyé",
                          "opened_at": s.get("opened_at") or "—", "signed_at": s.get("signed_at") or "—"} for s in sends]}

    if metric == "client_errors":
        errs = await db.client_errors.find({"created_at": {"$gte": since_dt}}, {"_id": 0}).sort("created_at", -1).to_list(30)
        return {**base, "title": f'Erros do lado do cliente — {win}',
                "description": "Erros JavaScript reportados automaticamente pelo navegador dos utilizadores (coleção `client_errors`).",
                "conditions": [f"Janela: created_at ≥ {since[:16].replace('T', ' ')} UTC ({win})", "Limpeza automática após 30 dias (índice TTL)", "Apresentação limitada aos 30 mais recentes"],
                "columns": [{"key": "created_at", "label": "Data"}, {"key": "message", "label": "Mensagem"}, {"key": "url", "label": "Página"}, {"key": "user", "label": "Utilizador"}],
                "rows": [{"created_at": e["created_at"].isoformat() if hasattr(e.get("created_at"), "isoformat") else e.get("created_at_iso"),
                          "message": (e.get("message") or "")[:200], "url": e.get("url") or "—", "user": pro(e.get("user_id")) if e.get("user_id") else "anonyme"} for e in errs]}

    if metric == "deck_downloads":
        rows = await db.deck_downloads.find({"created_at": {"$gte": since}}, {"_id": 0}).sort("created_at", -1).to_list(50)
        return {**base, "title": f'Apresentação para investidores — {win}',
                "description": "Pessoas que preencheram o formulário da página Investidores para descarregar o pitch deck (coleção `deck_downloads`).",
                "conditions": [f"Janela: created_at ≥ {since[:16].replace('T', ' ')} UTC ({win})",
                               "Cada descarga é uma linha: a mesma pessoa pode aparecer várias vezes", "Apresentação limitada aos 50 mais recentes"],
                "columns": [{"key": "created_at", "label": "Data"}, {"key": "name", "label": "Nome"}, {"key": "email", "label": "E-mail"}, {"key": "fund", "label": "Fundo / sociedade"},
                            {"key": "note", "label": "Mensagem"}, {"key": "referer", "label": "Provenance"}],
                "rows": [{"created_at": d.get("created_at"), "name": d.get("name") or "—", "email": d.get("email") or "—", "fund": d.get("fund") or "—",
                          "note": (d.get("note") or "")[:160], "referer": d.get("referer") or "—"} for d in rows]}

    raise HTTPException(404, "Indicador desconhecido")



class BulkEmailBody(BaseModel):
    recipients: list[str]
    subject: str
    message: str


@router.post("/bulk-email")
async def admin_bulk_email(body: BulkEmailBody, admin=Depends(admin_user)) -> dict:
    """Envoie un e-mail promotionnel à une liste de contacts sélectionnés dans le détail admin."""
    import os
    import re
    import asyncio
    from engines.emailer import send_email, wrap_html
    seen: set[str] = set()
    emails: list[str] = []
    for e in body.recipients or []:
        e = (e or "").strip().lower()
        if e and e not in seen and re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", e):
            seen.add(e)
            emails.append(e)
    emails = emails[:200]
    if not emails:
        raise HTTPException(400, "Nenhum destinatário válido")
    subject = (body.subject or "").strip()[:200] or "ConstruPilot"
    msg_html = (body.message or "").strip()
    if not msg_html:
        raise HTTPException(400, "Message vide")
    html = wrap_html(subject, msg_html.replace("\n", "<br>"),
                     unsubscribe_url=f"{os.getenv('FRONTEND_URL', '')}/desinscription")

    async def _one(addr: str) -> bool:
        try:
            await send_email(addr, subject, html)
            return True
        except Exception:  # noqa: BLE001
            return False

    sent = 0
    for i in range(0, len(emails), 10):
        chunk = emails[i:i + 10]
        res = await asyncio.gather(*[_one(a) for a in chunk])
        sent += sum(1 for r in res if r)
    await db.email_campaigns.insert_one({
        "campaign_id": "camp_" + os.urandom(5).hex(),
        "subject": subject,
        "message": msg_html[:5000],
        "recipients_count": len(emails),
        "recipients_sample": emails[:50],
        "sent": sent,
        "failed": len(emails) - sent,
        "sent_by": (admin or {}).get("email") or (admin or {}).get("user_id"),
        "created_at": datetime.now(timezone.utc).isoformat(),
    })
    return {"ok": True, "sent": sent, "failed": len(emails) - sent, "total": len(emails)}


@router.get("/welcome-email/preview", response_class=HTMLResponse)
async def welcome_email_preview(name: str = "", admin=Depends(admin_user)):
    """Aperçu HTML de l'e-mail publicitaire de bienvenue (nouveaux utilisateurs)."""
    from engines.welcome_marketing import welcome_marketing_html
    cta = f"{os.getenv('FRONTEND_URL', 'https://construpilot.pt')}/?utm_source=email&utm_medium=welcome&utm_campaign=onboarding"
    html = welcome_marketing_html(name.strip() or None, cta,
                                  unsubscribe_url=f"{os.getenv('FRONTEND_URL', '')}/desinscription")
    return HTMLResponse(html)


def _parse_recipients(raw: str) -> list[str]:
    """Extrait les e-mails valides d'une chaîne (séparateurs: , ; espace ou saut de ligne)."""
    import re
    parts = re.split(r"[,;\s]+", (raw or "").strip())
    seen: set[str] = set()
    out: list[str] = []
    for p in parts:
        e = p.strip().lower()
        if e and e not in seen and re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", e):
            seen.add(e)
            out.append(e)
    return out[:200]


async def _send_marketing(recipients: list[str], subject: str, html: str,
                          campaign_type: str, actor: str | None) -> dict:
    """Envoie un e-mail marketing à plusieurs destinataires + journalise la campagne."""
    import asyncio
    from engines.emailer import send_email

    async def _one(addr: str) -> bool:
        try:
            await send_email(addr, subject, html, from_name="ConstruPilot")
            return True
        except Exception:  # noqa: BLE001
            return False

    sent = 0
    for i in range(0, len(recipients), 10):
        chunk = recipients[i:i + 10]
        res = await asyncio.gather(*[_one(a) for a in chunk])
        sent += sum(1 for r in res if r)
    failed = len(recipients) - sent
    await db.email_campaigns.insert_one({
        "campaign_id": "mk_" + secrets.token_hex(5), "type": campaign_type,
        "subject": subject, "recipients_count": len(recipients),
        "recipients_sample": recipients[:50], "sent": sent, "failed": failed,
        "sent_by": actor or "admin", "created_at": datetime.now(timezone.utc).isoformat()})
    return {"ok": True, "sent": sent, "failed": failed, "recipients": len(recipients)}


class WelcomeTestBody(BaseModel):
    to: str
    name: str = ""


@router.post("/welcome-email/test")
async def welcome_email_test(body: WelcomeTestBody, admin=Depends(admin_user)) -> dict:
    """Envoie l'e-mail publicitaire de bienvenue à une ou plusieurs adresses via Resend."""
    from engines.welcome_marketing import welcome_marketing_html, SUBJECT
    recipients = _parse_recipients(body.to)
    if not recipients:
        raise HTTPException(400, "Nenhum endereço de e-mail válido")
    cta = f"{os.getenv('FRONTEND_URL', 'https://construpilot.pt')}/?utm_source=email&utm_medium=welcome&utm_campaign=onboarding"
    html = welcome_marketing_html((body.name or "").strip() or None, cta,
                                  unsubscribe_url=f"{os.getenv('FRONTEND_URL', '')}/desinscription")
    actor = (admin or {}).get("email") or (admin or {}).get("user_id")
    return await _send_marketing(recipients, SUBJECT, html, "mk_welcome", actor)


def _prospect_render(audience: str, name: str):
    """(subject, html) pour l'e-mail prospect selon l'audience: 'particulier' | 'pro'."""
    from engines.prospect_marketing import (prospect_particulier_html, prospect_pro_html,
                                            PART_SUBJECT, PRO_SUBJECT)
    front = os.getenv("FRONTEND_URL", "https://construpilot.pt")
    unsub = f"{os.getenv('FRONTEND_URL', '')}/desinscription"
    first = (name or "").strip() or None
    if audience == "pro":
        cta = f"{front}/?utm_source=email&utm_medium=prospect&utm_campaign=prospect_pro"
        return PRO_SUBJECT, prospect_pro_html(first, cta, unsubscribe_url=unsub)
    cta = f"{front}/?utm_source=email&utm_medium=prospect&utm_campaign=prospect_particulier"
    return PART_SUBJECT, prospect_particulier_html(first, cta, unsubscribe_url=unsub)


@router.get("/prospect-email/preview", response_class=HTMLResponse)
async def prospect_email_preview(audience: str = "particulier", name: str = "",
                                 admin=Depends(admin_user)):
    """Aperçu HTML de l'e-mail prospect (audience: 'particulier' ou 'pro')."""
    _, html = _prospect_render(audience, name)
    return HTMLResponse(html)


class ProspectTestBody(BaseModel):
    to: str
    audience: str = "particulier"
    name: str = ""


@router.post("/prospect-email/test")
async def prospect_email_test(body: ProspectTestBody, admin=Depends(admin_user)) -> dict:
    """Envoie l'e-mail prospect à une ou plusieurs adresses via Resend."""
    recipients = _parse_recipients(body.to)
    if not recipients:
        raise HTTPException(400, "Nenhum endereço de e-mail válido")
    audience = "pro" if (body.audience or "").strip().lower() == "pro" else "particulier"
    subject, html = _prospect_render(audience, body.name)
    actor = (admin or {}).get("email") or (admin or {}).get("user_id")
    res = await _send_marketing(recipients, subject, html, f"mk_prospect_{audience}", actor)
    return {**res, "audience": audience}




@router.get("/campaigns/upsell/stats")
async def upsell_stats(weeks: int = 12, admin=Depends(admin_user)):
    from engines.upsell import conversion_stats
    return await conversion_stats(weeks=min(52, max(1, weeks)))


@router.post("/campaigns/upsell/run")
async def run_upsell_now(step: str = "j3", admin=Depends(admin_user)):
    """Déclenche immédiatement l'email d'incitation J+3 ou la relance J+10 (cron 10:00 / 10:20 UTC)."""
    from engines.upsell import run_upsell_emails, run_upsell_j10_emails
    return await (run_upsell_j10_emails() if step == "j10" else run_upsell_emails())


@router.post("/campaigns/upsell/preview")
async def preview_upsell(audience: str = "pro", step: str = "j3", admin=Depends(admin_user)):
    """Envoie l'email d'incitation (Pro ou Particulier, J+3 ou J+10) à l'admin connecté pour vérification."""
    from engines.emailer import send_email, wrap_html
    from engines.upsell import _template, _template_j10, _weekly_promo_code
    from routes.emails import build_unsubscribe_url
    fake = {"name": admin.get("name") or "", "account_type": "pro" if audience == "pro" else "particulier",
            "role": "pro" if audience == "pro" else "user"}
    if step == "j10":
        code, exp = await _weekly_promo_code()
        subject, body, cta = _template_j10(fake, code, exp)
        cta_url = f"{os.getenv('FRONTEND_URL', '')}/tarifs?promo={code}"
    else:
        subject, body, cta = _template(fake)
        cta_url = f"{os.getenv('FRONTEND_URL', '')}/tarifs"
    html = wrap_html(subject, body, cta_url=cta_url, cta_label=cta,
                     unsubscribe_url=build_unsubscribe_url(admin["user_id"]))
    await send_email(admin["email"], f'[PRÉ-VISUALIZAÇÃO] {subject}', html)
    return {"ok": True, "to": admin["email"], "subject": subject}



@router.get("/campaigns")
async def admin_campaigns() -> dict:
    """Historique des campagnes e-mail groupées."""
    rows = await db.email_campaigns.find({}, {"_id": 0, "message": 0, "recipients_sample": 0}) \
        .sort("created_at", -1).to_list(500)
    return {"campaigns": rows}




@router.get("/prices")
async def prices() -> list:
    overrides = {d["key"]: d async for d in db.price_reference.find({}, {"_id": 0})}
    return [{**l, **overrides.get(l["key"], {}), "overridden": l["key"] in overrides} for l in LOTS]


class PriceIn(BaseModel):
    mat_eco: float | None = None
    mat_std: float | None = None
    mat_premium: float | None = None
    labour: float | None = None
    hours: float | None = None


@router.put("/prices/{key}")
async def update_price(key: str, body: PriceIn) -> dict:
    updates = {k: v for k, v in body.model_dump().items() if v is not None}
    await db.price_reference.update_one(
        {"key": key}, {"$set": {**updates, "key": key,
                                "updated_at": datetime.now(timezone.utc).isoformat()}}, upsert=True)
    from engines.catalog import LOTS_BY_KEY
    if key in LOTS_BY_KEY:
        LOTS_BY_KEY[key].update(updates)
    return {"key": key, **updates}


@router.delete("/prices/{key}")
async def reset_price(key: str) -> dict:
    await db.price_reference.delete_one({"key": key})
    return {"ok": True}


@router.get("/regions")
async def regions():
    docs = await db.regions.find({}, {"_id": 0}).to_list(500)
    return docs or REGIONS


class RegionIn(BaseModel):
    country: str
    region: str
    coef: float


@router.put("/regions")
async def upsert_region(body: RegionIn):
    from engines.catalog import REGIONS as R
    existing = next((r for r in R if r["country"] == body.country and r["region"] == body.region), None)
    if existing:
        existing["coef"] = body.coef
    else:
        R.append(body.model_dump())
    await db.regions.delete_many({})
    await db.regions.insert_many([dict(r) for r in R])
    return body.model_dump()


@router.get("/users")
async def users():
    return await db.users.find({}, {"_id": 0, "password_hash": 0}).sort("created_at", -1).to_list(500)


class UserIn(BaseModel):
    role: str | None = None
    plan: str | None = None
    account_type: str | None = None
    two_fa_enabled: bool | None = None
    two_fa_email: str | None = None


@router.put("/users/{user_id}")
async def update_user(user_id: str, body: UserIn):
    updates = {k: v for k, v in body.model_dump().items() if v is not None}
    if "account_type" in updates and updates["account_type"] not in ("particulier", "pro", "pro_business"):
        raise HTTPException(400, "Tipo de conta inválido")
    if "two_fa_email" in updates:
        updates["two_fa_email"] = updates["two_fa_email"].strip().lower() or None
    await db.users.update_one({"user_id": user_id}, {"$set": updates})
    return await db.users.find_one({"user_id": user_id}, {"_id": 0, "password_hash": 0})


# Collections purgées lors de la suppression définitive d'un compte : core/account_purge.py


@router.delete("/users/{user_id}")
async def delete_user(user_id: str, admin=Depends(admin_user)) -> dict:
    """Supprime DÉFINITIVEMENT un compte et purge toutes ses données (irréversible)."""
    target = await db.users.find_one({"user_id": user_id}, {"_id": 0})
    if not target:
        raise HTTPException(404, "Utilizador não encontrado")
    if target.get("role") == "admin":
        raise HTTPException(403, "Impossível eliminar uma conta de administrador")
    if user_id == admin["user_id"]:
        raise HTTPException(403, "Não pode eliminar a sua própria conta")
    purged = await purge_user_data(user_id)
    await db.users.delete_one({"user_id": user_id})
    return {"ok": True, "deleted_user": user_id,
            "email": target.get("email"), "purged": purged,
            "purged_total": sum(purged.values())}


@router.get("/projects")
async def all_projects():
    return await db.projects.find({}, {"_id": 0, "estimation.lots": 0}) \
        .sort("created_at", -1).to_list(300)


@router.get("/leads")
async def all_leads():
    return await db.leads.find({}, {"_id": 0}).sort("created_at", -1).to_list(300)


@router.get("/leads/stats")
async def leads_stats() -> dict:
    total = await db.leads.count_documents({})
    particulier = await db.leads.count_documents({"source": {"$regex": "particulier$"}})
    pro = await db.leads.count_documents({"source": {"$regex": "pro$"}})
    landing = await db.leads.count_documents({"source": {"$regex": "^landing"}})
    nouveau = await db.leads.count_documents({"status": "nouveau"})
    gagne = await db.leads.count_documents({"status": "gagné"})
    assignes = await db.leads.count_documents({"assigned_to": {"$nin": [None, ""]}})
    en_attente = await db.leads.count_documents({"assigned_to": {"$nin": [None, ""]}, "handling_status": {"$in": [None, "en_cours"]}})
    pris_en_charge = await db.leads.count_documents({"handling_status": "acceptee"})
    refuses = await db.leads.count_documents({"handling_status": "refusee"})
    auto_assignes = await db.leads.count_documents({"auto_assigned": True})
    conversion = round(pris_en_charge / total * 100) if total else 0
    return {"total": total, "particulier": particulier, "pro": pro,
            "landing": landing, "nouveau": nouveau, "gagne": gagne,
            "assignes": assignes, "en_attente": en_attente,
            "pris_en_charge": pris_en_charge, "refuses": refuses,
            "auto_assignes": auto_assignes, "conversion": conversion}


class LeadStatusIn(BaseModel):
    status: str | None = None
    assigned_to: str | None = None


async def _notify_assigned_pro(pro: dict, lead: dict) -> None:
    """Notifie le pro qu'une demande de travaux lui a été assignée (cloche + e-mail)."""
    name = lead.get("name") or lead.get("email") or "um cliente"
    try:
        await db.notifications.insert_one({
            "notif_id": "n_" + secrets.token_hex(5),
            "user_id": pro["user_id"], "type": "lead_assigned",
            "lead_id": lead.get("lead_id"),
            "message": f'Novo pedido de obras a tratar: {name}',
            "created_at": datetime.now(timezone.utc).isoformat(), "read": False,
        })
    except Exception:
        pass
    try:
        from engines.emailer import send_email, wrap_html
        rows = [
            ("Cliente", lead.get("name") or "—"),
            ("E-mail", lead.get("email") or "—"),
            ("Telefone", lead.get("phone") or "—"),
            ("Morada", lead.get("address") or "—"),
            ("Disponibilidade", lead.get("availability") or "—"),
            ("Orçamento", f"{lead.get('budget')} €" if lead.get("budget") else "—"),
            ("Pedido", lead.get("description") or "—"),
        ]
        body = "".join(f'<p style="margin:0 0 8px 0"><b>{k} :</b> {v}</p>' for k, v in rows)
        html = wrap_html("Novo pedido de obras a tratar",
                         f'<p>Olá,</p><p>Foi-lhe atribuído um pedido de obras:</p>{body}<p>Contacte o cliente para o tratar.</p>')
        await send_email(pro["email"], "Foi-lhe atribuído um pedido de obras — ConstruPilot", html)
    except Exception:
        pass


@router.post("/leads/{lead_id}/invite")
async def invite_lead(lead_id: str) -> dict:
    """Envoie au lead un e-mail l'incitant à créer un compte."""
    lead = await db.leads.find_one({"lead_id": lead_id}, {"_id": 0})
    if not lead:
        raise HTTPException(404, "Pedido não encontrado")
    if not lead.get("email"):
        raise HTTPException(400, "Este pedido não tem endereço de e-mail")
    from routes.leads import send_account_invite
    try:
        await send_account_invite(lead["email"], lead.get("name") or "")
    except Exception as e:
        raise HTTPException(502, f'Envio impossível: {e}')
    await db.leads.update_one({"lead_id": lead_id},
                              {"$set": {"invited_at": datetime.now(timezone.utc).isoformat()}})
    return {"ok": True, "email": lead["email"]}


@router.put("/leads/{lead_id}")
async def update_lead(lead_id: str, body: LeadStatusIn):
    lead = await db.leads.find_one({"lead_id": lead_id}, {"_id": 0})
    if not lead:
        raise HTTPException(404, "Pedido não encontrado")
    upd = {}
    if body.status is not None:
        upd["status"] = body.status
    notify_pro = None
    if body.assigned_to is not None:
        if body.assigned_to == "":
            upd["assigned_to"] = None
            upd["assigned_to_name"] = None
            upd["assigned_at"] = None
        else:
            pro = await db.users.find_one(
                {"user_id": body.assigned_to},
                {"_id": 0, "user_id": 1, "email": 1, "name": 1})
            if not pro:
                raise HTTPException(404, "Profissional não encontrado")
            upd["assigned_to"] = pro["user_id"]
            upd["assigned_to_name"] = pro.get("name") or pro.get("email")
            upd["assigned_at"] = datetime.now(timezone.utc).isoformat()
            upd["candidates"] = []  # attribution manuelle directe : plus de mise en concurrence
            upd["handling_status"] = None
            if lead.get("assigned_to") != pro["user_id"]:
                notify_pro = pro
    if upd:
        await db.leads.update_one({"lead_id": lead_id}, {"$set": upd})
    if notify_pro:
        await _notify_assigned_pro(notify_pro, {**lead, **upd})
        try:
            await db.leads.update_one({"lead_id": lead_id}, {"$push": {"assignment_log": {
                "action": "assignee_manuelle", "user_id": notify_pro["user_id"],
                "user_name": notify_pro.get("name") or notify_pro.get("email"),
                "at": datetime.now(timezone.utc).isoformat()}}})
        except Exception:
            pass
    return await db.leads.find_one({"lead_id": lead_id}, {"_id": 0})


@router.get("/suppliers")
async def suppliers() -> dict:
    extra = await db.suppliers.find({}, {"_id": 0}).to_list(200)
    return {"builtin": price_search.SUPPLIERS, "custom": extra}


class SupplierIn(BaseModel):
    key: str
    name: str
    domain: str
    shipping: float = 30
    free_from: float = 300
    min_order: float = 0
    delivery_days: int = 4
    rating: float = 4.0
    stores: int = 0


@router.post("/suppliers")
async def add_supplier(body: SupplierIn):
    doc = body.model_dump()
    await db.suppliers.update_one({"key": doc["key"]}, {"$set": doc}, upsert=True)
    if not any(s["key"] == doc["key"] for s in price_search.SUPPLIERS):
        price_search.SUPPLIERS.append(doc)
        price_search.SUPPLIERS_BY_KEY[doc["key"]] = doc
    return doc


@router.delete("/suppliers/{key}")
async def delete_supplier(key: str) -> dict:
    await db.suppliers.delete_one({"key": key})
    return {"ok": True}



# ---------- Plans & Monétisation ----------

@router.get("/plans")
async def list_all_plans():
    return await db.plans.find({}, {"_id": 0}).sort("sort_order", 1).to_list(100)


class PlanIn(BaseModel):
    plan_id: str
    code: str
    name: str
    tagline: str | None = None
    description: str | None = None
    audience: str = "particulier"
    kind: str = "subscription"
    amount_cents: int = 0
    currency: str = "eur"
    interval: str | None = None
    lookup_key: str | None = None
    trial_days: int | None = None
    features: list[str] = []
    quotas: dict = {}
    sort_order: int = 100
    active: bool = True
    highlight: bool = False
    badge: str | None = None


@router.post("/plans")
async def upsert_plan(body: PlanIn):
    doc = body.model_dump()
    # Préserver les IDs Stripe existants (ils sont re-synchronisés par sync-stripe)
    existing = await db.plans.find_one({"plan_id": doc["plan_id"]}, {"_id": 0})
    if existing:
        for k in ("stripe_product_id", "stripe_price_id", "synced_at"):
            if existing.get(k):
                doc.setdefault(k, existing[k])
    await db.plans.update_one({"plan_id": doc["plan_id"]}, {"$set": doc}, upsert=True)
    return doc


@router.delete("/plans/{plan_id}")
async def delete_plan(plan_id: str) -> dict:
    await db.plans.delete_one({"plan_id": plan_id})
    return {"ok": True}


@router.post("/plans/sync-stripe")
async def sync_stripe() -> dict:
    from engines import monetization
    await monetization.ensure_stripe_catalog()
    return {"ok": True}


@router.get("/feature-flags")
async def get_flags():
    flags = await db.feature_flags.find_one({"_id": "global"})
    if flags:
        flags.pop("_id", None)
    return flags or {}


@router.put("/feature-flags")
async def set_flags(body: dict):
    body.pop("_id", None)
    await db.feature_flags.update_one({"_id": "global"}, {"$set": body}, upsert=True)
    return body


# ---------- Revenue dashboard (Phase 1 : basique) ----------

@router.get("/revenue")
async def revenue_dashboard() -> dict:
    paid = await db.payment_transactions.find(
        {"payment_status": "paid"}, {"_id": 0}).to_list(5000)
    from collections import defaultdict
    by_plan = defaultdict(lambda: {"count": 0, "revenue_cents": 0})
    total = 0
    for p in paid:
        by_plan[p["plan_id"]]["count"] += 1
        by_plan[p["plan_id"]]["revenue_cents"] += p.get("amount_cents", 0)
        total += p.get("amount_cents", 0)
    active_subs = await db.entitlements.count_documents(
        {"status": "active", "kind": "subscription"})
    active_passes = await db.entitlements.count_documents(
        {"status": "active", "kind": "one_time",
         "$or": [{"expires_at": {"$exists": False}},
                 {"expires_at": {"$gt": datetime.now(timezone.utc).isoformat()}}]})
    return {
        "total_revenue_cents": total,
        "total_revenue_eur": round(total / 100, 2),
        "active_subscriptions": active_subs,
        "active_project_pass": active_passes,
        "by_plan": [{"plan_id": k, **v} for k, v in by_plan.items()],
        "transactions_count": len(paid),
    }


# ---------- Sélecteur de modèle IA ----------

class AiModelIn(BaseModel):
    tier: str


@router.get("/ai-model")
async def get_ai_model() -> dict:
    from engines import ai
    from engines import llm_keys
    current = await ai.get_text_tier()
    return {
        "current": current,
        "openai_key": llm_keys.status(),
        "options": [
            {"tier": k, "label": v["label"], "desc": v["desc"], "model": v["model"], "provider": v["provider"],
             "key_source": "Chave OpenAI da empresa" if v["provider"] == "openai" else "Chave LLM universal Emergent",
             "quality": v.get("quality"), "speed": v.get("speed"), "cost": v.get("cost")}
            for k, v in ai.AI_TEXT_MODELS.items()
        ],
    }


@router.put("/ai-model")
async def set_ai_model(body: AiModelIn) -> dict:
    from fastapi import HTTPException
    from engines import ai
    if body.tier not in ai.AI_TEXT_MODELS:
        raise HTTPException(400, f'nível desconhecido: {body.tier}')
    tier = await ai.set_text_tier(body.tier)
    return {"current": tier}


@router.get("/ai-openai-key")
async def get_openai_key_status() -> dict:
    from engines import llm_keys
    return llm_keys.status()


@router.post("/ai-openai-key/reactivate")
async def reactivate_openai_key() -> dict:
    """Test de connexion OpenAI puis remise en service de la clé d'entreprise (après rechargement du crédit)."""
    from fastapi import HTTPException
    from engines import llm_keys
    try:
        return await llm_keys.reactivate_openai()
    except ValueError as e:
        raise HTTPException(409, str(e))


@router.post("/ai-openai-key/disable")
async def disable_openai_key() -> dict:
    """Bascule manuelle sur la clé Emergent (ex. pour économiser le crédit OpenAI)."""
    from engines import llm_keys
    if llm_keys.openai_direct_active():
        await llm_keys.disable_openai("Desativação manual pelo administrador", alert=False)
    return llm_keys.status()


# ---------- Backend Gemini : clé Emergent vs SDK Google natif ----------

class GeminiBackendIn(BaseModel):
    backend: str  # "emergent" | "native"


@router.get("/ai-gemini-backend")
async def get_gemini_backend() -> dict:
    from engines import ai
    from engines import gemini_native
    current = await ai.get_gemini_backend()
    return {
        "current": current,
        "key_present": gemini_native.native_available(),
        "models": {"pro": gemini_native.NATIVE_PRO, "flash": gemini_native.NATIVE_FLASH},
        "options": [
            {"backend": "emergent", "label": "Chave LLM universal Emergent",
             "desc": "Gemini via chave Emergent (sem faturação Google)"},
            {"backend": "native", "label": "SDK Google nativo (gemini latest)",
             "desc": "Chamadas diretas à Google com a sua chave — faturação Google. Como o gemini-2.5 está descontinuado (2026), usam-se os aliases estáveis pro/flash latest."},
        ],
    }


@router.put("/ai-gemini-backend")
async def set_gemini_backend(body: GeminiBackendIn) -> dict:
    from fastapi import HTTPException
    from engines import ai, gemini_native
    if body.backend not in ("emergent", "native"):
        raise HTTPException(400, f'backend desconhecido: {body.backend}')
    if body.backend == "native" and not gemini_native.native_available():
        raise HTTPException(409, "Chave Google ausente (GOOGLE_GEMINI_API_KEY). Acrescente-a ao backend antes de ativar o modo nativo.")
    backend = await ai.set_gemini_backend(body.backend)
    return {"current": backend}


@router.post("/ai-gemini-backend/test")
async def test_gemini_native_key() -> dict:
    """Vérifie que la clé Google native fonctionne (petit appel authentifié)."""
    from engines import gemini_native
    ok, status = await gemini_native.check_key()
    return {"ok": ok, "status": status}


# Libellés lisibles des fonctionnalités IA
_AI_FEATURE_LABELS = {
    "smart_project": "Estimation Smart Project",
    "photo_analyse": "Análise de fotografia",
    "quote_scan": "Scanner de orçamentos",
    "quote_compare": "Comparação de orçamentos",
    "project_advice": "Conselhos de projeto",
    "coach": "Coach IA",
    "misc": "Outro",
}


@router.get("/ai-usage")
async def ai_usage() -> dict:
    """Compteur d'appels IA par fonctionnalité et par modèle."""
    from collections import defaultdict
    rows = await db.ai_usage.find({}, {"_id": 0}).to_list(1000)
    by_feature = defaultdict(int)
    by_model = defaultdict(int)
    total = 0
    detail = []
    for r in rows:
        calls = r.get("calls", 0)
        feat = r.get("feature", "misc")
        model = r.get("model", "?")
        by_feature[feat] += calls
        by_model[model] += calls
        total += calls
        detail.append({
            "feature": feat,
            "feature_label": _AI_FEATURE_LABELS.get(feat, feat),
            "provider": r.get("provider"),
            "model": model,
            "calls": calls,
            "last_used": r.get("last_used"),
        })
    detail.sort(key=lambda x: x["calls"], reverse=True)
    return {
        "total_calls": total,
        "by_feature": [{"feature": k, "feature_label": _AI_FEATURE_LABELS.get(k, k),
                        "calls": v} for k, v in sorted(by_feature.items(),
                                                       key=lambda i: -i[1])],
        "by_model": [{"model": k, "calls": v} for k, v in sorted(by_model.items(),
                                                                 key=lambda i: -i[1])],
        "detail": detail,
    }


@router.get("/ai-usage-daily")
async def ai_usage_daily(days: int = 30) -> dict:
    """Appels IA par jour sur les N derniers jours (pour le graphique de consommation)."""
    from datetime import datetime, timezone, timedelta
    days = max(1, min(days, 90))
    today = datetime.now(timezone.utc).date()
    rows = await db.ai_usage_daily.find({}, {"_id": 1, "calls": 1}).to_list(200)
    by_day = {r["_id"]: r.get("calls", 0) for r in rows}
    series = []
    for i in range(days - 1, -1, -1):
        d = (today - timedelta(days=i)).isoformat()
        series.append({"date": d, "calls": by_day.get(d, 0)})
    return {"days": days, "series": series, "total": sum(s["calls"] for s in series)}


class AiBudgetIn(BaseModel):
    threshold: int | None = None
    alert_email: str | None = None


@router.get("/ai-budget")
async def get_ai_budget() -> dict:
    from datetime import datetime, timezone
    doc = await db.app_settings.find_one({"_id": "ai"}) or {}
    month = datetime.now(timezone.utc).strftime("%Y-%m")
    rows = await db.ai_usage_daily.find({"_id": {"$regex": f"^{month}"}}).to_list(40)
    month_calls = sum(r.get("calls", 0) for r in rows)
    return {
        "threshold": doc.get("budget_threshold"),
        "alert_email": doc.get("budget_email"),
        "month": month,
        "month_calls": month_calls,
        "alert_sent_this_month": doc.get("budget_alert_month") == month,
    }


@router.put("/ai-budget")
async def set_ai_budget(body: AiBudgetIn) -> dict:
    updates = {}
    if body.threshold is not None:
        updates["budget_threshold"] = max(0, int(body.threshold))
    if body.alert_email is not None:
        updates["budget_email"] = body.alert_email.strip() or None
    # Réinitialise le verrou d'alerte quand le seuil change (nouvelle config)
    updates["budget_alert_month"] = None
    await db.app_settings.update_one({"_id": "ai"}, {"$set": updates}, upsert=True)
    return await get_ai_budget()


# ---------- Mode démo : débloquer toutes les options (Pro Business) ----------

@router.post("/demo-unlock")
async def demo_unlock(user=Depends(current_user)) -> dict:
    """Octroie au compte courant une entitlement Pro Business (démo, 10 ans) + l'add-on
    Facturation, pour débloquer toutes les options sans passer par Stripe.
    Stripe reste en mode test : la carte 4242 4242 4242 4242 fonctionne aussi dans le checkout."""
    from datetime import datetime, timezone, timedelta
    now = datetime.now(timezone.utc)
    ent = {
        "entitlement_id": f"demo_{user['user_id']}",
        "user_id": user["user_id"], "plan_id": "pro_business_yearly",
        "status": "active", "source": "demo",
        "granted_at": now.isoformat(),
        "expires_at": (now + timedelta(days=3650)).isoformat(),
    }
    await db.entitlements.update_one(
        {"entitlement_id": ent["entitlement_id"]}, {"$set": ent}, upsert=True)
    await db.users.update_one({"user_id": user["user_id"]},
                              {"$set": {"invoicing_addon": True, "demo_mode": True}})
    from engines.monetization import user_tier
    return {"ok": True, "tier": await user_tier(user["user_id"]),
            "invoicing_addon": True, "card": "4242 4242 4242 4242 (Stripe test)"}


@router.post("/demo-lock")
async def demo_lock(user=Depends(current_user)) -> dict:
    """Désactive le mode démo (retire l'entitlement démo + l'add-on)."""
    await db.entitlements.delete_one({"entitlement_id": f"demo_{user['user_id']}"})
    await db.users.update_one({"user_id": user["user_id"]},
                              {"$set": {"invoicing_addon": False, "demo_mode": False}})
    from engines.monetization import user_tier
    return {"ok": True, "tier": await user_tier(user["user_id"])}
