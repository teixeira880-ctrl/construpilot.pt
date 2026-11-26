"""Execução do motor de construção tradicional para o Assistente BTP (ferramenta `calcul_tradicional`).
Entradas, por esta ordem: `_plan` (planta lida), `modelo_json` (projeto completo), `implantacao` (retângulo sem planta)."""
from __future__ import annotations

import json

from engines.lsf.i18n import num
from engines.lsf.quantities import precificar

from . import adapter, defaults
from . import pdf as P
from .engine import calcular
from .quantities import linhas
from .viewer import html_viewer
from .xlsx import xlsx


def projeto(a: dict) -> dict:
    op = {k: a[k] for k in ("inclinacao", "beiral", "cobertura") if a.get(k) is not None}
    if a.get("inclinacao_graus"):
        op["inclinacao"] = a["inclinacao_graus"]
    if a.get("_plan"):
        p = adapter.from_takeoff(a["_plan"], a.get("_levels"), (a.get("pais") or "pt").lower(), op)
    elif a.get("modelo_json"):
        p = json.loads(a["modelo_json"])
        for k, v in defaults.base(p.get("country", "PT")).items():
            p.setdefault(k, v)
    else:
        p = adapter.retangulo(a)
    if a.get("q_adm_kpa"):
        p["regras"]["q_adm_kpa"] = float(a["q_adm_kpa"])
        p["hipoteses"] = [h for h in p["hipoteses"] if "Tensão admissível" not in h]
    for k, tipo in (("alvenaria_exterior", "EXT"), ("alvenaria_interior", "INT")):
        if a.get(k):
            p["tiposParede"][tipo]["unidade"] = a[k]
    if a.get("titulo"):
        p["nome"] = a["titulo"]
    return p


def note(a: dict) -> dict:
    p = projeto(a)
    res = calcular(p)
    lin = linhas(res)
    tot = precificar(lin, a.get("_biblioteca"), p.get("precos"))
    renders = list(a.get("_renders") or [])
    if not renders and a.get("render", True):
        try:
            from .render import render
            renders = render(res, largura=1600, altura=900, spp=64, vistas=[("estrutura", (-0.62, -0.78), 0.55)], orcamento_s=180)
        except Exception:  # noqa: BLE001
            renders = []
    titulo = p.get("nome") or "Construção tradicional"
    aviso = None if a.get("_biblioteca") else "Sem biblioteca de preços da empresa: nenhuma linha tem preço inventado — as linhas sem preço ficam « a orçamentar »."
    doc = P.dossier(res, lin, tot, a.get("_branding"), renders, titulo, aviso)
    from engines.bet_core.brand import from_branding
    b = from_branding(a.get("_branding"), res.get("country", "PT"))
    xl = xlsx(res, lin, tot, b.hex, b.name if b.is_client else None, titulo, aviso)
    vw = html_viewer(res, titulo, "#" + b.hex, b.name if b.is_client else None)
    e = res["estudo"]
    txt = [f"Estudo de construção tradicional «{titulo}»: {num(e['m3Betao'], 2)} m³ de betão armado, {num(e['kgAco'], 0)} kg de aço (varões e malhas "
           f"calculados elemento a elemento), {num(e['m2Alvenaria'], 1)} m² de alvenaria ({num(e['unidadesAlvenaria'], 0)} unidades contadas fiada a fiada), "
           f"{e['nPilares']} pilares, {e['nVigas']} vigas, {e['nSapatas']} sapatas, {num(e['escavacao'], 1)} m³ de escavação."]
    txt.append("Por piso: " + "; ".join(sorted({l["cat"].split(" ", 1)[1].split(" — ")[0] for l in lin})))
    txt.append(f"Total com preço {tot['total']:.2f} € — {tot['linhas_sem_preco']} de {tot['linhas']} linhas a orçamentar." if tot["total"]
               else f"Sem preços na biblioteca da empresa: {tot['linhas']} linhas de quantidades a orçamentar.")
    txt += [f"Hipótese: {h}" for h in (res.get("hipoteses") or [])[:8]]
    txt += [f"A VERIFICAR: {x}" for x in (res.get("avisos") or [])[:10]]
    txt.append("Ficheiros: dossier PDF (síntese, mapa por piso, quadro de armaduras, planta de fundações, plantas estruturais, alçado de cada parede), "
               "Excel e visualizador 3D.")
    png = renders[0][1] if renders else _preview(doc)
    return {"titre": f"Construção tradicional — {titulo}", "resume": "\n".join(txt), "pdf": doc, "png": png,
            "data": {"m3_betao": round(e["m3Betao"], 3), "kg_aco": round(e["kgAco"], 1), "unidades_alvenaria": e["unidadesAlvenaria"],
                     "m2_alvenaria": round(e["m2Alvenaria"], 2), "total_eur": tot["total"], "linhas_sem_preco": tot["linhas_sem_preco"]},
            "files_extra": [("Mapa-quantidades-tradicional", f"Mapa de quantidades — {titulo}", xl, "xlsx"),
                            ("Visualizador-3D-tradicional", f"Visualizador 3D — {titulo}", vw, "html")]}


def _preview(pdf: bytes) -> bytes:
    import pymupdf
    return pymupdf.open(stream=pdf, filetype="pdf")[0].get_pixmap(dpi=80).tobytes("png")
