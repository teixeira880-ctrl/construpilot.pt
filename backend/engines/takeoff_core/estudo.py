"""One study for any building: geometry → quantities with their origin → cross-checks → prices → dossier.

The same steps, in the same order, for every company and every construction system:

1. heights: what the plan gives, otherwise the standard heights (RDC 3.00 m, other floors 2.50 m), marked "standard";
2. network: wall ends joined onto the other wall's axis, runs joined over lintels (drawn, or inferred from gaps);
3. pieces: L/T/X junctions resolved without double count, split at the production format of prefabricated systems;
4. quantities: per system rule (sistemas.py), each with its origin and sources;
5. cross-checks: two independent methods must agree within the tolerance (2 % by default);
6. prices: company library, each price with its source; a quantity without price stays visible as "sem preço".
"""
from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from . import rede, sistemas

SystemId = Literal["clt", "alvenaria_tijolo", "alvenaria_bloco", "betao_armado", "ossatura_madeira", "ossatura_metalica",
                   "divisoria_gesso"]
Coord = Annotated[float, Field(ge=-100_000, le=100_000, allow_inf_nan=False)]

# Standard VAT rates (published law). The company can override them in the project.
VAT = {"PT": (23.0, "CIVA art. 18.º, n.º 1, al. c) (taxa normal 23 %)"),
       "FR": (20.0, "CGI art. 278 (taux normal 20 %)"),
       "UA": (20.0, "Податковий кодекс України, ст. 193.1 (ПДВ 20 %)")}


class WallIn(BaseModel):
    id: str = Field(min_length=1, max_length=40)
    x1: Coord
    y1: Coord
    x2: Coord
    y2: Coord
    thickness_mm: Annotated[float, Field(gt=0, le=1500, allow_inf_nan=False)]
    height_m: Annotated[float, Field(gt=0, le=20, allow_inf_nan=False)] | None = None
    base_z_m: float = Field(default=0.0, ge=-50, le=500, allow_inf_nan=False)
    layers: Annotated[int, Field(ge=1, le=13)] | None = None
    sistema: SystemId | None = None
    openings: list[rede.Opening] = Field(default_factory=list, max_length=40)
    source: str = Field(default="", max_length=200)


class LintelIn(BaseModel):
    ref: str = Field(min_length=1, max_length=40)
    rect_m: list[Coord] = Field(min_length=4, max_length=4)
    head_m: Annotated[float, Field(gt=0, le=20, allow_inf_nan=False)]
    thickness_mm: Annotated[float, Field(gt=0, le=1500, allow_inf_nan=False)] | None = None


class RoomIn(BaseModel):
    nome: str = Field(min_length=1, max_length=60)
    poligono: list[tuple[Coord, Coord]] = Field(min_length=3, max_length=500)


class FloorIn(BaseModel):
    nome: str = Field(min_length=1, max_length=60)
    nivel: int = Field(default=0, ge=-5, le=60, description="0 = rés-do-chão; o standard de altura depende dele")
    elevation_m: float = Field(default=0.0, ge=-50, le=500, allow_inf_nan=False)
    altura_m: Annotated[float, Field(gt=0, le=20, allow_inf_nan=False)] | None = Field(
        default=None, description="altura estrutural lida no corte; vazio = altura standard")
    altura_fonte: str = Field(default="", max_length=200)
    paredes: list[WallIn] = Field(min_length=1, max_length=500)
    linteis: list[LintelIn] = Field(default_factory=list, max_length=500)
    divisoes: list[RoomIn] = Field(default_factory=list, max_length=200)
    ligar: bool = True
    inferir_vaos: bool = False
    leitura: Literal["vetorial", "manual", "imagem", "dxf"] = "manual"


class Project(BaseModel):
    nome: str = Field(default="Estudo", min_length=1, max_length=80)
    pais: Literal["PT", "FR", "UA"] = "PT"
    sistema: SystemId = "alvenaria_tijolo"
    pisos: list[FloorIn] = Field(min_length=1, max_length=20)
    iva_pct: Annotated[float, Field(ge=0, le=50)] | None = None
    iva_fonte: str = Field(default="", max_length=200)

    @model_validator(mode="after")
    def unique(self):
        if len({f.nome for f in self.pisos}) != len(self.pisos):
            raise ValueError("Cada piso deve ter um nome único.")
        ids = [w.id for f in self.pisos for w in f.paredes]
        if len(set(ids)) != len(ids):
            raise ValueError("Os identificadores das paredes devem ser únicos em todo o projeto.")
        return self


