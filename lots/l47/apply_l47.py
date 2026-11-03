"""Lot 47 — corrections trouvées au test complet du 03/11 (FR et PT).

Usage : python3 lots/l47/apply_l47.py <racine /app> <fr|pt>

Commun FR + PT :
  1. Pages réservées Business (Espace Entreprise, RH, Équipe…) : plus de redirection vers
     « Passez Pro » pendant le chargement de l'abonnement (on attend la réponse /billing/me).
  2. Liste des plans : le nombre de pièces s'affichait toujours « 0 pce » (rooms_count absent).
  3. Pop-up Web Summit : ne s'ouvre plus sur la page /demo (écran du stand).
  4. billing._level_for : un compte pro_business est reconnu « business » même sans abonnement.
PT seulement :
  5. Libellés restés en français dans Plantas & medições (pce, page, plan guardado, divisãos).
  6. Conta demo Pro : tipo pro_business + empresa demo (Espaço Empresa acessível na demo).

S'arrête (exit 1) sans rien écrire si une ancre manque. Idempotent.
"""
import pathlib
import re
import sys

root = pathlib.Path(sys.argv[1])
site = sys.argv[2]
assert site in ("fr", "pt"), "site = fr ou pt"

P = {}  # chemin -> liste de (ancre, remplacement, nombre attendu)


def add(path, old, new, count=1):
    P.setdefault(path, []).append((old, new, count))


# 1) Attendre la facturation avant de juger l'accès
BC = "frontend/src/context/BillingContext.jsx"
add(BC, '      setState({ tier: me.data.tier || "free", active: me.data.active || null, loading: false });\n',
        '      setState({ tier: me.data.tier || "free", active: me.data.active || null, loading: false, uid: user.user_id });\n')
add(BC, '    } catch {\n      setState({ tier: "free", active: null, loading: false });\n',
        '    } catch {\n      setState({ tier: "free", active: null, loading: false, uid: user.user_id });\n')
add(BC, 'value={{ ...state, flags, has, refresh }}',
        'value={{ ...state, ready: !user || state.uid === user.user_id, flags, has, refresh }}')
APP = "frontend/src/App.js"
add(APP, "const { tier } = useBilling();", "const { tier, ready: billingReady } = useBilling();", 3)

# 2) Nombre de pièces dans la liste des plans
add("backend/routes/plans_crud.py",
    '    ).sort("created_at", -1).to_list(100)\n    return {"plans": docs}\n',
    '    ).sort("created_at", -1).to_list(100)\n'
    '    for d in docs:\n'
    '        d["rooms_count"] = len(d.get("rooms") or [])\n'
    '    return {"plans": docs}\n')

# 3) Pas de pop-up sur /demo
add("frontend/public/construpilot-websummit-popup.js",
    "  if (alreadySeen()) return;\n",
    "  if (/^\\/demo(\\/|$)/.test(location.pathname || \"\")) return;\n  if (alreadySeen()) return;\n")

# 4) Niveau d'un compte pro_business
add("backend/routes/billing.py",
    '    base = "pro" if user.get("account_type") == "pro" else "particulier_gratuit"\n',
    '    at = user.get("account_type")\n'
    '    base = "business" if at == "pro_business" else "pro" if at == "pro" else "particulier_gratuit"\n')

