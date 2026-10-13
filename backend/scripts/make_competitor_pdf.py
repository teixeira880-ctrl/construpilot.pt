"""Génère le PDF comparatif ConstruPilot vs 10 concurrents BTP (matrice + fiches)."""
import sys
from datetime import date

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Image, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

FONT_DIR = "/usr/share/fonts/truetype/freefont/"
pdfmetrics.registerFont(TTFont("Sans", FONT_DIR + "FreeSans.ttf"))
pdfmetrics.registerFont(TTFont("Sans-Bold", FONT_DIR + "FreeSansBold.ttf"))
pdfmetrics.registerFont(TTFont("Sans-Italic", FONT_DIR + "FreeSansOblique.ttf"))

GREEN = colors.HexColor("#1f6f4a")
DARK = colors.HexColor("#111827")
GREY = colors.HexColor("#6b7280")
LIGHT = colors.HexColor("#f3f4f6")
ACCENT_BG = colors.HexColor("#e8f5ee")
GRID = colors.HexColor("#d1d5db")

S = {
    "title": ParagraphStyle("t", fontName="Sans-Bold", fontSize=22, leading=26, textColor=DARK),
    "sub": ParagraphStyle("s", fontName="Sans", fontSize=10.5, leading=14, textColor=GREY),
    "h2": ParagraphStyle("h2", fontName="Sans-Bold", fontSize=14, leading=18, textColor=GREEN, spaceBefore=6, spaceAfter=4),
    "body": ParagraphStyle("b", fontName="Sans", fontSize=9.2, leading=12.5, textColor=DARK),
    "small": ParagraphStyle("sm", fontName="Sans", fontSize=7.8, leading=10, textColor=GREY),
    "cell": ParagraphStyle("c", fontName="Sans", fontSize=7, leading=8.8, textColor=DARK),
    "cellc": ParagraphStyle("cc", fontName="Sans", fontSize=6.6, leading=8.2, textColor=DARK, alignment=TA_CENTER),
    "cellb": ParagraphStyle("cb", fontName="Sans-Bold", fontSize=7, leading=8.8, textColor=DARK),
    "head": ParagraphStyle("h", fontName="Sans-Bold", fontSize=7.4, leading=9, textColor=colors.white, alignment=TA_CENTER),
    "headl": ParagraphStyle("hl", fontName="Sans-Bold", fontSize=7.4, leading=9, textColor=colors.white),
    "note": ParagraphStyle("n", fontName="Sans-Italic", fontSize=7.8, leading=10, textColor=GREY),
}

Y, P, N = "Y", "P", "N"
MARK = {Y: "<font color='#1f6f4a'><b>OUI</b></font>", P: "<font color='#b45309'><b>PARTIEL</b></font>", N: "<font color='#b91c1c'><b>NON</b></font>"}

# Ordre des colonnes
COMP = ["ConstruPilot", "OBAT", "Vertuoza", "Alobees", "Kalitics", "BatiChiffrage", "Renalto", "Costructor", "BTPBip", "Batappli", "Tolteck"]

