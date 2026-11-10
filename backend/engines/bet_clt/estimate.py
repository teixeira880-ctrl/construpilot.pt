"""Orçamento final / devis final d'une maison CLT, aux prix d'un marché donné (UA : hryvnias, avec contre-valeur en euros).

Quantités : relevé du moteur CLT (planchers, murs, fondations, assemblages, stabilité) + enveloppe de l'étude thermique
(façades, baies, toiture, plancher bas) + données du plan non modélisées par la trame (`estimate.basement`, `terrace`,
`partitions_m2`, `bathrooms`…). Prix unitaires : base datée et sourcée ci-dessous ; chaque prix non publié est marqué
« hypothèse » et doit être remplacé par l'offre de l'entreprise (fabricant CLT, maçon, menuisier…).
Déterministe, sans IA.
"""
from __future__ import annotations

from datetime import date as _date
from pathlib import Path

from .lang import num, t

# ------------------------------------------------------------------------------------------------------------------------
# Base de prix UA — hryvnias (UAH) hors TVA (ПДВ 20 %), fourni-posé sauf mention. Taux de change BNU du 09/11/2026.
EUR_UAH = 50.65
SOURCES = {     # (FR, PT, EN, UK), url
    "S1": (("Технологія Бетону — tarif 04.2026 : C20/25 4 152–4 827 грн/m³, C25/30 4 344–5 055 грн/m³",
            "Технологія Бетону — tabela 04.2026: C20/25 4 152–4 827 грн/m³, C25/30 4 344–5 055 грн/m³",
            "Tekhnolohiia Betonu — price list 04.2026: C20/25 4,152–4,827 UAH/m³, C25/30 4,344–5,055 UAH/m³",
            "Технологія Бетону — прайс 04.2026: C20/25 4 152–4 827 грн/м³, C25/30 4 344–5 055 грн/м³"), "https://tehbeton.com.ua/price/"),
    "S2": (("Prom.ua — acier HA A500C 45 250–45 860 грн/t (TBK Metalbud), 11.2026", "Prom.ua — aço A500C 45 250–45 860 грн/t (TBK Metalbud), 11.2026",
            "Prom.ua — A500C rebar 45,250–45,860 UAH/t (TBK Metalbud), 11.2026", "Prom.ua — арматура А500С 45 250–45 860 грн/т (ТБК Металбуд), 11.2026"),
           "https://prom.ua/Armatura-a500.html"),
    "S3": (("SS.LV — panneaux CLT 660 €/m³ (fabricant balte) ; CLT Rezult ne publie pas de prix : 700 €/m³ retenus, à confirmer par le fabricant",
            "SS.LV — painéis CLT 660 €/m³ (fabricante báltico); a CLT Rezult não publica preços: 700 €/m³ adotados, a confirmar pelo fabricante",
            "SS.LV — CLT panels €660/m³ (Baltic manufacturer); CLT Rezult publishes no prices: €700/m³ used, to be confirmed by the manufacturer",
            "SS.LV — панелі CLT 660 €/м³ (балтійський виробник); CLT Rezult не публікує цін: прийнято 700 €/м³, підтверджує виробник"),
           "https://www.ss.lv/msg/ru/construction/materials/timber/clt-panels/cxgfng.html"),
    "S4": (("Epicentr — laine minérale 100 mm 149–348 грн/m², 11.2026", "Epicentr — lã mineral 100 mm 149–348 грн/m², 11.2026",
            "Epicentr — mineral wool 100 mm 149–348 UAH/m², 11.2026", "Епіцентр — мінвата 100 мм 149–348 грн/м², 11.2026"),
           "https://epicentrk.ua/ua/shop/bazaltovaya-i-mineralnaya-vata/fs/tolshchina-100/"),
    "S5": (("MehBud — main-d'œuvre isolation de façade 550–650 грн/m² (2026)", "MehBud — mão de obra isolamento de fachada 550–650 грн/m² (2026)",
            "MehBud — façade insulation labour 550–650 UAH/m² (2026)", "MehBud — роботи з утеплення фасаду 550–650 грн/м² (2026)"),
           "https://blog.mehbud.com.ua/en/other/ukraines-energy-efficient-materials-market-analysis"),
    "S6": (("Prom.ua — XPS 100 mm 397–455 грн/m², 11.2026", "Prom.ua — XPS 100 mm 397–455 грн/m², 11.2026", "Prom.ua — XPS 100 mm 397–455 UAH/m², 11.2026",
            "Prom.ua — XPS 100 мм 397–455 грн/м², 11.2026"), "https://prom.ua/Stirodur-100mm.html"),
    "S7": (("Zaxid.net (06.07.2026) — fenêtres PVC 5 500–6 500 грн/m², aluminium ≈ 15 000 грн/m², pose ≈ 30 % de la commande",
            "Zaxid.net (06.07.2026) — janelas PVC 5 500–6 500 грн/m², alumínio ≈ 15 000 грн/m², montagem ≈ 30 % da encomenda",
            "Zaxid.net (06.07.2026) — PVC windows 5,500–6,500 UAH/m², aluminium ≈ 15,000 UAH/m², installation ≈ 30 % of the order",
            "Zaxid.net (06.07.2026) — вікна ПВХ 5 500–6 500 грн/м², алюміній ≈ 15 000 грн/м², монтаж ≈ 30 % замовлення"),
           "https://zaxid.net/tsini_na_sklopaketi_v_ukrayini_2026_zrostannya_40_vidsotkiv_yaka_prichina_n1640940"),
    "S8": (("Epicentr — plaque de plâtre 12,5 mm 138–417 грн/m², 11.2026", "Epicentr — gesso cartonado 12,5 mm 138–417 грн/m², 11.2026",
            "Epicentr — 12.5 mm plasterboard 138–417 UAH/m², 11.2026", "Епіцентр — гіпсокартон 12,5 мм 138–417 грн/м², 11.2026"),
           "https://epicentrk.ua/ua/shop/lvov/gipsokarton/fs/tolshchina-12-5/"),
    "S9": (("Sika Ukraine — tarif membranes PVC Sikaplan (29.06.2026), HT", "Sika Ucrânia — tabela membranas PVC Sikaplan (29.06.2026), s/IVA",
            "Sika Ukraine — Sikaplan PVC membrane price list (29.06.2026), excl. VAT", "Sika Україна — прайс ПВХ-мембран Sikaplan (29.06.2026), без ПДВ"),
           "https://ukr.sika.com/dms/getdocument.get/dd72ad3d-28f1-43ad-8955-7c49ba323435/PriceList_Roofing%2026-06-2026.pdf"),
    "S10": (("Rabotniki.ua (09.11.2026) — maison clés en main prête à finir 24 500–48 000 грн/m² (moy. 37 250), avec finitions 40 880 грн/m²",
             "Rabotniki.ua (09.11.2026) — casa chave na mão pronta a acabar 24 500–48 000 грн/m² (média 37 250), com acabamentos 40 880 грн/m²",
             "Rabotniki.ua (09.11.2026) — turnkey house ready for finishing 24,500–48,000 UAH/m² (avg 37,250), finished 40,880 UAH/m²",
             "Rabotniki.ua (09.11.2026) — будинок під ключ під чистову 24 500–48 000 грн/м² (сер. 37 250), з оздобленням 40 880 грн/м²"),
            "https://www.rabotniki.ua/uk/price/stroitelstvo-doma-pod-klyuch-pod-chistovuyu-otdelku"),
    "H": (("Hypothèse ConstruPilot (prix de marché UA 2026 non publié) — à remplacer par le devis de l'entreprise",
           "Hipótese ConstruPilot (preço de mercado UA 2026 não publicado) — a substituir pela proposta da empresa",
           "ConstruPilot assumption (UA 2026 market price not published) — to be replaced by the contractor's quote",
           "Припущення ConstruPilot (ринкова ціна 2026 не опублікована) — замінити пропозицією підрядника"), ""),
}


