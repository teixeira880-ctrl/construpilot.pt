"""Corta o GeoPackage das RGG do BUPi em mosaicos de 2 km e publica-os no Tigris (TIGRIS_BUCKET).

Uso (a partir de backend/):
  python scripts/bupi_rgg_mosaicos.py --verificar             só mostra recurso, tamanhos, disco livre e acesso ao bucket
  python scripts/bupi_rgg_mosaicos.py --seco                  descarrega e corta, mas não envia nada (conta mosaicos)
  python scripts/bupi_rgg_mosaicos.py                         descarrega, corta e publica; apaga os temporários no fim
  python scripts/bupi_rgg_mosaicos.py --gpkg /caminho/x.gpkg  usa um GeoPackage já existente
  opções: --bbox minx,miny,maxx,maxy (PT-TM06, para testar uma zona) · --pasta /tmp/x (temporários)

Disco: verifica ANTES de descarregar e ANTES de descomprimir se há espaço (zip + GeoPackage + 400 MB de margem) e
aborta se não houver. Os mosaicos vão diretos para o bucket, sem ficar em disco. O manifesto (bupi/rgg/atual.json) só é
escrito no fim, por isso o backend continua a usar a versão anterior até a nova estar completa.
"""
from __future__ import annotations

import argparse
import concurrent.futures as cf
import json
import os
import shutil
import sqlite3
import sys
import time
import urllib.request
import zipfile

sys.path.insert(0, os.path.normpath(os.path.join(os.path.dirname(__file__), "..")))

from engines.terrenos_pt import rgg_limite as RL  # noqa: E402
from engines.terrenos_pt import rgg_mosaicos as MO  # noqa: E402

import importlib.util  # noqa: E402

_spec = importlib.util.spec_from_file_location("bupi_dl", os.path.join(os.path.dirname(__file__), "bupi_rgg_descarregar.py"))
DL = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(DL)

MARGEM = 400 * 1024 * 1024


def livre(p: str) -> int:
    return shutil.disk_usage(p).free


def gb(n) -> str:
    return f"{(n or 0) / 1024 ** 3:.2f} GB"


def verificar_bucket() -> str:
    if not MO.configurado():
        return "NAO configurado (TIGRIS_BUCKET em falta)"
    try:
        MO.cliente().list_objects_v2(Bucket=MO._bucket(), Prefix=MO.PREFIXO + "/", MaxKeys=1)
        return f"OK ({MO._bucket()})"
    except Exception as e:  # noqa: BLE001
        return f"ERRO {type(e).__name__}: {str(e)[:160]}"


def obter_gpkg(pasta: str, recurso: dict, seco_info: bool = False) -> str:
    tam = int(recurso.get("tamanho") or 0)
    if livre(pasta) < tam + MARGEM:
        raise SystemExit(f"Disco insuficiente para descarregar: livre {gb(livre(pasta))}, preciso {gb(tam + MARGEM)}")
    zp = os.path.join(pasta, "rgg.zip")
    print("A descarregar", recurso["url"], gb(tam))
    with DL._get(recurso["url"]) as resp, open(zp, "wb") as f:
        shutil.copyfileobj(resp, f, 1 << 20)
    with zipfile.ZipFile(zp) as z:
        info = next((i for i in z.infolist() if i.filename.lower().endswith(".gpkg") and ".." not in i.filename), None)
        if not info:
            raise SystemExit("O ZIP não contém nenhum .gpkg")
        print("GeoPackage dentro do ZIP:", info.filename, gb(info.file_size))
        if livre(pasta) < info.file_size + MARGEM:
            os.remove(zp)
            raise SystemExit(f"Disco insuficiente para descomprimir: livre {gb(livre(pasta))}, preciso {gb(info.file_size + MARGEM)}")
        gp = os.path.join(pasta, "rgg.gpkg")
        with z.open(info) as src, open(gp, "wb") as dst:
            shutil.copyfileobj(src, dst, 1 << 20)
    os.remove(zp)
    return gp


