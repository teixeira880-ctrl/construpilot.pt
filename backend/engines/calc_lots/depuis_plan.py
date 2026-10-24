"""Entradas dos motores de especialidades tiradas de uma planta lida pelo ConstruPilot (coleção `plans_takeoff`) — Portugal.

Mesma leitura geométrica que o motor de planos de execução (`engines.mep.adapter.from_takeoff` e depois
`engines.mep.model.build`): divisões calibradas, aberturas associadas às paredes, pisos empilhados. Daí obtém-se:
- as divisões e paredes das perdas de calor de `lotes_tecnicos` (paredes exteriores, envidraçados, portas, pavimento, cobertura);
- a geometria « caixa » do estudo de estrutura de moradia `structuro_house` (implantação, pisos, aberturas por fachada);
- os dados de área útil e envidraçados do pré-certificado REH.
Tudo o que a planta não dá (altura das caixilharias, natureza do pavimento térreo, desvão) é uma hipótese nomeada.
"""
from __future__ import annotations

from shapely.geometry import LineString, Polygon
from shapely.ops import unary_union

from engines.mep.adapter import from_takeoff
from engines.mep.model import EDGE_TOL, build

# Alturas correntes das caixilharias (m) — hipóteses, a substituir pelas cotas da planta
H_ABERTURA = {"fenetre": 1.20, "baie": 2.10, "porte_fenetre": 2.10, "porte": 2.10, "porte_garage": 2.00}
NOME_ABERTURA = {"fenetre": "janela", "baie": "vão envidraçado", "porte_fenetre": "porta-janela", "porte": "porta",
                 "porte_garage": "portão de garagem"}
ESPESSURA_PAREDE = 0.20
# Tipos de divisão do motor MEP → chaves de aquecimento.T_INT
TIPO_DIVISAO = {"sejour": "sala", "chambre": "quarto", "cuisine": "cozinha", "salle_de_bain": "casa_de_banho",
                "salle_d_eau": "casa_de_banho", "wc": "casa_de_banho", "entree": "corredor", "circulation": "corredor",
                "escalier": "corredor", "bureau": "escritorio", "buanderie": "lavandaria", "cellier": "arrumos",
                "dressing": "arrumos", "autre": "outro"}
NAO_AQUECIDO = {"garage", "exterieur"}
FACHADAS = ("frente", "tras", "esquerda", "direita")


def niveaux(plan: dict) -> list:
    """Pisos do modelo MEP (levanta AdapterError se a planta não tiver divisões nem escala)."""
    levels, _ = build(from_takeoff(plan, None, "pt", {}))
    if not any(lv.rooms for lv in levels):
        raise ValueError("Nenhuma divisão utilizável nesta planta (são necessárias divisões fechadas e calibradas).")
    return levels


def _implantacao(level) -> Polygon:
    polys = [Polygon(r.polygon).buffer(EDGE_TOL, join_style=2) for r in level.rooms if len(r.polygon) >= 3]
    return unary_union(polys)


def _exterior(level):
    """Função (a, b) → True se a aresta segue a fachada (união das divisões alargada da espessura da parede)."""
    contorno = _implantacao(level).boundary

    def test(a, b) -> bool:
        mid = LineString([a, b]).interpolate(0.5, normalized=True)
        return mid.distance(contorno) <= 1.5 * EDGE_TOL
    return test


def _aberturas_exteriores(room) -> list:
    vistas = {}
    for o, *_ in list(room.windows) + list(room.doors):          # porta-janela: presente nas duas listas
        if o.exterior:
            vistas[id(o)] = o
    return list(vistas.values())


def _retangulo(room) -> tuple[float | None, float | None]:
    """Comprimento × largura do retângulo envolvente, só se a divisão for (quase) retangular."""
    poly = Polygon(room.polygon)
    x0, y0, x1, y1 = poly.bounds
    bbox = (x1 - x0) * (y1 - y0)
    if bbox <= 0 or poly.area / bbox < 0.95:
        return None, None
    return round(max(x1 - x0, y1 - y0), 2), round(min(x1 - x0, y1 - y0), 2)


