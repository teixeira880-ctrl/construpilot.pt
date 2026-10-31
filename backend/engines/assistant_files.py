"""Immutable, private PDF/JPG results. Only explicit image requests call OpenAI."""
import asyncio
import base64
import hashlib
import io
import os
import re
from datetime import datetime, timezone
from html import escape  # noqa: F401
from pathlib import Path

from PIL import Image

from core.db import db
from engines.assistant_workspace import function
from engines.nom_fichier import nom_artefact, nom_document
from fastapi import HTTPException

FILE_TOOLS = [
    function("create_downloadable_file", "Criar um verdadeiro ficheiro pedido explicitamente: PDF para um relatório/solução, JPG para uma ilustração IA NÃO contratual. body contém o documento PDF ou o prompt da ilustração. A geração JPG parte do texto, não de um retoque fiel de uma fotografia. Nunca criar uma imagem sem pedido explícito. As imagens já criadas podem ser incluídas num PDF via source_artifact_ids.", {
        "format": {"type": "string", "enum": ["pdf", "jpg"]}, "title": {"type": "string", "minLength": 1, "maxLength": 160},
        "body": {"type": "string", "minLength": 1, "maxLength": 45000},
        "source_artifact_ids": {"type": "array", "items": {"type": "string"}, "maxItems": 4}}),
    function("read_generated_file", "Reler o conteúdo ou ver uma ilustração gerada anteriormente nesta conversa antes de propor uma nova versão. O ficheiro antigo é conservado.", {"artifact_id": {"type": "string"}}),
    function("edit_image_from_photo", "Editar / retocar uma FOTOGRAFIA já fornecida na conversa com IA (Nano Banana): simular obras ou uma renovação, acrescentar/retirar um elemento, mudar um acabamento ou uma cor, inserir uma construção, etc. document_id = identificador de uma imagem anexada à conversa (doc_…). body = instruções de alteração. Produz uma ilustração IA NÃO contratual a partir da fotografia real. Usar APENAS a pedido explícito de alterar/retocar uma fotografia fornecida. NUNCA para anotar, cotar ou comparar plantas (arquitetura, estruturas): usar check_plans_coherence.", {
        "document_id": {"type": "string"}, "title": {"type": "string", "minLength": 1, "maxLength": 160},
        "body": {"type": "string", "minLength": 1, "maxLength": 4000}}),
]

FILE_INSTRUCTIONS = "\nFotografias de obra: examina realmente as imagens fornecidas, distingue o que é visível das hipóteses.\nQuando te pedem uma solução, propõe opções construtivas, vantagens, limites, etapas e controlos,\nnão apenas uma série de perguntas. Para uma junção entre edifícios, trata nomeadamente os movimentos\ndiferenciais, a junta, as infiltrações e as fixações, SEM inventar uma dimensão ou um diagnóstico estrutural.\nUtiliza a pesquisa técnica genérica se estiver ativada, cita apenas as suas fontes reais. As informações\nem falta determinantes devem ser verificadas no local. Uma fotografia não valida nem capacidade resistente nem execução.\nNão mostres um raciocínio interno detalhado: fornece observações, justificação concisa e avanço útil.\nPara PDF/JPG explicitamente pedidos, chama create_downloadable_file e anuncia apenas os ficheiros\nefetivamente devolvidos. JPG = ilustração IA hipotética, não uma fotografia real nem um pormenor de execução certificado.\nUm pedido de correção produz uma nova versão com read_generated_file se necessário; conserva a antiga.\nAs novas mensagens recebidas durante o trabalho são tratadas a seguir, por ordem; não afirmes ter\ntido em conta uma precisão ausente desta ronda. Nunca geres uma imagem só porque uma fotografia está anexada.\n"


def image_requested(text):
    text = text.casefold()
    noun = r"(?:jpe?g|png|image|illustration|schéma|schema|dessin|imagem|esquema|desenho|diagram|picture)"
    if re.search(r"(?:pas (?:d[’']|de |une? )?|sans |(?:no |without |(?:do not|don't) (?:create |generate |draw )?)|não (?:cries? |geres? |desenhes? )?)" + noun, text):
        return False
    verbs = r"\b(crée|créer|créez|cree|creer|génère|générer|génerez|genere|generer|fais|fait|faites|faire|montre|montrer|mostra|mostrar|faz|fazer|produis|produire|ajoute|ajouter|illustre|illustrer|dessine|dessiner|cria|crie|gera|gerar|desenha|desenhar|create|generate|draw|make|refais|refaire|modifie|modifier|ajuste|ajuster)\b"
    return bool(re.search(noun, text) and (re.search(verbs, text) or re.search(r"\b(jpe?g|png)\b", text)))


