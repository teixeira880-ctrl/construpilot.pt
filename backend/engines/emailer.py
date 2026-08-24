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


def _from(from_name: str | None = None):
    addr = os.environ.get("SENDER_EMAIL") or "onboarding@resend.dev"
    if from_name:
        clean = from_name.replace('"', "").replace("<", "").replace(">", "").strip()[:80]
        if clean:
            return f"{clean} <{addr}>"
    return addr


async def send_email(to: str, subject: str, html: str,
                     reply_to: str | None = None, from_name: str | None = None) -> dict:
    if not _configure():
        raise RuntimeError("RESEND_API_KEY manquant")
    params = {"from": _from(from_name), "to": [to], "subject": subject, "html": html}
    if reply_to:
        params["reply_to"] = reply_to
    try:
        resp = await asyncio.to_thread(resend.Emails.send, params)
        return {"ok": True, "id": resp.get("id")}
    except Exception as e:
        logger.error(f"Email send failed: {e}")
        raise


async def send_email_with_pdf(to: str, subject: str, html: str,
                              pdf_bytes: bytes, filename: str = "devis.pdf",
                              cc: str | None = None,
                              extra_attachments: list[dict] | None = None,
                              reply_to: str | None = None,
                              from_name: str | None = None) -> dict:
    """Envoie un email avec un PDF principal + éventuellement d'autres pièces jointes.

    extra_attachments : liste de dicts {filename, content (bytes)}.
    """
    if not _configure():
        raise RuntimeError("RESEND_API_KEY manquant")
    attachments = [{
        "filename": filename,
        "content": base64.b64encode(pdf_bytes).decode("utf-8"),
        "content_type": "application/pdf",
    }]
    for att in extra_attachments or []:
        attachments.append({
            "filename": att["filename"],
            "content": base64.b64encode(att["content"]).decode("utf-8"),
            "content_type": att.get("content_type", "application/pdf"),
        })
    params = {"from": _from(from_name), "to": [to], "subject": subject, "html": html,
              "attachments": attachments}
    if cc:
        params["cc"] = [cc]
    if reply_to:
        params["reply_to"] = reply_to
    try:
        resp = await asyncio.to_thread(resend.Emails.send, params)
        return {"ok": True, "id": resp.get("id")}
    except Exception as e:
        logger.error(f"Email+PDF send failed: {e}")
        raise


BRAND = "#FF5A00"
COMPANY_NAME = "ConstruPilot"
COMPANY_ADDRESS = "ConstruPilot · France"  # override via env in prod
COMPANY_WEBSITE = "https://construpilot.fr"


def _footer(unsubscribe_url: str | None = None) -> str:
    """Pied de mail pro : logo, adresse postale, liens légaux, désinscription."""
    company_addr = os.environ.get("COMPANY_POSTAL_ADDRESS") or COMPANY_ADDRESS
    unsub_row = ""
    if unsubscribe_url:
        unsub_row = (
            f'<tr><td style="padding:8px 24px 20px;background:#f8fafc;text-align:center">'
            f'<a href="{unsubscribe_url}" style="color:#94A3B8;font-size:11px;'
            f'text-decoration:underline">Se désinscrire des emails marketing</a>'
            f'</td></tr>'
        )
    # SVG logo inline (small brand mark)
    logo_svg = (
        '<div style="display:inline-block;vertical-align:middle;margin-right:8px;'
        'width:24px;height:24px;background:' + BRAND + ';border-radius:4px;'
        'color:#fff;font-weight:800;font-size:14px;line-height:24px;text-align:center;'
        'font-family:Arial,sans-serif">C</div>'
    )
    return (
        '<tr><td style="padding:20px 24px 12px;background:#f8fafc;'
        'border-top:1px solid #e2e8f0">'
        + logo_svg +
        f'<span style="font-size:13px;font-weight:700;color:#334155;vertical-align:middle">'
        f'{COMPANY_NAME}</span>'
        '<div style="font-size:11px;color:#64748B;margin-top:8px;line-height:1.5">'
        f'{company_addr}<br/>'
        f'<a href="{COMPANY_WEBSITE}" style="color:#64748B;text-decoration:none">'
        f'{COMPANY_WEBSITE.replace("https://","")}</a> · '
        '<a href="' + COMPANY_WEBSITE + '/mentions-legales" '
        'style="color:#64748B;text-decoration:none">Mentions légales</a> · '
        '<a href="' + COMPANY_WEBSITE + '/confidentialite" '
        'style="color:#64748B;text-decoration:none">Confidentialité</a>'
        '</div>'
        '<div style="font-size:11px;color:#94A3B8;margin-top:8px">'
        'Estimation indicative — ne constitue pas un devis contractuel. '
        'Vous recevez cet email car vous utilisez ConstruPilot.'
        '</div>'
        '</td></tr>' + unsub_row
    )


