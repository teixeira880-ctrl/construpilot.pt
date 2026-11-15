"""Geometria v3: regras unitárias + banco de ensaio sobre plantas de referência com verdade exata.

O banco de ensaio é o travão de não-regressão: uma alteração que piore a leitura de uma planta de referência falha aqui.
Limites por fonte (medidos em 12/11/2026, com margem): DXF e PDF vetorial exatos; imagens e digitalizações ≤ 0,5 %;
1:100 digitalizado a 150 dpi é o caso-limite assumido (paredes de 6 px) e só tem de manter o que já faz.
"""
import math

import pytest
from shapely.geometry import box

from engines.geometria import coerencia, escala, vetor
from engines.geometria.banco import PASTA, correr


def linhas_rect(x0, y0, x1, y1):
    pts = [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]
    return [{"p": (a, b), "camada": "", "largura": None} for a, b in zip(pts, pts[1:] + pts[:1])]


def parede(x0, y0, x1, y1, buraco=None):
    """Contorno de um retângulo de parede, opcionalmente com um vão [a, b] no sentido do comprimento (horizontal)."""
    if not buraco:
        return linhas_rect(x0, y0, x1, y1)
    a, b = buraco
    return ([{"p": ((x0, y0), (a, y0))}, {"p": ((b, y0), (x1, y0))}, {"p": ((x0, y1), (a, y1))}, {"p": ((b, y1), (x1, y1))},
             {"p": ((x0, y0), (x0, y1))}, {"p": ((x1, y0), (x1, y1))}, {"p": ((a, y0), (a, y1))}, {"p": ((b, y0), (b, y1))}])


def caixa(W=6.0, H=4.0, e=.2, u=100.0):
    """Divisão W×H (exterior) com paredes de espessura e, em unidades u por metro."""
    s = u
    return linhas_rect(0, 0, W * s, H * s) + linhas_rect(e * s, e * s, (W - e) * s, (H - e) * s)


# ---------------------------------------------------------------- divisões

def test_divisao_simples_area_exata():
    a = vetor.analisar(caixa(), 100.0)
    assert a["ok"] and len(a["divisoes"]) == 1
    assert a["divisoes"][0]["area_m2"] == pytest.approx(5.6 * 3.6, rel=1e-6)
    assert a["area_implantacao_m2"] == pytest.approx(24.0, rel=1e-6)
    assert a["paredes"]["espessura_exterior_m"] == pytest.approx(.2, abs=.005)


def test_mobiliario_nao_corta_a_divisao():
    movel = linhas_rect(100, 100, 260, 160) + [{"p": ((20, 250), (300, 250))}]   # cama + bancada encostada à parede
    a = vetor.analisar(caixa() + movel, 100.0)
    assert len(a["divisoes"]) == 1
    assert a["divisoes"][0]["area_m2"] == pytest.approx(5.6 * 3.6, rel=1e-6)


def test_faixa_de_cotas_nunca_e_divisao():
    cota = [{"p": ((0, -120), (600, -120))}, {"p": ((0, -130), (0, 0))}, {"p": ((600, -130), (600, 0))}]
    a = vetor.analisar(caixa() + cota, 100.0)
    assert [round(d["area_m2"], 2) for d in a["divisoes"]] == [20.16]


def test_vao_so_fechado_quando_as_duas_faces_estao_interrompidas():
    # duas divisões separadas por uma parede de 0,10 com uma porta de 0,80: a porta é fechada (2 divisões, não 1)
    u = 100.0
    base = linhas_rect(0, 0, 800, 400) + linhas_rect(20, 20, 780, 380)
    porta = parede(20, 195, 780, 205, buraco=(300, 380))
    a = vetor.analisar(base + porta, u)
    assert len(a["divisoes"]) == 2
    assert a["vaos"]["portas"] == 1
    # um alinhamento acidental de UMA só linha com uma lacuna não cria ponte
    soltas = [{"p": ((100, 100), (200, 100))}, {"p": ((300, 100), (400, 100))}]
    b = vetor.analisar(caixa(8, 4, .2) + soltas, u)
    assert b["estatisticas"]["pontes"] == 0


def test_folha_de_porta_fechada_absorvida_pela_divisao():
    u = 100.0
    folha = [{"p": ((300, 20), (300, 100))}, {"p": ((300, 100), (380, 20))}]   # folha + traço de fecho (triângulo estreito)
    a = vetor.analisar(caixa() + folha, u)
    assert len(a["divisoes"]) == 1
    assert a["divisoes"][0]["area_m2"] == pytest.approx(20.16, rel=1e-6)


def test_area_escrita_e_nome_lidos():
    textos = [{"text": "Sala", "x": 250, "y": 180, "w": 30, "h": 10}, {"text": "20,16 m²", "x": 250, "y": 200, "w": 40, "h": 10}]
    a = vetor.analisar(caixa(), 100.0, textos=textos)
    d = a["divisoes"][0]
    assert d["nomes"] == ["Sala"] and d["areas_escritas_m2"] == [20.16]


def test_escala_desconhecida_bloqueia():
    a = vetor.analisar(caixa(), 0)
    assert not a["ok"] and a["motivo"] == "escala desconhecida"


# ---------------------------------------------------------------- escala

def test_escala_confirmada_por_duas_fontes():
    pt_m = escala.PT_POR_M_PAPEL / 50
    c = escala.consenso(escala.candidatos_declarados([50], escala.PT_POR_M_PAPEL)
                        + [escala.candidato_cotas([{"x1": 0, "y1": 0, "x2": 12 * pt_m, "y2": 0, "value_m": 12.0},
                                                   {"x1": 0, "y1": 0, "x2": 0, "y2": 9 * pt_m, "value_m": 9.0}])])
    assert c["estado"] == "confirmada" and c["u_por_m"] == pytest.approx(pt_m, rel=1e-6)


