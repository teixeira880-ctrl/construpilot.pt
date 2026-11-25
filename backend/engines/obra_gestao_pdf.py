"""PDF da gestão de obra: entrada do diário, relatório semanal e registo de qualidade e segurança.

Mesma identidade que os documentos da empresa (logótipo, cor, rodapé legal) via pdf_docs.
"""
from __future__ import annotations

import base64
from io import BytesIO
from typing import Optional
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.platypus import Image, Paragraph, SimpleDocTemplate, Spacer

from engines import obra_gestao_txt as TX
from engines.pdf_docs import _doc_styles, _header_banner, _page_footer, _palette
from engines.pdf_i18n import pdf_labels
from engines.pdf_takeoff import _styles, _table


def _doc(branding: Optional[dict]):
    P = _palette(branding)
    S = _doc_styles(_styles(), P, "bandeau")
    buf = BytesIO()
    pdf = SimpleDocTemplate(buf, pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm, topMargin=14 * mm, bottomMargin=26 * mm)
    story: list = []
    _header_banner(story, branding, S, P)
    return P, S, buf, pdf, story


def _build(pdf, story, branding, P, buf) -> bytes:
    L = pdf_labels(TX.LANG)

    def _on_page(canvas, d):
        _page_footer(canvas, d, branding, P, L)

    pdf.build(story, onFirstPage=_on_page, onLaterPages=_on_page)
    return buf.getvalue()


def _p(txt: Optional[str]) -> str:
    return escape(str(txt or "")).replace("\n", "<br/>")


def _grid(P, rows, widths):
    return _table(rows, widths, style_extras=[
        ("BACKGROUND", (0, 0), (-1, 0), P["head"]), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"), ("FONTSIZE", (0, 0), (-1, -1), 8.5),
        ("VALIGN", (0, 1), (-1, -1), "TOP"), ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, P["soft"]]),
        ("LEFTPADDING", (0, 0), (-1, -1), 5), ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4)], repeat_rows=1)


def _img(data: bytes, w_mm: float, max_h_mm: float):
    try:
        from reportlab.lib.utils import ImageReader
        ir = ImageReader(BytesIO(data))
        iw, ih = ir.getSize()
        w = w_mm * mm
        h = w * ih / iw if iw else max_h_mm * mm
        if h > max_h_mm * mm:
            h = max_h_mm * mm
            w = h * iw / ih
        return Image(BytesIO(data), width=w, height=h)
    except Exception:  # noqa: BLE001
        return None


def _meteo_txt(m: Optional[dict]) -> str:
    if not m:
        return TX.DIARIO_PDF["sem_meteo"]
    partes = [m.get("descricao") or "—"]
    if m.get("tmin") is not None and m.get("tmax") is not None:
        partes.append(f"{m['tmin']} / {m['tmax']} °C")
    if m.get("precipitacao_mm") is not None:
        partes.append(f"{m['precipitacao_mm']} mm")
    if m.get("vento_max_kmh") is not None:
        partes.append(f"{m['vento_max_kmh']} km/h")
    return " · ".join(str(x) for x in partes) + f"  ({m.get('fonte', '')})"


