"""Leitura de cotas e de terras suportadas nos CORTES/ALÇADOS, por IA de visão — sobre a geometria já lida.

A IA não desenha nem mede a planta: recebe a planta com as arestas do contorno REAL numeradas (E1…En)
e as folhas de cortes, e devolve apenas cotas e a escolha de arestas. Tudo é validado pelo código;
o que falhar fica nas hipóteses por defeito, com aviso.
"""
from __future__ import annotations

import base64
import io
import json
import logging
import math
import re

from shapely.geometry import LineString

from .model import Building, Wall

log = logging.getLogger(__name__)

SECTION_RX = re.compile(r"\b(corte|alçado|alcado|section|coupe)\b", re.I)

SYSTEM = (
    "És um engenheiro civil a ler peças desenhadas de arquitetura (Portugal). Respondes SÓ com JSON válido. "
    "Não inventes: se um valor não estiver legível nos desenhos, usa null."
)

PROMPT = """A imagem 1 é a planta do edifício com o contorno REAL a vermelho e as arestas numeradas E1…E{n}
(origem e orientação da planta original). A imagem 2 é a folha de planta ORIGINAL (com a legenda de áreas).
As restantes imagens são cortes/alçados.

Lê nos cortes e devolve este JSON:
{{
  "floor_level": cota do pavimento interior principal (m, ex. 390.50) ou null,
  "roof_slab_top_level": cota da face superior da laje de cobertura estrutural (m; NÃO a platibanda, NÃO o seixo) ou null,
  "storeys": número de pisos acima do pavimento (inteiro),
  "declared_construction_area_m2": área de construção declarada na legenda da planta original (m²) ou null,
  "retaining": [ {{"edge": "E7", "retained_height_m": 2.5, "evidence": "corte C2: terreno a 393.00 encostado à garagem"}} ],
  "notes": "curto"
}}
Regras: só incluis em "retaining" arestas onde o TERRENO encosta à parede acima do pavimento interior
(muro de suporte enterrado). retained_height_m = cota do terreno junto à parede − cota do pavimento."""


def _png(page, dpi=80, clip=None) -> str:
    pix = page.get_pixmap(dpi=dpi, clip=clip)
    return base64.b64encode(pix.tobytes("png")).decode()


def edges(b: Building) -> list[LineString]:
    cs = list(b.footprint.exterior.simplify(0.05).coords)
    return [LineString([cs[i], cs[i + 1]]) for i in range(len(cs) - 1) if math.dist(cs[i], cs[i + 1]) > 0.3]


def plan_with_edges_png(b: Building) -> str:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(11, 8))
    x, y = b.footprint.exterior.xy
    ax.plot(x, y, color="#c0262d", lw=2)
    for h in b.footprint.interiors:
        x, y = h.xy
        ax.plot(x, y, color="#c0262d", lw=1, ls="--")
    for w in b.walls:
        ax.plot([w.a[0], w.b[0]], [w.a[1], w.b[1]], color="#7b8794", lw=max(1.0, w.t * 12))
    for i, e in enumerate(edges(b)):
        m = e.interpolate(0.5, normalized=True)
        ax.text(m.x, m.y, f"E{i + 1}", fontsize=9, color="white", ha="center", va="center",
                bbox={"boxstyle": "round,pad=0.2", "fc": "#c0262d", "ec": "none"})
    ax.set_aspect("equal")
    ax.set_title("Contorno real lido — Norte do desenho para cima")
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=70, bbox_inches="tight")
    plt.close(fig)
    return base64.b64encode(buf.getvalue()).decode()


def section_pages(docs, limit=4):
    import pymupdf

    out = []
    for _, data in docs:
        try:
            pdf = pymupdf.open(stream=data, filetype="pdf")
        except Exception:  # noqa: BLE001
            continue
        for page in pdf:
            head = " ".join(page.get_text().split())
            m = re.search(r"\b(CORTE|ALÇADO)\s+[A-Z0-9]+", head)
            if m and re.search(r"1\s*:\s*(50|100|200)\b", head):
                out.append(page)
            if len(out) >= limit:
                return out
    return out


def apply(b: Building, data: dict) -> list[str]:
    """Valida e aplica a resposta da IA. Devolve avisos."""
    warns = []
    fl, rl = data.get("floor_level"), data.get("roof_slab_top_level")
    try:
        fl = float(fl) if fl is not None else None
        rl = float(rl) if rl is not None else None
    except (TypeError, ValueError):
        fl = rl = None
    if fl is not None and rl is not None and 2.4 <= rl - fl <= 6.5:
        b.floor_level, b.roof_level = fl, rl
        b.checks.append({"item": "pé-direito estrutural (cortes)", "valor": round(rl - fl, 2), "unidade": "m",
                         "metodo": f"cotas lidas nos cortes: pavimento {fl:.2f}, laje {rl:.2f}".replace(".", ",")})
    else:
        warns.append("Cotas do pavimento/cobertura não confirmadas nos cortes: pé-direito estrutural assumido "
                     f"{b.storey_height:.2f} m.")
    try:
        decl = float(data.get("declared_construction_area_m2")) if data.get("declared_construction_area_m2") else None
    except (TypeError, ValueError):
        decl = None
    if decl:
        diff = (b.footprint.area - decl) / decl
        ok = abs(diff) <= 0.05
        b.checks.append({"item": "área declarada na legenda (2.ª fonte)", "valor": round(decl, 2), "unidade": "m²",
                         "metodo": f"legenda da planta (IA); diferença para a geometria lida {diff * 100:+.1f} %".replace(".", ","),
                         "ok": ok})
        if not ok:
            warns.append(f"Área lida ({b.footprint.area:.1f} m²) difere {diff * 100:+.1f} % da declarada ({decl:.1f} m²): "
                         "rever a leitura do contorno antes de usar as quantidades.")
    try:
        b.storeys = max(1, int(data.get("storeys") or 1))
    except (TypeError, ValueError):
        b.storeys = 1
    es = edges(b)
    for r in data.get("retaining") or []:
        try:
            k = int(str(r.get("edge", "")).strip().upper().lstrip("E")) - 1
            h = float(r.get("retained_height_m"))
        except (TypeError, ValueError):
            continue
        if not (0 <= k < len(es)) or not (0.3 <= h <= 6.0):
            warns.append(f"Muro de suporte ignorado (aresta/altura inválida): {r}")
            continue
        e = es[k]
        b.walls.append(Wall(e.coords[0], e.coords[1], 0.30, "betao", True, round(h, 2),
                            f"cortes (IA): {str(r.get('evidence') or '')[:120]}"))
    return warns


async def read_levels(b: Building, docs, llm, plan_page=None) -> list[str]:
    """Best-effort: nunca bloqueia o estudo."""
    if llm is None:
        return ["Cotas não lidas (IA de visão indisponível): pé-direito e terras por defeito."]
    try:
        secs = section_pages(docs)
        if not secs:
            return ["Sem cortes legíveis no processo: pé-direito e terras por defeito."]
        images = [plan_with_edges_png(b)] + ([_png(plan_page, 90)] if plan_page is not None else []) + [_png(p) for p in secs]
        txt = await llm(SYSTEM, PROMPT.format(n=len(edges(b))), images=images, max_tokens=1500)
        m = re.search(r"\{.*\}", txt or "", re.S)
        data = json.loads(m.group(0)) if m else {}
        return apply(b, data)
    except Exception as exc:  # noqa: BLE001
        log.warning("bet_geo levels read failed: %s", type(exc).__name__)
        return ["Leitura das cotas nos cortes falhou: pé-direito e terras por defeito."]
