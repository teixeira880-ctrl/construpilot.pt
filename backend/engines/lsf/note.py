"""Execução do motor LSF para o Assistente BTP (ferramenta `calcul_lsf` de engines.calc_lots.outils).

Entradas aceites (por esta ordem):
  • `_plan`  — planta já lida no ConstruPilot (injetada pela ponte a partir de `plan_id`) → geometria real das divisões;
  • `modelo_json` — projeto LSF completo (formato de engines.lsf.defaults);
  • `implantacao` — retângulo simples (comprimento × largura, pisos, vãos por fachada) quando não há planta.
Saída: {titre, resume, pdf (dossier), png (render da estrutura ou vista 3D), data, files_extra [(rótulo, título, bytes, formato)]}.
"""
from __future__ import annotations

import json

from . import adapter, defaults
from . import pdf as P
from . import quantities as Q
from .engine import calcular
from .i18n import num, t
from .viewer import html_viewer
from .xlsx import xlsx


def _retangulo(a: dict) -> dict:
    imp = a.get("implantacao") or {}
    L, W = float(imp.get("comprimento_m") or 0), float(imp.get("largura_m") or 0)
    if L <= 0 or W <= 0:
        raise ValueError("Indique a planta (plan_id), o modelo LSF (modelo_json) ou a implantação (comprimento_m e largura_m).")
    n = int(imp.get("pisos") or 1)
    pd = [float(x) for x in (imp.get("pe_direito_m") or [])] or [2.7] * n
    p = defaults.base((a.get("pais") or "PT").upper())
    p["nome"] = a.get("titulo") or f"Moradia LSF {L:g} × {W:g} m".replace(".", ",")
    pts = [[0, 0], [L * 1000, 0], [L * 1000, W * 1000], [0, W * 1000]]
    viga = p["perfis"]["C200_15"]
    prof = viga["h"] + 2 * viga["t"] + p["placas"]["OSB22"]["esp"]
    z = 0.0
    fach = {"frente": "0", "direita": "1", "tras": "2", "esquerda": "3"}
    for k in range(n):
        h = pd[min(k, len(pd) - 1)] * 1000
        altura = h - (prof if k + 1 < n else 0) if k + 1 < n else h
        per = {"id": f"N{k}", "nivel": "R/C" if k == 0 else f"{k}.º andar", "tipo": "EXT", "z0": z, "altura": altura, "pontos": pts, "vaos": {}}
        for i, v in enumerate(a.get("vaos") or []):
            if int(v.get("piso") or 0) != k:
                continue
            lado = fach.get(v.get("fachada") or "frente", "0")
            vao = {"id": f"V{k}{i + 1}", "tipo": "porta" if v.get("tipo") == "porta" else "janela", "x": float(v["x_m"]) * 1000,
                   "largura": float(v["largura_m"]) * 1000, "altura": float(v.get("altura_m") or (2.1 if v.get("tipo") == "porta" else 1.2)) * 1000}
            if vao["tipo"] == "janela":
                vao["peitoril"] = float(v.get("peitoril_m") if v.get("peitoril_m") is not None else 0.9) * 1000
            per["vaos"].setdefault(lado, []).append(vao)
        p["perimetros"].append(per)
        if k + 1 < n:
            zf = z + altura
            vao_dir = "y" if W <= L else "x"
            vmax = 5000
            span = W if vao_dir == "y" else L
            nz = max(1, -(-int(span * 1000) // vmax))
            for j in range(nz):
                s0, s1 = span * 1000 * j / nz, span * 1000 * (j + 1) / nz
                f = {"id": f"PISO{k + 1}-{j + 1}", "grupo": f"PISO{k + 1}", "z": zf, "vao": vao_dir, "viga": "C200_15", "espacamento": 600,
                     "placa": "OSB22", "travamentoMax": 2500}
                f.update(x0=0, x1=L * 1000, y0=s0, y1=s1) if vao_dir == "y" else f.update(x0=s0, x1=s1, y0=0, y1=W * 1000)
                p["pisos"].append(f)
            if nz > 1:
                p["hipoteses"].append(f"Piso {k + 1}: vão de {span:g} m dividido em {nz} zonas — {nz - 1} linha(s) de apoio intermédia(s) a prever")
            z = zf + prof
        else:
            z = z + altura
    p["coberturas"].append({"id": "COB", "x0": 0, "y0": 0, "x1": L * 1000, "y1": W * 1000, "z": z, "cumeeira": "x" if L >= W else "y",
                            "inclinacao": float(a.get("inclinacao_graus") or 30), "beiral": float(a.get("beiral_mm") or 500), "espacamento": 600,
                            "banzo": "C90_12", "diagonal": "C90_10", "placa": "OSB12",
                            "subtelha": {"nome": "Subtelha / membrana", "larguraRolo": 1500, "comprimentoRolo": 50000, "sobreposicao": 100}})
    p["hipoteses"].append("Implantação retangular indicada no pedido (sem planta): paredes interiores não modeladas")
    return p


def projeto(a: dict) -> dict:
    op = {k: a[k] for k in ("inclinacao", "beiral", "cobertura") if a.get(k) is not None}
    if a.get("inclinacao_graus"):
        op["inclinacao"] = a["inclinacao_graus"]
    if a.get("_plan"):
        p = adapter.from_takeoff(a["_plan"], a.get("_levels"), (a.get("pais") or "pt").lower(), op)
    elif a.get("modelo_json"):
        p = json.loads(a["modelo_json"])
        base = defaults.base(p.get("country", "PT"))
        for k, v in base.items():
            p.setdefault(k, v)
    else:
        p = _retangulo(a)
    if a.get("espacamento_mm"):
        for T in p["tiposParede"].values():
            T["espacamento"] = float(a["espacamento_mm"])
    if a.get("titulo"):
        p["nome"] = a["titulo"]
    return p


def note(a: dict) -> dict:
    lang = (a.get("lingua") or "pt").lower()
    p = projeto(a)
    res = calcular(p)
    res["barraComercial"] = p.get("barraComercial", 6000)
    lin = Q.linhas(res, lang)
    tot = Q.precificar(lin, a.get("_biblioteca"), p.get("precos"))
    br = a.get("_branding")
    renders = list(a.get("_renders") or [])          # render calculado + foto fotorrealista já preparados pela ponte do Assistente
    if not renders and a.get("render", True):
        try:
            from .render import render
            renders = render(res, largura=1600, altura=900, spp=64, vistas=[("estrutura", (-0.62, -0.78), 0.55)], orcamento_s=180)
        except Exception:  # noqa: BLE001 — sem Mitsuba: dossier sem render
            renders = []
    titulo = p.get("nome") or t("titulo", lang)
    doc = P.dossier(res, lin, tot, lang, br, renders, titulo)
    from engines.bet_core.brand import from_branding
    b = from_branding(br, res.get("country", "PT"))
    xl = xlsx(res, lin, tot, lang, b.hex, b.name if b.is_client else None, titulo)
    vw = html_viewer(res, titulo, lang, "#" + b.hex, b.name if b.is_client else None)
    e = res["estudo"]
    leitura = p.get("leitura") or {}
    res_txt = [f"Estudo LSF «{titulo}»: {e['nMembros']} perfis, {num(e['kgAco'], 0)} kg de aço"
               + (f" ({num(e['kgPorM2'], 1)} kg/m² de piso)" if e.get("kgPorM2") else "") + f", {num(e['nParafusos'], 0)} parafusos contados um a um."]
    res_txt.append("Perfis: " + "; ".join(f"{x['perfil']} {x['pecas']} pç / {x['metros']:.0f} m / {x['kg']:.0f} kg" for x in res["perfis"]))
    res_txt.append("Placas (plano de corte com reaproveitamento): " + "; ".join(f"{x['nome']} {x['un']} un ({x['area']:.0f} m²)" for x in res["placasResumo"]))
    res_txt.append("Ancoragens: " + "; ".join(f"{x['nome']} {x['qtd']}" for x in res["ancoragens"]))
    if leitura.get("pisos"):
        res_txt.append("Leitura da planta: " + "; ".join(f"{x['nivel']}: {x['divisoes']} divisões, {x['paredes_interiores']} paredes interiores, "
                                                         f"{x['vaos_exteriores'] + x['vaos_interiores']} vãos" for x in leitura["pisos"]))
    res_txt.append(f"Total com preço {tot['total']:.2f} € — {tot['linhas_sem_preco']} de {tot['linhas']} linhas a orçamentar (sem preço na biblioteca da empresa)."
                   if tot["total"] else f"Sem preços na biblioteca da empresa: {tot['linhas']} linhas de quantidades a orçamentar.")
    res_txt += [f"Hipótese: {h}" for h in (res.get("hipoteses") or [])[:8]]
    res_txt += [f"A VERIFICAR: {x}" for x in (res.get("avisos") or [])[:10]]
    res_txt.append("Ficheiros: dossier PDF (nota, mapa, lista de corte, plantas e alçados de fabrico com peças numeradas), Excel e visualizador 3D.")
    png = renders[0][1] if renders else _preview_png(doc)
    return {"titre": f"Estudo LSF — {titulo}", "resume": "\n".join(res_txt), "pdf": doc, "png": png,
            "data": {"kg_aco": round(e["kgAco"], 1), "pecas": e["nMembros"], "parafusos": e["nParafusos"], "kg_m2": e.get("kgPorM2"),
                     "total_eur": tot["total"], "linhas_sem_preco": tot["linhas_sem_preco"], "avisos": len(res.get("avisos") or [])},
            "files_extra": [("Mapa-quantidades-LSF", f"Mapa de quantidades LSF — {titulo}", xl, "xlsx"),
                            ("Visualizador-3D-LSF", f"Visualizador 3D LSF — {titulo}", vw, "html")]}


def _preview_png(pdf: bytes) -> bytes:
    import pymupdf
    d = pymupdf.open(stream=pdf, filetype="pdf")
    return d[0].get_pixmap(dpi=80).tobytes("png")
