"""Pièces du DCE autour des CCTP : page de garde & sommaire, Clauses générales TCE, Règlement de consultation.

Modèle observé sur des DCE d'architecte (maison individuelle) : page de garde avec intervenants (MOA,
architecte, BET structure, BET fluides…) et bandeau des phases, sommaire des pièces écrites et graphiques,
CCTP par lot faisant référence à des « Clauses générales TCE » communes.

Les références juridiques citées sont limitées à des textes stables et vérifiés :
Code civil art. 1792, 1792-2, 1792-3, 1792-6 (garanties) ; Code des assurances art. L241-1 (décennale) ;
loi n° 93-1418 du 31 décembre 1993 (coordination SPS) ; Code du travail art. L8222-1 (obligation de vigilance).
Les montants, délais et pénalités ne sont jamais inventés : ils viennent du projet ou restent « à définir au CCAP ».
"""
from __future__ import annotations

import io
from datetime import date

from engines.cctp_redacteur import CREME, CUIVRE, VERT, _field, _logo, _shade, intervenants

PHASES = ["ESQUISSE", "APS", "APD", "PC", "PRO", "DCE", "ACT", "EXE", "DET", "AOR"]


def _base(projet: dict, titre_piece: str, branding: dict | None):
    from docx import Document
    from docx.enum.section import WD_SECTION
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.shared import Cm, Pt, RGBColor

    doc = Document()
    sec = doc.sections[0]
    sec.page_height, sec.page_width = Cm(29.7), Cm(21.0)
    sec.left_margin = sec.right_margin = Cm(2.0)
    sec.top_margin, sec.bottom_margin = Cm(2.0), Cm(1.8)
    st = doc.styles["Normal"]
    st.font.name, st.font.size = "Calibri", Pt(10)
    st.paragraph_format.space_after = Pt(4)
    for lvl, size, color in ((1, 14, VERT), (2, 12, VERT), (3, 11, CUIVRE)):
        h = doc.styles[f"Heading {lvl}"]
        h.font.name, h.font.size, h.font.bold = "Calibri", Pt(size), True
        h.font.color.rgb = RGBColor.from_string(color)
        h.paragraph_format.keep_with_next = True
    fp = sec.footer.paragraphs[0]
    fp.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    r = fp.add_run(f"{projet.get('nom') or 'Projet'} — {titre_piece} — Page ")
    r.font.size = Pt(8)
    _field(fp.add_run(), "PAGE")
    fp.add_run(" / ").font.size = Pt(8)
    _field(fp.add_run(), "NUMPAGES")
    return doc


def _entete(doc, projet: dict, titre: str, sous_titre: str, branding: dict | None):
    from docx.enum.table import WD_TABLE_ALIGNMENT
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.shared import Cm, Pt, RGBColor

    logo = _logo(branding)
    if logo:
        try:
            doc.add_picture(logo, height=Cm(2.0))
        except Exception:  # noqa: BLE001
            pass
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r = p.add_run((projet.get("nom") or "Projet").upper())
    r.bold, r.font.size, r.font.color.rgb = True, Pt(20), RGBColor.from_string(VERT)
    if projet.get("adresse"):
        doc.add_paragraph(projet["adresse"]).alignment = WD_ALIGN_PARAGRAPH.CENTER
    t = doc.add_table(rows=1, cols=1)
    t.alignment = WD_TABLE_ALIGNMENT.CENTER
    c = t.rows[0].cells[0]
    _shade(c, VERT)
    cp = c.paragraphs[0]
    cp.alignment = WD_ALIGN_PARAGRAPH.CENTER
    rr = cp.add_run(titre)
    rr.bold, rr.font.size, rr.font.color.rgb = True, Pt(22), RGBColor(0xFF, 0xFF, 0xFF)
    if sous_titre:
        c2 = c.add_paragraph()
        c2.alignment = WD_ALIGN_PARAGRAPH.CENTER
        r2 = c2.add_run(sous_titre)
        r2.font.size, r2.font.color.rgb = Pt(12), RGBColor.from_string(CREME)
    doc.add_paragraph()


def _tableau(doc, rows: list[tuple[str, str]]):
    from docx.shared import Cm
    rows = [(k, v) for k, v in rows if v]
    if not rows:
        return
    tb = doc.add_table(rows=len(rows), cols=2)
    tb.style = "Table Grid"
    for i, (k, v) in enumerate(rows):
        a, b = tb.rows[i].cells
        a.width, b.width = Cm(5), Cm(12)
        _shade(a, CREME)
        a.paragraphs[0].add_run(k).bold = True
        b.paragraphs[0].add_run(str(v))
    doc.add_paragraph()


