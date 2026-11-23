"""Rotas do Estúdio de Projeto — modelo único do edifício ligado a um processo de licenciamento.

GET    /estudio-projeto/processos/{pid}             modelo (guardado, ou criado a partir do processo) + tudo o que deriva dele
PUT    /estudio-projeto/processos/{pid}             guarda o modelo editado
DELETE /estudio-projeto/processos/{pid}             repõe o modelo a partir do processo
POST   /estudio-projeto/derivar                     modelo → derivado (edição em direto, sem guardar)
POST   /estudio-projeto/desenho.svg                 modelo → planta | alçado | corte em SVG (edição em direto)
GET    /estudio-projeto/processos/{pid}/pranchas.pdf   plantas, alçados e cortes do modelo guardado (carimbo do processo)
GET    /estudio-projeto/processos/{pid}/medicoes.csv   medições geométricas (paredes, camadas, vãos, divisões, lajes, cobertura)
GET    /estudio-projeto/processos/{pid}/modelo.ifc     IFC4 do modelo guardado
GET    /estudio-projeto/processos/{pid}/desenhos.dxf   plantas, alçados e cortes em DXF (metros, camadas)
POST   /estudio-projeto/processos/{pid}/operacoes      aplica operações (parede, sala, vão, materiais…) e guarda
GET    /estudio-projeto/processos/{pid}/divergencias   o que o Estúdio tem de diferente do processo de licenciamento
POST   /estudio-projeto/processos/{pid}/sincronizar-materiais   leva os acabamentos gerais do Estúdio para o processo

O modelo fica numa coleção própria (`urbanismo_estudios`): o processo de licenciamento não é alterado por estas rotas.
"""
from __future__ import annotations

import csv
import io
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import Response
from pydantic import BaseModel, Field

from core.db import db
from core.security import current_user
from engines import estudio_projeto as EP
from engines.estudio_projeto import desenhos as D
from engines.estudio_projeto.modelo import COBERTURAS, TIPOS_BASE, VAO_BASE
from engines.nom_fichier import content_disposition, nom_document
from routes import urbanismo_auto as UA

router = APIRouter(prefix="/estudio-projeto", tags=["estudio-projeto"])


class ModeloIn(BaseModel):
    modelo: Dict[str, Any]


class OperacoesIn(BaseModel):
    operacoes: List[Dict[str, Any]] = Field(min_length=1, max_length=60)
    guardar: bool = True


class DesenhoIn(BaseModel):
    modelo: Dict[str, Any]
    tipo: str = Field(default="planta", pattern="^(planta|alcado|corte)$")
    piso: int = Field(default=0, ge=0, le=5)
    lado: str = Field(default="frente", pattern="^(frente|tardoz|esquerda|direita)$")
    eixo: str = Field(default="x", pattern="^(x|y)$")
    pos: Optional[float] = Field(default=None, ge=-500, le=500)


def _limpo(modelo: Dict[str, Any]) -> Dict[str, Any]:
    try:
        return EP.normalizar(modelo)
    except EP.ErroModelo as e:
        raise HTTPException(422, str(e))


async def _carregar(pid: str, uid: str) -> Dict[str, Any]:
    d = await UA._owned(pid, uid)
    g = await db.urbanismo_estudios.find_one({"processo_id": pid, "user_id": uid}, {"_id": 0})
    if g and g.get("modelo"):
        try:
            return {"processo": d, "modelo": EP.normalizar(g["modelo"]), "origem": "guardado", "avisos_origem": [],
                    "updated_at": g.get("updated_at")}
        except EP.ErroModelo:
            pass          # modelo guardado ilegível: volta ao do processo em vez de falhar
    try:
        r = EP.de_processo(d)
    except EP.ErroModelo as e:
        raise HTTPException(409, str(e))
    return {"processo": d, "modelo": r["modelo"], "origem": "processo", "avisos_origem": r["avisos"], "updated_at": None}


def _catalogo() -> Dict[str, Any]:
    from engines.estudio_projeto import materiais as MAT
    from engines.estudio_projeto import objetos as OBJ
    return {"tipos_parede": TIPOS_BASE, "vaos": VAO_BASE, "coberturas": list(COBERTURAS), **MAT.catalogo(), **OBJ.catalogo()}


