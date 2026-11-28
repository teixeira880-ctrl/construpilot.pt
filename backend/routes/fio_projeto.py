"""Fio do projeto — API.

GET    /api/fio-projeto/{pid}                    estado: projeto (medições exatas), ligações, imagens, etapas
POST   /api/fio-projeto/{pid}/ligar              liga um resultado (BIM, térmica, execução, orçamento, DCE, conversa)
POST   /api/fio-projeto/{pid}/imagens            junta uma imagem 3D / render / foto (PNG, JPEG, WebP ≤ 6 MB)
GET    /api/fio-projeto/{pid}/imagens/{iid}      a imagem
DELETE /api/fio-projeto/{pid}/imagens/{iid}
GET    /api/fio-projeto/{pid}/dossier.pdf        dossier final (seguimento, áreas, envolvente, vãos, imagens, peças desenhadas)
"""
from __future__ import annotations

import base64

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, Field

from engines.fio_projeto import servico as S
from routes.atelier_archi import current_user, db   # mesma base e mesma autenticação que o Ateliê

router = APIRouter(prefix="/fio-projeto", tags=["fio-projeto"])


class LigarIn(BaseModel):
    campo: str = Field(min_length=1, max_length=40)
    valor: str = Field(min_length=1, max_length=120)
    nota: str = Field(default="", max_length=300)


class ImagemB64In(BaseModel):
    image_b64: str = Field(min_length=20, max_length=9_000_000)
    tipo: str = Field(default="outra", max_length=20)
    legenda: str = Field(default="", max_length=200)


def _erro(e: S.ErroFio) -> HTTPException:
    return HTTPException(e.status, e.msg)


@router.get("/{pid}")
async def ver(pid: str, user=Depends(current_user)) -> dict:
    try:
        return await S.estado(db, user, pid)
    except S.ErroFio as e:
        raise _erro(e)


@router.post("/{pid}/ligar")
async def ligar(pid: str, body: LigarIn, user=Depends(current_user)) -> dict:
    try:
        return {"ok": True, "ligacao": await S.ligar(db, user, pid, body.campo, body.valor, body.nota)}
    except S.ErroFio as e:
        raise _erro(e)


@router.post("/{pid}/imagens")
async def juntar_imagem(pid: str, file: UploadFile = File(...), tipo: str = Form("outra"), legenda: str = Form(""),
                        user=Depends(current_user)) -> dict:
    data = await file.read(S.MAX_BYTES + 1)
    try:
        return {"ok": True, "imagem": await S.adicionar_imagem(db, user, pid, data, tipo, legenda)}
    except S.ErroFio as e:
        raise _erro(e)


@router.post("/{pid}/imagens/b64")
async def juntar_imagem_b64(pid: str, body: ImagemB64In, user=Depends(current_user)) -> dict:
    """Para os renders e as vistas 3D que o navegador já tem em memória (data URL)."""
    try:
        data = base64.b64decode(body.image_b64.split(",", 1)[-1], validate=False)
    except Exception:  # noqa: BLE001
        raise HTTPException(415, S.t("img_tipo"))
    try:
        return {"ok": True, "imagem": await S.adicionar_imagem(db, user, pid, data, body.tipo, body.legenda)}
    except S.ErroFio as e:
        raise _erro(e)


@router.get("/{pid}/imagens/{iid}")
async def imagem(pid: str, iid: str, user=Depends(current_user)):
    try:
        d = await S.ler_imagem(db, user, pid, iid)
    except S.ErroFio as e:
        raise _erro(e)
    return Response(content=bytes(d["data"]), media_type=d.get("mime") or "image/png",
                    headers={"Cache-Control": "private, max-age=3600"})


@router.delete("/{pid}/imagens/{iid}")
async def apagar_imagem(pid: str, iid: str, user=Depends(current_user)) -> dict:
    try:
        return {"ok": await S.apagar_imagem(db, user, pid, iid)}
    except S.ErroFio as e:
        raise _erro(e)


@router.get("/{pid}/dossier.pdf")
async def dossier(pid: str, user=Depends(current_user)):
    try:
        pdf, est = await S.dossier(db, user, pid)
    except S.ErroFio as e:
        raise _erro(e)
    nome = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in (est["projeto"].get("titulo") or pid))[:60]
    return Response(content=pdf, media_type="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="Dossier-{nome}.pdf"'})
