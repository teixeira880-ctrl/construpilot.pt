"""Smoke-test da fixture sintética PT (L1.6).

Garante que o gerador cria os ficheiros esperados em `tmp_path` sem erros, e
que o `brief.json` é parseável pelo `parse_user_brief`.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from engines.bet_agent.brief import parse_user_brief


def test_fixture_build_creates_all_files(tmp_path: Path) -> None:
    from tests.fixtures.bet_agent.generate_moradia_pt import build_fixture
    paths = build_fixture(target_dir=tmp_path)
    for key in ("arquitectura", "geotecnico", "brief", "defects"):
        assert paths[key].exists(), f"missing {key}"
        assert paths[key].stat().st_size > 100, f"{key} too small (empty?)"


def test_fixture_brief_is_valid_user_brief(tmp_path: Path) -> None:
    from tests.fixtures.bet_agent.generate_moradia_pt import build_fixture
    paths = build_fixture(target_dir=tmp_path)
    raw = json.loads(paths["brief"].read_text(encoding="utf-8"))
    ub = parse_user_brief(raw)
    assert ub.materials.slab_type is not None
    assert ub.materials.slab_type.value == "aligeirada_vigotas_abobadilhas"
    assert ub.seismic.zone == "1.3"
    assert ub.seismic.soil_class == "C"
    # Nota contém referência fora de âmbito (térmica REH) para activar SEM-005
    assert ub.notes and "termica" in ub.notes.lower() or "térmica" in ub.notes.lower()


def test_fixture_defects_md_lists_five_items(tmp_path: Path) -> None:
    from tests.fixtures.bet_agent.generate_moradia_pt import build_fixture
    paths = build_fixture(target_dir=tmp_path)
    md = paths["defects"].read_text(encoding="utf-8")
    # Verifica que todos os 5 defeitos estão referenciados por código.
    for code in ("GEO-001", "GEO-002", "GEO-004", "GEO-007", "SEM-002"):
        assert code in md, f"código {code} ausente de fixture_defects.md"
