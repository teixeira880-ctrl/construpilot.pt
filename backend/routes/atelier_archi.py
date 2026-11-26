"""Atelier do Arquiteto (app « Arquiteto & BIM », construpilot.pt) — mesmo código que o construpilot.fr.

No .pt o Estúdio de Projeto ainda não está ligado aos processos de licenciamento : as funções partilhadas com a rota do
Estúdio (validação do modelo, catálogo, medições CSV, desenho SVG em direto) estão aqui, e o editor usa
/atelier-archi/derivar e /atelier-archi/desenho.svg.

Atelier Architecte (app « Architecte & BIM ») — projets d'architecture sans dossier d'urbanisme.

Esquisse → maquette du Studio de projet → plans, façades, coupes, métré, DXF, IFC, PDF → DCE (CCTP + DPGF).

POST   /atelier-archi/esquisse/prompt            prompt en langage courant → maquette (aperçu, rien n'est enregistré)
POST   /atelier-archi/esquisse/croquis           traits dessinés à la main → maquette (aperçu)
POST   /atelier-archi/esquisse/photo             photo d'un croquis papier → maquette (aperçu)
POST   /atelier-archi/projets                    enregistre une maquette comme projet
GET    /atelier-archi/projets                    liste des projets
GET    /atelier-archi/projets/{id}               même réponse que le Studio (modelo, derivado, catalogo…) : l'éditeur du Studio s'ouvre tel quel
PUT    /atelier-archi/projets/{id}               enregistre la maquette éditée
DELETE /atelier-archi/projets/{id}               revient à la maquette de départ (comme « Réinitialiser » du Studio)
DELETE /atelier-archi/projets/{id}/definitif     supprime le projet
POST   /atelier-archi/projets/{id}/operacoes     opérations du Studio (Assistant, prompts d'édition)
GET    /atelier-archi/projets/{id}/pranchas.pdf | modelo.ifc | medicoes.csv | desenhos.dxf
GET    /atelier-archi/projets/{id}/dce/apercu    lots et lignes quantifiées tirés de la maquette
POST   /atelier-archi/projets/{id}/dce           lance la rédaction du DCE (même moteur et même historique que /pro/cctp)

Les projets sont dans `archi_projects` (un document par projet, propriétaire = user_id).
"""
from __future__ import annotations

import asyncio
import csv
import io
import base64
import hashlib
import secrets
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import Response
from pydantic import BaseModel, Field

from core.db import db
from core.security import current_user
from engines import estudio_projeto as EP
from engines.access import require_level
from engines.atelier_archi import croquis as C
from engines.atelier_archi import dce as DCE
from engines.atelier_archi import generateur as GEN
from engines.atelier_archi import programme as PROG
from engines.atelier_archi import verificacao as VER
from engines.estudio_projeto import desenhos as D
from engines.estudio_projeto import i18n as I
from engines.nom_fichier import content_disposition, nom_document
from engines.estudio_projeto.modelo import COBERTURAS, TIPOS_BASE, VAO_BASE

router = APIRouter(prefix="/atelier-archi", tags=["atelier-archi"])
T = I.tr
_TASKS: set = set()
MAX_PROJETS = 200


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
    """Modelo vindo do editor (nomes na língua do site) → modelo interno validado."""
    try:
        return EP.normalizar(I.modelo_entrada(modelo))
    except EP.ErroModelo as e:
        raise HTTPException(422, T(str(e)))


def _catalogo() -> Dict[str, Any]:
    from engines.estudio_projeto import materiais as MAT
    from engines.estudio_projeto import objetos as OBJ
    return I.catalogo_saida({"tipos_parede": TIPOS_BASE, "vaos": VAO_BASE, "coberturas": list(COBERTURAS), **MAT.catalogo(), **OBJ.catalogo()})


def _sai(m: Dict[str, Any], der: Dict[str, Any]) -> Dict[str, Any]:
    return {"modelo": I.modelo_saida(m), "derivado": I.traduzir(der)}


def _desenho(m: Dict[str, Any], der: Dict[str, Any], tipo: str, piso: int, lado: str, eixo: str, pos: Optional[float]) -> Dict[str, Any]:
    if tipo == "planta":
        if piso >= len(der["pisos"]):
            raise HTTPException(404, T("Piso inexistente."))
        return D.planta(m, der, piso)
    if not der["paredes"]:
        raise HTTPException(409, T("Desenhe pelo menos uma parede."))
    return D.alcado(m, der, lado) if tipo == "alcado" else D.corte(m, der, eixo, pos)


