"""Révocation one-shot des 3 JWT fuités (dépôt Sprint 0 sécurité).

Contexte : trois fichiers `.token.txt`, `.pro_token.txt` et `.adm_token.txt`
ont été trouvés à la racine du dépôt lors de l'audit. Ils étaient valides
jusqu'en décembre 2026 pour les comptes user, pro et admin.

Les JWT eux-mêmes NE SONT PLUS STOCKÉS DANS CE FICHIER : règle sécurité
"zéro secret en clair dans le dépôt". Les `sub` (user_id) ont été extraits
hors ligne lors de l'audit et sont codés en dur ci-dessous pour permettre
la révocation. Après exécution, incrémenter `token_version` sur ces comptes
rend tout JWT antérieur invalide.

Ce script :
  1) incrémente `token_version` sur chaque compte listé
     → l'auth (`core/security.py`, ligne ~46) rejette immédiatement les JWT
       dont `payload["v"] != user["token_version"]`.
  2) purge toutes les sessions actives (`user_sessions`) pour forcer la
     re-connexion sur tous les appareils.

Usage :
    cd backend && python -m scripts.revoke_leaked_tokens
"""
import asyncio

from core.db import db


# user_id extraits lors de l'audit Sprint 0 (JWT fuités déjà révoqués en prod).
# Les JWT eux-mêmes ne sont PAS stockés ici (règle sécurité).
LEAKED_USER_IDS = [
    "user_ed759360fbfe",
    "user_1d2b550f454f",
    "user_900764e6f9e9",
]


async def main() -> None:
    user_ids = list(LEAKED_USER_IDS)
    print(f"Révocation pour {len(user_ids)} comptes : {user_ids}")

    for user_id in user_ids:
        r = await db.users.update_one(
            {"user_id": user_id},
            {"$inc": {"token_version": 1}},
        )
        print(f"  {user_id}: matched={r.matched_count} modified={r.modified_count}")

    sess = await db.user_sessions.delete_many({"user_id": {"$in": user_ids}})
    print(f"Sessions purgées : {sess.deleted_count}")
    print("\n✔ Tokens fuités désormais invalides. Rotation JWT_SECRET recommandée en complément.")


if __name__ == "__main__":
    asyncio.run(main())
