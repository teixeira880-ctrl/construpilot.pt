"""Кошторис / Bill of quantities (Україна) — orçamento DETALHADO de uma moradia, em inglês e ucraniano, a partir de:
  • modelo estrutural verificado (gros_oeuvre): betão, armaduras, CLT com as secções ajustadas, ligadores (planos_especialidades.conectores);
  • envolvente conforme ao ДБН (espessuras de isolamento necessárias);
  • divisões e especialidades (especialidades.calcular): pontos elétricos, cabos, tubagens por diâmetro, aparelhos, piso radiante, bomba de calor.
Preços em UAH (taxa NBU), cada linha com a fonte: S1…S10 = fontes do motor bet_clt (estimate.SOURCES), S11…S16 = fontes das especialidades
(datadas, com URL), H = hipótese ConstruPilot a substituir pela proposta do empreiteiro. ПДВ 20 % (Податковий кодекс, ст. 193).
"""
from __future__ import annotations

import math

from . import especialidades as E

PDV = 0.20
EUR_UAH = 50.6455
DATA = "09.11.2026"
PCT = {"site": 0.03, "design": 0.05, "contingency": 0.05}

SOURCES = {
    "S11": (("UNIAN (07.05.2026) — socket installation 500–1,500 UAH per point (Kyiv)", "УНІАН (07.05.2026) — встановлення розетки 500–1 500 грн за точку (Київ)"),
            "https://www.unian.ua/society/yak-zrobiti-dodatkovi-rozetki-v-kvartiri-skilki-ce-koshtuye-i-shcho-dlya-cogo-potribno-13373466.html"),
    "S12": (("PricesUA (02.07.2026) — water point 1,500–3,500; WC 1,500–3,000; washbasin 1,000–2,500; washing machine 800–2,000 UAH (labour)",
             "PricesUA (02.07.2026) — точка водопостачання 1 500–3 500; унітаз 1 500–3 000; умивальник 1 000–2 500; пральна машина 800–2 000 грн (роботи)"),
            "https://pricesua.com/rozcinky-santehnichni-roboty-ukrayina-2026/"),
    "S13": (("Telegraf (16.05.2026) — water UFH installation 250–520 UAH/m²; mixing group + manifold cabinet 16,000–17,000 UAH",
             "Телеграф (16.05.2026) — монтаж водяної теплої підлоги 250–520 грн/м²; змішувальний вузол + колекторна шафа 16 000–17 000 грн"),
            "https://news.telegraf.com.ua/ukr/obshhestvo/5940271-vodyanoy-ili-elektricheskiy-teplyy-pol-skolko-stoit-montazh-i-chto-bystree-okupitsya"),
    "S14": (("Vencon — LG Therma V 16 kW 3-phase air/water heat pump (heating down to −25 °C): 495,000 UAH (listed price, out of stock 11.2026)",
             "Vencon — тепловий насос LG Therma V 16 кВт 3ф (опалення до −25 °C): 495 000 грн (ціна каталогу, немає в наявності 11.2026)"),
            "https://vencon.ua/products/lg-therma-v-16-kvt-3f-hu163ma-u33ruhn1636m-nk5ru"),
    "S15": (("Vencon — Odeskabel VVGng 3×2.5 mm² cable: 17,708 UAH / 200 m = 88.5 UAH/m", "Vencon — кабель Одескабель ВВГнг 3×2,5 мм²: 17 708 грн / 200 м = 88,5 грн/м"),
            "https://vencon.ua/ua/products/odeskabel-vvgng-3x2-5-mm-ozh-15714"),
    "S16": (("Vencon — electrical connection of a water heater 5,660 UAH; washing machine / dishwasher 5,278 UAH", "Vencon — електропідключення бойлера 5 660 грн; пральної / посудомийної машини 5 278 грн"),
            "https://vencon.ua/ua/catalog/montazh-elektrooborudovaniya"),
}


def _src(k, lg):
    if k in SOURCES:
        lab, url = SOURCES[k]
        return (lab[1] if lg == "uk" else lab[0]), url
    from engines.bet_clt.estimate import SOURCES as S0
    lab, url = S0[k]
    return (lab[3] if lg == "uk" else lab[2]), url


