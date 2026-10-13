"""Correction automatique des problèmes d'audit SEO.

Chaque correction est appliquée à chaud (surcharges lues par le site : title/description/canonical, redirections 404) et
tracée dans `growth_fix_runs`. Le problème passe en statut `fixing` ; seul un ré-audit qui ne le retrouve plus le clôture (`fixed`).
Ce qui ne peut pas être corrigé sans toucher au code est listé avec une raison — jamais de faux « corrigé ».
"""
import difflib
import logging
from urllib.parse import urlparse

from core.db import db
from growth.common import new_id, now_iso

logger = logging.getLogger(__name__)

META_KINDS = {"missing_title", "long_title", "missing_description", "long_description", "duplicate_title"}
CANONICAL_KINDS = {"canonical_mismatch", "missing_canonical"}
REDIRECT_KINDS = {"http_error", "broken_links"}
MANUAL_REASONS = {
    "missing_h1": "Structure de page : le H1 se corrige dans le composant de la page (déploiement requis).",
    "multiple_h1": "Structure de page : un seul H1 doit rester dans le composant (déploiement requis).",
    "thin_html": "HTML initial trop léger : dépend du pré-rendu / SSR côté hébergement.",
    "slow_response": "Temps de réponse : dépend de l'hébergement et du pré-rendu, pas d'une balise.",
    "heavy_html": "Poids du HTML : optimisation du bundle à faire dans le code.",
    "img_alt": "Attributs alt : à renseigner sur chaque image dans le code des pages.",
    "jsonld_invalid": "JSON-LD invalide : à corriger dans le composant qui l'émet.",
    "redirect_chain": "Chaîne de redirections : à simplifier dans la configuration du domaine / CDN.",
    "hreflang_target_error": "La cible hreflang répond en erreur : publier la page équivalente ou retirer l'alternate.",
    "missing_hreflang": "Hreflang : nécessite une page équivalente FR/PT confirmée.",
    "hreflang_no_default": "x-default : géré par le code des balises <head> (déploiement requis).",
    "sitemap_missing": "Sitemap absent : à générer côté serveur.",
    "noindex": "noindex explicite : décision éditoriale à confirmer avant de l'enlever.",
    "no_viewport": "Meta viewport : dans index.html (déploiement requis).",
    "missing_lang": "Attribut lang : géré par le code des balises <head> (déploiement requis).",
    "lang_mismatch": "Attribut lang : géré par le code des balises <head> (déploiement requis).",
    "inaccessible": "Page inaccessible : vérifier l'hébergement ou la redirection.",
    "no_html": "Contenu non HTML : à servir en HTML côté serveur.",
}


def _path(url: str) -> str:
    p = urlparse(url).path or "/"
    return p if p == "/" or not p.endswith("/") else p.rstrip("/")


async def _mark_fixing(issue_ids: list[str], how: str) -> None:
    if issue_ids:
        await db.growth_issues.update_many({"issue_id": {"$in": issue_ids}}, {"$set": {"status": "fixing", "fix_applied": how, "fix_applied_at": now_iso(), "fixed_by": "autofix"}})


async def _fix_meta(project: dict, audit: dict, issues: list[dict]) -> list[dict]:
    """Titres / descriptions : génération LLM puis application directe (statut approved) via propose_seo_overrides."""
    from growth.autopilot import propose_seo_overrides
    await db.growth_seo_overrides.update_many({"project_id": project["project_id"], "status": "proposed"},
                                              {"$set": {"status": "approved", "decided_at": now_iso(), "decided_by": "autofix"}})
    created = await propose_seo_overrides(project, audit, "auto")
    out = []
    by_url: dict[str, list] = {}
    for i in issues:
        by_url.setdefault(i["url"], []).append(i)
    for url, items in by_url.items():
        ov = await db.growth_seo_overrides.find_one({"project_id": project["project_id"], "path": _path(url), "status": "approved"}, {"_id": 0, "override_id": 1, "title": 1})
        if not ov:
            continue
        await _mark_fixing([i["issue_id"] for i in items], f"Surcharge title/description appliquée ({ov['override_id']})")
        out.append({"kind": "meta", "url": url, "how": f"Titre « {ov['title']} » et description appliqués à chaud", "issue_ids": [i["issue_id"] for i in items], "ref": ov["override_id"]})
    if created:
        logger.info("autofix meta: %s surcharge(s) créée(s)", created)
    return out


