"""Identifiants des comptes de test — lus EXCLUSIVEMENT depuis l'environnement.

Règle sécurité : ZÉRO password en clair dans ce fichier (ni fallback). Si une variable
n'est pas définie dans .env, l'attribut correspondant vaut None et le test doit
abort/skip explicitement au lieu d'utiliser un fallback hardcoded.

Variables attendues dans backend/.env :
  - TEST_ADMIN_EMAIL / TEST_ADMIN_PASSWORD
  - TEST_PRO_EMAIL   / TEST_PRO_PASSWORD
  - TEST_COLLEGUE_EMAIL / TEST_COLLEGUE_PASSWORD
  - TEST_CLIENT_EMAIL   / TEST_CLIENT_PASSWORD
  - TEST_DEMO_EMAIL     / TEST_DEMO_PASSWORD

Les anciens emails hardcoded (admin/pro/collegue/client/demo @construpilot.fr) restent
comme valeurs par défaut d'adresse email (public, non sensible), mais les passwords
sont strictement sans fallback.
"""
import os


def _pwd(key: str) -> str | None:
    v = (os.environ.get(key) or "").strip()
    return v if v and v != "<redacted>" else None


ADMIN_EMAIL = os.environ.get("TEST_ADMIN_EMAIL", "admin@construpilot.fr")
ADMIN_PWD = _pwd("TEST_ADMIN_PASSWORD")
PRO_EMAIL = os.environ.get("TEST_PRO_EMAIL", "pro@construpilot.fr")
PRO_PWD = _pwd("TEST_PRO_PASSWORD")
COLLEGUE_EMAIL = os.environ.get("TEST_COLLEGUE_EMAIL", "collegue@construpilot.fr")
COLLEGUE_PWD = _pwd("TEST_COLLEGUE_PASSWORD")
CLIENT_EMAIL = os.environ.get("TEST_CLIENT_EMAIL", "client@construpilot.fr")
CLIENT_PWD = _pwd("TEST_CLIENT_PASSWORD")
DEMO_EMAIL = os.environ.get("TEST_DEMO_EMAIL", "demo@construpilot.fr")
DEMO_PWD = _pwd("TEST_DEMO_PASSWORD")

ADMIN = (ADMIN_EMAIL, ADMIN_PWD)
PRO = (PRO_EMAIL, PRO_PWD)
COLLEGUE = (COLLEGUE_EMAIL, COLLEGUE_PWD)
CLIENT = (CLIENT_EMAIL, CLIENT_PWD)
