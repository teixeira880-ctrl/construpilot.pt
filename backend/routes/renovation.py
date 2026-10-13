"""RenoPilot — module d'estimation énergétique et de préparation de rénovation.

Étape 1 (honnête) : questionnaire adaptatif + EvidenceStore (provenance/statut),
données manquantes, analyse qualitative Niveau A, scénarios P1/P2/P3 déterministes,
descriptif par lot, métré et chiffrage via le moteur « Corps d'état » existant.

RÈGLE ABSOLUE : aucun chiffre énergétique (classe DPE, kWh) n'est inventé.
Tant qu'un moteur 3CL certifié n'est pas branché, l'énergie reste
« moteur_non_configure » et seul un Niveau A qualitatif est produit.
"""
from __future__ import annotations

import secrets
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from fastapi.responses import Response
from pydantic import BaseModel, Field

from core.db import db
from core.security import current_user
from engines import corps_etat
from engines import ai as ai_engine
from engines import aides_reno
from engines import ademe_dpe
from engines import gemini_ocr
from routes import documents as docs_mod
from routes.plans_common import _resolve_branding
from routes.plans_analysis import _ensure_level_thumb

router = APIRouter(prefix="/renovation", tags=["renovation"])


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Questionnaire adaptatif — champs clés (sections A→J du cahier des charges)
# ---------------------------------------------------------------------------
# importance: high = pilote l'analyse/le métré ; med = utile
QUESTIONNAIRE = [
    # A — Identité & localisation
    {"path": "localisation.code_postal", "section": "A — Localização", "label": "Código postal", "unit": "", "type": "text", "importance": "high"},
    {"path": "bien.type", "section": "A — Localização", "label": "Tipo de imóvel", "unit": "", "type": "enum", "options": ["maison", "appartement", "immeuble"], "importance": "high"},
    {"path": "bien.periode_construction", "section": "A — Localização", "label": "Período de construção", "unit": "", "type": "enum", "options": ["avant 1948", "1948-1974", "1975-1988", "1989-2000", "2001-2012", "après 2012"], "importance": "high"},
    {"path": "bien.mitoyennete", "section": "A — Localização", "label": "Contiguidade", "unit": "", "type": "enum", "options": ["isolée", "1 mitoyenneté", "2 mitoyennetés", "+"], "importance": "med"},
    # B — Géométrie
    {"path": "geometrie.surface_habitable_m2", "section": "B — Geometria", "label": "Área útil", "unit": "m²", "type": "number", "importance": "high"},
    {"path": "geometrie.niveaux_chauffes", "section": "B — Geometria", "label": "Número de pisos aquecidos", "unit": "", "type": "number", "importance": "high"},
    {"path": "geometrie.hauteur_sous_plafond_m", "section": "B — Geometria", "label": "Pé-direito", "unit": "m", "type": "number", "importance": "med"},
    {"path": "geometrie.surface_murs_m2", "section": "B — Geometria", "label": "Área de paredes (da envolvente)", "unit": "m²", "type": "number", "importance": "high"},
    {"path": "geometrie.surface_toiture_m2", "section": "B — Geometria", "label": "Área de cobertura / teto superior", "unit": "m²", "type": "number", "importance": "high"},
    {"path": "geometrie.surface_plancher_bas_m2", "section": "B — Geometria", "label": "Área de pavimento inferior", "unit": "m²", "type": "number", "importance": "high"},
    {"path": "geometrie.surface_vitree_m2", "section": "B — Geometria", "label": "Área envidraçada total", "unit": "m²", "type": "number", "importance": "med"},
    # C — Parois
    {"path": "murs.materiau", "section": "C — Envolvente", "label": "Material das paredes", "unit": "", "type": "text", "importance": "med"},
    {"path": "murs.isolation", "section": "C — Envolvente", "label": "Isolamento das paredes", "unit": "", "type": "enum", "options": ["aucune", "Isolamento pelo interior", "ITE", "inconnue"], "importance": "high"},
    {"path": "toiture.isolation", "section": "C — Envolvente", "label": "Isolamento da cobertura / desvão", "unit": "", "type": "enum", "options": ["aucune", "présente", "inconnue"], "importance": "high"},
    {"path": "plancher_bas.isolation", "section": "C — Envolvente", "label": "Isolamento do pavimento inferior", "unit": "", "type": "enum", "options": ["aucune", "présente", "inconnue"], "importance": "high"},
    {"path": "parois.humidite", "section": "C — Envolvente", "label": "Sinais de humidade / infiltração", "unit": "", "type": "enum", "options": ["non", "oui", "inconnu"], "importance": "high"},
    # D — Menuiseries
    {"path": "menuiseries.nombre", "section": "D — Menuiseries", "label": "Número de janelas/portas-janelas", "unit": "u", "type": "number", "importance": "high"},
    {"path": "menuiseries.vitrage", "section": "D — Menuiseries", "label": "Tipo de vidro", "unit": "", "type": "enum", "options": ["simple", "double", "triple", "inconnu"], "importance": "high"},
    {"path": "menuiseries.materiau", "section": "D — Menuiseries", "label": "Material dos caixilhos", "unit": "", "type": "enum", "options": ["bois", "PVC", "alu", "mixte", "inconnu"], "importance": "med"},
    # E — Chauffage & ECS
    {"path": "chauffage.energie", "section": "E — Aquecimento / AQS", "label": "Energia de aquecimento", "unit": "", "type": "enum", "options": ["gaz", "fioul", "électricité", "bois", "rede urbana de calor", "PAC", "inconnu"], "importance": "high"},
    {"path": "chauffage.type", "section": "E — Aquecimento / AQS", "label": "Gerador", "unit": "", "type": "text", "importance": "med"},
    {"path": "chauffage.annee", "section": "E — Aquecimento / AQS", "label": "Ano do gerador", "unit": "", "type": "number", "importance": "med"},
    {"path": "ecs.production", "section": "E — Aquecimento / AQS", "label": "Production eau chaude", "unit": "", "type": "text", "importance": "med"},
    # F — Ventilation
    {"path": "ventilation.type", "section": "F — Ventilation", "label": "Ventilation", "unit": "", "type": "enum", "options": ["naturelle", "VMC simple flux", "VMC double flux", "inconnue"], "importance": "high"},
    # H — Objectifs
    {"path": "objectifs.budget_eur", "section": "H — Objectifs", "label": "Orçamento de obras previsto", "unit": "€", "type": "number", "importance": "high"},
    {"path": "objectifs.priorite", "section": "H — Objectifs", "label": "Prioridade", "unit": "", "type": "enum", "options": ["économies", "confort", "carbone", "valor do imóvel"], "importance": "med"},
    {"path": "objectifs.phasage", "section": "H — Objectifs", "label": "Reabilitação", "unit": "", "type": "enum", "options": ["en une fois", "par étapes"], "importance": "med"},
]
_FIELD_BY_PATH = {f["path"]: f for f in QUESTIONNAIRE}
_VALID_STATUS = {"documenté", "mesuré", "déclaré", "hypothèse", "inconnu", "contradictoire"}


# ---------------------------------------------------------------------------
# Catalogue de mesures de rénovation (déterministe)
# ---------------------------------------------------------------------------
# metre: surface_toiture / surface_murs / surface_plancher_bas / menuiseries / forfait
# poste: clé corps_etat réutilisée pour le chiffrage, ou None → « à chiffrer »
RENO_CATALOGUE = [
    {"code": "ISO_COMBLES", "lot": "LOTE 01 — Isolamento da cobertura", "label": "Isolamento do desvão / cobertura", "component": "toiture", "metre": "surface_toiture", "poste": "isolation", "induced": [], "controls": ["Continuidade do isolamento", "Ventilação da cobertura", "Barreira pára-vapor adequada"]},
    {"code": "ITE", "lot": "LOTE 02 — Isolamento das paredes pelo exterior", "label": "Isolamento térmico pelo exterior (ETICS / capoto)", "component": "murs", "metre": "surface_murs", "poste": None, "induced": ["Andaime", "Tratamento das pontes térmicas", "Reposição dos peitoris"], "controls": ["Support", "Fixations", "Continuidade", "Fichas técnicas dos produtos"]},
    {"code": "Isolamento pelo interior", "lot": "LOTE 02 — Isolamento das paredes pelo interior", "label": "Isolamento térmico pelo interior", "component": "murs", "metre": "surface_murs", "poste": "placo", "induced": ["Tratamento das ombreiras", "Reposição das redes", "Ponts thermiques"], "controls": ["Risco de condensação", "Continuidade", "Perda de área"]},
    {"code": "ISO_PB", "lot": "LOTE 03 — Isolamento do pavimento inferior", "label": "Isolamento do pavimento térreo", "component": "plancher_bas", "metre": "surface_plancher_bas", "poste": "isolation", "induced": [], "controls": ["Acessibilidade", "Continuidade"]},
    {"code": "MENUISERIES", "lot": "LOT 04 — Menuiseries", "label": "Substituição da caixilharia exterior", "component": "menuiseries", "metre": "menuiseries", "poste": None, "induced": ["Remoção", "Calfeutrement", "Tableaux", "Protections solaires"], "controls": ["Uw/Sw", "Estanquidade das juntas", "Coordination ventilation"]},
    {"code": "VMC", "lot": "LOT 05 — Ventilation", "label": "Ventilação mecânica (simples ou de duplo fluxo)", "component": "ventilation", "metre": "forfait", "poste": None, "induced": ["Redes de condutas", "Entradas de ar"], "controls": ["Caudais", "Manutenção", "Renouvellement d'air"]},
    {"code": "ETANCH_AIR", "lot": "LOTE 05 — Estanquidade ao ar", "label": "Tratamento da estanquidade ao ar", "component": "enveloppe", "metre": "forfait", "poste": None, "induced": [], "controls": ["Ensaio de permeabilidade ao ar", "Aparelhos de combustão"]},
    {"code": "CHAUFFAGE_PAC", "lot": "LOT 06 — Chauffage", "label": "Bomba de calor (estudo necessário)", "component": "chauffage", "metre": "forfait", "poste": None, "induced": ["Adaptação dos emissores", "Eletricidade"], "controls": ["Perdas térmicas após obras", "Regimes de temperatura da água", "Acoustique", "Implantation"]},
    {"code": "REGULATION", "lot": "LOTE 06 — Regulação", "label": "Regulação / termóstatos programáveis", "component": "chauffage", "metre": "forfait", "poste": None, "induced": [], "controls": ["Zonage", "Programmation"]},
    {"code": "ECS", "lot": "LOTE 07 — Água quente sanitária", "label": "Produção de AQS eficiente (ex. termoacumulador com bomba de calor)", "component": "ecs", "metre": "forfait", "poste": None, "induced": [], "controls": ["Volume", "Emplacement", "Calorifugeage"]},
]
_CAT_BY_CODE = {m["code"]: m for m in RENO_CATALOGUE}

