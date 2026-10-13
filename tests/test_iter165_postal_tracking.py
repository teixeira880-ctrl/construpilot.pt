"""Iteration 165 — Merci Facteur tracking normalisation (accepted → printed → posted → delivered / returned)."""
import sys

import pytest

sys.path.append("/app/backend")

from engines import postal_tracking as pt


@pytest.mark.parametrize("payload, stage, returned", [
    ({"statutPrintEnvoi": "Traitement en attente", "suiviCourrier": []}, "accepted", False),
    ({"statutPrintEnvoi": "Impression en cours", "suiviCourrier": [{"lastState": ""}]}, "accepted", False),
    ({"statutPrintEnvoi": "Impression terminée", "suiviCourrier": [{"lastState": "", "pnd": None}]}, "printed", False),
    ({"statutPrintEnvoi": "Remis à La Poste", "suiviCourrier": []}, "posted", False),
    ({"statutPrintEnvoi": "Impression terminée", "suiviCourrier": [{"lastState": "Pris en charge par La Poste", "refTracking": "1A2B", "pnd": "0"}]}, "posted", False),
    ({"statutPrintEnvoi": "Impression terminée", "suiviCourrier": [{"lastState": "Courrier distribué au destinataire", "pnd": "0"}]}, "delivered", False),
    ({"statutPrintEnvoi": "Impression terminée", "suiviCourrier": [{"lastState": "En cours d'acheminement", "pnd": "1"}]}, "returned", True),
    ({"statutPrintEnvoi": "Impression terminée", "suiviCourrier": [{"lastState": "Retour à l'expéditeur : destinataire inconnu", "lastStateCode": {"event": "PND"}}]}, "returned", True),
])
def test_normalize_stage(payload, stage, returned):
    result = pt.normalize(payload)
    assert result["stage"] == stage and result["returned"] is returned
    assert result["stage_label"] == pt.LABELS[stage]


def test_normalize_keeps_tracking_reference_and_history():
    result = pt.normalize({"statutPrintEnvoi": "Impression terminée",
                           "suiviCourrier": [{"lastState": "Pris en charge", "refTracking": "6A12345", "historique": "h1\nh2"}]})
    assert result["tracking_ref"] == "6A12345" and result["history"] == "h1\nh2" and result["provider_status"] == "Pris en charge"
