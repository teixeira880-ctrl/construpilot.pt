"""DPGF / BPU / DQE : lecture Excel, chiffrage (bibliothèque + IA), CCTP, consignes, devis.

Espace Pro Business. Le classeur de l'architecte est lu onglet par onglet (lots,
désignations, unités, quantités). Les prix viennent d'abord de la bibliothèque de
l'entreprise, puis de l'IA pour les lignes manquantes. Le CCTP et les consignes du
pro (« ne chiffre pas le carrelage ») sont appliqués avant le calcul des totaux.
"""
import asyncio
import io
import json
import logging
import os
import secrets
import time
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from core.db import db
from core.security import current_user
from engines import ai, dpgf_engine, price_library, storage
from engines.access import require_level
from routes.company_library import get_user_library, remember_prices
from routes.documents import _client_snapshot, _compute_totals, _next_number, _now

router = APIRouter(prefix="/pro/dpgf", tags=["dpgf"], dependencies=[Depends(require_level("pro"))])
logger = logging.getLogger(__name__)

XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
CCTP_PAGE_CAP = 60          # pages lues au maximum par pièce écrite
CCTP_TIME_BUDGET = 150      # secondes d'extraction de texte pour l'ensemble des pièces
PLAN_CONTENT_BYTES = 1_000_000  # au-delà, la page est un plan : elle est ignorée


def _cctp_text(raw: bytes, filename: str, deadline: float | None = None,
               state: dict | None = None) -> str:
    """Extrait le texte d'une pièce écrite, en ignorant les pages de plans.

    Un DCE mélange des pièces écrites et des plans. Une page de plan pèse plusieurs
    mégaoctets de tracés vectoriels, coûte des secondes à dépouiller et ne rapporte qu'un
    cartouche : sa taille de flux est mesurée en 10 ms et la page est sautée. Reste un
    plafond de pages et un budget de temps, la production ne disposant que d'un quart de cœur.
    """
    name = (filename or "").lower()
    if name.endswith(".pdf"):
        from pypdf import PdfReader
        reader = PdfReader(io.BytesIO(raw))
        pages = reader.pages[:CCTP_PAGE_CAP]
        if state is not None:
            state.update({"doc": filename, "page": 0, "pages": len(pages), "plans": 0})
        out = []
        for i, page in enumerate(pages):
            if deadline and time.monotonic() > deadline:
                break
            if _is_plan_page(page):
                if state is not None:
                    state["plans"] = state.get("plans", 0) + 1
                    state["page"] = i + 1
                continue
            out.append(page.extract_text() or "")
            if state is not None:
                state["page"] = i + 1
        return "\n".join(out)
    if name.endswith((".docx", ".txt", ".csv", ".xlsx")):
        from engines.office_text import extract_office_text
        return extract_office_text(raw, name.rsplit(".", 1)[-1])
    raise HTTPException(400, "CCTP : formats acceptés .pdf, .docx, .txt")


def _is_plan_page(page) -> bool:
    """Une page dont le flux graphique dépasse le seuil est un plan, pas une pièce écrite."""
    try:
        return len(page.get_contents().get_data()) > PLAN_CONTENT_BYTES
    except Exception:  # noqa: BLE001 — page atypique : on la lit normalement
        return False


async def _study(file_id: str, user_id: str) -> dict:
    doc = await db.dpgf_imports.find_one({"file_id": file_id, "user_id": user_id}, {"_id": 0})
    if not doc:
        raise HTTPException(404, "Étude DPGF introuvable")
    return doc


def _public(doc: dict) -> dict:
    return {
        "file_id": doc["file_id"], "filename": doc.get("filename"),
        "label": doc.get("label") or "",
        "created_at": doc.get("created_at"),
        "download_url": f"/api/pro/dpgf/file/{doc['file_id']}",
        "sources": doc.get("sources", []),
        "sheets": doc.get("sheets", []), "lots": doc.get("lot_totals", []),
        "gaps": doc.get("gaps", []),
        "line_count": len(doc.get("lines", [])),
        "priced": doc.get("priced", 0),
        "dedup_count": doc.get("dedup_count", sum(1 for x in doc.get("lines", []) if (x.get("exclusion_reason") or "").startswith("Doublon"))),
        "from_library": sum(1 for x in doc.get("lines", []) if x.get("source") == "bibliotheque"),
        "from_ai": sum(1 for x in doc.get("lines", []) if x.get("source") == "ia"),
        "excluded": sum(1 for x in doc.get("lines", []) if x.get("excluded")),
        "grand_total_ht": doc.get("grand_total_ht", 0),
        "instructions": doc.get("instructions", ""),
        "directives": doc.get("directives", {}),
        "cctp": doc.get("cctp", {}),
        "quote_doc_id": doc.get("quote_doc_id"),
        "variant_group": doc.get("variant_group"),
        "lines": doc.get("lines", [])[:1000],
    }


AI_BATCH = 120  # lignes envoyées par appel de chiffrage (tout le bordereau est traité)
JOB_STALE_MIN = 25  # un travail sans signe de vie au-delà est déclaré en échec
EMAIL_MIN_LINES = 40  # au-delà, le chiffrage est « gros » : e-mail en plus de la cloche


async def _job(job_id: str, **fields) -> None:
    await db.dpgf_jobs.update_one({"job_id": job_id},
                                  {"$set": {**fields, "updated_at": _now()}})


async def _notify(user_id: str, title: str, body: str) -> None:
    """Prévient le pro à la fin du chiffrage : il peut fermer l'onglet pendant le calcul."""
    await db.notifications.insert_one({
        "notif_id": "n_" + uuid.uuid4().hex[:10], "user_id": user_id, "type": "dpgf_job",
        "title": title[:160], "body": body[:400], "url": "/dpgf",
        "read": False, "created_at": _now(),
    })


async def _email_done(user_id: str, label: str, priced: int, line_count: int,
                      total_ht: float) -> None:
    """E-mail de fin pour les gros chiffrages : la cloche ne suffit pas quand l'onglet est fermé.

    Un chiffrage long (gros DCE) se lance puis le pro ferme l'onglet ; il ne verra la cloche
    qu'en revenant sur l'app. L'e-mail le prévient sans qu'il ait à surveiller. Opt-out par
    réglage utilisateur (``dpgf_email_notify``).
    """
    u = await db.users.find_one({"user_id": user_id},
                                {"_id": 0, "email": 1, "name": 1, "dpgf_email_notify": 1}) or {}
    if not u.get("email") or u.get("dpgf_email_notify") is False:
        return
    from engines import emailer
    base = (os.environ.get("FRONTEND_URL") or "https://construpilot.pt").rstrip("/")
    total = f"{total_ht:,.0f}".replace(",", " ")
    greeting = f" {u['name']}" if u.get("name") else ""
    html = emailer.wrap_html(
        "Votre chiffrage est terminé",
        f"<p>Bonjour{greeting},</p>"
        f"<p>Le chiffrage <strong>{label}</strong> vient de se terminer sur ConstruPilot.</p>"
        f"<ul style='padding-left:18px'>"
        f"<li><strong>{priced}/{line_count}</strong> ligne(s) chiffrée(s)</li>"
        f"<li>Total : <strong>{total} € HT</strong></li></ul>"
        f"<p>Ouvrez l'étude pour ajuster les prix, comparer une variante de marge ou "
        f"la passer en devis.</p>",
        cta_url=f"{base}/dpgf", cta_label="Ouvrir mon chiffrage")
    try:
        await emailer.send_email(u["email"], f"Chiffrage terminé — {label}", html,
                                 from_name="ConstruPilot")
    except Exception as exc:  # noqa: BLE001 — l'e-mail est un bonus, la cloche reste la source
        logger.warning("dpgf completion email failed: %s", exc)


