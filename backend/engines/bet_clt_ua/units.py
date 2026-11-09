"""Explicit conversions. Nominal timber sizes are never actual section sizes."""
import math
import re

def imperial_length_m(text: str) -> float:
    m = re.fullmatch(r"\s*(\d+(?:\.\d+)?)\s*'\s*(?:-?\s*(\d+(?:\.\d+)?)\s*\")?\s*", text)
    if not m:
        raise ValueError("Expected decimal feet or feet-inches, e.g. 186.6' or 19'-8\"")
    feet, inches = float(m[1]), float(m[2] or 0)
    if inches >= 12:
        raise ValueError("Inches must be less than 12")
    return feet * 0.3048 + inches * 0.0254

def r_imperial_to_rsi(r: float) -> float:
    if isinstance(r, bool) or not math.isfinite(r) or r <= 0:
        raise ValueError("Positive finite imperial R required")
    return r * 0.1761101838
