"""Outils CRM de l'Assistente Construção : clients, dossiers de obra (projetos) et rattachements.

Permet à l'assistant de CRÉER réellement une fiche client, un processo de obra, et de rattacher
devis / factures / plantas, au lieu de demander à l'utilisateur de le faire à la main.
Toutes les opérations passent par les mêmes fonctions que l'interface (mêmes contrôles de droits).
"""
from __future__ import annotations

import re

from fastapi import HTTPException

from engines.assistant_workspace import function

S = {"type": "string", "maxLength": 200}
LONG = {"type": "string", "maxLength": 2000}

CRM_TOOLS = [
    function("find_clients", "Procura fichas de cliente no CRM da conta (nome, empresa, e-mail, cidade). Query vazia = os mais recentes. Utilizar ANTES de criar um cliente para evitar duplicados, e para obter o client_id.",
             {"query": S}),
    function("create_client", "CRIA uma ficha de cliente real no CRM (/clients). Para uma empresa, preencher company; para um particular, first_name/last_name. Campos desconhecidos = cadeia vazia (nunca inventar e-mail, telefone ou NIF). Se já existir uma ficha com o mesmo nome/e-mail/empresa, devolve-a (duplicate=true) em vez de criar outra.",
             {"company": S, "first_name": S, "last_name": S, "email": S, "phone": S, "address": S,
              "postal_code": {"type": "string", "maxLength": 16}, "city": S, "nif": {"type": "string", "maxLength": 20}, "notes": LONG}),
    function("find_projects", "Procura processos de obra / projetos da conta (Dossiers de obra, /chantiers). Query vazia = os mais recentes. Devolve chantier_id, nome, cliente e estado.",
             {"query": S}),
    function("create_project", "CRIA um processo de obra / projeto real (Dossiers de obra, /chantiers), associado a um cliente do CRM (client_id de find_clients/create_client; vazio se não houver cliente). Morada vazia = retoma a morada do cliente. status: prospect, en_cours ou termine.",
             {"name": {"type": "string", "minLength": 1, "maxLength": 160}, "client_id": S, "address": S,
              "postal_code": {"type": "string", "maxLength": 16}, "city": S,
              "status": {"type": "string", "enum": ["prospect", "en_cours", "termine"]}, "notes": LONG}),
    function("link_to_client", "Associa um orçamento ou fatura existente (doc_id) a uma ficha de cliente do CRM (client_id), para que apareça na ficha do cliente. Um documento já associado a OUTRO cliente, ou emitido/assinado com outro cliente, não é alterado.",
             {"doc_id": S, "client_id": S}),
    function("attach_to_project", "Junta um elemento existente da conta a um processo de obra: kind=document (orçamento/fatura, ref_id=doc_id) ou plan (planta, ref_id=plan_id).",
             {"chantier_id": S, "kind": {"type": "string", "enum": ["document", "plan"]}, "ref_id": S}),
]
CRM_TOOL_NAMES = {t["name"] for t in CRM_TOOLS}

CRM_INSTRUCTIONS = (
    "\nCRM E PROJETOS: tens ferramentas REAIS para gerir clientes e processos de obra. Quando o utilizador pede para "
    "criar um cliente, um projeto/obra, ou associar um orçamento/fatura a um cliente, FÁ-LO tu próprio com find_clients, "
    "create_client, find_projects, create_project, link_to_client e attach_to_project. NUNCA respondas que não tens "
    "ferramenta nem peças ao utilizador para o fazer à mão. Encadeamento típico: find_clients → create_client (se não existir) → "
    "create_project com o client_id → anuncia os dois com as ligações /clients/<client_id> e /chantiers/<chantier_id>. "
    "Um nome como «Cunha Jardins» é uma empresa (company). Não inventes e-mail, telefone, NIF nem morada: deixa vazio. "
    "Depois de criar um orçamento para um cliente do CRM, associa-o com link_to_client (e attach_to_project se houver obra).\n"
)


def _label(c: dict | None) -> str:
    if not c:
        return ""
    return c.get("company") or " ".join(filter(None, [c.get("first_name"), c.get("last_name")])) or c.get("email") or ""


def _client_out(c: dict) -> dict:
    return {"client_id": c["client_id"], "name": _label(c), "company": c.get("company", ""),
            "first_name": c.get("first_name", ""), "last_name": c.get("last_name", ""),
            "email": c.get("email", ""), "phone": c.get("phone", ""), "city": c.get("city", ""),
            "url": f"/clients/{c['client_id']}"}


