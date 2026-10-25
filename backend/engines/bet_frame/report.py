"""Note de calcul A4 de l'ossature BA + revue automatique (statut du dossier)."""
from __future__ import annotations

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from engines.bet_core import brand as B
from engines.bet_core import draw  # noqa: F401 — enregistre les polices

from .calc import mesh_txt
from .calc import sp as _sp
from .lang import _, num
from .model import BLOCK, Frame

H1 = ParagraphStyle("fh1", fontName="TT", fontSize=15, leading=18, spaceBefore=10, spaceAfter=5)
H2 = ParagraphStyle("fh2", fontName="TTS", fontSize=11.5, leading=14, spaceBefore=6, spaceAfter=3)
P = ParagraphStyle("fp", fontName="DV", fontSize=8.6, leading=12, textColor=colors.Color(0.15, 0.17, 0.20))
SM = ParagraphStyle("fsm", fontName="DV", fontSize=7.3, leading=9.4, textColor=colors.Color(0.15, 0.17, 0.20))
SMH = ParagraphStyle("fsmh", parent=SM, fontName="DVB", textColor=colors.white)


def _esc(s) -> str:
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _t(rows, widths):
    br = B.get()
    data = [[Paragraph(_esc(c), SMH if i == 0 else SM) for c in r] for i, r in enumerate(rows)]
    t = Table(data, colWidths=[w * mm for w in widths], repeatRows=1)
    st = [("LINEBELOW", (0, 0), (-1, -1), 0.25, colors.Color(0.84, 0.85, 0.87)), ("VALIGN", (0, 0), (-1, -1), "TOP"),
          ("LEFTPADDING", (0, 0), (-1, -1), 3), ("RIGHTPADDING", (0, 0), (-1, -1), 3),
          ("TOPPADDING", (0, 0), (-1, -1), 2.2), ("BOTTOMPADDING", (0, 0), (-1, -1), 2.2),
          ("BACKGROUND", (0, 0), (-1, 0), br.accent), ("LINEBELOW", (0, 0), (-1, 0), 1.0, br.accent2)]
    for i in range(2, len(rows), 2):
        st.append(("BACKGROUND", (0, i), (-1, i), br.tint2))
    t.setStyle(TableStyle(st))
    return t


def _ov(m: Frame) -> str:
    ov = (m.raw.get("geometry") or {}).get("overall") or {}
    if not (ov.get("length") and ov.get("width")):
        return _("NON RELEVÉES — trame à recaler sur les plans d'architecte", "NÃO RELEVADAS — trama a acertar pelas plantas de arquitetura")
    return f"{num(float(ov['length']))} × {num(float(ov['width']))} m" + (f" ({ov['source']})" if ov.get("source") else "")


def review(m: Frame, r: dict, e: dict, anomalies: list[dict]) -> dict:
    items = []
    for a in anomalies + r["issues"]:
        items.append({"level": a.get("level", "avertissement"), "message": a["message"] + (f" — {a['fix']}" if a.get("fix") else "")})
    for c in r["checks"]:
        items.append(c)
    blocking = sum(1 for i in items if i["level"] == BLOCK)
    nok = [f"{c['name']}" for c in r["columns"] if any(not s.get("ok") for s in c["segs"])]
    if nok:
        items.append({"level": BLOCK, "message": _("Poteaux non vérifiés : ", "Pilares não verificados: ") + ", ".join(nok[:10])})
        blocking += 1
    for fl in r["floors"]:
        bad = [b["name"] for b in fl["beams"] if not b["ok"]]
        if bad:
            items.append({"level": BLOCK, "message": _(f"Poutres non vérifiées ({fl['slab'].name}) : ", f"Vigas não verificadas ({fl['slab'].name}): ") + ", ".join(bad)})
            blocking += 1
    status = _("PRÊT (pré-dimensionnement)", "PRONTO (pré-dimensionamento)") if not blocking else _("NON PRÊT", "NÃO PRONTO")
    return {"status": status, "blocking": blocking, "items": items}


