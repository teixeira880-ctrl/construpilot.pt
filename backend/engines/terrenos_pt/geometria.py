"""Geometria do terreno: PT-TM06/ETRS89 (EPSG:3763), validação, área, perímetro, importação e exportação.

A projeção é calculada aqui (Transverse Mercator, elipsoide GRS80, série de Snyder) para não depender do pyproj:
erro < 1 mm no território continental face à transformação oficial.
"""
from __future__ import annotations

import io
import json
import math
import re
import zipfile
from typing import Any, Dict, List, Optional, Tuple
from xml.sax.saxutils import escape

# ------------------------------------------------------------------ PT-TM06 / ETRS89 (EPSG:3763)
_A = 6378137.0
_F = 1 / 298.257222101
_E2 = _F * (2 - _F)
_EP2 = _E2 / (1 - _E2)
_LAT0 = math.radians(39.66825833333333)
_LON0 = math.radians(-8.133108333333334)
_K0 = 1.0


def _m(phi: float) -> float:
    e2, e4, e6 = _E2, _E2 ** 2, _E2 ** 3
    return _A * ((1 - e2 / 4 - 3 * e4 / 64 - 5 * e6 / 256) * phi
                 - (3 * e2 / 8 + 3 * e4 / 32 + 45 * e6 / 1024) * math.sin(2 * phi)
                 + (15 * e4 / 256 + 45 * e6 / 1024) * math.sin(4 * phi)
                 - (35 * e6 / 3072) * math.sin(6 * phi))


_M0 = _m(_LAT0)


def tm06(lat: float, lon: float) -> Tuple[float, float]:
    """(lat, lon) ETRS89 → (M, P) em metros, PT-TM06."""
    phi, lam = math.radians(lat), math.radians(lon)
    s, c = math.sin(phi), math.cos(phi)
    n = _A / math.sqrt(1 - _E2 * s * s)
    t = math.tan(phi) ** 2
    cc = _EP2 * c * c
    a = (lam - _LON0) * c
    x = _K0 * n * (a + (1 - t + cc) * a ** 3 / 6 + (5 - 18 * t + t * t + 72 * cc - 58 * _EP2) * a ** 5 / 120)
    y = _K0 * (_m(phi) - _M0 + n * math.tan(phi) * (a * a / 2 + (5 - t + 9 * cc + 4 * cc * cc) * a ** 4 / 24
                                                     + (61 - 58 * t + t * t + 600 * cc - 330 * _EP2) * a ** 6 / 720))
    return x, y


def tm06_inv(x: float, y: float) -> Tuple[float, float]:
    """(M, P) PT-TM06 → (lat, lon) ETRS89."""
    m = _M0 + y / _K0
    mu = m / (_A * (1 - _E2 / 4 - 3 * _E2 ** 2 / 64 - 5 * _E2 ** 3 / 256))
    e1 = (1 - math.sqrt(1 - _E2)) / (1 + math.sqrt(1 - _E2))
    p1 = (mu + (3 * e1 / 2 - 27 * e1 ** 3 / 32) * math.sin(2 * mu) + (21 * e1 ** 2 / 16 - 55 * e1 ** 4 / 32) * math.sin(4 * mu)
          + (151 * e1 ** 3 / 96) * math.sin(6 * mu) + (1097 * e1 ** 4 / 512) * math.sin(8 * mu))
    s, c = math.sin(p1), math.cos(p1)
    c1 = _EP2 * c * c
    t1 = math.tan(p1) ** 2
    n1 = _A / math.sqrt(1 - _E2 * s * s)
    r1 = _A * (1 - _E2) / (1 - _E2 * s * s) ** 1.5
    d = x / (n1 * _K0)
    lat = p1 - (n1 * math.tan(p1) / r1) * (d * d / 2 - (5 + 3 * t1 + 10 * c1 - 4 * c1 * c1 - 9 * _EP2) * d ** 4 / 24
                                           + (61 + 90 * t1 + 298 * c1 + 45 * t1 * t1 - 252 * _EP2 - 3 * c1 * c1) * d ** 6 / 720)
    lon = _LON0 + (d - (1 + 2 * t1 + c1) * d ** 3 / 6
                   + (5 - 2 * c1 + 28 * t1 - 3 * c1 * c1 + 8 * _EP2 + 24 * t1 * t1) * d ** 5 / 120) / c
    return math.degrees(lat), math.degrees(lon)


# ------------------------------------------------------------------ anel
PT_LAT = (29.0, 43.0)       # Continente, Madeira, Açores
PT_LON = (-32.0, -6.0)


class GeometriaInvalida(ValueError):
    pass


