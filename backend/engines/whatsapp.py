"""Contactos WhatsApp da empresa — motor puro (sem base de dados nem rede).

Cada empresa cliente do ConstruPilot escolhe quem aparece no botão WhatsApp (o gerente e os colaboradores) e
em que sítios: página pública da empresa, orçamentos enviados, portal da obra e app dos operários.
Nada é publicado sem a empresa o ativar: os números só saem nos sítios marcados, contacto a contacto.

Idêntico no .pt e no .fr: só os textos (WA_TXT) e o indicativo do país mudam.
"""
from __future__ import annotations

import re
import secrets
from typing import Any, Iterable, Optional
from urllib.parse import quote

INDICATIVO = "351"          # Portugal (o .fr usa 33)
LOCAIS = ("pagina", "orcamentos", "portal", "operarios")
MAX_CONTACTOS = 12

WA_TXT = {
    "pagina": "Olá, vi a página da {empresa} no ConstruPilot e gostaria de falar sobre uma obra.",
    "orcamentos": "Olá, tenho uma questão sobre o orçamento {ref} da {empresa}.",
    "portal": "Olá, contacto-vos sobre a obra {ref}.",
    "operarios": "Olá, sou da equipa da obra {ref}.",
    "telefone_invalido": "Número de telefone inválido para «{nome}» (use o formato +351 912 345 678).",
    "gerente": "Gerente",
    "colaborador": "Colaborador",
}


def normalizar_telefone(raw: Any, indicativo: str = INDICATIVO) -> Optional[str]:
    """Devolve o número no formato internacional só com dígitos (ex.: 351912345678), ou None se inválido."""
    s = str(raw or "").strip()
    if not s:
        return None
    s = re.sub(r"[\s().\-/]", "", s)
    if s.startswith("+"):
        d = s[1:]
    elif s.startswith("00"):
        d = s[2:]
    else:
        d = s
        if not d.isdigit():
            return None
        if d.startswith("0") and len(d) == 10:          # França: 06 12 34 56 78
            d = indicativo + d[1:]
        elif len(d) == 9:                                # Portugal: 912 345 678
            d = indicativo + d
    if not d.isdigit() or not 8 <= len(d) <= 15 or d.startswith("0"):
        return None
    return d


def link(numero: str, mensagem: str = "") -> str:
    return f"https://wa.me/{numero}" + (f"?text={quote(mensagem[:500])}" if mensagem else "")


def validar(contactos: Iterable[dict], indicativo: str = INDICATIVO) -> tuple[Optional[str], list[dict]]:
    """Valida e normaliza a lista guardada pela empresa. Devolve (erro, lista)."""
    out, vistos = [], set()
    for c in list(contactos)[:MAX_CONTACTOS]:
        nome = re.sub(r"\s+", " ", str(c.get("nome") or "")).strip()[:80]
        if not nome:
            continue
        num = normalizar_telefone(c.get("telefone"), indicativo)
        if not num:
            return WA_TXT["telefone_invalido"].format(nome=nome), []
        if num in vistos:
            continue
        vistos.add(num)
        cid = str(c.get("id") or "")
        locais = c.get("locais") if isinstance(c.get("locais"), dict) else {}
        out.append({"id": cid if re.fullmatch(r"[A-Za-z0-9_-]{1,40}", cid) else f"wa_{secrets.token_hex(4)}",
                    "nome": nome, "funcao": re.sub(r"\s+", " ", str(c.get("funcao") or "")).strip()[:60],
                    "telefone": "+" + num, "user_id": str(c.get("user_id") or "")[:60] or None,
                    "locais": {k: bool(locais.get(k)) for k in LOCAIS}})
    return None, out


def publicos(cfg: Optional[dict], local: str, empresa: str = "", ref: str = "") -> list[dict]:
    """Contactos a mostrar num sítio, com o link WhatsApp e a mensagem já escrita. Lista vazia se desativado."""
    if not cfg or not cfg.get("ativo") or local not in LOCAIS:
        return []
    msg = WA_TXT[local].format(empresa=empresa or "empresa", ref=ref or "").replace("  ", " ").strip()
    out = []
    for c in cfg.get("contactos") or []:
        if not (c.get("locais") or {}).get(local):
            continue
        num = normalizar_telefone(c.get("telefone"))
        if num:
            out.append({"nome": c.get("nome"), "funcao": c.get("funcao") or "", "link": link(num, msg)})
    return out
