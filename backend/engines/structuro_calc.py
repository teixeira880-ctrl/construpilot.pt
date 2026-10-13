"""Auditable gravity-load mechanics. Not an Eurocode resistance/design engine.

Units: m, kN, kN/m, kN/m², kN.m² for EI. Positive loads act downwards.
Only simply supported, constant-EI beams and explicitly distributed axial paths.
No section, soil strength, code factor or reinforcement is inferred by this module.
"""
from __future__ import annotations

import hashlib
import json
import math
from collections import deque
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator, model_serializer
from engines.structuro_rebar import ReinforcementStudy, calculate_reinforcement
from engines.structuro_drawings import DrawingStudy
from engines.structuro_automation import AutomationSettings
from engines.structuro_linked_rebar import LinkedSection, inspect_links, calculate_links, VERSION as LINKED_VERSION
from engines.structuro_architecture import ArchitecturalStudy, calculate_architecture, VERSION as ARCHITECTURE_VERSION

VERSION = "gravity-0.1.0"
IDENT = Annotated[str, Field(pattern=r"^[A-Za-z][A-Za-z0-9_-]{0,59}$")]
POS = Annotated[float, Field(gt=0, le=1e6, allow_inf_nan=False)]
NONNEG = Annotated[float, Field(ge=0, le=1e6, allow_inf_nan=False)]
COORD = Annotated[float, Field(ge=-1e6, le=1e6, allow_inf_nan=False)]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False, strict=True)


class Source(StrictModel):
    document: str = Field(default="", max_length=160)
    page: int | None = Field(default=None, ge=1, le=10000)
    note: str = Field(default="", max_length=1200)


class Action(StrictModel):
    id: IDENT
    kind: Literal["G", "Q"]
    label: str = Field(max_length=120)


class Load(StrictModel):
    action: IDENT
    value: NONNEG
    mode: Literal["surface", "line", "point"]
    position_m: NONNEG | None = None
    source: Source


class Support(StrictModel):
    target: IDENT
    # Non-beams use explicit tributary fractions; beams use left/right reactions.
    fraction: Annotated[float, Field(gt=0, le=1)] | None = None
    receiving: Literal["axial", "uniform", "point"] = "axial"
    position_m: NONNEG | None = None
    # Forme de la charge répartie reçue par une poutre (dalle portant dans 2 sens) :
    # triangle (bord court, rampe = L/2) ou trapèze symétrique (bord long, rampe = lx/2).
    # Absent = charge uniforme (comportement historique).
    shape: Literal["triangle", "trapezoid"] | None = None
    ramp_m: POS | None = None

    @model_serializer(mode="wrap")
    def drop_unused_shape(self, handler):
        data = handler(self)
        # Empreintes historiques inchangées quand la forme n'est pas utilisée.
        if self.shape is None:
            data.pop("shape", None)
        if self.ramp_m is None:
            data.pop("ramp_m", None)
        return data


class Element(StrictModel):
    id: IDENT
    kind: Literal["slab", "beam", "wall", "column", "footing"]
    level: str = Field(default="À préciser", max_length=60)
    material: str = Field(default="À préciser", max_length=80)
    # Rectangle footprint: length local x, width local y, height vertical.
    length_m: POS | None = None
    width_m: POS | None = None
    height_m: POS | None = None
    x_m: COORD | None = None
    y_m: COORD | None = None
    angle_deg: Annotated[float, Field(ge=-360, le=360)] = 0
    density_kn_m3: NONNEG | None = None
    ei_kn_m2: POS | None = None
    source: Source = Field(default_factory=Source)
    mechanics_source: Source = Field(default_factory=Source)
    reviewed: bool = False
    loads: list[Load] = Field(default_factory=list, max_length=30)
    supports: list[Support] = Field(default_factory=list, max_length=20)


class Combination(StrictModel):
    id: IDENT
    label: str = Field(max_length=120)
    factors: dict[IDENT, Annotated[float, Field(ge=0, le=10)]]
    source: Source


