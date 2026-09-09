"""Gera documentação comercial completa PT-PT (PDF + PPTX) do ConstruPilot.

Saída:
    /app/frontend/public/construpilot-funcionalidades-completas.pdf
    /app/frontend/public/construpilot-funcionalidades-completas.pptx

Execução:
    cd /app/backend && python scripts/generate_features_docs.py
"""
from __future__ import annotations
from pathlib import Path
from datetime import datetime

# --- Marca ---
PRIMARY = "#10b981"
DARK = "#0f172a"
SLATE = "#64748b"
LIGHT = "#f8fafc"
ORANGE = "#f97316"

OUT_DIR = Path("/app/frontend/public")
OUT_DIR.mkdir(parents=True, exist_ok=True)
PDF_PATH = OUT_DIR / "construpilot-funcionalidades-completas.pdf"
PPTX_PATH = OUT_DIR / "construpilot-funcionalidades-completas.pptx"

# ============================================================================
# CONTEÚDO CANÓNICO (PT-PT)
# ============================================================================
KPIS = [
    ("322", "trabalhos compostos"),
    ("43", "especialidades"),
    ("7 021", "linhas de composição"),
    ("6 / 13 / 23 %", "taxas IVA PT"),
]

REGIONAL_COEFS = [
    ("Lisboa", "1,15"),
    ("Porto", "1,08"),
    ("Algarve", "1,12"),
    ("Interior", "0,90"),
]

FONTES = "Santander · CYPE Ingenieros · Multigam · Grupo Casais"

