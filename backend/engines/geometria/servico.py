"""Ponto de entrada: uma página de `plans_takeoff` → divisões, paredes, vãos, escala por consenso e confiança.

Escolhe sozinho o caminho certo:
  - DXF/DWG importado → traços CAD (px do aperçu), unidades declaradas;
  - PDF vetorial (traços suficientes) → traços em pontos PDF, cotas vetoriais, textos exatos;
  - imagem / digitalização / PDF que é só uma imagem → vetorização (`raster`) e o mesmo motor.

Devolve tudo em píxeis da imagem da página (para a sobreposição no ecrã) e em metros. Sem IA, sem I/O.
"""
from __future__ import annotations

import time

from engines.geometria import coerencia, escala, raster, vetor

VERSAO = "geometria-v3.0"
MIN_TRACOS_VETOR = 40


def _fonte(pagina: dict, tipo: str) -> str:
    if tipo == "dxf" or pagina.get("dxf_ratio"):
        return "dxf"
    vet = [v for v in pagina.get("vectors") or [] if v.get("type") in ("line", "rect", "quad")]
    if tipo == "pdf" and len(vet) >= MIN_TRACOS_VETOR:
        return "pdf_vetorial"
    return "imagem"


def analisar_pagina(pagina: dict, tipo: str = "pdf", calibracao: dict | None = None) -> dict:
    """`pagina` = elemento de `plans_takeoff.pages`; `calibracao` = {pixels_per_meter} feita pelo utilizador (opcional)."""
    t0 = time.time()
    fonte = _fonte(pagina, tipo)
    dpi = pagina.get("dpi")
    textos = pagina.get("text_blocks") or []
    px_por_u = 1.0
    cands = []
    ppm_user = (calibracao or {}).get("pixels_per_meter")
    if fonte == "pdf_vetorial":
        px_por_u = (dpi or 72) / 72
        linhas = vetor.linhas_de_vetores(pagina.get("vectors") or [])
        cotas = [{**c, "x1": c["x1"] / px_por_u, "y1": c["y1"] / px_por_u, "x2": c["x2"] / px_por_u, "y2": c["y2"] / px_por_u}
                 for c in pagina.get("pdf_dimensions") or [] if all(k in c for k in ("x1", "y1", "x2", "y2"))]
        cands += escala.candidatos_declarados(escala.escalas_declaradas(textos), escala.PT_POR_M_PAPEL)
        cands.append(escala.candidato_cotas(cotas))
    elif fonte == "dxf":
        linhas = vetor.linhas_de_vetores(pagina.get("vectors") or [])
        cotas = list(pagina.get("dxf_dimensions") or [])
        if pagina.get("dxf_ratio") and pagina.get("unit_to_m"):
            cands.append({"fonte": "unidades_cad", "u_por_m": pagina["dxf_ratio"] / pagina["unit_to_m"]})
        cands.append(escala.candidato_cotas([c for c in cotas if not c.get("override")] or cotas))
    else:
        cotas = []
        linhas = None
        cands += escala.candidatos_declarados(escala.escalas_declaradas(textos), escala.px_por_m_papel(dpi) if pagina.get("from_pdf_raster") or tipo == "pdf" else None)
    if ppm_user:
        cands.append({"fonte": "utilizador", "u_por_m": ppm_user / px_por_u})
    esc = escala.consenso([c for c in cands if c])
    u_por_m = esc["u_por_m"]
    if not u_por_m:
        return {"ok": False, "versao": VERSAO, "fonte": fonte, "escala": esc, "motivo": "escala desconhecida",
                "mensagem": esc["mensagem"], "divisoes": []}
    vetorizacao = None
    if fonte == "imagem":
        img = pagina.get("image_png_b64")
        if not img:
            return {"ok": False, "versao": VERSAO, "fonte": fonte, "escala": esc, "motivo": "imagem em falta", "divisoes": []}
        vetorizacao = raster.vetorizar(img, u_por_m, dpi=dpi)
        linhas = vetorizacao["linhas_endireitadas"]
        an = vetor.analisar(linhas, u_por_m, extensao_m=.04, tol_min=2.0)
    else:
        an = vetor.analisar(linhas, u_por_m, cotas=cotas, textos=textos)
    if an.get("ok"):
        # segunda volta da escala: áreas escritas nas divisões confirmam (ou contradizem) a escala usada
        pares = [(d["poligono"].area, a) for d in an["divisoes"] for a in d["areas_escritas_m2"][:1]]
        ca = escala.candidato_areas(pares)
        if ca:
            esc = escala.consenso([c for c in cands if c] + [ca])
        imp = an.get("implantacao")
        if imp is not None:
            x0, y0, x1, y1 = imp.bounds
            an["caixa_m"] = [(x1 - x0) / u_por_m, (y1 - y0) / u_por_m]
    cotas_m = sorted({round(c.get("value_m") or c.get("valor_m") or 0, 3) for c in cotas if (c.get("value_m") or c.get("valor_m"))})
    conf = coerencia.avaliar(an, esc, fonte, cotas_m)
    rot = (vetorizacao or {}).get("rotacao")

    def para_px(poly):
        pts = [(x * px_por_u, y * px_por_u) for x, y in list(poly.exterior.coords)[:-1]]
        if rot and abs(rot["angulo"]) > .05:
            import cv2
            M = cv2.getRotationMatrix2D(tuple(rot["centro"]), -rot["angulo"], 1.0)
            pts = [(M[0, 0] * x + M[0, 1] * y + M[0, 2], M[1, 0] * x + M[1, 1] * y + M[1, 2]) for x, y in pts]
        return [[round(x, 1), round(y, 1)] for x, y in pts]
    divisoes = []
    for i, (d, c) in enumerate(zip(an.get("divisoes", []), conf["divisoes"]), 1):
        nome = d["nomes"][0] if d["nomes"] else f"Divisão {i}"
        divisoes.append({"id": f"D{i:02d}", "nome": nome, "nome_lido": bool(d["nomes"]),
                         "area_m2": round(d["area_m2"], 3), "perimetro_m": round(d["perimetro_m"], 3),
                         "area_escrita_m2": d["areas_escritas_m2"][0] if d["areas_escritas_m2"] else None,
                         "poligono_px": para_px(d["poligono"]), **c})
    paredes = {k: (round(v, 3) if isinstance(v, float) else v) for k, v in (an.get("paredes") or {}).items()}
    return {"ok": bool(an.get("ok")), "versao": VERSAO, "fonte": fonte, "motivo": an.get("motivo"),
            "escala": esc, "px_por_m": round(u_por_m * px_por_u, 6), "divisoes": divisoes,
            "area_util_m2": round(sum(d["area_m2"] for d in divisoes), 3),
            "area_implantacao_m2": round(an["area_implantacao_m2"], 3) if an.get("area_implantacao_m2") else None,
            "implantacao_px": para_px(an["implantacao"]) if an.get("implantacao") is not None and an["implantacao"].geom_type == "Polygon" else None,
            "paredes": paredes, "vaos": an.get("vaos"), "verificacoes": conf["verificacoes"],
            "confianca": {"resumo": conf["resumo"], "nivel_global": conf["nivel_global"]},
            "estatisticas": {**(an.get("estatisticas") or {}), "segundos": round(time.time() - t0, 2),
                             "angulo_endireitamento_graus": (vetorizacao or {}).get("angulo_graus")},
            "avisos": an.get("avisos", [])}
