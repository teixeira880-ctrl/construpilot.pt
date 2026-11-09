from __future__ import annotations
from typing import Annotated, Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator

Positive = Annotated[float, Field(gt=0, strict=True, allow_inf_nan=False)]
Nonnegative = Annotated[float, Field(ge=0, strict=True, allow_inf_nan=False)]
Finite = Annotated[float, Field(strict=True, allow_inf_nan=False)]
Text = Annotated[str, Field(min_length=1, max_length=2000)]

class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False, str_strip_whitespace=True)

class Basis(Strict):
    reference: Text
    revision: Text
    declared_by: Text
    # A declaration in input, never a certificate issued by this software.
    confirmed: bool = False

class Site(Strict):
    country: Literal["UA"] = "UA"
    region: str | None = None
    locality: str | None = None
    latitude: Annotated[float, Field(ge=-90, le=90)] | None = None
    longitude: Annotated[float, Field(ge=-180, le=180)] | None = None
    altitude_m: Finite | None = None
    thermal_zone: Literal["I", "II"] | None = None
    # Location-specific design data, with units; no built-in city fallback.
    winter_design_c: Finite | None = None
    snow_ground_kpa: Nonnegative | None = None
    wind_reference_kpa: Nonnegative | None = None
    seismic_basis: str | None = None
    basis: Basis | None = None

class Panel(Strict):
    id: Text
    product: Text
    layup_id: Text
    bending_axis: Literal["longitudinal", "transverse"]
    application: Literal["floor", "roof"]
    support_model: Literal["one_way_simply_supported_udl"]
    span_m: Positive
    strip_width_m: Positive
    thickness_m: Positive
    density_kn_m3: Positive
    # Both stiffnesses for the FULL analysed strip, in the span direction.
    # GA includes the shear correction / rolling-shear contribution.
    ei_eff_kn_m2: Positive
    ga_eff_kn: Positive
    moment_resistance_knm: Positive
    shear_resistance_kn: Positive
    permanent_superimposed_kpa: Nonnegative
    variable_kpa: Nonnegative
    gamma_g: Positive
    gamma_q: Positive
    creep_factor: Nonnegative
    quasi_permanent_factor: Annotated[float, Field(ge=0, le=1)]
    deflection_limit_mm: Positive
    product_basis: Basis
    action_basis: Basis

class Layer(Strict):
    name: Text
    thickness_m: Positive
    conductivity_w_mk: Positive
    source: Text

class LinearBridge(Strict):
    name: Text
    length_m: Nonnegative
    psi_w_mk: Finite  # negative psi is possible with an explicit reference convention
    source: Text

class PointBridge(Strict):
    name: Text
    count: Annotated[int, Field(ge=0)]
    chi_w_k: Finite
    source: Text

class Assembly(Strict):
    id: Text
    category: Literal["wall", "roof", "floor_over_unheated"]
    area_m2: Positive
    layers: list[Layer] = Field(min_length=1)
    rsi_m2k_w: Nonnegative
    rse_m2k_w: Nonnegative
    linear_bridges: list[LinearBridge]
    point_bridges: list[PointBridge]
    bridges_reviewed: bool = False
    required_effective_r_m2k_w: Positive | None = None
    basis: Basis

class Study(Strict):
    schema_version: Literal["clt-ua-1"] = "clt-ua-1"
    name: Text
    target_system: Literal["CLT"] = "CLT"
    source_address: str | None = None
    site: Site
    panels: list[Panel] = Field(default_factory=list, max_length=300)
    assemblies: list[Assembly] = Field(default_factory=list, max_length=300)
    unresolved: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def unique_ids(self):
        for items in (self.panels, self.assemblies):
            ids = [i.id for i in items]
            if len(ids) != len(set(ids)):
                raise ValueError("Duplicate element identifiers")
        return self
