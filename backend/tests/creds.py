"""Identifiants des comptes de test — surchargeables par variables d'environnement.

Aucun secret de production : ce sont les comptes seed du preview
(créés uniquement quand SEED_DEMO_DATA=true).
"""
import os

ADMIN_EMAIL = os.environ.get("TEST_ADMIN_EMAIL", "admin@construpilot.fr")
ADMIN_PWD = os.environ.get("TEST_ADMIN_PASSWORD", "Construpilot2026!")
PRO_EMAIL = os.environ.get("TEST_PRO_EMAIL", "pro@construpilot.fr")
PRO_PWD = os.environ.get("TEST_PRO_PASSWORD", "Pro2026!")
COLLEGUE_EMAIL = os.environ.get("TEST_COLLEGUE_EMAIL", "collegue@construpilot.fr")
COLLEGUE_PWD = os.environ.get("TEST_COLLEGUE_PASSWORD", "Collegue2026!")
CLIENT_EMAIL = os.environ.get("TEST_CLIENT_EMAIL", "client@construpilot.fr")
CLIENT_PWD = os.environ.get("TEST_CLIENT_PASSWORD", "Client2026!")
DEMO_EMAIL = os.environ.get("TEST_DEMO_EMAIL", "demo@construpilot.fr")
DEMO_PWD = os.environ.get("TEST_DEMO_PASSWORD", "Demo2026!")

ADMIN = (ADMIN_EMAIL, ADMIN_PWD)
PRO = (PRO_EMAIL, PRO_PWD)
COLLEGUE = (COLLEGUE_EMAIL, COLLEGUE_PWD)
CLIENT = (CLIENT_EMAIL, CLIENT_PWD)
