"""PDF générique pour les documents pro : devis, factures, avoirs.

Lignes libres (désignation / qté / unité / PU HT / TVA), TVA multi-taux, acompte.
Réutilise les helpers de mise en page de pdf_takeoff.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from io import BytesIO
from xml.sax.saxutils import escape

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Image, PageBreak, Table, TableStyle

from engines.pdf_takeoff import (
    _styles, _table, _fmt, _story_quote_reviews, _decode_brand_logo,
    make_logo_watermark,
)
from engines.pdf_i18n import pdf_labels

DOC_LABELS = {"quote": "DEVIS", "invoice": "FACTURE", "credit_note": "AVOIR"}

# Couleur par défaut des documents commerciaux (vert). Le pro peut la changer
# dans « Ma page & mes documents » (champ accent_color) : toute la palette en dérive.
DEFAULT_DOC_COLOR = "#15803D"

# Modèles de mise en page proposés au pro (champ branding["doc_layout"]).
# Les 3 premiers : en-tête « ConstruPilot ». Les 3 suivants (kit CMRENOV) : en-tête « papier à
# lettre » (logo + identité à gauche, numéro/date du document à droite).
LAYOUTS = ("bandeau", "classique", "compact", "essentiel", "detaille", "signature")
LETTERHEAD = ("essentiel", "detaille", "signature")
DEFAULT_LAYOUT = "bandeau"


def _layout_of(branding: dict | None) -> str:
    lay = str((branding or {}).get("doc_layout") or "").strip().lower()
    return lay if lay in LAYOUTS else DEFAULT_LAYOUT


def _mix(hex_color: str, target: tuple[int, int, int], ratio: float) -> str:
    h = hex_color.lstrip("#")
    r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
    out = tuple(round(c + (t - c) * ratio) for c, t in zip((r, g, b), target))
    return "#%02X%02X%02X" % out


def _palette(branding: dict | None) -> dict:
    """Dérive titres / en-têtes / fonds / filets d'une seule couleur d'accent."""
    raw = str((branding or {}).get("accent_color") or "").strip()
    if len(raw) != 7 or not raw.startswith("#"):
        raw = DEFAULT_DOC_COLOR
    try:
        int(raw[1:], 16)
    except ValueError:
        raw = DEFAULT_DOC_COLOR
    black, white = (0, 0, 0), (255, 255, 255)
    return {
        "main": colors.HexColor(raw),
        "deep": colors.HexColor(_mix(raw, black, 0.45)),
        "head": colors.HexColor(_mix(raw, black, 0.22)),
        "soft": colors.HexColor(_mix(raw, white, 0.94)),
        "row": colors.HexColor(_mix(raw, white, 0.86)),
        "line": colors.HexColor(_mix(raw, white, 0.72)),
    }


def _doc_styles(base: dict, P: dict, layout: str = DEFAULT_LAYOUT) -> dict:
    """Styles du document : couleur du pro, tailles selon le modèle choisi."""
    S = dict(base)
    h1_size = {"bandeau": 15.5, "classique": 17, "compact": 13,
               "essentiel": 16, "detaille": 16, "signature": 18.5}[layout]
    for key, size, leading, color in (("h1", h1_size, h1_size + 3.5, P["deep"]), ("h2", 10.5, 13, P["main"])):
        st = base[key].clone(f"doc_{key}")
        st.fontSize, st.leading, st.textColor = size, leading, color
        st.spaceBefore = 10 if key == "h2" else 0
        st.spaceAfter = 4
        S[key] = st
    k = base["kicker"].clone("doc_kicker")
    k.textColor, k.fontSize = P["main"], 8
    S["kicker"] = k
    w = base["body"].clone("doc_banner")
    w.textColor, w.fontSize, w.leading = colors.white, 8.5, 11
    S["banner"] = w
    for src, name in (("body", "body_right"), ("muted", "muted_right")):
        st = base[src].clone(f"doc_{name}")
        st.alignment = 2  # TA_RIGHT
        S[name] = st
    wb = base["h2"].clone("doc_banner_title")
    wb.textColor, wb.fontSize, wb.leading, wb.spaceBefore, wb.spaceAfter = colors.white, 13, 15, 0, 1
    S["banner_title"] = wb
    # Grand libellé du document (DEVIS / FACTURE / AVOIR) aligné à droite pour l'en-tête papier à lettre.
    lab = base["h1"].clone("doc_label_right")
    lab.alignment, lab.fontSize, lab.leading, lab.textColor = 2, 20, 23, P["deep"]
    lab.spaceBefore = lab.spaceAfter = 0
    S["label_right"] = lab
    # Identité entreprise (colonne gauche de l'en-tête papier à lettre).
    idn = base["h2"].clone("doc_ident")
    idn.textColor, idn.fontSize, idn.leading, idn.spaceBefore, idn.spaceAfter = P["deep"], 12.5, 15, 0, 1
    S["ident"] = idn
    return S


def _compact_header_text(text: str, branding: dict | None) -> str:
    """Condense le bloc de coordonnées saisi par le pro et retire ce que l'en-tête affiche déjà."""
    b = branding or {}
    already = [str(b.get(k) or "").lower() for k in ("company_name", "siret", "vat", "nif")]
    already = [a for a in already if a]
    kept = []
    for raw in str(text).splitlines():
        line = raw.strip(" ·-")
        if not line:
            continue
        low = line.lower()
        # supprime les doublons de l'en-tête (nom de société, SIRET, TVA) et les fragments d'adresse
        if any(a and (a in low or low in a) for a in already):
            continue
        if low.replace(" ", "").isdigit() and len(low.replace(" ", "")) <= 5:  # code postal seul
            continue
        if low in ("france", "portugal"):
            continue
        kept.append(line)
    return " · ".join(kept)


