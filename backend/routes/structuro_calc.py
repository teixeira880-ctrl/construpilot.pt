"""Versioned structural mechanics under existing Pro and tenant permissions."""
import asyncio
import io
import json
import uuid
import zipfile
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import Field, ValidationError
from core.db import db
from core.security import current_user
from engines.access import require_level
from engines.structuro_calc import StrictModel, Model, Action, calculate, example
from engines.structuro_calc_exports import build_pdf, build_dxf
from engines import structuro_pc
from engines import structuro_eurocode as eurocode
from engines import structuro_ec2 as ec2
from engines import structuro_ec7 as ec7
from engines import structuro_ec3 as ec3
from engines import structuro_ec5 as ec5
from engines import structuro_sls as sls
from engines import structuro_crack as crack
from engines import structuro_anchorage as anchorage
from engines import structuro_lintel as lintel
from engines.structuro_ec_exports import build_ferraillage_pdf, build_dossier_pdf
from engines.structuro_lintel_export import build_lintel_pdf, build_lintel_dxf
from engines.structuro_rebar_exports import build_rebar_pdf
from engines.structuro_drawings import compile_dossier
from engines.structuro_drawing_exports import build_drawing_pdf, build_schedule_csv, build_scene, scene_svg
from engines.structuro_automation import run_automation

router=APIRouter(prefix="/structuro/calc",tags=["structuro-calc"],dependencies=[Depends(require_level("pro"))])


def now():
    return datetime.now(timezone.utc).isoformat()


async def owned(study_id,user):
    s=await db.structuro_calculations.find_one({"study_id":study_id,"user_id":user["user_id"]},{"_id":0})
    if not s: raise HTTPException(404,"Estudo não encontrado")
    return s


async def source_plan(s,user):
    if not s.get("plan_id"): return None
    p=await db.plans_takeoff.find_one({"plan_id":s["plan_id"],"user_id":user["user_id"]},{"_id":0})
    if not p: raise HTTPException(404,"Projeto de origem não encontrado")
    if p.get("updated_at")!=s.get("source_updated_at"):
        raise HTTPException(409,"O projeto de origem mudou. Crie um novo estudo a partir da sua versão atual.")
    return p


class CreateIn(StrictModel):
    plan_id: str | None = Field(default=None,max_length=100)
    demonstration: bool = False
    drawing_demonstration: bool = False
    automation_demonstration: bool = False


class SaveIn(StrictModel):
    expected_revision: int = Field(ge=1)
    model: Model


class ReadIn(StrictModel):
    expected_revision: int = Field(ge=1)
    page: int = Field(ge=1,le=10000)


class ImportIn(StrictModel):
    model: Model


@router.post("/import")
async def import_model(body:ImportIn,user=Depends(current_user)):
    """Import data, never imported results, ownership or an engineering visa."""
    model=body.model;auto_report=None
    if model.automation_settings is not None:
        model=model.model_copy(deep=True);model.automation_generated_hash=None
        model,auto_report=await asyncio.to_thread(run_automation,model)
    s={"study_id":"strcalc_"+uuid.uuid4().hex,"user_id":user["user_id"],"revision":1,
       "plan_id":None,"source_updated_at":None,"page_count":0,"page_readings":{},
       "model":model.model_dump(),"result":await asyncio.to_thread(calculate,model),"automation_result":auto_report,
       "created_at":now(),"updated_at":now()}
    await db.structuro_calculations.insert_one(dict(s))
    return s


@router.get("/schema")
async def schema(user=Depends(current_user)):
    return Model.model_json_schema()


@router.get("/studies")
async def list_studies(user=Depends(current_user)):
    rows=await db.structuro_calculations.find({"user_id":user["user_id"]},
        {"_id":0,"study_id":1,"revision":1,"model.title":1,"updated_at":1,"plan_id":1}).sort("updated_at",-1).to_list(100)
    return {"studies":rows}


@router.post("/studies")
async def create(body:CreateIn,user=Depends(current_user)):
    demos=(body.demonstration,body.drawing_demonstration,body.automation_demonstration)
    if body.plan_id and any(demos): raise HTTPException(422,"Um exemplo não pode ser associado a um projeto real")
    if sum(demos)>1: raise HTTPException(422,"Escolher um único exemplo")
    plan=None
    if body.plan_id:
        plan=await db.plans_takeoff.find_one({"plan_id":body.plan_id,"user_id":user["user_id"]},{"_id":0})
        if not plan: raise HTTPException(404,"Projeto não encontrado")
    model=example() if body.demonstration else Model(
        title=(plan.get("filename") or "Estudo de estruturas")[:160] if plan else "Estudo de estruturas",
        actions=[Action(id="G",kind="G",label="Permanentes"),Action(id="Q",kind="Q",label="Exploitation")],self_weight_action="G")
    if body.drawing_demonstration:
        from engines.structuro_drawing_example import drawing_example
        model=drawing_example()
    if body.automation_demonstration:
        from engines.structuro_drawing_example import automation_example
        model=automation_example()
    s={"study_id":"strcalc_"+uuid.uuid4().hex,"user_id":user["user_id"],"revision":1,
       "plan_id":body.plan_id,"source_updated_at":plan.get("updated_at") if plan else None,
       "page_count":len(plan.get("pages") or []) if plan else 0,"page_readings":{},
       "model":model.model_dump(),"result":calculate(model),"created_at":now(),"updated_at":now()}
    await db.structuro_calculations.insert_one(dict(s))
    return s


