"""Génération du PDF de MÉTRÉ ConstruPilot PLAN."""
from dataclasses import dataclass
from io import BytesIO
from datetime import datetime, timezone

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import (SimpleDocTemplate, Paragraph, Spacer, Table, LongTable, TableStyle,
                               PageBreak)
from reportlab.graphics.shapes import Drawing, Circle, String


# Iter 61 — icônes visuelles par catégorie pour la table des modèles.
# Chaque catégorie a une couleur + une lettre (initiale) affichée dans un cercle.
PRESET_KIND_ICONS = {
    "wall":       {"color": colors.HexColor("#0ea5e9"), "letter": "M", "label": "Parede", "full": "Parede"},
    "opening":    {"color": colors.HexColor("#a855f7"), "letter": "O", "label": "Aberto.", "full": "Vão"},
    "floor":      {"color": colors.HexColor("#f97316"), "letter": "S", "label": "Pavimento", "full": "Pavimento"},
    "ceiling":    {"color": colors.HexColor("#8b5cf6"), "letter": "P", "label": "Teto", "full": "Teto"},
    "paint":      {"color": colors.HexColor("#eab308"), "letter": "PEI", "label": "Peint.", "full": "Pintura"},
    "insulation": {"color": colors.HexColor("#22c55e"), "letter": "I", "label": "Isol.", "full": "Isolamento"},
    "counter":    {"color": colors.HexColor("#ec4899"), "letter": "#", "label": "Cptr.", "full": "Contagem"},
    "roof":       {"color": colors.HexColor("#3b82f6"), "letter": "T", "label": "Cobert.", "full": "Toiture"},
    "note":       {"color": colors.HexColor("#64748b"), "letter": "N", "label": "Nota", "full": "Nota"},
    "other":      {"color": colors.HexColor("#64748b"), "letter": "?", "label": "Outro", "full": "Outro"},
}


def _preset_icon_drawing(kind: str) -> Drawing:
    """Retourne un petit dessin (cercle coloré + initiale blanche) pour une catégorie
    de modèle — remplace la colonne 'Type' texte par une pastille visuelle."""
    icon = PRESET_KIND_ICONS.get(kind, PRESET_KIND_ICONS["other"])
    size = 14
    d = Drawing(size, size)
    d.add(Circle(size / 2, size / 2, size / 2 - 0.5,
                 fillColor=icon["color"], strokeColor=colors.white, strokeWidth=0.5))
    # Lettre blanche centrée
    letter = icon["letter"]
    font_size = 7 if len(letter) > 1 else 8
    d.add(String(size / 2, size / 2 - 2.2, letter,
                 fillColor=colors.white,
                 fontName="Helvetica-Bold", fontSize=font_size, textAnchor="middle"))
    return d

ORANGE = colors.HexColor('#FF5A00')
GREEN_BRAND = colors.HexColor('#18A858')
DARK = colors.HexColor('#0A0D14')
GREY = colors.HexColor('#64748B')
LIGHT_GREY = colors.HexColor('#F1F5F9')


def _fmt(v, unit="", digits=2):
    if isinstance(v, (int, float)):
        fmt = f"{{:,.{digits}f}} {{}}".format(v, unit)
        return fmt.replace(",", " ").replace(".", ",").strip()
    return str(v)


def _styles() -> dict:
    ss = getSampleStyleSheet()
    return {
        "h1": ParagraphStyle("h1", parent=ss["Heading1"], textColor=DARK,
                              fontName="Helvetica-Bold", fontSize=22, leading=26,
                              spaceAfter=6),
        "h2": ParagraphStyle("h2", parent=ss["Heading2"], textColor=ORANGE,
                              fontName="Helvetica-Bold", fontSize=13, leading=16,
                              spaceBefore=14, spaceAfter=6),
        "kicker": ParagraphStyle("k", textColor=ORANGE, fontName="Helvetica-Bold",
                                  fontSize=9, letterSpacing=1.5, spaceAfter=2),
        "body": ParagraphStyle("body", parent=ss["BodyText"], fontSize=9,
                                leading=12, textColor=DARK),
        "muted": ParagraphStyle("mu", parent=ss["BodyText"], fontSize=8, leading=11,
                                 textColor=GREY),
    }


# ============ TAKEOFF PDF HELPERS ============
# Each helper appends to `story` (mutates in place) — keeps the main builder flat.

def _table(rows, col_widths, style_extras=None, repeat_rows=0, splittable=False):
    """Small helper: build a Table with default border style + optional extras.

    splittable=True → use a LongTable that can split an oversized row across pages
    (splitInRow) so a very long description cell never triggers a LayoutError.
    """
    if splittable:
        t = LongTable(rows, colWidths=col_widths, repeatRows=repeat_rows,
                      splitByRow=1, splitInRow=1)
    else:
        t = Table(rows, colWidths=col_widths,
                  repeatRows=repeat_rows) if repeat_rows else Table(rows, colWidths=col_widths)
    base_style = [
        ("BOX", (0, 0), (-1, -1), 0.4, GREY),
        ("INNERGRID", (0, 0), (-1, -1), 0.2, GREY),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]
    t.setStyle(TableStyle(base_style + (style_extras or [])))
    return t


def _decode_brand_logo(logo_b64_str: str, size_mm: float = 32):
    """Try to decode a b64 logo into a ReportLab Image; return None on failure."""
    from reportlab.platypus import Image as RLImage
    import base64 as b64lib
    from io import BytesIO as BIO
    try:
        logo_bytes = b64lib.b64decode(logo_b64_str.split(",")[-1])
        return RLImage(BIO(logo_bytes), width=size_mm * mm, height=size_mm * mm,
                       kind="proportional")
    except Exception:
        return None


def _story_header_branding(story: list, branding: dict | None, S: dict) -> None:
    """Section 1 — logo + photo de profil + company + contact line + certifications."""
    if not branding or not (branding.get("company_name") or branding.get("logo_b64")
                            or branding.get("profile_photo_b64")
                            or branding.get("verified")
                            or branding.get("certifications")):
        return
    logo_cell = _decode_brand_logo(branding["logo_b64"]) if branding.get("logo_b64") else None
    photo_cell = (_decode_brand_logo(branding["profile_photo_b64"], size_mm=18)
                  if branding.get("profile_photo_b64") else None)
    info_lines = []
    if branding.get("company_name"):
        info_lines.append(Paragraph(f"<b>{branding['company_name']}</b>", S["body"]))
    if branding.get("verified"):
        info_lines.append(Paragraph(
            "<font color=\"#3F7D54\"><b>&#10004; Profissional verificado</b></font> <font color=\"#64748B\">— identidade e seguro de responsabilidade civil controlados pelo ConstruPilot</font>",
            S["muted"]))
    if branding.get("contact_line"):
        info_lines.append(Paragraph(branding["contact_line"], S["muted"]))
    _fisc = []
    if branding.get("nif"):
        _fisc.append(f"NIF {branding['nif']}")
    if not branding.get("nif") and branding.get("siret"):
        _fisc.append(f"NIF {branding['siret']}")
    if branding.get("vat"):
        _fisc.append(f"{('IVA' if branding.get('nif') else 'IVA')} {branding['vat']}")
    if branding.get("alvara"):
        _fisc.append(f"Alvará {branding['alvara']}")
    if _fisc:
        info_lines.append(Paragraph(" · ".join(_fisc), S["muted"]))
    certs = branding.get("certifications") or []
    if certs:
        _cert_labels = {"qualibat": "Qualibat", "rge": "RGE", "qualipac": "QualiPAC",
                        "qualifelec": "Qualifelec", "qualibois": "Qualibois"}
        parts = []
        for c in certs:
            lbl = _cert_labels.get(c.get("code"), (c.get("code") or "").upper())
            parts.append(lbl + (f" (n° {c['number']})" if c.get("number") else ""))
        info_lines.append(Paragraph(
            "<b>Certificações:</b> " + " · ".join(parts), S["muted"]))
    cells = [logo_cell or "", info_lines]
    widths = [35 * mm, None]
    if photo_cell:
        cells.append(photo_cell)
        widths = [35 * mm, None, 20 * mm]
    t = Table([cells], colWidths=widths)
    t.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
    ]))
    story.append(t)
    story.append(Spacer(1, 6))


