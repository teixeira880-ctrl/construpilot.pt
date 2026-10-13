"""StructuroPilot — Mode « Analyse de dossier BET » : IA de LECTURE uniquement.

L'IA LIT des plans (PNG/JPG) et des notes de calcul (PDF) et en extrait les FAITS
ÉCRITS : cotes, charges, matériaux, hypothèses, indice/révision lu au cartouche.
Elle compare deux versions et signale des incohérences entre documents.

Lecture via la clé universelle Emergent (provider Gemini) : les images sont envoyées
telles quelles, les PDF sont rasterisés en images (PyMuPDF) — comme gemini_ocr.

Interdits absolus : ne jamais inventer une valeur, ne jamais recalculer, ne jamais
trancher « la bonne valeur ». Repli déterministe si le LLM est indisponible.
"""
from __future__ import annotations

import base64
import json
import os
import re

from dotenv import load_dotenv

load_dotenv()

_MODEL = os.environ.get("BET_GEMINI_MODEL") or os.environ.get("GEMINI_FALLBACK_MODEL") or "gemini-3.5-flash"
_MAX_IMG_BYTES = 10 * 1024 * 1024
_MAX_PDF_PAGES = 8
IMAGE_MIMES = {"image/png", "image/jpeg", "image/jpg", "image/webp", "image/gif"}

_SYSTEM = (
    "És um assistente de CONTROLO DE PROCESSOS para um gabinete de projeto de estruturas (construção). LÊS plantas e memórias de cálculo e relatas APENAS o que está escrito. Proibições absolutas: nunca inventes uma cota, uma carga, uma secção, uma resistência nem uma conclusão; não recalcules nada; nunca decidas qual valor está correto. Se algo estiver ilegível ou ausente, põe-no nas incertezas. Responde ESTRITAMENTE em JSON válido, sem texto à volta."
)

_EXTRACT_PROMPT = (
    "Lê este documento do processo de engenharia (todas as páginas/imagens fornecidas) e devolve ESTE JSON exato:\n{\"resume\":\"<2 phrases max, factuel>\",\"indice_detecte\":\"<indice/révision lu au cartouche, ex: B ou null>\",\"cotes\":[{\"libelle\":\"\",\"valeur\":\"\",\"unite\":\"\",\"localisation\":\"\"}],\"charges\":[{\"libelle\":\"\",\"valeur\":\"\",\"unite\":\"\"}],\"materiaux\":[{\"libelle\":\"\",\"caracteristique\":\"\"}],\"hypotheses\":[\"\"],\"references\":[\"\"],\"incertitudes\":[\"\"]}\nCada valor deve estar literalmente presente. Preserva exatamente unidades, sinais e casas decimais. Não acrescentes nenhum dado não escrito. Listas vazias se nada for encontrado. O resumo em português europeu."
)

_COMPARE_PROMPT = (
    "Compara o DOCUMENTO A (versão antiga) e o DOCUMENTO B (versão nova) de um mesmo elemento do processo. Devolve ESTE JSON exato:\n{\"ajouts\":[\"\"],\"suppressions\":[\"\"],\"modifications\":[{\"sujet\":\"\",\"avant\":\"\",\"apres\":\"\"}],\"conflits_a_verifier\":[{\"sujet\":\"\",\"detail\":\"\"}]}\nCompara cotas, cargas, materiais, hipóteses e marcas. Nunca decidas qual valor está correto: assinala os conflitos. Listas vazias se não houver nenhuma diferença. Textos em português europeu.\n\nDOCUMENT A:\n{a}\n\nDOCUMENT B:\n{b}"
)

_INCO_PROMPT = (
    "Eis os factos extraídos de vários documentos de UM MESMO processo de engenharia. Identifica as INCOERÊNCIAS: uma mesma grandeza (cota, carga, material, hipótese) citada de forma diferente consoante os documentos. Devolve ESTE JSON exato:\n{\"incoherences\":[{\"sujet\":\"\",\"valeurs\":[{\"document\":\"\",\"valeur\":\"\"}],\"note\":\"\"}]}\nNão recalcules nada, não decidas: relata apenas as diferenças a verificar. Lista vazia se tudo concordar. Textos em português europeu.\n\nDOCUMENTS:\n{docs}"
)


def _extract_json(text: str) -> dict | None:
    if not text:
        return None
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except json.JSONDecodeError:
        return None


