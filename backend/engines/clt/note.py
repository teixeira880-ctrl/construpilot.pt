"""Execução do motor CLT para o Assistente BTP (ferramenta `calcul_clt` de engines.calc_lots.outils).

Entradas aceites (por esta ordem):
  • `_plan`  — planta já lida no ConstruPilot (injetada pela ponte a partir de `plan_id`) → geometria real das divisões;
  • `modelo_json` — projeto CLT completo (formato de engines.clt.defaults);
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


def projeto(a: dict) -> dict:
    op = {k: a[k] for k in ("inclinacao", "beiral", "cobertura") if a.get(k) is not None}
    if a.get("inclinacao_graus"):
        op["inclinacao"] = a["inclinacao_graus"]
    produto = a.get("produto") or "generico_c24"
    if a.get("_plan"):
        p = adapter.from_takeoff(a["_plan"], a.get("_levels"), (a.get("pais") or "pt").lower(), op, produto)
    elif a.get("modelo_json"):
        p = json.loads(a["modelo_json"])
        b = defaults.base(p.get("country", "PT"), p.get("produto") or produto)
        for k, v in b.items():
            p.setdefault(k, v)
    else:
        p = adapter.retangulo({**a, "produto": produto})
    if a.get("parede_exterior"):
        p["tiposParede"]["EXT"]["painel"] = a["parede_exterior"]
    if a.get("parede_interior"):
        p["tiposParede"]["INT"]["painel"] = a["parede_interior"]
    if a.get("so_clt"):
        p["soClt"] = True
    if a.get("titulo"):
        p["nome"] = a["titulo"]
    return p


def note(a: dict) -> dict:
    lang = (a.get("lingua") or "pt").lower()
    p = projeto(a)
    res = calcular(p)
    lin = Q.linhas(res, lang)
    tot = Q.precificar(lin, a.get("_biblioteca"), p.get("precos"))
    br = a.get("_branding")
    renders = list(a.get("_renders") or [])
    if not renders and a.get("render", True):
        try:
            from .render import render
            renders = render(res, largura=1600, altura=900, spp=64, vistas=[("estrutura", (-0.62, -0.78), 0.55)], orcamento_s=180)
        except Exception:  # noqa: BLE001 — sem Mitsuba: dossier sem render
            renders = []
    titulo = p.get("nome") or t("titulo", lang)
    aviso = None if a.get("_biblioteca") else ("Sem biblioteca de preços da empresa: nenhuma linha tem preço inventado — "
                                               "as linhas sem preço ficam « a orçamentar ».")
    doc = P.dossier(res, lin, tot, lang, br, renders, titulo, aviso)
    from engines.bet_core.brand import from_branding
    b = from_branding(br, res.get("country", "PT"))
    xl = xlsx(res, lin, tot, lang, b.hex, b.name if b.is_client else None, titulo, aviso)
    vw = html_viewer(res, titulo, lang, "#" + b.hex, b.name if b.is_client else None)
    e = res["estudo"]
    leitura = p.get("leitura") or {}
    txt = [f"Estudo CLT «{titulo}»: {e['nPaineis']} painéis, {num(e['m3Liq'], 2)} m³ líquidos, {num(e['m3Prensa'], 2)} m³ de prensa "
           f"(perda {num(e['desperdicio'] * 100, 1)} %), {num(e['kg'] / 1000, 1)} t, {num(e['nParafusos'], 0)} parafusos/pregos e "
           f"{num(e['nConectores'], 0)} conectores contados painel a painel."]
    txt.append("Composições: " + "; ".join(f"{x['painel']} {x['n']} painéis / {x['volLiq']:.2f} m³ líq. / {x['volPrensa']:.2f} m³ prensa"
                                           for x in res["paineisResumo"]))
    txt.append(f"Vãos recortados: {len(res['vaos'])} ({num(e['m2Vaos'], 1)} m², {num(e['m3Vaos'], 2)} m³ de CLT retirados por CNC).")
    if leitura.get("pisos"):
        txt.append("Leitura da planta: " + "; ".join(f"{x['nivel']}: {x['divisoes']} divisões, {x['paredes_interiores']} paredes interiores, "
                                                     f"{x['vaos_exteriores'] + x['vaos_interiores']} vãos" for x in leitura["pisos"]))
    txt.append(f"Total com preço {tot['total']:.2f} € — {tot['linhas_sem_preco']} de {tot['linhas']} linhas a orçamentar."
               if tot["total"] else f"Sem preços na biblioteca da empresa: {tot['linhas']} linhas de quantidades a orçamentar.")
    txt += [f"Hipótese: {h}" for h in (res.get("hipoteses") or [])[:8]]
    txt += [f"A VERIFICAR: {x}" for x in (res.get("avisos") or [])[:10]]
    txt.append("Ficheiros: dossier PDF (nota, mapa, lista de painéis, plantas, alçados de fabrico numerados, lajes, cobertura, plano de prensa), "
               "Excel e visualizador 3D.")
    png = renders[0][1] if renders else _preview_png(doc)
    return {"titre": f"Estudo CLT — {titulo}", "resume": "\n".join(txt), "pdf": doc, "png": png,
            "data": {"m3_liquido": round(e["m3Liq"], 3), "m3_prensa": round(e["m3Prensa"], 3), "paineis": e["nPaineis"], "parafusos": e["nParafusos"],
                     "conectores": e["nConectores"], "total_eur": tot["total"], "linhas_sem_preco": tot["linhas_sem_preco"],
                     "avisos": len(res.get("avisos") or [])},
            "files_extra": [("Mapa-quantidades-CLT", f"Mapa de quantidades CLT — {titulo}", xl, "xlsx"),
                            ("Visualizador-3D-CLT", f"Visualizador 3D CLT — {titulo}", vw, "html")]}


def _preview_png(pdf: bytes) -> bytes:
    import pymupdf
    d = pymupdf.open(stream=pdf, filetype="pdf")
    return d[0].get_pixmap(dpi=80).tobytes("png")
