"""Dossier PDF premium da Carta de Obra de Baixo Carbono (PT) : capa com o logótipo e as cores da empresa, marca de água,
graphiques en couleur, synthèse RE2020, contrôles (manques et écarts aux imperatifs), suivi matériaux, émissions chantier,
grille de la charte, pièces justificatives et méthode."""
from __future__ import annotations

import io
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (Image, NextPageTemplate, PageBreak, PageTemplate, Frame, BaseDocTemplate, Paragraph,
                                Spacer, Table, TableStyle)

from . import referentiel as R

_FONTS = Path(__file__).resolve().parents[2] / "assets" / "fonts"
_REG = False
NIV_COL = {"bloquant": "#F8D7DA", "alerte": "#FFE5CC", "manquant": "#FFF3CD", "info": "#DCEBFA"}
NIV_LIB = {"bloquant": "Bloqueante", "alerte": "Fora do imperativo", "manquant": "Informação em falta", "info": "Info"}
ST_LIGHT = {"Conforme": "#D8F3DC", "Em curso": "#DCEBFA", "A iniciar": "#FFF3CD", "Não conforme": "#F8D7DA", "Não aplicável": "#EEEEEE"}
ST_COL = {"Conforme": "#2D6A4F", "Em curso": "#4C8DD6", "A iniciar": "#E9B949", "Não conforme": "#D64545", "Não aplicável": "#9AA5A0"}


def _fonts():
    global _REG
    if not _REG:
        pdfmetrics.registerFont(TTFont("CPS", str(_FONTS / "DejaVuSans.ttf")))
        pdfmetrics.registerFont(TTFont("CPS-B", str(_FONTS / "DejaVuSans-Bold.ttf")))
        _REG = True


def _n(x, d=0):
    if x is None:
        return "—"
    s = f"{x:,.{d}f}".replace(",", " ").replace(".", ",")
    return s


def _logos(b64):
    """(logótipo, logótipo esbatido para marca de água) a partir do logótipo original da empresa (base64 / data URI)."""
    if not b64:
        return None, None
    try:
        import base64
        from PIL import Image as PILImage
        raw = base64.b64decode(str(b64).split(",", 1)[-1])
        im = PILImage.open(io.BytesIO(raw)).convert("RGBA")
        bg = PILImage.new("RGBA", im.size, (255, 255, 255, 255))
        solid = PILImage.alpha_composite(bg, im).convert("RGB")
        pale = PILImage.blend(PILImage.new("RGB", im.size, (255, 255, 255)), solid, 0.07)
        out = []
        for x in (solid, pale):
            bio = io.BytesIO()
            x.save(bio, format="PNG")
            bio.seek(0)
            out.append(ImageReader(bio))
        return out[0], out[1]
    except Exception:  # noqa: BLE001 — logótipo ilegível : dossier sem logótipo, nunca bloqueado
        return None, None


def _png(fig) -> bytes:
    bio = io.BytesIO()
    fig.savefig(bio, format="png", dpi=170, bbox_inches="tight", transparent=False, facecolor="white")
    import matplotlib.pyplot as plt
    plt.close(fig)
    return bio.getvalue()


