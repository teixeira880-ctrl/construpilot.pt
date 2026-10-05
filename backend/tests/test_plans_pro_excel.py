"""Testes Excel export Plans Pro."""
from __future__ import annotations

import io
import os
import sys
from pathlib import Path

import pytest
from openpyxl import load_workbook

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("JWT_SECRET", "test-secret")

from engines.plans_pro.excel_export import IVA_RATES_PT, build_workbook  # noqa: E402


def _sample_plan() -> dict:
    return {
        "plan_id": "pln_test123456",
        "user_id": "user_abc",
        "project_id": "obra-casa-teste",
        "file_name": "casa_t2.dwg",
        "file_type": "dwg",
        "autodesk_urn": "dXJuOmFkc2sub2JqZWN0czpvcy5vYmplY3Q6",
        "model_used": "claude-opus-5-5",
        "quantities": {
            "Paredes": {"count": 42, "source": "layers", "layers": [
                {"layer": "A-WALL-INT", "count": 25},
                {"layer": "A-WALL-EXT", "count": 17},
            ]},
            "Lajes": {"count": 2, "source": "categories"},
            "Portas": {"count": 8, "source": "layers"},
        },
        "ai_analysis": {
            "synthesis": {
                "resumo": "Habitação T2 com 80 m² em betão armado e alvenaria.",
                "ouvrages": [
                    {"nome": "Fundações C25/30", "quantidade": 16, "unidade": "m³",
                     "pu_eur": 180.0, "observacoes": "Sapatas isoladas."},
                    {"nome": "Laje térrea", "quantidade": 80, "unidade": "m²",
                     "pu_eur": 45.0, "observacoes": "Com membrana."},
                    {"nome": "Alvenaria tijolo 15cm", "quantidade": 120, "unidade": "m²",
                     "pu_eur": 32.0, "observacoes": None},
                ],
                "normas_aplicaveis": [
                    "RGEU - Decreto-Lei n.º 38 382/51",
                    "Eurocódigo 2 (EN 1992-1-1) - estruturas de betão",
                    "REH - Regulamento das Edificações",
                ],
            }
        },
    }


class TestExcelExport:
    def test_iva_rates_pt(self):
        assert "23" in IVA_RATES_PT
        assert IVA_RATES_PT["23"]["rate"] == 0.23
        assert IVA_RATES_PT["6"]["rate"] == 0.06
        assert "Reabilitação" in IVA_RATES_PT["6"]["label"]

    def test_build_workbook_bytes(self):
        data, meta = build_workbook(plan_doc=_sample_plan(), iva_rate="23")
        assert len(data) > 2000
        assert data[:2] == b"PK"  # xlsx = zip
        assert meta["iva_rate"] == 0.23
        assert meta["ouvrages"] == 3
        assert meta["quantities"] == 3
        assert meta["numero_orc"].startswith("ORC-")

    def test_totals_math_23pct(self):
        data, meta = build_workbook(plan_doc=_sample_plan(), iva_rate="23")
        # 16*180 + 80*45 + 120*32 = 2880 + 3600 + 3840 = 10320
        assert abs(meta["totals"]["total_ht_eur"] - 10320.0) < 0.01
        assert abs(meta["totals"]["iva_eur"] - 10320.0 * 0.23) < 0.01
        assert abs(meta["totals"]["total_ttc_eur"] - 10320.0 * 1.23) < 0.01

    def test_totals_math_6pct_madeira(self):
        _, meta = build_workbook(plan_doc=_sample_plan(), iva_rate="6")
        assert abs(meta["totals"]["iva_eur"] - 10320.0 * 0.06) < 0.01

    def test_invalid_iva_rate_defaults_to_23(self):
        _, meta = build_workbook(plan_doc=_sample_plan(), iva_rate="999")
        assert meta["iva_rate"] == 0.23

    def test_workbook_structure(self):
        data, _ = build_workbook(plan_doc=_sample_plan(), iva_rate="23")
        wb = load_workbook(io.BytesIO(data))
        assert wb.sheetnames == ["Resumo", "Orçamento", "Quantidades"]

    def test_budget_headers_pt(self):
        data, _ = build_workbook(plan_doc=_sample_plan(), iva_rate="23")
        wb = load_workbook(io.BytesIO(data))
        ws = wb["Orçamento"]
        headers = [ws.cell(row=1, column=c).value for c in range(1, 10)]
        assert headers == [
            "Designação", "Un", "Quantidade", "Preço Unit. (€)",
            "Total s/ IVA", "IVA (23%)", "Total c/ IVA",
            "Ref. Biblioteca PT", "Observações",
        ]

    def test_budget_rows_have_data(self):
        data, _ = build_workbook(plan_doc=_sample_plan(), iva_rate="23")
        wb = load_workbook(io.BytesIO(data))
        ws = wb["Orçamento"]
        # Linha 2 = primeiro ouvrage
        assert ws.cell(row=2, column=1).value == "Fundações C25/30"
        assert ws.cell(row=2, column=2).value == "m³"
        assert ws.cell(row=2, column=3).value == 16
        assert ws.cell(row=2, column=4).value == 180.0
        # Fórmula E2 = IFERROR(C2*D2,0)
        assert "C2*D2" in str(ws.cell(row=2, column=5).value)

    def test_quantities_sheet_populated(self):
        data, _ = build_workbook(plan_doc=_sample_plan(), iva_rate="23")
        wb = load_workbook(io.BytesIO(data))
        ws = wb["Quantidades"]
        assert ws.cell(row=1, column=1).value == "Ouvrage"
        # 3 categorias => linhas 2,3,4
        cats = {ws.cell(row=r, column=1).value for r in range(2, 5)}
        assert cats == {"Paredes", "Lajes", "Portas"}

    def test_resumo_sheet_header(self):
        data, _ = build_workbook(plan_doc=_sample_plan(), iva_rate="23")
        wb = load_workbook(io.BytesIO(data))
        ws = wb["Resumo"]
        assert ws["A1"].value == "ConstruPilot — Orçamento preliminar"

    def test_empty_analysis_still_generates(self):
        """Mesmo sem ouvrages, workbook deve gerar com totals=0."""
        doc = _sample_plan()
        doc["ai_analysis"] = {"synthesis": {"ouvrages": []}}
        data, meta = build_workbook(plan_doc=doc, iva_rate="23")
        assert len(data) > 1000
        assert meta["totals"]["total_ht_eur"] == 0.0
