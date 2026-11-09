"""Branchement du moteur ossature dans l'outil Assistant generate_full_bet_study (bet_core.assistant_tool._work).

maybe_handle() décide du moteur selon le bâtiment : maison individuelle → False (chaîne bet_core inchangée) ;
bâtiment à ossature (immeuble, bureaux, parking, ERP…) → étude bet_frame complète ; génie civil → réponse claire « hors périmètre ».
"""
from __future__ import annotations
import re

import asyncio
import copy
import logging
import tempfile
from pathlib import Path

from . import pipeline, reader

log = logging.getLogger(__name__)

INSTRUCTIONS_EXTRA = (
    " TYPES DE BÂTIMENTS : generate_full_bet_study traite la maison individuelle ET les bâtiments à ossature béton armé (immeuble "
    "collectif / edifício de habitação coletiva, bureaux, commerce, parking / garagem, bâtiment d'activité, équipement public) : le type est "
    "détecté automatiquement sur les plans ; pour ces bâtiments le dossier comprend fondations, plans de coffrage de chaque plancher, "
    "tableaux de poteaux / poutres / dalles / semelles, PLANS D'EXÉCUTION DU FERRAILLAGE (élévations cotées des poutres avec barres, "
    "longueurs et cadres ; sections armées des poteaux ; semelles armées en plan et coupe), coupe, plans de niveaux, réseaux, schéma "
    "vertical des colonnes, PLANS PAR LOGEMENT TYPE (électricité : points, circuits numérotés tirés depuis le tableau, schéma unifilaire ; "
    "plomberie : appareils sanitaires cotés, alimentations EF/ECS, évacuations Ø et pentes vers la chute ; ventilation ; plancher chauffant "
    "en FR), NOTE D'ÉTUDE THERMIQUE séparée (PT : estudo de comportamento térmico REH fração a fração — soluções construtivas com U "
    "calculado e Umáx, balanço Nic/Ni, Nvc/Nv, Ntc/Nt, classe, potências ; FR : pré-étude RE2020 du bâtiment — Bbio, Cep, Cep,nr, DH, Ic, "
    "étiquettes DPE — + déperditions et puissances logement par logement) et plans de chauffage / ventilation par niveau. Ne dis donc "
    "jamais que l'étude thermique, les plans électriques, de plomberie ou d'exécution ne sont pas faits : présente-les (champ `thermal` = "
    "classes et puissance totale). Avec generate_bet_lot_plans, le lot « chauffage » donne la note thermique + les plans de chauffage / "
    "ventilation, « electricite » et « plomberie » les plans par logement type, et « gros_oeuvre » inclut le ferraillage d'exécution. "
    "BOIS MASSIF (mise à jour 09/11/2026, prioritaire) : si la structure est en CLT / bois lamellé-croisé / lamellé-collé (maison, "
    "immeuble, poteaux-poutres ou murs CLT), écris « CLT » dans `hypotheses` de generate_full_bet_study : le moteur bois massif "
    "produit la note EN 1995 (CLT, poutres, pannes, poteaux, feu, vibrations, assemblages), le calepinage CLT, les plans de charpente "
    "par niveau, les détails, les tableaux, les fondations BA et le devis ; pays FR, PT ou UA. Pour country=UA, l'étude CLT est désormais "
    "COMPLÈTE (plans, note, devis en anglais + ukrainien) ; les données de site manquantes (S0, W0, sol, séisme) sont prises du côté de "
    "la sécurité et listées comme points à confirmer — dis-le ; ce n'est jamais une approbation réglementaire. "
    "Le génie civil (ponts, murs de soutènement isolés, VRD, réseaux publics, ouvrages hydrauliques) n'est PAS encore couvert : dis-le "
    "clairement et n'improvise pas de calcul. "
    "N'écris JAMAIS un document texte intitulé « Plan », « Planta » ou « Plan de coffrage » : un plan est un dessin produit par "
    "generate_full_bet_study ou generate_bet_lot_plans. draw_section_schema sert UNIQUEMENT aux coupes de principe d'une paroi, d'un "
    "plancher ou d'une toiture (jamais pour des colonnes de plomberie, un réseau ou un bâtiment entier) et ses libellés s'écrivent dans "
    "la langue du projet."
)

