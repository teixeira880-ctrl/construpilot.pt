"""Planches du dossier bois massif (même logique qu'un dossier d'exécution de fabricant CLT / lamellé-collé) :
CL00 page de garde (spécifications matériaux, tolérances, sommaire, consignes), CL01 vue axonométrique, CL02 fondations
(gros œuvre), CL03 implantation des poteaux / murs, CL1x plans de charpente par niveau (poutres, pannes, sommiers, étriers),
CL2x calepinage CLT par niveau (repères de panneaux, compositions, sens de portée), CL30 coupe, CL31 détails d'assemblage
cotés, CL4x tableaux (CLT, lamellé-collé, assemblages, semelles). Échelles exactes en PDF + DXF."""
from __future__ import annotations

import math

from engines.bet_core.draw import Sheet
from engines.bet_frame import sheets as FS
from engines.bet_frame.sheets import AREA, S, _new, _plan_sheet, grid, grid_dims, table_sheets, u

from .lang import num, t

WOOD = (0.96, 0.90, 0.78)
WOOD2 = (0.93, 0.84, 0.68)
GLU = (0.86, 0.68, 0.45)
COL = (0.55, 0.36, 0.18)
CONC = (0.82, 0.83, 0.85)
STEEL = (0.45, 0.48, 0.55)
PANEL_FILLS = [(0.97, 0.92, 0.82), (0.95, 0.89, 0.76), (0.98, 0.94, 0.86), (0.94, 0.88, 0.78)]


def _note(sh, *lines):
    sh.notes += [S(x) for x in lines if x]


def _cols(sh, r, tags=True):
    for c in r["columns"]:
        s0 = c["segs"][0]
        b, h = s0["b"] / 1000, s0["h"] / 1000
        sh.rect("CHARPENTE", c["x"] - b / 2, c["y"] - h / 2, c["x"] + b / 2, c["y"] + h / 2, 0.4, COL)
        if tags:
            sh.text("TEXTE", (c["x"] + b / 2 + u(sh, 0.6), c["y"] + h / 2 + u(sh, 0.4)), S(c["name"]), 1.5, bold=True)


def _cols_level(sh, r, lid):
    for c in r["columns"]:
        s = next((x for x in c["segs"] if x["level"] == lid), None)
        if not s:
            continue
        b, h = s["b"] / 1000, s["h"] / 1000
        sh.rect("CHARPENTE", c["x"] - b / 2, c["y"] - h / 2, c["x"] + b / 2, c["y"] + h / 2, 0.4, COL)


# ================================================================ CL00 page de garde
def cover(m, r) -> Sheet:
    sh = _new("CL00", t("Page de garde — spécifications et sommaire", "Folha de rosto — especificações e índice", "Cover sheet — specifications and contents",
                        "Титульний аркуш — специфікації та зміст"), 1000, (0, 0),
              t("Structure bois massif CLT / lamellé-collé", "Estrutura em madeira maciça CLT / lamelado-colado", "Mass timber structure CLT / glulam",
                "Конструкції з масивної деревини CLT / клеєний брус"), kind="cover")
    sh.dxf = False
    W, H = AREA[2] - AREA[0], AREA[3] - AREA[1]
    y = H - 4
    sh.text("TITRE", (2, y), S(t("SPÉCIFICATIONS DU PROJET", "ESPECIFICAÇÕES DO PROJETO", "PROJECT SPECIFICATIONS", "СПЕЦИФІКАЦІЇ ПРОЄКТУ")), 4.2, bold=True)
    y -= 9
    clt_used = sorted({f["clt"]["name"] for f in r["floors"]})
    gl_used = sorted({b["grade"] for f in r["floors"] for b in f["beams"]} | {s["grade"] for c in r["columns"] for s in c["segs"]})
    rows = [
        (t("CLT — produit", "CLT — produto", "CLT — product", "CLT — виріб"), t("Bois lamellé-croisé EN 16351, lamelles C24, colle PUR / MUF",
                                                                           "Madeira lamelada-cruzada EN 16351, lamelas C24, cola PUR / MUF",
                                                                           "Cross-laminated timber EN 16351, C24 lamellas, PUR / MUF adhesive",
                                                                           "Перехресно-клеєна деревина EN 16351, ламелі C24, клей PUR / MUF")),
        (t("CLT — compositions", "CLT — composições", "CLT — layups", "CLT — структури"), ", ".join(clt_used) or "—"),
        (t("CLT — aspect", "CLT — acabamento", "CLT — finish", "CLT — поверхня"), t("Sous-face visible (VI) poncée grain 80, faces cachées NVI",
                                                                              "Face inferior à vista (VI) lixada grão 80, faces ocultas NVI",
                                                                              "Visible soffit (VI) sanded 80 grit, hidden faces NVI",
                                                                              "Видима нижня поверхня (VI), шліфування P80, приховані NVI")),
        (t("Lamellé-collé", "Lamelado-colado", "Glulam", "Клеєний брус"), (", ".join(gl_used) or "GL24h") + " — EN 14080:2013"),
        (t("Humidité à la livraison", "Humidade à entrega", "Moisture content at delivery", "Вологість при поставці"), "12 % ± 2 %"),
        (t("Classe de service", "Classe de serviço", "Service class", "Клас експлуатації"), t("1 (intérieur chauffé) — EN 1995-1-1", "1 (interior aquecido) — EN 1995-1-1",
                                                                                          "1 (heated interior) — EN 1995-1-1", "1 (опалюване приміщення) — EN 1995-1-1")),
        (t("Stabilité au feu", "Resistência ao fogo", "Fire resistance", "Вогнестійкість"), f"R{r['R']} — {r['R_src']} — EN 1995-1-2"),
        (t("Acier", "Aço", "Steel", "Сталь"), t("Platines, étriers : S355 galvanisé à chaud (EN ISO 1461)", "Chapas, ligadores: S355 galvanizado a quente (EN ISO 1461)",
                                                "Plates, hangers: S355 hot-dip galvanized (EN ISO 1461)", "Пластини, опори: S355 гаряче цинкування (EN ISO 1461)")),
        (t("Vis", "Parafusos", "Screws", "Шурупи"), t("Entièrement filetées sous ETA (Ø6, Ø8, Ø10)", "Rosca total com ETA (Ø6, Ø8, Ø10)",
                                                      "Fully threaded, with ETA (Ø6, Ø8, Ø10)", "З повною різьбою, з ETA (Ø6, Ø8, Ø10)")),
        (t("Béton / aciers", "Betão / aço", "Concrete / rebar", "Бетон / арматура"), f"{r['foundations']['mt']['concrete']} / {r['foundations']['mt']['steel']}"),
    ]
    for k, (a, b) in enumerate(rows):
        fill = (0.95, 0.96, 0.95) if k % 2 == 0 else None
        sh.rect("TEXTE", 0, y - 5.4, 170, y, 0.12, fill)
        sh.text("TEXTE", (1.5, y - 3.8), S(a), 2.0, bold=True)
        sh.text("TEXTE", (52, y - 3.8), S(b[:110]), 1.9)
        y -= 5.4
    y -= 6
    sh.text("TITRE", (2, y), S(t("TOLÉRANCES DE FABRICATION", "TOLERÂNCIAS DE FABRICO", "MANUFACTURING TOLERANCES", "ДОПУСКИ ВИГОТОВЛЕННЯ")), 3.4, bold=True)
    y -= 7
    tol = [("CLT", t("épaisseur ±2 mm ; largeur / longueur ±2 mm ; équerrage ±2 mm / 3 m ; perçages ±2 mm",
                     "espessura ±2 mm; largura / comprimento ±2 mm; esquadria ±2 mm / 3 m; furos ±2 mm",
                     "thickness ±2 mm; width / length ±2 mm; squareness ±2 mm / 3 m; holes ±2 mm",
                     "товщина ±2 мм; ширина / довжина ±2 мм; прямокутність ±2 мм / 3 м; отвори ±2 мм")),
           ("GL", t("largeur ±2 mm ; hauteur ±4 mm (h ≤ 400) / ±1 % ; longueur ±2 mm / 2 m ; rectitude L/500",
                    "largura ±2 mm; altura ±4 mm (h ≤ 400) / ±1 %; comprimento ±2 mm / 2 m; retilinearidade L/500",
                    "width ±2 mm; depth ±4 mm (h ≤ 400) / ±1 %; length ±2 mm / 2 m; straightness L/500",
                    "ширина ±2 мм; висота ±4 мм (h ≤ 400) / ±1 %; довжина ±2 мм / 2 м; прямолінійність L/500")),
           (t("Acier", "Aço", "Steel", "Сталь"), t("position des trous ±1,5 mm ; soudures EN 1090-2 EXC2", "posição dos furos ±1,5 mm; soldaduras EN 1090-2 EXC2",
                                                   "hole position ±1.5 mm; welds EN 1090-2 EXC2", "положення отворів ±1,5 мм; зварні шви EN 1090-2 EXC2"))]
    for a, b in tol:
        sh.text("TEXTE", (1.5, y), S(a), 2.0, bold=True)
        sh.text("TEXTE", (22, y), S(b), 1.9)
        y -= 5
    y -= 5
    sh.text("TITRE", (2, y), S(t("MANUTENTION, STOCKAGE ET MONTAGE", "MANUSEAMENTO, ARMAZENAMENTO E MONTAGEM", "HANDLING, STORAGE AND ASSEMBLY",
                                 "ТРАНСПОРТУВАННЯ, ЗБЕРІГАННЯ ТА МОНТАЖ")), 3.4, bold=True)
    y -= 7
    hand = [t("Levage par sangles textiles ou vis de levage sous ETA ; jamais de chaînes ou d'élingues acier au contact du bois.",
              "Elevação com cintas têxteis ou parafusos de elevação com ETA; nunca correntes ou cabos de aço em contacto com a madeira.",
              "Lift with textile slings or ETA lifting screws; never chains or steel slings in contact with the timber.",
              "Підйом текстильними стропами або монтажними шурупами з ETA; ніколи сталевими ланцюгами чи стропами по деревині."),
            t("Stockage à plat sur cales espacées ≤ 2 m, à 15 cm du sol, sous bâche respirante ; éviter tout contact avec l'eau stagnante.",
              "Armazenar na horizontal sobre calços espaçados ≤ 2 m, a 15 cm do solo, sob lona respirável; evitar água estagnada.",
              "Store flat on bearers ≤ 2 m apart, 15 cm above ground, under breathable covers; avoid standing water.",
              "Зберігати горизонтально на підкладках через ≤ 2 м, 15 см від землі, під паропроникним покриттям; уникати води."),
            t("Montage niveau par niveau : poteaux, poutres porteuses, pannes, panneaux CLT, vissage, éclissages ; contreventement provisoire jusqu'à la pose du diaphragme.",
              "Montagem piso a piso: pilares, vigas, madres, painéis CLT, aparafusamento, juntas; contraventamento provisório até ao diafragma.",
              "Floor-by-floor erection: columns, main beams, purlins, CLT panels, screwing, splines; temporary bracing until the diaphragm is complete.",
              "Монтаж поверх за поверхом: колони, головні балки, прогони, панелі CLT, кріплення, накладки; тимчасові в'язі до завершення диска."),
            t("Aucun perçage, entaille ou découpe sur chantier sans accord écrit du bureau d'études.",
              "Nenhuma furação, entalhe ou corte em obra sem acordo escrito do projetista.",
              "No site drilling, notching or cutting without the engineer's written approval.",
              "Жодного свердління, вирізів чи різання на майданчику без письмової згоди проєктувальника."),
            t("Humidité du bois ≤ 18 % avant fermeture des complexes (contrôle à l'humidimètre, PV).",
              "Humidade da madeira ≤ 18 % antes de fechar os revestimentos (medição com humidímetro).",
              "Timber moisture ≤ 18 % before enclosing build-ups (moisture-meter record).",
              "Вологість деревини ≤ 18 % перед закриттям оздоблення (контроль вологоміром).")]
    for hline in hand:
        for k_, ln in enumerate(_wrap(hline, 120)):
            sh.text("TEXTE", (3.5 if k_ else 1.5, y), S(("• " if k_ == 0 else "  ") + ln), 1.85)
            y -= 3.6
        y -= 0.8
    # sommaire (rempli par la pipeline)
    sh._toc_at = (186, H - 4)
    return sh


