"""Outil Assistant BTP « generate_heat_pump_layout » : implantation PAC air-eau réversible (plancher chauffant-rafraîchissant +
ventilo-convecteurs plafond) dessinée sur les plans d'architecte, note PDF au nom de l'entreprise.

Les positions imposées par l'utilisateur (« mets le ballon dans l'entrée contre le mur de la cuisine ») sont mémorisées par
conversation (collection pac_layouts) : chaque nouvel appel repart de la dernière implantation validée."""
from __future__ import annotations

import asyncio
import base64
import hashlib
from datetime import datetime, timezone

from .plans import norm

EQUIPMENTS = ["module", "collecteur", "groupe_exterieur", "vc"]

PAC_LAYOUT_TOOL = {
    "type": "function", "name": "generate_heat_pump_layout", "strict": True,
    "description": "IMPLANTATION PAC AIR-EAU RÉVERSIBLE sur les plans d'architecte (DCE / PC, PDF vectoriel) : plancher chauffant-"
                   "rafraîchissant (boucles par pièce, collecteur par niveau, sonde de point de rosée), ventilo-convecteurs plafond en "
                   "eau froide (condensats, pompes de relevage), module hydraulique + ballon tampon, colonne montante, groupe extérieur. "
                   "Lit toutes les planches « Plan RDC / R+1 / R-1… » du document, dessine l'implantation SUR chaque plan (PNG) et "
                   "produit la note PDF au logo de l'entreprise. OBLIGATOIRE pour toute demande de PAC réversible / plancher chauffant "
                   "ou rafraîchissant / ventilo-convecteurs / clim par eau à implanter sur des plans, et pour DÉPLACER un équipement "
                   "(« mets le ballon dans l'entrée », « le groupe extérieur dans le patio contre le garage », « le collecteur sur le mur "
                   "de la cuisine », « 2 ventilos dans le séjour ») : relancer avec placements. document_id vide = document de "
                   "l'implantation précédente de la conversation.",
    "parameters": {"type": "object", "properties": {
        "document_id": {"type": "string", "description": "doc_… ou plan_… du DCE / PC (PDF) ; vide pour reprendre le précédent"},
        "placements": {"type": "array", "description": "positions imposées (s'ajoutent à celles déjà demandées dans la conversation)",
                       "items": {"type": "object", "properties": {
                           "equipment": {"type": "string", "enum": EQUIPMENTS,
                                         "description": "module = module hydraulique + ballon tampon ; collecteur = collecteur plancher "
                                                        "d'un niveau ; groupe_exterieur = unité extérieure ; vc = nombre de ventilo-convecteurs d'une pièce"},
                           "level": {"type": ["string", "null"], "description": "RDC, R+1… (obligatoire pour collecteur)"},
                           "room": {"type": "string", "description": "nom de la pièce tel qu'écrit sur le plan (Entrée, Garage, CB 1…). "
                                                                     "groupe_exterieur : pièce dont le mur extérieur reçoit l'unité"},
                           "near_room": {"type": ["string", "null"], "description": "contre le mur commun avec cette pièce (ex. Cuisine)"},
                           "side": {"type": ["string", "null"], "description": "nord / sud / est / ouest (haut / bas / droite / gauche du plan)"},
                           "count": {"type": ["integer", "null"], "description": "vc uniquement : nombre d'unités (0 = aucune)"}},
                           "required": ["equipment", "level", "room", "near_room", "side", "count"], "additionalProperties": False}},
        "reset_placements": {"type": "boolean", "description": "true = oublier les positions imposées précédemment"}},
        "required": ["document_id", "placements", "reset_placements"], "additionalProperties": False}}

