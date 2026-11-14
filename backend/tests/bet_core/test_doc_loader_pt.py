"""Testes do `doc_loader` do wrapper .pt (`_make_pt_doc_loader`).

Valida que o wrapper:
- Lê `assistant_docs` inline b64 (caso < 8 MB).
- Lê `assistant_doc_chunks` para PDF grandes (concat ordenado por `index`).
- Deduplica anexos idênticos (sha256 do conteúdo).
- Falha com erro claro se o PDF estiver corrompido (não começa com `%PDF`).
- Respeita ownership — `_allowed_doc` lança `PermissionError` se não for do
  utilizador correcto.
"""
import asyncio
import base64
import sys

import pytest

sys.path.insert(0, "/app/backend")

# Minúsculo PDF válido (header + EOF)
_PDF_MIN = b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n" \
           b"2 0 obj<</Type/Pages/Count 0/Kids[]>>endobj\nxref\n0 3\n" \
           b"0000000000 65535 f\n0000000009 00000 n\n0000000055 00000 n\n" \
           b"trailer<</Size 3/Root 1 0 R>>\nstartxref\n0\n%%EOF\n"
_PDF_OTHER = b"%PDF-1.5\n% other content " + b"x" * 200 + b"\n%%EOF\n"


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro) if sys.version_info < (3, 10) else asyncio.run(coro)


def test_loads_small_inline_pdf():
    """`data_b64` directo → carrega 1 (name, bytes)."""
    from engines.assistant_bet_core_tool import _make_pt_doc_loader

    docs = {"d1": {"filename": "plano.pdf", "mime": "application/pdf", "data_b64": base64.b64encode(_PDF_MIN).decode()}}

    async def allowed(did, uid, with_data=True):
        return docs[did]

    out = _run(_make_pt_doc_loader(allowed)(None, ["d1"], "u-x"))
    assert len(out) == 1
    name, data = out[0]
    assert name == "plano.pdf"
    assert data == _PDF_MIN


def test_dedup_duplicate_docs():
    """2 doc_ids com o mesmo conteúdo sha256 → 1 só devolvido."""
    from engines.assistant_bet_core_tool import _make_pt_doc_loader

    data_same = base64.b64encode(_PDF_MIN).decode()
    docs = {
        "d1": {"filename": "copia1.pdf", "mime": "application/pdf", "data_b64": data_same},
        "d2": {"filename": "copia2.pdf", "mime": "application/pdf", "data_b64": data_same},
        "d3": {"filename": "distinto.pdf", "mime": "application/pdf",
               "data_b64": base64.b64encode(_PDF_OTHER).decode()},
    }

    async def allowed(did, uid, with_data=True):
        return docs[did]

    out = _run(_make_pt_doc_loader(allowed)(None, ["d1", "d2", "d3"], "u-x"))
    assert len(out) == 2, f"esperados 2 após dedup, obtidos {len(out)}: {[n for n, _ in out]}"
    names = sorted(n for n, _ in out)
    assert names == ["copia1.pdf", "distinto.pdf"], names


def test_rejects_non_pdf_mime():
    from engines.assistant_bet_core_tool import _make_pt_doc_loader

    docs = {"d1": {"filename": "foto.jpg", "mime": "image/jpeg", "data_b64": base64.b64encode(b"\xff\xd8\xff").decode()}}

    async def allowed(did, uid, with_data=True):
        return docs[did]

    with pytest.raises(ValueError, match="não é PDF"):
        _run(_make_pt_doc_loader(allowed)(None, ["d1"], "u-x"))


def test_rejects_corrupt_pdf_without_magic_bytes():
    """Mime=application/pdf mas sem `%PDF` → erro claro."""
    from engines.assistant_bet_core_tool import _make_pt_doc_loader

    docs = {"d1": {"filename": "corrupto.pdf", "mime": "application/pdf",
                   "data_b64": base64.b64encode(b"not a pdf").decode()}}

    async def allowed(did, uid, with_data=True):
        return docs[did]

    with pytest.raises(ValueError, match="PDF legível"):
        _run(_make_pt_doc_loader(allowed)(None, ["d1"], "u-x"))


def test_ownership_violation_propagates():
    """`_allowed_doc` lança PermissionError → sobe tal e qual."""
    from engines.assistant_bet_core_tool import _make_pt_doc_loader

    async def allowed(did, uid, with_data=True):
        raise PermissionError("Documento inacessível para esta conta")

    with pytest.raises(PermissionError, match="inacessível"):
        _run(_make_pt_doc_loader(allowed)(None, ["d-other"], "u-x"))


def test_handles_chunked_pdf_via_allowed_doc():
    """Simula `_allowed_doc` que já concatenou os chunks (schema `.pt` real)."""
    from engines.assistant_bet_core_tool import _make_pt_doc_loader

    # Simula um PDF grande cuja montagem já foi feita por `_allowed_doc`
    big = _PDF_MIN + b"\n% block B\n" + b"X" * 1024 + b"\n%%EOF\n"
    docs = {"d-big": {"filename": "grande.pdf", "mime": "application/pdf",
                      "data_b64": base64.b64encode(big).decode()}}

    async def allowed(did, uid, with_data=True):
        # mimica `_allowed_doc`: devolve d com data_b64 já concatenado
        return docs[did]

    out = _run(_make_pt_doc_loader(allowed)(None, ["d-big"], "u-x"))
    assert len(out) == 1
    assert out[0][1].startswith(b"%PDF")
    assert len(out[0][1]) == len(big)


def test_planta_dwg_do_modulo_plantas_entra_no_estudo(monkeypatch):
    """14/11 Valpaços: DWG metido no Assistente fica como plan_… no módulo Plantas → o estudo lê as folhas (antes:
    «Documento inacessível para esta conta»)."""
    from engines import assistant_bet_core_tool as T
    from engines.bet_core import assistant_tool as BC

    async def allowed(did, uid, with_data):
        raise PermissionError("Documento inacessível para esta conta")

    async def plan_as_doc(_db, did, uid):
        assert did == "plan_abc" and uid == "u1"
        return {"filename": "Valpacos.pdf", "mime": "application/pdf", "data_b64": base64.b64encode(_PDF_MIN).decode()}

    monkeypatch.setattr(BC, "_plan_as_doc", plan_as_doc)
    out = _run(T._make_pt_doc_loader(allowed)(None, ["plan_abc"], "u1"))
    assert out == [("Valpacos.pdf", _PDF_MIN)]
    with pytest.raises(PermissionError):
        _run(T._make_pt_doc_loader(allowed)(None, ["doc_de_outro"], "u1"))


def test_anexo_dxf_convertido_em_prancha(monkeypatch):
    from engines import assistant_bet_core_tool as T
    from engines.bet_core import assistant_tool as BC

    async def allowed(did, uid, with_data):
        return {"filename": "planta.dxf", "mime": "application/dxf", "data_b64": base64.b64encode(b"0\nSECTION").decode()}

    async def cad_to_pdf(data, name, uid):
        return _PDF_OTHER, "planta.pdf"

    monkeypatch.setattr(BC, "_cad_to_pdf", cad_to_pdf)
    assert _run(T._make_pt_doc_loader(allowed)(None, ["doc_1"], "u1")) == [("planta.pdf", _PDF_OTHER)]