class Model(StrictModel):
    title: str = Field(default="Étude de structure", max_length=160)
    country: Literal["FR", "PT"] = "PT"
    actions: list[Action] = Field(default_factory=list, max_length=8)
    self_weight_action: IDENT | None = None
    elements: list[Element] = Field(default_factory=list, max_length=200)
    combinations: list[Combination] = Field(default_factory=list, max_length=12)
    assumptions: list[Annotated[str, Field(max_length=600)]] = Field(default_factory=list, max_length=30)
    # Explicit consent to the mechanical idealisation, not engineering approval.
    gravity_model_reviewed: bool = False
    reinforcement: ReinforcementStudy | None = None
    drawings: DrawingStudy | None = None
    automation_settings: AutomationSettings | None = None
    automation_generated_hash: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    linked_sections: list[LinkedSection] = Field(default_factory=list, max_length=100)
    architecture: ArchitecturalStudy | None = None

    @model_serializer(mode="wrap")
    def preserve_legacy_serialization(self, handler):
        data = handler(self)
        # Preserve historical inputs/fingerprints when these features are unused.
        if not self.linked_sections:
            data.pop("linked_sections", None)
        if self.architecture is None:
            data.pop("architecture", None)
        if self.drawings is None:
            data.pop("drawings", None)
        if self.automation_settings is None:
            data.pop("automation_settings", None)
        if self.automation_generated_hash is None:
            data.pop("automation_generated_hash", None)
        if self.reinforcement is None:
            data.pop("reinforcement", None)
        return data

    @model_validator(mode="after")
    def unique_identifiers(self):
        for rows in (self.actions, self.elements, self.combinations):
            if len({x.id for x in rows}) != len(rows):
                raise ValueError("Repères dupliqués")
        if set(x.id for x in self.actions) & set(x.id for x in self.combinations):
            raise ValueError("Un cas et une combinaison ne peuvent partager le même repère")
        return self


LIMITS = [
    "Efforts gravitaires uniquement ; aucune résistance ni conformité Eurocodes vérifiée.",
    "Poutres isostatiques sur deux appuis simples, EI constant ; déformations petites et linéaires.",
    "Planchers : répartition tributaire saisie, sans calcul de plaque ni redistribution par rigidité.",
    "Murs et poteaux : compression centrée ; excentricités, flambement et second ordre non calculés.",
    "Semelles : pression moyenne N/A sous charge centrée ; portance, tassement et ferraillage non vérifiés.",
    "Vent, séisme, poussées, torsion, incendie, soutènements et phases provisoires non calculés.",
    "Les sections dessinées sont des données ou propositions ; aucun dimensionnement automatique.",
]


def fingerprint(model: Model) -> str:
    data = {"engine": VERSION, "model": model.model_dump()}
    if model.linked_sections or model.architecture is not None or model.drawings is not None or model.automation_settings is not None:
        # Normalize float defaults through the same path as JSON imports.
        data["model"] = Model.model_validate_json(model.model_dump_json()).model_dump()
        if model.linked_sections:
            data["linked_engine"] = LINKED_VERSION
        if model.architecture is not None:
            data["architecture_engine"] = ARCHITECTURE_VERSION
        if model.drawings is not None:
            from engines.structuro_drawings import VERSION as DRAWING_VERSION
            data["drawing_engine"] = DRAWING_VERSION
        if model.automation_settings is not None:
            from engines.structuro_automation import VERSION as AUTO_VERSION
            data["automation_engine"] = AUTO_VERSION
    raw = json.dumps(data, sort_keys=True, allow_nan=False)
    return hashlib.sha256(raw.encode()).hexdigest()


def _has_source(source: Source) -> bool:
    return bool(source.document.strip() or source.note.strip())