# Prix forfaitaires indicatifs (HYPOTHÈSE à confirmer par une source locale datée).
_HYPO_FORFAIT = {
    "VMC": 2500.0, "ETANCH_AIR": 2000.0, "CHAUFFAGE_PAC": 12000.0,
    "REGULATION": 900.0, "ECS": 3500.0,
}
_HYPO_UNIT = {"ITE": 160.0, "MENUISERIES": 650.0}  # €/m² murs ITE, €/menuiserie


# ---------------------------------------------------------------------------
# Modèles d'entrée
# ---------------------------------------------------------------------------
class RenoProjectIn(BaseModel):
    title: str = Field(default="", max_length=160)
    country: str = Field(default="PT", max_length=4)
    bien_type: str = Field(default="maison", max_length=20)


class EvidenceIn(BaseModel):
    path: str
    value: object | None = None
    status: str = "déclaré"
    source: str = "saisie"


class InputsPatch(BaseModel):
    fields: list[EvidenceIn] = Field(default_factory=list)


class ScenariosIn(BaseModel):
    pass


class AidesIn(BaseModel):
    """Situation ménage pour la simulation des aides (Mes Aides Réno)."""
    revenu: int | None = None                 # revenu fiscal de référence (€)
    personnes: int | None = None              # nb de personnes du ménage
    commune_insee: str | None = None          # code INSEE (sinon déduit du code postal projet)
    proprietaire_occupant: bool = True
    residence_principale: bool = True
    dpe_actuel: str | None = None             # lettre A..G (sinon celle du projet)
    dpe_vise: str | None = None               # lettre A..G
    parcours: str = "reabilitação energética"
    gain_energetique_pct: int | None = 40     # gain projeté (parcours accompagné)
    scenario_key: str | None = None           # pour le reste à charge indicatif
    travaux_ht_override: float | None = None  # montant imposé (ex. coût d'un scénario d'audit ADEME)
    label_override: str | None = None         # libellé affiché (ex. « Audit — étape finale »)


class ImportDpeNumberIn(BaseModel):
    numero_dpe: str = Field(min_length=6, max_length=20)


class AuditToDevisIn(BaseModel):
    audit_index: int = 0
    step_index: int = Field(ge=0)


class GesteToDevisIn(BaseModel):
    geste_code: str
    value: float | None = None
    mpr: float | None = None
    cee: float | None = None
    price_ht: float | None = None   # prix estimé des travaux (pour le reste à charge)


def _owned(project: dict | None):
    if not project:
        raise HTTPException(404, "Projeto não encontrado")
    return project


async def _get_project(project_id: str, user_id: str) -> dict:
    p = await db.reno_projects.find_one({"project_id": project_id, "user_id": user_id}, {"_id": 0})
    return _owned(p)


def _evidence(value, status="déclaré", source="saisie", unit=""):
    return {"value": value, "unit": unit, "status": status, "source": source, "captured_at": _now()}


# ---------------------------------------------------------------------------
# CRUD projet
# ---------------------------------------------------------------------------
@router.post("/projects")
async def create_project(body: RenoProjectIn, user=Depends(current_user)) -> dict:
    pid = "reno_" + secrets.token_hex(6)
    doc = {
        "project_id": pid, "user_id": user["user_id"],
        "title": (body.title or "Projeto de remodelação").strip()[:160],
        "country": (body.country or "PT").upper()[:4],
        "project_type": "renovation_existant",
        "status": "collecte",
        "inputs": {"bien.type": _evidence(body.bien_type, status="déclaré")},
        "documents": [], "scenarios": [],
        "created_at": _now(), "updated_at": _now(),
    }
    await db.reno_projects.insert_one(dict(doc))
    doc.pop("_id", None)
    return doc


@router.get("/projects")
async def list_projects(user=Depends(current_user)) -> dict:
    items = await db.reno_projects.find(
        {"user_id": user["user_id"]}, {"_id": 0, "project_id": 1, "title": 1, "status": 1,
                                       "created_at": 1, "updated_at": 1}).sort("updated_at", -1).to_list(200)
    return {"projects": items}


@router.get("/questionnaire")
async def get_questionnaire(user=Depends(current_user)) -> dict:
    return {"fields": QUESTIONNAIRE}


@router.get("/catalogue")
async def get_catalogue(user=Depends(current_user)) -> dict:
    return {"measures": RENO_CATALOGUE}


@router.get("/projects/{project_id}")
async def get_project(project_id: str, user=Depends(current_user)) -> dict:
    return await _get_project(project_id, user["user_id"])


@router.patch("/projects/{project_id}/inputs")
async def patch_inputs(project_id: str, body: InputsPatch, user=Depends(current_user)) -> dict:
    p = await _get_project(project_id, user["user_id"])
    inputs = p.get("inputs") or {}
    for f in body.fields:
        if f.path not in _FIELD_BY_PATH:
            continue
        status = f.status if f.status in _VALID_STATUS else "déclaré"
        if f.value in (None, ""):
            status = "inconnu"
        inputs[f.path] = _evidence(f.value if f.value != "" else None, status=status,
                                    source=f.source, unit=_FIELD_BY_PATH[f.path].get("unit", ""))
    await db.reno_projects.update_one(
        {"project_id": project_id, "user_id": user["user_id"]},
        {"$set": {"inputs": inputs, "updated_at": _now()}})
    return {"ok": True, "inputs": inputs}


@router.get("/projects/{project_id}/missing-data")
async def missing_data(project_id: str, user=Depends(current_user)) -> dict:
    p = await _get_project(project_id, user["user_id"])
    inputs = p.get("inputs") or {}
    missing, contradictions = [], []
    for f in QUESTIONNAIRE:
        ev = inputs.get(f["path"])
        known = ev and ev.get("value") not in (None, "") and ev.get("status") != "inconnu"
        if not known:
            missing.append({"path": f["path"], "label": f["label"], "section": f["section"],
                            "importance": f["importance"]})
        if ev and ev.get("status") == "contradictoire":
            contradictions.append({"path": f["path"], "label": f["label"]})
    # cohérence : surface vitrée > surface murs
    sv = _num(inputs.get("geometrie.surface_vitree_m2"))
    sm = _num(inputs.get("geometrie.surface_murs_m2"))
    if sv and sm and sv > sm:
        contradictions.append({"path": "geometrie.surface_vitree_m2",
                               "label": "Área envidraçada superior à área de paredes — a verificar"})
    high = [m for m in missing if m["importance"] == "high"]
    coverage = round(100 * (len(QUESTIONNAIRE) - len(missing)) / len(QUESTIONNAIRE)) if QUESTIONNAIRE else 0
    return {"missing": missing, "missing_high_priority": high,
            "contradictions": contradictions, "coverage_pct": coverage}


def _num(ev):
    try:
        if not ev:
            return None
        v = ev.get("value")
        if v in (None, ""):
            return None
        return float(str(v).replace(",", "."))
    except (TypeError, ValueError):
        return None


def _val(inputs, path):
    ev = inputs.get(path)
    return ev.get("value") if ev else None


# ---------------------------------------------------------------------------
# Niveau A — analyse qualitative (JAMAIS de classe/kWh)
# ---------------------------------------------------------------------------
def _assess_component(label, iso_value, period_old, extra_reason=""):
    """Renvoie (assessment, reason) de façon déterministe, sans chiffre énergétique."""
    iso = (iso_value or "").lower()
    if iso in ("inconnue", "inconnu", "", None):
        return "a verificar", f'Isolamento {label} não preenchida — a levantar no local.'
    if iso in ("aucune",):
        return "provavelmente com perdas", f'Ausência de isolamento declarada para {label}.'
    return "correto (declarado)", f'Isolamento {label} declarado presente — a confirmar por comprovativo.'


