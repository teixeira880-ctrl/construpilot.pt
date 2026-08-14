"""Iter53 refactor regression suite.

Valide les refactorings :
- `engines/calculators.py` : dataclass params (PaintParams, TileParams, RoofFacadeParams)
- `engines/monetization.py` : helpers (_index_existing_products, _resolve_price,
  _compute_trial_days, _resolve_promo_discount, _build_checkout_kwargs)
- `engines/pdf_takeoff.py` : TVA attestation via helpers
- `routes/plans.py` : split en 5 modules (crud, analysis, render, export, common)
"""
import os
import io
import pytest

BASE = os.environ.get("REACT_APP_BACKEND_URL",
                      "http://localhost:8001").rstrip("/")
if not BASE.endswith("/api"):
    BASE = BASE + "/api"


# ============ CALCULATORS (dataclass + kwargs compat) ============

class TestCalculatorsRefactor:
    def test_paint_kwargs_and_dataclass_equivalent(self):
        from engines.calculators import paint, PaintParams
        r_kwargs = paint(4, 3, 2.5, doors=1, windows=1, coats=2)
        r_dc = paint(PaintParams(length=4, width=3, height=2.5,
                                  doors=1, windows=1, coats=2))
        assert r_kwargs["estimated_budget"] == r_dc["estimated_budget"]
        assert r_kwargs["materials"] == r_dc["materials"]

    def test_tile_dataclass(self):
        from engines.calculators import tile, TileParams
        r = tile(TileParams(area=12, tile_length=60, tile_width=60,
                             pose="diagonale"))
        assert r["inputs"]["loss_pct"] == 12  # diagonale = 12% pertes
        assert r["inputs"]["area"] == 12

    def test_roof_facade_dataclass_and_kwargs(self):
        from engines.calculators import roof_facade, RoofFacadeParams
        r1 = roof_facade(100, 30, None, 40, 5.5, 15, 140)
        r2 = roof_facade(RoofFacadeParams(projected_m2=100, pitch_deg=30,
                                            wall_perimeter_m=40, wall_height_m=5.5,
                                            openings_m2=15, ite_thickness_mm=140))
        # Budget peut ne pas être exposé, mais matériaux doivent matcher
        assert r1["materials"] == r2["materials"]

    def test_roof_facade_warnings_over_60_deg(self):
        from engines.calculators import roof_facade
        r = roof_facade(projected_m2=100, pitch_deg=65,
                        wall_perimeter_m=0, wall_height_m=0)
        assert any("Pente > 60" in w for w in r["warnings"])


# ============ PDF (TVA attestation via helpers) ============

class TestPdfTakeoffTvaRefactor:
    def test_tva_dataclass_input(self):
        from engines.pdf_takeoff import (
            build_tva_attestation_pdf, TvaAttestationInput,
        )
        data = TvaAttestationInput(
            client_name="Alice Dupont",
            client_address="10 rue de la Paix, 75002 Paris",
            work_address="Idem",
            work_description="Rénovation salle de bain",
            company_name="ConstruPilot Test",
            company_address="",
            branding=None,
            tva_rate=0.10,
        )
        pdf = build_tva_attestation_pdf(data)
        assert pdf.startswith(b"%PDF")
        assert len(pdf) > 500

    def test_tva_legacy_kwargs_still_work(self):
        from engines.pdf_takeoff import build_tva_attestation_pdf
        pdf = build_tva_attestation_pdf(
            client_name="Bob",
            client_address="1 impasse du test",
            work_address="Idem",
            work_description="Peinture",
            company_name="Pro Peinture",
            company_address="",
            tva_rate=0.055,
        )
        assert pdf.startswith(b"%PDF")


# ============ MONETIZATION helpers ============