def _chat():
    from emergentintegrations.llm.chat import LlmChat
    import uuid
    return (LlmChat(api_key=os.environ["EMERGENT_LLM_KEY"],
                    session_id=f"bet-{uuid.uuid4().hex}", system_message=_SYSTEM)
            .with_model("gemini", _MODEL).with_params(max_tokens=4000))


def is_analyzable(mime: str) -> bool:
    return mime == "application/pdf" or (mime or "").lower() in IMAGE_MIMES


def _pdf_to_images(raw: bytes) -> list[bytes]:
    import fitz
    out: list[bytes] = []
    doc = fitz.open(stream=raw, filetype="pdf")
    try:
        for pno in range(min(doc.page_count, _MAX_PDF_PAGES)):
            out.append(doc[pno].get_pixmap(dpi=170).tobytes("png"))
    finally:
        doc.close()
    return out


def render_doc_images(raw: bytes, dpi: int = 150, budget: int = 8, keywords: tuple | None = None) -> list[bytes]:
    """Rasterise un PDF en PNG. Si `keywords` est fourni et que le PDF a une couche texte,
    ne retient que les pages pertinentes (plus la 1re), sinon prend les `budget` premières pages.
    Sans `keywords` (ex : rapport G2 scanné), rend TOUTES les pages jusqu'à `budget`."""
    import fitz
    doc = fitz.open(stream=raw, filetype="pdf")
    try:
        n = doc.page_count
        if keywords:
            kws = [k.lower() for k in keywords]
            hits = []
            for i in range(n):
                try:
                    t = (doc[i].get_text() or "").lower()
                except Exception:  # noqa: BLE001
                    t = ""
                if any(k in t for k in kws):
                    hits.append(i)
            pages = hits if hits else list(range(n))
            if 0 not in pages:
                pages = [0] + pages
            pages = sorted(set(pages))[:budget]
        else:
            pages = list(range(min(n, budget)))
        return [doc[i].get_pixmap(dpi=dpi).tobytes("png") for i in pages]
    finally:
        doc.close()


def _skipped(msg: str) -> dict:
    return {"source_engine": "skipped", "resume": "", "indice_detecte": None,
            "cotes": [], "charges": [], "materiaux": [], "hypotheses": [],
            "references": [], "incertitudes": [msg]}


async def extract_document(data: bytes, mime: str, filename: str) -> dict:
    """Extrait les faits écrits d'un PDF ou d'une image. Jamais d'invention."""
    mime = (mime or "").lower()
    if not os.environ.get("EMERGENT_LLM_KEY"):
        return _skipped("Chave IA ausente.")
    if not is_analyzable(mime):
        return _skipped("Formato ilegível pela IA (planta vetorial DWG/IFC).")
    try:
        from emergentintegrations.llm.chat import UserMessage, ImageContent
        images: list[bytes] = []
        if mime == "application/pdf":
            images = await _run(_pdf_to_images, data)
            if not images:
                return _skipped("PDF ilegível ou vazio.")
        else:
            if len(data) > _MAX_IMG_BYTES:
                return _skipped("Imagem demasiado volumosa para a análise (máx. 10 MB).")
            images = [data]
        contents = [ImageContent(image_base64=base64.b64encode(im).decode("ascii")) for im in images[:_MAX_PDF_PAGES]]
        resp = await _chat().send_message(UserMessage(text=_EXTRACT_PROMPT, file_contents=contents))
        parsed = _extract_json(resp if isinstance(resp, str) else str(resp))
        if not parsed:
            return {**_skipped("A IA não devolveu dados utilizáveis."), "source_engine": "fallback"}
        parsed.setdefault("resume", "")
        parsed.setdefault("indice_detecte", None)
        for k in ("cotes", "charges", "materiaux", "hypotheses", "references", "incertitudes"):
            if not isinstance(parsed.get(k), list):
                parsed[k] = []
        parsed["source_engine"] = "claude"
        return parsed
    except Exception as e:  # noqa: BLE001
        return {**_skipped(f'Leitura IA indisponível: {str(e)[:120]}'), "source_engine": "error"}


async def _run(fn, *args):
    import asyncio
    return await asyncio.to_thread(fn, *args)


def _compact(extraction: dict) -> str:
    if not extraction:
        return "(nenhum dado)"
    keep = {k: extraction.get(k) for k in
            ("resume", "indice_detecte", "cotes", "charges", "materiaux", "hypotheses")}
    return json.dumps(keep, ensure_ascii=False)[:6000]


