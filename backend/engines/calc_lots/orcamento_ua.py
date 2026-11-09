"""Кошторисна оцінка (Україна) — quantidades tiradas do modelo estrutural e da envolvente, preços com fonte, ПДВ 20 %.

Os preços unitários estão em UAH SEM ПДВ. Cada linha diz de onde vem o preço:
  • "джерело" = preço publicado (fornecedor / estatística) com data;
  • "орієнтир" = valor de referência ConstruPilot a confirmar com orçamentos locais (nunca apresentado como cotação).
O ПДВ (податок на додану вартість) é a taxa base de 20 % (Податковий кодекс України, ст. 193). Câmbio: taxa oficial do NBU.
"""
from __future__ import annotations

import math

PDV = 0.20
EUR_UAH = 50.6455                     # курс НБУ на 09.11.2026 (index.minfin.com.ua / bank.gov.ua)
DATA_PRECOS = "09.11.2026"

# (descrição, unidade, preço UAH sem ПДВ, fonte, tipo)
PRECOS = {
    "escavacao":    ("Розробка ґрунту котлована з вивезенням", "м³", 450, "орієнтир ConstruPilot", "орієнтир"),
    "betao_c25":    ("Бетон C20/25 (B25) з доставкою", "м³", 3125, "dbn.co.ua, Київ 2026: 2 900–3 350 грн/м³ з доставкою (середнє)", "джерело"),
    "betao_c30":    ("Бетон C25/30 (B30) з доставкою", "м³", 3375, "dbn.co.ua, Київ 2026: 3 100–3 650 грн/м³ з доставкою (середнє)", "джерело"),
    "aco":          ("Арматура A500C Ø12–16", "т", 50000, "Метінвест-СМЦ Київ, 09.11.2026: 50 000 грн/т", "джерело"),
    "mo_betao":     ("Бетонні роботи (опалубка, армування, укладання)", "м³", 2200, "орієнтир ConstruPilot", "орієнтир"),
    "imperm":       ("Гідроізоляція і утеплення XPS стін підвалу", "м²", 950, "орієнтир ConstruPilot", "орієнтир"),
    "clt":          ("Панелі Rezult CLT (виготовлення, ЧПК-обробка, доставка)", "м³", round(650 * EUR_UAH), "ринок ЄС ≥ 500 €/м³ (Holzkurier, 2025) + обробка й доставка → 650 €/м³; запитати ціну Rezult", "орієнтир"),
    "clt_montagem": ("Монтаж CLT (кран, кріплення, ущільнення стиків)", "м³", 6500, "орієнтир ConstruPilot", "орієнтир"),
    "fachada":      ("Фасадна система: мінвата + вітрозахист + оздоблення", "м²", 1900, "орієнтир ConstruPilot", "орієнтир"),
    "cobertura":    ("Плоска покрівля: пароізоляція, XPS, ухил, мембрана ПВХ, гравій", "м²", 3200, "орієнтир ConstruPilot", "орієнтир"),
    "janelas":      ("Вікна та двері тераси (енергоефективні, з монтажем)", "м²", 9500, "орієнтир ConstruPilot", "орієнтир"),
    "bomba_calor":  ("Тепловий насос повітря–вода з монтажем", "кВт", 21000, "орієнтир ConstruPilot", "орієнтир"),
}
TAXA_ACO = {"sapata": 60, "muro": 80, "laje": 110}          # кг арматури на м³ (орієнтир)


def _comp(pts):
    return sum(math.hypot(b[0] - a[0], b[1] - a[1]) for a, b in zip(pts[:-1], pts[1:]))


