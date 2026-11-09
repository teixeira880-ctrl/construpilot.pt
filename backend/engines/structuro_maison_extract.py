"""Lecture IA (vision) d'un permis de construire (PC/DP) et d'une étude géotechnique G2 → géométrie structure
au format de engines/structuro_maison.compute().

Principes (corrige l'ancien auto-pilote qui inventait une trame 2 × 4 m) :
- on ne devine JAMAIS une dimension : valeur illisible → null + incertitude, et l'Assistant demande à l'utilisateur ;
- 2 lectures en PARALLÈLE avec le meilleur modèle vision disponible, chacune avec timeout :
    (a) PLANS de niveaux (cotes, murs porteurs, position des baies le long de chaque façade, cage d'escalier),
    (b) FAÇADES + COUPES + NOTICE (niveaux, égout/faîtage, hauteurs et allèges des baies, type de toiture) ;
  puis fusion déterministe ;
- G2 : on lit d'abord la COUCHE TEXTE (q ELS/q ELU, type de fondation, niveau d'assise) par expressions régulières,
  la vision n'est utilisée qu'en secours (G2 scannée).
"""
from __future__ import annotations

import asyncio
import base64
import io
import json
import logging
import os
import re

log = logging.getLogger("structuro.maison.extract")

MAX_SIDE = 2000
TIMEOUT_S = 150
# Modèles vision, du meilleur au repli (noms emergentintegrations ; le premier qui répond est retenu)
VISION_MODELS = [("gemini", "gemini-3.1-pro-preview"), ("anthropic", "claude-sonnet-4-6"), ("openai", "gpt-6-astra")]

CONVENTION = (
    "CONVENTION D'AXES (obligatoire) : L = grand côté du bâtiment (le long de X), W = petit côté (le long de Y). "
    "« frente » = mur du grand côté à y = 0 ; « tras » = mur du grand côté à y = W ; « esquerda » = mur du petit côté à x = 0 ; "
    "« direita » = mur du petit côté à x = L. Choisis l'orientation pour que la façade sur rue soit esquerda ou frente. "
    "x0_m d'une baie = distance (m) depuis l'extrémité du mur la plus proche de l'origine (x = 0 pour frente/tras, y = 0 pour "
    "esquerda/direita) jusqu'au tableau de la baie. Lis les cotes écrites (chaînes de cotes) ; n'estime jamais à l'œil.")

PLANS_PROMPT = (
    "Tu es ingénieur structure. Voici les PLANS DE NIVEAUX cotés d'un permis de construire (sous-sol, RDC, étages, combles). "
    + CONVENTION +
    " Renvoie UNIQUEMENT ce JSON :\n"
    '{"name": "adresse ou nom du projet ou null", "outer_L_m": nombre, "outer_W_m": nombre,\n'
    ' "wall_thickness_m": épaisseur totale des murs extérieurs cotée (m),\n'
    ' "structural_wall_m": épaisseur porteuse si distinguée (bloc 20 → 0.20) sinon null,\n'
    ' "interior_walls_x": [positions x (m) des murs intérieurs PORTEURS continus parallèles à Y (épaisseur >= 15 cm, présents à tous les niveaux)],\n'
    ' "interior_walls_y": [positions y des murs intérieurs porteurs parallèles à X],\n'
    ' "party_walls": ["frente"|"tras"|"esquerda"|"direita" — murs mitoyens/en limite séparative],\n'
    ' "level_names": ["Sous-sol", "RDC", "R+1", "Combles", ...] (de bas en haut),\n'
    ' "basement_present": true/false,\n'
    ' "garage_level": "nom du niveau qui contient un garage" ou null,\n'
    ' "openings": [{"level": nom, "facade": "frente|tras|esquerda|direita", "x0_m": nombre, "width_m": nombre, '
    '"label": "porte de garage|porte d\'entrée|fenêtre|baie vitrée|châssis fixe", "kind": "baie"|"lucarne"|"fenetre_toit"}],\n'
    ' "stair": {"present": bool, "x0_m": nombre, "y0_m": nombre, "cage_length_m": nombre, "cage_width_m": nombre} ,\n'
    ' "incertitudes": ["..."]}\n'
    "Les cloisons de 5 à 10 cm ne sont PAS porteuses. Toutes les baies des murs extérieurs, à tous les niveaux, avec leur x0_m et width_m lus "
    "sur les cotes. Valeur non cotée → null et une incertitude. "
    "lucarne = ouvrage maçonné ou charpenté avec jouées verticales qui dépasse du versant (visible en façade au-dessus de l'égout) ; "
    "fenêtre de toit (type Velux) = châssis dans le plan du versant, sans jouées → kind = fenetre_toit. "
    "Réponds en JSON strict, sans texte autour.")