@router.get("/studies/{study_id}")
async def get(study_id:str,user=Depends(current_user)):
    s=await owned(study_id,user)
    try:
        await source_plan(s,user)
    except HTTPException as exc:
        if exc.status_code not in (404,409): raise
        s["source_stale"]=True
        s["automation_result"]=None
        s["result"]={**s["result"],"status":"blocked","cases":[],"quantities":[],"reinforcement":None,"linked_reinforcement":None,"architectural_compatibility":None,
                     "issues":[{"element":None,"message":str(exc.detail)}]}
    return s


@router.put("/studies/{study_id}")
async def save(study_id:str,body:SaveIn,user=Depends(current_user)):
    s=await owned(study_id,user)
    await source_plan(s,user)
    if s["revision"]!=body.expected_revision: raise HTTPException(409,"Estudo modificado; recarregue antes de guardar")
    model=body.model;auto_report=None
    if model.automation_settings and model.automation_settings.confirmed and model.automation_settings.regenerate_on_save:
        model,auto_report=await asyncio.to_thread(run_automation,model)
    result=await asyncio.to_thread(calculate,model)
    patch={"model":model.model_dump(),"result":result,"revision":s["revision"]+1,"updated_at":now(),
           "last_editor":user["user_id"],"automation_result":auto_report}
    changed=await db.structuro_calculations.update_one({"study_id":study_id,"user_id":user["user_id"],"revision":body.expected_revision},{"$set":patch})
    if not changed.matched_count: raise HTTPException(409,"Modificação concorrente; recarregue")
    return {**s,**patch}


@router.post("/studies/{study_id}/read-page")
async def read_page(study_id:str,body:ReadIn,user=Depends(current_user)):
    s=await owned(study_id,user)
    p=await source_plan(s,user)
    if not p: raise HTTPException(422,"Associe um projeto a este estudo")
    pages=p.get("pages") or []
    if body.page>len(pages): raise HTTPException(422,"Página fora do documento")
    if s["revision"]!=body.expected_revision: raise HTTPException(409,"Estudo modificado; recarregue")
    previous=(s.get("page_readings") or {}).get(str(body.page))
    if previous: return s  # idempotent; no repeat paid call or duplicate elements
    try:
        reading=await asyncio.wait_for(structuro_pc.read_page(pages[body.page-1],body.page,p.get("filename") or "PC"),timeout=85)
    except (ValueError,ValidationError):
        raise HTTPException(422,"Leitura inutilizável; nenhum dado foi acrescentado") from None
    except asyncio.TimeoutError:
        raise HTTPException(504,"Leitura demasiado longa; a página continua por analisar") from None
    except Exception:
        raise HTTPException(502,"Leitura IA indisponível; os dados existentes são conservados") from None
    # Store candidates independently: user must select and deduplicate across sheets.
    patch={f"page_readings.{body.page}":reading,"revision":s["revision"]+1,"updated_at":now()}
    await source_plan(s,user)  # source may have changed while the provider was reading
    changed=await db.structuro_calculations.update_one({"study_id":study_id,"user_id":user["user_id"],"revision":body.expected_revision},{"$set":patch})
    if not changed.matched_count: raise HTTPException(409,"Estudo modificado durante a leitura; recarregue")
    return await owned(study_id,user)


@router.get("/combinations/catalog")
async def combinations_catalog(user=Depends(current_user)):
    return eurocode.catalog()


class GenCombosIn(StrictModel):
    expected_revision: int = Field(ge=1)
    categories: dict[str, str] = Field(default_factory=dict)
    options: dict[str, bool] = Field(default_factory=dict)
    psi_overrides: dict[str, dict] = Field(default_factory=dict)
    apply: bool = True
    replace_generated: bool = True