def _story_takeoff_title(story: list, plan: dict, takeoff: dict, S: dict) -> None:
    """Section 2 — main title + subtitle line."""
    story.append(Paragraph("MEDIÇÃO CONSTRUPILOT", S["kicker"]))
    story.append(Paragraph(plan.get("filename") or "Planta", S["h1"]))
    date_str = datetime.now(timezone.utc).strftime("%d/%m/%Y")
    story.append(Paragraph(
        f"Plan ID <b>{plan.get('plan_id', '?')}</b> · {plan.get('page_count', 1)} page(s) · {takeoff.get('room_count', 0)} divisões · gerado em {date_str}", S["muted"]))
    story.append(Spacer(1, 10))


def _story_totals_global(story: list, totals: dict, S: dict) -> None:
    """Section 3 — global totals two-column table."""
    story.append(Paragraph("Totais globais", S["h2"]))
    data = [
        ["Pavimento", _fmt(totals.get("floor_m2", 0), "m²")],
        ["Tetos", _fmt(totals.get("ceiling_m2", 0), "m²")],
        ["Paredes brutas", _fmt(totals.get("walls_gross_m2", 0), "m²")],
        ["Paredes líquidas", _fmt(totals.get("walls_net_m2", 0), "m²")],
        ["Perímetro total", _fmt(totals.get("perimeter_m", 0), "m")],
    ]
    story.append(_table(data, [60 * mm, 40 * mm], style_extras=[
        ("BACKGROUND", (0, 0), (0, -1), LIGHT_GREY),
        ("TEXTCOLOR", (0, 0), (-1, -1), DARK),
        ("FONTNAME", (1, 0), (1, -1), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
    ]))


def _story_totals_per_level(story: list, levels: list, S: dict) -> None:
    """Section 4 — per-level breakdown (only if >1 level)."""
    if len(levels) <= 1:
        return
    story.append(Paragraph("Totais por piso", S["h2"]))
    rows = [["Piso", "Divisões", "Pavimento", "Paredes líquidas", "Perímetro"]]
    for lvl in levels:
        lt = lvl.get("totals", {})
        rows.append([lvl.get("level_label", "—"),
                     str(len(lvl.get("rooms", []))),
                     _fmt(lt.get("floor_m2", 0), "m²"),
                     _fmt(lt.get("walls_net_m2", 0), "m²"),
                     _fmt(lt.get("perimeter_m", 0), "m")])
    story.append(_table(rows, [35 * mm, 20 * mm, 30 * mm, 30 * mm, 30 * mm], style_extras=[
        ("BACKGROUND", (0, 0), (-1, 0), ORANGE),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 8.5),
        ("ALIGN", (1, 1), (-1, -1), "RIGHT"),
    ]))


def _story_rooms_detail(story: list, rooms: list, S: dict) -> None:
    """Section 5 — one-row-per-room detail table."""
    if not rooms:
        return
    story.append(Paragraph("Detalhe por divisão", S["h2"]))
    rows = [["Divisão", "Pavimento", "Perím.", "Paredes brutas", "Aberto.", "Paredes líquidas",
             "Volume", "Esp. pavimento", "H."]]
    for r in rooms:
        rows.append([r.get("name", "—"),
                     _fmt(r.get("surface_m2", 0), "m²"),
                     _fmt(r.get("perimeter_m", 0), "m"),
                     _fmt(r.get("wall_area_gross_m2", 0), "m²"),
                     _fmt(r.get("openings_area_m2", 0), "m²"),
                     _fmt(r.get("wall_area_net_m2", 0), "m²"),
                     _fmt(r.get("volume_m3",
                                round(r.get("surface_m2", 0) * r.get("ceiling_height_m", 2.5), 2)),
                          "m³"),
                     _fmt(r.get("floor_thickness_m", 0.15), "m", digits=2),
                     _fmt(r.get("ceiling_height_m", 2.5), "m")])
    story.append(_table(rows, [30 * mm, 18 * mm, 15 * mm, 20 * mm, 15 * mm,
                                20 * mm, 18 * mm, 18 * mm, 12 * mm],
                        style_extras=[
                            ("BACKGROUND", (0, 0), (-1, 0), DARK),
                            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                            ("FONTSIZE", (0, 0), (-1, -1), 7.5),
                            ("ALIGN", (1, 1), (-1, -1), "RIGHT"),
                            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, LIGHT_GREY]),
                        ], repeat_rows=1))
    # Optional openings sub-section : list all openings across rooms
    all_openings = []
    for r in rooms:
        for o in (r.get("openings") or []):
            all_openings.append([r.get("name", "—"),
                                  (o.get("kind") or "—").capitalize(),
                                  (o.get("label") or "—"),
                                  _fmt(o.get("width_m", 0), "m", digits=2),
                                  _fmt(o.get("height_m", 0), "m", digits=2),
                                  str(o.get("count", 1)),
                                  _fmt(o.get("area_m2", 0), "m²")])
    if all_openings:
        story.append(Spacer(1, 4 * mm))
        story.append(Paragraph("Vãos detalhados", S["h2"]))
        story.append(_table(
            [["Divisão", "Type", "Descrição", "Larg.", "Alt.", "Nb", "Superfície"]] + all_openings,
            [40 * mm, 22 * mm, 30 * mm, 18 * mm, 18 * mm, 12 * mm, 22 * mm],
            style_extras=[
                ("BACKGROUND", (0, 0), (-1, 0), DARK),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 8),
                ("ALIGN", (3, 1), (-1, -1), "RIGHT"),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, LIGHT_GREY]),
            ], repeat_rows=1))


def _material_row(section: str, m: dict) -> list[str] | None:
    """Map (section, material meta) to a printable table row, or None to skip."""
    if section == "floor":
        return [f"Sol ({m.get('material', '?')}) — área + perdas",
                _fmt(m.get("quantity_m2", 0), "m²")]
    if section == "paint":
        return [f"Tinta ({m.get('coats', 2)} demãos, margem {m.get('margin_pct', 15)}%)",
                _fmt(m.get("liters_recommended", 0), "L")]
    if section == "placo":
        return ["Placas de gesso cartonado (perdas 5%)", _fmt(m.get("plates", 0), "plaques")]
    if section == "skirting":
        return ["Rodapés (perímetro - portas + perdas)",
                _fmt(m.get("quantity_m", 0), "m")]
    return None


def _story_materials(story: list, materials: dict | None, S: dict) -> None:
    """Section 6 — materials breakdown (on a new page)."""
    if not materials:
        return
    story.append(PageBreak())
    story.append(Paragraph("Quantitativo de materiais", S["h2"]))
    rows = [["Material", "Quantidade"]]
    for section in ("floor", "paint", "placo", "skirting"):
        row = _material_row(section, materials.get(section) or {})
        if row and materials.get(section):
            rows.append(row)
    if len(rows) == 1:
        return
    story.append(_table(rows, [110 * mm, 45 * mm], style_extras=[
        ("BACKGROUND", (0, 0), (-1, 0), ORANGE),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("ALIGN", (1, 1), (-1, -1), "RIGHT"),
    ], repeat_rows=1))


