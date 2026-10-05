"""Testes Stair Engine — Blondel, verificações, PDF."""
from __future__ import annotations

import io
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("JWT_SECRET", "test-secret")

from engines.stair_engine import StairInputs, calculate_stair  # noqa: E402
from engines.stair_engine.blondel import (  # noqa: E402
    blondel_check, blondel_optimal, suggest_num_steps,
)
from engines.stair_engine.pdf_dossier import build_pdf  # noqa: E402
from engines.stair_engine.verifications import run_all, summarize  # noqa: E402


class TestBlondel:
    def test_optimal_habitacao_tipica(self):
        # Altura 3m, 17 degraus → h ~ 17.6 cm, g ~ 27.8 cm, Blondel ~ 63
        r = blondel_optimal(300, 17)
        assert 17 < r.h_cm < 18.5
        assert 25 < r.g_cm < 30
        assert 60 <= r.blondel <= 64
        assert r.blondel_ok
        assert r.comfort_score >= 7

    def test_suggest_num_steps_300cm(self):
        n = suggest_num_steps(300)
        assert 15 <= n <= 18

    def test_blondel_check_bad(self):
        r = blondel_check(22, 22)  # degrau muito alto
        assert not r.blondel_ok
        assert r.inclination_deg > 40
        assert r.comfort_score < 6

    def test_blondel_check_ideal(self):
        r = blondel_check(17, 29)
        assert r.blondel_ok
        assert r.comfort_score >= 8


class TestVerifications:
    def _base(self, **k):
        base = dict(h_cm=17.5, g_cm=28.0, largura_m=1.0, pe_direito_m=2.5,
                    uso="habitacao", material="betao")
        base.update(k)
        return base

    def test_rgeu_altura_ok_habitacao(self):
        v = run_all(**self._base())
        rgeu_42 = [x for x in v if x["referencia"] == "Art. 42º"]
        assert len(rgeu_42) == 1
        assert rgeu_42[0]["estado"] == "conforme"

    def test_rgeu_altura_excessiva_evacuacao(self):
        # Para evacuação, h máx = 17.5. Se h=18 → não conforme
        v = run_all(**self._base(h_cm=18.0, uso="evacuacao", capacidade=50))
        assert any(x["estado"] == "nao_conforme" and x["referencia"] == "Art. 42º" for x in v)

    def test_reh_largura_insuficiente_comercio(self):
        v = run_all(**self._base(largura_m=0.9, uso="comercio"))
        reh = [x for x in v if x["norma"] == "REH"]
        assert any(x["estado"] == "nao_conforme" for x in reh)

    def test_rscie_evacuacao_capacidade(self):
        # 300 pessoas → 3 UP → 1.80 m. Se largura 1.00 → não conforme
        v = run_all(**self._base(largura_m=1.0, uso="evacuacao", capacidade=300))
        rscie = [x for x in v if x["norma"] == "RSCIE"]
        assert any(x["estado"] == "nao_conforme" for x in rscie)

    def test_en_1992_betao_only(self):
        v = run_all(**self._base(material="madeira"))
        assert not any(x["norma"] == "EN 1992" for x in v)
        v2 = run_all(**self._base(material="betao"))
        assert any(x["norma"] == "EN 1992" for x in v2)

    def test_en_1991_carga_evacuacao(self):
        v = run_all(**self._base(uso="evacuacao", capacidade=50))
        en = [x for x in v if x["norma"] == "EN 1991"]
        assert en and "4.0" in en[0]["mensagem"]

    def test_dl_163_acessibilidade(self):
        # h=18 cm > 16 cm limite acessibilidade
        v = run_all(**self._base(h_cm=18.0, acessibilidade=True))
        dl = [x for x in v if x["norma"] == "DL 163/2006"]
        assert any(x["estado"] == "nao_conforme" for x in dl)
        # Sem acessibilidade → não deve emitir regras DL 163
        v2 = run_all(**self._base(h_cm=18.0, acessibilidade=False))
        assert not any(x["norma"] == "DL 163/2006" for x in v2)

    def test_summarize(self):
        v = run_all(**self._base())
        s = summarize(v)
        assert s["total"] == len(v)
        assert s["overall"] in ("conforme", "atencao", "nao_conforme")


class TestCalculator:
    def test_habitacao_tipica(self):
        inp = StairInputs(altura_total_m=3.0, pe_direito_m=2.7, largura_m=1.0, uso="habitacao")
        r = calculate_stair(inp)
        assert 15 <= r["dimensoes"]["num_degraus"] <= 18
        assert r["conforto_score"] >= 7
        assert r["svgs"]["plan_svg"].startswith("<svg")
        assert r["svgs"]["elevation_svg"].startswith("<svg")
        # Sem alertas de não-conformidade críticos
        assert r["resumo_verificacoes"]["nao_conforme"] == 0

    def test_evacuacao_300pessoas(self):
        inp = StairInputs(altura_total_m=3.0, pe_direito_m=2.5, largura_m=1.20,
                          uso="evacuacao", capacidade=300)
        r = calculate_stair(inp)
        # 300 pessoas → 3 UP → 1.80m. largura 1.20 insuficiente.
        assert r["resumo_verificacoes"]["nao_conforme"] >= 1

    def test_acessibilidade_strict(self):
        inp = StairInputs(altura_total_m=3.0, pe_direito_m=2.7, largura_m=1.2,
                          uso="publico", acessibilidade=True)
        r = calculate_stair(inp)
        # Verificações DL 163/2006 devem estar presentes
        normas = {v["norma"] for v in r["verificacoes"]}
        assert "DL 163/2006" in normas


class TestPDF:
    def test_pdf_builds(self):
        inp = StairInputs(altura_total_m=3.0, pe_direito_m=2.7, largura_m=1.0, uso="habitacao")
        r = calculate_stair(inp)
        pdf = build_pdf(r, project_name="Teste T2", ia_text="Análise exemplo.",
                        branding={"brand_company_name": "ConstruPilot", "brand_nif": "509123456"})
        assert pdf[:4] == b"%PDF"
        assert len(pdf) > 3000
