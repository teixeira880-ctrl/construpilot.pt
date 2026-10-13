"""Comparaison de documents (devis ↔ devis, devis ↔ plan) via la Responses API — sortie JSON stricte.

Le document est une donnée : aucun texte qu'il contient n'est une instruction. Pour un particulier, aucune donnée
d'entreprise n'entre dans le prompt et le ton reste explicatif (jamais « trop cher », « frauduleux »).
"""
from __future__ import annotations

import base64
import json
import os

from engines.openai_studies import MODEL_LIGHT, _client, _file_part, _log_usage, _respond, _upload_pdf

MODEL_COMPARE = os.environ.get("STUDIES_MODEL_COMPARE", MODEL_LIGHT)

_S = lambda: {"type": "string"}  # noqa: E731
_N = lambda: {"type": ["number", "null"]}  # noqa: E731
_ARR = lambda: {"type": "array", "items": {"type": "string"}}  # noqa: E731

DOC_SUMMARY = {"type": "object", "additionalProperties": False, "properties": {
    "title": _S(), "issuer": _S(), "date": _S(), "total_ht": _N(), "total_ttc": _N(), "vat_rate": _N(), "lines_count": {"type": "integer"},
    "scope_summary": _S()}, "required": ["title", "issuer", "date", "total_ht", "total_ttc", "vat_rate", "lines_count", "scope_summary"]}

COMPARE_SCHEMA = {"type": "object", "additionalProperties": False, "properties": {
    "comparison_type": {"type": "string", "enum": ["quote_vs_quote", "quote_vs_plan", "other"]},
    "summary": _S(),
    "document_a": DOC_SUMMARY, "document_b": DOC_SUMMARY,
    "line_matches": {"type": "array", "items": {"type": "object", "additionalProperties": False, "properties": {
        "topic": _S(), "designation_a": _S(), "designation_b": _S(), "unit": _S(), "qty_a": _N(), "qty_b": _N(),
        "unit_price_a": _N(), "unit_price_b": _N(), "total_a": _N(), "total_b": _N(), "delta_pct": _N(),
        "status": {"type": "string", "enum": ["identical", "different_quantity", "different_price", "different_scope", "only_a", "only_b", "to_confirm"]},
        "comment": _S()},
        "required": ["topic", "designation_a", "designation_b", "unit", "qty_a", "qty_b", "unit_price_a", "unit_price_b", "total_a", "total_b",
                     "delta_pct", "status", "comment"]}},
    "only_in_a": _ARR(), "only_in_b": _ARR(),
    "differences": {"type": "array", "items": {"type": "object", "additionalProperties": False, "properties": {
        "topic": _S(), "detail": _S(), "importance": {"type": "string", "enum": ["low", "medium", "high"]},
        "kind": {"type": "string", "enum": ["observed", "calculated", "deduced", "to_confirm"]}},
        "required": ["topic", "detail", "importance", "kind"]}},
    "questions_to_ask": _ARR(), "caveats": _ARR(), "confidence": {"type": "number"}},
    "required": ["comparison_type", "summary", "document_a", "document_b", "line_matches", "only_in_a", "only_in_b", "differences",
                 "questions_to_ask", "caveats", "confidence"]}

PROMPT_PRO = "És o comparador de documentos ConstruPilot para um PROFISSIONAL da construção (língua: {lang}). Compara rigorosamente o\nDOCUMENTO A e o DOCUMENTO B: aproxima os trabalhos equivalentes (mesma prestação, mesma unidade), regista as diferenças de quantidades,\nde preços unitários, de totais (delta_pct = (B − A) / A × 100 quando os dois valores existem), as prestações presentes num\nsó documento, as diferenças de âmbito, de opções, de IVA, de garantias, de prazos e de condições. Para um orçamento face a uma\nplanta: confronta as quantidades do orçamento com as áreas/comprimentos legíveis ou calculáveis na planta (indica observado / calculado /\ndeduzido / a confirmar). Nunca inventes: um valor ilegível fica null e o comentário indica-o. Estilo: direto, quantificado,\nprofissional. Foco pedido: {focus}"

PROMPT_INDIVIDUAL = "És o assistente ConstruPilot para um PARTICULAR (língua: {lang}). Compara o DOCUMENTO A e o DOCUMENTO B de forma\npedagógica e neutra: explica as diferenças de prestações, de quantidades, de materiais, de acabamentos, de garantias, de\nprazos, de IVA e de preços, definindo os termos técnicos. PROIBIDO: declarar que um orçamento é demasiado caro, fraudulento,\ndesonesto ou incorreto com base numa diferença de preço; dar uma classificação ou um «vencedor». Para cada diferença, propõe\nexplicações possíveis (materiais, acabamento, complexidade, mão de obra, localização, acesso, garantias, prazos) e perguntas\na fazer aos profissionais. Para um orçamento face a uma planta: verifica se as quantidades são coerentes com o que é legível na planta,\nassinalando observado / calculado / deduzido / a confirmar. Nunca inventes: um valor ilegível fica null. Foco: {focus}"


async def compare_documents(*, user_id: str, project_id: str | None, doc_a: dict, doc_b: dict, focus: str, individual: bool,
                            lang: str = "pt") -> dict:
    """doc = {label, filename, pdf_bytes|image_b64|text, extra_json}. Renvoie le JSON strict + métadonnées."""
    client = _client()
    uploaded: list[str] = []
    content: list[dict] = []
    try:
        for tag, d in (("A", doc_a), ("B", doc_b)):
            content.append({"type": "input_text", "text": f"=== DOCUMENT {tag} : {d.get('filename')} ({d.get('label')}) ==="})
            if d.get("pdf_bytes"):
                fid = await _upload_pdf(client, d["pdf_bytes"], d.get("filename") or f"document_{tag}.pdf")
                uploaded.append(fid)
                content.append(_file_part(fid))
            elif d.get("image_b64"):
                content.append({"type": "input_image", "image_url": f"data:image/png;base64,{d['image_b64']}", "detail": "high"})
            if d.get("text"):
                content.append({"type": "input_text", "text": f"Texto extraído do documento {tag} :\n{d['text'][:30000]}"})
            if d.get("extra_json"):
                content.append({"type": "input_text", "text": f"Dados ConstruPilot (cálculos exatos) do documento {tag} :\n{json.dumps(d['extra_json'], ensure_ascii=False)[:20000]}"})
        tpl = PROMPT_INDIVIDUAL if individual else PROMPT_PRO
        r = await _respond(client, MODEL_COMPARE, "high", tpl.format(lang="pt-PT" if lang == "pt" else "pt", focus=focus or "comparação completa"),
                           content, COMPARE_SCHEMA, "document_comparison")
        await _log_usage(user_id, project_id, "assistant_compare", MODEL_COMPARE, r.usage, None)
        data = json.loads(r.output_text)
    finally:
        for fid in uploaded:
            try:
                await client.files.delete(fid)
            except Exception:  # noqa: BLE001
                pass
    data["model"] = MODEL_COMPARE
    data["account_type"] = "individual" if individual else "professional"
    return data


def image_to_b64(data: bytes) -> str:
    return base64.b64encode(data).decode()
