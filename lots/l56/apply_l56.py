"""Lot 56 — lecture automatique des pages de plan : niveau, type de vue (tests réels sur des PDF clients).

Constats (FR) :
  1. Permis Gourlay p.11 : niveau « R+50 » — « 1 : 50 » (échelle) suivi à la ligne de « Etage 1 » lu comme
     « 50e étage ». Et la forme « Étage 1 » n'était jamais reconnue.
  2. Plan AES « Plan coffrage PH R+4 » classé « coupe » (repère « Coupe 12 ») au lieu de plan de structure ;
     « Plan coffrage » (sans « de ») non reconnu ; niveau R+4 du titre non retenu (« Accès combles », « sous-sol »
     cités dans les notes → plusieurs niveaux).
Constats (PT) : tout était en français — « CORTE AA », « ALÇADO NORTE », « PLANTA DO PISO 1 », « PLANTA DE
COFRAGEM », « r/c », « 1.º andar », « sótão » jamais reconnus ; « inclinação 1/2 » pris pour une échelle.

Correctifs (engines/plan_page_context.py) : niveaux FR+PT sans enjamber les lignes ni lire une échelle ;
repère « Coupe 12 » ≠ titre de coupe ; « plan (de) coffrage » / « planta de cofragem » = plan de structure ;
niveau du titre (« Plan … R+4 », « Planta do piso 1 ») prioritaire quand les notes citent d'autres niveaux ;
mots PT pour coupe / façade / plan ; filtre des fausses échelles en PT.

Usage : python3 lots/l56/apply_l56.py <racine /app> <fr|pt>   (idempotent ; ARRÊT si une ancre manque)
"""
import pathlib
import sys

root = pathlib.Path(sys.argv[1])
site = sys.argv[2]
assert site in ("fr", "pt")
f = root / "backend" / "engines" / "plan_page_context.py"
s = f.read_text(encoding="utf-8")
if "Lot 56" in s:
    print("déjà appliqué"); print(f"L56 {site.upper()} OK"); sys.exit(0)

EDITS = [
 ('    section = bool(re.search(r"^\\s*COUPES?\\s+(?!FEU\\b)\\S", text, re.I | re.M))\n',
  '    # Lot 56 : « Coupe 12 » seul sur sa ligne est un repère de coupe, pas un titre ; PT : CORTE(S)\n'
  '    section = bool(re.search(r"^\\s*(?:COUPES?\\s+(?!FEU\\b)(?!\\d+\\s*$)|CORTES?\\s+(?!CORTA\\b)(?!\\d+\\s*$))\\S", text, re.I | re.M))\n'),
 ('    elevation = bool(re.search(r"^\\s*FA[ÇC]ADES?\\s+(?:BAT|NORD|SUD|EST|OUEST)", text, re.I | re.M))\n',
  '    elevation = bool(re.search(r"^\\s*(?:FA[ÇC]ADES?\\s+(?:BAT|NORD|SUD|EST|OUEST)|AL[ÇC]ADOS?\\s+(?:NORTE|SUL|NASCENTE|POENTE|ESTE|OESTE|PRINCIPAL|POSTERIOR|LATERAL))", text, re.I | re.M))\n'),
 ('    floor = bool(re.search(r"^\\s*PLAN\\s+(?:R[+\\-\\d ]|RDC|DE\\s+RDC|DU\\s+(?:RDC|SOUS-SOL))", text, re.I | re.M))\n',
  '    floor = bool(re.search(r"^\\s*(?:PLAN\\s+(?:R[+\\-\\d ]|RDC|DE\\s+RDC|DU\\s+(?:RDC|SOUS-SOL))'
  '|PLANTA\\s+(?:D[OA]\\s+)?(?:PISO|R/?C|R[ÉE]S|CAVE|S[ÓO]T[ÃA]O|\\d|PRIMEIRO|SEGUNDO|PISO))", text, re.I | re.M))  # Lot 56 : PT\n'),
 ('    elif re.search(r"^\\s*(?:coffrages?\\s*[-:]|plan(?:s)? de coffrage\\b)", plain, re.M):\n',
  '    elif re.search(r"^\\s*(?:coffrages?\\s*[-:]|plan(?:s)?\\s+(?:de\\s+)?coffrage\\b|plantas?\\s+(?:de\\s+)?cofragem\\b)", plain, re.M):  # Lot 56\n'),
 ('    unique_level = levels[0] if len(levels) == 1 and kind in ("floor_plan", "unknown") else {}\n',
  '    unique_level = levels[0] if len(levels) == 1 and kind in ("floor_plan", "unknown", "structural_plan") else {}\n'
  '    if not unique_level and kind in ("floor_plan", "unknown", "structural_plan"):  # Lot 56 : niveau du titre\n'
  '        _tl = _title_levels(text)\n'
  '        if len(_tl) == 1:\n'
  '            unique_level = _tl[0]\n'),
]
if site == "pt":
    EDITS.insert(0, (
     '    return sorted({int(m.group(1)) for m in _SCALE.finditer(text or "") if int(m.group(1)) > 0})\n',
     '    # Lot 56 : « inclinação 1/2 », « folha 1/3 », « página 1/10 » ne sont pas des échelles\n'
     '    text = text or ""\n'
     '    out = set()\n'
     '    for m in _SCALE.finditer(text):\n'
     '        den = int(m.group(1))\n'
     '        if den not in STANDARD_SCALES:\n'
     '            continue\n'
     '        if den < 10 and not re.search(r"(?:[ée]ch(?:elle)?|scale|esc(?:ala)?)\\.?\\s*:?\\s*$", text[max(0, m.start() - 12):m.start()], re.I):\n'
     '            continue\n'
     '        before = text[max(0, m.start() - 14):m.start()]\n'
     '        if _NOT_SCALE_BEFORE.search(before) or re.match(r"\\s*(?:folhas?|p[áa]ginas?|feuilles?|pages?)\\b", text[m.end():m.end() + 12], re.I):\n'
     '            continue\n'
     '        out.add(den)\n'
     '    return sorted(out)\n'))