def _acteurs(projet: dict) -> list[tuple[str, str]]:
    return [("Maître d'ouvrage", projet.get("maitre_ouvrage")), ("Maître d'œuvre", projet.get("maitre_oeuvre")), *intervenants(projet)]


def _save(doc) -> bytes:
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


def _p(doc, texte: str):
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    doc.add_paragraph(texte).alignment = WD_ALIGN_PARAGRAPH.JUSTIFY


def liste_pieces(projet: dict, lots: list[dict]) -> list[tuple[str, list[str]]]:
    ecrites = ["RC — Règlement de consultation", "Clauses générales communes à tous les corps d'état (TCE)"]
    ecrites += [f"CCTP Lot n°{l['numero']:02d} — {l['titre']}" for l in lots]
    ecrites.append("Cadre de DPGF (décomposition du prix global et forfaitaire), tous lots")
    graph = [str(x).strip() for x in (projet.get("plans") or []) if str(x).strip()]
    out = [("Pièces écrites", ecrites)]
    out.append(("Pièces graphiques", graph or ["Plans de l'architecte et des bureaux d'études (liste à compléter)"]))
    return out


# ---------------------------------------------------------------------------------------------
def page_garde_docx(projet: dict, lots: list[dict], branding: dict | None = None) -> bytes:
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.shared import Pt, RGBColor

    doc = _base(projet, "Page de garde DCE", branding)
    _entete(doc, projet, "DOSSIER DE CONSULTATION DES ENTREPRISES", "D.C.E.", branding)
    t = doc.add_table(rows=1, cols=len(PHASES))
    t.style = "Table Grid"
    for i, ph in enumerate(PHASES):
        c = t.rows[0].cells[i]
        run = c.paragraphs[0].add_run(ph)
        run.font.size = Pt(7)
        c.paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.CENTER
        if ph == (projet.get("phase") or "DCE"):
            _shade(c, CUIVRE)
            run.bold, run.font.color.rgb = True, RGBColor(0xFF, 0xFF, 0xFF)
    doc.add_paragraph()
    _tableau(doc, _acteurs(projet) + [("Date", projet.get("date") or date.today().strftime("%d/%m/%Y")),
                                      ("Indice", projet.get("indice") or "A")])
    doc.add_heading("SOMMAIRE DU DOSSIER", 1)
    num = 1
    for groupe, items in liste_pieces(projet, lots):
        doc.add_heading(groupe, 2)
        for it in items:
            doc.add_paragraph(f".{num}  {it}")
            num += 1
    _p(doc, "Les pièces graphiques jointes au présent dossier font partie intégrante du DCE. En cas de discordance entre "
            "pièces, l'entreprise le signalera par écrit au maître d'œuvre avant la remise de son offre.")
    return _save(doc)


