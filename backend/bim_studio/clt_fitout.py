"""Fit-out quantities up to key handover, from the rooms, fixtures and openings read on the plans.

Electricity uses the app's RTIEBT engine (engines.calc_lots.instalacoes.eletricidade): sockets and light
points per room, circuits of at most 8 points, circuit length to the board, residual-current devices.
Plumbing counts the drawn fixtures (DR 23/95 devices); pipe runs follow the rooms on the plan: horizontal
distance from the room to the technical riser plus the storey height, cold water to every fixture and hot
water to the fixtures that take it. Every quantity says which rule or measurement it comes from.
"""
from __future__ import annotations

from decimal import Decimal

from engines.calc_lots import instalacoes

WET = {"casa_de_banho"}
DROP_M = Decimal("1.5")          # vertical run from ceiling or floor to the fixture (hipótese)
WALL_TILE_M = Decimal("2.1")     # tiled height in bathrooms (hipótese, the plan names the tile only)
OPENING_H = {"lintel": Decimal("2.3"), "janela": Decimal("1.2"), "vao_envidracado": Decimal("2.1")}
FITTING_ALLOWANCE = Decimal("1.1")  # +10 % for fittings and offcuts, as in engines.calc_lots.especialidades

FIXTURE_BASES = {"autoclismo": "un_sanita", "lavatorio": "un_lavatorio", "chuveiro": "un_base_duche",
                 "banheira": "un_banheira", "lava_loica": "un_lava_loica"}


def _d(value):
    return Decimal(str(value))


def _centre(room):
    x0, y0, x1, y1 = room["rect_m"]
    return (x0 + x1) / 2, (y0 + y1) / 2


