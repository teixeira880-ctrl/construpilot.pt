"""(Versão PT, textos em português) Photovoltaïque résidentiel en toiture (France / Portugal) — pré-dimensionnement indicatif.

Production : productible spécifique (kWh/kWc.an, orientation optimale, pertes système incluses, ordre de grandeur PVGIS) × facteur
d'orientation / inclinaison × (1 − ombrage). Autoconsommation estimée par une loi empirique selon le rapport production / consommation
et le profil de présence. Électrique (UTE C15-712-1 / NF C 15-100 partie 7-712 ; RTIEBT secção 712 au Portugal) : nombre de modules
par chaîne (tension à froid ≤ tension max onduleur, tension MPP à chaud ≥ seuil MPPT), courant (Iz ≥ 1,25 Isc), sections et chutes
de tension DC / AC, protections. Économie : économie sur facture + vente du surplus, coût, temps de retour.
Les tarifs (achat, rachat du surplus, coût installé) changent souvent : valeurs datées, remplaçables par l'utilisateur.
"""
from __future__ import annotations

import math

from . import climat

# ---------------------------------------------------------------------------------------------------------------------------------
# Productible spécifique (kWh/kWc.an) à orientation optimale, pertes système ≈ 14 % incluses — ordres de grandeur PVGIS
PROD_FR = {"H1a": 1100, "H1b": 1130, "H1c": 1270, "H2a": 1180, "H2b": 1230, "H2c": 1320, "H2d": 1500, "H3": 1540}
PROD_PT = {"1": 1640, "2": 1600, "3": 1550, "4": 1520, "5": 1540, "6": 1580, "7": 1680, "8": 1720, "9": 1400}   # 1er chiffre du code postal
REGION_PT = {"1": "Lisboa", "2": "Lisboa / Setúbal / Santarém / Leiria", "3": "Coimbra / Aveiro / Viseu", "4": "Porto / Braga / Viana",
             "5": "Vila Real / Bragança", "6": "Castelo Branco / Guarda", "7": "Évora / Beja / Portalegre", "8": "Faro (Algarve)", "9": "Madeira / Açores"}
# facteur d'orientation : azimut par rapport au sud (0 = sud, 90 = est/ouest, 180 = nord) × inclinaison (°)
_AZ = [0, 45, 90, 135, 180]
_TI = [0, 30, 60, 90]
_F = [[0.93, 1.00, 0.91, 0.68], [0.93, 0.96, 0.88, 0.66], [0.93, 0.90, 0.78, 0.55], [0.93, 0.75, 0.58, 0.40], [0.93, 0.58, 0.40, 0.28]]   # table usuelle (Hespul / ADEME)

# Tarifs indicatifs (à mettre à jour) — sources et dates dans TARIFS["source"]
TARIFS = {
    "fr": {"achat_kwh": 0.2001, "surplus_kwh": {100: 0.011}, "prime_kwc": {}, "cout_kwc": {3: 2300, 6: 2000, 9: 1850, 36: 1500},
           "tva": "TVA 5,5 % jusqu'à 9 kWc si conditions de l'arrêté du 08/09/2025 (sinon 20 %, batterie 20 %)",
           "source": "tarif bleu Base 01/08/2026 ; rachat du surplus S21 modifié le 05/06/2026 (1,1 c€/kWh, prime à l'autoconsommation supprimée) ; coûts TTC indicatifs 2026"},
    "pt": {"achat_kwh": 0.21, "surplus_kwh": {9999: 0.03}, "prime_kwc": {}, "cout_kwc": {3: 1600, 6: 1450, 9: 1300, 36: 1050},
           "tva": "IVA 23 % (taxa reduzida de 6 % terminada em 30/06/2025, a confirmar)",
           "source": "tarifa regulada simples out. 2026 ≈ 0,171 €/kWh s/ IVA ; excedente 0,025–0,04 €/kWh (contrato, OMIE) ; custos indicativos 2026"},
}
MODULE_DEFAUT = {"wc": 430, "voc": 39.0, "isc": 13.9, "vmp": 32.8, "imp": 13.1, "beta_voc": -0.26, "gamma_vmp": -0.34, "surface_m2": 1.95, "masse_kg": 21.5}
ONDULEURS = [  # (kVA AC, phase, Vmax DC, MPPT min, MPPT max, I max d'entrée par MPPT, Isc max par MPPT, nb MPPT) — onduleurs chaîne courants
    (3.0, "mono", 600, 90, 560, 16, 22, 2), (3.6, "mono", 600, 90, 560, 16, 22, 2), (4.6, "mono", 600, 90, 560, 16, 22, 2), (6.0, "mono", 600, 90, 560, 16, 22, 2),
    (8.0, "tri", 1000, 160, 950, 16, 22, 2), (10.0, "tri", 1000, 160, 950, 16, 22, 2), (15.0, "tri", 1000, 160, 950, 26, 32, 2), (20.0, "tri", 1000, 160, 950, 26, 32, 2),
    (30.0, "tri", 1000, 200, 950, 32, 40, 3)]
