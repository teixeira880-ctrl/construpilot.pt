"""Lot 110 (FR + PT) — audit de nuit du 28/11/2026, suite.

 1. Étude structure maison : l'avertissement disait toujours « zone de sismicité 1 », même à Nice (zone 4).
    Le message reprend maintenant la zone réelle du projet et dit si les règles parasismiques s'imposent.
 2. Résoudre un problème BTP : un diagnostic a mis 8 min et pouvait rester « en cours » pour toujours
    (aucun délai sur la recherche web ni sur l'IA, tâche perdue au redémarrage du serveur). Délais ajoutés
    (recherche 120 s → on continue sans ; IA 150 s → fournisseur suivant ; total 330 s → erreur claire),
    diagnostic « en cours » depuis plus de 10 min → marqué interrompu avec un message pour relancer.
    Écran : durée annoncée réaliste ; risque traduit (« medium » → « moyen »).
 3. Ossature LSF (.fr) : textes portugais affichés sur le site français (« Calcular a estrutura LSF »,
    « Aço… sobrecarga de piso… neve… vento », « Aplicar e recalcular », « página »).

Usage : python3 lots/l110/apply_l110.py <racine /app> <fr|pt>   (idempotent, marqueur CP-AUDIT-NUIT-2 ;
chaque correctif est indépendant, ancre absente → « IGNORÉ » sans rien modifier).
"""
import pathlib
import re
import sys

root = pathlib.Path(sys.argv[1])
site = sys.argv[2] if len(sys.argv) > 2 else "fr"
assert site in ("fr", "pt")
MARK = "CP-AUDIT-NUIT-2"
report = []


def read(rel):
    p = root / rel
    return p, (p.read_text(encoding="utf-8") if p.exists() else None)


def done(name, status):
    report.append(f"{status:9} {name}")


def replace(name, rel, old, new, all_=False):
    p, txt = read(rel)
    if txt is None:
        return done(name, "ABSENT")
    if new in txt:
        return done(name, "DÉJÀ")
    if old not in txt:
        return done(name, "IGNORÉ")
    if not all_ and txt.count(old) != 1:
        return done(name, "AMBIGU")
    p.write_text(txt.replace(old, new), encoding="utf-8")
    done(name, "OK")


def regex(name, rel, pattern, repl, already):
    p, txt = read(rel)
    if txt is None:
        return done(name, "ABSENT")
    if already in txt:
        return done(name, "DÉJÀ")
    new, n = re.subn(pattern, repl, txt, count=1, flags=re.S | re.M)
    if n != 1:
        return done(name, "IGNORÉ")
    p.write_text(new, encoding="utf-8")
    done(name, "OK")


# ---------------------------------------------------------------- 1. Zone sismique réelle
SEISME = (
    f"    # {MARK} : zone de sismicité du projet (et non « zone 1 » en dur).\n"
    "    _zs = (geo or {}).get(\"seismic_zone\") if isinstance(geo, dict) else None\n"
    "    try:\n"
    "        _zs = int(_zs) if _zs not in (None, \"\") else None\n"
    "    except (TypeError, ValueError):\n"
    "        _zs = None\n"
    "    if _zs is None:\n"
    "        warnings.append(\"Séisme (NF EN 1998-1) NON vérifié — zone de sismicité non renseignée : la vérifier (Géorisques) \"\n"
    "                        \"et appliquer les dispositions constructives correspondantes.\")\n"
    "    elif _zs <= 2:\n"
    "        warnings.append(f\"Séisme (NF EN 1998-1) NON vérifié — zone de sismicité {_zs} : pas d'exigence parasismique pour une \"\n"
    "                        f\"maison (catégorie II) ; règles obligatoires en catégories III/IV\" + (\" (zone 2)\" if _zs == 2 else \"\") + \".\")\n"
    "    else:\n"
    "        warnings.append(f\"Séisme (NF EN 1998-1) NON vérifié — zone de sismicité {_zs} : règles parasismiques OBLIGATOIRES \"\n"
    "                        f\"(NF EN 1998-1 ou guide CP-MI), non couvertes par ce pré-dimensionnement — à faire par le BET structure.\")\n"
)
replace("1 Étude maison : zone sismique réelle", "backend/engines/structuro_maison.py",
        '    warnings.append("Séisme (NF EN 1998-1) NON vérifié — en zone de sismicité 1, vérifier les dispositions constructives.")\n',
        SEISME)

