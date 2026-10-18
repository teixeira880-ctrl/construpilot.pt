"""Documentos de demonstração : PC + estudo geotécnico fictícios → estudo imediato, sem IA, com a empresa fictícia."""
import asyncio
import base64
import io

from pypdf import PdfReader

from engines.bet_core import assistant_tool, brand, samples

from .test_assistant_tool import DB, _pdf


def test_demo_pdfs_are_marked_and_detected():
    files = samples.build_all("moradia_pt_demo")
    assert len(files) == 2
    for data in files.values():
        meta = PdfReader(io.BytesIO(data)).metadata
        assert meta["/Subject"] == samples.MARK + "moradia_pt_demo"
        assert "DEMONSTRAÇÃO" in "".join(p.extract_text() or "" for p in PdfReader(io.BytesIO(data)).pages).upper()
    docs = list(files.items())
    assert samples.detect(docs) == "moradia_pt_demo"
    assert samples.detect(docs + [("outro.pdf", _pdf(["PLANTA DO R/C"]))]) is None      # documento real misturado → leitura IA


def test_demo_branding_is_fictional_and_valid():
    b = samples.demo_branding("PT")
    assert "fictícia" in b["footer_text"] and b["logo_b64"].startswith("data:image/png;base64,")
    br = brand.from_branding(b, "PT")
    assert br.is_client and br.logo is not None and br.name.startswith("Construções Horizonte")


def test_demo_study_is_instant_without_llm():
    db = DB()

    class U:
        async def find_one(self, q, proj=None):
            return {f"brand_{k}": v for k, v in samples.demo_branding("PT").items() if k != "postal_code"}
    db.users = U()
    for i, (name, data) in enumerate(samples.build_all("moradia_pt_demo").items()):
        db.assistant_docs.docs.append({"doc_id": f"demo_{i}", "user_id": "demo_pro", "filename": name, "mime": "application/pdf",
                                       "data_b64": base64.b64encode(data).decode()})

    async def no_llm(*a, **k):
        raise AssertionError("os documentos de demonstração não devem chamar a IA")
    user, conv = {"user_id": "demo_pro", "account_type": "pro"}, {"conversation_id": "c1", "_quote_request_id": "r1"}
    out = asyncio.run(assistant_tool.execute("generate_full_bet_study", {"document_ids": ["demo_0", "demo_1"], "hypotheses": "", "country": "PT"},
                                             user, conv, db, llm=no_llm, background=False))
    st = asyncio.run(assistant_tool.execute("read_full_bet_study", {"job_id": out["job_id"]}, user, conv, db))
    assert st["status"] == "done" and st["demo"] == "moradia_pt_demo" and st["blocking"] == 0
    assert {a["format"] for a in st["artifacts"]} == {"pdf", "zip", "xlsx"}
    assert any(a["filename"].startswith("Processo_estudo") for a in db.assistant_artifacts.docs)


def test_demo_documents_can_carry_existing_demo_project_identity():
    pj = {"name": "Moradia Martins", "client": "Família Martins (fictícia)", "address": "Braga — morada fictícia"}
    files = samples.build_all("moradia_pt_demo", pj)
    assert set(files) == {"Projeto_arquitetura_Moradia_Martins_DEMO.pdf", "Estudo_geotecnico_Moradia_Martins_DEMO.pdf"}
    docs = list(files.items())
    assert samples.detect(docs) == "moradia_pt_demo" and samples.project_of(docs)["name"] == "Moradia Martins"
    from engines.bet_core import reader
    rd = asyncio.run(reader.read_building(docs, "", "PT"))
    assert rd["ok"] and rd["model"]["project"]["name"] == "Moradia Martins"
    assert rd["model"]["project"]["client"] == "Família Martins (fictícia)"
