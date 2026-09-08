"""Gera o pitch deck PT-PT (8 slides, 16:9) em /app/frontend/public/pitch-deck.pdf.

Execução:
    python /app/backend/scripts/generate_pitch_deck.py
"""
from pathlib import Path
from reportlab.lib.colors import HexColor, white, black
from reportlab.lib.pagesizes import landscape
from reportlab.pdfgen import canvas
from reportlab.lib.units import mm

# 16:9 slide — 297 mm × 167 mm
PAGE_W, PAGE_H = 297 * mm, 167 * mm
PRIMARY   = HexColor("#10b981")   # verde ConstruPilot
DARK      = HexColor("#0f172a")   # slate-900
MUTED     = HexColor("#64748b")   # slate-500
LIGHT_BG  = HexColor("#f8fafc")   # slate-50
ACCENT    = HexColor("#f97316")   # laranja de destaque

OUT = Path("/app/frontend/public/pitch-deck.pdf")


def _footer(c, page_no, total):
    """Rodapé discreto com nº de slide + marca."""
    c.setFillColor(MUTED)
    c.setFont("Helvetica", 8)
    c.drawString(15 * mm, 8 * mm, "ConstruPilot · construpilot.pt")
    c.drawRightString(PAGE_W - 15 * mm, 8 * mm, f"{page_no} / {total}")


def _top_band(c, title, kicker=None):
    """Faixa colorida no topo + título grande alinhado à esquerda."""
    c.setFillColor(PRIMARY)
    c.rect(0, PAGE_H - 6 * mm, PAGE_W, 6 * mm, fill=1, stroke=0)
    if kicker:
        c.setFillColor(PRIMARY)
        c.setFont("Helvetica-Bold", 9)
        c.drawString(15 * mm, PAGE_H - 18 * mm, kicker.upper())
    c.setFillColor(DARK)
    c.setFont("Helvetica-Bold", 26)
    c.drawString(15 * mm, PAGE_H - 30 * mm, title)


def _bullets(c, x, y, items, size=13, line_h=8):
    """Lista de bullets com marcador verde quadrado."""
    for text in items:
        c.setFillColor(PRIMARY)
        c.rect(x, y - 3, 3, 3, fill=1, stroke=0)
        c.setFillColor(DARK)
        c.setFont("Helvetica", size)
        c.drawString(x + 7, y - 2, text)
        y -= line_h * mm


def _kpi_box(c, x, y, w, h, value, label):
    """Caixa KPI (valor grande + rótulo)."""
    c.setFillColor(LIGHT_BG)
    c.rect(x, y, w, h, fill=1, stroke=0)
    c.setStrokeColor(PRIMARY)
    c.setLineWidth(0.5)
    c.rect(x, y, w, h, fill=0, stroke=1)
    c.setFillColor(PRIMARY)
    c.setFont("Helvetica-Bold", 24)
    c.drawCentredString(x + w / 2, y + h - 14 * mm, value)
    c.setFillColor(MUTED)
    c.setFont("Helvetica", 9)
    c.drawCentredString(x + w / 2, y + 6 * mm, label)


# ==========================================================================
# SLIDES
# ==========================================================================
def slide_1_capa(c):
    """Capa — fundo escuro, logo textual + tagline."""
    c.setFillColor(DARK)
    c.rect(0, 0, PAGE_W, PAGE_H, fill=1, stroke=0)
    # Barra verde vertical à esquerda
    c.setFillColor(PRIMARY)
    c.rect(0, 0, 8 * mm, PAGE_H, fill=1, stroke=0)
    # Wordmark
    c.setFillColor(white)
    c.setFont("Helvetica-Bold", 48)
    c.drawString(25 * mm, PAGE_H - 65 * mm, "ConstruPilot")
    c.setFillColor(PRIMARY)
    c.setFont("Helvetica-Bold", 20)
    c.drawString(25 * mm, PAGE_H - 82 * mm, "Da planta ao orçamento em minutos")
    # Descrição
    c.setFillColor(HexColor("#cbd5e1"))
    c.setFont("Helvetica", 13)
    c.drawString(
        25 * mm, PAGE_H - 100 * mm,
        "Plataforma SaaS com IA para medição 2D/3D, orçamentação e CRM"
    )
    c.drawString(25 * mm, PAGE_H - 108 * mm, "dedicada ao setor da construção em Portugal.")
    # Rodapé escuro
    c.setFillColor(HexColor("#94a3b8"))
    c.setFont("Helvetica", 10)
    c.drawString(25 * mm, 18 * mm, "construpilot.pt")
    c.drawString(25 * mm, 12 * mm, "Pitch Deck · 2026")
    c.setFillColor(PRIMARY)
    c.setFont("Helvetica-Bold", 10)
    c.drawRightString(PAGE_W - 15 * mm, 12 * mm, "CONFIDENCIAL — Investidores")


