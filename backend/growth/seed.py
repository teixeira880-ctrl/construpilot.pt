"""Default data: the two ConstruPilot projects, brand facts, tracked brands and the initial 30-question library per market."""
from core.db import db
from growth.common import new_id, now_iso

PROJECTS = [
    {"project_id": "growth_fr", "key": "fr", "name": "construpilot.fr", "domain": "construpilot.fr", "site_url": "https://construpilot.fr", "language": "fr-FR", "country": "FR", "market": "France"},
    {"project_id": "growth_pt", "key": "pt", "name": "construpilot.pt", "domain": "construpilot.pt", "site_url": "https://construpilot.pt", "language": "pt-PT", "country": "PT", "market": "Portugal"},
]
DEFAULT_SETTINGS = {"max_pages": 60, "crawl_cadence_days": 7, "publish_mode": "review", "budgets": {"daily_usd": 5, "monthly_usd": 60},
                    "providers": {"perplexity": {"enabled": True, "preset": "fast", "model": None}, "openai": {"enabled": True, "model": "gpt-5.4"},
                                  "gemini": {"enabled": False, "model": "gemini-3.5-flash"}, "anthropic": {"enabled": False, "model": "claude-sonnet-4-6"}},
                    "repetitions": 2, "content_frequency_per_week": 2, "autopilot_enabled": True, "articles_per_week": 3, "autopilot_batch": 3, "seo_override_mode": "auto", "auto_fix_enabled": True}

SELF_BRAND = {"name": "ConstruPilot", "variants": ["ConstruPilot", "Constru Pilot", "Construpilot", "construpilot"], "domains": ["construpilot.fr", "construpilot.pt"], "is_self": True, "confirmed": True}
COMPETITORS_FR = [{"name": "Obat", "variants": ["Obat"], "domains": ["obat.fr"], "is_self": False, "confirmed": False, "suggested": True},
                  {"name": "Vertuoza", "variants": ["Vertuoza"], "domains": ["vertuoza.com"], "is_self": False, "confirmed": False, "suggested": True}]

FACTS = [
    ("produit", "Logiciel BTP en ligne : devis, factures, suivi de chantier, clients", "confirmed"),
    ("produit", "Assistant IA BTP capable d'analyser des plans PDF/DWG et d'en déduire des volumes (coffrage, béton)", "confirmed"),
    ("produit", "Module de métré : mesure sur plan, pièces, ouvertures, quantités", "confirmed"),
    ("produit", "Estimation de travaux pour particuliers avec fourchette indicative de 30 %", "confirmed"),
    ("produit", "Radar Chantiers : permis de construire officiels (SITADEL) et courrier postal", "confirmed"),
    ("marché", "Disponible en français (construpilot.fr) et en portugais du Portugal (construpilot.pt)", "confirmed"),
    ("tarifs", "Tarifs et offres : à reprendre depuis la page tarifs publique avant toute affirmation", "to_verify"),
    ("preuves", "Nombre de clients, témoignages, certifications : aucun chiffre confirmé — ne pas publier", "to_verify"),
    ("conformité", "Facturation électronique (PDP) : en préparation, non opérationnelle", "planned"),
]

