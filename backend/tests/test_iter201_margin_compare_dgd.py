"""Marge par lot (DPGF), comparatif des offres, décompte général définitif (DGD)."""
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
RFQ_TO = "delivered@resend.dev"

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


def dpgf_bytes():
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["Désignation", "Unité", "Quantité", "Prix unitaire HT", "Montant HT"])
    ws.append(["01 — MACONNERIE", None, None, None, None])
    ws.append(["Mur en blocs béton 20 cm", "m2", 10, 100, None])
    ws.append(["02 — PLOMBERIE", None, None, None, None])
    ws.append(["Alimentation PER par point d'eau", "u", 4, None, None])
    out = io.BytesIO()
    wb.save(out)
    return out.getvalue()


r = s.post(f"{API}/auth/login", json={"email": EMAIL, "password": PWD}, timeout=30)
check("login pro", r.status_code == 200, r.text[:200])
if r.status_code != 200:
    sys.exit(1)

# ─────────── A. Marge par lot ───────────
imp = s.post(f"{API}/pro/dpgf/import", files={"file": ("TEST_iter201.xlsx", dpgf_bytes(), XL)},
             data={"analyse_cctp": "false", "market_compare": "true"}, timeout=240)
check("import DPGF", imp.status_code == 200, imp.text[:300])
if imp.status_code != 200:
    sys.exit(1)
res = imp.json()
fid = res["file_id"]
plomb = [l for l in res["lines"] if "PER" in l["designation"]][0]
base_pu = plomb["pu"]
check("prix IA de départ sur la plomberie", base_pu and base_pu > 0, str(plomb)[:200])

m = s.patch(f"{API}/pro/dpgf/{fid}/lot-margin", json={"lot": "02 — PLOMBERIE", "margin_pct": 20})
check("coefficient de lot appliqué", m.status_code == 200, m.text[:250])
r2 = m.json()
p2 = [l for l in r2["lines"] if "PER" in l["designation"]][0]
mac = [l for l in r2["lines"] if "blocs" in l["designation"]][0]
check("PU plomberie majoré de 20 %", abs(p2["pu"] - round(p2["pu_base"] * 1.2, 2)) < 0.02,
      f"{p2['pu']} vs {p2['pu_base']}")
check("maçonnerie (prix du bordereau) inchangée", mac["pu"] == 100, str(mac["pu"]))
check("coefficient mémorisé par lot",
      r2["directives"]["lot_margins"].get("02 — PLOMBERIE") == 20,
      str(r2["directives"].get("lot_margins")))
m0 = s.patch(f"{API}/pro/dpgf/{fid}/lot-margin", json={"lot": "02 — PLOMBERIE", "margin_pct": 0}).json()
p0 = [l for l in m0["lines"] if "PER" in l["designation"]][0]
check("coefficient réversible (pas de cumul)", p0["pu"] == p0["pu_base"], f"{p0['pu']} vs {p0['pu_base']}")

# ─────────── B. Comparatif des offres ───────────
rfq = s.post(f"{API}/pro/dpgf/{fid}/rfq",
             json={"lot": "02 — PLOMBERIE", "emails": [RFQ_TO], "origin_url": BASE,
                   "message": "Test iter201 — ignorer."}, timeout=120)
check("demande de prix envoyée", rfq.status_code == 200, rfq.text[:250])
token = rfq.json()["recipients"][0]["token"]
lines = pub.get(f"{API}/public/rfq/{token}").json()["lines"]
cheap = round(p0["pu"] * 0.8, 2)
pub.post(f"{API}/public/rfq/{token}",
         json={"prices": {l["line_id"]: cheap for l in lines}, "contact_name": "Plomberie Test",
               "note": "Offre 20 % sous le marché"})
cmp = s.get(f"{API}/pro/dpgf/{fid}/offers-compare")
check("comparatif disponible", cmp.status_code == 200, cmp.text[:250])
cd = cmp.json()
lot = next((x for x in cd["lots"] if x["lot"] == "02 — PLOMBERIE"), None)
check("lot présent dans le comparatif", bool(lot), str(cd)[:300])
if lot:
    off = lot["offers"][0]
    check("écart calculé (~-20 %)", off["delta_pct"] is not None and -21 <= off["delta_pct"] <= -19,
          str(off))
    check("meilleure offre identifiée", lot["best"]["token"] == token, str(lot["best"])[:200])
    check("économie estimée > 0", lot["saving_ht"] > 0, str(lot["saving_ht"]))
    check("réponses comptées", lot["answered"] == 1 and lot["requested"] == 1, str(lot)[:200])
s.delete(f"{API}/pro/dpgf/{fid}")

