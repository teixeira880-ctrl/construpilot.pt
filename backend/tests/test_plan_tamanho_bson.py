"""Planta DWG/DXF densa: o documento tem de caber nos 16 MB do MongoDB sem perder geometria (cotas em píxeis)."""
import asyncio
import base64
import io
import os

import pytest

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "test_plan_bson")
os.environ.setdefault("JWT_SECRET", "test")


def _png_pesado(w=3000, h=2200):
    from PIL import Image, ImageDraw
    im = Image.new("RGB", (w, h), "white")
    d = ImageDraw.Draw(im)
    import random
    rnd = random.Random(1)
    for _ in range(40000):                       # planta muito densa
        x, y = rnd.randrange(w), rnd.randrange(h)
        d.line((x, y, x + rnd.randrange(-80, 80), y + rnd.randrange(-80, 80)), fill=(rnd.randrange(255), 0, 0), width=1)
    b = io.BytesIO()
    im.save(b, "PNG", compress_level=0)          # PNG sem compressão, como um render HQ pesado
    return base64.b64encode(b.getvalue()).decode()


class _Col:
    def __init__(self):
        self.docs = []

    async def insert_one(self, d):
        self.docs.append(d)


def _doc(png, paredes=0):
    return {"plan_id": "plan_x", "user_id": "u", "kind": "dxf", "cad_import": {"layers": [{"n": i} for i in range(10)]},
            "pages": [{"index": 0, "width_px": 3000, "height_px": 2200, "image_png_b64": png, "img_mime": "image/png",
                       "vectors": [{"type": "line", "x1": i, "y1": i, "x2": i + 1, "y2": i + 1} for i in range(8000)],
                       "text_blocks": [{"text": "x" * 20, "x": 1, "y": 2} for _ in range(3000)],
                       "walls_analysis": {"walls": [{"id": i, "pts": [[i, i], [i + 1, i + 1]] * 20} for i in range(paredes)]},
                       "dxf_ratio": 1.0}]}


def test_dwg_denso_cabe_no_mongo(monkeypatch):
    from routes import plans_crud as PC

    class DB:
        plans_takeoff = _Col()
    monkeypatch.setattr(PC, "db", DB())
    png = _png_pesado()
    assert len(png) > 15 * 1024 * 1024               # o caso real: só a imagem já passa o limite
    d = _doc(png)
    asyncio.run(PC._insert_plan_safe(d))
    g = DB.plans_takeoff.docs[0]
    assert PC._bson_size_mb(g) < 15
    pg = g["pages"][0]
    assert pg["img_mime"] == "image/jpeg" and pg["image_recompressed"].startswith("jpeg")
    from PIL import Image
    im = Image.open(io.BytesIO(base64.b64decode(pg["image_png_b64"])))
    assert im.size == (3000, 2200)                   # mesmas dimensões: a geometria em píxeis continua válida
    assert pg["dxf_ratio"] == 1.0


def test_planta_leve_fica_intacta(monkeypatch):
    from routes import plans_crud as PC

    class DB:
        plans_takeoff = _Col()
    monkeypatch.setattr(PC, "db", DB())
    from PIL import Image
    b = io.BytesIO()
    Image.new("RGB", (800, 600), "white").save(b, "PNG")
    d = _doc(base64.b64encode(b.getvalue()).decode())
    asyncio.run(PC._insert_plan_safe(d))
    pg = DB.plans_takeoff.docs[0]["pages"][0]
    assert pg["img_mime"] == "image/png" and len(pg["vectors"]) == 8000 and len(pg["text_blocks"]) == 3000


def test_paredes_a_mais_sao_cortadas_e_assinaladas(monkeypatch):
    from routes import plans_crud as PC

    class DB:
        plans_takeoff = _Col()
    monkeypatch.setattr(PC, "db", DB())
    from PIL import Image
    b = io.BytesIO()
    Image.new("RGB", (800, 600), "white").save(b, "PNG")
    d = _doc(base64.b64encode(b.getvalue()).decode(), paredes=60000)
    assert PC._bson_size_mb(d) > 15
    asyncio.run(PC._insert_plan_safe(d))
    g = DB.plans_takeoff.docs[0]
    assert PC._bson_size_mb(g) < 15
    assert len(g["pages"][0]["walls_analysis"]["walls"]) == 2000 and g["listas_cortadas"]["maior"] == 60000