async def compare_documents(ext_a: dict, ext_b: dict) -> dict:
    empty = {"ajouts": [], "suppressions": [], "modifications": [], "conflits_a_verifier": [], "source_engine": "skipped"}
    if not os.environ.get("EMERGENT_LLM_KEY"):
        return empty
    try:
        from emergentintegrations.llm.chat import UserMessage
        prompt = _COMPARE_PROMPT.format(a=_compact(ext_a), b=_compact(ext_b))
        resp = await _chat().send_message(UserMessage(text=prompt))
        parsed = _extract_json(resp if isinstance(resp, str) else str(resp)) or {}
        for k in ("ajouts", "suppressions", "modifications", "conflits_a_verifier"):
            if not isinstance(parsed.get(k), list):
                parsed[k] = []
        parsed["source_engine"] = "claude"
        return parsed
    except Exception as e:  # noqa: BLE001
        return {**empty, "source_engine": "error", "error": str(e)[:120]}


_META_PROMPT = (
    "Eis os METADADOS de um ficheiro CAD/BIM (DWG/IFC) traduzido pela Autodesk: camadas, categorias/classes de objetos, chaves de propriedades e uma amostra de objetos com as suas propriedades. Relata APENAS os factos presentes nestes metadados. Devolve ESTE JSON exato:\n{\"resume\":\"<2 phrases max, factuel>\",\"indice_detecte\":null,\"cotes\":[{\"libelle\":\"\",\"valeur\":\"\",\"unite\":\"\",\"localisation\":\"\"}],\"charges\":[{\"libelle\":\"\",\"valeur\":\"\",\"unite\":\"\"}],\"materiaux\":[{\"libelle\":\"\",\"caracteristique\":\"\"}],\"hypotheses\":[\"\"],\"references\":[\"\"],\"incertitudes\":[\"\"]}\nNão inventes nenhuma dimensão nem carga ausente dos metadados. Para um DWG, as entidades por camada NÃO são elementos identificados: põe esses limites nas incertezas. Para um IFC, explora as propriedades/quantidades presentes (dimensões, materiais). Textos em português europeu.\n\nMÉTADONNÉES:\n{meta}"
)


async def extract_from_metadata(meta_summary: str) -> dict:
    """Transforme des métadonnées Autodesk (DWG/IFC) en faits BET, sans invention."""
    if not os.environ.get("EMERGENT_LLM_KEY"):
        return _skipped("Chave IA ausente.")
    try:
        from emergentintegrations.llm.chat import UserMessage
        resp = await _chat().send_message(UserMessage(text=_META_PROMPT.format(meta=(meta_summary or "")[:12000])))
        parsed = _extract_json(resp if isinstance(resp, str) else str(resp))
        if not parsed:
            return {**_skipped("Metadados não utilizáveis pela IA."), "source_engine": "fallback"}
        parsed.setdefault("resume", "")
        parsed.setdefault("indice_detecte", None)
        for k in ("cotes", "charges", "materiaux", "hypotheses", "references", "incertitudes"):
            if not isinstance(parsed.get(k), list):
                parsed[k] = []
        parsed["source_engine"] = "autodesk"
        return parsed
    except Exception as e:  # noqa: BLE001
        return {**_skipped(f'Leitura de metadados indisponível: {str(e)[:120]}'), "source_engine": "error"}


async def find_inconsistencies(docs: list[dict]) -> dict:
    """docs: [{"name": str, "extraction": dict}]. Signale les écarts entre documents."""
    empty = {"incoherences": [], "source_engine": "skipped"}
    analyzable = [d for d in docs if d.get("extraction") and d["extraction"].get("source_engine") in ("claude", "autodesk")]
    if not os.environ.get("EMERGENT_LLM_KEY") or len(analyzable) < 2:
        return empty
    try:
        from emergentintegrations.llm.chat import UserMessage
        blob = "\n".join(f"### {d['name']}\n{_compact(d['extraction'])}" for d in analyzable)[:12000]
        resp = await _chat().send_message(UserMessage(text=_INCO_PROMPT.format(docs=blob)))
        parsed = _extract_json(resp if isinstance(resp, str) else str(resp)) or {}
        if not isinstance(parsed.get("incoherences"), list):
            parsed["incoherences"] = []
        parsed["source_engine"] = "claude"
        return parsed
    except Exception as e:  # noqa: BLE001
        return {**empty, "source_engine": "error", "error": str(e)[:120]}
