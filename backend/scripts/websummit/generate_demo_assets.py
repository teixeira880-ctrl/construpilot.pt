"""Gera os 6 ficheiros estáticos da demo Moradia Martins para o SW WebSummit.

Chama **os motores reais** (`engines.bet_core.samples` + `engines.bet_core.pipeline`)
e grava em `/app/frontend/public/demo-assets/`. O service worker 2a pré-cacheia
estes ficheiros em install (best-effort).

Ficheiros gerados:
    Projeto_arquitetura_Moradia_Martins_DEMO.pdf   — samples.build_all().pc
    Estudo_geotecnico_Moradia_Martins_DEMO.pdf    — samples.build_all().g2
    Dossier_BET_Moradia_Martins.pdf               — pipeline.run().files.pdf
    Desenhos_BET_Moradia_Martins.zip              — pipeline.run().files.zip
    Orcamento_Moradia_Martins.xlsx                — pipeline.run().files.xlsx
    Nota_calculo_sismica_Moradia_Martins.pdf      — derivado de resultats.json

Uso:
    python -m scripts.websummit.generate_demo_assets
"""
from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from engines.bet_core import pipeline
from engines.bet_core.samples import build_all, case

OUT_DIR = Path(__file__).resolve().parents[3] / "frontend" / "public" / "demo-assets"
PROJECT = {
    "name": "Moradia Martins",
    "client": "Carla & Rui Martins",
    "address": "Rua das Oliveiras 12, 1700 Lisboa",
    "architect": "Atelier Exemplo Arquitetos",
}


def _write(path: Path, data: bytes) -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return path.stat().st_size


def _build_pc_g2() -> dict[str, int]:
    docs = build_all("moradia_pt_demo", PROJECT)
    out = {}
    for fname, data in docs.items():
        # Normalizar nome (build_all já faz slug mas garantimos nome fixo)
        if fname.startswith("Projeto_arquitetura_"):
            target = OUT_DIR / "Projeto_arquitetura_Moradia_Martins_DEMO.pdf"
        elif fname.startswith("Estudo_geotecnico_"):
            target = OUT_DIR / "Estudo_geotecnico_Moradia_Martins_DEMO.pdf"
        else:
            target = OUT_DIR / fname
        out[target.name] = _write(target, data)
    return out


def _build_bet(tmpdir: Path) -> dict:
    raw = case("moradia_pt_demo", PROJECT)
    raw["project"].update(LISBOA_SEISMIC)
    res = pipeline.run(raw, tmpdir, lang="pt", stem="Moradia_Martins")
    if res["status"] == "MODELE_INVALIDE":
        raise RuntimeError(f"bet_core pipeline invalid: {res.get('anomalies')}")
    return res


# Zonamento sísmico do concelho de Lisboa (NP EN 1998-1, Anexo Nacional, Quadro NA.I) — a morada do projeto demo é
# em Lisboa; o caso de base (concelho ilustrativo de Braga) usa 1.6 / 2.5.
LISBOA_SEISMIC = {"seismic_zone_type1": "1.3", "seismic_zone_type2": "2.3",
                  "_seismic_source": "Zonas sísmicas do concelho de Lisboa (Anexo Nacional NP EN 1998-1, Quadro NA.I) "
                                     "e terreno tipo B admitido — a confirmar pelo estudo geotécnico"}


