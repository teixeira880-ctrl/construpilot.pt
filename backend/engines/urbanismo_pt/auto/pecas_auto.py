"""Peças geradas pelo piloto automático: planta de localização (ortofotomapa), planta topográfica indicativa,
vãos das fachadas (para o 3D e os alçados), materiais e memória descritiva determinística (sem números inventados).
"""
from __future__ import annotations

import base64
import io
import math
from typing import Any, Dict, List, Optional

from PIL import Image, ImageDraw

from engines.urbanismo_pt import volumes as V

MATERIAIS_FACHADA = {
    "reboco_branco": "Reboco pintado a branco",
    "granito": "Revestimento em granito da região (cantaria / placagem)",
    "madeira": "Revestimento em ripado de madeira tratada",
    "xisto": "Revestimento em pedra de xisto",
    "tijolo": "Tijolo face à vista",
    "betao": "Betão aparente",
    "misto_granito_reboco": "Granito no rés-do-chão e reboco branco no andar",
    "misto_madeira_reboco": "Reboco branco com apontamentos em madeira",
    "misto_granito_madeira": "Granito da região com revestimento em ripado de madeira na fachada principal",
}
MATERIAIS_COBERTURA = {"telha_ceramica": "Telha cerâmica vermelha (tipo Marselha / lusa)", "telha_preta": "Telha cerâmica preta",
                       "zinco": "Chapa de zinco", "plana_seixo": "Cobertura plana com proteção em seixo"}
CAIXILHARIA = {"aluminio_antracite": "Alumínio lacado antracite com corte térmico, vidro duplo",
               "aluminio_branco": "Alumínio lacado branco com corte térmico, vidro duplo",
               "madeira": "Madeira, vidro duplo", "pvc_branco": "PVC branco, vidro duplo"}
_SINONIMOS = {"granito": "granito", "pedra": "granito", "madeira": "madeira", "ripado": "madeira", "xisto": "xisto",
              "tijolo": "tijolo", "betão": "betao", "betao": "betao", "branco": "reboco_branco", "reboco": "reboco_branco",
              "moderno": "misto_madeira_reboco", "rústico": "granito", "rustico": "granito"}


def material_fachada(txt: Optional[str]) -> str:
    t = (txt or "").lower().strip()
    if t in MATERIAIS_FACHADA:
        return t
    hits = [v for k, v in _SINONIMOS.items() if k in t]
    if "granito" in hits and "madeira" in hits:
        return "misto_granito_madeira"
    if "granito" in hits and "reboco_branco" in hits:
        return "misto_granito_reboco"
    if "madeira" in hits and "reboco_branco" in hits:
        return "misto_madeira_reboco"
    return hits[0] if hits else "reboco_branco"


# ------------------------------------------------------------------ vãos (janelas e portas)
def vaos(plan: Dict[str, Any], volume: dict, fachada_sol: str) -> List[Dict[str, Any]]:
    """Um vão por compartimento habitável em fachada exterior; sala com envidraçado amplo; porta principal na entrada.
    Coordenadas no referencial do terreno: fachada (frente/tardoz/esquerda/direita), x ao longo da fachada, z cota."""
    x0, y0, x1, y1 = plan["casa_rect"]
    sh = float(volume.get("storey_h_m") or 3.0)
    out = []
    for p in plan["pisos"]:
        zb = p["piso"] * sh
        for c in p["compartimentos"]:
            for fach, ok in (("frente", abs(c["y0"] - y0) < 1e-6), ("tardoz", abs(c["y1"] - y1) < 1e-6)):
                if not ok:
                    continue
                w = c["x1"] - c["x0"]
                t = c["tipo"]
                if t == "sala":
                    larg, alt, peit, tipo = min(w - 0.8, 4.8 if fach == fachada_sol else 2.4), 2.3, 0.0, "envidracado"
                elif t in ("quarto", "escritorio"):
                    larg, alt, peit, tipo = min(w - 0.8, 1.8 if fach == fachada_sol else 1.2), 1.4 if fach != fachada_sol else 2.2, 0.0 if fach == fachada_sol else 0.9, "janela"
                elif t == "cozinha":
                    larg, alt, peit, tipo = min(w - 0.6, 1.6), 1.2, 1.0, "janela"
                elif t in ("wc", "wc_social", "lavandaria"):
                    larg, alt, peit, tipo = min(w - 0.4, 0.8), 0.6, 1.5, "janela"
                elif t == "entrada" and fach == "frente" and p["piso"] == 0:
                    larg, alt, peit, tipo = min(w - 0.4, 1.2), 2.3, 0.0, "porta"
                else:
                    continue
                if larg < 0.5:
                    continue
                cx = (c["x0"] + c["x1"]) / 2
                out.append({"fachada": fach, "piso": p["piso"], "compartimento": c["nome"], "tipo": tipo,
                            "x0": round(cx - larg / 2, 3), "x1": round(cx + larg / 2, 3),
                            "z0": round(zb + peit + 0.0, 3), "z1": round(zb + peit + alt, 3)})
    return out