LABELS = {"fr": {"pdf": "Dossier d'étude BET — ossature (note de calcul + plans)", "plans_pdf": "Plans PDF (pour les entreprises)",
                 "xlsx": "Devis et métré (Excel)", "zip": "Plans DXF (pour logiciel de DAO)",
                 "re2020_pdf": "Étude thermique — RE2020 et déperditions (note de calcul)"},
          "pt": {"pdf": "Processo de estudo — estrutura (memória de cálculo + desenhos)", "plans_pdf": "Desenhos PDF (para as empresas)",
                 "xlsx": "Medições e orçamento (Excel)", "zip": "Desenhos DXF (para software CAD)",
                 "re2020_pdf": "Estudo térmico — pré-certificado REH por fração (nota de cálculo)"}}

CIVIL_MSG = {"fr": ("Ces documents décrivent un ouvrage de génie civil (pont, soutènement, VRD, réseau ou ouvrage hydraulique) : ce type "
                    "d'ouvrage n'est pas encore couvert par le moteur BET de ConstruPilot. Aucun calcul n'a été produit pour ne pas vous "
                    "donner de résultat faux. Le moteur couvre aujourd'hui les maisons individuelles et les bâtiments à ossature béton armé."),
             "pt": ("Estes documentos descrevem uma obra de engenharia civil (ponte, contenção, arruamentos, redes ou obra hidráulica): "
                    "este tipo de obra ainda não é coberto pelo motor de cálculo do ConstruPilot. Não foi produzido nenhum cálculo para não "
                    "lhe dar um resultado errado. O motor cobre hoje moradias e edifícios em estrutura de betão armado.")}


async def maybe_handle(db, job_id, uid, cid, request_id, docs, hypotheses, country, *, step, store, llm=None, branding=None,
                       decide_alone=False) -> bool:
    lang = "pt" if country == "PT" else "fr"
    hypotheses = hypotheses or ""
    try:
        return await _handle(db, job_id, uid, cid, request_id, docs, hypotheses, country, lang, step=step, store=store, llm=llm,
                             branding=branding, decide_alone=decide_alone)
    except _NotFrame:
        return False
    except Exception as exc:  # noqa: BLE001 — erreur du moteur ossature : message clair, jamais une pile Python brute
        log.exception("bet_frame study failed")
        from .pipeline import where_frame
        from engines.bet_core.reader import providers_message
        msg = providers_message(exc, lang) or (_FAIL[lang] + f" ({type(exc).__name__}: {str(exc)[:200]} — {where_frame(exc)})")
        await step("Échec", status="failed", error=msg[:1200])
        return True


class _NotFrame(Exception):
    pass


_HOUSE = re.compile(r"\b(maison|moradia|vivenda|casa|house|villa|pavillon|habitation individuelle|clt|bois massif|madeira maci[cç]a|"
                    r"cross[- ]?laminated|massivholz|будин(ок|ку))\b", re.I)
_BUILDING = re.compile(r"\b(immeuble|pr[ée]dio|edif[ií]cio de habita[cç][aã]o coletiva|apartments?|logements collectifs|bureaux|"
                       r"escrit[oó]rios|parking|erp|frame|ossature)\b", re.I)


_TIMBER = re.compile(r"\b(clt|bois massif|madeira maci[cç]a|cross[- ]?laminated|massivholz)\b", re.I)


def _user_says_house(hypotheses: str) -> bool:
    """Choix explicite de l'utilisateur : maison / CLT bois massif → chaîne maison (jamais l'ossature BA)."""
    h = hypotheses or ""
    if _TIMBER.search(h):
        return True
    return bool(_HOUSE.search(h)) and not _BUILDING.search(h)


_FAIL = {"fr": "L'étude du bâtiment n'a pas pu être menée à son terme. Relancez-la ; si l'erreur persiste, transmettez ce message au support",
         "pt": "O estudo do edifício não pôde ser concluído. Volte a lançá-lo; se o erro persistir, envie esta mensagem ao suporte"}


