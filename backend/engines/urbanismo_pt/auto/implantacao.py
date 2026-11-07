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
from typing import Any, Dict, List, Optional

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


def implantar(ter: Dict[str, Any], topo: Optional[Dict[str, Any]], prog: Dict[str, Any],
              alv: Dict[str, Any], validar=None) -> Dict[str, Any]:
    """`validar(resultado) -> (ok, motivo)`: p. ex. as plantas dos pisos; se falhar, tenta a proporção seguinte."""
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
            L = round(A / W, 2)
            if L < W * 0.7:      # volume demasiado «fundo» (frente muito curta para a distribuição em duas faixas)
                continue
            gl, gw = (gar["l_m"], gar["w_m"]) if gar else (0.0, 0.0)
            largura = L + gl
            zx0, zy0, zx1, zy1 = zona.bounds
            if largura > zx1 - zx0 + 1e-6 or W > zy1 - zy0 + 1e-6:
                tentativas.append(f"{n_pisos} piso(s), {L:.1f}×{W:.1f} m: não cabe na zona edificável")
                continue
            # índices com os alvos
            impl = L * W + gl * gw
            constr = L * W * n_pisos + gl * gw
            if impl / area_ter * 100 > io_max + 1e-6 or constr / area_ter > iu_max + 1e-6:
                tentativas.append(f"{n_pisos} piso(s), {L:.1f}×{W:.1f} m: excede Io/Iu alvo")
                continue
            # posição em y (frente/tardoz)
            folga_y = (zy1 - zy0) - max(W, gw)
            y0 = zy0 if fachada_sol == "tardoz" else zy0 + min(6.0, folga_y * 0.5)
            # posição em x: grupo casa + garagem centrado na zona edificável
            folga_x = (zx1 - zx0) - largura
            gx0 = zx0 + folga_x / 2
            if gar and lado_garagem == "esquerda":
                g_rect = (gx0, y0, gx0 + gl, y0 + gw)
                h_rect = (gx0 + gl, y0, gx0 + gl + L, y0 + W)
            else:
                h_rect = (gx0, y0, gx0 + L, y0 + W)
                g_rect = (gx0 + L, y0, gx0 + L + gl, y0 + gw) if gar else None
            casa_ok = zona.buffer(1e-6).contains(box(*h_rect))
            gar_ok = (not gar) or zona.buffer(1e-6).contains(box(*g_rect))
            if not (casa_ok and gar_ok):
                tentativas.append(f"{n_pisos} piso(s), {L:.1f}×{W:.1f} m: forma do terreno não permite")
                continue
            if n_pisos > a["n_pisos_max"]:
                continue
            # cota de soleira e movimento de terras (plano médio)
            soleira, terras = _terras(topo, h_rect)
            decisoes += [
                f"Moradia com {_pt(L)} m de frente × {_pt(W)} m de fundo, em {n_pisos} {'piso' if n_pisos == 1 else 'pisos'}.",
                f"Sala e quartos voltados para o {_rumo(az[fachada_sol])} (fachada de {'tardoz' if fachada_sol == 'tardoz' else 'frente'}), "
                "a melhor exposição solar do terreno.",
                ("Casa encostada ao afastamento frontal: acesso curto e jardim grande a tardoz, do lado do sol."
                 if fachada_sol == "tardoz" else "Casa recuada para criar um jardim frontal soalheiro."),
            ]
            if gar:
                decisoes.append(f"Garagem para {gar['lugares']} {'carro' if gar['lugares'] == 1 else 'carros'} do lado {'esquerdo' if lado_garagem == 'esquerda' else 'direito'} "
                                f"({_rumo(az[lado_garagem])}), o menos exposto ao sol, com acesso direto à via.")
            if decl_y > 5:
                decisoes.append(f"Declive de {str(decl_y).replace('.', ',')} % no sentido da profundidade: volume com {_pt(W)} m de fundo para "
                                "reduzir aterros e escavações.")
            volume = {
                "shape": "rectangle", "plot_l_m": round(L_plot, 2), "plot_w_m": round(W_plot, 2),
                "footprint_l_m": round(L, 2), "footprint_w_m": round(W, 2), "wing_l_m": 0, "wing_w_m": 0,
                "levels": n_pisos, "storey_h_m": PISO_A_PISO_M, "espessura_laje_m": LAJE_M,
                "total_h_m": round(n_pisos * PISO_A_PISO_M + 2.0, 2), "roof_type": "duas_aguas",
                "setback_front_m": round(h_rect[1], 2), "setback_side_m": round(h_rect[0], 2),
                "blocks": ([{"name": "Garagem", "l_m": round(gl, 2), "w_m": round(gw, 2), "x_m": round(g_rect[0], 2),
                             "y_m": round(g_rect[1], 2), "h_m": gar["h_m"]}] if gar else []),
                "uso": "habitacao", "n_fogos": 1, "lugares_previstos": prog.get("lugares") or (gar or {}).get("lugares") or 0,
            }
            res = {"ok": True, "volume": volume, "casa_rect": h_rect, "garagem_rect": g_rect, "fachada_sol": fachada_sol,
                    "lado_garagem": lado_garagem, "n_pisos": n_pisos, "cota_soleira_m": soleira, "terras": terras,
                    "decisoes": decisoes, "zona_edificavel_m2": round(zona.area, 1),
                    "declive_profundidade_pct": decl_y}
            if validar:
                ok_v, motivo_v = validar(res)
                if not ok_v:
                    tentativas.append(f"{n_pisos} piso(s), {L:.1f}×{W:.1f} m: {motivo_v}")
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
