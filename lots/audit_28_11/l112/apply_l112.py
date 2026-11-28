"""Lot 112 (FR + PT) — audit de nuit du 28/11/2026, suite 3.

 1. Charge serveur : chaque onglet ouvert interrogeait /api/agents/active toutes les 2,5 s et
    /api/pc/study-jobs toutes les 4 s, même onglet caché et sans aucune tâche (≈ 0,9 requête/s/onglet).
    Désormais : rien quand l'onglet est caché ; rythme ÷4 (agents) / ÷3 (études) tant qu'aucune tâche ne tourne ;
    rythme normal dès qu'une tâche est active.
 2. Tableau de bord : « 1 mes projets · 73,2 m² » → « 1 projet · 73,2 m² » (singulier/pluriel, 6 langues).
 3. Ossature LSF (.fr) : clés internes portugaises dans le tableau de vérification (« barra », « flecha_mm »…)
    → libellés français.

Usage : python3 lots/l112/apply_l112.py <racine /app> <fr|pt>   (idempotent, marqueur CP-AUDIT-NUIT-4)
"""
import pathlib
import sys

root = pathlib.Path(sys.argv[1])
site = sys.argv[2] if len(sys.argv) > 2 else "fr"
assert site in ("fr", "pt")
MARK = "CP-AUDIT-NUIT-4"
report = []


def replace(name, rel, pairs):
    """pairs = [(ancien, nouveau), …] appliqués ensemble (tout ou rien) sur le même fichier."""
    p = root / rel
    if not p.exists():
        return report.append(f"ABSENT    {name}")
    txt = p.read_text(encoding="utf-8")
    if MARK in txt:
        return report.append(f"DÉJÀ      {name}")
    for old, _ in pairs:
        if txt.count(old) != 1:
            return report.append(("IGNORÉ    " if old not in txt else "AMBIGU    ") + name)
    for old, new in pairs:
        txt = txt.replace(old, new)
    p.write_text(txt, encoding="utf-8")
    report.append(f"OK        {name}")


replace("1a Indicateur agents : moins de requêtes", "frontend/src/components/AgentsRunning.jsx", [
    ("    const poll = async () => {\n      if (polling || stopped) return;\n",
     f"    let tick = 0;  // {MARK} : onglet caché → rien ; aucune tâche → 1 sondage sur 4\n"
     "    const poll = async (force) => {\n      if (polling || stopped) return;\n"
     "      if (force !== true) { if (document.hidden) return; tick += 1; if (!prev.current.size && tick % 4) return; }\n"),
    ("    poll();\n    timer.current = setInterval(poll, POLL_MS);", "    poll(true);\n    timer.current = setInterval(poll, POLL_MS);"),
])
replace("1b Indicateur études : moins de requêtes", "frontend/src/components/StudyRunning.jsx", [
    ("    const poll=async()=>{\n      if(busy) return; busy=true;",
     f"    let tick=0;  // {MARK} : onglet caché → rien ; aucune étude → 1 sondage sur 3\n"
     "    const poll=async(force)=>{\n      if(busy) return;\n"
     "      if(force!==true){ if(document.hidden) return; tick+=1; if(!seen.current.size && tick%3) return; }\n      busy=true;"),
    ("    poll();const timer=setInterval(poll,4000);", "    poll(true);const timer=setInterval(poll,4000);"),
])
replace("2 Tableau de bord : « 1 projet »", "frontend/src/pages/Dashboard.jsx", [
    ('`${num(projects.length)} ${t("dash.stat_projects").toLowerCase()} · ${num(totalSurface, 1)} m²`',
     '`${num(projects.length)} ${(({ fr: ["projet", "projets"], en: ["project", "projects"], pt: ["projeto", "projetos"], '
     'es: ["proyecto", "proyectos"], it: ["progetto", "progetti"], de: ["Projekt", "Projekte"] })[lang] || [t("dash.stat_projects").toLowerCase(), '
     f't("dash.stat_projects").toLowerCase()])[projects.length > 1 ? 1 : 0]}} · ${{num(totalSurface, 1)}} m²` /* {MARK} */'),
])
if site == "fr":
    replace("3 LSF : libellés de vérification en français", "frontend/src/pages/LsfStudies.jsx", [
        ('const kv = (o) => Object.entries(o || {}).filter(([, x]) => x != null && typeof x !== "object").map(([k, x]) => `${k} ${typeof x === "number" ? fmt(x, 2) : x}`).join(" · ");',
         'const kv = (o) => Object.entries(o || {}).filter(([, x]) => x != null && typeof x !== "object").map(([k, x]) => `${LSF_KEYS_FR[k] || k} ${typeof x === "number" ? fmt(x, 2) : x}`).join(" · ");'),
        ("const CAMPOS = [",
         f"// {MARK} : clés internes du moteur (portugais) → libellés français\n"
         'const LSF_KEYS_FR = { barra: "barre", flecha_mm: "flèche_mm", flecha_total_mm: "flèche_totale_mm", flecha_Q_mm: "flèche_Q_mm", '
         'limite_flecha_mm: "limite_flèche_mm", limite_total_mm: "limite_totale_mm", limite_Q_mm: "limite_Q_mm", '
         'levantamento_kN_m: "soulèvement_kN_m", interacao: "interaction", comprimento_contraventado_m: "longueur_contreventée_m", '
         'F_ancoragem_kN: "F_ancrage_kN", passo_m: "entraxe_m", rho_alma: "rho_âme", governante: "dimensionnant", valor: "valeur" };\n'
         "const CAMPOS = ["),
    ])
else:
    report.append("N/A       3 LSF (site .pt)")

print(f"Lot 112 ({site}) — {MARK}")
print("\n".join(report))
sys.exit(1 if any(r.startswith("AMBIGU") for r in report) else 0)
