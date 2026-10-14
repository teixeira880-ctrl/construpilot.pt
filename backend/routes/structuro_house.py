"""API do estudo estrutural de moradia (pré-dimensionamento): cálculo JSON e dossier PDF."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import Response
from pydantic import BaseModel

from engines.access import require_level
from engines import structuro_house as H
from engines.structuro_house_pdf import build_pdf

router = APIRouter(prefix="/structuro/house", tags=["structuro-house"],
                   dependencies=[Depends(require_level("pro"))])


class HouseIn(BaseModel):
    geometry: dict


@router.get("/defaults")
async def defaults() -> dict:
    return {"geometry": H.normalize({}), "uses": list(H.USE_Q.keys()), "version": H.VERSION}


@router.post("/compute")
async def compute(body: HouseIn) -> dict:
    try:
        return await run_in_threadpool(H.compute, body.geometry)
    except (ValueError, TypeError) as e:
        raise HTTPException(422, f"Geometria inválida: {e}") from None


@router.post("/pdf")
async def pdf(body: HouseIn):
    try:
        r = await run_in_threadpool(H.compute, body.geometry)
    except (ValueError, TypeError) as e:
        raise HTTPException(422, f"Geometria inválida: {e}") from None
    data = await run_in_threadpool(build_pdf, r, r["geometry"].get("name") or "Moradia")
    return Response(content=data, media_type="application/pdf",
                    headers={"Content-Disposition": 'inline; filename="dossier-estrutural.pdf"'})
