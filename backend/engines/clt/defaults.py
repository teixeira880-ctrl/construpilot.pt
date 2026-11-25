"""Parâmetros por defeito do motor CLT (madeira lamelada-colada cruzada) e projeto de exemplo.

Composições, dimensões de prensa, conectores e passos de fixação são PARÂMETROS de projeto / fabricante: o motor não os
inventa, aplica-os à geometria. Cada regra tem a sua origem (`REGRAS_FONTE`); os valores marcados « prática corrente » não
são mínimos normativos e têm de ser confirmados pelo projeto de estabilidade (EN 1995-1-1) e pelas ETA do painel e dos
conectores adotados.
"""
from __future__ import annotations

import copy

# Composições-tipo (espessuras das lamelas em mm, camada exterior longitudinal). Confirmar com o catálogo do fabricante.
PAINEIS = {
    "CLT80-3s": {"esp": 80, "camadas": [20, 40, 20]},
    "CLT90-3s": {"esp": 90, "camadas": [30, 30, 30]},
    "CLT100-3s": {"esp": 100, "camadas": [30, 40, 30]},
    "CLT120-3s": {"esp": 120, "camadas": [40, 40, 40]},
    "CLT140-5s": {"esp": 140, "camadas": [30, 25, 30, 25, 30]},
    "CLT160-5s": {"esp": 160, "camadas": [40, 20, 40, 20, 40]},
    "CLT180-5s": {"esp": 180, "camadas": [40, 30, 40, 30, 40]},
    "CLT200-5s": {"esp": 200, "camadas": [40, 40, 40, 40, 40]},
    "CLT220-7s": {"esp": 220, "camadas": [40, 20, 40, 20, 40, 20, 40]},
    "CLT240-7s": {"esp": 240, "camadas": [30, 40, 30, 40, 30, 40, 30]},
}

# Pré-dimensionamento das lajes / coberturas pela esbelteza (vão / espessura). Não substitui a verificação EN 1995-1-1
# (ELU, deformação e vibrações §7.3) — o motor escolhe a primeira composição que respeita a esbelteza.
LAJES = ["CLT140-5s", "CLT160-5s", "CLT180-5s", "CLT200-5s", "CLT220-7s", "CLT240-7s"]

PARAFUSOS_STD = [60, 80, 100, 120, 140, 160, 180, 200, 220, 240, 260, 280, 300, 320, 340, 360, 380, 400, 440, 480, 520, 560, 600]

CONECTORES = {
    "esquadroBetao": {"nome": "Esquadro de corte madeira-betão 90×116 mm (tipo TITAN / AE116)", "pregos": 14, "ancora": "Bucha química + varão M12 classe 5.8"},
    "esquadroMadeira": {"nome": "Esquadro de corte madeira-madeira 90×116 mm (tipo TITAN / AE116)", "pregos": 14, "parafusos": 2},
    "holdDownBetao": {"nome": "Hold-down madeira-betão (tipo WHT / HTT)", "pregos": 20, "ancora": "Bucha química + varão M16 classe 8.8"},
    "holdDownMadeira": {"nome": "Hold-down madeira-madeira (tipo WHT / HTT) com varão roscado através da laje", "pregos": 20,
                        "ancora": "Varão roscado M16 + porca + anilha (atravessa a laje)"},
    "prego": "Prego anelado 4,0×60 (conectores metálicos)",
    "parafusoEsquadro": "Parafuso madeira 5,0×50 (conectores metálicos)",
    "parafusoEstrutural": "Parafuso autoperfurante madeira 8,0×{L}",
    "lambrim": {"nome": "Régua de junta LVL 27×100 mm (junta de lambrim)", "parafuso": "Parafuso autoperfurante madeira 5,0×60"},
    "elevacao": "Parafuso de elevação descartável 11×300",
}

REGRAS = {
    "esquadroPasso": 800,       # esquadros de corte ao longo da base de cada painel (mm)
    "esquadroExtremo": 300,     # distância do 1.º esquadro ao bordo do painel / vão (mm)
    "esquadroMin": 2,           # mínimo por painel
    "holdDownVaoMin": 900,      # hold-down de cada lado dos vãos com largura ≥ (mm)
    "cantoPasso": 300,          # parafusos estruturais nos cantos e T entre paredes (mm, ao longo da altura)
    "bordoPasso": 100,          # distância do 1.º parafuso ao bordo (mm)
    "penetracao": 80,           # penetração mínima no painel recetor (≈ 10 d para Ø8) (mm)
    "lajeApoioPasso": 300,      # laje → paredes de apoio (mm)
    "coberturaApoioPasso": 300, # cobertura → paredes / empenas / viga de cumeeira (mm)
    "lambrimPasso": 150,        # parafusos da régua de junta, por lado (mm)
    "elevacaoParede": 2,        # pontos de elevação por painel de parede
    "elevacaoLaje": 4,          # pontos de elevação por painel de laje / cobertura
    "juntaVaoMin": 300,         # distância mínima de uma junta vertical a um vão (mm)
    "vergaMin": 300,            # altura mínima de painel acima de um vão (mm)
    "esbelteza": 30,            # lajes: vão / espessura máximo
    "esbeltezaCobertura": 35,   # coberturas: vão / espessura máximo
    "perdaCamadas": 0.0,        # sem majoração: camadas por plano de corte / rolos
}