async def execute_crm_tool(name: str, args: dict, user: dict, conv: dict, db) -> dict:
    from core.security import pro_required
    await pro_required(user)
    uid = user["user_id"]

    if name == "find_clients":
        from routes.clients import list_clients
        res = await list_clients(q=(args.get("query") or "").strip()[:120], user=user)
        rows = res["clients"][:25]
        return {"ok": True, "count": res["count"], "clients": [_client_out(c) for c in rows]}

    if name == "create_client":
        from routes.clients import ClientIn, create_client
        from routes.documents import _match_client
        data = {k: (args.get(k) or "").strip() for k in ("company", "first_name", "last_name", "email", "phone",
                                                          "address", "postal_code", "city", "notes")}
        if data["email"] and not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", data["email"]):
            data["email"] = ""
        data["siret"] = (args.get("nif") or "").strip()
        existing = await _match_client(uid, data)
        if existing:
            c = await db.clients.find_one({"client_id": existing, "user_id": uid}, {"_id": 0})
            return {"ok": True, "duplicate": True, "client": _client_out(c),
                    "note": "Já existia uma ficha com esta identidade: reutilizada, nenhuma duplicação."}
        c = await create_client(ClientIn(**data), user=user)
        await db.clients.update_one({"client_id": c["client_id"], "user_id": uid}, {"$set": {"source": "assistant"}})
        return {"ok": True, "duplicate": False, "client": _client_out(c)}

    if name == "find_projects":
        from routes.chantiers import list_chantiers
        res = await list_chantiers(q=(args.get("query") or "").strip()[:120], status="", user=user)
        rows = (res.get("chantiers") or res.get("items") or [])[:25]
        return {"ok": True, "projects": [{"chantier_id": r["chantier_id"], "name": r.get("name"),
                                          "client_id": r.get("client_id"), "client_name": r.get("client_name"),
                                          "status": r.get("status"), "city": r.get("city"),
                                          "url": f"/chantiers/{r['chantier_id']}"} for r in rows]}

    if name == "create_project":
        from routes.chantiers import ChantierIn, create_chantier
        cid = (args.get("client_id") or "").strip() or None
        nm = args["name"].strip()
        dup = await db.chantiers.find_one(
            {"user_id": uid, "name": {"$regex": f"^{re.escape(nm)}$", "$options": "i"}, "client_id": cid}, {"_id": 0})
        if dup:
            return {"ok": True, "duplicate": True, "project": {"chantier_id": dup["chantier_id"], "name": dup["name"],
                    "client_id": dup.get("client_id"), "client_name": dup.get("client_name"),
                    "url": f"/chantiers/{dup['chantier_id']}"}}
        ch = await create_chantier(ChantierIn(
            name=nm[:160], client_id=cid, address=(args.get("address") or "").strip()[:200],
            postal_code=(args.get("postal_code") or "").strip()[:16], city=(args.get("city") or "").strip()[:80],
            status=args.get("status") or "en_cours", notes=(args.get("notes") or "").strip()[:2000]), user=user)
        return {"ok": True, "duplicate": False, "project": {"chantier_id": ch["chantier_id"], "name": ch["name"],
                "client_id": ch.get("client_id"), "client_name": ch.get("client_name"),
                "url": f"/chantiers/{ch['chantier_id']}"}}

    if name == "link_to_client":
        from routes.documents import _client_snapshot
        cid = args["client_id"].strip()
        snap = await _client_snapshot(cid, user)
        if not snap:
            raise HTTPException(404, "Cliente não encontrado nesta conta")
        doc = await db.pro_documents.find_one({"doc_id": args["doc_id"].strip(), "user_id": uid},
                                              {"_id": 0, "doc_id": 1, "client_id": 1, "doc_type": 1, "number": 1, "title": 1})
        if not doc:
            raise HTTPException(404, "Documento não encontrado nesta conta")
        if doc.get("client_id") and doc["client_id"] != cid:
            return {"ok": False, "error": "Este documento já está associado a outro cliente; altere-o no editor."}
        await db.pro_documents.update_one({"doc_id": doc["doc_id"], "user_id": uid},
                                          {"$set": {"client_id": cid, "client": snap}})
        return {"ok": True, "doc_id": doc["doc_id"], "client_id": cid, "client_url": f"/clients/{cid}"}

    if name == "attach_to_project":
        from routes.chantiers import AttachIn, attach
        return await attach(args["chantier_id"].strip(), AttachIn(kind=args["kind"], ref_id=args["ref_id"].strip()), user=user)

    raise HTTPException(422, "Ferramenta desconhecida")
