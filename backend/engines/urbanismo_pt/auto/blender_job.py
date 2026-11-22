"""Trabalho de fundo «imagens do projeto» de um processo de licenciamento automático.

1. Blender (Cycles): renders reais antes / depois a partir da geometria exata do processo, sobre o ortofotomapa oficial,
   com o sol na posição real; exporta o modelo 3D georreferenciado (.glb, .blend, georreferencia.json).
2. Acabamento fotográfico (opcional, por omissão ligado): cada render do Blender passa pela cascata de imagem do
   ConstruPilot (Nano Banana 3.1 → Nano Banana Pro → GPT Image 2 → Runway Gen-4) com a geometria e a câmara bloqueadas,
   para chegar à definição de uma fotografia. A versão Blender pura fica sempre guardada ao lado.

Coleções: urbanismo_blender (estado por processo) e urbanismo_blender_ficheiros (um documento por ficheiro, < 16 MB).
"""
from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from bson.binary import Binary

from engines.urbanismo_pt.auto import blender3d as B
from engines.urbanismo_pt.auto import pecas_auto as PA

log = logging.getLogger(__name__)
_TAREFAS: Dict[str, asyncio.Task] = {}
MIME = {"jpg": "image/jpeg", "png": "image/png", "glb": "model/gltf-binary", "blend": "application/x-blender",
        "json": "application/json"}
PRINCIPAL = ("drone", "rua", "aerea", "jardim")
_RANK = {"foto": 2, "blender": 1, "pc": 0}     # no PDF: acabamento fotográfico > Blender no servidor > rendu no PC
# dossier de licenciamento: o motor de maior qualidade primeiro, mesmo que demore (GPT Image 2 «high» ~2 min por vista)
MOTORES_DOSSIER = [m.strip() for m in os.environ.get("BLENDER_FOTO_MOTORES", "gpt_image_2,gemini_image3_pro,gen4_image,emergent").split(",") if m.strip()]      # a primeira vista acabada serve de referência de estilo às outras


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def prompt_foto(processo: Dict[str, Any], camara: str, estado: str) -> str:
    m = (processo.get("auto") or {}).get("materiais") or {}
    fach = PA.MATERIAIS_FACHADA.get(m.get("fachada"), "white render")
    cob = PA.MATERIAIS_COBERTURA.get(m.get("cobertura"), "red clay tiles")
    cx = PA.CAIXILHARIA.get(m.get("caixilharia"), "anthracite aluminium")
    vista = {"aerea": "high oblique aerial photograph", "drone": "low drone photograph from the street",
             "rua": "eye-level photograph taken from the street", "jardim": "eye-level photograph from the garden"}.get(camara, "photograph")
    comum = ("Keep the camera position, lens, framing, horizon, terrain levels, plot boundaries, roads and neighbouring "
             "buildings exactly as in the reference image. Ultra-detailed, tack-sharp, high dynamic range, natural colours, "
             "real textures, realistic vegetation (lawn, shrubs, native trees of the Minho region, northern Portugal), soft "
             "late-afternoon spring sunlight coming from the same direction as the shadows in the reference. ")
    if estado == "antes":
        return (f"Turn this 3D render into a {vista} of the CURRENT site, before any construction: an empty plot of land with "
                "natural grass and shrubs. Do NOT add any new house, garage or paving on the plot. " + comum +
                "Architectural photography for a building permit application (before / after comparison).")
    return (f"Turn this Blender render into a {vista} of the finished single-family house, for an architect's building permit "
            "dossier. The house geometry is FINAL and must stay 100% identical: same volumes, proportions, roof shape and pitch, "
            "number of storeys, every window and door in the same place and size, same garage and same paving layout. Do not "
            f"add or remove any window, storey, balcony, chimney or volume. Real materials: facade = {fach}; roof = {cob}; "
            f"window frames = {cx}; paving in local granite. " + comum)


async def _guardar(db, pid: str, uid: str, nome: str, data: bytes) -> None:
    ext = nome.rsplit(".", 1)[-1].lower()
    await db.urbanismo_blender_ficheiros.replace_one(
        {"processo_id": pid, "user_id": uid, "nome": nome},
        {"processo_id": pid, "user_id": uid, "nome": nome, "mime": MIME.get(ext, "application/octet-stream"),
         "bytes": len(data), "data": Binary(data), "created_at": _now()}, upsert=True)


async def ler_ficheiro(db, pid: str, uid: str, nome: str) -> Optional[Dict[str, Any]]:
    return await db.urbanismo_blender_ficheiros.find_one({"processo_id": pid, "user_id": uid, "nome": nome}, {"_id": 0})


