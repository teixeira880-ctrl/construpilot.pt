"""Partial takeoffs cannot silently become complete project estimates."""
from types import SimpleNamespace as NS
from unittest.mock import AsyncMock

import pymupdf
import pytest

from engines.plan_quote_scope import group_coverage, positive_quantity
from engines.plan_vector_pdf import pdf_text_blocks, extract_vector_dimensions
from test_audit_regressions import functions


def qty(m):
    return m.get("qty")


def test_all_recorded_rows_priced_does_not_certify_the_whole_project():
    c = group_coverage([{"plan_id":"B"}], {"B":{"measurements":[{"qty":10,"poste":"wall"}]}}, qty, lambda p:True)
    assert c["recorded_measurements_complete"]
    assert not c["project_complete"]
    assert c["status"] == "partial"


def test_missing_empty_unpriced_invalid_and_duplicate_plans_remain_visible():
    levels = [{"plan_id":p} for p in ["B","C","A","D","B"]]
    plans = {"B":{"measurements":[{"qty":10,"poste":"wall"},{"qty":None},{"qty":-1},{"qty":3}]},
             "C":{"measurements":[]},"D":{"measurements":[{"qty":4,"poste":"unknown"}]}}
    c = group_coverage(levels, plans, qty, lambda p:p == "wall")
    assert c["plans_count"] == 4 and c["available_plans"] == 3
    assert c["missing_plan_ids"] == ["A"] and c["empty_plan_ids"] == ["C"]
    assert c["duplicate_plan_ids"] == ["B"] and c["measurements_count"] == 5
    assert c["unpriced_measurements"] == 2 and c["invalid_measurements"] == 2
    assert len(c["warnings"]) == 6 and not c["recorded_measurements_complete"]


@pytest.mark.parametrize("value", [None,0,-1,float('nan'),float('inf'),True,'invalid'])
def test_invalid_quantity_not_valued(value):
    assert positive_quantity({"qty":value},qty) is None


@pytest.mark.asyncio
async def test_real_consolidation_deduplicates_and_reports_missing_plans():
    plans=[{"plan_id":"B","measurements":[{"qty":10,"area_m2":10,"poste":"wall"}]},
           {"plan_id":"C","measurements":[]}]
    cursor=NS(to_list=AsyncMock(return_value=plans))
    db=NS(plans_takeoff=NS(find=lambda *a,**k:cursor))
    ns=functions("routes/plans_analysis.py", {"_group_payload","_consolidate_plan"}, db=db,
        _load_ce_prefs=AsyncMock(return_value={"prices":{},"ratios":{}}),
        _measure_chiffrage_qty=qty,_known_poste=lambda *a:True,
        _estimate_poste=lambda *a:{"totals":{"ht_with_margin":100,"ttc":120}})
    result=await ns["_group_payload"]({"group_id":"g","name":"Projet","levels":[{"plan_id":p} for p in ["B","B","C","A"]]}, {"user_id":"owner"}, True)
    assert result["totals"]["ht_with_margin"] == 100
    assert result["totals"]["area_m2"] == 10 and len(result["levels"]) == 3
    assert result["coverage"]["missing_plan_ids"] == ["A"]
    assert result["coverage"]["empty_plan_ids"] == ["C"]
    assert not result["coverage"]["project_complete"]


@pytest.mark.asyncio
async def test_real_consolidation_excludes_nan_and_counts_unit_measures():
    ns=functions("routes/plans_analysis.py", {"_consolidate_plan"}, _measure_chiffrage_qty=qty,
        _known_poste=lambda *a:True,_estimate_poste=lambda *a:{"totals":{"ht_with_margin":30,"ttc":36}})
    result=await ns["_consolidate_plan"]({"measurements":[{"qty":float('nan'),"area_m2":float('nan'),"poste":"x"},
        {"qty":3,"kind":"count","poste":"x"}]}, {"prices":{},"ratios":{}},0)
    assert result["metre"]["count_u"] == 3 and result["metre"]["area_m2"] == 0
    assert result["chiffrage"]["ht_with_margin"] == 30


@pytest.mark.parametrize("power", ["2","3","²","³"])
def test_split_area_volume_unit_never_becomes_a_linear_dimension(power):
    class Page:
        rotation_matrix=pymupdf.Matrix(1,1)
        def get_text(self, kind):
            return {"blocks":[{"type":0,"lines":[{"dir":(1,0),"spans":[
                {"text":"6,1 m","bbox":(40,40,70,48)},
                {"text":power,"bbox":(70,36,73,42)}]},
                {"dir":(1,0),"spans":[{"text":"4.00 m","bbox":(140,40,160,48)}]}]}]}
    blocks=pdf_text_blocks(Page())
    assert blocks[0]["non_dimension"] and blocks[1]["non_dimension"]
    assert not blocks[2]["non_dimension"]
    vectors=[{"type":"line","p1":[x,y],"p2":[a,b]} for x,y,a,b in [(0,50,300,50),(0,30,0,70),(300,30,300,70)]]
    dims=extract_vector_dimensions(vectors,blocks,1,75)["dimensions"]
    assert all(d["value_m"] != 6.1 for d in dims)
    assert any(d["value_m"] == 4 for d in dims)


@pytest.mark.asyncio
async def test_exported_pdf_preserves_partial_scope_and_unknown_prices():
    from engines.plan_quote_scope import SCOPE_NOTICE
    group={"group_id":"g","name":"Ensemble A B C D","levels":[{"plan_id":"missing"}]}
    cursor=NS(to_list=AsyncMock(return_value=[]))
    db=NS(plan_groups=NS(find_one=AsyncMock(return_value=group)),plans_takeoff=NS(find=lambda *a,**k:cursor))
    payload={"levels":[{"plan_id":"missing","level_label":"Bâtiment A","missing":True}],
             "totals":{"area_m2":0,"length_ml":0,"ht_with_margin":0,"ttc":0},
             "coverage":{"warnings":[SCOPE_NOTICE]}}
    ns=functions("routes/plans_analysis.py",{"plan_group_pdf"},db=db,Query=lambda default,*a,**k:default,
        _group_payload=AsyncMock(return_value=payload),_resolve_branding=AsyncMock(return_value={}),
        _group_cover_client=AsyncMock(return_value={}),_group_reference=lambda x:"REF",
        _ensure_level_thumb=AsyncMock(return_value=None),_detail_cotes_flowables=lambda *a,**k:[])
    result=await ns["plan_group_pdf"]("g", user={"user_id":"owner"})
    with pymupdf.open(stream=result.body,filetype="pdf") as pdf:
        text="\n".join(page.get_text() for page in pdf)
    assert "partiel" in text and "budget global" in text
    assert "SOUS-TOTAL" in text and "N/C" in text
    assert "MONTANT ESTIMÉ TTC" not in text and "TOTAL PROJET" not in text
