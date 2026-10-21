"""Phase 4 tools: Autodesk Model Derivative extraction per plan and deterministic revision comparison."""
from engines.plan_identity import identify_document

AUTODESK_TOOLS = [
    {"type": "function", "name": "extract_autodesk_data", "strict": True,
     "description": "Extrai via Autodesk Model Derivative os objetos, camadas e propriedades REALMENTE disponíveis no ficheiro CAD/BIM de origem de uma planta (DWG/RVT/IFC). Uma tradução por ficheiro (em cache). Um DWG traduzido dá entidades por camada, não paredes identificadas.",
     "parameters": {"type": "object", "properties": {"plan_id": {"type": "string"}}, "required": ["plan_id"], "additionalProperties": False}},
    {"type": "function", "name": "compare_revisions", "strict": True,
     "description": "Compara dois documentos (plantas) pela identidade da legenda (índice, data de revisão, código, escala) e pelas suas camadas/objetos Autodesk se extraídos. Nunca soma quantidades de revisões diferentes; assinala quando as revisões são incompatíveis.",
     "parameters": {"type": "object", "properties": {"plan_id_a": {"type": "string"}, "plan_id_b": {"type": "string"}},
                    "required": ["plan_id_a", "plan_id_b"], "additionalProperties": False}},
]
AUTODESK_TOOL_NAMES = {t["name"] for t in AUTODESK_TOOLS}


def plan_text(plan: dict) -> str:
    parts = []
    for pg in plan.get("pages") or []:
        for blk in (pg.get("text_blocks") or []) if isinstance(pg, dict) else []:
            parts.append(blk.get("text") if isinstance(blk, dict) else str(blk))
    return " ".join(p for p in parts if p)[:80000]


def plan_words(plan: dict) -> list[tuple]:
    """Positioned text blocks as (x0, y0, x1, y1, text) so title-block rows split across cells can be rebuilt."""
    out = []
    for pg in plan.get("pages") or []:
        for blk in (pg.get("text_blocks") or []) if isinstance(pg, dict) else []:
            if isinstance(blk, dict) and blk.get("text") and blk.get("x") is not None and blk.get("y") is not None:
                out.append((blk["x"], blk["y"], blk["x"] + (blk.get("w") or 0), blk["y"] + (blk.get("h") or 0), blk["text"]))
    return out[:6000]


def _identity(plan: dict) -> dict:
    return identify_document(plan_text(plan), plan_words(plan))


def compare_revisions(plan_a: dict, plan_b: dict, md_a: dict | None, md_b: dict | None) -> dict:
    ia, ib = _identity(plan_a), _identity(plan_b)
    same_doc = bool(ia["document_code"] and ia["document_code"] == ib["document_code"])
    same_rev = same_doc and ia["revision_index"] == ib["revision_index"] and ia["revision_date"] == ib["revision_date"]
    layers_a = {name: n for name, n in (md_a or {}).get("views", [{}])[0].get("layers", [])} if md_a else {}
    layers_b = {name: n for name, n in (md_b or {}).get("views", [{}])[0].get("layers", [])} if md_b else {}
    layer_diff = [{"layer": k, "a": layers_a.get(k, 0), "b": layers_b.get(k, 0)} for k in sorted(set(layers_a) | set(layers_b)) if layers_a.get(k, 0) != layers_b.get(k, 0)]
    if same_rev:
        status, note = "same_revision", "Mesmo documento e mesmo índice: comparação sem objeto, quantidades acumuláveis apenas se forem páginas diferentes do mesmo documento."
    elif same_doc:
        status, note = "different_revisions", "Mesmo documento, índices diferentes: as quantidades e cotas NÃO devem ser somadas entre revisões; analisar as diferenças."
    else:
        status, note = "different_documents", "Documentos diferentes (códigos distintos ou legenda ilegível): não comparar como revisões."
    return {"status": status, "note": note, "a": {"plan_id": plan_a.get("plan_id"), "filename": plan_a.get("filename"), **{k: ia[k] for k in ("document_code", "revision_index", "revision_date", "declared_scale", "level")}},
            "b": {"plan_id": plan_b.get("plan_id"), "filename": plan_b.get("filename"), **{k: ib[k] for k in ("document_code", "revision_index", "revision_date", "declared_scale", "level")}},
            "layer_differences": layer_diff[:60], "autodesk_data": {"a": bool(md_a), "b": bool(md_b)},
            "scale_warning": None if ia["declared_scale"] == ib["declared_scale"] else "Escalas declaradas diferentes: calibrar cada vista separadamente antes de qualquer medição."}
