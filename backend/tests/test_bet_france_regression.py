"""BET.0 — regressão combinada Caso 1 (Saint-Denis) + Caso 2 (La Courneuve).

Baseline esperada: 16/16 FAIL antes dos fixes BET.1→BET.6.
Progressão esperada:
- BET.1 → c1_1, c2_1 PASS (detecção país/locale).
- BET.2 → c1_2, c1_3, c2_2 PASS (coerência G2).
- BET.3 → c1_4, c1_5 PASS (clarifications paredes/aberturas).
- BET.3b → c2_4, c2_5 PASS (muros cave + confinantes).
- BET.4 → c1_6, c2_3, c2_6, c2_7 PASS (neve/escadas/sísmica/descrição).
- BET.5 → c1_7, c2_8 PASS (chain full).
- BET.6 → c2_9 PASS (PDF resiliente).
"""
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tests.fixtures import bet_france_mismatched_g2 as C1
from tests.fixtures import bet_france_coherent_g2 as C2


def _bet_pipeline(pc, g2=None, confirm_g2_use=False):
    """Orquestra os módulos BET disponíveis e devolve resultado estruturado.

    Enquanto BET.5 (chain full) não existe, chama os pedaços directamente.
    Devolve dict com `locale`, `norms_used`, `warnings` (list[dict]),
    `clarifications`, `measurements`, `quote`, `bet_result`, `error`.
    """
    out = {
        "locale": None, "country_code": None, "norms_used": None,
        "doc_language": None, "warnings": [], "clarifications": [],
        "footings": None, "cave_walls": None, "snow_zone": None,
        "parasismic_rules": None, "measurements": None, "quote": None,
        "bet_result": None, "plans_available": False, "error": None,
    }
    try:
        from engines.bet import locale as bet_locale
        info = bet_locale.detect_country_from_address(pc.get("project_address", ""))
        out["country_code"] = info["country_code"]
        out["locale"] = info["locale"]
        out["norms_used"] = info["norms"]
        out["doc_language"] = info["doc_language"]
    except ImportError:
        pass

    try:
        from engines.bet import g2_coherence
        if g2:
            coh = g2_coherence.verify_g2_coherence(pc, g2)
            if coh["severity"] == "high" and not confirm_g2_use:
                out["warnings"].append({
                    "code": "mismatch_address", "severity": "high",
                    "detail": coh.get("detail"),
                    "action": "require_user_confirmation",
                })
            if coh["coherent"]:
                out["footings"] = {
                    "q_ELS_kPa": g2["q_ELS_MPa"] * 1000,
                    "settlement_mm": g2.get("settlement_mm"),
                    "type": g2.get("preferred_footing_type", "corrida"),
                }
            elif confirm_g2_use:
                out["footings"] = {
                    "q_ELS_kPa": g2["q_ELS_MPa"] * 1000,
                    "settlement_mm": g2.get("settlement_mm"),
                    "type": "corrida_confirmada",
                }
    except ImportError:
        pass

    # BET.3 — clarifications paredes/aberturas (stub até fase BET.3)
    try:
        from engines.bet import plan_reading
        clar = plan_reading.extract_or_ask(pc)
        out["clarifications"].extend(clar.get("questions", []))
    except ImportError:
        pass

    # BET.3b — muros de cave
    try:
        from engines.bet import cave_walls
        if g2 and pc.get("neighbors"):
            cw = cave_walls.compute(pc, g2)
            out["cave_walls"] = cw
            out["warnings"].extend(cw.get("warnings", []))
    except ImportError:
        pass

    # BET.4 — snow / parasismic / mass plan discrepancy
    try:
        from engines.bet import regional_data
        rd = regional_data.lookup(pc)
        out["snow_zone"] = rd.get("snow_zone")
        out["parasismic_rules"] = rd.get("parasismic_rules")
        out["warnings"].extend(rd.get("warnings", []))
    except ImportError:
        pass

    # BET.5 — chain full
    try:
        from engines.bet import chain
        c = chain.run_full_chain(pc, g2, confirm_g2_use=confirm_g2_use)
        out.update({
            "bet_result": c.get("bet_result"),
            "measurements": c.get("measurements"),
            "quote": c.get("quote"),
            "plans_available": c.get("plans_available", False),
        })
    except ImportError:
        pass

    return out


# ─── Caso 1 ─────────────────────────────────────────────────────────────────
def test_c1_1_detects_france_from_address():
    r = _bet_pipeline(C1.PC_DATA, g2=None)
    assert r["country_code"] == "FR"
    assert r["locale"] == "fr-FR"
    assert r["norms_used"] == "NF EN + AN FR"
    assert r["doc_language"] == "fr"


def test_c1_2_detects_g2_address_mismatch():
    r = _bet_pipeline(C1.PC_DATA, g2=C1.G2_DATA)
    mismatch = [w for w in r["warnings"]
                if w.get("code") == "mismatch_address" and w.get("severity") == "high"]
    assert mismatch, "Esperado warning mismatch_address severity=high"
    assert mismatch[0]["action"] == "require_user_confirmation"


def test_c1_3_uses_g2_when_user_confirms():
    r = _bet_pipeline(C1.PC_DATA, g2=C1.G2_DATA, confirm_g2_use=True)
    assert r["footings"] is not None
    assert r["footings"]["q_ELS_kPa"] == 250.0


def test_c1_4_reads_interior_walls_or_asks():
    r = _bet_pipeline(C1.PC_DATA)
    walls_in_pc = C1.PC_DATA.get("walls_interior_resistant") or []
    missing = [q for q in r["clarifications"]
               if q.get("field") == "walls_interior_resistant"]
    assert walls_in_pc or missing, (
        "Esperado walls_interior_resistant preenchidos OU clarification question"
    )