PLANS = {
    "Particulares": {
        "tagline": "Freemium — para autoconstrutores, proprietários e primeiro estudo.",
        "features": [
            ("Landing Portugal", "Página inicial 100% PT com landings regionais (Lisboa, Porto, Algarve, Interior)."),
            ("Estimativa por descrição", "Descreva a obra em texto e receba uma estimativa instantânea, chiffrada, por m² e por especialidade."),
            ("Estimativa por voz", "Grave um vídeo/áudio a descrever a obra: Whisper transcreve em PT-PT e a IA gera o orçamento."),
            ("Análise foto de divisão", "Fotografe uma divisão: a IA identifica paredes, pavimento, teto, vãos, sanitários e propõe os trabalhos."),
            ("Análise foto com dimensões", "Medição por foto: obtenha comprimento/largura/altura aproximados de qualquer divisão."),
            ("Coach IA obras", "Chatbot em PT-PT que responde às suas dúvidas sobre obras, licenças, IVA e materiais."),
            ("Calculadoras públicas", "Azulejos, pladur, betão, isolamento — resultado detalhado com quantidades e orçamento."),
            ("Guias Faço-eu-mesmo (DIY)", "Passo a passo, materiais calculados, dicas de profissional e erros a evitar."),
            ("Pesquisa multi-fornecedor", "Compare preços de materiais em vários fornecedores portugueses."),
            ("Biblioteca partilhada (consulta)", "322 trabalhos compostos PT 2026 com preços baixo/médio/alto."),
            ("Blog técnico", "Artigos sobre construção, renovação, isolamento, pladur, canalização, IVA."),
            ("Comparativo entre soluções", "Escolha entre pladur × alvenaria, gás × elétrico, ladrilho × microcimento."),
            ("Partilha por link + QR", "Envie fichas ao cliente por SMS ou email; funciona sem conta."),
            ("Descarga PDF de fichas", "Cada ficha de cálculo exportável em PDF profissional."),
            ("SEO PT + Open Graph", "Meta tags, sitemap, OG image, canonical PT-PT."),
        ],
    },
    "Premium": {
        "tagline": "Upgrade Particulares — quem quer estudar plantas e ter export PDF profissional.",
        "features": [
            ("Estudo de plantas DWG/DXF/PDF", "Upload de plantas (CloudConvert converte DWG→DXF); leitura automática de divisões, muros e vãos."),
            ("Medição 2D interativa", "Corrija a leitura da IA: mova divisórias, ajuste medidas, adicione elementos."),
            ("Comparação de plantas", "Compare duas versões (antes/depois) lado a lado."),
            ("Estimação estrutural avançada", "Cálculo de armaduras, cofragens, betão, laje, vigas."),
            ("Análise foto profissional", "Dimensões, área útil, área bruta, materiais, tempo de execução."),
            ("Notificações Push (VAPID)", "Alertas quando o estudo termina ou o orçamento é aceite."),
            ("Exportação PDF profissional", "PDF com logotipo, cabeçalho verde, KPIs, tabela de trabalhos e assinatura."),
            ("Painel utilizador", "Histórico completo dos seus estudos, plantas e fotos."),
        ],
    },
    "Pro": {
        "tagline": "Para profissionais liberais e pequenas empresas de construção.",
        "features": [
            ("Biblioteca pessoal 322 items", "Catálogo inicial PT 2026 já semeado; cada empresa ajusta preços."),
            ("Catálogo de materiais próprio", "Import Excel/CSV; procura Tavily de preços web."),
            ("Orçamentos completos", "Editor drag-and-drop, IVA 6/13/23%, retenções, sinal, condições de pagamento."),
            ("Faturas + notas de crédito", "Numeração automática, série anual, formatos PT."),
            ("Assinatura eletrónica", "Cliente assina no telemóvel; PDF final com selo temporal."),
            ("CRM básico", "Clientes, obras, projetos, pipeline de propostas."),
            ("Envio orçamento/fatura por email", "Via Resend (domínio verificado construpilot.pt)."),
            ("Recibos PDF automáticos", "Emitidos assim que o pagamento é registado."),
            ("Templates com branding", "Logotipo, cores, condições gerais editáveis."),
            ("Estatísticas de negócio", "Volume de negócio assinado, faturado, por especialidade e por cliente."),
            ("QuoteScanner", "Digitalize orçamentos concorrentes e faça matching automático de linhas."),
            ("Portal do cliente", "O cliente consulta orçamentos, faturas e histórico numa área privada."),
            ("Leads e avaliações", "Receba pedidos de particulares; publique reviews verificadas."),
            ("Portal Verified", "Selo profissional com KYC básico."),
        ],
    },
    "Pro Business": {
        "tagline": "Empresas com vários utilizadores, marketplace e estudos avançados.",
        "features": [
            ("Biblioteca partilhada PT 2026", "322 items com preços baixo/médio/alto usados pelos estudos de plantas em fallback."),
            ("Coeficientes regionais", "Lisboa 1,15 · Porto 1,08 · Algarve 1,12 · Interior 0,90 aplicados automaticamente."),
            ("Multi-utilizador por empresa", "Convite de colegas, permissões por perfil (comercial, técnico, administrativo)."),
            ("KYC empresa + verificação", "NIF, alvará, seguros de responsabilidade civil, número CCP."),
            ("Import DPGF Excel", "Suba um DPGF FR/PT em Excel e recupere linhas orçamentadas."),
            ("Marketplace pro", "Publique especialidade e receba pedidos de particulares (radius geográfico)."),
            ("Estatísticas avançadas", "CA anual assinado, painel executivo, previsão de tesouraria."),
            ("Auditoria e recibos pro", "Trail de eventos, exportação para contabilista."),
            ("EInvoicing (Factur-X PT)", "Faturas eletrónicas certificadas para clientes públicos."),
            ("API keys empresariais", "Ligue o seu ERP ou app à ConstruPilot."),
            ("Módulo HR (scaffold)", "Gestão de funcionários, horas, ordenados por obra."),
            ("Módulo Approvisionamento", "Encomendas materiais, folhas de obra, entregas."),
            ("Suporte prioritário", "Resposta útil em <4h, gestor de conta dedicado."),
        ],
    },
}

BLOG_ARTIGOS = [
    ("Preços de construção em Portugal 2026", "Balanço regional dos preços por m² por especialidade (Lisboa, Porto, Algarve)."),
    ("Como calcular betão para uma laje", "Fórmula, margens de segurança e comparativo saco × autobetoneira."),
    ("Pladur × alvenaria: qual escolher?", "Comparação de custo, isolamento térmico e acústico, execução."),
    ("IVA na construção em Portugal", "Regime dos 6% (reabilitação urbana), 13% e 23% — quando cada um se aplica."),
    ("Construir piscina em Portugal", "Betão × fibra de vidro × liner; regulação e custos 2026."),
    ("Licença de construção: passos e prazos", "Da submissão à Câmara ao alvará; documentos e taxas."),
]