@router.get("/processos/{pid}")
async def obter(pid: str, user=Depends(current_user)) -> dict:
    c = await _carregar(pid, user["user_id"])
    der = await run_in_threadpool(EP.derivar, c["modelo"])
    return {"modelo": c["modelo"], "derivado": der, "origem": c["origem"], "avisos_origem": c["avisos_origem"],
            "updated_at": c["updated_at"], "catalogo": _catalogo(), "titulo": c["processo"].get("title"),
            "nota": ("O Estúdio parte das medidas do processo. As peças do licenciamento (implantação, quadro de áreas, "
                     "memória) continuam a ser as do processo: o que alterar aqui ainda não as atualiza.")}


@router.put("/processos/{pid}")
async def guardar(pid: str, body: ModeloIn, user=Depends(current_user)) -> dict:
    await UA._owned(pid, user["user_id"])
    m = _limpo(body.modelo)
    der = await run_in_threadpool(EP.derivar, m)
    agora = datetime.now(timezone.utc).isoformat()
    await db.urbanismo_estudios.replace_one({"processo_id": pid, "user_id": user["user_id"]},
                                            {"processo_id": pid, "user_id": user["user_id"], "modelo": m, "updated_at": agora},
                                            upsert=True)
    return {"ok": True, "modelo": m, "derivado": der, "updated_at": agora}


@router.delete("/processos/{pid}")
async def repor(pid: str, user=Depends(current_user)) -> dict:
    await UA._owned(pid, user["user_id"])
    await db.urbanismo_estudios.delete_one({"processo_id": pid, "user_id": user["user_id"]})
    return {"ok": True}


@router.post("/derivar")
async def derivar(body: ModeloIn, user=Depends(current_user)) -> dict:
    m = _limpo(body.modelo)
    return {"modelo": m, "derivado": await run_in_threadpool(EP.derivar, m)}


def _desenho(m: Dict[str, Any], der: Dict[str, Any], tipo: str, piso: int, lado: str, eixo: str, pos: Optional[float]) -> Dict[str, Any]:
    if tipo == "planta":
        if piso >= len(der["pisos"]):
            raise HTTPException(404, "Piso inexistente.")
        return D.planta(m, der, piso)
    if not der["paredes"]:
        raise HTTPException(409, "Desenhe pelo menos uma parede.")
    return D.alcado(m, der, lado) if tipo == "alcado" else D.corte(m, der, eixo, pos)


@router.post("/desenho.svg")
async def desenho_svg(body: DesenhoIn, user=Depends(current_user)):
    m = _limpo(body.modelo)

    def go():
        der = EP.derivar(m)
        return D.svg(_desenho(m, der, body.tipo, body.piso, body.lado, body.eixo, body.pos))
    return Response(content=await run_in_threadpool(go), media_type="image/svg+xml", headers={"Cache-Control": "no-store"})


@router.get("/processos/{pid}/pranchas.pdf")
async def pranchas(pid: str, user=Depends(current_user)):
    """Pranchas A3 vetoriais, à escala (1:50, 1:100…), com escala gráfica e carimbo do processo."""
    from engines.estudio_projeto import exportar as EX
    c = await _carregar(pid, user["user_id"])

    def go():
        der = EP.derivar(c["modelo"])
        return EX.pranchas_pdf(c["processo"], D.conjunto(c["modelo"], der))
    data = await run_in_threadpool(go)
    return Response(content=data, media_type="application/pdf", headers={
        "Content-Disposition": content_disposition(nom_document("Estudio-pranchas", c["processo"].get("title")), inline=True)})


