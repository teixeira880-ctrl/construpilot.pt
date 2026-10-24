"""Dimension-chain arithmetic: interior spans + wall thicknesses, value comparison, ambiguous readings."""
from .contracts import Calculation, Finding, Reading, worst

READING_TOL_M = 0.01


def _fmt(v: float) -> str:
    return f"{v:.2f}".rstrip("0").rstrip(".") if abs(v - round(v, 2)) < 1e-9 else f"{v:.3f}"


def _input(r: Reading) -> dict:
    return {"label": r.label, "value_m": r.value_m, "candidates_m": r.candidates_m, "origin": r.origin, "state": r.state,
            "plan_id": r.plan_id, "page": r.page, "box": r.box}


def _readings(items: list) -> list[Reading]:
    return [i if isinstance(i, Reading) else Reading(**i) for i in items]


def check_dimension_chain(*, spans: list, thicknesses: list | None = None, chain_includes_thickness: bool = False,
                          reference: str = "faces", declared_total: Reading | dict | None = None,
                          reading_tol_m: float = READING_TOL_M) -> dict:
    """Sums a chain of spans (+ thicknesses of walls actually crossed) and compares it with a declared total.

    `reference="axes"` means the declared total runs between the axes of the two end walls: only half of the
    first and last thickness is inside the interval. Thicknesses are never added twice: when the chain already
    includes them (`chain_includes_thickness=True`) the list is only used for documentation.
    """
    spans_r, thick_r = _readings(spans), _readings(thicknesses or [])
    total_r = Reading(**declared_total) if isinstance(declared_total, dict) else declared_total
    parts = spans_r + ([] if chain_includes_thickness else thick_r)
    states = [r.state for r in parts]
    inputs = [_input(r) for r in spans_r + thick_r] + ([_input(total_r)] if total_r else [])
    unresolved = [r.label for r in parts if r.state == "indeterminate"]
    terms = [f"{_fmt(r.value_m)}" for r in spans_r if r.value_m is not None]
    applied_thick = []
    if not chain_includes_thickness:
        for idx, r in enumerate(thick_r):
            if r.value_m is None:
                continue
            if reference == "axes" and idx in (0, len(thick_r) - 1) and len(thick_r) >= 2:
                applied_thick.append(r.value_m / 2)
                terms.append(f"{_fmt(r.value_m)}/2")
            else:
                applied_thick.append(r.value_m)
                terms.append(_fmt(r.value_m))
    formula = " + ".join(terms) if terms else "—"
    if unresolved:
        calc = Calculation(kind="dimension_chain", inputs=inputs, formula=formula, result=None, unit="m", state="indeterminate",
                           reason=f"Leitura não resolvida: {', '.join(unresolved)}. Nenhum total é calculado antes da confirmação.")
        return {"calculation": calc.model_dump(), "findings": [Finding(subject="Cadeia de cotas", severity="to_clarify", certainty="indeterminate",
                explanation=calc.reason, action="Ampliação / extração nativa da cota ambígua", calc_id=calc.calc_id).model_dump()]}
    total = round(sum(r.value_m for r in spans_r) + sum(applied_thick), 4)
    note = " (espessuras já incluídas na cadeia, não acrescentadas de novo)" if chain_includes_thickness and thick_r else ""
    calc = Calculation(kind="dimension_chain", inputs=inputs, formula=f"{formula} = {_fmt(total)} m{note}", result=total, unit="m",
                       state=worst(*states), reason="Soma dos vãos" + ("" if chain_includes_thickness else " e das espessuras atravessadas"),
                       tolerance={"reading_tol_m": reading_tol_m, "execution_tol": None})
    findings = []
    if total_r is not None:
        cmp = compare_values(Reading(label="total calculado", value_m=total, origin="native_text"), total_r, same_interval=True,
                             same_reference=True, reading_tol_m=reading_tol_m)
        cmp["calculation"]["kind"] = "chain_vs_declared_total"
        findings = cmp["findings"]
        return {"calculation": calc.model_dump(), "comparison": cmp["calculation"], "findings": findings}
    return {"calculation": calc.model_dump(), "findings": findings}