class PriceItem(BaseModel):
    codigo: str = Field(min_length=1, max_length=60)
    sistema: SystemId | None = None
    preco_unitario: Annotated[float, Field(ge=0, le=10_000_000, allow_inf_nan=False)]
    unidade: str = Field(min_length=1, max_length=12)
    fonte: str = Field(min_length=1, max_length=200)
    moeda: str = Field(default="EUR", max_length=3)

    @field_validator("unidade")
    @classmethod
    def unit(cls, v):
        return {"m2": "m²", "m3": "m³", "ml": "m", "u": "un", "unid": "un"}.get(v.strip().lower(), v.strip())


def _height(floor: FloorIn, params):
    if floor.altura_m:
        return floor.altura_m, "medido", floor.altura_fonte or "altura indicada no projeto"
    key = "geral.altura_standard_rdc_m" if floor.nivel <= 0 else "geral.altura_standard_pisos_m"
    return params[key]["valor"], params[key]["origem"], params[key]["fonte"]


def _walls(floor: FloorIn, default_system, params):
    h, h_origin, h_source = _height(floor, params)
    out = []
    for w in floor.paredes:
        sid = w.sistema or default_system
        layers = w.layers or (int(params["clt.clt_camadas"]["valor"]) if sid == "clt" else None)
        out.append(rede.WallAxis(id=w.id, x1=w.x1, y1=w.y1, x2=w.x2, y2=w.y2, thickness_mm=w.thickness_mm, layers=layers,
                                 height_m=w.height_m or h, base_z_m=w.base_z_m, openings=w.openings,
                                 source=w.source, sistema=sid, height_origin="medido" if w.height_m else h_origin))
    return out, {"valor_m": h, "origem": h_origin, "fonte": h_source}


def _limits(walls, params):
    length, height = {}, {}
    for w in walls:
        if w.sistema == "clt":
            length[w.id] = params["clt.clt_comprimento_max_m"]["valor"]
            height[w.id] = params["clt.clt_largura_max_m"]["valor"]
        elif w.sistema in ("ossatura_madeira", "ossatura_metalica"):
            length[w.id] = params[f"{w.sistema}.comprimento_max_m"]["valor"]
    return length, height