@router.post("/studies/{study_id}/combinations/generate")
async def generate_combinations(study_id: str, body: GenCombosIn, user=Depends(current_user)):
    s = await owned(study_id, user)
    await source_plan(s, user)
    if s["revision"] != body.expected_revision:
        raise HTTPException(409, "Estudo modificado; recarregue antes de gerar")
    model = Model.model_validate(s["model"])
    generated = eurocode.generate(model.actions, body.categories, body.options, body.psi_overrides)
    proposal = [c.model_dump() for c in generated]
    if not body.apply:
        return {"generated": proposal, "applied": False, "catalog": eurocode.catalog()}
    kept = [c for c in model.combinations
            if not (eurocode.is_uls(c.id) or eurocode.is_sls(c.id))] if body.replace_generated else list(model.combinations)
    merged = kept + generated
    if len(merged) > 12:
        raise HTTPException(422, "Demasiadas combinações (máximo 12). Reduza os casos variáveis ou desative uma classe (p. ex. ELS frequente).")
    model.combinations = merged
    model = Model.model_validate(model.model_dump())
    result = await asyncio.to_thread(calculate, model)
    patch = {"model": model.model_dump(), "result": result, "revision": s["revision"] + 1,
             "updated_at": now(), "last_editor": user["user_id"]}
    changed = await db.structuro_calculations.update_one(
        {"study_id": study_id, "user_id": user["user_id"], "revision": body.expected_revision}, {"$set": patch})
    if not changed.matched_count:
        raise HTTPException(409, "Modificação concorrente; recarregue")
    return {"generated": proposal, "applied": True, "study": {**s, **patch}}


@router.get("/studies/{study_id}/design")
async def design(study_id: str, user=Depends(current_user)):
    s = await owned(study_id, user)
    try:
        await source_plan(s, user)
    except HTTPException as exc:
        if exc.status_code not in (404, 409):
            raise
    return eurocode.design_envelope(s.get("result") or {})


@router.get("/ec2/catalog")
async def ec2_catalog(user=Depends(current_user)):
    return ec2.materials_catalog()


class Ec2RebarIn(StrictModel):
    med_knm: float = Field(ge=0, le=1e6)
    ved_kn: float = Field(default=0.0, ge=0, le=1e6)
    b_m: float = Field(gt=0, le=20)
    h_m: float = Field(gt=0, le=20)
    d_m: float = Field(gt=0, le=20)
    d_prime_m: float = Field(default=0.05, ge=0, le=5)
    fck: float = Field(default=25, gt=0, le=90)
    fyk: float = Field(default=500, gt=0, le=700)
    gamma_c: float = Field(default=1.5, ge=1, le=2)
    gamma_s: float = Field(default=1.15, ge=1, le=2)
    alpha_cc: float = Field(default=1.0, gt=0, le=1.5)
    cot_theta: float = Field(default=2.5, ge=1, le=2.5)


@router.post("/ec2/rebar")
async def ec2_rebar(body: Ec2RebarIn, user=Depends(current_user)):
    """Ferraillage d'une section isolée (M/V saisis à la main)."""
    try:
        return ec2.design_section(**body.model_dump())
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from None


class Ec2StudyIn(StrictModel):
    fck: float = Field(default=25, gt=0, le=90)
    fyk: float = Field(default=500, gt=0, le=700)
    gamma_c: float = Field(default=1.5, ge=1, le=2)
    gamma_s: float = Field(default=1.15, ge=1, le=2)
    alpha_cc: float = Field(default=1.0, gt=0, le=1.5)
    cot_theta: float = Field(default=2.5, ge=1, le=2.5)
    cover_m: float = Field(default=0.05, ge=0, le=0.5)
    bar_mm: int = Field(default=16)
    stirrup_mm: int = Field(default=8)
    legs: int = Field(default=2, ge=2, le=6)


@router.post("/studies/{study_id}/ec2/design")
async def ec2_design(study_id: str, body: Ec2StudyIn, user=Depends(current_user)):
    """Lie le moment/effort tranchant dimensionnant (enveloppe EN 1990) à l'acier EN 1992."""
    s = await owned(study_id, user)
    try:
        await source_plan(s, user)
    except HTTPException as exc:
        if exc.status_code not in (404, 409):
            raise
    return ec2.design_study(s.get("model") or {}, s.get("result") or {}, body.model_dump(), s.get("automation_result"))


# ---- Lot 3 : EN 1997 portance des fondations ----
@router.get("/ec7/catalog")
async def ec7_catalog(user=Depends(current_user)):
    return ec7.catalog()


class Ec7In(StrictModel):
    mode: str = Field(default="drained")
    b_m: float = Field(gt=0, le=50)
    l_m: float = Field(gt=0, le=50)
    q_ed_kpa: float = Field(default=0.0, ge=0, le=1e6)
    d_m: float = Field(default=0.0, ge=0, le=50)
    gamma_soil: float = Field(default=0.0, ge=0, le=40)
    c_kpa: float = Field(default=0.0, ge=0, le=1e5)
    phi_deg: float = Field(default=0.0, ge=0, le=60)
    cu_kpa: float = Field(default=0.0, ge=0, le=1e5)
    gamma_Rv: float = Field(default=1.4, ge=1, le=3)
    gamma_phi: float = Field(default=1.0, ge=1, le=2)
    gamma_c: float = Field(default=1.0, ge=1, le=2)
    gamma_cu: float = Field(default=1.0, ge=1, le=2)


@router.post("/ec7/bearing")
async def ec7_bearing(body: Ec7In, user=Depends(current_user)):
    try:
        return ec7.bearing(**body.model_dump())
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from None


