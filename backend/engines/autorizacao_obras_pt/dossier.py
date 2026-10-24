"""Geração do processo de autorização de obras: requerimento, memória, ficha estatística,
estimativa + PDF único e ZIP com peças separadas.

Os modelos de requerimento são municipais (não há PDF nacional único descarregável), pelo
que o formato é gerado de raiz com reportlab, seguindo a estrutura padrão. Cada PDF inclui
a nota: «Documento preparado a partir do formato padrão; verificar com o município
destinatário antes da submissão.»
"""
from __future__ import annotations

import io
import os
import zipfile
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas as rl_canvas
from reportlab.platypus import (
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)
from reportlab.lib import colors
from pypdf import PdfReader, PdfWriter

VERSION = "dossier-1.0.1"

# Fontes TrueType embebidas (Inter, licença SIL OFL — engines/bet_core/fonts): o Helvetica padrão do PDF não
# garante «²», «º» e acentos em todos os leitores. Repli Helvetica se a fonte faltar.
from pathlib import Path as _Path
from reportlab.pdfbase import pdfmetrics as _pm
from reportlab.pdfbase.ttfonts import TTFont as _TTF
_FONTES = _Path(__file__).resolve().parent.parent / "bet_core" / "fonts"
try:
    _pm.registerFont(_TTF("AO", str(_FONTES / "Inter_400Regular.ttf")))
    _pm.registerFont(_TTF("AOB", str(_FONTES / "Inter_600SemiBold.ttf")))
    _pm.registerFontFamily("AO", normal="AO", bold="AOB", italic="AO", boldItalic="AOB")
    F, FB = "AO", "AOB"
except Exception:  # noqa: BLE001
    F, FB = "Helvetica", "Helvetica-Bold"

TIPOS_OBRA = {"moradia_nova": "Construção nova — moradia", "ampliacao": "Ampliação", "anexo": "Anexo / construção secundária",
              "interiores": "Obras de alteração no interior", "piscina": "Piscina", "muro": "Muro / vedação",
              "demolicao": "Demolição", "fachada": "Alteração de fachada", "alteracao_uso": "Alteração de utilização"}
TECNICOS = {"arquiteto": "Arquiteto(a)", "engenheiro_estruturas": "Engenheiro(a) de estruturas",
            "engenheiro_civil": "Engenheiro(a) civil", "engenheiro_eletrotecnico": "Engenheiro(a) eletrotécnico(a)",
            "engenheiro_civil_ou_eletrotecnico": "Engenheiro(a) civil ou eletrotécnico(a)",
            "coordenador_projeto": "Coordenador(a) de projeto"}


def _num(v, casas: int = 1) -> str:
    """Número em formato português (vírgula decimal, espaço nos milhares)."""
    try:
        x = float(v or 0)
    except (TypeError, ValueError):
        return str(v)
    s = f"{x:,.{casas}f}".replace(",", " ").replace(".", ",")
    return s[:-(casas + 1)] if casas and s.endswith("," + "0" * casas) else s

NOTA_RODAPE = (
    "Documento preparado a partir do formato padrão da operação urbanística. "
    "A responsabilidade legal é do requerente e dos técnicos subscritores. "
    "Confirmar com o município destinatário antes da submissão."
)


# --------------------------------------------------------------------------- helpers

def _now_iso_pt() -> str:
    d = datetime.now(timezone.utc)
    return d.strftime("%d/%m/%Y")


def _styles() -> Dict[str, ParagraphStyle]:
    base = getSampleStyleSheet()
    return {
        "title": ParagraphStyle("t", parent=base["Title"], fontName=FB,
                                fontSize=16, leading=20, alignment=1, spaceAfter=10),
        "h2": ParagraphStyle("h2", parent=base["Heading2"], fontName=FB,
                             fontSize=12, leading=14, spaceBefore=10, spaceAfter=4),
        "body": ParagraphStyle("b", parent=base["BodyText"], fontName=F,
                               fontSize=10, leading=14, alignment=4),
        "small": ParagraphStyle("s", parent=base["BodyText"], fontName=F,
                                fontSize=8, leading=10, textColor=colors.grey),
        "field": ParagraphStyle("f", parent=base["BodyText"], fontName=F,
                                fontSize=10, leading=14),
    }


