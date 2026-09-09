"""Bibliothèque perso — ouvrages & matériaux avec prix définis par l'entreprise.

- Catalogue de départ pré-rempli (seed une seule fois par utilisateur).
- Réutilisable dans l'éditeur de devis (étape suivante).
- CRUD complet ; chaque nouvel ouvrage saisi est enregistré dans la bibliothèque perso.
"""
from __future__ import annotations

import re
import secrets
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from core.db import db
from core.security import current_user

router = APIRouter(tags=["library"], prefix="/library")

UNITS = ["u", "m²", "ml", "m³", "forfait", "ens", "h", "j", "kg", "L"]


# Catálogo de partida PT-PT (biblioteca_pt_2026.xlsx, gama Standard).
# Gerado automaticamente por scripts/import_biblioteca_pt_2026.py.
# Prix indicatifs sem IVA; cada empresa pode ajustar.
# Auto-gerado a partir de biblioteca_pt_2026.xlsx — 322 items PT-PT
STARTER_CATALOGUE: list[dict] = [
    {'code': 'PT-01-001', 'type': 'ouvrage', 'category': 'Instalação de estaleiro', 'designation': 'Instalação e desmontagem de estaleiro', 'unit': 'forfait', 'unit_price_ht': 990.0, 'vat_rate': 23},
    {'code': 'PT-01-002', 'type': 'ouvrage', 'category': 'Instalação de estaleiro', 'designation': 'Instalação e desmontagem de estaleiro', 'unit': 'm²', 'unit_price_ht': 4.62, 'vat_rate': 23},
    {'code': 'PT-01-003', 'type': 'ouvrage', 'category': 'Instalação de estaleiro', 'designation': 'Instalação e desmontagem de estaleiro', 'unit': 'm²', 'unit_price_ht': 3.96, 'vat_rate': 23},
    {'code': 'PT-01-004', 'type': 'ouvrage', 'category': 'Instalação de estaleiro', 'designation': 'Instalação e desmontagem de estaleiro', 'unit': 'un', 'unit_price_ht': 429.0, 'vat_rate': 23},
    {'code': 'PT-01-005', 'type': 'ouvrage', 'category': 'Instalação de estaleiro', 'designation': 'Instalação e desmontagem de estaleiro', 'unit': 'm²', 'unit_price_ht': 18.48, 'vat_rate': 23},
    {'code': 'PT-01-006', 'type': 'ouvrage', 'category': 'Instalação de estaleiro', 'designation': 'Instalação e desmontagem de estaleiro', 'unit': 'm²', 'unit_price_ht': 5.94, 'vat_rate': 23},
    {'code': 'PT-02-001', 'type': 'ouvrage', 'category': 'Demolições / Remoções', 'designation': 'Instalação e desmontagem de estaleiro', 'unit': 'm²', 'unit_price_ht': 14.52, 'vat_rate': 23},
    {'code': 'PT-02-002', 'type': 'ouvrage', 'category': 'Demolições / Remoções', 'designation': 'Instalação e desmontagem de estaleiro', 'unit': 'm²', 'unit_price_ht': 36.3, 'vat_rate': 23},
    {'code': 'PT-02-003', 'type': 'ouvrage', 'category': 'Demolições / Remoções', 'designation': 'Instalação e desmontagem de estaleiro', 'unit': 'm²', 'unit_price_ht': 56.1, 'vat_rate': 23},
    {'code': 'PT-02-004', 'type': 'ouvrage', 'category': 'Demolições / Remoções', 'designation': 'Instalação e desmontagem de estaleiro', 'unit': 'm²', 'unit_price_ht': 18.48, 'vat_rate': 23},
    {'code': 'PT-02-005', 'type': 'ouvrage', 'category': 'Demolições / Remoções', 'designation': 'Instalação e desmontagem de estaleiro', 'unit': 'm²', 'unit_price_ht': 11.88, 'vat_rate': 23},
    {'code': 'PT-02-006', 'type': 'ouvrage', 'category': 'Demolições / Remoções', 'designation': 'Instalação e desmontagem de estaleiro', 'unit': 'm²', 'unit_price_ht': 13.2, 'vat_rate': 23},
    {'code': 'PT-02-007', 'type': 'ouvrage', 'category': 'Demolições / Remoções', 'designation': 'Instalação e desmontagem de estaleiro', 'unit': 'un', 'unit_price_ht': 79.2, 'vat_rate': 23},
    {'code': 'PT-02-008', 'type': 'ouvrage', 'category': 'Demolições / Remoções', 'designation': 'Instalação e desmontagem de estaleiro', 'unit': 'un', 'unit_price_ht': 42.9, 'vat_rate': 23},
    {'code': 'PT-03-001', 'type': 'ouvrage', 'category': 'Movimentos de terras', 'designation': 'Instalação e desmontagem de estaleiro', 'unit': 'm²', 'unit_price_ht': 7.92, 'vat_rate': 23},
    {'code': 'PT-03-002', 'type': 'ouvrage', 'category': 'Movimentos de terras', 'designation': 'Instalação e desmontagem de estaleiro', 'unit': 'm³', 'unit_price_ht': 25.08, 'vat_rate': 23},
    {'code': 'PT-03-003', 'type': 'ouvrage', 'category': 'Movimentos de terras', 'designation': 'Instalação e desmontagem de estaleiro', 'unit': 'ml', 'unit_price_ht': 27.72, 'vat_rate': 23},
    {'code': 'PT-03-004', 'type': 'ouvrage', 'category': 'Movimentos de terras', 'designation': 'Instalação e desmontagem de estaleiro', 'unit': 'm³', 'unit_price_ht': 29.7, 'vat_rate': 23},
    {'code': 'PT-03-005', 'type': 'ouvrage', 'category': 'Movimentos de terras', 'designation': 'Instalação e desmontagem de estaleiro', 'unit': 'm³', 'unit_price_ht': 25.08, 'vat_rate': 23},
    {'code': 'PT-03-006', 'type': 'ouvrage', 'category': 'Movimentos de terras', 'designation': 'Instalação e desmontagem de estaleiro', 'unit': 'm³', 'unit_price_ht': 34.32, 'vat_rate': 23},
    {'code': 'PT-03-007', 'type': 'ouvrage', 'category': 'Movimentos de terras', 'designation': 'Instalação e desmontagem de estaleiro', 'unit': 'ml', 'unit_price_ht': 36.3, 'vat_rate': 23},
    {'code': 'PT-04-001', 'type': 'ouvrage', 'category': 'Fundações', 'designation': 'Instalação e desmontagem de estaleiro', 'unit': 'm²', 'unit_price_ht': 12.96, 'vat_rate': 23},
    {'code': 'PT-04-002', 'type': 'ouvrage', 'category': 'Fundações', 'designation': 'Instalação e desmontagem de estaleiro', 'unit': 'ml', 'unit_price_ht': 68.4, 'vat_rate': 23},
    {'code': 'PT-04-003', 'type': 'ouvrage', 'category': 'Fundações', 'designation': 'Instalação e desmontagem de estaleiro', 'unit': 'un', 'unit_price_ht': 302.4, 'vat_rate': 23},
    {'code': 'PT-04-004', 'type': 'ouvrage', 'category': 'Fundações', 'designation': 'Instalação e desmontagem de estaleiro', 'unit': 'ml', 'unit_price_ht': 97.2, 'vat_rate': 23},
    {'code': 'PT-04-005', 'type': 'ouvrage', 'category': 'Fundações', 'designation': 'Instalação e desmontagem de estaleiro', 'unit': 'm²', 'unit_price_ht': 104.4, 'vat_rate': 23},
    {'code': 'PT-04-006', 'type': 'ouvrage', 'category': 'Fundações', 'designation': 'Instalação e desmontagem de estaleiro', 'unit': 'm³', 'unit_price_ht': 302.4, 'vat_rate': 23},
    {'code': 'PT-05-001', 'type': 'ouvrage', 'category': 'Betão armado', 'designation': 'Instalação e desmontagem de estaleiro', 'unit': 'm³', 'unit_price_ht': 182.0, 'vat_rate': 23},
    {'code': 'PT-05-002', 'type': 'ouvrage', 'category': 'Betão armado', 'designation': 'Instalação e desmontagem de estaleiro', 'unit': 'm²', 'unit_price_ht': 40.6, 'vat_rate': 23},
    {'code': 'PT-05-003', 'type': 'ouvrage', 'category': 'Betão armado', 'designation': 'Instalação e desmontagem de estaleiro', 'unit': 'm²', 'unit_price_ht': 45.5, 'vat_rate': 23},
    {'code': 'PT-05-004', 'type': 'ouvrage', 'category': 'Betão armado', 'designation': 'Instalação e desmontagem de estaleiro', 'unit': 'kg', 'unit_price_ht': 2.24, 'vat_rate': 23},
    {'code': 'PT-05-005', 'type': 'ouvrage', 'category': 'Betão armado', 'designation': 'Instalação e desmontagem de estaleiro', 'unit': 'ml', 'unit_price_ht': 105.0, 'vat_rate': 23},
    {'code': 'PT-05-006', 'type': 'ouvrage', 'category': 'Betão armado', 'designation': 'Instalação e desmontagem de estaleiro', 'unit': 'ml', 'unit_price_ht': 133.0, 'vat_rate': 23},
    {'code': 'PT-05-007', 'type': 'ouvrage', 'category': 'Betão armado', 'designation': 'Instalação e desmontagem de estaleiro', 'unit': 'm²', 'unit_price_ht': 80.5, 'vat_rate': 23},
    {'code': 'PT-06-001', 'type': 'ouvrage', 'category': 'Alvenaria de blocos', 'designation': 'Instalação e desmontagem de estaleiro', 'unit': 'm²', 'unit_price_ht': 37.4, 'vat_rate': 23},
    {'code': 'PT-06-002', 'type': 'ouvrage', 'category': 'Alvenaria de blocos', 'designation': 'Instalação e desmontagem de estaleiro', 'unit': 'm²', 'unit_price_ht': 42.16, 'vat_rate': 23},
    {'code': 'PT-06-003', 'type': 'ouvrage', 'category': 'Alvenaria de blocos', 'designation': 'Instalação e desmontagem de estaleiro', 'unit': 'm²', 'unit_price_ht': 48.96, 'vat_rate': 23},
    {'code': 'PT-06-004', 'type': 'ouvrage', 'category': 'Alvenaria de blocos', 'designation': 'Instalação e desmontagem de estaleiro', 'unit': 'm²', 'unit_price_ht': 85.0, 'vat_rate': 23},
    {'code': 'PT-06-005', 'type': 'ouvrage', 'category': 'Alvenaria de blocos', 'designation': 'Instalação e desmontagem de estaleiro', 'unit': 'm²', 'unit_price_ht': 64.6, 'vat_rate': 23},
    {'code': 'PT-06-006', 'type': 'ouvrage', 'category': 'Alvenaria de blocos', 'designation': 'Instalação e desmontagem de estaleiro', 'unit': 'ml', 'unit_price_ht': 30.6, 'vat_rate': 23},
    {'code': 'PT-06-007', 'type': 'ouvrage', 'category': 'Alvenaria de blocos', 'designation': 'Instalação e desmontagem de estaleiro', 'unit': 'ml', 'unit_price_ht': 32.64, 'vat_rate': 23},
    {'code': 'PT-06-008', 'type': 'ouvrage', 'category': 'Alvenaria de blocos', 'designation': 'Instalação e desmontagem de estaleiro', 'unit': 'ml', 'unit_price_ht': 57.8, 'vat_rate': 23},
    {'code': 'PT-07-001', 'type': 'ouvrage', 'category': 'Tijolo', 'designation': 'Instalação e desmontagem de estaleiro', 'unit': 'm²', 'unit_price_ht': 54.12, 'vat_rate': 23},
    {'code': 'PT-07-002', 'type': 'ouvrage', 'category': 'Tijolo', 'designation': 'Instalação e desmontagem de estaleiro', 'unit': 'm²', 'unit_price_ht': 31.68, 'vat_rate': 23},
    {'code': 'PT-07-003', 'type': 'ouvrage', 'category': 'Tijolo', 'designation': 'Instalação e desmontagem de estaleiro', 'unit': 'm²', 'unit_price_ht': 89.1, 'vat_rate': 23},
    {'code': 'PT-07-004', 'type': 'ouvrage', 'category': 'Tijolo', 'designation': 'Instalação e desmontagem de estaleiro', 'unit': 'm²', 'unit_price_ht': 75.9, 'vat_rate': 23},
    {'code': 'PT-07-005', 'type': 'ouvrage', 'category': 'Tijolo', 'designation': 'Instalação e desmontagem de estaleiro', 'unit': 'ml', 'unit_price_ht': 49.5, 'vat_rate': 23},
    {'code': 'PT-08-001', 'type': 'ouvrage', 'category': 'Fachadas / Rebocos', 'designation': 'Instalação e desmontagem de estaleiro', 'unit': 'm²', 'unit_price_ht': 27.72, 'vat_rate': 23},
    {'code': 'PT-08-002', 'type': 'ouvrage', 'category': 'Fachadas / Rebocos', 'designation': 'Instalação e desmontagem de estaleiro', 'unit': 'm²', 'unit_price_ht': 49.5, 'vat_rate': 23},
    {'code': 'PT-08-003', 'type': 'ouvrage', 'category': 'Fachadas / Rebocos', 'designation': 'Instalação e desmontagem de estaleiro', 'unit': 'm²', 'unit_price_ht': 15.84, 'vat_rate': 23},
    {'code': 'PT-08-004', 'type': 'ouvrage', 'category': 'Fachadas / Rebocos', 'designation': 'Instalação e desmontagem de estaleiro', 'unit': 'm²', 'unit_price_ht': 21.12, 'vat_rate': 23},
    {'code': 'PT-08-005', 'type': 'ouvrage', 'category': 'Fachadas / Rebocos', 'designation': 'Instalação e desmontagem de estaleiro', 'unit': 'm²', 'unit_price_ht': 56.1, 'vat_rate': 23},
    {'code': 'PT-08-006', 'type': 'ouvrage', 'category': 'Fachadas / Rebocos', 'designation': 'Instalação e desmontagem de estaleiro', 'unit': 'm²', 'unit_price_ht': 95.7, 'vat_rate': 23},
    {'code': 'PT-09-001', 'type': 'ouvrage', 'category': 'Isolamento exterior ETICS', 'designation': 'Instalação e desmontagem de estaleiro', 'unit': 'm²', 'unit_price_ht': 75.0, 'vat_rate': 23},
    {'code': 'PT-09-002', 'type': 'ouvrage', 'category': 'Isolamento exterior ETICS', 'designation': 'Instalação e desmontagem de estaleiro', 'unit': 'm²', 'unit_price_ht': 85.0, 'vat_rate': 23},
    {'code': 'PT-09-003', 'type': 'ouvrage', 'category': 'Isolamento exterior ETICS', 'designation': 'Instalação e desmontagem de estaleiro', 'unit': 'm²', 'unit_price_ht': 97.5, 'vat_rate': 23},
    {'code': 'PT-09-004', 'type': 'ouvrage', 'category': 'Isolamento exterior ETICS', 'designation': 'Instalação e desmontagem de estaleiro', 'unit': 'm²', 'unit_price_ht': 110.0, 'vat_rate': 23},
    {'code': 'PT-09-005', 'type': 'ouvrage', 'category': 'Isolamento exterior ETICS', 'designation': 'Instalação e desmontagem de estaleiro', 'unit': 'm²', 'unit_price_ht': 67.5, 'vat_rate': 23},
    {'code': 'PT-09-006', 'type': 'ouvrage', 'category': 'Isolamento exterior ETICS', 'designation': 'Instalação e desmontagem de estaleiro', 'unit': 'ml', 'unit_price_ht': 9.0, 'vat_rate': 23},
    {'code': 'PT-10-001', 'type': 'ouvrage', 'category': 'Isolamento interior', 'designation': 'Instalação e desmontagem de estaleiro', 'unit': 'm²', 'unit_price_ht': 38.28, 'vat_rate': 23},
    {'code': 'PT-10-002', 'type': 'ouvrage', 'category': 'Isolamento interior', 'designation': 'Instalação e desmontagem de estaleiro', 'unit': 'm²', 'unit_price_ht': 34.32, 'vat_rate': 23},
    {'code': 'PT-10-003', 'type': 'ouvrage', 'category': 'Isolamento interior', 'designation': 'Instalação e desmontagem de estaleiro', 'unit': 'm²', 'unit_price_ht': 31.68, 'vat_rate': 23},
    {'code': 'PT-10-004', 'type': 'ouvrage', 'category': 'Isolamento interior', 'designation': 'Instalação e desmontagem de estaleiro', 'unit': 'm²', 'unit_price_ht': 23.1, 'vat_rate': 23},
    {'code': 'PT-10-005', 'type': 'ouvrage', 'category': 'Isolamento interior', 'designation': 'Instalação e desmontagem de estaleiro', 'unit': 'm²', 'unit_price_ht': 29.7, 'vat_rate': 23},
    {'code': 'PT-10-006', 'type': 'ouvrage', 'category': 'Isolamento interior', 'designation': 'Instalação e desmontagem de estaleiro', 'unit': 'm²', 'unit_price_ht': 18.48, 'vat_rate': 23},
    {'code': 'PT-11-001', 'type': 'ouvrage', 'category': 'Carpintaria estrutural', 'designation': 'Instalação e desmontagem de estaleiro', 'unit': 'm²', 'unit_price_ht': 95.7, 'vat_rate': 23},
    {'code': 'PT-11-002', 'type': 'ouvrage', 'category': 'Carpintaria estrutural', 'designation': 'Instalação e desmontagem de estaleiro', 'unit': 'm²', 'unit_price_ht': 69.3, 'vat_rate': 23},
    {'code': 'PT-11-003', 'type': 'ouvrage', 'category': 'Carpintaria estrutural', 'designation': 'Instalação e desmontagem de estaleiro', 'unit': 'ml', 'unit_price_ht': 79.2, 'vat_rate': 23},
    {'code': 'PT-11-004', 'type': 'ouvrage', 'category': 'Carpintaria estrutural', 'designation': 'Instalação e desmontagem de estaleiro', 'unit': 'm²', 'unit_price_ht': 18.48, 'vat_rate': 23},
    {'code': 'PT-11-005', 'type': 'ouvrage', 'category': 'Carpintaria estrutural', 'designation': 'Instalação e desmontagem de estaleiro', 'unit': 'ml', 'unit_price_ht': 95.7, 'vat_rate': 23},
    {'code': 'PT-12-001', 'type': 'ouvrage', 'category': 'Coberturas', 'designation': 'Instalação e desmontagem de estaleiro', 'unit': 'm²', 'unit_price_ht': 83.75, 'vat_rate': 23},
    {'code': 'PT-12-002', 'type': 'ouvrage', 'category': 'Coberturas', 'designation': 'Instalação e desmontagem de estaleiro', 'unit': 'm²', 'unit_price_ht': 110.55, 'vat_rate': 23},
    {'code': 'PT-12-003', 'type': 'ouvrage', 'category': 'Coberturas', 'designation': 'Instalação e desmontagem de estaleiro', 'unit': 'm²', 'unit_price_ht': 140.7, 'vat_rate': 23},
    {'code': 'PT-12-004', 'type': 'ouvrage', 'category': 'Coberturas', 'designation': 'Instalação e desmontagem de estaleiro', 'unit': 'm²', 'unit_price_ht': 63.65, 'vat_rate': 23},
    {'code': 'PT-12-005', 'type': 'ouvrage', 'category': 'Coberturas', 'designation': 'Instalação e desmontagem de estaleiro', 'unit': 'm²', 'unit_price_ht': 103.85, 'vat_rate': 23},
    {'code': 'PT-12-006', 'type': 'ouvrage', 'category': 'Coberturas', 'designation': 'Instalação e desmontagem de estaleiro', 'unit': 'm²', 'unit_price_ht': 14.74, 'vat_rate': 23},
    {'code': 'PT-13-001', 'type': 'ouvrage', 'category': 'Funilaria / Rufos', 'designation': 'Instalação e desmontagem de estaleiro', 'unit': 'ml', 'unit_price_ht': 36.3, 'vat_rate': 23},
    {'code': 'PT-13-002', 'type': 'ouvrage', 'category': 'Funilaria / Rufos', 'designation': 'Instalação e desmontagem de estaleiro', 'unit': 'ml', 'unit_price_ht': 31.68, 'vat_rate': 23},
    {'code': 'PT-13-003', 'type': 'ouvrage', 'category': 'Funilaria / Rufos', 'designation': 'Instalação e desmontagem de estaleiro', 'unit': 'ml', 'unit_price_ht': 62.7, 'vat_rate': 23},
    {'code': 'PT-13-004', 'type': 'ouvrage', 'category': 'Funilaria / Rufos', 'designation': 'Instalação e desmontagem de estaleiro', 'unit': 'ml', 'unit_price_ht': 36.3, 'vat_rate': 23},
    {'code': 'PT-13-005', 'type': 'ouvrage', 'category': 'Funilaria / Rufos', 'designation': 'Instalação e desmontagem de estaleiro', 'unit': 'ml', 'unit_price_ht': 40.92, 'vat_rate': 23},
    {'code': 'PT-13-006', 'type': 'ouvrage', 'category': 'Funilaria / Rufos', 'designation': 'Instalação e desmontagem de estaleiro', 'unit': 'ml', 'unit_price_ht': 56.1, 'vat_rate': 23},
    {'code': 'PT-14-001', 'type': 'ouvrage', 'category': 'Impermeabilizações', 'designation': 'Instalação e desmontagem de estaleiro', 'unit': 'm²', 'unit_price_ht': 56.1, 'vat_rate': 23},
    {'code': 'PT-14-002', 'type': 'ouvrage', 'category': 'Impermeabilizações', 'designation': 'Instalação e desmontagem de estaleiro', 'unit': 'm²', 'unit_price_ht': 51.48, 'vat_rate': 23},
    {'code': 'PT-14-003', 'type': 'ouvrage', 'category': 'Impermeabilizações', 'designation': 'Instalação e desmontagem de estaleiro', 'unit': 'm²', 'unit_price_ht': 47.52, 'vat_rate': 23},
    {'code': 'PT-14-004', 'type': 'ouvrage', 'category': 'Impermeabilizações', 'designation': 'Instalação e desmontagem de estaleiro', 'unit': 'm²', 'unit_price_ht': 18.48, 'vat_rate': 23},
    {'code': 'PT-14-005', 'type': 'ouvrage', 'category': 'Impermeabilizações', 'designation': 'Instalação e desmontagem de estaleiro', 'unit': 'm²', 'unit_price_ht': 14.52, 'vat_rate': 23},
    {'code': 'PT-15-001', 'type': 'ouvrage', 'category': 'Caixilharias exteriores', 'designation': 'Instalação e desmontagem de estaleiro', 'unit': 'un', 'unit_price_ht': 348.4, 'vat_rate': 23},
    {'code': 'PT-15-002', 'type': 'ouvrage', 'category': 'Caixilharias exteriores', 'designation': 'Instalação e desmontagem de estaleiro', 'unit': 'un', 'unit_price_ht': 482.4, 'vat_rate': 23},
    {'code': 'PT-15-003', 'type': 'ouvrage', 'category': 'Caixilharias exteriores', 'designation': 'Instalação e desmontagem de estaleiro', 'unit': 'un', 'unit_price_ht': 636.5, 'vat_rate': 23},
    {'code': 'PT-15-004', 'type': 'ouvrage', 'category': 'Caixilharias exteriores', 'designation': 'Instalação e desmontagem de estaleiro', 'unit': 'un', 'unit_price_ht': 1239.5, 'vat_rate': 23},
    {'code': 'PT-15-005', 'type': 'ouvrage', 'category': 'Caixilharias exteriores', 'designation': 'Instalação e desmontagem de estaleiro', 'unit': 'un', 'unit_price_ht': 1474.0, 'vat_rate': 23},
    {'code': 'PT-15-006', 'type': 'ouvrage', 'category': 'Caixilharias exteriores', 'designation': 'Instalação e desmontagem de estaleiro', 'unit': 'un', 'unit_price_ht': 435.5, 'vat_rate': 23},
    {'code': 'PT-15-007', 'type': 'ouvrage', 'category': 'Caixilharias exteriores', 'designation': 'Instalação e desmontagem de estaleiro', 'unit': 'un', 'unit_price_ht': 770.5, 'vat_rate': 23},
    {'code': 'PT-16-001', 'type': 'ouvrage', 'category': 'Gesso cartonado / Divisórias', 'designation': 'Instalação e desmontagem de estaleiro', 'unit': 'm²', 'unit_price_ht': 28.8, 'vat_rate': 23},
    {'code': 'PT-16-002', 'type': 'ouvrage', 'category': 'Gesso cartonado / Divisórias', 'designation': 'Instalação e desmontagem de estaleiro', 'unit': 'm²', 'unit_price_ht': 37.2, 'vat_rate': 23},
    {'code': 'PT-16-003', 'type': 'ouvrage', 'category': 'Gesso cartonado / Divisórias', 'designation': 'Instalação e desmontagem de estaleiro', 'unit': 'm²', 'unit_price_ht': 34.8, 'vat_rate': 23},
    {'code': 'PT-16-004', 'type': 'ouvrage', 'category': 'Gesso cartonado / Divisórias', 'designation': 'Instalação e desmontagem de estaleiro', 'unit': 'm²', 'unit_price_ht': 27.6, 'vat_rate': 23},
    {'code': 'PT-16-005', 'type': 'ouvrage', 'category': 'Gesso cartonado / Divisórias', 'designation': 'Instalação e desmontagem de estaleiro', 'unit': 'm²', 'unit_price_ht': 31.2, 'vat_rate': 23},
    {'code': 'PT-16-006', 'type': 'ouvrage', 'category': 'Gesso cartonado / Divisórias', 'designation': 'Instalação e desmontagem de estaleiro', 'unit': 'm²', 'unit_price_ht': 36.0, 'vat_rate': 23},
    {'code': 'PT-16-007', 'type': 'ouvrage', 'category': 'Gesso cartonado / Divisórias', 'designation': 'Instalação e desmontagem de estaleiro', 'unit': 'ml', 'unit_price_ht': 39.0, 'vat_rate': 23},
    {'code': 'PT-17-001', 'type': 'ouvrage', 'category': 'Carpintaria interior', 'designation': 'Instalação e desmontagem de estaleiro', 'unit': 'un', 'unit_price_ht': 257.4, 'vat_rate': 23},
    {'code': 'PT-17-002', 'type': 'ouvrage', 'category': 'Carpintaria interior', 'designation': 'Instalação e desmontagem de estaleiro', 'unit': 'un', 'unit_price_ht': 343.2, 'vat_rate': 23},
    {'code': 'PT-17-003', 'type': 'ouvrage', 'category': 'Carpintaria interior', 'designation': 'Instalação e desmontagem de estaleiro', 'unit': 'un', 'unit_price_ht': 627.0, 'vat_rate': 23},
    {'code': 'PT-17-004', 'type': 'ouvrage', 'category': 'Carpintaria interior', 'designation': 'Instalação e desmontagem de estaleiro', 'unit': 'ml', 'unit_price_ht': 11.88, 'vat_rate': 23},
    {'code': 'PT-17-005', 'type': 'ouvrage', 'category': 'Carpintaria interior', 'designation': 'Instalação e desmontagem de estaleiro', 'unit': 'ml', 'unit_price_ht': 561.0, 'vat_rate': 23},
    {'code': 'PT-17-006', 'type': 'ouvrage', 'category': 'Carpintaria interior', 'designation': 'Instalação e desmontagem de estaleiro', 'unit': 'un', 'unit_price_ht': 2970.0, 'vat_rate': 23},
    {'code': 'PT-18-001', 'type': 'ouvrage', 'category': 'Eletricidade', 'designation': 'Instalação e desmontagem de estaleiro', 'unit': 'un', 'unit_price_ht': 34.1, 'vat_rate': 23},
    {'code': 'PT-18-002', 'type': 'ouvrage', 'category': 'Eletricidade', 'designation': 'Instalação e desmontagem de estaleiro', 'unit': 'un', 'unit_price_ht': 42.16, 'vat_rate': 23},
    {'code': 'PT-18-003', 'type': 'ouvrage', 'category': 'Eletricidade', 'designation': 'Instalação e desmontagem de estaleiro', 'unit': 'un', 'unit_price_ht': 58.9, 'vat_rate': 23},
    {'code': 'PT-18-004', 'type': 'ouvrage', 'category': 'Eletricidade', 'designation': 'Instalação e desmontagem de estaleiro', 'unit': 'un', 'unit_price_ht': 29.76, 'vat_rate': 23},
    {'code': 'PT-18-005', 'type': 'ouvrage', 'category': 'Eletricidade', 'designation': 'Instalação e desmontagem de estaleiro', 'unit': 'un', 'unit_price_ht': 40.3, 'vat_rate': 23},
    {'code': 'PT-18-006', 'type': 'ouvrage', 'category': 'Eletricidade', 'designation': 'Instalação e desmontagem de estaleiro', 'unit': 'un', 'unit_price_ht': 35.96, 'vat_rate': 23},
    {'code': 'PT-18-007', 'type': 'ouvrage', 'category': 'Eletricidade', 'designation': 'Instalação e desmontagem de estaleiro', 'unit': 'un', 'unit_price_ht': 46.5, 'vat_rate': 23},
    {'code': 'PT-18-008', 'type': 'ouvrage', 'category': 'Eletricidade', 'designation': 'Instalação e desmontagem de estaleiro', 'unit': 'un', 'unit_price_ht': 52.7, 'vat_rate': 23},
    {'code': 'PT-18-009', 'type': 'ouvrage', 'category': 'Eletricidade', 'designation': 'Instalação e desmontagem de estaleiro', 'unit': 'un', 'unit_price_ht': 607.6, 'vat_rate': 23},
    {'code': 'PT-18-010', 'type': 'ouvrage', 'category': 'Eletricidade', 'designation': 'Instalação e desmontagem de estaleiro', 'unit': 'forfait', 'unit_price_ht': 403.0, 'vat_rate': 23},
    {'code': 'PT-18-011', 'type': 'ouvrage', 'category': 'Eletricidade', 'designation': 'Instalação e desmontagem de estaleiro', 'unit': 'm²', 'unit_price_ht': 71.3, 'vat_rate': 23},
    {'code': 'PT-19-001', 'type': 'ouvrage', 'category': 'Domótica', 'designation': 'Instalação e desmontagem de estaleiro', 'unit': 'un', 'unit_price_ht': 82.5, 'vat_rate': 23},
    {'code': 'PT-19-002', 'type': 'ouvrage', 'category': 'Domótica', 'designation': 'Instalação e desmontagem de estaleiro', 'unit': 'un', 'unit_price_ht': 89.1, 'vat_rate': 23},
    {'code': 'PT-19-003', 'type': 'ouvrage', 'category': 'Domótica', 'designation': 'Instalação e desmontagem de estaleiro', 'unit': 'un', 'unit_price_ht': 211.2, 'vat_rate': 23},
    {'code': 'PT-19-004', 'type': 'ouvrage', 'category': 'Domótica', 'designation': 'Instalação e desmontagem de estaleiro', 'unit': 'un', 'unit_price_ht': 105.6, 'vat_rate': 23},
    {'code': 'PT-19-005', 'type': 'ouvrage', 'category': 'Domótica', 'designation': 'Instalação e desmontagem de estaleiro', 'unit': 'forfait', 'unit_price_ht': 3168.0, 'vat_rate': 23},
    {'code': 'PT-20-001', 'type': 'ouvrage', 'category': 'Canalização', 'designation': 'Instalação e desmontagem de estaleiro', 'unit': 'ml', 'unit_price_ht': 19.84, 'vat_rate': 23},
    {'code': 'PT-20-002', 'type': 'ouvrage', 'category': 'Canalização', 'designation': 'Instalação e desmontagem de estaleiro', 'unit': 'ml', 'unit_price_ht': 17.36, 'vat_rate': 23},
    {'code': 'PT-20-003', 'type': 'ouvrage', 'category': 'Canalização', 'designation': 'Instalação e desmontagem de estaleiro', 'unit': 'ml', 'unit_price_ht': 26.04, 'vat_rate': 23},
    {'code': 'PT-20-004', 'type': 'ouvrage', 'category': 'Canalização', 'designation': 'Instalação e desmontagem de estaleiro', 'unit': 'un', 'unit_price_ht': 148.8, 'vat_rate': 23},
    {'code': 'PT-20-005', 'type': 'ouvrage', 'category': 'Canalização', 'designation': 'Instalação e desmontagem de estaleiro', 'unit': 'un', 'unit_price_ht': 46.5, 'vat_rate': 23},
    {'code': 'PT-20-006', 'type': 'ouvrage', 'category': 'Canalização', 'designation': 'Instalação e desmontagem de estaleiro', 'unit': 'un', 'unit_price_ht': 114.7, 'vat_rate': 23},
    {'code': 'PT-20-007', 'type': 'ouvrage', 'category': 'Canalização', 'designation': 'Instalação e desmontagem de estaleiro', 'unit': 'un', 'unit_price_ht': 161.2, 'vat_rate': 23},
    {'code': 'PT-20-008', 'type': 'ouvrage', 'category': 'Canalização', 'designation': 'Instalação e desmontagem de estaleiro', 'unit': 'm²', 'unit_price_ht': 46.5, 'vat_rate': 23},
    {'code': 'PT-21-001', 'type': 'ouvrage', 'category': 'Sanitários', 'designation': 'Instalação e desmontagem de estaleiro', 'unit': 'un', 'unit_price_ht': 627.0, 'vat_rate': 23},
    {'code': 'PT-21-002', 'type': 'ouvrage', 'category': 'Sanitários', 'designation': 'Instalação e desmontagem de estaleiro', 'unit': 'un', 'unit_price_ht': 343.2, 'vat_rate': 23},
    {'code': 'PT-21-003', 'type': 'ouvrage', 'category': 'Sanitários', 'designation': 'Instalação e desmontagem de estaleiro', 'unit': 'un', 'unit_price_ht': 514.8, 'vat_rate': 23},
    {'code': 'PT-21-004', 'type': 'ouvrage', 'category': 'Sanitários', 'designation': 'Instalação e desmontagem de estaleiro', 'unit': 'un', 'unit_price_ht': 277.2, 'vat_rate': 23},
    {'code': 'PT-21-005', 'type': 'ouvrage', 'category': 'Sanitários', 'designation': 'Instalação e desmontagem de estaleiro', 'unit': 'un', 'unit_price_ht': 514.8, 'vat_rate': 23},
    {'code': 'PT-21-006', 'type': 'ouvrage', 'category': 'Sanitários', 'designation': 'Instalação e desmontagem de estaleiro', 'unit': 'un', 'unit_price_ht': 429.0, 'vat_rate': 23},
    {'code': 'PT-21-007', 'type': 'ouvrage', 'category': 'Sanitários', 'designation': 'Instalação e desmontagem de estaleiro', 'unit': 'un', 'unit_price_ht': 627.0, 'vat_rate': 23},
    {'code': 'PT-21-008', 'type': 'ouvrage', 'category': 'Sanitários', 'designation': 'Instalação e desmontagem de estaleiro', 'unit': 'un', 'unit_price_ht': 343.2, 'vat_rate': 23},
    {'code': 'PT-22-001', 'type': 'ouvrage', 'category': 'Aquecimento', 'designation': 'Instalação e desmontagem de estaleiro', 'unit': 'un', 'unit_price_ht': 348.4, 'vat_rate': 23},
    {'code': 'PT-22-002', 'type': 'ouvrage', 'category': 'Aquecimento', 'designation': 'Instalação e desmontagem de estaleiro', 'unit': 'un', 'unit_price_ht': 455.6, 'vat_rate': 23},
    {'code': 'PT-22-003', 'type': 'ouvrage', 'category': 'Aquecimento', 'designation': 'Instalação e desmontagem de estaleiro', 'unit': 'un', 'unit_price_ht': 4355.0, 'vat_rate': 23},
    {'code': 'PT-22-004', 'type': 'ouvrage', 'category': 'Aquecimento', 'designation': 'Instalação e desmontagem de estaleiro', 'unit': 'ml', 'unit_price_ht': 30.15, 'vat_rate': 23},
    {'code': 'PT-22-005', 'type': 'ouvrage', 'category': 'Aquecimento', 'designation': 'Instalação e desmontagem de estaleiro', 'unit': 'm²', 'unit_price_ht': 63.65, 'vat_rate': 23},
    {'code': 'PT-22-006', 'type': 'ouvrage', 'category': 'Aquecimento', 'designation': 'Instalação e desmontagem de estaleiro', 'unit': 'forfait', 'unit_price_ht': 435.5, 'vat_rate': 23},
    {'code': 'PT-23-001', 'type': 'ouvrage', 'category': 'Bomba de calor', 'designation': 'Instalação e desmontagem de estaleiro', 'unit': 'un', 'unit_price_ht': 7140.0, 'vat_rate': 23},
    {'code': 'PT-23-002', 'type': 'ouvrage', 'category': 'Bomba de calor', 'designation': 'Instalação e desmontagem de estaleiro', 'unit': 'un', 'unit_price_ht': 9180.0, 'vat_rate': 23},
    {'code': 'PT-23-003', 'type': 'ouvrage', 'category': 'Bomba de calor', 'designation': 'Instalação e desmontagem de estaleiro', 'unit': 'un', 'unit_price_ht': 1496.0, 'vat_rate': 23},
    {'code': 'PT-23-004', 'type': 'ouvrage', 'category': 'Bomba de calor', 'designation': 'Instalação e desmontagem de estaleiro', 'unit': 'un', 'unit_price_ht': 4420.0, 'vat_rate': 23},
    {'code': 'PT-23-005', 'type': 'ouvrage', 'category': 'Bomba de calor', 'designation': 'Instalação e desmontagem de estaleiro', 'unit': 'un', 'unit_price_ht': 2244.0, 'vat_rate': 23},
    {'code': 'PT-24-001', 'type': 'ouvrage', 'category': 'Ar condicionado', 'designation': 'Instalação e desmontagem de estaleiro', 'unit': 'un', 'unit_price_ht': 1254.0, 'vat_rate': 23},
    {'code': 'PT-24-002', 'type': 'ouvrage', 'category': 'Ar condicionado', 'designation': 'Instalação e desmontagem de estaleiro', 'unit': 'un', 'unit_price_ht': 1518.0, 'vat_rate': 23},
    {'code': 'PT-24-003', 'type': 'ouvrage', 'category': 'Ar condicionado', 'designation': 'Instalação e desmontagem de estaleiro', 'unit': 'un', 'unit_price_ht': 2838.0, 'vat_rate': 23},
    {'code': 'PT-24-004', 'type': 'ouvrage', 'category': 'Ar condicionado', 'designation': 'Instalação e desmontagem de estaleiro', 'unit': 'm²', 'unit_price_ht': 85.8, 'vat_rate': 23},
    {'code': 'PT-24-005', 'type': 'ouvrage', 'category': 'Ar condicionado', 'designation': 'Instalação e desmontagem de estaleiro', 'unit': 'ml', 'unit_price_ht': 42.9, 'vat_rate': 23},
    {'code': 'PT-25-001', 'type': 'ouvrage', 'category': 'Ventilação', 'designation': 'Instalação e desmontagem de estaleiro', 'unit': 'un', 'unit_price_ht': 561.0, 'vat_rate': 23},
    {'code': 'PT-25-002', 'type': 'ouvrage', 'category': 'Ventilação', 'designation': 'Instalação e desmontagem de estaleiro', 'unit': 'un', 'unit_price_ht': 891.0, 'vat_rate': 23},
    {'code': 'PT-25-003', 'type': 'ouvrage', 'category': 'Ventilação', 'designation': 'Instalação e desmontagem de estaleiro', 'unit': 'un', 'unit_price_ht': 3432.0, 'vat_rate': 23},
    {'code': 'PT-25-004', 'type': 'ouvrage', 'category': 'Ventilação', 'designation': 'Instalação e desmontagem de estaleiro', 'unit': 'un', 'unit_price_ht': 62.7, 'vat_rate': 23},
    {'code': 'PT-25-005', 'type': 'ouvrage', 'category': 'Ventilação', 'designation': 'Instalação e desmontagem de estaleiro', 'unit': 'ml', 'unit_price_ht': 18.48, 'vat_rate': 23},
    {'code': 'PT-26-001', 'type': 'ouvrage', 'category': 'Betonilhas / Regularização', 'designation': 'Instalação e desmontagem de estaleiro', 'unit': 'm²', 'unit_price_ht': 25.08, 'vat_rate': 23},
    {'code': 'PT-26-002', 'type': 'ouvrage', 'category': 'Betonilhas / Regularização', 'designation': 'Instalação e desmontagem de estaleiro', 'unit': 'm²', 'unit_price_ht': 27.72, 'vat_rate': 23},
    {'code': 'PT-26-003', 'type': 'ouvrage', 'category': 'Betonilhas / Regularização', 'designation': 'Instalação e desmontagem de estaleiro', 'unit': 'm²', 'unit_price_ht': 38.28, 'vat_rate': 23},
    {'code': 'PT-26-004', 'type': 'ouvrage', 'category': 'Betonilhas / Regularização', 'designation': 'Instalação e desmontagem de estaleiro', 'unit': 'm²', 'unit_price_ht': 14.52, 'vat_rate': 23},
    {'code': 'PT-26-005', 'type': 'ouvrage', 'category': 'Betonilhas / Regularização', 'designation': 'Instalação e desmontagem de estaleiro', 'unit': 'm²', 'unit_price_ht': 18.48, 'vat_rate': 23},
    {'code': 'PT-27-001', 'type': 'ouvrage', 'category': 'Revestimentos cerâmicos', 'designation': 'Instalação e desmontagem de estaleiro', 'unit': 'm²', 'unit_price_ht': 46.8, 'vat_rate': 23},
    {'code': 'PT-27-002', 'type': 'ouvrage', 'category': 'Revestimentos cerâmicos', 'designation': 'Instalação e desmontagem de estaleiro', 'unit': 'm²', 'unit_price_ht': 68.25, 'vat_rate': 23},
    {'code': 'PT-27-003', 'type': 'ouvrage', 'category': 'Revestimentos cerâmicos', 'designation': 'Grés porcelânico premium', 'unit': 'm²', 'unit_price_ht': 81.25, 'vat_rate': 23},
    {'code': 'PT-27-004', 'type': 'ouvrage', 'category': 'Revestimentos cerâmicos', 'designation': 'Azulejo de parede', 'unit': 'm²', 'unit_price_ht': 50.7, 'vat_rate': 23},
    {'code': 'PT-27-005', 'type': 'ouvrage', 'category': 'Revestimentos cerâmicos', 'designation': 'Mosaico para duche', 'unit': 'm²', 'unit_price_ht': 74.75, 'vat_rate': 23},
    {'code': 'PT-27-006', 'type': 'ouvrage', 'category': 'Revestimentos cerâmicos', 'designation': 'Rodapé cerâmico', 'unit': 'ml', 'unit_price_ht': 14.3, 'vat_rate': 23},
    {'code': 'PT-28-001', 'type': 'ouvrage', 'category': 'Pavimentos madeira / vinílico', 'designation': 'Pavimento laminado fornecido e aplicado', 'unit': 'm²', 'unit_price_ht': 31.68, 'vat_rate': 23},
    {'code': 'PT-28-002', 'type': 'ouvrage', 'category': 'Pavimentos madeira / vinílico', 'designation': 'Soalho multicamada', 'unit': 'm²', 'unit_price_ht': 51.48, 'vat_rate': 23},
    {'code': 'PT-28-003', 'type': 'ouvrage', 'category': 'Pavimentos madeira / vinílico', 'designation': 'Soalho maciço colado', 'unit': 'm²', 'unit_price_ht': 82.5, 'vat_rate': 23},
    {'code': 'PT-28-004', 'type': 'ouvrage', 'category': 'Pavimentos madeira / vinílico', 'designation': 'Afagamento e envernizamento de soalho', 'unit': 'm²', 'unit_price_ht': 27.72, 'vat_rate': 23},
    {'code': 'PT-28-005', 'type': 'ouvrage', 'category': 'Pavimentos madeira / vinílico', 'designation': 'Pavimento vinílico em réguas', 'unit': 'm²', 'unit_price_ht': 31.68, 'vat_rate': 23},
    {'code': 'PT-28-006', 'type': 'ouvrage', 'category': 'Pavimentos madeira / vinílico', 'designation': 'Alcatifa fornecida e aplicada', 'unit': 'm²', 'unit_price_ht': 27.72, 'vat_rate': 23},
    {'code': 'PT-29-001', 'type': 'ouvrage', 'category': 'Pintura', 'designation': 'Preparação + pintura de paredes 2 demãos', 'unit': 'm²', 'unit_price_ht': 19.2, 'vat_rate': 23},
    {'code': 'PT-29-002', 'type': 'ouvrage', 'category': 'Pintura', 'designation': 'Pintura plafond 2 couches', 'unit': 'm²', 'unit_price_ht': 21.0, 'vat_rate': 23},
    {'code': 'PT-29-003', 'type': 'ouvrage', 'category': 'Pintura', 'designation': 'Reboco ratissage complet', 'unit': 'm²', 'unit_price_ht': 16.8, 'vat_rate': 23},
    {'code': 'PT-29-004', 'type': 'ouvrage', 'category': 'Pintura', 'designation': 'Pintura de madeiras', 'unit': 'm²', 'unit_price_ht': 27.0, 'vat_rate': 23},
    {'code': 'PT-29-005', 'type': 'ouvrage', 'category': 'Pintura', 'designation': 'Pintura fachada', 'unit': 'm²', 'unit_price_ht': 28.8, 'vat_rate': 23},
    {'code': 'PT-29-006', 'type': 'ouvrage', 'category': 'Pintura', 'designation': 'Papel de parede standard aplicado', 'unit': 'm²', 'unit_price_ht': 25.2, 'vat_rate': 23},
    {'code': 'PT-30-001', 'type': 'ouvrage', 'category': 'Cozinhas', 'designation': 'Montagem de móveis de cozinha inferiores/superiores', 'unit': 'ml', 'unit_price_ht': 316.8, 'vat_rate': 23},
    {'code': 'PT-30-002', 'type': 'ouvrage', 'category': 'Cozinhas', 'designation': 'Tampo laminado aplicado', 'unit': 'ml', 'unit_price_ht': 145.2, 'vat_rate': 23},
    {'code': 'PT-30-003', 'type': 'ouvrage', 'category': 'Cozinhas', 'designation': 'Tampo em quartzo aplicado', 'unit': 'ml', 'unit_price_ht': 429.0, 'vat_rate': 23},
    {'code': 'PT-30-004', 'type': 'ouvrage', 'category': 'Cozinhas', 'designation': 'Revestimento cerâmico entre móveis', 'unit': 'm²', 'unit_price_ht': 62.7, 'vat_rate': 23},
    {'code': 'PT-30-005', 'type': 'ouvrage', 'category': 'Cozinhas', 'designation': 'Lava-loiça + misturadora aplicada', 'unit': 'un', 'unit_price_ht': 429.0, 'vat_rate': 23},
    {'code': 'PT-30-006', 'type': 'ouvrage', 'category': 'Cozinhas', 'designation': 'Cozinha completa standard', 'unit': 'forfait', 'unit_price_ht': 7920.0, 'vat_rate': 23},
    {'code': 'PT-31-001', 'type': 'ouvrage', 'category': 'Casas de banho', 'designation': 'Rénovation completa salle de bains standard', 'unit': 'm²', 'unit_price_ht': 990.0, 'vat_rate': 23},
    {'code': 'PT-31-002', 'type': 'ouvrage', 'category': 'Casas de banho', 'designation': 'Duche walk-in completo', 'unit': 'un', 'unit_price_ht': 1848.0, 'vat_rate': 23},
    {'code': 'PT-31-003', 'type': 'ouvrage', 'category': 'Casas de banho', 'designation': 'Impermeabilização completa da zona de duche', 'unit': 'un', 'unit_price_ht': 495.0, 'vat_rate': 23},
    {'code': 'PT-31-004', 'type': 'ouvrage', 'category': 'Casas de banho', 'designation': 'Nicho de parede revestido', 'unit': 'un', 'unit_price_ht': 297.0, 'vat_rate': 23},
    {'code': 'PT-31-005', 'type': 'ouvrage', 'category': 'Casas de banho', 'designation': 'Renovação de WC separado', 'unit': 'forfait', 'unit_price_ht': 2112.0, 'vat_rate': 23},
    {'code': 'PT-32-001', 'type': 'ouvrage', 'category': 'Piscinas', 'designation': 'Piscina em bloco de betão + liner', 'unit': 'm²', 'unit_price_ht': 510.0, 'vat_rate': 23},
    {'code': 'PT-32-002', 'type': 'ouvrage', 'category': 'Piscinas', 'designation': 'Piscina em betão armado moldado', 'unit': 'm²', 'unit_price_ht': 680.0, 'vat_rate': 23},
    {'code': 'PT-32-003', 'type': 'ouvrage', 'category': 'Piscinas', 'designation': 'Piscina em betão projetado', 'unit': 'm²', 'unit_price_ht': 816.0, 'vat_rate': 23},
    {'code': 'PT-32-004', 'type': 'ouvrage', 'category': 'Piscinas', 'designation': 'Terraçoment piscine', 'unit': 'm³', 'unit_price_ht': 32.64, 'vat_rate': 23},
    {'code': 'PT-32-005', 'type': 'ouvrage', 'category': 'Piscinas', 'designation': 'Casa das máquinas / filtração', 'unit': 'forfait', 'unit_price_ht': 2176.0, 'vat_rate': 23},
    {'code': 'PT-32-006', 'type': 'ouvrage', 'category': 'Piscinas', 'designation': 'Bomba de filtração', 'unit': 'un', 'unit_price_ht': 748.0, 'vat_rate': 23},
    {'code': 'PT-32-007', 'type': 'ouvrage', 'category': 'Piscinas', 'designation': 'Bomba de calor para piscina', 'unit': 'un', 'unit_price_ht': 1904.0, 'vat_rate': 23},
    {'code': 'PT-32-008', 'type': 'ouvrage', 'category': 'Piscinas', 'designation': 'Liner 75/100 aplicado', 'unit': 'm²', 'unit_price_ht': 37.4, 'vat_rate': 23},
    {'code': 'PT-33-001', 'type': 'ouvrage', 'category': 'Terraços', 'designation': 'Dalle betão terrasse 12 cm', 'unit': 'm²', 'unit_price_ht': 62.7, 'vat_rate': 23},
    {'code': 'PT-33-002', 'type': 'ouvrage', 'category': 'Terraços', 'designation': 'Terraço com revestimento cerâmico exterior', 'unit': 'm²', 'unit_price_ht': 72.6, 'vat_rate': 23},
    {'code': 'PT-33-003', 'type': 'ouvrage', 'category': 'Terraços', 'designation': 'Deck em pinho tratado', 'unit': 'm²', 'unit_price_ht': 62.7, 'vat_rate': 23},
    {'code': 'PT-33-004', 'type': 'ouvrage', 'category': 'Terraços', 'designation': 'Deck em madeira exótica', 'unit': 'm²', 'unit_price_ht': 108.9, 'vat_rate': 23},
    {'code': 'PT-33-005', 'type': 'ouvrage', 'category': 'Terraços', 'designation': 'Deck compósito', 'unit': 'm²', 'unit_price_ht': 89.1, 'vat_rate': 23},
    {'code': 'PT-33-006', 'type': 'ouvrage', 'category': 'Terraços', 'designation': 'Pedestais reguláveis para terraço', 'unit': 'm²', 'unit_price_ht': 21.12, 'vat_rate': 23},
    {'code': 'PT-34-001', 'type': 'ouvrage', 'category': 'Muros / Vedações', 'designation': 'Parede bloco de betão 20 cm sem fundação', 'unit': 'm²', 'unit_price_ht': 51.48, 'vat_rate': 23},
    {'code': 'PT-34-002', 'type': 'ouvrage', 'category': 'Muros / Vedações', 'designation': 'Parede de clôture rebocado em 2 faces', 'unit': 'm²', 'unit_price_ht': 95.7, 'vat_rate': 23},
    {'code': 'PT-34-003', 'type': 'ouvrage', 'category': 'Muros / Vedações', 'designation': 'Muro de suporte em betão armado', 'unit': 'm²', 'unit_price_ht': 184.8, 'vat_rate': 23},
    {'code': 'PT-34-004', 'type': 'ouvrage', 'category': 'Muros / Vedações', 'designation': 'Vedação painel rígido', 'unit': 'ml', 'unit_price_ht': 62.7, 'vat_rate': 23},
    {'code': 'PT-34-005', 'type': 'ouvrage', 'category': 'Muros / Vedações', 'designation': 'Vedação em madeira', 'unit': 'ml', 'unit_price_ht': 95.7, 'vat_rate': 23},
    {'code': 'PT-34-006', 'type': 'ouvrage', 'category': 'Muros / Vedações', 'designation': 'Capeamento de betão', 'unit': 'ml', 'unit_price_ht': 29.7, 'vat_rate': 23},
    {'code': 'PT-35-001', 'type': 'ouvrage', 'category': 'Portões', 'designation': 'Portão de alumínio de batente manual', 'unit': 'un', 'unit_price_ht': 1848.0, 'vat_rate': 23},
    {'code': 'PT-35-002', 'type': 'ouvrage', 'category': 'Portões', 'designation': 'Portão de alumínio de correr manual', 'unit': 'un', 'unit_price_ht': 2310.0, 'vat_rate': 23},
    {'code': 'PT-35-003', 'type': 'ouvrage', 'category': 'Portões', 'designation': 'Automatismo portail de batente', 'unit': 'un', 'unit_price_ht': 957.0, 'vat_rate': 23},
    {'code': 'PT-35-004', 'type': 'ouvrage', 'category': 'Portões', 'designation': 'Automatismo portail de correr', 'unit': 'un', 'unit_price_ht': 1089.0, 'vat_rate': 23},
    {'code': 'PT-35-005', 'type': 'ouvrage', 'category': 'Portões', 'designation': 'Portinhola em alumínio', 'unit': 'un', 'unit_price_ht': 792.0, 'vat_rate': 23},
    {'code': 'PT-36-001', 'type': 'ouvrage', 'category': 'Infraestruturas exteriores', 'designation': 'Coletor de esgoto PVC Ø110 enterrado', 'unit': 'ml', 'unit_price_ht': 49.5, 'vat_rate': 23},
    {'code': 'PT-36-002', 'type': 'ouvrage', 'category': 'Infraestruturas exteriores', 'designation': 'Coletor pluvial PVC Ø110 enterrado', 'unit': 'ml', 'unit_price_ht': 46.2, 'vat_rate': 23},
    {'code': 'PT-36-003', 'type': 'ouvrage', 'category': 'Infraestruturas exteriores', 'designation': 'Regard betão 40x40', 'unit': 'un', 'unit_price_ht': 211.2, 'vat_rate': 23},
    {'code': 'PT-36-004', 'type': 'ouvrage', 'category': 'Infraestruturas exteriores', 'designation': 'Dreno periférico', 'unit': 'ml', 'unit_price_ht': 42.9, 'vat_rate': 23},
    {'code': 'PT-36-005', 'type': 'ouvrage', 'category': 'Infraestruturas exteriores', 'designation': 'Tubo corrugado TPC', 'unit': 'ml', 'unit_price_ht': 11.88, 'vat_rate': 23},
    {'code': 'PT-36-006', 'type': 'ouvrage', 'category': 'Infraestruturas exteriores', 'designation': 'Ligação exterior de água', 'unit': 'ml', 'unit_price_ht': 29.7, 'vat_rate': 23},
    {'code': 'PT-37-001', 'type': 'ouvrage', 'category': 'Saneamento', 'designation': 'Fossa séptica 3000 L instalada', 'unit': 'un', 'unit_price_ht': 4290.0, 'vat_rate': 23},
    {'code': 'PT-37-002', 'type': 'ouvrage', 'category': 'Saneamento', 'designation': 'ETAR compacta para 5 habitantes instalada', 'unit': 'un', 'unit_price_ht': 6270.0, 'vat_rate': 23},
    {'code': 'PT-37-003', 'type': 'ouvrage', 'category': 'Saneamento', 'designation': 'Dreno de infiltração', 'unit': 'ml', 'unit_price_ht': 56.1, 'vat_rate': 23},
    {'code': 'PT-37-004', 'type': 'ouvrage', 'category': 'Saneamento', 'designation': 'Estação elevatória', 'unit': 'un', 'unit_price_ht': 1848.0, 'vat_rate': 23},
    {'code': 'PT-37-005', 'type': 'ouvrage', 'category': 'Saneamento', 'designation': 'Separador de hidrocarbonetos', 'unit': 'un', 'unit_price_ht': 2772.0, 'vat_rate': 23},
    {'code': 'PT-38-001', 'type': 'ouvrage', 'category': 'Arranjos exteriores', 'designation': 'Pavés betão sur lit de sable', 'unit': 'm²', 'unit_price_ht': 51.48, 'vat_rate': 23},
    {'code': 'PT-38-002', 'type': 'ouvrage', 'category': 'Arranjos exteriores', 'designation': 'Betuminoso/asfalto', 'unit': 'm²', 'unit_price_ht': 36.3, 'vat_rate': 23},
    {'code': 'PT-38-003', 'type': 'ouvrage', 'category': 'Arranjos exteriores', 'designation': 'Gravilha estabilizada', 'unit': 'm²', 'unit_price_ht': 25.08, 'vat_rate': 23},
    {'code': 'PT-38-004', 'type': 'ouvrage', 'category': 'Arranjos exteriores', 'designation': 'Lancil de betão', 'unit': 'ml', 'unit_price_ht': 21.12, 'vat_rate': 23},
    {'code': 'PT-38-005', 'type': 'ouvrage', 'category': 'Arranjos exteriores', 'designation': 'Relva em rolo', 'unit': 'm²', 'unit_price_ht': 14.52, 'vat_rate': 23},
    {'code': 'PT-38-006', 'type': 'ouvrage', 'category': 'Arranjos exteriores', 'designation': 'Regularização de terreno', 'unit': 'm²', 'unit_price_ht': 7.92, 'vat_rate': 23},
    {'code': 'PT-39-001', 'type': 'ouvrage', 'category': 'Escadas / Serralharia', 'designation': 'Escada de betão reta', 'unit': 'un', 'unit_price_ht': 3432.0, 'vat_rate': 23},
    {'code': 'PT-39-002', 'type': 'ouvrage', 'category': 'Escadas / Serralharia', 'designation': 'Guarda-corpos aço lacado', 'unit': 'ml', 'unit_price_ht': 211.2, 'vat_rate': 23},
    {'code': 'PT-39-003', 'type': 'ouvrage', 'category': 'Escadas / Serralharia', 'designation': 'Guarda-corpos em vidro', 'unit': 'ml', 'unit_price_ht': 343.2, 'vat_rate': 23},
    {'code': 'PT-39-004', 'type': 'ouvrage', 'category': 'Escadas / Serralharia', 'designation': 'Corrimão inox', 'unit': 'ml', 'unit_price_ht': 92.4, 'vat_rate': 23},
    {'code': 'PT-39-005', 'type': 'ouvrage', 'category': 'Escadas / Serralharia', 'designation': 'Escada metálica interior', 'unit': 'un', 'unit_price_ht': 4752.0, 'vat_rate': 23},
    {'code': 'PT-40-001', 'type': 'ouvrage', 'category': 'Lareiras / Salamandras', 'designation': 'Salamandra a lenha + chaminé', 'unit': 'un', 'unit_price_ht': 3432.0, 'vat_rate': 23},
    {'code': 'PT-40-002', 'type': 'ouvrage', 'category': 'Lareiras / Salamandras', 'designation': 'Salamandra a pellets + chaminé', 'unit': 'un', 'unit_price_ht': 4290.0, 'vat_rate': 23},
    {'code': 'PT-40-003', 'type': 'ouvrage', 'category': 'Lareiras / Salamandras', 'designation': 'Tubagem interior de chaminé', 'unit': 'ml', 'unit_price_ht': 72.6, 'vat_rate': 23},
    {'code': 'PT-40-004', 'type': 'ouvrage', 'category': 'Lareiras / Salamandras', 'designation': 'Criação de chaminé isolada', 'unit': 'ml', 'unit_price_ht': 125.4, 'vat_rate': 23},
    {'code': 'PT-40-005', 'type': 'ouvrage', 'category': 'Lareiras / Salamandras', 'designation': 'Recuperador de calor', 'unit': 'un', 'unit_price_ht': 3168.0, 'vat_rate': 23},
    {'code': 'PT-41-001', 'type': 'ouvrage', 'category': 'Solar / Fotovoltaico', 'designation': 'Sistema fotovoltaico 3 kWc', 'unit': 'forfait', 'unit_price_ht': 5610.0, 'vat_rate': 23},
    {'code': 'PT-41-002', 'type': 'ouvrage', 'category': 'Solar / Fotovoltaico', 'designation': 'Sistema fotovoltaico 6 kWc', 'unit': 'forfait', 'unit_price_ht': 8910.0, 'vat_rate': 23},
    {'code': 'PT-41-003', 'type': 'ouvrage', 'category': 'Solar / Fotovoltaico', 'designation': 'Bateria de armazenamento 5 kWh', 'unit': 'un', 'unit_price_ht': 3432.0, 'vat_rate': 23},
    {'code': 'PT-41-004', 'type': 'ouvrage', 'category': 'Solar / Fotovoltaico', 'designation': 'Sistema solar térmico para AQS', 'unit': 'un', 'unit_price_ht': 4290.0, 'vat_rate': 23},
    {'code': 'PT-42-001', 'type': 'ouvrage', 'category': 'Tratamento de humidades', 'designation': 'Injeção de resina contra humidade ascensional', 'unit': 'ml', 'unit_price_ht': 62.7, 'vat_rate': 23},
    {'code': 'PT-42-002', 'type': 'ouvrage', 'category': 'Tratamento de humidades', 'designation': 'Drenagem interior de parede enterrada', 'unit': 'ml', 'unit_price_ht': 95.7, 'vat_rate': 23},
    {'code': 'PT-42-003', 'type': 'ouvrage', 'category': 'Tratamento de humidades', 'designation': 'Impermeabilização integral de cave', 'unit': 'm²', 'unit_price_ht': 75.9, 'vat_rate': 23},
    {'code': 'PT-42-004', 'type': 'ouvrage', 'category': 'Tratamento de humidades', 'designation': 'Tratamento anti-bolor', 'unit': 'm²', 'unit_price_ht': 18.48, 'vat_rate': 23},
    {'code': 'PT-42-005', 'type': 'ouvrage', 'category': 'Tratamento de humidades', 'designation': 'Desumidificação de obra', 'unit': 'dia', 'unit_price_ht': 62.7, 'vat_rate': 23},
    {'code': 'PT-43-001', 'type': 'ouvrage', 'category': 'Diagnósticos / Estudos', 'designation': 'Diagnóstico técnico pré-obra', 'unit': 'forfait', 'unit_price_ht': 429.0, 'vat_rate': 23},
    {'code': 'PT-43-002', 'type': 'ouvrage', 'category': 'Diagnósticos / Estudos', 'designation': 'Estudo térmico', 'unit': 'forfait', 'unit_price_ht': 792.0, 'vat_rate': 23},
    {'code': 'PT-43-003', 'type': 'ouvrage', 'category': 'Diagnósticos / Estudos', 'designation': 'Estudo estrutural', 'unit': 'forfait', 'unit_price_ht': 1188.0, 'vat_rate': 23},
    {'code': 'PT-43-004', 'type': 'ouvrage', 'category': 'Diagnósticos / Estudos', 'designation': 'Levantamento e medições da habitação', 'unit': 'forfait', 'unit_price_ht': 297.0, 'vat_rate': 23},
    {'code': 'PT-43-005', 'type': 'ouvrage', 'category': 'Diagnósticos / Estudos', 'designation': 'Ensaio de estanquidade ao ar', 'unit': 'forfait', 'unit_price_ht': 429.0, 'vat_rate': 23},
    {'code': 'PT-PISC-001', 'type': 'ouvrage', 'category': 'Piscinas – Construção e Equipamentos', 'designation': 'Escavação de piscina em terreno corrente', 'unit': 'm³', 'unit_price_ht': 32.0, 'vat_rate': 23},
    {'code': 'PT-PISC-002', 'type': 'ouvrage', 'category': 'Piscinas – Construção e Equipamentos', 'designation': 'Transporte de terras da piscina a vazadouro', 'unit': 'm³', 'unit_price_ht': 30.0, 'vat_rate': 23},
    {'code': 'PT-PISC-003', 'type': 'ouvrage', 'category': 'Piscinas – Construção e Equipamentos', 'designation': 'Camada de base compactada sob laje', 'unit': 'm²', 'unit_price_ht': 16.0, 'vat_rate': 23},
    {'code': 'PT-PISC-004', 'type': 'ouvrage', 'category': 'Piscinas – Construção e Equipamentos', 'designation': 'Betão de limpeza sob piscina', 'unit': 'm²', 'unit_price_ht': 13.0, 'vat_rate': 23},
    {'code': 'PT-PISC-005', 'type': 'ouvrage', 'category': 'Piscinas – Construção e Equipamentos', 'designation': 'Laje de fundo da piscina em betão armado 20 cm', 'unit': 'm²', 'unit_price_ht': 110.0, 'vat_rate': 23},
    {'code': 'PT-PISC-006', 'type': 'ouvrage', 'category': 'Piscinas – Construção e Equipamentos', 'designation': 'Armadura dupla da laje de fundo', 'unit': 'm²', 'unit_price_ht': 34.0, 'vat_rate': 23},
    {'code': 'PT-PISC-007', 'type': 'ouvrage', 'category': 'Piscinas – Construção e Equipamentos', 'designation': 'Parede de piscina em bloco de cofragem 20 cm', 'unit': 'm²', 'unit_price_ht': 98.0, 'vat_rate': 23},
    {'code': 'PT-PISC-008', 'type': 'ouvrage', 'category': 'Piscinas – Construção e Equipamentos', 'designation': 'Parede de piscina em betão armado 20 cm', 'unit': 'm²', 'unit_price_ht': 135.0, 'vat_rate': 23},
    {'code': 'PT-PISC-009', 'type': 'ouvrage', 'category': 'Piscinas – Construção e Equipamentos', 'designation': 'Piscina em betão projetado / gunite', 'unit': 'm²', 'unit_price_ht': 165.0, 'vat_rate': 23},
    {'code': 'PT-PISC-010', 'type': 'ouvrage', 'category': 'Piscinas – Construção e Equipamentos', 'designation': 'Cofragem de escada em betão', 'unit': 'un', 'unit_price_ht': 620.0, 'vat_rate': 23},
    {'code': 'PT-PISC-011', 'type': 'ouvrage', 'category': 'Piscinas – Construção e Equipamentos', 'designation': 'Escada construída com 3 degraus', 'unit': 'un', 'unit_price_ht': 1100.0, 'vat_rate': 23},
    {'code': 'PT-PISC-012', 'type': 'ouvrage', 'category': 'Piscinas – Construção e Equipamentos', 'designation': 'Banco submerso construído', 'unit': 'ml', 'unit_price_ht': 280.0, 'vat_rate': 23},
    {'code': 'PT-PISC-013', 'type': 'ouvrage', 'category': 'Piscinas – Construção e Equipamentos', 'designation': 'Reboco de regularização do tanque', 'unit': 'm²', 'unit_price_ht': 25.0, 'vat_rate': 23},
    {'code': 'PT-PISC-014', 'type': 'ouvrage', 'category': 'Piscinas – Construção e Equipamentos', 'designation': 'Impermeabilização cimentícia do tanque', 'unit': 'm²', 'unit_price_ht': 35.0, 'vat_rate': 23},
    {'code': 'PT-PISC-015', 'type': 'ouvrage', 'category': 'Piscinas – Construção e Equipamentos', 'designation': 'Liner 75/100 fornecido e aplicado', 'unit': 'm²', 'unit_price_ht': 38.0, 'vat_rate': 23},
    {'code': 'PT-PISC-016', 'type': 'ouvrage', 'category': 'Piscinas – Construção e Equipamentos', 'designation': 'Membrana armada PVC 150/100', 'unit': 'm²', 'unit_price_ht': 62.0, 'vat_rate': 23},
    {'code': 'PT-PISC-017', 'type': 'ouvrage', 'category': 'Piscinas – Construção e Equipamentos', 'designation': 'Revestimento cerâmico para piscina', 'unit': 'm²', 'unit_price_ht': 75.0, 'vat_rate': 23},
    {'code': 'PT-PISC-018', 'type': 'ouvrage', 'category': 'Piscinas – Construção e Equipamentos', 'designation': 'Pastilha/mosaico para piscina', 'unit': 'm²', 'unit_price_ht': 95.0, 'vat_rate': 23},
    {'code': 'PT-PISC-019', 'type': 'ouvrage', 'category': 'Piscinas – Construção e Equipamentos', 'designation': 'Pedra de remate em betão reconstituído', 'unit': 'ml', 'unit_price_ht': 45.0, 'vat_rate': 23},
    {'code': 'PT-PISC-020', 'type': 'ouvrage', 'category': 'Piscinas – Construção e Equipamentos', 'designation': 'Pedra de remate natural', 'unit': 'ml', 'unit_price_ht': 82.0, 'vat_rate': 23},
    {'code': 'PT-PISC-021', 'type': 'ouvrage', 'category': 'Piscinas – Construção e Equipamentos', 'designation': 'Skimmer de boca larga', 'unit': 'un', 'unit_price_ht': 210.0, 'vat_rate': 23},
    {'code': 'PT-PISC-022', 'type': 'ouvrage', 'category': 'Piscinas – Construção e Equipamentos', 'designation': 'Boca de impulsão', 'unit': 'un', 'unit_price_ht': 62.0, 'vat_rate': 23},
    {'code': 'PT-PISC-023', 'type': 'ouvrage', 'category': 'Piscinas – Construção e Equipamentos', 'designation': 'Tomada de aspiração', 'unit': 'un', 'unit_price_ht': 58.0, 'vat_rate': 23},
    {'code': 'PT-PISC-024', 'type': 'ouvrage', 'category': 'Piscinas – Construção e Equipamentos', 'designation': 'Ralo de fundo', 'unit': 'un', 'unit_price_ht': 110.0, 'vat_rate': 23},
    {'code': 'PT-PISC-025', 'type': 'ouvrage', 'category': 'Piscinas – Construção e Equipamentos', 'designation': 'Projetor LED para piscina', 'unit': 'un', 'unit_price_ht': 280.0, 'vat_rate': 23},
    {'code': 'PT-PISC-026', 'type': 'ouvrage', 'category': 'Piscinas – Construção e Equipamentos', 'designation': 'Tubagem PVC pressão Ø50', 'unit': 'ml', 'unit_price_ht': 18.0, 'vat_rate': 23},
    {'code': 'PT-PISC-027', 'type': 'ouvrage', 'category': 'Piscinas – Construção e Equipamentos', 'designation': 'Tubagem PVC pressão Ø63', 'unit': 'ml', 'unit_price_ht': 23.0, 'vat_rate': 23},
    {'code': 'PT-PISC-028', 'type': 'ouvrage', 'category': 'Piscinas – Construção e Equipamentos', 'designation': 'Coletores e válvulas da casa das máquinas', 'unit': 'forfait', 'unit_price_ht': 520.0, 'vat_rate': 23},
    {'code': 'PT-PISC-029', 'type': 'ouvrage', 'category': 'Piscinas – Construção e Equipamentos', 'designation': 'Bomba de filtração 0,75-1 CV', 'unit': 'un', 'unit_price_ht': 620.0, 'vat_rate': 23},
    {'code': 'PT-PISC-030', 'type': 'ouvrage', 'category': 'Piscinas – Construção e Equipamentos', 'designation': 'Bomba de filtração de velocidade variável', 'unit': 'un', 'unit_price_ht': 1100.0, 'vat_rate': 23},
    {'code': 'PT-PISC-031', 'type': 'ouvrage', 'category': 'Piscinas – Construção e Equipamentos', 'designation': 'Filtro de areia 600 mm', 'unit': 'un', 'unit_price_ht': 820.0, 'vat_rate': 23},
    {'code': 'PT-PISC-032', 'type': 'ouvrage', 'category': 'Piscinas – Construção e Equipamentos', 'designation': 'Carga filtrante de vidro', 'unit': 'un', 'unit_price_ht': 185.0, 'vat_rate': 23},
    {'code': 'PT-PISC-033', 'type': 'ouvrage', 'category': 'Piscinas – Construção e Equipamentos', 'designation': 'Casa das máquinas equipada', 'unit': 'forfait', 'unit_price_ht': 2600.0, 'vat_rate': 23},
    {'code': 'PT-PISC-034', 'type': 'ouvrage', 'category': 'Piscinas – Construção e Equipamentos', 'designation': 'Quadro elétrico da piscina', 'unit': 'un', 'unit_price_ht': 560.0, 'vat_rate': 23},
    {'code': 'PT-PISC-035', 'type': 'ouvrage', 'category': 'Piscinas – Construção e Equipamentos', 'designation': 'Eletrólise de sal', 'unit': 'un', 'unit_price_ht': 1200.0, 'vat_rate': 23},
    {'code': 'PT-PISC-036', 'type': 'ouvrage', 'category': 'Piscinas – Construção e Equipamentos', 'designation': 'Regulação automática de pH', 'unit': 'un', 'unit_price_ht': 820.0, 'vat_rate': 23},
    {'code': 'PT-PISC-037', 'type': 'ouvrage', 'category': 'Piscinas – Construção e Equipamentos', 'designation': 'Regulação Redox de cloro', 'unit': 'un', 'unit_price_ht': 950.0, 'vat_rate': 23},
    {'code': 'PT-PISC-038', 'type': 'ouvrage', 'category': 'Piscinas – Construção e Equipamentos', 'designation': 'Bomba de calor piscina 7-9 kW', 'unit': 'un', 'unit_price_ht': 1900.0, 'vat_rate': 23},
    {'code': 'PT-PISC-039', 'type': 'ouvrage', 'category': 'Piscinas – Construção e Equipamentos', 'designation': 'Bomba de calor piscina 12-15 kW', 'unit': 'un', 'unit_price_ht': 2600.0, 'vat_rate': 23},
    {'code': 'PT-PISC-040', 'type': 'ouvrage', 'category': 'Piscinas – Construção e Equipamentos', 'designation': 'Duche solar exterior', 'unit': 'un', 'unit_price_ht': 420.0, 'vat_rate': 23},
    {'code': 'PT-PISC-041', 'type': 'ouvrage', 'category': 'Piscinas – Construção e Equipamentos', 'designation': 'Escada inox para piscina', 'unit': 'un', 'unit_price_ht': 340.0, 'vat_rate': 23},
    {'code': 'PT-PISC-042', 'type': 'ouvrage', 'category': 'Piscinas – Construção e Equipamentos', 'designation': 'Cobertura automática exterior', 'unit': 'm²', 'unit_price_ht': 125.0, 'vat_rate': 23},
    {'code': 'PT-PISC-043', 'type': 'ouvrage', 'category': 'Piscinas – Construção e Equipamentos', 'designation': 'Cobertura automática submersa', 'unit': 'm²', 'unit_price_ht': 215.0, 'vat_rate': 23},
    {'code': 'PT-PISC-044', 'type': 'ouvrage', 'category': 'Piscinas – Construção e Equipamentos', 'designation': 'Cobertura de segurança com barras', 'unit': 'm²', 'unit_price_ht': 62.0, 'vat_rate': 23},
    {'code': 'PT-PISC-045', 'type': 'ouvrage', 'category': 'Piscinas – Construção e Equipamentos', 'designation': 'Cobertura térmica de bolhas + enrolador', 'unit': 'm²', 'unit_price_ht': 28.0, 'vat_rate': 23},
    {'code': 'PT-PISC-046', 'type': 'ouvrage', 'category': 'Piscinas – Construção e Equipamentos', 'designation': 'Sistema de natação contracorrente', 'unit': 'un', 'unit_price_ht': 2800.0, 'vat_rate': 23},
    {'code': 'PT-PISC-047', 'type': 'ouvrage', 'category': 'Piscinas – Construção e Equipamentos', 'designation': 'Robô elétrico de limpeza', 'unit': 'un', 'unit_price_ht': 820.0, 'vat_rate': 23},
    {'code': 'PT-PISC-048', 'type': 'ouvrage', 'category': 'Piscinas – Construção e Equipamentos', 'designation': 'Zona envolvente em betão', 'unit': 'm²', 'unit_price_ht': 65.0, 'vat_rate': 23},
    {'code': 'PT-PISC-049', 'type': 'ouvrage', 'category': 'Piscinas – Construção e Equipamentos', 'designation': 'Zona envolvente em cerâmica antiderrapante', 'unit': 'm²', 'unit_price_ht': 88.0, 'vat_rate': 23},
    {'code': 'PT-PISC-050', 'type': 'ouvrage', 'category': 'Piscinas – Construção e Equipamentos', 'designation': 'Deck compósito envolvente', 'unit': 'm²', 'unit_price_ht': 95.0, 'vat_rate': 23},
    {'code': 'PT-PISC-051', 'type': 'ouvrage', 'category': 'Piscinas – Construção e Equipamentos', 'designation': 'Drenagem periférica da piscina', 'unit': 'ml', 'unit_price_ht': 42.0, 'vat_rate': 23},
    {'code': 'PT-PISC-052', 'type': 'ouvrage', 'category': 'Piscinas – Construção e Equipamentos', 'designation': 'Aterro periférico com brita', 'unit': 'm³', 'unit_price_ht': 42.0, 'vat_rate': 23},
    {'code': 'PT-PISC-053', 'type': 'ouvrage', 'category': 'Piscinas – Construção e Equipamentos', 'designation': 'Enchimento e colocação em funcionamento', 'unit': 'forfait', 'unit_price_ht': 420.0, 'vat_rate': 23},
    {'code': 'PT-PISC-054', 'type': 'ouvrage', 'category': 'Piscinas – Construção e Equipamentos', 'designation': 'Preparação da piscina para inverno', 'unit': 'forfait', 'unit_price_ht': 210.0, 'vat_rate': 23},
    {'code': 'PT-PISC-055', 'type': 'ouvrage', 'category': 'Piscinas – Construção e Equipamentos', 'designation': 'Colocação em serviço no início da época', 'unit': 'forfait', 'unit_price_ht': 250.0, 'vat_rate': 23},
    {'code': 'PT-PISC-056', 'type': 'ouvrage', 'category': 'Piscinas – Construção e Equipamentos', 'designation': 'Piscina de fibra 6 x 3 m instalada', 'unit': 'forfait', 'unit_price_ht': 12500.0, 'vat_rate': 23},
    {'code': 'PT-PISC-057', 'type': 'ouvrage', 'category': 'Piscinas – Construção e Equipamentos', 'designation': 'Piscina de fibra 8 x 4 m instalada', 'unit': 'forfait', 'unit_price_ht': 18000.0, 'vat_rate': 23},
    {'code': 'PT-PISC-058', 'type': 'ouvrage', 'category': 'Piscinas – Construção e Equipamentos', 'designation': 'Piscina em betão 6 x 3 m completa', 'unit': 'forfait', 'unit_price_ht': 19500.0, 'vat_rate': 23},
    {'code': 'PT-PISC-059', 'type': 'ouvrage', 'category': 'Piscinas – Construção e Equipamentos', 'designation': 'Piscina em betão 7 x 3,5 m completa', 'unit': 'forfait', 'unit_price_ht': 22500.0, 'vat_rate': 23},
    {'code': 'PT-PISC-060', 'type': 'ouvrage', 'category': 'Piscinas – Construção e Equipamentos', 'designation': 'Piscina em betão 8 x 4 m completa', 'unit': 'forfait', 'unit_price_ht': 26500.0, 'vat_rate': 23},
    {'code': 'PT-PISC-061', 'type': 'ouvrage', 'category': 'Piscinas – Construção e Equipamentos', 'designation': 'Piscina em betão 9 x 4 m completa', 'unit': 'forfait', 'unit_price_ht': 30500.0, 'vat_rate': 23},
    {'code': 'PT-PISC-062', 'type': 'ouvrage', 'category': 'Piscinas – Construção e Equipamentos', 'designation': 'Piscina em betão 10 x 5 m completa', 'unit': 'forfait', 'unit_price_ht': 37500.0, 'vat_rate': 23},
]



