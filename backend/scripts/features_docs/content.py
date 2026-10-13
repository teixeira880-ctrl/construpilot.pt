"""Inventaire complet des fonctionnalités ConstruPilot (FR) — source unique pour PDF & PPTX."""

BRAND = {
    "name": "ConstruPilot",
    "tagline": "Estimez. Comparez. Construisez.",
    "site": "construpilot.fr · construpilot.pt",
    "dark": "#04120a", "green": "#16211c", "mid": "#24352d",
    "lime": "#a3e635", "amber": "#f59e0b", "soft": "#eaf3ee", "grey": "#8ba396",
    "logo": "/app/frontend/public/construpilot-logo.png",
}

INTRO = (
    "ConstruPilot est la plateforme SaaS BTP tout-en-un : estimation de travaux par IA, "
    "lecture de plans DWG/DXF/PDF, devis & factures avec marges, approvisionnement, "
    "prospection de chantiers, blog SEO et bien plus. Une seule application pour les "
    "particuliers qui préparent leurs travaux et pour les artisans, PME et bureaux d'études "
    "qui chiffrent, vendent et pilotent leurs chantiers."
)

TIERS = [
    {
        "key": "particulier", "name": "Particuliers", "price": "Gratuit",
        "sub": "0 € — sans engagement · 2 projets actifs · 3 estimations détaillées / mois",
        "audience": "Propriétaires, futurs acquéreurs, bricoleurs",
        "pitch": "Tout pour préparer un projet de travaux : estimer, comparer, comprendre — en 30 secondes.",
        "sections": [
            ("Estimation & chiffrage", [
                "Estimateur de travaux : rénovation, construction maison, extension, piscine… par type de projet, état du bien et région (coefficients de marché 2026, 16 districts PT)",
                "3 gammes de prix — Économique / Standard / Premium — matériaux + main-d'œuvre",
                "Détail par corps de métier, planning des phases, export PDF (avec TVA 6 % / 23 % au Portugal)",
                "Smart Project : décrivez « rénover salle de bain 8 m² » ou dictez à la voix → lots, matériaux et budget générés par l'IA",
                "Panier d'achats matériaux optimisé (parpaing/brique, mortier, colle, enduit de façade…)",
                "Comparatif des offres et des prix, ordres de grandeur €/m² par ville (pages locales « devis travaux »)",
            ]),
            ("Outils IA", [
                "Analyse de photo : envoyez une photo d'une pièce ou d'un défaut, l'IA propose des pistes et des priorités",
                "Coach IA travaux : un assistant qui répond à vos questions chantier en français (conseils limités en gratuit)",
                "DIY Advisor : faisable soi-même ou par un pro ? Sécurité d'abord (gaz, électricité, murs porteurs → orientation vers un professionnel)",
            ]),
            ("Calculateurs & prix", [
                "Calculateurs de matériaux : peinture, carrelage (colle, joint, croisillons, natte, profilés), béton, maçonnerie (parpaing/brique, mortier, colle, mousse PU, enduit), surfaces, volumes",
                "Fiches de calcul partageables par lien",
                "Recherche de prix : aperçu de la bibliothèque de 322 ouvrages chiffrés (prix bas, médian, haut)",
            ]),
            ("Trouver un pro & compte", [
                "Demande de devis auprès de pros vérifiés (K-bis, SIRET, décennale) — profil public « Pro vérifié » et avis clients",
                "Compte sécurisé : e-mail ou Google Sign-In, double authentification par e-mail, appareils connectés, export de mes données",
                "Parrainage avec récompenses, application mobile (PWA) installable",
                "Interface FR / PT-PT, blog et newsletter conseils travaux",
            ]),
        ],
    },
    {
        "key": "pass", "name": "Project Pass", "price": "50 € une fois",
        "sub": "Paiement unique · 1 projet complet · valable 90 jours · sans abonnement",
        "audience": "Une rénovation ponctuelle",
        "pitch": "Un projet complet, débloqué en une fois — idéal pour une rénovation ponctuelle.",
        "sections": [
            ("Inclus dans le Pass", [
                "Estimation complète avec détail par corps de métier",
                "Matériaux, quantités et prix + panier optimisé",
                "DIY Advisor et IA avancée dédiés à ce projet",
                "Planning + budget, PDF professionnel",
                "Analyse (scanner) de 3 devis d'artisans : explication, vérification des montants",
                "Accès Plan 2D + 3 rendus 3D IA offerts",
            ]),
        ],
    },
    {
        "key": "premium", "name": "Premium", "price": "19 € / mois",
        "sub": "ou 190 € / an (−17 %) · 7 jours d'essai · projets et estimations illimités",
        "audience": "Particuliers multi-projets, investisseurs, bailleurs",
        "pitch": "Le plus populaire : projets illimités, IA complète et comparaison avancée des prix.",
        "sections": [
            ("Tout Particuliers, sans limite", [
                "Projets illimités, estimations détaillées illimitées",
                "ConstruPilot AI Advisor complet (coach IA sans limite)",
                "Analyse de devis illimitée (scanner de devis PDF : l'IA explique et vérifie les montants)",
            ]),
            ("Prix & budget", [
                "Comparaison avancée des prix et historique des prix",
                "Alertes prix, optimisation du panier",
                "Budget intelligent + planning, suivi des dépenses",
                "Recommandations personnalisées, conseils DIY avancés",
                "Export PDF de tous les documents",
            ]),
            ("3D & visualisation (crédits)", [
                "Rendu 3D IA photoréaliste (5 €), vidéo 3D (10 €), maquette 3D interactive navigable (5 €), partage par lien",
            ]),
        ],
    },
    {
        "key": "pro", "name": "Pro", "price": "149 € HT / mois",
        "sub": "ou 1 570 € / an · 7 jours d'essai · 1 utilisateur · projets illimités",
        "audience": "Artisans, indépendants, TPE du bâtiment",
        "pitch": "Chiffrez à partir d'un plan, d'un CCTP, d'une photo ou de la voix, vendez avec vos marges, faites signer en ligne.",
        "sections": [
            ("Devis & factures", [
                "Éditeur de devis : lots, lignes, TVA 0 / 5,5 / 10 / 20 % (PT : 0 / 6 / 13 / 23 %, règle IVA 6 % réhabilitation), remises, notes, auto-sauvegarde",
                "Bibliothèque de prix partagée (322 ouvrages FR, 3 gammes) + ma bibliothèque entreprise (import Excel / BPU / anciens devis PDF), ouvrages composés, suggestions IA",
                "Devis depuis : texte ou dictée vocale (Whisper), photo / vidéo du chantier, plan (métré → devis), CCTP / DPGF (IA + OCR des PDF scannés, multi-lots, mémoire des lots à garder)",
                "Devis multi-plans consolidé (gros œuvre, maison, ferraillage) avec sous-traitance TVA 0 %",
                "PDF au logo de l'entreprise (couleurs, SIRET, TVA, RIB ; NIF / Alvará au Portugal), envoi par e-mail via votre SMTP ou ConstruPilot, pièces jointes, modèles de messages, suivi d'ouverture, relances",
                "Signature électronique en ligne (signature dessinée) + acompte Stripe à la signature (30 % paramétrable)",
                "Option Facturation (5 €/mois) : factures, acompte, situations, solde, décompte général, avoirs, suivi des paiements, facturation électronique Factur-X",
            ]),
            ("Marges & rentabilité", [
                "Coût de revient par ligne, marge € et % par ligne et par lot, lignes « à perte » signalées",
                "Marge cible globale et par lot (calcul automatique du prix de vente), alerte marge faible avant envoi",
                "PDF interne « ne pas transmettre au client » : coûts, marges par lot, synthèse",
                "Analyse de rentabilité, IA professionnelle",
            ]),
            ("Plans & métré", [
                "Import DWG (conversion automatique) / DXF / PDF / images : rendu fidèle (cotes, textes, cartouche), calibration automatique de l'échelle",
                "Détection IA des pièces, murs, ouvertures, poteaux, poutres, dalles ; métré structure béton par calques (murs, planchers, escaliers, poutres, poteaux → m³, coffrage, aciers, €)",
                "Outils de mesure (distance, surface polygone, historique), plein écran, contraste, comparaison de 2 versions de plan, assistant IA d'édition en langage naturel",
                "Mesure sur photo, estimation par pièce (peinture, sol, plomberie, maçonnerie…) avec choix du bloc et enduit",
                "Étude Permis de Construire gros œuvre : estimation par niveau, planning Gantt, météo, comparateur négoces, bon de commande, envoi et signature client, relances automatiques",
            ]),
            ("Approvisionnement & fournisseurs", [
                "Ferraillage / acier : lecture IA des plans → bordereau HA6…HA32, treillis, tonnage, quantités commandables (pertes, longueur de barre)",
                "Étanchéité (toiture-terrasse), toiture (tuiles, ardoises, bac acier…), VRD / réseaux et tranchées",
                "Fournisseurs (agence, n° client, catégories), export CSV, bons de commande, fusion multi-plans, statuts brouillon / envoyé / confirmé",
                "Chiffrage DPGF automatique : vos prix d'abord, l'IA en repli",
            ]),
            ("Clients, leads & réputation", [
                "CRM clients et projets, suivi des devis (vus, signés, relances), portail client",
                "Mes demandes : leads de particuliers avec scoring, notifications, e-mail",
                "Avis clients collectés par lien, badge « Pro vérifié » (KYC K-bis + SIRET + décennale)",
                "Radar Chantiers, rendus 3D, accès API développeurs (voir pages suivantes)",
            ]),
        ],
    },
    {
        "key": "business", "name": "Pro Business", "price": "249 € HT / mois",
        "sub": "ou 2 490 € / an · 7 jours d'essai · 5 utilisateurs inclus · Facturation & Factur-X incluses",
        "audience": "PME du bâtiment, entreprises générales, bureaux d'études",
        "pitch": "Tout Pro + équipes, RH & pointage, suivi de chantier avec coûts réels, reporting et automatisations.",
        "sections": [
            ("Équipe & organisation", [
                "Jusqu'à 5 utilisateurs, rôles (admin, collaborateur, lecture seule), invitations par lien",
                "Espace Entreprise : identité, logo, SMTP, RIB, paramètres Factur-X, branding des documents",
                "Portail Pro et rapport hebdomadaire automatique",
            ]),
            ("RH, pointage & chantier", [
                "Module RH : salariés, contrats, absences ; application ouvrier de pointage sur mobile",
                "Suivi de chantier : avancement, photos de chantier, coûts réels vs devis, partage au client",
                "Situations de travaux, facture de solde, décompte général — Option Facturation incluse",
            ]),
            ("Pilotage", [
                "Planning + Gantt, reporting & analytics, rentabilité par chantier",
                "Automatisations : relances devis / acomptes, notifications d'ouverture, rapports",
                "Plan 2D takeoff professionnel, rendu 3D interactif + vidéo 3D inclus",
            ]),
        ],
    },
]

