"""Détail de montage d'une baie (fenêtre, porte-fenêtre, coulissant) avec ou sans volet roulant — dessin déterministe.

Deux vues réelles, à l'échelle, comme un détail de menuiserie d'architecte / de fabricant :
  • coupe verticale : appui (ou seuil) en bas, tête (linteau + coffre) en haut, partie courante coupée par un trait de coupure ;
  • coupe horizontale : un tableau (jambage) vu en plan, extérieur en haut, intérieur en bas.
Toutes les géométries viennent des paramètres (types de pose, de coffre, d'isolation, matériaux, cotes). Rien n'est inventé par une IA :
les valeurs par défaut sont des valeurs courantes signalées comme hypothèses dans le cartouche. Sortie : PDF vectoriel (2 pages) + 2 PNG.
Textes en français ou en portugais (lang="fr" | "pt")."""
from __future__ import annotations

import io
import math
from dataclasses import dataclass, field

# ----------------------------------------------------------------------------------------------------------------- vocabulaire
POSES = ("applique_int", "tunnel", "feuillure", "renovation", "applique_ext")
COFFRES = ("aucun", "monobloc", "tunnel", "interieur", "exterieur")
OUVRAGES = ("fenetre", "porte_fenetre", "coulissant")
ISOLATIONS = ("iti", "ite", "aucune")
MATERIAUX = ("pvc", "alu", "bois")
MURS = ("beton", "parpaing", "brique", "pierre")

# poses compatibles avec chaque coffre (au-delà : refus avec une explication, l'Assistant pose la question)
COFFRE_POSES = {"aucun": POSES, "monobloc": ("applique_int", "applique_ext"), "tunnel": ("tunnel", "applique_int", "feuillure"),
                "interieur": ("tunnel", "applique_int", "renovation"), "exterieur": POSES}

T = {
    "fr": {
        "title": {"fenetre": "Fenêtre", "porte_fenetre": "Porte-fenêtre", "coulissant": "Baie coulissante"},
        "vr": "avec volet roulant", "sans_vr": "sans volet roulant",
        "pose": {"applique_int": "pose en applique intérieure", "tunnel": "pose en tunnel", "feuillure": "pose en feuillure",
                 "renovation": "pose en rénovation (sur dormant existant)", "applique_ext": "pose en applique extérieure (ITE)"},
        "coffre": {"aucun": "", "monobloc": "coffre monobloc (bloc-baie)", "tunnel": "coffre tunnel", "interieur": "coffre intérieur apparent",
                   "exterieur": "coffre extérieur (en façade)"},
        "iso": {"iti": "isolation intérieure", "ite": "isolation par l'extérieur", "aucune": "mur non isolé"},
        "mat": {"pvc": "PVC", "alu": "aluminium à rupture de pont thermique", "bois": "bois"},
        "mur": {"beton": "voile béton", "parpaing": "parpaing", "brique": "brique", "pierre": "maçonnerie de pierre"},
        "v": "COUPE VERTICALE", "h": "COUPE HORIZONTALE (tableau vu en plan)",
        "int": "INTÉRIEUR", "ext": "EXTÉRIEUR", "scale": "Échelle", "partie_courante": "partie courante non représentée",
        "subtitle": "Détail de principe — à confirmer par la notice de pose du fabricant et le DTU 36.5",
        "legend": "Légende", "reserv": "Cotes clés", "hyp": "Hypothèses / à valider",
        "foot": "ConstruPilot — détail de principe dessiné à partir des cotes du dossier (cotes en mm). Ne vaut pas plan d'exécution.",
        "e": {
            "mur": "Mur {mur} — {ep} mm", "linteau": "Linteau béton armé — h {h} mm", "dalle": "Dalle / plancher béton — {ep} mm",
            "planelle": "Planelle de rive + rupteur", "allege": "Allège {mur}",
            "isolant_int": "Doublage : isolant {ep} mm", "plaque": "Plaque de plâtre 13 mm", "enduit_int": "Enduit plâtre intérieur",
            "isolant_ext": "Isolant ITE {ep} mm (fixé-collé)", "enduit_ext": "Enduit extérieur", "retour_iso": "Retour d'isolant en tableau",
            "dormant": "Dormant {mat} — prof. {d} mm", "tapee": "Tapée d'isolation (élargisseur) {d} mm", "ouvrant": "Ouvrant {mat}",
            "vitrage": "Double vitrage isolant {v}", "parclose": "Parclose", "joint_mousse": "Mousse imprégnée précomprimée (étanchéité air/eau)",
            "mastic": "Mastic élastomère sur fond de joint", "membrane": "Membrane d'étanchéité à l'air (pare-vapeur) collée",
            "cale": "Cales d'assise + fixation (vis/pattes)", "appui": "Appui béton préfabriqué : pente ≥ 10 %, rejingot, larmier",
            "bavette": "Bavette aluminium (pente ≥ 10 %)", "tablette": "Tablette intérieure",
            "seuil": "Seuil aluminium à rupture thermique (ressaut ≤ 20 mm)", "seuil_ext": "Seuil / pièce d'appui extérieure (pente)",
            "chape": "Chape + isolant sous chape", "revet": "Revêtement de sol fini", "sol_ext": "Revêtement extérieur (terrasse / dallage)",
            "caniveau": "Caniveau à grille (évacuation des eaux, accès PMR)",
            "coffre_mono": "Coffre monobloc isolé — H {h} mm (fait partie du bloc-baie)", "coffre_tunnel": "Coffre tunnel dans l'épaisseur du mur — H {h} mm",
            "coffre_int": "Coffre intérieur apparent — H {h} mm", "coffre_ext": "Coffre extérieur en façade — {h} × {h} mm",
            "tablier": "Tablier enroulé Ø {d} mm (lames alu/PVC)", "lame_finale": "Lame finale", "trappe": "Trappe de visite",
            "coulisse": "Coulisse de volet roulant", "tablier_ferme": "Tablier en position fermée", "habillage": "Habillage / lambrequin",
            "ancien_dormant": "Dormant existant conservé (bois)", "aile": "Aile de recouvrement du dormant de rénovation",
            "cornière": "Cornière d'habillage extérieure", "plafond": "Plafond (plaque / enduit)",
        },
        "k": {
            "hm": "Hauteur menuiserie (hors coffre)", "lm": "Largeur menuiserie", "hc": "Hauteur coffre", "hres": "Hauteur de réservation (maçonnerie)",
            "lres": "Largeur de réservation (maçonnerie)", "roll": "Ø tablier enroulé (calcul)", "ressaut": "Ressaut du seuil intérieur / extérieur",
            "rec": "Recouvrement du dormant sur la maçonnerie", "jeu": "Jeu de pose périphérique", "allege": "Hauteur d'allège (sol fini / dessus d'appui)",
            "debord": "Débord de l'appui / bavette sur la façade",
        },
        "notes": {
            "defaults": "Cotes non fournies prises par défaut (valeurs courantes) : {keys}.",
            "dtu": "Mise en œuvre selon NF DTU 36.5 et la notice du fabricant ; la fixation et l'étanchéité sont du ressort du poseur.",
            "pmr": "Seuil PMR : ressauts ≤ 2 cm (arrondis/chanfreinés) ; seuil sans rejingot : protection par caniveau et pente extérieure.",
            "mono": "Bloc-baie : coffre, dormant et coulisses forment une seule pièce posée en applique — pas de coffre rapporté séparé.",
            "tunnel_coffre": "Coffre tunnel : réservation haute = hauteur menuiserie + hauteur coffre ; isoler la sous-face et la face intérieure du coffre.",
            "interieur": "Coffre intérieur : réduit la hauteur de passage ; prévoir l'isolation et l'étanchéité à l'air du caisson.",
            "exterieur": "Coffre extérieur : solution de rénovation, aucune réservation ; coulisses fixées en façade.",
            "ite": "ITE : menuiserie dans le plan de l'isolant (ou retour d'isolant ≥ 20 mm en tableau) pour traiter le pont thermique.",
            "reno": "Rénovation : l'ancien dormant doit être sain et d'équerre ; jour réduit d'environ 2 × l'aile.",
        },
    },
    "pt": {
        "title": {"fenetre": "Janela", "porte_fenetre": "Porta-janela", "coulissant": "Vão de correr"},
        "vr": "com estore de enrolar", "sans_vr": "sem estore",
        "pose": {"applique_int": "montagem pelo interior (aplique)", "tunnel": "montagem em túnel (no vão)", "feuillure": "montagem em batente / rebaixo",
                 "renovation": "montagem de renovação (sobre aro existente)", "applique_ext": "montagem pelo exterior (ETICS / capoto)"},
        "coffre": {"aucun": "", "monobloc": "caixa monobloco (bloco-vão)", "tunnel": "caixa túnel", "interieur": "caixa interior à vista",
                   "exterieur": "caixa exterior (na fachada)"},
        "iso": {"iti": "isolamento pelo interior", "ite": "isolamento pelo exterior (ETICS)", "aucune": "parede sem isolamento"},
        "mat": {"pvc": "PVC", "alu": "alumínio com corte térmico", "bois": "madeira"},
        "mur": {"beton": "parede de betão", "parpaing": "bloco de betão", "brique": "tijolo", "pierre": "alvenaria de pedra"},
        "v": "CORTE VERTICAL", "h": "CORTE HORIZONTAL (ombreira em planta)",
        "int": "INTERIOR", "ext": "EXTERIOR", "scale": "Escala", "partie_courante": "zona corrente não representada",
        "subtitle": "Pormenor de princípio — a confirmar pelas instruções de montagem do fabricante",
        "legend": "Legenda", "reserv": "Cotas principais", "hyp": "Hipóteses / a validar",
        "foot": "ConstruPilot — pormenor de princípio desenhado a partir das cotas do processo (cotas em mm). Não é desenho de execução.",
        "e": {
            "mur": "Parede de {mur} — {ep} mm", "linteau": "Padieira / verga de betão armado — h {h} mm", "dalle": "Laje de betão — {ep} mm",
            "planelle": "Remate de laje + corte térmico", "allege": "Peitoril em {mur}",
            "isolant_int": "Contra-fachada: isolamento {ep} mm", "plaque": "Placa de gesso cartonado 13 mm", "enduit_int": "Estuque interior",
            "isolant_ext": "Isolamento ETICS {ep} mm (colado e fixado)", "enduit_ext": "Reboco exterior", "retour_iso": "Retorno de isolamento na ombreira",
            "dormant": "Aro {mat} — prof. {d} mm", "tapee": "Alargador de aro (tapa-isolamento) {d} mm", "ouvrant": "Folha {mat}",
            "vitrage": "Vidro duplo isolante {v}", "parclose": "Bite", "joint_mousse": "Fita de espuma pré-comprimida (estanquidade ar/água)",
            "mastic": "Mastique elastomérico sobre cordão de fundo", "membrane": "Membrana de estanquidade ao ar (barreira de vapor) colada",
            "cale": "Calços de assentamento + fixação (parafusos/grampos)", "appui": "Peitoril pré-fabricado de betão: pendente ≥ 10 %, ressalto, pingadeira",
            "bavette": "Rufo / peitoril de alumínio (pendente ≥ 10 %)", "tablette": "Parapeito interior",
            "seuil": "Soleira de alumínio com corte térmico (ressalto ≤ 20 mm)", "seuil_ext": "Soleira exterior (com pendente)",
            "chape": "Betonilha + isolamento sob betonilha", "revet": "Revestimento de piso", "sol_ext": "Revestimento exterior (terraço)",
            "caniveau": "Caleira com grelha (drenagem, acessibilidade)",
            "coffre_mono": "Caixa monobloco isolada — H {h} mm (faz parte do bloco-vão)", "coffre_tunnel": "Caixa túnel na espessura da parede — H {h} mm",
            "coffre_int": "Caixa interior à vista — H {h} mm", "coffre_ext": "Caixa exterior na fachada — {h} × {h} mm",
            "tablier": "Estore enrolado Ø {d} mm (réguas alu/PVC)", "lame_finale": "Régua final", "trappe": "Tampa de visita",
            "coulisse": "Calha-guia do estore", "tablier_ferme": "Estore na posição fechada", "habillage": "Remate / sanca",
            "ancien_dormant": "Aro existente mantido (madeira)", "aile": "Aba de recobrimento do aro de renovação",
            "cornière": "Cantoneira de remate exterior", "plafond": "Teto (placa / estuque)",
        },
        "k": {
            "hm": "Altura da caixilharia (sem caixa)", "lm": "Largura da caixilharia", "hc": "Altura da caixa", "hres": "Altura do vão em tosco",
            "lres": "Largura do vão em tosco", "roll": "Ø do estore enrolado (cálculo)", "ressaut": "Ressalto da soleira interior / exterior",
            "rec": "Recobrimento do aro sobre a alvenaria", "jeu": "Folga de montagem periférica", "allege": "Altura do peitoril (piso acabado / peitoril)",
            "debord": "Saliência do peitoril / rufo sobre a fachada",
        },
        "notes": {
            "defaults": "Cotas não fornecidas tomadas por defeito (valores correntes): {keys}.",
            "dtu": "Execução segundo as instruções do fabricante e as boas práticas (ex. ITE 51 / LNEC); fixação e vedação a cargo do instalador.",
            "pmr": "Acessibilidade (DL 163/2006): ressaltos ≤ 2 cm boleados; soleira sem ressalto: proteger com caleira e pendente exterior.",
            "mono": "Bloco-vão: caixa, aro e calhas-guia formam uma só peça montada pelo interior — não há caixa separada.",
            "tunnel_coffre": "Caixa túnel: vão em tosco = altura da caixilharia + altura da caixa; isolar a face inferior e interior da caixa.",
            "interieur": "Caixa interior: reduz a altura de passagem; prever isolamento e estanquidade ao ar da caixa.",
            "exterieur": "Caixa exterior: solução de renovação, sem reserva no vão; calhas fixadas na fachada.",
            "ite": "ETICS: caixilharia no plano do isolamento (ou retorno de isolamento ≥ 20 mm na ombreira) para tratar a ponte térmica.",
            "reno": "Renovação: o aro antigo deve estar são e em esquadria; o vão útil reduz cerca de 2 × a aba.",
        },
    },
}

