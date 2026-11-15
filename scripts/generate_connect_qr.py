"""Gera os três QR Codes do stand Web Summit (cliente, investidor, parceiro) para construpilot.pt.

Os URLs devem ser verificados depois da publicação (abrir cada um num telemóvel).
Uso: pip install segno && python3 scripts/generate_connect_qr.py
"""
from pathlib import Path

import segno

BASE = "https://construpilot.pt/connect"
OUT = Path(__file__).resolve().parents[1] / "frontend/public/connect"
URLS = {
    "client": f"{BASE}/client?source=websummit2026&utm_source=websummit2026&utm_medium=qr&utm_campaign=stand_client",
    "investor": f"{BASE}/investor?source=websummit2026&utm_source=websummit2026&utm_medium=qr&utm_campaign=stand_investor",
    "partner": f"{BASE}/partner?source=websummit2026&utm_source=websummit2026&utm_medium=qr&utm_campaign=stand_partner",
}

OUT.mkdir(parents=True, exist_ok=True)
for name, url in URLS.items():
    qr = segno.make(url, error="m")
    qr.save(OUT / f"qr-{name}.svg", scale=8, border=2, dark="#1f3a2a", light="#ffffff", xmldecl=False, svgns=True, title=url)
    qr.save(OUT / f"qr-{name}.png", scale=12, border=2, dark="#1f3a2a", light="#ffffff")
    print(name, url)
(OUT / "qr-urls.txt").write_text("\n".join(f"{k}: {v}" for k, v in URLS.items()) + "\n", encoding="utf-8")
