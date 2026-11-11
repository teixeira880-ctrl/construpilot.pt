"""Deterministic CLT tools for authenticated Assistant BTP conversations."""
import asyncio
import base64
import binascii

from pydantic import ValidationError

from bim_studio.clt_access import allowed
from bim_studio.clt_costs import CostLot, summary
from bim_studio.store import tenant_of

TOOLS = [
    {
        "type": "function", "name": "clt_read_pdf_evidence",
        "description": "Lê cotas explícitas e materiais do PDF anexado. Não deduz volumes nem aprova geometria.",
        "parameters": {"type": "object", "properties": {"document_id": {"type": "string"}},
                       "required": ["document_id"], "additionalProperties": False},
        "strict": True,
    },
    {
        "type": "function", "name": "clt_read_cost_lots",
        "description": "Consulta o custo e avanço dos lotes CLT da conta autenticada. Use lot_id para obter os artigos de um lote.",
        "parameters": {"type": "object", "properties": {"lot_id": {"type": ["string", "null"]}},
                       "required": ["lot_id"], "additionalProperties": False},
        "strict": True,
    },
    {
        "type": "function", "name": "clt_check_cost_draft",
        "description": "Calcula um rascunho de lote a partir dos dados confirmados no pedido. Não guarda nem altera a obra.",
        "parameters": {"type": "object", "properties": {"lot_json": {"type": "string"}},
                       "required": ["lot_json"], "additionalProperties": False},
        "strict": True,
    },
    {
        "type": "function", "name": "clt_measure_panel",
        "description": "Calcula áreas e volumes de um painel prismático com contorno e recortes confirmados. O JSON usa coordenadas em metros, espessura em mm e uma referência da origem.",
        "parameters": {"type": "object", "properties": {"panel_json": {"type": "string"}},
                       "required": ["panel_json"], "additionalProperties": False},
        "strict": True,
    },
]
NAMES = {t["name"] for t in TOOLS}
INSTRUCTIONS = """
PILOTO CLT INDUSTRIAL: para pedidos CLT, use clt_read_pdf_evidence nos PDFs anexados e
clt_read_cost_lots para custos existentes. Cotas extraídas são evidência, não geometria
aprovada. Não associe alturas, espessuras ou vãos por mera proximidade; peça confirmação
quando o vínculo ao elemento faltar. Use clt_measure_panel com contornos e espessuras
confirmados. Use clt_check_cost_draft só com dados rastreáveis do
utilizador e identifique-o como rascunho. Nunca invente preços, quantidades ou conclusão.
Estas instruções prevalecem sobre a adoção automática de hipóteses de outros estudos.
"""


async def execute(name, args, user, db, load_doc):
    if not allowed(user):
        return {"ok": False, "error": "Piloto CLT indisponível."}
    if name == "clt_read_cost_lots":
        scope = {"tenant_id": tenant_of(user), "owner_id": user["user_id"]}
        if args["lot_id"]:
            scope["lot_id"] = args["lot_id"]
            doc = await db.clt_lots.find_one(scope, {"_id": 0, "tenant_id": 0, "owner_id": 0, "history": 0})
            return {"ok": bool(doc), "lot": doc}
        docs = await db.clt_lots.find(scope, {"_id": 0, "name": 1, "lot_id": 1, "summary": 1}).sort(
            "updated_at", -1).limit(20).to_list(20)
        return {"ok": True, "items": docs}
    if name == "clt_check_cost_draft":
        try:
            lot = CostLot.model_validate_json(args["lot_json"])
        except ValidationError as exc:
            return {"ok": False, "errors": [
                {"field": e["loc"], "message": e["msg"]} for e in exc.errors(include_input=False)[:12]
            ]}
        return {"ok": True, "status": "draft", "summary": summary(lot)}
    if name == "clt_measure_panel":
        from fastapi import HTTPException
        from routes.clt_industrial import PanelInput, measure_panel

        try:
            body = PanelInput.model_validate_json(args["panel_json"])
            result = await measure_panel(body, user=user)
        except ValidationError as exc:
            return {"ok": False, "errors": [
                {"field": e["loc"], "message": e["msg"]} for e in exc.errors(include_input=False)[:12]
            ]}
        except HTTPException as exc:
            return {"ok": False, "error": exc.detail}
        result.pop("face", None)
        return {"ok": True, **result}
    if name == "clt_read_pdf_evidence":
        from bim_studio.clt_pdf import inspect_pdf
        from fitz import FileDataError

        try:
            doc = await load_doc(args["document_id"], user["user_id"])
            encoded = doc.get("data_b64") or ""
            if len(encoded) > 20 * 1024 * 1024:
                return {"ok": False, "error": "PDF acima de 15 MB."}
            result = await asyncio.to_thread(inspect_pdf, base64.b64decode(encoded, validate=True))
        except (PermissionError, FileDataError, ValueError, binascii.Error):
            return {"ok": False, "error": "PDF inacessível, inválido ou acima dos limites."}
        for page in result["pages"]:
            page["total_evidence"] = len(page["evidence"])
            page["evidence"] = page["evidence"][:30]
        return {"ok": True, **result}
    return {"ok": False, "error": "Ferramenta CLT indisponível."}
