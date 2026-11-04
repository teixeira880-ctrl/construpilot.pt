"""Lot 63 — contrôle des cotes : plus de « KO » sur un plan juste dont l'emprise n'est pas un rectangle.

Test réel (plans du fondateur, moteur de production) : PC v3 p.8 — 7 cotes sur 7 justes, verdict « KO » ;
Gourlay p.10, PC v3 p.11 et p.13 : verdict « KO » sans aucune cote fausse. Cause : les « dimensions générales
opposées » (gauche/droite, haut/bas) sont supposées égales comme sur un rectangle ; une maison en L ou avec
décrochés (9,89 m / 6,74 m) était déclarée incohérente.
Correctif (engines/plan_cotes.py) : écart > 30 cm ou > 5 % → « emprise non rectangulaire probable » (non
déterminé, pas une erreur) ; 10 à 30 cm → « à vérifier » (décroché possible) ; ≤ 10 cm → inchangé (KO si > 2 cm).
La conclusion le dit clairement au lieu d'affirmer « les dimensions générales opposées sont égales ».
Usage : python3 lots/l63/apply_l63.py <racine /app> <fr|pt>   (idempotent ; ARRÊT si une ancre manque)
"""
import pathlib
import sys

root = pathlib.Path(sys.argv[1])
site = sys.argv[2]
assert site in ("fr", "pt")
f = root / "backend" / "engines" / "plan_cotes.py"
s = f.read_text(encoding="utf-8")
if "Lot 63" in s:
    print("déjà appliqué"); print(f"L63 {site.upper()} OK"); sys.exit(0)
for a in ("def _find_facades(", "def quick_conclusion(", "def check_dimensions("):
    if a not in s:
        print(f"ANCRE {a!r} introuvable — ARRÊT, rien écrit"); sys.exit(1)
T = {"fr": {"note": "Dimensions générales opposées différentes ({lst}) : emprise non rectangulaire probable (décrochés, forme en L) — ce n'est pas une incohérence démontrée.",
            "allok_prefix": "Toutes les cotes inscrites correspondent",
            "allok": "Toutes les cotes inscrites correspondent à la mesure, les chaînes se referment, les cotes sont rattachées au dessin et les éléments étiquetés ont la largeur annoncée : aucune incohérence relevée sur cette page.",
            "pair": "{a:.2f} m {sa} / {b:.2f} m {sb}"},
     "pt": {"note": "Dimensões gerais opostas diferentes ({lst}): implantação provavelmente não retangular (recuos, forma em L) — não é uma incoerência demonstrada.",
            "allok_prefix": "Todas as cotas inscritas correspondem",
            "allok": "Todas as cotas inscritas correspondem à medição, as cadeias fecham, as cotas estão associadas ao desenho e os elementos etiquetados têm a largura anunciada: nenhuma incoerência registada nesta página.",
            "pair": "{a:.2f} m {sa} / {b:.2f} m {sb}"}}[site]
ADD = f'''

# --- Lot 63 : emprise non rectangulaire ≠ incohérence ---
_find_facades_lot63_base = _find_facades


def _find_facades(items, img_w, img_h):
    out = _find_facades_lot63_base(items, img_w, img_h)
    for fc in out:
        d = abs(float(fc.get("delta_m") or 0))
        big = max(abs(float(fc.get("a_m") or 0)), abs(float(fc.get("b_m") or 0)), 1e-6)
        if fc.get("status") in ("ko", "warn"):
            if d > 0.30 or d / big > 0.05:
                fc["status"] = "nd"
                fc["shape_note"] = "non_rectangular"
            elif d > 0.10:
                fc["status"] = "warn"
    return out


_quick_conclusion_lot63_base = quick_conclusion


def quick_conclusion(report):
    fac = report.get("facades") or []
    nd = [fc for fc in fac if fc.get("status") == "nd"]
    if not nd:
        return _quick_conclusion_lot63_base(report)
    base = _quick_conclusion_lot63_base({{**report, "facades": [fc for fc in fac if fc.get("status") != "nd"]}})
    if base.startswith({T["allok_prefix"]!r}):
        base = {T["allok"]!r}
    lst = " ; ".join({T["pair"]!r}.format(a=fc["a_m"], sa=fc.get("a_side", ""), b=fc["b_m"], sb=fc.get("b_side", "")) for fc in nd[:3])
    return {T["note"]!r}.format(lst=lst) + " " + base
'''
f.write_text(s.rstrip("\n") + "\n" + ADD, encoding="utf-8")
(root / "backend" / "tests" / "test_l63.py").write_bytes((pathlib.Path(__file__).resolve().parent / "tests" / "test_l63.py").read_bytes())
print("ok backend/engines/plan_cotes.py + backend/tests/test_l63.py")
print(f"L63 {site.upper()} OK")
