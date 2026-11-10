"""Україна / Ukraine — теплотехніка, тепловтрати, навантаження та несучі конструкції (ConstruPilot).

Детерміновані розрахунки за нормами України (без ШІ):
  • ДБН В.2.6-31:2021 «Теплова ізоляція та енергоефективність будівель» — Rq,min за температурними зонами I / II (табл. 1),
    допустимий перепад Δθ між повітрям і поверхнею (табл. 3), внутрішні температури (табл. Б.2);
  • ДСТУ-Н Б В.1.1-27:2010 «Будівельна кліматологія» — розрахункова температура зовнішнього повітря (найхолодніша п'ятиденка 0,92);
  • ДБН В.1.2-2:2006 «Навантаження і впливи» — сніг Sm = γfm·S0·C, вітер Wm = γfm·W0·C (додаток Е, обласні центри);
  • ДСТУ-Н Б EN 1992 / 1995 / 1997 (Єврокоди, прийняті в Україні) — несучі конструкції через модуль gros_oeuvre з робочими кресленнями.
Результат: розрахункова записка PDF українською з резюме англійською + креслення ГО-01…ГО-05 (якщо задано модель конструкцій).
Довідкові кліматичні дані обласних центрів — перевіряти за чинними нормами для конкретної ділянки.
"""
from __future__ import annotations

import math
import re

from . import graficos as G
from . import isolamento, rendu

# ------------------------------------------------------------------------------------------------ кліматичні дані (обласні центри)
# θe: найхолодніша п'ятиденка 0,92 (ДСТУ-Н Б В.1.1-27:2010, довідкові значення); ГД: градусо-доби опалювального періоду (база 18 °C, довідково);
# зона: температурна зона ДБН В.2.6-31:2021 (карта дод. А — перевірити); S0, W0: ДБН В.1.2-2:2006 дод. Е (Па).
CLIMA = {
    "kyiv": ("Київ", "Kyiv", -22, 3572, "I", 1550, 370), "lviv": ("Львів", "Lviv", -19, 3474, "I", 1310, 520),
    "kharkiv": ("Харків", "Kharkiv", -23, 3799, "I", 1600, 430), "odesa": ("Одеса", "Odesa", -18, 2805, "II", 880, 460),
    "dnipro": ("Дніпро", "Dnipro", -23, 3325, "I", 1340, 470), "zaporizhzhia": ("Запоріжжя", "Zaporizhzhia", -22, 3202, "II", 1110, 460),
    "vinnytsia": ("Вінниця", "Vinnytsia", -21, 3610, "I", 1360, 470), "uzhhorod": ("Ужгород", "Uzhhorod", -18, 2657, "II", 1340, 370),
    "chernihiv": ("Чернігів", "Chernihiv", -23, 3767, "I", 1720, 410), "poltava": ("Полтава", "Poltava", -23, 3721, "I", 1450, 470),
    "ivano_frankivsk": ("Івано-Франківськ", "Ivano-Frankivsk", -20, None, "I", 1410, 500), "zhytomyr": ("Житомир", "Zhytomyr", -22, 3610, "I", 1460, 460),
    "cherkasy": ("Черкаси", "Cherkasy", -22, None, "I", 1520, 420), "rivne": ("Рівне", "Rivne", -21, 3555, "I", 1320, 520),
    "ternopil": ("Тернопіль", "Ternopil", -21, 3515, "I", 1390, 520), "lutsk": ("Луцьк", "Lutsk", -20, 3403, "I", 1240, 480),
    "khmelnytskyi": ("Хмельницький", "Khmelnytskyi", -21, None, "I", 1340, 500), "chernivtsi": ("Чернівці", "Chernivtsi", -20, None, "I", 1320, 500),
    "sumy": ("Суми", "Sumy", -24, None, "I", 1670, 420), "mykolaiv": ("Миколаїв", "Mykolaiv", -20, 2904, "II", 870, 470),
    "kherson": ("Херсон", "Kherson", -19, 2906, "II", 760, 480), "kropyvnytskyi": ("Кропивницький", "Kropyvnytskyi", -22, 3515, "I", 1230, 410),
}
CIDADES = list(CLIMA)
# середня температура січня, °C (кліматичні норми, довідково) — для перевірки конденсації (Глейзер) у найхолоднішому місяці
T_JAN = {"kyiv": -3.5, "lviv": -3.0, "kharkiv": -5.0, "odesa": -0.5, "dnipro": -3.9, "zaporizhzhia": -2.8, "vinnytsia": -4.3, "uzhhorod": -1.5,
         "chernihiv": -5.0, "poltava": -4.6, "ivano_frankivsk": -3.6, "zhytomyr": -4.4, "cherkasy": -4.2, "rivne": -3.8, "ternopil": -4.3,
         "lutsk": -3.5, "khmelnytskyi": -4.6, "chernivtsi": -3.2, "sumy": -5.8, "mykolaiv": -1.8, "kherson": -1.4, "kropyvnytskyi": -4.0}

# ДБН В.2.6-31:2021 табл. 1 — Rq,min, м²·К/Вт (житлові та громадські будинки)
RQMIN = {"parede": {"I": 4.00, "II": 3.50}, "cobertura": {"I": 7.00, "II": 6.00}, "sotao": {"I": 6.00, "II": 5.50},
         "pavimento_ext": {"I": 5.00, "II": 4.00}, "janela": {"I": 0.90, "II": 0.70}, "claraboia": {"I": 0.80, "II": 0.70},
         "porta": {"I": 0.70, "II": 0.60}}
# табл. 3 — допустимий перепад Δθint-si,max, °C: (житлові/дошкільні/освітні/лікувальні, інші громадські)
DTMAX = {"parede": (4.0, 5.0), "cobertura": (3.0, 4.0), "sotao": (3.0, 4.0), "pavimento_ext": (2.0, 2.5)}
# табл. Б.2 — внутрішня температура та вологість
INTERIOR = {"residencial": (20, 0.55), "publico": (20, 0.50), "escola_saude": (22, 0.50), "desporto": (18, 0.50)}
ALFA_I, ALFA_E = 8.7, 23.0
RSI, RSE = 1 / ALFA_I, 1 / ALFA_E
EL_UK = {"parede": "Зовнішня стіна", "cobertura": "Суміщене покриття", "sotao": "Горищне перекриття", "pavimento_ext": "Перекриття над холодним підвалом / проїздом",
         "janela": "Вікна (світлопрозорі)", "claraboia": "Зенітні ліхтарі", "porta": "Зовнішні двері", "pavimento_solo": "Підлога по ґрунту"}
EL_EN = {"parede": "External wall", "cobertura": "Flat roof", "sotao": "Attic floor", "pavimento_ext": "Floor over unheated space",
         "janela": "Windows", "claraboia": "Skylights", "porta": "External doors", "pavimento_solo": "Ground floor"}
