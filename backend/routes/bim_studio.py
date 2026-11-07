"""API do ConstruPilot BIM Studio (exclusivo construpilot.pt).

Prefixo: /api/bim. Todas as rotas exigem conta profissional; as alterações exigem a
permissão "devis" da organização. Os dados são isolados por organização (tenant).
"""
from __future__ import annotations

import base64
import csv
import hashlib
import hmac
import io
import json
import re
import secrets
import time
from typing import Literal

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, Field

from bim_studio import budget as bud
from bim_studio import config, jobs, storage
from bim_studio.constants import CATEGORIES, QTY_LABELS, UNIT_OF
from bim_studio.store import audit, get_db, now, tenant_of
from core.permissions import require_feature
from core.security import pro_required

router = APIRouter(prefix="/bim", tags=["bim-studio"])
files_router = APIRouter(prefix="/bim", tags=["bim-studio"])

PROFILES = ("arquiteto", "engenheiro", "empresa", "simples")
_SCHEMA_RE = re.compile(rb"FILE_SCHEMA\s*\(\s*\(\s*'([A-Za-z0-9_]+)'")
SUPPORTED_SCHEMAS = ("IFC2X3", "IFC4", "IFC4X1", "IFC4X2", "IFC4X3", "IFC4X3_ADD1", "IFC4X3_ADD2", "IFC4X3_TC1")


# ── Guardas ──────────────────────────────────────────────────────────────────
def _require_enabled():
    if not config.enabled():
        raise HTTPException(404, "BIM Studio indisponível.")


async def viewer(user=Depends(pro_required)):
    _require_enabled()
    return user


async def editor(user=Depends(pro_required)):
    _require_enabled()
    require_feature(user, "devis")
    return user


async def _model(model_id: str, user: dict) -> dict:
    m = await get_db().bim_models.find_one({"model_id": model_id, "tenant_id": tenant_of(user),
                                            "deleted": {"$ne": True}}, {"_id": 0})
    if not m:  # 404 também para modelos de outra empresa (não revela existência)
        raise HTTPException(404, "Modelo não encontrado.")
    return m


async def _version(model_id: str, version: int, user: dict, done: bool = False) -> dict:
    await _model(model_id, user)
    v = await get_db().bim_versions.find_one({"model_id": model_id, "version": version,
                                              "tenant_id": tenant_of(user)}, {"_id": 0})
    if not v:
        raise HTTPException(404, "Versão não encontrada.")
    if done and v.get("status") != "done":
        raise HTTPException(409, "O modelo ainda não foi processado.")
    return v


def _public_version(v: dict) -> dict:
    return {k: v.get(k) for k in (
        "model_id", "version", "filename", "size", "status", "progress", "stage", "error", "error_code",
        "warnings", "stats", "storeys", "units", "schema", "engine_version", "ifcopenshell_version",
        "created_at", "started_at", "finished_at", "duration_s", "created_by_name") if k in v} | {
        "chunks": len(v.get("chunk_keys") or [])}


async def _overrides(model_id: str, version: int) -> dict:
    out = {}
    async for o in get_db().bim_overrides.find({"model_id": model_id, "version": version}, {"_id": 0}):
        out[(o["gid"], o["key"])] = o
    return out


async def _elements(model_id: str, version: int, projection: dict | None = None) -> list[dict]:
    proj = {"_id": 0, "properties": 0} if projection is None else projection
    return await get_db().bim_elements.find({"model_id": model_id, "version": version}, proj).to_list(None)


async def _tenant_user_ids(user: dict) -> list[str]:
    if user.get("organization_id"):
        ids = [u["user_id"] async for u in get_db().users.find(
            {"organization_id": user["organization_id"]}, {"_id": 0, "user_id": 1})]
        return ids or [user["user_id"]]
    return [user["user_id"]]


async def _library(user: dict) -> list[dict]:
    try:  # reutiliza o catálogo inicial da biblioteca existente
        from routes.library import _seed_if_needed
        await _seed_if_needed(user)
    except Exception:  # noqa: BLE001
        pass
    ids = await _tenant_user_ids(user)
    return await get_db().library_items.find({"user_id": {"$in": ids}}, {"_id": 0}).to_list(5000)


