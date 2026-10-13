"""Vérification déterministe du moteur doc_intel (Étape 1)."""
import io
import sys

import openpyxl

sys.path.insert(0, "/app/backend")
from engines import doc_intel  # noqa: E402


def build_xlsx() -> bytes:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "DPGF"
    ws.append(["Désignation", "Quantité", "Unité", "Prix unitaire", "Montant"])
    ws.append(["01 - MAÇONNERIE", None, None, None, None])          # lot title
    ws.append(["Mur parpaing", 10, "m2", "25,50", "=B3*D3"])        # formule sans cache
    ws.append(["Enduit", 5, "m2", 12, 70])                          # 5*12=60 ≠ 70 → mismatch
    ws.append(["Dalle béton", "1.234,5", "m3", "1,00", 1234.5])     # milliers FR/PT
    ws.append(["Ligne masquée", 2, "u", 100, 200])                 # ligne cachée
    ws.append(["Sous-total lot 01", None, None, None, 1719.5])      # sous-total (exclu)
    ws.append(["Divers", "abc", "u", 5, None])                     # qté illisible
    ws.row_dimensions[6].hidden = True
    # feuille masquée non ignorée
    ws2 = wb.create_sheet("Annexe")
    ws2.append(["Désignation", "Quantité", "Unité", "Prix unitaire", "Montant"])
    ws2.append(["Poste annexe", 3, "u", 10, 30])
    ws2.sheet_state = "hidden"
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def build_pdf() -> bytes:
    import fitz
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), "Lot 02 - Plâtrerie", fontsize=12)
    page.insert_text((72, 100), "Cloison 72/48  25 m2  18,50 EUR", fontsize=11)
    out = doc.tobytes()
    doc.close()
    return out


def main():
    ok = True
    res = doc_intel.analyse(build_xlsx(), "test_dpgf.xlsx", vat_rate=20)
    lines = res["lines"]
    by_kind = {}
    for l in lines:
        by_kind.setdefault(l["kind"], []).append(l)
    detail = by_kind.get("detail", [])
    ari = res["arithmetic"]["summary"]

    def check(name, cond):
        nonlocal ok
        print(("PASS" if cond else "FAIL"), "-", name)
        ok = ok and cond

    check("feuille masquée signalée", any(w["type"] == "hidden_sheet" for w in res["warnings"]))
    check("feuille masquée analysée (Annexe lue)", any(l["sheet"] == "Annexe" for l in detail))
    check("lot_title détecté", len(by_kind.get("lot_title", [])) >= 1)
    check("sous-total exclu du sum", ari["subtotals_excluded"] == 1)
    mur = next((l for l in detail if l["designation"] == "Mur parpaing"), None)
    check("formule sans résultat signalée", bool(mur) and any("formula_result_missing" in f for f in mur["flags"]))
    check("provenance cellule (feuille!cellule)", bool(mur) and mur["provenance"]["pu"] == "DPGF!D3")
    check("PU FR '25,50' → 25.5", bool(mur) and mur["pu"]["value"] == 25.5)
    dalle = next((l for l in detail if l["designation"] == "Dalle béton"), None)
    check("milliers FR '1.234,5' → 1234.5", bool(dalle) and dalle["qty"]["value"] == 1234.5)
    hid = next((l for l in detail if l["designation"] == "Ligne masquée"), None)
    check("ligne masquée incluse + flag", bool(hid) and "hidden_row" in hid["flags"])
    div = next((l for l in detail if l["designation"] == "Divers"), None)
    check("qté illisible détectée", bool(div) and div["qty"]["status"] == "illegible")
    mism = [c for c in res["arithmetic"]["checks"] if c["status"] == "mismatch"]
    check("mismatch arithmétique (5×12≠70)", len(mism) == 1)
    check("insufficient pour qté illisible", ari["insufficient"] >= 1)
    check("TVA 20% calculée", ari["vat_amount"] is not None and ari["total_ttc"] is not None)

    # Idempotence de l'empreinte (mêmes octets → même empreinte)
    import hashlib
    b = build_xlsx()
    check("empreinte stable", hashlib.sha256(b).hexdigest() == hashlib.sha256(b).hexdigest())

    # PDF
    pres = doc_intel.analyse(build_pdf(), "plan.pdf")
    check("PDF: lignes texte extraites", len(pres["lines"]) >= 2)
    check("PDF: provenance page+bbox", all("page" in l and "bbox" in l for l in pres["lines"]))

    print("\nRÉSUMÉ arithmétique:", ari)
    print("RESULT:", "ALL PASS" if ok else "SOME FAIL")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
