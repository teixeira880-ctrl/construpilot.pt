"""Branche bet_frame dans bet_core (idempotent). Usage : cd backend && python -m engines.bet_frame.install_hooks [--check]

Modifications ancrées (échoue sans rien écrire si une ancre manque) :
1. bet_core/assistant_tool.py : _work() délègue au moteur ossature quand le bâtiment n'est pas une maison ;
   description de generate_full_bet_study élargie ; consignes complémentaires de l'Assistant.
2. bet_core/pipeline.py : render_lots() accepte un relevé d'ossature (plans de lots depuis une étude d'immeuble).
"""
from __future__ import annotations

import sys
from pathlib import Path

BASE = Path(__file__).resolve().parents[1] / "bet_core"
MARK = "bet_frame"

EDITS = {
    "assistant_tool.py": [
        ("    try:\n        key = docs_hash(docs, hypotheses, country, decide_alone)\n",
         "    try:\n"
         "        from engines.bet_frame import hook as _frame_hook       # bet_frame : immeubles, bureaux, parkings, ERP (ossature BA)\n"
         "        if await _frame_hook.maybe_handle(db, job_id, uid, cid, request_id, docs, hypotheses, country, step=step, store=_store,\n"
         "                                          llm=llm, branding=branding, decide_alone=decide_alone):\n"
         "            return\n"
         "        key = docs_hash(docs, hypotheses, country, decide_alone)\n"),
        ("\"ÉTUDE BET COMPLÈTE d'une maison individuelle à partir du PC / plans d'architecte (PDF joints) et de l'étude de sol : \"",
         "\"ÉTUDE BET COMPLÈTE d'un bâtiment — maison individuelle OU bâtiment à ossature béton armé (immeuble collectif, bureaux, \"\n"
         "                     \"commerce, parking, bâtiment d'activité, équipement public ; type détecté sur les plans) — à partir des plans \"\n"
         "                     \"d'architecte (PDF joints) et de l'étude de sol : \""),
        ("\n\nMIME = {",
         "\nfrom engines.bet_frame.hook import INSTRUCTIONS_EXTRA as _FRAME_INSTRUCTIONS  # bet_frame\nINSTRUCTIONS += _FRAME_INSTRUCTIONS\n\nMIME = {"),
    ],
    "pipeline.py": [
        ("    out = Path(out)\n    m, anomalies = validate(raw)\n    blocking = [a for a in anomalies if a.get(\"level\") == checks.BLOCK]\n    if m is None or blocking:\n        return {\"ok\": False, \"anomalies\": blocking or anomalies}\n",
         "    if (raw or {}).get(\"kind\") == \"frame\":          # bet_frame : relevé d'un bâtiment à ossature\n"
         "        from engines.bet_frame.pipeline import render_lots as _frame_lots\n"
         "        return _frame_lots(raw, lots, out, date, lang, branding)\n"
         "    out = Path(out)\n    m, anomalies = validate(raw)\n    blocking = [a for a in anomalies if a.get(\"level\") == checks.BLOCK]\n    if m is None or blocking:\n        return {\"ok\": False, \"anomalies\": blocking or anomalies}\n"),
    ],
}


def main(check_only: bool = False) -> int:
    plan = {}
    for fname, edits in EDITS.items():
        p = BASE / fname
        s = p.read_text(encoding="utf-8")
        for old, new in edits:
            if new in s:
                continue
            n = s.count(old)
            if n != 1:
                print(f"ANCRE {'ABSENTE' if n == 0 else 'MULTIPLE'} dans {fname} : {old[:70]!r}")
                return 1
            s = s.replace(old, new)
        plan[p] = s
    if check_only:
        print("ancres OK")
        return 0
    for p, s in plan.items():
        p.write_text(s, encoding="utf-8")
    print("hooks installés :", ", ".join(x.name for x in plan))
    return 0


if __name__ == "__main__":
    sys.exit(main("--check" in sys.argv))
