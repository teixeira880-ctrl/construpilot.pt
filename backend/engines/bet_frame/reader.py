"""Lecture IA des plans d'un bâtiment à ossature (immeuble, bureaux, parking, ERP) → FrameModel JSON, puis contrôles
déterministes et boucle de correction. Détection du type de bâtiment (maison / ossature / génie civil)."""
from __future__ import annotations

import json
import re
from pathlib import Path

from engines.bet_core import reader as R

from . import model, pipeline
from .lang import _, use_lang

EXAMPLE = Path(__file__).with_name("cases") / "immeuble_demo_pt.json"

KIND_RX = {
    "civil": r"\b(ponte|viaduto|pont\b|viaduc|ouvrage d'art|passage inf[ée]rieur|passagem inferior|muro de suporte|mur de sout[eè]nement|"
             r"pal[ée]planche|estacas? de conten|parede moldada|paroi moul[ée]e|VRD\b|voirie|arruamento|pavimenta[cç][aã]o|"
             r"assainissement collectif|rede de saneamento|ETAR|station d'[ée]puration|barragem|barrage|reservat[oó]rio|ch[aâ]teau d'eau|t[uú]nel|tunnel)",
    "frame": r"(fra[cç][aã]o|fra[cç][oõ]es|habita[cç][aã]o (colectiva|coletiva|multifamiliar|plurifamiliar)|edif[ií]cio de habita|piso tipo|"
             r"logements? collectifs?|immeuble|b[aâ]timent collectif|appartements?|\bR ?\+ ?[2-9]\b|r[ée]sidence|cave de estacionamento|"
             r"lugares de estacionamento|parque de estacionamento|parking|garagem colectiva|garagem coletiva|bureaux|escrit[oó]rios|"
             r"pavilh[aã]o|armaz[eé]m|hangar|entrep[oô]t|b[aâ]timent d'activit|nave industrial|[ée]cole|escola|gin[aá]sio|gymnase|"
             r"lyc[ée]e|coll[eè]ge|creche|cr[eè]che|h[oô]pital|centro de sa[uú]de|ERP\b|equipamento p[uú]blico|mairie|c[aâ]mara municipal|"
             r"centre commercial|centro comercial|h[oô]tel|lar de idosos|EHPAD|planta de (cofragem|estrutura|funda[cç][oõ]es)|"
             r"plan de coffrage)",
    "maison": r"(maison individuelle|PCMI|moradia (unifamiliar|isolada|geminada|em banda)?|habita[cç][aã]o unifamiliar|pavillon individuel|villa\b|T[1-6] individuel)",
}

CLASSIFY_SYS = ("Tu classes des plans de bâtiment. Réponds UNIQUEMENT par un JSON {\"kind\": \"maison\"|\"frame\"|\"civil\"|\"other\", "
                "\"building_type\": \"immeuble_collectif\"|\"bureaux\"|\"garage\"|\"hangar\"|\"public\"|\"maison\"|\"civil\"|\"other\", \"reason\": \"…\"}. "
                "maison = maison individuelle / moradia (un seul logement, maçonnerie porteuse possible). "
                "frame = bâtiment sur trame de poteaux BA : immeuble collectif (plusieurs fractions / logements), bureaux, commerce, parking, "
                "bâtiment d'activité, école, équipement public. civil = génie civil (pont, mur de soutènement isolé, voirie, réseaux, ouvrage hydraulique). "
                "other = rien de lisible.")


def _doc_text(docs) -> str:
    txt = ""
    for _n, data in docs:
        try:
            for p in R.pages_of(data, _n)[:30]:
                txt += " " + p["text"][:4000]
        except Exception:  # noqa: BLE001 — document illisible : on se rabat sur l'IA
            continue
    return txt


def _scanned(docs) -> bool:
    """Plans scannés : la majorité des pages n'a aucune couche texte."""
    n = empty = 0
    for _n, data in docs:
        try:
            for p in R.pages_of(data, _n)[:30]:
                n += 1
                empty += len(p["text"].strip()) < 15
        except Exception:  # noqa: BLE001
            continue
    return n > 0 and empty * 2 > n


def detect_text(docs: list[tuple[str, bytes]], hypotheses: str = "", doc_text: str | None = None) -> str | None:
    """Type par mots-clés (texte vectoriel + noms de fichiers + demande). None si indécidable."""
    txt = hypotheses + " " + " ".join(n for n, _ in docs) + " " + (doc_text if doc_text is not None else _doc_text(docs))
    hits = {k: len(re.findall(rx, txt, flags=re.I)) for k, rx in KIND_RX.items()}
    if hits["civil"] >= 2 and hits["civil"] > hits["frame"] + hits["maison"]:
        return "civil"
    if hits["frame"] >= 2 and hits["frame"] >= 2 * hits["maison"]:
        return "frame"
    if hits["maison"] >= 1 and hits["frame"] == 0:
        return "maison"
    return None


