"""Note de calcul A4 de la structure bois massif (FR / PT / EN / UK) + revue automatique du dossier."""
from __future__ import annotations

import io

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import Image, KeepTogether, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from engines.bet_core import brand as B
from engines.bet_core import draw  # noqa: F401 — enregistre les polices

from .lang import cur, num, t
from .mat import CLT, GL
from .norms import GAM_M, KDEF, KMOD

H1 = ParagraphStyle("ch1", fontName="DVX", fontSize=14, leading=17, spaceBefore=10, spaceAfter=5)
H2 = ParagraphStyle("ch2", fontName="DVB", fontSize=10.5, leading=13, spaceBefore=6, spaceAfter=3)
P = ParagraphStyle("cp", fontName="DV", fontSize=8.4, leading=11.6, textColor=colors.Color(0.15, 0.17, 0.20))
SM = ParagraphStyle("csm", fontName="DV", fontSize=7.2, leading=9.2, textColor=colors.Color(0.15, 0.17, 0.20))
SMH = ParagraphStyle("csmh", parent=SM, fontName="DVB", textColor=colors.white)
EQ = ParagraphStyle("ceq", fontName="DV", fontSize=7.8, leading=10.6, leftIndent=8, textColor=colors.Color(0.10, 0.25, 0.20))
BLOCK, WARN = "bloquant", "avertissement"


def _esc(s) -> str:
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _tbl(rows, widths):
    br = B.get()
    data = [[Paragraph(_esc(c), SMH if i == 0 else SM) for c in r] for i, r in enumerate(rows)]
    tb = Table(data, colWidths=[w * mm for w in widths], repeatRows=1)
    st = [("LINEBELOW", (0, 0), (-1, -1), 0.25, colors.Color(0.84, 0.85, 0.87)), ("VALIGN", (0, 0), (-1, -1), "TOP"),
          ("LEFTPADDING", (0, 0), (-1, -1), 3), ("RIGHTPADDING", (0, 0), (-1, -1), 3),
          ("TOPPADDING", (0, 0), (-1, -1), 2.0), ("BOTTOMPADDING", (0, 0), (-1, -1), 2.0),
          ("BACKGROUND", (0, 0), (-1, 0), br.accent), ("LINEBELOW", (0, 0), (-1, 0), 1.0, br.accent2)]
    for i in range(2, len(rows), 2):
        st.append(("BACKGROUND", (0, i), (-1, i), br.tint2))
    tb.setStyle(TableStyle(st))
    return tb


def _chart_util(r) -> Image | None:
    """Graphique couleur des taux de travail maximaux par groupe d'éléments (vert ≤ 0,8, orange ≤ 1, rouge > 1)."""
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except Exception:  # noqa: BLE001
        return None
    labels, vals = [], []
    for f in r["floors"]:
        labels.append(f"CLT {f['tag']}")
        vals.append(f["clt"]["u_max"])
        if f["beams"]:
            labels.append(f"GL {f['tag']}")
            vals.append(max(b["sec"]["u_max"] for b in f["beams"]))
    if r["columns"]:
        for lid in dict.fromkeys(s["level"] for c in r["columns"] for s in c["segs"]):
            us = [s["chk"]["u_max"] for c in r["columns"] for s in c["segs"] if s["level"] == lid]
            labels.append(t("Pot.", "Pil.", "Col.", "Кол.") + f" {lid}")
            vals.append(max(us))
    for w in r["walls"]:
        labels.append(w["id"])
        vals.append(max(max(s["u"], s["u_c90"]) for s in w["segs"]))
    if not vals:
        return None
    fig, ax = plt.subplots(figsize=(7.2, 2.9), dpi=160)
    cols = ["#2E8B57" if v <= 0.8 else "#E0A030" if v <= 1.0 else "#C0392B" for v in vals]
    ax.bar(range(len(vals)), vals, color=cols)
    ax.axhline(1.0, color="#C0392B", lw=1, ls="--")
    ax.set_xticks(range(len(vals)))
    ax.set_xticklabels(labels, rotation=60, ha="right", fontsize=6.5)
    ax.set_ylabel(t("Taux de travail max", "Taxa de trabalho máx.", "Max utilisation", "Макс. коеф. використання"), fontsize=7)
    ax.tick_params(axis="y", labelsize=6.5)
    ax.set_ylim(0, max(1.15, max(vals) * 1.1))
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    fig.tight_layout()
    buf = io.BytesIO()
    fig.savefig(buf, format="png")
    plt.close(fig)
    buf.seek(0)
    return Image(buf, width=170 * mm, height=68 * mm)


def _chart_qty(r) -> Image | None:
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except Exception:  # noqa: BLE001
        return None
    q = r["quantities"]
    items = [("CLT", q["clt_m3"] + q["wall_m3"], "#C8A26B"), (t("Lamellé-collé", "Lamelado-colado", "Glulam", "Клеєний брус"), q["gl_beams_m3"] + q["gl_cols_m3"], "#8B5A2B"),
             (t("Béton", "Betão", "Concrete", "Бетон"), q["conc_fnd_m3"] + q["conc_slab_m3"] + q["conc_plinth_m3"], "#9AA3AD")]
    items = [x for x in items if x[1] > 0]
    fig, ax = plt.subplots(figsize=(5.6, 2.2), dpi=160)
    ax.barh([x[0] for x in items], [x[1] for x in items], color=[x[2] for x in items])
    for k, x in enumerate(items):
        ax.text(x[1], k, f"  {x[1]:.1f} m³", va="center", fontsize=7)
    ax.tick_params(labelsize=7)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    ax.set_xlim(0, max(x[1] for x in items) * 1.25)
    fig.tight_layout()
    buf = io.BytesIO()
    fig.savefig(buf, format="png")
    plt.close(fig)
    buf.seek(0)
    return Image(buf, width=140 * mm, height=55 * mm)