async def _heartbeat(job_id: str, state: dict) -> None:
    """Publie l'avancement de la lecture d'une pièce écrite (sinon l'étape paraît figée)."""
    while True:
        await asyncio.sleep(3)
        await _job(job_id, step="cctp_read", sub_doc=state.get("doc"),
                   sub_done=state.get("page", 0), sub_total=state.get("pages", 0))


async def _price_batches(job_id: str, targets: list[dict], context: str) -> None:
    """Chiffrage IA par paquets : aucune limite de taille de bordereau, avancement publié."""
    total = len(targets)
    for start in range(0, total, AI_BATCH):
        chunk = targets[start:start + AI_BATCH]
        await _job(job_id, step="pricing", done=start, total=total)
        try:
            est = await ai.price_dpgf_lines(
                [{"designation": x["designation"], "unit": x["unit"], "qty": x["qty"]}
                 for x in chunk], context)
        except Exception as exc:  # noqa: BLE001 — un paquet en échec ne perd pas les autres
            logger.warning("dpgf pricing batch failed: %s", exc)
            continue
        for k, x in enumerate(chunk):
            if k < len(est) and est[k] > 0:
                x["pu_ai"] = round(est[k], 2)
                if x["pu_base"] is None:
                    x["pu_base"] = x["pu_ai"]
                    x["source"] = "ia"
    await _job(job_id, step="pricing", done=total, total=total)


async def _run_import(job_id: str, fid: str, user_id: str, xlsx: list[tuple[str, bytes]],
                      cctp_docs: list[tuple[str, bytes]], opts: dict) -> None:
    """Traitement complet de l'étude, hors requête HTTP (aucune requête longue côté client)."""
    try:
        rows: list[dict] = []
        sheets: list[dict] = []
        sources: list[dict] = []
        await _job(job_id, step="reading")
        for idx, (filename, raw) in enumerate(xlsx):
            try:
                parsed = await asyncio.to_thread(dpgf_engine.parse_workbook, raw)
            except Exception:  # noqa: BLE001 — fichier illisible : message clair au pro
                await _job(job_id, status="error", error=f"Fichier Excel illisible : {filename}")
                return
            for r in parsed["rows"]:
                r["src"] = idx
                r["src_name"] = filename
                r["line_id"] = f"f{idx}{r['line_id']}"
                rows.append(r)
            sheets += [{**s, "src": idx, "src_name": filename} for s in parsed["sheets"]]
            path = f"{storage.APP_NAME}/dpgf/{user_id}/{fid}_src{idx}.xlsx"
            await asyncio.to_thread(storage.put_object, path, raw, XLSX_MIME)
            sources.append({"src": idx, "filename": filename, "path": path,
                            "lines": len(parsed["rows"])})
        if not rows:
            await _job(job_id, status="error",
                       error="Aucune ligne exploitable. Attendu : Désignation / Unité / "
                             "Quantité / Prix unitaire.")
            return
        # Neutralise les doublons stricts (feuille récap/DQE, fichier importé 2 fois) AVANT
        # tout chiffrage : on ne price jamais deux fois la même ligne.
        dup_count = dpgf_engine.dedup_rows(rows)
        lots = dpgf_engine.lots(rows)

        # 1) Consignes du pro → directives (exclusions, coefficients, prescriptions)
        await _job(job_id, step="directives", total=len(rows))
        directives = await ai.dpgf_directives(opts["instructions"], lots)
        try:
            manual_lots = {str(k): float(v)
                           for k, v in json.loads(opts["lot_margins"] or "{}").items()}
        except (ValueError, TypeError, AttributeError):
            manual_lots = {}
        if opts["margin_pct"]:
            directives["margin_pct"] = float(opts["margin_pct"])
        directives["lot_margins"] = {**(directives.get("lot_margins") or {}), **manual_lots}
        applied = dpgf_engine.apply_directives(rows, directives)

        # 2) CCTP et pièces écrites (plusieurs documents possibles) → prescriptions
        cctp_info: dict = {"summary": "", "prescriptions": [], "documents": [], "used": False}
        gaps: list[dict] = []
        if cctp_docs:
            await _job(job_id, step="cctp_read")
            parts = []
            # budget réparti : un DCE de plans ne doit pas consommer le temps des vrais CCTP
            per_doc = max(30.0, CCTP_TIME_BUDGET / max(1, len(cctp_docs)))
            for filename, raw in cctp_docs:
                state = {"doc": filename, "page": 0, "pages": 0}
                beat = asyncio.create_task(_heartbeat(job_id, state))
                try:
                    # pypdf est bloquant : hors boucle d'événements, sinon tout le serveur gèle
                    text = await asyncio.to_thread(_cctp_text, raw, filename,
                                                   time.monotonic() + per_doc, state)
                except HTTPException as exc:
                    beat.cancel()
                    await _job(job_id, status="error", error=str(exc.detail))
                    return
                finally:
                    beat.cancel()
                truncated = 0 < state["pages"] and state["page"] < state["pages"]
                cctp_info["documents"].append({"filename": filename, "chars": len(text),
                                               "pages_read": state["page"],
                                               "pages": state["pages"],
                                               "plans_skipped": state.get("plans", 0),
                                               "truncated": truncated})
                parts.append(f"=== DOCUMENT : {filename} ===\n{text}")
            full = "\n\n".join(parts)[:200000]
            cctp_info["filename"] = ", ".join(d["filename"] for d in cctp_info["documents"])
            cctp_info["chars"] = len(full)
            if opts["analyse_cctp"]:
                await _job(job_id, step="cctp_analysis")
                try:
                    res = await ai.cctp_prescriptions(full, lots)
                    cctp_info.update({"summary": res["summary"],
                                      "prescriptions": res["prescriptions"], "used": True})
                    dpgf_engine.apply_prescriptions(rows, res["prescriptions"])
                except Exception as exc:  # noqa: BLE001 — le chiffrage continue sans le CCTP
                    logger.warning("cctp analysis failed: %s", exc)
                    cctp_info["error"] = "Analyse CCTP indisponible"
                await _job(job_id, step="gaps")
                try:
                    missing = await ai.cctp_missing_works(full, [r["designation"] for r in rows])
                    gaps = [{**m, "gap_id": f"g{i + 1}", "added": False}
                            for i, m in enumerate(missing)]
                except Exception as exc:  # noqa: BLE001 — la vérification des oublis est un bonus
                    logger.warning("cctp gap check failed: %s", exc)

        # 3) Bibliothèque de prix de l'entreprise (priorité absolue)
        await _job(job_id, step="library")
        library = await get_user_library(user_id)
        if library:
            for x in rows:
                if x["excluded"]:
                    continue
                m = price_library.match_price(x["designation"], x.get("unit", ""), library)
                if m:
                    x["pu_library"] = round(m[0], 2)
                    x["matched_designation"] = m[1]
                    if x["pu_file"] is None:
                        x["pu_base"] = x["pu_library"]
                        x["source"] = "bibliotheque"

        # 4) IA : lignes sans prix, + comparaison marché si demandée
        ctx_parts = (directives.get("notes") or []) + [p["text"] for p in cctp_info["prescriptions"]]
        context = " · ".join(ctx_parts)[:4000]
        targets = [x for x in rows if not x["excluded"] and
                   (opts["market_compare"] or (x["pu_base"] is None))]
        if targets:
            await _price_batches(job_id, targets, context)

        totals = dpgf_engine.finalise(rows)
        doc = {
            "file_id": fid, "user_id": user_id,
            "sources": sources, "source_path": sources[0]["path"],
            "filename": ", ".join(s["filename"] for s in sources), "created_at": _now(),
            "label": (opts["label"] or "").strip()[:140],
            "sheets": sheets, "lines": rows, "gaps": gaps,
            "lot_totals": totals["lots"], "grand_total_ht": totals["grand_total_ht"],
            "priced": totals["priced"], "dedup_count": dup_count,
            "instructions": (opts["instructions"] or "").strip()[:2000],
            "directives": {**directives, **applied}, "cctp": cctp_info,
            "market_compare": bool(opts["market_compare"]),
        }
        await _job(job_id, step="saving")
        await db.dpgf_imports.insert_one(dict(doc))
        await _job(job_id, status="done", step="done")
        label_txt = doc['label'] or doc['filename']
        await _notify(user_id, f"Chiffrage terminé — {label_txt}",
                      f"{totals['priced']} ligne(s) chiffrée(s) · "
                      f"{totals['grand_total_ht']:,.0f} € HT".replace(",", " "))
        if len(rows) >= EMAIL_MIN_LINES or cctp_info.get("used"):
            await _email_done(user_id, label_txt, totals["priced"], len(rows),
                              totals["grand_total_ht"])
    except Exception as exc:  # noqa: BLE001 — l'échec doit rester lisible côté pro
        logger.exception("dpgf import job failed")
        await _job(job_id, status="error", error=f"Chiffrage interrompu : {exc}")
        await _notify(user_id, "Chiffrage interrompu", str(exc)[:200])


