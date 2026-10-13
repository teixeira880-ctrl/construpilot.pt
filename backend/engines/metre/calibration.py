"""Per-view scale calibration: explicit dimensions calibrate each view/detail; pixel measures are blocked when the scale is unreliable."""
import math
import statistics

from .contracts import Calculation

SPREAD_TOL = 0.015
DECLARED_TOL = 0.03
ANISOTROPY_TOL = 0.01
INCH_M = 0.0254


def calibrate_view(*, view_id: str, references: list[dict], declared_scale: str | None = None, dpi: float | None = None) -> dict:
    """references: [{label, value_m, px_length, axis: 'h'|'v'|None}] — explicit, legible dimensions of THIS view only."""
    refs = [r for r in references if r.get("value_m") and r.get("px_length") and r["value_m"] > 0 and r["px_length"] > 0]
    reasons = []
    if not refs:
        return {"view_id": view_id, "status": "unreliable", "px_per_m": None, "measurements_allowed": False,
                "reasons": ["Aucune cote explicite lisible pour calibrer cette vue : mesures en pixels interdites, cotes explicites toujours lisibles."]}
    for r in refs:
        r["px_per_m"] = r["px_length"] / r["value_m"]
    ratios = [r["px_per_m"] for r in refs]
    median = statistics.median(ratios)
    spread = (max(ratios) - min(ratios)) / median if len(ratios) > 1 else 0.0
    if len(refs) < 2:
        reasons.append("Une seule référence : calibration non confirmée par une cote indépendante.")
    if spread > SPREAD_TOL:
        reasons.append(f"Références incohérentes entre elles ({spread * 100:.1f} % d'écart) : plusieurs échelles ou lecture erronée dans la vue.")
    axes = {}
    for axis in ("h", "v"):
        vals = [r["px_per_m"] for r in refs if r.get("axis") == axis]
        if vals:
            axes[axis] = statistics.median(vals)
    anisotropy = None
    if "h" in axes and "v" in axes:
        anisotropy = abs(axes["h"] - axes["v"]) / max(axes["h"], axes["v"])
        if anisotropy > ANISOTROPY_TOL:
            reasons.append(f"Déformation : échelle horizontale et verticale différentes ({anisotropy * 100:.1f} %) — scan étiré ou vue anamorphosée.")
    declared_check = None
    if declared_scale and dpi:
        try:
            denom = float(declared_scale.replace(" ", "").split("/")[-1].split(":")[-1])
            expected = dpi / INCH_M / denom
            diff = (median - expected) / expected
            declared_check = {"declared_scale": declared_scale, "expected_px_per_m": round(expected, 2), "measured_px_per_m": round(median, 2), "difference_pct": round(diff * 100, 2)}
            if abs(diff) > DECLARED_TOL:
                reasons.append(f"L'échelle du cartouche ({declared_scale}) ne correspond pas au document ({diff * 100:+.1f} %) : PDF redimensionné ou impression ; l'échelle déclarée n'est pas utilisée.")
        except (ValueError, ZeroDivisionError):
            declared_check = {"declared_scale": declared_scale, "error": "échelle déclarée illisible"}
    reliable = len(refs) >= 2 and spread <= SPREAD_TOL and (anisotropy is None or anisotropy <= ANISOTROPY_TOL)
    axis_ok = anisotropy is not None and anisotropy > ANISOTROPY_TOL and len(refs) >= 3 and spread_by_axis_ok(refs)
    status = "reliable" if reliable else "per_axis" if axis_ok else "unreliable"
    return {"view_id": view_id, "status": status, "px_per_m": round(median, 3) if status == "reliable" else None,
            "px_per_m_by_axis": {k: round(v, 3) for k, v in axes.items()} if status == "per_axis" else None,
            "spread_pct": round(spread * 100, 2), "anisotropy_pct": None if anisotropy is None else round(anisotropy * 100, 2),
            "declared_check": declared_check, "references": [{k: r.get(k) for k in ("label", "value_m", "px_length", "axis")} | {"px_per_m": round(r["px_per_m"], 3)} for r in refs],
            "measurements_allowed": status != "unreliable", "reasons": reasons,
            "note": "Calibration propre à cette vue / ce détail ; ne pas la réutiliser pour une autre vue de la feuille."}


def spread_by_axis_ok(refs: list[dict]) -> bool:
    for axis in ("h", "v"):
        vals = [r["px_per_m"] for r in refs if r.get("axis") == axis]
        if len(vals) >= 2 and (max(vals) - min(vals)) / statistics.median(vals) > SPREAD_TOL:
            return False
    return True


def measure_pixels(*, calibration: dict, label: str, px_length: float, axis: str | None = None) -> dict:
    """Converts a pixel length with a view calibration; refused (not_verifiable) when the calibration is unreliable."""
    inputs = [{"label": label, "px_length": px_length, "axis": axis, "view_id": calibration.get("view_id"), "calibration_status": calibration.get("status")}]
    if not calibration.get("measurements_allowed"):
        calc = Calculation(kind="pixel_measure", inputs=inputs, formula="—", result=None, unit="m", state="not_verifiable",
                           reason="Échelle non fiable pour cette vue : aucune mesure dérivée des pixels n'est présentée comme confirmée. " + " ".join(calibration.get("reasons") or []))
        return {"calculation": calc.model_dump(), "allowed": False}
    factor = calibration.get("px_per_m")
    if calibration.get("status") == "per_axis":
        factor = (calibration.get("px_per_m_by_axis") or {}).get(axis)
        if not factor:
            calc = Calculation(kind="pixel_measure", inputs=inputs, formula="—", result=None, unit="m", state="not_verifiable",
                               reason="Vue déformée : indiquer l'axe (h/v) de la mesure pour utiliser la calibration par axe.")
            return {"calculation": calc.model_dump(), "allowed": False}
    value = round(px_length / factor, 4)
    calc = Calculation(kind="pixel_measure", inputs=inputs, formula=f"{px_length:g} px / {factor:g} px/m = {value:g} m", result=value, unit="m", state="probable",
                       reason="Mesure géométrique calibrée : une cote explicite lisible reste prioritaire sur cette valeur.",
                       tolerance={"calibration_spread_pct": calibration.get("spread_pct"), "execution_tol": None})
    return {"calculation": calc.model_dump(), "allowed": True}