def slide_2_problema(c):
    _top_band(c, "O problema", "Setor fragmentado")
    _bullets(c, 20 * mm, PAGE_H - 45 * mm, [
        "Medições manuais em plantas físicas — lentas e sujeitas a erro humano",
        "Orçamentos imprecisos que geram estouros de custo e disputas com clientes",
        "Catálogos de preços desatualizados espalhados por Excel, PDFs e emails",
        "Ferramentas genéricas (Word, Excel) sem lógica específica de construção civil",
        "PMEs sem CRM: propostas perdidas, sem seguimento pós-envio",
    ], size=13, line_h=9)
    # Caixa de destaque
    c.setFillColor(HexColor("#fef2f2"))
    c.rect(20 * mm, 18 * mm, PAGE_W - 40 * mm, 22 * mm, fill=1, stroke=0)
    c.setFillColor(HexColor("#b91c1c"))
    c.setFont("Helvetica-Bold", 11)
    c.drawString(25 * mm, 30 * mm, "Impacto:")
    c.setFillColor(DARK)
    c.setFont("Helvetica", 11)
    c.drawString(
        45 * mm, 30 * mm,
        "cada orçamento demora 4–8 h a preparar. Empresas de 5 pessoas perdem "
    )
    c.drawString(
        25 * mm, 22 * mm,
        "1 dia útil/semana só a fazer orçamentos e a atualizar preços."
    )


def slide_3_solucao(c):
    _top_band(c, "A solução", "Plataforma all-in-one")
    _bullets(c, 20 * mm, PAGE_H - 45 * mm, [
        "Medição automática de plantas 2D/3D por IA (DWG, DXF, PDF, JPG)",
        "Estimativa instantânea de betão, aço, vãos e mão de obra",
        "Biblioteca partilhada de trabalhos e materiais com preços de mercado",
        "Orçamento pronto a enviar em minutos, com assinatura eletrónica",
        "CRM integrado: clientes, obras, faturas e cobrança automática",
    ], size=13, line_h=9)
    # Faixa CTA
    c.setFillColor(PRIMARY)
    c.rect(20 * mm, 18 * mm, PAGE_W - 40 * mm, 20 * mm, fill=1, stroke=0)
    c.setFillColor(white)
    c.setFont("Helvetica-Bold", 14)
    c.drawCentredString(PAGE_W / 2, 27 * mm,
                        "4–8 horas   →   menos de 15 minutos por orçamento")


def slide_4_mercado(c):
    _top_band(c, "Mercado", "PT primeiro, expansão ibérica depois")
    # 3 KPI boxes
    y = PAGE_H - 95 * mm
    _kpi_box(c, 20 * mm, y, 78 * mm, 40 * mm, "8 B€", "Obras residenciais/ano em Portugal")
    _kpi_box(c, 110 * mm, y, 78 * mm, 40 * mm, "~30 mil", "PMEs da construção elegíveis")
    _kpi_box(c, 200 * mm, y, 78 * mm, 40 * mm, "300 M€", "SAM aproximado (SaaS setor)")
    # Segmentos alvo
    c.setFillColor(DARK)
    c.setFont("Helvetica-Bold", 13)
    c.drawString(20 * mm, 48 * mm, "Segmentos-alvo:")
    _bullets(c, 20 * mm, 40 * mm, [
        "Empreiteiros e PMEs de construção (2–50 colaboradores)",
        "Arquitetos e gabinetes de projeto que precisam de estimativas rápidas",
        "Autoconstrutores e particulares em obras de renovação",
    ], size=11, line_h=7)