async def _handle(db, job_id, uid, cid, request_id, docs, hypotheses, country, lang, *, step, store, llm=None, branding=None,
                  decide_alone=False) -> bool:
    try:
        from engines.bet_core import samples
        demo = bool(samples.detect(docs))
    except Exception:  # noqa: BLE001 — samples n'existe pas sur tous les sites
        demo = False
    if demo:
        raise _NotFrame
    try:
        # Bois massif CLT / lamellé-collé (poteaux-poutres ou murs) : moteur bet_clt (09/11 : FR, PT, UA).
        if _wants_clt(docs, hypotheses):
            if await _handle_clt(db, job_id, uid, cid, request_id, docs, hypotheses, country, lang, step=step, store=store, llm=llm,
                                 branding=branding, decide_alone=decide_alone):
                return True
            raise _NotFrame
        # Le choix explicite de l'utilisateur prime sur la détection IA (09/11 : « maison CLT / bois massif »
        # était reclassée « immeuble_collectif » et l'étude partait dans le moteur ossature BA).
        if _user_says_house(hypotheses):
            raise _NotFrame
        det = await reader.detect(docs, hypotheses, llm=llm)
    except Exception:  # noqa: BLE001 — détection impossible : chaîne maison historique
        log.warning("bet_frame: détection du type impossible", exc_info=True)
        raise _NotFrame
    if det["kind"] == "maison":
        raise _NotFrame
    await db.bet_study_jobs.update_one({"job_id": job_id}, {"$set": {"building_kind": det["kind"], "building_type": det.get("building_type")}})
    if det["kind"] == "civil":
        await step("Échec", status="failed", error=CIVIL_MSG[lang], out_of_scope=True)
        return True
    await step("Lecture des plans par IA et relevé du modèle bâtiment")
    rd = await reader.read_frame(docs, hypotheses, country, llm=llm, decide_alone=decide_alone,
                                 building_type=det.get("building_type") or "immeuble_collectif")
    decisions = rd.get("decisions") or []
    if not rd["ok"]:
        if decide_alone and not rd.get("questions"):
            blocking = [a for a in rd.get("anomalies") or [] if a.get("level") == "bloquant"]
            msg = ("Relevé impossible à compléter, même en tranchant seul : " if lang == "fr" else "Levantamento impossível de completar, mesmo decidindo sozinho: ") + \
                " ; ".join(f"{a['message']} ({a.get('fix') or '?'})" for a in blocking[:3])
            await step("Échec", status="failed", error=msg[:1200], anomalies=rd.get("anomalies"), decisions=decisions, provider=rd.get("provider"))
        else:
            await step("Questions à l'utilisateur", status="questions", questions=rd["questions"], anomalies=rd["anomalies"],
                       decisions=decisions, decide_alone=decide_alone, model=rd["model"], pages=rd["pages"], provider=rd.get("provider"))
        return True
    await step("Calculs, plans, devis et contrôle", model=rd["model"], pages=rd["pages"])
    with tempfile.TemporaryDirectory() as tmp:
        raw = copy.deepcopy(rd["model"])
        res = await asyncio.to_thread(pipeline.run, raw, tmp, None, lang, None, branding)
        if res["status"] == "MODELE_INVALIDE":
            qs = [] if decide_alone else rd["questions"] + [f"{a['message']} — {a.get('fix') or '?'}" for a in res["anomalies"] if a.get("level") == "bloquant"]
            if decide_alone:
                await step("Échec", status="failed", error=("; ".join(a["message"] for a in res["anomalies"] if a.get("level") == "bloquant"))[:1200],
                           anomalies=res["anomalies"], decisions=decisions)
            else:
                await step("Questions à l'utilisateur", status="questions", questions=qs, anomalies=res["anomalies"], decisions=decisions)
            return True
        arts = []
        for kind in ("pdf", "re2020_pdf", "plans_pdf", "xlsx", "zip"):
            if res["files"].get(kind):
                arts.append(await store(db, uid, cid, request_id, kind, Path(res["files"][kind]), LABELS[lang][kind]))
    decisions = list(dict.fromkeys(decisions + res.get("decisions", [])))
    await step("Terminé", status="done", artifacts=arts, review_status=res["status"], blocking=res["blocking"], sheets=res["sheets"],
               devis_ht=res["devis_ht"], devis_ttc=res["devis_ttc"], decisions=decisions, decide_alone=decide_alone,
               points=[a["message"] for a in res["anomalies"]][:30] + [i["message"] for i in res["review"]][:30],
               questions=rd["questions"], provider=rd.get("provider"), building_kind="frame", thermal=res.get("thermal"))
    return True


# ====================================================================== bois massif CLT (bet_clt)
_CLT_DOC = re.compile(r"\b(clt|cross[- ]?laminated|crosslam|bois lamell[ée][- ]crois[ée]|madeira lamelada[- ]cruzada|glulam|lamell[ée][- ]coll[ée]|"
                      r"lamelado[- ]colado|mass timber|клеєн|перехресно)", re.I)
