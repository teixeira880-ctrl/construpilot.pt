"""Parâmetros por defeito do motor de construção tradicional (estrutura porticada de betão armado + alvenarias).

Unidades de alvenaria, cargas, betão, aço e recobrimentos são PARÂMETROS de projeto / fabricante: o motor não os inventa,
aplica-os à geometria lida na planta e dimensiona cada elemento pelos motores ConstruPilot (NP EN 1992-1-1, NP EN 1997-1).
"""
from __future__ import annotations

import copy

UNIDADES = {
    # alvenaria: comprimento × altura × espessura (mm); junta (mm)
    "T30x20x22": {"nome": "Tijolo cerâmico furado 30×20×22 cm", "l": 300, "h": 200, "t": 220, "junta": 10},
    "T30x20x15": {"nome": "Tijolo cerâmico furado 30×20×15 cm", "l": 300, "h": 200, "t": 150, "junta": 10},
    "T30x20x11": {"nome": "Tijolo cerâmico furado 30×20×11 cm", "l": 300, "h": 200, "t": 110, "junta": 10},
    "B50x20x20": {"nome": "Bloco de betão 50×20×20 cm", "l": 500, "h": 200, "t": 200, "junta": 10},
    "B50x20x15": {"nome": "Bloco de betão 50×20×15 cm", "l": 500, "h": 200, "t": 150, "junta": 10},
}

CAMADAS = {
    "ETICS_EPS60": {"nome": "ETICS — placas EPS 60 mm (sistema certificado)", "tipo": "placa", "esp": 60, "w": 1000, "h": 500},
    "REBOCO_INT": {"nome": "Reboco / estuque interior (15 mm)", "tipo": "area", "esp": 15},
    "REBOCO_EXT": {"nome": "Reboco exterior tradicional (20 mm)", "tipo": "area", "esp": 20},
}

REGRAS = {
    "vaoMaxPilares": 5000,      # distância máxima entre pilares ao longo de uma parede resistente (mm)
    "pilarB": 220, "pilarH": 300,          # secção mínima dos pilares (mm) — b = espessura da parede exterior
    "vigaB": 220, "vigaHmin": 300,          # vigas: b = espessura da parede; h mínimo (mm)
    "vigaFundB": 300, "vigaFundH": 400,     # vigas de fundação (lintéis) sob as paredes do R/C
    "lajeHmin": 150, "lajeHmax": 300,       # espessura das lajes maciças (mm)
    "sapataHmin": 400, "sapataBmin": 800, "profundidadeFundacao": 800, "folgaEscavacao": 300, "limpeza": 100,
    "vergaH": 200, "vergaApoio": 200,       # vergas sobre os vãos (altura, apoio de cada lado)
    "massameH": 150, "enrocamento": 150,    # pavimento térreo
    "q_adm_kpa": 200,           # tensão admissível do terreno (estudo geotécnico) — HIPÓTESE se não indicada
    "g2_piso": 2.5, "q_piso": 2.0,          # kN/m² revestimentos + divisórias / sobrecarga habitação (EN 1991-1-1 A)
    "g2_cob": 2.0, "q_cob": 0.4,            # cobertura não acessível (cat. H)
    "gamaAlvenaria": 11.0,      # kN/m³ (alvenaria de tijolo furado rebocada) — ficha do fabricante
    "fck": 25, "fyk": 500, "recobrimento": 30,
    "inclinacao": 30, "beiral": 500,
}

REGRAS_FONTE = {
    "vaoMaxPilares": "Prática corrente em estrutura porticada de habitação; validar pelo projeto de estabilidade",
    "g2_piso": "NP EN 1991-1-1 — revestimentos e divisórias (valor do projeto)",
    "q_piso": "NP EN 1991-1-1 quadro 6.2, categoria A (habitação)",
    "q_cob": "NP EN 1991-1-1 quadro 6.10, categoria H (cobertura não acessível)",
    "q_adm_kpa": "Estudo geotécnico — valor a confirmar (hipótese sem estudo)",
    "fck": "NP EN 206 / NP EN 1992-1-1 — C25/30, aço A500 NR",
    "vergaH": "Armadura construtiva mínima de verga (2 Ø10 + 2 Ø8, estribos Ø6 // 0,15); validar pelo projeto",
    "unidades": "Dimensões de fabrico das unidades de alvenaria (ficha técnica do fabricante)",
}

TELHA = {"nome": "Telha cerâmica lusa", "passo": 360, "largura": 240}   # dimensões úteis (mm) — ficha do fabricante


def tipos_parede(country: str = "PT") -> dict:
    if country.upper() == "FR":
        return {"EXT": {"nome": "Mur extérieur en blocs béton", "unidade": "B50x20x20", "exterior": [{"camada": "ETICS_EPS60"}],
                        "interior": [{"camada": "REBOCO_INT"}], "resistente": True},
                "INT": {"nome": "Cloison maçonnée", "unidade": "B50x20x15", "faceA": [{"camada": "REBOCO_INT"}], "faceB": [{"camada": "REBOCO_INT"}],
                        "resistente": False}}
    return {"EXT": {"nome": "Parede exterior em alvenaria de tijolo", "unidade": "T30x20x22", "exterior": [{"camada": "ETICS_EPS60"}],
                    "interior": [{"camada": "REBOCO_INT"}], "resistente": True},
            "INT": {"nome": "Parede interior em alvenaria de tijolo", "unidade": "T30x20x11", "faceA": [{"camada": "REBOCO_INT"}],
                    "faceB": [{"camada": "REBOCO_INT"}], "resistente": False}}


def base(country: str = "PT") -> dict:
    return {"country": country.upper(), "unidades": copy.deepcopy(UNIDADES), "camadas": copy.deepcopy(CAMADAS), "regras": copy.deepcopy(REGRAS),
            "tiposParede": tipos_parede(country), "telha": dict(TELHA), "perimetros": [], "paredes": [], "pisos": [], "coberturas": [],
            "precos": {}, "hipoteses": []}


def exemplo() -> dict:
    """Moradia de exemplo R/C + 1.º andar (10 × 8 m) — mesma geometria dos exemplos LSF e CLT."""
    from engines.clt import defaults as C
    c = C.exemplo()
    p = base("PT")
    p["nome"] = "Moradia exemplo — construção tradicional R/C + 1.º andar"
    p["perimetros"] = [dict(x) for x in c["perimetros"]]
    p["paredes"] = [dict(x) for x in c["paredes"]]
    p["pisos"] = [{k: f[k] for k in ("id", "grupo", "nivel", "x0", "y0", "x1", "y1", "z", "vao")} for f in c["pisos"]]
    p["coberturas"] = [dict(x) for x in c["coberturas"]]
    return p
