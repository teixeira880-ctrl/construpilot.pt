"""Ferramentas do Assistente — estudo estrutural de moradia/pequeno edifício a partir dos anexos.

1) read_building_geometry: lê (IA visão) o projeto de licenciamento + estudo geotécnico anexados e
   devolve a geometria estruturada + incertezas, guardada com um geometry_id → o assistente MOSTRA-A ao
   utilizador para validação (ecrã de validação = a conversa).
2) generate_structural_execution_dossier: com o geometry_id (+ correções do utilizador em JSON) calcula
   (engines/structuro_house.py) e gera o PDF: nota de cálculo A4 + desenhos A3 (lajes com armaduras,
   fundações, pormenores: cintas, pilaretes, lintéis, muro de cave, escadas) + medições.
Resultado = PRÉ-DIMENSIONAMENTO a verificar e assinar por engenheiro civil.
"""
from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import logging
import uuid
from datetime import datetime, timezone

from core.db import db
from engines.assistant_workspace import function

log = logging.getLogger("assistant.bet")

BET_TOOLS = [
    function(
        "read_building_geometry",
        "PASSO 1 do estudo estrutural: lê com IA as peças do projeto de licenciamento / plantas cotadas "
        "(geometry_document_ids) e o estudo geotécnico (soil_document_ids) ANEXADOS e devolve a geometria "
        "estrutural (dimensões, pisos, pé-direito, paredes resistentes, aberturas, caixa de escada, cave, "
        "cobertura, tensão do solo) com um geometry_id. Usar quando o utilizador pedir planos de execução, "
        "cofragem, armaduras/ferragens, betão armado, 'gros œuvre', 'ferraillage' ou um cálculo de estruturas.",
        {"geometry_document_ids": {"type": "array", "items": {"type": "string"}, "maxItems": 6},
         "soil_document_ids": {"type": "array", "items": {"type": "string"}, "maxItems": 3}}),
    function(
        "generate_structural_execution_dossier",
        "PASSO 2: calcula a estrutura (lajes em 2 direções, descida de cargas, alvenaria NP EN 1996-3, sapatas, "
        "lintéis, cintas/pilaretes, muros de cave, escadas) e gera o PDF do dossier: nota de cálculo A4 + desenhos A3 "
        "de cofragem/armaduras por laje, fundações e pormenores + medições de betão e aço. geometry_id vem do passo 1. "
        "corrections_json = JSON (string) só com os valores que o UTILIZADOR corrigiu ou confirmou, nas mesmas chaves "
        "da geometria (ex.: '{\"outer_L_m\": 11.2, \"levels\": [...], \"soil\": {\"q_els_kpa\": 200, \"confirmed\": true}}'); "
        "'{}' se nada a corrigir.",
        {"geometry_id": {"type": "string"}, "corrections_json": {"type": "string", "maxLength": 20000}}),
]
BET_TOOL_NAMES = {t["name"] for t in BET_TOOLS}

BET_INSTRUCTIONS = (
    "\nESTUDO ESTRUTURAL / PLANOS DE EXECUÇÃO (cofragem, armaduras, 'gros œuvre', 'ferraillage'): NÃO recuses e NÃO te "
    "limites a um esquema de princípio. Com o projeto/plantas (e de preferência o estudo geotécnico) anexados:\n"
    "1) chama read_building_geometry com os document_id (plantas/PC → geometry_document_ids; geotecnia → soil_document_ids);\n"
    "2) mostra ao utilizador, numa tabela curta, a geometria lida (dimensões, pisos e pé-direito, utilização, paredes "
    "resistentes interiores, aberturas, escada, cave, cobertura, q_ELS do solo) e as incertezas; pede para confirmar "
    "ou corrigir — se o utilizador já pediu para avançar sem validação, ou responder «ok/confirmo», segue;\n"
    "3) chama generate_structural_execution_dossier com o geometry_id e as correções em corrections_json;\n"
    "4) apresenta o PDF devolvido, o resumo (espessuras de laje, armaduras principais, sapatas, lintéis, betão m³, aço kg) "
    "e os avisos. Diz sempre que é um pré-dimensionamento automático (Eurocódigos, Anexos Nacionais PT) a verificar e "
    "assinar por engenheiro civil, e que a ação sísmica (NP EN 1998-1) não está verificada. Sem estudo geotécnico as "
    "sapatas não são dimensionadas: pede o relatório ou a tensão admissível.\n")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


async def _doc_images(doc_ids, uid, *, dpi, per_doc, cap, keywords, allowed_doc):
    from engines import structuro_bet_ai as betai
    imgs, names = [], []
    for did in doc_ids:
        d = await allowed_doc(did, uid)
        raw = base64.b64decode(d.get("data_b64") or "")
        mime = (d.get("mime") or "").lower()
        names.append(d.get("filename") or did)
        if mime == "application/pdf" or raw[:4] == b"%PDF":
            imgs += await asyncio.to_thread(betai.render_doc_images, raw, dpi, per_doc, keywords)
        elif mime in betai.IMAGE_MIMES:
            imgs.append(raw)
        if len(imgs) >= cap:
            break
    return imgs[:cap], names


