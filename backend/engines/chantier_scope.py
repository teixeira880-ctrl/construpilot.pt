"""Owner-scoped links; a legacy name must never override an explicit dossier."""
import re


def named_scope(chantier, user_id, *, owner_key="user_id", id_key="chantier_id", name_key="project"):
    choices = [{id_key: chantier["chantier_id"]}]
    if (chantier.get("name") or "").strip():
        choices.append({id_key: None, name_key: {"$regex": f"^{re.escape(chantier['name'].strip())}$", "$options": "i"}})
    return {owner_key: user_id, "$or": choices}


async def labor_scope(db, chantier, user_id):
    query = named_scope(chantier, user_id, owner_key="employer_id", id_key="project_id", name_key="project_name")
    # The HR module uses projects IDs. Only explicitly linked, owned projects qualify.
    linked = await db.projects.find({"user_id": user_id, "chantier_id": chantier["chantier_id"]}, {"project_id": 1}).to_list(501)
    if len(linked) > 500:
        from fastapi import HTTPException
        raise HTTPException(422, "Trop de projets RH liés à ce dossier")
    ids = [p["project_id"] for p in linked if p.get("project_id")]
    if ids:
        query["$or"].append({"project_id": {"$in": ids}})
    return query


async def purchase_scope(db, chantier, user_id):
    query = named_scope(chantier, user_id)
    plans = await db.plans_takeoff.find({"user_id": user_id, "chantier_id": chantier["chantier_id"]}, {"plan_id": 1}).to_list(1001)
    if len(plans) > 1000:
        from fastapi import HTTPException
        raise HTTPException(422, "Trop de plans liés à ce dossier")
    ids = [p["plan_id"] for p in plans if p.get("plan_id")]
    if ids:
        query["$or"].extend([{"chantier_id": None, "plan_id": {"$in": ids}}, {"chantier_id": None, "plan_ids": {"$in": ids}}])
    return query
