"""Estilos arquitetónicos do piloto automático (moradias em Portugal).

Cada estilo é um conjunto COERENTE de decisões de projeto — forma da cobertura, materiais por zona da fachada,
caixilharia, proporção dos vãos, elementos característicos — e as palavras para as imagens realistas.
Nada aqui altera áreas, afastamentos ou índices: o estilo só decide linguagem e materiais, a geometria
continua a sair dos motores de implantação e plantas (uma só verdade).

Referências (síntese, sem cópia de projetos concretos): arquitetura popular portuguesa por região
(casa minhota e serrana em granito, casas de xisto da Beira, monte alentejano caiado com barras, casa algarvia
com platibandas, chaminés e açoteias) e a moradia contemporânea portuguesa (volumes simples, cobertura plana,
betão/reboco claro com ripado de madeira, grandes envidraçados para o jardim e a piscina).
"""
from __future__ import annotations

import re
import unicodedata
from typing import Any, Dict, List, Optional

ESTILOS: Dict[str, Dict[str, Any]] = {
    "contemporaneo": {
        "nome": "Contemporâneo",
        "descricao": "Volumes simples, cobertura plana, reboco claro com ripado de madeira e grandes envidraçados para o jardim.",
        "cobertura": {"tipo": "plana", "material": "plana_seixo"},
        "fachada": "misto_madeira_reboco", "caixilharia": "aluminio_antracite",
        "envidracado": 1.0, "elementos": ["platibanda", "pala em betão sobre a entrada", "ripado vertical de madeira"],
        "render": "contemporary Portuguese villa, flat roof with thin parapet, smooth off-white render, vertical natural timber "
                  "slats, large frameless glazing, minimalist landscaping, ornamental grasses, olive trees",
        "palavras": ["contemporane", "moderna", "moderno", "atual", "minimal"],
    },
    "minimalista": {
        "nome": "Minimalista branco",
        "descricao": "Volumes brancos puros, cobertura plana, poucos materiais, vãos rasgados e linhas horizontais.",
        "cobertura": {"tipo": "plana", "material": "plana_seixo"},
        "fachada": "reboco_branco", "caixilharia": "aluminio_antracite", "envidracado": 1.1,
        "elementos": ["platibanda", "vãos de canto", "muros brancos"],
        "render": "minimalist white modernist house, pure white rendered volumes, flat roof, long horizontal windows, "
                  "dark aluminium frames, white walls, gravel and lawn, Mediterranean light",
        "palavras": ["minimalista", "branca pura", "cubica", "cubo"],
    },
    "tradicional_portugues": {
        "nome": "Casa portuguesa tradicional",
        "descricao": "Telhado de duas águas em telha cerâmica, reboco branco, cantarias de granito nos vãos e beiral.",
        "cobertura": {"tipo": "duas_aguas", "material": "telha_ceramica"},
        "fachada": "misto_granito_reboco", "caixilharia": "madeira", "envidracado": 0.75,
        "elementos": ["beiral à portuguesa", "molduras de granito nos vãos", "portadas de madeira"],
        "render": "traditional Portuguese country house, white lime render, granite stone window and door surrounds, "
                  "red clay roof tiles with Portuguese eaves, wooden shutters, cobblestone path, vine pergola",
        "palavras": ["tradicional", "portuguesa", "antiga", "antigo", "classica", "classico", "rural"],
    },
    "minhoto_granito": {
        "nome": "Minhoto (granito)",
        "descricao": "Inspirada na casa do Minho: alvenaria de granito aparente, telha cerâmica, madeira nas portadas.",
        "cobertura": {"tipo": "duas_aguas", "material": "telha_ceramica"},
        "fachada": "granito", "caixilharia": "madeira", "envidracado": 0.7,
        "elementos": ["granito aparente", "alpendre de madeira", "cunhais em cantaria"],
        "render": "northern Portugal Minho style house, rough-cut grey granite masonry walls, red clay tile gable roof, "
                  "dark timber shutters and porch, green hills, vineyards, granite paving",
        "palavras": ["minho", "minhot", "granito aparente", "pedra"],
    },
    "rustico_pedra_madeira": {
        "nome": "Rústico contemporâneo (pedra e madeira)",
        "descricao": "Base em pedra natural e volumes em madeira, telhado de duas águas, ambiente de campo atual.",
        "cobertura": {"tipo": "duas_aguas", "material": "telha_preta"},
        "fachada": "misto_granito_madeira", "caixilharia": "aluminio_antracite", "envidracado": 0.9,
        "elementos": ["embasamento em pedra", "revestimento em madeira", "envidraçados amplos para o jardim"],
        "render": "modern rustic house, granite stone base, warm horizontal timber cladding, dark grey roof, large glazing, "
                  "natural garden with stone walls and native trees",
        "palavras": ["rustic", "campo", "quinta"],
    },
    "xisto_beira": {
        "nome": "Xisto da Beira",
        "descricao": "Paredes em pedra de xisto, telhado de duas águas, varanda de madeira — inspirada nas aldeias do xisto.",
        "cobertura": {"tipo": "duas_aguas", "material": "telha_ceramica"},
        "fachada": "xisto", "caixilharia": "madeira", "envidracado": 0.65,
        "elementos": ["xisto em lajeado", "varanda de madeira", "pequenos vãos"],
        "render": "Portuguese schist village style house, dark layered schist stone walls, red clay tile roof, timber balcony, "
                  "small deep windows, mountain landscape with chestnut trees",
        "palavras": ["xisto", "beira", "serra"],
    },
    "alentejano": {
        "nome": "Alentejano (monte)",
        "descricao": "Casa térrea caiada de branco com barras azuis ou ocre à volta dos vãos, chaminé e telha cerâmica.",
        "cobertura": {"tipo": "duas_aguas", "material": "telha_ceramica"},
        "fachada": "reboco_branco", "caixilharia": "madeira", "envidracado": 0.6,
        "elementos": ["cal branca", "barras azuis ou ocre nos vãos e no rodapé", "chaminé alentejana"],
        "render": "Alentejo monte farmhouse, single storey, thick whitewashed lime walls with blue painted base band and window "
                  "frames, red clay tile roof, tall white chimney, cork oaks and dry golden fields",
        "palavras": ["alentej", "caiad", "barras azuis"],
    },
    "algarvio": {
        "nome": "Algarvio",
        "descricao": "Paredes brancas, platibandas e chaminés decoradas, açoteia (terraço plano) — influência mediterrânica.",
        "cobertura": {"tipo": "plana", "material": "plana_seixo"},
        "fachada": "reboco_branco", "caixilharia": "aluminio_branco", "envidracado": 0.8,
        "elementos": ["platibanda decorada", "chaminé algarvia rendilhada", "açoteia"],
        "render": "traditional Algarve house, white lime walls, decorated parapet with coloured band, ornate white lattice "
                  "chimney, flat roof terrace, terracotta floor, bougainvillea, carob and almond trees, bright southern light",
        "palavras": ["algarv", "acoteia", "chamine rendilhada"],
    },
    "mediterranico": {
        "nome": "Mediterrânico",
        "descricao": "Reboco claro, telha cerâmica, pérgolas e alpendres sombreados, pátio e piscina integrados.",
        "cobertura": {"tipo": "duas_aguas", "material": "telha_ceramica"},
        "fachada": "reboco_branco", "caixilharia": "madeira", "envidracado": 0.85,
        "elementos": ["alpendre", "pérgola de madeira", "pátio"],
        "render": "Mediterranean villa, warm off-white render, terracotta roof tiles, deep shaded porch with timber pergola, "
                  "terracotta and stone paving, lavender, olive and cypress trees",
        "palavras": ["mediterr", "pergola", "alpendre"],
    },
    "nordico_madeira": {
        "nome": "Nórdico (madeira)",
        "descricao": "Volumes de duas águas sem beiral, revestimento integral em madeira escura ou natural, vãos grandes.",
        "cobertura": {"tipo": "duas_aguas", "material": "zinco"},
        "fachada": "madeira", "caixilharia": "aluminio_antracite", "envidracado": 1.0,
        "elementos": ["telhado sem beiral", "madeira integral", "envidraçados nos topos"],
        "render": "Scandinavian style gable house, no eaves, full timber cladding, standing seam metal roof, large gable "
                  "glazing, simple lawn and birch trees",
        "palavras": ["nordic", "escandinav", "chale", "madeira integral"],
    },
}

ESTILO_PADRAO = "contemporaneo"


def _norm(s: str) -> str:
    return unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode().lower()


def detectar(texto: str) -> Optional[str]:
    """Estilo pedido numa frase simples (None se não houver indicação)."""
    t = _norm(texto)
    if not t:
        return None
    for k, e in ESTILOS.items():
        if _norm(e["nome"]) in t:
            return k
    best, score = None, 0
    for k, e in ESTILOS.items():
        s = sum(1 for p in e["palavras"] if p in t)
        if s > score:
            best, score = k, s
    return best


def lista() -> List[Dict[str, Any]]:
    return [{"id": k, "nome": e["nome"], "descricao": e["descricao"], "cobertura": e["cobertura"]["tipo"],
             "fachada": e["fachada"], "elementos": e["elementos"]} for k, e in ESTILOS.items()]


def obter(estilo: Optional[str]) -> Dict[str, Any]:
    return {"id": estilo if estilo in ESTILOS else ESTILO_PADRAO, **ESTILOS.get(estilo or "", ESTILOS[ESTILO_PADRAO])}
