"""Rédacteur CCTP / DCE de ConstruPilot.

Produit, pour chaque lot choisi, un CCTP complet au format des économistes (page de garde, sommaire,
prescriptions particulières, préconisations de mise en œuvre, description des ouvrages avec localisation
et variantes chiffrables), plus un cadre de DPGF Excel à la même numérotation, le tout réuni en dossier DCE.

Fiabilité :
- la base (prescriptions, documents de référence, articles types) est déterministe : cctp_catalogue ;
- l'IA (Claude) adapte et complète les articles au projet, en JSON strict ;
- vérification après rédaction : toute norme / DTU cité qui n'est pas dans la liste blanche du catalogue est
  retiré et signalé ; aucune quantité n'est acceptée si elle ne vient pas des données saisies ou du devis ;
- si l'IA échoue, le CCTP est rédigé depuis le catalogue seul (jamais de page blanche).
"""
from __future__ import annotations

import base64
import io
import json
import logging
import re
import unicodedata
import zipfile
from datetime import date

from engines.cctp_catalogue import A_CHARGE, COMMUNES, LOTS, LOTS_PAR_CODE, RENOVATION
from engines.cctp_pieces import articles_par_piece

logger = logging.getLogger(__name__)

VERT = "1F4E4A"
CUIVRE = "B87333"
CREME = "F7F1E8"
IA_TIMEOUT_S = 150.0          # par lot : au-delà, rédaction depuis le catalogue


# ---------------------------------------------------------------------------------------------
# Outils texte
# ---------------------------------------------------------------------------------------------
def _fold(s: str) -> str:
    return unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode().lower()


def _num(x) -> float | None:
    try:
        v = float(str(x).replace(",", ".").replace(" ", ""))
    except (TypeError, ValueError):
        return None
    return round(v, 2) if v > 0 else None


_REF_RE = re.compile(r"\b(?:NF\s+)?DTU\s*\d+(?:\.\d+)*|\bNF\s+EN\s+\d+(?:-\d+)*|\bNF\s+[A-Z]\s*\d{2}[- ]?\d{3}(?:-\d+)?"
                     r"|\bEurocode\s+\d+", re.I)


def _norm_ref(r: str) -> str:
    r = _fold(r).replace("nf ", "").replace(" ", "").replace("-", "")
    return r


def _whitelist() -> set[str]:
    out = set()
    for lot in LOTS:
        for ref in lot["refs"]:
            for m in _REF_RE.finditer(ref):
                out.add(_norm_ref(m.group(0)))
    return out


WHITELIST = _whitelist()


def verifier_references(texte: str) -> tuple[str, list[str]]:
    """Retire les normes / DTU absents de la liste blanche. Renvoie (texte corrigé, références retirées)."""
    retirees: list[str] = []

    def _sub(m):
        ref = m.group(0)
        if _norm_ref(ref) in WHITELIST:
            return ref
        retirees.append(ref.strip())
        return "la norme applicable"
    return _REF_RE.sub(_sub, texte or ""), retirees


# ---------------------------------------------------------------------------------------------
# Sélection : lot et ouvrage pour une ligne libre ou une ligne de devis
# ---------------------------------------------------------------------------------------------
def _score(txt: str, mots: list[str]) -> int:
    best = 0
    for k in mots:
        kk = _fold(k)
        if re.search(r"\b" + re.escape(kk), txt):
            best = max(best, len(kk))
    return best


def lot_pour(designation: str, description: str = "") -> str | None:
    txt = _fold(f"{designation} {description}")
    best, code = 0, None
    for lot in LOTS:
        mots = list(lot["motscles"]) + [m for o in lot["ouvrages"] for m in o["motscles"]]
        s = _score(txt, mots)
        if lot["code"] == "gros_oeuvre":        # « mur » apparaît aussi dans « faïence (mur) », « doublage mur »…
            s -= 1
        if s > best:
            best, code = s, lot["code"]
    return code


def ouvrage_pour(lot: dict, designation: str, description: str = "") -> str | None:
    txt = _fold(f"{designation} {description}")
    best, code = 0, None
    for o in lot["ouvrages"]:
        s = _score(txt, o["motscles"] + [o["titre"]])
        if s > best:
            best, code = s, o["code"]
    return code


def selection_depuis_devis(lines: list[dict]) -> list[dict]:
    """Convertit les lignes d'un devis ConstruPilot en sélection de lots/ouvrages, avec quantités."""
    lots: dict[str, dict] = {}
    for ln in lines or []:
        if ln.get("kind", "line") != "line" or not ln.get("designation"):
            continue
        code = lot_pour(ln.get("designation", ""), ln.get("description") or "")
        if not code:
            continue
        sel = lots.setdefault(code, {"code": code, "ouvrages": [], "lignes": []})
        sel["lignes"].append({"designation": str(ln["designation"])[:200], "detail": str(ln.get("description") or "")[:400],
                              "unite": str(ln.get("unit") or "")[:10], "quantite": _num(ln.get("qty")),
                              "localisation": ""})
    order = [l["code"] for l in LOTS]
    return [lots[c] for c in order if c in lots]