def _story_footer(story: list, S: dict) -> None:
    """Section 7 — small legal disclaimer footer."""
    story.append(Spacer(1, 20))
    story.append(Paragraph(
        "Medição gerada pelo <b>ConstruPilot</b> — Estime. Compare. Construa. <br/>Documento de levantamento de quantidades (áreas, lineares, volumes) — sem preços.",
        S["muted"]))


def _story_room_presets(story: list, rooms: list, presets_by_id: dict, S: dict) -> None:
    """Section — Modèles d'ouvrages appliqués (Vague B, PDF export).

    Pour chaque pièce ayant un `preset_id`, affiche le modèle appliqué (nom, catégorie,
    prix unitaire, notes techniques) — visible pour le client sur le PDF.

    Iter 61 : la colonne 'Type' est remplacée par une icône colorée (Drawing ReportLab)
    permettant au client de repérer les catégories en un coup d'œil.
    """
    rooms_with_preset = [
        (r, presets_by_id[r["preset_id"]])
        for r in (rooms or [])
        if r.get("preset_id") and r["preset_id"] in presets_by_id
    ]
    if not rooms_with_preset:
        return
    story.append(Paragraph("Modelos de artigos aplicados", S["h2"]))
    rows = [["Divisão", "Modelo", "Cat.", "Un.", "Preço", "Notas"]]
    for r, p in rooms_with_preset:
        rows.append([
            r.get("name", "—"),
            p.get("name", "—"),
            _preset_icon_drawing(p.get("kind", "other")),
            p.get("unit", "u"),
            f"{p['price_per_unit']:.2f} €" if p.get("price_per_unit") is not None else "—",
            (p.get("notes") or "").strip()[:60] or "—",
        ])
    story.append(_table(rows, [30 * mm, 45 * mm, 14 * mm, 18 * mm, 20 * mm, 42 * mm],
                        style_extras=[
                            ("BACKGROUND", (0, 0), (-1, 0), DARK),
                            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                            ("FONTSIZE", (0, 0), (-1, -1), 8),
                            ("ALIGN", (2, 1), (2, -1), "CENTER"),  # icône centrée
                            ("ALIGN", (3, 1), (4, -1), "RIGHT"),
                            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, LIGHT_GREY]),
                        ], repeat_rows=1))
    story.append(Spacer(1, 2 * mm))
    _story_preset_legend(story, [p.get("kind", "other") for _, p in rooms_with_preset], S)
    story.append(Spacer(1, 4 * mm))


def _story_preset_legend(story: list, kinds: list[str], S: dict) -> None:
    """Iter63 — légende des pastilles de catégories sous la table des modèles.

    Affiche uniquement les catégories réellement présentes dans le tableau,
    par lignes de 6 paires (pastille + libellé complet) max.
    """
    used = set(kinds)
    seen = [k for k in PRESET_KIND_ICONS if k in used]
    if not seen:
        return
    pairs = []
    for k in seen:
        pairs.append(_preset_icon_drawing(k))
        pairs.append(Paragraph(PRESET_KIND_ICONS[k]["full"], S["muted"]))
    per_row = 12  # 6 paires (icône + libellé)
    rows = [pairs[i:i + per_row] for i in range(0, len(pairs), per_row)]
    rows[-1] += [""] * (per_row - len(rows[-1]))
    t = Table(rows, colWidths=[6 * mm, 22 * mm] * 6)
    t.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 1),
        ("RIGHTPADDING", (0, 0), (-1, -1), 3),
        ("TOPPADDING", (0, 0), (-1, -1), 1),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 1),
    ]))
    story.append(Paragraph("Legenda das categorias:", S["muted"]))
    story.append(t)


def _story_measurements(story: list, measurements: list, S: dict) -> None:
    """Iter66 — mesures ad-hoc enregistrées (trace imprimable avec libellés)."""
    if not measurements:
        return
    story.append(Paragraph("Medições guardadas", S["h2"]))
    kind_fr = {"distance": "Distância", "polyline": "Polilinha", "polygon": "Polygone"}
    rows = [["Descrição", "Type", "Página", "Valor", "Criada em"]]
    for m in measurements:
        if m.get("kind") == "polygon":
            value = f"{_fmt(m.get('area_m2', 0), 'm²')}"
        else:
            value = _fmt(m.get("value_m") or m.get("length_m") or 0, "m")
        d = str(m.get("created_at") or "")[:10]
        created = f"{d[8:10]}/{d[5:7]}/{d[0:4]}" if len(d) == 10 else "—"
        rows.append([m.get("label") or "—",
                     kind_fr.get(m.get("kind"), m.get("kind") or "—"),
                     str((m.get("page_index") or 0) + 1),
                     value, created])
    story.append(_table(rows, [58 * mm, 25 * mm, 14 * mm, 38 * mm, 25 * mm],
                        style_extras=[
                            ("BACKGROUND", (0, 0), (-1, 0), DARK),
                            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                            ("FONTSIZE", (0, 0), (-1, -1), 8),
                            ("ALIGN", (2, 1), (3, -1), "RIGHT"),
                            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, LIGHT_GREY]),
                        ], repeat_rows=1))
    story.append(Spacer(1, 4 * mm))


def build_takeoff_pdf(plan: dict, takeoff: dict, materials: dict | None = None,
                       branding: dict | None = None,
                       presets_by_id: dict | None = None,
                       measurements: list | None = None) -> bytes:
    """Rend un PDF de métré à partir d'un plan (rooms + totals + levels).

    `branding` optionnel : {"company_name": str, "contact_line": str, "logo_b64": str}
    `presets_by_id` optionnel : dict{preset_id: preset_doc} — si fourni, une section
        "Modèles d'ouvrages appliqués" est ajoutée pour montrer au client les specs
        techniques des matériaux choisis par pièce.

    Complexité maîtrisée : chaque section est déléguée à un helper `_story_*`.
    """
    buf = BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4,
                            leftMargin=18 * mm, rightMargin=18 * mm,
                            topMargin=18 * mm, bottomMargin=18 * mm)
    S = _styles()
    story: list = []

    _story_header_branding(story, branding, S)
    _story_takeoff_title(story, plan, takeoff, S)
    _story_totals_global(story, takeoff.get("totals", {}), S)
    _story_totals_per_level(story, takeoff.get("levels", []), S)
    _story_rooms_detail(story, takeoff.get("rooms", []), S)
    _story_room_presets(story, takeoff.get("rooms", []), presets_by_id or {}, S)
    _story_measurements(story, measurements or [], S)
    _story_materials(story, materials, S)
    _story_footer(story, S)

    doc.build(story)
    return buf.getvalue()


# ============ RAPPORT ÉCARTS SURFACES (iter63) ============

ECARTS_METHOD_LABELS = {
    "auto_pdf_scale": "escala do PDF", "two_points": "2 pontos",
    "known_dimension": "cota conhecida", "auto_cotes": "auto (cotes IA)",
    "reconcile_surfaces": "reajustada (áreas escritas)", "ai_scale_text": "escala escrita",
}
GREEN = colors.HexColor("#16a34a")
AMBER = colors.HexColor("#d97706")


def _ecarts_title(story: list, plan: dict, page_index: int, S: dict) -> None:
    story.append(Paragraph("RELATÓRIO DE CONTROLO DAS ÁREAS", S["kicker"]))
    story.append(Paragraph(plan.get("filename") or "Planta", S["h1"]))
    date_str = datetime.now(timezone.utc).strftime("%d/%m/%Y")
    story.append(Paragraph(
        f"Plan ID <b>{plan.get('plan_id', '?')}</b> · page {page_index + 1} · gerado em {date_str} — comparação das áreas medidas digitalmente com as áreas escritas na planta.",
        S["muted"]))
    story.append(Spacer(1, 10))