# ── Configuração e perfil ────────────────────────────────────────────────────
@router.get("/config")
async def bim_config(user=Depends(pro_required)):
    pref = await get_db().bim_prefs.find_one({"user_id": user["user_id"]}, {"_id": 0}) or {}
    return {"enabled": config.enabled(), "max_upload_mb": config.MAX_UPLOAD_MB,
            "profile": pref.get("profile"), "profiles": list(PROFILES),
            "categories": CATEGORIES, "quantity_labels": QTY_LABELS, "origin_labels": bud.ORIGIN_LABELS}


class PrefsIn(BaseModel):
    profile: Literal["arquiteto", "engenheiro", "empresa", "simples"]


@router.put("/prefs")
async def set_prefs(body: PrefsIn, user=Depends(viewer)):
    await get_db().bim_prefs.update_one({"user_id": user["user_id"]},
                                        {"$set": {"profile": body.profile, "updated_at": now()}}, upsert=True)
    return {"profile": body.profile}


@router.get("/library")
async def bim_library(user=Depends(viewer)):
    """Artigos da biblioteca da empresa (preços definidos pela empresa — nunca inventados)."""
    items = await _library(user)
    return {"items": [{k: i.get(k) for k in ("item_id", "designation", "category", "unit", "unit_price_ht",
                                              "vat_rate", "type")} for i in items]}


# ── Upload ───────────────────────────────────────────────────────────────────
async def _read_limited(file: UploadFile, limit: int) -> bytes:
    buf = io.BytesIO()
    while True:
        chunk = await file.read(1024 * 1024)
        if not chunk:
            break
        buf.write(chunk)
        if buf.tell() > limit:
            raise HTTPException(413, f"Ficheiro demasiado grande (máximo {config.MAX_UPLOAD_MB} MB).")
    return buf.getvalue()


def validate_ifc_bytes(filename: str, data: bytes) -> str:
    """Valida extensão, cabeçalho STEP e esquema IFC. Devolve o esquema."""
    name = (filename or "").lower()
    if name.endswith((".ifcxml", ".ifczip")):
        raise HTTPException(415, "Formatos ifcXML/ifcZIP ainda não suportados — exporte em IFC (STEP).")
    if not name.endswith(".ifc"):
        raise HTTPException(415, "Só são aceites ficheiros .ifc.")
    if len(data) < 64:
        raise HTTPException(422, "Ficheiro IFC vazio ou incompleto.")
    head = data[:4096]
    if not head.lstrip(b"\xef\xbb\xbf \r\n\t").startswith(b"ISO-10303-21"):
        raise HTTPException(422, "O ficheiro não é um IFC válido (cabeçalho ISO-10303-21 em falta).")
    m = _SCHEMA_RE.search(data[:65536])
    schema = m.group(1).decode().upper() if m else ""
    if schema not in SUPPORTED_SCHEMAS:
        raise HTTPException(422, f"Esquema IFC não suportado: {schema or 'desconhecido'}.")
    if b"END-ISO-10303-21" not in data[-4096:]:
        raise HTTPException(422, "Ficheiro IFC truncado (fim de ficheiro em falta).")
    return schema


