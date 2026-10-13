"""Organization policy shared by the permission endpoint and business routes.

Identity is still resolved by the existing JWT/Google dependencies from MongoDB.
Historical solo professionals keep access; unknown/inactive memberships do not.
"""
from fastapi import Depends, HTTPException

FEATURES = ["dashboard", "devis", "factures", "situations", "chantier", "rh", "catalogue", "entreprise", "pointage"]
ROLE_PERMISSIONS = {
    "owner": {f: True for f in FEATURES},
    "admin": {f: True for f in FEATURES},
    "chef_chantier": {f: f in {"dashboard", "devis", "situations", "chantier", "rh", "catalogue"} for f in FEATURES},
    "comptable": {f: f in {"dashboard", "devis", "factures", "situations", "catalogue"} for f in FEATURES},
    "member": {f: f in {"dashboard", "devis", "catalogue"} for f in FEATURES},
    "ouvrier": {f: f == "pointage" for f in FEATURES},
}


def permissions_for(user: dict) -> dict:
    denied = {f: False for f in FEATURES}
    if user.get("role") == "admin":
        return dict(ROLE_PERMISSIONS["owner"])
    if user.get("company_active") is False or user.get("active") is False or user.get("account_type") == "particulier":
        return denied
    if user.get("organization_id"):
        return dict(ROLE_PERMISSIONS.get(user.get("org_role"), denied))
    if user.get("role") == "worker":
        return dict(ROLE_PERMISSIONS["ouvrier"])
    return dict(ROLE_PERMISSIONS["owner"])


def require_feature(user: dict, feature: str) -> None:
    if permissions_for(user).get(feature) is not True:
        raise HTTPException(403, "A sua função não permite este acesso.")


def feature_dependency(feature: str):
    from core.security import pro_required

    async def check(user=Depends(pro_required)):
        require_feature(user, feature)
        return user
    return check