"""Conversão DWG → DXF local e open source: LibreDWG (WebAssembly, processo Node separado) + ezdxf.

1. `tools/dwg2json/dwg2json.mjs` lê o DWG com LibreDWG e escreve o espaço modelo e os blocos usados em JSON.
   LibreDWG é GPL-3.0: corre como programa independente, chamado por subprocesso, sem ligação ao nosso código.
2. Este módulo reconstrói um DXF com o ezdxf (camadas, blocos, linhas, polilinhas, arcos, círculos, splines,
   textos, cotas como blocos, tramas), que segue depois o circuito normal `process_dxf`.

Vantagens face aos outros conversores de `dwg_convert`: não custa nada por ficheiro e o desenho do cliente não sai
do servidor. Precisa de Node ≥ 20 e de `npm ci` em `tools/dwg2json` (ver README dessa pasta).
"""
from __future__ import annotations

import io
import itertools
import json
import logging
import math
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

logger = logging.getLogger("dwg_libredwg")

TOOL_DIR = Path(os.environ.get("LIBREDWG_TOOL_DIR") or Path(__file__).resolve().parents[1] / "tools" / "dwg2json")
TIMEOUT_S = 180
MAX_DWG_BYTES = 80 * 1024 * 1024
ARC_STEP = math.radians(3)       # segmentação dos arcos horários das tramas


def _node() -> str | None:
    return os.environ.get("NODE_BINARY") or shutil.which("node")


def available() -> bool:
    if os.environ.get("LIBREDWG_DISABLED") == "true":
        return False
    return bool(_node()) and (TOOL_DIR / "node_modules" / "@mlightcad" / "libredwg-web" / "wasm").is_dir()


def read_json(data: bytes) -> dict:
    """DWG → dicionário (entidades do espaço modelo, blocos, camadas, cabeçalho)."""
    if len(data) > MAX_DWG_BYTES:
        raise RuntimeError("DWG demasiado grande para conversão (máx. 80 MB)")
    if not available():
        raise RuntimeError("Conversor LibreDWG não instalado no servidor")
    with tempfile.TemporaryDirectory(prefix="cp-dwg-") as tmp:
        src, dst = Path(tmp) / "plan.dwg", Path(tmp) / "plan.json"
        src.write_bytes(data)
        try:
            proc = subprocess.run([_node(), "--max-old-space-size=3072", str(TOOL_DIR / "dwg2json.mjs"), str(src), str(dst)],
                                  cwd=str(TOOL_DIR), capture_output=True, timeout=TIMEOUT_S, check=False)
        except (OSError, subprocess.SubprocessError) as e:
            raise RuntimeError("Conversão DWG local impossível (LibreDWG)") from e
        if proc.returncode != 0 or not dst.is_file():
            logger.warning("dwg2json falhou rc=%s: %s", proc.returncode, proc.stderr[-500:])
            raise RuntimeError("O DWG não pôde ser lido pelo LibreDWG (versão ou ficheiro não suportados)")
        out = json.loads(dst.read_bytes())
    if not out.get("entities") and not any(out.get("blocks") or {}):
        raise RuntimeError("O DWG não tem entidades legíveis no espaço modelo (ficheiro danificado ou versão não suportada)")
    return out


def dwg_to_dxf(data: bytes) -> tuple[bytes, dict]:
    """→ (DXF em bytes, estatísticas da conversão)."""
    return json_to_dxf(read_json(data))


# ---------------------------------------------------------------- JSON → DXF

def _deg(a) -> float:
    return math.degrees(float(a or 0.0))


def _xy(p, z=False):
    p = p or {}
    return (float(p.get("x", 0.0)), float(p.get("y", 0.0)), float(p.get("z", 0.0))) if z else \
        (float(p.get("x", 0.0)), float(p.get("y", 0.0)))


def _cw_arc_points(c, r, a0, a1, step=ARC_STEP):
    """Pontos de um arco percorrido no sentido horário de a0 a a1 (radianos)."""
    while a1 > a0:
        a1 -= math.tau
    n = max(2, math.ceil((a0 - a1) / step))
    return [(c[0] + r * math.cos(a0 + (a1 - a0) * i / n), c[1] + r * math.sin(a0 + (a1 - a0) * i / n)) for i in range(n + 1)]


