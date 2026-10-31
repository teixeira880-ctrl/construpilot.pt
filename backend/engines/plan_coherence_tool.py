"""Outil Assistant BTP « check_plans_coherence » : contrôle archi ↔ BET calculé par engines.plan_coherence.

L'IA n'intervient que pour relever les chaînes de cotes d'un plan IMAGE (positions + valeurs) ; orientation, rapprochement,
écarts, contrôles internes et superposition sont calculés de façon déterministe."""
from __future__ import annotations

import asyncio
import base64
import hashlib
import io
from datetime import datetime, timezone

from engines import plan_coherence as pc

PLANS_COHERENCE_TOOL = {
    "type": "function", "name": "check_plans_coherence", "strict": True,
    "description": "CONTROLO DE COERÊNCIA PLANTA DE ARQUITETURA ↔ PLANTA DE ESTRUTURAS (cofragem / estrutura / projeto de execução) do "
                   "mesmo piso: lê as cadeias de cotas de cada planta com a sua ORIENTAÇÃO e POSIÇÃO, associa os vãos equivalentes (nunca uma "
                   "cota horizontal com uma vertical, nunca uma cota de terraço/envolvente com o edifício), quantifica as diferenças, controla "
                   "cada planta internamente (cota escrita ≠ desenho, cadeias paralelas contraditórias, fachada não paralela) e produz uma "
                   "SOBREPOSIÇÃO alinhada pelos eixos (PNG + PDF, nenhuma imagem gerada por IA). OBRIGATÓRIO sempre que o utilizador pede as "
                   "incoerências / a comparação / a sobreposição entre uma planta de arquitetura e uma de estruturas. Identificadores doc_… ou "
                   "plan_…; level = piso a comparar (ex. « R/C », « 1.º piso », « PH RDC ») para escolher a vista certa numa folha com várias "
                   "vistas; páginas a partir de 0.",
    "parameters": {"type": "object", "properties": {
        "document_archi": {"type": "string"}, "document_bet": {"type": "string"},
        "level": {"type": "string", "description": "Piso comparado (R/C, 1.º piso, cave…); vazio se desconhecido"},
        "page_archi": {"type": "integer"}, "page_bet": {"type": "integer"}},
        "required": ["document_archi", "document_bet", "level", "page_archi", "page_bet"], "additionalProperties": False}}

INSTRUCTIONS = """
Comparação planta de arquitetura ↔ planta de estruturas: chama SEMPRE check_plans_coherence (nunca compare_documents, nunca uma leitura
« a olho », nunca edit_image_from_photo nem um JPG create_downloadable_file para anotar ou « atualizar » uma planta). Vale também para um
pedido de seguimento (« atualiza o quadro », « refaz os esquemas comparativos », « corrige a imagem ») e mesmo que as plantas tenham sido
anexadas numa mensagem anterior: volta a chamar check_plans_coherence com os respetivos doc_id. Qualquer imagem ou quadro de comparação
antigo produzido de outra forma na conversa está obsoleto e pode estar errado: não o retomes nem o cites como resultado. Apresenta depois:
as diferenças arquitetura ↔ estruturas por vão (largura e depois profundidade), as incoerências internas de cada planta, as cadeias não
comparadas (terraço, envolvente) numa linha, e a sobreposição devolvida (PNG/PDF). Podes acrescentar o que VÊS na sobreposição (paredes
presentes só num lado, vãos, pilares) marcando « observado na sobreposição, a confirmar ». Não recalcules nem reinterpretes nenhuma cota:
os números vêm da ferramenta.
"""


def _to_png(raw: bytes) -> bytes:
    from PIL import Image
    with Image.open(io.BytesIO(raw)) as im:
        buf = io.BytesIO()
        im.convert("RGB").save(buf, "PNG")
        return buf.getvalue()


async def _vision_chains(png: bytes) -> tuple[dict | None, str]:
    """Relevé IA des chaînes de cotes d'un plan image (image ramenée à ≤ 1600 px ; coordonnées remises à l'échelle)."""
    from PIL import Image
    from engines.structuro_maison_extract import ask_vision
    with Image.open(io.BytesIO(png)) as im:
        w, h = im.size
        k = min(1.0, 1600 / max(w, h))
        small = im.convert("RGB").resize((int(w * k), int(h * k))) if k < 1 else im.convert("RGB")
        buf = io.BytesIO()
        small.save(buf, "PNG")
    data, model = await ask_vision(pc.VISION_PROMPT.format(w=small.width, h=small.height), [buf.getvalue()])
    if data and k < 1:
        for ch in data.get("chains") or []:
            ch["ticks_px"] = [[t[0] / k, t[1] / k] for t in ch.get("ticks_px") or [] if isinstance(t, (list, tuple)) and len(t) == 2]
    return data, model