def test_c1_5_reads_openings_or_asks():
    r = _bet_pipeline(C1.PC_DATA)
    openings = C1.PC_DATA.get("openings_facades") or []
    missing = [q for q in r["clarifications"]
               if q.get("field") == "openings_facades"]
    assert openings or missing


def test_c1_6_load_path_consistency():
    r = _bet_pipeline(C1.PC_DATA, g2=C1.G2_DATA, confirm_g2_use=True)
    bet = r.get("bet_result")
    assert bet is not None, "chain não produziu bet_result"
    n_elu_t5 = bet.get("descent_summary", {}).get("N_ELU_quadro_5")
    n_elu_t6 = bet.get("descent_summary", {}).get("N_ELU_quadro_6")
    assert n_elu_t5 is not None and n_elu_t6 is not None
    tol = max(abs(n_elu_t5), abs(n_elu_t6)) * 0.05
    assert abs(n_elu_t5 - n_elu_t6) <= tol, (
        f"Descida de cargas inconsistente: quadro5={n_elu_t5}, quadro6={n_elu_t6}"
    )


def test_c1_7_chain_bet_measurements_quote():
    r = _bet_pipeline(C1.PC_DATA, g2=C1.G2_DATA, confirm_g2_use=True)
    assert r["bet_result"] is not None, "bet_result em falta"
    assert r["measurements"] is not None, "measurements em falta"
    assert r["quote"] is not None, "quote em falta"


# ─── Caso 2 ─────────────────────────────────────────────────────────────────
def test_c2_1_detects_france_from_address():
    r = _bet_pipeline(C2.PC_DATA, g2=None)
    assert r["country_code"] == "FR"
    assert r["locale"] == "fr-FR"
    assert r["norms_used"] == "NF EN + AN FR"


def test_c2_2_g2_same_address_no_confirmation_required():
    r = _bet_pipeline(C2.PC_DATA, g2=C2.G2_DATA)
    high_mismatch = [w for w in r["warnings"]
                     if w.get("code") == "mismatch_address" and w.get("severity") == "high"]
    assert not high_mismatch, (
        "G2 com mesma morada NÃO deve emitir warning mismatch_address severity=high"
    )
    assert r["footings"] is not None


def test_c2_3_footings_corridas_dimensioned_at_250kpa():
    r = _bet_pipeline(C2.PC_DATA, g2=C2.G2_DATA)
    f = r["footings"]
    assert f is not None
    assert f["q_ELS_kPa"] == 250.0
    assert f["type"] == "sapata_corrida"
    assert abs((f.get("settlement_mm") or 0) - 12.7) <= 0.1


def test_c2_4_cave_walls_K0_plus_neighbor_surcharge():
    r = _bet_pipeline(C2.PC_DATA, g2=C2.G2_DATA)
    cw = r["cave_walls"]
    assert cw is not None, "muros de cave não calculados"
    layers = cw.get("layers_K0") or []
    k0_aterros = next((lay["k0"] for lay in layers if lay["name"] == "aterros"), None)
    k0_aluvioes = next((lay["k0"] for lay in layers if lay["name"] == "aluvioes"), None)
    assert k0_aterros == 0.577
    assert k0_aluvioes == 0.500
    assert (cw.get("neighbor_surcharge_kN_m") or 0) > 0


def test_c2_5_neighbors_warning_present():
    r = _bet_pipeline(C2.PC_DATA, g2=C2.G2_DATA)
    neigh = [w for w in r["warnings"]
             if w.get("code") == "neighbors_attached_unknown_cave"]
    assert neigh, "Falta warning neighbors_attached_unknown_cave"
    assert neigh[0].get("severity") == "high"
    rem = neigh[0].get("remediation", "")
    assert "recalçamento" in rem.lower() or "soutènement" in rem.lower()


def test_c2_6_no_parasismic_rules_zone_1():
    r = _bet_pipeline(C2.PC_DATA, g2=C2.G2_DATA)
    assert r.get("parasismic_rules") is not None
    assert r["parasismic_rules"].get("required") is False
    assert "1" in str(r["parasismic_rules"].get("zone", ""))


def test_c2_7_mass_plan_discrepancy_reported():
    r = _bet_pipeline(C2.PC_DATA, g2=C2.G2_DATA)
    discrep = [w for w in r["warnings"]
               if w.get("code") == "building_description_mismatch"]
    assert discrep, "Falta warning building_description_mismatch (R+2+cave vs R+1+C)"


def test_c2_8_chain_bet_measurements_quote():
    r = _bet_pipeline(C2.PC_DATA, g2=C2.G2_DATA)
    assert r["bet_result"] is not None
    assert r["measurements"] is not None
    assert r["quote"] is not None


def test_c2_9_pdf_import_resilient():
    """Importação de PDF deve devolver estrutura estruturada em erro."""
    try:
        from engines.bet.pdf_import import parse_pc_pdf_resilient
    except ImportError:
        pytest.fail("engines.bet.pdf_import.parse_pc_pdf_resilient não existe")
    # Simula PDF corrompido (bytes aleatórios)
    r = parse_pc_pdf_resilient(b"\x00" * 100)
    assert r.get("status") == "error"
    assert r.get("code") in {"CORRUPTED_PDF", "OCR_FAILED",
                              "SIZE_LIMIT", "SCANNED_NO_OCR", "EMPTY_PAGES"}
    assert "remediation" in r
    assert "details" in r