def source(k: str) -> tuple[str, str]:
    lab, url = SOURCES[k]
    return t(*lab), url


# code : (prix UAH, source)
UA = {
    "excav": (420, "H"), "backfill": (260, "H"),
    "conc_fnd": (7400, "S1"), "conc_wall": (9900, "S1"), "conc_slab": (8800, "S1"), "conc_plinth": (9900, "S1"), "rebar": (68, "S2"),
    "bsmt_wp": (680, "H"), "bsmt_xps": (640, "S6"), "drain": (1150, "H"), "lean": (5200, "S1"),
    "clt_supply": (round(700 * EUR_UAH), "S3"), "clt_pose": (650, "H"), "spline": (720, "H"), "bracket": (1150, "H"), "holddown": (3400, "H"),
    "screws": (95, "H"), "crane": (38000, "H"), "sole": (950, "H"),
    "ext_ins": (1850, "S4"), "membrane": (95, "H"), "plinth_xps": (780, "S6"),
    "roof_xps": (620, "S6"), "roof_lwc": (560, "S1"), "roof_pvc": (1250, "S9"), "roof_gravel": (190, "H"), "roof_edge": (1400, "H"),
    "win_pvc": (8500, "S7"), "win_alu": (16500, "S7"), "door_ext": (48000, "H"),
    "lining": (720, "S8"), "ceiling": (980, "S8"), "partition": (1950, "S8"), "acoustic": (420, "H"),
    "screed": (780, "H"), "flooring": (1450, "H"), "tiling": (2300, "H"), "paint": (290, "H"), "doors_int": (16500, "H"), "stairs": (145000, "H"),
    "elec": (1650, "H"), "bath": (98000, "H"), "kitchen": (48000, "H"), "hp": (520000, "H"), "ufh": (1350, "H"), "mvhr": (185000, "H"), "pv": (55000, "H"),
    "terrace": (9800, "H"),
}
PCT = {"site": 0.03, "design": 0.05, "contingency": 0.05}
VAT = 0.20


def _L(code, lot, des, unit, qty, P=UA):
    pu, src = P[code]
    return {"code": code, "lot": lot, "des": des, "unit": unit, "qty": round(float(qty), 2), "pu": float(pu), "src": src} if qty and qty > 0 else None


