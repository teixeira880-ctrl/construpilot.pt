"""Iteration 168 — unified report (Phase 3): the PDF is built from the same tool results as the chat (N), stays within scope (I),
and document identity comes from the title block, not the upload date (authorized eval fixture AES COF 0100 R+1 indice B)."""
import sys

from pypdf import PdfReader

sys.path.append("/app/backend")

from engines.assistant_report_pdf import build_conversation_report
from engines.metre.tools import run_metre_tool
from engines.plan_identity import identify_document

FIXTURE = "/app/tests/fixtures/eval/AES_COF_0100_R+1_B.pdf"


def _r(label, value, origin="native_text"):
    return {"label": label, "value_m": value, "candidates_m": [], "origin": origin}


def _text(pdf_bytes):
    import io
    return "\n".join((p.extract_text() or "") for p in PdfReader(io.BytesIO(pdf_bytes)).pages)


def test_identity_reads_revision_from_title_block_not_upload_date():
    text = PdfReader(FIXTURE).pages[0].extract_text()
    ident = identify_document(text)
    assert ident["revision_index"] == "B" and ident["revision_date"] == "23/11/2021"
    assert ident["document_code"] == "COF 0100 R+1" and ident["declared_scale"] == "1/50" and ident["level"] == "R+1"
    assert ident["discipline"] == "Structure — coffrage" and ident["title"].startswith("Plan coffrage PH R+1")
    assert [r["index"] for r in ident["revision_history"]] == ["A", "B"]
    assert identify_document("aucun cartouche ici")["revision_index"] is None


def test_N_pdf_uses_exactly_the_chat_tool_results_and_I_scope_only():
    chain = run_metre_tool("check_dimension_chain", {"spans": [_r("vide 1", 4.0), _r("vide 2", 5.0)],
        "thicknesses": [_r("mur ext. G", 0.2), _r("cloison", 0.1), _r("mur ext. D", 0.2)], "chain_includes_thickness": False,
        "reference": "faces", "declared_total": _r("total plan", 9.53)})
    qty = run_metre_tool("calculate_quantities", {"items": [{"category": "wall_area", "element": "Voile V12", "location": "R+1 file 3", "sources": ["plan COF 0100"],
        "length_m": 5.0, "height_m": 2.8, "width_m": None, "area_m2": None, "openings": [{"label": "porte", "width_m": 1.0, "height_m": 2.1}],
        "deduction_rule": "full", "deduction_threshold_m2": None, "extra_pct": None, "plan_area_m2": None, "slope_deg": None, "net_quantity": None,
        "units_per_measure": None, "pack_size": None, "waste_pct": None, "product": None, "unit": None}]})
    calcs = [{"tool": "check_dimension_chain", "result": chain}, {"tool": "calculate_quantities", "result": qty}]
    conv = {"conversation_id": "conv_test_unified_0001", "title": "Contrôle voiles vide sanitaire"}
    plans = [{"plan_id": "plan_x", "filename": "AES_COF_0100_R+1_B.pdf", "sha256": "abc123def456", "page_count": 1, "created_at": "2026-09-15T10:00:00",
              "revision": "Indice B 23/11/2021 COF 0100 R+1"}]
    sources = [{"url": "https://fab.example/fiche.pdf", "title": "Fiche technique X", "entity": "fab.example", "version": "3.2", "dates_found": ["12/03/2025"],
                "consulted_at": "2026-09-15T10:05:00", "verified": True, "claim": "pose sur support sec"}]
    from PIL import Image as PILImage
    chain["calculation"]["inputs"][0].update(plan_id="plan_x", page=0, box=[0.1, 0.1, 0.3, 0.12])
    calls = []

    def crop_provider(plan_id, page, box):
        calls.append((plan_id, page, box))
        return PILImage.new("RGB", (400, 200), "white"), [0.2, 0.3, 0.8, 0.5]
    pdf = build_conversation_report(conv=conv, calculations=calcs, solutions=[], sources=sources, plans=plans,
                                    branding={"company_name": "Entreprise Test SARL"}, lang="fr", crop_provider=crop_provider,
                                    scope="Cohérence des cotes et surface des voiles du vide sanitaire ; semelles exclues du contrôle.")
    text = _text(pdf)
    assert calls == [("plan_x", 0, [0.1, 0.1, 0.3, 0.12])] and "Extraits annotés du plan" in text and "CA-01 · vide 1 = 4 m" in text
    # same numbers, formula and state as the tool result shown in the chat
    assert "9.5 m" in text and "0.03" in text and "3 cm" in text
    assert "11.9" in text and "2.1" in text and "14" in text and "Confirmé" in text
    assert chain["comparison"]["result"] == 0.03 and qty["lines"][0]["net"] == 11.9
    # document identity from title block, upload date flagged as not the revision date
    assert "Indice B 23/11/2021" in text and "n'est pas la date de révision" in text.replace("\n", " ")
    # real company, control mention, clickable source with version, footer brand
    assert "Entreprise Test SARL" in text and "CM RENOV" not in text
    assert "ne constitue pas une note de calcul structurel" in text.replace("\n", " ")
    assert "Fiche technique X" in text and "v3.2" in text and "ConstruPilot.fr" in text
    # scope: no generic chapter about missing documents, nothing about excluded footings beyond the scope sentence
    lower = text.lower()
    assert "documents manquants" not in lower and "plans absents" not in lower
    assert lower.count("semelle") == 1


def test_solution_report_marks_structural_validation_and_unverified_options():
    sol = {"problem": "Appui d'isolant : extension de dalle", "facts": ["débord 8 cm"], "hypotheses": [], "criteria": [],
           "options": [{"name": "Extension de dalle", "description": "", "suitability": "adaptée sous conditions", "conditions": ["ancrage"], "advantages": ["appui continu"],
                        "limitations": ["pont thermique"], "sources": [], "source_status": "aucune source", "evidence_level": "hypothèse à confirmer"}],
           "recommended_option": None, "justification": "", "missing_decisive_data": ["hauteur libre"], "structural_validation_required": True,
           "required_verifications": ["Validation structurelle spécifique (BET / ingénieur) avant exécution"], "next_action": "Relevé"}
    text = _text(build_conversation_report(conv={"conversation_id": "c2", "title": "ITE"}, calculations=[], solutions=[sol], sources=[], plans=[], branding=None, lang="pt"))
    flat = " ".join(text.split())
    assert "Validation structurelle" in flat and "hypothèse à confirmer" in flat and "aucune source" in flat
    assert "donnée décisive manquante" in flat and "ConstruPilot.pt" in flat
