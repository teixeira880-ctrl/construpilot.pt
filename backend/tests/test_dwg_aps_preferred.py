"""APS_DWG_PREFERRED=true: o AutoCAD da Autodesk é tentado primeiro; se falhar, o conversor local continua a funcionar."""
import asyncio
import os

os.environ.setdefault("CLOUDCONVERT_API_BASE", "https://example.invalid")
os.environ.setdefault("CLOUDCONVERT_SYNC_BASE", "https://example.invalid")

from engines import dwg_convert  # noqa: E402

DWG = b"AC1032" + b"\0" * 100
DXF_LOCAL = b"  0\nSECTION\n  2\nHEADER\n  0\nENDSEC\n  0\nEOF\n"
DXF_APS = b"  0\nSECTION\n  2\nHEADER\n999\naps\n  0\nENDSEC\n  0\nEOF\n"


def _setup(monkeypatch, aps):
    import engines.autodesk_dwg as A
    from engines import dwg_local
    monkeypatch.setattr(dwg_convert, "_oda_ok", lambda: False)
    monkeypatch.setattr(dwg_local, "available", lambda: True)
    monkeypatch.setattr(dwg_local, "dwg_to_dxf_hint", lambda b: (DXF_LOCAL, None))
    monkeypatch.setattr(A, "convert", aps)
    monkeypatch.setenv("APS_DWG_ENABLED", "true")


def test_preferred_uses_autodesk_first(monkeypatch):
    async def aps(data, *, user_id):
        return DXF_APS, {"provider": "autodesk"}
    _setup(monkeypatch, aps)
    monkeypatch.setenv("APS_DWG_PREFERRED", "true")
    prov = {}
    assert asyncio.run(dwg_convert.dwg_to_dxf(DWG, user_id="u", provenance=prov)) == DXF_APS
    assert prov["provider"] == "autodesk"


def test_preferred_failure_falls_back_to_local(monkeypatch):
    async def aps(data, *, user_id):
        raise RuntimeError("autodesk em baixo")
    _setup(monkeypatch, aps)
    monkeypatch.setenv("APS_DWG_PREFERRED", "true")
    prov = {}
    assert asyncio.run(dwg_convert.dwg_to_dxf(DWG, user_id="u", provenance=prov)) == DXF_LOCAL
    assert prov["provider"] == "libredwg" and prov["fallback_reason"].startswith("aps_preferred_failed")


def test_without_flag_local_first_as_before(monkeypatch):
    async def aps(data, *, user_id):
        raise AssertionError("não devia chamar a Autodesk")
    _setup(monkeypatch, aps)
    monkeypatch.delenv("APS_DWG_PREFERRED", raising=False)
    assert asyncio.run(dwg_convert.dwg_to_dxf(DWG, user_id="u")) == DXF_LOCAL
