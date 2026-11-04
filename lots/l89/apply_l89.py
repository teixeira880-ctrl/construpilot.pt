"""Lot 89 (FR + PT) — import DWG sur construpilot.pt : « Caminho ODA_FILE_CONVERTER inválido no servidor ».

Constat (production .pt, 04/11 21 h, import réel R+2.dwg) : la variable ODA_FILE_CONVERTER est définie sur le serveur
mais pointe vers un fichier absent ; la conversion s'arrêtait là au lieu d'essayer Autodesk puis CloudConvert
(chemin qui fonctionne sur .fr pour le même fichier).
Correctif : un exécutable ODA introuvable lève une erreur dédiée, interceptée : on journalise et on passe au
service suivant. Un ODA présent reste prioritaire (comportement inchangé).
Usage : python3 lots/l89/apply_l89.py <racine /app>   (idempotent ; ARRÊT si une ancre manque)
"""
import pathlib
import re
import sys

root = pathlib.Path(sys.argv[1])
f = root / "backend" / "engines" / "dwg_convert.py"
s = f.read_text(encoding="utf-8")
if "Lot 89" in s:
    print("déjà appliqué"); print("L89 OK"); sys.exit(0)
A1 = ('    if os.environ.get("ODA_FILE_CONVERTER"):\n'
      '        output = await asyncio.to_thread(_local_dwg_to_dxf,dwg_bytes)\n'
      '        if provenance is not None: provenance.update(provider="oda", status="converted")\n'
      '        return output\n')
B1 = ('    if os.environ.get("ODA_FILE_CONVERTER"):\n'
      '        try:\n'
      '            output = await asyncio.to_thread(_local_dwg_to_dxf,dwg_bytes)\n'
      '        except OdaMissing89 as exc:  # Lot 89 : ODA déclaré mais absent → service suivant\n'
      '            logger.warning("%s : repli sur les autres convertisseurs", exc)\n'
      '            if provenance is not None: provenance.update(fallback_reason="oda_missing")\n'
      '            output = None\n'
      '        if output is not None:\n'
      '            if provenance is not None: provenance.update(provider="oda", status="converted")\n'
      '            return output\n')
m = re.search(r'    if not executable\.is_absolute\(\) or not executable\.is_file\(\):\n        raise RuntimeError\(("[^"]*ODA_FILE_CONVERTER[^"]*")\)\n', s)
if s.count(A1) != 1 or not m:
    print("ANCRE introuvable — ARRÊT, rien écrit"); sys.exit(1)
s = s.replace(A1, B1)
s = s.replace(m.group(0), m.group(0).replace("raise RuntimeError(", "raise OdaMissing89("))
H = "def is_configured() -> bool:\n"
if s.count(H) != 1:
    print("ANCRE is_configured introuvable — ARRÊT, rien écrit"); sys.exit(1)
s = s.replace(H, "class OdaMissing89(RuntimeError):\n    \"\"\"Lot 89 : ODA_FILE_CONVERTER défini mais exécutable absent.\"\"\"\n\n\n" + H)
f.write_text(s, encoding="utf-8")
(root / "backend" / "tests" / "test_l89.py").write_bytes((pathlib.Path(__file__).resolve().parent / "tests" / "test_l89.py").read_bytes())
print("ok backend/engines/dwg_convert.py + backend/tests/test_l89.py")
print("L89 OK")