async def read_geometry(args: dict, user: dict, conv: dict, allowed_doc) -> dict:
    from engines import structuro_house as H
    from engines.structuro_house_extract import extract
    uid = user["user_id"]
    gids, sids = args.get("geometry_document_ids") or [], args.get("soil_document_ids") or []
    if not gids:
        return {"ok": False, "error": "Anexe as peças desenhadas do projeto (plantas, cortes, alçados)."}
    geom, gnames = await _doc_images(gids, uid, dpi=90, per_doc=6, cap=8,
                                     keywords=("planta", "corte", "alçado", "implantação", "piso", "cobertura", "escala",
                                               "plan", "coupe", "façade", "niveau", "1/100", "1/50"), allowed_doc=allowed_doc)
    soil, snames = await _doc_images(sids, uid, dpi=90, per_doc=18, cap=18,
                                     keywords=("tensão admissível", "tensao admissivel", "capacidade de carga", "q_els", "qels",
                                               "kpa", "fundações", "fundacoes", "conclus", "recomenda", "sondagem", "spt",
                                               "contrainte", "portance", "fondation"), allowed_doc=allowed_doc)
    ex = await extract(geom, soil)
    geometry = H.normalize(ex["geometry"])
    gid = "geo_" + uuid.uuid4().hex[:12]
    await db.bet_geometries.insert_one({"geometry_id": gid, "user_id": uid, "conversation_id": conv.get("conversation_id"),
                                        "raw": ex["geometry"], "geometry": geometry, "incertezas": ex["incertezas"],
                                        "documents": {"geometria": gnames, "solo": snames}, "created_at": _now()})
    read_keys = set(ex["geometry"].keys())
    return {"ok": True, "geometry_id": gid, "geometry": geometry,
            "valores_por_defeito": sorted(k for k in ("outer_L_m", "outer_W_m", "wall_thickness_m", "levels", "roof",
                                                       "basement", "stair", "soil") if k not in read_keys),
            "incertezas": ex["incertezas"], "documentos_lidos": {"geometria": gnames, "solo": snames},
            "proximo_passo": "Mostrar ao utilizador para validação e depois chamar generate_structural_execution_dossier."}


async def generate(args: dict, user: dict, conv: dict) -> dict:
    from engines import structuro_house as H
    from engines.structuro_house_pdf import build_pdf
    uid, cid = user["user_id"], conv["conversation_id"]
    rec = await db.bet_geometries.find_one({"geometry_id": args["geometry_id"], "user_id": uid}, {"_id": 0})
    if not rec:
        return {"ok": False, "error": "geometry_id desconhecido — chame primeiro read_building_geometry."}
    try:
        corr = json.loads(args.get("corrections_json") or "{}") or {}
        if not isinstance(corr, dict):
            raise ValueError
    except ValueError:
        return {"ok": False, "error": "corrections_json inválido (deve ser um objeto JSON)."}
    if isinstance(corr.get("soil"), dict) and corr["soil"].get("q_els_kpa") and "confirmed" not in corr["soil"]:
        corr["soil"]["confirmed"] = True          # valor indicado pelo utilizador
    geometry = H.merge(rec["geometry"], corr)
    r = await asyncio.to_thread(H.compute, geometry)
    project = geometry.get("name") or "Moradia"
    pdf = await asyncio.to_thread(build_pdf, r, project)
    await db.bet_geometries.update_one({"geometry_id": args["geometry_id"], "user_id": uid},
                                       {"$set": {"geometry": r["geometry"], "computed_at": _now()}})
    digest = hashlib.sha256((str(conv.get("_quote_request_id", "")) + str(conv.get("_file_call_id", "")) + args["geometry_id"]).encode()).hexdigest()[:28]
    ident = "file_" + digest
    doc = {"artifact_id": ident, "user_id": uid, "conversation_id": cid, "request_id": conv.get("_quote_request_id"),
           "title": f"Dossier estrutural (pré-dimensionamento) — {project}",
           "body": "Nota de cálculo A4 + desenhos A3 de cofragem/armaduras, fundações e pormenores.",
           "filename": "dossier-estrutural.pdf", "format": "pdf", "mime": "application/pdf", "size": len(pdf),
           "data_b64": base64.b64encode(pdf).decode(), "source_artifact_ids": [], "created_at": _now(),
           "illustrative": False, "bet_dossier": True, "download": f"/assistant/artifacts/{ident}/content"}
    await db.assistant_artifacts.update_one({"artifact_id": ident, "user_id": uid}, {"$setOnInsert": doc}, upsert=True)
    artifact = {k: v for k, v in doc.items() if k not in ("data_b64", "body", "user_id")}
    q = r["quantities"]
    return {
        "ok": True, "artifact": artifact,
        "resumo": {
            "lajes": [{"laje": s["name"], "espessura_m": s["h"],
                       "armaduras": sorted({f"{d['mesh_short']['label']} / {d['mesh_long']['label']}" for d in s["panels"]})}
                      for s in r["slabs"]],
            "sapatas": {k: f"b={v['b_m']} h={v['h_m']} {v['transv']}" for k, v in r["footings"].items()} or "não dimensionadas (sem q_ELS confirmado)",
            "alvenaria": {k: v["choice"] for k, v in r["walls_check"].items()},
            "lintéis": [f"{li['rep']} {li.get('level')}/{li.get('facade')} vão {li['clear']} m: "
                        + (f"{li['b']}×{li['h']} {li['bot']} + {li['stirrups']}" if li.get("ok") else "viga a dimensionar") for li in r["lintels"]],
            "escadas": [f"lanço {s['lanco']}: {s.get('risers')}×{s.get('riser_mm')} mm, cobertor {s.get('giron_mm')} mm, {s.get('main', {}).get('label')}"
                        for s in r["stairs"] if not s.get("error")],
            "betao_m3": q["concrete_m3"], "aco_kg": q["steel_kg"], "racio_kg_m3": q["ratio_kg_m3"],
            "paginas": "nota A4 + " + str(len(r["slabs"]) + 2) + " folhas A3",
        },
        "avisos": r["warnings"],
    }


async def run_bet_tool(name: str, args: dict, user: dict, conv: dict, allowed_doc) -> dict:
    if name == "read_building_geometry":
        return await read_geometry(args, user, conv, allowed_doc)
    return await generate(args, user, conv)