def toc(sh: Sheet, sheets: list[Sheet]):
    x, y = sh._toc_at
    sh.text("TITRE", (x, y), S(t("SOMMAIRE", "ÍNDICE", "TABLE OF CONTENTS", "ЗМІСТ")), 4.2, bold=True)
    y -= 8
    for s in sheets:
        sh.text("TEXTE", (x, y), S(s.code), 1.9, bold=True)
        sh.text("TEXTE", (x + 13, y), S(str(s.title)[:62]), 1.8)
        y -= 3.7
        if y < 8:
            break


def _wrap(s: str, n: int) -> list[str]:
    out, cur = [], ""
    for w in s.split():
        if len(cur) + len(w) + 1 > n:
            out.append(cur)
            cur = w
        else:
            cur = (cur + " " + w).strip()
    if cur:
        out.append(cur)
    return out


# ================================================================ CL01 vue axonométrique
def iso(m, r) -> Sheet:
    sh = _new("CL01", t("Vue axonométrique de la structure", "Vista axonométrica da estrutura", "Isometric view of the structure", "Аксонометрія конструкції"),
              1000, (0, 0), "", kind="iso")
    sh.dxf = False
    c30, s30 = math.cos(math.radians(30)), math.sin(math.radians(30))

    def P(x, y, z):
        return ((x - y) * c30, (x + y) * s30 + z)
    pts = [P(x, y, z) for x in (m.gx[0], m.gx[-1]) for y in (m.gy[0], m.gy[-1]) for z in (m.levels[0].z, m.slabs[-1].z)]
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    W, H = AREA[2] - AREA[0] - 6, AREA[3] - AREA[1] - 14
    k = min(W / (max(xs) - min(xs)), H / (max(ys) - min(ys)))
    ox, oy = -min(xs) * k + 3, -min(ys) * k + 6

    def Q(x, y, z):
        p = P(x, y, z)
        return (p[0] * k + ox, p[1] * k + oy)
    o = r["scheme"]["o"]
    for f in r["floors"]:
        z = f["z"]
        cells = set(map(tuple, f["cells"]))
        for (i, j) in cells:
            poly = [Q(m.gx[i], m.gy[j], z), Q(m.gx[i + 1], m.gy[j], z), Q(m.gx[i + 1], m.gy[j + 1], z), Q(m.gx[i], m.gy[j + 1], z)]
            sh.poly("CHARPENTE", poly, 0.12, True, WOOD)
        for p in f["panels"]:
            if p["dir"] == "x":
                sh.line("CHARPENTE", Q(p["x0"], p["y0"], z), Q(p["x1"], p["y0"], z), 0.08)
            else:
                sh.line("CHARPENTE", Q(p["x0"], p["y0"], z), Q(p["x0"], p["y1"], z), 0.08)
        for bm in f["beams"]:
            a, b = _beam_axis(m, bm, o)
            sh.line("CHARPENTE", Q(a[0], a[1], z - 0.02), Q(b[0], b[1], z - 0.02), 0.45 if bm["role"] != "purlin" else 0.25)
        for w in r["walls"]:
            seg = next((s for s in w["segs"] if abs(next(l.z + l.height for l in m.levels if l.id == s["level"]) - z) < 0.05), None)
            if seg:
                a, b = _wall_axis(w)
                z0 = z - next(l.height for l in m.levels if l.id == seg["level"])
                sh.poly("CHARPENTE", [Q(a[0], a[1], z0), Q(b[0], b[1], z0), Q(b[0], b[1], z), Q(a[0], a[1], z)], 0.15, True, WOOD2)
    for c in r["columns"]:
        for s in c["segs"]:
            lv = next(l for l in m.levels if l.id == s["level"])
            sh.line("CHARPENTE", Q(c["x"], c["y"], lv.z), Q(c["x"], c["y"], lv.z + lv.height), 0.6)
    b0 = m.levels[0].z
    sh.poly("BA", [Q(m.gx[0], m.gy[0], b0), Q(m.gx[-1], m.gy[0], b0), Q(m.gx[-1], m.gy[-1], b0), Q(m.gx[0], m.gy[-1], b0)], 0.3, True, CONC)
    _note(sh, t("Vue de principe : poteaux, poutres, pannes, panneaux CLT et dallage BA du rez-de-chaussée.",
                "Vista de princípio: pilares, vigas, madres, painéis CLT e laje térrea.",
                "Principle view: columns, beams, purlins, CLT panels and RC ground slab.",
                "Принципова схема: колони, балки, прогони, панелі CLT та з/б плита по ґрунту."))
    return sh


