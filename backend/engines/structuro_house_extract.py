"""Leitura IA (visão) da geometria de uma moradia a partir das peças do projeto de licenciamento
e do estudo geotécnico. Nunca inventa: valores ilegíveis → null + incerteza."""
from __future__ import annotations

import asyncio
import io
import logging

from engines import structuro_autopilot as ap

log = logging.getLogger("structuro.house.extract")

MAX_SIDE = 1800
GEOM_TIMEOUT_S = 150
SOIL_TIMEOUT_S = 150

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


def _shrink(img: bytes) -> bytes:
    try:
        from PIL import Image
        im = Image.open(io.BytesIO(img))
        if max(im.size) <= MAX_SIDE:
            return img
        im.thumbnail((MAX_SIDE, MAX_SIDE))
        if im.mode not in ("RGB", "L"):
            im = im.convert("RGB")
        out = io.BytesIO(); im.save(out, format="PNG", optimize=True)
        return out.getvalue()
    except Exception:  # noqa: BLE001
        return img


async def _read_geom(images):
    if not images:
        return {}, ["Sem peças desenhadas legíveis — indicar dimensões, pisos e pé-direito."]
    try:
        g = await asyncio.wait_for(ap._ask(GEOM_PROMPT, images), timeout=GEOM_TIMEOUT_S)
    except asyncio.TimeoutError:
        log.warning("leitura da geometria: timeout %ss", GEOM_TIMEOUT_S)
        return {}, [f"Leitura das plantas demorou mais de {GEOM_TIMEOUT_S // 60} min e foi interrompida — indicar dimensões, pisos e pé-direito (ou anexar só as plantas/cortes principais)."]
    except Exception as e:  # noqa: BLE001
        return {}, [f"Leitura da geometria indisponível: {str(e)[:120]}"]
    if not isinstance(g, dict):
        return {}, ["Geometria não lida nas peças fornecidas — indicar dimensões, pisos e pé-direito."]
    return {k: v for k, v in g.items() if k != "incertezas"}, [str(x) for x in (g.get("incertezas") or [])]


async def _read_soil(images):
    if not images:
        return {}, ["Sem estudo geotécnico: as sapatas não serão dimensionadas."]
    try:
        s, s_inc = await asyncio.wait_for(ap._extract_soil_batched(images), timeout=SOIL_TIMEOUT_S)
    except asyncio.TimeoutError:
        log.warning("leitura do estudo geotécnico: timeout %ss", SOIL_TIMEOUT_S)
        return {}, ["Leitura do estudo geotécnico interrompida (demasiado longa) — indicar q_ELS (kPa)."]
    except Exception as e:  # noqa: BLE001
        return {}, [f"Leitura do estudo geotécnico indisponível: {str(e)[:120]}"]
    inc = list(s_inc or [])
    soil = {}
    if s and isinstance(s.get("soil"), dict):
        raw = s["soil"]
        soil = {"q_els_kpa": raw.get("q_els_kpa"), "q_elu_kpa": raw.get("q_elu_kpa"),
                "phi_deg": raw.get("phi_deg") or 30.0, "gamma_kn_m3": raw.get("gamma_soil_kn_m3") or 20.0,
                "foundation_type": raw.get("foundation_type"), "anchorage_depth_m": raw.get("anchorage_depth_m"),
                "soil_class": raw.get("soil_class"), "confirmed": raw.get("q_els_kpa") is not None}
    if not soil.get("q_els_kpa"):
        inc.append("Tensão admissível não encontrada no estudo geotécnico — indicar q_ELS (kPa).")
    return soil, inc


async def extract(geom_images, soil_images):
    """Plantas e geotecnia lidas EM PARALELO, cada uma com timeout; nunca bloqueia mais de ~2,5 min."""
    geom_images = await asyncio.to_thread(lambda: [_shrink(i) for i in geom_images])
    soil_images = await asyncio.to_thread(lambda: [_shrink(i) for i in soil_images])
    (geo, g_inc), (soil, s_inc) = await asyncio.gather(_read_geom(geom_images), _read_soil(soil_images))
    if soil:
        geo["soil"] = soil
    return {"geometry": geo, "incertezas": g_inc + s_inc}