ELEV_PROMPT = (
    "Tu es ingénieur structure. Voici les FAÇADES, COUPES et la NOTICE d'un permis de construire. " + CONVENTION +
    " Renvoie UNIQUEMENT ce JSON :\n"
    '{"levels": [{"name": nom, "floor_level_m": cote du plancher fini par rapport au RDC (RDC = 0), '
    '"use": "habitation|garage|commerce|bureaux|combles"}] (de bas en haut, sous-sol inclus avec une cote négative),\n'
    ' "eaves_level_m": cote de l\'égout, "ridge_level_m": cote du faîtage (null si toiture-terrasse),\n'
    ' "roof_type": "inclinee"|"terrasse", "roof_bearing_walls": "long"|"short" (murs qui portent la charpente = murs gouttereaux ; '
    '"short" si les versants descendent vers les petits côtés esquerda/direita),\n'
    ' "roof_structure": "fermettes|charpente traditionnelle|dalle" ,\n'
    ' "attic_floor_slab": true/false (plancher BA sous les combles / au niveau des combles),\n'
    ' "openings": [{"level": nom, "facade": "frente|tras|esquerda|direita", "x0_m": nombre ou null, "width_m": nombre, '
    '"height_m": hauteur de la baie, "sill_m": hauteur d\'allège depuis le plancher fini, "label": texte, "kind": "baie"|"lucarne"|"fenetre_toit"}],\n'
    ' "materials": "texte court (maçonnerie blocs béton 20, enduit, isolation...)",\n'
    ' "incertitudes": ["..."]}\n'
    "Lis les cotes de niveau écrites (NGF ou relatives) ; les lucarnes dans les versants ont kind = lucarne. "
    "lucarne = ouvrage maçonné ou charpenté avec jouées verticales qui dépasse du versant (visible en façade au-dessus de l'égout) ; "
    "fenêtre de toit (type Velux) = châssis dans le plan du versant, sans jouées → kind = fenetre_toit. JSON strict.")

G2_PROMPT = (
    "Voici des pages d'une étude géotechnique (G2 AVP/PRO). Renvoie UNIQUEMENT : "
    '{"q_els_kpa": nombre ou null, "q_elu_kpa": nombre ou null, "foundation_type": "filante|isolee|radier|pieux|null", '
    '"embedment_m": profondeur d\'assise sous le terrain naturel (m) ou null, "soil_layer": "couche d\'ancrage", '
    '"water": "niveau d\'eau / nappe (texte court)", "incertitudes": ["..."]}. Convertis MPa → kPa (×1000) et t/m² → kPa (×10).')


# ------------------------------------------------------------------ rendu des pages
def _shrink(png: bytes) -> bytes:
    try:
        from PIL import Image
        im = Image.open(io.BytesIO(png))
        if max(im.size) <= MAX_SIDE:
            return png
        im.thumbnail((MAX_SIDE, MAX_SIDE))
        out = io.BytesIO()
        im.convert("RGB").save(out, format="PNG", optimize=True)
        return out.getvalue()
    except Exception:  # noqa: BLE001
        return png