def _beam_axis(m, bm, o):
    gs = m.gx if o == "x" else m.gy
    gp = m.gy if o == "x" else m.gx
    if bm["o"] == "p":
        pos = bm["pos"] if bm.get("pos") is not None else gs[bm["line"][1]]
        return ((pos, bm["a0"]), (pos, bm["a1"])) if o == "x" else ((bm["a0"], pos), (bm["a1"], pos))
    pos = gp[bm["line"][1]]
    return ((bm["a0"], pos), (bm["a1"], pos)) if o == "x" else ((pos, bm["a0"]), (pos, bm["a1"]))


def _wall_axis(w):
    if w["axis"] == "x":                      # mur sur une file x = pos (porteur, perpendiculaire à x)
        return (w["pos"], w["a"]), (w["pos"], w["b"])
    return (w["a"], w["pos"]), (w["b"], w["pos"])


# ================================================================ CL02 fondations
def foundations(m, r) -> Sheet:
    f = r["foundations"]
    sh = _plan_sheet(m, "CL02", t("Plan de fondations — gros œuvre", "Planta de fundações", "Foundation plan", "План фундаментів"),
                     t(f"Semelles BA {f['mt']['concrete']} / {f['mt']['steel']}, σ adm = {num(f.get('sigma_kpa', 200) / 1000)} MPa",
                       f"Sapatas BA {f['mt']['concrete']} / {f['mt']['steel']}, σ adm = {num(f.get('sigma_kpa', 200) / 1000)} MPa",
                       f"RC footings {f['mt']['concrete']} / {f['mt']['steel']}, allowable σ = {num(f.get('sigma_kpa', 200) / 1000)} MPa",
                       f"З/б фундаменти {f['mt']['concrete']} / {f['mt']['steel']}, σ доп = {num(f.get('sigma_kpa', 200) / 1000)} МПа"), kind="fond")
    grid(sh, m)
    FS.outline(sh, m, 0.3)
    for p in f.get("pads", []):
        B = p["B"]
        sh.rect("FOND", p["x"] - B / 2, p["y"] - B / 2, p["x"] + B / 2, p["y"] + B / 2, 0.35, (0.85, 0.93, 0.87))
        sh.text("TEXTE", (p["x"], p["y"] - B / 2 - u(sh, 2.4)), S(f"{p['name']} {num(B)}×{num(B)}×{num(p['h'])}"), 1.35, "c")
    for s in f.get("wall_strips", []):
        if s["axis"] == "x":
            sh.rect("FOND", s["pos"] - s["B"] / 2, s["a"] - s["B"] / 2, s["pos"] + s["B"] / 2, s["b"] + s["B"] / 2, 0.35, (0.85, 0.93, 0.87))
            sh.text("TEXTE", (s["pos"] + s["B"] / 2 + u(sh, 1), (s["a"] + s["b"]) / 2), S(f"{s['id']} B={num(s['B'])} h={num(s['h'])}"), 1.4, rot=90)
        else:
            sh.rect("FOND", s["a"] - s["B"] / 2, s["pos"] - s["B"] / 2, s["b"] + s["B"] / 2, s["pos"] + s["B"] / 2, 0.35, (0.85, 0.93, 0.87))
            sh.text("TEXTE", ((s["a"] + s["b"]) / 2, s["pos"] + s["B"] / 2 + u(sh, 1)), S(f"{s['id']} B={num(s['B'])} h={num(s['h'])}"), 1.4, "c")
    _cols(sh, r, tags=False)
    gs_ = f["ground_slab"]
    _note(sh,
          t(f"Assise à {num(f.get('depth', 1.0))} m sous le terrain naturel, sur sol en place reconnu ; béton de propreté 5 cm.",
            f"Cota de fundação a {num(f.get('depth', 1.0))} m abaixo do terreno natural; betão de limpeza 5 cm.",
            f"Founding depth {num(f.get('depth', 1.0))} m below natural ground; 5 cm blinding.",
            f"Глибина закладання {num(f.get('depth', 1.0))} м від природного рельєфу; підготовка 5 см."),
          t(f"Dallage BA e = {num(gs_['h'])} m, treillis {gs_['mesh']}, sur hérisson 20 cm + polyane ; joints de retrait ≤ 25 m².",
            f"Laje térrea BA e = {num(gs_['h'])} m, malha {gs_['mesh']}, sobre enrocamento 20 cm + filme; juntas ≤ 25 m².",
            f"RC ground slab t = {num(gs_['h'])} m, mesh {gs_['mesh']}, on 20 cm hardcore + membrane; joints ≤ 25 m².",
            f"З/б плита t = {num(gs_['h'])} м, сітка {gs_['mesh']}, на щебені 20 см + плівка; шви ≤ 25 м²."),
          t("Soubassement BA 20 × 30 cm en périphérie : arase étanche, le bois reste à 20 cm minimum au-dessus du sol fini.",
            "Murete BA 20 × 30 cm na periferia: corte de capilaridade, madeira a ≥ 20 cm acima do terreno.",
            "20 × 30 cm RC upstand around the perimeter: damp-proof course, timber at least 20 cm above finished ground.",
            "З/б цоколь 20 × 30 см по периметру: гідроізоляція, деревина не нижче 20 см над рівнем землі."),
          t("Platines et tiges d'ancrage posées sur gabarit avant bétonnage (tolérance ±3 mm en plan, ±5 mm en niveau).",
            "Chapas e chumbadouros colocados com gabarito antes da betonagem (tolerância ±3 mm em planta, ±5 mm em cota).",
            "Base plates and anchor rods set with a template before pouring (±3 mm in plan, ±5 mm in level).",
            "Пластини та анкери встановлюються за шаблоном до бетонування (±3 мм у плані, ±5 мм по висоті)."))
    grid_dims(sh, m)
    return sh