def public_artifact(doc):
    out = {key: value for key, value in doc.items() if key not in ("_id", "data_b64", "body", "user_id")}
    if "filename" in out:
        out["filename"] = nom_artefact(doc)
    return out


async def owned_artifact(ident, uid, conversation_id=None):
    query = {"artifact_id": ident, "user_id": uid}
    if conversation_id:
        query["conversation_id"] = conversation_id
    doc = await db.assistant_artifacts.find_one(query, {"_id": 0})
    if not doc:
        raise HTTPException(404, "Ficheiro inacessível nesta conversa.")
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


_BOX = str.maketrans({"─": "-", "━": "-", "│": "|", "┃": "|", "├": "+", "┤": "+", "┬": "+", "┴": "+", "┼": "+", "└": "+", "┘": "+",
                      "┌": "+", "┐": "+", "═": "=", "║": "|", "╔": "+", "╗": "+", "╚": "+", "╝": "+", "▶": ">", "◀": "<", "►": ">",
                      "▼": "v", "▲": "^", "→": "->", "←": "<-", "↓": "v", "↑": "^", "⇒": "=>", "↔": "<->"})
_BOX_RE = re.compile(r"[─━│┃├┤┬┴┼└┘┌┐═║╔╗╚╝▶◀►▼▲↓↑]")


def _clean(text, font):
    """Retira os emojis e os caracteres ausentes da fonte (saíam como quadrados vazios); substitui-os quando possível."""
    from reportlab.pdfbase import pdfmetrics
    try:
        cmap = pdfmetrics.getFont(font).face.charToGlyph
    except Exception:  # noqa: BLE001
        cmap = None
    out = []
    for ch in text:
        o = ord(ch)
        if o in (0xFE0F, 0x200D) or 0x1F000 <= o <= 0x1FAFF or 0x2600 <= o <= 0x26FF and ch not in "⚠":
            continue
        if cmap is not None and o > 127 and o not in cmap:
            ch = ch.translate(_BOX)
            if len(ch) == 1 and ord(ch) > 127 and ord(ch) not in cmap:
                continue
        out.append(ch)
    return "".join(out)


def _blocks(body):
    """Divide o markdown em blocos: tabelas, código / esquemas ASCII, linhas comuns."""
    lines, out, i = body.splitlines(), [], 0
    while i < len(lines):
        ln = lines[i]
        if ln.strip().startswith("```"):
            j = i + 1
            buf = []
            while j < len(lines) and not lines[j].strip().startswith("```"):
                buf.append(lines[j])
                j += 1
            out.append(("code", buf))
            i = j + 1
            continue
        if ln.strip().startswith("|") and ln.count("|") >= 2:
            rows = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                r = lines[i].strip()
                if not re.fullmatch(r"\|?(\s*:?-{2,}:?\s*\|)+\s*:?-*:?\s*\|?", r):
                    rows.append([c.strip() for c in r.strip("|").split("|")])
                i += 1
            out.append(("table", rows))
            continue
        if _BOX_RE.search(ln) or re.fullmatch(r"\s*[\[\(].*[\]\)]\s*", ln or "x") and i + 1 < len(lines) and _BOX_RE.search(lines[i + 1] or ""):
            buf = []
            while i < len(lines) and lines[i].strip() and (_BOX_RE.search(lines[i]) or re.fullmatch(r"\s*[\[\(].*[\]\)]\s*", lines[i])
                                                          or len(lines[i].strip()) < 4):
                buf.append(lines[i])
                i += 1
            if buf:
                out.append(("code", buf))
                continue
        out.append(("line", ln))
        i += 1
    return out


