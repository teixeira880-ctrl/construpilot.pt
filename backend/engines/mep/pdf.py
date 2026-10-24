"""Dossier PDF A3 paysage : synthèse, plans électricité et plomberie par niveau,
schéma unifilaire, circuits, nomenclature, contrôles. Avertissement sur chaque page."""
from __future__ import annotations

import io
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A3, landscape
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (Flowable, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table,
                                TableStyle)

from . import render as R
from .i18n import tr
from .rules import rules_for

_FONT = "Helvetica"
_FONT_B = "Helvetica-Bold"


def _fonts():
    global _FONT, _FONT_B
    if _FONT == "MEPSans":
        return
    here = Path(__file__).resolve().parents[2] / "assets" / "fonts"
    cands = [here, Path("/usr/share/fonts/truetype/dejavu")]
    for d in cands:
        reg, bold = d / "DejaVuSans.ttf", d / "DejaVuSans-Bold.ttf"
        if reg.exists() and bold.exists():
            try:
                pdfmetrics.registerFont(TTFont("MEPSans", str(reg)))
                pdfmetrics.registerFont(TTFont("MEPSans-Bold", str(bold)))
                _FONT, _FONT_B = "MEPSans", "MEPSans-Bold"
            except Exception:  # noqa: BLE001 — repli Helvetica
                pass
            return


class SceneBox(Flowable):
    def __init__(self, scene, width, height, legend=None, legend_w=92 * mm):
        super().__init__()
        self.scene, self.w, self.h, self.legend, self.lw = scene, width, height, legend, legend_w

    def wrap(self, aw, ah):
        return self.w, self.h

    def draw(self):
        c = self.canv
        c.setStrokeColor(colors.HexColor("#D0D4D9"))
        c.setLineWidth(0.6)
        c.rect(0, 0, self.w, self.h)
        lw = self.lw if self.legend else 0
        self.scene.draw(c, 4, 4, self.w - lw - 8, self.h - 8, _FONT, _FONT_B)
        if self.legend:
            c.setFillColor(colors.HexColor("#F8FAFC"))
            c.rect(self.w - lw, 0, lw, self.h, stroke=1, fill=1)
            self.legend.draw(c, self.w - lw + 6, 6, lw - 12, self.h - 12, _FONT, _FONT_B, margin=0.3,
                             max_scale=42, align_top=True)


def _styles():
    base = dict(fontName=_FONT, fontSize=9, leading=12, textColor=colors.HexColor(R.NAVY))
    return {
        "h1": ParagraphStyle("h1", **{**base, "fontName": _FONT_B, "fontSize": 22, "leading": 27}),
        "h2": ParagraphStyle("h2", **{**base, "fontName": _FONT_B, "fontSize": 14, "leading": 18,
                                      "textColor": colors.HexColor(R.BRAND)}),
        "p": ParagraphStyle("p", **base),
        "small": ParagraphStyle("small", **{**base, "fontSize": 7.5, "leading": 9.5}),
        "warn": ParagraphStyle("warn", **{**base, "fontName": _FONT_B, "fontSize": 10, "leading": 13,
                                          "textColor": colors.HexColor("#9A3412"), "backColor": colors.HexColor("#FFF7ED"),
                                          "borderColor": colors.HexColor(R.BRAND), "borderWidth": 1, "borderPadding": 6}),
    }


def _table(rows, widths, header=True, zebra=True, font_size=8):
    t = Table(rows, colWidths=widths, repeatRows=1 if header else 0)
    st = [("FONT", (0, 0), (-1, -1), _FONT, font_size), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
          ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#D0D4D9")),
          ("LEFTPADDING", (0, 0), (-1, -1), 4), ("RIGHTPADDING", (0, 0), (-1, -1), 4)]
    if header:
        st += [("BACKGROUND", (0, 0), (-1, 0), colors.HexColor(R.NAVY)), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
               ("FONT", (0, 0), (-1, 0), _FONT_B, font_size)]
    if zebra:
        for i in range(1, len(rows)):
            if i % 2 == 0:
                st.append(("BACKGROUND", (0, i), (-1, i), colors.HexColor("#F8FAFC")))
    t.setStyle(TableStyle(st))
    return t