def _header_classic(story: list, branding: dict | None, S: dict, P: dict) -> None:
    """Modèle « classique » : logo à gauche, identité à droite, filet de couleur. Sobre et neutre."""
    b = branding or {}
    logo = _decode_brand_logo(b["logo_b64"], size_mm=24) if b.get("logo_b64") else None
    right = []
    if b.get("company_name"):
        right.append(Paragraph(f"<b>{escape(b['company_name'])}</b>", S["body_right"]))
    if b.get("contact_line"):
        right.append(Paragraph(escape(b["contact_line"]), S["muted_right"]))
    fisc = _fiscal_parts(b)
    if fisc:
        right.append(Paragraph(escape(" · ".join(fisc)), S["muted_right"]))
    if not right and not logo:
        return
    row = [logo or "", right]
    story.append(_table([row], [34 * mm, 140 * mm], style_extras=[
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("ALIGN", (1, 0), (1, 0), "RIGHT"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("LINEBELOW", (0, 0), (-1, -1), 1.4, P["main"]),
    ]))
    story.append(Spacer(1, 10))


def _header_compact(story: list, branding: dict | None, S: dict, P: dict) -> None:
    """Modèle « compact » : une seule ligne dense, pour tenir le devis sur une page."""
    b = branding or {}
    parts = [x for x in [b.get("company_name"), b.get("contact_line")] if x]
    parts += _fiscal_parts(b)
    if not parts:
        return
    story.append(_table([[Paragraph(f"<b>{escape(parts[0])}</b> · " + escape(" · ".join(parts[1:])),
                                    S["muted"])]], [174 * mm], style_extras=[
        ("BACKGROUND", (0, 0), (-1, -1), P["soft"]),
        ("BOX", (0, 0), (-1, -1), 0.6, P["line"]),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    story.append(Spacer(1, 8))


def _fiscal_parts(b: dict) -> list[str]:
    # Le texte d'en-tête libre n'est plus rendu sur les documents : il faisait doublon avec le
    # bandeau (nom + coordonnées) et le pied de page (mentions légales). Seule l'identité fiscale reste.
    fisc = []
    if b.get("nif"):
        fisc.append(f"NIF {b['nif']}")
    elif b.get("siret"):
        fisc.append(f"SIRET {b['siret']}")
    if b.get("vat"):
        fisc.append(f"{'IVA' if b.get('nif') else 'TVA'} {b['vat']}")
    if b.get("alvara"):
        fisc.append(f"Alvará {b['alvara']}")
    return fisc


def _header_banner(story: list, branding: dict | None, S: dict, P: dict) -> None:
    """Modèle « bandeau » : bloc coloré pleine largeur, logo dans une pastille blanche."""
    b = branding or {}
    logo = _decode_brand_logo(b["logo_b64"], size_mm=20) if b.get("logo_b64") else None
    info = []
    if b.get("company_name"):
        info.append(Paragraph(escape(b["company_name"]), S["banner_title"]))
    if b.get("contact_line"):
        info.append(Paragraph(escape(b["contact_line"]), S["banner"]))
    fisc = _fiscal_parts(b)
    if fisc:
        info.append(Paragraph(escape(" · ".join(fisc)), S["banner"]))
    if not info and not logo:
        return

    extras = [
        ("BACKGROUND", (0, 0), (-1, -1), P["head"]),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 10),
        ("RIGHTPADDING", (0, 0), (-1, -1), 10),
        ("TOPPADDING", (0, 0), (-1, -1), 9),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 9),
        ("INNERGRID", (0, 0), (-1, -1), 0, P["head"]),
        ("BOX", (0, 0), (-1, -1), 0, P["head"]),
    ]
    if logo:
        extras += [("BACKGROUND", (0, 0), (0, 0), colors.white),
                   ("ALIGN", (0, 0), (0, 0), "CENTER")]
        row, widths = [logo, info], [30 * mm, 144 * mm]
    else:
        row, widths = [info], [174 * mm]
    story.append(_table([row], widths, style_extras=extras))
    story.append(Spacer(1, 12))


def _header_letterhead(story: list, branding: dict | None, S: dict, P: dict,
                       doc: dict, L: dict, layout: str) -> None:
    """En-tête « papier à lettre » du kit CMRENOV, une identité visuelle par modèle.

    - essentiel : en-tête blanc sobre + filet d'accent (barre d'accent en haut de page via onPage).
    - detaille  : bandeau plein d'accent (texte blanc), titre « DEVIS PAR LOTS ».
    - signature : bandeau sable + intitulé de projet en serif, libellé DEVIS en accent.
    """
    b = branding or {}
    logo = _decode_brand_logo(b["logo_b64"], size_mm=22) if b.get("logo_b64") else None
    banner = layout in ("detaille", "signature")
    sable = colors.HexColor("#F4EFE6")

    # Styles d'en-tête déclinés selon le modèle (couleur d'identité et du grand libellé).
    ident = S["ident"]
    muted = S["muted"]
    label_style = S["label_right"]
    if layout == "detaille":
        ident = S["ident"].clone("lh_ident_w"); ident.textColor = colors.white
        muted = S["muted"].clone("lh_muted_w"); muted.textColor = colors.white
        label_style = S["label_right"].clone("lh_label_w"); label_style.textColor = colors.white
    elif layout == "signature":
        dark = colors.HexColor("#313834")
        ident = S["ident"].clone("lh_ident_d"); ident.textColor = dark
        label_style = S["label_right"].clone("lh_label_a"); label_style.textColor = P["main"]

    left: list = []
    if logo:
        left.append(logo)
    if b.get("company_name"):
        left.append(Paragraph(escape(b["company_name"]), ident))
    if b.get("contact_line"):
        left.append(Paragraph(escape(b["contact_line"]), muted))
    fisc = _fiscal_parts(b)
    if fisc:
        left.append(Paragraph(escape(" · ".join(fisc)), muted))

    doc_key = {"quote": "doc_quote", "invoice": "doc_invoice", "credit_note": "doc_credit"}
    label = L[doc_key.get(doc.get("doc_type"), "doc_generic")]
    if layout == "detaille" and doc.get("doc_type") == "quote":
        label = "DEVIS PAR LOTS"
    right: list = [Paragraph(f"<b>{escape(label)}</b>", label_style)]
    meta_style = muted if layout == "detaille" else S["muted_right"]
    if doc.get("number"):
        right.append(Paragraph(f"{L['num']} <b>{escape(str(doc['number']))}</b>", meta_style))
    if doc.get("issue_date"):
        right.append(Paragraph(f"{L['date']} : {doc['issue_date'][:10]}", meta_style))
    if doc.get("due_date"):
        right.append(Paragraph(f"{L['due']} : {doc['due_date'][:10]}", meta_style))

    if banner:
        bg = P["head"] if layout == "detaille" else sable
        extras = [
            ("BACKGROUND", (0, 0), (-1, -1), bg),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 14),
            ("RIGHTPADDING", (0, 0), (-1, -1), 14),
            ("TOPPADDING", (0, 0), (-1, -1), 14),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 14),
        ]
    else:
        extras = [
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("RIGHTPADDING", (0, 0), (-1, -1), 0),
            ("TOPPADDING", (0, 0), (-1, -1), 0),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
            ("LINEBELOW", (0, 0), (-1, -1), 1.4, P["line"]),
        ]
    story.append(_table([[left, right]], [104 * mm, 70 * mm], style_extras=extras))

    if layout == "signature":
        title = doc.get("title") or "Votre projet de rénovation"
        serif = S["h1"].clone("lh_serif")
        serif.fontName, serif.fontSize, serif.leading = "Times-Bold", 24, 27
        serif.textColor = colors.HexColor("#313834")
        story.append(_table([[Paragraph(escape(str(title)), serif)]], [174 * mm], style_extras=[
            ("BACKGROUND", (0, 0), (-1, -1), sable),
            ("LEFTPADDING", (0, 0), (-1, -1), 14), ("RIGHTPADDING", (0, 0), (-1, -1), 14),
            ("TOPPADDING", (0, 0), (-1, -1), 2), ("BOTTOMPADDING", (0, 0), (-1, -1), 16),
        ]))
        story.append(Spacer(1, 10))
    else:
        story.append(Spacer(1, 10))
        title = doc.get("title") or doc.get("number") or label
        story.append(Paragraph(escape(str(title)), S["h1"]))
        story.append(Spacer(1, 8))