class Ec7StudyIn(StrictModel):
    mode: str = Field(default="drained")
    d_m: float = Field(default=0.0, ge=0, le=50)
    gamma_soil: float = Field(default=0.0, ge=0, le=40)
    c_kpa: float = Field(default=0.0, ge=0, le=1e5)
    phi_deg: float = Field(default=0.0, ge=0, le=60)
    cu_kpa: float = Field(default=0.0, ge=0, le=1e5)
    gamma_Rv: float = Field(default=1.4, ge=1, le=3)
    gamma_phi: float = Field(default=1.0, ge=1, le=2)
    gamma_c: float = Field(default=1.0, ge=1, le=2)
    gamma_cu: float = Field(default=1.0, ge=1, le=2)


@router.post("/studies/{study_id}/ec7/design")
async def ec7_design(study_id: str, body: Ec7StudyIn, user=Depends(current_user)):
    s = await owned(study_id, user)
    try:
        await source_plan(s, user)
    except HTTPException as exc:
        if exc.status_code not in (404, 409):
            raise
    return ec7.design_study(s.get("model") or {}, s.get("result") or {}, body.model_dump())


# ---- Lot 4 : EN 1993 acier ----
@router.get("/ec3/catalog")
async def ec3_catalog(user=Depends(current_user)):
    return ec3.catalog()


class Ec3In(StrictModel):
    med_knm: float = Field(ge=0, le=1e6)
    ved_kn: float = Field(default=0.0, ge=0, le=1e6)
    wpl_y_cm3: float = Field(gt=0, le=1e7)
    wel_y_cm3: float = Field(gt=0, le=1e7)
    av_cm2: float = Field(gt=0, le=1e5)
    fy_mpa: float = Field(gt=0, le=1000)
    section_class: int = Field(default=1, ge=1, le=4)
    gamma_m0: float = Field(default=1.0, ge=1, le=2)
    gamma_m1: float = Field(default=1.0, ge=1, le=2)
    mcr_knm: float | None = Field(default=None, ge=0, le=1e7)
    buckling_curve: str = Field(default="a")
    tw_mm: float | None = Field(default=None, gt=0, le=200)
    h_mm: float | None = Field(default=None, gt=0, le=2000)
    tf_mm: float | None = Field(default=None, gt=0, le=200)


@router.post("/ec3/verify")
async def ec3_verify(body: Ec3In, user=Depends(current_user)):
    return ec3.verify(**body.model_dump())


class Ec3StudyIn(StrictModel):
    profile: str = Field(default="IPE300")
    grade: str = Field(default="S235")
    section_class: int | None = Field(default=None, ge=1, le=4)
    gamma_m0: float = Field(default=1.0, ge=1, le=2)
    gamma_m1: float = Field(default=1.0, ge=1, le=2)
    mcr_knm: float | None = Field(default=None, ge=0, le=1e7)
    buckling_curve: str | None = Field(default=None)
    c1: float = Field(default=1.0, ge=0.5, le=3)
    spans: dict[str, float] | None = Field(default=None)
    k_buckling: float = Field(default=1.0, ge=0.5, le=4)
    lcr_m: float | None = Field(default=None, ge=0, le=100)
    med_col_knm: float = Field(default=0.0, ge=0, le=1e6)
    cmy: float = Field(default=0.9, ge=0.4, le=1.0)
    cm_lt: float = Field(default=0.9, ge=0.4, le=1.0)
    lateral_restraint: bool = Field(default=False)


@router.post("/studies/{study_id}/ec3/design")
async def ec3_design(study_id: str, body: Ec3StudyIn, user=Depends(current_user)):
    s = await owned(study_id, user)
    try:
        await source_plan(s, user)
    except HTTPException as exc:
        if exc.status_code not in (404, 409):
            raise
    return ec3.design_study(s.get("model") or {}, s.get("result") or {}, body.model_dump())


# ---- Lot 5 : EN 1995 bois ----
@router.get("/ec5/catalog")
async def ec5_catalog(user=Depends(current_user)):
    return ec5.catalog()


class Ec5In(StrictModel):
    med_knm: float = Field(ge=0, le=1e6)
    ved_kn: float = Field(default=0.0, ge=0, le=1e6)
    b_m: float = Field(gt=0, le=5)
    h_m: float = Field(gt=0, le=5)
    strength_class: str = Field(default="C24")
    service_class: str = Field(default="1")
    load_duration: str = Field(default="medium")
    gamma_m: float | None = Field(default=None, ge=1, le=2)
    lef_m: float | None = Field(default=None, ge=0, le=100)
    kcr: float = Field(default=0.67, gt=0, le=1)
    ksys: float = Field(default=1.0, ge=1, le=1.2)