@router.post("/projects/{project_id}/analyze-baseline")
async def analyze_baseline(project_id: str, user=Depends(current_user)) -> dict:
    p = await _get_project(project_id, user["user_id"])
    inputs = p.get("inputs") or {}
    period = (_val(inputs, "bien.periode_construction") or "")
    period_old = period in ("avant 1948", "1948-1974", "1975-1988")
    posts = []
    a, r = _assess_component("as paredes", _val(inputs, "murs.isolation"), period_old)
    posts.append({"component": "Paredes", "assessment": a, "reason": r, "data_needed": ["murs.isolation", "murs.materiau"]})
    a, r = _assess_component("a cobertura", _val(inputs, "toiture.isolation"), period_old)
    posts.append({"component": "Cobertura / desvão", "assessment": a, "reason": r, "data_needed": ["toiture.isolation"]})
    a, r = _assess_component("o pavimento inferior", _val(inputs, "plancher_bas.isolation"), period_old)
    posts.append({"component": "Pavimento inferior", "assessment": a, "reason": r, "data_needed": ["plancher_bas.isolation"]})
    vit = (_val(inputs, "menuiseries.vitrage") or "").lower()
    if vit in ("simple",):
        posts.append({"component": "Menuiseries", "assessment": "provavelmente com perdas", "reason": "Vidro simples declarado.", "data_needed": ["menuiseries.vitrage"]})
    elif vit in ("", "inconnu"):
        posts.append({"component": "Menuiseries", "assessment": "a verificar", "reason": "Tipo de vidro não preenchido.", "data_needed": ["menuiseries.vitrage"]})
    else:
        posts.append({"component": "Menuiseries", "assessment": "correto (declarado)", "reason": f'Vitrage {vit} declarado — Uw a confirmar.', "data_needed": ["menuiseries.vitrage"]})
    vent = (_val(inputs, "ventilation.type") or "").lower()
    posts.append({"component": "Ventilation", "assessment": "a verificar" if vent in ("", "inconnue") else "correto (declarado)",
                  "reason": "Tipo de ventilação não preenchido." if vent in ("", "inconnue") else f"Ventilation {vent} déclarée.",
                  "data_needed": ["ventilation.type"]})
    energie = (_val(inputs, "chauffage.energie") or "").lower()
    posts.append({"component": "Aquecimento / AQS",
                  "assessment": "a verificar" if energie in ("", "inconnu") else "a peritar",
                  "reason": "Energia de aquecimento não preenchida." if energie in ("", "inconnu") else f'Energia {energie} declarada — rendimento do gerador a verificar.',
                  "data_needed": ["chauffage.energie", "chauffage.annee"]})

    energy = {
        "status": "moteur_non_configure",
        "class_simulee": None, "kwh_ep_m2_an": None, "ges": None,
        "message": "Nenhum motor de cálculo certificado está ligado. Nenhuma classe energética nem consumo em kWh é calculado. Esta análise é qualitativa (Nível A) e não substitui um certificado energético (SCE) nem uma auditoria regulamentar.",
    }
    md = await missing_data(project_id, user)
    baseline = {"posts": posts, "energy": energy, "coverage_pct": md["coverage_pct"],
                "missing_high_priority": md["missing_high_priority"], "analyzed_at": _now()}
    await db.reno_projects.update_one(
        {"project_id": project_id, "user_id": user["user_id"]},
        {"$set": {"baseline": baseline, "status": "analyse", "updated_at": _now()}})
    return baseline


# ---------------------------------------------------------------------------
# Scénarios P1/P2/P3 + métré + chiffrage (corps d'état)
# ---------------------------------------------------------------------------
_PARCOURS = {
    "P1": {"name": "Prioridades (orçamento)", "desc": "Melhor ganho realizável dentro do orçamento declarado, pré-requisitos essenciais.",
           "measures": ["ISO_COMBLES", "REGULATION", "ETANCH_AIR", "VMC"]},
    "P2": {"name": "Equilíbrio", "desc": "Combinação com o melhor compromisso custo / ganho / exequibilidade.",
           "measures": ["ISO_COMBLES", "MENUISERIES", "VMC", "REGULATION"]},
    "P3": {"name": "Renovação completa", "desc": "Objetivo de desempenho ambicioso (de uma só vez ou por etapas).",
           "measures": ["ISO_COMBLES", "ITE", "ISO_PB", "MENUISERIES", "VMC", "CHAUFFAGE_PAC", "ECS"]},
}


def _metre_for(measure, inputs):
    """Retourne (quantity, unit, status) pour une mesure, à partir de la géométrie saisie."""
    basis = measure["metre"]
    if basis == "forfait":
        return 1, "forfait", "hypothèse"
    if basis == "menuiseries":
        n = _num(inputs.get("menuiseries.nombre"))
        return (n, "u", "déclaré") if n else (None, "u", "a confirmar")
    path = {"surface_toiture": "geometrie.surface_toiture_m2",
            "surface_murs": "geometrie.surface_murs_m2",
            "surface_plancher_bas": "geometrie.surface_plancher_bas_m2"}[basis]
    q = _num(inputs.get(path))
    return (q, "m²", "déclaré") if q else (None, "m²", "a confirmar")


def _chiffrage_for(measure, qty):
    """Chiffrage déterministe : corps_etat si poste connu, sinon hypothèse forfait/unitaire ou « à chiffrer »."""
    if qty is None:
        return {"total_ht": None, "status": "quantidade a confirmar", "source": None, "lines": []}
    poste = measure.get("poste")
    if poste and poste in corps_etat.POSTES:
        est = corps_etat.estimate(poste, qty, {"margin_pct": 0})
        return {"total_ht": round(est["totals"]["ht"], 2), "status": "com preço (biblioteca por especialidade)",
                "source": f"corps_etat:{poste}", "lines": est["lines"], "poste": poste}
    if measure["code"] in _HYPO_UNIT:
        pu = _HYPO_UNIT[measure["code"]]
        return {"total_ht": round(pu * qty, 2), "status": "hipótese (PU indicativo a confirmar)",
                "source": "hypothèse", "pu": pu, "lines": []}
    if measure["code"] in _HYPO_FORFAIT:
        return {"total_ht": round(_HYPO_FORFAIT[measure["code"]] * (qty or 1), 2),
                "status": "hipótese (valor global indicativo a confirmar)", "source": "hypothèse", "lines": []}
    return {"total_ht": None, "status": "a orçamentar", "source": None, "lines": []}


def _build_work_item(measure, inputs):
    qty, unit, qstatus = _metre_for(measure, inputs)
    chi = _chiffrage_for(measure, qty)
    return {
        "code": measure["code"], "lot": measure["lot"], "label": measure["label"],
        "component": measure["component"],
        "metre": {"quantity": qty, "unit": unit, "status": qstatus},
        "chiffrage": chi,
        "induced": measure.get("induced", []),
        "controls": measure.get("controls", []),
        "descriptif": _descriptif(measure, qty, unit, qstatus, chi),
    }


def _descriptif(measure, qty, unit, qstatus, chi):
    qty_txt = f"{qty:.2f} {unit}" if qty is not None else f'a confirmar ({unit})'
    prix_txt = (f"{chi['total_ht']:.2f} € HT ({chi['status']})" if chi.get("total_ht") is not None
                else chi["status"])
    return {
        "localisation": "A precisar na visita",
        "constat": "Estado e composição existentes a levantar no local (dado não verificado).",
        "objectif": f"{measure['label']} — reduzir as perdas térmicas e tratar as interfaces acessíveis.",
        "performance_cible": "Definida após simulação energética (motor não configurado) e controlo das exigências aplicáveis — a confirmar.",
        "metre": f'{qty_txt}; complementos (ombreiras, peitoris, pontes térmicas) a levantar separadamente.',
        "mise_en_oeuvre": "Preparação do suporte, remoção se necessário, fornecimento e aplicação, acabamentos.",
        "interfaces": ", ".join(measure.get("induced", [])) or "A coordenar com os lotes vizinhos.",
        "prerequis_reserves": "Exequibilidade, licenças e composição a confirmar. Referências normativas a verificar (não geradas).",
        "prix": prix_txt,
        "controles": ", ".join(measure.get("controls", [])),
    }


@router.post("/projects/{project_id}/scenarios")
async def generate_scenarios(project_id: str, user=Depends(current_user)) -> dict:
    p = await _get_project(project_id, user["user_id"])
    inputs = p.get("inputs") or {}
    budget = _num(inputs.get("objectifs.budget_eur"))
    scenarios = []
    for key, spec in _PARCOURS.items():
        items = [_build_work_item(_CAT_BY_CODE[c], inputs) for c in spec["measures"] if c in _CAT_BY_CODE]
        chiffrable = [it for it in items if it["chiffrage"].get("total_ht") is not None]
        total = round(sum(it["chiffrage"]["total_ht"] for it in chiffrable), 2)
        a_chiffrer = [it["label"] for it in items if it["chiffrage"].get("total_ht") is None]
        budget_flag = None
        if budget is not None and total > 0:
            budget_flag = "dentro do orçamento" if total <= budget else "acima do orçamento declarado"
        scenarios.append({
            "scenario_id": f"{project_id}:{key}", "key": key, "name": spec["name"],
            "description": spec["desc"], "work_items": items,
            "total_ht_chiffrable": total, "a_chiffrer": a_chiffrer,
            "budget_flag": budget_flag,
            "energy_gain": {"status": "non_calcule",
                            "message": "Ganhos energéticos não calculados: motor de cálculo não configurado. As medidas interagem — nenhuma soma de percentagens."},
        })
    await db.reno_projects.update_one(
        {"project_id": project_id, "user_id": user["user_id"]},
        {"$set": {"scenarios": scenarios, "status": "scenarios", "updated_at": _now()}})
    return {"scenarios": scenarios}


@router.get("/projects/{project_id}/scenarios/{key}/work-items")
async def get_work_items(project_id: str, key: str, user=Depends(current_user)) -> dict:
    p = await _get_project(project_id, user["user_id"])
    sc = next((s for s in (p.get("scenarios") or []) if s["key"] == key), None)
    if not sc:
        raise HTTPException(404, "Cenário não encontrado — gere primeiro os cenários")
    return sc


