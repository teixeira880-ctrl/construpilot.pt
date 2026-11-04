"""Lot 90 (FR + PT, frontend) — Plans & métrés : plan en grand, outils au survol.

Demande du fondateur (04/11, 21 h 45) : « impossible de travailler manuellement avec un écran aussi petit ; le plan doit
être en pleine page, le plus grand écran possible, et les fonctions doivent apparaître au passage de la souris ».
Constat : le canevas faisait 500 px de haut (PlanCanvas prend la hauteur du parent, qui n'en avait pas), coincé entre la
colonne des pages et le panneau de droite, sous une barre d'outils de 3-4 lignes.
Correctif (mode « plan en grand », activé par défaut, mémorisé dans le navigateur, bouton pour revenir à l'ancien
affichage) :
- le plan occupe toute la largeur et la hauteur de l'écran (100vh − en-tête) ; pages et panneau Métré passent dessous ;
- la barre d'outils flotte au-dessus du plan et n'apparaît qu'au survol du bord supérieur (ou au clavier) ; une
  languette discrète indique où la trouver ; sur écran tactile (sans souris) elle reste visible ;
- en « Plein écran », même barre flottante et plan sur toute la hauteur.
Usage : python3 lots/l90/apply_l90.py <racine /app> <fr|pt>   (idempotent ; ARRÊT si une ancre manque)
"""
import pathlib
import sys

root = pathlib.Path(sys.argv[1])
lang = (sys.argv[2] if len(sys.argv) > 2 else "fr").lower()
f = root / "frontend" / "src" / "pages" / "PlanTakeoff.jsx"
s = f.read_text(encoding="utf-8")
if "Lot 90" in s:
    print("déjà appliqué"); print(f"L90 {lang.upper()} OK"); sys.exit(0)
T = {"fr": ("Outils — survolez le haut du plan", "Plan en grand", "Affichage classique",
            "Plan en grand : le plan occupe tout l'écran, outils au survol"),
     "pt": ("Ferramentas — passe o rato no topo da planta", "Planta em grande", "Vista clássica",
            "Planta em grande: a planta ocupa o ecrã inteiro, ferramentas ao passar o rato")}[lang]
HINT, WIDE_ON, WIDE_OFF, WIDE_TITLE = T

TOOLBAR_OVERLAY = ("absolute top-0 inset-x-0 z-40 p-2 flex flex-wrap gap-2 rounded-t-md border-b border-border "
                   "bg-background/95 backdrop-blur shadow-lg opacity-0 pointer-events-none transition-opacity duration-150 "
                   "group-hover/tb:opacity-100 group-hover/tb:pointer-events-auto focus-within:opacity-100 "
                   "focus-within:pointer-events-auto [@media(hover:none)]:opacity-100 [@media(hover:none)]:pointer-events-auto")
R = [
    ("  const [fullscreen, setFullscreen] = useState(false);\n",
     "  const [fullscreen, setFullscreen] = useState(false);\n"
     "  // Lot 90 : plan en grand (par défaut), outils au survol — choix mémorisé dans le navigateur\n"
     "  const [planWide, setPlanWide] = useState(() => {\n"
     "    try { return localStorage.getItem(\"cp_plan_wide\") !== \"0\"; } catch { return true; }\n"
     "  });\n"
     "  useEffect(() => {\n"
     "    try { localStorage.setItem(\"cp_plan_wide\", planWide ? \"1\" : \"0\"); } catch { /* stockage indisponible */ }\n"
     "    const t = setTimeout(() => window.dispatchEvent(new Event(\"resize\")), 60);\n"
     "    return () => clearTimeout(t);\n"
     "  }, [planWide]);\n"),
    ('className="grid grid-cols-1 xl:grid-cols-[minmax(0,1fr)_320px] 2xl:grid-cols-[180px_minmax(0,1fr)_320px] gap-4 min-w-0"',
     'className={planWide ? "grid grid-cols-1 gap-4 min-w-0" : "grid grid-cols-1 xl:grid-cols-[minmax(0,1fr)_320px] 2xl:grid-cols-[180px_minmax(0,1fr)_320px] gap-4 min-w-0"}'),
    ('"fixed inset-0 z-[60] p-3 bg-background overflow-auto"',
     '"fixed inset-0 z-[60] p-3 bg-background overflow-auto group/plan"'),
    (': "surface p-3 min-w-0"} data-testid="plan-canvas-surface">',
     ': planWide ? "surface p-2 min-w-0 order-first group/plan" : "surface p-3 min-w-0"} data-testid="plan-canvas-surface">'),
    ('          <div className="flex flex-wrap gap-2 mb-3 pb-3 border-b border-border">\n',
     '          {/* Lot 90 : zone de survol du haut du plan — la barre d\'outils y apparaît */}\n'
     '          <div className={(planWide || fullscreen) ? "relative z-40 group/tb h-0" : "contents"}>\n'
     '          {(planWide || fullscreen) && (\n'
     '            <div className="absolute top-0 inset-x-0 h-4 z-30" aria-hidden="true" />\n'
     '          )}\n'
     '          {(planWide || fullscreen) && (\n'
     '            <div className="absolute top-1 left-1/2 -translate-x-1/2 z-30 px-3 py-0.5 rounded-full text-[11px] '
     'bg-foreground/70 text-background pointer-events-none transition-opacity group-hover/tb:opacity-0 '
     f'[@media(hover:none)]:hidden" data-testid="plan-tools-hint">{HINT}</div>\n'
     '          )}\n'
     f'          <div className={{(planWide || fullscreen) ? "{TOOLBAR_OVERLAY}" : "flex flex-wrap gap-2 mb-3 pb-3 border-b border-border"}}\n'
     '               data-testid="plan-toolbar">\n'),
    ('          {/* CANVAS */}\n          <div className={fullscreen ? "relative h-[calc(100vh-92px)]" : "relative"}>\n',
     '          </div>{/* Lot 90 : fin zone de survol */}\n'
     '          {/* CANVAS */}\n'
     '          <div className={fullscreen ? "relative h-[calc(100vh-24px)]" : planWide ? "relative h-[calc(100vh-96px)] min-h-[520px]" : "relative"}>\n'),
    ("            {/* P1 — Plein écran */}\n",
     "            {/* Lot 90 : bascule plan en grand / affichage classique */}\n"
     "            <Button size=\"sm\" variant={planWide ? \"default\" : \"outline\"} onClick={() => setPlanWide((v) => !v)}\n"
     "                    data-testid=\"tool-plan-wide\" className=\"rounded-sm gap-1 h-8\"\n"
     f"                    title=\"{WIDE_TITLE}\">\n"
     f"              {{planWide ? \"{WIDE_OFF}\" : \"{WIDE_ON}\"}}\n"
     "            </Button>\n"
     "            {/* P1 — Plein écran */}\n"),
]
# Ancre de fin de barre d'outils : la div qui précède « {/* CANVAS */} » doit se fermer avant notre fermeture de zone.
for a, _ in R:
    if s.count(a) != 1:
        print("ANCRE introuvable — ARRÊT, rien écrit:", a.strip()[:80]); sys.exit(1)
for a, b in R:
    s = s.replace(a, b)
f.write_text(s, encoding="utf-8")
print("ok frontend/src/pages/PlanTakeoff.jsx")
print(f"L90 {lang.upper()} OK")