# Матеріали (довідкові розрахункові λ, Вт/(м·К), умови експлуатації Б; μ — коефіцієнт опору паропроникненню). Використовувати λ з декларацій.
MAT = {
    "gazobeton_d400": ("Газобетон D400", 0.12, 8), "gazobeton_d500": ("Газобетон D500", 0.14, 7), "gazobeton_d600": ("Газобетон D600", 0.16, 6),
    "tsehla_povnotila": ("Цегла керамічна повнотіла", 0.81, 9), "tsehla_pustotila": ("Цегла керамічна пустотіла", 0.58, 8),
    "keramoblok": ("Керамічний блок 380/440", 0.17, 6), "zalizobeton": ("Залізобетон", 2.04, 80), "bloky_betonni": ("Бетонні блоки", 0.93, 15),
    "mineralna_vata": ("Мінеральна вата (фасадна)", 0.041, 1), "mineralna_vata_pokr": ("Мінеральна вата (покрівельна)", 0.042, 1),
    "pinopolistyrol": ("Пінополістирол (EPS)", 0.041, 40), "pinopolistyrol_grafit": ("Пінополістирол графітовий", 0.033, 40),
    "xps": ("Екструдований пінополістирол (XPS)", 0.037, 150), "pir": ("Поліізоціанурат (PIR)", 0.024, 60),
    "shtukaturka_tsem": ("Цементно-піщана штукатурка", 0.93, 10), "shtukaturka_gips": ("Гіпсова штукатурка", 0.35, 10),
    "tonka_shtukaturka": ("Тонкошарова фасадна штукатурка", 0.70, 25), "gipsokarton": ("Гіпсокартон", 0.21, 10),
    "styazhka": ("Цементна стяжка", 0.93, 20), "derevyna": ("Деревина (сосна)", 0.18, 50), "clt": ("Панель CLT", 0.13, 50),
    "keramzyt": ("Керамзитовий гравій", 0.21, 3),
}
MEMB = {"paroizolyatsiya": ("Пароізоляція (Sd ≥ 18 м)", 18.0), "paroizolyatsiya_al": ("Пароізоляція бітумна з алюмінієвою фольгою (Sd ≈ 1500 м)", 1500.0), "vitrozakhyst": ("Вітрозахисна мембрана (Sd ≤ 0,2 м)", 0.2),
        "pokrivelna_membrana": ("Покрівельна мембрана ПВХ/ТПО", 15.0)}

UK = {"note": "Розрахункова записка", "page": "сторінка", "ref": "Номер", "synthese": "Зведення перевірок", "conformes": "відповідають",
      "non_conformes": "не відповідають", "a_verifier": "перевірити", "verdict_ok": "ВІДПОВІДАЄ", "verdict_ko": "НЕ ВІДПОВІДАЄ",
      "verdict_na": "ПЕРЕВІРИТИ", "verdict_glob_ok": "Усі розраховані перевірки виконуються", "verdict_glob_ko": "Принаймні одна перевірка не виконується",
      "verdict_glob_na": "Невідповідностей немає — є пункти для перевірки", "head": ["Норма", "Вимога", "Значення", "Результат"],
      "hyp": "Припущення / для перевірки", "brand_sub": "Цифрове проєктне бюро"}


def _c(x, n=2):
    return f"{x:,.{n}f}".replace(",", " ").replace(".", ",")


def clima(cidade: str) -> dict:
    k = (cidade or "").lower().replace("-", "_").replace(" ", "_").replace("kiev", "kyiv")
    if k not in CLIMA:
        raise ValueError(f"місто / city {cidade!r} невідоме ({', '.join(CIDADES)}); або задайте theta_e, zona, s0_pa, w0_pa")
    uk, en, te, gd, zona, s0, w0 = CLIMA[k]
    return {"chave": k, "nome": uk, "name": en, "theta_e": te, "gd": gd, "zona": zona, "s0_pa": s0, "w0_pa": w0, "t_jan": T_JAN.get(k)}


def _clima_p(p):
    c = clima(p["cidade"]) if p.get("cidade") else {"chave": None, "nome": p.get("local") or "—", "name": p.get("local") or "—", "theta_e": None,
                                                      "gd": None, "zona": None, "s0_pa": None, "w0_pa": None}
    c.setdefault("t_jan", None)
    for k in ("theta_e", "gd", "zona", "s0_pa", "w0_pa", "t_jan"):
        if p.get(k) is not None:
            c[k] = p[k]
    if c["theta_e"] is None or c["zona"] is None:
        raise ValueError("вкажіть місто (cidade) або theta_e і zona (I / II)")
    return c


# ------------------------------------------------------------------------------------------------ огороджувальні конструкції
def elemento(e: dict, c: dict, ti: float, phi_i: float, uso: str) -> dict:
    tipo = e.get("tipo") or "parede"
    nome = e.get("nome") or EL_UK.get(tipo, tipo)
    camadas, R = [], 0.0
    if e.get("camadas"):
        for k in e["camadas"]:
            code, ep = k["material"], float(k.get("espessura_mm") or 0)
            if code in MEMB:
                nm, sd = MEMB[code]
                camadas.append({"nom": nm, "ep": 0, "lam": None, "R": 0.0, "Sd": sd})
                continue
            if code not in MAT:
                raise ValueError(f"матеріал {code!r} невідомий ({', '.join(list(MAT) + list(MEMB))})")
            nm, lam, mu = MAT[code]
            lam = float(k.get("lambda") or lam)
            r = ep / 1000 / lam
            camadas.append({"nom": nm, "ep": ep, "lam": lam, "R": r, "Sd": mu * ep / 1000})
            R += r
        Rt = RSI + R + RSE
    elif e.get("R") is not None:
        Rt = float(e["R"])
    elif e.get("U") is not None:
        Rt = 1 / float(e["U"])
    else:
        raise ValueError(f"{nome}: задайте шари (camadas) або R / U")
    # pontes térmicas explícitas (método bet_clt_ua.engine.assembly): U_ef = U + (Σ L·ψ + Σ n·χ) / A
    pl, pp = e.get("pontes_lineares") or [], e.get("pontes_pontuais") or []
    area = float(e.get("area_m2") or 0)
    pontes = sum(float(x["comprimento_m"]) * float(x["psi"]) for x in pl) + sum(int(x["n"]) * float(x["chi"]) for x in pp)
    u_ef = None
    if (pl or pp) and area > 0:
        u_ef = 1 / Rt + pontes / area
        if u_ef <= 0:
            raise ValueError(f"{nome}: U efetivo não positivo — rever as áreas de referência das pontes térmicas")
    zona = c["zona"]
    rq = RQMIN.get(tipo, {}).get(zona)
    ctl = []
    if rq:
        ctl.append({"ref": f"ДБН В.2.6-31:2021 табл. 1 (зона {zona})", "exigence": f"R∑ ≥ Rq,min = {_c(rq)} м²·К/Вт", "valeur": f"{_c(Rt)} м²·К/Вт",
                    "ok": Rt >= rq - 1e-9, "taux": rq / Rt})
        if u_ef is not None:
            ctl.append({"ref": "Приведений опір з тепловими містками (ψ, χ)", "exigence": f"Rпр = 1/Uеф ≥ {_c(rq)} м²·К/Вт",
                        "valeur": f"{_c(1 / u_ef)} м²·К/Вт (Uеф {_c(u_ef, 3)})", "ok": 1 / u_ef >= rq - 1e-9, "taux": rq * u_ef})
    dt = None
    if tipo in DTMAX:
        lim = DTMAX[tipo][0 if uso in ("residencial", "escola_saude") else 1]
        dt = (ti - c["theta_e"]) / (Rt * ALFA_I)
        ctl.append({"ref": "ДБН В.2.6-31:2021 табл. 3", "exigence": f"Δθ ≤ {_c(lim, 1)} °C", "valeur": f"{_c(dt, 1)} °C", "ok": dt <= lim + 1e-9, "taux": dt / lim})
    gl = None
    b = float(e.get("b") if e.get("b") is not None else (0.6 if tipo in ("pavimento_ext", "pavimento_solo") else 1.0))
    if len(camadas) >= 2:
        tj = c.get("t_jan")
        te_g = tj if tj is not None else c["theta_e"]
        te_g = ti - b * (ti - te_g)                       # простір, що не опалюється: еквівалентна температура
        gl = isolamento.glaser(camadas, ti, te_g, phi_i, 0.85, RSE)
        ctl.append({"ref": f"Конденсація в товщі (метод Глейзера, θ = {te_g:.1f} °C — " + ("середня січня" if tj is not None else "розрахункова θe") + ")",
                    "exigence": "немає зони конденсації", "ok": not gl["condensation"] if not gl["condensation"] else None,
                    "valeur": "немає" if not gl["condensation"] else
                    f"можлива конденсація: {str(gl['plan']).replace('após ', 'після ')} ({gl['g_jour']:.1f} г/м² на добу) — перевірити вологісний режим за ДСТУ Б В.2.6-189"})
    return {"nome": nome, "tipo": tipo, "area_m2": area, "R": Rt, "U": u_ef if u_ef is not None else 1 / Rt, "pontes_explicitas": u_ef is not None, "rq": rq, "dt": dt, "camadas": camadas,
            "glaser": gl, "controles": ctl, "ok": all(x["ok"] is not False for x in ctl), "b": b}


