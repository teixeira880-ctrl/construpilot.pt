"""Leitura e escrita de GeoTIFF de uma banda (MDT), sem GDAL.

Leitura: Pillow (libtiff: deflate / LZW / predictores) e, em alternativa, tifffile. A georreferência vem das etiquetas
GeoTIFF ModelPixelScale (33550) + ModelTiepoint (33922) e o valor nulo da etiqueta GDAL_NODATA (42113).
Escrita: tifffile (Float32, deflate) com as mesmas etiquetas + GeoKeyDirectory EPSG:3763, legível por QGIS/ArcGIS/AutoCAD Map.
"""
from __future__ import annotations

import io
from dataclasses import dataclass
from typing import Optional

import numpy as np


@dataclass
class Raster:
    z: np.ndarray            # float32 [linhas, colunas], NaN = sem dados; linha 0 = norte
    x0: float                # x (este) do canto superior esquerdo, metros PT-TM06
    y0: float                # y (norte) do canto superior esquerdo
    px: float                # dimensão do píxel (m)
    py: float

    @property
    def x1(self) -> float:
        return self.x0 + self.z.shape[1] * self.px

    @property
    def y1(self) -> float:
        return self.y0 - self.z.shape[0] * self.py


def _georef(tags: dict, shape) -> Optional[tuple]:
    scale = tags.get(33550)
    tie = tags.get(33922)
    if not scale or not tie or len(tie) < 6:
        return None
    sx, sy = float(scale[0]), float(scale[1])
    i, j, X, Y = float(tie[0]), float(tie[1]), float(tie[3]), float(tie[4])
    return X - i * sx, Y + j * sy, sx, sy


def _nodata(tags: dict) -> Optional[float]:
    v = tags.get(42113)
    if v is None:
        return None
    try:
        return float(str(v).strip().strip("\x00"))
    except ValueError:
        return None


def ler(dados: bytes) -> Raster:
    erros = []
    try:
        from PIL import Image
        Image.MAX_IMAGE_PIXELS = None
        with Image.open(io.BytesIO(dados)) as im:
            tags = {k: im.tag_v2.get(k) for k in (33550, 33922, 42113)}
            z = np.array(im, dtype=np.float32)
        ref = _georef(tags, z.shape)
        if ref is None:
            raise ValueError("sem georreferência GeoTIFF")
        return _limpa(z, ref, _nodata(tags))
    except Exception as e:  # noqa: BLE001
        erros.append(f"Pillow: {e}")
    try:
        import tifffile
        with tifffile.TiffFile(io.BytesIO(dados)) as tf:
            pg = tf.pages[0]
            tags = {}
            for k in (33550, 33922, 42113):
                t = pg.tags.get(k)
                if t is not None:
                    tags[k] = t.value
            z = pg.asarray().astype(np.float32)
        if z.ndim == 3:
            z = z[..., 0]
        ref = _georef(tags, z.shape)
        if ref is None:
            raise ValueError("sem georreferência GeoTIFF")
        return _limpa(z, ref, _nodata(tags))
    except Exception as e:  # noqa: BLE001
        erros.append(f"tifffile: {e}")
    raise ValueError("GeoTIFF ilegível — " + " | ".join(erros))


def _limpa(z: np.ndarray, ref: tuple, nodata: Optional[float]) -> Raster:
    if nodata is not None:
        z[z == np.float32(nodata)] = np.nan
    z[(z < -500) | (z > 5000)] = np.nan          # valores fora do território (nodata não declarado: -9999, -3.4e38…)
    return Raster(z, *ref)


def escrever(r: Raster, epsg: int = 3763) -> bytes:
    """GeoTIFF Float32 comprimido (deflate), NaN como nulo (-9999)."""
    import tifffile
    z = np.where(np.isnan(r.z), -9999.0, r.z).astype(np.float32)
    # GeoKeyDirectory: modelo projetado, raster PixelIsArea, CRS projetado EPSG
    geokeys = (1, 1, 0, 3,
               1024, 0, 1, 1,        # GTModelTypeGeoKey = Projected
               1025, 0, 1, 1,        # GTRasterTypeGeoKey = PixelIsArea
               3072, 0, 1, epsg)     # ProjectedCSTypeGeoKey
    extra = [
        (33550, "d", 3, (r.px, r.py, 0.0), True),
        (33922, "d", 6, (0.0, 0.0, 0.0, r.x0, r.y0, 0.0), True),
        (34735, "H", len(geokeys), geokeys, True),
        (42113, "s", 0, "-9999", True),
    ]
    buf = io.BytesIO()
    tifffile.imwrite(buf, z, compression="zlib", extratags=extra, photometric="minisblack")
    return buf.getvalue()
