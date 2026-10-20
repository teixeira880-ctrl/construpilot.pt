"""Deterministic RC sub-calculations, never an execution approval.

Restricted first-generation EC2 stress block (fck <= 50 MPa), no axial force,
rectangular sections, no redistribution. Inputs are already combined design
actions. Soil checks reproduce an explicitly supplied geotechnical report.
Units: geometry mm (except footing m), stress MPa, force kN, moment kNm.
Reference: JRC EUR 26566 EN (2014), chapters 3 and 4; see docs/structure-aciers.md.
"""
from __future__ import annotations

import hashlib
import json
import math
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

VERSION = "rc-sections-0.2.0"
Positive = Annotated[float, Field(gt=0, le=1e7)]
Nonnegative = Annotated[float, Field(ge=0, le=1e7)]
Text = Annotated[str, Field(min_length=1, max_length=1800, pattern=r"\S")]


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, allow_inf_nan=False)


class Materials(Strict):
    fck_mpa: float = Field(ge=12, le=50)
    fyk_mpa: float = Field(ge=400, le=600)
    fctm_mpa: Positive
    gamma_c: float = Field(ge=1, le=2)
    gamma_s: float = Field(ge=1, le=2)
    alpha_cc: float = Field(gt=0, le=1)
    source: Text


class Section(Strict):
    id: Text
    kind: Literal["beam", "slab_strip"]
    b_mm: Positive
    h_mm: Positive
    d_mm: Positive
    med_knm: float = Field(ge=-1e6, le=1e6)
    ved_kn: Nonnegative
    ned_kn: float = Field(default=0, ge=-1e6, le=1e6)
    torsion_knm: float = Field(default=0, ge=-1e6, le=1e6)
    materials: Materials
    as_provided_mm2: Positive | None = None
    cot_theta: float = Field(ge=1, le=2.5)
    source: Text
    # Independent section forces, not automatically linked to a gravity result.
    case: Text

    @model_validator(mode="after")
    def geometry(self):
        if self.d_mm >= self.h_mm:
            raise ValueError("La hauteur utile d doit être inférieure à h")
        if self.kind == "slab_strip" and self.b_mm != 1000:
            raise ValueError("Une bande de dalle est calculée sur exactement 1 m")
        return self


class Footing(Strict):
    id: Text
    width_m: Positive
    wall_width_m: Positive
    h_m: Positive
    d_m: Positive
    n_els_characteristic_kn_m: Nonnegative
    n_els_quasi_permanent_kn_m: Nonnegative
    n_elu_kn_m: Nonnegative
    # Total forces already include the foundation weight; never added again.
    q_els_limit_kpa: Positive
    q_elu_limit_kpa: Positive
    min_width_m: Positive
    horizontal_kn_m: float = Field(ge=-1e6, le=1e6)
    moment_knm_m: float = Field(ge=-1e6, le=1e6)
    centred_level_base: bool
    report_conditions_confirmed: bool
    # Used for force-to-steel conversion only, not a complete material check.
    fyk_mpa: float = Field(ge=400, le=600)
    gamma_s: float = Field(ge=1, le=2)
    source: Text

    @model_validator(mode="after")
    def geometry(self):
        if self.wall_width_m >= self.width_m or self.d_m >= self.h_m:
            raise ValueError("Géométrie de semelle incohérente")
        return self


class Bar(Strict):
    mark: Text
    diameter_mm: float = Field(ge=4, le=40)
    count: int = Field(ge=1, le=100000)
    developed_length_m: Positive
    description: Text


class Schedule(Strict):
    id: Text
    basis: Text
    source: Text
    steel_density_kg_m3: float = Field(ge=7000, le=8500)
    source_total_kg: Positive | None = None
    bars: list[Bar] = Field(min_length=1, max_length=200)

    @model_validator(mode="after")
    def unique_marks(self):
        if len({b.mark for b in self.bars}) != len(self.bars):
            raise ValueError("Repère d'armature dupliqué dans la nomenclature")
        return self


class Evidence(Strict):
    filename: Text
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    pages: int = Field(ge=1, le=10000)
    revision: Text


class ReinforcementStudy(Strict):
    basis: Literal["source_replay", "design_draft"]
    sources: list[Evidence] = Field(default_factory=list, max_length=60)
    observations: list[Text] = Field(default_factory=list, max_length=40)
    sections: list[Section] = Field(default_factory=list, max_length=100)
    footings: list[Footing] = Field(default_factory=list, max_length=100)
    schedules: list[Schedule] = Field(default_factory=list, max_length=100)

    @model_validator(mode="after")
    def ids(self):
        for rows in (self.sections, self.footings, self.schedules):
            if len({r.id for r in rows}) != len(rows):
                raise ValueError("Repère dupliqué")
        return self