# couleurs / hachures (style plan d'architecte : niveaux de gris + une teinte par famille)
STYLE = {
    "beton": ("#d6d6d6", "beton"), "parpaing": ("#cfcfcf", "parpaing"), "brique": ("#e9b9a0", "brique"), "pierre": ("#d9cbb5", "pierre"),
    "isolant": ("#fff3b0", "laine"), "pse": ("#fff8d6", "pse"), "plaque": ("#ffffff", "plaque"), "enduit": ("#f3efe8", None),
    "pvc": ("#ffffff", None), "alu": ("#c9d3dc", None), "bois": ("#e7c79a", "bois"), "verre": ("#d7eef7", "verre"),
    "mousse": ("#f0a35e", None), "mastic": ("#222222", None), "membrane": ("#2c6fb0", None), "chape": ("#e4e0d8", "chape"),
    "revet": ("#9a8f86", None), "terrain": ("#c8b48c", None), "coffre": ("#f7f7f7", None), "air": ("#ffffff", None), "lame": ("#9fb1c1", None),
}

PROFIL = {"pvc": {"D": 70, "Fd": 58, "Fo": 72, "vit": "4/20/4"}, "alu": {"D": 70, "Fd": 48, "Fo": 58, "vit": "4/20/4"},
          "bois": {"D": 68, "Fd": 56, "Fo": 70, "vit": "4/20/4"}}


@dataclass
class Shape:
    kind: str                 # rect | poly | line | circle | text
    pts: list
    mat: str | None = None
    lw: float = 0.6
    dash: list | None = None
    key: str | None = None    # libellé de légende
    color: str = "#1d1d1d"
    anchor: tuple | None = None
    text: str = ""
    z: int = 0


