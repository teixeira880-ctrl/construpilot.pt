"""Lot 44 — documents haut de gamme servis par le site + prix du générateur alignés sur le pitch.
Usage : python3 apply_l44.py <racine_app> <dossier_lot44>   (idempotent ; s'arrête si une ancre manque)"""
import shutil, sys, pathlib
root, src = pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[2])
# 1. fichiers
shutil.copy(src / "premium_docs.py", root / "backend/engines/premium_docs.py")
dst = root / "backend/assets/premium_docs"
if dst.exists():
    shutil.rmtree(dst)
shutil.copytree(src / "premium_docs", dst)
# 2. routes/brochures.py
p = root / "backend/routes/brochures.py"; s = p.read_text()
if "premium_docs" not in s:
    a = "from engines import presentation_pdf, presentation_pptx"
    assert s.count(a) == 1, "ancre import"
    s = s.replace(a, a + "\nfrom engines import premium_docs", 1)
    hooks = [
        ('    """Plaquette commerciale, à l\'en-tête de l\'entreprise abonnée."""\n',
         '    if (user.get("role") == "admin" or not branded) and premium_docs.available("plaquette", lang, "pdf"):\n        return premium_docs.response("plaquette", lang, "pdf")\n'),
        ('    """Deck client PowerPoint : page de garde personnalisée et captures d\'écran réelles."""\n',
         '    if (user.get("role") == "admin" or not branded) and premium_docs.available("client", lang, "pptx"):\n        return premium_docs.response("client", lang, "pptx")\n'),
        ('    """Présentation investisseur avec les KPI réels mesurés à l\'instant de la génération."""\n',
         '    if premium_docs.available("investor", lang, "pdf"):\n        return premium_docs.response("investor", lang, "pdf")\n'),
        ('    """Deck investisseur PowerPoint : KPI réels, marché, plan d\'exploitation de 500 000 €."""\n',
         '    if premium_docs.available("investor", lang, "pptx"):\n        return premium_docs.response("investor", lang, "pptx")\n'),
    ]
    for a, b in hooks:
        assert s.count(a) == 1, "ancre " + a[:40]
        s = s.replace(a, a + b, 1)
    p.write_text(s)
# 3. prix du générateur (plaquettes à l'en-tête d'un client abonné)
p = root / "backend/engines/presentation_pdf.py"; s = p.read_text()
R = [
 ('''                  ["Particulier", "Un projet personnel, une estimation, un suivi de travaux", f"{OFFER['particulier']:.0f} € / mois"],
                  ["Professionnel", "Artisans et PME : devis, chantiers, factures, espace client", f"{OFFER['pro']:.0f} € / mois"],
                  ["API / intégration", "Éditeurs et grands comptes qui branchent leurs outils", f"{OFFER['api']:.0f} € / mois"],
                  ["Options", "Modules additionnels (facturation avancée, etc.)", f"à partir de {OFFER['addon']:.0f} € / mois"]],''',
  '''                  ["Particulier · Premium", "Projets illimités, scanner de devis (offre gratuite : 2 projets)", "19 € / mois"],
                  ["Pro", "Artisans et TPE : devis depuis plan, CCTP, photo ou voix, signature en ligne", "149 € HT / mois"],
                  ["Pro Business", "PME : 5 utilisateurs, facturation et Factur-X incluses, RH, suivi de chantier", "249 € HT / mois"],
                  ["Options et API", "Facturation 5 € / mois · Project Pass 50 € · API dès 99 € / mois", "à la carte"]],'''),
 ('''                  ["Individual", "A personal project, an estimate, works monitoring", f"€{OFFER['particulier']:.0f} / month"],
                  ["Professional", "Trade contractors and SMEs: quotes, sites, invoices, client portal", f"€{OFFER['pro']:.0f} / month"],
                  ["API / integration", "Software vendors and large accounts connecting their tools", f"€{OFFER['api']:.0f} / month"],
                  ["Add-ons", "Additional modules (advanced invoicing, etc.)", f"from €{OFFER['addon']:.0f} / month"]],''',
  '''                  ["Homeowner · Premium", "Unlimited projects, quote scanner (free plan: 2 projects)", "€19 / month"],
                  ["Pro", "Tradespeople: quotes from a plan, specification, photo or voice, e-signature", "€149 excl. VAT / month"],
                  ["Pro Business", "SMEs: 5 users, invoicing and e-invoicing included, HR, site tracking", "€249 excl. VAT / month"],
                  ["Add-ons and API", "Invoicing €5 / month · Project Pass €50 · API from €99 / month", "à la carte"]],'''),
 ('''                  ["Particular", "Um projeto pessoal, uma estimativa, acompanhamento de obras", f"{OFFER['particulier']:.0f} € / mês"],
                  ["Profissional", "Artesãos e PME: orçamentos, obras, faturas, espaço do cliente", f"{OFFER['pro']:.0f} € / mês"],
                  ["API / integração", "Editores e grandes contas que ligam as suas ferramentas", f"{OFFER['api']:.0f} € / mês"],
                  ["Opções", "Módulos adicionais (faturação avançada, etc.)", f"a partir de {OFFER['addon']:.0f} € / mês"]],''',
  '''                  ["Particular · Premium", "Projetos ilimitados, análise de orçamentos (plano gratuito: 2 projetos)", "19 € / mês"],
                  ["Pro", "Artesãos: orçamentos a partir de planta, caderno de encargos, foto ou voz", "149 € + IVA / mês"],
                  ["Pro Business", "PME: 5 utilizadores, faturação incluída, RH, acompanhamento de obra", "249 € + IVA / mês"],
                  ["Opções e API", "Faturação 5 € / mês · Project Pass 50 € · API desde 99 € / mês", "à medida"]],'''),
 ('OFFER = {"free_promo": True,', 'OFFER = {"free_promo": False,'),
]
n_pdf = 0
for a, b in R:
    n_pdf += s.count(a)
    s = s.replace(a, b)