def quantities(floors):
    """floors: [{name, height_m, ceiling_height_m, rooms[{nome, tipo, area_m2, perimetro_m, comprimento_m, aparelhos, rect_m}],
                 windows[{largura_m, sobre, tipo}], interior_doors, riser_m: [x, y] | None}]
    Returns one dict of basis quantities per floor and the notes on how they were obtained."""
    rooms = [(i, r) for i, f in enumerate(floors) for r in f.get("rooms") or []]
    out = [dict() for _ in floors]
    notes = []
    if not rooms:
        return out, notes
    riser = next((f["riser_m"] for f in floors if f.get("riser_m")), None)
    level = [Decimal(0)]
    for f in floors[:-1]:
        level.append(level[-1] + _d(f["height_m"]))

    def run(i, room):
        if riser is None or not room.get("rect_m"):
            return Decimal(8)
        cx, cy = _centre(room)
        return _d(abs(cx - riser[0]) + abs(cy - riser[1])) + level[i] + DROP_M

    # electricity: one installation for the house, quantities returned to the floor of each room
    divisoes = []
    for i, r in rooms:
        kind = r["tipo"] if r["tipo"] in instalacoes.DIVISOES else "corredor"
        divisoes.append({"nome": f"{r['nome']} ({floors[i]['name']})", "tipo": kind, "area_m2": r["area_m2"],
                         "perimetro_m": r.get("perimetro_m"), "comprimento_m": r.get("comprimento_m"),
                         "distancia_quadro_m": float(run(i, r))})
    el = instalacoes.eletricidade({"divisoes": divisoes, "equipamentos": {"placa": True, "forno": True,
                                   "maquina_lavar_roupa": True, "maquina_lavar_loica": True, "termoacumulador": True}})
    floor_of = {d["nome"]: i for d, (i, _) in zip(divisoes, rooms)}
    for p in el["pontos"]:
        q = out[floor_of[p["divisao"]]]
        q["un_tomada"] = q.get("un_tomada", 0) + p["tomadas"]
        q["un_ponto_luz"] = q.get("un_ponto_luz", 0) + p["pontos_luz"]
        q["un_interruptor"] = q.get("un_interruptor", 0) + max(1, p["pontos_luz"])
    for c in el["circuitos"]:
        n = max(1, int(c.get("pontos") or 1))
        length = _d(c["comprimento_m"]) * (1 + Decimal("0.25") * (n - 1) if c["familia"] in ("iluminacao", "tomadas") else 1) * FITTING_ALLOWANCE
        where = [floor_of[d] for d in c.get("divisoes") or [] if d in floor_of] or [0]
        for i in where:
            q = out[i]
            share = length / len(where)
            q["m_cabo"] = q.get("m_cabo", 0) + share * (Decimal(5) / 3 if c.get("b") == 3 else 1)
            q["m_tubo_eletrico"] = q.get("m_tubo_eletrico", 0) + share * Decimal("0.9")
            q["un_circuito"] = q.get("un_circuito", 0) + Decimal(1) / len(where)
    out[0]["un_quadro"] = 1
    out[0]["un_diferencial"] = el["diferenciais"]
    notes.append(f"Eletricidade (RTIEBT, motor instalacoes): {sum(p['tomadas'] for p in el['pontos'])} tomadas, "
                 f"{sum(p['pontos_luz'] for p in el['pontos'])} pontos de luz, {len(el['circuitos'])} circuitos, "
                 f"{el['diferenciais']} diferenciais; potência a contratar {el['potencia_contratada_kva']:g} kVA.")

    # plumbing and sanitary ware, per room
    for i, r in rooms:
        q = out[i]
        length = run(i, r)
        for fixture in r.get("aparelhos") or []:
            flow, hot, drain, _ = instalacoes.DISPOSITIVOS[fixture]
            q["un_ponto_agua"] = q.get("un_ponto_agua", 0) + 1 + int(hot)
            q["m_tubo_agua"] = q.get("m_tubo_agua", 0) + length * (1 + int(hot)) * FITTING_ALLOWANCE
            if drain:
                q["un_ponto_esgoto"] = q.get("un_ponto_esgoto", 0) + 1
                q["m_tubo_esgoto"] = q.get("m_tubo_esgoto", 0) + length * FITTING_ALLOWANCE
            if fixture in FIXTURE_BASES:
                q[FIXTURE_BASES[fixture]] = q.get(FIXTURE_BASES[fixture], 0) + 1
        area, perimeter = _d(r["area_m2"]), _d(r.get("perimetro_m") or 0)
        if r["tipo"] in WET:
            q["m2_pavimento_ceramico"] = q.get("m2_pavimento_ceramico", 0) + area
            q["m2_ceramica_parede"] = q.get("m2_ceramica_parede", 0) + perimeter * WALL_TILE_M
        else:
            q["m2_pavimento"] = q.get("m2_pavimento", 0) + area
            q["m_rodape"] = q.get("m_rodape", 0) + perimeter
    out[0]["un_aqs"] = 1
    notes.append("Canalização: aparelhos desenhados nas plantas (DR 23/95); tubagem pela distância em planta de cada divisão à "
                 "coluna técnica + altura do piso + 1,5 m de descida, água quente só nos aparelhos que a usam, +10 % de acessórios.")

    # joinery
    for i, f in enumerate(floors):
        q = out[i]
        for w in f.get("windows") or []:
            if w.get("sobre") == "viga":
                height = _d(f.get("ceiling_height_m") or OPENING_H["vao_envidracado"])
            elif w.get("sobre") == "lintel":
                height = OPENING_H["lintel"]
            else:
                height = OPENING_H[w["tipo"]]
            q["m2_caixilharia"] = q.get("m2_caixilharia", 0) + _d(w["largura_m"]) * height
            q["un_vao_exterior"] = q.get("un_vao_exterior", 0) + 1
        q["un_porta_interior"] = int(f.get("interior_doors") or 0)
    out[0]["un_porta_entrada"] = 1
    notes.append("Caixilharia: vãos medidos na envolvente (interrupções das paredes CLT). Altura: sob viga = pé-direito acabado; "
                 "sob lintel = 2,30 m (topo das portas cotadas); janela sem lintel 1,20 m e vão envidraçado 2,10 m (hipóteses, como no motor de plantas).")
    notes.append("Uma porta de entrada (a planta não a identifica). Portas interiores = portas Dv numeradas na planta.")
    return [{k: _d(v) for k, v in q.items()} for q in out], notes
