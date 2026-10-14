"""Ferramenta do Assistente: dossier de execução estrutural (cofragem + armaduras) a partir
dos documentos anexados (projeto de licenciamento / plantas + estudo geotécnico).

Reutiliza o pipeline determinístico do Autopiloto BET (engines/structuro_autopilot.py):
leitura IA da geometria e do solo → modelo → descida de cargas → sapatas (só com solo lido) →
armaduras → medições → PDF A3 de cofragem/armaduras (engines/structuro_coffrage.py).
O resultado é um PRÉ-DIMENSIONAMENTO a validar por engenheiro — nunca um projeto de execução assinado.
"""
from __future__ import annotations

import asyncio
import base64
import hashlib
import logging
from datetime import datetime, timezone

from fastapi import HTTPException

from core.db import db
from engines.assistant_workspace import function

log = logging.getLogger("assistant.bet")

N = lambda t: {"type": [t, "null"]}  # noqa: E731

BET_TOOLS = [
    function(
        "generate_structural_execution_dossier",
        "Gera o DOSSIER DE EXECUÇÃO ESTRUTURAL pré-dimensionado (planos A3 de cofragem por piso, sapatas, vigas, "
        "pilares, lajes, mapa de armaduras, amarrações, nota de cálculo resumida e medições de betão/aço) a partir "
        "dos documentos ANEXADOS: projeto de licenciamento / plantas cotadas (geometry_document_ids) e estudo "
        "geotécnico (soil_document_ids). Motor determinístico NP EN 1990/1991/1992/1997 (Anexos Nacionais PT). "
        "Usar SEMPRE que o utilizador pedir planos de execução, cofragem, armaduras/ferragens, betão armado, "
        "'gros œuvre', 'ferraillage' ou 'faz os cálculos como um gabinete de estruturas'. Os overrides servem "
        "apenas para valores que o UTILIZADOR indicou explicitamente; caso contrário null.",
        {
            "geometry_document_ids": {"type": "array", "items": {"type": "string"}, "maxItems": 6},
            "soil_document_ids": {"type": "array", "items": {"type": "string"}, "maxItems": 3},
            "levels": N("integer"),
            "storey_height_m": N("number"),
            "bays_x_m": {"type": ["array", "null"], "items": {"type": "number"}, "maxItems": 12},
            "bays_y_m": {"type": ["array", "null"], "items": {"type": "number"}, "maxItems": 12},
            "structure": {"type": ["string", "null"], "description": "portique (pilares-vigas) ou voiles (paredes resistentes); null se não indicado"},
            "destination": {"type": ["string", "null"], "description": "habitacao, escritorios, comercio, estacionamento, industrial ou publico; null se não indicado"},
            "soil_q_els_kpa": N("number"),
        }),
]

BET_TOOL_NAMES = {t["name"] for t in BET_TOOLS}

BET_INSTRUCTIONS = (
    "\nPLANOS DE EXECUÇÃO / COFRAGEM / ARMADURAS: quando o utilizador pedir planos de execução estrutural, "
    "cofragem, armaduras (ferragens), 'gros œuvre' ou 'ferraillage' e houver plantas/projeto (e idealmente o "
    "estudo geotécnico) anexados, NÃO recuses e NÃO te limites a um esquema de princípio: chama "
    "generate_structural_execution_dossier com os document_id dos anexos (plantas/PC em geometry_document_ids, "
    "relatório geotécnico em soil_document_ids). Depois apresenta: o ficheiro PDF devolvido, o resumo (pisos, "
    "malha, elementos, betão m³, aço kg, sapatas), as incertezas de leitura e os avisos. Explica que é um "
    "pré-dimensionamento automático (Eurocódigos com Anexos Nacionais PT) a verificar e assinar por um "
    "engenheiro civil antes da obra, e que a ação sísmica (NP EN 1998-1) não está verificada. Se faltar o "
    "estudo geotécnico, as sapatas não são dimensionadas: diz isso e pede o relatório. Se a leitura da "
    "geometria tiver falhado, pede as cotas em falta (número de pisos, pé-direito, vãos entre alinhamentos) e "
    "volta a chamar a ferramenta com esses valores nos overrides.\n")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


async def _doc_images(doc_ids: list[str], uid: str, *, dpi: int, per_doc: int, cap: int,
                      keywords: tuple | None, allowed_doc) -> tuple[list[bytes], list[str]]:
    from engines import structuro_bet_ai as betai
    imgs: list[bytes] = []
    names: list[str] = []
    for did in doc_ids:
        d = await allowed_doc(did, uid)
        raw = base64.b64decode(d.get("data_b64") or "")
        mime = (d.get("mime") or d.get("content_type") or "").lower()
        names.append(d.get("filename") or did)
        if mime == "application/pdf" or raw[:4] == b"%PDF":
            imgs += await asyncio.to_thread(betai.render_doc_images, raw, dpi, per_doc, keywords)
        elif mime in betai.IMAGE_MIMES:
            imgs.append(raw)
        if len(imgs) >= cap:
            break
    return imgs[:cap], names