for old, new in EDITS:
    c = s.count(old)
    if c != 1:
        print(f"ANCRE introuvable ({c}/1) : {old[:80]!r} — ARRÊT, rien écrit"); sys.exit(1)
    s = s.replace(old, new)

PT_SCALES = '''
STANDARD_SCALES = {1, 2, 5, 10, 20, 25, 50, 75, 100, 125, 150, 200, 250, 500, 1000, 2000, 2500, 5000, 10000, 25000}
_NOT_SCALE_BEFORE = re.compile(r"(inclina[çc][ãa]o|pendente|declive|junta|juntas|folha|folhas|p[áa]gina|p[áa]ginas|tra[çc]o|dosagem|rela[çc][ãa]o"
                               r"|pente|pentes|joint|joints|page|pages|feuille|feuilles|ratio)\\W{0,3}$", re.I)
''' if site == "pt" else ""
LABELS = ('"Sótão"', '"Cave"') if site == "pt" else ('"Combles"', '"Sous-sol"')

ADD = f'''

# --- Lot 56 : niveaux FR + PT, sans enjamber les lignes ni lire une échelle -----------------------------------
{PT_SCALES}
def level_candidates(text: str) -> list[dict]:
    text = text or ""
    levels = set()
    if re.search(r"\\b(?:sous[\\s-]?sol|caves?|s[\\s-]sol|subcave)\\b", text, re.I):
        levels.add(-1)
    if re.search(r"\\b(?:rdc|rez[\\s-]de[\\s-]chauss[éeè]e?|r/c|r[ée]s[\\s-]do[\\s-]ch[ãa]o)(?![\\w/])", text, re.I):
        levels.add(0)
    for match in re.finditer(r"(?<![\\w/])r[ \\t]*([+-])[ \\t]*(\\d{{1,2}})\\b", text, re.I):
        levels.add(int(match.group(2)) * (1 if match.group(1) == "+" else -1))
    for match in re.finditer(r"(?<![:/\\d])(?<![:/][ \\t])\\b(\\d{{1,2}})(?:e|er|eme|ème)?[ \\t]*[eé]tage\\b", text, re.I):
        levels.add(int(match.group(1)))
    for match in re.finditer(r"\\b[eé]tage[ \\t]+(\\d{{1,2}})\\b", text, re.I):
        levels.add(int(match.group(1)))
    for match in re.finditer(r"\\bpiso[ \\t]*(-?[ \\t]*\\d{{1,2}})\\b", text, re.I):
        levels.add(int(match.group(1).replace(" ", "").replace("\\t", "")))
    for match in re.finditer(r"(?<![:/\\d])\\b(\\d{{1,2}})[ \\t]*\\.?[ \\t]*[ºo°][ \\t]*andar\\b", text, re.I):
        levels.add(int(match.group(1)))
    if re.search(r"\\b(?:combles?|grenier|s[óo]t[ãa]o|[áa]guas[\\s-]furtadas)\\b", text, re.I):
        levels.add(99)
    return [{{"level_index": n, "level_label": {LABELS[0]} if n == 99 else "RDC" if n == 0 else {LABELS[1]} if n == -1 else f"R{{n:+d}}"}}
            for n in sorted(levels)]


def _title_levels(text: str) -> list[dict]:
    """Niveaux cités dans les lignes de titre (« Plan coffrage PH R+4 », « Planta do piso 1 »)."""
    lines = [ln for ln in (text or "").splitlines() if re.match(r"\\s*(?:plans?|plantas?)\\b", ln, re.I)]
    found = {{}}
    for ln in lines:
        for lv in level_candidates(ln):
            found[lv["level_index"]] = lv
    return list(found.values())
'''
s = s.rstrip("\n") + "\n" + ADD
f.write_text(s, encoding="utf-8")
t = pathlib.Path(__file__).resolve().parent / "tests" / "test_l56.py"
(root / "backend" / "tests" / "test_l56.py").write_bytes(t.read_bytes())
print("ok backend/engines/plan_page_context.py + backend/tests/test_l56.py")
print(f"L56 {site.upper()} OK")
