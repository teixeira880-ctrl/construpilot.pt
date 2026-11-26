"""Descarrega as texturas fotográficas CC0 do 3D do Estúdio (Poly Haven, domínio público) para o próprio site.

Uso (no servidor, uma vez; volta a correr para atualizar):
    python backend/scripts/baixar_texturas_cc0.py [pasta_destino]
Destino por omissão: frontend/public/texturas  →  servido em /texturas/… (sem dependência de um CDN externo em produção).

Para cada padrão do Estúdio tenta os identificadores pela ordem (o primeiro que existir na API ganha), descarrega
cor (diffuse), relevo (normal GL) e rugosidade em 1k JPG, e escreve manifest.json com: identificador, escala real
(metros por repetição, a partir das dimensões publicadas pela Poly Haven), autores e licença.
Licença: CC0 1.0 (https://polyhaven.com/license) — uso comercial livre, sem atribuição obrigatória (fica registada).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import requests

API = "https://api.polyhaven.com"
UA = {"User-Agent": "ConstruPilot-Estudio/1.0 (texturas CC0)"}
RES = "1k"

# padrão do Estúdio → candidatos Poly Haven (por ordem de preferência) ; natural = mostra a cor da fotografia
CANDIDATOS = {
    "soalho": (["embedded_plank_flooring", "diagonal_parquet", "dark_wooden_planks", "wood_floor_deck"], True),
    "deck": (["wood_floor_deck", "brown_planks_03", "dark_planks"], True),
    "ladrilho": (["floor_tiles_08", "anti_skid_tiles", "floor_tiles_06"], False),
    "marmore": (["floor_tiles_06", "floor_tiles_02", "floor_tiles_04"], True),
    "pedra": (["granite_wall", "castle_wall_slates", "medieval_blocks_06", "coral_stone_wall"], True),
    "pedra_exterior": (["floor_pattern_01", "cobblestone_floor_04", "cobblestone_pavement", "cobblestone_square"], True),
    "tijolo": (["brick_wall_001", "large_red_bricks", "brick_4"], True),
    "reboco": (["grey_plaster", "beige_wall_001", "beige_wall_002"], False),
    "betao": (["concrete_wall_009", "concrete", "concrete_slab_wall"], True),
    "ripado": (["brown_planks_03", "dark_planks", "brown_planks_05"], True),
    "chapa": (["box_profile_metal_sheet", "corrugated_iron", "corrugated_iron_02"], False),
    "telha": (["clay_roof_tiles", "clay_roof_tiles_02", "roof_tiles_14", "ceramic_roof_01"], True),
    "ardosia": (["roof_slates_02", "roof_slates_03", "grey_roof_tiles"], True),
    "seixo": (["gravel_ground_01", "floor_pebbles_01", "pebble_ground_01"], True),
    "relva": (["grass_ground", "aerial_grass_rock", "forrest_ground_01"], True),
}
MAPAS = {"dif": "Diffuse", "nor": "nor_gl", "rug": "Rough"}


def _get(url: str):
    r = requests.get(url, headers=UA, timeout=60)
    r.raise_for_status()
    return r


def _escala(info: dict) -> float:
    dim = info.get("dimensions") or []                    # milímetros (largura, altura) do material fotografado
    try:
        m = max(float(dim[0]), float(dim[1])) / 1000.0
        return round(min(8.0, max(0.3, m)), 2)
    except (IndexError, TypeError, ValueError):
        return 2.0


def baixar(destino: Path) -> dict:
    destino.mkdir(parents=True, exist_ok=True)
    manifest, relatorio = {}, []
    for padrao, (ids, natural) in CANDIDATOS.items():
        feito = False
        for aid in ids:
            try:
                files = _get(f"{API}/files/{aid}").json()
                info = _get(f"{API}/info/{aid}").json()
            except Exception as e:  # noqa: BLE001
                relatorio.append(f"{padrao}: {aid} indisponível ({e.__class__.__name__})")
                continue
            pasta = destino / padrao
            pasta.mkdir(exist_ok=True)
            entrada = {"id": aid, "m": _escala(info), "natural": natural, "licenca": "CC0 1.0 (Poly Haven)",
                       "autores": sorted((info.get("authors") or {}).keys()), "fonte": f"https://polyhaven.com/a/{aid}"}
            ok = True
            for chave, mapa in MAPAS.items():
                try:
                    url = files[mapa][RES]["jpg"]["url"]
                    (pasta / f"{chave}.jpg").write_bytes(_get(url).content)
                    entrada[chave] = f"{chave}.jpg"
                except Exception:  # noqa: BLE001 — relevo/rugosidade são opcionais; a cor é obrigatória
                    if chave == "dif":
                        ok = False
                        break
            if ok:
                manifest[padrao] = entrada
                relatorio.append(f"{padrao}: {aid} ✓ ({entrada['m']} m por repetição)")
                feito = True
                break
        if not feito:
            relatorio.append(f"{padrao}: NENHUM candidato disponível — fica a textura desenhada do Estúdio")
    (destino / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=1), encoding="utf-8")
    (destino / "LICENCA.txt").write_text(
        "Texturas fotográficas: Poly Haven (https://polyhaven.com), licença CC0 1.0 — domínio público, uso comercial livre.\n"
        + "\n".join(f"{p}: {e['fonte']} — autores: {', '.join(e['autores']) or 'n/d'}" for p, e in manifest.items()) + "\n",
        encoding="utf-8")
    print("\n".join(relatorio))
    return manifest


if __name__ == "__main__":
    raiz = Path(__file__).resolve().parents[2]
    alvo = Path(sys.argv[1]) if len(sys.argv) > 1 else raiz / "frontend" / "public" / "texturas"
    m = baixar(alvo)
    print(f"\n{len(m)}/{len(CANDIDATOS)} padrões com fotografia CC0 em {alvo}")
