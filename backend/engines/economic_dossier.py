"""Dossier económico de uma obra tradicional (alvenaria / betão), no espírito do dossier da conta CLT
(bim_studio.clt_economics + clt_study): quanto vai custar, quanto se vende, a margem, o planeamento e os cenários.

Dados da empresa (cada valor traz a sua origem: « empresa » = introduzido pela empresa, « hipotese » = valor por defeito
a substituir antes de usar o resultado para orçamentar):
  * duas bibliotecas de preços: VENDA (preço ao cliente, nas linhas do orçamento) e COMPRA (preço de custo) ;
  * recursos: mão de obra por função (custo/hora carregado), veículos (custo/dia + consumo L/100 km), máquinas
    (custo/hora ou /dia), combustível (€/L), custos de estrutura (%), parâmetros de obra (horas/dia, km/dia…).

Custo da obra = custos diretos das linhas (preço de compra; senão hipótese pela margem-alvo)
              + estaleiro: equipa no local × duração (só a parte de mão de obra não incluída nos custos diretos),
                enquadramento (engenheiro / diretor de obra), veículos (dias + gasóleo), máquinas
              + custos de estrutura (% do custo).
Margem = venda s/ IVA − custo total. Determinístico, sem IA.
"""
from __future__ import annotations

import math
import re
import unicodedata

# ------------------------------------------------------------------ recursos por defeito (hipóteses a substituir)
DEFAULT_RESOURCES = {
    "PT": [
        {"id": "trolha", "kind": "mao_de_obra", "name": "Pedreiro / trolha", "unit": "h", "cost": 15.5},
        {"id": "servente", "kind": "mao_de_obra", "name": "Servente", "unit": "h", "cost": 11.5},
        {"id": "encarregado", "kind": "mao_de_obra", "name": "Encarregado", "unit": "h", "cost": 18.0},
        {"id": "condutor", "kind": "mao_de_obra", "name": "Condutor / manobrador", "unit": "h", "cost": 14.0},
        {"id": "engenheiro", "kind": "mao_de_obra", "name": "Engenheiro / diretor de obra", "unit": "h", "cost": 30.0},
        {"id": "carrinha", "kind": "veiculo", "name": "Carrinha de obra", "unit": "dia", "cost": 32.0, "consumption_l_100km": 9.0},
        {"id": "camiao", "kind": "veiculo", "name": "Camião basculante", "unit": "dia", "cost": 95.0, "consumption_l_100km": 28.0},
        {"id": "giratoria", "kind": "maquina", "name": "Mini-giratória", "unit": "dia", "cost": 160.0},
        {"id": "betoneira", "kind": "maquina", "name": "Betoneira / pequeno equipamento", "unit": "dia", "cost": 12.0},
    ],
    "FR": [
        {"id": "trolha", "kind": "mao_de_obra", "name": "Maçon", "unit": "h", "cost": 32.0},
        {"id": "servente", "kind": "mao_de_obra", "name": "Manœuvre", "unit": "h", "cost": 26.0},
        {"id": "encarregado", "kind": "mao_de_obra", "name": "Chef de chantier", "unit": "h", "cost": 38.0},
        {"id": "condutor", "kind": "mao_de_obra", "name": "Chauffeur / conducteur d'engins", "unit": "h", "cost": 30.0},
        {"id": "engenheiro", "kind": "mao_de_obra", "name": "Ingénieur / conducteur de travaux", "unit": "h", "cost": 55.0},
        {"id": "carrinha", "kind": "veiculo", "name": "Fourgon de chantier", "unit": "dia", "cost": 45.0, "consumption_l_100km": 9.0},
        {"id": "camiao", "kind": "veiculo", "name": "Camion benne", "unit": "dia", "cost": 140.0, "consumption_l_100km": 28.0},
        {"id": "giratoria", "kind": "maquina", "name": "Mini-pelle", "unit": "dia", "cost": 220.0},
        {"id": "betoneira", "kind": "maquina", "name": "Bétonnière / petit matériel", "unit": "dia", "cost": 15.0},
    ],
}
DEFAULT_PARAMS = {
    "PT": {"fuel_price_l": 1.65, "overhead_pct": 12.0, "hours_per_day": 8.0, "km_per_day": 60.0, "labour_share_pct": 40.0,
           "target_margin_pct": 20.0, "team": {"trolha": 2, "servente": 1, "encarregado": 0.5}, "supervision_h_week": 6.0,
           "vehicles": {"carrinha": 1}, "machines": {"betoneira": 1}, "truck_days_pct": 10.0, "digger_days_pct": 5.0},
    "FR": {"fuel_price_l": 1.75, "overhead_pct": 15.0, "hours_per_day": 7.0, "km_per_day": 60.0, "labour_share_pct": 45.0,
           "target_margin_pct": 20.0, "team": {"trolha": 2, "servente": 1, "encarregado": 0.5}, "supervision_h_week": 6.0,
           "vehicles": {"carrinha": 1}, "machines": {"betoneira": 1}, "truck_days_pct": 10.0, "digger_days_pct": 5.0},
}


