"""Converte /app/docs/aurora_master_spec.md → PDF via WeasyPrint.

Corre com: `cd /app && python -m backend.scripts.build_aurora_pdf`
ou: `cd /app/backend && python -m scripts.build_aurora_pdf`
"""
from __future__ import annotations

from pathlib import Path

import markdown as md
from weasyprint import CSS, HTML


DOCS_DIR = Path("/app/docs")
MD_PATH = DOCS_DIR / "aurora_master_spec.md"
PDF_PATH = DOCS_DIR / "aurora_master_spec.pdf"

CSS_STYLE = """
@page {
    size: A4;
    margin: 2cm 2cm 2cm 2cm;
    @bottom-right {
        content: "Página " counter(page) " de " counter(pages);
        font-size: 9pt;
        color: #666;
    }
    @top-left {
        content: "Aurora Master Spec · v1.0";
        font-size: 9pt;
        color: #666;
    }
}

body {
    font-family: "Helvetica", "Arial", sans-serif;
    font-size: 10pt;
    line-height: 1.45;
    color: #222;
}

h1 {
    font-size: 22pt;
    color: #0f172a;
    border-bottom: 3px solid #0f172a;
    padding-bottom: 6px;
    margin-top: 24pt;
    page-break-before: always;
}
h1:first-of-type { page-break-before: auto; }

h2 {
    font-size: 15pt;
    color: #1e293b;
    border-bottom: 1px solid #cbd5e1;
    padding-bottom: 3px;
    margin-top: 18pt;
}

h3 {
    font-size: 12pt;
    color: #334155;
    margin-top: 12pt;
}

h4 {
    font-size: 11pt;
    color: #475569;
    margin-top: 10pt;
}

p, li { orphans: 3; widows: 3; }

code {
    font-family: "Courier New", monospace;
    font-size: 9pt;
    background: #f1f5f9;
    padding: 1px 4px;
    border-radius: 2px;
}

pre {
    background: #0f172a;
    color: #e2e8f0;
    padding: 10px 12px;
    border-radius: 4px;
    font-size: 8.5pt;
    line-height: 1.35;
    overflow-x: auto;
    page-break-inside: avoid;
}

pre code {
    background: transparent;
    color: inherit;
    padding: 0;
}

table {
    width: 100%;
    border-collapse: collapse;
    margin: 8pt 0;
    font-size: 9pt;
    page-break-inside: avoid;
}

th {
    background: #0f172a;
    color: white;
    padding: 5px 8px;
    text-align: left;
    border: 1px solid #0f172a;
}

td {
    padding: 4px 8px;
    border: 1px solid #cbd5e1;
    vertical-align: top;
}

tr:nth-child(even) td { background: #f8fafc; }

blockquote {
    border-left: 4px solid #f59e0b;
    background: #fef3c7;
    padding: 8px 12px;
    margin: 8pt 0;
    color: #78350f;
    page-break-inside: avoid;
}

hr {
    border: none;
    border-top: 1px solid #cbd5e1;
    margin: 18pt 0;
}

a { color: #2563eb; text-decoration: none; }

ul, ol { margin: 4pt 0; padding-left: 20pt; }
li { margin: 1pt 0; }

.cover {
    page-break-after: always;
    text-align: center;
    padding-top: 6cm;
}
.cover h1 { border: none; font-size: 32pt; page-break-before: auto; }
.cover .subtitle { font-size: 14pt; color: #64748b; margin-top: 12pt; }
.cover .meta { margin-top: 4cm; font-size: 10pt; color: #64748b; }
"""


def build_pdf() -> None:
    if not MD_PATH.exists():
        raise FileNotFoundError(f"MD source não encontrado: {MD_PATH}")

    markdown_text = MD_PATH.read_text(encoding="utf-8")
    html_body = md.markdown(
        markdown_text,
        extensions=["extra", "tables", "fenced_code", "sane_lists", "toc"],
    )

    cover = """
    <div class="cover">
      <h1>Aurora Company API</h1>
      <div class="subtitle">Especificação Técnica Master · v1.0</div>
      <div class="meta">
        Emitido por Engenharia ConstruPilot<br>
        Fevereiro 2026<br>
        Confidencial · uso interno das partes contraentes
      </div>
    </div>
    """

    full_html = f"""<!DOCTYPE html>
<html lang="pt-PT">
<head>
  <meta charset="utf-8">
  <title>Aurora Master Spec v1.0</title>
</head>
<body>
{cover}
{html_body}
</body>
</html>"""

    HTML(string=full_html, base_url=str(DOCS_DIR)).write_pdf(
        target=str(PDF_PATH),
        stylesheets=[CSS(string=CSS_STYLE)],
    )
    size_kb = PDF_PATH.stat().st_size / 1024
    print(f"✅ PDF gerado: {PDF_PATH} ({size_kb:.1f} KB)")


if __name__ == "__main__":
    build_pdf()
