"""Documentos de demonstração pré-configurados (contas demo / Web Summit).

Gera, a partir de um caso fictício (cases/*.json), dois PDF que o utilizador pode « importar » no Assistente :
  - o projeto de arquitetura (plantas, cortes, alçados) — peças desenhadas de licenciamento ;
  - o estudo geotécnico (G2 / relatório geotécnico).
Cada PDF leva no campo /Subject a marca « construpilot-demo:<caso> ». Quando TODOS os PDF de um pedido trazem a
marca do mesmo caso, reader.read_building salta a leitura por IA e devolve o modelo exato do caso : resultado
imediato (segundos), sem custo de API, e sempre certo. Os PDF dizem claramente « exemplo fictício de demonstração ».

Linha de comandos :  python -m engines.bet_core.samples <pasta_saida> [caso]
"""
from __future__ import annotations

import copy
import io
import json
import sys
from pathlib import Path

from pypdf import PdfReader, PdfWriter

CASES = Path(__file__).with_name("cases")
MARK = "construpilot-demo:"
SAMPLES = {
    "moradia_pt_demo": {
        "country": "PT", "lang": "pt",
        "pc": "Projeto_arquitetura_Moradia_T3_DEMO.pdf",
        "g2": "Estudo_geotecnico_Moradia_T3_DEMO.pdf",
        "architect": "Atelier Exemplo Arquitetos",
    },
}
# peças desenhadas de licenciamento : (folha do motor, código, título PT)
_PC_SHEETS = [("GO-02", "ARQ-01", "PLANTA DO RÉS-DO-CHÃO"), ("GO-03", "ARQ-02", "PLANTA DO 1.º ANDAR"),
              ("GO-05", "ARQ-03", "CORTES A-A E B-B"), ("GO-06a", "ARQ-04", "ALÇADOS PRINCIPAL E POSTERIOR"),
              ("GO-06b", "ARQ-05", "ALÇADOS LATERAIS")]


def case(case_id: str) -> dict:
    return json.loads((CASES / f"{case_id}.json").read_text(encoding="utf-8"))


def _mark(pdf: bytes, case_id: str, title: str) -> bytes:
    r = PdfReader(io.BytesIO(pdf))
    w = PdfWriter()
    for p in r.pages:
        w.add_page(p)
    w.add_metadata({"/Title": title, "/Subject": MARK + case_id, "/Author": "ConstruPilot — exemplo fictício de demonstração"})
    buf = io.BytesIO()
    w.write(buf)
    return buf.getvalue()


def build_pc(case_id: str) -> bytes:
    """Projeto de arquitetura fictício (5 folhas A3) desenhado a partir do modelo do caso."""
    import tempfile

    from . import brand, draw, mep, pipeline, sheets, structure, timber
    s = SAMPLES[case_id]
    raw = case(case_id)
    m, _ = pipeline.validate(raw)
    r = structure.compute(m)
    tim = timber.compute(m, r["loads"])
    shs = {x.code: x for x in sheets.all_sheets(m, r, tim, mep.electrical(m), mep.plumbing(m))}
    out = []
    for src, code, title in _PC_SHEETS:
        if src in shs:
            sh = copy.copy(shs[src])
            sh.code, sh.title, sh.notes = code, title, ["Peça desenhada de licenciamento — EXEMPLO FICTÍCIO DE DEMONSTRAÇÃO."]
            sh.subtitle = "Projeto de arquitetura"
            out.append(sh)
    proj = dict(raw["project"], date="15/09/2026")
    with pipeline._RENDER_LOCK:
        brand.use({"company_name": s["architect"], "contact_line": "Gabinete fictício de demonstração"}, s["country"])
        try:
            with tempfile.TemporaryDirectory() as tmp:
                p = Path(tmp) / "pc.pdf"
                draw.render_pdf(out, p, proj, lang=s["lang"])
                data = p.read_bytes()
        finally:
            brand.use(None, "FR")
    return _mark(data, case_id, "Projeto de arquitetura — " + raw["project"]["name"])


