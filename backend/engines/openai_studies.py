"""Moteur « études » ConstruPilot ↔ OpenAI Responses API (GPT-6 Astra / GPT-5.6 Terra).

Seul le backend parle à OpenAI. Le PDF original est envoyé en input_file (detail high), les zones de petites cotes en
input_image haute résolution, les calculs exacts du moteur ConstruPilot en JSON. Sortie = JSON Schema strict, puis
seconde passe « contrôleur indépendant ». Consommation journalisée par utilisateur / projet / type.
"""
from __future__ import annotations

import base64
import io
import json
import logging
import os
from datetime import datetime, timedelta, timezone

from core.db import db
from engines.plan_walls import INCOMPLETE_MSG
from engines.studies_prompt import (
    ANALYSIS_SCHEMA,
    SYSTEM_PROMPT,
    VERIFY_PROMPT,
    VERIFY_SCHEMA,
)

logger = logging.getLogger("studies")

MODEL_ANALYSIS = os.environ["STUDIES_MODEL_ANALYSIS"]
MODEL_LIGHT = os.environ["STUDIES_MODEL_LIGHT"]
MAX_PDF_MB = 25
MAX_PAGES = 20
MAX_PER_HOUR = int(os.environ.get("STUDIES_MAX_PER_HOUR", "10"))


class StudiesError(Exception):
    pass


def _client():
    from engines.llm_keys import openai_direct_active
    key = os.environ.get("OPENAI_API_KEY")
    if not key:
        raise StudiesError("Chave OpenAI não configurada no servidor")
    if not openai_direct_active():
        raise StudiesError("Chave OpenAI da empresa desativada (crédito esgotado) — o administrador deve reativá-la em Admin → IA")
    from openai import AsyncOpenAI
    return AsyncOpenAI(api_key=key, timeout=900)


async def check_quota(user_id: str) -> None:
    since = datetime.now(timezone.utc) - timedelta(hours=1)
    n = await db.ai_usage.count_documents({"user_id": user_id, "engine": "openai_studies", "created": {"$gte": since}})
    if n >= MAX_PER_HOUR:
        raise StudiesError(f'Limite atingido: {MAX_PER_HOUR} análises OpenAI por hora e por conta')


async def _log_usage(user_id: str, project_id: str | None, kind: str, model: str, usage, plan_id: str | None) -> None:
    from engines.expenses.context import actor
    from engines.expenses.store import observe
    from engines.expenses.metering import usage_units
    inserted = await db.ai_usage.insert_one({
        "user_id": user_id, "project_id": project_id, "plan_id": plan_id, "engine": "openai_studies", "kind": kind,
        "company_id": actor().get("company_id"),
        "model": model, "input_tokens": getattr(usage, "input_tokens", None), "output_tokens": getattr(usage, "output_tokens", None),
        "reasoning_tokens": getattr(getattr(usage, "output_tokens_details", None), "reasoning_tokens", None),
        "created": datetime.now(timezone.utc)})
    await observe(source="ai_usage", source_id=str(inserted.inserted_id), provider="openai_direct", feature=kind,
                  model=model, units=usage_units(usage), state="completed")


def _safe_error(e: Exception) -> str:
    """Message sans fuite de clé ni de payload."""
    msg = str(e)
    for k in (os.environ.get("OPENAI_API_KEY") or "",):
        if k and k in msg:
            msg = msg.replace(k, "***")
    return f"{type(e).__name__}: {msg[:200]}"