# ---------------------------------------------------------------------------------------------
# Articles
# ---------------------------------------------------------------------------------------------
def _article_catalogue(o: dict, localisation: str = "") -> dict:
    return {"chapitre": o["chapitre"], "titre": o["titre"], "description": o["description"],
            "localisation": localisation or "Suivant plans.", "code": o["code"], "source": "catalogue",
            "variantes": [{"libelle": v, "unite": o["unite"], "quantite": None} for v in o["variantes"]]}


# Ouvrages types remplacés par les articles « par pièce » quand un programme de pièces est fourni.
REMPLACES_PAR_PIECES = {"prises", "eclairage", "tableau", "rj45", "wc", "lavabo", "douche", "evier"}


def articles_de_base(lot: dict, sel: dict, exclure: set[str] | None = None) -> list[dict]:
    """Articles déterministes : ouvrages cochés + lignes saisies (rattachées à un ouvrage type si possible)."""
    arts: dict[str, dict] = {}
    for code in sel.get("ouvrages") or []:
        o = next((x for x in lot["ouvrages"] if x["code"] == code), None)
        if o:
            arts[code] = _article_catalogue(o)
    libres: list[dict] = []
    for ln in sel.get("lignes") or []:
        des = (ln.get("designation") or "").strip()
        if not des:
            continue
        var = {"libelle": des, "unite": (ln.get("unite") or "").strip() or "u", "quantite": _num(ln.get("quantite"))}
        oc = ln.get("ouvrage") or ouvrage_pour(lot, des, ln.get("detail") or "")
        o = next((x for x in lot["ouvrages"] if x["code"] == oc), None)
        if o:
            art = arts.get(oc)
            if not art:
                art = _article_catalogue(o, ln.get("localisation") or "")
                art["variantes"] = []
                art["source"] = "devis"
                arts[oc] = art
            elif ln.get("localisation") and art["localisation"] == "Suivant plans.":
                art["localisation"] = ln["localisation"]
            art["variantes"].append(var)
        else:
            libres.append({"chapitre": "Ouvrages complémentaires", "titre": des.upper()[:120],
                           "description": (ln.get("detail") or "").strip() or
                           f"Fourniture et mise en œuvre : {des}, conformément aux documents de référence du lot et aux "
                           "prescriptions des fabricants, y compris toutes sujétions de façon et de finition.",
                           "localisation": ln.get("localisation") or "Suivant plans.", "code": None, "source": "saisie",
                           "variantes": [var]})
    order = {o["code"]: i for i, o in enumerate(lot["ouvrages"])}
    out = sorted(arts.values(), key=lambda a: order.get(a["code"], 999)) + libres
    if not out:                                    # lot coché sans détail : tous les ouvrages types
        out = [_article_catalogue(o) for o in lot["ouvrages"] if o["code"] not in (exclure or set())]
    return out


def lot_compose(sel: dict) -> dict:
    """Lot du catalogue, ou lot regroupé (ex. « Aménagements intérieurs » = plâtrerie + menuiseries int. + peinture + sols)."""
    codes = [sel["code"]] + [c for c in (sel.get("inclure") or []) if c in LOTS_PAR_CODE and c != sel["code"]]
    lots = [LOTS_PAR_CODE[c] for c in codes]
    base = lots[0]
    if len(lots) == 1:
        return {**base, "titre": (sel.get("titre") or base["titre"]).strip(), "codes": codes,
                "a_charge": list(A_CHARGE.get(base["code"], []))}
    refs, presc, ouvrages, mots, charge = [], [], [], [], []
    for l in lots:
        refs += [r for r in l["refs"] if r not in refs]
        presc += [(f"{chap} — {l['titre']}", items) for chap, items in l["prescriptions"]]
        ouvrages += l["ouvrages"]
        mots += l["motscles"]
        charge += [x for x in A_CHARGE.get(l["code"], []) if x not in charge]
    return {"code": base["code"], "numero": base["numero"], "codes": codes, "refs": refs, "prescriptions": presc,
            "ouvrages": ouvrages, "motscles": mots, "a_charge": charge,
            "titre": (sel.get("titre") or " – ".join(l["titre"].split(" – ")[0] for l in lots)).strip()}


def _quantites_saisies(sel: dict) -> set[float]:
    return {q for q in (_num(l.get("quantite")) for l in sel.get("lignes") or []) if q}


