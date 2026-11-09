"""Offline tests: python -m unittest discover -s tests -p test_clt_ua.py -v."""
import asyncio
import copy
import json
import math
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, AsyncMock
from pydantic import ValidationError
from engines.bet_clt_ua import engine, reader, routing, report, units
from engines.bet_clt_ua.schema import Study, Panel, Assembly
from engines.bet_core import pipeline, profiles, spec, assistant_tool
from engines.bet_core import reader as legacy_reader
from engines.bet_frame import pipeline as frame_pipeline
from engines.bet_frame import thermal as frame_thermal

def run_immediate(coro):
    """Drive mocked, non-suspending async units without an OS network event loop."""
    try:
        coro.send(None)
    except StopIteration as done:
        return done.value
    finally:
        coro.close()
    raise AssertionError("Unexpected real asynchronous I/O in offline unit test")

def basis():
    return {"reference": "SYNTHETIC TEST ONLY - not a product or site", "revision": "test-1",
            "declared_by": "offline test", "confirmed": True}

def panel_input():
    return dict(id="P1", product="SYNTHETIC NOT FOR CONSTRUCTION", layup_id="synthetic-5-layer", bending_axis="longitudinal", application="floor",
                support_model="one_way_simply_supported_udl", span_m=4., strip_width_m=1., thickness_m=.12,
                density_kn_m3=5., ei_eff_kn_m2=1000., ga_eff_kn=10000., moment_resistance_knm=30.,
                shear_resistance_kn=30., permanent_superimposed_kpa=1.4, variable_kpa=2.,
                gamma_g=1.35, gamma_q=1.5, creep_factor=.6, quasi_permanent_factor=.3,
                deflection_limit_mm=20., product_basis=basis(), action_basis=basis())

def assembly_input():
    return dict(id="W1", category="wall", area_m2=10., layers=[
        {"name":"test CLT", "thickness_m":.12,"conductivity_w_mk":.12,"source":"synthetic"},
        {"name":"test insulation", "thickness_m":.16,"conductivity_w_mk":.04,"source":"synthetic"}],
        rsi_m2k_w=.13,rse_m2k_w=.04,linear_bridges=[],point_bridges=[],bridges_reviewed=True,
        required_effective_r_m2k_w=4.,basis=basis())

def study_input():
    return dict(name="Synthetic verification only", site={"country":"UA"},panels=[],assemblies=[])

