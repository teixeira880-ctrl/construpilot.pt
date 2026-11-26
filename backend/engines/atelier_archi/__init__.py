"""Atelier Architecte — esquisse à la main levée, photo de croquis ou prompt → maquette du Studio de projet.

Le module ne crée pas un second modèle de bâtiment : tout ce qu'il produit est un modèle du Studio de projet
(`engines.estudio_projeto`), donc les mêmes plans, façades, coupes, métrés, DXF, IFC et PDF que le Studio.

- `programme`  : prompt en langage courant → programme (pièces, surfaces, niveaux, toiture), déterministe ;
- `generateur` : programme → plan rangé (bande avant / circulation / bande jardin), portes et fenêtres ;
- `croquis`    : traits dessinés à la main (souris, doigt, stylet) ou lus sur une photo → murs droits, raccordés ;
- `vision`     : photo d'un croquis papier → traits (IA vision), puis même nettoyage que le dessin à la main ;
- `dce`        : maquette → sélection de lots et lignes quantifiées pour le rédacteur CCTP / DPGF.

Règle : les quantités qui partent vers le CCTP viennent uniquement du métré de la maquette. Ce qui est supposé
(surfaces types, hauteur sous plafond, menuiseries) est écrit dans les avertissements.
"""
