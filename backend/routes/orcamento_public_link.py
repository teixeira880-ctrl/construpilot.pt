"""Portal cliente final — ligações públicas de orçamento (Fase D).

Endpoints:
    POST /api/orcamentos/{orcamento_id}/public-link  (JWT, owner-only)
    GET  /api/public/orcamentos/{token}              (sem JWT, rate-limited)
    GET  /api/public/orcamentos/{token}/pdf          (sem JWT, rate-limited)

Fluxo:
    * Pro cria um orçamento via Assistente BTP.
    * Chama o endpoint protegido para gerar um token seguro (32 bytes
      url-safe) com validade `PUBLIC_LINK_TTL_DAYS` (default 60).
    * Opcionalmente fornece `cliente_email` → o backend envia o link
      por Resend (Fase prévia Resend já integrada).
    * Clientes finais abrem o link (sem conta ConstruPilot), veem o
      orçamento formatado e podem transferir o PDF.
    * Canal viral: PDF e página pública têm watermark/CTA
      "Gerado por ConstruPilot.pt".
"""
from __future__ import annotations

import logging
import os
import secrets
from datetime import datetime, timedelta, timezone
from io import BytesIO
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response
from pydantic import BaseModel, EmailStr, Field
from reportlab.lib.colors import HexColor
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import (
    Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle,
)

from core.db import db  # ref importada; propagada por tests via setattr se necessário
from core.rate_limit import limiter
from core.security import current_user

logger = logging.getLogger("orcamento_public_link")

router = APIRouter(tags=["orcamento-public-link"])


# ---------------------------------------------------------------------------
# Configuração
# ---------------------------------------------------------------------------
def _ttl_days() -> int:
    try:
        return max(1, int(os.environ.get("PUBLIC_LINK_TTL_DAYS", "60")))
    except (TypeError, ValueError):
        return 60


def _tz_aware(dt):
    """Mongo devolve datetimes naive — garante UTC-aware para comparação."""
    if isinstance(dt, datetime) and dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def _public_app_url() -> str:
    return (
        os.environ.get("PUBLIC_APP_URL")
        or os.environ.get("FRONTEND_URL")
        or "https://construpilot.pt"
    ).rstrip("/")


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------
class CriarPublicLinkIn(BaseModel):
    cliente_email: EmailStr | None = Field(
        default=None,
        description="Se fornecido, envia a ligação por e-mail via Resend.",
    )
    enviar_email: bool = Field(
        default=True,
        description="Quando False, apenas gera o token (sem envio).",
    )


class CriarPublicLinkOut(BaseModel):
    token: str
    url: str
    expires_at_iso: str
    email_enviado: bool
    email_destinatario: str | None = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
async def _buscar_orcamento(orcamento_id: str, user_id: str) -> dict | None:
    """Procura em `btp_assistant_orcamentos` primeiro (nova fonte),
    depois em `quotes` (fluxo legacy) para retrocompatibilidade."""
    doc = await db.btp_assistant_orcamentos.find_one(
        {"orcamento_id": orcamento_id, "user_id": user_id}, {"_id": 0},
    )
    if doc:
        return {"source": "btp_assistant", **doc}
    legacy = await db.quotes.find_one(
        {"doc_id": orcamento_id, "user_id": user_id}, {"_id": 0},
    )
    if legacy:
        # Normaliza para o mesmo shape
        return {
            "source": "quotes_legacy",
            "orcamento_id": orcamento_id,
            "user_id": user_id,
            "cliente_nome": legacy.get("client_name") or "",
            "titulo": legacy.get("title") or legacy.get("number") or "Orçamento",
            "items": legacy.get("items") or [],
            "iva_pct": (legacy.get("totals") or {}).get("vat_rate") or 23.0,
            "subtotal_eur": (legacy.get("totals") or {}).get("ht") or 0.0,
            "iva_eur": (legacy.get("totals") or {}).get("vat") or 0.0,
            "total_eur": (legacy.get("totals") or {}).get("ttc") or 0.0,
            "created_at_iso": legacy.get("created_at") or "",
        }
    return None


async def _buscar_dados_empresa(user_id: str) -> dict:
    """Devolve branding mínimo do Pro (apenas dados não-PII do cliente final)."""
    u = await db.users.find_one(
        {"user_id": user_id},
        {"_id": 0, "company_name": 1, "company_logo_url": 1, "nif": 1},
    ) or {}
    return {
        "nome": u.get("company_name") or "",
        "logo_url": u.get("company_logo_url") or "",
        "nif": u.get("nif") or "",
    }


