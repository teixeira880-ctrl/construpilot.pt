"""Découpe la grande vidéo narrée en clips par fonction clé + génère features.json
(clip, titre, narration, description écrite détaillée, route de la fonctionnalité)."""
import json, subprocess
from pathlib import Path

DEMO = Path("/app/frontend/public/demo")
CLIPS = DEMO / "clips"; CLIPS.mkdir(parents=True, exist_ok=True)
demo = json.loads((DEMO / "demo.json").read_text())
chapters = demo["chapters"]
total = demo["total_duration"]
starts = {c["key"]: c["start"] for c in chapters}
order = [c["key"] for c in chapters]

# fonctions clés + description écrite détaillée + route de la fonctionnalité
KEY = {
 "metre": {"route": "/plan", "desc": "Le métré sur plan est le cœur de ConstruPilot. **À quoi ça sert :** obtenir des quantités exactes (surfaces, périmètres, longueurs) directement depuis un plan PDF ou image, sans ressaisie. **Comment l'utiliser :** importez votre plan, calibrez-le une fois en indiquant une distance connue, puis tracez surfaces, périmètres et distances à la souris ; dessinez les pièces et déduisez automatiquement portes et fenêtres. **Bénéfices :** un métré fiable au centimètre, zéro calcul manuel, aucune erreur d'arrondi, et des quantités prêtes à basculer dans un devis."},
 "estimation": {"route": "/estimation", "desc": "L'estimateur produit un premier chiffrage complet à partir d'une simple description en langage courant. **À quoi ça sert :** donner un ordre de prix crédible en quelques secondes, avant même le métré détaillé. **Comment l'utiliser :** décrivez votre projet (« rénovation appartement 60 m² : peinture, sol, cuisine ») et laissez l'outil détailler les postes. **Bénéfices :** un devis d'approche instantané, poste par poste, pour répondre vite à un prospect."},
 "plans_pro": {"route": "/plans-pro", "desc": "L'analyse de plan Pro détecte automatiquement les éléments du plan. **À quoi ça sert :** accélérer le métré en pré-identifiant pièces, murs et surfaces. **Comment l'utiliser :** importez un plan et laissez l'analyse proposer les zones ; ajustez si besoin. **Bénéfices :** un gain de temps considérable sur les grands projets et une base de métré fiable en un instant."},
 "calculateurs": {"route": "/calculateurs", "desc": "Les calculateurs de matériaux donnent les quantités exactes à commander. **À quoi ça sert :** convertir une surface ou un volume en quantités concrètes (carrelage, peinture, béton, placo…) avec pertes de pose. **Comment l'utiliser :** saisissez vos dimensions et le type d'ouvrage, l'outil calcule quantités, marges et pertes. **Bénéfices :** des commandes justes, moins de gaspillage, pas de rupture en cours de chantier."},
 "escaliers": {"route": "/escaliers", "desc": "Le module de calcul d'escaliers est un moteur déterministe conforme aux normes. **À quoi ça sert :** dimensionner un escalier (droit, quart-tournant, hélicoïdal), vérifier sa faisabilité et quantifier le béton armé. **Comment l'utiliser :** renseignez la hauteur à monter et le reculement disponible, cliquez sur Calculer, puis explorez le résultat, la Vue 3D interactive et le dossier PDF coté. **Bénéfices :** un escalier vérifié DTU 36.3, une vue 3D pour valider avec le client, et un métré béton/coffrage/ferraillage prêt pour le devis."},
 "devis_editeur": {"route": "/devis-editeur", "desc": "L'éditeur de devis compose votre proposition ligne par ligne. **À quoi ça sert :** construire un devis professionnel précis, avec fournitures, main d'œuvre et ouvrages composés. **Comment l'utiliser :** ajoutez vos lignes, saisissez quantités et prix unitaires, choisissez la TVA ; sous-totaux et total se recalculent en temps réel. Générez le PDF en un clic. **Bénéfices :** des calculs toujours justes, une présentation soignée, et un devis envoyé au client en quelques minutes."},
 "factures": {"route": "/factures", "desc": "La facturation transforme un devis signé en facture conforme. **À quoi ça sert :** facturer sans ressaisie, dans le respect de la réglementation (Factur-X). **Comment l'utiliser :** depuis un devis accepté, cliquez sur « Facturer un devis » ; gérez acomptes, situations et facture définitive. **Bénéfices :** une numérotation continue, des factures conformes, et une trésorerie suivie chantier par chantier."},
 "chantiers": {"route": "/chantiers", "desc": "Les dossiers chantier réunissent tout au même endroit. **À quoi ça sert :** centraliser plans, devis, factures et documents de chaque projet. **Comment l'utiliser :** créez un dossier par chantier et rattachez-y automatiquement vos pièces au fil de l'eau. **Bénéfices :** plus rien ne se perd, tout l'historique d'un projet est accessible en un clic."},
 "dpgf": {"route": "/dpgf", "desc": "Le module DPGF transforme le cadre de l'architecte en devis chiffrable. **À quoi ça sert :** répondre à un appel d'offres sans recopier la décomposition de prix. **Comment l'utiliser :** importez le DPGF, l'outil en extrait les postes que vous chiffrez directement. **Bénéfices :** un gain de temps énorme sur les marchés, et un devis parfaitement aligné sur la demande."},
 "analyse_docs": {"route": "/analyse-documents", "desc": "L'analyse de documents lit vos pièces écrites. **À quoi ça sert :** extraire automatiquement les éléments chiffrables d'un DPGF ou d'un CCTP, avec provenance vérifiable. **Comment l'utiliser :** importez vos fichiers (Excel, PDF, scans), l'outil structure les quantités et signale les incohérences. **Bénéfices :** un chiffrage sourcé, sans double comptage, et des contrôles arithmétiques automatiques."},
 "etudes_pc": {"route": "/etudes-pc", "desc": "Le module Études prépare votre permis de construire. **À quoi ça sert :** assembler et organiser les pièces d'un dossier PC. **Comment l'utiliser :** renseignez le projet et suivez les étapes de constitution du dossier. **Bénéfices :** un permis mieux préparé, des pièces cohérentes, moins d'allers-retours avec l'administration."},
 "multiniveaux": {"route": "/plan", "desc": "Les projets multi-niveaux regroupent plusieurs plans. **À quoi ça sert :** traiter une maison entière (fondations, RDC, étages) comme un seul projet. **Comment l'utiliser :** créez un groupe et ajoutez-y vos niveaux ; le métré et le devis sont consolidés automatiquement. **Bénéfices :** une vision d'ensemble, un chiffrage global cohérent, et un gain de temps sur les projets complexes."},
}

