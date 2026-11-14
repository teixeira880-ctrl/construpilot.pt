"""Visualizador 3D autónomo (um único ficheiro HTML, sem internet): three.js empacotado + dados do estudo.
Cada perfil é extrudido a partir da sua secção real (C/U com espessura), nas coordenadas calculadas pelo motor."""
from __future__ import annotations

import html
import json
from pathlib import Path

from .i18n import num, t

TEMPLATE = Path(__file__).with_name("assets") / "viewer_template.html"


def _r(v, d=1):
    if isinstance(v, float):
        return round(v, d)
    if isinstance(v, list):
        return [_r(x, d) for x in v]
    if isinstance(v, dict):
        return {k: _r(x, d) for k, x in v.items()}
    return v


def dados(res: dict) -> dict:
    """Subconjunto compacto do resultado para o visualizador."""
    mem = [{"id": m["id"], "tipoPeca": t(m["tipoPeca"], res.get("lang", "pt")), "perfilNome": m["perfilNome"], "L": m["L"], "kg": round(m["kg"], 3),
            "nota": m.get("nota"), "o": _r(m["o"]), "u": _r(m["u"], 5), "v": _r(m["v"], 5), "w": _r(m["w"], 5), "sec": m["sec"], "bbox": _r(m["bbox"])}
           for m in res["membros"]]
    pl = [{"placa": p["placa"], "grupo": p["grupo"], "nome": p["nome"], "ref": p["ref"], "face": p["face"], "cell": _r(p["cell"]),
           "pecas": _r(p["pecas"]), "parafusos": p.get("parafusos", 0), "plano": _r(p["plano"], 5)} for p in res["placas"]]
    return {"membros": mem, "placas": pl}


def html_viewer(res: dict, titulo: str | None = None, lang: str = "pt", accent: str = "#203B2D", empresa: str | None = None) -> bytes:
    res = {**res, "lang": lang}
    d = dados(res)
    d["accent"] = accent
    d["locale"] = {"pt": "pt-PT", "fr": "fr-FR", "en": "en-GB", "uk": "uk-UA"}.get(lang, "pt-PT")
    d["txt"] = {"semCorte": t("semCorte", lang)}
    e = res["estudo"]
    kpi = f"{num(e['kgAco'] / 1000, 2, lang)} t · {e['nMembros']} {t('pecas', lang).lower()} · {num(e['nParafusos'], 0, lang)} {t('parafusos', lang).lower()}"
    tit = titulo or res.get("nome") or t("titulo", lang)
    sub = (empresa + " · " if empresa else "") + t("viewer_sub", lang)
    page = TEMPLATE.read_text(encoding="utf-8")
    rep = {"__LANG__": lang, "__TITLE__": html.escape(tit), "__SUB__": html.escape(sub), "__KPI__": html.escape(kpi),
           "__T_CAMADAS__": t("camadas", lang), "__T_ESTRUTURA__": t("estrutura", lang), "__T_GESSO__": t("gesso", lang),
           "__T_PISO__": t("piso", lang), "__T_COB__": t("cob", lang), "__T_CORTE__": t("corte", lang), "__T_FRENTE__": t("frente", lang),
           "__T_LADO__": t("lado", lang), "__T_TOPO__": t("topo", lang)}
    for k, v in rep.items():
        page = page.replace(k, v)
    js = json.dumps(d, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    page = page.replace("/*LSF_DATA*/null", js, 1)
    return page.encode("utf-8")