TRANSVERSAL = [
    {
        "key": "radar", "name": "Radar Chantiers & prospection",
        "pitch": "Trouvez les chantiers avant vos concurrents et prospectez en 1 clic (Pro & Pro Business).",
        "sections": [
            ("Détection d'opportunités", [
                "Carte des permis de construire (données SITADEL) autour de votre base, filtrés par vos métiers et votre rayon",
                "Profil Radar : métiers de l'entreprise, zone repositionnable sur la carte, KPIs",
            ]),
            ("Courrier de prospection", [
                "Courrier PDF personnalisé (en-tête entreprise, référence du permis, fourchette de prix, RGPD) + QR code",
                "Assistant IA de rédaction : ton formel / chaleureux / direct / commercial, longueur au choix",
                "Envoi postal réel depuis l'app (Merci Facteur) : lettre simple, suivie ou LRAR — dès ≈ 2,26 € TTC, suivi de distribution",
            ]),
            ("Capture & suivi", [
                "Landing publique dédiée par courrier (QR / lien) → le prospect laisse ses coordonnées",
                "Lead créé automatiquement dans « Mes demandes », notification + e-mail, anti-spam et anti-doublons",
                "Suivi de campagne : ouvertures, réponses, taux par courrier",
            ]),
        ],
    },
    {
        "key": "blog", "name": "Blog, SEO & newsletter",
        "pitch": "Un blog conseils travaux FR & PT alimenté automatiquement, optimisé pour Google.",
        "sections": [
            ("Contenu", [
                "Blog natif : articles FR (prix, aides, réglementation, méthodes) et PT-PT (licenciamento, IVA 6 %, custos por distrito)",
                "Génération automatique d'articles SEO (BabyLoveGrowth) : synchronisation toutes les 2 h + webhook temps réel, image de couverture, FAQ structurée",
                "« À lire aussi » (articles liés) et maillage interne vers l'estimateur, les calculateurs et les prix",
            ]),
            ("Référencement", [
                "Sitemap dynamique (index + pages + articles), JSON-LD BlogPosting / FAQ, Open Graph, robots.txt",
                "Pages locales « Devis travaux {ville} », landings /particuliers, /metre, /portugal, /investisseurs, vidéos de démonstration",
            ]),
            ("Newsletter", [
                "Inscription sous chaque article et sur le blog, e-mail de bienvenue, notification à chaque nouvel article, désinscription 1 clic",
                "Statistiques d'abonnés dans l'administration",
            ]),
        ],
    },
    {
        "key": "growth", "name": "Acquisition, e-mailing & fidélisation",
        "pitch": "Les outils marketing intégrés qui transforment les visiteurs en abonnés.",
        "sections": [
            ("E-mailing", [
                "Campagnes e-mail (Resend) avec suivi des envois et des échecs",
                "Relances automatiques J+3 et J+10 des comptes gratuits (Pro 149 € / Premium 19 €), code promo hebdomadaire −20 % × 3 mois appliqué automatiquement au paiement",
                "Suivi de conversion par semaine : envois → abonnements",
            ]),
            ("Croissance", [
                "Essai gratuit 7 jours, codes promo Stripe, paiement mensuel ou annuel",
                "Parrainage et affiliation avec récompenses, page « Passez Pro » pour les particuliers",
                "Marketplace de pros vérifiés (activable), avis clients publics",
            ]),
        ],
    },
    {
        "key": "addons", "name": "Options, API & Entreprise",
        "pitch": "Complétez votre offre à l'unité ou intégrez le moteur ConstruPilot dans vos outils.",
        "sections": [
            ("Options à l'unité", [
                "Option Facturation : 5 €/mois (incluse Pro Business)",
                "Rendu 3D IA (image) : 5 € · Vidéo 3D : 10 € · Maquette 3D interactive : 5 €",
            ]),
            ("API commerciale", [
                "API Starter 99 €/mois : 1 000 appels, Estimation Engine, Material Calculators, Price Intelligence (démo)",
                "API Business 299 €/mois : 10 000 appels, AI Renovation Advisor, webhooks, support prioritaire",
                "API Scale 999 €/mois : 100 000 appels, SLA 99,9 %, SSO, endpoints dédiés, account manager",
                "Espace développeurs : clés API, documentation, portail fournisseur",
            ]),
            ("Enterprise & sécurité", [
                "Offre Enterprise sur devis (volumes, SSO, marque blanche en préparation)",
                "Sécurité : 2FA e-mail, alerte de connexion admin, appareils connectés, stockage privé des documents KYC, RGPD",
            ]),
        ],
    },
    {
        "key": "admin", "name": "Administration ConstruPilot",
        "pitch": "Le back-office complet pour piloter la plateforme.",
        "sections": [
            ("Pilotage", [
                "Utilisateurs, abonnements et revenus, synchronisation des plans Stripe, désactivation 2FA",
                "Validation KYC des pros (K-bis, décennale, SIRET) : approuver / refuser avec motif",
            ]),
            ("Données & contenu", [
                "Bibliothèque partagée : import Excel (fusion des manquants, actualisation des prix), export Excel, FR / PT",
                "Configuration maçonnerie (ratios, blocs, prix), import SITADEL (CSV géocodé), SEO / Blog (synchro, webhook, suppression)",
                "Campagnes e-mail : aperçus, envoi J+3 / J+10, statistiques de conversion",
            ]),
        ],
    },
]

