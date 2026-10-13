"""Immutable, private PDF/JPG results. Only explicit image requests call OpenAI."""
import asyncio
import base64
import hashlib
import io
import os
import re
from datetime import datetime, timezone
from html import escape
from pathlib import Path

from PIL import Image

from core.db import db
from engines.assistant_workspace import function
from fastapi import HTTPException

FILE_TOOLS = [
    function("create_downloadable_file", "Créer un vrai fichier demandé explicitement : PDF pour un rapport/solution, JPG pour une illustration IA NON contractuelle. body contient le document PDF ou le prompt de l'illustration. La génération JPG part du texte, pas d'une retouche fidèle d'une photo. Ne jamais créer une image sans demande explicite. Les images déjà créées peuvent être incluses dans un PDF via source_artifact_ids.", {
        "format": {"type": "string", "enum": ["pdf", "jpg"]}, "title": {"type": "string", "minLength": 1, "maxLength": 160},
        "body": {"type": "string", "minLength": 1, "maxLength": 45000},
        "source_artifact_ids": {"type": "array", "items": {"type": "string"}, "maxItems": 4}}),
    function("read_generated_file", "Relire le contenu ou voir une illustration générée précédemment dans cette conversation avant d'en proposer une nouvelle version. L'ancien fichier est conservé.", {"artifact_id": {"type": "string"}}),
]

FILE_INSTRUCTIONS = """
Photos de chantier : examine réellement les images fournies, distingue ce qui est visible des hypothèses.
Quand on demande une solution, propose des options constructives, avantages, limites, étapes et contrôles,
pas seulement une série de questions. Pour une jonction entre bâtiments, traite notamment les mouvements
différentiels, le joint, les infiltrations et les fixations, SANS inventer une dimension ou un diagnostic structurel.
Utilise la recherche technique générique si activée, cite seulement ses sources réelles. Les informations
manquantes déterminantes sont à vérifier sur site. Une photo ne valide ni capacité portante ni exécution.
N'affiche pas un raisonnement interne détaillé : fournis observations, justification concise et avancement utile.
Pour PDF/JPG explicitement demandés, appelle create_downloadable_file et annonce seulement les fichiers
effectivement retournés. JPG = illustration IA hypothétique, pas photo réelle, ni détail d'exécution certifié.
Une demande de correction produit une nouvelle version avec read_generated_file si nécessaire ; conserve l'ancienne.
Les nouveaux messages reçus pendant le travail sont traités ensuite, dans l'ordre ; ne prétends pas avoir
pris en compte une précision absente de ce tour. Ne génère jamais une image juste parce qu'une photo est jointe.
"""


def image_requested(text):
    text = text.casefold()
    noun = r"(?:jpe?g|png|image|illustration|schéma|schema|dessin|imagem|esquema|desenho|diagram|picture)"
    if re.search(r"(?:pas (?:d[’']|de |une? )?|sans |(?:no |without |(?:do not|don't) (?:create |generate |draw )?)|não (?:cries? |geres? |desenhes? )?)" + noun, text):
        return False
    verbs = r"\b(crée|créer|créez|cree|creer|génère|générer|génerez|genere|generer|fais|faire|produis|produire|ajoute|ajouter|illustre|illustrer|dessine|dessiner|cria|crie|gera|gerar|desenha|desenhar|create|generate|draw|make|refais|refaire|modifie|modifier|ajuste|ajuster)\b"
    return bool(re.search(noun, text) and (re.search(verbs, text) or re.search(r"\b(jpe?g|png)\b", text)))


def public_artifact(doc):
    return {key: value for key, value in doc.items() if key not in ("_id", "data_b64", "body", "user_id")}


async def owned_artifact(ident, uid, conversation_id=None):
    query = {"artifact_id": ident, "user_id": uid}
    if conversation_id:
        query["conversation_id"] = conversation_id
    doc = await db.assistant_artifacts.find_one(query, {"_id": 0})
    if not doc:
        raise HTTPException(404, "Fichier inaccessible dans cette conversation.")
    return doc