def _signature_block(story: list, S: dict, L: dict, P: dict, sign_url: str | None) -> None:
    """Bon pour accord + QR code de signature en ligne (déterministe, aucun visuel généré)."""
    left = [Paragraph(f"<b>{L['agreement']}</b>", S["body"]),
            Paragraph("Date et signature du client :", S["muted"]),
            Spacer(1, 16)]
    qr_cell = ""
    if sign_url:
        try:
            import qrcode
            img = qrcode.make(sign_url)
            bio = BytesIO()
            img.save(bio, format="PNG")
            bio.seek(0)
            qr_cell = [Image(bio, width=24 * mm, height=24 * mm),
                       Paragraph("Scanner pour signer", S["muted"])]
            link_style = S["muted"].clone("doc_signlink")
            link_style.wordWrap = "CJK"   # force la coupe d'une URL sans espace
            link_style.fontSize = 6.2
            link_style.leading = 8
            left.append(Paragraph("Ou signer en ligne :", S["muted"]))
            left.append(Paragraph(f'<font color="#1F5F3F">{escape(sign_url)}</font>', link_style))
        except Exception:  # noqa: BLE001 — le devis reste valide sans QR
            qr_cell = ""
    story.append(Spacer(1, 14))
    story.append(_table([[left, qr_cell]], [132 * mm, 42 * mm], style_extras=[
        ("BOX", (0, 0), (-1, -1), 0.8, P["line"]),
        ("BACKGROUND", (0, 0), (-1, -1), P["soft"]),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("ALIGN", (1, 0), (1, 0), "CENTER"),
        ("LEFTPADDING", (0, 0), (-1, -1), 10),
        ("RIGHTPADDING", (0, 0), (-1, -1), 10),
        ("TOPPADDING", (0, 0), (-1, -1), 10),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
    ]))


def _wrap_to_width(canvas, text: str, max_w: float, font: str, size: float,
                   max_lines: int = 2) -> list[str]:
    """Découpe un texte sur la largeur réelle mesurée, sans jamais dépasser la marge."""
    text = (text or "").strip()
    if not text:
        return []
    words, lines, cur = text.split(), [], ""
    for wd in words:
        trial = f"{cur} {wd}".strip()
        if canvas.stringWidth(trial, font, size) <= max_w:
            cur = trial
        else:
            if cur:
                lines.append(cur)
            cur = wd
            if len(lines) == max_lines:
                break
    if cur and len(lines) < max_lines:
        lines.append(cur)
    if len(lines) == max_lines and len(" ".join(lines)) < len(text):
        while lines[-1] and canvas.stringWidth(lines[-1] + " …", font, size) > max_w:
            lines[-1] = lines[-1][:-1]
        lines[-1] += " …"
    return lines