def medicoes_csv(der: Dict[str, Any]) -> str:
    """Medições com o identificador de cada parede, para a empresa poder conferir no desenho."""
    md = I.traduzir(der)["medicoes"]
    P = I.parte
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=";")
    n = lambda v: str(v).replace(".", ",")  # noqa: E731
    lin = lambda *cols: w.writerow([T(c) if isinstance(c, str) else c for c in cols])  # noqa: E731 — cabeçalhos na língua do site
    lin("ConstruPilot — Estúdio de Projeto — medições geométricas")
    w.writerow([md["convencao"]])
    w.writerow([])
    lin("PAREDES", "Piso", "Tipo", "Comprimento no eixo (m)", "Comprimento líquido (m)", "Altura (m)", "Espessura (m)",
        "Área bruta (m²)", "Vãos (m²)", "Área líquida (m²)", "Volume (m³)")
    for p in md["paredes"]:
        w.writerow([p["id"], p["piso"], p["nome_tipo"], n(p["comprimento_eixo_m"]), n(p["comprimento_liquido_m"]), n(p["altura_m"]),
                    n(p["espessura_m"]), n(p["area_bruta_m2"]), n(p["area_vaos_m2"]), n(p["area_liquida_m2"]), n(p["volume_m3"])])
    w.writerow([])
    lin("CAMADAS POR TIPO DE PAREDE", "Camada", "Espessura (m)", "Área (m²)", "Volume (m³)")
    for t in md["por_tipo"]:
        for c in t["camadas"]:
            w.writerow([t["nome"], c["material"], n(c["esp_m"]), n(c["area_m2"]), n(c["volume_m3"])])
    w.writerow([])
    lin("VÃOS", "Largura (m)", "Altura (m)", "Quantidade", "Área (m²)", "Identificadores")
    for v in md["vaos"]:
        w.writerow([P(v["tipo"]), n(v["largura_m"]), n(v["altura_m"]), v["quantidade"], n(v["area_m2"]), " ".join(v["ids"])])
    w.writerow([])
    lin("MAPA DE VÃOS", "Tipo", "Modelo", "Folhas", "Largura (m)", "Altura (m)", "Peitoril (m)", "Caixilharia", "Proteção", "Exterior",
        "Quantidade", "Área (m²)", "Identificadores")
    for v in md.get("mapa_vaos") or []:
        w.writerow([v["codigo"], P(v["tipo"]), v["modelo"], v["folhas"], n(v["largura_m"]), n(v["altura_m"]), n(v["peitoril_m"]), v["caixilharia"],
                    v["protecao"], P("sim") if v["exterior"] else P("não"), v["quantidade"], n(v["area_m2"]), " ".join(v["ids"])])
    w.writerow([])
    lin("QUADRO DE ÁREAS", "Área bruta (m²)", "Área útil (m²)", "Divisões", "Paredes e vazios (m²)")
    for q in md.get("quadro_areas") or []:
        w.writerow([q["piso"], n(q["area_bruta_m2"]), n(q["area_util_m2"]), q["n_divisoes"], n(q["paredes_e_vazios_m2"])])
    lin("Área de implantação (m²)", n(md.get("area_implantacao_m2", "")))
    if md.get("objetos"):
        w.writerow([])
        lin("EQUIPAMENTO E MOBILIÁRIO", "Categoria", "Quantidade")
        for ob in md["objetos"]:
            w.writerow([ob["nome"], ob["categoria"], ob["quantidade"]])
    w.writerow([])
    lin("DIVISÕES", "Piso", "Área útil (m²)", "Perímetro (m)", "Paredes da divisão (m²)", "Rodapé (m)", "Pavimento", "Paredes", "Teto")
    for d in md["divisoes"]:
        w.writerow([d["nome"], d["piso"], n(d["area_m2"]), n(d["perimetro_m"]), n(d["area_paredes_m2"]), n(d["rodape_m"]),
                    d["pavimento"], d["parede_interior"], d["teto"]])
    w.writerow([])
    lin("LAJES", "Área (m²)", "Espessura (m)", "Volume (m³)")
    for lj in md["lajes"]:
        w.writerow([lj["nome"], n(lj["area_m2"]), n(lj["espessura_m"]), n(lj["volume_m3"])])
    for t in md["terracos"]:
        w.writerow([T(f"Terraço sobre {t['sobre']}"), n(t["area_m2"]), "", ""])
    if md.get("escadas"):
        w.writerow([])
        lin("ESCADAS", "Piso", "Tipo", "Espelhos", "Espelho (m)", "Cobertores", "Cobertor (m)", "Largura (m)", "2e + c (m)",
            "Altura vencida (m)", "Área em planta (m²)", "Vazio na laje (m²)")
        for e in md["escadas"]:
            w.writerow([e["id"], e["piso"], P(f"escada {e['tipo']}"), e["n_espelhos"], n(e["espelho_m"]), e["n_cobertores"], n(e["cobertor_m"]), n(e["largura_m"]),
                        n(e["blondel_m"]), n(e["altura_m"]), n(e["area_planta_m2"]), n(e["vazio_m2"])])
        w.writerow([md["regra_vazio_escada"]])
    w.writerow([])
    lin("ACABAMENTOS", "Material", "Área (m²)")
    for ac in md["acabamentos"]:
        w.writerow([ac["elemento"], ac["material"], n(ac["area_m2"])])
    c, f, t = md["cobertura"], md["fachada"], md["totais"]
    w.writerow([])
    lin("COBERTURA", "Tipo", "Inclinação (°)", "Área real (m²)", "Área em planta (m²)", "Perímetro do beirado (m)", "Empenas (m²)")
    w.writerow(["", P(c["tipo"]), n(c["inclinacao_graus"]), n(c["area_m2"]), n(c["area_planta_m2"]), n(c["perimetro_beirado_m"]), n(c["empenas_m2"])])
    w.writerow([])
    lin("FACHADA EXTERIOR", "Perímetro (m)", "Área bruta (m²)", "Vãos (m²)", "Área líquida (m²)")
    w.writerow(["", n(f["perimetro_m"]), n(f["area_bruta_m2"]), n(f["area_vaos_m2"]), n(f["area_liquida_m2"])])
    w.writerow([])
    lin("TOTAIS", "Área bruta de construção (m²)", "Área útil (m²)")
    w.writerow(["", n(t["area_bruta_construcao_m2"]), n(t["area_util_m2"])])
    return buf.getvalue()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class PromptIn(BaseModel):
    prompt: str = Field(min_length=3, max_length=20000)
    ia: bool = True
    alvo_m2: Optional[float] = Field(default=None, ge=40, le=2000)   # modo simples: área de construção pretendida (sem garagem)


