"""Ligações do CLT contadas peça a peça: casa retangular 8 × 6 m com uma parede interior, uma porta e uma janela."""
import math

import pytest

from bim_studio import clt_ligacoes as L


def parede(i, x1, y1, x2, y2, vaos=()):
    return {"id": i, "x1": x1, "y1": y1, "x2": x2, "y2": y2, "thickness_mm": 100, "height_m": 3.0, "openings": list(vaos)}


PORTA = {"offset_m": 3.0, "width_m": 1.0, "sill_m": 0.0, "height_m": 2.1}
JANELA = {"offset_m": 1.0, "width_m": 1.2, "sill_m": 0.9, "height_m": 1.2}
CASA = {"nome": "RDC", "paredes": [parede("S", 0, 0, 8, 0, [PORTA]), parede("N", 0, 6, 8, 6, [JANELA]), parede("O", 0, 0, 0, 6), parede("E", 8, 0, 8, 6),
                                   parede("I", 4, 0, 4, 6)],
        "faixas": [{"id": "L1", "tipo": "laje", "ret": (0, 0, 8, 2)}, {"id": "L2", "tipo": "laje", "ret": (0, 2, 8, 4)},
                   {"id": "L3", "tipo": "laje", "ret": (0, 4, 8, 6)}]}


def test_base_das_paredes_conta_cada_cantoneira_e_holddown():
    r = L.calcular([CASA])
    por = lambda tipo, w: [x for x in r["ligadores"] if x["tipo"] == tipo and x["parede"] == w]
    # S: porta de 3 a 4 m → troços de 3 m e 4 m → 3 + 4 cantoneiras, hold-down nas 2 pontas de cada troço
    assert len(por("cantoneira", "S")) == 7 and len(por("holddown", "S")) == 4
    assert sorted(x["x"] for x in por("holddown", "S")) == [0.0, 3.0, 4.0, 8.0]
    # N: a janela (peitoril 0,9 m) não corta a base → 8 cantoneiras, 2 hold-down
    assert len(por("cantoneira", "N")) == 8 and len(por("holddown", "N")) == 2
    assert len(por("cantoneira", "O")) == 6 and len(por("cantoneira", "I")) == 6
    assert r["totais"]["cantoneira"]["quantidade"] == 7 + 8 + 6 + 6 + 6
    assert r["totais"]["holddown"]["quantidade"] == 4 + 2 + 2 + 2 + 2
    # cada ligador traz as suas fixações: 33 × 10 + 12 × 15 parafusos na parede, 33 × 2 ancoragens ao betão, 12 varões M16
    assert r["totais"]["paraf_ligador"]["quantidade"] == 33 * 10 + 12 * 15
    assert r["totais"]["anc_betao"]["quantidade"] == 66 and r["totais"]["anc_m16"]["quantidade"] == 12


def test_juntas_verticais_L_T_e_parafusos_pela_altura():
    r = L.calcular([CASA])
    jv = [j for j in r["juntas"] if j["produto"] == "paraf_canto"]
    assert sorted(j["tipo"][-1] for j in jv) == ["L", "L", "L", "L", "T", "T"]          # 4 cantos + a parede interior em S e em N
    assert all(j["parafusos"] == 11 and j["comprimento_m"] == 3.0 for j in jv)           # 3 m a 0,30 m → 10 intervalos, 11 parafusos
    assert r["totais"]["paraf_canto"]["quantidade"] == 66


def test_laje_sobre_paredes_e_juntas_entre_faixas():
    r = L.calcular([CASA])
    jh = {j["entre"][0]: j for j in r["juntas"] if j["produto"] == "paraf_laje_parede"}
    assert jh["S"]["comprimento_m"] == 8.0 and jh["S"]["parafusos"] == 33                # 8 m a 0,25 m → 32 intervalos
    assert jh["I"]["comprimento_m"] == 6.0 and jh["I"]["parafusos"] == 25                # atravessa as 3 faixas, conta uma vez
    jf = [j for j in r["juntas"] if j["produto"] == "paraf_faixa"]
    assert len(jf) == 2 and all(j["comprimento_m"] == 8.0 and j["parafusos"] == 28 * 2 for j in jf)   # L1–L2 e L2–L3; L1 e L3 não se tocam
    # fita: 6 juntas verticais de 3 m + topo das 5 paredes (8 + 8 + 6 + 6 + 6) + 2 juntas de faixas de 8 m
    assert r["totais"]["fita"]["quantidade"] == pytest.approx(18 + 34 + 16)
    assert r["parafusos_total"] == sum(v["quantidade"] for k, v in r["totais"].items() if k.startswith("paraf_"))


