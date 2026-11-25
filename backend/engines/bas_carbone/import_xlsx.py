"""Importação de um quadro já preenchido pela empresa : modelo « Charte_Chantier_Bas_Carbone v3 » (FR) ou exportação
ConstruPilot (PT ou FR). Os valores franceses (capítulos, tipologias) são convertidos para os equivalentes portugueses.
Lecture par NOMS de colonnes (pas par position) ; seules les valeurs saisies sont reprises, les formules sont recalculées
par ConstruPilot."""
from __future__ import annotations

import io

import openpyxl

from . import referentiel as R
from .calcul import _num, ligne_materiau

COLS = {"capitulo / especialidade": "lot", "familia de materiais": "famille", "solucao aplicada": "solution", "tipologia": "typologie",
        "quantidade considerada": "quantite", "unidade": "unite", "fe referencia standard": "fe_ref", "fe dap obra": "fe_fdes",
        "ref. dap": "ref_fdes", "distancia abast.": "distance_km", "qtd. prevista": "quantite_prevue", "qtd. entregue": "quantite_livree",
        "validade dap": "fdes_validite",
        "lot": "lot", "famille de materiaux": "famille", "solution mise en oeuvre": "solution", "typologie": "typologie",
        "quantite": "quantite", "quantite retenue": "quantite", "unite": "unite", "fe reference standard": "fe_ref",
        "fe fdes / pep chantier": "fe_fdes", "ref. fdes / pep": "ref_fdes", "distance appro.": "distance_km",
        "qte prevue (metre)": "quantite_prevue", "qte livree (bons de livraison)": "quantite_livree", "validite fdes": "fdes_validite"}
EMI = {"subcategoria / recurso": "ressource", "quantidade consumida": "quantite", "sous-categorie / ressource": "ressource", "quantite consommee": "quantite"}
CH = {"indicador de desempenho": "kpi", "valor realizado": "realise", "estado de implementacao": "statut", "estado forcado": "statut_force",
      "indicateur de performance": "kpi", "valeur realisee": "realise", "statut de mise en oeuvre": "statut", "statut force": "statut_force"}
FR_LOTS = ["Gros Œuvre", "Charpente / Structure", "Façade / Enveloppe", "Menuiseries", "Second Œuvre", "Revêtements",
           "Lots Techniques (CVC / Élec / Plomberie)", "VRD / Aménagements"]
FR_TYPO = {"Bas carbone": "Baixo carbono", "Biosourcé": "Biológico", "Géosourcé": "Geológico", "Recyclé": "Reciclado", "Réemploi": "Reutilização"}
FR_TYPOLOGIE = {"Maison individuelle": "Moradia unifamiliar", "Logement collectif": "Habitação coletiva", "Bureaux": "Serviços / escritórios",
               "Enseignement primaire/secondaire": "Escolar", "Autre tertiaire": "Outro"}
SHEETS = {"mat": ("Materiais", "Suivi_Materiaux"), "emi": ("Emissoes_Obra", "Suivi_Emissions_Chantier"), "ch": ("Grelha_Carta", "Grille_Charte_Bas_Carbone"),
          "syn": ("Sintese", "Synthese_RE2020")}


def _sheet(wb, k):
    return next((n for n in SHEETS[k] if n in wb.sheetnames), None)


def _map(row, table):
    out = {}
    for i, h in enumerate(row):
        f = R.fold(str(h or "").replace("Œ", "Oe").replace("œ", "oe"))
        for k, v in table.items():
            if f.startswith(k) and v not in out:
                out[v] = i
    return out


def _wb_vals(data: bytes):
    """Valeurs saisies (formules ignorées : None si la cellule est une formule non calculée)."""
    wb = openpyxl.load_workbook(io.BytesIO(data), data_only=True)
    wf = openpyxl.load_workbook(io.BytesIO(data), data_only=False)
    return wb, wf