@router.post("/projects/{project_id}/scenarios/{key}/create-estimate")
async def create_estimate(project_id: str, key: str, user=Depends(current_user)) -> dict:
    """Crée un devis ConstruPilot à partir d'un scénario (réutilise le moteur Corps d'état
    et l'éditeur de devis existant). Les postes sans prix sortent en « à chiffrer » (0 €)."""
    p = await _get_project(project_id, user["user_id"])
    sc = next((s for s in (p.get("scenarios") or []) if s["key"] == key), None)
    if not sc:
        raise HTTPException(404, "Cenário não encontrado — gere primeiro os cenários")
    lines = []
    for it in sc["work_items"]:
        qty = it["metre"]["quantity"]
        lines.append(docs_mod.DocLine(
            kind="section", title=f"{it['lot']} — {it['label']}"))
        chi = it["chiffrage"]
        pu = 0.0
        price_missing = True
        if chi.get("total_ht") is not None and qty:
            pu = round(chi["total_ht"] / qty, 2)
            price_missing = chi.get("source") == "hypothèse"
        lines.append(docs_mod.DocLine(
            kind="line", line_kind="ouvrage",
            designation=it["label"],
            description=it["descriptif"]["objectif"],
            unit=it["metre"]["unit"] if it["metre"]["unit"] != "forfait" else "u",
            qty=float(qty) if qty else 1,
            unit_price_ht=pu,
            price_estimated=(chi.get("source") == "hypothèse"),
            price_missing=price_missing and chi.get("total_ht") is None,
            quantity_missing=qty is None,
            price_reference_label=chi.get("status", ""),
        ))
    body = docs_mod.DocIn(doc_type="quote",
                          title=f"Reabilitação — {p.get('title', '')} — {sc['name']}",
                          lines=lines,
                          notes="Orçamento gerado a partir do RenoPilot (Etapa 1). As linhas «a orçamentar» e os preços indicativos (hipótese) devem ser confirmados por uma fonte local datada. Nenhum ganho energético é garantido.")
    created = await docs_mod.create_document(body, user)
    doc_id = created.get("doc_id") if isinstance(created, dict) else None
    return {"ok": True, "doc_id": doc_id, "scenario": key,
            "message": "Orçamento criado no editor ConstruPilot."}


@router.post("/projects/{project_id}/aides")
async def simulate_aides(project_id: str, body: AidesIn, user=Depends(current_user)) -> dict:
    """Simule les aides à la rénovation (MaPrimeRénov' / CEE / Éco-PTZ…) via l'API
    officielle « Mes Aides Réno » (Publicodes). Déterministe, montants INDICATIFS."""
    p = await _get_project(project_id, user["user_id"])
    inputs = p.get("inputs") or {}

    # Commune INSEE : fournie > INSEE officiel du DPE (exact) > déduite du code postal.
    commune = (body.commune_insee or "").strip()
    commune_options: list[dict] = []
    if not commune:
        commune = str(_val(inputs, "localisation.commune_insee") or "").strip()
    if not commune:
        cp = _val(inputs, "localisation.code_postal")
        if cp:
            commune_options = await aides_reno.insee_from_cp(str(cp))
            if len(commune_options) == 1:
                commune = commune_options[0]["code"]
    if not commune:
        return {"ok": False, "need_commune": True, "commune_options": commune_options,
                "message": "Indique o concelho para simular os apoios."}

    bien_type = aides_reno.TYPE_MAP.get(str(_val(inputs, "bien.type") or "maison"), "maison")
    periode = aides_reno.PERIODE_MAP.get(
        str(_val(inputs, "bien.periode_construction") or ""), "pelo menos 15 anos")
    surface = _num(inputs.get("geometrie.surface_habitable_m2"))

    dpe_actuel = (body.dpe_actuel or "").upper().strip()
    dpe_vise = (body.dpe_vise or "").upper().strip()

    situation: dict = {
        "ménage.commune": commune,
        "logement.commune": commune,
        "logement.type": bien_type,
        "logement.période de construction": periode,
        "logement.propriétaire occupant": "oui" if body.proprietaire_occupant else "non",
        "logement.résidence principale propriétaire": "oui" if body.residence_principale else "non",
        "vous.propriétaire.statut": "propriétaire" if body.proprietaire_occupant else "não proprietário",
        "parcours d'aide": body.parcours,
    }
    if body.revenu is not None:
        situation["ménage.revenu"] = int(body.revenu)
    if body.personnes is not None:
        situation["ménage.personnes"] = int(body.personnes)
    if surface:
        situation["logement.surface"] = int(round(surface))
    if dpe_actuel in aides_reno.DPE_LETTER_TO_NUM:
        situation["DPE.actuel"] = aides_reno.DPE_LETTER_TO_NUM[dpe_actuel]
    if dpe_vise in aides_reno.DPE_LETTER_TO_NUM:
        situation["projet.DPE visé"] = aides_reno.DPE_LETTER_TO_NUM[dpe_vise]
    if body.gain_energetique_pct:
        situation["projet.gain énergétique"] = f"{int(body.gain_energetique_pct)} %"

    # Montant de travaux : override explicite (scénario d'audit ADEME) sinon total du scénario RenoPilot.
    travaux_ht = None
    scenario_name = None
    if body.travaux_ht_override is not None:
        travaux_ht = float(body.travaux_ht_override)
        scenario_name = body.label_override or "Montante da auditoria ADEME"
    elif body.scenario_key:
        sc = next((s for s in (p.get("scenarios") or []) if s["key"] == body.scenario_key), None)
        if sc:
            travaux_ht = sc.get("total_ht_chiffrable") or None
            scenario_name = sc.get("name")

    try:
        result = await aides_reno.estimate_aides(situation, travaux_ht=travaux_ht)
    except Exception as exc:
        raise HTTPException(502, f'API Mes Aides Réno indisponível: {type(exc).__name__}')

    result.update({"ok": True, "commune": commune,
                   "commune_options": commune_options,
                   "scenario_key": body.scenario_key, "scenario_name": scenario_name})

    await db.reno_projects.update_one(
        {"project_id": project_id, "user_id": user["user_id"]},
        {"$set": {"aides": result, "updated_at": _now()}})
    return result


class GesteItemIn(BaseModel):
    code: str
    value: float | None = None


class GestesAidesIn(BaseModel):
    revenu: int | None = None
    personnes: int | None = None
    commune_insee: str | None = None
    proprietaire_occupant: bool = True
    residence_principale: bool = True
    gestes: list[GesteItemIn] = []


@router.get("/aides/gestes-catalogue")
async def gestes_catalogue(user=Depends(current_user)) -> dict:
    return {"gestes": aides_reno.GESTE_CATALOGUE}


@router.post("/projects/{project_id}/aides-gestes")
async def simulate_aides_gestes(project_id: str, body: GestesAidesIn, user=Depends(current_user)) -> dict:
    """Aides « par geste » (MaPrimeRénov' + CEE par poste) via l'API officielle Mes Aides Réno."""
    p = await _get_project(project_id, user["user_id"])
    inputs = p.get("inputs") or {}
    commune = (body.commune_insee or "").strip() or str(_val(inputs, "localisation.commune_insee") or "").strip()
    commune_options: list[dict] = []
    if not commune:
        cp = _val(inputs, "localisation.code_postal")
        if cp:
            commune_options = await aides_reno.insee_from_cp(str(cp))
            if len(commune_options) == 1:
                commune = commune_options[0]["code"]
    if not commune:
        return {"ok": False, "need_commune": True, "commune_options": commune_options,
                "message": "Indique o concelho para simular os apoios."}

    bien_type = aides_reno.TYPE_MAP.get(str(_val(inputs, "bien.type") or "maison"), "maison")
    periode = aides_reno.PERIODE_MAP.get(
        str(_val(inputs, "bien.periode_construction") or ""), "pelo menos 15 anos")
    situation = {
        "ménage.commune": commune, "logement.commune": commune,
        "logement.type": bien_type, "logement.période de construction": periode,
        "logement.propriétaire occupant": "oui" if body.proprietaire_occupant else "non",
        "logement.résidence principale propriétaire": "oui" if body.residence_principale else "non",
        "vous.propriétaire.statut": "propriétaire" if body.proprietaire_occupant else "não proprietário",
        "parcours d'aide": "gestes",
    }
    if body.revenu is not None:
        situation["ménage.revenu"] = int(body.revenu)
    if body.personnes is not None:
        situation["ménage.personnes"] = int(body.personnes)

    items = [{"code": g.code, "value": g.value} for g in body.gestes]
    try:
        result = await aides_reno.estimate_gestes(situation, items)
    except Exception as exc:
        raise HTTPException(502, f'API Mes Aides Réno indisponível: {type(exc).__name__}')
    result.update({"ok": True, "commune": commune, "commune_options": commune_options})
    await db.reno_projects.update_one(
        {"project_id": project_id, "user_id": user["user_id"]},
        {"$set": {"aides_gestes": result, "updated_at": _now()}})
    return result


# Mapping période ADEME ("2013-2021"…) → options du questionnaire RenoPilot.
def _map_periode_ademe(periode: str | None) -> str | None:
    if not periode:
        return None
    import re
    pl = str(periode).lower()
    if "avant" in pl:
        return "avant 1948"
    m = re.search(r"(\d{4})", str(periode))
    if not m:
        return None
    y = int(m.group(1))
    if y < 1948:
        return "avant 1948"
    if y <= 1974:
        return "1948-1974"
    if y <= 1988:
        return "1975-1988"
    if y <= 2000:
        return "1989-2000"
    if y <= 2012:
        return "2001-2012"
    return "après 2012"


def _map_energie_ademe(energie: str | None) -> str | None:
    if not energie:
        return None
    e = energie.lower()
    if "gaz" in e:
        return "gaz"
    if "fioul" in e or "fuel" in e:
        return "fioul"
    if "électr" in e or "electr" in e:
        return "électricité"
    if "bois" in e or "granul" in e or "pellet" in e:
        return "bois"
    if "réseau" in e or "reseau" in e or "urbain" in e:
        return "rede urbana de calor"
    if "pac" in e or "pompe" in e:
        return "PAC"
    return None


DPE_NUMBER_RE = __import__("re").compile(r"\b\d{4}[A-Z]\d{7}[A-Z]\b")