def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class LibraryItemIn(BaseModel):
    type: str = "ouvrage"
    category: str = ""
    designation: str = ""
    unit: str = "u"
    unit_price_ht: float = Field(default=0.0, ge=0)
    vat_rate: float = Field(default=10.0, ge=0, le=100)
    notes: str = ""


def _clean(body: LibraryItemIn) -> dict:
    t = body.type if body.type in ("ouvrage", "materiau") else "ouvrage"
    return {
        "type": t,
        "category": (body.category or "").strip()[:80],
        "designation": (body.designation or "").strip()[:200],
        "unit": (body.unit or "u").strip()[:12],
        "unit_price_ht": round(float(body.unit_price_ht or 0), 2),
        "vat_rate": float(body.vat_rate if body.vat_rate is not None else 10.0),
        "notes": (body.notes or "").strip()[:500],
    }


async def _seed_if_needed(user: dict) -> None:
    """Insère le catalogue de départ une seule fois par utilisateur."""
    if user.get("library_seeded"):
        return
    now = _now()
    docs = [{
        "item_id": "lib_" + secrets.token_hex(6),
        "user_id": user["user_id"],
        **item,
        "unit_price_ht": round(float(item["unit_price_ht"]), 2),
        "vat_rate": float(item["vat_rate"]),
        "notes": "",
        "source": "starter",
        "created_at": now,
        "updated_at": now,
    } for item in STARTER_CATALOGUE]
    if docs:
        await db.library_items.insert_many(docs)
    await db.users.update_one({"user_id": user["user_id"]},
                              {"$set": {"library_seeded": True}})


