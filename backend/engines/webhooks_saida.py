"""Webhooks de saída — avisa o ERP, a contabilidade ou outra ferramenta da empresa quando algo acontece na obra.

Segurança:
  * só https, porta 443 ou outra explícita, nunca para endereços privados, locais ou de metadados (anti-SSRF);
    a resolução DNS é verificada no momento do envio (um nome público que passe a apontar para a rede
    interna é recusado);
  * cada envio é assinado: cabeçalho X-ConstruPilot-Signature = sha256=HMAC(segredo, corpo);
  * sem redirecionamentos, tempo máximo de 8 s, nunca bloqueia o pedido do utilizador (tarefa em segundo plano).
"""
from __future__ import annotations

import asyncio
import hashlib
import hmac
import ipaddress
import json
import logging
import secrets
import socket
from datetime import datetime, timezone
from typing import Optional
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

EVENTOS = (
    "diario.assinado", "qse.criado", "qse.fechado", "rfi.criado", "rfi.respondido",
    "stock.rececao", "alerta.critico",
)
TIMEOUT_S = 8.0
_TAREFAS: set = set()  # referências às tarefas em curso (evita que sejam recolhidas antes do fim)


def novo_segredo() -> str:
    return "whsec_" + secrets.token_hex(24)


def _ip_publico(ip: str) -> bool:
    try:
        a = ipaddress.ip_address(ip)
    except ValueError:
        return False
    return not (a.is_private or a.is_loopback or a.is_link_local or a.is_multicast or a.is_reserved
                or a.is_unspecified or (a.version == 6 and a.ipv4_mapped is not None and not _ip_publico(str(a.ipv4_mapped))))


def url_valida(url: str) -> bool:
    """Validação sintática (sem DNS): https, anfitrião com ponto, sem credenciais, sem IP privado literal."""
    try:
        u = urlparse(url or "")
    except ValueError:
        return False
    if u.scheme != "https" or not u.hostname or u.username or u.password or len(url) > 500:
        return False
    host = u.hostname.lower()
    if host in ("localhost",) or host.endswith((".local", ".internal", ".localhost")):
        return False
    try:
        ipaddress.ip_address(host)
        return _ip_publico(host)
    except ValueError:
        return "." in host


async def _resolve_publico(host: str, port: int) -> bool:
    try:
        infos = await asyncio.get_running_loop().getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except OSError:
        return False
    ips = {i[4][0] for i in infos}
    return bool(ips) and all(_ip_publico(ip) for ip in ips)


def assinatura(segredo: str, corpo: bytes) -> str:
    return "sha256=" + hmac.new(segredo.encode(), corpo, hashlib.sha256).hexdigest()


async def enviar(hook: dict, evento: str, dados: dict, *, client=None) -> dict:
    """Envia um evento a um webhook. Devolve o resultado (nunca levanta exceção)."""
    corpo = json.dumps({"evento": evento, "enviado_em": datetime.now(timezone.utc).isoformat(), "dados": dados},
                       ensure_ascii=False, default=str).encode()
    res = {"evento": evento, "url": hook.get("url"), "ok": False, "status": None, "erro": None,
           "at": datetime.now(timezone.utc).isoformat()}
    url = hook.get("url") or ""
    if not url_valida(url):
        res["erro"] = "url_invalida"
        return res
    u = urlparse(url)
    if not await _resolve_publico(u.hostname, u.port or 443):
        res["erro"] = "destino_nao_publico"
        return res
    headers = {"Content-Type": "application/json", "User-Agent": "ConstruPilot-Webhooks/1.0",
               "X-ConstruPilot-Event": evento, "X-ConstruPilot-Signature": assinatura(hook.get("segredo") or "", corpo)}
    try:
        import httpx
        own = client is None
        client = client or httpx.AsyncClient(timeout=TIMEOUT_S, follow_redirects=False)
        try:
            r = await client.post(url, content=corpo, headers=headers)
        finally:
            if own:
                await client.aclose()
        res["status"] = r.status_code
        res["ok"] = 200 <= r.status_code < 300
    except Exception as e:  # noqa: BLE001
        res["erro"] = type(e).__name__
    return res


async def disparar(db, owner_user_id: str, evento: str, dados: dict) -> None:
    """Procura os webhooks da empresa subscritos a este evento e envia em segundo plano."""
    if evento not in EVENTOS or not owner_user_id:
        return
    try:
        hooks = await db.webhooks_saida.find({"user_id": owner_user_id, "ativo": True, "eventos": evento},
                                             {"_id": 0}).to_list(5)
    except Exception as e:  # noqa: BLE001
        logger.info("webhooks: leitura falhou: %s", e)
        return
    for h in hooks:
        async def _run(h=h):
            res = await enviar(h, evento, dados)
            try:
                await db.webhooks_saida.update_one({"hook_id": h["hook_id"]},
                                                   {"$set": {"ultimo_envio": res}, "$inc": {"envios": 1, "falhas": 0 if res["ok"] else 1}})
            except Exception:  # noqa: BLE001
                pass
        t = asyncio.create_task(_run())
        _TAREFAS.add(t)
        t.add_done_callback(_TAREFAS.discard)


def publico(h: dict, mostrar_segredo: bool = False) -> dict:
    out = {k: v for k, v in h.items() if k not in ("_id", "segredo")}
    if mostrar_segredo:
        out["segredo"] = h.get("segredo")
    else:
        s = h.get("segredo") or ""
        out["segredo_fim"] = s[-4:]
    return out


def evento_valido(e: Optional[str]) -> bool:
    return e in EVENTOS