@router.post("/import", status_code=202)
async def import_dpgf(
    file: UploadFile | None = File(default=None),
    files: list[UploadFile] = File(default=[]),
    cctp: UploadFile | None = File(default=None),
    cctp_files: list[UploadFile] = File(default=[]),
    instructions: str = Form(default=""),
    label: str = Form(default=""),
    margin_pct: float = Form(default=0),
    lot_margins: str = Form(default="{}"),
    analyse_cctp: bool = Form(default=True),
    market_compare: bool = Form(default=True),
    user=Depends(current_user),
) -> dict:
    """Démarre le chiffrage en tâche de fond et rend la main immédiatement.

    Le traitement (lecture Excel, CCTP, appels IA) dure de quelques secondes à plusieurs
    minutes selon la taille du DCE : il ne doit jamais tenir dans une requête HTTP, sinon
    le proxy coupe la connexion. L'avancement se lit sur GET /import/job/{job_id}.
    """
    uploads = [f for f in ([file] if file is not None else []) + list(files or [])
               if f is not None and getattr(f, "filename", None)]
    if not uploads:
        raise HTTPException(400, "Joignez au moins un bordereau Excel (.xlsx)")
    if len(uploads) > 10:
        raise HTTPException(400, "Maximum 10 bordereaux par étude")
    cctp_uploads = [f for f in ([cctp] if cctp is not None else []) + list(cctp_files or [])
                    if f is not None and getattr(f, "filename", None)][:10]

    xlsx = [(up.filename, await up.read()) for up in uploads]
    cctp_docs = [(up.filename, await up.read()) for up in cctp_uploads]

    fid = "dpgf_" + uuid.uuid4().hex[:12]
    job_id = "job_" + uuid.uuid4().hex[:12]
    await db.dpgf_jobs.insert_one({
        "job_id": job_id, "file_id": fid, "user_id": user["user_id"],
        "status": "running", "step": "queued", "done": 0, "total": 0, "error": None,
        "filename": ", ".join(name for name, _ in xlsx),
        "cctp_count": len(cctp_docs), "created_at": _now(), "updated_at": _now(),
    })
    asyncio.create_task(_run_import(job_id, fid, user["user_id"], xlsx, cctp_docs, {
        "instructions": instructions, "label": label, "margin_pct": margin_pct,
        "lot_margins": lot_margins, "analyse_cctp": analyse_cctp,
        "market_compare": market_compare,
    }))
    return {"job_id": job_id, "file_id": fid, "status": "running", "step": "queued"}


@router.get("/import/job/active")
async def active_job(user=Depends(current_user)) -> dict:
    """Chiffrage en cours de l'utilisateur, pour reprendre le suivi après un retour sur la page."""
    job = await db.dpgf_jobs.find_one({"user_id": user["user_id"], "status": "running"},
                                      {"_id": 0}, sort=[("created_at", -1)])
    return {"job": job}


@router.get("/import/job/{job_id}")
async def import_job(job_id: str, user=Depends(current_user)) -> dict:
    """Avancement du chiffrage ; renvoie l'étude complète dès que le travail est terminé."""
    job = await db.dpgf_jobs.find_one({"job_id": job_id, "user_id": user["user_id"]}, {"_id": 0})
    if not job:
        raise HTTPException(404, "Chiffrage introuvable")
    if job["status"] == "running":
        seen = datetime.fromisoformat(job["updated_at"])
        if datetime.now(timezone.utc) - seen > timedelta(minutes=JOB_STALE_MIN):
            job.update({"status": "error", "error": "Chiffrage interrompu (délai dépassé)"})
            await _job(job_id, status="error", error=job["error"])
    if job["status"] == "done":
        doc = await db.dpgf_imports.find_one({"file_id": job["file_id"]}, {"_id": 0})
        job["result"] = _public(doc) if doc else None
    return job


@router.get("")
async def list_imports(user=Depends(current_user)) -> list[dict]:
    docs = await db.dpgf_imports.find(
        {"user_id": user["user_id"]},
        {"_id": 0, "file_id": 1, "filename": 1, "created_at": 1, "grand_total_ht": 1,
         "lines": 1, "quote_doc_id": 1, "label": 1}).sort("created_at", -1).to_list(50)
    return [{"file_id": d["file_id"], "filename": d.get("filename"),
             "label": d.get("label") or "",
             "created_at": d.get("created_at"), "grand_total_ht": d.get("grand_total_ht", 0),
             "line_count": len(d.get("lines", [])), "quote_doc_id": d.get("quote_doc_id")}
            for d in docs]