def small_dimension_crops(image_png_b64: str, items: list[dict], max_crops: int = 8, margin: int = 140) -> list[str]:
    """Crops haute résolution (×2) autour des petites cotes (< 1 m) — data URLs PNG."""
    from PIL import Image
    try:
        img = Image.open(io.BytesIO(base64.b64decode(image_png_b64))).convert("RGB")
    except Exception:  # noqa: BLE001
        return []
    small = sorted((it for it in items if not it.get("ignored") and float(it.get("indicated_m") or 0) < 1.0),
                   key=lambda it: it.get("indicated_m") or 0)
    out, taken = [], []
    for it in small:
        cx, cy = (it["x1"] + it["x2"]) / 2, (it["y1"] + it["y2"]) / 2
        if any(abs(cx - tx) < margin and abs(cy - ty) < margin for tx, ty in taken):
            continue
        taken.append((cx, cy))
        box = (int(max(0, cx - margin)), int(max(0, cy - margin)), int(min(img.width, cx + margin)), int(min(img.height, cy + margin)))
        crop = img.crop(box)
        crop = crop.resize((crop.width * 2, crop.height * 2), Image.LANCZOS)
        buf = io.BytesIO()
        crop.save(buf, format="PNG")
        out.append({"data_url": "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode("ascii"),
                    "box_px": list(box), "cotes": [it["index"]]})
        if len(out) >= max_crops:
            break
    return out


def _file_part(file_id: str) -> dict:
    return {"type": "input_file", "file_id": file_id, "detail": "high"}


async def _upload_pdf(client, pdf_bytes: bytes, filename: str) -> str:
    if len(pdf_bytes) > MAX_PDF_MB * 1024 * 1024:
        raise StudiesError(f'PDF demasiado volumoso (> {MAX_PDF_MB} MB)')
    f = await client.files.create(file=(filename or "plan.pdf", pdf_bytes, "application/pdf"), purpose="user_data")
    return f.id


def _json_payload(value) -> str:
    text = json.dumps(value, ensure_ascii=False, allow_nan=False)
    if len(text) > 500_000:
        raise StudiesError("Dados de análise demasiado volumosos: tratar zonas mais pequenas")
    return text


def _selected_page_pdf(pdf_bytes: bytes, page_index: int) -> bytes:
    import pymupdf
    with pymupdf.open(stream=pdf_bytes, filetype="pdf") as src:
        if page_index < 0 or page_index >= len(src):
            raise StudiesError("Página pedida ausente do PDF")
        with pymupdf.open() as selected:
            selected.insert_pdf(src, from_page=page_index, to_page=page_index)
            return selected.tobytes()


async def _respond(client, model: str, effort: str, instructions: str, content: list[dict], schema: dict, name: str):
    response = await client.responses.create(
        model=model, reasoning={"effort": effort}, instructions=instructions,
        input=[{"role": "user", "content": content}],
        text={"format": {"type": "json_schema", "name": name, "strict": True, "schema": schema}})
    if getattr(response, "status", "completed") != "completed" or not response.output_text:
        raise StudiesError("Resposta IA incompleta: nenhuma análise pode ser validada")
    from jsonschema import ValidationError, validate
    try:
        validate(json.loads(response.output_text), schema)
    except (ValueError, ValidationError):
        raise StudiesError("Resposta IA inválida: estrutura esperada não respeitada") from None
    return response


def review_disagreements(review: dict, engine: dict, page_index: int) -> list[str]:
    """Une relecture ne peut pas valider des mesures absentes ou réécrites."""
    reasons = []
    def same_number(a, b):
        return a is None and b is None or (isinstance(a, (int, float)) and isinstance(b, (int, float)) and abs(a-b) <= .0002)
    for field, key, numeric, references in (
        ("interior_measurements", "measurement_id", ("geometric_dimension_m", "written_dimension_m", "difference_m"),
         ("direction", "from_wall", "to_wall", "from_face", "to_face", "reference_type", "status")),
        ("closure_equations", "row_id", ("sum_m", "difference_m"), ("direction", "status")),
    ):
        originals = {m[key]: m for m in engine.get(field) or []}
        candidates = review.get(field) or []
        if len(candidates) != len(originals) or {m.get(key) for m in candidates} != set(originals):
            reasons.append(f'inventário IA diferente do motor: {field}')
        for candidate in candidates:
            original = originals.get(candidate.get(key))
            if original is None:
                continue
            differs = any(not same_number(candidate.get(k), original.get(k)) for k in numeric)
            differs |= any(candidate.get(k) != original.get(k) for k in references)
            if field == "interior_measurements":
                differs |= candidate.get("page") != page_index + 1
            else:
                differs |= not same_number(candidate.get("exterior_dimension_m"), original.get("written_exterior_m"))
            if differs:
                reasons.append(f'desacordo IA / geometria a resolver: {candidate.get(key)}')
    if any(w.get("engine_agreement") != "confirmed" for w in review.get("walls") or []):
        reasons.append("inventário das paredes corrigido ou rejeitado pela revisão: geometria a reexaminar")
    if {w.get("wall_id") for w in review.get("walls") or []} != {w["wall_id"] for w in engine.get("walls") or []}:
        reasons.append("inventário das paredes não comparado com o motor")
    return reasons


