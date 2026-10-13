"""Analysis report PDF — coherence check with proofs, assumptions, missing data; explicitly not a structural calculation note."""
import base64
import io
from datetime import datetime, timezone

from PIL import Image, ImageDraw
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer

from engines.pdf_takeoff import DARK, ORANGE, _story_header_branding, _styles
from engines.plan_cotes_pdf import _fit_image, _tbl

STATUS = {"to_verify": "a verificar", "provisional": "provisório (hipótese)", "validated": "validé", "undetermined": "não determinado", "rejected": "rejeté"}
DISCLAIMER = "Controlo de coerência e medição a partir dos elementos lidos na planta. Este relatório não constitui uma memória de cálculo estrutural; as dimensões em falta ou supostas são listadas e devem ser confirmadas antes da execução."


def _annotated(page: dict, elements: list[dict]) -> bytes | None:
    b64 = page.get("image_png_b64")
    if not b64:
        return None
    im = Image.open(io.BytesIO(base64.b64decode(b64))).convert("RGB")
    d = ImageDraw.Draw(im, "RGBA")
    for e in elements:
        pts = (e.get("geometry") or {}).get("points_px")
        if not pts or len(pts) < 3:
            continue
        col = (37, 99, 235, 60) if e["type"] == "dalle" else (5, 150, 105, 0)
        d.polygon([tuple(p) for p in pts], fill=col if e["type"] == "dalle" else None, outline=(5, 150, 105, 255) if e["type"] == "mur" else (37, 99, 235, 255), width=4)
        if e["type"] == "dalle":
            cx, cy = sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts)
            d.text((cx, cy), e["room_name"], fill=(30, 58, 138, 255))
    out = io.BytesIO()
    im.save(out, "PNG")
    return out.getvalue()


def _p(text, S, style="body"):
    return Paragraph(str(text).replace("&", "&amp;").replace("<", "&lt;"), S[style])


def build_analysis_report(plan: dict, analysis: dict, elements: list[dict], lines: list[dict], overrides: list[dict], pages: list[dict], branding: dict | None) -> bytes:
    S = _styles()
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=14 * mm, rightMargin=14 * mm, topMargin=14 * mm, bottomMargin=14 * mm, title=f"Rapport d'analyse — {plan.get('filename')}")
    story = []
    _story_header_branding(story, branding, S)
    story += [_p(f"Relatório de análise rastreável — {plan.get('filename') or plan['plan_id']}", S, "h1"),
              _p(f"Revisão {analysis.get('revision')} · regras {analysis.get('rules_version')} · gerado em {datetime.now(timezone.utc).strftime('%d/%m/%Y %H:%M')} UTC · {len(elements)} trabalhos · {len(lines)} lignes"
                 + (" · fonte DXF lida" if analysis.get("has_dxf") else ""), S, "muted"),
              Spacer(1, 4), _p(DISCLAIMER, S, "muted"), Spacer(1, 8)]
    stats = {k: sum(1 for q in lines if q["status"] == k) for k in STATUS}
    story.append(_tbl([["Estado", "Linhas"]] + [[STATUS[k], str(v)] for k, v in stats.items() if v], [70 * mm, 30 * mm], S))
    story.append(Spacer(1, 8))
    if analysis.get("missing"):
        story.append(_p("Informações em falta e hipóteses declaradas", S, "h2"))
        for m in analysis["missing"]:
            story.append(_p(("[hipótese] " if m.get("covered_by_assumption") else "[manquant] ") + m["message"], S, "muted"))
        story.append(Spacer(1, 6))
    if overrides:
        story.append(_p("Hipóteses (visíveis, revisíveis)", S, "h2"))
        story.append(_tbl([["Artigo", "Altura", "Espessura", "Motivo", "Par", "Le"]] + [[next((e["label"] for e in elements if e["element_id"] == o["element_id"]), o["element_id"]), o.get("hauteur_m") or "—", o.get("epaisseur_m") or "—", o.get("reason") or "", o.get("by") or "", (o.get("at") or "")[:10]] for o in overrides],
                          [45 * mm, 18 * mm, 18 * mm, 55 * mm, 30 * mm, 16 * mm], S))
        story.append(Spacer(1, 6))
    if analysis.get("conflicts"):
        story.append(_p("Conflitos entre validações e recálculo", S, "h2"))
        for c in analysis["conflicts"]:
            story.append(_p(f"{c['designation']} : validado {c['previous']} par {c['validated_by']}, recalculado {c['new']}", S, "muted"))
    for pg in pages:
        png = _annotated(pg, [e for e in elements if e.get("page_index") == pg.get("index", 0) and e.get("source") != "dxf"])
        if png:
            story += [PageBreak(), _p(f"Planta anotada — página {pg.get('index', 0) + 1} (azul: lajes, verde: paredes)", S, "h2"), _fit_image(png, 180 * mm, 210 * mm)]
    story.append(PageBreak())
    story.append(_p("Quantidades por capítulo — fórmula, dados e proveniência", S, "h2"))
    for lot in sorted({q["lot"] for q in lines}):
        story.append(_p(lot, S, "kicker"))
        rows = [["Designação", "Fórmula / dados (proveniência)", "Net", "A enc.", "Estado"]]
        for q in [x for x in lines if x["lot"] == lot]:
            data = " ; ".join(f"{i['name']}={i.get('value') if i.get('value') is not None else '?'} {i.get('unit') or ''} ({i.get('source')})" for i in q["inputs"])
            ded = (" ; deduções: " + ", ".join(f"{d['name']} −{d['value']} {d['unit']}" for d in q["deductions"])) if q.get("deductions") else ""
            val = f" · validado por {q.get('validated_by')} le {(q.get('validated_at') or '')[:10]}" if q.get("validated_by") else ""
            rows.append([_p(q["designation"], S, "muted"), _p(f"{q['formula']} — {data}{ded}{val}{(' — ' + q['note']) if q.get('note') else ''}", S, "muted"),
                         f"{q['quantity_net'] if q['quantity_net'] is not None else '—'} {q['unit']}", f"{q['quantity_to_order'] if q['quantity_to_order'] is not None else '—'}", STATUS.get(q["status"], q["status"])])
        story.append(_tbl(rows, [42 * mm, 88 * mm, 20 * mm, 14 * mm, 18 * mm], S))
        story.append(Spacer(1, 6))
    story += [Spacer(1, 10), _p(DISCLAIMER, S, "muted")]
    doc.build(story)
    return buf.getvalue()


__all__ = ["DARK", "ORANGE", "build_analysis_report", "colors"]