# código: (preço UAH, fonte)
P = {
    # 1 terraplenagem e cave (preços do motor bet_clt)
    "excav": (420, "H"), "lean": (5200, "S1"), "conc_fnd": (7400, "S1"), "conc_wall": (9900, "S1"), "conc_slab": (8800, "S1"), "rebar": (68, "S2"),
    "bsmt_wp": (680, "H"), "bsmt_xps": (640, "S6"), "drain": (1150, "H"), "backfill": (260, "H"), "plinth": (9900, "S1"),
    # 2 CLT
    "clt_supply": (round(700 * 50.65), "S3"), "clt_pose": (650, "H"), "crane": (38000, "H"), "bracket": (1150, "H"), "holddown": (3400, "H"),
    "screws": (95, "H"), "screw6": (18, "H"), "spline": (720, "H"), "sole": (950, "H"), "acoustic_strip": (160, "H"),
    # 3 envolvente
    "ext_ins": (1990, "S4"), "membrane": (95, "H"), "plinth_xps": (780, "S6"), "roof_xps": (1240, "S6"), "roof_vcl": (140, "H"), "roof_lwc": (560, "S1"),
    "roof_pvc": (1250, "S9"), "roof_gravel": (190, "H"), "roof_edge": (1400, "H"), "win_alu": (16500, "S7"), "win_pvc": (8500, "S7"), "door_ext": (48000, "H"),
    # 4 interiores
    "lining": (720, "S8"), "ceiling": (980, "S8"), "partition": (1950, "S8"), "acoustic": (420, "H"), "screed": (780, "H"), "flooring": (1450, "H"),
    "floor_tile": (2300, "H"), "wall_tile": (2300, "H"), "paint": (290, "H"), "doors_int": (16500, "H"), "stairs": (145000, "H"),
    # 5 eletricidade
    "el_board": (6500, "H"), "el_main": (1800, "H"), "el_spd": (3500, "H"), "el_rcd": (3800, "H"), "el_mcb1": (450, "H"), "el_mcb3": (900, "H"),
    "el_c15": (60, "H"), "el_c25": (89, "S15"), "el_c525": (150, "H"), "el_conduit": (18, "H"), "el_box": (45, "H"), "el_dev": (280, "H"),
    "el_light": (1200, "H"), "el_point": (800, "S11"), "el_ded": (5278, "S16"), "el_hp": (5660, "S16"), "el_earth": (6500, "H"), "el_test": (8500, "H"),
    "el_lv": (450, "H"),
    # 6 águas e esgotos
    "pl_point": (2500, "S12"), "pl_dpoint": (2000, "H"), "pl_pex16": (55, "H"), "pl_pex20": (75, "H"), "pl_pex32": (160, "H"), "pl_pex40": (230, "H"),
    "pl_insul": (35, "H"), "pl_pp50": (120, "H"), "pl_pp75": (180, "H"), "pl_pp90": (220, "H"), "pl_pp110": (260, "H"), "pl_vent": (1500, "H"),
    "pl_wc": (14000, "H"), "pl_wc_i": (2250, "S12"), "pl_basin": (6500, "H"), "pl_basin_i": (1750, "S12"), "pl_shower": (22000, "H"), "pl_shower_i": (3500, "H"),
    "pl_bath": (18000, "H"), "pl_bath_i": (3500, "H"), "pl_sink_i": (1750, "S12"), "pl_app_i": (1400, "S12"), "pl_util": (4500, "H"),
    "pl_meter": (9500, "H"), "pl_pump": (38000, "H"), "pl_ext": (15000, "H"), "pl_firecollar": (1200, "H"),
    # 7 aquecimento
    "ht_hp": (495000, "S14"), "ht_hp_i": (45000, "H"), "ht_dhw": (52000, "H"), "ht_buffer": (9500, "H"), "ht_vessel": (2200, "H"), "ht_group": (16500, "S13"),
    "ht_manif": (1100, "H"), "ht_act": (1200, "H"), "ht_thermo": (2200, "H"), "ht_pipe": (38, "H"), "ht_board": (320, "H"), "ht_edge": (25, "H"),
    "ht_lab": (385, "S13"), "ht_plant": (35000, "H"), "ht_riser": (450, "H"), "ht_comm": (12000, "H"),
    # 8 ventilação, terraço
    "mvhr": (185000, "H"), "terrace": (9800, "H"),
}


def _comp(pts):
    return sum(math.hypot(b[0] - a[0], b[1] - a[1]) for a, b in zip(pts[:-1], pts[1:]))