async def detect(docs, hypotheses: str = "", llm=None) -> dict:
    """{kind, building_type, source}. Mots-clés d'abord ; plans vectoriels sans mot-clé → maison (chaîne historique) ;
    plans scannés (sans texte) → lecture IA rapide de 2 pages."""
    dt = _doc_text(docs)
    k = detect_text(docs, hypotheses, dt)
    if k:
        return {"kind": k, "building_type": {"frame": "immeuble_collectif", "maison": "maison", "civil": "civil"}[k], "source": "texte"}
    if not _scanned(docs):
        return {"kind": "maison", "building_type": "maison", "source": "défaut"}
    llm = llm or R._default_llm
    imgs = []
    for n, data in docs:
        try:
            for p in R.pages_of(data, n)[:2]:
                imgs.append(R.render_png(data, p["page"], 1100))
        except Exception:  # noqa: BLE001
            continue
        if len(imgs) >= 3:
            break
    if not imgs:
        return {"kind": "maison", "building_type": "maison", "source": "défaut"}
    try:
        txt = await llm(CLASSIFY_SYS, "Demande du client : " + (hypotheses or "—") + "\nClasse ce bâtiment.", images=imgs, max_tokens=300)
        d = R._extract_json(txt)
        kind = d.get("kind") if d.get("kind") in ("maison", "frame", "civil", "other") else "maison"
        return {"kind": "maison" if kind == "other" else kind, "building_type": d.get("building_type") or kind, "source": "ia", "reason": d.get("reason")}
    except Exception:  # noqa: BLE001 — classification impossible : chaîne maison historique
        return {"kind": "maison", "building_type": "maison", "source": "défaut"}


