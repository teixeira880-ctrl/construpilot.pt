"""Ferramenta do Assistente BTP « generate_heat_pump_layout » : implantação de bomba de calor ar-água reversível (piso radiante
de aquecimento e arrefecimento + ventiloconvectores de teto) desenhada sobre as plantas do arquiteto, nota PDF em nome da empresa.

As posições impostas pelo utilizador (« põe o depósito no hall contra a parede da cozinha ») ficam memorizadas por conversa
(coleção pac_layouts) : cada nova chamada parte da última implantação validada."""
from __future__ import annotations

import asyncio
import base64
import hashlib
from datetime import datetime, timezone

from .plans import norm

EQUIPMENTS = ["module", "collecteur", "groupe_exterieur", "vc"]

PAC_LAYOUT_TOOL = {
    "type": "function", "name": "generate_heat_pump_layout", "strict": True,
    "description": "IMPLANTAÇÃO DE BOMBA DE CALOR AR-ÁGUA REVERSÍVEL sobre as plantas do arquiteto (projeto de arquitetura / licenciamento, "
                   "PDF vetorial) : piso radiante de aquecimento e arrefecimento (circuitos por compartimento, coletor por piso, sonda de "
                   "ponto de orvalho), ventiloconvectores de teto em água fria (condensados, bombas de condensados), módulo hidráulico + "
                   "depósito de inércia, coluna montante, unidade exterior. Lê todas as plantas « R/C / Piso 1 / Cave… » do documento, "
                   "desenha a implantação SOBRE cada planta (PNG) e produz a nota PDF com o logótipo da empresa. OBRIGATÓRIO para qualquer "
                   "pedido de bomba de calor reversível / piso radiante / ventiloconvectores / climatização por água a implantar em plantas, e "
                   "para DESLOCAR um equipamento (« põe o depósito no hall », « a unidade exterior no pátio contra a garagem », « o coletor na "
                   "parede da cozinha », « 2 ventiloconvectores na sala ») : voltar a chamar com placements. document_id vazio = documento "
                   "da implantação anterior da conversa.",
    "parameters": {"type": "object", "properties": {
        "document_id": {"type": "string", "description": "doc_… ou plan_… do projeto (PDF) ; vazio para retomar o anterior"},
        "placements": {"type": "array", "description": "posições impostas (somam-se às já pedidas na conversa)",
                       "items": {"type": "object", "properties": {
                           "equipment": {"type": "string", "enum": EQUIPMENTS,
                                         "description": "module = módulo hidráulico + depósito de inércia ; collecteur = coletor do piso "
                                                        "radiante de um piso ; groupe_exterieur = unidade exterior ; vc = número de ventiloconvectores de um compartimento"},
                           "level": {"type": ["string", "null"], "description": "R/C, Piso 1… (obrigatório para collecteur)"},
                           "room": {"type": "string", "description": "nome do compartimento tal como escrito na planta (Hall, Garagem, Quarto 1…). "
                                                                     "groupe_exterieur : compartimento cuja parede exterior recebe a unidade"},
                           "near_room": {"type": ["string", "null"], "description": "contra a parede comum com este compartimento (ex. Cozinha)"},
                           "side": {"type": ["string", "null"], "description": "norte / sul / este / oeste (cima / baixo / direita / esquerda da planta)"},
                           "count": {"type": ["integer", "null"], "description": "só vc : número de unidades (0 = nenhuma)"}},
                           "required": ["equipment", "level", "room", "near_room", "side", "count"], "additionalProperties": False}},
        "reset_placements": {"type": "boolean", "description": "true = esquecer as posições impostas anteriormente"}},
        "required": ["document_id", "placements", "reset_placements"], "additionalProperties": False}}

INSTRUCTIONS = """
Bomba de calor ar-água reversível / piso radiante (aquecimento e arrefecimento) / ventiloconvectores em plantas : chama
generate_heat_pump_layout com o doc_id do projeto de arquitetura (PDF). Nunca desenhes tu próprio um esquema de implantação (nem imagem IA,
nem JPG) : a ferramenta lê as plantas, coloca os equipamentos, calcula os circuitos e desenha sobre as plantas do arquiteto. Para deslocar
um equipamento (pedido escrito, ou captura da planta anotada pelo utilizador : seta, círculo), traduz o pedido em placements —
compartimento (nome exato da planta), parede comum com outro compartimento (near_room) ou lado — e volta a chamar a ferramenta
(document_id vazio se for o mesmo documento). Apresenta depois em poucas linhas : onde ficam a unidade exterior, o módulo + depósito de
inércia e os coletores, o total de circuitos e de ventiloconvectores por piso, os pontos a validar, e entrega os ficheiros (PDF + plantas
PNG). Não recalcules nenhum valor : os números vêm da ferramenta. Se a ferramenta indicar uma posição impossível, di-lo simplesmente e
propõe uma alternativa.
"""


def _key(p: dict) -> str:
    eq = p.get("equipment")
    if eq == "collecteur":
        return f"collecteur:{norm(p.get('level') or '')}"
    if eq == "vc":
        return f"vc:{norm(p.get('level') or '')}:{norm(p.get('room') or '')}"
    return eq or ""


