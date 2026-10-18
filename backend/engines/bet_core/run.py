"""Ligne de commande : python -m engines.bet_core.run <case.json> <out_dir> [lang] [stem]

Exemple : python -m engines.bet_core.run engines/bet_core/cases/la_courneuve.json /tmp/out
"""
import json
import sys
from pathlib import Path

from . import pipeline


def main(case: str, out: str, lang: str | None = None, stem: str | None = None, date: str | None = None) -> int:
    raw = json.loads(Path(case).read_text(encoding="utf-8"))
    if stem is None and Path(case).stem == "la_courneuve":
        stem = "La_Courneuve"
    res = pipeline.run(raw, out, date=date, lang=lang, stem=stem)
    if res["status"] == "MODELE_INVALIDE":
        print("ARRÊT : modèle invalide", json.dumps(res["anomalies"], ensure_ascii=False, indent=1))
        return 2
    print(json.dumps({k: res[k] for k in ("status", "blocking", "lang", "devis_ht", "devis_ttc")} | {"sheets": len(res["sheets"])}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main(*sys.argv[1:5]))
