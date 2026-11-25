"""Visualizador 3D autónomo (um único ficheiro HTML, sem internet): three.js empacotado + dados do estudo CLT.
Cada painel é extrudido a partir do seu contorno real com os recortes, nas coordenadas calculadas pelo motor."""
from __future__ import annotations

import html
import json
from pathlib import Path

from engines.lsf.viewer import _r

from .i18n import num, t

TEMPLATE = Path(__file__).with_name("assets") / "viewer_template.html"


def dados(res: dict, lang: str = "pt") -> dict:
    pn = [{"id": p["id"], "tipo": p["tipo"], "tipoNome": t(p["tipo"], lang), "painel": p["painel"], "esp": p["esp"],
           "camadasTxt": "-".join(str(int(c)) for c in p["camadas"]), "L": p["L"], "H": p["H"], "volLiq": round(p["volLiq"], 4),
           "kg": round(p["kg"], 1), "nota": p.get("nota"), "o": _r(p["o"]), "u": _r(p["u"], 6), "v": _r(p["v"], 6), "w": _r(p["w"], 6),
           "contorno": _r([list(map(float, x)) for x in p["contorno"]]),
           "recortes": [{k: _r(float(r[k])) for k in ("x0", "x1", "z0", "z1")} for r in p.get("recortes") or []]} for p in res["paineis"]]
    vg = [{"nome": v["nome"], "L": v["L"], "b": v["b"], "h": v["h"], "m3": round(v["m3"], 4), "o": _r(v["o"]), "eixo": v["eixo"], "lado": v["lado"]}
          for v in res.get("vigas") or []]
    return {"paineis": pn, "vigas": vg}


def html_viewer(res: dict, titulo: str | None = None, lang: str = "pt", accent: str = "#203B2D", empresa: str | None = None) -> bytes:
    d = dados(res, lang)
    d["accent"] = accent
    d["locale"] = {"pt": "pt-PT", "fr": "fr-FR", "en": "en-GB", "uk": "uk-UA"}.get(lang, "pt-PT")
    d["txt"] = {"semCorte": t("semCorte", lang)}
    e = res["estudo"]
    kpi = f"{num(e['m3Liq'], 2, lang)} m³ · {e['nPaineis']} {t('paineis', lang).lower()} · {num(e['nParafusos'], 0, lang)} {t('parafusos', lang).lower()}"
    tit = titulo or res.get("nome") or t("titulo", lang)
    sub = (empresa + " · " if empresa else "") + t("viewer_sub", lang)
    page = TEMPLATE.read_text(encoding="utf-8")
    rep = {"__LANG__": lang, "__TITLE__": html.escape(tit), "__SUB__": html.escape(sub), "__KPI__": html.escape(kpi),
           "__T_CAMADAS__": t("camadas", lang), "__T_ESTRUTURA__": t("estrutura", lang), "__T_PISO__": t("piso", lang), "__T_COB__": t("cob", lang),
           "__T_CORTE__": t("corte", lang), "__T_FRENTE__": t("frente", lang), "__T_LADO__": t("lado", lang), "__T_TOPO__": t("topo", lang)}
    for k, v in rep.items():
        page = page.replace(k, v)
    js = json.dumps(d, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    page = page.replace("/*CLT_DATA*/null", js, 1)
    return page.encode("utf-8")