def medicoes_csv(der: Dict[str, Any]) -> str:
    """Medições com o identificador de cada parede, para a empresa poder conferir no desenho."""
    md = der["medicoes"]
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=";")
    n = lambda v: str(v).replace(".", ",")  # noqa: E731
    w.writerow(["ConstruPilot — Estúdio de Projeto — medições geométricas"])
    w.writerow([md["convencao"]])
    w.writerow([])
    w.writerow(["PAREDES", "Piso", "Tipo", "Comprimento no eixo (m)", "Comprimento líquido (m)", "Altura (m)", "Espessura (m)",
                "Área bruta (m²)", "Vãos (m²)", "Área líquida (m²)", "Volume (m³)"])
    for p in md["paredes"]:
        w.writerow([p["id"], p["piso"], p["nome_tipo"], n(p["comprimento_eixo_m"]), n(p["comprimento_liquido_m"]), n(p["altura_m"]),
                    n(p["espessura_m"]), n(p["area_bruta_m2"]), n(p["area_vaos_m2"]), n(p["area_liquida_m2"]), n(p["volume_m3"])])
    w.writerow([])
    w.writerow(["CAMADAS POR TIPO DE PAREDE", "Camada", "Espessura (m)", "Área (m²)", "Volume (m³)"])
    for t in md["por_tipo"]:
        for c in t["camadas"]:
            w.writerow([t["nome"], c["material"], n(c["esp_m"]), n(c["area_m2"]), n(c["volume_m3"])])
    w.writerow([])
    w.writerow(["VÃOS", "Largura (m)", "Altura (m)", "Quantidade", "Área (m²)", "Identificadores"])
    for v in md["vaos"]:
        w.writerow([v["tipo"], n(v["largura_m"]), n(v["altura_m"]), v["quantidade"], n(v["area_m2"]), " ".join(v["ids"])])
    w.writerow([])
    w.writerow(["MAPA DE VÃOS", "Tipo", "Modelo", "Folhas", "Largura (m)", "Altura (m)", "Peitoril (m)", "Caixilharia", "Proteção", "Exterior",
                "Quantidade", "Área (m²)", "Identificadores"])
    for v in md.get("mapa_vaos") or []:
        w.writerow([v["codigo"], v["tipo"], v["modelo"], v["folhas"], n(v["largura_m"]), n(v["altura_m"]), n(v["peitoril_m"]), v["caixilharia"],
                    v["protecao"], "sim" if v["exterior"] else "não", v["quantidade"], n(v["area_m2"]), " ".join(v["ids"])])
    w.writerow([])
    w.writerow(["QUADRO DE ÁREAS", "Área bruta (m²)", "Área útil (m²)", "Divisões", "Paredes e vazios (m²)"])
    for q in md.get("quadro_areas") or []:
        w.writerow([q["piso"], n(q["area_bruta_m2"]), n(q["area_util_m2"]), q["n_divisoes"], n(q["paredes_e_vazios_m2"])])
    w.writerow(["Área de implantação (m²)", n(md.get("area_implantacao_m2", ""))])
    if md.get("objetos"):
        w.writerow([])
        w.writerow(["EQUIPAMENTO E MOBILIÁRIO", "Categoria", "Quantidade"])
        for ob in md["objetos"]:
            w.writerow([ob["nome"], ob["categoria"], ob["quantidade"]])
    w.writerow([])
    w.writerow(["DIVISÕES", "Piso", "Área útil (m²)", "Perímetro (m)", "Paredes da divisão (m²)", "Rodapé (m)", "Pavimento", "Paredes", "Teto"])
    for d in md["divisoes"]:
        w.writerow([d["nome"], d["piso"], n(d["area_m2"]), n(d["perimetro_m"]), n(d["area_paredes_m2"]), n(d["rodape_m"]),
                    d["pavimento"], d["parede_interior"], d["teto"]])
    w.writerow([])
    w.writerow(["LAJES", "Área (m²)", "Espessura (m)", "Volume (m³)"])
    for lj in md["lajes"]:
        w.writerow([lj["nome"], n(lj["area_m2"]), n(lj["espessura_m"]), n(lj["volume_m3"])])
    for t in md["terracos"]:
        w.writerow([f"Terraço sobre {t['sobre']}", n(t["area_m2"]), "", ""])
    if md.get("escadas"):
        w.writerow([])
        w.writerow(["ESCADAS", "Piso", "Tipo", "Espelhos", "Espelho (m)", "Cobertores", "Cobertor (m)", "Largura (m)", "2e + c (m)",
                    "Altura vencida (m)", "Área em planta (m²)", "Vazio na laje (m²)"])
        for e in md["escadas"]:
            w.writerow([e["id"], e["piso"], e["tipo"], e["n_espelhos"], n(e["espelho_m"]), e["n_cobertores"], n(e["cobertor_m"]), n(e["largura_m"]),
                        n(e["blondel_m"]), n(e["altura_m"]), n(e["area_planta_m2"]), n(e["vazio_m2"])])
        w.writerow([md["regra_vazio_escada"]])
    w.writerow([])
    w.writerow(["ACABAMENTOS", "Material", "Área (m²)"])
    for ac in md["acabamentos"]:
        w.writerow([ac["elemento"], ac["material"], n(ac["area_m2"])])
    c, f, t = md["cobertura"], md["fachada"], md["totais"]
    w.writerow([])
    w.writerow(["COBERTURA", "Tipo", "Inclinação (°)", "Área real (m²)", "Área em planta (m²)", "Perímetro do beirado (m)", "Empenas (m²)"])
    w.writerow(["", c["tipo"], n(c["inclinacao_graus"]), n(c["area_m2"]), n(c["area_planta_m2"]), n(c["perimetro_beirado_m"]), n(c["empenas_m2"])])
    w.writerow([])
    w.writerow(["FACHADA EXTERIOR", "Perímetro (m)", "Área bruta (m²)", "Vãos (m²)", "Área líquida (m²)"])
    w.writerow(["", n(f["perimetro_m"]), n(f["area_bruta_m2"]), n(f["area_vaos_m2"]), n(f["area_liquida_m2"])])
    w.writerow([])
    w.writerow(["TOTAIS", "Área bruta de construção (m²)", "Área útil (m²)"])
    w.writerow(["", n(t["area_bruta_construcao_m2"]), n(t["area_util_m2"])])
    return buf.getvalue()


