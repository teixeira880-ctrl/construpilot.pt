"""Étape 1 — Génère TOUTE la narration FR d'abord, puis mesure la durée exacte de
chaque piste. La vidéo sera ensuite calée sur ces durées (synchro parfaite)."""
import json, os, subprocess
from pathlib import Path
from elevenlabs.client import ElevenLabs

API = os.environ.get("ELEVENLABS_API_KEY")
VOICE = "6DEjyaHWnTHsvXM5Byys"
AUD = Path("/app/frontend/public/demo/audio"); AUD.mkdir(parents=True, exist_ok=True)
client = ElevenLabs(api_key=API)

# Ordre = ordre du tour. Les 3 modules clés (métré, devis, factures) sont détaillés.
N = {
 "home": ("Bienvenue sur ConstruPilot", "Bienvenue sur ConstruPilot, la plateforme tout-en-un de chiffrage et de gestion pour les professionnels du bâtiment. Suivez la visite : chaque fonction est montrée en action."),
 "estimation": ("Estimateur", "L'estimateur génère un chiffrage détaillé de votre projet, poste par poste, à partir d'une simple description en langage courant."),
 "metre": ("Métré sur plan", "Le métré sur plan est le cœur de ConstruPilot. Importez un plan réel et nommez-le. Calibrez-le en indiquant une seule distance connue : toutes vos mesures deviennent alors précises au centimètre. Tracez une surface pour obtenir instantanément les mètres carrés. Tracez un périmètre pour vos linéaires de plinthes ou de cloisons. Tracez une distance pour un métré linéaire simple. Dessinez enfin une pièce, puis déduisez automatiquement portes et fenêtres de vos surfaces. Aucun calcul manuel, aucune erreur possible."),
 "plans_pro": ("Analyse de plan Pro", "L'analyse de plan Pro détecte automatiquement les pièces, les murs et les surfaces pour accélérer encore votre métré."),
 "controle": ("Contrôle des cotes", "Le contrôle des cotes compare vos mesures aux cotes écrites du plan et signale la moindre incohérence."),
 "escaliers": ("Calcul d'escaliers", "Le module escaliers calcule votre ouvrage béton, contrôle les normes, propose une vue en trois dimensions interactive et un dossier PDF entièrement coté."),
 "calculateurs": ("Calculateurs de matériaux", "Les calculateurs donnent les quantités exactes de matériaux, marges et pertes de pose comprises."),
 "prix": ("Prix matériaux", "La base de prix matériaux vous tient informé des tarifs à jour du marché."),
 "devis": ("Suivi des devis", "Le suivi des devis centralise toutes vos propositions commerciales et leur statut, du brouillon à la signature."),
 "devis_editeur": ("Éditeur de devis", "L'éditeur de devis compose votre proposition ligne par ligne. Ajoutez des fournitures, de la main d'œuvre et des ouvrages complets, avec leurs quantités et leurs prix unitaires. La TVA, les sous-totaux et le total sont recalculés en temps réel, sans la moindre erreur de calcul. En un clic, générez un devis PDF professionnel prêt à envoyer à votre client."),
 "factures": ("Factures", "La facturation transforme n'importe quel devis signé en facture conforme, en un seul clic. Acomptes, situations de travaux et factures définitives restent reliés à votre chantier, avec une numérotation continue et le format Factur-X."),
 "situations": ("Situations de travaux", "Les situations de travaux gèrent l'avancement et les acomptes de vos chantiers, mois après mois."),
 "clients": ("Clients", "L'espace clients regroupe tous vos contacts et l'historique de chaque relation."),
 "chantiers": ("Dossiers chantier", "Les dossiers chantier réunissent plans, devis et documents de chaque projet au même endroit."),
 "suivi": ("Suivi de chantier", "Le suivi de chantier pilote l'avancement au quotidien, tâche par tâche."),
 "dpgf": ("DPGF vers devis", "Le module DPGF transforme le cadre de l'architecte en un devis directement chiffrable."),
 "analyse_docs": ("Analyse de documents", "L'analyse de documents lit vos DPGF et CCTP pour en extraire automatiquement les éléments chiffrables."),
 "scanner": ("Scanner de devis", "Le scanner numérise un devis papier et le rend immédiatement exploitable."),
 "appro": ("Analyse technique et appro", "L'analyse technique et l'approvisionnement optimisent vos commandes de matériaux et anticipent les besoins."),
 "etudes_pc": ("Études permis de construire", "Le module études prépare et assemble les pièces de votre permis de construire."),
 "mesure_photo": ("Mesurer sur photo", "Mesurez directement sur une simple photo prise sur le chantier."),
 "rendu_ia": ("Rendu IA avant-après", "Le rendu par intelligence artificielle illustre vos travaux, avant et après."),
 "multiniveaux": ("Projets multi-niveaux", "Regroupez fondations, rez-de-chaussée et étages en un projet multi-niveaux, avec métré et devis consolidés."),
 "bibliotheque": ("Bibliothèque d'ouvrages", "La bibliothèque mémorise vos compositions d'ouvrages, réutilisables sur tous vos chantiers."),
 "catalogue": ("Catalogue de prix", "Le catalogue de prix personnalise vos tarifs et vos ratios d'entreprise."),
 "equipe": ("Équipe", "La gestion d'équipe partage l'accès et les données entre tous vos collaborateurs."),
 "rh": ("RH et pointage", "Le module ressources humaines gère le pointage et les heures de vos équipes."),
 "entreprise": ("Espace entreprise", "L'espace entreprise centralise l'identité et les paramètres de votre société."),
 "ma_page": ("Ma page publique", "Votre page publique met en avant votre entreprise et vos réalisations auprès de vos prospects."),
 "radar": ("Radar chantiers", "Le radar chantiers vous alerte des opportunités d'affaires près de chez vous."),
 "assistant": ("Assistant BTP", "L'assistant intelligent répond à vos questions et vous guide dans toute l'application."),
 "pro": ("L'offre Pro", "Passez à l'offre Pro : sept jours d'essai, puis un abonnement clair et sans engagement."),
 "dashboard": ("Tableau de bord", "Enfin, votre tableau de bord réunit toute votre activité. ConstruPilot vous fait gagner du temps, du premier chiffrage à la facturation finale."),
}


def synth(text, path):
    r = client.text_to_speech.convert(voice_id=VOICE, model_id="eleven_multilingual_v2",
                                      output_format="mp3_44100_128", text=text)
    with open(path, "wb") as f:
        for ch in r:
            if ch:
                f.write(ch)


def dur(path):
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                        "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
                       capture_output=True, text=True)
    return float(r.stdout.strip() or 0)


def main():
    out = {}
    for key, (title, text) in N.items():
        mp3 = AUD / f"{key}.mp3"
        print("TTS", key, flush=True)
        synth(text, mp3)
        out[key] = {"title": title, "text": text, "file": str(mp3), "duration": round(dur(mp3), 2)}
    Path("/tmp/narration.json").write_text(json.dumps(out, ensure_ascii=False, indent=2))
    print("NARRATION DONE", len(out), "pistes", flush=True)


if __name__ == "__main__":
    main()