async def estado(db, pid: str, uid: str) -> Dict[str, Any]:
    d = await db.urbanismo_blender.find_one({"processo_id": pid, "user_id": uid}, {"_id": 0})
    if not d:
        return {"estado": "nenhum", "blender_instalado": B.disponivel()}
    if d.get("estado") == "a_renderizar" and pid not in _TAREFAS:
        try:                                            # servidor reiniciado a meio: o trabalho já não existe
            ini = datetime.fromisoformat(d.get("updated_at") or d.get("created_at"))
            if (datetime.now(timezone.utc) - ini).total_seconds() > 300:
                d["estado"] = "interrompido"
        except Exception:  # noqa: BLE001
            pass
    d["blender_instalado"] = B.disponivel()
    return d


async def _passo(db, pid, uid, **campos):
    await db.urbanismo_blender.update_one({"processo_id": pid, "user_id": uid}, {"$set": {**campos, "updated_at": _now()},
                                          "$setOnInsert": {"created_at": _now()}}, upsert=True)


async def executar(db, pid: str, uid: str, qualidade: str = "normal", acabamento: bool = True) -> Dict[str, Any]:
    d = await db.urbanismo_processos.find_one({"processo_id": pid, "user_id": uid}, {"_id": 0})
    if not d or not d.get("auto"):
        await _passo(db, pid, uid, estado="erro", motivo="Processo não encontrado.")
        return {"ok": False}
    processo = {k: d.get(k) for k in ("auto", "volume", "terreno", "title")}
    await _passo(db, pid, uid, estado="a_renderizar", etapa="Blender: a construir a cena e a renderizar (Cycles)")
    r = await B.renderizar_async(processo, qualidade)
    if not r.get("ok"):
        await _passo(db, pid, uid, estado="erro", motivo=r.get("motivo"), log=(r.get("log") or "")[-1500:])
        return r
    for nome, data in r["ficheiros"].items():
        await _guardar(db, pid, uid, nome, data)
    man = r["manifesto"]
    imagens = [{**i, "versao": "blender"} for i in man["imagens"]]
    await _passo(db, pid, uid, imagens=imagens, manifesto={k: v for k, v in man.items() if k != "imagens"},
                 georef=r["georef"], sol=r["sol"], n_vizinhos=r.get("n_vizinhos"), segundos_blender=r["segundos"],
                 ficheiros=[n for n in r["ficheiros"] if not n.endswith(".jpg")],
                 etapa="Acabamento fotográfico (geometria bloqueada)" if acabamento else "Concluído")

    fotos: List[Dict[str, Any]] = []
    if acabamento:
        from engines import photoreal as PR
        bases = [i for i in man["imagens"] if i["camara"] != "topo"]
        ordem = sorted([i for i in bases if i["estado"] == "depois"], key=lambda i: PRINCIPAL.index(i["camara"]) if i["camara"] in PRINCIPAL else 9)
        ref = None

        async def acabar(i, style):
            try:
                res = await PR.render(r["ficheiros"][i["ficheiro"]], prompt_foto(processo, i["camara"], i["estado"]),
                                      style_ref=style, feature="licenciamento_blender_foto", session_id=pid,
                                      engines=MOTORES_DOSSIER, timeout=420.0)
            except Exception:  # noqa: BLE001
                res = None
            if not res:
                return None
            data, motor = res
            nome = "foto_" + i["ficheiro"]
            await _guardar(db, pid, uid, nome, data)
            return {**i, "ficheiro": nome, "versao": "foto", "motor_ia": motor, "base": i["ficheiro"]}, data
        if ordem:
            primeiro = await acabar(ordem[0], None)
            if primeiro:
                fotos.append(primeiro[0])
                ref = primeiro[1]
            outros = ordem[1:] + [i for i in bases if i["estado"] == "antes"]
            for x in await asyncio.gather(*(acabar(i, ref if i["estado"] == "depois" else None) for i in outros)):
                if x:
                    fotos.append(x[0])
    await _passo(db, pid, uid, estado="pronto", imagens=imagens + fotos, n_fotos=len(fotos), etapa="Concluído",
                 acabamento=acabamento, acabamento_falhou=bool(acabamento and not fotos))
    return {"ok": True, "imagens": len(imagens), "fotos": len(fotos)}


