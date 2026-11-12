"""CLT access: the engines are open to every PT account; the pilot account keeps what is dedicated to it."""
import hmac
import json
import os

from bim_studio.store import tenant_of
from core.market import SITE_COUNTRY


def enabled_for(user_id, tenant_id):
    if SITE_COUNTRY != "PT" or not isinstance(user_id, str) or not isinstance(tenant_id, str):
        return False
    owner = os.environ.get("CLT_PILOT_USER_ID", "").strip()
    tenant = os.environ.get("CLT_PILOT_TENANT_ID", "").strip()
    if owner and tenant and hmac.compare_digest(user_id.encode(), owner.encode()) and hmac.compare_digest(tenant_id.encode(), tenant.encode()):
        return True
    try:
        accounts = json.loads(os.environ.get("CLT_PILOT_ACCOUNTS", "{}"))
    except ValueError:
        return False
    return bool(isinstance(accounts, dict) and tenant_id and accounts.get(user_id) == tenant_id)


def _active(user):
    return bool(user and user.get("user_id") and user.get("active") is not False and user.get("company_active") is not False)


def allowed(user):
    """CLT page, engines and CLT study: every active account of the PT app (decision of 2026-11-11).

    Each company works on its own data (parameters, prices, libraries and lots are stored per tenant)."""
    return _active(user) and SITE_COUNTRY == "PT" and isinstance(tenant_of(user), str)


def is_pilot(user):
    """The pilot account(s): what is dedicated to them (CLT Rezult branding of the dossiers) stays theirs."""
    return _active(user) and enabled_for(user["user_id"], tenant_of(user))
