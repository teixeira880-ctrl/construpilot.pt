"""Programa IA de opções — o cliente assinala, valida e depois a IA executa sozinha.

Só as opções assinaladas e validadas são executadas (nenhum acréscimo implícito).
Cada opção chama os motores determinísticos portugueses existentes (RTIEBT, DR 23/95, EN 12831-1, NP EN 1264,
Eurocódigos NP EN, REH); o prompt preparado só serve para redigir a síntese do entregável.

Fluxo: GET /missions/catalog → POST /missions/plan (resumo, nada é executado)
→ POST /agents/{run_id}/launch (fila e worker dos agentes: segundo plano,
lease, cancelamento, notificação) → GET /missions/{run_id}.
"""
from __future__ import annotations

import logging
import secrets
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from core.db import db
from core.security import admin_user, current_user
from engines import missions as M
from routes.plans_common import _now

log = logging.getLogger("missions")

router = APIRouter(tags=["missions"], prefix="/missions")


async def _option_allowed(key: str, user: dict) -> None:
    """Mesmos direitos que o ecrã de origem de cada motor."""
    from routes.agents import _authorize_agent
    if key == "controle":
        await _authorize_agent("supervise", user)
    elif key in ("devis", "dossier", "dpgf"):
        await _authorize_agent("devis", user)
    elif key in ("plan_electricite", "plan_plomberie", "thermique", "structure", "dpe"):
        from engines.access import require_level
        await _authorize_agent("metre", user)
        await require_level("pro")(user=user)
    else:  # analyse_plans, metre, planning, partage
        await _authorize_agent("metre", user)


async def _allowed_catalog(user: dict) -> dict[str, dict]:
    catalog = await M.effective_options(db)
    out = {}
    for key, spec in catalog.items():
        if not spec["enabled"]:
            continue
        try:
            await _option_allowed(key, user)
        except HTTPException:
            continue
        out[key] = spec
    return out


def _public_option(spec: dict) -> dict:
    return {k: spec[k] for k in ("key", "name", "group", "desc", "needs", "depends_on", "deliverable")}


@router.get("/catalog")
async def catalog(user=Depends(current_user)) -> dict:
    return {"options": [_public_option(s) for s in (await _allowed_catalog(user)).values()]}


class MissionIn(BaseModel):
    options: list[str] = Field(min_length=1, max_length=20)
    chantier_id: Optional[str] = Field(None, min_length=1, max_length=80)
    plan_ids: list[str] = Field(default_factory=list, max_length=50)
    note: str = Field("", max_length=1000)


@router.post("/plan")
async def propose(body: MissionIn, user=Depends(current_user)) -> dict:
    """Resumo da seleção SEM executar nada. O cliente valida-o a seguir."""
    from routes.agents import _authorize_agent, _load_owned_plans, _plan_status
    await _authorize_agent("mission", user)
    if body.chantier_id:
        from routes.chantiers import _get
        await _get(body.chantier_id, user["user_id"])
    allowed = await _allowed_catalog(user)
    try:
        ordered = M.resolve(body.options, allowed, has_plans=bool(body.plan_ids),
                            has_chantier=bool(body.chantier_id))
    except M.MissionError as exc:
        raise HTTPException(422, str(exc))
    plans = await _load_owned_plans(body.plan_ids, user) if body.plan_ids else []
    if body.chantier_id and any(p.get("chantier_id") != body.chantier_id for p in plans):
        raise HTTPException(422, "Uma planta selecionada pertence a outro processo")
    plan_status = await _plan_status(plans, user)

    warnings = [f"« {s['filename']} » não tem nenhuma medição nem divisão levantada: as opções de plantas vão assinalá-lo."
                for s in plan_status if not s["ready"]]
    if "devis" in ordered and not sum(s["priced"] for s in plan_status):
        warnings.append("Nenhuma medição está associada a um artigo: o orçamento ficará vazio enquanto não associar artigos.")
    if "partage" in ordered and not SHAREABLE & set(ordered):
        warnings.append("A partilha só contém os entregáveis produzidos por este programa: assinale também uma planta de "
                        "execução, uma nota de cálculo, o pré-certificado ou o mapa de quantidades / caderno de encargos.")
    if "planning" in ordered and "devis" not in ordered:
        warnings.append("O planeamento parte dos orçamentos já associados ao processo; sem orçamento, ficará vazio.")

    steps = [{"key": k, "name": allowed[k]["name"], "deliverable": allowed[k]["deliverable"],
              "depends_on": allowed[k]["depends_on"], "prompt": allowed[k]["prompt"],
              "prompt_version": allowed[k]["prompt_version"], "status": "pending"} for k in ordered]
    run = {
        "run_id": "agr_" + secrets.token_hex(6), "user_id": user["user_id"], "agent": "mission",
        "prompt": body.note.strip(), "plan_ids": [s["plan_id"] for s in plan_status], "quote_ids": [],
        "chantier_id": body.chantier_id, "organization_id": user.get("organization_id"),
        "plan_status": plan_status, "warnings": warnings,
        "steps": [{"key": s["key"], "label": s["name"], "detail": s["deliverable"]} for s in steps],
        "mission": {"options": ordered, "steps": steps},
        "status": "proposed", "created_at": _now(),
    }
    await db.agent_runs.insert_one(dict(run))
    run.pop("_id", None)
    return {"run": _public_run(run)}