# ================================================================ CL03 implantation des poteaux
def columns_plan(m, r) -> Sheet:
    sh = _plan_sheet(m, "CL03", t("Implantation des poteaux — rez-de-chaussée", "Implantação dos pilares — R/C", "Column layout — level 1", "Розміщення колон — 1-й поверх"),
                     t("Pieds de poteaux : voir détails CL31", "Bases dos pilares: ver pormenores CL31", "Column bases: see details CL31", "Опори колон: див. вузли CL31"),
                     kind="col")
    grid(sh, m)
    FS.outline(sh, m, 0.3)
    bases = {b["col"]: b for b in r["connections"]["bases"]}
    for c in r["columns"]:
        s0 = c["segs"][0]
        b, h = s0["b"] / 1000, s0["h"] / 1000
        bp = bases.get(c["name"])
        if bp:
            Bp = bp["B"] / 1000
            sh.rect("ACIER", c["x"] - Bp / 2, c["y"] - Bp / 2, c["x"] + Bp / 2, c["y"] + Bp / 2, 0.2, None, dash="dashed")
        sh.rect("CHARPENTE", c["x"] - b / 2, c["y"] - h / 2, c["x"] + b / 2, c["y"] + h / 2, 0.4, COL)
        sh.text("TEXTE", (c["x"] + b / 2 + u(sh, 0.8), c["y"] + h / 2 + u(sh, 0.6)), S(f"{c['name']}"), 1.6, bold=True)
        sh.text("TEXTE", (c["x"] + b / 2 + u(sh, 0.8), c["y"] - u(sh, 1.0)), S(f"{s0['b']}×{s0['h']} {s0['grade']}"), 1.3)
        if bp:
            sh.text("TEXTE", (c["x"] + b / 2 + u(sh, 0.8), c["y"] - u(sh, 3.2)), S(f"N={num(bp['NEd'], 0)} kN · PL{bp['t']}"), 1.2)
    for w in r["walls"]:
        _wall_plan(sh, w, w["segs"][0])
    _note(sh, t("Poteaux centrés sur les axes sauf indication contraire ; aboutage à chaque plancher sur platine S355 (CL31).",
                "Pilares centrados nos eixos salvo indicação; emenda em cada piso sobre chapa S355 (CL31).",
                "Columns centred on gridlines unless noted; spliced at each floor on an S355 plate (CL31).",
                "Колони по осях, якщо не вказано інше; стик на кожному перекритті на пластині S355 (CL31)."),
          t("Section et classe indiquées pour l'étage ; tableau complet CL41.", "Secção e classe do piso; quadro completo CL41.",
            "Section and grade for this storey; full schedule CL41.", "Переріз і клас для поверху; повна таблиця CL41."))
    grid_dims(sh, m)
    return sh


def _wall_plan(sh, w, seg):
    tt = seg["t"] / 1000
    a, b = _wall_axis(w)
    if w["axis"] == "x":
        sh.rect("CHARPENTE", a[0] - tt / 2, a[1], a[0] + tt / 2, b[1], 0.35, WOOD2, hatch="bois")
        sh.text("TEXTE", (a[0] - tt / 2 - u(sh, 1.2), (a[1] + b[1]) / 2), S(f"{w['id']} CLT {seg['layup']}"), 1.5, "c", rot=90, bold=True)
    else:
        sh.rect("CHARPENTE", a[0], a[1] - tt / 2, b[0], a[1] + tt / 2, 0.35, WOOD2, hatch="bois")
        sh.text("TEXTE", ((a[0] + b[0]) / 2, a[1] + tt / 2 + u(sh, 1.0)), S(f"{w['id']} CLT {seg['layup']}"), 1.5, "c", bold=True)


# ================================================================ CL1x plans de charpente
def framing(m, r, f, code) -> Sheet:
    o = r["scheme"]["o"]
    walls = r["system"] == "walls"
    sh = _plan_sheet(m, code, t(f"Plan de charpente — {f['name']}", f"Planta de estrutura — {f['name']}", f"Framing plan — {f['name']}",
                                f"План каркаса — {f['name']}"),
                     t(f"Dessous CLT à {num(f['z'] - f['clt']['h'] / 1000)} m", f"Face inferior CLT a {num(f['z'] - f['clt']['h'] / 1000)} m",
                       f"U/S of CLT at {num(f['z'] - f['clt']['h'] / 1000)} m", f"Низ CLT на відм. {num(f['z'] - f['clt']['h'] / 1000)} м"), kind="framing", level=f["id"])
    grid(sh, m)
    FS.outline(sh, m, 0.25)
    if walls:
        below = f["level_below"]
        for w in r["walls"]:
            seg = next((s for s in w["segs"] if s["level"] == below), None)
            if seg:
                _wall_plan(sh, w, seg)
    else:
        _cols_level(sh, r, f["level_below"])
        for bm in f["beams"]:
            a, b = _beam_axis(m, bm, o)
            w = bm["b"] / 1000
            vert = abs(a[0] - b[0]) < 1e-6
            x0, x1 = (a[0] - w / 2, a[0] + w / 2) if vert else (a[0], b[0])
            y0, y1 = (a[1], b[1]) if vert else (a[1] - w / 2, a[1] + w / 2)
            sh.rect("CHARPENTE", x0, y0, x1, y1, 0.3, GLU if bm["role"] != "purlin" else WOOD2)
            lab = f"{bm['id']} {bm['b']}×{bm['h']}"
            mx, my = (a[0] + b[0]) / 2, (a[1] + b[1]) / 2
            if vert:
                sh.text("TEXTE", (mx - w / 2 - u(sh, 0.8), my), S(lab), 1.25, "c", rot=90)
            else:
                sh.text("TEXTE", (mx, my + w / 2 + u(sh, 0.6)), S(lab), 1.25, "c")
            # repère d'étrier aux extrémités
            hs = {h["end"]: h for h in r["connections"]["hangers"] if h["beam"] == bm["id"]}
            for end, p in (("R0", a), ("R1", b)):
                h = hs.get(end)
                if h:
                    dx = (0.35 if not vert else 0) * (1 if end == "R0" else -1)
                    dy = (0.35 if vert else 0) * (1 if end == "R0" else -1)
                    sh.text("ACIER", (p[0] + dx, p[1] + dy - u(sh, 0.5)), S(h["type"]), 1.1, "c", bold=True)
    _note(sh, t("Poutres GL isostatiques, assemblées par étriers cachés (repères H, tableau CL42, détail CL31).",
                "Vigas GL simplesmente apoiadas, ligadas por ligadores ocultos (referências H, quadro CL42, pormenor CL31).",
                "Glulam beams simply supported, connected by concealed hangers (marks H, schedule CL42, detail CL31).",
                "Балки GL однопрольотні, з'єднані прихованими опорами (марки H, таблиця CL42, вузол CL31)."),
          t("Dessus des poutres = dessous du CLT ; pannes au même niveau que les poutres porteuses.",
            "Face superior das vigas = face inferior do CLT; madres ao mesmo nível das vigas.",
            "Top of beams = underside of CLT; purlins flush with main beams.",
            "Верх балок = низ CLT; прогони в одному рівні з головними балками.") if not walls else
          t("Murs CLT porteurs : lisse basse sur arase étanche au RDC, équerres et ancrages d'about selon CL42.",
            "Paredes CLT resistentes: soleira sobre corte de capilaridade no R/C, esquadros e ancoragens conforme CL42.",
            "Load-bearing CLT walls: sole plate on damp-proof course at ground level, brackets and hold-downs per CL42.",
            "Несучі стіни CLT: лежень на гідроізоляції, кутики та анкери згідно CL42."))
    grid_dims(sh, m)
    return sh