def _sanitizar_para_publico(orcamento: dict, empresa: dict) -> dict:
    """Remove PII do owner, mantém dados úteis ao cliente final."""
    return {
        "numero": orcamento.get("orcamento_id") or "",
        "titulo": orcamento.get("titulo") or "Orçamento",
        "cliente_nome": orcamento.get("cliente_nome") or "",
        "items": [
            {
                "descricao": it.get("descricao") or "",
                "qtd": float(it.get("qtd") or 0),
                "unidade": it.get("unidade") or "un",
                "preco_unit_eur": float(it.get("preco_unit_eur") or 0),
                "total_eur": round(
                    float(it.get("qtd") or 0) * float(it.get("preco_unit_eur") or 0),
                    2,
                ),
            }
            for it in (orcamento.get("items") or [])
        ],
        "subtotal_eur": float(orcamento.get("subtotal_eur") or 0),
        "iva_pct": float(orcamento.get("iva_pct") or 23.0),
        "iva_eur": float(orcamento.get("iva_eur") or 0),
        "total_eur": float(orcamento.get("total_eur") or 0),
        "data_iso": orcamento.get("created_at_iso") or "",
        "empresa": {
            "nome": empresa.get("nome") or "",
            "logo_url": empresa.get("logo_url") or "",
        },
    }


# ---------------------------------------------------------------------------
# POST /api/orcamentos/{orcamento_id}/public-link
# ---------------------------------------------------------------------------
@router.post(
    "/orcamentos/{orcamento_id}/public-link",
    response_model=CriarPublicLinkOut,
    summary="Gera uma ligação pública (link mágico) para um orçamento.",
)
async def criar_public_link(
    orcamento_id: str,
    body: CriarPublicLinkIn,
    user=Depends(current_user),
) -> CriarPublicLinkOut:
    user_id = user.get("user_id") or user.get("sub") or ""
    doc = await _buscar_orcamento(orcamento_id, user_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Orçamento não encontrado.")

    token = f"mp_{secrets.token_urlsafe(32)}"
    agora = datetime.now(timezone.utc)
    expira = agora + timedelta(days=_ttl_days())

    cliente_email = body.cliente_email or None
    link_doc = {
        "token": token,
        "orcamento_id": orcamento_id,
        "created_by_user_id": user_id,
        "cliente_email": cliente_email,
        "created_at": agora,
        "expires_at": expira,
        "viewed_count": 0,
        "last_viewed_at": None,
    }
    await db.orcamento_public_links.insert_one(link_doc)

    url = f"{_public_app_url()}/orcamento-publico/{token}"

    # Envio opcional via Resend (fonte-única `info@construpilot.pt`)
    email_enviado = False
    if cliente_email and body.enviar_email:
        try:
            from engines.emailer import send_email  # import tardio

            empresa = await _buscar_dados_empresa(user_id)
            html = _render_email_html(
                cliente_nome=doc.get("cliente_nome") or "",
                titulo=doc.get("titulo") or "Orçamento",
                total_eur=float(doc.get("total_eur") or 0),
                url=url,
                empresa_nome=empresa.get("nome") or "",
            )
            subject = f"O seu orçamento ConstruPilot — {doc.get('titulo') or 'Proposta'}"
            await send_email(
                to=cliente_email, subject=subject, html=html,
                from_name=empresa.get("nome") or None,
                campaign_id="orcamento_public_link",
            )
            email_enviado = True
        except Exception as e:  # noqa: BLE001
            logger.warning("falha ao enviar e-mail do link público: %s", e)

    return CriarPublicLinkOut(
        token=token,
        url=url,
        expires_at_iso=expira.isoformat(),
        email_enviado=email_enviado,
        email_destinatario=cliente_email if email_enviado else None,
    )


# ---------------------------------------------------------------------------
# GET /api/public/orcamentos/{token}  — SEM JWT
# ---------------------------------------------------------------------------
@router.get(
    "/public/orcamentos/{token}",
    summary="Dados sanitizados de um orçamento via link mágico (sem JWT).",
)
@limiter.limit("20/minute")
async def consultar_orcamento_publico(request: Request, token: str) -> dict[str, Any]:
    link = await db.orcamento_public_links.find_one({"token": token}, {"_id": 0})
    if not link:
        raise HTTPException(status_code=404, detail="Ligação inválida.")
    expires_at = _tz_aware(link.get("expires_at"))
    if isinstance(expires_at, datetime) and expires_at < datetime.now(timezone.utc):
        raise HTTPException(status_code=410, detail="Ligação expirada.")

    orc = await _buscar_orcamento(link["orcamento_id"], link["created_by_user_id"])
    if not orc:
        raise HTTPException(status_code=404, detail="Orçamento não disponível.")

    empresa = await _buscar_dados_empresa(link["created_by_user_id"])
    out = _sanitizar_para_publico(orc, empresa)

    # Tracking de abertura (não bloqueante)
    try:
        await db.orcamento_public_links.update_one(
            {"token": token},
            {
                "$inc": {"viewed_count": 1},
                "$set": {"last_viewed_at": datetime.now(timezone.utc)},
            },
        )
    except Exception:  # noqa: BLE001
        logger.exception("tracking de abertura falhou (não bloqueia a resposta)")

    out["expires_at_iso"] = (
        expires_at.isoformat() if isinstance(expires_at, datetime) else ""
    )
    return out


# ---------------------------------------------------------------------------
# GET /api/public/orcamentos/{token}/pdf  — SEM JWT
# ---------------------------------------------------------------------------
@router.get(
    "/public/orcamentos/{token}/pdf",
    summary="PDF descarregável do orçamento (sem JWT, com watermark viral).",
)
@limiter.limit("20/minute")
async def descarregar_pdf_publico(request: Request, token: str) -> Response:
    link = await db.orcamento_public_links.find_one({"token": token}, {"_id": 0})
    if not link:
        raise HTTPException(status_code=404, detail="Ligação inválida.")
    expires_at = _tz_aware(link.get("expires_at"))
    if isinstance(expires_at, datetime) and expires_at < datetime.now(timezone.utc):
        raise HTTPException(status_code=410, detail="Ligação expirada.")

    orc = await _buscar_orcamento(link["orcamento_id"], link["created_by_user_id"])
    if not orc:
        raise HTTPException(status_code=404, detail="Orçamento não disponível.")

    empresa = await _buscar_dados_empresa(link["created_by_user_id"])
    dados = _sanitizar_para_publico(orc, empresa)
    pdf_bytes = _gerar_pdf(dados)

    nome = (dados["numero"] or "orcamento").replace("/", "_")
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'inline; filename="{nome}.pdf"',
            "Cache-Control": "private, max-age=60",
        },
    )


