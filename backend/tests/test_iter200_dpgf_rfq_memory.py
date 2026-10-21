"""DPGF : oublis CCTP, mémoire des prix, appel d'offres sous-traitants, historique."""
import io
import os
import re
import sys

import openpyxl
import requests

with open("/app/frontend/.env") as f:
    BASE = re.search(r"REACT_APP_BACKEND_URL=(\S+)", f.read()).group(1)
API = BASE.rstrip("/") + "/api"
EMAIL = os.environ.get("TEST_PRO_EMAIL", "pro@construpilot.fr")
PWD = os.environ.get("TEST_PRO_PASSWORD", "Pro2026!")
XL = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
RFQ_TO = "delivered@resend.dev"  # boîte de test Resend

s = requests.Session()
pub = requests.Session()
ok = fail = 0


def check(label, cond, detail=""):
    global ok, fail
    if cond:
        ok += 1
        print(f"✅ {label}")
    else:
        fail += 1
        print(f"❌ {label} — {detail}")


def wb_bytes():
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["Désignation", "Unité", "Quantité", "Prix unitaire HT", "Montant HT"])
    ws.append(["01 — PLOMBERIE", None, None, None, None])
    ws.append(["Alimentation PER encastrée par point d'eau", "u", 8, None, None])
    ws.append(["Evacuation PVC diamètre 100", "ml", 18, None, None])
    out = io.BytesIO()
    wb.save(out)
    return out.getvalue()


CCTP = (
    "CCTP LOT PLOMBERIE — Villa TEST iter200\n"
    "ARTICLE 1 : alimentations en PER encastré sous gaine, nourrice collective avec vannes "
    "d'arrêt par départ. Evacuations en PVC de diamètre adapté.\n"
    "ARTICLE 2 : l'entreprise fournira et posera un CHAUFFE-EAU THERMODYNAMIQUE de 200 litres "
    "avec son support et son raccordement électrique et hydraulique.\n"
    "ARTICLE 3 : il sera prévu la pose d'un ADOUCISSEUR D'EAU avec by-pass, ainsi que le "
    "calorifugeage complet des canalisations en volume non chauffé.\n"
    "ARTICLE 4 : essais d'étanchéité et mise en service consignés au PV de réception. "
    "Respect des NF DTU 60.1 et 60.11. Nettoyage quotidien du chantier.\n"
) * 3

r = s.post(f"{API}/auth/login", json={"email": EMAIL, "password": PWD}, timeout=30)
check("login pro", r.status_code == 200, r.text[:200])
if r.status_code != 200:
    sys.exit(1)

files = {"file": ("dpgf_iter200.xlsx", wb_bytes(), XL),
         "cctp": ("cctp_iter200.txt", CCTP.encode(), "text/plain")}
r = s.post(f"{API}/pro/dpgf/import", files=files,
           data={"analyse_cctp": "true", "market_compare": "true"}, timeout=300)
check("import avec analyse CCTP", r.status_code == 200, r.text[:300])
if r.status_code != 200:
    sys.exit(1)
res = r.json()
fid = res["file_id"]

# ---- 1) Vérif des oublis
gaps = res.get("gaps") or []
print("   oublis:", [g["designation"] for g in gaps])
check("oublis CCTP détectés", len(gaps) > 0, "aucun oubli détecté")
check("chauffe-eau ou adoucisseur signalé",
      any(k in " ".join(g["designation"].lower() for g in gaps)
          for k in ("chauffe", "adoucisseur", "calorifug")), str(gaps)[:300])
if gaps:
    g0 = gaps[0]
    before = res["line_count"]
    r2 = s.post(f"{API}/pro/dpgf/{fid}/gap/{g0['gap_id']}/add", json={"qty": 1}, timeout=180)
    check("ajout de l'ouvrage oublié à l'étude", r2.status_code == 200, r2.text[:300])
    if r2.status_code == 200:
        st = r2.json()
        added = [l for l in st["lines"] if l.get("added_from_cctp")]
        check("ligne ajoutée et chiffrée", st["line_count"] == before + 1 and added and added[0]["pu"],
              str(added)[:250])
        check("oubli marqué comme traité",
              next(g["added"] for g in st["gaps"] if g["gap_id"] == g0["gap_id"]), "non marqué")
        res = st
    if len(gaps) > 1:
        r3 = s.post(f"{API}/pro/dpgf/{fid}/gap/{gaps[1]['gap_id']}/ignore")
        check("oubli ignorable",
              r3.status_code == 200 and all(g["gap_id"] != gaps[1]["gap_id"] for g in r3.json()["gaps"]),
              r3.text[:200])
        res = r3.json()