# Comparatif : (fonction, Particulier, Premium, Pro, Pro Business)
COMPARE = [
    ("Estimateur 3 gammes + calculateurs", "✓ (3/mois)", "Illimité", "Illimité", "Illimité"),
    ("Smart Project, photo IA, Coach IA", "Limité", "✓", "✓", "✓"),
    ("Scanner / analyse de devis", "—", "Illimité", "✓", "✓"),
    ("Historique & alertes prix, suivi dépenses", "—", "✓", "✓", "✓"),
    ("Rendu 3D / vidéo / maquette", "—", "Crédits", "Crédits", "Inclus"),
    ("Éditeur de devis + bibliothèque 322 ouvrages", "—", "—", "✓", "✓"),
    ("Marges par lot, PDF interne, alerte marge", "—", "—", "✓", "✓"),
    ("Devis depuis plan / CCTP / voix / photo", "—", "—", "✓", "✓"),
    ("Signature en ligne + acompte Stripe", "—", "—", "✓", "✓"),
    ("Factures, situations, Factur-X", "—", "—", "Option 5 €", "Inclus"),
    ("Plans DWG/DXF/PDF, métré béton, étude PC", "—", "—", "✓", "✓"),
    ("Approvisionnement (acier, toiture, VRD)", "—", "—", "✓", "✓"),
    ("Radar Chantiers + courrier postal", "—", "—", "✓", "✓"),
    ("CRM clients, leads, avis, Pro vérifié", "—", "—", "✓", "✓"),
    ("Équipe (5 utilisateurs), rôles", "—", "—", "1 utilisateur", "✓"),
    ("RH, pointage, suivi chantier coûts réels", "—", "—", "—", "✓"),
    ("Gantt, reporting, automatisations", "—", "—", "—", "✓"),
    ("Blog, newsletter, FR / PT, PWA", "✓", "✓", "✓", "✓"),
]

