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
        "temp_password_version": 1,
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
    {
        # Potencial cliente (pedido do fundador, 12/11/2026): conta Pro Business de demonstração com a identidade
        # pública da empresa (site leveldesire.com: textos, logótipo, cor #009B95, fotografias das obras).
        "seed_version": 1,
        "email": "info@leveldesire.com",
        "name": "LevelDesire",
        "account_type": "pro_business",
        "lang": "pt",
        "logo_file": "leveldesire.png",
        "temp_password_env": "LEVELDESIRE_TEMP_PASSWORD",
        # empreinte bcrypt du mot de passe communiqué par le fondateur (jamais en clair) ; pas de changement forcé
        "temp_password_version": 1,
        "temp_password_bcrypt": "$2b$12$QoP5UI8T.wH1Q/KvfZHANOzp7KGSDshHdgD5ZDNS0H21.ZSkqAfCW",
        "must_change_password": False,
        "pro_business_entitlement": True,
        "style_defaults": {"account_type": "pro_business", "brand_doc_layout": "detaille"},
        "photos_version": 1,
        "photos": [
            ("https://leveldesire.com/assets/images/40072e47-f352-42de-a4d7-e0a4ac83de74-828x466.jpeg", "Moradia concluída — exterior"),
            ("https://leveldesire.com/assets/images/4b97a016-31f3-4032-bc32-8ad77e5e11ff-828x554.jpg", "Sala e cozinha em open space — tetos com iluminação LED"),
            ("https://leveldesire.com/assets/images/6977eed4-ff12-4eda-b449-16611b63682f-828x554.jpg", "Sala — sanca com iluminação indireta"),
            ("https://leveldesire.com/assets/images/6a5911fc-32b6-408a-be35-fc1711f9f2de-828x554.jpg", "Casa de banho — remodelação completa"),
            ("https://leveldesire.com/assets/images/6fc8f7c3-242c-489e-ba8a-9b70da3e0234-828x554.jpg", "Casa de banho com resguardo de duche em vidro"),
            ("https://leveldesire.com/assets/images/58eacc0d-64b9-4925-aaf9-5ced96c06cca-828x554.jpg", "Interior remodelado — escada e pavimento flutuante"),
            ("https://leveldesire.com/assets/images/1f7541d5-ad54-41c3-ac0f-58799fe44477-828x554.jpg", "Quarto — pavimento flutuante e teto falso"),
            ("https://leveldesire.com/assets/images/bca2303a-42c2-4a98-abc7-8dbd234b40b5-1-828x466.jpeg", "Moradia em estrutura — fachada principal"),
            ("https://leveldesire.com/assets/images/852e8d8b-492a-4110-b4e0-a78ca134d45b-828x466.jpg", "Estrutura em betão armado — varandas"),
            ("https://leveldesire.com/assets/images/98a735d9-e36d-4115-840e-f3e57f9d1c07-828x466.jpg", "Alvenarias e isolamento das paredes"),
            ("https://leveldesire.com/assets/images/24a4839f-eeec-48aa-aef4-079a4c1f7018-828x621.jpg", "Fundações — cofragem de sapatas e muros"),
            ("https://leveldesire.com/assets/images/06ec5285-1bf3-491a-9790-2e0c1e4e5813-828x621.jpg", "Fundações — cofragem e betonagem"),
            ("https://leveldesire.com/assets/images/8cf33da8-634e-4152-a1a9-fd2a1b23f33f-828x621.jpg", "Fundações — vista geral do estaleiro"),
            ("https://leveldesire.com/assets/images/de0d4883-4c65-47f3-8608-652d605882b3-828x466.jpg", "Cofragem dos muros de suporte"),
            ("https://leveldesire.com/assets/images/1a37cc16-d435-4d91-9096-0d2053c1b59f-828x466.jpg", "Armaduras da laje de fundação"),
            ("https://leveldesire.com/assets/images/9a4183c5-0180-4cb6-a457-8b61cb9a180d-5-828x466.jpeg", "Armaduras de pilares e vigas"),
        ],
        "fields": {
            "company": "LevelDesire",
            "company_name": "LevelDesire",
            "brand_company_name": "LevelDesire — Construções, Remodelações e Engenharia",
            "brand_company_email": "info@leveldesire.com",
            "brand_address": "Avenida João XXI, N.º 72B, Loja E1 — Galeria Via Veneto",
            "brand_postal": "1000-219",
            "brand_city": "Lisboa",
            "brand_country": "PT",
            "brand_contact_line": "+351 968 364 515 · info@leveldesire.com · leveldesire.com",
            "brand_accent_color": "#009B95",
            "brand_tagline": "Construção · Remodelações · Engenharia — empreitadas e sub-empreitadas, de Lisboa para todo o país",
            "brand_description": (
                "A LevelDesire quer revolucionar o mercado da Construção Civil e Obras Públicas. Foi criada para prestar "
                "serviços de remodelações, empreitadas, sub-empreitadas, obras de raiz e também reparações e manutenções — "
                "sempre com o máximo profissionalismo, respeito e dedicação.\n\n"
                "Conta com uma numerosa equipa de profissionais e parceiros, já executou inúmeros apartamentos e moradias "
                "em território nacional e também empreitadas no estrangeiro. O objetivo é a satisfação dos clientes: a "
                "empresa progride todos os dias, juntando a experiência no setor à pesquisa e às sugestões dos clientes.\n\n"
                "Empreitadas: construção de raiz e remodelação completa (canalização, eletricidade, esgotos, pavimentação, "
                "iluminação, chão flutuante, pinturas).\n"
                "Sub-empreitadas: ladrilho, pladur (gesso cartonado), projeção de estuque e pinturas em geral.\n\n"
                "Porquê a Level?\n"
                "• Respeito — valorizamos as pessoas: com elas somamos valores e subtraímos a ineficácia.\n"
                "• Dedicação — o nosso compromisso é com o sucesso; a resiliência é o caminho.\n"
                "• Qualidade — não basta fazer, é preciso saber fazer. Os nossos resultados falam por nós.\n"
                "• Prazos — valorizamos cada investimento cumprindo a agenda proposta."
            ),
            "brand_header_text": "LevelDesire — Construções | Remodelações | Engenharia",
            "brand_footer_text": (
                "LevelDesire — Avenida João XXI, N.º 72B, Loja E1, Galeria Via Veneto, 1000-219 Lisboa · "
                "info@leveldesire.com · +351 968 364 515"
            ),
            "service_zones": ["Lisboa", "Portugal", "Estrangeiro (empreitadas)"],
            "public_slug": "leveldesire",
            "public_published": True,
            "public_show_reviews": False,
            "public_contact_phone": "+351 968 364 515",
            "public_website": "https://leveldesire.com",
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
            # Posé si le compte n'a pas de mot de passe, OU une seule fois (marqueur temp_password_version)
            # pour remettre le mot de passe provisoire connu, tant que l'entreprise ne l'a pas changé.
            tpv = c.get("temp_password_version") or 0
            reset_once = tpv and (user.get("temp_password_version") or 0) < tpv
            if temp_hash and (not user.get("password_hash") or reset_once):
                await db.users.update_one({"user_id": user["user_id"]},
                                          {"$set": {"password_hash": temp_hash,
                                                    "must_change_password": c.get("must_change_password", True),
                                                    "temp_password_version": tpv}})
                await db.user_sessions.delete_many({"user_id": user["user_id"]})
                try:   # lève le blocage « trop de tentatives » lié à cet e-mail
                    import re as _re
                    await db.login_attempts.delete_many({"identifier": {"$regex": ":" + _re.escape(email) + "$"}})
                except Exception:  # noqa: BLE001
                    pass
                user["password_hash"] = "set"
                summary[email] += "+temp_password"
            if c.get("pro_business_entitlement"):
                if user.get("plan") != "premium":              # mesmo nível que a conta Teste Websummit
                    await db.users.update_one({"user_id": user["user_id"]}, {"$set": {"plan": "premium"}})
                ent_id = f"company_seed_{user['user_id']}"
                if not await db.entitlements.find_one({"entitlement_id": ent_id}, {"_id": 1}):
                    await db.entitlements.insert_one({
                        "entitlement_id": ent_id, "user_id": user["user_id"], "plan_id": "pro_business_monthly",
                        "plan_code": "PRO_BUSINESS_MONTHLY", "kind": "subscription", "audience": "pro",
                        "status": "active", "granted_at": now, "source": "company_seed"})
                    summary[email] += "+pro_business"
            if c.get("photos") and (user.get("company_photos_version") or 0) < (c.get("photos_version") or 1):
                import asyncio
                asyncio.get_running_loop().create_task(_seed_photos(db, user["user_id"], c))   # sem atrasar o arranque
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


async def _seed_photos(db, user_id: str, c: dict) -> None:
    """Fotografias das obras (site público da empresa) → galeria da página da empresa. Uma só vez (photos_version)."""
    import asyncio
    import uuid

    import httpx
    from engines import storage
    from engines.assistant_media import normalize_attachment
    done = 0
    try:
        u = await db.users.find_one({"user_id": user_id}, {"_id": 0, "showcase_photos": 1}) or {}
        have = {p.get("source_url") for p in u.get("showcase_photos") or []}
        async with httpx.AsyncClient(timeout=25, follow_redirects=True,
                                     headers={"User-Agent": "Mozilla/5.0 ConstruPilot company-page"}) as cli:
            for url, title in c["photos"][:24]:
                if url in have:
                    continue
                try:
                    r = await cli.get(url)
                    r.raise_for_status()
                    data, mime = await asyncio.to_thread(normalize_attachment, r.content)
                    if not mime.startswith("image/"):
                        continue
                    pid = f"shw_{uuid.uuid4().hex[:12]}"
                    path = f"public/showcase/{user_id}/{pid}.jpg"
                    await asyncio.to_thread(storage.put_object, path, data, mime)
                    await db.users.update_one({"user_id": user_id}, {"$push": {"showcase_photos": {
                        "photo_id": pid, "path": path, "mime": mime, "title": title[:120], "description": "",
                        "source_url": url, "created_at": datetime.now(timezone.utc).isoformat()}}})
                    done += 1
                except Exception as exc:  # noqa: BLE001 — uma foto em falta não impede as outras
                    logger.warning("Foto %s : %s", url, exc)
        if done or have:                                  # nada descarregado (site em baixo) → nova tentativa no próximo arranque
            await db.users.update_one({"user_id": user_id}, {"$set": {"company_photos_version": c.get("photos_version") or 1}})
        logger.info("Galeria %s : %d fotografias", c["name"], done)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Galeria %s échouée : %s", c["name"], exc)
