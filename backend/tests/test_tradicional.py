"""Construção tradicional: alvenaria assente unidade a unidade, fiada a fiada."""
import pytest

from engines import estudo_modelo as M
from engines.tradicional import engine as T
from engines.tradicional import modelo as TM


def parede(i, x1, y1, x2, y2, tipo="INT", h=0.62, vaos=()):
    return {"id": i, "x1": x1, "y1": y1, "x2": x2, "y2": y2, "tipo": tipo, "altura_m": h, "vaos": list(vaos)}


def test_parede_simples_fiada_a_fiada_com_desencontro():
    # 3,09 m de tijolo 30×20×11 com junta de 10 mm: 10 inteiros por fiada; a fiada 2 começa com meio tijolo
    r = T.calcular({"pisos": [{"nome": "P", "paredes": [parede("A", 0, 0, 3.09, 0)]}]})
    por = lambda f: [u for u in r["unidades"] if u["fiada"] == f]
    assert [len(por(f)) for f in (1, 2, 3)] == [10, 11, 10] and all(u["inteira"] for u in por(1) + por(3))
    assert (por(2)[0]["c"], por(2)[-1]["c"]) == (0.15, 0.14) and por(2)[1]["s"] == 0.16
    res = r["resumo"][0]
    assert (res["inteiras"], res["cortes"], res["unidades_para_cortes"], res["a_comprar"]) == (29, 2, 1, 30)   # os dois cortes saem do mesmo tijolo
    # argamassa: junta de assentamento + junta vertical de cada unidade, 11 cm de espessura
    assert res["argamassa_m3"] == pytest.approx(sum(u["c"] * 0.11 * 0.01 + u["h"] * 0.11 * 0.01 for u in r["unidades"]), abs=1e-4)
    assert r["estudo"]["area_alvenaria_m2"] == pytest.approx(3.09 * 0.62, abs=0.006)


def test_vao_corta_as_fiadas_e_leva_lintel():
    porta = {"offset_m": 1.24, "largura_m": 0.61, "peitoril_m": 0, "altura_m": 0.41}
    r = T.calcular({"pisos": [{"nome": "P", "paredes": [parede("A", 0, 0, 3.09, 0, vaos=[porta])]}]})
    por = lambda f: [u for u in r["unidades"] if u["fiada"] == f]
    assert len(por(1)) == 8 and all(u["inteira"] for u in por(1))                      # 4 de cada lado da porta
    assert not [u for u in por(1) + por(2) if 1.24 - 1e-6 < u["s"] < 1.85 - 1e-6]      # nada assente dentro do vão nas duas primeiras fiadas
    assert len(por(3)) == 10                                                           # por cima do vão a fiada volta a ser inteira
    assert len(r["linteis"]) == 1 and r["linteis"][0]["comprimento_m"] == pytest.approx(1.01) and r["linteis"][0]["z"] == 0.41
    assert r["estudo"]["area_alvenaria_m2"] == pytest.approx(3.09 * 0.62 - 0.61 * 0.41, abs=0.006)


def test_encontro_em_T_nao_assenta_o_canto_duas_vezes_e_cruzamento_avisa():
    base = parede("A", 0, 0, 6, 0, "EXT")
    r = T.calcular({"pisos": [{"nome": "P", "paredes": [base, parede("B", 3, 0, 3, 3)]}]})
    b = next(w for w in r["paredes"] if w["id"] == "B")
    assert b["util_m"] == pytest.approx(3 - 0.22 / 2)                                   # encurtada meia espessura da parede de 22
    assert min(u["s"] for u in r["unidades"] if u["parede"] == "B") == pytest.approx(0.11)
    x = T.calcular({"pisos": [{"nome": "P", "paredes": [base, parede("C", 3, -2, 3, 2)]}]})
    assert any("cruzam-se" in a for a in x["avisos"])


def test_blocos_de_betao_parametros_e_erros():
    r = T.calcular({"junta_mm": 12, "pisos": [{"nome": "P", "paredes": [parede("A", 0, 0, 5.11, 0, "EXT_BLOCO", h=2.0)]}]})
    assert r["resumo"][0]["unidade"] == "bloco_50x20x20" and r["parametros"]["junta_mm"]["valor"] == 12
    assert max(u["fiada"] for u in r["unidades"]) == 10 and r["paredes"][0]["t"] == 0.2          # 10 fiadas de 20 + 1,2 cm em 2 m
    with pytest.raises(ValueError):
        T.calcular({"pisos": [{"nome": "P", "paredes": [parede("A", 0, 0, 2, 0, "XPTO")]}]})
    with pytest.raises(ValueError):
        T.calcular({"pisos": [{"nome": "P", "paredes": [parede("A", 0, 0, 2, 0, vaos=[{"offset_m": 1.5, "largura_m": 1, "altura_m": 0.4}])]}]})


def test_moradia_exemplo_no_visualizador_comum():
    res = T.calcular(T.exemplo())
    m = TM.modelo(res, projeto=T.exemplo())
    assert M.validar(m) == [] and m["motor"] == "tradicional"
    assert sum(1 for s in m["solidos"] if s["camada"] != "linteis") == res["estudo"]["unidades"]      # cada unidade, um sólido
    assert sum(len(a["rects"]) for a in m["alcados"]) == res["estudo"]["unidades"] and len(m["alcados"]) == 5
    assert sum(q["n"] for q in m["lista_corte"]) == sum(1 for u in res["unidades"] if not u["inteira"])
    comprar = sum(q["qtd"] for q in m["quantidades"] if q["capitulo"] == "Alvenaria")
    assert comprar == res["estudo"]["a_comprar"] and res["estudo"]["a_comprar"] <= res["estudo"]["unidades"]
    assert any("betão armado" in a for a in m["avisos"])
