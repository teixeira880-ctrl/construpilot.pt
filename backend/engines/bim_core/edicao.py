"""Edição do modelo de edifício (BuildingModel): as mesmas operações servem o editor por opções e o editor por prompt.

Cada operação é um dicionário {"op": nome, ...}; `aplicar` devolve um modelo NOVO (o original não é tocado), a lista do
que foi feito em linguagem corrente e os erros das operações recusadas. Nada é inventado: uma operação que não fecha
(parede inexistente, vão que sai da parede, espessura fora dos limites) é recusada com o motivo.

`interpretar` transforma frases correntes («muda a espessura da parede V2 para 25 cm», «acrescenta uma janela de
1,20 m na parede V1 a 2 m do início», «apaga a parede C3», «pé-direito 2,80») em operações, sem IA; o que não percebe
é devolvido tal e qual, para o Assistente tratar. O IFC gera-se do modelo editado com ifc_builder.build_ifc.
"""
from __future__ import annotations

import copy
import math
import re
import unicodedata
from dataclasses import asdict

from .model import DEFAULTS, Beam, BuildingModel, Column, Footing, Opening, Slab, Space, Wall

LIMITES = {"espessura": (0.03, 1.0), "altura": (1.5, 12.0), "largura_vao": (0.3, 12.0)}
_TIPOS = {"Wall": Wall, "Opening": Opening, "Slab": Slab, "Column": Column, "Beam": Beam, "Footing": Footing, "Space": Space}
_LISTAS = (("walls", Wall), ("openings", Opening), ("slabs", Slab), ("columns", Column), ("beams", Beam), ("footings", Footing), ("spaces", Space))
VAOS = {"porta": "porte", "janela": "fenetre", "vao": "baie", "porte": "porte", "fenetre": "fenetre", "baie": "baie"}
DIMENSOES = {
    "walls": {"espessura": "thickness", "altura": "height", "comprimento": "length"},
    "openings": {"largura": "width", "altura": "height", "peitoril": "sill"},
    "slabs": {"espessura": "thickness"},
    "columns": {"comprimento": "dx", "largura": "dy", "altura": "height"},
    "beams": {"comprimento": "length", "largura": "width", "altura": "depth", "espessura": "depth"},
    "footings": {"comprimento": "dx", "largura": "dy", "altura": "depth", "profundidade": "depth", "espessura": "depth"},
    "spaces": {"altura": "height"},
}
REVESTIMENTOS = {
    "madeira": ("Madeira", (0.58, 0.35, 0.18)),
    "granito": ("Granito", (0.47, 0.48, 0.47)),
    "pedra": ("Pedra", (0.65, 0.58, 0.46)),
    "reboco": ("Reboco", (0.90, 0.88, 0.83)),
    "tijolo": ("Tijolo", (0.64, 0.31, 0.22)),
    "betao": ("Betão aparente", (0.58, 0.60, 0.59)),
}
PAVIMENTOS = {
    "ceramica": ("Cerâmica", (0.68, 0.36, 0.27)),
    "porcelanato": ("Grés porcelânico", (0.73, 0.69, 0.62)),
    "vinil": ("Vinil", (0.53, 0.57, 0.57)),
    "laminado": ("Laminado", (0.72, 0.55, 0.37)),
    **{key: REVESTIMENTOS[key] for key in ("madeira", "granito", "pedra", "betao")},
}
CORES_PAREDE = {
    "branco": "#efede6", "creme": "#e7d9bd", "bege": "#d4bea3", "cinza claro": "#bfc2c2",
    "cinza": "#858a8b", "antracite": "#32383c", "preto": "#292b2c", "terracota": "#b76b51",
    "azul petroleo": "#1e5962", "azul": "#4d729c", "verde salvia": "#8a9b83", "verde": "#527d61",
    "amarelo": "#dfb353", "rosa": "#c99699", "vermelho": "#a54440", "castanho": "#785443",
}


class OpErro(ValueError):
    """Operação recusada, com o motivo em linguagem corrente."""


def para_dict(m: BuildingModel) -> dict:
    """Modelo → JSON (para guardar a cópia editável e enviar ao editor)."""
    d = asdict(m)
    d["origin"] = list(m.origin)
    for k in ("slabs", "spaces"):
        for x in d[k]:
            x["points"] = [list(p) for p in x["points"]]
    return d


def de_dict(d: dict) -> BuildingModel:
    m = BuildingModel(plan_id=d.get("plan_id") or "", page_index=int(d.get("page_index") or 0), storey_name=d.get("storey_name") or "Piso",
                      params=dict(d.get("params") or {}), warnings=list(d.get("warnings") or []), ifc_guids=bool(d.get("ifc_guids")),
                      origin=tuple(d.get("origin") or (0.0, 0.0)))
    for k, cls in _LISTAS:
        for x in d.get(k) or []:
            x = dict(x)
            if "points" in x:
                x["points"] = [tuple(p) for p in x["points"]]
            getattr(m, k).append(cls(**x))
    return m