def slide_5_produto(c):
    _top_band(c, "Produto", "5 pilares que substituem 5 ferramentas")
    # 2 colunas de features
    features_left = [
        ("Medição 2D/3D com IA", "DWG · DXF · PDF · foto — deteção automática"),
        ("Estimação inteligente", "Betão, aço, vãos, mão de obra em segundos"),
        ("Biblioteca de preços", "Trabalhos e materiais partilhados PT"),
    ]
    features_right = [
        ("CRM + assinatura", "Clientes, propostas, tracking, assinatura eletrónica"),
        ("Faturação automática", "Situações de trabalho, sinais, faturas finais"),
        ("Painel LC", "Licenças de construção e planeamento integrado"),
    ]
    for i, (title, desc) in enumerate(features_left):
        y = PAGE_H - 55 * mm - i * 32 * mm
        c.setFillColor(PRIMARY)
        c.rect(20 * mm, y, 4, 22 * mm, fill=1, stroke=0)
        c.setFillColor(DARK)
        c.setFont("Helvetica-Bold", 13)
        c.drawString(28 * mm, y + 15 * mm, title)
        c.setFillColor(MUTED)
        c.setFont("Helvetica", 10)
        c.drawString(28 * mm, y + 6 * mm, desc)
    for i, (title, desc) in enumerate(features_right):
        y = PAGE_H - 55 * mm - i * 32 * mm
        c.setFillColor(PRIMARY)
        c.rect(150 * mm, y, 4, 22 * mm, fill=1, stroke=0)
        c.setFillColor(DARK)
        c.setFont("Helvetica-Bold", 13)
        c.drawString(158 * mm, y + 15 * mm, title)
        c.setFillColor(MUTED)
        c.setFont("Helvetica", 10)
        c.drawString(158 * mm, y + 6 * mm, desc)


def slide_6_tracao(c):
    _top_band(c, "Tração e diferencial", "Já em produção")
    _bullets(c, 20 * mm, PAGE_H - 45 * mm, [
        "Plataforma operacional em construpilot.pt — SaaS multi-tenant",
        "Localização 100% PT-PT — único fornecedor especializado em Portugal",
        "Integrações produtivas: CloudConvert (planos), Tavily (pesquisa), Resend (emails)",
        "Domínio verificado + SPF/DKIM + emails transacionais operacionais",
        "Motor de IA proprietário para deteção de estrutura em plantas",
    ], size=13, line_h=9)
    # Caixa "vs concorrência"
    c.setFillColor(LIGHT_BG)
    c.rect(20 * mm, 18 * mm, PAGE_W - 40 * mm, 32 * mm, fill=1, stroke=0)
    c.setStrokeColor(PRIMARY)
    c.rect(20 * mm, 18 * mm, PAGE_W - 40 * mm, 32 * mm, fill=0, stroke=1)
    c.setFillColor(PRIMARY)
    c.setFont("Helvetica-Bold", 11)
    c.drawString(25 * mm, 42 * mm, "Diferencial vs Bloco 6, PrimaverA, softwares FR:")
    c.setFillColor(DARK)
    c.setFont("Helvetica", 10)
    c.drawString(25 * mm, 34 * mm, "· Único com medição 2D + estimação IA + CRM num único fluxo")
    c.drawString(25 * mm, 27 * mm, "· Preços de mercado PT integrados (não é template ES/FR adaptado)")
    c.drawString(25 * mm, 20 * mm, "· UX moderno, mobile-first, sem instalação — SaaS puro")


def slide_7_modelo(c):
    _top_band(c, "Modelo de negócio", "Freemium + Marketplace")
    # 3 planos lado a lado
    plans = [
        ("Gratuito", "0 €", ["Estimativas ilimitadas", "1 orçamento/mês", "1 utilizador"], LIGHT_BG, MUTED),
        ("Pro", "29 €/mês", ["Orçamentos ilimitados", "Biblioteca partilhada", "CRM + faturas", "Até 5 utilizadores"], PRIMARY, white),
        ("Empresa", "sob consulta", ["Utilizadores ilimitados", "SSO + API", "Suporte dedicado", "SLA 99,9%"], DARK, white),
    ]
    x0 = 20 * mm
    box_w = 82 * mm
    for i, (name, price, feats, bg, fg) in enumerate(plans):
        x = x0 + i * (box_w + 6 * mm)
        y = PAGE_H - 105 * mm
        c.setFillColor(bg)
        c.rect(x, y, box_w, 55 * mm, fill=1, stroke=0)
        c.setFillColor(fg)
        c.setFont("Helvetica-Bold", 16)
        c.drawString(x + 6 * mm, y + 45 * mm, name)
        c.setFont("Helvetica-Bold", 20)
        c.drawString(x + 6 * mm, y + 33 * mm, price)
        c.setFont("Helvetica", 9)
        for j, f in enumerate(feats):
            c.drawString(x + 6 * mm, y + 24 * mm - j * 5 * mm, f"• {f}")
    # Nota receita
    c.setFillColor(DARK)
    c.setFont("Helvetica-Bold", 11)
    c.drawString(20 * mm, 32 * mm, "Fluxos de receita:")
    c.setFillColor(MUTED)
    c.setFont("Helvetica", 10)
    c.drawString(20 * mm, 25 * mm,
                 "1) Subscrições recorrentes (MRR)   2) Marketplace de profissionais (comissão)   3) Add-ons: SMS, assinatura eletrónica premium")


