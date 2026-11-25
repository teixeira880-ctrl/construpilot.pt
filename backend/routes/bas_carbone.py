"""Obra › Baixo carbono : Carta de Obra de Baixo Carbono do processo de obra.

As empresas depositam DAP, fichas técnicas, guias de remessa, e-GAR e faturas de gasóleo : o quadro preenche-se
automaticamente e cada resultado é cruzado com os imperativos da obra (controlos). Exportação Excel e PDF.
"""
from __future__ import annotations

import copy
import logging
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, Field

from core.db import db
from core.security import current_user, pro_required
from core.uploads import ALLOWED_DOCUMENT, ALLOWED_IMAGE, validate_upload
from engines.bas_carbone import calculer, documents as D, import_xlsx, nouveau_dossier, referentiel as R
from engines.bas_carbone.calcul import ligne_materiau

log = logging.getLogger("bas_carbone")
router = APIRouter(prefix="/chantiers", tags=["bas-carbone"], dependencies=[Depends(pro_required)])
MAX_FILES = 25
MAT_EDIT = {"lot", "famille", "solution", "typologie", "unite", "quantite_prevue", "quantite_livree", "fe_ref", "fe_fdes", "ref_fdes",
            "fdes_unite", "fdes_validite", "distance_km", "note", "code"}


_XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
_EXT = {".pdf": "application/pdf", ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp",
        ".heic": "image/heic", ".txt": "text/plain", ".xlsx": _XLSX}


async def read_upload(f: UploadFile, kind: str = "doc_image", max_mb: int = 40) -> bytes:
    """Validação do upload (lista branca de tipos + tamanho) com o validador comum da plataforma ; devolve os bytes."""
    allowed = [_XLSX] if kind == "spreadsheet" else ALLOWED_DOCUMENT + ALLOWED_IMAGE + ["text/plain"]
    ext = ("." + (f.filename or "").rsplit(".", 1)[-1].lower()) if "." in (f.filename or "") else ""
    ctype = (f.content_type or "").lower()
    over = _EXT.get(ext) if ctype in ("", "application/octet-stream") or ctype not in allowed else None
    if over and over not in allowed:
        over = None
    await validate_upload(f, allowed, max_mb, override_content_type=over)
    data = await f.read()
    if ext == ".pdf" and not data.startswith(b"%PDF"):
        raise HTTPException(400, "PDF inválido")
    return data


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


async def _chantier(cid: str, uid: str) -> dict:
    c = await db.chantiers.find_one({"chantier_id": cid, "user_id": uid}, {"_id": 0})
    if not c:
        raise HTTPException(404, "Obra não encontrada")
    return c


async def _load(cid: str, uid: str) -> tuple[dict, dict]:
    c = await _chantier(cid, uid)
    doc = await db.bas_carbone.find_one({"chantier_id": cid, "user_id": uid}, {"_id": 0})
    if doc and doc.get("dossier"):
        return c, doc["dossier"]
    adr = " ".join(x for x in (c.get("address"), c.get("postal_code"), c.get("city")) if x)
    return c, nouveau_dossier(c.get("name") or "", adresse=adr)


async def _save(cid: str, uid: str, dossier: dict) -> dict:
    await db.bas_carbone.update_one({"chantier_id": cid, "user_id": uid},
                                    {"$set": {"chantier_id": cid, "user_id": uid, "dossier": dossier, "updated_at": _now()}}, upsert=True)
    return calculer(dossier)


def _out(dossier: dict, res: dict, extra: dict | None = None) -> dict:
    return {"dossier": dossier, "resultats": res, "referentiel": {"lots": R.LOTS, "typologies": list(R.TYPOLOGIES), "jalons": list(R.JALONS),
            "typologies_materiau": R.TYPOLOGIES_MATERIAU, "statuts": R.STATUTS,
            "familles": [{"code": f["code"], "famille": f["famille"], "lot": f["lot"], "unite": f["unite"]} for f in R.FAMILLES]},
            **(extra or {})}


@router.get("/{chantier_id}/bas-carbone")
async def get_bas_carbone(chantier_id: str, user=Depends(current_user)) -> dict:
    _, d = await _load(chantier_id, user["user_id"])
    return _out(d, calculer(d))


class ProjetIn(BaseModel):
    nom: Optional[str] = Field(None, max_length=160)
    adresse: Optional[str] = Field(None, max_length=240)
    typologie: Optional[str] = None
    sref_m2: Optional[float] = Field(None, ge=0, le=1e7)
    jalon: Optional[str] = None
    seuil_ic: Optional[float] = Field(None, ge=0, le=1e5)


class MajIn(BaseModel):
    projet: Optional[ProjetIn] = None
    materiaux: Optional[list[dict[str, Any]]] = Field(None, max_length=300)
    emissions: Optional[dict[str, float]] = None          # {id: quantité}
    charte: Optional[dict[str, dict[str, Any]]] = None    # {id: {realise, statut_force, commentaire, cible}}
    dechets: Optional[dict[str, Optional[float]]] = None


