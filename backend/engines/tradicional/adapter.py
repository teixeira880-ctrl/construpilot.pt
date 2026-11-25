"""Planta lida no ConstruPilot → projeto de construção tradicional, com a MESMA leitura de geometria que os motores LSF e CLT
(engines.lsf.adapter): contorno real de cada piso, paredes interiores, vãos, zonas de laje, cobertura. Só mudam as espessuras
(unidades de alvenaria) e a espessura das lajes (dimensionadas pelo motor; a cota superior de cada piso mantém-se)."""
from __future__ import annotations

from engines.lsf import adapter as LA

from . import defaults

AdapterError = LA.AdapterError


def from_levels(levels, country: str = "PT", nome: str | None = None, opcoes: dict | None = None) -> dict:
    b = defaults.base(country)
    t_ext = b["unidades"][b["tiposParede"]["EXT"]["unidade"]]["t"]
    o = dict(opcoes or {})
    o.update(dtExt_mm=t_ext, espInt_mm=15.0, profPiso_mm=180.0, vaoMaxPiso=o.get("vaoMaxPiso", 6000))
    lp = LA.from_levels(levels, country, nome, o)
    p = b
    p["nome"] = (lp.get("nome") or "Projeto").replace("LSF", "").strip() or "Projeto"
    p["hipoteses"] = ["Geometria lida na planta: faces interiores = divisões calibradas; alvenarias exteriores postas para fora e ETICS por fora — "
                      "áreas úteis das divisões preservadas"] + [h for h in lp.get("hipoteses") or [] if "LSF" not in h and "asnas" not in h.lower()]
    p["hipoteses"].append(f"Tensão admissível do terreno {b['regras']['q_adm_kpa']} kPa sem estudo geotécnico — HIPÓTESE a confirmar")
    p["leitura"] = lp.get("leitura")
    p["perimetros"] = [dict(x) for x in lp["perimetros"]]
    p["paredes"] = [dict(x) for x in lp["paredes"]]
    p["pisos"] = [{k: f[k] for k in ("id", "grupo", "x0", "y0", "x1", "y1", "z", "vao")} | {"cobertura": bool(f.get("cobertura"))} for f in lp["pisos"]]
    p["coberturas"] = [{k: c[k] for k in ("id", "x0", "y0", "x1", "y1", "z", "cumeeira", "inclinacao", "beiral")} for c in lp["coberturas"]]
    return p


def from_mep_input(data: dict, nome: str | None = None, opcoes: dict | None = None) -> dict:
    from engines.mep.model import build
    levels, _ = build(data)
    if not any(lv.rooms for lv in levels):
        raise AdapterError("Nenhuma divisão utilizável (são necessárias divisões fechadas e calibradas).")
    return from_levels(levels, (data.get("country") or "pt").upper(), nome or (data.get("project") or {}).get("name"), opcoes)


def from_takeoff(plan: dict, levels: list[dict] | None = None, country: str = "pt", opcoes: dict | None = None) -> dict:
    from engines.mep.adapter import AdapterError as MepErr
    from engines.mep.adapter import from_takeoff as mep_ft
    try:
        data = mep_ft(plan, levels, country, {})
    except MepErr as exc:
        raise AdapterError(str(exc)) from exc
    return from_mep_input(data, plan.get("filename"), opcoes)


def retangulo(a: dict) -> dict:
    """Implantação retangular (sem planta): mesma geometria que os motores LSF / CLT."""
    from engines.clt import adapter as CA
    c = CA.retangulo({**a, "produto": "generico_c24"})
    p = defaults.base((a.get("pais") or "PT").upper())
    p["nome"] = (a.get("titulo") or c["nome"]).replace("CLT", "").replace("  ", " ")
    p["perimetros"] = [dict(x) for x in c["perimetros"]]
    for x in p["perimetros"]:
        x.pop("apoio", None)
    p["pisos"] = [{k: f[k] for k in ("id", "grupo", "x0", "y0", "x1", "y1", "z", "vao")} | {"cobertura": bool(f.get("cobertura"))} for f in c["pisos"]]
    p["coberturas"] = [dict(x) for x in c["coberturas"]]
    p["hipoteses"] = list(c["hipoteses"]) + [f"Tensão admissível do terreno {p['regras']['q_adm_kpa']} kPa sem estudo geotécnico — HIPÓTESE a confirmar"]
    return p