def navantazhennya(c: dict, inclinacao_graus: float = 0.0, termo_anos: int = 50, altitude_m: float | None = None,
                   coef_vento: float = 0.7) -> dict:
    """Сніг і вітер за ДБН В.1.2-2:2006 (граничні розрахункові значення)."""
    if c.get("s0_pa") is None:
        return {}
    gfm = {50: 1.0, 100: 1.14}.get(int(termo_anos), 1.0)
    a = float(inclinacao_graus or 0)
    mu = 1.0 if a <= 25 else (max(0.0, (60 - a) / 35) if a < 60 else 0.0)
    calt = 1.0 if not altitude_m or altitude_m < 500 else 1.4 * altitude_m / 1000 + 0.3
    sm = gfm * c["s0_pa"] * mu * calt / 1000
    se = 0.49 * c["s0_pa"] * mu * calt / 1000
    wm = gfm * c["w0_pa"] * coef_vento / 1000
    return {"gfm": gfm, "mu": mu, "calt": calt, "sm_kpa": sm, "se_kpa": se, "wm_kpa": wm, "s0": c["s0_pa"], "w0": c["w0_pa"]}


def calcular(p: dict) -> dict:
    c = _clima_p(p)
    uso = p.get("uso") or "residencial"
    ti, phi_i = INTERIOR.get(uso, INTERIOR["residencial"])
    ti = float(p.get("theta_i") or ti)
    els = [elemento(e, c, ti, phi_i, uso) for e in (p.get("elementos") or [])]
    hyp = ["кліматичні дані обласного центру (ДСТУ-Н Б В.1.1-27:2010, ДБН В.1.2-2:2006 дод. Е) — для конкретної ділянки перевірити за чинними нормами",
           "температурна зона за картою дод. А ДБН В.2.6-31:2021 — перевірити для конкретного населеного пункту",
           "розрахункові λ матеріалів — довідкові (умови експлуатації Б); у проєкті використовувати значення з декларацій виробників / ДСТУ Б В.2.6-189",
           f"Rsi = 1/{_c(ALFA_I, 1)}, Rse = 1/{_c(ALFA_E, 0)} м²·К/Вт; перевірка конденсації методом Глейзера при розрахунковій θe (консервативно)"]
    # тепловтрати
    out = {"clima": c, "uso": uso, "ti": ti, "elementos": els, "hipoteses": hyp}
    if els and any(e["area_m2"] for e in els):
        ht = sum(e["area_m2"] * e["U"] * e["b"] for e in els)
        dpt = float(p.get("pontes_termicas_w_m2k") if p.get("pontes_termicas_w_m2k") is not None else 0.05)
        a_env = sum(e["area_m2"] for e in els if not e["pontes_explicitas"])      # elementos com ψ / χ explícitos: sem margem global
        ht += dpt * a_env
        vol = float(p.get("volume_m3") or 0)
        n = float(p.get("renovacoes_h") if p.get("renovacoes_h") is not None else 0.5)
        eta = float(p.get("recuperacao_calor") or 0)
        hv = 0.34 * n * vol * (1 - eta)
        dT = ti - c["theta_e"]
        phi = (ht + hv) * dT
        out.update(ht=ht, hv=hv, dpt=dpt, phi_w=phi, a_env=a_env, n=n, eta=eta, vol=vol)
        hyp.append(f"теплові містки: надбавка ΔU = {_c(dpt)} Вт/(м²·К) до всієї оболонки (спрощено); вентиляція {_c(n)} год⁻¹"
                   + (f", рекуперація η = {_c(eta)}" if eta else ""))
        area = float(p.get("area_aquecida_m2") or 0)
        if c.get("gd") and area:
            q = (ht + hv) * c["gd"] * 24 / 1000
            out.update(q_kwh=q, q_kwh_m2=q / area, area=area)
            hyp.append("річна потреба в теплі = (H_T + H_V) × ГД × 24 — без сонячних і внутрішніх теплонадходжень (верхня оцінка); "
                       "енергетичний клас визначається за Методикою (наказ Мінрегіону) та ДСТУ EN ISO 52016")
        out["potencia_kw"] = phi / 1000 * 1.1
    out["cargas"] = navantazhennya(c, p.get("inclinacao_cobertura_graus") or 0, p.get("termo_servico_anos") or 50, p.get("altitude_m"))
    return out