async def rediger_lot_ia(lot: dict, projet: dict, sel: dict, articles: list[dict]) -> tuple[list[dict], list[tuple[str, str]], list[str]]:
    """Claude adapte les articles au projet. Renvoie (articles, prescriptions complémentaires, points à vérifier)."""
    from engines import ai
    system = (ai.BRAND + " Tu es économiste de la construction et rédacteur de CCTP en France. Tu rédiges des articles de "
              "CCTP précis, au futur, dans le style des cahiers des charges d'économistes (« Fourniture et pose de … », "
              "« Y compris … », « Localisation : … »). Tu retournes UNIQUEMENT du JSON valide.")
    base = [{k: a[k] for k in ("chapitre", "titre", "description", "localisation", "variantes")} for a in articles]
    prompt = (
        f"PROJET : {json.dumps({k: projet.get(k) for k in ('nom', 'adresse', 'nature', 'description')}, ensure_ascii=False)}\n"
        f"LOT n°{sel.get('numero') or lot['numero']} — {lot['titre']}\n"
        f"Documents de référence AUTORISÉS (n'en cite aucun autre) : {json.dumps(lot['refs'], ensure_ascii=False)}\n"
        f"Consignes du rédacteur pour ce lot : {(sel.get('notes') or 'aucune')[:2000]}\n\n"
        f"ARTICLES DE BASE (à conserver, adapter au projet et compléter) :\n{json.dumps(base, ensure_ascii=False)[:30000]}\n\n"
        "Retourne UNIQUEMENT ce JSON : {\n"
        '  "articles": [ { "chapitre": "…", "titre": "TITRE EN MAJUSCULES", "description": "texte complet de l\'article : '
        'matériaux, caractéristiques, mise en œuvre, sujétions", "localisation": "…",\n'
        '      "variantes": [ { "libelle": "…", "unite": "m2|ml|m3|u|ens|forfait", "quantite": nombre ou null } ] } ],\n'
        '  "prescriptions_complementaires": [ { "titre": "…", "texte": "…" } ],\n'
        '  "points_a_verifier": [ "information manquante ou hypothèse prise, à valider par le maître d\'œuvre" ]\n'
        "}\n"
        "Règles : garde TOUS les articles de base et leurs variantes (mêmes libellés et quantités). Ne crée pas de "
        "quantité : laisse null si elle n'est pas fournie. N'invente ni marque, ni prix, ni performance chiffrée qui "
        "dépend d'une étude (thermique, acoustique, structure) : écris « suivant étude … ». Les prescriptions "
        "complémentaires (0 à 4) ne concernent que ce projet (nature des travaux, consignes) et ne répètent pas les "
        "généralités. Français professionnel, sans markdown."
    )
    data = ai._json(await ai._complete(system, prompt, feature="cctp_redaction"), {})
    if not isinstance(data, dict) or not data.get("articles"):
        raise ValueError("réponse IA vide")
    permises = _quantites_saisies(sel)
    out = []
    for a in data["articles"][:60]:
        titre = str(a.get("titre") or "").strip()[:160]
        desc = str(a.get("description") or "").strip()[:4000]
        if not titre or len(desc) < 30:
            continue
        vars_ = []
        for v in (a.get("variantes") or [])[:15]:
            lib = str(v.get("libelle") or "").strip()[:200]
            if not lib:
                continue
            q = _num(v.get("quantite"))
            vars_.append({"libelle": lib, "unite": str(v.get("unite") or "u")[:10], "quantite": q if q in permises else None})
        out.append({"chapitre": str(a.get("chapitre") or "Ouvrages")[:120], "titre": titre.upper(), "description": desc,
                    "localisation": str(a.get("localisation") or "Suivant plans.")[:600], "source": "ia", "code": None,
                    "variantes": vars_ or [{"libelle": titre.capitalize(), "unite": "u", "quantite": None}]})
    # Garde-fou : un article de base perdu par l'IA est réintégré tel quel.
    titres = {_fold(a["titre"]) for a in out}
    for a in articles:
        if _fold(a["titre"]) not in titres:
            out.append(a)
    presc = [(str(p.get("titre") or "")[:120], str(p.get("texte") or "")[:2000])
             for p in (data.get("prescriptions_complementaires") or [])[:4] if p.get("titre") and p.get("texte")]
    points = [str(p)[:300] for p in (data.get("points_a_verifier") or [])[:15] if p]
    return out, presc, points


def _verifier_articles(articles: list[dict], presc: list[tuple[str, str]]) -> tuple[list[dict], list[tuple[str, str]], list[str]]:
    retirees: list[str] = []
    for a in articles:
        for k in ("description", "localisation"):
            a[k], r = verifier_references(a[k])
            retirees += r
    out_p = []
    for t, x in presc:
        x, r = verifier_references(x)
        retirees += r
        out_p.append((t, x))
    msgs = [f"Référence non vérifiée retirée du texte : « {r} »" for r in dict.fromkeys(retirees)]
    return articles, out_p, msgs


