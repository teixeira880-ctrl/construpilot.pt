"""Sem regime próprio para a conta CLT Rezult; Excel de orçamento com os totais já calculados."""
import os
import tempfile

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "test_clt")
os.environ.setdefault("JWT_SECRET", "test")


def test_sem_regime_proprio_para_a_conta_clt():
    """A conta CLT Rezult trabalha como todas as outras: nenhum desvio automático para o modelo Ucrânia."""
    import engines.assistant_bet_core_tool as T
    assert not hasattr(T, "conta_clt_ua")


def test_excel_do_orcamento_tem_os_totais_calculados():
    from openpyxl import load_workbook
    from engines.bet_clt import estimate as E
    from engines.bet_frame import model as M
    m = M.from_dict({"kind": "frame", "project": {"name": "Teste", "country": "UA"}, "levels": [], "grids": {}})
    e = {"eur": 48.5, "vat": 0.2, "sources": [], "extra": [{"lab": "Imprevistos", "pct": 0.05}],
         "lines": [{"lot": "CLT", "des": "Painel", "unit": "m²", "qty": 120.0, "pu": 3500.0, "src": "x"},
                   {"lot": "GO", "des": "Betão", "unit": "m³", "qty": 18.5, "pu": 5200.0, "src": "y"}]}
    p = tempfile.mktemp(suffix=".xlsx")
    E.write_xlsx(p, m, e)
    ws = load_workbook(p, data_only=True).active
    vals = [r[5].value for r in ws.iter_rows(min_row=5) if r[5].value is not None]
    obras = 120 * 3500 + 18.5 * 5200
    ttc = obras * 1.05 * 1.2
    assert any(abs(v - ttc) < 0.01 for v in vals if isinstance(v, (int, float))), vals
    assert str(load_workbook(p).active["F5"].value).startswith("=")                              # continua editável