feats = []
for key, meta in KEY.items():
    if key not in starts:
        continue
    i = order.index(key)
    start = starts[key]
    end = chapters[i + 1]["start"] if i + 1 < len(chapters) else total
    dur = round(end - start, 2)
    ch = chapters[i]
    out = CLIPS / f"{key}.mp4"
    cmd = ["ffmpeg", "-y", "-i", str(DEMO / "construpilot-demo.mp4"),
           "-ss", str(start), "-to", str(end),
           "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p",
           "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart", str(out)]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        print("ERR", key, r.stderr[-300:]); continue
    # poster (image d'aperçu) — frame représentative à ~40% du clip
    poster = CLIPS / f"{key}.jpg"
    subprocess.run(["ffmpeg", "-y", "-ss", str(round(min(3.0, dur * 0.4), 2)), "-i", str(out),
                    "-frames:v", "1", "-q:v", "3", str(poster)], capture_output=True, text=True)
    feats.append({"key": key, "title": ch["title"], "clip": f"/demo/clips/{key}.mp4",
                  "poster": f"/demo/clips/{key}.jpg",
                  "duration": dur, "narration": ch["narration"],
                  "description": meta["desc"], "route": meta["route"]})
    print("clip", key, f"{dur}s")

(DEMO / "features.json").write_text(json.dumps({"features": feats}, ensure_ascii=False, indent=2))
print("DONE", len(feats), "clips")
