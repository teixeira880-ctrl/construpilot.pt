"""Note de calcul A4 + revue automatique du dossier (le « vérificateur »)."""
from __future__ import annotations

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import PageBreak, SimpleDocTemplate, Spacer, Table, TableStyle

from . import draw  # noqa: F401  (enregistre les polices)
from .i18n import protect, tr
from .profiles import profile

_LANG = ["fr"]


def Paragraph(text, style):  # noqa: N802 — traduit au rendu
    from reportlab.platypus import Paragraph as _P
    return _P(tr(text, _LANG[0]), style)


def _fmt(v, n=2):
    return f"{v:.{n}f}".replace(".", ",")

GREEN = colors.Color(0.12, 0.42, 0.27)
H1 = ParagraphStyle("h1", fontName="DVB", fontSize=13, textColor=GREEN, spaceBefore=8, spaceAfter=4)
H2 = ParagraphStyle("h2", fontName="DVB", fontSize=10.5, textColor=GREEN, spaceBefore=6, spaceAfter=3)
P = ParagraphStyle("p", fontName="DV", fontSize=8.6, leading=11.2, alignment=TA_LEFT)
SM = ParagraphStyle("sm", fontName="DV", fontSize=7.4, leading=9.4)
RED = ParagraphStyle("red", parent=P, textColor=colors.Color(0.75, 0.1, 0.1), fontName="DVB")


def _seismic(s, sz):
    """Chapitre sismique (Portugal) — texte rédigé directement en portugais."""
    from reportlab.platypus import Paragraph as _P
    s.append(_P(f"Ação sísmica — NP EN 1998-1 + Anexo Nacional (método das forças laterais)", H1))
    s.append(_P(sz["intro"], P))
    s.append(_t_native([["Parâmetro", "Ação sísmica tipo 1 (afastada)", "Ação sísmica tipo 2 (próxima)"]] +
                       [[k, a, b] for k, a, b in sz["table"]], [52, 63, 63]))
    s.append(Spacer(1, 2 * mm))
    s.append(_t_native([["Piso", "z (m)", "Massa (t)", "F_i (kN)"]] + [[x["level"], _fmt(x["z"]), _fmt(x["m_t"], 1), _fmt(x["F_kN"], 1)] for x in sz["storeys"]],
                       [50, 30, 30, 30]))
    s.append(Spacer(1, 2 * mm))
    s.append(_t_native([["Direção", "Comprimento de paredes (m)", "Área de paredes / área em planta", "V_Ed (kN)", "V_Rd (kN)", "Taxa"]] +
                       [[d["dir"], _fmt(d["length_m"]), f"{d['pA']:.1f} %".replace(".", ","), _fmt(d["V_Ed"], 1), _fmt(d["V_Rd"], 1), f"{d['ratio']*100:.0f} %"] for d in sz["directions"]],
                       [28, 32, 38, 26, 26, 22]))
    for x in sz["notes"]:
        s.append(_P("• " + x, SM))


def _t_native(rows, widths):
    from reportlab.platypus import Paragraph as _P
    data = [[_P(str(c), SM) for c in r] for r in rows]
    t = Table(data, colWidths=[w * mm for w in widths], repeatRows=1)
    t.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.25, colors.Color(0.75, 0.75, 0.75)), ("VALIGN", (0, 0), (-1, -1), "TOP"),
                           ("BACKGROUND", (0, 0), (-1, 0), colors.Color(0.88, 0.94, 0.90))]))
    return t