def test_piso_de_cima_fixa_na_laje_e_parametros_editaveis():
    cima = {**CASA, "nome": "Piso 1", "faixas": [{"id": "C1", "tipo": "cobertura", "ret": (0, 0, 8, 6)}]}
    r = L.calcular([CASA, cima], {"cantoneira_esp_m": 0.5})
    assert r["parametros"]["cantoneira_esp_m"]["valor"] == 0.5 and "hipótese" in r["parametros"]["cantoneira_esp_m"]["fonte"]
    assert r["totais"]["cantoneira"]["quantidade"] == 2 * (6 + 8 + 16 + 12 + 12 + 12)   # o dobro das cantoneiras, nos dois pisos
    assert r["totais"]["anc_betao"]["quantidade"] == 66 * 2                              # só o piso térreo vai ao betão
    assert r["totais"]["paraf_piso"]["quantidade"] == 66 * 10                            # o piso de cima aparafusa à laje CLT
    assert not [j for j in r["juntas"] if j["piso"] == "Piso 1" and j["produto"] == "paraf_faixa"]   # uma só faixa: sem junta


def test_avisos_troco_curto_cruzamento_e_piso_sem_geometria():
    estreito = parede("P", 0, 0, 3, 0, [{"offset_m": 0.2, "width_m": 0.9, "sill_m": 0, "height_m": 2.1}])
    cruz = [parede("A", 0, 5, 4, 5), parede("B", 2, 3, 2, 7)]
    r = L.calcular([{"nome": "RDC", "paredes": [estreito, *cruz]}, {"nome": "Sótão", "paredes": []}])
    assert any("troço de 0.20 m" in a for a in r["avisos"]) and any("sem faixas" in a for a in r["avisos"]) and any("Sótão" in a for a in r["avisos"])
    x = [j for j in r["juntas"] if j["tipo"].endswith("X")]
    assert len(x) == 1 and x[0]["parafusos"] == 22                                       # cruzamento: duas filas
    assert math.isclose(sum(1 for g in r["ligadores"] if g["parede"] == "P" and g["tipo"] == "cantoneira"), 2)   # só o troço de 1,9 m


def test_linhas_para_o_estudo_e_adaptador_do_calculo():
    class Eixo:                                                  # como o WallAxis do clt_walls
        def __init__(self, **k):
            self.__dict__.update(k)
    q = {"_desenhos": ([("RDC", [Eixo(id="S", x1=0, y1=0, x2=8, y2=0, thickness_mm=100, height_m=3.0, base_z_m=0.0, openings=[])], [])], None),
         "pecas": [{"piso": "RDC", "elemento": "Laje", "rotulo": "L1 · 160 mm", "ret_m": (0, -1, 8, 1)},
                   {"piso": "RDC", "elemento": "Paredes", "rotulo": "S"}]}
    pisos = L.pisos_do_calculo(q)
    assert len(pisos) == 1 and len(pisos[0]["faixas"]) == 1
    rows = L.linhas(L.calcular(pisos))
    assert {r["capitulo"] for r in rows} == {"ligacoes"} and all(r["contado"] and r["regra"]["pt"] and r["regra"]["en"] for r in rows)
    assert all(float(r["quantidade"]).is_integer() for r in rows if r["unidade"] == "un")
    assert next(r for r in rows if "Cantoneira" in r["nome"]["pt"])["quantidade"] == 8


def test_complementos_trocam_os_racios_pela_contagem():
    from bim_studio import clt_complements as CC
    entrada = {"floors": [{"name": "RDC", "height_m": "3", "walls": [{"thickness_mm": "100", "layers": 5, "length_m": "34"}], "roof_buildup_m2": "48"}]}
    racio = [r for r in CC.lines(entrada) if r["capitulo"] == "ligacoes"]
    contado = [r for r in CC.lines(entrada, ligacoes=L.linhas(L.calcular([CASA]))) if r["capitulo"] == "ligacoes"]
    assert len(racio) == 4 and not any(r.get("contado") for r in racio)
    assert contado and all(r["contado"] for r in contado)
    assert next(r for r in contado if "Cantoneira" in r["nome"]["pt"])["quantidade"] == 33
    assert CC.totals(contado)["custo_eur"] > 0