# Matrice : critère -> liste alignée sur COMP de (niveau, note courte)
MATRIX = [
    ("Application native iOS / Android (stores)", [(Y, "3 apps : Chantier, Collaborateur, Particuliers + PWA/push"), (Y, "app mobile, sans hors ligne"), (Y, "apps Admin, Chantier, Intervention"), (Y, "app ouvriers iOS/Android"), (P, "web mobile sans installation"), (P, "web responsive"), (Y, "app iOS/Android + WhatsApp"), (P, "web PC/tablette/mobile"), (P, "PWA hors ligne"), (Y, "app terrain"), (Y, "apps + hors ligne")]),
    ("Particuliers (maîtres d'ouvrage) : compte dédié", [(Y, "app ConstruPilot Particuliers : estimation, calculateurs, coach IA"), (N, ""), (N, ""), (N, ""), (N, ""), (P, "estimatifs pour MOE/diagnostiqueurs"), (N, ""), (N, ""), (N, ""), (N, ""), (N, "")]),
    ("Professionnels (artisans, entreprises)", [(Y, "app ConstruPilot Chantier + web : Premium, Pro, Pro Business"), (Y, ""), (Y, ""), (Y, ""), (Y, ""), (Y, ""), (Y, ""), (Y, ""), (Y, ""), (Y, ""), (Y, "")]),
    ("Collaborateurs / équipe (rôles, accès, pointage)", [(Y, "app ConstruPilot Collaborateur : rôles, pointage, comptes rendus"), (Y, "multi-utilisateurs selon pack"), (Y, "droits personnalisables (Expert)"), (Y, "licences illimitées"), (Y, "45 € / utilisateur"), (N, "mono-utilisateur"), (P, "3 utilisateurs (PME)"), (P, "utilisateurs suppl. Business+/Premium"), (Y, "tarif par employé"), (P, "+19 € / utilisateur"), (N, "solo")]),
    ("Clients & sous-traitants externes (accès invité)", [(Y, "portail OTP par chantier, droits fins, cloisonné"), (N, ""), (P, "partage documents"), (P, "partage client"), (P, "portail limité"), (N, ""), (N, ""), (Y, "portail client"), (P, ""), (N, ""), (N, "")]),
    ("Devis, factures, avoirs, situations", [(Y, "révisions tracées, signés figés"), (Y, "acomptes, situations, avoirs"), (Y, ""), (N, "via Sage/EBP/Codial"), (Y, "multi-lots, retenues"), (Y, "offre Devis-Factures"), (P, "devis → facture, pas de situations"), (Y, "acomptes, situations, avoirs"), (Y, ""), (Y, "acomptes, situations, relances"), (Y, "acompte, avancement, finale")]),
    ("Facturation électronique Factur-X", [(Y, "natif + validation EN16931"), (Y, "via Iopole"), (Y, ""), (N, ""), (Y, "certifiée"), (P, "annoncée"), (Y, "PRO+ / PME"), (Y, "Peppol"), (Y, ""), (Y, "via Cecurity"), (Y, "via plateforme tierce")]),
    ("Signature électronique client", [(Y, "horodatée, PDF figé"), (Y, ""), (Y, ""), (N, ""), (Y, ""), (Y, "illimitée"), (N, ""), (Y, ""), (Y, ""), (P, "paiement Stripe, signature limitée"), (N, "")]),
    ("Bibliothèque de prix", [(Y, "catalogue + prix entreprise, provenance"), (Y, "30 000 ouvrages régionalisés"), (Y, "base + composants"), (N, ""), (P, "catalogues via API"), (Y, "80 000 prix — référence"), (P, "500 à 5 000 ouvrages"), (Y, "Batiprix intégrée"), (Y, ""), (Y, "Batichiffrage incluse (1 lot)"), (Y, "ouvrages + tarifs fournisseurs")]),
    ("Devis généré par IA / dictée vocale", [(Y, "dictée → devis, TVA contrôlée"), (N, ""), (Y, "vocal ≈ 45 s"), (N, ""), (N, ""), (P, "édition assistée"), (Y, "cœur : voix, WhatsApp, photo, DPGF"), (Y, "création assistée IA"), (P, "assistant Bip (pilotage, extraction)"), (N, ""), (N, "")]),
    ("Lecture de plans & métrés (PDF, DWG, Revit, IFC)", [(Y, "métré traçable, Autodesk, 3 IA vision"), (N, ""), (P, "import DPGF"), (N, ""), (N, ""), (N, ""), (N, "DPGF seulement"), (N, ""), (N, ""), (N, ""), (N, "")]),
    ("Diagnostic technique IA (désordres)", [(Y, "Solveur BTP sourcé + devis"), (N, ""), (N, ""), (N, ""), (N, ""), (N, ""), (N, ""), (N, ""), (N, ""), (N, ""), (N, "")]),
    ("Suivi de chantier (comptes rendus, photos, réserves)", [(Y, "dossier continu, réserves, rappels"), (Y, "Gantt, rentabilité"), (Y, "pack PRO+"), (Y, "cœur du produit"), (Y, "rapports, GED"), (P, "planning simple"), (N, ""), (Y, "Gantt/Kanban, documents"), (Y, ""), (Y, "offre Artisan"), (N, "")]),
    ("Planning équipes & pointage RH", [(Y, "pointage mobile, selfie"), (Y, "pointage heures"), (Y, "pack Ultime"), (Y, "planning de charge, paie"), (Y, "planning partagé"), (N, ""), (N, ""), (Y, "feuilles d'heures"), (Y, "+ formations, flotte, SAV"), (P, "bons d'intervention"), (N, "")]),
    ("Radar de chantiers (permis de construire)", [(Y, "données officielles, filtres"), (N, ""), (N, ""), (N, ""), (N, ""), (N, ""), (N, ""), (N, ""), (N, ""), (N, ""), (N, "")]),
    ("Page publique entreprise + demandes de devis", [(Y, "vitrine, galerie → CRM"), (N, ""), (N, ""), (N, ""), (N, ""), (N, ""), (N, ""), (N, ""), (N, ""), (N, ""), (N, "")]),
    ("CRM & relances", [(Y, "leads assignés, relances"), (Y, ""), (Y, "CRM avancé"), (P, ""), (Y, "Kanban, workflows"), (P, "règlements"), (P, "paiements clients"), (Y, "connexion bancaire"), (Y, "trésorerie"), (Y, "relances impayés"), (P, "statuts documents")]),
    ("Achats, stocks, fournisseurs", [(P, "approvisionnement"), (P, "sous-traitants"), (Y, "pack Ultime"), (N, ""), (Y, "commandes, BL, scan"), (N, ""), (N, ""), (P, ""), (Y, ""), (Y, "stocks, commandes"), (N, "")]),
    ("Rentabilité par chantier", [(Y, "KPIs, couverture des coûts"), (Y, "temps réel"), (Y, ""), (P, "CA par chantier"), (Y, "compte de résultat"), (N, ""), (N, ""), (Y, "déboursé sec, marges"), (Y, ""), (P, ""), (P, "marges")]),
    ("Vocal terrain (dicter / écouter)", [(Y, "notes, réserves, portail, lecture audio"), (N, ""), (P, "devis vocal"), (N, ""), (N, ""), (N, ""), (Y, "dictée du devis"), (N, ""), (P, "assistant vocal"), (N, ""), (N, "")]),
    ("Multilingue", [(Y, "7 langues, fiscalité FR/PT"), (N, "FR"), (P, "FR, NL"), (N, "FR"), (N, "FR"), (N, "FR"), (N, "FR"), (N, "FR"), (N, "FR"), (N, "FR"), (N, "FR")]),
    ("Mode hors ligne", [(N, ""), (N, ""), (P, "apps mobiles"), (P, ""), (P, ""), (N, ""), (N, ""), (N, ""), (Y, "PWA synchronisée"), (P, "app mobile"), (Y, "")]),
    ("API ouverte / intégrations", [(Y, "API, Stripe, Autodesk, Resend"), (P, "export comptable"), (Y, "comptabilité"), (Y, "Sage, EBP, Lucca, Silae"), (Y, "~200 points REST"), (P, "export tiers"), (P, "Sage Batigest, CSV"), (Y, "banque, comptabilité"), (Y, "Google Calendar, Sage, EBP"), (Y, "300 tarifs fournisseurs"), (P, "tarifs fournisseurs")]),
]