INSTRUCTIONS = """
PAC air-eau réversible / plancher chauffant-rafraîchissant / ventilo-convecteurs sur des plans : appelle generate_heat_pump_layout avec
le doc_id du DCE ou du PC (PDF). Ne dessine jamais toi-même un schéma d'implantation (ni image IA, ni JPG) : l'outil lit les planches,
place les équipements, calcule les boucles et dessine sur les plans de l'architecte. Pour déplacer un équipement (demande écrite, ou
capture du plan annotée par l'utilisateur : flèche, cercle), traduis la demande en placements — pièce (nom exact du plan), mur commun
avec une autre pièce (near_room) ou côté — puis relance l'outil (document_id vide si c'est le même document). Présente ensuite en
quelques lignes : où sont le groupe extérieur, le module + ballon tampon et les collecteurs, le total de boucles et de ventilo-convecteurs
par niveau, puis les points à valider, et donne les fichiers (PDF + plans PNG). Ne recalcule aucune valeur : les chiffres viennent de
l'outil. Si l'outil signale une position impossible, dis-le simplement et propose une alternative.
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
        return {"ok": False, "error": "Joindre le DCE ou le PC (PDF vectoriel avec les plans d'étage) puis relancer."}
    if doc_id != state.get("document_id"):
        state = {}
    placements = [] if args.get("reset_placements") else list(state.get("placements") or [])
    placements = merge_placements(placements, args.get("placements") or [])
    try:
        src = await load_source(doc_id, uid)
    except PermissionError:
        return {"ok": False, "error": "Document inaccessible pour ce compte."}
    if not src.get("pdf_bytes"):
        return {"ok": False, "error": "Ce document n'est pas un PDF : joindre le DCE / PC en PDF (plans vectoriels)."}
    branding = None
    if branding_loader is not None:
        try:
            branding = await branding_loader(db, uid, user)
        except Exception:  # noqa: BLE001 — sans identité : ConstruPilot
            branding = None
    out = await asyncio.to_thread(report.run, src["pdf_bytes"], placements, branding, None, src.get("filename"), state.get("pages"))
    if not out.get("ok"):
        return {"ok": False, "error": out.get("error") or "Implantation impossible."}
    res = out["result"]
    now = datetime.now(timezone.utc).isoformat()
    await db.pac_layouts.update_one({"user_id": uid, "conversation_id": cid},
                                    {"$set": {"user_id": uid, "conversation_id": cid, "document_id": doc_id, "placements": placements,
                                              "pages": out["pages"], "updated_at": now}}, upsert=True)
    arts = await _store(out, user, conv, db, placements)
    summary = {n: {"boucles": res["levels"][n].get("collector_outlets", 0),
                   "surface_chauffee_m2": round(sum(x["area"] for x in res["levels"][n]["loops"]), 2),
                   "ventilo_convecteurs": [f"{v['id']} ({v['room']})" for v in res["levels"][n]["vc"]],
                   "equipements": [f"{e['kind']} : {e['room']}" for e in res["levels"][n]["equipment"]]}
               for n in res["heated_levels"]}
    return {"ok": True, "project": out["project"], "niveaux": summary, "decisions": res["decisions"], "points_a_valider": res["checks"],
            "positions_imposees": placements, "artifact": arts[0], "artifacts": arts,
            "pieces_lues": {n: [f"{r['name']} {r['area']} m² ({r['status']})" for r in res["levels"][n]["rooms"]] for n in res["order"]}}


async def _store(out: dict, user: dict, conv: dict, db, placements: list[dict]) -> list[dict]:
    from engines.assistant_files import public_artifact
    uid, cid = user["user_id"], conv["conversation_id"]
    seed = str(conv.get("_quote_request_id")) + str(conv.get("_file_call_id", "")) + repr(placements) + datetime.now(timezone.utc).isoformat()
    ident = "file_" + hashlib.sha256((seed + "pac").encode()).hexdigest()[:27]
    slug = "".join(ch if ch.isalnum() else "-" for ch in norm(out["project"]).split(" — ")[0])[:30].strip("-") or "projet"
    title = f"{out['project']} — PAC réversible (plancher + ventilo-convecteurs)"
    body = "\n".join(["# Implantation PAC air-eau réversible"] + [f"- {d}" for d in out["result"]["decisions"]] +
                     ["", "# Points à valider"] + [f"- {c}" for c in out["result"]["checks"]])
    files = [("p", "pdf", "application/pdf", out["pdf"], f"{slug}-pac-reversible-plancher-ventilo.pdf")]
    for i, (lvl, png) in enumerate(out["pngs"].items()):
        files.append((f"i{i}", "png", "image/png", png, f"{slug}-implantation-pac-{norm(lvl).replace('+', 'plus').replace(' ', '')}.png"))
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
