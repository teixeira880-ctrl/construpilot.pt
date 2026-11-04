"""Lot 88 (FR + PT) — DPGF réel : les lignes « OPTION » étaient additionnées au total de base.

Constat (production .fr, 04/11, import réel « DPGF HOUILLES-L3.xlsx », lot 3 menuiseries ext.) : 30/30 lignes
chiffrées, total 70 948 € HT — mais la section « 3.2 OPTION : Volets roulants à commande électrique » (10 lignes,
≈ 21 600 €) était comptée EN PLUS des volets manuels de base : les volets étaient payés deux fois.
Correctif : une section dont le titre commence par OPTION / VARIANTE / PSE (prestation supplémentaire éventuelle)
marque ses lignes « option » jusqu'au titre de section suivant ; elles restent chiffrées et visibles (préfixe
« OPTION — »), mais sont exclues du total de base et totalisées à part (options_total_ht, par lot options_ht).
Dans le devis généré, une option apparaît en catégorie « Options » à 0 € avec son montant dans le libellé.
Usage : python3 lots/l88/apply_l88.py <racine /app> <fr|pt>   (idempotent ; ARRÊT si une ancre manque)
"""
import pathlib
import re
import sys

root = pathlib.Path(sys.argv[1])
lang = (sys.argv[2] if len(sys.argv) > 2 else "fr").lower()
fe = root / "backend" / "engines" / "dpgf_engine.py"
fr_ = root / "backend" / "routes" / "dpgf.py"
e = fe.read_text(encoding="utf-8")
r = fr_.read_text(encoding="utf-8")
if "Lot 88" in e and "Lot 88" in r:
    print("déjà appliqué"); print(f"L88 {lang.upper()} OK"); sys.exit(0)
if lang == "pt":
    OPT_LABEL, OPT_CAT = "OPÇÃO (não incluída no total)", "Opções"
    OPT_NOTE = "As linhas «OPÇÃO» são indicadas à parte e não estão incluídas no total."
else:
    OPT_LABEL, OPT_CAT = "OPTION (non incluse au total)", "Options"
    OPT_NOTE = "Les lignes « OPTION » sont indiquées à part et ne sont pas incluses au total."

E = [("        lot = \"\"\n        count = 0\n        pending_desc: list[str] = []\n",
      "        lot = \"\"\n        count = 0\n        pending_desc: list[str] = []\n"
      "        in_option = False  # Lot 88 : section OPTION / VARIANTE / PSE en cours\n"),
     ("            if _is_lot_title(text, qty, pu):\n                lot = text\n                pending_desc = []\n                continue\n",
      "            if _is_lot_title(text, qty, pu):\n"
      "                in_option = _is_option_title88(text)\n"
      "                if not in_option:\n"
      "                    lot = text\n"
      "                pending_desc = []\n"
      "                continue\n"),
     ("            if qty is None and not unit and pu is None:\n                pending_desc.append(text)          # ligne de descriptif libre\n",
      "            if qty is None and not unit and pu is None:\n"
      "                if _is_option_title88(text):\n"
      "                    in_option = True\n"
      "                elif len(text) <= 90 and not text.rstrip().endswith(\".\"):\n"
      "                    in_option = False  # nouveau titre de section : fin de l'option\n"
      "                pending_desc.append(text)          # ligne de descriptif libre\n"),
     ('                "excluded": False, "exclusion_reason": "",\n',
      '                "excluded": False, "exclusion_reason": "", "option": in_option,\n'),
     ("            rows.append({\n                \"line_id\": f\"l{len(rows) + 1}\",\n",
      "            if in_option and not fold(text).startswith(\"option\"):\n"
      "                text = \"OPTION — \" + text\n"
      "            rows.append({\n                \"line_id\": f\"l{len(rows) + 1}\",\n"),
     ("def parse_workbook(raw: bytes) -> dict:\n",
      "_OPTION_RE88 = re.compile(r\"^\\s*(\\d+(\\.\\d+)*\\s*[-—:.]?\\s*)?(option|variante|pse\\b|prestation suppl|opcao|opção)\", re.I)\n\n\n"
      "def _is_option_title88(text: str) -> bool:\n"
      "    \"\"\"Lot 88 : titre de section d'option (« OPTION : … », « Variante … », « PSE … »).\"\"\"\n"
      "    return bool(_OPTION_RE88.match(fold(text)) or _OPTION_RE88.match(text or \"\"))\n\n\n"
      "def parse_workbook(raw: bytes) -> dict:\n"),
     ("    by_lot: dict[str, dict] = {}\n    total = 0.0\n    priced = 0\n",
      "    by_lot: dict[str, dict] = {}\n    total = 0.0\n    priced = 0\n    options_total = 0.0  # Lot 88\n"),
     ("        elif r.get(\"total\"):\n            slot[\"total_ht\"] = round(slot[\"total_ht\"] + r[\"total\"], 2)\n",
      "        elif r.get(\"total\") and r.get(\"option\"):  # Lot 88 : option chiffrée, hors total de base\n"
      "            slot[\"options_ht\"] = round(slot.get(\"options_ht\", 0.0) + r[\"total\"], 2)\n"
      "            options_total = round(options_total + r[\"total\"], 2)\n"
      "        elif r.get(\"total\"):\n            slot[\"total_ht\"] = round(slot[\"total_ht\"] + r[\"total\"], 2)\n"),
     ('    return {"lots": list(by_lot.values()), "grand_total_ht": round(total, 2), "priced": priced}\n',
      '    return {"lots": list(by_lot.values()), "grand_total_ht": round(total, 2), "priced": priced,\n'
      '            "options_total_ht": round(options_total, 2)}\n')]