if site == "pt":
    PTK = "frontend/src/pages/PlanTakeoff.jsx"
    add(PTK, "{p.rooms_count || 0} pce", "{p.rooms_count || 0} div.")
    add(PTK, '{(p.page_count || 1)} page{(p.page_count || 1) > 1 ? "s" : ""} · {p.rooms_count || 0} divisão{(p.rooms_count || 0) > 1 ? "s" : ""}',
             '{(p.page_count || 1)} página{(p.page_count || 1) > 1 ? "s" : ""} · {p.rooms_count || 0} {(p.rooms_count || 0) > 1 ? "divisões" : "divisão"}')
    add(PTK, '{p.page_count || 1} page{p.page_count > 1 ? "s" : ""}',
             '{p.page_count || 1} página{p.page_count > 1 ? "s" : ""}')
    add(PTK, '{allPlans.length} plan{allPlans.length > 1 ? "s" : ""} guardado{allPlans.length > 1 ? "s" : ""}',
             '{allPlans.length} planta{allPlans.length > 1 ? "s" : ""} guardada{allPlans.length > 1 ? "s" : ""}')
    add(PTK, 'Importar {pendingFiles.length} plan{pendingFiles.length > 1 ? "s" : ""}',
             'Importar {pendingFiles.length} planta{pendingFiles.length > 1 ? "s" : ""}')
    WS = "backend/core/websummit_seed_pt.py"
    add(WS, '            "account_type": "pro",\n            "plan": "premium",\n',
            '            "account_type": "pro_business",\n            "plan": "premium",\n')
    add(WS, '    return summary\n\n\nasync def reset_websummit_demo_data_pt(db) -> dict:\n',
            '    # Lote 47: empresa demo (Espaço Empresa, equipa, RH) para a conta Pro Business.\n'
            '    if cfg["pro"]["password"]:\n'
            '        try:\n'
            '            summary["org"] = await _ensure_demo_org_pt(db, cfg["pro"]["email"])\n'
            '        except Exception as exc:  # noqa: BLE001\n'
            '            logger.warning("websummit demo seed: org step failed (%s)", exc)\n'
            '            summary["org"] = f"error: {exc}"\n'
            '    return summary\n\n\n'
            'DEMO_ORG_CODE = "WEBSUMMIT-2026-PT"\n'
            '_ORG_BRAND = {"brand_company_name": "brand_company_name", "brand_contact_line": "brand_contact_line",\n'
            '              "brand_logo_b64": "brand_logo_b64", "brand_company_email": "brand_company_email",\n'
            '              "brand_nif": "brand_nif", "brand_alvara": "brand_alvara", "brand_address": "brand_address",\n'
            '              "brand_city": "brand_city", "brand_postal": "brand_postal_code"}\n'
            '\n\n'
            'async def _ensure_demo_org_pt(db, pro_email: str) -> str:\n'
            '    """Empresa fictícia da conta demo Pro (idempotente). Copia o branding fictício da conta\n'
            '    para a empresa, para que os PDF continuem com « Construções Horizonte, Lda. »."""\n'
            '    u = await db.users.find_one({"email": pro_email, "is_demo": True, "demo_source": DEMO_SOURCE}, {"_id": 0})\n'
            '    if not u:\n'
            '        return "skipped_user_absent"\n'
            '    now = datetime.now(timezone.utc).isoformat()\n'
            '    org = await db.organizations.find_one({"org_code": DEMO_ORG_CODE}, {"_id": 0})\n'
            '    if not org:\n'
            '        org = {"org_id": "org_" + secrets.token_hex(6), "org_code": DEMO_ORG_CODE,\n'
            '               "name": "Construções Horizonte, Lda. (demo)", "owner_user_id": u["user_id"],\n'
            '               "is_demo": True, "demo_source": DEMO_SOURCE, "created_at": now}\n'
            '        await db.organizations.insert_one(dict(org))\n'
            '        state = "created"\n'
            '    else:\n'
            '        state = "unchanged"\n'
            '    brand = {k: u.get(src) for k, src in _ORG_BRAND.items() if u.get(src)}\n'
            '    brand["brand_country"] = "PT"\n'
            '    await db.organizations.update_one({"org_code": DEMO_ORG_CODE}, {"$set": brand})\n'
            '    if u.get("organization_id") != org["org_id"] or u.get("org_role") != "owner":\n'
            '        await db.users.update_one({"user_id": u["user_id"]},\n'
            '                                  {"$set": {"organization_id": org["org_id"], "org_role": "owner",\n'
            '                                            "joined_org_at": now}})\n'
            '    return state\n'
            '\n\n'
            'async def reset_websummit_demo_data_pt(db) -> dict:\n')

# Contrôle des ancres puis écriture
plan = {}
for rel, edits in P.items():
    f = root / rel
    if not f.exists():
        print(f"FICHIER ABSENT : {rel} — ARRÊT")
        sys.exit(1)
    s = f.read_text(encoding="utf-8")
    done = 0
    for old, new, cnt in edits:
        if s.count(new) >= cnt and new not in old:
            done += 1
            continue
        c = s.count(old)
        if c != cnt:
            print(f"ANCRE introuvable ({c}/{cnt}) dans {rel} : {old[:70]!r} — ARRÊT, rien écrit")
            sys.exit(1)
        s = s.replace(old, new)
    plan[rel] = (s, done)

# App.js : attendre la facturation dans les 3 gardes (ProRoute, SubscriberRoute, BusinessRoute)
s, _ = plan[APP]
if "billingReady === false" not in s:
    parts = s.split("const { tier, ready: billingReady } = useBilling();")
    if len(parts) != 4:
        print("App.js : gardes inattendues — ARRÊT")
        sys.exit(1)
    for i in range(1, 4):
        if "  if (loading)\n" not in parts[i]:
            print("App.js : ancre « if (loading) » absente — ARRÊT")
            sys.exit(1)
        parts[i] = parts[i].replace("  if (loading)\n", "  if (loading || (user && billingReady === false))\n", 1)
    s = "const { tier, ready: billingReady } = useBilling();".join(parts)
plan[APP] = (s, 0)

for rel, (s, done) in plan.items():
    (root / rel).write_text(s, encoding="utf-8")
    print(f"ok {rel}" + (f" (déjà appliqué : {done})" if done else ""))
t = pathlib.Path(__file__).resolve().parent / "tests" / "test_l47.py"
(root / "backend" / "tests" / "test_l47.py").write_bytes(t.read_bytes())
print("ok backend/tests/test_l47.py")
print(f"L47 {site.upper()} OK")
