"""Testa o script de geração de assets estáticos da demo (LOTE 2c).

Valida:
- Script corre sem erro e grava 6+1 ficheiros em `/app/frontend/public/demo-assets/`.
- Tamanhos razoáveis (> 1 KB cada, PDF/ZIP/XLSX plausíveis).
- Manifest referencia os motores `bet_core.samples.build_all` + `pipeline.run`.
"""
import json
import subprocess
from pathlib import Path

OUT = Path("/app/frontend/public/demo-assets")
EXPECTED = [
    "Projeto_arquitetura_Moradia_Martins_DEMO.pdf",
    "Estudo_geotecnico_Moradia_Martins_DEMO.pdf",
    "Dossier_BET_Moradia_Martins.pdf",
    "Desenhos_BET_Moradia_Martins.zip",
    "Orcamento_Moradia_Martins.xlsx",
    "Nota_calculo_sismica_Moradia_Martins.pdf",
]


def test_assets_script_runs_and_outputs_six_files():
    r = subprocess.run(
        ["python", "-m", "scripts.websummit.generate_demo_assets"],
        cwd="/app/backend",
        capture_output=True,
        text=True,
        timeout=180,
        check=True,
    )
    payload = json.loads(r.stdout)
    assert payload["status"] == "ok"
    outputs = payload["outputs"]
    for name in EXPECTED:
        assert name in outputs, f"missing output: {name}"
        assert outputs[name] > 1024, f"{name} too small: {outputs[name]}"
    assert "_manifest.json" in outputs


def test_assets_files_exist_on_disk():
    for name in EXPECTED:
        p = OUT / name
        assert p.exists(), f"missing on disk: {p}"
        assert p.stat().st_size > 1024, f"{p} too small"


def test_assets_pdf_zip_xlsx_magic_bytes():
    checks = {
        "Projeto_arquitetura_Moradia_Martins_DEMO.pdf": b"%PDF",
        "Estudo_geotecnico_Moradia_Martins_DEMO.pdf": b"%PDF",
        "Dossier_BET_Moradia_Martins.pdf": b"%PDF",
        "Nota_calculo_sismica_Moradia_Martins.pdf": b"%PDF",
        "Desenhos_BET_Moradia_Martins.zip": b"PK",
        "Orcamento_Moradia_Martins.xlsx": b"PK",  # XLSX é um zip
    }
    for name, magic in checks.items():
        with (OUT / name).open("rb") as fh:
            head = fh.read(4)
        assert head.startswith(magic), f"{name} magic bytes incorrectos: {head!r}"


def test_assets_manifest_references_engines():
    manifest = json.loads((OUT / "_manifest.json").read_text("utf-8"))
    engines = " ".join(manifest["engines"])
    assert "bet_core.samples.build_all" in engines
    assert "bet_core.pipeline.run" in engines
    assert manifest["project"]["name"] == "Moradia Martins"
