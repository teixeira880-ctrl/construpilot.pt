"""Banco de ensaio da geometria: lê cada planta de referência pelo MESMO caminho que a produção (importação DXF / PDF /
imagem → `servico.analisar_pagina`) e compara com a verdade exata (`*.geo.json`, gerada por scripts/geometria_referencia.py).

Métricas por planta e por fonte:
  - divisões: encontradas, emparelhadas com a verdade (área a ≤ 10 %), recall a 2 % e a 1 %, erro médio e máximo (%);
  - implantação, paredes exteriores (eixo) e divisórias: erro (%);
  - portas e janelas: contagem exata.
Uso: python -m engines.geometria.banco  (imprime o quadro; --json para a saída completa)
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

PASTA = Path(__file__).resolve().parents[2] / "tests/fixtures/geometria"


def _pagina_imagem(caminho: Path, dpi: float, escala_den: int) -> dict:
    import base64
    return {"image_png_b64": base64.b64encode(caminho.read_bytes()).decode("ascii"), "dpi": dpi,
            "text_blocks": [{"text": f"ESCALA 1:{escala_den}", "x": 0, "y": 0, "w": 0, "h": 0}]}


def _emparelhar(lidas: list[float], verdade: list[float]):
    """Emparelhamento guloso pela menor diferença relativa; um par só conta abaixo de 10 %."""
    pares, livres = [], list(enumerate(lidas))
    for v in sorted(verdade, reverse=True):
        if not livres:
            pares.append((v, None))
            continue
        j, a = min(livres, key=lambda t: abs(t[1] - v) / v)
        if abs(a - v) / v <= .10:
            pares.append((v, a))
            livres.remove((j, a))
        else:
            pares.append((v, None))
    return pares, [a for _, a in livres]


def _erro(a, v):
    return None if a is None or not v else round((a - v) / v * 100, 3)


def pontuar(res: dict, verdade: dict) -> dict:
    vt = [d["area_m2"] for d in verdade["divisoes"].values()]
    lidas = [d["area_m2"] for d in res.get("divisoes", [])]
    pares, extras = _emparelhar(lidas, vt)
    erros = [abs(_erro(a, v)) for v, a in pares if a is not None]
    par = res.get("paredes") or {}
    vaos = res.get("vaos") or {}
    return {
        "ok": res.get("ok", False), "escala": (res.get("escala") or {}).get("estado"),
        "divisoes_verdade": len(vt), "divisoes_lidas": len(lidas), "emparelhadas": len(erros), "a_mais": len(extras),
        "recall_2pct": round(sum(e <= 2 for e in erros) / len(vt), 3), "recall_1pct": round(sum(e <= 1 for e in erros) / len(vt), 3),
        "erro_medio_pct": round(sum(erros) / len(erros), 3) if erros else None, "erro_max_pct": round(max(erros), 3) if erros else None,
        "implantacao_pct": _erro(res.get("area_implantacao_m2"), verdade["area_implantacao_m2"]),
        "paredes_exteriores_pct": _erro(par.get("exteriores_eixo_m"), verdade["paredes"]["exteriores_eixo_m"]),
        "divisorias_pct": _erro(par.get("interiores_m"), verdade["paredes"]["interiores_eixo_m"]),
        "portas": [vaos.get("portas"), verdade["contagens"]["porta"]], "janelas": [vaos.get("janelas"), verdade["contagens"]["janela"]],
        "confianca": (res.get("confianca") or {}).get("resumo"), "segundos": (res.get("estatisticas") or {}).get("segundos"),
    }


def correr(pasta: Path = PASTA, fontes: tuple = ("dxf", "pdf", "png", "scan", "scan300")) -> dict:
    from engines.geometria.servico import analisar_pagina
    from engines.plan_dxf import process_dxf
    from engines.plan_processor import process_upload
    rel = {}
    for gj in sorted(pasta.glob("*.geo.json")):
        v = json.loads(gj.read_text(encoding="utf-8"))
        nome = v["planta"]
        den = int(v["escala_declarada"].split(":")[1])
        for fonte in fontes:
            chave = f"{nome}/{fonte}"
            if fonte == "dxf":
                pg = process_dxf((pasta / f"{nome}.dxf").read_bytes(), f"{nome}.dxf")["pages"][0]
                res = analisar_pagina(pg, "dxf")
            elif fonte == "pdf":
                pg = process_upload((pasta / f"{nome}.pdf").read_bytes(), f"{nome}.pdf", "application/pdf")["pages"][0]
                res = analisar_pagina(pg, "pdf")
            elif fonte == "png":
                res = analisar_pagina(_pagina_imagem(pasta / f"{nome}.png", 150, den), "pdf")
            elif fonte == "scan":
                res = analisar_pagina(_pagina_imagem(pasta / f"{nome}_scan.jpg", v["imagem"]["dpi_scan"], den), "pdf")
            else:
                f = pasta / f"{nome}_scan300.jpg"
                if not f.exists():
                    continue
                res = analisar_pagina(_pagina_imagem(f, 300, den), "pdf")
            rel[chave] = pontuar(res, v)
    return rel


def quadro(rel: dict) -> str:
    cab = f"{'planta/fonte':<18}{'escala':<12}{'div':>7}{'rec2%':>7}{'erro méd':>9}{'erro máx':>9}{'impl':>7}{'p.ext':>7}{'divis':>7}{'portas':>8}{'janelas':>8}{'s':>6}"
    linhas = [cab, "-" * len(cab)]
    for k, r in rel.items():
        f = lambda x: "—" if x is None else f"{x:+.2f}"
        linhas.append(f"{k:<18}{str(r['escala']):<12}{r['emparelhadas']}/{r['divisoes_verdade']:<5}{r['recall_2pct']:>7.2f}"
                      f"{'—' if r['erro_medio_pct'] is None else round(r['erro_medio_pct'], 2):>9}{'—' if r['erro_max_pct'] is None else round(r['erro_max_pct'], 2):>9}"
                      f"{f(r['implantacao_pct']):>7}{f(r['paredes_exteriores_pct']):>7}{f(r['divisorias_pct']):>7}"
                      f"{'%s/%s' % tuple(r['portas']):>8}{'%s/%s' % tuple(r['janelas']):>8}{r['segundos'] or 0:>6}")
    return "\n".join(linhas)


if __name__ == "__main__":
    r = correr()
    print(json.dumps(r, ensure_ascii=False, indent=1) if "--json" in sys.argv else quadro(r))
