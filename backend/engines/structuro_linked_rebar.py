"""Bind RC checks to current gravity results. No independent forces are accepted.

Simply supported beams and uniform one-way slab strips only. Each selected
combination is checked separately; maxima never create an invented load case.
"""
from __future__ import annotations

from typing import Literal
from pydantic import Field, model_validator
from engines.structuro_rebar import Strict, Text, Positive, Materials, Section, section_design, UNRESOLVED

VERSION = "linked-rc-0.3.0"


class LinkedSection(Strict):
    id: Text
    element_id: Text
    case_ids: list[Text] = Field(min_length=1, max_length=12)
    kind: Literal["beam", "slab_strip"]
    # Distance from tension face to steel centroid, not nominal cover.
    tension_centroid_from_face_mm: Positive
    materials: Materials
    as_provided_mm2: Positive | None = None
    cot_theta: float = Field(ge=1, le=2.5)
    uniform_across_width: bool = False
    source: Text

    @model_validator(mode="after")
    def unique_cases(self):
        if len(set(self.case_ids)) != len(self.case_ids):
            raise ValueError("Combinaison liée en double")
        return self


def inspect_links(model):
    issues = []
    elements = {e.id: e for e in model.elements}
    combinations = {c.id for c in model.combinations}
    def issue(link, text): issues.append({"element": link.element_id, "message": f"{link.id} : {text}"})
    ids = set()
    manual_ids = {s.id for s in model.reinforcement.sections} if model.reinforcement else set()
    for link in model.linked_sections:
        if link.id in ids or link.id in manual_ids:
            issue(link, "repère d'aciers dupliqué entre sections liées ou indépendantes.")
        ids.add(link.id)
        e = elements.get(link.element_id)
        if e is None or e.kind != "beam":
            issue(link, "lier une poutre isostatique du modèle, ou une dalle représentée par une poutre équivalente.")
            continue
        if any(case not in combinations for case in link.case_ids):
            issue(link, "chaque cas doit être une combinaison explicite du modèle ; actions isolées exclues.")
        if e.height_m is None or link.tension_centroid_from_face_mm >= e.height_m*1000:
            issue(link, "centre des aciers hors de la hauteur de section.")
        if link.kind == "slab_strip":
            if not link.uniform_across_width:
                issue(link, "la répartition uniforme dans la largeur doit être justifiée explicitement.")
            if any(l.mode == "point" for l in e.loads) or any(
                s.target == e.id and s.receiving == "point" for incoming in model.elements for s in incoming.supports):
                issue(link, "une charge ponctuelle ne peut pas être divisée automatiquement par la largeur de dalle.")
    return issues


def calculate_links(model, gravity_result):
    out = {"engine_version": VERSION, "input_hash": gravity_result["input_hash"],
           "status": "blocked" if gravity_result["status"] == "blocked" else "partial",
           "execution_ready": False, "sections": [], "unresolved": UNRESOLVED,
           "scope": "Flexion positive de travées simplement appuyées ; aucune continuité ni armature sur appui déduite."}
    if out["status"] == "blocked":
        out["issues"] = gravity_result["issues"]
        return out
    by_case = {c["id"]: {e["id"]: e for e in c["elements"]} for c in gravity_result["cases"]}
    elements = {e.id: e for e in model.elements}
    for link in model.linked_sections:
        e = elements[link.element_id]
        divisor = e.width_m if link.kind == "slab_strip" else 1.0
        rows = []
        for case in link.case_ids:
            force = by_case[case][e.id]
            s = Section(id=link.id, kind=link.kind,
                b_mm=1000.0 if link.kind == "slab_strip" else e.width_m*1000,
                h_mm=e.height_m*1000, d_mm=e.height_m*1000-link.tension_centroid_from_face_mm,
                med_knm=force["moment_max_knm"]/divisor, ved_kn=force["shear_max_kn"]/divisor,
                materials=link.materials, as_provided_mm2=link.as_provided_mm2,
                cot_theta=link.cot_theta, source=link.source, case=case)
            rows.append({"case_id": case, "section_input": s.model_dump(), "result": section_design(s)})
        complete = [r for r in rows if "as_required_mm2" in r["result"]]
        status = "out_of_scope" if len(complete) != len(rows) else (
            "fails_check" if any(r["result"]["status"] == "fails_check" for r in rows) else "partial")
        # Do not display a misleading envelope when one selected case could not be checked.
        governing = max(complete, key=lambda r: r["result"]["as_required_mm2"]) if len(complete) == len(rows) else None
        out["sections"].append({"id": link.id, "element_id": e.id, "kind": link.kind,
            "status": status, "execution_ready": False, "input_hash": gravity_result["input_hash"],
            "force_divisor": divisor, "force_basis": "Par mètre de largeur" if link.kind == "slab_strip" else "Section entière",
            "span_m": e.length_m, "source": link.source, "cases": rows,
            "governing_flexure_case": governing["case_id"] if governing else None,
            "as_required_envelope_mm2": governing["result"]["as_required_mm2"] if governing else None})
    if any(s["status"] in ("out_of_scope", "fails_check") for s in out["sections"]):
        out["status"] = "has_unresolved_checks"
    return out
