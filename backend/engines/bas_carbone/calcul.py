"""Cálculo do balanço de carbono da obra e cruzamento com os imperativos da carta (100 % determinístico, sem IA).
(Versão portuguesa : identificadores internos iguais aos do construpilot.fr para facilitar a manutenção conjunta.)

Un dossier est un dict JSON (stocké tel quel en base) :
  projet     : nom, adresse, typologie, sref_m2, jalon, seuil_ic (forcé, sinon RE2020), date
  materiaux  : lignes du suivi (famille, quantités prévue / livrée, FE référence, FE FDES, réf. FDES, distance, pièces)
  emissions  : consommations de la phase chantier (GNR, HVO, kWh, eau, t.km, déchets, km)
  charte     : engagements (imperatif op/cible, valeur réalisée, statut forcé éventuel, pièces)
  dechets    : tonnages issus des BSD (total, valorisé)
  documents  : pièces déposées par les entreprises (FDES, fiches techniques, bons de livraison, BSD, factures…)

calculer(dossier) renvoie les résultats et la liste des contrôles : ce qui MANQUE et ce qui SORT des imperatifs du chantier.
"""
from __future__ import annotations

import copy
import secrets
from datetime import date

from . import referentiel as R

NIVEAUX = ("bloquant", "alerte", "manquant", "info")      # ordre d'affichage


def _id(p: str) -> str:
    return f"{p}_{secrets.token_hex(4)}"


def _num(v):
    if v is None or v == "" or isinstance(v, bool):
        return None
    try:
        x = float(str(v).replace(",", ".").replace(" ", "").replace(" ", "")) if isinstance(v, str) else float(v)
    except (TypeError, ValueError):
        return None
    return x if x == x and abs(x) != float("inf") else None


def ligne_materiau(code: str | None = None, **kw) -> dict:
    f = R.FAMILLE.get(code or "", {})
    ln = {"id": _id("mat"), "code": code, "lot": f.get("lot", R.LOTS[0]), "famille": f.get("famille", ""), "solution": f.get("solution", ""),
          "typologie": f.get("typologie", "Standard"), "unite": f.get("unite", "u"), "quantite_prevue": 0.0, "quantite_livree": None,
          "fe_ref": f.get("fe_ref"), "fe_ref_source": R.SOURCE_TABLEAU if f.get("fe_ref") is not None else "",
          "fe_fdes": None, "ref_fdes": "", "fdes_unite": "", "fdes_validite": "", "distance_km": None, "distance_source": "",
          "origine": "introduzido", "source_quantite": "", "pieces": [], "note": ""}
    ln.update({k: v for k, v in kw.items() if k in ln or k == "detail"})
    return ln


def nouveau_dossier(nom: str = "", typologie: str = "Habitação coletiva", sref_m2: float | None = None, jalon: str = "Diretiva (UE) 2024/1275",
                    adresse: str = "", modele: bool = True) -> dict:
    """Dossier vierge au format du tableau. modele=True : les 14 familles du tableau à quantité nulle (lignes à compléter)."""
    mats = [ligne_materiau(f["code"]) for f in R.FAMILLES if f.get("fe_ref") is not None] if modele else []
    return {
        "version": 1,
        "projet": {"nom": nom, "adresse": adresse, "typologie": typologie, "sref_m2": sref_m2, "jalon": jalon, "seuil_ic": None,
                   "date": date.today().isoformat()},
        "materiaux": mats,
        "emissions": [{"id": c, "poste": p, "ressource": r, "quantite": 0.0, "unite": u, "fe": fe, "unite_fe": ufe, "pieces": []}
                      for c, p, r, u, fe, ufe in R.EMISSIONS],
        "charte": [dict(zip(R.CHARTE_KEYS, c), realise=None, statut_force=None, commentaire="", pieces=[]) for c in R.CHARTE],
        "dechets": {"total_t": None, "valorise_t": None, "pieces": []},
        "documents": [],
        "decisions": [],
    }


# --------------------------------------------------------------------------------------------------------------------------------
def _ok(op: str, realise: float, cible: float) -> bool:
    return realise >= cible if op == ">=" else realise <= cible if op == "<=" else abs(realise - cible) < 1e-9


def _ctrl(out, niveau, code, message, action="", cible=None, ref=None):
    out.append({"niveau": niveau, "code": code, "message": message, "action": action, "cible": cible, "ref": ref})