async def prepare(src: dict, page: int, level: str | None, label: str) -> dict:
    """src = {pdf_bytes | image_b64, filename} (format de _compare_source)."""
    if src.get("pdf_bytes"):
        r = await asyncio.to_thread(pc.prepare_vector, src["pdf_bytes"], max(0, page), level, label)
        if r.get("ok"):
            return r
        png = r["png"]
        pre = [r["note"]]
    elif src.get("image_b64"):
        png = await asyncio.to_thread(_to_png, base64.b64decode(src["image_b64"]))
        pre = []
    else:
        return {"ok": False, "note": f"{label}: documento ilegível (nem PDF nem imagem)."}
    data, model = await _vision_chains(png)
    r = await asyncio.to_thread(pc.prepare_raster, png, data, label)
    r["notes"] = pre + r.get("notes", []) + ([f"Leitura das cotas da imagem: {model} (controlada por cálculo)."] if model else [])
    return r


async def run(args: dict, user: dict, conv: dict, db, load_source) -> dict:
    uid = user["user_id"]
    if args["document_archi"] == args["document_bet"]:
        return {"ok": False, "error": "Os dois identificadores designam o mesmo documento."}
    try:
        sa = await load_source(args["document_archi"], uid)
        sb = await load_source(args["document_bet"], uid)
    except PermissionError:
        return {"ok": False, "error": "Documento inacessível para esta conta."}
    level = (args.get("level") or "").strip() or None
    a, b = await asyncio.gather(prepare(sa, args.get("page_archi") or 0, level, "Arquitetura"),
                                prepare(sb, args.get("page_bet") or 0, level, "Estruturas"))
    if not a.get("ok") or not b.get("ok"):
        return {"ok": False, "error": "Cotas ilegíveis: " + " ".join(x.get("note", "") for x in (a, b) if not x.get("ok")),
                "notes": a.get("notes", []) + b.get("notes", [])}
    title = f"Sobreposição {level or 'planta'} — arquitetura × estruturas"
    res = await asyncio.to_thread(pc.finalize, a, b, title)
    out = {k: v for k, v in res.items() if k != "overlay_png"}
    out["files"] = {"archi": sa.get("filename"), "bet": sb.get("filename")}
    if res.get("overlay_png"):
        out.update(await _store(res["overlay_png"], title, res, user, conv, db))
    return out


async def _store(png: bytes, title: str, res: dict, user: dict, conv: dict, db) -> dict:
    from PIL import Image
    from engines.assistant_files import build_document_pdf, public_artifact
    uid, cid = user["user_id"], conv["conversation_id"]
    ident = "file_" + hashlib.sha256((str(conv.get("_quote_request_id")) + str(conv.get("_file_call_id", "")) + "coh").encode()).hexdigest()[:27]
    with Image.open(io.BytesIO(png)) as im:
        buf = io.BytesIO()
        im.convert("RGB").save(buf, "JPEG", quality=90)
        jpg = buf.getvalue()
    st = {"incoherence": "incoerência", "a_verifier": "a verificar", "conforme": "conforme"}
    lines = [f"- [{st.get(f['statut'], f['statut'])}] {f['detail']}" for f in res["findings"]]
    body = "\n".join(["# Constatações"] + (lines or ["- Nenhuma incoerência de cotas nas cadeias comparadas."]) +
                     ["", "# Regras de leitura"] + [f"- {r}" for r in res["rules"]] +
                     ["", "Sobreposição calculada pelos eixos comuns (nenhuma imagem gerada por IA)."])
    pdf = await asyncio.to_thread(build_document_pdf, title, body, [jpg])
    now = datetime.now(timezone.utc).isoformat()
    docs = []
    for suffix, fmt_, mime, data, fname in (("i", "png", "image/png", png, "sobreposicao-arquitetura-estruturas.png"),
                                            ("p", "pdf", "application/pdf", pdf, "controlo-coerencia-arquitetura-estruturas.pdf")):
        aid = ident + suffix
        doc = {"artifact_id": aid, "user_id": uid, "conversation_id": cid, "request_id": conv.get("_quote_request_id"), "title": title,
               "body": body, "filename": fname, "format": fmt_, "mime": mime, "size": len(data), "data_b64": base64.b64encode(data).decode(),
               "source_artifact_ids": [], "created_at": now, "illustrative": False, "computed_overlay": True,
               "download": f"/assistant/artifacts/{aid}/content"}
        await db.assistant_artifacts.update_one({"artifact_id": aid, "user_id": uid}, {"$setOnInsert": doc}, upsert=True)
        docs.append(public_artifact(doc))
    return {"artifact": docs[0], "pdf_artifact": docs[1]}