def _graphes(res: dict, accent: str) -> dict:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 9, "axes.spines.top": False, "axes.spines.right": False})
    out = {}
    # 1. par lot : référence vs réel
    lots = [(k, v) for k, v in res["par_lot"].items() if v["ref"] or v["reel"]]
    fig, ax = plt.subplots(figsize=(7.2, 3.2))
    if lots:
        names = [k.replace(" (AVAC / Eletricidade / Águas)", "\n(AVAC/Elet./Águas)").replace(" e ", "\ne ").replace(" / ", "\n/ ") for k, _ in lots]
        x = range(len(lots))
        ax.bar([i - 0.2 for i in x], [v["ref"] / 1000 for _, v in lots], 0.4, label="Referência", color="#B7C9BF")
        ax.bar([i + 0.2 for i in x], [v["reel"] / 1000 for _, v in lots], 0.4, label="Real da obra", color=accent)
        ax.set_xticks(list(x), names, fontsize=7.5)
        ax.set_ylabel("tCO2e")
        ax.legend(frameon=False)
        ax.grid(axis="y", alpha=0.25)
    else:
        ax.text(0.5, 0.5, "Nenhuma quantidade introduzida", ha="center", va="center", transform=ax.transAxes, color="#888")
        ax.set_axis_off()
    ax.set_title("Pegada dos materiais por capítulo", loc="left", fontweight="bold", color="#1B4332")
    out["lots"] = _png(fig)
    # 2. Ic vs seuil
    t = res["totaux"]
    fig, ax = plt.subplots(figsize=(3.6, 3.0))
    vals = [("Referência", t.get("ic_ref"), "#B7C9BF"), ("Real", t.get("ic_reel"), accent)]
    vals = [(a, b or 0, c) for a, b, c in vals]
    ax.bar([a for a, _, _ in vals], [b for _, b, _ in vals], color=[c for *_, c in vals], width=0.55)
    if t.get("seuil"):
        ax.axhline(t["seuil"], color="#D64545", lw=2, ls="--")
        ax.text(1.32, t["seuil"], f"Meta {t['seuil']:.0f}", color="#D64545", va="bottom", ha="right", fontsize=8, fontweight="bold")
    for i, (_, b, _) in enumerate(vals):
        ax.text(i, b, f"{b:.0f}", ha="center", va="bottom", fontsize=9, fontweight="bold")
    ax.set_ylabel("kgCO2e/m²")
    ax.set_title("Rácio (pilotagem)", loc="left", fontweight="bold", color="#1B4332")
    out["ic"] = _png(fig)
    # 3. charte
    st = {k: v for k, v in res["statuts_charte"].items() if v}
    fig, ax = plt.subplots(figsize=(3.6, 3.0))
    if st:
        ax.pie(list(st.values()), colors=[ST_COL[k] for k in st], startangle=90, counterclock=False,
               wedgeprops={"width": 0.38, "edgecolor": "white"})
        ax.text(0, 0, f"{res['statuts_charte'].get('Conforme', 0)}/{sum(res['statuts_charte'].values())}\nconformes", ha="center", va="center",
                fontsize=10, fontweight="bold", color="#1B4332")
        ax.legend([f"{k} ({v})" for k, v in st.items()], loc="center left", bbox_to_anchor=(1.0, 0.5), frameon=False, fontsize=8)
    ax.set_title("Compromissos da carta", loc="left", fontweight="bold", color="#1B4332")
    out["charte"] = _png(fig)
    # 4. contrôles
    cc = res["compte_controles"]
    fig, ax = plt.subplots(figsize=(3.6, 2.4))
    ks = ["bloquant", "alerte", "manquant", "info"]
    ax.barh([NIV_LIB[k] for k in ks][::-1], [cc[k] for k in ks][::-1], color=["#9DC3E6", "#F2C94C", "#F2994A", "#D64545"])
    for i, k in enumerate(ks[::-1]):
        ax.text(cc[k], i, f" {cc[k]}", va="center", fontweight="bold")
    ax.set_title("Controlos", loc="left", fontweight="bold", color="#1B4332")
    ax.set_xticks([])
    out["ctrl"] = _png(fig)
    return out


