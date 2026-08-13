"""Aggregator des routes plans/takeoffs.

Refactor iter53 : le fichier historique (2385 lignes, 48 imports) a été
découpé en modules focalisés :
- `plans_common`   → routers, helpers partagés (branding, snapshot, portal…)
- `plans_crud`     → upload / list / get / delete / calibrate / defaults / levels
- `plans_analysis` → IA + CV + rooms + mesures + takeoff + matériaux + history + compare
- `plans_render`   → rendu 3D (Nano Banana) + tour vidéo
- `plans_export`   → PDF, envoi devis, TVA, rappels, notifs, signature, portail

Ce fichier ne fait que réimporter les modules pour enregistrer les endpoints
sur les deux routers partagés, et réexporte les symboles attendus par
`server.py` (router, quote_router, _run_reminders, build_client_portal_token).
"""
from __future__ import annotations

# Importing the sub-modules registers all endpoints on the shared routers.
from routes import plans_crud as _crud  # noqa: F401
from routes import plans_analysis as _analysis  # noqa: F401
from routes import plans_render as _render  # noqa: F401
from routes import plans_export as _export  # noqa: F401

from routes.plans_common import (  # noqa: F401 - re-exports
    build_client_portal_token,
    quote_router,
    router,
)
from routes.plans_export import _run_reminders  # noqa: F401 - scheduler entry point
