"""PDFs do módulo de urbanismo PT: quadro de áreas e verificação (A4), peças desenhadas (A3) e exportação ZIP.

Sem rede e sem IA: a memória descritiva usa o texto guardado no processo (gerado a pedido) ou o texto
neutro do módulo de autorização de obras. Os PDFs do requerimento, ficha estatística e estimativa
são os do módulo existente engines.autorizacao_obras_pt.dossier (reutilizados, não duplicados).
"""
from __future__ import annotations

import io
import os
import zipfile
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from xml.sax.saxutils import escape

from pypdf import PdfReader, PdfWriter
from reportlab.lib import colors
from reportlab.lib.pagesizes import A3, A4, landscape
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from engines.urbanismo_pt import regras as R
from engines.urbanismo_pt import volumes as V

VERSION = "urbanismo-pt-1.0.0"
GREEN = colors.HexColor("#285541")  # verde ConstruPilot
INK = colors.HexColor("#1f2933")
_FONT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "assets", "fonts")
_FONTS = {"regular": "Helvetica", "bold": "Helvetica-Bold"}

RESULTADO_LABEL = {"conforme": "Conforme", "nao_conforme": "Não conforme", "sem_dados": "Sem dados",
                   "atencao": "Atenção", "informativo": "Informativo"}
RESULTADO_COR = {"conforme": "#1b7f4b", "nao_conforme": "#b42318", "sem_dados": "#6b7280",
                 "atencao": "#b54708", "informativo": "#475467"}
STATUS_LABEL = {"confirmado": "confirmado", "a_confirmar": "a confirmar", "parametro_utilizador": "plano municipal"}


def _fonts() -> Dict[str, str]:
    if _FONTS["regular"] != "Helvetica":
        return _FONTS
    try:
        if "UrbDV" not in pdfmetrics.getRegisteredFontNames():
            pdfmetrics.registerFont(TTFont("UrbDV", os.path.join(_FONT_DIR, "DejaVuSans.ttf")))
            pdfmetrics.registerFont(TTFont("UrbDVB", os.path.join(_FONT_DIR, "DejaVuSans-Bold.ttf")))
        _FONTS.update(regular="UrbDV", bold="UrbDVB")
    except Exception:  # noqa: BLE001 — sem TTF: Helvetica (sem ≤ ≥)
        pass
    return _FONTS


def _hoje() -> str:
    return datetime.now(timezone.utc).strftime("%d/%m/%Y")


def _styles():
    f = _fonts()
    body = ParagraphStyle("b", fontName=f["regular"], fontSize=9.2, leading=12.5, textColor=INK)
    return {
        "title": ParagraphStyle("t", parent=body, fontName=f["bold"], fontSize=16, leading=20, textColor=GREEN, spaceAfter=4),
        "h2": ParagraphStyle("h2", parent=body, fontName=f["bold"], fontSize=11.5, leading=15, spaceBefore=9, spaceAfter=4, textColor=GREEN),
        "body": body,
        "small": ParagraphStyle("s", parent=body, fontSize=7.6, leading=9.6, textColor=colors.HexColor("#5b6670")),
        "cell": ParagraphStyle("c", parent=body, fontSize=8.2, leading=10.4),
        "cellb": ParagraphStyle("cb", parent=body, fontName=f["bold"], fontSize=8.2, leading=10.4),
        "cellh": ParagraphStyle("ch", parent=body, fontName=f["bold"], fontSize=8.2, leading=10.4, textColor=colors.white),
    }


def _p(text, style):
    return Paragraph(escape(str(text if text is not None else "—")), style)


