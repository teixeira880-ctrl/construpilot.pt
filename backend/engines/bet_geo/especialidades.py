"""Comportamento térmico (REH, normas portuguesas), análise custo-benefício e especialidades sobre a geometria REAL.

Envolvente medida no contorno lido (paredes exteriores, paredes para espaços não úteis, cobertura, pavimento, vãos por
orientação do mapa de vãos) → pré-certificado REH (DL 101-D/2020, Portaria 138-I/2021, Despachos 6476-E/H/2021) pelo
motor calc_lots.reh. A solução construtiva e o sistema são ESCOLHIDOS por custo de ciclo de vida (20 anos) entre as que
cumprem todos os requisitos → é essa a solução usada nos desenhos, nas quantidades e no orçamento.
Especialidades (perdas EN 12831, piso radiante EN 1264, bomba de calor, eletricidade RTIEBT, águas e esgotos DR 23/95,
ventilação Portaria 138-I / NP 1037-1) pelos motores calc_lots existentes, alimentados com as divisões reais.
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass, field

from shapely.geometry import LineString
from shapely.ops import unary_union

from . import costs
from .model import Building
from .rooms import PRINCIPAL, Layout, _norm, glazing_by_orient

ELEC_EUR_KWH = 0.22
GAS_EUR_KWH = 0.12
YEARS, DISC, ESC = 20, 0.03, 0.02


# ----------------------------------------------------------------------------- envolvente
@dataclass
class Envelope:
    hsp: float                      # pé-direito livre (m)
    H: float                        # altura de parede exterior (pavimento → topo da laje)
    wall_ext: float                 # parede exterior opaca (m²)
    wall_enu: float                 # parede para espaço não útil (garagem, técnico) (m²)
    roof: float
    floor: float
    glazing: dict[str, float]
    glazing_src: str
    doors: float = 2.2
    perimeter: float = 0.0
    notes: list[str] = field(default_factory=list)

    @property
    def glazing_total(self) -> float:
        return round(sum(self.glazing.values()), 2)


def envelope(b: Building, lay: Layout, slab_h: float = 0.25) -> Envelope:
    fp = b.footprint
    H = max(2.6, b.storey_height)
    hsp = round(max(2.40, H - slab_h - 0.12), 2)
    unheated = unary_union([r.zone for r in lay.rooms if not r.heated and r.zone is not None]) if lay.rooms else None
    heated = fp.difference(unheated) if unheated is not None and not unheated.is_empty else fp
    edge = unary_union([LineString(fp.exterior.coords), *[LineString(h.coords) for h in fp.interiors]])
    bnd = unary_union([LineString(p.exterior.coords) for p in getattr(heated, "geoms", [heated])]
                      + [LineString(i.coords) for p in getattr(heated, "geoms", [heated]) for i in p.interiors])
    ext_len = bnd.intersection(edge.buffer(0.05)).length
    enu_len = max(0.0, bnd.length - ext_len)
    gl, src = glazing_by_orient(lay, b, hsp)
    gross = ext_len * H
    g_tot = sum(gl.values())
    notes = []
    if g_tot + 2.2 > 0.6 * gross:
        k = 0.6 * gross / (g_tot + 2.2)
        gl = {o: round(v * k, 2) for o, v in gl.items()}
        notes.append("vãos limitados a 60 % da fachada medida (leitura a confirmar)")
    useful = lay.useful_area or round(heated.area * 0.88, 1)
    gross_heated = heated.area
    return Envelope(hsp=hsp, H=H, wall_ext=round(max(0.2 * gross, gross - sum(gl.values()) - 2.2), 2),
                    wall_enu=round(enu_len * H, 2), roof=round(gross_heated, 2), floor=round(gross_heated, 2),
                    glazing=gl, glazing_src=src, perimeter=round(ext_len, 2), notes=notes + [f"área útil aquecida {useful:.1f} m²"])


# ----------------------------------------------------------------------------- soluções construtivas
@dataclass(frozen=True)
class Solution:
    etics: int          # mm EPS λ 0,036 nas paredes exteriores
    roof: int           # mm XPS λ 0,034 na cobertura invertida
    floor: int          # mm XPS sob o pavimento térreo
    uw: float           # caixilharia
    system: str         # "bc" | "caldeira" | "eletrico"
    g: float = 0.60     # fator solar do vidro (0,35 = controlo solar)

    @property
    def U(self) -> dict:
        return {"parede": round(1 / (0.17 + 0.52 + 0.02 + self.etics / 1000 / 0.036), 3),
                "parede_enu": round(1 / (0.26 + 0.52 + 0.04 + 0.08 / 0.036), 3),          # 80 mm na parede da garagem / técnico
                "cobertura": round(1 / (0.14 + 0.125 + 0.05 + self.roof / 1000 / 0.034), 3),
                "pavimento": round(1 / (0.17 + 0.04 + 0.075 + self.floor / 1000 / 0.034), 3),
                "envidracado": self.uw}


SYSTEMS = {
    "bc": ("Bomba de calor ar-água + piso radiante + AQS por bomba de calor", "bomba_calor", "bomba_calor"),
    "caldeira": ("Caldeira a gás de condensação + radiadores + AQS", "caldeira_gas_condensacao", "caldeira_gas_condensacao"),
    "eletrico": ("Radiadores elétricos + termoacumulador", "resistencia_eletrica", "termoacumulador"),
}
VECTOR = {"bomba_calor": "eletricidade", "caldeira_gas_condensacao": "gas_natural", "resistencia_eletrica": "eletricidade",
          "termoacumulador": "eletricidade"}


def find_concelho(docs, hypotheses: str = "") -> str | None:
    from engines.calc_lots import reh
    names = sorted({v for v in getattr(reh, "_MUN", {}) and [m for ms in reh._MUN.values() for m in ms.split(", ")]}, key=len, reverse=True)
    hay = [hypotheses or ""]
    from .rooms import doc_texts
    for _, _, t in doc_texts(docs)[:40]:
        hay += [ln for ln in t.splitlines() if re.search(r"(?i)local|concelho|freguesia|morada|implanta|obra|lugar|situa", ln)]
    for h in hay:
        n = reh._norm(h)
        for name in names:
            if len(name) > 3 and re.search(rf"\b{re.escape(reh._norm(name))}\b", n):
                return name
    return None


def reh_params(b: Building, lay: Layout, env: Envelope, sol: Solution, concelho: str | None) -> dict:
    U = sol.U
    e = [{"tipo": "parede", "area_m2": env.wall_ext, "U": U["parede"]},
         {"tipo": "cobertura", "area_m2": env.roof, "U": U["cobertura"]},
         {"tipo": "pavimento", "area_m2": env.floor, "U": U["pavimento"], "fronteira": "solo"},
         {"tipo": "porta", "area_m2": env.doors, "U": 1.8}]
    if env.wall_enu > 0.5:
        e.append({"tipo": "parede", "area_m2": env.wall_enu, "U": U["parede_enu"], "fronteira": "enu"})
    for o, a in env.glazing.items():
        if a > 0.05:
            e.append({"tipo": "envidracado", "area_m2": a, "U": U["envidracado"], "orientacao": o, "g": sol.g})
    _, ka, kq = SYSTEMS[sol.system]
    ap = lay.useful_area or round(b.footprint.area * 0.88, 1)
    p = {"tipo": "moradia", "obra": "nova", "area_util_m2": ap, "pe_direito_m": env.hsp, "pisos": b.storeys, "envolvente": e,
         "tipologia": max(1, sum(1 for r in lay.rooms if r.type == "quarto")), "aquecimento": {"tipo": ka}, "aqs": {"tipo": kq},
         "hipoteses_entrada": [f"geometria real lida nas plantas: área útil {ap:.1f} m², pé-direito {env.hsp:.2f} m, "
                               f"fachada {env.perimeter:.1f} m, vãos {env.glazing_total:.1f} m² ({env.glazing_src})"] + env.notes}
    if concelho:
        p["concelho"] = concelho
    else:
        p["nuts"] = "Grande Lisboa"
        p["hipoteses_entrada"].append("concelho não encontrado nas peças: clima da Grande Lisboa admitido — indicar o concelho")
    return p


def _energy_cost(r: dict, ap: float) -> tuple[float, float]:
    """(kWh finais/ano, €/ano) dos usos regulados."""
    from engines.calc_lots.reh import FPU
    u = r["ntc_usos"]
    va, vq = VECTOR.get(r["aquecimento"], "eletricidade"), VECTOR.get(r["aqs"], "eletricidade")
    fin = {"eletricidade": 0.0, "gas_natural": 0.0}
    fin[va] += u["aquecimento"] * ap / FPU[va]
    fin[vq] += u["aqs"] * ap / FPU[vq]
    fin["eletricidade"] += (u["arrefecimento"] + u["ventilacao"]) * ap / 2.5
    kwh = sum(fin.values())
    return kwh, fin["eletricidade"] * ELEC_EUR_KWH + fin["gas_natural"] * GAS_EUR_KWH


def _system_cost(sol: Solution, r: dict, ap: float) -> float:
    P = max(3.0, (r["Htr"] + r["Hve"]) * (20 - r["clima"]["theta_i"]) / 1000 * 1.1)
    pr = costs.PRICES
    if sol.system == "bc":
        return P * pr["bc_kw"][0] + pr["bc_instalacao"][0] + ap * pr["piso_radiante"][0] + pr["aqs_bc_200"][0]
    if sol.system == "caldeira":
        return pr["caldeira_condensacao"][0] + P * 120.0 + 1500.0           # radiadores + ramal de gás
    return P * pr["radiador_eletrico_kw"][0] + pr["termoacumulador_200"][0]


def _envelope_cost(sol: Solution, env: Envelope) -> float:
    g = env.glazing_total
    return (env.wall_ext * costs.etics_price(sol.etics) + env.roof * costs.roof_ins_price(sol.roof)
            + env.floor * costs.floor_ins_price(sol.floor) + g * (costs.window_price(sol.uw) + (40.0 if sol.g < 0.4 else 0.0))
            + env.wall_enu * 0.25 * 80)


def options(b: Building, lay: Layout, env: Envelope, concelho: str | None) -> list[dict]:
    from engines.calc_lots import reh
    ap = lay.useful_area or round(b.footprint.area * 0.88, 1)
    out = []
    for system in SYSTEMS:
        for et in (60, 80, 100, 120, 140):
            for uw, g in ((2.4, 0.75), (1.6, 0.60), (1.6, 0.35), (1.1, 0.50), (1.1, 0.35)):
                sol = Solution(etics=et, roof=et + 20, floor=max(80, et), uw=uw, system=system, g=g)
                try:
                    r = reh.calcular(reh_params(b, lay, env, sol, concelho))
                except Exception:  # noqa: BLE001
                    continue
                ok = all(c["ok"] is not False for c in r["controles"])
                inv = _envelope_cost(sol, env) + _system_cost(sol, r, ap)
                kwh, eur = _energy_cost(r, ap)
                npv = sum(eur * (1 + ESC) ** t / (1 + DISC) ** t for t in range(1, YEARS + 1))
                out.append({"sol": sol, "reh": r, "ok": ok, "invest": round(inv), "kwh": round(kwh), "eur_ano": round(eur),
                            "lcc": round(inv + npv), "classe": r["classe"], "RNt": r["RNt"]})
    return out


def choose(opts: list[dict]) -> tuple[dict, dict | None]:
    """(recomendada, mínima que cumpre) — recomendada = menor custo em 20 anos entre as que cumprem o REH."""
    good = [o for o in opts if o["ok"]] or sorted(opts, key=lambda o: o["RNt"])[:5]
    best = min(good, key=lambda o: o["lcc"])
    cheap = min(good, key=lambda o: o["invest"])
    return best, cheap


def _f(x, d=0):
    s = f"{x:,.{d}f}".replace(",", " ").replace(".", ",")
    return s


def addons(b: Building, lay: Layout, env: Envelope, best: dict, concelho: str | None) -> list[dict]:
    """Fotovoltaico (autoconsumo) e VMC de dupla fluxo sobre a solução recomendada: investimento, poupança e retorno."""
    from engines.calc_lots import reh
    ap = lay.useful_area or round(b.footprint.area * 0.88, 1)
    base = reh_params(b, lay, env, best["sol"], concelho)
    out = []
    kwp = max(2.0, min(6.0, round(ap / 60, 1)))
    for name, extra, cost in (
            (f"Fotovoltaico {kwp:g} kWp em autoconsumo".replace(".", ","), {"renovavel_tipo": "fotovoltaico", "renovavel_kwh": kwp * 1400},
             kwp * costs.PRICES["pv_kwp"][0]),
            ("VMC de dupla fluxo com recuperação (η 75 %)", {"ventilacao_mecanica": True, "recuperador_eta": 0.75},
             costs.PRICES["vmc_dupla_fluxo"][0])):
        try:
            r = reh.calcular({**base, **extra})
        except Exception:  # noqa: BLE001
            continue
        _, eur = _energy_cost(r, ap)
        save = best["eur_ano"] - eur
        if "renovavel_kwh" in extra:                       # autoconsumo (usos regulados + 2 500 kWh domésticos), excedente vendido 0,05 €/kWh
            pv = extra["renovavel_kwh"]
            own = min(0.6 * pv, best["kwh"] + 2500)
            save = own * ELEC_EUR_KWH + (pv - own) * 0.05
        out.append({"name": name, "invest": round(cost), "save": round(save), "classe": r["classe"],
                    "payback": round(cost / save, 1) if save > 1 else None})
    return out


def cost_benefit_note(opts: list[dict], best: dict, cheap: dict, env: Envelope, meta: dict, addons: list | None = None) -> bytes:
    from engines.calc_lots import graficos as G
    from engines.calc_lots import notes
    W = notes.W
    rows = []
    good = sorted([o for o in opts if o["ok"]], key=lambda o: o["lcc"])
    shown = good[:10] + [o for o in sorted(opts, key=lambda o: o["lcc"]) if not o["ok"]][:3]
    for o in shown:
        s = o["sol"]
        fail = ", ".join(c.get("lib") or c["ref"].split(" (")[0] for c in o["reh"]["controles"] if c["ok"] is False)[:60]
        rows.append([("★ " if o is best else "") + SYSTEMS[s.system][0].split(" + ")[0], f"{s.etics}/{s.roof}/{s.floor}",
                     f"{s.uw:g} · g {s.g:g}".replace(".", ","),
                     o["classe"], _f(o["invest"]), _f(o["eur_ano"]), _f(o["lcc"]), "sim" if o["ok"] else "não: " + fail])
    pay = None
    if best is not cheap and best["eur_ano"] < cheap["eur_ano"]:
        pay = (best["invest"] - cheap["invest"]) / max(1, cheap["eur_ano"] - best["eur_ano"])
    sys_rows = []
    for k, (name, _, _) in SYSTEMS.items():
        c = [o for o in good if o["sol"].system == k]
        if c:
            o = min(c, key=lambda o: o["lcc"])
            sys_rows.append((name.split(" + ")[0], o["lcc"]))
    kp = [{"label": "Solução recomendada", "value": best["classe"], "unit": "classe REH", "ok": best["ok"]},
          {"label": "Investimento (envolvente + sistema)", "value": _f(best["invest"]), "unit": "€"},
          {"label": "Energia (usos regulados)", "value": _f(best["eur_ano"]), "unit": "€/ano"},
          {"label": "Retorno vs mínimo regulamentar", "value": (_f(pay, 1) if pay else "imediato" if best is cheap else "—"), "unit": "anos" if pay else ""}]
    s = best["sol"]
    blocs = [("kpis", kp),
             ("p", f"Comparação de {len(opts)} combinações (espessura de isolamento × caixilharia × sistema) sobre a envolvente REAL lida nas "
                   f"plantas: fachada {env.perimeter:.1f} m, paredes exteriores {env.wall_ext:.0f} m², cobertura {env.roof:.0f} m², "
                   f"vãos {env.glazing_total:.0f} m². Cada combinação é calculada pelo REH; o custo de ciclo de vida soma o investimento "
                   f"e {YEARS} anos de energia (atualização {DISC * 100:.0f} %/ano, subida da energia {ESC * 100:.0f} %/ano)."),
             ("h2", "1. Solução recomendada (adotada nos desenhos, quantidades e orçamento)"),
             ("p", f"{SYSTEMS[s.system][0]}. Paredes: ETICS EPS {s.etics} mm (U = {s.U['parede']:.2f}); cobertura invertida XPS {s.roof} mm "
                   f"(U = {s.U['cobertura']:.2f}); pavimento térreo XPS {s.floor} mm (U = {s.U['pavimento']:.2f}); caixilharia Uw = {s.uw:g} W/(m².°C). "
                   f"Classe {best['classe']} (RNt {best['RNt']:.2f})."),
             ("h2", "2. Combinações comparadas"),
             ("table", ["Sistema", "Isol. mm (par/cob/pav)", "Uw · g", "Classe", "Investimento €", "Energia €/ano", f"Custo {YEARS} anos €", "Cumpre REH"],
              rows, [30 * W, 22 * W, 18 * W, 11 * W, 21 * W, 19 * W, 21 * W, 18 * W])]
    if sys_rows:
        blocs += [("chart", G.barres_h(sorted(sys_rows, key=lambda kv: kv[1]), f"Custo de ciclo de vida ({YEARS} anos) — melhor variante de cada sistema",
                                         "€", couleur=G.SERIES[0]), "Investimento + energia atualizada.")]
    if best is cheap:
        lead = (f"A solução que cumpre o REH com o menor investimento ({_f(best['invest'])} €) é também a de menor custo a {YEARS} anos: "
                f"{_f(best['eur_ano'])} €/ano de energia nos usos regulados.")
    else:
        lead = ("A solução mais barata à partida (mínimo regulamentar) custa " + _f(cheap["invest"]) + " € e gasta " + _f(cheap["eur_ano"])
                + " €/ano; a recomendada custa " + _f(best["invest"]) + " € e gasta " + _f(best["eur_ano"]) + " €/ano"
                + (f" — o acréscimo paga-se em {pay:.1f} anos.".replace(".", ",") if pay else "."))
    blocs += [("h2", "3. Leitura"), ("p", lead)]
    if addons:
        blocs += [("h2", "4. Investimentos complementares (sobre a solução recomendada)"),
                  ("table", ["Medida", "Investimento €", "Poupança €/ano", "Retorno (anos)", "Classe"],
                   [[a["name"], _f(a["invest"]), _f(a["save"]), _f(a["payback"], 1) if a["payback"] else "—", a["classe"]] for a in addons],
                   [60 * W, 26 * W, 26 * W, 24 * W, 18 * W])]
    hyp = [f"eletricidade {ELEC_EUR_KWH:.2f} €/kWh, gás natural {GAS_EUR_KWH:.2f} €/kWh (tarifas de referência 2026, a ajustar)".replace(".", ","),
           "preços de referência ConstruPilot sem IVA (ETICS, XPS, caixilharia, equipamentos) — substituídos pela biblioteca da empresa no orçamento",
           "fotovoltaico: 1 400 kWh/kWp·ano, 60 % em autoconsumo, excedente a 0,05 €/kWh",
           "consumos = necessidades REH dos usos regulados (aquecimento, arrefecimento, AQS); equipamentos domésticos não incluídos"]
    pdf, _ = notes.pdf("Análise custo-benefício — envolvente e sistemas", f"{meta.get('obra', 'Moradia')} · REH, {YEARS} anos", blocs, hyp)
    return pdf


# ----------------------------------------------------------------------------- especialidades
LOTES_TIPO = {"sala": "sala", "quarto": "quarto", "escritorio": "escritorio", "cozinha": "cozinha", "casa_de_banho": "casa_de_banho",
              "lavandaria": "lavandaria", "corredor": "corredor", "arrumos": "arrumos"}


def _quadro_pos(lay: Layout, b: Building):
    for t in ("tecnico", "garagem", "corredor", "lavandaria"):
        r = next((r for r in lay.rooms if r.type == t and r.placed), None)
        if r:
            return r.x, r.y, r.name
    c = b.footprint.representative_point()
    return c.x, c.y, "zona central"


def mep_params(b: Building, lay: Layout, env: Envelope, sol: Solution, concelho: str | None) -> dict:
    U = sol.U
    edge = unary_union([LineString(b.footprint.exterior.coords), *[LineString(h.coords) for h in b.footprint.interiors]])
    qx, qy, _ = _quadro_pos(lay, b)
    heated = [r for r in lay.rooms if r.heated and r.type in LOTES_TIPO and r.area > 0]
    tot_area = sum(r.area for r in heated) or 1
    div = []
    from .rooms import _room_of
    for r in heated:
        gl = sum(w.area for w in lay.windows if _room_of(w.room, lay.rooms) is r)
        if r.zone is not None:
            ext = r.zone.boundary.intersection(edge.buffer(0.08)).length * env.H
        else:
            ext = env.wall_ext * r.area / tot_area
        if not lay.windows:
            gl = env.glazing_total * r.area / tot_area
        paredes = [{"tipo": "parede", "area_m2": round(max(0.0, ext - gl), 2), "U": U["parede"], "lado": "exterior"},
                   {"tipo": "cobertura", "area_m2": r.area, "U": U["cobertura"], "lado": "exterior"},
                   {"tipo": "pavimento", "area_m2": r.area, "U": U["pavimento"], "lado": "solo"}]
        if gl > 0:
            paredes.append({"tipo": "envidracado", "area_m2": round(gl, 2), "U": sol.uw, "lado": "exterior"})
        d = math.hypot((r.x or qx) - qx, (r.y or qy) - qy) * 1.3 + 3
        div.append({"nome": r.name, "tipo": LOTES_TIPO[r.type], "area_m2": r.area, "pe_direito_m": env.hsp, "paredes": paredes,
                    "perimetro_m": round(r.zone.length if r.zone is not None else 4 * math.sqrt(r.area), 1),
                    "distancia_quadro_m": round(d, 1),
                    "revestimento": "ceramico" if r.type in ("casa_de_banho", "cozinha", "lavandaria") else "flutuante"})
    p = {"obra": "nova", "divisoes": div, "ventilacao": "natural", "estanquidade": "estanque",
         "emissores": "piso_radiante" if sol.system == "bc" else "radiadores",
         "gerador": "bomba_calor" if sol.system == "bc" else "caldeira",
         "equipamentos": {"placa": True, "forno": True, "maquina_lavar_roupa": True, "maquina_lavar_loica": True},
         "tipologia": max(1, sum(1 for r in lay.rooms if r.type == "quarto"))}
    if concelho:
        p["concelho"] = concelho
    else:
        p["nuts"] = "Grande Lisboa"
    return p


def ventilation_params(lay: Layout, env: Envelope) -> dict:
    tmap = {"sala": "sala", "quarto": "quarto", "escritorio": "escritorio", "cozinha": "cozinha", "casa_de_banho": "instalacao_sanitaria",
            "lavandaria": "lavandaria"}
    comp = [{"nome": r.name, "tipo": tmap[r.type], "area_m2": r.area} for r in lay.rooms if r.type in tmap and r.area > 0]
    return {"ventilacao": {"compartimentos": comp, "pe_direito_m": env.hsp}}


def run_all(b: Building, lay: Layout, docs, hypotheses: str, meta: dict, slab_h: float) -> dict:
    """Tudo o que é calculado (sem desenhos): envolvente, opções, REH da solução escolhida, especialidades, ventilação."""
    from engines.calc_lots import lotes_tecnicos, redes, reh
    concelho = find_concelho(docs, hypotheses)
    env = envelope(b, lay, slab_h)
    opts = options(b, lay, env, concelho)
    if not opts:
        raise ValueError("REH: nenhuma combinação calculável")
    best, cheap = choose(opts)
    sol = best["sol"]
    rp = reh_params(b, lay, env, sol, concelho)
    reh_note = reh.note(rp)
    out = {"concelho": concelho, "env": env, "options": opts, "best": best, "cheap": cheap, "solution": sol,
           "reh": reh_note, "reh_pdf": reh_note["pdf"], "warnings": []}
    out["addons"] = addons(b, lay, env, best, concelho)
    out["cb_pdf"] = cost_benefit_note(opts, best, cheap, env, meta, out["addons"])
    try:
        mp = mep_params(b, lay, env, sol, concelho)
        lot = lotes_tecnicos.note(mp)
        out["mep"], out["mep_pdf"] = lot, lot["pdf"]
    except Exception as exc:  # noqa: BLE001 — especialidades nunca bloqueiam o estudo
        out["warnings"].append(f"Especialidades não calculadas ({type(exc).__name__}: {str(exc)[:160]})")
    try:
        vp = ventilation_params(lay, env)
        if vp["ventilacao"]["compartimentos"]:
            v = redes.note(vp)
            out["vent"], out["vent_pdf"] = v, v["pdf"]
    except Exception as exc:  # noqa: BLE001
        out["warnings"].append(f"Ventilação não calculada ({type(exc).__name__}: {str(exc)[:160]})")
    return out
