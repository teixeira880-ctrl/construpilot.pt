"""Pré-preenchimento da Carta de Obra de Baixo Carbono a partir de um estudo completo (motor BET) : as quantidades vêm da
medição determinística do estudo (mesmas plantas → mesmas quantidades), nunca de um rácio. O que não se deduz da medição
fica vazio e aparece como controlo (DAP, distâncias, consumos da obra, documentos).
"""
from __future__ import annotations

import re
from pathlib import Path

from . import referentiel as R
from .calcul import calculer, ligne_materiau, nouveau_dossier

# clé du devis BET → famille du tableau (plusieurs familles possibles pour un même ouvrage composite)
CLE_FAMILLE = {
    "porotherme": ["maconnerie"], "pignon": ["maconnerie"], "bloc_bancher": ["maconnerie"],
    "plancher": ["plancher"], "couverture": ["couverture"], "enduit": ["enduit"],
    "fenetre": ["menuiserie"], "porte_entree": ["menuiserie_int"], "porte_garage": ["menuiserie_int"], "porte_int": ["menuiserie_int"],
    "placard": ["menuiserie_int"], "cloison": ["cloison"], "plafond": ["cloison"], "doublage": ["isolant", "cloison"],
    "isol_rampant": ["isolant"], "carrelage": ["chape"], "faience": ["chape"], "chape_anh": ["chape"], "parquet": ["parquet"],
    "peint_mur": ["peinture"], "peint_plaf": ["peinture"], "pac": ["pac"], "cet": ["pac"],
    "multicouche": ["canalisation"], "chute": ["canalisation"], "collecteur": ["canalisation"],
    "wc": ["sanitaire"], "lavabo": ["sanitaire"], "lave_mains": ["sanitaire"], "douche": ["sanitaire"], "baignoire": ["sanitaire"],
    "evier": ["sanitaire"], "pc": ["appareillage"], "pl": ["appareillage"], "inter": ["appareillage"], "rj45": ["appareillage"],
    "spec": ["appareillage"], "tableau": ["appareillage"],
}


def _section_m2(txt) -> float | None:
    m = re.search(r"(\d{2,3})\s*[×x]\s*(\d{2,3})(?:\s*[×x]\s*(\d{2,3}))?", str(txt or ""))
    if not m:
        return None
    a, b, c = (int(x) if x else None for x in m.groups())
    if c:                                   # « 2 × 75 × 225 » (moisé) → 2 pièces de 75 × 225
        return a * b * c / 1e6 if a < 10 else b * c / 1e6
    return a * b / 1e6


def dossier_depuis_etude(raw: dict, r: dict, tim: dict, lines: list[dict], sref_m2: float | None, nom: str = "", adresse: str = "",
                        typologie: str = "Moradia unifamiliar") -> dict:
    jalon = "Diretiva (UE) 2024/1275"
    d = nouveau_dossier(nom, typologie, round(sref_m2, 1) if sref_m2 else None, jalon, adresse, modele=False)
    dec = d["decisions"]
    acc: dict[str, dict] = {}

    def add(code, q, unit, src):
        f = R.FAMILLE[code]
        ln = acc.get(code)
        if ln is None:
            ln = acc[code] = ligne_materiau(code, origine="étude", detail=[])
        k = R.facteur_unite(unit, f["unite"])
        if k is None:
            dec.append(f"{f['famille']} : « {src} » ({q:g} {unit}) não convertível em {f['unite']} — não reportado")
            return
        ln["quantite_prevue"] = round(ln["quantite_prevue"] + q * k, 3)
        ln["detail"].append(f"{src} : {q:g} {unit}")

    q = (r or {}).get("quantities") or {}
    if q.get("concrete_total_m3"):
        add("beton", float(q["concrete_total_m3"]), "m³", "Betão da medição de estrutura (fundações, cave, laje térrea, paredes)")
    if q.get("steel_total_kg"):
        add("acier", float(q["steel_total_kg"]) / 1000, "t", "Aço da medição de estrutura (armaduras)")
    tim = tim or {}
    secs = {"panne": tim.get("panne_section"), "chevron": tim.get("chevron_section"), "sabliere": "75 × 200"}
    for ln in lines or []:
        key, qty = ln.get("key"), float(ln.get("qty") or 0)
        if qty <= 0:
            continue
        if key in secs:
            s = _section_m2(secs[key])
            if s:
                add("bois", qty * s, "m³", f"{ln.get('label')} ({qty:g} ml × secção {secs[key]})")
            else:
                dec.append(f"Cobertura : secção de « {ln.get('label')} » não lida — volume de madeira não reportado")
            continue
        for code in CLE_FAMILLE.get(key, []):
            add(code, qty, R.FAMILLE[code]["unite"] if ln.get("unit") in ("ft",) else ln.get("unit"), ln.get("label") or key)
    if any(ln.get("key") == "doublage" for ln in lines or []):
        dec.append("Contra-fachadas : área reportada em isolamento E em gesso cartonado (dois materiais do mesmo elemento)")
    if any(ln.get("key") == "gnt" for ln in lines or []):
        dec.append("Tout-venant sob a laje térrea : medido em m², tonelagem não deduzida sem espessura medida — completar com as guias de remessa")
    d["materiaux"] = sorted(acc.values(), key=lambda x: (R.LOTS.index(x["lot"]) if x["lot"] in R.LOTS else 99, x["famille"]))
    for ln in d["materiaux"]:
        ln["source_quantite"] = "Medição do estudo ConstruPilot"
        ln["typologie"], ln["solution"] = "Standard", ""     # la solution réelle est celle de la FDES déposée, pas celle du modèle
        ln["note"] = " ; ".join(ln.pop("detail", []))[:600]
    dec.insert(0, "Quantidades previstas retomadas da medição do estudo completo (nenhum rácio) ; FE de referência : " + R.SOURCE_TABLEAU)
    return d


def produire(raw: dict, r: dict, tim: dict, lines: list[dict], sref_m2: float | None, out: Path, stem: str,
             branding: dict | None = None) -> tuple[Path, Path, dict]:
    """Escreve Carta_baixo_carbono_<stem>.xlsx e .pdf ; devolve (xlsx, pdf, dossier)."""
    from . import export_pdf, export_xlsx
    pr = (raw or {}).get("project") or {}
    d = dossier_depuis_etude(raw, r, tim, lines, sref_m2, pr.get("name") or "", pr.get("address") or "")
    res = calculer(d)
    ent = str((branding or {}).get("company_name") or "")
    x = Path(out) / f"Carta_baixo_carbono_{stem}.xlsx"
    p = Path(out) / f"Carta_baixo_carbono_{stem}.pdf"
    x.write_bytes(export_xlsx.construire(res, ent))
    p.write_bytes(export_pdf.construire(res, branding, ent))
    return x, p, d
