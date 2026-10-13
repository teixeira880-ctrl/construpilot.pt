import sys
sys.path.insert(0, "/app/backend")
from engines import doc_reconcile as R  # noqa: E402


def L(line_id, des, lot="Lot 1"):
    return {"line_id": line_id, "kind": "detail", "lot": lot, "designation": des,
            "provenance": {"designation": f"DPGF!A{line_id[-1]}"}}


def main():
    ok = True

    def chk(name, cond):
        nonlocal ok
        print(("PASS" if cond else "FAIL"), "-", name)
        ok = ok and cond

    # FR/PT dictionnaire + similarité
    chk("synonyme FR/PT (carrelage↔azulejo)", R.similarity("carrelage grès", "revestimento azulejo") > 0)
    chk("épaisseur cm→mm", R._thickness_mm("dalle ep 20 cm") == {200})

    pdf_lines = [
        {"text": "Isolant laine de roche épaisseur 140 mm sous rampant", "page": 3, "bbox": [0, 0, 1, 1]},
        {"text": "Carrelage grès cérame 60x60 au sol", "page": 4, "bbox": [0, 0, 1, 1]},
        {"text": "Étanchéité SEL sur toiture terrasse", "page": 5, "bbox": [0, 0, 1, 1]},
    ]
    pres = R.extract_prescriptions(pdf_lines)
    chk("3 prescriptions extraites", len(pres) == 3)

    devis = [
        L("l1", "Isolant laine de roche 100 mm"),          # mismatch 100 vs 140
        L("l2", "Carrelage grès cérame collé"),            # match, pas d'écart
        L("l3", "Carrelage grès cérame collé", lot="Lot 2"),  # doublon inter-lots avec l2
    ]
    res = R.reconcile(devis, pres, corrections=[])
    types = [a["type"] for a in res["anomalies"]]
    chk("écart d'épaisseur détecté (140 vs 100)", "thickness_mismatch" in types)
    chk("ouvrage prescrit non trouvé (étanchéité)", "prescribed_not_found" in types)
    chk("double comptage inter-lots", "duplicate_lot" in types)
    tm = next(a for a in res["anomalies"] if a["type"] == "thickness_mismatch")
    chk("écart épaisseur sourcé (CCTP page + devis source)",
        tm["cctp"]["page"] == 3 and tm["devis"]["source"] == "DPGF!A1")

    # Mémoire des corrections : neutralise l'écart d'épaisseur
    corr = [{"signature": tm["signature"], "resolution": "ignored", "active": True}]
    res2 = R.reconcile(devis, pres, corrections=corr)
    chk("correction (ignored) neutralise l'écart",
        not any(a["type"] == "thickness_mismatch" for a in res2["anomalies"]))

    print("RESULT:", "ALL PASS" if ok else "SOME FAIL")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
