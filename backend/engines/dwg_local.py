"""Conversion DWG → DXF sans service externe ni clé : LibreDWG (WebAssembly) dans un processus Node séparé.

backend/tools/dwg/dwg2json.mjs lit le DWG et écrit la base de dessin en JSON ; ce module la réécrit en DXF R2010 (ezdxf)
avec les calques, les blocs (y compris les blocs de cotes) et l'unité d'origine. Géométrie native : rien n'est redessiné.
LibreDWG est sous GPL-3.0 : il tourne côté serveur uniquement, jamais livré au navigateur.
"""
from __future__ import annotations

import io
import json
import math
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

TOOL = Path(__file__).resolve().parents[1] / "tools" / "dwg"
TIMEOUT_S = int(os.environ.get("DWG_LOCAL_TIMEOUT", "180"))
MAX_DWG = 80 * 1024 * 1024


def available() -> bool:
    """node + LibreDWG (node_modules, ou cópia embarcada em tools/dwg/vendor — o deploy não instala pacotes npm do backend)."""
    return bool(shutil.which("node")) and any((p / "wasm" / "libredwg-web.wasm").is_file() for p in
                                              (TOOL / "node_modules" / "@mlightcad" / "libredwg-web", TOOL / "vendor" / "libredwg-web"))


def dwg_to_json(data: bytes) -> dict:
    if not re.match(rb"AC10[0-9]{2}", data[:6]):
        raise RuntimeError("Le fichier ne porte pas une signature DWG AutoCAD reconnue")
    if len(data) > MAX_DWG:
        raise RuntimeError("DWG trop volumineux (> 80 Mo)")
    if not available():
        raise RuntimeError("Lecteur DWG local non installé (node + tools/dwg/node_modules)")
    with tempfile.TemporaryDirectory(prefix="cp-dwg-") as tmp:
        src, dst = Path(tmp) / "in.dwg", Path(tmp) / "out.json"
        src.write_bytes(data)
        try:
            subprocess.run([shutil.which("node"), str(TOOL / "dwg2json.mjs"), str(src), str(dst)], cwd=str(TOOL), check=True,
                           timeout=TIMEOUT_S, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        except subprocess.TimeoutExpired:
            raise RuntimeError("Lecture DWG trop longue (délai dépassé)") from None
        except subprocess.CalledProcessError as exc:
            raise RuntimeError("DWG illisible par LibreDWG : " + (exc.stderr or b"").decode(errors="ignore")[-200:]) from None
        return json.loads(dst.read_text(encoding="utf-8"))


_BAD = re.compile(r'[<>/\\":;?*|=`]')


def _safe(name: str) -> str:
    return _BAD.sub("_", name or "")[:250] or "_"


def json_to_dxf(db: dict) -> bytes:
    import ezdxf
    doc = ezdxf.new("R2010", setup=True)
    doc.units = int((db.get("header") or {}).get("INSUNITS") or 0)
    doc.header["$INSUNITS"] = doc.units
    for la in ((db.get("tables") or {}).get("LAYER") or {}).get("entries", []):
        name = _safe(la.get("name", ""))
        if name and name not in doc.layers:
            try:
                doc.layers.add(name, color=min(max(abs(int(la.get("colorIndex") or 7)), 1), 255))
            except Exception:  # noqa: BLE001 — nom de calque refusé par ezdxf : entités sur le calque 0
                pass
    stats = {"errors": 0}

    def attrs(e):
        layer = _safe(e.get("layer") or "0")
        a = {"layer": layer if layer in doc.layers else "0"}
        c = e.get("colorIndex", 256)
        if isinstance(c, int) and 0 <= c <= 255:
            a["color"] = c
        return a

    def p(v):
        return (float(v["x"]), float(v["y"]))

    def add(space, e, blocks):
        t = e.get("type")
        a = attrs(e)
        try:
            if t == "LINE":
                space.add_line(p(e["startPoint"]), p(e["endPoint"]), dxfattribs=a)
            elif t == "CIRCLE":
                space.add_circle(p(e["center"]), e["radius"], dxfattribs=a)
            elif t == "ARC":
                space.add_arc(p(e["center"]), e["radius"], math.degrees(e["startAngle"]), math.degrees(e["endAngle"]), dxfattribs=a)
            elif t == "ELLIPSE":
                mj = e["majorAxisEndPoint"]
                if abs(mj["x"]) + abs(mj["y"]) > 0:
                    space.add_ellipse(p(e["center"]), (mj["x"], mj["y"], 0), max(min(e["axisRatio"], 1), 1e-6), e["startAngle"], e["endAngle"], dxfattribs=a)
            elif t == "LWPOLYLINE":
                pts = [(v["x"], v["y"], 0, 0, v.get("bulge", 0)) for v in e.get("vertices", [])]
                if len(pts) > 1:
                    space.add_lwpolyline(pts, format="xyseb", close=bool(e.get("flag", 0) & 1), dxfattribs=a)
            elif t in ("MTEXT", "TEXT"):
                txt = e.get("text", "") or ""
                h = e.get("textHeight") or 0.1
                ins = e.get("insertionPoint") or e.get("startPoint")
                if ins is None:
                    return
                if t == "MTEXT":
                    mt = space.add_mtext(txt, dxfattribs={**a, "char_height": h, "attachment_point": int(e.get("attachmentPoint") or 1),
                                                          "rotation": math.degrees(e.get("rotation") or 0)})
                    mt.set_location(p(ins))
                else:
                    space.add_text(txt, height=h, dxfattribs={**a, "rotation": math.degrees(e.get("rotation") or 0)}).set_placement(p(ins))
            elif t == "HATCH":
                h = space.add_hatch(dxfattribs=a)
                if e.get("solidFill"):
                    h.set_solid_fill(color=a.get("color", 7))
                else:
                    h.set_pattern_fill("ANSI31", scale=0.02)
                for bp in e.get("boundaryPaths", []):
                    if bp.get("edges"):
                        pts = [p(g["start"]) for g in bp["edges"] if g.get("type") == 1 and "start" in g]
                    else:
                        pts = [(v["x"], v["y"]) for v in bp.get("vertices", [])]
                    if len(pts) >= 3:
                        h.paths.add_polyline_path(pts, is_closed=True)
            elif t == "INSERT":
                n = _safe(e.get("name", ""))
                if n in blocks:
                    space.add_blockref(n, p(e["insertionPoint"]), dxfattribs={**a, "xscale": e.get("xScale", 1) or 1, "yscale": e.get("yScale", 1) or 1,
                                                                             "rotation": math.degrees(e.get("rotation") or 0)})
            elif t == "DIMENSION":
                n = _safe(e.get("name", ""))
                if n in blocks:        # géométrie figée de la cote (bloc anonyme)
                    space.add_blockref(n, (0, 0), dxfattribs=a)
        except Exception:  # noqa: BLE001 — une entité corrompue ne bloque pas la conversion
            stats["errors"] += 1

    recs = ((db.get("tables") or {}).get("BLOCK_RECORD") or {}).get("entries", [])
    blocks = {}
    for b in recs:
        n = b.get("name", "")
        if n.startswith("*Model_Space") or n.startswith("*Paper_Space"):
            continue
        sn = _safe(n)
        if sn not in doc.blocks:
            bp = b.get("basePoint") or {"x": 0, "y": 0}
            blocks[sn] = doc.blocks.new(sn, base_point=(bp["x"], bp["y"]))
        else:
            blocks[sn] = doc.blocks.get(sn)
    for b in recs:
        n = b.get("name", "")
        if n.startswith("*Model_Space") or n.startswith("*Paper_Space"):
            continue
        for e in b.get("entities", []):
            add(blocks[_safe(n)], e, blocks)
    ms = next((b.get("handle") for b in recs if b.get("name") == "*Model_Space"), None)
    msp = doc.modelspace()
    for e in db.get("entities", []):
        if e.get("type") != "VIEWPORT" and (ms is None or e.get("ownerBlockRecordSoftId") == ms):
            add(msp, e, blocks)
    buf = io.StringIO()
    doc.write(buf)
    return buf.getvalue().encode("utf-8")


def dwg_to_dxf(data: bytes) -> bytes:
    return json_to_dxf(dwg_to_json(data))


def ensure_installed() -> bool:
    """Au démarrage : installe le lecteur (npm, version figée) s'il manque. Sans réseau ni node : la chaîne garde ODA / services externes."""
    if available():
        return True
    npm = shutil.which("npm")
    if not npm or not (TOOL / "package.json").is_file():
        return False
    try:
        subprocess.run([npm, "install", "--omit=dev", "--no-audit", "--no-fund"], cwd=str(TOOL), check=True, timeout=300,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except (OSError, subprocess.SubprocessError):
        return False
    return available()
