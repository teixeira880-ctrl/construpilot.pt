"""Small auditable PDF/JSON package. No execution drawings or fabricated prices."""
import json
from pathlib import Path
from xml.sax.saxutils import escape

def write_pdf(path, title, result):
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    fonts = Path(__file__).resolve().parents[2] / "assets" / "fonts"
    if (fonts / "DejaVuSans.ttf").exists():
        if "CLTDejaVu" not in pdfmetrics.getRegisteredFontNames():
            pdfmetrics.registerFont(TTFont("CLTDejaVu", str(fonts / "DejaVuSans.ttf")))
        font = "CLTDejaVu"
    else:
        font = "Helvetica"
    styles = getSampleStyleSheet()
    for s in styles.byName.values():
        s.fontName = font
    story = [Paragraph(escape(title), styles["Title"]), Spacer(1, 12),
             Paragraph("PRELIMINARY / INPUT REVIEW REQUIRED - NOT FOR CONSTRUCTION", styles["Heading2"])]
    # Paragraphs per line avoid an unsplittable huge JSON block.
    for line in json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False).splitlines():
        story.append(Paragraph(escape(line) or " ", styles["BodyText"]))
    SimpleDocTemplate(str(path), title=title, leftMargin=42, rightMargin=42).build(story)

def save(out, result, raw=None):
    import zipfile
    out = Path(out); out.mkdir(parents=True, exist_ok=True)
    data = out / "CLT_UA_results.json"
    data.write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
    if raw is not None:
        (out / "CLT_UA_input.json").write_text(json.dumps(raw, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
    pdf = out / "CLT_UA_review.pdf"
    write_pdf(pdf, "ConstruPilot - CLT Ukraine", result)
    package = out / "CLT_UA_evidence.zip"
    with zipfile.ZipFile(package, "w", zipfile.ZIP_DEFLATED) as z:
        z.write(data, data.name)
        if raw is not None:
            z.write(out / "CLT_UA_input.json", "CLT_UA_input.json")
    return {"pdf": str(pdf), "zip": str(package)}
