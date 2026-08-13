/**
 * Full body content of each SEO blog article, keyed by slug.
 * Kept separate from `blogArticles.js` so the metadata stays lean for the index page.
 */

export const ARTICLE_BODIES = {
  "cout-renovation-2026": (
    <>
      <p className="lead">
        En 2026, la fourchette de prix d'une rénovation en France varie de <strong>350 € à 1 800 € HT/m²</strong>{" "}
        selon l'ampleur des travaux, la région et la gamme de finition choisie. Voici les chiffres exacts
        que nous constatons chez les artisans utilisateurs de ConstruPilot, actualisés chaque mois.
      </p>

      <h2>Rénovation légère (rafraîchissement) : 350 – 700 € HT/m²</h2>
      <p>
        Inclut : peinture murs & plafonds, changement des sols souples (moquette, lino), petits travaux
        électriques (prises, interrupteurs), plomberie de surface (mitigeurs, robinetterie). Aucun mur
        ni cloison touché·e.
      </p>

      <h2>Rénovation complète : 900 – 1 400 € HT/m²</h2>
      <p>
        Inclut la rénovation légère + <strong>cloisons non porteuses</strong>, <strong>électricité complète
        (remise aux normes NF C 15-100)</strong>, plomberie neuve, isolation intérieure, cuisine et salle de bain
        neuves, sols durs (parquet, carrelage). C'est la gamme la plus fréquente en France, notamment
        en région parisienne.
      </p>

      <h2>Rénovation lourde : 1 400 – 1 800 € HT/m² (voire plus)</h2>
      <p>
        Ajoute : déplacement de <strong>murs porteurs</strong>, création d'ouvertures, refonte des réseaux,
        isolation par l'extérieur (ITE), remplacement de menuiseries, structure béton ou métal. Nécessite
        toujours un bureau d'études.
      </p>

      <h2>Prix par lot en 2026 (chantier moyen 60 m²)</h2>
      <ul>
        <li><strong>Cuisine équipée</strong> : 8 000 à 25 000 €</li>
        <li><strong>Salle de bain complète</strong> : 6 000 à 15 000 €</li>
        <li><strong>Électricité (remise aux normes)</strong> : 90 à 130 €/m²</li>
        <li><strong>Plomberie complète</strong> : 70 à 110 €/m²</li>
        <li><strong>Isolation intérieure (RT 2020)</strong> : 40 à 80 €/m²</li>
        <li><strong>Peinture (2 couches + apprêt)</strong> : 25 à 45 €/m²</li>
        <li><strong>Parquet massif posé</strong> : 60 à 140 €/m²</li>
        <li><strong>Carrelage grès cérame posé</strong> : 55 à 120 €/m²</li>
      </ul>

      <h2>Écart par région</h2>
      <p>
        Île-de-France : <strong>+18 à 25 %</strong> par rapport à la moyenne nationale. PACA et
        Rhône-Alpes : <strong>+5 à 10 %</strong>. Bretagne, Grand-Est, Nouvelle-Aquitaine : proche de la
        moyenne. Nord, Occitanie : <strong>–5 à 10 %</strong>.
      </p>

      <h2>Comment obtenir un chiffrage précis en 30 secondes ?</h2>
      <p>
        Décrivez votre projet sur <a href="/smart-project" className="text-primary underline">ConstruPilot
        Smart Project</a> : notre IA analyse la description, le calcule par lot, et vous rend un
        devis chiffré à ± 15 %, gratuit et sans inscription.
      </p>
    </>
  ),

  "devis-tva-10-mode-emploi": (
    <>
      <p className="lead">
        La TVA à taux réduit de <strong>10 %</strong> est LE levier fiscal favori des artisans du bâtiment
        pour rendre les devis plus attractifs auprès des particuliers. Voici les 4 conditions à respecter
        pour l'appliquer sans risque de redressement, et l'attestation obligatoire à faire signer.
      </p>

      <h2>Article 279-0 bis du CGI : les 4 conditions cumulatives</h2>
      <ol>
        <li>Le local doit être un <strong>logement d'habitation</strong> (résidence principale ou secondaire).</li>
        <li>L'immeuble doit être <strong>achevé depuis plus de 2 ans</strong> à la date de début des travaux.</li>
        <li>Les travaux doivent porter sur <strong>l'amélioration, la transformation, l'aménagement ou
        l'entretien</strong> — pas sur du gros œuvre neuf.</li>
        <li>Une <strong>attestation signée par le client</strong> doit être remise à l'artisan AVANT
        facturation.</li>
      </ol>

      <h2>Ce qui reste à 20 % même en rénovation</h2>
      <ul>
        <li>Fourniture <strong>seule</strong> (sans pose)</li>
        <li>Ascenseurs, gros équipements de chauffage collectif</li>
        <li>Travaux de <strong>plus de 2/3</strong> de la surface habitable qui deviennent assimilés à un
        neuf</li>
        <li>Terrasses, piscines, portails, aménagements extérieurs (jardin, allée)</li>
      </ul>

      <h2>Attestation TVA 10 % : le modèle 2026</h2>
      <p>
        L'administration fiscale exige un formulaire simplifié (<strong>Cerfa 1300*05</strong>) ou tout
        document équivalent contenant : identité du client, adresse du chantier, nature des travaux, date
        et signature. <strong>Sans cette attestation, vous êtes solidairement responsable du complément
        de TVA en cas de contrôle.</strong>
      </p>

      <h2>Générer automatiquement avec ConstruPilot</h2>
      <p>
        Quand vous cochez « Joindre l'attestation TVA à taux réduit » dans le devis ConstruPilot,
        l'attestation est <strong>générée automatiquement</strong> avec les infos du chantier, jointe au
        devis PDF envoyé au client, et signable en ligne. Vous êtes couvert légalement, votre client
        gagne 10 % — tout le monde y gagne.
      </p>

      <h2>Exemple concret</h2>
      <p>
        Devis rénovation salle de bain <strong>8 000 € HT</strong> :
      </p>
      <ul>
        <li>Sans attestation TVA 10 % → 8 000 × 1,20 = <strong>9 600 € TTC</strong></li>
        <li>Avec attestation TVA 10 % → 8 000 × 1,10 = <strong>8 800 € TTC</strong></li>
        <li>Économie client : <strong>800 €</strong></li>
      </ul>
    </>
  ),

  "guide-metre-2d": (
    <>
      <p className="lead">
        Métrer un plan d'architecte, une esquisse client ou même un plan cadastral pour chiffrer un
        chantier prenait facilement <strong>2 à 3 heures</strong> avec les outils classiques
        (AutoCAD, Revit, mètre + calculatrice). Voici la méthode 2026 pour le faire en <strong>5
        minutes</strong>, avec précision au centimètre.
      </p>

      <h2>Étape 1 — Uploader le plan (PDF, PNG, DXF)</h2>
      <p>
        Depuis <a href="/plan" className="text-primary underline">/plan</a>, glissez-déposez votre plan.
        ConstruPilot accepte PDF vectoriel, PDF scanné, PNG haute résolution et fichiers DXF issus
        d'AutoCAD ou de logiciels d'architecte.
      </p>

      <h2>Étape 2 — Calibrer à l'échelle réelle</h2>
      <p>
        Cliquez deux points de référence dont vous connaissez la distance réelle (par exemple : le côté
        d'une pièce ou une porte standard de 83 cm). ConstruPilot déduit automatiquement l'échelle
        <strong> m/pixel</strong> pour tout le plan. Cette étape prend <strong>10 secondes</strong>.
      </p>

      <h2>Étape 3 — Détection automatique des murs (OpenCV)</h2>
      <p>
        Cliquez sur « Détecter murs » : l'IA détecte les traits noirs, filtre le bruit et reconstruit les
        segments de murs. Vous validez ou corrigez en 30 secondes.
      </p>

      <h2>Étape 4 — Étiqueter les pièces</h2>
      <p>
        Cliquez à l'intérieur d'une pièce, tapez son nom (cuisine, salon, ch. parents…). ConstruPilot
        calcule instantanément la <strong>surface m²</strong>, le <strong>périmètre</strong> et l'<strong>
        aire des murs</strong> pour la peinture / le placo.
      </p>

      <h2>Étape 5 — Chiffrer le chantier</h2>
      <p>
        Un clic sur « Lancer l'estimation » : les surfaces mesurées alimentent le moteur d'estimation
        ConstruPilot qui calcule les lots (peinture, sol, placo, plinthes, TVA) avec les prix France
        2026. Un second clic génère le <strong>devis PDF prêt à envoyer</strong>, avec attestation TVA
        10 % et signature électronique client.
      </p>

      <h2>Bonus 2026 : le rendu 3D IA</h2>
      <p>
        Depuis la même page, cliquez « Voir en 3D » : ConstruPilot génère un rendu 3D IA
        (isométrique / photoréaliste / intérieur) et même un <strong>tour vidéo MP4</strong> avec
        watermark et musique d'ambiance à joindre à votre devis. Effet <em>wow</em> garanti sur le
        client.
      </p>

      <h2>Précision</h2>
      <p>
        Sur les plans vectoriels PDF ou DXF, la précision est <strong>&lt; 1 %</strong>. Sur les plans
        scannés ou photographiés, comptez <strong>3-5 %</strong> selon la qualité — largement suffisant
        pour un devis client.
      </p>
    </>
  ),

  "abattre-mur-porteur-reglementation": (
    <>
      <p className="lead">
        Ouvrir un mur porteur, c'est le rêve de tous les propriétaires qui veulent une pièce à vivre
        décloisonnée. C'est aussi <strong>l'un des chantiers les plus encadrés légalement</strong>. Voici
        la procédure complète 2026, le prix moyen, et les 3 pièges qui font capoter 1 chantier sur 4
        en copropriété.
      </p>

      <h2>Comment savoir si un mur est porteur ?</h2>
      <p>
        Trois indices concordants : (1) épaisseur supérieure à <strong>15 cm</strong>, (2) situé au
        droit d'une fondation ou d'un mur du dessous (relever le plan), (3) sonorité mate au marteau.
        En doute → <strong>bureau d'études structure obligatoire</strong>. Coût : 350 à 900 € pour un
        rapport de sondage.
      </p>

      <h2>Les 5 étapes légales obligatoires</h2>
      <ol>
        <li><strong>Diagnostic structure</strong> par bureau d'études (BE) : 500 à 1 200 €.</li>
        <li><strong>Note de calcul</strong> validant la section d'IPN ou HEA. Le BE dimensionne
        la poutre nécessaire selon la portée et les charges.</li>
        <li><strong>Autorisation copropriété</strong> (AG obligatoire, majorité art. 25 loi 1965).
        Sans elle, vous êtes exposé à démolition + dommages-intérêts.</li>
        <li><strong>Déclaration préalable de travaux</strong> en mairie (aucun permis nécessaire
        si façade non modifiée). Délai 1 mois.</li>
        <li><strong>Réalisation par entreprise assurée décennale</strong>. La décennale du BE ne
        couvre PAS l'exécution.</li>
      </ol>

      <h2>Prix moyens 2026 en France</h2>
      <ul>
        <li>Ouverture <strong>2 mètres</strong> (IPN) : <strong>3 500 à 6 000 €</strong> TTC.</li>
        <li>Ouverture <strong>3 à 4 mètres</strong> (HEA 200) : <strong>7 000 à 12 000 €</strong> TTC.</li>
        <li>Ouverture <strong>&gt; 4 mètres</strong> (double HEA) : à partir de <strong>15 000 €</strong>.</li>
        <li>Habillage / placo / peinture (finition) : <strong>+ 800 à 1 500 €</strong>.</li>
      </ul>

      <h2>Les 3 pièges à éviter</h2>
      <p>
        <strong>Piège 1 :</strong> croire qu'un mur de refend n'est pas porteur. En copropriété
        ancienne (Haussmann, brique), 70 % des refends portent des solives.
      </p>
      <p>
        <strong>Piège 2 :</strong> zapper l'AG copropriété « parce que c'est chez moi ». Un syndic peut
        engager une action en démolition sous 10 ans (prescription trentenaire pour les modifications
        structurelles). Coût du redressement moyen : <strong>25 000 €</strong>.
      </p>
      <p>
        <strong>Piège 3 :</strong> prendre une entreprise sans <strong>décennale spécifique
        « gros œuvre + structure »</strong>. Une décennale « peinture-plâtrerie » ne couvre PAS une
        ouverture d'IPN.
      </p>

      <h2>Chiffrez en 30 secondes avec ConstruPilot</h2>
      <p>
        Ajoutez « ouverture mur porteur 3m » à votre description sur{" "}
        <a href="/smart-project" className="text-primary underline">Smart Project</a> : l'IA détecte
        automatiquement la nécessité d'un BE, le lot IPN, et vous chiffre à ± 15 % — coach IA compris
        pour vous alerter sur les obligations légales.
      </p>
    </>
  ),

  "permis-construire-2026": (
    <>
      <p className="lead">
        En 2026, les seuils d'obligation du permis de construire ont légèrement bougé avec la loi
        Climat & Résilience et la simplification des procédures d'urbanisme. Voici les cas clairs pour
        savoir <strong>qui doit déposer un permis (PC), une déclaration préalable (DP), ou rien
        du tout</strong>, avec les délais réels observés en préfecture.
      </p>

      <h2>Extension : DP jusqu'à 40 m², PC au-delà</h2>
      <ul>
        <li><strong>≤ 5 m² d'emprise au sol</strong> : aucune formalité (garage à vélo, abri de
        jardin).</li>
        <li><strong>5 à 20 m²</strong> (hors zones U du PLU) : <strong>déclaration préalable</strong>.</li>
        <li><strong>5 à 40 m²</strong> (en zone U du PLU) : <strong>déclaration préalable</strong>.</li>
        <li><strong>Au-delà de 40 m² OU si la surface totale dépasse 150 m²</strong>{" "}
        (recours obligatoire à l'architecte) : <strong>permis de construire</strong>.</li>
      </ul>

      <h2>Surélévation, garage, piscine, ravalement</h2>
      <ul>
        <li><strong>Surélévation créant de la surface</strong> : PC si &gt; 20 m² (40 m² en zone U).</li>
        <li><strong>Garage attenant</strong> : DP jusqu'à 20 m², PC au-delà.</li>
        <li><strong>Piscine enterrée</strong> : DP pour un bassin ≤ 100 m² sans abri fixe. PC si abri
        fixe &gt; 1,80 m.</li>
        <li><strong>Ravalement de façade + changement d'aspect</strong> : DP (couleur, matériau).</li>
        <li><strong>Changement de destination</strong> (garage → chambre, commerce → logement) :
        DP obligatoire même sans travaux visibles.</li>
      </ul>

      <h2>Délais réels 2026 (préfectures)</h2>
      <ul>
        <li><strong>Déclaration préalable</strong> : 1 mois d'instruction (2 mois si zone protégée
        ABF). Silence = accord tacite.</li>
        <li><strong>Permis de construire maison individuelle</strong> : 2 mois. En pratique 8 à
        14 semaines avec compléments.</li>
        <li><strong>Permis de construire lotissement / ERP</strong> : 3 mois, souvent prolongé à 6.</li>
      </ul>

      <h2>Pièces à fournir</h2>
      <p>Cerfa 13703 (DP) ou 13406 (PC) + plan de situation + plan de masse + plan de coupe + plan
      des façades + notice descriptive + photos. Total : <strong>8 à 12 pièces</strong> selon le projet.
      Un géomètre pour le plan de masse coûte 300 à 700 € ; un architecte 3 à 8 % du montant travaux.</p>

      <h2>Coût moyen constitution dossier</h2>
      <ul>
        <li>DP en autonomie : <strong>0 €</strong> (à part le géomètre éventuel).</li>
        <li>DP par architecte : <strong>500 à 1 500 €</strong>.</li>
        <li>PC maison individuelle par architecte : <strong>3 000 à 8 000 €</strong>.</li>
      </ul>

      <h2>Astuce ConstruPilot</h2>
      <p>
        Quand vous décrivez votre projet sur{" "}
        <a href="/smart-project" className="text-primary underline">Smart Project</a>, notre coach IA
        détecte si vos travaux nécessitent DP ou PC, et vous alerte AVANT de commencer — évitant
        redressement (mise en conformité rétroactive : 15 000 à 50 000 €).
      </p>
    </>
  ),

  "re2020-renovation-guide": (
    <>
      <p className="lead">
        La <strong>Réglementation Environnementale 2020 (RE2020)</strong> a d'abord ciblé la
        construction neuve depuis 2022. En 2026, elle s'étend progressivement à la{" "}
        <strong>rénovation d'ampleur</strong>. Voici ce que tout artisan et particulier doit connaître
        pour rester dans les clous — et transformer la contrainte en argument commercial.
      </p>

      <h2>Quand la RE2020 s'applique-t-elle en rénovation ?</h2>
      <p>
        Depuis 2024, la RE2020 s'applique à toute <strong>rénovation lourde qui touche plus de 25 %
        des parois de l'enveloppe</strong> (murs extérieurs, toiture, ouvertures) ou dont le coût
        dépasse <strong>25 % de la valeur du bien</strong>. Le seuil sera abaissé à 20 % en 2027.
      </p>

      <h2>Les 3 indicateurs à respecter</h2>
      <ol>
        <li><strong>Bbio (Besoin bioclimatique)</strong> : mesure l'efficacité passive du bâtiment
        (orientation, inertie, ouvertures). Seuil rénovation lourde : <strong>Bbio_max × 1,3</strong>.</li>
        <li><strong>Cep (Consommation énergétique primaire)</strong> : ≤ <strong>70 kWh/m²/an</strong>
        après travaux (contre 50 en neuf). Chauffage, ECS, refroidissement, éclairage inclus.</li>
        <li><strong>Ic Énergie + Ic Construction</strong> (empreinte carbone) : plafond
        <strong> 1 800 kgCO₂/m²</strong> sur 50 ans en rénovation d'ampleur.</li>
      </ol>

      <h2>Isolation minimale imposée</h2>
      <ul>
        <li><strong>Murs extérieurs</strong> : R ≥ <strong>4,4 m².K/W</strong> (soit 14 cm laine
        de verre ou 12 cm biosourcée).</li>
        <li><strong>Toiture / combles</strong> : R ≥ <strong>7,0 m².K/W</strong> (24 cm minimum).</li>
        <li><strong>Planchers bas</strong> : R ≥ <strong>3,0 m².K/W</strong>.</li>
        <li><strong>Menuiseries</strong> : Uw ≤ 1,3 W/m².K (double vitrage argon obligatoire, triple
        recommandé au Nord).</li>
      </ul>

      <h2>Matériaux à privilégier pour le carbone</h2>
      <p>
        Béton bas carbone (CEM III, laitier), ossature bois, isolants biosourcés (chanvre, ouate de
        cellulose, laine de bois). Un DPE en RE2020 valorise ces matériaux : compter un bonus de
        <strong> 30 à 60 kgCO₂/m²</strong> économisés vs équivalents traditionnels.
      </p>

      <h2>Aides financières 2026</h2>
      <ul>
        <li>MaPrimeRénov' : jusqu'à <strong>63 000 €</strong> pour une rénovation performante,
        forfait bonus RE2020.</li>
        <li>Éco-PTZ : <strong>50 000 €</strong> sans intérêts sur 20 ans.</li>
        <li>TVA à 5,5 % sur les travaux d'amélioration énergétique performants.</li>
        <li>CEE (Certificats d'économie d'énergie) : cumulables avec les aides publiques.</li>
      </ul>

      <h2>ConstruPilot vous alerte automatiquement</h2>
      <p>
        Quand votre estimation dépasse 25 % de valeur du bien ou touche l'enveloppe, le coach IA
        vous notifie de l'obligation RE2020 dans le devis, calcule les Bbio/Cep prévisionnels et
        vous rappelle les aides disponibles pour chaque poste. Un{" "}
        <strong>argument commercial imparable</strong> face à un particulier qui hésite.
      </p>
    </>
  ),
};