def inspect(model: Model) -> tuple[list[dict], list[str]]:
    issues: list[dict] = inspect_links(model)
    def issue(el, text):
        issues.append({"element": el, "message": text})
    elements = {e.id: e for e in model.elements}
    actions = {a.id: a for a in model.actions}
    if not elements:
        issue(None, "Ajouter les éléments porteurs et leurs appuis.")
    if not model.gravity_model_reviewed:
        issue(None, "Confirmer le modèle gravitaire, les transferts centrés et les hypothèses de répartition.")
    if model.self_weight_action not in actions or actions[model.self_weight_action].kind != "G":
        issue(None, "Affecter le poids propre à une action permanente G existante.")
    for c in model.combinations:
        if set(c.factors) != set(actions) or not _has_source(c.source):
            issue(None, f"{c.id} : fournir un coefficient explicite par action et sa justification.")
    indegree = dict.fromkeys(elements, 0)
    for e in model.elements:
        if not e.reviewed:
            issue(e.id, "Géométrie, matériau, chargement et appuis à confirmer.")
        if not _has_source(e.source) or not _has_source(e.mechanics_source):
            issue(e.id, "Documenter la géométrie et les hypothèses mécaniques (poids propre, rigidité, appuis).")
        if any(v is None for v in (e.length_m, e.width_m, e.height_m, e.density_kn_m3)):
            issue(e.id, "Longueur, largeur, hauteur et poids volumique requis ; inconnu n'est pas zéro.")
        if e.kind == "beam" and (len(e.supports) != 2 or any(s.fraction is not None for s in e.supports)):
            issue(e.id, "Poutre : exactement deux appuis ordonnés gauche/droite, sans fraction imposée.")
        if e.kind == "footing" and e.supports:
            issue(e.id, "Une semelle termine le chemin de charges ; supprimer ses appuis.")
        if e.kind not in ("beam", "footing"):
            if not e.supports or any(s.fraction is None for s in e.supports) or abs(sum(s.fraction or 0 for s in e.supports)-1) > 1e-9:
                issue(e.id, "Les fractions de répartition vers les appuis doivent totaliser 1.")
        for s in e.supports:
            target = elements.get(s.target)
            if not target:
                issue(e.id, f"Appui inconnu : {s.target}")
                continue
            indegree[s.target] += 1
            if target.kind == "slab":
                issue(e.id, "Reprise par une dalle non couverte par ce modèle.")
            if target.kind == "beam":
                if s.receiving == "axial":
                    issue(e.id, "Préciser charge uniforme ou ponctuelle sur la poutre réceptrice.")
                if s.receiving == "point" and (s.position_m is None or target.length_m is None or s.position_m > target.length_m):
                    issue(e.id, "Position de charge absente ou hors de la poutre réceptrice.")
                if s.receiving == "uniform" and s.position_m is not None:
                    issue(e.id, "Une charge uniforme ne possède pas de position ponctuelle.")
                if s.shape is not None:
                    if s.receiving != "uniform":
                        issue(e.id, "Une forme triangle/trapèze s'applique à une charge répartie (receiving=uniform).")
                    elif target.length_m is not None:
                        ramp = _ramp(s, target.length_m)
                        if ramp is None or not (0 < ramp <= target.length_m / 2 + 1e-9):
                            issue(e.id, "Trapèze : rampe absente ou supérieure à la demi-portée de la poutre réceptrice.")
                elif s.ramp_m is not None:
                    issue(e.id, "Rampe fournie sans forme de charge (triangle/trapèze).")
            elif s.receiving != "axial" or s.position_m is not None or s.shape is not None or s.ramp_m is not None:
                issue(e.id, "Les transferts vers murs/poteaux/semelles sont uniquement axiaux centrés.")
        for load in e.loads:
            if load.action not in actions or not _has_source(load.source):
                issue(e.id, "Chaque charge doit référencer une action et une source explicites.")
            if load.mode == "surface" and e.kind != "slab":
                issue(e.id, "Les charges surfaciques sont réservées aux planchers.")
            if load.mode == "line" and e.kind not in ("beam", "wall"):
                issue(e.id, "Charge linéique réservée aux poutres et murs.")
            if load.mode == "point" and e.kind == "beam":
                if load.position_m is None or e.length_m is None or load.position_m > e.length_m:
                    issue(e.id, "Position de charge ponctuelle absente ou hors de la portée.")
            elif load.position_m is not None:
                issue(e.id, "Position ponctuelle acceptée uniquement pour une charge ponctuelle sur poutre.")
    q = deque(k for k, n in indegree.items() if n == 0)
    order = []
    while q:
        key = q.popleft()
        order.append(key)
        for support in elements[key].supports:
            if support.target in indegree:
                indegree[support.target] -= 1
                if indegree[support.target] == 0:
                    q.append(support.target)
    if len(order) != len(elements):
        issue(None, "Cycle dans les appuis : aucune descente de charges possible.")
    return issues, order