SYSTEM = """Tu es le dessinateur-projeteur d'un bureau d'études structure. Tu relèves, sur les plans d'architecte et/ou de structure joints,
le MODÈLE D'OSSATURE d'un bâtiment sur trame de poteaux béton armé (immeuble collectif, bureaux, commerce, parking, équipement public).
Tu ne calcules RIEN : le code calcule. Tu relèves la géométrie et tu traces chaque hypothèse.

Règles :
1. Repère : x le long de la plus grande dimension du bâtiment, y le long de la petite ; origine au coin bas-gauche de l'emprise ; mètres.
2. grid.x / grid.y = abscisses des FILES DE POTEAUX (axes). Si un plan de coffrage / structure est joint, recopie ses axes et ses cotes.
   Sinon, propose une trame réaliste : files sur les façades et sur les murs structurants (cages d'escalier, murs mitoyens entre logements),
   portées de 4,5 à 7,0 m, alignées sur les cotes des plans ; écris la décision dans "_decisions".
3. levels : du plus bas au plus haut, floor_top = cote du dessus de dalle (m, R/C ou RDC = 0,00 si non coté), height = hauteur d'étage
   (dalle à dalle). Un niveau enterré (cave, sous-sol, parking) a on_grade = true. use ∈ habitation, bureaux, commerce, scolaire, public,
   stationnement, technique. roof.use = toiture (inaccessible) ou terrasse (accessible).
4. structure : sections indiquées sur les plans sinon column [0.30, 0.30], beam [0.30, 0.50], slab 0.20 ; concrete C25/30 ; columns_omit
   = intersections de la trame SANS poteau (ex. [["3","B"]]).
5. cores : cages d'escalier / ascenseur (rectangle extérieur des voiles, wall = épaisseur).
4 ter. GÉOMÉTRIE RÉELLE — les plans cotés produits en dépendent, aucune valeur estimée ou arrondie :
   "geometry": {"overall": {"length": cote extérieure totale en x (m), "width": en y, "facade_to_axis": distance nu de façade → axe
   des files de rive (m, souvent 0,15), "source": "planche + cote lue, ex. Planta Piso 1, cota 26,40"}}. Recopie les cotes écrites sur
   les planches (chaînes de cotes) ; les files de poteaux tombent sur des murs / cotes réelles du plan, jamais une trame régulière inventée.
   units[].area_declared = surface du quadro de áreas / tableau des surfaces de l'architecte quand il existe ; le rectangle de la fraction
   doit la respecter (limites = murs séparatifs et palier). Deux fractions d'un même piso ne se chevauchent jamais.
   NIVEAUX D'EMPRISES DIFFÉRENTES : si la cave / le sous-sol déborde des étages (garage, pátio, zona técnica) ou si un étage est en
   retrait, la trame couvre le PLUS GRAND niveau et chaque niveau plus petit liste ses cases absentes dans levels[].void_cells.
   ÉTAGE COURANT : une planta « Piso 1 » dont les fractions portent « Fr. E/I/N/R » représente 4 pisos identiques (E au Piso 1,
   I au Piso 2, N au Piso 3, R au Piso 4) : crée ces 4 niveaux et l'unité avec levels = les 4 pisos (même règle pour « E - N »).
   INTERDIT : recalculer, ajuster ou « déduire » les dimensions du bâtiment, la trame ou le nombre de niveaux à partir du quadro de
   áreas ou pour faire coïncider des surfaces. Le bâtiment est celui DESSINÉ ; un écart de surface se signale dans "_questions".
4 bis. EMPRISE RÉELLE : la trame est le rectangle englobant ; si le bâtiment n'est PAS rectangulaire (forme en L, en U, en T,
   décrochements, cour ou patio), liste dans structure.void_cells les cases de trame SANS plancher, chacune repérée par la file x à
   sa gauche et la file y en dessous (ex. [["5","C"], ["6","C"]] = cases entre les files 5-6 et 6-7, au-dessus de la file C). Les
   poteaux qui ne touchent aucune case pleine sont supprimés automatiquement. Ne laisse JAMAIS une partie hors bâtiment en case
   pleine : les plans, les charges et les métrés en dépendent.
6. balconies : balcons en console (side N/S/E/W, depth, a0/a1 = début/fin le long de la façade depuis l'origine, levels).
7. units : chaque fraction / logement / lot par niveau (rectangle englobant x0,y0,x1,y1 dans le repère ; name ; typology T0…T5 ou
   « commerce », « bureau » ; levels = liste des niveaux où il se répète à l'identique ; fixtures = appareils sanitaires comptés sur le plan :
   wc, lavatorio, duche, banheira, bide, pia, mlr, mll ; rooms = compartiments relevés sur le plan d'architecte, chacun
   {type, name, x0, y0, x1, y1} dans le repère du bâtiment, type ∈ sala, quarto, cozinha, instalacao_sanitaria, hall, corredor,
   lavandaria, arrumos — relève-les dès que la planta les montre, ils servent aux plans d'électricité et de plomberie de chaque logement).
8. risers : colonnes montantes et chutes (kind AF eau froide, ECS eau chaude collective, EU chute eaux usées, EP eaux pluviales,
   ELEC colonne électrique, VENT ventilation, GAZ), position x,y dans le repère (gaines techniques, courettes). S'il n'y en a pas sur les
   plans : une chute EU près des pièces d'eau de chaque fraction et une colonne AF + une colonne ELEC dans le noyau, en _decisions.
9. geotech : sigma_adm_mpa, depth (assise), source — depuis l'étude de sol jointe ; sinon laisse null (le code prendra une valeur prudente).
10. project : name, address, country (FR ou PT), architect, pc_ref (référence des plans), g2_ref.
10 bis. LANGUE : tous les noms (niveaux, fractions, noyaux, pièces) s'écrivent dans la langue du PAYS du projet (PT → português :
   « Piso 0 — habitação e cobertura das caves », « Fração A — noroeste », « Caixa de escada » ; FR → français), jamais un mélange.
   Les textes "_decisions" et "_questions" aussi : PT → português europeu (« Fundações diretas supostas a 1 m »), jamais en français.
   Une fraction répétée sur plusieurs pisos (un seul objet avec "levels") : "name" liste les fractions dans l'ordre des pisos,
   du plus bas au plus haut (« Frações E, I, N, R » = E au Piso 1, I au Piso 2…).
11. "_questions" : uniquement ce qui est indispensable et illisible. "_decisions" : chaque hypothèse que tu as prise.
Réponds par le JSON complet seul, sans texte autour."""

DECIDE = ("\n\nMODE DÉCIDER SEUL : ne pose AUCUNE question (\"_questions\": []) ; tranche l'hypothèse la plus probable pour chaque point "
          "et écris-la dans \"_decisions\".")


_FR_WORDS = re.compile(r"\b(les|des|du|aux|selon|d'après|supposée?s?|déduite?s?|étages?|logements?|sous-sol|absence|chauffage|fondations)\b", re.I)