@router.get("/processos/{pid}/modelo.ifc")
async def modelo_ifc(pid: str, user=Depends(current_user)):
    """IFC4 do modelo guardado: paredes com camadas, vãos, lajes, cobertura, escadas e espaços."""
    from engines.estudio_projeto import ifc as IFC
    c = await _carregar(pid, user["user_id"])

    def go():
        der = EP.derivar(c["modelo"])
        return IFC.construir(c["modelo"], der, chave=pid, nome_projeto=c["processo"].get("title") or "Projeto ConstruPilot").to_string().encode("utf-8")
    data = await run_in_threadpool(go)
    return Response(content=data, media_type="application/x-step", headers={
        "Content-Disposition": content_disposition(nom_document("Estudio-modelo", c["processo"].get("title"), ext="ifc"))})


@router.get("/processos/{pid}/medicoes.csv")
async def medicoes(pid: str, user=Depends(current_user)):
    c = await _carregar(pid, user["user_id"])
    der = await run_in_threadpool(EP.derivar, c["modelo"])
    data = ("﻿" + medicoes_csv(der)).encode("utf-8")
    return Response(content=data, media_type="text/csv; charset=utf-8", headers={
        "Content-Disposition": content_disposition(nom_document("Estudio-medicoes", c["processo"].get("title"), ext="csv"))})


@router.get("/processos/{pid}/desenhos.dxf")
async def desenhos_dxf(pid: str, user=Depends(current_user)):
    """Plantas, alçados e cortes em DXF (metros, uma camada por tipo de elemento), para abrir em AutoCAD, BricsCAD, QGIS…"""
    from engines.estudio_projeto import exportar as EX
    c = await _carregar(pid, user["user_id"])

    def go():
        der = EP.derivar(c["modelo"])
        return EX.dxf(D.conjunto(c["modelo"], der), c["processo"].get("title"))
    data = await run_in_threadpool(go)
    return Response(content=data, media_type="image/vnd.dxf", headers={
        "Content-Disposition": content_disposition(nom_document("Estudio-desenhos", c["processo"].get("title"), ext="dxf"))})


async def _guardar(pid: str, uid: str, m: Dict[str, Any]) -> str:
    agora = datetime.now(timezone.utc).isoformat()
    await db.urbanismo_estudios.replace_one({"processo_id": pid, "user_id": uid},
                                            {"processo_id": pid, "user_id": uid, "modelo": m, "updated_at": agora}, upsert=True)
    return agora


async def aplicar_operacoes(pid: str, uid: str, operacoes: List[Dict[str, Any]], guardar_modelo: bool = True) -> Dict[str, Any]:
    """Usado pela rota e pelo Assistente: aplica as operações ao modelo do processo e (por omissão) guarda."""
    from engines.estudio_projeto import operacoes as OP
    c = await _carregar(pid, uid)

    def go():
        m, feitos, falhas = OP.aplicar(c["modelo"], operacoes)
        return m, feitos, falhas, EP.derivar(m)
    m, feitos, falhas, der = await run_in_threadpool(go)
    guardado = None
    if guardar_modelo and feitos:
        guardado = await _guardar(pid, uid, m)
    return {"ok": bool(feitos), "feitos": feitos, "falhas": falhas, "modelo": m, "derivado": der, "updated_at": guardado,
            "resumo": OP.resumo(m, der)}