QUESTIONS_FR = {
    "découverte": ["Quel logiciel de devis choisir pour une entreprise de rénovation en France ?", "Quels logiciels permettent d'exploiter des plans pour préparer un métré ?",
                   "Comment faire un métré à partir d'un plan PDF ?", "Quel outil pour calculer les quantités de béton à partir d'un plan ?", "Quels logiciels de gestion de chantier existent pour les PME du bâtiment ?",
                   "Existe-t-il des assistants IA spécialisés dans le bâtiment ?"],
    "comparaison": ["Quelles alternatives à Obat et Vertuoza pour une PME du bâtiment ?", "Obat ou Vertuoza : lequel choisir pour les devis et factures ?", "Quels sont les meilleurs logiciels de devis bâtiment en 2026 ?",
                    "Quel logiciel BTP intègre à la fois devis, facturation et lecture de plans ?", "Comparatif des logiciels de facturation pour artisans du BTP", "Quel logiciel de métré est le plus simple pour un artisan ?"],
    "achat": ["Combien coûte un logiciel de devis et factures pour artisan ?", "Quel logiciel de devis bâtiment gratuit ou pas cher pour démarrer ?", "Quel logiciel BTP choisir pour une entreprise de 5 salariés ?",
              "Quel logiciel de gestion de chantier propose un essai gratuit ?", "Quel logiciel de devis est conforme à la facturation électronique 2026 ?", "Quel abonnement logiciel pour un maçon indépendant ?"],
    "besoin métier": ["Comment estimer le coût d'une rénovation de maison en France ?", "Comment calculer le volume de béton d'une dalle et de fondations ?", "Comment lire un plan de coffrage ?",
                      "Comment trouver des chantiers et des permis de construire près de chez moi ?", "Comment préparer un compte rendu de réunion de chantier ?", "Comment suivre la rentabilité d'un chantier ?"],
    "marque": ["Qu'est-ce que ConstruPilot ?", "ConstruPilot avis : que vaut ce logiciel BTP ?", "ConstruPilot permet-il d'analyser des plans DWG ?",
               "ConstruPilot ou Obat pour une entreprise de rénovation ?", "Quels sont les tarifs de ConstruPilot ?", "ConstruPilot est-il disponible au Portugal ?"],
}
QUESTIONS_PT = {
    "découverte": ["Qual é o melhor software de orçamentos para empresas de construção em Portugal?", "Que software permite gerir obras e faturação em Portugal?",
                   "Como analisar plantas e calcular quantidades para um orçamento de construção?", "Que ferramentas existem para fazer medições a partir de plantas em PDF?",
                   "Que software de gestão de obras existe para pequenas empresas de construção?", "Existem assistentes de inteligência artificial para a construção civil?"],
    "comparaison": ["Quais são as alternativas aos programas de orçamentação tradicionais em Portugal?", "Qual o melhor software de faturação para empreiteiros em Portugal?",
                    "Que software junta orçamentos, faturação e leitura de plantas?", "Comparativo de programas de orçamentos para construção civil", "Qual o software de medições mais simples para um empreiteiro?",
                    "Software de gestão de obras: quais as opções mais usadas em Portugal?"],
    "achat": ["Quanto custa um software de orçamentos e faturação para construção?", "Que software de orçamentos gratuito ou barato para começar?", "Que software de construção escolher para uma empresa com 5 trabalhadores?",
              "Que software de gestão de obras oferece período de teste gratuito?", "Que software de faturação é certificado pela AT em Portugal?", "Que subscrição de software para um pedreiro independente?"],
    "besoin métier": ["Como estimar o custo de uma remodelação de casa em Portugal?", "Como calcular o volume de betão de uma laje e das fundações?", "Como ler uma planta de cofragem?",
                      "Como acompanhar a rentabilidade de uma obra?", "Como preparar uma ata de reunião de obra?", "Como fazer um mapa de quantidades a partir de uma planta?"],
    "marque": ["O que é o ConstruPilot?", "ConstruPilot opiniões: vale a pena este software de construção?", "O ConstruPilot permite analisar plantas DWG?",
               "Quais são os preços do ConstruPilot?", "O ConstruPilot está disponível em Portugal?", "ConstruPilot ou outro software de orçamentos para construção?"],
}


async def ensure_seed() -> dict:
    created = {"projects": 0, "questions": 0, "facts": 0, "brands": 0}
    for p in PROJECTS:
        if not await db.growth_projects.find_one({"project_id": p["project_id"]}):
            await db.growth_projects.insert_one({**p, "settings": DEFAULT_SETTINGS, "created_at": now_iso()})
            created["projects"] += 1
        pid = p["project_id"]
        if not await db.growth_brands.find_one({"project_id": pid, "is_self": True}):
            await db.growth_brands.insert_one({"brand_id": new_id("brand"), "project_id": pid, **SELF_BRAND, "created_at": now_iso()})
            created["brands"] += 1
            if p["key"] == "fr":
                for c in COMPETITORS_FR:
                    await db.growth_brands.insert_one({"brand_id": new_id("brand"), "project_id": pid, **c, "created_at": now_iso()})
                    created["brands"] += 1
        if not await db.growth_brand_facts.find_one({"project_id": pid}):
            for cat, st, status in FACTS:
                await db.growth_brand_facts.insert_one({"fact_id": new_id("fact"), "project_id": pid, "category": cat, "statement": st, "status": status,
                                                        "source": "Inspection du code ConstruPilot (PRD.md) — à confirmer par l'équipe", "date": now_iso()[:10], "created_at": now_iso()})
                created["facts"] += 1
        if not await db.growth_questions.find_one({"project_id": pid}):
            bank = QUESTIONS_FR if p["key"] == "fr" else QUESTIONS_PT
            for intent, qs in bank.items():
                for q in qs:
                    await db.growth_questions.insert_one({"question_id": new_id("q"), "project_id": pid, "text": q, "intent": intent, "branded": intent == "marque",
                                                          "active": True, "version": 1, "created_at": now_iso()})
                    created["questions"] += 1
    return created
