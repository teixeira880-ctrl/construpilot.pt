"""Lot 109 (FR + PT) — audit de nuit du 28/11/2026 : tout le site parcouru comme particulier, ingénieur,
architecte, petite et grande entreprise. Corrections des erreurs constatées en production (construpilot.fr).

 1. /bim plantait (« atelierId is not defined ») : la variable n'était plus déclarée dans BimViewer.jsx.
 2. GET /api/takeoffs renvoyait 30 Mo (vecteurs de chaque page) à chaque ouverture de l'Assistant, des études,
    du BIM… → 6 s d'attente et serveur saturé. La liste n'envoie plus que le résumé (vecteurs/textes exclus ;
    le plan complet reste chargé par GET /api/takeoffs/{id}).
 3. Détection automatique des pièces : un plan de 2 pièces donnait « 30 pièces » (vide entre les deux traits
    d'un mur, lettres des textes). Les faux contours (< 0,5 m² ou largeur moyenne < 30 cm) sont écartés.
 4. Assistant : un ancien n° de conversation (404) restait en mémoire et le champ de saisie était désactivé
    pendant son chargement → des lettres/chiffres tapés étaient perdus (« 5,20 m » devenait « 5,0 m »).
 5. Barre « Décrivez… / Générer » débordant de sa colonne (escaliers, études) : largeur contrainte.
 6. Escalier droit : quand la configuration idéale ne rentre pas dans le reculement, recherche d'une
    configuration compacte conforme (h ≤ 195 mm, g ≥ 220 mm, Blondel 580-660, pente ≤ 40°) au lieu de
    « Non réalisable » (ex. 2,80 m dans 3,50 m → 15 hauteurs de 186,7 mm, giron 250 mm). Échappée non
    calculée : « — » au lieu de « -1 mm » (écran et PDF).
 7. Après chaque déploiement, « Loading chunk … failed » (erreurs client) : rechargement automatique unique.
 8. Visiter /portugal sur le .fr passait TOUTE l'interface (et la langue des e-mails du compte) en portugais
    de façon permanente : la page passe en PT sans l'enregistrer et rend la langue précédente en sortant.
 9. Libellés : « Facture importée » (et non « importé ») ; statut urbanisme traduit (« exported » → « Exporté »).
10. Économies : nombres au format français (32,1 % ; 79,6× ; 5 567 €).

Usage : python3 lots/l109/apply_l109.py <racine /app> <fr|pt>
Idempotent (marqueur CP-AUDIT-NUIT). Chaque correctif est indépendant : si son ancre n'existe pas sur ce
serveur, il est signalé « ignoré » et rien n'est modifié dans ce fichier.
"""
import pathlib
import re
import sys

root = pathlib.Path(sys.argv[1])
site = sys.argv[2] if len(sys.argv) > 2 else "fr"
assert site in ("fr", "pt")
MARK = "CP-AUDIT-NUIT"
report = []


def read(rel):
    p = root / rel
    return p, (p.read_text(encoding="utf-8") if p.exists() else None)


def done(name, status):
    report.append(f"{status:9} {name}")


def replace(name, rel, old, new, count=1):
    p, txt = read(rel)
    if txt is None:
        return done(name, "ABSENT")
    if new in txt:
        return done(name, "DÉJÀ")
    if old not in txt:
        return done(name, "IGNORÉ")
    if count == 1 and txt.count(old) != 1:
        return done(name, "AMBIGU")
    p.write_text(txt.replace(old, new), encoding="utf-8")
    done(name, "OK")


def regex(name, rel, pattern, repl, already):
    p, txt = read(rel)
    if txt is None:
        return done(name, "ABSENT")
    if already in txt:
        return done(name, "DÉJÀ")
    new, n = re.subn(pattern, repl, txt, count=1, flags=re.S)
    if n != 1:
        return done(name, "IGNORÉ")
    p.write_text(new, encoding="utf-8")
    done(name, "OK")


