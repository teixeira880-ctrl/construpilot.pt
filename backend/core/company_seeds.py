"""Contas Pro de empresas parceiras criadas a pedido do fundador.

Corre em CADA arranque (produção incluída), de forma idempotente:
  - Conta ausente -> criada SEM palavra-passe (zero segredos no código).
    A empresa ativa o acesso em « Esqueci-me da palavra-passe » com o seu e-mail:
    o fluxo /api/auth/forgot-password envia um link « definir a palavra-passe ».
  - Ficha da empresa + página pública + logótipo aplicados UMA só vez (marcador
    `company_seed_version`): as alterações feitas depois pela empresa nunca são reescritas.
  - O logótipo é lido de backend/data/company_logos/<ficheiro>.
"""
from __future__ import annotations

import base64
import logging
import os
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger("company_seeds")
LOGO_DIR = Path(__file__).resolve().parent.parent / "data" / "company_logos"

COMPANIES = [
    {
        "seed_version": 3,
        # Conta de DEMONSTRAÇÃO : login fictício num domínio ConstruPilot (ninguém de fora recebe e-mails).
        "email": "clt-rezult.demo@construpilot.pt",
        "legacy_emails": ["office@clt-rezult.com"],
        # PDFs idênticos aos da CM RENOV : mesmo nível de conta e mesmo modelo de documento.
        "style_from_email": "contact@cmrenov.com",
        "style_defaults": {"account_type": "pro_business", "brand_doc_layout": "detaille", "kyc_status": "verified"},
        "name": "CLT Rezult",
        "account_type": "pro_business",
        "lang": "en",
        "logo_file": "clt-rezult.png",
        "temp_password_env": "CLT_REZULT_TEMP_PASSWORD",
        # Repli si le secret n'est pas configuré : empreinte bcrypt du mot de passe provisoire
        # (jamais le mot de passe en clair). Changement obligatoire à la 1re connexion.
        "temp_password_bcrypt": "$2b$12$HFqaKiNQ31CrApac/kDmd.pubDWbXrLxbPlPk7EbPjOfxD1hX4n0e",
        "fields": {
            "company": "CLT Rezult",
            "company_name": "CLT Rezult",
            "brand_company_name": "CLT Rezult",
            "brand_company_email": "office@clt-rezult.com",
            "brand_address": "15, Petro Sahaidachnoho Str.",
            "brand_postal": "04070",
            "brand_city": "Kyiv, Ucrânia",
            "brand_country": "UA",
            "brand_contact_line": "+380 50 402 00 50 · office@clt-rezult.com · clt-rezult.com",
            "brand_accent_color": "#E21411",
            "brand_logo_plate": True,
            # Orçamentos/faturas automaticamente em inglês + 2.º PDF em ucraniano.
            "doc_langs": ["en", "uk"],
            "brand_tagline": "Painéis de madeira lamelada cruzada (CLT) — o primeiro e único fabricante na Ucrânia",
            "brand_description": (
                "A CLT Rezult é o primeiro e único fabricante e fornecedor de painéis multicamada "
                "de madeira lamelada cruzada (CLT) na Ucrânia. Acompanha os clientes desde a solução "
                "arquitetónica até à construção do edifício: consultoria, formação e acompanhamento.\n\n"
                "Produção própria: a CLT Rezult integra a Rezult, um dos maiores grupos de "
                "transformação de madeira da Europa de Leste (capacidade de 1,2 milhões de m³ de madeira por ano). "
                "A linha de CLT ultrapassa 91 000 m³ por ano.\n\n"
                "Painéis: até 18 m × 3,5 m; 3, 5, 7 ou 9 camadas; espessura de 60 a 360 mm; "
                "resinosas (pinho, abeto, lariço); cola de poliuretano monocomponente (PUR) sem formaldeído. "
                "Os elementos saem da fábrica prontos a montar, com vãos para janelas e roços para "
                "as redes: montagem rápida, obra limpa e custos mais baixos.\n\n"
                "Obras realizadas: casas modulares, moradias, casas em banda, edifícios multifamiliares, "
                "residências, edifícios administrativos (até 1 650 m²), de um piso a vários pisos."
            ),
            "brand_header_text": "CLT Rezult — Cross Laminated Timber",
            "brand_footer_text": (
                "CLT Rezult — Head office: 15, Petro Sahaidachnoho Str., 04070 Kyiv, Ukraine · "
                "Plant: 11-T, Serhiya Kemskoho Str., Korosten, Zhytomyr region, 11501, Ukraine"
            ),
            "service_zones": ["Ucrânia"],
            "public_slug": "clt-rezult",
            "public_published": True,
            "public_show_reviews": False,
            "public_contact_phone": "+380 50 402 00 50",
            "public_website": "https://clt-rezult.com/en/",
        },
    },
]