def _public_run(run: dict) -> dict:
    """O prompt completo fica do lado do servidor (rasto); o cliente vê o entregável."""
    out = {k: v for k, v in run.items() if k not in ("worker", "lease_until")}
    mission = dict(out.get("mission") or {})
    mission["steps"] = [{k: v for k, v in s.items() if k != "prompt"} for s in mission.get("steps") or []]
    out["mission"] = mission
    for key in ("result", "partial_result"):
        if isinstance(out.get(key), dict) and out[key].get("kind") == "mission":
            out[key] = {**out[key], "steps": [{k: v for k, v in s.items() if k != "prompt"}
                                              for s in out[key].get("steps") or []]}
    return out


@router.get("/{run_id}")
async def get_mission(run_id: str, user=Depends(current_user)) -> dict:
    run = await db.agent_runs.find_one({"run_id": run_id, "user_id": user["user_id"], "agent": "mission"}, {"_id": 0})
    if not run:
        raise HTTPException(404, "Programa não encontrado")
    return {"run": _public_run(run)}


# ============================ Execução ============================

async def _exec_analyse(ctx) -> dict:
    from btp_ai.routes import get_analysis
    rows = []
    for s in ctx["run"]["plan_status"]:
        try:
            a = await get_analysis(s["plan_id"], user=ctx["user"])
        except HTTPException as exc:
            rows.append({"plan_id": s["plan_id"], "filename": s["filename"], "error": str(exc.detail)[:200]})
            continue
        except (TypeError, AttributeError, ValueError):    # planta sem divisões utilizáveis: o motor não produz análise
            rows.append({"plan_id": s["plan_id"], "filename": s["filename"], "error": "Análise indisponível nesta planta"})
            continue
        analysis = a.get("analysis") or {}
        rows.append({"plan_id": s["plan_id"], "filename": s["filename"], "state": a.get("state"),
                     "elements": len(a.get("elements") or []), "stats": a.get("stats") or {},
                     "missing": len(analysis.get("missing") or []), "conflicts": len(analysis.get("conflicts") or []),
                     "link": f"/analyse/{s['plan_id']}"})
    if rows and all(r.get("error") for r in rows):
        raise HTTPException(422, "Nenhuma planta pôde ser analisada")
    return {"kind": "analysis", "plans": rows}


async def _exec_controle(ctx) -> dict:
    from engines.platform_supervisor import run_supervisor
    return await run_supervisor(db, ctx["user"], {**ctx["run"], "quote_ids": []}, repair=False)


async def _exec_agent(agent: str, ctx) -> dict:
    from routes.agents import _do_execute
    return await _do_execute({**ctx["run"], "agent": agent}, ctx["body"], ctx["user"])


async def _mep_studies(ctx) -> list[dict]:
    """Um estudo MEP por planta, partilhado entre as opções de eletricidade e canalização."""
    if "mep" in ctx["cache"]:
        return ctx["cache"]["mep"]
    from engines.mep import generate
    from engines.mep.adapter import AdapterError, from_takeoff
    from routes.mep import DEFAULT_COUNTRY, _save
    uid = ctx["user"]["user_id"]
    rows = []
    for s in ctx["run"]["plan_status"]:
        plan = await db.plans_takeoff.find_one(
            {"plan_id": s["plan_id"], "user_id": uid},
            {"_id": 0, "plan_id": 1, "filename": 1, "rooms": 1, "calibrations": 1, "structure": 1, "mep_fixtures": 1})
        if not plan:
            rows.append({"plan_id": s["plan_id"], "filename": s["filename"], "error": "Planta não encontrada"})
            continue
        try:
            study = generate(from_takeoff(plan, None, DEFAULT_COUNTRY, {}))
        except (AdapterError, ValueError) as exc:
            rows.append({"plan_id": s["plan_id"], "filename": s["filename"], "error": str(exc)[:200]})
            continue
        saved = await _save(uid, study, f"Planos de execução — {plan.get('filename') or ''}", s["plan_id"])
        rows.append({"plan_id": s["plan_id"], "filename": s["filename"], "study_id": saved["study_id"],
                     "summary": saved.get("summary") or {}, "pdf": f"/mep/studies/{saved['study_id']}/pdf"})
    ctx["cache"]["mep"] = rows
    return rows