# ---------------------------------------------------------------------------------------------
# Rédaction d'un dossier
# ---------------------------------------------------------------------------------------------
async def rediger(projet: dict, selection: list[dict], ia: bool = True) -> list[dict]:
    """Rédige chaque lot. Renvoie la liste des lots rédigés (structure prête pour DOCX / DPGF)."""
    fusion: dict[str, dict] = {}
    hote = {c: s_["code"] for s_ in selection for c in (s_.get("inclure") or [])}   # lot inclus → lot regroupé
    for sel in sorted(selection, key=lambda x: 0 if x.get("inclure") else 1):
        code = hote.get(sel.get("code"), sel.get("code"))   # un même lot sélectionné deux fois (devis + saisie) est fusionné
        if code not in fusion:
            fusion[code] = {**sel, "ouvrages": list(sel.get("ouvrages") or []), "lignes": list(sel.get("lignes") or [])}
        else:
            f = fusion[code]
            f["ouvrages"] += [o for o in sel.get("ouvrages") or [] if o not in f["ouvrages"]]
            f["lignes"] += list(sel.get("lignes") or [])
            f["notes"] = "\n".join(x for x in (f.get("notes"), sel.get("notes")) if x)
            f["numero"] = f.get("numero") or sel.get("numero")
    import asyncio
    sem = asyncio.Semaphore(4)

    pieces = projet.get("pieces") or []

    async def _un(sel: dict) -> dict | None:
        if sel.get("code") not in LOTS_PAR_CODE:
            return None
        lot = lot_compose(sel)
        numero = int(sel.get("numero") or lot["numero"])
        par_piece = bool(pieces) and any(c in lot["codes"] for c in ("electricite", "plomberie"))
        articles = articles_de_base(lot, sel, REMPLACES_PAR_PIECES if par_piece else None)
        presc: list[tuple[str, str]] = []
        points: list[str] = []
        mode = "catalogue"
        if ia and articles:
            try:
                async with sem:
                    articles, presc, points = await asyncio.wait_for(
                        rediger_lot_ia(lot, projet, {**sel, "numero": numero}, articles), IA_TIMEOUT_S)
                mode = "ia"
            except Exception as exc:  # noqa: BLE001 — repli catalogue, jamais de CCTP vide
                logger.warning("cctp: rédaction IA indisponible pour %s (%s), repli catalogue", lot["code"], exc)
                points.append("Rédaction assistée indisponible : CCTP établi depuis les articles types ConstruPilot.")
        articles, presc, msgs = _verifier_articles(articles, presc)
        # Équipements par pièce (quantités par règle, hors IA) pour l'électricité et la plomberie.
        for code in lot["codes"]:
            articles += articles_par_piece(code, pieces)
        sans_qte = sum(1 for a in articles for v in a["variantes"] if v["quantite"] is None)
        if sans_qte:
            points.append(f"{sans_qte} ligne(s) du cadre de DPGF sans quantité : à métrer ou à laisser au quantitatif des entreprises.")
        if par_piece:
            points.append("Équipements par pièce : socle établi depuis le programme saisi, à confronter aux plans électricité / plomberie.")
        return {"code": lot["code"], "codes": lot["codes"], "numero": numero, "titre": lot["titre"], "refs": lot["refs"],
                "prescriptions": lot["prescriptions"], "a_charge": lot["a_charge"], "complementaires": presc,
                "articles": articles, "points": points + msgs, "mode": mode}

    rediges = [r for r in await asyncio.gather(*(_un(s) for s in fusion.values())) if r]
    rediges.sort(key=lambda r: r["numero"])
    return rediges


# ---------------------------------------------------------------------------------------------
# Numérotation commune CCTP / DPGF
# ---------------------------------------------------------------------------------------------
def numeroter(lot: dict) -> list[dict]:
    """Chapitres de description (N.2, N.3…), articles N.c.a, variantes N.c.a.v."""
    n = lot["numero"]
    chapitres: dict[str, list[dict]] = {}
    for a in lot["articles"]:
        chapitres.setdefault(a["chapitre"], []).append(a)
    out = []
    for ci, (chap, arts) in enumerate(chapitres.items(), 2):
        c = {"num": f"{n}.{ci}", "titre": chap, "articles": []}
        for ai_, a in enumerate(arts, 1):
            num_a = f"{c['num']}.{ai_}"
            c["articles"].append({**a, "num": num_a,
                                  "variantes": [{**v, "num": f"{num_a}.{vi}"} for vi, v in enumerate(a["variantes"], 1)]})
        out.append(c)
    return out


# ---------------------------------------------------------------------------------------------
# DOCX
# ---------------------------------------------------------------------------------------------
def _field(run, instr: str):
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn
    for kind, text in (("begin", None), (None, instr), ("separate", None), (None, "…"), ("end", None)):
        if kind:
            el = OxmlElement("w:fldChar")
            el.set(qn("w:fldCharType"), kind)
            run._r.append(el)
        elif text == instr:
            el = OxmlElement("w:instrText")
            el.set(qn("xml:space"), "preserve")
            el.text = instr
            run._r.append(el)
        else:
            el = OxmlElement("w:t")
            el.text = text
            run._r.append(el)


def _shade(cell, hex_):
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn
    tc = cell._tc.get_or_add_tcPr()
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:color"), "auto")
    shd.set(qn("w:fill"), hex_)
    tc.append(shd)


def _logo(branding: dict | None):
    raw = (branding or {}).get("logo_b64")
    if not raw:
        return None
    try:
        return io.BytesIO(base64.b64decode(raw.split(",", 1)[-1]))
    except Exception:  # noqa: BLE001
        return None


