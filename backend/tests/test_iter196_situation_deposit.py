"""Situation de travaux : déduction de l'acompte réellement encaissé.

Exécution : python backend/tests/test_iter196_situation_deposit.py
"""
import os
import sys

import requests

BASE = os.environ.get("TEST_BASE_URL") or ""
if not BASE:
    import re
    with open("/app/frontend/.env") as f:
        BASE = re.search(r"REACT_APP_BACKEND_URL=(\S+)", f.read()).group(1)
API = BASE.rstrip("/") + "/api"
EMAIL = os.environ.get("TEST_PRO_EMAIL", "pro@construpilot.fr")
PWD = os.environ.get("TEST_PRO_PASSWORD", "Pro2026!")

s = requests.Session()
ok = fail = 0


def check(label, cond, detail=""):
    global ok, fail
    if cond:
        ok += 1
        print(f"✅ {label}")
    else:
        fail += 1
        print(f"❌ {label} — {detail}")


r = s.post(f"{API}/auth/login", json={"email": EMAIL, "password": PWD}, timeout=30)
check("login pro", r.status_code == 200, r.text[:200])
if r.status_code != 200:
    sys.exit(1)

# Devis 10 000 € HT (TVA 10%)
lines = [{"designation": "Lot maçonnerie", "unit": "u", "qty": 1, "unit_price_ht": 6000, "vat_rate": 10},
         {"designation": "Lot peinture", "unit": "u", "qty": 1, "unit_price_ht": 4000, "vat_rate": 10}]
q = s.post(f"{API}/documents", json={"doc_type": "quote", "title": "TEST iter196 situation acompte",
                                     "lines": lines}).json()
qid = q["doc_id"]
s.patch(f"{API}/documents/{qid}/status", json={"status": "signed"})

dep = s.post(f"{API}/documents/{qid}/deposit-invoice", json={"pct": 30}).json()
check("facture acompte 30% créée", dep.get("totals", {}).get("ht") == 3000, str(dep)[:200])

# Acompte non encaissé → rien à déduire
sit = s.post(f"{API}/situations", json={"marche_id": qid, "lines": [{"idx": 0, "pct": 50}],
                                        "deposit_mode": "prorata"})
check("situation sans acompte encaissé → 0 déduit",
      sit.status_code == 200 and sit.json().get("deposit_imputed_ht") == 0, sit.text[:300])
sit1 = sit.json()
s.delete(f"{API}/situations/{sit1['situation_id']}")

# Encaissement de l'acompte (3 300 € TTC = 3 000 € HT)
pay = s.post(f"{API}/documents/{dep['doc_id']}/payments", json={"amount": 3300, "method": "virement"})
check("paiement acompte enregistré", pay.status_code == 200, pay.text[:200])

summ = s.get(f"{API}/situations/summary", params={"marche_id": qid}).json()
check("summary : acompte encaissé 3300 TTC / 3000 HT dispo",
      summ["deposit"]["paid_ttc"] == 3300 and summ["deposit"]["available_ht"] == 3000,
      str(summ.get("deposit"))[:300])

# Situation 1 : 50% sur les deux lots → travaux 5 000 HT, prorata acompte = 3000*0.5 = 1500
r1 = s.post(f"{API}/situations", json={"marche_id": qid,
                                       "lines": [{"idx": 0, "pct": 50}, {"idx": 1, "pct": 50}],
                                       "deposit_mode": "prorata", "retention_pct": 5})
d1 = r1.json()
check("situation 1 : travaux 5000 HT", d1.get("works_ht") == 5000, str(d1)[:300])
check("situation 1 : acompte prorata 1500 HT déduit", d1.get("deposit_imputed_ht") == 1500, str(d1)[:300])
check("situation 1 : facture HT = 3500", d1.get("total_ht") == 3500, str(d1.get("total_ht")))
check("situation 1 : retenue 5% sur travaux = 250", d1.get("retention_amount") == 250, str(d1))
check("situation 1 : net à payer = TTC - retenue",
      abs(d1["net_due"] - (d1["total_ttc"] - 250)) < 0.01, str(d1))

