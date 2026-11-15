"""Modelo de estudo comum aos motores (visualizador com 3D, alçados, quantidades, corte): adaptadores LSF e CLT."""
import json

import pytest

from bim_studio import clt_modelo as CM
from engines import estudo_modelo as M
from engines.lsf import defaults, engine
from engines.lsf import modelo as LM


def test_lsf_moradia_exemplo_no_formato_comum():
    res = engine.calcular(defaults.exemplo())
    m = LM.modelo(res, projeto={"nome": "x"})
    assert M.validar(m) == [] and m["motor"] == "lsf"
    assert sum(1 for s in m["solidos"] if s["t"] == "perfil") == res["estudo"]["nMembros"]                 # cada perfil, um sólido
    assert sum(1 for s in m["solidos"] if s["t"] == "caixa") == sum(len(p["pecas"]) for p in res["placas"])  # cada peça de placa
    assert len(m["alcados"]) == len(res["paredes"]) and m["alcados"][0]["vaos"][0] == {"x": 1500.0, "y": 900.0, "w": 1200.0, "h": 1200.0}
    assert sum(c["n"] for c in m["lista_corte"]) == res["estudo"]["nMembros"]
    assert len(m["planos_corte"]) == sum(len(c["folhas"] or []) for c in res["planosCorte"])
    parafusos = sum(q["qtd"] for q in m["quantidades"] if q["capitulo"] == "Parafusos")
    assert parafusos == res["estudo"]["nParafusos"]
    json.dumps(m)                                                                                           # serializável tal como está


def parede(i, x1, y1, x2, y2, vaos=()):
    return {"id": i, "x1": x1, "y1": y1, "x2": x2, "y2": y2, "thickness_mm": 100, "height_m": 3.0, "openings": list(vaos)}


PORTA = {"offset_m": 3.0, "width_m": 1.0, "sill_m": 0.0, "height_m": 2.1}
JANELA = {"offset_m": 1.0, "width_m": 1.2, "sill_m": 0.9, "height_m": 1.2}


def test_clt_casa_simples_no_formato_comum():
    faixas, aviso = CM.faixas_da_laje("L", [(0, 0), (8, 0), (8, 6), (0, 6)], 3.5, espessura_mm=160)
    assert aviso is None and len(faixas) == 2 and faixas[0]["ret"] == (0, 0, 8, 3) and faixas[1]["ret"] == (0, 3, 8, 6)
    piso = {"nome": "RDC", "cota_m": 0, "paredes": [parede("S", 0, 0, 8, 0, [PORTA]), parede("N", 0, 6, 8, 6, [JANELA]), parede("O", 0, 0, 0, 6),
                                                    parede("E", 8, 0, 8, 6)], "faixas": faixas}
    corte = {"grupos": [{"espessura_mm": 100, "camadas": 5, "paineis": 1, "layout": [{"painel": 1, "comprimento_usado_m": 8.01, "largura_m": 3.5,
             "aproveitamento_percent": 85.6, "pecas": [{"id": "S", "x_m": 0, "y_m": 0, "comprimento_m": 8.0, "largura_m": 3.0, "rodada": False}]}]}],
             "total": {"paineis": 1, "desperdicio_percent": 14.4}}
    m = CM.modelo([piso], corte, "Casa teste")
    assert M.validar(m) == [] and m["motor"] == "clt"
    caixas = lambda camada: [s for s in m["solidos"] if s["camada"] == camada]
    # S: 2 troços + padieira da porta; N: 2 troços + peitoril + padieira da janela; O e E inteiras
    assert len(caixas("paredes")) == 3 + 4 + 1 + 1 and len(caixas("lajes")) == 2
    s_porta = next(s for s in caixas("paredes") if s["info"]["titulo"].endswith("parede S") and s["o"][2] == 2100.0)
    assert s_porta["a"][0] == 1000.0 and s_porta["c"][2] == 900.0                                          # padieira: 1 m × 0,9 m por cima da porta
    assert all(s["o"][2] == 3000.0 and s["c"][2] == 160.0 for s in caixas("lajes"))                        # a laje assenta no topo das paredes
    liquido = (8 * 3 - 2.1) + (8 * 3 - 1.44) + 18 + 18
    clt = next(q for q in m["quantidades"] if q["capitulo"] == "CLT")
    assert clt["qtd"] == pytest.approx(liquido * 0.1 + 48 * 0.16, abs=1e-3)
    ligadores = sum(q["qtd"] for q in m["quantidades"] if q["item"].startswith("Cantoneira") or "hold-down" in q["item"])
    assert len(caixas("ligadores")) == ligadores == (7 + 8 + 6 + 6) + (4 + 2 + 2 + 2)                      # cada ligador desenhado no seu sítio
    assert len(m["alcados"]) == 4 and m["alcados"][0]["vaos"] == [{"x": 3000.0, "y": 0.0, "w": 1000.0, "h": 2100.0}]
    assert len(m["lista_corte"]) == 6 and len(m["planos_corte"]) == 1 and m["planos_corte"][0]["aproveitamento"] == 85.6
    assert any("Hipótese" in a for a in m["avisos"]) and m["kpi"][0] == "6 peças"


def test_laje_nao_retangular_avisa_e_validador_apanha_erros():
    faixas, aviso = CM.faixas_da_laje("L", [(0, 0), (8, 0), (8, 3), (4, 3), (4, 6), (0, 6)], 3.5)
    assert len(faixas) == 1 and "não retangular" in aviso
    m = M.novo("clt", "x", camadas=(("a", "A", True),))
    m["solidos"].append(M.caixa("outra", "#fff", [0, 0, 0], [1, 0, 0], [0, 1, 0], [0, 0, 1], "peça"))
    m["planos_corte"].append({"titulo": "p", "W": 100, "H": 100, "pecas": [{"x": 90, "y": 0, "w": 20, "h": 10, "rotulo": "q"}]})
    erros = M.validar(m)
    assert any("camada" in e for e in erros) and any("fora da chapa" in e for e in erros)
    with pytest.raises(ValueError):
        M.novo("aco", "x")


def test_pisos_empilhados_pela_altura_das_paredes_e_da_laje():
    rdc = {"nome": "RDC", "paredes": [parede("A", 0, 0, 4, 0)], "faixas": [{"id": "L1", "tipo": "laje", "ret": (0, -1, 4, 1), "espessura_mm": 160}]}
    p1 = {"nome": "Piso 1", "paredes": [parede("B", 0, 0, 4, 0)], "faixas": [{"id": "C1", "tipo": "cobertura", "ret": (0, -1, 4, 1), "espessura_mm": 140}]}
    pisos = CM.empilhar([rdc, p1])
    assert [p["cota_m"] for p in pisos] == [0.0, 3.16]
    m = CM.modelo(pisos)
    assert M.validar(m) == []
    assert next(s for s in m["solidos"] if s["info"]["titulo"].startswith("Piso 1 · parede"))["o"][2] == 3160.0
    assert next(s for s in m["solidos"] if s["camada"] == "cobertura")["o"][2] == 6160.0 and not m["planos_corte"]