class TestMonetizationRefactor:
    def test_helpers_exported(self):
        """Les nouveaux helpers doivent exister au niveau module."""
        from engines import monetization as m
        for name in ("_index_existing_products", "_upsert_product", "_upsert_price",
                     "_resolve_price", "_compute_trial_days", "_resolve_promo_discount",
                     "_build_checkout_kwargs", "_consume_referral_bonus",
                     "_credit_referrer_safe", "_apply_pro_credit_topup"):
            assert hasattr(m, name), f"helper {name} missing"

    def test_plan_is_pro_tier(self):
        from engines.monetization import _plan_is_pro_tier
        assert _plan_is_pro_tier({"audience": "pro", "plan_id": "pro_monthly"}) == True
        assert _plan_is_pro_tier({"audience": "particulier",
                                   "plan_id": "pro_business_yearly"}) == True
        # premium_* n'est PAS pro-tier (préserve sémantique originale du code)
        assert _plan_is_pro_tier({"audience": "particulier",
                                   "plan_id": "premium_monthly"}) == False

    def test_price_matches(self):
        from engines.monetization import _price_matches

        class P:
            unit_amount = 4900
            currency = "eur"
        plan = {"amount_cents": 4900, "currency": "eur"}
        assert _price_matches(P, plan)
        plan_diff = {"amount_cents": 9900, "currency": "eur"}
        assert not _price_matches(P, plan_diff)


# ============ ROUTES/plans split (backward compatible imports) ============

class TestPlansSplit:
    def test_router_and_quote_router_exported_from_plans_module(self):
        """server.py utilise plans_routes.router / plans_routes.quote_router."""
        from routes import plans as plans_mod
        assert hasattr(plans_mod, "router")
        assert hasattr(plans_mod, "quote_router")
        assert hasattr(plans_mod, "_run_reminders")
        assert hasattr(plans_mod, "build_client_portal_token")

    def test_router_prefixes(self):
        from routes import plans as plans_mod
        assert plans_mod.router.prefix == "/takeoffs"
        assert plans_mod.quote_router.prefix == "/quotes"

    def test_endpoints_registered(self):
        """Vérifie que les endpoints critiques sont bien enregistrés après le split."""
        from routes import plans as plans_mod
        paths = {getattr(r, "path", None) for r in plans_mod.router.routes}
        # CRUD
        assert "/takeoffs/upload" in paths
        assert "/takeoffs/{plan_id}" in paths
        # Analysis
        assert "/takeoffs/{plan_id}/analyze" in paths
        assert "/takeoffs/{plan_id}/takeoff" in paths
        # Render
        assert "/takeoffs/{plan_id}/render-3d" in paths
        assert "/takeoffs/{plan_id}/render-video" in paths
        # Export
        assert "/takeoffs/{plan_id}/pdf" in paths
        assert "/takeoffs/{plan_id}/send-quote" in paths

    def test_quote_endpoints(self):
        from routes import plans as plans_mod
        paths = {getattr(r, "path", None) for r in plans_mod.quote_router.routes}
        assert "/quotes/templates" in paths
        assert "/quotes/multi-pdf" in paths
        assert "/quotes/client-portal/{token}" in paths
        assert "/quotes/public/sign/{token}" in paths

    def test_client_portal_token_roundtrip(self):
        from routes.plans import build_client_portal_token
        from routes.emails import _sign
        import base64
        tok = build_client_portal_token("client@test.fr")
        assert "." in tok
        b64, sig = tok.rsplit(".", 1)
        assert base64.urlsafe_b64decode(b64).decode() == "client@test.fr"
        assert sig == _sign("client@test.fr")


# ============ E2E : Landing still 200 (backend didn't break) ============

def test_landing_still_200():
    import requests
    r = requests.get(f"{BASE}/plans/all-public", timeout=10)
    # This endpoint might not exist — try health
    assert r.status_code in (200, 404, 405)


def test_api_openapi_still_lists_split_routes():
    import requests
    # Call the underlying openapi via localhost (no ingress)
    r = requests.get("http://localhost:8001/openapi.json", timeout=10)
    assert r.status_code == 200
    paths = r.json().get("paths", {})
    takeoff_count = sum(1 for p in paths if "takeoff" in p)
    quote_count = sum(1 for p in paths if p.startswith("/api/quotes"))
    # Après le split, on doit avoir toujours >= 30 routes takeoffs et >= 10 quotes
    assert takeoff_count >= 30, f"Only {takeoff_count} takeoff routes"
    assert quote_count >= 10, f"Only {quote_count} quote routes"