def _ecarts_calibration(story: list, calibration: dict | None, S: dict) -> None:
    story.append(Paragraph("Calibração utilizada", S["h2"]))
    if not calibration:
        story.append(Paragraph("Página não calibrada — calibre a página para medições fiáveis.",
                               S["muted"]))
        return
    method = ECARTS_METHOD_LABELS.get(calibration.get("method"),
                                      calibration.get("method") or "—")
    rows = [["Método", method],
            ["Escala", _fmt(calibration.get("pixels_per_meter", 0), "px/m")]]
    if calibration.get("samples_used"):
        rows.append(["Cotas utilizadas",
                     f"{calibration['samples_used']} (dispersion ±{calibration.get('spread_pct', 0)} %)"])
    if calibration.get("confidence") is not None:
        rows.append(["Confiança", f"{int(round(calibration['confidence'] * 100))} %"])
    story.append(_table(rows, [60 * mm, 60 * mm], style_extras=[
        ("BACKGROUND", (0, 0), (0, -1), LIGHT_GREY),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
    ]))


def _ecarts_table(story: list, matches: list[dict], unmatched: list[dict], S: dict) -> None:
    story.append(Paragraph("Diferenças por divisão", S["h2"]))
    rows = [["Divisão", "Medida", "Escrita (planta)", "Desvio", "Estado"]]
    row_styles = []
    for i, m in enumerate(matches, start=1):
        delta = m.get("delta_pct") or 0
        ok = abs(delta) <= 5.0
        rows.append([m.get("room_name") or "—",
                     _fmt(m.get("measured_m2", 0), "m²"),
                     _fmt(m.get("written_m2", 0), "m²"),
                     f"{'+' if delta > 0 else ''}{delta} %",
                     "Conforme" if ok else "Desvio"])
        row_styles.append(("TEXTCOLOR", (3, i), (4, i), GREEN if ok else AMBER))
        row_styles.append(("FONTNAME", (4, i), (4, i), "Helvetica-Bold"))
    for j, r in enumerate(unmatched, start=len(matches) + 1):
        rows.append([r.get("name") or "—", _fmt(r.get("surface_m2", 0), "m²"),
                     "—", "—", "Sem referência"])
        row_styles.append(("TEXTCOLOR", (2, j), (4, j), GREY))
    story.append(_table(rows, [45 * mm, 28 * mm, 30 * mm, 22 * mm, 30 * mm], style_extras=[
        ("BACKGROUND", (0, 0), (-1, 0), DARK),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 8.5),
        ("ALIGN", (1, 1), (3, -1), "RIGHT"),
        ("ALIGN", (4, 1), (4, -1), "CENTER"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, LIGHT_GREY]),
    ] + row_styles, repeat_rows=1))


def _ecarts_summary(story: list, matches: list[dict], unmatched: list[dict], S: dict) -> None:
    story.append(Spacer(1, 10))
    story.append(Paragraph("Síntese", S["h2"]))
    deltas = sorted(abs(m.get("delta_pct") or 0) for m in matches)
    conformes = sum(1 for d in deltas if d <= 5.0)
    ecarts = len(deltas) - conformes
    rows = [["Divisões conformes (diferença ≤ 5 %)", str(conformes)],
            ["Divisões com diferença (> 5 %)", str(ecarts)],
            ["Divisões sem área escrita", str(len(unmatched))]]
    if deltas:
        n = len(deltas)
        med = deltas[n // 2] if n % 2 else (deltas[n // 2 - 1] + deltas[n // 2]) / 2
        rows.append(["Diferença mediana absoluta", f"{round(med, 1)} %"])
    story.append(_table(rows, [90 * mm, 45 * mm], style_extras=[
        ("BACKGROUND", (0, 0), (0, -1), LIGHT_GREY),
        ("FONTNAME", (1, 0), (1, -1), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("ALIGN", (1, 0), (1, -1), "RIGHT"),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
    ]))
    story.append(Spacer(1, 8))
    if matches and ecarts == 0:
        verdict = ParagraphStyle("v_ok", fontName="Helvetica-Bold", fontSize=10,
                                 textColor=GREEN, leading=13)
        story.append(Paragraph(
            "Todas as áreas medidas estão conformes com as áreas escritas na planta (tolerância 5 %).", verdict))
    elif ecarts:
        verdict = ParagraphStyle("v_ko", fontName="Helvetica-Bold", fontSize=10,
                                 textColor=AMBER, leading=13)
        story.append(Paragraph(
            f'{ecarts} divisão(ões) apresentam uma diferença superior a 5 % — utilize «Reajustar a escala» no ConstruPilot PLANTA ou verifique o traçado dessas divisões.', verdict))


def build_ecarts_pdf(plan: dict, calibration: dict | None, matches: list[dict],
                     unmatched: list[dict], branding: dict | None = None,
                     page_index: int = 0) -> bytes:
    """Rapport PDF des écarts surfaces mesurées ↔ surfaces écrites (iter63).

    Document de contrôle qualité à joindre au métré pour rassurer le client :
    calibration utilisée, écart par pièce, synthèse et verdict.
    """
    buf = BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4,
                            leftMargin=18 * mm, rightMargin=18 * mm,
                            topMargin=18 * mm, bottomMargin=18 * mm)
    S = _styles()
    story: list = []

    _story_header_branding(story, branding, S)
    _ecarts_title(story, plan, page_index, S)
    _ecarts_calibration(story, calibration, S)
    _ecarts_table(story, matches, unmatched, S)
    _ecarts_summary(story, matches, unmatched, S)
    story.append(Spacer(1, 16))
    story.append(Paragraph(
        "Relatório gerado pelo <b>ConstruPilot</b> — as áreas «escritas» são lidas automaticamente na planta pela IA; as áreas «medidas» vêm da medição digital calibrada. Documento de controlo indicativo.", S["muted"]))

    doc.build(story)
    return buf.getvalue()


# ============ DEVIS (Full quote PDF) ============

def _story_quote_title(story: list, quote: dict, S: dict) -> None:
    """Devis title + subtitle line."""
    story.append(Paragraph("ORÇAMENTO ESTIMATIVO CONSTRUPILOT", S["kicker"]))
    story.append(Paragraph(quote.get("filename") or "Orçamento de obras", S["h1"]))
    date_str = datetime.now(timezone.utc).strftime("%d/%m/%Y")
    finish_label = {"eco": "Eco", "std": "Standard", "premium": "Premium"}.get(
        quote.get("finish", "std"), "Standard")
    story.append(Paragraph(
        f"Plan <b>{quote.get('plan_id', '?')}</b> · Gama <b>{finish_label}</b> · Sol : <b>{quote.get('floor_material', '').capitalize()}</b> · gerado em {date_str}",
        S["muted"]))
    story.append(Spacer(1, 10))


def _story_quote_surfaces(story: list, totals: dict, S: dict) -> None:
    """Surfaces mesurées section."""
    story.append(Paragraph("Áreas medidas", S["h2"]))
    surf_data = [
        ["Pavimento", _fmt(totals.get("floor_m2", 0), "m²")],
        ["Tetos", _fmt(totals.get("ceiling_m2", 0), "m²")],
        ["Paredes líquidas", _fmt(totals.get("walls_net_m2", 0), "m²")],
        ["Perímetro", _fmt(totals.get("perimeter_m", 0), "m")],
    ]
    story.append(_table(surf_data, [60 * mm, 40 * mm], style_extras=[
        ("BACKGROUND", (0, 0), (0, -1), LIGHT_GREY),
        ("FONTNAME", (1, 0), (1, -1), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
    ]))


def _story_quote_line_items(story: list, line_items: list, S: dict) -> None:
    """Detail table (one row per lot)."""
    story.append(Paragraph("Detalhe dos artigos", S["h2"]))
    rows = [["Designação", "Qtd.", "Unit.", "Materiais", "M.O.", "Total s/ IVA"]]
    for li in line_items:
        rows.append([
            li["name"], _fmt(li["quantity"]), li["unit"],
            _fmt(li["material_total"], "€"),
            _fmt(li["labour_total"], "€"),
            _fmt(li["total"], "€"),
        ])
    story.append(_table(rows,
        [70 * mm, 18 * mm, 14 * mm, 25 * mm, 22 * mm, 25 * mm],
        style_extras=[
            ("BACKGROUND", (0, 0), (-1, 0), DARK),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 8.5),
            ("ALIGN", (1, 1), (-1, -1), "RIGHT"),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, LIGHT_GREY]),
        ], repeat_rows=1))


