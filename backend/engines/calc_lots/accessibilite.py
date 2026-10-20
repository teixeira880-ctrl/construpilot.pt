"""Accessibilité PMR — vérification indicative d'un projet (France : arrêtés du 24/12/2015 logements et du 20/04/2017 ERP neufs ;
Portugal : Decreto-Lei 163/2006, normas técnicas).

Chaque mesure fournie est comparée à l'exigence du contexte (logement collectif, maison individuelle, ERP, Portugal). Les mesures non fournies
ne sont pas vérifiées. Pentes de rampe : FR ≤ 5 % (8 % sur ≤ 2 m, 10 % sur ≤ 0,50 m), PT ≤ 6 % jusqu'à 10 m / ≤ 8 % jusqu'à 5 m (interpolation).
Valeurs reprises de sources secondaires pour une partie du logement (notes DDT/CAUE) et du DL 163/2006 (sections 4.8/4.9) : signalées.
"""
from __future__ import annotations

CONTEXTES = ("fr_logement_collectif", "fr_maison_individuelle", "fr_erp", "pt")


def _c(ref, exig, val, ok, note=None):
    return {"ref": ref, "exigence": exig, "valeur": val, "ok": ok, "note": note}


def _rampe_fr(pente, long):
    if pente <= 5 + 1e-9:
        return True, "≤ 5 %"
    if pente <= 8 + 1e-9:
        return long <= 2 + 1e-9, "8 % toléré sur ≤ 2 m"
    if pente <= 10 + 1e-9:
        return long <= 0.5 + 1e-9, "10 % toléré sur ≤ 0,50 m"
    return False, "> 10 % interdit"


def _rampe_pt(pente, long, desnivel):
    if pente > 8 + 1e-9:
        return False, "> 8 % (obra nova)"
    lim_long = 10 - (pente - 6) / 2 * 5 if pente > 6 else 10      # 6 % → 10 m ; 8 % → 5 m (interpolação)
    lim_desn = 0.60 - (pente - 6) / 2 * 0.20 if pente > 6 else 0.60
    return long <= lim_long + 1e-9 and (desnivel is None or desnivel <= lim_desn + 1e-9), f"≤ {pente:.1f} % com projeção ≤ {lim_long:.1f} m e desnível ≤ {lim_desn:.2f} m"