# ------------------------------------------------------------------ planta de localização
def planta_localizacao(orto_b64: Optional[str], bbox: Optional[str], parcel_ll: List, casa_ll: List[List],
                       titulo: str = "Planta de localização (ortofotomapa)", fonte: str = "") -> bytes:
    Wimg, Himg = 1600, 1130
    img = Image.new("RGB", (Wimg, Himg), "white")
    dr = ImageDraw.Draw(img)
    V._header(dr, Wimg, titulo)
    S = 960
    ox, oy = (Wimg - S) // 2, 70
    if orto_b64 and bbox:
        try:
            ph = Image.open(io.BytesIO(base64.b64decode(orto_b64))).convert("RGB").resize((S, S))
            img.paste(ph, (ox, oy))
        except Exception:  # noqa: BLE001
            dr.rectangle([ox, oy, ox + S, oy + S], fill=(235, 235, 230))
    else:
        dr.rectangle([ox, oy, ox + S, oy + S], fill=(235, 235, 230))
        dr.text((ox + S / 2, oy + S / 2), "Ortofotomapa indisponível — juntar planta de localização municipal",
                fill=V.GREY, font=V._font(20), anchor="mm")
    if bbox:
        lo0, la0, lo1, la1 = [float(v) for v in bbox.split(",")]

        def P(la, lo):
            return ox + (lo - lo0) / (lo1 - lo0) * S, oy + (la1 - la) / (la1 - la0) * S
        if parcel_ll:
            pts = [P(*p) for p in parcel_ll]
            dr.line(pts + [pts[0]], fill=(230, 40, 40), width=5)
        for poly in casa_ll:
            pts = [P(*p) for p in poly]
            dr.polygon(pts, fill=(255, 210, 90), outline=(40, 40, 40))
        # escala gráfica (20 m)
        m_px = S / ((lo1 - lo0) * 111_320 * math.cos(math.radians((la0 + la1) / 2)))
        L = 20 * m_px
        dr.rectangle([ox + 20, oy + S - 40, ox + 20 + L, oy + S - 30], fill="white", outline="black")
        dr.rectangle([ox + 20, oy + S - 40, ox + 20 + L / 2, oy + S - 30], fill="black")
        dr.text((ox + 20, oy + S - 58), "0            10           20 m", fill="white", font=V._font(16))
    # norte (ortofoto orientada a norte)
    nx, ny = ox + S - 50, oy + 70
    dr.polygon([(nx, ny - 40), (nx - 14, ny + 10), (nx, ny), (nx + 14, ny + 10)], fill="white", outline="black")
    dr.text((nx, ny - 58), "N", fill="white", font=V._font(24), anchor="mm")
    lx = ox + S + 30
    dr.text((lx, 120), "Legenda", fill=V.INK, font=V._font(20))
    dr.line([(lx, 160), (lx + 40, 160)], fill=(230, 40, 40), width=5)
    dr.text((lx + 50, 150), "Limite do terreno", fill=V.INK, font=V._font(16))
    dr.rectangle([lx, 185, lx + 40, 205], fill=(255, 210, 90), outline=(40, 40, 40))
    dr.text((lx + 50, 185), "Construção proposta", fill=V.INK, font=V._font(16))
    if fonte:
        dr.text((lx, 240), "Fonte:", fill=V.GREY, font=V._font(15))
        for k, ln in enumerate(_wrap(fonte, 28)):
            dr.text((lx, 262 + 20 * k), ln, fill=V.GREY, font=V._font(15))
    V._footer(dr, Wimg, Himg, "Limite do terreno a confirmar por levantamento topográfico e certidão predial.")
    return V._png(img)


