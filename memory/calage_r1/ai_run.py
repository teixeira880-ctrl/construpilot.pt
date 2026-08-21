import asyncio, base64, io, json, sys
sys.path.insert(0, "/app/backend")
import pymupdf
from PIL import Image
from engines.plan_structure import detect_structure_tiled

def render(path, dpi=200):
    doc = pymupdf.open(path)
    page = doc[0]
    pix = page.get_pixmap(dpi=dpi, alpha=False)
    img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
    w, h = img.size
    buf = io.BytesIO(); img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode(), w, h

async def main():
    b64, w, h = render("/app/memory/calage_r1/r1.pdf")
    print(f"image {w}x{h}", flush=True)
    res = await detect_structure_tiled(b64, w, h)
    counts = {
        "walls": len(res.get("walls", [])),
        "columns": len(res.get("columns", [])),
        "beams": len(res.get("beams", [])),
        "floors": len(res.get("floors", [])),
        "footings": len(res.get("footings", [])),
        "openings": len(res.get("openings", [])),
        "reservations": len(res.get("reservations", [])),
        "plan_kind": res.get("plan_kind"),
        "confidence": res.get("confidence"),
    }
    open("/app/memory/calage_r1/ai_pdf.json", "w").write(json.dumps(counts, ensure_ascii=False, indent=2))
    print("AI PDF COUNTS:", json.dumps(counts, ensure_ascii=False), flush=True)

asyncio.run(main())