def quantidades(m: dict, elementos: list, potencia_kw: float | None) -> dict:
    q = {k: 0.0 for k in PRECOS}
    aco = 0.0
    for s in m.get("sapatas_continuas") or []:
        v = _comp(s["pontos"]) * s["b_m"] * s["h_m"]
        q["betao_c25"] += v
        aco += v * TAXA_ACO["sapata"]
    for s in m.get("sapatas") or []:
        v = s["b_m"] * s["l_m"] * s["h_m"]
        q["betao_c25"] += v
        aco += v * TAXA_ACO["sapata"]
    prof = 0.0
    per_cave = 0.0
    for mu in m.get("muros") or []:
        L = _comp(mu["pontos"])
        h = mu["cota_topo_m"] - mu["cota_base_m"]
        if mu.get("material") == "clt":
            q["clt"] += L * h * mu["espessura_m"] * 0.9                      # −10 % vãos
        else:
            v = L * h * mu["espessura_m"]
            q["betao_c25"] += v
            aco += v * TAXA_ACO["muro"]
            if mu["pontos"][0] == mu["pontos"][-1]:
                per_cave = max(per_cave, L)
                prof = max(prof, -mu["cota_base_m"])
    for lj in m.get("lajes") or []:
        A = abs(lj["x1_m"] - lj["x0_m"]) * abs(lj["y1_m"] - lj["y0_m"])
        if lj.get("tipo") == "clt":
            q["clt"] += A * float(lj.get("espessura_m") or sum(lj.get("camadas_mm") or [0]) / 1000)
        elif lj.get("tipo") in ("laje_ba", "laje_terrea"):
            v = A * float(lj["espessura_m"])
            q["betao_c30" if lj.get("tipo") == "laje_ba" else "betao_c25"] += v
            aco += v * TAXA_ACO["laje"] * (1 if lj.get("tipo") == "laje_ba" else 0.4)
    q["aco"] = aco / 1000
    q["mo_betao"] = q["betao_c25"] + q["betao_c30"]
    q["clt_montagem"] = q["clt"]
    if per_cave and prof:
        x0 = min(g["pos_m"] for g in m["grelhas_x"]); x1 = max(g["pos_m"] for g in m["grelhas_x"])
        y0 = min(g["pos_m"] for g in m["grelhas_y"]); y1 = max(g["pos_m"] for g in m["grelhas_y"])
        q["escavacao"] = (x1 - x0 + 2.0) * (y1 - y0 + 2.0) * (prof + 0.2)
        q["imperm"] = per_cave * prof
    for e in elementos:
        if e["tipo"] == "parede":
            q["fachada"] += e["area_m2"]
        elif e["tipo"] in ("cobertura", "sotao"):
            q["cobertura"] += e["area_m2"]
        elif e["tipo"] in ("janela", "porta", "claraboia"):
            q["janelas"] += e["area_m2"]
    if potencia_kw:
        q["bomba_calor"] = math.ceil(potencia_kw)
    return {k: round(v, 2) for k, v in q.items() if v > 0}


def orcamento(m: dict, elementos: list, potencia_kw: float | None, area_m2: float | None, precos: dict | None = None) -> dict:
    P = dict(PRECOS)
    for k, v in (precos or {}).items():                               # preços do utilizador / fabricante substituem os de referência
        if k in P and v:
            d, u, _, _, _ = P[k]
            P[k] = (d, u, float(v), "ціна користувача", "джерело")
    q = quantidades(m, elementos, potencia_kw)
    linhas = []
    for k, qt in q.items():
        d, u, pu, fonte, tipo = P[k]
        linhas.append({"chave": k, "desc": d, "un": u, "qt": qt, "pu": pu, "total": qt * pu, "fonte": fonte, "tipo": tipo})
    sem = sum(x["total"] for x in linhas)
    pdv = sem * PDV
    com = sem + pdv
    grupos = {"Фундаменти й підвал (з/б)": ("escavacao", "betao_c25", "betao_c30", "aco", "mo_betao", "imperm"),
              "Каркас Rezult CLT": ("clt", "clt_montagem"), "Оболонка (фасад, покрівля, вікна)": ("fachada", "cobertura", "janelas"),
              "Опалення": ("bomba_calor",)}
    por_grupo = {g: sum(x["total"] for x in linhas if x["chave"] in ks) for g, ks in grupos.items()}
    return {"linhas": linhas, "sem_pdv": sem, "pdv": pdv, "com_pdv": com, "eur_com_pdv": com / EUR_UAH, "eur_sem_pdv": sem / EUR_UAH,
            "por_m2_com_pdv": com / area_m2 if area_m2 else None, "grupos": por_grupo, "taxa_pdv": PDV, "cambio": EUR_UAH, "data": DATA_PRECOS,
            "parte_fonte": sum(x["total"] for x in linhas if x["tipo"] == "джерело") / sem if sem else 0}
