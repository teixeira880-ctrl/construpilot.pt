"""Gera fixture sintética PNG para testes OCR (Fase E · Plans Pro).

Idempotente — só gera se o ficheiro ainda não existir ou se forçado via
`--force`. Usa `ImageFont.load_default()` para evitar dependências de
fontes TTF externas.
"""
from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

FIXTURE_DIR = Path(__file__).resolve().parent.parent / "tests" / "fixtures" / "plans_pro"
FIXTURE_PATH = FIXTURE_DIR / "thumbnail_moradia_sintetica.png"

TEXTOS = [
    "PLANTA MORADIA T3",
    "PP e=20",
    "C25/30",
    "AÇO A500NR",
    "VARÃO 12",
    "SAPATA 0,30x0,60",
    "L=3,50m",
    "H=2,70m",
    "COBERTURA TELHA LUSA",
    "AREA 120 m2",
]


def gerar(force: bool = False) -> Path:
    FIXTURE_DIR.mkdir(parents=True, exist_ok=True)
    if FIXTURE_PATH.exists() and not force:
        return FIXTURE_PATH
    # Canvas branco 1600x1600 + texto preto grande (facilita OCR)
    img = Image.new("RGB", (1600, 1600), "white")
    draw = ImageDraw.Draw(img)
    # Tenta usar DejaVuSans a 48px se disponível; cai para default
    fonte = None
    for caminho in (
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ):
        try:
            fonte = ImageFont.truetype(caminho, 60)
            break
        except Exception:  # noqa: BLE001
            continue
    if fonte is None:
        fonte = ImageFont.load_default()
    y = 80
    for linha in TEXTOS:
        draw.text((100, y), linha, fill="black", font=fonte)
        y += 120
    img.save(FIXTURE_PATH, format="PNG")
    return FIXTURE_PATH


if __name__ == "__main__":
    force = "--force" in sys.argv
    caminho = gerar(force=force)
    print(f"Fixture OCR em: {caminho}")