HIGHLIGHTS = {
    "particulier": [
        "Estimateur 3 gammes (éco / standard / premium) par type de projet et région",
        "Smart Project : description ou dictée vocale → lots, matériaux, budget IA",
        "Analyse photo IA, Coach IA travaux, DIY Advisor",
        "Calculateurs matériaux (peinture, carrelage, béton, maçonnerie…)",
        "Aperçu des prix : 322 ouvrages chiffrés bas / médian / haut",
        "Demande de devis à des pros vérifiés, avis clients",
        "Compte sécurisé (Google, 2FA), PWA mobile, FR / PT, blog & newsletter",
    ],
    "pass": [
        "Estimation complète, détail par corps de métier",
        "Matériaux, quantités, prix et panier optimisé",
        "Planning + budget, PDF professionnel",
        "Analyse de 3 devis d'artisans par l'IA",
        "Plan 2D + 3 rendus 3D offerts",
        "Valable 90 jours, sans abonnement",
    ],
    "premium": [
        "Projets et estimations illimités, AI Advisor complet",
        "Scanner de devis illimité : l'IA explique et vérifie",
        "Comparaison avancée, historique et alertes prix",
        "Budget intelligent, planning, suivi des dépenses",
        "Recommandations personnalisées, conseils DIY avancés",
        "Rendus 3D, vidéo 3D et maquette interactive (crédits)",
    ],
    "pro": [
        "Éditeur de devis + bibliothèque 322 ouvrages + votre bibliothèque",
        "Devis depuis plan, CCTP (IA + OCR), photo, vidéo ou voix",
        "Marges par ligne et par lot, marge cible, alerte marge faible, PDF interne",
        "PDF à votre logo, envoi e-mail, signature en ligne, acompte Stripe",
        "Plans DWG / DXF / PDF : métré béton, escaliers, planchers, étude Permis de Construire",
        "Approvisionnement : acier, étanchéité, toiture, VRD, bons de commande",
        "Radar Chantiers : permis de construire, courrier + QR, envoi postal",
        "CRM clients, leads, avis, badge Pro vérifié",
    ],
    "business": [
        "Tout Pro + 5 utilisateurs, rôles et invitations",
        "Facturation & Factur-X incluses : acompte, situations, solde",
        "RH, pointage mobile des ouvriers",
        "Suivi de chantier : photos, coûts réels vs devis, partage client",
        "Planning Gantt, reporting, rentabilité par chantier",
        "Automatisations (relances, rapports), rendu 3D interactif inclus",
    ],
}

CONTACT = [
    "Site : construpilot.fr — Portugal : construpilot.pt",
    "Essai gratuit 7 jours sur toutes les offres payantes, sans carte pour l'offre Particuliers",
    "Tarifs HT pour les offres Pro · TTC pour les particuliers · résiliable à tout moment",
]