def _ramp(support: "Support", length: float) -> float | None:
    """Rampe (m) de la charge trapézoïdale reçue ; triangle = demi-portée."""
    if support.shape == "triangle":
        return length / 2
    return support.ramp_m


def trap_moment(length: float, total: float, ramp: float, x: float) -> float:
    """Moment fléchissant exact d'un trapèze symétrique (charge totale `total`, rampes `ramp`)
    sur poutre isostatique. Triangle : ramp = L/2. Intensité de plateau p = W/(L−a)."""
    if total == 0:
        return 0.0
    a = ramp
    p = total / (length - a)
    xs = min(x, length - x)            # symétrie
    r = total / 2
    if xs <= a:
        loads = p / a * xs ** 3 / 6
    else:
        loads = p * (xs * a / 2 - a * a / 3) + p * (xs - a) ** 2 / 2
    return r * xs - loads


def _trap_deflection(length: float, traps: list[tuple[float, float]], ei: float, n: int = 2000) -> list[float]:
    """Flèche (m) des charges trapézoïdales par double intégration numérique de M/EI
    (n segments, conditions v(0)=v(L)=0). Superposée à la solution fermée udl/ponctuelles."""
    xs = [length * i / n for i in range(n + 1)]
    curv = [-sum(trap_moment(length, w, a, x) for w, a in traps) / ei for x in xs]
    h = length / n
    slope = [0.0]
    for i in range(n):
        slope.append(slope[-1] + (curv[i] + curv[i + 1]) * h / 2)
    disp = [0.0]
    for i in range(n):
        disp.append(disp[-1] + (slope[i] + slope[i + 1]) * h / 2)
    end = disp[-1]
    return [disp[i] - end * xs[i] / length for i in range(n + 1)]