def _story_quote_recap(story: list, quote: dict, S: dict) -> None:
    """Recap : sous-totaux, TVA, total TTC."""
    story.append(Spacer(1, 12))
    story.append(Paragraph("Resumo", S["h2"]))
    tva_pct = int(round(quote.get("tva_rate", 0.06) * 100))
    tot_rows = [
        ["Subtotal de materiais", _fmt(quote.get("subtotal_material", 0), "€")],
        ["Subtotal de mão de obra", _fmt(quote.get("subtotal_labour", 0), "€")],
        ["Subtotal s/ IVA", _fmt(quote.get("subtotal_ht", 0), "€")],
        [f'IVA {tva_pct} %', _fmt(quote.get("tva", 0), "€")],
        ["TOTAL C/ IVA", _fmt(quote.get("total_ttc", 0), "€")],
    ]
    story.append(_table(tot_rows, [110 * mm, 45 * mm], style_extras=[
        ("BACKGROUND", (0, 0), (0, -1), LIGHT_GREY),
        ("BACKGROUND", (0, -1), (-1, -1), ORANGE),
        ("TEXTCOLOR", (0, -1), (-1, -1), colors.white),
        ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
        ("FONTNAME", (1, 0), (1, -1), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9.5),
        ("FONTSIZE", (0, -1), (-1, -1), 12),
        ("ALIGN", (1, 0), (1, -1), "RIGHT"),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))


def _decode_signature_image(sig_b64: str, width_mm: float = 60, height_mm: float = 25):
    """Return an RLImage or empty string if decoding fails."""
    from reportlab.platypus import Image as RLImage
    from io import BytesIO as BIO
    import base64 as b64lib
    try:
        sig_bytes = b64lib.b64decode(sig_b64)
        return RLImage(BIO(sig_bytes), width=width_mm * mm, height=height_mm * mm,
                       kind="proportional")
    except Exception:
        return ""


def _story_quote_signature(story: list, signature: dict | None, S: dict) -> None:
    """Optional Bon-pour-accord signature block."""
    if not signature or not signature.get("b64"):
        return
    story.append(Spacer(1, 18))
    story.append(Paragraph("Aceito — Assinatura do cliente", S["h2"]))
    sig_img = _decode_signature_image(signature["b64"])
    signed_date = (signature.get("at") or "")[:10]
    info = [
        Paragraph(f"<b>Signatário:</b> {signature.get('name') or ''}", S["body"]),
        Paragraph(f"<b>Email :</b> {signature.get('client_email') or ''}", S["body"]),
        Paragraph(f'<b>Assinado em:</b> {signed_date}', S["body"]),
    ]
    sig_table = Table([[sig_img, info]], colWidths=[70 * mm, None])
    sig_table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("BOX", (0, 0), (-1, -1), 0.6, ORANGE),
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#FFF7EC")),
        ("TOPPADDING", (0, 0), (-1, -1), 10),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
        ("LEFTPADDING", (0, 0), (-1, -1), 12),
        ("RIGHTPADDING", (0, 0), (-1, -1), 12),
    ]))
    story.append(sig_table)


def _story_quote_footer(story: list, S: dict) -> None:
    story.append(Spacer(1, 18))
    story.append(Paragraph(
        "Orçamento <b>estimativo</b> gerado pelo ConstruPilot a partir da sua planta medida. Preços médios Portugal 2026 (base de referência + mão de obra). IVA a 6 % aplicável nas empreitadas de reabilitação de habitação (verba 2.27 CIVA), 23 % nos restantes casos. Este documento não constitui um orçamento contratual: peça vários orçamentos a profissionais para comparar.", S["muted"]))


def _story_quote_reviews(story: list, reviews: dict | None, S: dict) -> None:
    """Bloc « Avis clients » — note moyenne + jusqu'à 3 commentaires publiés."""
    if not reviews or not reviews.get("count"):
        return
    story.append(Spacer(1, 16))
    avg = reviews.get("average", 0)
    story.append(Paragraph(
        f"Opiniões de clientes — classificação média {avg}/5 em {reviews.get('count')} opiniões verificadas",
        S["h2"]))
    for it in (reviews.get("items") or [])[:3]:
        comment = (it.get("comment") or "").strip()
        if not comment:
            continue
        story.append(Paragraph(
            f"<b>{it.get('rating')}/5</b> — « {comment} » <i>({it.get('author_name') or 'Cliente'})</i>", S["body"]))
        story.append(Spacer(1, 4))


def build_quote_pdf(quote: dict, branding: dict | None = None,
                    signature: dict | None = None,
                    reviews: dict | None = None) -> bytes:
    """Rend un PDF Devis à partir d'un quote (line_items + totaux).

    Complexité maîtrisée : chaque section est déléguée à un helper `_story_quote_*`.
    """
    buf = BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4,
                             leftMargin=18 * mm, rightMargin=18 * mm,
                             topMargin=18 * mm, bottomMargin=18 * mm)
    S = _styles()
    story: list = []

    _story_header_branding(story, branding, S)
    _story_quote_title(story, quote, S)
    _story_quote_surfaces(story, quote.get("totals", {}), S)
    _story_quote_line_items(story, quote.get("line_items", []), S)
    _story_quote_recap(story, quote, S)
    _story_quote_signature(story, signature, S)
    _story_quote_reviews(story, reviews, S)
    _story_quote_footer(story, S)

    doc.build(story)
    return buf.getvalue()


# ============ MULTI-PLAN PROJECT PDF ============

def _pq_title(story: list, project: dict, S: dict) -> None:
    story.append(Paragraph("ORÇAMENTO CONSOLIDADO DO PROJETO", S["kicker"]))
    story.append(Paragraph(project.get("project_name") or "Projeto ConstruPilot", S["h1"]))
    date_str = datetime.now(timezone.utc).strftime("%d/%m/%Y")
    finish_label = {"eco": "Eco", "std": "Standard",
                    "premium": "Premium"}.get(project.get("finish", "std"), "Standard")
    story.append(Paragraph(
        f"<b>{project.get('plan_count', 0)} plantas</b> · Gama <b>{finish_label}</b> · gerado em {date_str}", S["muted"]))
    story.append(Spacer(1, 12))