@router.post("/ec5/verify")
async def ec5_verify(body: Ec5In, user=Depends(current_user)):
    cls = ec5.CLASSES.get(body.strength_class)
    if not cls:
        raise HTTPException(422, "Classe de resistência desconhecida")
    kmod = ec5.kmod_value(body.service_class, body.load_duration)
    gm = body.gamma_m or ec5.GAMMA_M[cls["kind"]]
    return ec5.verify(body.med_knm, body.ved_kn, b_m=body.b_m, h_m=body.h_m, fm_k=cls["fm_k"],
                      fv_k=cls["fv_k"], E0_05=cls["E0_05"], kmod=kmod, gamma_m=gm, kind=cls["kind"],
                      lef_m=body.lef_m, kcr=body.kcr, ksys=body.ksys)


class Ec5StudyIn(StrictModel):
    strength_class: str = Field(default="C24")
    service_class: str = Field(default="1")
    load_duration: str = Field(default="medium")
    gamma_m: float | None = Field(default=None, ge=1, le=2)
    lef_m: float | None = Field(default=None, ge=0, le=100)
    kcr: float = Field(default=0.67, gt=0, le=1)
    ksys: float = Field(default=1.0, ge=1, le=1.2)


@router.post("/studies/{study_id}/ec5/design")
async def ec5_design(study_id: str, body: Ec5StudyIn, user=Depends(current_user)):
    s = await owned(study_id, user)
    try:
        await source_plan(s, user)
    except HTTPException as exc:
        if exc.status_code not in (404, 409):
            raise
    return ec5.design_study(s.get("model") or {}, s.get("result") or {}, body.model_dump())


# ---- Flèches SLS (EN 1990) ----
class SlsIn(StrictModel):
    ratio_char: float = Field(default=250, ge=50, le=2000)
    ratio_qp: float = Field(default=300, ge=50, le=2000)
    spans: dict[str, float] | None = Field(default=None)


@router.post("/studies/{study_id}/sls/deflection")
async def sls_deflection(study_id: str, body: SlsIn, user=Depends(current_user)):
    s = await owned(study_id, user)
    try:
        await source_plan(s, user)
    except HTTPException as exc:
        if exc.status_code not in (404, 409):
            raise
    return sls.deflection_study(s.get("model") or {}, s.get("result") or {}, body.model_dump())


# ---- Note de ferraillage EN 1992 (PDF) ----
@router.post("/studies/{study_id}/export/ferraillage")
async def export_ferraillage(study_id: str, body: Ec2StudyIn, user=Depends(current_user)):
    s = await owned(study_id, user)
    try:
        await source_plan(s, user)
    except HTTPException as exc:
        if exc.status_code not in (404, 409):
            raise
    ec2_out = ec2.design_study(s.get("model") or {}, s.get("result") or {}, body.model_dump(), s.get("automation_result"))
    content = await asyncio.to_thread(build_ferraillage_pdf, s.get("model") or {}, s["revision"], ec2_out)
    return Response(content, media_type="application/pdf",
                    headers={"Content-Disposition": f'''attachment; filename="armaduras-{study_id}-r{s['revision']}.pdf"'''})


# ---- Fissuration EN 1992 §7.3 ----
class CrackIn(Ec2StudyIn):
    w_max_mm: float = Field(default=0.3, gt=0, le=2)
    kt: float = Field(default=0.4, ge=0.4, le=0.6)


@router.post("/studies/{study_id}/ec2/crack")
async def ec2_crack(study_id: str, body: CrackIn, user=Depends(current_user)):
    s = await owned(study_id, user)
    try:
        await source_plan(s, user)
    except HTTPException as exc:
        if exc.status_code not in (404, 409):
            raise
    return crack.crack_study(s.get("model") or {}, s.get("result") or {}, body.model_dump(), s.get("automation_result"))


# ---- Ancrages & recouvrements EN 1992 §8.4/§8.7 ----
class AnchorageIn(Ec2StudyIn):
    bond: str = Field(default="good")
    rho1_pct: float = Field(default=50.0, ge=0, le=100)
    alpha1: float = Field(default=1.0, ge=0.7, le=1.0)
    alpha3: float = Field(default=1.0, ge=0.7, le=1.0)
    alpha4: float = Field(default=1.0, ge=0.7, le=1.0)
    alpha5: float = Field(default=1.0, ge=0.7, le=1.0)


@router.post("/studies/{study_id}/ec2/anchorage")
async def ec2_anchorage(study_id: str, body: AnchorageIn, user=Depends(current_user)):
    s = await owned(study_id, user)
    try:
        await source_plan(s, user)
    except HTTPException as exc:
        if exc.status_code not in (404, 409):
            raise
    return anchorage.anchorage_study(s.get("model") or {}, s.get("result") or {}, body.model_dump(), s.get("automation_result"))


