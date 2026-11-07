"""Motores de cálculo partilhados pelas ferramentas por profissão e pelo orçamento guiado.

Regras:
- Nenhuma constante escondida: rendimento, demãos, perdas e embalagens vêm do utilizador
  (ou do produto escolhido). Os valores sugeridos são devolvidos como *sugestão*, nunca aplicados em silêncio.
- « Não sei » não vale zero: um dado essencial em falta fica em `pending` e o resultado que dele
  depende não é calculado (fica a None), em vez de produzir uma precisão fictícia.
- Cada valor do resultado indica a sua origem: `user` (introduzido), `formula` (calculado).
- Os três modos da interface (guiado, direto, avançado) chamam estes mesmos motores.
"""
from __future__ import annotations

import math
from typing import Any

# Sugestões mostradas ao utilizador (nunca aplicadas sem confirmação).
SUGGESTIONS = {
    "paint_yield_m2_per_l": {"value": 10, "note": "Valor típico de tinta plástica de interior (8–12 m²/L). Confirme na ficha técnica do produto."},
    "paint_coats": {"value": 2, "note": "Duas demãos é o habitual sobre superfície já pintada."},
    "floor_waste_pct": {"value": 10, "note": "Colocação reta: 5–10 %; diagonal ou espinha: 12–15 %."},
    "masonry_waste_pct": {"value": 5, "note": "Perdas habituais de corte e quebra: 3–7 %."},
}


class CalcError(ValueError):
    """Dado inválido (negativo, fora de limites). Mensagem destinada ao utilizador."""


def _num(value: Any, field: str, *, minimum: float = 0, maximum: float = 1e6, allow_zero: bool = True) -> float | None:
    """Converte um valor introduzido. None / "" / "nao_sei" → None (pendente), nunca 0."""
    if value is None or value == "" or value == "nao_sei":
        return None
    try:
        v = float(value)
    except (TypeError, ValueError):
        raise CalcError(f"«{field}»: indique um número.")
    if math.isnan(v) or math.isinf(v):
        raise CalcError(f"«{field}»: valor inválido.")
    if v < minimum or v > maximum or (not allow_zero and v == 0):
        raise CalcError(f"«{field}»: valor fora dos limites aceitáveis.")
    return v


def _r(v: float | None, d: int = 2) -> float | None:
    return None if v is None else round(v + 0.0, d)


def _openings_area(openings: list[dict] | None, pending: list[str], label: str) -> float | None:
    total = 0.0
    for i, o in enumerate(openings or []):
        w = _num(o.get("width_m"), f"{label}: largura da abertura {i + 1}", maximum=50)
        h = _num(o.get("height_m"), f"{label}: altura da abertura {i + 1}", maximum=50)
        count = _num(o.get("count", 1), f"{label}: número de aberturas {i + 1}", maximum=500) or 0
        if w is None or h is None:
            pending.append(f"{label}: dimensões da abertura {i + 1}")
            return None
        total += w * h * count
    return total


# --------------------------------------------------------------------------- pintura