def _pq_totals(story: list, totals: dict, S: dict) -> None:
    story.append(Paragraph("Áreas totais do projeto", S["h2"]))
    data = [
        ["Pavimento total", _fmt(totals.get("floor_m2", 0), "m²")],
        ["Tetos total", _fmt(totals.get("ceiling_m2", 0), "m²")],
        ["Paredes líquidas total", _fmt(totals.get("walls_net_m2", 0), "m²")],
        ["Perímetro total", _fmt(totals.get("perimeter_m", 0), "m")],
    ]
    story.append(_table(data, [60 * mm, 40 * mm], style_extras=[
        ("BACKGROUND", (0, 0), (0, -1), LIGHT_GREY),
        ("FONTNAME", (1, 0), (1, -1), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
    ]))
    story.append(Spacer(1, 14))


def _pq_sub_quote(story: list, sq: dict, index: int, S: dict) -> None:
    """Render one sub-quote block (per-plan detail table)."""
    story.append(Paragraph(f"Planta {index} : {sq.get('filename', 'Sem nome')}", S["h2"]))
    story.append(Paragraph(
        f"Pavimento {sq['totals']['floor_m2']} m² · Paredes líquidas {sq['totals']['walls_net_m2']} m² · Perímetro {sq['totals']['perimeter_m']} m", S["muted"]))
    rows = [["Designação", "Qtd.", "Unit.", "Total s/ IVA"]]
    for li in sq.get("line_items", []):
        rows.append([li["name"], _fmt(li["quantity"]), li["unit"], _fmt(li["total"], "€")])
    rows.append(["", "", "TOTAL s/ IVA da planta", _fmt(sq.get("subtotal_ht", 0), "€")])
    story.append(_table(rows, [85 * mm, 20 * mm, 20 * mm, 30 * mm], style_extras=[
        ("BACKGROUND", (0, 0), (-1, 0), DARK),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTNAME", (2, -1), (-1, -1), "Helvetica-Bold"),
        ("BACKGROUND", (0, -1), (-1, -1), LIGHT_GREY),
        ("FONTSIZE", (0, 0), (-1, -1), 8.5),
        ("ALIGN", (1, 1), (-1, -1), "RIGHT"),
    ], repeat_rows=1))
    story.append(Spacer(1, 10))


def _pq_recap(story: list, project: dict, S: dict) -> None:
    story.append(Spacer(1, 8))
    story.append(Paragraph("Resumo do projeto", S["h2"]))
    tva_pct = int(round(project.get("tva_rate", 0.06) * 100))
    rows = [
        ["Subtotal de materiais", _fmt(project.get("subtotal_material", 0), "€")],
        ["Subtotal de mão de obra", _fmt(project.get("subtotal_labour", 0), "€")],
        ["Subtotal s/ IVA", _fmt(project.get("subtotal_ht", 0), "€")],
        [f'IVA {tva_pct} %', _fmt(project.get("tva", 0), "€")],
        ["TOTAL DO PROJETO c/ IVA", _fmt(project.get("total_ttc", 0), "€")],
    ]
    story.append(_table(rows, [110 * mm, 45 * mm], style_extras=[
        ("BACKGROUND", (0, 0), (0, -1), LIGHT_GREY),
        ("BACKGROUND", (0, -1), (-1, -1), ORANGE),
        ("TEXTCOLOR", (0, -1), (-1, -1), colors.white),
        ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
        ("FONTNAME", (1, 0), (1, -1), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9.5),
        ("FONTSIZE", (0, -1), (-1, -1), 12),
        ("ALIGN", (1, 0), (1, -1), "RIGHT"),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))


def _pq_footer(story: list, S: dict) -> None:
    story.append(Spacer(1, 18))
    story.append(Paragraph(
        "Orçamento <b>consolidado do projeto</b> gerado pelo ConstruPilot a partir de várias plantas medidas. Preços médios Portugal 2026. IVA a 6 % aplicável nas empreitadas de reabilitação de habitação (verba 2.27 CIVA). Documento estimativo não contratual.", S["muted"]))


def build_project_quote_pdf(project: dict, branding: dict | None = None) -> bytes:
    """PDF Devis Projet consolidant plusieurs plans (multi-niveaux, extensions…).

    Complexité maîtrisée : 5 helpers `_pq_*` extraits — le corps de la fonction
    ne dépasse plus 20 lignes.
    """
    buf = BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4,
                             leftMargin=18 * mm, rightMargin=18 * mm,
                             topMargin=18 * mm, bottomMargin=18 * mm)
    S = _styles()
    story: list = []

    _story_header_branding(story, branding, S)
    _pq_title(story, project, S)
    _pq_totals(story, project.get("totals", {}), S)
    for i, sq in enumerate(project.get("sub_quotes", []), 1):
        _pq_sub_quote(story, sq, i, S)
    _pq_recap(story, project, S)
    _pq_footer(story, S)

    doc.build(story)
    return buf.getvalue()



# ============ PAGE DE GARDE (dossier de chiffrage pro) ============

def build_cover_story(branding: dict | None, project: dict, client: dict | None,
                      reference: str, S: dict) -> list:
    """Page de garde professionnelle : bandeau vert de marque (logo + société),
    titre « Dossier de chiffrage », nom du projet, bloc client et métadonnées.

    `project` = {"name", "levels_count", "total_ttc"} ; `client` = {"name",
    "company", "address", "city", "email", "phone"}. Retourne les flowables
    (terminés par un PageBreak) à préfixer au corps du rapport.
    """
    from reportlab.platypus import PageBreak
    story: list = []

    white_big = ParagraphStyle("cv_wb", fontName="Helvetica-Bold", fontSize=14,
                               textColor=colors.white, leading=17)
    white_small = ParagraphStyle("cv_ws", fontName="Helvetica", fontSize=8.5,
                                 textColor=colors.white, leading=12)
    label_style = ParagraphStyle("cv_lbl", fontName="Helvetica-Bold", fontSize=8,
                                 textColor=GREEN_BRAND, leading=12, spaceAfter=2)
    kicker_green = ParagraphStyle("cv_kick", fontName="Helvetica-Bold", fontSize=9,
                                  textColor=GREEN_BRAND, leading=12, spaceAfter=2)

    # --- Bandeau vert de marque : logo + identité société ---
    logo = (_decode_brand_logo(branding["logo_b64"], size_mm=20)
            if branding and branding.get("logo_b64") else "")
    comp_lines = []
    if branding:
        if branding.get("company_name"):
            comp_lines.append(Paragraph(branding["company_name"], white_big))
        addr = " ".join(x for x in [branding.get("address"),
                                     branding.get("postal_code"),
                                     branding.get("city")] if x)
        if addr:
            comp_lines.append(Paragraph(addr, white_small))
        if branding.get("contact_line"):
            comp_lines.append(Paragraph(branding["contact_line"], white_small))
        if branding.get("company_email"):
            comp_lines.append(Paragraph(branding["company_email"], white_small))
        fisc = []
        if branding.get("siret"):
            fisc.append("NIF " + str(branding["siret"]))
        if branding.get("vat"):
            fisc.append("IVA " + str(branding["vat"]))
        if fisc:
            comp_lines.append(Paragraph(" · ".join(fisc), white_small))
    if not comp_lines:
        comp_lines = [Paragraph("ConstruPilot", white_big)]
    banner = Table([[logo, comp_lines]], colWidths=[26 * mm, None])
    banner.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), GREEN_BRAND),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 14),
        ("RIGHTPADDING", (0, 0), (-1, -1), 14),
        ("TOPPADDING", (0, 0), (-1, -1), 14),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 14),
    ]))
    story.append(banner)
    if branding and branding.get("verified"):
        story.append(Spacer(1, 4))
        story.append(Paragraph(
            "<font color=\"#3F7D54\"><b>&#10004; Profissional verificado</b></font> <font color=\"#64748B\">— identidade e seguro controlados pelo ConstruPilot</font>",
            S["muted"]))
    story.append(Spacer(1, 34 * mm))

    # --- Titre principal ---
    story.append(Paragraph("PROCESSO DE ORÇAMENTAÇÃO", kicker_green))
    story.append(Paragraph(project.get("name") or "Projeto", ParagraphStyle(
        "cv_title", fontName="Helvetica-Bold", fontSize=28, textColor=DARK,
        leading=32, spaceAfter=6)))
    story.append(Paragraph(
        f"Projeto multinível · {project.get('levels_count', 0)} piso(s)", S["muted"]))

    ttc = project.get("total_ttc")
    if ttc:
        story.append(Spacer(1, 10 * mm))
        amount_box = Table([[
            [Paragraph("MONTANTE ESTIMADO c/ IVA", ParagraphStyle(
                "cv_ttc_lbl", fontName="Helvetica-Bold", fontSize=8.5,
                textColor=colors.white, leading=11, spaceAfter=3)),
             Paragraph(_fmt(ttc, "€"), ParagraphStyle(
                "cv_ttc_val", fontName="Helvetica-Bold", fontSize=26,
                textColor=colors.white, leading=30))]
        ]], colWidths=[None])
        amount_box.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), DARK),
            ("LEFTPADDING", (0, 0), (-1, -1), 16),
            ("RIGHTPADDING", (0, 0), (-1, -1), 16),
            ("TOPPADDING", (0, 0), (-1, -1), 12),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 12),
        ]))
        story.append(amount_box)
    story.append(Spacer(1, 20 * mm))

    # --- Bloc client + métadonnées (2 colonnes) ---
    cli = client or {}
    client_cell = [Paragraph("CLIENTE", label_style)]
    cname = cli.get("name") or cli.get("company")
    if cname:
        client_cell.append(Paragraph(f"<b>{cname}</b>", S["body"]))
    if cli.get("company") and cli.get("name") and cli.get("company") != cli.get("name"):
        client_cell.append(Paragraph(cli["company"], S["body"]))
    for key in ("address", "city"):
        if cli.get(key):
            client_cell.append(Paragraph(cli[key], S["body"]))
    contact = " · ".join(x for x in [cli.get("email"), cli.get("phone")] if x)
    if contact:
        client_cell.append(Paragraph(contact, S["muted"]))
    if len(client_cell) == 1:
        client_cell.append(Paragraph("—", S["muted"]))

    date_str = datetime.now(timezone.utc).strftime("%d/%m/%Y")
    meta_cell = [
        Paragraph("REFERÊNCIA DO PROCESSO", label_style),
        Paragraph(f"<b>{reference}</b>", S["body"]),
        Spacer(1, 6),
        Paragraph("EMITIDO EM", label_style),
        Paragraph(date_str, S["body"]),
        Spacer(1, 6),
        Paragraph("VALIDADE", label_style),
        Paragraph("Orçamento estimativo válido 30 dias", S["body"]),
    ]
    info = Table([[client_cell, meta_cell]], colWidths=[None, 62 * mm])
    info.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("BOX", (0, 0), (-1, -1), 0.6, GREEN_BRAND),
        ("LINEAFTER", (0, 0), (0, -1), 0.4, LIGHT_GREY),
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#F1FBF4")),
        ("LEFTPADDING", (0, 0), (-1, -1), 14),
        ("RIGHTPADDING", (0, 0), (-1, -1), 14),
        ("TOPPADDING", (0, 0), (-1, -1), 14),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 14),
    ]))
    story.append(info)
    story.append(Spacer(1, 16 * mm))
    story.append(Paragraph(
        "Documento gerado pelo <b>ConstruPilot</b> — medição e orçamentação determinísticas. Estimativa indicativa que não constitui um orçamento contratual.", S["muted"]))
    story.append(PageBreak())
    return story