R = [("        if x.get(\"pu\") is None:\n            continue\n        lines.append({\n",
      "        if x.get(\"pu\") is None:\n            continue\n"
      "        if x.get(\"option\"):  # Lot 88 : option affichée à part, jamais additionnée au total du devis\n"
      "            amount = f\"{(x.get('total') or 0):,.2f} € HT\".replace(\",\", \" \")\n"
      f"            lines.append({{\"designation\": f\"{OPT_LABEL} — {{x['designation'][:240]}} — {{amount}}\",\n"
      "                          \"description\": (desc or \"\")[:2000], \"unit\": x.get(\"unit\") or \"u\",\n"
      "                          \"qty\": x.get(\"qty\") if x.get(\"qty\") is not None else 1, \"unit_price_ht\": 0,\n"
      f"                          \"vat_rate\": body.vat_rate, \"category\": \"{OPT_CAT}\"}})\n"
      "            continue\n"
      "        lines.append({\n")]
NOTE_A = "    if any(x.get(\"excluded\") for x in rows):\n"
R.append((NOTE_A, "    if any(x.get(\"option\") and x.get(\"pu\") is not None for x in rows):  # Lot 88\n"
                  f"        notes.append({OPT_NOTE!r})\n" + NOTE_A))
for s, reps, name in ((e, E, "dpgf_engine"), (r, R, "routes/dpgf")):
    for a, _ in reps:
        if s.count(a) != 1:
            print(f"ANCRE {name} introuvable — ARRÊT, rien écrit:", a.strip()[:70]); sys.exit(1)
for a, b in E:
    e = e.replace(a, b)
for a, b in R:
    r = r.replace(a, b)
if "\nimport re\n" not in e:
    print("import re absent de dpgf_engine — ARRÊT"); sys.exit(1)
fe.write_text(e, encoding="utf-8")
fr_.write_text(r, encoding="utf-8")
(root / "backend" / "tests" / "test_l88.py").write_bytes((pathlib.Path(__file__).resolve().parent / "tests" / "test_l88.py").read_bytes())
print("ok backend/engines/dpgf_engine.py + routes/dpgf.py + backend/tests/test_l88.py")
print(f"L88 {lang.upper()} OK")
