"""Outil Assistant BTP « check_plans_coherence » : contrôle archi ↔ BET calculé par engines.plan_coherence.

L'IA n'intervient que pour relever les chaînes de cotes d'un plan IMAGE (positions + valeurs) ; orientation, rapprochement,
écarts, contrôles internes et superposition sont calculés de façon déterministe."""
from __future__ import annotations

import asyncio
import base64
import hashlib
import io
from datetime import datetime, timezone

from engines import plan_coherence as pc

PLANS_COHERENCE_TOOL = {
    "type": "function", "name": "check_plans_coherence", "strict": True,
    "description": "CONTRÔLE DE COHÉRENCE PLAN ARCHI ↔ PLAN BET (coffrage / structure / plan d'exécution) d'un même niveau : lit les chaînes de "
                   "cotes de chaque plan avec leur ORIENTATION et leur POSITION, rapproche les travées équivalentes (jamais une cote horizontale "
                   "avec une verticale, jamais une cote de terrasse/abords avec le bâtiment), chiffre les écarts, contrôle chaque plan en interne "
                   "(cote écrite ≠ dessin, chaînes parallèles contradictoires, façade non parallèle) et produit une SUPERPOSITION calée sur les "
                   "axes (PNG + PDF, aucune image générée par IA). OBLIGATOIRE dès que l'utilisateur demande les incohérences / la comparaison / "
                   "la superposition entre un plan d'architecte et un plan BET. Identifiants doc_… ou plan_… ; level = niveau à comparer "
                   "(ex. « RDC », « R+1 ») pour choisir la bonne vue sur une planche BET multi-vues ; pages 0-based.",
    "parameters": {"type": "object", "properties": {
        "document_archi": {"type": "string"}, "document_bet": {"type": "string"},
        "level": {"type": "string", "description": "Niveau comparé (RDC, R+1, VS…) ; vide si inconnu"},
        "page_archi": {"type": "integer"}, "page_bet": {"type": "integer"}},
        "required": ["document_archi", "document_bet", "level", "page_archi", "page_bet"], "additionalProperties": False}}

INSTRUCTIONS = """
Comparaison plan d'architecte ↔ plan BET : appelle TOUJOURS check_plans_coherence (jamais compare_documents, jamais une lecture « à l'œil »,
jamais edit_image_from_photo ni un JPG create_downloadable_file pour annoter ou « mettre à jour » un plan). C'est vrai aussi pour une
relance (« mets à jour le tableau », « refais les schémas comparatifs », « corrige l'image ») et même si les plans ont été joints à un tour
précédent : relance check_plans_coherence avec leurs doc_id. Toute ancienne image ou ancien tableau de comparaison produit autrement dans
la conversation est obsolète et peut être faux : ne le reprends pas, ne le cite pas comme résultat. Présente ensuite : les écarts archi ↔ BET par travée (largeur puis profondeur), les
incohérences internes de chaque plan, les chaînes non comparées (terrasse, abords) en une ligne, et la superposition retournée (PNG/PDF).
Tu peux ajouter ce que tu VOIS sur la superposition (murs présents d'un seul côté, ouvertures, poteaux) en le marquant « observé sur la
superposition, à confirmer ». Ne recalcule et ne réinterprète aucune cote : les chiffres viennent de l'outil.
"""


def _to_png(raw: bytes) -> bytes:
    from PIL import Image
    with Image.open(io.BytesIO(raw)) as im:
        buf = io.BytesIO()
        im.convert("RGB").save(buf, "PNG")
        return buf.getvalue()


async def _vision_chains(png: bytes) -> tuple[dict | None, str]:
    """Relevé IA des chaînes de cotes d'un plan image (image ramenée à ≤ 1600 px ; coordonnées remises à l'échelle)."""
    from PIL import Image
    from engines.structuro_maison_extract import ask_vision
    with Image.open(io.BytesIO(png)) as im:
        w, h = im.size
        k = min(1.0, 1600 / max(w, h))
        small = im.convert("RGB").resize((int(w * k), int(h * k))) if k < 1 else im.convert("RGB")
        buf = io.BytesIO()
        small.save(buf, "PNG")
    data, model = await ask_vision(pc.VISION_PROMPT.format(w=small.width, h=small.height), [buf.getvalue()])
    if data and k < 1:
        for ch in data.get("chains") or []:
            ch["ticks_px"] = [[t[0] / k, t[1] / k] for t in ch.get("ticks_px") or [] if isinstance(t, (list, tuple)) and len(t) == 2]
    return data, model


