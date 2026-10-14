"""Leitura IA (visão) da geometria de uma moradia a partir das peças do projeto de licenciamento
e do estudo geotécnico. Nunca inventa: valores ilegíveis → null + incerteza."""
from __future__ import annotations

from engines import structuro_autopilot as ap

GEOM_PROMPT = (
    "Analisas as peças desenhadas de um PROJETO DE LICENCIAMENTO (plantas de piso, cortes, alçados, implantação) de "
    "uma moradia / pequeno edifício em Portugal. Lê as COTAS escritas e a ESCALA indicada. Devolve APENAS este JSON:\n"
    '{"name": "designação da obra (morada ou nome) ou null",\n'
    ' "outer_L_m": comprimento exterior fora a fora (lado maior) em m,\n'
    ' "outer_W_m": largura exterior fora a fora (lado menor) em m,\n'
    ' "wall_thickness_m": espessura das paredes exteriores resistentes (sem isolamento ETICS) em m ou null,\n'
    ' "structure": "alvenaria" (paredes resistentes de blocos) | "portico" (pilares e vigas de betão) | "betao" (paredes de betão),\n'
    ' "levels": [{"name": "R/C" | "1.º piso" | "2.º piso"…, "storey_height_m": pé-direito + laje (diferença entre cotas de pavimentos), '
    '"use": "habitacao" | "garagem" | "comercio" | "escritorios"}] de baixo para cima, SEM a cave,\n'
    ' "basement": {"present": true/false, "height_m": altura da cave ou null},\n'
    ' "roof": {"type": "inclinada" | "laje_plana", "ridge_height_m": altura da cumeeira acima da última laje ou null},\n'
    ' "interior_walls_x": [posições em m, medidas a partir da fachada ESQUERDA, das paredes interiores RESISTENTES '
    'contínuas paralelas ao lado menor (que atravessam o edifício e se repetem nos pisos)],\n'
    ' "interior_walls_y": [posições em m, a partir da fachada da FRENTE, das paredes interiores resistentes paralelas ao lado maior],\n'
    ' "openings": [{"level": nome do piso, "facade": "frente" | "tras" | "esquerda" | "direita", "width_m": largura do vão, '
    '"label": "porta de garagem" | "janela sala"…}] — só vãos com largura ≥ 0,8 m e legível,\n'
    ' "stair": {"present": true/false, "cage_length_m": comprimento da caixa de escada, "cage_width_m": largura},\n'
    ' "incertezas": ["…"]}\n'
    "REGRAS: medidas em METROS; null quando não estiver escrito/legível (nunca inventes); a FRENTE é a fachada da rua/entrada. "
    "Paredes divisórias leves (tijolo 11, gesso cartonado) NÃO são resistentes. Se não houver paredes interiores resistentes "
    "claras, devolve listas vazias e diz em incertezas. Pé-direito típico se só houver cotas de pavimentos: diferença entre elas. "
    "Escreve as incertezas em português europeu.")


async def extract(geom_images: list[bytes], soil_images: list[bytes]) -> dict:
    geo: dict = {}
    inc: list[str] = []
    try:
        g = await ap._ask(GEOM_PROMPT, geom_images) if geom_images else None
        if isinstance(g, dict):
            geo = {k: v for k, v in g.items() if k != "incertezas"}
            inc += [str(x) for x in (g.get("incertezas") or [])]
        else:
            inc.append("Geometria não lida nas peças fornecidas — indicar dimensões, pisos e pé-direito.")
    except Exception as e:  # noqa: BLE001
        inc.append(f"Leitura da geometria indisponível: {str(e)[:120]}")
    soil = {}
    try:
        s, s_inc = await ap._extract_soil_batched(soil_images) if soil_images else (None, [])
        inc += s_inc or []
        if s and isinstance(s.get("soil"), dict):
            raw = s["soil"]
            soil = {"q_els_kpa": raw.get("q_els_kpa"), "q_elu_kpa": raw.get("q_elu_kpa"),
                    "phi_deg": raw.get("phi_deg") or 30.0, "gamma_kn_m3": raw.get("gamma_soil_kn_m3") or 20.0,
                    "foundation_type": raw.get("foundation_type"), "anchorage_depth_m": raw.get("anchorage_depth_m"),
                    "soil_class": raw.get("soil_class"), "confirmed": raw.get("q_els_kpa") is not None}
    except Exception as e:  # noqa: BLE001
        inc.append(f"Leitura do estudo geotécnico indisponível: {str(e)[:120]}")
    if not soil_images:
        inc.append("Sem estudo geotécnico: as sapatas não serão dimensionadas.")
    elif not soil.get("q_els_kpa"):
        inc.append("Tensão admissível não encontrada no estudo geotécnico — indicar q_ELS (kPa).")
    if soil:
        geo["soil"] = soil
    return {"geometry": geo, "incertezas": inc}
