"""Catálogos de objetos do Estúdio: mobiliário, cozinha, sanitários, equipamentos técnicos e modelos de vãos.

Dimensões correntes de mercado (largura × profundidade × altura, em metros), editáveis em cada objeto colocado. São
volumes de ocupação para planta, 3D, IFC e contagem — não são modelos de fabricante.
"""
from __future__ import annotations

from typing import Any, Dict, List, Tuple

# categoria → [(id, nome, largura, profundidade, altura, altura da base ao chão, forma, classe IFC)]
_OBJ: List[Tuple[str, str, List[Tuple[str, str, float, float, float, float, str, str]]]] = [
    ("Sala", "#8c7b6b", [
        ("sofa_2", "Sofá de 2 lugares", 1.60, 0.90, 0.85, 0, "ret", "IfcFurniture"), ("sofa_3", "Sofá de 3 lugares", 2.20, 0.95, 0.85, 0, "ret", "IfcFurniture"),
        ("sofa_canto", "Sofá de canto", 2.60, 1.70, 0.85, 0, "ret", "IfcFurniture"), ("poltrona", "Poltrona", 0.85, 0.85, 0.85, 0, "ret", "IfcFurniture"),
        ("mesa_centro", "Mesa de centro", 1.10, 0.60, 0.40, 0, "ret", "IfcFurniture"), ("movel_tv", "Móvel de televisão", 1.80, 0.45, 0.50, 0, "ret", "IfcFurniture"),
        ("estante", "Estante", 1.00, 0.35, 2.00, 0, "ret", "IfcFurniture"), ("aparador", "Aparador", 1.60, 0.45, 0.85, 0, "ret", "IfcFurniture"),
        ("lareira", "Recuperador de calor / lareira", 1.00, 0.60, 1.20, 0, "ret", "IfcBuildingElementProxy"),
        ("salamandra", "Salamandra", 0.50, 0.45, 0.90, 0, "ret", "IfcBuildingElementProxy"),
    ]),
    ("Sala de jantar", "#9a7b55", [
        ("mesa_4", "Mesa de jantar de 4 lugares", 1.20, 0.80, 0.75, 0, "ret", "IfcFurniture"), ("mesa_6", "Mesa de jantar de 6 lugares", 1.60, 0.90, 0.75, 0, "ret", "IfcFurniture"),
        ("mesa_8", "Mesa de jantar de 8 lugares", 2.00, 1.00, 0.75, 0, "ret", "IfcFurniture"), ("mesa_redonda", "Mesa redonda Ø 1,10", 1.10, 1.10, 0.75, 0, "circ", "IfcFurniture"),
        ("cadeira", "Cadeira", 0.45, 0.50, 0.90, 0, "ret", "IfcFurniture"), ("banco_alto", "Banco alto", 0.40, 0.40, 0.75, 0, "circ", "IfcFurniture"),
    ]),
    ("Quarto", "#7d8a99", [
        ("cama_solteiro", "Cama de solteiro 90 × 200", 0.90, 2.00, 0.50, 0, "cama", "IfcFurniture"), ("cama_casal", "Cama de casal 140 × 200", 1.40, 2.00, 0.50, 0, "cama", "IfcFurniture"),
        ("cama_queen", "Cama 160 × 200", 1.60, 2.00, 0.50, 0, "cama", "IfcFurniture"), ("cama_king", "Cama 180 × 200", 1.80, 2.00, 0.50, 0, "cama", "IfcFurniture"),
        ("berco", "Berço", 0.70, 1.30, 0.90, 0, "cama", "IfcFurniture"), ("beliche", "Beliche", 0.95, 2.00, 1.60, 0, "cama", "IfcFurniture"),
        ("mesa_cabeceira", "Mesa de cabeceira", 0.45, 0.40, 0.50, 0, "ret", "IfcFurniture"), ("comoda", "Cómoda", 1.00, 0.50, 0.85, 0, "ret", "IfcFurniture"),
        ("roupeiro_2", "Roupeiro de 2 portas", 1.00, 0.60, 2.20, 0, "alto", "IfcFurniture"), ("roupeiro_3", "Roupeiro de 3 portas", 1.50, 0.60, 2.20, 0, "alto", "IfcFurniture"),
        ("roupeiro_embutido", "Roupeiro embutido", 2.00, 0.60, 2.50, 0, "alto", "IfcFurniture"), ("secretaria", "Secretária", 1.20, 0.60, 0.75, 0, "ret", "IfcFurniture"),
        ("cadeira_escritorio", "Cadeira de escritório", 0.60, 0.60, 1.00, 0, "circ", "IfcFurniture"),
    ]),
    ("Cozinha", "#b9b4a8", [
        ("coz_base_60", "Módulo base de 60", 0.60, 0.60, 0.90, 0, "ret", "IfcFurniture"), ("coz_base_90", "Módulo base de 90", 0.90, 0.60, 0.90, 0, "ret", "IfcFurniture"),
        ("coz_base_120", "Módulo base de 120", 1.20, 0.60, 0.90, 0, "ret", "IfcFurniture"), ("coz_canto", "Módulo de canto", 0.90, 0.90, 0.90, 0, "ret", "IfcFurniture"),
        ("coz_superior_60", "Módulo superior de 60", 0.60, 0.35, 0.70, 1.45, "ret", "IfcFurniture"), ("coz_superior_90", "Módulo superior de 90", 0.90, 0.35, 0.70, 1.45, "ret", "IfcFurniture"),
        ("coz_coluna", "Coluna de forno e micro-ondas", 0.60, 0.60, 2.10, 0, "alto", "IfcFurniture"), ("coz_ilha", "Ilha de cozinha", 1.80, 0.90, 0.90, 0, "ret", "IfcFurniture"),
        ("lava_loica_1", "Lava-loiça de 1 cuba", 0.80, 0.60, 0.90, 0, "cuba", "IfcSanitaryTerminal"), ("lava_loica_2", "Lava-loiça de 2 cubas", 1.20, 0.60, 0.90, 0, "cuba", "IfcSanitaryTerminal"),
        ("placa", "Placa de cozinha de 60", 0.60, 0.60, 0.90, 0, "placa", "IfcElectricAppliance"), ("exaustor", "Exaustor", 0.60, 0.50, 0.40, 1.60, "ret", "IfcElectricAppliance"),
        ("frigorifico", "Frigorífico combinado", 0.60, 0.65, 1.85, 0, "alto", "IfcElectricAppliance"), ("frigorifico_americano", "Frigorífico americano", 0.91, 0.72, 1.78, 0, "alto", "IfcElectricAppliance"),
        ("maq_loica", "Máquina de lavar loiça", 0.60, 0.60, 0.85, 0, "ret", "IfcElectricAppliance"),
    ]),
    ("Lavandaria", "#c3c7ca", [
        ("maq_roupa", "Máquina de lavar roupa", 0.60, 0.60, 0.85, 0, "ret", "IfcElectricAppliance"), ("maq_secar", "Máquina de secar roupa", 0.60, 0.60, 0.85, 0, "ret", "IfcElectricAppliance"),
        ("tanque", "Tanque de lavar", 0.60, 0.50, 0.85, 0, "cuba", "IfcSanitaryTerminal"), ("estendal", "Estendal", 1.80, 0.55, 1.00, 0, "ret", "IfcFurniture"),
    ]),
    ("Casa de banho", "#e9eef0", [
        ("sanita", "Sanita com tanque", 0.37, 0.65, 0.40, 0, "sanita", "IfcSanitaryTerminal"), ("sanita_suspensa", "Sanita suspensa", 0.36, 0.54, 0.40, 0, "sanita", "IfcSanitaryTerminal"),
        ("bide", "Bidé", 0.37, 0.60, 0.40, 0, "sanita", "IfcSanitaryTerminal"), ("lavatorio", "Lavatório", 0.60, 0.46, 0.85, 0, "cuba", "IfcSanitaryTerminal"),
        ("lavatorio_duplo", "Lavatório duplo", 1.20, 0.50, 0.85, 0, "cuba", "IfcSanitaryTerminal"), ("movel_lavatorio", "Móvel com lavatório de 80", 0.80, 0.46, 0.85, 0, "cuba", "IfcSanitaryTerminal"),
        ("banheira_170", "Banheira 170 × 70", 1.70, 0.70, 0.55, 0, "banheira", "IfcSanitaryTerminal"), ("banheira_150", "Banheira 150 × 70", 1.50, 0.70, 0.55, 0, "banheira", "IfcSanitaryTerminal"),
        ("duche_80", "Base de duche 80 × 80", 0.80, 0.80, 0.05, 0, "duche", "IfcSanitaryTerminal"), ("duche_100", "Base de duche 100 × 100", 1.00, 1.00, 0.05, 0, "duche", "IfcSanitaryTerminal"),
        ("duche_120", "Base de duche 120 × 80", 1.20, 0.80, 0.05, 0, "duche", "IfcSanitaryTerminal"), ("duche_140", "Base de duche 140 × 80", 1.40, 0.80, 0.05, 0, "duche", "IfcSanitaryTerminal"),
        ("toalheiro", "Toalheiro aquecido", 0.50, 0.12, 1.20, 0.60, "ret", "IfcBuildingElementProxy"),
    ]),
    ("Equipamentos técnicos", "#9aa3a8", [
        ("bomba_calor_ext", "Bomba de calor — unidade exterior", 0.90, 0.35, 0.80, 0, "ret", "IfcBuildingElementProxy"),
        ("bomba_calor_int", "Bomba de calor — unidade interior", 0.60, 0.60, 1.80, 0, "alto", "IfcBuildingElementProxy"),
        ("termoacumulador", "Termoacumulador Ø 60", 0.60, 0.60, 1.60, 0, "circ", "IfcBuildingElementProxy"), ("esquentador", "Esquentador / caldeira mural", 0.40, 0.30, 0.70, 1.40, "ret", "IfcBuildingElementProxy"),
        ("quadro_eletrico", "Quadro elétrico", 0.40, 0.12, 0.60, 1.40, "ret", "IfcBuildingElementProxy"), ("ar_condicionado", "Ar condicionado — unidade mural", 0.85, 0.20, 0.30, 2.10, "ret", "IfcBuildingElementProxy"),
        ("radiador", "Radiador", 1.00, 0.10, 0.60, 0.15, "ret", "IfcBuildingElementProxy"), ("ventilacao", "Unidade de ventilação mecânica", 0.60, 0.35, 0.70, 1.50, "ret", "IfcBuildingElementProxy"),
        ("deposito_agua", "Depósito de água Ø 80", 0.80, 0.80, 1.80, 0, "circ", "IfcBuildingElementProxy"),
    ]),
    ("Garagem e exterior", "#6f7a82", [
        ("automovel", "Automóvel (ocupação 1,80 × 4,50)", 1.80, 4.50, 1.50, 0, "ret", "IfcBuildingElementProxy"), ("moto", "Motociclo", 0.80, 2.10, 1.20, 0, "ret", "IfcBuildingElementProxy"),
        ("bicicleta", "Bicicleta", 0.60, 1.80, 1.10, 0, "ret", "IfcBuildingElementProxy"), ("bancada_oficina", "Bancada de trabalho", 1.50, 0.60, 0.90, 0, "ret", "IfcFurniture"),
        ("mesa_exterior", "Mesa de exterior", 1.60, 0.90, 0.75, 0, "ret", "IfcFurniture"), ("espreguicadeira", "Espreguiçadeira", 0.65, 1.90, 0.35, 0, "ret", "IfcFurniture"),
        ("churrasqueira", "Churrasqueira", 1.20, 0.60, 1.00, 0, "ret", "IfcBuildingElementProxy"), ("vaso", "Vaso / floreira", 0.50, 0.50, 0.50, 0, "circ", "IfcBuildingElementProxy"),
    ]),
    # Exteriores: plano de implantação. Mesmas regras que o mobiliário (posição, rotação, largura e profundidade editáveis);
    # as áreas e perímetros saem nas medições («exteriores»).
    ("Piscina", "#5aa9d6", [
        ("piscina", "Piscina retangular (plano de água)", 8.00, 4.00, 0.10, 0, "cuba", "IfcBuildingElementProxy"),
        ("piscina_infinita", "Piscina de transbordo (plano de água)", 10.00, 4.00, 0.10, 0, "cuba", "IfcBuildingElementProxy"),
        ("jacuzzi", "Jacuzzi / spa", 2.20, 2.20, 0.90, 0, "cuba", "IfcBuildingElementProxy"),
        ("casa_maquinas", "Casa das máquinas da piscina", 2.00, 1.50, 1.20, 0, "alto", "IfcBuildingElementProxy"),
    ]),
    ("Terraços e pavimentos exteriores", "#b48a5e", [
        ("terraco_pedra", "Terraço em pedra natural", 6.00, 4.00, 0.05, 0, "ret", "IfcSlab"),
        ("deck_madeira", "Deck de madeira", 4.00, 3.00, 0.08, 0, "ret", "IfcSlab"),
        ("deck_piscina", "Deck de piscina", 12.00, 2.00, 0.08, 0, "ret", "IfcSlab"),
        ("caminho", "Caminho pedonal", 1.20, 6.00, 0.03, 0, "ret", "IfcSlab"),
        ("acesso_viaturas", "Acesso automóvel", 3.50, 8.00, 0.05, 0, "ret", "IfcSlab"),
        ("estrada", "Estrada / arruamento", 6.00, 20.00, 0.08, 0, "ret", "IfcSlab"),
        ("estacionamento", "Estacionamento exterior", 5.00, 5.00, 0.05, 0, "ret", "IfcSlab"),
        ("terraco_suspenso", "Terraço suspenso / varanda em balanço", 6.00, 3.00, 0.25, -0.25, "ret", "IfcSlab"),
    ]),
    ("Jardim e estruturas exteriores", "#6f9d4f", [
        ("relvado", "Relvado", 8.00, 6.00, 0.02, 0, "ret", "IfcBuildingElementProxy"),
        ("canteiro", "Canteiro", 3.00, 1.00, 0.40, 0, "ret", "IfcBuildingElementProxy"),
        ("arvore", "Árvore", 3.00, 3.00, 5.00, 0, "circ", "IfcBuildingElementProxy"),
        ("arbusto", "Arbusto", 1.00, 1.00, 1.20, 0, "circ", "IfcBuildingElementProxy"),
        ("pergola", "Pérgola", 4.00, 3.00, 2.50, 0, "alto", "IfcBuildingElementProxy"),
        ("cozinha_exterior", "Cozinha / zona de refeições exterior", 3.00, 0.70, 0.90, 0, "ret", "IfcFurniture"),
        ("muro_vedacao", "Muro de vedação", 10.00, 0.20, 1.50, 0, "ret", "IfcWall"),
        ("portao_entrada", "Portão de entrada", 4.00, 0.20, 1.80, 0, "ret", "IfcBuildingElementProxy"),
        ("sebe", "Sebe", 10.00, 0.80, 1.50, 0, "ret", "IfcBuildingElementProxy"),
        ("lago", "Lago / espelho de água", 4.00, 3.00, 0.10, 0, "cuba", "IfcBuildingElementProxy"),
        ("horta", "Horta", 4.00, 3.00, 0.30, 0, "ret", "IfcBuildingElementProxy"),
        ("guarda_corpo", "Guarda-corpo em vidro", 6.00, 0.05, 1.05, 0, "alto", "IfcRailing"),
        ("pilar", "Pilar de betão 25 × 25", 0.25, 0.25, 2.60, 0, "alto", "IfcColumn"),
    ]),
    ("Jogos e lazer", "#e0a23c", [
        ("parque_infantil", "Parque infantil (zona de jogos)", 8.00, 6.00, 0.05, 0, "ret", "IfcBuildingElementProxy"),
        ("baloico", "Baloiço", 3.00, 2.00, 2.20, 0, "alto", "IfcBuildingElementProxy"),
        ("escorrega", "Escorrega", 4.00, 1.00, 2.20, 0, "alto", "IfcBuildingElementProxy"),
        ("trampolim", "Trampolim", 3.70, 3.70, 0.90, 0, "circ", "IfcBuildingElementProxy"),
        ("caixa_areia", "Caixa de areia", 2.00, 2.00, 0.30, 0, "ret", "IfcBuildingElementProxy"),
        ("casinha_criancas", "Casinha de crianças", 1.50, 1.50, 1.80, 0, "alto", "IfcBuildingElementProxy"),
        ("campo_jogos", "Campo de jogos", 15.00, 8.00, 0.02, 0, "ret", "IfcBuildingElementProxy"),
        ("campo_tenis", "Campo de ténis", 36.00, 18.00, 0.02, 0, "ret", "IfcBuildingElementProxy"),
    ]),
]
CATEGORIAS_EXTERIORES = ("Piscina", "Terraços e pavimentos exteriores", "Jardim e estruturas exteriores", "Jogos e lazer")