UNRESOLVED = [
    "Combinaisons, enveloppes et modèle porteur global à justifier séparément.",
    "ELS : fissuration et flèche différée non vérifiées par ce module.",
    "Ancrages, recouvrements, arrêts de barres, congestion et enrobages non dimensionnés.",
    "Poteaux, interaction N-M, second ordre, voiles, torsion et poinçonnement non dimensionnés.",
    "Stabilité, vent, séisme, feu, soutènements et phases provisoires à justifier.",
    "Qualification indépendante du moteur et validation de l'ingénieur structure requises avant EXE.",
]


def section_design(s: Section) -> dict:
    result = {"id": s.id, "case": s.case, "status": "partial", "execution_ready": False,
              "source": s.source, "issues": [], "checks": {}}
    if s.ned_kn != 0 or s.torsion_knm != 0:
        return {**result, "status": "out_of_scope", "issues": ["Effort normal ou torsion : flexion simple inapplicable."]}
    m = s.materials
    b, d = s.b_mm, s.d_mm
    fcd, fyd = m.alpha_cc*m.fck_mpa/m.gamma_c, m.fyk_mpa/m.gamma_s
    mu = abs(s.med_knm)*1e6/(b*d*d*fcd)
    # x/d <= .45 is a conservative domain gate, not an assertion about ductility.
    mu_limit = .8*.45*(1-.4*.45)
    result.update(fcd_mpa=fcd, fyd_mpa=fyd, mu=mu, mu_limit=mu_limit,
                  tension_face="top" if s.med_knm < 0 else "bottom")
    if mu > mu_limit:
        return {**result, "status": "out_of_scope", "issues": ["x/d > 0,45 : section doublement armée ou autre modèle requis."]}
    # Stable root of M=0.8*b*x*fcd*(d-0.4*x).
    x = (2*mu/(.8*(1+math.sqrt(1-2*mu))))*d
    z = d-.4*x
    as_flex = abs(s.med_knm)*1e6/(z*fyd)
    as_min = max(.26*m.fctm_mpa/m.fyk_mpa, .0013)*b*d
    required = max(as_flex, as_min)
    result.update(x_mm=x, z_mm=z, as_flexure_mm2=as_flex, as_min_mm2=as_min,
                  as_required_mm2=required, as_max_mm2=.04*b*s.h_mm,
                  as_provided_mm2=s.as_provided_mm2)
    if s.as_provided_mm2 is not None:
        result["checks"]["area_at_least_required"] = s.as_provided_mm2 >= required
        result["checks"]["area_below_four_percent"] = s.as_provided_mm2 <= .04*b*s.h_mm
        # More steel can leave the assumed yielded-steel stress-block domain.
        xp = s.as_provided_mm2*fyd/(.8*b*fcd)
        result["checks"]["provided_section_in_domain"] = xp/d <= .45
        result["mrd_provided_knm"] = s.as_provided_mm2*fyd*(d-.4*xp)/1e6 if xp/d <= .45 else None
        k = min(1+math.sqrt(200/d), 2)
        rho = min(s.as_provided_mm2/(b*d), .02)
        vrdc = max(.18/m.gamma_c*k*(100*rho*m.fck_mpa)**(1/3),
                   .035*k**1.5*math.sqrt(m.fck_mpa))*b*d/1000
        result["vrdc_kn"] = vrdc
        if s.kind == "slab_strip":
            result["checks"]["shear_without_links"] = s.ved_kn <= vrdc
            if s.ved_kn > vrdc:
                result["issues"].append("Bande de dalle : résistance sans armatures de cisaillement dépassée.")
    else:
        result["issues"].append("Aciers disposés manquants : VRd,c et section réellement armée non vérifiés.")
    if s.kind == "beam":
        zs = min(.9*d, z)
        nu = .6*(1-m.fck_mpa/250)
        vmax = b*zs*nu*fcd/(s.cot_theta+1/s.cot_theta)/1000
        asw = s.ved_kn*1e6/(zs*fyd*s.cot_theta)  # mm²/m
        asw_min = .08*math.sqrt(m.fck_mpa)/m.fyk_mpa*b*1000
        result.update(asw_required_mm2_m=max(asw, asw_min), asw_min_mm2_m=asw_min,
                      vrdmax_kn=vmax, stirrup_spacing_max_mm=.75*d,
                      shift_length_mm=.5*zs*s.cot_theta)
        result["checks"]["strut_crushing"] = s.ved_kn <= vmax
        result["issues"].append("Asw/s calculé ; branches, espacement transversal et décalage des aciers longitudinaux à détailler.")
    if any(v is False for v in result["checks"].values()):
        result["status"] = "fails_check"
    result["formulas"] = ["fcd=alpha_cc*fck/gamma_c; fyd=fyk/gamma_s",
        "M=0.8*b*x*fcd*(d-0.4*x); As=M/(z*fyd)",
        "As,min=max(0.26*fctm/fyk,0.0013)*b*d"]
    return result