def reconcile_pdf_outline(saved: BuildingModel, read: BuildingModel, verified: BuildingModel) -> BuildingModel:
    """Bring forward the corrected PDF geometry while retaining explicit BIM edits."""
    options = verified.params.get("verified_outline")
    saved.params.pop("verified_outline", None)
    if not options or len(read.slabs) != 1 or len(verified.slabs) != 1:
        return saved
    before, after = read.slabs[0], verified.slabs[0]
    slab = next((s for s in saved.slabs if s.source_id == before.source_id), None)
    if slab is None or slab.points not in (before.points, after.points):
        return saved
    slab.points = after.points
    saved.params["verified_outline"] = options

    def axes(w):
        return w.x1, w.y1, w.x2, w.y2

    before_walls = {w.source_id: w for w in read.walls}
    after_walls = {w.source_id: w for w in verified.walls}
    before_openings = {v.source_id: v for v in read.openings}
    after_openings = {v.source_id: v for v in verified.openings}
    for wall in saved.walls:
        original, corrected = before_walls.get(wall.source_id), after_walls.get(wall.source_id)
        if original is None or corrected is None or axes(wall) != axes(original) or axes(wall) == axes(corrected):
            continue
        changes = []
        for opening in saved.openings:
            if opening.wall_id != wall.source_id:
                continue
            a, b = before_openings.get(opening.source_id), after_openings.get(opening.source_id)
            offset, width = opening.offset, opening.width
            if a and b and b.wall_id == wall.source_id and (offset, width) == (a.offset, a.width):
                offset, width = b.offset, b.width
            changes.append((opening, offset, width))
        if any(offset + width > corrected.length + .0002 for _, offset, width in changes):
            continue
        for opening, offset, width in changes:
            opening.offset, opening.width = offset, width
        old_length = wall.length
        wall.x1, wall.y1, wall.x2, wall.y2 = axes(corrected)
        _alinhar_sapatas(saved, wall)
        for footing in saved.footings:
            if footing.wall_id == wall.source_id and math.isclose(footing.dx, old_length, abs_tol=.001):
                footing.dx = wall.length
    return saved


def _lim(nome, v, chave):
    lo, hi = LIMITES[chave]
    v = float(v)
    if not (lo <= v <= hi) or math.isnan(v):
        raise OpErro(f"{nome} de {v:g} m fora dos limites ({lo:g} a {hi:g} m).")
    return v


def _parede(m, i):
    w = next((w for w in m.walls if w.source_id == i), None)
    if not w:
        raise OpErro(f"Não existe a parede «{i}».")
    return w


def _alinhar_sapatas(m, parede):
    for sapata in m.footings:
        if sapata.wall_id == parede.source_id:
            sapata.cx = (parede.x1 + parede.x2) / 2
            sapata.cy = (parede.y1 + parede.y2) / 2
            sapata.angle = parede.angle


def _novo_id(m, prefixo):
    usados = {x.source_id for k, _ in _LISTAS for x in getattr(m, k)}
    n = 1
    while f"{prefixo}{n}" in usados:
        n += 1
    return f"{prefixo}{n}"


def _vao_cabe(w, o, outros):
    if o.offset < -1e-9 or o.offset + o.width > w.length + 1e-6:
        raise OpErro(f"O vão não cabe na parede «{w.source_id}» ({w.length:.2f} m): começa a {o.offset:.2f} m e tem {o.width:.2f} m.")
    if o.sill + o.height > w.height + 1e-6:
        raise OpErro(f"O vão ultrapassa a altura da parede «{w.source_id}» ({w.height:.2f} m).")
    for x in outros:
        if x.source_id != o.source_id and x.wall_id == o.wall_id and o.offset < x.offset + x.width - 1e-9 and x.offset < o.offset + o.width - 1e-9:
            raise OpErro(f"O vão sobrepõe-se ao vão «{x.source_id}» na parede «{w.source_id}».")


def _redimensionar(m, o):
    grupo, medida = o["grupo"], o["dimensao"]
    atributo = DIMENSOES.get(grupo, {}).get(medida)
    if not atributo:
        raise OpErro("Essa dimensão não é editável neste tipo de elemento.")
    elementos = getattr(m, grupo)
    ids = set(o["ids"])
    alvos = [item for item in elementos if item.source_id in ids]
    if not alvos or {item.source_id for item in alvos} != ids:
        raise OpErro("Selecione um elemento deste piso.")
    modo, valor = o["modo"], float(o["valor"])
    if modo not in {"absoluto", "relativo", "percentagem"} or not math.isfinite(valor):
        raise OpErro("Indique uma medida válida.")
    alteracoes = []
    for item in alvos:
        anterior = getattr(item, atributo)
        novo = {"absoluto": valor, "relativo": anterior + valor, "percentagem": anterior * (1 + valor / 100)}[modo]
        limite = {
            ("walls", "height"): "altura", ("walls", "thickness"): "espessura",
            ("slabs", "thickness"): "espessura", ("openings", "width"): "largura_vao",
        }.get((grupo, atributo))
        if limite:
            novo = _lim(medida.capitalize(), novo, limite)
        elif not math.isfinite(novo) or not ((0 if atributo == "sill" else 0.05) <= novo <= 300):
            raise OpErro(f"{medida.capitalize()} fora dos limites do modelo.")
        if atributo == "length":
            if anterior <= 0:
                raise OpErro("O elemento precisa de um segmento válido.")
            item.x2 = item.x1 + (item.x2 - item.x1) * novo / anterior
            item.y2 = item.y1 + (item.y2 - item.y1) * novo / anterior
        else:
            setattr(item, atributo, novo)
        if grupo == "openings":
            _vao_cabe(_parede(m, item.wall_id), item, m.openings)
        if grupo == "walls":
            if atributo == "length":
                _alinhar_sapatas(m, item)
            for vao in m.openings:
                if vao.wall_id == item.source_id:
                    _vao_cabe(item, vao, m.openings)
        alteracoes.append(f"{item.source_id}: {anterior:.2f} → {novo:.2f} m")
    return f"{medida.capitalize()}: " + ", ".join(alteracoes) + "."


def _contorno(m):
    from shapely.geometry import Polygon
    from shapely.ops import unary_union

    areas = [Polygon(s.points) for s in m.slabs if len(s.points) >= 3]
    valid = [p for p in areas if p.is_valid and p.area > 0.5]
    return unary_union(valid) if valid else None


