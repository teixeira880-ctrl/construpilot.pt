"""Detecção de país/locale/normas a partir da morada do projeto.

Heurística (ordem):
  1. Token explícito do país ("France", "Portugal", "FR", "PT").
  2. Código postal: FR = 5 dígitos (01000-97999); PT = NNNN-NNN (4-3 dígitos).
  3. Fallback → PT com warning. Nunca FR por defeito.
"""
import re
from typing import Any

_FR_TOKENS = {"france", "frança", "françaises", "fr"}
_PT_TOKENS = {"portugal", "portuguesa", "português", "pt"}

_RE_CP_FR = re.compile(r"\b(0[1-9]|[1-8]\d|9[0-5])\d{3}\b")  # 01000-95999
_RE_CP_PT = re.compile(r"\b\d{4}-\d{3}\b")

PROFILES = {
    "FR": {
        "country_code": "FR",
        "locale": "fr-FR",
        "norms": "NF EN + AN FR",
        "doc_language": "fr",
    },
    "PT": {
        "country_code": "PT",
        "locale": "pt-PT",
        "norms": "NP EN + AN PT",
        "doc_language": "pt",
    },
}


def detect_country_from_address(address: str) -> dict[str, Any]:
    """Devolve dicionário com country_code / locale / norms / doc_language."""
    if not address:
        return {**PROFILES["PT"], "ambiguous": True}
    s = address.lower().strip()
    tokens = {t.strip(" ,.;:") for t in re.split(r"[\s,]+", s) if t}
    if tokens & _FR_TOKENS:
        return PROFILES["FR"]
    if tokens & _PT_TOKENS:
        return PROFILES["PT"]
    if _RE_CP_PT.search(address):
        return PROFILES["PT"]
    if _RE_CP_FR.search(address):
        return PROFILES["FR"]
    # Fallback explícito — nunca assume FR por defeito
    return {**PROFILES["PT"], "ambiguous": True,
            "fallback_reason": "país não detectado — PT por defeito"}
