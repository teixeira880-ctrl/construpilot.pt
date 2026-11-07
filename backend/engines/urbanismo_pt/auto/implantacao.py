"""Implantação automática da moradia e da garagem no terreno.

Regras (determinísticas e explicadas, para que o resultado seja sempre o mesmo para os mesmos dados):
1. Zona edificável = terreno recuado dos afastamentos (frente, laterais, tardoz) — valores do PDM se conhecidos,
   senão alvos prudentes (registados como hipóteses de projeto, nunca como valores municipais).
2. Profundidade do volume entre 8 e 12 m; mais estreita quando o declive é forte no sentido da profundidade (menos aterro).
3. Sala e quartos na fachada mais bem exposta ao sol (azimute mais próximo de sul); garagem do lado menos exposto.
4. Jardim principal do lado do sol: se o sol está no tardoz, a casa encosta ao afastamento frontal (acesso curto);
   se está na frente, a casa recua para libertar um jardim frontal.
5. Verificação final de tudo com geometria exata (shapely): se algo não cabe, o motor diz porquê em vez de forçar.
"""
from __future__ import annotations

import math
from typing import Any, Dict, List, Optional, Tuple

from shapely.geometry import Polygon, box

ALVOS_PRUDENTES = {"afastamento_frontal_min_m": 5.0, "afastamento_lateral_min_m": 3.0, "afastamento_tardoz_min_m": 6.0,
                   "io_max_pct": 30.0, "iu_max": 0.60, "altura_fachada_max_m": 6.5, "n_pisos_max": 2}
PISO_A_PISO_M = 3.0      # ≥ 2,70 m do RGEU, com folga para pavimentos e tetos
LAJE_M = 0.30


def _sol(az: float) -> float:
    """Exposição solar de uma fachada (1 = sul, -1 = norte)."""
    return math.cos(math.radians(az - 180.0))