def beam_response(length: float, udl: float, points: list[tuple[float, float]], ei: float | None = None,
                  traps: list[tuple[float, float]] | None = None) -> dict:
    """Exact statics; elastic deflection sampled at 401 stations, never a code check.

    `traps` : charges réparties triangulaires/trapézoïdales symétriques [(W total kN, rampe m)]
    transmises par une dalle portant dans deux sens. Sans `traps`, calcul historique inchangé.
    """
    traps = list(traps or [])
    if not math.isfinite(length) or length <= 0 or not math.isfinite(udl) or udl < 0:
        raise ValueError("Portée/charge invalide")
    if ei is not None and (not math.isfinite(ei) or ei <= 0):
        raise ValueError("EI invalide")
    if any(not all(math.isfinite(v) for v in (p, x)) or p < 0 or x < 0 or x > length for p, x in points):
        raise ValueError("Charge ponctuelle invalide")
    if any(not all(math.isfinite(v) for v in (w, a)) or w < 0 or a <= 0 or a > length / 2 + 1e-9
           for w, a in traps):
        raise ValueError("Charge trapézoïdale invalide")
    traps = [(w, min(a, length / 2)) for w, a in traps]
    w_traps = sum(w for w, _ in traps)
    left = udl*length/2 + sum(p*(length-x)/length for p, x in points) + w_traps/2
    right = udl*length + sum(p for p, _ in points) + w_traps - left
    stations = sorted({0., length, *(x for _, x in points)})
    extrema = list(stations)
    for a, b in zip(stations, stations[1:]):
        if udl > 0:
            root = (left-w_traps/2-sum(p for p, x in points if x <= a))/udl
            if a < root < b:
                extrema.append(root)
    def moment(x):
        m = (left-w_traps/2)*x-udl*x*x/2-sum(p*max(0., x-a) for p, a in points)
        return m + sum(trap_moment(length, w, a, x) for w, a in traps)
    if traps:
        # Moment non quadratique : maximum recherché sur 2001 stations + stations singulières.
        extrema += [length * i / 2000 for i in range(2001)]
    xm = max(extrema, key=moment)
    formula = "RA=wL/2+ΣP(L-a)/L; RB=wL+ΣP-RA; M(x)=RA*x-w*x²/2-ΣP*max(x-a,0)"
    if traps:
        formula += ("; trapèze symétrique (W, rampe a) : p=W/(L−a), R=W/2, "
                    "M(x≤a)=R·x−p·x³/(6a), M(a≤x≤L/2)=R·x−p(a·x/2−a²/3)−p(x−a)²/2")
    out = {"reaction_left_kn": left, "reaction_right_kn": right,
           "moment_max_knm": moment(xm), "moment_position_m": xm,
           "shear_max_kn": max(abs(left-sum(p for p,x in points if x==0)),
                               abs(right-sum(p for p,x in points if x==length))),
           "deflection_sampled_mm": None,
           "formula": formula}
    if ei is not None:
        def displacement(x):
            value = udl*x*(length**3-2*length*x*x+x**3)/(24*ei)
            for p, a in points:
                b = length-a
                if x <= a:
                    value += p*b*x*(length**2-b*b-x*x)/(6*length*ei)
                else:
                    z = length-x
                    value += p*a*z*(length**2-a*a-z*z)/(6*length*ei)
            return value
        if traps:
            extra = _trap_deflection(length, traps, ei)   # 2000 segments → stations i*5 = 401 points
            out["deflection_sampled_mm"] = max(displacement(length*i/400) + extra[i*5] for i in range(401))*1000
        else:
            out["deflection_sampled_mm"] = max(displacement(length*i/400) for i in range(401))*1000
        out["deflection_note"] = ("Maximum échantillonné (401 points), EI fourni, élastique NON fissuré, "
                                  "hors fluage : utiliser la flèche fissurée long terme pour la vérification.")
    return out


def calculate(model: Model) -> dict:
    issues, order = inspect(model)
    result = {"engine_version": VERSION, "input_hash": fingerprint(model),
              "status": "blocked" if issues else "mechanical_only", "execution_ready": False,
              "issues": issues, "limits": LIMITS, "cases": [], "quantities": [], "load_path": order,
              "reinforcement": calculate_reinforcement(model.reinforcement)}
    if issues:
        return result
    elements = {e.id: e for e in model.elements}
    cases = [(a.id, a.label, {a.id: 1.}) for a in model.actions]
    cases += [(c.id, c.label, c.factors) for c in model.combinations]
    for e in model.elements:
        result["quantities"].append({"id": e.id, "material": e.material,
            "gross_volume_m3": e.length_m*e.width_m*e.height_m,
            "note": "Volume brut par élément ; jonctions/baies non déduites, pas une commande."})
    for case_id, label, factors in cases:
        inbox = {k: [] for k in elements}
        rows, transfers = [], []
        total_external = total_ground = 0.
        for key in order:
            e = elements[key]
            weight = e.length_m*e.width_m*e.height_m*e.density_kn_m3*factors.get(model.self_weight_action, 0.)
            own = [(weight, "uniform" if e.kind == "beam" else "axial", None)]
            for load in e.loads:
                value = load.value*factors.get(load.action, 0.)
                if load.mode == "surface":
                    value *= e.length_m*e.width_m
                elif load.mode == "line":
                    value *= e.length_m
                mode = ("point" if load.mode == "point" else "uniform") if e.kind == "beam" else "axial"
                own.append((value, mode, load.position_m))
            external = sum(v for v, _, _ in own)
            total_external += external
            loads = inbox[key]+own
            force = sum(v for v, _, _ in loads)
            row = {"id": key, "kind": e.kind, "total_kn": force, "own_kn": external,
                   "received_kn": force-external, "design_status": "not_verified"}
            if e.kind == "beam":
                response = beam_response(e.length_m,
                    sum(v for v, mode, _ in loads if mode == "uniform")/e.length_m,
                    [(v, x) for v, mode, x in loads if mode == "point"], e.ei_kn_m2,
                    traps=[(v, x) for v, mode, x in loads if mode == "trap"])
                row.update(response)
                reactions = [response["reaction_left_kn"], response["reaction_right_kn"]]
            else:
                reactions = [force*s.fraction for s in e.supports]
                if e.kind in ("wall", "column"):
                    row["axial_stress_mpa"] = force/(e.length_m*e.width_m)/1000
                    row["formula"] = "σ=N/A ; compression centrée seulement"
                elif e.kind == "footing":
                    row["mean_pressure_kpa"] = force/(e.length_m*e.width_m)
                    row["formula"] = "q=N/A ; poids de la semelle inclus, remblai/eau à saisir explicitement"
                    total_ground += force
            for s, reaction in zip(e.supports, reactions):
                if s.shape is not None:
                    ramp = _ramp(s, elements[s.target].length_m)
                    inbox[s.target].append((reaction, "trap", ramp))
                    transfers.append({"from": key, "to": s.target, "force_kn": reaction,
                                      "receiving": s.receiving, "position_m": s.position_m,
                                      "shape": s.shape, "ramp_m": ramp})
                    continue
                inbox[s.target].append((reaction, s.receiving, s.position_m))
                transfers.append({"from": key, "to": s.target, "force_kn": reaction,
                                  "receiving": s.receiving, "position_m": s.position_m})
            rows.append(row)
        if abs(total_external-total_ground) > 1e-7*max(1., total_external):
            raise ValueError("Déséquilibre du chemin de charges")
        result["cases"].append({"id": case_id, "label": label, "factors": factors, "elements": rows,
            "transfers": transfers, "external_kn": total_external, "ground_kn": total_ground,
            "balance_error_kn": total_external-total_ground})
    if model.architecture is not None:
        result["architectural_compatibility"] = calculate_architecture(model, result["input_hash"])
    if model.linked_sections:
        result["linked_reinforcement"] = calculate_links(model, result)
    return result


