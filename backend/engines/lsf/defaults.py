"""Parâmetros por defeito do motor LSF e projeto de exemplo.

Perfis, placas e regras de fixação são PARÂMETROS de projeto / fabricante: o motor não os inventa, aplica-os à geometria.
Cada regra de fixação tem a sua origem (`REGRAS_FONTE`); os valores marcados « prática corrente » não são mínimos normativos e
têm de ser confirmados pelo projeto de estabilidade e pela ficha técnica do sistema LSF adotado.
"""
from __future__ import annotations

import copy

PERFIS = {
    "C90_12": {"tipo": "C", "h": 90, "b": 43, "c": 10, "t": 1.2},
    "C90_10": {"tipo": "C", "h": 90, "b": 43, "c": 10, "t": 1.0},
    "C70_08": {"tipo": "C", "h": 70, "b": 40, "c": 10, "t": 0.8},
    "C150_15": {"tipo": "C", "h": 150, "b": 43, "c": 15, "t": 1.5},
    "C200_15": {"tipo": "C", "h": 200, "b": 50, "c": 15, "t": 1.5},
    "C250_20": {"tipo": "C", "h": 250, "b": 50, "c": 15, "t": 2.0},
    "F50_12": {"tipo": "F", "h": 50, "t": 1.2},
}

PLACAS = {
    "OSB12": {"nome": "OSB/3 12 mm", "esp": 12, "w": 1250, "h": 2500, "parafuso": "Autoperfurante c/ asas 4,2×32", "bordo": 150, "interior": 300},
    "OSB18": {"nome": "OSB/3 18 mm", "esp": 18, "w": 2500, "h": 1250, "parafuso": "Autoperfurante c/ asas 4,2×38", "bordo": 150, "interior": 300},
    "OSB22": {"nome": "OSB/3 22 mm macho-fêmea", "esp": 22, "w": 2500, "h": 675, "parafuso": "Autoperfurante c/ asas 4,8×45", "bordo": 150,
              "interior": 300, "rodar": False},
    "GC125": {"nome": "Gesso cartonado 12,5 mm (tipo A)", "esp": 12.5, "w": 1200, "h": 3000, "parafuso": "Trombeta 3,5×25", "bordo": 250, "interior": 250},
    "GC125H": {"nome": "Gesso cartonado hidrófugo 12,5 mm (tipo H)", "esp": 12.5, "w": 1200, "h": 3000, "parafuso": "Trombeta 3,5×25", "bordo": 250,
               "interior": 250},
    "GC15F": {"nome": "Gesso cartonado resistente ao fogo 15 mm (tipo F)", "esp": 15, "w": 1200, "h": 3000, "parafuso": "Trombeta 3,5×25", "bordo": 250,
              "interior": 250},
}

REGRAS = {
    "parafusoAco": "Autoperfurante cabeça wafer 4,2×13 (aço/aço)",
    "montanteGuia": 4,        # por montante: 1 por banzo × 2 banzos × 2 extremos
    "caixaoPasso": 300,       # costura montante rei + montante de apoio (caixão) — passo (mm), por face
    "vergaApoio": 4,          # por perfil de verga, em cada extremo
    "vergaGuiaPasso": 300,    # guias da verga aos perfis C — passo (mm), por banzo
    "peitorilExtremo": 2,     # guia de peitoril, em cada extremo
    "bloqueadorExtremo": 2,   # bloqueador, em cada extremo
    "fitaExtremo": 6,         # fita de contraventamento, em cada extremo
    "fitaCruzamento": 1,      # fita, em cada montante atravessado
    "vigaRim": 4,             # viga de piso à guia de bordadura, por extremo
    "asnaNoBanzo": 4,         # diagonal de asna, por extremo
    "asnaApoio": 6,           # nó de apoio (banzo superior + inferior)
    "asnaCumeeira": 6,        # nó de cumeeira
    "asnaParede": 2,          # asna à guia superior da parede (por apoio)
    "pisoParede": 2,          # guia de bordadura à guia superior da parede, por viga
    "ligacaoPasso": 300,      # costura entre paredes em cantos e T — passo (mm)
}

REGRAS_FONTE = {
    "montanteGuia": "Prática corrente LSF (1 parafuso por banzo e por extremo); confirmar com a ficha do sistema",
    "caixaoPasso": "Prática corrente LSF (costura de perfis compostos ≤ 300 mm)",
    "vergaApoio": "Prática corrente LSF; validar pelo cálculo da verga (EN 1993-1-3)",
    "vergaGuiaPasso": "Prática corrente LSF (≤ 300 mm)",
    "bloqueadorExtremo": "Prática corrente LSF",
    "fitaExtremo": "Prática corrente LSF; número exato pelo cálculo do contraventamento",
    "vigaRim": "Prática corrente LSF; validar pelo cálculo da ligação",
    "asnaNoBanzo": "Prática corrente LSF; número exato pelo cálculo da asna",
    "ligacaoPasso": "Prática corrente LSF (≤ 300 mm)",
    "placas": "Passos de aparafusamento das placas: ficha técnica do fabricante (OSB 150/300 mm; gesso cartonado 250 mm, EN 520 / sistemas correntes)",
}