# ---------------------------------------------------------------------------------------------
def clauses_tce_docx(projet: dict, lots: list[dict], branding: dict | None = None) -> bytes:
    doc = _base(projet, "Clauses générales TCE", branding)
    _entete(doc, projet, "CLAUSES GÉNÉRALES TCE", "Communes à tous les corps d'état — CCTP Lot n°00", branding)
    nature = {"neuf": "la construction", "renovation": "la rénovation"}.get(projet.get("nature"), "la réalisation")
    sections: list[tuple[str, list[str]]] = [
        ("Objet du document", [
            f"Le présent document définit les clauses techniques et d'organisation communes à l'ensemble des lots de "
            f"l'opération « {projet.get('nom') or 'Projet'} » ({nature}{', ' + projet['adresse'] if projet.get('adresse') else ''}). "
            "Il complète le CCTP de chaque lot ; chaque entreprise est réputée en avoir pris connaissance.",
            *( [projet["description"]] if projet.get("description") else [] )]),
        ("Décomposition en lots", [f"Lot n°{l['numero']:02d} — {l['titre']}" for l in lots]),
        ("Caractère forfaitaire du prix", [
            "Les travaux sont traités à prix global et forfaitaire. Du seul fait de la remise de son offre, l'entrepreneur "
            "reconnaît s'être rendu sur les lieux, avoir apprécié les accès, les contraintes et l'importance des travaux, et "
            "avoir étudié l'ensemble des pièces du dossier. Il devra l'intégralité des travaux nécessaires au complet "
            "achèvement de ses ouvrages, sans pouvoir se prévaloir d'erreurs, d'omissions ou d'insuffisances des plans et "
            "pièces écrites qu'il n'aurait pas signalées avant la remise de son offre.",
            "Les quantités portées au cadre de DPGF sont indicatives : l'entrepreneur établit son propre quantitatif sous sa "
            "responsabilité."]),
        ("Réglementation et documents de référence", [
            "Les travaux seront exécutés conformément aux lois, décrets, arrêtés, normes NF et EN, NF DTU, Eurocodes, Avis "
            "Techniques et règles professionnelles en vigueur à la date de remise des offres, ainsi qu'aux prescriptions des "
            "fabricants. Chaque CCTP de lot précise les documents propres à son corps d'état."]),
        ("Coordination et plans d'exécution", [
            "Chaque entrepreneur établit ses plans d'exécution, de réservations et ses détails, qu'il soumet au visa du "
            "maître d'œuvre avant exécution. Il se coordonne avec les autres lots pour les réservations, incorporations, "
            "raccords et interfaces ; il vérifie les supports livrés et formule ses réserves écrites avant intervention.",
            "Les entreprises assistent aux réunions de chantier sur convocation du maître d'œuvre ; les comptes rendus "
            "valent ordre de service pour les décisions qui y sont consignées."]),
        ("Hygiène, sécurité et protection de la santé", [
            "Lorsque l'opération y est soumise (loi n° 93-1418 du 31 décembre 1993), un coordonnateur SPS est désigné par le "
            "maître d'ouvrage. Chaque entreprise respecte le Plan Général de Coordination (PGC) et remet son Plan Particulier "
            "de Sécurité et de Protection de la Santé (PPSPS) avant toute intervention.",
            "Les travaux à proximité des réseaux font l'objet des déclarations préalables réglementaires (DT-DICT)."]),
        ("Installations de chantier", [
            "Les installations communes de chantier (clôtures, accès, branchements provisoires, sanitaires, stockage) sont "
            "à la charge du lot désigné au CCTP correspondant ; leur répartition financière éventuelle entre lots relève du "
            "CCAP ou de la convention de compte prorata."]),
        ("Délais d'exécution", [
            f"Le délai d'exécution est de {projet['delai']}." if projet.get("delai") else
            "Le délai global d'exécution et les délais partiels sont fixés à l'acte d'engagement et au planning contractuel.",
            "Les pénalités de retard éventuelles sont fixées au CCAP."]),
        ("Échantillons et validation des fournitures", [
            "Les fiches techniques, procès-verbaux, Avis Techniques et échantillons des matériaux et équipements sont soumis "
            "au visa du maître d'œuvre et au choix du maître d'ouvrage avant toute commande."]),
        ("Gestion des déchets et propreté du chantier", [
            "Chaque entreprise trie, évacue et justifie l'élimination de ses déchets vers des filières autorisées, nettoie sa "
            "zone de travail au fur et à mesure et remet les lieux en état de propreté avant réception."]),
        ("Réception des travaux", [
            "La réception est prononcée à la demande de la partie la plus diligente, contradictoirement, avec ou sans "
            "réserves (article 1792-6 du Code civil). Avant les opérations préalables à la réception, chaque entreprise "
            "aura réalisé ses essais et autocontrôles et remis ses procès-verbaux."]),
        ("Garanties", [
            "Garantie de parfait achèvement : un an à compter de la réception (article 1792-6 du Code civil).",
            "Garantie de bon fonctionnement des éléments d'équipement dissociables : deux ans minimum (article 1792-3 du Code civil).",
            "Responsabilité décennale : dix ans pour les dommages compromettant la solidité de l'ouvrage ou le rendant impropre "
            "à sa destination (articles 1792 et 1792-2 du Code civil)."]),
        ("Assurances", [
            "Chaque entreprise justifie, avant la signature du marché, d'une assurance de responsabilité décennale couvrant les "
            "activités exercées sur l'opération (article L241-1 du Code des assurances) et d'une assurance de responsabilité "
            "civile professionnelle, par des attestations en cours de validité."]),
        ("Dossier des ouvrages exécutés (DOE)", [
            "À l'achèvement de ses travaux, chaque entreprise remet son DOE : plans conformes à exécution, fiches techniques, "
            "notices d'entretien et de maintenance, procès-verbaux et attestations réglementaires (Consuel, essais…)."]),
    ]
    for i, (titre, paras) in enumerate(sections, 1):
        doc.add_heading(f"0.{i} {titre.upper()}", 2)
        for x in paras:
            if titre == "Décomposition en lots":
                doc.add_paragraph(x, style="List Bullet")
            else:
                _p(doc, x)
    return _save(doc)