@router.post("/models")
async def upload_model(file: UploadFile = File(...), name: str = Form(""), project_id: str = Form(""),
                       model_id: str = Form(""), user=Depends(editor)):
    db = get_db()
    tenant = tenant_of(user)
    data = await _read_limited(file, config.MAX_UPLOAD_MB * 1024 * 1024)
    schema = validate_ifc_bytes(file.filename or "", data)
    sha = hashlib.sha256(data).hexdigest()
    safe_name = re.sub(r"[^A-Za-z0-9._ \-À-ÿ]", "_", (file.filename or "modelo.ifc"))[:120]
    if project_id:
        ids = await _tenant_user_ids(user)
        if not await db.projects.find_one({"project_id": project_id, "user_id": {"$in": ids}}, {"_id": 1}):
            raise HTTPException(404, "Projeto não encontrado.")
    if model_id:
        model = await _model(model_id, user)
        last = await db.bim_versions.find_one({"model_id": model_id}, {"_id": 0, "version": 1},
                                              sort=[("version", -1)])
        version = int((last or {}).get("version", 0)) + 1
    else:
        count = await db.bim_models.count_documents({"tenant_id": tenant, "deleted": {"$ne": True}})
        if count >= config.MAX_MODELS_PER_TENANT:
            raise HTTPException(429, "Limite de modelos BIM da empresa atingido.")
        model_id = "bim_" + secrets.token_hex(8)
        model = {"model_id": model_id, "tenant_id": tenant, "owner_user_id": user["user_id"],
                 "name": (name or safe_name.rsplit(".", 1)[0])[:120], "project_id": project_id or None,
                 "created_at": now(), "updated_at": now(), "deleted": False}
        await db.bim_models.insert_one(dict(model))
        version = 1
    key = storage.key_for(tenant, model_id, version, "model.ifc")
    await storage.put(key, data, "application/x-step")
    v = {"model_id": model_id, "version": version, "tenant_id": tenant, "filename": safe_name,
         "size": len(data), "sha256": sha, "schema": schema, "storage_key": key, "status": "queued",
         "progress": 0.0, "stage": "em fila de espera", "attempts": 0, "created_by": user["user_id"],
         "created_by_name": user.get("name"), "created_at": now()}
    await db.bim_versions.insert_one(dict(v))
    await db.bim_models.update_one({"model_id": model_id}, {"$set": {"latest_version": version, "updated_at": now()}})
    await audit(user, "upload", model_id, version, filename=safe_name, size=len(data), sha256=sha)
    jobs.wake()
    return {"model_id": model_id, "version": version, "status": "queued", "schema": schema}


# ── Modelos e versões ────────────────────────────────────────────────────────
@router.get("/models")
async def list_models(user=Depends(viewer)):
    db = get_db()
    models = await db.bim_models.find({"tenant_id": tenant_of(user), "deleted": {"$ne": True}},
                                      {"_id": 0}).sort("updated_at", -1).to_list(500)
    for m in models:
        v = await db.bim_versions.find_one({"model_id": m["model_id"], "version": m.get("latest_version", 1)},
                                           {"_id": 0})
        m["latest"] = _public_version(v) if v else None
    return {"items": models}


@router.get("/models/{model_id}")
async def get_model(model_id: str, user=Depends(viewer)):
    m = await _model(model_id, user)
    versions = await get_db().bim_versions.find({"model_id": model_id, "tenant_id": tenant_of(user)},
                                                {"_id": 0}).sort("version", -1).to_list(100)
    m["versions"] = [_public_version(v) for v in versions]
    return m


@router.delete("/models/{model_id}")
async def delete_model(model_id: str, user=Depends(editor)):
    await _model(model_id, user)
    await get_db().bim_models.update_one({"model_id": model_id}, {"$set": {"deleted": True, "deleted_at": now()}})
    await audit(user, "delete_model", model_id)
    return {"ok": True}


@router.get("/models/{model_id}/versions/{version}")
async def get_version(model_id: str, version: int, user=Depends(viewer)):
    return _public_version(await _version(model_id, version, user))


@router.post("/models/{model_id}/versions/{version}/cancel")
async def cancel_version(model_id: str, version: int, user=Depends(editor)):
    v = await _version(model_id, version, user)
    if v["status"] not in ("queued", "processing"):
        raise HTTPException(409, "Este processamento já terminou.")
    await jobs.cancel(model_id, version)
    await audit(user, "cancel", model_id, version)
    return {"ok": True}


@router.post("/models/{model_id}/versions/{version}/retry")
async def retry_version(model_id: str, version: int, user=Depends(editor)):
    v = await _version(model_id, version, user)
    if v["status"] not in ("failed", "cancelled"):
        raise HTTPException(409, "Só é possível relançar um processamento falhado ou anulado.")
    await get_db().bim_versions.update_one({"model_id": model_id, "version": version}, {"$set": {
        "status": "queued", "progress": 0.0, "stage": "em fila de espera", "error": None, "error_code": None,
        "cancel_requested": False, "attempts": 0, "created_at": now()}})
    await audit(user, "retry", model_id, version)
    jobs.wake()
    return {"ok": True}