def example() -> Model:
    """Independent teaching fixture. Never applied automatically to a user's PC."""
    source = Source(note="EXEMPLE PÉDAGOGIQUE : valeurs fictives, ne pas utiliser sur chantier")
    def el(id, kind, length, width, height, x, y, supports=(), **kw):
        return Element(id=id, kind=kind, length_m=length, width_m=width, height_m=height,
            x_m=x, y_m=y, density_kn_m3=25., source=source, mechanics_source=source,
            reviewed=True, material="Béton fictif", supports=list(supports), **kw)
    axial = lambda id: Support(target=id, fraction=1.)
    return Model(title="EXEMPLE FICTIF - travée gravitaire", actions=[Action(id="G",kind="G",label="Permanentes"),
        Action(id="Q",kind="Q",label="Exploitation fictive")], self_weight_action="G", gravity_model_reviewed=True,
        assumptions=["Exemple indépendant du PC. Transferts centrés. Aucune vérification de résistance."],
        elements=[
            el("D1","slab",4,3,.20,0,0,[Support(target="B1",fraction=.5,receiving="uniform"),Support(target="M1",fraction=.5)],
                level="R+1",loads=[Load(action="Q",value=2,mode="surface",source=source)]),
            el("B1","beam",4,.25,.45,0,0,[Support(target="P1"),Support(target="P2")],level="R+1",ei_kn_m2=25000),
            el("M1","wall",4,.20,2.8,0,3,[axial("S3")],level="RDC"),
            el("P1","column",.3,.3,2.8,0,0,[axial("S1")],level="RDC"),
            el("P2","column",.3,.3,2.8,4,0,[axial("S2")],level="RDC"),
            el("S1","footing",1,1,.3,0,0,level="Fondations"),
            el("S2","footing",1,1,.3,4,0,level="Fondations"),
            el("S3","footing",4,.6,.3,0,3,level="Fondations"),
        ], combinations=[Combination(id="GplusQ",label="Somme illustrative G+Q (pas une combinaison normative)",factors={"G":1.,"Q":1.},source=source)])