def zone_crops(pdf_bytes: bytes, page_index: int, walls_result: dict, px_per_pt: float, max_crops: int = 14, zoom: float = 3.0) -> list[dict]:
    """Crops haute résolution rendus depuis le PDF ORIGINAL (jamais depuis la capture annotée) : périphéries haute/basse/gauche/
    droite, bandes intérieures, travées à confirmer, intersections. Chaque crop garde sa zone en pixels du plan."""
    import pymupdf
    walls = walls_result.get("walls") or []
    if not walls:
        # L'absence de détection ne doit pas supprimer les zooms : inspecter
        # la page source en tuiles, sans inventer de murs ni de mesures.
        with pymupdf.open(stream=pdf_bytes, filetype="pdf") as doc:
            page = doc[page_index]
            result = []
            for row in range(3):
                for col in range(3):
                    if len(result) >= max_crops: return result
                    rect = pymupdf.Rect(max(0,(col-.08)*page.rect.width/3), max(0,(row-.08)*page.rect.height/3),
                                         min(page.rect.width,(col+1.08)*page.rect.width/3), min(page.rect.height,(row+1.08)*page.rect.height/3))
                    z = min(zoom, 2600/max(rect.width,rect.height))
                    pix = page.get_pixmap(matrix=pymupdf.Matrix(z,z),clip=rect,alpha=False)
                    result.append({"label": f'zone source {row + 1}-{col + 1} (paredes não estabelecidas)',
                                   "data_url": "data:image/png;base64," + base64.b64encode(pix.tobytes("png")).decode("ascii"),
                                   "box_px": [round(v*px_per_pt) for v in rect], "zoom": round(z,2)})
            return result
    xs = [v for w in walls for v in (w["face_1"]["x1"], w["face_1"]["x2"], w["face_2"]["x1"], w["face_2"]["x2"])]
    ys = [v for w in walls for v in (w["face_1"]["y1"], w["face_1"]["y2"], w["face_2"]["y1"], w["face_2"]["y2"])]
    x0, x1, y0, y1 = min(xs) / px_per_pt, max(xs) / px_per_pt, min(ys) / px_per_pt, max(ys) / px_per_pt
    m = 1.6 * (walls_result.get("pt_per_m") or 40)  # marge ≈ 1,6 m (chaînes de cotes périphériques)
    zones = [("periferia superior", x0 - m, y0 - m, x1 + m, y0 + m * 0.4), ("periferia inferior", x0 - m, y1 - m * 0.4, x1 + m, y1 + m),
             ("periferia esquerda", x0 - m, y0 - m, x0 + m * 0.4, y1 + m), ("periferia direita", x1 - m * 0.4, y0 - m, x1 + m, y1 + m)]
    h = (y1 - y0) / 3
    zones += [(f'faixa interior {lbl}', x0 - m * 0.3, y0 + i * h - m * 0.2, x1 + m * 0.3, y0 + (i + 1) * h + m * 0.2)
              for i, lbl in enumerate(("supérieure", "centrale", "inférieure"))]
    meas = sorted(walls_result.get("interior_measurements") or [], key=lambda mm: (mm["status"] != "to_confirm", -mm.get("geometric_dimension_m", 0)))
    for mm in meas:
        c = mm["coordinates"]
        cx0, cy0, cx1, cy1 = (min(c["x1"], c["x2"]) / px_per_pt, min(c["y1"], c["y2"]) / px_per_pt,
                              max(c["x1"], c["x2"]) / px_per_pt, max(c["y1"], c["y2"]) / px_per_pt)
        zones.append((f"travée {mm['measurement_id']} ({mm['from_wall']}→{mm['to_wall']})", cx0 - m * 0.5, cy0 - m * 0.5, cx1 + m * 0.5, cy1 + m * 0.5))
    out = []
    doc = pymupdf.open(stream=pdf_bytes, filetype="pdf")
    try:
        page = doc[page_index]
        pr = page.rect
        for label, ax0, ay0, ax1, ay1 in zones[:max_crops]:
            clip = pymupdf.Rect(max(pr.x0, ax0), max(pr.y0, ay0), min(pr.x1, ax1), min(pr.y1, ay1))
            if clip.is_empty or clip.width < 10 or clip.height < 10:
                continue
            z = min(zoom, 2600 / max(clip.width, clip.height))  # ≤ ~2600 px de côté
            pix = page.get_pixmap(matrix=pymupdf.Matrix(z, z), clip=clip, alpha=False)
            out.append({"label": label, "data_url": "data:image/png;base64," + base64.b64encode(pix.tobytes("png")).decode("ascii"),
                        "box_px": [round(clip.x0 * px_per_pt), round(clip.y0 * px_per_pt), round(clip.x1 * px_per_pt), round(clip.y1 * px_per_pt)],
                        "zoom": round(z, 2)})
    finally:
        doc.close()
    return out