def _paredes_exteriores(m):
    from shapely.geometry import LineString

    contorno = _contorno(m)
    if contorno is None:
        return []
    border = contorno.boundary
    walls = []
    for w in m.walls:
        axis = LineString([(w.x1, w.y1), (w.x2, w.y2)])
        band = border.buffer(max(0.20, min(0.35, w.thickness * 1.5)))
        if axis.length > 0.1 and axis.intersection(band).length >= 0.70 * axis.length:
            walls.append(w.source_id)
    return walls


def _editar_sapata_alinhada(m, ident):
    from shapely.geometry import LineString, Point

    sapata = next((f for f in m.footings if f.source_id == ident), None)
    if not sapata:
        raise OpErro("Selecione uma sapata do modelo.")
    if sapata.wall_id:
        paredes = [_parede(m, sapata.wall_id)]
    else:
        ids = set(_paredes_exteriores(m))
        paredes = [w for w in m.walls if w.source_id in ids]
    ponto = Point(sapata.cx, sapata.cy)
    angulo = sapata.angle if sapata.dx >= sapata.dy else sapata.angle + math.pi / 2
    largura = min(sapata.dx, sapata.dy)
    comprimento = max(sapata.dx, sapata.dy)
    candidatos = []
    for parede in paredes:
        if abs(math.cos(parede.angle - angulo)) < 0.97:
            continue
        linha = LineString([(parede.x1, parede.y1), (parede.x2, parede.y2)])
        distancia = ponto.distance(linha)
        if distancia <= largura / 2 + 0.35 and parede.length >= comprimento - 0.02:
            candidatos.append((distancia, parede))
    candidatos.sort(key=lambda pair: pair[0])
    if not candidatos or (len(candidatos) > 1 and candidatos[1][0] - candidatos[0][0] <= 0.1):
        raise OpErro("Não encontrei uma única parede exterior alinhada. Indique o comprimento da sapata.")
    _, parede = candidatos[0]
    sapata.cx = (parede.x1 + parede.x2) / 2
    sapata.cy = (parede.y1 + parede.y2) / 2
    sapata.dx, sapata.dy = parede.length, largura
    sapata.angle = parede.angle
    return f"Sapata «{ident}» alinhada com a parede exterior «{parede.source_id}»: {parede.length:.2f} m."


def _sapatas_nos_cantos(m, ident):
    modelo = next((f for f in m.footings if f.source_id == ident), None)
    if not modelo or modelo.wall_id:
        raise OpErro("Selecione uma sapata isolada como modelo para os cantos.")
    poligono = _contorno(m)
    if poligono is None or poligono.geom_type != "Polygon" or poligono.interiors:
        raise OpErro("Preciso de um perímetro único para identificar os cantos.")
    cantos = list(poligono.simplify(0.025, preserve_topology=True).exterior.coords)[:-1]
    if len(cantos) != 4:
        raise OpErro(f"O contorno tem {len(cantos)} cantos. Indique quais são os quatro pretendidos.")
    criadas = 0
    for x, y in cantos:
        if any(math.hypot(ft.cx - x, ft.cy - y) <= 0.05 for ft in m.footings):
            continue
        m.footings.append(Footing(_novo_id(m, "S"), x, y, modelo.dx, modelo.dy, modelo.depth, modelo.angle))
        criadas += 1
    if not criadas:
        raise OpErro("Já existem sapatas nos quatro cantos.")
    return f"{criadas} sapata(s) criada(s) nos cantos, usando as dimensões de «{ident}»."


