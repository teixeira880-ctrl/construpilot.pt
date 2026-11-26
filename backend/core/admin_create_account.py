"""Criação de contas por um administrador (botão «Criar conta» do back-office).

Regras:
  - A palavra-passe provisória é escrita pelo admin no formulário; só o hash
    bcrypt é guardado (nunca o texto).
  - A conta nasce com `must_change_password=True`: no primeiro início de sessão
    a app leva o cliente para «A minha conta», onde muda a palavra-passe e
    acrescenta o telefone (que pode ficar vazio na criação).
  - E-mail único: se já existir uma conta, nada é alterado (erro 400).
  - Nenhum entitlement / subscrição paga é criado aqui: o tipo de conta e o
    plano são os mesmos que o admin já pode mudar na tabela Utilizadores.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone

ACCOUNT_TYPES = ("particulier", "pro", "pro_business")
PLANS = ("free", "premium", "pro")
MIN_PASSWORD = 8
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class AccountCreateError(ValueError):
    """Erro de validação com mensagem pronta a mostrar ao admin."""


def normalize_input(data: dict, lang_default: str) -> dict:
    email = (data.get("email") or "").strip().lower()
    if not _EMAIL_RE.match(email):
        raise AccountCreateError("E-mail inválido")
    pw = data.get("temp_password") or ""
    if len(pw) < MIN_PASSWORD:
        raise AccountCreateError(f"Palavra-passe provisória: mínimo {MIN_PASSWORD} caracteres")
    account_type = data.get("account_type") or "pro_business"
    if account_type not in ACCOUNT_TYPES:
        raise AccountCreateError("Tipo de conta inválido")
    plan = data.get("plan") or "pro"
    if plan not in PLANS:
        raise AccountCreateError("Plano inválido")
    company = (data.get("company_name") or "").strip()[:120] or None
    name = (data.get("name") or "").strip()[:120] or company or email.split("@")[0]
    phone = (data.get("phone") or "").strip()[:20] or None
    siret = re.sub(r"[ .\-]", "", data.get("siret") or "")[:20] or None
    lang = (data.get("lang") or lang_default or "pt").strip().lower()[:5]
    return {"email": email, "temp_password": pw, "account_type": account_type,
            "plan": plan, "company_name": company, "name": name,
            "phone": phone, "siret": siret, "lang": lang}


async def create_account(db, data: dict, *, hash_password, new_user_id, admin_id: str,
                         lang_default: str = "pt", now: datetime | None = None) -> dict:
    """Cria a conta e devolve o documento público (sem hash)."""
    d = normalize_input(data, lang_default)
    if await db.users.find_one({"email": d["email"]}, {"_id": 0, "user_id": 1}):
        raise AccountCreateError("Já existe uma conta com este e-mail")
    is_pro = d["account_type"] in ("pro", "pro_business")
    user = {
        "user_id": new_user_id(), "email": d["email"], "name": d["name"],
        "company_name": d["company_name"], "phone": d["phone"],
        "password_hash": hash_password(d["temp_password"]), "picture": None,
        "role": "user", "plan": d["plan"], "auth_provider": "password",
        "account_type": d["account_type"], "siret": d["siret"],
        "kyc_status": "pending" if is_pro else "not_applicable", "kyc_documents": {},
        "lang": d["lang"], "email_verified": True,
        "must_change_password": True, "two_fa_enabled": False,
        "provisioned_by_admin": True, "created_by_admin": admin_id,
        "created_at": (now or datetime.now(timezone.utc)).isoformat(),
    }
    await db.users.insert_one(dict(user))
    user.pop("password_hash", None)
    user.pop("_id", None)
    return user