p.write_text(s)
p = root / "backend/engines/presentation_pptx.py"; s = p.read_text()
R = [
 ('''                "Professionnel : 149 € / mois par entreprise · Particulier : 19 € / mois.",
                "API et intégrations : 99 € / mois · options et modules à partir de 5 € / mois.",
                "Essai de 7 jours, phase de lancement gratuite en cours, paiement par Stripe.",''',
  '''                "Pro : 149 € HT / mois (1 utilisateur) · Pro Business : 249 € HT / mois (5 utilisateurs, facturation incluse).",
                "Premium particulier : 19 € / mois · Project Pass 50 € · option Facturation 5 € / mois · API dès 99 € / mois.",
                "Essai gratuit de 7 jours, sans engagement, paiement par Stripe.",'''),
 ('''                "Professional: €149 / month per company · Individual: €19 / month.",
                "API and integrations: €99 / month · add-ons from €5 / month.",''',
  '''                "Pro: €149 excl. VAT / month (1 user) · Pro Business: €249 excl. VAT / month (5 users, invoicing included).",
                "Homeowner Premium: €19 / month · Project Pass €50 · invoicing option €5 / month · API from €99 / month.",'''),
 ('''                "Profissional: 149 € / mês por empresa · Particular: 19 € / mês.",
                "API e integrações: 99 € / mês · opções e módulos a partir de 5 € / mês.",''',
  '''                "Pro: 149 € + IVA / mês (1 utilizador) · Pro Business: 249 € + IVA / mês (5 utilizadores, faturação incluída).",
                "Premium particular: 19 € / mês · Project Pass 50 € · opção Faturação 5 € / mês · API desde 99 € / mês.",'''),
]
n_pptx = 0
for a, b in R:
    n_pptx += s.count(a)
    s = s.replace(a, b)
s = s.replace("Essai de 7 jours, phase de lancement gratuite en cours, paiement par Stripe.", "Essai gratuit de 7 jours, sans engagement, paiement par Stripe.")
p.write_text(s)
print(f"L44 OK (prix générateur : {n_pdf} tableaux PDF, {n_pptx} blocs PowerPoint mis à jour)")
# 4. page publique /presentation : les plaquettes haut de gamme
pres = root / "frontend/public/presentation"
pres.mkdir(parents=True, exist_ok=True)
for f in (src / "presentation").iterdir():
    shutil.copy(f, pres / f.name)
print("L44 presentation OK")
