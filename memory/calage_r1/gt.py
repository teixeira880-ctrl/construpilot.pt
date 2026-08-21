import asyncio, json, sys
sys.path.insert(0, "/app/backend")
from engines.dwg_convert import dwg_to_dxf
from engines.plan_dxf import process_dxf

async def main():
    dwg = open("/app/memory/calage_r1/r1.dwg", "rb").read()
    print("converting DWG->DXF via CloudConvert…", flush=True)
    dxf = await dwg_to_dxf(dwg, "r1.dwg")
    open("/app/memory/calage_r1/r1.dxf", "wb").write(dxf)
    print("DXF bytes:", len(dxf), flush=True)
    res = process_dxf(dxf, "r1.dxf")
    sm = res.get("structural_metre") or {}
    out = {
        "beton_total_m3": sm.get("beton_total_m3"),
        "acier_total_kg": sm.get("acier_total_kg"),
        "wall_count": sm.get("wall_count"),
        "column_count": sm.get("column_count"),
        "beam_count": sm.get("beam_count"),
        "floor_count": sm.get("floor_count"),
        "totals": {k: v for k, v in sm.items() if isinstance(v, (int, float))},
        "lines": sm.get("lines", [])[:60],
    }
    open("/app/memory/calage_r1/gt.json", "w").write(json.dumps(out, ensure_ascii=False, indent=2, default=str))
    print("GROUND TRUTH keys:", list(sm.keys()), flush=True)
    print(json.dumps(out.get("totals"), ensure_ascii=False, default=str), flush=True)

asyncio.run(main())