async def _exec_mep(layer: str, ctx) -> dict:
    rows = await _mep_studies(ctx)
    if rows and all(r.get("error") for r in rows):
        raise HTTPException(422, rows[0]["error"])
    return {"kind": "mep", "layer": layer, "studies": [
        {**r, "svg": f"/mep/studies/{r['study_id']}/svg?layer={layer}"} if r.get("study_id") else r for r in rows]}


async def _exec_planning(ctx) -> dict:
    from routes import planning as PL
    cid, user = ctx["run"]["chantier_id"], ctx["user"]
    existing = await PL.COLL.find_one({"chantier_id": cid, "user_id": user["user_id"]}, {"_id": 1})
    if existing:
        # Nunca se substitui um planeamento introduzido pelo profissional.
        return {"kind": "planning", "kept_existing": True, "link": f"/planning?chantier={cid}"}
    out = await PL.init_plan(cid, PL.InitIn(), user=user)
    project = (out.get("schedule") or {}).get("project") or {}
    return {"kind": "planning", "kept_existing": False, "tasks": len(out.get("tasks") or []),
            "from_lots": out.get("from_lots") or [], "start_date": project.get("start_date"),
            "end_date": project.get("end_date"), "link": f"/planning?chantier={cid}"}


async def _exec_metre(ctx) -> dict:
    """Síntese de medição do agente « metre », completada com as divisões relevadas (contagens da base, sem cálculo)."""
    out = await _exec_agent("metre", ctx)
    ids = ctx["run"].get("plan_ids") or []
    plans = await db.plans_takeoff.find({"plan_id": {"$in": ids}, "user_id": ctx["user"]["user_id"]},
                                        {"_id": 0, "plan_id": 1, "rooms": 1}).to_list(51) if ids else []
    rooms = {p["plan_id"]: p.get("rooms") or [] for p in plans}
    for row in out.get("plans") or []:
        rs = rooms.get(row.get("plan_id"), [])
        row["rooms"] = len(rs)
        row["rooms_surface_m2"] = round(sum(float(r.get("surface_m2") or 0) for r in rs), 2)
    out["total_rooms"] = sum(len(v) for v in rooms.values())
    out["total_surface_m2"] = round(sum(float(r.get("surface_m2") or 0) for v in rooms.values() for r in v), 2)
    return out


async def _levels(ctx) -> list[dict]:
    """Pisos lidos em cada planta (mesma leitura que o motor de instalações), partilhados entre opções."""
    if "levels" in ctx["cache"]:
        return ctx["cache"]["levels"]
    from engines.calc_lots.depuis_plan import niveaux
    from engines.mep.adapter import AdapterError
    rows = []
    for s in ctx["run"]["plan_status"]:
        plan = await db.plans_takeoff.find_one({"plan_id": s["plan_id"], "user_id": ctx["user"]["user_id"]},
            {"_id": 0, "plan_id": 1, "filename": 1, "rooms": 1, "calibrations": 1, "structure": 1, "mep_fixtures": 1})
        if not plan:
            rows.append({"plan_id": s["plan_id"], "filename": s["filename"], "error": "Planta não encontrada"})
            continue
        try:
            rows.append({"plan_id": s["plan_id"], "filename": s["filename"], "levels": niveaux(plan)})
        except (AdapterError, ValueError) as exc:
            rows.append({"plan_id": s["plan_id"], "filename": s["filename"], "error": str(exc)[:200]})
    ctx["cache"]["levels"] = rows
    return rows


def concelho_do_processo(chantier: dict) -> str | None:
    """Concelho reconhecido pelo clima REH a partir da localidade ou da morada do processo (None se nenhum)."""
    from engines.calc_lots import reh
    import re
    cands = [chantier.get("city")] + [p.strip() for p in (chantier.get("address") or "").split(",")]
    for c in cands:
        c = re.sub(r"^\s*\d{4}(-\d{3})?\s*", "", c or "")     # código postal à frente da localidade
        if not c:
            continue
        try:
            reh.clima(c)
        except ValueError:
            continue
        return c.strip()
    return None


MIME = {"pdf": "application/pdf", "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document"}


async def _save_note(ctx, kind: str, title: str, data: bytes, summary: dict, ext: str = "pdf") -> dict:
    """Entregável guardado (PDF, Excel, Word), descarregável pelo proprietário e partilhável pela opção « partilha »."""
    import base64
    note_id = "mnote_" + secrets.token_hex(6)
    await db.mission_notes.insert_one({"note_id": note_id, "user_id": ctx["user"]["user_id"], "run_id": ctx["run"]["run_id"],
                                       "chantier_id": ctx["run"].get("chantier_id"),
                                       "kind": kind, "title": title, "ext": ext, "data_b64": base64.b64encode(data).decode(),
                                       "summary": summary, "created_at": _now()})
    return {"note_id": note_id, "title": title, "ext": ext, "pdf": f"/missions/notes/{note_id}/file", **summary}


def _all_failed(out: list[dict]) -> None:
    if out and all(r.get("error") for r in out):
        raise HTTPException(422, out[0]["error"])