inv1 = s.get(f"{API}/documents/{d1['invoice_doc_id']}").json()
neg = [l for l in inv1["lines"] if l["unit_price_ht"] < 0]
check("facture situation 1 : ligne négative acompte", len(neg) == 1 and neg[0]["unit_price_ht"] == -1500,
      str(neg)[:200])

pdf = s.get(f"{API}/situations/{d1['situation_id']}/pdf")
check("décompte PDF généré", pdf.status_code == 200 and pdf.content[:4] == b"%PDF", str(pdf.status_code))
cert = s.get(f"{API}/situations/{d1['situation_id']}/certificate")
check("certificat PDF généré", cert.status_code == 200 and cert.content[:4] == b"%PDF", str(cert.status_code))

# Situation 2 : 100% → travaux 5 000, solde d'acompte 1 500
r2 = s.post(f"{API}/situations", json={"marche_id": qid,
                                       "lines": [{"idx": 0, "pct": 100}, {"idx": 1, "pct": 100}],
                                       "deposit_mode": "prorata"})
d2 = r2.json()
check("situation 2 : solde acompte 1500 déduit", d2.get("deposit_imputed_ht") == 1500, str(d2)[:300])
check("situation 2 : facture HT = 3500", d2.get("total_ht") == 3500, str(d2.get("total_ht")))

summ2 = s.get(f"{API}/situations/summary", params={"marche_id": qid}).json()
check("summary : acompte totalement imputé, disponible 0",
      summ2["deposit"]["imputed_ht"] == 3000 and summ2["deposit"]["available_ht"] == 0,
      str(summ2["deposit"])[:300])

# Jamais plus que le disponible
r3 = s.post(f"{API}/situations", json={"marche_id": qid, "lines": [{"idx": 0, "pct": 100}],
                                       "deposit_mode": "full"})
check("plus d'acompte disponible → création refusée (delta nul)", r3.status_code == 400, r3.text[:150])

# Suppression → l'acompte redevient disponible
s.delete(f"{API}/situations/{d2['situation_id']}")
summ3 = s.get(f"{API}/situations/summary", params={"marche_id": qid}).json()
check("suppression situation 2 → 1500 HT redeviennent disponibles",
      summ3["deposit"]["available_ht"] == 1500, str(summ3["deposit"])[:300])

# Module simple depuis le devis (/documents/{id}/situation-invoice) — même logique
s.delete(f"{API}/situations/{d1['situation_id']}")
recap = s.get(f"{API}/documents/{qid}/billing-recap").json()
check("billing-recap expose l'acompte encaissé", recap["deposit"]["available_ht"] == 3000,
      str(recap.get("deposit"))[:300])
si = s.post(f"{API}/documents/{qid}/situation-invoice", json={"pct": 50, "deposit_mode": "prorata"}).json()
check("situation simple 50% : 1500 HT d'acompte déduit", si.get("deposit_imputed_ht") == 1500, str(si)[:300])
check("situation simple : facture HT = 3500", si.get("totals", {}).get("ht") == 3500, str(si.get("totals"))[:200])
sm = s.post(f"{API}/documents/{qid}/situation-invoice",
            json={"pct": 50, "deposit_mode": "manual", "deposit_amount_ht": 99999}).json()
check("mode manuel plafonné au disponible (1500)", sm.get("deposit_imputed_ht") == 1500, str(sm)[:300])
sn = s.post(f"{API}/documents/{qid}/situation-invoice", json={"pct": 10, "deposit_mode": "none"}).json()
check("mode none : aucune déduction", sn.get("deposit_imputed_ht") == 0, str(sn)[:200])

# Nettoyage
for did in [si.get("doc_id"), sm.get("doc_id"), sn.get("doc_id"), dep.get("doc_id"), qid]:
    if did:
        s.delete(f"{API}/documents/{did}")

print(f"\n{ok} OK / {fail} KO")
sys.exit(1 if fail else 0)
