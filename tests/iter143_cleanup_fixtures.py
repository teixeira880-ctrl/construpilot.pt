import os

from dotenv import load_dotenv
from pymongo import MongoClient


def main():
    load_dotenv("/app/backend/.env")
    mongo_url = os.environ.get("MONGO_URL")
    db_name = os.environ.get("DB_NAME")
    if not mongo_url or not db_name:
        raise SystemExit("Missing MONGO_URL or DB_NAME")
    db = MongoClient(mongo_url)[db_name]

    db.radar_contacts.delete_many({"opp_id": {"$regex": r"^TEST_ITER143_UI_"}})
    db.radar_contact_searches.delete_many({"opp_id": {"$regex": r"^TEST_ITER143_UI_"}})
    db.radar_prospections.delete_many({"opp_id": {"$regex": r"^TEST_ITER143_UI_"}})
    db.radar_postal.delete_many({"opp_id": {"$regex": r"^TEST_ITER143_UI_"}})
    db.radar_permits.delete_many({"id": {"$regex": r"^TEST_ITER143_UI_"}})
    print("cleanup_done")


if __name__ == "__main__":
    main()