def classify_pages(pdf: bytes) -> dict:
    """Classe les pages d'un PC par la couche texte : plans / façades-coupes / autres."""
    import fitz
    doc = fitz.open(stream=pdf, filetype="pdf")
    plans, elev, notice = [], [], []
    try:
        for i in range(doc.page_count):
            t = (doc[i].get_text() or "").lower()
            if any(k in t for k in ("façade", "facade", "elevation", "élévation")):
                elev.append(i)
            elif "coupe" in t and not any(k in t for k in ("m²", "m2", "chambre", "séjour", "sejour", "cuisine")):
                elev.append(i)
            elif any(k in t for k in ("notice", "descriptive")):
                notice.append(i)
            else:
                # score « plan de niveau » : surfaces de pièces et noms de pièces (évite situation / plan de masse)
                score = sum(t.count(k) for k in ("m²", "m2", "chambre", "séjour", "sejour", "cuisine", "sdb", "wc", "garage",
                                                 "dégt", "degt", "salon", "bureau", "cellier", "buanderie"))
                if any(k in t for k in ("plan de masse", "plan de situation", "cadastr")):
                    score = 0
                if score >= 2:
                    plans.append((score, i))
        plans = [i for _, i in sorted(sorted(plans, reverse=True)[:6], key=lambda x: x[1])]
        if not plans and not elev:                        # PC scanné sans texte : tout est candidat
            plans = list(range(min(doc.page_count, 6)))
            elev = list(range(min(doc.page_count, 10)))
        return {"plans": plans, "elev": (elev + notice[:1])[:6], "count": doc.page_count}
    finally:
        doc.close()


def render(pdf: bytes, pages: list[int], dpi: int = 110) -> list[bytes]:
    import fitz
    doc = fitz.open(stream=pdf, filetype="pdf")
    try:
        return [_shrink(doc[i].get_pixmap(dpi=dpi).tobytes("png")) for i in pages if 0 <= i < doc.page_count]
    finally:
        doc.close()


# ------------------------------------------------------------------ appel IA
def _json(txt: str) -> dict | None:
    t = (txt or "").strip()
    if t.startswith("```"):
        t = t.split("\n", 1)[1] if "\n" in t else t[3:]
        t = t.rsplit("```", 1)[0]
    m = re.search(r"\{.*\}", t, re.DOTALL)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except json.JSONDecodeError:
        return None


async def ask_vision(prompt: str, images: list[bytes]) -> tuple[dict | None, str]:
    """Essaie les modèles vision dans l'ordre ; renvoie (json, modèle utilisé)."""
    if not images:
        return None, ""
    key = os.environ.get("EMERGENT_LLM_KEY")
    if not key:
        return None, ""
    from emergentintegrations.llm.chat import ImageContent, LlmChat, UserMessage
    contents = [ImageContent(image_base64=base64.b64encode(im).decode("ascii")) for im in images]
    last_err = ""
    for provider, model in VISION_MODELS:
        try:
            chat = LlmChat(api_key=key, session_id=f"maison-{os.urandom(4).hex()}",
                           system_message="Tu lis des plans d'architecte avec la rigueur d'un ingénieur structure. JSON strict uniquement.")
            chat = chat.with_model(provider, model)
            resp = await asyncio.wait_for(chat.send_message(UserMessage(text=prompt, file_contents=contents)), timeout=TIMEOUT_S)
            data = _json(resp if isinstance(resp, str) else str(resp))
            if data:
                return data, f"{provider}/{model}"
            last_err = "réponse non JSON"
        except Exception as e:  # noqa: BLE001
            last_err = str(e)[:160]
            log.warning("vision %s/%s : %s", provider, model, last_err)
    log.warning("lecture vision impossible : %s", last_err)
    return None, ""


# ------------------------------------------------------------------ G2 (texte d'abord)
_NUM = r"(\d+(?:[.,]\d+)?)"


