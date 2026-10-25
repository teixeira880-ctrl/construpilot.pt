"""Branchement du moteur ossature dans l'outil Assistant generate_full_bet_study (bet_core.assistant_tool._work).

maybe_handle() décide du moteur selon le bâtiment : maison individuelle → False (chaîne bet_core inchangée) ;
bâtiment à ossature (immeuble, bureaux, parking, ERP…) → étude bet_frame complète ; génie civil → réponse claire « hors périmètre ».
"""
from __future__ import annotations

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
    "tableaux de poteaux / poutres / dalles / semelles, coupe, plans de niveaux, réseaux et schéma vertical des colonnes montantes. "
    "Le génie civil (ponts, murs de soutènement isolés, VRD, réseaux publics, ouvrages hydrauliques) n'est PAS encore couvert : dis-le "
    "clairement et n'improvise pas de calcul. "
    "N'écris JAMAIS un document texte intitulé « Plan », « Planta » ou « Plan de coffrage » : un plan est un dessin produit par "
    "generate_full_bet_study ou generate_bet_lot_plans. draw_section_schema sert UNIQUEMENT aux coupes de principe d'une paroi, d'un "
    "plancher ou d'une toiture (jamais pour des colonnes de plomberie, un réseau ou un bâtiment entier) et ses libellés s'écrivent dans "
    "la langue du projet."
)

LABELS = {"fr": {"pdf": "Dossier d'étude BET — ossature (note de calcul + plans)", "plans_pdf": "Plans PDF (pour les entreprises)",
                 "xlsx": "Devis et métré (Excel)", "zip": "Plans DXF (pour logiciel de DAO)"},
          "pt": {"pdf": "Processo de estudo — estrutura (memória de cálculo + desenhos)", "plans_pdf": "Desenhos PDF (para as empresas)",
                 "xlsx": "Medições e orçamento (Excel)", "zip": "Desenhos DXF (para software CAD)"}}

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
        msg = (_FAIL[lang] + f" ({type(exc).__name__}: {str(exc)[:200]} — {where_frame(exc)})")
        await step("Échec", status="failed", error=msg[:1200])
        return True


class _NotFrame(Exception):
    pass


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
        for kind in ("pdf", "plans_pdf", "xlsx", "zip"):
            if res["files"].get(kind):
                arts.append(await store(db, uid, cid, request_id, kind, Path(res["files"][kind]), LABELS[lang][kind]))
    decisions = list(dict.fromkeys(decisions + res.get("decisions", [])))
    await step("Terminé", status="done", artifacts=arts, review_status=res["status"], blocking=res["blocking"], sheets=res["sheets"],
               devis_ht=res["devis_ht"], devis_ttc=res["devis_ttc"], decisions=decisions, decide_alone=decide_alone,
               points=[a["message"] for a in res["anomalies"]][:30] + [i["message"] for i in res["review"]][:30],
               questions=rd["questions"], provider=rd.get("provider"), building_kind="frame")
    return True