# ------------------------------------------------------------------------------------------------ записка
def note(p: dict) -> dict:
    import json

    import pymupdf
    r = calcular(p)
    c, els = r["clima"], r["elementos"]
    lingua = (p.get("lingua") or "uk").lower()
    from . import lingua_ucrania as LU
    L = {"pt": LU.tr, "en": LU.tr_en}.get(lingua, lambda x: x)
    DEEP = {"pt": LU.deep, "en": LU.deep_en}.get(lingua)
    if lingua in ("pt", "en"):
        c = dict(c, nome=c["name"])
    W = rendu.mm
    proj = p.get(f"projeto_{(p.get('lingua') or 'uk').lower()}") or p.get("projeto") or "Будинок"
    blocs = []
    kpis = [{"label": "Місто / City", "value": c["nome"], "unit": f"{c['name']} · зона {c['zona']}"},
            {"label": "θe розрахункова / design", "value": f"{c['theta_e']:g}", "unit": "°C"}]
    if r.get("phi_w"):
        kpis.append({"label": "Тепловтрати / heat loss", "value": _c(r["phi_w"] / 1000, 1), "unit": "кВт / kW"})
    if r.get("q_kwh_m2"):
        kpis.append({"label": "Потреба в теплі / heating need", "value": _c(r["q_kwh_m2"], 0), "unit": "кВт·год/м² рік"})
    if els:
        kpis.append({"label": "Огородження ДБН В.2.6-31", "value": "відповідає" if all(e["ok"] for e in els) else "НЕ відповідає",
                     "ok": all(e["ok"] for e in els)})
    if r["cargas"]:
        kpis.append({"label": "Сніг Sm / snow", "value": _c(r["cargas"]["sm_kpa"]), "unit": "кПа"})
    blocs.append(("kpis", kpis))
    # English summary
    en = [f"Location: {c['name']} (Ukraine), temperature zone {c['zona']} (DBN V.2.6-31:2021), design outdoor temperature {c['theta_e']:g} °C"
          + (f", {c['gd']} heating degree-days" if c.get("gd") else "") + "."]
    if els:
        en.append("Envelope: " + "; ".join(f"{EL_EN.get(e['tipo'], e['tipo'])} R = {e['R']:.2f} m²K/W"
                                           + (f" (min {e['rq']:.2f})" if e["rq"] else "") + (" OK" if e["ok"] else " NOT COMPLIANT") for e in els) + ".")
    if r.get("phi_w"):
        en.append(f"Design heat loss {r['phi_w'] / 1000:.1f} kW (EN 12831 simplified), recommended heat generator ≈ {r['potencia_kw']:.1f} kW"
                  + (f"; annual heating need ≈ {r['q_kwh']:,.0f} kWh ({r['q_kwh_m2']:.0f} kWh/m²·yr, upper bound without gains)" if r.get("q_kwh") else "") + ".")
    if r["cargas"]:
        k = r["cargas"]
        en.append(f"Loads DBN V.1.2-2:2006: snow S0 = {k['s0']} Pa → Sm = {k['sm_kpa']:.2f} kPa; wind W0 = {k['w0']} Pa → Wm ≈ {k['wm_kpa']:.2f} kPa.")
    blocs += [("h2", "Summary (English)"), ("p", " ".join(en))]
    # 1. клімат
    blocs += [("h2", "1. Кліматичні параметри"),
              ("table", ["Параметр", "Значення", "Джерело"],
               [["Розрахункова температура зовнішнього повітря θe", f"{c['theta_e']:g} °C", "ДСТУ-Н Б В.1.1-27:2010 (п'ятиденка 0,92)"],
                ["Градусо-доби опалювального періоду", f"{c['gd']}" if c.get("gd") else "—", "довідково (база 18 °C)"],
                ["Температурна зона", c["zona"], "ДБН В.2.6-31:2021, дод. А"],
                ["Внутрішня температура / вологість", f"{r['ti']:g} °C / {INTERIOR.get(r['uso'], (0, 0.55))[1] * 100:.0f} %", "ДБН В.2.6-31:2021, табл. Б.2"],
                ["Характеристичне снігове навантаження S0", f"{c['s0_pa']} Па" if c.get("s0_pa") else "—", "ДБН В.1.2-2:2006, дод. Е"],
                ["Характеристичний тиск вітру W0", f"{c['w0_pa']} Па" if c.get("w0_pa") else "—", "ДБН В.1.2-2:2006, дод. Е"]],
               [78 * W, 34 * W, 68 * W])]
    # 2. огородження
    if els:
        rows = [[e["nome"], _c(e["R"]), _c(e["rq"]) if e["rq"] else "—", _c(e["U"], 3), "відповідає" if e["ok"] else "НЕ відповідає"] for e in els]
        blocs += [("h2", "2. Теплотехнічний розрахунок огороджувальних конструкцій"),
                  ("p", "Опір теплопередачі R∑ = Rsi + Σ(d/λ) + Rse порівнюється з мінімально допустимим Rq,min (ДБН В.2.6-31:2021, табл. 1); "
                        "перевіряються перепад температур Δθ (табл. 3) і відсутність конденсації в товщі конструкції."),
                  ("table", ["Конструкція", "R∑, м²·К/Вт", "Rq,min", "U, Вт/(м²·К)", "Статус"], rows, [70 * W, 24 * W, 20 * W, 26 * W, 40 * W]),
                  ("chart", G.barres_h([(L(e["nome"])[:30], e["R"] / e["rq"] if e["rq"] else None) for e in els], L("R∑ / Rq,min (≥ 1,0 — відповідає)"),
                                       None, ref=(1.0, "Rq,min"), dec=2), None)]
        for e in els:
            if e["camadas"]:
                cr = [[k["nom"], _c(k["ep"], 0) if k["ep"] else "—", _c(k["lam"], 3) if k["lam"] else "—", _c(k["R"], 3) if k["R"] else "—",
                       _c(k["Sd"], 2)] for k in e["camadas"]]
                blocs += [("h2", f"{e['nome']}"), ("table", ["Шар (зсередини назовні)", "d, мм", "λ, Вт/(м·К)", "R, м²·К/Вт", "Sd, м"], cr,
                                                           [76 * W, 20 * W, 26 * W, 28 * W, 24 * W])]
            blocs.append(("controls", e["controles"]))
    # 3. тепловтрати
    if r.get("phi_w"):
        parts = [(e["nome"][:28], e["area_m2"] * e["U"] * e["b"] * (r["ti"] - c["theta_e"]) / 1000) for e in els if e["area_m2"]]
        parts += [("Теплові містки", r["dpt"] * r["a_env"] * (r["ti"] - c["theta_e"]) / 1000), ("Вентиляція", r["hv"] * (r["ti"] - c["theta_e"]) / 1000)]
        blocs += [("h2", "3. Розрахункові тепловтрати та потреба в теплі"),
                  ("p", f"H_T = Σ A·U·b + ΔU·A = {_c(r['ht'], 1)} Вт/К; H_V = 0,34·n·V·(1 − η) = {_c(r['hv'], 1)} Вт/К; "
                        f"Φ = (H_T + H_V)·(θi − θe) = {_c(r['phi_w'] / 1000, 2)} кВт при θe = {c['theta_e']:g} °C. "
                        f"Рекомендована потужність теплогенератора ≈ {_c(r['potencia_kw'], 1)} кВт (+10 %)."
                        + (f" Річна потреба ≈ {_c(r['q_kwh'], 0)} кВт·год ({_c(r['q_kwh_m2'], 0)} кВт·год/м² на рік, {_c(r['area'], 0)} м²)." if r.get("q_kwh") else "")),
                  ("chart", G.donut([(L(n), v) for n, v in parts if v > 0], L("Розподіл тепловтрат, кВт"), _c(r["phi_w"] / 1000, 1), L("кВт")), None)]
    # 4. навантаження
    if r["cargas"]:
        k = r["cargas"]
        blocs += [("h2", "4. Снігове та вітрове навантаження (ДБН В.1.2-2:2006)"),
                  ("table", ["Величина", "Значення"],
                   [["S0 (характеристичне)", f"{k['s0']} Па"], ["γfm (термін експлуатації)", _c(k["gfm"])], ["μ (форма покрівлі)", _c(k["mu"])],
                    ["Calt (висота)", _c(k["calt"])], ["Sm = γfm·S0·μ·Calt (граничне)", f"{_c(k['sm_kpa'])} кПа"],
                    ["Se = 0,49·S0·C (експлуатаційне)", f"{_c(k['se_kpa'])} кПа"], ["W0 (характеристичне)", f"{k['w0']} Па"],
                    ["Wm ≈ γfm·W0·C (C = 0,7, будинок до 10 м)", f"{_c(k['wm_kpa'])} кПа"]], [90 * W, 50 * W])]
    # 5. несучі конструкції
    planos_pdf, go = None, None
    if p.get("modelo_estrutural"):
        from . import gros_oeuvre
        import copy
        mod = json.loads(p["modelo_estrutural"]) if isinstance(p["modelo_estrutural"], str) else copy.deepcopy(p["modelo_estrutural"])
        if p.get(f"projeto_{lingua}"):
            mod["projeto"] = p[f"projeto_{lingua}"]            # título dos planos na língua do dossier
        if lingua == "en":
            mod = LU.modelo_en(mod)
            for g, nm in zip(mod.get("grelhas_y") or [], "ABCDEFGHIJ"):     # eixos em letras latinas seguidas (А Б В Г Д → A B C D E)
                if not str(g.get("nome", "")).isdigit():
                    g["nome"] = nm
        mod.setdefault("local", f"{c['nome']} ({c['name']})")
        for lj in mod.get("lajes") or []:
            if lj.get("tipo") == "clt":
                for k_src, k_dst in (("produto_clt", "produto"), ("especie_clt", "especie"), ("fogo_min", "fogo_min")):
                    if p.get(k_src):
                        lj[k_dst] = p[k_src]
        if r["cargas"]:
            for v in mod.get("vigas") or []:
                if v.get("piso") == "cobertura" and v.get("q_kn_m") is None and v.get("largura_influencia_m"):
                    v["q_kn_m"] = round(r["cargas"]["sm_kpa"] * float(v["largura_influencia_m"]), 2)
                    v.setdefault("psi2", 0.0)
            for lj in mod.get("lajes") or []:          # neve ДБН В.1.2-2; o gros_oeuvre toma máx(neve, sobrecarga de cobertura / terraço)
                if (lj.get("piso") == "cobertura" or lj.get("cobertura_terraco")) and lj.get("q_kn_m2") is None and lj.get("neve_kn_m2") is None:
                    lj["neve_kn_m2"] = round(r["cargas"]["sm_kpa"], 2)
        go = gros_oeuvre.calcular(mod, lingua={"pt": None, "en": "en"}.get(lingua, "uk"))
        planos_pdf = go["planos_pdf"]
        ver = go["verificacao"]
        rows = [[e["tipo"], e["ref"], e["seccao"], f"{e['taxa'] * 100:.0f} %" if e["taxa"] is not None else "—", "відповідає" if e["ok"] else "НЕ відповідає"]
                for e in ver["elementos"]]
        tr = gros_oeuvre._dic("uk")         # (em PT, a tradução final LU.deep repõe o português)
        tok = gros_oeuvre._TR_CV.set(tr)
        try:
            rows = [[gros_oeuvre._tr(str(x)) for x in rw] for rw in rows]
            aj = [gros_oeuvre._tr(a) for a in ver["ajustes"]]
            hip_go = [gros_oeuvre._tr(h) for h in ver["hipoteses"]]
        finally:
            gros_oeuvre._TR_CV.reset(tok)
        r["hipoteses"] += hip_go
        blocs += [("h2", "5. Несучі конструкції (ДСТУ-Н Б EN 1992 / 1995 / 1997)"),
                  ("p", f"Перевірено {len(ver['elementos'])} елементів; снігове навантаження на покриття Sm = "
                        f"{_c(r['cargas']['sm_kpa']) if r['cargas'] else '—'} кПа. Робочі креслення ГО-01…ГО-05 (масштаб 1:{go['escala']}, {go['formato']}) додані до записки."),
                  ("table", ["Тип", "Марка", "Прийнятий переріз", "Викор.", "Статус"], rows[:80], [28 * W, 16 * W, 80 * W, 16 * W, 30 * W])]
        if aj:
            blocs += [("h2", "Автоматичні коригування перерізів"), ("hyp", aj)]
        en.append(f"Structure: {len(ver['elementos'])} elements checked (Eurocodes adopted in Ukraine), {len(ver['ajustes'])} section adjustments, "
                  f"dimensioned drawings GO-01…GO-05 at 1:{go['escala']} attached.")
        blocs[2] = ("p", " ".join(en))
    # 6. кошторисна оцінка з ПДВ 20 %
    orc = None
    if go and p.get("orcamento") is not False:
        from . import orcamento_ua as OU
        orc = OU.orcamento(go["modelo"], [e for e in (p.get("elementos") or [])], r.get("potencia_kw"), r.get("area"), p.get("precos"))
        rows = [[x["desc"], x["un"], _c(x["qt"], 1), _c(x["pu"], 0), _c(x["total"], 0), "✓ " + x["fonte"] if x["tipo"] == "джерело" else "≈ " + x["fonte"]]
                for x in orc["linhas"]]
        rows += [["Разом без ПДВ", "", "", "", _c(orc["sem_pdv"], 0), ""],
                 [f"ПДВ {orc['taxa_pdv'] * 100:.0f} % (ПКУ, ст. 193)", "", "", "", _c(orc["pdv"], 0), ""],
                 ["РАЗОМ З ПДВ", "", "", "", _c(orc["com_pdv"], 0), f"≈ {_c(orc['eur_com_pdv'], 0)} € (НБУ {orc['cambio']:g} грн/€, {orc['data']})"]]
        blocs += [("h2", "6. Кошторисна оцінка (несучі конструкції, оболонка, опалення) з ПДВ 20 %"),
                  ("kpis", [{"label": "Без ПДВ / excl. VAT", "value": _c(orc["sem_pdv"] / 1e6, 2), "unit": "млн грн"},
                            {"label": "ПДВ 20 % / VAT", "value": _c(orc["pdv"] / 1e6, 2), "unit": "млн грн"},
                            {"label": "З ПДВ / incl. VAT", "value": _c(orc["com_pdv"] / 1e6, 2), "unit": f"млн грн ≈ {_c(orc['eur_com_pdv'] / 1000, 0)} тис. €"}]
                   + ([{"label": "На 1 м² опалюваної площі", "value": _c(orc["por_m2_com_pdv"], 0), "unit": "грн/м² з ПДВ"}] if orc["por_m2_com_pdv"] else [])),
                  ("table", ["Позиція", "Од.", "К-сть", "Ціна, грн", "Сума, грн", "Джерело ціни"], rows, [52 * W, 10 * W, 14 * W, 16 * W, 20 * W, 58 * W]),
                  ("chart", G.donut([(L(g), v / 1e6) for g, v in orc["grupos"].items() if v > 0], L("Структура вартості, млн грн без ПДВ"),
                                    _c(orc["sem_pdv"] / 1e6, 2), L("млн")), None),
                  ("p", "Кількості обчислені з розрахункової моделі (бетон, арматура за питомими витратами, об'єм CLT, площі оболонки). Ціни без ПДВ: "
                        "«✓» — опубліковані ціни постачальників із датою, «≈» — орієнтири ConstruPilot, які слід замінити комерційними пропозиціями "
                        "(зокрема ціну Rezult CLT). Не включено: внутрішнє оздоблення, інженерні мережі (крім теплового насоса), благоустрій, проєктні роботи.")]
        en.append(f"Cost estimate (structure, envelope, heat pump): {orc['sem_pdv']:,.0f} UAH excl. VAT + VAT 20 % = {orc['com_pdv']:,.0f} UAH "
                  f"(≈ {orc['eur_com_pdv']:,.0f} € at NBU {orc['cambio']:g} UAH/€).")
        blocs[2] = ("p", " ".join(en))
    blocs += [("h2", "Припущення / для перевірки"), ("hyp", r["hipoteses"] + (["перерізи несучих конструкцій — попередній розрахунок, підлягає перевірці "
                                                                               "інженером-конструктором; ДБН В.1.2-14 (надійність) і ДБН В.2.1-10 (основи)"] if go else []))]
    titre = f"Україна / Ukraine — {proj} · {c['nome']} / {c['name']}"
    sub = f"Теплотехніка, тепловтрати, навантаження та несучі конструкції · ДБН / ДСТУ · {c['name']}, Ukraine"
    foot = "ConstruPilot — розрахунок детермінованими модулями; підлягає перевірці відповідальним проєктувальником."
    if DEEP:
        blocs = [b if b[0] == "chart" else DEEP(b) for b in blocs]
        titre, sub, foot = L(titre), L(sub), L(foot)
        r["hipoteses"] = DEEP(r["hipoteses"])
        pdf = rendu.build_pdf(titre, sub, blocs, footer=foot, lang=LU.EN_RENDU if lingua == "en" else None)
    else:
        pdf = rendu.build_pdf(titre, sub, blocs, footer=foot, lang=UK)
    d = pymupdf.open(stream=pdf, filetype="pdf")
    n_nota = len(d)
    extra = p.get("paginas_extra_pdf")                     # p.ex. renders 3D (PDF) inseridos depois da nota
    renders = p.get("renders")
    if renders is None and go and p.get("render", True) is not False:
        renders = gerar_renders(go["modelo"], p.get("render_opcoes"))
    if renders:
        extra = pagina_renders(renders, L, extra)
        if not p.get("capa_imagem"):
            p = dict(p, capa_imagem=renders[0][1])
    if extra:
        d.insert_pdf(pymupdf.open(stream=extra, filetype="pdf"))
        n_nota = len(d)
    if planos_pdf:
        d.insert_pdf(pymupdf.open(stream=planos_pdf, filetype="pdf"))
    out = d.tobytes(garbage=3, deflate=True)
    if p.get("premium", True):
        from . import premium as PR
        emp = PR.marca(p.get("empresa"))
        idx = []
        for i, pg in enumerate(pymupdf.open(stream=pdf, filetype="pdf")):
            for ln in pg.get_text().splitlines():
                if re.match(r"^[1-9]\. [А-ЯІЇЄҐA-Z]", ln) and not any(ln.strip()[:70] == t for t, _ in idx):
                    idx.append((ln.strip()[:70], i + 2))
        if extra:
            idx.append(("Візуалізації 3D / 3D views", len(pymupdf.open(stream=pdf, filetype="pdf")) + 2))
        if planos_pdf:
            for j, pg in enumerate(pymupdf.open(stream=planos_pdf, filetype="pdf")):
                t0 = next((ln for ln in pg.get_text().splitlines() if ln.startswith("GO-")), f"GO-{j + 1:02d}")
                idx.append((t0[:70], n_nota + j + 2))
        kp = [("Місто / City", c["nome"], f"{c['name']} · зона {c['zona']}"), ("θe розрахункова", f"{c['theta_e']:g} °C", "ДСТУ-Н Б В.1.1-27")]
        if r.get("phi_w"):
            kp.append(("Тепловтрати / heat loss", f"{_c(r['phi_w'] / 1000, 1)} кВт", "EN 12831 (спрощено)"))
        if go:
            kp.append(("Конструкції / structure", "OK ✓" if go["verificacao"]["conforme"] else "перевірити",
                       f"{len(go['verificacao']['elementos'])} ел., {len(go['verificacao']['ajustes'])} коригув."))
        if els:
            kp.append(("Оболонка ДБН В.2.6-31", "OK ✓" if all(e["ok"] for e in els) else "посилити", "Rq,min зона " + str(c["zona"])))
        if orc:
            kp += [("Вартість з ПДВ / incl. VAT", f"{_c(orc['com_pdv'] / 1e6, 2)} млн", "грн"), ("≈ EUR з ПДВ", f"{_c(orc['eur_com_pdv'] / 1000, 0)} тис.", "€ (курс НБУ)")]
            if orc["por_m2_com_pdv"]:
                kp.append(("На 1 м²", f"{_c(orc['por_m2_com_pdv'], 0)}", "грн/м² з ПДВ"))
        from datetime import date
        capa = {"titulo": proj, "subtitulo": "Розрахунок за нормами України · Calculation to Ukrainian norms",
                "local": f"{c['name']}, Україна" if DEEP else f"{c['nome']} / {c['name']}, Україна",
                "data": date.today().strftime("%d.%m.%Y"), "kpis": kp, "indice": idx,
                "miniatura_pagina": p.get("miniatura_pagina", n_nota + 2 if planos_pdf else None) if not p.get("capa_imagem") else None}
        if DEEP:
            capa = DEEP(capa)
        capa["capa_imagem"] = p.get("capa_imagem")
        out = PR.embelezar(out, capa, emp, n_nota, tr=L)
    d = pymupdf.open(stream=out, filetype="pdf")
    return {"titre": titre, "pdf": out, "png": d[0].get_pixmap(dpi=110).tobytes("png"), "r": r, "go": go, "resumo_en": " ".join(en), "orcamento": orc}