def _wrap(t: str, n: int) -> List[str]:
    out, cur = [], ""
    for w in t.split():
        if len(cur) + len(w) + 1 > n:
            out.append(cur)
            cur = w
        else:
            cur = (cur + " " + w).strip()
    return out + ([cur] if cur else [])


# ------------------------------------------------------------------ planta topográfica indicativa
def planta_topografica(topo: Dict[str, Any], parcel_m: List, casa_rect, garagem_rect=None, soleira: Optional[float] = None) -> bytes:
    Wimg, Himg = 1600, 1130
    img = Image.new("RGB", (Wimg, Himg), "white")
    dr = ImageDraw.Draw(img)
    V._header(dr, Wimg, "Planta topográfica indicativa (altimetria de satélite)")
    xs = [p[0] for p in parcel_m]
    ys = [p[1] for p in parcel_m]
    mx0, mx1, my0, my1 = min(xs) - 4, max(xs) + 4, min(ys) - 4, max(ys) + 4
    s = min(1200 / (mx1 - mx0), 900 / (my1 - my0))
    ox = (Wimg - (mx1 - mx0) * s) / 2
    oy = 90 + (my1 - my0) * s

    def P(x, y):
        return ox + (x - mx0) * s, oy - (y - my0) * s

    g = topo.get("grelha") or []
    pl = topo["plano"]

    gx = sorted({q["x"] for q in g})
    gy = sorted({q["y"] for q in g})
    gz = {(q["x"], q["y"]): q["z"] for q in g}

    def z_at(x, y):   # interpolação bilinear na grelha regular medida (plano médio fora da grelha)
        if len(gx) < 2 or len(gy) < 2 or not (gx[0] <= x <= gx[-1] and gy[0] <= y <= gy[-1]):
            return pl["a"] + pl["b"] * x + pl["c"] * y
        i = max(0, min(len(gx) - 2, next(k for k in range(len(gx) - 1) if x <= gx[k + 1])))
        j = max(0, min(len(gy) - 2, next(k for k in range(len(gy) - 1) if y <= gy[k + 1])))
        x0_, x1_, y0_, y1_ = gx[i], gx[i + 1], gy[j], gy[j + 1]
        try:
            z00, z10, z01, z11 = gz[(x0_, y0_)], gz[(x1_, y0_)], gz[(x0_, y1_)], gz[(x1_, y1_)]
        except KeyError:
            return pl["a"] + pl["b"] * x + pl["c"] * y
        tx = (x - x0_) / ((x1_ - x0_) or 1)
        ty = (y - y0_) / ((y1_ - y0_) or 1)
        return (z00 * (1 - tx) * (1 - ty) + z10 * tx * (1 - ty) + z01 * (1 - tx) * ty + z11 * tx * ty)
    step = 0.5
    zs_all = [q["z"] for q in g] or [pl["a"]]
    zmin, zmax = min(zs_all), max(zs_all)
    span = max(0.5, zmax - zmin)
    if span > 8:
        step = 1.0
    if span > 20:
        step = 2.0
    # raster de cores + curvas de nível (fronteiras entre classes)
    cell = 6
    W_px, H_px = int((mx1 - mx0) * s), int((my1 - my0) * s)
    grid = {}
    for i in range(0, W_px, cell):
        for j in range(0, H_px, cell):
            x = mx0 + i / s
            y = my1 - j / s
            z = z_at(x, y)
            grid[(i, j)] = z
            t = (z - zmin) / span
            col = (int(225 - 40 * t), int(230 - 20 * t), int(205 - 60 * t))
            dr.rectangle([ox + i, 90 + j, ox + i + cell, 90 + j + cell], fill=col)
    for (i, j), z in grid.items():
        for di, dj in ((cell, 0), (0, cell)):
            z2 = grid.get((i + di, j + dj))
            if z2 is not None and math.floor(z / step) != math.floor(z2 / step):
                dr.rectangle([ox + i + di - 1, 90 + j + dj - 1, ox + i + di + 1, 90 + j + dj + 1], fill=(120, 95, 60))
    pts = [P(*p) for p in parcel_m]
    dr.line(pts + [pts[0]], fill=(230, 40, 40), width=4)
    for r, col in ((casa_rect, (255, 210, 90)), (garagem_rect, (240, 170, 120))):
        if r:
            a, b = P(r[0], r[3]), P(r[2], r[1])
            dr.rectangle([a, b], fill=col, outline=V.INK, width=2)
    for q in g:
        x, y = P(q["x"], q["y"])
        if ox <= x <= ox + W_px and 90 <= y <= 90 + H_px:
            dr.ellipse([x - 3, y - 3, x + 3, y + 3], fill=V.INK)
            dr.text((x + 5, y - 8), f"{q['z']:.1f}", fill=V.INK, font=V._font(13))
    lx = 40
    linhas = [f"Cotas: {zmin:.1f} a {zmax:.1f} m (curvas de {step:g} m)",
              f"Declive médio: {topo.get('declive_pct', 0):.1f} %, a descer para a {topo.get('descida', '?')}",
              f"Fonte: {topo.get('fonte', '')}"]
    if soleira is not None:
        linhas.insert(1, f"Cota de soleira proposta: {soleira:.2f} m")
    for k, ln in enumerate(linhas):
        dr.text((lx, Himg - 140 + 22 * k), ln, fill=V.INK, font=V._font(16))
    V._footer(dr, Wimg, Himg, "INDICATIVO — substituir pelo levantamento topográfico georreferenciado (PT-TM06/ETRS89) feito por topógrafo.")
    return V._png(img)