# Fiches : (nom, positionnement, cible, tarif HT/mois, mise en route, lecture ConstruPilot)
FICHES = [
    ("ConstruPilot", "Plateforme BTP complète avec IA : du plan au paiement, client inclus", "Particuliers (app gratuite), artisans/PME (app Chantier), collaborateurs (app Collaborateur), clients & sous-traitants (portail)", "Particulier 0 € · Premium 19 € · Pro 149 € · Pro Business 249 €, sans engagement", "Immédiate, essai libre, aucun accompagnement payant",
     "Seul du panel à couvrir les 4 publics (particulier, pro, collaborateur, invité externe) avec 3 applications natives dédiées (Chantier, Collaborateur, Particuliers) et à réunir métré depuis plans, diagnostic IA sourcé, radar et page publique. Limite : pas de mode hors ligne complet."),
    ("OBAT", "Devis-factures + suivi de chantier pour artisans/TPE", "Micro-entrepreneurs, artisans, TPE/PME ≤ 50", "25 € à 109 € selon pack et statut (annuel) ; option Batichiffrage ≈ 12 €", "Essai 14 jours",
     "Très bon rapport qualité/prix pour l'artisan : bibliothèque régionalisée, Factur-X via Iopole. Pas d'IA, pas de plans, pas de portail client, pas de prospection."),
    ("Vertuoza", "ERP tout-en-un par packs (TPE → PME)", "PME structurées, multi-équipes (FR, BE)", "Sur devis (4 packs PRO → Ultime)", "Démo commerciale",
     "ERP bien pensé pour la PME qui grandit (stocks, RH, compta), devis vocal IA. Tarif opaque, pas de métré depuis plans, pas de diagnostic ni de radar."),
    ("Alobees", "Planning & suivi terrain (pas de facturation)", "Entreprises avec équipes terrain", "Sur devis, licences illimitées", "Essai 14 jours + démo 1 h",
     "Excellent sur la communication bureau ↔ terrain et le planning de charge. Dépend d'un second logiciel pour devis/factures. Aucune IA."),
    ("Kalitics", "ERP BTP web/mobile, du chiffrage au compte de résultat", "PME/ETI, conducteurs de travaux, multi-sociétés", "45 € / utilisateur + prestation de déploiement obligatoire", "Chef de projet dédié (payant)",
     "ERP solide : compte de résultat par chantier, achats/stocks, API ouverte. Déploiement long et payant, pas d'IA métier ni de portail client complet."),
    ("BatiChiffrage", "Bibliothèque de prix + logiciels Devis-Factures / Estimatifs", "Artisans, architectes, MOE, diagnostiqueurs", "37 € à 60 € selon offre et durée", "Essai, paiement 3× sans frais",
     "La référence des bibliothèques de prix (80 000 prix fourni-posés). Chiffrage avant tout : pas de suivi de chantier, RH, portail ni plans."),
    ("Renalto", "Devis-factures IA « Rita » pour la rénovation / second œuvre", "Artisans et petites PME de rénovation", "PRO 25 € · PRO+ 30 € · PME 49 € (3 utilisateurs) ; devis IA plafonnés 30–100/mois", "Essai 14 jours, sans engagement",
     "Concurrent le plus proche sur le devis vocal IA (voix, WhatsApp, photo de notes, DPGF). Périmètre limité au devis-facture : ni chantier, ni RH, ni plans, ni portail, ni signature."),
    ("Costructor", "Devis-facturation + suivi de chantier 100 % en ligne, version gratuite illimitée", "Artisans, TPE, PME", "Gratuit (devis/factures illimités) · Pro 15 € · Business+ 30 € · Premium 60 €", "Essai 14 jours",
     "Offre gratuite agressive, Batiprix, CEE/MaPrimeRénov', portail client, Peppol. IA limitée à l'aide à la rédaction ; pas de plans, diagnostic, radar ni RH avancée."),
    ("BTPBip", "Tout-en-un 32 modules (devis, planning, trésorerie, flotte, SAV)", "Artisans et PME (SIRET requis)", "40 € / artisan seul ; dégressif par effectif (40 → 5 € / employé) ; −20 % annuel", "Essai 30 jours, migration Excel incluse",
     "Très large couverture (formations, flotte, SAV, hors ligne PWA, assistant vocal Bip). Pas de lecture de plans, de diagnostic IA, de radar ni de page publique ; prix élevé pour les équipes moyennes."),
    ("Batappli", "Devis-factures + gestion artisan (Systemlog / ISAGRI)", "Artisans et TPE", "Devis 39 € · Artisan 79 € ; utilisateur suppl. 19 € ; lot Batichiffrage 9 €", "Essai 10 jours",
     "Solide sur le chiffrage (Batichiffrage, 300 tarifs fournisseurs) et l'administratif. Aucune IA, pas de portail client, pas de plans ; coûts additionnels par utilisateur."),
    ("Tolteck", "Devis-factures simples et rapides pour l'artisan solo", "Artisans indépendants, petites structures", "19 € (annuel) ou 25 € (mensuel) ; −35 % jeunes entreprises", "Essai 30 jours",
     "Prise en main en 5 minutes, hors ligne, tarif unique. Pas de planning, stocks, heures, signature, IA, chantier ni portail : outil d'entrée de gamme."),
]

