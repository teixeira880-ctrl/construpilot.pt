"""Données officielles ADEME — DPE existant & Audit énergétique (open data).

Deux jeux de données publics, gratuits et fiables (API data-fair data.ademe.fr) :
  • dpe03existant   → état énergétique réel d'un logement (par n° de DPE)
  • audit-opendata  → scénarios de rénovation officiels avant/après (par n° de DPE)

RÈGLE ConstruPilot : données OFFICIELLES reprises telles quelles (déterministe,
aucune IA, aucun chiffre inventé). Rien n'est recalculé ici.
"""
from __future__ import annotations

import httpx

DPE_DATASET = "https://data.ademe.fr/data-fair/api/v1/datasets/dpe03existant/lines"
DPE_NEUF_DATASET = "https://data.ademe.fr/data-fair/api/v1/datasets/dpe02neuf/lines"
DPE_TERT_DATASET = "https://data.ademe.fr/data-fair/api/v1/datasets/dpe01tertiaire/lines"
AUDIT_DATASET = "https://data.ademe.fr/data-fair/api/v1/datasets/audit-opendata/lines"
TIMEOUT = 20.0
HEADERS = {"User-Agent": "ConstruPilot/1.0"}

DPE_SELECT = [
    "numero_dpe", "numero_dpe_immeuble_associe", "date_etablissement_dpe",
    "etiquette_dpe", "etiquette_ges",
    "conso_5_usages_par_m2_ep", "conso_5_usages_par_m2_ef",
    "emission_ges_5_usages_par_m2", "cout_total_5_usages",
    "type_batiment", "surface_habitable_logement", "surface_habitable_immeuble",
    "periode_construction", "hauteur_sous_plafond", "classe_inertie_batiment",
    "adresse_ban", "code_postal_ban", "nom_commune_ban", "code_insee_ban",
    "adresse_brut", "code_postal_brut", "nom_commune_brut",
    "type_energie_principale_chauffage", "description_installation_chauffage_n1",
    "type_energie_principale_ecs", "type_generateur_n1_ecs_n1", "type_installation_ecs",
    "type_ventilation",
    "qualite_isolation_enveloppe", "qualite_isolation_murs",
    "qualite_isolation_plancher_bas", "qualite_isolation_plancher_haut_toit_terrasse",
    "qualite_isolation_menuiseries",
    "deperditions_murs", "deperditions_planchers_bas",
    "deperditions_planchers_hauts", "deperditions_baies_vitrees",
]

AUDIT_SELECT = [
    "n_audit", "numero_dpe", "etape_travaux", "categorie_scenario",
    "classe_bilan_dpe", "etiquette_ges", "cout_travaux", "travaux_realises",
    "ep_conso_5_usages_m2", "emission_ges_5_usages_m2",
    "gain_relatif_conso_5_usages_m2_ep",
    "date_etablissement_audit",
]


async def _query(url: str, numero: str, select: list[str], size: int = 50) -> list[dict]:
    base = {"qs": f'numero_dpe:"{numero}"', "size": str(size)}
    async with httpx.AsyncClient(timeout=TIMEOUT, follow_redirects=True) as client:
        r = await client.get(url, params={**base, "select": ",".join(select)}, headers=HEADERS)
        if r.status_code == 400:
            # Certains datasets (ex. dpe02neuf) rejettent des champs inconnus du select.
            r = await client.get(url, params=base, headers=HEADERS)
        r.raise_for_status()
        return r.json().get("results") or []


