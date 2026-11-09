"""Prevent a CLT/Ukraine study from entering legacy masonry/RC defaults."""
import json
import re

def is_clt(value) -> bool:
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, default=str)
    return bool(re.search(r"\bCLT\b|cross[ -]laminated|cross[ -]lamell|клеєн\w*\s+перехрес|перехресно", text, re.I))

def legacy_issue(raw: dict) -> dict | None:
    country = str((raw.get("project") or {}).get("country") or "FR").upper()
    # Só a Ucrânia é desviada: o CLT em França / Portugal continua nos motores existentes (sem retrocesso).
    if country == "UA" or raw.get("schema_version") == "clt-ua-1":
        return {"code": "ENGINE-SCOPE", "level": "bloquant",
                "message": "CLT / country outside legacy FR-PT scope: material and country substitution prohibited.",
                "fix": "Use the Ukraine CLT evidence and explicit-input calculation engine for UA; retain source facts."}
    return None


def clt_warning(raw: dict) -> dict | None:
    """FR / PT com CLT indicado: o estudo continua nos motores existentes (sem retrocesso), com aviso explícito de que
    o motor alvenaria / BA não dimensiona os painéis CLT (usar calc_lots.gros_oeuvre / estrutura de madeira)."""
    country = str((raw.get("project") or {}).get("country") or "FR").upper()
    if country in {"FR", "PT"} and is_clt(raw.get("user_hypotheses") or {}):
        return {"code": "CLT-SCOPE", "level": "avertissement",
                "message": "CLT indiqué : ce moteur maçonnerie / BA ne dimensionne pas les panneaux CLT — à vérifier séparément.",
                "fix": "Vérifier les panneaux et assemblages CLT avec le moteur bois (calcul_structure / calcul_gros_oeuvre) ou le BET bois."}
    return None