INTEGRACOES = [
    ("Emergent LLM", "Claude Sonnet + GPT-4 para análise de fotos, estimação IA e coach conversacional."),
    ("Resend", "Emails transacionais (verificação, orçamentos, faturas) com domínio construpilot.pt verificado (SPF/DKIM)."),
    ("CloudConvert", "Conversão DWG→DXF e PDF→imagens para o motor de leitura de plantas."),
    ("Tavily", "Pesquisa web em tempo real de preços de materiais em fornecedores portugueses."),
    ("OpenAI Whisper", "Transcrição de vídeos/áudios em PT-PT (herda da língua do utilizador)."),
    ("Web Speech API", "Reconhecimento de voz no navegador para o Coach IA (pt-PT)."),
    ("VAPID Push", "Notificações Push web mesmo com o browser fechado."),
    ("Twilio / SMS.to", "SMS transacionais (em preparação)."),
    ("Stripe", "Checkout de subscrições Premium/Pro/Pro Business (em preparação)."),
    ("AutoSEO webhook", "Publicação automática de artigos de blog com sitemap regenerado."),
    ("MongoDB Atlas", "Base de dados NoSQL managed, TLS e backups automáticos."),
    ("FastAPI + Motor", "Backend Python assíncrono, tipagem Pydantic e alta concorrência."),
]

ROADMAP = [
    ("SMS.to ativação", "Notificações SMS PT para orçamentos e faturas."),
    ("Stripe Checkout", "Subscrição self-service com cartão SEPA."),
    ("Expansão EN + ES", "Multi-idioma (após consolidação PT)."),
    ("Módulo HR completo", "Payroll, ponto biométrico, ordenados por obra."),
    ("Planning + Gantt", "Planeamento visual do estaleiro."),
    ("Assinatura biométrica", "Assinatura móvel qualificada (eIDAS)."),
    ("Módulo Approvisionamento V2", "Encomendas cruzadas, alertas de rutura."),
    ("App móvel iOS/Android", "Wrapper nativo PWA (já responsivo)."),
]

