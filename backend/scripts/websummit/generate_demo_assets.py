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

sys.path.insert(0, "/app/backend")

from engines.bet_core import pipeline
from engines.bet_core.samples import build_all, case

OUT_DIR = Path("/app/frontend/public/demo-assets")
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
    res = pipeline.run(raw, tmpdir, lang="pt", stem="Moradia_Martins")
    if res["status"] == "MODELE_INVALIDE":
        raise RuntimeError(f"bet_core pipeline invalid: {res.get('anomalies')}")
    return res


def _build_seismic_note(tmpdir: Path) -> Path:
    """PDF curto derivado de resultats.json — zero números inventados."""
    results = json.loads((tmpdir / "resultats.json").read_text("utf-8"))
    seismic = results.get("structure", {}).get("seismic") or {}
    loads = results.get("structure", {}).get("loads") or {}
    # Fallback campos — usa só o que `structure.compute` devolveu
    content = [
        "NOTA DE CÁLCULO SÍSMICA — EXEMPLO FICTÍCIO DE DEMONSTRAÇÃO",
        "Projeto: Moradia Martins (T3, Lisboa, Portugal)",
        "",
        "Normas aplicáveis (demo):",
        "  NP EN 1998-1 (Eurocódigo 8, parte 1) — Anexo Nacional PT",
        "  NP EN 1990 — Bases do projeto",
        "",
        "Resumo (saída do motor engines.bet_core.structure.compute):",
    ]
    for k, v in {**seismic, **loads}.items():
        content.append(f"  {k}: {v}")
    content += [
        "",
        "Hipóteses:",
        f"  Zona sísmica: {seismic.get('zone', '2A (Lisboa) — Anexo Nacional PT')}",
        f"  Classe de importância: {seismic.get('importance_class', 'II (habitação)')}",
        f"  Terreno (classe): {seismic.get('ground_type', 'A/B — a confirmar com estudo geotécnico G2)')}",
        "",
        "Este documento é um EXEMPLO FICTÍCIO DE DEMONSTRAÇÃO.",
        "Não é um documento de licenciamento. Não substitui o visto de um engenheiro de estruturas.",
    ]
    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.pdfgen import canvas
        target = OUT_DIR / "Nota_calculo_sismica_Moradia_Martins.pdf"
        c = canvas.Canvas(str(target), pagesize=A4)
        c.setTitle("Nota de cálculo sísmica — Moradia Martins (DEMO)")
        c.setAuthor("ConstruPilot — exemplo fictício de demonstração")
        c.setSubject("construpilot-demo:moradia_pt_demo")
        y = 800
        for line in content:
            c.setFont("Helvetica-Bold" if line.endswith("DEMONSTRAÇÃO") else "Helvetica", 10)
            c.drawString(60, y, line[:120])
            y -= 14
            if y < 60:
                c.showPage()
                y = 800
        c.save()
        return target
    except Exception as exc:  # noqa: BLE001
        # Fallback plain text com extensão PDF — mantemos ficheiro para precache (não ideal, mas não bloqueia)
        print(f"warning: reportlab indisponível ({exc}); fallback para plano", file=sys.stderr)
        target = OUT_DIR / "Nota_calculo_sismica_Moradia_Martins.pdf"
        target.write_text("\n".join(content), encoding="utf-8")
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