# ---- Linteau / reprise d'ouverture sur mur porteur (EN 1992/1993) ----
class LintelIn(StrictModel):
    clear_span_m: float = Field(gt=0, le=12)
    wall_thickness_m: float = Field(default=0.2, gt=0, le=2)
    masonry_unit_weight_kn_m3: float = Field(default=20, gt=0, le=30)
    masonry_height_above_m: float = Field(default=3.0, ge=0, le=30)
    load_model: str = Field(default="arching")
    arch_angle_deg: float = Field(default=60, ge=30, le=75)
    permanent_line_kn_m: float = Field(default=0, ge=0, le=100000)
    variable_line_kn_m: float = Field(default=0, ge=0, le=100000)
    psi2: float = Field(default=0.3, ge=0, le=1)
    bearing_length_m: float = Field(default=0.2, gt=0, le=2)
    masonry_comp_strength_mpa: float = Field(default=0.6, gt=0, le=20)
    deflection_limit_total: float = Field(default=300, ge=100, le=1000)
    deflection_limit_qp: float = Field(default=500, ge=100, le=1000)
    material: str = Field(default="both")
    steel_grade: str = Field(default="S235")
    steel_families: list[str] = Field(default_factory=lambda: ["IPE", "HEA", "HEB"])
    max_profiles: int = Field(default=2, ge=1, le=2)
    gamma_m0: float = Field(default=1.0, ge=1, le=1.2)
    gamma_m1: float = Field(default=1.0, ge=1, le=1.2)
    lateral_restraint_masonry: bool = Field(default=True)
    ltb_c1: float = Field(default=1.12, ge=1.0, le=2.7)
    rc_width_m: float | None = Field(default=None, gt=0, le=2)
    rc_height_m: float | None = Field(default=None, gt=0, le=2)
    fck: float = Field(default=25, ge=12, le=50)
    fyk: float = Field(default=500, ge=400, le=600)
    cover_m: float = Field(default=0.03, ge=0, le=0.2)
    bar_mm: int = Field(default=12)
    cot_theta: float = Field(default=2.5, ge=1, le=2.5)
    gamma_c: float = Field(default=1.5, ge=1, le=2)
    gamma_s: float = Field(default=1.15, ge=1, le=2)
    alpha_cc: float = Field(default=1.0, gt=0, le=1)
    rc_span_depth_limit: float = Field(default=20, ge=8, le=35)
    steel_eur_per_kg: float = Field(default=3.0, ge=0, le=100)
    concrete_eur_per_m3: float = Field(default=180, ge=0, le=2000)
    rebar_eur_per_kg: float = Field(default=2.0, ge=0, le=100)


@router.post("/studies/{study_id}/opening/lintel")
async def opening_lintel(study_id: str, body: LintelIn, user=Depends(current_user)):
    await owned(study_id, user)
    return lintel.lintel_design(body.model_dump())


# ---- Plusieurs ouvertures : liste de linteaux enregistrés dans l'étude ----
class SavedLintelIn(LintelIn):
    id: str = Field(pattern=r"^[A-Za-z0-9_-]{1,60}$")
    name: str = Field(default="Vão", max_length=80)
    left: str | None = Field(default=None, max_length=60)
    right: str | None = Field(default=None, max_length=60)


class LintelsIn(StrictModel):
    lintels: list[SavedLintelIn] = Field(default_factory=list, max_length=30)


def _lintel_opts(entry: dict) -> dict:
    return {k: v for k, v in entry.items() if k not in ("id", "name", "left", "right")}


def _store_lintels(payload: list[SavedLintelIn]) -> list[dict]:
    stored = []
    for item in payload:
        data = item.model_dump()
        opts = _lintel_opts(data)
        stored.append({"id": data["id"], "name": data["name"], "left": data["left"],
                       "right": data["right"], "inputs": opts,
                       "result": lintel.lintel_design(opts), "at": now()})
    return stored


@router.get("/studies/{study_id}/lintels")
async def list_lintels(study_id: str, user=Depends(current_user)):
    s = await owned(study_id, user)
    return {"lintels": s.get("lintels", [])}


@router.put("/studies/{study_id}/lintels")
async def save_lintels(study_id: str, body: LintelsIn, user=Depends(current_user)):
    await owned(study_id, user)
    ids = [x.id for x in body.lintels]
    if len(ids) != len(set(ids)):
        raise HTTPException(422, "Identificadores de padieiras duplicados")
    stored = _store_lintels(body.lintels)
    await db.structuro_calculations.update_one(
        {"study_id": study_id, "user_id": user["user_id"]},
        {"$set": {"lintels": stored, "updated_at": now()}})
    return {"lintels": stored}