def review(m, r: dict, anomalies: list[dict]) -> dict:
    items = []
    for a in anomalies + r["issues"]:
        items.append({"level": a.get("level", WARN), "message": a["message"] + (f" — {a['fix']}" if a.get("fix") else "")})
    for c in r["review"]:
        items.append({"level": "OK" if c["level"] == "OK" else BLOCK, "message": c["message"]})
    blocking = sum(1 for i in items if i["level"] == BLOCK)
    status = t("PRÊT (pré-dimensionnement)", "PRONTO (pré-dimensionamento)", "READY (preliminary design)", "ГОТОВО (попередній розрахунок)") if not blocking else \
        t("NON PRÊT", "NÃO PRONTO", "NOT READY", "НЕ ГОТОВО")
    return {"status": status, "blocking": blocking, "items": items}


def _norms_txt(c: str) -> list[str]:
    if c == "PT":
        return ["NP EN 1990, NP EN 1991-1-1/-1-3/-1-4 (AN PT)", "NP EN 1995-1-1, NP EN 1995-1-2 (madeira, fogo)", "NP EN 1998-1 (sismos)",
                "NP EN 1992-1-1 (fundações BA)", "RT-SCIE — Portaria 1532/2008 (resistência ao fogo)", "EN 16351 (CLT), EN 14080 (lamelado-colado)"]
    if c == "UA":
        return ["ДСТУ-Н Б EN 1990, ДСТУ-Н Б EN 1995-1-1, ДСТУ-Н Б EN 1995-1-2", "ДБН В.1.2-2:2006 (навантаження і впливи, зі змінами)",
                "ДБН В.1.1-12:2014 (сейсміка), ДБН В.1.1-7:2016 (пожежна безпека)", "ДБН В.2.6-161:2017 (дерев'яні конструкції)",
                "EN 16351 (CLT), EN 14080 (glulam)"]
    return ["NF EN 1990/NA, NF EN 1991-1-1/-1-3/-1-4 (AN France)", "NF EN 1995-1-1/NA, NF EN 1995-1-2/NA (bois, feu)", "NF EN 1998-1/NA + arrêté du 22/10/2010",
            "NF EN 1992-1-1/NA (fondations BA), NF DTU 13.1 / 13.3", "NF DTU 31.1 / 31.2, Règles professionnelles CLT", "EN 16351 (CLT), EN 14080 (lamellé-collé)"]