@router.get("/{file_id}")
async def get_import(file_id: str, user=Depends(current_user)) -> dict:
    return _public(await _study(file_id, user["user_id"]))


class LineUpdate(BaseModel):
    pu: float | None = Field(default=None, ge=0)
    source: str | None = None      # bibliotheque | ia | manuel | fichier
    excluded: bool | None = None


@router.patch("/{file_id}/line/{line_id}")
async def update_line(file_id: str, line_id: str, body: LineUpdate,
                      user=Depends(current_user)) -> dict:
    doc = await _study(file_id, user["user_id"])
    rows = doc.get("lines", [])
    target = next((x for x in rows if x.get("line_id") == line_id), None)
    if not target:
        raise HTTPException(404, "Ligne introuvable")
    if body.excluded is not None:
        target["excluded"] = body.excluded
        target["exclusion_reason"] = "Exclu manuellement" if body.excluded else ""
        if body.excluded:
            target["pu"] = None
            target["pu_base"] = None
            target["source"] = None
    if body.source in ("bibliotheque", "ia", "fichier"):
        key = {"bibliotheque": "pu_library", "ia": "pu_ai", "fichier": "pu_file"}[body.source]
        if target.get(key) is None:
            raise HTTPException(400, "Aucun prix disponible pour cette source")
        target["pu_base"] = target[key]
        target["source"] = body.source
        target["excluded"] = False
    elif body.pu is not None:
        target["pu_base"] = round(body.pu, 2)
        target["source"] = "manuel"
        target["excluded"] = False
    totals = dpgf_engine.finalise(rows)
    await db.dpgf_imports.update_one(
        {"file_id": file_id, "user_id": user["user_id"]},
        {"$set": {"lines": rows, "lot_totals": totals["lots"],
                  "grand_total_ht": totals["grand_total_ht"], "priced": totals["priced"]}})
    doc.update({"lines": rows, "lot_totals": totals["lots"],
                "grand_total_ht": totals["grand_total_ht"], "priced": totals["priced"]})
    return _public(doc)


class GapAddIn(BaseModel):
    qty: float = Field(gt=0)
    unit: str | None = None
    pu: float | None = Field(default=None, ge=0)


@router.post("/{file_id}/gap/{gap_id}/add")
async def add_gap_line(file_id: str, gap_id: str, body: GapAddIn,
                       user=Depends(current_user)) -> dict:
    """Ajoute à l'étude un ouvrage du CCTP oublié au bordereau (puis au devis)."""
    doc = await _study(file_id, user["user_id"])
    gap = next((g for g in doc.get("gaps", []) if g.get("gap_id") == gap_id), None)
    if not gap:
        raise HTTPException(404, "Oubli introuvable")
    if gap.get("added"):
        raise HTTPException(400, "Cet ouvrage a déjà été ajouté à l'étude")
    rows = doc.get("lines", [])
    unit = (body.unit or gap.get("unit") or "u")[:12]
    row = {
        "line_id": f"gap{gap_id}", "sheet": "", "row": None, "src": -1,
        "src_name": "Ajout CCTP", "lot": gap.get("lot") or "Ajouts CCTP",
        "designation": gap["designation"], "description": gap.get("reason") or "",
        "unit": unit, "qty": round(float(body.qty), 3),
        "pu_file": None, "pu_library": None, "pu_ai": None,
        "pu_base": None, "pu": None, "source": None, "matched_designation": None,
        "excluded": False, "exclusion_reason": "", "cctp_note": gap.get("reason") or "",
        "margin_pct": float((doc.get("directives") or {}).get("margin_pct") or 0),
        "added_from_cctp": True,
    }
    library = await get_user_library(user["user_id"])
    m = price_library.match_price(row["designation"], unit, library) if library else None
    if body.pu:
        row["pu_base"] = round(float(body.pu), 2)
        row["source"] = "manuel"
    elif m:
        row["pu_library"] = round(m[0], 2)
        row["matched_designation"] = m[1]
        row["pu_base"] = row["pu_library"]
        row["source"] = "bibliotheque"
    else:
        est = await ai.price_dpgf_lines([{"designation": row["designation"], "unit": unit,
                                          "qty": row["qty"]}])
        if est and est[0] > 0:
            row["pu_ai"] = round(est[0], 2)
            row["pu_base"] = row["pu_ai"]
            row["source"] = "ia"
    rows.append(row)
    gap["added"] = True
    totals = dpgf_engine.finalise(rows)
    await db.dpgf_imports.update_one(
        {"file_id": file_id, "user_id": user["user_id"]},
        {"$set": {"lines": rows, "gaps": doc["gaps"], "lot_totals": totals["lots"],
                  "grand_total_ht": totals["grand_total_ht"], "priced": totals["priced"]}})
    doc.update({"lines": rows, "lot_totals": totals["lots"],
                "grand_total_ht": totals["grand_total_ht"], "priced": totals["priced"]})
    return _public(doc)


@router.post("/{file_id}/gap/{gap_id}/ignore")
async def ignore_gap(file_id: str, gap_id: str, user=Depends(current_user)) -> dict:
    doc = await _study(file_id, user["user_id"])
    gaps = [g for g in doc.get("gaps", []) if g.get("gap_id") != gap_id]
    await db.dpgf_imports.update_one({"file_id": file_id, "user_id": user["user_id"]},
                                     {"$set": {"gaps": gaps}})
    doc["gaps"] = gaps
    return _public(doc)


class QuoteIn(BaseModel):
    vat_rate: float = Field(default=10, ge=0, le=25)
    full_descriptions: bool = True
    client_id: str | None = None
    title: str = ""