def write_note(path, m: Frame, r: dict, e: dict, tot: dict, rev: dict, sheets: list, th: dict | None = None):
    br = B.get()
    for st in (H1, H2):
        st.textColor = br.accent
    pr = m.project
    sec = [0]

    def H(title):
        sec[0] += 1
        return Paragraph(f"{sec[0]}. {_esc(title)}", H1)
    s = []
    s.append(Paragraph(_esc(_("Note de calcul — ossature béton armé", "Memória de cálculo — estrutura de betão armado")), H1))
    s.append(Paragraph(_esc(f"{pr.get('name', '')} — {pr.get('address', '')}"), P))
    s.append(Spacer(1, 3 * mm))
    col = colors.Color(0.10, 0.45, 0.25) if not rev["blocking"] else colors.Color(0.75, 0.12, 0.10)
    s.append(Paragraph(_esc(_("STATUT DU DOSSIER : ", "ESTADO DO PROCESSO: ") + rev["status"]),
                       ParagraphStyle("st", fontName="DVB", fontSize=12, leading=15, textColor=col)))
    s.append(Paragraph(_esc(_("Pré-dimensionnement à faire viser et signer par un ingénieur structure avant exécution. "
                              "Les hypothèses non fournies sont tracées ci-dessous et doivent être confirmées.",
                              "Pré-dimensionamento a verificar e assinar por um engenheiro de estruturas antes da execução. "
                              "As hipóteses não fornecidas estão identificadas abaixo e devem ser confirmadas.")), P))
    # 1. objet
    s.append(H(_("Objet, documents et bâtiment", "Objeto, documentos e edifício")))
    bt = {"immeuble_collectif": _("Immeuble collectif d'habitation", "Edifício de habitação coletiva"), "bureaux": _("Immeuble de bureaux", "Edifício de escritórios"),
          "garage": _("Parking / garage", "Garagem / parque de estacionamento"), "hangar": _("Bâtiment d'activité", "Edifício de atividade"),
          "public": _("Bâtiment public / ERP", "Edifício público")}.get(m.raw.get("building_type", ""), _("Bâtiment à ossature BA", "Edifício em estrutura de betão armado"))
    s.append(_t([[_("Donnée", "Dado"), _("Valeur", "Valor")],
                 [_("Type", "Tipo"), bt],
                 [_("Plans d'architecte", "Projeto de arquitetura"), pr.get("pc_ref", "—")],
                 [_("Étude de sol", "Estudo geotécnico"), pr.get("g2_ref", "—") + (f" ({m.geo.get('source')})" if m.geo.get("source") else "")],
                 [_("Emprise de la trame", "Implantação da trama"), f"{num(m.L)} × {num(m.W)} m — {num(m.footprint, 1)} m²"],
                 [_("Cotes extérieures relevées", "Cotas exteriores relevadas"), _ov(m)],
                 [_("Trame x", "Trama x"), " / ".join(num(b - a) for a, b in zip(m.gx, m.gx[1:])) + " m"],
                 [_("Trame y", "Trama y"), " / ".join(num(b - a) for a, b in zip(m.gy, m.gy[1:])) + " m"],
                 [_("Niveaux", "Pisos"), ", ".join(f"{l.name} ({'+' if l.z >= 0 else ''}{num(l.z)}, h={num(l.height)})" for l in m.levels)],
                 [_("Fractions / lots", "Frações"), str(len(m.units))],
                 [_("Normes", "Normas"), _("EN 1990, EN 1991-1-1, EN 1992-1-1 et -1-2, EN 1998-1 (zones sismiques) + annexes nationales françaises",
                                           "NP EN 1990, NP EN 1991-1-1, NP EN 1992-1-1 e -1-2, NP EN 1998-1 + Anexos Nacionais; DR 23/95; RTIEBT")]],
                [48, 126]))
    dec = [str(d) for d in (m.raw.get("_decisions") or [])] + r["decisions"]
    if dec:
        s.append(Paragraph(_esc(_("Hypothèses et décisions", "Hipóteses e decisões")), H2))
        for d in dec:
            s.append(Paragraph("• " + _esc(d), SM))
    # 2. matériaux
    mt = r["mat"]
    s.append(H(_("Matériaux et enrobages", "Materiais e recobrimentos")))
    s.append(_t([[_("Élément", "Elemento"), _("Valeur", "Valor")],
                 [_("Béton", "Betão"), f"{mt['concrete']} — fcd = {num(mt['fcd'], 1)} MPa, fctm = {num(mt['fctm'])} MPa"],
                 [_("Acier", "Aço"), f"{mt['steel']} — fyd = {num(mt['fyd'], 0)} MPa"],
                 [_("Enrobages", "Recobrimentos"), _("dalles 2,5 cm · poutres / poteaux 3 cm · fondations 5 cm", "lajes 2,5 cm · vigas / pilares 3 cm · fundações 5 cm")],
                 [_("Coefficients", "Coeficientes"), "γG = 1,35 · γQ = 1,50 · γc = 1,50 · γs = 1,15"]], [48, 126]))
    # 3. actions
    s.append(H(_("Actions", "Ações")))
    rows = [[_("Plancher", "Laje"), _("Usage", "Utilização"), "e (m)", "G (kN/m²)", "Q (kN/m²)", "ψ2", "pELU (kN/m²)"]]
    for fl in r["floors"]:
        ld = fl["loads"]
        rows.append([fl["slab"].name, ld["label"], num(fl["slab"].h), f"{num(ld['g'])} ({num(ld['g_self'])}+{num(ld['g_fin'])}+{num(ld['g_part'])})",
                     num(ld["q"]), num(ld["psi2"], 1), num(ld["p_uls"])])
    s.append(_t(rows, [30, 46, 12, 36, 16, 10, 22]))
    fac = (m.raw.get("facade") or {}).get("weight", 2.8 if m.country == "PT" else 2.5)
    s.append(Paragraph(_esc(_(f"Façades : {num(float(fac))} kN/m² sur les poutres de rive ; balcons : dalle + revêtement + garde-corps 1 kN/m, Q = 3,5 kN/m². "
                              "Vent, neige et séisme : voir § contreventement.",
                              f"Fachadas: {num(float(fac))} kN/m² nas vigas de bordo; varandas: laje + revestimento + guarda 1 kN/m, Q = 3,5 kN/m². "
                              "Vento, neve e sismo: ver § contraventamento.")), SM))
    # 4. dalles
    s.append(H(_("Dalles pleines", "Lajes maciças")))
    from .sheets import _group_name, _slab_groups
    for g in _slab_groups(r):
        fl = g[0]
        rows = [[_("Panneau", "Painel"), "lx × ly", "Mx / My (kN·m/m)", _("Inf. court", "Inf. menor"), _("Inf. long", "Inf. maior"), _("Chapeaux max", "Sup. máx."), "l/d ≤ lim"]]
        for p in fl["panels"]:
            topm = max(p["top"].values(), key=lambda t: t["As"])
            rows.append([p["id"], f"{num(p['dx'])} × {num(p['dy'])}", f"{num(p['Mtx'], 1)} / {num(p['Mty'], 1)}", mesh_txt(p["mesh_short"]),
                         mesh_txt(p["mesh_long"]), mesh_txt(topm), f"{num(p['ld'], 1)} ≤ {num(p['ld_lim'], 1)}"])
        s.append(KeepTogether([Paragraph(_esc(_("Dalle ", "Laje ") + _group_name(g) + f" — e = {num(fl['slab'].h)} m"), H2), _t(rows, [18, 24, 30, 24, 24, 26, 28])]))
    # 5. poutres
    s.append(H(_("Poutres", "Vigas")))
    for g in _slab_groups(r):
        fl = g[0]
        rows = [[_("Poutre", "Viga"), "b×h", "L (m)", "M+ / M− (kN·m)", _("Inf.", "Inf."), _("Sup.", "Sup."), "VEd (kN)", _("Cadres", "Estribos")]]
        for bm in fl["beams"]:
            for k, sp in enumerate(bm["spans"]):
                rows.append([f"{bm['name']}.{k + 1}", f"{int(round(bm['b'] * 100))}×{int(round(bm['h'] * 100))}", num(sp["L"]),
                             f"{int(round(sp['M_span']))} / {int(round(max(sp['M_left'], sp['M_right'])))}", sp["bot"]["txt"],
                             f"{sp['top_l']['txt']} / {sp['top_r']['txt']}", f"{int(round(sp['V']))}", sp["stirrups"] + (f" · zc {_sp(sp['s_crit'])}" if sp.get("stirrups_crit") and sp["stirrups_crit"] != sp["stirrups"] else "")])
        s.append(Paragraph(_esc(_("Dalle ", "Laje ") + _group_name(g)), H2))
        s.append(_t(rows, [18, 16, 14, 28, 22, 32, 16, 28]))
    # 6. poteaux
    s.append(H(_("Poteaux — descente de charges et flexion composée", "Pilares — descida de cargas e flexão composta")))
    rows = [[_("Poteau", "Pilar"), _("Section", "Secção"), _("Pied : NG / NQ / NEd (kN)", "Base: NG / NQ / NEd (kN)"), "ν", "λ / λlim", _("Aciers", "Armadura"), _("Cadres", "Cintas"), "M/MRd"]]
    for c in r["columns"]:
        s0 = c["segs"][0]
        ax = s0["axes"]["x"]
        rows.append([c["name"], f"{int(round(c['b'] * 100))}×{int(round(c['h'] * 100))}", f"{int(s0['NG'])} / {int(s0['NQ'])} / {int(s0['NEd'])}",
                     num(s0["nu"]), f"{num(ax['lam'], 1)} / {num(ax['lam_lim'], 1)}", s0.get("txt", "—"), s0.get("ties", "—") + (f" · zc {_sp(s0['s_crit'])}" if s0.get("ties_crit") and s0["ties_crit"] != s0.get("ties") else ""), num(s0.get("util", 0))])
    s.append(_t(rows, [16, 16, 38, 12, 20, 20, 30, 12]))
    s.append(Paragraph(_esc(_("Longueur de flambement l0 = 0,7 h (contreventé par les noyaux) ; second ordre par courbure nominale (5.8.8) si λ > λlim ; "
                              "imperfection ei = l0/400 ; e0 ≥ max(h/30 ; 20 mm) ; flexion déviée 5.8.9 (4).",
                              "Comprimento de encurvadura l0 = 0,7 h (contraventado pelos núcleos); 2.ª ordem por curvatura nominal (5.8.8) se λ > λlim; "
                              "imperfeição ei = l0/400; e0 ≥ max(h/30; 20 mm); flexão desviada 5.8.9 (4).")), SM))
    # 7. fondations
    f = r["foundations"]
    s.append(H(_("Fondations", "Fundações")))
    s.append(Paragraph(_esc(_(f"Contrainte admissible {num(f['sigma_kpa'] / 1000)} MPa" + (" (HYPOTHÈSE)" if f["assumed"] else "") +
                              f", assise à {num(f['depth'])} m ; semelles = {f['ratio'] * 100:.0f} % de l'emprise ({f['kind']}).",
                              f"Tensão admissível {num(f['sigma_kpa'] / 1000)} MPa" + (" (HIPÓTESE)" if f["assumed"] else "") +
                              f", cota de fundação a {num(f['depth'])} m; sapatas = {f['ratio'] * 100:.0f} % da implantação.")), P))
    rows = [[_("Semelle", "Sapata"), "B × B × h (m)", "N ELS (kN)", "NEd (kN)", "σ (MPa)", _("Aciers 2 sens", "Armadura 2 dir.")]]
    for p in f["pads"]:
        rows.append([p["name"], f"{num(p['B'])} × {num(p['B'])} × {num(p['h'])}", f"{int(p['N'])}", f"{int(p['NEd'])}", num(p["sigma"] / 1000, 3), mesh_txt(p["mesh"])])
    s.append(_t(rows, [20, 40, 24, 24, 20, 30]))
    bas = r.get("basement")
    if bas:
        s.append(Paragraph(_esc(_("Murs de sous-sol", "Muros de cave")), H2))
        s.append(Paragraph(_esc(_(f"H = {num(bas['H'])} m, e = {num(bas['t'])} m ; K0 = {num(bas['K0'])}, γ = {num(bas['gamma'], 0)} kN/m³, surcharge {num(bas['q'], 0)} kPa ; "
                                  f"MEd = {num(bas['M'], 1)} kN·m/m, VEd = {num(bas['V'], 1)} kN/m ; verticaux intérieurs {mesh_txt(bas['vert'])}, "
                                  f"face terre {mesh_txt(bas['outer'])}, horizontaux {mesh_txt(bas['hor'])}.",
                                  f"H = {num(bas['H'])} m, e = {num(bas['t'])} m; K0 = {num(bas['K0'])}, γ = {num(bas['gamma'], 0)} kN/m³, sobrecarga {num(bas['q'], 0)} kPa; "
                                  f"MEd = {num(bas['M'], 1)} kN·m/m, VEd = {num(bas['V'], 1)} kN/m; vertical interior {mesh_txt(bas['vert'])}, "
                                  f"face terreno {mesh_txt(bas['outer'])}, horizontal {mesh_txt(bas['hor'])}.")), P))
    # 8. contreventement
    sz = r["seismic"]
    s.append(H(_("Contreventement, séisme et vent", "Contraventamento, sismo e vento")))
    txt = _(f"Masse sismique estimée {int(sz['W_total'])} kN, hauteur {num(sz['H'])} m, période fondamentale estimée T1 ≈ {num(sz['T1'])} s (EN 1998-1 4.3.3.2.2). ",
            f"Massa sísmica estimada {int(sz['W_total'])} kN, altura {num(sz['H'])} m, período fundamental estimado T1 ≈ {num(sz['T1'])} s (NP EN 1998-1 4.3.3.2.2). ")
    if sz.get("Fb_kN"):
        txt += _(f"Effort tranchant à la base estimé Fb ≈ {int(sz['Fb_kN'])} kN (ag = {sz['ag']} m/s², q = 3). ",
                 f"Corte basal estimado Fb ≈ {int(sz['Fb_kN'])} kN (ag = {sz['ag']} m/s², q = 3). ")
    txt += _("Le contreventement (noyaux / voiles) et la justification sismique et au vent doivent être faits sur un modèle 3D par l'ingénieur structure : "
             "ce dossier dimensionne l'ossature sous charges verticales.",
             "O contraventamento (núcleos / paredes) e a verificação sísmica e ao vento devem ser feitos num modelo 3D pelo engenheiro de estruturas: "
             "este processo dimensiona a estrutura para as ações verticais.")
    s.append(Paragraph(_esc(txt), P))
    # 9. réseaux
    s.append(H(_("Réseaux collectifs", "Redes coletivas")))
    rows = [[_("Colonne", "Coluna"), _("Type", "Tipo"), _("Fractions", "Frações"), _("Pied de colonne", "Base da coluna"), _("Tête", "Topo")]]
    for ri in e["risers"]:
        if not ri["sections"]:
            continue
        a, b_ = ri["sections"][0], ri["sections"][-1]

        def fm(x):
            if "sec" in x:
                return f"{x['sec']} mm² · {int(x['I'])} A · {num(x['s_kva'], 1)} kVA"
            return f"Ø{x['d']} · {num(x['q'])} l/s"
        rows.append([ri["id"], ri["kind"], str(len(ri["served"])), fm(a), fm(b_)])
    s.append(_t(rows, [22, 16, 18, 60, 58]))
    for n in e["notes"]:
        s.append(Paragraph("• " + _esc(n), SM))
    # 9 bis. térmica
    if th:
        pt = th["country"] == "PT"
        s.append(H(_("Comportement thermique et chauffage", "Comportamento térmico e climatização")))
        if pt:
            rows = [["Fração", "Piso", "Ap (m²)", "Nic / Ni", "Ntc / Nt", "RNt", "Classe", "Φ (kW)"]]
            for x in th["units"]:
                rows.append([x["name"], x["level_name"], num(x["Ap"], 1), f"{num(x['Nic'], 1)} / {num(x['Ni'], 1)}", f"{num(x['Ntc'], 1)} / {num(x['Nt'], 1)}",
                             num(x["RNt"], 2), x["classe"], num(x["phi_w"] / 1000, 2)])
            s.append(_t(rows, [24, 30, 16, 26, 30, 14, 14, 18]))
            cl = {}
            for x in th["units"]:
                cl[x["classe"]] = cl.get(x["classe"], 0) + 1
            s.append(Paragraph(_esc("Classes energéticas: " + ", ".join(f"{k} × {v}" for k, v in sorted(cl.items())) +
                                    f" · potência total de aquecimento {num(sum(x['phi_w'] for x in th['units']) / 1000, 1)} kW."), P))
        else:
            rows = [["Logement", "Niveau", "Su (m²)", "Besoin (kWh/m².an)", "Φ (kW)"]]
            for x in th["units"]:
                rows.append([x["name"], x["level_name"], num(x["Ap"], 1), num(x["bch"], 1), num(x["phi_w"] / 1000, 2)])
            s.append(_t(rows, [34, 40, 20, 40, 20]))
        for h in th["hyp"]:
            s.append(Paragraph("• " + _esc(h), SM))
    # 10. revue
    s.append(H(_("Vérifications et points à valider", "Verificações e pontos a validar")))
    for it in rev["items"]:
        lvl = {"ok": "OK", "avertissement": _("À VÉRIFIER", "A VERIFICAR"), "bloquant": _("BLOQUANT", "BLOQUEANTE"),
               "info": "INFO"}.get(str(it["level"]).lower(), str(it["level"]).upper())
        s.append(Paragraph(f"<b>[{_esc(lvl)}]</b> " + _esc(it["message"]), SM))
    s.append(Paragraph(_esc(_(f"Estimation du coût : {tot['ht']:,.0f} € HT ({tot['ttc']:,.0f} € TTC) — voir le devis Excel.".replace(",", " "),
                              f"Estimativa de custo: {tot['ht']:,.0f} € s/IVA ({tot['ttc']:,.0f} € c/IVA) — ver o orçamento Excel.".replace(",", " "))), P))
    s.append(Paragraph(_esc(_("Planches jointes : ", "Desenhos anexos: ") + ", ".join(f"{x.code} {x.title}" for x in sheets)), SM))

    def page(c, doc):
        W, Hh = A4
        c.saveState()
        c.setFillColor(br.accent)
        c.rect(0, Hh - 12 * mm, W, 12 * mm, stroke=0, fill=1)
        c.setFillColor(colors.white)
        c.setFont("TTS", 10)
        c.drawString(18 * mm, Hh - 8 * mm, (br.name or "ConstruPilot")[:40])
        c.setFont("DV", 7.5)
        c.drawRightString(W - 18 * mm, Hh - 8 * mm, _("Note de calcul — ", "Memória de cálculo — ") + str(pr.get("name", ""))[:60])
        c.setFillColor(colors.Color(0.45, 0.47, 0.50))
        c.drawString(18 * mm, 10 * mm, _("Pré-dimensionnement — à viser par un ingénieur structure", "Pré-dimensionamento — a verificar por engenheiro de estruturas"))
        c.drawRightString(W - 18 * mm, 10 * mm, str(doc.page))
        c.restoreState()
    doc = SimpleDocTemplate(str(path), pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm, topMargin=20 * mm, bottomMargin=18 * mm,
                            title=_("Note de calcul — ", "Memória de cálculo — ") + str(pr.get("name", "")))
    doc.build(s, onFirstPage=page, onLaterPages=page)
