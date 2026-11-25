"""Redator de Caderno de Encargos / processo de concurso (espaço Pro) — ConstruPilot Portugal.

- GET  /pro/cctp/catalogue                  → capítulos, documentos de referência e artigos tipo
- POST /pro/cctp/dossiers                   → lança a redação (tarefa em segundo plano), devolve dossier_id
- GET  /pro/cctp/dossiers                   → histórico
- GET  /pro/cctp/dossiers/{id}              → estado, capítulos redigidos, pontos a verificar, ficheiros
- GET  /pro/cctp/dossiers/{id}/fichiers/{i} → um ficheiro (caderno .docx, mapa de quantidades .xlsx, nota)
- GET  /pro/cctp/dossiers/{id}/zip          → processo de concurso completo (.zip)

Seleção possível a partir de um orçamento ConstruPilot (doc_id) : as linhas são ligadas aos capítulos e aos artigos
tipo, com as quantidades, e completadas pelos capítulos / artigos escolhidos e pelas linhas introduzidas.
(Mesmos caminhos de API que o construpilot.fr, para manter a paridade de código.)
"""
from __future__ import annotations

import asyncio
import base64
import logging
import secrets
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field

from core.db import db
from core.security import current_user
from engines import cctp_redacteur as R
from engines.access import require_level
from engines.nom_fichier import content_disposition

router = APIRouter(prefix="/pro/cctp", tags=["cctp"], dependencies=[Depends(require_level("pro"))])
logger = logging.getLogger(__name__)
_TASKS: set = set()


class Piece(BaseModel):
    nom: str = Field(min_length=1, max_length=80)
    type: str = Field(default="", max_length=20)
    surface: float | None = Field(default=None, ge=0, le=5000)
    niveau: str = Field(default="", max_length=20)
    extras: list[str] = Field(default_factory=list, max_length=20)


class Intervenants(BaseModel):
    architecte: str = Field(default="", max_length=200)
    bet_structure: str = Field(default="", max_length=200)
    bet_fluides: str = Field(default="", max_length=200)
    bet_thermique: str = Field(default="", max_length=200)
    coordonnateur_sps: str = Field(default="", max_length=200)
    controleur_technique: str = Field(default="", max_length=200)


class Consultation(BaseModel):
    date_limite: str = Field(default="", max_length=60)
    remise: str = Field(default="", max_length=200)
    visite: str = Field(default="", max_length=500)
    validite_jours: int = Field(default=90, ge=30, le=365)
    variantes: bool = True


class Projet(BaseModel):
    nom: str = Field(min_length=1, max_length=160)
    adresse: str = Field(default="", max_length=300)
    maitre_ouvrage: str = Field(default="", max_length=200)
    maitre_oeuvre: str = Field(default="", max_length=200)
    nature: str = Field(default="neuf", pattern="^(neuf|renovation)$")
    description: str = Field(default="", max_length=4000)
    phase: str = Field(default="Concurso", max_length=30)
    indice: str = Field(default="A", max_length=10)
    style: str = Field(default="economiste", pattern="^(economiste|architecte)$")
    intervenants: Intervenants = Field(default_factory=Intervenants)
    pieces: list[Piece] = Field(default_factory=list, max_length=60)
    plans: list[str] = Field(default_factory=list, max_length=120)
    tce: bool = True                       # peças do concurso : capa e índice, programa de concurso, cláusulas gerais
    par_lots: bool = False                 # False = caderno único (empreitada geral) ; True = um caderno por capítulo / lote
    delai: str = Field(default="", max_length=120)
    consultation: Consultation = Field(default_factory=Consultation)


class Ligne(BaseModel):
    designation: str = Field(min_length=1, max_length=200)
    unite: str = Field(default="u", max_length=10)
    quantite: float | None = None
    localisation: str = Field(default="", max_length=300)
    detail: str = Field(default="", max_length=1000)


class LotSel(BaseModel):
    code: str = Field(max_length=40)
    numero: int | None = Field(default=None, ge=1, le=99)
    titre: str = Field(default="", max_length=120)           # título personalizado (ex. « Acabamentos interiores »)
    inclure: list[str] = Field(default_factory=list, max_length=12)   # capítulos do catálogo agrupados neste
    ouvrages: list[str] = Field(default_factory=list, max_length=40)
    lignes: list[Ligne] = Field(default_factory=list, max_length=200)
    notes: str = Field(default="", max_length=2000)


class DossierIn(BaseModel):
    projet: Projet
    lots: list[LotSel] = Field(default_factory=list, max_length=20)
    doc_id: str | None = Field(default=None, max_length=80)
    ia: bool = True


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


async def _branding(user_id: str) -> dict | None:
    from routes.plans_common import _resolve_branding
    try:
        return await _resolve_branding(user_id)
    except Exception:  # noqa: BLE001 — o processo é gerado sem logótipo
        return None


@router.get("/catalogue")
async def catalogue() -> dict:
    return {"lots": R.catalogue_public()}


