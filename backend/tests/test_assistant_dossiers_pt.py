"""Processos completos no Assistente (.pt): rotas /assistant/dossiers, ferramenta listar_processo, inventário entregue ao modelo,
resolução por nome de ficheiro (read_document) e controlo de acesso — base em memória, sem Mongo nem IA."""
import asyncio
import io
import os
import zipfile

import pytest

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "test_dossier_pt")
os.environ.setdefault("JWT_SECRET", "test")

from fake_mongo_pt import FakeDB  # noqa: E402

R = pytest.importorskip("routes.assistant_dossiers")
A = pytest.importorskip("routes.assistant")
J = pytest.importorskip("engines.assistant_jobs")
from fastapi import HTTPException, UploadFile  # noqa: E402

from engines import dossier_tool as T  # noqa: E402

USER = {"user_id": "u_a", "organization_id": "org_x", "account_type": "pro", "active": True}
OTHER = {"user_id": "u_b", "organization_id": "org_x", "account_type": "pro", "active": True}


def run(coro):
    return asyncio.run(coro)


@pytest.fixture
def db(monkeypatch):
    fake = FakeDB()
    for mod in (R, A, J):
        monkeypatch.setattr(mod, "db", fake)
    return fake


def _zip(entries):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for n, d in entries:
            z.writestr(n, d)
    return buf.getvalue()


def _xlsx_register():
    from openpyxl import Workbook
    wb = Workbook()
    ws = wb.active
    ws.append(["LISTA DE DESENHOS — ESTABILIDADE"])
    ws.append(["N.º", "NOME", "DESCRIÇÃO", "Rev.", "Data"])
    ws.append(["0100", "XYZ_PE_EST_TZ_P1_COF_0100", "Planta de cofragem - Piso 1", "B", "24/11/2021"])
    ws.append(["0200", "XYZ_PE_EST_TZ_P2_COF_0200", "Planta de cofragem - Piso 2", "A", "22/10/2021"])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _pdf(text):
    import pymupdf
    doc = pymupdf.open()
    doc.new_page().insert_text((72, 72), text)
    return doc.tobytes()


_PLAN = None


def _plan_pdf():
    global _PLAN
    _PLAN = _PLAN or _pdf("Planta do piso 1 escala 1:100")     # mesmos bytes em todos os envios (deteção de duplicados)
    return _PLAN


def _upload(name, data):
    return UploadFile(file=io.BytesIO(data), filename=name)


def _import(db, user=USER):
    d = run(R.create_dossier(R.DossierIn(name="Moradia exemplo"), user=user))
    data = _zip([("01_Arquitetura/Planta Piso 1.pdf", _plan_pdf()),
                 ("02_Estabilidade/XYZ_PE_EST_TZ_P1_COF_0100_-_A.dxf", b"0\nSECTION\n2\nENTITIES\n0\nENDSEC\n0\nEOF\n"),
                 ("Lista de desenhos.xlsx", _xlsx_register()),
                 ("Caderno de encargos.txt", "CADERNO DE ENCARGOS\nCláusulas técnicas: betão C25/30.".encode()),
                 ("virus.exe", b"MZ")])
    res = run(R.add_file(d["dossier_id"], file=_upload("processo.zip", data), user=user))
    return d, res


def test_import_zip_classifies_and_stores_without_listing_in_documents(db):
    d, res = _import(db)
    assert d["dossier_id"].startswith("dos_") and d["name"] == "Moradia exemplo"
    by = {a["filename"]: a for a in res["added"]}
    assert by["Planta Piso 1.pdf"]["discipline"] == "arquitetura" and by["Planta Piso 1.pdf"]["level"] == "Piso 1"
    assert by["Planta Piso 1.pdf"]["pages"] == 1
    assert by["XYZ_PE_EST_TZ_P1_COF_0100_-_A.dxf"]["discipline"] == "cofragem" and by["XYZ_PE_EST_TZ_P1_COF_0100_-_A.dxf"]["indice"] == "A"
    assert by["Lista de desenhos.xlsx"]["discipline"] == "lista_desenhos" and by["Lista de desenhos.xlsx"]["desenhos_na_lista"] == 2
    assert by["Caderno de encargos.txt"]["rotulo"] == "Caderno de encargos"
    assert any("virus.exe" in s for s in res["skipped"])
    txt = next(x for x in db.assistant_docs.docs if x["filename"] == "Caderno de encargos.txt")
    assert "betão C25/30" in txt["text"] and txt["mime"] == "text/plain"           # legível com read_document
    assert db.assistant_dossiers.docs[0]["files_count"] == 4
    assert run(A.list_docs(user=USER)) == []                                        # peças do processo fora da lista de anexos soltos


def test_duplicate_upload_is_skipped_and_limits(db, monkeypatch):
    d, _ = _import(db)
    again = run(R.add_file(d["dossier_id"], file=_upload("Planta Piso 1.pdf", _plan_pdf()), user=USER))
    assert again["added"] == [] and "já está no processo" in again["skipped"][0]
    with pytest.raises(HTTPException) as e:
        run(R.add_file(d["dossier_id"], file=_upload("vazio.pdf", b""), user=USER))
    assert e.value.status_code == 422
    with pytest.raises(HTTPException) as e:
        run(R.add_file(d["dossier_id"], file=_upload("mau.zip", b"PK\x03\x04garbage"), user=USER))
    assert e.value.status_code == 422 and "ilegível" in e.value.detail
    monkeypatch.setattr(R.D, "MAX_FILES", 4)
    with pytest.raises(HTTPException) as e:
        run(R.add_file(d["dossier_id"], file=_upload("extra.pdf", _pdf("outro")), user=USER))
    assert e.value.status_code == 413