async def analyze_interior(*, client, file_id: str, user_id: str, plan_id: str, project_id: str | None, page_index: int, request_text: str,
                           walls_result: dict, crops: list[dict], lang: str, effort: str = "high") -> dict:
    """Trois passes séparées (géométrie → cotations → rapprochement), GPT-6 Astra, sortie JSON stricte."""
    from engines.interior_prompt import INTERIOR_PROMPT, INTERIOR_SCHEMA, PASS_DIMENSIONS, PASS_GEOMETRY, PASS_RECONCILE
    lang_note = "Redige todos os textos em português europeu profissional." if lang == "pt" else "Redige todos os textos em português europeu profissional."
    engine = {k: walls_result.get(k) for k in ("coverage", "walls", "interior_measurements", "closure_equations", "cotes", "sections_ignored", "stats", "validation",
                                               "peripheral", "legend")}
    lg = walls_result.get("legend") or {}
    request_text = (f"{request_text}\nLEGENDA DA PLANTA (fonte prioritária): {' | '.join(lg.get('legend') or []) or 'nenhuma legenda detetada'}\nCARTOUCHE : {' | '.join(lg.get('cartouche') or []) or '—'} — tipo de documento: {lg.get('document_kind') or 'não determinado'}")
    engine_txt = _json_payload(engine)
    from engines.plan_symbols import prompt_block
    head = [_file_part(file_id), {"type": "input_text", "text": f'{lang_note}\nÂMBITO PEDIDO: {request_text}\nPage : {page_index + 1}.\nO ficheiro transmitido contém apenas esta página de origem; utiliza o número {page_index + 1} nos resultados.\nConserva os identificadores e as referências de faces do motor sem os renomear. Qualquer correção proposta deve ser explicada em review_findings.\n{prompt_block()}\n\nPAREDES / MEDIÇÕES / COTAS / FECHOS: candidatos geométricos a controlar; comprimentos em metros, coordenadas em píxeis da pré-visualização:\n{engine_txt}'}]
    imgs = []
    for c in crops:
        imgs.append({"type": "input_text", "text": f"Ampliação de alta resolução — {c['label']} (page {page_index + 1}, zone pixels {c['box_px']}, ×{c['zoom']}) :"})
        imgs.append({"type": "input_image", "image_url": c["data_url"], "detail": "high"})
    r1 = await _respond(client, MODEL_ANALYSIS, effort, INTERIOR_PROMPT, head + [{"type": "input_text", "text": PASS_GEOMETRY}] + imgs,
                        INTERIOR_SCHEMA, "interior_pass_geometry")
    await _log_usage(user_id, project_id, "interior_geometry", MODEL_ANALYSIS, r1.usage, plan_id)
    p1 = json.loads(r1.output_text)
    r2 = await _respond(client, MODEL_ANALYSIS, effort, INTERIOR_PROMPT,
                        head + [{"type": "input_text", "text": PASS_DIMENSIONS + "\nRESULTADO DA PASSAGEM 1 (paredes):\n" + _json_payload(p1.get("walls"))}] + imgs,
                        INTERIOR_SCHEMA, "interior_pass_dimensions")
    await _log_usage(user_id, project_id, "interior_dimensions", MODEL_ANALYSIS, r2.usage, plan_id)
    p2 = json.loads(r2.output_text)
    r3 = await _respond(client, MODEL_ANALYSIS, "high", INTERIOR_PROMPT,
                        head + [{"type": "input_text", "text": PASS_RECONCILE + "\nPASSAGE 1 :\n" + _json_payload(p1)
                                 + "\nPASSAGE 2 :\n" + _json_payload(p2)}] + imgs,
                        INTERIOR_SCHEMA, "interior_pass_reconcile")
    await _log_usage(user_id, project_id, "interior_reconcile", MODEL_ANALYSIS, r3.usage, plan_id)
    final = json.loads(r3.output_text)
    engine_ok = bool((walls_result.get("validation") or {}).get("complete"))
    blocking = [f for f in final.get("review_findings") or [] if f.get("severity") == "bloquant"]
    disagreements = review_disagreements(final, engine, page_index)
    complete = engine_ok and bool(final.get("analysis_complete")) and not blocking and not disagreements
    reasons = list((walls_result.get("validation") or {}).get("failed_checks") or []) + list(final.get("incompleteness_reasons") or [])
    reasons += [f"{f['target']} : {f['finding']}" for f in blocking]
    reasons += disagreements
    return {"engine": engine, "ai": final, "passes": {"geometry": p1.get("walls"), "dimensions": p2.get("dimension_associations_rejected")},
            "complete": complete, "reasons": reasons, "message": None if complete else INCOMPLETE_MSG,
            "crops": [{"label": c["label"], "box_px": c["box_px"]} for c in crops]}


