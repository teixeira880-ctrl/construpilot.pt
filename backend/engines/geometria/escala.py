"""Escala por consenso: nenhuma medição sem que fontes independentes concordem.

Fontes possíveis (cada uma dá unidades-do-desenho por metro, `u_por_m`):
  - calibração feita pelo utilizador (duas pontas + valor real) — a mais forte;
  - escala declarada na folha (« 1:50 », « ESC. 1/100 ») — exige saber quantas unidades tem um metro de papel;
  - cotas: comprimento desenhado ÷ valor escrito, para cada cota (mediana robusta, outliers fora);
  - unidades declaradas do DXF (milímetros, metros…);
  - áreas escritas nas divisões ÷ áreas calculadas (√), quando já há divisões.

Estado: « confirmada » (≥ 2 fontes independentes de acordo a 1,5 %), « fonte_unica », « conflito » (fontes em desacordo:
fica a mais forte, assinalada a vermelho) ou « desconhecida ». Vários `1:x` diferentes na mesma folha não bloqueiam:
cada candidato é testado contra as cotas e as áreas.
"""
from __future__ import annotations

import math
import re
from statistics import median

ESCALA_TXT = re.compile(r"(?:ESC(?:ALA)?\.?|ECH(?:ELLE)?\.?|SCALE)?\s*1\s*[:/]\s*(\d{1,4})\b", re.I)
TOL_ACORDO = .015
PESO = {"utilizador": 5.0, "cotas": 3.0, "unidades_cad": 3.0, "areas_escritas": 2.0, "declarada": 2.0}


def escalas_declaradas(textos: list[dict]) -> list[int]:
    """Denominadores « 1:x » plausíveis (1:1 a 1:2000) presentes no texto da folha, sem repetição, por ordem."""
    vistos = []
    for t in textos or []:
        for m in ESCALA_TXT.finditer(str(t.get("text") or "")):
            d = int(m.group(1))
            if 1 <= d <= 2000 and d not in vistos:
                vistos.append(d)
    return vistos


def candidato_cotas(cotas: list[dict]) -> dict | None:
    """Cada cota dá comprimento_u ÷ valor_m. Mediana com rejeição dos desvios > 3 % (cotas falsas, texto mal lido)."""
    razoes = []
    for c in cotas or []:
        v = c.get("valor_m") if c.get("valor_m") is not None else c.get("value_m")
        L = c.get("comprimento_u")
        if L is None and all(k in c for k in ("x1", "y1", "x2", "y2")):
            L = math.dist((c["x1"], c["y1"]), (c["x2"], c["y2"]))
        if v and L and v > .05 and L > 0:
            razoes.append(L / v)
    if not razoes:
        return None
    m = median(razoes)
    bons = [r for r in razoes if abs(r - m) / m <= .03]
    if not bons:
        return None
    return {"fonte": "cotas", "u_por_m": median(bons), "n": len(bons), "rejeitadas": len(razoes) - len(bons)}


def candidato_areas(divisoes_u2: list[tuple[float, float]]) -> dict | None:
    """Pares (área desenhada em u², área escrita em m²) → √(u²/m²). Exige ≥ 2 divisões concordantes."""
    razoes = [math.sqrt(a_u / a_m) for a_u, a_m in divisoes_u2 if a_u > 0 and a_m and a_m > .5]
    if len(razoes) < 2:
        return None
    m = median(razoes)
    bons = [r for r in razoes if abs(r - m) / m <= .03]
    if len(bons) < 2:
        return None
    return {"fonte": "areas_escritas", "u_por_m": median(bons), "n": len(bons), "rejeitadas": len(razoes) - len(bons)}


def consenso(candidatos: list[dict]) -> dict:
    """Agrupa os candidatos que concordam a 1,5 % e escolhe o grupo mais apoiado (fontes distintas, depois peso)."""
    cands = [c for c in candidatos if c and c.get("u_por_m") and math.isfinite(c["u_por_m"]) and c["u_por_m"] > 0]
    if not cands:
        return {"estado": "desconhecida", "u_por_m": None, "fontes": [], "candidatos": [], "mensagem": "Escala desconhecida: calibrar com uma cota conhecida."}
    grupos = []
    for c in sorted(cands, key=lambda c: -PESO.get(c["fonte"], 1)):
        for g in grupos:
            if abs(c["u_por_m"] - g["ref"]) / g["ref"] <= TOL_ACORDO:
                g["membros"].append(c)
                break
        else:
            grupos.append({"ref": c["u_por_m"], "membros": [c]})

    def apoio(g):
        fontes = {m["fonte"] for m in g["membros"]}
        return (len(fontes), sum(PESO.get(f, 1) for f in fontes))
    grupos.sort(key=apoio, reverse=True)
    melhor = grupos[0]
    fontes = sorted({m["fonte"] for m in melhor["membros"]}, key=lambda f: -PESO.get(f, 1))
    # valor: o da fonte mais forte do grupo (a calibração do utilizador ou as cotas fixam o número; as outras confirmam)
    principal = max(melhor["membros"], key=lambda m: PESO.get(m["fonte"], 1))
    outros = [g for g in grupos[1:] if any(PESO.get(m["fonte"], 1) >= 2 for m in g["membros"])]
    if len(fontes) >= 2 and not outros:
        estado, msg = "confirmada", f"Escala confirmada por {len(fontes)} fontes independentes."
    elif len(fontes) >= 2:
        estado, msg = "confirmada", "Escala confirmada; há outra escala na folha (pormenor a outra escala?) — verificar a vista."
    elif outros:
        estado, msg = "conflito", "Fontes de escala em desacordo: medições a confirmar antes de orçamentar."
    else:
        estado, msg = "fonte_unica", f"Escala de uma só fonte ({fontes[0]}): confirmar com uma cota conhecida."
    return {"estado": estado, "u_por_m": principal["u_por_m"], "fontes": fontes, "mensagem": msg,
            "candidatos": [{**{k: v for k, v in c.items() if k != "u_por_m"}, "u_por_m": round(c["u_por_m"], 6)} for c in cands],
            "desvio_max_pct": round(max(abs(m["u_por_m"] - principal["u_por_m"]) / principal["u_por_m"] for m in melhor["membros"]) * 100, 3)}


def candidatos_declarados(denominadores: list[int], u_por_m_papel: float | None) -> list[dict]:
    """1:x → u_por_m = (unidades por metro de papel) ÷ x. Sem conhecer o papel (digitalização sem dpi), nada."""
    if not u_por_m_papel:
        return []
    return [{"fonte": "declarada", "u_por_m": u_por_m_papel / d, "denominador": d} for d in denominadores]


PT_POR_M_PAPEL = 72 / .0254


def px_por_m_papel(dpi: float | None) -> float | None:
    return dpi / .0254 if dpi else None
