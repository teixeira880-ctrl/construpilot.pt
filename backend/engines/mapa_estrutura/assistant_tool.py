"""Ferramenta do Assistente : MAPA DE QUANTIDADES DA ESTRUTURA medido numa planta estrutural em PDF.

medir_planta_estrutural → lê as plantas (PDF vetorial exportado do CAD), mede pilares, paredes, núcleos, lajes (maciças e
aligeiradas) e vigas, e devolve o resumo, os pressupostos, as perguntas e dois ficheiros : o mapa em Excel (com fórmulas) e o
desenho de controlo em PDF. Determinístico (sem IA) : as mesmas plantas dão sempre as mesmas quantidades."""
from __future__ import annotations

import asyncio
import base64
import hashlib
import logging
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from . import controlo, excel, leitura, medicao, vetores

log = logging.getLogger(__name__)
MAX_ARTIFACT = 15 * 1024 * 1024
MAX_PAGINAS = 12
MIME = {"pdf": "application/pdf", "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"}

TOOLS = [
    {"type": "function", "name": "medir_planta_estrutural", "strict": False,
     "description": (
         "MAPA DE QUANTIDADES DA ESTRUTURA a partir de PLANTAS ESTRUTURAIS em PDF (plantas de estrutura / cofragem / betão armado exportadas do CAD, "
         "com pilares P…, paredes Par…, núcleos Nb…, vigas V…, lajes maciças ou aligeiradas). Mede diretamente no desenho, sem IA : secção de cada "
         "pilar/parede/núcleo, altura livre entre lajes (caixas de nível Zsup / e), área das lajes, moldes de aligeiramento contados um a um, vãos "
         "livres e larguras das vigas. Devolve betão (m³), cofragem (m²), moldes (un) e aço estimado (kg), os pressupostos, as perguntas a fazer "
         "ao utilizador e dois ficheiros : Excel com fórmulas e PDF de controlo com o que foi medido pintado sobre a planta. "
         "Usar SEMPRE que pedem o mapa de quantidades / medições / quantidades de betão de uma planta ESTRUTURAL em PDF. "
         "Não serve para plantas de arquitetura (usar generate_multifamily_building_study ou generate_full_bet_study) nem para DWG/DXF "
         "(usar medir_camadas_cad). Demora 5 a 30 s."),
     "parameters": {"type": "object", "properties": {
         "document_ids": {"type": "array", "items": {"type": "string"}, "description": "doc_… ou plan_… das plantas estruturais em PDF"},
         "escala": {"type": "integer", "description": "Denominador da escala (100 para 1/100). Omitir para ler a escala escrita no desenho."},
         "cota_base_m": {"type": "number", "description": "Cota de arranque dos pilares e paredes (topo das fundações ou do piso inferior), se o utilizador a indicar."},
         "altura_vigas_m": {"type": "number", "description": "Altura das vigas sem secção escrita no desenho, se o utilizador a indicar."}},
         "required": ["document_ids"], "additionalProperties": False}},
]
TOOL_NAMES = {t["name"] for t in TOOLS}
TOOL_STATUS = {"medir_planta_estrutural": "A medir a planta estrutural (pilares, paredes, lajes, vigas)…"}
INSTRUCTIONS = (
    "\n\nMAPA DE QUANTIDADES DE UMA PLANTA ESTRUTURAL (medir_planta_estrutural) : quando o utilizador anexa uma planta de ESTRUTURA em PDF e pede "
    "o mapa de quantidades, as medições ou o betão, chama medir_planta_estrutural com os documentos, sem pedir mais nada antes : a ferramenta lê a "
    "escala e as cotas no desenho. Nunca respondas que não consegues medir um PDF sem a teres chamado. Depois : 1) apresenta o quadro do resumo "
    "(betão por tipo de elemento, cofragem, moldes, aço estimado) tal como vem, sem recalcular ; 2) lista os PRESSUPOSTOS e faz as PERGUNTAS "
    "devolvidas, tal como estão ; 3) diz o que NÃO está incluído ; 4) os ficheiros (Excel e desenho de controlo) aparecem como botões de descarga : "
    "não escrevas links e convida a conferir o desenho de controlo. Se o utilizador responder às perguntas (cota de arranque, altura das vigas, "
    "escala), volta a chamar a ferramenta com esses valores. Se a ferramenta devolver ok = false, transmite o motivo e o que falta (por exemplo, "
    "PDF digitalizado em imagem : pedir o PDF exportado do CAD ou o DWG). O aço é sempre uma estimativa enquanto não houver desenhos de armaduras. "
    "É uma medição a validar pelo projetista.")


def _now():
    return datetime.now(timezone.utc).isoformat()