@router.get("")
async def list_items(q: str = "", type: str = "", user=Depends(current_user)) -> dict:
    await _seed_if_needed(user)
    query: dict = {"user_id": user["user_id"]}
    if type in ("ouvrage", "materiau"):
        query["type"] = type
    if q.strip():
        rx = {"$regex": q.strip(), "$options": "i"}
        query["$or"] = [{"designation": rx}, {"category": rx}]
    items = await db.library_items.find(query, {"_id": 0}).sort("designation", 1).to_list(5000)
    cats = sorted({(i.get("category") or "Autre") for i in items})
    return {"items": items, "count": len(items), "categories": cats}


@router.post("")
async def create_item(body: LibraryItemIn, user=Depends(current_user)) -> dict:
    data = _clean(body)
    if not data["designation"]:
        raise HTTPException(400, "La désignation est obligatoire")
    doc = {
        "item_id": "lib_" + secrets.token_hex(6),
        "user_id": user["user_id"],
        **data,
        "source": "manual",
        "created_at": _now(),
        "updated_at": _now(),
    }
    await db.library_items.insert_one(dict(doc))
    doc.pop("_id", None)
    return doc


@router.put("/{item_id}")
async def update_item(item_id: str, body: LibraryItemIn,
                      user=Depends(current_user)) -> dict:
    data = _clean(body)
    if not data["designation"]:
        raise HTTPException(400, "La désignation est obligatoire")
    res = await db.library_items.update_one(
        {"item_id": item_id, "user_id": user["user_id"]},
        {"$set": {**data, "updated_at": _now()}})
    if not res.matched_count:
        raise HTTPException(404, "Élément introuvable")
    doc = await db.library_items.find_one(
        {"item_id": item_id, "user_id": user["user_id"]}, {"_id": 0})
    return doc


