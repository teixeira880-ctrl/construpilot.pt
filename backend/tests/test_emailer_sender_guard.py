"""Testes do guard de remetente (`mail_sender_config` + `emailer`)."""
import os
from unittest.mock import AsyncMock, patch

import pytest

from engines.mail_sender_config import (
    FORBIDDEN_DOMAIN_SUFFIXES,
    ForbiddenSenderError,
    Market,
    assert_valid_sender,
    get_sender,
    is_production,
)


# ---------------------------------------------------------------------------
# a) ENV=production + remetente .local → levanta ForbiddenSenderError
# ---------------------------------------------------------------------------
def test_production_blocks_local_sender(monkeypatch):
    monkeypatch.setenv("ENV", "production")
    monkeypatch.setenv("SENDER_PT_FROM", "no-reply@construpilot.local")
    with pytest.raises(ForbiddenSenderError) as excinfo:
        get_sender(Market.PT)
    assert "construpilot.local" in str(excinfo.value).lower() or "proibido" in str(excinfo.value).lower()


def test_production_blocks_localhost_sender(monkeypatch):
    monkeypatch.setenv("ENV", "production")
    with pytest.raises(ForbiddenSenderError):
        get_sender(Market.PT, override={"from": "x@localhost"})


def test_production_blocks_example_com(monkeypatch):
    monkeypatch.setenv("ENV", "production")
    with pytest.raises(ForbiddenSenderError):
        get_sender(Market.PT, override={"from": "test@example.com"})


def test_dev_warns_but_does_not_block(monkeypatch, caplog):
    monkeypatch.setenv("ENV", "development")
    # Em dev, `.local` passa — mas regista warning
    sender = get_sender(Market.PT, override={"from": "dev@thing.local"})
    assert sender["from"] == "dev@thing.local"
    # Verifica log
    assert any("thing.local" in r.message.lower() or "seria bloqueado" in r.message.lower()
               for r in caplog.records if r.levelname == "WARNING")


# ---------------------------------------------------------------------------
# b) Default sender = info@construpilot.pt
# ---------------------------------------------------------------------------
def test_default_sender_is_info_construpilot_pt(monkeypatch):
    # Remove envs que podiam influenciar
    for k in ("SENDER_PT_FROM", "SENDER_PT_REPLY", "SENDER_PT_NAME",
              "SENDER_EMAIL", "ENV"):
        monkeypatch.delenv(k, raising=False)
    sender = get_sender(Market.PT)
    assert sender["from"] == "info@construpilot.pt"
    assert sender["name"] == "ConstruPilot"
    assert sender["reply_to"] == "info@construpilot.pt"


def test_env_sender_pt_from_overrides_default(monkeypatch):
    monkeypatch.setenv("SENDER_PT_FROM", "campanhas@construpilot.pt")
    monkeypatch.delenv("ENV", raising=False)
    sender = get_sender(Market.PT)
    assert sender["from"] == "campanhas@construpilot.pt"


def test_format_from_header():
    from engines.mail_sender_config import format_from_header
    assert format_from_header({"name": "ConstruPilot", "from": "info@construpilot.pt"}) \
        == "ConstruPilot <info@construpilot.pt>"
    assert format_from_header({"name": "", "from": "x@y.pt"}) == "x@y.pt"


# ---------------------------------------------------------------------------
# c) Resend devolve erro → estado "failed"
# ---------------------------------------------------------------------------
@pytest.mark.anyio
async def test_resend_api_error_marks_failed(monkeypatch):
    monkeypatch.setenv("RESEND_API_KEY", "re_test_fake_key")
    monkeypatch.delenv("ENV", raising=False)
    monkeypatch.setenv("SENDER_PT_FROM", "info@construpilot.pt")

    logged = []

    async def _fake_log(**kwargs):
        logged.append(kwargs)

    with patch("engines.emailer._log_email_event", side_effect=_fake_log), \
         patch("resend.Emails.send",
               side_effect=Exception("domain not verified")):
        from engines.emailer import send_email
        with pytest.raises(Exception) as ei:
            await send_email("alvo@construpilot.pt", "assunto", "<p>x</p>")
        assert "domain not verified" in str(ei.value)

    # Deve ter sido logado como "failed"
    assert any(e["status"] == "failed" for e in logged), f"logged={logged}"
    assert any("domain not verified" in (e.get("error") or "") for e in logged)


# ---------------------------------------------------------------------------
# d) Resposta Resend com id → status "accepted" (NUNCA "delivered")
# ---------------------------------------------------------------------------
@pytest.mark.anyio
async def test_resend_api_accepted_marks_accepted_not_delivered(monkeypatch):
    monkeypatch.setenv("RESEND_API_KEY", "re_test_fake_key")
    monkeypatch.delenv("ENV", raising=False)
    monkeypatch.setenv("SENDER_PT_FROM", "info@construpilot.pt")

    logged = []

    async def _fake_log(**kwargs):
        logged.append(kwargs)

    with patch("engines.emailer._log_email_event", side_effect=_fake_log), \
         patch("resend.Emails.send", return_value={"id": "re_abc_123"}):
        from engines.emailer import send_email
        result = await send_email("alvo@construpilot.pt", "assunto", "<p>x</p>")

    assert result["ok"] is True
    assert result["id"] == "re_abc_123"
    assert result["status"] == "accepted"
    assert any(e["status"] == "accepted" and e["resend_id"] == "re_abc_123"
               for e in logged), f"logged={logged}"
    # Importante: NUNCA logar "delivered" apenas porque API aceitou
    assert not any(e["status"] == "delivered" for e in logged)


@pytest.mark.anyio
async def test_production_send_with_local_env_raises_before_api_call(monkeypatch):
    """Garante que em produção o guard dispara ANTES de chamar Resend."""
    monkeypatch.setenv("ENV", "production")
    monkeypatch.setenv("RESEND_API_KEY", "re_test_fake_key")
    monkeypatch.setenv("SENDER_PT_FROM", "no-reply@construpilot.local")

    api_called = {"n": 0}

    def _spy(*a, **kw):
        api_called["n"] += 1
        return {"id": "should_not_happen"}

    with patch("resend.Emails.send", side_effect=_spy):
        from engines.emailer import send_email
        with pytest.raises(ForbiddenSenderError):
            await send_email("alvo@construpilot.pt", "assunto", "<p>x</p>")

    assert api_called["n"] == 0, "API Resend NÃO devia ter sido chamada!"


# ---------------------------------------------------------------------------
# Config sanity checks
# ---------------------------------------------------------------------------
def test_forbidden_suffixes_include_local():
    assert ".local" in FORBIDDEN_DOMAIN_SUFFIXES
    assert "localhost" in FORBIDDEN_DOMAIN_SUFFIXES or ".localhost" in FORBIDDEN_DOMAIN_SUFFIXES


def test_assert_valid_sender_rejects_malformed(monkeypatch):
    monkeypatch.setenv("ENV", "production")
    with pytest.raises(ForbiddenSenderError):
        assert_valid_sender("not-an-email")
    with pytest.raises(ForbiddenSenderError):
        assert_valid_sender("")


def test_is_production_flags():
    import importlib
    import engines.mail_sender_config as m
    for v in ("production", "PROD", "prod"):
        os.environ["ENV"] = v
        importlib.reload(m)  # garante nova leitura
        assert m.is_production() is True
    for v in ("development", "dev", "", "test"):
        os.environ["ENV"] = v
        importlib.reload(m)
        assert m.is_production() is False
    os.environ.pop("ENV", None)