def room_paint_surfaces(room: dict) -> dict:
    """Superfícies de uma divisão: paredes (perímetro × altura − aberturas) e teto (área).

    Aceita `length_m`+`width_m` (retangular) ou `perimeter_m`+`floor_area_m2` (forma livre),
    ou diretamente `wall_area_m2` (medida feita no local / planta)."""
    name = (room.get("name") or "Divisão").strip()[:60]
    pending: list[str] = []
    h = _num(room.get("height_m"), f"{name}: pé-direito", maximum=30, allow_zero=False)
    length = _num(room.get("length_m"), f"{name}: comprimento", maximum=500, allow_zero=False)
    width = _num(room.get("width_m"), f"{name}: largura", maximum=500, allow_zero=False)
    perimeter = _num(room.get("perimeter_m"), f"{name}: perímetro", maximum=2000, allow_zero=False)
    floor = _num(room.get("floor_area_m2"), f"{name}: área do chão", maximum=100000, allow_zero=False)
    direct_walls = _num(room.get("wall_area_m2"), f"{name}: área das paredes", maximum=100000)

    if perimeter is None and length is not None and width is not None:
        perimeter = 2 * (length + width)
    if floor is None and length is not None and width is not None:
        floor = length * width

    openings = _openings_area(room.get("openings"), pending, name)
    walls_gross = direct_walls
    if walls_gross is None:
        if perimeter is None:
            pending.append(f"{name}: comprimento e largura (ou perímetro)")
        if h is None:
            pending.append(f"{name}: pé-direito")
        if perimeter is not None and h is not None:
            walls_gross = perimeter * h
    walls_net = None
    if walls_gross is not None and openings is not None:
        walls_net = max(walls_gross - openings, 0.0)
        if openings > walls_gross:
            raise CalcError(f"{name}: as aberturas são maiores do que as paredes — verifique as medidas.")

    paint_walls = room.get("paint_walls", True) is not False
    paint_ceiling = bool(room.get("paint_ceiling", False))
    ceiling = floor if paint_ceiling else 0.0
    if paint_ceiling and floor is None:
        pending.append(f"{name}: área do teto (comprimento × largura)")

    surface = None
    parts_ok = (not paint_walls or walls_net is not None) and (not paint_ceiling or ceiling is not None)
    if parts_ok:
        surface = (walls_net if paint_walls else 0.0) + (ceiling or 0.0)
    return {
        "name": name,
        "walls_gross_m2": _r(walls_gross), "openings_m2": _r(openings), "walls_net_m2": _r(walls_net),
        "ceiling_m2": _r(ceiling if paint_ceiling else 0.0), "surface_m2": _r(surface),
        "source": "user" if direct_walls is not None else "formula",
        "pending": pending,
    }


def paint_calc(payload: dict) -> dict:
    """Quantidade de tinta: superfície × demãos ÷ rendimento → litros → embalagens."""
    rooms = payload.get("rooms") or []
    if not isinstance(rooms, list) or not rooms:
        raise CalcError("Indique pelo menos uma divisão ou superfície.")
    if len(rooms) > 200:
        raise CalcError("Máximo de 200 divisões por cálculo.")
    details = [room_paint_surfaces(r) for r in rooms]
    pending = [p for d in details for p in d["pending"]]
    coats = _num(payload.get("coats"), "Número de demãos", maximum=10, allow_zero=False)
    yield_m2_l = _num(payload.get("yield_m2_per_l"), "Rendimento (m²/L por demão)", maximum=100, allow_zero=False)
    can_l = _num(payload.get("can_size_l"), "Tamanho da embalagem (L)", maximum=1000, allow_zero=False)
    if coats is None:
        pending.append("Número de demãos")
    if yield_m2_l is None:
        pending.append("Rendimento da tinta (ficha técnica do produto)")

    surface = None if any(d["surface_m2"] is None for d in details) else sum(d["surface_m2"] for d in details)
    liters = None
    if surface is not None and coats is not None and yield_m2_l is not None:
        liters = surface * coats / yield_m2_l
    cans = math.ceil(liters / can_l - 1e-9) if liters is not None and can_l else None

    suggestions = {}
    if coats is None:
        suggestions["coats"] = SUGGESTIONS["paint_coats"]
    if yield_m2_l is None:
        suggestions["yield_m2_per_l"] = SUGGESTIONS["paint_yield_m2_per_l"]
    return {
        "tool": "paint",
        "rooms": details,
        "surface_m2": _r(surface), "coats": coats, "yield_m2_per_l": yield_m2_l,
        "liters": _r(liters, 1), "can_size_l": can_l, "cans": cans,
        "formula": "litros = superfície (m²) × demãos ÷ rendimento (m²/L)",
        "provenance": {"surface_m2": "formula", "coats": "user" if coats else None,
                       "yield_m2_per_l": "user" if yield_m2_l else None, "liters": "formula"},
        "pending": pending, "suggestions": suggestions,
        "complete": not pending,
    }


# --------------------------------------------------------------------------- pavimentos / revestimentos

