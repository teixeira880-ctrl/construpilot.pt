"""Live trace of the Ukrainian engine (calcul_ucrania) for the calculation-tracking page (CLT Rezult account only).

Runs inside the calculation thread: uses calc_live.ev_sync, a no-op for every other account. Nothing is recomputed:
it shows the inputs, formulas, intermediate values and checks the engine actually used, with the DBN / DSTU reference.
"""
from __future__ import annotations

from engines import calc_live as CL

ev, n = CL.ev_sync, CL.num
M = "calcul_ucrania"


def inicio(p: dict, caso: str | None) -> None:
    if not CL.ativo():
        return
    ev("etapa", "1. Inputs", motor=M)
    ev("dado", "Project data used by the engine",
       valores={"stored case (geometry read from the plans)": caso or "—", "city": p.get("cidade"), "use": p.get("uso"),
                "heated area": n(p.get("area_aquecida_m2"), 1, "m²"), "heated volume": n(p.get("volume_m3"), 1, "m³"),
                "structural system": p.get("sistema"), "CLT product": p.get("produto_clt"), "fire resistance": f"REI {p.get('fogo_min')}",
                "envelope elements": len(p.get("elementos") or []), "company branding": p.get("empresa")},
       porque="The saved case is the geometry measured on the CLT Rezult «Home A» drawings; nothing is guessed from the text.")


def renders() -> None:
    if not CL.ativo():
        return
    ev("etapa", "Rendering the 3D views from the calculated structural model (same geometry as the calculation)", motor=M)