def verifier(p: dict) -> dict:
    ctx = p.get("contexte") or "pt"
    if ctx not in CONTEXTES:
        raise ValueError("contexte : " + ", ".join(CONTEXTES))
    pt = ctx == "pt"
    erp = ctx == "fr_erp"
    m = {k: v for k, v in (p.get("mesures") or {}).items() if v is not None}
    if not m:
        raise ValueError("aucune mesure fournie (largeurs, pentes, portes, escaliers…)")
    ctl, hyp = [], []
    g = lambda k: float(m[k])
    if "largeur_cheminement_m" in m:
        lim = 1.20 if (pt or not erp) else 1.40
        ctl.append(_c("Largeur du cheminement / percurso", f"≥ {lim:.2f} m" + (" (réduction ponctuelle 1,20 m)" if erp else " (0,90 m ponctuellement)" if not pt else " (0,90 m em ≤ 1,50 m)"),
                      f"{g('largeur_cheminement_m'):.2f} m", g("largeur_cheminement_m") >= lim - 1e-9))
    if "pente_rampe_pct" in m:
        L = float(m["longueur_rampe_m"]) if m.get("longueur_rampe_m") is not None else None
        if L is None and (pt or g("pente_rampe_pct") > 5):
            ctl.append(_c("Rampe / rampa", "longueur (ou dénivelé) à fournir pour vérifier la pente", f"{g('pente_rampe_pct'):g} %", None))
            L = -1.0
        if L == -1.0:
            pass
        elif pt:
            ok, txt = _rampe_pt(g("pente_rampe_pct"), L, float(m["desnivel_rampa_m"]) if m.get("desnivel_rampa_m") is not None else None)
            ref = "Rampa (DL 163/2006, 2.5)"
        else:
            ok, txt = _rampe_fr(g("pente_rampe_pct"), L)
            ref = "Pente du cheminement / plan incliné"
        if L != -1.0:
            ctl.append(_c(ref, txt, f"{g('pente_rampe_pct'):g} % sur {L:g} m", ok))
        L = max(L, 0.0)
        if not pt and g("pente_rampe_pct") >= 4 and L > 10:
            ctl.append(_c("Paliers de repos", "tous les 10 m si pente ≥ 4 % (1,20 × 1,40 m)", "à prévoir", None))
        if pt and g("pente_rampe_pct") > 6:
            ctl.append(_c("Corrimãos da rampa", "duplos (0,70–0,75 m e 0,90–0,95 m) dos dois lados se inclinação > 6 %", "a prever", None))
    if "largeur_rampe_m" in m:
        lim = 0.90 if pt and float(m.get("longueur_rampe_m") or 99) <= 5 else 1.40 if erp else 1.20
        ctl.append(_c("Largeur de la rampe", f"≥ {lim:.2f} m" + (" (0,90 m se projeção ≤ 5 m)" if pt else ""), f"{g('largeur_rampe_m'):.2f} m",
                      g("largeur_rampe_m") >= lim - 1e-9))
    if "devers_pct" in m:
        ctl.append(_c("Dévers / inclinação transversal", "≤ 2 %", f"{g('devers_pct'):g} %", g("devers_pct") <= 2 + 1e-9))
    if "ressaut_cm" in m:
        chanf = bool(m.get("ressaut_chanfreine"))
        lim = (5.0 if chanf else 2.0) if pt else (4.0 if chanf else 2.0)
        ctl.append(_c("Ressaut / ressalto", f"≤ {lim:g} cm" + (" chanfreiné à 1/3" if chanf and not pt else " chanfrado ≤ 50 %" if chanf else ""), f"{g('ressaut_cm'):g} cm",
                      g("ressaut_cm") <= lim + 1e-9))
        if pt and chanf:
            hyp.append("ressalto chanfrado ≤ 5 cm: secção 4.8 do DL 163/2006 não confirmada no texto")
    if erp and "porte_entree_utile_m" in m:
        hyp.append("ERP recevant ≥ 100 personnes : porte de 1,40 m dont un vantail de 0,90 m (0,83 m utile) — non vérifié ici")
    if "porte_entree_utile_m" in m:
        lim = 0.87 if pt else 0.83
        ctl.append(_c("Porte d'entrée — passage utile" if not pt else "Porta de entrada — largura útil", f"≥ {lim:.2f} m" + ("" if pt else " (porte de 0,90 m)"),
                      f"{g('porte_entree_utile_m'):.2f} m", g("porte_entree_utile_m") >= lim - 1e-9))
    if "porte_interieure_utile_m" in m:
        ctl.append(_c("Portes intérieures — passage utile" if not pt else "Portas do percurso — largura útil", "≥ 0,77 m (porte de 0,80 m)" if not pt else "≥ 0,77 m",
                      f"{g('porte_interieure_utile_m'):.2f} m", g("porte_interieure_utile_m") >= 0.77 - 1e-9))
        if pt:
            hyp.append("largura útil 0,77 m das portas do percurso: secção 4.9.3 do DL 163/2006 não confirmada no texto")
    if "diametre_rotation_m" in m:
        ctl.append(_c("Aire de rotation / zona de rotação", "Ø ≥ 1,50 m", f"Ø {g('diametre_rotation_m'):.2f} m", g("diametre_rotation_m") >= 1.50 - 1e-9))
    if "circulation_interieure_m" in m:
        lim = 1.10 if pt else 1.40 if erp else 0.90
        ctl.append(_c("Circulations intérieures" + (" (ERP, 1,20 m ponctuellement)" if erp else " du logement") if not pt else "Corredores da habitação", f"≥ {lim:.2f} m", f"{g('circulation_interieure_m'):.2f} m",
                      g("circulation_interieure_m") >= lim - 1e-9))
    if "escalier_hauteur_marche_cm" in m or "escalier_giron_cm" in m or "escalier_largeur_m" in m:
        hmax = 18 if pt else 16 if erp else 17
        lmin = (1.20 if m.get("publico") else 1.00) if pt else 1.20 if erp else 1.00
        if pt and not m.get("publico"):
            hyp.append("escada de habitação (3.3.5): largura ≥ 1,00 m; edifícios públicos (2.4): ≥ 1,20 m — indicar « publico »")
        if ctx == "fr_maison_individuelle" or m.get("escalier_interieur_logement"):
            hmax, lmin, gmin = 18, 0.80, 24
        else:
            gmin = 28
        if "escalier_hauteur_marche_cm" in m:
            ctl.append(_c("Escalier — hauteur de marche", f"≤ {hmax} cm", f"{g('escalier_hauteur_marche_cm'):g} cm", g("escalier_hauteur_marche_cm") <= hmax + 1e-9))
        if "escalier_giron_cm" in m:
            ctl.append(_c("Escalier — giron", f"≥ {gmin} cm", f"{g('escalier_giron_cm'):g} cm", g("escalier_giron_cm") >= gmin - 1e-9))
        if "escalier_largeur_m" in m:
            ctl.append(_c("Escalier — largeur" + (" entre mains courantes" if not pt else ""), f"≥ {lmin:.2f} m", f"{g('escalier_largeur_m'):.2f} m", g("escalier_largeur_m") >= lmin - 1e-9))
        if ctx == "fr_logement_collectif":
            hyp.append("escaliers des parties communes (≤ 17 cm, ≥ 28 cm, 1,00 m) : valeurs de l'arrêté de 2015 reprises de notes DDT / CAUE")
    if "stationnement_largeur_m" in m:
        lim = 3.50 if pt else 3.30
        lg = float(m["stationnement_longueur_m"]) if m.get("stationnement_longueur_m") is not None else None
        ok = g("stationnement_largeur_m") >= lim - 1e-9 and (lg is None or lg >= 5 - 1e-9)
        ctl.append(_c("Place de stationnement adaptée" if not pt else "Lugar de estacionamento", f"largeur ≥ {lim:.2f} m" + (" (2,50 m + faixa 1,00 m)" if pt else " (2,50 + 0,80 m)") + ", longueur ≥ 5,00 m",
                      f"{g('stationnement_largeur_m'):.2f} m" + (f" × {lg:.2f} m" if lg is not None else " (longueur non fournie)"), ok if (lg is not None or not ok) else None))
    if "nb_places_adaptees" in m and "nb_places_total" not in m:
        hyp.append("nombre de places adaptées fourni sans nombre total : quota non vérifié")
    if "nb_places_total" in m and ctx != "fr_maison_individuelle":
        n = int(m["nb_places_total"])
        if pt:
            if m.get("publico") is None:
                hyp.append("estacionamento: tabela da habitação (3.2.6) aplicada — indicar « publico » para edifícios abertos ao público (2.8)")
            if m.get("publico"):
                req = 1 if n <= 10 else 2 if n <= 25 else 3 if n <= 100 else 4 if n <= 500 else 4 + (n - 500 + 99) // 100
            else:     # habitação (3.2.6)
                req = 0 if n < 13 else 1 if n <= 50 else 2 if n <= 200 else 2 + (n - 200 + 99) // 100
        else:
            req = (max(10, -(-n * 2 // 100)) if n > 500 else -(-n * 2 // 100)) if erp else -(-n * 5 // 100)
            if erp and n > 500:
                hyp.append("ERP > 500 places : nombre fixé par arrêté municipal (minimum 10)")
            if ctx == "fr_logement_collectif":
                hyp.append("5 % de places adaptées en logement collectif : valeur non confirmée dans le texte de l'arrêté de 2015")
        ok = int(m["nb_places_adaptees"]) >= req if m.get("nb_places_adaptees") is not None else None
        ctl.append(_c("Nombre de places adaptées", f"≥ {req}", f"{m.get('nb_places_adaptees', 'non indiqué')}", ok))
    if "wc_espace_lateral_m" in m:
        ctl.append(_c("WC — espace d'usage latéral" if not pt else "Instalação sanitária — cabina", "0,80 × 1,30 m" if not pt else "cabina ≥ 1,60 × 1,70 m",
                      f"{m['wc_espace_lateral_m']}", None, "dimensions à vérifier sur plan (largeur × longueur)"))
    if "douche_seuil_cm" in m:
        ctl.append(_c("Douche — ressaut", "≤ 2 cm", f"{g('douche_seuil_cm'):g} cm", g("douche_seuil_cm") <= 2 + 1e-9))
    if "nb_niveaux_au_dessus_rdc" in m and ctx == "fr_logement_collectif":
        n = int(m["nb_niveaux_au_dessus_rdc"])
        asc = m.get("ascenseur")
        ctl.append(_c("Ascenseur (loi ELAN)", "obligatoire dès 3 étages au-dessus du rez-de-chaussée", "prévu" if asc else ("non prévu" if asc is False else "non précisé"),
                      True if (n < 3 or asc) else (False if asc is False else None)))
    if "eclairage_exterieur_lux" in m and not pt:
        ctl.append(_c("Éclairage extérieur / stationnement", "≥ 20 lux", f"{g('eclairage_exterieur_lux'):g} lux", g("eclairage_exterieur_lux") >= 20 - 1e-9))
    if not ctl:
        raise ValueError("aucune mesure reconnue (voir le schéma de l'outil)")
    ref = {"fr_logement_collectif": "arrêté du 24/12/2015 (logements collectifs neufs)", "fr_maison_individuelle": "arrêté du 24/12/2015 (maisons individuelles neuves)",
           "fr_erp": "arrêté du 20/04/2017 (ERP neufs)", "pt": "Decreto-Lei 163/2006 (normas técnicas de acessibilidade)"}[ctx]
    hyp.insert(0, f"référentiel : {ref} — vérification indicative des seules mesures fournies")
    return {"contexte": ctx, "referentiel": ref, "controles": ctl, "hypotheses": hyp, "conforme": (False if any(c["ok"] is False for c in ctl) else None if any(c["ok"] is None for c in ctl) else True)}


def note(p: dict) -> dict:
    from . import notes
    r = verifier(p)
    titre = "Vérification accessibilité PMR" if r["contexte"] != "pt" else "Verificação de acessibilidade"
    blocs = [("p", "Vérification indicative — ne remplace pas l'attestation d'accessibilité / la notice du dossier de permis."), ("controls", r["controles"])]
    pdf, png = notes.pdf(titre, r["referentiel"], blocs, r["hypotheses"])
    return {**r, "titre": titre, "pdf": pdf, "png": png}
