"""À exécuter depuis backend : python -m scripts.setup_assistant_indexes.

Crée uniquement des index ; ne supprime ni ne réécrit de données existantes.
Une collision d'index unique doit être examinée avant de relancer.
"""
import asyncio
from core.db import db


async def main():
    await db.assistant_settings.create_index('user_id', unique=True)
    await db.assistant_convs.create_index([('user_id', 1), ('updated_at', -1)])
    await db.assistant_msgs.create_index([('conversation_id', 1), ('created_at', -1)])
    await db.assistant_prefs.create_index([('user_id', 1), ('scope', 1), ('active', 1)])
    await db.assistant_prefs.create_index([('organization_id', 1), ('scope', 1), ('active', 1)])
    await db.assistant_work_drafts.create_index([('user_id', 1), ('draft_id', 1)], unique=True)
    await db.assistant_docs.create_index([('user_id', 1), ('doc_id', 1)])
    await db.assistant_doc_chunks.create_index([('user_id', 1), ('doc_id', 1), ('index', 1)], unique=True)
    await db.plan_cad_sources.create_index([('user_id', 1), ('plan_id', 1), ('source_kind', 1), ('index', 1)], unique=True)
    await db.plan_sources.create_index([('user_id', 1), ('plan_id', 1)], unique=True)
    await db.plan_source_chunks.create_index([('user_id', 1), ('plan_id', 1), ('source_generation', 1), ('index', 1)], unique=True)
    print('Index assistant / CAO prêts.')


if __name__ == '__main__':
    try:
        asyncio.run(main())
    finally:
        db.client.close()
