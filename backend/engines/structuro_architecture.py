"""Explicit PC constraints, separate from mechanical resistance.

No plan recognition or automatic code minimum: every available band, depth and
headroom criterion must be sourced. Passing listed checks is never a global visa.
"""
import math
from typing import Literal
from pydantic import Field, model_validator
from engines.structuro_rebar import Strict, Text, Positive, Nonnegative

VERSION = "architecture-0.4.0"


class Clearance(Strict):
    id: Text
    element_id: Text
    label: Text
    pc_clearance_m: Positive
    integrated_depth_m: Nonnegative
    additional_loss_m: Nonnegative = 0.0
    minimum_clearance_m: Positive
    source: Text
    criterion_source: Text


class FitBand(Strict):
    id: Text
    element_id: Text
    label: Text
    axis: Literal["x", "y"]
    minimum_m: float = Field(ge=-1e6, le=1e6)
    maximum_m: float = Field(ge=-1e6, le=1e6)
    # A beam check measures its transverse section, not its complete footprint.
    mode: Literal["beam_width", "column_footprint"]
    source: Text

    @model_validator(mode="after")
    def ordered(self):
        if self.minimum_m >= self.maximum_m:
            raise ValueError("A faixa disponível deve ter uma largura positiva")
        return self


class ArchitecturalStudy(Strict):
    clearances: list[Clearance] = Field(default_factory=list, max_length=100)
    fit_bands: list[FitBand] = Field(default_factory=list, max_length=100)
    unresolved: list[Text] = Field(default_factory=list, max_length=40)

    @model_validator(mode="after")
    def ids(self):
        rows = [*self.clearances, *self.fit_bands]
        if len({r.id for r in rows}) != len(rows):
            raise ValueError("Marca de controlo de arquitetura duplicada")
        return self


def calculate_architecture(model, input_hash):
    study = model.architecture
    out = dict(engine_version=VERSION, input_hash=input_hash, execution_ready=False,
               architectural_layout_accepted=False, status="not_checked", checks=[], issues=[],
               unresolved=list(study.unresolved),
               scope="Apenas restrições explicitamente introduzidas. Nem deteção automática dos conflitos, nem validação do projeto, nem cálculo de apoio local.")
    elements = {e.id: e for e in model.elements}
    for c in study.clearances:
        e = elements.get(c.element_id)
        if e is None or e.kind != "beam" or e.height_m is None:
            out["issues"].append(f'{c.id} : viga e altura conhecidas obrigatórias.')
            continue
        drop = max(0., e.height_m-c.integrated_depth_m)
        free = c.pc_clearance_m-drop-c.additional_loss_m
        margin = free-c.minimum_clearance_m
        out["checks"].append(dict(id=c.id, element_id=e.id, label=c.label, kind="clearance",
            source=c.source, criterion_source=c.criterion_source, status="pass" if margin >= -1e-9 else "conflict",
            beam_height_m=e.height_m, downstand_m=drop, remaining_clearance_m=free,
            required_clearance_m=c.minimum_clearance_m, margin_m=margin,
            summary=f'Altura livre {free:.3f} m ; alvo introduzido {c.minimum_clearance_m:.3f} m ; altura abaixo da laje {drop:.3f} m.'))
    for c in study.fit_bands:
        e = elements.get(c.element_id)
        if e is None or any(getattr(e, k) is None for k in ("x_m", "y_m", "length_m", "width_m")):
            out["issues"].append(f'{c.id} : implantação e dimensões conhecidas obrigatórias.')
            continue
        a = math.radians(e.angle_deg); co, si = math.cos(a), math.sin(a)
        if c.mode == "beam_width":
            # Only a band parallel to the transverse width is meaningful here.
            if e.kind != "beam" or (abs(co) > 1e-9 if c.axis == "x" else abs(si) > 1e-9):
                out["issues"].append(f'{c.id} : faixa transversal alinhada com uma viga obrigatória.')
                continue
            points = [(e.x_m, e.y_m), (e.x_m-e.width_m*si, e.y_m+e.width_m*co)]
        else:
            if e.kind != "column":
                out["issues"].append(f'{c.id} : implantação de pilar obrigatória.')
                continue
            points = [(e.x_m+x*co-y*si, e.y_m+x*si+y*co)
                      for x,y in ((0,0),(e.length_m,0),(e.length_m,e.width_m),(0,e.width_m))]
        index = 0 if c.axis == "x" else 1
        lo, hi = min(p[index] for p in points), max(p[index] for p in points)
        before, after = max(0., c.minimum_m-lo), max(0., hi-c.maximum_m)
        out["checks"].append(dict(id=c.id, element_id=e.id, label=c.label, kind="fit_band",
            source=c.source, status="pass" if max(before,after) <= 1e-9 else "conflict",
            axis=c.axis, element_minimum_m=lo, element_maximum_m=hi,
            band_minimum_m=c.minimum_m, band_maximum_m=c.maximum_m,
            centre_offset_m=(lo+hi-c.minimum_m-c.maximum_m)/2,
            protrusion_before_m=before, protrusion_after_m=after,
            summary=f'Emprise [{lo:.3f} ; {hi:.3f}] m ; faixa [{c.minimum_m:.3f} ; {c.maximum_m:.3f}] m ; saliências {before * 100:.1f}/{after * 100:.1f} cm.'))
    if out["issues"]:
        out["status"] = "incomplete"
    elif any(c["status"] == "conflict" for c in out["checks"]):
        out["status"] = "conflicts"
    elif out["checks"]:
        out["status"] = "listed_checks_only"
    return out