@router.get("/studies/{study_id}/lintels/{lintel_id}/export/{fmt}")
async def export_lintel(study_id: str, lintel_id: str, fmt: str, user=Depends(current_user)):
    s = await owned(study_id, user)
    entry = next((x for x in s.get("lintels", []) if x.get("id") == lintel_id), None)
    if not entry:
        raise HTTPException(404, "Padieira não encontrada; guarde primeiro a lista das aberturas")
    res = entry.get("result") or lintel.lintel_design(entry.get("inputs") or {})
    nm = entry.get("name", "Vão")
    if fmt == "pdf":
        content = await asyncio.to_thread(build_lintel_pdf, res, nm, s["revision"]); mime = "application/pdf"
    elif fmt == "dxf":
        content = await asyncio.to_thread(build_lintel_dxf, res, nm); mime = "application/dxf"
    else:
        raise HTTPException(422, "Formato disponível: pdf ou dxf")
    safe = "".join(c if c.isalnum() else "-" for c in nm)[:40] or "linteau"
    return Response(content, media_type=mime, headers={"Cache-Control": "no-store",
                    "Content-Disposition": f'attachment; filename="padieira-{safe}-{lintel_id}.{fmt}"'})



# ---- Dossier BET complet (PDF) ----
class DossierIn(StrictModel):
    include: list[str] = Field(default_factory=lambda: ["ec2", "ec7", "sls"])
    ec2: Ec2StudyIn = Field(default_factory=Ec2StudyIn)
    ec3: Ec3StudyIn = Field(default_factory=Ec3StudyIn)
    ec5: Ec5StudyIn = Field(default_factory=Ec5StudyIn)
    ec7: Ec7StudyIn = Field(default_factory=Ec7StudyIn)
    sls: SlsIn = Field(default_factory=SlsIn)
    crack: CrackIn = Field(default_factory=CrackIn)
    anchorage: AnchorageIn = Field(default_factory=AnchorageIn)
    lintel: LintelIn | None = None