class Tests(unittest.TestCase):
    def test_closed_form_bending(self):
        r=engine.panel(Panel(**panel_input()))
        self.assertAlmostEqual(r["moment_knm"],11.4)
        self.assertAlmostEqual(r["reaction_each_support_kn"],11.4)
    def test_shear_deformation_is_not_omitted(self):
        r=engine.panel(Panel(**panel_input()))
        self.assertAlmostEqual(r["instant_deflection"]["bending_mm"],13.3333333333)
        self.assertAlmostEqual(r["instant_deflection"]["shear_mm"],.8)
    def test_creep_and_sustained_fraction(self):
        r=engine.panel(Panel(**panel_input()))
        self.assertAlmostEqual(r["final_deflection"]["total_mm"],19.6453333333333)
    def test_full_strip_width_scaling(self):
        a=panel_input(); r1=engine.panel(Panel(**a))
        for k in ("strip_width_m","ei_eff_kn_m2","ga_eff_kn","moment_resistance_knm","shear_resistance_kn"): a[k]*=2
        r2=engine.panel(Panel(**a))
        self.assertAlmostEqual(r2["ratios"]["bending"],r1["ratios"]["bending"])
        self.assertAlmostEqual(r2["final_deflection"]["total_mm"],r1["final_deflection"]["total_mm"])
    def test_overstressed_panel_fails(self):
        a=study_input(); p=panel_input();p["moment_resistance_knm"]=1;a["panels"]=[p]
        self.assertEqual(engine.run(a)["status"],"LIMITED_CHECKS_FAILED")
    def test_no_clt_properties_no_fabricated_panel(self):
        r=engine.run(study_input());self.assertEqual(r["panels"],[]);self.assertIn("panels.with_product_properties_and_design_actions",r["missing"])
    def test_unconfirmed_product_is_not_calculated(self):
        a=study_input();p=panel_input();p["product_basis"]["confirmed"]=False;a["panels"]=[p]
        self.assertEqual(engine.run(a)["panels"],[])
    def test_unknown_country_rejected(self):
        a=study_input();a["site"]["country"]="FR"
        with self.assertRaises(ValidationError):engine.run(a)
    def test_nan_rejected(self):
        a=panel_input();a["span_m"]=float("nan")
        with self.assertRaises(ValidationError):Panel(**a)
    def test_boolean_is_not_a_dimension(self):
        a=panel_input();a["span_m"]=True
        with self.assertRaises(ValidationError):Panel(**a)
    def test_missing_rolling_shear_stiffness_rejected(self):
        a=panel_input();a.pop("ga_eff_kn")
        with self.assertRaises(ValidationError):Panel(**a)
    def test_cantilever_not_simple_support(self):
        a=panel_input();a["support_model"]="cantilever"
        with self.assertRaises(ValidationError):Panel(**a)
    def test_duplicate_element_rejected(self):
        a=study_input();a["panels"]=[panel_input(),panel_input()]
        with self.assertRaises(ValidationError):engine.run(a)
    def test_clear_u_hand_calculation(self):
        r=engine.assembly(Assembly(**assembly_input()))
        self.assertAlmostEqual(r["r_clear_m2k_w"],5.17)
        self.assertAlmostEqual(r["u_clear_w_m2k"],1/5.17)
    def test_bridges_change_effective_u(self):
        a=assembly_input();a["linear_bridges"]=[dict(name="test",length_m=5,psi_w_mk=.1,source="synthetic")]
        r=engine.assembly(Assembly(**a));self.assertAlmostEqual(r["u_effective_w_m2k"],1/5.17+.05)
    def test_unreviewed_bridges_not_zero(self):
        a=assembly_input();a["bridges_reviewed"]=False;r=engine.assembly(Assembly(**a))
        self.assertIsNone(r["u_effective_w_m2k"]);self.assertIsNone(r["limited_requirement_passed"])
    def test_no_ua_thermal_threshold_invented(self):
        a=assembly_input();a["required_effective_r_m2k_w"]=None
        self.assertIsNone(engine.assembly(Assembly(**a))["limited_requirement_passed"])
    def test_country_wide_is_not_one_climate(self):
        r=engine.run(study_input());self.assertIn("site.snow_ground_kpa",r["missing"]);self.assertIn("site.locality",r["missing"])
    def test_success_never_certifies_building(self):
        a=study_input();a["panels"]=[panel_input()];a["assemblies"]=[assembly_input()]
        r=engine.run(a);self.assertFalse(r["execution_ready"]);self.assertFalse(r["certified"]);self.assertIn("fire_resistance",r["not_checked"])
    def test_input_unchanged_and_hash_deterministic(self):
        a=study_input();b=copy.deepcopy(a);r=engine.run(a)
        self.assertEqual(a,b);self.assertEqual(r["input_sha256"],engine.run(a)["input_sha256"])
    def test_decimal_feet(self):
        self.assertAlmostEqual(units.imperial_length_m("186.6'")-units.imperial_length_m("175.5'"),3.38328)
    def test_feet_inches(self):self.assertAlmostEqual(units.imperial_length_m('19\'-8"'),5.9944)
    def test_r_not_rsi(self):self.assertAlmostEqual(units.r_imperial_to_rsi(25),4.402754595)
    def test_unknown_profile_no_fr_fallback(self):
        with self.assertRaises(ValueError):profiles.profile("UA")
    def test_core_guard_before_mutation(self):
        a={"project":{"country":"UA"}};b=copy.deepcopy(a);m,an=pipeline.validate(a)
        self.assertIsNone(m);self.assertEqual(an[0]["code"],"ENGINE-SCOPE");self.assertEqual(a,b)
    def test_clt_with_fr_flag_not_masonry(self):
        # Integração ConstruPilot: o CLT em FR / PT continua nos motores existentes (sem retrocesso), com aviso CLT-SCOPE;
        # só a Ucrânia é desviada para bet_clt_ua.
        from engines.bet_clt_ua.routing import clt_warning, legacy_issue
        a={"project":{"country":"FR"},"user_hypotheses":{"floor_system":"CLT"}}
        self.assertIsNone(legacy_issue(a));self.assertEqual(clt_warning(a)["code"],"CLT-SCOPE")
        spec.apply_defaults(a)
        self.assertIsNotNone(legacy_issue({"project":{"country":"UA"}}))
    def test_frame_guard(self):self.assertIsNone(frame_pipeline.validate({"project":{"country":"UA"}})[0])
    def test_thermal_no_fr_fallback(self):
        with self.assertRaises(ValueError):frame_thermal.solutions("UA")
    def test_existing_profiles_preserved(self):
        self.assertEqual(profiles.profile("FR")["country"],"FR");self.assertEqual(profiles.profile("PT")["country"],"PT")
        a={"project":{"country":"FR"}};spec.apply_defaults(a);self.assertEqual(a["user_hypotheses"]["masonry"],"brique_isobric_20")
    def test_english_title_beats_incidental_elevations(self):
        self.assertEqual(legacy_reader.classify("see elevations MAIN FLOOR PLAN"),"plan")
        self.assertEqual(legacy_reader.classify("SECTIONS AND ASSEMBLIES see elevations"),"coupe")
    def test_tools_registered(self):
        self.assertIn("calculate_clt_ua",assistant_tool.TOOL_NAMES)
        t=next(t for t in assistant_tool.TOOLS if t["name"]=="generate_full_bet_study")
        self.assertIn("UA",t["parameters"]["properties"]["country"]["enum"])
    def test_calculation_tool_entry(self):
        r=run_immediate(assistant_tool.execute("calculate_clt_ua",{"model_json":json.dumps(study_input())},{"user_id":"test"},{},None))
        self.assertEqual(r["country"],"UA");self.assertFalse(r["execution_ready"])
    def test_all_twenty_pages_read_in_five_batches(self):
        pages=[{"page":i,"text":"source "*200} for i in range(1,21)]
        call=AsyncMock(return_value='{"facts":[],"issues":[]}')
        with patch.object(legacy_reader,"pages_of",return_value=pages),patch.object(legacy_reader,"render_png",return_value="fake_image"):
            r=run_immediate(reader.read([("ref.pdf",b"test")],"all Ukraine CLT",llm=call))
        self.assertEqual(len(r["pages"]),20);self.assertEqual(call.await_count,5)
        self.assertEqual(r["calculation_input"]["panels"],[])
    def test_bad_evidence_reference_rejected(self):
        response={"facts":[dict(document="source_1",page=99,field="x",raw_text="1",value="1",unit="m",status="extracted_unreviewed")],"issues":[]}
        with patch.object(legacy_reader,"pages_of",return_value=[{"page":1,"text":"x"*1400}]),patch.object(legacy_reader,"render_png",return_value="fake"):
            with self.assertRaises(ValueError):run_immediate(reader.read([("x.pdf",b"x")],"",llm=AsyncMock(return_value=json.dumps(response))))
    def test_ua_dispatch_precedes_legacy(self):
        class Collection:
            async def update_one(self,*a,**k):pass
        class DB:bet_study_jobs=Collection()
        with patch("engines.bet_clt_ua.hook.handle",new_callable=AsyncMock) as handle,patch("engines.bet_frame.hook.maybe_handle",new_callable=AsyncMock) as legacy:
            run_immediate(assistant_tool._work(DB(),"j","u","c","r",[],"CLT","UA"))
            handle.assert_awaited_once();legacy.assert_not_awaited()
    def test_pdf_and_json_delivery(self):
        from pypdf import PdfReader
        r=engine.run(study_input())
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[1]) as tmp:
            files=report.save(tmp,r,study_input())
            self.assertGreater(len(PdfReader(files["pdf"]).pages),0)
            self.assertEqual(json.loads((Path(tmp)/"CLT_UA_results.json").read_text())["status"],"INPUT_REQUIRED")
    def test_reference_case_is_not_a_design(self):
        p=Path(reader.__file__).with_name("cases")/"villavicencio_reference.json"
        case=json.loads(p.read_text(encoding="utf-8"))
        self.assertEqual(case["source_country"],"CA");self.assertEqual(case["target_country"],"UA")
        self.assertEqual(len(case["source_facts"]),24)
        r=engine.run(case["calculation_input"])
        self.assertEqual(r["status"],case["expected_status"]);self.assertFalse(r["execution_ready"])
    def test_training_examples_are_loaded(self):
        cases=json.loads(reader.examples());self.assertEqual(len(cases),10)
        self.assertIn("instruction_boundary",[c["case"] for c in cases])
    def test_raster_sheet_gets_four_readable_quadrants(self):
        import base64,io
        from PIL import Image
        b=io.BytesIO();Image.new("RGB",(520,360),"white").save(b,format="PNG")
        encoded=base64.b64encode(b.getvalue()).decode()
        detail=reader.detail_images(b"pdf",1,lambda *a,**k:encoded)
        self.assertEqual(len(detail),4)
    def test_no_ukrainian_snow_default_in_legacy(self):
        with self.assertRaises(ValueError):spec.complete_project({"project":{"country":"UA"}})
    def test_random_equilibrium_and_closed_form(self):
        import random
        rng=random.Random(1776)
        for _ in range(100):
            p=panel_input();p.update(span_m=rng.uniform(1,10),strip_width_m=rng.uniform(.5,3),
                permanent_superimposed_kpa=rng.uniform(0,5),variable_kpa=rng.uniform(0,8))
            r=engine.panel(Panel(**p));w=r["uls_line_kn_m"];L=p["span_m"]
            self.assertAlmostEqual(2*r["reaction_each_support_kn"],w*L,places=9)
            self.assertAlmostEqual(r["moment_knm"],w*L*L/8,places=9)
            self.assertGreaterEqual(r["final_deflection"]["total_mm"],r["instant_deflection"]["total_mm"])
    def test_zero_actions_zero_deformation_except_self_weight(self):
        p=panel_input();p["variable_kpa"]=0.;p["permanent_superimposed_kpa"]=0.
        r=engine.panel(Panel(**p));self.assertAlmostEqual(r["g_line_kn_m"],.6)
    def test_limit_at_capacity_and_above(self):
        p=panel_input();p["moment_resistance_knm"]=11.4
        self.assertTrue(engine.panel(Panel(**p))["limited_checks_passed"])
        p["moment_resistance_knm"]=11.39
        self.assertFalse(engine.panel(Panel(**p))["limited_checks_passed"])
    def test_thermal_monotonicity(self):
        a=assembly_input();before=engine.assembly(Assembly(**a))["u_clear_w_m2k"]
        a["layers"][1]["thickness_m"]*=2
        self.assertLess(engine.assembly(Assembly(**a))["u_clear_w_m2k"],before)
    def test_layup_and_direction_required(self):
        p=panel_input();p.pop("bending_axis")
        with self.assertRaises(ValidationError):Panel(**p)
    def test_negative_conductivity_rejected(self):
        a=assembly_input();a["layers"][0]["conductivity_w_mk"]=-.12
        with self.assertRaises(ValidationError):Assembly(**a)
    def test_unphysical_negative_effective_u_rejected(self):
        a=assembly_input();a["linear_bridges"]=[dict(name="bad",length_m=100,psi_w_mk=-1,source="bad test")]
        with self.assertRaises(ValueError):engine.assembly(Assembly(**a))
    def test_legacy_three_reference_models(self):
        root=Path(pipeline.__file__).with_name("cases")
        for name in ("la_courneuve.json","moradia_pt_demo.json","saint_denis.json"):
            m,an=pipeline.validate(json.loads((root/name).read_text(encoding="utf-8")))
            self.assertIsNotNone(m);self.assertFalse(any(a.get("level")=="bloquant" for a in an))

if __name__=="__main__":unittest.main()

