"""Descarrega o GeoPackage das RGG do BUPi (dados.gov.pt, eBUPi, CC BY 4.0) para backend/data/bupi/rgg.gpkg.

Uso (no servidor, a partir de backend/):  python scripts/bupi_rgg_descarregar.py [--so-info]
A eBUPi atualiza o GeoPackage de 15 em 15 dias: correr de novo para atualizar. Escreve para um ficheiro temporário e só
substitui o anterior depois de verificar que o GeoPackage abre, tem geometria e índice espacial.
"""
from __future__ import annotations

import io
import json
import os
import shutil
import sqlite3
import struct
import sys
import urllib.request
import zipfile

API = "https://dados.gov.pt/api/1/datasets/representacao-grafica-georreferenciada/"
DESTINO = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "data", "bupi"))
UA = {"User-Agent": "ConstruPilot/1.0 (+https://construpilot.pt)"}


def _get(url: str):
    return urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=120)


def recursos() -> list:
    with _get(API) as r:
        js = json.load(r)
    out = []
    for x in js.get("resources", []):
        out.append({"titulo": x.get("title"), "formato": (x.get("format") or "").lower(), "url": x.get("url"),
                    "tamanho": x.get("filesize"), "atualizado": x.get("last_modified")})
    return out


def _escolher(rs: list):
    for r in rs:
        u = (r["url"] or "").lower()
        if "gpkg" in r["formato"] or u.endswith(".gpkg") or ("zip" in r["formato"] and "gpkg" in (r["titulo"] or "").lower()):
            return r
    for r in rs:
        if (r["url"] or "").lower().endswith(".zip"):
            return r
    return None


def _envelope(blob: bytes):
    if not blob or blob[:2] != b"GP":
        return None
    flags = blob[3]
    e = (flags >> 1) & 0x07
    if e == 0:
        return None
    end = "<" if flags & 1 else ">"
    minx, maxx, miny, maxy = struct.unpack(end + "4d", blob[8:40])
    return minx, maxx, miny, maxy


def verificar_e_indexar(caminho: str) -> dict:
    con = sqlite3.connect(caminho)
    try:
        tab, col = con.execute("SELECT table_name, column_name FROM gpkg_geometry_columns LIMIT 1").fetchone()
        n = con.execute(f'SELECT COUNT(*) FROM "{tab}"').fetchone()[0]
        rt = f"rtree_{tab}_{col}"
        tem_rt = con.execute("SELECT 1 FROM sqlite_master WHERE name=?", (rt,)).fetchone() is not None
        if not tem_rt:     # cria o índice a partir dos envelopes guardados em cada geometria
            pk = next((c[1] for c in con.execute(f'PRAGMA table_info("{tab}")') if c[5] == 1), "fid")
            con.execute(f'CREATE VIRTUAL TABLE "{rt}" USING rtree(id, minx, maxx, miny, maxy)')
            cur = con.execute(f'SELECT "{pk}", "{col}" FROM "{tab}"')
            lote = []
            for fid, blob in cur:
                e = _envelope(blob)
                if e:
                    lote.append((fid, *e))
                if len(lote) >= 50000:
                    con.executemany(f'INSERT INTO "{rt}" VALUES (?,?,?,?,?)', lote)
                    lote = []
            if lote:
                con.executemany(f'INSERT INTO "{rt}" VALUES (?,?,?,?,?)', lote)
            con.commit()
        srs = con.execute("SELECT srs_id FROM gpkg_geometry_columns LIMIT 1").fetchone()[0]
        return {"tabela": tab, "geometria": col, "elementos": n, "srs": srs, "indice_criado": not tem_rt}
    finally:
        con.close()


def main() -> int:
    rs = recursos()
    print("Recursos no dados.gov.pt:")
    for r in rs:
        print(f"  - {r['titulo']} | {r['formato']} | {r['tamanho']} bytes | {r['atualizado']} | {r['url']}")
    if "--so-info" in sys.argv:
        return 0
    r = _escolher(rs)
    if not r:
        print("Nenhum GeoPackage encontrado nos recursos.")
        return 2
    os.makedirs(DESTINO, exist_ok=True)
    tmp = os.path.join(DESTINO, "download.part")
    print("A descarregar", r["url"])
    with _get(r["url"]) as resp, open(tmp, "wb") as f:
        shutil.copyfileobj(resp, f, 1 << 20)
    gp_tmp = os.path.join(DESTINO, "rgg.gpkg.part")
    if zipfile.is_zipfile(tmp):
        with zipfile.ZipFile(tmp) as z:
            nome = next((n for n in z.namelist() if n.lower().endswith(".gpkg") and ".." not in n), None)
            if not nome:
                print("O ZIP não contém nenhum .gpkg")
                return 3
            with z.open(nome) as src, open(gp_tmp, "wb") as dst:
                shutil.copyfileobj(src, dst, 1 << 20)
        os.remove(tmp)
    else:
        os.replace(tmp, gp_tmp)
    info = verificar_e_indexar(gp_tmp)
    if info["srs"] != 3763:
        print("Atenção: o GeoPackage não está em EPSG:3763 (srs", info["srs"], ") — não instalado.")
        return 4
    os.replace(gp_tmp, os.path.join(DESTINO, "rgg.gpkg"))
    print("Instalado:", json.dumps(info, ensure_ascii=False), "→", os.path.join(DESTINO, "rgg.gpkg"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
