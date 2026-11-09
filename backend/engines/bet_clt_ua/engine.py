"""Deterministic mechanics and steady-state heat transfer, not UA certification.

Panel model: constant effective EI and effective GA, two simple supports,
uniform load, one bending direction. Strength inputs MUST already incorporate
the applicable product, duration/service and design safety factors. No EC5
solid-section substitution for a cross-laminated panel is performed here.
"""
from __future__ import annotations
import hashlib
import json
from . import VERSION
from .schema import Study, Panel, Assembly

NOT_CHECKED = ["global_lateral_stability", "seismic_response", "wind_uplift",
               "connections_and_hold_downs", "bearing_and_buckling", "fire_resistance",
               "floor_vibration", "openings_and_notches", "foundations_and_retaining",
               "construction_stages", "hygrothermal_condensation", "annual_energy",
               "summer_comfort", "ventilation_design"]

def panel(p: Panel) -> dict:
    g_area = p.density_kn_m3 * p.thickness_m + p.permanent_superimposed_kpa
    g, q = g_area * p.strip_width_m, p.variable_kpa * p.strip_width_m
    w_uls = p.gamma_g * g + p.gamma_q * q
    length = p.span_m
    moment, shear = w_uls * length**2 / 8, w_uls * length / 2
    def deform(w):
        bending = 5 * w * length**4 / (384 * p.ei_eff_kn_m2)
        rolling_shear = w * length**2 / (8 * p.ga_eff_kn)
        return {"bending_mm": bending * 1000, "shear_mm": rolling_shear * 1000,
                "total_mm": (bending + rolling_shear) * 1000}
    instant = deform(g + q)
    final = deform(g * (1 + p.creep_factor) + q * (1 + p.quasi_permanent_factor * p.creep_factor))
    ratios = {"bending": moment / p.moment_resistance_knm,
              "shear": shear / p.shear_resistance_kn,
              "final_deflection": final["total_mm"] / p.deflection_limit_mm}
    return {"id": p.id, "layup_id": p.layup_id, "bending_axis": p.bending_axis,
            "scope": "single_panel_uniform_gravity_load_only",
            "self_weight_kpa": p.density_kn_m3 * p.thickness_m,
            "g_line_kn_m": g, "q_line_kn_m": q, "uls_line_kn_m": w_uls,
            "moment_knm": moment, "reaction_each_support_kn": shear,
            "instant_deflection": instant, "final_deflection": final,
            "ratios": ratios, "limited_checks_passed": all(r <= 1 for r in ratios.values()),
            "basis": {"product": p.product_basis.model_dump(), "actions": p.action_basis.model_dump()}}

def assembly(a: Assembly) -> dict:
    resistances = [{"name": l.name, "r_m2k_w": l.thickness_m / l.conductivity_w_mk,
                    "source": l.source} for l in a.layers]
    r_clear = a.rsi_m2k_w + a.rse_m2k_w + sum(l["r_m2k_w"] for l in resistances)
    u_clear = 1 / r_clear
    bridges = sum(b.length_m * b.psi_w_mk for b in a.linear_bridges) + sum(b.count * b.chi_w_k for b in a.point_bridges)
    u_eff = u_clear + bridges / a.area_m2
    if u_eff <= 0:
        raise ValueError(f"{a.id}: nonpositive effective U; review bridge reference areas")
    # Missing bridge review is not equivalent to zero thermal bridges.
    effective = 1 / u_eff if a.bridges_reviewed else None
    passed = effective >= a.required_effective_r_m2k_w if effective is not None and a.required_effective_r_m2k_w is not None else None
    return {"id": a.id, "scope": "steady_state_opaque_assembly_only", "layers": resistances,
            "r_clear_m2k_w": r_clear, "u_clear_w_m2k": u_clear,
            "u_effective_w_m2k": u_eff if a.bridges_reviewed else None,
            "r_effective_m2k_w": effective, "required_r_m2k_w": a.required_effective_r_m2k_w,
            "limited_requirement_passed": passed, "basis": a.basis.model_dump()}

def run(raw: dict) -> dict:
    study = Study.model_validate(raw)
    missing, panels, assemblies = [], [], []
    site = study.site
    for field in ("region", "locality", "latitude", "longitude", "altitude_m", "thermal_zone",
                  "winter_design_c", "snow_ground_kpa", "wind_reference_kpa", "seismic_basis"):
        if getattr(site, field) is None or getattr(site, field) == "":
            missing.append("site." + field)
    if not site.basis or not site.basis.confirmed:
        missing.append("site.confirmed_basis")
    for p in study.panels:
        if not p.product_basis.confirmed or not p.action_basis.confirmed:
            missing.append(f"panels.{p.id}.confirmed_product_and_action_basis")
        else:
            panels.append(panel(p))
    for a in study.assemblies:
        if not a.basis.confirmed:
            missing.append(f"assemblies.{a.id}.confirmed_basis")
            continue
        assemblies.append(assembly(a))
        if not a.bridges_reviewed:
            missing.append(f"assemblies.{a.id}.thermal_bridges")
        if a.required_effective_r_m2k_w is None:
            missing.append(f"assemblies.{a.id}.local_requirement")
    if not study.panels:
        missing.append("panels.with_product_properties_and_design_actions")
    if not study.assemblies:
        missing.append("assemblies.with_project_layers")
    missing.extend(study.unresolved)
    failed = any(not r["limited_checks_passed"] for r in panels) or any(r["limited_requirement_passed"] is False for r in assemblies)
    payload = study.model_dump()
    digest = hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True, allow_nan=False).encode()).hexdigest()
    result = {"engine_version": VERSION, "input_sha256": digest, "country": "UA",
            "status": "LIMITED_CHECKS_FAILED" if failed else ("INPUT_REQUIRED" if missing else "PRELIMINARY_ONLY"),
            "certified": False, "execution_ready": False, "national_code_compliance": "NOT_DEMONSTRATED",
            "panels": panels, "assemblies": assemblies,
            "missing": sorted(set(missing)), "not_checked": NOT_CHECKED,
            "note": "Explicit-input calculations only. No automatic Ukrainian climate lookup, product design or whole-building approval."}
    # Finite input alone does not guarantee finite arithmetic for extreme magnitudes.
    json.dumps(result, allow_nan=False)
    return result