def g2_from_text(pdf: bytes) -> dict:
    import fitz
    doc = fitz.open(stream=pdf, filetype="pdf")
    try:
        txt = "\n".join(doc[i].get_text() or "" for i in range(doc.page_count))
    finally:
        doc.close()
    flat = re.sub(r"\s+", " ", txt)
    out: dict = {"source_text": bool(flat.strip())}

    def to_kpa(val: str, unit: str) -> float:
        v = float(val.replace(",", "."))
        u = unit.lower()
        return v * 1000 if "mpa" in u else v * 10 if "t/m" in u else v * 100 if "bar" in u else v

    m = re.search(r"Q\s*_?\s*ELS\s*=?\s*" + _NUM + r"\s*(MPa|kPa|t/m²|t/m2|bars?)", flat, re.I)
    if m:
        out["q_els_kpa"] = round(to_kpa(m.group(1), m.group(2)), 0)
    m = re.search(r"Q\s*_?\s*ELU\s*=?\s*" + _NUM + r"\s*(MPa|kPa|t/m²|t/m2|bars?)", flat, re.I)
    if m:
        out["q_elu_kpa"] = round(to_kpa(m.group(1), m.group(2)), 0)
    if re.search(r"semelles? filantes?", flat, re.I):
        out["foundation_type"] = "filante"
    elif re.search(r"radier", flat, re.I):
        out["foundation_type"] = "radier"
    elif re.search(r"pieux|micropieux", flat, re.I):
        out["foundation_type"] = "pieux"
    m = re.search(r"arase inf[ée]rieure des semelles se situera vers " + _NUM + r"\s*m", flat, re.I) or \
        re.search(r"(?:ancr[ée]es?|assise|fond de fouille)[^.]{0,60}?" + _NUM + r"\s*m\s*/\s*TN", flat, re.I)
    if m:
        out["embedment_m"] = float(m.group(1).replace(",", "."))
    m = re.search(r"(sol d.ancrage|couche d.ancrage|ancrage[^.]{0,20}au sein des)\s*([A-Za-zéèàç' ]{4,40})", flat, re.I)
    if m:
        out["soil_layer"] = m.group(2).strip()
    return out


def _norm_level(name) -> str:
    import unicodedata
    t = unicodedata.normalize("NFKD", str(name or "")).encode("ascii", "ignore").decode().lower()
    t = re.sub(r"\b(niv(eau)?|plan|du|de|des|la|le)\b\.?", " ", t)
    return re.sub(r"[^a-z0-9+-]+", " ", t).strip()


def _level_rank(name, n_above: int):
    """Rang d'un libellé de niveau : -1 sous-sol, 0 RDC, 1 étage… ; combles = dernier niveau hors sol."""
    t = _norm_level(name)
    if not t:
        return None
    if re.search(r"sous ?-?sol|\bss\b|cave|r ?- ?1", t):
        return -1
    if re.search(r"\brdc\b|rez|r ?\+ ?0", t):
        return 0
    if "comble" in t:
        return max(n_above - 1, 0)
    m = re.search(r"r ?\+ ?(\d)", t) or re.search(r"(\d)\s*(?:er|e|eme|ème)?\s*etage", t)
    if m:
        return int(m.group(1))
    if "etage" in t:
        return 1
    return None