def _footer(c: rl_canvas.Canvas, doc) -> None:
    c.saveState()
    c.setFont(F, 7)
    c.setFillGray(0.4)
    text = f"ConstruPilot · Processo preparado em {_now_iso_pt()} · {VERSION}"
    c.drawString(15 * mm, 10 * mm, text)
    c.drawRightString(A4[0] - 15 * mm, 10 * mm, f"Pág. {c.getPageNumber()}")
    from ..identidade_pt import faixa_azulejo
    faixa_azulejo(c, 0, A4[1] - 5 * mm, A4[0], 5 * mm)   # identidade .pt
    c.restoreState()


def _build_pdf(story: List[Any]) -> bytes:
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, title="ConstruPilot",
                            leftMargin=18 * mm, rightMargin=18 * mm,
                            topMargin=18 * mm, bottomMargin=18 * mm)
    doc.build(story, onFirstPage=_footer, onLaterPages=_footer)
    return buf.getvalue()


# --------------------------------------------------------------------------- memória

MEMORIA_FALLBACK = (
    "A presente memória descritiva refere-se à operação urbanística identificada no "
    "requerimento, a executar na morada indicada pelo requerente. A obra respeita os "
    "parâmetros do PDM eficaz para a zona, bem como o regulamento municipal aplicável. "
    "Os materiais e soluções construtivas a adotar correspondem aos usos correntes e às "
    "boas práticas da construção civil em Portugal, garantindo o cumprimento das exigências "
    "regulamentares de segurança estrutural, segurança contra incêndio, salubridade, "
    "acústica, térmica, acessibilidades e eficiência energética. Da obra não resulta impacto "
    "significativo sobre o espaço público nem alteração do uso do imóvel."
)


async def gerar_memoria_descritiva(respostas: Dict[str, Any], diagnostico: Dict[str, Any]) -> str:
    """Chama o LLM do pod via Emergent Universal Key. Em caso de falha ou falta de chave,
    devolve um texto neutro completo (fallback) para o PDF nunca ir vazio."""
    api_key = os.environ.get("EMERGENT_LLM_KEY")
    if not api_key:
        return MEMORIA_FALLBACK
    try:
        from emergentintegrations.llm.chat import LlmChat, UserMessage  # type: ignore

        campos = []
        for k in ("tipo_obra", "concelho", "freguesia", "altura_m", "area_implantacao_m2",
                  "area_construcao_total_m2", "area_construcao_criada_m2", "subtipo_muro",
                  "confina_via_publica", "zona_protegida", "imovel_classificado",
                  "altera_fachada", "altera_cobertura", "altera_uso"):
            v = respostas.get(k)
            if v in (None, "", 0, 0.0, False):
                continue
            campos.append(f"- {k}: {v}")
        system = (
            "És um técnico de projeto de arquitetura em Portugal e redigires textos técnicos para "
            "requerimentos de autorização de obras. Escreve EXCLUSIVAMENTE em Português Europeu "
            "(nunca brasileiro, nunca francês). Tom profissional, impessoal, sem floreios."
        )
        prompt = (
            "Redige a MEMÓRIA DESCRITIVA E JUSTIFICATIVA de uma operação urbanística em Portugal, "
            "entre 250 e 450 palavras, com secções numeradas:\n"
            "1. Identificação e localização\n"
            "2. Descrição da obra\n"
            "3. Áreas e dimensões\n"
            "4. Soluções construtivas e materiais\n"
            "5. Conformidade com o PDM e regulamento municipal\n"
            "6. Impacto urbanístico\n\n"
            f"Procedimento aplicável: {diagnostico.get('procedimento')}\n"
            f"Fundamento legal: {diagnostico.get('fundamento_legal')}\n"
            f"Dados declarados:\n" + "\n".join(campos) + "\n\n"
            "Regras: NÃO inventes parâmetros do PDM nem valores que não estejam acima; "
            "quando faltar informação, escreve «a confirmar pelo requerente». "
            "Devolve APENAS o texto da memória, sem cabeçalho de email, sem markdown."
        )
        chat = (
            LlmChat(api_key=api_key, session_id=f"autorizacao-{int(datetime.now().timestamp())}",
                    system_message=system)
            .with_model("anthropic", "claude-sonnet-4-5-20250929")
            .with_params(max_tokens=1500)
        )
        resp = chat.send_message(UserMessage(text=prompt))
        if hasattr(resp, "__await__"):
            import asyncio
            resp = await resp
        text = str(resp).strip()
        return text or MEMORIA_FALLBACK
    except Exception:  # noqa: BLE001
        return MEMORIA_FALLBACK