class Trait(BaseModel):
    type: str = Field(default="mur", pattern="^(mur|mur_ext|cloison|porte|fenetre|baie|portail)$")
    points: List[List[float]] = Field(min_length=1, max_length=4000)


class Texte(BaseModel):
    x: float
    y: float
    nom: str = Field(min_length=1, max_length=40)


class Cote(BaseModel):
    a: List[float] = Field(min_length=2, max_length=2)
    b: List[float] = Field(min_length=2, max_length=2)
    m: float = Field(gt=0, le=500)


class CroquisIn(BaseModel):
    traits: List[Trait] = Field(min_length=1, max_length=800)
    textes: List[Texte] = Field(default_factory=list, max_length=200)
    cotes: List[Cote] = Field(default_factory=list, max_length=40)
    y_bas: bool = True
    pe_direito: Optional[float] = Field(default=None, ge=2.0, le=6.0)
    toiture: Optional[str] = Field(default=None, pattern="^(plana|uma_agua|duas_aguas|quatro_aguas)$")


class PhotoIn(BaseModel):
    image_b64: str = Field(min_length=100, max_length=14_000_000)


class ProjetIn(BaseModel):
    titre: str = Field(min_length=1, max_length=160)
    modelo: Dict[str, Any]
    origine: str = Field(default="manuel", max_length=40)
    adresse: str = Field(default="", max_length=300)
    maitre_ouvrage: str = Field(default="", max_length=200)
    programme: str = Field(default="", max_length=20000)


class ModeloIn(BaseModel):
    modelo: Dict[str, Any]