async def lancar(db, pid: str, uid: str, qualidade: str = "normal", acabamento: bool = True) -> Dict[str, Any]:
    """Arranca em segundo plano (um trabalho por processo de cada vez)."""
    t = _TAREFAS.get(pid)
    if t and not t.done():
        return {"ok": True, "estado": "a_renderizar", "ja_em_curso": True}
    if not B.disponivel():
        return {"ok": False, "estado": "indisponivel", "motivo": "O Blender não está instalado neste servidor."}
    await db.urbanismo_blender.replace_one(
        {"processo_id": pid, "user_id": uid},
        {"processo_id": pid, "user_id": uid, "estado": "a_renderizar", "qualidade": qualidade, "acabamento": acabamento,
         "etapa": "Na fila", "created_at": _now(), "updated_at": _now(), "imagens": []}, upsert=True)

    async def correr():
        try:
            await executar(db, pid, uid, qualidade, acabamento)
        except Exception as e:  # noqa: BLE001
            log.exception("blender job %s", pid)
            await _passo(db, pid, uid, estado="erro", motivo=f"{type(e).__name__}: {e}"[:300])
        finally:
            _TAREFAS.pop(pid, None)
    _TAREFAS[pid] = asyncio.create_task(correr())
    return {"ok": True, "estado": "a_renderizar"}


def auto_ativo() -> bool:
    if os.environ.get("PYTEST_CURRENT_TEST") and os.environ.get("BLENDER_AUTO") != "1":
        return False                                    # nos testes só quando pedido explicitamente
    return os.environ.get("BLENDER_AUTO", "1") != "0" and B.disponivel()


async def desenhos_para_pdf(db, pid: str, uid: str) -> List[Dict[str, Any]]:
    """Simulações para as peças desenhadas: a versão fotográfica de cada vista quando existe, senão a do Blender."""
    try:
        st = await db.urbanismo_blender.find_one({"processo_id": pid, "user_id": uid}, {"_id": 0, "imagens": 1})
    except Exception:  # noqa: BLE001 — as simulações são um anexo opcional: nunca impedem o PDF ou o ZIP
        log.warning("simulações Blender indisponíveis para %s", pid, exc_info=True)
        return []
    imgs = (st or {}).get("imagens") or []
    por = {}
    for i in imgs:
        k = (i["camara"], i["estado"])
        if k not in por or _RANK.get(i.get("versao"), 1) > _RANK.get(por[k].get("versao"), 1):
            por[k] = i
    ordem = sorted(por.values(), key=lambda i: ((PRINCIPAL + ("topo",)).index(i["camara"]) if i["camara"] in PRINCIPAL + ("topo",) else 9,
                                               0 if i["estado"] == "antes" else 1))
    out = []
    for n, i in enumerate(ordem, 1):
        f = await ler_ficheiro(db, pid, uid, i["ficheiro"])
        if not f:
            continue
        sufixo = " — situação existente" if i["estado"] == "antes" else " — proposta"
        orig = {"foto": " (render Blender + acabamento fotográfico)", "pc": " (render 3D no PC do utilizador, path tracing)"}.get(
            i.get("versao"), " (render Blender, Cycles)")
        out.append({"code": f"SIM-{n:02d}", "title": i["titulo"] + sufixo + orig, "filename": f"SIM-{n:02d}_{i['ficheiro']}",
                    "png": bytes(f["data"])})
    return out


# ------------------------------------------------------------------ rendu híbrido: cena no servidor, imagem no PC
# O servidor (sem GPU) só constrói a cena exata no Blender e exporta o .glb (segundos); o navegador do utilizador faz o
# path tracing com a placa gráfica do PC. Estado e ficheiros à parte (prefixo pc_) para nunca tocar no trabalho Cycles.
PC = "pc_"
PC_FICHEIROS = ("modelo.glb", "modelo_antes.glb", "georreferencia.json")
_TAREFAS_PC: Dict[str, asyncio.Task] = {}
CAMARAS_PC = {"aerea", "drone", "rua", "jardim", "topo"}


async def estado_pc(db, pid: str, uid: str) -> Dict[str, Any]:
    d = await db.urbanismo_blender_pc.find_one({"processo_id": pid, "user_id": uid}, {"_id": 0})
    if not d:
        return {"estado": "nenhum", "blender_instalado": B.disponivel()}
    if d.get("estado") == "a_preparar" and pid not in _TAREFAS_PC:
        d["estado"] = "interrompido"
    d["blender_instalado"] = B.disponivel()
    return d


