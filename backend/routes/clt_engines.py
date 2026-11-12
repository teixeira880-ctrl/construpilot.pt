"""CLT engines: wall network, cutting plan, IFC model and fabrication drawings."""
from __future__ import annotations

import asyncio
import hashlib
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, Field, model_validator

from bim_studio.clt_nesting import NestingInput
from bim_studio.clt_walls import WallAxis
from routes.clt_industrial import _upload, editor, viewer

router = APIRouter(prefix="/clt-industrial/motores", tags=["clt-industrial"])


class EngineLintel(BaseModel):
    ref: str = Field(min_length=1, max_length=40)
    rect_m: list[Annotated[float, Field(ge=-100_000, le=100_000, allow_inf_nan=False)]] = Field(min_length=4, max_length=4)
    head_m: Annotated[float, Field(gt=0, le=20, allow_inf_nan=False)]
    thickness_mm: Annotated[float, Field(gt=0, le=500, allow_inf_nan=False)] | None = None


class EngineFloor(BaseModel):
    name: str = Field(min_length=1, max_length=60)
    elevation_m: float = Field(default=0.0, ge=-50, le=500, allow_inf_nan=False)
    walls: list[WallAxis] = Field(min_length=1, max_length=500)
    lintels: list[EngineLintel] = Field(default_factory=list, max_length=500)
    # heal the network read from a drawing: ends onto the other wall's axis, runs joined over the lintels
    connect: bool = True


class Slab(BaseModel):
    name: str = Field(min_length=1, max_length=60)
    storey: str = Field(min_length=1, max_length=60)
    polygon: list[tuple[float, float]] = Field(min_length=3, max_length=500)
    thickness_mm: Annotated[float, Field(gt=0, le=500)]
    elevation_m: float = Field(ge=-50, le=500, allow_inf_nan=False)
    source: str = Field(default="", max_length=200)


class CuttingOptions(BaseModel):
    blank_length_m: Annotated[float, Field(gt=0, le=40)] = 18.0
    blank_width_m: Annotated[float, Field(gt=0, le=6)] = 3.5
    kerf_mm: Annotated[float, Field(ge=0, le=50)] = 10.0
    allow_rotation: bool = False
    variable_length: bool = True
    variable_width: bool = False
    time_limit_s: Annotated[float, Field(gt=0, le=30)] = 8.0


class Project(BaseModel):
    name: str = Field(default="ConstruPilot CLT", min_length=1, max_length=80)
    floors: list[EngineFloor] = Field(min_length=1, max_length=10)
    slabs: list[Slab] = Field(default_factory=list, max_length=20)
    cutting: CuttingOptions = Field(default_factory=CuttingOptions)

    @model_validator(mode="after")
    def unique(self):
        if len({f.name for f in self.floors}) != len(self.floors):
            raise ValueError("Cada piso deve ter um nome único.")
        ids = [w.id for f in self.floors for w in f.walls]
        if len(set(ids)) != len(ids):
            raise ValueError("Os identificadores das paredes devem ser únicos em todo o projeto.")
        if any(s.storey not in {f.name for f in self.floors} for s in self.slabs):
            raise ValueError("Cada laje deve indicar um piso existente.")
        return self


def _run(body: Project, *, ifc=False, drawings=False):
    from bim_studio import clt_nesting, clt_walls

    networks = [clt_walls.connect(f.walls, lintels=[li.model_dump() for li in f.lintels]) if f.connect else (f.walls, None)
                for f in body.floors]
    analyses = [clt_walls.analyse(clt_walls.Floor(name=f.name, walls=walls), body.cutting.blank_length_m)
                for f, (walls, _net) in zip(body.floors, networks)]
    for a, (_walls, net) in zip(analyses, networks):
        a["rede"] = net
    pieces = [p for a in analyses for p in clt_nesting.pieces_from_walls(a)]
    nesting = clt_nesting.plan(NestingInput(pieces=pieces, **body.cutting.model_dump()))
    out = {"pisos": analyses, "corte": nesting}
    staged = [(f.name, f.elevation_m, walls, a["pecas"]) for f, (walls, _net), a in zip(body.floors, networks, analyses)]
    if ifc:
        from bim_studio import clt_ifc

        data, check = clt_ifc.build(staged, project_name=body.name, slabs=[s.model_dump() for s in body.slabs])
        out["ifc"], out["verificacao_3d"] = data, check
    if drawings:
        from bim_studio import clt_drawings

        out["desenhos"] = clt_drawings.build([(n, w, p) for n, _, w, p in staged], nesting, title=body.name)
    return out