def build(m: dict, r: dict, conectores: dict, env: dict | None = None) -> dict:
    """m = modelo verificado (secções ajustadas), r = especialidades.calcular(m). env = {fachada_m2, cobertura_m2, vidro_alu_m2, vidro_pvc_m2, terraco_m2,
    portas_int, escadas, mw_mm, xps_cob_mm}."""
    env = dict({"fachada_m2": 236, "cobertura_m2": 148, "vidro_alu_m2": 20, "vidro_pvc_m2": 10, "terraco_m2": 26.5, "portas_int": 14, "escadas": 2,
                "mw_mm": 120, "xps_cob_mm": 200}, **(env or {}))
    L = []

    def add(lot, code, en, uk, unit_en, unit_uk, qty):
        if qty and qty > 0:
            pu, src = P[code]
            L.append({"lot": lot, "code": code, "en": en, "uk": uk, "u_en": unit_en, "u_uk": unit_uk, "qty": round(float(qty), 2), "pu": float(pu), "src": src})
    # ---------------------------------------------------------------- quantidades estruturais
    xs = [g["pos_m"] for g in m["grelhas_x"]]
    ys = [g["pos_m"] for g in m["grelhas_y"]]
    W, D = max(xs) - min(xs), max(ys) - min(ys)
    v_fnd = sum(_comp(s["pontos"]) * s["b_m"] * s["h_m"] for s in m.get("sapatas_continuas") or [])
    a_fnd = sum(_comp(s["pontos"]) * s["b_m"] for s in m.get("sapatas_continuas") or [])
    rc_walls = [mu for mu in m.get("muros") or [] if mu.get("material") != "clt"]
    v_wall = sum(_comp(mu["pontos"]) * (mu["cota_topo_m"] - mu["cota_base_m"]) * mu["espessura_m"] for mu in rc_walls)
    per = max([_comp(mu["pontos"]) for mu in rc_walls if mu["pontos"][0] == mu["pontos"][-1]] or [2 * (W + D)])
    prof = max([-mu["cota_base_m"] for mu in rc_walls] or [0])
    v_slab = sum(abs(lj["x1_m"] - lj["x0_m"]) * abs(lj["y1_m"] - lj["y0_m"]) * lj["espessura_m"] for lj in m.get("lajes") or [] if lj.get("tipo") == "laje_ba")
    excav = (W + 2.0) * (D + 2.0) * (prof + 0.2)
    clt_walls = [mu for mu in m.get("muros") or [] if mu.get("material") == "clt"]
    v_cltw = sum(_comp(mu["pontos"]) * (mu["cota_topo_m"] - mu["cota_base_m"]) * mu["espessura_m"] for mu in clt_walls) * 0.9
    v_cltf = sum(abs(lj["x1_m"] - lj["x0_m"]) * abs(lj["y1_m"] - lj["y0_m"]) * (sum(lj.get("camadas_mm") or []) / 1000 or lj["espessura_m"])
                 for lj in m.get("lajes") or [] if lj.get("tipo") == "clt")
    a_cltw = sum(_comp(mu["pontos"]) * (mu["cota_topo_m"] - mu["cota_base_m"]) for mu in clt_walls)
    l1 = ("1. Earthworks, foundations and RC basement", "1. Земляні роботи, фундаменти та з/б підвал")
    add(l1, "excav", "Bulk excavation incl. disposal", "Розробка ґрунту котловану з вивезенням", "m³", "м³", excav)
    add(l1, "lean", "Blinding concrete C8/10, 50 mm", "Бетонна підготовка C8/10, 50 мм", "m³", "м³", a_fnd * 0.05)
    add(l1, "conc_fnd", "Strip footings C25/30 incl. formwork", "Стрічкові фундаменти C25/30 з опалубкою", "m³", "м³", v_fnd)
    add(l1, "conc_wall", "RC basement walls 250 mm C25/30", "З/б стіни підвалу 250 мм C25/30", "m³", "м³", v_wall)
    add(l1, "conc_slab", "RC slab 250 mm over basement C25/30", "З/б плита 250 мм над підвалом C25/30", "m³", "м³", v_slab)
    add(l1, "plinth", "RC upstand under CLT walls h 300 mm", "З/б цоколь під стіни CLT h 300 мм", "m³", "м³", sum(_comp(mu["pontos"]) for mu in clt_walls if abs(mu["cota_base_m"]) < 0.05) * 0.3 * 0.25)
    add(l1, "rebar", "Reinforcement A500C (footings 60, walls 80, slab 110 kg/m³)", "Арматура A500C (фундаменти 60, стіни 80, плита 110 кг/м³)", "kg", "кг",
        v_fnd * 60 + v_wall * 80 + v_slab * 110)
    add(l1, "bsmt_wp", "Waterproofing of basement walls", "Гідроізоляція стін підвалу", "m²", "м²", per * prof)
    add(l1, "bsmt_xps", "XPS 100 mm on basement walls", "XPS 100 мм на стінах підвалу", "m²", "м²", per * prof)
    add(l1, "drain", "Perimeter drain with gravel and geotextile", "Пристінний дренаж з гравієм і геотекстилем", "m", "м", per + 4)
    add(l1, "backfill", "Backfill and compaction", "Зворотна засипка з ущільненням", "m³", "м³", max(0, excav - W * D * (prof + 0.2)))
    l2 = ("2. Rezult CLT structure", "2. Конструкції Rezult CLT")
    add(l2, "clt_supply", "Rezult CLT wall panels (100 L5s), CNC-machined, delivered", "Стінові панелі Rezult CLT (100 L5s), ЧПК, з доставкою", "m³", "м³", v_cltw)
    add(l2, "clt_supply", "Rezult CLT floor / roof panels (240 L7s; roof 160–180 L5s as checked)", "Панелі перекриття / покриття Rezult CLT (240 L7s; покриття 160–180 L5s за розрахунком)",
        "m³", "м³", v_cltf)
    add(l2, "clt_pose", "CLT erection (lifting, shimming, screwing, joint sealing)", "Монтаж CLT (підйом, вирівнювання, кріплення, ущільнення швів)", "m²", "м²",
        a_cltw + v_cltf / 0.2)
    add(l2, "crane", "Mobile crane with crew", "Автокран з бригадою", "day", "зміна", 6)
    for (en, uk, u, qv), code in zip(conectores["linhas"], ("bracket", "holddown", "screws", "spline", "screw6", "sole", "acoustic_strip")):
        add(l2, code, en, uk, "u" if u == "un" else "m", "шт" if u == "un" else "м", qv)
    l3 = ("3. Envelope, insulation and waterproofing", "3. Огороджувальні конструкції, утеплення, гідроізоляція")
    add(l3, "ext_ins", f"Façade: vapour control + mineral wool {env['mw_mm']} mm (ДБН R ≥ 4.0) + breather membrane + ventilated cladding",
        f"Фасад: пароізоляція + мінвата {env['mw_mm']} мм (ДБН R ≥ 4,0) + вітрозахист + вентильоване облицювання", "m²", "м²", env["fachada_m2"])
    add(l3, "plinth_xps", "XPS 100 mm plinth insulation", "Утеплення цоколя XPS 100 мм", "m²", "м²", 2 * (W + D) * 0.5)
    add(l3, "roof_vcl", "Roof vapour control layer (Al)", "Пароізоляція покрівлі (Al)", "m²", "м²", env["cobertura_m2"])
    add(l3, "roof_xps", f"Roof XPS {env['xps_cob_mm']} mm (ДБН R ≥ 7.0)", f"Утеплення покрівлі XPS {env['xps_cob_mm']} мм (ДБН R ≥ 7,0)", "m²", "м²", env["cobertura_m2"])
    add(l3, "roof_lwc", "Lightweight concrete to falls ±100 mm", "Ухилоутворювальний легкий бетон ±100 мм", "m²", "м²", env["cobertura_m2"])
    add(l3, "roof_pvc", "PVC roofing membrane + geotextile", "ПВХ-мембрана + геотекстиль", "m²", "м²", env["cobertura_m2"] * 1.08)
    add(l3, "roof_gravel", "Gravel ballast", "Гравійний баласт", "m²", "м²", env["cobertura_m2"])
    add(l3, "roof_edge", "Parapets, upstands, rainwater outlets", "Парапети, примикання, водоприймальні воронки", "m", "м", 2 * (W + D) + 24)
    add(l3, "win_alu", "Thermally broken aluminium sliding doors, triple glazing", "Алюмінієві розсувні двері з терморозривом, 3-камерний склопакет", "m²", "м²", env["vidro_alu_m2"])
    add(l3, "win_pvc", "PVC windows Uw ≤ 1.0, triple glazing, installed", "Вікна ПВХ Uw ≤ 1,0, 3-камерний склопакет, з монтажем", "m²", "м²", env["vidro_pvc_m2"])
    add(l3, "door_ext", "Insulated entrance door", "Утеплені вхідні двері", "u", "шт", 1)
    # ---------------------------------------------------------------- interiores (a partir das divisões)
    divs = r["divisoes"]
    seco = [d for d in divs if d.get("revestimento") != "ceramico"]
    hum = [d for d in divs if d.get("revestimento") == "ceramico"]
    wet = [d for d in divs if d["tipo"] in ("casa_de_banho", "lavandaria")]
    a_aq = sum(E.area(d) for d in divs if d.get("aquecida", True))
    a_cave = sum(E.area(d) for d in divs if not d.get("aquecida", True))
    part = 0.0                                  # divisórias = arestas das divisões que não coincidem com paredes estruturais (por piso)
    for c in sorted({round(d["cota"], 2) for d in divs}):
        ds = [d for d in divs if round(d["cota"], 2) == c]
        mus = [mu for mu in m.get("muros") or [] if c - 0.3 <= mu["cota_base_m"] <= c + 0.05]
        L_ext = sum(_comp(mu["pontos"]) for mu in mus if mu["pontos"][0] == mu["pontos"][-1])
        L_int = sum(_comp(mu["pontos"]) for mu in mus if mu["pontos"][0] != mu["pontos"][-1])
        L_div = (sum(2 * ((d["x1"] - d["x0"]) + (d["y1"] - d["y0"])) for d in ds) - L_ext) / 2
        part += max(0.0, L_div - L_int) * max(d["pe_direito"] for d in ds)
    l4 = ("4. Linings, partitions, screeds and finishes", "4. Обшивка, перегородки, стяжки, оздоблення")
    add(l4, "lining", "Plasterboard 2×12.5 mm lining on CLT walls (fire / services)", "Обшивка стін CLT ГКП 2×12,5 мм (вогнезахист / комунікації)", "m²", "м²", a_cltw * 1.5)
    add(l4, "ceiling", "Suspended plasterboard ceilings (heated floors)", "Підвісні стелі з ГКП (опалювані поверхи)", "m²", "м²", a_aq)
    add(l4, "partition", "Stud partitions 48 mm + rock wool + 2×12.5 plasterboard both faces", "Перегородки каркас 48 мм + мінвата + ГКП 2×12,5 з двох боків", "m²", "м²", part)
    add(l4, "acoustic", "Impact-sound underlay under screed", "Звукоізоляція від ударного шуму під стяжку", "m²", "м²", a_aq)
    add(l4, "screed", "Screed 50–65 mm (with UFH on heated floors) / basement screed", "Стяжка 50–65 мм (з ТП на опалюваних поверхах) / стяжка підвалу", "m²", "м²", a_aq + a_cave)
    add(l4, "flooring", "Engineered wood flooring (dry rooms)", "Інженерна дошка (сухі приміщення)", "m²", "м²", sum(E.area(d) for d in seco if d.get("aquecida", True)))
    add(l4, "floor_tile", "Floor tiles (wet rooms, halls, basement service rooms)", "Плитка підлоги (санвузли, холи, технічні приміщення)", "m²", "м²",
        sum(E.area(d) for d in hum) + a_cave * 0.0)
    add(l4, "wall_tile", "Wall tiles in wet rooms h 2.10 m", "Плитка стін санвузлів h 2,10 м", "m²", "м²", sum(2 * ((d["x1"] - d["x0"]) + (d["y1"] - d["y0"])) * 2.1 for d in wet))
    add(l4, "paint", "Painting of walls and ceilings", "Фарбування стін і стель", "m²", "м²", a_cltw * 1.5 + a_aq + part * 2)
    add(l4, "doors_int", "Internal doors (set with frame and ironmongery)", "Міжкімнатні двері (комплект з коробкою та фурнітурою)", "u", "шт", env["portas_int"])
    add(l4, "stairs", "Timber stairs (flight)", "Дерев'яні сходи (марш)", "u", "шт", env["escadas"])
    # ---------------------------------------------------------------- eletricidade
    q = r["quantidades"]
    el = r["eletricidade"]
    l5 = ("5. Electrical installation", "5. Електромонтажні роботи")
    n1 = sum(1 for c in el["circuitos"] if c.get("b") != 3)
    n3 = sum(1 for c in el["circuitos"] if c.get("b") == 3)
    add(l5, "el_board", f"Distribution board {q['quadro_modulos']} modules IP40 incl. assembly", f"Щит розподільчий {q['quadro_modulos']} модулів IP40 зі складанням", "u", "шт", 1)
    add(l5, "el_main", "Main switch 4P", "Ввідний вимикач 4P", "u", "шт", 1)
    add(l5, "el_spd", "Surge protection device type 2", "УЗІП тип 2", "u", "шт", 1)
    add(l5, "el_rcd", "RCD 4P 30 mA (types A / AC)", "ПЗВ 4P 30 мА (тип A / AC)", "u", "шт", q["diferenciais"])
    add(l5, "el_mcb1", "MCB 1P+N (C10 / C16)", "Автоматичний вимикач 1P+N (C10 / C16)", "u", "шт", n1)
    add(l5, "el_mcb3", "MCB 3P C16", "Автоматичний вимикач 3P C16", "u", "шт", n3)
    cab = q["cabo_m"]
    add(l5, "el_c15", "Cable Cu 3×1.5 mm² (lighting)", "Кабель ВВГнг 3×1,5 мм² (освітлення)", "m", "м", cab.get("1.5", 0))
    tri_m = sum(c["comprimento_m"] * 1.1 for c in el["circuitos"] if c.get("b") == 3)
    add(l5, "el_c25", "Cable Cu 3×2.5 mm² (sockets, appliances)", "Кабель ВВГнг 3×2,5 мм² (розетки, техніка)", "m", "м", max(0, cab.get("2.5", 0) - tri_m * 5 / 3))
    add(l5, "el_c525", "Cable Cu 5×2.5 mm² (3-phase circuits)", "Кабель ВВГнг 5×2,5 мм² (3-фазні лінії)", "m", "м", tri_m)
    add(l5, "el_conduit", "Flexible conduit Ø20 in linings", "Гофротруба Ø20 в обшивці", "m", "м", q["tubo_corrugado_m"])
    add(l5, "el_box", "Back boxes / junction boxes", "Підрозетники / розподільчі коробки", "u", "шт", q["caixas"])
    add(l5, "el_dev", "Sockets and switches (devices)", "Розетки та вимикачі (механізми)", "u", "шт", q["tomadas"] + q["interruptores"])
    add(l5, "el_light", "Light fittings (allowance)", "Світильники (резерв)", "u", "шт", q["pontos_luz"])
    add(l5, "el_point", "Installation labour per point (socket / switch / light)", "Монтаж за точку (розетка / вимикач / світильник)", "pt", "точка",
        q["tomadas"] + q["interruptores"] + q["pontos_luz"])
    add(l5, "el_ded", "Dedicated appliance connections (hob, oven, washing machine, dryer, dishwasher)",
        "Підключення техніки окремими лініями (варильна, духова, пральна, сушильна, посудомийна)", "u", "шт", max(0, q["ponto_dedicado"] - 2))
    add(l5, "el_hp", "Heat pump and backup heater connection", "Підключення теплового насоса і ТЕН", "u", "шт", 2)
    add(l5, "el_earth", "Earthing system + main equipotential bonding", "Заземлення + основна система зрівнювання потенціалів", "set", "компл.", 1)
    add(l5, "el_lv", "Low voltage (data / TV / doorbell) points", "Слабкі струми (інтернет / ТБ / дзвінок)", "pt", "точка", sum(1 for d in divs if d["tipo"] in ("sala", "quarto")) * 2 + 2)
    add(l5, "el_test", "Testing, measurements and documentation", "Випробування, вимірювання, документація", "set", "компл.", 1)
    # ---------------------------------------------------------------- águas e esgotos
    l6 = ("6. Water supply and drainage", "6. Водопостачання та каналізація")
    for k, v in q["tubo_agua_m"].items():
        dn = int(k.split("Ø")[1])
        code = {16: "pl_pex16", 20: "pl_pex20", 25: "pl_pex20", 32: "pl_pex32", 40: "pl_pex40"}.get(dn, "pl_pex20")
        hw = k.startswith("AQ")
        add(l6, code, f"PE-Xa / multilayer pipe Ø{dn} — {'hot' if hw else 'cold'} water", f"Труба PE-Xa / металопластик Ø{dn} — {'гаряча' if hw else 'холодна'} вода", "m", "м", v)
    add(l6, "pl_insul", "Insulation of hot-water pipes 9 mm", "Ізоляція труб гарячої води 9 мм", "m", "м", sum(v for k, v in q["tubo_agua_m"].items() if k.startswith("AQ")))
    for k, v in q["tubo_pvc_m"].items():
        dn = int(k.strip("Ø"))
        add(l6, {50: "pl_pp50", 75: "pl_pp75", 90: "pl_pp90", 110: "pl_pp110"}.get(dn, "pl_pp110"), f"PP drainage pipe Ø{dn} with fittings", f"Каналізаційна труба PP Ø{dn} з фітингами", "m", "м", v)
    add(l6, "pl_vent", "Stack vent through roof + air admittance", "Вентиляція стояка через покрівлю", "u", "шт", q["tubos_queda"])
    add(l6, "pl_firecollar", "Fire collars / sleeves through CLT floors (EI 60)", "Протипожежні манжети / гільзи через перекриття CLT (EI 60)", "u", "шт", q["tubos_queda"] * 2 + 6)
    add(l6, "pl_point", "Water supply points (CW / HW), labour", "Точки водопостачання (ХВ / ГВ), роботи", "pt", "точка", q["pontos_agua"])
    add(l6, "pl_dpoint", "Drainage points, labour", "Точки каналізації, роботи", "pt", "точка", q["pontos_esgoto"])
    ap = q["aparelhos"]
    add(l6, "pl_wc", "Wall-hung WC with concealed frame (supply)", "Підвісний унітаз з інсталяцією (постачання)", "u", "шт", ap.get("autoclismo", 0))
    add(l6, "pl_wc_i", "WC installation", "Монтаж унітазу", "u", "шт", ap.get("autoclismo", 0))
    add(l6, "pl_basin", "Washbasin with mixer and siphon (supply)", "Умивальник зі змішувачем і сифоном (постачання)", "u", "шт", ap.get("lavatorio", 0))
    add(l6, "pl_basin_i", "Washbasin installation", "Монтаж умивальника", "u", "шт", ap.get("lavatorio", 0))
    add(l6, "pl_shower", "Walk-in shower (drain, thermostatic set, glass screen)", "Душова зона (трап, термостатичний комплект, скляна перегородка)", "u", "шт", ap.get("chuveiro", 0))
    add(l6, "pl_shower_i", "Shower installation", "Монтаж душової зони", "u", "шт", ap.get("chuveiro", 0))
    add(l6, "pl_bath", "Bathtub with mixer (supply)", "Ванна зі змішувачем (постачання)", "u", "шт", ap.get("banheira", 0))
    add(l6, "pl_bath_i", "Bathtub installation", "Монтаж ванни", "u", "шт", ap.get("banheira", 0))
    add(l6, "pl_sink_i", "Kitchen sink connection", "Підключення кухонної мийки", "u", "шт", ap.get("lava_loica", 0))
    add(l6, "pl_app_i", "Washing machine / dishwasher water connection", "Підключення пральної / посудомийної машини до води", "u", "шт",
        ap.get("maquina_lavar_roupa", 0) + ap.get("maquina_lavar_loica", 0))
    add(l6, "pl_util", "Utility sink (laundry)", "Господарська мийка (пральня)", "u", "шт", ap.get("tanque", 0))
    add(l6, "pl_meter", "Water inlet: meter, check valve, filter, pressure reducer", "Ввід: водомір, зворотний клапан, фільтр, редуктор тиску", "set", "компл.", 1)
    add(l6, "pl_pump", "Sewage pumping unit for basement fixtures", "КНС для приладів підвалу", "u", "шт", q["estacao_elevatoria"])
    add(l6, "pl_ext", "Building drain connection to external network", "Випуск і підключення до зовнішньої мережі", "set", "компл.", 1)
    # ---------------------------------------------------------------- aquecimento
    bc = r["bomba_calor"]
    l7 = ("7. Heating — air/water heat pump and underfloor heating", "7. Опалення — тепловий насос повітря/вода і тепла підлога")
    add(l7, "ht_hp", f"Cold-climate air/water heat pump {bc['p_nominal_kw']} kW 3-phase (−25 °C), with backup heater",
        f"Тепловий насос повітря/вода для холодного клімату {bc['p_nominal_kw']} кВт 3ф (−25 °C), з ТЕН", "u", "шт", 1)
    add(l7, "ht_hp_i", "Heat pump installation, refrigerant / hydraulic connections", "Монтаж теплового насоса, гідравлічні підключення", "u", "шт", 1)
    add(l7, "ht_dhw", f"DHW cylinder {q['aqs_l']} L for heat pump (large coil)", f"Бойлер ГВП {q['aqs_l']} л для теплового насоса", "u", "шт", 1)
    add(l7, "ht_buffer", "Buffer tank 50 L", "Буферна ємність 50 л", "u", "шт", 1)
    add(l7, "ht_vessel", f"Expansion vessel {q['vaso_l']} L + safety group", f"Розширювальний бак {q['vaso_l']} л + група безпеки", "u", "шт", 1)
    add(l7, "ht_plant", "Plant-room pipework, valves, 3-way diverter, dirt separator", "Обв'язка котельні: труби, арматура, 3-ход. клапан, шламовідділювач", "set", "компл.", 1)
    add(l7, "ht_riser", "Heating risers to manifolds (insulated)", "Стояки опалення до колекторів (в ізоляції)", "m", "м",
        sum(abs(c["cota"] - (r["mep"].get("central") or {}).get("cota", 0)) + 8 for c in r["mep"].get("coletores") or []) * 2)
    add(l7, "ht_group", "Mixing group + manifold cabinet", "Змішувальний вузол + колекторна шафа", "u", "шт", len(q["coletores"]))
    add(l7, "ht_manif", "UFH manifold outlets with flow meters", "Виходи колектора ТП з витратомірами", "u", "шт", q["circuitos_pr"])
    add(l7, "ht_act", "Thermal actuators on manifold outlets", "Сервоприводи на виходах колектора", "u", "шт", q["circuitos_pr"])
    add(l7, "ht_thermo", "Room thermostats (wired)", "Кімнатні термостати (дротові)", "u", "шт", q["termostatos"])
    add(l7, "ht_pipe", "UFH pipe PE-Xa 16×2 with oxygen barrier", "Труба ТП PE-Xa 16×2 з кисневим бар'єром", "m", "м", q["tubo_pex_m"])
    add(l7, "ht_board", "UFH insulation board (EPS / XPS) + PE film", "Плита утеплення під ТП (ППС / XPS) + плівка", "m²", "м²", q["piso_radiante_m2"])
    add(l7, "ht_edge", "Edge insulation strip", "Демпферна стрічка", "m", "м", sum(2 * ((d["x1"] - d["x0"]) + (d["y1"] - d["y0"])) for d in divs if d.get("aquecida", True)))
    add(l7, "ht_lab", "UFH installation labour", "Монтаж теплої підлоги", "m²", "м²", q["piso_radiante_m2"])
    add(l7, "ht_comm", "Pressure test, balancing, commissioning, first heating", "Опресування, балансування, пусконалагодження, перший запуск", "set", "компл.", 1)
    l8 = ("8. Ventilation and external works", "8. Вентиляція та зовнішні роботи")
    add(l8, "mvhr", "Mechanical ventilation with heat recovery (MVHR) incl. ducts", "Припливно-витяжна вентиляція з рекуперацією, з повітроводами", "set", "компл.", 1)
    add(l8, "terrace", "Covered terrace: timber deck + canopy", "Крита тераса: дерев'яний настил + навіс", "m²", "м²", env["terraco_m2"])
    for x in L:
        x["tot"] = round(x["qty"] * x["pu"], 2)
    works = sum(x["tot"] for x in L)
    extra = [{"key": k, "en": en, "uk": uk, "pct": PCT[k], "tot": round(works * PCT[k], 2)} for k, en, uk in (
        ("site", "Site set-up and preliminaries", "Облаштування будмайданчика"),
        ("design", "Shop drawings, MEP design review and site supervision", "Робоча документація, перевірка інженерних мереж, технагляд"),
        ("contingency", "Contingency", "Непередбачені витрати"))]
    ht = works + sum(e["tot"] for e in extra)
    lots = []
    for x in L:
        if x["lot"] not in lots:
            lots.append(x["lot"])
    por_lot = [(lt, sum(x["tot"] for x in L if x["lot"] == lt)) for lt in lots]
    gross = a_aq + a_cave
    srcs = sorted({x["src"] for x in L}, key=lambda s: (s == "H", len(s), s))
    pub = sum(x["tot"] for x in L if x["src"] != "H")
    return {"lines": L, "extra": extra, "works": works, "ht": ht, "vat": ht * PDV, "ttc": ht * (1 + PDV), "eur": EUR_UAH, "gross_m2": gross,
            "heated_m2": a_aq, "per_m2": ht / gross if gross else 0, "per_m2_ttc": ht * (1 + PDV) / gross if gross else 0, "lots": por_lot, "sources": srcs,
            "parte_fonte": pub / works if works else 0, "data": DATA}


