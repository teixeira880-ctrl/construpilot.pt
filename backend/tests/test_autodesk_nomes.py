"""14/11: as chaves Autodesk do .pt estão como AUTODESK_CLIENT_ID/SECRET — o cliente APS aceita os dois nomes."""
import pytest
from engines import autodesk_client as AC


def test_aceita_autodesk_e_defaults(monkeypatch):
    for k in ("APS_CLIENT_ID", "APS_CLIENT_SECRET", "APS_TOKEN_URL", "APS_BUCKET_KEY", "AUTODESK_BUCKET_KEY"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("AUTODESK_CLIENT_ID", "abc")
    monkeypatch.setenv("AUTODESK_CLIENT_SECRET", "xyz")
    assert AC.config("APS_CLIENT_ID") == "abc" and AC.config("APS_CLIENT_SECRET") == "xyz"
    assert AC.config("APS_TOKEN_URL").startswith("https://developer.api.autodesk.com/")
    assert AC.config("APS_BUCKET_KEY").startswith("construpilot-tmp-")    # nunca o bucket «persistent» do Plantas Pro
    monkeypatch.setenv("AUTODESK_BUCKET_KEY", "construpilot-plans-x")
    assert AC.config("APS_BUCKET_KEY") != "construpilot-plans-x"
    monkeypatch.delenv("AUTODESK_BUCKET_KEY")
    monkeypatch.setenv("APS_CLIENT_ID", "aps")
    assert AC.config("APS_CLIENT_ID") == "aps"                 # APS_* tem prioridade


def test_atividade_continua_obrigatoria(monkeypatch):
    monkeypatch.delenv("APS_ACTIVITY_QUALIFIED", raising=False)
    with pytest.raises(AC.AutodeskError):
        AC.config("APS_ACTIVITY_QUALIFIED")


def test_causa_da_preparacao_nao_e_engolida():
    from engines import autodesk_md
    txt = autodesk_md._causa(AC.AutodeskError("bucket_policy", "O armazenamento Autodesk deve ser privado e temporário.", status=None))
    assert "bucket_policy" in txt and "temporário" in txt
    assert autodesk_md._causa(ValueError("x")) == "ValueError"