def divisoes_termicas(levels: list) -> tuple[list[dict], list[str]]:
    """Divisões no formato de `calc_lots.lotes_tecnicos` (paredes com áreas; U deixados ao motor)."""
    hyp = ["geometria lida na planta: paredes exteriores = paredes das divisões na fachada; pé-direito do piso",
           "alturas correntes das caixilharias: " + ", ".join(f"{NOME_ABERTURA[k]} {v:g} m".replace(".", ",") for k, v in H_ABERTURA.items())
           + " (a substituir pelas cotas do projeto)",
           "pavimento do piso inferior sobre o solo; cobertura do último piso sob desvão não útil (ENU)",
           "garagem e espaços exteriores não aquecidos e não contados; as suas paredes meeiras tratadas como interiores"]
    bas, haut = levels[0].id, levels[-1].id
    out = []
    for lv in levels:
        ext = _exterior(lv)
        for r in lv.rooms:
            if r.type in NAO_AQUECIDO:
                continue
            n = len(r.polygon)
            paredes_ext = 0.0
            for i in range(n):
                a, b = r.polygon[i], r.polygon[(i + 1) % n]
                if ext(a, b):
                    paredes_ext += LineString([a, b]).length * lv.height
            vaos = [{"tipo": "porta" if o.kind in ("porte", "porte_garage") else "envidracado",
                     "area_m2": round(o.width * H_ABERTURA.get(o.kind, H_ABERTURA["fenetre"]), 2), "U": None, "lado": "exterior"}
                    for o in _aberturas_exteriores(r)]
            paredes = []
            a_vaos = sum(v["area_m2"] for v in vaos)
            if paredes_ext > 0:
                paredes.append({"tipo": "parede", "area_m2": round(max(paredes_ext - a_vaos, 0.0), 2), "U": None, "lado": "exterior"})
            paredes += vaos
            if lv.id == bas:
                paredes.append({"tipo": "pavimento", "area_m2": round(r.area, 2), "U": None, "lado": "solo"})
            if lv.id == haut:
                paredes.append({"tipo": "cobertura", "area_m2": round(r.area, 2), "U": None, "lado": "enu"})
            comp, larg = _retangulo(r)
            div = {"nome": f"{r.name} ({lv.name})" if len(levels) > 1 else r.name, "tipo": TIPO_DIVISAO.get(r.type, "outro"),
                   "area_m2": round(r.area, 2), "pe_direito_m": lv.height, "paredes": paredes,
                   "local_inferior": "solo" if lv.id == bas else "aquecido"}
            if comp and larg:
                div.update(comprimento_m=comp, largura_m=larg)
            out.append(div)
    if not out:
        raise ValueError("Nenhuma divisão aquecida reconhecida na planta.")
    return out, hyp


def dados_reh(levels: list) -> tuple[dict, list[str]]:
    """Área útil, pé-direito médio, número de pisos, envidraçados exteriores e tipologia (T-n) para `calc_lots.reh`."""
    uteis = [(lv, r) for lv in levels for r in lv.rooms if r.type not in NAO_AQUECIDO]
    area = sum(r.area for _, r in uteis)
    if area <= 0:
        raise ValueError("Nenhuma área útil relevada na planta")
    pd = sum(lv.height * r.area for lv, r in uteis) / area
    vidro = sum(o.width * H_ABERTURA.get(o.kind, H_ABERTURA["fenetre"]) for _, r in uteis for o in _aberturas_exteriores(r)
                if o.kind not in ("porte", "porte_garage"))
    quartos = sum(1 for _, r in uteis if r.type == "chambre")
    p = {"area_util_m2": round(area, 1), "pe_direito_m": round(pd, 2), "pisos": len(levels), "tipo": "moradia", "tipologia": quartos}
    hyp = [f"área útil = soma das divisões aquecidas relevadas na planta: {area:.1f} m²".replace(".", ","),
           f"tipologia T{quartos} deduzida do número de quartos reconhecidos na planta"]
    if vidro > 0:
        p["area_envidracada_m2"] = round(vidro, 1)
        hyp.append(f"área envidraçada = vãos exteriores da planta com alturas correntes: {vidro:.1f} m²".replace(".", ","))
    return p, hyp


def geometria_estrutura(levels: list, nome: str) -> tuple[dict, list[str]]:
    """Geometria « caixa » de `structuro_house`: retângulo envolvente, pisos da planta, aberturas exteriores por fachada."""
    allp = unary_union([Polygon(r.polygon) for lv in levels for r in lv.rooms if r.type != "exterieur" and len(r.polygon) >= 3])
    x0, y0, x1, y1 = allp.bounds
    t = ESPESSURA_PAREDE
    L, W = (x1 - x0) + 2 * t, (y1 - y0) + 2 * t
    hyp = [f"implantação = retângulo envolvente das divisões + paredes de {t:g} m: {L:.2f} × {W:.2f} m (forma real a verificar)".replace(".", ","),
           "um piso por página da planta; sem paredes resistentes interiores indicadas (vãos de laje entre fachadas); cobertura inclinada; "
           "solo sem estudo geotécnico (larguras de sapata por tabela, nada definitivo)",
           "pé-direito do piso + 0,20 m de laje = altura entre pisos"]
    ops = []
    for lv in levels:
        for o in lv.openings:
            if not o.exterior or o.width <= 0.3:
                continue
            mx, my = o.mid
            d = {"frente": my - y0, "tras": y1 - my, "esquerda": mx - x0, "direita": x1 - mx}
            fac = min(d, key=d.get)
            ops.append({"level": lv.name, "facade": fac, "width_m": round(o.width, 2), "label": NOME_ABERTURA.get(o.kind, "abertura")})
    geo = {"name": nome, "outer_L_m": round(L, 2), "outer_W_m": round(W, 2), "wall_thickness_m": t,
           "levels": [{"name": lv.name, "storey_height_m": round(lv.height + 0.2, 2), "use": "habitacao"} for lv in levels],
           "openings": ops}
    return geo, hyp