def _op(m: BuildingModel, o: dict) -> str:
    op = o.get("op")
    if op == "elementos_redimensionar":
        return _redimensionar(m, o)
    if op == "sapata_ate_limite":
        return _editar_sapata_alinhada(m, o["id"])
    if op == "sapatas_quatro_cantos":
        return _sapatas_nos_cantos(m, o["id"])
    if op == "sapatas_lineares_criar":
        ids = _paredes_exteriores(m) if o.get("fachadas") else [o["parede"]]
        if not ids:
            raise OpErro("Não foi possível identificar as paredes exteriores. Selecione uma parede no desenho.")
        largura, altura = float(o["largura"]), float(o["altura"])
        if not (0.1 <= largura <= 10 and 0.1 <= altura <= 10):
            raise OpErro("Indique uma largura e uma altura positivas em metros dentro dos limites do modelo.")
        adicionadas = 0
        for ident in ids:
            w = _parede(m, ident)
            if largura < w.thickness:
                raise OpErro(f"A largura indicada é menor que a espessura da parede «{ident}».")
            if any(f.wall_id == ident for f in m.footings):
                continue
            m.footings.append(Footing(_novo_id(m, "SL"), (w.x1 + w.x2) / 2, (w.y1 + w.y2) / 2,
                                      w.length, largura, altura, w.angle, ident))
            adicionadas += 1
        if not adicionadas:
            raise OpErro("Já existem sapatas lineares nestas paredes. Selecione uma sapata para editar.")
        return f"{adicionadas} sapata(s) linear(es) desenhada(s): largura {largura:.2f} m e altura {altura:.2f} m."
    if op == "revestimento_paredes":
        material = o["material"]
        if material not in REVESTIMENTOS:
            raise OpErro("Escolha um material de revestimento disponível.")
        ids = _paredes_exteriores(m) if o.get("fachadas") else [o["id"]]
        if not ids:
            raise OpErro("As fachadas não estão identificadas neste piso. Selecione uma parede no desenho.")
        paredes = [_parede(m, ident) for ident in ids]
        revestimentos = m.params.setdefault("revestimentos", {})
        for parede in paredes:
            revestimentos[parede.source_id] = material
        return f"Revestimento de {REVESTIMENTOS[material][0].lower()} em {len(paredes)} parede(s)."
    if op == "pintar_paredes":
        cor = str(o.get("cor") or "").lower()
        if not re.fullmatch(r"#[0-9a-f]{6}", cor):
            raise OpErro("Indique uma cor da paleta ou um código hexadecimal RGB.")
        ids = _paredes_exteriores(m) if o.get("fachadas") else o.get("ids") or []
        if not ids:
            raise OpErro("Selecione uma parede ou indique quais quer pintar.")
        for ident in ids:
            _parede(m, ident)
        m.params.setdefault("cores_parede", {}).update(dict.fromkeys(ids, cor))
        return f"Cor {cor.upper()} aplicada em {len(ids)} parede(s)."
    if op == "revestimento_piso":
        material = o.get("material")
        if material not in PAVIMENTOS:
            raise OpErro("Indique um material de pavimento disponível.")
        ids = o.get("ids") or []
        slabs = [s for s in m.slabs if s.source_id in ids]
        if not ids or len(slabs) != len(set(ids)):
            raise OpErro("Selecione um pavimento desta página.")
        depth = o.get("espessura")
        if depth is not None:
            depth = float(depth)
            if not .001 <= depth <= .10:
                raise OpErro("A espessura do revestimento deve estar entre 1 e 100 mm.")
        finishes = m.params.setdefault("pavimentos", {})
        for slab in slabs:
            current = finishes.get(slab.source_id) or {}
            thickness = depth if depth is not None else current.get("espessura") if current.get("material") == material else None
            finishes[slab.source_id] = {"material": material, "espessura": thickness}
        return f"{PAVIMENTOS[material][0]} aplicado: {', '.join(s.name for s in slabs)}."
    if op == "parede_criar":
        w = Wall(source_id=o.get("id") or _novo_id(m, "P"), x1=float(o["x1"]), y1=float(o["y1"]), x2=float(o["x2"]), y2=float(o["y2"]),
                 thickness=_lim("Espessura", o.get("espessura", m.params.get("cloison_ep", DEFAULTS["cloison_ep"])), "espessura"),
                 height=_lim("Altura", o.get("altura", m.params.get("wall_height", DEFAULTS["wall_height"])), "altura"), load_bearing=bool(o.get("resistente", False)))
        if w.length < 0.05:
            raise OpErro("A parede tem menos de 5 cm de comprimento.")
        if any(x.source_id == w.source_id for x in m.walls):
            raise OpErro(f"Já existe a parede «{w.source_id}».")
        m.walls.append(w)
        return f"Parede «{w.source_id}» criada: {w.length:.2f} m, {w.thickness * 100:g} cm de espessura."
    if op == "parede_alterar":
        w = _parede(m, o["id"])
        feito = []
        if o.get("espessura") is not None:
            w.thickness = _lim("Espessura", o["espessura"], "espessura")
            feito.append(f"espessura {w.thickness * 100:g} cm")
        if o.get("altura") is not None:
            w.height = _lim("Altura", o["altura"], "altura")
            feito.append(f"altura {w.height:.2f} m")
        if o.get("resistente") is not None:
            w.load_bearing = bool(o["resistente"])
            feito.append("resistente" if w.load_bearing else "divisória")
        if any(o.get(k) is not None for k in ("x1", "y1", "x2", "y2")):
            for k in ("x1", "y1", "x2", "y2"):
                if o.get(k) is not None:
                    setattr(w, k, float(o[k]))
            if w.length < 0.05:
                raise OpErro("A parede ficaria com menos de 5 cm de comprimento.")
            feito.append(f"comprimento {w.length:.2f} m")
            _alinhar_sapatas(m, w)
        if not feito:
            raise OpErro("Nada para alterar na parede.")
        for v in [v for v in m.openings if v.wall_id == w.source_id]:
            _vao_cabe(w, v, m.openings)
        return f"Parede «{w.source_id}»: {', '.join(feito)}."
    if op == "parede_mover":
        w = _parede(m, o["id"])
        dx, dy = float(o.get("dx") or 0), float(o.get("dy") or 0)
        if not dx and not dy:
            raise OpErro("Deslocamento nulo.")
        w.x1, w.x2, w.y1, w.y2 = w.x1 + dx, w.x2 + dx, w.y1 + dy, w.y2 + dy
        _alinhar_sapatas(m, w)
        return f"Parede «{w.source_id}» deslocada {dx:+.2f} m em x e {dy:+.2f} m em y."
    if op == "parede_apagar":
        w = _parede(m, o["id"])
        n = sum(1 for v in m.openings if v.wall_id == w.source_id)
        m.walls.remove(w)
        m.openings[:] = [v for v in m.openings if v.wall_id != w.source_id]
        m.footings[:] = [f for f in m.footings if f.wall_id != w.source_id]
        return f"Parede «{w.source_id}» apagada" + (f", com os seus {n} vão(s)." if n else ".")
    if op == "vao_criar":
        w = _parede(m, o["parede"])
        tipo = VAOS.get(str(o.get("tipo") or "janela").lower())
        if not tipo:
            raise OpErro(f"Tipo de vão desconhecido: «{o.get('tipo')}».")
        larg = _lim("Largura do vão", o["largura"], "largura_vao")
        peit = float(o["peitoril"]) if o.get("peitoril") is not None else (DEFAULTS["window_sill"] if tipo == "fenetre" else 0.0)
        alt = float(o["altura"]) if o.get("altura") is not None else DEFAULTS[{"porte": "door_height", "fenetre": "window_height", "baie": "baie_height"}[tipo]]
        off = float(o["offset"]) if o.get("offset") is not None else (w.length - larg) / 2
        v = Opening(source_id=o.get("id") or _novo_id(m, "V"), kind=tipo, wall_id=w.source_id, offset=off, width=larg, sill=peit, height=alt)
        _vao_cabe(w, v, m.openings)
        m.openings.append(v)
        nome = {"porte": "Porta", "fenetre": "Janela", "baie": "Vão"}[tipo]
        return f"{nome} «{v.source_id}» de {larg:.2f} × {alt:.2f} m na parede «{w.source_id}», a {off:.2f} m do início."
    if op in ("vao_alterar", "vao_apagar"):
        v = next((v for v in m.openings if v.source_id == o["id"]), None)
        if not v:
            raise OpErro(f"Não existe o vão «{o['id']}».")
        if op == "vao_apagar":
            m.openings.remove(v)
            return f"Vão «{v.source_id}» apagado."
        for k, a in (("largura", "width"), ("altura", "height"), ("peitoril", "sill"), ("offset", "offset")):
            if o.get(k) is not None:
                setattr(v, a, float(o[k]))
        _lim("Largura do vão", v.width, "largura_vao")
        _vao_cabe(_parede(m, v.wall_id), v, m.openings)
        return f"Vão «{v.source_id}»: {v.width:.2f} × {v.height:.2f} m, peitoril {v.sill:.2f} m, a {v.offset:.2f} m do início."
    if op == "laje_alterar":
        s = next((s for s in m.slabs if s.source_id == o["id"]), None)
        if not s:
            raise OpErro(f"Não existe a laje «{o['id']}».")
        s.thickness = _lim("Espessura", o["espessura"], "espessura")
        return f"Laje «{s.source_id}»: espessura {s.thickness * 100:g} cm."
    if op == "pe_direito":
        h = _lim("Pé-direito", o["altura"], "altura")
        for v in m.openings:
            if v.sill + v.height > h + 1e-6:
                raise OpErro(f"O vão «{v.source_id}» ({v.sill + v.height:.2f} m) não cabe num pé-direito de {h:.2f} m.")
        for w in m.walls:
            w.height = h
        for c in m.columns:
            c.height = h
        for sp in m.spaces:
            sp.height = h
        m.params["wall_height"] = h
        return f"Pé-direito de {h:.2f} m em {len(m.walls)} paredes."
    if op == "paredes_espessura":
        e = _lim("Espessura", o["espessura"], "espessura")
        alvo = [w for w in m.walls if o.get("resistente") is None or w.load_bearing == bool(o["resistente"])]
        if not alvo:
            raise OpErro("Nenhuma parede corresponde.")
        for w in alvo:
            w.thickness = e
        quais = "todas as paredes" if o.get("resistente") is None else "paredes resistentes" if o["resistente"] else "divisórias"
        return f"{len(alvo)} {quais} com {e * 100:g} cm."
    if op == "material":
        alvo = o["id"]
        if not any(x.source_id == alvo for k, _ in _LISTAS for x in getattr(m, k)):
            raise OpErro(f"Não existe o elemento «{alvo}».")
        m.params.setdefault("materiais", {})[alvo] = str(o["material"])
        return f"Material de «{alvo}»: {o['material']}."
    raise OpErro(f"Operação desconhecida: «{op}».")