THERMIQUE_LOTES = ("aquecimento", "piso_radiante", "bomba_calor")


async def _exec_thermique(ctx) -> dict:
    from fastapi.concurrency import run_in_threadpool
    from engines.calc_lots import lotes_tecnicos
    from engines.calc_lots.depuis_plan import divisoes_termicas
    from routes.chantiers import _get
    chantier = await _get(ctx["run"]["chantier_id"], ctx["user"]["user_id"])
    concelho = concelho_do_processo(chantier)
    out = []
    for row in await _levels(ctx):
        if row.get("error"):
            out.append({k: row[k] for k in ("plan_id", "filename", "error")})
            continue
        try:
            divisoes, hyp = divisoes_termicas(row["levels"])
            params = {"divisoes": divisoes, **({"concelho": concelho} if concelho else {})}
            n = await run_in_threadpool(lotes_tecnicos.note, params, THERMIQUE_LOTES)
        except (ValueError, KeyError) as exc:
            out.append({"plan_id": row["plan_id"], "filename": row["filename"], "error": str(exc)[:200]})
            continue
        aq, bc, pr = n.get("aquecimento") or {}, n.get("bomba_calor") or {}, n.get("piso_radiante") or {}
        ctl = [c for k in THERMIQUE_LOTES for c in (n.get(k) or {}).get("controles", [])]
        if not concelho:
            hyp = hyp + ["concelho do processo de obra não indicado ou não reconhecido (localidade / morada): clima REH por defeito"]
        summary = {"plan_id": row["plan_id"], "filename": row["filename"], "divisoes": len(divisoes), "concelho": concelho,
                   "perdas_w": round(aq.get("phi_total") or 0), "theta_e": aq.get("theta_e"),
                   "bomba_calor_kw": bc.get("p_nominal_kw"), "apoio_kw": bc.get("apoio_kw"), "cop_theta_e": bc.get("cop"),
                   "emissores": "piso_radiante" if pr else bc.get("emissores"), "aqs": None,
                   "theta_ida": bc.get("temperatura_ida") or pr.get("theta_ida"), "circuitos": pr.get("circuitos"),
                   "nao_conformes": sum(1 for c in ctl if c.get("ok") is False), "hipoteses": (hyp + n.get("hipoteses", []))[:20]}
        out.append(await _save_note(ctx, "thermique", n.get("titre") or "Nota térmica", n["pdf"], summary))
    _all_failed(out)
    return {"kind": "notes", "lot": "thermique", "notes": out}


async def _exec_structure(ctx) -> dict:
    from fastapi.concurrency import run_in_threadpool
    from engines import structuro_house as SH
    from engines.calc_lots.depuis_plan import geometria_estrutura
    from engines.structuro_house_pdf import build_pdf
    out = []
    for row in await _levels(ctx):
        if row.get("error"):
            out.append({k: row[k] for k in ("plan_id", "filename", "error")})
            continue
        nome = (row["filename"] or "Moradia").rsplit(".", 1)[0][:80]
        try:
            geo, hyp = geometria_estrutura(row["levels"], nome)
            r = await run_in_threadpool(SH.compute, geo)
            pdf = await run_in_threadpool(build_pdf, r, nome)
        except (ValueError, TypeError, KeyError) as exc:
            out.append({"plan_id": row["plan_id"], "filename": row["filename"], "error": f"Geometria inválida: {exc}"[:200]})
            continue
        g = r["geometry"]
        summary = {"plan_id": row["plan_id"], "filename": row["filename"], "implantacao_m": [g["outer_L_m"], g["outer_W_m"]],
                   "pisos": [lv["name"] for lv in g["levels"]], "linteis": len(r.get("lintels") or []),
                   "betao_m3": (r.get("quantities") or {}).get("concrete_m3"), "aco_kg": (r.get("quantities") or {}).get("steel_kg"),
                   "avisos": (r.get("warnings") or [])[:15], "hipoteses": hyp}
        out.append(await _save_note(ctx, "structure", f"Estudo de estrutura — {nome}", pdf, summary))
    _all_failed(out)
    return {"kind": "notes", "lot": "structure", "notes": out}


