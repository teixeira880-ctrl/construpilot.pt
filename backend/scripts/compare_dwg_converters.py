"""Compara a conversão DWG→DXF do conversor local (LibreDWG) com a do AutoCAD da Autodesk (Automation API) no MESMO ficheiro.

Uso (no pod, a partir de /app/backend):
  python3 scripts/compare_dwg_converters.py --file /caminho/planta.dwg [--user <user_id>]
  python3 scripts/compare_dwg_converters.py --doc "R+1"          # DWG já anexado no assistente (nome contém o texto)
Lança 1 WorkItem Autodesk por ficheiro (nível gratuito / Flex). Não altera nada no site nem na base, além da cache de conversão.
Imprime só contagens e medições (nada de chaves)."""
import argparse
import asyncio
import base64
import io
import json
import sys
import time
from collections import Counter
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / ".env")


def _summary(dxf: bytes) -> dict:
    import ezdxf
    from ezdxf import recover
    try:
        doc = ezdxf.read(io.StringIO(dxf.decode("utf-8", "ignore")))
    except Exception:  # noqa: BLE001
        doc, _ = recover.read(io.BytesIO(dxf))
    msp = doc.modelspace()
    kinds = Counter(e.dxftype() for e in msp)
    out = {"tamanho_kb": round(len(dxf) / 1024), "entidades": sum(kinds.values()), "por_tipo": dict(kinds.most_common(12)),
           "camadas": len(doc.layers), "blocos": len(doc.blocks), "unidades_INSUNITS": doc.header.get("$INSUNITS", 0)}
    try:
        from engines.metre.coffrage_dxf import coffrage_takeoff
        r = coffrage_takeoff(dxf)
        el = r.get("elements", {})
        out["medicao"] = {"laje_m2": (el.get("slab") or {}).get("net_area_m2"), "paredes_planta_m2": (el.get("walls") or {}).get("plan_area_m2"),
                          "paredes_ml": (el.get("walls") or {}).get("length_total_m"), "vigas_ml": (el.get("beams") or {}).get("length_total_m"),
                          "pilares": (el.get("columns") or {}).get("count"), "niveis_lidos": (r.get("levels_printed") or {}).get("dominant")}
    except Exception as exc:  # noqa: BLE001
        out["medicao"] = {"erro": type(exc).__name__}
    try:
        from engines.plan_dxf import process_dxf
        process_dxf(dxf, "comparacao.dxf")
        out["importacao_planta"] = "OK"
    except Exception as exc:  # noqa: BLE001
        out["importacao_planta"] = f"ERRO {type(exc).__name__}"
    return out


async def _load(args):
    if args.file:
        return Path(args.file).read_bytes(), Path(args.file).name, args.user or "comparacao-operador"
    from core.db import db
    q = {"filename": {"$regex": args.doc, "$options": "i"}}
    async for d in db.assistant_docs.find(q, {"_id": 0, "filename": 1, "data_b64": 1, "user_id": 1}).sort("created_at", -1):
        if (d.get("filename") or "").lower().endswith(".dwg") and d.get("data_b64"):
            return base64.b64decode(d["data_b64"]), d["filename"], d["user_id"]
    raise SystemExit(f"nenhum DWG anexado com «{args.doc}» no nome")


async def main(args):
    data, name, uid = await _load(args)
    res = {"ficheiro": name, "tamanho_dwg_kb": round(len(data) / 1024)}
    from engines import dwg_local
    t = time.monotonic()
    try:
        local, _hint = await asyncio.to_thread(dwg_local.dwg_to_dxf_hint, data)
        res["libredwg"] = {"segundos": round(time.monotonic() - t, 1), **_summary(local)}
    except Exception as exc:  # noqa: BLE001
        res["libredwg"] = {"erro": f"{type(exc).__name__}: {str(exc)[:200]}"}
    from engines.autodesk_dwg import convert
    t = time.monotonic()
    try:
        aps, meta = await convert(data, user_id=uid)
        res["autocad_autodesk"] = {"segundos": round(time.monotonic() - t, 1), **_summary(aps)}
    except Exception as exc:  # noqa: BLE001
        res["autocad_autodesk"] = {"erro": f"{type(exc).__name__}: {str(exc)[:200]}"}
    print(json.dumps(res, ensure_ascii=False, indent=1, default=str))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--file"); ap.add_argument("--doc"); ap.add_argument("--user")
    a = ap.parse_args()
    if not (a.file or a.doc):
        ap.error("--file ou --doc")
    asyncio.run(main(a))
