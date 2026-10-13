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

PROMPT_PRO = """Tu es le comparateur de documents ConstruPilot pour un PROFESSIONNEL du BTP (langue : {lang}). Compare rigoureusement le
DOCUMENT A et le DOCUMENT B : rapproche les ouvrages équivalents (même prestation, même unité), relève les écarts de quantités,
de prix unitaires, de totaux (delta_pct = (B − A) / A × 100 quand les deux valeurs existent), les prestations présentes dans un
seul document, les différences de périmètre, d'options, de TVA, de garanties, de délais et de conditions. Pour un devis face à un
plan : confronte les quantités du devis aux surfaces/longueurs lisibles ou calculables sur le plan (indique observé / calculé /
déduit / à confirmer). Jamais d'invention : une valeur illisible reste null et le commentaire l'indique. Style : direct, chiffré,
professionnel. Focus demandé : {focus}"""

PROMPT_INDIVIDUAL = """Tu es l'assistant ConstruPilot pour un PARTICULIER (langue : {lang}). Compare le DOCUMENT A et le DOCUMENT B de façon
pédagogique et neutre : explique les différences de prestations, de quantités, de matériaux, de finitions, de garanties, de
délais, de TVA et de prix, en définissant les termes techniques. INTERDIT : déclarer qu'un devis est trop cher, frauduleux,
malhonnête ou incorrect sur la base d'un écart de prix ; donner un classement ou un « gagnant ». Pour chaque écart, propose des
explications possibles (matériaux, finition, complexité, main-d'œuvre, localisation, accès, garanties, délais) et des questions
à poser aux artisans. Pour un devis face à un plan : vérifie si les quantités sont cohérentes avec ce qui est lisible sur le plan,
en signalant observé / calculé / déduit / à confirmer. Jamais d'invention : une valeur illisible reste null. Focus : {focus}"""


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
                content.append({"type": "input_text", "text": f"Texte extrait du document {tag} :\n{d['text'][:30000]}"})
            if d.get("extra_json"):
                content.append({"type": "input_text", "text": f"Données ConstruPilot (calculs exacts) du document {tag} :\n"
                                                              f"{json.dumps(d['extra_json'], ensure_ascii=False)[:20000]}"})
        tpl = PROMPT_INDIVIDUAL if individual else PROMPT_PRO
        r = await _respond(client, MODEL_COMPARE, "high", tpl.format(lang="pt-PT" if lang == "pt" else "pt", focus=focus or "comparaison complète"),
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
