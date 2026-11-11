"""Run the CLT engines on real drawings and write a PDF test report.

Usage:
    python -m scripts.clt_engines_report --pdf "Home A.en.pdf" \
        --image "RDC=terreo.jpg" --image "+1=pavimento_superior.jpg" --image-ppm 20.2 \
        --out /path/to/folder

Outputs in --out: the report, the Home A IFC, fabrication DXF and PDF.
Every figure in the report comes from the engines on the given files; the
reviewed Home A take-off (home_a_takeoff) is the reference for the generic
PDF reader.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import time
from datetime import datetime, timezone
from pathlib import Path

import fitz
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Image, KeepTogether, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from shapely.geometry import box

from bim_studio import clt_drawings, clt_ifc, clt_nesting, clt_pdf_walls, clt_raster_walls, clt_walls
from bim_studio import home_a_takeoff as reviewed
from bim_studio.clt_pdf import inspect_pdf

FONT = "Helvetica"
for path in ("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",):
    if Path(path).exists():
        pdfmetrics.registerFont(TTFont("DejaVu", path))
        pdfmetrics.registerFont(TTFont("DejaVu-Bold", path.replace("Sans.ttf", "Sans-Bold.ttf")))
        FONT = "DejaVu"
styles = getSampleStyleSheet()
H1 = ParagraphStyle("h1", parent=styles["Heading1"], fontName=FONT + ("-Bold" if FONT != "Helvetica" else ""), fontSize=16)
H2 = ParagraphStyle("h2", parent=styles["Heading2"], fontName=H1.fontName, fontSize=12.5, spaceBefore=10)
P = ParagraphStyle("p", parent=styles["BodyText"], fontName=FONT, fontSize=9, leading=12)
SMALL = ParagraphStyle("s", parent=P, fontSize=7.5, leading=9.5)
OK, FAIL, WARN = colors.HexColor("#1b7f3b"), colors.HexColor("#b3261e"), colors.HexColor("#9a6700")


def table(rows, widths=None, status_col=None):
    data = [[Paragraph(str(c), SMALL) for c in r] for r in rows]
    t = Table(data, colWidths=widths, repeatRows=1)
    style = [("GRID", (0, 0), (-1, -1), 0.3, colors.grey), ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#eeeeee")),
             ("VALIGN", (0, 0), (-1, -1), "TOP")]
    if status_col is not None:
        for i, r in enumerate(rows[1:], 1):
            v = str(r[status_col])
            colour = OK if v.startswith("PASSOU") else FAIL if v.startswith("FALHOU") else WARN
            style.append(("TEXTCOLOR", (status_col, i), (status_col, i), colour))
    t.setStyle(TableStyle(style))
    return t


def overlay_pdf(page, markers, reference=None, dpi=60):
    """Page render with detected walls (red) and reviewed walls missed by the reader (blue)."""
    pix = page.get_pixmap(dpi=dpi)
    doc = fitz.open()
    out = doc.new_page(width=pix.width, height=pix.height)
    out.insert_image(out.rect, pixmap=pix)
    for m in markers:
        x0, y0, x1, y1 = m["rect"]
        out.draw_rect(fitz.Rect(x0 * pix.width, y0 * pix.height, x1 * pix.width, y1 * pix.height),
                      color=(1, 0, 0), width=1.6)
    for m in reference or []:
        x0, y0, x1, y1 = m["rect"]
        out.draw_rect(fitz.Rect(x0 * pix.width, y0 * pix.height, x1 * pix.width, y1 * pix.height),
                      color=(0, 0, 1), width=1.6)
    return out.get_pixmap(dpi=110).tobytes("png")


def overlay_image(path, bands):
    import cv2

    im = cv2.imread(str(path))
    for a, b, c, d in bands:
        cv2.rectangle(im, (a, b), (c - 1, d - 1), (0, 0, 255), 2)
    ok, png = cv2.imencode(".png", im)
    return png.tobytes()


def img(png, width_mm=180):
    reader = Image(io.BytesIO(png))
    ratio = reader.imageHeight / reader.imageWidth
    reader.drawWidth, reader.drawHeight = width_mm * mm, width_mm * mm * ratio
    if reader.drawHeight > 200 * mm:
        reader.drawHeight, reader.drawWidth = 200 * mm, 200 * mm / ratio
    return reader


def status(passed):
    return "PASSOU" if passed else "FALHOU"


def run(pdf_path, images, ppm, out, screenshot=None):
    out.mkdir(parents=True, exist_ok=True)
    story, tests = [], []
    started = time.time()
    data = Path(pdf_path).read_bytes()
    sha = hashlib.sha256(data).hexdigest()
    report = inspect_pdf(data)
    heights = {k: v["height_m"] for k, v in (report.get("estimate_extras") or {}).get("floors", {}).items()}
    doc = fitz.open(stream=data, filetype="pdf")
    floors, comparisons, overlays = [], [], []
    for number, name in ((2, "RDC"), (3, "+1")):
        page = doc[number - 1]
        _, ref_markers, _ = reviewed._wall_geometry(page)
        ref = [m for m in ref_markers if "length_m" in m]
        t0 = time.time()
        found = clt_pdf_walls.detect(data, number, height_m=heights[name], scale=50)
        elapsed = time.time() - t0
        boxes = [box(*m["rect"]) for m in found["marcadores"]]
        missed = [m for m in ref if not any(b.intersection(box(*m["rect"])).area > .5 * min(b.area, box(*m["rect"]).area)
                                            for b in boxes)]
        extra = [m for m, b in zip(found["marcadores"], boxes)
                 if not any(box(*r["rect"]).intersection(b).area > .5 * min(b.area, box(*r["rect"]).area) for r in ref)]
        ref_len = sum(m["length_m"] for m in ref)
        gen_len = found["analise"]["metodos"]["eixos_desenhados_m"]
        err = abs(gen_len - ref_len) / ref_len * 100
        comparisons.append([name, len(ref), len(found["paredes"]), len(missed), len(extra), f"{ref_len:.3f}",
                            f"{gen_len:.3f}", f"{err:.2f} %", found["tracejados_medidos"],
                            status(not missed and not extra and err <= 2)])
        tests.append((f"Leitor PDF genérico · {name} · paredes encontradas vs take-off revisto",
                      status(not missed and not extra), f"{len(found['paredes'])}/{len(ref)} paredes, {len(missed)} em falta, "
                                                       f"{len(extra)} a mais, {elapsed:.1f} s"))
        tests.append((f"Leitor PDF genérico · {name} · comprimento dentro de 2 %", status(err <= 2), f"erro {err:.2f} %"))
        overlays.append((name, overlay_pdf(page, found["marcadores"], missed)))
        walls = [clt_walls.WallAxis(**w) for w in found["paredes"]]
        floors.append((name, 0.0 if name == "RDC" else heights["RDC"] + 0.24, walls, found))

    analyses = []
    for name, elevation, walls, found in floors:
        a = found["analise"]
        analyses.append((name, elevation, walls, a))
        v = a["verificacao_volume"]
        tests.append((f"Rede de paredes · {name} · volume das peças vs união das plantas (GEOS)", status(v["passed"]),
                      f"{a['metodos']['volume_pecas_m3']:.4f} vs {a['metodos']['volume_uniao_planta_m3']:.4f} m³"))
    pieces = [p for _, _, _, a in analyses for p in clt_nesting.pieces_from_walls(a)]
    t0 = time.time()
    nest_fixed = clt_nesting.plan(clt_nesting.NestingInput(pieces=pieces, time_limit_s=10))
    nest_var = clt_nesting.plan(clt_nesting.NestingInput(pieces=pieces, time_limit_s=10, variable_width=True))
    nest_time = time.time() - t0
    feasible = all(b["comprimento_usado_m"] <= 18 + 1e-9 for g in nest_fixed["grupos"] for b in g["layout"])
    placed = sorted(p["id"] for g in nest_fixed["grupos"] for b in g["layout"] for p in b["pecas"])
    tests.append(("Plano de corte · todas as peças colocadas uma vez, dentro de 18 × 3,5 m",
                  status(feasible and placed == sorted(p.id for p in pieces)), f"{len(placed)} peças, {nest_time:.1f} s"))
    tests.append(("Plano de corte · CP-SAT nunca pior que a heurística",
                  status(all(g["paineis"] <= g["heuristica_paineis"] for g in nest_fixed["grupos"])),
                  "; ".join(f"{g['espessura_mm']:g} mm: {g['paineis']} painéis (heurística {g['heuristica_paineis']}, "
                            f"mínimo teórico {g['limite_inferior_paineis']}, {g['motor']})" for g in nest_fixed["grupos"])))
    staged = [(n, e, w, a["pecas"]) for n, e, w, a in analyses]
    ifc, check = clt_ifc.build(staged, project_name="Home A · teste motores")
    (out / "HomeA-paredes-CLT.ifc").write_bytes(ifc)
    tests.append(("Modelo IFC · volume OpenCascade vs analítico, peça a peça (≤ 2 %)", status(check["passed"]),
                  f"{check['volume_ifc_m3']:.4f} vs {check['volume_analitico_m3']:.4f} m³, "
                  f"{len(check['pecas'])} peças, erro máx. {max(r['erro_percent'] or 0 for r in check['pecas']):.4f} %"))
    drawings = clt_drawings.build([(n, w, p) for n, _, w, p in staged], nest_fixed, title="Home A")
    (out / "HomeA-fabrico.dxf").write_bytes(drawings["dxf"])
    (out / "HomeA-fabrico.pdf").write_bytes(drawings["pdf"])
    with fitz.open(stream=drawings["pdf"], filetype="pdf") as d:
        pages = len(d)
    tests.append(("Desenhos de fabrico · DXF legível e PDF com uma folha por grupo", status(pages == len(drawings["folhas"])),
                  f"{pages} folhas PDF, DXF {len(drawings['dxf']) // 1024} kB"))

    raster = []
    for name, path in images:
        found = clt_raster_walls.detect(Path(path).read_bytes(), pixels_per_metre=ppm, height_m=3.0, grey=(35, 115),
                                        min_thickness_m=0.1)
        raster.append((name, path, found))
        tests.append((f"Leitor de imagem · {name} · leitura concluída e volumes coerentes",
                      "ESTIMATIVA" if found.get("analise", {}).get("verificacao_volume", {}).get("passed") else "FALHOU",
                      f"{len(found['paredes'])} bandas; {found['incerteza']}"))

    # ---- Report ----
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    story += [Paragraph("ConstruPilot CLT · Relatório de testes dos motores", H1),
              Paragraph(f"Gerado em {now}. Ficheiro Home A: SHA-256 {sha[:16]}…, a mesma revisão do take-off revisto. "
                        "Todos os números abaixo saem dos motores aplicados aos ficheiros enviados; nada foi escrito à mão.", P),
              Spacer(1, 4 * mm), Paragraph("Resumo dos testes", H2),
              table([["Teste", "Resultado", "Detalhe"]] + [list(t) for t in tests], [80 * mm, 20 * mm, 75 * mm], 1),
              Spacer(1, 3 * mm),
              Paragraph("O que não foi verificado: testes no Chrome em produção (o acesso ao PC não está disponível a "
                        "partir do projeto), aprovação dos desenhos por um engenheiro, e as alturas por troço (usa-se a "
                        "altura estrutural máxima de cada piso, medida no corte). A casa das imagens parece ser de betão: "
                        "serve apenas para testar o leitor de imagem.", P),
              Paragraph("1 · Leitor genérico de PDF vetorial vs take-off revisto (Home A)", H2),
              Paragraph("O take-off revisto usa números de traçado escolhidos à mão para este ficheiro. O leitor genérico "
                        "não usa nenhum: lê a escala 1:50, junta os contornos pela cor da legenda CLT, aceita só larguras "
                        "nominais (±3 mm) e lê as paredes só tracejadas. Vermelho = detetado; azul = parede revista que o "
                        "leitor falhou.", P),
              table([["Piso", "Paredes revistas", "Detetadas", "Em falta", "A mais", "Comprimento revisto (m)",
                       "Comprimento lido (m)", "Erro", "Só tracejado", "Resultado"]] + comparisons,
                    [12 * mm, 16 * mm, 15 * mm, 13 * mm, 12 * mm, 22 * mm, 22 * mm, 14 * mm, 16 * mm, 20 * mm], 9),
              Paragraph("A diferença de comprimento vem da escala: o take-off revisto calibra-a numa cota do desenho, "
                        "o leitor genérico usa a escala nominal 1:50 impressa.", SMALL)]
    for name, png in overlays:
        story += [Spacer(1, 2 * mm), KeepTogether([Paragraph(f"Home A · {name}", P), img(png, 150)])]
    story += [PageBreak(), Paragraph("2 · Rede de paredes: juntas e contagem dupla", H2),
              Paragraph("As peças de produção resolvem as juntas: a parede mais comprida passa, a outra encosta. "
                        "O volume é verificado por dois caminhos independentes.", P)]
    rows = [["Piso", "Altura (m)", "Paredes", "Juntas L/T/X", "Comprimento peças (m)", "Volume bruto (m³)",
             "Contagem dupla evitada (m³)", "Verificação"]]
    for name, _, walls, a in analyses:
        kinds = {k: sum(1 for j in a["juntas"] if j["tipo"] == k) for k in ("L", "T", "X")}
        rows.append([name, f"{walls[0].height_m:.3f}", len(walls), f"{kinds['L']}/{kinds['T']}/{kinds['X']}",
                     f"{a['metodos']['pecas_producao_m']:.3f}", f"{a['totais']['volume_bruto_m3']:.3f}",
                     f"{a['contagem_dupla_evitada_m3']:.4f}", status(a["verificacao_volume"]["passed"])])
    story += [table(rows, None, 7),
              Paragraph("Altura de cada piso: maior pé-direito acabado cotado + pavimento + teto falso medidos no corte "
                        "(motor existente). Paredes sem vãos deduzidos: os vãos do Home A estão no estudo completo, "
                        "não nas paredes.", SMALL),
              Paragraph("3 · Plano de corte nos painéis de prensa (OR-Tools CP-SAT)", H2),
              Paragraph("Formato Rezult: comprimento ≤ 18,00 m, largura ≤ 3,50 m (clt-rezult.com, lido 2026-11-11). "
                        "Corte de serra 10 mm (hipótese editável). Duas variantes: largura fixa 3,50 m e largura à medida.", P)]
    rows = [["Variante", "Espessura", "Painéis", "Mínimo teórico", "Motor", "Volume peças (m³)", "Volume painéis (m³)",
             "Desperdício"]]
    for label, nest in (("largura fixa 3,50 m", nest_fixed), ("largura à medida", nest_var)):
        for g in nest["grupos"]:
            rows.append([label, f"{g['espessura_mm']:g} mm {g['camadas']}c", g["paineis"], g["limite_inferior_paineis"],
                         g["motor"] + (" (ótimo provado)" if g["otimo_provado"] else ""), f"{g['volume_pecas_m3']:.3f}",
                         f"{g['volume_paineis_m3']:.3f}", f"{g['desperdicio_percent']:.1f} %"])
    story += [table(rows), Paragraph(
        f"Com largura fixa o desperdício é {nest_fixed['total']['desperdicio_percent']:.1f} %; com largura à medida "
        f"{nest_var['total']['desperdicio_percent']:.1f} %. A diferença é a faixa entre a altura da parede e os 3,50 m "
        "da prensa: confirmar com a Rezult se a largura é produzida à medida.", P)]
    story += [Paragraph("4 · Modelo 3D IFC e verificação OpenCascade", H2),
              Paragraph(f"{check['motor']}. Cada peça é um IfcWall com camadas CLT, quantidades Qto_WallBaseQuantities e "
                        "a origem de cada valor. O volume de cada sólido é recalculado pela geometria 3D.", P)]
    rows = [["Peça", "Volume IFC (m³)", "Volume analítico (m³)", "Erro", "Resultado"]]
    rows += [[r["peca"], f"{r['volume_ifc_m3']:.5f}", f"{r['volume_analitico_m3']:.5f}", f"{r['erro_percent'] or 0:.4f} %",
              status(r["passed"])] for r in check["pecas"]]
    story += [table(rows, [40 * mm, 30 * mm, 35 * mm, 25 * mm, 25 * mm], 4)]
    story += [PageBreak(), Paragraph("5 · Leitor de imagens (segunda casa, JPG)", H2),
              Paragraph(f"Escala medida na barra gráfica: 0 m em x=82 px e 10 m em x=284 px, logo {ppm:.1f} px/m "
                        f"(1 píxel ≈ {1000 / ppm:.0f} mm). Uma imagem não tem vetores: cada medida tem ±1 píxel de "
                        "incerteza, por isso o resultado é sempre estimativa e não cumpre o limite de 2 %. Vidros e "
                        "caixilhos desenhados a traço fino não são lidos como parede. Pilares e blocos mais largos que "
                        "50 cm são excluídos.", P)]
    for name, path, found in raster:
        a = found.get("analise", {})
        story += [Paragraph(f"{name}: {len(found['paredes'])} bandas, eixos {a.get('metodos', {}).get('eixos_desenhados_m', 0):.1f} m, "
                            f"peças {a.get('metodos', {}).get('pecas_producao_m', 0):.1f} m, "
                            f"volume a 3,00 m de altura {a.get('totais', {}).get('volume_bruto_m3', 0):.1f} m³ (estimativa).", P),
                  img(overlay_image(path, found["bandas_px"]), 150)]
    if screenshot:
        story += [PageBreak(), Paragraph("6 · Página CLT no browser (teste local)", H2),
                  Paragraph("Separador \"Juntas, corte, 3D e fabrico\" num Chromium local, contra a API real: leitura das "
                            "páginas 2 e 3 do Home A, cálculo, e descarga do IFC e dos desenhos PDF, sem erros na consola. "
                            "Sem os estilos da aplicação; não é o teste em produção.", P),
                  img(Path(screenshot).read_bytes(), 170)]
    story += [PageBreak(), Paragraph(f"{7 if screenshot else 6} · Software open-source usado e licenças", H2), table([
        ["Biblioteca", "Licença", "Uso na ConstruPilot", "Forma de uso"],
        ["Shapely / GEOS", "BSD-3 / LGPL-2.1", "Plantas, uniões, juntas, contagem dupla", "dependência (já instalada)"],
        ["OR-Tools CP-SAT (Google)", "Apache-2.0", "Plano de corte dos painéis", "dependência (já instalada)"],
        ["IfcOpenShell + OpenCascade", "LGPL-3.0 / LGPL-2.1", "Modelo IFC4 e verificação de volumes 3D", "dependência (já instalada)"],
        ["ezdxf", "MIT", "Desenhos DXF de fabrico com cotas", "dependência (já instalada)"],
        ["Matplotlib", "PSF/BSD", "PDF dos desenhos", "dependência (já instalada)"],
        ["OpenCV", "Apache-2.0", "Leitura de plantas em imagem", "dependência (já instalada)"],
        ["PyMuPDF", "AGPL-3.0 ou comercial", "Leitura de PDF (já existia)", "ATENÇÃO: num SaaS a AGPL obriga a publicar o código "
                                                                         "ou a ter licença comercial Artifex"],
        ["FreeCAD, Bonsai/BlenderBIM, LibreCAD, QCAD, LibreDWG", "LGPL/GPL", "Avaliados", "não copiados: GPL não pode entrar no produto; "
                                                                                   "DWG continua via Autodesk APS"],
    ], [38 * mm, 28 * mm, 50 * mm, 59 * mm]),
        Spacer(1, 3 * mm), Paragraph(f"Tempo total dos testes: {time.time() - started:.0f} s.", SMALL)]
    pdf = SimpleDocTemplate(str(out / "Relatorio-testes-motores-CLT.pdf"), pagesize=A4, leftMargin=15 * mm,
                            rightMargin=15 * mm, topMargin=14 * mm, bottomMargin=14 * mm,
                            title="ConstruPilot CLT · Relatório de testes dos motores")
    pdf.build(story)
    return tests


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--pdf", required=True)
    parser.add_argument("--image", action="append", default=[], help="NOME=caminho.jpg")
    parser.add_argument("--image-ppm", type=float, default=20.2)
    parser.add_argument("--out", required=True)
    parser.add_argument("--screenshot")
    args = parser.parse_args()
    images = [tuple(i.split("=", 1)) for i in args.image]
    for t in run(args.pdf, images, args.image_ppm, Path(args.out), args.screenshot):
        print(" | ".join(map(str, t)))


if __name__ == "__main__":
    main()