def exemplo_kyiv() -> dict:  # noqa: D401
    """Будинок 10 × 12 м, газобетон D400 375 мм + мінвата 100 мм, Київ — приклад для демонстрації."""
    return {"projeto": "Житловий будинок 120 м²", "cidade": "kyiv", "uso": "residencial", "area_aquecida_m2": 120, "volume_m3": 324,
            "renovacoes_h": 0.5, "recuperacao_calor": 0.0, "inclinacao_cobertura_graus": 0,
            "elementos": [
                {"nome": "Стіна: газобетон D400 + мінвата 100", "tipo": "parede", "area_m2": 105,
                 "camadas": [{"material": "shtukaturka_gips", "espessura_mm": 15}, {"material": "gazobeton_d400", "espessura_mm": 375},
                             {"material": "mineralna_vata", "espessura_mm": 100}, {"material": "tonka_shtukaturka", "espessura_mm": 8}]},
                {"nome": "Покриття: з/б плита + PIR 180", "tipo": "cobertura", "area_m2": 120,
                 "camadas": [{"material": "zalizobeton", "espessura_mm": 200}, {"material": "paroizolyatsiya_al"},
                             {"material": "pir", "espessura_mm": 180}, {"material": "pokrivelna_membrana"}]},
                {"nome": "Підлога над техпідпіллям: з/б + XPS 200", "tipo": "pavimento_ext", "area_m2": 120,
                 "camadas": [{"material": "styazhka", "espessura_mm": 60}, {"material": "paroizolyatsiya"}, {"material": "xps", "espessura_mm": 200},
                             {"material": "zalizobeton", "espessura_mm": 200}]},
                {"nome": "Вікна (двокамерний склопакет)", "tipo": "janela", "area_m2": 22, "R": 0.95},
                {"nome": "Вхідні двері", "tipo": "porta", "area_m2": 2.2, "R": 0.80}],
            "modelo_estrutural": modelo_casa_kyiv()}