L = {
    "fr": {"status": "Statut", "errs": "{e} erreur(s), {w} point(s) à vérifier", "surface": "Surface (hors garage)",
           "points": "Points électriques", "board": "tableau", "fixtures": "Appareils sanitaires", "cables": "Câbles",
           "hyp_route": "Cheminement des câbles : {r} ; surlongueur {p} %.",
           "hyp_ecs": "Production d'eau chaude : {h} ; distribution en pieuvre depuis nourrice(s).",
           "hyp_depth": "Profondeur disponible pour les évacuations : {a} m à l'étage, {b} m sous dallage.",
           "hyp_auto": "Positions des appareils marqués « auto » proposées par le moteur ; les autres sont reprises du plan.",
           "hyp_price": "Les prix ne sont jamais estimés par l'IA : ils proviennent de la bibliothèque de prix de l'entreprise.",
           "h_circ": ["Circuit", "Désignation", "Section", "Protection", "DDR", "Points", "Longueur"],
           "supplies": "Alimentations", "drains": "Évacuations",
           "h_sup": ["Réf.", "Réseau", "Appareil", "Tube", "Débit", "Vitesse", "Longueur"],
           "main": "Alimentation générale",
           "h_drn": ["Réf.", "Réseau", "Appareil", "Vers", "Ø", "Pente", "Longueur", "Dénivelé / dispo"],
           "h_q": ["Code", "Désignation", "Unité", "Quantité", "P.U. HT", "Total HT"], "to_price": "à chiffrer",
           "price_note": "Prix : bibliothèque de prix de l'entreprise uniquement — aucune valeur estimée par l'IA.",
           "h_chk": ["Domaine", "Statut", "Contrôle", "Référence"], "elec": "Électricité", "plumb": "Plomberie"},
    "pt": {"status": "Estado", "errs": "{e} erro(s), {w} ponto(s) a verificar", "surface": "Área (sem garagem)",
           "points": "Pontos elétricos", "board": "quadro", "fixtures": "Aparelhos sanitários", "cables": "Cabos",
           "hyp_route": "Passagem dos cabos: {r}; folga {p} %.",
           "hyp_ecs": "Produção de água quente: {h}; distribuição em coletor (sistema em estrela).",
           "hyp_depth": "Espessura disponível para esgotos: {a} m no piso, {b} m sob a laje térrea.",
           "hyp_auto": "Aparelhos marcados «auto» posicionados pelo motor; os restantes vêm da planta.",
           "hyp_price": "Os preços nunca são estimados pela IA: vêm da tabela de preços da empresa.",
           "h_circ": ["Circuito", "Designação", "Secção", "Proteção", "Diferencial", "Pontos", "Comprimento"],
           "supplies": "Abastecimento", "drains": "Esgotos",
           "h_sup": ["Ref.", "Rede", "Aparelho", "Tubo", "Caudal", "Velocidade", "Comprimento"],
           "main": "Ramal de alimentação",
           "h_drn": ["Ref.", "Rede", "Aparelho", "Para", "Ø", "Inclinação", "Comprimento", "Desnível / disponível"],
           "h_q": ["Código", "Designação", "Unid.", "Quantidade", "P.U. s/IVA", "Total s/IVA"], "to_price": "a orçamentar",
           "price_note": "Preços: apenas a tabela de preços da empresa — nenhum valor estimado pela IA.",
           "h_chk": ["Domínio", "Estado", "Verificação", "Referência"], "elec": "Eletricidade", "plumb": "Canalização"},
}