# ---------------------------------------------------------------- 1. BimViewer : atelierId déclaré
def fix_bim():
    rel = "frontend/src/pages/BimViewer.jsx"
    p, txt = read(rel)
    if txt is None:
        return done("1 BimViewer atelierId", "ABSENT")
    if re.search(r"\b(const|let|var)\s+atelierId\b", txt) or "atelierId" not in txt:
        return done("1 BimViewer atelierId", "DÉJÀ")
    m = re.search(r"\n(\s*)const planId = (\w+)\.get\(\"plan\"\);\n", txt)
    if m:
        ins = f'{m.group(0)}{m.group(1)}const atelierId = {m.group(2)}.get("atelier");   // {MARK} : projet de l\'Atelier Architecte\n'
        txt = txt.replace(m.group(0), ins, 1)
    else:
        m = re.search(r"export default function BimViewer\([^)]*\)\s*\{\n", txt)
        if not m:
            return done("1 BimViewer atelierId", "IGNORÉ")
        ins = m.group(0) + f'  const atelierId = new URLSearchParams(window.location.search).get("atelier");   // {MARK}\n'
        txt = txt.replace(m.group(0), ins, 1)
    p.write_text(txt, encoding="utf-8")
    done("1 BimViewer atelierId", "OK")


fix_bim()

# ---------------------------------------------------------------- 2. Liste des plans allégée
LIGHT = ('{"_id": 0, "pages.image_png_b64": 0, "pages.vectors": 0, "pages.text_blocks": 0,\n'
         f'         "pages.pdf_elements": 0, "pages.pdf_auto_spans": 0}}  # {MARK} : liste légère (30 Mo → < 1 Mo)')
regex("2 GET /takeoffs léger", "backend/routes/plans_crud.py",
      r'(async def list_plans\(.*?\.find\(\s*\{"user_id": user\["user_id"\], "trashed_at": \{"\$exists": False\}\},\s*)'
      r'\{"_id": 0, "pages\.image_png_b64": 0\}',
      lambda m: m.group(1) + LIGHT, "liste légère (30 Mo")

# ---------------------------------------------------------------- 3. Faux contours de pièces
SLIVER = (
    '                r["perimeter_m"] = round(G.polygon_perimeter_m(r["points"], ppm), 3)\n'
    f'        # {MARK} : écarter les faux contours (vide entre les deux traits d\'un mur, lettres des textes).\n'
    '        kept = []\n'
    '        for r in result.get("rooms", []):\n'
    '            s, per = r.get("surface_m2"), r.get("perimeter_m")\n'
    '            if s is not None and per and (s < 0.5 or 2 * s / per < 0.3):\n'
    '                continue\n'
    '            kept.append(r)\n'
    '        dropped = len(result.get("rooms", [])) - len(kept)\n'
    '        if dropped:\n'
    '            result["rooms"] = kept\n'
    '            result["filtered_slivers"] = dropped\n'
    '    return result\n'
)
regex("3 pièces : faux contours", "backend/routes/plans_analysis.py",
      r'(async def detect_all_rooms_route\(.*?)                r\["perimeter_m"\] = round\(G\.polygon_perimeter_m\(r\["points"\], ppm\), 3\)\n    return result\n',
      lambda m: m.group(1) + SLIVER, "écarter les faux contours")

# ---------------------------------------------------------------- 4. Assistant : saisie jamais perdue
A = "frontend/src/pages/Assistant.jsx"
replace("4a Assistant : champ actif pendant le chargement", A,
        "<textarea ref={textareaRef} disabled={loadingConversation} ",
        "<textarea ref={textareaRef} aria-busy={loadingConversation} ")
replace("4b Assistant : pas d'envoi pendant le chargement", A,
        "if ((!text.trim() && !pending.length && !dossierImport.ids.length) || sendLock.current",
        "if (loadingConversation || (!text.trim() && !pending.length && !dossierImport.ids.length) || sendLock.current")
replace("4c Assistant : conversation supprimée oubliée", A,
        ".catch(() => { if (active) setHistoryError(true); })",
        ".catch((err) => { if (!active) return; if (err?.response?.status === 404) { "
        f"/* {MARK} : conversation supprimée → on l'oublie */ try {{ localStorage.removeItem(`assistant-last-${{user?.user_id}}`); }} catch {{ /* */ }} return; }} "
        "setHistoryError(true); })")

# ---------------------------------------------------------------- 5. Barre IA contenue dans sa colonne
replace("5 Barre IA sans débordement", "frontend/src/components/AIPromptBar.jsx",
        '<div className="w-full grid gap-2" data-testid="ai-prompt-bar">',
        '<div className="w-full min-w-0 grid grid-cols-[minmax(0,1fr)] gap-2" data-testid="ai-prompt-bar">')