def modelo_casa_kyiv() -> dict:
    """Одноповерховий будинок 10 × 12 м: монолітні стрічкові фундаменти, цокольні стіни, з/б плити перекриття і покриття, стіни з газобетону."""
    gx = [{"nome": "1", "pos_m": 0.0}, {"nome": "2", "pos_m": 5.0}, {"nome": "3", "pos_m": 10.0}]
    gy = [{"nome": "А", "pos_m": 0.0}, {"nome": "Б", "pos_m": 6.0}, {"nome": "В", "pos_m": 12.0}]
    linhas = [[[0, 0], [10, 0]], [[10, 0], [10, 12]], [[10, 12], [0, 12]], [[0, 12], [0, 0]], [[5, 0], [5, 12]], [[0, 6], [10, 6]]]
    m = {"projeto": "Житловий будинок 120 м²", "grelhas_x": gx, "grelhas_y": gy, "solo_q_adm_kpa": 200, "cota_pavimento_m": 0.0,
         "niveis": [{"nome": "чиста підлога", "cota_m": 0.0}, {"nome": "верх фундаментів", "cota_m": -1.2}, {"nome": "верх покриття", "cota_m": 3.2}],
         "sapatas": [], "pilares": [], "vigas": [],
         "sapatas_continuas": [{"ref": "ФС-1" if i < 4 else "ФС-2", "pontos": l, "b_m": 0.6 if i < 4 else 0.7, "h_m": 0.4, "cota_topo_m": -1.2,
                                "g_kn_m": 38 if i < 4 else 55, "q_kn_m": 10 if i < 4 else 18} for i, l in enumerate(linhas)],
         "muros": [{"pontos": l, "espessura_m": 0.4, "cota_base_m": -1.2, "cota_topo_m": -0.2} for l in linhas]
                  + [{"pontos": l, "espessura_m": 0.375, "cota_base_m": 0.0, "cota_topo_m": 3.0, "material": "gazobeton"} for l in linhas],
         "lajes": []}
    for x0, x1 in ((0, 5), (5, 10)):
        for y0, y1 in ((0, 6), (6, 12)):
            m["lajes"].append({"ref": "П-1", "piso": "pavimento", "tipo": "laje_ba", "x0_m": x0, "y0_m": y0, "x1_m": x1, "y1_m": y1, "espessura_m": 0.2,
                               "cota_topo_m": -0.0, "q_kn_m2": 1.5, "g2_kn_m2": 1.6, "direcao_vao": "x", "descricao": "з/б плита 200, C25/30"})
            m["lajes"].append({"ref": "П-2", "piso": "cobertura", "tipo": "laje_ba", "x0_m": x0, "y0_m": y0, "x1_m": x1, "y1_m": y1, "espessura_m": 0.2,
                               "cota_topo_m": 3.2, "g2_kn_m2": 1.2, "isolamento_m": 0.18, "direcao_vao": "x", "descricao": "з/б плита 200 + PIR 180"})
    return m


