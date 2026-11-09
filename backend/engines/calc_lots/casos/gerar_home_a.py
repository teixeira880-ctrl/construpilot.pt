import sys, os, pickle, re
sys.path.insert(0, '/tmp/claude-0/homeA'); sys.path.insert(0, '/home/claude/teixeira880-ctrl/construpilot.pt/backend')
import modelo as H
import pymupdf
from engines.calc_lots import ucrania, especialidades as E, planos_especialidades as PE, gros_oeuvre as G, lingua_ucrania as LU, devis_ua as DV, premium as PR
OUT = '/tmp/claude-0/homeA/final/'; os.makedirs(OUT, exist_ok=True)
renders = pickle.load(open('/tmp/claude-0/homeA/renders.pkl', 'rb'))
PROJ = {"uk": "Житловий будинок, секція А — Rezult CLT", "en": "Residential house, Unit A — Rezult CLT"}
LOC = {"uk": "Київ, Україна", "en": "Kyiv, Ukraine"}
nv = ucrania.navantazhennya(ucrania.clima("kyiv"))
emp = PR.marca("clt-rezult")
res = {}
for lg in ("uk", "en"):
    T = (lambda en, uk: uk if lg == "uk" else en)
    # --- GO-01…08 pelo caminho ucraniano (cargas ДБН, ETA Rezult, R60)
    p = {"projeto_uk": PROJ["uk"], "projeto_en": PROJ["en"], "cidade": "kyiv", "uso": "residencial", "area_aquecida_m2": 200, "volume_m3": 560,
         "empresa": "clt-rezult", "sistema": "clt", "produto_clt": "rezult_clt", "fogo_min": 60, "elementos": H.envolvente("projeto"),
         "modelo_estrutural": H.modelo(), "render": False, "premium": False, "lingua": lg}
    o = ucrania.note(p)
    go_pdf = o["go"]["planos_pdf"]
    # --- modelo para especialidades / orçamento (mesmas cargas)
    m = H.modelo(lat=(lg == "en")); m["divisoes"] = H.divisoes(); m["mep"] = H.mep()
    m.update(projeto=PROJ[lg], local=LOC[lg], neve_kn_m2=round(nv["sm_kpa"], 2), produto_clt="rezult_clt", fogo_min=60)
    if lg == "en":
        m = LU.modelo_en(m)
    ver = G.verificar(m)
    r = E.calcular(m)
    mep_pdf = PE.planos(m, r, ver, "09/11/2026", lg)
    d = pymupdf.open(stream=go_pdf, filetype="pdf"); d.insert_pdf(pymupdf.open(stream=mep_pdf, filetype="pdf"))
    nomes = []
    for pg in d:
        t = pg.get_text().split("\n")
        nomes.append(next((x for x in t if re.match(r"^(GO|EL|WS|HT)-\d\d · ", x)), "—"))
    capa = {"titulo": T("Construction drawings", "Робочі креслення"), "subtitulo": T(f"{PROJ['en']} · structure, electrical, water & drainage, heating",
                                                                                  f"{PROJ['uk']} · конструкції, електрика, водопостачання і каналізація, опалення"),
            "local": LOC[lg], "data": "09.11.2026", "capa_imagem": renders[0][1],
            "kpis": [(T("Drawings", "Аркушів"), str(len(d)), T("A1 / A0 sheets", "аркуші A1 / A0")),
                     (T("Heat loss", "Тепловтрати"), f"{r['phi_total_w'] / 1000:.1f}".replace(".", "," if lg == "uk" else "."), T("kW at −22 °C", "кВт при −22 °C")),
                     (T("Circuits", "Груп"), str(len(r["eletricidade"]["circuitos"])), T(f"{r['quantidades']['tomadas']} sockets", f"{r['quantidades']['tomadas']} розеток")),
                     (T("UFH loops", "Контурів ТП"), str(r["quantidades"]["circuitos_pr"]), T(f"{r['quantidades']['piso_radiante_m2']:.0f} m²", f"{r['quantidades']['piso_radiante_m2']:.0f} м²"))],
            "indice": [(x[:70], i + 2) for i, x in enumerate(nomes)][:28]}
    plan = PR.embelezar(d.tobytes(garbage=3, deflate=True), capa, emp, n_nota=0, tr=(lambda s: s.split(" / ")[1] if lg == "en" and " / " in s else (s.split(" / ")[0] if " / " in s else s)))
    fn_p = OUT + {"uk": "Kreslennia_Budynok_A_RezultCLT_UK.pdf", "en": "Drawings_House_A_RezultCLT_EN.pdf"}[lg]
    open(fn_p, "wb").write(plan)
    # --- orçamento
    cn = PE.conectores(m)
    dv = DV.build(m, r, cn)
    body = DV.pdf(dv, lg, PROJ[lg], LOC[lg])
    nb = len(pymupdf.open(stream=body, filetype="pdf"))
    capa2 = {"titulo": T("Cost estimate", "Кошторис"), "subtitulo": T(f"{PROJ['en']} · detailed bill of quantities, Ukrainian prices, VAT 20 %",
                                                                     f"{PROJ['uk']} · детальна відомість обсягів, ціни України, ПДВ 20 %"),
             "local": LOC[lg], "data": "09.11.2026", "capa_imagem": renders[1][1],
             "kpis": [(T("Total incl. VAT", "Разом з ПДВ"), f"{dv['ttc'] / 1e6:.2f} M".replace(".", "," if lg == "uk" else "."), T("UAH", "грн")),
                      (T("≈ euro", "≈ євро"), f"{dv['ttc'] / dv['eur'] / 1000:.0f} k", T("€ (NBU rate)", "€ (курс НБУ)")),
                      (T("Per m² gross", "За м²"), f"{dv['per_m2_ttc']:,.0f}".replace(",", " "), T("UAH/m² incl. VAT", "грн/м² з ПДВ")),
                      (T("Line items", "Позицій"), str(len(dv["lines"])), T(f"{len(dv['lots'])} packages", f"{len(dv['lots'])} розділів"))],
             "indice": [((lt[1] if lg == "uk" else lt[0])[:70], "") for lt, _ in dv["lots"]]}
    est = PR.embelezar(body, capa2, emp, n_nota=nb, tr=(lambda s: s.split(" / ")[1] if lg == "en" and " / " in s else (s.split(" / ")[0] if " / " in s else s)))
    fn_e = OUT + {"uk": "Koshtorys_Budynok_A_RezultCLT_UK.pdf", "en": "Cost_Estimate_House_A_RezultCLT_EN.pdf"}[lg]
    open(fn_e, "wb").write(est)
    fn_x = fn_e.replace(".pdf", ".xlsx")
    DV.xlsx(dv, fn_x, lg, PROJ[lg])
    res[lg] = (dv, r)
    print(lg, "plans", len(d), "pages; estimate", round(dv["ht"]), "excl VAT", round(dv["ttc"]), "incl;", round(dv["per_m2_ttc"]), "UAH/m2; pub share", round(dv["parte_fonte"] * 100), "%")
    for lt, v in dv["lots"]:
        print("   ", lt[0], round(v))
pickle.dump({k: v[0] for k, v in res.items()}, open('/tmp/claude-0/homeA/dv.pkl', 'wb'))