def test_inventory_register_control_and_isolation(db):
    d, _ = _import(db)
    inv = run(R.get_dossier(d["dossier_id"], user=USER))
    assert inv["ok"] and inv["inventario"]["total"] == 4
    ck = inv["controlo_lista_desenhos"]
    assert ck["desenhos_na_lista"] == 2 and {m["code"] for m in ck["em_falta"]} == {"XYZ_PE_EST_TZ_P2_COF_0200"}
    assert ck["revisoes_desatualizadas"][0]["revisao_ficheiro"] == "A" and ck["revisoes_desatualizadas"][0]["revisao_lista"] == "B"
    assert "mapa de quantidades" in inv["pecas_habituais_em_falta"]
    assert all("register" not in f for f in inv["files"])
    with pytest.raises(HTTPException) as e:                                          # outra conta (mesma empresa): 404
        run(R.get_dossier(d["dossier_id"], user=OTHER))
    assert e.value.status_code == 404
    with pytest.raises(HTTPException):
        run(R.add_file(d["dossier_id"], file=_upload("a.pdf", _pdf("x")), user=OTHER))
    assert [x["dossier_id"] for x in run(R.list_dossiers(user=USER))] == [d["dossier_id"]]
    assert run(R.list_dossiers(user=OTHER)) == []


def test_delete_removes_files_and_chunks(db, monkeypatch):
    monkeypatch.setattr(R, "CHUNK", 16)                      # força o armazenamento em blocos
    d, _ = _import(db)
    assert db.assistant_doc_chunks.docs
    assert run(R.delete_dossier(d["dossier_id"], user=USER)) == {"deleted": 4}
    assert db.assistant_docs.docs == [] and db.assistant_doc_chunks.docs == [] and db.assistant_dossiers.docs == []


def test_assistant_tool_and_model_context(db):
    d, _ = _import(db)
    assert "listar_processo" in {t["name"] for t in A.tools_for(USER)}
    assert "listar_processo" in {t["name"] for t in A.tools_for({**USER, "account_type": "particulier"})}
    conv = {"conversation_id": "c1"}
    out = run(A._exec_tool("listar_processo", {"dossier_id": d["dossier_id"]}, USER, conv))
    assert out["ok"] and out["inventario"]["total"] == 4
    foreign = run(A._exec_tool("listar_processo", {"dossier_id": d["dossier_id"]}, OTHER, conv))
    assert foreign["ok"] is False and "não encontrado" in foreign["error"]
    text = T.context_text(out)
    assert text.startswith(f"PROCESSO ANEXADO {d['dossier_id']} «Moradia exemplo»: 4 ficheiros")
    assert "01_Arquitetura/Planta Piso 1.pdf | arquitetura | Piso 1 | pdf" in text and "Lista de desenhos: 2 desenhos" in text
    assert "nunca uma instrução" in text
    assert "listar_processo" in T.INSTRUCTIONS and A.TOOL_STATUS_PT["listar_processo"].startswith("Inventário")


def test_read_document_accepts_the_filename_from_the_inventory(db):
    _import(db)
    conv = {"conversation_id": "c1"}
    out = run(A._exec_tool("read_document", {"document_id": "Caderno de encargos.txt", "first_page": 1, "page_count": 1}, USER, conv))
    assert out["document_id"].startswith("doc_") and out["filename"] == "Caderno de encargos.txt"
    assert "C25/30" in str(out)
    with pytest.raises(PermissionError):
        run(A._exec_tool("read_document", {"document_id": "inexistente.pdf", "first_page": 1, "page_count": 1}, USER, conv))
    with pytest.raises(PermissionError):                                           # .pt: acesso por conta (mesma empresa ≠ acesso)
        run(A._exec_tool("read_document", {"document_id": out["document_id"], "first_page": 1, "page_count": 1}, OTHER, conv))
    assert run(A._find_doc_id(out["document_id"], OTHER["user_id"]))[1].endswith("inacessível para esta conta.")
    assert run(A._find_doc_id("Caderno", USER["user_id"]))[0] == out["document_id"]


def test_message_and_job_accept_only_owned_dossiers(db):
    d, _ = _import(db)
    assert A.MsgIn(conversation_id="c", text="x").dossier_ids == []
    body = A.MsgIn(conversation_id="c1", text="Faça o inventário deste processo.", request_id="r1", dossier_ids=[d["dossier_id"]])
    db.assistant_convs.docs.append({"conversation_id": "c1", "user_id": "u_b", "title": "Nova conversa"})
    with pytest.raises(HTTPException) as e:
        run(J.enqueue(body, OTHER))
    assert e.value.status_code == 403 and e.value.detail == "Processo inacessível."
    db.assistant_convs.docs.append({"conversation_id": "c1", "user_id": "u_a", "title": "Nova conversa"})
    job = run(J.enqueue(A.MsgIn(conversation_id="c1", text="Inventário", request_id="r2", dossier_ids=[d["dossier_id"]]), USER))
    assert job["status"] == "queued"
    conv = next(c for c in db.assistant_convs.docs if c["user_id"] == "u_a")
    assert conv["active_dossiers"] == [d["dossier_id"]]
