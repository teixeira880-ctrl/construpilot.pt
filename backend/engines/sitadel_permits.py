"""Only observed SDES fields; no invented dates, surface, name or street."""
import os
import re
from datetime import date, datetime, timezone
from urllib.parse import urlencode

from engines.radar_filters import observed_categories
from engines.sitadel_text import repair_source_row


def window_start(today=None):
    today = today or datetime.now(timezone.utc).date()
    try:
        return today.replace(year=today.year - 1).isoformat()
    except ValueError:
        return today.replace(year=today.year - 1, day=28).isoformat()


def text(value):
    return str(value).strip() if value is not None else ""


def iso_date(value):
    try:
        return date.fromisoformat(text(value)[:10]).isoformat()
    except ValueError:
        return None


def amount(row, key):
    try:
        return max(0, float(row.get(key) or 0))
    except (TypeError, ValueError):
        return 0


def official_permit(row, meta, rid, kind, department, communes):
    row, text_corrections = repair_source_row(row)
    auth = iso_date(row.get("DATE_REELLE_AUTORISATION"))
    if (not auth or not window_start() <= auth <= datetime.now(timezone.utc).date().isoformat()
            or text(row.get("DEP_CODE")) != department or row.get("TYPE_DAU") != "PC"
            or row.get("ETAT_DAU") not in (2, 5) or not row.get("NUM_DAU")):
        return None
    num = text(row["NUM_DAU"])
    commune = communes.get(text(row.get("COMM")), {})
    coordinates = (commune.get("centre") or {}).get("coordinates")
    cj = text(row.get("CJ_DEM"))
    company = bool(re.fullmatch(r"[2-9]\d{3}", cj))
    # The official file does not contain the applicant's street. Never use the site street here.
    promoteur = {"nom": text(row.get("DENOM_DEM")), "siren": text(row.get("SIREN_DEM")),
        "siret": text(row.get("SIRET_DEM")), "categorie_juridique": cj, "adresse1": "", "adresse2": "",
        "cp": text(row.get("CODPOST_DEM")), "ville": text(row.get("LOCALITE_DEM")),
        "email": "", "telephone": ""} if company else None
    hab = amount(row, "SURF_HAB_CREEE") + amount(row, "SURF_HAB_ISSUE_TRANSFO")
    loc = amount(row, "SURF_LOC_CREEE") + amount(row, "SURF_LOC_ISSUE_TRANSFO")
    status = "Licenciado" if row["ETAT_DAU"] == 2 else "Iniciado"
    name = "Habitações" if kind == "logements" else "Espaços não residenciais"
    nature = {1: "neuf", 2: "renovation"}.get(row.get("NATURE_PROJET_DECLAREE"), "inconnue")
    if row.get("I_EXTENSION") is True:
        name += " · extension"
    elif nature == "renovation":
        name += " · obras em edifício existente"
    record_url = f'{os.environ["SITADEL_API_URL"].rstrip("/")}/datafiles/{rid}/rows?' + urlencode({
        "millesime": meta["millesime"], "NUM_DAU": f"eq:{num}", "page": 1, "pageSize": 10})
    source = {"name": "SDES · SITADEL", "kind": "sitadel_official", "verified": True,
        "dataset_id": meta.get("dataset"), "rid": rid, "millesime": meta["millesime"],
        "published_at": meta["published"], "coverage_end": meta.get("temporal_coverage", {}).get("end"),
        "record_url": record_url, "url": os.environ["SITADEL_PORTAL_URL"]}
    return {"id": "SITADEL-PC-" + num, "num": num, "type": "Licença de construção", "nature": nature,
        "commune": text(row.get("ADR_LOCALITE_TER")) or commune.get("nom") or text(row.get("COMM")),
        "map_commune": commune.get("nom") or text(row.get("COMM")),
        "insee_commune": text(row.get("COMM")), "cp": text(row.get("ADR_CODPOST_TER")), "dep": department,
        "adresse": " ".join(filter(None, [text(row.get("ADR_NUM_TER")), text(row.get("ADR_LIBVOIE_TER"))])) if text(row.get("ADR_LIBVOIE_TER")) else "",
        "adresse_complement": text(row.get("ADR_LIEUDIT_TER")),
        "lat": coordinates[1] if coordinates else None, "lon": coordinates[0] if coordinates else None,
        "geometry_precision": "commune_centroid" if coordinates else "unknown",
        "geometry_source": os.environ["SITADEL_COMMUNES_URL"], "batiment": name,
        "surface_hab": hab, "surface_loc": loc, "surf_created": hab + loc,
        "surface_basis": "Área criada ou resultante de transformação declarada",
        "logements": int(amount(row, "NB_LGT_TOT_CREES")),
        "date_depot": iso_date(row.get("DR_DEPOT")), "date_auth": auth,
        "statut": status, "statut_code": row["ETAT_DAU"], "mo": ("SCI" if cj.startswith("654") else "COLLECTIVITE" if cj.startswith("7") else "ENTREPRISE") if company else "DESCONHECIDO",
        "promoteur": promoteur, "coordonnees_status": "partiel" if promoteur else "absent",
        "source": source, "source_records": [source], "is_demo": False,
        **observed_categories(row, kind), "source_text_corrections": text_corrections,
        "imported_at": datetime.now(timezone.utc).isoformat()}


def merge_permits(existing, incoming):
    # Mixed-use permits can occur in both files. Keep one project, never sum duplicate surfaces.
    if existing is None:
        return incoming
    existing["source_records"].extend(incoming["source_records"])
    for field in ("work_types", "building_types"):
        values = set(existing.get(field, [])) | set(incoming.get(field, []))
        existing[field] = sorted(values - {"inconnu"}) or ["inconnu"]
    existing.setdefault("source_text_corrections", {}).update(incoming.get("source_text_corrections") or {})
    for field in ("surface_hab", "surface_loc", "logements"):
        existing[field] = max(existing[field], incoming[field])
    existing["surf_created"] = existing["surface_hab"] + existing["surface_loc"]
    if not existing.get("promoteur"):
        existing["promoteur"] = incoming.get("promoteur")
        existing["mo"] = incoming["mo"]
    if len(existing["source_records"]) > 1:
        existing["batiment"] = "Projeto misto · habitação e comércio/serviços"
    return existing