def slide_8_equipa_cta(c):
    """Slide final — fundo escuro, CTA forte."""
    c.setFillColor(DARK)
    c.rect(0, 0, PAGE_W, PAGE_H, fill=1, stroke=0)
    c.setFillColor(PRIMARY)
    c.rect(0, PAGE_H - 8 * mm, PAGE_W, 8 * mm, fill=1, stroke=0)
    # Título
    c.setFillColor(white)
    c.setFont("Helvetica-Bold", 30)
    c.drawString(20 * mm, PAGE_H - 32 * mm, "Vamos falar.")
    c.setFillColor(HexColor("#94a3b8"))
    c.setFont("Helvetica", 13)
    c.drawString(20 * mm, PAGE_H - 44 * mm,
                 "À procura de investimento seed para acelerar produto e crescimento.")
    # 2 colunas: Roadmap + Contacto
    y0 = PAGE_H - 70 * mm
    c.setFillColor(PRIMARY)
    c.setFont("Helvetica-Bold", 12)
    c.drawString(20 * mm, y0, "ROADMAP 6 MESES")
    c.setFillColor(white)
    c.setFont("Helvetica", 11)
    roadmap = [
        "SMS de ativação (SMS.to) e recuperação de contas",
        "Pagamentos Stripe integrados (subscrições + sinais)",
        "Marketplace de profissionais qualificados",
        "Expansão ES + EN (i18n já preparado)",
        "App móvel iOS/Android (React Native)",
    ]
    for i, r in enumerate(roadmap):
        c.setFillColor(PRIMARY)
        c.rect(20 * mm, y0 - 8 * mm - i * 7 * mm - 3, 3, 3, fill=1, stroke=0)
        c.setFillColor(white)
        c.drawString(26 * mm, y0 - 8 * mm - i * 7 * mm - 2, r)
    # Contacto
    c.setFillColor(PRIMARY)
    c.setFont("Helvetica-Bold", 12)
    c.drawString(160 * mm, y0, "CONTACTO")
    c.setFillColor(white)
    c.setFont("Helvetica-Bold", 16)
    c.drawString(160 * mm, y0 - 12 * mm, "info@construpilot.pt")
    c.setFont("Helvetica", 12)
    c.drawString(160 * mm, y0 - 22 * mm, "construpilot.pt")
    c.setFillColor(HexColor("#94a3b8"))
    c.setFont("Helvetica", 10)
    c.drawString(160 * mm, y0 - 34 * mm, "Marca uma demo:")
    c.setFillColor(PRIMARY)
    c.setFont("Helvetica-Bold", 11)
    c.drawString(160 * mm, y0 - 42 * mm, "construpilot.pt/demo")
    # Rodapé
    c.setFillColor(HexColor("#64748b"))
    c.setFont("Helvetica", 9)
    c.drawString(20 * mm, 12 * mm, "ConstruPilot · 2026 · Documento confidencial")
    c.drawRightString(PAGE_W - 20 * mm, 12 * mm, "Obrigado.")


# ==========================================================================
# Build
# ==========================================================================
def main():
    OUT.parent.mkdir(parents=True, exist_ok=True)
    c = canvas.Canvas(str(OUT), pagesize=(PAGE_W, PAGE_H))
    c.setTitle("ConstruPilot — Pitch Deck 2026")
    c.setAuthor("ConstruPilot")
    c.setSubject("Pitch Deck para investidores")

    slides = [
        slide_1_capa,
        slide_2_problema,
        slide_3_solucao,
        slide_4_mercado,
        slide_5_produto,
        slide_6_tracao,
        slide_7_modelo,
        slide_8_equipa_cta,
    ]
    total = len(slides)
    for i, slide_fn in enumerate(slides, start=1):
        slide_fn(c)
        # Rodapé em todos exceto capa e slide final (que têm design próprio)
        if i not in (1, total):
            _footer(c, i, total)
        c.showPage()
    c.save()
    size = OUT.stat().st_size
    print(f"OK: {OUT} ({size} bytes = {size/1024:.1f} KB, {total} slides)")


if __name__ == "__main__":
    main()
