"""Auditoria V2 — desvio de preço e contas do scanner calculados de forma determinística."""


def _num(v):
    if v is None or isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    import re as _re
    c = _re.sub(r"[^\d,.\-]", "", str(v))
    if "," in c and "." in c:
        c = c.replace(".", "").replace(",", ".") if c.rfind(",") > c.rfind(".") else c.replace(",", "")
    elif "," in c:
        c = c.replace(",", ".")
    try:
        return float(c)
    except ValueError:
        return None


def ground_quote_analysis(result: dict, reference: dict | None) -> dict:
    """Auditoria V2 (07/11/2026) : a IA lê o orçamento, mas NUNCA produz o desvio
    nem o veredicto de preço. Sem referência válida → «comparação indisponível».
    Com referência (estimativa de projeto) → desvio calculado aqui, de forma
    determinística, com a base de comparação indicada. Contas das linhas
    (qtd × PU = total) também recontroladas aqui."""
    result = dict(result or {})
    ai_delta = result.pop("delta_vs_reference_pct", None)
    checks, mismatches = [], 0
    sum_lines = 0.0
    for i, ln in enumerate(result.get("lines") or []):
        q, pu, tot = _num(ln.get("quantity")), _num(ln.get("unit_price")), _num(ln.get("total"))
        if tot is not None:
            sum_lines += tot
        if q is None or pu is None or tot is None:
            continue
        exp = round(q * pu, 2)
        diff = round(abs(exp - tot), 2)
        ok = diff <= max(0.02, abs(exp) * 0.005)
        ln["computed_total"] = exp
        ln["arith_ok"] = ok
        if not ok:
            mismatches += 1
            checks.append({"line": i, "label": ln.get("label"), "expected": exp, "file": tot, "diff": diff})
    result["arithmetic"] = {"mismatches": mismatches, "checks": checks,
                            "sum_lines": round(sum_lines, 2)}
    total_ht = _num(result.get("total_ht"))
    ref_total = _num((reference or {}).get("total_avg"))
    if ref_total and total_ht:
        result["delta_vs_reference_pct"] = round((total_ht - ref_total) / ref_total * 100, 1)
        result["reference_basis"] = {"type": "project_estimate", "reference_total": ref_total,
                                     "quote_total_ht": total_ht,
                                     "label": "Total s/ IVA do orçamento vs estimativa do projeto associado"}
        d = result["delta_vs_reference_pct"]
        result["verdict"] = "bas" if d < -15 else "correct" if d <= 15 else "eleve" if d <= 35 else "tres_eleve"
    else:
        result["delta_vs_reference_pct"] = None
        result["reference_basis"] = None
        result["verdict"] = "sem_referencia"
        result["verdict_label"] = ("Comparação de preço indisponível : nenhuma referência equivalente "
                                   "(mesmo artigo, unidade, região e data) foi associada a este orçamento.")
    if ai_delta is not None:
        result["ai_delta_discarded"] = True
    return result