_CLT_HINT = (" STRUCTURE BOIS MASSIF CLT / LAMELLÉ-COLLÉ : relève la trame des poteaux (ou des murs porteurs pour une maison) comme pour un "
             "bâtiment à ossature ; ajoute structure.system = \"post_beam\" (poteaux-poutres) ou \"walls\" (murs CLT porteurs, maison / petit "
             "collectif) ; pas de dalle ni de poutre BA à relever. Pays FR, PT ou UA."
             " Si le plan ou le détail constructif DONNE les compositions CLT (« CLT Panel 240-7s », « CLT 5s 100 wall »…), recopie-les : "
             "structure.clt_floor_layup, structure.clt_roof_layup, structure.wall_layup (le moteur les VÉRIFIE au lieu de les choisir) ; mur mitoyen "
             "double (« CLT wall 80+80 mm 3 layers ») → structure.party_wall = {side: x0|x1|y0|y1, layup: \"80 L3s\", leaves: 2} ; sens de portée "
             "évident (grande pièce sans mur intermédiaire) → structure.clt_span_dir. Étage partiel (R+1 en retrait, en L) → levels[].void_cells. "
             "Couches d'enveloppe du détail (isolant, épaisseur) → envelope.wall|roof|floor.layers [[nom, e en m, λ W/m.K]], plancher bas sur sous-sol "
             "non chauffé → envelope.below = \"unheated\". Sous-sol BA ou terrasse hors trame → estimate.basement {area, height, perimeter} / "
             "estimate.terrace {area}. Plans sans repères de files dans un sens (seuls des axes 1, 2, 3… numérotés) : prends comme files "
             "les lignes des murs porteurs principaux (façades, murs entre pièces) et nomme-les A, B, C… ; niveaux non cotés : hauteur "
             "sous plafond + épaisseur de plancher du détail. Ne bloque jamais sur la trame : décide et trace la décision.")
_UA_PRICES = re.compile(r"(pre[çc]os?|prix|prices?|ціни|цін|orçamento|devis|estimate|кошторис)[^.\n]{0,40}(ucr[aâ]nia|ukrain|україн|uah|грн|hryvn)|"
                        r"(ucr[aâ]nia|ukrain|україн)[^.\n]{0,30}(pre[çc]os?|prix|prices?|ціни)", re.I)


def _wants_clt(docs, hypotheses: str) -> bool:
    if _TIMBER.search(hypotheses or "") or _CLT_DOC.search(hypotheses or ""):
        return True
    try:
        from .reader import _doc_text
        txt = _doc_text(docs)[:200000]
    except Exception:  # noqa: BLE001
        return False
    return len(_CLT_DOC.findall(txt)) >= 2


async def _doc_langs(db, uid) -> list[str]:
    try:
        u = await db.users.find_one({"user_id": uid}, {"_id": 0, "doc_langs": 1}) or {}
        return [x for x in (u.get("doc_langs") or []) if x in ("fr", "pt", "en", "uk")]
    except Exception:  # noqa: BLE001
        return []


CLT_LABELS = {
    "fr": {"pdf": "Dossier bois massif CLT — note de calcul + plans", "plans_pdf": "Plans CLT / lamellé-collé (PDF)", "xlsx": "Devis et métré CLT (Excel)", "zip": "Plans DXF", "estimate_pdf": "Devis final aux prix ukrainiens (PDF)", "estimate_xlsx": "Devis final aux prix ukrainiens (Excel)"},
    "pt": {"pdf": "Processo madeira maciça CLT — memória de cálculo + desenhos", "plans_pdf": "Desenhos CLT / lamelado-colado (PDF)", "xlsx": "Medições e orçamento CLT (Excel)", "zip": "Desenhos DXF", "estimate_pdf": "Orçamento final com preços da Ucrânia (PDF)", "estimate_xlsx": "Orçamento final com preços da Ucrânia (Excel)"},
    "en": {"pdf": "Mass timber CLT study — calculation report + drawings", "plans_pdf": "CLT / glulam drawings (PDF)", "xlsx": "CLT quantities and estimate (Excel)", "zip": "DXF drawings", "estimate_pdf": "Final estimate at Ukrainian prices (PDF)", "estimate_xlsx": "Final estimate at Ukrainian prices (Excel)"},
    "uk": {"pdf": "Розрахунок CLT — записка + креслення", "plans_pdf": "Креслення CLT / клеєний брус (PDF)", "xlsx": "Кошторис CLT (Excel)", "zip": "Креслення DXF", "estimate_pdf": "Остаточний кошторис за цінами України (PDF)", "estimate_xlsx": "Остаточний кошторис за цінами України (Excel)"},
}