def _table(rows, widths, s, header=True):
    data = []
    for i, r in enumerate(rows):
        st = s["cellh"] if (header and i == 0) else s["cell"]
        data.append([c if isinstance(c, Paragraph) else _p(c, st) for c in r])
    t = Table(data, colWidths=widths, repeatRows=1 if header else 0)
    style = [("BOX", (0, 0), (-1, -1), 0.4, colors.HexColor("#d9dfdc")),
             ("INNERGRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#dfe8e2")),
             ("VALIGN", (0, 0), (-1, -1), "TOP"),
             ("LEFTPADDING", (0, 0), (-1, -1), 4), ("RIGHTPADDING", (0, 0), (-1, -1), 4),
             ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
             ("ROWBACKGROUNDS", (0, 1 if header else 0), (-1, -1), [colors.white, colors.HexColor("#f4f8f7")])]
    if header:
        style.append(("BACKGROUND", (0, 0), (-1, 0), GREEN))
    t.setStyle(TableStyle(style))
    return t


def _val(v, unidade=""):
    if v is None or v == "":
        return "—"
    if isinstance(v, bool):
        return "sim" if v else "não"
    if isinstance(v, (int, float)):
        txt = V.fmt(v, 2) if isinstance(v, float) else str(v)
        return f"{txt} {unidade}".strip()
    return str(v)


def _footer(c, doc):
    f = _fonts()
    c.saveState()
    c.setFont(f["regular"], 7)
    c.setFillGray(0.4)
    c.drawString(15 * mm, 9 * mm, f"ConstruPilot · Urbanismo · {VERSION} · {_hoje()}")
    c.drawRightString(doc.pagesize[0] - 15 * mm, 9 * mm, f"Pág. {c.getPageNumber()}")
    from ..identidade_pt import faixa_azulejo
    faixa_azulejo(c, 0, doc.pagesize[1] - 5 * mm, doc.pagesize[0], 5 * mm)   # identidade .pt
    c.restoreState()


