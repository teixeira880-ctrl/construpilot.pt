"""Verificação cruzada do orçamento (bet_frame): 2.ª fonte + IA corrigem sem bloquear."""
import copy
import json
from pathlib import Path

import pytest
from openpyxl import load_workbook

from engines.bet_frame import calc, devis, mep, model, pipeline, verificacao
from engines.bet_frame.lang import use_lang

CASE = json.loads((Path(__file__).parents[2] / "engines/bet_frame/cases/immeuble_demo_pt.json").read_text(encoding="utf-8"))


def _recuado():
    raw = copy.deepcopy(CASE)
    for lv in raw["levels"]:
        if lv["id"] in ("P3", "P4"):
            lv["void_cells"] = [["5", "C"], ["6", "C"], ["5", "B"], ["6", "B"]]
    for u in raw["units"]:                                   # sem frações nas células recuadas
        if u["x0"] >= 22.0:
            u["levels"] = [l for l in u["levels"] if l not in ("P3", "P4")]
    return raw


def _estudo(raw):
    m = model.from_dict(raw)
    r = calc.compute(m)
    return m, r, devis.build_lines(m, r, mep.compute(m))


def _q(lines, key):
    return next(x["qty"] for x in lines if x.get("key") == key)


def test_pisos_recuados_o_orcamento_diverge_da_segunda_fonte():
    with use_lang("pt"):
        m, r, L = _estudo(_recuado())
        d = {x["key"] for x in verificacao.desvios(L, verificacao.referencia(m, r))}
    assert {"laje_betao", "laje_cofragem"} <= d


def test_sem_recuos_nao_ha_correcao():
    with use_lang("pt"):
        m, r, L = _estudo(copy.deepcopy(CASE))
        antes = [dict(x) for x in L]
        res = verificacao.reconciliar(m, r, L, diagnosticar=lambda dv: [])
    assert res["corrigidos"] == [] and res["por_confirmar"] == [] and L == antes


def test_ia_diagnostica_e_correcao_confirmada_pela_segunda_fonte():
    with use_lang("pt"):
        m, r, L = _estudo(_recuado())
        ref = verificacao.referencia(m, r)
        res = verificacao.reconciliar(m, r, L, diagnosticar=lambda dv: [
            {"key": d["key"], "veredito": "corrigir_orcamento", "causa": "usou a planta do piso base nos pisos recuados"} for d in dv])
        assert verificacao.desvios(L, ref) == []
    assert set(res["corrigidos"]) == {"laje_betao", "laje_cofragem"} and res["por_confirmar"] == []
    assert abs(_q(L, "laje_betao") - round(ref["laje_betao"]["qty"], 2)) < 0.01
    assert all(x["ia"] and "recuados" in x["causa"] for x in res["log"])


def test_sem_ia_continua_em_modo_deterministico():
    with use_lang("pt"):
        m, r, L = _estudo(_recuado())

        def falha(dv):
            raise RuntimeError("IA em baixo")
        res = verificacao.reconciliar(m, r, L, diagnosticar=falha)
        assert verificacao.desvios(L, verificacao.referencia(m, r)) == []
    assert res["corrigidos"] and not any(x["ia"] for x in res["log"])


def test_ia_diz_referencia_incorreta_mantem_valor_e_avisa_sem_bloquear():
    with use_lang("pt"):
        m, r, L = _estudo(_recuado())
        antes = _q(L, "laje_betao")
        res = verificacao.reconciliar(m, r, L, diagnosticar=lambda dv: [{"key": d["key"], "veredito": "referencia_incorreta", "causa": "x"} for d in dv])
    assert _q(L, "laje_betao") == antes and "laje_betao" in res["por_confirmar"]
    assert all(a["level"] == model.WARN for a in res["avisos"])


def _xlsx_quantidades(path):
    ws = load_workbook(path).active
    return {row[1].value: row[3].value for row in ws.iter_rows(min_row=5) if row[1].value}


def test_orcamento_corrigido_no_excel_sem_renderizar(tmp_path, monkeypatch):
    """_verificar (usado pelo pipeline) + escrita do Excel, sem a fase de desenhos."""
    monkeypatch.setattr(verificacao, "_ia_diagnostico", lambda dv: None)             # sem rede
    with use_lang("pt"):
        m, r, L = _estudo(_recuado())
        an: list = []
        res = pipeline._verificar(m, r, L, an)
        ref = verificacao.referencia(m, r)
        devis.write_xlsx(tmp_path / "o.xlsx", m, L)
    assert res and res["corrigidos"] and not model.has_block(an)
    q = _xlsx_quantidades(tmp_path / "o.xlsx")
    assert abs(q["Betão em lajes maciças"] - ref["laje_betao"]["qty"]) < 0.01
    assert abs(q["Cofragem e escoramento de lajes"] - ref["laje_cofragem"]["qty"]) < 0.01


def test_pipeline_completo_entrega_orcamento_corrigido(tmp_path, monkeypatch):
    pytest.importorskip("ezdxf")
    monkeypatch.setattr(verificacao, "_ia_diagnostico", lambda dv: None)
    res = pipeline.run(_recuado(), tmp_path, stem="V")
    assert res["status"] != "MODELE_INVALIDE" and res["verificacao"]["corrigidos"]
    with use_lang("pt"):
        m, r, _l = _estudo(_recuado())
        ref = verificacao.referencia(m, r)
    q = _xlsx_quantidades(res["files"]["xlsx"])
    assert abs(q["Betão em lajes maciças"] - ref["laje_betao"]["qty"]) < 0.01