def _block_name(name: str) -> str:
    """Nomes anónimos (*U12, *D3) passam a nomes normais, para o ezdxf os aceitar como blocos explícitos."""
    return "ANON_" + name[1:] if name.startswith("*") else name


class _Writer:
    def __init__(self, doc):
        self.doc = doc
        self.stats = {"written": 0, "skipped": {}, "failed": {}}

    def attribs(self, e) -> dict:
        a = {"layer": e.get("layer") or "0"}
        ci = e.get("colorIndex")
        if isinstance(ci, int) and 0 < ci < 256:
            a["color"] = ci
        ex = e.get("extrusionDirection") or {}
        ez = (float(ex.get("x", 0) or 0), float(ex.get("y", 0) or 0), float(ex.get("z", 0) or 0))
        if any(ez) and ez != (0.0, 0.0, 1.0) and e.get("type") not in ("LINE", "POINT", "3DFACE", "POLYLINE3D", "SPLINE", "DIMENSION"):
            a["extrusion"] = ez                                          # entidades espelhadas: OCS com Z para baixo
        return a

    def add(self, space, e) -> None:
        t = e.get("type")
        fn = getattr(self, "_" + (t or ""), None)
        if fn is None:
            self.stats["skipped"][t] = self.stats["skipped"].get(t, 0) + 1
            return
        try:
            fn(space, e, self.attribs(e))
            self.stats["written"] += 1
        except Exception as exc:  # noqa: BLE001 — uma entidade estranha não deve impedir a leitura do resto
            self.stats["failed"][t] = self.stats["failed"].get(t, 0) + 1
            logger.debug("entidade %s ignorada: %s", t, exc)

    # --- entidades
    def _LINE(self, s, e, a):
        s.add_line(_xy(e["startPoint"], True), _xy(e["endPoint"], True), dxfattribs=a)

    def _LWPOLYLINE(self, s, e, a):
        pts = [(v["x"], v["y"], 0.0, 0.0, v.get("bulge", 0.0) or 0.0) for v in e.get("vertices") or []]
        if len(pts) < 2:
            return
        a = {**a, "elevation": float(e.get("elevation") or 0.0)}
        s.add_lwpolyline(pts, format="xyseb", close=bool((e.get("flag") or 0) & 1), dxfattribs=a)

    def _POLYLINE2D(self, s, e, a):
        pts = [(v["x"], v["y"], 0.0, 0.0, v.get("bulge", 0.0) or 0.0) for v in e.get("vertices") or []
               if not (v.get("flag") or 0) & 16]                         # sem vértices de controlo de spline
        if len(pts) >= 2:
            s.add_lwpolyline(pts, format="xyseb", close=bool((e.get("flag") or 0) & 1), dxfattribs=a)

    def _POLYLINE3D(self, s, e, a):
        pts = [_xy(v, True) for v in e.get("vertices") or []]
        if len(pts) >= 2:
            pl = s.add_polyline3d(pts, dxfattribs=a)
            if (e.get("flag") or 0) & 1:
                pl.close(True)

    def _ARC(self, s, e, a):
        s.add_arc(_xy(e["center"], True), float(e["radius"]), _deg(e.get("startAngle")), _deg(e.get("endAngle")), dxfattribs=a)

    def _CIRCLE(self, s, e, a):
        s.add_circle(_xy(e["center"], True), float(e["radius"]), dxfattribs=a)

    def _ELLIPSE(self, s, e, a):
        s.add_ellipse(_xy(e["center"], True), major_axis=_xy(e.get("majorAxisEndPoint"), True),
                      ratio=float(e.get("axisRatio") or 1.0), start_param=float(e.get("startAngle") or 0.0),
                      end_param=float(e.get("endAngle") or math.tau), dxfattribs=a)

    def _SPLINE(self, s, e, a):
        deg = int(e.get("degree") or 3)
        cps = [_xy(p, True) for p in e.get("controlPoints") or []]
        fit = [_xy(p, True) for p in e.get("fitPoints") or []]
        if len(cps) > deg:
            sp = s.add_open_spline(cps, degree=deg, knots=e.get("knots") or None, dxfattribs=a)
        elif len(fit) >= 2:
            sp = s.add_spline(fit, degree=deg, dxfattribs=a)
        else:
            return
        if (e.get("flag") or 0) & 1:
            sp.closed = True

    def _text(self, s, txt, a, *, insert, height, rotation, halign=0, valign=0, align=None, style=None):
        if not txt:
            return
        attrs = {**a, "insert": insert, "height": float(height or 1.0), "rotation": _deg(rotation),
                 "halign": int(halign or 0), "valign": int(valign or 0)}
        if align is not None and (halign or valign):
            attrs["align_point"] = align
        s.add_text(str(txt), dxfattribs=attrs)

    def _TEXT(self, s, e, a):
        self._text(s, e.get("text"), a, insert=_xy(e.get("startPoint")), height=e.get("textHeight"),
                   rotation=e.get("rotation"), halign=e.get("halign"), valign=e.get("valign"), align=_xy(e.get("endPoint")))

    def _ATTRIB(self, s, e, a):
        t = e.get("text") if isinstance(e.get("text"), dict) else {}
        self._text(s, t.get("text"), a, insert=_xy(t.get("startPoint")), height=t.get("textHeight"),
                   rotation=t.get("rotation"), halign=t.get("halign"), valign=t.get("valign"), align=_xy(t.get("endPoint")))

    def _MTEXT(self, s, e, a):
        rot = e.get("rotation") or 0.0
        d = e.get("direction") or {}
        if not rot and d and (d.get("x") or d.get("y")):
            rot = math.atan2(d.get("y", 0.0), d.get("x", 1.0))
        attrs = {**a, "insert": _xy(e.get("insertionPoint"), True), "char_height": float(e.get("textHeight") or 1.0),
                 "attachment_point": int(e.get("attachmentPoint") or 1), "rotation": _deg(rot)}
        if e.get("rectWidth"):
            attrs["width"] = float(e["rectWidth"])
        s.add_mtext(str(e.get("text") or ""), dxfattribs=attrs)

    def _INSERT(self, s, e, a):
        name = _block_name(e.get("name") or "")
        if name not in self.doc.blocks:
            raise KeyError(name)
        attrs = {**a, "xscale": float(e.get("xScale") or 1.0), "yscale": float(e.get("yScale") or 1.0),
                 "zscale": float(e.get("zScale") or 1.0), "rotation": _deg(e.get("rotation"))}
        if (e.get("columnCount") or 0) > 1 or (e.get("rowCount") or 0) > 1:
            attrs.update(column_count=int(e["columnCount"] or 1), row_count=int(e["rowCount"] or 1),
                         column_spacing=float(e.get("columnSpacing") or 0.0), row_spacing=float(e.get("rowSpacing") or 0.0))
        s.add_blockref(name, _xy(e.get("insertionPoint"), True), dxfattribs=attrs)

    def _DIMENSION(self, s, e, a):
        # A geometria da cota (linhas, setas, texto) está no bloco *D… em coordenadas do mundo.
        name = _block_name(e.get("name") or "")
        if name in self.doc.blocks:
            s.add_blockref(name, (0.0, 0.0, 0.0), dxfattribs=a)

    def _SOLID(self, s, e, a):
        s.add_solid([_xy(e[k], True) for k in ("corner1", "corner2", "corner3", "corner4") if e.get(k)], dxfattribs=a)

    _TRACE = _SOLID

    def _3DFACE(self, s, e, a):
        s.add_3dface([_xy(e[k], True) for k in ("corner1", "corner2", "corner3", "corner4") if e.get(k)], dxfattribs=a)

    def _POINT(self, s, e, a):
        s.add_point(_xy(e.get("position"), True), dxfattribs=a)

    def _HATCH(self, s, e, a):
        solid = bool(e.get("solidFill"))
        h = s.add_hatch(color=a.get("color", 256), dxfattribs={k: v for k, v in a.items() if k != "color"})
        if not solid and e.get("patternName"):
            try:
                h.set_pattern_fill(str(e["patternName"]), scale=float(e.get("patternScale") or 1.0),
                                   angle=_deg(e.get("patternAngle")))
            except Exception:  # noqa: BLE001 — padrão desconhecido do ezdxf: trama sólida
                h.set_solid_fill(color=a.get("color", 256))
        paths = 0
        for p in e.get("boundaryPaths") or []:
            flag = int(p.get("boundaryPathTypeFlag") or 0)
            if p.get("vertices"):
                pts = [(v["x"], v["y"], v.get("bulge", 0.0) or 0.0) for v in p["vertices"]]
                h.paths.add_polyline_path(pts, is_closed=True, flags=flag)
                paths += 1
                continue
            ep = h.paths.add_edge_path(flags=flag)
            for ed in p.get("edges") or []:
                et = ed.get("type")
                if et == 1:
                    ep.add_line(_xy(ed["start"]), _xy(ed["end"]))
                elif et == 2:
                    if ed.get("isCCW", 1):
                        ep.add_arc(_xy(ed["center"]), float(ed["radius"]), _deg(ed.get("startAngle")), _deg(ed.get("endAngle")))
                    else:
                        # Arco no sentido horário: o DWG guarda os ângulos simétricos. Segmentado em linhas, no sentido
                        # do contorno, para não depender da convenção de cada leitor.
                        pts = _cw_arc_points(_xy(ed["center"]), float(ed["radius"]), -float(ed.get("startAngle") or 0.0),
                                             -float(ed.get("endAngle") or 0.0))
                        for a_, b_ in itertools.pairwise(pts):
                            ep.add_line(a_, b_)
                elif et == 3:
                    ep.add_ellipse(_xy(ed["center"]), _xy(ed.get("end") or ed.get("majorAxisEndPoint")),
                                   float(ed.get("lengthOfMinorAxis") or ed.get("axisRatio") or 1.0),
                                   _deg(ed.get("startAngle")), _deg(ed.get("endAngle")), ccw=bool(ed.get("isCCW", 1)))
                elif et == 4:
                    cps = [_xy(c) for c in ed.get("controlPoints") or []]
                    if cps:
                        ep.add_spline(control_points=cps, knot_values=ed.get("knots") or None,
                                      degree=int(ed.get("degree") or 3))
            paths += 1
        if not paths:
            s.delete_entity(h)
            raise ValueError("trama sem contorno")