@router.post("/studies/{study_id}/export/dossier")
async def export_dossier(study_id: str, body: DossierIn, user=Depends(current_user)):
    s = await owned(study_id, user)
    try:
        await source_plan(s, user)
    except HTTPException as exc:
        if exc.status_code not in (404, 409):
            raise
    model, res = s.get("model") or {}, s.get("result") or {}
    inc = set(body.include)
    auto = s.get("automation_result")
    sections = {"envelope": eurocode.design_envelope(res)}
    if "ec2" in inc:
        sections["ec2"] = ec2.design_study(model, res, body.ec2.model_dump(), auto)
    if "crack" in inc:
        sections["crack"] = crack.crack_study(model, res, body.crack.model_dump(), auto)
    if "anchorage" in inc:
        sections["anchorage"] = anchorage.anchorage_study(model, res, body.anchorage.model_dump(), auto)
    if "ec3" in inc:
        sections["ec3"] = ec3.design_study(model, res, body.ec3.model_dump())
    if "ec5" in inc:
        sections["ec5"] = ec5.design_study(model, res, body.ec5.model_dump())
    if "ec7" in inc:
        sections["ec7"] = ec7.design_study(model, res, body.ec7.model_dump())
    if "sls" in inc:
        sections["sls"] = sls.deflection_study(model, res, body.sls.model_dump())
    if "reinforcement" in inc and res.get("reinforcement"):
        sections["reinforcement"] = res["reinforcement"]
    if "architecture" in inc and res.get("architectural_compatibility"):
        sections["architecture"] = res["architectural_compatibility"]
    if "linked" in inc and res.get("linked_reinforcement"):
        sections["linked"] = res["linked_reinforcement"]
    if "lintel" in inc:
        saved = s.get("lintels") or []
        if saved:
            sections["lintels"] = [{"name": x.get("name", "Vão"),
                                    "result": x.get("result") or lintel.lintel_design(x.get("inputs") or {})}
                                   for x in saved]
        elif body.lintel is not None:
            sections["lintel"] = lintel.lintel_design(body.lintel.model_dump())
    content = await asyncio.to_thread(build_dossier_pdf, model, s["revision"], sections)
    return Response(content, media_type="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="dossier-bet-{study_id}-r{s["revision"]}.pdf"'})


@router.get("/studies/{study_id}/export/{fmt}")
async def export(study_id:str,fmt:str,user=Depends(current_user),expected_revision:int | None=None):
    s=await owned(study_id,user)
    await source_plan(s,user)
    if expected_revision is not None and expected_revision!=s["revision"]:
        raise HTTPException(409,"Revisão ultrapassada; recarregue o estudo antes da exportação")
    model=Model.model_validate(s["model"])
    if fmt=="pdf":
        content=await asyncio.to_thread(build_pdf,model,s["revision"]);mime="application/pdf"
    elif fmt=="dxf":
        content=await asyncio.to_thread(build_dxf,model,s["revision"]);mime="application/dxf"
    elif fmt=="aciers":
        if model.reinforcement is None and not model.linked_sections: raise HTTPException(422,"Nenhum processo de armaduras")
        content=await asyncio.to_thread(build_rebar_pdf,model,s["revision"]);mime="application/pdf"
    elif fmt in ("plans","nomenclature","dossier"):
        manifest=await asyncio.to_thread(compile_dossier,model,s["revision"])
        if not manifest["can_export"]: raise HTTPException(422,{"message":"Processo geométrico incompleto","errors":manifest["errors"]})
        if fmt=="dossier":
            from engines.structuro_automation_exports import build_automation_pdf
            auto=s.get("automation_result")
            if not auto or auto.get("output_input_hash")!=calculate(model)["input_hash"]:
                raise HTTPException(409,"Relance a geração automática para produzir o processo completo")
            def make_zip():
                out=io.BytesIO()
                with zipfile.ZipFile(out,"w",zipfile.ZIP_DEFLATED) as z:
                    z.writestr("01_plans_A3.pdf",build_drawing_pdf(model,s["revision"],manifest))
                    z.writestr("02_note_automatisation.pdf",build_automation_pdf(model,auto,s["revision"]))
                    z.writestr("03_note_gravitaire.pdf",build_pdf(model,s["revision"]))
                    z.writestr("04_nomenclature.csv",build_schedule_csv(manifest))
                    z.writestr("05_modele.json",model.model_dump_json(indent=2))
                    z.writestr("06_controles.json",json.dumps(auto,indent=2,ensure_ascii=False))
                return out.getvalue()
            content=await asyncio.to_thread(make_zip);mime="application/zip"
        else:
            content=await asyncio.to_thread(build_drawing_pdf,model,s["revision"],manifest) if fmt=="plans" else build_schedule_csv(manifest)
            mime="application/pdf" if fmt=="plans" else "text/csv"
    elif fmt=="json":
        content=model.model_dump_json(indent=2).encode();mime="application/json"
    else: raise HTTPException(422,"Formatos disponíveis: pdf, dxf, aciers, plans, nomenclature, dossier ou json")
    await source_plan(s,user)
    if (await owned(study_id,user))["revision"]!=s["revision"]:
        raise HTTPException(409,"Estudo modificado durante a geração; recarregue")
    suffix={"aciers":"pdf","plans":"pdf","nomenclature":"csv","dossier":"zip"}.get(fmt,fmt)
    return Response(content,media_type=mime,headers={"Cache-Control":"no-store","X-Study-Revision":str(s["revision"]),
        "Content-Disposition":f'attachment; filename="estrutura-{fmt}-{study_id}-r{s["revision"]}.{suffix}"'})


@router.get("/studies/{study_id}/drawings")
async def drawings(study_id:str,expected_revision:int,user=Depends(current_user)):
    s=await owned(study_id,user)
    await source_plan(s,user)
    if expected_revision!=s["revision"]: raise HTTPException(409,"Revisão ultrapassada; recarregue o estudo")
    manifest=await asyncio.to_thread(compile_dossier,Model.model_validate(s["model"]),s["revision"])
    await source_plan(s,user)
    if (await owned(study_id,user))["revision"]!=s["revision"]: raise HTTPException(409,"Estudo modificado durante a geração")
    return manifest


@router.get("/studies/{study_id}/drawings/{sheet_id}")
async def drawing_sheet(study_id:str,sheet_id:str,expected_revision:int,user=Depends(current_user)):
    s=await owned(study_id,user)
    await source_plan(s,user)
    if expected_revision!=s["revision"]: raise HTTPException(409,"Revisão ultrapassada; recarregue o estudo")
    model=Model.model_validate(s["model"])
    manifest=await asyncio.to_thread(compile_dossier,model,s["revision"])
    if not manifest["can_export"]: raise HTTPException(422,"Corrija os erros do processo antes da pré-visualização")
    sheet=next((sh for sh in manifest["sheets"] if sh["id"]==sheet_id),None)
    if not sheet: raise HTTPException(404,"Folha não encontrada")
    content=await asyncio.to_thread(lambda:scene_svg(build_scene(model,manifest,sheet)))
    await source_plan(s,user)
    if (await owned(study_id,user))["revision"]!=s["revision"]: raise HTTPException(409,"Estudo modificado durante a geração")
    return Response(content,media_type="image/svg+xml",headers={"Cache-Control":"no-store","X-Study-Revision":str(s["revision"]),
        "Content-Security-Policy":"default-src 'none'; style-src 'unsafe-inline'; sandbox"})


@router.post("/studies/{study_id}/automate")
async def automate(study_id:str,body:SaveIn,user=Depends(current_user)):
    s=await owned(study_id,user)
    await source_plan(s,user)
    if s["revision"]!=body.expected_revision: raise HTTPException(409,"Estudo modificado; recarregue antes de gerar")
    candidate,report=await asyncio.to_thread(run_automation,body.model)
    result=await asyncio.to_thread(calculate,candidate)
    await source_plan(s,user)
    patch={"model":candidate.model_dump(),"result":result,"automation_result":report,
        "revision":s["revision"]+1,"updated_at":now(),"last_editor":user["user_id"]}
    changed=await db.structuro_calculations.update_one({"study_id":study_id,"user_id":user["user_id"],"revision":body.expected_revision},{"$set":patch})
    if not changed.matched_count: raise HTTPException(409,"Estudo modificado durante a geração; recarregue")
    return {**s,**patch}
