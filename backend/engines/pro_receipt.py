"""Reçu d'abonnement Pro (PDF) + e-mail de bienvenue après paiement."""
from __future__ import annotations

from datetime import datetime, timezone
from io import BytesIO

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import (Paragraph, SimpleDocTemplate, Spacer, Table,
                                TableStyle)

BRAND = colors.HexColor("#FF5A00")
INK = colors.HexColor("#0A0D14")
MUTED = colors.HexColor("#64748B")


def _eur(v: float) -> str:
    return f"{v:,.2f} €".replace(",", " ").replace(".", ",").replace(" ", "\u202f")


def build_pro_receipt_pdf(*, receipt_no: str, plan_name: str, interval: str,
                          amount_ttc: float, customer_name: str,
                          customer_email: str, paid_at: str,
                          stripe_ref: str | None = None) -> bytes:
    buf = BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, topMargin=22 * mm,
                            leftMargin=20 * mm, rightMargin=20 * mm, bottomMargin=18 * mm)
    h1 = ParagraphStyle("h1", fontName="Helvetica-Bold", fontSize=22, textColor=INK, leading=26)
    small = ParagraphStyle("small", fontName="Helvetica", fontSize=9, textColor=MUTED, leading=13)
    body = ParagraphStyle("body", fontName="Helvetica", fontSize=10.5, textColor=INK, leading=15)
    label = ParagraphStyle("label", fontName="Helvetica-Bold", fontSize=9, textColor=MUTED, leading=12)
    el = []
    el.append(Paragraph('<font color="#FF5A00">Constru</font>Pilot', h1))
    el.append(Paragraph("Recibo de subscrição", ParagraphStyle("sub", parent=body, fontSize=13, textColor=BRAND, spaceBefore=2)))
    el.append(Spacer(1, 10))
    el.append(Paragraph(f'Recibo n.º <b>{receipt_no}</b> · emitido em {paid_at}', small))
    el.append(Spacer(1, 16))

    el.append(Paragraph("FATURADO A", label))
    el.append(Paragraph(f"{customer_name or customer_email}<br/>{customer_email}", body))
    el.append(Spacer(1, 16))

    per = {"month": "mensuel", "year": "annuel"}.get(interval, "")
    rows = [
        [Paragraph("<b>Prestação</b>", body), Paragraph("<b>Montante</b>", body)],
        [Paragraph(f'Subscrição {plan_name} ({per})', body), Paragraph(_eur(amount_ttc), body)],
    ]
    t = Table(rows, colWidths=[110 * mm, 60 * mm])
    t.setStyle(TableStyle([
        ("LINEBELOW", (0, 0), (-1, 0), 0.8, INK),
        ("LINEBELOW", (0, -1), (-1, -1), 0.4, colors.HexColor("#E2E8F0")),
        ("ALIGN", (1, 0), (1, -1), "RIGHT"),
        ("TOPPADDING", (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
    ]))
    el.append(t)
    el.append(Spacer(1, 8))
    tot = Table([[Paragraph("<b>Total pago</b>", body), Paragraph(f"<b>{_eur(amount_ttc)}</b>", body)]],
                colWidths=[110 * mm, 60 * mm])
    tot.setStyle(TableStyle([("ALIGN", (1, 0), (1, 0), "RIGHT"),
                             ("TEXTCOLOR", (0, 0), (-1, -1), BRAND)]))
    el.append(tot)
    el.append(Spacer(1, 20))

    if stripe_ref:
        el.append(Paragraph(f'Referência de pagamento: {stripe_ref}', small))
    el.append(Paragraph("Pagamento processado de forma segura pela Stripe. IVA incluído à taxa legal em vigor (ou isenção nos termos do art. 53.º do CIVA, se aplicável).", small))
    el.append(Spacer(1, 6))
    el.append(Paragraph("Obrigado pela sua confiança — a equipa ConstruPilot.", small))
    doc.build(el)
    return buf.getvalue()


def welcome_email_html(*, customer_name: str, plan_name: str, amount_ttc: float,
                       dashboard_url: str) -> str:
    name = (customer_name or "").split(" ")[0] or "Olá"
    amt = _eur(amount_ttc)
    return f'\n<div style="font-family:-apple-system,Segoe UI,Roboto,Arial,sans-serif;max-width:560px;margin:0 auto;color:#0A0D14">\n  <div style="text-align:center;padding:24px 0">\n    <div style="font-size:26px;font-weight:800;letter-spacing:-0.5px">\n      <span style="color:#FF5A00">Constru</span>Pilot</div>\n  </div>\n  <div style="background:#FFF7F2;border:1px solid #FFE0CF;border-radius:14px;padding:28px 26px">\n    <h1 style="font-size:22px;margin:0 0 6px">Bem-vindo ao Pro, {name} 🎉</h1>\n    <p style="font-size:15px;line-height:1.55;color:#334155;margin:0 0 16px">\n      A sua subscrição <b>{plan_name}</b> está ativa. Tem agora acesso a\n      todas as funções profissionais: orçamentos &amp; faturas, obras,\n      medições IA, faturação eletrónica e muito mais.</p>\n    <a href="{dashboard_url}" style="display:inline-block;background:#FF5A00;color:#fff;\n       text-decoration:none;font-weight:700;padding:12px 22px;border-radius:10px">\n       Aceder ao meu painel</a>\n    <p style="font-size:13px;color:#64748B;margin:18px 0 0">\n      Montante pago: <b>{amt}</b>. O seu recibo segue em anexo.</p>\n  </div>\n  <p style="font-size:12px;color:#94A3B8;text-align:center;margin:18px 0">\n    ConstruPilot · O copiloto dos profissionais da construção</p>\n</div>'


def receipt_no_for(user_id: str) -> str:
    ts = datetime.now(timezone.utc).strftime("%Y%m%d")
    return f"CP-PRO-{ts}-{user_id[-6:].upper()}"