# ── Elementos e medições ─────────────────────────────────────────────────────
@router.get("/models/{model_id}/versions/{version}/elements")
async def list_elements(model_id: str, version: int, category: str | None = None, storey: str | None = None,
                        q: str | None = None, missing: bool = False, skip: int = Query(0, ge=0),
                        limit: int = Query(200, ge=1, le=1000), user=Depends(viewer)):
    await _version(model_id, version, user, done=True)
    flt: dict = {"model_id": model_id, "version": version}
    if category:
        flt["category"] = category
    if storey:
        flt["storey_gid"] = storey
    if missing:
        flt["missing.0"] = {"$exists": True}
    if q:
        rx = re.escape(q[:60])
        flt["$or"] = [{"name": {"$regex": rx, "$options": "i"}}, {"gid": q[:30]},
                      {"type_name": {"$regex": rx, "$options": "i"}}]
    db = get_db()
    total = await db.bim_elements.count_documents(flt)
    rows = await db.bim_elements.find(flt, {"_id": 0, "properties": 0}).sort([("category", 1), ("name", 1)]) \
        .skip(skip).limit(limit).to_list(limit)
    ov = await _overrides(model_id, version)
    return {"total": total, "items": [bud.element_view(e, ov) for e in rows]}


@router.get("/models/{model_id}/versions/{version}/elements/{gid}")
async def get_element(model_id: str, version: int, gid: str, user=Depends(viewer)):
    await _version(model_id, version, user, done=True)
    e = await get_db().bim_elements.find_one({"model_id": model_id, "version": version, "gid": gid}, {"_id": 0})
    if not e:
        raise HTTPException(404, "Elemento não encontrado.")
    return bud.element_view(e, await _overrides(model_id, version))


class QtyEdit(BaseModel):
    value: float | None = Field(default=None, ge=0, le=1e9, allow_inf_nan=False)
    note: str = Field(default="", max_length=300)
    reset: bool = False


class ElementPatch(BaseModel):
    included: bool | None = None
    quantities: dict[str, QtyEdit] = {}
    validate_keys: list[str] = Field(default=[], alias="validate")

    model_config = {"populate_by_name": True}


@router.patch("/models/{model_id}/versions/{version}/elements/{gid}")
async def patch_element(model_id: str, version: int, gid: str, body: ElementPatch, user=Depends(editor)):
    await _version(model_id, version, user, done=True)
    db = get_db()
    e = await db.bim_elements.find_one({"model_id": model_id, "version": version, "gid": gid}, {"_id": 0})
    if not e:
        raise HTTPException(404, "Elemento não encontrado.")
    if body.included is not None:
        if body.included and not e.get("counted", True):
            raise HTTPException(409, "Elemento agregador: as quantidades estão nos sub-elementos (evita contagem dupla).")
        await db.bim_elements.update_one({"model_id": model_id, "version": version, "gid": gid},
                                         {"$set": {"included": body.included}})
    for key, ed in body.quantities.items():
        if key not in QTY_LABELS:
            raise HTTPException(422, f"Quantidade desconhecida: {key}")
        sel = {"model_id": model_id, "version": version, "gid": gid, "key": key}
        if ed.reset:
            await db.bim_overrides.delete_one(sel)
            continue
        if ed.value is None:
            raise HTTPException(422, "Valor em falta.")
        await db.bim_overrides.update_one(sel, {"$set": {
            **sel, "tenant_id": tenant_of(user), "value": float(ed.value), "corrected": True, "validated": True,
            "unit": UNIT_OF.get(key, ""),
            "note": ed.note, "by": user.get("name") or user["user_id"], "at": now(),
            "previous": ((e.get("quantities") or {}).get(key) or {}).get("value")}}, upsert=True)
    for key in body.validate_keys:
        if key not in (e.get("quantities") or {}):
            raise HTTPException(422, f"Não existe quantidade {key} para validar.")
        sel = {"model_id": model_id, "version": version, "gid": gid, "key": key}
        await db.bim_overrides.update_one(sel, {"$set": {**sel, "tenant_id": tenant_of(user), "validated": True,
                                                         "by": user.get("name") or user["user_id"], "at": now()}},
                                          upsert=True)
    await audit(user, "edit_element", model_id, version, gid=gid, included=body.included,
                quantities={k: v.model_dump() for k, v in body.quantities.items()}, validated=body.validate_keys)
    e = await db.bim_elements.find_one({"model_id": model_id, "version": version, "gid": gid}, {"_id": 0})
    return bud.element_view(e, await _overrides(model_id, version))


