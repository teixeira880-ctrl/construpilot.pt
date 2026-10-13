"""DPGF : nom du chiffrage (label) et alerte de marge minimale par lot."""
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


def dpgf_bytes():
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["Désignation", "Unité", "Quantité", "Prix unitaire HT", "Montant HT"])
    ws.append(["01 — MACONNERIE", None, None, None, None])
    ws.append(["Mur en blocs béton 20 cm", "m2", 10, 100, None])   # prix bordereau → marge 0
    ws.append(["02 — PLOMBERIE", None, None, None, None])
    ws.append(["Alimentation PER par point d'eau", "u", 4, None, None])  # prix IA → coef appliqué
    out = io.BytesIO()
    wb.save(out)
    return out.getvalue()


r = s.post(f"{API}/auth/login", json={"email": EMAIL, "password": PWD}, timeout=30)
check("login pro", r.status_code == 200, r.text[:200])
if r.status_code != 200:
    sys.exit(1)

imp = s.post(f"{API}/pro/dpgf/import", files={"file": ("TEST_iter202.xlsx", dpgf_bytes(), XL)},
             data={"analyse_cctp": "false", "market_compare": "true",
                   "label": "Houilles — Lot 2 variante A", "margin_pct": "15"}, timeout=240)
check("import avec nom du chiffrage", imp.status_code == 200, imp.text[:300])
if imp.status_code != 200:
    sys.exit(1)
res = imp.json()
fid = res["file_id"]
check("nom enregistré à l'import", res["label"] == "Houilles — Lot 2 variante A", str(res["label"]))

hist = s.get(f"{API}/pro/dpgf").json()
mine = next((h for h in hist if h["file_id"] == fid), None)
check("nom visible dans l'historique", mine and mine["label"] == "Houilles — Lot 2 variante A",
      str(mine)[:200])

ren = s.patch(f"{API}/pro/dpgf/{fid}/label", json={"label": "Houilles — Lot 2 variante B"})
check("renommage", ren.status_code == 200 and ren.json()["label"] == "Houilles — Lot 2 variante B",
      ren.text[:200])

# ---- Marge réelle par lot
lots = {x["lot"]: x for x in ren.json()["lots"]}
mac = lots["01 — MACONNERIE"]
plo = lots["02 — PLOMBERIE"]
check("marge du lot au prix bordereau = 0 %", mac["margin_pct"] == 0, str(mac))
check("marge du lot chiffré IA ≈ coefficient 15 %", 14.5 <= plo["margin_pct"] <= 15.5, str(plo))
check("marge en euros calculée", plo["margin_ht"] > 0 and mac["margin_ht"] == 0,
      f"{plo['margin_ht']} / {mac['margin_ht']}")

# ---- Réglage de la marge minimale (persisté sur le compte)
st = s.patch(f"{API}/pro/dpgf/settings/margin", json={"min_margin_pct": 12})
check("marge minimale enregistrée", st.status_code == 200 and st.json()["min_margin_pct"] == 12,
      st.text[:200])
check("marge minimale relue", s.get(f"{API}/pro/dpgf/settings/margin").json()["min_margin_pct"] == 12,
      "valeur non persistée")
low = [l for l in ren.json()["lots"] if l["total_ht"] > 0 and l["margin_pct"] < 12]
check("lot sous le minimum détecté (maçonnerie)",
      [l["lot"] for l in low] == ["01 — MACONNERIE"], str([l["lot"] for l in low]))

# Après application d'un coefficient de 30 % sur la maçonnerie, la marge reste 0 %
# (prix issu du bordereau, jamais majoré) → on vérifie sur le lot plomberie
m = s.patch(f"{API}/pro/dpgf/{fid}/lot-margin", json={"lot": "02 — PLOMBERIE", "margin_pct": 5}).json()
plo2 = {x["lot"]: x for x in m["lots"]}["02 — PLOMBERIE"]
check("marge du lot suit le coefficient (5 %)", 4.5 <= plo2["margin_pct"] <= 5.5, str(plo2))
low2 = [l["lot"] for l in m["lots"] if l["total_ht"] > 0 and l["margin_pct"] < 12]
check("plomberie passe sous le minimum après baisse du coefficient",
      "02 — PLOMBERIE" in low2, str(low2))

s.patch(f"{API}/pro/dpgf/settings/margin", json={"min_margin_pct": 0})
s.delete(f"{API}/pro/dpgf/{fid}")
print(f"\n{ok} OK / {fail} KO")
sys.exit(1 if fail else 0)
