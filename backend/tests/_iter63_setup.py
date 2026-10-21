"""Setup helper for iter63 frontend testing: upload plan, inject FAKE_AI, calibrate, room."""
import io
import os
import sys
import requests
from PIL import Image, ImageDraw

BASE_URL = None
with open("/app/frontend/.env") as f:
    for ln in f:
        if ln.startswith("REACT_APP_BACKEND_URL="):
            BASE_URL = ln.split("=", 1)[1].strip().strip('"').strip("'").rstrip("/")

FAKE_AI = {
    "plan_type": "residential", "detected_scale": "1:100",
    "quality": "good", "page_index": 0, "confidence": 0.9, "warnings": [],
    "dimension_lines": [
        {"value_m": 6.0, "bbox_norm": [100/1200, 80/900, 400/1200, 80/900],
         "orientation": "horizontale", "confidence": 0.9},
        {"value_m": 4.0, "bbox_norm": [0.05, 0.2, 0.05, 0.2 + 200/900],
         "orientation": "verticale", "confidence": 0.8},
        {"value_m": 2.0, "bbox_norm": [0.5, 0.9, 0.5 + 100/1200, 0.9],
         "orientation": "horizontale", "confidence": 0.9},
    ],
    "rooms": [
        {"name": "Séjour", "surface_written_m2": 121.0, "estimated_surface_m2": 120.0,
         "ceiling_height_m": 2.7, "floor_material": "carrelage"},
    ],
    "materials_notes": [], "openings": {"details": []},
}

def make_png():
    im = Image.new("RGB", (1200, 900), "white")
    d = ImageDraw.Draw(im)
    d.rectangle([100, 100, 700, 500], outline="black", width=6)
    d.rectangle([700, 100, 1100, 400], outline="black", width=6)
    buf = io.BytesIO()
    im.save(buf, format="PNG")
    return buf.getvalue()

def mongo_db():
    import pymongo
    env = {}
    with open("/app/backend/.env") as f:
        for ln in f:
            if "=" in ln:
                k, v = ln.split("=", 1)
                env[k.strip()] = v.strip().strip('"').strip("'")
    return pymongo.MongoClient(env["MONGO_URL"])[env["DB_NAME"]]

def main():
    r = requests.post(f"{BASE_URL}/api/auth/login",
                      json={"email": "admin@construpilot.fr", "password": "Construpilot2026!"},
                      timeout=15)
    r.raise_for_status()
    token = r.json()["token"]
    hdrs = {"Authorization": f"Bearer {token}"}
    files = {"file": ("plan_iter63_ui.png", make_png(), "image/png")}
    r = requests.post(f"{BASE_URL}/api/takeoffs/upload", files=files, headers=hdrs, timeout=60)
    r.raise_for_status()
    pid = r.json()["plan_id"]
    db = mongo_db()
    res = db.plans_takeoff.update_one({"plan_id": pid}, {"$set": {"ai_analysis": FAKE_AI}})
    assert res.matched_count == 1
    # Calibrate
    r = requests.post(f"{BASE_URL}/api/takeoffs/{pid}/calibrate/from-cotes",
                      json={"page_index": 0}, headers=hdrs, timeout=15)
    r.raise_for_status()
    # Create room
    r = requests.post(f"{BASE_URL}/api/takeoffs/{pid}/rooms", json={
        "page_index": 0, "name": "Séjour",
        "points": [[100, 100], [600, 100], [600, 600], [100, 600]],
        "ceiling_height_m": 2.5,
    }, headers=hdrs, timeout=15)
    r.raise_for_status()
    print(f"PLAN_ID={pid}")
    print(f"TOKEN={token}")

if __name__ == "__main__":
    main()
