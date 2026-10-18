"""Seed Web Summit demo accounts (PT only) — idempotent, fail-closed.

Objectivo: criar as 2 contas demo que o fundador vai usar no stand do Web Summit
em `construpilot.pt`:
    - conta Pro:        email = $WEBSUMMIT_DEMO_EMAIL_PT (default demo.websummit@construpilot.pt),
                         password hash a partir de $WEBSUMMIT_DEMO_PASSWORD_PT
    - conta Particular: email = $WEBSUMMIT_DEMO_PARTICULAR_EMAIL_PT (default demo.websummit.particular@construpilot.pt),
                         password hash a partir de $WEBSUMMIT_DEMO_PARTICULAR_PASSWORD_PT

Regras de segurança não-negociáveis:
    - Zero password em claro neste ficheiro.
    - Fail-closed: se um dos pares email/password estiver ausente ou vazio no .env,
      a conta correspondente NÃO é criada; log neutro `"websummit demo: skipped (missing config)"`.
    - Password NUNCA é reescrita se já corresponde ao hash do segredo actual.
    - Email NUNCA é alterado após criação.
    - Flag `is_demo=True` + `demo_source="websummit_2026"` para bloquear acções em runtime.
    - Projecto "Moradia Martins" criado 1 vez; dados sintéticos reset diário por tarefa separada.
    - Documentos BET-core demo + branding fictício "Construções Horizonte, Lda." aplicados a cada
      startup / reset diário / endpoint admin via `apply_demo_showcase_pt`.
"""
from __future__ import annotations

import base64
import logging
import os
import secrets
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger("websummit_seed_pt")

# Nome do projecto demo e metadata associada (nenhum dado real).
DEMO_PROJECT_NAME = "Moradia Martins"
DEMO_SOURCE = "websummit_2026"
DEMO_PLAN_FIXTURE = "/app/backend/tests/fixtures/plans_pro/thumbnail_moradia_sintetica.png"


def _env(key: str) -> Optional[str]:
    v = (os.environ.get(key) or "").strip()
    if not v or v == "<redacted>":
        return None
    return v


def _config() -> dict:
    """Lê a configuração de env. Devolve dict com chaves `pro` e `particular`.

    Cada entrada tem `email` e `password` ou None se qualquer um dos dois estiver
    em falta (fail-closed por conta).
    """
    pro_email = _env("WEBSUMMIT_DEMO_EMAIL_PT") or "demo.websummit@construpilot.pt"
    pro_pwd = _env("WEBSUMMIT_DEMO_PASSWORD_PT")
    particular_email = _env("WEBSUMMIT_DEMO_PARTICULAR_EMAIL_PT") or "demo.websummit.particular@construpilot.pt"
    particular_pwd = _env("WEBSUMMIT_DEMO_PARTICULAR_PASSWORD_PT")
    return {
        "pro": {
            "email": pro_email.lower(),
            "password": pro_pwd,
            "name": "Demo Pro Web Summit",
            "account_type": "pro",
            "plan": "premium",
            "plan_id": "pro_business_monthly",
        },
        "particular": {
            "email": particular_email.lower(),
            "password": particular_pwd,
            "name": "Demo Particular Web Summit",
            "account_type": "particulier",
            "plan": "free",
            "plan_id": None,
        },
    }