# --------------------------------------------------------------------------- estimativa

PRECO_M2 = {
    "anexo": (450, 900),
    "muro": (120, 250),
    "interiores": (300, 700),
    "piscina": (900, 1600),
    "ampliacao": (900, 1500),
    "moradia_nova": (1000, 1800),
    "outro": (600, 1200),
}

PRAZOS_PROC_SEMANAS = {
    "isento": {"instrucao": 1, "obra_min": 4, "obra_max": 24},
    "comunicacao_previa": {"instrucao": 3, "obra_min": 8, "obra_max": 36},
    "licenciamento": {"instrucao": 12, "obra_min": 16, "obra_max": 52},
}


def estimativa_e_calendario(respostas: Dict[str, Any], diagnostico: Dict[str, Any]) -> Dict[str, Any]:
    tipo = respostas.get("tipo_obra", "outro")
    area_ref = (respostas.get("area_construcao_total_m2") or respostas.get("area_construcao_criada_m2")
                or respostas.get("area_implantacao_m2") or 0.0)
    try:
        area_ref = float(area_ref)
    except Exception:  # noqa: BLE001
        area_ref = 0.0
    lo, hi = PRECO_M2.get(tipo, PRECO_M2["outro"])
    custo_min = round(lo * area_ref)
    custo_max = round(hi * area_ref)
    proc = diagnostico.get("procedimento") or "licenciamento"
    cal = PRAZOS_PROC_SEMANAS.get(proc, PRAZOS_PROC_SEMANAS["licenciamento"])
    return {
        "area_ref_m2": area_ref,
        "preco_min_m2": lo,
        "preco_max_m2": hi,
        "custo_min_eur": custo_min,
        "custo_max_eur": custo_max,
        "calendario": {
            "instrucao_semanas": cal["instrucao"],
            "obra_semanas_min": cal["obra_min"],
            "obra_semanas_max": cal["obra_max"],
        },
    }


# --------------------------------------------------------------------------- checklist

CHECKLIST_BASE = {
    "isento": [
        "Informação sobre o início dos trabalhos (art.º 80.º-A do RJUE)",
        "Levantamento fotográfico do local",
    ],
    "comunicacao_previa": [
        "Comunicação prévia (modelo oficial)",
        "Memória descritiva e justificativa",
        "Projeto de arquitetura",
        "Projetos de especialidades",
        "Termos de responsabilidade (art.º 10.º do RJUE)",
        "Levantamento topográfico",
        "Planta de localização e de implantação",
    ],
    "licenciamento": [
        "Requerimento de licença (modelo oficial)",
        "Memória descritiva e justificativa",
        "Projeto de arquitetura",
        "Projetos de especialidades (estabilidade, redes, SCIE, acústica, térmico)",
        "Termos de responsabilidade (art.º 10.º do RJUE)",
        "Levantamento topográfico",
        "Planta de localização e de implantação",
        "Ficha de elementos estatísticos (INE)",
        "Estimativa orçamental",
    ],
}