@router.post("/{file_id}/quote")
async def dpgf_to_quote(file_id: str, body: QuoteIn, user=Depends(current_user)) -> dict:
    """Passe l'étude DPGF en devis brouillon : une catégorie par lot, exclusions conservées."""
    doc = await _study(file_id, user["user_id"])
    rows = doc.get("lines", [])
    dpgf_engine.dedup_rows(rows)  # protège aussi les études importées avant le correctif
    lines = []
    for x in rows:
        # Le descriptif du BORDEREAU est repris dans le devis, mais JAMAIS les prescriptions
        # CCTP : elles servent au chiffrage (coefficient) et restent dans l'étude, pas dans
        # le devis client (elles alourdissent le devis et ne sont pas des lignes de prestation).
        desc = (x.get("description") or "") if body.full_descriptions else ""
        if (x.get("exclusion_reason") or "").startswith("Doublon"):
            continue  # ligne en doublon : ni chiffrée, ni recopiée dans le devis
        if x.get("excluded"):
            lines.append({
                "designation": f"{x['designation']} — {dpgf_engine.NOT_PRICED}",
                "description": (desc or "")[:2000], "unit": x.get("unit") or "u",
                "qty": x.get("qty") or 0, "unit_price_ht": 0, "vat_rate": body.vat_rate,
                "category": x.get("lot") or "Sans lot"})
            continue
        if x.get("pu") is None:
            continue
        lines.append({
            "designation": x["designation"][:300], "description": (desc or "")[:2000],
            "unit": x.get("unit") or "u", "qty": x.get("qty") if x.get("qty") is not None else 1,
            "unit_price_ht": x["pu"], "vat_rate": body.vat_rate,
            "category": x.get("lot") or "Sans lot",
            "price_source": x.get("source") or "",
            "price_reference": x.get("matched_designation") or ""})
    if not lines:
        raise HTTPException(400, "Aucune ligne chiffrée à convertir en devis")

    totals = _compute_totals(lines, 0)
    now = _now()
    notes = [f"Devis établi à partir du bordereau « {doc.get('filename') or 'DPGF'} »."]
    if doc.get("instructions"):
        notes.append(f"Consignes appliquées : {doc['instructions']}")
    if (doc.get("cctp") or {}).get("summary"):
        notes.append(f"CCTP : {doc['cctp']['summary']}")
    if any(x.get("excluded") for x in rows):
        notes.append("Les prestations marquées « Non chiffré — hors marché » ne sont pas incluses au total.")
    quote = {
        "doc_id": "doc_" + secrets.token_hex(6), "user_id": user["user_id"],
        "doc_type": "quote", "number": None,
        "title": (body.title or f"DPGF — {doc.get('filename') or 'bordereau'}")[:160],
        "client_id": body.client_id,
        "client": await _client_snapshot(body.client_id, user),
        "status": "draft", "lines": lines, "notes": "\n".join(notes)[:3000],
        "payment_terms": "", "deposit_pct": 0, "totals": totals,
        "issue_date": None, "due_date": None,
        "source": "dpgf", "dpgf_file_id": file_id,
        "created_at": now, "updated_at": now,
    }
    await db.pro_documents.insert_one(dict(quote))
    quote.pop("_id", None)
    await db.dpgf_imports.update_one({"file_id": file_id, "user_id": user["user_id"]},
                                     {"$set": {"quote_doc_id": quote["doc_id"]}})
    remembered = await remember_prices(
        user["user_id"],
        # prix de base (hors marge et hors impact CCTP) : une bibliothèque garde des coûts
        # de référence, sinon chaque conversion rechargerait la marge de la précédente
        [{"designation": x["designation"], "unit": x.get("unit") or "u",
          "unit_price": x.get("pu_base"), "price_source": x.get("source") or "",
          "lot": x.get("lot") or x.get("category") or "", "vat_rate": x.get("vat_rate")}
         for x in rows if not x.get("excluded") and x.get("pu_base")],
        origin=f"DPGF — {doc.get('filename') or file_id}")
    from engines import activity
    await activity.log(user, "quote.dpgf", "document", quote["title"],
                       {"doc_id": quote["doc_id"], "lines": len(lines)})
    return {"doc_id": quote["doc_id"], "lines": len(lines), "totals": totals,
            "remembered_prices": remembered}


@router.post("/{file_id}/remember")
async def remember_study_prices(file_id: str, user=Depends(current_user)) -> dict:
    """Enregistre les prix retenus de l'étude dans la bibliothèque de l'entreprise.

    Le prix mémorisé est le prix de base (avant marge et avant impact CCTP) : c'est un coût
    de référence réutilisable, pas le prix de vente d'une affaire particulière.
    """
    doc = await _study(file_id, user["user_id"])
    items = [{"designation": x["designation"], "unit": x.get("unit") or "u",
              "unit_price": x.get("pu_base"), "price_source": x.get("source") or "",
              "lot": x.get("lot") or x.get("category") or "", "vat_rate": x.get("vat_rate")}
             for x in doc.get("lines", [])
             if not x.get("excluded") and x.get("pu_base")]
    saved = await remember_prices(user["user_id"], items,
                                  origin=f"DPGF — {doc.get('label') or doc.get('filename')}")
    return {"remembered": saved, "candidates": len(items)}


@router.get("/file/{file_id}")
async def download_dpgf(file_id: str, src: int | None = None, user=Depends(current_user)):
    """Bordereaux d'origine remplis avec les prix retenus (ZIP si plusieurs fichiers)."""
    doc = await _study(file_id, user["user_id"])
    sources = doc.get("sources") or ([{"src": 0, "filename": doc.get("filename"),
                                       "path": doc.get("source_path")}]
                                     if doc.get("source_path") else [])
    if not sources:
        raise HTTPException(404, "Fichier source introuvable")
    rows = doc.get("lines", [])

    def filled_for(s: dict) -> bytes:
        raw, _ = storage.get_object(s["path"])
        return dpgf_engine.write_workbook(raw, [r for r in rows if r.get("src", 0) == s["src"]])

    if src is not None or len(sources) == 1:
        s = next((x for x in sources if x["src"] == (src or 0)), sources[0])
        name = (s.get("filename") or "dpgf").rsplit(".", 1)[0] + "_chiffre.xlsx"
        return StreamingResponse(io.BytesIO(filled_for(s)), media_type=XLSX_MIME,
                                 headers={"Content-Disposition": f'attachment; filename="{name}"'})

    import zipfile
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for s in sources:
            base = (s.get("filename") or f"bordereau_{s['src']}").rsplit(".", 1)[0]
            z.writestr(f"{base}_chiffre.xlsx", filled_for(s))
    buf.seek(0)
    return StreamingResponse(buf, media_type="application/zip",
                             headers={"Content-Disposition": 'attachment; filename="dpgf_chiffre.zip"'})


@router.delete("/{file_id}")
async def delete_import(file_id: str, user=Depends(current_user)) -> dict:
    await _study(file_id, user["user_id"])
    await db.dpgf_imports.delete_one({"file_id": file_id, "user_id": user["user_id"]})
    return {"ok": True}


# ─────────────────────────  Demande de prix aux sous-traitants  ─────────────────────────

class RfqIn(BaseModel):
    lot: str = Field(min_length=1, max_length=160)
    supplier_ids: list[str] = Field(default_factory=list)
    emails: list[str] = Field(default_factory=list)
    message: str = Field(default="", max_length=1500)
    due_days: int = Field(default=7, ge=1, le=60)
    origin_url: str = Field(default="", max_length=200)


def _rfq_public(rfq: dict, origin: str = "") -> dict:
    return {
        "rfq_id": rfq["rfq_id"], "lot": rfq["lot"], "file_id": rfq["file_id"],
        "due_date": rfq.get("due_date"), "created_at": rfq.get("created_at"),
        "lines": rfq.get("lines", []),
        "recipients": [{
            "name": r.get("name"), "email": r.get("email"), "token": r.get("token"),
            "sent": bool(r.get("sent_at")), "email_status": r.get("email_status"),
            "responded_at": r.get("responded_at"), "total_ht": r.get("total_ht"),
            "note": r.get("note"), "prices": r.get("prices") or {},
            "link": f"{origin.rstrip('/')}/appel-offres/{r.get('token')}" if origin else None,
        } for r in rfq.get("recipients", [])],
    }