async def _fix_canonical(project: dict, issues: list[dict]) -> list[dict]:
    """La canonical doit être l'URL finale de la page elle-même : surcharge `canonical` lue par les balises <head>."""
    out = []
    for i in issues:
        path = _path(i["url"])
        await db.growth_seo_overrides.update_one(
            {"project_id": project["project_id"], "path": path, "kind": "canonical"},
            {"$set": {"canonical": path, "url": i["url"], "status": "approved", "updated_at": now_iso(), "created_by": "autofix", "issue_kinds": [i["kind"]]},
             "$setOnInsert": {"override_id": new_id("seo"), "created_at": now_iso(), "project_id": project["project_id"], "path": path, "kind": "canonical"},
             "$addToSet": {"issue_ids": i["issue_id"]}}, upsert=True)
        await _mark_fixing([i["issue_id"]], f"Canonical forcée sur {path}")
        out.append({"kind": "canonical", "url": i["url"], "how": f"Canonical fixée à {path}", "issue_ids": [i["issue_id"]]})
    return out


async def _fix_redirects(project: dict, audit: dict, issues: list[dict]) -> tuple[list[dict], list[dict]]:
    """URL en erreur : redirection vers la page valide la plus proche (similarité de chemin ≥ 0,6), sinon manuel."""
    ok_paths = sorted({_path(p["url"]) async for p in db.growth_pages.find({"audit_id": audit["audit_id"], "status_code": {"$lt": 400}}, {"_id": 0, "url": 1})})
    fixed, manual = [], []
    for i in issues:
        broken = [i["url"]] if i["kind"] == "http_error" else [u.strip() for u in (i.get("evidence") or "").replace("→", " ").split() if u.startswith("http")]
        for url in broken:
            src = _path(url)
            if src in ok_paths or src == "/":
                continue
            best = difflib.get_close_matches(src, [p for p in ok_paths if p != src], n=1, cutoff=0.6)
            if not best:
                manual.append({"kind": i["kind"], "url": url, "reason": "Aucune page valide assez proche pour une redirection sûre."})
                continue
            await db.growth_redirects.update_one({"project_id": project["project_id"], "from_path": src},
                                                 {"$set": {"to_path": best[0], "status": "approved", "created_by": "autofix", "updated_at": now_iso(), "issue_id": i["issue_id"]},
                                                  "$setOnInsert": {"redirect_id": new_id("rdr"), "created_at": now_iso()}}, upsert=True)
            await _mark_fixing([i["issue_id"]], f"Redirection {src} → {best[0]}")
            fixed.append({"kind": "redirect", "url": url, "how": f"Redirection {src} → {best[0]}", "issue_ids": [i["issue_id"]]})
    return fixed, manual


async def _align_stale(project_id: str, audit_id: str) -> int:
    """Doublons d'audits précédents encore « ouverts » : ils suivent le statut du même défaut (URL + type) dans le dernier audit,
    ou passent en correction appliquée si une surcharge approuvée couvre déjà leur page."""
    n = 0
    async for i in db.growth_issues.find({"project_id": project_id, "status": "open", "audit_id": {"$ne": audit_id}}, {"_id": 0, "issue_id": 1, "url": 1, "kind": 1}):
        latest = await db.growth_issues.find_one({"audit_id": audit_id, "url": i["url"], "kind": i["kind"]}, {"_id": 0, "status": 1, "fix_applied": 1})
        sets = None
        if latest and latest["status"] in ("fixed", "fixing", "ignored"):
            sets = {"status": latest["status"], "fix_applied": latest.get("fix_applied") or "Aligné sur le dernier audit", "fixed_by": "autofix"}
        elif i["kind"] in META_KINDS | CANONICAL_KINDS:
            kind_q = {"kind": "canonical"} if i["kind"] in CANONICAL_KINDS else {"kind": {"$ne": "canonical"}}
            if await db.growth_seo_overrides.find_one({"project_id": project_id, "path": _path(i["url"]), "status": "approved", **kind_q}, {"_id": 1}):
                sets = {"status": "fixing", "fix_applied": "Surcharge approuvée déjà en place", "fixed_by": "autofix"}
        if sets:
            await db.growth_issues.update_one({"issue_id": i["issue_id"]}, {"$set": {**sets, "fix_applied_at": now_iso()}})
            n += 1
    return n


