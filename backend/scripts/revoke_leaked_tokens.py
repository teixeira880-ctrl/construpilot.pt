"""Révocation one-shot des 3 JWT fuités (dépôt Sprint 0 sécurité).

Contexte : trois fichiers `.token.txt`, `.pro_token.txt` et `.adm_token.txt`
ont été trouvés à la racine du dépôt lors de l'audit. Ils sont valides
jusqu'en décembre 2026 pour les comptes user, pro et admin.

Ce script :
  1) décode les payloads JWT pour récupérer les `sub` (user_id)
  2) incrémente `token_version` sur chaque compte
     → l'auth (`core/security.py`, ligne ~46) rejette immédiatement les JWT
       dont `payload["v"] != user["token_version"]`.
  3) purge toutes les sessions actives (`user_sessions`) pour forcer la
     re-connexion sur tous les appareils.

Usage :
    cd backend && python -m scripts.revoke_leaked_tokens
"""
import asyncio
import base64
import json

from core.db import db


# Les tokens ci-dessous ont été trouvés en clair dans le dépôt. Une fois ce
# script exécuté ils ne servent plus à rien.
LEAKED_TOKENS = [
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJ1c2VyX2VkNzU5MzYwZmJmZSIsImV4cCI6MTc4NzMwNTg4MH0.rykngrkjBFn1eTMPSbVF_j_uyRqQ1UVwkk3eN7L7J-g",
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJ1c2VyXzFkMmI1NTBmNDU0ZiIsImV4cCI6MTc4NzMwNjIwN30.83cGFmU68XQiBlJg7-6fnwXg256QZnnvK2vxc-ql7xs",
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJ1c2VyXzkwMDc2NGU2ZjllOSIsImV4cCI6MTc4NzMwNjE1OX0.Ramp0rO_JH2lSbQ9pqJf7Q1V_KWjIHSepaSb3W72Aig",
]


def _decode_sub(token: str) -> str:
    payload_b64 = token.split(".")[1]
    payload_b64 += "=" * (-len(payload_b64) % 4)
    payload = json.loads(base64.urlsafe_b64decode(payload_b64))
    return payload["sub"]


async def main() -> None:
    user_ids = [_decode_sub(t) for t in LEAKED_TOKENS]
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