@router.post("/{file_id}/rfq")
async def create_rfq(file_id: str, body: RfqIn, user=Depends(current_user)) -> dict:
    """Envoie une demande de prix pour un lot à des sous-traitants / fournisseurs."""
    doc = await _study(file_id, user["user_id"])
    lot_lines = [{"line_id": x["line_id"], "designation": x["designation"],
                  "unit": x.get("unit") or "u", "qty": x.get("qty")}
                 for x in doc.get("lines", []) if x["lot"] == body.lot and not x["excluded"]]
    if not lot_lines:
        raise HTTPException(400, "Aucune ligne à chiffrer dans ce lot")

    recipients: list[dict] = []
    if body.supplier_ids:
        sups = await db.suppliers.find(
            {"user_id": user["user_id"], "supplier_id": {"$in": body.supplier_ids[:20]}},
            {"_id": 0, "supplier_id": 1, "name": 1, "email": 1}).to_list(20)
        for sp in sups:
            if sp.get("email"):
                recipients.append({"supplier_id": sp["supplier_id"], "name": sp.get("name") or "",
                                   "email": sp["email"].strip().lower()})
    for em in body.emails[:20]:
        em = (em or "").strip().lower()
        if "@" in em and em not in [r["email"] for r in recipients]:
            recipients.append({"supplier_id": None, "name": "", "email": em})
    if not recipients:
        raise HTTPException(400, "Aucun destinataire avec e-mail valide")

    due = (datetime.now(timezone.utc) + timedelta(days=body.due_days)).date().isoformat()
    origin = (body.origin_url or "").rstrip("/")
    company = (await db.users.find_one({"user_id": user["user_id"]},
                                       {"_id": 0, "company_name": 1, "name": 1})) or {}
    sender = company.get("company_name") or company.get("name") or "ConstruPilot"
    rfq = {"rfq_id": "rfq_" + secrets.token_hex(6), "user_id": user["user_id"],
           "file_id": file_id, "lot": body.lot, "lines": lot_lines,
           "message": body.message.strip(), "due_date": due, "created_at": _now(),
           "recipients": []}
    from engines import emailer
    for r in recipients:
        token = secrets.token_urlsafe(18)
        link = f"{origin}/appel-offres/{token}" if origin else ""
        status = "skipped"
        if link:
            html = emailer.wrap_html(
                f"Demande de prix — {body.lot}",
                f"<p>Bonjour{(' ' + r['name']) if r['name'] else ''},</p>"
                f"<p><strong>{sender}</strong> vous consulte pour le lot <strong>{body.lot}</strong> "
                f"({len(lot_lines)} ligne(s)). Réponse souhaitée avant le <strong>{due}</strong>.</p>"
                + (f"<blockquote>{body.message.strip()}</blockquote>" if body.message.strip() else "")
                + "<p>Saisissez vos prix unitaires en ligne (aucun compte nécessaire) :</p>",
                cta_url=link, cta_label="Répondre à la demande de prix")
            try:
                await emailer.send_email(r["email"], f"Demande de prix — {body.lot} ({sender})", html)
                status = "sent"
            except Exception as exc:  # noqa: BLE001 — le lien reste utilisable manuellement
                logger.warning("rfq email failed: %s", exc)
                status = "failed"
        rfq["recipients"].append({**r, "token": token, "sent_at": _now(),
                                  "email_status": status, "prices": {}, "responded_at": None,
                                  "total_ht": None, "note": ""})
    await db.dpgf_rfq.insert_one(dict(rfq))
    rfq.pop("_id", None)
    return _rfq_public(rfq, origin)


@router.get("/{file_id}/rfq")
async def list_rfq(file_id: str, origin_url: str = "", user=Depends(current_user)) -> list[dict]:
    await _study(file_id, user["user_id"])
    rows = await db.dpgf_rfq.find({"user_id": user["user_id"], "file_id": file_id},
                                  {"_id": 0}).sort("created_at", -1).to_list(50)
    return [_rfq_public(r, origin_url) for r in rows]


class OfferIn(BaseModel):
    token: str
    prices: dict[str, float] = Field(default_factory=dict)
    note: str = Field(default="", max_length=1000)
    contact_name: str = Field(default="", max_length=120)


def _record_offer(rfq: dict, token: str, prices: dict, note: str, contact: str) -> dict:
    rec = next((r for r in rfq.get("recipients", []) if r.get("token") == token), None)
    if not rec:
        raise HTTPException(404, "Destinataire introuvable")
    clean = {}
    for line in rfq.get("lines", []):
        v = prices.get(line["line_id"])
        if v is not None and float(v) > 0:
            clean[line["line_id"]] = round(float(v), 2)
    if not clean:
        raise HTTPException(400, "Aucun prix saisi")
    total = round(sum(clean[l["line_id"]] * (l.get("qty") or 0)
                      for l in rfq["lines"] if l["line_id"] in clean), 2)
    rec.update({"prices": clean, "total_ht": total, "responded_at": _now(),
                "note": (note or "").strip()[:1000]})
    if contact:
        rec["name"] = contact.strip()[:120]
    return rec


@router.post("/{file_id}/rfq/{rfq_id}/offer")
async def record_offer_pro(file_id: str, rfq_id: str, body: OfferIn,
                           user=Depends(current_user)) -> dict:
    """Saisie manuelle d'une offre reçue par téléphone ou par e-mail."""
    rfq = await db.dpgf_rfq.find_one({"rfq_id": rfq_id, "user_id": user["user_id"]}, {"_id": 0})
    if not rfq:
        raise HTTPException(404, "Demande de prix introuvable")
    _record_offer(rfq, body.token, body.prices, body.note, body.contact_name)
    await db.dpgf_rfq.update_one({"rfq_id": rfq_id}, {"$set": {"recipients": rfq["recipients"]}})
    return _rfq_public(rfq)


class ApplyOfferIn(BaseModel):
    token: str