# ============================================================================== saídas
def _fmt(x, lg, d=0):
    s = f"{x:,.{d}f}".replace(",", " ")
    return s.replace(".", ",") if lg == "uk" else s


def pdf(dv: dict, lg: str, projeto: str, local: str) -> bytes:
    from . import lingua_ucrania as LU
    from . import rendu
    from .ucrania import UK
    T = (lambda en, uk: uk if lg == "uk" else en)
    W = rendu.mm
    blocs = [("kpis", [{"label": T("Total incl. VAT", "Разом з ПДВ"), "value": f"{_fmt(dv['ttc'] / 1e6, lg, 2)} M", "unit": T("UAH", "грн")},
                       {"label": T("≈ in euro (NBU rate)", "≈ у євро (курс НБУ)"), "value": f"{_fmt(dv['ttc'] / dv['eur'] / 1000, lg, 0)} k", "unit": "€"},
                       {"label": T("Per m² gross (incl. VAT)", "За м² загальної площі (з ПДВ)"), "value": _fmt(dv["per_m2_ttc"], lg), "unit": T("UAH/m²", "грн/м²")},
                       {"label": T("Lines with published price", "Позицій з опублікованою ціною"), "value": f"{_fmt(dv['parte_fonte'] * 100, lg)} %", "unit": T("of works value", "вартості робіт")}]),
             ("h2", T("Summary by work package", "Зведення за розділами")),
             ("table", [T("Work package", "Розділ"), T("Amount excl. VAT (UAH)", "Сума без ПДВ (грн)"), "€", "%"],
              [[(lt[1] if lg == "uk" else lt[0]), _fmt(v, lg), _fmt(v / dv["eur"], lg), _fmt(v / dv["works"] * 100, lg, 1)] for lt, v in dv["lots"]]
              + [[T("Works subtotal", "Разом роботи"), _fmt(dv["works"], lg), _fmt(dv["works"] / dv["eur"], lg), "100"]]
              + [[(e["uk"] if lg == "uk" else e["en"]) + f" ({_fmt(e['pct'] * 100, lg)} %)", _fmt(e["tot"], lg), _fmt(e["tot"] / dv["eur"], lg), ""] for e in dv["extra"]]
              + [[T("TOTAL excl. VAT", "РАЗОМ без ПДВ"), _fmt(dv["ht"], lg), _fmt(dv["ht"] / dv["eur"], lg), ""],
                 [T("VAT 20 %", "ПДВ 20 %"), _fmt(dv["vat"], lg), _fmt(dv["vat"] / dv["eur"], lg), ""],
                 [T("TOTAL incl. VAT", "РАЗОМ з ПДВ"), _fmt(dv["ttc"], lg), _fmt(dv["ttc"] / dv["eur"], lg), ""]],
              [90 * W, 40 * W, 28 * W, 14 * W])]
    for lt, _ in dv["lots"]:
        rows = [[x["code"], x["uk"] if lg == "uk" else x["en"], x["u_uk"] if lg == "uk" else x["u_en"], _fmt(x["qty"], lg, 1), _fmt(x["pu"], lg),
                 _fmt(x["tot"], lg), x["src"]] for x in dv["lines"] if x["lot"] == lt]
        blocs += [("h2", lt[1] if lg == "uk" else lt[0]),
                  ("table", [T("Code", "Код"), T("Description", "Найменування"), T("Unit", "Од."), T("Qty", "К-сть"), T("Rate", "Ціна"), T("Amount", "Сума"), T("Src", "Дж.")],
                   rows, [18 * W, 78 * W, 12 * W, 16 * W, 16 * W, 20 * W, 10 * W])]
    srcs = []
    for k in dv["sources"]:
        lab, url = _src(k, lg)
        srcs.append(f"{k} — {lab}" + (f" — {url}" if url else ""))
    blocs += [("h2", T("Price sources", "Джерела цін")), ("hyp", srcs),
              ("h2", T("Basis of the estimate", "Основа кошторису")),
              ("hyp", [T(f"Quantities measured on the model of the plans (structure, rooms, MEP layouts EL / WS / HT, connector schedule GO-09) — {DATA}.",
                         f"Обсяги виміряні на моделі креслень (конструкції, приміщення, інженерні мережі EL / WS / HT, специфікація з’єднувачів GO-09) — {DATA}."),
                       T("Envelope priced in its ДБН-compliant version (mineral wool 120 mm, roof XPS 200 mm) — not the 100 mm of the architect's sheet, "
                         "which does not meet ДБН В.2.6-31:2021 in Kyiv.",
                         "Огороджувальні конструкції враховані у варіанті, що відповідає ДБН (мінвата 120 мм, XPS покрівлі 200 мм) — не 100 мм з аркуша "
                         "архітектора, що не відповідає ДБН В.2.6-31:2021 для Києва."),
                       T("Retail market prices are used as net prices (conservative); rates marked H are ConstruPilot assumptions to be replaced by the "
                         "contractor's quote; CLT Rezult supply price to be confirmed by the manufacturer.",
                         "Роздрібні ринкові ціни прийнято як ціни без ПДВ (з запасом); ціни з позначкою H — припущення ConstruPilot, замінити пропозицією "
                         "підрядника; ціну постачання Rezult CLT підтверджує виробник."),
                       T(f"Currency: UAH, NBU rate 1 € = {_fmt(dv['eur'], lg, 4)} UAH ({DATA}); VAT (ПДВ) 20 % — Tax Code of Ukraine, art. 193.",
                         f"Валюта: грн, курс НБУ 1 € = {_fmt(dv['eur'], lg, 4)} грн ({DATA}); ПДВ 20 % — Податковий кодекс України, ст. 193."),
                       T("Excluded: land, permits and connection fees, kitchen furniture and appliances, loose furniture, landscaping, interior design.",
                         "Не враховано: земля, дозволи та плата за приєднання до мереж, кухонні меблі й техніка, меблі, благоустрій, дизайн інтер'єру.")])]
    titre = T(f"Bill of quantities and cost estimate — {projeto}", f"Кошторис (відомість обсягів і вартості) — {projeto}")
    sub = T(f"{local} · Ukrainian market prices {DATA} · VAT 20 %", f"{local} · ціни ринку України {DATA} · ПДВ 20 %")
    foot = T("ConstruPilot — estimate from the design model", "ConstruPilot — кошторис з моделі проєкту")
    return rendu.build_pdf(titre, sub, blocs, footer=foot, lang=(LU.EN_RENDU if lg == "en" else UK))