# ── Geometria e ficheiros (acesso privado) ──────────────────────────────────
@router.get("/models/{model_id}/versions/{version}/geometry/{chunk}")
async def geometry_chunk(model_id: str, version: int, chunk: int, user=Depends(viewer)):
    v = await _version(model_id, version, user, done=True)
    keys = v.get("chunk_keys") or []
    if chunk < 0 or chunk >= len(keys):
        raise HTTPException(404, "Bloco de geometria inexistente.")
    data = await storage.get(keys[chunk])
    return Response(content=data, media_type="application/json",
                    headers={"Content-Encoding": "gzip", "Cache-Control": "private, max-age=3600"})


def _sign(payload: str) -> str:
    sig = hmac.new(config.url_secret().encode(), payload.encode(), hashlib.sha256).digest()
    return base64.urlsafe_b64encode(sig).decode().rstrip("=")


def make_token(tenant: str, model_id: str, version: int, ttl: int | None = None) -> str:
    exp = int(time.time()) + int(ttl or config.SIGNED_URL_TTL_S)
    payload = f"{tenant}|{model_id}|{version}|{exp}"
    return base64.urlsafe_b64encode(payload.encode()).decode().rstrip("=") + "." + _sign(payload)


def read_token(token: str) -> tuple[str, str, int]:
    try:
        p64, sig = token.split(".", 1)
        payload = base64.urlsafe_b64decode(p64 + "=" * (-len(p64) % 4)).decode()
        if not hmac.compare_digest(sig, _sign(payload)):
            raise ValueError
        tenant, model_id, version, exp = payload.split("|")
        if int(exp) < time.time():
            raise HTTPException(410, "Ligação expirada.")
        return tenant, model_id, int(version)
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(403, "Ligação inválida.")


@router.get("/models/{model_id}/versions/{version}/download-url")
async def download_url(model_id: str, version: int, user=Depends(viewer)):
    await _version(model_id, version, user)
    await audit(user, "download_url", model_id, version)
    return {"url": f"/api/bim/files/{make_token(tenant_of(user), model_id, version)}",
            "expires_in": config.SIGNED_URL_TTL_S}


@files_router.get("/files/{token}")
async def signed_file(token: str):
    _require_enabled()
    tenant, model_id, version = read_token(token)
    v = await get_db().bim_versions.find_one({"model_id": model_id, "version": version, "tenant_id": tenant},
                                             {"_id": 0})
    if not v:
        raise HTTPException(404, "Ficheiro não encontrado.")
    data = await storage.get(v["storage_key"])
    return Response(content=data, media_type="application/x-step", headers={
        "Content-Disposition": f'attachment; filename="{v["filename"]}"', "Cache-Control": "private, no-store"})


# ── Associação a artigos e orçamento ────────────────────────────────────────
async def _groups_and_mappings(model_id: str, version: int):
    els = await _elements(model_id, version)
    ov = await _overrides(model_id, version)
    groups = bud.build_groups(els, ov)
    maps = {m["group_key"]: m async for m in get_db().bim_mappings.find(
        {"model_id": model_id, "version": version}, {"_id": 0})}
    return groups, maps


@router.get("/models/{model_id}/versions/{version}/groups")
async def get_groups(model_id: str, version: int, user=Depends(viewer)):
    await _version(model_id, version, user, done=True)
    groups, maps = await _groups_and_mappings(model_id, version)
    for g in groups:
        g["mapping"] = maps.get(g["group_key"])
        g["gids_count"] = len(g["gids"])
        g["gids"] = g["gids"][:2000]
    return {"groups": groups}