def wrap_html(title: str, body: str, cta_url: str | None = None, cta_label: str | None = None,
              unsubscribe_url: str | None = None) -> str:
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
{_footer(unsubscribe_url)}
</table></td></tr></table></body></html>"""



def wrap_company_html(title: str, body: str, *, company_name: str = "",
                      logo_b64: str | None = None, contact_line: str | None = None,
                      siret: str | None = None, vat: str | None = None,
                      company_email: str | None = None, verified: bool = False,
                      verify_url: str | None = None) -> str:
    """Habillage e-mail aux coordonnées de l'entreprise (logo + nom + contact).

    Utilisé pour les e-mails clients (devis/factures) afin d'afficher l'identité
    de l'entreprise émettrice et non celle de ConstruPilot.
    """
    if logo_b64:
        src = logo_b64 if logo_b64.startswith("data:") else f"data:image/png;base64,{logo_b64}"
        header = (f'<img src="{src}" alt="{company_name}" '
                  f'style="max-height:76px;max-width:260px;display:block;margin:0 auto"/>')
    else:
        header = (f'<div style="font-size:24px;font-weight:800;letter-spacing:-0.5px;'
                  f'text-align:center;color:#0A0D14">{company_name or "Devis"}</div>')

    badge = ""
    if verified:
        chip = ('<span style="display:inline-block;background:#E8F3ED;color:#3F7D54;'
                'font-size:12px;font-weight:700;padding:5px 12px;border-radius:999px;'
                'border:1px solid #C4E1D0">&#10004; Pro vérifié par ConstruPilot</span>')
        if verify_url:
            chip = (f'<a href="{verify_url}" style="text-decoration:none" '
                    f'target="_blank" rel="noopener">{chip}</a>')
        badge = f'<div style="text-align:center;margin-top:12px">{chip}</div>'

    coords = []
    if contact_line:
        coords.append(contact_line)
    ids = " · ".join([x for x in [f"SIRET {siret}" if siret else "",
                                   f"TVA {vat}" if vat else ""] if x])
    if ids:
        coords.append(ids)
    if company_email:
        coords.append(f'<a href="mailto:{company_email}" '
                      f'style="color:#64748B;text-decoration:none">{company_email}</a>')
    footer_inner = "<br/>".join(coords) if coords else ""
    footer = ""
    if footer_inner or company_name:
        footer = (
            '<tr><td style="padding:18px 24px 22px;background:#f8fafc;'
            'border-top:1px solid #e2e8f0;text-align:center">'
            f'<div style="font-size:13px;font-weight:700;color:#334155">{company_name}</div>'
            f'<div style="font-size:11px;color:#64748B;margin-top:6px;line-height:1.6">'
            f'{footer_inner}</div></td></tr>')

    return f"""<!doctype html>
<html><body style="margin:0;background:#f5f5f7;font-family:Arial,sans-serif;color:#0A0D14">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="padding:32px 0">
<tr><td align="center">
<table role="presentation" width="560" cellpadding="0" cellspacing="0"
       style="background:#fff;border:1px solid #e2e8f0;border-radius:6px;overflow:hidden">
<tr><td style="padding:24px;background:#f8fafc;border-bottom:2px solid {BRAND}">
  {header}
  {badge}
</td></tr>
<tr><td style="padding:28px">
  <div style="font-size:15px;line-height:1.7;color:#1e293b">{body}</div>
</td></tr>
{footer}
</table></td></tr></table></body></html>"""