async def _to_pt(items: list[str], llm) -> list[str]:
    """Hypothèses rédigées en français par le lecteur sur un projet PT → português europeu (repli : texte d'origine)."""
    try:
        txt = await llm("Traduz para português europeu técnico (engenharia civil, Portugal). Mantém números, unidades e siglas. "
                        "Responde só com o JSON {\"t\": [strings na mesma ordem]}.", json.dumps(items, ensure_ascii=False), max_tokens=2000)
        out = json.loads(txt[txt.index("{"): txt.rindex("}") + 1]).get("t")
        if isinstance(out, list) and len(out) == len(items):
            return [str(x) for x in out]
    except Exception:  # noqa: BLE001
        pass
    return items


MAX_TOTAL_IMAGES = 20

COTES_SYS = """Tu es métreur. Sur les planches jointes (plans d'architecte), tu TRANSCRIS les cotes écrites, sans rien calculer ni
déduire. Réponds en JSON seul : {"overall": {"length": cote extérieure totale la plus grande du bâtiment en m, "width": cote extérieure
totale perpendiculaire en m, "where": "planche + emplacement de la cote"}, "cotes": [toutes les cotes lues, en mètres],
"levels": nombre de niveaux dessinés (caves comprises), "per_level": [{"level": "nom de la planta (ex. Piso -1)", "length": cote extérieure
la plus grande de CE niveau en m, "width": perpendiculaire en m}] (une entrée par planta, murs extérieurs, balcons exclus), "units_per_level": {"nom du niveau": nombre de fractions}}.
Si une cote totale n'est pas écrite, additionne la chaîne de cotes extérieure écrite et dis-le dans "where" ; si illisible : null."""


async def _read_cotes(images: list, llm) -> dict:
    """Lecture indépendante des cotes (appel séparé, sans le modèle d'ossature) : sert de témoin contre un relevé fabriqué."""
    try:
        txt = await llm(COTES_SYS, "Transcris les cotes de ces planches.", images=images, max_tokens=3000)
        d = R._extract_json(txt)
        out = {"overall": d.get("overall") or {}, "cotes": [], "levels": d.get("levels"), "units_per_level": d.get("units_per_level"),
               "per_level": [x for x in d.get("per_level") or [] if isinstance(x, dict)]}
        for v in d.get("cotes") or []:
            try:
                out["cotes"].append(float(str(v).replace(",", ".")))
            except ValueError:
                continue
        for k in ("length", "width"):
            v = out["overall"].get(k)
            try:
                out["overall"][k] = float(str(v).replace(",", ".")) if v is not None else None
            except ValueError:
                out["overall"][k] = None
        return out
    except Exception:  # noqa: BLE001 — témoin facultatif
        return {}


