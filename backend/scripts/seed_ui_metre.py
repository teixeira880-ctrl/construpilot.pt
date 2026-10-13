"""Seed idempotent pour valider l'UI : hauteurs/ouvertures m², fusion de cotes,
report m² groupé, rapprochement plan↔devis + correction. Compte pro@construpilot.fr.

Lancer : PYTHONPATH=/app/backend python scripts/seed_ui_metre.py
- Plan éditeur : /plan?open=plan_uitest (2 murs cumulés labellisés + 1 surface)
- DocIntel : import doc_uitest (DPGF) sur /analyse-documents
"""
import asyncio
import base64
import io

from PIL import Image

from core.db import db


async def main():
    u = await db.users.find_one({"email": "pro@construpilot.fr"}, {"user_id": 1, "company_id": 1})
    uid = u["user_id"]

    img = Image.new("RGB", (1000, 800), (245, 245, 245))
    b = io.BytesIO(); img.save(b, format="PNG")
    png = base64.b64encode(b.getvalue()).decode()

    await db.plans_takeoff.delete_many({"plan_id": "plan_uitest"})
    await db.plans_takeoff.insert_one({
        "plan_id": "plan_uitest", "user_id": uid, "filename": "Maison UI test.png",
        "created_at": "2026-09-29T00:00:00Z", "updated_at": "2026-09-29T00:00:00Z",
        "pages": [{"image_png_b64": png, "width_px": 1000, "height_px": 800, "dpi": 150}],
        "calibrations": {"0": {"pixels_per_meter": 100.0, "meters_per_pixel": 0.01,
                                "method": "manual", "confidence": 1.0}},
        "measurements": [
            {"measurement_id": "mes_ui_nord", "page_index": 0, "kind": "cumulative",
             "label": "Mur façade nord parpaing", "poste": "peinture", "value_m": 6.0, "length_m": 6.0,
             "gross_m": 6.0, "wall_height_m": 2.5, "wall_area_gross_m2": 15.0,
             "openings_area_m2": 0.0, "wall_area_net_m2": 33.0,
             "segments": [[[100, 100], [700, 100]]], "points": [[100, 100], [700, 100]],
             "color": "#dc2626"},
            {"measurement_id": "mes_ui_sud", "page_index": 0, "kind": "cumulative",
             "label": "Mur façade sud parpaing", "poste": "placo", "value_m": 4.0, "length_m": 4.0,
             "segments": [[[100, 400], [500, 400]]], "points": [[100, 400], [500, 400]],
             "color": "#2563eb"},
            {"measurement_id": "mes_ui_sol", "page_index": 0, "kind": "cumulative_area",
             "label": "Carrelage sol séjour", "poste": "carrelage", "area_m2": 30.0, "perimeter_m": 22.0,
             "polygons": [[[100, 500], [400, 500], [400, 700], [100, 700]]],
             "points": [[100, 500], [400, 500], [400, 700], [100, 700]], "color": "#0d9488"},
        ],
        "rooms": [],
    })

    await db.doc_imports.delete_many({"import_id": "doc_uitest"})
    await db.doc_imports.insert_one({
        "import_id": "doc_uitest", "user_id": uid, "company_id": u.get("company_id"),
        "filename": "DPGF-UI-test.xlsx", "format": "xlsx", "status": "done",
        "created_at": "2026-09-29T00:00:00Z",
        "result": {"format": "xlsx", "language": "fr", "engine_version": "doc_intel/1.0.0", "duration_ms": 5,
                   "warnings": [], "unread": [], "sheets": [],
                   "lines": [
                       {"line_id": "L1", "kind": "detail", "lot": "Maçonnerie",
                        "designation": "Murs en parpaing façade nord", "unit": "m²",
                        "qty": {"value": 30.0, "status": "ok"}, "pu": {"value": 45.0, "status": "ok"},
                        "amount": {"value": 1350.0, "status": "ok"}, "flags": [],
                        "provenance": {"designation": "DPGF!D5", "amount": "DPGF!G5"}},
                       {"line_id": "L2", "kind": "detail", "lot": "Revêtement",
                        "designation": "Carrelage grès cérame au sol séjour", "unit": "m²",
                        "qty": {"value": 30.0, "status": "ok"}, "pu": {"value": 55.0, "status": "ok"},
                        "amount": {"value": 1650.0, "status": "ok"}, "flags": [],
                        "provenance": {"designation": "DPGF!D8", "amount": "DPGF!G8"}},
                   ],
                   "arithmetic": {"checks": [], "subtotals": [],
                                  "summary": {"sum_computed_ht": 3000.0, "mismatches": 0,
                                              "vat_rate": 20, "vat_amount": 600.0, "total_ttc": 3600.0}}},
    })
    print("Seeded plan_uitest + doc_uitest for", uid)


if __name__ == "__main__":
    asyncio.run(main())