async def run(project: dict, audit: dict | None, trigger: str = "manual") -> dict:
    """Corrige tout ce qui est corrigeable sur les problèmes ouverts du dernier audit ; liste le reste avec sa raison."""
    if not audit:
        return {"status": "skipped", "note": "Aucun audit terminé"}
    run_id = new_id("fix")
    report = {"run_id": run_id, "project_id": project["project_id"], "audit_id": audit["audit_id"], "trigger": trigger, "started_at": now_iso(), "status": "running",
              "fixed": [], "manual": [], "counts": {}}
    await db.growth_fix_runs.insert_one(dict(report))
    try:
        from growth.autopilot import close_resolved
        report["closed_by_recrawl"] = await close_resolved(project, audit)
        report["aligned"] = await _align_stale(project["project_id"], audit["audit_id"])
        issues = await db.growth_issues.find({"audit_id": audit["audit_id"], "status": "open"}, {"_id": 0}).to_list(3000)
        meta = [i for i in issues if i["kind"] in META_KINDS]
        canon = [i for i in issues if i["kind"] in CANONICAL_KINDS]
        redir = [i for i in issues if i["kind"] in REDIRECT_KINDS]
        from growth.autopilot import budget_state
        if meta:
            if (await budget_state(project))["ok"]:
                report["fixed"] += await _fix_meta(project, audit, meta)
            else:
                report["manual"] += [{"kind": i["kind"], "url": i["url"], "reason": "Plafond budget IA atteint : génération des titres suspendue."} for i in meta]
        report["fixed"] += await _fix_canonical(project, canon)
        f, m = await _fix_redirects(project, audit, redir)
        report["fixed"] += f
        report["manual"] += m
        handled = {iid for x in report["fixed"] for iid in x["issue_ids"]}
        for i in issues:  # les doublons d'audits précédents (même URL, même défaut) suivent la même correction
            if i["issue_id"] in handled:
                await db.growth_issues.update_many({"project_id": project["project_id"], "url": i["url"], "kind": i["kind"], "status": "open"},
                                                   {"$set": {"status": "fixing", "fix_applied": "Même correction que le dernier audit", "fix_applied_at": now_iso(), "fixed_by": "autofix"}})
        for i in issues:
            if i["issue_id"] in handled or i["kind"] in REDIRECT_KINDS:
                continue
            if i["kind"] in META_KINDS:
                report["manual"].append({"kind": i["kind"], "url": i["url"], "reason": "Génération du titre/description impossible pour cette page (réessai au prochain cycle)."})
            elif i["kind"] not in CANONICAL_KINDS:
                report["manual"].append({"kind": i["kind"], "url": i["url"], "reason": MANUAL_REASONS.get(i["kind"], i.get("fix") or "Correction manuelle nécessaire.")})
        report["counts"] = {"open_before": len(issues), "fixed": sum(len(x["issue_ids"]) for x in report["fixed"]), "manual": len(report["manual"]),
                            "awaiting_recrawl": await db.growth_issues.count_documents({"project_id": project["project_id"], "status": "fixing"})}
        report.update({"status": "completed", "finished_at": now_iso()})
    except Exception as e:  # noqa: BLE001
        logger.exception("autofix failed")
        report.update({"status": "failed", "error": f"{type(e).__name__}: {e}"[:300], "finished_at": now_iso()})
    await db.growth_fix_runs.update_one({"run_id": run_id}, {"$set": report})
    return report


async def flag_reappeared(project_id: str, audit_id: str) -> int:
    """Un problème re-détecté alors qu'une correction est active : le site crawlé n'applique pas (encore) la surcharge (déploiement ?)."""
    n = 0
    async for i in db.growth_issues.find({"audit_id": audit_id, "status": "open"}, {"_id": 0, "issue_id": 1, "url": 1, "kind": 1}):
        prev = await db.growth_issues.find_one({"project_id": project_id, "url": i["url"], "kind": i["kind"], "status": "fixing", "audit_id": {"$ne": audit_id}}, {"_id": 0, "fix_applied": 1})
        if prev:
            await db.growth_issues.update_one({"issue_id": i["issue_id"]}, {"$set": {"fix_active": True, "fix_note": f"Correction déjà appliquée ({prev.get('fix_applied')}) mais non visible sur le site crawlé — vérifier que la dernière version est déployée."}})
            n += 1
    return n