def alvos(pdm: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Alvos de projeto: o valor do PDM quando existe, senão o prudente — com a origem de cada um."""
    out, origem = {}, {}
    for k, v in ALVOS_PRUDENTES.items():
        x = (pdm or {}).get(k)
        if isinstance(x, (int, float)) and x > 0:
            out[k], origem[k] = float(x), "PDM"
        else:
            out[k], origem[k] = v, "alvo prudente (hipótese de projeto)"
    return {"valores": out, "origem": origem}


GAP_GARAGEM_EXT_M = 1.5        # garagem exterior (independente): afastada da casa
PISCINA_AFAST_LIMITES_M = 2.0  # alvo prudente aos limites do terreno (o regulamento municipal pode exigir mais)
PISCINA_AFAST_CASA_M = 2.0
PISCINA_PADRAO = (8.0, 4.0)


def _forma_l(A: float, d1: float, quota_ala: float = 0.4) -> Optional[Dict[str, float]]:
    """Casa em L: corpo à frente (profundidade d1, largura total) + ala no tardoz com a largura de um braço.
    `quota_ala`: fração da área da zona de noite (quartos e instalações sanitárias) — define o tamanho da ala."""
    ww = max(6.5, min(d1, 9.0))
    q = max(0.3, min(0.65, quota_ala))
    Lb = (1 - q) * A / d1
    if Lb < ww + 4.0:
        Lb = ww + 4.0
    e = (A - Lb * d1) / ww
    if e < 4.0:
        return None
    return {"L": round(Lb, 2), "W": round(d1 + e, 2), "ww": round(ww, 2), "e": round(e, 2), "d1": round(d1, 2)}


def _poly_l(x0: float, y0: float, g: Dict[str, float]) -> Polygon:
    L, W, ww, e = g["L"], g["W"], g["ww"], g["e"]
    return Polygon([(x0, y0), (x0 + L, y0), (x0 + L, y0 + W - e), (x0 + ww, y0 + W - e), (x0 + ww, y0 + W), (x0, y0 + W)])


def piscina(parcel: Polygon, casa: Polygon, garagem: Optional[Polygon], dims: Tuple[float, float],
            fachada_sol: str, patio: Optional[Polygon] = None) -> Dict[str, Any]:
    """Posição da piscina no jardim: dentro do terreno com afastamento aos limites, longe da casa e da garagem,
    do lado do sol e o mais perto possível da sala; numa casa em L prefere o pátio (abrigado)."""
    pl, pw = dims
    zona = parcel.buffer(-PISCINA_AFAST_LIMITES_M, join_style=2)
    if zona.is_empty:
        return {"ok": False, "motivo": "terreno sem espaço para a piscina com os afastamentos aos limites"}
    minx, miny, maxx, maxy = zona.bounds
    cminy, cmaxy = casa.bounds[1], casa.bounds[3]
    best, best_s = None, None
    step = 0.5
    obst = [casa] + ([garagem] if garagem is not None else [])
    for (a, b) in ((pl, pw), (pw, pl)):
        x = minx
        while x + a <= maxx + 1e-9:
            y = miny
            while y + b <= maxy + 1e-9:
                r = box(x, y, x + a, y + b)
                if zona.contains(r) and all(r.distance(o) >= (PISCINA_AFAST_CASA_M if o is casa else 1.5) - 1e-9 for o in obst):
                    cy = y + b / 2
                    lado_ok = cy >= cmaxy if fachada_sol == "tardoz" else cy <= cminy
                    s = r.distance(casa) + (0 if lado_ok else 25) - (8 if patio is not None and patio.intersection(r).area > 0.5 * a * b else 0)
                    if best_s is None or s < best_s:
                        best, best_s = (round(x, 2), round(y, 2), round(a, 2), round(b, 2)), s
                y += step
            x += step
    if not best:
        return {"ok": False, "motivo": "não há espaço livre no jardim para uma piscina de "
                                       f"{_pt(pl)} × {_pt(pw)} m com os afastamentos prudentes"}
    x, y, a, b = best
    return {"ok": True, "x_m": x, "y_m": y, "l_m": a, "w_m": b, "profundidade_m": 1.5, "area_m2": round(a * b, 2)}


def implantar(ter: Dict[str, Any], topo: Optional[Dict[str, Any]], prog: Dict[str, Any],
              alv: Dict[str, Any], validar=None, forma: str = "retangulo", garagem_tipo: str = "integrada",
              piscina_dims: Optional[Tuple[float, float]] = None) -> Dict[str, Any]:
    """`validar(resultado) -> (ok, motivo)`: p. ex. as plantas dos pisos; se falhar, tenta a proporção seguinte.
    `forma`: «retangulo» ou «l»; `garagem_tipo`: «integrada» (encostada) ou «exterior» (independente, afastada);
    `piscina_dims`: (comprimento, largura) para implantar uma piscina descoberta no jardim."""
    a = alv["valores"]
    sf, sl, sr = a["afastamento_frontal_min_m"], a["afastamento_lateral_min_m"], a["afastamento_tardoz_min_m"]
    parcel = Polygon(ter["poligono_m"])
    L_plot, W_plot = ter["plot_l_m"], ter["plot_w_m"]
    minx, miny, maxx, maxy = parcel.bounds
    zona = parcel.buffer(-sl, join_style=2).intersection(box(minx - 1, miny + sf, maxx + 1, maxy - sr))
    decisoes: List[str] = []
    if zona.is_empty or zona.area < 30:
        return {"ok": False, "motivo": "O terreno é demasiado pequeno para os afastamentos aplicáveis "
                                       f"(frente {sf:g} m, laterais {sl:g} m, tardoz {sr:g} m)."}
    az = ter["azimutes"]
    sol_frente, sol_tardoz = _sol(az["frente"]), _sol(az["tardoz"])
    fachada_sol = "tardoz" if sol_tardoz >= sol_frente else "frente"
    lado_garagem = "esquerda" if _sol(az["esquerda"]) <= _sol(az["direita"]) else "direita"

    # profundidade preferida: declive no sentido y penaliza volumes profundos
    c = abs((topo or {}).get("plano", {}).get("c", 0.0)) if topo and topo.get("ok") else 0.0
    decl_y = round(c * 100, 1)          # valor registado no resultado: o texto cita exatamente este número
    A1 = prog["area_bruta_total_m2"] / prog["n_pisos"]
    W_pref = min(10.5, max(8.0, math.sqrt(A1 / 1.45)))          # proporção ~1,45 : 1 (fachada longa ao sol)
    if decl_y > 10:
        W_pref = min(W_pref, 8.5)
    elif decl_y > 5:
        W_pref = min(W_pref, 9.5)
    io_max, iu_max = a["io_max_pct"], a["iu_max"]
    area_ter = ter["area_m2"]
    gar = prog.get("garagem")
    tentativas = []
    for n_pisos in [prog["n_pisos"]]:   # o pipeline tenta outras variantes (2 pisos, menos lugares) com o programa refeito
        A = prog["area_bruta_total_m2"] / n_pisos
        for W in sorted({round(W_pref, 2), 7.5, 8.0, 8.5, 9.0, 9.5, 10.0, 10.5, 11.0, 12.0}, key=lambda w: abs(w - W_pref)):
            gl_ = None
            if forma == "l":
                comp = [r for r in prog["compartimentos"] if r["piso"] == 0]
                noite = sum(r["area_projeto_m2"] for r in comp if r["tipo"] in ("quarto", "wc"))
                circ = sum(r["area_projeto_m2"] for r in comp if r["tipo"] == "circulacao") / 2
                total = sum(r["area_projeto_m2"] for r in comp) or 1.0
                gl_ = _forma_l(A, W, (noite + circ) / total)
                if not gl_:
                    continue
                L, W_tot = gl_["L"], gl_["W"]
                area_casa = round(L * gl_["d1"] + gl_["ww"] * gl_["e"], 2)
            else:
                L, W_tot = round(A / W, 2), W
                area_casa = L * W
                if L < W * 0.7:      # volume demasiado «fundo» (frente muito curta para a distribuição em duas faixas)
                    continue
            gl, gw = (gar["l_m"], gar["w_m"]) if gar else (0.0, 0.0)
            gap = GAP_GARAGEM_EXT_M if gar and garagem_tipo == "exterior" else 0.0
            largura = L + gl + gap
            atras = False
            zx0, zy0, zx1, zy1 = zona.bounds
            if gar and gap and largura > zx1 - zx0 + 1e-6 and W_tot + gap + gw <= zy1 - zy0 + 1e-6:
                largura, atras = L, True   # garagem independente atrás da casa (acesso lateral)
            zx0, zy0, zx1, zy1 = zona.bounds
            if largura > zx1 - zx0 + 1e-6 or W_tot > zy1 - zy0 + 1e-6:
                tentativas.append(f"{n_pisos} piso(s), {L:.1f}×{W_tot:.1f} m: não cabe na zona edificável")
                continue
            # índices com os alvos
            impl = area_casa + gl * gw
            constr = area_casa * n_pisos + gl * gw
            if impl / area_ter * 100 > io_max + 1e-6 or constr / area_ter > iu_max + 1e-6:
                tentativas.append(f"{n_pisos} piso(s), {L:.1f}×{W:.1f} m: excede Io/Iu alvo")
                continue
            # posição em y (frente/tardoz)
            folga_y = (zy1 - zy0) - (W_tot + gap + gw if atras else max(W_tot, gw))
            y0 = zy0 if fachada_sol == "tardoz" else zy0 + min(6.0, folga_y * 0.5)
            # posição em x: grupo casa + garagem centrado na zona edificável
            folga_x = (zx1 - zx0) - largura
            gx0 = zx0 + folga_x / 2
            if atras:
                h_rect = (gx0, y0, gx0 + L, y0 + W_tot)
                g_rect = (gx0 + L - gl, y0 + W_tot + gap, gx0 + L, y0 + W_tot + gap + gw)
            elif gar and lado_garagem == "esquerda" and forma != "l":
                g_rect = (gx0, y0, gx0 + gl, y0 + gw)
                h_rect = (gx0 + gl + gap, y0, gx0 + gl + gap + L, y0 + W_tot)
            else:   # numa casa em L a garagem fica do lado do pátio (a ala dos quartos está à esquerda)
                h_rect = (gx0, y0, gx0 + L, y0 + W_tot)
                g_rect = (gx0 + L + gap, y0, gx0 + L + gap + gl, y0 + gw) if gar else None
            casa_poly = _poly_l(h_rect[0], h_rect[1], gl_) if gl_ else box(*h_rect)
            casa_ok = zona.buffer(1e-6).contains(casa_poly)
            gar_ok = (not gar) or zona.buffer(1e-6).contains(box(*g_rect))
            if not (casa_ok and gar_ok):
                tentativas.append(f"{n_pisos} piso(s), {L:.1f}×{W_tot:.1f} m: forma do terreno não permite")
                continue
            if n_pisos > a["n_pisos_max"]:
                continue
            # cota de soleira e movimento de terras (plano médio)
            soleira, terras = _terras(topo, h_rect)
            decisoes += [
                (f"Moradia em L com {_pt(L)} m de frente × {_pt(W_tot)} m de fundo (corpo de dia à frente, ala dos quartos com "
                 f"{_pt(gl_['ww'])} m de largura no tardoz), em {n_pisos} {'piso' if n_pisos == 1 else 'pisos'}."
                 if gl_ else f"Moradia com {_pt(L)} m de frente × {_pt(W)} m de fundo, em {n_pisos} {'piso' if n_pisos == 1 else 'pisos'}."),
                (f"Sala voltada para o {_rumo(az[fachada_sol])} (fachada de {'tardoz' if fachada_sol == 'tardoz' else 'frente'}), "
                 "a melhor exposição solar do terreno; quartos na ala do tardoz, abertos para o pátio formado pelo L."
                 if gl_ else
                 f"Sala e quartos voltados para o {_rumo(az[fachada_sol])} (fachada de {'tardoz' if fachada_sol == 'tardoz' else 'frente'}), "
                 "a melhor exposição solar do terreno."),
                ("Casa encostada ao afastamento frontal: acesso curto e jardim grande a tardoz, do lado do sol."
                 if fachada_sol == "tardoz" else "Casa recuada para criar um jardim frontal soalheiro."),
            ]
            if gar and garagem_tipo == "exterior":
                decisoes.append(f"Garagem independente para {gar['lugares']} {'carro' if gar['lugares'] == 1 else 'carros'}, "
                                f"afastada {_pt(gap)} m da casa, "
                                + ("no tardoz, com acesso lateral pelo logradouro (a frente não tinha largura para casa e garagem lado a lado)."
                                   if atras else "com acesso direto à via."))
            elif gar:
                decisoes.append(f"Garagem para {gar['lugares']} {'carro' if gar['lugares'] == 1 else 'carros'} do lado {'esquerdo' if lado_garagem == 'esquerda' else 'direito'} "
                                f"({_rumo(az[lado_garagem])}), o menos exposto ao sol, com acesso direto à via.")
            if decl_y > 5:
                decisoes.append(f"Declive de {str(decl_y).replace('.', ',')} % no sentido da profundidade: "
                                + (f"corpo principal com {_pt(W)} m de fundo" if gl_ else f"volume com {_pt(W)} m de fundo")
                                + " para reduzir aterros e escavações.")
            volume = {
                "shape": "l" if gl_ else "rectangle", "plot_l_m": round(L_plot, 2), "plot_w_m": round(W_plot, 2),
                "footprint_l_m": round(L, 2), "footprint_w_m": round(W_tot, 2),
                "wing_l_m": round(L - gl_["ww"], 2) if gl_ else 0, "wing_w_m": gl_["e"] if gl_ else 0,
                "levels": n_pisos, "storey_h_m": PISO_A_PISO_M, "espessura_laje_m": LAJE_M,
                "total_h_m": round(n_pisos * PISO_A_PISO_M + 2.0, 2), "roof_type": "duas_aguas",
                "setback_front_m": round(h_rect[1], 2), "setback_side_m": round(h_rect[0], 2),
                "blocks": ([{"name": "Garagem" if gap == 0 else "Garagem (independente)", "l_m": round(gl, 2), "w_m": round(gw, 2), "x_m": round(g_rect[0], 2),
                             "y_m": round(g_rect[1], 2), "h_m": gar["h_m"]}] if gar else []),
                "uso": "habitacao", "n_fogos": 1, "lugares_previstos": prog.get("lugares") or (gar or {}).get("lugares") or 0,
            }
            if piscina_dims:
                patio = box(h_rect[0] + gl_["ww"], h_rect[1] + gl_["d1"], h_rect[2], h_rect[3]) if gl_ else None
                pisc = piscina(parcel, casa_poly, box(*g_rect) if g_rect else None, piscina_dims, fachada_sol, patio)
                if pisc["ok"]:
                    volume["piscina"] = {k: pisc[k] for k in ("x_m", "y_m", "l_m", "w_m", "profundidade_m")}
                    decisoes.append(f"Piscina de {_pt(pisc['l_m'])} × {_pt(pisc['w_m'])} m no jardim, do lado do sol"
                                    + (", no pátio abrigado formado pelo L." if patio is not None and patio.intersects(box(
                                        pisc["x_m"], pisc["y_m"], pisc["x_m"] + pisc["l_m"], pisc["y_m"] + pisc["w_m"])) else "."))
            else:
                pisc = None
            res = {"ok": True, "volume": volume, "casa_rect": h_rect, "garagem_rect": g_rect, "fachada_sol": fachada_sol,
                   "forma": "l" if gl_ else "retangulo", "piscina": pisc, "geometria_l": gl_, "garagem_atras": atras,
                    "lado_garagem": lado_garagem, "n_pisos": n_pisos, "cota_soleira_m": soleira, "terras": terras,
                    "decisoes": decisoes, "zona_edificavel_m2": round(zona.area, 1),
                    "declive_profundidade_pct": decl_y}
            if validar:
                ok_v, motivo_v = validar(res)
                if not ok_v:
                    tentativas.append(f"{n_pisos} piso(s), {L:.1f}×{W_tot:.1f} m: {motivo_v}")
                    decisoes[:] = []
                    continue
            return res
    return {"ok": False, "motivo": "Não foi possível implantar a casa pedida neste terreno com os afastamentos e índices "
                                   "aplicáveis. Reduza a tipologia ou retire a garagem.", "tentativas": tentativas[:8]}


def _pt(v: float) -> str:
    return f"{v:.2f}".replace(".", ",")


def _rumo(az: float) -> str:
    nomes = ["norte", "nordeste", "este", "sudeste", "sul", "sudoeste", "oeste", "noroeste"]
    return nomes[int(((az % 360) + 22.5) // 45) % 8]


def _terras(topo, rect):
    if not topo or not topo.get("ok"):
        return None, None
    p = topo["plano"]
    x0, y0, x1, y1 = rect
    zs = []
    n = 8
    for i in range(n + 1):
        for j in range(n + 1):
            x, y = x0 + (x1 - x0) * i / n, y0 + (y1 - y0) * j / n
            zs.append(p["a"] + p["b"] * x + p["c"] * y)
    zmed = sum(zs) / len(zs)
    soleira = round(zmed + 0.15, 2)
    cel = (x1 - x0) * (y1 - y0) / len(zs)
    esc = sum(max(0.0, z - zmed) for z in zs) * cel
    ater = sum(max(0.0, zmed - z) for z in zs) * cel
    return soleira, {"escavacao_m3": round(esc, 1), "aterro_m3": round(ater, 1),
                     "desnivel_m": round(max(zs) - min(zs), 2)}