# ---------------------------------------------------------------- 6. Escalier droit compact + échappée
COMPACT = (
    "    blondel = blondel_value(h_mm, g_mm)\n"
    f"    # {MARK} : si la configuration idéale ne rentre pas dans le reculement, chercher une configuration\n"
    "    # compacte encore conforme (h ≤ max acceptable, g ≥ minimum absolu, Blondel acceptable, pente ≤ max).\n"
    "    _avail = getattr(inp, \"available_length_mm\", None) or 0\n"
    "    if _avail and num_treads * g_mm > _avail:\n"
    "        _best = None\n"
    "        _n0 = max(2, int(math.ceil(inp.floor_height_mm / norms.riser_height_acceptable_max_mm)))\n"
    "        for _n in range(_n0, n_steps + 1):\n"
    "            _h = inp.floor_height_mm / _n\n"
    "            if not (norms.riser_height_acceptable_min_mm <= _h <= norms.riser_height_acceptable_max_mm):\n"
    "                continue\n"
    "            _g = math.floor(min(optimal_giron_mm(_h, norms), _avail / (_n - 1)))\n"
    "            _b = blondel_value(_h, _g)\n"
    "            if _g < norms.tread_depth_hard_min_mm or not (norms.blondel_acceptable_min_mm <= _b <= norms.blondel_acceptable_max_mm):\n"
    "                continue\n"
    "            if math.degrees(math.atan2(inp.floor_height_mm, (_n - 1) * _g)) > norms.slope_hard_max_deg:\n"
    "                continue\n"
    "            _score = abs(_b - 630.0) + 2.0 * abs(_h - 170.0)\n"
    "            if _best is None or _score < _best[0]:\n"
    "                _best = (_score, _n, _h, float(_g))\n"
    "        if _best:\n"
    "            _, n_steps, h_mm, g_mm = _best\n"
    "            num_treads = n_steps - 1\n"
    "            in_optimal = norms.riser_height_optimal_min_mm <= h_mm <= norms.riser_height_optimal_max_mm\n"
    "            blondel = blondel_value(h_mm, g_mm)\n"
    "            alerts_all.append(Alert(level=\"orange\", code=\"COMPACT_CONFIG\", message_fr=(\n"
    "                f\"Configuration compacte pour tenir dans {_avail:.0f} mm : {n_steps} hauteurs de {h_mm:.1f} mm, \"\n"
    "                f\"giron {g_mm:.0f} mm (Blondel {blondel:.0f} mm). Conforme mais moins confortable que l'idéal.\"),\n"
    "                metric=\"stair_run_mm\", value=num_treads * g_mm, threshold=_avail))\n"
)
regex("6a Escalier droit compact", "backend/stair_engine/straight.py",
      r"(def compute_straight\(.*?g_mm = optimal_giron_mm\(h_mm, norms\)\n)    blondel = blondel_value\(h_mm, g_mm\)\n",
      lambda m: m.group(1) + COMPACT, "COMPACT_CONFIG")
replace("6b Échappée « — » (écran)", "frontend/src/pages/StairCalculator.jsx",
        'const mm = (v) => (v == null ? "—" : `${Math.round(v)} mm`);',
        'const mm = (v) => (v == null || v < 0 ? "—" : `${Math.round(v)} mm`);  // ' + MARK + " : -1 = non calculé")
replace("6c Échappée « — » (PDF)", "backend/stair_engine/pdf_dossier.py",
        """["Échappée", f"{stair_result.get('headroom_mm', '—')} mm"],""",
        """["Échappée", (f"{stair_result.get('headroom_mm')} mm" if (stair_result.get('headroom_mm') or -1) >= 0 """
        """else "non vérifiée (trémie non renseignée)")],  # """ + MARK)

replace("6d test CP-10 aligné (2,70 m dans 4,00 m devient réalisable en 15 × 180 mm)", "backend/tests/test_stairs_cp10.py",
        """    r = compute_straight(p)
    assert r.is_buildable is False
    assert any(a.code == "STAIR_RUN_TOO_LONG" for a in r.alerts)""",
        """    r = compute_straight(p)
    # """ + MARK + """ : l'ancienne longueur (4000) rentre maintenant en configuration compacte conforme.
    assert r.is_buildable is True
    assert r.stair_run_mm <= 4000
    assert any(a.code == "COMPACT_CONFIG" for a in r.alerts)""")

