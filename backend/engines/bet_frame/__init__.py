"""bet_frame — moteur BET des bâtiments à ossature béton armé (poteaux, poutres, dalles).

Couvre ce que bet_core (maison individuelle en maçonnerie porteuse) ne couvre pas : immeubles collectifs,
bureaux, commerces, parkings, bâtiments publics sur trame de poteaux. Même principe : l'IA lit, le code calcule,
un vérificateur contrôle. Aucune valeur structurelle n'est produite par un LLM.

    FrameModel (JSON) ─► model.load + checks ─► calc (charges EN 1991, dalles, poutres continues, poteaux
    flexion composée EN 1992, semelles, quantités) ─► mep (colonnes montantes eau / eaux usées / électricité)
    ─► sheets (fondations, coffrage par niveau, tableaux, coupe, plans de niveaux, réseaux, schémas verticaux)
    ─► report (note de calcul A4) + devis (Excel à formules) + DXF.
"""
