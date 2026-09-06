"""Recibo automático PT-PT enviado após assinatura de orçamento.

Reutiliza a geração de PDF do orçamento assinado (build_document_pdf /
build_quote_pdf) — o PDF do orçamento assinado é o comprovativo de aceitação
(inclui o bloco de assinatura).

Este módulo produz apenas o corpo email PT-PT.
"""
from __future__ import annotations

from datetime import datetime, timezone
from zoneinfo import ZoneInfo


MONTHS_PT = [
    "janeiro", "fevereiro", "março", "abril", "maio", "junho",
    "julho", "agosto", "setembro", "outubro", "novembro", "dezembro",
]


def _eur_pt(v: float) -> str:
    """Formata valor em EUR no formato PT (1.234,56 €)."""
    try:
        s = f"{float(v):,.2f}"
        # US -> PT: 1,234.56 -> 1.234,56
        int_part, dec_part = s.split(".")
        int_part = int_part.replace(",", ".")
        return f"{int_part},{dec_part} €"
    except Exception:
        return f"{v} €"


def _date_pt(iso: str | None) -> str:
    """Devolve data PT tipo '6 de setembro de 2026'. Tenta Europe/Lisbon."""
    if not iso:
        iso = datetime.now(timezone.utc).isoformat()
    try:
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        try:
            dt = dt.astimezone(ZoneInfo("Europe/Lisbon"))
        except Exception:
            pass
        return f"{dt.day} de {MONTHS_PT[dt.month - 1]} de {dt.year}"
    except Exception:
        return iso[:10]


def receipt_subject_pt(quote_number: str | None) -> str:
    n = quote_number or "sem número"
    return f"Recibo de assinatura — Orçamento #{n} — ConstruPilot"


def receipt_email_text_pt(*, client_name: str | None, quote_number: str | None,
                          quote_title: str | None, total_ttc: float,
                          signed_at_iso: str | None) -> str:
    name = (client_name or "").strip() or "Cliente"
    n = quote_number or "sem número"
    title = quote_title or "orçamento"
    return (
        f"Olá {name},\n\n"
        f"Confirmamos a assinatura do orçamento #{n} — {title}.\n\n"
        f"Recibo em anexo (PDF)\n"
        f"Total: {_eur_pt(total_ttc)}\n"
        f"Data de assinatura: {_date_pt(signed_at_iso)}\n\n"
        f"Próximos passos:\n"
        f"1. Guarde este recibo para os seus registos.\n"
        f"2. Contactar-nos-emos em breve para agendar o início da obra.\n\n"
        f"Para questões, responda a este email ou contacte-nos em info@construpilot.pt.\n\n"
        f"Cumprimentos,\n"
        f"Equipa ConstruPilot\n"
        f"https://construpilot.pt\n"
    )


def receipt_email_html_pt(*, client_name: str | None, quote_number: str | None,
                          quote_title: str | None, total_ttc: float,
                          signed_at_iso: str | None) -> str:
    name = (client_name or "").strip() or "Cliente"
    n = quote_number or "sem número"
    title = quote_title or "orçamento"
    total = _eur_pt(total_ttc)
    date = _date_pt(signed_at_iso)
    return f"""<div style="font-family:-apple-system,Segoe UI,Roboto,Arial,sans-serif;max-width:560px;margin:0 auto;color:#0A0D14;padding:20px">
  <div style="text-align:center;padding:8px 0 20px">
    <div style="font-size:26px;font-weight:800;letter-spacing:-0.5px">
      <span style="color:#FF5A00">Constru</span>Pilot</div>
  </div>
  <div style="background:#FFF7F2;border:1px solid #FFE0CF;border-radius:14px;padding:26px 24px">
    <h1 style="font-size:22px;margin:0 0 10px;color:#0A0D14">Olá {name},</h1>
    <p style="font-size:15px;line-height:1.55;color:#334155;margin:0 0 14px">
      Confirmamos a assinatura do orçamento <b>#{n}</b> — {title}.</p>
    <div style="background:#FFFFFF;border:1px solid #FFE0CF;border-radius:10px;padding:14px 18px;margin:14px 0">
      <p style="margin:6px 0;font-size:14px"><span style="color:#64748B">📄 Recibo</span> em anexo (PDF)</p>
      <p style="margin:6px 0;font-size:14px"><span style="color:#64748B">💰 Total:</span> <b>{total}</b></p>
      <p style="margin:6px 0;font-size:14px"><span style="color:#64748B">📅 Data de assinatura:</span> {date}</p>
    </div>
    <p style="font-size:14px;color:#334155;margin:16px 0 6px"><b>Próximos passos:</b></p>
    <ol style="font-size:14px;color:#334155;margin:0 0 10px 20px;padding:0;line-height:1.6">
      <li>Guarde este recibo para os seus registos.</li>
      <li>Contactar-nos-emos em breve para agendar o início da obra.</li>
    </ol>
    <p style="font-size:13px;color:#64748B;margin:14px 0 0">
      Para questões, responda a este email ou contacte-nos em
      <a href="mailto:info@construpilot.pt" style="color:#FF5A00;text-decoration:none">info@construpilot.pt</a>.
    </p>
  </div>
  <p style="font-size:12px;color:#94A3B8;text-align:center;margin:18px 0 4px">
    Cumprimentos, Equipa <span style="color:#FF5A00">Constru</span>Pilot</p>
  <p style="font-size:12px;color:#94A3B8;text-align:center;margin:0">
    <a href="https://construpilot.pt" style="color:#94A3B8;text-decoration:none">construpilot.pt</a>
  </p>
</div>"""


def receipt_filename(quote_number: str | None) -> str:
    n = (quote_number or "").strip().replace("/", "-").replace(" ", "") or "orcamento"
    return f"recibo_orcamento_{n}.pdf"