# ================================================================ CL2x calepinage CLT
def clt_plan(m, r, f, code) -> Sheet:
    c = f["clt"]
    sh = _plan_sheet(m, code, t(f"Calepinage CLT — {f['name']}", f"Esquema de painéis CLT — {f['name']}", f"CLT panel layout — {f['name']}",
                                f"Розкладка панелей CLT — {f['name']}"),
                     t(f"CLT {c['name']} — dessus à {num(f['z'])} m", f"CLT {c['name']} — face superior a {num(f['z'])} m",
                       f"CLT {c['name']} — top at {num(f['z'])} m", f"CLT {c['name']} — верх на відм. {num(f['z'])} м"), kind="clt", level=f["id"])
    grid(sh, m)
    tps = {tp["type"]: k for k, tp in enumerate(f["ptypes"])}
    for p in f["panels"]:
        fill = PANEL_FILLS[tps.get(p.get("type"), 0) % len(PANEL_FILLS)]
        sh.rect("CHARPENTE", p["x0"], p["y0"], p["x1"], p["y1"], 0.3, fill)
        cx, cy = (p["x0"] + p["x1"]) / 2, (p["y0"] + p["y1"]) / 2
        horiz = p["dir"] == "x"
        rot = 0 if horiz else 90
        sh.text("TEXTE", (cx, cy + (u(sh, 0.9) if horiz else 0)) if horiz else (cx - u(sh, 0.9), cy), S(p["id"]), 1.45, "c", rot=rot, bold=True)
        sh.text("TEXTE", (cx, cy - u(sh, 1.6)) if horiz else (cx + u(sh, 1.6), cy), S(f"{p['layup']} · {p['type']}"), 1.15, "c", rot=rot)
        # flèche de sens de portée
        L = (p["x1"] - p["x0"]) if horiz else (p["y1"] - p["y0"])
        a = min(L * 0.18, u(sh, 8))
        if horiz:
            y = cy - u(sh, 3.6)
            sh.line("TEXTE", (cx - a, y), (cx + a, y), 0.2)
            for s_ in (-1, 1):
                sh.line("TEXTE", (cx + s_ * a, y), (cx + s_ * a - s_ * u(sh, 0.8), y + u(sh, 0.5)), 0.2)
                sh.line("TEXTE", (cx + s_ * a, y), (cx + s_ * a - s_ * u(sh, 0.8), y - u(sh, 0.5)), 0.2)
        else:
            x = cx + u(sh, 3.6)
            sh.line("TEXTE", (x, cy - a), (x, cy + a), 0.2)
            for s_ in (-1, 1):
                sh.line("TEXTE", (x, cy + s_ * a), (x + u(sh, 0.5), cy + s_ * a - s_ * u(sh, 0.8)), 0.2)
                sh.line("TEXTE", (x, cy + s_ * a), (x - u(sh, 0.5), cy + s_ * a - s_ * u(sh, 0.8)), 0.2)
    _cols_level(sh, r, f["level_below"])
    for cc in m.cores:
        sh.rect("BA", cc["x0"], cc["y0"], cc["x1"], cc["y1"], 0.35, None, hatch="ba")
    d = r["lateral"]["diaphragm"]
    _note(sh, t(f"Composition {c['name']} : plis {'/'.join(str(x) for x in c['layers'])} mm, plis extérieurs dans le sens de la flèche (sens de portée).",
                f"Composição {c['name']}: camadas {'/'.join(str(x) for x in c['layers'])} mm, camadas exteriores no sentido da seta (vão).",
                f"Layup {c['name']}: plies {'/'.join(str(x) for x in c['layers'])} mm, outer plies along the arrow (span direction).",
                f"Структура {c['name']}: шари {'/'.join(str(x) for x in c['layers'])} мм, зовнішні шари вздовж стрілки (напрям прольоту)."),
          t(f"Joints entre panneaux : éclisse {d['spline']} en feuillure, vis {d['screw']} tous les {d['spacing']} mm de chaque côté (diaphragme {num(d['v_kNm'])} kN/m).",
            f"Juntas entre painéis: tala {d['spline']} em rebaixo, parafusos {d['screw']} cada {d['spacing']} mm de cada lado (diafragma {num(d['v_kNm'])} kN/m).",
            f"Panel joints: {d['spline']} surface spline, {d['screw']} screws at {d['spacing']} mm each side (diaphragm {num(d['v_kNm'])} kN/m).",
            f"Стики панелей: накладка {d['spline']} у четверть, шурупи {d['screw']} крок {d['spacing']} мм з кожного боку (диск {num(d['v_kNm'])} кН/м)."),
          t(f"Fixation CLT / poutres : vis Ø8 entièrement filetées, ancrage ≥ 100 mm dans la poutre, tous les 300 mm.",
            f"Fixação CLT / vigas: parafusos Ø8 de rosca total, ancoragem ≥ 100 mm na viga, cada 300 mm.",
            f"CLT to beam fixing: Ø8 fully threaded screws, ≥ 100 mm into the beam, at 300 mm.",
            f"Кріплення CLT до балок: шурупи Ø8 з повною різьбою, ≥ 100 мм у балку, крок 300 мм."),
          t(f"{len(f['panels'])} panneaux, {len(f['ptypes'])} types (tableau CL40) ; réservations > Ø150 à valider par le BET.",
            f"{len(f['panels'])} painéis, {len(f['ptypes'])} tipos (quadro CL40); aberturas > Ø150 a validar pelo projetista.",
            f"{len(f['panels'])} panels, {len(f['ptypes'])} types (schedule CL40); openings > Ø150 to be approved by the engineer.",
            f"{len(f['panels'])} панелей, {len(f['ptypes'])} типів (таблиця CL40); отвори > Ø150 погодити з проєктувальником."))
    grid_dims(sh, m)
    return sh