# ---------------------------------------------------------------------------
# Geração PDF (reportlab) + watermark/CTA viral
# ---------------------------------------------------------------------------
def _render_email_html(
    *, cliente_nome: str, titulo: str, total_eur: float, url: str,
    empresa_nome: str,
) -> str:
    """E-mail HTML simples em PT-PT com CTA."""
    nome_html = cliente_nome or "Caro Cliente"
    emp = empresa_nome or "o seu profissional"
    return f"""
    <div style="font-family:Arial,Helvetica,sans-serif;max-width:560px;margin:0 auto;color:#111">
      <h2 style="color:#D9541E;margin-bottom:0.4em">Olá {nome_html},</h2>
      <p>Enviamos-lhe o orçamento <strong>{titulo}</strong> preparado por {emp}.</p>
      <p style="font-size:20px;margin:1em 0"><strong>Total: {total_eur:,.2f} €</strong></p>
      <p>
        <a href="{url}" style="background:#D9541E;color:#fff;padding:12px 24px;
                               text-decoration:none;border-radius:4px;font-weight:bold;
                               display:inline-block">
          Ver o orçamento
        </a>
      </p>
      <p style="color:#555;font-size:12px">
        Esta ligação é pessoal e expira dentro de {_ttl_days()} dias.
      </p>
      <hr style="border:none;border-top:1px solid #eee;margin:2em 0" />
      <p style="color:#999;font-size:11px">
        Orçamento gerado com <strong>ConstruPilot</strong> — IA para orçamentos de obras.
        <a href="{_public_app_url()}" style="color:#D9541E">Experimente grátis →</a>
      </p>
    </div>
    """.strip()


