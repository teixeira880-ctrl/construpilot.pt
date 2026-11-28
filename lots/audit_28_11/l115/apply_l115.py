"""Lot 115 (FR + PT) — erreurs « nom non défini » trouvées par analyse statique (pyflakes) du backend.

 1. Estimation → « Envoyer par email » : la fonction utilise le module `html` (html.escape) puis crée plus loin une
    variable locale du même nom `html = emailer.wrap_html(...)` → Python lève UnboundLocalError dès la 1re ligne :
    l'envoi de l'estimation par e-mail échoue à chaque fois. Variable renommée `html_body`.
 2. Études PT/UA (especialidades) : `prev_z` utilisé avant d'être défini si la première cote n'est pas la plus basse.
 3. Atelier, édition par phrase : `_sai(...)` appelé sans préfixe alors que la fonction vit dans le module RE
    (appliqué seulement si `_sai` n'est défini nulle part dans le fichier).

Usage : python3 lots/l115/apply_l115.py <racine /app> <fr|pt>   (idempotent, marqueur CP-AUDIT-NUIT-7)
"""
import pathlib
import re
import sys

root = pathlib.Path(sys.argv[1])
site = sys.argv[2] if len(sys.argv) > 2 else "fr"
MARK = "CP-AUDIT-NUIT-7"
report = []


def edit(name, rel, fn):
    p = root / rel
    if not p.exists():
        return report.append(f"ABSENT    {name}")
    txt = p.read_text(encoding="utf-8")
    res = fn(txt)
    if res is None:
        return report.append(f"IGNORÉ    {name}")
    if res == txt:
        return report.append(f"DÉJÀ      {name}")
    p.write_text(res, encoding="utf-8")
    report.append(f"OK        {name}")


def fix_email(txt):
    m = re.search(r"\nasync def estimation_pdf_email\(.*?(?=\n@router|\nasync def |\ndef |\Z)", txt, flags=re.S)
    if not m:
        return None
    body = m.group(0)
    if "html_body" in body:
        return txt
    if "html.escape(" not in body or "        html = emailer.wrap_html(" not in body:
        return txt if "html = " not in body else None
    new = body.replace("        html = emailer.wrap_html(", "        html_body = emailer.wrap_html(")
    new = re.sub(r"(send_email_with_pdf\([^)]*?subject,\s*)html(\s*,)", r"\1html_body\2", new, count=1)
    if "subject, html," in new or "subject, html_body" not in new:
        return None
    new = new.replace("    safe_client = html.escape(", f"    # {MARK} : la variable du corps de l'e-mail ne masque plus le module html\n    safe_client = html.escape(", 1)
    return txt.replace(body, new)


def fix_prev_z(txt):
    if MARK in txt:
        return txt
    old = '    prev, prev_q = "E", "AQS"\n    for c in cotas:\n'
    if txt.count(old) != 1:
        return None
    return txt.replace(old, f'    prev, prev_q = "E", "AQS"\n    prev_z = z0  # {MARK}\n    for c in cotas:\n')


def fix_sai(txt):
    if re.search(r"^\s*def _sai\b|^_sai\s*=|import .*\b_sai\b", txt, flags=re.M):
        return txt
    if "**_sai(m, der)" not in txt:
        return txt
    if "RE._sai(" not in txt:
        return None
    return txt.replace("**_sai(m, der)", "**RE._sai(m, der)")


edit("1 Estimation : envoi par e-mail", "backend/routes/estimation_routes.py", fix_email)
edit("2 especialidades : prev_z initialisé", "backend/engines/calc_lots_ua/especialidades.py", fix_prev_z)
edit("3 Atelier phrase : RE._sai", "backend/routes/atelier_archi.py", fix_sai)

print(f"Lot 115 ({site}) — {MARK}")
print("\n".join(report))