@router.put("/{chantier_id}/bas-carbone")
async def update_bas_carbone(chantier_id: str, body: MajIn, user=Depends(current_user)) -> dict:
    _, d = await _load(chantier_id, user["user_id"])
    if body.projet:
        p = body.projet.model_dump(exclude_unset=True)
        if p.get("typologie") and p["typologie"] not in R.TYPOLOGIES:
            raise HTTPException(422, "Tipologia desconhecida")
        if p.get("jalon") and p["jalon"] not in R.JALONS:
            raise HTTPException(422, "Enquadramento desconhecido")
        d["projet"].update(p)
    if body.materiaux is not None:
        old = {m["id"]: m for m in d["materiaux"]}
        new = []
        for m in body.materiaux:
            base = old.get(m.get("id")) or ligne_materiau(m.get("code") if m.get("code") in R.FAMILLE else None, origine="saisie")
            for k, v in m.items():
                if k in MAT_EDIT:
                    base[k] = v
            if base.get("lot") not in R.LOTS:
                raise HTTPException(422, f"Capítulo desconhecido : {base.get('lot')}")
            if base.get("typologie") not in R.TYPOLOGIES_MATERIAU:
                raise HTTPException(422, f"Tipologia de material desconhecida : {base.get('typologie')}")
            new.append(base)
        d["materiaux"] = new
    if body.emissions:
        for e in d["emissions"]:
            if e["id"] in body.emissions and body.emissions[e["id"]] is not None:
                e["quantite"] = max(0.0, float(body.emissions[e["id"]]))
    if body.charte:
        for c in d["charte"]:
            u = body.charte.get(c["id"])
            if not u:
                continue
            if "realise" in u:
                c["realise"] = u["realise"] if u["realise"] in (None, "") or isinstance(u["realise"], (int, float)) else None
            if "statut_force" in u:
                if u["statut_force"] not in (None, "", *R.STATUTS):
                    raise HTTPException(422, "Estado desconhecido")
                c["statut_force"] = u["statut_force"] or None
            if "commentaire" in u:
                c["commentaire"] = str(u["commentaire"] or "")[:500]
            if isinstance(u.get("cible"), (int, float)):
                c["cible"] = u["cible"]
    if body.dechets is not None:
        d["dechets"].update({k: v for k, v in body.dechets.items() if k in ("total_t", "valorise_t")})
    return _out(d, await _save(chantier_id, user["user_id"], d))


@router.post("/{chantier_id}/bas-carbone/documents")
async def upload_documents(chantier_id: str, files: list[UploadFile] = File(...), user=Depends(current_user)) -> dict:
    """Depósito de documentos : leitura (regras + IA verificada), registo no quadro, distâncias, controlos."""
    if len(files) > MAX_FILES:
        raise HTTPException(413, f"Máximo de {MAX_FILES} ficheiros por envio")
    c, d = await _load(chantier_id, user["user_id"])
    lus = []
    for f in files:
        data = await read_upload(f, kind="doc_image", max_mb=40)
        doc = await D.lire(data, f.filename or "documento")
        dec = D.appliquer(d, doc) if doc.get("statut") != "ilegivel" else []
        if doc.get("statut") == "ilegivel":
            rec = {k: doc.get(k) for k in ("doc_id", "nom", "type", "type_libelle", "statut", "pages", "taille", "notes")}
            d["documents"] = [x for x in d["documents"] if x.get("doc_id") != doc["doc_id"]] + [dict(rec, extrait={}, rattache_a=None, apports=[])]
        lus.append({"doc_id": doc["doc_id"], "nom": doc["nom"], "type": doc.get("type_libelle"), "statut": doc.get("statut"),
                    "decisions": dec, "notes": doc.get("notes") or []})
    try:
        adr = d["projet"].get("adresse") or " ".join(x for x in (c.get("address"), c.get("postal_code"), c.get("city")) if x)
        await D.completer_distances(d, adr)
    except Exception:  # noqa: BLE001 — le géocodage ne bloque jamais le dépôt
        log.warning("bas carbone: distances non calculées", exc_info=True)
    return _out(d, await _save(chantier_id, user["user_id"], d), {"lus": lus})


class RattacherIn(BaseModel):
    ligne_id: str = Field(..., min_length=3, max_length=60)


@router.post("/{chantier_id}/bas-carbone/documents/{doc_id}/rattacher")
async def attach_document(chantier_id: str, doc_id: str, body: RattacherIn, user=Depends(current_user)) -> dict:
    _, d = await _load(chantier_id, user["user_id"])
    rec = next((x for x in d["documents"] if x.get("doc_id") == doc_id), None)
    if rec is None:
        raise HTTPException(404, "Documento não encontrado")
    if not any(m["id"] == body.ligne_id for m in d["materiaux"]):
        raise HTTPException(404, "Linha não encontrada")
    D.retirer(d, doc_id)
    doc = {k: rec.get(k) for k in ("doc_id", "nom", "type", "type_libelle", "statut", "pages", "taille", "notes")}
    doc["extrait"] = rec.get("extrait") or {}
    D.appliquer(d, doc, body.ligne_id)
    return _out(d, await _save(chantier_id, user["user_id"], d))