def _t(rows, widths, head=True, zebra=True):
    data = [[Paragraph(str(c), SM) for c in r] for r in rows]
    t = Table(data, colWidths=[w * mm for w in widths], repeatRows=1 if head else 0)
    st = [("GRID", (0, 0), (-1, -1), 0.25, colors.Color(0.75, 0.75, 0.75)), ("VALIGN", (0, 0), (-1, -1), "TOP"),
          ("LEFTPADDING", (0, 0), (-1, -1), 3), ("RIGHTPADDING", (0, 0), (-1, -1), 3)]
    if head:
        st += [("BACKGROUND", (0, 0), (-1, 0), colors.Color(0.88, 0.94, 0.90))]
    if zebra:
        for i in range(1, len(rows)):
            if i % 2 == 0:
                st.append(("BACKGROUND", (0, i), (-1, i), colors.Color(0.97, 0.97, 0.97)))
    t.setStyle(TableStyle(st))
    return t


def review(m, r, tim, e, p, devis_lines, sheets, model_anomalies) -> dict:
    """Vérificateur : contrôle le dossier produit comme le ferait un BET contrôleur."""
    out = []

    def a(level, msg):
        out.append({"level": level, "message": msg})

    hyp = m.raw["user_hypotheses"]
    a("ok" if r["floors"]["system"] == hyp["floor_system"] else "bloquant",
      f"Plancher demandé « poutrelles-hourdis » → calculé : {r['floors']['slabs'][0]['label_system']}")
    a("ok" if r["masonry"]["material"] == hyp["masonry"] else "bloquant", "Murs demandés « brique Porotherme 20 » → calculés en Porotherme 20 (EN 1996)")
    top = m.levels[-1]
    if "omble" in top.name:
        nch = len([x for x in m.rooms(top.id) if x["type"] == "chambre"])
        nsb = len([x for x in m.rooms(top.id) if x["type"] == "salle_eau"])
        a("ok" if top.use == "habitation" else "bloquant", f"Comble classé habitable (cat. A) — {nch} chambres" + (" + SDB" if nsb else "") + " au PC")
    else:
        a("ok" if top.use.startswith("habitation") else "bloquant", f"Dernier niveau ({top.name}) classé habitation (cat. A)")
    first = next(l for l in m.levels if l.floor_top > -1.0)
    kinds = {}
    for sh in sheets:
        kinds.setdefault(getattr(sh, "kind", ""), []).append(sh)

    def code_of(kind, level=None):
        lst = [x for x in kinds.get(kind, []) if level is None or getattr(x, "level", None) == level]
        return lst[0].code if lst else None
    need = [("Plan de fondations", code_of("fond")), ("Plans de maçonnerie cotés", code_of("level", first.id)),
            ("Plans de planchers", code_of("floor")), ("Coupes", code_of("coupe")), ("Façades", code_of("facade")),
            ("Détails de ferraillage", code_of("detail")), ("Charpente", code_of("charpente")), ("Électricité", code_of("elec", first.id)),
            ("Tableau électrique", code_of("elec_panel")), ("Plomberie", code_of("plumb", first.id)), ("Schéma colonnes", code_of("plumb_riser"))]
    for k, c in need:
        a("ok" if c else "bloquant", f"Livrable « {k} » ({c or '—'}) {'produit' if c else 'MANQUANT'}")
    nlots = len({l["lot"] for l in devis_lines})
    a("ok" if devis_lines else "bloquant", f"Devis chiffré produit ({len(devis_lines)} lignes, {nlots} lots)")
    bmin = m.geo["verified_widths_m"]["filante"]
    for it in r["foundations"]["items"]:
        a("ok" if it["ratio_ELS"] <= 0.90 and it["B"] >= bmin else "bloquant",
          f"{it['label']} : B = {it['B']:.2f} ≥ {_fmt(bmin)} (G2), taux ELS {it['ratio_ELS']*100:.0f} % ≤ 90 %")
    a("ok" if r["masonry"]["ok"] else "bloquant", f"Maçonnerie : taux maxi {r['masonry']['worst']['ratio']*100:.0f} % ({r['masonry']['worst']['file']} {r['masonry']['worst']['level']})")
    a("ok" if all(pp["ok"] for pp in r["lintels"]["posts"]) else "bloquant", "Poteaux de trumeau vérifiés")
    a("ok" if tim["panne_section"] and tim["chevron_section"] else "bloquant", "Charpente : pannes et chevrons vérifiés (flexion + flèche L/200)")
    a("ok" if not any(f["horiz_m"] > 4.0 for f in p["fixtures"]) else "attention", "Plomberie : longueurs d'évacuation ≤ 4 m vers les chutes")
    a("ok", f"Électricité : {e['totals']['pc']} prises, {e['totals']['pl']} points lumineux, {len(e['circuits'])} circuits, {len(e['rcds'])} différentiels")
    if r["floors"]["impact_heights"] > 0:
        a("attention", f"Plancher {r['floors']['slabs'][0]['system']} (h = {r['floors']['slabs'][0]['h']*100:.0f} cm) plus épais que le PC ({r['floors']['pc_thickness']*100:.0f} cm) : "
                       f"+{r['floors']['impact_heights']*100:.0f} cm par niveau à valider avec l'architecte, ou variante dalle alvéolée 20+5")
    for an in model_anomalies:
        a("bloquant" if an["level"] == "bloquant" else "attention", f"Modèle : {an['message']}")
    if r["basement"]["walls"] and any(d["type"] == "mitoyen" for d in m.raw["sides"].values()):
        a("attention", f"Surcharge des fondations voisines prise forfaitairement à {m.geo['retaining']['neighbour_surcharge_kpa']} kPa : à confirmer par la G2 PRO")
    a("attention", f"f_k de la brique ({_fmt(r['masonry']['brick']['fk'], 1)} MPa) et Avis Technique des poutrelles : à confirmer par les DoP / notes fabricants")
    if r.get("seismic"):
        sz = r["seismic"]
        a("ok" if sz["ok"] else "bloquant", f"Séisme (NP EN 1998-1) : effort tranchant à la base {sz['Fb_kN']} kN, taux maxi des murs {sz['worst_ratio']*100:.0f} %")
        a("attention", "Zonage sísmico, classe de terrain et valeurs de a_gR : à confirmer (Anexo Nacional, concelho, estudo geotécnico)")
    a("attention", "Contreventement de la charpente au vent et note de l'escaliéteur : à fournir par les entreprises")
    blocking = [x for x in out if x["level"] == "bloquant"]
    return {"items": out, "blocking": len(blocking), "model_anomalies": model_anomalies,
            "status": "PRÊT POUR VISA BET" if not blocking else "NON PRÊT — anomalies bloquantes"}


