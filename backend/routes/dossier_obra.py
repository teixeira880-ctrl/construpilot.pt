"""Dossier de Obra — centro de trabalho por obra, área, especialidade, fase e local.

Assenta no processo de obra existente (`db.chantiers`, rotas /chantiers): não duplica plantas, orçamentos,
fotografias nem autos — liga-os POR REFERÊNCIA. Regras:
- isolamento: só o dono do processo (mesma regra de /chantiers) lê ou escreve;
- nada é apagado nem movido silenciosamente; cada alteração fica no histórico;
- itens aprovados/validados só mudam com confirmação explícita e com o impacto apresentado;
- orçamentos aceites, encomendas enviadas e autos aprovados NUNCA são alterados por este módulo;
- a compilação congela um retrato (snapshot) do conteúdo; os ficheiros são gerados a partir dele;
- a compilação não equivale à validação técnica da obra.
"""
from __future__ import annotations

import hashlib
import json
import secrets
from datetime import datetime, timezone
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel, Field

from core.db import db
from core.permissions import feature_dependency, permissions_for
from core.security import current_user
from engines import dossier_obra_catalog as C

router = APIRouter(prefix="/dossier-obra", tags=["dossier-obra"], dependencies=[Depends(feature_dependency("chantier"))])

ENABLED_DEFAULT: list[str] = []
LOCKED_DOC_STATUSES = {"signed", "paid", "sent"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _id(prefix: str) -> str:
    return f"{prefix}_{secrets.token_hex(6)}"


# ───────────────────────── acesso e configuração ─────────────────────────

async def _chantier(cid: str, uid: str) -> dict:
    c = await db.chantiers.find_one({"chantier_id": cid, "user_id": uid}, {"_id": 0})
    if not c:
        raise HTTPException(404, "Processo de obra não encontrado")
    return c


async def _config(cid: str, uid: str) -> dict:
    cfg = await db.dossier_obra_configs.find_one({"chantier_id": cid, "user_id": uid}, {"_id": 0})
    if cfg:
        cfg.setdefault("custom", [])
        cfg.setdefault("locations", [])
        cfg.setdefault("hidden", [])
        return cfg
    return {"chantier_id": cid, "user_id": uid, "global_phase": None, "enabled": list(ENABLED_DEFAULT), "hidden": [],
            "custom": [], "locations": [], "next_action": "", "started_mid_way": False, "_new": True}


async def _save_config(cfg: dict) -> dict:
    cfg = {k: v for k, v in cfg.items() if k != "_new"}
    cfg["updated_at"] = _now()
    exists = await db.dossier_obra_configs.find_one({"chantier_id": cfg["chantier_id"], "user_id": cfg["user_id"]}, {"_id": 1})
    if exists:
        await db.dossier_obra_configs.update_one({"chantier_id": cfg["chantier_id"], "user_id": cfg["user_id"]}, {"$set": cfg})
    else:
        cfg["created_at"] = cfg["updated_at"]
        await db.dossier_obra_configs.insert_one(dict(cfg))
    cfg.pop("_id", None)
    return cfg


def _specialties(cfg: dict) -> dict:
    """Catálogo + especialidades/subdivisões personalizadas desta obra."""
    out = {k: dict(v) for k, v in C.SPECIALTIES.items()}
    for s in cfg.get("custom", []):
        out[s["key"]] = {"key": s["key"], "area": s["area"], "label": s["label"], "short": s["label"], "description": s.get("description", ""),
                         "examples": [], "terms": s.get("terms", ""), "custom": True, "parent": s.get("parent")}
    return out


def _spec(cfg: dict, key: str) -> dict:
    s = _specialties(cfg).get(key)
    if not s:
        raise HTTPException(404, "Especialidade desconhecida")
    return s


def _location_path(cfg: dict, location_id: Optional[str]) -> str:
    if not location_id:
        return ""
    by_id = {loc["location_id"]: loc for loc in cfg.get("locations", [])}
    parts, cur, guard = [], by_id.get(location_id), 0
    while cur and guard < 6:
        parts.append(cur["name"])
        cur, guard = by_id.get(cur.get("parent_id")), guard + 1
    return " · ".join(reversed(parts))


def _can_finance(user: dict) -> bool:
    p = permissions_for(user)
    return bool(p.get("devis") or p.get("factures"))


# ───────────────────────── catálogo e preferências ─────────────────────────

@router.get("/catalogo")
async def catalogo(q: str = "") -> dict:
    out = C.public_catalog()
    if q.strip():
        out["results"] = C.search(q)
    return out


# Catálogo de ações do dossier: permite ligar mais tarde a Aurora / o Assistente BTP como ferramentas («tudo por prompt»).
ACTIONS = [
    {"name": "abrir_especialidade", "method": "GET", "path": "/dossier-obra/{cid}/especialidades/{key}", "params": ["fase", "local"], "effect": "leitura"},
    {"name": "ativar_especialidades", "method": "PUT", "path": "/dossier-obra/{cid}/config", "body": ["enabled", "hidden", "global_phase"], "effect": "configuração"},
    {"name": "registar", "method": "POST", "path": "/dossier-obra/{cid}/itens", "body": ["specialty", "kind", "title", "phase", "location_id", "measurement", "quantities", "unit_price"], "effect": "cria registo"},
    {"name": "alterar_registo", "method": "PATCH", "path": "/dossier-obra/{cid}/itens/{item_id}", "body": ["…", "confirm"], "effect": "altera (409 com impacto se precisar de confirmação)"},
    {"name": "validar_interpretacao", "method": "POST", "path": "/dossier-obra/{cid}/itens/{item_id}/validacao", "body": ["action", "layer_order", "material"], "effect": "confirma/corrige/rejeita"},
    {"name": "orcamento_especialidade", "method": "GET", "path": "/dossier-obra/{cid}/orcamento", "params": ["especialidades"], "effect": "leitura"},
    {"name": "criar_orcamento", "method": "POST", "path": "/dossier-obra/{cid}/orcamento/rascunho", "body": ["specialties"], "effect": "cria orçamento em rascunho"},
    {"name": "dependencias", "method": "POST", "path": "/dossier-obra/{cid}/dependencias", "body": ["from_specialty", "relation", "to_specialty", "confirm"], "effect": "propõe/confirma sequência"},
    {"name": "previsualizar", "method": "POST", "path": "/dossier-obra/{cid}/compilar/previsualizar", "body": ["scope", "specialties", "phases", "locations", "include", "recipient"], "effect": "leitura"},
    {"name": "emitir_dossier", "method": "POST", "path": "/dossier-obra/{cid}/emissoes", "body": ["…selecção"], "effect": "cria emissão versionada"},
]


@router.get("/acoes")
async def actions() -> dict:
    return {"actions": ACTIONS, "rules": "Alterações com impacto exigem confirm=true depois de apresentar o impacto ao utilizador."}


class PrefIn(BaseModel):
    mode: Literal["guiado", "tecnico"]


@router.get("/preferencias")
async def get_prefs(user=Depends(current_user)) -> dict:
    u = await db.users.find_one({"user_id": user["user_id"]}, {"_id": 0, "dossier_mode": 1}) or {}
    return {"mode": u.get("dossier_mode") or "guiado"}


@router.put("/preferencias")
async def set_prefs(body: PrefIn, user=Depends(current_user)) -> dict:
    # O modo só muda a apresentação: os mesmos registos são lidos e escritos nos dois modos.
    await db.users.update_one({"user_id": user["user_id"]}, {"$set": {"dossier_mode": body.mode}})
    return {"mode": body.mode}


# ───────────────────────── visão geral ─────────────────────────

def _display_status(item: dict) -> str:
    """Estado para a compilação: validado / rascunho / pendente / nao_aplicavel."""
    if item.get("status") == "nao_aplicavel":
        return "nao_aplicavel"
    if item.get("kind") == "orcamento":
        q = (item.get("quantities") or {}).get("orcamentada")
        if item.get("unit_price") is None or q is None or item.get("price_source") == "mercado":
            return "pendente"   # preço ou quantidade em falta, ou preço de mercado por confirmar
    if item.get("validation") == "rejeitado":
        return "rejeitado"
    interpretation = item.get("kind") in ("medicao", "material", "documento") or item.get("source") == "inferido"
    if item.get("status") in ("pendente", "bloqueado", "por_fazer", "em_curso") or item.get("needs_review") \
            or (interpretation and item.get("validation") == "por_confirmar"):
        return "pendente"
    if item.get("validation") in ("validado", "confirmado", "corrigido") or item.get("status") == "concluido":
        return "validado"
    return "rascunho"


def _is_open(item: dict) -> bool:
    return _display_status(item) == "pendente" or item.get("status") in ("por_fazer", "em_curso", "pendente", "bloqueado")


async def _items(cid: str, uid: str, **flt) -> list[dict]:
    q = {"chantier_id": cid, "user_id": uid, "archived": {"$ne": True}}
    q.update({k: v for k, v in flt.items() if v is not None})
    return await db.dossier_obra_items.find(q, {"_id": 0}).sort("created_at", 1).to_list(2000)


async def _states(cid: str, uid: str) -> dict:
    rows = await db.dossier_obra_specialties.find({"chantier_id": cid, "user_id": uid}, {"_id": 0}).to_list(500)
    return {r["key"]: r for r in rows}


async def _deps(cid: str, uid: str) -> list[dict]:
    return await db.dossier_obra_dependencies.find({"chantier_id": cid, "user_id": uid}, {"_id": 0}).sort("created_at", 1).to_list(500)


async def _referenced(cid: str, uid: str) -> set:
    rows = await db.dossier_obra_items.find({"chantier_id": cid, "user_id": uid, "ref": {"$ne": None}}, {"_id": 0, "ref": 1}).to_list(5000)
    return {(r["ref"].get("kind"), r["ref"].get("id")) for r in rows if r.get("ref")}


async def _unclassified(c: dict, uid: str) -> list[dict]:
    """Registos já ligados ao processo mas ainda sem especialidade: ficam em «Por organizar» (nada é movido)."""
    cid = c["chantier_id"]
    link = {"user_id": uid, "chantier_id": cid}
    done = await _referenced(cid, uid)
    out = []
    sources = (
        ("plan", db.plans_takeoff, "plan_id", lambda r: r.get("filename") or r.get("plan_id"), {"trashed_at": None}),
        ("document", db.pro_documents, "doc_id", lambda r: r.get("title") or r.get("number") or r.get("doc_id"), {}),
        ("plans_pro", db.plans_pro_jobs, "job_id", lambda r: r.get("filename") or r.get("job_id"), {}),
        ("site_report", db.site_reports, "report_id", lambda r: r.get("title") or r.get("report_id"), {}),
        ("btp_problem", db.btp_problems, "problem_id", lambda r: (r.get("description") or "")[:80] or r.get("problem_id"), {}),
    )
    for kind, coll, key, label, extra in sources:
        rows = await coll.find({**link, **extra}, {"_id": 0, key: 1, "filename": 1, "title": 1, "number": 1, "description": 1,
                                                    "doc_type": 1, "status": 1, "created_at": 1}).to_list(300)
        for r in rows:
            if (kind, r.get(key)) in done:
                continue
            created = r.get("created_at")
            out.append({"kind": kind, "id": r.get(key), "label": label(r), "doc_type": r.get("doc_type"), "status": r.get("status"),
                        "created_at": created.isoformat() if isinstance(created, datetime) else created})
    return out


def _next_action(cfg: dict, items: list[dict], specs: dict, states: dict) -> dict | None:
    if cfg.get("next_action"):
        return {"label": cfg["next_action"], "specialty": None, "source": "manual"}
    order = {"bloqueado": 0, "pendente": 1, "em_curso": 2, "por_fazer": 3}
    open_items = [i for i in items if i.get("kind") in ("tarefa", "pendencia", "verificacao") and i.get("status") in order]
    if not open_items:
        return None
    open_items.sort(key=lambda i: (order[i["status"]], i.get("created_at", "")))
    i = open_items[0]
    return {"label": i["title"], "specialty": i.get("specialty"), "specialty_label": (specs.get(i.get("specialty")) or {}).get("label"),
            "item_id": i["item_id"], "source": "pendencias"}


@router.get("/{cid}")
async def overview(cid: str, user=Depends(current_user)) -> dict:
    uid = user["user_id"]
    c = await _chantier(cid, uid)
    cfg = await _config(cid, uid)
    specs = _specialties(cfg)
    states = await _states(cid, uid)
    items = await _items(cid, uid)
    deps = await _deps(cid, uid)
    enabled = [k for k in cfg.get("enabled", []) if k in specs and k not in cfg.get("hidden", [])]
    per_spec: dict = {}
    for i in items:
        s = per_spec.setdefault(i.get("specialty"), {"items": 0, "open": 0, "pending": 0})
        s["items"] += 1
        s["open"] += 1 if _is_open(i) else 0
        s["pending"] += 1 if _display_status(i) == "pendente" else 0
    areas = []
    for ak, alabel, adesc, icon in C.AREAS:
        lst = [{**specs[k], "state": states.get(k, {}), "counts": per_spec.get(k, {"items": 0, "open": 0, "pending": 0})}
               for k in specs if specs[k]["area"] == ak and k in enabled]
        areas.append({"key": ak, "label": alabel, "description": adesc, "icon": icon, "specialties": lst,
                      "available": len([k for k in specs if specs[k]["area"] == ak])})
    pend = [i for i in items if _display_status(i) == "pendente"]
    unclassified = await _unclassified(c, uid)
    last = await db.dossier_obra_emissions.find({"chantier_id": cid, "user_id": uid}, {"_id": 0, "snapshot": 0}).sort("version", -1).limit(1).to_list(1)
    return {
        "chantier": {k: c.get(k) for k in ("chantier_id", "name", "ref", "client_name", "address", "postal_code", "city", "status", "demo")},
        "config": {k: v for k, v in cfg.items() if k not in ("user_id",)},
        "areas": areas, "enabled": enabled,
        "pendencias": [{"item_id": i["item_id"], "title": i["title"], "specialty": i.get("specialty"),
                        "specialty_label": (specs.get(i.get("specialty")) or {}).get("label"), "status": i.get("status"),
                        "kind": i.get("kind")} for i in pend[:30]],
        "pendencias_total": len(pend),
        "next_action": _next_action(cfg, items, specs, states),
        "dependencies_pending": len([d for d in deps if d.get("status") != "confirmada"]),
        "por_organizar": {"total": len(unclassified), "items": unclassified[:50]},
        "last_emission": last[0] if last else None,
        "disclaimer": C.DISCLAIMER,
    }


class ConfigIn(BaseModel):
    global_phase: Optional[str] = Field(None, max_length=30)
    enabled: Optional[list[str]] = Field(None, max_length=200)
    hidden: Optional[list[str]] = Field(None, max_length=200)
    next_action: Optional[str] = Field(None, max_length=300)
    started_mid_way: Optional[bool] = None


@router.put("/{cid}/config")
async def update_config(cid: str, body: ConfigIn, user=Depends(current_user)) -> dict:
    uid = user["user_id"]
    await _chantier(cid, uid)
    cfg = await _config(cid, uid)
    specs = _specialties(cfg)
    if body.global_phase is not None:
        if body.global_phase and body.global_phase not in C.PHASE_KEYS:
            raise HTTPException(422, "Fase desconhecida")
        cfg["global_phase"] = body.global_phase or None
    for field in ("enabled", "hidden"):
        val = getattr(body, field)
        if val is not None:
            bad = [k for k in val if k not in specs]
            if bad:
                raise HTTPException(422, f"Especialidades desconhecidas: {', '.join(bad[:5])}")
            cfg[field] = list(dict.fromkeys(val))
    if body.next_action is not None:
        cfg["next_action"] = body.next_action.strip()
    if body.started_mid_way is not None:
        cfg["started_mid_way"] = body.started_mid_way
    return await _save_config(cfg)


class CustomSpecIn(BaseModel):
    area: str = Field(..., max_length=30)
    label: str = Field(..., min_length=2, max_length=120)
    description: str = Field("", max_length=400)
    parent: Optional[str] = Field(None, max_length=60)   # subdivisão de uma especialidade existente


@router.post("/{cid}/especialidades")
async def add_custom_specialty(cid: str, body: CustomSpecIn, user=Depends(current_user)) -> dict:
    uid = user["user_id"]
    await _chantier(cid, uid)
    cfg = await _config(cid, uid)
    if body.area not in [a[0] for a in C.AREAS]:
        raise HTTPException(422, "Área desconhecida")
    if body.parent and body.parent not in _specialties(cfg):
        raise HTTPException(422, "Especialidade-mãe desconhecida")
    key = "cx_" + secrets.token_hex(4)
    cfg["custom"].append({"key": key, "area": body.area, "label": body.label.strip(), "description": body.description.strip(),
                          "parent": body.parent, "created_at": _now()})
    cfg["enabled"] = list(dict.fromkeys([*cfg.get("enabled", []), key]))
    await _save_config(cfg)
    return _specialties(cfg)[key]


class LocationIn(BaseModel):
    kind: Literal["edificio", "piso", "zona"]
    name: str = Field(..., min_length=1, max_length=80)
    parent_id: Optional[str] = Field(None, max_length=40)


@router.post("/{cid}/locais")
async def add_location(cid: str, body: LocationIn, user=Depends(current_user)) -> dict:
    uid = user["user_id"]
    await _chantier(cid, uid)
    cfg = await _config(cid, uid)
    ids = {loc["location_id"] for loc in cfg["locations"]}
    if body.parent_id and body.parent_id not in ids:
        raise HTTPException(422, "Local-pai desconhecido")
    loc = {"location_id": _id("loc"), "kind": body.kind, "name": body.name.strip(), "parent_id": body.parent_id}
    cfg["locations"].append(loc)
    await _save_config(cfg)
    return {**loc, "path": _location_path(cfg, loc["location_id"])}


@router.delete("/{cid}/locais/{location_id}")
async def delete_location(cid: str, location_id: str, user=Depends(current_user)) -> dict:
    uid = user["user_id"]
    await _chantier(cid, uid)
    cfg = await _config(cid, uid)
    used = await db.dossier_obra_items.count_documents({"chantier_id": cid, "user_id": uid, "location_id": location_id})
    children = [loc for loc in cfg["locations"] if loc.get("parent_id") == location_id]
    if used or children:
        raise HTTPException(409, "Este local tem registos ou sublocais associados: não é eliminado.")
    cfg["locations"] = [loc for loc in cfg["locations"] if loc["location_id"] != location_id]
    await _save_config(cfg)
    return {"ok": True}


# ───────────────────────── especialidade ─────────────────────────

def _item_view(i: dict, cfg: dict) -> dict:
    return {**i, "location_path": _location_path(cfg, i.get("location_id")), "display_status": _display_status(i)}


def _computed_next_step(items: list[dict]) -> str:
    order = {"bloqueado": 0, "pendente": 1, "em_curso": 2, "por_fazer": 3}
    cand = sorted([i for i in items if i.get("status") in order and i.get("kind") in ("tarefa", "pendencia", "verificacao")],
                  key=lambda i: (order[i["status"]], i.get("created_at", "")))
    if cand:
        return cand[0]["title"]
    unconfirmed = [i for i in items if i.get("validation") == "por_confirmar"]
    if unconfirmed:
        return f"Confirmar: {unconfirmed[0]['title']}"
    return ""


@router.get("/{cid}/especialidades/{key}")
async def specialty(cid: str, key: str, fase: Optional[str] = None, local: Optional[str] = None,
                    user=Depends(current_user)) -> dict:
    uid = user["user_id"]
    c = await _chantier(cid, uid)
    cfg = await _config(cid, uid)
    spec = _spec(cfg, key)
    states = await _states(cid, uid)
    all_items = await _items(cid, uid, specialty=key)
    # Fase e local filtram a vista; registos sem fase/local (transversais) continuam visíveis.
    items = [i for i in all_items
             if (not fase or not i.get("phase") or i.get("phase") == fase)
             and (not local or not i.get("location_id") or i.get("location_id") == local or _is_ancestor(cfg, i.get("location_id"), local))]
    deps = [d for d in await _deps(cid, uid) if key in (d["from_specialty"], d["to_specialty"])]
    specs = _specialties(cfg)
    linked = []
    for d in deps:
        other = d["to_specialty"] if d["from_specialty"] == key else d["from_specialty"]
        other_items = await _items(cid, uid, specialty=other)
        linked.append({**d, "other": other, "other_label": (specs.get(other) or {}).get("label", other),
                       "other_area": (specs.get(other) or {}).get("area"),
                       "direction": "out" if d["from_specialty"] == key else "in",
                       "relation_label": C.RELATIONS.get(d["relation"], d["relation"]),
                       "other_open": len([i for i in other_items if _is_open(i)]),
                       "other_blocked": len([i for i in other_items if i.get("status") == "bloqueado"]),
                       "other_status": (states.get(other) or {}).get("status", "por_iniciar")})
    state = states.get(key) or {"key": key, "status": "por_iniciar", "stage": "preparar", "responsible": "", "next_step": ""}
    by_kind: dict = {}
    for i in items:
        by_kind.setdefault(i.get("kind"), []).append(_item_view(i, cfg))
    conv = await db.assistant_convs.find_one({"user_id": uid, "chantier_id": cid, "dossier_context.specialty": key},
                                             {"_id": 0, "conversation_id": 1})
    return {
        "chantier": {k: c.get(k) for k in ("chantier_id", "name", "client_name", "city", "demo")},
        "specialty": spec, "area": next(({"key": a[0], "label": a[1]} for a in C.AREAS if a[0] == spec["area"]), None),
        "state": state, "next_step": state.get("next_step") or _computed_next_step(items),
        "filters": {"fase": fase, "local": local, "local_path": _location_path(cfg, local)},
        "global_phase": cfg.get("global_phase"),
        "items": [_item_view(i, cfg) for i in items], "by_kind": by_kind,
        "counts": {"total": len(items), "open": len([i for i in items if _is_open(i)]),
                   "pending": len([i for i in items if _display_status(i) == "pendente"]), "hidden_by_filter": len(all_items) - len(items)},
        "dependencies": linked,
        "locations": [{**loc, "path": _location_path(cfg, loc["location_id"])} for loc in cfg["locations"]],
        "enabled": key in cfg.get("enabled", []),
        "assistant_conversation_id": (conv or {}).get("conversation_id"),
        "can_finance": _can_finance(user),
    }


def _is_ancestor(cfg: dict, location_id: Optional[str], ancestor: str) -> bool:
    by_id = {loc["location_id"]: loc for loc in cfg.get("locations", [])}
    cur, guard = by_id.get(location_id), 0
    while cur and guard < 6:
        if cur.get("parent_id") == ancestor:
            return True
        cur, guard = by_id.get(cur.get("parent_id")), guard + 1
    return False


class SpecStateIn(BaseModel):
    status: Optional[str] = Field(None, max_length=30)
    stage: Optional[str] = Field(None, max_length=30)
    responsible: Optional[str] = Field(None, max_length=120)
    next_step: Optional[str] = Field(None, max_length=300)


@router.patch("/{cid}/especialidades/{key}")
async def update_specialty(cid: str, key: str, body: SpecStateIn, user=Depends(current_user)) -> dict:
    uid = user["user_id"]
    await _chantier(cid, uid)
    cfg = await _config(cid, uid)
    _spec(cfg, key)
    if body.status is not None and body.status not in C.SPECIALTY_STATUS:
        raise HTTPException(422, "Estado desconhecido")
    if body.stage is not None and body.stage not in C.STAGE_KEYS:
        raise HTTPException(422, "Etapa desconhecida")
    cur = await db.dossier_obra_specialties.find_one({"chantier_id": cid, "user_id": uid, "key": key}, {"_id": 0})
    changes = {k: v for k, v in body.model_dump().items() if v is not None}
    entry = {"at": _now(), "by": user.get("name") or user.get("email") or uid, "action": "estado",
             "changes": {k: [(cur or {}).get(k), v] for k, v in changes.items()}}
    if cur:
        await db.dossier_obra_specialties.update_one({"chantier_id": cid, "user_id": uid, "key": key},
                                                     {"$set": {**changes, "updated_at": _now()}, "$push": {"history": entry}})
    else:
        await db.dossier_obra_specialties.insert_one({"chantier_id": cid, "user_id": uid, "key": key, "status": "por_iniciar",
                                                      "stage": "preparar", "responsible": "", "next_step": "", **changes,
                                                      "history": [entry], "created_at": _now(), "updated_at": _now()})
    # Trabalhar numa especialidade ativa-a, sem obrigar a configurar a árvore toda.
    if key not in cfg.get("enabled", []):
        cfg["enabled"] = [*cfg.get("enabled", []), key]
        await _save_config(cfg)
    return await db.dossier_obra_specialties.find_one({"chantier_id": cid, "user_id": uid, "key": key}, {"_id": 0})


# ───────────────────────── registos (itens) ─────────────────────────

class MeasurementIn(BaseModel):
    document: str = Field("", max_length=160)
    revision: str = Field("", max_length=30)
    page: str = Field("", max_length=30)
    element: str = Field("", max_length=160)
    scale: str = Field("", max_length=30)
    method: str = Field("", max_length=160)
    quantity: Optional[float] = Field(None, ge=0, le=1e9, allow_inf_nan=False)
    unit: str = Field("", max_length=12)
    width_m: Optional[float] = Field(None, gt=0, le=10000, allow_inf_nan=False)    # dimensões medidas (esquema da medição)
    height_m: Optional[float] = Field(None, gt=0, le=10000, allow_inf_nan=False)


class LayerIn(BaseModel):
    order: int = Field(..., ge=1, le=50)
    name: str = Field(..., min_length=1, max_length=80)
    material: str = Field("", max_length=160)
    source: Literal["extraido", "manual", "inferido"] = "manual"
    validation: Literal["por_confirmar", "confirmado", "corrigido", "rejeitado", "validado"] = "por_confirmar"
    reference: str = Field("", max_length=200)   # documento/legenda/ficha que suporta a camada
    note: str = Field("", max_length=300)


class RefIn(BaseModel):
    kind: Literal["plan", "document", "plans_pro", "site_report", "btp_problem", "purchase", "situation"]
    id: str = Field(..., min_length=1, max_length=80)


class ItemIn(BaseModel):
    specialty: str = Field(..., max_length=60)
    element: str = Field("", max_length=160)             # subespecialidade ou elemento (ex.: Cerâmica exterior)
    kind: Literal["tarefa", "pendencia", "verificacao", "medicao", "material", "orcamento", "registo", "documento", "alteracao", "nota"]
    title: str = Field(..., min_length=1, max_length=300)
    detail: str = Field("", max_length=4000)
    status: Literal["por_fazer", "em_curso", "pendente", "bloqueado", "concluido", "nao_aplicavel"] = "por_fazer"
    stage: Optional[str] = Field(None, max_length=30)
    phase: Optional[str] = Field(None, max_length=30)
    location_id: Optional[str] = Field(None, max_length=40)
    source: Literal["extraido", "manual", "inferido"] = "manual"
    validation: Literal["por_confirmar", "confirmado", "corrigido", "rejeitado", "validado"] = "por_confirmar"
    measurement: Optional[MeasurementIn] = None
    quantities: Optional[dict[str, Optional[float]]] = None
    layers: Optional[list[LayerIn]] = Field(None, max_length=30)
    ref: Optional[RefIn] = None
    revision: str = Field("", max_length=30)
    related_specialty: Optional[str] = Field(None, max_length=60)   # pendência ligada a outra especialidade
    # Linha de orçamento da especialidade (quantidade em quantities.orcamentada; preço nunca inventado)
    unit: str = Field("", max_length=12)
    unit_price: Optional[float] = Field(None, ge=0, le=1e8, allow_inf_nan=False)
    vat_rate: Optional[float] = Field(None, ge=0, le=100, allow_inf_nan=False)
    price_source: Literal["", "biblioteca", "manual", "mercado"] = ""
    price_reference: str = Field("", max_length=200)
    from_item_id: Optional[str] = Field(None, max_length=40)        # medição de origem


def _clean_quantities(q: Optional[dict]) -> dict:
    out = {}
    for k, v in (q or {}).items():
        if k not in C.QUANTITY_KEYS:
            raise HTTPException(422, f"Tipo de quantidade desconhecido: {k}")
        if v is not None:
            if not isinstance(v, (int, float)) or v != v or v < 0 or v > 1e9:
                raise HTTPException(422, f"Quantidade inválida: {k}")
            out[k] = float(v)
    return out


async def _check_ref(ref: Optional[dict], cid: str, uid: str) -> None:
    if not ref:
        return
    coll, key = {"plan": (db.plans_takeoff, "plan_id"), "document": (db.pro_documents, "doc_id"), "plans_pro": (db.plans_pro_jobs, "job_id"),
                 "site_report": (db.site_reports, "report_id"), "btp_problem": (db.btp_problems, "problem_id"),
                 "purchase": (db.material_orders, "order_id"), "situation": (db.situations, "situation_id")}[ref["kind"]]
    found = await coll.find_one({key: ref["id"], "user_id": uid}, {"_id": 1})
    if not found:
        raise HTTPException(404, "Registo de origem não encontrado ou inacessível")


@router.post("/{cid}/itens")
async def create_item(cid: str, body: ItemIn, user=Depends(current_user)) -> dict:
    uid = user["user_id"]
    await _chantier(cid, uid)
    cfg = await _config(cid, uid)
    _spec(cfg, body.specialty)
    if body.related_specialty:
        _spec(cfg, body.related_specialty)
    if body.phase and body.phase not in C.PHASE_KEYS:
        raise HTTPException(422, "Fase desconhecida")
    if body.stage and body.stage not in C.STAGE_KEYS:
        raise HTTPException(422, "Etapa desconhecida")
    if body.location_id and body.location_id not in {loc["location_id"] for loc in cfg["locations"]}:
        raise HTTPException(422, "Local desconhecido")
    data = body.model_dump()
    await _check_ref(data.get("ref"), cid, uid)
    data["quantities"] = _clean_quantities(body.quantities)
    if body.from_item_id:
        src = await db.dossier_obra_items.find_one({"item_id": body.from_item_id, "chantier_id": cid, "user_id": uid}, {"_id": 0})
        if not src:
            raise HTTPException(404, "Medição de origem não encontrada")
        mq = (src.get("measurement") or {}).get("quantity")
        if body.kind == "orcamento" and "orcamentada" not in data["quantities"] and mq is not None:
            data["quantities"]["orcamentada"] = float(mq)   # a quantidade vem da medição (rastreável)
        data["unit"] = data["unit"] or (src.get("measurement") or {}).get("unit", "")
    # Informação inferida nunca nasce validada.
    if data["source"] == "inferido" and data["validation"] in ("confirmado", "validado"):
        data["validation"] = "por_confirmar"
    for layer in data.get("layers") or []:
        if layer["source"] == "inferido" and layer["validation"] in ("confirmado", "validado"):
            layer["validation"] = "por_confirmar"
    item = {"item_id": _id("itm"), "chantier_id": cid, "user_id": uid, **data, "approved": False, "needs_review": False,
            "history": [{"at": _now(), "by": user.get("name") or user.get("email") or uid, "action": "criado"}],
            "created_at": _now(), "updated_at": _now()}
    await db.dossier_obra_items.insert_one(dict(item))
    if body.specialty not in cfg.get("enabled", []):
        cfg["enabled"] = [*cfg.get("enabled", []), body.specialty]
        await _save_config(cfg)
    item.pop("_id", None)
    return _item_view(item, cfg)


async def _get_item(cid: str, uid: str, item_id: str) -> dict:
    i = await db.dossier_obra_items.find_one({"item_id": item_id, "chantier_id": cid, "user_id": uid}, {"_id": 0})
    if not i:
        raise HTTPException(404, "Registo não encontrado")
    return i


async def _locked_reason(item: dict, uid: str) -> Optional[str]:
    if item.get("approved") or item.get("validation") == "validado":
        return "Registo aprovado/validado"
    ref = item.get("ref") or {}
    if ref.get("kind") == "document":
        d = await db.pro_documents.find_one({"doc_id": ref["id"], "user_id": uid}, {"_id": 0, "status": 1, "doc_type": 1})
        if d and d.get("status") in LOCKED_DOC_STATUSES:
            return "Ligado a um orçamento/fatura enviado, aceite ou pago"
    if ref.get("kind") == "purchase":
        o = await db.material_orders.find_one({"order_id": ref["id"], "user_id": uid}, {"_id": 0, "status": 1})
        if o and o.get("status") not in (None, "draft", "brouillon", "rascunho"):
            return "Ligado a uma encomenda enviada"
    if ref.get("kind") == "situation":
        s = await db.situations.find_one({"situation_id": ref["id"], "user_id": uid}, {"_id": 0, "status": 1})
        if s and s.get("status") in ("validated", "approved", "sent", "paid", "validado", "aprovado"):
            return "Ligado a um auto aprovado"
    return None


async def _impact(cid: str, uid: str, item: dict, cfg: dict) -> dict:
    """1) identifica trabalhos relacionados, 2) impacto conhecido, 3) o que precisa de revisão."""
    specs = _specialties(cfg)
    key = item.get("specialty")
    related = []
    for d in await _deps(cid, uid):
        if key not in (d["from_specialty"], d["to_specialty"]):
            continue
        other = d["to_specialty"] if d["from_specialty"] == key else d["from_specialty"]
        affected = d["relation"] in ("pode_afetar", "partilha_com") or (d["relation"] in ("depende_de", "verificar_antes_de") and d["from_specialty"] == key) \
            or (d["relation"] == "depende_de" and d["to_specialty"] == key)
        if not affected:
            continue
        others = [i for i in await _items(cid, uid, specialty=other) if i.get("status") != "nao_aplicavel"]
        related.append({"specialty": other, "label": (specs.get(other) or {}).get("label", other), "relation": d["relation"],
                        "relation_label": C.RELATIONS.get(d["relation"]), "confirmed": d.get("status") == "confirmada",
                        "items_to_review": [{"item_id": i["item_id"], "title": i["title"], "status": i.get("status")}
                                            for i in others if i.get("kind") in ("medicao", "material", "tarefa", "verificacao")][:20]})
    if item.get("related_specialty") and item["related_specialty"] not in [r["specialty"] for r in related]:
        rs = item["related_specialty"]
        related.append({"specialty": rs, "label": (specs.get(rs) or {}).get("label", rs), "relation": "pendencia",
                        "relation_label": "Pendência ligada", "confirmed": True, "items_to_review": []})
    locked = await _locked_reason(item, uid)
    return {"item_id": item["item_id"], "locked": bool(locked), "locked_reason": locked, "related": related,
            "requires_confirmation": bool(locked) or any(r["items_to_review"] for r in related)}


@router.get("/{cid}/itens/{item_id}/impacto")
async def item_impact(cid: str, item_id: str, user=Depends(current_user)) -> dict:
    uid = user["user_id"]
    await _chantier(cid, uid)
    cfg = await _config(cid, uid)
    return await _impact(cid, uid, await _get_item(cid, uid, item_id), cfg)


class ItemPatch(BaseModel):
    title: Optional[str] = Field(None, min_length=1, max_length=300)
    detail: Optional[str] = Field(None, max_length=4000)
    element: Optional[str] = Field(None, max_length=160)
    status: Optional[Literal["por_fazer", "em_curso", "pendente", "bloqueado", "concluido", "nao_aplicavel"]] = None
    stage: Optional[str] = Field(None, max_length=30)
    phase: Optional[str] = Field(None, max_length=30)
    location_id: Optional[str] = Field(None, max_length=40)
    specialty: Optional[str] = Field(None, max_length=60)
    measurement: Optional[MeasurementIn] = None
    quantities: Optional[dict[str, Optional[float]]] = None
    layers: Optional[list[LayerIn]] = Field(None, max_length=30)
    revision: Optional[str] = Field(None, max_length=30)
    unit: Optional[str] = Field(None, max_length=12)
    unit_price: Optional[float] = Field(None, ge=0, le=1e8, allow_inf_nan=False)
    vat_rate: Optional[float] = Field(None, ge=0, le=100, allow_inf_nan=False)
    price_source: Optional[Literal["", "biblioteca", "manual", "mercado"]] = None
    price_reference: Optional[str] = Field(None, max_length=200)
    validation: Optional[Literal["por_confirmar", "confirmado", "corrigido", "rejeitado", "validado"]] = None
    approved: Optional[bool] = None
    note: str = Field("", max_length=300)                # motivo da alteração (histórico)
    confirm: bool = False                                # confirmação explícita depois de ver o impacto
    flag_related: bool = True                            # assinalar para revisão os trabalhos relacionados


@router.patch("/{cid}/itens/{item_id}")
async def update_item(cid: str, item_id: str, body: ItemPatch, user=Depends(current_user)) -> dict:
    uid = user["user_id"]
    await _chantier(cid, uid)
    cfg = await _config(cid, uid)
    item = await _get_item(cid, uid, item_id)
    patch = body.model_dump(exclude={"note", "confirm", "flag_related"}, exclude_none=True)
    if "specialty" in patch:
        _spec(cfg, patch["specialty"])
    if patch.get("phase") and patch["phase"] not in C.PHASE_KEYS:
        raise HTTPException(422, "Fase desconhecida")
    if patch.get("stage") and patch["stage"] not in C.STAGE_KEYS:
        raise HTTPException(422, "Etapa desconhecida")
    if patch.get("location_id") and patch["location_id"] not in {loc["location_id"] for loc in cfg["locations"]}:
        raise HTTPException(422, "Local desconhecido")
    if "quantities" in patch:
        patch["quantities"] = {**(item.get("quantities") or {}), **_clean_quantities(body.quantities)}
    impact = await _impact(cid, uid, item, cfg)
    substantive = {k for k in patch if k not in ("approved",)}
    if impact["locked"] and substantive and not body.confirm:
        raise HTTPException(409, detail={"message": "Este registo está aprovado ou ligado a um compromisso. Reveja o impacto e confirme.",
                                         "impact": impact})
    if impact["related"] and any(r["items_to_review"] for r in impact["related"]) and \
            ({"measurement", "quantities", "layers", "specialty"} & substantive) and not body.confirm:
        raise HTTPException(409, detail={"message": "Esta alteração pode afetar outras especialidades. Confirme para continuar.",
                                         "impact": impact})
    if patch.get("approved") and _display_status({**item, **patch}) == "pendente":
        raise HTTPException(422, "Não é possível aprovar um registo com pendências ou por confirmar.")
    changes = {k: [item.get(k), v] for k, v in patch.items() if item.get(k) != v}
    entry = {"at": _now(), "by": user.get("name") or user.get("email") or uid, "action": "alterado", "changes": changes, "note": body.note}
    if "revision" in patch and patch["revision"] != item.get("revision"):
        entry["action"] = "nova_revisao"
    if patch.get("status") == "concluido" or patch.get("validation") in ("confirmado", "corrigido", "validado"):
        patch["needs_review"] = False
    await db.dossier_obra_items.update_one({"item_id": item_id, "user_id": uid},
                                           {"$set": {**patch, "updated_at": _now()}, "$push": {"history": entry}})
    flagged = []
    if body.confirm and body.flag_related and ({"measurement", "quantities", "layers", "specialty"} & substantive):
        for r in impact["related"]:
            for other in r["items_to_review"]:
                await db.dossier_obra_items.update_one(
                    {"item_id": other["item_id"], "user_id": uid},
                    {"$set": {"needs_review": True, "updated_at": _now()},
                     "$push": {"history": {"at": _now(), "by": "dossier", "action": "assinalado_revisao",
                                           "note": f"Alteração em «{item['title']}»"}}})
                flagged.append(other["item_id"])
    out = await _get_item(cid, uid, item_id)
    return {**_item_view(out, cfg), "flagged_for_review": flagged}


class ValidationIn(BaseModel):
    action: Literal["confirmar", "corrigir", "rejeitar", "validar"]
    layer_order: Optional[int] = Field(None, ge=1, le=50)     # validar uma camada específica
    material: Optional[str] = Field(None, max_length=160)     # correção
    note: str = Field("", max_length=300)


@router.post("/{cid}/itens/{item_id}/validacao")
async def validate_item(cid: str, item_id: str, body: ValidationIn, user=Depends(current_user)) -> dict:
    """Confirmar, corrigir ou rejeitar uma interpretação (material, camada, medição). Fica no histórico."""
    uid = user["user_id"]
    await _chantier(cid, uid)
    cfg = await _config(cid, uid)
    item = await _get_item(cid, uid, item_id)
    target = {"confirmar": "confirmado", "corrigir": "corrigido", "rejeitar": "rejeitado", "validar": "validado"}[body.action]
    if body.action == "corrigir" and not (body.material or "").strip():
        raise HTTPException(422, "Indique o material corrigido.")
    by = user.get("name") or user.get("email") or uid
    if body.layer_order is not None:
        layers = item.get("layers") or []
        layer = next((lay for lay in layers if lay.get("order") == body.layer_order), None)
        if not layer:
            raise HTTPException(404, "Camada não encontrada")
        before = dict(layer)
        layer["validation"] = target
        if body.action == "corrigir":
            layer["material"] = body.material.strip()
            layer["source"] = "manual"
        entry = {"at": _now(), "by": by, "action": f"camada_{target}", "changes": {f"camada {layer['order']}": [before, dict(layer)]}, "note": body.note}
        await db.dossier_obra_items.update_one({"item_id": item_id, "user_id": uid},
                                               {"$set": {"layers": layers, "updated_at": _now()}, "$push": {"history": entry}})
    else:
        sets = {"validation": target, "needs_review": False}
        if body.action == "corrigir":
            sets["title"] = body.material.strip()
            sets["source"] = "manual"
        entry = {"at": _now(), "by": by, "action": target, "changes": {k: [item.get(k), v] for k, v in sets.items()}, "note": body.note}
        await db.dossier_obra_items.update_one({"item_id": item_id, "user_id": uid},
                                               {"$set": {**sets, "updated_at": _now()}, "$push": {"history": entry}})
    return _item_view(await _get_item(cid, uid, item_id), cfg)


@router.post("/{cid}/itens/{item_id}/arquivar")
async def archive_item(cid: str, item_id: str, confirm: bool = False, user=Depends(current_user)) -> dict:
    """Retira o registo da vista sem o apagar (histórico preservado)."""
    uid = user["user_id"]
    await _chantier(cid, uid)
    item = await _get_item(cid, uid, item_id)
    if await _locked_reason(item, uid) and not confirm:
        raise HTTPException(409, "Registo aprovado ou ligado a um compromisso: confirme o arquivo.")
    await db.dossier_obra_items.update_one({"item_id": item_id, "user_id": uid},
                                           {"$set": {"archived": True, "updated_at": _now()},
                                            "$push": {"history": {"at": _now(), "by": user.get("name") or uid, "action": "arquivado"}}})
    return {"ok": True}


@router.get("/{cid}/registos")
async def records_view(cid: str, vista: Literal["especialidade", "fase", "local"] = "especialidade", user=Depends(current_user)) -> dict:
    """Os mesmos registos agrupados por especialidade, fase ou local."""
    uid = user["user_id"]
    await _chantier(cid, uid)
    cfg = await _config(cid, uid)
    specs = _specialties(cfg)
    phases = dict(C.PHASES)
    groups: dict = {}
    for i in await _items(cid, uid):
        if vista == "especialidade":
            gk, gl = i.get("specialty"), (specs.get(i.get("specialty")) or {}).get("label", i.get("specialty"))
        elif vista == "fase":
            gk, gl = i.get("phase") or "_", phases.get(i.get("phase"), "Sem fase")
        else:
            gk, gl = i.get("location_id") or "_", _location_path(cfg, i.get("location_id")) or "Sem local (transversal)"
        g = groups.setdefault(gk, {"key": gk, "label": gl, "items": []})
        g["items"].append(_item_view(i, cfg))
    return {"vista": vista, "groups": list(groups.values())}


# ───────────────────────── «Por organizar» ─────────────────────────

class ClassifyIn(BaseModel):
    kind: Literal["plan", "document", "plans_pro", "site_report", "btp_problem"]
    id: str = Field(..., min_length=1, max_length=80)
    specialty: str = Field(..., max_length=60)
    phase: Optional[str] = Field(None, max_length=30)
    location_id: Optional[str] = Field(None, max_length=40)
    title: str = Field("", max_length=300)


@router.get("/{cid}/por-organizar")
async def unclassified(cid: str, user=Depends(current_user)) -> dict:
    uid = user["user_id"]
    c = await _chantier(cid, uid)
    items = await _unclassified(c, uid)
    return {"total": len(items), "items": items}


@router.post("/{cid}/classificar")
async def classify(cid: str, body: ClassifyIn, user=Depends(current_user)) -> dict:
    """Classifica um registo antigo por REFERÊNCIA (o original não é copiado, movido nem alterado)."""
    uid = user["user_id"]
    c = await _chantier(cid, uid)
    pending = {(x["kind"], x["id"]): x for x in await _unclassified(c, uid)}
    src = pending.get((body.kind, body.id))
    if not src:
        raise HTTPException(404, "Registo não encontrado em «Por organizar»")
    kind = {"plan": "documento", "document": "documento", "plans_pro": "documento", "site_report": "registo", "btp_problem": "pendencia"}[body.kind]
    return await create_item(cid, ItemIn(specialty=body.specialty, kind=kind, title=body.title or src["label"] or body.id,
                                         phase=body.phase, location_id=body.location_id, source="manual", validation="confirmado",
                                         status="concluido" if kind != "pendencia" else "pendente",
                                         ref=RefIn(kind=body.kind, id=body.id)), user)


# ───────────────────────── dependências ─────────────────────────

class DepIn(BaseModel):
    from_specialty: str = Field(..., max_length=60)
    relation: Literal["depende_de", "verificar_antes_de", "partilha_com", "pode_afetar"]
    to_specialty: str = Field(..., max_length=60)
    note: str = Field("", max_length=300)
    confirm: bool = False


@router.get("/{cid}/dependencias")
async def list_deps(cid: str, user=Depends(current_user)) -> dict:
    uid = user["user_id"]
    await _chantier(cid, uid)
    cfg = await _config(cid, uid)
    specs = _specialties(cfg)
    deps = await _deps(cid, uid)
    existing = {(d["from_specialty"], d["relation"], d["to_specialty"]) for d in deps}
    enabled = set(cfg.get("enabled", []))
    suggestions = [{"from_specialty": f, "relation": r, "to_specialty": t, "note": n, "relation_label": C.RELATIONS[r],
                    "from_label": specs[f]["label"], "to_label": specs[t]["label"]}
                   for f, r, t, n in C.SUGGESTED_DEPENDENCIES if f in enabled and t in enabled and (f, r, t) not in existing]
    return {"dependencies": [{**d, "relation_label": C.RELATIONS.get(d["relation"]),
                              "from_label": (specs.get(d["from_specialty"]) or {}).get("label"),
                              "to_label": (specs.get(d["to_specialty"]) or {}).get("label")} for d in deps],
            "suggestions": suggestions,
            "note": "Sequências sugeridas: só passam a valer depois de confirmadas pelo responsável da obra."}


@router.post("/{cid}/dependencias")
async def add_dep(cid: str, body: DepIn, user=Depends(current_user)) -> dict:
    uid = user["user_id"]
    await _chantier(cid, uid)
    cfg = await _config(cid, uid)
    _spec(cfg, body.from_specialty)
    _spec(cfg, body.to_specialty)
    if body.from_specialty == body.to_specialty:
        raise HTTPException(422, "Uma especialidade não depende de si própria")
    dup = await db.dossier_obra_dependencies.find_one({"chantier_id": cid, "user_id": uid, "from_specialty": body.from_specialty,
                                                       "relation": body.relation, "to_specialty": body.to_specialty}, {"_id": 0})
    if dup:
        return dup
    by = user.get("name") or user.get("email") or uid
    dep = {"dep_id": _id("dep"), "chantier_id": cid, "user_id": uid, "from_specialty": body.from_specialty, "relation": body.relation,
           "to_specialty": body.to_specialty, "note": body.note, "status": "confirmada" if body.confirm else "proposta",
           "confirmed_by": by if body.confirm else None, "confirmed_at": _now() if body.confirm else None, "created_at": _now()}
    await db.dossier_obra_dependencies.insert_one(dict(dep))
    dep.pop("_id", None)
    return dep


@router.post("/{cid}/dependencias/{dep_id}/confirmar")
async def confirm_dep(cid: str, dep_id: str, user=Depends(current_user)) -> dict:
    uid = user["user_id"]
    await _chantier(cid, uid)
    res = await db.dossier_obra_dependencies.update_one({"dep_id": dep_id, "chantier_id": cid, "user_id": uid},
                                                        {"$set": {"status": "confirmada", "confirmed_by": user.get("name") or user.get("email") or uid,
                                                                  "confirmed_at": _now()}})
    if not res.matched_count:
        raise HTTPException(404, "Dependência não encontrada")
    return await db.dossier_obra_dependencies.find_one({"dep_id": dep_id, "user_id": uid}, {"_id": 0})


@router.delete("/{cid}/dependencias/{dep_id}")
async def delete_dep(cid: str, dep_id: str, user=Depends(current_user)) -> dict:
    uid = user["user_id"]
    await _chantier(cid, uid)
    res = await db.dossier_obra_dependencies.delete_one({"dep_id": dep_id, "chantier_id": cid, "user_id": uid})
    if not res.deleted_count:
        raise HTTPException(404, "Dependência não encontrada")
    return {"ok": True}


# ───────────────────────── assistente contextual ─────────────────────────

class AssistantCtxIn(BaseModel):
    fase: Optional[str] = Field(None, max_length=30)
    local: Optional[str] = Field(None, max_length=40)


def context_label(spec_label: str, phase: Optional[str], location_path: str) -> str:
    parts = ["Assistente BTP", spec_label]
    if phase:
        parts.append(dict(C.PHASES).get(phase, phase))
    if location_path:
        parts.append(location_path)
    return " · ".join(parts)


@router.post("/{cid}/especialidades/{key}/assistente")
async def specialty_assistant(cid: str, key: str, body: AssistantCtxIn, user=Depends(current_user)) -> dict:
    """Uma conversa por especialidade (reutiliza o Assistente BTP existente, com contexto especializado)."""
    uid = user["user_id"]
    c = await _chantier(cid, uid)
    cfg = await _config(cid, uid)
    spec = {"label": "Compilação", "area": None} if key == COMPILE_KEY else _spec(cfg, key)
    ctx = {"specialty": key, "specialty_label": spec["label"], "area": spec["area"], "phase": body.fase,
           "location_id": body.local, "location_path": _location_path(cfg, body.local)}
    conv = await db.assistant_convs.find_one({"user_id": uid, "chantier_id": cid, "dossier_context.specialty": key}, {"_id": 0, "conversation_id": 1})
    if conv:
        await db.assistant_convs.update_one({"conversation_id": conv["conversation_id"], "user_id": uid},
                                            {"$set": {"dossier_context": ctx, "updated_at": _now()}})
        cid_conv = conv["conversation_id"]
    else:
        from routes.assistant import ConvIn, create_conv
        created = await create_conv(ConvIn(chantier_id=cid, title=f"{c['name']} · {spec['label']}"), user)
        cid_conv = created["conversation_id"]
        await db.assistant_convs.update_one({"conversation_id": cid_conv, "user_id": uid}, {"$set": {"dossier_context": ctx}})
    return {"conversation_id": cid_conv, "context": ctx, "label": context_label(spec["label"], body.fase, ctx["location_path"])}


COMPILE_KEY = "_compilacao"


async def assistant_context(cid: str, uid: str, ctx: dict) -> dict:
    """Contexto especializado entregue ao assistente: só dados registados e autorizados (do próprio utilizador)."""
    cfg = await _config(cid, uid)
    specs = _specialties(cfg)
    key = ctx.get("specialty")
    if key == COMPILE_KEY:
        # Compilação: visão de conjunto (estado e pendências por especialidade ativa), sem dados financeiros.
        items = await _items(cid, uid)
        states = await _states(cid, uid)
        out = []
        for k in [k for k in cfg.get("enabled", []) if k in specs]:
            its = [i for i in items if i.get("specialty") == k]
            out.append({"especialidade": specs[k]["label"], "estado": C.SPECIALTY_STATUS.get((states.get(k) or {}).get("status") or "por_iniciar"),
                        "registos": len(its), "pendencias": [i["title"] for i in its if _display_status(i) == "pendente"][:15],
                        "por_confirmar": [i["title"] for i in its if i.get("validation") == "por_confirmar" and i.get("kind") in ("material", "medicao")][:10]})
        return {"especialidade": "Compilação do dossier", "fase_global_obra": dict(C.PHASES).get(cfg.get("global_phase")), "especialidades": out}
    if key not in specs:
        return {"erreur": "especialidade inexistente"}
    items = await _items(cid, uid, specialty=key)
    states = await _states(cid, uid)

    def brief(i: dict) -> dict:
        return {k: v for k, v in {
            "titulo": i["title"], "tipo": i.get("kind"), "elemento": i.get("element") or None, "estado": i.get("status"),
            "validacao": i.get("validation"), "origem": C.SOURCES.get(i.get("source")), "fase": i.get("phase"),
            "local": _location_path(cfg, i.get("location_id")) or None, "revisao": i.get("revision") or None,
            "medicao": i.get("measurement") or None, "quantidades": i.get("quantities") or None,
            "camadas": [{"n": lay.get("order"), "camada": lay.get("name"), "material": lay.get("material") or None,
                         "origem": lay.get("source"), "validacao": lay.get("validation"), "referencia": lay.get("reference") or None}
                        for lay in i.get("layers") or []] or None,
            "a_rever": i.get("needs_review") or None,
            "preco_unitario": i.get("unit_price"), "origem_preco": i.get("price_source") or None, "unidade": i.get("unit") or None, "pendencia_ligada_a": (specs.get(i.get("related_specialty")) or {}).get("label"),
        }.items() if v not in (None, "", [], {})}
    deps = []
    for d in await _deps(cid, uid):
        if key in (d["from_specialty"], d["to_specialty"]):
            other = d["to_specialty"] if d["from_specialty"] == key else d["from_specialty"]
            other_items = await _items(cid, uid, specialty=other)
            deps.append({"relacao": f"{specs.get(d['from_specialty'], {}).get('label')} — {C.RELATIONS.get(d['relation'])} — "
                                    f"{specs.get(d['to_specialty'], {}).get('label')}",
                         "confirmada": d.get("status") == "confirmada",
                         "pendencias_da_outra": [x["title"] for x in other_items if _is_open(x)][:10]})
    st = states.get(key) or {}
    return {"especialidade": specs[key]["label"], "area": dict((a[0], a[1]) for a in C.AREAS).get(specs[key]["area"]),
            "fase_global_obra": dict(C.PHASES).get(cfg.get("global_phase")), "fase_selecionada": dict(C.PHASES).get(ctx.get("phase")),
            "local_selecionado": ctx.get("location_path") or None, "estado": C.SPECIALTY_STATUS.get(st.get("status") or "por_iniciar"),
            "etapa": dict(C.STAGES).get(st.get("stage") or "preparar"), "responsavel": st.get("responsible") or None,
            "registos": [brief(i) for i in items][:80], "dependencias": deps}


ASSISTANT_RULES = (
    "CONTEXTO DE ESPECIALIDADE (dossier de obra, chave `dossier_especialidade`). Trabalha APENAS com estes registos e com o processo "
    "de obra. Na resposta separa claramente, com títulos curtos: **Factos** (registados, cita documento e revisão quando existirem), "
    "**Cálculos** (mostra a fórmula e os valores de origem), **Hipóteses** e **Sugestões**. Indica a informação em falta. Nunca "
    "inventes medidas, preços, materiais nem conformidade regulamentar: uma trama ou legenda não prova o material nem todas as camadas. "
    "Se for relevante, considera as dependências e pendências das outras especialidades indicadas. Antes de qualquer alteração com "
    "impacto (orçamento aceite, encomenda, auto, documento aprovado) pede validação explícita ao utilizador.")


# ───────────────────────── orçamento por especialidade ─────────────────────────

def _line_total(i: dict) -> Optional[float]:
    q = (i.get("quantities") or {}).get("orcamentada")
    return None if q is None or i.get("unit_price") is None else round(q * i["unit_price"], 2)


async def budget_model(cid: str, uid: str, keys: Optional[list[str]] = None) -> dict:
    """Orçamento por especialidade: cada módulo é orçamentado sozinho; o total é a soma dos módulos escolhidos."""
    cfg = await _config(cid, uid)
    specs = _specialties(cfg)
    lines = [i for i in await _items(cid, uid, kind="orcamento") if i.get("status") != "nao_aplicavel"]
    order = [k for k in (keys or cfg.get("enabled", [])) if k in specs]
    out, total, missing = [], 0.0, 0
    for k in order:
        ls = [i for i in lines if i.get("specialty") == k]
        if not ls and keys is None:
            continue
        rows = []
        for i in ls:
            t = _line_total(i)
            if t is None:
                missing += 1
            rows.append({"item_id": i["item_id"], "title": i["title"], "element": i.get("element") or "", "unit": i.get("unit") or "",
                         "qty": (i.get("quantities") or {}).get("orcamentada"), "unit_price": i.get("unit_price"), "vat_rate": i.get("vat_rate"),
                         "total": t, "price_source": i.get("price_source") or "", "price_reference": i.get("price_reference") or "",
                         "from_item_id": i.get("from_item_id"), "status": _display_status(i)})
        sub = round(sum(r["total"] or 0 for r in rows), 2)
        total += sub
        out.append({"key": k, "label": specs[k]["label"], "area": specs[k]["area"], "lines": rows, "subtotal_ht": sub,
                    "missing_prices": len([r for r in rows if r["total"] is None])})
    return {"specialties": out, "total_ht": round(total, 2), "missing_prices": missing,
            "note": "Totais só com linhas com quantidade e preço. Preços de mercado ficam por confirmar; nenhum preço é inventado."}


@router.get("/{cid}/orcamento")
async def budget(cid: str, especialidades: str = "", user=Depends(current_user)) -> dict:
    uid = user["user_id"]
    await _chantier(cid, uid)
    if not _can_finance(user):
        raise HTTPException(403, "A sua função não permite ver orçamentos.")
    keys = [k for k in especialidades.split(",") if k] or None
    return await budget_model(cid, uid, keys)


class BudgetDraftIn(BaseModel):
    specialties: list[str] = Field(default_factory=list, max_length=200)   # vazio = todas as que têm linhas
    title: str = Field("", max_length=160)


@router.post("/{cid}/orcamento/rascunho")
async def budget_to_quote(cid: str, body: BudgetDraftIn, user=Depends(current_user)) -> dict:
    """Cria um NOVO orçamento em rascunho no módulo de orçamentos (nunca altera orçamentos existentes)."""
    uid = user["user_id"]
    c = await _chantier(cid, uid)
    if not _can_finance(user):
        raise HTTPException(403, "A sua função não permite criar orçamentos.")
    model = await budget_model(cid, uid, body.specialties or None)
    groups = [g for g in model["specialties"] if g["lines"]]
    if not groups:
        raise HTTPException(422, "Sem linhas de orçamento nas especialidades escolhidas.")
    from routes.documents import DocIn, DocLine, create_document
    lines = []
    for g in groups:
        lines.append(DocLine(kind="section", title=g["label"]))
        for r in g["lines"]:
            lines.append(DocLine(kind="line", designation=r["title"], description=r["element"], unit=r["unit"] or "u",
                                 qty=r["qty"] if r["qty"] is not None else 0, unit_price_ht=r["unit_price"] if r["unit_price"] is not None else 0,
                                 vat_rate=r["vat_rate"], category=g["label"],
                                 price_source=r["price_source"] or ("a_definir" if r["unit_price"] is None else ""), price_reference=r["price_reference"]))
    title = body.title.strip() or (f"{c['name']} — {groups[0]['label']}" if len(groups) == 1 else f"{c['name']} — orçamento completo")
    notes = "Gerado a partir do dossier de obra."
    if model["missing_prices"]:
        notes += f" {model['missing_prices']} linha(s) sem preço ou quantidade: a completar antes de enviar."
    doc = await create_document(DocIn(doc_type="quote", title=title, lines=lines, notes=notes, chantier_id=cid, client_id=c.get("client_id"), status="draft"), user)
    return {"doc_id": doc["doc_id"], "title": title, "specialties": [g["label"] for g in groups], "total_ht": model["total_ht"],
            "missing_prices": model["missing_prices"]}


# ───────────────────────── compilação do dossier ─────────────────────────

class SelectionIn(BaseModel):
    scope: Literal["especialidade", "fase_local", "global"] = "global"
    specialties: list[str] = Field(default_factory=list, max_length=200)   # vazio = todas as ativas
    phases: list[str] = Field(default_factory=list, max_length=10)
    locations: list[str] = Field(default_factory=list, max_length=100)
    content: Literal["validado", "validado_pendencias", "tudo"] = "validado_pendencias"
    include: list[Literal["medicoes", "materiais", "registos", "verificacoes", "alteracoes", "pendencias", "fotografias", "anexos", "financeiro"]] = \
        Field(default_factory=lambda: ["medicoes", "materiais", "registos", "verificacoes", "alteracoes", "pendencias", "fotografias", "anexos"])
    recipient: Literal["dono_obra", "fiscalizacao", "equipa", "interno"] = "dono_obra"
    title: str = Field("", max_length=160)


RECIPIENTS = {"dono_obra": "Dono de obra", "fiscalizacao": "Fiscalização", "equipa": "Equipa e subempreiteiros", "interno": "Uso interno"}
STATUS_LABEL = {"validado": "Validado", "rascunho": "Rascunho", "pendente": "Pendente", "nao_aplicavel": "Não aplicável", "rejeitado": "Rejeitado"}


async def build_model(cid: str, user: dict, sel: SelectionIn) -> dict:
    """Modelo do documento (fonte única para pré-visualização, PDF, DOCX, XLSX e ZIP)."""
    uid = user["user_id"]
    c = await _chantier(cid, uid)
    cfg = await _config(cid, uid)
    specs = _specialties(cfg)
    states = await _states(cid, uid)
    enabled = [k for k in cfg.get("enabled", []) if k in specs and k not in cfg.get("hidden", [])]
    chosen = [k for k in (sel.specialties or enabled) if k in specs]
    if sel.scope == "especialidade" and len(chosen) != 1:
        raise HTTPException(422, "O relatório de especialidade exige exatamente uma especialidade.")
    if not chosen:
        raise HTTPException(422, "Selecione pelo menos uma especialidade.")
    finance_requested = "financeiro" in sel.include
    finance = finance_requested and _can_finance(user)
    warnings = []
    if finance_requested and not finance:
        warnings.append("Informação financeira excluída: a sua função não permite este acesso.")
    if finance and sel.recipient in ("equipa",):
        warnings.append("Atenção: informação financeira incluída num documento para a equipa.")
    phases = dict(C.PHASES)
    all_items = await _items(cid, uid)

    def keep(i: dict) -> bool:
        if i.get("specialty") not in chosen:
            return False
        if sel.phases and i.get("phase") and i["phase"] not in sel.phases:
            return False
        if sel.locations and i.get("location_id") and not any(i["location_id"] == loc or _is_ancestor(cfg, i["location_id"], loc) for loc in sel.locations):
            return False
        ds = _display_status(i)
        if ds == "rejeitado" and "alteracoes" not in sel.include:
            return False
        if sel.content == "validado" and ds not in ("validado", "nao_aplicavel"):
            return False
        if sel.content == "validado_pendencias" and ds == "rascunho":
            return False
        return True

    items = [i for i in all_items if keep(i)]
    chapters = []
    for ak, alabel, _d, _i in C.AREAS:
        sp = []
        for k in chosen:
            if specs[k]["area"] != ak:
                continue
            its = [i for i in items if i["specialty"] == k]
            st = states.get(k) or {}
            sp.append({"key": k, "label": specs[k]["label"], "status": C.SPECIALTY_STATUS.get(st.get("status") or "por_iniciar"),
                       "stage": dict(C.STAGES).get(st.get("stage") or "preparar"), "responsible": st.get("responsible") or "",
                       "items": [{"title": i["title"], "kind": C.ITEM_KINDS.get(i.get("kind")), "element": i.get("element") or "",
                                  "status": STATUS_LABEL[_display_status(i)], "status_key": _display_status(i),
                                  "phase": phases.get(i.get("phase"), ""), "location": _location_path(cfg, i.get("location_id")),
                                  "revision": i.get("revision") or "", "source": C.SOURCES.get(i.get("source"), ""),
                                  "detail": i.get("detail") or ""} for i in its],
                       "counts": {s: len([i for i in its if _display_status(i) == s]) for s in STATUS_LABEL}})
        if sp:
            chapters.append({"key": ak, "label": alabel, "specialties": sp})

    def rows(kind: str) -> list[dict]:
        return [i for i in items if i.get("kind") == kind]
    measurements = [{"specialty": specs[i["specialty"]]["label"], "title": i["title"], "element": i.get("element") or "",
                     "location": _location_path(cfg, i.get("location_id")), **{f"m_{k}": v for k, v in (i.get("measurement") or {}).items()},
                     "quantities": {k: v for k, v in (i.get("quantities") or {}).items() if finance or k not in ("faturada",)},
                     "status": STATUS_LABEL[_display_status(i)]}
                    for i in items if i.get("measurement") or i.get("quantities")] if "medicoes" in sel.include else []
    materials = [{"specialty": specs[i["specialty"]]["label"], "title": i["title"], "element": i.get("element") or "",
                  "status": STATUS_LABEL[_display_status(i)], "source": C.SOURCES.get(i.get("source"), ""),
                  "layers": [{"order": lay.get("order"), "name": lay.get("name"), "material": lay.get("material") or "—",
                              "source": C.SOURCES.get(lay.get("source"), ""), "validation": C.VALIDATION.get(lay.get("validation"), ""),
                              "reference": lay.get("reference") or ""} for lay in i.get("layers") or []]}
                 for i in rows("material")] if "materiais" in sel.include else []
    records = [{"specialty": specs[i["specialty"]]["label"], "title": i["title"], "kind": C.ITEM_KINDS.get(i["kind"]),
                "status": STATUS_LABEL[_display_status(i)], "date": (i.get("created_at") or "")[:10]}
               for i in items if i.get("kind") in ("registo", "verificacao") and
               (("registos" in sel.include and i["kind"] == "registo") or ("verificacoes" in sel.include and i["kind"] == "verificacao"))]
    changes = []
    if "alteracoes" in sel.include:
        for i in items:
            for h in i.get("history") or []:
                if h.get("action") not in ("criado",):
                    changes.append({"date": (h.get("at") or "")[:10], "specialty": specs[i["specialty"]]["label"], "title": i["title"],
                                    "action": h.get("action"), "by": h.get("by"), "note": h.get("note") or ""})
        changes.sort(key=lambda x: x["date"])
    pend = [{"specialty": specs[i["specialty"]]["label"], "title": i["title"], "status": C.TASK_STATUS.get(i.get("status"), ""),
             "related": (specs.get(i.get("related_specialty")) or {}).get("label", "")}
            for i in items if _display_status(i) == "pendente"] if "pendencias" in sel.include else []
    refs = [{"specialty": specs[i["specialty"]]["label"], "title": i["title"], "ref_kind": (i.get("ref") or {}).get("kind"),
             "ref_id": (i.get("ref") or {}).get("id"), "revision": i.get("revision") or ""}
            for i in items if i.get("ref") or i.get("kind") == "documento"]
    photos = []
    if "fotografias" in sel.include:
        report_ids = [(i.get("ref") or {}).get("id") for i in items if (i.get("ref") or {}).get("kind") == "site_report"]
        if report_ids:
            reps = await db.site_reports.find({"user_id": uid, "report_id": {"$in": report_ids}}, {"_id": 0, "report_id": 1, "title": 1, "photos": 1}).to_list(200)
            for r in reps:
                photos += [{"report": r.get("title") or r["report_id"], "path": p} for p in (r.get("photos") or [])][:50]
    finance_block = None
    if finance:
        from routes.chantiers import build_dossier
        d = await build_dossier(cid, uid)
        finance_block = {"kpis": d.get("kpis"),
                         "documents": [{"number": x.get("number"), "title": x.get("title"), "type": x.get("doc_type"), "status": x.get("status"),
                                        "total_ht": (x.get("totals") or {}).get("ht"), "total_ttc": (x.get("totals") or {}).get("ttc")}
                                       for x in d.get("documents", [])[:100]]}
    budget_block = None
    if finance:
        b = await budget_model(cid, uid, chosen)
        if any(g["lines"] for g in b["specialties"]):
            b["specialties"] = [g for g in b["specialties"] if g["lines"]]
            budget_block = b
    revisions = sorted({f"{i.get('measurement', {}).get('document') if i.get('measurement') else i['title']} · {i['revision']}"
                        for i in items if i.get("revision")})
    totals = {s: len([i for i in items if _display_status(i) == s]) for s in STATUS_LABEL}
    branding = None
    try:
        from routes.plans_common import _resolve_branding
        b = await _resolve_branding(uid) or {}
        branding = {"company": b.get("company_name") or b.get("brand_company_name") or "", "logo_b64": b.get("logo_b64") or b.get("brand_logo_b64")}
    except Exception:  # noqa: BLE001 — o logótipo é opcional
        branding = None
    toc = ["Resumo", *[ch["label"] for ch in chapters]]
    toc += [t for t, ok in (("Plantas e referências", refs), ("Medições", measurements), ("Materiais e sistemas", materials),
                            ("Registos e verificações", records), ("Alterações", changes), ("Pendências", pend),
                            ("Orçamento por especialidade", budget_block), ("Informação financeira", finance_block), ("Anexos", photos or refs)) if ok]
    toc.append("Identificação da emissão")
    kind_title = {"especialidade": f"Relatório da especialidade — {specs[chosen[0]]['label']}" if len(chosen) == 1 else "Relatório",
                  "fase_local": "Relatório de fase / local", "global": "Dossier de obra"}[sel.scope]
    return {
        "title": sel.title.strip() or kind_title, "scope": sel.scope,
        "obra": {"name": c["name"], "ref": c.get("ref") or c["chantier_id"], "client": c.get("client_name") or "",
                 "address": " ".join(filter(None, [c.get("address"), c.get("postal_code"), c.get("city")])),
                 "global_phase": phases.get(cfg.get("global_phase"), "Não definida"), "demo": bool(c.get("demo"))},
        "recipient": RECIPIENTS[sel.recipient], "content_label": {"validado": "Só informação validada",
                                                                  "validado_pendencias": "Informação validada e pendências",
                                                                  "tudo": "Tudo, incluindo rascunhos"}[sel.content],
        "filters": {"phases": [phases.get(p, p) for p in sel.phases], "locations": [_location_path(cfg, loc) for loc in sel.locations]},
        "toc": toc, "summary": {"specialties": len(chosen), "items": len(items), **totals},
        "chapters": chapters, "references": refs, "measurements": measurements, "materials": materials, "records": records,
        "changes": changes, "pendencias": pend, "photos": photos, "finance": finance_block, "budget": budget_block, "revisions": revisions,
        "warnings": warnings, "branding": branding,
        "notice": "A compilação reúne a informação registada e não equivale à validação técnica da obra.",
        "selection": sel.model_dump(),
    }


@router.post("/{cid}/compilar/previsualizar")
async def preview(cid: str, body: SelectionIn, user=Depends(current_user)) -> dict:
    model = await build_model(cid, user, body)
    model.pop("branding", None)
    return model


@router.post("/{cid}/emissoes")
async def create_emission(cid: str, body: SelectionIn, user=Depends(current_user)) -> dict:
    uid = user["user_id"]
    model = await build_model(cid, user, body)
    last = await db.dossier_obra_emissions.find({"chantier_id": cid, "user_id": uid}, {"_id": 0, "version": 1}).sort("version", -1).limit(1).to_list(1)
    version = (last[0]["version"] + 1) if last else 1
    now = _now()
    model["emission"] = {"version": version, "date": now, "by": user.get("name") or user.get("email") or uid,
                         "status": "Emissão compilada (não constitui validação técnica)"}
    snap = json.dumps(model, ensure_ascii=False, sort_keys=True, default=str)
    em = {"emission_id": _id("emi"), "chantier_id": cid, "user_id": uid, "version": version, "created_at": now, "scope": body.scope,
          "title": model["title"], "recipient": model["recipient"], "summary": model["summary"],
          "specialties": [s["label"] for ch in model["chapters"] for s in ch["specialties"]], "revisions": model["revisions"],
          "formats": ["pdf", "docx", "xlsx", "zip"], "sha256": hashlib.sha256(snap.encode()).hexdigest(), "snapshot": snap}
    await db.dossier_obra_emissions.insert_one(dict(em))
    em.pop("_id", None)
    em.pop("snapshot", None)
    return em


@router.get("/{cid}/emissoes")
async def list_emissions(cid: str, user=Depends(current_user)) -> dict:
    uid = user["user_id"]
    await _chantier(cid, uid)
    rows = await db.dossier_obra_emissions.find({"chantier_id": cid, "user_id": uid}, {"_id": 0, "snapshot": 0}).sort("version", -1).to_list(200)
    return {"emissions": rows}


async def _emission(cid: str, uid: str, eid: str) -> dict:
    await _chantier(cid, uid)
    em = await db.dossier_obra_emissions.find_one({"emission_id": eid, "chantier_id": cid, "user_id": uid}, {"_id": 0})
    if not em:
        raise HTTPException(404, "Emissão não encontrada")
    return em


@router.get("/{cid}/emissoes/{eid}")
async def get_emission(cid: str, eid: str, user=Depends(current_user)) -> dict:
    em = await _emission(cid, user["user_id"], eid)
    model = json.loads(em.pop("snapshot"))
    model.pop("branding", None)
    return {**em, "model": model}


@router.get("/{cid}/emissoes/{eid}/ficheiro")
async def emission_file(cid: str, eid: str, formato: Literal["pdf", "docx", "xlsx", "zip"] = Query("pdf"),
                        user=Depends(current_user)):
    from engines import dossier_obra_export as X
    em = await _emission(cid, user["user_id"], eid)
    model = json.loads(em["snapshot"])
    name = X.filename(model, formato)
    if formato == "pdf":
        data, mt = X.to_pdf(model), "application/pdf"
    elif formato == "docx":
        data, mt = X.to_docx(model), "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    elif formato == "xlsx":
        data, mt = X.to_xlsx(model), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    else:
        data, mt = await X.to_zip(model), "application/zip"
    return Response(content=data, media_type=mt, headers={"Content-Disposition": f'attachment; filename="{name}"',
                                                          "Cache-Control": "private, no-store"})


# ───────────────────────── dados fictícios (só fora de produção) ─────────────────────────

@router.post("/demo")
async def create_demo(user=Depends(current_user)) -> dict:
    """Cria a obra fictícia «Moradia em L (exemplo demonstrativo)» — recusado em produção."""
    from core.environment import is_relaxed
    if not is_relaxed():
        raise HTTPException(403, "Dados fictícios indisponíveis neste ambiente.")
    from engines.dossier_obra_demo import seed
    return await seed(db, user)
