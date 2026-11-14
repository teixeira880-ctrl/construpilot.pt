"""Mapa de quantidades AO VIVO da casa do Estúdio — medido na geometria editada, decomposto até aos parafusos.

Quantidades: todas MEDIDAS na casa do Estúdio (contornos L/T, pisos, piso a piso, vãos reais, divisões das plantas
escaladas ao contorno atual, anexos). Soluções construtivas: as escolhidas no Estúdio (fachada, cobertura,
caixilharia); o que o Estúdio não define (tijolo da parede, acabamentos por compartimento) é uma solução corrente
DECLARADA na descrição de cada artigo. A estrutura vem do motor de cálculo (bet_frame) sobre o contorno real.
"""
from __future__ import annotations

import math
from collections import defaultdict
from typing import Any, Dict, List

from engines.urbanismo_pt import volumes as V

SECO = {"cozinha", "wc", "wc_social", "lavandaria"}       # compartimentos com cerâmico
FACHADA_ART = {
    "reboco_branco": [("Reboco exterior e=2 cm (paredes exteriores)", "reboco"), ("Pintura exterior 2 demãos (paredes exteriores)", "pintura")],
    "granito": [("Revestimento em granito e=3 cm (fachadas)", "pedra")],
    "xisto": [("Revestimento em xisto e=4 cm (fachadas)", "pedra")],
    "madeira": [("Ripado de madeira (fachadas)", "ripado")],
    "tijolo": [("Tijolo face à vista — paramento exterior (contagem pelo formato 24x11,5x7)", "tijolo")],
    "betao": [],
}
COBERTURA_ART = {"telha_ceramica": "Cobertura em telha cerâmica", "telha_preta": "Cobertura em telha cerâmica preta",
                 "zinco": "Cobertura em zinco", "plana_seixo": "Cobertura plana não acessível (invertida, seixo)"}
CAIX_NOME = {"aluminio_antracite": "alumínio antracite", "aluminio_branco": "alumínio branco", "madeira": "madeira", "pvc_branco": "PVC branco"}


def _hip(t: str) -> str:
    return f"Medido na casa do Estúdio. Solução corrente (hipótese a confirmar): {t}."