REGRAS_FONTE = {
    "esquadroPasso": "Prática corrente CLT; número exato pelo cálculo ao corte (EN 1995-1-1 §8 + ETA do esquadro)",
    "holdDownVaoMin": "Prática corrente CLT; posição e número exatos pelo cálculo ao derrubamento",
    "cantoPasso": "Prática corrente CLT (≤ 300 mm); validar pela ETA do parafuso",
    "penetracao": "EN 1995-1-1 §8.7 / ETA do parafuso (comprimento de penetração ≥ ≈ 10 d)",
    "lajeApoioPasso": "Prática corrente CLT (≤ 300 mm); validar pelo cálculo do diafragma",
    "lambrimPasso": "Prática corrente CLT (≤ 150 mm por lado); validar pelo cálculo do diafragma / parede",
    "esbelteza": "Pré-dimensionamento corrente (L/30 lajes de habitação, L/35 coberturas); verificar EN 1995-1-1 §7.3 (vibrações)",
    "composicoes": "Composições-tipo de lamelas; confirmar com o catálogo e a ETA do fabricante",
    "prensa": "Dimensões máximas de prensa / transporte do fabricante (ETA, anexo de dimensões)",
}

CAMADAS = {
    "MEMB_RESP": {"nome": "Membrana respirável de fachada (Sd ≤ 0,1 m)", "tipo": "rolo", "largura": 1500, "comprimento": 50000, "sobreposicao": 100},
    "FIBRA120": {"nome": "Isolamento exterior em fibra de madeira 120 mm (ETICS)", "tipo": "placa", "esp": 120, "w": 1200, "h": 600},
    "ETICS_BUCHA": {"nome": "Bucha de fixação ETICS p/ madeira (parafuso)", "tipo": "fixacao", "porPlaca": None},
    "PARAVAPOR": {"nome": "Membrana pára-vapor / estanquidade ao ar", "tipo": "rolo", "largura": 1500, "comprimento": 50000, "sobreposicao": 100},
    "FIBRA200": {"nome": "Isolamento de cobertura em fibra de madeira 200 mm", "tipo": "placa", "esp": 200, "w": 1200, "h": 600},
    "SUBTELHA": {"nome": "Subtelha / membrana respirável de cobertura", "tipo": "rolo", "largura": 1500, "comprimento": 50000, "sobreposicao": 100},
    "IMPERM": {"nome": "Impermeabilização de cobertura plana (membrana)", "tipo": "rolo", "largura": 1000, "comprimento": 10000, "sobreposicao": 100},
    "PIR160": {"nome": "Isolamento de cobertura plana PIR 160 mm", "tipo": "placa", "esp": 160, "w": 1200, "h": 600},
}

SELANTES = {
    "fitaAr": {"nome": "Fita de estanquidade ao ar (juntas de painéis)", "rolo": 25000},
    "bandaBase": {"nome": "Banda de corte de capilaridade EPDM sob paredes (sobre betão)", "rolo": 20000},
    "bandaPiso": {"nome": "Banda de compressão / acústica sob paredes de andar", "rolo": 20000},
}


def tipos_parede() -> dict:
    return {
        "EXT": {"nome": "Parede exterior CLT", "painel": "CLT100-3s", "visivel": False,
                "exterior": [{"camada": "MEMB_RESP"}, {"camada": "FIBRA120"}], "interior": []},
        "INT": {"nome": "Parede interior CLT", "painel": "CLT100-3s", "visivel": False, "faceA": [], "faceB": []},
    }


