"""Papel de cada camada do CAD (paredes, trama de corte, traço fino, louças, cozinha) a partir do NOME da camada.
Os nomes variam de gabinete para gabinete : as expressões cobrem PT/FR/EN ; o utilizador pode forçar com `mapa_camadas`."""
from __future__ import annotations

import re
import unicodedata

PADROES = {
    "trama": r"trama|hatch|hachur|achur",
    "muros": r"muros?\b|vedac|cl[oô]ture|fence|boundary",
    "paredes": r"parede|wall|\bmur\b|alvenar|cloison|tijolo",
    "fino": r"fino|thin|\bfin\b|v[aã]os?\b|janela|window|fenetre|caixilh|tracofino",
    "sanitarios": r"sanit|\bwc\b|louc|appareil",
    "cozinha": r"cozinha|kitchen|cuisine|bancada",
    "texto": r"texto|text|txt",
}


def _norm(s: str) -> str:
    return unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode().lower()


def papel(nome: str, forcado: dict | None = None) -> str | None:
    if forcado and nome in forcado:
        return forcado[nome]
    n = _norm(nome)
    if re.search(PADROES["trama"], n):
        return "trama"
    for k in ("muros", "paredes", "sanitarios", "cozinha", "fino", "texto"):
        if re.search(_norm(PADROES[k]), n):
            return k
    return None


def mapa(camadas, forcado: dict | None = None) -> dict:
    """Se houver uma trama «de corte» (corte/cut/coupe/section), só essa conta como parede cortada : as outras tramas são
    revestimentos, pavimentos ou terreno."""
    m = {c: papel(c, forcado) for c in camadas}
    corte = [c for c, p in m.items() if p == "trama" and re.search(r"corte|cut|coupe|section|secc", _norm(c))]
    if corte:
        for c, p in m.items():
            if p == "trama" and c not in corte and not (forcado and c in forcado):
                m[c] = None
    return m