# ------------------------------------------------------------------------------------------------ fusão com bet_clt_ua (Codex)
_CAT = {"wall": "parede", "roof": "cobertura", "floor_over_unheated": "pavimento_ext"}


def preencher_clt_ua(raw: dict) -> tuple[dict, list[str]]:
    """Completa um estudo bet_clt_ua com os dados normativos ConstruPilot (clima da localidade, S0 / W0 em kPa, zona,
    Rq,min do ДБН В.2.6-31:2021) SÓ onde o campo está vazio. Nada é marcado como confirmado: a confirmação continua a ser
    do projetista (o motor bet_clt_ua mantém INPUT_REQUIRED até lá). Devolve (estudo, lista do que foi preenchido)."""
    import copy
    raw = copy.deepcopy(raw)
    feito = []
    site = raw.setdefault("site", {"country": "UA"})
    loc = site.get("locality") or site.get("region")
    c = None
    if loc:
        try:
            c = clima(str(loc))
        except ValueError:
            c = None
    if c:
        for campo, valor, fonte in (("thermal_zone", c["zona"], "ДБН В.2.6-31:2021 дод. А"), ("winter_design_c", float(c["theta_e"]), "ДСТУ-Н Б В.1.1-27:2010"),
                                    ("snow_ground_kpa", c["s0_pa"] / 1000, "ДБН В.1.2-2:2006 дод. Е"), ("wind_reference_kpa", c["w0_pa"] / 1000, "ДБН В.1.2-2:2006 дод. Е")):
            if site.get(campo) is None:
                site[campo] = valor
                feito.append(f"site.{campo} = {valor} ({fonte}, {c['name']}, довідково — підтвердити)")
    zona = site.get("thermal_zone")
    for a in raw.get("assemblies") or []:
        if a.get("required_effective_r_m2k_w") is None and zona in ("I", "II") and a.get("category") in _CAT:
            a["required_effective_r_m2k_w"] = RQMIN[_CAT[a["category"]]][zona]
            feito.append(f"assemblies.{a.get('id')}.required_effective_r_m2k_w = {a['required_effective_r_m2k_w']} (ДБН В.2.6-31:2021 табл. 1, зона {zona})")
    return raw, feito


def exemplo_clt(cidade: str = "kyiv", produto: str = "rezult_clt") -> dict:
    """Будинок 10 × 12 м з панелей CLT (стіни, перекриття, покриття) на стрічкових фундаментах — приклад для CLT в Україні."""
    p = exemplo_kyiv()
    p.update(projeto="Житловий будинок Rezult CLT 120 м²", cidade=cidade)
    p["elementos"] = [
        {"nome": "Стіна CLT 100 + мінвата 200", "tipo": "parede", "area_m2": 105,
         "camadas": [{"material": "gipsokarton", "espessura_mm": 12.5}, {"material": "clt", "espessura_mm": 100}, {"material": "paroizolyatsiya"},
                     {"material": "mineralna_vata", "espessura_mm": 200}, {"material": "vitrozakhyst"}],
         "pontes_lineares": [{"comprimento_m": 44, "psi": 0.03}, {"comprimento_m": 60, "psi": 0.02}], "pontes_pontuais": [{"n": 160, "chi": 0.002}]},
        {"nome": "Покриття CLT 200 + мінвата 260", "tipo": "cobertura", "area_m2": 120,
         "camadas": [{"material": "clt", "espessura_mm": 200}, {"material": "paroizolyatsiya_al"}, {"material": "mineralna_vata_pokr", "espessura_mm": 260},
                     {"material": "pokrivelna_membrana"}]},
        {"nome": "Перекриття CLT 200 над техпідпіллям + мінвата 200", "tipo": "pavimento_ext", "area_m2": 120,
         "camadas": [{"material": "styazhka", "espessura_mm": 50}, {"material": "clt", "espessura_mm": 200}, {"material": "mineralna_vata", "espessura_mm": 200}]},
        {"nome": "Вікна (двокамерний склопакет)", "tipo": "janela", "area_m2": 22, "R": 0.95},
        {"nome": "Вхідні двері", "tipo": "porta", "area_m2": 2.2, "R": 0.80}]
    m = modelo_casa_kyiv()
    m["projeto"] = "Житловий будинок Rezult CLT 120 м²"
    m["muros"] = [mu for mu in m["muros"] if mu.get("material") != "gazobeton"] + \
                 [dict(mu, espessura_m=0.10, material="clt") for mu in modelo_casa_kyiv()["muros"] if mu.get("material") == "gazobeton"]
    for g in m["sapatas_continuas"]:
        g.update(g_kn_m=22 if g["ref"] == "ФС-1" else 30, q_kn_m=9 if g["ref"] == "ФС-1" else 15)
    m["lajes"] = []
    for x0, x1 in ((0, 5), (5, 10)):
        for y0, y1 in ((0, 6), (6, 12)):
            m["lajes"].append({"ref": "CLT-П", "piso": "pavimento", "tipo": "clt", "x0_m": x0, "y0_m": y0, "x1_m": x1, "y1_m": y1, "espessura_m": 0.2,
                               "camadas_mm": [40, 40, 40, 40, 40], "vao_m": 5.0, "cota_topo_m": 0.0, "q_kn_m2": 1.5, "g2_kn_m2": 1.3, "psi2": 0.3,
                               "produto": produto, "fogo_min": 60,
                               "direcao_vao": "x", "descricao": "Rezult CLT 200 (5 × 40), ETA-21/0914"})
            m["lajes"].append({"ref": "CLT-К", "piso": "cobertura", "tipo": "clt", "x0_m": x0, "y0_m": y0, "x1_m": x1, "y1_m": y1, "espessura_m": 0.2,
                               "camadas_mm": [40, 40, 40, 40, 40], "vao_m": 5.0, "cota_topo_m": 3.2, "g2_kn_m2": 0.8, "psi2": 0.0, "isolamento_m": 0.26,
                               "produto": produto, "fogo_min": 60,
                               "direcao_vao": "x", "descricao": "Rezult CLT 200 + мінвата 260"})
    p["modelo_estrutural"] = m
    return p