def importer(dossier: dict, data: bytes) -> list[str]:
    wb, wf = _wb_vals(data)
    dec: list[str] = []
    sh = _sheet(wb, "mat")
    if sh:
        ws, wsf = wb[sh], wf[sh]
        rows = list(ws.iter_rows(values_only=True))
        frows = list(wsf.iter_rows(values_only=True))
        hi = next((i for i, r in enumerate(rows[:10]) if r and any(R.fold(c).startswith(("famille de materiaux", "familia de materiais")) for c in r if c)), None)
        if hi is not None:
            cm = _map(rows[hi], COLS)
            lignes = []
            for r, rf in zip(rows[hi + 1:], frows[hi + 1:]):
                lot = r[cm["lot"]] if "lot" in cm else None
                if not lot or str(lot).upper().startswith("TOTAL") or str(lot).startswith("Leg"):
                    continue
                get = lambda k: r[cm[k]] if k in cm and cm[k] < len(r) else None   # noqa: E731
                isf = lambda k: k in cm and isinstance(rf[cm[k]], str) and str(rf[cm[k]]).startswith("=")   # noqa: E731
                fam = str(get("famille") or "")
                code = R.famille_de(fam + " " + str(get("solution") or ""))
                ln = ligne_materiau(code, origine="importação Excel")
                lot = R.LOTS[FR_LOTS.index(str(lot))] if str(lot) in FR_LOTS else str(lot)
                if lot not in R.LOTS:
                    lot = ln["lot"]
                typo = FR_TYPO.get(str(get("typologie") or ""), str(get("typologie") or "Standard"))
                ln.update(lot=lot, famille=fam or ln["famille"], solution=str(get("solution") or ""),
                          typologie=typo if typo in R.TYPOLOGIES_MATERIAU else "Standard", unite=R.unite(get("unite")) or ln["unite"],
                          fe_ref=_num(get("fe_ref")), fe_fdes=_num(get("fe_fdes")), ref_fdes=str(get("ref_fdes") or ""),
                          distance_km=_num(get("distance_km")), fdes_validite=str(get("fdes_validite") or ""))
                if "quantite_prevue" in cm:
                    ln["quantite_prevue"] = _num(get("quantite_prevue")) or 0.0
                    ln["quantite_livree"] = _num(get("quantite_livree"))
                elif not isf("quantite"):
                    ln["quantite_prevue"] = _num(get("quantite")) or 0.0
                ln["fe_ref_source"] = "importação Excel" if ln["fe_ref"] is not None else ""
                lignes.append(ln)
            if lignes:
                dossier["materiaux"] = lignes
                dec.append(f"Importação Excel : {len(lignes)} linha(s) de materiais retomadas")
    sh = _sheet(wb, "emi")
    if sh:
        rows = list(wb[sh].iter_rows(values_only=True))
        hi = next((i for i, r in enumerate(rows[:6]) if r and any(R.fold(c).startswith(("quantite consommee", "quantidade consumida")) for c in r if c)), None)
        if hi is not None:
            cm = _map(rows[hi], EMI)
            n = 0
            data = [r for r in rows[hi + 1:] if r and r[0] and not str(r[0]).upper().startswith("TOTAL")]
            for i, r in enumerate(data[:len(dossier["emissions"])]):     # mesma ordem de linhas nos modelos FR e PT
                if "quantite" in cm and _num(r[cm["quantite"]]) is not None:
                    dossier["emissions"][i]["quantite"] = _num(r[cm["quantite"]])
                    n += 1
            dec.append(f"Importação Excel : {n} consumo(s) da obra retomados")
    sh = _sheet(wb, "ch")
    if sh:
        rows = list(wb[sh].iter_rows(values_only=True))
        hi = next((i for i, r in enumerate(rows[:6]) if r and any(R.fold(c).startswith(("valeur realisee", "valor realizado")) for c in r if c)), None)
        if hi is not None:
            cm = _map(rows[hi], CH)
            n = 0
            for r, c in zip(rows[hi + 1:], dossier["charte"]):
                v = _num(r[cm["realise"]]) if "realise" in cm else None
                if v is not None:
                    c["realise"] = v
                    n += 1
                sf = r[cm["statut_force"]] if "statut_force" in cm else (r[cm["statut"]] if "statut" in cm else None)
                if sf in ("Non applicable", "Não aplicável"):
                    c["statut_force"] = "Não aplicável"
            dec.append(f"Importação Excel : {n} valor(es) realizado(s) da carta retomados")
    sh = _sheet(wb, "syn")
    if sh:
        ws = wb[sh]
        for r in range(3, 12):
            a = R.fold(ws.cell(r, 1).value)
            v = ws.cell(r, 2).value
            if a.startswith(("typologie", "tipologia")) and v:
                t = FR_TYPOLOGIE.get(str(v), str(v))
                if t in R.TYPOLOGIES:
                    dossier["projet"]["typologie"] = t
            elif a.startswith(("surface de reference", "area util")) and _num(v):
                dossier["projet"]["sref_m2"] = _num(v)
            elif a.startswith("meta de carbono") and _num(v):
                dossier["projet"]["seuil_ic"] = _num(v)
    dossier["decisions"] = list(dict.fromkeys((dossier.get("decisions") or []) + dec))
    return dec
