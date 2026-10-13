"""One input contract for public calculators and the platform assistant."""
import math

from engines.calculators import CALCULATORS


def run_validated(key: str, params: dict, *, require_inputs: bool = False) -> dict:
    cfg = CALCULATORS.get(key)
    if not cfg:
        raise ValueError("Calculadora desconhecida")
    if not isinstance(params, dict):
        raise ValueError("Parâmetros inválidos")
    if set(params) - {field["name"] for field in cfg["fields"]}:
        raise ValueError("Campo desconhecido para esta calculadora; verifique os parâmetros e unidades")
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
                raise ValueError(f"Indique {field['label']} ; nenhuma dimensão por omissão é utilizada pelo agente.")
            value = field["default"]
            defaults.append(name)
        if field["type"] == "number":
            if isinstance(value, bool):
                raise ValueError(f"{field['label']} : número esperado")
            try:
                value = float(value)
            except (TypeError, ValueError):
                raise ValueError(f"{field['label']} : número esperado") from None
            if not math.isfinite(value) or value < 0 or value > 1_000_000:
                raise ValueError(f"{field['label']} : valor positivo finito obrigatório (máximo 1 000 000)")
            if name in positive and value <= 0:
                raise ValueError(f"{field['label']} deve ser superior a zero")
            if name in integers:
                if not value.is_integer():
                    raise ValueError(f"{field['label']} : número inteiro obrigatório")
                value = int(value)
            if name == "pitch_deg" and value >= 89:
                raise ValueError("A inclinação deve estar entre 0 e 89 graus exclusive")
        elif field["type"] == "boolean":
            if type(value) is bool:
                pass
            elif value in ("true", "false"):
                value = value == "true"
            else:
                raise ValueError(f"{field['label']} : verdadeiro ou falso esperado")
        elif field["type"] == "select" and value not in field.get("options", []):
            raise ValueError(f"{field['label']} : opção desconhecida")
        args[name] = value
    if key == "roof_facade" and args.get("openings_m2", 0) > args.get("wall_perimeter_m", 0) * args.get("wall_height_m", 0):
        raise ValueError("A área dos vãos ultrapassa a da fachada")
    try:
        result = cfg["fn"](**args)
    except (TypeError, ValueError, ZeroDivisionError, OverflowError):
        raise ValueError("Dados incompatíveis com este cálculo; verifique as dimensões e as unidades") from None

    def finite(value):
        if isinstance(value, float) and not math.isfinite(value):
            raise ValueError("O cálculo produziu um valor não finito")
        if isinstance(value, dict):
            for child in value.values():
                finite(child)
        if isinstance(value, list):
            for child in value:
                finite(child)

    finite(result)
    return {**result, "validation": {"arithmetic_checked": True, "defaulted_fields": defaults,
                                     "inputs": args, "source_measurements_verified": False}}
