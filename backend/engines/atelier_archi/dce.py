"""Maquette du Studio de projet → sélection de lots pour le rédacteur CCTP / DCE (`engines.cctp_redacteur`).

Toutes les quantités viennent du métré de la maquette (`estudio_projeto.derivar`) : surfaces nettes de murs par couche,
menuiseries du tableau des baies, sols / murs / plafonds par pièce, planchers, toiture. Une quantité que la maquette
ne connaît pas (faïence, fouilles, réseaux) n'est pas inventée : l'ouvrage est cité sans quantité, comme dans le
rédacteur CCTP. Le texte est toujours en français (CCTP / DCE en français sur construpilot.fr et construpilot.pt).
"""
from __future__ import annotations

import re
import unicodedata
from collections import defaultdict
from typing import Any, Dict, List, Optional, Tuple

from engines import estudio_projeto as EP
from engines.estudio_projeto import i18n as I

TYPES_BAIE = {"janela": "Fenêtre", "porta": "Porte", "portada": "Porte-fenêtre", "portao": "Porte de garage"}


def _f(s: str) -> str:
    return unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode().lower()


def _q(x: float) -> float:
    return round(float(x), 2)


def _ligne(designation: str, unite: str, quantite: Optional[float], localisation: str = "", detail: str = "") -> Dict[str, Any]:
    return {"designation": designation[:200], "unite": unite, "quantite": _q(quantite) if quantite else None,
            "localisation": localisation[:300], "detail": detail[:1000]}


def _couche_lot(materiau: str, exterieur: bool) -> Tuple[str, Optional[str], str]:
    """Couche de mur → (lot, ouvrage type du catalogue, intitulé)."""
    lot, ouv, titre = _couche_lot_brut(materiau, exterieur)
    pre = titre.split(" — ")[0]
    if " — " in titre and _f(materiau).startswith(_f(pre)):     # « Isolation … — Isolation … (PSE) » → une seule fois
        titre = materiau
    return lot, ouv, titre


def _couche_lot_brut(materiau: str, exterieur: bool) -> Tuple[str, Optional[str], str]:
    m = _f(materiau)
    if re.search(r"etics|isolation thermique par l.exterieur|ite\b|sous-enduit arme|finition acrylique|finition armee|polystyrene.*(graphite|gris)", m):
        return "gros_oeuvre", None, f"Isolation thermique par l'extérieur — {materiau}"
    if re.search(r"enduit|crepi|monocouche", m) and exterieur:
        return "gros_oeuvre", "enduit_facade", f"Enduit de façade — {materiau}"
    if re.search(r"doublage|isolant|laine|pse|polystyrene|polyurethane", m):
        return "platrerie", "doublage_isolant", f"Doublage isolant — {materiau}"
    if re.search(r"carreau de platre|carreaux de platre", m):
        return "platrerie", "carreaux_platre", f"Cloison en carreaux de plâtre — {materiau}"
    if re.search(r"plaque de platre|ba13|placo|gypse", m):
        return "platrerie", None, f"Parement plaque de plâtre — {materiau}"
    if re.search(r"enduit|platre projete", m):
        return "platrerie", None, f"Enduit intérieur — {materiau}"
    if re.search(r"beton arme|voile", m):
        return "gros_oeuvre", None, f"Voile en béton armé — {materiau}"
    if re.search(r"parpaing|bloc|brique|beton cellulaire|monomur|maconnerie|pierre|terre cuite", m):
        return "gros_oeuvre", "murs_blocs", f"Maçonnerie — {materiau}"
    if re.search(r"bois|ossature|clt|osb", m):
        return "charpente_couverture", None, f"Ossature / panneaux bois — {materiau}"
    return "gros_oeuvre", None, materiau


