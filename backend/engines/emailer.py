"""Envoi d'emails via Resend (async wrapper).

Usage:
    await send_email(to, subject, html)
    await send_email_with_pdf(to, subject, html, pdf_bytes, filename)
"""
import os
import base64
import asyncio
import logging

import resend

logger = logging.getLogger(__name__)


def _configure():
    key = os.environ.get("RESEND_API_KEY")
    if key:
        resend.api_key = key
    return bool(key)


def _from():
    return os.environ.get("SENDER_EMAIL") or "onboarding@resend.dev"


async def send_email(to: str, subject: str, html: str) -> dict:
    if not _configure():
        raise RuntimeError("RESEND_API_KEY manquant")
    params = {"from": _from(), "to": [to], "subject": subject, "html": html}
    try:
        resp = await asyncio.to_thread(resend.Emails.send, params)
        return {"ok": True, "id": resp.get("id")}
    except Exception as e:
        logger.error(f"Email send failed: {e}")
        raise


async def send_email_with_pdf(to: str, subject: str, html: str,
                              pdf_bytes: bytes, filename: str = "devis.pdf") -> dict:
    if not _configure():
        raise RuntimeError("RESEND_API_KEY manquant")
    params = {
        "from": _from(), "to": [to], "subject": subject, "html": html,
        "attachments": [{
            "filename": filename,
            "content": base64.b64encode(pdf_bytes).decode("utf-8"),
            "content_type": "application/pdf",
        }],
    }
    try:
        resp = await asyncio.to_thread(resend.Emails.send, params)
        return {"ok": True, "id": resp.get("id")}
    except Exception as e:
        logger.error(f"Email+PDF send failed: {e}")
        raise


BRAND = "#FF5A00"


def wrap_html(title: str, body: str, cta_url: str | None = None, cta_label: str | None = None) -> str:
    """Template email ConstruPilot — inline CSS, tables, français."""
    cta = ""
    if cta_url and cta_label:
        cta = (f'<tr><td style="padding:24px 0"><a href="{cta_url}" '
               f'style="background:{BRAND};color:#fff;text-decoration:none;padding:12px 20px;'
               f'font-family:Arial,sans-serif;font-size:14px;font-weight:bold;border-radius:4px;'
               f'display:inline-block">{cta_label}</a></td></tr>')
    return f"""<!doctype html>
<html><body style="margin:0;background:#f5f5f7;font-family:Arial,sans-serif;color:#0A0D14">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="padding:32px 0">
<tr><td align="center">
<table role="presentation" width="560" cellpadding="0" cellspacing="0"
       style="background:#fff;border:1px solid #e2e8f0;border-radius:6px;overflow:hidden">
<tr><td style="padding:24px;border-bottom:2px solid {BRAND}">
  <div style="font-size:22px;font-weight:800;letter-spacing:-0.5px">
    ConstruPilot
  </div>
  <div style="color:#64748B;font-size:12px;margin-top:4px">Estimez, Comparez, Construisez.</div>
</td></tr>
<tr><td style="padding:28px">
  <h1 style="font-size:20px;margin:0 0 16px 0">{title}</h1>
  <div style="font-size:14px;line-height:1.55;color:#334155">{body}</div>
  {cta}
</td></tr>
<tr><td style="padding:16px 24px;background:#f8fafc;border-top:1px solid #e2e8f0;
              font-size:11px;color:#64748B">
  Estimation indicative — ne constitue pas un devis contractuel. Vous recevez cet email car vous
  utilisez ConstruPilot.
</td></tr>
</table></td></tr></table></body></html>"""