def _inline_md(text):
    """Bold/italic/code markers → reportlab inline tags, on already escaped text."""
    text = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text)
    text = re.sub(r"(?<!\w)\*(?!\s)(.+?)(?<!\s)\*(?!\w)", r"<i>\1</i>", text)
    return re.sub(r"`(.+?)`", r"<font face='Courier'>\1</font>", text)


def _markdown_paragraph(line, text_style, h_styles, Paragraph, Spacer):
    from xml.sax.saxutils import escape
    raw = line.rstrip()
    if not raw.strip():
        return Spacer(1, 4)
    if re.fullmatch(r"\s*-{3,}\s*", raw):
        return Spacer(1, 8)
    m = re.match(r"^(#{1,6})\s+(.*)$", raw)
    if m:
        return Paragraph(_inline_md(escape(m.group(2))), h_styles[min(len(m.group(1)), 3)])
    if re.match(r"^\s*\|?\s*:?-{2,}", raw) and "|" in raw:
        return Spacer(1, 0)
    if raw.strip().startswith("|"):
        cells = [c.strip() for c in raw.strip().strip("|").split("|")]
        return Paragraph(_inline_md(escape("  ·  ".join(c for c in cells if c))), text_style)
    m = re.match(r"^(\s*)([-*•]|\d+[.)])\s+(.*)$", raw)
    if m:
        indent = 12 + 10 * (len(m.group(1)) // 2)
        bullet = "•" if not m.group(2)[0].isdigit() else m.group(2)
        return Paragraph(f"{bullet} " + _inline_md(escape(m.group(3))), text_style, ) if indent == 12 else Paragraph("&#160;" * (indent // 3) + f"{bullet} " + _inline_md(escape(m.group(3))), text_style)
    if raw.lstrip().startswith(">"):
        return Paragraph("<i>" + _inline_md(escape(raw.lstrip()[1:].strip())) + "</i>", text_style)
    return Paragraph(_inline_md(escape(raw)), text_style)


def build_document_pdf(title, body, images=()):
    import reportlab
    from reportlab.lib import colors
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.platypus import Image as PDFImage
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer
    font = "AssistantVera"
    if font not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(TTFont(font, str(Path(reportlab.__file__).parent / "fonts" / "Vera.ttf")))
    text_style = ParagraphStyle("body", fontName=font, fontSize=10, leading=15, spaceAfter=6, wordWrap="CJK")
    title_style = ParagraphStyle("title", parent=text_style, fontSize=20, leading=26, textColor=colors.HexColor("#137566"), spaceAfter=16)
    h_styles = {1: ParagraphStyle("h1", parent=text_style, fontSize=15, leading=20, spaceBefore=10, spaceAfter=6, textColor=colors.HexColor("#137566")),
                2: ParagraphStyle("h2", parent=text_style, fontSize=13, leading=18, spaceBefore=8, spaceAfter=4),
                3: ParagraphStyle("h3", parent=text_style, fontSize=11, leading=16, spaceBefore=6, spaceAfter=3)}
    from reportlab.platypus import Table, TableStyle
    logo_path = Path(__file__).resolve().parents[2] / "frontend" / "public" / "assistant-btp-icon.png"
    brand = Paragraph("Assistant BTP <font size=10 color='#6b7280'>· ConstruPilot</font>", title_style)
    if logo_path.exists():
        head = Table([[PDFImage(str(logo_path), width=46, height=46), brand]], colWidths=[56, 400])
        head.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("LEFTPADDING", (0, 0), (-1, -1), 0)]))
        story = [head, Paragraph(escape(title), title_style)]
    else:
        story = [brand, Paragraph(escape(title), title_style)]
    for line in body.splitlines():
        story.append(_markdown_paragraph(line, text_style, h_styles, Paragraph, Spacer))
    for data in images:
        from PIL import Image
        with Image.open(io.BytesIO(data)) as im:
            width, height = im.size
        scale = min(460 / width, 500 / height)
        story.extend([Spacer(1, 12), PDFImage(io.BytesIO(data), width=width * scale, height=height * scale)])
    story.extend([Spacer(1, 12), Paragraph("Document d’aide à la décision — hypothèses et illustrations à vérifier sur site. Ne vaut pas validation structurelle ni plan d’exécution.", text_style)])
    output = io.BytesIO()
    SimpleDocTemplate(output, title=title, author="ConstruPilot", leftMargin=42, rightMargin=42, topMargin=42, bottomMargin=42).build(story)
    return output.getvalue()


