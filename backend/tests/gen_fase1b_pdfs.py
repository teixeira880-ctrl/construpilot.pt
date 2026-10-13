"""Script auxiliar: gera `nota.pdf` + `cofragem.pdf` para a Fase 1b.

Usa um modelo REAL (habitação R/C+1, 3×2 vãos, sobrecarga 2 kN/m²) e valida que
`elementos > 0` e `mapa_armaduras > 0` antes de escrever os PDFs em
`/app/test_reports/bet_fase1b/`.
"""
from __future__ import annotations

import sys
from pathlib import Path

# garante /app/backend no sys.path quando chamado por script
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from engines.structuro_autopilot import build_and_compute  # noqa: E402
from engines.structuro_coffrage import build_coffrage_pdf  # noqa: E402


def main() -> int:
    out_dir = Path("/app/test_reports/bet_fase1b")
    out_dir.mkdir(parents=True, exist_ok=True)

    # Entrada REAL — habitação R/C+1, pórtico pilares-vigas
    inputs = {
        "building": {
            "destination": "habitacao",   # alias PT, deverá ser normalizado para "habitation"
            "levels": 2,
            "storey_height_m": 2.8,
            "ground_height_m": 3.0,
        },
        "grid": {
            "bays_x_m": [4.0, 4.5, 4.0],
            "bays_y_m": [4.0, 5.0],
        },
        "system": {"structure": "portique", "wall_thickness_m": 0.20},
        "loads": {"floor_var_kn_m2": 2.0},   # habitação Cat A — kN/m²
        "soil": {
            "q_els_kpa": 200.0, "q_elu_kpa": 300.0, "q_confirmed": True,
            "foundation_type": "isolee", "anchorage_depth_m": 0.8,
        },
    }

    out = build_and_compute(inputs)
    model = out["model"]
    superstructure = out["summary"]["superstructure"]
    metre = out["metre"]
    summary = out["summary"]

    n_elements = len(model.get("elements", []))
    schedule = (metre.get("steel") or {}).get("schedule") or []
    n_sched = len(schedule)
    print(f"Elementos: {n_elements}")
    print(f"Mapa de armaduras: {n_sched}")
    print(f"Betão total (m³): {metre.get('concrete', {}).get('total_m3')}")
    print(f"Aço total (kg): {(metre.get('steel') or {}).get('total_kg')}")

    assert n_elements > 0, f"Modelo vazio (elementos={n_elements})"
    assert n_sched > 0, f"Mapa de armaduras vazio ({n_sched})"

    # ------- cofragem.pdf (BET A3 + plantas + ferraillage) -------
    pdf = build_coffrage_pdf(model, 1, model["title"], superstructure=superstructure,
                              metre_data=metre, summary=summary,
                              soil=out.get("soil"), inputs=inputs,
                              marks=out.get("marks"))
    (out_dir / "cofragem.pdf").write_bytes(pdf)

    # ------- nota.pdf (estudo preliminar A4) -------
    from engines.structuro_note import build_study_note
    study = {
        "title": "Habitação R/C+1 — Autopiloto BET (Fase 1b)",
        "study_id": "BET-FASE1B-001",
        "country": "PT",
        "revision": 1,
        "output_level": "preliminar",
        "goal": {"label": "Pré-dimensionamento estrutural automático"},
        "data": {},
        "levels": [{"name": "R/C", "elevation_m": {"value": 0.0}},
                   {"name": "Cobertura", "elevation_m": {"value": 2.8}}],
        "elements": [],
        "facts": [],
        "verifications": [],
        "approvals": [],
        "plans": [],
    }
    pdf_nota = build_study_note(study)
    (out_dir / "nota.pdf").write_bytes(pdf_nota)
    print(f"PDFs gerados em: {out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
