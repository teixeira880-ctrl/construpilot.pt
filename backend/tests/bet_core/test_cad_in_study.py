"""13/11: um DWG/DXF metido no Assistente entra no estudo (convertido em prancha PDF), em vez de ser recusado."""
import asyncio
import base64
import io

import ezdxf

from engines.bet_core import assistant_tool
from tests.bet_core.test_assistant_tool import DB


def _dxf() -> bytes:
    d = ezdxf.new(units=6)               # metros
    m = d.modelspace()
    m.add_lwpolyline([(0, 0), (12, 0), (12, 9), (0, 9)], close=True)
    m.add_line((6, 0), (6, 9))
    m.add_text("PLANTA DO RES-DO-CHAO", dxfattribs={"height": 0.4}).set_placement((1, 10))
    buf = io.StringIO()
    d.write(buf)
    return buf.getvalue().encode()


def test_dxf_attachment_becomes_pdf_for_the_study():
    db = DB()
    db.assistant_docs.docs.append({"doc_id": "d1", "user_id": "u1", "filename": "Implantacao.dxf", "mime": "image/vnd.dxf",
                                   "data_b64": base64.b64encode(_dxf()).decode()})
    docs = asyncio.run(assistant_tool._load_assistant_docs(db, ["d1"], "u1"))
    assert docs[0][0] == "Implantacao.pdf" and docs[0][1].startswith(b"%PDF")


def test_dwg_attachment_goes_through_converter(monkeypatch):
    calls = []

    async def fake(data, name, user_id=None, provenance=None):
        calls.append(name)
        return _dxf()
    import engines.dwg_convert as dc
    monkeypatch.setattr(dc, "dwg_to_dxf", fake)
    db = DB()
    db.assistant_docs.docs.append({"doc_id": "d2", "user_id": "u1", "filename": "CNT_Arq.dwg", "mime": "application/acad",
                                   "data_b64": base64.b64encode(b"AC1018" + b"\0" * 64).decode()})
    docs = asyncio.run(assistant_tool._load_assistant_docs(db, ["d2"], "u1"))
    assert calls == ["CNT_Arq.dwg"] and docs[0][1].startswith(b"%PDF")