async def _exec_dpgf(ctx) -> dict:
    from engines import mapa_caderno as MC
    devis = (ctx["results"].get("devis") or {})
    doc_id = devis.get("doc_id")
    if not doc_id:
        raise HTTPException(422, "O rascunho de orçamento não foi criado: mapa de quantidades e caderno de encargos impossíveis.")
    doc = await db.pro_documents.find_one({"doc_id": doc_id, "user_id": ctx["user"]["user_id"]}, {"_id": 0, "title": 1, "lines": 1})
    if not doc:
        raise HTTPException(404, "Orçamento não encontrado")
    lotes = MC.por_lote(doc.get("lines") or [])
    if not lotes:
        raise HTTPException(422, "O orçamento não contém nenhuma linha de trabalhos.")
    titulo = (doc.get("title") or "Projeto").replace("Orçamento parcial — ", "")[:120]
    summary = {"lotes": [{"lote": l["lote"], "linhas": len(l["linhas"]), "total": l["total"], "por_orcamentar": l["por_orcamentar"],
                          "referencias": l["refs"]} for l in lotes],
               "total": round(sum(l["total"] for l in lotes), 2)}
    files = [await _save_note(ctx, "mapa_quantidades", f"Mapa de quantidades — {titulo}", MC.mapa_xlsx(lotes, titulo), {}, ext="xlsx"),
             await _save_note(ctx, "caderno_encargos", f"Caderno de encargos — {titulo}", MC.caderno_docx(lotes, titulo), {}, ext="docx")]
    return {"kind": "files", "files": [{"note_id": f["note_id"], "title": f["title"], "ext": f["ext"], "url": f["pdf"]} for f in files], **summary}


NOVA = ("construcao nova", "construção nova", "moradia nova", "chave na mao", "chave na mão", "obra nova", "edificio novo", "edifício novo")


def estado_obra(chantier: dict) -> tuple[str, int | None, str]:
    """(obra REH, ano de construção, origem) a partir do processo de obra: edifício novo só se o processo o disser."""
    from datetime import date
    from engines.mep.rules import _fold
    if (chantier.get("work_type") or "") == "new_build":
        return "nova", date.today().year, "tipo de obra do processo = construção nova"
    for campo in ("type", "work_type", "name", "description", "notes"):
        txt = _fold(str(chantier.get(campo) or ""))
        hit = next((k for k in NOVA if _fold(k) in txt), None)
        if hit:
            return "nova", date.today().year, f"« {hit} » no campo {campo} do processo de obra"
    return "existente", None, "processo de obra sem indicação de construção nova"


async def _aquecimento_da_termica(ctx, plan_id: str) -> dict | None:
    """Sistema de aquecimento dimensionado pela opção térmica: deste programa, senão a última nota térmica do mesmo processo."""
    for n in (ctx["results"].get("thermique") or {}).get("notes") or []:
        if n.get("plan_id") == plan_id and not n.get("error") and n.get("bomba_calor_kw"):
            return {**n, "origem": "opção térmica deste programa"}
    cid = ctx["run"].get("chantier_id")
    if not cid:
        return None
    rows = await db.mission_notes.find({"user_id": ctx["user"]["user_id"], "chantier_id": cid, "kind": "thermique"},
                                       {"_id": 0, "summary": 1, "created_at": 1, "run_id": 1}).sort("created_at", -1).to_list(20)
    rows = [r for r in rows if (r.get("summary") or {}).get("bomba_calor_kw")]
    best = next((r for r in rows if r["summary"].get("plan_id") == plan_id), rows[0] if rows else None)
    if not best:
        return None
    return {**best["summary"], "origem": f"nota térmica anterior deste processo ({str(best.get('created_at') or '')[:10]})"}