async def _apply_ademe_import(project_id: str, user_id: str, numero: str, base_inputs: dict) -> dict:
    """Récupère le DPE officiel ADEME + scénarios d'audit, préremplit les inputs (statut
    « documenté »), persiste. Renvoie {dpe, audits} ou lève 404/502."""
    numero = (numero or "").strip().upper()
    try:
        dpe = await ademe_dpe.fetch_dpe(numero)
    except Exception as exc:
        raise HTTPException(502, f'API ADEME indisponível: {type(exc).__name__}')
    if not dpe:
        raise HTTPException(404, "Nenhum DPE encontrado para este número nos dados abertos da ADEME. Verifique o número (13 caracteres, no topo do PDF).")
    try:
        audits = await ademe_dpe.fetch_audit_scenarios(numero)
    except Exception:
        audits = []

    inputs = dict(base_inputs or {})

    def _doc(path, value, unit=""):
        if value not in (None, ""):
            inputs[path] = _evidence(value, status="documenté", source="DPE ADEME", unit=unit)

    _doc("bien.type", dpe.get("type_batiment"))
    _doc("bien.periode_construction", _map_periode_ademe(dpe.get("periode_construction")))
    _doc("localisation.code_postal", dpe.get("code_postal"))
    _doc("localisation.commune_insee", dpe.get("code_insee"))
    _doc("geometrie.surface_habitable_m2", dpe.get("surface_m2"), unit="m²")
    _doc("geometrie.hauteur_sous_plafond_m", dpe.get("hauteur_sous_plafond"), unit="m")
    _doc("chauffage.energie", _map_energie_ademe(dpe.get("chauffage_energie")))
    _doc("ecs.production", dpe.get("ecs_generateur"))
    if dpe.get("ventilation"):
        _doc("ventilation.type", dpe.get("ventilation"))

    await db.reno_projects.update_one(
        {"project_id": project_id, "user_id": user_id},
        {"$set": {"inputs": inputs, "ademe_dpe": dpe, "ademe_audits": audits,
                  "updated_at": _now()}})
    return {"dpe": dpe, "audits": audits}


@router.post("/projects/{project_id}/import-dpe-number")
async def import_dpe_number(project_id: str, body: ImportDpeNumberIn, user=Depends(current_user)) -> dict:
    """Récupère le DPE officiel (open data ADEME) et ses scénarios d'audit par n° de DPE,
    préremplit l'état actuel du projet (données « documentées », source officielle)."""
    p = await _get_project(project_id, user["user_id"])
    numero = body.numero_dpe.strip().upper()
    res = await _apply_ademe_import(project_id, user["user_id"], numero, p.get("inputs") or {})
    return {"ok": True, "dpe": res["dpe"], "audits": res["audits"], "prefilled": True,
            "message": f'Certificado energético oficial {numero} importado — estado atual pré-preenchido.'}


@router.post("/projects/{project_id}/import-dpe-immeuble")
async def import_dpe_immeuble(project_id: str, user=Depends(current_user)) -> dict:
    """Récupère le DPE de l'IMMEUBLE associé (parties communes) via le n° de DPE immeuble
    rattaché au logement — sans jamais moyenner les étiquettes logement/immeuble."""
    p = await _get_project(project_id, user["user_id"])
    numero = (p.get("ademe_dpe") or {}).get("numero_dpe_immeuble")
    if not numero:
        raise HTTPException(404, "Nenhum certificado energético de edifício associado a esta habitação.")
    try:
        dpe = await ademe_dpe.fetch_dpe(numero)
    except Exception as exc:
        raise HTTPException(502, f'API ADEME indisponível: {type(exc).__name__}')
    if not dpe:
        raise HTTPException(404, "Certificado de edifício não encontrado nos dados abertos da ADEME.")
    await db.reno_projects.update_one(
        {"project_id": project_id, "user_id": user["user_id"]},
        {"$set": {"ademe_dpe_immeuble": dpe, "updated_at": _now()}})
    return {"ok": True, "dpe_immeuble": dpe,
            "message": f'Certificado energético do edifício {numero} importado (partes comuns).'}


@router.post("/projects/{project_id}/audit-to-devis")
async def audit_to_devis(project_id: str, body: AuditToDevisIn, user=Depends(current_user)) -> dict:
    """Transforme un scénario d'audit officiel ADEME en devis ConstruPilot chiffrable.
    Les travaux de l'audit deviennent des postes « à chiffrer » ; le coût ADEME est un
    repère indicatif (jamais recalculé ni imposé comme prix)."""
    import re
    p = await _get_project(project_id, user["user_id"])
    audits = p.get("ademe_audits") or []
    if body.audit_index >= len(audits):
        raise HTTPException(404, "Auditoria não encontrada — importe primeiro um certificado energético com auditoria.")
    audit = audits[body.audit_index]
    steps = audit.get("steps") or []
    if body.step_index >= len(steps):
        raise HTTPException(404, "Etapa de auditoria não encontrada.")
    step = steps[body.step_index]

    dpe_initial = ((p.get("ademe_dpe") or {}).get("etiquette_energie")
                   or next((s.get("etiquette_energie") for s in steps
                            if "initial" in (s.get("etape") or "").lower()), None) or "?")
    travaux_text = step.get("travaux") or ""
    items = [t.strip() for t in re.split(r"[;,]", travaux_text) if t.strip()]
    if not items:
        items = [f"Obras de reabilitação — {step.get('etape') or 'cenário de auditoria'}"]

    lines = [docs_mod.DocLine(kind="section",
                              title=f"Obras — cenário de auditoria ADEME ({step.get('etape')})")]
    for it in items:
        lines.append(docs_mod.DocLine(
            kind="line", line_kind="ouvrage", designation=it,
            unit="u", qty=1, unit_price_ht=0.0,
            price_missing=True, quantity_missing=True, price_reference_label="a orçamentar"))

    cout = step.get("cout_travaux")
    etq = step.get("etiquette_energie")
    notes = (f"Orçamento gerado a partir de um cenário de auditoria energética OFICIAL ADEME (n.º DPE {(p.get('ademe_dpe') or {}).get('numero_dpe', '—')}, audit {audit.get('n_audit')}). Montante global INDICATIVO da auditoria: {int(cout)} € (custo de obras ADEME, não vinculativo). Classe energética pretendida: {etq}. Cada artigo deve ser orçamentado por uma fonte local datada; nenhum ganho energético é garantido.")
    doc_body = docs_mod.DocIn(
        doc_type="quote",
        title=f"Reabilitação (auditoria ADEME) — {step.get('etape')} — DPE {dpe_initial}→{etq}",
        lines=lines, notes=notes)
    created = await docs_mod.create_document(doc_body, user)
    doc_id = created.get("doc_id") if isinstance(created, dict) else None
    return {"ok": True, "doc_id": doc_id,
            "cout_audit_indicatif": cout, "etiquette_visee": etq,
            "message": "Orçamento criado a partir do cenário de auditoria — artigos a orçamentar no editor."}


@router.post("/projects/{project_id}/geste-to-devis")
async def geste_to_devis(project_id: str, body: GesteToDevisIn, user=Depends(current_user)) -> dict:
    """Transforme un geste chiffré (PAC, fenêtres, isolation…) en devis ConstruPilot :
    une ligne « à chiffrer » pour le poste + la mention de l'aide associée (MPR + CEE)."""
    p = await _get_project(project_id, user["user_id"])
    g = next((x for x in aides_reno.GESTE_CATALOGUE if x["code"] == body.geste_code), None)
    if not g:
        raise HTTPException(404, "Medida desconhecida.")
    unit = g.get("unit") or "u"
    qty = float(body.value) if body.value not in (None, "") else 1.0

    def _eur_int(n):
        try:
            return f"{int(round(float(n)))} €"
        except (TypeError, ValueError):
            return None

    mpr_txt = _eur_int(body.mpr)
    cee_txt = _eur_int(body.cee)
    aide_parts = []
    if mpr_txt:
        aide_parts.append(f"MaPrimeRénov': {mpr_txt}")
    if cee_txt:
        aide_parts.append(f'CEE: {cee_txt}')
    aide_line = " · ".join(aide_parts) if aide_parts else "Apoio a confirmar (API indisponível)"
    total_aide = (body.mpr or 0) + (body.cee or 0)
    total_txt = _eur_int(total_aide) if total_aide else None

    # Prix estimé → PU de la ligne (sinon « à chiffrer » à 0 €).
    price_ht = float(body.price_ht) if body.price_ht not in (None, "") else None
    pu = 0.0
    if price_ht is not None:
        pu = round(price_ht / qty, 2) if qty else round(price_ht, 2)
    reste = round(price_ht - total_aide, 2) if price_ht is not None else None
    reste_txt = _eur_int(reste) if reste is not None else None

    lines = [docs_mod.DocLine(kind="section", title=f"Reabilitação — {g['label']}")]
    lines.append(docs_mod.DocLine(
        kind="line", line_kind="ouvrage", designation=g["label"],
        description=f'Artigo orçamentado/estimado — apoio associado: {aide_line}',
        unit=unit if unit != "équipements" else "u",
        qty=qty, unit_price_ht=pu,
        price_missing=(price_ht is None), price_estimated=(price_ht is not None),
        quantity_missing=(body.value in (None, "")),
        price_reference_label="preço estimado (a confirmar)" if price_ht is not None else "a orçamentar"))
    reste_block = (f' · Preço estimado das obras: {_eur_int(price_ht)}' if price_ht is not None else "")
    reste_block += (f' · <b>Encargo final estimado: {reste_txt}</b>' if reste_txt is not None else "")
    lines.append(docs_mod.DocLine(
        kind="text",
        text=(f'Apoio associado (indicativo, não vinculativo) — {aide_line}'
              + (f' · Total de apoios: {total_txt}' if total_txt else "")
              + reste_block
              + ". Montantes provenientes do simulador oficial de apoios ou de um valor fixo oficial em alternativa; a confirmar junto de um técnico (ex. Fundo Ambiental).")))

    notes = (f"Orçamento gerado a partir de uma medida RenoPilot «{g['label']} ». "
             + (f'Preço estimado das obras: {_eur_int(price_ht)}; encargo final estimado após apoios: {reste_txt}. '
                if price_ht is not None else "O preço do artigo deve ser orçamentado por uma fonte local datada. ")
             + f'Apoio associado (indicativo): {aide_line}. Nenhum ganho energético garantido.')
    doc_body = docs_mod.DocIn(doc_type="quote",
                              title=f"Reabilitação — {g['label']}", lines=lines, notes=notes)
    created = await docs_mod.create_document(doc_body, user)
    doc_id = created.get("doc_id") if isinstance(created, dict) else None
    return {"ok": True, "doc_id": doc_id, "aide_associee": aide_line,
            "message": "Orçamento criado a partir da medida — artigo a orçamentar no editor."}



