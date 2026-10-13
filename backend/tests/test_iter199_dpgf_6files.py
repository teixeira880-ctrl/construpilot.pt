"""DPGF : charge réelle — 6 bordereaux + 6 CCTP dans une seule étude."""
import io
import os
import re
import sys
import time
import zipfile

import openpyxl
import requests

with open("/app/frontend/.env") as f:
    BASE = re.search(r"REACT_APP_BACKEND_URL=(\S+)", f.read()).group(1)
API = BASE.rstrip("/") + "/api"
EMAIL = os.environ.get("TEST_PRO_EMAIL", "pro@construpilot.fr")
PWD = os.environ.get("TEST_PRO_PASSWORD", "Pro2026!")
XL = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

LOTS = [
    ("01 — MACONNERIE", [("Mur en blocs béton 20 cm hourdés au mortier", "m2", 40),
                         ("Chape ciment dosée à 300 kg/m3", "m2", 30),
                         ("Enduit ciment de dressage sur mur", "m2", 25)]),
    ("02 — CHARPENTE", [("Charpente sapin traité classe 2", "m2", 60),
                        ("Liteaunage pour couverture tuiles", "m2", 60),
                        ("Chevêtre bois pour fenêtre de toit", "u", 2)]),
    ("03 — CARRELAGE", [("Carrelage grès cérame 60x60 collé", "m2", 45),
                        ("Plinthes carrelage assorties", "ml", 30),
                        ("Faïence murale salle de bain", "m2", 12)]),
    ("04 — PLOMBERIE", [("Alimentation PER encastrée par point d'eau", "u", 8),
                        ("Evacuation PVC diamètre 100", "ml", 18),
                        ("Pose de WC suspendu avec bâti support", "u", 2)]),
    ("05 — REVETEMENTS DE SOL", [("Parquet contrecollé chêne collé plein", "m2", 35),
                                 ("Plinthes bois chêne vernies", "ml", 28),
                                 ("Ragréage autolissant fibré", "m2", 35)]),
    ("06 — PEINTURE", [("Peinture acrylique mate 2 couches sur murs", "m2", 120),
                       ("Peinture plafond blanc mat 2 couches", "m2", 60),
                       ("Enduit de rebouchage et ponçage", "m2", 120)]),
]

CCTP_TPL = (
    "CAHIER DES CLAUSES TECHNIQUES PARTICULIERES — {lot}\n"
    "ARTICLE 1 : les ouvrages seront exécutés conformément aux NF DTU en vigueur, avec "
    "matériaux certifiés NF ou équivalent. L'entreprise fournira ses fiches techniques.\n"
    "ARTICLE 2 : prescriptions particulières du lot {lot} — matériaux de marque imposée, "
    "épaisseurs minimales respectées, mise en œuvre soignée, finition de degré C.\n"
    "ARTICLE 3 : nettoyage quotidien du chantier, protection des ouvrages livrés, "
    "échafaudages et moyens de levage à la charge de l'entreprise.\n"
)

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
    ws.append([f"Bordereau {lot}"])
    ws.append(["Désignation", "Unité", "Quantité", "Prix unitaire HT", "Montant HT"])
    ws.append([lot, None, None, None, None])
    for d, u, q in lines:
        ws.append([d, u, q, None, None])
    ws.append(["Sous-total lot", None, None, None, None])
    out = io.BytesIO()
    wb.save(out)
    return out.getvalue()


r = s.post(f"{API}/auth/login", json={"email": EMAIL, "password": PWD}, timeout=30)
check("login pro", r.status_code == 200, r.text[:200])
if r.status_code != 200:
    sys.exit(1)

files = []
for i, (lot, lines) in enumerate(LOTS):
    files.append(("files", (f"dpgf_lot{i + 1}.xlsx", wb_bytes(lot, lines), XL)))
    files.append(("cctp_files", (f"cctp_lot{i + 1}.txt", (CCTP_TPL.format(lot=lot) * 4).encode(),
                                 "text/plain")))