async def seed_websummit_demo_pt(db, hash_password_fn, verify_password_fn, new_user_id_fn) -> dict:
    """Chamado uma vez no startup. Retorna um resumo (sem segredos).

    - db: motor Mongo async.
    - hash_password_fn / verify_password_fn / new_user_id_fn: injectados de core.security.
    """
    cfg = _config()
    summary = {"pro": "skipped_missing_config", "particular": "skipped_missing_config", "project": None}

    for kind, acc in cfg.items():
        if not acc["password"]:
            logger.info("websummit demo: skipped (missing config)")  # neutro, sem citar var
            continue
        email = acc["email"]
        existing = await db.users.find_one({"email": email}, {"_id": 0})
        now = datetime.now(timezone.utc).isoformat()

        if not existing:
            # Criação inicial.
            doc = {
                "email": email,
                "name": acc["name"],
                "role": "user",
                "plan": acc["plan"],
                "account_type": acc["account_type"],
                "country": "PT",
                "language": "pt",
                "password_hash": hash_password_fn(acc["password"]),
                "auth_provider": "password",
                "picture": None,
                "user_id": new_user_id_fn(),
                "must_change_password": False,
                "email_verified": True,
                "two_fa_enabled": False,
                "is_demo": True,
                "demo_source": DEMO_SOURCE,
                "demo_quota_ai_calls_today": 0,
                "demo_quota_date": now[:10],
                "active": True,
                "created_at": now,
            }
            await db.users.insert_one(dict(doc))
            summary[kind] = "created"
            logger.info("websummit demo: account %s created", kind)
        else:
            # Idempotente: só actualiza se faltar flag ou se password já não corresponder.
            update = {}
            if not existing.get("is_demo"):
                update["is_demo"] = True
            if existing.get("demo_source") != DEMO_SOURCE:
                update["demo_source"] = DEMO_SOURCE
            if existing.get("plan") != acc["plan"]:
                update["plan"] = acc["plan"]
            if existing.get("account_type") != acc["account_type"]:
                update["account_type"] = acc["account_type"]
            if not existing.get("email_verified"):
                update["email_verified"] = True
            # Password: SÓ reescrever se não corresponder ao segredo actual.
            # (ex: fundador rodou a password nos Production Secrets — queremos realinhar.)
            current_hash = existing.get("password_hash") or ""
            if not current_hash or not verify_password_fn(acc["password"], current_hash):
                update["password_hash"] = hash_password_fn(acc["password"])
                logger.info("websummit demo: account %s password realigned to current secret", kind)
            if update:
                await db.users.update_one({"email": email}, {"$set": update})
                summary[kind] = "updated"
            else:
                summary[kind] = "unchanged"

        # Entitlement Pro só para a conta Pro.
        if acc["plan_id"]:
            user = await db.users.find_one({"email": email}, {"user_id": 1})
            ent_id = f"websummit_demo_{user['user_id']}"
            ent = await db.entitlements.find_one({"entitlement_id": ent_id}, {"_id": 0})
            if not ent:
                await db.entitlements.insert_one({
                    "entitlement_id": ent_id,
                    "user_id": user["user_id"],
                    "plan_id": acc["plan_id"],
                    "plan_code": "PRO_BUSINESS_MONTHLY",
                    "kind": "subscription",
                    "audience": "pro",
                    "status": "active",
                    "granted_at": now,
                    "source": "websummit_demo_seed",
                })

    # Projecto "Moradia Martins" para a conta Pro — criado 1 vez.
    pro_email = cfg["pro"]["email"]
    if cfg["pro"]["password"]:
        pro_user = await db.users.find_one({"email": pro_email}, {"user_id": 1})
        if pro_user:
            existing_project = await db.projects.find_one({
                "owner_user_id": pro_user["user_id"],
                "name": DEMO_PROJECT_NAME,
                "is_demo": True,
            })
            if not existing_project:
                project_id = "prj_" + secrets.token_hex(6)
                await db.projects.insert_one({
                    "project_id": project_id,
                    "name": DEMO_PROJECT_NAME,
                    "description": "Moradia unifamiliar T3 em Lisboa — dados demo não executivos.",
                    "owner_user_id": pro_user["user_id"],
                    "status": "active",
                    "location": "Lisboa, Portugal",
                    "work_type": "construcao_nova",
                    "is_demo": True,
                    "demo_source": DEMO_SOURCE,
                    "created_at": datetime.now(timezone.utc).isoformat(),
                })
                summary["project"] = "created"
                logger.info("websummit demo: project 'Moradia Martins' created")
            else:
                summary["project"] = "unchanged"

    # Showcase BET-core: documentos demo + branding fictício nas contas demo.
    # Idempotente, não duplica, preserva dados pré-existentes.
    try:
        showcase_summary = await apply_demo_showcase_pt(db)
        summary["showcase"] = showcase_summary
    except Exception as exc:  # noqa: BLE001
        logger.warning("websummit demo seed: showcase step failed (%s)", exc)
        summary["showcase"] = f"error: {exc}"

    return summary