def make_logo_watermark(logo_b64: str | None, alpha: float = 0.12):
    """Retourne une fonction (canvas, doc) dessinant un filigrane du logo
    centré sur chaque page — ou None si pas de logo exploitable.
    alpha : opacité (0.12 = visible mais lisible sous le texte)."""
    if not logo_b64:
        return None
    try:
        import base64 as b64lib
        from reportlab.lib.utils import ImageReader
        from io import BytesIO as BIO
        raw = b64lib.b64decode(logo_b64.split(",")[-1])
        reader = ImageReader(BIO(raw))
        iw, ih = reader.getSize()
    except Exception:
        return None
    if not iw or not ih:
        return None
    ratio = ih / iw

    def _draw(canvas, doc):
        from reportlab.lib.pagesizes import A4
        pw, ph = A4
        w = 110 * mm
        h = w * ratio
        x = (pw - w) / 2
        y = (ph - h) / 2
        canvas.saveState()
        try:
            canvas.setFillAlpha(alpha)
            canvas.setStrokeAlpha(alpha)
        except Exception:
            pass
        canvas.drawImage(reader, x, y, width=w, height=h,
                         mask="auto", preserveAspectRatio=True)
        canvas.restoreState()

    return _draw


# ============ ATTESTATION TVA (Cerfa 1301-SD simplifié) ============

@dataclass
class TvaAttestationInput:
    """Input container for `build_tva_attestation_pdf` — groups the 8 fields
    the caller must provide, so the function signature stays short and typed."""
    client_name: str
    client_address: str
    work_address: str
    work_description: str
    company_name: str = ""
    company_address: str = ""
    branding: dict | None = None
    tva_rate: float = 0.06


def _tva_header_and_intro(story: list, tva_pct: int, S: dict) -> None:
    is_reduced = tva_pct in (10, 5, 55)  # 5.5 arrondi
    header_title = (f'DECLARAÇÃO — IVA À TAXA REDUZIDA ({tva_pct} %)'
                     if is_reduced else "DECLARAÇÃO DE OBRAS")
    story.append(Paragraph(header_title, S["kicker"]))
    story.append(Paragraph("Verba 2.27 da Lista I anexa ao Código do IVA", S["h1"]))
    story.append(Paragraph(
        "Declaração a entregar à empresa para beneficiar da taxa reduzida de IVA nas empreitadas de reabilitação de imóveis afetos à habitação.", S["muted"]))
    story.append(Spacer(1, 12))


def _tva_labelled_block(story: list, title: str, rows: list, S: dict) -> None:
    """Render a title + 2-col labelled table (client info / company info)."""
    story.append(Paragraph(title, S["h2"]))
    t = Table(rows, colWidths=[45 * mm, 120 * mm])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, -1), LIGHT_GREY),
        ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 10),
        ("BOX", (0, 0), (-1, -1), 0.4, GREY),
        ("INNERGRID", (0, 0), (-1, -1), 0.2, GREY),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
    ]))
    story.append(t)
    story.append(Spacer(1, 12))


def _tva_declarations(story: list, S: dict) -> None:
    story.append(Paragraph("Declara sob compromisso de honra que:", S["h2"]))
    story.append(Paragraph(
        "1. O imóvel onde são realizados os trabalhos está <b>afeto à habitação</b> (habitação própria permanente ou secundária).",
        S["body"]))
    story.append(Paragraph(
        "2. Os trabalhos constituem uma <b>empreitada de reabilitação</b> (beneficiação, remodelação, renovação, restauro, reparação ou conservação) do imóvel.",
        S["body"]))
    story.append(Paragraph(
        "3. O valor dos materiais incorporados não excede 20 % do valor global da prestação de serviços (se exceder, a taxa reduzida aplica-se apenas à mão de obra).",
        S["body"]))
    story.append(Spacer(1, 12))