def aplicar(modelo: BuildingModel, ops: list[dict]):
    """(modelo novo, [o que foi feito], [erros]). Cada operação é atómica: a que falha não deixa nada a meio."""
    m = copy.deepcopy(modelo)
    feito, erros = [], []
    for o in ops:
        ensaio = copy.deepcopy(m)
        try:
            feito.append(_op(ensaio, o))
            m = ensaio
        except (OpErro, KeyError, TypeError, ValueError) as e:
            erros.append(f"{o.get('op', '?')}: {e if isinstance(e, OpErro) else 'dados em falta ou inválidos (' + str(e) + ')'}")
    return m, feito, erros


# ------------------------------------------------------------------------------------------- frases correntes → operações
def _norm(s):
    return "".join(c for c in unicodedata.normalize("NFD", (s or "").lower()) if unicodedata.category(c) != "Mn")


_NUM = r"(\d+(?:[.,]\d+)?)"


def _m(valor, unidade):
    v = float(valor.replace(",", "."))
    return v / 100 if unidade == "cm" else v / 1000 if unidade == "mm" else v


def interpretar(texto: str, modelo: BuildingModel):
    """(operações, frases não percebidas). Os identificadores são os do modelo, sem distinguir maiúsculas."""
    ids = {x.source_id.lower(): x.source_id for k, _ in _LISTAS for x in getattr(modelo, k)}
    ops, resto = [], []
    for frase in [f.strip() for f in re.split(r"[;\n]|(?<!\d)\.(?!\d)", texto or "") if f.strip()]:
        t = _norm(frase)
        ident = lambda s: ids.get(s.lower(), s)
        if (x := re.search(rf"pe[- ]direito\D*{_NUM}\s*(m|cm)?", t)):
            ops.append({"op": "pe_direito", "altura": _m(x[1], x[2] or "m")})
        elif (x := re.search(rf"(?:apaga|remove|elimina|tira)\w*\s+(?:a\s+|o\s+)?(parede|vao|janela|porta)\s+(\S+)", t)):
            ops.append({"op": "parede_apagar" if x[1] == "parede" else "vao_apagar", "id": ident(x[2])})
        elif (x := re.search(rf"(?:acrescenta|adiciona|cria|poe|coloca)\w*\s+(?:uma?\s+)?(janela|porta|vao)\s+(?:de|com)\s+{_NUM}\s*(m|cm)?.*?parede\s+(\S+)(?:.*?\ba\s+{_NUM}\s*(m|cm)?\s+do\s+inicio)?", t)):
            o = {"op": "vao_criar", "tipo": x[1], "largura": _m(x[2], x[3] or "m"), "parede": ident(x[4])}
            if x[5]:
                o["offset"] = _m(x[5], x[6] or "m")
            ops.append(o)
        elif (x := re.search(rf"espessura\s+d[ae]s?\s+parede\s+(\S+)\s+(?:para|com|de|=)\s*{_NUM}\s*(m|cm|mm)", t)):
            ops.append({"op": "parede_alterar", "id": ident(x[1]), "espessura": _m(x[2], x[3])})
        elif (x := re.search(rf"(todas as paredes|paredes resistentes|divisorias)\s+(?:com|de|para|a)\s*{_NUM}\s*(m|cm|mm)", t)):
            ops.append({"op": "paredes_espessura", "espessura": _m(x[2], x[3]),
                        **({} if x[1].startswith("todas") else {"resistente": x[1].startswith("paredes")})})
        elif (x := re.search(rf"(?:move|desloca|empurra)\w*\s+(?:a\s+)?parede\s+(\S+)\s+{_NUM}\s*(m|cm)?\s+para\s+(?:a\s+|o\s+)?(direita|esquerda|cima|baixo|norte|sul|este|leste|oeste)", t)):
            d = _m(x[2], x[3] or "m")
            dx, dy = {"direita": (d, 0), "este": (d, 0), "leste": (d, 0), "esquerda": (-d, 0), "oeste": (-d, 0), "cima": (0, d), "norte": (0, d),
                      "baixo": (0, -d), "sul": (0, -d)}[x[4]]
            ops.append({"op": "parede_mover", "id": ident(x[1]), "dx": dx, "dy": dy})
        elif (x := re.search(rf"parede\s+(\S+)\s+(?:passa a\s+|fica\s+|e\s+)?(resistente|divisoria)", t)):
            ops.append({"op": "parede_alterar", "id": ident(x[1]), "resistente": x[2] == "resistente"})
        elif (x := re.search(rf"laje\s+(\S+)\s+(?:com|de|para)\s*{_NUM}\s*(m|cm|mm)", t)):
            ops.append({"op": "laje_alterar", "id": ident(x[1]), "espessura": _m(x[2], x[3])})
        elif (x := re.search(r"material\s+d[aeo]s?\s+(?:parede|laje|pilar|viga|elemento)?\s*(\S+)\s*(?:para|=|:|e)\s+(.+)", t)):
            ops.append({"op": "material", "id": ident(x[1]), "material": frase[frase.lower().rfind(x[2][:4]):].strip() if x[2][:4] in frase.lower() else x[2]})
        else:
            resto.append(frase)
    return ops, resto