def build_g2(case_id: str) -> bytes:
    """Relatório geotécnico fictício coerente com o bloco `geotech` do caso."""
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    from . import brand  # noqa: F401 — regista as fontes DV / DVB / TT
    raw = case(case_id)
    g, pj = raw["geotech"], raw["project"]
    h1 = ParagraphStyle("h1", fontName="TT", fontSize=17, leading=21, spaceAfter=6, textColor=colors.HexColor("#0E4D4A"))
    h2 = ParagraphStyle("h2", fontName="DVB", fontSize=11, leading=14, spaceBefore=10, spaceAfter=4)
    bd = ParagraphStyle("bd", fontName="DV", fontSize=9.5, leading=13.5)
    sm = ParagraphStyle("sm", fontName="DV", fontSize=8, leading=11, textColor=colors.HexColor("#666666"))
    wb = g.get("verified_widths_m", {})
    rows = [["Parâmetro", "Valor"],
            ["Camada de fundação", g["bearing_layer"]],
            ["Cota de base das fundações", f"{g['foundation_base_depth_m']:.2f} m abaixo do terreno natural".replace(".", ",")],
            ["Encastramento mínimo na camada", f"{g['anchorage_m']:.2f} m".replace(".", ",")],
            ["Tensão admissível (ELS)", f"{g['q_els_kpa']} kPa"],
            ["Valor de cálculo da resistência (ELU)", f"{g['q_elu_kpa']} kPa"],
            ["Larguras verificadas", f"sapata corrida {wb.get('filante', 0.5):.2f} m · sapata isolada {wb.get('isolee', 0.8):.2f} m".replace(".", ",")],
            ["Assentamento estimado (B = 0,60 m)", f"{g['settlement_mm_B060']} mm"],
            ["Nível freático", g["water"]],
            ["Classe de exposição do betão em contacto com o solo", g["exposure_class_soil"]],
            ["Tipo de terreno (NP EN 1998-1)", pj.get("ground_type", "B")]]
    tb = Table([[Paragraph(str(a), bd), Paragraph(str(b), bd)] for a, b in rows], colWidths=[70 * mm, 100 * mm])
    tb.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#E6F0EF")), ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#9AA5A4")),
                            ("VALIGN", (0, 0), (-1, -1), "TOP")]))
    story = [Paragraph("ESTUDO GEOTÉCNICO", h1),
             Paragraph(f"{g['source']} — {pj['name']}", bd),
             Paragraph(f"Local : {pj['address']} · Data : 02/09/2026 · Gabinete de Geotecnia Exemplo (fictício)", sm),
             Paragraph("EXEMPLO FICTÍCIO DE DEMONSTRAÇÃO — sem valor contratual.", sm),
             Paragraph("1. Objeto", h2),
             Paragraph("Caracterização geotécnica do terreno para as fundações de uma moradia unifamiliar de dois pisos (R/C + 1.º andar), "
                       "estrutura em betão armado e alvenaria, cobertura em madeira.", bd),
             Paragraph("2. Trabalhos de prospeção", h2),
             Paragraph("Três sondagens à rotação com ensaios SPT a cada 1,5 m e dois ensaios de penetração dinâmica (DPSH) nos cantos "
                       "da implantação. Profundidade máxima atingida : 6,0 m.", bd),
             Paragraph("3. Zonamento geotécnico", h2),
             Paragraph("ZG3 (0,0 a 0,5 m) : terra vegetal e aterro — a remover. ZG2 (0,5 a 0,8 m) : saibro solto. "
                       f"ZG1 (abaixo de 0,8 m) : {g['bearing_layer']}, N(SPT) superior a 40 pancadas.", bd),
             Paragraph("4. Parâmetros recomendados para o projeto de fundações", h2), tb,
             Paragraph("5. Recomendações", h2),
             Paragraph("Fundações diretas por sapatas corridas sob as paredes e sapatas isoladas sob os pilares, apoiadas na zona ZG1. "
                       "Inspeção do fundo das escavações antes da betonagem, com betão de limpeza de 0,05 m. Drenagem periférica "
                       "recomendada junto às paredes enterradas.", bd)]
    buf = io.BytesIO()
    SimpleDocTemplate(buf, pagesize=A4, leftMargin=20 * mm, rightMargin=20 * mm, topMargin=18 * mm, bottomMargin=18 * mm,
                      title="Estudo geotécnico — " + pj["name"]).build(story)
    return _mark(buf.getvalue(), case_id, "Estudo geotécnico — " + pj["name"])