def base(country: str = "PT", produto: str = "generico_c24") -> dict:
    from engines.calc_lots.clt_produtos import produto as prod
    pr = prod(produto)
    return {
        "country": country.upper(),
        "produto": pr["chave"],
        "produtoNome": pr["nome"], "eta": pr["eta"], "classe": pr["classe"],
        "densidade": 470,                # kg/m³ de cálculo de massas (madeira a 12 % + cola) — parâmetro
        "prensa": {"W": pr["largura_max_m"] * 1000, "L": pr["comprimento_max_m"] * 1000,
                   # larguras de produção dos painéis brutos (mm) — confirmar com o fabricante; a última = largura máxima de prensa
                   "larguras": [w for w in (2400, 2500, 2750, 2950, 3000, 3250, 3500) if w < pr["largura_max_m"] * 1000] + [pr["largura_max_m"] * 1000]},
        "paineis": copy.deepcopy(PAINEIS),
        "lajes": list(LAJES),
        "conectores": copy.deepcopy(CONECTORES),
        "regras": copy.deepcopy(REGRAS),
        "camadas": copy.deepcopy(CAMADAS),
        "selantes": copy.deepcopy(SELANTES),
        "tiposParede": tipos_parede(),
        "cobertura": {"exterior": [{"camada": "PARAVAPOR"}, {"camada": "FIBRA200"}, {"camada": "SUBTELHA"}],
                      "plana": [{"camada": "PARAVAPOR"}, {"camada": "PIR160"}, {"camada": "IMPERM"}], "vigaCumeeira": "GL24h"},
        "soClt": False,
        "perimetros": [], "paredes": [], "pisos": [], "coberturas": [],
        "precos": {}, "corte": {"kerf": 10},
        "hipoteses": [],
    }


def exemplo(produto: str = "generico_c24") -> dict:
    """Moradia de exemplo R/C + 1.º andar (10 × 8 m) — mesma geometria do exemplo LSF."""
    p = base("PT", produto)
    p["nome"] = "Moradia exemplo CLT — R/C + 1.º andar"
    p["perimetros"] = [
        {"id": "RC", "nivel": "R/C", "tipo": "EXT", "z0": 0, "altura": 2700, "apoio": "betao",
         "pontos": [[0, 0], [10000, 0], [10000, 8000], [0, 8000]],
         "vaos": {
             "0": [{"id": "J1", "tipo": "janela", "x": 1500, "largura": 1200, "altura": 1200, "peitoril": 900},
                   {"id": "P1", "tipo": "porta", "x": 4500, "largura": 1000, "altura": 2100},
                   {"id": "J2", "tipo": "janela", "x": 7300, "largura": 1200, "altura": 1200, "peitoril": 900}],
             "1": [{"id": "J3", "tipo": "janela", "x": 5200, "largura": 1500, "altura": 1200, "peitoril": 900}],
             "2": [{"id": "P2", "tipo": "porta", "x": 2000, "largura": 2400, "altura": 2100}],
             "3": [{"id": "J4", "tipo": "janela", "x": 5600, "largura": 1200, "altura": 1200, "peitoril": 900}],
         }},
        {"id": "P1", "nivel": "1.º andar", "tipo": "EXT", "z0": "auto:PISO1", "altura": 2600, "apoio": "laje",
         "pontos": [[0, 0], [10000, 0], [10000, 8000], [0, 8000]],
         "vaos": {
             "0": [{"id": "J5", "tipo": "janela", "x": 1500, "largura": 1200, "altura": 1200, "peitoril": 900},
                   {"id": "J6", "tipo": "janela", "x": 7300, "largura": 1200, "altura": 1200, "peitoril": 900}],
             "2": [{"id": "J7", "tipo": "janela", "x": 3800, "largura": 2400, "altura": 1300, "peitoril": 800}],
         }},
    ]
    p["paredes"] = [
        {"id": "I1", "nivel": "R/C", "tipo": "INT", "z0": 0, "altura": 2700, "a": [0, 4000], "b": [10000, 4000], "alinhamento": "eixo", "apoio": "betao",
         "vaos": [{"id": "P3", "tipo": "porta", "x": 2500, "largura": 900, "altura": 2100},
                  {"id": "P4", "tipo": "porta", "x": 6500, "largura": 900, "altura": 2100}]},
        {"id": "I2", "nivel": "R/C", "tipo": "INT", "z0": 0, "altura": 2700, "a": [5000, 4000], "b": [5000, 8000], "alinhamento": "eixo", "apoio": "betao",
         "vaos": [{"id": "P5", "tipo": "porta", "x": 1000, "largura": 900, "altura": 2100}]},
    ]
    p["pisos"] = [
        {"id": "PISO1-A", "grupo": "PISO1", "nivel": "1.º andar", "x0": 0, "y0": 0, "x1": 10000, "y1": 4000, "z": 2700, "vao": "y"},
        {"id": "PISO1-B", "grupo": "PISO1", "nivel": "1.º andar", "x0": 0, "y0": 4000, "x1": 10000, "y1": 8000, "z": 2700, "vao": "y"},
    ]
    p["coberturas"] = [
        {"id": "COB", "x0": 0, "y0": 0, "x1": 10000, "y1": 8000, "z": "auto:P1", "cumeeira": "x", "inclinacao": 30, "beiral": 500},
    ]
    return p