@router.post("/{file_id}/rfq/{rfq_id}/apply")
async def apply_offer(file_id: str, rfq_id: str, body: ApplyOfferIn,
                      user=Depends(current_user)) -> dict:
    """Retient l'offre d'un sous-traitant comme prix de l'étude pour les lignes du lot."""
    doc = await _study(file_id, user["user_id"])
    rfq = await db.dpgf_rfq.find_one({"rfq_id": rfq_id, "user_id": user["user_id"]}, {"_id": 0})
    if not rfq:
        raise HTTPException(404, "Demande de prix introuvable")
    rec = next((r for r in rfq.get("recipients", []) if r.get("token") == body.token), None)
    if not rec or not rec.get("prices"):
        raise HTTPException(400, "Cette offre n'a pas encore de prix")
    who = rec.get("name") or rec.get("email")
    rows = doc.get("lines", [])
    applied = 0
    for x in rows:
        pu = rec["prices"].get(x["line_id"])
        if pu is None:
            continue
        x["pu_sub"] = round(float(pu), 2)
        x["pu_base"] = x["pu_sub"]
        x["source"] = "soustraitant"
        x["offer_from"] = who
        x["excluded"] = False
        applied += 1
    totals = dpgf_engine.finalise(rows)
    await db.dpgf_imports.update_one(
        {"file_id": file_id, "user_id": user["user_id"]},
        {"$set": {"lines": rows, "lot_totals": totals["lots"],
                  "grand_total_ht": totals["grand_total_ht"], "priced": totals["priced"]}})
    doc.update({"lines": rows, "lot_totals": totals["lots"],
                "grand_total_ht": totals["grand_total_ht"], "priced": totals["priced"]})
    return {"applied": applied, "from": who, "study": _public(doc)}


# ---- Page publique du sous-traitant (sans compte) --------------------------

public_router = APIRouter(prefix="/public/rfq", tags=["dpgf"])


@public_router.get("/{token}")
async def public_rfq(token: str) -> dict:
    rfq = await db.dpgf_rfq.find_one({"recipients.token": token}, {"_id": 0})
    if not rfq:
        raise HTTPException(404, "Lien invalide ou expiré")
    rec = next(r for r in rfq["recipients"] if r["token"] == token)
    owner = (await db.users.find_one({"user_id": rfq["user_id"]},
                                     {"_id": 0, "company_name": 1, "name": 1})) or {}
    return {"lot": rfq["lot"], "due_date": rfq.get("due_date"),
            "message": rfq.get("message") or "",
            "company": owner.get("company_name") or owner.get("name") or "ConstruPilot",
            "recipient": {"name": rec.get("name") or "", "email": rec.get("email")},
            "responded_at": rec.get("responded_at"),
            "prices": rec.get("prices") or {},
            "lines": rfq.get("lines", [])}


class PublicOfferIn(BaseModel):
    prices: dict[str, float] = Field(default_factory=dict)
    note: str = Field(default="", max_length=1000)
    contact_name: str = Field(default="", max_length=120)


@public_router.post("/{token}")
async def public_rfq_submit(token: str, body: PublicOfferIn) -> dict:
    rfq = await db.dpgf_rfq.find_one({"recipients.token": token}, {"_id": 0})
    if not rfq:
        raise HTTPException(404, "Lien invalide ou expiré")
    rec = _record_offer(rfq, token, body.prices, body.note, body.contact_name)
    await db.dpgf_rfq.update_one({"rfq_id": rfq["rfq_id"]},
                                 {"$set": {"recipients": rfq["recipients"]}})
    await db.notifications.insert_one({
        "notif_id": "n_" + secrets.token_hex(5), "user_id": rfq["user_id"],
        "type": "rfq_offer", "url": "/dashboard",
        "message": f"Offre reçue pour le lot {rfq['lot']} : {rec['total_ht']:.2f} € HT "
                   f"({rec.get('name') or rec.get('email')}).",
        "read": False, "created_at": _now()})
    return {"ok": True, "total_ht": rec["total_ht"]}


class GlobalMarginIn(BaseModel):
    margin_pct: float = Field(ge=-50, le=200)


@router.patch("/{file_id}/global-margin")
async def set_global_margin(file_id: str, body: GlobalMarginIn,
                            user=Depends(current_user)) -> dict:
    """Applique un coefficient unique à TOUTE l'étude en un clic (utile pour une variante).

    Remplace les coefficients par lot : on teste une hypothèse de marge globale sans
    retoucher chaque lot. Les prix saisis à la main restent inchangés (finalise ne coeffe
    que bibliothèque / IA / sous-traitant).
    """
    doc = await _study(file_id, user["user_id"])
    rows = doc.get("lines", [])
    pct = float(body.margin_pct)
    for x in rows:
        x["margin_pct"] = pct
    directives = doc.get("directives") or {}
    directives["margin_pct"] = pct
    directives["lot_margins"] = {}
    totals = dpgf_engine.finalise(rows)
    await db.dpgf_imports.update_one(
        {"file_id": file_id, "user_id": user["user_id"]},
        {"$set": {"lines": rows, "directives": directives, "lot_totals": totals["lots"],
                  "grand_total_ht": totals["grand_total_ht"], "priced": totals["priced"]}})
    doc.update({"lines": rows, "directives": directives, "lot_totals": totals["lots"],
                "grand_total_ht": totals["grand_total_ht"], "priced": totals["priced"]})
    return _public(doc)


class LotMarginIn(BaseModel):
    lot: str = Field(min_length=1, max_length=200)
    margin_pct: float = Field(ge=-50, le=200)


@router.patch("/{file_id}/lot-margin")
async def set_lot_margin(file_id: str, body: LotMarginIn, user=Depends(current_user)) -> dict:
    """Coefficient propre à un lot, appliqué aux prix bibliothèque / IA / sous-traitant."""
    doc = await _study(file_id, user["user_id"])
    rows = doc.get("lines", [])
    touched = 0
    for x in rows:
        if x["lot"] == body.lot:
            x["margin_pct"] = float(body.margin_pct)
            touched += 1
    if not touched:
        raise HTTPException(404, "Lot introuvable")
    directives = doc.get("directives") or {}
    directives["lot_margins"] = {**(directives.get("lot_margins") or {}),
                                 body.lot: float(body.margin_pct)}
    totals = dpgf_engine.finalise(rows)
    await db.dpgf_imports.update_one(
        {"file_id": file_id, "user_id": user["user_id"]},
        {"$set": {"lines": rows, "directives": directives, "lot_totals": totals["lots"],
                  "grand_total_ht": totals["grand_total_ht"], "priced": totals["priced"]}})
    doc.update({"lines": rows, "directives": directives, "lot_totals": totals["lots"],
                "grand_total_ht": totals["grand_total_ht"], "priced": totals["priced"]})
    return _public(doc)