# empresa fictícia das contas demo (identidade aplicada ao processo, orçamentos, PDF) — nenhum dado real
DEMO_COMPANY = {
    "PT": {"company_name": "Construções Horizonte, Lda.", "contact_line": "Empresa fictícia de demonstração",
           "address": "Rua do Exemplo, 100", "postal_code": "4700-000", "city": "Braga",
           "phone": "+351 253 000 000", "company_email": "geral@construcoes-horizonte.example",
           "nif": "500 000 000", "alvara": "00000-PUB", "accent_color": "#0E4D4A", "accent2_color": "#C9A227",
           "footer_text": "Construções Horizonte, Lda. — empresa fictícia criada para demonstração do ConstruPilot. Sem valor contratual."},
}


def demo_logo_png(country: str = "PT") -> bytes:
    """Logótipo fictício (monograma geométrico + nome), gerado — nenhuma marca real."""
    from PIL import Image, ImageDraw, ImageFont
    c = DEMO_COMPANY[country]
    acc = tuple(int(c["accent_color"][i:i + 2], 16) for i in (1, 3, 5))
    gold = tuple(int(c["accent2_color"][i:i + 2], 16) for i in (1, 3, 5))
    W, H = 1200, 360
    im = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle((10, 10, 340, 340), radius=48, fill=acc)
    d.polygon([(60, 250), (175, 110), (290, 250)], fill=gold)            # telhado / horizonte
    d.rectangle((60, 262, 290, 282), fill=(255, 255, 255, 255))
    fonts = Path(__file__).with_name("fonts")
    big = ImageFont.truetype(str(fonts / "BarlowSemiCondensed_700Bold.ttf"), 120)
    sub = ImageFont.truetype(str(fonts / "Inter_500Medium.ttf"), 46)
    name = c["company_name"].split(",")[0].upper()
    first, _, rest = name.partition(" ")
    d.text((380, 70), first, font=big, fill=acc)
    d.text((380, 190), (rest or "") + "  ·  " + c["city"].upper(), font=sub, fill=(90, 98, 104, 255))
    buf = io.BytesIO()
    im.crop(im.getbbox()).save(buf, "PNG")
    return buf.getvalue()


def demo_branding(country: str = "PT") -> dict:
    """Campos a gravar como brand_* nas contas demo Pro / Pro Business (e logo_b64)."""
    import base64
    return {**DEMO_COMPANY[country], "logo_b64": "data:image/png;base64," + base64.b64encode(demo_logo_png(country)).decode()}


def build_all(case_id: str = "moradia_pt_demo") -> dict[str, bytes]:
    s = SAMPLES[case_id]
    return {s["pc"]: build_pc(case_id), s["g2"]: build_g2(case_id)}


def detect(docs: list[tuple[str, bytes]]) -> str | None:
    """Caso de demonstração se TODOS os PDF trazem a marca do mesmo caso ; senão None (leitura normal por IA)."""
    ids = set()
    for _, data in docs:
        try:
            subj = str((PdfReader(io.BytesIO(data)).metadata or {}).get("/Subject") or "")
        except Exception:  # noqa: BLE001
            return None
        if not subj.startswith(MARK):
            return None
        ids.add(subj[len(MARK):])
    if len(ids) == 1 and next(iter(ids)) in SAMPLES:
        return next(iter(ids))
    return None


def demo_model(case_id: str) -> dict:
    raw = case(case_id)
    raw.setdefault("_questions", [])
    return raw


if __name__ == "__main__":
    dest = Path(sys.argv[1] if len(sys.argv) > 1 else ".")
    dest.mkdir(parents=True, exist_ok=True)
    cid = sys.argv[2] if len(sys.argv) > 2 else "moradia_pt_demo"
    for fname, data in build_all(cid).items():
        (dest / fname).write_bytes(data)
        print(dest / fname, len(data))
    ctry = SAMPLES[cid]["country"]
    (dest / "logo_empresa_demo.png").write_bytes(demo_logo_png(ctry))
    (dest / "branding_empresa_demo.json").write_text(json.dumps(demo_branding(ctry), ensure_ascii=False), encoding="utf-8")
    print(dest / "logo_empresa_demo.png", dest / "branding_empresa_demo.json")