def medir(docs: list, escala=None, cota_base=None, h_vigas=None, out_dir=None) -> dict:
    """Medição completa (síncrona) de uma lista [(nome, bytes PDF)]. Devolve o modelo ; se out_dir for dado, escreve o Excel e o PDF."""
    leituras, textos, avisos, n_pag = [], [], [], 0
    for nome, data in docs:
        try:
            total = vetores.n_paginas(data)
        except Exception as exc:  # noqa: BLE001
            avisos.append(f"{nome} : PDF ilegível ({type(exc).__name__}).")
            continue
        for pg in range(total):
            if n_pag >= MAX_PAGINAS:
                avisos.append(f"Só as primeiras {MAX_PAGINAS} páginas foram lidas.")
                break
            n_pag += 1
            folha = vetores.ler(data, pg)
            lt = leitura.ler_folha(folha, escala)
            textos.append(folha.texto)
            if lt.get("ok"):
                leituras.append(lt)
            elif lt.get("erro") in ("escala", "raster") or total == 1:
                avisos += [f"{nome}, página {pg + 1} : {a}" for a in lt.get("avisos", [])]
    if not leituras:
        return {"ok": False, "avisos": avisos or ["Nenhuma planta estrutural legível nos documentos."], "perguntas": [], "pressupostos": []}
    modelo = medicao.consolidar(leituras, cota_base=cota_base, h_vigas=h_vigas, textos="\n".join(textos))
    modelo["avisos"] = list(dict.fromkeys(avisos + modelo.get("avisos", [])))
    if modelo.get("ok") and out_dir:
        out = Path(out_dir)
        out.mkdir(parents=True, exist_ok=True)
        titulo = Path(docs[0][0]).stem[:60]
        plantas = [p for lt in leituras for p in lt["plantas"]]
        modelo["files"] = {"xlsx": excel.gerar(modelo, str(out / "Mapa_quantidades_estrutura.xlsx"), titulo),
                           "controlo": controlo.gerar_pdf(plantas, modelo, str(out / "Controlo_medicao_estrutura.pdf"), titulo)}
    return modelo


async def _store(db, uid, cid, request_id, kind, path: Path, title):
    fmt = "xlsx" if path.suffix == ".xlsx" else "pdf"
    data = path.read_bytes()
    if len(data) > MAX_ARTIFACT:
        raise ValueError(f"{path.name} : {len(data)} bytes")
    aid = "file_" + hashlib.sha256((request_id + kind + path.name).encode()).hexdigest()[:28]
    doc = {"artifact_id": aid, "user_id": uid, "conversation_id": cid, "request_id": request_id, "title": title, "body": "",
           "filename": f"ConstruPilot_{path.name}", "format": fmt, "kind": kind, "mime": MIME[fmt], "size": len(data),
           "data_b64": base64.b64encode(data).decode(), "source_artifact_ids": [], "created_at": _now(), "illustrative": False,
           "download": f"/assistant/artifacts/{aid}/content"}
    await db.assistant_artifacts.update_one({"artifact_id": aid, "user_id": uid}, {"$setOnInsert": doc}, upsert=True)
    return {k: doc[k] for k in ("artifact_id", "title", "filename", "format", "kind", "mime", "size", "download")}


def _publico(modelo: dict) -> dict:
    """O que o Assistente recebe : resumo e listas curtas (o pormenor está no Excel)."""
    out = {"ok": True, "escala": f"1/{modelo.get('escala')}", "resumo": modelo["resumo"],
           "niveis": [{"nome": n["nome"], "zsup": n["zsup"], "e": n["e"], "altura_livre": n["h_livre"]} for n in modelo["niveis"]],
           "lajes": [{k: lj[k] for k in ("nivel", "area", "aberturas", "fora_do_perimetro", "moldes", "betao")} for lj in modelo["lajes"]],
           "pressupostos": modelo["pressupostos"], "perguntas": modelo["perguntas"], "avisos": modelo["avisos"][:20],
           "nao_incluido": modelo.get("fora_do_ambito", []),
           "nota": "Medição determinística sobre o PDF. Apresentar o resumo tal como está, os pressupostos e as perguntas. A validar pelo projetista."}
    return out


async def execute(name: str, args: dict, user: dict, conv: dict, db, doc_loader=None) -> dict:
    uid, cid = user["user_id"], conv.get("conversation_id")
    ids = [d for d in args.get("document_ids") or [] if d]
    if not ids:
        return {"ok": False, "error": "Junte a planta estrutural em PDF."}
    try:
        if doc_loader is None:
            from engines.bet_core.assistant_tool import _load_assistant_docs as doc_loader
        docs = await doc_loader(db, ids, uid)
    except (PermissionError, ValueError) as exc:
        return {"ok": False, "error": str(exc)}
    esc = args.get("escala") or None
    request_id = hashlib.sha256(("".join(ids) + str(esc) + str(args.get("cota_base_m")) + str(args.get("altura_vigas_m"))).encode()).hexdigest()[:16]
    try:
        with tempfile.TemporaryDirectory() as tmp:
            modelo = await asyncio.to_thread(medir, docs, esc, args.get("cota_base_m"), args.get("altura_vigas_m"), tmp)
            if not modelo.get("ok"):
                return {"ok": False, "error": " ".join(modelo.get("avisos") or ["Planta não legível."]),
                        "o_que_falta": "PDF vetorial exportado do CAD com as secções a cheio, as etiquetas (P, Par, V) e a escala ; ou o DWG/DXF."}
            arts = [await _store(db, uid, cid, request_id, "mapa_estrutura_xlsx", Path(modelo["files"]["xlsx"]), "Mapa de quantidades da estrutura (Excel)"),
                    await _store(db, uid, cid, request_id, "mapa_estrutura_controlo", Path(modelo["files"]["controlo"]), "Desenho de controlo da medição (PDF)")]
    except Exception as exc:  # noqa: BLE001
        log.exception("medir_planta_estrutural failed")
        return {"ok": False, "error": f"Medição impossível — {type(exc).__name__}: {str(exc)[:200]}"}
    return {**_publico(modelo), "artifacts": arts}