def checklist_pecas(diagnostico: Dict[str, Any], pecas_carregadas: List[str]) -> Dict[str, Any]:
    proc = diagnostico.get("procedimento") or "licenciamento"
    exigidas = list(CHECKLIST_BASE.get(proc, CHECKLIST_BASE["licenciamento"]))
    exigidas.extend(diagnostico.get("pecas_necessarias") or [])
    seen = set()
    unicas = []
    for p in exigidas:
        if p not in seen:
            seen.add(p); unicas.append(p)
    exigidas = unicas
    import unicodedata as _ud
    def _norm(s: str) -> str:
        s = _ud.normalize("NFKD", s or "").encode("ascii", "ignore").decode("ascii")
        return s.lower().strip()
    carregadas_norm = [_norm(p) for p in (pecas_carregadas or []) if p]
    status = []
    for p in exigidas:
        pn = _norm(p)
        ok = any(c and (c in pn or pn in c) for c in carregadas_norm)
        status.append({"peca": p, "carregada": ok})
    em_falta = [s["peca"] for s in status if not s["carregada"]]
    return {"procedimento": proc, "pecas": status, "em_falta": em_falta,
            "total": len(exigidas), "carregadas": len(exigidas) - len(em_falta)}


# --------------------------------------------------------------------------- PDFs

def _kv_table(rows: List[List[str]]) -> Table:
    k = ParagraphStyle("kv", fontName=F, fontSize=9.5, leading=12)
    kb = ParagraphStyle("kvb", parent=k, fontName=FB)
    rows = [[Paragraph(str(a), kb), Paragraph(str(b), k)] for a, b in rows]   # quebra de linha: sem sobreposição
    t = Table(rows, colWidths=[62 * mm, 103 * mm])
    t.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, -1), F),
        ("FONTSIZE", (0, 0), (-1, -1), 9.5),
        ("ROWBACKGROUNDS", (0, 0), (-1, -1), [colors.whitesmoke, colors.white]),
        ("BOX", (0, 0), (-1, -1), 0.4, colors.lightgrey),
        ("INNERGRID", (0, 0), (-1, -1), 0.3, colors.lightgrey),
        ("FONTNAME", (0, 0), (0, -1), FB),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    return t


def construir_requerimento_pdf(respostas: Dict[str, Any], diagnostico: Dict[str, Any],
                               requerente: Dict[str, Any] | None = None) -> bytes:
    s = _styles()
    requerente = requerente or {}
    proc = (diagnostico.get("procedimento") or "licenciamento").replace("_", " ")
    story: List[Any] = [
        Paragraph("REQUERIMENTO DE AUTORIZAÇÃO DE OBRAS", s["title"]),
        Paragraph(f"<b>Procedimento aplicável:</b> {proc.upper()}", s["body"]),
        Spacer(1, 4 * mm),

        Paragraph("1. Identificação do requerente", s["h2"]),
        _kv_table([
            ["Nome", requerente.get("nome") or "— a preencher —"],
            ["NIF", requerente.get("nif") or "— a preencher —"],
            ["Morada", requerente.get("morada") or "— a preencher —"],
            ["Telefone / E-mail", f"{requerente.get('telefone','') or '—'} / {requerente.get('email','') or '—'}"],
        ]),
        Spacer(1, 4 * mm),

        Paragraph("2. Identificação do local da obra", s["h2"]),
        _kv_table([
            ["Concelho", respostas.get("concelho") or "— a preencher —"],
            ["Freguesia", respostas.get("freguesia") or "— a preencher —"],
            ["Zona de proteção / imóvel classificado",
             "Sim" if (respostas.get("zona_protegida") or respostas.get("imovel_classificado")) else "Não"],
        ]),
        Spacer(1, 4 * mm),

        Paragraph("3. Descrição da operação urbanística", s["h2"]),
        _kv_table([
            ["Tipo", TIPOS_OBRA.get(respostas.get("tipo_obra"), (respostas.get("tipo_obra") or "—").replace("_", " "))],
            ["Área de implantação (m²)", _num(respostas.get("area_implantacao_m2"), 2)],
            ["Área de construção total (m²)", _num(respostas.get("area_construcao_total_m2"), 2)],
            ["Área de construção criada (m²)", _num(respostas.get("area_construcao_criada_m2"), 2)],
            ["Altura (m)", _num(respostas.get("altura_m"), 2)],
        ]),
        Spacer(1, 4 * mm),

        Paragraph("4. Fundamento legal", s["h2"]),
        Paragraph(diagnostico.get("fundamento_legal") or "—", s["body"]),
        Spacer(1, 4 * mm),

        Paragraph("5. Técnicos subscritores (termos de responsabilidade)", s["h2"]),
        _kv_table([[TECNICOS.get(t, t.replace("_", " ").capitalize()), "— a preencher —"]
                   for t in (diagnostico.get("tecnicos_obrigatorios") or [])] or [["—", "—"]]),
        Spacer(1, 6 * mm),
        Paragraph("Pede deferimento, " + _now_iso_pt(), s["body"]),
        Spacer(1, 12 * mm),
        Paragraph("_______________________________________________", s["body"]),
        Paragraph("Assinatura do requerente", s["small"]),
        Spacer(1, 6 * mm),
        Paragraph(NOTA_RODAPE, s["small"]),
    ]
    return _build_pdf(story)