def _page_footer(canvas, pdf_doc, branding: dict | None, P: dict, L: dict) -> None:
    """Pied de page répété : mentions légales du pro + pagination."""
    b = branding or {}
    canvas.saveState()
    w, _h = A4
    y = 13 * mm
    canvas.setStrokeColor(P["main"])
    canvas.setLineWidth(0.8)
    canvas.line(18 * mm, y + 9 * mm, w - 18 * mm, y + 9 * mm)
    canvas.setFont("Helvetica", 6.4)
    canvas.setFillColor(colors.HexColor("#4B5563"))
    avail = w - 36 * mm - 18 * mm  # marges + place pour la pagination
    legal = " · ".join(x.strip() for x in str(b.get("footer_text") or "").splitlines() if x.strip())
    lines = _wrap_to_width(canvas, legal, avail, "Helvetica", 6.4, max_lines=2)
    lines += _wrap_to_width(canvas, L["footer"], avail, "Helvetica", 6.4, max_lines=2)
    for i, ln in enumerate(lines[:4]):
        canvas.drawString(18 * mm, y + 6 * mm - i * 2.6 * mm, ln)
    canvas.setFont("Helvetica-Bold", 6.6)
    canvas.drawRightString(w - 18 * mm, y + 6 * mm, f"page {canvas.getPageNumber()}")
    canvas.restoreState()


def _effective_validity(doc: dict) -> str | None:
    """Date de validité effective : auto (émission + validity_days) sinon date manuelle."""
    days = doc.get("validity_days")
    if days and int(days) > 0:
        base = doc.get("issue_date") or doc.get("created_at")
        try:
            d = datetime.fromisoformat(base.replace("Z", "+00:00")) if base else datetime.now(timezone.utc)
        except (ValueError, AttributeError):
            d = datetime.now(timezone.utc)
        return (d + timedelta(days=int(days))).date().isoformat()
    return (doc.get("valid_until") or "").strip() or None


def _parties_block(story: list, doc: dict, S: dict, L: dict, P: dict) -> None:
    """Bloc CLIENT / CHANTIER / VALIDITÉ (devis), façon kit CMRENOV."""
    client = doc.get("client") or {}
    name = " ".join(x for x in [client.get("first_name"), client.get("last_name")] if x)
    cl = []
    if client.get("company"):
        cl.append(f"<b>{escape(client['company'])}</b>")
    if name:
        cl.append(escape(name))
    addr = ", ".join(x for x in [client.get("address"), client.get("postal_code"), client.get("city")] if x)
    if addr:
        cl.append(escape(addr))
    if client.get("email"):
        cl.append(escape(client["email"]))

    columns = [(L.get("p_client", "CLIENT"), cl or [L.get("client", "Client")])]

    site = []
    if doc.get("project_address"):
        site.append(f"<b>{escape(doc['project_address'])}</b>")
    if doc.get("project_duration"):
        site.append(escape(f"{L.get('p_duration', 'Durée')} : {doc['project_duration']}"))
    if doc.get("project_start"):
        site.append(escape(f"{L.get('p_start', 'Démarrage')} : {doc['project_start']}"))
    if site:
        columns.append((L.get("p_site", "CHANTIER"), site))

    vu = _effective_validity(doc)
    if vu:
        valid_label = L.get("p_valid_until", "Valable jusqu'au")
        columns.append((L.get("p_validity", "VALIDITÉ"),
                        [f"<b>{escape(valid_label)} {vu}</b>"]))

    kicker = S["kicker"].clone("party_kicker")
    kicker.spaceAfter = 3
    cells = []
    for head, body_lines in columns:
        stack = [Paragraph(head, kicker)]
        stack.append(Paragraph("<br/>".join(body_lines), S["body"]))
        cells.append(stack)
    width = round(174 / len(cells), 1)
    story.append(_table([cells], [width * mm] * len(cells), style_extras=[
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (0, -1), 0),
        ("LEFTPADDING", (1, 0), (-1, -1), 10),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
        ("LINEBEFORE", (1, 0), (-1, -1), 0.5, P["line"]),
    ]))
    story.append(Spacer(1, 12))


def _payment_schedule(story: list, doc: dict, S: dict, L: dict, P: dict) -> None:
    """Échéancier de règlement prévisionnel (label · % · montant TTC)."""
    stages = doc.get("payment_schedule") or []
    if not stages:
        return
    ttc = float((doc.get("totals") or {}).get("ttc", 0) or 0)
    story.append(Spacer(1, 12))
    story.append(Paragraph(L.get("schedule_title", "Règlement prévisionnel"), S["h2"]))
    rows = [[L.get("schedule_stage", "Échéance"), "%", L.get("schedule_amount", "Montant TTC")]]
    for s in stages:
        pct = float(s.get("pct") or 0)
        rows.append([escape(s.get("label") or ""), f"{_fmt(pct)}%", _fmt(round(ttc * pct / 100, 2), "€")])
    story.append(_table(rows, [116 * mm, 20 * mm, 38 * mm], style_extras=[
        ("BACKGROUND", (0, 0), (-1, 0), P["head"]),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 8.5),
        ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, P["soft"]]),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))


