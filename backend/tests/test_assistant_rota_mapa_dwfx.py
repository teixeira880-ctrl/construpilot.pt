"""Coimbra 24/11 : pedido de mapa com DWFX anexado → primeiro passo forçado medir_arquitetura_dwfx com os ids reais."""
import asyncio
import types

from routes import assistant as A


class _Cur:
    def __init__(self, rows): self.rows = rows
    def __aiter__(self):
        self._it = iter(self.rows); return self
    async def __anext__(self):
        try: return next(self._it)
        except StopIteration: raise StopAsyncIteration


class _Docs:
    rows = [{"user_id": "u", "doc_id": "doc_dw", "filename": "ARQ08.dwfx", "mime": "model/vnd.dwfx+xps"},
            {"user_id": "u", "doc_id": "doc_e", "filename": "DUEL_COIMBRA.pdf", "mime": "application/pdf"},
            {"user_id": "x", "doc_id": "doc_outro", "filename": "y.dwfx", "mime": "model/vnd.dwfx+xps"}]

    def find(self, q, proj=None):
        ids = q["doc_id"]["$in"]
        return _Cur([d for d in self.rows if d["user_id"] == q["user_id"] and d["doc_id"] in ids])


class _DB:
    assistant_docs = _Docs()


TOOLS = [{"name": "medir_arquitetura_dwfx"}, {"name": "read_document"}]


def test_mapa_com_dwfx_forca_o_motor(monkeypatch):
    monkeypatch.setattr(A, "db", _DB())
    body = types.SimpleNamespace(text="le estes ficheiros e faz um mapa de quantidades completo e um orçamento", doc_ids=[])
    tool, txt = asyncio.run(A._rota_mapa_dwfx(body, {"user_id": "u"}, {"active_docs": ["doc_dw", "doc_e", "doc_outro"]}, TOOLS))
    assert tool == "medir_arquitetura_dwfx"
    assert '["doc_dw"]' in txt and '["doc_e"]' in txt and "doc_outro" not in txt


def test_sem_dwfx_ou_sem_pedido_de_mapa_nao_forca(monkeypatch):
    monkeypatch.setattr(A, "db", _DB())
    b1 = types.SimpleNamespace(text="olá, qual é o prazo?", doc_ids=["doc_dw"])
    assert asyncio.run(A._rota_mapa_dwfx(b1, {"user_id": "u"}, {}, TOOLS)) == (None, "")
    b2 = types.SimpleNamespace(text="faz o mapa de quantidades", doc_ids=["doc_e"])
    assert asyncio.run(A._rota_mapa_dwfx(b2, {"user_id": "u"}, {}, TOOLS)) == (None, "")