async def _exec_dpe(ctx) -> dict:
    from fastapi.concurrency import run_in_threadpool
    from engines.calc_lots import reh
    from engines.calc_lots.depuis_plan import dados_reh
    from routes.chantiers import _get
    chantier = await _get(ctx["run"]["chantier_id"], ctx["user"]["user_id"])
    concelho = concelho_do_processo(chantier)
    if not concelho:
        raise HTTPException(422, "Concelho do processo de obra em falta ou não reconhecido (localidade ou morada): "
                                 "fixa o clima do pré-certificado REH.")
    out = []
    for row in await _levels(ctx):
        if row.get("error"):
            out.append({k: row[k] for k in ("plan_id", "filename", "error")})
            continue
        try:
            params, hyp = dados_reh(row["levels"])
            hyp = ["área útil, pé-direito, envidraçados e tipologia lidos na planta: " + "; ".join(hyp)]
            confirmar = []
            obra, ano, origem = estado_obra(chantier)
            params["obra"] = obra
            if ano:
                params["ano_construcao"] = ano
                hyp.append(f"edifício novo, ano de construção {ano} (origem: {origem})")
                confirmar.append("envolvente-tipo de edifício novo (U ≈ 85 % do Umáx da Portaria 138-I): substituir pelas soluções do projeto")
            else:
                hyp.append(f"edifício existente, ano de construção 1980 por defeito do motor (origem: {origem})")
                confirmar += ["estado da obra (existente) e ano de construção", "envolvente por defeito da época de construção"]
            termica = await _aquecimento_da_termica(ctx, row["plan_id"])
            if termica:
                params["aquecimento"] = {"tipo": "bomba_calor"}
                emis = "piso radiante" if termica.get("emissores") == "piso_radiante" else (termica.get("emissores") or "emissores não indicados")
                cop = termica.get("cop_theta_e")
                hyp.append(f"aquecimento: bomba de calor ar/água {termica['bomba_calor_kw']:g} kW com {emis} (origem: {termica['origem']}); "
                           "o REH não distingue os emissores".replace(".", ","))
                hyp.append("eficiência sazonal (SCOP) não determinada pela nota térmica"
                           + (f" (só o COP indicativo a θe: {cop:.2f})".replace(".", ",") if cop else "")
                           + ": eficiência por defeito do motor REH para bomba de calor (3,5)")
                confirmar.append("SCOP da bomba de calor (ficha técnica / etiqueta energética do equipamento)")
            else:
                hyp.append("aquecimento não dimensionado (opção térmica não executada para este processo): sistema por defeito do motor REH "
                           "(resistência elétrica, η = 1) — o motor não tem modo « sistemas de referência »")
                confirmar.append("sistema de aquecimento e respetiva eficiência")
            if termica and termica.get("aqs"):
                params["aqs"] = {"tipo": termica["aqs"]}
                hyp.append(f"AQS: {termica['aqs']} (origem: {termica['origem']})")
            else:
                hyp.append("AQS não determinadas pela nota térmica: termoacumulador elétrico por defeito do motor REH")
                confirmar.append("sistema de AQS e respetiva eficiência")
            confirmar += ["orientação e sombreamento dos envidraçados (repartição-tipo do motor)", "taxa de renovação de ar (Rph por defeito)",
                          "pontes térmicas lineares"]
            hyp.append("DADOS POR DEFEITO A CONFIRMAR PELO PERITO QUALIFICADO: " + "; ".join(confirmar))
            n = await run_in_threadpool(reh.note, {**params, "concelho": concelho, "hipoteses_entrada": hyp})
        except (ValueError, KeyError) as exc:
            out.append({"plan_id": row["plan_id"], "filename": row["filename"], "error": str(exc)[:200]})
            continue
        summary = {"plan_id": row["plan_id"], "filename": row["filename"], "area_util_m2": params["area_util_m2"], "concelho": concelho,
                   "classe": n["classe"], "rnt": round(n["RNt"], 2), "ntc": round(n["Ntc"], 1), "nt": round(n["Nt"], 1),
                   "nic": round(n["Nic"], 1), "ni": round(n["Ni"], 1), "obra": obra, "ano_construcao": ano,
                   "aquecimento": n.get("aquecimento"), "aqs": n.get("aqs"), "aquecimento_origem": termica["origem"] if termica else None,
                   "a_confirmar_perito": confirmar, "hipoteses": n.get("hipoteses", [])[:20],
                   "aviso": "Indicativo: não substitui o certificado energético SCE emitido por Perito Qualificado (ADENE)."}
        out.append(await _save_note(ctx, "dpe", n.get("titre") or "Pré-certificado energético", n["pdf"], summary))
    _all_failed(out)
    return {"kind": "notes", "lot": "dpe", "notes": out}


SHAREABLE = {"plan_electricite", "plan_plomberie", "thermique", "structure", "dpgf", "dpe"}


async def _exec_partage(ctx) -> dict:
    """Prepara uma ligação de partilha dos entregáveis deste programa. A ligação fica INATIVA: só o profissional a ativa."""
    studies = [r for r in ctx["cache"].get("mep") or [] if r.get("study_id")]
    notes = await db.mission_notes.find({"run_id": ctx["run"]["run_id"], "user_id": ctx["user"]["user_id"]},
                                        {"_id": 0, "note_id": 1, "title": 1, "ext": 1}).to_list(100)
    if not studies and not notes:
        raise HTTPException(422, "Nenhum entregável a partilhar: assinale também uma opção que produza um estudo, uma nota ou um ficheiro.")
    items = [{"type": "mep", "id": r["study_id"], "title": f"Planos de execução — {r['filename']}", "ext": "pdf"} for r in studies]
    items += [{"type": "note", "id": n["note_id"], "title": n.get("title") or "Documento", "ext": n.get("ext") or "pdf"} for n in notes]
    share = {"share_id": "mshare_" + secrets.token_hex(6), "token": secrets.token_urlsafe(24), "user_id": ctx["user"]["user_id"],
             "run_id": ctx["run"]["run_id"], "items": items, "active": False, "created_at": _now()}
    await db.mission_shares.insert_one(dict(share))
    return {"kind": "share", "share_id": share["share_id"], "active": False, "files": [i["title"] for i in items],
            "activate": f"/missions/shares/{share['share_id']}/activate"}


EXECUTORS = {
    "analyse_plans": _exec_analyse,
    "controle": _exec_controle,
    "metre": _exec_metre,
    "plan_electricite": lambda ctx: _exec_mep("elec", ctx),
    "plan_plomberie": lambda ctx: _exec_mep("plumb", ctx),
    "thermique": _exec_thermique,
    "structure": _exec_structure,
    "devis": lambda ctx: _exec_agent("devis", ctx),
    "planning": _exec_planning,
    "dpgf": _exec_dpgf,
    "dpe": _exec_dpe,
    "dossier": lambda ctx: _exec_agent("report", ctx),
    "partage": _exec_partage,
}