_GRUPOS = {
    "walls": r"\bparedes?\b",
    "openings": r"\b(?:vaos?|portas?|janelas?)\b",
    "slabs": r"\b(?:lajes?|pisos?|pavimentos?)\b",
    "columns": r"\bpilar(?:es)?\b",
    "beams": r"\bvigas?\b",
    "footings": r"\bsapatas?\b",
    "spaces": r"\b(?:divisao|divisoes|compartimentos?)\b",
}
_MEDIDA = re.compile(r"\b(comprimento|largura|altura|espessura|profundidade|peitoril)\b")
_VALOR = re.compile(r"(?<![\w.,])(?P<qual>\b(?:para|em|por|de|com)\s+|=\s*)?(?P<sinal>[+-])?\s*(?P<valor>\d+(?:[.,]\d+)?)\s*(?P<unidade>mm\b|cm\b|m\b|%)")
_FACHADA = re.compile(r"\b(?:fachadas?|faxadas?)\b")
_REVESTIR = re.compile(r"\b(?:revest\w*|acabamento|material)\b")
_MAT = re.compile(r"\b(em|com|de|para)\s+(madeira|granito|pedra|reboco|tijolo|betao)(?:\s+aparente)?\b")
_ACAO_ACABAMENTO = re.compile(r"\b(?:met\w*|poe|ponh\w*|coloc\w*|aplic\w*|assent\w*|revest\w*|forr\w*|troc\w*|mud\w*|acabamento)\b")
_PAVIMENTO = re.compile(r"\b(?:pisos?|pavimentos?|chao|lajes?)\b")
_PISO_NOME = re.compile(r"\b(?:piso\s+terreo|res[- ]do[- ]chao|r/c|piso\s+\d+|(?:primeiro|segundo|terceiro)\s+piso)\b")
_PISO_MATERIAIS = {
    "ceramica": r"ceramic[ao]s?|tijoleira|ladrilhos? ceramic[ao]s?",
    "porcelanato": r"porcelanato|gres porcelanico",
    **{key: key for key in PAVIMENTOS if key not in ("ceramica", "porcelanato")},
}
_SAPATA_LINEAR = re.compile(r"\b(?:sapatas?\s+linear(?:es)?|sapatas?\s+corridas?)\b")
_SAPATA_CONTINUA = re.compile(r"(\bao longo\b|\btoda\b[^.;\n]*\b(?:largura|longura|comprimento)\b|\bperimetro\b)")


def mesmas_medidas(a, b):
    def valores(texto):
        return [((m["sinal"] or ""), float(m["valor"].replace(",", ".")), m["unidade"]) for m in _VALOR.finditer(_norm(texto))]

    return valores(a) == valores(b)


def _numero_associado(frase, nome):
    campo = re.search(rf"\b(?:{nome})\s*(?:de\s+|=\s*)?{_NUM}\s*(mm|cm|m)\b", frase)
    if not campo:
        campo = re.search(rf"{_NUM}\s*(mm|cm|m)\s+(?:de\s+)?(?:{nome})\b", frase)
    return _m(campo[1], campo[2]) if campo else None