@router.delete("/{chantier_id}/bas-carbone/documents/{doc_id}")
async def delete_document(chantier_id: str, doc_id: str, user=Depends(current_user)) -> dict:
    _, d = await _load(chantier_id, user["user_id"])
    if not D.retirer(d, doc_id):
        raise HTTPException(404, "Documento não encontrado")
    return _out(d, await _save(chantier_id, user["user_id"], d))


@router.get("/{chantier_id}/bas-carbone/etudes")
async def list_studies(chantier_id: str, user=Depends(current_user)) -> list[dict]:
    await _chantier(chantier_id, user["user_id"])
    cur = db.bas_carbone_etudes.find({"user_id": user["user_id"]}, {"_id": 0, "job_id": 1, "nom": 1, "created_at": 1}).sort("created_at", -1).limit(30)
    return [x async for x in cur]


class EtudeIn(BaseModel):
    job_id: str = Field(..., min_length=3, max_length=80)


@router.post("/{chantier_id}/bas-carbone/importer-etude")
async def import_study(chantier_id: str, body: EtudeIn, user=Depends(current_user)) -> dict:
    """Retoma as quantidades da medição de um estudo completo ; os documentos já depositados são reaplicados."""
    _, d = await _load(chantier_id, user["user_id"])
    e = await db.bas_carbone_etudes.find_one({"user_id": user["user_id"], "job_id": body.job_id}, {"_id": 0})
    if not e:
        raise HTTPException(404, "Estudo não encontrado")
    anciens = copy.deepcopy(d.get("documents") or [])
    src = e["dossier"]
    d["materiaux"] = copy.deepcopy(src.get("materiaux") or [])
    for k in ("typologie", "sref_m2", "jalon"):
        if src.get("projet", {}).get(k):
            d["projet"][k] = src["projet"][k]
    d["decisions"] = list(dict.fromkeys((d.get("decisions") or []) + (src.get("decisions") or [])))
    D.reappliquer(d, anciens)
    return _out(d, await _save(chantier_id, user["user_id"], d))


@router.post("/{chantier_id}/bas-carbone/importer-excel")
async def import_excel(chantier_id: str, file: UploadFile = File(...), user=Depends(current_user)) -> dict:
    """Quadro já preenchido (modelo Charte v3 ou exportação ConstruPilot)."""
    data = await read_upload(file, kind="spreadsheet", max_mb=15)
    _, d = await _load(chantier_id, user["user_id"])
    anciens = copy.deepcopy(d.get("documents") or [])
    try:
        dec = import_xlsx.importer(d, data)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(422, f"Livro Excel ilegível ({type(exc).__name__})")
    if not dec:
        raise HTTPException(422, "Nenhum separador da carta reconhecido (Materiais, Emissoes_Obra, Grelha_Carta ou o modelo francês)")
    D.reappliquer(d, anciens)
    return _out(d, await _save(chantier_id, user["user_id"], d), {"import": dec})


@router.post("/{chantier_id}/bas-carbone/reinitialiser")
async def reset(chantier_id: str, user=Depends(current_user)) -> dict:
    c = await _chantier(chantier_id, user["user_id"])
    adr = " ".join(x for x in (c.get("address"), c.get("postal_code"), c.get("city")) if x)
    d = nouveau_dossier(c.get("name") or "", adresse=adr)
    return _out(d, await _save(chantier_id, user["user_id"], d))


async def _branding(user):
    try:
        from engines.bet_core.assistant_tool import _default_branding
        return await _default_branding(db, user["user_id"], user)
    except Exception:  # noqa: BLE001
        return None


@router.get("/{chantier_id}/bas-carbone/export.{fmt}")
async def export(chantier_id: str, fmt: str, user=Depends(current_user)) -> Response:
    if fmt not in ("xlsx", "pdf"):
        raise HTTPException(404, "Formato desconhecido")
    c, d = await _load(chantier_id, user["user_id"])
    res = calculer(d)
    b = await _branding(user)
    ent = str((b or {}).get("company_name") or "")
    from engines.nom_fichier import disposition, nom_document
    name = nom_document("Carta-baixo-carbono", c.get("name") or d["projet"].get("nom"), ext=fmt)
    if fmt == "xlsx":
        from engines.bas_carbone import export_xlsx
        data = export_xlsx.construire(res, ent)
        mime = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    else:
        import asyncio
        from engines.bas_carbone import export_pdf
        data = await asyncio.to_thread(export_pdf.construire, res, b, ent)
        mime = "application/pdf"
    return Response(content=data, media_type=mime, headers=disposition(name))