async def _save_progress(run: dict, steps: list[dict]) -> None:
    await db.agent_runs.update_one(
        {"run_id": run["run_id"], "user_id": run["user_id"], "status": "running", "worker": run.get("worker")},
        {"$set": {"partial_result": {"kind": "mission", "steps": steps}}})


async def run_mission(run: dict, body, user: dict) -> dict:
    """Executa as opções validadas, pela ordem registada no resumo.

    Uma opção falhada bloqueia as que dela dependem; as outras continuam."""
    validated = (run.get("mission") or {}).get("steps") or []
    prompts = {s["key"]: s.get("prompt") or "" for s in validated}
    # Os prompts ficam no rasto da seleção, não no resultado apresentado.
    steps = [{k: v for k, v in s.items() if k != "prompt"} for s in validated]
    if not steps:
        raise HTTPException(422, "Nenhuma opção validada")
    ctx = {"run": run, "body": body, "user": user, "cache": {}, "results": {}}
    status_of: dict[str, str] = {}
    for step in steps:
        key = step["key"]
        failed = [d for d in step.get("depends_on") or [] if status_of.get(d) != "done"]
        if failed:
            step.update(status="skipped", error="Não lançada: a opção de que depende não terminou.")
            status_of[key] = "skipped"
            await _save_progress(run, steps)
            continue
        step.update(status="running", started_at=_now())
        await _save_progress(run, steps)
        try:
            await _option_allowed(key, user)
            result = await EXECUTORS[key](ctx)
            step.update(status="done", result=result)
            ctx["results"][key] = result
            step["synthese"] = await M.synthesize(prompts[key], result, user=user)
        except HTTPException as exc:
            step.update(status="error", error=str(exc.detail)[:300])
        except Exception as exc:  # noqa: BLE001 -- no provider secrets in client errors
            log.error("Mission %s option %s failed (%s)", run["run_id"], key, type(exc).__name__)
            step.update(status="error", error="Tratamento interrompido nesta opção.")
        step["finished_at"] = _now()
        status_of[key] = step["status"]
        await _save_progress(run, steps)
    counts = {s: sum(1 for x in steps if x["status"] == s) for s in ("done", "error", "skipped")}
    if not counts["done"]:
        raise HTTPException(422, "Nenhuma opção terminou: " + (next((s["error"] for s in steps if s.get("error")), "")))
    return {"kind": "mission", "steps": steps, **counts}


def _file_response(doc: dict):
    import base64
    from fastapi.responses import Response
    from engines.nom_fichier import content_disposition, nom_document
    ext = doc.get("ext") or "pdf"
    return Response(content=base64.b64decode(doc["data_b64"]), media_type=MIME.get(ext, "application/octet-stream"),
                    headers={"Content-Disposition": content_disposition(nom_document("Nota", doc.get("title") or "calculo", ext=ext),
                                                                        inline=ext == "pdf")})


@router.get("/notes/{note_id}/file")
async def note_file(note_id: str, user=Depends(current_user)):
    doc = await db.mission_notes.find_one({"note_id": note_id, "user_id": user["user_id"]}, {"_id": 0, "data_b64": 1, "title": 1, "ext": 1})
    if not doc:
        raise HTTPException(404, "Nota não encontrada")
    return _file_response(doc)


# ============================ Partilha dos entregáveis ============================

SHARE_DAYS_DEFAULT = 30


class ShareActivateIn(BaseModel):
    days: int = Field(SHARE_DAYS_DEFAULT, ge=1, le=365)


def _share_url(token: str) -> str:
    import os
    base = os.environ.get("PUBLIC_BACKEND_URL") or os.environ.get("FRONTEND_URL") or ""
    return f"{base.rstrip('/')}/api/missions/public/{token}"


@router.post("/shares/{share_id}/activate")
async def activate_share(share_id: str, body: ShareActivateIn | None = None, user=Depends(current_user)) -> dict:
    """Clique do profissional: torna a ligação consultável (só leitura) pela duração escolhida. Nada é enviado."""
    from datetime import datetime, timedelta, timezone
    days = (body or ShareActivateIn()).days
    expires = (datetime.now(timezone.utc) + timedelta(days=days)).isoformat()
    res = await db.mission_shares.update_one({"share_id": share_id, "user_id": user["user_id"]},
                                             {"$set": {"active": True, "expires_at": expires, "activated_at": _now()}})
    if not res.matched_count:
        raise HTTPException(404, "Partilha não encontrada")
    share = await db.mission_shares.find_one({"share_id": share_id, "user_id": user["user_id"]}, {"_id": 0, "token": 1})
    return {"ok": True, "url": _share_url(share["token"]), "expires_at": expires}