def footing_check(s: Footing) -> dict:
    out = {"id": s.id, "source": s.source, "status": "partial", "execution_ready": False,
           "issues": [], "checks": {}}
    if not s.centred_level_base or s.horizontal_kn_m != 0 or s.moment_knm_m != 0:
        return {**out, "status": "out_of_scope", "issues": ["Charge excentrée, inclinée ou base non horizontale : modèle de semelle centrée inapplicable."]}
    checks = {"width": s.width_m >= s.min_width_m}
    pressures = {}
    for key, n, limit in [("ELS_caracteristique", s.n_els_characteristic_kn_m, s.q_els_limit_kpa),
                          ("ELS_quasi_permanent", s.n_els_quasi_permanent_kn_m, s.q_els_limit_kpa),
                          ("ELU_fondamental", s.n_elu_kn_m, s.q_elu_limit_kpa)]:
        q = n/s.width_m
        pressures[key] = {"n_kn_m": n, "q_kpa": q, "limit_kpa": limit, "utilisation": q/limit}
        checks[key] = q <= limit
    # JRC 4.2.1.1 / EC2 9.8.2.2: maximum tie force per metre of strip.
    # Gross upward pressure is retained: no favourable self-weight deduction.
    x = s.width_m/2-.35*s.wall_width_m
    z = .9*s.d_m
    force = pressures["ELU_fondamental"]["q_kpa"]*x*x/(2*z)
    out.update(pressures=pressures, checks=checks, tie_force_kn_m=force,
               as_tie_only_mm2_m=force*1000/(s.fyk_mpa/s.gamma_s), z_m=z,
               pressure_basis="Pression brute conservée, sans déduction favorable du poids propre.",
               formula="x=B/2-0.35*a; z=0.9*d; Fs,max=q*x²/(2*z); As=Fs/fyd")
    out["issues"] += ["Aciers de tirant dus aux efforts seulement : minima constructifs, cisaillement, compression des bielles et ancrage non vérifiés.",
                       "Les charges sont celles du rapport, pas une nouvelle descente de charges."]
    if not s.report_conditions_confirmed:
        out["issues"].append("Horizon d'assise, profondeur, voisinage et hypothèses du G2 à confirmer ; comparaison de pressions conditionnelle.")
    if any(v is False for v in checks.values()):
        out["status"] = "fails_check"
    return out


def schedule_quantities(s: Schedule) -> dict:
    bars = []
    for b in s.bars:
        area = math.pi*b.diameter_mm**2/4
        unit_mass = area*1e-6*s.steel_density_kg_m3
        length = b.count*b.developed_length_m
        bars.append({**b.model_dump(), "area_one_bar_mm2": area,
                     "unit_mass_kg_m": unit_mass, "total_length_m": length, "mass_kg": length*unit_mass})
    total = sum(b["mass_kg"] for b in bars)
    return {"id": s.id, "basis": s.basis, "source": s.source, "bars": bars,
            "total_kg": total, "source_total_kg": s.source_total_kg,
            "delta_kg": total-s.source_total_kg if s.source_total_kg is not None else None,
            "note": "Longueurs développées saisies, crochets inclus si présents dans la source. Hors chutes. Aucun nouveau façonnage généré."}


def calculate_reinforcement(study: ReinforcementStudy | None) -> dict | None:
    if study is None:
        return None
    raw = json.dumps({"engine": VERSION, "input": study.model_dump()}, sort_keys=True, allow_nan=False)
    return {"engine_version": VERSION, "input_hash": hashlib.sha256(raw.encode()).hexdigest(),
            "execution_ready": False, "status": "partial", "basis": study.basis,
            "sections": [section_design(s) for s in study.sections],
            "footings": [footing_check(s) for s in study.footings],
            "schedules": [schedule_quantities(s) for s in study.schedules],
            "unresolved": UNRESOLVED}
