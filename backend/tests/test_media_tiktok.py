"""GET /api/media/tiktok nunca devolve 500: cache vazia + exceções de storage
devolvem HTTP 200 com corpo vazio e header X-Media-Configured=false, para que
o frontend não quebre o player quando o ficheiro de marketing não está presente.
"""
import asyncio

from fastapi import Request

from routes import media as media_route


class _StubRequest:
    def __init__(self, headers=None):
        self.headers = headers or {}


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro) if False else asyncio.new_event_loop().run_until_complete(coro)


def test_tiktok_sem_configuracao_devolve_200(monkeypatch):
    """Sem storage ativo (get_object falha), handler responde 200 e nunca propaga 500."""
    media_route._cache = None

    def _boom(path):
        raise RuntimeError("storage indisponível no ambiente de teste")

    monkeypatch.setattr(media_route.storage, "get_object", _boom)
    resp = _run(media_route.tiktok(_StubRequest()))
    assert resp.status_code == 200
    assert resp.media_type == "video/mp4"
    assert resp.body == b""
    assert resp.headers.get("x-media-configured") == "false"


def test_tiktok_com_dados_devolve_video(monkeypatch):
    """Quando o storage responde, mantém-se o comportamento inalterado (video/mp4)."""
    media_route._cache = None
    payload = b"\x00" * 2048

    def _ok(path):
        return payload, "video/mp4"

    monkeypatch.setattr(media_route.storage, "get_object", _ok)
    resp = _run(media_route.tiktok(_StubRequest()))
    assert resp.status_code == 200
    assert resp.media_type == "video/mp4"
    assert resp.body == payload
    assert "x-media-configured" not in {k.lower() for k in resp.headers.keys()}