def build(m, r: dict, th: dict | None) -> dict:
    est = m.raw.get("estimate") or {}
    q = r["quantities"]
    lines = []

    def add(*a):
        x = _L(*a)
        if x:
            lines.append(x)
    bs = est.get("basement") or {}
    # ---------------------------------------------------------------- 1 cave BA (plan -1)
    l1 = t("1. Sous-sol (niveau -1) en béton armé", "1. Cave (piso -1) em betão armado", "1. Basement (level -1) in reinforced concrete", "1. Підвал (рівень -1) із залізобетону")
    if bs:
        A, Hb, P = float(bs["area"]), float(bs.get("height", 2.8)), float(bs.get("perimeter", 0))
        add("excav", l1, t("Terrassement en pleine masse (évacuation comprise)", "Escavação geral (com transporte a vazadouro)", "Bulk excavation (incl. disposal)",
                           "Розробка котловану (з вивезенням)"), "m³", A * (Hb + 0.5) * 1.15)
        add("lean", l1, t("Béton de propreté 5 cm", "Betão de limpeza 5 cm", "Blinding concrete 5 cm", "Бетонна підготовка 5 см"), "m³", A * 0.05)
        add("conc_slab", l1, t("Radier BA 25 cm", "Ensoleiramento BA 25 cm", "RC raft 25 cm", "З/б фундаментна плита 25 см"), "m³", A * 0.25)
        add("conc_wall", l1, t("Voiles enterrés BA 25 cm", "Muros de cave BA 25 cm", "RC retaining walls 25 cm", "З/б стіни підвалу 25 см"), "m³", P * Hb * 0.25)
        add("rebar", l1, t("Aciers HA radier et voiles (≈ 95 kg/m³)", "Armaduras ensoleiramento e muros (≈ 95 kg/m³)", "Reinforcement raft and walls (≈ 95 kg/m³)",
                           "Арматура плити та стін (≈ 95 кг/м³)"), "kg", (A * 0.25 + P * Hb * 0.25) * 95)
        add("bsmt_wp", l1, t("Étanchéité des voiles enterrés", "Impermeabilização dos muros enterrados", "Waterproofing of buried walls", "Гідроізоляція стін підвалу"), "m²", P * Hb)
        add("bsmt_xps", l1, t("Isolant XPS 100 mm des voiles enterrés", "Isolamento XPS 100 mm dos muros enterrados", "XPS 100 mm on buried walls",
                              "Утеплення XPS 100 мм стін підвалу"), "m²", P * Hb)
        add("drain", l1, t("Drainage périphérique", "Drenagem periférica", "Perimeter drain", "Пристінний дренаж"), "m", P)
        add("backfill", l1, t("Remblaiement périphérique", "Aterro periférico", "Perimeter backfill", "Зворотна засипка"), "m³", P * Hb * 0.8)
    # ---------------------------------------------------------------- 2 fondations / plancher bas
    l2 = t("2. Fondations et plancher bas", "2. Fundações e laje do R/C", "2. Foundations and ground-floor slab", "2. Фундаменти та перекриття над підвалом")
    if not bs:
        add("excav", l2, t("Fouilles des semelles", "Escavação de sapatas", "Footing excavation", "Розробка під фундаменти"), "m³", q["excav_m3"])
        add("conc_fnd", l2, t("Béton des semelles (coffrage compris)", "Betão em sapatas (com cofragem)", "Footing concrete (incl. formwork)", "Бетон фундаментів (з опалубкою)"),
            "m³", q["conc_fnd_m3"])
    add("conc_slab", l2, t("Dalle BA du rez-de-chaussée sur sous-sol" if bs else "Dallage BA sur hérisson", "Laje BA do R/C sobre a cave" if bs else "Laje térrea BA",
                           "RC ground-floor slab over basement" if bs else "RC ground slab", "З/б перекриття над підвалом" if bs else "З/б плита по ґрунту"),
        "m³", (q["slab_area"] * 0.20) if bs else q["conc_slab_m3"])
    add("conc_plinth", l2, t("Soubassement BA h 30 cm (arase étanche sous CLT)", "Murete BA h 30 cm (corte de capilaridade sob CLT)", "RC upstand h 30 cm (DPC under CLT)",
                             "З/б цоколь h 30 см (гідроізоляція під CLT)"), "m³", q["conc_plinth_m3"])
    add("rebar", l2, t("Aciers HA", "Armaduras A500", "Reinforcement A500C", "Арматура А500С"), "kg", (q["slab_area"] * 0.20 * 100) if bs else q["rebar_kg"])
    # ---------------------------------------------------------------- 3 structure CLT
    l3 = t("3. Structure bois massif CLT", "3. Estrutura em madeira maciça CLT", "3. CLT mass timber structure", "3. Конструкції CLT")
    fl = ", ".join(sorted({f["clt"]["name"] for f in r["floors"]}))
    wl = ", ".join(sorted({s["layup"] for w in r["walls"] for s in w["segs"]}))
    add("clt_supply", l3, t(f"Panneaux CLT de planchers et toiture ({fl}), usinés CNC, livrés", f"Painéis CLT de pisos e cobertura ({fl}), maquinados CNC, entregues",
                            f"CLT floor and roof panels ({fl}), CNC-machined, delivered", f"Панелі CLT перекриттів і покрівлі ({fl}), обробка ЧПК, доставка"), "m³", q["clt_m3"])
    add("clt_supply", l3, t(f"Panneaux CLT de murs ({wl}), usinés CNC, livrés", f"Painéis CLT de paredes ({wl}), maquinados CNC, entregues",
                            f"CLT wall panels ({wl}), CNC-machined, delivered", f"Стінові панелі CLT ({wl}), обробка ЧПК, доставка"), "m³", q["wall_m3"])
    add("clt_pose", l3, t("Montage des panneaux CLT (levage, calage, vissage)", "Montagem dos painéis CLT (elevação, calços, aparafusamento)",
                          "CLT panel erection (lifting, shimming, screwing)", "Монтаж панелей CLT (підйом, вирівнювання, кріплення)"), "m²", q["clt_m2"] + q["wall_m2"])
    add("sole", l3, t("Lisse d'assise et membrane d'arase", "Soleira e membrana de corte", "Sole plate and damp-proof membrane", "Лежень і відсічна гідроізоляція"), "m",
        sum(s.get("L", w["L"]) for w in r["walls"] for s in w["segs"][:1]))
    add("spline", l3, t("Éclissages des joints CLT (LVL + vis)", "Juntas CLT (LVL + parafusos)", "CLT joint splines (LVL + screws)", "Накладки стиків CLT (LVL + шурупи)"), "m", q["spline_m"])
    lat = (r["lateral"].get("walls") or {})
    nb = sum(v["brackets"] for v in lat.values()) * len(m.levels)
    nh = sum(v["holddowns"] for v in lat.values()) * len(m.levels)
    add("bracket", l3, t("Équerres de cisaillement", "Esquadros de corte", "Shear brackets", "Кутики зсуву"), "u", nb)
    add("holddown", l3, t("Ancrages hold-down (tiges M16)", "Ancoragens hold-down (varões M16)", "Hold-downs (M16 rods)", "Анкери hold-down (шпильки M16)"), "u", nh)
    add("screws", l3, t("Vis d'assemblage murs / planchers", "Parafusos de ligação paredes / pisos", "Wall / floor connection screws", "Шурупи з'єднань стін / перекриттів"), "u",
        round((q["clt_m2"] + q["wall_m2"]) * 1.6))
    days = max(4, round((q["clt_m2"] + q["wall_m2"]) / 120))
    add("crane", l3, t("Grue mobile + équipe de levage", "Grua móvel + equipa de elevação", "Mobile crane + lifting crew", "Автокран + монтажна бригада"),
        t("j", "dia", "day", "дн"), days)
    # ---------------------------------------------------------------- 4 enveloppe
    l4 = t("4. Enveloppe, isolation et étanchéité", "4. Envolvente, isolamento e impermeabilização", "4. Envelope, insulation and waterproofing",
           "4. Огороджувальні конструкції, утеплення, гідроізоляція")
    fac = sum(th["walls"].values()) if th else q["wall_m2"] * 0.5
    win = th["windows"] if th else {}
    roof = th["roof"] if th else q["slab_area"]
    add("ext_ins", l4, t("Isolation extérieure laine minérale 100 mm + enduit / parement", "Isolamento exterior lã mineral 100 mm + reboco / revestimento",
                         "External mineral-wool insulation 100 mm + render / cladding", "Зовнішнє утеплення мінватою 100 мм + штукатурка / облицювання"), "m²", fac)
    add("membrane", l4, t("Membrane pare-pluie / frein-vapeur", "Membrana pára-vapor / respirável", "Breather / vapour-control membrane", "Вітро-пароізоляційна мембрана"), "m²", fac)
    per0 = sum(th["geometry"]["storeys"][0]["fac"].values()) if th else 0
    add("plinth_xps", l4, t("Isolation XPS 100 mm du soubassement", "Isolamento XPS 100 mm do soco", "XPS 100 mm plinth insulation", "Утеплення цоколя XPS 100 мм"), "m²", per0 * 0.6)
    add("roof_xps", l4, t("Toiture : panneau XPS 100 mm thermo-acoustique", "Cobertura: painel XPS 100 mm térmico e acústico", "Roof: XPS 100 mm thermal-acoustic board",
                          "Покрівля: плити XPS 100 мм"), "m²", roof)
    add("roof_lwc", l4, t("Toiture : béton léger de forme de pente ±100 mm", "Cobertura: betão leve de pendentes ±100 mm", "Roof: lightweight concrete screed to falls ±100 mm",
                          "Покрівля: ухилоутворюючий легкий бетон ±100 мм"), "m²", roof)
    add("roof_pvc", l4, t("Toiture : membrane PVC + géotextile", "Cobertura: membrana PVC + geotêxtil", "Roof: PVC membrane + geotextile", "Покрівля: ПВХ-мембрана + геотекстиль"), "m²", roof * 1.08)
    add("roof_gravel", l4, t("Toiture : lestage galets", "Cobertura: seixo rolado", "Roof: gravel ballast", "Покрівля: баласт з гальки"), "m²", roof)
    add("roof_edge", l4, t("Acrotères, relevés, évacuations EP", "Platibandas, remates, tubos de queda", "Parapets, upstands, rainwater outlets", "Парапети, примикання, водостоки"), "m",
        sum(sum(st["fac"].values()) + st["party"] for st in th["geometry"]["storeys"]) * 0.75 if th else 0)
    south = max(win, key=lambda k: win[k]) if win else None
    add("win_alu", l4, t(f"Baies coulissantes aluminium RPT triple vitrage (façade {south})", f"Caixilharia de correr alumínio RPT vidro triplo (fachada {south})",
                         f"Thermally broken aluminium sliding doors, triple glazing ({south} façade)", f"Алюмінієві розсувні системи з термомостом, потрійне скло (фасад {south})"),
        "m²", win.get(south, 0) if south else 0)
    add("win_pvc", l4, t("Fenêtres PVC Uw 1,3 (autres façades)", "Janelas PVC Uw 1,3 (outras fachadas)", "PVC windows Uw 1.3 (other façades)", "Вікна ПВХ Uw 1,3 (інші фасади)"),
        "m²", sum(v for k, v in win.items() if k != south))
    add("door_ext", l4, t("Porte d'entrée isolante", "Porta de entrada isolada", "Insulated entrance door", "Утеплені вхідні двері"), "u", 1)
    # ---------------------------------------------------------------- 5 second œuvre
    l5 = t("5. Doublages, cloisons, plafonds et finitions", "5. Revestimentos, divisórias, tetos e acabamentos", "5. Linings, partitions, ceilings and finishes",
           "5. Обшивка, перегородки, стелі, оздоблення")
    gfa = sum(st["area"] for st in th["geometry"]["storeys"]) if th else q["slab_area"]
    part = float(est.get("partitions_m2") or 0)
    add("lining", l5, t("Doublage plaque de plâtre BA13 ×2 sur murs CLT", "Revestimento gesso cartonado BA13 ×2 nas paredes CLT", "BA13 ×2 plasterboard lining on CLT walls",
                        "Обшивка стін CLT ГКП 12,5 мм у 2 шари"), "m²", q["wall_m2"] * 1.5)
    add("ceiling", l5, t("Plafonds suspendus BA15 sous planchers CLT", "Tetos suspensos BA15 sob pisos CLT", "BA15 suspended ceilings under CLT floors", "Підвісні стелі ГКП 15 мм"), "m²", gfa)
    add("partition", l5, t("Cloisons sur ossature 48 mm + laine de roche + BA13 ×2 (2 faces)", "Divisórias estrutura 48 mm + lã de rocha + BA13 ×2 (2 faces)",
                           "Partitions 48 mm studs + rock wool + 2×BA13 both faces", "Перегородки каркас 48 мм + мінвата + ГКП ×2 з двох боків"), "m²", part)
    add("acoustic", l5, t("Résilient acoustique sous chape", "Membrana acústica sob betonilha", "Acoustic underlay under screed", "Звукоізоляційна мембрана під стяжку"), "m²",
        sum(f["area"] for f in r["floors"] if not f["roof"]))
    add("screed", l5, t("Chape béton léger 100 mm", "Betonilha de betão leve 100 mm", "Lightweight concrete screed 100 mm", "Стяжка з легкого бетону 100 мм"), "m²", gfa)
    add("flooring", l5, t("Revêtements de sol (parquet contrecollé)", "Pavimentos (soalho multicamada)", "Floor finishes (engineered wood)", "Підлогове покриття (інженерна дошка)"), "m²",
        gfa * 0.80)
    nbath = int(est.get("bathrooms") or 0) + int(est.get("wc") or 0)
    add("tiling", l5, t("Carrelage sols et murs des pièces d'eau", "Cerâmico pavimentos e paredes das instalações sanitárias", "Wet-room floor and wall tiling",
                        "Плитка підлоги та стін санвузлів"), "m²", nbath * 22)
    add("paint", l5, t("Peinture murs et plafonds", "Pintura de paredes e tetos", "Wall and ceiling painting", "Фарбування стін і стель"), "m²", q["wall_m2"] * 1.5 + gfa + part * 2)
    add("doors_int", l5, t("Portes intérieures", "Portas interiores", "Internal doors", "Міжкімнатні двері"), "u", int(est.get("doors") or 0))
    add("stairs", l5, t("Escaliers bois (2 volées)", "Escadas em madeira (2 lanços)", "Timber stairs (2 flights)", "Дерев'яні сходи (2 марші)"), "u", int(est.get("stairs") or 0))
    # ---------------------------------------------------------------- 6 lots techniques
    l6 = t("6. Lots techniques", "6. Instalações técnicas", "6. Building services", "6. Інженерні системи")
    add("elec", l6, t("Électricité courants forts / faibles (sous-sol compris)", "Instalação elétrica e telecomunicações (cave incluída)",
                      "Electrical and low-voltage installation (basement included)", "Електромонтаж і слабкі струми (з підвалом)"), "m²",
        gfa + float(bs.get("area") or 0))
    add("bath", l6, t("Salles d'eau équipées (réseaux + sanitaires)", "Instalações sanitárias equipadas (redes + louças)", "Fitted bathrooms (pipework + sanitaryware)",
                      "Санвузли під ключ (мережі + сантехніка)"), "u", nbath)
    add("kitchen", l6, t("Alimentation / évacuation cuisine", "Abastecimento / esgoto da cozinha", "Kitchen water supply / drainage", "Водопостачання / каналізація кухні"), "u",
        int(est.get("kitchens") or 0))
    kw = (th["phi_w"] / 1000) if th else 8.0
    add("hp", l6, t(f"PAC air-eau {num(max(6.0, round(kw * 1.2)), 0)} kW + ballon ECS", f"Bomba de calor ar-água {num(max(6.0, round(kw * 1.2)), 0)} kW + depósito AQS",
                    f"Air-to-water heat pump {num(max(6.0, round(kw * 1.2)), 0)} kW + DHW tank", f"Тепловий насос повітря-вода {num(max(6.0, round(kw * 1.2)), 0)} кВт + бойлер ГВП"),
        "u", 1)
    add("ufh", l6, t("Plancher chauffant-rafraîchissant", "Piso radiante (aquecimento / arrefecimento)", "Underfloor heating / cooling", "Тепла підлога (опалення / охолодження)"),
        "m²", gfa * 0.75)
    add("mvhr", l6, t("Ventilation double flux", "Ventilação mecânica com recuperação de calor", "Mechanical ventilation with heat recovery", "Припливно-витяжна вентиляція з рекуперацією"),
        "u", 1)
    pv = float(th.get("pv_kwp") or 0) if th else 0
    add("pv", l6, t("Photovoltaïque (kWc)", "Fotovoltaico (kWp)", "Photovoltaics (kWp)", "Сонячна електростанція (кВт)"), "kWp", pv)
    # ---------------------------------------------------------------- 7 extérieurs
    ter = float((est.get("terrace") or {}).get("area") or 0)
    if ter:
        add("terrace", t("7. Terrasse couverte", "7. Terraço coberto", "7. Covered terrace", "7. Крита тераса"),
            t("Terrasse bois + couverture CLT", "Deck em madeira + cobertura CLT", "Timber deck + CLT canopy", "Дерев'яна тераса + навіс CLT"), "m²", ter)
    for x in lines:
        x["tot"] = round(x["qty"] * x["pu"], 2)
    works = sum(x["tot"] for x in lines)
    extra = [{"key": k, "lab": lab, "pct": PCT[k], "tot": round(works * PCT[k], 2)} for k, lab in (
        ("site", t("Installation de chantier", "Estaleiro", "Site set-up", "Облаштування майданчика")),
        ("design", t("Études d'exécution et suivi (BET, fabricant)", "Projeto de execução e acompanhamento", "Shop drawings and supervision", "Робоча документація та нагляд")),
        ("contingency", t("Aléas", "Imprevistos", "Contingency", "Непередбачені витрати")))]
    ht = works + sum(e["tot"] for e in extra)
    gross = (sum(st["area"] for st in th["geometry"]["storeys"]) if th else q["slab_area"]) + (float(bs.get("area") or 0))
    return {"lines": lines, "extra": extra, "works": round(works, 2), "ht": round(ht, 2), "vat": VAT, "ttc": round(ht * (1 + VAT), 2), "eur": EUR_UAH,
            "gross": round(gross, 1), "per_m2": round(ht / gross, 0) if gross else 0.0, "market": "UA", "currency": "грн / UAH",
            "sources": sorted({x["src"] for x in lines}, key=lambda s: (s == "H", len(s), s))}


