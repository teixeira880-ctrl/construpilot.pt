"""Lot 117 (FR + PT) — numérotation après import de devis/factures d'un autre logiciel.

Constat : après import de « F202600106 » (année 2026 collée au n° 00106), le compteur ConstruPilot sautait à
202 600 106 → les documents suivants sortaient en « DEV-2026-202600128 » / « FAC-2026-202600128 ».
Correctif : quand le dernier groupe de chiffres commence par une année (2000-2099) suivie d'au moins 2 chiffres,
seule la partie après l'année est reprise (F202600106 → 106 ; DEV-2026-0042 → 42 inchangé).
Les compteurs déjà enregistrés ne sont jamais baissés (pas de doublon possible).

Usage : python3 lots/l117/apply_l117.py <racine /app> <fr|pt>   (idempotent, marqueur CP-AUDIT-NUIT-9)
"""
import pathlib
import sys

root = pathlib.Path(sys.argv[1])
MARK = "CP-AUDIT-NUIT-9"
p = root / "backend/routes/documents.py"
txt = p.read_text(encoding="utf-8")
OLD = '''def _seq_from_number(number: str) -> int:
    import re
    m = re.findall(r"\\d+", number or "")
    return int(m[-1]) if m else 0
'''
NEW = f'''def _seq_from_number(number: str) -> int:
    import re
    m = re.findall(r"\\d+", number or "")
    if not m:
        return 0
    last = m[-1]
    # {MARK} : « F202600106 » = année 2026 + n° 00106 → 106 (et non 202 600 106)
    if len(last) >= 6 and 2000 <= int(last[:4]) <= 2099:
        return int(last[4:])
    return int(last)
'''
if MARK in txt:
    print("DÉJÀ      numérotation après import")
elif txt.count(OLD) != 1:
    print("IGNORÉ    numérotation après import (ancre absente)")
else:
    p.write_text(txt.replace(OLD, NEW), encoding="utf-8")
    print("OK        numérotation après import")
