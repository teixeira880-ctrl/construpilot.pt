"""Lot 88 — section OPTION d'un DPGF : lignes chiffrées mais hors total de base."""
import io

import openpyxl

from engines import dpgf_engine as de


def _xlsx():
    wb = openpyxl.Workbook()
    ws = wb.active
    rows = [["N° Art.", "DESIGNATION DES OUVRAGES", "Unité", "Quantité", "P.Unitaire", "P.Total HT"],
            ["LOT 3", "MENUISERIES EXTERIEURES"],
            ["3.2", "Volets roulants à commande manuelle, aluminium"],
            ["3.2.1", "Volet manuel F-01", "Unité", 5, 100, None],
            ["3.2", "OPTION : Volets roulants à commande électrique, aluminium"],
            ["3.2.1", "Volet électrique F-01", "Unité", 5, 150, None],
            ["3.2.10", "Manoeuvre électrique des volets roulants", "Unité", 16, 10, None],
            ["3.3", "Ouvrages divers"],
            ["3.3.1", "Entrées d'air", "Unité", 16, 5, None]]
    for row in rows:
        ws.append(row)
    b = io.BytesIO(); wb.save(b)
    return b.getvalue()


def test_option_lines_kept_but_out_of_base_total():
    rows = de.parse_workbook(_xlsx())["rows"]
    opts = [r for r in rows if r["option"]]
    assert [r["designation"] for r in opts] == ["OPTION — Volet électrique F-01", "OPTION — Manoeuvre électrique des volets roulants"]
    assert not any(r["option"] for r in rows if "manuel" in r["designation"] or "air" in r["designation"])
    t = de.finalise(rows)
    assert t["grand_total_ht"] == 5 * 100 + 16 * 5
    assert t["options_total_ht"] == 5 * 150 + 16 * 10


def test_no_option_section_unchanged():
    wb = openpyxl.Workbook(); ws = wb.active
    for row in [["Désignation", "Unité", "Quantité", "PU"], ["LOT 1 GROS OEUVRE"], ["Béton", "m3", 10, 100]]:
        ws.append(row)
    b = io.BytesIO(); wb.save(b)
    rows = de.parse_workbook(b.getvalue())["rows"]
    t = de.finalise(rows)
    assert t["grand_total_ht"] == 1000 and t["options_total_ht"] == 0
