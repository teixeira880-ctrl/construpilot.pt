"""Note de calcul A4 + revue automatique du dossier (le « vérificateur »)."""
from __future__ import annotations

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import PageBreak, SimpleDocTemplate, Spacer, Table, TableStyle

from . import brand as _brand
from . import draw  # noqa: F401  (enregistre les polices)
from .i18n import protect, tr
from .profiles import profile
from . import spec as SPEC
from . import schema as SCHEMA

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
SMH = ParagraphStyle("smh", parent=SM, fontName="DVB", textColor=colors.white)


def _restyle():
    """Styles aux couleurs de l'entreprise (appelé à chaque rendu)."""
    br = _brand.get()
    for st, font, size, lead in ((H1, "TT", 15, 18), (H2, "TTS", 11.5, 14)):
        st.fontName, st.fontSize, st.leading, st.textColor = font, size, lead, br.accent
    H1.spaceBefore, H1.spaceAfter = 10, 5
    P.fontName, P.fontSize, P.leading = "DV", 8.6, 12
    P.textColor = SM.textColor = colors.Color(0.15, 0.17, 0.20)
    SM.fontName, SM.fontSize, SM.leading = "DV", 7.4, 9.6


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
    br = _brand.get()
    t.setStyle(TableStyle([("LINEBELOW", (0, 0), (-1, -1), 0.25, colors.Color(0.84, 0.85, 0.87)), ("VALIGN", (0, 0), (-1, -1), "TOP"),
                           ("BACKGROUND", (0, 0), (-1, 0), br.tint), ("LINEBELOW", (0, 0), (-1, 0), 1.0, br.accent2)]))
    return t


def _t(rows, widths, head=True, zebra=True):
    br = _brand.get()
    data = [[Paragraph(str(c), SMH if (head and i == 0) else SM) for c in r] for i, r in enumerate(rows)]
    t = Table(data, colWidths=[w * mm for w in widths], repeatRows=1 if head else 0)
    st = [("LINEBELOW", (0, 0), (-1, -1), 0.25, colors.Color(0.84, 0.85, 0.87)), ("VALIGN", (0, 0), (-1, -1), "TOP"),
          ("LEFTPADDING", (0, 0), (-1, -1), 4), ("RIGHTPADDING", (0, 0), (-1, -1), 4),
          ("TOPPADDING", (0, 0), (-1, -1), 2.6), ("BOTTOMPADDING", (0, 0), (-1, -1), 2.6)]
    if head:
        st += [("BACKGROUND", (0, 0), (-1, 0), br.accent), ("LINEBELOW", (0, 0), (-1, 0), 1.0, br.accent2)]
    if zebra:
        for i in range(1, len(rows)):
            if i % 2 == 0:
                st.append(("BACKGROUND", (0, i), (-1, i), br.tint2))
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
    a("ok" if r["masonry"]["material"] == hyp["masonry"] else "bloquant", f"Murs demandés « {SPEC.of(m)['brick_name']} » → calculés en {SPEC.of(m)['brick']} (EN 1996)")
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
    if (m.raw.get("project") or {}).get("country", "FR") != "PT":
        need += [("Ventilation", code_of("vmc", first.id)), ("Schéma de ventilation", code_of("vmc_schema")),
                 ("Schéma hydraulique chauffage", code_of("hydro")), ("Coupe-type plancher et déperditions", code_of("pc_detail"))]
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


HYP_LABEL = {"poutrelles_hourdis": "Planchers poutrelles-hourdis", "brique_porotherme_20": "murs brique Porotherme 20 cm",
             "brique_isobric_20": "murs à partir du RDC en brique Isobric 20 cm", "brique_20": "murs brique 20 cm",
             "bloc_a_bancher_20": "murs du sous-sol en blocs à bancher 20 cm", "voile_ba_20": "murs du sous-sol en voiles BA 20",
             "charpente_traditionnelle": "charpente traditionnelle", "XC2": "semelles BA classe XC2"}


def _hyp_text(m) -> str:
    uh = m.raw.get("user_hypotheses", {})
    out = []
    for k, v in uh.items():
        if k.startswith("_"):
            continue
        if k == "basement_slab_cm":
            if m.levels and m.levels[0].floor_top < -1.0:
                out.append(f"dallage du sous-sol BA {v} cm")
            continue
        if k == "basement_wall" and not (m.levels and m.levels[0].floor_top < -1.0):
            continue
        out.append(HYP_LABEL.get(str(v), str(v)))
    return " ; ".join(out)