async def ver_resumo(pid: str, uid: str) -> Dict[str, Any]:
    from engines.estudio_projeto import operacoes as OP
    c = await _carregar(pid, uid)
    der = await run_in_threadpool(EP.derivar, c["modelo"])
    return {"origem": c["origem"], **OP.resumo(c["modelo"], der)}


@router.post("/processos/{pid}/operacoes")
async def operacoes(pid: str, body: OperacoesIn, user=Depends(current_user)) -> dict:
    return await aplicar_operacoes(pid, user["user_id"], body.operacoes, body.guardar)


def divergencias_de(processo: Dict[str, Any], m: Dict[str, Any], der: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Compara o Estúdio com o modelo que sai diretamente do processo de licenciamento. Só factos medidos; nada é corrigido."""
    from engines.estudio_projeto import materiais as MAT
    try:
        ref = EP.de_processo(processo)["modelo"]
    except EP.ErroModelo:
        return []
    dref = EP.derivar(ref)
    out: List[Dict[str, Any]] = []

    def dif(campo, a, b, unidade="", tol=0.0):
        if isinstance(a, (int, float)) and isinstance(b, (int, float)):
            if abs(float(a) - float(b)) <= tol:
                return
        elif a == b:
            return
        out.append({"campo": campo, "processo": a, "estudio": b, "unidade": unidade})

    ma, mb = dref["medicoes"], der["medicoes"]
    dif("Número de pisos", len(ref["pisos"]), len(m["pisos"]))
    dif("Área de implantação", ma["area_implantacao_m2"], mb["area_implantacao_m2"], "m²", 0.05)
    dif("Área bruta de construção", ma["totais"]["area_bruta_construcao_m2"], mb["totais"]["area_bruta_construcao_m2"], "m²", 0.05)
    dif("Área útil", ma["totais"]["area_util_m2"], mb["totais"]["area_util_m2"], "m²", 0.05)
    for pa, pb in zip(dref["pisos"], der["pisos"]):
        dif(f"Pé-direito — {pb['nome']}", pa["pe_direito_m"], pb["pe_direito_m"], "m", 0.005)
    dif("Tipo de cobertura", ref["cobertura"]["tipo"].replace("_", " "), m["cobertura"]["tipo"].replace("_", " "))
    dif("Inclinação da cobertura", ref["cobertura"]["inclinacao_graus"], m["cobertura"]["inclinacao_graus"], "°", 0.5)
    dif("Altura da cumeeira", dref["cobertura"].get("z_cumeeira"), der["cobertura"].get("z_cumeeira"), "m", 0.02)
    ext = lambda d: sum(l["quantidade"] for l in d["medicoes"]["mapa_vaos"] if l["exterior"])  # noqa: E731
    dif("Vãos exteriores", ext(dref), ext(der))
    dif("Área de vãos na fachada", ma["fachada"]["area_vaos_m2"], mb["fachada"]["area_vaos_m2"], "m²", 0.05)
    cr, ce = MAT.cores(ref.get("materiais")), MAT.cores(m.get("materiais"))
    for k in ("fachada", "cobertura", "caixilharia"):
        ia, ib = (ref.get("materiais") or {}).get(k) or MAT.PADRAO[k], (m.get("materiais") or {}).get(k) or MAT.PADRAO[k]
        if ia != ib:
            out.append({"campo": f"Acabamento — {k}", "processo": MAT.acabamento(k, ia)["nome"], "estudio": MAT.acabamento(k, ib)["nome"], "unidade": ""})
    del cr, ce
    return out


@router.get("/processos/{pid}/divergencias")
async def divergencias(pid: str, user=Depends(current_user)) -> dict:
    c = await _carregar(pid, user["user_id"])
    der = await run_in_threadpool(EP.derivar, c["modelo"])
    return {"origem": c["origem"], "divergencias": divergencias_de(c["processo"], c["modelo"], der),
            "nota": "As peças do licenciamento são as do processo. O Estúdio não as altera sozinho: use «Levar acabamentos para o processo» "
                    "ou corrija o processo para as medidas coincidirem."}


@router.post("/processos/{pid}/sincronizar-materiais")
async def sincronizar_materiais(pid: str, user=Depends(current_user)) -> dict:
    """Leva fachada, cobertura e caixilharia do Estúdio para o processo (mesma regra do processo: só o que o seu catálogo conhece;
    a memória descritiva é refeita pela rota do processo)."""
    from engines.urbanismo_pt.auto import pecas_auto as PA
    c = await _carregar(pid, user["user_id"])
    mm = c["modelo"].get("materiais") or {}
    pedido, ignorados = {}, []
    for k, cat in (("fachada", PA.MATERIAIS_FACHADA), ("cobertura", PA.MATERIAIS_COBERTURA), ("caixilharia", PA.CAIXILHARIA)):
        if mm.get(k) in cat:
            pedido[k] = mm[k]
        elif mm.get(k):
            ignorados.append(k)
    if not pedido:
        return {"ok": False, "levados": {}, "ignorados": ignorados,
                "msg": "Os acabamentos escolhidos no Estúdio não existem no catálogo das peças de licenciamento; o processo fica como está."}
    r = await UA.materiais(pid, UA.MateriaisIn(**pedido), user)
    return {"ok": True, "levados": pedido, "ignorados": ignorados, "materiais": r["materiais"]}


async def anexar_ao_zip(zbytes: bytes, pid: str, uid: str) -> bytes:
    """Junta ao ZIP do processo a pasta «Estudio-de-Projeto» (pranchas à escala, DXF, IFC, medições e diferenças para o processo).
    Só quando o utilizador guardou um modelo no Estúdio; qualquer falha deixa o ZIP do processo exatamente como estava."""
    import io
    import logging
    import zipfile
    try:
        g = await db.urbanismo_estudios.find_one({"processo_id": pid, "user_id": uid}, {"_id": 0})
        if not g or not g.get("modelo"):
            return zbytes
        c = await _carregar(pid, uid)
        if c["origem"] != "guardado":
            return zbytes

        def go() -> bytes:
            from engines.estudio_projeto import exportar as EX, ifc as IFC
            m = c["modelo"]
            der = EP.derivar(m)
            cj = D.conjunto(m, der)
            titulo = c["processo"].get("title") or "Projeto ConstruPilot"
            difs = divergencias_de(c["processo"], m, der)
            linhas = ["ESTÚDIO DE PROJETO — ConstruPilot", "",
                      "Esta pasta contém o modelo editado no Estúdio de Projeto. As peças de licenciamento do processo (fora desta pasta)",
                      "são as que foram verificadas contra o PDM, o RGEU e o RJUE; o Estúdio não as altera.", ""]
            if difs:
                linhas += ["DIFERENÇAS ENTRE O ESTÚDIO E O PROCESSO:"] + [
                    f"  - {x['campo']}: processo = {x['processo']} {x['unidade']} · Estúdio = {x['estudio']} {x['unidade']}".rstrip() for x in difs]
            else:
                linhas += ["O Estúdio coincide com o processo nas medidas comparadas (pisos, áreas, cobertura, vãos, acabamentos)."]
            if der["erros"]:
                linhas += ["", "ERROS DO MODELO:"] + [f"  - {e['msg']}" for e in der["erros"]]
            out = io.BytesIO()
            with zipfile.ZipFile(io.BytesIO(zbytes)) as zin, zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zout:
                for it in zin.infolist():
                    zout.writestr(it, zin.read(it.filename))
                p = "Estudio-de-Projeto/"
                zout.writestr(p + "LEIA-ME.txt", "\r\n".join(linhas))
                zout.writestr(p + "Pranchas-A3-a-escala.pdf", EX.pranchas_pdf(c["processo"], cj))
                zout.writestr(p + "Desenhos.dxf", EX.dxf(cj, titulo))
                zout.writestr(p + "Medicoes-geometricas.csv", ("﻿" + medicoes_csv(der)).encode("utf-8"))
                if der["ok"]:
                    zout.writestr(p + "Modelo.ifc", IFC.construir(m, der, chave=pid, nome_projeto=titulo).to_string().encode("utf-8"))
            return out.getvalue()
        return await run_in_threadpool(go)
    except Exception:  # noqa: BLE001 — o ZIP do processo nunca pode falhar por causa do Estúdio
        logging.getLogger(__name__).exception("Estúdio: anexo ao ZIP falhou")
        return zbytes
