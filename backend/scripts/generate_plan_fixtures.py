"""Gera fixtures mínimos para o smoke test do pipeline plantas.

- /app/backend/tests/fixtures/plan_test.dxf : retângulo 12×15m + texto "Área: 180 m²" + cota
- /app/backend/tests/fixtures/plan_test.pdf : planta textual simples com áreas/dimensões

Executar: `cd /app/backend && python -m scripts.generate_plan_fixtures`
"""
from __future__ import annotations

from pathlib import Path


FIXTURES_DIR = Path(__file__).resolve().parent.parent / "tests" / "fixtures"


def build_dxf() -> Path:
    """Cria DXF com layer TESTE, retângulo 12×15m via LWPOLYLINE, cota linear + texto de área."""
    import ezdxf

    doc = ezdxf.new(dxfversion="R2010", setup=True)
    doc.header["$INSUNITS"] = 6  # metros
    msp = doc.modelspace()

    doc.layers.add(name="PAREDES", color=1)
    doc.layers.add(name="TEXTO", color=2)
    doc.layers.add(name="COTAS", color=3)

    # Retângulo 12 x 15 m (área = 180 m²)
    pts = [(0, 0), (12, 0), (12, 15), (0, 15), (0, 0)]
    msp.add_lwpolyline(pts, dxfattribs={"layer": "PAREDES", "closed": True})

    # Divisões internas (mais entidades para o extractor)
    msp.add_line((6, 0), (6, 15), dxfattribs={"layer": "PAREDES"})
    msp.add_line((0, 7.5), (12, 7.5), dxfattribs={"layer": "PAREDES"})

    # Texto identificativo
    msp.add_text(
        "Planta baixa - Área total: 180 m²",
        dxfattribs={"layer": "TEXTO", "height": 0.5},
    ).set_placement((0.5, 15.5))
    msp.add_text("Sala 90 m²", dxfattribs={"layer": "TEXTO", "height": 0.3}).set_placement((1, 8))
    msp.add_text("Quartos 90 m²", dxfattribs={"layer": "TEXTO", "height": 0.3}).set_placement((1, 3))

    # Cotas (dimension) linear
    dim = msp.add_linear_dim(
        base=(0, -1),
        p1=(0, 0),
        p2=(12, 0),
        dimstyle="EZDXF",
        override={"dimtxt": 0.3},
    )
    dim.render()

    out = FIXTURES_DIR / "plan_test.dxf"
    doc.saveas(str(out))
    return out


def build_pdf() -> Path:
    """Cria PDF textual simples (reportlab) com dados de planta."""
    from reportlab.pdfgen import canvas
    from reportlab.lib.pagesizes import A4

    out = FIXTURES_DIR / "plan_test.pdf"
    c = canvas.Canvas(str(out), pagesize=A4)
    c.setFont("Helvetica-Bold", 16)
    c.drawString(72, 780, "Planta baixa — Habitação T3")
    c.setFont("Helvetica", 11)
    lines = [
        "",
        "Área bruta: 180,00 m²",
        "Área útil: 165,00 m²",
        "Pé direito: 2,70 m",
        "",
        "Divisões:",
        "  · Sala comum: 45,00 m²",
        "  · Cozinha: 15,00 m²",
        "  · Quarto 1 (suite): 22,00 m²",
        "  · Quarto 2: 14,00 m²",
        "  · Quarto 3: 12,00 m²",
        "  · WC 1: 6,00 m²",
        "  · WC 2: 4,00 m²",
        "  · Corredor: 8,00 m²",
        "",
        "Materiais previstos:",
        "  · Paredes exteriores em tijolo 30, isoladas com XPS 60mm",
        "  · Paredes divisórias em pladur 100mm com lã mineral",
        "  · Pavimento cerâmico 60x60 nas zonas técnicas",
        "  · Pavimento em madeira de carvalho nos quartos e sala",
        "  · Pintura branca em todas as paredes interiores",
        "",
        "Vãos:",
        "  · Portas interiores: 8 unidades",
        "  · Janelas de correr em alumínio: 6 unidades",
        "  · Porta de entrada blindada: 1 unidade",
        "",
        "Estimativa preliminar: € 145 000 - 165 000 (base de custo).",
    ]
    y = 760
    for ln in lines:
        c.drawString(72, y, ln)
        y -= 15
    c.showPage()
    c.save()
    return out


def main() -> None:
    FIXTURES_DIR.mkdir(parents=True, exist_ok=True)
    dxf_path = build_dxf()
    pdf_path = build_pdf()
    print(f"DXF: {dxf_path} ({dxf_path.stat().st_size} bytes)")
    print(f"PDF: {pdf_path} ({pdf_path.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