def build_pdf(study: dict) -> bytes:
    _fonts()
    lang = study["lang"]
    T = L.get(lang, L["fr"])
    rules = rules_for(study["country"])
    S = _styles()
    buf = io.BytesIO()
    page = landscape(A3)
    W = page[0] - 30 * mm
    Hplan = page[1] - 62 * mm
    proj = (study.get("input") or {}).get("project") or {}

    def on_page(c, doc):
        c.saveState()
        c.setFillColor(colors.HexColor(R.NAVY))
        c.rect(0, page[1] - 14 * mm, page[0], 14 * mm, fill=1, stroke=0)
        c.setFillColor(colors.white)
        c.setFont(_FONT_B, 11)
        c.drawString(15 * mm, page[1] - 9 * mm, f"ConstruPilot — {tr(lang, 'title')}")
        c.setFont(_FONT, 9)
        c.drawRightString(page[0] - 15 * mm, page[1] - 9 * mm, f"{proj.get('name', '')}  ·  {study['norms']}  ·  {study['engine']}")
        c.setFillColor(colors.HexColor(R.BRAND))
        c.rect(0, page[1] - 15 * mm, page[0], 1 * mm, fill=1, stroke=0)
        c.setFillColor(colors.HexColor("#9A3412"))
        c.setFont(_FONT_B, 8)
        c.drawString(15 * mm, 8 * mm, "⚠ " + study["disclaimer"])
        c.setFillColor(colors.HexColor("#666666"))
        c.setFont(_FONT, 8)
        c.drawRightString(page[0] - 15 * mm, 8 * mm, f"{doc.page}")
        c.restoreState()

    doc = SimpleDocTemplate(buf, pagesize=page, leftMargin=15 * mm, rightMargin=15 * mm,
                            topMargin=20 * mm, bottomMargin=15 * mm, title=tr(lang, "title"),
                            author="ConstruPilot")
    story = []
    # --- synthèse ------------------------------------------------------------------------
    sm = study["summary"]
    story += [Paragraph(tr(lang, "title"), S["h1"]), Spacer(1, 3 * mm),
              Paragraph(f"{proj.get('name', '')} — {proj.get('client', '')}", S["h2"]),
              Paragraph(f"{tr(lang, 'rules')} : {study['norms']}  ·  {proj.get('source', '')}", S["p"]),
              Spacer(1, 4 * mm), Paragraph("⚠ " + study["disclaimer"], S["warn"]), Spacer(1, 6 * mm)]
    status_lbl = tr(lang, f"status.{sm['status']}")
    rows = [[tr(lang, "summary"), ""],
            [T["status"], f"{status_lbl} — " + T["errs"].format(e=sm["errors"], w=sm["warnings"])],
            [T["surface"], f"{sm['habitable_m2']} m²"],
            [T["points"], str(sm["points"])],
            [tr(lang, "circuits"), f"{sm['circuits']} circuits · {sm['rcds']} × 30 mA · {T['board']} "
                                   f"{study['electrical']['panel']['rows_13']} × 13 modules"],
            [T["fixtures"], str(sm["fixtures"])],
            [T["cables"], " · ".join(f"{k.replace('.', ',')} mm² : {v} m" for k, v in study["electrical"]["cables"]["by_section_m"].items())]]
    story.append(_table(rows, [70 * mm, W - 70 * mm], font_size=9))
    story.append(Spacer(1, 5 * mm))
    story.append(Paragraph(tr(lang, "assumptions"), S["h2"]))
    o = study["options"]
    hyp = [T["hyp_route"].format(r=o["route"], p=int(o["cable_slack"] * 100)),
           T["hyp_ecs"].format(h=o["water_heater"]),
           T["hyp_depth"].format(a=o["floor_drain_depth_m"], b=o["slab_drain_depth_m"]),
           T["hyp_auto"], T["hyp_price"]]
    for h in hyp:
        story.append(Paragraph("• " + h, S["p"]))
    # --- plans ---------------------------------------------------------------------------
    for lv in study["levels"]:
        story += [PageBreak(), Paragraph(f"{tr(lang, 'elec_plan')} — {lv['name']}", S["h2"]), Spacer(1, 2 * mm),
                  SceneBox(R.elec_scene(study, lv["id"]), W, Hplan, R.legend_elec(lang))]
    for lv in study["levels"]:
        story += [PageBreak(), Paragraph(f"{tr(lang, 'plumb_plan')} — {lv['name']}", S["h2"]), Spacer(1, 2 * mm),
                  SceneBox(R.plumb_scene(study, lv["id"], rules), W, Hplan, R.legend_plumb(lang))]
    story += [PageBreak(), Paragraph(tr(lang, "unifilar"), S["h2"]), Spacer(1, 2 * mm),
              SceneBox(R.unifilar_scene(study), W, Hplan * 0.75)]
    # --- circuits ------------------------------------------------------------------------
    story += [PageBreak(), Paragraph(tr(lang, "circuits"), S["h2"]), Spacer(1, 2 * mm)]
    rows = [T["h_circ"]]
    for c in study["electrical"]["circuits"]:
        rows.append([c["id"], Paragraph(c["label"], S["small"]),
                     f'{str(c["section_mm2"]).replace(".", ",")} mm²', f'{c["breaker_a"]} A', c.get("rcd_id", ""),
                     str(len(c["points"])), f'{c["length_m"]} m'])
    story.append(_table(rows, [22 * mm, W - 162 * mm, 25 * mm, 25 * mm, 25 * mm, 20 * mm, 45 * mm]))
    pl = study["plumbing"]
    story += [Spacer(1, 6 * mm), Paragraph(T["supplies"], S["h2"])]
    rows = [T["h_sup"]]
    for s in pl["supplies"]:
        rows.append([s["id"], s["net"], s["fixture"], f'Ø{s["pipe_ext_mm"]} ({s["pipe_int_mm"]} int.)',
                     f'{s["q_ls"]} l/s', f'{s["velocity_ms"]} m/s', f'{s["length_m"]} m'])
    for s in pl["risers"]:
        rows.append([s["id"], s["net"], tr(lang, "riser"), f'Ø{s["pipe_ext_mm"]}', f'{s["q_probable_ls"]} l/s',
                     f'{s["velocity_ms"]} m/s', f'{s["length_m"]} m'])
    if pl.get("main"):
        m = pl["main"]
        rows.append(["AEP", "EF", T["main"], f'Ø{m["pipe_ext_mm"]}', f'{m["q_probable_ls"]} l/s',
                     f'{m["velocity_ms"]} m/s', f'{m.get("length_in_building_m") or "—"} m'])
    story.append(_table(rows, [22 * mm, 20 * mm, W - 192 * mm, 45 * mm, 30 * mm, 30 * mm, 45 * mm]))
    story += [Spacer(1, 6 * mm), Paragraph(T["drains"], S["h2"])]
    rows = [T["h_drn"]]
    for d in pl["drains"]:
        rows.append([d["id"], d["net"], d["fixture"], d["to"], f'{d["diameter_mm"]}', f'{round(d["slope"] * 100, 1)} %',
                     f'{d["length_m"]} m', f'{d["drop_m"]} / {d["available_m"]} m'])
    if pl.get("collector"):
        c = pl["collector"]
        rows.append(["COL", "EU/EV", tr(lang, "collector"), tr(lang, "exit"), f'{c["diameter_mm"]}',
                     f'{round(c["slope"] * 100, 1)} %', f'{c["length_m"]} m', f'{c["drop_m"]} / {c["available_m"]} m'])
    for st in pl["stacks"]:
        rows.append([st["id"], "EU/EV", tr(lang, "stack"), st["lands_in_room"] or "—", f'{st["diameter_mm"]}', "—",
                     f'{st["height_m"]} m', st["ventilation"]])
    story.append(_table(rows, [22 * mm, 20 * mm, 50 * mm, 45 * mm, 20 * mm, 22 * mm, 30 * mm, W - 209 * mm]))
    # --- nomenclature --------------------------------------------------------------------
    story += [PageBreak(), Paragraph(tr(lang, "quantities"), S["h2"]), Spacer(1, 2 * mm)]
    rows = [T["h_q"]]
    for q in study["quantities"]:
        rows.append([q["code"], Paragraph(q["designation"], S["small"]), q["unit"], str(q["qty"]).replace(".", ","),
                     f'{q["unit_price"]:.2f} €' if q.get("unit_price") is not None else T["to_price"],
                     f'{q["total"]:.2f} €' if q.get("total") is not None else "—"])
    story.append(_table(rows, [42 * mm, W - 172 * mm, 18 * mm, 25 * mm, 42 * mm, 45 * mm]))
    story.append(Spacer(1, 3 * mm))
    story.append(Paragraph(T["price_note"], S["small"]))
    # --- contrôles -----------------------------------------------------------------------
    story += [PageBreak(), Paragraph(tr(lang, "checks"), S["h2"]), Spacer(1, 2 * mm)]
    color = {"ok": "#15803D", "warning": "#B45309", "error": "#B91C1C", "info": "#1D4ED8"}
    rows = [T["h_chk"]]
    order = {"error": 0, "warning": 1, "info": 2, "ok": 3}
    for ch in sorted(study["checks"], key=lambda c: (order[c["status"]], c["domain"])):
        rows.append([T[ch["domain"]],
                     Paragraph(f'<font color="{color[ch["status"]]}"><b>{tr(lang, "status." + ch["status"])}</b></font>', S["small"]),
                     Paragraph(ch["message"], S["small"]), Paragraph(ch.get("source") or "—", S["small"])])
    story.append(_table(rows, [30 * mm, 28 * mm, W - 158 * mm, 100 * mm]))
    doc.build(story, onFirstPage=on_page, onLaterPages=on_page)
    return buf.getvalue()
