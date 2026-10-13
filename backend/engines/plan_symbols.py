"""Bibliothèque des symboles de plans BTP (ConstruPilot v2.0) — référentiel injecté dans les prompts d'analyse et
heuristiques de classement des ouvrages détectés (texte voisin : PP, 50x30, 13x13, EF, EP…)."""
from __future__ import annotations

import json
import os
import re
from functools import lru_cache

_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "symbols_btp.json")
STRUCTURE_CATS = ("Architecture & ouvertures", "Béton armé & structure", "Cotations, niveaux & repères", "Maçonnerie, isolation & finitions")

# texte voisin → classe candidate (indicatif ; la légende du plan reste prioritaire)
LABEL_RULES = [
    (re.compile(r"^(?:PP|P\.P\.)\s*\d*$", re.I), "Poutre", "repère PP (poutre principale)"),
    (re.compile(r"^(?:PS|P\.S\.)\s*\d*$", re.I), "Poutre", "repère PS (poutre secondaire)"),
    (re.compile(r"^L\s*\d+$", re.I), "Longrine", "repère L (longrine)"),
    (re.compile(r"^S\s*\d+$", re.I), "Semelle filante", "repère S (semelle)"),
    (re.compile(r"^(\d{2,3})\s*[xX×]\s*(\d{2,3})$"), "SECTION", "section (largeur × hauteur en cm)"),
    (re.compile(r"^(?:EF|ECS|EU|EV|EP|BECS)$", re.I), "Réseau", "canalisation repérée"),
    (re.compile(r"^(?:ST)\s*\d+", re.I), "Treillis soudé", "repère STxx"),
]


@lru_cache(maxsize=1)
def library() -> dict:
    with open(_PATH, encoding="utf-8") as f:
        return json.load(f)


def prompt_block(categories: tuple[str, ...] = STRUCTURE_CATS, max_chars: int = 6000) -> str:
    """Bloc texte compact du référentiel (catégories structure par défaut) pour les prompts IA."""
    lib = library()
    lines = [f"RÉFÉRENTIEL SYMBOLES DE PLANS BTP ConstruPilot (v{lib['version']}). Priorité des sources : "
             + " > ".join(lib["priority_of_sources"]) + f". {lib['safety_rule']} Pour chaque ouvrage identifié, renvoyer : "
             + ", ".join(lib["expected_output"]) + "."]
    for it in lib["items"]:
        if it["category"] in categories:
            lines.append(f"- {it['name']} : {it['convention']} (à distinguer : {it['confusable_with']})")
    txt = "\n".join(lines)
    return txt[:max_chars]


def classify_by_label(text: str) -> tuple[str, str] | None:
    t = (text or "").strip()
    for rx, cls, why in LABEL_RULES:
        m = rx.match(t)
        if m:
            if cls == "SECTION":
                # 50x30 peut désigner une poutre, une semelle ou un autre
                # ouvrage. La section seule ne permet pas de choisir sa classe.
                return "Section d'ouvrage", "section annotée ; fonction à déterminer par la légende et le contexte"
            return cls, why
    return None


def label_walls(walls: list[dict], text_blocks: list[dict], px_per_pt: float, ppm: float) -> None:
    """Étiquette chaque mur détecté avec les textes situés dans sa bande (± 25 cm le long) → classe candidate indicative."""
    margin = 0.25 * ppm
    for w in walls:
        vert = w["orientation"] == "vertical"
        labels, classes = [], {}
        for t in text_blocks or []:
            # text_blocks et murs sont tous deux en points PDF, pas en pixels.
            cx, cy = t["x"] + t.get("w", 0) / 2, t["y"] + t.get("h", 0) / 2
            perp, along = (cx, cy) if vert else (cy, cx)
            if w["pos_1"] - margin <= perp <= w["pos_2"] + margin and w["lo"] - margin <= along <= w["hi"] + margin:
                txt = (t.get("text") or "").strip()
                if not txt or re.fullmatch(r"[\d.,]+", txt):
                    continue
                labels.append(txt)
                c = classify_by_label(txt)
                if c and c[0] != "Section d'ouvrage":
                    classes[c[0]] = classes.get(c[0], 0) + 1
        w["labels"] = sorted(set(labels))[:12]
        if classes:
            best = max(classes, key=classes.get)
            w["ouvrage_class"] = best
            w["class_source"] = "repère / annotation (bibliothèque symboles, indicatif — légende prioritaire)"
            w["class_alternatives"] = [k for k in classes if k != best]
        else:
            w["ouvrage_class"] = ("Voile béton / mur poché" if w.get("source") == "hatched_band" else "Mur (deux traits parallèles)")
            w["class_source"] = "géométrie vectorielle (convention générale, indicatif)"
            w["class_alternatives"] = ["Semelle filante", "Longrine", "Ligne de cote"] if not w.get("thickness_cote_m") else ["Cloison", "Voile béton"]


_LEGEND_RX = re.compile(r"^(l[ée]gende|nomenclature|symboles?|conventions?)\b", re.I)
_CARTOUCHE_KEYS = re.compile(r"(plan|fondation|coupe|fa[çc]ade|niveau|rdc|r\+\d|sous-sol|vide sanitaire|[ée]chelle|ech\.?|1/\d{2,3}|indice|date|dess|maître|ma[îi]tre|projet|dossier|ph\.?|phase|lot)", re.I)


def extract_legend(text_blocks: list[dict], width_px: float, height_px: float) -> dict:
    """Légende (bloc sous un titre « LÉGENDE / NOMENCLATURE / SYMBOLES ») et cartouche (bande droite ou bas-droit riche en
    mots-clés). Sources prioritaires pour classer les ouvrages : renvoyées au moteur et aux prompts IA."""
    tb = [t for t in text_blocks or [] if (t.get("text") or "").strip()]
    legend, cartouche = [], []
    titles = [t for t in tb if _LEGEND_RX.match(t["text"].strip())]
    for ti in titles:
        x0, y0 = ti["x"] - 0.02 * width_px, ti["y"]
        x1, y1 = ti["x"] + max(ti.get("w", 0) * 6, 0.25 * width_px), ti["y"] + 0.35 * height_px
        legend += [t["text"].strip() for t in tb if x0 <= t["x"] <= x1 and y0 <= t["y"] <= y1 and t is not ti]
    right = [t for t in tb if t["x"] >= 0.8 * width_px]
    bottom_right = [t for t in tb if t["x"] >= 0.6 * width_px and t["y"] >= 0.78 * height_px]
    zone = right if sum(1 for t in right if _CARTOUCHE_KEYS.search(t["text"])) >= sum(1 for t in bottom_right if _CARTOUCHE_KEYS.search(t["text"])) else bottom_right
    cartouche = [t["text"].strip() for t in sorted(zone, key=lambda t: (round(t["y"] / 12), t["x"]))]
    kind = None
    joined = " ".join(cartouche).lower()
    for k, lbl in (("fondation", "plan de fondations"), ("vide sanitaire", "plan du vide sanitaire"), ("coupe", "coupe"), ("façade", "façade"),
                   ("facade", "façade"), ("toiture", "plan de toiture"), ("rdc", "plan du RDC"), ("étage", "plan d'étage"), ("plan", "plan")):
        if k in joined:
            kind = lbl
            break
    return {"legend": legend[:60], "cartouche": cartouche[:40], "document_kind": kind, "has_legend": bool(legend)}