# ============================================================================================ PDF
def write_pdf(path, m, e: dict, branding_name: str | None = None):
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    from engines.bet_core import brand as B

    from .report import H1, H2, P, SM, SMH, _esc
    br = B.get()
    H1.textColor = br.accent
    H2.textColor = br.accent
    pr = m.project
    s = []
    s.append(Paragraph(_esc(t("Devis estimatif final — prix du marché ukrainien", "Orçamento final — preços do mercado ucraniano", "Final cost estimate — Ukrainian market prices",
                              "Остаточний кошторис — ціни ринку України")), H1))
    s.append(Paragraph(_esc(f"{pr.get('name', '')} — {pr.get('address', '')}"), P))
    s.append(Paragraph(_esc(t(f"Prix hors TVA en hryvnias (грн), contre-valeur en euros au taux BNU du 09/11/2026 : 1 € = {num(e['eur'])} грн. Date : {_date.today().strftime('%d/%m/%Y')}.",
                              f"Preços sem IVA em hryvnias (грн), contravalor em euros à taxa do BNU de 09/11/2026: 1 € = {num(e['eur'])} грн. Data: {_date.today().strftime('%d/%m/%Y')}.",
                              f"Prices excl. VAT in hryvnias (UAH), euro equivalent at the NBU rate of 09/11/2026: €1 = {num(e['eur'])} UAH. Date: {_date.today().strftime('%d/%m/%Y')}.",
                              f"Ціни без ПДВ у гривнях, еквівалент у євро за курсом НБУ на 09.11.2026: 1 € = {num(e['eur'])} грн. Дата: {_date.today().strftime('%d.%m.%Y')}.")), SM))
    s.append(Spacer(1, 4))
    # synthèse
    lots = {}
    for x in e["lines"]:
        lots[x["lot"]] = lots.get(x["lot"], 0.0) + x["tot"]
    rows = [[t("Lot", "Capítulo", "Package", "Розділ"), t("Montant HT (грн)", "Montante s/IVA (грн)", "Amount excl. VAT (UAH)", "Сума без ПДВ (грн)"), "€", "%"]]
    for k, v in lots.items():
        rows.append([k, num(v, 0), num(v / e["eur"], 0), num(100 * v / e["ht"], 1)])
    for x in e["extra"]:
        rows.append([f"{x['lab']} ({num(100 * x['pct'], 0)} %)", num(x["tot"], 0), num(x["tot"] / e["eur"], 0), num(100 * x["tot"] / e["ht"], 1)])
    rows.append([t("TOTAL HT", "TOTAL s/IVA", "TOTAL excl. VAT", "РАЗОМ без ПДВ"), num(e["ht"], 0), num(e["ht"] / e["eur"], 0), "100"])
    rows.append([t("TVA 20 %", "IVA 20 %", "VAT 20 %", "ПДВ 20 %"), num(e["ht"] * e["vat"], 0), num(e["ht"] * e["vat"] / e["eur"], 0), ""])
    rows.append([t("TOTAL TTC", "TOTAL c/IVA", "TOTAL incl. VAT", "РАЗОМ з ПДВ"), num(e["ttc"], 0), num(e["ttc"] / e["eur"], 0), ""])

    def tbl(rows, widths, bold_last=0, right=()):
        data = [[Paragraph(_esc(c), SMH if i == 0 else SM) for c in r] for i, r in enumerate(rows)]
        tb = Table(data, colWidths=[w * mm for w in widths], repeatRows=1)
        st = [("LINEBELOW", (0, 0), (-1, -1), 0.25, colors.Color(0.84, 0.85, 0.87)), ("VALIGN", (0, 0), (-1, -1), "TOP"),
              ("LEFTPADDING", (0, 0), (-1, -1), 3), ("RIGHTPADDING", (0, 0), (-1, -1), 3), ("TOPPADDING", (0, 0), (-1, -1), 2), ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
              ("BACKGROUND", (0, 0), (-1, 0), br.accent)]
        for k in range(bold_last):
            st.append(("BACKGROUND", (0, len(rows) - 1 - k), (-1, len(rows) - 1 - k), br.tint))
        tb.setStyle(TableStyle(st))
        return tb
    try:
        from reportlab.platypus import Image as RLImage
        from . import premium
        png = premium.estimate_chart(e, Path(str(path) + ".chart.png"))
        s.append(RLImage(str(png), width=178 * mm, height=89 * mm))
    except Exception:  # noqa: BLE001 — graphique facultatif
        png = None
    s.append(tbl(rows, (92, 34, 26, 22), bold_last=3))
    s.append(Spacer(1, 4))
    s.append(Paragraph(_esc(t(f"Ratio : {num(e['per_m2'], 0)} грн HT/m² de surface de plancher brute ({num(e['gross'], 1)} m², sous-sol compris) — "
                              f"repère marché ukrainien 2026 : maison prête à finir 24 500–48 000 грн/m², avec finitions ≈ 40 880 грн/m² [S10].",
                              f"Rácio: {num(e['per_m2'], 0)} грн s/IVA/m² de área bruta ({num(e['gross'], 1)} m², cave incluída) — "
                              f"referência do mercado ucraniano 2026: casa pronta a acabar 24 500–48 000 грн/m², com acabamentos ≈ 40 880 грн/m² [S10].",
                              f"Ratio: {num(e['per_m2'], 0)} UAH excl. VAT per m² gross floor area ({num(e['gross'], 1)} m², basement included) — "
                              f"Ukrainian market benchmark 2026: shell-and-core house 24,500–48,000 UAH/m², finished ≈ 40,880 UAH/m² [S10].",
                              f"Питомий показник: {num(e['per_m2'], 0)} грн без ПДВ/м² загальної площі ({num(e['gross'], 1)} м² з підвалом) — "
                              f"ринкові орієнтири 2026: будинок під чистове оздоблення 24 500–48 000 грн/м², з оздобленням ≈ 40 880 грн/м² [S10].")), P))
    s.append(Spacer(1, 6))
    s.append(Paragraph(_esc(t("Détail quantitatif et estimatif", "Mapa de quantidades e preços", "Bill of quantities", "Відомість обсягів і вартості")), H2))
    rows = [[t("Désignation", "Designação", "Description", "Найменування"), t("U", "Un.", "Unit", "Од."), t("Qté", "Qtd.", "Qty", "К-сть"),
             t("PU грн", "PU грн", "Rate UAH", "Ціна грн"), t("Total грн", "Total грн", "Total UAH", "Сума грн"), t("Src", "Fonte", "Src", "Дж.")]]
    cur_lot = None
    for x in e["lines"]:
        if x["lot"] != cur_lot:
            rows.append([x["lot"], "", "", "", "", ""])
            cur_lot = x["lot"]
        rows.append([x["des"], x["unit"], num(x["qty"], 2 if x["qty"] < 100 else 1), num(x["pu"], 0), num(x["tot"], 0), x["src"]])
    tb = tbl(rows, (82, 12, 18, 20, 26, 12))
    st = [("BACKGROUND", (0, i), (-1, i), br.tint2) for i, r in enumerate(rows) if i and r[1] == "" and r[2] == ""]
    st += [("FONTNAME", (0, i), (-1, i), "DVB") for i, r in enumerate(rows) if i and r[1] == "" and r[2] == ""]
    tb.setStyle(TableStyle(st))
    s.append(tb)
    s.append(Spacer(1, 6))
    s.append(Paragraph(_esc(t("Sources des prix", "Fontes dos preços", "Price sources", "Джерела цін")), H2))
    for k in e["sources"]:
        lab, url = source(k)
        s.append(Paragraph(f"<b>{_esc(k)}</b> — {_esc(lab)}" + (f" — <font color='#2a5db0'>{_esc(url)}</font>" if url else ""), SM))
    s.append(Spacer(1, 4))
    s.append(Paragraph(_esc(t("Estimation pour décision : quantités issues du plan Home A et du pré-dimensionnement ConstruPilot ; les prix marqués H sont des hypothèses "
                              "à remplacer par les offres des entreprises (CLT Rezult pour le CLT). Ne vaut pas offre de prix.",
                              "Estimativa para decisão: quantidades da planta Home A e do pré-dimensionamento ConstruPilot; os preços marcados H são hipóteses "
                              "a substituir pelas propostas das empresas (CLT Rezult para o CLT). Não constitui proposta de preço.",
                              "Estimate for decision-making: quantities from the Home A drawings and the ConstruPilot preliminary design; prices marked H are assumptions "
                              "to be replaced by contractors' quotes (CLT Rezult for the CLT). Not a binding offer.",
                              "Оцінка для прийняття рішень: обсяги за кресленнями Home A та попереднім розрахунком ConstruPilot; ціни з позначкою H — припущення, "
                              "які слід замінити пропозиціями підрядників (CLT Rezult — для CLT). Не є комерційною пропозицією.")), SM))

    def page(c, doc):
        W, Hh = A4
        c.saveState()
        c.setFillColor(br.accent)
        c.rect(0, Hh - 12 * mm, W, 12 * mm, stroke=0, fill=1)
        c.setFillColor(colors.white)
        c.setFont("DVB", 9.5)
        c.drawString(18 * mm, Hh - 8 * mm, (branding_name or br.name or "ConstruPilot")[:40])
        c.setFont("DV", 7.2)
        c.drawRightString(W - 18 * mm, Hh - 8 * mm, t("Devis final — ", "Orçamento final — ", "Final estimate — ", "Кошторис — ") + str(pr.get("name", ""))[:60])
        c.setFillColor(colors.Color(0.45, 0.47, 0.50))
        c.drawRightString(W - 18 * mm, 10 * mm, str(doc.page))
        c.restoreState()
    doc = SimpleDocTemplate(str(path), pagesize=A4, leftMargin=16 * mm, rightMargin=16 * mm, topMargin=20 * mm, bottomMargin=18 * mm,
                            title=t("Devis final — ", "Orçamento final — ", "Final estimate — ", "Кошторис — ") + str(pr.get("name", "")))
    doc.build(s, onFirstPage=page, onLaterPages=page)
    if png:
        Path(png).unlink(missing_ok=True)
    return path


