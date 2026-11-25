"""Planta lida no ConstruPilot → projeto CLT, com a MESMA leitura de geometria do motor LSF (engines.lsf.adapter):
contorno real de cada piso a partir das divisões, paredes interiores, vãos associados às paredes, zonas de laje e
cobertura. Só mudam as espessuras (painéis CLT) e a composição das lajes, escolhida pela esbelteza dos vãos reais."""
from __future__ import annotations

from engines.lsf import adapter as LA

from . import defaults

AdapterError = LA.AdapterError


def _converter(lp: dict, country: str, produto: str, t_piso: float) -> dict:
    p = defaults.base(country, produto)
    p["nome"] = (lp.get("nome") or "Projeto").replace("LSF", "CLT")
    hip = [h for h in lp.get("hipoteses") or [] if "LSF" not in h and "asnas" not in h.lower()]
    hip.insert(0, "Geometria lida na planta: faces interiores = divisões calibradas; os painéis CLT são postos para fora e o isolamento "
                  "por fora dos painéis — áreas úteis das divisões preservadas")
    p["hipoteses"] = hip
    p["leitura"] = lp.get("leitura")
    p["perimetros"] = [dict(x, apoio="betao" if k == 0 else "laje") for k, x in enumerate(lp["perimetros"])]
    p["paredes"] = [dict(x) for x in lp["paredes"]]
    for f in lp["pisos"]:
        p["pisos"].append({k: f[k] for k in ("id", "grupo", "x0", "y0", "x1", "y1", "z", "vao")} | {"cobertura": bool(f.get("cobertura"))})
    for c in lp["coberturas"]:
        p["coberturas"].append({k: c[k] for k in ("id", "x0", "y0", "x1", "y1", "z", "cumeeira", "inclinacao", "beiral")})
    return p


def _acertar_lajes(p: dict) -> None:
    """Composição de cada laje pelos vãos reais; a cota superior de cada piso mantém-se (as paredes de baixo ajustam a altura)."""
    from .engine import Ctx, _prep_lajes
    ctx = Ctx(p)
    _prep_lajes(ctx)
    t_ref = p.pop("_t_ref")
    por_z: dict[float, list] = {}
    for f, g in zip(p["pisos"], ctx.lajes):
        f["painel"] = g["painel"]
        por_z.setdefault(round(f["z"]), []).append((f, g))
    for z_old, lst in por_z.items():
        pis = [g["esp"] for f, g in lst if not f.get("cobertura")] or [g["esp"] for f, g in lst]
        delta = max(pis) - t_ref                # paredes de baixo à face inferior da laje mais espessa desse nível
        if abs(delta) < 0.5:
            continue
        for f, g in lst:
            f["z"] = f["z"] - delta
        for w in p["perimetros"] + p["paredes"]:
            if isinstance(w.get("z0"), (int, float)) and abs(w["z0"] + w["altura"] - z_old) < 5:
                w["altura"] = w["altura"] - delta
    p["hipoteses"].append("Lajes CLT escolhidas pela esbelteza dos vãos lidos na planta (" +
                          ", ".join(sorted({f"{g['grupo']}: {g['painel']}" for g in ctx.lajes})) + ") — verificação EN 1995-1-1 a fazer")


def from_levels(levels, country: str = "PT", nome: str | None = None, opcoes: dict | None = None, produto: str = "generico_c24") -> dict:
    o = dict(opcoes or {})
    base = defaults.base(country, produto)
    T = base["tiposParede"]["EXT"]
    t_ext = base["paineis"][T["painel"]]["esp"]
    t_ref = base["paineis"]["CLT200-5s"]["esp"]
    o.update(dtExt_mm=t_ext, espInt_mm=0.0, profPiso_mm=t_ref, vaoMaxPiso=o.get("vaoMaxPiso", 7000))
    lp = LA.from_levels(levels, country, nome, o)
    p = _converter(lp, country, produto, t_ref)
    p["_t_ref"] = t_ref
    _acertar_lajes(p)
    return p


def from_mep_input(data: dict, nome: str | None = None, opcoes: dict | None = None, produto: str = "generico_c24") -> dict:
    from engines.mep.model import build
    levels, _ = build(data)
    if not any(lv.rooms for lv in levels):
        raise AdapterError("Nenhuma divisão utilizável (são necessárias divisões fechadas e calibradas).")
    return from_levels(levels, (data.get("country") or "pt").upper(), nome or (data.get("project") or {}).get("name"), opcoes, produto)


def from_takeoff(plan: dict, levels: list[dict] | None = None, country: str = "pt", opcoes: dict | None = None, produto: str = "generico_c24") -> dict:
    from engines.mep.adapter import AdapterError as MepErr
    from engines.mep.adapter import from_takeoff as mep_ft
    try:
        data = mep_ft(plan, levels, country, {})
    except MepErr as exc:
        raise AdapterError(str(exc)) from exc
    return from_mep_input(data, plan.get("filename"), opcoes, produto)


def retangulo(a: dict) -> dict:
    """Implantação retangular simples (sem planta): comprimento × largura, pisos, vãos por fachada."""
    imp = a.get("implantacao") or {}
    L, W = float(imp.get("comprimento_m") or 0), float(imp.get("largura_m") or 0)
    if L <= 0 or W <= 0:
        raise ValueError("Indique a planta (plan_id), o modelo CLT (modelo_json) ou a implantação (comprimento_m e largura_m).")
    n = int(imp.get("pisos") or 1)
    pd = [float(x) for x in (imp.get("pe_direito_m") or [])] or [2.7] * n
    p = defaults.base((a.get("pais") or "PT").upper(), a.get("produto") or "generico_c24")
    p["nome"] = a.get("titulo") or f"Moradia CLT {L:g} × {W:g} m".replace(".", ",")
    pts = [[0, 0], [L * 1000, 0], [L * 1000, W * 1000], [0, W * 1000]]
    fach = {"frente": "0", "direita": "1", "tras": "2", "esquerda": "3"}
    from .engine import Ctx, _prep_lajes
    vy = W <= L
    z = 0.0
    for k in range(n):
        h = pd[min(k, len(pd) - 1)] * 1000
        per = {"id": f"N{k}", "nivel": "R/C" if k == 0 else f"{k}.º andar", "tipo": "EXT", "z0": z, "altura": h, "pontos": pts, "vaos": {},
               "apoio": "betao" if k == 0 else "laje"}
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
        zt = z + h
        ultimo = k + 1 == n
        if ultimo and (a.get("cobertura") or "") != "plana":
            p["coberturas"].append({"id": "COB", "x0": 0, "y0": 0, "x1": L * 1000, "y1": W * 1000, "z": zt, "cumeeira": "x" if L >= W else "y",
                                    "inclinacao": float(a.get("inclinacao_graus") or 30), "beiral": float(a.get("beiral_mm") or 500)})
            break
        gid = "COBP" if ultimo else f"PISO{k + 1}"
        f = {"id": gid, "grupo": gid, "nivel": "Cobertura" if ultimo else f"{k + 1}.º andar", "vao": "y" if vy else "x", "z": zt,
             "x0": 0, "y0": 0, "x1": L * 1000, "y1": W * 1000, "cobertura": ultimo}
        ctx = Ctx({**p, "pisos": [f]})
        _prep_lajes(ctx)
        f["painel"] = ctx.lajes[0]["painel"]
        p["pisos"].append(f)
        z = zt + ctx.lajes[0]["esp"]
    p["hipoteses"].append("Implantação retangular indicada no pedido (sem planta): paredes interiores não modeladas")
    return p