def tipos_parede() -> dict:
    return {
        "EXT": {
            "nome": "Parede exterior resistente",
            "montante": "C90_12", "espacamento": 600, "folgaMontante": 0,
            "verga": "C150_15", "bloqueadores": 1, "bloqueadorAuto": True,
            "contraventamento": "OSB",
            "fita": "F50_12",
            "exterior": [{"placa": "OSB12"}],
            "interior": [{"placa": "GC125"}],
            "isolamento": {"nome": "Lã mineral", "esp": 90, "m2PorEmbalagem": None},
            "etics": {"nome": "ETICS — EPS", "esp": 60, "placaW": 1000, "placaH": 500, "bucha": None, "cola": None,
                      "rede": {"largura": 1000, "sobreposicao": 100, "rolo": 50000}},
            "membrana": None,
            "ancoragem": {"nome": "Bucha química + varão M12", "extremo": 150, "passoMax": 600},
            "holdDowns": {"extremos": True, "vaos": True, "parafusos": None},
        },
        "INT": {
            "nome": "Divisória interior",
            "montante": "C70_08", "espacamento": 600, "folgaMontante": 0,
            "verga": "C150_15", "bloqueadores": 0, "bloqueadorAuto": False,
            "contraventamento": "nenhum",
            "faceA": [{"placa": "GC125"}],
            "faceB": [{"placa": "GC125"}],
            "isolamento": {"nome": "Lã mineral", "esp": 70, "m2PorEmbalagem": None},
            "ancoragem": {"nome": "Bucha metálica M8", "extremo": 150, "passoMax": 1000},
            "holdDowns": {"extremos": False, "vaos": False, "parafusos": None},
        },
    }


def base(country: str = "PT") -> dict:
    """Parâmetros completos sem geometria (perfis, placas, regras, tipos de parede)."""
    return {
        "country": country.upper(),
        "aco": {"densidade": 7850, "grau": "S350GD", "galvanizacao": "Z275"},
        "perfis": copy.deepcopy(PERFIS),
        "placas": copy.deepcopy(PLACAS),
        "regras": copy.deepcopy(REGRAS),
        "tiposParede": tipos_parede(),
        "perimetros": [], "paredes": [], "pisos": [], "coberturas": [],
        "precos": {}, "barraComercial": 6000, "corte": {"kerf": 3},
        "hipoteses": [],
    }


def exemplo() -> dict:
    """Moradia de exemplo R/C + 1.º andar (10 × 8 m) — mesma geometria dos testes."""
    p = base("PT")
    p["nome"] = "Moradia exemplo — R/C + 1.º andar"
    p["perimetros"] = [
        {"id": "RC", "tipo": "EXT", "z0": 0, "altura": 2700,
         "pontos": [[0, 0], [10000, 0], [10000, 8000], [0, 8000]],
         "vaos": {
             "0": [{"id": "J1", "tipo": "janela", "x": 1500, "largura": 1200, "altura": 1200, "peitoril": 900},
                   {"id": "P1", "tipo": "porta", "x": 4500, "largura": 1000, "altura": 2100},
                   {"id": "J2", "tipo": "janela", "x": 7300, "largura": 1200, "altura": 1200, "peitoril": 900}],
             "1": [{"id": "J3", "tipo": "janela", "x": 5200, "largura": 1500, "altura": 1200, "peitoril": 900}],
             "2": [{"id": "P2", "tipo": "porta", "x": 2000, "largura": 2400, "altura": 2100}],
             "3": [{"id": "J4", "tipo": "janela", "x": 5600, "largura": 1200, "altura": 1200, "peitoril": 900}],
         }},
        {"id": "P1", "tipo": "EXT", "z0": "auto:PISO1", "altura": 2600,
         "pontos": [[0, 0], [10000, 0], [10000, 8000], [0, 8000]],
         "vaos": {
             "0": [{"id": "J5", "tipo": "janela", "x": 1500, "largura": 1200, "altura": 1200, "peitoril": 900},
                   {"id": "J6", "tipo": "janela", "x": 7300, "largura": 1200, "altura": 1200, "peitoril": 900}],
             "2": [{"id": "J7", "tipo": "janela", "x": 3800, "largura": 2400, "altura": 1300, "peitoril": 800}],
         }},
    ]
    p["paredes"] = [
        {"id": "I1", "tipo": "INT", "z0": 0, "altura": 2700, "a": [0, 4000], "b": [10000, 4000], "alinhamento": "eixo",
         "vaos": [{"id": "P3", "tipo": "porta", "x": 2500, "largura": 900, "altura": 2100},
                  {"id": "P4", "tipo": "porta", "x": 6500, "largura": 900, "altura": 2100}]},
        {"id": "I2", "tipo": "INT", "z0": 0, "altura": 2700, "a": [5000, 4000], "b": [5000, 8000], "alinhamento": "eixo",
         "vaos": [{"id": "P5", "tipo": "porta", "x": 1000, "largura": 900, "altura": 2100}]},
    ]
    p["pisos"] = [
        {"id": "PISO1-A", "grupo": "PISO1", "x0": 0, "y0": 0, "x1": 10000, "y1": 4000, "z": 2700, "vao": "y", "viga": "C200_15",
         "espacamento": 600, "placa": "OSB22", "travamentoMax": 2500},
        {"id": "PISO1-B", "grupo": "PISO1", "x0": 0, "y0": 4000, "x1": 10000, "y1": 8000, "z": 2700, "vao": "y", "viga": "C200_15",
         "espacamento": 600, "placa": "OSB22", "travamentoMax": 2500},
    ]
    p["coberturas"] = [
        {"id": "COB", "x0": 0, "y0": 0, "x1": 10000, "y1": 8000, "z": "auto:P1", "cumeeira": "x", "inclinacao": 30, "beiral": 500,
         "espacamento": 600, "banzo": "C90_12", "diagonal": "C90_10", "placa": "OSB12",
         "subtelha": {"nome": "Subtelha / membrana", "larguraRolo": 1500, "comprimentoRolo": 50000, "sobreposicao": 100}},
    ]
    return p
