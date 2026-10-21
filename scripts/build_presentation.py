"""Plaquette COMPLÈTE ConstruPilot (de A à Z) en 3 langues (PT / FR / EN).

Sortie : /app/frontend/public/presentation/construpilot-{pt,fr,en}.pdf
Couvre : mission & principes fondateurs, fondations techniques, TOUS les modules,
les 3 applications mobiles (Entreprise, Collaborateur, Particuliers), conformité,
marché & lancement Europe. Déterministe, sans dépendance réseau.
"""
import os
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak, HRFlowable,
    ListFlowable, ListItem,
)

OUT_DIR = "/app/frontend/public/presentation"
BRAND = colors.HexColor("#0F5257")
ACCENT = colors.HexColor("#E07A5F")
INK = colors.HexColor("#1f2937")
MUTED = colors.HexColor("#6b7280")
LINE = colors.HexColor("#cbd5e1")
DARK = colors.HexColor("#0B0F17")

CONTENT = {
    "fr": {
        "file": "construpilot-fr.pdf",
        "cover_title": "ConstruPilot",
        "cover_tag": "Le SaaS BTP déterministe — 0% hallucination",
        "cover_sub": "Dossier complet · fondations de A à Z · Web Summit 2026 · Lancement Europe",
        "ready": "DÉJÀ EN LIGNE · PRÊT POUR UN LANCEMENT DANS TOUTE L'EUROPE (FR / PT / EN)",
        "s_mission": "Mission & principes fondateurs",
        "mission_intro": "ConstruPilot est une plateforme SaaS pour les professionnels du BTP et leurs clients. "
                         "Sa fondation est une promesse simple : zéro hallucination. Tous les calculs — métré, devis, "
                         "facturation, énergie et ingénierie — sont déterministes, traçables et vérifiables. L'IA sert "
                         "uniquement à lire et à assister ; jamais à inventer un chiffre.",
        "principles": [
            "0% hallucination : tous les calculs sont déterministes, jamais générés par l'IA.",
            "Traçabilité totale : chaque donnée porte sa provenance (mesure / document / essai) et son statut.",
            "L'IA lit (OCR, extraction de faits) mais ne calcule jamais.",
            "Conformité réglementaire native (Factur-X, DPE/ADEME, DTU).",
            "Aucune affirmation publique sans preuve (référentiel de claims).",
            "Plafond d'exploitation maîtrisé avec alertes de coût.",
            "Multilingue et multi-TVA, prêt pour l'Europe (FR / PT / EN).",
        ],
        "s_found": "Fondations techniques",
        "stack": [
            "Frontend : React (CRA), shadcn/ui, Tailwind CSS ; apps mobiles via Capacitor (iOS + Android).",
            "Backend : FastAPI (Python) + MongoDB ; limitation de débit (SlowAPI).",
            "Sécurité : cookies HttpOnly, JWT, connexion Google, 2FA administrateur, anti-force brute.",
            "IA (lecture seule) : clé universelle Emergent — OpenAI, Anthropic Claude, Google Gemini, Whisper (STT) et synthèse vocale.",
            "Génération PDF déterministe (ReportLab) ; Factur-X PDF/A-3 + XML CII.",
            "Intégrations : Stripe (paiements), Autodesk APS (CAO), ADEME/France Rénov' (DPE & aides), facturxapi (EN 16931), Perplexity (prix), ElevenLabs (voix), Resend (e-mails), stockage objet Emergent.",
        ],
        "s_modules": "Les modules, de A à Z",
        "s_apps": "Les 3 applications mobiles",
        "s_compliance": "Conformité & réglementation",
        "compliance": [
            "Facturation électronique Factur-X, profil EN 16931 certifié (PDF/A-3 + XML CII).",
            "Données énergétiques officielles ADEME (DPE open data) et aides France Rénov'.",
            "Calculs d'ouvrages conformes aux DTU (escaliers, béton).",
            "RGPD : suppression de compte et de données in-app et par URL dédiée.",
            "Conformité stores Apple/Google (étiquettes de confidentialité, Data Safety).",
        ],
        "s_market": "Marché & lancement Europe",
        "market": "ConstruPilot est opérationnel et déjà en ligne. L'objectif est un lancement dans toute l'Europe — "
                  "à commencer par la France et le Portugal — grâce à une architecture multilingue (FR/PT/EN) et multi-TVA, "
                  "et un moteur de facturation électronique conforme à la norme européenne EN 16931, prête pour l'obligation "
                  "de facturation électronique.",
        "contact": "Contact : Martinho · ConstruPilot — prêt pour une démonstration en direct.",
        "col_mod": "Module", "col_desc": "Description",
        "lbl_audience": "Public",
        "modules": [
            ("Assistant IA BTP", "Claude / OpenAI / Gemini (clé Emergent) : commandes vocales, recherche web de prix matériaux, chiffrage à la voix — l'IA assiste mais ne calcule jamais le métré/chiffrage."),
            ("Métré sur plan", "Import PDF/DXF/images/ZIP, calibration d'échelle, tracé de surfaces, linéaires et volumes, déduction d'ouvertures, familles et sous-totaux, versions comparables."),
            ("Projets multi-niveaux", "Regroupe plusieurs plans en niveaux (Fondations, RDC, R+1…) et consolide métré + chiffrage par niveau et pour le projet entier, en un seul dossier PDF."),
            ("Éditeur de devis", "Chiffrage déterministe par corps d'état (16 ouvrages + postes perso), prix unitaires éditables, TVA multi-taux, remises, acompte, échéancier, PDF professionnel."),
            ("Factures Factur-X", "Factures électroniques hybrides PDF/A-3 + XML CII, profils BASIC et EN 16931 certifié, prêtes pour l'obligation de facturation électronique."),
            ("Suivi de chantier", "Dossier chantier continu : photos, comptes rendus, comparateur avant/après, PV de réception, levée de réserves — tout horodaté et tracé."),
            ("Espace Client (portail)", "Portail invité à isolation stricte : le client suit son chantier, consulte devis et factures, accepte et signe en ligne (OTP, acompte automatique)."),
            ("RenoPilot — rénovation énergétique", "Import du DPE officiel ADEME, scénarios d'audit, aides (MaPrimeRénov'/CEE/Éco-PTZ) via l'API France Rénov', reste à charge par geste, rapport PDF."),
            ("StructuroPilot — ingénierie structurelle", "Étude autonome depuis une description : extraction de faits, questionnaire adaptatif, modèle tracé (niveaux/éléments), esquisses et note d'étude. Moteur Eurocodes verrouillé par honnêteté."),
            ("Analyse de documents", "Lecture Excel/PDF/scans avec OCR IA, provenance cellule/page, contrôles arithmétiques déterministes, rapprochement CCTP↔DPGF/devis, mémoire des corrections."),
            ("Calcul d'escaliers", "Escaliers droits, quart/demi-tournant et hélicoïdaux conformes DTU, optimisation, analyse béton, vue 3D interactive, dossier PDF coté, escalier→devis."),
            ("Analyse de plan Pro", "Traitement de fichiers CAO lourds (DWG/RVT/IFC) via Autodesk APS pour les professionnels."),
            ("Résoudre un problème", "Diagnostic BTP assisté par IA à partir d'une description et de photos (humidité, fissures…)."),
            ("RH & pointage chantier", "Pointage géolocalisé (clock-in/out), feuilles d'heures, selfie, notes de chantier pour les équipes terrain."),
            ("Espace Entreprise & rôles", "Organisation multi-utilisateurs (owner, admin, chef de chantier, comptable, membre, ouvrier), permissions fines, KPIs, branding partagé."),
            ("Admin & pilotage", "Back-office complet : gestion des utilisateurs, 2FA, Revenue Cockpit, suivi des dépenses et plafond d'exploitation maîtrisé."),
            ("Growth & pages publiques", "Landings Pro et Particuliers, vidéo de démo narrée, clips par fonction, SEO, page vitrine publique par entreprise."),
        ],
        "apps": [
            ("ConstruPilot Entreprise", "Chef d'entreprise, artisans, TPE/PME du BTP",
             "L'app de terrain du professionnel : créez vos devis à la voix, chiffrez sur plan, suivez vos chantiers et facturez sans ressaisie.",
             ["Devis & factures conformes (TVA, retenue de garantie)", "Métré automatique sur plan PDF",
              "Dictée vocale : devis, réserves, messages", "Dossier chantier continu (photos, comptes rendus)",
              "Espace client intégré"]),
            ("ConstruPilot Collaborateur", "Salariés, compagnons et sous-traitants",
             "L'app des équipes terrain : pointez vos heures, envoyez vos photos, signalez les réserves et consultez vos tâches du jour — tout remonte au bureau.",
             ["Pointage géolocalisé (opt-in)", "Photos et comptes rendus de chantier",
              "Signalement de réserves", "Tâches du jour"]),
            ("ConstruPilot Particuliers", "Maîtres d'ouvrage / particuliers",
             "Estimez le prix de vos travaux en quelques minutes, comparez les devis reçus et suivez votre chantier en toute transparence.",
             ["Estimation chiffrée des travaux", "Comparaison de devis",
              "Suivi de chantier (photos, comptes rendus)", "Accès aux aides à la rénovation"]),
        ],
    },
    "pt": {
        "file": "construpilot-pt.pdf",
        "cover_title": "ConstruPilot",
        "cover_tag": "O SaaS determinístico para a construção — 0% alucinação",
        "cover_sub": "Dossier completo · fundações de A a Z · Web Summit 2026 · Lançamento Europa",
        "ready": "JÁ ONLINE · PRONTO PARA LANÇAMENTO EM TODA A EUROPA (PT / FR / EN)",
        "s_mission": "Missão & princípios fundadores",
        "mission_intro": "O ConstruPilot é uma plataforma SaaS para os profissionais da construção civil e os seus clientes. "
                         "A sua fundação é uma promessa simples: zero alucinação. Todos os cálculos — medições, orçamentos, "
                         "faturação, energia e engenharia — são determinísticos, rastreáveis e verificáveis. A IA serve apenas "
                         "para ler e assistir; nunca para inventar um valor.",
        "principles": [
            "0% alucinação: todos os cálculos são determinísticos, nunca gerados por IA.",
            "Rastreabilidade total: cada dado tem origem (medição / documento / ensaio) e estado.",
            "A IA lê (OCR, extração de factos) mas nunca calcula.",
            "Conformidade regulamentar nativa (Factur-X, DPE/ADEME, DTU).",
            "Nenhuma afirmação pública sem prova (referencial de claims).",
            "Teto de exploração controlado com alertas de custo.",
            "Multilíngue e multi-IVA, pronto para a Europa (PT / FR / EN).",
        ],
        "s_found": "Fundações técnicas",
        "stack": [
            "Frontend: React (CRA), shadcn/ui, Tailwind CSS; apps móveis via Capacitor (iOS + Android).",
            "Backend: FastAPI (Python) + MongoDB; limitação de débito (SlowAPI).",
            "Segurança: cookies HttpOnly, JWT, login Google, 2FA de administrador, anti-força bruta.",
            "IA (apenas leitura): chave universal Emergent — OpenAI, Anthropic Claude, Google Gemini, Whisper (STT) e síntese de voz.",
            "Geração de PDF determinística (ReportLab); Factur-X PDF/A-3 + XML CII.",
            "Integrações: Stripe (pagamentos), Autodesk APS (CAD), ADEME/France Rénov' (DPE & apoios), facturxapi (EN 16931), Perplexity (preços), ElevenLabs (voz), Resend (emails), armazenamento de objetos Emergent.",
        ],
        "s_modules": "Os módulos, de A a Z",
        "s_apps": "As 3 aplicações móveis",
        "s_compliance": "Conformidade & regulamentação",
        "compliance": [
            "Faturação eletrónica Factur-X, perfil EN 16931 certificado (PDF/A-3 + XML CII).",
            "Dados energéticos oficiais ADEME (DPE open data) e apoios France Rénov'.",
            "Cálculos de obra conformes às normas DTU (escadas, betão).",
            "RGPD: eliminação de conta e de dados na app e por URL dedicada.",
            "Conformidade com as stores Apple/Google (etiquetas de privacidade, Data Safety).",
        ],
        "s_market": "Mercado & lançamento Europa",
        "market": "O ConstruPilot está operacional e já em linha. O objetivo é um lançamento em toda a Europa — "
                  "a começar por França e Portugal — graças a uma arquitetura multilíngue (PT/FR/EN) e multi-IVA, "
                  "e a um motor de faturação eletrónica conforme à norma europeia EN 16931, preparado para a obrigação "
                  "de faturação eletrónica.",
        "contact": "Contacto: Martinho · ConstruPilot — pronto para uma demonstração ao vivo.",
        "col_mod": "Módulo", "col_desc": "Descrição",
        "lbl_audience": "Público",
        "modules": [
            ("Assistente IA da construção", "Claude / OpenAI / Gemini (chave Emergent): comandos por voz, pesquisa web de preços de materiais, orçamentação por voz — a IA assiste mas nunca calcula a medição/orçamento."),
            ("Medição sobre planta", "Importa PDF/DXF/imagens/ZIP, calibra a escala, traça superfícies, lineares e volumes, deduz vãos, famílias e subtotais, versões comparáveis."),
            ("Projetos multinível", "Agrupa várias plantas em níveis (Fundações, R/C, 1.º andar…) e consolida medição + orçamento por nível e para o projeto inteiro, num único dossier PDF."),
            ("Editor de orçamentos", "Orçamentação determinística por ofício (16 artigos + artigos próprios), preços unitários editáveis, IVA multitaxa, descontos, sinal, plano de pagamentos, PDF profissional."),
            ("Faturas Factur-X", "Faturas eletrónicas híbridas PDF/A-3 + XML CII, perfis BASIC e EN 16931 certificado, prontas para a obrigação de faturação eletrónica."),
            ("Acompanhamento de obra", "Dossier de obra contínuo: fotos, relatórios, comparador antes/depois, auto de receção, levantamento de reservas — tudo datado e rastreado."),
            ("Espaço Cliente (portal)", "Portal de convidado com isolamento estrito: o cliente acompanha a obra, consulta orçamentos e faturas, aceita e assina online (OTP, sinal automático)."),
            ("RenoPilot — renovação energética", "Importa o DPE oficial ADEME, cenários de auditoria, apoios (MaPrimeRénov'/CEE/Eco-PTZ) via API France Rénov', custo restante por intervenção, relatório PDF."),
            ("StructuroPilot — engenharia estrutural", "Estudo autónomo a partir de uma descrição: extração de factos, questionário adaptativo, modelo rastreado (níveis/elementos), esboços e nota de estudo. Motor Eurocódigos bloqueado por honestidade."),
            ("Análise de documentos", "Leitura de Excel/PDF/digitalizações com OCR por IA, origem célula/página, controlos aritméticos determinísticos, reconciliação CCTP↔orçamento, memória de correções."),
            ("Cálculo de escadas", "Escadas retas, de quarto/meio-volta e helicoidais conformes às DTU, otimização, análise de betão, vista 3D interativa, dossier PDF cotado, escada→orçamento."),
            ("Análise de plantas Pro", "Processamento de ficheiros CAD pesados (DWG/RVT/IFC) via Autodesk APS, para profissionais."),
            ("Resolver um problema", "Diagnóstico de construção assistido por IA a partir de uma descrição e de fotos (humidade, fissuras…)."),
            ("RH & registo de ponto", "Registo de ponto geolocalizado (entrada/saída), folhas de horas, selfie, notas de obra para as equipas no terreno."),
            ("Espaço Empresa & papéis", "Organização multiutilizador (owner, admin, chefe de obra, contabilista, membro, operário), permissões detalhadas, KPIs, marca partilhada."),
            ("Admin & pilotagem", "Back-office completo: gestão de utilizadores, 2FA, Revenue Cockpit, acompanhamento de despesas e teto de exploração controlado."),
            ("Growth & páginas públicas", "Landings Pro e Particulares, vídeo de demonstração narrado, clips por função, SEO, página vitrina pública por empresa."),
        ],
        "apps": [
            ("ConstruPilot Empresa", "Chefes de empresa, artesãos, PME da construção",
             "A app de terreno do profissional: crie os seus orçamentos por voz, orce sobre a planta, acompanhe as obras e fature sem voltar a introduzir dados.",
             ["Orçamentos & faturas conformes (IVA, retenção de garantia)", "Medição automática sobre planta PDF",
              "Ditado por voz: orçamentos, reservas, mensagens", "Dossier de obra contínuo (fotos, relatórios)",
              "Espaço cliente integrado"]),
            ("ConstruPilot Colaborador", "Trabalhadores, operários e subcontratados",
             "A app das equipas no terreno: marque as suas horas, envie as suas fotos, assinale reservas e consulte as tarefas do dia — tudo chega ao escritório.",
             ["Registo de ponto geolocalizado (opt-in)", "Fotos e relatórios de obra",
              "Sinalização de reservas", "Tarefas do dia"]),
            ("ConstruPilot Particulares", "Donos de obra / particulares",
             "Estime o preço das suas obras em minutos, compare os orçamentos recebidos e acompanhe a sua obra com total transparência.",
             ["Estimativa de custo das obras", "Comparação de orçamentos",
              "Acompanhamento de obra (fotos, relatórios)", "Acesso aos apoios à renovação"]),
        ],
    },
    "en": {
        "file": "construpilot-en.pdf",
        "cover_title": "ConstruPilot",
        "cover_tag": "The deterministic construction SaaS — 0% hallucination",
        "cover_sub": "Full dossier · foundations A to Z · Web Summit 2026 · Europe launch",
        "ready": "ALREADY LIVE · READY TO LAUNCH ACROSS EUROPE (EN / FR / PT)",
        "s_mission": "Mission & founding principles",
        "mission_intro": "ConstruPilot is a SaaS platform for construction professionals and their clients. Its foundation is a "
                         "simple promise: zero hallucination. All maths — takeoff, quotes, invoicing, energy and engineering — "
                         "is deterministic, traceable and verifiable. AI is used only to read and assist; never to invent a number.",
        "principles": [
            "0% hallucination: all calculations are deterministic, never AI-generated.",
            "Full traceability: every data point carries its provenance (measurement / document / test) and status.",
            "AI reads (OCR, fact extraction) but never computes.",
            "Native regulatory compliance (Factur-X, energy/ADEME, building codes).",
            "No public claim without proof (claims ledger).",
            "Controlled operating budget with cost alerts.",
            "Multilingual and multi-VAT, ready for Europe (EN / FR / PT).",
        ],
        "s_found": "Technical foundations",
        "stack": [
            "Frontend: React (CRA), shadcn/ui, Tailwind CSS; mobile apps via Capacitor (iOS + Android).",
            "Backend: FastAPI (Python) + MongoDB; rate limiting (SlowAPI).",
            "Security: HttpOnly cookies, JWT, Google sign-in, admin 2FA, brute-force protection.",
            "AI (read-only): Emergent universal key — OpenAI, Anthropic Claude, Google Gemini, Whisper (STT) and text-to-speech.",
            "Deterministic PDF generation (ReportLab); Factur-X PDF/A-3 + CII XML.",
            "Integrations: Stripe (payments), Autodesk APS (CAD), ADEME/France Rénov' (energy & grants), facturxapi (EN 16931), Perplexity (prices), ElevenLabs (voice), Resend (emails), Emergent object storage.",
        ],
        "s_modules": "Modules, from A to Z",
        "s_apps": "The 3 mobile apps",
        "s_compliance": "Compliance & regulation",
        "compliance": [
            "Factur-X e-invoicing, certified EN 16931 profile (PDF/A-3 + CII XML).",
            "Official ADEME energy data (open-data certificates) and France Rénov' grants.",
            "Building-code-compliant calculations (staircases, concrete).",
            "GDPR: account and data deletion in-app and via dedicated URL.",
            "Apple/Google store compliance (privacy labels, Data Safety).",
        ],
        "s_market": "Market & Europe launch",
        "market": "ConstruPilot is operational and already live. The goal is a Europe-wide launch — starting with France and "
                  "Portugal — powered by a multilingual (EN/FR/PT) and multi-VAT architecture, and an e-invoicing engine "
                  "compliant with the European EN 16931 standard, ready for mandatory e-invoicing.",
        "contact": "Contact: Martinho · ConstruPilot — ready for a live demo.",
        "col_mod": "Module", "col_desc": "Description",
        "lbl_audience": "Audience",
        "modules": [
            ("Construction AI assistant", "Claude / OpenAI / Gemini (Emergent key): voice commands, web search for material prices, voice pricing — AI assists but never computes takeoff/pricing."),
            ("Plan takeoff", "Imports PDF/DXF/images/ZIP, scale calibration, drawing of areas, lengths and volumes, opening deductions, families and subtotals, comparable versions."),
            ("Multi-level projects", "Groups several plans into levels (Foundations, ground floor, 1st floor…) and consolidates takeoff + pricing per level and for the whole project, in a single PDF file."),
            ("Quote editor", "Deterministic trade-by-trade pricing (16 works + custom items), editable unit prices, multi-rate VAT, discounts, deposit, payment schedule, professional PDF."),
            ("Factur-X invoices", "Hybrid PDF/A-3 + CII XML e-invoices, BASIC and certified EN 16931 profiles, ready for mandatory e-invoicing."),
            ("Site tracking", "Continuous site file: photos, reports, before/after comparator, handover minutes, reservation clearing — all timestamped and traceable."),
            ("Client space (portal)", "Strictly isolated guest portal: the client follows the project, views quotes and invoices, accepts and signs online (OTP, automatic deposit)."),
            ("RenoPilot — energy renovation", "Imports official ADEME energy certificates, audit scenarios, grants (MaPrimeRénov'/CEE/eco-loan) via the France Rénov' API, remaining cost per action, PDF report."),
            ("StructuroPilot — structural engineering", "Autonomous study from a description: fact extraction, adaptive questionnaire, traced model (levels/elements), sketches and a study note. Eurocode engine locked by design."),
            ("Document analysis", "Reads Excel/PDF/scans with AI OCR, cell/page provenance, deterministic arithmetic checks, spec-to-quote reconciliation, correction memory."),
            ("Staircase calculation", "Straight, quarter/half-turn and helical stairs compliant with building codes, optimization, concrete analysis, interactive 3D view, dimensioned PDF file, stair→quote."),
            ("Pro plan analysis", "Processing of heavy CAD files (DWG/RVT/IFC) via Autodesk APS, for professionals."),
            ("Solve a problem", "AI-assisted construction diagnosis from a description and photos (damp, cracks…)."),
            ("HR & site time tracking", "Geolocated clock-in/out, timesheets, selfie, site notes for field teams."),
            ("Company space & roles", "Multi-user organization (owner, admin, site manager, accountant, member, worker), fine-grained permissions, KPIs, shared branding."),
            ("Admin & steering", "Full back-office: user management, 2FA, Revenue Cockpit, expense tracking and a controlled operating budget."),
            ("Growth & public pages", "Pro and consumer landing pages, narrated demo video, per-feature clips, SEO, public company showcase page."),
        ],
        "apps": [
            ("ConstruPilot Business", "Business owners, tradespeople, construction SMEs",
             "The professional's field app: create quotes by voice, price on plans, track your sites and invoice without re-entering data.",
             ["Compliant quotes & invoices (VAT, retention)", "Automatic takeoff on PDF plans",
              "Voice dictation: quotes, reservations, messages", "Continuous site file (photos, reports)",
              "Built-in client space"]),
            ("ConstruPilot Collaborator", "Employees, journeymen and subcontractors",
             "The field-team app: clock your hours, send your photos, flag reservations and check your daily tasks — everything flows back to the office.",
             ["Geolocated clock-in/out (opt-in)", "Site photos and reports",
              "Reservation flagging", "Daily tasks"]),
            ("ConstruPilot Homeowners", "Project owners / homeowners",
             "Estimate the cost of your works in minutes, compare the quotes you receive and follow your project with full transparency.",
             ["Costed estimate of works", "Quote comparison",
              "Site tracking (photos, reports)", "Access to renovation grants"]),
        ],
    },
}