INTERVENANTS = [("architecte", "Architecte"), ("bet_structure", "BET Structure"), ("bet_fluides", "BET Fluides"),
                ("bet_thermique", "BET Thermique"), ("coordonnateur_sps", "Coordonnateur SPS"),
                ("controleur_technique", "Contrôleur technique")]


def intervenants(projet: dict) -> list[tuple[str, str]]:
    iv = projet.get("intervenants") or {}
    return [(lib, str(iv[k]).strip()) for k, lib in INTERVENANTS if str(iv.get(k) or "").strip()]


def cctp_docx(projet: dict, lot: dict, branding: dict | None = None) -> bytes:
    from docx import Document
    from docx.enum.section import WD_SECTION
    from docx.enum.table import WD_TABLE_ALIGNMENT
    from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_BREAK
    from docx.shared import Cm, Pt, RGBColor

    vert, cuivre = RGBColor.from_string(VERT), RGBColor.from_string(CUIVRE)
    doc = Document()
    sec = doc.sections[0]
    sec.page_height, sec.page_width = Cm(29.7), Cm(21.0)
    sec.left_margin = sec.right_margin = Cm(2.0)
    sec.top_margin, sec.bottom_margin = Cm(2.0), Cm(1.8)
    st = doc.styles["Normal"]
    st.font.name, st.font.size = "Calibri", Pt(10)
    st.paragraph_format.space_after = Pt(4)
    for lvl, size, color in ((1, 14, vert), (2, 12, vert), (3, 11, cuivre), (4, 10, vert)):
        h = doc.styles[f"Heading {lvl}"]
        h.font.name, h.font.size, h.font.bold = "Calibri", Pt(size), True
        h.font.color.rgb = color
        h.paragraph_format.space_before = Pt(10 if lvl < 3 else 6)
        h.paragraph_format.keep_with_next = True

    n = lot["numero"]
    societe = (branding or {}).get("company_name") or projet.get("redacteur") or ""

    # ---------- Page de garde
    logo = _logo(branding)
    if logo:
        try:
            doc.add_picture(logo, height=Cm(2.2))
            doc.paragraphs[-1].alignment = WD_ALIGN_PARAGRAPH.LEFT
        except Exception:  # noqa: BLE001 — logo illisible : on continue sans
            pass
    for _ in range(3):
        doc.add_paragraph()
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r = p.add_run((projet.get("nom") or "Projet").upper())
    r.bold, r.font.size, r.font.color.rgb = True, Pt(20), vert
    if projet.get("adresse"):
        p = doc.add_paragraph(projet["adresse"])
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    doc.add_paragraph()
    t = doc.add_table(rows=1, cols=1)
    t.alignment = WD_TABLE_ALIGNMENT.CENTER
    c = t.rows[0].cells[0]
    _shade(c, VERT)
    cp = c.paragraphs[0]
    cp.alignment = WD_ALIGN_PARAGRAPH.CENTER
    rr = cp.add_run("C.C.T.P.")
    rr.bold, rr.font.size, rr.font.color.rgb = True, Pt(28), RGBColor(0xFF, 0xFF, 0xFF)
    cp2 = c.add_paragraph()
    cp2.alignment = WD_ALIGN_PARAGRAPH.CENTER
    rr = cp2.add_run("Cahier des Clauses Techniques Particulières")
    rr.font.size, rr.font.color.rgb = Pt(13), RGBColor(0xFF, 0xFF, 0xFF)
    cp3 = c.add_paragraph()
    cp3.alignment = WD_ALIGN_PARAGRAPH.CENTER
    rr = cp3.add_run(f"LOT N°{n:02d} — {lot['titre'].upper()}")
    rr.bold, rr.font.size, rr.font.color.rgb = True, Pt(15), RGBColor.from_string(CREME)
    doc.add_paragraph()
    info = [("Maître d'ouvrage", projet.get("maitre_ouvrage")), ("Maître d'œuvre", projet.get("maitre_oeuvre")),
            ("Nature des travaux", {"neuf": "Construction neuve", "renovation": "Rénovation / réhabilitation"}.get(projet.get("nature"), projet.get("nature"))),
            *intervenants(projet),
            ("Phase", projet.get("phase") or "DCE"), ("Indice", projet.get("indice") or "A"),
            ("Date", projet.get("date") or date.today().strftime("%d/%m/%Y")), ("Rédigé par", societe)]
    info = [(k, v) for k, v in info if v]
    tb = doc.add_table(rows=len(info), cols=2)
    tb.style = "Table Grid"
    tb.alignment = WD_TABLE_ALIGNMENT.CENTER
    for i, (k, v) in enumerate(info):
        a, b = tb.rows[i].cells
        a.width, b.width = Cm(5), Cm(10)
        _shade(a, CREME)
        a.paragraphs[0].add_run(k).bold = True
        b.paragraphs[0].add_run(str(v))
    doc.add_paragraph().add_run().add_break(WD_BREAK.PAGE)

    # ---------- Sommaire
    doc.add_heading("SOMMAIRE", 1)
    _field(doc.add_paragraph().add_run(), 'TOC \\o "1-3" \\h \\z \\u')
    doc.add_paragraph("Clic droit sur le sommaire puis « Mettre à jour les champs » pour actualiser la pagination.").runs[0].italic = True

    # ---------- En-tête / pied
    body = doc.add_section(WD_SECTION.NEW_PAGE)
    body.header.is_linked_to_previous = False
    body.footer.is_linked_to_previous = False
    hp = body.header.paragraphs[0]
    hr = hp.add_run(f"{projet.get('nom') or 'Projet'} — CCTP Lot n°{n:02d} {lot['titre']}")
    hr.font.size, hr.font.color.rgb = Pt(8), vert
    fp = body.footer.paragraphs[0]
    fp.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    pied = (f"Document établi par {societe} — " if societe and projet.get("style") == "architecte" else "")
    fr = fp.add_run(f"{pied}{projet.get('phase') or 'DCE'} — Indice {projet.get('indice') or 'A'}    Page ")
    fr.font.size = Pt(8)
    _field(fp.add_run(), "PAGE")
    fp.add_run(" / ").font.size = Pt(8)
    _field(fp.add_run(), "NUMPAGES")

    # ---------- N.1 Généralités / prescriptions particulières
    archi = projet.get("style") == "architecte"
    just = WD_ALIGN_PARAGRAPH.JUSTIFY
    doc.add_heading(f"{n}.1 {'GÉNÉRALITÉS' if archi else 'PRESCRIPTIONS PARTICULIÈRES'}", 1)
    doc.add_heading(f"{n}.1.1 GÉNÉRALITÉS" if not archi else f"{n}.1.1 OBJET ET CONSISTANCE DES TRAVAUX", 2)
    k = 1
    doc.add_heading(f"{n}.1.1.{k} Objet de la prestation", 3)
    nature = {"neuf": "la construction", "renovation": "la rénovation"}.get(projet.get("nature"), "la réalisation")
    lieu = f", située {projet['adresse']}" if projet.get("adresse") else ""
    doc.add_paragraph(f"Le présent document a pour objet de décrire les travaux du lot n°{n:02d} — {lot['titre']}, dans le cadre "
                      f"de {nature} de l'opération « {projet.get('nom') or 'Projet'} »{lieu}.").alignment = just
    if projet.get("description"):
        doc.add_paragraph(projet["description"]).alignment = just
    pieces = projet.get("pieces") or []
    if pieces:
        noms = ", ".join(p.get("nom") or "" for p in pieces if p.get("nom"))
        doc.add_paragraph(f"Le programme comprend : {noms}.").alignment = just
    if projet.get("maitre_oeuvre"):
        doc.add_paragraph(f"L'ensemble sera réalisé suivant les études de la maîtrise d'œuvre : {projet['maitre_oeuvre']}.").alignment = just
    k += 1
    doc.add_heading(f"{n}.1.1.{k} Nature des prestations", 3)
    doc.add_paragraph("Les travaux du présent lot concernent notamment :")
    for chap in dict.fromkeys(a_["chapitre"] for a_ in lot["articles"]):
        doc.add_paragraph(chap, style="List Bullet")
    communes = list(COMMUNES)
    if projet.get("nature") == "renovation":
        communes.insert(2, RENOVATION)
    if projet.get("tce"):
        communes.insert(0, ("Connaissance des clauses générales TCE",
                            "L'entreprise titulaire du présent lot est réputée avoir pris connaissance et accepté sans réserve les "
                            "Clauses générales communes à tous les corps d'état (TCE) jointes au dossier de consultation, qui "
                            "complètent le présent CCTP."))
    for titre, texte in communes:
        k += 1
        doc.add_heading(f"{n}.1.1.{k} {titre}", 3)
        doc.add_paragraph(texte).alignment = just
    k += 1
    doc.add_heading(f"{n}.1.1.{k} Documents de référence du lot", 3)
    doc.add_paragraph("Outre les documents cités aux généralités, les ouvrages du présent lot respecteront notamment :")
    for ref in lot["refs"]:
        doc.add_paragraph(ref, style="List Bullet")
    if lot.get("a_charge"):
        k += 1
        doc.add_heading(f"{n}.1.1.{k} Prestations à la charge du présent lot", 3)
        doc.add_paragraph("Sont notamment à la charge du présent lot, comme compris dans son forfait :")
        for x in lot["a_charge"]:
            doc.add_paragraph(x, style="List Bullet")
    if lot["complementaires"]:
        k += 1
        doc.add_heading(f"{n}.1.1.{k} Dispositions propres au projet", 3)
        for titre, texte in lot["complementaires"]:
            pp = doc.add_paragraph()
            pp.add_run(f"{titre}. ").bold = True
            pp.add_run(texte)
            pp.alignment = just
    for ci, (chap, items) in enumerate(lot["prescriptions"], 2):
        doc.add_heading(f"{n}.1.{ci} {chap.upper()}", 2)
        for ii, (titre, texte) in enumerate(items, 1):
            doc.add_heading(f"{n}.1.{ci}.{ii} {titre}", 3)
            doc.add_paragraph(texte).alignment = just

    # ---------- Description des ouvrages
    label = "Position : " if archi else "Localisation : "
    for ci, chap in enumerate(numeroter(lot)):
        if archi and ci == 0:
            doc.add_paragraph().add_run().add_break(WD_BREAK.PAGE)
            t_ = doc.add_paragraph()
            r_ = t_.add_run("DESCRIPTIF DES TRAVAUX")
            r_.bold, r_.font.size, r_.font.color.rgb = True, Pt(16), vert
        doc.add_heading(f"{chap['num']} {chap['titre'].upper()}", 1)
        for a in chap["articles"]:
            doc.add_heading(f"{a['num']} {a['titre']} :", 2)
            for ligne in a["description"].split("\n"):
                if ligne.startswith("- "):
                    doc.add_paragraph(ligne[2:], style="List Bullet")
                elif ligne.strip():
                    doc.add_paragraph(ligne).alignment = just
            pl = doc.add_paragraph()
            pl.add_run(label).bold = True
            pl.add_run(a["localisation"])
            for v in ([] if a.get("source") == "pieces" else a["variantes"]):   # par pièce : la liste suffit, le DPGF détaille
                hv = doc.add_heading(f"{v['num']} {v['libelle']}", 4)
                hv.runs[0].font.size = Pt(10)
                q = f"{v['quantite']:g} {v['unite']}" if v["quantite"] else v["unite"]
                pm = doc.add_paragraph()
                if archi:
                    txt = f"Quantité = {q}" if v["quantite"] else f"Unité : {q}"
                else:
                    txt = f"Unité de règlement : {q}" if not v["quantite"] else f"Quantité indicative : {q}"
                rm = pm.add_run(txt)
                rm.italic, rm.font.size, rm.font.color.rgb = True, Pt(9), cuivre

    doc.add_paragraph()
    fin = doc.add_paragraph(f"Fin du CCTP du lot n°{n:02d} — {lot['titre']}.")
    fin.alignment = WD_ALIGN_PARAGRAPH.CENTER
    fin.runs[0].italic = True
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


