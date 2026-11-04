"""Lot 75 — DPGF : titre de lot avec parenthèse ; arrêt après le Total TTC."""
import io

import openpyxl

from engines import dpgf_engine as E


def _wb():
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Devis"
    ws.append(["N°", "Désignation", "Unité", "Quantité", "PU HT", "Montant HT"])
    ws.append(["3", "LINTEAUX ET ALLÈGES BA des baies", None, None, None, None])
    ws.append(["3.1", "Béton C25/30 linteaux", "m³", 15.7, 185, 2904.5])
    ws.append(["4", "POUTRES BA (consoles de balcons/coursives et poutres)", None, None, None, None])
    ws.append(["4.1", "Béton C25/30 poutres", "m³", 15.9, 185, 2941.5])
    ws.append([None, None, None, None, "Total HT", 5846.0])
    ws.append([None, None, None, None, "TVA", 1169.2])
    ws.append([None, None, None, None, "Total TTC", 7015.2])
    ws.append([None, "Ratios de contrôle", None, None, None, None])
    ws.append([None, "Béton total (m³)", None, 31.6, None, None])
    ws.append([None, "Acier total (kg)", None, 3796.0, None, None])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def test_lot_title_with_parenthesis_and_stop_after_total():
    rows = E.parse_workbook(_wb())["rows"]
    names = [r["designation"] for r in rows]
    assert names == ["Béton C25/30 linteaux", "Béton C25/30 poutres"]
    assert rows[1]["lot"].startswith("POUTRES BA")
    assert rows[0]["lot"].startswith("LINTEAUX")


def test_lowercase_line_still_not_a_title():
    assert not E._is_lot_title("Béton de propreté (dosé à 150 kg)", None, None)