def _image_key():
    """Universal key when the assistant runs on it (ASSISTANT_PROVIDER=anthropic), else the account's OpenAI key."""
    return os.environ["EMERGENT_LLM_KEY"] if os.environ.get("ASSISTANT_PROVIDER") == "anthropic" else os.environ["OPENAI_API_KEY"]


def _generate_jpg(prompt):
    # Primary key first; on credits/quota failure only, one retry on the universal key.
    try:
        return _generate_jpg_with(prompt, _image_key())
    except Exception as exc:  # noqa: BLE001
        from engines.assistant_fallback import is_billing_error
        if is_billing_error(exc) and os.environ.get("EMERGENT_LLM_KEY") and _image_key() != os.environ["EMERGENT_LLM_KEY"]:
            return _generate_jpg_with(prompt, os.environ["EMERGENT_LLM_KEY"])
        raise


def _generate_jpg_with(prompt, api_key):
    from emergentintegrations.llm.openai.image_generation import OpenAIImageGeneration
    from PIL import Image, ImageDraw, ImageFont
    generator = OpenAIImageGeneration(api_key=api_key)
    images = asyncio.run(generator.generate_images(prompt=prompt, model=os.environ["ASSISTANT_IMAGE_MODEL"], number_of_images=1, quality="medium"))
    if not images:
        raise RuntimeError("Aucune image retournée")
    with Image.open(io.BytesIO(images[0])) as original:
        image = original.convert("RGB")
        band = max(48, image.width // 24)
        output = Image.new("RGB", (image.width, image.height + band), "white")
        output.paste(image, (0, 0))
        font = ImageFont.load_default(size=max(13, image.width // 60))
        ImageDraw.Draw(output).text((16, image.height + band // 3), "ConstruPilot | Illustration IA - A valider sur site | Non contractuel", fill="#17483f", font=font)
        buffer = io.BytesIO()
        output.save(buffer, "JPEG", quality=92)
        return buffer.getvalue()


async def create_file(args, user, conv):
    uid, cid = user["user_id"], conv["conversation_id"]
    if args["format"] == "jpg" and not image_requested(conv.get("_user_request_text", "")):
        raise HTTPException(400, "Une demande explicite de création d’image/JPG est nécessaire pour lancer cette opération.")
    digest = hashlib.sha256((conv["_quote_request_id"] + str(conv.get("_file_call_id", ""))).encode()).hexdigest()[:28]
    ident = "file_" + digest
    old = await db.assistant_artifacts.find_one({"artifact_id": ident, "user_id": uid}, {"_id": 0})
    if old:
        return {"ok": True, "artifact": public_artifact(old)}
    if args["format"] == "jpg" and await db.assistant_artifacts.find_one({"user_id": uid, "conversation_id": cid, "request_id": conv["_quote_request_id"], "format": "jpg"}, {"_id": 1}):
        raise HTTPException(409, "Une illustration a déjà été créée pour cette demande. Demandez une variante dans le message suivant.")
    images = []
    for source in args["source_artifact_ids"]:
        item = await owned_artifact(source, uid, cid)
        if item["mime"] == "image/jpeg":
            images.append(base64.b64decode(item["data_b64"]))
    if args["format"] == "pdf":
        data = await asyncio.to_thread(build_document_pdf, args["title"], args["body"], images)
        mime = "application/pdf"
    else:
        prompt = "Illustration technique BTP conceptuelle, pas un plan d'exécution ni une photo de chantier réelle. Aucune cote inventée. " + args["body"]
        data = await asyncio.to_thread(_generate_jpg, prompt)
        mime = "image/jpeg"
        from engines.expenses.store import observe
        await observe(source="assistant_image", source_id=ident, provider="emergent" if os.environ.get("ASSISTANT_PROVIDER") == "anthropic" else "openai_direct", feature="assistant_image", model=os.environ["ASSISTANT_IMAGE_MODEL"], units={"images": 1}, state="completed")
    if len(data) > 8 * 1024 * 1024:
        raise HTTPException(413, "Résultat trop volumineux ; demandez un document plus court.")
    doc = {"artifact_id": ident, "user_id": uid, "conversation_id": cid, "request_id": conv["_quote_request_id"], "title": args["title"], "body": args["body"],
           "filename": ident + "." + args["format"], "format": args["format"], "mime": mime, "size": len(data),
           "data_b64": base64.b64encode(data).decode(), "source_artifact_ids": args["source_artifact_ids"],
           "created_at": datetime.now(timezone.utc).isoformat(), "illustrative": args["format"] == "jpg",
           "download": f"/assistant/artifacts/{ident}/content"}
    await db.assistant_artifacts.update_one({"artifact_id": ident, "user_id": uid}, {"$setOnInsert": doc}, upsert=True)
    return {"ok": True, "artifact": public_artifact(doc)}

async def create_schema(args, user, conv):
    """Deterministic drawn section (PNG + PDF pair) stored as artifacts; no image model involved."""
    from engines.section_schema import draw_schema
    uid, cid = user["user_id"], conv["conversation_id"]
    digest = hashlib.sha256((conv["_quote_request_id"] + str(conv.get("_file_call_id", "")) + "schema").encode()).hexdigest()[:28]
    ident = "file_" + digest
    old = await db.assistant_artifacts.find_one({"artifact_id": ident, "user_id": uid}, {"_id": 0})
    if old:
        return {"ok": True, "artifact": public_artifact(old)}
    png = await asyncio.to_thread(draw_schema, args)
    with Image.open(io.BytesIO(png)) as im:
        buf = io.BytesIO(); im.convert("RGB").save(buf, "JPEG", quality=92); jpg = buf.getvalue()
    body = "\n".join([f"Couches (gauche → droite) : " + " | ".join(f"{l['label']} {float(l['thickness_cm']):g} cm" for l in args["layers"])] +
                     [f"- {x['label']}" + (f" — {float(x['value_cm']):g} cm" if x.get("value_cm") else "") for x in args.get("features") or []] +
                     [f"Hypothèse / à valider : {n}" for n in args.get("notes") or []])
    pdf = await asyncio.to_thread(build_document_pdf, args["title"], body + "\n\nSchéma de principe — ne vaut pas validation technique d'exécution.", [jpg])
    now = datetime.now(timezone.utc).isoformat()
    docs = []
    for fmt, mime, data in (("png", "image/png", png), ("pdf", "application/pdf", pdf)):
        aid = ident if fmt == "png" else ident[:-1] + "p"
        doc = {"artifact_id": aid, "user_id": uid, "conversation_id": cid, "request_id": conv["_quote_request_id"], "title": args["title"], "body": body,
               "filename": f"schema-de-principe.{fmt}", "format": fmt, "mime": mime, "size": len(data), "data_b64": base64.b64encode(data).decode(),
               "source_artifact_ids": [], "created_at": now, "illustrative": True, "vector_schema": True, "schema_args": args, "download": f"/assistant/artifacts/{aid}/content"}
        await db.assistant_artifacts.update_one({"artifact_id": aid, "user_id": uid}, {"$setOnInsert": doc}, upsert=True)
        docs.append(public_artifact(doc))
    return {"ok": True, "artifact": docs[0], "pdf_artifact": docs[1], "note": "Schéma dessiné depuis les cotes fournies (aucune génération IA) ; PNG + PDF."}