async def executar_modelo(db, pid: str, uid: str) -> Dict[str, Any]:
    async def passo(**c):
        await db.urbanismo_blender_pc.update_one({"processo_id": pid, "user_id": uid}, {"$set": {**c, "updated_at": _now()}}, upsert=True)
    d = await db.urbanismo_processos.find_one({"processo_id": pid, "user_id": uid}, {"_id": 0})
    if not d or not d.get("auto"):
        await passo(estado="erro", motivo="Processo não encontrado.")
        return {"ok": False}
    processo = {k: d.get(k) for k in ("auto", "volume", "terreno", "title")}
    r = await B.renderizar_async(processo, "modelo")
    if not r.get("ok"):
        await passo(estado="erro", motivo=r.get("motivo"), log=(r.get("log") or "")[-1500:])
        return r
    guardados = []
    for nome in PC_FICHEIROS:
        if nome in r["ficheiros"]:
            await _guardar(db, pid, uid, PC + nome, r["ficheiros"][nome])
            guardados.append(PC + nome)
    if PC + "modelo.glb" not in guardados:
        await passo(estado="erro", motivo="O Blender não exportou o modelo 3D.")
        return {"ok": False}
    await passo(estado="pronto", ficheiros=guardados, georef=r["georef"], sol=r["sol"], segundos=r["segundos"],
                camaras=[{k: c.get(k) for k in ("id", "titulo", "pos", "alvo", "lente_mm", "ortografica", "escala", "norte", "so_depois")}
                         for c in json_camaras(r)])
    return {"ok": True}


def json_camaras(r: Dict[str, Any]) -> List[Dict[str, Any]]:
    import json
    try:
        return json.loads(r["ficheiros"]["georreferencia.json"]).get("camaras") or []
    except Exception:  # noqa: BLE001
        return []


async def lancar_modelo(db, pid: str, uid: str) -> Dict[str, Any]:
    t = _TAREFAS_PC.get(pid)
    if t and not t.done():
        return {"ok": True, "estado": "a_preparar", "ja_em_curso": True}
    if not B.disponivel():
        return {"ok": False, "estado": "indisponivel", "motivo": "O Blender não está instalado neste servidor."}
    await db.urbanismo_blender_pc.replace_one(
        {"processo_id": pid, "user_id": uid},
        {"processo_id": pid, "user_id": uid, "estado": "a_preparar", "created_at": _now(), "updated_at": _now()}, upsert=True)

    async def correr():
        try:
            await executar_modelo(db, pid, uid)
        except Exception as e:  # noqa: BLE001
            log.exception("blender modelo pc %s", pid)
            await db.urbanismo_blender_pc.update_one({"processo_id": pid, "user_id": uid},
                                                     {"$set": {"estado": "erro", "motivo": f"{type(e).__name__}: {e}"[:300]}})
        finally:
            _TAREFAS_PC.pop(pid, None)
    _TAREFAS_PC[pid] = asyncio.create_task(correr())
    return {"ok": True, "estado": "a_preparar"}


async def guardar_imagem_pc(db, pid: str, uid: str, camara: str, est: str, titulo: str, data: bytes, segundos: float = 0.0,
                            amostras: int = 0) -> Dict[str, Any]:
    """Imagem calculada no PC → guardada ao lado das do Blender (versão «pc») para o dossier e o PDF."""
    if camara not in CAMARAS_PC or est not in ("antes", "depois"):
        return {"ok": False, "motivo": "Vista inválida."}
    if not (data[:3] == b"\xff\xd8\xff" or data[:8] == b"\x89PNG\r\n\x1a\n") or len(data) > 15_000_000:
        return {"ok": False, "motivo": "Imagem inválida (JPEG ou PNG, até 15 MB)."}
    ext = "png" if data[:4] == b"\x89PNG" else "jpg"
    nome = f"{PC}{camara}_{est}.{ext}"
    await _guardar(db, pid, uid, nome, data)
    item = {"ficheiro": nome, "camara": camara, "titulo": (titulo or camara)[:120], "estado": est, "versao": "pc",
            "segundos": round(float(segundos or 0), 1), "amostras": int(amostras or 0)}
    q = {"processo_id": pid, "user_id": uid}
    if not await db.urbanismo_blender.find_one(q, {"_id": 1}):
        await db.urbanismo_blender.insert_one({**q, "estado": "pronto", "etapa": "Concluído (rendu no PC)", "imagens": [],
                                               "created_at": _now(), "updated_at": _now()})
    await db.urbanismo_blender.update_one(q, {"$pull": {"imagens": {"versao": "pc", "camara": camara, "estado": est}}})
    await db.urbanismo_blender.update_one(q, {"$push": {"imagens": item}, "$set": {"updated_at": _now()}})
    return {"ok": True, "imagem": item}