async def reset_websummit_demo_data_pt(db) -> dict:
    """Reset diário dos dados sintéticos (chamado por background task + endpoint admin).

    O que é reset:
      - Mensagens de assistente de obra na conta demo pro (keep só 1 conversa seed)
      - Orçamentos criados pela conta demo
      - Fotos/documentos adicionados pela conta demo
      - Reset do contador de quota IA diário

    O que NÃO é reset (preserva integridade):
      - User doc (email, password_hash, is_demo, etc.)
      - Projecto Moradia Martins (recriado se faltar)
      - Entitlements
    """
    cfg = _config()
    pro_email = cfg["pro"]["email"]
    particular_email = cfg["particular"]["email"]
    reset_summary = {"pro_user_id": None, "particular_user_id": None, "deleted_counts": {}}

    for email, key in [(pro_email, "pro_user_id"), (particular_email, "particular_user_id")]:
        user = await db.users.find_one({"email": email, "is_demo": True}, {"user_id": 1})
        if not user:
            continue
        uid = user["user_id"]
        reset_summary[key] = uid

        # Lista de colecções a limpar — só documentos criados pela conta demo.
        collections_to_clean = [
            "quotes", "takeoffs", "photos", "project_documents",
            "assistant_messages", "coach_messages", "activity_log",
            "notifications", "email_logs", "stripe_customer_actions",
        ]
        deleted = {}
        for coll in collections_to_clean:
            try:
                r = await db[coll].delete_many({"user_id": uid})
                if r.deleted_count:
                    deleted[coll] = r.deleted_count
            except Exception as exc:  # noqa: BLE001
                logger.warning("websummit demo reset: skipped %s (%s)", coll, exc)
        reset_summary["deleted_counts"][key] = deleted

        # Reset quota diária.
        today = datetime.now(timezone.utc).isoformat()[:10]
        await db.users.update_one(
            {"user_id": uid},
            {"$set": {"demo_quota_ai_calls_today": 0, "demo_quota_date": today}},
        )

    # Re-aplicar documentos BET-core demo + branding fictício. Idempotente.
    try:
        showcase_summary = await apply_demo_showcase_pt(db)
        reset_summary["showcase"] = showcase_summary
    except Exception as exc:  # noqa: BLE001
        logger.warning("websummit demo reset: showcase step failed (%s)", exc)
        reset_summary["showcase"] = f"error: {exc}"

    logger.info("websummit demo: data reset executed")
    return reset_summary


# ---------------------------------------------------------------------------
# Showcase BET-core: documentos + branding fictício "Construções Horizonte, Lda."
# ---------------------------------------------------------------------------

# Marker usado pelos documentos BET-core demo (filename-based idempotence).
DEMO_DOCS_MARK = "DEMO"
DEMO_CASE_ID = "moradia_pt_demo"


async def _upsert_demo_doc(db, user_id: str, filename: str, data: bytes) -> str:
    """Insere ou actualiza um documento BET-core demo em `assistant_docs`.

    Idempotência: match por (user_id, filename). Mantém o `doc_id` existente
    quando aplicável — apenas o conteúdo e o `updated_at` são refrescados.
    Formato: `data_b64` inline (schema do `.pt` descoberto em
    `routes/assistant.py::_allowed_doc`).
    """
    now = datetime.now(timezone.utc).isoformat()
    data_b64 = base64.b64encode(data).decode()
    existing = await db.assistant_docs.find_one(
        {"user_id": user_id, "filename": filename},
        {"_id": 0, "doc_id": 1},
    )
    if existing and existing.get("doc_id"):
        await db.assistant_docs.update_one(
            {"user_id": user_id, "doc_id": existing["doc_id"]},
            {"$set": {
                "data_b64": data_b64,
                "mime": "application/pdf",
                "kind": "pdf",
                "updated_at": now,
                "is_demo": True,
                "demo_source": DEMO_SOURCE,
            }},
        )
        return existing["doc_id"]
    doc_id = "doc_" + secrets.token_hex(8)
    await db.assistant_docs.insert_one({
        "doc_id": doc_id,
        "user_id": user_id,
        "filename": filename,
        "mime": "application/pdf",
        "data_b64": data_b64,
        "kind": "pdf",
        "is_demo": True,
        "demo_source": DEMO_SOURCE,
        "created_at": now,
        "updated_at": now,
    })
    return doc_id