def write_note(path, m, r, tim, e, p, tot, rev, sheets, lang="fr"):
    _LANG[0] = lang
    protect(m)
    try:
        return _write_note(path, m, r, tim, e, p, tot, rev, sheets)
    finally:
        _LANG[0] = "fr"


HYP_LABEL = {"poutrelles_hourdis": "Planchers poutrelles-hourdis", "brique_porotherme_20": "murs brique Porotherme 20 cm"}


def _write_note(path, m, r, tim, e, p, tot, rev, sheets):
    prof = profile(m.raw["project"].get("country"))
    sec = [0]

    def H(title):
        sec[0] += 1
        return Paragraph(f"{sec[0]}. {title}", H1)
    doc = SimpleDocTemplate(str(path), pagesize=A4, leftMargin=16 * mm, rightMargin=16 * mm, topMargin=16 * mm, bottomMargin=16 * mm,
                            title=tr("Note de calcul — ", _LANG[0]) + m.raw["project"]["name"])
    pr = m.raw["project"]
    s = []
    s.append(Paragraph("CONSTRUPILOT · BUREAU D'ÉTUDES", ParagraphStyle("b", fontName="DVB", fontSize=10, textColor=GREEN)))
    s.append(Spacer(1, 6 * mm))
    s.append(Paragraph("DOSSIER D'ÉTUDE STRUCTURE, CHARPENTE, ÉLECTRICITÉ, PLOMBERIE ET DEVIS", ParagraphStyle("t", fontName="DVB", fontSize=15, leading=19)))
    s.append(Spacer(1, 3 * mm))
    s.append(Paragraph(pr["name"] + "<br/>" + pr["address"], ParagraphStyle("t2", fontName="DV", fontSize=11, leading=15)))
    s.append(Spacer(1, 4 * mm))
    s.append(_t([["Document d'entrée", "Référence"],
                 ["Permis de construire", f"{pr['pc_ref']} — {pr['architect']}"],
                 ["Étude géotechnique", pr["g2_ref"]],
                 ["Hypothèses du client", " ; ".join(HYP_LABEL.get(v, v) for k, v in m.raw.get("user_hypotheses", {}).items() if not k.startswith("_"))],
                 ["Normes", prof["norms_text"]]],
                [45, 133]))
    s.append(Spacer(1, 5 * mm))
    col = colors.Color(0.1, 0.5, 0.25) if rev["blocking"] == 0 else colors.Color(0.75, 0.1, 0.1)
    s.append(Paragraph(f"STATUT DU DOSSIER : {rev['status']}", ParagraphStyle("st", fontName="DVB", fontSize=12, textColor=col)))
    s.append(Paragraph("Pré-dimensionnement à faire viser et signer par un ingénieur structure avant exécution. Les notes des fabricants "
                       "(poutrelles, escalier) et la mission G2 PRO restent à produire.", P))
    s.append(Spacer(1, 4 * mm))
    fl = r["floors"]["slabs"][0]
    mit = max((i for i in r["foundations"]["items"] if i.get("side") != "cage"), key=lambda i: i["ratio_ELS"])
    gar = max(r["lintels"]["lintels"], key=lambda l: l["M_Ed"]) if r["lintels"]["lintels"] else None
    gar_op = next((o for o in m.openings if gar and o.id == gar["opening"]), None)
    gar_lab = "Garage" if gar_op and "garage" in gar_op.kind else (f"Linteau le plus sollicité {gar['id']}" if gar else "")
    exc = [i for i in r["foundations"]["items"] if i["excentric"]]
    mits = any(m.side(i["side"])["type"] == "mitoyen" for i in exc if i["side"] in m.raw["sides"])
    bnd = [i for i in exc if i["side"] in m.raw["sides"] and m.side(i["side"])["type"] != "mitoyen"]
    where = " et ".join((["mitoyens"] if mits else []) + [("façade rue" if "rue" in m.side(i["side"])["label"].lower() else "façade en limite") for i in bnd])
    zb = -(r["foundations"]["base_depth"] + 0.10)
    worst = r["masonry"]["worst"]
    wmit = worst["side"] in m.raw["sides"] and m.side(worst["side"])["type"] == "mitoyen"
    bsmt = bool(r["basement"]["walls"])
    s.append(Paragraph("Synthèse des solutions", H2))
    rows = [["Ouvrage", "Solution retenue", "Justification"],
            ["Fondations", f"Semelles filantes BA, B = {mit['B']:.2f} m, h = {mit['h']:.2f} m, " + (f"excentrées sous {where}" if where else "centrées sous les murs") + f", arase ≈ {_fmt(zb)}",
             f"σ ELS max {mit['sigma_ELS']} kPa = {mit['ratio_ELS']*100:.0f} % de {r['foundations']['q_els']} kPa (G2)"]]
    if bsmt:
        rows.append(["Sous-sol", "Voiles BA 20 enterrés + dallage BA 20 sur GNT", f"Poussée K0 + {m.geo['retaining']['neighbour_surcharge_kpa']} kPa mitoyens : {r['basement']['walls'][0]['face_terre']} face terre"])
    rows += [["Planchers", fl["label_system"], f"Portée {fl['span']} m, L/h = {fl['slenderness']}, M nervure {fl['M_rib']} kN.m"],
             ["Murs", "Brique Porotherme 20 joint mince + chaînages BA", f"Taux maxi {worst['ratio']*100:.0f} % ({worst['level']} {'mitoyens' if wmit else worst['file']})"],
             ["Linteaux / poteaux", f"{len(r['lintels']['lintels'])} linteaux BA, {len(r['lintels']['posts'])} poteaux de trumeau",
              f"{gar_lab} : {gar['b']*100:.0f}×{gar['h']*100:.0f}, {gar['bottom']} (M = {gar['M_Ed']} kN.m)" if gar else ""],
             ["Charpente", f"Pannes GL24h {tim['panne_section']['label']} sur pignons, chevrons {tim['chevron_section']['label']}", f"Pente {tim['pitch_deg']}°, flèche pannes {tim['panne_section']['w_fin_mm']} mm"],
             ["Électricité", f"{e['totals']['pc']} PC, {e['totals']['pl']} PL, {len(e['circuits'])} circuits, tableau {e['panel']['rows']} rangées", prof["electrical"]],
             ["Plomberie", f"{len(p['fixtures'])} appareils, {len(p['stacks'])} chutes Ø100, CET 200 L" + (f", relevage {m.levels[0].id}" if p["relevage"]["needed"] else ""),
              f"{'DTU 60.11' if prof['country'] == 'FR' else prof['plumbing']} : débit probable {p['flow']['q_probable']} l/s"]]
    if r.get("seismic"):
        sz = r["seismic"]
        rows.append(["Séisme", f"Méthode des forces latérales, q = {_fmt(sz['q'], 1)}", f"F_b = {sz['Fb_kN']} kN ; taux maxi des murs {sz['worst_ratio']*100:.0f} %"])
    rows.append(["Devis", f"{tot['ht']:,.0f} € HT — {tot['ttc']:,.0f} € TTC".replace(",", " "), "Lots GO, charpente-couverture, élec, plomberie (prix indicatifs)"])
    s.append(_t(rows, [28, 80, 70]))
    s.append(PageBreak())

    s.append(H("Données d'entrée relevées sur le PC (modèle bâtiment)"))
    s.append(Paragraph(m.raw["_comment"], P))
    s.append(_t([["Niveau", "Altitude", "Plancher", "HSP", "Usage"]] +
                [[l.name, f"{l.floor_top:+.2f}", f"{l.slab*100:.0f} cm", f"{l.hsp:.2f}", l.use] for l in m.levels] +
                [["Égout / faîtage", f"{m.roof['eaves_level']:+.2f} / {m.roof['ridge_level']:+.2f}", "", "", "toiture 2 pans, pignons = mitoyens"
                  if any(m.side(g)["type"] == "mitoyen" for g in m.roof.get("gables", [])) else "toiture 2 pans sur pignons"]],
                [40, 28, 28, 20, 62]))
    s.append(Spacer(1, 2 * mm))
    s.append(_t([["Baie", "Niveau", "Façade", "Position (m)", "Dimensions"]] +
                [[o.id, o.level, m.side(o.side)["label"], f"{o.a:.2f} → {o.b:.2f}", o.kind] for o in m.openings],
                [26, 16, 50, 26, 60]))
    s.append(Paragraph("Contrôles du modèle avant calcul", H2))
    anomalies = rev["model_anomalies"]
    s.append(Paragraph("Aucune anomalie bloquante." if not any(x["level"] == "bloquant" for x in anomalies) else "ANOMALIES BLOQUANTES — voir ci-dessous.", P))
    for x in anomalies:
        s.append(Paragraph(f"• [{x['level']}] {x['message']} — {x['fix']}", SM))
    s.append(Paragraph("Contrôles effectués : baies dans les murs, trumeaux > 0 (pas de baie comptée deux fois), hauteurs d'étage, HSP des niveaux habités, "
                       "classement du comble, surfaces des pièces vs PC, aucun mur dans la trémie, escalier dans sa cage (giron ≥ 21 cm, Blondel).", SM))

    s.append(H("Charges"))
    ld = r["loads"]
    s.append(_t([["Action", "Valeur", "Origine"],
                 ["Béton armé", "25 kN/m³", "EN 1991-1-1"],
                 ["Mur Porotherme 20 + enduit + doublage", f"{ld['g_wall']} kN/m²", "fabricant / EN 1991-1-1"],
                 ["Finitions planchers (chape, carrelage, plafond)", f"{ld['g_fin']} kN/m²", "hypothèse"],
                 ["Cloisons de distribution", f"{ld['g_clois']} kN/m²", "EN 1991-1-1 §6.3.1.2"],
                 ["Toiture (tuile méca, liteaux, chevrons, isolant, plafond) en rampant", f"{ld['g_roof_slope']} kN/m²", "fabricants"],
                 ["Exploitation habitation / garage (cat. A / F)", "1,5 / 2,5 kN/m²", "EN 1991-1-1 AN"],
                 [f"Neige : s_k ({m.raw['project'].get('snow_region') or m.raw['project'].get('snow_zone', '')}) × μ1", f"{ld['snow_sk']} × {ld['snow_mu']} = {ld['snow_s']} kN/m²", "EN 1991-1-3 AN"],
                 ["Combinaisons", "ELU 1,35 G + 1,5 Q (+ 0,75×1,5 S) ; ELS G + Q + S", "EN 1990"]], [80, 50, 48]))
    for n in ld["notes"]:
        s.append(Paragraph("• " + n, SM))

    s.append(H("Planchers poutrelles-hourdis"))
    for ru in r["floors"]["rules"]:
        s.append(Paragraph("• " + ru, P))
    s.append(_t([["Plancher", "Système", "G / Q (kN/m²)", "q_u", "M_Ed (kN.m/m)", "M nervure", "Réactions G / Q (kN/m)"]] +
                [[x["label"], x["label_system"], f"{x['G']} / {x['Q']}", x["qu"], x["M_per_m"], f"{x['M_rib']} ≤ {x['Mrd_ind']}", f"{x['R_G_per_m']} / {x['R_Q_per_m']}"]
                 for x in r["floors"]["slabs"]], [34, 46, 20, 12, 20, 22, 24]))
    from .structure import HOURDIS, SLENDER_MAX
    pch = r["floors"]["pc_thickness"]
    pcs = next((hh for hh in HOURDIS if abs(hh[1] - pch) < 1e-6), None)
    if pcs and fl["h"] > pch + 1e-6:
        s.append(Paragraph(f"Le système {pcs[0]} ({pch*100:.0f} cm du PC) donne L/h = {r['floors']['span_calc']/pch:.1f} > {SLENDER_MAX:.0f} pour une portée de {r['floors']['span_calc']} m : "
                           f"il est trop élancé. Le {fl['system']}{' jumelé' if fl['twin'] else ''} est retenu. {r['floors']['variant']}", RED))
    else:
        s.append(Paragraph(f"Le système {fl['system']}{' jumelé' if fl['twin'] else ''} retenu est compatible avec l'épaisseur prévue au projet ({pch*100:.0f} cm).", P))

    s.append(H("Descente de charges (kN/m en pied de niveau)"))
    s.append(_t([["File", "Niveau", "Matériau", "G", "Q", "S", "ELS", "ELU"]] +
                [[x["file"], x["level"], x["material"], x["G"], x["Q"], x["S"], x["ELS"], x["ELU"]] for x in r["descent"]["rows"]],
                [52, 14, 26, 16, 16, 14, 18, 18]))
    s.append(Paragraph(f"Toiture sur chaque pignon : G = {r['descent']['roof_G_per_gable']} kN/m, S = {r['descent']['roof_S_per_gable']} kN/m (pannes portant de pignon à pignon).", SM))

    s.append(H("Maçonnerie porteuse Porotherme 20"))
    s.append(Paragraph(r["masonry"]["method"] + f" f_d = f_k/γ_M = {r['masonry']['brick']['fk']}/{r['masonry']['brick']['gamma_m']} = {r['masonry']['fd_MPa']} MPa. " + r["masonry"]["brick"]["note"], P))
    s.append(_t([["Mur", "Niveau", "h (m)", "h_ef/t", "N_Ed (kN/m)", "Φ", "N_Rd (kN/m)", "Taux"]] +
                [[c["file"], c["level"], c["h"], c["hef_t"], c["N_Ed"], c["phi"], c["N_Rd"], f"{c['ratio']*100:.0f} %"] for c in r["masonry"]["checks"]],
                [50, 14, 14, 16, 22, 14, 22, 16]))

    s.append(H("Linteaux, poteaux et chaînages"))
    s.append(_t([["Repère", "Portée", "b × h", "q_u", "M_Ed", "V_Ed", "Aciers inf.", "Cadres"]] +
                [[l["id"], l["span"], f"{l['b']:.2f}×{l['h']:.2f}", l["qu"], l["M_Ed"], l["V_Ed"], l["bottom"], l["stirrups"]] for l in r["lintels"]["lintels"]],
                [24, 14, 20, 16, 16, 16, 22, 30]))
    s.append(Spacer(1, 2 * mm))
    s.append(_t([["Poteau", "Section", "h", "N_Ed", "N_Rd", "λ", "Aciers"]] +
                [[x["id"], x["section"], x["height"], x["N_Ed"], x["N_Rd"], x["lambda"], x["steel"]] for x in r["lintels"]["posts"]],
                [30, 22, 12, 18, 18, 14, 52]))
    for k, v in r["lintels"]["chainages"].items():
        s.append(Paragraph("• " + v, SM))

    if bsmt:
        s.append(H("Voiles enterrés du sous-sol"))
        s.append(Paragraph(r["basement"]["method"], P))
        s.append(_t([["Voile", "q (kPa)", "p tête / pied (kPa)", "Portée", "M_ser", "M_Ed", "As (cm²/m)", "Face terre"]] +
                    [[w["name"], w["q_kpa"], f"{w['p_top']} / {w['p_bot']}", w["span"], w["M_ser"], w["M_Ed"], w["As_req"], w["face_terre"]] for w in r["basement"]["walls"]],
                    [52, 14, 24, 14, 14, 14, 18, 22]))
        for x in r["basement"]["execution"]:
            s.append(Paragraph("• " + x, SM))
        if r["basement"]["note_neighbour"]:
            s.append(Paragraph("• " + r["basement"]["note_neighbour"], SM))

    s.append(H("Fondations (selon G2 AVP)"))
    for x in r["foundations"]["rules"]:
        s.append(Paragraph("• " + x, P))
    s.append(_t([["Semelle", "N ELS / ELU (kN/m)", "B × h", "σ ELS / ELU (kPa)", "Taux ELS / ELU", "Aciers transv.", "Tassement"]] +
                [[i["label"], f"{i['N_ELS']} / {i['N_ELU']}", f"{i['B']:.2f} × {i['h']:.2f}", f"{i['sigma_ELS']} / {i['sigma_ELU']}",
                  f"{i['ratio_ELS']*100:.0f} % / {i['ratio_ELU']*100:.0f} %", i["transversal"], i["settlement"]] for i in r["foundations"]["items"]],
                [44, 24, 18, 24, 22, 20, 26]))
    s.append(H("Dallage et escalier"))
    sg = r["slab_on_grade"]
    for x in (sg["type"], sg["steel"], sg["rule"], sg["joints"]):
        s.append(Paragraph("• " + x, P))
    st = r["stairs"]
    s.append(_t([["Volée", "Hauteur", "Marches", "h (mm)", "g (mm)", "2h + g (mm)"]] +
                [[f"{f['from']} → {f['to']}", f["H"], f["risers"], f["h_mm"], f["g_mm"], f["blondel_mm"]] for f in st["flights"]],
                [30, 22, 22, 22, 22, 26]))
    s.append(Paragraph(st["structure"], SM))

    if r.get("seismic"):
        _seismic(s, r["seismic"])
    s.append(H("Charpente"))
    for x in [tim["type"], tim["panne_material"], tim["sabliere"], tim["ceiling"], tim["bearings"], tim["bracing"], tim["covering"], tim["insulation"]] + tim["checks"]:
        s.append(Paragraph("• " + x, P))

    s.append(H(f"Électricité ({prof['electrical']})"))
    for x in e["rules"]:
        s.append(Paragraph("• " + x, P))
    if prof["country"] == "PT":
        from reportlab.platypus import Paragraph as _P
        s.append(_P("Nota : pré-dimensionamento das instalações elétricas com regras de base equivalentes ; o projeto de especialidade (RTIEBT – Portaria "
                    "949-A/2006 e ITED, 4.ª edição) deve ser elaborado e subscrito por técnico responsável inscrito (DGEG / ANACOM) e certificado pela entidade inspetora.", SM))
    s.append(_t([["ID", "Type", "Circuits"]] + [[x["id"], f"40 A 30 mA type {x['type']}", ", ".join(x["circuits"])] for x in e["rcds"]], [12, 34, 132]))
    s.append(H(f"Plomberie ({'NF DTU 60.11' if prof['country'] == 'FR' else prof['plumbing']})"))
    for x in p["rules"] + [p["ecs"], p["distribution"], p["relevage"]["spec"], p["ventilation"], p["rain"]]:
        if x:
            s.append(Paragraph("• " + x, P))

    if prof["country"] == "PT":
        from reportlab.platypus import Paragraph as _P
        s.append(_P("Nota : redes prediais pré-dimensionadas ; o projeto de especialidade de águas e esgotos segundo o Decreto Regulamentar 23/95 "
                    "(caudais de cálculo, pressões, ventilação e ramais de ligação) e o regulamento da entidade gestora local deve ser elaborado e subscrito por técnico responsável.", SM))
    s.append(H("Devis estimatif"))
    vat = tot.get("vat", 0.20)
    s.append(_t([["Lot", "Montant € HT"]] + [[k, f"{v:,.0f}".replace(",", " ")] for k, v in tot["lots"].items()] +
                [["TOTAL HT", f"{tot['ht']:,.0f}".replace(",", " ")], [f"TVA {vat*100:.0f} %", f"{tot['tva']:,.0f}".replace(",", " ")], ["TOTAL TTC", f"{tot['ttc']:,.0f}".replace(",", " ")]],
                [120, 40]))
    s.append(Paragraph(f"Prix unitaires indicatifs {prof['price_ref_long']} (fourni-posé, HT) ; détail ligne par ligne et formules dans le fichier Excel. "
                       "Hors lots : menuiseries, plâtrerie, chapes, revêtements, peinture, chauffage, VRD.", SM))
    if prof["country"] != "FR":
        s.append(Paragraph(prof["vat_note"], SM))

    s.append(H("Revue du dossier (vérificateur)"))
    s.append(_t([["Contrôle", "Résultat"]] + [[x["message"], x["level"].upper()] for x in rev["items"]], [150, 28]))
    s.append(H("Liste des planches"))
    s.append(_t([["Planche", "Titre", "Échelle"]] + [[x.code, x.title, f"1:{x.scale}" if x.scale < 1000 else "s.e."] for x in sheets], [20, 140, 18]))
    s.append(Spacer(1, 6 * mm))
    s.append(Paragraph("Ingénieur responsable (nom, visa, date) : ________________________________", P))
    doc.build(s)