def xlsx(dv: dict, path: str, lg: str, projeto: str):
    import openpyxl
    from openpyxl.styles import Alignment, Font, PatternFill
    T = (lambda en, uk: uk if lg == "uk" else en)
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = T("Estimate", "Кошторис")
    hdr = PatternFill("solid", fgColor="174A38")
    ws.append([projeto])
    ws["A1"].font = Font(bold=True, size=13)
    ws.append([T(f"Prices excl. VAT in UAH — €1 = {dv['eur']} UAH (NBU {DATA}) — editable", f"Ціни без ПДВ у грн — 1 € = {dv['eur']} грн (НБУ {DATA}) — можна редагувати")])
    ws.append([T("Package", "Розділ"), T("Code", "Код"), T("Description", "Найменування"), T("Unit", "Од."), T("Quantity", "Кількість"), T("Rate UAH", "Ціна грн"),
               T("Amount UAH", "Сума грн"), "€", T("Source", "Джерело")])
    for c in ws[3]:
        c.font, c.fill = Font(bold=True, color="FFFFFF"), hdr
    r0 = 4
    for i, x in enumerate(dv["lines"]):
        r = r0 + i
        ws.append([x["lot"][1] if lg == "uk" else x["lot"][0], x["code"], x["uk"] if lg == "uk" else x["en"], x["u_uk"] if lg == "uk" else x["u_en"],
                   x["qty"], x["pu"], f"=E{r}*F{r}", f"=G{r}/{dv['eur']}", x["src"]])
    r1 = r0 + len(dv["lines"]) - 1
    rt = r1 + 2
    ws.cell(rt, 3, T("Works total", "Разом роботи")).font = Font(bold=True)
    ws.cell(rt, 7, f"=SUM(G{r0}:G{r1})")
    for j, e in enumerate(dv["extra"]):
        ws.cell(rt + 1 + j, 3, f"{e['uk'] if lg == 'uk' else e['en']} ({int(e['pct'] * 100)} %)")
        ws.cell(rt + 1 + j, 7, f"=G{rt}*{e['pct']}")
    rh = rt + 1 + len(dv["extra"])
    ws.cell(rh, 3, T("TOTAL excl. VAT", "РАЗОМ без ПДВ")).font = Font(bold=True)
    ws.cell(rh, 7, f"=SUM(G{rt}:G{rh - 1})")
    ws.cell(rh + 1, 3, T("VAT 20 %", "ПДВ 20 %"))
    ws.cell(rh + 1, 7, f"=G{rh}*0.2")
    ws.cell(rh + 2, 3, T("TOTAL incl. VAT", "РАЗОМ з ПДВ")).font = Font(bold=True)
    ws.cell(rh + 2, 7, f"=G{rh}+G{rh + 1}")
    for rr in range(rt, rh + 3):
        ws.cell(rr, 8, f"=G{rr}/{dv['eur']}")
    for rr in range(r0, rh + 3):
        for cc in (5, 6, 7, 8):
            ws.cell(rr, cc).number_format = "#,##0.00" if cc == 5 else "#,##0"
    for col, w in zip("ABCDEFGHI", (34, 12, 70, 8, 12, 12, 16, 12, 8)):
        ws.column_dimensions[col].width = w
    for row in ws.iter_rows(min_row=r0, max_row=r1):
        row[2].alignment = Alignment(wrap_text=True)
    s2 = wb.create_sheet(T("Sources", "Джерела"))
    for k in dv["sources"]:
        lab, url = _src(k, lg)
        s2.append([k, lab, url])
    s2.column_dimensions["B"].width = 120
    s2.column_dimensions["C"].width = 80
    wb.save(path)