def _styles():
    ss = getSampleStyleSheet()
    ss.add(ParagraphStyle("Cover", fontName="Helvetica-Bold", fontSize=46, leading=50,
                          textColor=colors.white, alignment=TA_CENTER))
    ss.add(ParagraphStyle("CoverTag", fontName="Helvetica", fontSize=14, leading=18,
                          textColor=ACCENT, alignment=TA_CENTER))
    ss.add(ParagraphStyle("CoverSub", fontName="Helvetica", fontSize=9.5, leading=14,
                          textColor=colors.HexColor("#cbd5e1"), alignment=TA_CENTER))
    ss.add(ParagraphStyle("Ready", fontName="Helvetica-Bold", fontSize=10, leading=14,
                          textColor=colors.white, alignment=TA_CENTER, backColor=BRAND, borderPadding=6))
    ss.add(ParagraphStyle("H1b", fontName="Helvetica-Bold", fontSize=16, leading=20,
                          textColor=BRAND, spaceBefore=12, spaceAfter=6))
    ss.add(ParagraphStyle("Bodyb", fontName="Helvetica", fontSize=10, leading=14, textColor=INK, spaceAfter=4))
    ss.add(ParagraphStyle("ModName", fontName="Helvetica-Bold", fontSize=10, leading=12.5, textColor=BRAND))
    ss.add(ParagraphStyle("ModDesc", fontName="Helvetica", fontSize=8.6, leading=11, textColor=INK))
    ss.add(ParagraphStyle("BulletX", fontName="Helvetica", fontSize=9.5, leading=13, textColor=INK))
    ss.add(ParagraphStyle("AppName", fontName="Helvetica-Bold", fontSize=12, leading=15, textColor=BRAND, spaceBefore=6))
    ss.add(ParagraphStyle("AppAud", fontName="Helvetica-Oblique", fontSize=8.5, leading=11, textColor=ACCENT))
    ss.add(ParagraphStyle("AppFeat", fontName="Helvetica", fontSize=9, leading=12, textColor=INK))
    return ss