async def _safe(fn, *args, **kwargs):
    try:
        return await asyncio.to_thread(fn, *args, **kwargs)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.post("/analise")
async def full_analysis(body: Project, user=Depends(viewer)):
    """Walls, junctions, production pieces, cutting plan and 3D volume check."""
    result = await _safe(_run, body, ifc=True)
    ifc = result.pop("ifc")
    totals = {
        "volume_bruto_m3": round(sum(a["totais"]["volume_bruto_m3"] for a in result["pisos"]), 4),
        "volume_liquido_m3": round(sum(a["totais"]["volume_liquido_m3"] for a in result["pisos"]), 4),
        "volume_paineis_m3": result["corte"]["total"]["volume_paineis_m3"],
        "paineis": result["corte"]["total"]["paineis"],
        "desperdicio_percent": result["corte"]["total"]["desperdicio_percent"],
        "juntas_parede_m": round(sum(a["totais"]["juntas_parede_m"] for a in result["pisos"]), 4),
        "contagem_dupla_evitada_m3": round(sum(a["contagem_dupla_evitada_m3"] for a in result["pisos"]), 5),
    }
    checks = {
        "pecas_vs_planta": all(a["verificacao_volume"]["passed"] for a in result["pisos"]),
        "ifc_opencascade": result["verificacao_3d"]["passed"],
    }
    return {**result, "total": totals, "verificacoes": checks, "ifc_sha256": hashlib.sha256(ifc).hexdigest(),
            "estado": "medido" if all(checks.values()) else "rever"}


@router.post("/ifc")
async def ifc_model(body: Project, user=Depends(viewer)):
    result = await _safe(_run, body, ifc=True)
    if not result["verificacao_3d"]["passed"]:
        raise HTTPException(422, "O modelo 3D não confere com as quantidades (erro acima de 2 %).")
    return Response(result["ifc"], media_type="application/x-step",
                    headers={"Content-Disposition": 'attachment; filename="construpilot-clt.ifc"'})


@router.post("/desenhos")
async def fabrication_drawings(body: Project, formato: Literal["pdf", "dxf"] = "pdf", user=Depends(viewer)):
    result = await _safe(_run, body, drawings=True)
    data = result["desenhos"][formato]
    media = "application/pdf" if formato == "pdf" else "application/dxf"
    return Response(data, media_type=media,
                    headers={"Content-Disposition": f'attachment; filename="construpilot-clt-fabrico.{formato}"'})


@router.post("/pdf-paredes")
async def pdf_walls(
    file: UploadFile = File(...),
    page: int = Form(..., ge=1, le=60),
    height_m: float = Form(..., gt=0, le=3.5),
    scale: int | None = Form(None, ge=10, le=500),
    colour: str | None = Form(None, pattern=r"^#[0-9a-fA-F]{6}$"),
    lintel_colour: str | None = Form(None, pattern=r"^#[0-9a-fA-F]{6}$"),
    layers: int = Form(5, ge=3, le=13),
    user=Depends(editor),
):
    from fitz import FileDataError

    from bim_studio.clt_pdf_walls import detect

    data = await _upload(file)
    try:
        result = await asyncio.to_thread(detect, data, page, scale=scale, height_m=height_m, layers=layers, colour=colour,
                                         lintel_colour=lintel_colour)
    except FileDataError as exc:
        raise HTTPException(422, "PDF inválido.") from exc
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    return {**result, "sha256": hashlib.sha256(data).hexdigest()}