def build_document_pdf(title, body, images=()):
    """Documento do Assistente com apresentação premium: fontes da marca, tabelas verdadeiras, esquemas ASCII em bloco legível,
    cabeçalho de marca, rodapé numerado. Nenhum caráter não imprimível (sem quadrados vazios)."""
    from xml.sax.saxutils import escape as _esc
    from reportlab.lib import colors
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.platypus import Image as PDFImage
    from reportlab.platypus import KeepTogether, Paragraph, Preformatted, SimpleDocTemplate, Spacer, Table, TableStyle
    from engines.bet_core import brand as _brand   # noqa: F401 — regista as fontes DV / DVB / TT
    from reportlab.pdfbase.pdfmetrics import registerFontFamily
    registerFontFamily("DV", normal="DV", bold="DVB", italic="DV", boldItalic="DVB")
    font, bold, head = "DV", "DVB", "TT"
    green = colors.HexColor("#203b2d")  # verde ConstruPilot
    ink = colors.HexColor("#1f2933")
    text_style = ParagraphStyle("body", fontName=font, fontSize=9.6, leading=14, spaceAfter=4, textColor=ink)
    cell = ParagraphStyle("cell", parent=text_style, fontSize=8.4, leading=11, spaceAfter=0)
    cellh = ParagraphStyle("cellh", parent=cell, fontName=bold, textColor=colors.white)
    title_style = ParagraphStyle("title", parent=text_style, fontName=head, fontSize=21, leading=26, textColor=green, spaceAfter=10)
    h_styles = {1: ParagraphStyle("h1", parent=text_style, fontName=head, fontSize=15, leading=20, spaceBefore=12, spaceAfter=5, textColor=green),
                2: ParagraphStyle("h2", parent=text_style, fontName=head, fontSize=12.5, leading=17, spaceBefore=9, spaceAfter=4, textColor=ink),
                3: ParagraphStyle("h3", parent=text_style, fontName=bold, fontSize=10.5, leading=15, spaceBefore=6, spaceAfter=3)}
    mono = ParagraphStyle("mono", fontName="Courier", fontSize=8.2, leading=10.4, textColor=ink, backColor=colors.HexColor("#f4f8f7"),
                          borderColor=colors.HexColor("#d5e3df"), borderWidth=0.6, borderPadding=6, spaceBefore=4, spaceAfter=8)
    logo_path = Path(__file__).resolve().parents[2] / "frontend" / "public" / "construpilot-icon.png"
    brand = Paragraph("Assistente de Obra <font size=10 color='#6b7280'>· ConstruPilot</font>", ParagraphStyle("b", parent=title_style, fontSize=16, spaceAfter=0))
    if logo_path.exists():
        hd = Table([[PDFImage(str(logo_path), width=34, height=34), brand]], colWidths=[42, 440])
        hd.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("LEFTPADDING", (0, 0), (-1, -1), 0)]))
        story = [hd, Spacer(1, 8)]
    else:
        story = [brand, Spacer(1, 8)]
    story.append(Paragraph(_esc(_clean(title, head)), title_style))
    width = 595 - 2 * 42
    for kind, val in _blocks(body):
        if kind == "line":
            story.append(_markdown_paragraph(_clean(val, font), text_style, h_styles, Paragraph, Spacer))
        elif kind == "code":
            txt = "\n".join(_clean(x, "Courier").translate(_BOX) for x in val)
            txt = txt.encode("latin-1", "replace").decode("latin-1").replace("?", "?")
            story.append(Preformatted(txt, mono))
        elif kind == "table" and val:
            n = max(len(r) for r in val)
            rows = [r + [""] * (n - len(r)) for r in val]
            lens = [max(len(r[k]) for r in rows) + 4 for k in range(n)]
            tot = sum(lens) or 1
            cw = [max(width * 0.10, width * l / tot) for l in lens]
            k = width / sum(cw)
            cw = [c * k for c in cw]
            data = [[Paragraph(_inline_md(_esc(_clean(c, bold if ri == 0 else font))), cellh if ri == 0 else cell) for c in r] for ri, r in enumerate(rows)]
            t = Table(data, colWidths=cw, repeatRows=1)
            st = [("BACKGROUND", (0, 0), (-1, 0), green), ("VALIGN", (0, 0), (-1, -1), "TOP"),
                  ("LINEBELOW", (0, 0), (-1, -1), 0.3, colors.HexColor("#d5e3df")), ("TOPPADDING", (0, 0), (-1, -1), 3),
                  ("BOTTOMPADDING", (0, 0), (-1, -1), 3), ("LEFTPADDING", (0, 0), (-1, -1), 4), ("RIGHTPADDING", (0, 0), (-1, -1), 4)]
            st += [("BACKGROUND", (0, i), (-1, i), colors.HexColor("#f4f8f7")) for i in range(2, len(rows), 2)]
            t.setStyle(TableStyle(st))
            story += [Spacer(1, 3), t, Spacer(1, 8)]
    for data in images:
        from PIL import Image
        with Image.open(io.BytesIO(data)) as im:
            w_, h_ = im.size
        scale = min(width / w_, 520 / h_)
        story.extend([Spacer(1, 10), PDFImage(io.BytesIO(data), width=w_ * scale, height=h_ * scale)])
    story.extend([Spacer(1, 12), Paragraph("Documento de apoio à decisão — hipóteses e ilustrações a verificar no local. Não vale como validação estrutural nem como planta de execução.",
                                           ParagraphStyle("disc", parent=text_style, fontSize=8, textColor=colors.HexColor("#6b7280")))])

    def _page(c, d):
        c.saveState()
        from .identidade_pt import faixa_azulejo
        faixa_azulejo(c, 0, 842 - 9, 595, 9)   # faixa de azulejos (identidade .pt)
        c.setFont(font, 7.5)
        c.setFillColor(colors.HexColor("#6b7280"))
        c.drawString(42, 22, _clean(title, font)[:90])
        c.drawRightString(595 - 42, 22, f"ConstruPilot · página {d.page}")
        c.restoreState()
    output = io.BytesIO()
    SimpleDocTemplate(output, title=title, author="ConstruPilot", leftMargin=42, rightMargin=42, topMargin=40, bottomMargin=44).build(
        story, onFirstPage=_page, onLaterPages=_page)
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
        raise RuntimeError("Nenhuma imagem devolvida")
    with Image.open(io.BytesIO(images[0])) as original:
        image = original.convert("RGB")
        band = max(48, image.width // 24)
        output = Image.new("RGB", (image.width, image.height + band), "white")
        output.paste(image, (0, 0))
        font = ImageFont.load_default(size=max(13, image.width // 60))
        ImageDraw.Draw(output).text((16, image.height + band // 3), "ConstruPilot | Ilustração IA - A validar no local | Não contratual", fill="#17483f", font=font)
        buffer = io.BytesIO()
        output.save(buffer, "JPEG", quality=92)
        return buffer.getvalue()


async def create_file(args, user, conv):
    uid, cid = user["user_id"], conv["conversation_id"]
    if args["format"] == "jpg" and not image_requested(conv.get("_user_request_text", "")):
        raise HTTPException(400, "É necessário um pedido explícito de criação de imagem/JPG para lançar esta operação.")
    digest = hashlib.sha256((conv["_quote_request_id"] + str(conv.get("_file_call_id", ""))).encode()).hexdigest()[:28]
    ident = "file_" + digest
    old = await db.assistant_artifacts.find_one({"artifact_id": ident, "user_id": uid}, {"_id": 0})
    if old:
        return {"ok": True, "artifact": public_artifact(old)}
    if args["format"] == "jpg" and await db.assistant_artifacts.find_one({"user_id": uid, "conversation_id": cid, "request_id": conv["_quote_request_id"], "format": "jpg"}, {"_id": 1}):
        raise HTTPException(409, "Já foi criada uma ilustração para este pedido. Peça uma variante na mensagem seguinte.")
    images = []
    for source in args["source_artifact_ids"]:
        item = await owned_artifact(source, uid, cid)
        if item["mime"] == "image/jpeg":
            images.append(base64.b64decode(item["data_b64"]))
    if args["format"] == "pdf":
        data = await asyncio.to_thread(build_document_pdf, args["title"], args["body"], images)
        mime = "application/pdf"
    else:
        prompt = "Ilustração técnica concetual de construção, não uma planta de execução nem uma fotografia real de obra. Nenhuma cota inventada. " + args["body"]
        data = await asyncio.to_thread(_generate_jpg, prompt)
        mime = "image/jpeg"
        from engines.expenses.store import observe
        await observe(source="assistant_image", source_id=ident, provider="emergent" if os.environ.get("ASSISTANT_PROVIDER") == "anthropic" else "openai_direct", feature="assistant_image", model=os.environ["ASSISTANT_IMAGE_MODEL"], units={"images": 1}, state="completed")
    if len(data) > 8 * 1024 * 1024:
        raise HTTPException(413, "Resultado demasiado volumoso; peça um documento mais curto.")
    doc = {"artifact_id": ident, "user_id": uid, "conversation_id": cid, "request_id": conv["_quote_request_id"], "title": args["title"], "body": args["body"],
           "filename": nom_document("Documento" if args["format"] == "pdf" else "Ilustracao", args["title"], ext=args["format"]), "format": args["format"], "mime": mime, "size": len(data),
           "data_b64": base64.b64encode(data).decode(), "source_artifact_ids": args["source_artifact_ids"],
           "created_at": datetime.now(timezone.utc).isoformat(), "illustrative": args["format"] == "jpg",
           "download": f"/assistant/artifacts/{ident}/content"}
    await db.assistant_artifacts.update_one({"artifact_id": ident, "user_id": uid}, {"$setOnInsert": doc}, upsert=True)
    return {"ok": True, "artifact": public_artifact(doc)}

async def edit_image(args, user, conv, source_bytes):
    """Edição de uma fotografia fornecida via Nano Banana (imagem para imagem). Artefacto de imagem não contratual."""
    uid, cid = user["user_id"], conv["conversation_id"]
    digest = hashlib.sha256((conv["_quote_request_id"] + str(conv.get("_file_call_id", "")) + "edit").encode()).hexdigest()[:28]
    ident = "file_" + digest
    old = await db.assistant_artifacts.find_one({"artifact_id": ident, "user_id": uid}, {"_id": 0})
    if old:
        return {"ok": True, "artifact": public_artifact(old)}
    from engines import image_studio
    prompt = ("Edição fotográfica realista a partir da imagem fornecida: conserva o enquadramento, a perspetiva, a luz "
              "e o ambiente reais da fotografia. " + args["body"] +
              " Resultado fotorrealista, escala e sombras coerentes. Nenhum texto, nenhuma anotação, nenhuma marca de água.")
    results = await image_studio.generate(prompt=prompt, provider="gemini", reference_images=[source_bytes],
                                          feature="assistant_image_edit", session_id="edit_" + cid)
    img, _mime = results[0]
    data = await asyncio.to_thread(_brand_band, img)
    if len(data) > 8 * 1024 * 1024:
        raise HTTPException(413, "Resultado demasiado volumoso.")
    doc = {"artifact_id": ident, "user_id": uid, "conversation_id": cid, "request_id": conv["_quote_request_id"],
           "title": args["title"], "body": args["body"], "filename": nom_document("Fotografia-editada", args["title"], ext="jpg"), "format": "jpg",
           "mime": "image/jpeg", "size": len(data), "data_b64": base64.b64encode(data).decode(),
           "source_artifact_ids": [], "edited_from": args.get("document_id"),
           "created_at": datetime.now(timezone.utc).isoformat(), "illustrative": True,
           "download": f"/assistant/artifacts/{ident}/content"}
    await db.assistant_artifacts.update_one({"artifact_id": ident, "user_id": uid}, {"$setOnInsert": doc}, upsert=True)
    return {"ok": True, "artifact": public_artifact(doc)}


def _brand_band(image_bytes: bytes) -> bytes:
    from PIL import Image, ImageDraw, ImageFont
    with Image.open(io.BytesIO(image_bytes)) as original:
        image = original.convert("RGB")
        band = max(48, image.width // 24)
        output = Image.new("RGB", (image.width, image.height + band), "white")
        output.paste(image, (0, 0))
        font = ImageFont.load_default(size=max(13, image.width // 60))
        ImageDraw.Draw(output).text((16, image.height + band // 3),
                                    "ConstruPilot | Edição IA - A validar no local | Não contratual",
                                    fill="#17483f", font=font)
        buffer = io.BytesIO()
        output.save(buffer, "JPEG", quality=92)
        return buffer.getvalue()


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
    body = "\n".join([f'Camadas (esquerda → direita): ' + " | ".join(f"{l['label']} {float(l['thickness_cm']):g} cm" for l in args["layers"])] +
                     [f"- {x['label']}" + (f" — {float(x['value_cm']):g} cm" if x.get("value_cm") else "") for x in args.get("features") or []] +
                     [f'Hipótese / a validar: {n}' for n in args.get("notes") or []])
    pdf = await asyncio.to_thread(build_document_pdf, args["title"], body + "\n\nEsquema de princípio — não vale como validação técnica de execução.", [jpg])
    now = datetime.now(timezone.utc).isoformat()
    docs = []
    for fmt, mime, data in (("png", "image/png", png), ("pdf", "application/pdf", pdf)):
        aid = ident if fmt == "png" else ident[:-1] + "p"
        doc = {"artifact_id": aid, "user_id": uid, "conversation_id": cid, "request_id": conv["_quote_request_id"], "title": args["title"], "body": body,
               "filename": nom_document("Esquema-de-principio", args["title"], now, ext=fmt), "format": fmt, "mime": mime, "size": len(data), "data_b64": base64.b64encode(data).decode(),
               "source_artifact_ids": [], "created_at": now, "illustrative": True, "vector_schema": True, "schema_args": args, "download": f"/assistant/artifacts/{aid}/content"}
        await db.assistant_artifacts.update_one({"artifact_id": aid, "user_id": uid}, {"$setOnInsert": doc}, upsert=True)
        docs.append(public_artifact(doc))
    return {"ok": True, "artifact": docs[0], "pdf_artifact": docs[1], "note": "Esquema desenhado a partir das cotas fornecidas (nenhuma geração IA); PNG + PDF."}