# ------------------------------------------------------------------ memória descritiva (determinística)
def _n(v, casas=2):
    s = f"{float(v):,.{casas}f}"
    return s.replace(",", " ").replace(".", ",")


def memoria_descritiva(processo: Dict[str, Any], verif: Dict[str, Any]) -> str:
    """Memória descritiva e justificativa escrita a partir dos dados do processo (todos os números vêm do quadro)."""
    a = processo.get("auto") or {}
    q = verif.get("quadro") or {}
    t = processo.get("terreno") or {}
    pdm = processo.get("pdm") or {}
    mat = a.get("materiais") or {}
    prog = a.get("programa") or {}
    rj = verif.get("rjue") or {}
    pl = (a.get("plantas") or {}).get("pisos") or []
    imp = a.get("implantacao") or {}
    linhas = [
        "MEMÓRIA DESCRITIVA E JUSTIFICATIVA",
        "",
        "1. Identificação",
        f"Pretende-se construir uma moradia unifamiliar de tipologia {prog.get('tipologia', '')}, no prédio sito em "
        f"{t.get('morada') or '—'}, freguesia de {t.get('freguesia') or '—'}, concelho de {t.get('concelho') or '—'}, "
        f"com a área de {_n(q.get('area_terreno_m2', 0))} m² ("
        + ("área estimada, a confirmar na caderneta predial e no levantamento" if a.get("area_terreno_hipotese")
           else q.get('area_terreno_origem', '')) + ").",
        "",
        "2. Enquadramento urbanístico",
        f"Segundo a Carta do Regime de Uso do Solo do {pdm.get('plano') or 'PDM'}, o prédio situa-se em "
        f"{pdm.get('classe_espaco') or 'classe de espaço a confirmar'}. "
        f"O procedimento de controlo prévio aplicável é: {rj.get('titulo_regra') or rj.get('procedimento') or '—'}.",
        "Os parâmetros numéricos do regulamento do PDM devem ser confirmados no regulamento em vigor; a proposta respeita "
        "alvos prudentes de projeto (índices, alturas e afastamentos) indicados no quadro de áreas.",
        "",
        "3. Descrição da proposta",
        f"A moradia desenvolve-se em {q.get('n_pisos')} piso(s) acima da cota de soleira, com a implantação de "
        f"{_n(q.get('area_implantacao_principal_m2', 0))} m² e uma área de construção total de {_n(q.get('area_construcao_m2', 0))} m².",
    ]
    for p in pl:
        nomes = ", ".join(f"{c['nome'].lower()} ({_n(c['area_util_m2'], 1)} m²)" for c in p["compartimentos"]
                          if c["tipo"] not in ("circulacao",))
        linhas.append(f"{p['nome']}: {nomes}.")
    if (processo.get("volume") or {}).get("blocks"):
        b = processo["volume"]["blocks"][0]
        nl = q.get('lugares_previstos') or 0
        linhas.append(f"Garagem anexa com {_n(b['l_m'])} m × {_n(b['w_m'])} m, para {nl} {'lugar' if nl == 1 else 'lugares'}.")
    linhas += [
        "",
        "4. Implantação e orientação",
        *(imp.get("decisoes") or []),
        f"Afastamentos: frontal {_n(q['afastamentos_m']['frontal'])} m, laterais {_n(q['afastamentos_m']['lateral_esquerdo'])} m e "
        f"{_n(q['afastamentos_m']['lateral_direito'])} m, tardoz {_n(q['afastamentos_m']['tardoz'])} m." if q.get("afastamentos_m") else "",
        "",
        "5. Volumetria e alturas",
        f"Altura da fachada de {_n(q.get('altura_fachada_m', 0))} m e altura total de {_n(q.get('altura_total_m', 0))} m; "
        f"piso a piso de {_n(q.get('piso_a_piso_m', 0))} m e pé-direito livre de {_n(q.get('pe_direito_livre_m', 0))} m "
        "(RGEU, art.º 65.º). Cobertura: " + (q.get("cobertura") or "").lower() + ".",
        "",
        "6. Materiais e acabamentos",
        f"Fachadas: {MATERIAIS_FACHADA.get(mat.get('fachada'), '—')}. Cobertura: {MATERIAIS_COBERTURA.get(mat.get('cobertura'), '—')}. "
        f"Caixilharia: {CAIXILHARIA.get(mat.get('caixilharia'), '—')}.",
        "",
        "7. Infraestruturas",
        "Ligação às redes públicas de abastecimento de água, drenagem de águas residuais, eletricidade e telecomunicações "
        "existentes na via, a confirmar com as entidades gestoras; águas pluviais conduzidas para a via ou infiltradas no prédio.",
        "",
        "8. Normas aplicáveis",
        "RJUE (DL 555/99, na redação em vigor), RGEU, Regulamento do PDM, regime das acessibilidades (DL 163/2006), "
        "desempenho energético (DL 101-D/2020), segurança contra incêndio (DL 220/2008) e acústica (DL 129/2002), "
        "a desenvolver nos projetos de especialidades.",
        "",
        "Documento preparado automaticamente pelo ConstruPilot a partir dos dados do processo; a rever e assinar pelo técnico autor.",
    ]
    return "\n".join(l for l in linhas if l is not None)