class DescribeIn(BaseModel):
    text: str = Field(default="", max_length=8000)


@router.post("/projects/{project_id}/describe")
async def describe_extract(project_id: str, body: DescribeIn, user=Depends(current_user)) -> dict:
    """Texte libre / dictée → propositions de champs (statut « déclaré », à CONFIRMER).
    N'enregistre rien : le front pré-remplit le formulaire pour validation par l'utilisateur."""
    await _get_project(project_id, user["user_id"])
    extracted = await ai_engine.renovation_extract(body.text or "", QUESTIONNAIRE)
    proposals = []
    for f in QUESTIONNAIRE:
        if f["path"] in extracted:
            proposals.append({"path": f["path"], "label": f["label"], "value": extracted[f["path"]],
                              "status": "déclaré", "source": "description"})
    return {"proposals": proposals, "count": len(proposals)}


@router.post("/projects/{project_id}/import-dpe")
async def import_dpe(project_id: str, file: UploadFile = File(...), user=Depends(current_user)) -> dict:
    """Importe un DPE/audit/plan (PDF ou XML), extrait le texte et pré-remplit le questionnaire
    (statut « documenté », provenance = fichier). Une classe DPE lue reste un DOCUMENT importé,
    jamais une simulation recalculée."""
    p = await _get_project(project_id, user["user_id"])
    raw = await file.read()
    if len(raw) > 25 * 1024 * 1024:
        raise HTTPException(413, "Ficheiro demasiado volumoso (máx. 25 MB)")
    fname = (file.filename or "document").strip()
    lower = fname.lower()
    text = ""
    try:
        if lower.endswith(".xml") or (raw[:200].lstrip().startswith(b"<")):
            text = raw.decode("utf-8", errors="ignore")
        elif lower.endswith(".pdf") or raw[:5] == b"%PDF-":
            import pymupdf
            doc = pymupdf.open(stream=raw, filetype="pdf")
            text = "\n".join(page.get_text() for page in doc[:12])
            doc.close()
        else:
            text = raw.decode("utf-8", errors="ignore")
    except Exception:
        text = ""
    # PDF scanné sans texte natif → OCR IA (déjà en place) pour récupérer le texte/numéro.
    if not text.strip() and (lower.endswith(".pdf") or raw[:5] == b"%PDF-") and gemini_ocr.available():
        try:
            ocr_data = await gemini_ocr.ocr(raw, "application/pdf", fname)
            text = "\n".join(p.get("text") or "" for p in ocr_data.get("pages") or [])
        except Exception:
            text = text
    if not text.strip():
        raise HTTPException(422, "Documento ilegível (formato não reconhecido). Introduza os dados manualmente.")

    # Détection automatique du n° de DPE (13 car.) → import officiel ADEME direct.
    ademe = None
    mnum = DPE_NUMBER_RE.search(text.upper())
    if mnum:
        try:
            ademe = await _apply_ademe_import(project_id, user["user_id"],
                                              mnum.group(0), p.get("inputs") or {})
        except HTTPException:
            ademe = None
    if ademe:
        pf = await _get_project(project_id, user["user_id"])
        filled = [{"path": k, "label": _FIELD_BY_PATH.get(k, {}).get("label", k),
                   "value": (v or {}).get("value")}
                  for k, v in (pf.get("inputs") or {}).items()
                  if (v or {}).get("source") == "DPE ADEME"]
        return {"ok": True, "ademe": True, "numero_dpe": mnum.group(0),
                "dpe": ademe["dpe"], "audits": ademe["audits"],
                "filled": filled, "count": len(filled),
                "message": f'Número de certificado energético detetado ({mnum.group(0)}) — certificado oficial ADEME importado automaticamente.'}

    extracted = await ai_engine.renovation_extract(text, QUESTIONNAIRE)
    inputs = p.get("inputs") or {}
    filled = []
    for path, val in extracted.items():
        inputs[path] = _evidence(val, status="documenté", source=f'Certificado/documento importado: {fname}',
                                 unit=_FIELD_BY_PATH[path].get("unit", ""))
        filled.append({"path": path, "label": _FIELD_BY_PATH[path]["label"], "value": val})
    # classe DPE éventuellement présente dans le texte → stockée comme DOCUMENT importé (pas simulation)
    import re
    imported_class = None
    m = re.search(r"class[ea][^\n:]{0,40}[:\s]\s*([A-G])(?![a-zA-Z])", text)
    if m:
        imported_class = m.group(1).upper()
    docmeta = {"doc_id": "dpe_" + secrets.token_hex(5), "filename": fname,
               "type": "dpe_import", "imported_class": imported_class, "imported_at": _now()}
    documents = (p.get("documents") or []) + [docmeta]
    await db.reno_projects.update_one(
        {"project_id": project_id, "user_id": user["user_id"]},
        {"$set": {"inputs": inputs, "documents": documents, "updated_at": _now()}})
    return {"ok": True, "filled": filled, "count": len(filled),
            "imported_class": imported_class,
            "note": ("Classe energética lida no documento (documento importado, não recalculado)."
                     if imported_class else "Nenhuma classe energética detetada automaticamente.")}


class PullSurfacesIn(BaseModel):
    plan_id: str


def _surface_family(m: dict) -> str | None:
    poste = (m.get("poste") or "").lower()
    lbl = (m.get("label") or "").lower()
    txt = poste + " " + lbl
    if any(k in txt for k in ["toiture", "combles", "plafond", "rampant", "couverture"]):
        return "toiture"
    if any(k in txt for k in ["sol", "plancher", "dalle", "carrelage", "parquet", "chape"]):
        return "plancher_bas"
    if any(k in txt for k in ["mur", "façade", "facade", "parpaing", "cloison", "enduit", "peinture", "isolation", "placo", "doublage"]):
        return "murs"
    return None


@router.get("/plans")
async def list_takeoff_plans(user=Depends(current_user)) -> dict:
    plans = await db.plans_takeoff.find(
        {"user_id": user["user_id"]},
        {"_id": 0, "plan_id": 1, "name": 1, "filename": 1, "updated_at": 1}).sort("updated_at", -1).to_list(100)
    out = [{"plan_id": p["plan_id"], "name": p.get("name") or p.get("filename") or p["plan_id"],
            "updated_at": p.get("updated_at")} for p in plans]
    return {"plans": out}


@router.post("/projects/{project_id}/pull-surfaces")
async def pull_surfaces(project_id: str, body: PullSurfacesIn, user=Depends(current_user)) -> dict:
    """Récupère les surfaces MESURÉES dans l'Éditeur de plans et les réinjecte dans le
    questionnaire (statut « mesuré »). On n'utilise que des cotes réellement mesurées."""
    p = await _get_project(project_id, user["user_id"])
    plan = await db.plans_takeoff.find_one(
        {"plan_id": body.plan_id, "user_id": user["user_id"]},
        {"_id": 0, "measurements": 1, "name": 1, "filename": 1})
    if not plan:
        raise HTTPException(404, "Planta não encontrada")
    sums = {"murs": 0.0, "toiture": 0.0, "plancher_bas": 0.0}
    counts = {"murs": 0, "toiture": 0, "plancher_bas": 0}
    for m in (plan.get("measurements") or []):
        area = m.get("area_m2")
        if area is None:
            area = m.get("wall_area_net_m2")
        if area is None:
            continue
        fam = _surface_family(m)
        if fam:
            sums[fam] += float(area)
            counts[fam] += 1
    mapping = {"murs": "geometrie.surface_murs_m2", "toiture": "geometrie.surface_toiture_m2",
               "plancher_bas": "geometrie.surface_plancher_bas_m2"}
    inputs = p.get("inputs") or {}
    filled = []
    src = f"Editor de plantas: {plan.get('name') or plan.get('filename') or body.plan_id}"
    for fam, path in mapping.items():
        if counts[fam] > 0 and sums[fam] > 0:
            val = round(sums[fam], 2)
            inputs[path] = _evidence(val, status="mesuré", source=src,
                                     unit=_FIELD_BY_PATH[path].get("unit", ""))
            filled.append({"path": path, "label": _FIELD_BY_PATH[path]["label"],
                           "value": val, "count": counts[fam]})
    if not filled:
        raise HTTPException(422, "Nenhuma área medida utilizável nesta planta (trace e nomeie áreas de paredes/cobertura/pavimento no Editor).")
    linked = (p.get("linked_plans") or [])
    if body.plan_id not in linked:
        linked.append(body.plan_id)
    await db.reno_projects.update_one(
        {"project_id": project_id, "user_id": user["user_id"]},
        {"$set": {"inputs": inputs, "linked_plans": linked, "updated_at": _now()}})
    return {"ok": True, "filled": filled, "count": len(filled)}