def _tva_signature_and_footer(story: list, S: dict) -> None:
    story.append(Paragraph(
        "Feito em …………………………………………… a ……… / ……… / ………………",
        S["body"]))
    story.append(Spacer(1, 20))
    story.append(Paragraph("Assinatura do cliente (precedida de «Aceito»):",
                            S["body"]))
    story.append(Spacer(1, 40))
    sig_frame = Table([[""]], colWidths=[90 * mm], rowHeights=[30 * mm])
    sig_frame.setStyle(TableStyle([("BOX", (0, 0), (-1, -1), 0.6, GREY)]))
    story.append(sig_frame)
    story.append(Spacer(1, 12))
    story.append(Paragraph(
        "<b>Atenção</b>: qualquer declaração falsa responsabiliza o cliente. A Autoridade Tributária pode exigir o pagamento do complemento de IVA correspondente à diferença entre a taxa reduzida e a taxa normal. Conserve este documento durante 10 anos.", S["muted"]))


def _coalesce_tva_input(data, kw) -> "TvaAttestationInput":
    """Normalize legacy kwargs into a `TvaAttestationInput`."""
    if data is not None:
        return data
    return TvaAttestationInput(
        client_name=kw.get("client_name") or "",
        client_address=kw.get("client_address") or "",
        work_address=kw.get("work_address") or "",
        work_description=kw.get("work_description") or "",
        company_name=kw.get("company_name", ""),
        company_address=kw.get("company_address", ""),
        branding=kw.get("branding"),
        tva_rate=kw.get("tva_rate", 0.06),
    )


def build_tva_attestation_pdf(
    data: "TvaAttestationInput | None" = None,
    /,
    # Backwards-compat kwargs — legacy callers can still pass positional args.
    client_name: str | None = None,
    client_address: str | None = None,
    work_address: str | None = None,
    work_description: str | None = None,
    company_name: str = "",
    company_address: str = "",
    branding: dict | None = None,
    tva_rate: float = 0.06,
) -> bytes:
    """Attestation simplifiée du client (art. 279-0 bis CGI) : logement > 2 ans.

    Refactor iter53 : orchestration only — chaque section déléguée à un helper `_tva_*`.
    """
    data = _coalesce_tva_input(data, locals())
    buf = BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4,
                             leftMargin=20 * mm, rightMargin=20 * mm,
                             topMargin=20 * mm, bottomMargin=20 * mm)
    S = _styles()
    story: list = []
    tva_pct = int(round(data.tva_rate * 100))

    _tva_header_and_intro(story, tva_pct, S)
    _tva_labelled_block(story, "O(A) abaixo assinado(a)", [
        ["Nome / Apelido:", data.client_name or "………………………………………………"],
        ["Morada (cliente):", data.client_address or "………………………………………………"],
        ["Morada da obra:", data.work_address or "………………………………………………"],
    ], S)
    _tva_declarations(story, S)
    story.append(Paragraph("Natureza dos trabalhos:", S["h2"]))
    story.append(Paragraph(data.work_description or "………………………………………………", S["body"]))
    story.append(Spacer(1, 20))
    _tva_labelled_block(story, "Empresa que realiza os trabalhos:", [
        ["Denominação social:", data.company_name or "………………………………………………"],
        ["Morada:", data.company_address or "………………………………………………"],
    ], S)
    story.append(Spacer(1, 8))
    _tva_signature_and_footer(story, S)

    doc.build(story)
    return buf.getvalue()



# ============ RAPPORT COMPTABLE MENSUEL ============

_FR_MONTHS = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet",
              "août", "septembre", "octobre", "novembre", "décembre"]


def build_accounting_recap_pdf(period: str, rows: list[dict],
                               plan_names: dict | None = None,
                               branding: dict | None = None) -> bytes:
    """Rapport comptable mensuel (PDF) prêt à transmettre au comptable.

    period = "YYYY-MM". rows = liste de quote_sends du mois.
    """
    plan_names = plan_names or {}
    buf = BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=16 * mm, rightMargin=16 * mm,
                            topMargin=16 * mm, bottomMargin=16 * mm)
    S = _styles()
    story: list = []

    _story_header_branding(story, branding, S)
    year, month = period.split("-")
    month_label = _FR_MONTHS[int(month) - 1].capitalize()
    story.append(Paragraph("RELATÓRIO CONTABILÍSTICO MENSAL", S["kicker"]))
    story.append(Paragraph(f"{month_label} {year}", S["h1"]))
    story.append(Paragraph(
        "Resumo dos orçamentos enviados e assinados no período — documento a transmitir ao seu contabilista certificado.", S["muted"]))
    story.append(Spacer(1, 12))

    header = ["Data", "Cliente", "Documento", "c/ IVA (€)", "Estado", "Assinado a"]
    trows = [header]
    signed_ttc = 0.0
    sent_ttc = 0.0
    signed_n = 0
    for r in sorted(rows, key=lambda x: x.get("created_at") or ""):
        status = ("Assinado" if r.get("signed")
                  else "Em aberto" if r.get("opened") else "Enviado")
        ttc = r.get("total_ttc") or 0
        sent_ttc += ttc
        if r.get("signed"):
            signed_ttc += ttc
            signed_n += 1
        trows.append([
            (r.get("created_at") or "")[:10],
            (r.get("client_name") or r.get("client_email") or "")[:26],
            (plan_names.get(r.get("plan_id")) or r.get("plan_id") or "")[:22],
            _fmt(ttc, "€"),
            status,
            (r.get("signed_at") or "")[:10],
        ])
    if len(trows) == 1:
        trows.append(["—", "Nenhum orçamento no período", "", "", "", ""])
    story.append(_table(
        trows, [22 * mm, 40 * mm, 36 * mm, 24 * mm, 20 * mm, 22 * mm],
        style_extras=[
            ("BACKGROUND", (0, 0), (-1, 0), DARK),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 8),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, LIGHT_GREY]),
            ("ALIGN", (3, 1), (3, -1), "RIGHT"),
        ], repeat_rows=1))
    story.append(Spacer(1, 16))

    signed_ht = round(signed_ttc / 1.10, 2)
    signed_tva = round(signed_ttc - signed_ht, 2)
    story.append(Paragraph("Síntese contabilística", S["h2"]))
    tot_rows = [
        ["Orçamentos enviados (número)", str(len(rows))],
        ["Orçamentos assinados (número)", str(signed_n)],
        ["Volume de negócios assinado s/ IVA", _fmt(signed_ht, "€")],
        ["IVA 6 % liquidado", _fmt(signed_tva, "€")],
        ["Volume de negócios assinado c/ IVA", _fmt(signed_ttc, "€")],
        ["Pipeline c/ IVA (enviado não assinado)", _fmt(round(sent_ttc - signed_ttc, 2), "€")],
    ]
    story.append(_table(tot_rows, [110 * mm, 45 * mm], style_extras=[
        ("BACKGROUND", (0, 0), (0, -1), LIGHT_GREY),
        ("BACKGROUND", (0, 4), (-1, 4), ORANGE),
        ("TEXTCOLOR", (0, 4), (-1, 4), colors.white),
        ("FONTNAME", (0, 4), (-1, 4), "Helvetica-Bold"),
        ("FONTNAME", (1, 0), (1, -1), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9.5),
        ("ALIGN", (1, 0), (1, -1), "RIGHT"),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    story.append(Spacer(1, 16))
    story.append(Paragraph(
        "Documento gerado pelo ConstruPilot. O IVA apresentado pressupõe a taxa reduzida de 6 % (empreitadas de reabilitação de habitação, verba 2.27 CIVA). Verifique a taxa aplicável a cada obra com o seu contabilista certificado.", S["muted"]))

    doc.build(story)
    return buf.getvalue()