t0 = time.time()
r = s.post(f"{API}/pro/dpgf/import", files=files,
           data={"instructions": "ne chiffre pas le carrelage ni le parquet, marge 10 %",
                 "analyse_cctp": "true", "market_compare": "true"}, timeout=600)
elapsed = round(time.time() - t0, 1)
check(f"import de 6 bordereaux + 6 CCTP (en {elapsed}s)", r.status_code == 200, r.text[:400])
if r.status_code != 200:
    sys.exit(1)
res = r.json()
fid = res["file_id"]
print(f"   lots: {[x['lot'] for x in res['lots']]}")
print(f"   lignes: {res['line_count']} · chiffrées: {res['priced']} · exclues: {res['excluded']}"
      f" · total: {res['grand_total_ht']} € HT")

check("6 sources enregistrées", len(res["sources"]) == 6, str(len(res["sources"])))
check("18 lignes lues (3 par bordereau)", res["line_count"] == 18, str(res["line_count"]))
check("6 lots détectés", len(res["lots"]) == 6, str([x["lot"] for x in res["lots"]]))
check("6 CCTP analysés", len(res["cctp"]["documents"]) == 6, str(len(res["cctp"]["documents"])))
check("synthèse CCTP produite", bool(res["cctp"]["summary"]), str(res["cctp"])[:200])
check("prescriptions CCTP rattachées", any(l.get("cctp_note") for l in res["lines"]), "aucune note")

excl = [l for l in res["lines"] if l["excluded"]]
check("carrelage et parquet exclus dans les bons fichiers",
      excl and all(("arrelage" in l["designation"] or "linthes" in l["designation"]
                    or "arquet" in l["designation"] or "aïence" in l["designation"])
                   for l in excl), str([l["designation"] for l in excl]))
priced = [l for l in res["lines"] if not l["excluded"] and l["pu"]]
check("toutes les lignes non exclues sont chiffrées",
      len(priced) == res["line_count"] - len(excl),
      f"{len(priced)} chiffrées / {res['line_count'] - len(excl)} attendues")
check("marge 10 % détectée", res["directives"].get("margin_pct") == 10,
      str(res["directives"].get("margin_pct")))
check("identifiants de ligne uniques", len({l["line_id"] for l in res["lines"]}) == 18, "doublons")
check("total = somme des lots",
      abs(res["grand_total_ht"] - sum(x["total_ht"] for x in res["lots"])) < 0.05,
      str(res["grand_total_ht"]))

z = s.get(f"{API}/pro/dpgf/file/{fid}", timeout=120)
check("ZIP des 6 classeurs chiffrés", z.status_code == 200 and z.content[:2] == b"PK", str(z.status_code))
if z.status_code == 200:
    names = zipfile.ZipFile(io.BytesIO(z.content)).namelist()
    check("6 fichiers dans le ZIP", len(names) == 6, str(names))

q = s.post(f"{API}/pro/dpgf/{fid}/quote", json={"vat_rate": 10, "full_descriptions": True}, timeout=120)
check("devis unique pour les 6 lots", q.status_code == 200, q.text[:300])
if q.status_code == 200:
    doc = s.get(f"{API}/documents/{q.json()['doc_id']}").json()
    cats = {l.get("category") for l in doc["lines"]}
    check("6 catégories (une par lot) dans le devis", len(cats) == 6, str(cats))
    check("18 lignes dans le devis", len(doc["lines"]) == 18, str(len(doc["lines"])))
    check("lignes exclues à 0 € avec mention",
          all("Non chiffré" in l["designation"] for l in doc["lines"] if l["unit_price_ht"] == 0),
          "mention manquante")
    s.delete(f"{API}/documents/{q.json()['doc_id']}")
s.delete(f"{API}/pro/dpgf/{fid}")

print(f"\n{ok} OK / {fail} KO")
sys.exit(1 if fail else 0)
