"""Mapa de materiais até aos parafusos, sem inventar (14/11)."""
from engines import mapa_materiais as M


def _mat(a, nome):
    return next(m for m in a["materiais"] if m["material"].startswith(nome))


def test_divisoria_ate_aos_parafusos():
    a = M.decompor({"designation": "Divisória em gesso cartonado 70/48, 1 placa por face, com lã mineral", "unit": "m²", "qty": 100})
    assert a["estado"] == "completo" and a["receita"] == "divisoria_gc"
    p = _mat(a, "Parafuso auto-perfurante TN")
    assert p["quantidade_liquida"] == 3000 and p["quantidade_encomenda"] == 3150 and p["embalagens"] == "4 × caixa 1000"
    assert _mat(a, "Placa de gesso")["quantidade_liquida"] == 200
    assert _mat(a, "Lã mineral")["quantidade_liquida"] == 100


def test_alvenaria_geometria_e_falta_de_formato():
    a = M.decompor({"designation": "Alvenaria de tijolo furado 30x20x11", "unit": "m2", "qty": 10})
    t = _mat(a, "Tijolo")
    assert round(t["quantidade_liquida"], 1) == round(10 / (0.31 * 0.21), 1)
    b = M.decompor({"designation": "Alvenaria de tijolo", "unit": "m2", "qty": 10})
    assert b["estado"] == "parcial" and "formato" in b["motivo"] and _mat(b, "Tijolo")["quantidade_liquida"] is None


def test_nao_inventa_quantidades_nem_espessuras():
    g = M.decompor({"designation": "Rede exterior de águas pluviais", "unit": "un", "qty": 1})
    assert g["estado"] == "global" and g["materiais"] == []
    s = M.decompor({"designation": "Pavimento betuminoso", "unit": "m2", "qty": 4897.03})
    # 14/11: sem espessura no desenho → perfil-tipo DECLARADO como hipótese (nunca apresentado como «decomposto» puro)
    assert s["estado"] == "hipotese" and "5 cm" in s["perfil_tipo"] and "hipótese" in s["motivo"]
    c = M.decompor({"designation": "Pavimento betuminoso AC 14 surf e=5cm", "unit": "m2", "qty": 1000})
    assert _mat(c, "Mistura betuminosa")["quantidade_liquida"] == 120.0
    x = M.decompor({"designation": "Divisória gesso cartonado", "unit": "m2", "qty": None, "quantity_missing": True})
    assert x["estado"] == "sem_medicao"


def test_caixilharia_fixacoes_ral():
    a = M.decompor({"designation": "Janela de correr 120x140", "unit": "un", "qty": 4})
    assert _mat(a, "Parafuso de caixilharia")["quantidade_liquida"] == 4 * (2 * 2 + 2 * 2)


def test_mapa_totais_por_material():
    r = M.mapa([{"designation": "Divisória gesso cartonado", "unit": "m2", "qty": 10},
                {"designation": "Teto falso gesso cartonado", "unit": "m2", "qty": 10},
                {"kind": "section", "designation": "Cap 1"}])
    t = {x["material"]: x for x in r["totais"]}
    assert t["Placa de gesso cartonado 12,5 mm"]["quantidade_liquida"] == 30.0
    assert r["contagem"]["parcial"] == 1 and r["contagem"]["completo"] == 1
