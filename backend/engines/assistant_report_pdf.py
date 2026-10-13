"""Unified conversation report: the PDF is built from the same persisted tool results shown in the chat (calculations, solutions, sources)."""
import io
from datetime import datetime, timezone

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import Image as RLImage, KeepTogether, PageBreak, Paragraph, SimpleDocTemplate, Spacer
from PIL import Image, ImageDraw

from engines.pdf_takeoff import _story_header_branding, _styles
from engines.plan_cotes_pdf import _e, _tbl

BLUE = colors.HexColor("#1D4ED8")
W = A4[0] - 28 * mm
STATE = {"confirmed": "Confirmé", "probable": "Probable", "indeterminate": "Indéterminé", "not_verifiable": "Non vérifiable"}
PRIORITY = {"demonstrated": "1 · Écart démontré", "to_clarify": "2 · À éclaircir", "info": "3 · Information"}
CONTROL_MENTION = ("Ce document présente un contrôle de cohérence des cotes, alignements et éléments expressément inclus dans la demande, à partir "
                   "des documents fournis. Il ne constitue pas une note de calcul structurel et ne remet pas en cause le dimensionnement établi par le "
                   "bureau d'études. Les points signalés précisent les vérifications ou clarifications à effectuer.")
SOLUTION_MENTION = ("Les solutions comparées sont des propositions à valider : leur statut, leurs conditions d'application et les vérifications "
                    "spécifiques indiquées ne préjugent d'aucune approbation du bureau d'études sur une solution qu'il n'a pas examinée.")


def _styles_blue():
    s = _styles()
    s["h2"] = ParagraphStyle("h2b", parent=s["h2"], textColor=BLUE)
    s["h3"] = ParagraphStyle("h3b", parent=s["h2"], textColor=BLUE, fontSize=11, leading=14, spaceBefore=6, spaceAfter=3)
    s["cell"] = ParagraphStyle("cell", parent=s["body"], fontSize=7.5, leading=9.5)
    s["concl"] = ParagraphStyle("concl", parent=s["body"], backColor=colors.HexColor("#EFF6FF"), borderColor=BLUE, borderWidth=0.8,
                                borderPadding=6, leading=14)
    return s


def _p(text, S, style="cell"):
    return Paragraph(_e(text), S[style])


def _link(url, label, S):
    return Paragraph(f'<a href="{_e(url)}" color="#1D4ED8"><u>{_e(label)}</u></a>', S["cell"])


def _footer(company: str, project: str, lang: str):
    brand = "Análise assistida por ConstruPilot.pt" if lang == "pt" else "Analyse assistée par ConstruPilot.fr"

    def draw(canvas, doc):
        canvas.saveState()
        canvas.setFont("Helvetica", 7.5)
        canvas.setFillColor(colors.HexColor("#64748B"))
        left = " · ".join(x for x in (company, project) if x)
        canvas.drawString(14 * mm, 9 * mm, left[:110])
        canvas.drawRightString(A4[0] - 14 * mm, 9 * mm, f"{brand} · page {doc.page}")
        canvas.restoreState()
    return draw


def annotated_crop(crop: Image.Image, rel_box: list[float], label: str) -> bytes:
    """Frame + table identifier drawn as vectors on a real crop of the document (no generated imagery)."""
    crop = crop.convert("RGB")
    w, h = crop.size
    draw = ImageDraw.Draw(crop)
    bx0, by0, bx1, by1 = rel_box[0] * w, rel_box[1] * h, rel_box[2] * w, rel_box[3] * h
    draw.rectangle([bx0 - 4, by0 - 4, bx1 + 4, by1 + 4], outline=(29, 78, 216), width=4)
    tw = 7 * len(label) + 10
    ty = by0 - 22 if by0 - 22 > 0 else min(h - 16, by1 + 6)
    draw.rectangle([max(0, bx0 - 4), ty, max(0, bx0 - 4) + tw, ty + 16], fill=(29, 78, 216))
    draw.text((max(0, bx0 - 4) + 4, ty + 2), label, fill=(255, 255, 255))
    out = io.BytesIO()
    crop.save(out, format="PNG")
    return out.getvalue()