def _gerar_pdf(dados: dict) -> bytes:
    """Gera PDF ReportLab com cabeçalho, tabela de items e watermark viral."""
    buf = BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        leftMargin=2 * cm, rightMargin=2 * cm,
        topMargin=1.6 * cm, bottomMargin=2.4 * cm,
    )
    styles = getSampleStyleSheet()
    cor_primario = HexColor("#D9541E")
    story = []

    # Cabeçalho
    story.append(Paragraph(
        f"<para align='right'><font size='9' color='#666'>"
        f"Ref · <b>{dados['numero']}</b></font></para>",
        styles["Normal"],
    ))
    story.append(Spacer(1, 4))
    story.append(Paragraph(
        f"<para><font size='18' color='#D9541E'><b>{dados['titulo']}</b></font></para>",
        styles["Title"],
    ))
    story.append(Spacer(1, 10))
    cliente_html = (
        f"<b>Cliente:</b> {dados['cliente_nome'] or '—'}<br/>"
        f"<b>Empresa:</b> {dados['empresa']['nome'] or 'ConstruPilot'}"
    )
    story.append(Paragraph(cliente_html, styles["Normal"]))
    story.append(Spacer(1, 14))

    # Tabela de items
    rows = [["Descrição", "Qtd", "Un.", "Preço unit.", "Total"]]
    for it in dados["items"]:
        rows.append([
            Paragraph(it["descricao"] or "—", styles["BodyText"]),
            _num(it["qtd"]),
            it["unidade"] or "un",
            _eur(it["preco_unit_eur"]),
            _eur(it["total_eur"]),
        ])
    tabela = Table(
        rows,
        colWidths=[7.5 * cm, 1.8 * cm, 1.6 * cm, 2.8 * cm, 2.8 * cm],
    )
    tabela.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), cor_primario),
        ("TEXTCOLOR", (0, 0), (-1, 0), HexColor("#FFFFFF")),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, 0), 9),
        ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
        ("ALIGN", (0, 0), (0, 0), "LEFT"),
        ("GRID", (0, 0), (-1, -1), 0.3, HexColor("#CCCCCC")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [HexColor("#FFFFFF"), HexColor("#F7F7F7")]),
        ("FONTSIZE", (0, 1), (-1, -1), 9),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]))
    story.append(tabela)
    story.append(Spacer(1, 14))

    # Totais
    totais = [
        ["Subtotal", _eur(dados["subtotal_eur"])],
        [f"IVA ({dados['iva_pct']:.0f}%)", _eur(dados["iva_eur"])],
        ["Total c/ IVA", _eur(dados["total_eur"])],
    ]
    tbl_tot = Table(totais, colWidths=[11 * cm, 5.5 * cm], hAlign="RIGHT")
    tbl_tot.setStyle(TableStyle([
        ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
        ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
        ("FONTSIZE", (0, -1), (-1, -1), 11),
        ("TEXTCOLOR", (0, -1), (-1, -1), cor_primario),
        ("LINEABOVE", (0, -1), (-1, -1), 1, cor_primario),
        ("TOPPADDING", (0, -1), (-1, -1), 6),
        ("FONTSIZE", (0, 0), (-1, -2), 9),
    ]))
    story.append(tbl_tot)
    story.append(Spacer(1, 20))

    # CTA viral
    story.append(Paragraph(
        "<para align='center'><font size='8' color='#999'>"
        "Orçamento gerado com <b>ConstruPilot.pt</b> — IA para orçamentos de obras · "
        f"<a href='{_public_app_url()}' color='#D9541E'>Experimente grátis</a>"
        "</font></para>",
        styles["Normal"],
    ))

    # Watermark em cada página (via onPage)
    def _watermark(canv, _doc):
        canv.saveState()
        canv.setFont("Helvetica", 7)
        canv.setFillColor(HexColor("#BBBBBB"))
        canv.drawCentredString(
            A4[0] / 2, 1.1 * cm,
            "Gerado por ConstruPilot.pt",
        )
        canv.restoreState()

    doc.build(story, onFirstPage=_watermark, onLaterPages=_watermark)
    return buf.getvalue()


def _eur(v: float) -> str:
    try:
        return f"{float(v):,.2f} €".replace(",", " ").replace(".", ",").replace(" ", ".")
    except (TypeError, ValueError):
        return "—"


def _num(v: float) -> str:
    try:
        n = float(v)
        if abs(n - int(n)) < 1e-9:
            return str(int(n))
        return f"{n:.2f}".replace(".", ",")
    except (TypeError, ValueError):
        return "—"