def alvos_pavimento(m, t, selecao):
    def alias(name):
        return re.sub(r"piso\s+terreo|res[- ]do[- ]chao|r/c", "piso terreo", _norm(name))

    if re.search(r"\b(?:cozinha|sala|quartos?|wc|banheiro|casa de banho|corredor|divisao)\b", t):
        return []
    nome = _PISO_NOME.search(t)
    if nome:
        procurado = alias(nome[0])
        return [s.source_id for s in m.slabs if alias(s.name) == procurado]
    ids = [s.source_id for s in m.slabs if re.search(rf"(?<![\w-]){re.escape(_norm(s.source_id))}(?![\w-])", t)]
    if ids:
        return ids
    if _PAVIMENTO.search(t) and re.search(r"\btod[oa]s?\b", t):
        return [s.source_id for s in m.slabs]
    if selecao and selecao["grupo"] == "slabs":
        return [s.source_id for s in m.slabs if s.source_id == selecao["id"]]
    return [m.slabs[0].source_id] if len(m.slabs) == 1 and _PAVIMENTO.search(t) else []


def interpretar_selecao(texto: str, modelo: BuildingModel, selecao=None):
    """Recognise dimensional commands against the selected, editable BIM element."""
    ops, nao_percebido, esclarecimentos = [], [], []
    texto = re.sub(r"\n\s*(?=(?:a|ao|à|em|nas|na|no|nos|com|para|de)\s)", " ", texto or "", flags=re.I)
    texto = re.sub(r"\b(?:e\s+depois|depois|e)\s+(?=(?:pint|coloc|aplic|revet|revest|mov|desloc|retir|apag|mud|"
                   r"acrescent|aument|reduz|engross|deix|tro[cq]|met|cri|tira|ponh)\w*\b)", "; ", texto, flags=re.I)
    for frase in (f.strip(" .!?") for f in re.split(r"[;\n]|(?<!\d)\.(?!\d)", texto)):
        if not frase:
            continue
        t = _norm(frase)
        if re.match(r"^(?:nao|qual|quais|quanto|quantas|quantos|quero saber|explica)\b", t):
            esclarecimentos.append({"frase": frase, "mensagem": "Indique a alteração a aplicar ao desenho."})
            continue
        material_piso = next((key for key, pattern in _PISO_MATERIAIS.items() if re.search(rf"\b(?:{pattern})\b", t)), None)
        if (material_piso and _ACAO_ACABAMENTO.search(t) and not (_FACHADA.search(t) or re.search(_GRUPOS["walls"], t))
                and (_PAVIMENTO.search(t) or (selecao or {}).get("grupo") == "slabs")):
            ids = alvos_pavimento(modelo, t, selecao)
            espessura = _numero_associado(t, "espessura")
            if not ids:
                esclarecimentos.append({"frase": frase, "mensagem": "O piso indicado não está nesta página ou há vários pavimentos. Abra a página correta ou selecione um pavimento."})
            elif len(list(_VALOR.finditer(t))) > int(espessura is not None):
                esclarecimentos.append({"frase": frase, "mensagem": "Pode indicar a espessura do revestimento. O formato das peças ainda não é editável."})
            else:
                ops.append({"op": "revestimento_piso", "ids": ids, "material": material_piso, "espessura": espessura})
            continue
        if re.search(r"\b(?:pint\w*|colore|muda\w* a cor)\b", t):
            cor = re.search(r"#[0-9a-f]{6}\b", t)
            cores = sorted(CORES_PAREDE, key=len, reverse=True)
            named = next((key for key in cores if re.search(rf"\b{re.escape(key)}\b", t.replace("-", " "))), None)
            if cor or named:
                paredes = list(modelo.walls)
                ids = [w.source_id for w in paredes if re.search(rf"(?<![\w-]){re.escape(_norm(w.source_id))}(?![\w-])", t)]
                fachadas = bool(_FACHADA.search(t) and not re.search(r"\b(?:esta|essa|selecionada)\b", t))
                if not ids and not fachadas and re.search(r"\btodas? as paredes\b", t):
                    ids = [w.source_id for w in paredes]
                if not ids and selecao and selecao["grupo"] == "walls" and not re.search(r"\b(?:piso|chao|laje|porta|janela|teto)\b", t):
                    ids = [selecao["id"]]
                if ids or fachadas:
                    ops.append({"op": "pintar_paredes", "ids": ids, "fachadas": fachadas, "cor": cor[0] if cor else CORES_PAREDE[named]})
                    continue
        if selecao and selecao["grupo"] == "footings":
            if re.search(r"\b(?:quatro|4)\s+cantos\b", t):
                ops.append({"op": "sapatas_quatro_cantos", "id": selecao["id"]})
                continue
            if re.search(r"\blimite\s+(?:da casa|do edificio|da moradia|exterior)\b", t):
                ops.append({"op": "sapata_ate_limite", "id": selecao["id"]})
                continue
        continua = _SAPATA_LINEAR.search(t) or (re.search(r"\bsapatas?\b", t) and _SAPATA_CONTINUA.search(t))
        if continua and re.search(r"\b(?:cri\w*|adicion\w*|coloc\w*|desenh\w*|faz\w*)\b", t):
            exteriores = bool(re.search(r"\b(?:perimetro|fachadas?|faxadas?|paredes?\s+exteriores?)\b", t))
            parede = selecao["id"] if selecao and selecao["grupo"] == "walls" else None
            largura = _numero_associado(t, "largura")
            altura = _numero_associado(t, "altura|espessura|profundidade")
            if (exteriores or parede) and largura is not None and altura is not None:
                ops.append({"op": "sapatas_lineares_criar", "fachadas": exteriores, "parede": parede,
                            "largura": largura, "altura": altura})
            else:
                esclarecimentos.append({"frase": frase, "mensagem":
                    "Selecione uma parede ou indique «paredes exteriores». Indique a largura e a altura, "
                    "por exemplo «criar sapatas lineares nas paredes exteriores com 60 cm de largura e 30 cm de altura»."})
            continue
        material = _MAT.search(t)
        fachada = _FACHADA.search(t)
        if material and (fachada or _REVESTIR.search(t)):
            if fachada and (fachada[0].endswith("s") or not re.search(r"\b(?:esta|essa|selecionada)\b", t)):
                ops.append({"op": "revestimento_paredes", "fachadas": True, "material": material[2]})
                continue
            if selecao and selecao["grupo"] in ("walls", "openings"):
                ident = selecao["id"]
                if selecao["grupo"] == "openings":
                    vao = next((v for v in modelo.openings if v.source_id == ident), None)
                    ident = vao.wall_id if vao else None
                if ident:
                    ops.append({"op": "revestimento_paredes", "id": ident, "material": material[2]})
                    continue
        if selecao:
            grupo_selecao = selecao["grupo"]
            id_selecao = selecao["id"]
            apagar = re.fullmatch(r"(?:apaga|remove|elimina|tira)\w*\s+(?:esta|este|a|o)\s+(parede|vao|porta|janela)(?:\s+selecionad[ao])?", t)
            if apagar and (grupo_selecao == ("walls" if apagar[1] == "parede" else "openings")):
                ops.append({"op": "parede_apagar" if grupo_selecao == "walls" else "vao_apagar", "id": id_selecao})
                continue
            mover = re.fullmatch(
                rf"(?:move|desloca|empurra)\w*\s+(?:(?:esta|a)\s+parede(?:\s+selecionada)?\s+)?"
                rf"(?:em\s+)?{_NUM}\s*(mm|cm|m)\s+para\s+(?:a\s+|o\s+)?(direita|esquerda|cima|baixo|norte|sul|este|leste|oeste)", t)
            if mover and grupo_selecao == "walls":
                direction = {"direita": (1, 0), "este": (1, 0), "leste": (1, 0), "esquerda": (-1, 0), "oeste": (-1, 0),
                             "cima": (0, 1), "norte": (0, 1), "baixo": (0, -1), "sul": (0, -1)}
                d = _m(mover[1], mover[2])
                dx, dy = direction[mover[3]]
                ops.append({"op": "parede_mover", "id": id_selecao, "dx": dx * d, "dy": dy * d})
                continue
        medida = _MEDIDA.search(t)
        grupos = [g for g, pattern in _GRUPOS.items() if re.search(pattern, t)]
        if not medida or len(grupos) > 1 or "pe-direito" in t or "pe direito" in t:
            antigos, resto = interpretar(frase, modelo)
            ops.extend(antigos)
            nao_percebido.extend(resto)
            continue

        grupo = (grupos or [selecao["grupo"] if selecao else None])[0]
        if not grupo:
            antigos, resto = interpretar(frase, modelo)
            ops.extend(antigos)
            nao_percebido.extend(resto)
            continue

        atributo = DIMENSOES[grupo].get(medida[1])
        if not atributo:
            esclarecimentos.append({"frase": frase, "mensagem": f"A dimensão «{medida[1]}» não é editável para este tipo de elemento."})
            continue
        disponiveis = {item.source_id: item for item in getattr(modelo, grupo)}
        id_explicito = next((sid for sid in disponiveis if re.search(
            rf"(?<![\w-]){re.escape(_norm(sid))}(?![\w-])", t)), None)
        if id_explicito:
            ids = [id_explicito]
        elif re.search(r"\btod[ao]s?\b", t) and grupos:
            ids = list(disponiveis)
        elif selecao and selecao["grupo"] == grupo and selecao["id"] in disponiveis:
            ids = [selecao["id"]]
        else:
            ids = []
        if not ids:
            esclarecimentos.append({"frase": frase, "mensagem": "Selecione o elemento no desenho ou indique o seu identificador. Use «todas» para editar o grupo."})
            continue

        medidas = list(_VALOR.finditer(t))
        if len(medidas) > 1:
            esclarecimentos.append({"frase": frase, "mensagem": "Indique uma medida por frase."})
            continue
        metrica = medidas[0] if medidas else None
        aumentar = bool(re.search(r"\b(?:aument\w*|along\w*|alarg\w*)\b", t))
        diminuir = bool(re.search(r"\b(?:diminu\w*|reduz\w*|encurt\w*)\b", t))
        if not metrica:
            exemplo = "20 cm" if aumentar or diminuir else "para 1,80 m"
            esclarecimentos.append({"frase": frase, "pedir_medida": True,
                                    "mensagem": f"Que medida quer aplicar? Pode responder «{exemplo}»."})
            continue
        unidade = metrica["unidade"]
        qual = (metrica["qual"] or "").strip()
        sinal = -1 if metrica["sinal"] == "-" or (diminuir and not metrica["sinal"]) else 1
        relativa = metrica["sinal"] or qual in ("em", "por") or ((aumentar or diminuir) and qual != "para")
        modo = "percentagem" if unidade == "%" else "relativo" if relativa else "absoluto"
        valor = sinal * _m(metrica["valor"], unidade) if modo != "absoluto" else _m(metrica["valor"], unidade)
        ops.append({"op": "elementos_redimensionar", "grupo": grupo, "ids": ids, "dimensao": medida[1],
                    "modo": modo, "valor": valor})
    return ops, nao_percebido, esclarecimentos