def normalizar_anel(anel: Any) -> List[List[float]]:
    """Lista de [lat, lon] sem ponto de fecho repetido nem vértices duplicados consecutivos."""
    if not isinstance(anel, (list, tuple)):
        raise GeometriaInvalida("Os limites do terreno têm de ser uma lista de pontos.")
    pts: List[List[float]] = []
    for p in anel:
        try:
            la, lo = float(p[0]), float(p[1])
        except (TypeError, ValueError, IndexError):
            raise GeometriaInvalida("Há um vértice sem coordenadas válidas.")
        if not (math.isfinite(la) and math.isfinite(lo)):
            raise GeometriaInvalida("Há um vértice sem coordenadas válidas.")
        if pts and abs(pts[-1][0] - la) < 1e-9 and abs(pts[-1][1] - lo) < 1e-9:
            continue
        pts.append([round(la, 8), round(lo, 8)])
    if len(pts) > 1 and abs(pts[0][0] - pts[-1][0]) < 1e-9 and abs(pts[0][1] - pts[-1][1]) < 1e-9:
        pts.pop()
    if len(pts) < 3:
        raise GeometriaInvalida("O terreno precisa de pelo menos 3 vértices.")
    if len(pts) > 5000:
        raise GeometriaInvalida("O limite tem demasiados vértices (máximo 5000).")
    for la, lo in pts:
        if not (PT_LAT[0] <= la <= PT_LAT[1] and PT_LON[0] <= lo <= PT_LON[1]):
            raise GeometriaInvalida("Há vértices fora de Portugal (verifique se a latitude e a longitude estão trocadas).")
    return pts


def poligono_m(anel: List[List[float]]):
    """Polígono shapely em PT-TM06 (metros)."""
    from shapely.geometry import Polygon
    return Polygon([tm06(la, lo) for la, lo in anel])


def medir(anel: Any) -> Dict[str, Any]:
    """Valida e mede: área (m², ha), perímetro, centroide, vértices em PT-TM06, avisos."""
    pts = normalizar_anel(anel)
    poly = poligono_m(pts)
    avisos: List[str] = []
    if not poly.is_valid:
        raise GeometriaInvalida("Os limites do terreno cruzam-se. Corrija a ordem dos vértices.")
    if poly.area < 1.0:
        raise GeometriaInvalida("A área do terreno é inferior a 1 m².")
    lados = []
    xy = list(poly.exterior.coords)[:-1]
    for i, a in enumerate(xy):
        b = xy[(i + 1) % len(xy)]
        lados.append(round(math.hypot(b[0] - a[0], b[1] - a[1]), 2))
    if min(lados) < 0.3:
        avisos.append("Há lados com menos de 30 cm — provavelmente vértices repetidos por engano.")
    c = poly.centroid
    clat, clon = tm06_inv(c.x, c.y)
    # sentido horário, como na RGG
    if poly.exterior.is_ccw:
        pts = [pts[0]] + list(reversed(pts[1:]))
        xy = [xy[0]] + list(reversed(xy[1:]))
        lados = [round(math.hypot(xy[(i + 1) % len(xy)][0] - xy[i][0], xy[(i + 1) % len(xy)][1] - xy[i][1]), 2) for i in range(len(xy))]
    return {
        "anel_latlon": pts,
        "area_m2": round(poly.area, 2),
        "area_ha": round(poly.area / 10000.0, 4),
        "perimetro_m": round(poly.length, 2),
        "centroide": [round(clat, 7), round(clon, 7)],
        "vertices_tm06": [{"n": i + 1, "M": round(x, 2), "P": round(y, 2), "lado_m": lados[i]} for i, (x, y) in enumerate(xy)],
        "bbox_lonlat": _bbox(pts),
        "sistema": "PT-TM06/ETRS89 (EPSG:3763)",
        "avisos": avisos,
    }


def _bbox(pts: List[List[float]], margem_graus: float = 0.0) -> List[float]:
    las = [p[0] for p in pts]
    los = [p[1] for p in pts]
    return [min(los) - margem_graus, min(las) - margem_graus, max(los) + margem_graus, max(las) + margem_graus]


def bbox_txt(pts: List[List[float]], margem_m: float = 0.0) -> str:
    d = margem_m / 111_320.0
    b = _bbox(pts, d)
    return ",".join(f"{v:.7f}" for v in b)


def geom_para_m(geom: Optional[dict]):
    """GeoJSON (lon, lat) → geometria shapely em PT-TM06, reparada. None se não for área."""
    if not geom:
        return None
    from shapely.geometry import shape
    from shapely.ops import transform
    try:
        g = shape(geom)
    except Exception:  # noqa: BLE001
        return None
    if g.geom_type not in ("Polygon", "MultiPolygon") or g.is_empty:
        return None
    g = transform(lambda x, y, z=None: _tm_vec(x, y), g)
    if not g.is_valid:
        g = g.buffer(0)
    return g


