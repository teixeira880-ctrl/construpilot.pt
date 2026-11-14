"""Verificação cruzada entre motores — 14/11 (Martinho): cada resultado CAD é confrontado com uma segunda via de cálculo
independente. Nada aqui altera quantidades: só confirma (ok) ou assinala (aviso) com o porquê, para máxima fiabilidade.

Vias cruzadas:
- unidades do desenho ↔ áreas escritas no próprio desenho (motor de camadas);
- área do contorno do edifício ↔ laje térrea e cobertura (motor de estrutura);
- perímetro do contorno ↔ fachada (altura implícita plausível);
- n.º de pilares (chumbadouros ÷ 4) × dimensões da sapata ↔ volume de betão das sapatas;
- escavação ↔ betão de limpeza + sapatas;
- aço por m² de implantação ↔ gama corrente de pavilhões em pórtico;
- orçamento: Σ(qtd × preço) ↔ total gravado; custo da estrutura por m² ↔ referência CYPE EAM010 (estrutura completa).
"""
import math
import re
import unicodedata

CYPE_EAM010_EUR_M2 = 69.41     # estrutura porticada completa (aço S275 ~32,8 kg/m²), CYPE PT 11/2026 — só referência cruzada
ACO_KG_M2 = (15.0, 60.0)       # gama corrente de pavilhões metálicos em pórtico


def _n(s) -> str:
    return unicodedata.normalize("NFKD", str(s or "")).encode("ascii", "ignore").decode().lower()


def _num(x) -> float:
    try:
        return float(str(x).replace(",", "."))
    except (TypeError, ValueError):
        return 0.0


def _soma(linhas, rx, unit=None) -> float:
    return sum(float(l.get("qty") or 0) for l in linhas if re.search(rx, _n(l.get("designation"))) and (unit is None or l.get("unit") == unit))


def _ok(nome, detalhe):
    return {"verificacao": nome, "estado": "ok", "detalhe": detalhe}


def _aviso(nome, detalhe):
    return {"verificacao": nome, "estado": "aviso", "detalhe": detalhe}


def _perimetro(pts) -> float:
    if not pts or len(pts) < 3:
        return 0.0
    return sum(math.dist(pts[i], pts[(i + 1) % len(pts)]) for i in range(len(pts)))