def construir_memoria_pdf(memoria_texto: str, respostas: Dict[str, Any]) -> bytes:
    s = _styles()
    story: List[Any] = [
        Paragraph("MEMÓRIA DESCRITIVA E JUSTIFICATIVA", s["title"]),
        Spacer(1, 4 * mm),
    ]
    for par in (memoria_texto or MEMORIA_FALLBACK).split("\n"):
        p = par.strip()
        if not p:
            story.append(Spacer(1, 2 * mm)); continue
        if p[:2] in ("1.", "2.", "3.", "4.", "5.", "6.", "7.", "8.", "9."):
            story.append(Paragraph(f"<b>{p}</b>", s["body"]))
        else:
            story.append(Paragraph(p, s["body"]))
    story += [Spacer(1, 8 * mm), Paragraph(NOTA_RODAPE, s["small"])]
    return _build_pdf(story)


def construir_ficha_estatistica_pdf(respostas: Dict[str, Any], diagnostico: Dict[str, Any]) -> bytes:
    s = _styles()
    story: List[Any] = [
        Paragraph("FICHA DE ELEMENTOS ESTATÍSTICOS (INE)", s["title"]),
        Paragraph("Modelo compatível com o inquérito 1696 do INE", s["small"]),
        Spacer(1, 4 * mm),
        _kv_table([
            ["Tipo de operação", (respostas.get("tipo_obra") or "—").replace("_", " ")],
            ["Procedimento", (diagnostico.get("procedimento") or "—").replace("_", " ")],
            ["Concelho", respostas.get("concelho") or "—"],
            ["Freguesia", respostas.get("freguesia") or "—"],
            ["N.º de pisos acima do solo", "— a preencher —"],
            ["N.º de alojamentos", "— a preencher —"],
            ["Área de implantação (m²)", str(respostas.get("area_implantacao_m2") or 0)],
            ["Área de construção total (m²)", str(respostas.get("area_construcao_total_m2") or 0)],
            ["Área de construção criada (m²)", str(respostas.get("area_construcao_criada_m2") or 0)],
            ["Uso principal previsto", "— a preencher —"],
        ]),
        Spacer(1, 6 * mm),
        Paragraph(NOTA_RODAPE, s["small"]),
    ]
    return _build_pdf(story)