@router.delete("/{item_id}")
async def delete_item(item_id: str, user=Depends(current_user)) -> dict:
    res = await db.library_items.delete_one(
        {"item_id": item_id, "user_id": user["user_id"]})
    if not res.deleted_count:
        raise HTTPException(404, "Élément introuvable")
    return {"ok": True}


@router.post("/reset-catalogue")
async def reset_catalogue(user=Depends(current_user)) -> dict:
    """Réinsère le catalogue de départ (utile si l'utilisateur a tout supprimé)."""
    await db.users.update_one({"user_id": user["user_id"]},
                              {"$unset": {"library_seeded": ""}})
    fresh = await db.users.find_one({"user_id": user["user_id"]}, {"_id": 0})
    await _seed_if_needed(fresh or user)
    count = await db.library_items.count_documents({"user_id": user["user_id"]})
    return {"ok": True, "count": count}



async def auto_save_from_lines(user_id: str, lines: list[dict]) -> int:
    """Enregistre/actualise automatiquement les postes d'un devis dans la bibliothèque de l'entreprise."""
    saved = 0
    for ln in lines or []:
        desig = (ln.get("designation") or "").strip()
        if len(desig) < 3:
            continue
        cat = (ln.get("category") or "").strip()
        if cat.lower().startswith("situation") or cat.lower().startswith("avancement"):
            continue  # on n'archive pas les lignes de situation
        set_fields = {
            "designation": desig,
            "type": "ouvrage",
            "category": cat or "Depuis devis",
            "unit": ln.get("unit") or "u",
            "unit_price_ht": round(float(ln.get("unit_price_ht") or 0), 2),
            "vat_rate": float(ln.get("vat_rate") or 10),
            "updated_at": _now(),
        }
        desc = (ln.get("description") or ln.get("notes") or "").strip()
        if desc:
            set_fields["notes"] = desc[:500]
        existing = await db.library_items.find_one(
            {"user_id": user_id,
             "designation": {"$regex": f"^{re.escape(desig)}$", "$options": "i"}},
            {"_id": 0, "item_id": 1})
        if existing:
            await db.library_items.update_one(
                {"user_id": user_id, "item_id": existing["item_id"]}, {"$set": set_fields})
        else:
            await db.library_items.insert_one({
                "item_id": "lib_" + secrets.token_hex(6), "user_id": user_id,
                "source": "devis", "notes": set_fields.pop("notes", ""),
                "created_at": _now(), **set_fields,
            })
        saved += 1
    return saved
