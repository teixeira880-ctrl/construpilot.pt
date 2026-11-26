"""Visualizador 3D autónomo da construção tradicional — mesmo visualizador que o CLT (three.js empacotado, sem internet):
cada elemento (sapata, pilar, viga, laje, parede com vãos e pilares recortados, cobertura) extrudido com a geometria calculada."""
from __future__ import annotations

import html
import json

from engines.clt.viewer import TEMPLATE
from engines.lsf.i18n import num
from engines.lsf.viewer import _r

COR = {"sapata": 0x9aa3ab, "viga_fundacao": 0x9aa3ab, "pilar": 0x7d8a96, "viga": 0x8796a3, "laje": 0xb9bfc4, "alvenaria": 0xc9805a, "empena": 0xc9805a,
       "cobertura": 0xa3423a}
TIPO = {"sapata": "laje", "viga_fundacao": "laje", "pilar": "vigas", "viga": "vigas", "laje": "laje", "alvenaria": "parede", "empena": "empena", "cobertura": "cobertura"}


def html_viewer(res: dict, titulo: str | None = None, accent: str = "#203B2D", empresa: str | None = None) -> bytes:
    pn = []
    for it in res["itens"]:
        pn.append({"id": it["id"], "tipo": TIPO[it["tipo"]], "tipoNome": it["tipo"].replace("_", " "), "painel": it.get("info") or "", "esp": it["esp"],
                   "camadasTxt": "", "L": it["contorno"][1][0], "H": max(p[1] for p in it["contorno"]), "volLiq": 0, "kg": 0, "nota": it.get("info"),
                   "o": _r(it["o"]), "u": _r(it["u"], 6), "v": _r(it["v"], 6), "w": _r(it["w"], 6), "cor": COR[it["tipo"]],
                   "contorno": _r([list(map(float, x)) for x in it["contorno"]]),
                   "recortes": [{k: _r(float(r[k])) for k in ("x0", "x1", "z0", "z1")} for r in it.get("recortes") or []]})
    d = {"paineis": pn, "vigas": [], "accent": accent, "locale": "pt-PT", "txt": {"semCorte": "sem corte"}}
    e = res["estudo"]
    kpi = f"{num(e['m3Betao'], 1)} m³ betão · {num(e['kgAco'], 0)} kg aço · {num(e['unidadesAlvenaria'], 0)} unidades de alvenaria"
    page = TEMPLATE.read_text(encoding="utf-8")
    rep = {"__LANG__": "pt", "__TITLE__": html.escape(titulo or res.get("nome") or "Construção tradicional"),
           "__SUB__": html.escape((empresa + " · " if empresa else "") + "Visualizador 3D — cada elemento calculado com a geometria real; toque num elemento para ver o ID"),
           "__KPI__": html.escape(kpi), "__T_CAMADAS__": "Camadas e vistas", "__T_ESTRUTURA__": "Alvenarias", "__T_PISO__": "Lajes e fundações",
           "__T_COB__": "Cobertura", "__T_CORTE__": "Corte horizontal", "__T_FRENTE__": "Frente", "__T_LADO__": "Lado", "__T_TOPO__": "Topo", "__T_VIGAS__": "Pilares e vigas"}
    for k, v in rep.items():
        page = page.replace(k, v)
    page = page.replace("/*CLT_DATA*/null", json.dumps(d, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/"), 1)
    return page.encode("utf-8")