# ------------------------------------------------------------------ fusion
def merge_reads(plans: dict | None, elev: dict | None, g2: dict | None) -> dict:
    """Fusion déterministe des lectures → géométrie structuro_maison + incertitudes."""
    p, e, inc = plans or {}, elev or {}, []
    inc += [str(x) for x in p.get("incertitudes") or []] + [str(x) for x in e.get("incertitudes") or []]
    geo: dict = {}
    for k in ("name", "outer_L_m", "outer_W_m", "wall_thickness_m", "structural_wall_m", "interior_walls_x", "interior_walls_y"):
        if p.get(k) not in (None, ""):
            geo[k] = p[k]
    if not geo.get("outer_L_m") or not geo.get("outer_W_m"):
        inc.append("Dimensions hors tout non lues — à indiquer (L × W).")
    # niveaux : cotes des planchers → hauteurs d'étage
    lv = sorted([x for x in e.get("levels") or [] if isinstance(x.get("floor_level_m"), (int, float))], key=lambda x: x["floor_level_m"])
    eaves = e.get("eaves_level_m")
    basement = [x for x in lv if x["floor_level_m"] < -0.5]
    above = [x for x in lv if x["floor_level_m"] >= -0.5]
    levels = []
    for i, x in enumerate(above):
        nxt = above[i + 1]["floor_level_m"] if i + 1 < len(above) else (eaves if isinstance(eaves, (int, float)) else None)
        if nxt is None:
            inc.append(f"Hauteur du niveau {x.get('name')} non lue (cote d'égout manquante).")
            nxt = x["floor_level_m"] + 2.7
        use = x.get("use") if x.get("use") in ("habitation", "garage", "commerce", "bureaux", "combles") else "habitation"
        if use == "combles":
            use = "habitation"
        levels.append({"name": x.get("name") or f"Niveau {i}", "storey_height_m": round(nxt - x["floor_level_m"], 2), "use": use})
    if p.get("garage_level"):
        for l_ in levels:
            if l_["name"].lower() == str(p["garage_level"]).lower():
                l_["use"] = "garage"
    if levels:
        geo["levels"] = levels
    else:
        inc.append("Niveaux non lus sur les coupes — à indiquer (nom + hauteur d'étage).")
    if basement:
        b = basement[0]
        geo["basement"] = {"present": True, "height_m": round(abs(b["floor_level_m"]), 2), "name": b.get("name") or "Sous-sol"}
    elif p.get("basement_present"):
        geo["basement"] = {"present": True, "height_m": None, "name": "Sous-sol"}
        inc.append("Sous-sol présent mais cote non lue — hauteur à indiquer.")
    ridge = e.get("ridge_level_m")
    roof = {"type": e.get("roof_type") if e.get("roof_type") in ("inclinee", "terrasse") else "inclinee"}
    if isinstance(ridge, (int, float)) and isinstance(eaves, (int, float)):
        roof["ridge_height_m"] = round(ridge - eaves, 2)
    if e.get("roof_bearing_walls") in ("long", "short"):
        roof["bearing"] = e["roof_bearing_walls"]
    else:
        inc.append("Murs porteurs de la charpente non identifiés — à confirmer (gouttereaux).")
    roof["top_slab"] = bool(e.get("attic_floor_slab")) if roof["type"] == "inclinee" else True
    geo["roof"] = roof
    # baies : positions (plans) + hauteurs/allèges (façades), appariement par niveau + façade + largeur/position.
    # Les 2 lectures nomment souvent les niveaux différemment (« R+1 » / « Niv Etage ») → libellés ramenés au niveau canonique.
    canon = {}
    if basement:
        canon[-1] = (geo.get("basement") or {}).get("name") or "Sous-sol"
    for i, l_ in enumerate(levels):
        canon[i] = l_["name"]
    exact = {_norm_level(v): v for v in canon.values()}

    def lvl(name):
        if not canon:
            return name
        k = _norm_level(name)
        if k in exact:
            return exact[k]
        r = _level_rank(name, len(levels))
        return canon.get(r, name)

    def near(a, b):
        return (a.get("facade") == b.get("facade") and a.get("level") == b.get("level")
                and abs((a.get("width_m") or 0) - (b.get("width_m") or 0)) < 0.45
                and (a.get("x0_m") is None or b.get("x0_m") is None or abs(a["x0_m"] - b["x0_m"]) < 0.6))

    ops = []
    pool = [{**o, "level": lvl(o.get("level"))} for o in e.get("openings") or []]
    for o in p.get("openings") or []:
        o = {**o, "level": lvl(o.get("level"))}
        if any(near(o, x) for x in ops):                         # doublon dans la même lecture
            continue
        best, bd = None, 9e9
        for q in pool:
            if q.get("facade") != o.get("facade") or q.get("level") != o.get("level"):
                continue
            d = abs((q.get("width_m") or 0) - (o.get("width_m") or 0)) + (abs((q.get("x0_m") or 0) - (o.get("x0_m") or 0)) if q.get("x0_m") is not None else 0.5)
            if d < bd:
                best, bd = q, d
        oo = dict(o)
        if best is not None and bd < 1.0:
            pool.remove(best)
            for k in ("height_m", "sill_m"):
                if oo.get(k) is None:
                    oo[k] = best.get(k)
            if best.get("kind") in ("lucarne", "fenetre_toit"):
                oo["kind"] = best["kind"]
        ops.append(oo)
    for q in pool:                                                # baies vues seulement en façade (lucarnes…)
        if q.get("x0_m") is not None and not any(near(q, x) for x in ops):
            ops.append(q)
    geo["openings"] = ops
    if p.get("stair"):
        geo["stair"] = p["stair"]
    names = {"frente": "Façade avant", "tras": "Façade arrière", "esquerda": "Façade rue", "direita": "Façade jardin"}
    for w in p.get("party_walls") or []:
        if w in names:
            names[w] = "Mur mitoyen" + (" 1" if w in ("frente", "esquerda") else " 2")
    geo["facade_names"] = names
    if g2:
        soil = {k: g2.get(k) for k in ("q_els_kpa", "q_elu_kpa", "foundation_type", "embedment_m") if g2.get(k) is not None}
        if g2.get("soil_layer"):
            soil["source"] = f"G2 — ancrage : {g2['soil_layer']}"
        soil["confirmed"] = soil.get("q_els_kpa") is not None
        if not soil["confirmed"]:
            inc.append("Contrainte admissible non trouvée dans la G2 — indiquer q ELS (kPa).")
        geo["soil"] = soil
    return {"geometry": geo, "incertitudes": inc}