def compare_values(a: Reading | dict, b: Reading | dict, *, same_interval: bool, same_reference: bool,
                   reading_tol_m: float = READING_TOL_M) -> dict:
    """Arithmetic difference between two values; only an incoherence when interval and reference are the same."""
    ra = Reading(**a) if isinstance(a, dict) else a
    rb = Reading(**b) if isinstance(b, dict) else b
    inputs = [_input(r) for r in (ra, rb)]
    if ra.usable is None or rb.usable is None:
        calc = Calculation(kind="value_comparison", inputs=inputs, formula="—", result=None, unit="m", state="indeterminate",
                           reason="Um dos dois valores não está resolvido.")
        return {"calculation": calc.model_dump(), "findings": []}
    diff = round(rb.usable - ra.usable, 4)
    formula = f"{_fmt(rb.usable)} − {_fmt(ra.usable)} = {_fmt(diff)} m ({round(abs(diff) * 100, 1):g} cm)"
    if not (same_interval and same_reference):
        calc = Calculation(kind="value_comparison", inputs=inputs, formula=formula, result=diff, unit="m", state="indeterminate",
                           reason="Intervalos ou referências diferentes: a diferença está documentada mas não constitui uma incoerência.")
        return {"calculation": calc.model_dump(), "findings": [Finding(subject=f"{ra.label} / {rb.label}", severity="info", certainty="indeterminate",
                explanation=calc.reason, action="Confirmar que as duas cotas cobrem o mesmo intervalo e a mesma referência (faces / eixos)",
                calc_id=calc.calc_id).model_dump()]}
    certainty = worst(ra.state, rb.state)
    within = abs(diff) <= reading_tol_m
    calc = Calculation(kind="value_comparison", inputs=inputs, formula=formula, result=diff, unit="m", state=certainty,
                       reason="Diferença dentro da tolerância de leitura" if within else "Diferença superior à tolerância de leitura — mesmo intervalo e mesma referência",
                       tolerance={"reading_tol_m": reading_tol_m, "execution_tol": None})
    if within:
        return {"calculation": calc.model_dump(), "findings": []}
    finding = Finding(subject=f"{ra.label} / {rb.label}", severity="demonstrated" if certainty == "confirmed" else "to_clarify", certainty=certainty,
                      explanation=f'Diferença de {round(abs(diff) * 100, 1):g} cm entre {ra.label} ({_fmt(ra.usable)} m) e {rb.label} ({_fmt(rb.usable)} m).',
                      consequence="Ponto de leitura ou de coerência a esclarecer; nenhuma tolerância de execução é aplicada sem referência verificada.",
                      action="Verificar as duas cotas na planta (ampliação / extração nativa) e pedir confirmação ao gabinete de projeto se a diferença persistir",
                      calc_id=calc.calc_id)
    return {"calculation": calc.model_dump(), "findings": [finding.model_dump()]}


def resolve_reading(*, label: str, candidates_m: list[float], confirmations: list[dict] | None = None,
                    arithmetic_fit_m: float | None = None) -> dict:
    """Ambiguous OCR (13,27 / 13,72): only independent evidence resolves it — never the value that makes a total close."""
    confirmations = confirmations or []
    supported = {}
    for c in confirmations:
        if c.get("kind") not in ("native_text", "zoom_crop", "user_statement"):
            continue
        try:
            supported.setdefault(round(float(c["value_m"]), 3), []).append(c)
        except (KeyError, TypeError, ValueError):
            continue
    matching = {v: e for v, e in supported.items() if any(abs(v - cand) < 1e-6 for cand in candidates_m)}
    notes = []
    if arithmetic_fit_m is not None:
        notes.append(f'A concordância aritmética com {_fmt(arithmetic_fit_m)} m é ignorada: não constitui prova de leitura.')
    if len(matching) == 1:
        value, ev = next(iter(matching.items()))
        origin = "user_statement" if any(e["kind"] == "user_statement" for e in ev) else "native_text"
        return {"reading": Reading(label=label, value_m=value, origin=origin).model_dump(), "state": "confirmed",
                "reason": f"Confirmado por {', '.join(sorted({e['kind'] for e in ev}))}. " + " ".join(notes)}
    reason = ("Várias confirmações contraditórias." if len(matching) > 1 else "Nenhuma prova independente (ampliação, texto nativo, declaração).") + " " + " ".join(notes)
    return {"reading": Reading(label=label, candidates_m=candidates_m).model_dump(), "state": "indeterminate", "reason": reason.strip(),
            "action": "Ampliar a zona, extrair o texto nativo do PDF ou pedir o valor ao autor da planta."}
