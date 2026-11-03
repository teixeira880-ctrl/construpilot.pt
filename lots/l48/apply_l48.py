"""Lot 48 — import PDF de devis/factures : refuser les doublons (même type + même numéro).

Constat du test du 03/11 : une facture importée deux fois (même n°, même montant) compte
double dans le chiffre d'affaires. Désormais l'import ignore un document dont le numéro
existe déjà pour ce compte et le signale dans le résultat (« déjà importé »).

Usage : python3 lots/l48/apply_l48.py <racine /app> <fr|pt>
S'arrête (exit 1) sans rien écrire si une ancre manque. Idempotent.
"""
import pathlib
import sys

root = pathlib.Path(sys.argv[1])
site = sys.argv[2]
assert site in ("fr", "pt")
f = root / "backend" / "routes" / "documents.py"
s = f.read_text(encoding="utf-8")
if "_already_imported" in s:
    print("déjà appliqué")
    print(f"L48 {site.upper()} OK")
    sys.exit(0)

MSG = ('f"Déjà importé : le n° {number} existe déjà"' if site == "fr"
       else 'f"Já importado: o n.º {number} já existe"')

EDITS = [
    ("async def _bump_counter(user_id: str, doc_type: str, seq: int) -> None:\n",
     "async def _already_imported(user_id: str, doc_type: str, number: str | None) -> bool:\n"
     "    \"\"\"Vrai si ce compte a déjà un document de ce type avec ce numéro (anti-doublon d'import).\"\"\"\n"
     "    if not number:\n"
     "        return False\n"
     "    return bool(await db.pro_documents.find_one(\n"
     "        {\"user_id\": user_id, \"doc_type\": doc_type, \"number\": number}, {\"_id\": 0, \"doc_id\": 1}))\n"
     "\n\n"
     "async def _bump_counter(user_id: str, doc_type: str, seq: int) -> None:\n"),
    ('    number = (item.get("number") or "").strip() or None\n',
     '    number = (item.get("number") or "").strip() or None\n'
     '    if await _already_imported(user["user_id"], dtype, number):\n'
     '        return ({"ok": False, "file": (item.get("file") or "").strip(), "duplicate": True,\n'
     f'                 "number": number, "error": {MSG}}}, dtype, 0)\n'),
    ('            number = (ext.get("number") or "").strip() or None\n',
     '            number = (ext.get("number") or "").strip() or None\n'
     '            if await _already_imported(user["user_id"], dtype, number):\n'
     f'                results.append({{"file": name, "ok": False, "duplicate": True, "number": number, "error": {MSG}}})\n'
     '                continue\n'),
]
for old, new in EDITS:
    c = s.count(old)
    if c != 1:
        print(f"ANCRE introuvable ({c}) : {old[:60]!r} — ARRÊT, rien écrit")
        sys.exit(1)
    s = s.replace(old, new)

# Le 2e chemin (import direct) doit connaître dtype avant le contrôle : vérifier l'ordre.
i_dt = s.find('            dtype = ext.get("doc_type") or "quote"\n')
i_chk = s.find('            if await _already_imported(user["user_id"], dtype, number):\n')
if i_dt == -1 or i_dt > i_chk:
    print("ordre dtype/number inattendu dans import_documents_pdf — ARRÊT, rien écrit")
    sys.exit(1)
i_dt2 = s.find('\n    dtype = item.get("doc_type") if item.get("doc_type") in DOC_TYPES else "quote"\n')
i_chk2 = s.find('\n    if await _already_imported(user["user_id"], dtype, number):\n')
if i_dt2 == -1 or i_dt2 > i_chk2:
    print("ordre dtype/number inattendu dans _persist_imported_doc — ARRÊT, rien écrit")
    sys.exit(1)

f.write_text(s, encoding="utf-8")
t = pathlib.Path(__file__).resolve().parent / "tests" / "test_l48.py"
(root / "backend" / "tests" / "test_l48.py").write_bytes(t.read_bytes())
print("ok backend/routes/documents.py + backend/tests/test_l48.py")
print(f"L48 {site.upper()} OK")