CP_DIFF = [
    "<b>IA vérifiable, pas de magie</b> (là où Renalto, Vertuoza, Costructor ou BTPBip proposent aussi une aide IA) : chaque prix, quantité ou TVA porte sa provenance (mesuré, saisi, bibliothèque, hypothèse) ; les documents signés sont figés (hash SHA-256) et toute modification crée une révision.",
    "<b>Du plan au devis</b> : import PDF/DWG/Revit/IFC, métré traçable, cascade de 3 IA de vision avec vote (jamais de comptage inventé), export Excel du métré, devis pré-rempli. Aucun des 10 concurrents ne lit un plan.",
    "<b>Solveur BTP</b> : diagnostic d'un désordre (fissure, humidité…) sourcé sur des normes officielles, causes, solutions chiffrées, PDF et devis en un clic. Unique sur le panel.",
    "<b>Prospection intégrée</b> : radar de chantiers (permis de construire officiels, filtres neuf/extension/promoteur…) + page publique entreprise qui génère des demandes de devis directement dans le CRM. Unique sur le panel.",
    "<b>Client dans la boucle</b> : espace client & sous-traitant par chantier (identifiant + code e-mail), avancement, photos, messagerie, signalement de problème → réserve, devis à signer ; tout est cloisonné et publié explicitement par le pro (Costructor propose un portail plus simple).",
    "<b>Terrain mains libres</b> : dicter un compte rendu, une réserve, une note de devis ; écouter une réponse de l'assistant ou un compte rendu.",
    "<b>Quatre publics sur une seule plateforme</b> : le particulier (compte gratuit : estimation, calculateurs, coach IA, suivi de projet — aucun concurrent ne s'adresse à lui), le professionnel, ses collaborateurs (rôles owner / chef de chantier / comptable / ouvrier, pointage mobile) et ses invités externes (clients, sous-traitants). Le particulier d'aujourd'hui devient le client suivi demain dans le portail du pro.",
    "<b>Tarif lisible</b> : 0 € particuliers, 19 € Premium, 149 € Pro, 249 € Pro Business, sans engagement ni prestation de déploiement. Points à surveiller : Costructor (gratuit), Tolteck (19 €) et Renalto (25 €) sont moins chers sur le seul devis-facture.",
    "<b>Trois applications natives, une par public</b> : <b>ConstruPilot Chantier</b> (le professionnel : devis, dossier chantier, plans, assistant), <b>ConstruPilot Collaborateur</b> (l'équipe : pointage, comptes rendus, réserves, planning) et <b>ConstruPilot Particuliers</b> (le maître d'ouvrage : estimation, calculateurs, coach IA, suivi de projet), disponibles sur Android et iPhone, complétées par la version web/PWA avec notifications push. Les concurrents proposent au mieux une application unique orientée pro ou ouvrier ; aucun n'a d'application pour le particulier. Point à consolider : le mode hors ligne complet (BTPBip, Tolteck).",
]