async def prepare(src: dict, page: int, level: str | None, label: str) -> dict:
    """src = {pdf_bytes | image_b64, filename} (format de _compare_source)."""
    if src.get("pdf_bytes"):
        r = await asyncio.to_thread(pc.prepare_vector, src["pdf_bytes"], max(0, page), level, label)
        if r.get("ok"):
            return r
        png = r["png"]
        pre = [r["note"]]
    elif src.get("image_b64"):
        png = await asyncio.to_thread(_to_png, base64.b64decode(src["image_b64"]))
        pre = []
    else:
        return {"ok": False, "note": f"{label} : document illisible (ni PDF ni image)."}
    data, model = await _vision_chains(png)
    r = await asyncio.to_thread(pc.prepare_raster, png, data, label)
    r["notes"] = pre + r.get("notes", []) + ([f"Relevé des cotes de l'image : {model} (contrôlé par calcul)."] if model else [])
    return r


async def run(args: dict, user: dict, conv: dict, db, load_source) -> dict:
    uid = user["user_id"]
    if args["document_archi"] == args["document_bet"]:
        return {"ok": False, "error": "Les deux identifiants désignent le même document."}
    try:
        sa = await load_source(args["document_archi"], uid)
        sb = await load_source(args["document_bet"], uid)
    except PermissionError:
        return {"ok": False, "error": "Document inaccessible pour ce compte."}
    level = (args.get("level") or "").strip() or None
    a, b = await asyncio.gather(prepare(sa, args.get("page_archi") or 0, level, "Archi"),
                                prepare(sb, args.get("page_bet") or 0, level, "BET"))
    if not a.get("ok") or not b.get("ok"):
        return {"ok": False, "error": "Cotes illisibles : " + " ".join(x.get("note", "") for x in (a, b) if not x.get("ok")),
                "notes": a.get("notes", []) + b.get("notes", [])}
    title = f"Superposition {level or 'plan'} — archi × BET"
    res = await asyncio.to_thread(pc.finalize, a, b, title)
    out = {k: v for k, v in res.items() if k != "overlay_png"}
    out["files"] = {"archi": sa.get("filename"), "bet": sb.get("filename")}
    if res.get("overlay_png"):
        out.update(await _store(res["overlay_png"], title, res, user, conv, db))
    return out


async def _store(png: bytes, title: str, res: dict, user: dict, conv: dict, db) -> dict:
    from PIL import Image
    from engines.assistant_files import build_document_pdf, public_artifact
    uid, cid = user["user_id"], conv["conversation_id"]
    ident = "file_" + hashlib.sha256((str(conv.get("_quote_request_id")) + str(conv.get("_file_call_id", "")) + "coh").encode()).hexdigest()[:27]
    with Image.open(io.BytesIO(png)) as im:
        buf = io.BytesIO()
        im.convert("RGB").save(buf, "JPEG", quality=90)
        jpg = buf.getvalue()
    lines = [f"- [{f['statut']}] {f['detail']}" for f in res["findings"]]
    body = "\n".join(["# Constats"] + (lines or ["- Aucune incohérence de cotes sur les chaînes rapprochées."]) +
                     ["", "# Règles de lecture"] + [f"- {r}" for r in res["rules"]] +
                     ["", "Superposition calculée sur les axes communs (aucune image générée par IA)."])
    pdf = await asyncio.to_thread(build_document_pdf, title, body, [jpg])
    now = datetime.now(timezone.utc).isoformat()
    docs = []
    for suffix, fmt_, mime, data, fname in (("i", "png", "image/png", png, "superposition-archi-bet.png"),
                                            ("p", "pdf", "application/pdf", pdf, "controle-coherence-archi-bet.pdf")):
        aid = ident + suffix
        doc = {"artifact_id": aid, "user_id": uid, "conversation_id": cid, "request_id": conv.get("_quote_request_id"), "title": title,
               "body": body, "filename": fname, "format": fmt_, "mime": mime, "size": len(data), "data_b64": base64.b64encode(data).decode(),
               "source_artifact_ids": [], "created_at": now, "illustrative": False, "computed_overlay": True,
               "download": f"/assistant/artifacts/{aid}/content"}
        await db.assistant_artifacts.update_one({"artifact_id": aid, "user_id": uid}, {"$setOnInsert": doc}, upsert=True)
        docs.append(public_artifact(doc))
    return {"artifact": docs[0], "pdf_artifact": docs[1]}