def write_xlsx(path, m, e: dict):
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill
    wb = Workbook()
    ws = wb.active
    ws.title = t("Devis UA", "Orçamento UA", "Estimate UA", "Кошторис UA")
    ws.append([m.project.get("name", "")])
    ws.append([t(f"Prix HT en грн — 1 € = {e['eur']} грн (BNU 09/11/2026) — prix modifiables", f"Preços s/IVA em грн — 1 € = {e['eur']} грн (BNU 09/11/2026) — editáveis",
                 f"Prices excl. VAT in UAH — €1 = {e['eur']} UAH (NBU 09/11/2026) — editable", f"Ціни без ПДВ у грн — 1 € = {e['eur']} грн (НБУ 09.11.2026) — можна змінювати")])
    ws.append([])
    hdr = [t("Lot", "Capítulo", "Package", "Розділ"), t("Désignation", "Designação", "Description", "Найменування"), t("Unité", "Un.", "Unit", "Од."),
           t("Quantité", "Quantidade", "Quantity", "К-сть"), t("PU грн", "PU грн", "Rate UAH", "Ціна грн"), t("Total грн", "Total грн", "Total UAH", "Сума грн"), "€", "Src"]
    ws.append(hdr)
    for c in ws[4]:
        c.font = Font(bold=True, color="FFFFFF")
        c.fill = PatternFill("solid", fgColor="1F4D3A")
    row = first = 5
    for x in e["lines"]:
        ws.append([x["lot"], x["des"], x["unit"], x["qty"], x["pu"], f"=D{row}*E{row}", f"=F{row}/{e['eur']}", x["src"]])
        row += 1
    last = row - 1
    ws.append([])
    row += 1
    tot_works = row
    ws.append(["", t("Total travaux", "Total trabalhos", "Works total", "Разом роботи"), "", "", "", f"=SUM(F{first}:F{last})", f"=F{row}/{e['eur']}"])
    row += 1
    for x in e["extra"]:
        ws.append(["", f"{x['lab']} ({int(x['pct'] * 100)} %)", "", "", "", f"=F{tot_works}*{x['pct']}", f"=F{row}/{e['eur']}"])
        row += 1
    ws.append(["", t("TOTAL HT", "TOTAL s/IVA", "TOTAL excl. VAT", "РАЗОМ без ПДВ"), "", "", "", f"=SUM(F{tot_works}:F{row - 1})", f"=F{row}/{e['eur']}"])
    row += 1
    ws.append(["", t("TVA 20 %", "IVA 20 %", "VAT 20 %", "ПДВ 20 %"), "", "", "", f"=F{row - 1}*{e['vat']}", f"=F{row}/{e['eur']}"])
    row += 1
    ws.append(["", t("TOTAL TTC", "TOTAL c/IVA", "TOTAL incl. VAT", "РАЗОМ з ПДВ"), "", "", "", f"=F{row - 2}+F{row - 1}", f"=F{row}/{e['eur']}"])
    for r_ in ws.iter_rows(min_row=first, max_row=row):
        for c in r_[3:7]:
            c.number_format = "#,##0.00"
    for col, w in zip("ABCDEFGH", (34, 70, 7, 11, 12, 15, 12, 6)):
        ws.column_dimensions[col].width = w
    ws2 = wb.create_sheet(t("Sources", "Fontes", "Sources", "Джерела"))
    for k in e["sources"]:
        ws2.append([k, *source(k)])
    ws2.column_dimensions["B"].width = 110
    ws.freeze_panes = "A5"
    wb.save(str(path))
    return path
