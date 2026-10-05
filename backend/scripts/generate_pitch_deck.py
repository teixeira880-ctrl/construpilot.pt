"""Gera o pitch deck PT-PT (8 slides, 16:9) em /app/frontend/public/pitch-deck.pdf.

Execução:
    python /app/backend/scripts/generate_pitch_deck.py
"""
from pathlib import Path
from reportlab.lib.colors import HexColor, white, black
from reportlab.lib.pagesizes import landscape
from reportlab.pdfgen import canvas
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader

# 16:9 slide — 297 mm × 167 mm
PAGE_W, PAGE_H = 297 * mm, 167 * mm
PRIMARY   = HexColor("#10b981")   # verde ConstruPilot
DARK      = HexColor("#0f172a")   # slate-900
MUTED     = HexColor("#64748b")   # slate-500
LIGHT_BG  = HexColor("#f8fafc")   # slate-50
ACCENT    = HexColor("#f97316")   # laranja de destaque
BORDER    = HexColor("#1e293b")   # slate-800 para borda de screenshots

OUT = Path("/app/frontend/public/pitch-deck.pdf")
SHOTS = Path("/app/backend/scripts/pitch_screenshots")


def _drop_shadow_image(c, img_path, x, y, w, h, caption=None):
    """Desenha imagem com moldura escura fina + legenda opcional por baixo."""
    # sombra suave (retângulo escuro deslocado)
    c.setFillColor(HexColor("#020617"))
    c.rect(x + 1.2 * mm, y - 1.2 * mm, w, h, fill=1, stroke=0)
    # borda
    c.setStrokeColor(BORDER)
    c.setLineWidth(0.6)
    c.rect(x, y, w, h, fill=0, stroke=1)
    # imagem
    try:
        img = ImageReader(str(img_path))
        c.drawImage(img, x + 0.4, y + 0.4, w - 0.8, h - 0.8,
                    preserveAspectRatio=True, anchor='c', mask='auto')
    except Exception as e:
        c.setFillColor(MUTED)
        c.setFont("Helvetica", 9)
        c.drawString(x + 4, y + h / 2, f"[imagem em falta: {img_path.name}]")
    # legenda
    if caption:
        c.setFillColor(MUTED)
        c.setFont("Helvetica-Oblique", 8)
        c.drawString(x, y - 5 * mm, caption)


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
    # Bullets à esquerda (coluna estreita)
    _bullets(c, 15 * mm, PAGE_H - 45 * mm, [
        "Medição automática de plantas 2D/3D por IA",
        "Estimativa instantânea de betão, aço, vãos",
        "Biblioteca partilhada de trabalhos PT",
        "Orçamento pronto em minutos + assinatura",
        "CRM: clientes, obras, faturas, cobrança",
    ], size=11, line_h=8)
    # Screenshot grande à direita (landing 3D)
    _drop_shadow_image(
        c, SHOTS / "01-landing.png",
        x=135 * mm, y=30 * mm, w=145 * mm, h=95 * mm,
        caption="Landing pública — visualizador 3D em tempo real"
    )
    # Faixa CTA no fundo (encolhida)
    c.setFillColor(PRIMARY)
    c.rect(15 * mm, 12 * mm, 110 * mm, 14 * mm, fill=1, stroke=0)
    c.setFillColor(white)
    c.setFont("Helvetica-Bold", 11)
    c.drawCentredString(70 * mm, 17 * mm, "4–8 h  →  <15 min por orçamento")


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
    _top_band(c, "Produto", "Assistente de Obras + Painel + Biblioteca")
    # 2 screenshots lado a lado
    _drop_shadow_image(
        c, SHOTS / "02-dashboard.png",
        x=15 * mm, y=35 * mm, w=130 * mm, h=85 * mm,
        caption="Painel do utilizador — checklist e KPIs"
    )
    _drop_shadow_image(
        c, SHOTS / "03-price-library.png",
        x=152 * mm, y=35 * mm, w=130 * mm, h=85 * mm,
        caption="Biblioteca partilhada — trabalhos e materiais PT 2026"
    )
    # Legendas curtas por baixo
    c.setFillColor(DARK)
    c.setFont("Helvetica-Bold", 10)
    c.drawString(15 * mm, 24 * mm, "6 pilares num só produto:")
    c.setFillColor(MUTED)
    c.setFont("Helvetica", 9)
    c.drawString(15 * mm, 18 * mm,
                 "Assistente de Obras (IA + web) · Medição IA · Estimação · Biblioteca PT · CRM + assinatura · Faturação SAF-T")


