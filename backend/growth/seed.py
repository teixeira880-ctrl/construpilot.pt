"""Default data: the two ConstruPilot projects, brand facts, tracked brands and the initial 30-question library per market."""
from core.db import db
from growth.common import new_id, now_iso

PROJECTS = [
    {"project_id": "growth_fr", "key": "fr", "name": "construpilot.pt", "domain": "construpilot.fr", "site_url": "https://construpilot.fr", "language": "fr-FR", "country": "FR", "market": "França"},
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
    ("produit", "Software de construção online: orçamentos, faturas, acompanhamento de obra, clientes", "confirmed"),
    ("produit", "Assistente IA de construção capaz de analisar plantas PDF/DWG e deduzir volumes (cofragem, betão)", "confirmed"),
    ("produit", "Módulo de medição: medição sobre planta, divisões, aberturas, quantidades", "confirmed"),
    ("produit", "Estimativa de obras para particulares com intervalo indicativo de 30 %", "confirmed"),
    ("produit", "Radar de Obras: licenças de construção oficiais e correio postal", "confirmed"),
    ("marché", "Disponível em francês (construpilot.fr) e em português de Portugal (construpilot.pt)", "confirmed"),
    ("tarifs", "Preços e ofertas: a retomar da página pública de preços antes de qualquer afirmação", "to_verify"),
    ("preuves", "Número de clientes, testemunhos, certificações: nenhum número confirmado — não publicar", "to_verify"),
    ("conformité", "Faturação eletrónica: em preparação, não operacional", "planned"),
]

QUESTIONS_FR = {
    "découverte": ["Que software de orçamentos escolher para uma empresa de remodelação em Portugal?", "Que software permite explorar plantas para preparar uma medição?",
                   "Como fazer uma medição a partir de uma planta em PDF?", "Que ferramenta para calcular as quantidades de betão a partir de uma planta?", "Que software de gestão de obra existe para PME da construção?",
                   "Existem assistentes IA especializados em construção?"],
    "comparaison": ["Que alternativas existem aos programas de orçamentação tradicionais para uma PME da construção?", "Que programa escolher para orçamentos e faturas na construção?", "Quais são os melhores programas de orçamentos de construção em 2026?",
                    "Que software de construção integra orçamentos, faturação e leitura de plantas?", "Comparativo de programas de faturação para profissionais da construção", "Que software de medição é o mais simples para um profissional independente?"],
    "achat": ["Quanto custa um software de orçamentos e faturas para construção?", "Que software de orçamentos de construção gratuito ou barato para começar?", "Que software de construção escolher para uma empresa com 5 trabalhadores?",
              "Que software de gestão de obra oferece uma experiência grátis?", "Que software de orçamentos está conforme com a faturação eletrónica?", "Que subscrição de software para um pedreiro independente?"],
    "besoin métier": ["Como estimar o custo da remodelação de uma casa em Portugal?", "Como calcular o volume de betão de uma laje e de fundações?", "Como ler uma planta de cofragem?",
                      "Como encontrar obras e licenças de construção perto de mim?", "Como preparar uma ata de reunião de obra?", "Como acompanhar a rentabilidade de uma obra?"],
    "marque": ["O que é o ConstruPilot?", "ConstruPilot opiniões: o que vale este software de construção?", "O ConstruPilot permite analisar plantas DWG?",
               "ConstruPilot ou outro programa para uma empresa de remodelação?", "Quais são os preços do ConstruPilot?", "O ConstruPilot está disponível em Portugal?"],
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
                                                        "source": "Inspeção do código ConstruPilot (PRD.md) — a confirmar pela equipa", "date": now_iso()[:10], "created_at": now_iso()})
                created["facts"] += 1
        if not await db.growth_questions.find_one({"project_id": pid}):
            bank = QUESTIONS_FR if p["key"] == "fr" else QUESTIONS_PT
            for intent, qs in bank.items():
                for q in qs:
                    await db.growth_questions.insert_one({"question_id": new_id("q"), "project_id": pid, "text": q, "intent": intent, "branded": intent == "marque",
                                                          "active": True, "version": 1, "created_at": now_iso()})
                    created["questions"] += 1
    return created