# ---------------------------------------------------------------------------------------------
def rc_docx(projet: dict, lots: list[dict], branding: dict | None = None) -> bytes:
    rc = projet.get("consultation") or {}
    doc = _base(projet, "Règlement de consultation", branding)
    _entete(doc, projet, "RÈGLEMENT DE CONSULTATION", "R.C.", branding)
    doc.add_heading("1. OBJET DE LA CONSULTATION", 2)
    nature = {"neuf": "la construction", "renovation": "la rénovation"}.get(projet.get("nature"), "la réalisation")
    _p(doc, f"La présente consultation porte sur les travaux de {nature} de l'opération « {projet.get('nom') or 'Projet'} »"
            f"{' située ' + projet['adresse'] if projet.get('adresse') else ''}.")
    doc.add_heading("2. INTERVENANTS", 2)
    _tableau(doc, _acteurs(projet))
    doc.add_heading("3. DÉCOMPOSITION EN LOTS", 2)
    _p(doc, "Les travaux sont répartis en lots séparés ; une entreprise peut répondre à un ou plusieurs lots, en "
            "présentant une offre distincte par lot.")
    for l in lots:
        doc.add_paragraph(f"Lot n°{l['numero']:02d} — {l['titre']}", style="List Bullet")
    doc.add_heading("4. VARIANTES", 2)
    _p(doc, "Les variantes sont admises à condition que l'offre de base soit remise et que chaque variante soit chiffrée "
            "séparément, avec sa justification technique." if rc.get("variantes", True) else
            "Les variantes ne sont pas admises.")
    doc.add_heading("5. CONTENU DU DOSSIER DE CONSULTATION", 2)
    for groupe, items in liste_pieces(projet, lots):
        doc.add_paragraph(groupe).runs[0].bold = True
        for it in items:
            doc.add_paragraph(it, style="List Bullet")
    doc.add_heading("6. VISITE DES LIEUX", 2)
    _p(doc, rc.get("visite") or "Une visite des lieux est vivement recommandée ; ses modalités sont à convenir avec le maître "
                                "d'œuvre. Aucune réclamation fondée sur la méconnaissance des lieux ne sera admise.")
    doc.add_heading("7. CONTENU DE L'OFFRE", 2)
    for x in ["Le cadre de DPGF du ou des lots, entièrement complété, daté et signé",
              "Un mémoire technique (moyens humains et matériels, méthodologie, fiches techniques des produits proposés)",
              "Un planning prévisionnel d'exécution",
              "Les attestations d'assurance de responsabilité décennale et de responsabilité civile en cours de validité",
              "Un extrait Kbis (ou équivalent) de moins de trois mois",
              "L'attestation de vigilance URSSAF de moins de six mois (article L8222-1 du Code du travail)",
              "Des références de chantiers comparables"]:
        doc.add_paragraph(x, style="List Bullet")
    doc.add_heading("8. DATE LIMITE ET MODALITÉS DE REMISE DES OFFRES", 2)
    _p(doc, f"Les offres seront remises au plus tard le {rc['date_limite']}" if rc.get("date_limite") else
            "Les offres seront remises au plus tard à la date indiquée dans la lettre de consultation")
    doc.paragraphs[-1].add_run(f", {rc['remise']}." if rc.get("remise") else ", par voie électronique au maître d'œuvre.")
    doc.add_heading("9. DÉLAI DE VALIDITÉ DES OFFRES", 2)
    _p(doc, f"Le délai de validité des offres est de {int(rc.get('validite_jours') or 90)} jours à compter de la date limite de remise.")
    doc.add_heading("10. JUGEMENT DES OFFRES", 2)
    crit = rc.get("criteres") or [("Prix des prestations", None), ("Valeur technique (mémoire technique)", None), ("Délais d'exécution", None)]
    for c in crit:
        nom, poids = (c if isinstance(c, (list, tuple)) else (c.get("nom"), c.get("poids")))
        doc.add_paragraph(f"{nom}" + (f" : {poids} %" if poids else ""), style="List Bullet")
    if not any((c[1] if isinstance(c, (list, tuple)) else c.get("poids")) for c in crit):
        _p(doc, "La pondération des critères est fixée par le maître d'ouvrage. Le maître d'ouvrage se réserve le droit de "
                "négocier avec les candidats ayant remis les offres les plus intéressantes.")
    doc.add_heading("11. RENSEIGNEMENTS COMPLÉMENTAIRES", 2)
    _p(doc, "Les questions des candidats sont adressées par écrit au maître d'œuvre"
            + (f" ({projet['maitre_oeuvre']})" if projet.get("maitre_oeuvre") else "")
            + " ; les réponses sont communiquées à l'ensemble des candidats consultés.")
    return _save(doc)