def json_to_dxf(data: dict) -> tuple[bytes, dict]:
    import ezdxf

    doc = ezdxf.new("R2018", setup=True)
    w = _Writer(doc)
    for lay in data.get("layers") or []:
        name = lay.get("name")
        if not name or name in doc.layers:
            continue
        try:
            layer = doc.layers.add(name, color=lay.get("colorIndex") if isinstance(lay.get("colorIndex"), int) and 0 < abs(lay["colorIndex"]) < 256 else 7)
            if lay.get("off"):
                layer.off()
            if lay.get("frozen"):
                layer.freeze()
        except Exception:  # noqa: BLE001 — nome de camada inválido para o ezdxf
            logger.debug("camada ignorada: %r", name)
    blocks = data.get("blocks") or {}
    for name, b in blocks.items():
        if b is None:
            continue
        bn = _block_name(name)
        if bn not in doc.blocks:
            doc.blocks.new(bn, base_point=_xy(b.get("basePoint"), True))
    for name, b in blocks.items():
        if b is None:
            continue
        blk = doc.blocks.get(_block_name(name))
        for e in b.get("entities") or []:
            if e.get("type") != "ATTDEF":
                w.add(blk, e)
    msp = doc.modelspace()
    for e in data.get("entities") or []:
        w.add(msp, e)
    h = data.get("header") or {}
    if isinstance(h.get("INSUNITS"), int):
        doc.header["$INSUNITS"] = h["INSUNITS"]
    buf = io.StringIO()
    doc.write(buf)
    stats = {"provider": "libredwg", "entities": len(data.get("entities") or []), "blocks": len(blocks), **w.stats}
    hint = _units_hint(data)
    if hint:
        stats["units_hint"] = hint
    return buf.getvalue().encode("utf-8"), stats


def _units_hint(data: dict) -> str | None:
    """Desenhos em metros declarados em milímetros (frequente em implantações georreferenciadas): textos com
    menos de 5 unidades de altura e extensão inferior a 5000 unidades não são plausíveis em mm."""
    h = data.get("header") or {}
    if h.get("INSUNITS") != 4:
        return None
    heights = sorted(float(e.get("textHeight") or 0) for e in data.get("entities") or []
                     if e.get("type") in ("TEXT", "MTEXT") and e.get("textHeight"))
    lo, hi = h.get("EXTMIN") or {}, h.get("EXTMAX") or {}
    span = max(abs(float(hi.get("x", 0)) - float(lo.get("x", 0))), abs(float(hi.get("y", 0)) - float(lo.get("y", 0))))
    if heights and heights[len(heights) // 2] < 5 and 0 < span < 5000:
        return "m"
    return None
