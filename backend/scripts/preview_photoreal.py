"""Pré-visualização: render geométrico (Mitsuba, rápido) + fotorrealismo IA da Home A, como em produção.
Uso: cd backend && python scripts/preview_photoreal.py /tmp/preview  → base_*.png, foto_*.jpg e tempos."""
import asyncio
import copy
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"))
    from engines.calc_lots import gros_oeuvre, pacote_ua, ucrania
    from engines import photoreal as PR
    pasta = sys.argv[1] if len(sys.argv) > 1 else "/tmp/preview"
    os.makedirs(pasta, exist_ok=True)
    p = pacote_ua.parametros("home_a_rezult_kyiv")
    m = gros_oeuvre.calcular(copy.deepcopy(p["modelo_estrutural"]))["modelo"]
    t = time.time()
    base = ucrania._render_isolado(m, p.get("render_opcoes") or {}, 1280, 720, 24, 90, 240)
    print("render geometrico", len(base), "vistas", round(time.time() - t, 1), "s")
    for n, b in base:
        open(os.path.join(pasta, f"base_{n}.png"), "wb").write(b)
    usados = []
    orig = PR.render

    async def espia(*a, **k):
        r = await orig(*a, **k)
        usados.append(r[1] if r else None)
        return r
    PR.render = espia
    t = time.time()
    fotos = ucrania._fotorrealismo(base)
    print("fotorrealismo IA", round(time.time() - t, 1), "s, motores:", usados)
    for n, b in fotos:
        open(os.path.join(pasta, f"foto_{n}.jpg"), "wb").write(b)
    print("ok", sorted(os.listdir(pasta)))