@router.post("/models/{model_id}/versions/{version}/mappings/suggest")
async def suggest_mappings(model_id: str, version: int, user=Depends(editor)):
    await _version(model_id, version, user, done=True)
    groups, maps = await _groups_and_mappings(model_id, version)
    items = await _library(user)
    db = get_db()
    n = 0
    for g in groups:
        cur = maps.get(g["group_key"])
        if cur and cur.get("status") == "confirmed":
            continue
        cands = bud.suggest(g, items)
        doc = {"model_id": model_id, "version": version, "tenant_id": tenant_of(user), "group_key": g["group_key"],
               "candidates": cands, "suggested_at": now()}
        if cands:
            best = cands[0]
            doc.update({"status": "suggested", "item_id": best["item_id"], "score": best["score"],
                        "reason": best["reason"], "quantity_key": bud.unit_key(best.get("unit") or "")})
            n += 1
        else:
            doc.update({"status": "none", "item_id": None})
        await db.bim_mappings.update_one({"model_id": model_id, "version": version, "group_key": g["group_key"]},
                                         {"$set": doc, "$setOnInsert": {"mapping_id": "map_" + secrets.token_hex(6)}},
                                         upsert=True)
    await audit(user, "suggest_mappings", model_id, version, suggested=n)
    return {"suggested": n, "groups": len(groups)}


class MappingIn(BaseModel):
    group_key: str = Field(max_length=200)
    item_id: str | None = Field(default=None, max_length=60)
    quantity_key: str | None = None
    status: Literal["confirmed", "suggested", "none"] = "confirmed"
    excluded: bool = False


@router.put("/models/{model_id}/versions/{version}/mappings")
async def set_mapping(model_id: str, version: int, body: MappingIn, user=Depends(editor)):
    await _version(model_id, version, user, done=True)
    groups, _ = await _groups_and_mappings(model_id, version)
    group = next((g for g in groups if g["group_key"] == body.group_key), None)
    if not group:
        raise HTTPException(404, "Grupo de elementos não encontrado.")
    snapshot = None
    if body.item_id:
        ids = await _tenant_user_ids(user)
        item = await get_db().library_items.find_one({"item_id": body.item_id, "user_id": {"$in": ids}}, {"_id": 0})
        if not item:
            raise HTTPException(404, "Artigo não encontrado na biblioteca.")
        snapshot = {k: item.get(k) for k in ("designation", "unit", "unit_price_ht", "vat_rate")}
    elif body.status == "confirmed" and not body.excluded:
        raise HTTPException(422, "Escolha um artigo para confirmar a associação.")
    if body.quantity_key and body.quantity_key not in ("area", "volume", "length", "count", "weight"):
        raise HTTPException(422, "Quantidade inválida.")
    qkey = body.quantity_key or (bud.unit_key(snapshot["unit"]) if snapshot else None)
    if body.item_id and not qkey:
        raise HTTPException(422, f"A unidade do artigo ({snapshot['unit']}) não tem medição BIM correspondente; "
                                 "indique a quantidade a usar.")
    sel = {"model_id": model_id, "version": version, "group_key": body.group_key}
    await get_db().bim_mappings.update_one(sel, {"$set": {
        **sel, "tenant_id": tenant_of(user), "item_id": body.item_id, "item_snapshot": snapshot,
        "quantity_key": qkey, "status": body.status, "excluded": body.excluded,
        "by": user.get("name") or user["user_id"], "at": now()},
        "$setOnInsert": {"mapping_id": "map_" + secrets.token_hex(6)}}, upsert=True)
    await audit(user, "set_mapping", model_id, version, **body.model_dump())
    return await get_db().bim_mappings.find_one(sel, {"_id": 0})


async def _budget(model_id: str, version: int, user: dict) -> dict:
    groups, maps = await _groups_and_mappings(model_id, version)
    ids = await _tenant_user_ids(user)
    item_ids = [m["item_id"] for m in maps.values() if m.get("item_id")]
    items = {i["item_id"]: i async for i in get_db().library_items.find(
        {"item_id": {"$in": item_ids}, "user_id": {"$in": ids}}, {"_id": 0})}
    return bud.budget(groups, maps, items)


@router.get("/models/{model_id}/versions/{version}/budget")
async def get_budget(model_id: str, version: int, user=Depends(viewer)):
    await _version(model_id, version, user, done=True)
    b = await _budget(model_id, version, user)
    for line in b["lines"]:
        line.pop("gids", None)
    return b


class QuoteIn(BaseModel):
    client_id: str | None = Field(default=None, max_length=60)
    title: str = Field(default="", max_length=200)