def defaults(country: str = "PT") -> dict:
    c = "FR" if str(country).upper() == "FR" else "PT"
    return {"resources": [dict(r, origin="hipotese") for r in DEFAULT_RESOURCES[c]],
            "params": dict(DEFAULT_PARAMS[c], origin="hipotese")}


def merge(saved: dict | None, country: str = "PT") -> dict:
    """Recursos da empresa sobre os valores por defeito (o que a empresa introduziu fica « empresa »)."""
    d = defaults(country)
    if not saved:
        return d
    by = {r["id"]: r for r in d["resources"]}
    for r in saved.get("resources") or []:
        if isinstance(r, dict) and r.get("id"):
            by[r["id"]] = {**by.get(r["id"], {}), **r, "origin": "empresa"}
    params = dict(d["params"])
    for k, v in (saved.get("params") or {}).items():
        if v is not None:
            params[k] = v
    if saved.get("params"):
        params["origin"] = "empresa"
    return {"resources": list(by.values()), "params": params}


# ------------------------------------------------------------------ custo das linhas (biblioteca de compra)
def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", str(s or "")).encode("ascii", "ignore").decode().lower()
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]+", " ", s)).strip()


def _sim(a: str, b: str) -> float:
    A, B = set(_norm(a).split()), set(_norm(b).split())
    if not A or not B:
        return 0.0
    return len(A & B) / len(A | B)


def cost_lookup(purchase: list[dict]):
    """Função designação/unidade → (custo unitário, origem, referência) a partir da biblioteca de compra."""
    items = [p for p in purchase or [] if float(p.get("cost_price_ht") or 0) > 0]

    def f(designation: str, unit: str):
        best, score = None, 0.0
        for p in items:
            if _norm(p.get("unit")) and _norm(unit) and _norm(p.get("unit")) != _norm(unit):
                continue
            s_ = _sim(designation, p.get("designation"))
            if s_ > score:
                best, score = p, s_
        if best is not None and score >= 0.6:
            return float(best["cost_price_ht"]), "@lib", best.get("designation", "")
        return None
    return f


def _lots(lines: list[dict]) -> list[tuple[str, list[dict]]]:
    out, cur = [], None
    has_sections = any(l.get("kind") == "section" for l in lines)
    for l in lines:
        k = l.get("kind")
        if k == "section":
            cur = (str(l.get("title") or "—").strip(), [])
            out.append(cur)
        elif k in (None, "line"):
            if has_sections:
                if cur is None:
                    cur = ("—", [])
                    out.append(cur)
                cur[1].append(l)
            else:
                name = str(l.get("category") or "Geral").strip() or "Geral"
                grp = next((g for g in out if g[0] == name), None)
                if grp is None:
                    grp = (name, [])
                    out.append(grp)
                grp[1].append(l)
    return [g for g in out if g[1]]


# ------------------------------------------------------------------ textos (PT / FR)
_TX = {
    "PT": {"quote_cost": "custo indicado no orçamento", "lib": "biblioteca de compra", "hyp": "HIPÓTESE (venda − margem-alvo {:.0f} %)",
           "sup": "Enquadramento — {}", "use": "{} — utilização", "day": "dia", "month": "mês", "fuel_v": "{} — gasóleo ({:.0f} km/dia, {:.0f} L/100 km)",
           "truck": "{} — evacuação e transporte", "fuel": "{} — gasóleo", "dig": "{} — terraplenagens", "base": "Base",
           "s_mat": "Materiais +10 %", "s_lab": "Mão de obra +10 %", "s_fuel": "Gasóleo +20 %", "s_disc": "Desconto comercial −5 %",
           "h_lines": "{} linha(s) sem preço de compra: custo estimado pela margem-alvo de {:.0f} % — introduza os preços de compra na biblioteca de compra.",
           "h_res": "Custos horários, veículos e máquinas por defeito (hipótese): substitua-os pelos custos reais da empresa.",
           "h_par": "Parâmetros por defeito: gasóleo {:.2f} €/L, {:.0f} km/dia, {:.0f} h/dia, custos de estrutura {:.0f} %, mão de obra = {:.0f} % dos custos diretos.",
           "h_team": "Equipa no local: {} → {} dias úteis ({:.1f} semanas)."},
    "FR": {"quote_cost": "coût indiqué dans le devis", "lib": "bibliothèque d'achat", "hyp": "HYPOTHÈSE (vente − marge cible {:.0f} %)",
           "sup": "Encadrement — {}", "use": "{} — utilisation", "day": "jour", "month": "mois", "fuel_v": "{} — gazole ({:.0f} km/jour, {:.0f} L/100 km)",
           "truck": "{} — évacuation et transport", "fuel": "{} — gazole", "dig": "{} — terrassements", "base": "Base",
           "s_mat": "Matériaux +10 %", "s_lab": "Main-d'œuvre +10 %", "s_fuel": "Gazole +20 %", "s_disc": "Remise commerciale −5 %",
           "h_lines": "{} ligne(s) sans prix d'achat : coût estimé par la marge cible de {:.0f} % — saisissez les prix d'achat dans la bibliothèque d'achat.",
           "h_res": "Coûts horaires, véhicules et engins par défaut (hypothèse) : remplacez-les par les coûts réels de l'entreprise.",
           "h_par": "Paramètres par défaut : gazole {:.2f} €/L, {:.0f} km/jour, {:.0f} h/jour, frais généraux {:.0f} %, main-d'œuvre = {:.0f} % des déboursés secs.",
           "h_team": "Équipe sur site : {} → {} jours ouvrés ({:.1f} semaines)."},
}


