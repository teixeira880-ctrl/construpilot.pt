"""BET.4 — Dados regionais FR (neve NV65 + sismicidade EC8-AN FR).

Também detecta discrepância entre `building_type` no PC e `mass_plan_annotation`.

Nota: tabelas simplificadas por departamento (primeiros 2 dígitos do CP FR).
Para zonas não mapeadas, assume defaults prudentes (A1 neve, zona 1 sísmica).
"""
import re
from typing import Any

# NV65 — zona de neve por departamento (prefixo CP FR).
# Default A1 para todo o território metropolitano em MVP.
_SNOW_ZONES_FR: dict[str, str] = {
    # Île-de-France
    "75": "A1", "77": "A1", "78": "A1", "91": "A1",
    "92": "A1", "93": "A1", "94": "A1", "95": "A1",
    # Normandia / Bretanha
    "14": "A1", "27": "A1", "50": "A1", "61": "A1", "76": "A1",
    "22": "A1", "29": "A1", "35": "A1", "56": "A1",
    # Hauts-de-France / Grand-Est (zonas B/C/D ajustáveis)
    "02": "A2", "59": "A2", "60": "A2", "62": "A2", "80": "A2",
    "67": "B1", "68": "B2", "88": "C1",
    # Auvergne-Rhône-Alpes (montanha)
    "73": "E", "74": "E", "38": "C2", "05": "D", "04": "C2",
    # PACA / Occitanie
    "06": "C1", "13": "A2", "83": "A2", "84": "A2",
    "11": "A2", "66": "A2", "34": "A1", "30": "A1",
}

# EC8-AN FR — zonas sísmicas por departamento (simplificado).
# Métropole: 1 (très faible) a 4 (moyenne); DOM: 5.
_SISMIC_ZONES_FR: dict[str, str] = {
    # Zona 1 (très faible) — maioria do norte/oeste
    "75": "1", "77": "1", "78": "1", "91": "1",
    "92": "1", "93": "1", "94": "1", "95": "1",
    "14": "1", "27": "1", "50": "1", "61": "1", "76": "1",
    "22": "1", "29": "1", "35": "1", "56": "1",
    "02": "1", "59": "1", "60": "1", "62": "1", "80": "1",
    # Zona 2 (faible) — Centre, Val-de-Loire
    "18": "2", "28": "2", "36": "2", "37": "2", "41": "2", "45": "2",
    "72": "2", "49": "2", "44": "2", "85": "2",
    # Zona 3 (modérée) — Alpes-Maritimes, PACA litoral
    "04": "3", "05": "3", "06": "3", "13": "3", "83": "3",
    # Zona 4 (moyenne) — Alpes du Nord, Pyrénées
    "73": "4", "74": "4", "38": "4", "65": "4", "64": "4",
}


def _extract_fr_dep(address: str) -> str | None:
    """Devolve os 2 primeiros dígitos do CP FR encontrado no endereço."""
    if not address:
        return None
    m = re.search(r"\b(\d{5})\b", address)
    if not m:
        return None
    return m.group(1)[:2]


def lookup(pc: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {
        "snow_zone": None,
        "parasismic_rules": None,
        "warnings": [],
    }

    addr = pc.get("project_address") or ""
    dep = _extract_fr_dep(addr)
    if dep:
        out["snow_zone"] = _SNOW_ZONES_FR.get(dep, "A1")
        zone = _SISMIC_ZONES_FR.get(dep, "1")
        out["parasismic_rules"] = {
            "zone": zone,
            "required": zone not in {"1"},
            "basis": "EC8-AN FR",
            "department": dep,
        }

    # Discrepância descrição edifício (PC vs plano de massas)
    bt = (pc.get("building_type") or "").strip()
    mpa = (pc.get("mass_plan_annotation") or "").strip()
    if bt and mpa and bt.lower() != mpa.lower():
        out["warnings"].append({
            "code": "building_description_mismatch",
            "severity": "medium",
            "detail": (
                f"Descrição do edifício no PC ({bt}) difere da anotação "
                f"no plano de massas ({mpa}). Reconciliar com MOA antes "
                "de dimensionar."
            ),
            "remediation": (
                "Confirmar com o projetista de arquitetura qual a "
                "descrição vinculativa (PC assinado prevalece)."
            ),
            "action": "require_moa_input",
        })

    return out
