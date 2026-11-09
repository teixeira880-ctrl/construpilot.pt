"""Note PDF « PAC air-eau réversible » au nom de l'entreprise (logo d'en-tête + filigrane, comme les devis)."""
from __future__ import annotations

import base64
import io
from pathlib import Path

ASSETS = Path(__file__).with_name("assets")
DEFAULT_ACCENT = "#1e8f4e"


def brand_for(branding: dict | None):
    """Identité de l'entreprise (Pro / Pro Business) ; à défaut, ConstruPilot avec son logo."""
    from engines.bet_core import brand as B
    b = dict(branding or {})
    if not b.get("logo_b64") and not b.get("company_name"):
        b = {"company_name": "ConstruPilot", "contact_line": "construpilot.fr", "accent_color": DEFAULT_ACCENT,
             "logo_b64": base64.b64encode((ASSETS / "construpilot-logo.png").read_bytes()).decode()}
    return B.from_branding(b, "FR")


def _hex(c) -> str:
    return "#%02x%02x%02x" % (int(c.red * 255), int(c.green * 255), int(c.blue * 255))


def fr(x: float, d: int = 2) -> str:
    return f"{x:.{d}f}".replace(".", ",")


def build_pdf(res: dict, level_pngs: dict[str, bytes], principle: bytes, br, project: str, sources: str) -> bytes:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import cm
    from reportlab.platypus import (BaseDocTemplate, Frame, Image, KeepTogether, ListFlowable, ListItem, NextPageTemplate,
                                    PageBreak, PageTemplate, Paragraph, Spacer, Table, TableStyle)
    from engines.bet_core import brand as B

    acc = br.accent
    T = ParagraphStyle("t", fontName="DVB", fontSize=16, leading=21, spaceAfter=6, textColor=acc)
    H = ParagraphStyle("h", fontName="DVB", fontSize=12, leading=15, spaceBefore=10, spaceAfter=4, textColor=acc)
    Bs = ParagraphStyle("b", fontName="DV", fontSize=9.5, leading=13.5)
    S = ParagraphStyle("s", parent=Bs, fontSize=8.5, textColor="#555555")

    def ul(items):
        return ListFlowable([ListItem(Paragraph(i, Bs), leftIndent=10) for i in items], bulletType="bullet", start="•", leftIndent=10)

    def tbl(rows, widths):
        t = Table(rows, colWidths=widths, repeatRows=1)
        t.setStyle(TableStyle([("FONT", (0, 0), (-1, -1), "DV", 8.5), ("FONT", (0, 0), (-1, 0), "DVB", 8.5),
                               ("BACKGROUND", (0, 0), (-1, 0), br.tint if hasattr(br, "tint") else colors.HexColor("#e8f3ec")),
                               ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#c4ccd4")),
                               ("ALIGN", (1, 1), (-1, -1), "CENTER"), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                               ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3)]))
        return t

    lvs = res["heated_levels"]
    L = res["levels"]
    tot_area = sum(sum(x["area"] for x in L[n]["loops"]) for n in lvs)
    vcs = [(n, v) for n in lvs for v in L[n]["vc"]]
    story = [Paragraph(f"{project}<br/>PAC air-eau réversible : plancher chauffant-rafraîchissant et ventilo-convecteurs plafond", T),
             Paragraph(f"Fonds de plan : {sources}", ParagraphStyle("m", parent=S, spaceAfter=4)),
             Paragraph("1. Principe retenu", H),
             Paragraph("Un groupe extérieur PAC air-eau réversible alimente un module hydraulique avec ballon tampon (50–100 L : "
                       "anti-cycles courts), vase d'expansion, soupape de sécurité et pot de décantation magnétique. Deux circuits en partent :", Bs),
             ul([f"<b>Circuit 1 – plancher chauffant-rafraîchissant</b> ({fr(tot_area)} m² sur {len(lvs)} niveau(x)) : environ 35 °C en hiver, "
                 "environ 18 °C en été, jamais sous le point de rosée (sonde de point de rosée sur chaque départ, vanne mélangeuse).",
                 f"<b>Circuit 2 – ventilo-convecteurs plafond</b> ({len(vcs)} unités) : eau froide ≈ 7 °C, vanne deux voies, bac et pompe de "
                 "relevage des condensats par unité, réseau isolé anticondensation."]),
             Paragraph("2. Implantation", H), ul(res["decisions"] + [
                 f"<b>{e['label'].replace(chr(10), ' ')}</b> ({n}) : {e['room']}." for n in lvs for e in L[n]["equipment"]
                 if e["kind"] == "collecteur"])]
    for i, n in enumerate(lvs):
        rows = [["Pièce", "Surface", "Pas", "Boucles", "L / boucle"]]
        for lp in L[n]["loops"]:
            rows.append([lp["room"], f"{fr(lp['area'])} m²", f"{int(lp['pitch'] * 100)} cm", str(lp["loops"]), f"≈ {lp['length']:.0f} m"])
        rows.append(["Total", f"{fr(sum(x['area'] for x in L[n]['loops']))} m²", "", str(L[n].get("collector_outlets", 0)), ""])
        story.append(KeepTogether([Paragraph(f"{3 + i}. Boucles de plancher {n} (pré-dimensionnement)", H),
                                   tbl(rows, [4.6 * cm, 2.6 * cm, 2 * cm, 2.2 * cm, 2.8 * cm])]))
    story.append(Paragraph("Tube PER Ø16, longueur maximale 120 m par boucle (amenées comprises). Thermostat chaud / froid par pièce.", S))
    k = 3 + len(lvs)
    rows = [["Repère", "Niveau", "Pièce", "Évacuation des condensats"]]
    for n, v in vcs:
        rows.append([v["id"], n, v["room"], f"Pompe de relevage → EU {v['drain_to']}"])
    if vcs:
        story.append(KeepTogether([Paragraph(f"{k}. Ventilo-convecteurs plafond", H), tbl(rows, [2 * cm, 1.8 * cm, 4.6 * cm, 6.2 * cm])]))
        k += 1
    story.append(KeepTogether([Paragraph(f"{k}. Points à valider", H), ul(res["checks"])]))
    k += 1
    story.append(NextPageTemplate("l"))
    for n in lvs:
        story += [PageBreak(), Paragraph(f"{k}. Plan d'implantation — {n}", H)]
        w = 22.5 * cm
        story.append(Image(io.BytesIO(level_pngs[n]), width=w, height=w * 2 / 3))
        k += 1
    story += [PageBreak(), Paragraph(f"{k}. Schéma de principe", H), Image(io.BytesIO(principle), width=19 * cm, height=19 * cm * 0.74)]

    def deco(c, d):
        W, Hh = c._pagesize
        c.saveState()
        B.watermark(c, W / 2, Hh / 2, min(W, Hh) * 0.55, br)
        B.draw_logo(c, 1.5 * cm, Hh - 1.95 * cm, 4.5 * cm, 1.2 * cm, br)
        c.setFillColor(colors.HexColor("#666666")); c.setFont("DV", 8)
        c.drawRightString(W - 1.5 * cm, Hh - 1.3 * cm, f"{project} — PAC réversible")
        c.setStrokeColor(acc); c.setLineWidth(1.2); c.line(1.5 * cm, Hh - 2.15 * cm, W - 1.5 * cm, Hh - 2.15 * cm)
        c.setLineWidth(0.5); c.line(1.5 * cm, 1.3 * cm, W - 1.5 * cm, 1.3 * cm)
        c.setFont("DV", 7.5)
        foot = " · ".join([br.name] + list(br.lines or [])[:2])
        c.drawString(1.5 * cm, 0.85 * cm, foot[:120])
        c.drawRightString(W - 1.5 * cm, 0.85 * cm, f"Page {d.page}")
        if br.is_client and br.name != "ConstruPilot":
            c.setFont("DV", 6.5); c.drawCentredString(W / 2, 0.45 * cm, "Étude réalisée avec ConstruPilot")
        c.restoreState()

    buf = io.BytesIO()
    pw, ph = A4
    lw, lh = landscape(A4)
    doc = BaseDocTemplate(buf, pagesize=A4, title=f"{project} – PAC réversible plancher et plafond", author=br.name)
    doc.addPageTemplates([PageTemplate("p", [Frame(2 * cm, 1.8 * cm, pw - 4 * cm, ph - 4.4 * cm)], pagesize=A4, onPage=deco),
                          PageTemplate("l", [Frame(1.5 * cm, 1.5 * cm, lw - 3 * cm, lh - 3.9 * cm)], pagesize=landscape(A4), onPage=deco)])
    doc.build(story)
    return buf.getvalue()