def write_note(path, m, r: dict, tot: dict, rev: dict, sheets: list):
    br = B.get()
    H1.textColor = br.accent
    H2.textColor = br.accent
    pr = m.project
    sec = [0]

    def H(title):
        sec[0] += 1
        return Paragraph(f"{sec[0]}. {_esc(title)}", H1)
    s = []
    s.append(Paragraph(_esc(t("Note de calcul — structure bois massif CLT / lamellé-collé", "Memória de cálculo — estrutura em madeira maciça CLT / lamelado-colado",
                              "Structural calculation report — mass timber CLT / glulam", "Розрахункова записка — конструкції з масивної деревини CLT / клеєний брус")), H1))
    s.append(Paragraph(_esc(f"{pr.get('name', '')} — {pr.get('address', '')}"), P))
    s.append(Paragraph(f"<b>{_esc(t('Statut', 'Estado', 'Status', 'Статус'))} : {_esc(rev['status'])}</b>", P))
    s.append(Spacer(1, 4))
    # ---------------------------------------------------------------- 1 hypothèses
    s.append(H(t("Hypothèses et normes", "Hipóteses e normas", "Design basis and codes", "Вихідні дані та норми")))
    for x in _norms_txt(r["country"]):
        s.append(Paragraph("• " + _esc(x), SM))
    s.append(Spacer(1, 3))
    rows = [[t("Matériau", "Material", "Material", "Матеріал"), "f_m,k", "f_c,0,k", "f_v,k / f_R,k", "E_0,mean", "E_0,05", "ρ_k"],
            [f"CLT (C24)", num(CLT["fm"], 1), num(CLT["fc0"], 1), f"{num(CLT['fv'], 1)} / {num(CLT['fR'], 2)}", num(CLT["E0"], 0), num(CLT["E05"], 0), str(CLT["rk"])]]
    for g in ("GL24h", "GL28h"):
        d = GL[g]
        rows.append([g, num(d["fm"], 1), num(d["fc0"], 1), num(d["fv"], 1), num(d["E0"], 0), num(d["E05"], 0), str(d["rk"])])
    s.append(_tbl(rows, (34, 20, 20, 30, 22, 22, 18)))
    s.append(Paragraph(_esc(t(f"MPa, kg/m³. Classe de service 1 ; k_mod = {KMOD['permanent']} (permanent), {KMOD['medium']} (moyen terme), {KMOD['short']} (court terme, neige) ; "
                              f"γ_M = {GAM_M['GL']} (CLT, GL), {GAM_M['CONN']} (assemblages) ; k_def = {KDEF['CLT']} (CLT), {KDEF['GL']} (GL).",
                              f"MPa, kg/m³. Classe de serviço 1; k_mod = {KMOD['permanent']} (permanente), {KMOD['medium']} (média duração), {KMOD['short']} (curta, neve); "
                              f"γ_M = {GAM_M['GL']} (CLT, GL), {GAM_M['CONN']} (ligações); k_def = {KDEF['CLT']} (CLT), {KDEF['GL']} (GL).",
                              f"MPa, kg/m³. Service class 1; k_mod = {KMOD['permanent']} (permanent), {KMOD['medium']} (medium-term), {KMOD['short']} (short-term, snow); "
                              f"γ_M = {GAM_M['GL']} (CLT, GL), {GAM_M['CONN']} (connections); k_def = {KDEF['CLT']} (CLT), {KDEF['GL']} (GL).",
                              f"МПа, кг/м³. Клас експлуатації 1; k_mod = {KMOD['permanent']} (постійне), {KMOD['medium']} (середньотривале), {KMOD['short']} (короткочасне, сніг); "
                              f"γ_M = {GAM_M['GL']} (CLT, GL), {GAM_M['CONN']} (з'єднання); k_def = {KDEF['CLT']} (CLT), {KDEF['GL']} (GL).")), SM))
    sn, wi, se = r["snow"], r["wind"], r["seismic"]
    rows = [[t("Action", "Ação", "Action", "Дія"), t("Valeur", "Valor", "Value", "Значення"), t("Référence", "Referência", "Reference", "Джерело")],
            [t("Neige", "Neve", "Snow", "Сніг"), f"s_k = {num(sn['sk'])} kN/m² ; μ = {num(sn['mu'], 1)} → s = {num(sn['s'])} kN/m²", sn["source"]],
            [t("Vent", "Vento", "Wind", "Вітер"), f"v_b = {num(wi['vb'], 1)} m/s ; q_p(H) = {num(wi['qp'])} kN/m²", wi["source"]],
            [t("Séisme", "Sismo", "Seismic", "Сейсміка"), (f"a_gR = {num(se['agr'])} m/s² ; S = {num(se['S'])} ; q = {num(se['q'], 1)}" if r["lateral"].get("seis_req")
                                                            else t("non requis (zone / catégorie)", "não exigido", "not required (zone / class)", "не вимагається")), se["source"]],
            [t("Feu", "Fogo", "Fire", "Вогонь"), f"R{r['R']}", r["R_src"]]]
    s.append(_tbl(rows, (26, 92, 56)))
    rows = [[t("Plancher", "Piso", "Floor", "Перекриття"), t("Usage", "Utilização", "Use", "Призначення"), "g_CLT", t("g revêt.", "g revest.", "g finishes", "g оздобл."),
             t("g cloisons", "g divisórias", "g partitions", "g перегородки"), "q", "ψ1 / ψ2", "p_ELU"]]
    for f in r["floors"]:
        ld, c = f["loads"], f["clt"]
        rows.append([f["name"], ld["use"], num(c["g_self"]), num(ld["fin"]), num(ld["part"]), num(ld["q"]), f"{num(ld['psi1'], 1)} / {num(ld['psi2'], 1)}", num(c["p_uls"])])
    s.append(Spacer(1, 3))
    s.append(_tbl(rows, (34, 24, 16, 18, 22, 14, 18, 18)))
    s.append(Paragraph(_esc(t("kN/m². Combinaisons EN 1990 : ELU 1,35 G + 1,5 Q ; ELS caractéristique G + Q ; quasi-permanente G + ψ2 Q ; incendie G + ψ1 Q. "
                              "Neige et charge d'entretien de toiture non cumulées.",
                              "kN/m². Combinações EN 1990: ELU 1,35 G + 1,5 Q; ELS característica G + Q; quase-permanente G + ψ2 Q; incêndio G + ψ1 Q. "
                              "Neve e sobrecarga de cobertura não cumulativas.",
                              "kN/m². EN 1990 combinations: ULS 1.35 G + 1.5 Q; SLS characteristic G + Q; quasi-permanent G + ψ2 Q; fire G + ψ1 Q. "
                              "Snow and roof maintenance load not combined.",
                              "кН/м². Сполучення EN 1990: ГСН 1,35 G + 1,5 Q; ГСЕ G + Q; квазіпостійне G + ψ2 Q; пожежа G + ψ1 Q. Сніг і експлуатаційне на покрівлі не сумуються.")), SM))
    # ---------------------------------------------------------------- 2 schéma porteur
    s.append(H(t("Choix du schéma porteur", "Escolha do esquema estrutural", "Structural scheme selection", "Вибір конструктивної схеми")))
    for d in r["decisions"]:
        s.append(Paragraph("• " + _esc(d), P))
    if r["scheme"].get("cands"):
        rows = [[t("Sens", "Sentido", "Direction", "Напрям"), t("Pannes / travée", "Madres / vão", "Purlins / bay", "Прогонів / проліт"), t("Portée CLT", "Vão CLT", "CLT span", "Проліт CLT"),
                 "CLT", t("Poutre", "Viga", "Beam", "Балка"), "m³/m²", "€/m²"]]
        for c in r["scheme"]["cands"][:8]:
            rows.append([c["o"].upper(), str(c["n"] - 1), num(c["s"]), c["clt"], c["beam"], num(c["vol_m3_m2"], 3), num(c["cost_m2"], 0)])
        s.append(_tbl(rows, (18, 28, 22, 26, 28, 22, 22)))
    # ---------------------------------------------------------------- 3 planchers CLT
    s.append(H(t("Planchers CLT", "Lajes CLT", "CLT floors", "Перекриття CLT")))
    s.append(Paragraph(_esc(t(
        "Bande de 1 m, méthode γ (EN 1995-1-1 annexe B appliquée au CLT : plis transversaux = liaison de raideur G_R·b/t̄, G_R = 50 MPa), panneaux continus sur ≥ 2 appuis "
        "(V = 0,625 p·L), moments de travée isostatique (sécuritaire). Vibrations §7.3.3 : f1 ≥ 8 Hz et w(1 kN) ≤ a. Feu : carbonisation par plis (β0 = 0,65 mm/min, chute de pli → 2β0 sur 25 mm), "
        "d_ef = d_char + 7 mm, k_fi = 1,15.",
        "Faixa de 1 m, método γ (EN 1995-1-1 anexo B aplicado ao CLT: camadas transversais = ligação de rigidez G_R·b/t̄, G_R = 50 MPa), painéis contínuos sobre ≥ 2 apoios "
        "(V = 0,625 p·L), momentos de vão simplesmente apoiado (a favor da segurança). Vibrações §7.3.3: f1 ≥ 8 Hz e w(1 kN) ≤ a. Fogo: carbonização por camadas (β0 = 0,65 mm/min, queda de camada → 2β0 em 25 mm), "
        "d_ef = d_char + 7 mm, k_fi = 1,15.",
        "1 m strip, γ-method (EN 1995-1-1 Annex B applied to CLT: cross plies = connection of stiffness G_R·b/t̄, G_R = 50 MPa), panels continuous over ≥ 2 supports "
        "(V = 0.625 p·L), simply supported span moments (conservative). Vibration §7.3.3: f1 ≥ 8 Hz and w(1 kN) ≤ a. Fire: ply-by-ply charring (β0 = 0.65 mm/min, ply fall-off → 2β0 over 25 mm), "
        "d_ef = d_char + 7 mm, k_fi = 1.15.",
        "Смуга 1 м, γ-метод (EN 1995-1-1 додаток B для CLT: поперечні шари = податливий зв'язок G_R·b/t̄, G_R = 50 МПа), панелі нерозрізні на ≥ 2 опорах "
        "(V = 0,625 p·L), прольотні моменти як для однопрольотної (у запас). Коливання §7.3.3: f1 ≥ 8 Гц і w(1 кН) ≤ a. Пожежа: обвуглення по шарах (β0 = 0,65 мм/хв, відпадання шару → 2β0 на 25 мм), "
        "d_ef = d_char + 7 мм, k_fi = 1,15.")), SM))
    rows = [[t("Plancher", "Piso", "Floor", "Перекриття"), "CLT", "L (m)", "σ/f_m", "τ_R/f_R", "w_inst / lim", "w_fin / lim", "f1 (Hz)", "w1kN", f"R{r['R']}", t("Taux", "Taxa", "Ratio", "Коеф.")]]
    for f in r["floors"]:
        c = f["clt"]
        fi = c["fire"]
        rows.append([f["name"], c["name"], num(c["span"]), num(c["u_m"]), num(c["u_r"]), f"{num(c['w_inst'], 1)} / {num(c['lim_inst'], 1)}",
                     f"{num(c['w_fin'], 1)} / {num(c['lim_fin'], 1)}", num(c["f1"], 1) if c["a_vib"] else "—", num(c["w1"]) if c["a_vib"] else "—",
                     num(fi["u"]) if fi else "—", num(c["u_max"])])
    s.append(_tbl(rows, (26, 18, 12, 13, 14, 20, 20, 13, 13, 13, 12)))
    if r["floors"]:
        f = max(r["floors"], key=lambda f_: f_["clt"]["p_uls"])
        c = f["clt"]
        L = c["span"]
        p = c["p_uls"]
        s.append(Paragraph(_esc(t(f"Détail — {f['name']} ({c['name']}, plis {'/'.join(map(str, c['layers']))} mm)", f"Detalhe — {f['name']} ({c['name']}, camadas {'/'.join(map(str, c['layers']))} mm)",
                                  f"Detail — {f['name']} ({c['name']}, plies {'/'.join(map(str, c['layers']))} mm)", f"Деталь — {f['name']} ({c['name']}, шари {'/'.join(map(str, c['layers']))} мм)")), H2))
        for ln in (f"G = {num(c['G'])} kN/m² ; Q = {num(c['q'])} kN/m² ; p_ELU = 1,35·G + 1,5·Q = {num(p)} kN/m²",
                   f"γ = {', '.join(num(g, 3) for g in c['gamma'])} ; (EI)_ef = {num(c['EI'] / 1e12, 3)} MN·m²/m",
                   f"M_Ed = p·L²/8 = {num(p * L * L / 8)} kN·m/m ; V_Ed = 0,625·p·L = {num(0.625 * p * L)} kN/m",
                   f"σ_m/f_m,d = {num(c['u_m'], 3)} ; τ_R/f_R,d = {num(c['u_r'], 3)} ; τ_v/f_v,d = {num(c['u_v'], 3)}",
                   f"w_inst(Q) = {num(c['w_inst'], 1)} ≤ L/{r['defl'][0]} = {num(c['lim_inst'], 1)} mm ; w_net,fin = {num(c['w_fin'], 1)} ≤ L/{r['defl'][1]} = {num(c['lim_fin'], 1)} mm",
                   (f"f1 = {num(c['f1'], 2)} Hz ≥ 8 Hz ; b_ef = {num(c['b_ef'])} m ; w(1 kN) = {num(c['w1'])} mm ≤ a = {num(c['a_vib'], 1)} mm" if c["a_vib"] else ""),
                   (f"R{r['R']} : d_char = {num(c['fire']['d_char'], 1)} mm ; d_ef = {num(c['fire']['d_ef'], 1)} mm ; h_res = {num(c['fire'].get('h_res', 0), 0)} mm ; taux = {num(c['fire']['u'], 3)}" if c["fire"] else "")):
            if ln:
                s.append(Paragraph(_esc(ln), EQ))
    # ---------------------------------------------------------------- 4 poutres
    if any(f["beams"] for f in r["floors"]):
        s.append(H(t("Poutres, pannes et sommiers lamellé-collé", "Vigas, madres e vigas mestras em lamelado-colado", "Glulam beams, purlins and girders",
                     "Балки, прогони та ригелі з клеєного бруса")))
        s.append(Paragraph(_esc(t("Isostatiques entre étriers ; flexion avec k_h, cisaillement avec k_cr = 0,67 ; flèches de flexion + effort tranchant (κ = 1,2) ; feu 3 faces (β_n = 0,7 mm/min), "
                                  "la face supérieure étant protégée par le CLT ; déversement empêché par le CLT vissé.",
                                  "Simplesmente apoiadas entre ligadores; flexão com k_h, corte com k_cr = 0,67; flechas de flexão + esforço transverso (κ = 1,2); fogo 3 faces (β_n = 0,7 mm/min), "
                                  "face superior protegida pelo CLT; bambeamento impedido pelo CLT aparafusado.",
                                  "Simply supported between hangers; bending with k_h, shear with k_cr = 0.67; bending + shear deflections (κ = 1.2); fire on 3 sides (β_n = 0.7 mm/min), "
                                  "top face protected by the CLT; lateral-torsional buckling prevented by the screwed CLT.",
                                  "Однопрольотні між опорами; згин з k_h, зріз з k_cr = 0,67; прогини від згину + зсуву (κ = 1,2); пожежа з 3 боків (β_n = 0,7 мм/хв), "
                                  "верх захищений CLT; втрата стійкості плоскої форми виключена CLT.")), SM))
        rows = [[t("Repère", "Ref.", "Mark", "Марка"), t("Rôle", "Função", "Role", "Роль"), "b×h", t("Classe", "Classe", "Grade", "Клас"), "L", "M_Ed", "V_Ed", "σ/f", "τ/f", "w_fin/lim", f"R{r['R']}", t("Taux", "Taxa", "Ratio", "Коеф.")]]
        for f in r["floors"]:
            seen = set()
            for bm in sorted(f["beams"], key=lambda b: -b["sec"]["u_max"]):
                key = (bm["role"], bm["b"], bm["h"], round(bm["L"], 2))
                if key in seen:
                    continue
                seen.add(key)
                sc = bm["sec"]
                rows.append([bm["id"], bm["role"], f"{bm['b']}×{bm['h']}", sc["grade"], num(bm["L"]), num(sc["M_Ed"], 1), num(sc["V_Ed"], 1), num(sc["u_m"]), num(sc["u_v"]),
                             f"{num(sc['w_fin'], 1)}/{num(sc['lim_fin'], 1)}", num(sc["fire"]["u"]) if sc["fire"] else "—", num(sc["u_max"])])
        s.append(_tbl(rows, (16, 14, 18, 14, 11, 14, 13, 11, 11, 20, 12, 12)))
    # ---------------------------------------------------------------- 5 poteaux / murs
    if r["columns"]:
        s.append(H(t("Poteaux lamellé-collé", "Pilares em lamelado-colado", "Glulam columns", "Колони з клеєного бруса")))
        s.append(Paragraph(_esc(t("Descente de charges par réactions d'appui des poutres ; excentricité d'étrier 0,15 m sur le déséquilibre ; flambement §6.3.2 (β_c = 0,1, L_ef = hauteur libre) ; "
                                  "flexion composée (6.23) ; feu 4 faces (L_ef,fi = 0,7 L, k_fi = 1,15).",
                                  "Descida de cargas pelas reações das vigas; excentricidade de ligação 0,15 m sobre o desequilíbrio; encurvadura §6.3.2 (β_c = 0,1, L_ef = altura livre); "
                                  "flexão composta (6.23); fogo 4 faces (L_ef,fi = 0,7 L, k_fi = 1,15).",
                                  "Load take-down from beam reactions; 0.15 m hanger eccentricity on unbalanced loads; buckling §6.3.2 (β_c = 0.1, L_ef = clear height); "
                                  "combined compression and bending (6.23); fire on 4 sides (L_ef,fi = 0.7 L, k_fi = 1.15).",
                                  "Збір навантажень за реакціями балок; ексцентриситет 0,15 м на різницю реакцій; стійкість §6.3.2 (β_c = 0,1, L_ef = вільна висота); "
                                  "стиск зі згином (6.23); пожежа з 4 боків (L_ef,fi = 0,7 L, k_fi = 1,15).")), SM))
        rows = [[t("Poteau", "Pilar", "Column", "Колона"), t("Étage", "Piso", "Storey", "Поверх"), "b×h", t("Classe", "Classe", "Grade", "Клас"), "N_Ed kN", "k_c", t("Taux", "Taxa", "Ratio", "Коеф."), f"R{r['R']}"]]
        top = sorted(r["columns"], key=lambda c: -c["segs"][0]["NEd"])[:14]
        for c in top:
            for sg in c["segs"]:
                ck = sg["chk"]
                rows.append([c["name"], sg["level_name"], f"{sg['b']}×{sg['h']}", sg["grade"], num(sg["NEd"], 0), num(ck["kc"], 3), num(ck["u"]),
                             num(ck["fire"]["u"]) if ck["fire"] else "—"])
        s.append(_tbl(rows, (18, 34, 20, 16, 20, 16, 16, 16)))
    if r["walls"]:
        s.append(H(t("Murs CLT porteurs", "Paredes CLT resistentes", "Load-bearing CLT walls", "Несучі стіни CLT")))
        rows = [[t("Mur", "Parede", "Wall", "Стіна"), t("Étage", "Piso", "Storey", "Поверх"), "CLT", "N_Ed kN/m", "k_c", t("Taux flamb.", "Taxa encurv.", "Buckling", "Стійкість"),
                 t("Compr. ⟂ plancher", "Compr. ⟂ laje", "Floor ⟂ crushing", "Зминання"), f"R{r['R']}"]]
        for w in r["walls"]:
            for sg in w["segs"]:
                rows.append([w["id"], sg["level_name"], sg["layup"], num(sg["N_Ed"], 1), num(sg["kc"], 3), num(sg["u"]), num(sg["u_c90"]),
                             num(sg["fire"]["u"]) if sg["fire"] else "—"])
        s.append(_tbl(rows, (14, 30, 20, 20, 14, 20, 26, 14)))
    # ---------------------------------------------------------------- 6 assemblages
    s.append(H(t("Assemblages", "Ligações", "Connections", "Вузли")))
    cn = r["connections"]
    if cn["hanger_types"]:
        h0 = cn["hangers"][0]
        s.append(Paragraph(_esc(t(f"Étriers : vis Ø8 entièrement filetées à 45°, arrachement éq. (8.38)–(8.40a) (f_ax,k = 0,52 d^-0,5 l_ef^-0,1 ρ_k^0,8), k_mod = 0,8, γ_M = 1,3 ; "
                                  f"résistance par vis en tranchant = R_ax,d·cos45° ≈ {num(h0['per_screw'])} kN.",
                                  f"Ligadores: parafusos Ø8 de rosca total a 45°, arranque eq. (8.38)–(8.40a), k_mod = 0,8, γ_M = 1,3; resistência por parafuso ≈ {num(h0['per_screw'])} kN.",
                                  f"Hangers: Ø8 fully threaded screws at 45°, withdrawal eq. (8.38)–(8.40a), k_mod = 0.8, γ_M = 1.3; shear resistance per screw ≈ {num(h0['per_screw'])} kN.",
                                  f"Опори: шурупи Ø8 з повною різьбою під 45°, висмикування (8.38)–(8.40a), k_mod = 0,8, γ_M = 1,3; на шуруп ≈ {num(h0['per_screw'])} кН.")), SM))
        rows = [[t("Type", "Tipo", "Type", "Тип"), t("Vis", "Parafusos", "Screws", "Шурупи"), t("Plaque", "Chapa", "Plate", "Пластина"), "Nb", "V_Ed max", "V_Rd", t("Taux", "Taxa", "Ratio", "Коеф.")]]
        for h in cn["hanger_types"]:
            rows.append([h["type"], f"{h['screws']} × Ø8×{h['L']}", h["plate"], str(h["n"]), num(h["V_max"], 1), num(h["V_Rd"], 1), num(h["V_max"] / h["V_Rd"])])
        s.append(_tbl(rows, (16, 34, 24, 14, 22, 20, 16)))
    if cn["bases"]:
        b = max(cn["bases"], key=lambda x: x["NEd"])
        s.append(Paragraph(_esc(t(f"Pied de poteau le plus chargé ({b['col']}) : N_Ed = {num(b['NEd'], 0)} kN ; f_jd = {num(b['f_jd'])} MPa (EN 1993-1-8 §6.2.5) ; platine {b['B']}×{b['B']}×{b['t']} S355 ; taux {num(b['u'])}.",
                                  f"Base mais carregada ({b['col']}): N_Ed = {num(b['NEd'], 0)} kN; f_jd = {num(b['f_jd'])} MPa (EN 1993-1-8 §6.2.5); chapa {b['B']}×{b['B']}×{b['t']} S355; taxa {num(b['u'])}.",
                                  f"Most loaded column base ({b['col']}): N_Ed = {num(b['NEd'], 0)} kN; f_jd = {num(b['f_jd'])} MPa (EN 1993-1-8 §6.2.5); plate {b['B']}×{b['B']}×{b['t']} S355; ratio {num(b['u'])}.",
                                  f"Найбільш навантажена опора ({b['col']}): N_Ed = {num(b['NEd'], 0)} кН; f_jd = {num(b['f_jd'])} МПа; пластина {b['B']}×{b['B']}×{b['t']} S355; коеф. {num(b['u'])}.")), P))
    # ---------------------------------------------------------------- 7 stabilité
    lat = r["lateral"]
    s.append(H(t("Stabilité horizontale", "Estabilidade horizontal", "Lateral stability", "Горизонтальна стійкість")))
    rows = [[t("Direction", "Direção", "Direction", "Напрям"), t("Vent (kN)", "Vento (kN)", "Wind (kN)", "Вітер (кН)"), t("Séisme (kN)", "Sismo (kN)", "Seismic (kN)", "Сейсміка (кН)"),
             "V_d (kN)", t("Dimensionnant", "Condicionante", "Governing", "Визначальне")]]
    for d in ("x", "y"):
        rows.append([d.upper(), num(lat["Vw"][d], 1), num(lat["Vs"], 1), num(lat["V_d"][d], 1), lat["gov"][d]])
    s.append(_tbl(rows, (24, 30, 30, 26, 30)))
    s.append(Paragraph(_esc(f"T1 = 0,05·H^0,75 = {num(lat['T1'], 3)} s ; S_d = {num(lat['Sd'], 3)} m/s² ; W = {num(lat['mass_kN'], 0)} kN ; c_f = {num(lat['cf'], 1)}"), EQ))
    d = lat["diaphragm"]
    s.append(Paragraph(_esc(t(f"Diaphragme CLT : flux de cisaillement {num(d['v_kNm'])} kN/m → éclisse {d['spline']}, vis {d['screw']} tous les {d['spacing']} mm.",
                              f"Diafragma CLT: fluxo de corte {num(d['v_kNm'])} kN/m → tala {d['spline']}, parafusos {d['screw']} a cada {d['spacing']} mm.",
                              f"CLT diaphragm: shear flow {num(d['v_kNm'])} kN/m → spline {d['spline']}, {d['screw']} screws at {d['spacing']} mm.",
                              f"Диск CLT: потік зсуву {num(d['v_kNm'])} кН/м → накладка {d['spline']}, шурупи {d['screw']} крок {d['spacing']} мм.")), P))
    for dd, br_ in (lat.get("braces") or {}).items():
        s.append(Paragraph(_esc(t(f"Palées {dd.upper()} : 4 croix de Saint-André tendues, N_Ed = {num(br_['N'], 1)} kN par diagonale → tirant {br_['rod']} S355 (angle {br_['angle']}°).",
                                  f"Contraventamento {dd.upper()}: 4 cruzes tracionadas, N_Ed = {num(br_['N'], 1)} kN por diagonal → tirante {br_['rod']} S355.",
                                  f"Bracing {dd.upper()}: 4 tension-only X-braces, N_Ed = {num(br_['N'], 1)} kN per diagonal → {br_['rod']} S355 tie rod.",
                                  f"В'язі {dd.upper()}: 4 хрестові (розтяг), N_Ed = {num(br_['N'], 1)} кН на розкіс → тяж {br_['rod']} S355.")), P))
    for dd, wv in (lat.get("walls") or {}).items():
        s.append(Paragraph(_esc(t(f"Murs de contreventement {dd.upper()} : {num(wv['v_kNm'])} kN/m → {wv['brackets']} équerres ({num(wv['F_br'], 0)} kN) et {wv['holddowns']} ancrages d'about ({num(wv['T_holddown'], 1)} kN) par niveau.",
                                  f"Paredes de contraventamento {dd.upper()}: {num(wv['v_kNm'])} kN/m → {wv['brackets']} esquadros e {wv['holddowns']} hold-downs por piso.",
                                  f"Shear walls {dd.upper()}: {num(wv['v_kNm'])} kN/m → {wv['brackets']} brackets and {wv['holddowns']} hold-downs ({num(wv['T_holddown'], 1)} kN) per level.",
                                  f"Стіни жорсткості {dd.upper()}: {num(wv['v_kNm'])} кН/м → {wv['brackets']} кутиків і {wv['holddowns']} анкерів hold-down на поверх.")), P))
    # ---------------------------------------------------------------- 8 fondations
    fnd = r["foundations"]
    s.append(H(t("Fondations — gros œuvre", "Fundações", "Foundations", "Фундаменти")))
    s.append(Paragraph(_esc(t(f"σ_adm = {num(fnd.get('sigma_kpa', 200), 0)} kPa ; assise {num(fnd.get('depth', 1.0))} m ; semelles calculées à l'ELS (σ = 1,10·N_ser/B²), armatures par la méthode des bielles à l'ELU.",
                              f"σ_adm = {num(fnd.get('sigma_kpa', 200), 0)} kPa; cota {num(fnd.get('depth', 1.0))} m; sapatas dimensionadas em serviço (σ = 1,10·N_ser/B²), armaduras pelo método das bielas.",
                              f"σ_allow = {num(fnd.get('sigma_kpa', 200), 0)} kPa; founding depth {num(fnd.get('depth', 1.0))} m; footings sized at SLS (σ = 1.10·N_ser/B²), strut-and-tie reinforcement at ULS.",
                              f"σ_доп = {num(fnd.get('sigma_kpa', 200), 0)} кПа; глибина {num(fnd.get('depth', 1.0))} м; підошва за ГСЕ (σ = 1,10·N_ser/B²), армування методом стержнів.")), P))
    pads = fnd.get("pads", [])
    if pads:
        rows = [[t("Semelle", "Sapata", "Footing", "Фундамент"), "B (m)", "h (m)", "N_ser kN", "σ kPa"]]
        for p_ in sorted(pads, key=lambda x: -x["N"])[:12]:
            rows.append([p_["name"], num(p_["B"]), num(p_["h"]), num(p_["N"], 0), num(p_["sigma"], 0)])
        s.append(_tbl(rows, (30, 22, 22, 26, 22)))
    for st in fnd.get("wall_strips", []):
        s.append(Paragraph(_esc(f"{st['id']} : B = {num(st['B'])} m, h = {num(st['h'])} m, n = {num(st['n'], 1)} kN/m, σ = {num(st['sigma'], 0)} kPa"), SM))
    if r.get("thermal"):
        from .thermal import blocks as _th_blocks
        s += _th_blocks(r["thermal"], H, P, SM, _tbl, _esc)
    # ---------------------------------------------------------------- 9 quantités
    s.append(H(t("Quantités et estimation", "Quantidades e estimativa", "Quantities and estimate", "Обсяги та кошторис")))
    q = r["quantities"]
    ch = _chart_qty(r)
    if ch:
        s.append(ch)
    s.append(Paragraph(_esc(t(f"CLT {num(q['clt_m3'] + q['wall_m3'], 1)} m³ ; lamellé-collé {num(q['gl_beams_m3'] + q['gl_cols_m3'], 1)} m³ ; béton {num(q['conc_fnd_m3'] + q['conc_slab_m3'] + q['conc_plinth_m3'], 1)} m³ ; "
                              f"{q['hangers']} étriers, {q['panels']} panneaux. Estimation : {num(tot['ht'], 0)} € HT ({num(tot['ttc'], 0)} € TTC) — devis Excel joint.",
                              f"CLT {num(q['clt_m3'] + q['wall_m3'], 1)} m³; lamelado-colado {num(q['gl_beams_m3'] + q['gl_cols_m3'], 1)} m³; betão {num(q['conc_fnd_m3'] + q['conc_slab_m3'] + q['conc_plinth_m3'], 1)} m³; "
                              f"{q['hangers']} ligadores, {q['panels']} painéis. Estimativa: {num(tot['ht'], 0)} € s/IVA ({num(tot['ttc'], 0)} € c/IVA) — orçamento Excel anexo.",
                              f"CLT {num(q['clt_m3'] + q['wall_m3'], 1)} m³; glulam {num(q['gl_beams_m3'] + q['gl_cols_m3'], 1)} m³; concrete {num(q['conc_fnd_m3'] + q['conc_slab_m3'] + q['conc_plinth_m3'], 1)} m³; "
                              f"{q['hangers']} hangers, {q['panels']} panels. Estimate: € {num(tot['ht'], 0)} excl. VAT (€ {num(tot['ttc'], 0)} incl. VAT) — Excel estimate attached.",
                              f"CLT {num(q['clt_m3'] + q['wall_m3'], 1)} м³; клеєний брус {num(q['gl_beams_m3'] + q['gl_cols_m3'], 1)} м³; бетон {num(q['conc_fnd_m3'] + q['conc_slab_m3'] + q['conc_plinth_m3'], 1)} м³; "
                              f"{q['hangers']} опор, {q['panels']} панелей. Кошторис: {num(tot['ht'], 0)} € без ПДВ ({num(tot['ttc'], 0)} € з ПДВ) — Excel додається.")), P))
    # ---------------------------------------------------------------- 10 revue
    s.append(H(t("Synthèse des vérifications", "Síntese das verificações", "Verification summary", "Зведення перевірок")))
    ch = _chart_util(r)
    if ch:
        s.append(ch)
    for it in rev["items"]:
        lvl = {"OK": "OK", WARN: t("À VÉRIFIER", "A VERIFICAR", "TO CHECK", "ПЕРЕВІРИТИ"), BLOCK: t("BLOQUANT", "BLOQUEANTE", "BLOCKING", "БЛОКУЄ")}.get(it["level"], str(it["level"]))
        s.append(Paragraph(f"<b>[{_esc(lvl)}]</b> " + _esc(it["message"]), SM))
    s.append(Spacer(1, 4))
    s.append(Paragraph(_esc(t("Planches jointes : ", "Desenhos anexos: ", "Attached drawings: ", "Креслення: ") + ", ".join(f"{x.code} {x.title}" for x in sheets)), SM))
    s.append(Paragraph(_esc(t("Pré-dimensionnement déterministe (aucune valeur produite par une IA) — à viser et signer par un ingénieur structure habilité avant exécution.",
                              "Pré-dimensionamento determinístico (nenhum valor produzido por IA) — a verificar e assinar por engenheiro de estruturas habilitado antes da execução.",
                              "Deterministic preliminary design (no value produced by AI) — to be checked and signed by a licensed structural engineer before construction.",
                              "Детермінований попередній розрахунок (жодне значення не згенеровано ШІ) — має бути перевірений і підписаний атестованим інженером-конструктором.")), SM))

    def page(c, doc):
        W, Hh = A4
        c.saveState()
        c.setFillColor(br.accent)
        c.rect(0, Hh - 12 * mm, W, 12 * mm, stroke=0, fill=1)
        c.setFillColor(colors.white)
        c.setFont("DVB", 9.5)
        c.drawString(18 * mm, Hh - 8 * mm, (br.name or "ConstruPilot")[:40])
        c.setFont("DV", 7.2)
        c.drawRightString(W - 18 * mm, Hh - 8 * mm, t("Note de calcul — ", "Memória de cálculo — ", "Calculation report — ", "Розрахунок — ") + str(pr.get("name", ""))[:60])
        c.setFillColor(colors.Color(0.45, 0.47, 0.50))
        c.drawString(18 * mm, 10 * mm, t("Pré-dimensionnement — à viser par un ingénieur structure", "Pré-dimensionamento — a verificar por engenheiro de estruturas",
                                         "Preliminary design — to be checked by a structural engineer", "Попередній розрахунок — перевіряє інженер-конструктор"))
        c.drawRightString(W - 18 * mm, 10 * mm, str(doc.page))
        c.restoreState()
    doc = SimpleDocTemplate(str(path), pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm, topMargin=20 * mm, bottomMargin=18 * mm,
                            title=t("Note de calcul CLT — ", "Memória de cálculo CLT — ", "CLT calculation report — ", "Розрахунок CLT — ") + str(pr.get("name", "")))
    doc.build(s, onFirstPage=page, onLaterPages=page)