def _calc_rows(calculations: list[dict], S, crops: list | None = None):
    rows, findings, qty = [], [], []
    for i, rec in enumerate(calculations, 1):
        res = rec.get("result") or {}
        for calc in [c for c in (res.get("calculation"), res.get("comparison")) if c]:
            ref = f"CA-{len(rows) + 1:02d}"
            rows.append([ref, _p(calc.get("kind", ""), S), _p(calc.get("formula", ""), S),
                         _p("" if calc.get("result") is None else f"{calc['result']:g} {calc.get('unit', '')}", S), _p(STATE.get(calc.get("state"), calc.get("state")), S)])
            if crops is not None and calc.get("kind") != "chain_vs_declared_total":
                for inp in calc.get("inputs") or []:
                    if inp.get("plan_id") and inp.get("box") and len(inp["box"]) == 4:
                        crops.append({"ref": ref, "reading": inp})
        for f in res.get("findings") or []:
            findings.append([f"CF-{len(findings) + 1:02d}", _p(PRIORITY.get(f.get("severity"), f.get("severity")), S), _p(f.get("subject", ""), S),
                             _p(f.get("explanation", ""), S), _p(f.get("consequence") or "—", S), _p(f.get("action") or "—", S)])
        if rec.get("tool") == "resolve_ambiguous_reading" and res.get("state") == "indeterminate":
            findings.append([f"CF-{len(findings) + 1:02d}", _p(PRIORITY["to_clarify"], S), _p(res.get("reading", {}).get("label", "Lecture"), S),
                             _p(res.get("reason", ""), S), _p("Aucune valeur retenue tant que la lecture n'est pas prouvée", S), _p(res.get("action") or "—", S)])
        for line in res.get("lines") or []:
            qty.append([_p(line.get("element", ""), S), _p(line.get("location") or "—", S), _p(line.get("formula", ""), S),
                        _p("" if line.get("net") is None else f"{line['net']:g} {line.get('unit', '')}", S),
                        _p(STATE.get(line.get("state"), line.get("state")) + (f" · manque : {', '.join(line['missing'])}" if line.get("missing") else ""), S)])
    return rows, findings, qty