def _client_block(story: list, client: dict | None, S: dict, L: dict, P: dict,
                  layout: str = DEFAULT_LAYOUT) -> None:
    if not client:
        return
    name = " ".join(x for x in [client.get("first_name"), client.get("last_name")] if x)
    lines = []
    if client.get("company"):
        lines.append(f"<b>{client['company']}</b>")
    if name:
        lines.append(name if not client.get("company") else name)
    addr = ", ".join(x for x in [client.get("address"), client.get("postal_code"),
                                 client.get("city")] if x)
    if addr:
        lines.append(addr)
    if client.get("email"):
        lines.append(client["email"])
    if client.get("phone"):
        lines.append(client["phone"])
    if client.get("siret"):
        lines.append(f"SIRET {client['siret']}")
    html = "<br/>".join(lines) or L["client"]
    tbl = _table([[Paragraph(f"<b>{L['addressed_to']}</b><br/>" + html, S["body"])]], [82 * mm],
                 style_extras=[
                     ("BOX", (0, 0), (-1, -1), 0.6, P["line"]),
                     ("BACKGROUND", (0, 0), (-1, -1), P["soft"]),
                     ("LEFTPADDING", (0, 0), (-1, -1), 10),
                     ("RIGHTPADDING", (0, 0), (-1, -1), 10),
                     ("TOPPADDING", (0, 0), (-1, -1), 8),
                     ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
                 ])
    tbl.hAlign = "LEFT" if layout in ("compact",) + LETTERHEAD else "RIGHT"
    story.append(tbl)
    story.append(Spacer(1, 6 if layout == "compact" else 10))


def _photo_strip(photos):
    """Bande de vignettes (max 9, 3 par rangée) sous la désignation. None si aucune."""
    from reportlab.lib.utils import ImageReader
    from engines import storage
    max_w, max_h = 56, 46
    imgs = []
    for ph in (photos or [])[:9]:
        path = ph.get("storage_path") if isinstance(ph, dict) else None
        if not path:
            continue
        try:
            data, _ = storage.get_object(path)
            bio = BytesIO(data)
            iw, ih = ImageReader(bio).getSize()
            bio.seek(0)
            scale = min(max_w / iw, max_h / ih, 1.0)
            imgs.append(Image(bio, width=iw * scale, height=ih * scale))
        except Exception:
            continue
    if not imgs:
        return None
    rows = [imgs[i:i + 3] for i in range(0, len(imgs), 3)]
    for r in rows:
        while len(r) < 3:
            r.append("")
    t = Table(rows, hAlign="LEFT")
    t.setStyle(TableStyle([
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ]))
    return t


def _desig_cell(ln: dict, S: dict):
    """Cellule désignation : n° + titre en gras + description détaillée (puces) en dessous + photos."""
    num = (ln.get("_num") or "").strip()
    prefix = f'<font color="#8A93A0">{escape(num)}</font>  ' if num else ""
    html = f"{prefix}<b>{escape(ln.get('designation') or '')}</b>"
    desc = (ln.get("description") or "").strip()
    if desc:
        desc_html = escape(desc).replace("\r\n", "\n").replace("\n", "<br/>")
        html += f'<br/><font size="7.5" color="#5B6472">{desc_html}</font>'
    para = Paragraph(html, S["body"])
    agg = list(ln.get("photos") or [])
    for comp in (ln.get("components") or []):
        agg.extend(comp.get("photos") or [])
    strip = _photo_strip(agg)
    if strip is not None:
        return [para, Spacer(1, 3), strip]
    return para