def test_escala_em_conflito_assinalada():
    pt_m = escala.PT_POR_M_PAPEL / 50
    c = escala.consenso(escala.candidatos_declarados([100], escala.PT_POR_M_PAPEL)
                        + [escala.candidato_cotas([{"comprimento_u": 5 * pt_m, "value_m": 5.0}])])
    assert c["estado"] == "conflito"
    assert c["u_por_m"] == pytest.approx(pt_m, rel=1e-6)    # ficam as cotas (fonte mais forte que o texto)


def test_duas_escalas_na_folha_escolhe_a_que_as_cotas_confirmam():
    pt_m = escala.PT_POR_M_PAPEL / 50
    textos = [{"text": "PLANTA 1:50"}, {"text": "PORMENOR 1/20"}]
    c = escala.consenso(escala.candidatos_declarados(escala.escalas_declaradas(textos), escala.PT_POR_M_PAPEL)
                        + [escala.candidato_cotas([{"comprimento_u": 4 * pt_m, "value_m": 4.0}])])
    assert c["estado"] == "confirmada" and c["u_por_m"] == pytest.approx(pt_m, rel=1e-6)


def test_cota_falsa_rejeitada():
    c = escala.candidato_cotas([{"comprimento_u": 100, "value_m": 1.0}, {"comprimento_u": 200, "value_m": 2.0},
                                {"comprimento_u": 300, "value_m": 3.0}, {"comprimento_u": 100, "value_m": 7.0}])
    assert c["u_por_m"] == pytest.approx(100) and c["rejeitadas"] == 1


# ---------------------------------------------------------------- confiança

def test_confianca_vermelho_quando_area_escrita_diverge():
    an = {"divisoes": [{"area_m2": 20.0, "areas_escritas_m2": [18.0], "nomes": ["Sala"]}], "area_implantacao_m2": None}
    r = coerencia.avaliar(an, {"estado": "confirmada"}, "pdf_vetorial")
    assert r["divisoes"][0]["nivel"] == "vermelho" and r["nivel_global"] == "vermelho"


def test_confianca_verde_vetorial_escala_confirmada():
    an = {"divisoes": [{"area_m2": 20.0, "areas_escritas_m2": [], "nomes": ["Sala"]}]}
    assert coerencia.avaliar(an, {"estado": "confirmada"}, "dxf")["divisoes"][0]["nivel"] == "verde"
    assert coerencia.avaliar(an, {"estado": "fonte_unica"}, "imagem")["divisoes"][0]["nivel"] == "laranja"


# ---------------------------------------------------------------- banco de ensaio (não-regressão)

LIMITES = {
    # fonte: (recall a 2 % mínimo, erro máximo de área %, erro de implantação %, erro paredes exteriores %)
    "dxf": (1.0, .1, .05, .05),
    "pdf": (1.0, .1, .05, .05),
    "png": (1.0, .5, .1, .1),
    "scan": (1.0, .5, .3, .2),
    "scan300": (1.0, .6, .1, .1),
}


@pytest.fixture(scope="module")
def banco():
    if not any(PASTA.glob("*.geo.json")):
        pytest.skip("plantas de referência ausentes (correr scripts/geometria_referencia.py)")
    return correr()


def _v(x):
    return 99.0 if x is None else abs(x)


def test_banco_de_ensaio(banco):
    falhas = []
    for chave, r in banco.items():
        planta, fonte = chave.split("/")
        if chave == "casa_c/scan":     # 1:100 a 150 dpi: caso-limite — não piorar
            if r["emparelhadas"] < 3 or _v(r["erro_max_pct"]) > 3.5:
                falhas.append(f"{chave}: piorou ({r})")
            continue
        rec, emax, eimp, eext = LIMITES[fonte]
        if r["recall_2pct"] < rec or _v(r["erro_max_pct"]) > emax or r["a_mais"]:
            falhas.append(f"{chave}: divisões {r['emparelhadas']}/{r['divisoes_verdade']} (+{r['a_mais']}), erro máx {r['erro_max_pct']} %")
        if _v(r["implantacao_pct"]) > eimp or _v(r["paredes_exteriores_pct"]) > eext:
            falhas.append(f"{chave}: implantação {r['implantacao_pct']} %, paredes exteriores {r['paredes_exteriores_pct']} %")
        if fonte in ("dxf", "pdf"):
            if r["escala"] != "confirmada":
                falhas.append(f"{chave}: escala {r['escala']}")
            if r["portas"][0] != r["portas"][1] or r["janelas"][0] != r["janelas"][1]:
                falhas.append(f"{chave}: vãos {r['portas']} {r['janelas']}")
            if _v(r["divisorias_pct"]) > 1.0:
                falhas.append(f"{chave}: divisórias {r['divisorias_pct']} %")
    assert not falhas, "\n".join(falhas)


def test_verdade_coerente():
    import json
    for gj in PASTA.glob("*.geo.json"):
        v = json.loads(gj.read_text(encoding="utf-8"))
        assert v["area_util_total_m2"] + v["area_paredes_m2"] == pytest.approx(v["area_implantacao_m2"], abs=.01)
        assert math.isclose(sum(d["area_m2"] for d in v["divisoes"].values()), v["area_util_total_m2"], abs_tol=.01)
        assert box(0, 0, 1, 1).area == 1
