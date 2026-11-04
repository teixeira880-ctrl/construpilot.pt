"""Lot 89 — un ODA_FILE_CONVERTER absent ne bloque plus la conversion DWG ; un ODA présent reste prioritaire."""
import asyncio

import pytest

from engines import dwg_convert as dc

DWG = b"AC1032" + b"\0" * 64


def test_missing_oda_falls_through(monkeypatch, tmp_path):
    monkeypatch.setenv("ODA_FILE_CONVERTER", str(tmp_path / "absent" / "ODAFileConverter"))
    monkeypatch.delenv("APS_DWG_ENABLED", raising=False)
    monkeypatch.delenv("CLOUDCONVERT_API_KEY", raising=False)
    monkeypatch.setattr(dc, "dwg_local", None, raising=False)
    with pytest.raises(RuntimeError) as exc:
        asyncio.run(dc.dwg_to_dxf(DWG))
    assert "ODA_FILE_CONVERTER" not in str(exc.value)   # message « convertissez en DXF », pas le chemin ODA


def test_present_oda_still_used(monkeypatch):
    monkeypatch.setenv("ODA_FILE_CONVERTER", "/configured/oda")
    monkeypatch.setattr(dc, "_local_dwg_to_dxf", lambda b: b"0\nEOF\n")
    out = asyncio.run(dc.dwg_to_dxf(DWG))
    assert out == b"0\nEOF\n"