def geom_linha_para_m(geom: Optional[dict]):
    if not geom:
        return None
    from shapely.geometry import shape
    from shapely.ops import transform
    try:
        g = shape(geom)
    except Exception:  # noqa: BLE001
        return None
    if g.is_empty:
        return None
    return transform(lambda x, y, z=None: _tm_vec(x, y), g)


def _tm_vec(lons, lats):
    if isinstance(lons, (int, float)):
        return tm06(lats, lons)
    xs, ys = [], []
    for lo, la in zip(lons, lats):
        x, y = tm06(la, lo)
        xs.append(x)
        ys.append(y)
    return xs, ys


def anel_de_geojson(geom: Optional[dict]) -> Optional[List[List[float]]]:
    """Maior anel exterior (lat, lon) de um Polygon/MultiPolygon GeoJSON."""
    if not geom:
        return None
    t = geom.get("type")
    if t == "Polygon":
        ring = (geom.get("coordinates") or [[]])[0]
    elif t == "MultiPolygon":
        cand = [p[0] for p in geom.get("coordinates") or [] if p]
        ring = max(cand, key=len) if cand else []
    else:
        return None
    return [[float(p[1]), float(p[0])] for p in ring if len(p) >= 2] or None


# ------------------------------------------------------------------ importação
MAX_FICHEIRO = 8 * 1024 * 1024


def ler_ficheiro(nome: str, dados: bytes) -> List[Dict[str, Any]]:
    """KML, KMZ, GPX, GeoJSON → [{"nome", "anel_latlon"}]. Linhas fechadas e trilhos GPS viram polígonos."""
    if len(dados) > MAX_FICHEIRO:
        raise GeometriaInvalida("Ficheiro demasiado grande (máximo 8 MB).")
    n = (nome or "").lower()
    if n.endswith(".kmz") or dados[:2] == b"PK":
        try:
            with zipfile.ZipFile(io.BytesIO(dados)) as z:
                kml = next((i for i in z.namelist() if i.lower().endswith(".kml")), None)
                if not kml:
                    raise GeometriaInvalida("O KMZ não contém nenhum KML.")
                if z.getinfo(kml).file_size > MAX_FICHEIRO:
                    raise GeometriaInvalida("KML demasiado grande.")
                dados = z.read(kml)
                n = "doc.kml"
        except zipfile.BadZipFile:
            raise GeometriaInvalida("KMZ corrompido.")
    txt = dados.decode("utf-8-sig", errors="replace").strip()
    if n.endswith((".geojson", ".json")) or txt.startswith("{"):
        out = _ler_geojson(txt)
    elif n.endswith(".gpx") or "<gpx" in txt[:500].lower():
        out = _ler_gpx(txt)
    elif n.endswith(".kml") or "<kml" in txt[:500].lower():
        out = _ler_kml(txt)
    else:
        raise GeometriaInvalida("Formato não suportado. Use KML, KMZ, GPX ou GeoJSON.")
    res = []
    for i, o in enumerate(out):
        try:
            m = medir(o["anel_latlon"])
        except GeometriaInvalida:
            continue
        res.append({"nome": o.get("nome") or f"Terreno {i + 1}", "anel_latlon": m["anel_latlon"], "area_m2": m["area_m2"]})
    if not res:
        raise GeometriaInvalida("Não foi encontrado nenhum polígono válido no ficheiro.")
    return res[:50]


def _xml(txt: str):
    from lxml import etree
    parser = etree.XMLParser(resolve_entities=False, no_network=True, huge_tree=False, remove_comments=True)
    try:
        return etree.fromstring(txt.encode("utf-8"), parser=parser)
    except etree.XMLSyntaxError:
        raise GeometriaInvalida("Ficheiro XML inválido.")


def _local(tag: Any) -> str:
    return str(tag).rsplit("}", 1)[-1].lower()


def _coords_kml(s: str) -> List[List[float]]:
    pts = []
    for tok in re.split(r"\s+", (s or "").strip()):
        parts = tok.split(",")
        if len(parts) >= 2:
            try:
                pts.append([float(parts[1]), float(parts[0])])
            except ValueError:
                continue
    return pts


def _ler_kml(txt: str) -> List[Dict[str, Any]]:
    root = _xml(txt)
    out = []
    for pm in root.iter():
        if _local(pm.tag) != "placemark":
            continue
        nome = next((e.text for e in pm.iter() if _local(e.tag) == "name" and e.text), None)
        anel = None
        for e in pm.iter():
            if _local(e.tag) == "outerboundaryis":
                c = next((x.text for x in e.iter() if _local(x.tag) == "coordinates"), "")
                cand = _coords_kml(c)
                if len(cand) >= 3 and (anel is None or len(cand) > len(anel)):
                    anel = cand
        if anel is None:
            for e in pm.iter():
                if _local(e.tag) == "linestring":
                    c = next((x.text for x in e.iter() if _local(x.tag) == "coordinates"), "")
                    cand = _coords_kml(c)
                    if len(cand) >= 3:
                        anel = cand
                        break
        if anel:
            out.append({"nome": (nome or "").strip()[:120], "anel_latlon": anel})
    return out