def construire(res: dict, branding: dict | None = None, entreprise: str = "") -> bytes:
    _fonts()
    b = branding or {}
    accent = str(b.get("accent_color") or "#2D6A4F")
    if not accent.startswith("#") or len(accent) not in (4, 7):
        accent = "#2D6A4F"
    ACC = colors.HexColor(accent)
    V = colors.HexColor("#1B4332")
    s = lambda n, **k: ParagraphStyle(n, fontName=k.pop("f", "CPS"), fontSize=k.pop("sz", 8.6), leading=k.pop("ld", 11), **k)   # noqa: E731
    H1 = s("h1", f="CPS-B", sz=15, ld=19, textColor=V, spaceAfter=6)
    H2 = s("h2", f="CPS-B", sz=11, ld=14, textColor=ACC, spaceBefore=8, spaceAfter=4)
    P = s("p")
    PS = s("ps", sz=7.4, ld=9.2)
    PB = s("pb", f="CPS-B", sz=7.6, ld=9.4, textColor=colors.white)
    g = _graphes(res, accent)
    pr, t = res["projet"], res["totaux"]

    bio = io.BytesIO()
    doc = BaseDocTemplate(bio, pagesize=A4, leftMargin=14 * mm, rightMargin=14 * mm, topMargin=16 * mm, bottomMargin=16 * mm,
                          title=f"Carta de obra de baixo carbono — {pr.get('nom') or 'Projeto'}", author=entreprise or "ConstruPilot")
    fp = Frame(doc.leftMargin, doc.bottomMargin, doc.width, doc.height, id="p")
    LW, LH = landscape(A4)
    fl = Frame(14 * mm, 14 * mm, LW - 28 * mm, LH - 30 * mm, id="l")

    def deco(c, d):
        c.saveState()
        c.setFont("CPS", 7)
        c.setFillColor(colors.HexColor("#6B7280"))
        c.drawString(14 * mm, 9 * mm, f"Carta de obra de baixo carbono — {pr.get('nom') or ''}  ·  {entreprise or 'ConstruPilot'}")
        c.drawRightString(d.pagesize[0] - 14 * mm, 9 * mm, f"p. {c.getPageNumber()}")
        _filigrane(c, d)
        c.restoreState()
    logo, logo_pale = _logos(b.get("logo_b64"))

    def _filigrane(c, d):                       # logótipo da empresa em marca de água (como nos orçamentos)
        if logo_pale is None:
            return
        W, H = d.pagesize
        w = min(W, H) * 0.55
        h = w * logo_pale.getSize()[1] / max(1, logo_pale.getSize()[0])
        c.drawImage(logo_pale, (W - w) / 2, (H - h) / 2, w, h, mask="auto")

    def capa(c, d):
        W, H = A4
        c.saveState()
        c.setFillColor(colors.HexColor("#F7F5EF"))
        c.rect(0, 0, W, H, stroke=0, fill=1)
        c.setFillColor(ACC)
        c.rect(0, H - 92 * mm, W, 92 * mm, stroke=0, fill=1)
        if logo is not None:
            lw, lh = logo.getSize()
            h = 22 * mm
            w = min(70 * mm, h * lw / max(1, lh))
            c.setFillColor(colors.white)
            c.roundRect(14 * mm, H - 40 * mm, w + 8 * mm, h + 8 * mm, 3 * mm, stroke=0, fill=1)
            c.drawImage(logo, 18 * mm, H - 36 * mm, w, h, preserveAspectRatio=True, mask="auto")
        c.setFillColor(colors.white)
        c.setFont("CPS-B", 10)
        c.drawRightString(W - 14 * mm, H - 20 * mm, (entreprise or "ConstruPilot")[:60])
        c.setFont("CPS", 9)
        c.drawRightString(W - 14 * mm, H - 26 * mm, "BALANÇO DE CARBONO & CUMPRIMENTO DA META")
        c.setFont("CPS-B", 26)
        c.drawString(14 * mm, H - 62 * mm, "Carta de obra de baixo carbono")
        c.setFont("CPS", 12)
        c.drawString(14 * mm, H - 72 * mm, (pr.get("nom") or "Projeto")[:80])
        c.setFont("CPS", 9)
        c.drawString(14 * mm, H - 80 * mm, " · ".join(x for x in ((pr.get("adresse") or "")[:70], str(pr.get("date") or "")) if x))
        kp = [("Balanço real", f"{_n(t['total_reel'] / 1000, 1)}", "tCO2e"), ("Rácio real", _n(t.get("ic_reel")), "kgCO2e/m²"),
              ("Meta", _n(t.get("seuil")) if t.get("seuil") else "a definir", "kgCO2e/m²"), ("Ganho materiais", f"{t['reduction']:.0%}", ""),
              ("Carta conforme", f"{res['statuts_charte'].get('Conforme', 0)}/{sum(res['statuts_charte'].values())}", ""),
              ("Controlos abertos", str(sum(res["compte_controles"][k] for k in ("bloquant", "alerte", "manquant"))), "")]
        bw, bh, x0, y0 = (W - 28 * mm - 10 * mm) / 3, 24 * mm, 14 * mm, H - 128 * mm
        for i, (lab, val, u) in enumerate(kp):
            x, y = x0 + (i % 3) * (bw + 5 * mm), y0 - (i // 3) * (bh + 5 * mm)
            c.setFillColor(colors.white)
            c.roundRect(x, y, bw, bh, 2.5 * mm, stroke=0, fill=1)
            c.setFillColor(ACC)
            c.rect(x, y, 1.6 * mm, bh, stroke=0, fill=1)
            c.setFillColor(colors.HexColor("#6B7280"))
            c.setFont("CPS", 7.5)
            c.drawString(x + 5 * mm, y + bh - 7 * mm, lab.upper())
            c.setFillColor(V)
            c.setFont("CPS-B", 17)
            c.drawString(x + 5 * mm, y + 6 * mm, str(val))
            c.setFont("CPS", 7.5)
            c.drawString(x + 5 * mm + pdfmetrics.stringWidth(str(val), "CPS-B", 17) + 2 * mm, y + 6.5 * mm, u)
        img = ImageReader(io.BytesIO(g["lots"]))
        iw, ih = img.getSize()
        w = W - 28 * mm
        c.drawImage(img, 14 * mm, 34 * mm, w, w * ih / iw, mask="auto")
        c.setFillColor(colors.HexColor("#6B7280"))
        c.setFont("CPS", 7)
        c.drawString(14 * mm, 14 * mm, "Documento gerado pelo ConstruPilot — pilotagem de obra ; não substitui o cálculo do PAG do ciclo de vida (Diretiva (UE) 2024/1275).")
        c.restoreState()

    fc = Frame(doc.leftMargin, doc.bottomMargin, doc.width, doc.height, id="c")
    doc.addPageTemplates([PageTemplate("C", [fc], onPage=capa, pagesize=A4), PageTemplate("P", [fp], onPage=deco, pagesize=A4),
                          PageTemplate("L", [fl], onPage=deco, pagesize=landscape(A4))])

    def tab(data, widths, head=True, zebra=True, extra=None, font=7.4):
        rows = [[c if hasattr(c, "wrap") else Paragraph(str(c if c is not None else ""), PB if (head and i == 0) else PS) for c in r]
                for i, r in enumerate(data)]
        tb = Table(rows, colWidths=widths, repeatRows=1 if head else 0)
        st = [("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#C9D6CF")), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
              ("TOPPADDING", (0, 0), (-1, -1), 2.5), ("BOTTOMPADDING", (0, 0), (-1, -1), 2.5)]
        if head:
            st.append(("BACKGROUND", (0, 0), (-1, 0), V))
        if zebra:
            for i in range(1 if head else 0, len(rows)):
                if i % 2 == 0:
                    st.append(("BACKGROUND", (0, i), (-1, i), colors.HexColor("#F0F7F4")))
        tb.setStyle(TableStyle(st + (extra or [])))
        return tb

    E = [Spacer(1, 1), NextPageTemplate("P"), PageBreak()]
    # ------------------------------------------------------------------ synthèse
    E.append(Paragraph("Síntese de carbono & cumprimento da meta", H1))
    stat = ("CUMPRE A META" if t.get("conforme") else "ACIMA DA META" if t.get("conforme") is False
            else "INCOMPLETO — famílias sem fator de emissão (ver controlos)" if any(c["code"] == "RE-02" for c in res["controles"]) else "DADOS EM FALTA")
    stc = "#2D6A4F" if t.get("conforme") else "#D64545" if t.get("conforme") is False else "#B7791F"
    kp = [("Balanço total real", f"{_n(t['total_reel'] / 1000, 1)} tCO2e"), ("Rácio real", f"{_n(t.get('ic_reel'))} kgCO2e/m²"),
          ("Meta (dono de obra)", f"{_n(t.get('seuil'))} kgCO2e/m²" if t.get("seuil") else "a definir"), ("Ganho materiais", f"{_n(t['gain'] / 1000, 1)} t ({t['reduction']:.0%})")]
    cards = Table([[Paragraph(f"<font size=7 color='#6B7280'>{a}</font><br/><font name='CPS-B' size=11.5 color='{accent}'>{b}</font>", P) for a, b in kp]],
                  colWidths=[doc.width / 4] * 4)
    cards.setStyle(TableStyle([("BOX", (0, 0), (-1, -1), 0.4, colors.HexColor("#C9D6CF")), ("INNERGRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#C9D6CF")),
                               ("TOPPADDING", (0, 0), (-1, -1), 6), ("BOTTOMPADDING", (0, 0), (-1, -1), 6)]))
    E += [cards, Spacer(1, 5)]
    E.append(Paragraph(f"<font name='CPS-B' color='{stc}'>Estado : {stat}</font> — tipologia {pr.get('typologie')}, área de referência {_n(pr.get('sref_m2'))} m², "
                       f"meta : {pr.get('seuil_source') or 'a introduzir (sem valor-limite legal em Portugal)'}.", P))
    E.append(Spacer(1, 4))
    E.append(Image(io.BytesIO(g["lots"]), width=doc.width, height=doc.width * 3.2 / 7.2 * 0.92))
    row = Table([[Image(io.BytesIO(g["ic"]), width=58 * mm, height=48 * mm), Image(io.BytesIO(g["charte"]), width=64 * mm, height=50 * mm),
                  Image(io.BytesIO(g["ctrl"]), width=58 * mm, height=39 * mm)]], colWidths=[doc.width / 3] * 3)
    E.append(row)
    E.append(Paragraph("Rácio do quadro = indicador de pilotagem (soma estática quantidade × FE / área). O PAG do ciclo de vida exigido pela "
                       "Diretiva (UE) 2024/1275 resulta de uma ACV completa feita com software próprio.", PS))
    # bilan + lots
    E.append(Paragraph("Balanço consolidado", H2))
    tot = t["total_reel"] or 1
    E.append(tab([["Rubrica do balanço", "kgCO2e", "tCO2e", "Parte"],
                  ["Pegada materiais (referência)", _n(t["materiaux_ref"]), _n(t["materiaux_ref"] / 1000, 2), "—"],
                  ["Pegada materiais (real da obra)", _n(t["materiaux_reel"]), _n(t["materiaux_reel"] / 1000, 2), f"{t['materiaux_reel'] / tot:.0%}"],
                  ["Emissões da fase de obra", _n(t["chantier"]), _n(t["chantier"] / 1000, 2), f"{t['chantier'] / tot:.0%}"],
                  ["TOTAL BALANÇO DE CARBONO (real)", _n(t["total_reel"]), _n(t["total_reel"] / 1000, 2), "100%"],
                  ["Ganho de carbono nos materiais", _n(t["gain"]), _n(t["gain"] / 1000, 2), f"{t['reduction']:.1%}"]],
                 [doc.width * 0.52, doc.width * 0.18, doc.width * 0.15, doc.width * 0.15]))

    # ------------------------------------------------------------------ contrôles
    E.append(PageBreak())
    E.append(Paragraph("Cruzamento com os imperativos da obra", H1))
    cc = res["compte_controles"]
    E.append(Paragraph(f"{cc['bloquant']} bloqueante(s) · {cc['alerte']} resultado(s) fora do imperativo · {cc['manquant']} informação(ões) em falta · "
                       f"{cc['info']} ponto(s) de atenção. Linhas de materiais justificadas por uma DAP : "
                       f"{res['completude']['avec_fdes']} / {res['completude']['lignes']}.", P))
    E.append(Spacer(1, 4))
    if res["controles"]:
        data = [["Nível", "Código", "Constatação", "Ação esperada da empresa"]]
        ex = []
        for i, c in enumerate(res["controles"], 1):
            data.append([NIV_LIB[c["niveau"]], c["code"], c["message"], c.get("action") or ""])
            ex.append(("BACKGROUND", (0, i), (-1, i), colors.HexColor(NIV_COL[c["niveau"]])))
        E.append(tab(data, [22 * mm, 15 * mm, doc.width * 0.47, doc.width - 37 * mm - doc.width * 0.47], zebra=False, extra=ex))
    else:
        E.append(Paragraph("Nenhum desvio : todas as informações esperadas estão presentes e dentro dos imperativos da obra.", P))

    # ------------------------------------------------------------------ matériaux (paysage)
    E += [NextPageTemplate("L"), PageBreak(), Paragraph("Acompanhamento da pegada de carbono dos materiais", H1)]
    W = LW - 28 * mm
    data = [["Capítulo", "Família / solução", "Tipo", "Qtd.", "U", "FE ref.", "FE DAP", "Ref. DAP", "Dist. km", "Peso ref. kg", "Peso real kg", "Ganho", "Controlo"]]
    ex = []
    act = [m for m in res["materiaux"] if m.get("actif")]
    for i, m in enumerate(act, 1):
        ctl = m.get("controles") or []
        worst = next((n for n in ("bloquant", "alerte", "manquant") if any(c["niveau"] == n for c in ctl)), None)
        data.append([m.get("lot"), f"<b>{m.get('famille')}</b><br/>{m.get('solution') or ''}", m.get("typologie"),
                     _n(m.get("quantite"), 2), m.get("unite"), _n(m.get("fe_ref"), 2), _n(m.get("fe_fdes"), 2), m.get("ref_fdes") or "—",
                     _n(m.get("distance_km")), _n(m["poids_ref"]), _n(m["poids_reel"]), f"{m['reduction']:.0%}",
                     ", ".join(sorted({c["code"] for c in ctl})) or "OK"])
        if worst:
            ex.append(("BACKGROUND", (12, i), (12, i), colors.HexColor(NIV_COL[worst])))
    if len(data) == 1:
        data.append(["—", "Nenhuma linha preenchida", "", "", "", "", "", "", "", "", "", "", ""])
    data.append(["", "<b>TOTAL</b>", "", "", "", "", "", "", "", _n(t["materiaux_ref"]), _n(t["materiaux_reel"]), f"{t['reduction']:.0%}", ""])
    E.append(tab(data, [w * W for w in (0.10, 0.19, 0.075, 0.07, 0.035, 0.055, 0.06, 0.105, 0.05, 0.075, 0.075, 0.045, 0.065)], extra=ex))
    E.append(Paragraph("Sem DAP, a linha conta com o fator de referência (nenhum ganho reivindicado). Quantidade considerada = quantidade entregue "
                       "(guias de remessa) se existir, senão a quantidade prevista na medição.", PS))
    # émissions
    E.append(Paragraph("Emissões da fase de obra", H2))
    data = [["Fonte", "Recurso", "Quantidade", "Unidade", "FE", "Unidade FE", "kgCO2e"]]
    for e in res["emissions"]:
        data.append([e["poste"], e["ressource"], _n(e["quantite"], 1), e["unite"], f"{e['fe']:g}", e["unite_fe"], _n(e["total"], 1)])
    data.append(["", "<b>TOTAL</b>", "", "", "", "", _n(t["chantier"], 1)])
    E.append(tab(data, [w * W for w in (0.15, 0.35, 0.1, 0.07, 0.08, 0.12, 0.13)]))
    # charte
    E += [PageBreak(), Paragraph("Grelha de acompanhamento da carta", H1)]
    data = [["Eixo", "Compromisso", "Indicador", "Objetivo", "Realizado", "Origem", "Responsável", "Estado", "Prova esperada"]]
    ex = []
    for i, c in enumerate(res["charte"], 1):
        sym = "≥" if c.get("op") == ">=" else "≤"
        data.append([c["axe"], c["action"], c["kpi"], f"{sym} {c['cible']:g} {c['unite']}",
                     "—" if c.get("realise") is None else f"{c['realise']:g} {c['unite']}", c.get("source_realise") or "", c["acteur"],
                     f"<b>{c['statut']}</b>", c["preuve"]])
        ex.append(("BACKGROUND", (7, i), (7, i), colors.HexColor(ST_LIGHT[c["statut"]])))
    E.append(tab(data, [w * W for w in (0.11, 0.20, 0.16, 0.07, 0.07, 0.08, 0.09, 0.08, 0.14)], extra=ex))
    # pièces
    E += [NextPageTemplate("P"), PageBreak(), Paragraph("Documentos justificativos e método", H1)]
    docs = res.get("documents") or []
    if docs:
        ids = {m["id"]: m.get("famille") for m in res["materiaux"]}
        data = [["Ficheiro", "Tipo", "Estado", "Associado a", "Observações"]]
        for d_ in docs:
            data.append([d_.get("nom"), d_.get("type_libelle") or d_.get("type"), d_.get("statut"),
                         ids.get(d_.get("rattache_a"), d_.get("rattache_a") or "NÃO ASSOCIADO"), " | ".join(d_.get("notes") or [])[:300]])
        E.append(tab(data, [doc.width * w for w in (0.26, 0.18, 0.09, 0.2, 0.27)]))
    else:
        E.append(Paragraph("Nenhum documento depositado : as empresas depositam as DAP, fichas técnicas, guias de remessa, e-GAR e faturas de "
                           "gasóleo no ConstruPilot (Obra › Baixo carbono) ; o quadro preenche-se e controla-se automaticamente.", P))
    E.append(Paragraph("Método e fontes", H2))
    for a, b in (("Meta", R.SOURCE_RE2020 + "."), ("Fatores de referência", R.SOURCE_TABLEAU + "."), ("Eletricidade", R.SOURCE_ELEC + "."),
                 ("DAP", "Alterações climáticas — total (GWP-total), ciclo de vida A1 a C4 sem o módulo D ; um valor lido pela IA só é aceite se figurar no documento ; validade 5 anos."),
                 ("Guias de remessa", "Quantidades acumuladas por família, guias duplicadas excluídas ; distância escrita na guia, senão em linha reta por geocodificação, a confirmar."),
                 ("Resíduos", "e-GAR (SILiAmb) : operações R = valorização, D = eliminação."),
                 ("Limites", "Pilotagem da obra : não substitui o cálculo do PAG do ciclo de vida feito com software próprio.")):
        E.append(Paragraph(f"<b>{a}</b> — {b}", P))
    if res.get("decisions"):
        E.append(Paragraph("Decisões registadas", H2))
        for x in res["decisions"][:60]:
            E.append(Paragraph("• " + x, PS))
    doc.build(E)
    pdf = bio.getvalue()
    return pdf