# ---- 2) Appel d'offres sous-traitant (lien public)
rfq = s.post(f"{API}/pro/dpgf/{fid}/rfq",
             json={"lot": "01 — PLOMBERIE", "emails": [RFQ_TO],
                   "message": "Test technique iter200 — merci d'ignorer.",
                   "origin_url": BASE, "due_days": 7}, timeout=120)
check("demande de prix envoyée", rfq.status_code == 200, rfq.text[:300])
if rfq.status_code == 200:
    rd = rfq.json()
    rec = rd["recipients"][0]
    token = rec["token"]
    check("lien public généré", bool(rec["link"]) and token, str(rec)[:200])
    check("lignes du lot transmises", len(rd["lines"]) >= 2, str(rd["lines"])[:200])

    v = pub.get(f"{API}/public/rfq/{token}")
    check("page publique accessible sans compte", v.status_code == 200, v.text[:200])
    lines = v.json()["lines"]
    prices = {l["line_id"]: 42.0 for l in lines}
    sub = pub.post(f"{API}/public/rfq/{token}", json={"prices": prices, "note": "Offre de test",
                                                      "contact_name": "Plomberie Test"})
    check("offre soumise par le sous-traitant", sub.status_code == 200, sub.text[:200])
    expected = round(sum(42.0 * (l["qty"] or 0) for l in lines), 2)
    check("total de l'offre calculé", abs(sub.json()["total_ht"] - expected) < 0.05,
          f"{sub.json().get('total_ht')} vs {expected}")

    lst = s.get(f"{API}/pro/dpgf/{fid}/rfq", params={"origin_url": BASE}).json()
    got = lst[0]["recipients"][0]
    check("offre visible côté pro", got["responded_at"] and got["total_ht"] == sub.json()["total_ht"],
          str(got)[:200])

    ap = s.post(f"{API}/pro/dpgf/{fid}/rfq/{rd['rfq_id']}/apply", json={"token": token})
    check("offre retenue sur les lignes", ap.status_code == 200 and ap.json()["applied"] >= 2,
          ap.text[:200])
    if ap.status_code == 200:
        st = ap.json()["study"]
        subs = [l for l in st["lines"] if l["source"] == "soustraitant"]
        check("prix sous-traitant appliqué", len(subs) >= 2 and all(l["pu"] for l in subs),
              str(subs)[:250])
        res = st

# ---- 3) Mémoire des prix (passage en devis)
lib_before = s.get(f"{API}/pro/price-library").json()["total"]
q = s.post(f"{API}/pro/dpgf/{fid}/quote", json={"vat_rate": 10, "full_descriptions": True})
check("passage en devis", q.status_code == 200, q.text[:300])
qd = q.json()
check("prix mémorisés dans la bibliothèque", qd.get("remembered_prices", 0) > 0, str(qd)[:200])
lib = s.get(f"{API}/pro/price-library").json()
check("bibliothèque enrichie", lib["total"] >= lib_before + 1, f"{lib_before} → {lib['total']}")
mem = [i for i in lib["items"] if "PER encastrée" in (i.get("designation") or "")]
check("provenance du prix tracée", mem and mem[0].get("price_source"), str(mem)[:250])
# Idempotence : un 2e passage ne duplique pas
q2 = s.post(f"{API}/pro/dpgf/{fid}/quote", json={"vat_rate": 10})
lib2 = s.get(f"{API}/pro/price-library").json()
check("pas de doublon en bibliothèque au 2e passage", lib2["total"] == lib["total"],
      f"{lib['total']} → {lib2['total']}")

# ---- 4) Historique
hist = s.get(f"{API}/pro/dpgf").json()
mine = [h for h in hist if h["file_id"] == fid]
check("étude présente dans l'historique", bool(mine), str(hist)[:200])
check("devis lié référencé dans l'historique", mine and mine[0].get("quote_doc_id"), str(mine)[:200])
again = s.get(f"{API}/pro/dpgf/{fid}")
check("réouverture d'une étude", again.status_code == 200 and again.json()["file_id"] == fid,
      again.text[:200])

# Nettoyage
for did in [qd.get("doc_id"), (q2.json() or {}).get("doc_id")]:
    if did:
        s.delete(f"{API}/documents/{did}")
s.delete(f"{API}/pro/dpgf/{fid}")
for it in [i for i in s.get(f"{API}/pro/price-library").json()["items"]
           if "iter200" in (i.get("source_file") or "") or "DPGF — dpgf_iter200" in (i.get("source_file") or "")]:
    s.delete(f"{API}/pro/price-library/{it['item_id']}")

print(f"\n{ok} OK / {fail} KO")
sys.exit(1 if fail else 0)