class DceIn(BaseModel):
    lots: List[str] = Field(default_factory=list, max_length=20)
    ia: bool = True
    maitre_ouvrage: str = Field(default="", max_length=200)
    maitre_oeuvre: str = Field(default="", max_length=200)
    adresse: str = Field(default="", max_length=300)
    description: str = Field(default="", max_length=4000)
    nature: str = Field(default="neuf", pattern="^(neuf|renovation)$")


def _verificar_seguro(m: Dict[str, Any], der: Dict[str, Any], programme: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
    """O controlo nunca pode impedir o esboço de aparecer."""
    try:
        return VER.verificar(m, der, programme)
    except Exception:  # noqa: BLE001
        return None


def _apercu(m: Dict[str, Any], avisos: List[str], extra: Optional[Dict[str, Any]] = None,
            programme: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    der = EP.derivar(m)
    tot = der["medicoes"]["totais"]
    return {**_sai(m, der), "avisos": I.traduzir(avisos), "verificacao": _verificar_seguro(m, der, programme), "resume": {
        "niveaux": len(m["pisos"]), "murs": len(m["paredes"]), "ouvertures": len(m["vaos"]),
        "surface_utile_m2": tot["area_util_m2"], "surface_construite_m2": tot["area_bruta_construcao_m2"],
        "pieces": [{"nom": d["nome"], "niveau": d["piso"], "surface_m2": d["area_m2"]} for d in der["medicoes"]["divisoes"]]},
        **(extra or {})}


# ------------------------------------------------------------------------------------------ edição em direto (editor do Estúdio)
@router.post("/derivar")
async def derivar_direto(body: ModeloIn, user=Depends(current_user)) -> dict:
    m = _limpo(body.modelo)
    return _sai(m, await run_in_threadpool(EP.derivar, m))


@router.post("/desenho.svg")
async def desenho_svg(body: DesenhoIn, user=Depends(current_user)):
    m = _limpo(body.modelo)

    def go():
        der = EP.derivar(m)
        return D.svg(I.desenho(_desenho(m, der, body.tipo, body.piso, body.lado, body.eixo, body.pos)))
    return Response(content=await run_in_threadpool(go), media_type="image/svg+xml", headers={"Cache-Control": "no-store"})


# ------------------------------------------------------------------------------------------ esquisses (aperçu)
@router.post("/esquisse/prompt")
async def esquisse_prompt(body: PromptIn, user=Depends(current_user)) -> dict:
    """Déterministe : le même prompt donne la même maquette. L'IA ne sert qu'à lire un prompt que l'analyseur ne reconnaît
    pas (et sa lecture est mémorisée, pour rester identique la fois suivante)."""
    prog = PROG.programme(body.prompt)
    if not prog["reconnu"] and body.ia:
        cle = hashlib.sha256(body.prompt.strip().lower().encode()).hexdigest()
        lu = await db.archi_prompt_cache.find_one({"cle": cle}, {"_id": 0})
        data = (lu or {}).get("data")
        if data is None:
            try:
                from engines import ai
                brut = await ai._complete(
                    "Tu lis une demande de maison et tu réponds UNIQUEMENT en JSON valide.",
                    "Demande : " + body.prompt[:2000] + "\nRéponds : {\"chambres\": entier|null, \"surface\": m² habitables|null, "
                    "\"niveaux\": 1|2|null, \"garage\": bool, \"bureau\": bool, \"buanderie\": bool, \"suite\": bool, "
                    "\"cuisine_ouverte\": bool|null, \"toiture\": \"plana\"|\"duas_aguas\"|\"quatro_aguas\"|\"uma_agua\"|null}",
                    feature="atelier_programme")
                data = ai._json(brut, {})
                await db.archi_prompt_cache.update_one({"cle": cle}, {"$set": {"cle": cle, "data": data, "at": _now()}}, upsert=True)
            except Exception:  # noqa: BLE001 — sans IA : programme type, dit dans les hypothèses
                data = {}
        p2 = PROG.programme_depuis_ia(data)
        if p2:
            prog = p2
    if body.alvo_m2 and prog.get("detalhado"):
        prog, r = await run_in_threadpool(GEN.ajustar_area, prog, float(body.alvo_m2))
    else:
        r = await run_in_threadpool(GEN.generer, prog)
    pieces = [{"nom": p["nom"], "surface": p["surface"], "niveau": p["niveau"]} for p in prog["pieces"]]
    return await run_in_threadpool(_apercu, r["modelo"], r["avisos"], {"programme": {"pieces": pieces, "niveaux": prog["niveaux"],
                                                                                     "garage": prog["garage"], "toiture": prog["toiture"],
                                                                                     "detalhado": bool(prog.get("detalhado")),
                                                                                     "area_anunciada": (prog.get("lu") or {}).get("surface"),
                                                                                     "ajustado": bool(body.alvo_m2 and prog.get("detalhado"))},
                                                                       "pedidos": prog.get("pedidos") or []}, prog)


@router.post("/esquisse/croquis")
async def esquisse_croquis(body: CroquisIn, user=Depends(current_user)) -> dict:
    try:
        r = await run_in_threadpool(C.nettoyer, [t.model_dump() for t in body.traits], [t.model_dump() for t in body.textes],
                                    [c.model_dump() for c in body.cotes], body.y_bas, body.pe_direito, body.toiture)
    except (C.ErreurCroquis, EP.ErroModelo) as e:
        raise HTTPException(422, T(str(e)))
    return await run_in_threadpool(_apercu, r["modelo"], r["avisos"], {"stats": r["stats"]})


@router.post("/esquisse/photo")
async def esquisse_photo(body: PhotoIn, user=Depends(current_user)) -> dict:
    from engines.atelier_archi import vision
    b64 = body.image_b64.split(",", 1)[-1]
    try:
        base64.b64decode(b64[:4000] + "=" * (-len(b64[:4000]) % 4), validate=False)
    except Exception:  # noqa: BLE001
        raise HTTPException(422, T("Image illisible."))
    try:
        r = await vision.lire_photo(b64)
    except (C.ErreurCroquis, EP.ErroModelo) as e:
        raise HTTPException(422, T(str(e)))
    except RuntimeError as e:
        raise HTTPException(503, str(e))
    return await run_in_threadpool(_apercu, r["modelo"], r["avisos"], {"stats": r["stats"]})


# ------------------------------------------------------------------------------------------ projets
async def _projet(pid: str, uid: str) -> Dict[str, Any]:
    p = await db.archi_projects.find_one({"projet_id": pid, "user_id": uid}, {"_id": 0})
    if not p:
        raise HTTPException(404, T("Projet introuvable."))
    return p


def _modele(p: Dict[str, Any]) -> Dict[str, Any]:
    try:
        return EP.normalizar(p.get("modelo") or p.get("modelo_inicial"))
    except EP.ErroModelo:
        return EP.normalizar(p["modelo_inicial"])


def _pseudo_processo(p: Dict[str, Any]) -> Dict[str, Any]:
    """Cartouche des planches : titre, maître d'ouvrage, adresse du projet."""
    return {"title": p.get("titre"), "applicant": {"nom": p.get("maitre_ouvrage") or ""}, "terrain": {"voie": p.get("adresse") or ""},
            "requerente": {"nome": p.get("maitre_ouvrage") or ""}, "terreno": {"morada": p.get("adresse") or ""}}


@router.post("/projets")
async def creer_projet(body: ProjetIn, user=Depends(current_user)) -> dict:
    m = _limpo(body.modelo)
    n = await db.archi_projects.count_documents({"user_id": user["user_id"]})
    if n >= MAX_PROJETS:
        raise HTTPException(409, T("Nombre maximal de projets atteint : supprimez d'anciens projets."))
    pid = "arch_" + secrets.token_hex(6)
    doc = {"projet_id": pid, "user_id": user["user_id"], "titre": body.titre.strip(), "origine": body.origine[:40],
           "adresse": body.adresse.strip(), "maitre_ouvrage": body.maitre_ouvrage.strip(), "programme": body.programme.strip(),
           "modelo": m, "modelo_inicial": m, "created_at": _now(), "updated_at": _now()}
    await db.archi_projects.insert_one(dict(doc))
    return {"projet_id": pid, "titre": doc["titre"]}


@router.get("/projets")
async def lister(user=Depends(current_user)) -> dict:
    cur = db.archi_projects.find({"user_id": user["user_id"]}, {"_id": 0, "modelo": 0, "modelo_inicial": 0}).sort("updated_at", -1).limit(MAX_PROJETS)
    return {"projets": [x async for x in cur]}


@router.get("/projets/{pid}")
async def obter(pid: str, user=Depends(current_user)) -> dict:
    p = await _projet(pid, user["user_id"])
    m = _modele(p)
    der = await run_in_threadpool(EP.derivar, m)
    contexto = {"morada": p["adresse"]} if p.get("adresse") else {}
    return {**_sai(m, der), "origem": "guardado", "avisos_origem": [], "updated_at": p.get("updated_at"),
            "catalogo": _catalogo(), "titulo": p.get("titre"), "contexto": contexto, "projet": {k: p.get(k) for k in (
                "projet_id", "titre", "origine", "adresse", "maitre_ouvrage", "programme", "created_at", "updated_at", "dce_id")},
            "nota": T("Projet de l'Atelier Architecte : la maquette est la seule source des plans, du métré, de l'IFC et du DCE.")}


@router.put("/projets/{pid}")
async def guardar(pid: str, body: ModeloIn, user=Depends(current_user)) -> dict:
    await _projet(pid, user["user_id"])
    m = _limpo(body.modelo)
    der = await run_in_threadpool(EP.derivar, m)
    agora = _now()
    await db.archi_projects.update_one({"projet_id": pid, "user_id": user["user_id"]}, {"$set": {"modelo": m, "updated_at": agora}})
    return {"ok": True, **_sai(m, der), "updated_at": agora}


@router.delete("/projets/{pid}")
async def repor(pid: str, user=Depends(current_user)) -> dict:
    p = await _projet(pid, user["user_id"])
    await db.archi_projects.update_one({"projet_id": pid, "user_id": user["user_id"]},
                                       {"$set": {"modelo": p["modelo_inicial"], "updated_at": _now()}})
    return {"ok": True}


@router.delete("/projets/{pid}/definitif")
async def supprimer(pid: str, user=Depends(current_user)) -> dict:
    await _projet(pid, user["user_id"])
    await db.archi_projects.delete_one({"projet_id": pid, "user_id": user["user_id"]})
    return {"ok": True}


@router.post("/projets/{pid}/operacoes")
async def operacoes(pid: str, body: OperacoesIn, user=Depends(current_user)) -> dict:
    from engines.estudio_projeto import operacoes as OP
    p = await _projet(pid, user["user_id"])
    m0 = _modele(p)

    def go():
        m, feitos, falhas = OP.aplicar(m0, I.operacoes_entrada(m0, body.operacoes))
        return m, feitos, falhas, EP.derivar(m)
    m, feitos, falhas, der = await run_in_threadpool(go)
    guardado = None
    if body.guardar and feitos:
        guardado = _now()
        await db.archi_projects.update_one({"projet_id": pid, "user_id": user["user_id"]}, {"$set": {"modelo": m, "updated_at": guardado}})
    return {"ok": bool(feitos), "feitos": I.traduzir(feitos), "falhas": I.traduzir(falhas), **_sai(m, der), "updated_at": guardado,
            "resumo": I.traduzir(OP.resumo(m, der))}


def _fichier(data: bytes, mime: str, base: str, p: Dict[str, Any], ext: str, inline: bool = False) -> Response:
    return Response(content=data, media_type=mime, headers={
        "Content-Disposition": content_disposition(nom_document(T(base), p.get("titre"), ext=ext) if ext != "pdf"
                                                   else nom_document(T(base), p.get("titre")), inline=inline)})


@router.get("/projets/{pid}/pranchas.pdf")
async def pranchas(pid: str, user=Depends(current_user)):
    from engines.estudio_projeto import exportar as EX
    p = await _projet(pid, user["user_id"])
    m = _modele(p)

    def go():
        return EX.pranchas_pdf(_pseudo_processo(p), I.desenhos(D.conjunto(m, EP.derivar(m))))
    return _fichier(await run_in_threadpool(go), "application/pdf", "Estudio-pranchas", p, "pdf", inline=True)


@router.get("/projets/{pid}/modelo.ifc")
async def modelo_ifc(pid: str, user=Depends(current_user)):
    from engines.estudio_projeto import ifc as IFC
    p = await _projet(pid, user["user_id"])
    m = _modele(p)

    def go():
        return IFC.construir(m, EP.derivar(m), chave=pid, nome_projeto=p.get("titre") or T("Projeto ConstruPilot")).to_string().encode("utf-8")
    return _fichier(await run_in_threadpool(go), "application/x-step", "Estudio-modelo", p, "ifc")


@router.get("/projets/{pid}/verificacao")
async def verificacao(pid: str, user=Depends(current_user)) -> dict:
    """Controlo regulamentar e do programa do projeto guardado (mesmas regras que no esboço)."""
    p = await _projet(pid, user["user_id"])
    m = _modele(p)

    def go():
        prog = PROG.programme(p["programme"]) if (p.get("programme") or "").strip() else None
        return VER.verificar(m, EP.derivar(m), prog)
    return await run_in_threadpool(go)


@router.get("/projets/{pid}/medicoes.csv")
async def medicoes(pid: str, user=Depends(current_user)):
    p = await _projet(pid, user["user_id"])
    der = await run_in_threadpool(EP.derivar, _modele(p))
    return _fichier(("﻿" + medicoes_csv(der)).encode("utf-8"), "text/csv; charset=utf-8", "Estudio-medicoes", p, "csv")


@router.get("/projets/{pid}/desenhos.dxf")
async def desenhos_dxf(pid: str, user=Depends(current_user)):
    from engines.estudio_projeto import exportar as EX
    p = await _projet(pid, user["user_id"])
    m = _modele(p)

    def go():
        return EX.dxf(I.desenhos(D.conjunto(m, EP.derivar(m))), p.get("titre"))
    return _fichier(await run_in_threadpool(go), "image/vnd.dxf", "Estudio-desenhos", p, "dxf")


# ------------------------------------------------------------------------------------------ DCE
@router.get("/projets/{pid}/dce/apercu")
async def dce_apercu(pid: str, user=Depends(current_user)) -> dict:
    p = await _projet(pid, user["user_id"])
    s = await run_in_threadpool(DCE.selection, _modele(p))
    return {"resume": s["resume"], "lots": [{"code": l["code"], "ouvrages": l["ouvrages"], "lignes": l["lignes"]} for l in s["lots"]]}


@router.post("/projets/{pid}/dce", dependencies=[Depends(require_level("pro"))])
async def dce_lancer(pid: str, body: DceIn, user=Depends(current_user)) -> dict:
    """Rédaction du DCE complet (pages de garde, RC, CCTP par lot, cadre de DPGF) par le rédacteur CCTP de ConstruPilot.
    Le dossier apparaît aussi dans l'historique du Rédacteur CCTP · DCE."""
    from routes import cctp as RC
    p = await _projet(pid, user["user_id"])
    s = await run_in_threadpool(DCE.selection, _modele(p), body.lots or None)
    if not s["lots"]:
        raise HTTPException(400, T("La maquette ne donne aucun lot : dessinez au moins les murs et les ouvertures."))
    projet = RC.Projet(nom=p["titre"][:160], adresse=body.adresse or p.get("adresse") or "",
                       maitre_ouvrage=body.maitre_ouvrage or p.get("maitre_ouvrage") or "", maitre_oeuvre=body.maitre_oeuvre,
                       nature=body.nature, description=(body.description or p.get("programme") or "")[:4000],
                       pieces=[RC.Piece(nom=x["nom"][:80], type=x["type"], surface=min(x["surface"], 5000), niveau=str(x["niveau"])[:20])
                               for x in s["pieces"]]).model_dump()
    dossier_id = "cctp_" + secrets.token_hex(6)
    await db.cctp_dossiers.insert_one({"dossier_id": dossier_id, "user_id": user["user_id"], "projet": projet, "doc_id": None,
                                       "ia": body.ia, "status": "running", "created_at": _now(), "source": {"atelier": pid}})
    await db.archi_projects.update_one({"projet_id": pid, "user_id": user["user_id"]}, {"$set": {"dce_id": dossier_id}})
    t = asyncio.create_task(RC._run(dossier_id, user["user_id"], projet, s["lots"], body.ia))
    _TASKS.add(t)
    t.add_done_callback(_TASKS.discard)
    return {"dossier_id": dossier_id, "status": "running", "lots": s["resume"]["lots"]}