# ---------------------------------------------------------------------------------------------
# Cadre de DPGF (même numérotation)
# ---------------------------------------------------------------------------------------------
def dpgf_cadre_xlsx(projet: dict, lots: list[dict]) -> bytes:
    import openpyxl
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side

    wb = openpyxl.Workbook()
    wb.remove(wb.active)
    thin = Side(style="thin", color="BFBFBF")
    border = Border(left=thin, right=thin, top=thin, bottom=thin)
    head_fill, lot_fill, chap_fill = PatternFill("solid", fgColor=VERT), PatternFill("solid", fgColor=CREME), PatternFill("solid", fgColor="EFE7DA")
    eur = '#,##0.00 "€"'
    recap = []
    for lot in lots:
        ws = wb.create_sheet(f"Lot {lot['numero']:02d}"[:31])
        ws.append([f"DPGF — {projet.get('nom') or 'Projet'}"])
        ws["A1"].font = Font(bold=True, size=13, color=VERT)
        ws.append([f"Lot n°{lot['numero']:02d} — {lot['titre']}  ·  Décomposition du prix global et forfaitaire (numérotation du CCTP)"])
        ws.append(["Les quantités indiquées le sont à titre indicatif : l'entreprise vérifie le quantitatif sous sa responsabilité."])
        ws["A3"].font = Font(italic=True, size=9)
        ws.append([])
        ws.append(["N°", "Désignation", "Unité", "Quantité", "PU HT (€)", "Montant HT (€)"])
        for c in ws[5]:
            c.font, c.fill, c.border = Font(bold=True, color="FFFFFF"), head_fill, border
        lignes_montant = []
        for chap in numeroter(lot):
            ws.append([chap["num"], chap["titre"].upper()])
            for c in ws[ws.max_row]:
                c.fill, c.font = chap_fill, Font(bold=True)
            for a in chap["articles"]:
                ws.append([a["num"], a["titre"]])
                ws.cell(ws.max_row, 2).font = Font(bold=True, color=VERT)
                for v in a["variantes"]:
                    r = ws.max_row + 1
                    ws.append([v["num"], v["libelle"], v["unite"], v["quantite"], None, f"=IF(AND(ISNUMBER(D{r}),ISNUMBER(E{r})),D{r}*E{r},0)"])
                    ws.cell(r, 5).number_format = ws.cell(r, 6).number_format = eur
                    for c in ws[r]:
                        c.border = border
                    lignes_montant.append(r)
        ws.append([])
        r = ws.max_row + 1
        somme = "+".join(f"F{x}" for x in lignes_montant) or "0"
        ws.append(["", f"TOTAL HT LOT {lot['numero']:02d}", "", "", "", f"={somme}" if len(lignes_montant) < 200 else f"=SUM(F6:F{r - 1})"])
        ws.cell(r, 2).font = ws.cell(r, 6).font = Font(bold=True)
        ws.cell(r, 6).number_format = eur
        ws.append(["", "TVA", "", "", "", None])
        ws.append(["", "TOTAL TTC", "", "", "", f"=F{r}+F{r + 1}"])
        ws.cell(r + 2, 2).font = ws.cell(r + 2, 6).font = Font(bold=True)
        ws.cell(r + 1, 6).number_format = ws.cell(r + 2, 6).number_format = eur
        for col, w in zip("ABCDEF", (11, 70, 8, 11, 13, 16)):
            ws.column_dimensions[col].width = w
        for row in ws.iter_rows(min_row=6, max_col=2, min_col=2):
            for c in row:
                c.alignment = Alignment(wrap_text=True, vertical="top")
        ws.freeze_panes = "A6"
        recap.append((lot, ws.title, r))
    rs = wb.create_sheet("Récapitulatif", 0)
    rs.append([f"Récapitulatif DPGF — {projet.get('nom') or 'Projet'}"])
    rs["A1"].font = Font(bold=True, size=13, color=VERT)
    rs.append([])
    rs.append(["Lot", "Intitulé", "Total HT (€)"])
    for c in rs[3]:
        c.font, c.fill = Font(bold=True, color="FFFFFF"), head_fill
    for lot, title, r in recap:
        rs.append([f"{lot['numero']:02d}", lot["titre"], f"='{title}'!F{r}"])
        rs.cell(rs.max_row, 3).number_format = eur
        rs.cell(rs.max_row, 1).fill = lot_fill
    n = rs.max_row
    rs.append(["", "TOTAL HT", f"=SUM(C4:C{n})"])
    rs.cell(n + 1, 2).font = rs.cell(n + 1, 3).font = Font(bold=True)
    rs.cell(n + 1, 3).number_format = eur
    for col, w in zip("ABC", (8, 60, 18)):
        rs.column_dimensions[col].width = w
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