def slide_6_tracao(c):
    _top_band(c, "Tração e diferencial", "Já em produção")
    # Bullets à esquerda
    _bullets(c, 15 * mm, PAGE_H - 45 * mm, [
        "SaaS multi-tenant PT em produção — localização 100 % PT-PT",
        "Opus 5.5 + OpenAI + Perplexity Plus (chat SSE, normas, materiais)",
        "Assistente de Obras — diagnóstico IA + web search com citações",
        "Plans Pro + Autodesk APS — DWG/RVT/IFC → análise IA",
        "Export Excel 5 regimes IVA PT (Continente/Açores/Madeira/ARU/Isento)",
        "Integrações produtivas: CloudConvert · Tavily · Resend",
    ], size=10.5, line_h=7)
    # Screenshot do estimador à direita
    _drop_shadow_image(
        c, SHOTS / "04-estimation.png",
        x=150 * mm, y=25 * mm, w=132 * mm, h=100 * mm,
        caption="Estimador em produção — 3 passos, resultado em segundos"
    )
    # Caixa diferencial compacta em baixo
    c.setFillColor(LIGHT_BG)
    c.rect(15 * mm, 12 * mm, 130 * mm, 24 * mm, fill=1, stroke=0)
    c.setStrokeColor(PRIMARY)
    c.rect(15 * mm, 12 * mm, 130 * mm, 24 * mm, fill=0, stroke=1)
    c.setFillColor(PRIMARY)
    c.setFont("Helvetica-Bold", 9)
    c.drawString(19 * mm, 30 * mm, "DIFERENCIAL")
    c.setFillColor(DARK)
    c.setFont("Helvetica", 8.5)
    c.drawString(19 * mm, 23 * mm, "· Assistente de Obras com acesso Internet + citações oficiais DRE/LNEC/APA")
    c.drawString(19 * mm, 17 * mm, "· Medição 2D · Estimação · Biblioteca PT 2026 · CRM · UX mobile-first")


def slide_7_modelo(c):
    _top_band(c, "Modelo de negócio", "Freemium + planos para profissionais")
    # 4 planos lado a lado
    plans = [
        ("Grátis",       "0 €",         ["Coach IA 20/h · Assistente Obras 10/h", "Estimativas ilimitadas", "1 utilizador"], LIGHT_BG, MUTED),
        ("Pro",          "99 €/mês",    ["Coach IA 60/h · Assistente Obras 40/h", "Orçamentos + CRM + faturas", "Autodesk APS · Excel IVA PT"], PRIMARY, white),
        ("Pro Business", "179 €/mês",   ["Coach IA 120/h · Assistente Obras 80/h", "Perplexity Plus · 5 utilizadores", "Rendering 3D · Automações"], DARK, white),
        ("Enterprise",   "sob consulta", ["Utilizadores ilimitados", "SSO + API", "SLA 99,9 %"], ACCENT, white),
    ]
    x0 = 12 * mm
    box_w = 65 * mm
    for i, (name, price, feats, bg, fg) in enumerate(plans):
        x = x0 + i * (box_w + 3 * mm)
        y = PAGE_H - 115 * mm
        c.setFillColor(bg)
        c.rect(x, y, box_w, 65 * mm, fill=1, stroke=0)
        c.setFillColor(fg)
        c.setFont("Helvetica-Bold", 14)
        c.drawString(x + 5 * mm, y + 55 * mm, name)
        c.setFont("Helvetica-Bold", 16)
        c.drawString(x + 5 * mm, y + 44 * mm, price)
        c.setFont("Helvetica", 7.5)
        for j, f in enumerate(feats):
            c.drawString(x + 5 * mm, y + 34 * mm - j * 5 * mm, f"• {f}")
    # Nota receita
    c.setFillColor(DARK)
    c.setFont("Helvetica-Bold", 11)
    c.drawString(15 * mm, 32 * mm, "Fluxos de receita:")
    c.setFillColor(MUTED)
    c.setFont("Helvetica", 9.5)
    c.drawString(15 * mm, 25 * mm,
                 "1) Subscrições MRR (Pro 99 € · Pro Business 179 €)   2) Marketplace de profissionais (comissão)   3) Add-ons: SMS, faturação eletrónica, API")
    # Nota anual
    c.setFillColor(PRIMARY)
    c.setFont("Helvetica-Bold", 9)
    c.drawString(15 * mm, 18 * mm,
                 "Planos anuais com ~17 % de desconto · Pro 988 €/ano · Pro Business 1 783 €/ano · trial 7 dias")


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