def selection(modelo: Dict[str, Any], lots: Optional[List[str]] = None) -> Dict[str, Any]:
    """Renvoie {"lots": [LotSel…], "pieces": [...], "resume": {...}} prêt pour `cctp_redacteur.rediger`."""
    der = I.traduzir(EP.derivar(modelo), "fr")
    md = der["medicoes"]
    sel: Dict[str, Dict[str, Any]] = defaultdict(lambda: {"ouvrages": [], "lignes": [], "notes": ""})
    plana = modelo["cobertura"]["tipo"] == "plana"
    garage_noms = {d["nome"] for d in md["divisoes"] if "garag" in _f(d["nome"])}

    def L(lot: str, *lignes: Dict[str, Any], ouvrages: Tuple[str, ...] = ()) -> None:
        s = sel[lot]
        s["lignes"] += [l for l in lignes if l]
        for o in ouvrages:
            if o not in s["ouvrages"]:
                s["ouvrages"].append(o)

    # ---- VRD / gros œuvre : emprise, fondations, planchers
    emprise = md.get("area_implantacao_m2") or 0
    if emprise:
        L("vrd", _ligne("Décapage de la terre végétale sur l'emprise du bâtiment", "m2", emprise, "Emprise du bâtiment",
                        "Surface d'emprise de la maquette ; débords de terrassement suivant étude de sol."), ouvrages=("fouilles", "remblai"))
    ext_p0 = sum(p["comprimento_liquido_m"] for p in md["paredes"] if p["exterior"] and p["piso"] == modelo["pisos"][0]["id"])
    if ext_p0:
        L("gros_oeuvre", _ligne("Semelles filantes sous murs périphériques", "ml", ext_p0, "Périphérie du rez-de-chaussée",
                                "Linéaire mesuré sur la maquette ; section et armatures suivant étude de structure (G2 / BET)."))
    for lj in md["lajes"]:
        n = _f(lj["nome"])
        if "bas du rez" in n or "terre" in n or "terrea" in n:
            L("gros_oeuvre", _ligne("Dallage / plancher bas du rez-de-chaussée", "m2", lj["area_m2"], "Rez-de-chaussée",
                                    f"Épaisseur de la maquette {lj['espessura_m'] * 100:.0f} cm, suivant étude de structure."))
        elif "dalle haute" in n or "cobertura" in n or "toiture" in n:
            if plana:
                L("gros_oeuvre", _ligne("Dalle de toiture-terrasse en béton armé", "m2", lj["area_m2"], "Toiture",
                                        "Étanchéité de toiture-terrasse : lot étanchéité à ajouter au DCE."))
        else:
            L("gros_oeuvre", _ligne(f"Plancher intermédiaire — {lj['nome']}", "m2", lj["area_m2"], lj["nome"],
                                    f"Épaisseur de la maquette {lj['espessura_m'] * 100:.0f} cm (poutrelles-hourdis ou dalle pleine suivant BET)."),
              ouvrages=("plancher_hourdis",))
    L("gros_oeuvre", ouvrages=("chainages",))

    # ---- murs par type et par couche (surfaces nettes, ouvertures déduites)
    for t in md["por_tipo"]:
        ext = any(p["exterior"] for p in md["paredes"] if p["tipo"] == t["tipo"])
        for c in t["camadas"]:
            lot, ouv, titre = _couche_lot(c["material"], ext)
            if ouv == "enduit_facade":
                continue                                   # façade : une seule ligne, sur la surface nette de façade (plus bas)
            L(lot, _ligne(f"{titre} — ép. {c['esp_m'] * 100:.1f} cm".replace(".0 cm", " cm"), "m2", c["area_m2"],
                          t["nome"], "Surface nette mesurée sur la maquette, baies déduites."),
              ouvrages=(ouv,) if ouv else ())
    f = md["fachada"]
    if f["area_liquida_m2"]:
        fin = next((a["material"] for a in md["acabamentos"] if _f(a["elemento"]).startswith("facade")), "enduit")
        L("gros_oeuvre", _ligne(f"Revêtement de façade — {fin}", "m2", f["area_liquida_m2"], "Ensemble des façades",
                                f"Périmètre {f['perimetro_m']:.2f} m, surface brute {f['area_bruta_m2']:.2f} m², baies {f['area_vaos_m2']:.2f} m²."),
          ouvrages=("enduit_facade",))

    # ---- aménagements extérieurs posés dans le Studio (piscine, terrasses, allées, jardin) : quantités de la maquette
    for e in md.get("exteriores") or []:
        t, nom = e["tipo"], e["nome"]
        if t in ("piscina", "piscina_infinita", "jacuzzi"):
            L("vrd", _ligne(f"{nom} — terrassement, structure et étanchéité (suivant étude)", "m2", e["area_m2"], "Extérieurs",
                            f"Dimensions de la maquette : {', '.join(e['medidas'])}.".replace(".", ",")[:-1] + "."),
              _ligne(f"{nom} — margelles", "ml", e["perimetro_m"], "Extérieurs", "Périmètre du bassin mesuré sur la maquette."))
        elif t in ("terraco_pedra", "deck_madeira", "deck_piscina", "caminho", "acesso_viaturas", "estrada", "estacionamento",
                   "terraco_suspenso", "parque_infantil", "campo_jogos", "campo_tenis", "lago", "horta", "sebe"):
            L("vrd", _ligne(f"{nom}", "m2", e["area_m2"], "Extérieurs", f"Dimensions de la maquette : {', '.join(e['medidas'])}.".replace(".", ",")[:-1] + "."))
        elif t in ("relvado", "canteiro"):
            L("vrd", _ligne(f"{nom} — préparation du sol et engazonnement / plantation", "m2", e["area_m2"], "Extérieurs"))
        elif t in ("arvore", "arbusto"):
            L("vrd", _ligne(f"{nom} — fourniture et plantation", "u", e["quantidade"], "Extérieurs"))
        elif t in ("pergola", "muro_vedacao", "cozinha_exterior", "casa_maquinas", "portao_entrada", "guarda_corpo", "pilar", "baloico", "escorrega",
                   "trampolim", "caixa_areia", "casinha_criancas"):
            L("vrd", _ligne(f"{nom}", "u", e["quantidade"], "Extérieurs", f"Dimensions de la maquette : {', '.join(e['medidas'])}.".replace(".", ",")[:-1] + "."))

    # ---- toiture
    cob = md["cobertura"]
    if not plana and cob.get("area_m2"):
        couv = next((a["material"] for a in md["acabamentos"] if _f(a["elemento"]).startswith("toiture")), "tuiles")
        L("charpente_couverture",
          _ligne("Charpente (fermettes industrielles ou traditionnelle suivant BET)", "m2", cob["area_planta_m2"], "Toiture",
                 f"Surface en plan ; pente {cob['inclinacao_graus']:.0f}° ({I.parte(cob['tipo'], 'fr')})."),
          _ligne("Écran de sous-toiture HPV", "m2", cob["area_m2"], "Toiture", "Surface rampante réelle."),
          _ligne(f"Couverture — {couv}", "m2", cob["area_m2"], "Toiture", "Surface rampante réelle mesurée sur la maquette."),
          _ligne("Égouts, rives et habillages de débords (zinguerie)", "ml", cob.get("perimetro_beirado_m"), "Périmètre des débords",
                 "Linéaire total des débords de toiture ; gouttières et descentes suivant calepinage."),
          ouvrages=("zinguerie",))
        if cob.get("empenas_m2"):
            L("gros_oeuvre", _ligne("Maçonnerie des pignons", "m2", cob["empenas_m2"], "Pignons", "Surface des pignons sous rampants."))
    # ---- menuiseries
    for v in md.get("mapa_vaos") or []:
        tb = TYPES_BAIE.get(v["tipo"], "Baie")
        des = f"{v['codigo']} — {tb} {v['modelo'].lower()} {v['largura_m']:.2f} × {v['altura_m']:.2f} m".replace(".", ",")
        if v["exterior"]:
            L("menuiseries_ext", _ligne(des, "u", v["quantidade"], "Repères " + " ".join(v["ids"]),
                                        f"{v['caixilharia']} ; allège {v['peitoril_m']:.2f} m.".replace(".", ",", 1)))
            if v.get("protecao") and not _f(v["protecao"]).startswith("sans") and not _f(v["protecao"]).startswith("sem"):
                L("menuiseries_ext", _ligne(f"{v['codigo']} — {v['protecao']}", "u", v["quantidade"], "Repères " + " ".join(v["ids"])),
                  ouvrages=("volets",))
        else:
            L("menuiseries_int", _ligne(f"Bloc-porte intérieur {v['largura_m']:.2f} × {v['altura_m']:.2f} m".replace(".", ","), "u",
                                        v["quantidade"], "Repères " + " ".join(v["ids"])), ouvrages=("bloc_porte",))
    for e in md.get("escadas") or []:
        des = (f"Escalier {I.parte('escada ' + e['tipo'], 'fr')} — {e['n_espelhos']} marches de {e['espelho_m'] * 100:.1f} cm, "
               f"giron {e['cobertor_m'] * 100:.0f} cm, emmarchement {e['largura_m']:.2f} m").replace(".", ",")
        L("menuiseries_int", _ligne(des, "u", 1, e["piso"],
                                    f"2h + g = {e['blondel_m']:.2f} m (DTU 36.3) ; matériau suivant choix du maître d'ouvrage.".replace(".", ",", 1)),
          ouvrages=("escalier_bois",))

    # ---- second œuvre par pièce (garage exclu des finitions)
    pieces = [d for d in md["divisoes"] if d["nome"] not in garage_noms]
    sols: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for d in pieces:
        sols[d["pavimento"]].append(d)
    for mat, ds in sols.items():
        surf = sum(d["area_m2"] for d in ds)
        loc = ", ".join(d["nome"] for d in ds)
        m = _f(mat)
        if re.search(r"parquet|stratifie|vinyle|pvc|lino|moquette|sol souple", m):
            L("sols_souples", _ligne(f"Revêtement de sol — {mat}", "m2", surf, loc), ouvrages=("ragreage",))
        else:
            L("sols_durs", _ligne("Chape de ravoirage / chape flottante", "m2", surf, loc, "Sous revêtements collés ou scellés."),
              _ligne(f"Revêtement de sol — {mat}", "m2", surf, loc),
              _ligne("Plinthes assorties", "ml", sum(d["rodape_m"] for d in ds), loc, "Linéaire de plinthes mesuré, portes déduites."))
    if any(re.search(r"salle|bain|eau|wc|cuisine", _f(d["nome"])) for d in pieces):
        L("sols_durs", ouvrages=("faience",))
    murs = sum(d["area_paredes_m2"] for d in pieces if re.search(r"peint|tinta|pintura", _f(d["parede_interior"])))
    plafonds = sum(d["area_m2"] for d in pieces if re.search(r"peint|pintad|pintura", _f(d["teto"])))
    if murs:
        L("peinture", _ligne("Peinture des murs intérieurs", "m2", murs, "Ensemble des pièces", "Faces des murs des pièces, baies déduites."))
    if plafonds:
        L("peinture", _ligne("Peinture des plafonds", "m2", plafonds, "Ensemble des pièces"))
    if not plana:
        haut = modelo["pisos"][-1]["id"]
        sous_combles = sum(d["area_m2"] for d in md["divisoes"] if d["piso"] == haut)
        L("platrerie", _ligne("Plafond plaque de plâtre sous charpente", "m2", sous_combles, "Dernier niveau"),
          _ligne("Isolation des combles", "m2", sous_combles, "Dernier niveau", "Résistance thermique suivant étude thermique RE2020."),
          ouvrages=("plafond_ba13", "isolation_combles"))
    L("electricite", ouvrages=("branchement", "terre", "tableau"))
    L("plomberie", ouvrages=("distribution", "evacuations", "ecs"))
    L("cvc", ouvrages=("vmc",))

    from engines.cctp_pieces import type_piece
    prog = [{"nom": d["nome"], "type": type_piece({"nom": d["nome"]}), "surface": d["area_m2"],
             "niveau": next((p["nome"] for p in der["pisos"] if p["id"] == d["piso"]), "")} for d in md["divisoes"]]

    voulus = set(lots or [])
    lots_out = []
    from engines.cctp_catalogue import LOTS_PAR_CODE
    for code, s in sel.items():
        if code not in LOTS_PAR_CODE or (voulus and code not in voulus):
            continue
        if not s["lignes"] and not s["ouvrages"]:
            continue
        lots_out.append({"code": code, "ouvrages": s["ouvrages"][:40], "lignes": s["lignes"][:200], "inclure": [], "titre": "",
                         "notes": "Quantités issues de la maquette ConstruPilot (Studio de projet) : surfaces nettes, baies déduites."})
    ordre = list(LOTS_PAR_CODE)
    lots_out.sort(key=lambda l: ordre.index(l["code"]))
    tot = md["totais"]
    return {"lots": lots_out, "pieces": prog[:60],
            "resume": {"surface_utile_m2": tot["area_util_m2"], "surface_construite_m2": tot["area_bruta_construcao_m2"],
                       "niveaux": len(modelo["pisos"]), "lots": [{"code": l["code"], "titre": LOTS_PAR_CODE[l["code"]]["titre"],
                                                                 "lignes": len(l["lignes"])} for l in lots_out]}}