@router.post("/models/{model_id}/versions/{version}/budget/quote")
async def create_quote(model_id: str, version: int, body: QuoteIn, user=Depends(editor)):
    """Cria um orçamento editável (coleção existente ``pro_documents``) a partir das associações confirmadas."""
    m = await _model(model_id, user)
    await _version(model_id, version, user, done=True)
    b = await _budget(model_id, version, user)
    if not b["lines"]:
        raise HTTPException(409, "Nenhuma associação confirmada: associe e confirme artigos antes de gerar o orçamento.")
    from routes.documents import _client_snapshot, _compute_totals
    lines: list[dict] = []
    traces = []
    for cat in dict.fromkeys(l["category"] for l in b["lines"]):
        lines.append({"line_id": "ln_" + secrets.token_hex(5), "kind": "section", "title": cat})
        for l in (x for x in b["lines"] if x["category"] == cat):
            lid = "ln_" + secrets.token_hex(5)
            storeys = "; ".join(f"{s}: {q:g}" for s, q in l["by_storey"].items())
            origin_txt = ", ".join(f"{bud.ORIGIN_LABELS.get(o, o).lower()} ×{n}" for o, n in l["origins"].items())
            lines.append({
                "line_id": lid, "kind": "line", "line_kind": "ouvrage", "designation": l["designation"],
                "description": (f"BIM: {l['bim_label']} — {l['elements']} elemento(s). "
                                f"Medição: {origin_txt or 'n/d'}." + (f" Por piso: {storeys}." if storeys else ""))[:900],
                "unit": l["unit"], "qty": l["qty"], "unit_price_ht": l["unit_price_ht"],
                "vat_rate": l["vat_rate"], "cost_price_ht": l["cost_price_ht"], "category": cat,
                "price_source": "bim_studio",
                "price_reference": l["mapping_id"], "price_reference_label": "Biblioteca da empresa",
                "price_missing": l["price_missing"], "quantity_missing": l["quantity_missing"],
                "price_estimated": l["confidence"] in ("estimada", "incompleta"),
            })
            traces.append({"line_id": lid, "mapping_id": l["mapping_id"], "group_key": l["group_key"],
                           "item_id": l["item_id"], "quantity_key": l["quantity_key"], "qty": l["qty"],
                           "origins": l["origins"], "confidence": l["confidence"], "gids": l["gids"]})
    doc_id = "doc_" + secrets.token_hex(6)
    doc = {
        "doc_id": doc_id, "user_id": user["user_id"], "doc_type": "quote", "number": None,
        "title": body.title or f"Orçamento BIM — {m['name']} (v{version})", "client_id": body.client_id,
        "client": await _client_snapshot(body.client_id, user), "status": "draft", "lines": lines,
        "notes": ("Quantidades extraídas do modelo BIM no ConstruPilot BIM Studio. "
                  "Verifique as medições assinaladas como estimadas ou incompletas antes de enviar."),
        "payment_terms": "", "deposit_pct": 0, "totals": _compute_totals(lines, 0), "issue_date": None,
        "due_date": None, "source": "bim_studio", "bim_model_id": model_id, "bim_version": version,
        "created_at": now(), "updated_at": now(),
    }
    db = get_db()
    await db.pro_documents.insert_one(dict(doc))
    await db.bim_quote_traces.insert_one({"doc_id": doc_id, "tenant_id": tenant_of(user), "model_id": model_id,
                                          "version": version, "lines": traces, "created_at": now()})
    await audit(user, "create_quote", model_id, version, doc_id=doc_id, total_ht=b["total_ht"])
    doc.pop("_id", None)
    return {"doc_id": doc_id, "totals": doc["totals"], "lines": len(lines), "warnings": b["warnings"]}


# ── Exportação (mapa de quantidades) ─────────────────────────────────────────
def _qmap_rows(groups: list[dict], b: dict) -> list[list]:
    lines = {l["group_key"]: l for l in b["lines"]}
    rows = []
    for g in groups:
        l = lines.get(g["group_key"])
        k = (l or {}).get("quantity_key") or g["primary_key"]
        rows.append([g["category_label"], g["label"], g.get("material") or "", g["included"],
                     QTY_LABELS.get(k, k), round(g["totals"].get(k, 0.0), 3), UNIT_OF.get(k, ""),
                     g["confidence"], g["missing"].get(k, 0),
                     (l or {}).get("designation") or "", (l or {}).get("unit_price_ht") or "",
                     (l or {}).get("total_ht") or ""])
    return rows