async def _handle_clt(db, job_id, uid, cid, request_id, docs, hypotheses, country, lang, *, step, store, llm=None, branding=None,
                      decide_alone=False) -> bool:
    """Étude CLT complète. False → la chaîne maison historique prend le relais (plans illisibles en trame)."""
    from engines.bet_clt import pipeline as cp
    from engines.bet_clt.lang import pick_lang
    house = bool(_HOUSE.search(hypotheses or "")) and not _BUILDING.search(hypotheses or "")
    if job_id:
        await db.bet_study_jobs.update_one({"job_id": job_id}, {"$set": {"building_kind": "clt"}})
    await step("Lecture des plans par IA et relevé de la trame bois massif (CLT)")
    rd = await reader.read_frame(docs, (hypotheses or "") + _CLT_HINT, country, llm=llm, decide_alone=decide_alone,
                                 building_type="maison" if house else "immeuble_collectif", engine="clt")
    decisions = rd.get("decisions") or []
    if not rd["ok"]:
        if rd.get("model") is None and house:
            return False
        if decide_alone and not rd.get("questions"):
            blocking = [a for a in rd.get("anomalies") or [] if a.get("level") == "bloquant"]
            await step("Échec", status="failed", error=("Relevé CLT impossible : " + " ; ".join(a["message"] for a in blocking[:3]))[:1200],
                       anomalies=rd.get("anomalies"), decisions=decisions)
        else:
            await step("Questions à l'utilisateur", status="questions", questions=rd["questions"], anomalies=rd["anomalies"],
                       decisions=decisions, decide_alone=decide_alone, model=rd["model"], pages=rd["pages"], provider=rd.get("provider"))
        return True
    raw = copy.deepcopy(rd["model"])
    st = raw.setdefault("structure", {})
    if not st.get("system"):
        st["system"] = "walls" if house else "post_beam"
    if _UA_PRICES.search(hypotheses or ""):           # « orçamento com os preços da Ucrânia » → devis final aux prix UA (грн + €)
        raw.setdefault("estimate", {})["market"] = "UA"
    try:
        from core.ui_lang import current_doc_lang
        wanted = current_doc_lang()
    except Exception:  # noqa: BLE001
        wanted = None
    extra = await _doc_langs(db, uid)
    main = extra[0] if extra else pick_lang(country, wanted if country == "FR" else None)
    await step("Calculs CLT (EN 1995), plans, devis et contrôle", model=raw, pages=rd["pages"])
    with tempfile.TemporaryDirectory() as tmp:
        res = await asyncio.to_thread(cp.run, raw, tmp, None, main, None, branding, extra[1:] if extra else None)
        if res["status"] == "MODELE_INVALIDE":
            msg = "; ".join(a["message"] for a in res["anomalies"] if a.get("level") == "bloquant")
            await step("Échec" if decide_alone else "Questions à l'utilisateur", status="failed" if decide_alone else "questions",
                       error=msg[:1200] if decide_alone else None, questions=[] if decide_alone else [msg], anomalies=res["anomalies"], decisions=decisions)
            return True
        arts = []
        for key, path in res["files"].items():
            base, _, lg = key.partition("_")
            for two in ("plans_pdf", "estimate_pdf", "estimate_xlsx"):
                if key == two:
                    base, lg = two, ""
                elif key.startswith(two + "_"):
                    base, lg = two, key[len(two) + 1:]
            lg = lg or res["lang"]
            label = CLT_LABELS.get(lg, CLT_LABELS["en"]).get(base, base)
            arts.append(await store(db, uid, cid, request_id, base, Path(path), label + ("" if lg == res["lang"] else f" [{lg.upper()}]")))
    decisions = list(dict.fromkeys(decisions + res.get("decisions", [])))
    await step("Terminé", status="done", artifacts=arts, review_status=res["status"], blocking=res["blocking"], sheets=res["sheets"],
               devis_ht=res["devis_ht"], devis_ttc=res["devis_ttc"], decisions=decisions, decide_alone=decide_alone,
               points=[a["message"] for a in res["anomalies"]][:30] + [i["message"] for i in res["review"]][:30],
               questions=rd["questions"], provider=rd.get("provider"), building_kind="clt", langs=res.get("langs"))
    return True