def _lines_table(story: list, lines: list, S: dict, L: dict, P: dict,
                 layout: str = DEFAULT_LAYOUT) -> None:
    story.append(Paragraph(L["lines_title"], S["h2"]))
    header = [L["c_designation"], L["c_qty"], L["c_unit"], L["c_pu_ht"],
              L.get("c_discount", "Remise"), L["c_vat"], L["c_total_ht"]]
    col_widths = [66 * mm, 14 * mm, 14 * mm, 20 * mm, 14 * mm, 14 * mm, 26 * mm]
    SPECIAL = ("section", "subsection", "text", "pagebreak")

    def _line_ht(b):
        return round((b.get("qty") or 0) * (b.get("unit_price_ht") or 0) * (1 - float(b.get("discount_pct") or 0) / 100), 2)

    has_structure = any(b.get("kind") in SPECIAL for b in lines)

    # Numérotation hiérarchique alignée sur l'ordre des blocs.
    nums = []
    sec = sub = ln = 0
    for b in lines:
        k = b.get("kind") or "line"
        if k == "section":
            sec += 1; sub = 0; ln = 0; nums.append(str(sec))
        elif k == "subsection":
            sub += 1; ln = 0; nums.append(f"{sec}.{sub}" if sec else str(sub))
        elif k in ("text", "pagebreak"):
            nums.append("")
        else:
            ln += 1
            nums.append(f"{sec}.{sub}.{ln}" if (sec and sub) else (f"{sec}.{ln}" if sec else str(ln)))

    # Sous-totaux par section / sous-section.
    sec_sub, subsec_sub = {}, {}
    cur_sec = cur_sub = None
    for i, b in enumerate(lines):
        k = b.get("kind") or "line"
        if k == "section":
            cur_sec = i; cur_sub = None; sec_sub[i] = 0.0
        elif k == "subsection":
            cur_sub = i; subsec_sub[i] = 0.0
        elif k not in SPECIAL:
            if cur_sec is not None:
                sec_sub[cur_sec] += _line_ht(b)
            if cur_sub is not None:
                subsec_sub[cur_sub] += _line_ht(b)

    lot_total = S["body_right"].clone("lot_total2")
    lot_total.textColor, lot_total.fontName = P["deep"], "Helvetica-Bold"

    def _new_seg():
        return {"rows": [list(header)], "roles": {}}

    segments = []
    seg = _new_seg()
    any_line = False
    for i, b in enumerate(lines):
        k = b.get("kind") or "line"
        if k == "pagebreak":
            if len(seg["rows"]) > 1:
                segments.append(seg)
            seg = _new_seg()
            continue
        if k in ("section", "subsection"):
            r = len(seg["rows"])
            title = (b.get("title") or "").strip() or (L.get("other_lot", "Autres") if k == "section" else "")
            pref = f"{nums[i]} " if nums[i] else ""
            sub_amount = (sec_sub if k == "section" else subsec_sub).get(i, 0)
            seg["rows"].append([Paragraph(f"<b>{escape(pref)}{escape(title)}</b>", S["body"]), "", "", "", "", "",
                                Paragraph(f"{_fmt(sub_amount, '€')} HT", lot_total)])
            seg["roles"][r] = k
        elif k == "text":
            r = len(seg["rows"])
            txt = escape((b.get("text") or "").strip()).replace("\n", "<br/>")
            seg["rows"].append([Paragraph(f'<font color="#5B6472">{txt}</font>', S["body"]), "", "", "", "", "", ""])
            seg["roles"][r] = "text"
        else:
            any_line = True
            r = len(seg["rows"])
            qty = b.get("qty") or 0
            pu = b.get("unit_price_ht") or 0
            disc = float(b.get("discount_pct") or 0)
            seg["rows"].append([_desig_cell({**b, "_num": nums[i]}, S), _fmt(qty), b.get("unit") or "",
                                _fmt(pu, "€"), (f"{_fmt(disc)}%" if disc else "—"),
                                f"{_fmt(b.get('vat_rate') or 0)}%", _fmt(_line_ht(b), "€")])
            seg["roles"][r] = "line"
    if len(seg["rows"]) > 1:
        segments.append(seg)

    # Fallback ancien format (aucune structure) : regroupement par `category`.
    if not has_structure:
        payable = [b for b in lines if b.get("kind") not in SPECIAL]
        groups, order = [], {}
        for b in payable:
            cat = (b.get("category") or "").strip()
            if cat not in order:
                order[cat] = len(groups)
                groups.append((cat, []))
            groups[order[cat]][1].append(b)
        if any(c for c, _ in groups):
            seg = _new_seg()
            for cat, lns in groups:
                r = len(seg["rows"])
                subt = round(sum(_line_ht(x) for x in lns), 2)
                seg["rows"].append([Paragraph(f"<b>{escape(cat or L.get('other_lot', 'Autres'))}</b>", S["body"]),
                                    "", "", "", "", "", Paragraph(f"{_fmt(subt, '€')} HT", lot_total)])
                seg["roles"][r] = "section"
                for x in lns:
                    rr = len(seg["rows"])
                    qty = x.get("qty") or 0; pu = x.get("unit_price_ht") or 0; disc = float(x.get("discount_pct") or 0)
                    seg["rows"].append([_desig_cell(x, S), _fmt(qty), x.get("unit") or "", _fmt(pu, "€"),
                                        (f"{_fmt(disc)}%" if disc else "—"), f"{_fmt(x.get('vat_rate') or 0)}%", _fmt(_line_ht(x), "€")])
                    seg["roles"][rr] = "line"
            segments = [seg]

    if not any_line and not segments:
        segments = [{"rows": [list(header), [L["no_line"], "", "", "", "", "", ""]], "roles": {}}]

    for si, seg in enumerate(segments):
        extras = [
            ("BACKGROUND", (0, 0), (-1, 0), P["head"]),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 7.6 if layout == "compact" else 8.5),
            ("ALIGN", (1, 1), (-1, -1), "RIGHT"),
            ("ALIGN", (0, 0), (0, -1), "LEFT"),
            ("VALIGN", (0, 1), (-1, -1), "TOP"),
            ("TOPPADDING", (0, 1), (-1, -1), 3 if layout == "compact" else 6),
            ("BOTTOMPADDING", (0, 1), (-1, -1), 3 if layout == "compact" else 6),
        ]
        for r, role in seg["roles"].items():
            if role in ("section", "subsection"):
                extras += [("SPAN", (0, r), (5, r)),
                           ("BACKGROUND", (0, r), (-1, r), P["row"] if role == "section" else P["soft"]),
                           ("TEXTCOLOR", (0, r), (-1, r), P["deep"]),
                           ("ALIGN", (6, r), (6, r), "RIGHT"),
                           ("VALIGN", (0, r), (-1, r), "MIDDLE"),
                           ("TOPPADDING", (0, r), (-1, r), 7)]
                if role == "subsection":
                    extras += [("LEFTPADDING", (0, r), (0, r), 16)]
            elif role == "text":
                extras += [("SPAN", (0, r), (-1, r)), ("BACKGROUND", (0, r), (-1, r), colors.white)]
        story.append(_table(seg["rows"], col_widths, style_extras=extras, repeat_rows=1, splittable=True))
        if si < len(segments) - 1:
            story.append(PageBreak())


def _lot_breakdown(lines: list, L: dict) -> list:
    """(nom de lot, total HT) en suivant le même regroupement que le tableau des lignes :
    par sections si le devis en a, sinon par `category`. Pour le récap de synthèse."""
    groups, order = {}, []
    other = L.get("other_lot", "Autres")

    def _ht(b):
        return round((b.get("qty") or 0) * (b.get("unit_price_ht") or 0) * (1 - float(b.get("discount_pct") or 0) / 100), 2)

    def add(name, ht):
        if name not in groups:
            groups[name] = 0.0
            order.append(name)
        groups[name] += ht

    has_sections = any(b.get("kind") == "section" for b in lines)
    if has_sections:
        cur = None
        for b in lines:
            k = b.get("kind")
            if k == "section":
                cur = (b.get("title") or "").strip() or other
                if cur not in groups:
                    groups[cur] = 0.0
                    order.append(cur)
            elif k in (None, "line"):
                add(cur or other, _ht(b))
    else:
        for b in lines:
            if b.get("kind") in ("section", "subsection", "text", "pagebreak"):
                continue
            add((b.get("category") or "").strip() or other, _ht(b))
    return [(n, groups[n]) for n in order]