_QMAP_HEADER = ["Categoria", "Grupo BIM", "Material", "Elementos", "Medição", "Quantidade", "Unidade",
                "Fiabilidade", "Elementos sem medição", "Artigo", "Preço unit. s/IVA", "Total s/IVA"]


@router.get("/models/{model_id}/versions/{version}/export.{fmt}")
async def export_qmap(model_id: str, version: int, fmt: Literal["csv", "xlsx"], user=Depends(viewer)):
    m = await _model(model_id, user)
    await _version(model_id, version, user, done=True)
    groups, _ = await _groups_and_mappings(model_id, version)
    b = await _budget(model_id, version, user)
    rows = _qmap_rows(groups, b)
    base = re.sub(r"[^A-Za-z0-9_-]+", "_", m["name"])[:60] or "modelo"
    await audit(user, "export", model_id, version, fmt=fmt)
    if fmt == "csv":
        buf = io.StringIO()
        w = csv.writer(buf, delimiter=";")
        w.writerow(_QMAP_HEADER)
        w.writerows(rows)
        return Response(content=("﻿" + buf.getvalue()).encode("utf-8"), media_type="text/csv; charset=utf-8",
                        headers={"Content-Disposition": f'attachment; filename="Mapa_quantidades_{base}_v{version}.csv"'})
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill
    wb = Workbook()
    ws = wb.active
    ws.title = "Mapa de quantidades"
    ws.append(_QMAP_HEADER)
    for c in ws[1]:
        c.font = Font(bold=True, color="FFFFFF")
        c.fill = PatternFill("solid", fgColor="1F5E4B")
    for r in rows:
        ws.append(r)
    ws.append([])
    ws.append(["", "", "", "", "", "", "", "", "", "Total s/IVA", "", b["total_ht"]])
    for col, width in zip("ABCDEFGHIJKL", (22, 30, 22, 10, 14, 12, 8, 12, 12, 40, 14, 14)):
        ws.column_dimensions[col].width = width
    ws2 = wb.create_sheet("Subtotais")
    ws2.append(["Por categoria", "Total s/IVA"])
    for k, v in b["subtotals_by_category"].items():
        ws2.append([k, v])
    ws2.append([])
    ws2.append(["Por piso", "Total s/IVA"])
    for k, v in b["subtotals_by_storey"].items():
        ws2.append([k, v])
    out = io.BytesIO()
    wb.save(out)
    return Response(content=out.getvalue(),
                    media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": f'attachment; filename="Mapa_quantidades_{base}_v{version}.xlsx"'})


# ── Comparação de versões e auditoria ───────────────────────────────────────
@router.get("/models/{model_id}/compare")
async def compare_versions(model_id: str, a: int, b: int, user=Depends(viewer)):
    await _version(model_id, a, user, done=True)
    await _version(model_id, b, user, done=True)
    proj = {"_id": 0, "gid": 1, "name": 1, "category": 1, "storey": 1, "ifc_class": 1, "quantities": 1}
    res = bud.compare(await _elements(model_id, a, proj), await _elements(model_id, b, proj))
    for k in ("added", "removed", "changed"):
        res[k] = res[k][:500]
    return res


@router.get("/models/{model_id}/audit")
async def model_audit(model_id: str, user=Depends(viewer)):
    await _model(model_id, user)
    rows = await get_db().bim_audit.find({"model_id": model_id, "tenant_id": tenant_of(user)},
                                         {"_id": 0}).sort("at", -1).to_list(200)
    return {"items": rows}


# ── Arranque / paragem (chamados pelo server.py) ────────────────────────────
async def on_startup():
    """Não bloqueia o arranque (readiness do deploy): índices e workers em segundo plano."""
    if not config.enabled():
        return
    import asyncio
    import logging

    async def _boot():
        from bim_studio.store import ensure_indexes
        try:
            await ensure_indexes()
        except Exception:  # noqa: BLE001
            logging.getLogger("bim_studio").exception("BIM índices")
        try:
            await jobs.start()
        except Exception:  # noqa: BLE001
            logging.getLogger("bim_studio").exception("BIM workers")

    global _BOOT_TASK
    _BOOT_TASK = asyncio.create_task(_boot())


_BOOT_TASK = None


async def on_shutdown():
    await jobs.stop()