def _ler_gpx(txt: str) -> List[Dict[str, Any]]:
    root = _xml(txt)
    out = []
    for grp, pt in (("trkseg", "trkpt"), ("rte", "rtept")):
        for seg in root.iter():
            if _local(seg.tag) != grp:
                continue
            pts = []
            for p in seg.iter():
                if _local(p.tag) == pt:
                    try:
                        pts.append([float(p.get("lat")), float(p.get("lon"))])
                    except (TypeError, ValueError):
                        continue
            if len(pts) >= 3:
                out.append({"nome": "Percurso GPS", "anel_latlon": simplificar(pts, 0.5)})
    if not out:
        pts = []
        for p in root.iter():
            if _local(p.tag) == "wpt":
                try:
                    pts.append([float(p.get("lat")), float(p.get("lon"))])
                except (TypeError, ValueError):
                    continue
        if len(pts) >= 3:
            out.append({"nome": "Pontos GPS", "anel_latlon": pts})
    return out


def _ler_geojson(txt: str) -> List[Dict[str, Any]]:
    try:
        js = json.loads(txt)
    except json.JSONDecodeError:
        raise GeometriaInvalida("GeoJSON inválido.")
    feats = js.get("features") if js.get("type") == "FeatureCollection" else [js]
    out = []
    for f in feats or []:
        geom = f.get("geometry") if f.get("type") == "Feature" else f
        props = (f.get("properties") or {}) if f.get("type") == "Feature" else {}
        anel = anel_de_geojson(geom)
        if not anel and (geom or {}).get("type") == "LineString":
            anel = [[c[1], c[0]] for c in geom.get("coordinates") or [] if len(c) >= 2]
        if anel and len(anel) >= 3:
            nome = props.get("nome") or props.get("name") or props.get("Name") or ""
            out.append({"nome": str(nome)[:120], "anel_latlon": anel})
    return out


def simplificar(pts: List[List[float]], tol_m: float) -> List[List[float]]:
    """Douglas-Peucker em metros (trilhos GPS com milhares de pontos)."""
    if len(pts) < 50:
        return pts
    from shapely.geometry import LineString
    xy = [tm06(a, b) for a, b in pts]
    s = LineString(xy).simplify(tol_m, preserve_topology=False)
    return [list(tm06_inv(x, y)) for x, y in s.coords]


# ------------------------------------------------------------------ exportação
def para_kml(nome: str, anel: List[List[float]], descricao: str = "") -> str:
    """KML 2.2 (WGS84/ETRS89, lon,lat) — o formato que a App e a plataforma BUPi aceitam para importação."""
    ring = anel + [anel[0]]
    coords = " ".join(f"{lo:.8f},{la:.8f},0" for la, lo in ring)
    nm = escape(nome or "Terreno")
    return ('<?xml version="1.0" encoding="UTF-8"?>\n'
            '<kml xmlns="http://www.opengis.net/kml/2.2"><Document>'
            f"<name>{nm}</name>"
            '<Style id="t"><LineStyle><color>ff3a73b8</color><width>3</width></LineStyle>'
            '<PolyStyle><color>333a73b8</color></PolyStyle></Style>'
            f"<Placemark><name>{nm}</name><description>{escape(descricao)}</description><styleUrl>#t</styleUrl>"
            "<Polygon><outerBoundaryIs><LinearRing><coordinates>"
            f"{coords}"
            "</coordinates></LinearRing></outerBoundaryIs></Polygon></Placemark></Document></kml>\n")


def para_geojson(nome: str, anel: List[List[float]], props: Optional[dict] = None) -> str:
    ring = [[lo, la] for la, lo in anel + [anel[0]]]
    f = {"type": "Feature", "properties": {"nome": nome, **(props or {})},
         "geometry": {"type": "Polygon", "coordinates": [ring]}}
    return json.dumps({"type": "FeatureCollection", "features": [f]}, ensure_ascii=False)


def para_csv_tm06(anel: List[List[float]]) -> str:
    """Quadro de vértices para topógrafo: n; M; P (PT-TM06); latitude; longitude."""
    linhas = ["vertice;M_PTTM06;P_PTTM06;latitude;longitude"]
    for i, (la, lo) in enumerate(anel):
        x, y = tm06(la, lo)
        linhas.append(f"{i + 1};{x:.2f};{y:.2f};{la:.8f};{lo:.8f}")
    return "\n".join(linhas) + "\n"