def _date(s):
    try:
        return date.fromisoformat(str(s)[:10])
    except (TypeError, ValueError):
        return None


def calculer(dossier: dict, aujourd_hui: date | None = None) -> dict:
    d = copy.deepcopy(dossier)
    today = aujourd_hui or date.today()
    pj = d.get("projet") or {}
    ctrl: list[dict] = []
    docs = {x.get("doc_id"): x for x in d.get("documents") or []}

    # ------------------------------------------------------------------ matériaux
    lignes = []
    for ln in d.get("materiaux") or []:
        f = R.FAMILLE.get(ln.get("code") or "", {})
        qp, ql = _num(ln.get("quantite_prevue")), _num(ln.get("quantite_livree"))
        q = ql if ql is not None and ql > 0 else (qp or 0.0)
        fe_ref, fe_fdes = _num(ln.get("fe_ref")), _num(ln.get("fe_fdes"))
        fe_reel = fe_fdes if fe_fdes is not None else fe_ref
        k = q * fe_ref if fe_ref is not None else 0.0
        l_ = q * fe_reel if fe_reel is not None else 0.0
        actif = q > 0 or bool(ln.get("pieces"))
        nom = f"{ln.get('famille') or ln.get('solution') or 'Linha'}"
        r = dict(ln, quantite=round(q, 3), fe_reel=fe_reel, poids_ref=round(k, 2), poids_reel=round(l_, 2), gain=round(k - l_, 2),
                 reduction=round((k - l_) / k, 4) if k > 0 else 0.0, actif=actif, controles=[])
        mine = []
        if actif:
            if q <= 0:
                _ctrl(mine, "manquant", "MAT-01", f"{nom} : documento depositado mas quantidade nula",
                      "Introduzir a quantidade prevista na medição ou depositar a guia de remessa", "materiau", ln["id"])
            if fe_ref is None:
                _ctrl(mine, "manquant", "MAT-03", f"{nom} : fator de emissão de referência a introduzir (sem valor por defeito no referencial)",
                      "Introduzir o dado ambiental genérico ou a DAP do produto", "materiau", ln["id"])
            if fe_fdes is None:
                lvl = "manquant" if q > 0 else "info"
                _ctrl(mine, lvl, "MAT-02", f"{nom} : DAP não fornecida — contada com o fator de referência, nenhum ganho reivindicado",
                      "Depositar a DAP (EN 15804 — DAPHabitat / EPD) do produto aplicado", "materiau", ln["id"])
                if ln.get("typologie") not in (None, "", "Standard") and q > 0:
                    _ctrl(mine, "alerte", "MAT-10", f"{nom} : tipologia « {ln.get('typologie')} » declarada sem DAP que a comprove",
                          "Fornecer a DAP / ficha de reutilização, ou voltar a pôr a linha em « Standard »", "materiau", ln["id"])
            else:
                lo, hi = f.get("plage", (None, None))
                if lo is not None and not (lo <= fe_fdes <= hi):
                    _ctrl(mine, "bloquant", "MAT-04",
                          f"{nom} : FE da DAP {fe_fdes:g} kgCO2e/{ln.get('unite')} fora do intervalo verosímil ({lo:g} a {hi:g}) — provável erro de unidade",
                          "Verificar a unidade declarada da DAP (kg, t, m², m³…) e o valor « alterações climáticas — total »", "materiau", ln["id"])
                if fe_ref is not None and fe_fdes > fe_ref:
                    _ctrl(mine, "alerte", "MAT-05", f"{nom} : a DAP ({fe_fdes:g}) tem mais carbono do que a referência ({fe_ref:g}) — sem ganho",
                          "Propor uma variante de baixo carbono ou justificar a escolha", "materiau", ln["id"])
                if ln.get("fdes_unite") and R.facteur_unite(ln["fdes_unite"], ln.get("unite")) is None and R.unite(ln["fdes_unite"]) != R.unite(ln.get("unite")):
                    _ctrl(mine, "bloquant", "MAT-07", f"{nom} : unidade da DAP ({ln['fdes_unite']}) incompatível com a linha ({ln.get('unite')})",
                          "Converter com a massa volúmica / superficial declarada na DAP", "materiau", ln["id"])
                dv = _date(ln.get("fdes_validite"))
                if dv and dv < today:
                    _ctrl(mine, "alerte", "MAT-06", f"{nom} : DAP expirada desde {dv.strftime('%d/%m/%Y')}",
                          "Pedir ao fabricante a DAP em vigor", "materiau", ln["id"])
                if not ln.get("ref_fdes"):
                    _ctrl(mine, "manquant", "MAT-11", f"{nom} : referência da DAP (n.º de registo) não indicada",
                          "Indicar o n.º de registo ou o nome exato da declaração", "materiau", ln["id"])
            if qp and ql is not None and ql > 0 and abs(ql - qp) / qp > R.ECART_LIVRAISON:
                _ctrl(mine, "alerte", "MAT-08",
                      f"{nom} : quantidade entregue {ql:g} {ln.get('unite')} ≠ prevista {qp:g} ({(ql - qp) / qp:+.0%}) — acima de ±{R.ECART_LIVRAISON:.0%}",
                      "Verificar as guias de remessa (duplicado, entrega parcial) ou atualizar a medição", "materiau", ln["id"])
            if f.get("lourd") and q > 0:
                dist = _num(ln.get("distance_km"))
                if dist is None:
                    _ctrl(mine, "manquant", "MAT-09", f"{nom} : distância de abastecimento desconhecida (material pesado)",
                          "Depositar a guia de remessa (local de carga) ou introduzir a distância", "materiau", ln["id"])
            for pid in ln.get("pieces") or []:
                if pid not in docs:
                    _ctrl(mine, "info", "DOC-03", f"{nom} : documento {pid} não encontrado (apagado)", "", "materiau", ln["id"])
        r["controles"] = mine
        ctrl += mine
        lignes.append(r)

    tot_ref = sum(x["poids_ref"] for x in lignes)
    tot_reel = sum(x["poids_reel"] for x in lignes)
    par_lot = {lot: {"ref": 0.0, "reel": 0.0, "gain": 0.0} for lot in R.LOTS}
    for x in lignes:
        b = par_lot.setdefault(x.get("lot") or "Autre", {"ref": 0.0, "reel": 0.0, "gain": 0.0})
        b["ref"] += x["poids_ref"]
        b["reel"] += x["poids_reel"]
        b["gain"] += x["gain"]

    # ------------------------------------------------------------------ émissions chantier
    em = []
    for e in d.get("emissions") or []:
        q, fe = _num(e.get("quantite")) or 0.0, _num(e.get("fe")) or 0.0
        em.append(dict(e, quantite=q, total=round(q * fe, 2)))
    tot_chantier = sum(e["total"] for e in em)
    if not any(e["quantite"] > 0 for e in em):
        _ctrl(ctrl, "manquant", "EMI-01", "Nenhum consumo da fase de obra introduzido (combustíveis, eletricidade, água, transportes, resíduos)",
              "Depositar as faturas de gasóleo / HVO, leituras de contadores e e-GAR, ou introduzir as quantidades", "emissions")
    emv = {e["id"]: e["quantite"] for e in em}

    # ------------------------------------------------------------------ RE2020
    sref = _num(pj.get("sref_m2"))
    seuil = _num(pj.get("seuil_ic"))
    seuil_src = "Meta introduzida (dono de obra / caderno de encargos)" if seuil is not None else ""
    if seuil is None:
        seuil = R.seuil_ic(pj.get("typologie", ""), pj.get("jalon", ""))
        seuil_src = R.SOURCE_RE2020 if seuil is not None else ""
    total = tot_reel + tot_chantier
    ic_ref = tot_ref / sref if sref else None
    ic_reel = total / sref if sref else None
    if not sref:
        _ctrl(ctrl, "bloquant", "PRJ-01", "Área de referência não indicada : rácios por m² impossíveis", "Introduzir a área útil de referência em m²", "projet")
    if seuil is None:
        _ctrl(ctrl, "manquant", "PRJ-02", "Meta de carbono (kgCO2e/m²) não definida : em Portugal não há valor-limite legal — a meta vem do dono de obra",
              "Introduzir a meta definida no caderno de encargos / pelo dono de obra", "projet")
    conforme = None
    sans_fe = [x for x in lignes if x["actif"] and x["quantite"] > 0 and x.get("fe_ref") is None and x.get("fe_fdes") is None]
    if ic_reel is not None and not any(x["actif"] and x["quantite"] > 0 for x in lignes):
        _ctrl(ctrl, "manquant", "MAT-00", "Nenhuma quantidade de material introduzida : balanço impossível de avaliar",
              "Introduzir as quantidades da medição, importar o estudo ou depositar as guias de remessa", "materiau")
    elif sans_fe and ic_reel is not None:
        _ctrl(ctrl, "manquant", "RE-02", f"Balanço incompleto : {len(sans_fe)} família(s) sem fator de emissão ({', '.join(x['famille'] for x in sans_fe[:6])}"
              f"{'…' if len(sans_fe) > 6 else ''}) — conformidade com a meta impossível de avaliar",
              "Depositar as DAP destas famílias ou introduzir o dado genérico", "projet")
    elif ic_reel is not None and seuil is not None:
        conforme = ic_reel <= seuil
        if not conforme:
            _ctrl(ctrl, "alerte", "RE-01", f"Rácio real {ic_reel:,.0f} kgCO2e/m² > meta {seuil:,.0f} kgCO2e/m²".replace(",", " "),
                  "Priorizar os capítulos mais emissores (separador Síntese) e as variantes de baixo carbono", "projet")

    # ------------------------------------------------------------------ KPI calculés
    actifs = [x for x in lignes if x["actif"] and x["quantite"] > 0 and x.get("fe_ref") is not None]
    base = sum(x["poids_ref"] for x in actifs)
    prouve = lambda x: x.get("fe_fdes") is not None or bool(x.get("pieces"))   # noqa: E731
    kpi = {}
    if base > 0:
        kpi["part_bas_carbone"] = round(100 * sum(x["poids_ref"] for x in actifs if x.get("typologie") not in ("", None, "Standard") and prouve(x)) / base, 1)
        kpi["part_reemploi"] = round(100 * sum(x["poids_ref"] for x in actifs if x.get("typologie") == "Reutilização" and prouve(x)) / base, 1)
    lourds = []
    for x in lignes:
        f = R.FAMILLE.get(x.get("code") or "", {})
        dist = _num(x.get("distance_km"))
        if f.get("lourd") and x["quantite"] > 0 and dist is not None:
            t = x["quantite"] * f["densite_t"] if f.get("densite_t") else None
            lourds.append((dist, t if t else 1.0))
    if lourds:
        kpi["distance_lourds"] = round(sum(a * w for a, w in lourds) / sum(w for _, w in lourds), 1)
    fuel = emv.get("gnr", 0) + emv.get("hvo", 0) + emv.get("engins_elec", 0) / 10.0       # 1 L de GNR ≈ 10 kWh
    if fuel > 0:
        kpi["part_engins_bas_carbone"] = round(100 * (emv.get("hvo", 0) + emv.get("engins_elec", 0) / 10.0) / fuel, 1)
    dch = d.get("dechets") or {}
    dt, dv_ = _num(dch.get("total_t")), _num(dch.get("valorise_t"))
    if dt:
        kpi["taux_valorisation"] = round(100 * (dv_ or 0) / dt, 1)
        if dv_ is not None and dv_ > dt:
            _ctrl(ctrl, "bloquant", "DEC-01", f"Resíduos : tonelagem valorizada ({dv_:g} t) superior ao total ({dt:g} t)", "Verificar as e-GAR", "dechets")

    # ------------------------------------------------------------------ charte
    charte = []
    for c in d.get("charte") or []:
        realise = _num(c.get("realise"))
        auto = c.get("auto")
        src = "introduzido"
        if realise is None and auto and auto in kpi:
            realise, src = kpi[auto], "calculado ConstruPilot"
        cible = _num(c.get("cible"))
        if c.get("statut_force"):
            st = c["statut_force"]
        elif realise is None:
            st = "Em curso" if c.get("pieces") else "A iniciar"
        else:
            st = "Conforme" if cible is None or _ok(c.get("op", ">="), realise, cible) else "Não conforme"
        r = dict(c, realise=realise, source_realise=src if realise is not None else "", statut=st)
        sym = "≥" if c.get("op") == ">=" else "≤"
        if st == "Não conforme":
            _ctrl(ctrl, "alerte", "CHA-01", f"Carta — {c.get('kpi')} : {realise:g} {c.get('unite')} para um objetivo {sym} {cible:g} {c.get('unite')}",
                  c.get("action", ""), "charte", c.get("id"))
        elif st in ("A iniciar", "Em curso") and realise is None:
            _ctrl(ctrl, "manquant", "CHA-02", f"Carta — {c.get('kpi')} : valor realizado não indicado (prova esperada : {c.get('preuve')})",
                  f"Depositar : {c.get('preuve')}", "charte", c.get("id"))
        if st == "Conforme" and not c.get("pieces") and src == "introduzido" and not c.get("statut_force"):
            _ctrl(ctrl, "info", "CHA-03", f"Carta — {c.get('kpi')} : conforme mas sem documento justificativo",
                  f"Juntar : {c.get('preuve')}", "charte", c.get("id"))
        charte.append(r)
    # distance par ligne au-delà de l'imperatif c03
    c03 = next((c for c in charte if c.get("id") == "c03"), None)
    if c03 and _num(c03.get("cible")) is not None:
        lim = _num(c03["cible"])
        for x in lignes:
            dist = _num(x.get("distance_km"))
            if R.FAMILLE.get(x.get("code") or "", {}).get("lourd") and x["quantite"] > 0 and dist is not None and dist > lim:
                m = {"niveau": "alerte", "code": "MAT-12", "message": f"{x.get('famille')} : abastecimento a {dist:g} km > {lim:g} km (circuito curto)",
                     "action": "Procurar um fornecedor mais próximo ou justificar", "cible": "materiau", "ref": x["id"]}
                x["controles"].append(m)
                ctrl.append(m)

    if c03 and _num(c03.get("cible")) is not None:              # chaque livraison au-delà de la distance-cible, même si la moyenne passe
        lim = _num(c03["cible"])
        for doc in docs.values():
            dd = _num((doc.get("extrait") or {}).get("distance_km"))
            if doc.get("type") == "bon_livraison" and doc.get("rattache_a") and dd is not None and dd > lim:
                _ctrl(ctrl, "alerte", "MAT-13", f"Guia « {doc.get('nom')} » : entrega a {dd:g} km > {lim:g} km (circuito curto)", "Justificar este fornecedor ou escolher um mais próximo", "document", doc.get("doc_id"))

    # ------------------------------------------------------------------ documents
    for doc in docs.values():
        if doc.get("statut") == "ilegivel":
            _ctrl(ctrl, "manquant", "DOC-01", f"Documento « {doc.get('nom')} » ilegível", "Depositar um PDF com texto ou uma fotografia nítida", "document", doc.get("doc_id"))
        elif not doc.get("rattache_a"):
            _ctrl(ctrl, "manquant", "DOC-02", f"Documento « {doc.get('nom')} » ({doc.get('type_libelle') or doc.get('type')}) não associado a uma linha",
                  "Escolher a linha do quadro correspondente", "document", doc.get("doc_id"))

    statuts = {s: sum(1 for c in charte if c["statut"] == s) for s in R.STATUTS}
    ctrl.sort(key=lambda c: NIVEAUX.index(c["niveau"]))
    compte = {n: sum(1 for c in ctrl if c["niveau"] == n) for n in NIVEAUX}
    n_actifs = sum(1 for x in lignes if x["actif"] and x["quantite"] > 0)
    n_fdes = sum(1 for x in lignes if x["actif"] and x["quantite"] > 0 and x.get("fe_fdes") is not None)
    return {
        "projet": dict(pj, seuil_ic=seuil, seuil_source=seuil_src),
        "materiaux": lignes,
        "emissions": em,
        "charte": charte,
        "kpi": kpi,
        "par_lot": {k: {kk: round(vv, 2) for kk, vv in v.items()} for k, v in par_lot.items()},
        "totaux": {"materiaux_ref": round(tot_ref, 2), "materiaux_reel": round(tot_reel, 2), "chantier": round(tot_chantier, 2),
                   "total_reel": round(total, 2), "gain": round(tot_ref - tot_reel, 2),
                   "reduction": round((tot_ref - tot_reel) / tot_ref, 4) if tot_ref > 0 else 0.0,
                   "ic_ref": round(ic_ref, 1) if ic_ref is not None else None, "ic_reel": round(ic_reel, 1) if ic_reel is not None else None,
                   "seuil": seuil, "conforme": conforme},
        "statuts_charte": statuts,
        "completude": {"lignes": n_actifs, "avec_fdes": n_fdes, "taux_fdes": round(n_fdes / n_actifs, 3) if n_actifs else 0.0},
        "controles": ctrl,
        "compte_controles": compte,
        "documents": list(docs.values()),
        "decisions": d.get("decisions") or [],
    }