async def extract(pc_pdfs: list[bytes], g2_pdfs: list[bytes]) -> dict:
    """PC/DP (PDF) + G2 (PDF) → {geometry, incertitudes, models}."""
    plan_imgs, elev_imgs = [], []
    for pdf in pc_pdfs:
        cls = await asyncio.to_thread(classify_pages, pdf)
        plan_imgs += await asyncio.to_thread(render, pdf, cls["plans"], 110)
        elev_imgs += await asyncio.to_thread(render, pdf, cls["elev"], 110)
    g2 = {}
    for pdf in g2_pdfs:
        g2 = {**await asyncio.to_thread(g2_from_text, pdf), **{k: v for k, v in g2.items() if v is not None}}
    tasks = [ask_vision(PLANS_PROMPT, plan_imgs[:6]), ask_vision(ELEV_PROMPT, elev_imgs[:6])]
    need_g2_vision = g2_pdfs and not g2.get("q_els_kpa")
    if need_g2_vision:
        g2_imgs = []
        for pdf in g2_pdfs:
            g2_imgs += await asyncio.to_thread(render, pdf, list(range(0, 20)), 80)
        tasks.append(ask_vision(G2_PROMPT, g2_imgs[:16]))
    res = await asyncio.gather(*tasks)
    (plans, m1), (elev, m2) = res[0], res[1]
    if need_g2_vision and res[2][0]:
        g2 = {**res[2][0], **{k: v for k, v in g2.items() if v is not None}}
    out = merge_reads(plans, elev, g2 if g2_pdfs else None)
    if plans is None:
        out["incertitudes"].insert(0, "Lecture des plans de niveaux impossible — indiquer les dimensions et les baies.")
    if elev is None:
        out["incertitudes"].insert(0, "Lecture des façades/coupes impossible — indiquer les niveaux, l'égout et le faîtage.")
    if not g2_pdfs:
        out["incertitudes"].append("Pas d'étude G2 : les semelles ne seront pas dimensionnées (tableau de largeurs seulement).")
    out["models"] = [m for m in (m1, m2) if m]
    return out
