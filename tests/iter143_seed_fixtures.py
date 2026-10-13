import os
from datetime import datetime, timezone

from dotenv import load_dotenv
from pymongo import MongoClient


def main():
    load_dotenv("/app/backend/.env")
    mongo_url = os.environ.get("MONGO_URL")
    db_name = os.environ.get("DB_NAME")
    if not mongo_url or not db_name:
        raise SystemExit("Missing MONGO_URL or DB_NAME")

    db = MongoClient(mongo_url)[db_name]
    now = datetime.now(timezone.utc).isoformat()
    fixtures = [
        {
            "id": "TEST_ITER143_UI_ABSENT_PARTICULIER",
            "num": "PC TEST UI 143 001",
            "type": "Permis de construire",
            "nature": "neuf",
            "commune": "Paris",
            "cp": "75012",
            "dep": "75",
            "adresse": "14 avenue Daumesnil",
            "lat": 48.844,
            "lon": 2.381,
            "batiment": "Maison sans contact TEST UI",
            "surf_created": 130,
            "logements": 1,
            "date_depot": "2026-05-05",
            "date_auth": "2026-06-05",
            "statut": "Autorisé",
            "mo": "PARTICULIER",
            "promoteur": None,
            "coordonnees_status": "absent",
            "imported_at": now,
            "is_demo": False,
        },
        {
            "id": "TEST_ITER143_UI_PARTIAL_ENTREPRISE",
            "num": "PC TEST UI 143 002",
            "type": "Permis de construire",
            "nature": "renovation",
            "commune": "Cergy",
            "cp": "95000",
            "dep": "95",
            "adresse": "2 boulevard du Port",
            "lat": 49.036,
            "lon": 2.077,
            "batiment": "Bâtiment entreprise partiel TEST UI",
            "surf_created": 420,
            "logements": 0,
            "date_depot": "2026-05-07",
            "date_auth": "2026-06-07",
            "statut": "Autorisé",
            "mo": "ENTREPRISE",
            "promoteur": {"nom": "Entreprise partielle TEST UI"},
            "coordonnees_status": "partiel",
            "imported_at": now,
            "is_demo": False,
        },
        {
            "id": "TEST_ITER143_UI_FAR_DEP13_ENTREPRISE",
            "num": "PC TEST UI 143 003",
            "type": "Permis de construire",
            "nature": "neuf",
            "commune": "Marseille",
            "cp": "13001",
            "dep": "13",
            "adresse": "8 La Canebière",
            "lat": 43.2965,
            "lon": 5.3698,
            "batiment": "Entrepôt distant TEST UI",
            "surf_created": 900,
            "logements": 0,
            "date_depot": "2026-05-08",
            "date_auth": "2026-06-08",
            "statut": "Autorisé",
            "mo": "ENTREPRISE",
            "promoteur": {
                "nom": "TEST Import Marseille",
                "adresse1": "8 La Canebière",
                "cp": "13001",
                "ville": "Marseille",
                "siren": "123456789",
            },
            "coordonnees_status": "complet",
            "imported_at": now,
            "is_demo": False,
        },
    ]

    for item in fixtures:
        db.radar_permits.update_one({"id": item["id"]}, {"$set": item}, upsert=True)
    print(f"seeded={len(fixtures)}")


if __name__ == "__main__":
    main()