# ---------------------------------------------------------------- 2. Diagnostic BTP : délais
SOL = "backend/btp_solver/solver.py"
regex("2a solver : import asyncio", SOL, r"^import json\n", "import asyncio\nimport json\n", "import asyncio")
regex("2b solver : recherche web ≤ 120 s", SOL,
      r"        research = await pplx\.ask\((.*?)\n        \)\n        research_txt = research\[\"text\"\]\n",
      lambda m: (f"        try:  # {MARK} : la recherche ne bloque jamais le diagnostic\n"
                 f"            research = await asyncio.wait_for(pplx.ask({m.group(1)}\n            ), timeout=120)\n"
                 "        except Exception:\n"
                 "            research = {\"text\": \"\", \"citations\": []}\n"
                 "        research_txt = research[\"text\"]\n"),
      "la recherche ne bloque jamais")
replace("2c solver : IA ≤ 150 s puis fournisseur suivant", SOL,
        "        raw = await chat.send_message(UserMessage(text=context))\n",
        f"        raw = await asyncio.wait_for(chat.send_message(UserMessage(text=context)), timeout=150)  # {MARK}\n",
        all_=True)
RT = "backend/btp_solver/routes.py"
replace("2d diagnostic : total ≤ 330 s", RT,
        "        resp = await solve(description=description, photos_urls=photos_urls, context=context, photo_analysis=photo_analysis)\n",
        "        resp = await asyncio.wait_for(solve(description=description, photos_urls=photos_urls, context=context,\n"
        f"                                            photo_analysis=photo_analysis), timeout=330)  # {MARK}\n")
regex("2e diagnostic resté « en cours » → interrompu", RT,
      r"(async def detail\(problem_id: str, user=Depends\(current_user\)\):\n.*?        raise HTTPException\(404, \"Diagnostic introuvable\"\)\n)    return doc\n",
      lambda m: m.group(1) + (
          f"    if doc.get(\"status\") == \"running\":  # {MARK} : tâche perdue (redémarrage) ou trop longue\n"
          "        try:\n"
          "            started = datetime.fromisoformat(str(doc.get(\"generated_at_iso\")))\n"
          "            if (datetime.now(timezone.utc) - started).total_seconds() > 600:\n"
          "                msg = \"Analyse interrompue (délai dépassé ou serveur redémarré) : relancez le diagnostic.\"\n"
          "                await db.btp_problems.update_one({\"problem_id\": problem_id, \"status\": \"running\"},\n"
          "                                                 {\"$set\": {\"status\": \"error\", \"error\": msg}})\n"
          "                doc[\"status\"], doc[\"error\"] = \"error\", msg\n"
          "        except Exception:  # noqa: BLE001\n"
          "            pass\n"
          "    return doc\n"),
      "tâche perdue (redémarrage)")
BS = "frontend/src/pages/BtpSolver.jsx"
replace("2f durée annoncée réaliste", BS, "Ceci peut prendre 1 à 2 minutes ; vous pouvez rester sur cette page.",
        "Ceci prend en général 2 à 5 minutes ; vous pouvez quitter la page, le diagnostic sera dans l'historique.")
replace("2g risque traduit", BS, '<span className="text-slate-500">Risque :</span> {s.risk}</div>',
        '<span className="text-slate-500">Risque :</span> {({ low: "faible", medium: "moyen", high: "élevé" })[s.risk] || s.risk}</div>')

# ---------------------------------------------------------------- 3. LSF en français sur le .fr
if site == "fr":
    LSF = "frontend/src/pages/LsfStudies.jsx"
    replace("3a LSF « Calculer la structure »", LSF, "/>}Calcular a estrutura LSF</Button>", "/>}Calculer la structure LSF</Button>")
    replace("3b LSF « page »", LSF, ">página {Number(l.page_index) + 1}</span>", ">page {Number(l.page_index) + 1}</span>")
    replace("3c LSF hypothèses en français", LSF,
            "Aço {v.aco?.grau} (fy = {fmt(v.aco?.fy_MPa)} MPa) · sobrecarga de piso {fmt(a.q_piso, 2)} kN/m² · neve s = {fmt(a.s, 2)} kN/m² ·\n"
            "        vento q<sub>p</sub>",
            "Acier {v.aco?.grau} (fy = {fmt(v.aco?.fy_MPa)} MPa) · charge d'exploitation plancher {fmt(a.q_piso, 2)} kN/m² · neige s = {fmt(a.s, 2)} kN/m² ·\n"
            "        vent q<sub>p</sub>")
    replace("3d LSF « Appliquer et recalculer »", LSF, "/>}Aplicar e recalcular</Button>", "/>}Appliquer et recalculer</Button>")
else:
    done("3 LSF (site .pt : textes portugais conservés)", "N/A")

print(f"Lot 110 ({site}) — {MARK}")
print("\n".join(report))
sys.exit(1 if any(r.startswith("AMBIGU") for r in report) else 0)