def diario_pdf(entrada: dict, obra: dict, branding: Optional[dict], fotos: list[bytes], assinatura_png: Optional[bytes]) -> bytes:
    D = TX.DIARIO_PDF
    P, S, buf, pdf, story = _doc(branding)
    story.append(Paragraph(D["kicker"], S["kicker"]))
    story.append(Paragraph(f"{D['titulo']} — {escape(entrada['data'])}", S["h1"]))
    story.append(Paragraph(_p(" · ".join(x for x in [obra.get("name"), obra.get("address"), obra.get("city")] if x)), S["muted"]))
    story.append(Spacer(1, 8))
    ef = entrada.get("efetivo_auto") or {}
    efetivo = D["trabalhadores"].format(n=ef.get("trabalhadores", 0), h=ef.get("horas", 0))
    extra = "; ".join(f"{e.get('equipa')}: {e.get('n')}" for e in entrada.get("efetivos") or [] if e.get("equipa"))
    rows = [[D["meteo"], Paragraph(_p(_meteo_txt(entrada.get("meteo"))), S["body"])],
            [D["efetivo"], Paragraph(_p(efetivo + (f" — {extra}" if extra else "")), S["body"])]]
    for k in ("trabalhos", "ocorrencias", "entregas", "visitas", "observacoes"):
        if (entrada.get(k) or "").strip():
            rows.append([D[k], Paragraph(_p(entrada[k]), S["body"])])
    story.append(_table(rows, [40 * mm, 134 * mm], style_extras=[
        ("VALIGN", (0, 0), (-1, -1), "TOP"), ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9), ("LINEBELOW", (0, 0), (-1, -1), 0.4, P["line"]),
        ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5)]))
    adit = entrada.get("aditamentos") or []
    if adit:
        story.append(Spacer(1, 8))
        story.append(Paragraph(D["aditamentos"], S["h2"]))
        for a in adit:
            story.append(Paragraph(f"<b>{escape((a.get('at') or '')[:16].replace('T', ' '))} — {escape((a.get('por') or {}).get('nome', ''))}</b>: "
                                   f"{_p(a.get('texto'))}", S["body"]))
    story.append(Spacer(1, 10))
    sig = entrada.get("assinatura")
    if sig:
        story.append(Paragraph(D["assinatura"].format(nome=escape(sig.get("nome", "")), data=escape((sig.get("at") or "")[:16].replace("T", " "))), S["body"]))
        if assinatura_png:
            im = _img(assinatura_png, 50, 22)
            if im:
                story.append(im)
    else:
        story.append(Paragraph(D["nao_assinado"], S["muted"]))
    v = entrada.get("visto_fiscal")
    if v:
        story.append(Paragraph(D["visto"].format(nome=escape(v.get("nome", "")), data=escape((v.get("at") or "")[:10])), S["body"]))
        if v.get("observacao"):
            story.append(Paragraph(_p(v["observacao"]), S["muted"]))
    if fotos:
        story.append(Spacer(1, 10))
        story.append(Paragraph(f"{D['fotos']} ({len(fotos)})", S["h2"]))
        cells, row = [], []
        for data in fotos[:12]:
            im = _img(data, 54, 42)
            if im:
                row.append(im)
            if len(row) == 3:
                cells.append(row)
                row = []
        if row:
            cells.append(row + [""] * (3 - len(row)))
        if cells:
            story.append(_table(cells, [58 * mm] * 3, style_extras=[("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                                                                   ("TOPPADDING", (0, 0), (-1, -1), 3)]))
    return _build(pdf, story, branding, P, buf)


def relatorio_pdf(obra: dict, dados: dict, alertas: list[dict], curva: Optional[dict], sintese: Optional[str],
                  branding: Optional[dict]) -> bytes:
    R = TX.RELATORIO
    P, S, buf, pdf, story = _doc(branding)
    story.append(Paragraph(R["kicker"], S["kicker"]))
    story.append(Paragraph(f"{R['titulo']} — {escape(obra.get('name') or '')}", S["h1"]))
    story.append(Paragraph(R["semana"].format(de=dados["de"], ate=dados["ate"]), S["muted"]))
    story.append(Spacer(1, 8))
    if sintese:
        story.append(Paragraph(R["resumo"], S["h2"]))
        story.append(Paragraph(_p(sintese), S["body"]))
        story.append(Spacer(1, 6))
    story.append(Paragraph(R["avanco"], S["h2"]))
    if curva and curva.get("disponivel"):
        story.append(Paragraph(f"<b>{curva['real_hoje_pct']} %</b> / {curva['previsto_hoje_pct']} % "
                               f"({curva['desvio_pp']:+} pp){' · SPI ' + str(curva['spi']) if curva.get('spi') else ''}"
                               f"{' · CPI ' + str(curva['cpi']) if curva.get('cpi') else ''}", S["body"]))
    story.append(Paragraph(R["dias_diario"].format(n=dados["dias_diario"], h=dados["horas"], f=dados["fotos"]), S["body"]))
    if dados["trabalhos"]:
        story.append(_grid(P, [["", ""]] + [[t["data"], Paragraph(_p(t["texto"]), S["body"])] for t in dados["trabalhos"]],
                           [24 * mm, 150 * mm]))
    elif not dados["dias_diario"]:
        story.append(Paragraph(R["sem_registos"], S["muted"]))
    story.append(Spacer(1, 6))
    story.append(Paragraph(R["qse"], S["h2"]))
    story.append(Paragraph(R["nc_abertas"].format(n=dados["nc_abertas"], i=dados["acidentes"], q=dados["quase_acidentes"], d=dados["dds"]), S["body"]))
    if dados["qse_semana"]:
        rows = [[TX.NUM, "", "", ""]] + [[str(q["numero"]), q["tipo"], Paragraph(_p(q["titulo"]), S["body"]),
                                         TX.QSE_ESTADOS.get(q["estado"], q["estado"])] for q in dados["qse_semana"]]
        story.append(_grid(P, rows, [14 * mm, 44 * mm, 88 * mm, 28 * mm]))
    story.append(Spacer(1, 6))
    story.append(Paragraph(R["rfi"], S["h2"]))
    story.append(Paragraph(R["rfi_abertos"].format(n=dados["rfi_abertos"], a=dados["rfi_atraso"]), S["body"]))
    for r in dados["rfi_lista"][:12]:
        story.append(Paragraph(f"• {escape(str(r['numero']))} — {_p(r['assunto'])}{' · ' + escape(r['prazo']) if r.get('prazo') else ''}", S["body"]))
    if alertas:
        story.append(Spacer(1, 6))
        story.append(Paragraph(R["alertas"], S["h2"]))
        for a in alertas[:15]:
            story.append(Paragraph(f"• <b>{escape(a['severidade_label'])}</b> — {_p(a['texto'])}", S["body"]))
    story.append(Spacer(1, 10))
    story.append(Paragraph(R["fonte"], S["muted"]))
    return _build(pdf, story, branding, P, buf)


def qse_pdf(obra: dict, itens: list[dict], branding: Optional[dict]) -> bytes:
    Q = TX.QSE_PDF
    P, S, buf, pdf, story = _doc(branding)
    story.append(Paragraph(Q["kicker"], S["kicker"]))
    story.append(Paragraph(f"{Q['titulo']} — {escape(obra.get('name') or '')}", S["h1"]))
    story.append(Spacer(1, 6))
    rows = [Q["cabecalho"]]
    for it in itens:
        rows.append([str(it.get("numero")), (it.get("data") or "")[:10], TX.QSE_TIPOS.get(it.get("tipo"), it.get("tipo")),
                     Paragraph(f"<b>{_p(it.get('titulo'))}</b><br/>{_p((it.get('descricao') or '')[:400])}", S["body"]),
                     TX.GRAVIDADE.get(it.get("gravidade"), "—"), TX.QSE_ESTADOS.get(it.get("estado"), it.get("estado"))])
    story.append(_grid(P, rows, [11 * mm, 19 * mm, 30 * mm, 74 * mm, 18 * mm, 22 * mm]))
    com_acoes = [it for it in itens if it.get("acoes")]
    if com_acoes:
        story.append(Spacer(1, 8))
        story.append(Paragraph(Q["acoes"], S["h2"]))
        rows = [[TX.NUM] + Q["acoes_cab"]]
        for it in com_acoes:
            for a in it["acoes"]:
                rows.append([str(it.get("numero")), Paragraph(_p(a.get("o_que")), S["body"]), Paragraph(_p(a.get("quem")), S["body"]),
                             a.get("quando") or "", TX.ACAO_ESTADOS.get(a.get("estado"), a.get("estado"))])
        story.append(_grid(P, rows, [11 * mm, 78 * mm, 40 * mm, 20 * mm, 25 * mm]))
    return _build(pdf, story, branding, P, buf)


def data_url_bytes(s: str) -> Optional[tuple[bytes, str]]:
    if not isinstance(s, str) or "base64," not in s:
        return None
    head, b64 = s.split("base64,", 1)
    try:
        raw = base64.b64decode(b64, validate=False)
    except Exception:  # noqa: BLE001
        return None
    ct = "image/png" if "image/png" in head else "image/jpeg" if ("image/jpeg" in head or "image/jpg" in head) else (
        "image/webp" if "image/webp" in head else None)
    if not ct:
        return None
    sig = {"image/png": b"\x89PNG", "image/jpeg": b"\xff\xd8\xff", "image/webp": b"RIFF"}[ct]
    if not raw.startswith(sig):
        return None
    return raw, ct
