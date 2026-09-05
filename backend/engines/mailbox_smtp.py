"""Envoi d'e-mails via le SMTP de l'entreprise (comme Obat).

Quand une entreprise connecte sa boîte (ex: contact@cmrenov.com via Gmail),
les devis/factures partent réellement depuis sa boîte et Google/serveur
enregistre automatiquement une copie dans le dossier « Envoyés ».

Le mot de passe (mot de passe d'application) est chiffré au repos via Fernet,
la clé étant dérivée de JWT_SECRET.
"""
from __future__ import annotations

import base64
import hashlib
import os
from email.message import EmailMessage

import aiosmtplib
from cryptography.fernet import Fernet

DEFAULT_PORTS = {"ssl": 465, "starttls": 587}


def _fernet() -> Fernet:
    secret = os.environ.get("JWT_SECRET") or "construpilot-dev-secret"
    key = base64.urlsafe_b64encode(hashlib.sha256(secret.encode()).digest())
    return Fernet(key)


def encrypt_secret(plaintext: str) -> str:
    return _fernet().encrypt(plaintext.encode()).decode()


def decrypt_secret(token: str) -> str:
    return _fernet().decrypt(token.encode()).decode()


def _build_message(cfg: dict, to: str, subject: str, html: str,
                   cc: str | None, reply_to: str | None, from_name: str | None,
                   attachments: list[dict] | None) -> EmailMessage:
    msg = EmailMessage()
    sender = cfg["email"]
    display = (from_name or cfg.get("from_name") or "").strip()
    msg["From"] = f"{display} <{sender}>" if display else sender
    msg["To"] = to
    if cc:
        msg["Cc"] = cc
    if reply_to:
        msg["Reply-To"] = reply_to
    msg["Subject"] = subject
    msg.set_content("Votre client de messagerie ne supporte pas le HTML.")
    msg.add_alternative(html, subtype="html")
    for att in attachments or []:
        ctype = att.get("content_type", "application/octet-stream")
        maintype, _, subtype = ctype.partition("/")
        msg.add_attachment(att["content"], maintype=maintype or "application",
                           subtype=subtype or "octet-stream",
                           filename=att["filename"])
    return msg


async def smtp_send(cfg: dict, to: str, subject: str, html: str,
                    cc: str | None = None, reply_to: str | None = None,
                    from_name: str | None = None,
                    attachments: list[dict] | None = None) -> dict:
    """Envoie via le SMTP de l'entreprise. cfg contient un password en clair."""
    msg = _build_message(cfg, to, subject, html, cc, reply_to, from_name, attachments)
    security = cfg.get("security", "ssl")
    host = cfg["host"]
    port = int(cfg.get("port") or DEFAULT_PORTS.get(security, 465))
    recipients = [to] + ([cc] if cc else [])
    await aiosmtplib.send(
        msg,
        hostname=host,
        port=port,
        username=cfg["email"],
        password=cfg["password"],
        use_tls=(security == "ssl"),
        start_tls=(security == "starttls"),
        recipients=recipients,
        timeout=30,
    )
    return {"ok": True, "id": msg.get("Message-Id"), "via": "smtp"}


async def smtp_verify(cfg: dict) -> None:
    """Teste la connexion + l'authentification. Lève une exception si échec."""
    security = cfg.get("security", "ssl")
    host = cfg["host"]
    port = int(cfg.get("port") or DEFAULT_PORTS.get(security, 465))
    client = aiosmtplib.SMTP(hostname=host, port=port,
                             use_tls=(security == "ssl"),
                             start_tls=(security == "starttls"),
                             timeout=20)
    await client.connect()
    try:
        await client.login(cfg["email"], cfg["password"])
    finally:
        try:
            await client.quit()
        except Exception:  # noqa: BLE001
            pass
