"""Catalogue du rédacteur CCTP : lots d'un DCE, documents de référence, prescriptions et ouvrages types.

Base déterministe, rédigée une fois et relue : c'est elle qui garantit qu'un CCTP ConstruPilot reste
juste même sans IA. L'IA (cctp_redacteur) adapte ces articles au projet, mais ne peut citer que les
documents listés ici (liste blanche vérifiée après rédaction).

Structure d'un CCTP de lot (modèle d'économiste, cf. « Lot n°6 Plâtrerie ») :
  N.1 Prescriptions particulières
      N.1.1 Généralités (connaissance du projet, des lieux, documents de référence, échantillons…)
      N.1.2 Préconisations de mise en œuvre (propres au lot)
  N.2 … N.k Description des ouvrages, par chapitre : article (description + localisation)
      puis variantes chiffrables (N.2.1.1.1 …), qui deviennent les lignes du cadre de DPGF.
"""
from __future__ import annotations

# ---------------------------------------------------------------------------------------------
# Prescriptions communes à tous les lots (N.1.1)
# ---------------------------------------------------------------------------------------------
COMMUNES: list[tuple[str, str]] = [
    ("Connaissance du projet",
     "Lors de l'étude du projet et avant la remise de son offre, l'entrepreneur doit prendre connaissance des plans, "
     "des lieux et des cahiers des charges des autres lots, notamment des dispositions communes à tous les lots, et "
     "tenir compte des exigences de l'ensemble des pièces constituant le marché de travaux. Les matériaux employés "
     "seront de premier choix et mis en œuvre suivant les règles de l'art et la réglementation applicable au moment "
     "de l'exécution des travaux. L'entrepreneur devra la livraison des ouvrages et installations en parfait état "
     "d'achèvement et de service."),
    ("Connaissance des lieux",
     "L'entrepreneur est réputé avoir pris connaissance des lieux et de toutes les conditions pouvant avoir une "
     "influence sur l'exécution, sur la conception des détails, sur la qualité et les prix des ouvrages à réaliser. "
     "Cette prise de connaissance concerne notamment les possibilités d'accès des engins, camions et équipements, les "
     "possibilités de stockage et d'installation de chantier, ainsi que les servitudes qui peuvent y être attachées. "
     "L'entrepreneur ne pourra arguer d'aucune ignorance à ce sujet pour prétendre à des suppléments de prix ou à des "
     "prolongations de délais."),
    ("Étendue des prestations",
     "Les prix de l'entrepreneur comprennent implicitement la fourniture, le transport, la manutention, la mise en "
     "œuvre et le réglage de tous les matériaux et accessoires nécessaires au complet et parfait achèvement des "
     "ouvrages décrits, y compris toutes coupes, ajustages, façons, scellements, fixations et sujétions, même si ces "
     "prestations ne sont pas explicitement mentionnées au présent document. La description des ouvrages n'a pas un "
     "caractère limitatif : l'entrepreneur devra signaler par écrit, avant la remise de son offre, toute omission ou "
     "contradiction relevée entre les pièces du dossier."),
    ("Interprétation du CCTP",
     "Le présent descriptif porte sur les travaux à exécuter en concordance avec les plans et ne présente aucun caractère "
     "limitatif. Les travaux comprennent tout ce qui est indiqué aux plans, coupes et élévations ainsi qu'au présent CCTP, "
     "quand bien même diverses indications de détail n'y seraient pas précisées : l'entrepreneur est réputé avoir suppléé "
     "par ses connaissances professionnelles aux éventuelles imprécisions des documents fournis. En cas de contradiction "
     "entre pièces, la prescription la plus favorable à la qualité de l'ouvrage s'applique, sauf avis contraire du maître "
     "d'œuvre."),
    ("Vérification des documents et des cotes",
     "Avant tout commencement d'exécution, l'entrepreneur vérifiera les cotes des documents graphiques et signalera au "
     "maître d'œuvre toute erreur ou omission constatée. À défaut, il sera tenu pour responsable de son erreur ainsi que "
     "des modifications qu'elle entraîne pour l'ensemble des corps d'état."),
    ("Documents de référence",
     "Les ouvrages seront exécutés conformément aux documents techniques en vigueur à la date de remise des offres, "
     "notamment : les normes NF DTU applicables au lot (cahiers des clauses techniques types et cahiers des clauses "
     "administratives spéciales types), les normes NF et EN, les Eurocodes et leurs annexes nationales, les Avis "
     "Techniques et Documents Techniques d'Application des produits non traditionnels, les règles professionnelles "
     "reconnues, ainsi que les prescriptions de pose des fabricants."),
    ("Échantillons, fiches techniques et plans d'exécution",
     "Avant toute commande, l'entrepreneur soumettra au visa du maître d'œuvre les fiches techniques, procès-verbaux "
     "d'essais, Avis Techniques et, à sa demande, les échantillons des matériaux et équipements proposés. Il établira "
     "les plans d'exécution, de réservations et les détails nécessaires à ses ouvrages. Aucun ouvrage ne pourra être "
     "engagé sans visa préalable."),
    ("Coordination avec les autres lots",
     "L'entrepreneur se coordonnera avec les autres corps d'état pour l'exécution des réservations, incorporations, "
     "trémies et raccords. Il vérifiera, avant de commencer ses travaux, que les supports livrés par les lots "
     "précédents sont conformes aux tolérances requises pour ses propres ouvrages ; à défaut de réserve écrite, il "
     "sera réputé les avoir acceptés."),
    ("Hygiène et sécurité",
     "L'entrepreneur se conformera aux prescriptions du Plan Général de Coordination (PGC) établi par le coordonnateur "
     "SPS lorsqu'il est requis, et remettra son Plan Particulier de Sécurité et de Protection de la Santé (PPSPS) avant "
     "toute intervention. Il assistera aux inspections communes et appliquera les mesures de prévention décidées."),
    ("Validation des fournitures",
     "Les références des fournitures et équipements (matériaux de finition, appareillages, équipements) seront présentées "
     "au maître d'ouvrage et à l'architecte pour validation, avec devis, avant toute commande. Les marques et modèles "
     "éventuellement cités le sont à titre de référence : l'entrepreneur peut proposer des produits techniquement et "
     "esthétiquement équivalents, sous réserve de l'accord du maître d'œuvre."),
    ("Protection, nettoyage et évacuation des déchets",
     "L'entrepreneur assurera la protection de ses ouvrages jusqu'à la réception ainsi que celle des ouvrages "
     "existants ou des autres lots qu'il pourrait détériorer. Il procédera au nettoyage quotidien de sa zone de "
     "travail et à l'évacuation de ses déchets, triés par nature, vers des filières agréées, avec bordereaux de suivi "
     "si nécessaire."),
    ("Dossier des ouvrages exécutés",
     "À l'achèvement des travaux, l'entrepreneur remettra les éléments du dossier des ouvrages exécutés (DOE) relevant "
     "de son lot : plans conformes à exécution, fiches techniques des produits mis en œuvre, notices d'entretien et "
     "de maintenance, procès-verbaux et attestations exigés par la réglementation."),
]

RENOVATION = ("Travaux en site existant",
              "Les travaux étant réalisés dans un bâtiment existant, l'entrepreneur prendra toutes dispositions pour "
              "préserver les ouvrages conservés, les réseaux en service et, le cas échéant, l'occupation des locaux. "
              "Avant toute intervention sur des matériaux susceptibles de contenir de l'amiante ou du plomb, il prendra "
              "connaissance des repérages réglementaires fournis par le maître d'ouvrage ; toute découverte imprévue "
              "sera signalée immédiatement et les travaux concernés suspendus.")


def _o(code, chapitre, titre, description, unite, variantes, motscles):
    return {"code": code, "chapitre": chapitre, "titre": titre, "description": description, "unite": unite,
            "variantes": variantes, "motscles": motscles}