def _money(x):
    return float(Decimal(str(x)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def price(rows, library, vat_pct, vat_source):
    """Lines of the estimate: each quantity row with a library price of the same code and unit (system-specific price
    first). Rows without a price are listed, never priced silently."""
    lib = {}
    for item in library or []:
        lib[(item.codigo, item.sistema)] = item
    lines, missing = [], []
    for r in rows:
        item = lib.get((r["codigo"], r["sistema"])) or lib.get((r["codigo"], None))
        if not item:
            missing.append({"codigo": r["codigo"], "sistema": r["sistema"], "piso": r["piso"], "unidade": r["unidade"]})
            continue
        if item.unidade != r["unidade"]:
            missing.append({"codigo": r["codigo"], "sistema": r["sistema"], "piso": r["piso"], "unidade": r["unidade"],
                            "motivo": f"unidade do preço {item.unidade} ≠ {r['unidade']}"})
            continue
        lines.append({**{k: r[k] for k in ("codigo", "sistema", "piso", "quantidade", "unidade", "origem")},
                      "preco_unitario": item.preco_unitario, "moeda": item.moeda, "fonte_preco": item.fonte,
                      "total": _money(r["quantidade"] * item.preco_unitario)})
    subtotal = _money(sum(line["total"] for line in lines))
    vat = _money(subtotal * vat_pct / 100)
    return {"linhas": lines, "sem_preco": missing, "subtotal": subtotal, "iva_pct": vat_pct, "iva_fonte": vat_source,
            "iva": vat, "total": _money(subtotal + vat),
            "parte_estimativa": _money(sum(line["total"] for line in lines if line["origem"] in sistemas.UNCERTAIN))}


def run(project: Project, company_params: dict | None = None, library: list[PriceItem] | None = None):
    params = sistemas.merged(company_params)
    tol = params["geral.tolerancia_verificacao_pct"]["valor"] / 100
    floors, all_rows, checks, networks = [], [], [], []
    for f in project.pisos:
        walls, height = _walls(f, project.sistema, params)
        lintels = [li.model_dump() for li in f.linteis]
        inferred = []
        if f.inferir_vaos:
            inferred = rede.gaps_as_openings(walls, min_m=params["geral.vao_inferido_min_m"]["valor"],
                                             max_m=params["geral.vao_inferido_max_m"]["valor"],
                                             head_m=params["geral.altura_vao_standard_m"]["valor"])
        net = None
        if f.ligar or lintels or inferred:
            walls, net = rede.connect(walls, lintels=lintels + inferred)
        length, heightcap = _limits(walls, params)
        analysis = rede.analyse(rede.Floor(name=f.nome, walls=walls), length or None, heightcap or None)
        by_wall = {w.id: w for w in walls}
        img = f.leitura == "imagem"
        rows = []
        for sid in sorted({w.sistema for w in walls}):
            sys_pieces = [p for p in analysis["pecas"] if by_wall[p["parede"]].sistema == sid]
            origins = {by_wall[p["parede"]].height_origin for p in sys_pieces}
            if any(str(o.get("label", "")).startswith("inferido") for p in sys_pieces for o in p["vaos"]):
                origins.add("inferido")
            origins.add("estimativa_imagem" if img else "medido")
            rows += sistemas.wall_rows(sid, sys_pieces, [w for w in walls if w.sistema == sid], params, f.nome,
                                       sistemas.combine(*origins))
        rows += sistemas.opening_rows(analysis["pecas"], f.nome)
        rows += sistemas.room_rows([r.model_dump() for r in f.divisoes], f.nome)
        t = analysis["totais"]
        area_check = rede.reconciliation(t["area_bruta_m2"] - t["area_vaos_m2"], t["area_liquida_m2"], zero_tolerance=1e-6, tolerance=tol)
        vol_check = rede.reconciliation(analysis["metodos"]["volume_pecas_m3"], analysis["metodos"]["volume_uniao_planta_m3"],
                                        zero_tolerance=1e-6, tolerance=tol)
        checks += [
            {"piso": f.nome, "verificacao": "volume_pecas_vs_uniao", "a": analysis["metodos"]["volume_pecas_m3"],
             "b": analysis["metodos"]["volume_uniao_planta_m3"], "unidade": "m³", **_check(vol_check)},
            {"piso": f.nome, "verificacao": "area_bruta_menos_vaos", "a": round(t["area_bruta_m2"] - t["area_vaos_m2"], 4),
             "b": t["area_liquida_m2"], "unidade": "m²", **_check(area_check)},
            {"piso": f.nome, "verificacao": "eixos_vs_pecas", "a": analysis["metodos"]["eixos_desenhados_m"],
             "b": analysis["metodos"]["pecas_producao_m"], "unidade": "m", "passou": True, "informativo": True,
             "erro_pct": _pct(analysis["metodos"]["pecas_producao_m"], analysis["metodos"]["eixos_desenhados_m"]),
             "nota": f"diferença = sobreposição nas juntas (contagem dupla evitada {analysis['contagem_dupla_evitada_m3']:.3f} m³)"},
        ]
        floors.append({"nome": f.nome, "nivel": f.nivel, "elevation_m": f.elevation_m, "altura": height, "leitura": f.leitura,
                       "analise": analysis, "rede": net, "vaos_inferidos": inferred, "linhas": rows})
        networks.append((f.nome, walls, analysis["pecas"]))
        all_rows += rows
    totals = {}
    for r in all_rows:
        key = (r["codigo"], r["sistema"], r["unidade"])
        t = totals.setdefault(key, {"codigo": r["codigo"], "sistema": r["sistema"], "unidade": r["unidade"], "quantidade": 0.0,
                                    "origens": set(), "fontes": []})
        t["quantidade"] += r["quantidade"]
        t["origens"].add(r["origem"])
        t["fontes"] += [s for s in r["fontes"] if s not in t["fontes"]]
    total_rows = [{**{k: v for k, v in t.items() if k != "origens"}, "quantidade": round(t["quantidade"], 4),
                   "origem": sistemas.combine(*t["origens"])} for t in totals.values()]
    vat_pct, vat_source = (project.iva_pct, project.iva_fonte or "valor indicado pela empresa") if project.iva_pct is not None \
        else VAT[project.pais]
    budget = price(all_rows, library, vat_pct, vat_source) if library else None
    used = {w.sistema for _n, walls, _p in networks for w in walls}
    hypotheses = [{"chave": k, **v} for k, v in params.items()
                  if v["origem"] in ("hipotese", "standard") and (k.startswith("geral.") or k.split(".")[0] in used)]
    return {"projeto": project.nome, "pais": project.pais, "sistema": project.sistema, "sistemas_usados": sorted(used),
            "pisos": floors, "totais": total_rows, "verificacoes": checks,
            "verificacoes_ok": all(c["passou"] for c in checks), "hipoteses": hypotheses, "parametros": params,
            "orcamento": budget, "_redes": networks}


def _check(c):
    return {"passou": c["passed"], "erro_pct": round(c["error_percent"], 4) if c["error_percent"] is not None else None,
            "limite": round(c["limit"], 6)}


def _pct(a, b):
    return round(abs(a - b) / b * 100, 3) if b else None


def public(result):
    """The result without the in-memory wall objects (JSON-safe)."""
    return {k: v for k, v in result.items() if not k.startswith("_")}