def _cover_bg(canvas, doc):
    canvas.saveState()
    canvas.setFillColor(DARK)
    canvas.rect(0, 0, A4[0], A4[1], fill=1, stroke=0)
    canvas.setStrokeColor(colors.HexColor("#1b2330"))
    canvas.setLineWidth(0.4)
    for x in range(0, int(A4[0]), 24):
        canvas.line(x, 0, x, A4[1])
    for y in range(0, int(A4[1]), 24):
        canvas.line(0, y, A4[0], y)
    canvas.restoreState()


def _bullets(ss, items):
    return ListFlowable([ListItem(Paragraph(x, ss["BulletX"]), leftIndent=6) for x in items],
                        bulletType="bullet", start="•")


def build(lang):
    c = CONTENT[lang]
    ss = _styles()
    path = os.path.join(OUT_DIR, c["file"])
    doc = SimpleDocTemplate(path, pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm,
                            topMargin=18 * mm, bottomMargin=16 * mm, title=f"ConstruPilot — {lang.upper()}")

    story = [Spacer(1, 70 * mm),
             Paragraph(c["cover_title"], ss["Cover"]),
             Spacer(1, 6 * mm),
             Paragraph(c["cover_tag"], ss["CoverTag"]),
             Spacer(1, 40 * mm),
             Paragraph(c["ready"], ss["Ready"]),
             Spacer(1, 10 * mm),
             Paragraph(c["cover_sub"], ss["CoverSub"]),
             PageBreak()]

    # Mission & principes
    story.append(Paragraph(c["s_mission"], ss["H1b"]))
    story.append(Paragraph(c["mission_intro"], ss["Bodyb"]))
    story.append(Spacer(1, 2 * mm))
    story.append(_bullets(ss, c["principles"]))
    story.append(HRFlowable(width="100%", color=LINE, spaceBefore=8, spaceAfter=6))

    # Fondations techniques
    story.append(Paragraph(c["s_found"], ss["H1b"]))
    story.append(_bullets(ss, c["stack"]))

    # Modules A-Z
    story.append(PageBreak())
    story.append(Paragraph(c["s_modules"], ss["H1b"]))
    rows = [[Paragraph(f"<b>{c['col_mod']}</b>", ss["ModDesc"]), Paragraph(f"<b>{c['col_desc']}</b>", ss["ModDesc"])]]
    for name, desc in c["modules"]:
        rows.append([Paragraph(name, ss["ModName"]), Paragraph(desc, ss["ModDesc"])])
    t = Table(rows, colWidths=[46 * mm, 128 * mm], repeatRows=1)
    t.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LINEBELOW", (0, 0), (-1, -1), 0.3, LINE),
        ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#eaf2f1")),
        ("BACKGROUND", (0, 1), (0, -1), colors.HexColor("#f4f8f7")),
    ]))
    story.append(t)

    # Apps mobiles
    story.append(PageBreak())
    story.append(Paragraph(c["s_apps"], ss["H1b"]))
    for name, audience, desc, feats in c["apps"]:
        story.append(Paragraph(name, ss["AppName"]))
        story.append(Paragraph(f"{c['lbl_audience']} : {audience}", ss["AppAud"]))
        story.append(Paragraph(desc, ss["Bodyb"]))
        story.append(ListFlowable([ListItem(Paragraph(f, ss["AppFeat"]), leftIndent=6) for f in feats],
                                  bulletType="bullet", start="•"))
        story.append(HRFlowable(width="100%", color=LINE, spaceBefore=6, spaceAfter=4))

    # Conformité
    story.append(Paragraph(c["s_compliance"], ss["H1b"]))
    story.append(_bullets(ss, c["compliance"]))

    # Marché & lancement
    story.append(Spacer(1, 4 * mm))
    story.append(Paragraph(c["s_market"], ss["H1b"]))
    story.append(Paragraph(c["market"], ss["Bodyb"]))
    story.append(Spacer(1, 6 * mm))
    story.append(HRFlowable(width="100%", color=BRAND, thickness=1.2, spaceBefore=6, spaceAfter=6))
    story.append(Paragraph(f"<b>{c['contact']}</b>", ss["Bodyb"]))

    def _later(canvas, d):
        canvas.saveState()
        canvas.setStrokeColor(LINE); canvas.setLineWidth(0.3)
        canvas.line(18 * mm, 12 * mm, A4[0] - 18 * mm, 12 * mm)
        canvas.setFillColor(MUTED); canvas.setFont("Helvetica", 7)
        canvas.drawString(18 * mm, 8 * mm, "ConstruPilot · construction SaaS · 0% hallucination")
        canvas.drawRightString(A4[0] - 18 * mm, 8 * mm, f"{d.page}")
        canvas.restoreState()

    doc.build(story, onFirstPage=_cover_bg, onLaterPages=_later)
    print(f"[ok] {path}")


if __name__ == "__main__":
    os.makedirs(OUT_DIR, exist_ok=True)
    for lang in ("pt", "fr", "en"):
        build(lang)
