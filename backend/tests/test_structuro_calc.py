"""Independent mechanics benchmarks, invalid inputs and load-path conservation."""
import copy
import pytest
from pydantic import ValidationError
from engines.structuro_calc import Model, Support, Source, Load, example, calculate, beam_response, fingerprint


def test_uniform_beam_reference():
    r=beam_response(6,10,[],30000)
    assert r["reaction_left_kn"]==pytest.approx(30)
    assert r["reaction_right_kn"]==pytest.approx(30)
    assert r["moment_max_knm"]==pytest.approx(45)
    assert r["shear_max_kn"]==pytest.approx(30)
    assert r["deflection_sampled_mm"]==pytest.approx(5*10*6**4/(384*30000)*1000)


def test_asymmetric_point_reference_and_center_deflection():
    r=beam_response(6,0,[(12,2)])
    assert r["reaction_left_kn"]==8
    assert r["reaction_right_kn"]==4
    assert r["moment_max_knm"]==16
    assert r["moment_position_m"]==2
    c=beam_response(6,0,[(12,3)],30000)
    assert c["deflection_sampled_mm"]==pytest.approx(12*6**3/(48*30000)*1000)


def test_load_directly_on_support_has_no_internal_shear_or_bending():
    r=beam_response(6,0,[(12,0),(15,6)],30000)
    assert r["reaction_left_kn"]==12 and r["reaction_right_kn"]==15
    assert r["moment_max_knm"]==r["shear_max_kn"]==r["deflection_sampled_mm"]==0


def test_combined_load_exact_extremum():
    # 10 kN/m over 6 m plus 12 kN at x=2: RA=38, RB=34.
    # After the point, V=26-10x, maximum at 2.6 m: M=57.8 kNm.
    r=beam_response(6,10,[(12,2)])
    assert r["reaction_left_kn"]==38 and r["reaction_right_kn"]==34
    assert r["moment_position_m"]==pytest.approx(2.6)
    assert r["moment_max_knm"]==pytest.approx(57.8)


def test_point_load_mirror_invariance():
    a=beam_response(7,3,[(13,1.5)],25000)
    b=beam_response(7,3,[(13,5.5)],25000)
    assert a["reaction_left_kn"]==pytest.approx(b["reaction_right_kn"])
    assert a["moment_max_knm"]==pytest.approx(b["moment_max_knm"])
    assert a["deflection_sampled_mm"]==pytest.approx(b["deflection_sampled_mm"])


def test_every_case_reaches_ground_once_and_sums_linearly():
    r=calculate(example())
    assert r["status"]=="mechanical_only" and r["execution_ready"] is False
    cases={c["id"]:c for c in r["cases"]}
    # Independent takeoff: slab60 + beam11.25 + wall56 + columns12.6 + pads15 + strip18.
    assert cases["G"]["external_kn"]==pytest.approx(172.85)
    assert cases["Q"]["external_kn"]==24
    for c in cases.values(): assert c["ground_kn"]==pytest.approx(c["external_kn"])
    for i,e in enumerate(cases["GplusQ"]["elements"]):
        assert e["total_kn"]==pytest.approx(cases["G"]["elements"][i]["total_kn"]+cases["Q"]["elements"][i]["total_kn"])
    s1=next(e for e in cases["GplusQ"]["elements"] if e["id"]=="S1")
    assert s1["mean_pressure_kpa"]==pytest.approx((42+11.25)/2+6.3+7.5)


@pytest.mark.parametrize("field,value",[("density_kn_m3",None),("length_m",None),("reviewed",False),("mechanics_source",Source())])
def test_missing_values_block_not_zero(field,value):
    m=example();setattr(m.elements[0],field,value)
    r=calculate(m);assert r["status"]=="blocked" and r["cases"]==[] and not r["execution_ready"]


@pytest.mark.parametrize("field,value",[("length_m",0),("width_m",-1),("height_m",float("nan")),("x_m",float("inf")),("density_kn_m3",True),("angle_deg",float("nan"))])
def test_invalid_dimensions_fail_schema(field,value):
    d=example().model_dump();d["elements"][0][field]=value
    with pytest.raises(ValidationError):Model.model_validate(d)


@pytest.mark.parametrize("mutation",["cycle","unknown","shares","beam_fraction","position","surface_on_column","no_review","coefficients"])
def test_unsupported_models_block(mutation):
    m=example()
    if mutation=="cycle":m.elements[2].supports=[Support(target="M1",fraction=1.)]
    elif mutation=="unknown":m.elements[2].supports=[Support(target="absent",fraction=1.)]
    elif mutation=="shares":m.elements[0].supports[0].fraction=.6
    elif mutation=="beam_fraction":m.elements[1].supports[0].fraction=.5
    elif mutation=="position":m.elements[0].supports[0].receiving="point";m.elements[0].supports[0].position_m=99
    elif mutation=="surface_on_column":m.elements[3].loads=[Load(action="Q",value=2,mode="surface",source=Source(note="test"))]
    elif mutation=="no_review":m.gravity_model_reviewed=False
    elif mutation=="coefficients":m.combinations[0].factors.pop("Q")
    assert calculate(m)["status"]=="blocked"


def test_zero_density_explicitly_supported_and_stale_hash_changes():
    m=example();old=fingerprint(m);m.elements[0].density_kn_m3=0
    assert fingerprint(m)!=old
    assert calculate(m)["cases"][0]["external_kn"]==pytest.approx(112.85)


def test_point_transfer_into_beam_is_not_smeared():
    m=example();s=m.elements[0].supports[0];s.receiving="point";s.position_m=1.
    case=next(c for c in calculate(m)["cases"] if c["id"]=="Q")
    beam=next(e for e in case["elements"] if e["id"]=="B1")
    assert beam["reaction_left_kn"]==9 and beam["reaction_right_kn"]==3
    assert beam["moment_max_knm"]==9


def test_forbidden_claims_and_duplicate_ids_rejected():
    d=example().model_dump();d["execution_ready"]=True
    with pytest.raises(ValidationError):Model.model_validate(d)
    d.pop("execution_ready");d["elements"].append(copy.deepcopy(d["elements"][0]))
    with pytest.raises(ValidationError):Model.model_validate(d)


def test_pdf_dxf_share_members_and_non_execution_status():
    import fitz,ezdxf,io
    from engines.structuro_calc_exports import build_pdf,build_dxf
    m=example();pdf=fitz.open(stream=build_pdf(m,7),filetype="pdf")
    text="\n".join(p.get_text() for p in pdf)
    assert "NON EXÉCUTOIRE" in text and fingerprint(m) in text.replace("\n","")
    assert all("NON EXÉCUTOIRE" in p.get_text() for p in pdf)
    dxf=ezdxf.read(io.StringIO(build_dxf(m,7).decode()))
    assert len(dxf.modelspace().query("LWPOLYLINE"))==len(m.elements)
    assert dxf.units==6
    assert "NON EXECUTOIRE" in " ".join(x.dxf.text for x in dxf.modelspace().query("TEXT"))


def test_missing_placement_is_never_invented_in_dxf():
    import io,ezdxf
    from engines.structuro_calc_exports import build_dxf
    m=example();m.elements[0].x_m=None
    doc=ezdxf.read(io.StringIO(build_dxf(m,1).decode()))
    assert len(doc.modelspace().query("LWPOLYLINE"))==len(m.elements)-1
    assert any("NON DESSINES: D1" in e.dxf.text for e in doc.modelspace().query("TEXT"))