def _recap(story: list, doc: dict, S: dict, L: dict, P: dict) -> None:
    t = doc.get("totals", {})
    story.append(Spacer(1, 12))
    # Synthèse par lot/étage : aperçu rapide pour relire un gros chiffrage (dès 2 lots).
    lots = _lot_breakdown(doc.get("lines") or [], L)
    if len([x for x in lots if abs(x[1]) > 0.005]) >= 2:
        story.append(Paragraph(L.get("lot_recap_title", "Récapitulatif par lot (HT)"), S["h2"]))
        lrows = [[Paragraph(escape(n), S["body"]), _fmt(ht, "€")] for n, ht in lots]
        story.append(_table(lrows, [130 * mm, 45 * mm], style_extras=[
            ("BACKGROUND", (0, 0), (-1, -1), P["soft"]),
            ("FONTNAME", (1, 0), (1, -1), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 9),
            ("ALIGN", (1, 0), (1, -1), "RIGHT"),
            ("LINEBELOW", (0, 0), (-1, -2), 0.3, P["line"]),
            ("LEFTPADDING", (0, 0), (-1, -1), 8),
            ("RIGHTPADDING", (0, 0), (-1, -1), 8),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ]))
        story.append(Spacer(1, 10))
        story.append(Paragraph(L["recap"], S["h2"]))
    else:
        story.append(Paragraph(L["recap"], S["h2"]))
    rows = [[L["total_ht"], _fmt(t.get("ht", 0), "€")]]
    for rate, amount in (t.get("tva_breakdown") or {}).items():
        rows.append([L["vat"].format(rate=_fmt(float(rate))), _fmt(amount, "€")])
    rows.append([L["total_ttc"], _fmt(t.get("ttc", 0), "€")])
    if (t.get("deposit_pct") or 0) > 0:
        rows.append([L["deposit_asked"].format(pct=_fmt(t.get('deposit_pct'))),
                     _fmt(t.get("deposit_amount", 0), "€")])
        rows.append([L["remaining"], _fmt(t.get("remaining", 0), "€")])
    ttc_row = 1 + len(t.get("tva_breakdown") or {})
    story.append(_table(rows, [110 * mm, 45 * mm], style_extras=[
        ("BACKGROUND", (0, 0), (0, -1), P["soft"]),
        ("BACKGROUND", (0, ttc_row), (-1, ttc_row), P["main"]),
        ("TEXTCOLOR", (0, ttc_row), (-1, ttc_row), colors.white),
        ("FONTNAME", (0, ttc_row), (-1, ttc_row), "Helvetica-Bold"),
        ("FONTNAME", (1, 0), (1, -1), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9.5),
        ("FONTSIZE", (0, ttc_row), (-1, ttc_row), 12),
        ("ALIGN", (1, 0), (1, -1), "RIGHT"),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))


def _facturx_badge(story: list, S: dict, P: dict, facturx: bool) -> None:
    """Encart de réassurance « Factur-X » sur les factures/avoirs.

    - facturx=True  : ce fichier EST la facture électronique hybride (XML intégré).
    - facturx=False : une version Factur-X est disponible (le PDF simple ne contient pas le XML).
    """
    if facturx:
        title = "Facture électronique Factur-X"
        body_txt = ("Ce document est une facture électronique au format <b>Factur-X</b> : un PDF/A-3 "
                    "avec un fichier <b>XML CII intégré</b> (norme européenne <b>EN 16931</b>, profil BASIC). "
                    "Il est exploitable automatiquement par votre logiciel comptable et prêt pour la "
                    "facturation électronique (réforme française).")
    else:
        title = "Compatible facturation électronique (Factur-X)"
        body_txt = ("Une version <b>Factur-X</b> de cette facture (PDF/A-3 + <b>XML CII</b> intégré, norme "
                    "<b>EN 16931</b>, profil BASIC) est disponible via le bouton « Factur-X » de votre "
                    "espace, pour la facturation électronique (réforme française).")
    inner = [Paragraph(f"<b>{title}</b>", S["body"]), Spacer(1, 2), Paragraph(body_txt, S["muted"])]
    box = Table([[inner]], colWidths=[174 * mm])
    box.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), P["soft"]),
        ("BOX", (0, 0), (-1, -1), 0.6, P["line"]),
        ("LINEBEFORE", (0, 0), (0, -1), 2.2, P["main"]),
        ("LEFTPADDING", (0, 0), (-1, -1), 8), ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 6), ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    story.append(Spacer(1, 12))
    story.append(box)