# ------------------------------------------------------------------ quadro de áreas ----
def quadro_pdf(processo: Dict[str, Any], verif: Dict[str, Any]) -> bytes:
    s = _styles()
    d = processo or {}
    ter = d.get("terreno") or {}
    req = d.get("requerente") or {}
    q = verif.get("quadro")
    rj = verif.get("rjue") or {}
    pdm = verif.get("pdm") or {}
    story: List[Any] = [
        _p("Quadro de áreas e verificação de parâmetros urbanísticos", s["title"]),
        _p(f"{d.get('title') or 'Processo'} · {verif.get('tipo_obra_label')}", s["body"]),
        Spacer(1, 3 * mm),
        _p("1. Identificação", s["h2"]),
        _table([["Requerente", req.get("nome") or "— a preencher —"],
                ["Local da obra", ", ".join(x for x in (ter.get("morada"), ter.get("codigo_postal")) if x) or "— a preencher —"],
                ["Concelho / freguesia", f"{ter.get('concelho') or '—'} / {ter.get('freguesia') or '—'}"],
                ["Artigo matricial / descrição predial", f"{ter.get('artigo_matricial') or '—'} / {ter.get('descricao_predial') or '—'}"],
                ["Plano municipal aplicável", " · ".join(x for x in (pdm.get("plano"), pdm.get("classe_espaco")) if x) or "— a indicar pelo utilizador —"],
                ["Artigos do regulamento", pdm.get("fonte_artigos") or "—"]],
               [55 * mm, 119 * mm], s, header=False),
    ]
    if q:
        af = q["afastamentos_m"]
        story += [
            _p("2. Quadro de áreas (sinopse)", s["h2"]),
            _table([["Parâmetro", "Valor", "Observação"],
                    ["Área do terreno", _val(q["area_terreno_m2"], "m²"), q["area_terreno_origem"]],
                    ["Área de implantação", _val(q["area_implantacao_m2"], "m²"),
                     f"principal {V.fmt(q['area_implantacao_principal_m2'])} m² + anexos {V.fmt(q['area_implantacao_anexos_m2'])} m²"],
                    ["Área de construção", _val(q["area_construcao_m2"], "m²"), q["area_construcao_origem"]],
                    ["Área de construção existente / criada",
                     f"{_val(q['area_construcao_existente_m2'], 'm²')} / {_val(q['area_construcao_criada_m2'], 'm²')}", "ampliações"],
                    ["Índice de ocupação do solo (Io)", _val(q["indice_ocupacao_pct"], "%"), "Ai / At × 100"],
                    ["Índice de utilização do solo (Iu)", V.fmt(q["indice_utilizacao"], 3), "Ac / At"],
                    ["N.º de pisos acima da cota de soleira", str(q["n_pisos"]), ""],
                    ["Altura piso a piso / pé-direito livre", f"{V.fmt(q['piso_a_piso_m'])} m / {V.fmt(q['pe_direito_livre_m'])} m",
                     f"laje + revestimentos {V.fmt(q['espessura_laje_m'])} m (valor de cálculo)"],
                    ["Altura da fachada / altura total", f"{V.fmt(q['altura_fachada_m'])} m / {V.fmt(q['altura_total_m'])} m", q["cobertura"]],
                    ["Afastamentos (frontal / lat. esq. / lat. dir. / tardoz)",
                     " / ".join(V.fmt(af[k]) for k in ("frontal", "lateral_esquerdo", "lateral_direito", "tardoz")) + " m", "construção principal"],
                    ["Fogos / lugares de estacionamento", f"{_val(q['n_fogos'])} / {_val(q['lugares_previstos'])}", ""]],
                   [62 * mm, 42 * mm, 70 * mm], s),
        ]
    rows = [["Verificação", "Projeto", "Limite", "Resultado", "Fonte"]]
    for it in verif.get("verificacoes") or []:
        cor = RESULTADO_COR.get(it["resultado"], "#475467")
        res = Paragraph(f'<font color="{cor}"><b>{escape(RESULTADO_LABEL.get(it["resultado"], it["resultado"]))}</b></font>', s["cell"])
        fonte = f"{it['fonte']['diploma']}" + (f" — {it['fonte']['artigo']}" if it['fonte']['artigo'] else "") + \
                f" [{STATUS_LABEL.get(it['fonte']['status'], it['fonte']['status'])}]"
        titulo = it["titulo"] + (f" — {it['nota']}" if it.get("nota") else "")
        rows.append([titulo, _val(it["valor"], it["unidade"]), _val(it["limite"], it["unidade"]), res, fonte])
    story += [_p("3. Verificação de parâmetros", s["h2"]), _table(rows, [52 * mm, 20 * mm, 20 * mm, 20 * mm, 62 * mm], s)]
    if verif.get("parametros_em_falta"):
        story += [Spacer(1, 2 * mm),
                  _p("Parâmetros do plano municipal não indicados (verificação não efetuada): " + "; ".join(verif["parametros_em_falta"]) + ".", s["small"])]
    proc = R.PROCEDIMENTO_LABEL.get(rj.get("procedimento"), rj.get("procedimento"))
    story += [
        _p("4. Enquadramento no RJUE (DL 555/99)", s["h2"]),
        _p(f"Procedimento indicativo: {proc}", s["cellb"]),
        Spacer(1, 1 * mm),
        _p(rj.get("fundamento_legal"), s["body"]),
    ]
    refs = rj.get("referencias_legais") or []
    if refs:
        story.append(_p("Referências: " + "; ".join(f"art.º {r['artigo']} — {r['descricao']}" for r in refs), s["small"]))
    if verif.get("valores_a_confirmar"):
        story += [_p("5. Valores a confirmar", s["h2"])] + [_p("• " + x, s["small"]) for x in verif["valores_a_confirmar"]]
    story += [Spacer(1, 5 * mm), _p(verif.get("aviso") or R.AVISO, s["small"])]
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, title="Quadro de áreas — ConstruPilot", leftMargin=18 * mm, rightMargin=18 * mm,
                            topMargin=16 * mm, bottomMargin=16 * mm)
    doc.build(story, onFirstPage=_footer, onLaterPages=_footer)
    return buf.getvalue()