@router.post("/shares/{share_id}/revoke")
async def revoke_share(share_id: str, user=Depends(current_user)) -> dict:
    res = await db.mission_shares.update_one({"share_id": share_id, "user_id": user["user_id"]},
                                             {"$set": {"active": False, "revoked_at": _now()}})
    if not res.matched_count:
        raise HTTPException(404, "Partilha não encontrada")
    return {"ok": True}


async def _live_share(token: str) -> dict:
    from datetime import datetime, timezone
    share = await db.mission_shares.find_one({"token": token, "active": True}, {"_id": 0})
    if not share or not share.get("expires_at") or datetime.fromisoformat(share["expires_at"]) < datetime.now(timezone.utc):
        raise HTTPException(404, "Ligação de partilha inativa ou expirada")
    return share


@router.get("/public/{token}")
async def public_share(token: str):
    """Página pública só de leitura: lista dos entregáveis partilhados."""
    from html import escape
    from fastapi.responses import HTMLResponse
    share = await _live_share(token)
    items = "".join(f'<li><a href="{escape(token)}/{escape(i["id"])}">{escape(i.get("title") or "Documento")}</a> '
                    f'<small>({escape((i.get("ext") or "pdf").upper())})</small></li>' for i in share.get("items") or [])
    html = ("<!doctype html><html lang='pt-PT'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>"
            "<meta name='robots' content='noindex'><title>Processo partilhado — ConstruPilot</title>"
            "<style>body{font-family:system-ui,sans-serif;max-width:640px;margin:40px auto;padding:0 16px;color:#1f2937}"
            "a{color:#0f766e}li{margin:8px 0}</style></head><body><h1>Processo partilhado</h1>"
            f"<p>Documentos transmitidos pelo seu profissional (só leitura, indicativos).</p><ul>{items}</ul></body></html>")
    return HTMLResponse(html, headers={"Cache-Control": "no-store", "X-Robots-Tag": "noindex"})


@router.get("/public/{token}/{item_id}")
async def public_share_file(token: str, item_id: str):
    from fastapi.responses import Response
    from engines.mep.pdf import build_pdf
    from engines.nom_fichier import content_disposition, nom_document
    share = await _live_share(token)
    item = next((i for i in share.get("items") or [] if i["id"] == item_id), None)
    if not item:
        raise HTTPException(404, "Documento não encontrado")
    if item.get("type") == "note":
        note = await db.mission_notes.find_one({"note_id": item_id, "user_id": share["user_id"]},
                                               {"_id": 0, "data_b64": 1, "title": 1, "ext": 1})
        if not note:
            raise HTTPException(404, "Documento não encontrado")
        resp = _file_response(note)
        resp.headers.update({"Cache-Control": "no-store", "X-Robots-Tag": "noindex"})
        return resp
    doc = await db.mep_studies.find_one({"study_id": item_id, "user_id": share["user_id"]}, {"_id": 0})
    if not doc:
        raise HTTPException(404, "Documento não encontrado")
    return Response(content=build_pdf(doc), media_type="application/pdf", headers={
        "Content-Disposition": content_disposition(nom_document("Planos-execucao-instalacoes", doc.get("title"), doc.get("updated_at")), inline=True),
        "Cache-Control": "no-store", "X-Robots-Tag": "noindex"})


# ============================ Admin: fichas de opções ============================

class OptionPatch(BaseModel):
    prompt: Optional[str] = Field(None, min_length=10, max_length=4000)
    enabled: Optional[bool] = None


@router.get("/admin/options")
async def admin_options(user=Depends(admin_user)) -> dict:
    catalog = await M.effective_options(db)
    return {"options": [{**_public_option(s), "prompt": s["prompt"], "enabled": s["enabled"],
                         "prompt_version": s["prompt_version"], "default_prompt": M.OPTIONS[k]["prompt"]}
                        for k, s in catalog.items()]}


@router.put("/admin/options/{key}")
async def admin_update_option(key: str, body: OptionPatch, user=Depends(admin_user)) -> dict:
    """Altera o prompt ou desativa uma opção. Os programas já validados mantêm a sua versão."""
    if key not in M.OPTIONS:
        raise HTTPException(404, "Opção desconhecida")
    patch = {"key": key, "updated_at": _now(), "updated_by": user["user_id"]}
    if body.prompt is not None:
        patch["prompt"] = body.prompt.strip()
    if body.enabled is not None:
        patch["enabled"] = body.enabled
    inc = {"version": 1} if body.prompt is not None else {}
    await db.mission_options.update_one({"key": key}, {"$set": patch, **({"$inc": inc} if inc else {})}, upsert=True)
    return {"ok": True, "options": (await admin_options(user))["options"]}


@router.delete("/admin/options/{key}/prompt")
async def admin_reset_prompt(key: str, user=Depends(admin_user)) -> dict:
    if key not in M.OPTIONS:
        raise HTTPException(404, "Opção desconhecida")
    await db.mission_options.update_one({"key": key}, {"$unset": {"prompt": ""}, "$set": {"updated_at": _now()}})
    return {"ok": True}