def calcular(vol: Dict[str, Any], estilo: Dict[str, Any], vaos: List[Dict[str, Any]], plantas: Dict[str, Any] | None,
             com_estrutura: bool = True) -> Dict[str, Any]:
    from shapely.geometry import Polygon
    from shapely.ops import unary_union
    polys = V.building_polygons(vol)
    casa = unary_union([Polygon(p["pts"]) for p in polys if not p["annexe"]]).buffer(0)
    anexos = [p for p in polys if p["annexe"]]
    pisos = max(1, int(vol.get("levels") or 1))
    sh = float(vol.get("storey_h_m") or 2.8)
    H = pisos * sh
    perim = casa.exterior.length
    area_impl = casa.area
    fach = estilo.get("fachada") or "reboco_branco"
    telhado = estilo.get("telhado") or "duas_aguas"
    cob = "plana_seixo" if telhado == "plana" else (estilo.get("cobertura") or "telha_ceramica")
    inc = float(estilo.get("inclinacao_pct") if estilo.get("inclinacao_pct") is not None else 30) / 100
    beiral = float(estilo.get("beiral_m") if estilo.get("beiral_m") is not None else 0.5)
    L: List[Dict[str, Any]] = []

    def item(cap, des, un, q, desc):
        if q and q > 0.005:
            L.append({"kind": "item", "category": cap, "designation": des, "unit": un, "qty": round(q, 2), "description": desc})

    # ── vãos ──
    area_vaos = 0.0
    grupos = defaultdict(int)
    for o in vaos or []:
        w, h = float(o.get("x1", 0)) - float(o.get("x0", 0)), float(o.get("z1", 0)) - float(o.get("z0", 0))
        if w <= 0 or h <= 0 or int(o.get("piso") or 0) >= pisos:
            continue
        area_vaos += w * h
        tipo = o.get("tipo") or "janela"
        grupos[(tipo, round(w * 100), round(h * 100))] += 1
    caix = CAIX_NOME.get(estilo.get("caixilharia") or "aluminio_antracite", "alumínio")
    for (tipo, wc, hc), n in sorted(grupos.items()):
        nome = {"porta": "Caixilharia — porta exterior", "envidracado": "Caixilharia — porta de sacada/envidraçado", "janela": "Caixilharia — janela"}[tipo]
        item("Caixilharias", f"{nome} em {caix} {wc}x{hc} cm", "un", n,
             f"Medido na casa do Estúdio: {n} vão(s) de {wc/100:.2f} × {hc/100:.2f} m. Vidro duplo; perfis com corte térmico (hipótese).")
    # ── paredes exteriores ──
    bruta = perim * H
    liq = max(0.0, bruta - area_vaos)
    item("Paredes exteriores", "Alvenaria de tijolo térmico 30x19x24 — paredes exteriores", "m2", liq,
         _hip(f"tijolo térmico 30×19×24 cm; perímetro medido {perim:.2f} m × altura {H:.2f} m − vãos {area_vaos:.2f} m²"))
    for des, _ in FACHADA_ART.get(fach, FACHADA_ART["reboco_branco"]):
        item("Revestimentos exteriores", des, "m2", liq, f"Medido na casa do Estúdio (fachada «{fach}»): {liq:.2f} m² de paredes exteriores sem vãos; fita e proteções medidas à parte.")
    if fach.startswith("misto"):
        item("Revestimentos exteriores", "Reboco exterior e=2 cm (paredes exteriores)", "m2", liq * 0.65, _hip("fachada mista: 65 % reboco"))
        item("Revestimentos exteriores", "Pintura exterior 2 demãos (paredes exteriores)", "m2", liq * 0.65, _hip("fachada mista: 65 % reboco; fita e proteções medidas à parte"))
        item("Revestimentos exteriores", "Revestimento em granito e=3 cm (fachadas)" if "granito" in fach else "Ripado de madeira (fachadas)",
             "m2", liq * 0.35, _hip("fachada mista: 35 % do material de destaque"))
    item("Revestimentos interiores", "Reboco interior e=1,5 cm (face interior das paredes exteriores)", "m2", liq, _hip("estuque projetado 1,5 cm"))
    # ── compartimentos (plantas escaladas ao contorno atual) ──
    area_int_paredes = 0.0
    pav_flut = pav_cer = 0.0
    rod_flut = rod_cer = 0.0
    portas = defaultdict(int)
    if plantas and plantas.get("pisos"):
        a0, b0, a1, b1 = plantas["casa_rect"]
        x0, y0, x1, y1 = casa.bounds
        sx, sy = (x1 - x0) / max(a1 - a0, 1e-6), (y1 - y0) / max(b1 - b0, 1e-6)
        for p in plantas["pisos"]:
            if p["piso"] >= pisos:
                continue
            soma_per = 0.0
            for c in p["compartimentos"]:
                w, d = (c["x1"] - c["x0"]) * sx, (c["y1"] - c["y0"]) * sy
                soma_per += 2 * (w + d)
                if c["tipo"] not in ("circulacao", "escada", "entrada"):
                    portas["70x200" if c["tipo"] in ("wc", "wc_social") else "80x200"] += 1
                if c["tipo"] in SECO:
                    pav_cer += w * d
                    rod_cer += 2 * (w + d) - 0.8                  # menos a porta
                elif c["tipo"] != "escada":
                    pav_flut += w * d
                    rod_flut += 2 * (w + d) - 0.8
            area_int_paredes += max(0.0, (soma_per - perim) / 2) * sh
    else:
        pav_flut = area_impl * pisos * 0.8
        pav_cer = area_impl * pisos * 0.2
    for dim, n in sorted(portas.items()):
        item("Carpintarias", f"Porta interior {dim} cm (folha, aro, guarnições e ferragens)", "un", n,
             _hip(f"1 porta por compartimento ({n}), {dim.replace('x', ' × ')} cm; contada nas plantas"))
    item("Paredes interiores", "Alvenaria de tijolo 30x20x11 — paredes divisórias", "m2", area_int_paredes,
         _hip("tijolo furado 30×20×11 cm; comprimento das divisórias medido nas plantas × piso a piso"))
    item("Revestimentos interiores", "Reboco interior e=1,5 cm (paredes divisórias, 2 faces)", "m2", area_int_paredes * 2, _hip("estuque 1,5 cm nas duas faces"))
    item("Pinturas", "Pintura interior 2 demãos (paredes)", "m2", liq + area_int_paredes * 2, _hip("tinta aquosa, 2 demãos; fita e proteções medidas à parte"))
    item("Pinturas", "Pintura de tetos 2 demãos", "m2", area_impl * pisos, _hip("tetos estucados e pintados; fita e proteções medidas à parte"))
    item("Pavimentos", "Betonilha de regularização e=5 cm", "m2", pav_flut + pav_cer, _hip("betonilha 5 cm sob todos os pavimentos"))
    item("Pavimentos", "Pavimento flutuante (salas, quartos, circulações)", "m2", pav_flut, _hip("flutuante AC4 sobre subcamada; rodapé medido à parte"))
    item("Pavimentos", "Cerâmico 60x60 cm (cozinha, instalações sanitárias, lavandaria)", "m2", pav_cer, _hip("grés porcelânico 60×60 cm; rodapé medido à parte"))
    item("Pavimentos", "Rodapé em MDF lacado (salas, quartos, circulações)", "m", rod_flut, "Medido: perímetro dos compartimentos menos as portas.")
    item("Pavimentos", "Rodapé cerâmico (cozinha, instalações sanitárias, lavandaria)", "m", rod_cer, "Medido: perímetro dos compartimentos menos as portas.")
    per_vaos = sum(2 * ((float(o["x1"]) - float(o["x0"])) + (float(o["z1"]) - float(o["z0"]))) for o in vaos or [] if float(o.get("x1", 0)) > float(o.get("x0", 0)))
    item("Pinturas", "Fita de pintor / proteções (vãos e rodapés)", "m", 2 * per_vaos + rod_flut + rod_cer,
         "Medido: perímetro dos vãos (2 faces) + rodapés.")
    # ── cobertura ──
    if cob == "plana_seixo":
        area_cob = area_impl
    else:
        fat = math.sqrt(1 + inc ** 2) if telhado != "plana" else 1.0
        area_cob = sum((max(p["pts"], key=lambda q: q[0])[0] - min(q[0] for q in p["pts"]) + 2 * beiral) *
                       (max(q[1] for q in p["pts"]) - min(q[1] for q in p["pts"]) + 2 * beiral)
                       for p in polys if not p["annexe"]) * fat
    item("Cobertura", COBERTURA_ART.get(cob, "Cobertura em telha cerâmica"), "m2", area_cob,
         f"Medido na casa do Estúdio: telhado «{telhado}», inclinação {inc*100:.0f} %, beiral {beiral:.2f} m → {area_cob:.2f} m² de vertente.")
    if cob != "plana_seixo":
        item("Cobertura", "Caleira e remates de beirado em chapa lacada", "m", perim + 8 * beiral, "Medido: perímetro do beirado.")
    # ── anexos ──
    for a in anexos:
        pa = Polygon(a["pts"])
        ha = float(a.get("h_m") or 3.0)
        item(f"Anexo — {a['name']}", f"Alvenaria de tijolo 30x20x15 — paredes do anexo «{a['name']}»", "m2", pa.exterior.length * ha,
             _hip(f"tijolo 30×20×15; perímetro {pa.exterior.length:.2f} m × {ha:.2f} m"))
        item(f"Anexo — {a['name']}", f"Reboco exterior e=2 cm — anexo «{a['name']}»", "m2", pa.exterior.length * ha, _hip("reboco"))
        item(f"Anexo — {a['name']}", f"Cobertura plana não acessível — anexo «{a['name']}»", "m2", pa.area, "Medido: área do anexo.")
        item(f"Anexo — {a['name']}", f"Laje térrea e=0,15 — anexo «{a['name']}»", "m2", pa.area, "Medido: área do anexo.")
    # ── estrutura (cálculo) ──
    estrutura = None
    if com_estrutura:
        try:
            from engines import estrutura_implantacao as EI
            r = EI.calcular(list(casa.exterior.coords)[:-1], nome="Casa do Estúdio", pisos=pisos, pe_direito=sh, uso="habitation")
            L.extend(r["linhas"])
            estrutura = {"pilares": r["pilares"], "malha": r["malha"]}
        except Exception as e:  # noqa: BLE001
            estrutura = {"erro": f"Estrutura não calculada ({type(e).__name__}: {str(e)[:120]})"}
    return {"linhas": L, "estrutura": estrutura,
            "resumo": {"area_implantacao_m2": round(area_impl, 2), "area_bruta_m2": round(area_impl * pisos, 2), "perimetro_m": round(perim, 2),
                       "paredes_exteriores_m2": round(liq, 2), "vaos_m2": round(area_vaos, 2), "cobertura_m2": round(area_cob, 2)}}
