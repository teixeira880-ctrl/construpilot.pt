"""Checks for continuous perimeter footings on a verified orthogonal L plan.

The input sheet contains design reactions and geotechnical limits, not values
inferred from the architectural drawings. Straight sections only. All results
remain preliminary until the foundation system and junctions are checked.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

from shapely.geometry import LineString, Polygon

from engines import structuro_anchorage, structuro_ec2

MARKER = "CP_SAPATAS_V1"
NUMERIC = {
    "largura_parede_m": (.12, .6), "profundidade_m": (.5, 3),
    "recobrimento_mm": (40, 100), "agregado_mm": (8, 32),
    "fck_mpa": (20, 50), "fyk_mpa": (400, 600), "gamma_c": (1.4, 2),
    "gamma_s": (1.1, 1.5), "alpha_cc": (.7, 1), "alpha_ct": (.7, 1),
    "gamma_g": (1.25, 1.6), "peso_betao_kn_m3": (22, 27),
    "aterro_kpa": (0, 100), "qrd_kpa": (10, 1500), "qlim_els_kpa": (10, 1000),
}


class InputError(ValueError):
    pass


@dataclass(frozen=True)
class Action:
    ned: float
    med: float
    nser: float
    mser: float


@dataclass(frozen=True)
class Inputs:
    values: dict
    actions: dict
    soil_reference: str
    load_reference: str
    demo: bool


def _finite(raw):
    try:
        result = float(raw.replace(",", "."))
    except ValueError as exc:
        raise InputError("Valor numérico inválido na ficha de sapatas.") from exc
    if not math.isfinite(result):
        raise InputError("Valor numérico não finito na ficha de sapatas.")
    return result


def _edge_key(a, b):
    return tuple(sorted((tuple(a), tuple(b))))


def read_inputs(docs):
    import pymupdf

    pages = []
    for _, data in docs:
        with pymupdf.open(stream=data, filetype="pdf") as pdf:
            for page in pdf:
                lines = [line.strip() for line in page.get_text().splitlines() if line.strip()]
                if lines and lines[0] == MARKER:
                    pages.append(lines[1:])
    if not pages:
        return None
    if len(pages) != 1:
        raise InputError("Anexe uma única ficha CP_SAPATAS_V1.")
    fields, actions = {}, {}
    for line in pages[0]:
        key, sep, value = line.partition("=")
        if not sep or not value.strip():
            raise InputError("Cada linha da ficha de sapatas tem de usar campo=valor.")
        key, value = key.strip(), value.strip()
        if key == "tramo":
            parts = [_finite(v) for v in value.split(";")]
            if len(parts) != 8:
                raise InputError("Cada tramo precisa de x1;y1;x2;y2;NEd;MEd;Nser;Mser.")
            coordinates = _edge_key(parts[:2], parts[2:4])
            action = Action(*parts[4:])
            if coordinates in actions or not 0 < action.nser <= action.ned <= 2000 or max(abs(action.med), abs(action.mser)) > 500:
                raise InputError("Tramo repetido ou reações fora do domínio do cálculo.")
            actions[coordinates] = action
        elif key in fields or key not in NUMERIC.keys() | {"tipo", "applicability", "fonte_geotecnia", "fonte_reacoes"}:
            raise InputError(f"Campo repetido ou desconhecido na ficha de sapatas ({key[:45]}).")
        else:
            fields[key] = value
    required = NUMERIC.keys() | {"tipo", "applicability", "fonte_geotecnia", "fonte_reacoes"}
    if required - fields.keys():
        raise InputError("Campos em falta na ficha: " + ", ".join(sorted(required - fields.keys())))
    if fields["tipo"] not in {"ensaio", "projeto"} or any(len(fields[k]) > 90 for k in ("fonte_geotecnia", "fonte_reacoes")):
        raise InputError("Indique tipo=ensaio ou tipo=projeto e referências de até 90 caracteres.")
    if fields["applicability"] != "paredes_continuas_centradas_no_contorno":
        raise InputError("O cálculo exige que os eixos dos muros resistentes coincidam com o contorno declarado na ficha.")
    values = {key: _finite(fields[key]) for key in NUMERIC}
    if any(not bounds[0] <= values[key] <= bounds[1] for key, bounds in NUMERIC.items()):
        raise InputError("Há parâmetros de material, solo ou geometria fora do domínio do cálculo.")
    return Inputs(values, actions, fields["fonte_geotecnia"], fields["fonte_reacoes"], fields["tipo"] == "ensaio")


def _outline(source):
    if not source.floors or not source.levels:
        raise InputError("Confirme os contornos, alinhamento e níveis de todos os pisos no PDF de origem.")
    outline = source.floors[0].outline
    points = list(outline.exterior.coords)
    edges = list(zip(points, points[1:]))
    recess = outline.envelope.difference(outline)
    if len(edges) != 6 or not recess.area or not recess.equals(recess.envelope) or any(
        (a[0] == b[0]) == (a[1] == b[1]) or math.dist(a, b) < 2 for a, b in edges
    ):
        raise InputError("O cálculo está limitado a contornos em L ortogonais com seis tramos de pelo menos 2 m.")
    if max(outline.bounds[2] - outline.bounds[0], outline.bounds[3] - outline.bounds[1]) > 100:
        raise InputError("A extensão máxima do contorno no pré-dimensionamento é de 100 m por direção.")
    return outline, edges


def _actions(q_left, q_right, width, projection, depth):
    """Integrate linear gross upward contact pressure over each cantilever."""
    slope = (q_right - q_left) / width
    moments, shears = [], []
    for q_edge, gradient in ((q_left, slope), (q_right, -slope)):
        moments.append(q_edge * projection**2 / 2 + gradient * projection**3 / 6)
        cut = max(projection - depth, 0)
        shears.append(q_edge * cut + gradient * cut**2 / 2)
    return max(moments), max(shears)


def _section(values, action, width, height, phi, spacing, long_count):
    cover = values["recobrimento_mm"] / 1000
    bar = phi / 1000
    wall = values["largura_parede_m"]
    projection = (width - wall) / 2
    depth = height - cover - bar / 2
    uniform = height * values["peso_betao_kn_m3"] + values["aterro_kpa"]
    ul_peak = (action.ned / width + values["gamma_g"] * uniform,
               6 * action.med / width**2)
    sl_peak = (action.nser / width + uniform, 6 * action.mser / width**2)
    ql, qr = ul_peak[0] - ul_peak[1], ul_peak[0] + ul_peak[1]
    qsl, qsr = sl_peak[0] - sl_peak[1], sl_peak[0] + sl_peak[1]
    qmax, qsmax = max(ql, qr), max(qsl, qsr)
    if min(ql, qr, qsl, qsr) <= 0 or qmax > values["qrd_kpa"] or qsmax > values["qlim_els_kpa"]:
        return None
    moment, shear = _actions(ql, qr, width, projection, depth)
    materials = {k: values[k] for k in ("gamma_c", "gamma_s", "alpha_cc")}
    materials.update(fck=values["fck_mpa"], fyk=values["fyk_mpa"])
    calc = structuro_ec2.design_section(moment, shear, b_m=1, h_m=height, d_m=depth,
                                       d_prime_m=cover + bar / 2, **materials)
    longitudinal = structuro_ec2.design_section(0, b_m=width, h_m=height, d_m=depth - bar,
                                               d_prime_m=cover + 1.5 * bar, **materials)
    flex = calc["flexure"]
    # The shared calculator rounds output to 0.01 cm². Compare with the upper
    # end of that interval and round the anchorage requirement conservatively.
    as_required = flex["as_req_cm2"] + .005
    transverse = math.pi * phi**2 / 4 * (1000 / spacing) / 100
    long_provided = math.pi * phi**2 / 4 * long_count / 100
    anchorage = structuro_anchorage.anchorage(phi, as_req_cm2=as_required,
        as_prov_cm2=transverse, cover_mm=min(values["recobrimento_mm"], (spacing - phi) / 2), bond="poor",
        gamma_c=materials["gamma_c"], gamma_s=materials["gamma_s"], alpha_cc=values["alpha_ct"],
        fck=materials["fck"], fyk=materials["fyk"])
    anchorage_mm = math.ceil(anchorage["lbd_reduced_mm"] + .05)
    available_mm = (projection - cover) * 1000
    if (flex["mode"] != "simple" or as_required > transverse or transverse > flex["as_max_cm2"]
        or long_provided < longitudinal["flexure"]["as_min_cm2"] + .005
        or long_provided > longitudinal["flexure"]["as_max_cm2"]
        or calc["shear"]["needs_stirrups"] or shear > calc["shear"]["vrdc_kn"] - .005
        or anchorage_mm > available_mm):
        return None
    return {"q_ed": qmax, "q_ser": qsmax, "q_min_ed": min(ql, qr), "q_min_ser": min(qsl, qsr),
            "m_ed": moment, "v_ed": shear, "v_rd": calc["shear"]["vrdc_kn"], "as_req": as_required,
            "as_prov": transverse, "as_long_min": longitudinal["flexure"]["as_min_cm2"] + .005,
            "as_long_prov": long_provided, "l_bd_mm": anchorage_mm, "l_av_mm": available_mm}


def calculate(source, inputs):
    outline, edges = _outline(source)
    if set(inputs.actions) != {_edge_key(a, b) for a, b in edges}:
        raise InputError("As coordenadas da ficha têm de coincidir com os seis tramos do PDF de origem.")
    values = inputs.values
    candidates = sorted((b*h, b, h) for b in range(600, 1301, 50) for h in range(300, 551, 50))
    min_edge = min(math.dist(a, b) for a, b in edges)
    for _, width_mm, height_mm in candidates:
        width, height = width_mm / 1000, height_mm / 1000
        if width <= values["largura_parede_m"] or width >= min_edge / 2 or height >= values["profundidade_m"]:
            continue
        for phi, spacing in ((10, 200), (10, 150), (10, 125), (12, 150), (12, 125), (12, 100), (14, 100), (16, 100)):
            clear_width = width_mm - 2 * values["recobrimento_mm"] - phi
            long_count = math.ceil(clear_width / spacing) + 1
            minimum = max(phi, values["agregado_mm"] + 5, 20)
            if (height_mm - 2 * values["recobrimento_mm"] - 2 * phi < minimum
                or clear_width / max(1, long_count - 1) - phi < minimum or spacing - phi < minimum):
                continue
            rows = [_section(values, inputs.actions[_edge_key(a, b)], width, height, phi, spacing, long_count)
                    for a, b in edges]
            if any(row is None for row in rows):
                continue
            # The wall/footing alignment is declared by the input sheet. The
            # shaded band is the joined footprint, not six overlapping solids.
            band = LineString(outline.exterior.coords).buffer(width / 2, join_style=2)
            if not isinstance(band, Polygon) or len(band.interiors) != 1 or not band.covers(outline.boundary):
                continue
            # Orthogonal mitred band: outside corners and inside corners cancel.
            if not math.isclose(band.area, outline.length * width, abs_tol=1e-6):
                continue
            return {"outline": outline, "band": band, "edges": edges, "checks": rows, "inputs": inputs,
                    "width_mm": width_mm, "height_mm": height_mm, "bar_mm": phi, "spacing_mm": spacing,
                    "long_count": long_count, "long_spacing_mm": clear_width / (long_count - 1),
                    "execution_verified": False}
    raise InputError("Nenhuma secção do catálogo passou os controlos dos seis tramos. Reveja o solo, as reações e a secção com o projetista.")