def run(pdf: bytes, placements: list[dict] | None = None, branding: dict | None = None, project: str | None = None,
        filename: str | None = None, pages: list[dict] | None = None) -> dict:
    """Chaîne complète (synchrone, à lancer dans un thread) : lecture des planches → implantation → plans PNG → PDF."""
    from . import layout, plans, render
    pp = pages or plans.plan_pages(pdf)
    if not pp:
        return {"ok": False, "error": "Aucune planche « Plan RDC / R+1 … » avec des étiquettes de pièces (S : xx m²) dans ce document."}
    levels = plans.read_plans(pdf, pp)
    if not levels:
        return {"ok": False, "error": "Pièces illisibles sur les planches de plans (PDF scanné ?) : joindre le PDF vectoriel du DCE / PC."}
    res = layout.compute(levels, placements)
    if not res.get("ok"):
        return res
    for lv in levels:
        res["checks"] += [n for n in lv.notes if n not in res["checks"]]
    br = brand_for(branding)
    logo = br.logo_bytes
    project = project or _project_name(pdf) or (filename or "Projet").rsplit(".", 1)[0]
    pngs = {}
    for lv in levels:
        if lv.name not in res["heated_levels"]:
            continue
        bg = plans.render_page(pdf, lv.page)
        pngs[lv.name] = render.level_png(bg, lv, res, br.name, _hex(br.accent), logo, project,
                                         f"plan {lv.name} de l'architecte, planche {lv.page + 1} au 1:{lv.scale}",
                                         plans.RENDER_DPI / plans.DPI)
    principle = render.principle_png(res)
    sources = ", ".join(f"plan {lv.name} (p. {lv.page + 1}, 1:{lv.scale})" for lv in levels) + (f" — {filename}" if filename else "")
    pdf_out = build_pdf(res, pngs, principle, br, project, sources)
    res = {k: v for k, v in res.items()}
    for n in res["levels"]:
        for nw in res["levels"][n]["networks"]:
            nw["path"] = [(round(float(x), 1), round(float(y), 1)) for x, y in nw["path"]]
    return {"ok": True, "result": res, "pngs": pngs, "pdf": pdf_out, "project": project,
            "pages": [{"page": lv.page, "level": lv.name, "scale": lv.scale} for lv in levels]}


def _project_name(pdf: bytes) -> str | None:
    """Nom du projet lu dans le cartouche (« HOUILLES _ Construction d'une maison individuelle_DCE »)."""
    import re
    import pymupdf
    try:
        with pymupdf.open(stream=pdf, filetype="pdf") as doc:
            for pg in doc:
                for line in pg.get_text().splitlines():
                    m = re.match(r"\s*([A-ZÉÈÀÂ][A-ZÉÈÀÂ' -]{2,40})\s*_\s*(.{5,80})$", line)
                    if m:
                        name = m.group(1).strip().title() if len(m.group(1).strip()) > 3 else m.group(1).strip()
                        what = re.sub(r"[_\s]*(DCE|PC|APD|APS|PRO|EXE)\s*$", "", m.group(2)).strip(" _")
                        return f"{m.group(1).strip()} — {what[:1].upper() + what[1:]}" if what else m.group(1).strip()
    except Exception:  # noqa: BLE001
        return None
    return None
