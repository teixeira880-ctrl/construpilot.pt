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
    item = {
        "id": "TEST_ITER144_UI_MISSING_SITE",
        "num": "PC TEST UI 144 001",
        "type": "Permis de construire",
        "nature": "neuf",
        "commune": "",
        "cp": "",
        "dep": "75",
        "adresse": "",
        "lat": 48.8566,
        "lon": 2.3522,
        "batiment": "Terrain incomplet TEST UI 144",
        "surf_created": 210,
        "logements": 0,
        "date_depot": "2026-05-10",
        "date_auth": "2026-06-10",
        "statut": "Autorisé",
        "mo": "ENTREPRISE",
        "promoteur": {
            "nom": "Entreprise complète TEST 144",
            "adresse1": "10 rue du Contact",
            "cp": "69001",
            "ville": "Lyon",
            "societe": "Contact Complet SAS",
        },
        "coordonnees_status": "complet",
        "imported_at": now,
        "is_demo": False,
    }
    db.radar_permits.update_one({"id": item["id"]}, {"$set": item}, upsert=True)
    print("seeded=1")


if __name__ == "__main__":
    main()
