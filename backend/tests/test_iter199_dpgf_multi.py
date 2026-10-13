"""DPGF multi-documents : plusieurs bordereaux + plusieurs CCTP dans une même étude."""
import io
import os
import re
import sys
import zipfile

import openpyxl
import requests

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


def wb_bytes(lot, lines):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["Désignation", "Unité", "Quantité", "Prix unitaire HT", "Montant HT"])
    ws.append([lot, None, None, None, None])
    for d, u, q in lines:
        ws.append([d, u, q, None, None])
    out = io.BytesIO()
    wb.save(out)
    return out.getvalue()


XL = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
b1 = wb_bytes("01 — MACONNERIE", [("Mur en blocs béton 20 cm", "m2", 40),
                                  ("Chape ciment 5 cm", "m2", 30)])
b2 = wb_bytes("03 — CARRELAGE", [("Carrelage grès cérame 60x60 collé", "m2", 25),
                                 ("Faïence murale salle de bain", "m2", 12)])
c1 = ("CCTP LOT MACONNERIE — blocs de classe B40 hourdés au mortier bâtard 350 kg/m3, "
      "chape armée treillis soudé, respect des NF DTU. Nettoyage quotidien à la charge "
      "de l'entreprise, protection des ouvrages livrés obligatoire.\n") * 4
c2 = ("CCTP LOT CARRELAGE — carrelage classé U4P4E3C2 posé en double encollage sur chape "
      "désolidarisée, joints époxy en pièces humides, faïence collée sur plaques hydrofuges.\n") * 4

r = s.post(f"{API}/auth/login", json={"email": EMAIL, "password": PWD}, timeout=30)
check("login pro", r.status_code == 200, r.text[:200])
if r.status_code != 200:
    sys.exit(1)

files = [("files", ("lot1_macon.xlsx", b1, XL)),
         ("files", ("lot3_carrelage.xlsx", b2, XL)),
         ("cctp_files", ("cctp_macon.txt", c1.encode(), "text/plain")),
         ("cctp_files", ("cctp_carrelage.txt", c2.encode(), "text/plain"))]
data = {"instructions": "ne chiffre pas la faïence", "analyse_cctp": "true", "market_compare": "true"}
r = s.post(f"{API}/pro/dpgf/import", files=files, data=data, timeout=240)
check("import de 2 bordereaux + 2 CCTP", r.status_code == 200, r.text[:400])
if r.status_code != 200:
    sys.exit(1)
res = r.json()
fid = res["file_id"]

check("2 sources enregistrées", len(res["sources"]) == 2, str(res["sources"])[:200])
check("4 lignes au total (2 par fichier)", res["line_count"] == 4, str(res["line_count"]))
check("chaque ligne référence son fichier",
      {l["src_name"] for l in res["lines"]} == {"lot1_macon.xlsx", "lot3_carrelage.xlsx"},
      str({l["src_name"] for l in res["lines"]}))
check("identifiants de ligne uniques entre fichiers",
      len({l["line_id"] for l in res["lines"]}) == 4, str([l["line_id"] for l in res["lines"]]))
check("2 lots détectés", len(res["lots"]) == 2, str([x["lot"] for x in res["lots"]]))
check("les 2 CCTP sont pris en compte",
      len(res["cctp"]["documents"]) == 2 and bool(res["cctp"]["summary"]), str(res["cctp"])[:300])
faience = [l for l in res["lines"] if "aïence" in l["designation"]]
check("consigne appliquée sur les 2 fichiers (faïence exclue)",
      faience and all(l["excluded"] for l in faience), str(faience)[:200])
check("total général > 0", res["grand_total_ht"] > 0, str(res["grand_total_ht"]))

z = s.get(f"{API}/pro/dpgf/file/{fid}")
check("téléchargement groupé en ZIP", z.status_code == 200 and z.content[:2] == b"PK", str(z.status_code))
names = zipfile.ZipFile(io.BytesIO(z.content)).namelist()
check("le ZIP contient les 2 classeurs chiffrés", len(names) == 2, str(names))
one = s.get(f"{API}/pro/dpgf/file/{fid}", params={"src": 1})
check("téléchargement d'un seul bordereau (src=1)",
      one.status_code == 200 and one.headers.get("content-type", "").endswith("spreadsheetml.sheet"),
      str(one.headers.get("content-type")))

q = s.post(f"{API}/pro/dpgf/{fid}/quote", json={"vat_rate": 20, "full_descriptions": True})
check("devis unique à partir des 2 bordereaux", q.status_code == 200, q.text[:300])
doc = s.get(f"{API}/documents/{q.json()['doc_id']}").json()
check("devis contient les lignes des 2 lots", len(doc["lines"]) == 4, str(len(doc["lines"])))
check("TVA 20 % appliquée", all(l["vat_rate"] == 20 for l in doc["lines"]), "TVA incorrecte")

s.delete(f"{API}/documents/{q.json()['doc_id']}")
s.delete(f"{API}/pro/dpgf/{fid}")

# Compatibilité : un seul fichier via le champ « file »
r2 = s.post(f"{API}/pro/dpgf/import", files={"file": ("solo.xlsx", b1, XL)},
            data={"analyse_cctp": "false", "market_compare": "false"}, timeout=180)
check("compatibilité mono-fichier (champ file)", r2.status_code == 200, r2.text[:300])
if r2.status_code == 200:
    solo = r2.json()
    x = s.get(f"{API}/pro/dpgf/file/{solo['file_id']}")
    check("mono-fichier → .xlsx direct (pas de ZIP)",
          x.headers.get("content-type", "").endswith("spreadsheetml.sheet"),
          str(x.headers.get("content-type")))
    s.delete(f"{API}/pro/dpgf/{solo['file_id']}")

print(f"\n{ok} OK / {fail} KO")
sys.exit(1 if fail else 0)
