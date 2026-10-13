"""Note de ferraillage EN 1992 (PDF) — NON EXÉCUTOIRE, à vérifier par l'ingénieur.

Reprend la SORTIE déterministe de structuro_ec2.design_study (A_s + schéma) et la met
en page pour le dossier. N'introduit aucune nouvelle donnée ni validation de sécurité.
"""
from __future__ import annotations

import io
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle


def build_ferraillage_pdf(model: dict, revision: int, ec2_out: dict) -> bytes:
    out = io.BytesIO()
    doc = SimpleDocTemplate(out, pagesize=landscape(A4), leftMargin=35, rightMargin=35, topMargin=42, bottomMargin=36)
    ss = getSampleStyleSheet()
    ss.add(ParagraphStyle("Tiny", parent=ss["BodyText"], fontSize=8, leading=11))
    p = lambda t: Paragraph(escape(str(t)), ss["Tiny"])
    title = (model or {}).get("title", "Étude de structure")
    story = [Paragraph("ConstruPilot | Note de ferraillage EN 1992", ss["Title"]), p(title),
             p(f"Révision {revision} | moteur {ec2_out.get('version', '')}"),
             Spacer(1, 8),
             Paragraph("FERRAILLAGE — PROPOSITION NON EXÉCUTOIRE — RÉSISTANCE NON VÉRIFIÉE", ss["Heading2"]),
             p("Acier NÉCESSAIRE issu de l'enveloppe EN 1990 (flexion simple/double, effort tranchant, As mini/maxi) "
               "et proposition d'armatures couvrant cet acier. Coefficients usuels AN FR. Aucune disposition "
               "constructive, ancrage, fissuration ni flèche vérifiés — À VÉRIFIER PAR L'INGÉNIEUR."),
             Spacer(1, 6)]

    def table(rows, widths):
        t = Table([[p(c) for c in r] for r in rows], colWidths=widths, repeatRows=1)
        t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e7eee9")),
                               ("GRID", (0, 0), (-1, -1), .3, colors.HexColor("#c5cfca")),
                               ("VALIGN", (0, 0), (-1, -1), "TOP"),
                               ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5)]))
        return t

    head = ["Poutre", "b×h · d (m)", "M dim. (kN·m)", "As flexion (cm²)", "V dim. → Asw/s (cm²/m)",
            "As mini / maxi (cm²)", "Ferraillage (à vérifier)"]
    rows = [head]
    warnings = []
    for r in ec2_out.get("elements", []):
        if r.get("status") != "ok":
            rows.append([r.get("id", "?"), "—", r.get("message", ""), "", "", "", ""])
            continue
        d = r["design"]
        fx, sh, sc = d["flexure"], d["shear"], r.get("scheme") or {}
        mode = f"double (As'={fx['as_comp_cm2']})" if fx["mode"] == "double" else "simple"
        ferr = ""
        if sc:
            ferr = sc["longitudinal"]["label"] + ((" · " + sc["stirrups"]["label"]) if sc.get("stirrups") else "")
            if r.get("reinforcement_source") == "automation":
                ferr = ("auto " + ("OK" if r.get("provided_ok") else "INSUFFISANT") + " · ") + ferr
        rows.append([r["id"], f"{r['b_m']}×{r['h_m']} · {r['d_m']}",
                     f"{r['med_knm']}  [{r.get('med_case', '')}]",
                     f"{fx['as_req_cm2']}  ({mode})",
                     (f"{r['ved_kn']} → {sh['asw_s_req_cm2_m']}" + (f"  cot θ={sh['cot_theta']}" if sh['needs_stirrups'] else "  mini")) if r.get("ved_kn") is not None else "—",
                     f"{fx['as_min_cm2']} / {fx['as_max_cm2']}", ferr])
        for w in d.get("warnings", []):
            warnings.append(f"{r['id']} : {w}")
    story.append(table(rows, [60, 95, 120, 120, 150, 95, 135]))

    if warnings:
        story += [Spacer(1, 8), Paragraph("Signalements", ss["Heading2"])]
        story += [p(w) for w in warnings]
    story += [Spacer(1, 8), p(ec2_out.get("note", ""))]
    combos = (model or {}).get("combinations") or []
    if combos:
        story += [Spacer(1, 6), Paragraph("Combinaisons EN 1990 du modèle", ss["Heading2"])]
        story += [p(f"{c.get('id')} : {c.get('label')}") for c in combos]

    def footer(canvas, docu):
        canvas.saveState()
        canvas.setFont("Helvetica-Bold", 8)
        canvas.setFillColor(colors.HexColor("#9d3e26"))
        canvas.drawString(35, 20, "FERRAILLAGE NON EXÉCUTOIRE - À VÉRIFIER PAR L'INGÉNIEUR - RÉSISTANCE NON VÉRIFIÉE")
        canvas.drawRightString(806, 20, f"Rév. {revision} | {docu.page}")
        canvas.restoreState()

    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    return out.getvalue()