# ─────────── C. Décompte général définitif ───────────
q = s.post(f"{API}/documents", json={
    "doc_type": "quote", "title": "TEST iter201 marché DGD",
    "lines": [{"designation": "Lot gros œuvre", "unit": "u", "qty": 1, "unit_price_ht": 10000, "vat_rate": 10},
              {"designation": "Lot finitions", "unit": "u", "qty": 1, "unit_price_ht": 5000, "vat_rate": 10}]}).json()
qid = q["doc_id"]
s.patch(f"{API}/documents/{qid}/status", json={"status": "signed"})
dep = s.post(f"{API}/documents/{qid}/deposit-invoice", json={"pct": 20}).json()      # 3 000 HT
s.post(f"{API}/documents/{dep['doc_id']}/payments", json={"amount": 3300, "method": "virement"})
sit = s.post(f"{API}/situations", json={"marche_id": qid,
                                        "lines": [{"idx": 0, "pct": 60}, {"idx": 1, "pct": 40}],
                                        "retention_pct": 5, "deposit_mode": "prorata"}).json()
check("situation intermédiaire créée", bool(sit.get("situation_id")), str(sit)[:250])

rec = s.get(f"{API}/situations/dgd", params={"marche_id": qid})
check("récapitulatif DGD", rec.status_code == 200, rec.text[:250])
t = rec.json()["totals"]
# facturé = 10000*60% + 5000*40% = 8 000 → solde travaux 7 000
check("solde de travaux calculé (7 000 HT)", abs(t["remaining_ht"] - 7000) < 0.5, str(t["remaining_ht"]))
check("acompte restant à imputer affiché", t["deposit_available_ht"] > 0, str(t["deposit_available_ht"]))
check("retenue détenue affichée", t["retention_held"] > 0, str(t["retention_held"]))
expected_dgd = round(7000 - t["deposit_available_ht"], 2)
check("solde à facturer = travaux - acompte", abs(t["dgd_ht"] - expected_dgd) < 0.5,
      f"{t['dgd_ht']} vs {expected_dgd}")

pdf = s.get(f"{API}/situations/dgd-pdf", params={"marche_id": qid})
check("aperçu PDF du DGD", pdf.status_code == 200 and pdf.content[:4] == b"%PDF", str(pdf.status_code))

held = t["retention_held"]
dgd = s.post(f"{API}/situations/dgd", json={"marche_id": qid, "impute_deposit": True,
                                            "release_retention": True})
check("DGD généré", dgd.status_code == 200, dgd.text[:300])
dd = dgd.json()
inv = s.get(f"{API}/documents/{dd['doc_id']}").json()
check("facture de solde = travaux restants", abs(dd["works_ht"] - 7000) < 0.5, str(dd["works_ht"]))
check("acompte restant déduit sur le DGD", dd["deposit_imputed_ht"] > 0, str(dd))
neg = [l for l in inv["lines"] if l["unit_price_ht"] < 0]
check("ligne négative d'acompte présente", len(neg) == 1, str(neg)[:200])
relig = [l for l in inv["lines"] if "Libération de la retenue" in l["designation"]]
check("libération de la retenue facturée sans TVA",
      relig and abs(relig[0]["unit_price_ht"] - held) < 0.5 and relig[0]["vat_rate"] == 0,
      str(relig)[:250])
check("retenue marquée libérée", dd["retention_released"], str(dd))
rets = s.get(f"{API}/situations/retentions").json()
mine = [x for x in rets if x["marche_id"] == qid]
check("statut retenue = libérée", mine and mine[0]["released"], str(mine)[:200])

again = s.post(f"{API}/situations/dgd", json={"marche_id": qid})
check("un seul DGD par marché", again.status_code == 400, again.text[:200])
rec2 = s.get(f"{API}/situations/dgd", params={"marche_id": qid}).json()
check("DGD référencé sur le marché", rec2.get("dgd_doc_id") == dd["doc_id"], str(rec2.get("dgd_doc_id")))
cancel = s.delete(f"{API}/situations/dgd/{qid}")
check("DGD annulable", cancel.status_code == 200, cancel.text[:200])
rec3 = s.get(f"{API}/situations/dgd", params={"marche_id": qid}).json()
check("marché de nouveau ouvert après annulation", not rec3.get("dgd_doc_id"), str(rec3.get("dgd_doc_id")))

# Nettoyage
s.delete(f"{API}/situations/{sit['situation_id']}")
for d in [dep.get("doc_id"), qid]:
    if d:
        s.delete(f"{API}/documents/{d}")
print(f"\n{ok} OK / {fail} KO")
sys.exit(1 if fail else 0)