def dossiers(p: dict) -> dict:
    """Os dois dossiers completos (sempre): ucraniano e inglês, com o mesmo cálculo. → {"uk": note, "en": note}."""
    if p.get("modelo_estrutural") and p.get("renders") is None and p.get("render", True) is not False:
        import json
        from . import gros_oeuvre
        mod = json.loads(p["modelo_estrutural"]) if isinstance(p["modelo_estrutural"], str) else p["modelo_estrutural"]
        p = dict(p, renders=gerar_renders(gros_oeuvre.calcular(mod)["modelo"], p.get("render_opcoes")))
    return {lg: note(dict(p, lingua=lg)) for lg in ("uk", "en")}


def _render_proc(args, destino):
    """Processo filho: render Mitsuba → pickle em `destino`."""
    import pickle
    from . import render3d
    modelo, opcoes, largura, altura, spp, budget = args
    out = render3d.render(modelo, opcoes, largura, altura, spp, orcamento_s=budget)
    with open(destino, "wb") as fh:
        pickle.dump(out, fh)


def _render_isolado(modelo, opcoes, largura, altura, spp, budget, hard):
    """Render num processo separado (spawn) com teto de tempo: se o motor de render encravar ou demorar demasiado, o
    processo é terminado e o dossier sai sem renders — o cálculo nunca fica parado."""
    import multiprocessing as mp
    import os
    import pickle
    import tempfile
    if os.environ.get("CP_RENDER_INLINE") == "1":            # testes / depuração
        from . import render3d
        return render3d.render(modelo, opcoes, largura, altura, spp, orcamento_s=budget)
    fd, destino = tempfile.mkstemp(suffix=".pkl")
    os.close(fd)
    try:
        pr = mp.get_context("spawn").Process(target=_render_proc, args=((modelo, opcoes, largura, altura, spp, budget), destino), daemon=True)
        pr.start()
        pr.join(hard)
        if pr.is_alive():
            pr.terminate()
            pr.join(5)
            if pr.is_alive():
                pr.kill()
            raise TimeoutError(f"render 3D > {hard:.0f} s — dossier sem renders")
        if pr.exitcode != 0 or os.path.getsize(destino) == 0:
            raise RuntimeError(f"processo de render terminou com código {pr.exitcode}")
        with open(destino, "rb") as fh:
            return pickle.load(fh)
    finally:
        try:
            os.unlink(destino)
        except OSError:
            pass


def gerar_renders(modelo: dict, opcoes: dict | None = None, largura=None, altura=None, spp=None, so_cache: bool = False):
    """Render 3D fotorrealista a partir do modelo dos planos (sempre que há modelo estrutural).
    `so_cache` : devolve só o render já em cache, ou None (sem calcular).
    Produção: 1920 × 1080 (Full HD), 32 amostras, orçamento de tempo CP_RENDER_BUDGET (80 s; a 1.ª vista é sempre feita) e cache em disco
    (mesmo modelo → resultado imediato). Qualquer falha do motor de render → lista vazia: o dossier sai sempre."""
    import hashlib
    import json
    import logging
    import os
    import pickle
    import tempfile
    largura = largura or int(os.environ.get("CP_RENDER_W", 1920))
    altura = altura or int(largura * 9 / 16)
    spp = spp or int(os.environ.get("CP_RENDER_SPP", 32))
    budget = float(os.environ.get("CP_RENDER_BUDGET", 80))
    chave = hashlib.sha256(json.dumps([modelo, opcoes or {}, largura, altura, spp], sort_keys=True, default=str).encode()).hexdigest()[:24]
    cache = os.path.join(os.environ.get("CP_RENDER_CACHE") or os.path.join(tempfile.gettempdir(), "cp_render_cache"), chave + ".pkl")
    try:
        if os.path.exists(cache):
            return pickle.load(open(cache, "rb"))
    except Exception:  # noqa: BLE001
        pass
    if so_cache:
        return None
    hard = float(os.environ.get("CP_RENDER_HARD", 240))        # teto: acima disto o dossier sai sem renders, o estudo nunca fica parado        # teto absoluto: o render corre num processo à parte, morto se exceder
    try:
        out = _render_isolado(modelo, opcoes or {}, largura, altura, spp, budget, hard)
    except Exception as exc:  # noqa: BLE001 — o render nunca pode impedir o dossier
        logging.getLogger(__name__).warning("render 3D indisponível: %s", exc)
        return []
    try:
        os.makedirs(os.path.dirname(cache), exist_ok=True)
        pickle.dump(out, open(cache, "wb"))
    except Exception:  # noqa: BLE001
        pass
    return out


def pagina_renders(renders, L, extra_pdf=None) -> bytes:
    """Páginas A4 horizontais com os renders (legendas na língua do dossier)."""
    import pymupdf
    from .gros_oeuvre import _fontes
    fr, fb = _fontes()
    nomes = {"principal": "Загальний вигляд", "terraco": "Вигляд з боку тераси", "aerea": "Вигляд з висоти"}
    d = pymupdf.open(stream=extra_pdf, filetype="pdf") if extra_pdf else pymupdf.open()
    W, H = 841.89, 595.28
    for i, (nome, png) in enumerate(renders):
        pg = d.new_page(width=W, height=H)
        pg.insert_font(fontname="cr", fontfile=fr)
        pg.insert_font(fontname="cb", fontfile=fb)
        pg.draw_rect(pymupdf.Rect(0, 0, W, H), color=None, fill=(0.10, 0.11, 0.12))
        pg.insert_image(pymupdf.Rect(28, 52, W - 28, 52 + (W - 56) * 9 / 16), stream=png)
        tit = L("Візуалізація 3D") + " — " + L(nomes.get(nome, nome))
        pg.insert_text((28, 36), tit, fontname="cb", fontsize=14, color=(1, 1, 1))
        pg.insert_text((28, H - 18), L("Згенеровано з моделі робочих креслень (Mitsuba 3, трасування шляхів, фізичне сонце й небо). "
                                      "Геометрія — за кресленнями; фасади, прорізи та озеленення — орієнтовні."), fontname="cr", fontsize=7.5,
                       color=(0.75, 0.75, 0.75))
    return d.tobytes(garbage=3, deflate=True)
