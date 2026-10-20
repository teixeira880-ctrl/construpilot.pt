"""Rapport d'utilisation indicatif (Ed/Rd) partagé par les lots BET.

N'est PAS une vérification réglementaire : simple comparaison déterministe des
données saisies. Couleurs : ok (≤0.90), proche (≤1.0), à revoir (>1.0).
"""
from __future__ import annotations

DISCLAIMER = ("Rapport indicatif Ed/Rd calculé à partir des données saisies — "
              "ne vaut pas vérification réglementaire. À valider par l'ingénieur.")

_LABELS = {"ok": "OK (indicatif)", "proche": "proche de la limite (indicatif)",
           "a_revoir": "à revoir (indicatif)", "non_calcule": "non calculé — donnée manquante"}


def util_status(ratio: float | None) -> dict:
    if ratio is None:
        return {"ratio": None, "status": "non_calcule", "label": _LABELS["non_calcule"]}
    s = "ok" if ratio <= 0.90 else "proche" if ratio <= 1.0 else "a_revoir"
    return {"ratio": round(float(ratio), 3), "status": s, "label": _LABELS[s]}