async def analyze_plan(*, user_id: str, plan_id: str, project_id: str | None, pdf_bytes: bytes, filename: str,
                       page_index: int, request_text: str, engine_json: dict, crops: list[dict], lang: str,
                       effort: str = "high", walls_result: dict | None = None, zone_crop_list: list[dict] | None = None) -> dict:
    """Passe 1 (analyse) + passe 2 (contrôleur indépendant) + 3 passes « dimensions intérieures ». Renvoie {analysis, verification, interior, verified…}."""
    await check_quota(user_id)
    client = _client()
    file_id = None
    try:
        scoped_pdf = _selected_page_pdf(pdf_bytes, page_index)
        file_id = await _upload_pdf(client, scoped_pdf, f"page-{page_index + 1}.pdf")
        interior = None
        if walls_result is None:
            walls_result = {"validation": {"complete": False, "failed_checks": ["geometria interior ausente"]}}
        if walls_result is not None:
            interior = await analyze_interior(client=client, file_id=file_id, user_id=user_id, plan_id=plan_id, project_id=project_id,
                                              page_index=page_index, request_text=request_text, walls_result=walls_result,
                                              crops=zone_crop_list or [], lang=lang, effort=effort)
            engine_json = {**engine_json, "dimensions_interieures": {"complete": interior["complete"], "reasons": interior["reasons"],
                                                                     "ai_summary": interior["ai"].get("summary"),
                                                                     "interior_measurements": interior["engine"].get("interior_measurements"),
                                                                     "closure_equations": interior["engine"].get("closure_equations")}}
        lang_note = ("Redige todos os textos em português europeu profissional." if lang == "pt"
                     else "Redige todos os textos em português europeu profissional.")
        engine_txt = _json_payload(engine_json)
        content = [_file_part(file_id),
                   {"type": "input_text", "text":
                    f'{lang_note}\nÂMBITO PEDIDO: {request_text}\nPágina a analisar: {page_index + 1} do documento «{filename}» (o ficheiro transmitido contém apenas esta página de origem).\nDADOS DO MOTOR CONSTRUPILOT (medições em metros; associações e classes a verificar):\n{engine_txt}'}]
        for i, c in enumerate(crops):
            content.append({"type": "input_text", "text": f"Ampliação de alta resolução n.º{i + 1} (page {page_index + 1}, zone pixels {c['box_px']}, cotes ConstruPilot #{c['cotes']}) :"})
            content.append({"type": "input_image", "image_url": c["data_url"], "detail": "high"})
        from engines.plan_symbols import prompt_block
        r1 = await _respond(client, MODEL_ANALYSIS, effort, SYSTEM_PROMPT + "\n\n" + prompt_block(), content, ANALYSIS_SCHEMA, "construction_plan_analysis")
        await _log_usage(user_id, project_id, "plan_analysis", MODEL_ANALYSIS, r1.usage, plan_id)
        analysis = json.loads(r1.output_text)
        if analysis.get("pages_analyzed") != [page_index + 1]:
            raise StudiesError("A resposta IA não corresponde à página de origem pedida")
        content2 = [_file_part(file_id),
                    {"type": "input_text", "text":
                     f'{lang_note}\nÂMBITO PEDIDO: {request_text}\nPage source : {page_index + 1}.\nJSON DA PRIMEIRA ANÁLISE:\n{_json_payload(analysis)}\n\nCÁLCULOS DO MOTOR CONSTRUPILOT:\n{engine_txt}'}]
        r2 = await _respond(client, MODEL_ANALYSIS, "high", VERIFY_PROMPT, content2 + content[2:], VERIFY_SCHEMA, "independent_verification")
        await _log_usage(user_id, project_id, "plan_verification", MODEL_ANALYSIS, r2.usage, plan_id)
        verification = json.loads(r2.output_text)
        drop = set(verification.get("corrected_inconsistency_ids_to_drop") or [])
        if drop:
            analysis["inconsistencies"] = [x for x in analysis.get("inconsistencies") or [] if x.get("id") not in drop]
        blocking = [f for f in verification.get("findings") or [] if f.get("severity") == "bloquant"]
        interior_ok = bool(interior and interior["complete"])
        return {"analysis": analysis, "verification": verification, "interior": interior,
                "verified": bool(verification.get("verified")) and not blocking and interior_ok,
                "incomplete_message": None if interior_ok else INCOMPLETE_MSG,
                "model": MODEL_ANALYSIS, "effort": effort, "crops": [{"box_px": c["box_px"], "cotes": c["cotes"]} for c in crops],
                "page_index": page_index, "created_at": datetime.now(timezone.utc).isoformat(), "lang": lang}
    except StudiesError:
        raise
    except Exception as e:  # noqa: BLE001
        from engines.llm_keys import note_openai_error
        if await note_openai_error(e):
            raise StudiesError("Chave OpenAI da empresa desativada (crédito esgotado) — o administrador deve reativá-la em Admin → IA") from None
        logger.warning("openai studies failed: %s", _safe_error(e))
        raise StudiesError(f'Análise OpenAI impossível — {_safe_error(e)}') from None

    finally:
        if file_id:
            try:
                await client.files.delete(file_id)
            except Exception as e:
                logger.info("file cleanup skipped: %s", _safe_error(e))
        await client.close()