def _p(text, style="cell"):
    return Paragraph(text, S[style])


def _footer(canvas, doc):
    canvas.saveState()
    canvas.setFont("Sans", 7)
    canvas.setFillColor(GREY)
    canvas.drawString(14 * mm, 8 * mm, f"ConstruPilot — comparatif concurrentiel · {date.today().strftime('%d/%m/%Y')} · Sources : sites éditeurs et comparateurs publics (juin 2026) ; les offres concurrentes évoluent, vérifier avant diffusion commerciale.")
    canvas.drawRightString(doc.pagesize[0] - 14 * mm, 8 * mm, f"Page {doc.page}")
    canvas.restoreState()


def _grid(extra=()):
    return TableStyle([("BACKGROUND", (0, 0), (-1, 0), GREEN), ("VALIGN", (0, 0), (-1, -1), "TOP"), ("GRID", (0, 0), (-1, -1), 0.4, GRID),
                       ("LEFTPADDING", (0, 0), (-1, -1), 3), ("RIGHTPADDING", (0, 0), (-1, -1), 3), ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3), *extra])


def build(out: str) -> None:
    doc = SimpleDocTemplate(out, pagesize=landscape(A4), leftMargin=12 * mm, rightMargin=12 * mm, topMargin=11 * mm, bottomMargin=14 * mm,
                            title="ConstruPilot vs concurrents", author="ConstruPilot")
    w = doc.width
    story = []
    try:
        story.append(Image("/app/frontend/public/construpilot-logo.png", width=42 * mm, height=42 * mm * 0.28, kind="proportional", hAlign="LEFT"))
    except Exception:  # noqa: BLE001
        pass
    story += [Spacer(1, 4), Paragraph("ConstruPilot face aux logiciels BTP du marché", S["title"]),
              Paragraph(" · ".join(COMP[1:]) + " — matrice fonctionnelle, positionnement, tarifs", S["sub"]), Spacer(1, 5),
              Paragraph(f"Légende : {MARK[Y]} inclus &nbsp;&nbsp; {MARK[P]} partiel, via option ou partenaire &nbsp;&nbsp; {MARK[N]} absent — la mention courte précise le périmètre.", S["small"]), Spacer(1, 4)]

    head = [_p("Critère", "headl")] + [_p(c, "head") for c in COMP]
    data = [head]
    for crit, cells in MATRIX:
        assert len(cells) == len(COMP), crit
        data.append([_p(crit, "cellb")] + [_p(MARK[lvl] + (f"<br/>{note}" if note else ""), "cellc") for lvl, note in cells])
    widths = [w * 0.118, w * 0.105] + [(w - w * 0.118 - w * 0.105) / 10] * 10
    t = Table(data, colWidths=widths, repeatRows=1)
    extra = [("BACKGROUND", (1, 1), (1, -1), ACCENT_BG)]
    for i in range(2, len(data), 2):
        extra.append(("BACKGROUND", (0, i), (0, i), LIGHT))
        extra.append(("BACKGROUND", (2, i), (-1, i), LIGHT))
    t.setStyle(_grid(extra))
    story += [t, PageBreak()]

    story += [Paragraph("Fiches : positionnement, cible, tarifs, mise en route", S["h2"])]
    rows = [[_p(h, "headl") for h in ["Éditeur", "Positionnement", "Cible", "Tarif indicatif (HT/mois)", "Mise en route", "Lecture ConstruPilot (forces / limites)"]]]
    for f in FICHES:
        rows.append([_p(f[0], "cellb")] + [_p(x) for x in f[1:]])
    t2 = Table(rows, colWidths=[w * 0.09, w * 0.17, w * 0.14, w * 0.17, w * 0.11, w * 0.32], repeatRows=1)
    t2.setStyle(_grid([("BACKGROUND", (0, 1), (-1, 1), ACCENT_BG)]))
    story += [t2, PageBreak()]

    story += [Paragraph("Ce que ConstruPilot fait et que les autres ne font pas", S["h2"])]
    for d in CP_DIFF:
        story += [Paragraph("• " + d, S["body"]), Spacer(1, 2)]
    story += [Spacer(1, 8), Paragraph("Quand recommander quoi ?", S["h2"]),
              Paragraph("• <b>Artisan solo, devis-factures uniquement</b> : Tolteck, Costructor (gratuit), Renalto (devis IA), OBAT ou Batappli sont les choix économiques — ConstruPilot Premium (19 €) couvre le même périmètre en ajoutant l'IA vérifiable et le portail client.", S["body"]),
              Paragraph("• <b>PME avec équipes terrain</b> : Alobees (planning), BTPBip (tout-en-un) ou Vertuoza (ERP) — ConstruPilot Pro Business ajoute RH/pointage, dossier chantier, portail client, métré depuis plans et prospection sans second logiciel.", S["body"]),
              Paragraph("• <b>Entreprise structurée multi-sociétés avec achats/stocks lourds</b> : Kalitics est plus profond sur l'ERP ; ConstruPilot est plus rapide à déployer et seul à offrir métré depuis plans, diagnostic IA et radar de chantiers.", S["body"]),
              Paragraph("• <b>Chiffrage pur / bibliothèque de prix</b> : BatiChiffrage (aussi intégré à OBAT et Batappli) ou Batiprix (Costructor) restent des références de prix ; ConstruPilot documente la provenance de chaque prix et peut importer un catalogue entreprise.", S["body"]),
              Spacer(1, 8),
              Paragraph("Note : informations concurrentes issues des sites éditeurs (obat.fr, vertuoza.com, alobees.com, kalitics.com, batichiffrage.fr, renalto.fr, costructor.co, btpbip.com, batappli.fr, tolteck.com) et de comparateurs publics consultés en juin 2026. Tarifs ConstruPilot issus du catalogue réel de l'application.", S["note"])]
    doc.build(story, onFirstPage=_footer, onLaterPages=_footer)


if __name__ == "__main__":
    out = sys.argv[1] if len(sys.argv) > 1 else "/app/frontend/public/ConstruPilot_vs_concurrents.pdf"
    build(out)
    print(out)