def construir_estimativa_pdf(estimativa: Dict[str, Any]) -> bytes:
    s = _styles()
    cal = estimativa.get("calendario") or {}
    story: List[Any] = [
        Paragraph("ESTIMATIVA ORÇAMENTAL E CALENDARIZAÇÃO", s["title"]),
        Spacer(1, 4 * mm),
        Paragraph("1. Estimativa de custo", s["h2"]),
        _kv_table([
            ["Área de referência (m²)", str(estimativa.get("area_ref_m2") or 0)],
            ["Preço indicativo (€/m²)",
             f"{estimativa.get('preco_min_m2','?')} – {estimativa.get('preco_max_m2','?')}"],
            ["Custo total estimado (€)",
             f"{estimativa.get('custo_min_eur',0):,}".replace(",", " ")
             + " — "
             + f"{estimativa.get('custo_max_eur',0):,}".replace(",", " ")],
        ]),
        Spacer(1, 4 * mm),
        Paragraph("2. Calendarização indicativa", s["h2"]),
        _kv_table([
            ["Instrução do processo (semanas)", str(cal.get("instrucao_semanas") or "—")],
            ["Duração da obra — mínimo (semanas)", str(cal.get("obra_semanas_min") or "—")],
            ["Duração da obra — máximo (semanas)", str(cal.get("obra_semanas_max") or "—")],
        ]),
        Spacer(1, 6 * mm),
        Paragraph("Os valores indicados são estimativas de ordem de grandeza, não substituem orçamento "
                  "confirmado por profissional e podem variar com o PDM, materiais escolhidos e condições do mercado.",
                  s["small"]),
        Spacer(1, 4 * mm),
        Paragraph(NOTA_RODAPE, s["small"]),
    ]
    return _build_pdf(story)


# --------------------------------------------------------------------------- merge + zip

def _merge_pdfs(pdfs: List[bytes]) -> bytes:
    writer = PdfWriter()
    for b in pdfs:
        try:
            r = PdfReader(io.BytesIO(b))
            for page in r.pages:
                writer.add_page(page)
        except Exception:  # noqa: BLE001
            continue
    out = io.BytesIO(); writer.write(out)
    return out.getvalue()


def _criar_zip(ficheiros: Dict[str, bytes]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for nome, b in ficheiros.items():
            z.writestr(nome, b)
    return buf.getvalue()


# --------------------------------------------------------------------------- orquestração

async def gerar_dossier(respostas: Dict[str, Any], diagnostico: Dict[str, Any],
                        pecas_carregadas: Optional[List[Dict[str, Any]]] = None,
                        requerente: Optional[Dict[str, Any]] = None,
                        memoria_override: Optional[str] = None) -> Dict[str, Any]:
    """Gera todo o processo. Devolve bytes dos PDFs + metadados."""
    pecas_carregadas = pecas_carregadas or []
    memoria = memoria_override or await gerar_memoria_descritiva(respostas, diagnostico)
    estimativa = estimativa_e_calendario(respostas, diagnostico)
    cl = checklist_pecas(diagnostico, [p.get("nome", "") for p in pecas_carregadas])

    pdfs: Dict[str, bytes] = {
        "01_requerimento.pdf": construir_requerimento_pdf(respostas, diagnostico, requerente),
        "02_memoria_descritiva.pdf": construir_memoria_pdf(memoria, respostas),
        "03_ficha_estatistica.pdf": construir_ficha_estatistica_pdf(respostas, diagnostico),
        "04_estimativa_custo.pdf": construir_estimativa_pdf(estimativa),
    }
    for i, p in enumerate(pecas_carregadas, 5):
        nome = p.get("nome") or f"peca_{i}.bin"
        b = p.get("bytes") or b""
        if b:
            pdfs[f"{i:02d}_{nome}"] = b

    pdf_unico = _merge_pdfs([v for k, v in pdfs.items() if k.endswith(".pdf")])
    zip_bytes = _criar_zip(pdfs)

    return {
        "version": VERSION,
        "pdf_unico": pdf_unico,
        "zip": zip_bytes,
        "memoria_texto": memoria,
        "checklist": cl,
        "estimativa": estimativa,
        "ficheiros": list(pdfs.keys()),
    }