# ---------------------------------------------------------------------------------------------
# Dossier DCE
# ---------------------------------------------------------------------------------------------
def _slug(s: str) -> str:
    from engines.nom_fichier import ascii_texte
    s = re.sub(r"[^A-Za-z0-9]+", "-", ascii_texte(s)).strip("-")
    return s[:50] or "Projet"


def note_verification(projet: dict, lots: list[dict]) -> str:
    lines = [f"Note de vérification — CCTP {projet.get('nom') or 'Projet'}", "",
             "Document interne au rédacteur (ne pas joindre au DCE). Le CCTP doit être relu et validé par le maître d'œuvre.", ""]
    for lot in lots:
        lines.append(f"Lot {lot['numero']:02d} — {lot['titre']} (rédaction : {'assistée par IA' if lot['mode'] == 'ia' else 'articles types'})")
        lines += [f"  - {p}" for p in lot["points"]] or ["  - Aucun point signalé."]
        lines.append("")
    return "\n".join(lines)


def fichiers_dossier(projet: dict, lots: list[dict], branding: dict | None = None) -> list[tuple[str, bytes, str]]:
    """Fichiers du dossier : pièces DCE (si demandées), un CCTP .docx par lot, le cadre de DPGF .xlsx, la note de vérification."""
    from engines import dce_pieces as DP
    docx_mime = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    nom = _slug(projet.get("nom") or "Projet")
    out = []
    if projet.get("tce"):
        out.append((f"00_Page-de-garde-DCE_{nom}.docx", DP.page_garde_docx(projet, lots, branding), docx_mime))
        out.append((f"RC_Reglement-de-consultation_{nom}.docx", DP.rc_docx(projet, lots, branding), docx_mime))
        out.append((f"CCTP_Lot-00_Clauses-generales-TCE_{nom}.docx", DP.clauses_tce_docx(projet, lots, branding), docx_mime))
    for lot in lots:
        out.append((f"CCTP_Lot-{lot['numero']:02d}_{_slug(lot['titre'])}_{nom}.docx", cctp_docx(projet, lot, branding), docx_mime))
    out.append((f"DPGF_{nom}.xlsx", dpgf_cadre_xlsx(projet, lots),
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"))
    out.append(("Note-de-verification.txt", note_verification(projet, lots).encode("utf-8"), "text/plain; charset=utf-8"))
    return out


def zip_dossier(projet: dict, fichiers: list[tuple[str, bytes, str]]) -> bytes:
    buf = io.BytesIO()
    racine = f"DCE_{_slug(projet.get('nom') or 'Projet')}"
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for name, data, _ in fichiers:
            sous = ("" if name.startswith("Note") else "1_Pieces-administratives/" if name.startswith(("00_", "RC_"))
                    else "2_CCTP/" if name.startswith("CCTP") else "3_DPGF/")
            z.writestr(f"{racine}/{sous}{name}", data)
    return buf.getvalue()


def catalogue_public() -> list[dict]:
    return [{"code": l["code"], "numero": l["numero"], "titre": l["titre"], "refs": l["refs"],
             "ouvrages": [{"code": o["code"], "chapitre": o["chapitre"], "titre": o["titre"], "unite": o["unite"]} for o in l["ouvrages"]]}
            for l in LOTS]