# ------------------------------------------------------------------ desenhos ----
def desenhos(processo: Dict[str, Any], verif: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    """Desenhos esquemáticos do processo, segundo o tipo de obra: [{code, title, filename, png}]."""
    d = processo or {}
    tipo = d.get("tipo_obra")
    spec = {"parametros": d.get("parametros") or {}}
    out: List[Dict[str, Any]] = []

    def add(code, title, fname, png):
        out.append({"code": code, "title": title, "filename": fname, "png": png})

    if tipo == "muro":
        add("PLANTA_IMPLANTACAO", "Planta de implantação — muro", "planta_implantacao_muro.png", V.muro_planta(spec))
        add("ALCADOS", "Alçado do muro", "alcado_muro.png", V.muro_alcado(spec))
        add("CORTES", "Corte-tipo do muro", "corte_muro.png", V.muro_corte(spec))
    elif tipo == "piscina":
        add("PLANTA_IMPLANTACAO", "Planta de implantação — piscina", "planta_implantacao_piscina.png", V.piscina_planta(spec))
        add("CORTES", "Corte da piscina", "corte_piscina.png", V.piscina_corte(spec))
    else:
        vol = d.get("volume") or {}
        q = (verif or {}).get("quadro") or R.quadro_areas(vol, d.get("terreno"), d.get("enquadramento"))
        add("PLANTA_IMPLANTACAO", "Planta de implantação", "planta_implantacao.png", V.planta_implantacao(vol, d.get("terreno"), q))
        add("CORTES", "Corte transversal A-A", "corte_AA.png", V.corte(vol))
        add("ALCADOS", "Alçado principal", "alcado_principal.png", V.alcado(vol))
        add("AXONOMETRIA", "Vista axonométrica", "axonometria.png", V.axonometria(vol))
    return out


def pecas_desenhadas_pdf(processo: Dict[str, Any], drawings: List[Dict[str, Any]]) -> bytes:
    """Uma folha A3 horizontal por desenho, com legenda (carimbo) em português."""
    f = _fonts()
    d = processo or {}
    ter = d.get("terreno") or {}
    req = d.get("requerente") or {}
    buf = io.BytesIO()
    pw, ph = landscape(A3)
    c = canvas.Canvas(buf, pagesize=(pw, ph))
    c.setTitle("Peças desenhadas — ConstruPilot")
    for i, dw in enumerate(drawings, 1):
        m = 12 * mm
        c.setStrokeColor(INK)
        c.setLineWidth(1.2)
        c.rect(m, m, pw - 2 * m, ph - 2 * m)
        cw, chh = 120 * mm, 46 * mm
        cx, cy = pw - m - cw, m
        img = ImageReader(io.BytesIO(dw["png"]))
        iw, ih = img.getSize()
        avail_w, avail_h = pw - 2 * m - 10 * mm, ph - 2 * m - chh - 12 * mm
        sc = min(avail_w / iw, avail_h / ih)
        c.drawImage(img, m + 5 * mm + (avail_w - iw * sc) / 2, m + chh + 6 * mm, iw * sc, ih * sc)
        c.setFillColor(colors.white)
        c.rect(cx, cy, cw, chh, fill=1)
        c.setFillColor(INK)
        rows = [("Processo", d.get("title") or "—"),
                ("Requerente", req.get("nome") or "—"),
                ("Local", ", ".join(x for x in (ter.get("morada"), ter.get("concelho")) if x) or "—"),
                ("Peça", dw["title"]),
                ("Escala", "sem escala — desenho esquemático"),
                ("Data / folha", f"{_hoje()} · {i}/{len(drawings)}"),
                ("Técnico autor", "______________________  (n.º de inscrição na Ordem)")]
        yy = cy + chh - 6 * mm
        for k, val in rows:
            c.setFont(f["bold"], 7.5)
            c.drawString(cx + 3 * mm, yy, k)
            c.setFont(f["regular"], 7.5)
            c.drawString(cx + 28 * mm, yy, str(val)[:70])
            yy -= 5.6 * mm
        c.setFont(f["regular"], 6.8)
        c.setFillGray(0.35)
        c.drawString(m + 3 * mm, m + 3 * mm, V.FOOTER)
        c.showPage()
    c.save()
    return buf.getvalue()


# ------------------------------------------------------------------ exportação ----
def _merge(pdfs: List[bytes]) -> bytes:
    w = PdfWriter()
    for b in pdfs:
        try:
            w.append(PdfReader(io.BytesIO(b)))
        except Exception:  # noqa: BLE001
            continue
    out = io.BytesIO()
    w.write(out)
    return out.getvalue()


def _img_pdf(data: bytes) -> Optional[bytes]:
    try:
        from PIL import Image
        img = Image.open(io.BytesIO(data)).convert("RGB")
        out = io.BytesIO()
        img.save(out, "PDF")
        return out.getvalue()
    except Exception:  # noqa: BLE001
        return None


def export_zip(processo: Dict[str, Any], verif: Dict[str, Any], uploaded: List[Dict[str, Any]] | None = None) -> bytes:
    """ZIP do processo: quadro de áreas, peças desenhadas, PDFs do módulo de autorização (requerimento,
    memória, ficha estatística, estimativa), peças carregadas e um PDF único fundido."""
    from engines.autorizacao_obras_pt import dossier as AD

    d = processo or {}
    rj = verif.get("rjue") or {}
    resp = rj.get("respostas") or {}
    diag = {k: rj.get(k) for k in ("procedimento", "fundamento_legal", "tecnicos_obrigatorios", "pecas_necessarias")}
    drawings = desenhos(d, verif)
    files: Dict[str, bytes] = {
        "00_quadro_areas_verificacao.pdf": quadro_pdf(d, verif),
        "01_pecas_desenhadas.pdf": pecas_desenhadas_pdf(d, drawings),
        "02_requerimento.pdf": AD.construir_requerimento_pdf(resp, diag, d.get("requerente") or {}),
        "03_memoria_descritiva.pdf": AD.construir_memoria_pdf(d.get("memoria_texto") or AD.MEMORIA_FALLBACK, resp),
        "04_estimativa_custo.pdf": AD.construir_estimativa_pdf(AD.estimativa_e_calendario(resp, diag)),
    }
    if rj.get("procedimento") == "licenciamento":
        files["05_ficha_estatistica.pdf"] = AD.construir_ficha_estatistica_pdf(resp, diag)
    for dw in drawings:
        files[f"desenhos/{dw['filename']}"] = dw["png"]
    merged = [v for k, v in files.items() if k.endswith(".pdf")]
    for i, p in enumerate(uploaded or [], 10):
        ext = (p.get("filename") or "").rsplit(".", 1)[-1].lower() or "bin"
        name = f"pecas/{i:02d}_{p['code']}.{ext}"
        files[name] = p["data"]
        if ext == "pdf":
            merged.append(p["data"])
        elif ext in ("png", "jpg", "jpeg", "webp"):
            pb = _img_pdf(p["data"])
            if pb:
                merged.append(pb)
    have = {p["code"] for p in (uploaded or [])} | {dw["code"] for dw in drawings} | {"QUADRO_AREAS", "MEMORIA", "ESTIMATIVA", "FICHA_ESTATISTICA"}
    exig = R.pecas_exigidas(rj.get("procedimento") or "licenciamento", d.get("tipo_obra"))
    falta = [p["label"] for p in exig if p["required"] and p["code"] not in have]
    leia = ["Processo de urbanismo — ConstruPilot", f"Gerado em {_hoje()} ({VERSION})", "",
            f"Procedimento indicativo: {R.PROCEDIMENTO_LABEL.get(rj.get('procedimento'), rj.get('procedimento'))}", "",
            "Peças em falta (a carregar ou a produzir pelo técnico):"] + [f" - {x}" for x in falta or ["nenhuma"]] + \
           ["", "Lista indicativa (Portaria n.º 71-A/2024) — confirmar com o município.", "", R.AVISO]
    files["LEIA-ME.txt"] = "\n".join(leia).encode("utf-8")
    files["processo_completo.pdf"] = _merge(merged)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for k, v in files.items():
            z.writestr(k, v)
    return buf.getvalue()
