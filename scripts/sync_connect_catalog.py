"""Discovery Engine: copia o catálogo e os casos de paridade para o frontend e gera os
instantâneos offline das demonstrações, calculados pelos motores reais (modo stand sem rede).

Uso: python3 scripts/sync_connect_catalog.py   (a partir da raiz do repositório)
"""
import json
import os
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "unused")

from engines.connect import demo_compute  # noqa: E402

for name in ("catalog.json", "cases.json"):
    shutil.copyfile(ROOT / "backend/engines/connect" / name, ROOT / "frontend/src/connect" / name)
    print("sincronizado", name)

snapshots = {d: demo_compute.compute(d) for d in ("demo_takeoff", "demo_painting", "demo_quote", "demo_margin")}
out = ROOT / "frontend/src/connect/demo_snapshots.json"
out.write_text(json.dumps(snapshots, ensure_ascii=False, indent=1, sort_keys=True) + "\n", encoding="utf-8")
print("gerado", out.relative_to(ROOT))