def _logo_data_url(fname: str) -> str | None:
    p = LOGO_DIR / fname
    if not p.is_file():
        logger.warning("Logo introuvable : %s", p)
        return None
    return "data:image/png;base64," + base64.b64encode(p.read_bytes()).decode()


async def apply_company_seeds(db, new_user_id, hash_password=None) -> dict:
    summary: dict[str, str] = {}
    now = datetime.now(timezone.utc).isoformat()
    for c in COMPANIES:
        email = c["email"].lower().strip()
        try:
            user = await db.users.find_one({"email": email}, {"_id": 0})
            if not user:
                # Migration : compte créé avant avec un ancien e-mail -> on le renomme (pas de doublon).
                for old in c.get("legacy_emails") or []:
                    legacy = await db.users.find_one({"email": old.lower()}, {"_id": 0})
                    if legacy:
                        await db.users.update_one({"user_id": legacy["user_id"]}, {"$set": {"email": email}})
                        await db.user_sessions.delete_many({"user_id": legacy["user_id"]})
                        user = {**legacy, "email": email}
                        summary[email] = f"renamed_from:{old}"
                        break
            if not user:
                user = {"email": email, "name": c["name"], "role": "user", "plan": "free",
                        "account_type": c["account_type"], "lang": c["lang"],
                        "password_hash": None, "auth_provider": "password", "picture": None,
                        "user_id": new_user_id(), "email_verified": True, "two_fa_enabled": False,
                        "provisioned_by_admin": True, "created_at": now}
                await db.users.insert_one(dict(user))
                summary[email] = "created"
            elif email not in summary:
                summary[email] = "exists"
            # Palavra-passe provisória (só via env, nunca no código) : posée UNIQUEMENT si le
            # compte n'a encore aucun mot de passe ; jamais de réécriture d'un mot de passe existant.
            temp_pw = (os.environ.get(c.get("temp_password_env") or "") or "").strip()
            temp_hash = hash_password(temp_pw) if (temp_pw and hash_password) else c.get("temp_password_bcrypt")
            if temp_hash and not user.get("password_hash"):
                await db.users.update_one({"user_id": user["user_id"]},
                                          {"$set": {"password_hash": temp_hash,
                                                    "must_change_password": True}})
                user["password_hash"] = "set"
                summary[email] += "+temp_password"
            if (user.get("company_seed_version") or 0) >= c["seed_version"]:
                continue
            upd = dict(c["fields"])
            # le slug ne doit pas voler celui d'une autre entreprise
            if await db.users.find_one({"public_slug": upd["public_slug"], "user_id": {"$ne": user["user_id"]}}, {"_id": 1}):
                upd["public_slug"] = f"{upd['public_slug']}-{user['user_id'][-4:]}"
            logo = _logo_data_url(c["logo_file"])
            if logo:
                upd["brand_logo_b64"] = logo
            # Style des PDF : copié du compte de référence (CM RENOV) s'il existe, sinon valeurs par défaut.
            style = dict(c.get("style_defaults") or {})
            if c.get("style_from_email"):
                ref = await db.users.find_one({"email": c["style_from_email"]},
                                              {"_id": 0, "account_type": 1, "brand_doc_layout": 1, "kyc_status": 1})
                for k, v in (ref or {}).items():
                    if v and k in ("brand_doc_layout", "kyc_status"):
                        style[k] = v
            upd.update(style)
            if not upd.get("account_type"):
                upd["account_type"] = c["account_type"]
            upd["company_seed_version"] = c["seed_version"]
            await db.users.update_one({"user_id": user["user_id"]}, {"$set": upd})
            summary[email] += "+page"
            logger.info("Page entreprise %s publiée : /entreprise/%s", c["name"], upd["public_slug"])
        except Exception as exc:  # noqa: BLE001
            logger.warning("Seed entreprise %s échoué : %s", email, exc)
            summary[email] = "error"
    return summary
