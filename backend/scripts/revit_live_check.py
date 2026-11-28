"""Contrôle réel du métré Revit avec les vraies clés APS du serveur (pré-production uniquement).

Usage : cd backend && python scripts/revit_live_check.py <fichier.rvt> [fr|pt]
Lance UNE traduction Autodesk (mise en cache par fichier : relancer ne recoûte rien),
affiche le résumé et écrit l'Excel dans /tmp/revit_check.xlsx. N'écrit rien dans les comptes clients.
"""
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


async def main(path: str, lang: str):
    from engines import autodesk_md
    from plans_pro.revit_workbook import revit_workbook

    data = Path(path).read_bytes()
    res = await autodesk_md.extract(data, Path(path).name, user_id="revit_live_check", lang=lang)
    t = res.get("revit_takeoff")
    print("statut:", res.get("status"), "| en cache:", res.get("cached"), "| vues:", [v.get("name") for v in res.get("views") or []])
    if not t:
        print("AUCUN MÉTRÉ REVIT — dérivés :", json.dumps(res.get("derivatives"), ensure_ascii=False))
        return 1
    print("éléments mesurés:", t["elements_count"], "| niveaux:", t["levels"])
    for name, q in t["by_ouvrage"].items():
        print(f"  {name:32} n={q['count']:4}  m²={q['total_area_m2']}  m³={q['total_volume_m3']}  ml={q['total_length_m']}")
    for w in t["warnings"]:
        print("  ⚠", w)
    Path("/tmp/revit_check.xlsx").write_bytes(revit_workbook({"filename": Path(path).name}, t))
    print("Excel : /tmp/revit_check.xlsx")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else "pt")))