def dossier(o: dict, p: dict) -> None:
    if not CL.ativo():
        return
    r = o.get("r") or {}
    c = r.get("clima") or {}
    ev("etapa", "2. Climate data (DSTU-N B V.1.1-27:2010, DBN V.2.6-31:2021)", motor=M)
    ev("dado", f"Climate of {c.get('name') or c.get('nome')}",
       valores={"design outdoor temperature θe": n(c.get("theta_e"), 1, "°C"), "mean January temperature": n(c.get("t_jan"), 1, "°C"),
                "heating degree-days GD": n(c.get("gd"), 0, "K·day"), "temperature zone": c.get("zona"),
                "snow S0": n(c.get("s0_pa"), 0, "Pa"), "wind W0": n(c.get("w0_pa"), 0, "Pa"), "indoor temperature θi": n(r.get("ti"), 1, "°C")},
       norma="DSTU-N B V.1.1-27:2010; DBN V.2.6-31:2021 annex A; DBN V.1.2-2:2006")

    ev("etapa", "3. Thermal resistance of each envelope element", motor=M)
    for e in r.get("elementos") or []:
        cam = [k for k in e.get("camadas") or [] if k.get("lam")]
        formula = "R∑ = Rsi + Σ(d/λ) + Rse = 1/8.7 + Σ(d/λ) + 1/23" if cam else "R given directly"
        vals = {f"{k['nom']} ({n(k['ep'], 0)} mm, λ {n(k['lam'], 3)})": n(k["R"], 3, "m²K/W") for k in cam}
        vals.update({"area": n(e.get("area_m2"), 1, "m²"), "U = 1/R∑": n(e.get("U"), 3, "W/m²K")})
        ev("calculo", f"{e.get('nome')}", formula=formula, valores=vals, resultado=f"R∑ = {n(e.get('R'), 2)} m²K/W")
        for ctl in e.get("controles") or []:
            ev("verificacao", f"{e.get('nome')} — {ctl.get('exigence')}", ok=ctl.get("ok"),
               valores={"obtained": ctl.get("valeur"), "utilisation": n(ctl.get("taux"), 2) if ctl.get("taux") is not None else None},
               norma=ctl.get("ref"))

    if r.get("ht") is not None:
        ev("etapa", "4. Heat losses and heating demand", motor=M)
        ev("calculo", "Transmission loss coefficient H_T", formula="H_T = Σ(A·U·b) + ΔU_tb · A_envelope",
           valores={"thermal-bridge allowance ΔU": n(r.get("dpt"), 3, "W/m²K"), "envelope area": n(r.get("a_env"), 1, "m²")},
           resultado=n(r.get("ht"), 1, "W/K"))
        ev("calculo", "Ventilation loss coefficient H_V", formula="H_V = 0.34 · n · V · (1 − η)",
           valores={"air changes n": n(r.get("n"), 2, "h⁻¹"), "volume V": n(r.get("vol"), 1, "m³"), "heat recovery η": n(r.get("eta"), 2)},
           resultado=n(r.get("hv"), 1, "W/K"))
        dT = (r.get("ti") or 0) - (c.get("theta_e") or 0)
        ev("calculo", "Design heat load Φ", formula="Φ = (H_T + H_V) · (θi − θe)",
           valores={"H_T + H_V": n((r.get("ht") or 0) + (r.get("hv") or 0), 1, "W/K"), "θi − θe": n(dT, 1, "K")},
           resultado=n((r.get("phi_w") or 0) / 1000, 2, "kW"))
        if r.get("potencia_kw"):
            ev("decisao", f"Heat pump sized at {n(r['potencia_kw'], 2, 'kW')}", porque="Φ × 1.10 (10 % margin for start-up and losses)")
        if r.get("q_kwh") is not None:
            ev("calculo", "Annual heating demand Q", formula="Q = (H_T + H_V) · GD · 24 / 1000",
               valores={"GD": n(c.get("gd"), 0, "K·day"), "heated area": n(r.get("area"), 1, "m²")},
               resultado=f"{n(r.get('q_kwh'), 0, 'kWh/yr')} = {n(r.get('q_kwh_m2'), 1, 'kWh/m²·yr')}")

    cg = r.get("cargas") or {}
    if cg:
        ev("etapa", "5. Snow and wind loads (DBN V.1.2-2:2006)", motor=M)
        ev("calculo", "Snow load, ultimate design value Sm", formula="Sm = γfm · S0 · μ · C_alt",
           valores={"γfm": n(cg.get("gfm"), 2), "S0": n(cg.get("s0"), 0, "Pa"), "μ (roof shape)": n(cg.get("mu"), 2), "C_alt": n(cg.get("calt"), 2)},
           resultado=n(cg.get("sm_kpa"), 3, "kPa"))
        ev("calculo", "Snow load, operational value Se", formula="Se = 0.49 · S0 · μ · C_alt", resultado=n(cg.get("se_kpa"), 3, "kPa"))
        ev("calculo", "Wind load Wm", formula="Wm = γfm · W0 · C (C = 0.7)", valores={"W0": n(cg.get("w0"), 0, "Pa")},
           resultado=n(cg.get("wm_kpa"), 3, "kPa"))

    go = (o.get("go") or {}).get("verificacao") or {}
    if go.get("elementos"):
        ev("etapa", "6. Structure: every slab, wall, beam and footing checked", motor=M)
        for el in go["elementos"]:
            ctls = el.get("controles") or []
            pior = max((x for x in ctls if x.get("taux") is not None), key=lambda x: x["taux"], default=None)
            vals = {x.get("lib") or x.get("ref"): f"{x.get('valeur')}  (required {x.get('exigence')})" for x in ctls[:10]}
            ev("verificacao", f"{el.get('elemento') or el.get('tipo')} {el.get('ref') or ''} — {el.get('seccao') or ''}".strip(),
               ok=el.get("ok"), valores=vals,
               resultado=f"max. utilisation {n(el.get('taxa'), 2)}" + (f" ({pior.get('lib') or pior.get('ref')})" if pior else ""),
               taxa=el.get("taxa"))
        for a in go.get("ajustes") or []:
            ev("decisao", a, porque="Section increased automatically by the engine until every check passes.")
        for h in go.get("hipoteses") or []:
            ev("pressuposto", h)
        ev("resultado", f"Structure: {len(go['elementos'])} elements, compliant: {'yes' if go.get('conforme') else 'NO'}")

    ob = o.get("orcamento") or {}
    if ob:
        ev("etapa", "7. Cost estimate (UAH, VAT 20 %)", motor=M)
        ev("calculo", "Total with VAT", formula="total = Σ(quantity × unit price) + VAT 20 %",
           valores={"without VAT": n(ob.get("sem_pdv"), 0, "UAH"), "VAT 20 %": n(ob.get("pdv"), 0, "UAH"),
                    "exchange rate": f"1 € = {n(ob.get('cambio'), 4)} UAH ({ob.get('data')})",
                    "per m² incl. VAT": n(ob.get("por_m2_com_pdv"), 0, "UAH/m²")},
           resultado=f"{n(ob.get('com_pdv'), 0, 'UAH')} ≈ {n(ob.get('eur_com_pdv'), 0, '€')}")
    for h in r.get("hipoteses") or []:
        ev("pressuposto", h)


def pacote(extra: list, p: dict) -> None:
    if not CL.ativo():
        return
    ev("etapa", "8. Drawings and detailed estimate (UK + EN)", motor=M)
    for lab, titulo, _pdf in extra or []:
        ev("resultado", f"{lab}: {titulo}")
    if p.get("_devis_ttc"):
        ev("resultado", f"Detailed estimate total: {n(p['_devis_ttc'], 0, 'UAH')} incl. VAT 20 %",
           porque="The dossier figure covers structure, envelope and heat pump; the detailed estimate covers the whole house.")
