"""Regressões da Auditoria Geral V2 (07/11/2026) — sem base de dados nem rede.

P1 · planta: uma divisão de 12 m² continua a ser 12 m² (sem face exterior,
     sem contorno do edifício, sem regiões minúsculas).
P1 · documento PDF: 10 × 25 = 275 é sinalizado (esperado 250, diferença 25)
     e o efeito nos totais aparece ; «nada encontrado» distingue não executado.
P1 · scanner: sem referência → comparação indisponível (nunca um % da IA).
P1/P2 · calculadoras: preço ausente ≠ 0 € ; dimensão 0 ou negativa → erro no campo.
"""
import base64

import pytest

cv2 = pytest.importorskip("cv2")
np = pytest.importorskip("numpy")


def _png(img) -> str:
    return base64.b64encode(cv2.imencode(".png", img)[1].tobytes()).decode()


def _area_m2(points, ppm=100):
    n = len(points)
    return abs(sum(points[i][0] * points[(i + 1) % n][1] - points[(i + 1) % n][0] * points[i][1]
                   for i in range(n))) / 2 / ppm / ppm


def test_single_room_not_doubled():
    from engines.plan_cv import detect_all_rooms
    img = np.full((600, 700, 3), 255, np.uint8)
    cv2.rectangle(img, (90, 90), (510, 410), (0, 0, 0), -1)
    cv2.rectangle(img, (100, 100), (500, 400), (255, 255, 255), -1)
    cv2.putText(img, "Sala 12 m2", (220, 250), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 0), 2)
    rooms = detect_all_rooms(_png(img))["rooms"]
    assert len(rooms) == 1
    assert _area_m2(rooms[0]["points"]) == pytest.approx(12.0, abs=0.1)


def test_building_envelope_dropped():
    from engines.plan_cv import detect_all_rooms
    img = np.full((700, 900, 3), 255, np.uint8)
    cv2.rectangle(img, (90, 90), (810, 510), (0, 0, 0), -1)
    for x0, y0, x1, y1 in [(100, 100, 500, 400), (510, 100, 800, 400), (100, 410, 800, 500)]:
        cv2.rectangle(img, (x0, y0), (x1, y1), (255, 255, 255), -1)
    res = detect_all_rooms(_png(img))
    areas = sorted(round(_area_m2(r["points"]), 1) for r in res["rooms"])
    assert areas == [6.3, 8.7, 12.0]
    assert any(d["reason"] == "envelope_of_detected_rooms" for d in res["dropped"])


def _pdf(lines):
    from reportlab.pdfgen import canvas
    import io
    buf = io.BytesIO()
    c = canvas.Canvas(buf)
    y = 800
    for t in lines:
        c.drawString(40, y, t)
        y -= 20
    c.save()
    return buf.getvalue()


def test_pdf_arithmetic_error_flagged():
    pytest.importorskip("fitz")
    from engines import doc_intel
    raw = _pdf(["TEST AUDIT - DEVIS AVEC ERREUR ARITHMETIQUE",
                "Designation | Quantite | Unite | Prix unitaire HT | Total HT",
                "Peinture des murs | 10 | m2 | 25.00 EUR | 275.00 EUR",
                "Preparation des supports | 1 | forfait | 50.00 EUR | 50.00 EUR",
                "Total HT: 325.00 EUR", "TVA 20%: 65.00 EUR", "Total TTC: 390.00 EUR"])
    a = doc_intel.analyse(raw, "erreur.pdf")["arithmetic"]
    assert a["summary"]["status"] == "executed"
    bad = [c for c in a["checks"] if c["status"] == "mismatch"]
    assert len(bad) == 1 and bad[0]["computed"] == 250.0 and bad[0]["file_amount"] == 275.0
    assert bad[0]["diff"] == 25.0
    ht = next(t for t in a["totals"] if t["type"] == "total_ht")
    assert ht["status"] == "mismatch" and ht["computed"] == 300.0


def test_pdf_without_table_is_not_run():
    pytest.importorskip("fitz")
    from engines import doc_intel
    a = doc_intel.analyse(_pdf(["Caderno de encargos: paredes em alvenaria."]), "cctp.pdf")["arithmetic"]
    assert a["summary"]["status"] == "not_run"


def test_ocr_items_rechecked():
    from engines import doc_intel
    a = doc_intel.ocr_arithmetic({"line_items": [{"description": "Pintura", "quantity": "10",
                                                  "unit_price": "25,00", "amount": "275,00"}]})
    assert a["summary"]["mismatches"] == 1


def test_quote_without_reference_has_no_delta():
    from engines.quote_grounding import ground_quote_analysis
    r = ground_quote_analysis({"verdict": "bas", "delta_vs_reference_pct": -40,
                               "lines": [{"label": "Pintura", "quantity": 20, "unit_price": 15, "total": 300}],
                               "total_ht": 300}, None)
    assert r["delta_vs_reference_pct"] is None and r["verdict"] == "sem_referencia"
    assert r["arithmetic"]["mismatches"] == 0


def test_quote_with_reference_is_computed():
    from engines.quote_grounding import ground_quote_analysis
    r = ground_quote_analysis({"total_ht": 300}, {"total_avg": 500})
    assert r["delta_vs_reference_pct"] == -40.0 and r["reference_basis"]["reference_total"] == 500


def test_calculator_zero_and_negative_rejected_with_field():
    from engines.calculator_validation import run_validated, FieldError
    for v in (-5, 0):
        with pytest.raises(FieldError) as e:
            run_validated("concrete", {"length": v, "width": 4, "thickness_cm": 12})
        assert e.value.field == "length"


def test_roof_has_no_fake_zero_budget():
    from engines.calculator_validation import run_validated
    r = run_validated("roof_facade", {})
    assert r.get("estimated_budget") is None  # a rota devolve price_status «unavailable»


def test_insulation_r_value():
    from engines.calculators import insulation
    r = insulation(area=60, material="laine_de_verre", thickness_mm=200)
    vals = {x["label"]: x["value"] for x in r["results"]}
    assert vals["Lambda do material"] == 0.032
    assert vals["Resistência térmica R obtida"] == 6.25