# ---------------------------------------------------------------------------------------------
# Lots
# ---------------------------------------------------------------------------------------------
LOTS: list[dict] = [
    {
        "code": "demolition", "numero": 1, "titre": "Démolition – Curage",
        "motscles": ["demolition", "depose", "curage", "desamiantage", "evacuation gravats"],
        "refs": ["Code du travail, articles R4412-94 et suivants — Risques d'exposition à l'amiante",
                 "Arrêté du 16 juillet 2019 relatif au repérage de l'amiante avant certaines opérations",
                 "Recommandation CNAM R 447 / Guide INRS des travaux de démolition"],
        "prescriptions": [
            ("Préparation et sécurité des démolitions", [
                ("Reconnaissance préalable",
                 "Avant tout début de démolition, l'entrepreneur procédera à la reconnaissance des ouvrages à démolir, au "
                 "repérage et à la neutralisation des réseaux (électricité, gaz, eau, assainissement) en liaison avec les "
                 "concessionnaires et les lots techniques. Il vérifiera que les ouvrages conservés ne sont pas porteurs ou "
                 "solidaires des ouvrages à démolir ; en cas de doute, il en référera au maître d'œuvre."),
                ("Étaiements et stabilité",
                 "L'entrepreneur assure, sous sa responsabilité, la stabilité des ouvrages conservés et des mitoyens pendant "
                 "toute la durée des travaux : étaiements, butonnages et blindages provisoires nécessaires, maintenus "
                 "jusqu'à la reprise définitive par le lot gros œuvre."),
                ("Tri et évacuation",
                 "Les produits de démolition seront triés sur site (inertes, bois, métaux, plâtre, déchets non dangereux, "
                 "déchets dangereux) et évacués vers des installations autorisées. Les bordereaux de suivi seront remis au "
                 "maître d'œuvre."),
            ]),
        ],
        "ouvrages": [
            _o("curage", "Curage", "CURAGE INTÉRIEUR COMPLET",
               "Dépose et évacuation de l'ensemble des équipements, revêtements et aménagements intérieurs désignés aux plans : "
               "revêtements de sols et muraux, faux plafonds, cloisons légères, menuiseries intérieures, appareils sanitaires et "
               "équipements techniques hors service. Y compris protection des ouvrages conservés, tri et évacuation.",
               "m2", ["Curage complet des niveaux concernés"], ["curage", "depose"]),
            _o("demol_cloison", "Démolitions", "DÉMOLITION DE CLOISONS NON PORTEUSES",
               "Démolition soignée de cloisons de distribution non porteuses (briques, carreaux de plâtre, plaques sur ossature), "
               "y compris dépose des huisseries, rebouchage des saignées et évacuation des gravois.",
               "m2", ["Cloisons de distribution, toutes épaisseurs"], ["demolition cloison", "demolition de cloison", "depose cloison"]),
            _o("ouverture_mur", "Démolitions", "CRÉATION D'OUVERTURE EN MUR PORTEUR",
               "Création d'ouverture dans un mur porteur, suivant note de calcul et plans d'exécution du bureau d'études structure : "
               "étaiement, sciage ou démolition soignée, mise en place du linteau ou de la poutre de reprise par le lot gros œuvre, "
               "y compris toutes sujétions.",
               "u", ["Ouverture suivant plans structure"], ["ouverture", "tremie", "mur porteur"]),
            _o("depose_revetements", "Déposes", "DÉPOSE DE REVÊTEMENTS DE SOLS",
               "Dépose de revêtements de sols existants (carrelage, parquet, sols souples) y compris colle ou mortier de pose, "
               "jusqu'au support sain, et évacuation.",
               "m2", ["Revêtements de sols, toutes natures"], ["depose carrelage", "depose parquet", "depose sol"]),
        ],
    },
    {
        "code": "vrd", "numero": 2, "titre": "Terrassement – VRD",
        "motscles": ["terrassement", "fouille", "remblai", "tranchee", "vrd", "assainissement", "regard", "drain"],
        "refs": ["NF DTU 12 — Terrassements pour le bâtiment",
                 "NF P 11-300 — Classification des matériaux utilisables dans la construction des remblais",
                 "NF EN 1610 — Mise en œuvre et essai des branchements et collecteurs d'assainissement",
                 "NF DTU 64.1 — Dispositifs d'assainissement non collectif",
                 "NF DTU 20.1 — Drainage des murs enterrés (partie relative aux ouvrages de drainage)"],
        "prescriptions": [
            ("Préconisations de mise en œuvre", [
                ("Implantation et piquetage",
                 "L'implantation des ouvrages sera réalisée à partir des repères fournis par le géomètre du maître d'ouvrage. "
                 "L'entrepreneur en assure la conservation pendant toute la durée du chantier."),
                ("Étude géotechnique",
                 "Les terrassements et fondations seront exécutés conformément aux conclusions de l'étude géotechnique "
                 "jointe au dossier. Toute différence constatée avec les hypothèses de l'étude sera signalée sans délai au "
                 "maître d'œuvre avant poursuite des travaux."),
                ("Réseaux enterrés",
                 "Les canalisations seront posées sur lit de pose et enrobées de matériaux adaptés, avec pentes régulières "
                 "conformes aux plans, grillage avertisseur de couleur normalisée et essais d'étanchéité avant remblaiement."),
            ]),
        ],
        "ouvrages": [
            _o("decapage", "Terrassements", "DÉCAPAGE DE LA TERRE VÉGÉTALE",
               "Décapage de la terre végétale sur l'emprise des constructions et des voiries, sur l'épaisseur constatée, avec mise "
               "en dépôt sur site pour réemploi ou évacuation.", "m2", ["Épaisseur moyenne suivant étude"], ["decapage", "terre vegetale"]),
            _o("fouilles", "Terrassements", "FOUILLES EN RIGOLES ET EN TRANCHÉES",
               "Fouilles en rigoles pour semelles filantes et en puits pour massifs, à la profondeur hors gel et au bon sol "
               "définis par l'étude géotechnique, y compris dressement des parois, épuisement éventuel et évacuation ou réemploi "
               "des déblais.", "m3", ["Fouilles en rigoles", "Fouilles en puits"], ["fouille", "rigole", "terrassement"]),
            _o("remblai", "Terrassements", "REMBLAIS COMPACTÉS",
               "Remblais en matériaux d'apport ou de réemploi conformes à la NF P 11-300, mis en œuvre par couches compactées, "
               "contre les ouvrages enterrés et sous dallages.", "m3", ["Remblai en grave compactée"], ["remblai"]),
            _o("reseau_eu", "Réseaux", "RÉSEAUX D'EAUX USÉES ET D'EAUX VANNES ENTERRÉS",
               "Canalisations en PVC compact CR8 posées en tranchée sur lit de sable, y compris raccords, pièces spéciales, regards "
               "de visite et raccordement au réseau public ou au dispositif d'assainissement.", "ml",
               ["PVC Ø 125 mm", "PVC Ø 160 mm"], ["eaux usees", "evacuation", "canalisation enterree"]),
            _o("reseau_ep", "Réseaux", "RÉSEAUX D'EAUX PLUVIALES",
               "Collecte des descentes d'eaux pluviales par regards à grille et canalisations PVC jusqu'à l'exutoire défini "
               "(réseau public, puits d'infiltration ou cuve de récupération).", "ml", ["PVC Ø 100 mm", "PVC Ø 125 mm"],
               ["eaux pluviales", "descente"]),
            _o("drainage", "Réseaux", "DRAINAGE PÉRIPHÉRIQUE",
               "Drain agricole annelé enrobé de géotextile et de gravier roulé, posé en pied de fondations, avec regards de "
               "visite aux changements de direction et rejet à l'exutoire.", "ml", ["Drain Ø 100 mm"], ["drain", "drainage"]),
        ],
    },
    {
        "code": "gros_oeuvre", "numero": 3, "titre": "Gros œuvre – Maçonnerie",
        "motscles": ["mur", "maconnerie", "parpaing", "bloc", "beton", "dalle", "fondation", "semelle", "linteau", "chainage",
                     "dallage", "voile", "poteau", "poutre", "plancher", "hourdis"],
        "refs": ["NF DTU 13.1 — Fondations superficielles", "NF DTU 13.3 — Dallages",
                 "NF DTU 20.1 — Ouvrages en maçonnerie de petits éléments", "NF DTU 21 — Exécution des ouvrages en béton",
                 "NF DTU 23.1 — Murs en béton banché", "NF EN 206/CN — Béton : spécification, performances, production et conformité",
                 "NF EN 1992 (Eurocode 2) — Calcul des structures en béton", "NF EN 1998 (Eurocode 8) — Calcul des structures pour leur résistance aux séismes"],
        "prescriptions": [
            ("Préconisations de mise en œuvre", [
                ("Études d'exécution",
                 "Les ouvrages de structure seront exécutés suivant les plans et notes de calcul du bureau d'études structure. "
                 "Les plans de coffrage et de ferraillage seront soumis au visa du maître d'œuvre et du contrôleur technique "
                 "avant exécution."),
                ("Bétons et armatures",
                 "Les bétons seront des bétons prêts à l'emploi conformes à la NF EN 206/CN, de classe de résistance et "
                 "d'exposition définies par l'étude structure. Les armatures seront en acier B500 conformes aux normes en "
                 "vigueur ; les enrobages respecteront les prescriptions de l'Eurocode 2 pour la classe d'exposition."),
                ("Tolérances",
                 "Les tolérances d'implantation, d'aplomb et de planéité seront celles des NF DTU 20.1 et 21. Les supports "
                 "destinés à recevoir des revêtements ou des doublages collés respecteront les tolérances exigées par les lots "
                 "concernés."),
                ("Réservations",
                 "L'entrepreneur exécutera toutes les réservations, trémies, fourreaux et incorporations demandées par les "
                 "lots techniques en temps utile, sur la base de leurs plans de réservations visés."),
            ]),
        ],
        "ouvrages": [
            _o("semelles", "Fondations", "SEMELLES FILANTES EN BÉTON ARMÉ",
               "Semelles filantes coulées en pleine fouille ou coffrées, sur béton de propreté, en béton armé de classe définie par "
               "l'étude structure, y compris armatures, attentes et réservations pour passage des réseaux.", "m3",
               ["Béton de propreté ép. 5 cm", "Semelles BA suivant plans structure"], ["semelle", "fondation"]),
            _o("soubassement", "Fondations", "MURS DE SOUBASSEMENT",
               "Murs de soubassement en blocs béton pleins ou à bancher, hourdés au mortier, avec arase étanche en tête et "
               "protection des parois enterrées.", "m2", ["Blocs à bancher ép. 20 cm"], ["soubassement", "vide sanitaire"]),
            _o("dallage", "Planchers bas", "DALLAGE SUR TERRE-PLEIN",
               "Dallage en béton armé sur hérisson compacté, film polyéthylène et isolant sous dallage le cas échéant, avec joints "
               "de retrait sciés suivant le NF DTU 13.3.", "m2", ["Dallage BA ép. 12 cm"], ["dallage", "dalle"]),
            _o("plancher_hourdis", "Planchers", "PLANCHER POUTRELLES ET ENTREVOUS",
               "Plancher à poutrelles précontraintes et entrevous béton ou isolants, avec dalle de compression armée, suivant "
               "plan de pose du fabricant et étude structure, y compris étaiement, chaînages et trémies.", "m2",
               ["Plancher 16+4", "Plancher 20+5"], ["plancher", "hourdis", "poutrelle"]),
            _o("murs_blocs", "Élévations", "MURS EN MAÇONNERIE DE BLOCS BÉTON",
               "Murs porteurs en blocs béton creux hourdés au mortier ou collés, conformes au NF DTU 20.1, y compris chaînages "
               "horizontaux et verticaux, linteaux, appuis et tableaux.", "m2", ["Blocs creux ép. 20 cm"],
               ["mur", "parpaing", "bloc", "maconnerie"]),
            _o("chainages", "Élévations", "CHAÎNAGES, LINTEAUX ET POTEAUX EN BÉTON ARMÉ",
               "Chaînages horizontaux et verticaux, linteaux et poteaux coulés en place ou préfabriqués, armés suivant étude "
               "structure.", "ml", ["Chaînages et linteaux suivant plans"], ["chainage", "linteau", "poteau", "poutre"]),
            _o("enduit_facade", "Façades", "ENDUIT MONOCOUCHE DE FAÇADE",
               "Enduit d'imperméabilisation monocouche projeté mécaniquement, sur support préparé, teinte et finition au choix "
               "de l'architecte, y compris baguettes d'angle et traitement des points singuliers.", "m2",
               ["Finition grattée", "Finition talochée"], ["enduit facade", "facade", "ravalement"]),
        ],
    },
    {
        "code": "charpente_couverture", "numero": 4, "titre": "Charpente – Couverture – Zinguerie",
        "motscles": ["charpente", "couverture", "toiture", "tuile", "ardoise", "zinguerie", "gouttiere", "fermette", "chevron", "liteau"],
        "refs": ["NF DTU 31.1 — Charpente en bois", "NF DTU 31.3 — Charpentes en bois assemblées par connecteurs métalliques",
                 "NF DTU 40.21 — Couvertures en tuiles de terre cuite à emboîtement ou à glissement à relief",
                 "NF DTU 40.11 — Couverture en ardoises", "NF DTU 40.29 — Écrans souples de sous-toiture",
                 "NF DTU 40.41 — Couvertures par éléments métalliques en feuilles et longues feuilles en zinc",
                 "NF DTU 40.5 — Évacuation des eaux pluviales", "NF EN 1995 (Eurocode 5) — Conception et calcul des structures en bois",
                 "NF EN 1991 (Eurocode 1) — Actions sur les structures (neige et vent)"],
        "prescriptions": [
            ("Préconisations de mise en œuvre", [
                ("Dimensionnement",
                 "La charpente sera dimensionnée par l'entrepreneur ou son bureau d'études suivant l'Eurocode 5 et les charges "
                 "de neige et de vent du site (Eurocode 1 et annexes nationales). La note de calcul et les plans de fabrication "
                 "seront soumis au visa avant fabrication."),
                ("Bois et traitement",
                 "Les bois seront de classe de résistance adaptée et traités contre les insectes et champignons selon la classe "
                 "d'emploi requise. Les bois de charpente auront une humidité compatible avec leur mise en œuvre."),
                ("Ventilation de la couverture",
                 "La ventilation de la sous-face des éléments de couverture et, le cas échéant, de la lame d'air sous écran sera "
                 "assurée conformément au NF DTU de la couverture concernée et au NF DTU 40.29."),
            ]),
        ],
        "ouvrages": [
            _o("charpente_fermettes", "Charpente", "CHARPENTE EN FERMETTES INDUSTRIELLES",
               "Fourniture et pose de fermettes industrielles assemblées par connecteurs, y compris contreventements, "
               "anti-flambements, ancrages et chevêtres pour trémies, suivant note de calcul du fabricant.", "m2",
               ["Fermettes à entraxe 0,60 m"], ["fermette", "charpente"]),
            _o("charpente_trad", "Charpente", "CHARPENTE TRADITIONNELLE",
               "Charpente traditionnelle en bois massif ou lamellé-collé (fermes, pannes, chevrons), assemblages, ferrures et "
               "ancrages suivant note de calcul.", "m2", ["Charpente bois massif traité"], ["charpente", "chevron", "panne"]),
            _o("ecran", "Couverture", "ÉCRAN SOUPLE DE SOUS-TOITURE",
               "Écran souple de sous-toiture HPV sous Avis Technique, posé sur chevrons avec contre-lattage, conformément au "
               "NF DTU 40.29.", "m2", ["Écran HPV"], ["ecran sous toiture", "sous-toiture"]),
            _o("tuiles", "Couverture", "COUVERTURE EN TUILES DE TERRE CUITE",
               "Couverture en tuiles de terre cuite à emboîtement, modèle et teinte au choix de l'architecte suivant règlement "
               "d'urbanisme, sur liteaux, y compris faîtage ventilé, rives, arêtiers, noues et accessoires.", "m2",
               ["Tuiles terre cuite à emboîtement"], ["tuile", "couverture", "toiture"]),
            _o("zinguerie", "Zinguerie", "GOUTTIÈRES ET DESCENTES D'EAUX PLUVIALES",
               "Gouttières pendantes ou havraises et descentes en zinc naturel ou prépatiné, y compris crochets, naissances, "
               "coudes, dauphins et raccordement aux réseaux.", "ml", ["Gouttière zinc dév. 25", "Descente zinc Ø 80"],
               ["gouttiere", "descente", "zinguerie", "zinc"]),
            _o("fenetre_toit", "Couverture", "FENÊTRES DE TOIT",
               "Fenêtres de toit avec raccord d'étanchéité adapté au matériau de couverture, dimensions suivant plans.", "u",
               ["Fenêtre de toit 78 x 98 cm"], ["fenetre de toit", "velux"]),
        ],
    },
    {
        "code": "menuiseries_ext", "numero": 5, "titre": "Menuiseries extérieures – Fermetures",
        "motscles": ["fenetre", "porte fenetre", "baie", "menuiserie exterieure", "volet", "porte d'entree", "vitrage", "coulissant"],
        "refs": ["NF DTU 36.5 — Mise en œuvre des fenêtres et portes extérieures", "NF DTU 34.4 — Mise en œuvre des fermetures et stores",
                 "NF DTU 39 — Travaux de vitrerie-miroiterie", "NF EN 14351-1 — Fenêtres et blocs portes extérieurs piétons"],
        "prescriptions": [
            ("Préconisations de mise en œuvre", [
                ("Performances",
                 "Les menuiseries présenteront des performances d'étanchéité à l'air, à l'eau et au vent (classement AEV) adaptées "
                 "à leur exposition, et des performances thermiques (Uw) et acoustiques conformes à l'étude thermique et à la "
                 "notice acoustique du projet. Les menuiseries bénéficieront d'un marquage CE et, de préférence, d'une "
                 "certification de qualité."),
                ("Pose",
                 "La pose (en applique, en tunnel ou en feuillure) sera conforme au NF DTU 36.5, avec calfeutrement continu "
                 "assurant l'étanchéité à l'air et à l'eau entre dormant et gros œuvre, et traitement soigné de l'appui."),
                ("Sécurité",
                 "Les vitrages des portes, portes-fenêtres et allèges basses seront des vitrages de sécurité, conformément au "
                 "NF DTU 39. Les garde-corps éventuels seront conformes à la NF P 01-012."),
            ]),
        ],
        "ouvrages": [
            _o("fenetres_pvc", "Menuiseries", "FENÊTRES ET PORTES-FENÊTRES",
               "Menuiseries en PVC, aluminium à rupture de pont thermique ou bois, ouvrant à la française ou oscillo-battant, "
               "double vitrage à isolation renforcée, avec entrées d'air conformes à l'étude de ventilation.", "u",
               ["Fenêtre 1 vantail", "Fenêtre 2 vantaux", "Porte-fenêtre 2 vantaux"], ["fenetre", "porte fenetre", "menuiserie"]),
            _o("coulissant", "Menuiseries", "BAIES COULISSANTES",
               "Baies coulissantes en aluminium à rupture de pont thermique, double vitrage de sécurité, seuil adapté aux "
               "exigences d'accessibilité le cas échéant.", "u", ["Baie coulissante 2 vantaux"], ["coulissant", "baie"]),
            _o("porte_entree", "Menuiseries", "PORTE D'ENTRÉE",
               "Bloc-porte d'entrée isolant, serrure de sûreté multipoints, seuil à rupture de pont thermique, modèle au choix "
               "de l'architecte.", "u", ["Porte d'entrée isolante"], ["porte d'entree", "porte entree"]),
            _o("volets", "Fermetures", "VOLETS ROULANTS",
               "Volets roulants à lames aluminium, coffre intégré ou demi-linteau, manœuvre électrique avec alimentation par le "
               "lot électricité.", "u", ["Volet roulant électrique"], ["volet", "volet roulant"]),
        ],
    },
    {
        "code": "platrerie", "numero": 6, "titre": "Plâtrerie – Cloisons – Doublages – Faux plafonds",
        "motscles": ["cloison", "placo", "doublage", "plafond", "plaque de platre", "ba13", "faux plafond", "soffite", "coffrage",
                     "carreau de platre", "isolation", "laine"],
        "refs": ["NF DTU 25.41 — Ouvrages en plaques de plâtre", "NF DTU 25.42 — Ouvrages de doublage et habillage en complexes et sandwiches",
                 "NF DTU 25.1 — Enduits intérieurs en plâtre", "NF DTU 25.31 — Ouvrages verticaux de plâtrerie en carreaux de plâtre",
                 "NF DTU 58.1 — Plafonds suspendus", "NF DTU 45.11 — Isolation des combles par rouleaux et panneaux",
                 "NF DTU 59.1 — Revêtements de peinture (pour les finitions associées)"],
        "prescriptions": [
            ("Exécution des ouvrages en plaques de parement", [
                ("Travaux préparatoires",
                 "Les travaux ne commenceront qu'une fois le bâtiment hors d'eau et hors d'air. Avant exécution, il sera procédé "
                 "à l'implantation et au traçage des ouvrages, à la mise en place des dispositifs de raccord avec les parois "
                 "existantes et les joints de gros œuvre. Les conduits et incorporations devront de préférence être en place."),
                ("Fixations de l'ossature",
                 "La fixation par pistoscellement ne sera pas utilisée sur supports fragiles (maçonnerie creuse, béton cellulaire), "
                 "comportant des canalisations incorporées, ni dans les poutrelles et prédalles précontraintes, ni lorsqu'elle "
                 "serait sollicitée en traction. Les lisses basses et hautes seront fixées tous les 0,60 m au plus ; en pièce "
                 "humide, la lisse basse sera protégée par un relevé étanche ou posée sur un support surélevé."),
                ("Ossature verticale",
                 "Les montants seront disposés à un entraxe de 0,40 m ou 0,60 m suivant les hauteurs admissibles du système, "
                 "d'une seule pièce sur toute la hauteur ; les aboutages éventuels seront éclissés et décalés d'un montant à "
                 "l'autre. Les montants seront doublés au droit des huisseries et des charges lourdes."),
                ("Pose des plaques",
                 "Les plaques seront posées jointives, butées en tête avec un jeu d'environ 1 cm en pied, joints au droit des "
                 "montants et alternés d'un parement à l'autre et entre couches successives. Vissage tous les 0,30 m au plus en "
                 "parement apparent. Les incorporations seront réalisées avant la fermeture du second parement."),
                ("Points singuliers et renforts",
                 "Un joint de fractionnement sera ménagé au droit des joints de gros œuvre et au plus tous les 15 m. Toute charge "
                 "suspendue supérieure à 30 kg sera reprise par un renfort solidaire de l'ossature (traverse ou platine) prévu "
                 "lors du montage."),
                ("Tolérances",
                 "Planéité locale : 1 mm sous la règle de 0,20 m ; planéité générale : 5 mm sous la règle de 2 m ; faux aplomb : "
                 "5 mm pour une hauteur d'étage courante. Après traitement des joints, le parement ne présentera ni pulvérulence "
                 "ni trou et sera apte à recevoir la finition prévue sans autre préparation que celle normalement admise."),
            ]),
            ("Ouvrages horizontaux et plafonds", [
                ("Ossature de plafond",
                 "L'ossature (fourrures, suspentes et fixations) sera dimensionnée pour reprendre le poids propre du plafond, de "
                 "l'isolant et des équipements, ainsi que les effets du vent le cas échéant. Les suspentes seront protégées contre "
                 "la corrosion. Les entraxes respecteront les valeurs du système retenu en fonction de l'épaisseur des plaques."),
                ("Planéité et joints",
                 "La sous-face de l'ossature ne présentera pas d'irrégularité supérieure à 5 mm sous la règle de 2 m. Le plafond "
                 "sera interrompu au droit des joints de dilatation de la structure et au plus tous les 15 m. Les joints en "
                 "plafond ne seront traités qu'après blocage des cloisons associées."),
                ("Isolation et pare-vapeur",
                 "Lorsque un isolant est disposé au-dessus du plafond, un pare-vapeur continu sera mis en place côté chaud, avec "
                 "recouvrements adhésivés et raccords étanches en périphérie et au droit des traversées."),
            ]),
        ],
        "ouvrages": [
            _o("cloison_72", "Cloisons en plaques de plâtre sur ossature", "CLOISONS DE DISTRIBUTION 72/48",
               "Cloison de 72 mm d'épaisseur composée d'une plaque de plâtre par face vissée sur ossature métallique en acier "
               "galvanisé de 48 mm (rails et montants à entraxe 0,60 m), incorporation d'isolant en laine minérale, traitement "
               "des joints, angles et cueillies par bande et enduit. Plaques hydrofuges en pièces humides.", "m2",
               ["1 plaque standard BA13 par parement", "1 plaque hydrofuge H1 BA13 par parement (pièces humides)"],
               ["cloison", "cloison distributive", "72/48"]),
            _o("cloison_98", "Cloisons en plaques de plâtre sur ossature", "CLOISONS À DOUBLES PLAQUES 98/48 AVEC ISOLANT",
               "Cloison de 98 mm d'épaisseur composée de deux plaques de plâtre par face, vissées sur rails et montants en acier "
               "galvanisé de 48 mm à entraxe 0,60 m, vis autoforeuses tête trompette à entraxe maximal 0,30 m, mastic acoustique "
               "en pied, incorporation de panneaux semi-rigides de laine minérale, traitement des joints par bande et enduit.",
               "m2", ["2 plaques standard BA13 par parement"], ["cloison separative", "98/48", "double plaque"]),
            _o("cloison_120", "Cloisons en plaques de plâtre sur ossature", "CLOISONS À DOUBLES PLAQUES 120/70 AVEC ISOLANT",
               "Cloison de 120 mm d'épaisseur à deux plaques de plâtre par face sur ossature de 70 mm, mêmes prescriptions que "
               "l'article précédent ; hauteur d'emploi suivant procès-verbal du système (montants doublés au besoin).", "m2",
               ["2 plaques standard BA13 par parement"], ["120/70", "cloison separative"]),
            _o("doublage_isolant", "Doublages", "DOUBLAGES THERMIQUES SUR OSSATURE",
               "Doublage des murs extérieurs par plaque de plâtre vissée sur ossature métallique indépendante ou fixée par appuis "
               "intermédiaires, isolant en laine minérale de résistance thermique définie par l'étude thermique, pare-vapeur "
               "continu côté chaud, traitement des joints.", "m2", ["Isolant R ≥ valeur de l'étude thermique, plaque BA13"],
               ["doublage", "isolation mur", "isolation"]),
            _o("doublage_colle", "Doublages", "COMPLEXES DE DOUBLAGE COLLÉS",
               "Complexes isolants plaque de plâtre + polystyrène ou polyuréthane, collés par plots de mortier adhésif sur support "
               "plan (irrégularités ≤ 15 mm), conformément au NF DTU 25.42.", "m2", ["Complexe 13 + isolant suivant étude thermique"],
               ["complexe de doublage", "doublage colle"]),
            _o("habillage_colle", "Habillages", "PLAQUES DE PLÂTRE COLLÉES",
               "Habillage de parois en plaques de plâtre fixées par plots de colle sur le support, joints par bande et enduit ; "
               "le support ne comportera pas d'irrégularité de surface supérieure à 15 mm.", "m2",
               ["Plaques hydrofuges de 10 mm"], ["habillage", "plaque collee"]),
            _o("plafond_ba13", "Plafonds non démontables", "PLAFONDS EN PLAQUES DE PLÂTRE SUR OSSATURE",
               "Plafond constitué d'une ou plusieurs plaques de plâtre (standard ou hydrofuge) vissées sur ossature métallique en "
               "acier galvanisé suspendue ou fixée sous plancher ou charpente, y compris suspentes, cornières et traitement des "
               "joints par bande et enduit.", "m2",
               ["Plaques standard 13 mm sous plancher", "Plaques standard 13 mm sous rampants", "Plaques hydrofuges 13 mm en pièces humides"],
               ["plafond", "faux plafond", "plafond placo"]),
            _o("isolation_combles", "Isolation", "ISOLATION DES COMBLES PERDUS",
               "Isolation des combles perdus par rouleaux ou panneaux de laine minérale posés en deux couches croisées, ou par "
               "soufflage, résistance thermique suivant étude thermique, y compris pare-vapeur, repérage des boîtiers et "
               "écarts au feu des conduits.", "m2", ["Laine minérale R ≥ valeur de l'étude thermique"], ["isolation combles", "combles", "laine"]),
            _o("trappe", "Ouvrages divers", "TRAPPES DE VISITE",
               "Trappes de visite à cadre et portillon en plaque de plâtre, joint de 3 mm maximum, degré coupe-feu ou isolation "
               "assurant la continuité de l'ouvrage traversé.", "u", ["Trappe 50 x 50 cm", "Trappe isolée d'accès aux combles 60 x 60 cm"],
               ["trappe"]),
            _o("soffite", "Encoffrements techniques", "SOFFITES ET COFFRES EN PLAQUES DE PLÂTRE",
               "Soffites et encoffrements de gaines composés de plaques de plâtre sur ossature avec laine minérale dans le plénum, "
               "y compris coupes, ajustages et sujétions de fixation et de finition.", "ml",
               ["Soffite 2 plaques standard 13 mm avec isolant"], ["soffite", "coffrage", "gaine"]),
            _o("carreaux_platre", "Cloisons en carreaux de plâtre", "CLOISONS EN CARREAUX DE PLÂTRE PLEINS",
               "Cloisons de distribution non porteuses en carreaux de plâtre pleins 66 x 50 à emboîtement, montés à la colle, "
               "premier rang en carreau hydrofuge, liaison en tête par bande résiliente, joints décalés, liaisons d'angle par "
               "harpage, huisseries fixées par pattes de scellement. Saignées des lots techniques exclusivement à la rainureuse.",
               "m2", ["Carreaux pleins de 70 mm", "Carreaux pleins de 100 mm"], ["carreau de platre", "carreaux de platre"]),
        ],
    },
    {
        "code": "menuiseries_int", "numero": 7, "titre": "Menuiseries intérieures",
        "motscles": ["porte interieure", "bloc porte", "placard", "escalier", "plinthe bois", "habillage bois", "menuiserie interieure"],
        "refs": ["NF DTU 36.2 — Menuiseries intérieures en bois", "NF DTU 36.3 — Escaliers en bois et garde-corps associés",
                 "NF P 01-012 — Dimensions des garde-corps"],
        "prescriptions": [
            ("Préconisations de mise en œuvre", [
                ("Huisseries",
                 "Les huisseries et bâtis seront posés d'aplomb et de niveau, calés et fixés à l'ossature ou à la maçonnerie, avant "
                 "ou pendant l'exécution des cloisons suivant le système retenu. Leur réglage tiendra compte de l'épaisseur des "
                 "revêtements de sol finis."),
                ("Quincaillerie",
                 "La quincaillerie sera de qualité adaptée à un usage intensif ; un échantillon de chaque type sera soumis à "
                 "l'architecte. Les portes de locaux humides recevront un détalonnage pour le transit de l'air de la ventilation."),
            ]),
        ],
        "ouvrages": [
            _o("bloc_porte", "Portes", "BLOCS-PORTES INTÉRIEURS",
               "Blocs-portes à âme alvéolaire ou pleine, huisserie métallique ou bâti bois, finition à peindre ou prépeinte, "
               "serrure à condamnation pour sanitaires et salles d'eau, béquilles sur rosaces.", "u",
               ["Bloc-porte 83 x 204 cm", "Bloc-porte 93 x 204 cm (accessibilité)"], ["porte interieure", "bloc porte", "porte"]),
            _o("placard", "Rangements", "PORTES DE PLACARD ET AMÉNAGEMENTS",
               "Façades de placards coulissantes ou battantes sur rails, aménagement intérieur (tablette, penderie) suivant plans.",
               "u", ["Façade coulissante 2 vantaux"], ["placard"]),
            _o("escalier_bois", "Escaliers", "ESCALIER EN BOIS",
               "Escalier en bois massif ou lamellé-collé, forme et dimensions suivant plans (hauteur et giron réguliers), "
               "garde-corps et main courante conformes à la NF P 01-012.", "u", ["Escalier quart tournant"], ["escalier"]),
            _o("plinthes_bois", "Finitions", "PLINTHES EN BOIS",
               "Plinthes en bois ou MDF à peindre, fixées par collage ou pointes, coupes d'onglet aux angles.", "ml",
               ["Plinthes 70 mm à peindre"], ["plinthe"]),
        ],
    },
    {
        "code": "sols_durs", "numero": 8, "titre": "Chapes – Carrelage – Faïences",
        "motscles": ["carrelage", "faience", "carreau", "chape", "etancheite sous carrelage", "spec", "sel", "gres"],
        "refs": ["NF DTU 26.2 — Chapes et dalles à base de liants hydrauliques",
                 "NF DTU 52.1 — Revêtements de sol scellés", "NF DTU 52.2 — Pose collée des revêtements céramiques et assimilés",
                 "NF DTU 52.10 — Mise en œuvre de sous-couches isolantes sous chape ou dalle flottantes et sous carrelage scellé"],
        "prescriptions": [
            ("Préconisations de mise en œuvre", [
                ("Supports",
                 "Avant pose, l'entrepreneur vérifiera la planéité, la cohésion, la propreté et la siccité des supports. Les délais "
                 "de séchage des chapes et dalles seront respectés avant collage."),
                ("Classement des locaux",
                 "Les carreaux et les mortiers-colles seront choisis en fonction du classement UPEC des locaux et de la nature du "
                 "support. Les carreaux de sol présenteront une résistance à la glissance adaptée aux locaux humides."),
                ("Locaux humides",
                 "Dans les douches et zones exposées aux projections d'eau, un système de protection à l'eau sous carrelage (SPEC "
                 "en murs, SEL en sols) sous Avis Technique sera mis en œuvre, avec bandes de renfort aux angles et traversées."),
                ("Joints",
                 "Les joints de fractionnement et périphériques seront respectés conformément aux NF DTU de pose. Les joints "
                 "souples entre revêtements et appareils sanitaires seront réalisés au mastic fongicide."),
            ]),
        ],
        "ouvrages": [
            _o("chape", "Chapes", "CHAPES FLUIDES OU TRADITIONNELLES",
               "Chape à base de liant hydraulique, adhérente ou flottante sur isolant ou sous-couche acoustique suivant plans, "
               "épaisseur conforme au NF DTU 26.2, y compris bandes périphériques et joints.", "m2",
               ["Chape flottante ép. 5 cm", "Chape adhérente ép. 4 cm"], ["chape"]),
            _o("carrelage_sol", "Revêtements de sols", "CARRELAGE AU SOL",
               "Carrelage en grès cérame, format et teinte au choix de l'architecte, posé collé au mortier-colle adapté au "
               "support et au format, joints au mortier de jointoiement, y compris coupes et barres de seuil.", "m2",
               ["Grès cérame 60 x 60 cm", "Grès cérame 30 x 60 cm"], ["carrelage", "carreau", "gres"]),
            _o("plinthes_carrelage", "Revêtements de sols", "PLINTHES CARRELÉES",
               "Plinthes assorties au carrelage, collées, joints alignés avec ceux du sol.", "ml", ["Plinthes h = 7 cm"],
               ["plinthe carrelage"]),
            _o("faience", "Revêtements muraux", "FAÏENCE MURALE",
               "Faïence murale collée en pièces humides, hauteurs suivant plans (toute hauteur en douche), y compris profilés "
               "d'angle et de finition.", "m2", ["Faïence 30 x 60 cm"], ["faience"]),
            _o("spec", "Revêtements muraux", "SYSTÈME DE PROTECTION À L'EAU SOUS CARRELAGE",
               "Système de protection à l'eau sous carrelage (SPEC en murs / SEL en sols) sous Avis Technique, en douches et "
               "zones exposées, avec bandes d'angle et manchons de traversée.", "m2", ["SPEC / SEL douches"],
               ["etancheite sous carrelage", "spec", "sel"]),
        ],
    },
    {
        "code": "sols_souples", "numero": 9, "titre": "Revêtements de sols souples – Parquets",
        "motscles": ["parquet", "sol souple", "pvc", "lino", "vinyle", "moquette", "ragreage", "stratifie"],
        "refs": ["NF DTU 51.1 — Pose des parquets à clouer", "NF DTU 51.11 — Pose flottante des parquets et revêtements de sol contrecollés",
                 "NF DTU 51.2 — Parquets collés", "NF DTU 53.12 — Préparation du support pour revêtements de sol souples",
                 "NF DTU 53.2 — Revêtements de sol PVC collés"],
        "prescriptions": [
            ("Préconisations de mise en œuvre", [
                ("Humidité des supports",
                 "Avant toute pose, l'humidité des supports sera mesurée et devra être compatible avec le revêtement et le mode de "
                 "pose. Les bois seront stockés dans les locaux le temps nécessaire à leur mise à l'équilibre hygrométrique."),
                ("Préparation",
                 "Les supports seront préparés par ragréage autolissant de classement adapté au local, après primaire, "
                 "conformément au NF DTU 53.12."),
                ("Jeux et joints",
                 "Un jeu périphérique sera ménagé au droit des parois et des obstacles pour les poses flottantes ; il sera masqué "
                 "par les plinthes ou des profilés."),
            ]),
        ],
        "ouvrages": [
            _o("ragreage", "Préparation des supports", "RAGRÉAGE AUTOLISSANT",
               "Ragréage autolissant fibré ou non, de classement P adapté au local, sur primaire d'accrochage.", "m2",
               ["Ragréage ép. moyenne 3 mm"], ["ragreage"]),
            _o("parquet_flottant", "Parquets", "PARQUET CONTRECOLLÉ POSE FLOTTANTE",
               "Parquet contrecollé à parement en bois noble, essence et finition au choix de l'architecte, posé flottant sur "
               "sous-couche acoustique, y compris barres de seuil et finitions.", "m2", ["Parquet chêne contrecollé verni"],
               ["parquet", "parquet flottant", "contrecolle"]),
            _o("parquet_colle", "Parquets", "PARQUET COLLÉ",
               "Parquet massif ou contrecollé collé en plein sur support préparé, colle adaptée, ponçage et vitrification si "
               "parquet brut.", "m2", ["Parquet chêne massif collé"], ["parquet colle"]),
            _o("sol_pvc", "Revêtements souples", "REVÊTEMENT DE SOL PVC",
               "Revêtement de sol PVC en lés ou en lames, collé sur ragréage, classement UPEC adapté, joints soudés à chaud en "
               "locaux humides, remontée en plinthe le cas échéant.", "m2", ["PVC en lés U3 P3"], ["pvc", "sol souple", "vinyle", "lino"]),
        ],
    },
    {
        "code": "peinture", "numero": 10, "titre": "Peinture – Revêtements muraux",
        "motscles": ["peinture", "enduit", "ratissage", "lasure", "papier peint", "toile de verre"],
        "refs": ["NF DTU 59.1 — Revêtements de peinture en feuil mince, semi-épais ou épais",
                 "NF DTU 59.4 — Mise en œuvre des papiers peints et des revêtements muraux"],
        "prescriptions": [
            ("Préconisations de mise en œuvre", [
                ("Degré de finition",
                 "Sauf indication contraire, la finition sera de type A (soignée) au sens du NF DTU 59.1 dans les pièces de vie et "
                 "de type B (courante) dans les locaux techniques et de service."),
                ("Préparation des fonds",
                 "Les travaux préparatoires (lessivage, égrenage, rebouchage, ratissage, impression) seront adaptés à la nature et à "
                 "l'état des fonds. L'entrepreneur réceptionnera les supports et formulera ses réserves avant intervention."),
                ("Produits",
                 "Les peintures seront en phase aqueuse, à faible émission de COV (étiquetage A+), de teintes au choix de "
                 "l'architecte sur nuancier. Les peintures de pièces humides seront lessivables et adaptées."),
            ]),
        ],
        "ouvrages": [
            _o("peinture_murs", "Peintures intérieures", "PEINTURE DES MURS",
               "Sur plaques de plâtre ou enduits : impression, enduit repassé, ponçage, deux couches de peinture acrylique velours "
               "ou mate.", "m2", ["Finition A, velours", "Finition A, mate"], ["peinture mur", "peinture"]),
            _o("peinture_plafonds", "Peintures intérieures", "PEINTURE DES PLAFONDS",
               "Impression, enduit repassé, ponçage, deux couches de peinture acrylique mate.", "m2", ["Finition A, mate"],
               ["peinture plafond"]),
            _o("peinture_boiseries", "Peintures intérieures", "PEINTURE DES BOISERIES ET MÉTAUX",
               "Peinture des portes, huisseries, plinthes et ouvrages métalliques : préparation, impression adaptée, deux couches "
               "de laque satinée.", "m2", ["Laque satinée"], ["laque", "boiserie"]),
            _o("toile_verre", "Revêtements muraux", "TOILE DE VERRE À PEINDRE",
               "Toile de verre collée sur fonds préparés, recevant deux couches de peinture.", "m2", ["Toile de verre maille moyenne"],
               ["toile de verre"]),
        ],
    },
    {
        "code": "plomberie", "numero": 11, "titre": "Plomberie – Sanitaires",
        "motscles": ["plomberie", "sanitaire", "evacuation", "alimentation eau", "wc", "lavabo", "douche", "baignoire", "chauffe-eau", "evier"],
        "refs": ["NF DTU 60.1 — Plomberie sanitaire pour bâtiments", "NF DTU 60.11 — Règles de calcul des installations de plomberie sanitaire et d'eaux pluviales",
                 "NF DTU 60.31 — Canalisations en PVC non plastifié (eau froide avec pression)",
                 "NF DTU 60.33 — Canalisations en PVC non plastifié (évacuation des eaux usées et eaux vannes)",
                 "NF DTU 60.5 — Canalisations en cuivre", "Arrêté du 30 novembre 2005 — Températures d'eau chaude sanitaire"],
        "prescriptions": [
            ("Préconisations de mise en œuvre", [
                ("Dimensionnement",
                 "Les réseaux seront dimensionnés suivant le NF DTU 60.11. L'entrepreneur établira les plans d'exécution et de "
                 "réservations, les schémas de principe et les notes de calcul, soumis au visa avant exécution."),
                ("Distribution",
                 "Distribution d'eau froide et d'eau chaude en cuivre, PER ou multicouche sous Avis Technique, avec vannes d'arrêt "
                 "par appareil et par zone, réducteur de pression si nécessaire, calorifugeage des réseaux d'eau chaude et des "
                 "réseaux d'eau froide traversant des locaux chauffés ou non chauffés."),
                ("Évacuations",
                 "Évacuations en PVC avec pentes régulières, ventilation primaire en toiture, siphons sur chaque appareil, "
                 "tampons de dégorgement aux changements de direction."),
                ("Essais et mise en service",
                 "Essais d'étanchéité des réseaux avant fermeture des gaines et doublages, rinçage et désinfection des réseaux "
                 "d'eau potable avant mise en service, procès-verbaux remis au maître d'œuvre."),
            ]),
        ],
        "ouvrages": [
            _o("distribution", "Réseaux", "DISTRIBUTION D'EAU FROIDE ET D'EAU CHAUDE",
               "Réseaux de distribution depuis le compteur jusqu'aux appareils, nourrice ou collecteur, vannes d'isolement, "
               "calorifuge.", "ens", ["Distribution complète du logement"], ["alimentation eau", "distribution", "per", "multicouche"]),
            _o("evacuations", "Réseaux", "ÉVACUATIONS EU / EV",
               "Chutes et collecteurs en PVC jusqu'aux attentes du lot VRD, ventilation primaire, raccordement des appareils.", "ens",
               ["Évacuations complètes du logement"], ["evacuation", "eaux usees", "chute"]),
            _o("ecs", "Production d'eau chaude", "PRODUCTION D'EAU CHAUDE SANITAIRE",
               "Production d'eau chaude sanitaire par ballon thermodynamique ou chauffe-eau électrique suivant étude thermique, "
               "groupe de sécurité, raccordements hydrauliques et évacuation.", "u",
               ["Chauffe-eau thermodynamique 200 L", "Chauffe-eau électrique 200 L"], ["chauffe-eau", "ballon", "ecs"]),
            _o("wc", "Appareils sanitaires", "WC SUSPENDUS OU AU SOL",
               "Cuvette en porcelaine vitrifiée, réservoir ou bâti-support autoportant avec plaque de commande double débit, "
               "abattant.", "u", ["WC suspendu sur bâti-support", "WC au sol"], ["wc"]),
            _o("lavabo", "Appareils sanitaires", "LAVABOS ET MEUBLES VASQUES",
               "Lavabo ou meuble vasque, mitigeur, siphon et vidage, raccordements.", "u", ["Meuble vasque 80 cm"], ["lavabo", "vasque"]),
            _o("douche", "Appareils sanitaires", "DOUCHES",
               "Receveur extra-plat ou douche à l'italienne (en coordination avec le lot carrelage), mitigeur thermostatique, "
               "ensemble de douche, paroi vitrée.", "u", ["Receveur 90 x 120 cm"], ["douche"]),
            _o("evier", "Appareils sanitaires", "ATTENTES CUISINE",
               "Attentes eau froide, eau chaude et évacuation pour évier, lave-vaisselle et lave-linge, avec robinets d'arrêt.", "u",
               ["Attentes cuisine et buanderie"], ["evier", "cuisine", "lave-linge"]),
        ],
    },
    {
        "code": "cvc", "numero": 12, "titre": "Chauffage – Ventilation – Climatisation",
        "motscles": ["chauffage", "pac", "pompe a chaleur", "radiateur", "plancher chauffant", "vmc", "ventilation", "climatisation", "chaudiere"],
        "refs": ["NF DTU 65.14 — Exécution de planchers chauffants à eau chaude", "NF DTU 65.16 — Installations de pompes à chaleur",
                 "NF DTU 68.3 — Installations de ventilation mécanique", "NF DTU 24.1 — Travaux de fumisterie",
                 "NF EN 12831 — Méthode de calcul de la charge thermique nominale",
                 "Arrêté du 24 mars 1982 modifié — Aération des logements"],
        "prescriptions": [
            ("Préconisations de mise en œuvre", [
                ("Dimensionnement",
                 "Les installations seront dimensionnées sur la base d'un calcul des déperditions pièce par pièce (NF EN 12831) "
                 "et de l'étude thermique réglementaire. Les débits de ventilation respecteront l'arrêté du 24 mars 1982 modifié."),
                ("Fluides frigorigènes",
                 "Les interventions sur les circuits frigorifiques seront réalisées par une entreprise titulaire de l'attestation de "
                 "capacité requise ; la fiche d'intervention sera remise au maître d'ouvrage."),
                ("Mise en service",
                 "Équilibrage des réseaux, réglage des régulations, mesures des débits de ventilation et procès-verbaux de mise en "
                 "service remis au maître d'œuvre ; formation de l'occupant à l'usage des équipements."),
            ]),
        ],
        "ouvrages": [
            _o("pac_air_eau", "Production de chaleur", "POMPE À CHALEUR AIR / EAU",
               "Pompe à chaleur air/eau, puissance suivant calcul des déperditions, module hydraulique, régulation sur sonde "
               "extérieure, liaisons frigorifiques ou hydrauliques, support antivibratile de l'unité extérieure.", "u",
               ["PAC air/eau réversible"], ["pac", "pompe a chaleur"]),
            _o("plancher_chauffant", "Émission", "PLANCHER CHAUFFANT HYDRAULIQUE",
               "Plancher chauffant à eau basse température : isolant, bande périphérique, tubes PER ou multicouche, collecteurs "
               "avec débitmètres, conforme au NF DTU 65.14 (enrobage par le lot chapes).", "m2", ["Plancher chauffant basse température"],
               ["plancher chauffant", "chauffage sol"]),
            _o("radiateurs", "Émission", "RADIATEURS",
               "Radiateurs acier ou sèche-serviettes, robinets thermostatiques, raccordements.", "u", ["Radiateur acier", "Sèche-serviettes"],
               ["radiateur", "seche-serviettes"]),
            _o("vmc", "Ventilation", "VENTILATION MÉCANIQUE CONTRÔLÉE",
               "VMC simple flux hygroréglable ou double flux suivant étude thermique : caisson, bouches d'extraction, entrées "
               "d'air, gaines isolées en volume non chauffé, rejet en toiture.", "ens",
               ["VMC simple flux hygro B", "VMC double flux haut rendement"], ["vmc", "ventilation"]),
        ],
    },
    {
        "code": "electricite", "numero": 13, "titre": "Électricité – Courants faibles",
        "motscles": ["electri", "prise", "eclairage", "tableau", "interrupteur", "courant faible", "rj45", "luminaire"],
        "refs": ["NF C 15-100 — Installations électriques à basse tension", "NF C 14-100 — Installations de branchement à basse tension",
                 "Guide UTE C 90-483 — Câblage résidentiel des réseaux de communication"],
        "prescriptions": [
            ("Préconisations de mise en œuvre", [
                ("Conformité",
                 "L'installation sera réalisée conformément à la NF C 15-100 dans sa version en vigueur. L'entrepreneur fournira "
                 "l'attestation de conformité visée par le Consuel avant mise sous tension définitive."),
                ("Équipement des pièces",
                 "Le nombre de points d'éclairage, de prises de courant et de circuits spécialisés respectera au minimum les "
                 "exigences de la NF C 15-100 par pièce, complété des équipements indiqués aux plans."),
                ("Courants faibles",
                 "Le réseau de communication sera réalisé à partir d'un tableau de communication avec prises RJ45 de grade "
                 "adapté, conformément au guide UTE C 90-483 et aux exigences de pré-équipement fibre."),
            ]),
        ],
        "ouvrages": [
            _o("chantier_elec", "Installation de chantier", "TABLEAU ÉLECTRIQUE DE CHANTIER",
               "Fourniture, pose et dépose en fin de travaux d'un coffret de chantier adapté à la pose extérieure, à proximité "
               "du point de raccordement, comprenant prises de courant, arrêt d'urgence et protections, ainsi que l'éclairage "
               "provisoire des zones de travail.", "forfait", ["Coffret de chantier et éclairage provisoire"],
               ["tableau de chantier", "installation de chantier", "coffret de chantier"]),
            _o("branchement", "Alimentation générale", "ALIMENTATION GÉNÉRALE ET FOURREAUX",
               "Fourreaux aiguillés entre le coffret du distributeur en limite de propriété et le tableau (alimentation générale, "
               "communication, alimentations extérieures), grillage avertisseur, liaison jusqu'à la gaine technique logement.",
               "forfait", ["Fourreaux et alimentation générale"], ["fourreau", "branchement", "alimentation generale", "enedis"]),
            _o("terre", "Prise de terre", "PRISE DE TERRE ET LIAISONS ÉQUIPOTENTIELLES",
               "Conducteur de terre en fond de fouille sur le périmètre du bâtiment, barrette de terre, liaisons équipotentielles "
               "principales et locales, mesure de la résistance de la prise de terre et amélioration si nécessaire.",
               "forfait", ["Prise de terre et liaisons"], ["prise de terre", "terre", "equipotentielle"]),
            _o("tableau", "Distribution", "TABLEAU DE RÉPARTITION",
               "Tableau électrique avec interrupteurs différentiels 30 mA, disjoncteurs divisionnaires, parafoudre suivant analyse "
               "du risque foudre, réserve de 20 % minimum, repérage des circuits.", "u", ["Tableau 3 rangées"], ["tableau"]),
            _o("prises", "Appareillage", "PRISES DE COURANT",
               "Prises de courant 16 A 2P+T encastrées, appareillage de gamme au choix de l'architecte, y compris câblage et "
               "boîtes d'encastrement.", "u", ["Prise 16 A", "Prise 20/32 A circuits spécialisés"], ["prise"]),
            _o("eclairage", "Appareillage", "POINTS D'ÉCLAIRAGE ET COMMANDES",
               "Points d'éclairage en plafond ou applique avec DCL, commandes simple allumage, va-et-vient ou télérupteur.", "u",
               ["Point lumineux DCL", "Interrupteur"], ["eclairage", "interrupteur", "luminaire"]),
            _o("rj45", "Courants faibles", "RÉSEAU DE COMMUNICATION",
               "Tableau de communication, prises RJ45 dans les pièces principales, câblage catégorie adaptée, prise TV.", "ens",
               ["Réseau grade 2TV"], ["rj45", "courant faible"]),
        ],
    },
]

