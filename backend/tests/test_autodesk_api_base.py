"""APS_AUTOMATION_BASE_URL pode vir com ou sem região/versão: o endereço final é sempre …/da/<região>/v3 (sem duplicar)."""
import pytest

from engines import autodesk_client as C


@pytest.mark.parametrize("base", ["https://developer.api.autodesk.com/da", "https://developer.api.autodesk.com/da/",
                                  "https://developer.api.autodesk.com/da/us-east", "https://developer.api.autodesk.com/da/us-east/v3",
                                  "https://developer.api.autodesk.com/da/us-east/v3/"])
def test_api_base_never_duplicates_region(monkeypatch, base):
    monkeypatch.setenv("APS_AUTOMATION_BASE_URL", base)
    monkeypatch.setenv("APS_AUTOMATION_REGION", "us-east")
    assert C.api_base() == "https://developer.api.autodesk.com/da/us-east/v3"