def build_dossier_pdf(model: dict, revision: int, sections: dict) -> bytes:
    """Dossier BET complet : EN 1990 → EN 1992/1993/1995 → EN 1997 → flèches/fissuration."""
    out = io.BytesIO()
    doc = SimpleDocTemplate(out, pagesize=landscape(A4), leftMargin=35, rightMargin=35, topMargin=42, bottomMargin=36)
    ss = getSampleStyleSheet()
    ss.add(ParagraphStyle("Tiny", parent=ss["BodyText"], fontSize=8, leading=11))
    p = lambda t: Paragraph(escape(str(t)), ss["Tiny"])

    def u(util):
        if not util:
            return "—"
        return f"{util['ratio']} · {util['label']}" if util.get("ratio") is not None else util.get("label", "—")

    def tbl(rows, widths):
        t = Table([[p(c) for c in r] for r in rows], colWidths=widths, repeatRows=1)
        t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e7eee9")),
                               ("GRID", (0, 0), (-1, -1), .3, colors.HexColor("#c5cfca")),
                               ("VALIGN", (0, 0), (-1, -1), "TOP"),
                               ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4)]))
        return t

    title = (model or {}).get("title", "Étude de structure")
    story = [Paragraph("ConstruPilot | Dossier de calcul BET", ss["Title"]), p(title),
             p(f"Révision {revision}"), Spacer(1, 6),
             Paragraph("DOSSIER NON EXÉCUTOIRE — EFFORTS & ARMATURES NÉCESSAIRES — RÉSISTANCES NON VALIDÉES", ss["Heading2"]),
             p("Combinaisons EN 1990 (valeurs usuelles AN FR) puis acier nécessaire / vérifications indicatives "
               "(EN 1992/1993/1995/1997, flèches, fissuration). Aucune résistance ni disposition constructive "
               "validée automatiquement — À VÉRIFIER PAR L'INGÉNIEUR."), Spacer(1, 8)]

    env = sections.get("envelope")
    if env:
        story.append(Paragraph("1. Enveloppe dimensionnante EN 1990", ss["Heading2"]))
        rows = [["Élément", "Type", "M dim. (kN·m)", "V dim. (kN)", "N dim. (kN)", "q dim. (kPa)"]]
        for e in env.get("elements", []):
            uls = e.get("uls") or {}
            rows.append([e["id"], e.get("kind", ""),
                         (uls.get("moment_knm") or {}).get("value", ""),
                         (uls.get("shear_kn") or {}).get("value", ""),
                         (uls.get("axial_kn") or {}).get("value", ""),
                         (uls.get("pressure_kpa") or {}).get("value", "")])
        story += [tbl(rows, [70, 70, 130, 130, 130, 130]), Spacer(1, 8)]

    ec2 = sections.get("ec2")
    if ec2:
        story.append(Paragraph("2. Béton armé EN 1992 — armatures nécessaires & ferraillage", ss["Heading2"]))
        rows = [["Poutre", "b×h·d (m)", "M dim.", "As flexion (cm²)", "V → Asw/s", "As mini/maxi", "Ferraillage"]]
        for r in ec2.get("elements", []):
            if r.get("status") != "ok":
                rows.append([r.get("id"), "—", r.get("message", ""), "", "", "", ""])
                continue
            fx, sh, sc = r["design"]["flexure"], r["design"]["shear"], r.get("scheme") or {}
            ferr = (sc.get("longitudinal") or {}).get("label", "") + ((" · " + sc["stirrups"]["label"]) if sc.get("stirrups") else "")
            if r.get("reinforcement_source") == "automation":
                ferr = ("auto " + ("OK" if r.get("provided_ok") else "INSUFFISANT") + " · ") + ferr
            rows.append([r["id"], f"{r['b_m']}×{r['h_m']}·{r['d_m']}", f"{r['med_knm']}",
                         f"{fx['as_req_cm2']} ({fx['mode']})",
                         f"{sh['asw_s_req_cm2_m']}" if r.get("ved_kn") is not None else "—",
                         f"{fx['as_min_cm2']}/{fx['as_max_cm2']}", ferr])
        story += [tbl(rows, [55, 95, 70, 120, 90, 90, 170]), Spacer(1, 8)]

    crack = sections.get("crack")
    if crack:
        story.append(Paragraph("2bis. Fissuration EN 1992 §7.3 (ELS quasi-permanent)", ss["Heading2"]))
        rows = [["Poutre", "Mqp (kN·m)", "σs (MPa)", "wk (mm)", "wmax", "As,min fiss. (cm²)", "Utilisation"]]
        for r in crack.get("elements", []):
            if r.get("status") != "ok":
                rows.append([r.get("id"), r.get("message", ""), "", "", "", "", ""])
                continue
            rows.append([r["id"], r["mqp_knm"], r["sigma_s_mpa"], r["wk_mm"], r["wmax_mm"],
                         r["as_min_fiss_cm2"], u(r["utilisation"])])
        story += [tbl(rows, [55, 110, 90, 90, 70, 130, 160]), Spacer(1, 8)]

    anch = sections.get("anchorage")
    if anch:
        story.append(Paragraph("2ter. Ancrages & recouvrements EN 1992 §8.4/§8.7", ss["Heading2"]))
        rows = [["Poutre", "Barre", "fbd (MPa)", "lb,rqd (m)", "lbd (m / ×Ø)", "Recouvrement l0 (m / ×Ø)"]]
        for r in anch.get("elements", []):
            if r.get("status") != "ok":
                rows.append([r.get("id"), r.get("message", ""), "", "", "", ""])
                continue
            a = r["result"]
            rows.append([r["id"], r.get("bar_label") or f"Ø{a['bar_mm']}", a["fbd_mpa"], a["lb_rqd_m"],
                         f"{a['lbd_m']} / {a['lbd_ratio_phi']}Ø", f"{a['l0_m']} / {a['l0_ratio_phi']}Ø"])
        story += [tbl(rows, [55, 110, 90, 100, 150, 180]), Spacer(1, 8)]

    ec3 = sections.get("ec3")
    if ec3:
        story.append(Paragraph("3. Acier EN 1993 — poutres", ss["Heading2"]))
        rows = [["Poutre", "Profil", "Flexion", "Cisaillement", "Déversement"]]
        for r in ec3.get("elements", []):
            if r.get("status") != "ok":
                rows.append([r.get("id"), "", r.get("message", ""), "", ""])
                continue
            res = r["result"]
            rows.append([r["id"], f"{r['profile']}/{r['grade']}", u(res["bending"]["utilisation"]),
                         u(res["shear"]["utilisation"]), u(res["lateral_torsional"]["utilisation"])])
        story.append(tbl(rows, [60, 90, 180, 150, 180]))
        cols = ec3.get("columns") or []
        if cols:
            story += [Spacer(1, 6), Paragraph("3bis. Acier EN 1993 — poteaux (N+M · flambement)", ss["Heading2"])]
            crows = [["Poteau", "Profil", "N dim. (kN)", "Lcr (m)", "Flambement N/Nb,Rd", "Interaction N+M"]]
            for r in cols:
                if r.get("status") != "ok":
                    crows.append([r.get("id"), "", r.get("message", ""), "", "", ""])
                    continue
                res = r["result"]
                crows.append([r["id"], f"{r['profile']}/{r['grade']}", r["ned_kn"], r["lcr_m"],
                              u(res["buckling"]["utilisation"]),
                              u((res.get("interaction") or {}).get("utilisation")) if res.get("interaction") else "N seul"])
            story.append(tbl(crows, [60, 90, 100, 80, 160, 160]))
        story.append(Spacer(1, 8))

    ec5 = sections.get("ec5")
    if ec5:
        story.append(Paragraph("4. Bois EN 1995 — poutres", ss["Heading2"]))
        rows = [["Poutre", "Classe", "Flexion", "Cisaillement", "Déversement"]]
        for r in ec5.get("elements", []):
            if r.get("status") != "ok":
                rows.append([r.get("id"), "", r.get("message", ""), "", ""])
                continue
            res = r["result"]
            rows.append([r["id"], r["strength_class"], u(res["bending"]["utilisation"]),
                         u(res["shear"]["utilisation"]), u(res["lateral_torsional"]["utilisation"])])
        story += [tbl(rows, [60, 80, 180, 150, 180]), Spacer(1, 8)]

    ec7 = sections.get("ec7")
    if ec7:
        story.append(Paragraph("5. Fondations EN 1997 — portance", ss["Heading2"]))
        rows = [["Semelle", "B×L (m)", "q_Ed (kPa)", "q_Rd (kPa)", "Utilisation"]]
        for r in ec7.get("elements", []):
            if r.get("status") != "ok":
                rows.append([r.get("id"), "", r.get("message") or (r.get("result") or {}).get("message", ""), "", ""])
                continue
            res = r["result"]
            rows.append([r["id"], f"{res['B_m']}×{res['L_m']}", res["q_ed_kpa"], res["q_Rd_kpa"], u(res["utilisation"])])
        story += [tbl(rows, [70, 90, 120, 120, 180]), Spacer(1, 8)]

    slsd = sections.get("sls")
    if slsd:
        story.append(Paragraph("6. Flèches en service SLS (EN 1990)", ss["Heading2"]))
        rows = [["Poutre", "Portée (m)", "Caractéristique", "Quasi-permanente"]]
        for r in slsd.get("elements", []):
            if r.get("status") != "ok":
                rows.append([r.get("id"), "", r.get("message", ""), ""])
                continue
            rows.append([r["id"], f"{r['span_m']} ({r['span_source']})", u(r["char"]["utilisation"]), u(r["qp"]["utilisation"])])
        story += [tbl(rows, [60, 120, 190, 190]), Spacer(1, 8)]

    _STAT = {"partial": "Calculé (indicatif)", "pass": "Conforme (saisi)", "conflict": "CONFLIT",
             "conflicts": "CONFLITS", "incomplete": "À compléter", "fails_check": "Contrôle NON satisfait",
             "out_of_scope": "Hors domaine", "listed_checks_only": "Contrôles listés",
             "has_unresolved_checks": "Contrôles à revoir", "not_checked": "Non vérifié",
             "no_design": "Pas de ferraillage", "need_sls": "ELS manquant"}
    stat = lambda v: _STAT.get(v, v or "—")

    reinf = sections.get("reinforcement")
    if reinf and (reinf.get("sections") or reinf.get("footings") or reinf.get("schedules")):
        story.append(Paragraph("7. Ferraillage manuel EN 1992 — sections saisies (efforts indépendants)", ss["Heading2"]))
        rows = [["Repère", "Cas", "As,req (cm²)", "As,prov (cm²)", "État"]]
        for r in reinf.get("sections", []):
            asr, asp = r.get("as_required_mm2"), r.get("as_provided_mm2")
            rows.append([r.get("id"), r.get("case", ""),
                         f"{asr / 100:.2f}" if asr else "—", f"{asp / 100:.2f}" if asp else "—", stat(r.get("status"))])
        story += [tbl(rows, [70, 190, 110, 110, 180]), Spacer(1, 4)]
        for sch in reinf.get("schedules", []):
            story.append(p(f"Nomenclature {sch.get('id')} : {sch.get('total_kg', 0):.1f} kg d'aciers (longueurs développées saisies)."))
        story.append(Spacer(1, 8))

    arch = sections.get("architecture")
    if arch and (arch.get("checks") or arch.get("issues")):
        story.append(Paragraph("8. Contrôles architecturaux PC — gabarits & hauteurs libres (saisis)", ss["Heading2"]))
        rows = [["Repère", "Élément", "Type", "État", "Détail"]]
        kinds = {"clearance": "Hauteur libre", "fit_band": "Gabarit"}
        for c in arch.get("checks", []):
            rows.append([c.get("id"), c.get("element_id", ""), kinds.get(c.get("kind"), c.get("kind", "")),
                         stat(c.get("status")), c.get("summary", "")])
        story.append(tbl(rows, [60, 70, 95, 110, 335]))
        for iss in arch.get("issues", []):
            story.append(p("• " + iss))
        story += [p(arch.get("scope", "")), Spacer(1, 8)]

    linked = sections.get("linked")
    if linked and linked.get("sections"):
        story.append(Paragraph("9. Aciers liés aux efforts EN 1992 (enveloppe des combinaisons, saisis)", ss["Heading2"]))
        rows = [["Repère", "Poutre", "Base effort", "Cas dim.", "As,req env. (cm²)", "Portée (m)", "État"]]
        for s2 in linked.get("sections", []):
            asr = s2.get("as_required_envelope_mm2")
            rows.append([s2.get("id"), s2.get("element_id", ""), s2.get("force_basis", ""),
                         s2.get("governing_flexure_case") or "—", f"{asr / 100:.2f}" if asr else "—",
                         s2.get("span_m", ""), stat(s2.get("status"))])
        story += [tbl(rows, [55, 60, 120, 110, 120, 70, 135]), p(linked.get("scope", "")), Spacer(1, 8)]

    lints = sections.get("lintels")
    lint_single = sections.get("lintel")
    if lints or lint_single:
        entries = lints if lints else [{"name": None, "result": lint_single}]
        story.append(Paragraph("10. Linteaux / reprises d'ouverture sur mur porteur (EN 1992/1993 — indicatif)", ss["Heading2"]))
        for idx, entry in enumerate(entries, 1):
            lint = entry.get("result") or {}
            nm = entry.get("name")
            if nm:
                story.append(Paragraph(f"10.{idx} {escape(str(nm))}", ss["Heading3"]))
            act = lint.get("actions", {})
            story.append(p(f"Portée libre {lint.get('clear_span_m')} m · modèle de charge « {lint.get('load_model')} » · "
                           f"M_Ed {act.get('m_ed_knm')} kN·m · V_Ed {act.get('v_ed_kn')} kN · {act.get('combination', '')}"))
            rows = [["Solution", "Proposition", "Vérifications", "Coût matière estimé"]]
            st = lint.get("steel") or {}
            if st.get("status") == "ok":
                ver = f"M_Rd {st.get('mrd_knm')} kN·m · V_Rd {st.get('vrd_kn')} kN · flèche {st.get('defl_char_mm')}/{st.get('defl_char_limit_mm')} mm"
                if st.get("ltb"):
                    lt = st["ltb"]
                    ver += f" · déversement Mb,Rd {lt.get('mb_rd_knm')} kN·m (χLT {lt.get('chi_lt')}, Mcr {lt.get('mcr_knm')})"
                rows.append(["Acier EN 1993", st.get("label", ""), ver, f"{st.get('cost_eur')} € ({st.get('mass_kg')} kg)"])
            elif st:
                rows.append(["Acier EN 1993", st.get("message", "Pas de solution"), "", ""])
            rc = lint.get("rc") or {}
            if rc.get("status") == "ok":
                rows.append(["Béton armé EN 1992", rc.get("label", ""),
                             f"As {rc.get('as_required_cm2')} cm² · Asw/s {rc.get('asw_required_cm2_m')} cm²/m · L/d {rc.get('span_depth_ratio')}",
                             f"{rc.get('cost_eur')} € ({rc.get('concrete_m3')} m³ + {rc.get('rebar_kg')} kg)"])
            elif rc:
                rows.append(["Béton armé EN 1992", rc.get("message", "Pas de solution"), "", ""])
            story.append(tbl(rows, [110, 150, 250, 110]))
            reco = lint.get("recommendation")
            if reco:
                story.append(p(f"Solution la plus économique : {('Acier' if reco['material'] == 'steel' else 'Béton armé')} — "
                               f"{reco.get('label')} ({reco.get('cost_eur')} €). {reco.get('reason')}."))
            br = lint.get("bearing") or {}
            story.append(p(f"Appui sur maçonnerie : réaction ELU {br.get('reaction_kn')} kN ; pression {br.get('sigma_kpa')} kPa "
                           f"≤ {br.get('allow_kpa')} kPa → {'OK' if br.get('status') == 'ok' else 'À REVOIR'} "
                           f"(about adopté {br.get('adopted_length_m')} m, requis ≥ {br.get('required_length_m')} m)."))
            if st.get("status") == "ok" and st.get("bearing_plate"):
                bp = st["bearing_plate"]
                story.append(p(f"Platine de répartition (acier) : {bp.get('length_mm')}×{bp.get('width_mm')}×{bp.get('thickness_mm')} mm "
                               f"— pression {bp.get('sigma_kpa')} ≤ {bp.get('allow_kpa')} kPa."))
            if rc.get("status") == "ok" and rc.get("detailing"):
                an = rc["detailing"].get("anchorage") or {}
                story.append(p(f"Ferraillage BA : ancrage barres inférieures {an.get('straight_mm')} mm (crochet {an.get('hook_mm')} mm, "
                               f"fbd {an.get('fbd_mpa')} MPa) ; cadres Asw/s {rc.get('asw_required_cm2_m')} cm²/m."))
            rk = lint.get("reactions") or {}
            story.append(p(f"Réaction à réinjecter sur chaque trumeau : G {rk.get('g_kn')} kN + Q {rk.get('q_kn')} kN "
                           f"(caractéristiques), pour boucler la descente de charges."))
            try:
                from engines.structuro_lintel_export import lintel_figure_dim
                story.append(lintel_figure_dim(lint, width=720, height=230))
            except Exception:
                pass
            for n in lint.get("notes", []):
                story.append(p("• " + n))
            story += [p(lint.get("note", "")), Spacer(1, 8)]

    def footer(canvas, docu):
        canvas.saveState()
        canvas.setFont("Helvetica-Bold", 8)
        canvas.setFillColor(colors.HexColor("#9d3e26"))
        canvas.drawString(35, 20, "DOSSIER BET NON EXÉCUTOIRE - À VÉRIFIER PAR L'INGÉNIEUR - RÉSISTANCES NON VALIDÉES")
        canvas.drawRightString(806, 20, f"Rév. {revision} | {docu.page}")
        canvas.restoreState()

    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    return out.getvalue()