async def _run(dossier_id: str, user_id: str, projet: dict, selection: list[dict], ia: bool) -> None:
    try:
        lots = await R.rediger(projet, selection, ia=ia)
        if not lots:
            raise ValueError("Nenhum capítulo reconhecido na seleção.")
        fichiers = R.fichiers_dossier(projet, lots, await _branding(user_id))
        await db.cctp_dossiers.update_one({"dossier_id": dossier_id}, {"$set": {
            "status": "done", "finished_at": _now(),
            "lots": [{"numero": l["numero"], "titre": l["titre"], "code": l["code"], "mode": l["mode"],
                      "articles": len(l["articles"]), "lignes": sum(len(a["variantes"]) for a in l["articles"]),
                      "points": l["points"]} for l in lots],
            "fichiers": [{"nom": n, "mime": m, "taille": len(d), "data_b64": base64.b64encode(d).decode()} for n, d, m in fichiers],
        }})
    except Exception as exc:  # noqa: BLE001
        logger.exception("caderno: falha do processo %s", dossier_id)
        await db.cctp_dossiers.update_one({"dossier_id": dossier_id},
                                          {"$set": {"status": "error", "error": str(exc)[:300], "finished_at": _now()}})


@router.post("/dossiers")
async def creer(body: DossierIn, user=Depends(current_user)) -> dict:
    selection: list[dict] = []
    if body.doc_id:
        doc = await db.pro_documents.find_one({"doc_id": body.doc_id, "user_id": user["user_id"]}, {"_id": 0, "lines": 1})
        if not doc:
            raise HTTPException(404, "Orçamento não encontrado")
        selection += R.selection_depuis_devis(doc.get("lines") or [])
    for l in body.lots:
        for c in [l.code, *l.inclure]:
            if c not in R.LOTS_PAR_CODE:
                raise HTTPException(400, f"Capítulo desconhecido : {c}")
        selection.append(l.model_dump())
    if not selection:
        raise HTTPException(400, "Escolha pelo menos um capítulo ou um orçamento.")
    dossier_id = "cctp_" + secrets.token_hex(6)
    projet = body.projet.model_dump()
    await db.cctp_dossiers.insert_one({"dossier_id": dossier_id, "user_id": user["user_id"], "projet": projet,
                                       "doc_id": body.doc_id, "ia": body.ia, "status": "running", "created_at": _now()})
    t = asyncio.create_task(_run(dossier_id, user["user_id"], projet, selection, body.ia))
    _TASKS.add(t)
    t.add_done_callback(_TASKS.discard)
    return {"dossier_id": dossier_id, "status": "running"}


def _public(d: dict) -> dict:
    d = {k: v for k, v in d.items() if k not in ("_id", "user_id")}
    d["fichiers"] = [{"index": i, "nom": f["nom"], "mime": f["mime"], "taille": f["taille"]}
                     for i, f in enumerate(d.get("fichiers") or [])]
    return d


async def _get(dossier_id: str, user: dict, with_files: bool = False) -> dict:
    proj = {"_id": 0} if with_files else {"_id": 0, "fichiers.data_b64": 0}
    d = await db.cctp_dossiers.find_one({"dossier_id": dossier_id, "user_id": user["user_id"]}, proj)
    if not d:
        raise HTTPException(404, "Processo não encontrado")
    return d


@router.get("/dossiers")
async def lister(user=Depends(current_user)) -> dict:
    rows = await db.cctp_dossiers.find({"user_id": user["user_id"]}, {"_id": 0, "fichiers.data_b64": 0}).sort(
        "created_at", -1).to_list(50)
    return {"dossiers": [_public(r) for r in rows]}


@router.get("/dossiers/{dossier_id}")
async def lire(dossier_id: str, user=Depends(current_user)) -> dict:
    return _public(await _get(dossier_id, user))


@router.get("/dossiers/{dossier_id}/fichiers/{index}")
async def fichier(dossier_id: str, index: int, user=Depends(current_user)) -> Response:
    d = await _get(dossier_id, user, with_files=True)
    files = d.get("fichiers") or []
    if not 0 <= index < len(files):
        raise HTTPException(404, "Ficheiro não encontrado")
    f = files[index]
    return Response(base64.b64decode(f["data_b64"]), media_type=f["mime"],
                    headers={"Content-Disposition": content_disposition(f["nom"])})


@router.get("/dossiers/{dossier_id}/zip")
async def zip_complet(dossier_id: str, user=Depends(current_user)) -> Response:
    d = await _get(dossier_id, user, with_files=True)
    if d.get("status") != "done":
        raise HTTPException(409, "Processo em redação")
    files = [(f["nom"], base64.b64decode(f["data_b64"]), f["mime"]) for f in d.get("fichiers") or []]
    data = R.zip_dossier(d["projet"], files)
    return Response(data, media_type="application/zip",
                    headers={"Content-Disposition": content_disposition(f"Concurso_{R._slug(d['projet'].get('nom') or 'Projeto')}.zip")})