OBJETOS: Dict[str, Dict[str, Any]] = {}
CATEGORIAS_OBJ: List[str] = []
for _cat, _cor, _itens in _OBJ:
    CATEGORIAS_OBJ.append(_cat)
    for _id, _nome, _l, _p, _a, _b, _forma, _ifc in _itens:
        OBJETOS[_id] = {"id": _id, "nome": _nome, "categoria": _cat, "largura_m": _l, "prof_m": _p, "altura_m": _a, "base_m": _b,
                        "forma": _forma, "ifc": _ifc, "cor": _cor}

# ---------------------------------------------------------------- modelos de vão e proteção solar
MODELOS_VAO: Dict[str, Dict[str, Dict[str, Any]]] = {
    "janela": {"batente_1": {"nome": "Batente de 1 folha", "folhas": 1}, "batente_2": {"nome": "Batente de 2 folhas", "folhas": 2},
               "oscilobatente_1": {"nome": "Oscilobatente de 1 folha", "folhas": 1}, "oscilobatente_2": {"nome": "Oscilobatente de 2 folhas", "folhas": 2},
               "correr_2": {"nome": "De correr de 2 folhas", "folhas": 2}, "correr_3": {"nome": "De correr de 3 folhas", "folhas": 3},
               "fixa": {"nome": "Fixa", "folhas": 1}, "basculante": {"nome": "Basculante", "folhas": 1}, "guilhotina": {"nome": "De guilhotina", "folhas": 1}},
    "portada": {"correr_2": {"nome": "De correr de 2 folhas", "folhas": 2}, "correr_3": {"nome": "De correr de 3 folhas", "folhas": 3},
                "correr_4": {"nome": "De correr de 4 folhas", "folhas": 4}, "batente_2": {"nome": "Batente de 2 folhas", "folhas": 2},
                "elevadora": {"nome": "Elevadora de correr", "folhas": 2}, "fixa": {"nome": "Pano fixo", "folhas": 1}, "harmonio": {"nome": "Em harmónio", "folhas": 4}},
    "porta": {"simples": {"nome": "De batente simples", "folhas": 1}, "dupla": {"nome": "De batente dupla", "folhas": 2},
              "correr": {"nome": "De correr", "folhas": 1}, "correr_embutida": {"nome": "De correr embutida na parede", "folhas": 1},
              "entrada": {"nome": "De entrada de segurança", "folhas": 1}, "vaivem": {"nome": "De vaivém", "folhas": 1},
              "corta_fogo": {"nome": "Corta-fogo", "folhas": 1}},
    "portao": {"seccionado": {"nome": "Seccionado", "folhas": 1}, "basculante": {"nome": "Basculante", "folhas": 1},
               "batente_2": {"nome": "De batente de 2 folhas", "folhas": 2}, "enrolar": {"nome": "De enrolar", "folhas": 1}},
}
MODELO_PADRAO = {"janela": "oscilobatente_2", "portada": "correr_2", "porta": "simples", "portao": "seccionado"}
PROTECOES = {"": "Sem proteção", "estore_exterior": "Estore exterior de lâminas", "estore_termico": "Estore térmico com caixa isolada",
             "portada_exterior": "Portadas exteriores", "portada_interior": "Portadas interiores", "veneziana": "Veneziana exterior",
             "lona": "Tela / lona de rolo", "brise": "Lâminas fixas (brise-soleil)", "pala": "Pala horizontal"}


def modelo_vao(tipo: str, ident: Any) -> Dict[str, Any]:
    mods = MODELOS_VAO.get(tipo) or MODELOS_VAO["janela"]
    k = str(ident or "")
    k = k if k in mods else MODELO_PADRAO.get(tipo, next(iter(mods)))
    return {"id": k, **mods[k]}


def catalogo() -> Dict[str, Any]:
    return {"objetos": list(OBJETOS.values()), "categorias_objetos": CATEGORIAS_OBJ, "modelos_vao": MODELOS_VAO,
            "modelo_vao_padrao": MODELO_PADRAO, "protecoes": PROTECOES}
