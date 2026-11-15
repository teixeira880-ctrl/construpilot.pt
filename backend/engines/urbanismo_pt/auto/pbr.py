"""Biblioteca de materiais fotografados (PBR) para os renders Blender — Poly Haven, licença CC0 (uso livre, sem atribuição).

Cada material: cor (diff), relevo (nor_gl) e rugosidade (rough), com o tamanho real da amostra em metros, para a textura
ficar à escala certa na fachada. O servidor descarrega os ficheiros uma vez de dl.polyhaven.org para a cache
(CP_PBR_DIR, por omissão backend/.cache/pbr) e usa-os em todos os renders seguintes. Sem rede, o render usa os materiais
procedimentais (nunca falha por causa disto).
"""
from __future__ import annotations

import logging
import os
from typing import Dict, Optional

log = logging.getLogger(__name__)

URL = "https://dl.polyhaven.org/file/ph-assets/Textures/jpg/{res}/{id}/{id}_{mapa}_{res}.jpg"
MAPAS = ("diff", "nor_gl", "rough")
# chave do motor → (asset Poly Haven, lado real da amostra em metros)
TEXTURAS: Dict[str, tuple] = {
    "granito": ("granite_wall", 1.90),
    "madeira": ("wood_plank_wall", 1.00),
    "reboco": ("white_stucco", 2.00),
    "telha_ceramica": ("clay_roof_tiles_02", 2.50),
    "telha_preta": ("grey_roof_tiles", 3.00),
    "xisto": ("castle_wall_slates", 2.50),
    "betao": ("concrete_wall_008", 2.71),
    "tijolo": ("red_brick_plaster_patch_02", 1.50),
    "lajeado": ("granite_tile_04", 2.00),
    "seixo": ("gravel", 2.00),
}


def pasta() -> str:
    p = os.environ.get("CP_PBR_DIR") or os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))))), ".cache", "pbr")
    os.makedirs(p, exist_ok=True)
    return p


def _local(asset: str, mapa: str) -> Optional[str]:
    """Ficheiro já em cache, na melhor resolução disponível."""
    for res in ("4k", "2k", "1k"):
        f = os.path.join(pasta(), f"{asset}_{mapa}_{res}.jpg")
        if os.path.exists(f) and os.path.getsize(f) > 1000:
            return f
    return None


def garantir(res: Optional[str] = None, timeout: float = 60.0) -> Dict[str, dict]:
    """Descarrega o que falta (uma vez) e devolve {chave: {diff, nor_gl, rough, tamanho_m, asset}} só dos completos."""
    res = res or os.environ.get("CP_PBR_RES", "2k")
    out = {}
    cliente = None
    try:
        for chave, (asset, tam) in TEXTURAS.items():
            fic = {}
            for mapa in MAPAS:
                f = _local(asset, mapa)
                if not f and os.environ.get("CP_PBR_OFFLINE") != "1":
                    try:
                        import httpx
                        cliente = cliente or httpx.Client(timeout=timeout, follow_redirects=True)
                        r = cliente.get(URL.format(res=res, id=asset, mapa=mapa))
                        if r.status_code == 200 and r.content[:3] == b"\xff\xd8\xff":
                            f = os.path.join(pasta(), f"{asset}_{mapa}_{res}.jpg")
                            tmp = f + ".part"
                            with open(tmp, "wb") as h:
                                h.write(r.content)
                            os.replace(tmp, f)
                    except Exception as e:  # noqa: BLE001 — sem rede: fica o procedimental
                        log.warning("PBR %s %s: %s", asset, mapa, str(e)[:120])
                if f:
                    fic[mapa] = f
            if len(fic) == len(MAPAS):
                out[chave] = {**fic, "tamanho_m": tam, "asset": asset}
    finally:
        if cliente:
            cliente.close()
    return out
