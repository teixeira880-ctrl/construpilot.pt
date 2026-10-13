"""One input contract for public calculators and the platform assistant."""
import math

from engines.calculators import CALCULATORS


def run_validated(key: str, params: dict, *, require_inputs: bool = False) -> dict:
    cfg = CALCULATORS.get(key)
    if not cfg:
        raise ValueError("Calculateur inconnu")
    if not isinstance(params, dict):
        raise ValueError("Paramètres invalides")
    if set(params) - {field["name"] for field in cfg["fields"]}:
        raise ValueError("Champ inconnu pour ce calculateur ; vérifiez les paramètres et unités")
    args, defaults = {}, []
    integers = {"doors", "windows", "coats", "tiles_per_box"}
    positive = {"tile_length", "tile_width", "tiles_per_box", "plate_length", "plate_width", "coats"}
    for field in cfg["fields"]:
        name = field["name"]
        value = params.get(name)
        if value is None or value == "":
            if field.get("default") is None:
                continue
            if require_inputs:
                raise ValueError(f"Précisez {field['label']} ; aucune dimension par défaut n'est utilisée par l'agent.")
            value = field["default"]
            defaults.append(name)
        if field["type"] == "number":
            if isinstance(value, bool):
                raise ValueError(f"{field['label']} : nombre attendu")
            try:
                value = float(value)
            except (TypeError, ValueError):
                raise ValueError(f"{field['label']} : nombre attendu") from None
            if not math.isfinite(value) or value < 0 or value > 1_000_000:
                raise ValueError(f"{field['label']} : valeur positive finie requise (maximum 1 000 000)")
            if name in positive and value <= 0:
                raise ValueError(f"{field['label']} doit être supérieur à zéro")
            if name in integers:
                if not value.is_integer():
                    raise ValueError(f"{field['label']} : nombre entier requis")
                value = int(value)
            if name == "pitch_deg" and value >= 89:
                raise ValueError("La pente doit être comprise entre 0 et 89 degrés exclus")
        elif field["type"] == "boolean":
            if type(value) is bool:
                pass
            elif value in ("true", "false"):
                value = value == "true"
            else:
                raise ValueError(f"{field['label']} : vrai ou faux attendu")
        elif field["type"] == "select" and value not in field.get("options", []):
            raise ValueError(f"{field['label']} : option inconnue")
        args[name] = value
    if key == "roof_facade" and args.get("openings_m2", 0) > args.get("wall_perimeter_m", 0) * args.get("wall_height_m", 0):
        raise ValueError("La surface des ouvertures dépasse celle de la façade")
    try:
        result = cfg["fn"](**args)
    except (TypeError, ValueError, ZeroDivisionError, OverflowError):
        raise ValueError("Données incompatibles avec ce calcul ; vérifiez les dimensions et les unités") from None

    def finite(value):
        if isinstance(value, float) and not math.isfinite(value):
            raise ValueError("Le calcul a produit une valeur non finie")
        if isinstance(value, dict):
            for child in value.values():
                finite(child)
        if isinstance(value, list):
            for child in value:
                finite(child)

    finite(result)
    return {**result, "validation": {"arithmetic_checked": True, "defaulted_fields": defaults,
                                     "inputs": args, "source_measurements_verified": False}}
