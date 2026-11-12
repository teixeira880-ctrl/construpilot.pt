"""Interruptor único das imagens 3D (perspetivas, renders físicos, fotos fotorrealistas) — .pt.

Pedido do Martinho (12/11/2026, dia de demonstração): «anula todas as imagens 3D no pt». Desligadas por defeito; para voltar
a ligar: CP_3D_IMAGES=1 no .env. Os orçamentos e estudos continuam com as imagens das PLANTAS (não são 3D).
"""
import os


def enabled() -> bool:
    return str(os.environ.get("CP_3D_IMAGES") or "").strip().lower() in ("1", "true", "yes", "on")