async def read_frame(docs: list[tuple[str, bytes]], hypotheses: str = "", country: str = "FR", llm=None, decide_alone: bool = False,
                     building_type: str = "immeuble_collectif", max_fix: int = 2) -> dict:
    llm = llm or R._default_llm
    pages, by_doc = [], {}
    for name, data in docs:
        by_doc[name] = data
        pages += R.pages_of(data, name)
    g2 = "\n".join(p["text"] for p in pages if p["kind"] == "g2")[:30000]
    chosen = R.select_pages(pages) or [p for p in pages if p["kind"] != "g2"][:R.MAX_IMAGES]
    if not chosen:
        return {"ok": False, "model": None, "anomalies": [], "pages": [], "attempts": 0, "decisions": [],
                "questions": [_("Aucun plan lisible dans les documents joints : joignez les plans de niveaux, coupes et façades en PDF.",
                                "Nenhuma planta legível nos documentos: junte as plantas dos pisos, cortes e alçados em PDF.")]}
    images = [R.render_png(by_doc[p["doc"]], p["page"]) for p in chosen]
    # grandes planches (A1/A0) : agrandissements du bâtiment, sinon les cotes sont illisibles et l'IA invente la géométrie
    from .zoom import zooms
    zl = []
    for p in chosen:
        if len(images) + len(zl) >= MAX_TOTAL_IMAGES:
            break
        try:
            z = zooms(by_doc[p["doc"]], p["page"])
        except Exception:  # noqa: BLE001 — agrandissement facultatif
            z = []
        z = z[:MAX_TOTAL_IMAGES - len(images) - len(zl)]
        zl += [(p, i, im) for i, im in enumerate(z)]
    images += [im for _p, _i, im in zl]
    zoom_legend = "".join(f"\n\nImage {len(chosen) + n + 1} : AGRANDISSEMENT de {p['doc']} p.{p['page']} — "
                          + ("bâtiment entier" if i == 0 else f"moitié {i}") + " (cotes lisibles : lis-les ici)."
                          for n, (p, i, _im) in enumerate(zl))
    ref = await _read_cotes(images, llm)
    ref_txt = ""
    if (ref.get("overall") or {}).get("length"):
        ov = ref["overall"]
        ref_txt = (f"\n\nCOTES EXTÉRIEURES LUES SUR LES PLANCHES (lecture indépendante) : {ov.get('length')} × {ov.get('width')} m "
                   f"({ov.get('where') or '?'}). La trame et l'emprise doivent les respecter.")
    legend = "\n\n".join(f"Image {i + 1} : {p['doc']} p.{p['page']} ({p['kind']}, feuille {p['size_mm'][0]}×{p['size_mm'][1]} mm). "
                         f"Texte vectoriel (mot@x,y mm ; cotes fiables) : {p['words'] or '(plan scanné — lire l image)'}" for i, p in enumerate(chosen)) + zoom_legend
    base = (f"EXEMPLE DE FrameModel (autre bâtiment, même schéma — ne recopie pas ses valeurs) :\n{EXAMPLE.read_text(encoding='utf-8')}\n\n"
            f"TYPE DE BÂTIMENT : {building_type}\nPAYS : {country}\nDEMANDE / HYPOTHÈSES DU CLIENT (prioritaires) : {hypotheses or 'aucune'}\n\n"
            f"PLANCHES JOINTES :\n{legend}\n\nÉTUDE DE SOL (texte extrait) :\n{g2 or 'AUCUNE'}" + ref_txt + "\n\nProduis le FrameModel JSON de CE bâtiment."
            + (DECIDE if decide_alone else ""))
    lang = "pt" if country == "PT" else "fr"
    txt = await llm(SYSTEM, base, images=images, max_tokens=R.MAX_OUT)
    attempts, raw, anomalies = 1, None, []
    while True:
        try:
            raw = R._extract_json(txt)
            raw["kind"] = "frame"
            raw.setdefault("building_type", building_type)
            raw.setdefault("project", {}).setdefault("country", country)
            with use_lang(lang):
                m, anomalies = pipeline.validate(raw, pages=chosen, strict=True, ref=ref)
                if attempts > max_fix:        # dernière lecture : cotes introuvables / trame idéalisée → avertissement mémorisé
                    soft = [dict(x, level=model.WARN) for x in anomalies if x.get("code") in ("GEO-02", "GEO-03")]
                    anomalies = [x for x in anomalies if x.get("code") not in ("GEO-02", "GEO-03")] + soft
                    raw["_geo_warnings"] = soft
            if m is not None and not model.has_block(anomalies):
                calc_err = pipeline.dry_run(raw, lang)
                if calc_err:
                    anomalies = anomalies + [calc_err]
        except Exception as exc:  # noqa: BLE001
            anomalies = [{"code": "JSON", "level": model.BLOCK, "message": f"JSON illisible : {exc}"}]
        blocking = [a for a in anomalies if a.get("level") == model.BLOCK]
        if not blocking or attempts > max_fix:
            break
        fix = (base + "\n\nTON RELEVÉ PRÉCÉDENT :\n" + (json.dumps(raw, ensure_ascii=False) if raw else txt[:20000]) +
               "\n\nCONTRÔLES DÉTERMINISTES — ANOMALIES BLOQUANTES :\n" +
               "\n".join(f"- {a['code']} : {a['message']} {a.get('fix', '')}" for a in blocking) +
               "\n\nRelis les planches et renvoie le JSON COMPLET corrigé.")
        txt = await llm(SYSTEM, fix, images=images, max_tokens=R.MAX_OUT)
        attempts += 1
    blocking = [a for a in anomalies if a.get("level") == model.BLOCK]
    decisions = [str(d) for d in (raw or {}).get("_decisions") or []]
    if lang == "pt" and decisions and any(_FR_WORDS.search(d) for d in decisions):
        decisions = await _to_pt(decisions, llm)
        if raw is not None:
            raw["_decisions"] = decisions
    questions = [] if decide_alone else list((raw or {}).get("_questions") or []) + [f"{a['message']} — {a.get('fix') or '?'}" for a in blocking]
    if raw is not None and hypotheses:
        raw.setdefault("user_hypotheses", {})["_source"] = hypotheses[:300]
    return {"ok": raw is not None and not blocking, "model": raw, "anomalies": anomalies, "questions": questions, "decisions": decisions,
            "decide_alone": decide_alone, "pages": [{k: p[k] for k in ("doc", "page", "kind")} for p in chosen], "attempts": attempts,
            "provider": R.LAST_PROVIDER[0] if llm is R._default_llm else "custom", "extraction": {}}