@dataclass
class View:
    shapes: list = field(default_factory=list)
    dims: list = field(default_factory=list)      # (x0, y0, x1, y1, offset, texte)  — cote alignée
    breaks: list = field(default_factory=list)    # zones coupées : (axe, debut, fin)
    labels: list = field(default_factory=list)    # libellés « intérieur / extérieur » : (x, y, texte)

    def rect(self, x0, x1, y0, y1, mat, key=None, lw=0.6, z=0, anchor=None, dash=None):
        if x1 - x0 <= 0 or y1 - y0 <= 0:
            return None
        s = Shape("rect", [(x0, y0), (x1, y0), (x1, y1), (x0, y1)], mat, lw, dash, key,
                  anchor=anchor or ((x0 + x1) / 2, (y0 + y1) / 2), z=z)
        self.shapes.append(s)
        return s

    def poly(self, pts, mat, key=None, lw=0.6, z=0, anchor=None):
        xs, ys = zip(*pts)
        s = Shape("poly", list(pts), mat, lw, None, key, anchor=anchor or (sum(xs) / len(xs), sum(ys) / len(ys)), z=z)
        self.shapes.append(s)
        return s

    def line(self, pts, lw=0.6, color="#1d1d1d", dash=None, key=None, z=5, anchor=None):
        s = Shape("line", list(pts), None, lw, dash, key, color=color, anchor=anchor or pts[len(pts) // 2], z=z)
        self.shapes.append(s)
        return s

    def circle(self, cx, cy, r, mat, key=None, z=3, lw=0.6):
        s = Shape("circle", [(cx, cy), r], mat, lw, None, key, anchor=(cx + r * 0.6, cy + r * 0.6), z=z)
        self.shapes.append(s)
        return s


# ----------------------------------------------------------------------------------------------------------------- paramètres
DEFAULTS = {"ouvrage": "porte_fenetre", "pose": "applique_int", "coffre": "monobloc", "isolation": "iti", "materiau": "pvc", "mur": "parpaing",
            "mur_ep_mm": 200, "isolant_ep_mm": 100, "isolant_ext_ep_mm": 140, "hauteur_mm": None, "largeur_mm": None, "allege_mm": 950,
            "linteau_h_mm": 200, "dalle_ep_mm": 200, "hauteur_coffre_mm": None, "seuil_pmr": True, "lang": "fr"}


def _clean(p: dict) -> tuple[dict, list]:
    p = dict(p or {})
    defaulted = []
    out = {}
    for k, v in DEFAULTS.items():
        val = p.get(k)
        if val is None or val == "":
            out[k] = v
            if k not in ("lang", "hauteur_coffre_mm") and v is not None:
                defaulted.append(k)
        else:
            out[k] = val
    for k, allowed in (("ouvrage", OUVRAGES), ("pose", POSES), ("coffre", COFFRES), ("isolation", ISOLATIONS), ("materiau", MATERIAUX), ("mur", MURS)):
        if out[k] not in allowed:
            raise ValueError(f"{k} inconnu : {out[k]!r} (valeurs : {', '.join(allowed)})")
    if out["lang"] not in T:
        out["lang"] = "fr"
    if out["pose"] not in COFFRE_POSES[out["coffre"]]:
        raise ValueError(f"coffre {out['coffre']} incompatible avec la pose {out['pose']} "
                         f"(poses possibles : {', '.join(COFFRE_POSES[out['coffre']])}) : précisez la pose ou le type de coffre")
    if out["pose"] == "applique_ext" and out["isolation"] != "ite":
        raise ValueError("la pose en applique extérieure suppose une isolation par l'extérieur (ITE) : précisez l'isolation ou la pose")
    if out["materiau"] == "pvc" and out["ouvrage"] == "coulissant":
        pass
    if out["hauteur_mm"] is None:
        out["hauteur_mm"] = {"fenetre": 1350, "porte_fenetre": 2150, "coulissant": 2150}[out["ouvrage"]]
        defaulted.append("hauteur_mm")
    if out["largeur_mm"] is None:
        out["largeur_mm"] = {"fenetre": 1200, "porte_fenetre": 1400, "coulissant": 2400}[out["ouvrage"]]
        defaulted.append("largeur_mm")
    for k in ("mur_ep_mm", "isolant_ep_mm", "isolant_ext_ep_mm", "hauteur_mm", "largeur_mm", "allege_mm", "linteau_h_mm", "dalle_ep_mm"):
        out[k] = float(out[k])
        if not (0 < out[k] < 10000):
            raise ValueError(f"{k} hors limites : {out[k]}")
    if not 100 <= out["mur_ep_mm"] <= 800:
        raise ValueError("épaisseur de mur entre 100 et 800 mm")
    if out["ouvrage"] == "porte_fenetre" or out["ouvrage"] == "coulissant":
        out["allege_mm"] = 0.0
        if "allege_mm" in defaulted:
            defaulted.remove("allege_mm")
    if out["coffre"] == "aucun":
        defaulted = [d for d in defaulted if d != "hauteur_coffre_mm"]
    if out["isolation"] != "iti" and "isolant_ep_mm" in defaulted:
        defaulted.remove("isolant_ep_mm")
    if out["isolation"] != "ite" and "isolant_ext_ep_mm" in defaulted:
        defaulted.remove("isolant_ext_ep_mm")
    return out, defaulted


def roll_diameter(h_mm: float, lame_ep=9.0, axe=40.0) -> float:
    """Ø extérieur du tablier enroulé : aire de la spirale = hauteur × épaisseur de lame autour d'un axe Ø40."""
    return math.sqrt(4 * (h_mm + 150) * lame_ep / math.pi + axe ** 2)


# ----------------------------------------------------------------------------------------------------------------- géométrie
class Detail:
    def __init__(self, params: dict):
        self.p, self.defaulted = _clean(params)
        p = self.p
        self.L = T[p["lang"]]
        self.W = p["mur_ep_mm"]
        pr = PROFIL[p["materiau"]]
        self.D = 110.0 if p["ouvrage"] == "coulissant" else float(pr["D"])
        self.Fd, self.Fo, self.vit = float(pr["Fd"]), float(pr["Fo"]), pr["vit"]
        iso = p["isolation"]
        self.t_int = p["isolant_ep_mm"] + 13 if iso == "iti" else 10.0
        self.t_ext = p["isolant_ext_ep_mm"] + 10 if iso == "ite" else 15.0
        self.u_int, self.u_ext = -self.t_int, self.W + self.t_ext
        self.rec = 35.0          # recouvrement du dormant en applique
        self.jeu = 10.0
        self.feu, self.nez = 50.0, 60.0
        vr = p["coffre"] != "aucun"
        self.vr = vr
        self.roll = roll_diameter(p["hauteur_mm"]) if vr else 0.0
        hc = p.get("hauteur_coffre_mm")
        self.Hc = float(hc) if hc else (max(165.0, math.ceil((self.roll + 40) / 5) * 5) if vr else 0.0)
        # position du dormant dans l'épaisseur
        pose = p["pose"]
        if pose == "applique_int":
            self.ud0, self.ud1 = -self.D - 8, -8.0
        elif pose == "tunnel":
            u0 = max(30.0, round(self.W * 0.3 / 5) * 5)
            u0 = min(u0, self.W - self.D - 30) if self.W - self.D - 30 > 0 else 0.0
            self.ud0, self.ud1 = u0, u0 + self.D
        elif pose == "feuillure":
            self.ud1 = self.W - self.nez
            self.ud0 = self.ud1 - self.D
        elif pose == "renovation":
            self.ue0 = max(20.0, round(self.W * 0.3 / 5) * 5)
            self.ue1 = self.ue0 + 56
            self.ud0, self.ud1 = self.ue0 - 12, self.ue0 - 12 + self.D
        else:   # applique_ext : dans le plan de l'ITE, posée sur la face extérieure du mur
            self.ud0, self.ud1 = self.W + 8, self.W + 8 + self.D
        # coulisses de volet roulant
        if p["coffre"] == "exterieur":
            self.uc0, self.uc1 = self.u_ext + 2, self.u_ext + 32
        elif vr:
            self.uc0, self.uc1 = self.ud1 + 6, self.ud1 + 36
        self.notes = []

    # ------------------------------------------------------------------ jambage générique en (u = profondeur, v = vers le jour)
    def jamb(self, V: View, M, vmax, head=False):
        """Éléments d'un tableau (jambage en plan ou tête en coupe). M(u, v) -> (x, y). v < 0 : dans la maçonnerie ; v > 0 : dans le jour."""
        p, L, e = self.p, self.L, self.L["e"]
        W, ui, ue = self.W, self.u_int, self.u_ext
        pose = p["pose"]
        vb = -260.0       # profondeur de mur représentée
        R = lambda u0, u1, v0, v1, mat, key=None, z=0, lw=0.6: self._r(V, M, u0, u1, v0, v1, mat, key, z, lw)
        mur_key = None if head else e["mur"].format(mur=L["mur"][p["mur"]], ep=int(W))
        # maçonnerie (+ feuillure)
        if pose == "feuillure":
            R(0, W - self.nez, vb, -self.feu, p["mur"], mur_key)
            R(W - self.nez, W, vb, 0, p["mur"], mur_key)
        else:
            R(0, W, vb, 0, p["mur"], mur_key)
        v_tab = -self.feu if pose == "feuillure" else 0.0     # face du tableau côté intérieur
        # côté intérieur
        if p["isolation"] == "iti":
            ep = p["isolant_ep_mm"]
            v_stop = -self.rec if pose in ("applique_int",) else v_tab
            R(-ep, 0, vb, v_stop, "isolant", e["isolant_int"].format(ep=int(ep)))
            R(ui, -ep, vb, v_stop, "plaque", e["plaque"])
            if pose != "applique_int":   # retour d'isolant + plaque en tableau jusqu'au dormant
                R(ui, self.ud0 - 1, v_tab, v_tab + 20, "isolant", e["retour_iso"])
                R(ui, self.ud0 - 1, v_tab + 20, v_tab + 33, "plaque")
        else:
            v_stop = -self.rec if pose == "applique_int" else v_tab
            R(ui, 0, vb, v_stop, "enduit", e["enduit_int"])
            if pose != "applique_int":
                R(0, self.ud0 - 1, v_tab, v_tab + 10, "enduit")
        # côté extérieur
        if p["isolation"] == "ite":
            ep = p["isolant_ext_ep_mm"]
            if pose == "applique_ext":
                R(W, W + ep, vb, self.Fd - 12, "pse", e["isolant_ext"].format(ep=int(ep)))
                R(W + ep, ue, vb, self.Fd - 12, "enduit", e["enduit_ext"])
            else:
                R(W, W + ep, vb, 0, "pse", e["isolant_ext"].format(ep=int(ep)))
                R(W + ep, ue, vb, 0, "enduit", e["enduit_ext"])
                ur = self.ud1 + 2 if pose in ("tunnel", "renovation") else W - (self.nez if pose == "feuillure" else 0)
                R(max(ur, self.uc1 + 2 if self.vr and p["coffre"] != "exterieur" else ur), ue, 0, 30, "pse", e["retour_iso"])
                R(max(ur, self.uc1 + 2 if self.vr and p["coffre"] != "exterieur" else ur), ue, 30, 38, "enduit")
        else:
            R(W, ue, vb, 0, "enduit", e["enduit_ext"])
            if pose not in ("applique_ext",):
                u_from = self.uc1 + 2 if (self.vr and p["coffre"] != "exterieur") else (self.ud1 + 2 if pose in ("tunnel", "renovation", "feuillure") else 0)
                R(max(u_from, 0), ue, 0, 10, "enduit")
        # ancien dormant (rénovation)
        if pose == "renovation":
            R(self.ue0, self.ue1, self.jeu, self.jeu + 64, "bois", e["ancien_dormant"])
        # dormant + tapée
        mat = p["materiau"]
        if pose == "applique_int":
            dv0 = -self.rec
        elif pose == "feuillure":
            dv0 = -self.feu + self.jeu
        elif pose == "renovation":
            dv0 = self.jeu + 64 - 22
        elif pose == "applique_ext":
            dv0 = -self.rec
        else:
            dv0 = self.jeu
        self.dv0 = dv0
        R(self.ud0, self.ud1, dv0, dv0 + self.Fd, mat, e["dormant"].format(mat=L["mat"][mat], d=int(self.D)), z=2, lw=0.9)
        if pose == "applique_int" and self.ud0 - ui > 6:
            R(ui, self.ud0, dv0, dv0 + self.Fd, mat, e["tapee"].format(d=int(self.ud0 - ui)), z=2)
        if pose == "renovation":
            R(self.ud0 - 3, self.ud0, self.jeu + 5, dv0 + self.Fd, "alu", e["aile"], z=3)
            R(self.ue1, self.ue1 + 2, self.jeu - 3, self.jeu + 64, "alu", e["cornière"], z=3)
        # joints : mousse imprégnée (côté maçonnerie) + mastic extérieur + membrane intérieure
        if pose in ("applique_int",):
            R(-8, 0, -self.rec, -4, "mousse", e["joint_mousse"], z=3)
            R(0, 6, -6, 0, "mastic", e["mastic"], z=4)
            V.line([M(ui + 3, dv0 - 3), M(-10, dv0 - 3)], lw=1.6, color=STYLE["membrane"][0], key=e["membrane"])
        elif pose == "applique_ext":
            R(W, W + 8, -self.rec, -4, "mousse", e["joint_mousse"], z=3)
            V.line([M(W - 2, -4), M(W - 2, dv0 + self.Fd)], lw=1.6, color=STYLE["membrane"][0], key=e["membrane"])
        elif pose == "renovation":
            R(self.ue0 + 4, self.ue1 - 4, self.jeu + 64, dv0 + 2, "mousse", e["joint_mousse"], z=3)
        else:
            vj0 = v_tab
            R(self.ud0 + 8, self.ud1 - 8, vj0, dv0, "mousse", e["joint_mousse"], z=3)
            R(self.ud1 - 8, self.ud1, vj0, dv0, "mastic", e["mastic"], z=4)
            V.line([M(self.ud0 - 1, vj0 + 1), M(self.ud0 - 1, dv0 + 12)], lw=1.6, color=STYLE["membrane"][0], key=e["membrane"])
        # ouvrant(s) + vitrage
        self._sash(V, M, dv0, vmax, mat)
        # coulisse du volet roulant
        if self.vr and not head:
            if p["coffre"] == "exterieur":
                R(self.uc0, self.uc1, -48, 14, "alu", e["coulisse"], z=3, lw=0.8)
            else:
                base = 0.0 if p["isolation"] != "ite" or pose == "applique_ext" else 0.0
                if p["coffre"] == "monobloc":   # coulisses solidaires du dormant
                    R(self.uc0, self.uc1, 2, 54, "alu", e["coulisse"], z=3, lw=0.8)
                else:
                    R(self.uc0, self.uc1, base + (10 if p["isolation"] != "ite" else 0), base + 62, "alu", e["coulisse"], z=3, lw=0.8)
            uc = (self.uc0 + self.uc1) / 2
            vs = 12 if p["coffre"] == "monobloc" else (-30 if p["coffre"] == "exterieur" else 28)
            V.line([M(uc, vs), M(uc, vmax)], lw=1.3, color="#4d6a85", dash=[3, 2], key=e["tablier_ferme"])

    def _sash(self, V, M, dv0, vmax, mat):
        e, L = self.L["e"], self.L
        R = lambda u0, u1, v0, v1, m, key=None, z=0, lw=0.6: self._r(V, M, u0, u1, v0, v1, m, key, z, lw)
        if self.p["ouvrage"] == "coulissant":
            for k, (a, b) in enumerate(((self.ud0 + 12, self.ud0 + 48), (self.ud0 + 60, self.ud0 + 96))):
                v0 = dv0 + 14 + 10 * k
                R(a, b, v0, v0 + self.Fo, mat, e["ouvrant"].format(mat=L["mat"][mat]) if k == 0 else None, z=4, lw=0.9)
                c = (a + b) / 2
                self._glass(V, M, c, v0 + self.Fo - 18, vmax, z=3, key=k == 0)
            return
        a, b = self.ud0 - 8, self.ud1 - 2      # l'ouvrant recouvre le dormant côté intérieur
        v0 = dv0 + self.Fd - 16
        R(a, b, v0, v0 + self.Fo, mat, e["ouvrant"].format(mat=L["mat"][mat]), z=4, lw=0.9)
        c = (a + b) / 2 + 4
        self._glass(V, M, c, v0 + self.Fo - 20, vmax, z=3, key=True)
        R(a + 4, c - 16, v0 + self.Fo - 2, v0 + self.Fo + 16, mat, e["parclose"], z=5)

    def _glass(self, V, M, c, v0, vmax, z=3, key=True):
        e = self.L["e"]
        g = 4.0
        R = lambda u0, u1, a, b, m, k=None: self._r(V, M, u0, u1, a, b, m, k, z, 0.5)
        R(c - 14, c - 14 + g, v0, vmax, "verre", e["vitrage"].format(v=self.vit) if key else None)
        R(c + 14 - g, c + 14, v0, vmax, "verre")
        R(c - 10, c + 10, v0, v0 + 12, "alu")       # intercalaire

    def _r(self, V, M, u0, u1, v0, v1, mat, key, z, lw):
        a, b = M(u0, v0), M(u1, v1)
        return V.rect(min(a[0], b[0]), max(a[0], b[0]), min(a[1], b[1]), max(a[1], b[1]), mat, key, lw, z)

    # ------------------------------------------------------------------ coupe horizontale
    def plan(self) -> View:
        V = View()
        vmax = 330.0
        M = lambda u, v: (v, u)          # x = vers le jour, y = profondeur (extérieur en haut)
        self.jamb(V, M, vmax)
        V.breaks.append(("x", vmax - 40, vmax))
        L = self.L
        V.labels += [(-250, self.u_int - 60, L["int"]), (-250, self.u_ext + 40, L["ext"])]
        # cotes : épaisseurs (à gauche) et recouvrement / jeu (en bas)
        xs = -300
        chain = [self.u_int, 0, self.W, self.u_ext]
        if self.p["isolation"] == "iti":
            chain.insert(1, -self.p["isolant_ep_mm"])
        if self.p["isolation"] == "ite":
            chain.insert(-1, self.W + self.p["isolant_ext_ep_mm"])
        for a, b in zip(chain, chain[1:]):
            V.dims.append(("v", xs, a, b, f"{b - a:g}"))
        V.dims.append(("v", xs - 70, self.u_int, self.u_ext, f"{self.u_ext - self.u_int:g}"))
        V.dims.append(("v", 260, self.ud0, self.ud1, f"{self.ud1 - self.ud0:g}"))
        if self.p["pose"] == "applique_int":
            V.dims.append(("h", self.u_int - 70, -self.rec, 0, f"{self.rec:g}"))
        elif self.p["pose"] in ("tunnel", "feuillure"):
            V.dims.append(("h", self.u_int - 70, self.dv0 - self.jeu, self.dv0, f"{self.jeu:g}"))
        return V

    # ------------------------------------------------------------------ coupe verticale
    def vertical(self) -> View:
        p, L, e = self.p, self.L, self.L["e"]
        V = View()
        W, ui, ue = self.W, self.u_int, self.u_ext
        FF = 80.0                                  # sol fini intérieur (dalle brute à 0)
        R = lambda u0, u1, y0, y1, mat, key=None, z=0, lw=0.6: V.rect(u0, u1, y0, y1, mat, key, lw, z)
        de = p["dalle_ep_mm"]
        x_in, x_out = ui - 320, ue + 260
        if p["ouvrage"] == "fenetre":
            yap = FF + p["allege_mm"]              # dessus d'appui à l'arrière (rejingot)
            ya = yap - 60                           # arase de l'allège
            R(x_in, W, -de, 0, "beton", e["dalle"].format(ep=int(de)))
            R(x_in, ui, 0, FF - 10, "chape", e["chape"])
            R(x_in, ui, FF - 10, FF, "revet", e["revet"])
            R(0, W, 0, ya, p["mur"], e["allege"].format(mur=L["mur"][p["mur"]]))
            pose = p["pose"]
            if pose == "applique_int":
                ydb = yap - self.rec
                t_top, u_t1 = ydb + self.rec, self.ud0
            elif pose == "renovation":
                R(self.ue0, self.ue1, yap, yap + 64, "bois", z=2)
                R(self.ue0 + 4, self.ue1 - 4, yap + 64, yap + 66, "mousse", z=3)
                ydb = yap + 66
                t_top, u_t1 = ydb + 22, self.ud0
            else:
                ydb = yap + 5
                t_top, u_t1 = ydb + 22, self.ud0
            self.t_top = t_top
            # doublage / enduit intérieur jusqu'à la tablette
            if p["isolation"] == "iti":
                R(-p["isolant_ep_mm"], 0, FF, t_top - 22, "isolant")
                R(ui, -p["isolant_ep_mm"], FF, t_top - 22, "plaque")
            else:
                R(ui, 0, FF, t_top - 22, "enduit")
            if p["isolation"] == "ite":
                R(W, W + p["isolant_ext_ep_mm"], -de, ya + (ydb - ya - 3 if pose == "applique_ext" else 0), "pse")
                R(W + p["isolant_ext_ep_mm"], ue, -de, ya - 20 if pose != "applique_ext" else ydb - 30, "enduit")
            else:
                R(W, ue, -de, ya - 20, "enduit")
            nose = ue + 40
            if pose == "applique_ext":
                V.poly([(self.ud1, ydb + 2), (ue + 45, ydb - 22), (ue + 45, ydb - 40), (ue + 42, ydb - 40), (ue + 42, ydb - 25), (self.ud1, ydb - 1)],
                       "alu", e["bavette"], z=4)
                R(self.ud0, self.ud1, ya, ydb, "pse")
                R(0, W, ya, t_top - 22, p["mur"])
            else:
                if pose == "applique_int":
                    u0 = 0.0
                    pts = [(0, ya), (nose, ya), (nose, ya + 40), (30, yap - 20), (30, yap), (0, yap)]
                else:
                    u0 = self.ud0 - 5
                    st = self.ud1 - 5 if pose != "renovation" else self.ue1
                    pts = [(u0, ya), (nose, ya), (nose, ya + 40), (st, yap - 20), (st, yap), (u0, yap)]
                    R(0, u0, ya, t_top - 22, p["mur"])
                V.poly(pts, "beton", e["appui"], z=1)
                V.poly([(ue + 14, ya), (ue + 22, ya), (ue + 22, ya + 8), (ue + 14, ya + 8)], "air", z=2)     # larmier
                if pose not in ("applique_int", "renovation"):
                    R(self.ud0 + 10, self.ud0 + 30, yap, ydb, "pvc", e["cale"], z=2)
            # tablette intérieure
            R(ui - 25, u_t1, t_top - 22, t_top, "bois", e["tablette"], z=2)
        else:
            ydb = FF - 25
            R(x_in, x_out, -de, 0, "beton", e["dalle"].format(ep=int(de)))
            R(x_in, self.ud0, 0, FF - 10, "chape", e["chape"])
            R(x_in, self.ud0, FF - 10, FF, "revet", e["revet"])
            R(self.ud0, self.ud1 + 28, 0, ydb, "mortier" if False else "chape", e["cale"], z=1)
            # seuil alu à rupture
            V.poly([(self.ud0, ydb), (self.ud1 + 28, ydb), (self.ud1 + 28, ydb + 8), (self.ud1, FF + 2), (self.ud1, FF + 15),
                    (self.ud0, FF + 15)], "alu", e["seuil"], z=3, lw=0.9)
            R(self.ud0 + 25, self.ud0 + 31, ydb + 4, FF + 10, "pvc", z=4)    # barrette de rupture
            yx = FF - 5
            u_s1 = ue + 30
            V.poly([(self.ud1 + 28, 0), (u_s1, 0), (u_s1, yx), (self.ud1 + 28, FF + 2)], "beton", e["seuil_ext"], z=1)
            if p["seuil_pmr"]:
                R(u_s1, u_s1 + 130, 0, yx - 70, "chape")
                V.poly([(u_s1, yx - 70), (u_s1 + 130, yx - 70), (u_s1 + 130, yx - 8), (u_s1 + 127, yx - 8), (u_s1 + 127, yx - 67),
                        (u_s1 + 3, yx - 67), (u_s1 + 3, yx - 8), (u_s1, yx - 8)], "alu", e["caniveau"], z=2)
                for k in range(6):
                    R(u_s1 + 5 + k * 21, u_s1 + 15 + k * 21, yx - 8, yx, "alu", z=3)
                R(u_s1 + 130, x_out, 0, yx - 12, "chape")
                R(u_s1 + 130, x_out, yx - 12, yx, "revet", e["sol_ext"])
            else:
                R(u_s1, x_out, 0, yx - 32, "chape")
                R(u_s1, x_out, yx - 32, yx - 20, "revet", e["sol_ext"])
            if p["isolation"] == "ite":
                R(W, W + p["isolant_ext_ep_mm"], -de - 80, -de, "pse")
        self.ydb = ydb
        # ----- menuiserie : bas
        Mb = lambda u, v: (u, ydb + v)
        hm = p["hauteur_mm"]
        yt = ydb + hm
        self._bottom_rail(V, ydb, yt)
        # ----- tête
        coffre, pose = p["coffre"], p["pose"]
        if coffre in ("monobloc", "tunnel", "interieur"):
            c0 = yt
            c1 = yt + self.Hc
            hb = c1 + self.jeu
            if coffre == "monobloc" and pose == "applique_ext":      # coffre dans le plan de l'ITE, devant le linteau
                hb = yt - self.rec
        else:
            hb = yt - self.rec if pose in ("applique_int", "applique_ext") else yt + self.jeu
            if pose == "feuillure":
                hb = yt + self.jeu - self.feu
            if pose == "renovation":
                hb = yt + self.jeu + 64 - 22 + 0
        self.hb = hb
        lh = p["linteau_h_mm"]
        hs = hb + lh
        # maçonnerie de tête (linteau + dalle + mur au-dessus)
        if pose == "feuillure" and coffre not in ("monobloc", "tunnel", "interieur"):
            R(0, W - self.nez, hb + self.feu, hs, "beton", e["linteau"].format(h=int(lh)))
            R(W - self.nez, W, hb, hs, "beton")
        else:
            R(0, W, hb, hs, "beton", e["linteau"].format(h=int(lh)))
        slab_out = W if p["isolation"] == "ite" else W - 50
        R(x_in, slab_out, hs, hs + de, "beton", e["dalle"].format(ep=int(de)))
        if slab_out < W:
            R(slab_out, W, hs, hs + de, "brique", e["planelle"])
        R(0, W, hs + de, hs + de + 120, p["mur"])
        R(x_in, ui, hs - 13, hs, "plaque", e["plafond"])
        top = hs + de + 120
        ite_mono = coffre == "monobloc" and pose == "applique_ext"
        if p["isolation"] == "ite":
            y_ite = yt + self.Hc + 5 if ite_mono else (hb if pose != "applique_ext" else yt - self.rec)
            R(W, W + p["isolant_ext_ep_mm"], y_ite, top, "pse")
            R(W + p["isolant_ext_ep_mm"], ue, y_ite, top, "enduit")
        else:
            R(W, ue, hb, top, "enduit")
        # head jamb mapping: v = hb - y  (v>0 vers le bas, dans le jour)
        if coffre in ("monobloc", "tunnel", "interieur"):
            self._coffre_in(V, yt, hb, hs)
        else:
            Mh = lambda u, v: (u, hb - v)
            self._head_simple(V, Mh, yt, hb, hs)
            if coffre == "exterieur":
                self._coffre_ext(V, yt, hb)
        # partie courante coupée
        y_cut0, y_cut1 = ydb + 260, yt - 220
        if p["ouvrage"] == "fenetre" and ya - 220 - (FF + 120) > 120:      # allège courante coupée aussi
            V.breaks.append(("y", FF + 120, ya - 220))
        if y_cut1 - y_cut0 > 120:
            V.breaks.append(("y", y_cut0, y_cut1))
        V.labels += [(x_in + 10, top - 60, L["int"]), (ue + 60, top - 60, L["ext"])]
        # cotes
        xd = x_out + 70
        V.dims.append(("v", xd, ydb, yt, f"{hm:g}"))
        if self.Hc and coffre != "exterieur":
            V.dims.append(("v", xd, yt, yt + self.Hc, f"{self.Hc:g}"))
        V.dims.append(("v", xd + 90, ydb if p["ouvrage"] != "fenetre" else ya, hb, f"{hb - (0 if p['ouvrage'] != 'fenetre' else ya):g}"))
        if p["ouvrage"] == "fenetre":
            V.dims.append(("v", x_in - 60, FF, yap, f"{yap - FF:g}"))
        else:
            V.dims.append(("v", x_in - 60, FF, FF + 15, "15"))
        chain = [ui, 0, W, ue]
        for a, b in zip(chain, chain[1:]):
            V.dims.append(("h", top + 60, a, b, f"{b - a:g}"))
        self.res_h = hb - (0 if p["ouvrage"] != "fenetre" else ya)
        self.yap = yap if p["ouvrage"] == "fenetre" else None
        self.top, self.x_in, self.x_out = top, x_in, x_out
        return V

    def _bottom_rail(self, V, ydb, yt):
        """Traverse basse du dormant + ouvrant + vitrage (coupés plus haut par le trait de coupure)."""
        p, e, L = self.p, self.L["e"], self.L
        mat = p["materiau"]
        is_pf = p["ouvrage"] != "fenetre"
        Mb = lambda u, v: (u, ydb + v)
        top = yt  # vitrage monte jusqu'en tête
        if not is_pf:
            self._r(V, Mb, self.ud0, self.ud1, 0, self.Fd, mat, None, 2, 0.9)
            if p["pose"] == "applique_int" and self.ud0 - self.u_int > 6:
                self._r(V, Mb, self.u_int, self.ud0, self.rec, self.Fd, mat, None, 2, 0.6)
            dv0 = 0.0
        else:
            dv0 = (80 + 15) - ydb - self.Fd + 6       # l'ouvrant démarre au-dessus du seuil
        if p["ouvrage"] == "coulissant":
            for k, (a, b) in enumerate(((self.ud0 + 12, self.ud0 + 48), (self.ud0 + 60, self.ud0 + 96))):
                v0 = dv0 + self.Fd + 2
                self._r(V, Mb, a, b, v0, v0 + self.Fo, mat, None, 4, 0.9)
                c = (a + b) / 2
                self._r(V, Mb, c - 14, c - 10, v0 + self.Fo - 18, top - ydb - 90, "verre", None, 3, 0.5)
                self._r(V, Mb, c + 10, c + 14, v0 + self.Fo - 18, top - ydb - 90, "verre", None, 3, 0.5)
            return
        a, b = self.ud0 - 8, self.ud1 - 2
        v0 = dv0 + self.Fd - 16
        self._r(V, Mb, a, b, v0, v0 + self.Fo, mat, None, 4, 0.9)
        c = (a + b) / 2 + 4
        self._r(V, Mb, c - 14, c - 10, v0 + self.Fo - 20, top - ydb - 100, "verre", None, 3, 0.5)
        self._r(V, Mb, c + 10, c + 14, v0 + self.Fo - 20, top - ydb - 100, "verre", None, 3, 0.5)
        self._r(V, Mb, c - 10, c + 10, v0 + self.Fo - 20, v0 + self.Fo - 8, "alu", None, 3, 0.5)
        self._r(V, Mb, a + 4, c - 16, v0 + self.Fo - 2, v0 + self.Fo + 16, mat, None, 5, 0.6)
        if self.vr and p["coffre"] != "exterieur":     # lame finale en position basse ? non : volet ouvert -> coulisse vue en coupe
            pass

    def _head_simple(self, V, Mh, yt, hb, hs):
        """Tête sans coffre intégré : linteau, dormant haut, ouvrant, vitrage (le vitrage descend vers la coupure)."""
        vmax = hb - (yt - 230) if False else (hb - (self.ydb + 300))
        self.jamb_head(V, Mh, vmax)

    def jamb_head(self, V, Mh, vmax):
        """Réutilise le jambage pour la tête, sans les couches déjà dessinées (linteau, isolants) ; seulement menuiserie et joints."""
        tmp = View()
        self.jamb(tmp, Mh, vmax, head=True)
        keep_mats = {"pvc", "alu", "bois", "verre", "mousse", "mastic", "isolant", "plaque", "pse", "enduit"}
        for s in tmp.shapes:
            if s.kind == "line" or s.mat in keep_mats:
                y0 = min(pt[1] for pt in s.pts) if s.kind != "circle" else 0
                if s.kind == "rect" and s.mat in ("isolant", "plaque", "pse", "enduit") and max(pt[1] for pt in s.pts) > self.hb + 1:
                    # doublage / ITE au-dessus du jour : redessiné ici jusqu'au plafond
                    pass
                V.shapes.append(s)
        p = self.p
        if p["isolation"] == "iti":
            hs = self.hb + p["linteau_h_mm"]
            y_from = self.hb + (self.rec if p["pose"] == "applique_int" else 0)
            if p["pose"] == "applique_int":
                y_from = self.hb + self.rec
            V.rect(-p["isolant_ep_mm"], 0, y_from, hs - 13, "isolant")
            V.rect(self.u_int, -p["isolant_ep_mm"], y_from, hs - 13, "plaque")

    def _coffre_in(self, V, yt, hb, hs):
        """Coffre monobloc / tunnel / intérieur posé sur la traverse haute du dormant."""
        p, e = self.p, self.L["e"]
        coffre, pose = p["coffre"], p["pose"]
        W, ui = self.W, self.u_int
        Hc = self.Hc
        c0, c1 = yt, yt + Hc
        mat = p["materiau"]
        # traverse haute du dormant + ouvrant + vitrage
        Mh = lambda u, v: (u, yt - v)
        self._r(V, Mh, self.ud0, self.ud1, 0, self.Fd, mat, None, 2, 0.9)
        if pose == "applique_int" and self.ud0 - ui > 6:
            self._r(V, Mh, ui, self.ud0, 0, self.Fd, mat, None, 2, 0.6)
        a, b = self.ud0 - 8, self.ud1 - 2
        v0 = self.Fd - 16
        self._r(V, Mh, a, b, v0, v0 + self.Fo, mat, None, 4, 0.9)
        c = (a + b) / 2 + 4
        vmax = yt - (self.ydb + 300)
        if p["ouvrage"] == "coulissant":
            for k, (aa, bb) in enumerate(((self.ud0 + 12, self.ud0 + 48), (self.ud0 + 60, self.ud0 + 96))):
                vv = 14 + 10 * k
                self._r(V, Mh, aa, bb, vv, vv + self.Fo, mat, None, 4, 0.9)
                cc = (aa + bb) / 2
                self._r(V, Mh, cc - 14, cc - 10, vv + self.Fo - 18, vmax, "verre", None, 3, 0.5)
                self._r(V, Mh, cc + 10, cc + 14, vv + self.Fo - 18, vmax, "verre", None, 3, 0.5)
        else:
            self._r(V, Mh, c - 14, c - 10, v0 + self.Fo - 20, vmax, "verre", None, 3, 0.5)
            self._r(V, Mh, c + 10, c + 14, v0 + self.Fo - 20, vmax, "verre", None, 3, 0.5)
            self._r(V, Mh, c - 10, c + 10, v0 + self.Fo - 20, v0 + self.Fo - 8, "alu", None, 3, 0.5)
        # caisson
        uc = (self.uc0 + self.uc1) / 2
        r = self.roll / 2
        ite_mono = coffre == "monobloc" and pose == "applique_ext"
        if ite_mono:
            u0 = W + 4
            u1 = max(self.u_ext, uc + 2 * r + 25)
            key = e["coffre_mono"].format(h=int(Hc))
        elif coffre == "monobloc":
            u0, u1 = min(ui, uc - 2 * r - 30), W
            key = e["coffre_mono"].format(h=int(Hc))
        elif coffre == "tunnel":
            u0, u1 = (0.0 if uc - 2 * r >= 20 else uc - 2 * r - 20), W
            key = e["coffre_tunnel"].format(h=int(Hc))
        else:
            u0, u1 = min(ui - 90, uc - 2 * r - 30), self.uc1 + 25
            key = e["coffre_int"].format(h=int(Hc))
        self.coffre_u0 = u0
        V.rect(u0, u1, c0, c1, "coffre", key, 1.1, 2)
        if coffre == "tunnel" and pose != "applique_int" and self.ud0 - ui > 10:     # sous-face : retour d'isolant jusqu'au dormant
            if p["isolation"] == "iti":
                V.rect(ui, self.ud0 - 1, c0 - 20, c0, "isolant", e["retour_iso"], 0.5, 2)
                V.rect(ui, self.ud0 - 1, c0 - 33, c0 - 20, "plaque", None, 0.5, 2)
            else:
                V.rect(ui, self.ud0 - 1, c0 - 10, c0, "enduit", None, 0.5, 2)
        # isolant intérieur du caisson (faces intérieure et dessus)
        V.rect(u0 + 3, u0 + 25, c0 + 3, c1 - 3, "pse", None, 0.4, 3)
        V.rect(u0 + 25, u1 - 3, c1 - 23, c1 - 3, "pse", None, 0.4, 3)
        # tablier enroulé : tangent à l'aplomb de la coulisse (côté extérieur du rouleau)
        cx = uc + r if ite_mono else uc - r
        cy = c0 + 14 + r if c0 + 14 + 2 * r < c1 - 25 else (c0 + c1 - 22) / 2
        V.circle(cx, cy, r, "lame", e["tablier"].format(d=int(round(self.roll))), z=4)
        V.circle(cx, cy, 20, "alu", None, z=5)
        V.line([(uc, cy), (uc, c0 - 2)], lw=1.6, color="#4d6a85", z=6)
        V.rect(uc - 9, uc + 9, c0 - 4, c0 + 8, "alu", e["lame_finale"], 0.6, 6)
        # trappe de visite (sous-face côté intérieur, ou face intérieure pour un coffre apparent)
        if ite_mono:
            V.rect(u1, u1 + 10, c0, c1 + 5, "enduit", e["enduit_ext"], 0.5, 3)
            V.line([(u1 - 1, c0 + 15), (u1 - 1, c1 - 15)], lw=2.2, color="#b5651d", key=e["trappe"], z=7)
        elif coffre == "interieur":
            V.line([(u0, c0 + 15), (u0, c1 - 15)], lw=2.2, color="#b5651d", key=e["trappe"], z=7)
        else:
            tv0 = ui + 5 if coffre == "monobloc" else 5.0
            V.line([(tv0, c0 + 1), (min(self.ud0 + 40, uc - 25), c0 + 1)], lw=2.2, color="#b5651d", key=e["trappe"], z=7)
        # coulisse vue en coupe (dans le jour, sous le coffre)
        V.rect(self.uc0, self.uc1, yt - 180, c0, "alu", e["coulisse"], 0.8, 3)
        V.rect(uc - 3, uc + 3, yt - 178, c0 - 2, "air", None, 0.3, 4)
        # habillage / jonction coffre – façade
        if coffre == "interieur" and u1 < W:
            V.rect(u1, W, c1 - 12, c1, "alu", e["habillage"], 0.6, 2)
        if p["isolation"] != "ite":
            V.rect(W, self.u_ext, c0, hb, "enduit", None, 0.5, 1)
        else:
            V.rect(W, W + p["isolant_ext_ep_mm"], c0 - 10, hb, "pse", None, 0.5, 1)
            V.rect(W + p["isolant_ext_ep_mm"], self.u_ext, c0 - 10, hb, "enduit", None, 0.5, 1)
        V.rect(max(u0, 0.0), W, c1, hb, "mousse", e["joint_mousse"], 0.4, 1)
        # doublage au-dessus du coffre (ITI)
        if p["isolation"] == "iti":
            ystart = c1 if coffre in ("monobloc", "interieur") else c0
            if coffre == "tunnel":
                V.rect(-p["isolant_ep_mm"], 0, c0, hs - 13, "isolant", e["isolant_int"].format(ep=int(p["isolant_ep_mm"])))
                V.rect(ui, -p["isolant_ep_mm"], c0, hs - 13, "plaque")
            else:
                V.rect(-p["isolant_ep_mm"], 0, ystart, hs - 13, "isolant", e["isolant_int"].format(ep=int(p["isolant_ep_mm"])))
                V.rect(ui, -p["isolant_ep_mm"], ystart, hs - 13, "plaque", e["plaque"])
        elif coffre == "tunnel":
            V.rect(ui, 0, c0, hs - 13, "enduit")
        if not ite_mono:
            V.line([(ui + 3, c1 + 2), (u0 + 40, c1 + 2)], lw=1.6, color=STYLE["membrane"][0], key=e["membrane"], z=6)

    def _coffre_ext(self, V, yt, hb):
        e = self.L["e"]
        Hc = self.Hc
        u0 = self.u_ext + 2
        u1 = u0 + Hc
        y0 = hb - 30
        V.rect(u0, u1, y0, y0 + Hc, "alu", e["coffre_ext"].format(h=int(Hc)), 1.1, 3)
        V.rect(u0 + 2, u1 - 2, y0 + 2, y0 + Hc - 2, "coffre", None, 0.3, 4)
        uc = (self.uc0 + self.uc1) / 2
        r = self.roll / 2
        cx, cy = u1 - r - 10, y0 + Hc / 2 + 4
        cx = min(cx, u1 - r - 6)
        V.circle(cx, cy, r, "lame", e["tablier"].format(d=int(round(self.roll))), z=5)
        V.circle(cx, cy, 20, "alu", None, z=6)
        V.line([(cx - r, cy), (uc, cy), (uc, y0 - 2)], lw=1.4, color="#4d6a85", z=6)
        V.rect(uc - 9, uc + 9, y0 - 6, y0 + 6, "alu", e["lame_finale"], 0.6, 7)
        V.rect(self.uc0, self.uc1, yt - 200, y0, "alu", e["coulisse"], 0.8, 3)
        V.line([(u1, y0 + 20), (u1, y0 + Hc - 20)], lw=2.2, color="#b5651d", key=e["trappe"], z=7)

    # ------------------------------------------------------------------ données de cartouche
    def key_values(self) -> list[tuple[str, str]]:
        p, k = self.p, self.L["k"]
        out = [(k["hm"], f"{p['hauteur_mm']:g} mm"), (k["lm"], f"{p['largeur_mm']:g} mm")]
        if self.vr:
            out += [(k["hc"], f"{self.Hc:g} mm"), (k["roll"], f"≈ {self.roll:.0f} mm")]
        lres = {"applique_int": p["largeur_mm"] - 2 * self.rec, "applique_ext": p["largeur_mm"] - 2 * self.rec,
                "tunnel": p["largeur_mm"] + 2 * self.jeu, "feuillure": p["largeur_mm"] - 2 * (self.feu - self.jeu),
                "renovation": p["largeur_mm"] + 2 * (self.jeu + 64 - 22)}[p["pose"]]
        out += [(k["hres"], f"{self.res_h:.0f} mm"), (k["lres"], f"{lres:.0f} mm")]
        if p["pose"] in ("applique_int", "applique_ext"):
            out.append((k["rec"], f"{self.rec:g} mm"))
        else:
            out.append((k["jeu"], f"{self.jeu:g} mm"))
        if p["ouvrage"] == "fenetre":
            out += [(k["allege"], f"{p['allege_mm']:g} mm"), (k["debord"], "40 mm")]
        else:
            out.append((k["ressaut"], "15 / 20 mm"))
        return out

    def notes_list(self) -> list[str]:
        p, n = self.p, self.L["notes"]
        out = []
        if self.defaulted:
            names = {"ouvrage": "ouvrage", "pose": "pose", "coffre": "coffre", "isolation": "isolation", "materiau": "matériau", "mur": "mur",
                     "mur_ep_mm": "ép. mur", "isolant_ep_mm": "ép. isolant int.", "isolant_ext_ep_mm": "ép. ITE", "hauteur_mm": "hauteur",
                     "largeur_mm": "largeur", "allege_mm": "allège", "linteau_h_mm": "linteau", "dalle_ep_mm": "dalle", "seuil_pmr": "seuil PMR"}
            out.append(n["defaults"].format(keys=", ".join(names.get(d, d) for d in self.defaulted)))
        if p["coffre"] == "monobloc":
            out.append(n["mono"])
        elif p["coffre"] == "tunnel":
            out.append(n["tunnel_coffre"])
        elif p["coffre"] == "interieur":
            out.append(n["interieur"])
        elif p["coffre"] == "exterieur":
            out.append(n["exterieur"])
        if p["ouvrage"] != "fenetre" and p["seuil_pmr"]:
            out.append(n["pmr"])
        if p["isolation"] == "ite":
            out.append(n["ite"])
        if p["pose"] == "renovation":
            out.append(n["reno"])
        out.append(n["dtu"])
        return out

    def title(self) -> str:
        p, L = self.p, self.L
        parts = [L["title"][p["ouvrage"]], L["vr"] if self.vr else L["sans_vr"]]
        sub = [L["pose"][p["pose"]]]
        if self.vr:
            sub.append(L["coffre"][p["coffre"]])
        sub += [L["mat"][p["materiau"]], L["iso"][p["isolation"]]]
        return " ".join(parts), " — ".join(sub)


# ----------------------------------------------------------------------------------------------------------------- rendu PDF
def _hex(c):
    from reportlab.lib.colors import HexColor
    return HexColor(c)


class _Page:
    """Rendu d'une vue dans un cadre de page : ajustement d'échelle normalisée, zones coupées, hachures, bulles et légende."""

    def __init__(self, cv, view: View, box, detail: Detail, flip_y=False):
        self.cv, self.V, self.d = cv, view, detail
        bx0, by0, bx1, by1 = box
        xs, ys = [], []
        for s in view.shapes:
            pts = s.pts if s.kind != "circle" else [(s.pts[0][0] - s.pts[1], s.pts[0][1] - s.pts[1]), (s.pts[0][0] + s.pts[1], s.pts[0][1] + s.pts[1])]
            xs += [q[0] for q in pts]
            ys += [q[1] for q in pts]
        for dm in view.dims:
            if dm[0] == "v":
                xs.append(dm[1]); ys += [dm[2], dm[3]]
            else:
                ys.append(dm[1]); xs += [dm[2], dm[3]]
        self.cuts = sorted([b for b in view.breaks], key=lambda b: b[1])
        self.x0m, self.x1m, self.y0m, self.y1m = min(xs) - 30, max(xs) + 60, min(ys) - 30, max(ys) + 40
        for ax, a, b in self.cuts:
            if ax == "x":
                self.x1m = min(self.x1m, a + 30)
        w_m = self._cx(self.x1m) - self._cx(self.x0m)
        h_m = self._cy(self.y1m) - self._cy(self.y0m)
        avail_w, avail_h = bx1 - bx0, by1 - by0
        mm_pt = 72 / 25.4
        k = min(avail_w / w_m, avail_h / h_m) / mm_pt          # échelle papier/réel
        self.scale_den = next((s for s in (2, 2.5, 5, 7.5, 10, 15, 20, 25, 50) if 1 / s <= k), 50)
        self.k = mm_pt / self.scale_den
        self.ox = bx0 + (avail_w - w_m * self.k) / 2 - self._cx(self.x0m) * self.k
        self.oy = by0 + (avail_h - h_m * self.k) / 2 - self._cy(self.y0m) * self.k

    # compression des zones coupées
    def _cx(self, x):
        return x

    def _cy(self, y):
        """Zone coupée [a, b] ramenée à une bande de G mm (trait de coupure)."""
        G = 70.0
        out = y
        for ax, a, b in self.cuts:
            if ax != "y":
                continue
            if y >= b:
                out -= (b - a) - G
            elif y > a:
                out -= (y - a) - G * (y - a) / (b - a)
        return out

    def P(self, x, y):
        return self.ox + self._cx(x) * self.k, self.oy + self._cy(y) * self.k

    def _clip_zones(self):
        """Zones visibles (en coordonnées modèle) : toute la vue, moins les intervalles coupés."""
        ycuts = [(a, b) for ax, a, b in self.cuts if ax == "y"]
        xcuts = [(a, b) for ax, a, b in self.cuts if ax == "x"]
        yz, prev = [], -1e9
        for a, b in ycuts:
            yz.append((prev, a)); prev = b
        yz.append((prev, 1e9))
        xz = [(-1e9, xcuts[0][0])] if xcuts else [(-1e9, 1e9)]
        return [(x, y) for x in xz for y in yz]

    def draw(self):
        cv = self.cv
        shapes = sorted(self.V.shapes, key=lambda s: s.z)
        for (xa, xb), (ya, yb) in self._clip_zones():
            cv.saveState()
            p = cv.beginPath()
            X0, Y0 = self.P(max(xa, self.x0m - 1000), max(ya, self.y0m - 1000))
            X1, Y1 = self.P(min(xb, self.x1m + 1000), min(yb, self.y1m + 1000))
            p.rect(X0, Y0, X1 - X0, Y1 - Y0)
            cv.clipPath(p, stroke=0, fill=0)
            for s in shapes:
                self._shape(s, (ya, yb))
            cv.restoreState()
        for ax, a, b in self.cuts:
            self._break_line(ax, a, b)

    def _path(self, s):
        cv = self.cv
        p = cv.beginPath()
        if s.kind == "circle":
            (cx, cy), r = s.pts
            X, Y = self.P(cx, cy)
            p.circle(X, Y, r * self.k)
            return p
        pts = [self.P(*q) for q in s.pts]
        p.moveTo(*pts[0])
        for q in pts[1:]:
            p.lineTo(*q)
        if s.kind in ("rect", "poly"):
            p.close()
        return p

    def _shape(self, s, yz):
        cv = self.cv
        if s.kind == "line":
            cv.setStrokeColor(_hex(s.color)); cv.setLineWidth(s.lw)
            cv.setDash(s.dash or [])
            cv.drawPath(self._path(s), stroke=1, fill=0)
            cv.setDash([])
            return
        fill, hatch = STYLE.get(s.mat, ("#eeeeee", None))
        cv.setFillColor(_hex(fill)); cv.setStrokeColor(_hex("#1d1d1d")); cv.setLineWidth(s.lw)
        path = self._path(s)
        cv.drawPath(path, stroke=0, fill=1)
        if hatch:
            cv.saveState()
            cv.clipPath(self._path(s), stroke=0, fill=0)
            self._hatch(s, hatch)
            cv.restoreState()
        cv.setLineWidth(s.lw)
        cv.setStrokeColor(_hex("#1d1d1d"))
        cv.drawPath(self._path(s), stroke=1, fill=0)

    def _bbox(self, s):
        if s.kind == "circle":
            (cx, cy), r = s.pts
            pts = [self.P(cx - r, cy - r), self.P(cx + r, cy + r)]
        else:
            pts = [self.P(*q) for q in s.pts]
        xs, ys = zip(*pts)
        return min(xs), min(ys), max(xs), max(ys)

    def _hatch(self, s, kind):
        cv = self.cv
        x0, y0, x1, y1 = self._bbox(s)
        cv.setLineWidth(0.25)
        if kind in ("beton",):
            cv.setStrokeColor(_hex("#7a7a7a")); cv.setFillColor(_hex("#7a7a7a"))
            step = 7.0
            i = 0
            y = y0 + 2
            while y < y1:
                x = x0 + (i % 3) * 2.3 + 1.5
                while x < x1:
                    if (int(x * 7 + y * 3)) % 5 == 0:
                        cv.line(x, y, x + 1.6, y + 1.0); cv.line(x + 1.6, y + 1.0, x + 0.4, y + 1.9); cv.line(x + 0.4, y + 1.9, x, y)
                    else:
                        cv.circle(x, y, 0.35, stroke=0, fill=1)
                    x += step * 0.9
                y += step * 0.7; i += 1
            cv.setFillColor(_hex("#7a7a7a"))
        elif kind in ("parpaing", "brique", "pierre", "bois", "chape"):
            col = {"parpaing": "#8a8a8a", "brique": "#a2543a", "pierre": "#8c7a5c", "bois": "#9c6b30", "chape": "#a7a29a"}[kind]
            cv.setStrokeColor(_hex(col))
            gap = {"parpaing": 5.0, "brique": 3.2, "pierre": 6.0, "bois": 2.6, "chape": 4.0}[kind]
            d = y1 - y0 + x1 - x0
            t = -d
            while t < d:
                if kind == "bois":
                    cv.line(x0, y0 + t + gap, x1, y0 + t + gap * 1.25)
                    t += gap
                    continue
                cv.line(x0 + t, y0, x0 + t + (y1 - y0), y1)
                if kind == "brique":
                    cv.line(x0 + t + 1.2, y0, x0 + t + 1.2 + (y1 - y0), y1)
                    t += gap * 1.2
                t += gap
        elif kind == "laine":
            cv.setStrokeColor(_hex("#a88a1e"))
            horiz = (x1 - x0) >= (y1 - y0)
            span = (y1 - y0) if horiz else (x1 - x0)
            amp = max(span / 2 - 0.4, 0.5)
            p = cv.beginPath()
            if horiz:
                ym = (y0 + y1) / 2
                x, up = x0, True
                p.moveTo(x, ym - amp)
                while x < x1:
                    x += span * 0.45
                    p.curveTo(x - span * 0.3, ym + (amp if up else -amp) * 1.6, x - span * 0.15, ym + (amp if up else -amp) * 1.6, x, ym - (amp if up else -amp))
                    up = not up
            else:
                xm = (x0 + x1) / 2
                y, up = y0, True
                p.moveTo(xm - amp, y)
                while y < y1:
                    y += span * 0.45
                    p.curveTo(xm + (amp if up else -amp) * 1.6, y - span * 0.3, xm + (amp if up else -amp) * 1.6, y - span * 0.15, xm - (amp if up else -amp), y)
                    up = not up
            cv.drawPath(p, stroke=1, fill=0)
        elif kind == "pse":
            cv.setStrokeColor(_hex("#b9a54a"))
            step = 4.5
            y = y0 + 1.5
            while y < y1:
                x = x0 + 1.5 + (int((y - y0) / step) % 2) * step / 2
                while x < x1:
                    cv.circle(x, y, 0.9, stroke=1, fill=0)
                    x += step
                y += step
        elif kind == "plaque":
            cv.setStrokeColor(_hex("#9a9a9a"))
            cv.setDash([0.6, 1.6])
            if (x1 - x0) < (y1 - y0):
                cv.line((x0 + x1) / 2, y0, (x0 + x1) / 2, y1)
            else:
                cv.line(x0, (y0 + y1) / 2, x1, (y0 + y1) / 2)
            cv.setDash([])
        elif kind == "verre":
            pass

    def _break_line(self, ax, a, b):
        cv = self.cv
        cv.setStrokeColor(_hex("#1d1d1d")); cv.setLineWidth(0.7)
        if ax == "y":
            for yy in (a, b):
                X0, Y = self.P(self.x0m + 20, yy)
                X1, _ = self.P(self.x1m - 40, yy)
                Y = self.P(0, yy)[1] + (0 if yy == a else 0)
                p = cv.beginPath(); p.moveTo(X0, Y)
                xm = (X0 + X1) / 2
                p.lineTo(xm - 4, Y); p.lineTo(xm - 1.5, Y + 4); p.lineTo(xm + 1.5, Y - 4); p.lineTo(xm + 4, Y); p.lineTo(X1, Y)
                cv.drawPath(p, stroke=1, fill=0)
            Ya, Yb = self.P(0, a)[1], self.P(0, b)[1]
            cv.setFont("CP-Oblique", 6.5); cv.setFillColor(_hex("#555555"))
            cv.drawString(self.P(self.x0m + 25, 0)[0], (Ya + Yb) / 2 - 2, self.d.L["partie_courante"])
        else:
            X = self.P(a, 0)[0]
            Y0, Y1 = self.P(0, self.y0m + 20)[1], self.P(0, self.y1m - 20)[1]
            p = cv.beginPath(); p.moveTo(X, Y0)
            ym = (Y0 + Y1) / 2
            p.lineTo(X, ym - 4); p.lineTo(X + 4, ym - 1.5); p.lineTo(X - 4, ym + 1.5); p.lineTo(X, ym + 4); p.lineTo(X, Y1)
            cv.drawPath(p, stroke=1, fill=0)

    def dims(self):
        cv = self.cv
        cv.setStrokeColor(_hex("#1d1d1d")); cv.setFillColor(_hex("#1d1d1d")); cv.setLineWidth(0.4)
        cv.setFont("CP", 6.8)
        for dm in self.V.dims:
            if dm[0] == "v":
                _, x, a, b, txt = dm
                X, Ya = self.P(x, a); _, Yb = self.P(x, b)
                cv.line(X, Ya, X, Yb)
                for Y in (Ya, Yb):
                    cv.line(X - 2.2, Y - 2.2, X + 2.2, Y + 2.2)
                    cv.line(X - 3.5, Y, X + 3.5, Y)
                cv.saveState(); cv.translate(X - 2.5, (Ya + Yb) / 2); cv.rotate(90)
                cv.drawCentredString(0, 0, txt); cv.restoreState()
            else:
                _, y, a, b, txt = dm
                Xa, Y = self.P(a, y); Xb, _ = self.P(b, y)
                cv.line(Xa, Y, Xb, Y)
                for X in (Xa, Xb):
                    cv.line(X - 2.2, Y - 2.2, X + 2.2, Y + 2.2)
                    cv.line(X, Y - 3.5, X, Y + 3.5)
                cv.drawCentredString((Xa + Xb) / 2, Y + 2.5, txt)
        cv.setFont("CP-Bold", 8)
        cv.setFillColor(_hex("#17483f"))
        for x, y, t in self.V.labels:
            X, Y = self.P(x, y)
            cv.drawString(X, Y, t)

    def bubbles(self, legend_keys: dict, col_left, col_right, y_top, y_bot):
        """Bulles numérotées réparties en deux colonnes (gauche / droite) sans chevauchement, reliées par un trait de rappel."""
        cv = self.cv
        items = {}
        mid = (self.P(self.x0m, 0)[0] + self.P(self.x1m, 0)[0]) / 2
        for s in self.V.shapes:
            if not s.key:
                continue
            ax, ay = s.anchor
            if not self._visible(ay, ax):
                ay = self._nearest_visible(ay)
            X, Y = self.P(ax, ay)
            if s.key not in items:
                items[s.key] = (X, Y)
        left = sorted([(Y, X, k) for k, (X, Y) in items.items() if X < mid], reverse=True)
        right = sorted([(Y, X, k) for k, (X, Y) in items.items() if X >= mid], reverse=True)
        for col, xcol in ((left, col_left), (right, col_right)):
            ys = self._spread([c[0] for c in col], y_top, y_bot, 13.5)
            for (Y, X, key), yb in zip(col, ys):
                n = legend_keys.setdefault(key, len(legend_keys) + 1)
                cv.setStrokeColor(_hex("#17483f")); cv.setLineWidth(0.35)
                cv.line(xcol + (5.5 if xcol < X else -5.5), yb, X, Y)
                cv.setFillColor(_hex("#17483f")); cv.circle(X, Y, 0.9, stroke=0, fill=1)
                cv.setFillColor(_hex("#ffffff")); cv.circle(xcol, yb, 5.5, stroke=1, fill=1)
                cv.setFillColor(_hex("#17483f")); cv.setFont("CP-Bold", 6.5)
                cv.drawCentredString(xcol, yb - 2.3, str(n))

    def _visible(self, y, x):
        for ax, a, b in self.cuts:
            if ax == "y" and a < y < b:
                return False
            if ax == "x" and x > a:
                return False
        return True

    def _nearest_visible(self, y):
        for ax, a, b in self.cuts:
            if ax == "y" and a < y < b:
                return a - 40 if y - a < b - y else b + 40
        return y

    @staticmethod
    def _spread(ys, top, bot, gap):
        if not ys:
            return []
        out = []
        cur = top + gap
        for y in ys:                      # du haut vers le bas
            yy = min(y, cur - gap)
            out.append(yy)
            cur = yy
        if out[-1] < bot:                 # trop bas : on remonte en bloc puis on resserre
            shift = bot - out[-1]
            out = [y + shift for y in out]
            for i in range(1, len(out)):
                if out[i - 1] - out[i] < gap:
                    out[i] = out[i - 1] - gap
        return out


def _wrap(text, font, size, width):
    from reportlab.pdfbase.pdfmetrics import stringWidth
    words, lines, cur = text.split(), [], ""
    for w in words:
        t = (cur + " " + w).strip()
        if stringWidth(t, font, size) > width and cur:
            lines.append(cur); cur = w
        else:
            cur = t
    if cur:
        lines.append(cur)
    return lines


def _register_fonts():
    """Police Vera livrée avec reportlab (accents FR/PT, ≥ ≤ ≈ Ø ×) — disponible sur tous les serveurs."""
    import os
    import reportlab
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    d = os.path.join(os.path.dirname(reportlab.__file__), "fonts")
    for name, f in (("CP", "Vera.ttf"), ("CP-Bold", "VeraBd.ttf"), ("CP-Oblique", "VeraIt.ttf")):
        if name not in pdfmetrics.getRegisteredFontNames():
            pdfmetrics.registerFont(TTFont(name, os.path.join(d, f)))


def render(params: dict) -> dict:
    """→ {"pdf": bytes, "png_vertical": bytes, "png_horizontal": bytes, "title": str, "subtitle": str, "key_values": [...], "notes": [...], "params": {...}}"""
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.pdfgen import canvas
    _register_fonts()
    d = Detail(params)
    Vv = d.vertical()
    Vh = d.plan()
    title, subtitle = d.title()
    kv = d.key_values()
    notes = d.notes_list()
    buf = io.BytesIO()
    cv = canvas.Canvas(buf, pagesize=A4)
    cv.setTitle(title)
    for view_kind, V, size in (("v", Vv, A4), ("h", Vh, landscape(A4))):
        cv.setPageSize(size)
        W, H = size
        m = 28
        cv.setFillColor(_hex("#17483f")); cv.setFont("CP-Bold", 13)
        cv.drawString(m, H - m - 6, f"{title} — {d.L[view_kind]}")
        cv.setFont("CP", 8); cv.setFillColor(_hex("#333333"))
        for i, line in enumerate(_wrap(subtitle, "CP", 8, W - 2 * m)[:2]):
            cv.drawString(m, H - m - 19 - i * 10, line)
        cv.setFillColor(_hex("#8a6d00")); cv.setFont("CP-Oblique", 7)
        cv.drawString(m, H - m - 41, d.L["subtitle"])
        # zone dessin / zone texte
        legend_h = 0
        if view_kind == "v":
            draw_box = (m + 40, 250, W - m - 40, H - m - 60)
        else:
            draw_box = (m + 40, 210, W - 250, H - m - 60)
        pg = _Page(cv, V, draw_box, d)
        pg.draw()
        pg.dims()
        legend = {}
        pg.bubbles(legend, draw_box[0] - 22, draw_box[2] + (22 if view_kind == "v" else 12), draw_box[3] - 4, draw_box[1] + 4)
        cv.setFont("CP", 7.5); cv.setFillColor(_hex("#1d1d1d"))
        cv.drawRightString(W - m, H - m - 6, f"{d.L['scale']} 1/{pg.scale_den:g}")
        # légende
        if view_kind == "v":
            lx, ly, lw, cols = m, 236, (W - 2 * m) / 2, 2
        else:
            lx, ly, lw, cols = W - 215, H - m - 64, 190, 1
        cv.setFont("CP-Bold", 8); cv.setFillColor(_hex("#17483f"))
        cv.drawString(lx, ly, d.L["legend"])
        cv.setFont("CP", 6.8); cv.setFillColor(_hex("#1d1d1d"))
        items = sorted(legend.items(), key=lambda kv_: kv_[1])
        per_col = math.ceil(len(items) / cols)
        y_end = ly
        for i, (key, n) in enumerate(items):
            c, r = divmod(i, per_col)
            x = lx + c * lw
            y = ly - 11 - r * 9.2
            cv.setFillColor(_hex("#17483f")); cv.drawString(x, y, f"{n}.")
            cv.setFillColor(_hex("#1d1d1d")); cv.drawString(x + 12, y, key[:95 if cols == 2 else 52])
            y_end = min(y_end, y)
        # cotes clés + hypothèses
        if view_kind == "v":
            tx, ty, tw = m, y_end - 18, (W - 2 * m) / 2 - 10
            nx, ny, nw = m + (W - 2 * m) / 2, y_end - 18, (W - 2 * m) / 2
        else:
            tx, ty, tw = m, 196, 300
            nx, ny, nw = m + 330, 196, W - 2 * m - 330
        cv.setFont("CP-Bold", 8); cv.setFillColor(_hex("#17483f"))
        cv.drawString(tx, ty, d.L["reserv"])
        cv.setFont("CP", 7)
        for i, (k_, v_) in enumerate(kv):
            yy = ty - 11 - i * 9
            cv.setFillColor(_hex("#1d1d1d")); cv.drawString(tx, yy, k_)
            cv.drawRightString(tx + tw, yy, v_)
            cv.setStrokeColor(_hex("#dddddd")); cv.setLineWidth(0.3); cv.line(tx, yy - 2.5, tx + tw, yy - 2.5)
        cv.setFont("CP-Bold", 8); cv.setFillColor(_hex("#8a6d00"))
        cv.drawString(nx, ny, d.L["hyp"])
        cv.setFont("CP", 6.8)
        yy = ny - 11
        for note in notes:
            for j, line in enumerate(_wrap(note, "CP", 6.8, nw - 8)):
                cv.drawString(nx + (0 if j == 0 else 6), yy, ("• " if j == 0 else "") + line)
                yy -= 8.5
            yy -= 1.5
        cv.setFont("CP", 6.5); cv.setFillColor(_hex("#555555"))
        cv.drawString(m, 18, d.L["foot"])
        cv.showPage()
    cv.save()
    pdf = buf.getvalue()
    import pymupdf
    doc = pymupdf.open(stream=pdf, filetype="pdf")
    pngs = [doc[i].get_pixmap(dpi=170).tobytes("png") for i in range(doc.page_count)]
    return {"pdf": pdf, "png_vertical": pngs[0], "png_horizontal": pngs[1], "title": title, "subtitle": subtitle,
            "key_values": kv, "notes": notes, "params": d.p}


# ----------------------------------------------------------------------------------------------------------------- outil Assistant
def _nullable(t, **kw):
    return {"type": [t, "null"], **kw}


WINDOW_TOOL = {"type": "function", "name": "draw_window_detail", "strict": True,
               "description": "Dessine le DÉTAIL DE MONTAGE d'une menuiserie (fenêtre, porte-fenêtre, baie coulissante), avec ou sans volet roulant : "
                              "coupe verticale (appui/seuil + tête avec linteau et coffre) et coupe horizontale (tableau en plan), à l'échelle, hachures, "
                              "légende numérotée, cotes de réservation calculées. À utiliser pour toute demande de schéma de pose / montage de fenêtre, "
                              "porte-fenêtre, baie, volet roulant, coffre, bloc-baie (et non draw_section_schema). Types : pose applique_int | tunnel | "
                              "feuillure | renovation | applique_ext (ITE) ; coffre aucun | monobloc (bloc-baie : coffre intégré, jamais « demi-coffre ») | "
                              "tunnel | interieur | exterieur. Mets null pour une cote inconnue : une valeur courante est prise et signalée comme hypothèse. "
                              "Si la combinaison est incompatible, l'outil renvoie une erreur à reformuler en question à l'utilisateur.",
               "parameters": {"type": "object", "additionalProperties": False, "properties": {
                   "ouvrage": {"type": "string", "enum": list(OUVRAGES)},
                   "pose": {"type": "string", "enum": list(POSES)},
                   "coffre": {"type": "string", "enum": list(COFFRES)},
                   "isolation": {"type": "string", "enum": list(ISOLATIONS)},
                   "materiau": {"type": "string", "enum": list(MATERIAUX)},
                   "mur": {"type": "string", "enum": list(MURS)},
                   "mur_ep_mm": _nullable("number"), "isolant_ep_mm": _nullable("number"), "isolant_ext_ep_mm": _nullable("number"),
                   "hauteur_mm": _nullable("number", description="hauteur de la menuiserie hors coffre"), "largeur_mm": _nullable("number"),
                   "allege_mm": _nullable("number", description="fenêtre : sol fini → dessus d'appui"), "linteau_h_mm": _nullable("number"),
                   "dalle_ep_mm": _nullable("number"), "hauteur_coffre_mm": _nullable("number", description="null = calculée depuis le Ø d'enroulement"),
                   "seuil_pmr": {"type": "boolean"}, "lang": {"type": "string", "enum": ["fr", "pt"]}},
                   "required": ["ouvrage", "pose", "coffre", "isolation", "materiau", "mur", "mur_ep_mm", "isolant_ep_mm", "isolant_ext_ep_mm",
                                "hauteur_mm", "largeur_mm", "allege_mm", "linteau_h_mm", "dalle_ep_mm", "hauteur_coffre_mm", "seuil_pmr", "lang"]}}