def build_conversation_report(*, conv: dict, calculations: list[dict], solutions: list[dict], sources: list[dict], plans: list[dict],
                              branding: dict | None, lang: str = "fr", scope: str | None = None, crop_provider=None) -> bytes:
    S = _styles_blue()
    company = (branding or {}).get("company_name") or ""
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=14 * mm, rightMargin=14 * mm, topMargin=14 * mm, bottomMargin=16 * mm,
                            title=f"Rapport ConstruPilot — {conv.get('title', '')}")
    story = []
    _story_header_branding(story, branding, S)
    story.append(Paragraph("Rapport de contrôle et de solutions techniques", S["h1"]))
    today = datetime.now(timezone.utc).strftime("%d/%m/%Y")
    story.append(_p(f"Dossier : {conv.get('title', '')} · Référence : {conv.get('conversation_id', '')[-10:].upper()} · Date : {today}", S, "muted"))
    story.append(Spacer(1, 4))
    crops = []
    rows, findings, qty = _calc_rows([c for c in calculations if not c.get("superseded_by")], S, crops)
    if plans:
        story.append(Paragraph("Documents analysés", S["h2"]))
        prow = [["Document", "Identifiant", "Empreinte SHA-256", "Pages", "Révision / date du document", "Importé le"]]
        for p in plans:
            prow.append([_p(p.get("filename", ""), S), _p(p.get("plan_id", ""), S), _p((p.get("sha256") or p.get("file_sha256") or "—")[:24], S),
                         _p(str(p.get("page_count") or "—"), S), _p(p.get("revision") or "non indiquée sur le document", S), _p((p.get("created_at") or "")[:10], S)])
        story.append(_tbl(prow, [40 * mm, 30 * mm, 42 * mm, 12 * mm, 38 * mm, 20 * mm], S))
        story.append(_p("La date d'import n'est pas la date de révision du document.", S, "muted"))
    demonstrated = sum(1 for f in findings if "démontré" in f[1].text)
    to_clarify = sum(1 for f in findings if "éclaircir" in f[1].text)
    confirmed = sum(1 for r in rows if r[4].text == "Confirmé")
    recommended = [s.get("recommended_option") for s in solutions if s.get("recommended_option")]
    story.append(Paragraph("Conclusion rapide", S["h2"]))
    concl = (f"{len(rows)} calcul(s) vérifié(s) dont {confirmed} confirmé(s) · {demonstrated} écart(s) démontré(s) · {to_clarify} point(s) à éclaircir · "
             f"{len(qty)} ligne(s) de quantités · {len(solutions)} comparaison(s) de solutions" + (f" — recommandation : {', '.join(recommended)}" if recommended else "")
             + f" · {sum(1 for s in sources if s.get('verified'))}/{len(sources)} source(s) avec passage probant.")
    story.append(Paragraph(_e(concl), S["concl"]))
    story.append(Paragraph("Objet du contrôle", S["h2"]))
    story.append(_p(scope or conv.get("title") or "Périmètre défini par la demande de l'utilisateur.", S, "body"))
    if findings:
        story.append(Paragraph("Constatations", S["h2"]))
        story.append(_tbl([["Réf.", "Priorité", "Sujet", "Preuve / calcul", "Conséquence possible", "Action"]] + findings,
                          [12 * mm, 22 * mm, 30 * mm, 50 * mm, 34 * mm, 34 * mm], S))
    if rows:
        story.append(Paragraph("Calculs", S["h2"]))
        story.append(_tbl([["Réf.", "Type", "Formule (entrées → résultat)", "Résultat", "État"]] + rows, [12 * mm, 28 * mm, 90 * mm, 24 * mm, 28 * mm], S))
        story.append(_p("Tolérance de lecture 1 cm ; aucune tolérance d'exécution appliquée sans référence vérifiée.", S, "muted"))
    shown = 0
    for item in crops:
        r = item["reading"]
        cropped = crop_provider(r["plan_id"], r.get("page") or 0, r["box"]) if crop_provider else None
        if cropped is None or shown >= 24:
            continue
        if shown == 0:
            story.append(Paragraph("Extraits annotés du plan", S["h2"]))
            story.append(_p("Recadrages réels du document analysé ; le cadre bleu localise la cote utilisée dans le calcul portant le même identifiant.", S, "muted"))
        label = f"{item['ref']} · {r.get('label')} = {r.get('value_m'):g} m" if r.get("value_m") is not None else f"{item['ref']} · {r.get('label')} (ambiguë)"
        png = annotated_crop(cropped[0], cropped[1], label)
        pil = Image.open(io.BytesIO(png))
        ratio = pil.size[1] / pil.size[0]
        width = min(W, 120 * mm)
        story.append(KeepTogether([RLImage(io.BytesIO(png), width=width, height=width * ratio),
                                   _p(f"{label} · origine : {r.get('origin')} · page {(r.get('page') or 0) + 1}", S, "muted")]))
        shown += 1
    if qty:
        story.append(Paragraph("Mesures et quantités", S["h2"]))
        story.append(_tbl([["Élément", "Localisation", "Formule / déductions", "Net", "État"]] + qty, [30 * mm, 26 * mm, 76 * mm, 22 * mm, 28 * mm], S))
        story.append(_p("Quantités séparées des prix. Les lignes non confirmées ne sont pas totalisées.", S, "muted"))
    if rows or findings:
        story.append(Spacer(1, 4))
        story.append(_p(CONTROL_MENTION, S, "muted"))
    for sol in solutions:
        story.append(PageBreak())
        story.append(Paragraph("Solutions techniques comparées", S["h2"]))
        story.append(_p(f"Problème : {sol.get('problem', '')}", S, "body"))
        if sol.get("facts"):
            story.append(_p("Faits : " + " · ".join(sol["facts"]), S, "body"))
        if sol.get("hypotheses"):
            story.append(_p("Hypothèses : " + " · ".join(sol["hypotheses"]), S, "body"))
        orow = [["Option", "Adéquation", "Conditions", "Avantages / limites", "Sources"]]
        for o in sol.get("options", []):
            srcs = [f"{s.get('title') or s.get('url')} ({s.get('status')})" for s in o.get("sources", [])] or ["aucune source"]
            orow.append([_p(o.get("name", ""), S), _p(f"{o.get('suitability', '')} · {o.get('evidence_level', '')}", S), _p(" · ".join(o.get("conditions") or []) or "—", S),
                         _p(" / ".join([*(o.get("advantages") or []), *(o.get("limitations") or [])]) or "—", S), _p(" ; ".join(srcs), S)])
        story.append(_tbl(orow, [30 * mm, 30 * mm, 40 * mm, 46 * mm, 36 * mm], S))
        story.append(Paragraph(_e("Recommandation : " + (sol.get("recommended_option") or "options conditionnelles — donnée décisive manquante : "
                                                           + ", ".join(sol.get("missing_decisive_data") or []))), S["concl"]))
        if sol.get("justification"):
            story.append(_p("Justification : " + sol["justification"], S, "body"))
        if sol.get("required_verifications"):
            story.append(_p("Vérifications requises avant exécution : " + " · ".join(sol["required_verifications"]), S, "body"))
        if sol.get("next_action"):
            story.append(_p("Prochaine étape : " + sol["next_action"], S, "body"))
        story.append(_p(SOLUTION_MENTION, S, "muted"))
    if sources:
        story.append(Paragraph("Sources consultées", S["h2"]))
        srow = [["Titre (lien)", "Entité", "Version / dates", "Consultée le", "Statut", "Affirmation vérifiée"]]
        for s in sources:
            dates = ", ".join(s.get("dates_found") or [])
            srow.append([_link(s.get("url", ""), s.get("title") or s.get("url", ""), S), _p(s.get("entity") or "", S),
                         _p(" · ".join(x for x in (s.get("version") and f"v{s['version']}", dates) if x) or "non indiquée", S),
                         _p((s.get("consulted_at") or "")[:16].replace("T", " "), S),
                         _p("Passage probant" if s.get("verified") else "Consultée sans passage probant", S), _p(s.get("claim") or "", S)])
        story.append(_tbl(srow, [52 * mm, 26 * mm, 26 * mm, 22 * mm, 24 * mm, 32 * mm], S))
    if not (rows or findings or qty or solutions or sources):
        story.append(_p("Aucun calcul, constatation ou source structurés n'a encore été produit dans cette conversation.", S, "body"))
    footer = _footer(company, conv.get("title", ""), lang)
    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    return buf.getvalue()