def mosaicos(gp: str, bbox=None):
    """Gera (ix, iy, itens) para cada mosaico com polígonos."""
    con = sqlite3.connect(f"file:{gp}?mode=ro", uri=True)
    tab, col = RL._tabela(con)
    rt = f"rtree_{tab}_{col}"
    pk = next((c[1] for c in con.execute(f'PRAGMA table_info("{tab}")') if c[5] == 1), "fid")
    tem_area = any(c[1] == "area" for c in con.execute(f'PRAGMA table_info("{tab}")'))
    minx, miny, maxx, maxy = bbox or con.execute(f'SELECT MIN(minx), MIN(miny), MAX(maxx), MAX(maxy) FROM "{rt}"').fetchone()
    T = MO.TAMANHO
    ix0, iy0 = MO.chave_mosaico(minx, miny)
    ix1, iy1 = MO.chave_mosaico(maxx, maxy)
    sel = (f'SELECT t."{pk}", t."{col}"' + (', t."area"' if tem_area else ", 0") +
           f' FROM "{tab}" t JOIN "{rt}" r ON r.id = t."{pk}" WHERE r.minx <= ? AND r.maxx >= ? AND r.miny <= ? AND r.maxy >= ?')
    try:
        for ix in range(ix0, ix1 + 1):
            for iy in range(iy0, iy1 + 1):
                x0, y0 = ix * T, iy * T
                rows = con.execute(sel, (x0 + T, x0, y0 + T, y0)).fetchall()
                itens = [(f, a or 0.0, RL._wkb_de_gpkg(b)) for f, b, a in rows]
                itens = [i for i in itens if i[2]]
                if itens:
                    yield ix, iy, itens
    finally:
        con.close()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--verificar", action="store_true")
    ap.add_argument("--seco", action="store_true")
    ap.add_argument("--gpkg")
    ap.add_argument("--bbox")
    ap.add_argument("--pasta", default=os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "data", "bupi")))
    a = ap.parse_args()
    os.makedirs(a.pasta, exist_ok=True)
    rs = DL.recursos()
    rec = DL._escolher(rs)
    print("Recurso:", json.dumps(rec, ensure_ascii=False))
    print("Disco livre em", a.pasta, ":", gb(livre(a.pasta)))
    print("Bucket:", verificar_bucket())
    if a.verificar:
        return 0
    if not a.seco and not verificar_bucket().startswith("OK"):
        print("Sem acesso ao bucket: use --seco para testar o corte sem publicar.")
        return 2
    gp = a.gpkg or obter_gpkg(a.pasta, rec)
    apagar = not a.gpkg
    try:
        info = DL.verificar_e_indexar(gp)
        print("GeoPackage:", info)
        if info["srs"] != 3763:
            print("Não está em EPSG:3763 — abortado.")
            return 3
        versao = (rec or {}).get("atualizado", "")[:10] or time.strftime("%Y-%m-%d")
        versao = versao.replace(":", "-")
        bbox = tuple(float(v) for v in a.bbox.split(",")) if a.bbox else None
        n_mos, n_pol, bytes_tot, t0 = 0, 0, 0, time.time()

        def enviar(ix, iy, itens):
            corpo = MO.codificar(itens)
            if not a.seco:
                MO.cliente().put_object(Bucket=MO._bucket(), Key=f"{MO.PREFIXO}/{versao}/{ix}_{iy}.bin.gz", Body=corpo,
                                        ContentType="application/octet-stream")
            return len(corpo)

        with cf.ThreadPoolExecutor(max_workers=12) as ex:
            futs = []
            for ix, iy, itens in mosaicos(gp, bbox):
                n_mos += 1
                n_pol += len(itens)
                futs.append(ex.submit(enviar, ix, iy, itens))
                if len(futs) >= 200:
                    bytes_tot += sum(f.result() for f in futs)
                    futs = []
                    print(f"  {n_mos} mosaicos, {n_pol} polígonos, {bytes_tot / 1024 ** 2:.0f} MB, {time.time() - t0:.0f} s", flush=True)
            bytes_tot += sum(f.result() for f in futs)
        man = {"versao": versao, "data": versao, "tamanho_m": MO.TAMANHO, "mosaicos": n_mos, "poligonos_em_mosaicos": n_pol,
               "elementos_gpkg": info["elementos"], "bytes": bytes_tot, "fonte": RL.FONTE_GPKG, "criado": time.strftime("%Y-%m-%dT%H:%M:%S")}
        print("Manifesto:", json.dumps(man, ensure_ascii=False))
        if not a.seco:
            MO.cliente().put_object(Bucket=MO._bucket(), Key=f"{MO.PREFIXO}/atual.json", Body=json.dumps(man).encode(),
                                    ContentType="application/json")
            print("Publicado.")
        return 0
    finally:
        if apagar and os.path.exists(gp):
            os.remove(gp)
            print("GeoPackage temporário apagado.")


if __name__ == "__main__":
    sys.exit(main())
