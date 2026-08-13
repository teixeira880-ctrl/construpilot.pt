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
};