async def run_bet_tool(args: dict, user: dict, conv: dict, allowed_doc) -> dict:
    from engines import structuro_autopilot as ap
    from engines.structuro_coffrage import build_coffrage_pdf
    uid, cid = user["user_id"], conv["conversation_id"]
    geom_ids, soil_ids = args.get("geometry_document_ids") or [], args.get("soil_document_ids") or []
    if not geom_ids and not soil_ids:
        return {"ok": False, "error": "Anexe pelo menos o projeto/plantas (e de preferência o estudo geotécnico)."}

    geom, gnames = await _doc_images(geom_ids, uid, dpi=110, per_doc=8, cap=12,
                                     keywords=("planta", "corte", "alçado", "implantação", "piso", "cobertura",
                                               "plan", "coupe", "façade", "niveau", "escala", "1/100", "1/50"),
                                     allowed_doc=allowed_doc)
    soil, snames = await _doc_images(soil_ids, uid, dpi=90, per_doc=40, cap=40, keywords=None, allowed_doc=allowed_doc)
    inputs = await ap.extract_inputs(geom, soil)

    # Overrides explícitos do utilizador
    b = inputs.setdefault("building", {})
    if args.get("levels"):
        b["levels"] = int(args["levels"])
    if args.get("storey_height_m"):
        b["storey_height_m"] = float(args["storey_height_m"])
    if args.get("destination"):
        b["destination"] = args["destination"]
    if args.get("structure"):
        inputs.setdefault("system", {})["structure"] = args["structure"]
    if args.get("bays_x_m"):
        inputs.setdefault("grid", {})["bays_x_m"] = [float(x) for x in args["bays_x_m"]]
    if args.get("bays_y_m"):
        inputs.setdefault("grid", {})["bays_y_m"] = [float(x) for x in args["bays_y_m"]]
    if args.get("soil_q_els_kpa"):
        s = inputs.setdefault("soil", {})
        s["q_els_kpa"] = float(args["soil_q_els_kpa"])
        s["q_confirmed"] = True
    inputs = ap.normalize_inputs(inputs)

    try:
        out = await asyncio.to_thread(ap.build_and_compute, inputs)
    except ValueError as exc:
        return {"ok": False, "error": f"Modelo não calculável: {exc}", "inputs": inputs}
    if out["result"].get("status") == "blocked":
        return {"ok": False, "error": "O pré-modelo não é calculável automaticamente.",
                "issues": out["result"].get("issues"), "inputs": inputs,
                "incertitudes": inputs.get("incertitudes")}

    model, summary = out["model"], out["summary"]
    pdf = await asyncio.to_thread(build_coffrage_pdf, model, 1, model.get("title", "Autopiloto BET"),
                                  out["superstructure"], out["metre"], out["marks"], summary, out["soil"], inputs)
    if len(pdf) > 15 * 1024 * 1024:
        raise HTTPException(413, "Dossier demasiado volumoso.")

    digest = hashlib.sha256((conv.get("_quote_request_id", "") + str(conv.get("_file_call_id", "")) + "bet").encode()).hexdigest()[:28]
    ident = "file_" + digest
    title = f"Dossier de execução estrutural (pré-dimensionamento) — {model.get('title', 'Autopiloto BET')}"
    doc = {"artifact_id": ident, "user_id": uid, "conversation_id": cid, "request_id": conv.get("_quote_request_id"),
           "title": title, "body": "Dossier A3 de cofragem e armaduras gerado pelo Autopiloto BET.",
           "filename": "dossier-execucao-estrutural.pdf", "format": "pdf", "mime": "application/pdf", "size": len(pdf),
           "data_b64": base64.b64encode(pdf).decode(), "source_artifact_ids": [],
           "created_at": _now(), "illustrative": False, "bet_dossier": True,
           "download": f"/assistant/artifacts/{ident}/content"}
    await db.assistant_artifacts.update_one({"artifact_id": ident, "user_id": uid}, {"$setOnInsert": doc}, upsert=True)

    metre = out.get("metre") or {}
    artifact = {k: v for k, v in doc.items() if k not in ("data_b64", "body", "user_id")}
    return {
        "ok": True, "artifact": artifact,
        "summary": {
            "titulo": model.get("title"),
            "pisos": (inputs.get("building") or {}).get("levels"),
            "pe_direito_m": (inputs.get("building") or {}).get("storey_height_m"),
            "sistema": (inputs.get("system") or {}).get("structure"),
            "vaos_x_m": (inputs.get("grid") or {}).get("bays_x_m"),
            "vaos_y_m": (inputs.get("grid") or {}).get("bays_y_m"),
            "elementos": len(model.get("elements") or []),
            "betao_m3": (metre.get("concrete") or {}).get("total_m3"),
            "aco_kg_indicativo": (metre.get("steel") or {}).get("total_kg"),
            "nota_medicao": metre.get("note"),
            "solo_confirmado": bool(out["soil"].get("q_confirmed")),
            "sapatas": summary.get("footings"),
        },
        "documentos_lidos": {"geometria": gnames, "solo": snames},
        "incertezas_de_leitura": inputs.get("incertitudes") or [],
        "avisos": (summary.get("warnings") or []) + [
            "Pré-dimensionamento automático (NP EN 1990/1991/1992/1997, Anexos Nacionais PT) — a verificar e assinar por engenheiro civil antes da execução.",
            "Ação sísmica (NP EN 1998-1) não verificada.",
        ],
    }
