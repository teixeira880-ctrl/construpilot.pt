import asyncio, base64, sys
sys.path.insert(0, "/app/backend")
from engines.dwg_convert import dwg_to_dxf
from engines import plan_dxf

async def main():
    dwg = open("/app/memory/calage_r1/r1.dwg", "rb").read()
    dxf = await dwg_to_dxf(dwg, "r1.dwg")
    open("/app/memory/calage_r1/r1.dxf", "wb").write(dxf)
    import ezdxf
    import tempfile, os
    with tempfile.NamedTemporaryFile(suffix=".dxf", delete=False) as f:
        f.write(dxf); p = f.name
    try:
        doc = ezdxf.readfile(p)
    except Exception:
        from ezdxf.recover import readfile as rf
        doc, _ = rf(p)
    os.unlink(p)
    msp = doc.modelspace()
    ents = list(plan_dxf._iter_dxf_entities(msp))
    b = plan_dxf._compute_bounds(ents)
    print("num entities:", len(ents))
    print("bounds:", b, "span_x=", b[2]-b[0], "span_y=", b[3]-b[1])
    # header extents
    try:
        print("EXTMIN:", doc.header.get('$EXTMIN'), "EXTMAX:", doc.header.get('$EXTMAX'))
        print("INSUNITS:", doc.header.get('$INSUNITS'))
    except Exception as e:
        print("hdr err", e)
    # distribution of X/Y to spot outliers
    xs, ys = [], []
    for e in ents:
        try:
            plan_dxf._bounds_from_entity(e, lambda x, y: (xs.append(x), ys.append(y)))
        except Exception:
            pass
    xs.sort(); ys.sort()
    n = len(xs)
    def pct(a, q): 
        return a[int(q*(len(a)-1))] if a else None
    print("X min/1%/50%/99%/max:", xs[0], pct(xs,.01), pct(xs,.5), pct(xs,.99), xs[-1])
    print("Y min/1%/50%/99%/max:", ys[0], pct(ys,.01), pct(ys,.5), pct(ys,.99), ys[-1])
    png, mapping = plan_dxf._render_preview(ents, b)
    open("/app/memory/calage_r1/preview_current.png", "wb").write(png)
    print("preview size:", mapping["width"], "x", mapping["height"], "ratio:", mapping["scale_px_per_dxf_unit"])

asyncio.run(main())
