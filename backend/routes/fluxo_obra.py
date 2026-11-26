"""Fluxo de obra entre apps: o percurso de um processo através de todas as apps.

Cada vez que um trabalho de um processo de obra é aberto ou produzido numa app
(Ateliê Arquiteto, BIM, medições, orçamento, estudos, PIC, renders…), o frontend
regista aqui um « passo » (app + rota + identificador do trabalho). O processo
guarda assim o fio completo do trabalho: qualquer app seguinte, o Assistente BTP
e a Aurora sabem de onde vem o trabalho e podem reabri-lo sem perder nada.

Regras:
- só rotas internas da plataforma (nunca um URL externo);
- um passo por (app, trabalho): reabrir o mesmo trabalho só atualiza a data;
- isolamento por conta: um utilizador só vê e escreve nos seus processos.
"""
import re
import secrets
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator

from core.db import db
from core.security import current_user, pro_required

router = APIRouter(prefix="/chantiers", tags=["fluxo-obra"], dependencies=[Depends(pro_required)])

MAX_PASSOS = 300
_ROTA = re.compile(r"^/[A-Za-z0-9_\-/]{0,120}$")
_PARAM_KEY = re.compile(r"^[A-Za-z0-9_\-]{1,40}$")
# Parâmetros de navegação que não identificam um trabalho.
_IGNORAR = {"chantier", "tab", "lang", "utm_source", "utm_medium", "utm_campaign", "from", "origem"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class PassoIn(BaseModel):
    rota: str = Field(..., min_length=1, max_length=140)
    params: dict[str, str] = Field(default_factory=dict)
    app: str = Field("", max_length=80)
    titulo: str = Field("", max_length=200)
    resumo: str = Field("", max_length=1000)

    @field_validator("rota")
    @classmethod
    def _rota_interna(cls, v: str) -> str:
        v = v.split("?")[0].split("#")[0].rstrip("/") or "/"
        if "//" in v or ".." in v or not _ROTA.match(v):
            raise ValueError("rota inválida")
        return v

    @field_validator("params")
    @classmethod
    def _params_limpos(cls, v: dict) -> dict:
        out = {}
        for k, val in (v or {}).items():
            if k in _IGNORAR or not _PARAM_KEY.match(str(k)):
                continue
            s = str(val)[:120]
            if s:
                out[k] = s
            if len(out) >= 8:
                break
        return out


async def _processo(chantier_id: str, user_id: str) -> dict:
    c = await db.chantiers.find_one({"chantier_id": chantier_id, "user_id": user_id}, {"_id": 0, "chantier_id": 1, "name": 1})
    if not c:
        raise HTTPException(404, "Processo de obra não encontrado")
    return c


def _chave(rota: str, params: dict) -> str:
    return rota + "?" + "&".join(f"{k}={params[k]}" for k in sorted(params))


def url_do_passo(p: dict) -> str:
    """URL para reabrir o trabalho dentro do processo (o processo segue sempre no URL)."""
    qs = "&".join(f"{k}={v}" for k, v in sorted((p.get("params") or {}).items()))
    base = f"{p['rota']}?chantier={p['chantier_id']}"
    return f"{base}&{qs}" if qs else base


@router.get("/{chantier_id}/percurso")
async def listar_percurso(chantier_id: str, user=Depends(current_user)) -> dict:
    c = await _processo(chantier_id, user["user_id"])
    passos = await db.chantier_percurso.find(
        {"chantier_id": chantier_id, "user_id": user["user_id"]}, {"_id": 0, "user_id": 0}
    ).sort("atualizado_em", -1).to_list(MAX_PASSOS)
    for p in passos:
        p["url"] = url_do_passo(p)
    return {"chantier_id": chantier_id, "nome": c.get("name"), "passos": passos}


@router.post("/{chantier_id}/percurso")
async def registar_passo(chantier_id: str, body: PassoIn, user=Depends(current_user)) -> dict:
    uid = user["user_id"]
    await _processo(chantier_id, uid)
    chave = _chave(body.rota, body.params)
    agora = _now()
    filtro = {"chantier_id": chantier_id, "user_id": uid, "chave": chave}
    existe = await db.chantier_percurso.find_one(filtro, {"_id": 1})
    if not existe and await db.chantier_percurso.count_documents({"chantier_id": chantier_id, "user_id": uid}) >= MAX_PASSOS:
        raise HTTPException(409, "O percurso deste processo atingiu o limite de passos.")
    definir = {"atualizado_em": agora}
    for campo, valor in (("titulo", body.titulo), ("resumo", body.resumo), ("app", body.app)):
        if valor:
            definir[campo] = valor
    ao_criar = {"passo_id": f"pas_{secrets.token_hex(6)}", "rota": body.rota, "params": body.params, "criado_em": agora}
    if not body.app:
        ao_criar["app"] = body.rota
    # upsert atómico: dois registos simultâneos do mesmo trabalho dão um só passo.
    await db.chantier_percurso.update_one(filtro, {"$set": definir, "$setOnInsert": ao_criar, "$inc": {"aberturas": 1}}, upsert=True)
    passo = await db.chantier_percurso.find_one(filtro, {"_id": 0, "user_id": 0}) or {**filtro, **ao_criar, **definir}
    await db.chantiers.update_one({"chantier_id": chantier_id, "user_id": uid}, {"$set": {"updated_at": agora}})
    passo.pop("_id", None)
    passo.pop("user_id", None)
    passo["url"] = url_do_passo(passo)
    return passo


@router.delete("/{chantier_id}/percurso/{passo_id}")
async def remover_passo(chantier_id: str, passo_id: str, user=Depends(current_user)) -> dict:
    await _processo(chantier_id, user["user_id"])
    r = await db.chantier_percurso.delete_one({"passo_id": passo_id, "chantier_id": chantier_id, "user_id": user["user_id"]})
    if not r.deleted_count:
        raise HTTPException(404, "Passo não encontrado neste processo")
    return {"ok": True}


async def percurso_resumido(chantier_id: str, user_id: str, limite: int = 40, database=None) -> list[dict]:
    """Percurso compacto para o dossier e o Assistente BTP (nunca levanta erro)."""
    try:
        passos = await (database if database is not None else db).chantier_percurso.find(
            {"chantier_id": chantier_id, "user_id": user_id}, {"_id": 0, "user_id": 0, "chave": 0}
        ).sort("atualizado_em", -1).to_list(limite)
    except Exception:  # noqa: BLE001 — o dossier nunca pode cair por causa do percurso
        return []
    out = []
    for p in passos:
        out.append({"passo_id": p.get("passo_id"), "app": p.get("app"), "rota": p.get("rota"), "params": p.get("params") or {},
                    "titulo": p.get("titulo") or None, "resumo": p.get("resumo") or None,
                    "atualizado_em": p.get("atualizado_em"), "url": url_do_passo(p)})
    return out