def _write_note(path, m, r, tim, e, p, tot, rev, sheets):
    prof = profile(m.raw["project"].get("country"))
    sec = [0]

    def H(title):
        sec[0] += 1
        return Paragraph(f"{sec[0]}. {title}", H1)
    doc = SimpleDocTemplate(str(path), pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm, topMargin=24 * mm, bottomMargin=20 * mm,
                            title=tr("Note de calcul — ", _LANG[0]) + m.raw["project"]["name"])
    pr = m.raw["project"]
    _restyle()
    s = [PageBreak()]                 # page 1 = couverture dessinée par _cover
    from reportlab.platypus import Paragraph as _P0
    s.append(_P0(_T("Données d'entrée et statut"), H1))
    s.append(_t([["Document d'entrée", "Référence"],
                 ["Permis de construire", f"{pr['pc_ref']} — {pr['architect']}"],
                 ["Étude géotechnique", pr["g2_ref"]],
                 ["Hypothèses du client", _hyp_text(m)],
                 ["Normes", prof["norms_text"]]],
                [45, 133]))
    hyp_rows = SCHEMA.hypotheses_rows(m.raw)
    if hyp_rows:
        s.append(Spacer(1, 3 * mm))
        s.append(Paragraph("Hypothèses retenues et sources", H2))
        s.append(_t([["Donnée", "Valeur retenue", "Source"]] + [list(r) for r in hyp_rows[:40]], [70, 60, 48]))
    notes = [str(n) for n in (m.raw.get("extraction_notes") or [])][:8]
    if notes:
        s.append(Spacer(1, 2 * mm))
        s.append(Paragraph("Notes de lecture : " + " ; ".join(notes), P))
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
        rows.append(["Sous-sol", f"{SPEC.of(m)['bw_buried']} + dallage BA 20 sur GNT", f"Poussée K0 + {m.geo['retaining']['neighbour_surcharge_kpa']} kPa mitoyens : {r['basement']['walls'][0]['face_terre']} face terre"])
    rows += [["Planchers", fl["label_system"], f"Portée {fl['span']} m, L/h = {fl['slenderness']}, M nervure {fl['M_rib']} kN.m"],
             ["Murs", f"Brique {SPEC.of(m)['brick']} joint mince + chaînages BA", f"Taux maxi {worst['ratio']*100:.0f} % ({worst['level']} {'mitoyens' if wmit else worst['file']})"],
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
                 [f"Mur {SPEC.of(m)['brick']} + enduit + doublage", f"{ld['g_wall']} kN/m²", "fabricant / EN 1991-1-1"],
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

    s.append(H(f"Maçonnerie porteuse {SPEC.of(m)['brick']}"))
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
    if prof["country"] != "PT":
        from .hvac import hvac as _hvac
        hv = _hvac(m, p["stacks"])
        loss, v = hv["loss"], hv["vmc"]
        th = m.raw.get("thermal")
        if th and th.get("U"):
            fr = lambda v, n=0: f"{v:.{n}f}".replace(".", ",")
            s.append(H("Étude thermique RE2020 (préalable aux plans) — isolation et épaisseur des parois"))
            s.append(Paragraph("Aucune étude thermique n'étant fournie, le moteur RE2020 ConstruPilot a été exécuté AVANT les calculs de structure : "
                               "il retient la solution la plus économique qui passe toutes les exigences avec 3 % de marge, puis l'épaisseur des murs "
                               "qui en découle est reportée dans les plans, le métré et le devis. Pré-étude indicative : l'étude thermique réglementaire "
                               "(logiciel évalué Th-BCE 2020) et l'attestation de dépôt de PC restent à produire par un thermicien.", P))
            s.append(_t([["Indicateur", "Valeur", "Seuil", "Résultat"]] +
                        [[k, fr(th[a], 1), fr(th[b], 1), "OK" if th[a] <= th[b] else "KO"] for k, a, b in
                         (("Bbio", "Bbio", "Bbio_max"), ("Cep,nr (kWhep/m².an)", "Cep_nr", "Cep_nr_max"), ("Cep (kWhep/m².an)", "Cep", "Cep_max"),
                          ("Ic énergie (kg éq. CO2/m²)", "Ic_energie", "Ic_energie_max"), ("DH (°C.h)", "DH", "DH_max"))] +
                        [["Classe énergie (DPE neuf)", f"{fr(th['cep_dpe'])} kWhEP · {fr(th['ges'], 1)} kgCO2", "—", th["classe"]]], [62, 46, 30, 30]))
            U, e = th["U"], th["thickness_mm"]
            attic = bool(m.roof.get("habitable_attic"))
            s.append(_t([["Paroi", "Composition retenue", "U (W/m².K)", "Épaisseur"]] + [
                ["Murs extérieurs", f"{SPEC.of(m)['brick_name']} + doublage PSE graphité λ 0,032 « 10 + {e['doublage']} »", fr(U["mur"], 3),
                 f"{fr(th['wall_total'], 2)} m + enduit"],
                (["Rampants", f"Laine minérale {e['rampants']} mm entre et sous chevrons", fr(U["rampants"], 3), f"{e['rampants']} mm"] if attic else
                 ["Plancher des combles", f"Laine minérale soufflée {e['combles']} mm λ 0,046", fr(U["combles"], 3), f"{e['combles']} mm"]),
                ["Plancher bas", f"Polyuréthane {e['sous_chape']} mm λ 0,022 sous chape" + (" (sur sous-sol non chauffé)" if m.levels[0].floor_top < -1 else ""),
                 fr(U["plancher_bas"], 3), f"{e['sous_chape']} mm"],
                ["Menuiseries", f"Uw {fr(U['fenetre'], 1)}, g 0,45, volets roulants", fr(U["fenetre"], 2), "—"],
                ["Ponts thermiques", "rupteurs en about de planchers" if th.get("psi", 0.22) <= 0.15 else "traitement courant (ITI)",
                 f"ψ {fr(th.get('psi', 0.22), 2)} /m²Sref", "—"],
            ], [36, 86, 22, 34]))
            sy = th.get("systems") or {}
            s.append(Paragraph("• Systèmes : PAC air/eau (SCOP 4) sur plancher chauffant" + (" réversible (rafraîchissement)" if sy.get("refroidissement") else "")
                               + ", ECS par chauffe-eau thermodynamique, " + ("VMC double flux" if th.get("ventilation") == "vmc_df" else "VMC simple flux hygro B")
                               + f" ; Sref {fr(th['sref'], 1)} m² ; zone {th['zone']}.", P))
            if th.get("baies_manque_m2", 0) > 0:
                s.append(Paragraph(f"• Exigence de moyens « surface de baies ≥ 1/6 de la surface habitable » NON tenue au PC ({fr(th['baies_m2'], 1)} m² "
                                   f"pour {fr(th['sref'] / 6, 1)} m²) : ajouter ≈ {fr(th['baies_manque_m2'], 1)} m² de vitrage, de préférence au Sud.", P))
        s.append(H("Génie climatique — déperditions, chauffage, ventilation"))
        for x in [f"Choix retenus : chauffage {hv['options']['heating'].replace('_', ' ')}, ventilation {v['system']}, isolation intérieure "
                  f"{hv['options']['insulation_mm']} mm ({', '.join(f'{k} : {w}' for k, w in hv['options']['source'].items())}).",
                  f"Déperditions (NF EN 12831 simplifiée) : {loss['total_w']} W pour {loss['a_heated']} m² chauffés, soit {loss['w_m2']} W/m², "
                  f"Tint {loss['t_int']:.0f} °C / Tbase {loss['t_base']} °C (département {loss['dept']}).",
                  f"{hv['pac']['label']} : besoin {hv['pac']['need_kw']} kW (relance + 10 %)" + (f", froid ≈ {hv['pac']['cooling_kw']} kW." if hv['options']['cooling'] else "."),
                  hv["pac"]["outdoor"]] + ((hv["pc"]["rules"] + [hv["pc"]["regime"]]) if hv.get("pc") else []) + v["rules"]:
            s.append(Paragraph("• " + x, P))
        s.append(_t([["Niveau", "Pièce", "Surface", "Déperditions", "W/m²"]] +
                    [[x["level"], x["room"], f"{x['area']:.1f} m²", f"{x['phi_w']} W", str(x["w_m2"])] for x in loss["rooms"]], [18, 70, 28, 34, 22]))
        if hv.get("pc"):
            s.append(_t([["Boucle", "Pièce", "Surface", "Pas", "Longueur", "Débit"]] +
                        [[l["id"], l["room"], f"{l['area']:.1f} m²", f"{int(l['pitch']*100)} cm", f"{l['length_m']} m", f"{l['flow_lh']} l/h"]
                         for lv in hv["pc"]["levels"] for l in lv["loops"]], [22, 62, 26, 20, 24, 24]))
        s.append(_t([["Niveau", "Pièce", "Bouche", "Débit base / pointe"]] +
                    [[b["level"], b["room"], b["kind"], f"{b['q']} / {b['q_pointe']} m³/h"] for b in v["bouches"]], [20, 70, 40, 48]))
    s.append(H("Devis estimatif"))
    vat = tot.get("vat", 0.20)
    s.append(_t([["Lot", "Montant € HT"]] + [[k, f"{v:,.0f}".replace(",", " ")] for k, v in tot["lots"].items()] +
                [["TOTAL HT", f"{tot['ht']:,.0f}".replace(",", " ")], [f"TVA {vat*100:.0f} %", f"{tot['tva']:,.0f}".replace(",", " ")], ["TOTAL TTC", f"{tot['ttc']:,.0f}".replace(",", " ")]],
                [120, 40]))
    s.append(Paragraph(f"Prix unitaires indicatifs {prof['price_ref_long']} (fourni-posé, HT) ; détail ligne par ligne et formules dans le fichier Excel. "
                       + ("Hors lots : menuiseries, plâtrerie, revêtements, peinture, VRD." if prof["country"] != "PT" else "Hors lots : menuiseries, plâtrerie, chapes, revêtements, peinture, chauffage, VRD."), SM))
    if prof["country"] != "FR":
        s.append(Paragraph(prof["vat_note"], SM))

    s.append(H("Revue du dossier (vérificateur)"))
    s.append(_t([["Contrôle", "Résultat"]] + [[x["message"], x["level"].upper()] for x in rev["items"]], [150, 28]))
    s.append(H("Liste des planches"))
    s.append(_t([["Planche", "Titre", "Échelle"]] + [[x.code, x.title, f"1:{x.scale}" if x.scale < 1000 else "s.e."] for x in sheets], [20, 140, 18]))
    s.append(Spacer(1, 6 * mm))
    s.append(Paragraph("Ingénieur responsable (nom, visa, date) : ________________________________", P))
    doc.build(s, onFirstPage=lambda c, d: _cover(c, d, m, rev, tot, sheets, prof),
              onLaterPages=lambda c, d: _header_footer(c, d, m))


def _short(t: str, n: int) -> str:
    """Valeur de cartouche tronquée proprement (les références de PC / G2 peuvent être longues)."""
    t = str(t)
    return t if len(t) <= n else t[: n - 1].rstrip(" ,;—-(") + "…"


# ------------------------------------------------------------------ mise en page premium
COVER = {
    "pt": {"DOSSIER D'ÉTUDE TECHNIQUE": "PROCESSO DE ESTUDO TÉCNICO",
           "Structure, gros œuvre, charpente, électricité, plomberie et devis": "Estrutura, alvenarias, cobertura, eletricidade, águas e esgotos e orçamento",
           "PROJET": "PROJETO", "Permis / projet": "Licenciamento / projeto", "Étude de sol": "Estudo geotécnico",
           "Indice / date": "Revisão / data", "Planches": "Desenhos", "Estimation": "Estimativa", "Normes": "Normas",
           "STATUT DU DOSSIER : ": "ESTADO DO PROCESSO : ",
           "Pré-dimensionnement à faire viser et signer par un ingénieur structure avant exécution.": "Pré-dimensionamento a verificar e assinar por engenheiro de estruturas antes da execução.",
           "Contenu du dossier": "Conteúdo do processo", "Note de calcul et revue du dossier": "Memória de cálculo e revisão do processo",
           "Gros œuvre — plans d'exécution cotés": "Estrutura e alvenarias — desenhos de execução cotados", "Charpente": "Cobertura (estrutura de madeira)",
           "Électricité": "Eletricidade", "Plomberie sanitaire": "Águas e esgotos",
           "Devis et métré (Excel à formules) · plans DXF": "Medições e orçamento (Excel com fórmulas) · desenhos DXF",
           "HT": "s/ IVA", "étude ConstruPilot": "estudo ConstruPilot",
           "Étude réalisée avec ConstruPilot — calculs Eurocodes déterministes, contrôle automatique du dossier.": "Estudo realizado com ConstruPilot — cálculos Eurocódigos determinísticos, revisão automática do processo.",
           "ConstruPilot — calculs Eurocodes déterministes, contrôle automatique du dossier.": "ConstruPilot — cálculos Eurocódigos determinísticos, revisão automática do processo.",
           "Pré-dimensionnement à faire viser par un ingénieur structure": "Pré-dimensionamento a verificar por engenheiro de estruturas",
           "PRÊT POUR VISA BET": "PRONTO PARA VERIFICAÇÃO DO ENGENHEIRO", "Données d'entrée et statut": "Dados de base e estado"},
}


def _T(x):
    d = COVER.get(_LANG[0])
    if d is not None and x in d:
        return d[x]
    return tr(x, _LANG[0])


def _cover(c, doc, m, rev, tot, sheets, prof):
    if _brand.get().style == "pt":
        return _cover_pt(c, doc, m, rev, tot, sheets, prof)
    from reportlab.pdfbase.pdfmetrics import stringWidth
    br = _brand.get()
    _brand.watermark(c, A4[0] / 2, 70 * mm, 120 * mm, br)
    W, H = A4
    pr = m.raw["project"]
    ink, grey = colors.Color(0.12, 0.14, 0.17), colors.Color(0.42, 0.45, 0.49)
    c.saveState()
    # bandeau supérieur
    band = 92 * mm
    c.setFillColor(br.accent)
    c.rect(0, H - band, W, band, stroke=0, fill=1)
    c.setFillColor(br.accent2)
    c.rect(0, H - band - 2.2 * mm, W, 2.2 * mm, stroke=0, fill=1)
    # carte logo
    c.setFillColor(colors.white)
    c.roundRect(18 * mm, H - 46 * mm, 62 * mm, 30 * mm, 2.5 * mm, stroke=0, fill=1)
    _brand.draw_logo(c, 22 * mm, H - 42 * mm, 54 * mm, 22 * mm, br, align="c")
    # identité entreprise (à droite)
    c.setFillColor(colors.white)
    c.setFont("TTS", 12.5)
    c.drawRightString(W - 18 * mm, H - 22 * mm, br.name or "ConstruPilot")
    c.setFont("DV", 7.6)
    yy = H - 27.5 * mm
    for ln in br.lines[:4]:
        c.drawRightString(W - 18 * mm, yy, ln[:80])
        yy -= 3.9 * mm
    # titre
    c.setFont("DVM", 9)
    c.drawString(18 * mm, H - 60 * mm, _T("DOSSIER D'ÉTUDE TECHNIQUE").upper())
    title = _T("Structure, gros œuvre, charpente, électricité, plomberie et devis")
    size = 24
    c.setFont("TT", size)
    words, lines, cur = title.split(), [], ""
    for w_ in words:
        if stringWidth((cur + " " + w_).strip(), "TT", size) > W - 36 * mm:
            lines.append(cur)
            cur = w_
        else:
            cur = (cur + " " + w_).strip()
    lines.append(cur)
    yy = H - 71 * mm
    if len(lines) > 2:
        size = 20
        c.setFont("TT", size)
        lines, cur = [], ""
        for w_ in words:
            if stringWidth((cur + " " + w_).strip(), "TT", size) > W - 36 * mm:
                lines.append(cur)
                cur = w_
            else:
                cur = (cur + " " + w_).strip()
        lines.append(cur)
    for ln in lines[:3]:
        c.drawString(18 * mm, yy, ln)
        yy -= size * 0.42 * mm
    # projet
    y = H - band - 20 * mm
    c.setFillColor(br.accent2)
    c.setFont("DVB", 7.6)
    c.drawString(18 * mm, y, _T("PROJET").upper())
    c.setFillColor(ink)
    c.setFont("TT", 17)
    nm = _T(pr["name"])
    while stringWidth(nm, "TT", 17) > W - 36 * mm and len(nm) > 20:
        nm = nm[:-2]
    c.drawString(18 * mm, y - 8 * mm, nm if nm == _T(pr["name"]) else nm.rstrip() + "…")
    c.setFont("DV", 10)
    c.setFillColor(grey)
    c.drawString(18 * mm, y - 14.5 * mm, _T(pr["address"])[:95])
    # grille d'informations
    gy = y - 30 * mm
    cells = [(_T("Permis / projet"), _short(_T(f"{pr.get('pc_ref', '—')}"), 44)), (_T("Étude de sol"), _short(_T(str(pr.get("g2_ref", "—"))), 44)),
             (_T("Indice / date"), f"A · {pr.get('date', '')}"), (_T("Planches"), f"{len(sheets)} (PDF + DXF)"),
             (_T("Estimation"), f"{tot['ht']:,.0f} € ".replace(",", " ") + _T("HT")), (_T("Normes"), _T(prof["norms_text"])[:60] + "…")]
    cw = (W - 36 * mm) / 2
    for i, (k, v) in enumerate(cells):
        cx, cy = 18 * mm + (i % 2) * cw, gy - (i // 2) * 15 * mm
        c.setStrokeColor(colors.Color(0.86, 0.87, 0.89))
        c.setLineWidth(0.4)
        c.line(cx, cy - 4.5 * mm, cx + cw - 6 * mm, cy - 4.5 * mm)
        c.setFillColor(grey)
        c.setFont("DV", 7)
        c.drawString(cx, cy + 3.2 * mm, k.upper())
        c.setFillColor(ink)
        c.setFont("DVM", 9)
        c.drawString(cx, cy - 1.8 * mm, v[:64])
    # statut
    sy = gy - 52 * mm
    ok = rev["blocking"] == 0
    stc = colors.Color(0.10, 0.48, 0.30) if ok else colors.Color(0.72, 0.12, 0.10)
    c.setFillColor(stc)
    c.roundRect(18 * mm, sy, W - 36 * mm, 15 * mm, 2 * mm, stroke=0, fill=1)
    c.setFillColor(colors.white)
    c.setFont("DVB", 10)
    c.drawString(24 * mm, sy + 8.6 * mm, _T("STATUT DU DOSSIER : ") + _T(rev["status"]))
    c.setFont("DV", 7.4)
    c.drawString(24 * mm, sy + 3.6 * mm, _T("Pré-dimensionnement à faire viser et signer par un ingénieur structure avant exécution.")[:120])
    # sommaire
    ty = sy - 12 * mm
    c.setFillColor(br.accent)
    c.setFont("TTS", 11)
    c.drawString(18 * mm, ty, _T("Contenu du dossier"))
    c.setFillColor(br.accent2)
    c.rect(18 * mm, ty - 2.2 * mm, 14 * mm, 0.7 * mm, stroke=0, fill=1)
    groups = [(_T("Note de calcul et revue du dossier"), "A4"),
              (_T("Gros œuvre — plans d'exécution cotés"), ", ".join(x.code for x in sheets if x.code.startswith("GO"))),
              (_T("Charpente"), ", ".join(x.code for x in sheets if x.code.startswith("CH"))),
              (_T("Électricité"), ", ".join(x.code for x in sheets if x.code.startswith("EL"))),
              (_T("Plomberie sanitaire"), ", ".join(x.code for x in sheets if x.code.startswith("PL"))),
              ("Ventilation", ", ".join(x.code for x in sheets if x.code.startswith("VE"))),
              ("Chauffage / rafraîchissement", ", ".join(x.code for x in sheets if x.code.startswith("CC"))),
              (_T("Devis et métré (Excel à formules) · plans DXF"), "XLSX · DXF")]
    yy = ty - 8 * mm
    for k, v in groups:
        if not v:
            continue
        c.setFillColor(ink)
        c.setFont("DV", 8.4)
        c.drawString(18 * mm, yy, k)
        c.setFillColor(grey)
        c.setFont("DV", 7.4)
        vv = v if len(v) < 60 else v.split(", ")[0] + " … " + v.split(", ")[-1]
        c.drawRightString(W - 18 * mm, yy, vv)
        c.setStrokeColor(colors.Color(0.90, 0.91, 0.92))
        c.line(18 * mm, yy - 2.2 * mm, W - 18 * mm, yy - 2.2 * mm)
        yy -= 7 * mm
    # pied
    c.setFillColor(br.tint2)
    c.rect(0, 0, W, 16 * mm, stroke=0, fill=1)
    c.setFillColor(grey)
    c.setFont("DV", 6.4)
    if br.legal:
        c.drawString(18 * mm, 9.5 * mm, br.legal[:150])
    c.drawString(18 * mm, 5.2 * mm, _T("Étude réalisée avec ConstruPilot — calculs Eurocodes déterministes, contrôle automatique du dossier.") if br.is_client
                 else _T("ConstruPilot — calculs Eurocodes déterministes, contrôle automatique du dossier."))
    c.restoreState()


def _header_footer(c, doc, m):
    br = _brand.get()
    W, H = A4
    grey = colors.Color(0.45, 0.47, 0.50)
    _brand.watermark(c, W / 2, H / 2 - 10 * mm, 120 * mm, br)
    c.saveState()
    if br.style == "pt":
        c.setFillColor(br.accent)
        c.rect(0, 0, 6 * mm, H, stroke=0, fill=1)
        c.setFillColor(br.accent2)
        c.rect(6 * mm, 0, 0.9 * mm, H, stroke=0, fill=1)
        _brand.draw_logo(c, W - 48 * mm, H - 16.5 * mm, 30 * mm, 9 * mm, br, align="r")
        c.setFillColor(grey)
        c.setFont("DV", 7)
        c.drawString(18 * mm, H - 11 * mm, _T("Note de calcul et revue du dossier"))
        c.setFont("DVM", 7)
        c.drawString(18 * mm, H - 14.5 * mm, _T(m.raw["project"]["name"])[:80])
    else:
        _brand.draw_logo(c, 18 * mm, H - 16.5 * mm, 30 * mm, 9 * mm, br)
        c.setFillColor(grey)
        c.setFont("DV", 7)
        c.drawRightString(W - 18 * mm, H - 11 * mm, _T("Note de calcul et revue du dossier"))
        c.setFont("DVM", 7)
        c.drawRightString(W - 18 * mm, H - 14.5 * mm, _T(m.raw["project"]["name"])[:90])
    c.setStrokeColor(br.accent)
    c.setLineWidth(0.8)
    c.line(18 * mm, H - 18.5 * mm, W - 18 * mm, H - 18.5 * mm)
    c.setStrokeColor(br.accent2)
    c.line(18 * mm, H - 18.5 * mm, 40 * mm, H - 18.5 * mm)
    c.setStrokeColor(colors.Color(0.86, 0.87, 0.89))
    c.setLineWidth(0.4)
    c.line(18 * mm, 13 * mm, W - 18 * mm, 13 * mm)
    c.setFont("DV", 6.4)
    c.drawString(18 * mm, 9 * mm, (br.name or "ConstruPilot") + (" — " + _T("étude ConstruPilot") if br.is_client else "") + " · " +
                 _T("Pré-dimensionnement à faire viser par un ingénieur structure"))
    c.setFont("DVB", 7)
    c.setFillColor(br.accent)
    c.drawRightString(W - 18 * mm, 9 * mm, f"{doc.page}")
    c.restoreState()


def _cover_pt(c, doc, m, rev, tot, sheets, prof):
    """Couverture « PT » : colonne latérale pleine hauteur (identité) + contenu à droite."""
    from reportlab.pdfbase.pdfmetrics import stringWidth
    br = _brand.get()
    W, H = A4
    pr = m.raw["project"]
    ink, grey = colors.Color(0.12, 0.14, 0.17), colors.Color(0.42, 0.45, 0.49)
    col = 68 * mm

    def wrap_(txt, font, size, maxw):
        out, cur = [], ""
        for w_ in txt.split():
            if stringWidth((cur + " " + w_).strip(), font, size) > maxw:
                out.append(cur)
                cur = w_
            else:
                cur = (cur + " " + w_).strip()
        return out + [cur]
    c.saveState()
    _brand.watermark(c, col + (W - col) / 2, H / 2 - 20 * mm, 105 * mm, br)
    c.setFillColor(br.accent)
    c.rect(0, 0, col, H, stroke=0, fill=1)
    c.setFillColor(br.accent2)
    c.rect(col, 0, 1.6 * mm, H, stroke=0, fill=1)
    c.setFillColor(colors.white)
    c.roundRect(10 * mm, H - 48 * mm, col - 20 * mm, 32 * mm, 2.5 * mm, stroke=0, fill=1)
    _brand.draw_logo(c, 13 * mm, H - 44 * mm, col - 26 * mm, 24 * mm, br, align="c")
    c.setFillColor(colors.white)
    c.setFont("TTS", 12)
    c.drawString(10 * mm, 62 * mm, (br.name or "ConstruPilot")[:28])
    c.setFont("DV", 7)
    yy = 56 * mm
    for ln in br.lines[:4]:
        for part in (ln[:44], ln[44:88]):
            if part:
                c.drawString(10 * mm, yy, part)
                yy -= 3.7 * mm
    c.setFont("DV", 6)
    cred = _T("Étude réalisée avec ConstruPilot — calculs Eurocodes déterministes, contrôle automatique du dossier.") if br.is_client else "ConstruPilot"
    for i, ln in enumerate(wrap_(cred, "DV", 6, col - 18 * mm)[:3]):
        c.drawString(10 * mm, 18 * mm - i * 3 * mm, ln)
    x0, wr = col + 14 * mm, W - col - 30 * mm

    def wrap(txt, font, size, maxw):
        out, cur = [], ""
        for w_ in txt.split():
            if stringWidth((cur + " " + w_).strip(), font, size) > maxw:
                out.append(cur)
                cur = w_
            else:
                cur = (cur + " " + w_).strip()
        return out + [cur]
    c.setFillColor(br.accent2)
    c.setFont("DVB", 8)
    c.drawString(x0, H - 30 * mm, _T("DOSSIER D'ÉTUDE TECHNIQUE").upper())
    c.setFillColor(br.accent)
    y = H - 42 * mm
    for ln in wrap(_T("Structure, gros œuvre, charpente, électricité, plomberie et devis"), "TT", 22, wr)[:4]:
        c.setFont("TT", 22)
        c.drawString(x0, y, ln)
        y -= 9.5 * mm
    y -= 8 * mm
    c.setFillColor(br.accent2)
    c.setFont("DVB", 7.6)
    c.drawString(x0, y, _T("PROJET").upper())
    c.setFillColor(ink)
    y -= 7 * mm
    for ln in wrap(_T(pr["name"]), "TTS", 14, wr)[:3]:
        c.setFont("TTS", 14)
        c.drawString(x0, y, ln)
        y -= 6 * mm
    c.setFillColor(grey)
    c.setFont("DV", 9)
    c.drawString(x0, y - 1 * mm, _T(pr["address"])[:70])
    y -= 16 * mm
    cells = [(_T("Permis / projet"), _short(_T(f"{pr.get('pc_ref', '—')}"), 44)), (_T("Étude de sol"), _short(_T(str(pr.get("g2_ref", "—"))), 44)),
             (_T("Indice / date"), f"A · {pr.get('date', '')}"), (_T("Planches"), f"{len(sheets)} (PDF + DXF)"),
             (_T("Estimation"), f"{tot['ht']:,.0f} € ".replace(",", " ") + _T("HT"))]
    for k, v in cells:
        c.setFillColor(grey)
        c.setFont("DV", 6.8)
        c.drawString(x0, y, k.upper())
        c.setFillColor(ink)
        c.setFont("DVM", 9)
        c.drawString(x0, y - 4.6 * mm, v[:60])
        c.setStrokeColor(colors.Color(0.86, 0.87, 0.89))
        c.setLineWidth(0.4)
        c.line(x0, y - 7 * mm, x0 + wr, y - 7 * mm)
        y -= 13 * mm
    ok = rev["blocking"] == 0
    c.setFillColor(colors.Color(0.10, 0.48, 0.30) if ok else colors.Color(0.72, 0.12, 0.10))
    c.roundRect(x0, y - 12 * mm, wr, 16 * mm, 2 * mm, stroke=0, fill=1)
    c.setFillColor(colors.white)
    st = _T("STATUT DU DOSSIER : ") + _T(rev["status"])
    c.setFont("DVB", 9 if stringWidth(st, "DVB", 9) < wr - 8 * mm else 7.6)
    c.drawString(x0 + 4 * mm, y - 2.5 * mm, st)
    c.setFont("DV", 6.6)
    for i, ln in enumerate(wrap(_T("Pré-dimensionnement à faire viser et signer par un ingénieur structure avant exécution."), "DV", 6.6, wr - 8 * mm)[:2]):
        c.drawString(x0 + 4 * mm, y - 6.5 * mm - i * 3 * mm, ln)
    y -= 26 * mm
    c.setFillColor(br.accent)
    c.setFont("TTS", 11)
    c.drawString(x0, y, _T("Contenu du dossier"))
    y -= 6 * mm
    groups = [(_T("Note de calcul et revue du dossier"), "A4"),
              (_T("Gros œuvre — plans d'exécution cotés"), "GO"), (_T("Charpente"), "CH"), (_T("Électricité"), "EL"),
              (_T("Plomberie sanitaire"), "PL"), ("Ventilation", "VE"), ("Chauffage / rafraîchissement", "CC"),
              (_T("Devis et métré (Excel à formules) · plans DXF"), "XLSX")]
    for k, code in groups:
        n = sum(1 for x in sheets if x.code.startswith(code)) if code not in ("A4", "XLSX") else 0
        if code not in ("A4", "XLSX") and not n:
            continue
        c.setFillColor(br.accent2)
        c.circle(x0 + 1 * mm, y + 1 * mm, 0.8 * mm, stroke=0, fill=1)
        c.setFillColor(ink)
        c.setFont("DV", 8)
        c.drawString(x0 + 4 * mm, y, k + (f"  ({n})" if n else ""))
        y -= 5.6 * mm
    if br.legal:
        c.setFillColor(grey)
        c.setFont("DV", 6)
        c.drawString(x0, 12 * mm, br.legal[:110])
    c.restoreState()
