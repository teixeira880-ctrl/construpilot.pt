"""Phase 4 tools: Autodesk Model Derivative extraction per plan and deterministic revision comparison."""
from engines.plan_identity import identify_document

AUTODESK_TOOLS = [
    {"type": "function", "name": "extract_autodesk_data", "strict": True,
     "description": "Extrait via Autodesk Model Derivative les objets, calques et propriétés RÉELLEMENT disponibles dans le fichier CAO/BIM d'origine d'un plan "
                    "(DWG/RVT/IFC). Une traduction par fichier (mise en cache). Un DWG traduit donne des entités par calque, pas des murs identifiés.",
     "parameters": {"type": "object", "properties": {"plan_id": {"type": "string"}}, "required": ["plan_id"], "additionalProperties": False}},
    {"type": "function", "name": "compare_revisions", "strict": True,
     "description": "Compare deux documents (plans) par leur identité de cartouche (indice, date de révision, code, échelle) et leurs calques/objets Autodesk si extraits. "
                    "Ne somme jamais des quantités de révisions différentes ; signale quand les révisions sont incompatibles.",
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
        status, note = "same_revision", "Même document et même indice : comparaison sans objet, quantités cumulables uniquement s'il s'agit de pages différentes du même document."
    elif same_doc:
        status, note = "different_revisions", "Même document, indices différents : les quantités et cotes ne doivent PAS être additionnées entre révisions ; analyser les écarts."
    else:
        status, note = "different_documents", "Documents différents (codes distincts ou cartouche illisible) : ne pas comparer comme des révisions."
    return {"status": status, "note": note, "a": {"plan_id": plan_a.get("plan_id"), "filename": plan_a.get("filename"), **{k: ia[k] for k in ("document_code", "revision_index", "revision_date", "declared_scale", "level")}},
            "b": {"plan_id": plan_b.get("plan_id"), "filename": plan_b.get("filename"), **{k: ib[k] for k in ("document_code", "revision_index", "revision_date", "declared_scale", "level")}},
            "layer_differences": layer_diff[:60], "autodesk_data": {"a": bool(md_a), "b": bool(md_b)},
            "scale_warning": None if ia["declared_scale"] == ib["declared_scale"] else "Échelles déclarées différentes : calibrer chaque vue séparément avant toute mesure."}
