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


def _op(m: BuildingModel, o: dict) -> str:
    op = o.get("op")
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
        return f"Parede «{w.source_id}» deslocada {dx:+.2f} m em x e {dy:+.2f} m em y."
    if op == "parede_apagar":
        w = _parede(m, o["id"])
        n = sum(1 for v in m.openings if v.wall_id == w.source_id)
        m.walls.remove(w)
        m.openings[:] = [v for v in m.openings if v.wall_id != w.source_id]
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