async def fetch_dpe(numero: str) -> dict | None:
    """État énergétique officiel par n° de DPE : existant → neuf → tertiaire. None sinon."""
    numero = (numero or "").strip().upper()
    if not numero:
        return None
    kind = "existant"
    rows = await _query(DPE_DATASET, numero, DPE_SELECT, size=1)
    if not rows:
        rows = await _query(DPE_NEUF_DATASET, numero, DPE_SELECT, size=1)
        if rows:
            kind = "neuf"
    if not rows:
        rows = await _query(DPE_TERT_DATASET, numero, DPE_SELECT, size=1)
        if rows:
            kind = "tertiaire"
    if not rows:
        return None
    p = rows[0]
    source = {
        "existant": "Certificado energético oficial — dados abertos (existente)",
        "neuf": "Certificado energético oficial — dados abertos (novo)",
        "tertiaire": "Certificado energético oficial — dados abertos (serviços)",
    }[kind]
    return {
        "source": source,
        "is_neuf": kind == "neuf",
        "is_tertiaire": kind == "tertiaire",
        "numero_dpe": p.get("numero_dpe"),
        "numero_dpe_immeuble": p.get("numero_dpe_immeuble_associe"),
        "date_dpe": p.get("date_etablissement_dpe"),
        "etiquette_energie": p.get("etiquette_dpe"),
        "etiquette_climat": p.get("etiquette_ges"),
        "conso_ep_m2": p.get("conso_5_usages_par_m2_ep") or p.get("conso_kwhep_m2_an"),
        "conso_ef_m2": p.get("conso_5_usages_par_m2_ef") or p.get("conso_kwhef_m2_an"),
        "ges_m2": p.get("emission_ges_5_usages_par_m2") or p.get("emission_ges_kgco2_m2_an"),
        "cout_annuel": p.get("cout_total_5_usages"),
        "type_batiment": p.get("type_batiment") or (("tertiaire" if kind == "tertiaire" else None)),
        "categorie_erp": p.get("categorie_erp"),
        "surface_m2": p.get("surface_habitable_logement") or p.get("surface_utile"),
        "surface_immeuble_m2": p.get("surface_habitable_immeuble"),
        "periode_construction": p.get("periode_construction"),
        "hauteur_sous_plafond": p.get("hauteur_sous_plafond"),
        "inertie": p.get("classe_inertie_batiment"),
        "adresse": p.get("adresse_ban") or p.get("adresse_brut"),
        "code_postal": p.get("code_postal_ban") or p.get("code_postal_brut"),
        "commune": p.get("nom_commune_ban") or p.get("nom_commune_brut"),
        "code_insee": p.get("code_insee_ban"),
        "chauffage_energie": p.get("type_energie_principale_chauffage"),
        "chauffage_desc": p.get("description_installation_chauffage_n1"),
        "ecs_energie": p.get("type_energie_principale_ecs"),
        "ecs_generateur": p.get("type_generateur_n1_ecs_n1") or p.get("type_installation_ecs"),
        "ventilation": p.get("type_ventilation"),
        "isolation": {
            "enveloppe": p.get("qualite_isolation_enveloppe"),
            "murs": p.get("qualite_isolation_murs"),
            "plancher_bas": p.get("qualite_isolation_plancher_bas"),
            "plancher_haut": p.get("qualite_isolation_plancher_haut_toit_terrasse"),
            "menuiseries": p.get("qualite_isolation_menuiseries"),
        },
        "deperditions": {
            "murs": p.get("deperditions_murs"),
            "planchers_bas": p.get("deperditions_planchers_bas"),
            "planchers_hauts": p.get("deperditions_planchers_hauts"),
            "baies_vitrees": p.get("deperditions_baies_vitrees"),
        },
    }


async def fetch_audit_scenarios(numero_dpe: str) -> list[dict]:
    """Scénarios de rénovation officiels (audit énergétique) rattachés à un n° de DPE.
    Regroupés par audit, chaque audit listant ses étapes (état initial → étape finale)."""
    numero_dpe = (numero_dpe or "").strip().upper()
    if not numero_dpe:
        return []
    rows = await _query(AUDIT_DATASET, numero_dpe, AUDIT_SELECT, size=50)
    audits: dict[str, dict] = {}
    for r in rows:
        na = r.get("n_audit") or "audit"
        audits.setdefault(na, {"n_audit": na,
                               "date": r.get("date_etablissement_audit"),
                               "steps": []})
        audits[na]["steps"].append({
            "etape": r.get("etape_travaux"),
            "categorie": r.get("categorie_scenario"),
            "etiquette_energie": r.get("classe_bilan_dpe"),
            "etiquette_climat": r.get("etiquette_ges"),
            "conso_ep_m2": r.get("ep_conso_5_usages_m2"),
            "ges_m2": r.get("emission_ges_5_usages_m2"),
            "cout_travaux": r.get("cout_travaux"),
            "gain_relatif_ep": r.get("gain_relatif_conso_5_usages_m2_ep"),
            "travaux": r.get("travaux_realises"),
        })
    # Ordre : état initial d'abord, puis étapes.
    def _order(s):
        e = (s.get("etape") or "").lower()
        return 0 if "initial" in e else (1 if "première" in e or "premiere" in e else 2)
    out = list(audits.values())
    for a in out:
        a["steps"].sort(key=_order)
    return out