def floor_calc(payload: dict) -> dict:
    """Pavimento ou revestimento: área × (1 + perdas) ÷ cobertura por embalagem → embalagens."""
    pending: list[str] = []
    area = _num(payload.get("area_m2"), "Área a revestir (m²)", maximum=100000, allow_zero=False)
    if area is None:
        length = _num(payload.get("length_m"), "Comprimento", maximum=1000, allow_zero=False)
        width = _num(payload.get("width_m"), "Largura", maximum=1000, allow_zero=False)
        if length is not None and width is not None:
            area = length * width
        else:
            pending.append("Área (ou comprimento e largura)")
    waste = _num(payload.get("waste_pct"), "Perdas (%)", maximum=50)
    if waste is None:
        pending.append("Percentagem de perdas")
    coverage = _num(payload.get("package_m2"), "Cobertura de uma embalagem (m²)", maximum=1000, allow_zero=False)
    if coverage is None:
        pl = _num(payload.get("piece_length_m"), "Comprimento da peça (m)", maximum=10, allow_zero=False)
        pw = _num(payload.get("piece_width_m"), "Largura da peça (m)", maximum=10, allow_zero=False)
        per_pack = _num(payload.get("pieces_per_package"), "Peças por embalagem", maximum=10000, allow_zero=False)
        if pl and pw and per_pack:
            coverage = pl * pw * per_pack
        else:
            pending.append("Cobertura por embalagem (m²) ou dimensões da peça e peças por embalagem")
    with_waste = area * (1 + waste / 100) if area is not None and waste is not None else None
    packages = math.ceil(with_waste / coverage - 1e-9) if with_waste is not None and coverage else None
    price = _num(payload.get("package_price"), "Preço por embalagem", maximum=1e6)
    cost = packages * price if packages is not None and price is not None else None
    return {
        "tool": "floor", "area_m2": _r(area), "waste_pct": waste, "area_with_waste_m2": _r(with_waste),
        "package_m2": _r(coverage, 3), "packages": packages, "package_price": price, "material_cost": _r(cost),
        "formula": "embalagens = arredondar acima( área × (1 + perdas/100) ÷ m² por embalagem )",
        "pending": pending, "suggestions": {} if waste is not None else {"waste_pct": SUGGESTIONS["floor_waste_pct"]},
        "complete": not pending,
    }


# --------------------------------------------------------------------------- alvenaria

def masonry_calc(payload: dict) -> dict:
    """Alvenaria: área líquida da parede ÷ área de um bloco com junta → nº de blocos (+ perdas)."""
    pending: list[str] = []
    length = _num(payload.get("wall_length_m"), "Comprimento da parede", maximum=1000, allow_zero=False)
    height = _num(payload.get("wall_height_m"), "Altura da parede", maximum=50, allow_zero=False)
    if length is None or height is None:
        pending.append("Comprimento e altura da parede")
    openings = _openings_area(payload.get("openings"), pending, "Parede")
    bl = _num(payload.get("block_length_m"), "Comprimento do bloco (m)", maximum=2, allow_zero=False)
    bh = _num(payload.get("block_height_m"), "Altura do bloco (m)", maximum=2, allow_zero=False)
    joint = _num(payload.get("joint_m"), "Espessura da junta (m)", maximum=0.05)
    if bl is None or bh is None:
        pending.append("Dimensões do bloco (comprimento × altura)")
    if joint is None:
        pending.append("Espessura da junta")
    waste = _num(payload.get("waste_pct"), "Perdas (%)", maximum=50)
    if waste is None:
        pending.append("Percentagem de perdas")
    net = None
    if length is not None and height is not None and openings is not None:
        net = length * height - openings
        if net <= 0:
            raise CalcError("As aberturas ocupam toda a parede — verifique as medidas.")
    per_m2 = 1 / ((bl + joint) * (bh + joint)) if bl and bh and joint is not None else None
    blocks = math.ceil(net * per_m2 * (1 + waste / 100) - 1e-9) if net is not None and per_m2 and waste is not None else None
    return {
        "tool": "masonry", "net_area_m2": _r(net), "openings_m2": _r(openings), "blocks_per_m2": _r(per_m2, 2),
        "waste_pct": waste, "blocks": blocks,
        "formula": "blocos = área líquida × 1/((c+junta)×(a+junta)) × (1 + perdas/100)",
        "limits": "Cálculo de quantidades apenas. Não verifica estabilidade nem dimensiona a parede.",
        "pending": pending, "suggestions": {} if waste is not None else {"waste_pct": SUGGESTIONS["masonry_waste_pct"]},
        "complete": not pending,
    }