# ============================================================================
# GERADOR PDF (ReportLab)
# ============================================================================
def build_pdf() -> None:
    from reportlab.lib.colors import HexColor, white
    from reportlab.lib.units import mm
    from reportlab.pdfgen import canvas as pdfcanvas

    # A4 paisagem 297×210 mm
    PW, PH = 297 * mm, 210 * mm
    c = pdfcanvas.Canvas(str(PDF_PATH), pagesize=(PW, PH))
    page_num = 0

    def new_page(section_title: str = "", cover: bool = False):
        nonlocal page_num
        if page_num > 0:
            c.showPage()
        page_num += 1
        if cover:
            return
        # header verde
        c.setFillColor(HexColor(PRIMARY))
        c.rect(0, PH - 12 * mm, PW, 12 * mm, fill=1, stroke=0)
        c.setFillColor(white)
        c.setFont("Helvetica-Bold", 11)
        c.drawString(15 * mm, PH - 8 * mm, "ConstruPilot — Funcionalidades Completas 2026")
        c.setFont("Helvetica", 9)
        c.drawRightString(PW - 15 * mm, PH - 8 * mm, section_title)
        # footer
        c.setFillColor(HexColor(SLATE))
        c.setFont("Helvetica", 8)
        c.drawString(15 * mm, 8 * mm, "construpilot.pt")
        c.drawRightString(PW - 15 * mm, 8 * mm, f"Página {page_num}")

    def wrap_text(text, max_chars):
        words = text.split()
        lines, cur = [], ""
        for w in words:
            if len(cur) + len(w) + 1 <= max_chars:
                cur = (cur + " " + w).strip()
            else:
                lines.append(cur); cur = w
        if cur:
            lines.append(cur)
        return lines

    # ---- capa ----
    new_page(cover=True)
    c.setFillColor(HexColor(DARK))
    c.rect(0, 0, PW, PH, fill=1, stroke=0)
    c.setFillColor(HexColor(PRIMARY))
    c.rect(15 * mm, 90 * mm, 60 * mm, 3 * mm, fill=1, stroke=0)
    c.setFillColor(white)
    c.setFont("Helvetica-Bold", 44)
    c.drawString(15 * mm, 105 * mm, "ConstruPilot")
    c.setFont("Helvetica-Bold", 26)
    c.drawString(15 * mm, 75 * mm, "Funcionalidades Completas — 2026")
    c.setFillColor(HexColor(SLATE))
    c.setFont("Helvetica", 14)
    c.drawString(15 * mm, 62 * mm, "Guia comercial · Particulares · Premium · Pro · Pro Business")
    c.setFillColor(white)
    c.setFont("Helvetica", 11)
    c.drawString(15 * mm, 30 * mm, "construpilot.pt")
    c.drawString(15 * mm, 24 * mm, "info@construpilot.pt")
    c.setFillColor(HexColor(PRIMARY))
    c.setFont("Helvetica-Bold", 11)
    c.drawString(15 * mm, 15 * mm, "Da planta ao orçamento em minutos.")

    # ---- índice ----
    new_page("Índice")
    c.setFillColor(HexColor(DARK))
    c.setFont("Helvetica-Bold", 24)
    c.drawString(15 * mm, PH - 30 * mm, "Índice")
    sections_list = [
        "1. Visão geral e KPIs",
        "2. Plano Particulares (Freemium)",
        "3. Plano Premium",
        "4. Plano Pro (Profissionais)",
        "5. Plano Pro Business (Empresas)",
        "6. Comparação de planos",
        "7. Blog e prospetos regionais",
        "8. Integrações",
        "9. Roadmap 2026",
    ]
    c.setFont("Helvetica", 14)
    y = PH - 50 * mm
    for s in sections_list:
        c.setFillColor(HexColor(PRIMARY))
        c.rect(15 * mm, y - 1 * mm, 3 * mm, 3 * mm, fill=1, stroke=0)
        c.setFillColor(HexColor(DARK))
        c.drawString(22 * mm, y, s)
        y -= 12 * mm

    # ---- 1. Visão geral ----
    new_page("Visão geral")
    c.setFillColor(HexColor(DARK)); c.setFont("Helvetica-Bold", 22)
    c.drawString(15 * mm, PH - 30 * mm, "1. Visão geral e KPIs")
    c.setFillColor(HexColor(SLATE)); c.setFont("Helvetica", 12)
    intro = ("Plataforma SaaS 100% PT-PT para construção civil. "
             "Da descrição do projeto (texto, voz ou foto) até ao orçamento profissional em minutos, "
             "com preços de mercado Portugal 2026 e coeficientes regionais aplicados automaticamente.")
    y = PH - 45 * mm
    for line in wrap_text(intro, 100):
        c.drawString(15 * mm, y, line); y -= 6 * mm
    # KPIs
    y -= 8 * mm
    for i, (val, label) in enumerate(KPIS):
        x = 15 * mm + (i % 4) * 68 * mm
        yk = y - (i // 4) * 30 * mm
        c.setFillColor(HexColor(LIGHT))
        c.rect(x, yk - 22 * mm, 62 * mm, 22 * mm, fill=1, stroke=0)
        c.setFillColor(HexColor(PRIMARY)); c.setFont("Helvetica-Bold", 22)
        c.drawString(x + 4 * mm, yk - 10 * mm, val)
        c.setFillColor(HexColor(DARK)); c.setFont("Helvetica", 10)
        c.drawString(x + 4 * mm, yk - 17 * mm, label)
    y -= 32 * mm
    # Coefs
    c.setFillColor(HexColor(DARK)); c.setFont("Helvetica-Bold", 14)
    c.drawString(15 * mm, y, "Coeficientes regionais aplicados")
    y -= 8 * mm
    c.setFont("Helvetica", 11)
    for zona, coef in REGIONAL_COEFS:
        c.setFillColor(HexColor(PRIMARY))
        c.circle(17 * mm, y + 1 * mm, 1 * mm, fill=1, stroke=0)
        c.setFillColor(HexColor(DARK))
        c.drawString(22 * mm, y, f"{zona}: × {coef}")
        y -= 6 * mm
    y -= 4 * mm
    c.setFillColor(HexColor(SLATE)); c.setFont("Helvetica-Oblique", 10)
    c.drawString(15 * mm, y, f"Fontes: {FONTES}")

    # ---- 2..5 Planos ----
    for idx, (plan_name, plan_data) in enumerate(PLANS.items(), start=2):
        features = plan_data["features"]
        # 12 features por página máximo
        pages = [features[i:i + 12] for i in range(0, len(features), 12)]
        for pnum, chunk in enumerate(pages):
            new_page(f"Plano {plan_name}")
            c.setFillColor(HexColor(DARK)); c.setFont("Helvetica-Bold", 22)
            c.drawString(15 * mm, PH - 30 * mm, f"{idx}. Plano {plan_name}")
            c.setFillColor(HexColor(SLATE)); c.setFont("Helvetica-Oblique", 11)
            if pnum == 0:
                c.drawString(15 * mm, PH - 38 * mm, plan_data["tagline"])
            y = PH - 50 * mm
            for name, desc in chunk:
                c.setFillColor(HexColor(PRIMARY)); c.setFont("Helvetica-Bold", 12)
                c.drawString(15 * mm, y, "▸ " + name)
                c.setFillColor(HexColor(DARK)); c.setFont("Helvetica", 10)
                y -= 5 * mm
                for line in wrap_text(desc, 130):
                    c.drawString(20 * mm, y, line); y -= 4.5 * mm
                y -= 3 * mm

    # ---- 6. Comparação de planos ----
    new_page("Comparação de planos")
    c.setFillColor(HexColor(DARK)); c.setFont("Helvetica-Bold", 22)
    c.drawString(15 * mm, PH - 30 * mm, "6. Comparação de planos")
    cols = ["Funcionalidade", "Particulares", "Premium", "Pro", "Pro Business"]
    matrix = [
        ["Estimativa por texto/voz/foto", "●", "●", "●", "●"],
        ["Coach IA obras", "●", "●", "●", "●"],
        ["Calculadoras + Guias DIY", "●", "●", "●", "●"],
        ["Consulta biblioteca partilhada", "●", "●", "●", "●"],
        ["Estudo de plantas DWG/DXF/PDF", "—", "●", "●", "●"],
        ["Medição 2D interativa", "—", "●", "●", "●"],
        ["Notificações Push", "—", "●", "●", "●"],
        ["Biblioteca pessoal editável", "—", "—", "●", "●"],
        ["Orçamentos + faturas + assinatura", "—", "—", "●", "●"],
        ["CRM e portal do cliente", "—", "—", "●", "●"],
        ["Envio por email (Resend)", "—", "—", "●", "●"],
        ["Multi-utilizador por empresa", "—", "—", "—", "●"],
        ["Marketplace pro + leads", "—", "—", "—", "●"],
        ["EInvoicing (Factur-X PT)", "—", "—", "—", "●"],
        ["API keys + módulos HR/Appro", "—", "—", "—", "●"],
        ["Suporte prioritário", "—", "—", "—", "●"],
    ]
    # header
    col_x = [15 * mm, 100 * mm, 140 * mm, 175 * mm, 215 * mm]
    y = PH - 45 * mm
    c.setFillColor(HexColor(PRIMARY))
    c.rect(15 * mm, y - 2 * mm, PW - 30 * mm, 7 * mm, fill=1, stroke=0)
    c.setFillColor(white); c.setFont("Helvetica-Bold", 10)
    for i, h in enumerate(cols):
        c.drawString(col_x[i] + 2 * mm, y + 1 * mm, h)
    y -= 9 * mm
    c.setFont("Helvetica", 9); c.setFillColor(HexColor(DARK))
    for row in matrix:
        for i, cell in enumerate(row):
            if i == 0:
                c.drawString(col_x[i] + 2 * mm, y, cell)
            else:
                color = PRIMARY if cell == "●" else SLATE
                c.setFillColor(HexColor(color))
                c.drawString(col_x[i] + 8 * mm, y, cell)
                c.setFillColor(HexColor(DARK))
        y -= 6 * mm
        if y < 20 * mm:
            break

    # ---- 7. Blog ----
    new_page("Blog & Prospetos")
    c.setFillColor(HexColor(DARK)); c.setFont("Helvetica-Bold", 22)
    c.drawString(15 * mm, PH - 30 * mm, "7. Blog e prospetos regionais")
    c.setFillColor(HexColor(SLATE)); c.setFont("Helvetica", 11)
    c.drawString(15 * mm, PH - 40 * mm,
                 "Landings regionais SEO PT: Lisboa · Porto · Algarve · Interior. Artigos técnicos:")
    y = PH - 55 * mm
    for titulo, resumo in BLOG_ARTIGOS:
        c.setFillColor(HexColor(PRIMARY)); c.setFont("Helvetica-Bold", 12)
        c.drawString(15 * mm, y, "▸ " + titulo)
        y -= 5 * mm
        c.setFillColor(HexColor(DARK)); c.setFont("Helvetica", 10)
        for line in wrap_text(resumo, 130):
            c.drawString(20 * mm, y, line); y -= 4.5 * mm
        y -= 3 * mm

    # ---- 8. Integrações ----
    pages_int = [INTEGRACOES[i:i + 8] for i in range(0, len(INTEGRACOES), 8)]
    for i, chunk in enumerate(pages_int):
        new_page("Integrações")
        c.setFillColor(HexColor(DARK)); c.setFont("Helvetica-Bold", 22)
        c.drawString(15 * mm, PH - 30 * mm, "8. Integrações")
        y = PH - 45 * mm
        for name, desc in chunk:
            c.setFillColor(HexColor(PRIMARY)); c.setFont("Helvetica-Bold", 12)
            c.drawString(15 * mm, y, "▸ " + name)
            y -= 5 * mm
            c.setFillColor(HexColor(DARK)); c.setFont("Helvetica", 10)
            for line in wrap_text(desc, 130):
                c.drawString(20 * mm, y, line); y -= 4.5 * mm
            y -= 3 * mm

    # ---- 9. Roadmap ----
    new_page("Roadmap")
    c.setFillColor(HexColor(DARK)); c.setFont("Helvetica-Bold", 22)
    c.drawString(15 * mm, PH - 30 * mm, "9. Roadmap 2026")
    y = PH - 45 * mm
    for name, desc in ROADMAP:
        c.setFillColor(HexColor(ORANGE)); c.setFont("Helvetica-Bold", 12)
        c.drawString(15 * mm, y, "▸ " + name)
        y -= 5 * mm
        c.setFillColor(HexColor(DARK)); c.setFont("Helvetica", 10)
        for line in wrap_text(desc, 130):
            c.drawString(20 * mm, y, line); y -= 4.5 * mm
        y -= 3 * mm

    # ---- contra-capa ----
    new_page(cover=True)
    c.setFillColor(HexColor(DARK)); c.rect(0, 0, PW, PH, fill=1, stroke=0)
    c.setFillColor(HexColor(PRIMARY)); c.setFont("Helvetica-Bold", 34)
    c.drawCentredString(PW / 2, PH / 2 + 20 * mm, "Da planta ao orçamento")
    c.setFillColor(white); c.setFont("Helvetica-Bold", 34)
    c.drawCentredString(PW / 2, PH / 2 + 5 * mm, "em minutos.")
    c.setFillColor(HexColor(SLATE)); c.setFont("Helvetica", 14)
    c.drawCentredString(PW / 2, PH / 2 - 15 * mm, "construpilot.pt   ·   info@construpilot.pt")
    c.setFillColor(HexColor(SLATE)); c.setFont("Helvetica", 9)
    c.drawCentredString(PW / 2, 15 * mm, f"© 2026 ConstruPilot. Documento gerado a {datetime.now().strftime('%d/%m/%Y')}.")

    c.save()


# ============================================================================
# GERADOR PPTX (python-pptx)
# ============================================================================
def build_pptx() -> None:
    from pptx import Presentation
    from pptx.util import Inches, Pt, Emu
    from pptx.dml.color import RGBColor
    from pptx.enum.shapes import MSO_SHAPE

    prs = Presentation()
    prs.slide_width = Inches(13.333)  # 16:9
    prs.slide_height = Inches(7.5)
    blank = prs.slide_layouts[6]

    def hex_rgb(h):
        h = h.lstrip("#")
        return RGBColor(int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))

    def add_bg(slide, color):
        bg = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, 0, 0, prs.slide_width, prs.slide_height)
        bg.line.fill.background()
        bg.fill.solid(); bg.fill.fore_color.rgb = hex_rgb(color)
        return bg

    def add_text(slide, x, y, w, h, text, *, size=18, bold=False, color=DARK, align="left"):
        from pptx.enum.text import PP_ALIGN
        tb = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
        tf = tb.text_frame; tf.word_wrap = True
        tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = Emu(0)
        p = tf.paragraphs[0]
        p.alignment = {"left": PP_ALIGN.LEFT, "center": PP_ALIGN.CENTER, "right": PP_ALIGN.RIGHT}[align]
        run = p.add_run(); run.text = text
        run.font.size = Pt(size); run.font.bold = bold; run.font.color.rgb = hex_rgb(color)
        run.font.name = "Calibri"
        return tb

    def add_header(slide, title):
        # barra verde
        bar = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, 0, 0, prs.slide_width, Inches(0.7))
        bar.line.fill.background()
        bar.fill.solid(); bar.fill.fore_color.rgb = hex_rgb(PRIMARY)
        add_text(slide, 0.4, 0.15, 12, 0.5, title, size=18, bold=True, color="#ffffff")

    def add_footer(slide, num):
        add_text(slide, 0.4, 7.05, 6, 0.3, "construpilot.pt", size=10, color=SLATE)
        add_text(slide, 12.4, 7.05, 0.6, 0.3, str(num), size=10, color=SLATE, align="right")

    slide_no = 0

    def new_slide(cover=False, title=None):
        nonlocal slide_no
        s = prs.slides.add_slide(blank)
        slide_no += 1
        if cover:
            add_bg(s, DARK)
        else:
            add_bg(s, "#ffffff")
            if title:
                add_header(s, title)
                add_footer(s, slide_no)
        return s

    # ---- CAPA ----
    s = new_slide(cover=True)
    # barra verde
    bar = s.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(0.6), Inches(2.6), Inches(2.5), Inches(0.15))
    bar.line.fill.background(); bar.fill.solid(); bar.fill.fore_color.rgb = hex_rgb(PRIMARY)
    add_text(s, 0.6, 2.9, 12, 1.5, "ConstruPilot", size=64, bold=True, color="#ffffff")
    add_text(s, 0.6, 4.4, 12, 1, "Funcionalidades Completas — 2026", size=32, bold=True, color="#ffffff")
    add_text(s, 0.6, 5.4, 12, 0.6, "Guia comercial · Particulares · Premium · Pro · Pro Business",
             size=16, color=SLATE)
    add_text(s, 0.6, 6.4, 12, 0.4, "construpilot.pt   ·   info@construpilot.pt", size=13, color="#ffffff")
    add_text(s, 0.6, 6.85, 12, 0.4, "Da planta ao orçamento em minutos.", size=13, bold=True, color=PRIMARY)

    # ---- ÍNDICE ----
    s = new_slide(title="Índice")
    idx_items = [
        "1. Visão geral e KPIs",
        "2. Plano Particulares (Freemium)",
        "3. Plano Premium",
        "4. Plano Pro (Profissionais)",
        "5. Plano Pro Business (Empresas)",
        "6. Comparação de planos",
        "7. Blog e prospetos regionais",
        "8. Integrações",
        "9. Roadmap 2026",
    ]
    for i, txt in enumerate(idx_items):
        add_text(s, 1.0, 1.3 + i * 0.55, 11, 0.5, txt, size=20, bold=True, color=DARK)

    # ---- VISÃO GERAL ----
    s = new_slide(title="1. Visão geral & KPIs")
    add_text(s, 0.6, 1.0, 12, 0.7,
             "Plataforma SaaS 100% PT-PT para construção civil.",
             size=22, bold=True, color=DARK)
    add_text(s, 0.6, 1.6, 12, 0.6,
             "Da descrição do projeto até ao orçamento profissional em minutos — preços PT 2026 + coeficientes regionais.",
             size=14, color=SLATE)
    # 4 KPIs em cards
    for i, (val, label) in enumerate(KPIS):
        x = 0.6 + i * 3.1
        card = s.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(x), Inches(2.6), Inches(2.9), Inches(1.5))
        card.line.color.rgb = hex_rgb(PRIMARY); card.line.width = Pt(1.2)
        card.fill.solid(); card.fill.fore_color.rgb = hex_rgb(LIGHT)
        add_text(s, x + 0.15, 2.75, 2.7, 0.7, val, size=32, bold=True, color=PRIMARY)
        add_text(s, x + 0.15, 3.5, 2.7, 0.4, label, size=13, color=DARK)
    # coefs regionais
    add_text(s, 0.6, 4.6, 12, 0.5, "Coeficientes regionais", size=18, bold=True, color=DARK)
    coef_line = "   ·   ".join([f"{z}: × {c}" for z, c in REGIONAL_COEFS])
    add_text(s, 0.6, 5.15, 12, 0.5, coef_line, size=14, color=PRIMARY)
    add_text(s, 0.6, 6.3, 12, 0.4, f"Fontes: {FONTES}", size=11, color=SLATE)

    # ---- PLANOS (2..5) ----
    for idx, (plan_name, plan_data) in enumerate(PLANS.items(), start=2):
        features = plan_data["features"]
        # slide de intro do plano
        s = new_slide(title=f"{idx}. Plano {plan_name}")
        add_text(s, 0.6, 1.0, 12, 0.8, f"Plano {plan_name}", size=36, bold=True, color=DARK)
        add_text(s, 0.6, 1.9, 12, 0.8, plan_data["tagline"], size=16, color=SLATE)
        add_text(s, 0.6, 3.0, 12, 0.5, f"{len(features)} funcionalidades detalhadas nos próximos slides ↓",
                 size=14, color=PRIMARY)
        # slides de features — 5 por slide
        chunks = [features[i:i + 5] for i in range(0, len(features), 5)]
        for k, chunk in enumerate(chunks):
            s = new_slide(title=f"{idx}. Plano {plan_name}  ·  {k+1}/{len(chunks)}")
            for j, (name, desc) in enumerate(chunk):
                y = 1.1 + j * 1.15
                add_text(s, 0.6, y, 12, 0.5, "▸ " + name, size=18, bold=True, color=PRIMARY)
                add_text(s, 0.9, y + 0.5, 11.8, 0.6, desc, size=12, color=DARK)

    # ---- COMPARAÇÃO DE PLANOS ----
    s = new_slide(title="6. Comparação de planos")
    matrix = [
        ["Funcionalidade", "Particulares", "Premium", "Pro", "Pro Business"],
        ["Estimativa texto/voz/foto", "●", "●", "●", "●"],
        ["Coach IA obras", "●", "●", "●", "●"],
        ["Calculadoras + DIY", "●", "●", "●", "●"],
        ["Estudo plantas DWG/DXF/PDF", "—", "●", "●", "●"],
        ["Medição 2D interativa", "—", "●", "●", "●"],
        ["Notificações Push", "—", "●", "●", "●"],
        ["Biblioteca pessoal editável", "—", "—", "●", "●"],
        ["Orçamentos + faturas", "—", "—", "●", "●"],
        ["CRM + portal cliente", "—", "—", "●", "●"],
        ["Envio email Resend", "—", "—", "●", "●"],
        ["Multi-utilizador empresa", "—", "—", "—", "●"],
        ["Marketplace + leads", "—", "—", "—", "●"],
        ["EInvoicing Factur-X PT", "—", "—", "—", "●"],
        ["API + HR + Appro", "—", "—", "—", "●"],
    ]
    rows = len(matrix); cols = 5
    tbl = s.shapes.add_table(rows, cols, Inches(0.4), Inches(1.0), Inches(12.5), Inches(6.0)).table
    for r, row in enumerate(matrix):
        for cix, val in enumerate(row):
            cell = tbl.cell(r, cix)
            cell.text = val
            for p in cell.text_frame.paragraphs:
                for run in p.runs:
                    run.font.size = Pt(11)
                    run.font.name = "Calibri"
                    if r == 0:
                        run.font.bold = True; run.font.color.rgb = hex_rgb("#ffffff")
                    elif val == "●":
                        run.font.bold = True; run.font.color.rgb = hex_rgb(PRIMARY)
                    elif val == "—":
                        run.font.color.rgb = hex_rgb(SLATE)
                    else:
                        run.font.color.rgb = hex_rgb(DARK)
            if r == 0:
                cell.fill.solid(); cell.fill.fore_color.rgb = hex_rgb(PRIMARY)

    # ---- BLOG ----
    s = new_slide(title="7. Blog & prospetos regionais")
    add_text(s, 0.6, 1.0, 12, 0.6,
             "Landings regionais SEO PT (Lisboa · Porto · Algarve · Interior) + artigos técnicos:",
             size=15, color=DARK)
    for j, (titulo, resumo) in enumerate(BLOG_ARTIGOS):
        y = 1.8 + j * 0.8
        add_text(s, 0.6, y, 12, 0.4, "▸ " + titulo, size=15, bold=True, color=PRIMARY)
        add_text(s, 0.9, y + 0.4, 11.8, 0.4, resumo, size=11, color=DARK)

    # ---- INTEGRAÇÕES ----
    chunks_int = [INTEGRACOES[i:i + 6] for i in range(0, len(INTEGRACOES), 6)]
    for k, chunk in enumerate(chunks_int):
        s = new_slide(title=f"8. Integrações  ·  {k+1}/{len(chunks_int)}")
        for j, (name, desc) in enumerate(chunk):
            y = 1.1 + j * 0.95
            add_text(s, 0.6, y, 12, 0.4, "▸ " + name, size=17, bold=True, color=PRIMARY)
            add_text(s, 0.9, y + 0.42, 11.8, 0.5, desc, size=12, color=DARK)

    # ---- ROADMAP ----
    s = new_slide(title="9. Roadmap 2026")
    for j, (name, desc) in enumerate(ROADMAP):
        y = 1.0 + j * 0.75
        add_text(s, 0.6, y, 12, 0.4, "▸ " + name, size=16, bold=True, color=ORANGE)
        add_text(s, 0.9, y + 0.38, 11.8, 0.4, desc, size=11, color=DARK)

    # ---- CONTRA-CAPA ----
    s = new_slide(cover=True)
    add_text(s, 0.6, 2.5, 12, 1, "Da planta ao orçamento", size=54, bold=True, color=PRIMARY, align="center")
    add_text(s, 0.6, 3.4, 12, 1, "em minutos.", size=54, bold=True, color="#ffffff", align="center")
    add_text(s, 0.6, 5.0, 12, 0.5, "construpilot.pt   ·   info@construpilot.pt",
             size=18, color=SLATE, align="center")
    add_text(s, 0.6, 6.9, 12, 0.4,
             f"© 2026 ConstruPilot. Documento gerado a {datetime.now().strftime('%d/%m/%Y')}.",
             size=10, color=SLATE, align="center")

    prs.save(str(PPTX_PATH))


def main():
    build_pdf()
    print(f"PDF: {PDF_PATH} ({PDF_PATH.stat().st_size:,} bytes)")
    build_pptx()
    print(f"PPTX: {PPTX_PATH} ({PPTX_PATH.stat().st_size:,} bytes)")


if __name__ == "__main__":
    main()