# ================================================================ CL30 coupe
def section(m, r) -> Sheet:
    o = r["scheme"]["o"]
    along_x = True
    xs = m.gx
    yc = m.gy[min(1, len(m.gy) - 1)]
    zb = m.levels[0].z - 1.2
    zt = r["floors"][-1]["z"] + 1.0 if r["floors"] else m.levels[-1].z + 3
    w = AREA[2] - AREA[0]
    h = AREA[3] - AREA[1]
    sc = next(s for s in (50, 75, 100, 125, 150, 200, 250, 300, 400, 500) if (m.L + 8) * 1000 / s <= w and (zt - zb + 6) * 1000 / s <= h)
    ox = xs[0] - ((w * sc / 1000) - m.L) / 2
    oy = zb - ((h * sc / 1000) - (zt - zb)) / 2
    lab = m.yl[min(1, len(m.yl) - 1)]
    sh = _new("CL30", t(f"Coupe sur file {lab}", f"Corte pelo alinhamento {lab}", f"Section on gridline {lab}", f"Розріз по осі {lab}"), sc, (ox, oy),
              "", kind="coupe")
    z0 = m.levels[0].z
    sh.rect("BA", xs[0] - 0.5, z0 - 0.16, xs[-1] + 0.5, z0, 0.3, CONC, hatch="ba")
    sh.line("TERRAIN", (xs[0] - 3, z0 - 0.15), (xs[-1] + 3, z0 - 0.15), 0.4)
    fnd = {p["node"]: p for p in r["foundations"].get("pads", [])}
    j = min(1, len(m.gy) - 1)
    for i, x in enumerate(xs):
        p = fnd.get((i, j))
        if p:
            dz = r["foundations"].get("depth", 1.0)
            sh.rect("FOND", x - p["B"] / 2, z0 - dz - p["h"], x + p["B"] / 2, z0 - dz, 0.3, (0.85, 0.93, 0.87), hatch="ba")
            sh.rect("BA", x - 0.2, z0 - dz, x + 0.2, z0 - 0.16, 0.25, CONC)
    for c in r["columns"]:
        if abs(c["y"] - yc) > 1e-6:
            continue
        for s in c["segs"]:
            lv = next(l for l in m.levels if l.id == s["level"])
            b = s["b"] / 1000
            sh.rect("CHARPENTE", c["x"] - b / 2, lv.z, c["x"] + b / 2, lv.z + lv.height - 0.05, 0.35, COL)
    for f in r["floors"]:
        hc = f["clt"]["h"] / 1000
        cells = set(map(tuple, f["cells"]))
        for i in range(len(xs) - 1):
            if (i, j) in cells or (i, j - 1) in cells:
                sh.rect("CHARPENTE", xs[i], f["z"] - hc, xs[i + 1], f["z"], 0.3, WOOD, hatch="bois")
        for bm in f["beams"]:
            a, b = _beam_axis(m, bm, o)
            if abs(a[1] - b[1]) < 1e-6 and abs(a[1] - yc) < 1e-6:          # poutre dans le plan de coupe (vue en élévation)
                sh.rect("CHARPENTE", a[0], f["z"] - hc - bm["h"] / 1000, b[0], f["z"] - hc, 0.3, GLU)
            elif abs(a[0] - b[0]) < 1e-6 and min(a[1], b[1]) - 1e-6 <= yc <= max(a[1], b[1]) + 1e-6:   # poutre coupée
                bw = bm["b"] / 1000
                sh.rect("CHARPENTE", a[0] - bw / 2, f["z"] - hc - bm["h"] / 1000, a[0] + bw / 2, f["z"] - hc, 0.3, GLU, hatch="bois")
        for w in r["walls"]:
            seg = next((s for s in w["segs"] if s["level"] == f["level_below"]), None)
            if seg and w["axis"] == "x":
                lv = next(l for l in m.levels if l.id == f["level_below"])
                tw = seg["t"] / 1000
                sh.rect("CHARPENTE", w["pos"] - tw / 2, lv.z, w["pos"] + tw / 2, f["z"] - hc, 0.3, WOOD2, hatch="bois")
        sh.level_mark((xs[-1] + 1.2, f["z"]), f["z"], f["name"])
    sh.level_mark((xs[-1] + 1.2, z0), z0, m.levels[0].name)
    for x, labx in zip(xs, m.xl):
        sh.line("AXE", (x, zb + 0.2), (x, zt), 0.15, "axis")
        sh.circle("AXE", (x, zt + u(sh, 3.2)), u(sh, 3.2), 0.3, (1, 1, 1))
        sh.text("AXE", (x, zt + u(sh, 2.2)), S(labx), 2.6, "c", bold=True)
    for a_, b_ in zip(xs, xs[1:]):
        sh.dim((a_, zb + 0.3), (b_, zb + 0.3), 0, None, 1.6)
    _note(sh, t("Complexe de plancher type : revêtement, chape flottante 50 mm, résilient, lest granulaire, CLT, plafond (selon exigences acoustiques).",
                "Pavimento tipo: revestimento, betonilha flutuante 50 mm, resiliente, enchimento granular, CLT, teto (requisitos acústicos).",
                "Typical floor build-up: finish, 50 mm floating screed, resilient layer, granular fill, CLT, ceiling (per acoustic requirements).",
                "Типовий склад перекриття: покриття, плаваюча стяжка 50 мм, пружний шар, засипка, CLT, стеля (за акустичними вимогами)."))
    return sh