@router.get("/projects/{project_id}/report.pdf")
async def report_pdf(project_id: str, user=Depends(current_user)):
    """Rapport client RenoPilot (logo, graphiques, « Pourquoi ? », synthèse, scénarios)."""
    p = await _get_project(project_id, user["user_id"])
    branding = await _resolve_branding(user["user_id"])
    thumb_b64 = None
    linked = p.get("linked_plans") or []
    if linked:
        try:
            thumb_b64 = await _ensure_level_thumb(linked[0], user["user_id"])
        except Exception:
            thumb_b64 = None
    pdf = _build_report_pdf(p, branding, thumb_b64)
    safe = (p.get("title") or "renopilot").replace(" ", "_")[:40]
    return Response(content=pdf, media_type="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="RenoPilot_{safe}.pdf"'})


def _build_report_pdf(p: dict, branding: dict | None = None, thumb_b64: str | None = None) -> bytes:
    from io import BytesIO
    import base64
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.lib import colors
    from reportlab.platypus import (SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image)
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.graphics.shapes import Drawing
    from reportlab.graphics.charts.barcharts import VerticalBarChart

    ss = getSampleStyleSheet()
    GREEN = colors.Color(0.05, 0.5, 0.3)
    h1 = ParagraphStyle("h1", parent=ss["Title"], fontSize=18, textColor=GREEN, spaceAfter=2, alignment=0)
    h2 = ParagraphStyle("h2", parent=ss["Heading2"], fontSize=12, textColor=colors.Color(0.1, 0.12, 0.16), spaceBefore=10, spaceAfter=4)
    body = ParagraphStyle("body", parent=ss["Normal"], fontSize=9, leading=12)
    muted = ParagraphStyle("muted", parent=ss["Normal"], fontSize=8, textColor=colors.grey, leading=11)
    why = ParagraphStyle("why", parent=ss["Normal"], fontSize=7.5, textColor=GREEN, leading=10, leftIndent=4)

    inputs = p.get("inputs") or {}
    baseline = p.get("baseline") or {}
    scenarios = p.get("scenarios") or []
    buf = BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, topMargin=14 * mm, bottomMargin=16 * mm,
                            leftMargin=16 * mm, rightMargin=16 * mm, title="Rapport RenoPilot")
    story = []

    # En-tête avec logo (branding) + titre
    logo_b64 = (branding or {}).get("brand_logo_b64")
    company = (branding or {}).get("brand_company_name") or ""
    header_cells = []
    logo_flow = None
    if logo_b64:
        try:
            raw = base64.b64decode(logo_b64.split(",")[-1])
            logo_flow = Image(BytesIO(raw), width=26 * mm, height=26 * mm, kind="proportional")
        except Exception:
            logo_flow = None
    title_block = [Paragraph("RenoPilot — Relatório de reabilitação energética", h1),
                   Paragraph(p.get("title", ""), body)]
    if company:
        title_block.append(Paragraph(company, muted))
    if logo_flow is not None:
        ht = Table([[logo_flow, title_block]], colWidths=[30 * mm, 148 * mm])
        ht.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0)]))
        story.append(ht)
    else:
        # Repère de marque par défaut (bandeau vert) quand aucun logo n'est renseigné
        mark = company or "ConstruPilot"
        badge = Table([[Paragraph(f"<font color='white'><b>{mark}</b></font>", body)]], colWidths=[30 * mm])
        badge.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), GREEN), ("TOPPADDING", (0, 0), (-1, -1), 10),
                                   ("BOTTOMPADDING", (0, 0), (-1, -1), 10), ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                                   ("VALIGN", (0, 0), (-1, -1), "MIDDLE")]))
        ht = Table([[badge, title_block]], colWidths=[30 * mm, 148 * mm])
        ht.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0)]))
        story.append(ht)
    story.append(Spacer(1, 4))
    if p.get("ademe_dpe"):
        story.append(Paragraph("As classes e consumos provêm do certificado energético oficial (dados abertos ADEME) — dados retomados tal como estão, não vinculativos. As orçamentações de obras continuam indicativas.", muted))
    else:
        story.append(Paragraph("Estimativa de reabilitação — não substitui um certificado energético (SCE) nem uma auditoria regulamentar. Cálculo energético (classe, kWh) não efetuado: motor de cálculo não configurado.", muted))
    story.append(Spacer(1, 6))

    # ------- Bloc officiel ADEME : DPE + avant/après (audit) + aides & reste à charge -------
    ademe = p.get("ademe_dpe") or {}
    ademe_imm = p.get("ademe_dpe_immeuble") or {}
    ademe_audits = p.get("ademe_audits") or []
    aides = p.get("aides") or {}
    ETQ = {"A": "#319834", "B": "#33cc31", "C": "#cbfc34", "D": "#fbfe06",
           "E": "#fbcc05", "F": "#fc9935", "G": "#fc0205"}

    def _eur(n):
        try:
            return f"{int(round(float(n))):,} €".replace(",", " ")
        except Exception:
            return "—"

    def _clean(s):
        return (str(s or "")).replace("\u202f", " ").replace("\u00a0", " ")

    def _etq(letter):
        l = (letter or "").upper()
        c = colors.HexColor(ETQ.get(l, "#94a3b8"))
        tc = colors.white if l in ("A", "B", "F", "G") else colors.black
        st = ParagraphStyle("etq", parent=body, textColor=tc, alignment=1, fontSize=10)
        tb = Table([[Paragraph(f"<b>{l or '—'}</b>", st)]], colWidths=[9 * mm])
        tb.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), c), ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("TOPPADDING", (0, 0), (-1, -1), 2),
                                ("BOTTOMPADDING", (0, 0), (-1, -1), 2)]))
        return tb

    if ademe:
        story.append(Paragraph("Certificado energético oficial (dados abertos ADEME)", h2))
        info = Table([[Paragraph("Energia", muted), _etq(ademe.get("etiquette_energie")),
                       Paragraph("Climat", muted), _etq(ademe.get("etiquette_climat")),
                       Paragraph(f"{ademe.get('conso_ep_m2', '—')} kWh/m²·an · "
                                 f"{ademe.get('ges_m2', '—')} kgCO2/m²·an"
                                 + (f" · ≈ {_eur(ademe.get('cout_annuel'))}/an" if ademe.get('cout_annuel') else ""),
                                 body)]],
                     colWidths=[16 * mm, 11 * mm, 15 * mm, 11 * mm, 125 * mm])
        info.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "MIDDLE")]))
        story.append(info)
        story.append(Paragraph(f"{ademe.get('type_batiment', '')} · {ademe.get('surface_m2', '—')} m² · "
                               f"{ademe.get('periode_construction', '')} · {ademe.get('adresse', '')} · "
                               f"DPE n° {ademe.get('numero_dpe', '')} ({ademe.get('date_dpe', '')})", muted))
        if ademe_imm:
            story.append(Paragraph(f"Edifício (partes comuns) — certificado n.º {ademe_imm.get('numero_dpe', '')}: energia {ademe_imm.get('etiquette_energie', '—')} / climat {ademe_imm.get('etiquette_climat', '—')} (não ponderado com a habitação).", muted))
        story.append(Paragraph("Fonte: dados abertos ADEME — dados oficiais retomados tal como estão, não vinculativos.", why))

    if ademe_audits:
        story.append(Paragraph("Cenários de auditoria oficiais — antes / depois (ADEME)", h2))
        rows = [["Etapa", "DPE", "Custo das obras", "Gain conso", "Obras"]]
        for a in ademe_audits:
            for s in a.get("steps", []):
                gain = (f"{round(abs(s['gain_relatif_ep']) * 100)} %"
                        if s.get("gain_relatif_ep") is not None else "—")
                rows.append([s.get("etape", "") or "", s.get("etiquette_energie", "") or "—",
                             _eur(s.get("cout_travaux")) if s.get("cout_travaux") else "—", gain,
                             Paragraph((s.get("travaux") or "")[:130], muted)])
        t = Table(rows, colWidths=[22 * mm, 12 * mm, 26 * mm, 20 * mm, 98 * mm])
        t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), GREEN), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                               ("FONTSIZE", (0, 0), (-1, -1), 7.5), ("GRID", (0, 0), (-1, -1), 0.4, colors.lightgrey),
                               ("VALIGN", (0, 0), (-1, -1), "TOP"), ("ALIGN", (2, 0), (3, -1), "RIGHT"),
                               ("TOPPADDING", (0, 0), (-1, -1), 2), ("BOTTOMPADDING", (0, 0), (-1, -1), 2)]))
        story.append(t)
        # Graphe coût par étape (couleur = étiquette atteinte).
        try:
            steps_flat = [s for a in ademe_audits for s in a.get("steps", []) if s.get("cout_travaux")]
            if steps_flat:
                d = Drawing(440, 160)
                bc = VerticalBarChart()
                bc.x, bc.y, bc.width, bc.height = 35, 28, 380, 115
                bc.data = [[float(s.get("cout_travaux") or 0) for s in steps_flat]]
                bc.categoryAxis.categoryNames = [
                    f"{(s.get('etape') or '')[:10]}\n→{s.get('etiquette_energie') or ''}" for s in steps_flat]
                bc.valueAxis.valueMin = 0
                bc.categoryAxis.labels.fontSize = 6.5
                bc.valueAxis.labels.fontSize = 6.5
                bc.barWidth = 10
                for i, s in enumerate(steps_flat):
                    try:
                        bc.bars[(0, i)].fillColor = colors.HexColor(
                            ETQ.get((s.get("etiquette_energie") or "").upper(), "#94a3b8"))
                    except Exception:
                        pass
                d.add(bc)
                story.append(d)
                story.append(Paragraph("Custo das obras por etapa de auditoria (€). Cor = classe energética atingida.", muted))
        except Exception:
            pass

    if aides and aides.get("ok"):
        story.append(Paragraph("Apoios financeiros e encargo final (indicativo)", h2))
        sub = aides.get("total_subventions_indicatif")
        reste = aides.get("reste_a_charge_indicatif")
        tr = aides.get("travaux_ht")
        ptz = _clean((aides.get("eco_ptz") or {}).get("formattedValue"))
        kv = Table([
            [Paragraph("Travaux retenus", muted), Paragraph(f"<b>{_eur(tr)}</b>" if tr else "—", body),
             Paragraph("Total de subsídios", muted), Paragraph(f"<b>{_eur(sub)}</b>" if sub else "—", body)],
            [Paragraph("Valor a cargo", muted), Paragraph(f"<b>{_eur(reste)}</b>" if reste is not None else "—", body),
             Paragraph("Empréstimo bonificado", muted), Paragraph(ptz or "—", body)],
        ], colWidths=[36 * mm, 42 * mm, 40 * mm, 60 * mm])
        kv.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.4, colors.lightgrey), ("FONTSIZE", (0, 0), (-1, -1), 8),
                                ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3)]))
        story.append(kv)
        rows = [["Apoio", "Montante", "Estado"]]
        for a in (aides.get("aides") or [])[:12]:
            rows.append([Paragraph(a.get("label") or "", muted), _clean(a.get("value")) or "—",
                         "Applicable" if a.get("status") else "Não aplicável"])
        t = Table(rows, colWidths=[112 * mm, 30 * mm, 36 * mm])
        t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), GREEN), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                               ("FONTSIZE", (0, 0), (-1, -1), 7.5), ("GRID", (0, 0), (-1, -1), 0.4, colors.lightgrey),
                               ("VALIGN", (0, 0), (-1, -1), "TOP"), ("ALIGN", (1, 0), (1, -1), "RIGHT"),
                               ("TOPPADDING", (0, 0), (-1, -1), 2), ("BOTTOMPADDING", (0, 0), (-1, -1), 2)]))
        story.append(t)
        story.append(Paragraph(aides.get("disclaimer") or "Montantes indicativos — não vinculativos.", why))
    story.append(Spacer(1, 4))

    # ------- Aides par geste (MaPrimeRénov' + CEE par poste) -------
    aides_gestes = p.get("aides_gestes") or {}
    g_rows_src = aides_gestes.get("gestes") or []
    if g_rows_src:
        story.append(Paragraph("Apoios por intervenção", h2))
        rows = [["Artigo", "Quantidade", "MaPrimeRénov'", "Certificados de poupança", "Total"]]
        for g in g_rows_src:
            val = g.get("value")
            qty_txt = f"{val} {g.get('unit') or ''}".strip() if val not in (None, "") else "—"
            mpr = g.get("mpr")
            cee = g.get("cee")
            mpr_txt = _eur(mpr) if isinstance(mpr, (int, float)) else "—"
            cee_txt = _eur(cee) if isinstance(cee, (int, float)) else "—"
            tot_v = (mpr if isinstance(mpr, (int, float)) else 0) + (cee if isinstance(cee, (int, float)) else 0)
            tot_txt = _eur(tot_v) if tot_v else "—"
            label = g.get("label") or ""
            note = g.get("note")
            cell = Paragraph(label + (f"<br/><font color='#92400e' size=6.5>{_clean(note)}</font>" if note else ""), muted)
            rows.append([cell, qty_txt, mpr_txt, cee_txt, tot_txt])
        rows.append([Paragraph("<b>Total de apoios (indicativo)</b>", muted), "",
                     _eur(aides_gestes.get("total_mpr_indicatif")),
                     _eur(aides_gestes.get("total_cee_indicatif")),
                     _eur(aides_gestes.get("total_aides_indicatif"))])
        t = Table(rows, colWidths=[70 * mm, 22 * mm, 30 * mm, 26 * mm, 30 * mm])
        t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), GREEN), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                               ("FONTSIZE", (0, 0), (-1, -1), 7.5), ("GRID", (0, 0), (-1, -1), 0.4, colors.lightgrey),
                               ("VALIGN", (0, 0), (-1, -1), "TOP"), ("ALIGN", (2, 0), (4, -1), "RIGHT"),
                               ("BACKGROUND", (0, -1), (-1, -1), colors.Color(0.93, 0.98, 0.95)),
                               ("TOPPADDING", (0, 0), (-1, -1), 2), ("BOTTOMPADDING", (0, 0), (-1, -1), 2)]))
        story.append(t)
        story.append(Paragraph(aides_gestes.get("disclaimer") or "Montantes indicativos por medida — não vinculativos.", why))
        story.append(Spacer(1, 4))


    cov = baseline.get("coverage_pct")
    story.append(Paragraph("Dados e fiabilidade", h2))
    story.append(Paragraph(f"Cobertura dos dados preenchidos: <b>{(cov if cov is not None else '—')}%</b>. Os dados desconhecidos continuam visíveis e não são substituídos por valores predefinidos.", body))
    story.append(Paragraph("Porquê? As áreas provêm da introdução manual, do Editor de plantas (estado «medido») ou de um certificado importado (estado «documentado»). As orçamentações sem fonte estão marcadas «a orçamentar».", why))
    if thumb_b64:
        try:
            traw = base64.b64decode(thumb_b64)
            timg = Image(BytesIO(traw), width=45 * mm, height=45 * mm, kind="proportional")
            story.append(Spacer(1, 3))
            story.append(Paragraph("Pré-visualização da planta associada (áreas medidas no Editor de plantas):", muted))
            story.append(timg)
        except Exception:
            pass

    posts = baseline.get("posts") or []
    if posts:
        story.append(Paragraph("Estado estimado (análise qualitativa — Nível A)", h2))
        rows = [["Componente", "Avaliação", "Observação · Porquê?"]]
        for pt in posts:
            dn = ", ".join(pt.get("data_needed") or [])
            cell = Paragraph(f"{pt['reason']}<br/><font color='#0a7a4d' size=7>Dado(s) a verificar: {dn or '—'}</font>", muted)
            rows.append([pt["component"], pt["assessment"], cell])
        t = Table(rows, colWidths=[36 * mm, 40 * mm, 102 * mm])
        t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), GREEN), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                               ("FONTSIZE", (0, 0), (-1, -1), 8), ("GRID", (0, 0), (-1, -1), 0.4, colors.lightgrey),
                               ("VALIGN", (0, 0), (-1, -1), "TOP"), ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3)]))
        story.append(t)
        story.append(Paragraph("Classe energética: não calculada. Consumo (kWh): não calculado (motor não configurado).", muted))

    if scenarios:
        story.append(Paragraph("Cenários de reabilitação comparados", h2))
        # Graphique : coût chiffrable par scénario
        try:
            d = Drawing(420, 150)
            bc = VerticalBarChart()
            bc.x = 20; bc.y = 15; bc.width = 380; bc.height = 115
            bc.data = [[round(s.get("total_ht_chiffrable", 0)) for s in scenarios]]
            bc.categoryAxis.categoryNames = [s["key"] for s in scenarios]
            bc.barWidth = 10
            bc.bars[0].fillColor = GREEN
            bc.valueAxis.valueMin = 0
            bc.categoryAxis.labels.fontSize = 8
            bc.valueAxis.labels.fontSize = 7
            d.add(bc)
            story.append(d)
            story.append(Paragraph("Custo das obras orçamentáveis por cenário (€ s/ IVA). Os artigos «a orçamentar» não estão incluídos.", muted))
        except Exception:
            pass
        rows = [["Percurso", "Obras orçamentadas s/ IVA", "A orçamentar", "Orçamento"]]
        for s in scenarios:
            rows.append([f"{s['key']} — {s['name']}",
                         f"{s.get('total_ht_chiffrable', 0):,.0f} €".replace(",", " "),
                         str(len(s.get("a_chiffrer") or [])),
                         s.get("budget_flag") or "—"])
        t = Table(rows, colWidths=[70 * mm, 40 * mm, 25 * mm, 43 * mm])
        t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), GREEN), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                               ("FONTSIZE", (0, 0), (-1, -1), 8), ("GRID", (0, 0), (-1, -1), 0.4, colors.lightgrey),
                               ("ALIGN", (1, 0), (1, -1), "RIGHT"), ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3)]))
        story.append(t)
        story.append(Paragraph("Porquê? Ganhos energéticos não calculados (motor não configurado). As medidas interagem: nenhuma soma de percentagens. Preços «hipótese»/«a orçamentar» a confirmar por uma fonte local datada.", why))
        sc = next((s for s in scenarios if s["key"] == "P3"), scenarios[-1])
        story.append(Paragraph(f"Descrição por lote — {sc['name']}", h2))
        for it in sc.get("work_items", []):
            story.append(Paragraph(f"<b>{it['lot']} — {it['label']}</b>", body))
            dd = it["descriptif"]
            q = it["metre"]
            qty_txt = f"{q['quantity']} {q['unit']}" if q.get("quantity") is not None else f"{q['unit']} a confirmar"
            story.append(Paragraph(f"Medição: {qty_txt} · Preço: {dd['prix']}", muted))
            story.append(Paragraph(f"Objetivo: {dd['objectif']} — Controlos: {dd['controles']}", muted))
            story.append(Paragraph(f"Porquê este preço? {it['chiffrage'].get('status', '')} (source : {it['chiffrage'].get('source') or 'sem fonte'}).", why))
            story.append(Spacer(1, 3))

    doc.build(story)
    return buf.getvalue()


@router.delete("/projects/{project_id}")
async def delete_project(project_id: str, user=Depends(current_user)) -> dict:
    r = await db.reno_projects.delete_one({"project_id": project_id, "user_id": user["user_id"]})
    if not r.deleted_count:
        raise HTTPException(404, "Projeto não encontrado")
    return {"ok": True}
