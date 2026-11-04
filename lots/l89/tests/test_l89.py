"""Lot 89 — un ODA_FILE_CONVERTER absent ne bloque plus la conversion DWG ; un ODA présent reste prioritaire."""
import asyncio
import importlib
import os

import pytest

os.environ.setdefault("CLOUDCONVERT_API_BASE", "https://api.cloudconvert.com/v2")
os.environ.setdefault("CLOUDCONVERT_SYNC_BASE", "https://sync.api.cloudconvert.com/v2")
from engines import dwg_convert as dc  # noqa: E402

DWG = b"AC1032" + b"\0" * 64


def _no_local(monkeypatch):
    try:
        local = importlib.import_module("engines.dwg_local")
        monkeypatch.setattr(local, "available", lambda: False)
    except ImportError:
        pass


def test_missing_oda_falls_through(monkeypatch, tmp_path):
    monkeypatch.setenv("ODA_FILE_CONVERTER", str(tmp_path / "absent" / "ODAFileConverter"))
    monkeypatch.delenv("APS_DWG_ENABLED", raising=False)
    monkeypatch.delenv("CLOUDCONVERT_API_KEY", raising=False)
    _no_local(monkeypatch)
    with pytest.raises(RuntimeError) as exc:
        asyncio.run(dc.dwg_to_dxf(DWG))
    assert "ODA_FILE_CONVERTER" not in str(exc.value)   # message « convertissez en DXF », pas le chemin ODA


def test_present_oda_still_used(monkeypatch):
    monkeypatch.setenv("ODA_FILE_CONVERTER", "/configured/oda")
    _no_local(monkeypatch)
    monkeypatch.setattr(dc, "_local_dwg_to_dxf", lambda b: b"0\nEOF\n")
    out = asyncio.run(dc.dwg_to_dxf(DWG))
    assert out == b"0\nEOF\n"