# ================================================================ CL31 détails
def details(m, r) -> Sheet:
    sh = _new("CL31", t("Détails d'assemblage", "Pormenores de ligação", "Connection details", "Вузли з'єднань"), 10, (0, 0), "", kind="detail")
    sh.dxf = False
    # coordonnées en m à l'échelle 1:10 (1 m = 100 mm papier) : zone 289 × 260 mm → 2,89 × 2,6 m
    conns = r["connections"]
    # --- détail 1 : pied de poteau
    if conns["bases"]:
        bp = max(conns["bases"], key=lambda b: b["NEd"])
        b = bp["b"] / 1000
        B = bp["B"] / 1000
        x0, y0 = 0.25, 1.55
        sh.rect("BA", x0 - 0.15, y0 - 0.45, x0 + B + 0.15, y0, 0.3, CONC, hatch="ba")
        sh.rect("ACIER", x0, y0, x0 + B, y0 + bp["t"] / 1000, 0.3, STEEL)
        cx = x0 + B / 2
        sh.rect("CHARPENTE", cx - b / 2, y0 + bp["t"] / 1000 + 0.02, cx + b / 2, y0 + 0.75, 0.35, COL)
        for dx in (-B / 2 + 0.04, B / 2 - 0.04):
            sh.line("ACIER", (cx + dx, y0 - 0.35), (cx + dx, y0 + 0.05), 0.5)
        sh.text("TEXTE", (x0, y0 + 0.85), S(t("DÉTAIL 1 — PIED DE POTEAU", "PORMENOR 1 — BASE DE PILAR", "DETAIL 1 — COLUMN BASE", "ВУЗОЛ 1 — ОПОРА КОЛОНИ")), 2.4, bold=True)
        sh.text("TEXTE", (x0 + B + 0.2, y0 + 0.55), S(f"GL {bp['b']}×{bp['h']}"), 1.8)
        sh.text("TEXTE", (x0 + B + 0.2, y0 + 0.40), S(t(f"Platine S355 {bp['B']}×{bp['B']}×{bp['t']}", f"Chapa S355 {bp['B']}×{bp['B']}×{bp['t']}",
                                                         f"S355 plate {bp['B']}×{bp['B']}×{bp['t']}", f"Пластина S355 {bp['B']}×{bp['B']}×{bp['t']}")), 1.8)
        sh.text("TEXTE", (x0 + B + 0.2, y0 + 0.25), S(f"{bp['n_rod']} × {bp['rod']} 8.8"), 1.8)
        sh.text("TEXTE", (x0 + B + 0.2, y0 + 0.10), S(t(f"Fixation bois : {bp['dowels']}", f"Fixação madeira: {bp['dowels']}", f"Timber fixing: {bp['dowels']}",
                                                         f"Кріплення: {bp['dowels']}")), 1.8)
        sh.text("TEXTE", (x0 + B + 0.2, y0 - 0.05), S(t("Calage mortier sans retrait 30 mm", "Argamassa não retrátil 30 mm", "30 mm non-shrink grout",
                                                         "Безусадкова підливка 30 мм")), 1.8)
        sh.text("TEXTE", (x0 + B + 0.2, y0 - 0.20), S(f"N_Ed = {num(bp['NEd'], 0)} kN · f_jd = {num(bp['f_jd'])} MPa · u = {num(bp['u'])}"), 1.7)
        sh.dim((x0, y0 - 0.5), (x0 + B, y0 - 0.5), 0, f"{bp['B']}", 1.6)
    # --- détail 2 : étrier caché poutre / poutre
    hts = conns["hanger_types"]
    if hts:
        h = max(hts, key=lambda x: x["V_max"])
        hb = 0.6
        x0, y0 = 1.55, 1.55
        sh.rect("CHARPENTE", x0, y0, x0 + 0.25, y0 + hb, 0.35, GLU)
        sh.rect("CHARPENTE", x0 + 0.27, y0 + 0.08, x0 + 1.0, y0 + hb, 0.35, GLU)
        sh.rect("ACIER", x0 + 0.22, y0 + 0.12, x0 + 0.36, y0 + hb - 0.05, 0.25, STEEL)
        n2 = max(2, h["screws"] // 2)
        for k in range(n2):
            yy = y0 + 0.16 + k * (hb - 0.25) / max(1, n2 - 1)
            sh.line("ACIER", (x0 + 0.30, yy), (x0 + 0.45, yy + 0.15), 0.35)
            sh.line("ACIER", (x0 + 0.24, yy), (x0 + 0.12, yy + 0.12), 0.35)
        sh.text("TEXTE", (x0, y0 + hb + 0.10), S(t("DÉTAIL 2 — ÉTRIER CACHÉ", "PORMENOR 2 — LIGADOR OCULTO", "DETAIL 2 — CONCEALED HANGER", "ВУЗОЛ 2 — ПРИХОВАНА ОПОРА")), 2.4, bold=True)
        sh.text("TEXTE", (x0 + 0.5, y0 - 0.08), S(t(f"Type {h['type']} : {h['screws']} vis Ø8×{h['L']} à 45°, plaque {h['plate']} S355",
                                                     f"Tipo {h['type']}: {h['screws']} parafusos Ø8×{h['L']} a 45°, chapa {h['plate']} S355",
                                                     f"Type {h['type']}: {h['screws']} Ø8×{h['L']} screws at 45°, plate {h['plate']} S355",
                                                     f"Тип {h['type']}: {h['screws']} шурупів Ø8×{h['L']} під 45°, пластина {h['plate']} S355")), 1.8)
        sh.text("TEXTE", (x0 + 0.5, y0 - 0.22), S(f"V_Ed ≤ {num(h['V_max'], 1)} kN ≤ V_Rd = {num(h['V_Rd'], 1)} kN"), 1.8)
    # --- détail 3 : joint CLT éclissé
    d = r["lateral"]["diaphragm"]
    hc = (r["floors"][0]["clt"]["h"] / 1000) if r["floors"] else 0.16
    x0, y0 = 0.25, 0.35
    sh.rect("CHARPENTE", x0, y0, x0 + 0.6, y0 + hc, 0.35, WOOD, hatch="bois")
    sh.rect("CHARPENTE", x0 + 0.6, y0, x0 + 1.2, y0 + hc, 0.35, WOOD, hatch="bois")
    sh.rect("CHARPENTE", x0 + 0.55, y0 + hc - 0.027, x0 + 0.65, y0 + hc, 0.3, (0.8, 0.62, 0.36))
    for xx in (x0 + 0.575, x0 + 0.625):
        sh.line("ACIER", (xx, y0 + hc), (xx, y0 + hc - 0.06), 0.4)
    sh.text("TEXTE", (x0, y0 + hc + 0.12), S(t("DÉTAIL 3 — JOINT CLT ÉCLISSÉ", "PORMENOR 3 — JUNTA CLT COM TALA", "DETAIL 3 — CLT SPLINE JOINT", "ВУЗОЛ 3 — СТИК CLT З НАКЛАДКОЮ")), 2.4, bold=True)
    sh.text("TEXTE", (x0, y0 - 0.12), S(t(f"Éclisse {d['spline']} + vis {d['screw']} @ {d['spacing']} mm", f"Tala {d['spline']} + parafusos {d['screw']} @ {d['spacing']} mm",
                                          f"Spline {d['spline']} + {d['screw']} screws @ {d['spacing']} mm", f"Накладка {d['spline']} + шурупи {d['screw']} @ {d['spacing']} мм")), 1.8)
    # --- détail 4 : appui CLT sur poutre
    if r["floors"] and r["floors"][0]["beams"]:
        bm = max(r["floors"][0]["beams"], key=lambda b: b["h"])
        x0, y0 = 1.55, 0.25
        bh = min(bm["h"] / 1000, 0.6)
        sh.rect("CHARPENTE", x0 + 0.40, y0, x0 + 0.40 + bm["b"] / 1000, y0 + bh, 0.35, GLU, hatch="bois")
        sh.rect("CHARPENTE", x0, y0 + bh, x0 + 1.1, y0 + bh + hc, 0.35, WOOD, hatch="bois")
        for xx in (x0 + 0.42, x0 + 0.40 + bm["b"] / 1000 - 0.02):
            sh.line("ACIER", (xx, y0 + bh + hc), (xx, y0 + bh - 0.10), 0.4)
        sh.text("TEXTE", (x0, y0 + bh + hc + 0.10), S(t("DÉTAIL 4 — APPUI CLT SUR POUTRE", "PORMENOR 4 — APOIO CLT SOBRE VIGA", "DETAIL 4 — CLT BEARING ON BEAM",
                                                         "ВУЗОЛ 4 — ОПИРАННЯ CLT НА БАЛКУ")), 2.4, bold=True)
        sh.text("TEXTE", (x0 + 0.40 + bm["b"] / 1000 + 0.05, y0 + 0.2), S(f"{bm['id']} GL {bm['b']}×{bm['h']}"), 1.8)
        sh.text("TEXTE", (x0 + 0.40 + bm["b"] / 1000 + 0.05, y0 + 0.06), S(t("Vis Ø8 entièrement filetées @ 300 mm", "Parafusos Ø8 rosca total @ 300 mm",
                                                                             "Ø8 fully threaded screws @ 300 mm", "Шурупи Ø8 з повною різьбою @ 300 мм")), 1.8)
    _note(sh, t("Dimensions en mm. Détails de principe à l'échelle 1:10 ; quincaillerie sous ETA, références du fabricant retenu à soumettre au BET.",
                "Dimensões em mm. Pormenores de princípio à escala 1:10; ferragens com ETA, referências do fabricante a submeter ao projetista.",
                "Dimensions in mm. Principle details at 1:10; hardware with ETA, chosen manufacturer's references to be submitted to the engineer.",
                "Розміри в мм. Принципові вузли М 1:10; кріплення з ETA, марки виробника погодити з проєктувальником."),
          t("Aboutage de poteaux : appui bois debout / bois debout sur platine 15 mm, CLT découpé autour du poteau (aucune compression transversale du CLT).",
            "Emenda de pilares: apoio topo / topo sobre chapa 15 mm, CLT recortado em torno do pilar (sem compressão transversal do CLT).",
            "Column splice: end-grain to end-grain bearing on a 15 mm plate, CLT cut around the column (no perpendicular-to-grain crushing of the CLT).",
            "Стик колон: торцеве опирання на пластину 15 мм, CLT вирізано навколо колони (без зминання CLT поперек волокон)."))
    return sh


# ================================================================ CL4x tableaux
def tables(m, r) -> list[Sheet]:
    out = []
    rows = []
    for f in r["floors"]:
        for tp in f["ptypes"]:
            rows.append([f"{f['tag']}-{tp['type']}", f["name"], tp["layup"], num(tp["L"]), num(tp["w"]), str(tp["n"]), num(tp["area"], 1), num(tp["vol"], 2),
                         ", ".join(tp["ids"][:6]) + (" …" if len(tp["ids"]) > 6 else "")])
    head = [(t("Type", "Tipo", "Type", "Тип"), 16), (t("Niveau", "Piso", "Level", "Рівень"), 30), (t("Composition", "Composição", "Layup", "Структура"), 22),
            ("L (m)", 14), ("l (m)", 14), ("Nb", 10), ("m²", 16), ("m³", 16), (t("Repères", "Referências", "Marks", "Марки"), 120)]
    out += table_sheets("CL40", t("Tableau des panneaux CLT", "Quadro dos painéis CLT", "CLT panel schedule", "Таблиця панелей CLT"), "", head, rows, "table",
                        notes=[t(f"Total CLT : {num(r['quantities']['clt_m2'], 1)} m² — {num(r['quantities']['clt_m3'], 2)} m³",
                                 f"Total CLT: {num(r['quantities']['clt_m2'], 1)} m² — {num(r['quantities']['clt_m3'], 2)} m³",
                                 f"CLT total: {num(r['quantities']['clt_m2'], 1)} m² — {num(r['quantities']['clt_m3'], 2)} m³",
                                 f"Усього CLT: {num(r['quantities']['clt_m2'], 1)} м² — {num(r['quantities']['clt_m3'], 2)} м³")])
    rows = []
    for f in r["floors"]:
        groups = {}
        for bm in f["beams"]:
            groups.setdefault((bm["role"], bm["b"], bm["h"], bm["grade"], round(bm["L"], 2)), []).append(bm)
        for (role, b, h, g, L), lst in sorted(groups.items(), key=lambda kv: (kv[0][0], -kv[0][2])):
            s = max(lst, key=lambda x: x["sec"]["u_max"])["sec"]
            rows.append([f["tag"], _role(role), f"{b}×{h}", g, num(L), str(len(lst)), num(b * h / 1e6 * L * len(lst), 2), num(s["M_Ed"], 1),
                         num(s["V_Ed"], 1), num(s["u_max"]), ", ".join(x["id"] for x in lst[:5]) + (" …" if len(lst) > 5 else "")])
    for c in r["columns"]:
        for s in c["segs"]:
            rows.append([s["level"], t("Poteau", "Pilar", "Column", "Колона"), f"{s['b']}×{s['h']}", s["grade"], num(s["Lc"] + 0.3), "1",
                         num(s["b"] * s["h"] / 1e6 * (s["Lc"] + 0.3), 2), "—", "—", num(s["chk"]["u_max"]), c["name"]])
    head = [(t("Niv.", "Piso", "Lvl", "Рів."), 12), (t("Rôle", "Função", "Role", "Роль"), 26), ("b×h", 20), (t("Classe", "Classe", "Grade", "Клас"), 16),
            ("L (m)", 14), ("Nb", 10), ("m³", 16), ("M_Ed kN·m", 20), ("V_Ed kN", 18), (t("Taux", "Taxa", "Ratio", "Коеф."), 14), (t("Repères", "Referências", "Marks", "Марки"), 92)]
    if rows:
        out += table_sheets("CL41", t("Tableau des pièces en lamellé-collé", "Quadro das peças em lamelado-colado", "Glulam member schedule",
                                      "Таблиця елементів з клеєного бруса"), "", head, rows, "table")
    rows = []
    for h in r["connections"]["hanger_types"]:
        rows.append([h["type"], t("Étrier caché", "Ligador oculto", "Concealed hanger", "Прихована опора"), f"{h['screws']} × Ø8×{h['L']} 45°", h["plate"],
                     str(h["n"]), num(h["V_max"], 1), num(h["V_Rd"], 1)])
    seen = {}
    for b in r["connections"]["bases"]:
        k_ = (b["B"], b["t"], b["rod"])
        seen.setdefault(k_, []).append(b)
    for k, ((B, tt, rod), lst) in enumerate(sorted(seen.items()), 1):
        rows.append([f"PP{k}", t("Pied de poteau", "Base de pilar", "Column base", "Опора колони"), f"PL {B}×{B}×{tt} + 4 {rod}", lst[0]["dowels"], str(len(lst)),
                     num(max(x["NEd"] for x in lst), 0), "—"])
    lat = r["lateral"]
    for d, br in (lat.get("braces") or {}).items():
        rows.append([f"X{d.upper()}", t("Palée en croix", "Contraventamento em cruz", "Cross bracing", "Хрестові в'язі"), f"{br['rod']} S355", f"{br['angle']}°",
                     str(br["n"]), num(br["N"], 1), "—"])
    for d, wv in (lat.get("walls") or {}).items():
        rows.append([f"E{d.upper()}", t("Équerres de cisaillement", "Esquadros de corte", "Shear brackets", "Кутики зсуву"), f"{wv['brackets']} u/niv.",
                     f"F_Rd {num(wv['F_br'], 0)} kN", str(wv["brackets"]), num(lat["V_d"][d], 1), "—"])
        rows.append([f"HD{d.upper()}", "Hold-down", f"{wv['holddowns']} u/niv.", f"F_Rd {num(wv['F_hd'], 0)} kN", str(wv["holddowns"]), num(wv["T_holddown"], 1), "—"])
    head = [(t("Repère", "Ref.", "Mark", "Марка"), 16), (t("Désignation", "Designação", "Description", "Найменування"), 40), (t("Composition", "Composição", "Make-up", "Склад"), 52),
            (t("Plaque / note", "Chapa / nota", "Plate / note", "Пластина / прим."), 46), ("Nb", 12), ("E_d kN", 20), ("R_d kN", 20)]
    out += table_sheets("CL42", t("Tableau des assemblages", "Quadro das ligações", "Connection schedule", "Таблиця вузлів"), "", head, rows, "table",
                        notes=[t("Capacités des équerres / hold-down : valeurs de conception à confirmer par l'ETA du produit retenu.",
                                 "Capacidades dos esquadros / hold-down: valores de projeto a confirmar pela ETA do produto escolhido.",
                                 "Bracket / hold-down capacities: design values to be confirmed by the chosen product's ETA.",
                                 "Несучу здатність кутиків / hold-down підтвердити ETA обраного виробу.")])
    rows = []
    for p in r["foundations"].get("pads", []):
        rows.append([p["name"], f"{num(p['B'])} × {num(p['B'])}", num(p["h"]), num(p["N"], 0), num(p["sigma"], 0), FS.mesh_txt(p["mesh"]) if hasattr(FS, "mesh_txt") else str(p["mesh"].get("txt", ""))])
    for s in r["foundations"].get("wall_strips", []):
        rows.append([s["id"], f"{num(s['B'])} × {num(s['L'])}", num(s["h"]), num(s["n"], 0) + " /m", num(s["sigma"], 0), FS.mesh_txt(s["mesh"]) if hasattr(FS, "mesh_txt") else ""])
    head = [(t("Semelle", "Sapata", "Footing", "Фундамент"), 24), ("B × L (m)", 30), ("h (m)", 16), ("N_ser kN", 22), ("σ kPa", 18),
            (t("Armatures (2 nappes croisées)", "Armaduras (2 direções)", "Reinforcement (2-way)", "Армування (2 напрями)"), 70)]
    if rows:
        out += table_sheets("CL43", t("Tableau des fondations", "Quadro das fundações", "Foundation schedule", "Таблиця фундаментів"), "", head, rows, "table")
    return out


def _role(role):
    return {"main": t("Poutre porteuse", "Viga principal", "Main beam", "Головна балка"), "purlin": t("Panne", "Madre", "Purlin", "Прогон"),
            "girder": t("Sommier", "Viga mestra", "Girder", "Ригель"), "edge": t("Poutre de rive", "Viga de bordadura", "Edge beam", "Крайова балка")}.get(role, role)


def all_sheets(m, r) -> list[Sheet]:
    shs = [cover(m, r), iso(m, r), foundations(m, r)]
    if r["columns"] or r["walls"]:
        shs.append(columns_plan(m, r))
    for k, f in enumerate(r["floors"], 1):
        shs.append(framing(m, r, f, f"CL1{k}" if k < 10 else f"CL1{k}"))
    for k, f in enumerate(r["floors"], 1):
        shs.append(clt_plan(m, r, f, f"CL2{k}"))
    shs.append(section(m, r))
    shs.append(details(m, r))
    shs += tables(m, r)
    toc(shs[0], shs)
    return shs