def build_document_pdf(doc: dict, branding: dict | None = None,
                       reviews: dict | None = None, lang: str | None = None,
                       sign_url: str | None = None, cover: list | None = None,
                       watermark_logo_b64: str | None = None,
                       appendix: list | None = None, facturx: bool = False) -> bytes:
    dossier = doc.get("study_dossier") if doc.get("doc_type") == "quote" else None
    if dossier and dossier.get("schema_version") == "construction-dossier-1":
        # The commercial cover retains identity, legal terms, VAT and signature.
        branding = {**(branding or {}), "accent_color": "#925535", "doc_layout": "essentiel"}
    else:
        dossier = None
    buf = BytesIO()
    P = _palette(branding)
    L = pdf_labels(lang)
    layout = _layout_of(branding)
    top = {"bandeau": 14, "classique": 16, "compact": 12,
           "essentiel": 16, "detaille": 16, "signature": 14}[layout]
    pdf = SimpleDocTemplate(buf, pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm,
                            topMargin=top * mm, bottomMargin=26 * mm)
    S = _doc_styles(_styles(), P, layout)
    if dossier:
        from engines.study_dossier_pdf import fonts
        fonts()
        for style in S.values():
            style.fontName = "DossierBold" if "Bold" in style.fontName else "Dossier"
    story: list = []
    if cover:
        story += list(cover)

    if layout in LETTERHEAD:
        _header_letterhead(story, branding, S, P, doc, L, layout)
    else:
        {"bandeau": _header_banner, "classique": _header_classic,
         "compact": _header_compact}[layout](story, branding, S, P)
        _doc_key = {"quote": "doc_quote", "invoice": "doc_invoice", "credit_note": "doc_credit"}
        label = L[_doc_key.get(doc.get("doc_type"), "doc_generic")]
        story.append(Paragraph(label, S["kicker"]))
        story.append(Paragraph(doc.get("title") or doc.get("number") or label, S["h1"]))
        meta = []
        if doc.get("number"):
            meta.append(f"{L['num']} <b>{doc['number']}</b>")
        if doc.get("issue_date"):
            meta.append(f"{L['date']} : {doc['issue_date'][:10]}")
        if doc.get("due_date"):
            meta.append(f"{L['due']} : {doc['due_date'][:10]}")
        if meta:
            story.append(Paragraph(" · ".join(meta), S["muted"]))
        story.append(Spacer(1, 10))

    if doc.get("doc_type") == "quote":
        _parties_block(story, doc, S, L, P)
    else:
        _client_block(story, doc.get("client"), S, L, P, layout)
    _lines_table(story, doc.get("lines", []), S, L, P, layout)
    _recap(story, doc, S, L, P)
    _payment_schedule(story, doc, S, L, P)

    _attach = doc.get("attachment_image_b64")
    if _attach:
        try:
            import base64
            raw = base64.b64decode(_attach.split(",", 1)[-1])
            img = Image(BytesIO(raw))
            max_w = 170 * mm
            ratio = (img.imageHeight or 1) / (img.imageWidth or 1)
            img.drawWidth = max_w
            img.drawHeight = max_w * ratio
            story.append(Spacer(1, 14))
            story.append(Paragraph(L.get("attachment_3d", "Vue 3D du projet"), S["h2"]))
            story.append(img)
        except Exception:
            pass

    if doc.get("notes"):
        story.append(Spacer(1, 12))
        story.append(Paragraph(L["notes"], S["h2"]))
        story.append(Paragraph(doc["notes"].replace("\n", "<br/>"), S["body"]))

    # RIB / coordonnées bancaires (factures et avoirs uniquement)
    if doc.get("doc_type") in ("invoice", "credit_note") and (branding or {}).get("bank_details"):
        story.append(Spacer(1, 12))
        story.append(Paragraph("Coordonnées bancaires", S["h2"]))
        story.append(Paragraph(str(branding["bank_details"]).replace("\n", "<br/>"), S["body"]))

    # Encart « Factur-X » — réassurance conformité facturation électronique (factures/avoirs)
    if doc.get("doc_type") in ("invoice", "credit_note"):
        _facturx_badge(story, S, P, facturx)

    if doc.get("doc_type") == "quote":
        if dossier:
            from engines.study_dossier import quote_lines_hash
            unchanged = quote_lines_hash(doc.get("lines", [])) == doc.get("study_lines_hash") and not doc.get("global_discount_pct")
            note = ("Étude de référence annexée : métrés, formules, hypothèses et provisions. Les choix constructifs et les prix restent à confirmer."
                    if unchanged else "Les lignes ou remises ont changé depuis l’étude. Les calculs de l’étude source ne sont pas annexés à ce devis modifié ; vérifiez la cohérence des nouveaux postes.")
            story.append(Paragraph(escape(note), S["muted"]))
        _signature_block(story, S, L, P, sign_url)
        _story_quote_reviews(story, reviews, S)

    if appendix:
        from reportlab.platypus import PageBreak
        story.append(PageBreak())
        story += list(appendix)

    # Filigrane par défaut = logo de l'entreprise (branding), afin que chaque devis/facture
    # porte la marque de l'entreprise avec un contraste visible sur toutes les pages.
    _wm_b64 = watermark_logo_b64 or (branding or {}).get("logo_b64")
    _wm = make_logo_watermark(_wm_b64) if _wm_b64 else None

    def _on_page(canvas, pdf_doc):
        if dossier:
            canvas.saveState()
            canvas.setFillColor(colors.HexColor("#F7F1E9"))
            canvas.rect(0, 0, A4[0], A4[1], fill=1, stroke=0)
            canvas.restoreState()
        if _wm:
            _wm(canvas, pdf_doc)
        if layout == "essentiel":
            canvas.saveState()
            canvas.setFillColor(P["main"])
            canvas.rect(0, A4[1] - 3 * mm, A4[0], 3 * mm, fill=1, stroke=0)
            canvas.restoreState()
        _page_footer(canvas, pdf_doc, branding, P, L)

    pdf.build(story, onFirstPage=_on_page, onLaterPages=_on_page)
    if dossier and unchanged:
        from engines.study_dossier_pdf import build_dossier_pdf
        import pymupdf
        source_pdf = build_dossier_pdf({"plan_id": doc.get("source_plan_id"), "filename": doc.get("title")}, dossier, branding)
        with pymupdf.open(stream=buf.getvalue(), filetype="pdf") as commercial:
            with pymupdf.open(stream=source_pdf, filetype="pdf") as annex:
                commercial.insert_pdf(annex)
            return commercial.tobytes(garbage=3, deflate=True)
    return buf.getvalue()