# ---------------------------------------------------------------- 7. Rechargement après déploiement
regex("7 Rechargement unique si morceau JS absent", "frontend/src/components/ErrorBoundary.jsx",
      r"(  componentDidCatch\(error, info\) \{\n)",
      lambda m: m.group(1) + (
          f"    // {MARK} : après un déploiement les anciens fichiers JS n'existent plus → recharger une seule fois.\n"
          "    try {\n"
          "      const m = String(error?.message || \"\");\n"
          "      if (error?.name === \"ChunkLoadError\" || /Loading (CSS )?chunk [\\w-]+ failed|dynamically imported module/i.test(m)) {\n"
          "        const last = Number(sessionStorage.getItem(\"cp_chunk_reload\") || 0);\n"
          "        if (Date.now() - last > 60000) { sessionStorage.setItem(\"cp_chunk_reload\", String(Date.now())); window.location.reload(); return; }\n"
          "      }\n"
          "    } catch { /* navigateur restreint */ }\n"),
      "cp_chunk_reload")

# ---------------------------------------------------------------- 8. /portugal ne change plus la langue du compte
I18N = "frontend/src/context/I18nContext.jsx"
regex("8a setLang(l, {persist:false})", I18N,
      r"  const setLang = \(l\) => \{\n    setLangState\(l\);\n    localStorage\.setItem\(STORAGE_KEY, l\);\n    applyDir\(l\);\n"
      r"(    // Sync best-effort.*?\n)    if \(localStorage\.getItem\(\"construpilot_session\"\) === \"1\"\) \{",
      lambda m: ("  const setLang = (l, opts = {}) => {\n    setLangState(l);\n"
                 f"    const persist = opts.persist !== false;  // {MARK} : une page vitrine peut changer la langue sans l'enregistrer\n"
                 "    if (persist) localStorage.setItem(STORAGE_KEY, l);\n    applyDir(l);\n" + m.group(1) +
                 "    if (persist && localStorage.getItem(\"construpilot_session\") === \"1\") {"),
      "opts.persist !== false")
replace("8b /portugal sans enregistrer la langue", "frontend/src/pages/LandingPortugal.jsx",
        '  const { setLang } = useI18n();\n  useEffect(() => { setLang("pt"); /* landing sempre em PT-PT */ /* eslint-disable-next-line */ }, []);',
        '  const { lang, setLang } = useI18n();\n'
        f'  // {MARK} : landing em PT-PT sem alterar a língua guardada do utilizador ; repõe a anterior à saída.\n'
        '  useEffect(() => { const prev = lang; setLang("pt", { persist: false }); return () => setLang(prev, { persist: false }); /* eslint-disable-next-line */ }, []);')

# ---------------------------------------------------------------- 9. Libellés
replace("9a « Facture importée »", "backend/routes/documents.py",
        '"title": f"{label} importé — {name[:60]}",',
        '"title": f"{label} " + ("importée" if dtype == "invoice" else "importé") + f" — {name[:60]}",  # ' + MARK)
replace("9b Statut urbanisme traduit", "frontend/src/pages/Urbanisme.jsx",
        '{d.verdict ? `Formalité : ${d.verdict}` : ""} · {d.status}',
        '{d.verdict ? `Formalité : ${d.verdict}` : ""} · {({ draft: "Brouillon", initiated: "Démarré", pending: "En attente", '
        'complete: "Complet", exported: "Exporté" })[d.status] || d.status}')

# ---------------------------------------------------------------- 10. Économies au format français
S = "frontend/src/components/SavingsCard.jsx"
replace("10a % au format local", S, "soit ~{data.pct_of_project} % du budget total du projet",
        "soit ~{Number(data.pct_of_project || 0).toLocaleString(document.documentElement.lang || \"fr\")} % du budget total du projet")
replace("10b ROI au format local", S, "ROI {data.roi_multiplier}× le Project Pass",
        "ROI {Number(data.roi_multiplier || 0).toLocaleString(document.documentElement.lang || \"fr\")}× le Project Pass")
replace("10c base matériaux avec séparateur", "backend/engines/savings.py",
        '"basis": f"{pct*100:.0f} % sur {materials:.0f} € de matériaux",',
        '"basis": f"{pct*100:.0f} % sur {materials:,.0f} € de matériaux".replace(",", "\\u202f"),')

print(f"Lot 109 ({site}) — {MARK}")
print("\n".join(report))
bad = [r for r in report if r.startswith("AMBIGU")]
sys.exit(1 if bad else 0)