def _build_seismic_note(tmpdir: Path) -> Path:
    """Nota de cálculo sísmica formatada a partir de resultats.json (saída do motor de estrutura) — zero números inventados."""
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    fonts = Path(__file__).resolve().parents[2] / "engines" / "bet_core" / "fonts"
    if "SN" not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(TTFont("SN", str(fonts / "Inter_400Regular.ttf")))
        pdfmetrics.registerFont(TTFont("SNB", str(fonts / "Inter_600SemiBold.ttf")))
        pdfmetrics.registerFontFamily("SN", normal="SN", bold="SNB", italic="SN", boldItalic="SNB")
    verde, verde_esc, cobre, linha = (colors.HexColor("#285541"), colors.HexColor("#203b2d"),
                                      colors.HexColor("#875133"), colors.HexColor("#f4f8f7"))
    results = json.loads((tmpdir / "resultats.json").read_text("utf-8"))
    s = (results.get("structure") or {}).get("seismic") or {}
    f = lambda v, n=1: f"{v:,.{n}f}".replace(",", " ").replace(".", ",")  # noqa: E731

    base = ParagraphStyle("b", fontName="SN", fontSize=9, leading=12.5, textColor=colors.HexColor("#1f2933"))
    small = ParagraphStyle("s", parent=base, fontSize=7.5, leading=10, textColor=colors.HexColor("#5b6670"))
    h1 = ParagraphStyle("h1", parent=base, fontName="SNB", fontSize=17, leading=21, textColor=verde_esc)
    h2 = ParagraphStyle("h2", parent=base, fontName="SNB", fontSize=11, leading=15, textColor=verde, spaceBefore=8, spaceAfter=3)
    kick = ParagraphStyle("k", parent=base, fontName="SNB", fontSize=8, leading=10, textColor=cobre)

    def table(rows, widths, head=True):
        rows = [[Paragraph(str(c), ParagraphStyle("c", parent=base, fontName="SNB" if head and i == 0 else "SN",
                                                  textColor=colors.white if head and i == 0 else base.textColor))
                 for c in r] for i, r in enumerate(rows)]
        t = Table(rows, colWidths=widths, repeatRows=1 if head else 0)
        st = [("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("LINEBELOW", (0, 0), (-1, -1), 0.3, colors.HexColor("#d5e3df")),
              ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3)]
        if head:
            st += [("BACKGROUND", (0, 0), (-1, 0), verde)]
        st += [("BACKGROUND", (0, i), (-1, i), linha) for i in range(2 if head else 1, len(rows), 2)]
        t.setStyle(TableStyle(st))
        return t

    W = A4[0] - 36 * mm
    story = [Paragraph("CONSTRUPILOT · EXEMPLO FICTÍCIO DE DEMONSTRAÇÃO", kick), Spacer(1, 2 * mm),
             Paragraph("Nota de cálculo sísmica", h1),
             Paragraph(f"{PROJECT['name']} — {PROJECT['address']} · Cliente : {PROJECT['client']} · "
                       f"Arquitetura : {PROJECT['architect']}", small), Spacer(1, 4 * mm),
             Paragraph("1. Modelo e método", h2),
             Paragraph(f"{s.get('method', 'NP EN 1998-1 + Anexo Nacional')}. {s.get('intro', '')}", base),
             Paragraph("2. Ação sísmica regulamentar", h2)]
    tab = s.get("table") or []
    if tab:
        story.append(table([["Parâmetro", "Ação tipo 1 (afastada)", "Ação tipo 2 (próxima)"]] + tab, [W * 0.5, W * 0.25, W * 0.25]))
    story.append(Spacer(1, 2 * mm))
    gov = s.get("governing")
    story.append(Paragraph(f"Ação condicionante : tipo {gov} — força de corte basal F<sub>b</sub> = {f(s.get('Fb_kN', 0))} kN "
                           f"(peso sísmico W = {f(s.get('W_kN', 0), 0)} kN, T<sub>1</sub> = {f(s.get('T1', 0), 3)} s, "
                           f"q = {f(s.get('q', 0), 1)}).", base))
    if s.get("storeys"):
        story += [Paragraph("3. Distribuição das forças pelos pisos", h2),
                  table([["Piso", "Cota z (m)", "Peso W (kN)", "Massa (t)", "Força F (kN)"]]
                        + [[x["level"], f(x["z"], 2), f(x["W_kN"]), f(x["m_t"]), f(x["F_kN"])] for x in s["storeys"]],
                        [W * 0.32, W * 0.17, W * 0.17, W * 0.17, W * 0.17])]
    if s.get("directions"):
        story += [Paragraph("4. Verificação das paredes resistentes ao corte", h2),
                  table([["Direção", "Comprim. (m)", "p<sub>A</sub> (%)", "V<sub>Ed</sub> (kN)", "V<sub>Rd</sub> (kN)", "Taxa"]]
                        + [[x["dir"], f(x["length_m"]), f(x["pA"], 2), f(x["V_Ed"]), f(x["V_Rd"]), f"{round(x['ratio'] * 100)} %"]
                           for x in s["directions"]],
                        [W * 0.30, W * 0.18, W * 0.12, W * 0.13, W * 0.13, W * 0.14])]
    ok = s.get("ok")
    story += [Paragraph("5. Conclusão", h2),
              Paragraph((f"Verificação satisfeita : taxa máxima de utilização das paredes {round((s.get('worst_ratio') or 0) * 100)} %."
                         if ok else "Verificação NÃO satisfeita — rever as paredes resistentes."), base)]
    notes = [n for n in (s.get("notes") or []) if isinstance(n, str)]
    if notes:
        story += [Paragraph("Notas e hipóteses", h2)] + [Paragraph("• " + n, small) for n in notes]
    story += [Spacer(1, 6 * mm), Paragraph(
        "Exemplo fictício de demonstração gerado pelos motores de cálculo do ConstruPilot. Não é um documento de "
        "licenciamento e não substitui o termo de responsabilidade de um engenheiro de estruturas.", small)]

    target = OUT_DIR / "Nota_calculo_sismica_Moradia_Martins.pdf"
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    def deco(c, d):
        c.saveState(); c.setFillColor(verde); c.rect(0, A4[1] - 9 * mm, A4[0], 9 * mm, stroke=0, fill=1)
        c.setFillColor(cobre); c.rect(0, A4[1] - 10.2 * mm, A4[0], 1.2 * mm, stroke=0, fill=1)
        c.setFont("SN", 7); c.setFillColor(colors.HexColor("#5b6670"))
        c.drawString(18 * mm, 10 * mm, "ConstruPilot · Nota de cálculo sísmica · Moradia Martins (demonstração)")
        c.drawRightString(A4[0] - 18 * mm, 10 * mm, str(d.page)); c.restoreState()

    doc = SimpleDocTemplate(str(target), pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm, topMargin=18 * mm,
                            bottomMargin=18 * mm, title="Nota de cálculo sísmica — Moradia Martins (demonstração)",
                            author="ConstruPilot — exemplo fictício de demonstração", subject="construpilot-demo:moradia_pt_demo")
    doc.build(story, onFirstPage=deco, onLaterPages=deco)
    return target


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    outputs: dict[str, int] = {}

    # 1) PC + G2
    outputs.update(_build_pc_g2())

    # 2) BET dossier + plans ZIP + xlsx (pipeline grava em tmpdir, movemos para OUT_DIR)
    import tempfile
    with tempfile.TemporaryDirectory(prefix="bet_demo_") as tmp:
        tmp_path = Path(tmp)
        res = _build_bet(tmp_path)
        src_pdf = Path(res["files"]["pdf"])
        src_zip = Path(res["files"]["zip"])
        src_xls = Path(res["files"]["xlsx"])
        for src, name in (
            (src_pdf, "Dossier_BET_Moradia_Martins.pdf"),
            (src_zip, "Desenhos_BET_Moradia_Martins.zip"),
            (src_xls, "Orcamento_Moradia_Martins.xlsx"),
        ):
            target = OUT_DIR / name
            shutil.copy2(src, target)
            outputs[name] = target.stat().st_size

        # 3) Nota de cálculo sísmica (derivada de resultats.json)
        note = _build_seismic_note(tmp_path)
        outputs[note.name] = note.stat().st_size

    # 4) Manifesto para rastreio
    manifest = {
        "generator": "scripts.websummit.generate_demo_assets",
        "engines": [
            "engines.bet_core.samples.build_all (PC + G2)",
            "engines.bet_core.pipeline.run (dossier BET + desenhos + orçamento)",
            "engines.bet_core.structure.compute (nota sísmica)",
        ],
        "project": PROJECT,
        "outputs": outputs,
    }
    (OUT_DIR / "_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8",
    )
    outputs["_manifest.json"] = (OUT_DIR / "_manifest.json").stat().st_size
    print(json.dumps({"status": "ok", "out_dir": str(OUT_DIR), "outputs": outputs},
                     ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