RHO_CU = 0.0225   # Ω.mm²/m à ≈ 70 °C (câble solaire)
SECTIONS_DC = [4, 6, 10, 16]
IZ_DC = {4: 55, 6: 70, 10: 98, 16: 132}             # câble solaire H1Z2Z2-K, pose en air (ordre de grandeur fabricants)
SECTIONS_AC = [(2.5, 20), (4, 25), (6, 32), (10, 40), (16, 63)]   # (mm², calibre disjoncteur max) conducteurs cuivre usuels
CALIBRES = [10, 16, 20, 25, 32, 40, 50, 63]


def facteur_orientation(azimut_sud: float, inclinaison: float) -> float:
    a = min(180.0, abs(((azimut_sud + 180) % 360) - 180))
    t = max(0.0, min(90.0, inclinaison))
    i = min(len(_AZ) - 2, int(a // 45))
    j = min(len(_TI) - 2, int(t // 30))
    fa = (a - _AZ[i]) / 45
    ft = (t - _TI[j]) / 30
    f00, f01, f10, f11 = _F[i][j], _F[i][j + 1], _F[i + 1][j], _F[i + 1][j + 1]
    return (f00 * (1 - fa) * (1 - ft) + f01 * (1 - fa) * ft + f10 * fa * (1 - ft) + f11 * fa * ft)


def _productible(pays: str, cp: str | None) -> tuple[float, str]:
    if pays == "pt":
        k = (cp or "").strip()[:1]
        if k not in PROD_PT:
            return 1500.0, "Portugal (média nacional, código postal não indicado)"
        return float(PROD_PT[k]), REGION_PT[k]
    try:
        from .re2020 import DEPT_ZONE
    except ImportError:
        raise ValueError("versão portuguesa: apenas instalações em Portugal (pays = pt)")
    d = climat.departement(cp)
    z = DEPT_ZONE.get(d or "")
    if not z:
        return 1150.0, "France (moyenne, code postal non fourni)"
    return float(PROD_FR[z]), f"département {d} (zone {z})"


def _tarif_palier(table: dict, kwc: float) -> float:
    for k in sorted(table):
        if kwc <= k:
            return table[k]
    return table[max(table)]


def taux_autoconsommation(production: float, consommation: float, profil: str, batterie_kwh: float = 0.0) -> float:
    """Part de la production consommée sur place (loi empirique) : SCR = k / (k + r), r = production / consommation."""
    if production <= 0 or consommation <= 0:
        return 0.0
    k = {"absent_journee": 0.35, "mixte": 0.5, "present_journee": 0.7, "teletravail": 0.7}.get(profil, 0.5)
    k += min(0.6, 0.12 * batterie_kwh)                       # une batterie déplace la production vers le soir
    r = production / consommation
    return min(0.95, k / (k + r))


def calculer(p: dict) -> dict:
    pays = p.get("pays") or "pt"
    if pays not in TARIFS:
        raise ValueError("pays : 'fr' ou 'pt'")
    hyp: list[str] = []
    fourni = {k: float(v) for k, v in (p.get("module") or {}).items() if v is not None}
    mod = {**MODULE_DEFAUT, **fourni}
    if fourni and set(fourni) < {"wc", "voc", "isc", "vmp", "imp"}:
        if "wc" in fourni and fourni["wc"] != MODULE_DEFAUT["wc"]:   # mise à l'échelle des caractéristiques électriques
            k = fourni["wc"] / MODULE_DEFAUT["wc"]
            for c_ in ("isc", "imp"):
                mod[c_] = fourni.get(c_, MODULE_DEFAUT[c_] * k)
            mod["surface_m2"] = fourni.get("surface_m2", MODULE_DEFAUT["surface_m2"] * k)
        hyp.append("fiche module incomplète : caractéristiques électriques manquantes déduites d'un module standard")
    if not p.get("module"):
        hyp.append(f"módulo standard {mod['wc']:g} Wc (Voc {mod['voc']:g} V, Isc {mod['isc']:g} A, Vmp {mod['vmp']:g} V) : substituir pela ficha técnica")
    if p.get("puissance_kwc"):
        n_mod = max(1, round(float(p["puissance_kwc"]) * 1000 / mod["wc"]))
    elif p.get("surface_toiture_m2"):
        n_mod = max(1, int(float(p["surface_toiture_m2"]) * 0.8 / mod["surface_m2"]))
        hyp.append("80 % da área de cobertura utilizável (beirados, cumeeira, obstáculos)")
    elif p.get("consommation_kwh"):
        n_mod = None
    else:
        raise ValueError("fournir puissance_kwc, surface_toiture_m2 ou consommation_kwh")
    cp = p.get("code_postal")
    prod_sp, lieu = _productible(pays, cp)
    az, inc = float(p.get("azimut_sud") or 0), float(p.get("inclinaison") if p.get("inclinaison") is not None else 30)
    f_or = facteur_orientation(az, inc)
    ombrage = float(p.get("ombrage_pct") or 0) / 100
    if not 0 <= ombrage < 0.95:
        raise ValueError("ombrage_pct doit être compris entre 0 et 95 %")
    conso = float(p.get("consommation_kwh") or 0)
    profil = p.get("profil") or "mixte"
    batt = float(p.get("batterie_kwh") or 0)
    if n_mod is None:      # dimensionnement par la consommation : rapport production / consommation ≈ 0,8
        kwc_cible = 0.8 * conso / (prod_sp * f_or * (1 - ombrage))
        n_mod = max(4, round(kwc_cible * 1000 / mod["wc"]))
        hyp.append("potência dimensionada para produzir ≈ 80 % do consumo anual (bom compromisso autoconsumo / excedente)")
    kwc = n_mod * mod["wc"] / 1000
    prod = kwc * prod_sp * f_or * (1 - ombrage)
    if not p.get("consommation_kwh"):
        conso = 4500.0
        hyp.append("consumo anual não indicado: considerados 4 500 kWh")
    scr = taux_autoconsommation(prod, conso, profil, batt)
    auto = prod * scr
    surplus = prod - auto
    # ---- électrique
    t_min = float(p.get("t_min") if p.get("t_min") is not None else (climat.temperature_base(cp)[0] if pays == "fr" and cp else -5.0 if pays == "pt" else -10.0))
    kva_cible = kwc / float(p.get("ratio_dc_ac") or 1.15)
    ond = next((o for o in ONDULEURS if o[0] >= kva_cible - 1e-9), ONDULEURS[-1])
    if p.get("raccordement") == "tri" and ond[1] == "mono":
        ond = next(o for o in ONDULEURS if o[1] == "tri")
    mono_impose = p.get("raccordement") == "mono"
    if mono_impose and ond[1] == "tri":
        ond = max((o for o in ONDULEURS if o[1] == "mono"), key=lambda o: o[0])
    kva, phase, vmax, vmppt_min, vmppt_max, imax, iscmax, nmppt = ond
    voc_froid = mod["voc"] * (1 + mod["beta_voc"] / 100 * (t_min - 25))
    vmp_chaud = mod["vmp"] * (1 + mod["gamma_vmp"] / 100 * (70 - 25))
    vmp_froid = mod["vmp"] * (1 + mod["gamma_vmp"] / 100 * (t_min - 25))
    n_max = int(min(vmax / voc_froid, vmppt_max / vmp_froid))
    n_min = math.ceil(vmppt_min / vmp_chaud)
    if n_min > n_max:
        raise ValueError("module incompatible avec l'onduleur (plage MPPT)")
    n_ch = max(1, math.ceil(n_mod / n_max))
    mods_par_ch = [n_mod // n_ch + (1 if i < n_mod % n_ch else 0) for i in range(n_ch)]
    ctl = []
    ctl.append({"ref": "Tensão a frio (RTIEBT secção 712 / IEC 62548)", "exigence": f"n × Voc({t_min:g} °C) ≤ {vmax} V (onduleur)",
                "valeur": f"{max(mods_par_ch)} × {voc_froid:.1f} = {max(mods_par_ch) * voc_froid:.0f} V", "ok": max(mods_par_ch) * voc_froid <= vmax})
    ctl.append({"ref": "Gama MPPT a quente", "exigence": f"n × Vmp(70 °C) ≥ {vmppt_min} V", "valeur": f"{min(mods_par_ch)} × {vmp_chaud:.1f} = {min(mods_par_ch) * vmp_chaud:.0f} V",
                "ok": min(mods_par_ch) * vmp_chaud >= vmppt_min,
                "note": "poucos módulos por fileira: agrupar numa só fileira ou usar microinversores" if min(mods_par_ch) * vmp_chaud < vmppt_min else None})
    ch_par_mppt = math.ceil(n_ch / nmppt)
    ctl.append({"ref": "Corrente por entrada MPPT", "exigence": f"{ch_par_mppt} fileira(s): Σ Imp ≤ {imax} A et Σ Isc ≤ {iscmax} A (ficha do inversor)",
                "valeur": f"Imp {ch_par_mppt * mod['imp']:.1f} A · Isc {ch_par_mppt * mod['isc']:.1f} A",
                "ok": ch_par_mppt * mod["imp"] <= imax + 1e-9 and ch_par_mppt * mod["isc"] <= iscmax + 1e-9})
    ctl.append({"ref": "Rácio DC/AC", "exigence": "0,9 a 1,3", "valeur": f"{kwc:.2f} kWc / {kva:g} kVA = {kwc / kva:.2f}", "ok": 0.9 <= kwc / kva <= 1.3})
    # câbles DC (longueur aller par chaîne)
    l_dc = float(p.get("longueur_dc_m") or 20)
    v_ch = min(mods_par_ch) * mod["vmp"]
    s_dc = next((s for s in SECTIONS_DC if IZ_DC[s] >= 1.25 * mod["isc"] and 2 * RHO_CU * l_dc * mod["imp"] / s / v_ch * 100 <= 1.0), SECTIONS_DC[-1])
    du_dc = 2 * RHO_CU * l_dc * mod["imp"] / s_dc / v_ch * 100
    ctl.append({"ref": "Cabo DC (RTIEBT 712 / IEC 62548)", "exigence": "Iz ≥ 1,25·Isc; ΔU ≤ 1 % recomendado (3 % máx.)", "valeur": f"{s_dc} mm², ΔU {du_dc:.2f} %",
                "ok": du_dc <= 3.0 and IZ_DC[s_dc] >= 1.25 * mod["isc"], "note": "fusíveis de fileira obrigatórios acima de 2 fileiras em paralelo" if ch_par_mppt > 2 else None})
    # AC
    l_ac = float(p.get("longueur_ac_m") or 15)
    i_ac = kva * 1000 / (230 if phase == "mono" else math.sqrt(3) * 400)
    cal = next(c for c in CALIBRES if c >= i_ac)
    s_ac = None
    for s, cmax in SECTIONS_AC:
        du = (2 if phase == "mono" else math.sqrt(3)) * RHO_CU * l_ac * i_ac / s / (230 if phase == "mono" else 400) * 100
        if cal <= cmax and du <= 1.0:
            s_ac = (s, du)
            break
    if s_ac is None:
        s, _ = SECTIONS_AC[-1]
        s_ac = (s, (2 if phase == "mono" else math.sqrt(3)) * RHO_CU * l_ac * i_ac / s / (230 if phase == "mono" else 400) * 100)
    ctl.append({"ref": "Linha AC inversor → quadro", "exigence": "ΔU ≤ 1 % recomendado, proteção por disjuntor dedicado",
                "valeur": f"{phase} {i_ac:.1f} A → disjuntor {cal} A, {s_ac[0]:g} mm², ΔU {s_ac[1]:.2f} %", "ok": s_ac[1] <= 1.0 + 1e-9})
    if mono_impose and kwc / kva > 1.3:
        ctl.append({"ref": "Raccordement monophasé" if pays == "pt" else "Raccordement Enedis monophasé",
                    "exigence": "onduleur monophasé ≤ 6 kVA : au-delà, raccordement triphasé ou puissance crête réduite",
                    "valeur": f"{kwc:.1f} kWc pour {kva:g} kVA", "ok": False})
    # charge en toiture
    surf = n_mod * mod["surface_m2"]
    charge = (mod["masse_kg"] / mod["surface_m2"] + 3) * 9.81 / 1000
    ctl.append({"ref": "Carga permanente adicional na cobertura", "exigence": "a verificar pela estrutura da cobertura (≈ 0,15 kN/m²)", "valeur": f"{charge:.2f} kN/m² em {surf:.1f} m²",
                "ok": None if charge > 0.2 else True})
    # ---- économie
    t = TARIFS[pays]
    achat = float(p.get("prix_achat_kwh") or t["achat_kwh"])
    rachat = float(p.get("prix_surplus_kwh") if p.get("prix_surplus_kwh") is not None else _tarif_palier(t["surplus_kwh"], kwc))
    cout = float(p.get("cout_installation") or kwc * _tarif_palier(t["cout_kwc"], kwc) + batt * 700)
    prime = kwc * _tarif_palier(t["prime_kwc"], kwc) if t["prime_kwc"] else 0.0
    gain_an = auto * achat + surplus * rachat
    retour = (cout - prime) / gain_an if gain_an > 0 else None
    gain_25 = sum((auto * achat * 1.02 ** k + surplus * rachat) * (1 - 0.005) ** k for k in range(25)) - (cout - prime) - 1200   # onduleur remplacé une fois
    hyp += [f"produtividade {prod_sp:.0f} kWh/kWp.ano ({lieu}), fator de orientação {f_or:.2f} (azimute {az:g}° / sul, inclinação {inc:g}°), sombreamento {ombrage * 100:.0f} %",
            f"autoconsumo estimado {scr * 100:.0f} % da produção (perfil {profil}{', bateria %g kWh' % batt if batt else ''})",
            f"preço da eletricidade {achat:.4f} €/kWh, excedente {rachat:.4f} €/kWh, custo {cout:.0f} € — {t['source']}",
            f"ganho a 25 anos: eletricidade +2 %/ano, degradação 0,5 %/ano, substituição do inversor 1 200 €",
            t["tva"]]
    if pays == "fr":
        hyp.append("démarches : déclaration préalable de travaux (mairie), demande de raccordement Enedis, Consuel, contrat de rachat du surplus (EDF OA, plafonné à 1 600 h × kWc par an)")
    else:
        hyp.append("procedimento: UPAC — sem controlo prévio até 700 W (800 W a confirmar, DL 130/2026), mera comunicação prévia até 30 kW, registo e certificado de exploração de 30 kW a 1 MW (DL 15/2022); venda do excedente por contrato com comercializador")
    return {"pays": pays, "lieu": lieu, "n_modules": n_mod, "kwc": kwc, "module": mod, "surface_m2": surf, "productible": prod_sp, "facteur_orientation": f_or,
            "production_kwh": prod, "consommation_kwh": conso, "taux_autoconsommation": scr, "autoconsommation_kwh": auto, "surplus_kwh": surplus,
            "taux_autoproduction": auto / conso if conso else 0.0, "onduleur": {"kva": kva, "phase": phase, "vmax": vmax, "mppt": f"{vmppt_min}–{vmppt_max} V", "nb_mppt": nmppt},
            "chaines": mods_par_ch, "t_min": t_min, "cable_dc_mm2": s_dc, "cable_ac_mm2": s_ac[0], "disjoncteur_ac_a": cal,
            "economie": {"prix_achat": achat, "prix_surplus": rachat, "cout": cout, "prime": prime, "gain_annuel": gain_an, "retour_ans": retour, "gain_25_ans": gain_25},
            "controles": ctl, "hypotheses": hyp,
            "protections": ["interruptor-seccionador DC à entrada do inversor", "descarregadores de sobretensões AC/DC conforme o risco de descargas atmosféricas (RTIEBT secção 443/534)",
                            "diferencial 30 mA tipo A (tipo B se o inversor não garantir a ausência de corrente contínua)", "ligação equipotencial das estruturas",
                            "sinalética regulamentar (dupla alimentação)"]}


def note(p: dict) -> dict:
    from . import notes
    r = calculer(p)
    f, W = notes._f, notes.W
    e = r["economie"]
    rows = [["Potência de pico", f"{r['kwc']:.2f} kWp ({r['n_modules']} módulos de {r['module']['wc']:g} Wp, {r['surface_m2']:.1f} m²)"],
            ["Produção anual", f"{f(r['production_kwh'])} kWh ({r['productible']:.0f} × {r['facteur_orientation']:.2f})"],
            ["Autoconsumo", f"{f(r['autoconsommation_kwh'])} kWh ({r['taux_autoconsommation'] * 100:.0f} % da produção, {r['taux_autoproduction'] * 100:.0f} % das necessidades)"],
            ["Excedente injetado", f"{f(r['surplus_kwh'])} kWh"],
            ["Inversor", f"{r['onduleur']['kva']:g} kVA {'monofásico' if r['onduleur']['phase'] == 'mono' else 'trifásico'} — fileiras: " + " + ".join(str(n) for n in r["chaines"]) + " módulos"],
            ["Cabos", f"DC {r['cable_dc_mm2']} mm² · AC {r['cable_ac_mm2']:g} mm² · disjuntor {r['disjoncteur_ac_a']} A"],
            ["Poupança anual", f"{f(e['gain_annuel'])} €"], ["Custo estimado", f"{f(e['cout'])} €"],
            ["Retorno do investimento", f"{e['retour_ans']:.1f} anos" if e["retour_ans"] else "—"], ["Ganho líquido a 25 anos", f"{f(e['gain_25_ans'])} €"]]
    blocs = [("p", "Pré-dimensionamento indicativo — a confirmar pelo instalador (estudo de sombreamento, fichas técnicas dos equipamentos, estado da cobertura)."),
             ("h2", "1. Síntese"), ("table", ["Grandeza", "Valor"], rows, [50 * W, 125 * W]),
             ("h2", "2. Verificações elétricas e estruturais"), ("controls", r["controles"]),
             ("h2", "3. Proteções"), ("hyp", r["protections"])]
    titre = "Pré-dimensionamento fotovoltaico"
    sous = f"{r['kwc']:.2f} kWp · {r['lieu']} · {f(r['production_kwh'])} kWh/ano"
    pdf, png = notes.pdf(titre, sous, blocs, r["hypotheses"])
    return {**r, "titre": titre, "sous_titre": sous, "pdf": pdf, "png": png}