# ------------------------------------------------------------------ cálculo
def compute(doc: dict, company: dict, purchase: list[dict] | None = None, country: str = "PT") -> dict:
    X = _TX["FR" if str(country).upper() == "FR" else "PT"]
    res = {r["id"]: r for r in company["resources"]}
    P = company["params"]
    tm = float(P.get("target_margin_pct") or 20) / 100
    look = cost_lookup(purchase or [])
    lines_out, lots_out = [], []
    hyp_lines = 0
    for lot, rows in _lots(doc.get("lines") or []):
        ls, lc = 0.0, 0.0
        for l in rows:
            q = float(l.get("qty") or 0)
            pu = float(l.get("unit_price_ht") or 0) * (1 - float(l.get("discount_pct") or 0) / 100)
            sale = q * pu
            cu, origin, ref = None, "", ""
            if float(l.get("cost_price_ht") or 0) > 0:
                cu, origin, ref = float(l["cost_price_ht"]), X["quote_cost"], ""
            else:
                hit = look(l.get("designation", ""), l.get("unit", ""))
                if hit:
                    cu, origin, ref = hit
                    origin = X["lib"]
            if cu is None:
                cu, origin = pu * (1 - tm), X["hyp"].format(tm * 100)
                hyp_lines += 1
            cost = q * cu
            lines_out.append({"lot": lot, "designation": l.get("designation", ""), "unit": l.get("unit", ""), "qty": q, "pu": pu,
                              "cu": round(cu, 2), "sale": round(sale, 2), "cost": round(cost, 2), "origin": origin, "ref": ref})
            ls += sale
            lc += cost
        lots_out.append({"lot": lot, "sale": round(ls, 2), "direct": round(lc, 2)})
    sale = sum(l["sale"] for l in lots_out)
    direct = sum(l["direct"] for l in lots_out)
    # ---- equipa, duração e estaleiro
    hpd = float(P.get("hours_per_day") or 8)
    team = {k: float(v) for k, v in (P.get("team") or {}).items() if k in res and float(v) > 0}
    team_rate = sum(res[k]["cost"] * n for k, n in team.items()) or 1.0
    labour_cost = direct * float(P.get("labour_share_pct") or 40) / 100           # parte de mão de obra nos custos diretos
    days = max(1, math.ceil(labour_cost / (team_rate * hpd)))
    weeks = days / 5
    site = []
    sup = res.get("engenheiro")
    if sup:
        h = float(P.get("supervision_h_week") or 0) * weeks
        site.append({"item": X["sup"].format(sup["name"]), "qty": round(h, 1), "unit": "h", "pu": sup["cost"], "total": round(h * sup["cost"], 2),
                     "origin": sup.get("origin", "")})
    fuel = float(P.get("fuel_price_l") or 1.65)
    km = float(P.get("km_per_day") or 0)
    for vid, n in (P.get("vehicles") or {}).items():
        v = res.get(vid)
        if not v:
            continue
        d_ = days * float(n)
        site.append({"item": X["use"].format(v["name"]), "qty": d_, "unit": X["day"], "pu": v["cost"], "total": round(d_ * v["cost"], 2),
                     "origin": v.get("origin", "")})
        litres = d_ * km * float(v.get("consumption_l_100km") or 0) / 100
        site.append({"item": X["fuel_v"].format(v["name"], km, float(v.get("consumption_l_100km") or 0)),
                     "qty": round(litres, 1), "unit": "L", "pu": fuel, "total": round(litres * fuel, 2), "origin": P.get("origin", "")})
    truck = res.get("camiao")
    if truck and float(P.get("truck_days_pct") or 0) > 0:
        d_ = max(1, round(days * float(P["truck_days_pct"]) / 100))
        litres = d_ * km * float(truck.get("consumption_l_100km") or 0) / 100
        site += [{"item": X["truck"].format(truck["name"]), "qty": d_, "unit": X["day"], "pu": truck["cost"],
                  "total": round(d_ * truck["cost"], 2), "origin": truck.get("origin", "")},
                 {"item": X["fuel"].format(truck["name"]), "qty": round(litres, 1), "unit": "L", "pu": fuel, "total": round(litres * fuel, 2),
                  "origin": P.get("origin", "")}]
    dig = res.get("giratoria")
    if dig and float(P.get("digger_days_pct") or 0) > 0:
        d_ = max(1, round(days * float(P["digger_days_pct"]) / 100))
        site.append({"item": X["dig"].format(dig["name"]), "qty": d_, "unit": X["day"], "pu": dig["cost"], "total": round(d_ * dig["cost"], 2),
                     "origin": dig.get("origin", "")})
    for mid, n in (P.get("machines") or {}).items():
        m = res.get(mid)
        if not m:
            continue
        d_ = days * float(n)
        site.append({"item": f"{m['name']}", "qty": d_, "unit": {"dia": X["day"], "h": "h", "km": "km", "mes": X["month"]}.get(m.get("unit"), X["day"]), "pu": m["cost"], "total": round(d_ * m["cost"], 2),
                     "origin": m.get("origin", "")})
    site_total = sum(x["total"] for x in site)
    overhead = (direct + site_total) * float(P.get("overhead_pct") or 0) / 100
    cost_total = direct + site_total + overhead
    margin = sale - cost_total
    for lt in lots_out:
        share = lt["direct"] / direct if direct else 0
        lt["cost"] = round(lt["direct"] + (site_total + overhead) * share, 2)
        lt["margin"] = round(lt["sale"] - lt["cost"], 2)
        lt["margin_pct"] = round(lt["margin"] / lt["sale"] * 100, 1) if lt["sale"] else 0.0

    fuel_cost = sum(x["total"] for x in site if x["unit"] == "L")
    ovh = float(P.get("overhead_pct") or 0) / 100

    def scen(label, dm=0.0, dl=0.0, df=0.0, ds=0.0):
        mat = direct - labour_cost
        c2 = (mat * (1 + dm) + labour_cost * (1 + dl) + (site_total - fuel_cost) + fuel_cost * (1 + df)) * (1 + ovh)
        s2 = sale * (1 + ds)
        return {"label": label, "cost": round(c2, 2), "sale": round(s2, 2), "margin": round(s2 - c2, 2),
                "margin_pct": round((s2 - c2) / s2 * 100, 1) if s2 else 0.0}
    base_check = scen(X["base"])
    scenarios = [base_check, scen(X["s_mat"], dm=0.10), scen(X["s_lab"], dl=0.10), scen(X["s_fuel"], df=0.20), scen(X["s_disc"], ds=-0.05)]
    # planeamento: capítulos em sequência com sobreposição de 20 %, duração proporcional ao custo direto
    plan, t0 = [], 0.0
    for lt in lots_out:
        dur = max(1.0, days * (lt["direct"] / direct if direct else 1 / max(1, len(lots_out))))
        plan.append({"lot": lt["lot"], "start": round(t0, 1), "days": round(dur, 1)})
        t0 += dur * 0.8
    total_days = max((p["start"] + p["days"] for p in plan), default=days)
    hyps = []
    if hyp_lines:
        hyps.append(X["h_lines"].format(hyp_lines, tm * 100))
    if any(r.get("origin") == "hipotese" for r in company["resources"]):
        hyps.append(X["h_res"])
    if P.get("origin") == "hipotese":
        hyps.append(X["h_par"].format(fuel, km, hpd, float(P.get('overhead_pct') or 0), float(P.get('labour_share_pct') or 40)))
    hyps.append(X["h_team"].format(", ".join(f"{n:g} × {res[k]['name']}" for k, n in team.items()), days, weeks))
    return {"title": doc.get("title") or "", "client": (doc.get("client") or {}).get("name") or doc.get("client_name") or "",
            "number": doc.get("number") or "", "sale": round(sale, 2), "direct": round(direct, 2), "site": site,
            "site_total": round(site_total, 2), "overhead": round(overhead, 2), "overhead_pct": float(P.get("overhead_pct") or 0),
            "cost": round(cost_total, 2), "margin": round(margin, 2), "margin_pct": round(margin / sale * 100, 1) if sale else 0.0,
            "target_margin_pct": tm * 100, "lots": lots_out, "lines": lines_out, "days": days, "total_days": round(total_days, 1),
            "team": team, "resources": company["resources"], "params": P, "scenarios": scenarios, "plan": plan,
            "hypotheses": hyps, "labour_cost": round(labour_cost, 2), "hyp_lines": hyp_lines}