async def apply_demo_showcase_pt(db) -> dict:
    """Instala documentos BET-core demo e branding "Construções Horizonte, Lda.".

    - Conta demo Pro (plan_id Pro Business): recebe os 2 PDF + branding completo.
    - Conta demo Particular: recebe só os 2 PDF (sem branding — não é empresa).
    - Idempotente: executar múltiplas vezes não duplica documentos.
    - Preserva dados demo pré-existentes (projecto Moradia Martins, etc.).
    - Fail-closed por conta: se config em falta, salta essa conta.
    """
    cfg = _config()
    summary: dict = {"docs": {}, "branding": {}}

    # Lazy import — evita custo de reportlab/PIL se a função nunca for chamada.
    try:
        from engines.bet_core.samples import build_all, demo_branding
    except Exception as exc:  # noqa: BLE001
        logger.warning("websummit demo showcase: bet_core samples unavailable (%s)", exc)
        return {"error": f"samples_unavailable: {exc}"}

    # Build dos PDF uma única vez por chamada (reutilizado entre contas).
    try:
        files = build_all(DEMO_CASE_ID)
    except Exception as exc:  # noqa: BLE001
        logger.warning("websummit demo showcase: build_all failed (%s)", exc)
        return {"error": f"build_failed: {exc}"}

    for kind, acc in cfg.items():
        if not acc["password"]:
            summary["docs"][kind] = "skipped_missing_config"
            continue
        user = await db.users.find_one(
            {"email": acc["email"], "is_demo": True, "demo_source": DEMO_SOURCE},
            {"user_id": 1},
        )
        if not user:
            summary["docs"][kind] = "skipped_user_absent"
            continue
        uid = user["user_id"]

        # (1) Documentos BET-core demo em `assistant_docs` (ambas as contas).
        inserted_ids = []
        for filename, data in files.items():
            doc_id = await _upsert_demo_doc(db, uid, filename, data)
            inserted_ids.append(doc_id)
        summary["docs"][kind] = {"count": len(inserted_ids), "doc_ids": inserted_ids}

        # (2) Branding "Construções Horizonte, Lda." — Pro apenas.
        # A conta particular representa um utilizador final (sem empresa) e deve
        # ficar com o tema ConstruPilot default: NÃO aplicar branding.
        if kind == "pro":
            try:
                b = demo_branding("PT")
            except Exception as exc:  # noqa: BLE001
                logger.warning("websummit demo showcase: demo_branding failed (%s)", exc)
                summary["branding"][kind] = f"skipped_build_error: {exc}"
                continue
            brand_fields = {f"brand_{k}": v for k, v in b.items()}
            await db.users.update_one(
                {"user_id": uid},
                {"$set": brand_fields},
            )
            summary["branding"][kind] = "applied"
        else:
            summary["branding"][kind] = "skipped_not_pro"

    logger.info("websummit demo showcase applied: %s", summary)
    return summary


# ----- Helpers chamados a partir das rotas /auth/demo-login e dos guards -----

async def get_demo_user_by_kind(db, kind: str) -> Optional[dict]:
    """Devolve o utilizador demo pedido (`pro` ou `particular`) ou None.

    Protecções:
      - só devolve se `is_demo=True` e `demo_source=websummit_2026`.
      - caller é responsável por autenticar via `verify_password` com a password do env.
    """
    cfg = _config()
    acc = cfg.get(kind)
    if not acc or not acc["password"]:
        return None
    user = await db.users.find_one({
        "email": acc["email"],
        "is_demo": True,
        "demo_source": DEMO_SOURCE,
    }, {"_id": 0})
    return user


def get_demo_password_by_kind(kind: str) -> Optional[str]:
    """Devolve a password do env para o kind pedido (`pro`|`particular`).

    Usada SÓ pelo backend em `/auth/demo-login` para fazer o verify_password
    interno. Nunca retornar ao frontend.
    """
    cfg = _config()
    acc = cfg.get(kind)
    return acc["password"] if acc else None


def is_websummit_demo_configured() -> dict:
    """Devolve estado da configuração (sem valores). Útil para health check."""
    cfg = _config()
    return {
        "pro_configured": bool(cfg["pro"]["password"]),
        "particular_configured": bool(cfg["particular"]["password"]),
    }
