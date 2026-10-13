"""Rapport d'utilisation indicatif (Ed/Rd) partagé par les lots BET.

N'est PAS une vérification réglementaire : simple comparaison déterministe des
données saisies. Couleurs : ok (≤0.90), proche (≤1.0), à revoir (>1.0).
"""
from __future__ import annotations

DISCLAIMER = ("Razão indicativa Ed/Rd calculada a partir dos dados introduzidos — não vale como verificação regulamentar. A validar pelo engenheiro.")

_LABELS = {"ok": "OK (indicativo)", "proche": "próximo do limite (indicativo)",
           "a_revoir": "a rever (indicativo)", "non_calcule": "não calculado — dado em falta"}


def util_status(ratio: float | None) -> dict:
    if ratio is None:
        return {"ratio": None, "status": "non_calcule", "label": _LABELS["non_calcule"]}
    s = "ok" if ratio <= 0.90 else "proche" if ratio <= 1.0 else "a_revoir"
    return {"ratio": round(float(ratio), 3), "status": s, "label": _LABELS[s]}