@router.get("/{file_id}/offers-compare")
async def compare_offers(file_id: str, user=Depends(current_user)) -> dict:
    """Comparatif lot par lot : mon chiffrage face aux offres reçues (écart en %)."""
    doc = await _study(file_id, user["user_id"])
    rows = {x["line_id"]: x for x in doc.get("lines", [])}
    rfqs = await db.dpgf_rfq.find({"user_id": user["user_id"], "file_id": file_id},
                                  {"_id": 0}).to_list(100)
    lots: dict[str, dict] = {}
    for rfq in rfqs:
        slot = lots.setdefault(rfq["lot"], {"lot": rfq["lot"], "offers": [], "requested": 0,
                                            "answered": 0})
        for rec in rfq.get("recipients", []):
            slot["requested"] += 1
            prices = rec.get("prices") or {}
            if not prices:
                continue
            slot["answered"] += 1
            mine = 0.0
            theirs = 0.0
            covered = 0
            for lid, pu in prices.items():
                row = rows.get(lid)
                if not row or row.get("excluded"):
                    continue
                qty = float(row.get("qty") or 0)
                if row.get("pu"):
                    mine = round(mine + float(row["pu"]) * qty, 2)
                theirs = round(theirs + float(pu) * qty, 2)
                covered += 1
            delta = round((theirs - mine) / mine * 100, 1) if mine else None
            slot["offers"].append({
                "rfq_id": rfq["rfq_id"], "token": rec.get("token"),
                "name": rec.get("name") or rec.get("email"), "email": rec.get("email"),
                "total_ht": theirs, "my_total_ht": mine, "lines_covered": covered,
                "delta_pct": delta, "note": rec.get("note") or "",
                "responded_at": rec.get("responded_at"),
            })
    out = []
    for slot in lots.values():
        offers = sorted(slot["offers"], key=lambda o: o["total_ht"])
        best = offers[0] if offers else None
        my_lot = next((x["total_ht"] for x in doc.get("lot_totals", []) if x["lot"] == slot["lot"]), 0)
        out.append({**slot, "offers": offers,
                    "my_lot_total_ht": my_lot,
                    "best": best,
                    "saving_ht": round(best["my_total_ht"] - best["total_ht"], 2) if best else 0})
    out.sort(key=lambda x: x["lot"])
    return {"lots": out, "grand_total_ht": doc.get("grand_total_ht", 0)}


# ─────────────────────────  Nom de l'étude & alerte de marge  ─────────────────────────

class LabelIn(BaseModel):
    label: str = Field(default="", max_length=140)


@router.patch("/{file_id}/label")
async def rename_study(file_id: str, body: LabelIn, user=Depends(current_user)) -> dict:
    """Nomme l'étude (ex. « Houilles — Lot 2 variante A »)."""
    doc = await _study(file_id, user["user_id"])
    label = body.label.strip()[:140]
    await db.dpgf_imports.update_one({"file_id": file_id, "user_id": user["user_id"]},
                                     {"$set": {"label": label}})
    doc["label"] = label
    return _public(doc)


# ─────────────────────────  Variantes de chiffrage  ─────────────────────────

class DuplicateIn(BaseModel):
    label: str = Field(default="", max_length=140)


@router.post("/{file_id}/duplicate")
async def duplicate_study(file_id: str, body: DuplicateIn, user=Depends(current_user)) -> dict:
    """Duplique l'étude en une variante indépendante (mêmes lignes, marges ajustables à part).

    Sert à comparer deux hypothèses de marge côte à côte : on duplique, on change le
    coefficient sur la copie, puis on lit l'écart de total dans le comparatif de variantes.
    Les deux études partagent un ``variant_group`` pour être rapprochées.
    """
    doc = await _study(file_id, user["user_id"])
    group = doc.get("variant_group") or file_id
    if not doc.get("variant_group"):
        await db.dpgf_imports.update_one({"file_id": file_id, "user_id": user["user_id"]},
                                         {"$set": {"variant_group": group}})
    new_fid = "dpgf_" + uuid.uuid4().hex[:12]
    base_label = (doc.get("label") or doc.get("filename") or "Chiffrage").strip()
    copy = {k: v for k, v in doc.items() if k != "_id"}
    copy.update({
        "file_id": new_fid, "variant_group": group,
        "label": (body.label.strip() or f"{base_label} — variante")[:140],
        "created_at": _now(), "quote_doc_id": None,
        "lines": [dict(x) for x in doc.get("lines", [])],
        "gaps": [dict(g) for g in doc.get("gaps", [])],
    })
    await db.dpgf_imports.insert_one(dict(copy))
    return _public(copy)


@router.get("/{file_id}/variants")
async def study_variants(file_id: str, user=Depends(current_user)) -> dict:
    """Comparatif côte à côte des variantes d'une étude : total et marge par lot."""
    doc = await _study(file_id, user["user_id"])
    group = doc.get("variant_group") or file_id
    docs = await db.dpgf_imports.find(
        {"user_id": user["user_id"], "$or": [{"variant_group": group}, {"file_id": group}]},
        {"_id": 0, "file_id": 1, "label": 1, "filename": 1, "created_at": 1,
         "grand_total_ht": 1, "lot_totals": 1, "quote_doc_id": 1, "lines": 1}
    ).sort("created_at", 1).to_list(20)
    variants = []
    lot_names: list[str] = []
    for d in docs:
        lots_map = {x["lot"]: x for x in d.get("lot_totals", [])}
        cost = sum(float(x.get("cost_ht") or 0) for x in d.get("lot_totals", []))
        margin = round(d.get("grand_total_ht", 0) - cost, 2)
        variants.append({
            "file_id": d["file_id"], "label": d.get("label") or d.get("filename") or "Chiffrage",
            "created_at": d.get("created_at"), "quote_doc_id": d.get("quote_doc_id"),
            "current": d["file_id"] == file_id,
            "grand_total_ht": d.get("grand_total_ht", 0),
            "margin_ht": margin,
            "margin_pct": round(margin / cost * 100, 1) if cost else 0.0,
            "line_count": len(d.get("lines", [])),
            "lots": {k: {"total_ht": v.get("total_ht", 0), "margin_pct": v.get("margin_pct", 0),
                         "margin_ht": v.get("margin_ht", 0)} for k, v in lots_map.items()},
        })
        for k in lots_map:
            if k not in lot_names:
                lot_names.append(k)
    return {"variants": variants, "lots": sorted(lot_names)}


class EmailNotifyIn(BaseModel):
    enabled: bool


@router.get("/settings/notify-email")
async def get_notify_email(user=Depends(current_user)) -> dict:
    u = await db.users.find_one({"user_id": user["user_id"]},
                                {"_id": 0, "dpgf_email_notify": 1}) or {}
    return {"enabled": u.get("dpgf_email_notify") is not False, "min_lines": EMAIL_MIN_LINES}


@router.patch("/settings/notify-email")
async def set_notify_email(body: EmailNotifyIn, user=Depends(current_user)) -> dict:
    await db.users.update_one({"user_id": user["user_id"]},
                              {"$set": {"dpgf_email_notify": bool(body.enabled)}})
    return {"enabled": bool(body.enabled)}


class MarginSettingIn(BaseModel):
    min_margin_pct: float = Field(ge=0, le=90)


@router.get("/settings/margin")
async def get_margin_setting(user=Depends(current_user)) -> dict:
    u = await db.users.find_one({"user_id": user["user_id"]},
                                {"_id": 0, "dpgf_min_margin_pct": 1}) or {}
    return {"min_margin_pct": float(u.get("dpgf_min_margin_pct") or 0)}


@router.patch("/settings/margin")
async def set_margin_setting(body: MarginSettingIn, user=Depends(current_user)) -> dict:
    await db.users.update_one({"user_id": user["user_id"]},
                              {"$set": {"dpgf_min_margin_pct": float(body.min_margin_pct)}})
    return {"min_margin_pct": float(body.min_margin_pct)}