def verificar(medicao: dict | None, estrutura: dict | None) -> list[dict]:
    med = medicao or {}
    out = []
    unid = str(med.get("unidades") or "")
    if unid:
        nu = _n(unid)
        confirmada = ("coincid" in nu or "confirmadas por" in nu or "confirmees par" in nu or "confirmees" in nu) and "sem area escrita" not in nu
        out.append(_ok("Unidades do desenho ↔ áreas escritas", unid[:220]) if confirmada
                   else _aviso("Unidades do desenho ↔ áreas escritas", "Sem áreas escritas no desenho para confirmar a unidade: confirmar a escala. " + unid[:160]))
    zeros = [l.get("designation") for l in med.get("linhas") or [] if float(l.get("qty") or 0) <= 0]
    if zeros:
        out.append(_aviso("Artigos medidos com quantidade nula", "; ".join(map(str, zeros[:6]))))
    if not estrutura or not estrutura.get("linhas"):
        return out
    L = estrutura["linhas"]
    ed = med.get("edificio") or {}
    area = float(ed.get("area_m2") or (estrutura.get("contorno") or {}).get("area_m2") or 0)
    if area > 0:
        laje = _soma(L, r"laje terrea|massame", "m2")
        if laje:
            d = abs(laje - area) / area
            out.append((_ok if d <= 0.05 else _aviso)("Contorno do edifício ↔ laje térrea", f"contorno {area:.2f} m² · laje {laje:.2f} m² ({d:.1%})"))
        cob = _soma(L, r"cobertura", "m2")
        if cob:
            r = cob / area
            out.append((_ok if 1.0 <= r <= 1.20 else _aviso)("Contorno ↔ cobertura (inclinação + beirados)", f"cobertura/implantação = {r:.3f} (esperado 1,00–1,20)"))
        aco = _soma(L, r"aco s275|aco s355", "kg")
        if aco:
            q = aco / area
            out.append((_ok if ACO_KG_M2[0] <= q <= ACO_KG_M2[1] else _aviso)("Aço da estrutura por m² ↔ gama corrente",
                                                                               f"{q:.1f} kg/m² (gama corrente {ACO_KG_M2[0]:.0f}–{ACO_KG_M2[1]:.0f} kg/m²)"))
    per = _perimetro([tuple(p) for p in ed.get("pontos") or []])
    fach = _soma(L, r"fachada", "m2")
    if per and fach:
        h = fach / per
        out.append((_ok if 2.5 <= h <= 15 else _aviso)("Perímetro ↔ fachada (altura implícita)", f"{fach:.0f} m² / {per:.1f} m = {h:.2f} m"))
    chumb = _soma(L, r"chumbadouro", "un") or _soma(L, r"chumbadouro", "u")
    vs = next((l for l in L if l.get("unit") == "m3" and re.search(r"betao .*sapatas?\b", _n(l.get("designation")))), None)
    if chumb and vs:
        m = re.search(r"(\d+[.,]\d+)\s*[x×]\s*(\d+[.,]\d+)\s*[x×]\s*(\d+[.,]\d+)", str(vs.get("designation")))
        if m:
            pilares = chumb / 4
            v1 = _num(m.group(1)) * _num(m.group(2)) * _num(m.group(3))
            esperado = pilares * v1
            d = abs(esperado - float(vs.get("qty") or 0)) / max(esperado, 1e-9)
            out.append((_ok if d <= 0.02 else _aviso)("Pilares × sapata ↔ betão das sapatas",
                                                      f"{pilares:.0f} pilares × {v1:.3f} m³ = {esperado:.2f} m³ · mapa {vs.get('qty')} m³"))
    esc = _soma(L, r"^escavacao", "m3")
    bet = _soma(L, r"betao .*sapata|betao de limpeza", "m3")
    if esc and bet:
        out.append((_ok if esc >= bet else _aviso)("Escavação ↔ betão enterrado", f"escavação {esc:.2f} m³ ≥ betões {bet:.2f} m³"))
    return out


def verificar_orcamento(rows: list[dict], total_ht: float | None, area_edificio: float | None, coef_venda: float) -> list[dict]:
    out = []
    soma = round(sum(round(float(r.get("qty") or 0) * float(r.get("unit_price_ht") or 0) * (1 - float(r.get("discount_pct") or 0) / 100), 2)
                     for r in rows), 2)
    if total_ht is not None:
        out.append((_ok if abs(soma - float(total_ht)) <= 0.05 else _aviso)("Σ(quantidade × preço) ↔ total gravado",
                                                                            f"{soma:,.2f} € ↔ {float(total_ht):,.2f} €"))
    sem_origem = [r.get("designation") for r in rows if not r.get("price_missing") and not r.get("price_source")]
    if sem_origem:
        out.append(_aviso("Preços sem origem", "; ".join(map(str, sem_origem[:6]))))
    if area_edificio:
        estr = sum(float(r.get("qty") or 0) * float(r.get("unit_price_ht") or 0) for r in rows
                   if re.search(r"aco s275|aco s355|chumbadouro|parafusos m\d+", _n(r.get("designation"))))
        if estr:
            ref = CYPE_EAM010_EUR_M2 * coef_venda
            q = estr / area_edificio
            d = q / ref
            out.append((_ok if 0.6 <= d <= 1.8 else _aviso)("Estrutura €/m² ↔ referência CYPE EAM010 (estrutura completa)",
                                                            f"{q:.2f} €/m² vs referência {ref:.2f} €/m² (razão {d:.2f}; aceitável 0,6–1,8)"))
    return out