TOOLS = {"paint": paint_calc, "floor": floor_calc, "masonry": masonry_calc}


def compute(tool: str, payload: dict) -> dict:
    fn = TOOLS.get(tool)
    if not fn:
        raise CalcError("Ferramenta desconhecida.")
    if not isinstance(payload, dict):
        raise CalcError("Dados inválidos.")
    return fn(payload)


# --------------------------------------------------------------------------- orçamento de pintura (percurso guiado)

def painting_quote_lines(job: dict) -> dict:
    """Constrói as linhas de um orçamento de pintura a partir do percurso guiado.

    Os preços são os do profissional (ou ficam a 0 e marcados « por confirmar »). Nenhuma taxa de IVA
    é escolhida aqui: as linhas ficam com `vat_rate=None`, e as regras fiscais existentes aplicam-se."""
    calc = paint_calc({"rooms": job.get("rooms") or [], "coats": job.get("coats"),
                       "yield_m2_per_l": job.get("yield_m2_per_l"), "can_size_l": job.get("can_size_l")})
    prices = job.get("prices") or {}
    labor_m2 = _num(prices.get("labor_per_m2"), "Mão de obra por m²", maximum=10000)
    paint_l = _num(prices.get("paint_per_l"), "Preço da tinta por litro", maximum=10000)
    can_price = _num(prices.get("paint_per_can"), "Preço por embalagem", maximum=100000)
    crack_ml = _num(job.get("crack_repair_ml"), "Fissuras a reparar (metros)", maximum=100000)
    crack_price = _num(prices.get("crack_per_ml"), "Preço da reparação de fissuras por metro", maximum=10000)
    prep_m2 = _num(prices.get("prep_per_m2"), "Preparação de superfícies por m²", maximum=10000)

    to_confirm: list[str] = list(calc["pending"])
    lines: list[dict] = [{"kind": "section", "title": "Pintura"}]
    surface = calc["surface_m2"]
    room_names = ", ".join(d["name"] for d in calc["rooms"])

    def line(designation, unit, qty, price, line_kind, description="", price_label=""):
        if price is None:
            to_confirm.append(f"Preço: {price_label or designation}")
        if qty is None:
            to_confirm.append(f"Quantidade: {designation}")
        lines.append({"kind": "line", "line_kind": line_kind, "designation": designation, "description": description,
                      "unit": unit, "qty": qty if qty is not None else 0, "unit_price_ht": price or 0, "vat_rate": None,
                      "price_missing": price is None, "quantity_missing": qty is None,
                      "price_source": "utilizador" if price is not None else ""})

    if job.get("surface_prep", True):
        line("Preparação de superfícies (limpeza, lixagem, betumação pontual)", "m²", surface, prep_m2,
             "main_oeuvre", f"Divisões: {room_names}", "preparação por m²")
    if job.get("crack_repair"):
        line("Reparação de fissuras (abertura, tratamento e betumação)", "ml", crack_ml, crack_price,
             "main_oeuvre", "", "reparação de fissuras por metro")
    coats = calc["coats"]
    line(f"Pintura de paredes{' e tetos' if any(r.get('paint_ceiling') for r in job.get('rooms') or []) else ''}"
         f"{f' — {int(coats)} demãos' if coats else ''}", "m²", surface, labor_m2, "main_oeuvre",
         f"Divisões: {room_names}", "mão de obra de pintura por m²")
    if job.get("supply_paint", True):
        if can_price is not None and calc["cans"] is not None:
            line(f"Tinta — {calc['cans']} embalagem(ns) de {calc['can_size_l']:g} L", "u", calc["cans"], can_price,
                 "fourniture", f"{calc['liters']} L calculados ({calc['formula']})")
        else:
            line("Tinta", "L", calc["liters"], paint_l, "fourniture",
                 f"{calc['formula']}" if calc["liters"] is not None else "Quantidade por confirmar", "tinta por litro")

    # sem duplicados, mantendo a ordem
    seen: set[str] = set()
    to_confirm = [x for x in to_confirm if not (x in seen or seen.add(x))]
    return {"lines": lines, "calc": calc, "to_confirm": to_confirm}