# Prestations explicitement à la charge de chaque lot (paragraphe « Sont à la charge du présent lot »)
A_CHARGE: dict[str, list[str]] = {
    "demolition": ["la neutralisation des réseaux en liaison avec les concessionnaires et les lots techniques",
                   "les étaiements provisoires nécessaires à la stabilité des ouvrages conservés",
                   "le tri, le chargement et l'évacuation des produits de démolition avec bordereaux de suivi"],
    "vrd": ["l'implantation à partir des repères du géomètre", "l'évacuation ou la mise en dépôt des terres excédentaires",
            "les essais d'étanchéité et inspections des réseaux avant remblaiement", "le grillage avertisseur au-dessus des réseaux"],
    "gros_oeuvre": ["l'installation de chantier, les clôtures et les échafaudages nécessaires à ses ouvrages",
                    "les réservations, trémies et fourreaux demandés en temps utile par les lots techniques",
                    "les plans d'exécution, de coffrage et de ferraillage soumis au visa",
                    "le rebouchage des trémies et réservations après passage des réseaux"],
    "charpente_couverture": ["la note de calcul et les plans de fabrication de la charpente",
                             "les traversées de toiture (ventilation primaire, VMC, conduits) avec accessoires d'étanchéité",
                             "les protections collectives en rive pendant les travaux"],
    "menuiseries_ext": ["les relevés de cotes sur place avant fabrication", "le calfeutrement périphérique et les bavettes",
                        "la pose des entrées d'air fournies ou prescrites par le lot ventilation",
                        "le réglage et le nettoyage des menuiseries et vitrages en fin de chantier"],
    "platrerie": ["le constat des supports et l'implantation des ouvrages", "les renforts pour charges suspendues",
                  "les trappes de visite et les incorporations prévues", "le traitement des joints prêt à peindre"],
    "menuiseries_int": ["la pose des huisseries en coordination avec le lot plâtrerie", "la quincaillerie et les butées",
                        "le détalonnage des portes pour le transit de l'air", "les réglages et la protection jusqu'à la réception"],
    "sols_durs": ["le constat du tracé du trait de niveau permettant de déterminer les arases du sol fini",
                  "les plans d'appareillage et calepinages éventuels des revêtements",
                  "la fourniture et la présentation d'échantillons au maître d'œuvre",
                  "les coupes, entailles, chutes et raccords, ainsi que les seuils et profilés de finition",
                  "la protection et le nettoyage des revêtements et des plinthes"],
    "sols_souples": ["la mesure de l'humidité des supports et la préparation par ragréage",
                     "la fourniture et la présentation d'échantillons au maître d'œuvre",
                     "les barres de seuil, plinthes et profilés de finition", "la protection et le nettoyage des revêtements"],
    "peinture": ["la réception des supports et les travaux préparatoires adaptés à leur nature",
                 "les protections (bâches, adhésifs) et calfeutrements", "les échantillons de teintes sur nuancier",
                 "le nettoyage complet avant réception avec retrait des protections"],
    "plomberie": ["les plans d'exécution et de réservations", "les essais d'étanchéité avant fermeture des gaines",
                  "le rinçage et la désinfection des réseaux avant mise en service", "le compteur ou sous-compteur d'eau si prévu"],
    "cvc": ["la note de dimensionnement (déperditions pièce par pièce)", "les réservations à communiquer aux lots concernés",
            "la mise en service, l'équilibrage et les mesures de débits", "la formation de l'occupant et les notices d'entretien"],
    "electricite": ["le tableau électrique de chantier et l'éclairage provisoire", "la mise à la terre et la mesure de la prise de terre",
                    "l'attestation de conformité visée par le Consuel", "les plans d'implantation et schémas unifilaires"],
}

LOTS_PAR_CODE = {lot["code"]: lot for lot in LOTS}


def references_autorisees(lot: dict) -> list[str]:
    """Liste blanche des documents citables pour un lot (références du lot + communes)."""
    return list(lot.get("refs") or [])
