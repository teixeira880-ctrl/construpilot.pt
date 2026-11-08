"""Gera um projeto «Edifício 3D» completo NO SERVIDOR, com os programas e APIs reais do ConstruPilot:

  1. coordenadas → altitude real e ortofotomapa (DGT / Google), via engines.urbanismo_pt.auto.geo;
  2. Blender (bpy) → modelo 3D real, GLB, renders Cycles de todas as vistas + antes/depois;
  3. motor de imagem ConstruPilot (image_studio) → acabamento fotorrealista SOBRE cada render Blender.

O projeto fica na conta indicada e aparece em /edificio-3d/<job_id>.

Uso (na pasta backend):
    python scripts/edificio3d_demo.py [--email conta@exemplo.pt] [--lat 41.56 --lon -8.42] [--azimute 180]
                                      [--qualidade rapida|normal|alta] [--sem-fotorrealista]
"""
import argparse
import asyncio
import os
import sys
import time

sys.path.insert(0, ".")
try:
    from dotenv import load_dotenv
    load_dotenv(".env")
except Exception:  # noqa: BLE001
    pass

from core.db import db  # noqa: E402
from engines.edificio3d import servico as S  # noqa: E402
from routes.edificio3d import QUAL  # noqa: E402


async def main(a):
    if S.blender_no_servidor() is None:
        sys.exit("Blender indisponível neste servidor: instale o módulo «bpy» compatível com este Python (ver LEIA-ME).")
    q = {"email": a.email.lower().strip()} if a.email else {"role": "admin"}
    u = await db.users.find_one(q, {"_id": 0, "user_id": 1, "email": 1})
    if not u:
        sys.exit(f"Utilizador não encontrado ({q}).")
    params = {"nome": a.nome, "morada": "", "latitude": a.lat, "longitude": a.lon, "altitude_m": None,
              "azimute_fachada_graus": a.azimute, "largura_m": 12.0, "profundidade_m": 9.0, "pisos": 2,
              "pe_direito_m": 3.0, "inclinacao_telhado_graus": 30.0, "beiral_m": 0.6, "render": QUAL[a.qualidade]}
    t0 = time.time()
    j = await S.criar_trabalho(u["user_id"], params, usar_arcgis=False)
    jid = j["job_id"]
    print(f"projeto {jid} criado para {u['email']}", flush=True)
    vistas_etapas = 0
    while True:
        await asyncio.sleep(5)
        d = await db[S.COL].find_one({"job_id": jid}, {"_id": 0, "estado": 1, "etapas": 1, "erro": 1})
        for e in (d.get("etapas") or [])[vistas_etapas:]:
            print("  •", e["texto"], flush=True)
        vistas_etapas = len(d.get("etapas") or [])
        if d["estado"] in ("concluido", "erro"):
            break
    if d["estado"] == "erro":
        sys.exit(f"ERRO: {d.get('erro')}")
    d = await db[S.COL].find_one({"job_id": jid}, {"_id": 0, "manifesto": 1})
    m = d["manifesto"]
    print(f"Blender OK ({m.get('motor')}): {m['geometria']['vertices']} vértices, {len(m['imagens'])} renders, "
          f"{time.time() - t0:.0f} s", flush=True)
    if not a.sem_fotorrealista:
        for vista in [v for v in m["imagens"] if not v.startswith("antes_")]:
            try:
                r = await S.gerar_fotorrealista(jid, vista)
                print(f"  fotorrealista {vista}: {r['ficheiro']}", flush=True)
            except Exception as e:  # noqa: BLE001
                print(f"  fotorrealista {vista}: FALHOU ({e})", flush=True)
    print(f"RESULTADO job_id={jid} url=/edificio-3d/{jid} duracao_s={time.time() - t0:.0f}", flush=True)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--email", default="", help="conta destino (por omissão: a primeira conta admin)")
    ap.add_argument("--nome", default="Moradia contemporânea — demonstração")
    ap.add_argument("--lat", type=float, default=41.5617)
    ap.add_argument("--lon", type=float, default=-8.4021)
    ap.add_argument("--azimute", type=float, default=180.0)
    ap.add_argument("--qualidade", default="normal", choices=list(QUAL))
    ap.add_argument("--sem-fotorrealista", action="store_true")
    asyncio.run(main(ap.parse_args()))