def merge_placements(old: list[dict], new: list[dict]) -> list[dict]:
    out = {_key(p): p for p in old or []}
    for p in new or []:
        if p.get("equipment") in EQUIPMENTS and p.get("room"):
            out[_key(p)] = {k: p.get(k) for k in ("equipment", "level", "room", "near_room", "side", "count")}
    return list(out.values())


async def run(args: dict, user: dict, conv: dict, db, load_source, branding_loader=None) -> dict:
    from . import report
    uid, cid = user["user_id"], conv["conversation_id"]
    state = await db.pac_layouts.find_one({"user_id": uid, "conversation_id": cid}, {"_id": 0}) or {}
    doc_id = (args.get("document_id") or "").strip() or state.get("document_id")
    if not doc_id:
        return {"ok": False, "error": "Anexar o projeto de arquitetura (PDF vetorial com as plantas dos pisos) e voltar a pedir."}
    if doc_id != state.get("document_id"):
        state = {}
    placements = [] if args.get("reset_placements") else list(state.get("placements") or [])
    placements = merge_placements(placements, args.get("placements") or [])
    try:
        src = await load_source(doc_id, uid)
    except PermissionError:
        return {"ok": False, "error": "Documento inacessível para esta conta."}
    if not src.get("pdf_bytes"):
        return {"ok": False, "error": "Este documento não é um PDF : anexar o projeto em PDF (plantas vetoriais)."}
    branding = None
    if branding_loader is not None:
        try:
            branding = await branding_loader(db, uid, user)
        except Exception:  # noqa: BLE001 — sans identité : ConstruPilot
            branding = None
    out = await asyncio.to_thread(report.run, src["pdf_bytes"], placements, branding, None, src.get("filename"), state.get("pages"))
    if not out.get("ok"):
        return {"ok": False, "error": out.get("error") or "Implantação impossível."}
    res = out["result"]
    now = datetime.now(timezone.utc).isoformat()
    await db.pac_layouts.update_one({"user_id": uid, "conversation_id": cid},
                                    {"$set": {"user_id": uid, "conversation_id": cid, "document_id": doc_id, "placements": placements,
                                              "pages": out["pages"], "updated_at": now}}, upsert=True)
    arts = await _store(out, user, conv, db, placements)
    summary = {n: {"circuitos": res["levels"][n].get("collector_outlets", 0),
                   "area_aquecida_m2": round(sum(x["area"] for x in res["levels"][n]["loops"]), 2),
                   "ventiloconvectores": [f"{v['id']} ({v['room']})" for v in res["levels"][n]["vc"]],
                   "equipamentos": [f"{e['kind']} : {e['room']}" for e in res["levels"][n]["equipment"]]}
               for n in res["heated_levels"]}
    return {"ok": True, "project": out["project"], "pisos": summary, "decisoes": res["decisions"], "pontos_a_validar": res["checks"],
            "posicoes_impostas": placements, "artifact": arts[0], "artifacts": arts,
            "compartimentos_lidos": {n: [f"{r['name']} {r['area']} m² ({r['status']})" for r in res["levels"][n]["rooms"]] for n in res["order"]}}


async def _store(out: dict, user: dict, conv: dict, db, placements: list[dict]) -> list[dict]:
    from engines.assistant_files import public_artifact
    uid, cid = user["user_id"], conv["conversation_id"]
    seed = str(conv.get("_quote_request_id")) + str(conv.get("_file_call_id", "")) + repr(placements) + datetime.now(timezone.utc).isoformat()
    ident = "file_" + hashlib.sha256((seed + "pac").encode()).hexdigest()[:27]
    slug = "".join(ch if ch.isalnum() else "-" for ch in norm(out["project"]).split(" — ")[0])[:30].strip("-") or "projeto"
    title = f"{out['project']} — bomba de calor reversível (piso radiante + ventiloconvectores)"
    body = "\n".join(["# Implantação de bomba de calor ar-água reversível"] + [f"- {d}" for d in out["result"]["decisions"]] +
                     ["", "# Pontos a validar"] + [f"- {c}" for c in out["result"]["checks"]])
    files = [("p", "pdf", "application/pdf", out["pdf"], f"{slug}-bomba-calor-reversivel-piso-radiante.pdf")]
    for i, (lvl, png) in enumerate(out["pngs"].items()):
        files.append((f"i{i}", "png", "image/png", png, f"{slug}-implantacao-bomba-calor-{norm(lvl).replace('+', 'plus').replace('/', '').replace(' ', '')}.png"))
    docs = []
    for suffix, fmt_, mime, data, fname in files:
        aid = ident + suffix
        doc = {"artifact_id": aid, "user_id": uid, "conversation_id": cid, "request_id": conv.get("_quote_request_id"), "title": title,
               "body": body, "filename": fname, "format": fmt_, "mime": mime, "size": len(data),
               "data_b64": base64.b64encode(data).decode(), "source_artifact_ids": [], "created_at": datetime.now(timezone.utc).isoformat(),
               "illustrative": False, "computed_overlay": True, "download": f"/assistant/artifacts/{aid}/content"}
        await db.assistant_artifacts.update_one({"artifact_id": aid, "user_id": uid}, {"$setOnInsert": doc}, upsert=True)
        docs.append(public_artifact(doc))
    return docs
