"""Peças do processo de concurso (obra particular) em torno do caderno de encargos — ConstruPilot Portugal.

- Capa e índice do processo : intervenientes, faixa das fases do projeto, peças escritas e desenhadas ;
- Programa de concurso : objeto, peças, esclarecimentos, visita, documentos da proposta, prazos, critério ;
- Caderno de encargos — Cláusulas gerais : regime da empreitada, licenciamento, livro de obra, segurança, prazos,
  trabalhos a mais, medições e pagamentos, receções, garantia, seguros, resíduos, telas finais.

Referências jurídicas limitadas a textos estáveis : Código Civil (art.º 1214.º, 1216.º, 1225.º), RJUE (Decreto-Lei
n.º 555/99), Lei n.º 31/2009 (diretor de obra), Portaria n.º 1268/2008 (livro de obra), Decreto-Lei n.º 273/2003,
Lei n.º 41/2015 (acesso à atividade de construção — IMPIC), Lei n.º 98/2009 (acidentes de trabalho),
Decreto-Lei n.º 102-D/2020 (resíduos), Decreto-Lei n.º 68/2004 (ficha técnica da habitação).
Montantes, prazos, multas e percentagens nunca são inventados : vêm do projeto ou ficam « a fixar no contrato ».
"""
from __future__ import annotations

import io
from datetime import date

from engines.cctp_redacteur import CREME, CUIVRE, NATUREZA_DE, VERT, _field, _logo, _shade, intervenants

PHASES = ["PROGRAMA BASE", "ESTUDO PRÉVIO", "ANTEPROJETO", "LICENCIAMENTO", "PROJETO DE EXECUÇÃO", "CONCURSO", "OBRA", "TELAS FINAIS"]


def _base(projet: dict, titre_piece: str):
    from docx import Document
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.shared import Cm, Pt, RGBColor

    doc = Document()
    sec = doc.sections[0]
    sec.page_height, sec.page_width = Cm(29.7), Cm(21.0)
    sec.left_margin = sec.right_margin = Cm(2.0)
    sec.top_margin, sec.bottom_margin = Cm(2.0), Cm(1.8)
    st = doc.styles["Normal"]
    st.font.name, st.font.size = "Calibri", Pt(10)
    st.paragraph_format.space_after = Pt(4)
    for lvl, size, color in ((1, 14, VERT), (2, 12, VERT), (3, 11, CUIVRE)):
        h = doc.styles[f"Heading {lvl}"]
        h.font.name, h.font.size, h.font.bold = "Calibri", Pt(size), True
        h.font.color.rgb = RGBColor.from_string(color)
        h.paragraph_format.keep_with_next = True
    fp = sec.footer.paragraphs[0]
    fp.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    r = fp.add_run(f"{projet.get('nom') or 'Projeto'} — {titre_piece} — Página ")
    r.font.size = Pt(8)
    _field(fp.add_run(), "PAGE")
    fp.add_run(" / ").font.size = Pt(8)
    _field(fp.add_run(), "NUMPAGES")
    return doc


def _entete(doc, projet: dict, titre: str, sous_titre: str, branding: dict | None):
    from docx.enum.table import WD_TABLE_ALIGNMENT
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.shared import Cm, Pt, RGBColor

    logo = _logo(branding)
    if logo:
        try:
            doc.add_picture(logo, height=Cm(2.0))
        except Exception:  # noqa: BLE001
            pass
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r = p.add_run((projet.get("nom") or "Projeto").upper())
    r.bold, r.font.size, r.font.color.rgb = True, Pt(20), RGBColor.from_string(VERT)
    if projet.get("adresse"):
        doc.add_paragraph(projet["adresse"]).alignment = WD_ALIGN_PARAGRAPH.CENTER
    t = doc.add_table(rows=1, cols=1)
    t.alignment = WD_TABLE_ALIGNMENT.CENTER
    c = t.rows[0].cells[0]
    _shade(c, VERT)
    cp = c.paragraphs[0]
    cp.alignment = WD_ALIGN_PARAGRAPH.CENTER
    rr = cp.add_run(titre)
    rr.bold, rr.font.size, rr.font.color.rgb = True, Pt(22), RGBColor(0xFF, 0xFF, 0xFF)
    if sous_titre:
        c2 = c.add_paragraph()
        c2.alignment = WD_ALIGN_PARAGRAPH.CENTER
        r2 = c2.add_run(sous_titre)
        r2.font.size, r2.font.color.rgb = Pt(12), RGBColor.from_string(CREME)
    doc.add_paragraph()


def _tableau(doc, rows: list[tuple[str, str]]):
    from docx.shared import Cm
    rows = [(k, v) for k, v in rows if v]
    if not rows:
        return
    tb = doc.add_table(rows=len(rows), cols=2)
    tb.style = "Table Grid"
    for i, (k, v) in enumerate(rows):
        a, b = tb.rows[i].cells
        a.width, b.width = Cm(5.5), Cm(11.5)
        _shade(a, CREME)
        a.paragraphs[0].add_run(k).bold = True
        b.paragraphs[0].add_run(str(v))
    doc.add_paragraph()


def _acteurs(projet: dict) -> list[tuple[str, str]]:
    return [("Dono de obra", projet.get("maitre_ouvrage")), ("Autor do projeto", projet.get("maitre_oeuvre")), *intervenants(projet)]


def _save(doc) -> bytes:
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


def _p(doc, texte: str):
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    doc.add_paragraph(texte).alignment = WD_ALIGN_PARAGRAPH.JUSTIFY


def _nome_obra(projet: dict) -> str:
    lugar = f", sita em {projet['adresse']}" if projet.get("adresse") else ""
    return f"{NATUREZA_DE.get(projet.get('nature'), 'a execução')} da obra « {projet.get('nom') or 'Projeto'} »{lugar}"


def liste_pieces(projet: dict, lots: list[dict]) -> list[tuple[str, list[str]]]:
    escritas = ["Programa de concurso", "Caderno de encargos — Cláusulas gerais"]
    if projet.get("par_lots"):
        escritas += [f"Caderno de encargos — Condições técnicas, capítulo {l['numero']:02d} — {l['titre']}" for l in lots]
    else:
        escritas.append("Caderno de encargos — Condições técnicas (capítulos " + ", ".join(f"{l['numero']:02d}" for l in lots) + ")")
    escritas.append("Mapa de quantidades de trabalho (todos os capítulos)")
    desenhadas = [str(x).strip() for x in (projet.get("plans") or []) if str(x).strip()]
    return [("Peças escritas", escritas),
            ("Peças desenhadas", desenhadas or ["Peças desenhadas do projeto de arquitetura e dos projetos de especialidades (lista a completar)"])]


# ---------------------------------------------------------------------------------------------
def page_garde_docx(projet: dict, lots: list[dict], branding: dict | None = None) -> bytes:
    """Capa e índice do processo de concurso."""
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.shared import Pt, RGBColor

    doc = _base(projet, "Capa e índice do processo")
    _entete(doc, projet, "PROCESSO DE CONCURSO", "Empreitada de construção", branding)
    t = doc.add_table(rows=1, cols=len(PHASES))
    t.style = "Table Grid"
    fase = (projet.get("phase") or "Concurso").upper()
    for i, ph in enumerate(PHASES):
        c = t.rows[0].cells[i]
        run = c.paragraphs[0].add_run(ph)
        run.font.size = Pt(6.5)
        c.paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.CENTER
        if ph == fase:
            _shade(c, CUIVRE)
            run.bold, run.font.color.rgb = True, RGBColor(0xFF, 0xFF, 0xFF)
    doc.add_paragraph()
    _tableau(doc, _acteurs(projet) + [("Data", projet.get("date") or date.today().strftime("%d/%m/%Y")),
                                      ("Revisão", projet.get("indice") or "A")])
    doc.add_heading("ÍNDICE DO PROCESSO", 1)
    num = 1
    for groupe, items in liste_pieces(projet, lots):
        doc.add_heading(groupe, 2)
        for it in items:
            doc.add_paragraph(f"{num:02d}  {it}")
            num += 1
    _p(doc, "As peças desenhadas fazem parte integrante do processo de concurso. Em caso de divergência entre peças, o "
            "concorrente deve assinalá-la por escrito ao autor do projeto antes da apresentação da proposta.")
    return _save(doc)


# ---------------------------------------------------------------------------------------------
def clauses_tce_docx(projet: dict, lots: list[dict], branding: dict | None = None) -> bytes:
    """Caderno de encargos — Cláusulas gerais (obra particular)."""
    doc = _base(projet, "Caderno de encargos — Cláusulas gerais")
    _entete(doc, projet, "CADERNO DE ENCARGOS", "Cláusulas gerais", branding)
    seccoes: list[tuple[str, list[str]]] = [
        ("Objeto", [
            f"O presente caderno de encargos tem por objeto {_nome_obra(projet)}, em regime de empreitada, e define as "
            "cláusulas gerais a incluir no contrato a celebrar entre o dono de obra e o empreiteiro, completadas pelas "
            "condições técnicas de cada capítulo.",
            *([projet["description"]] if projet.get("description") else [])]),
        ("Capítulos da empreitada", [f"Capítulo {l['numero']:02d} — {l['titre']}" for l in lots]),
        ("Regime da empreitada e preço", [
            "A empreitada é por preço global, salvo indicação em contrário no contrato. O empreiteiro, ao apresentar a sua "
            "proposta, declara ter visitado o local, apreciado os acessos, as condicionantes e o volume dos trabalhos, e "
            "estudado todas as peças do processo, não podendo invocar erros ou omissões que não tenha assinalado antes da "
            "apresentação da proposta.",
            "As quantidades do mapa de quantidades de trabalho são indicativas : o concorrente verifica as medições sob sua "
            "responsabilidade."]),
        ("Prevalência das peças", [
            "Em caso de divergência, prevalecem, por esta ordem : o contrato, as presentes cláusulas gerais, as condições "
            "técnicas, as peças desenhadas e o mapa de quantidades, sem prejuízo dos esclarecimentos prestados durante o "
            "concurso."]),
        ("Licenciamento, livro de obra e direção técnica", [
            "O dono de obra assegura o título de controlo prévio da operação urbanística nos termos do Regime Jurídico da "
            "Urbanização e da Edificação (Decreto-Lei n.º 555/99). O empreiteiro mantém em obra o livro de obra (Portaria "
            "n.º 1268/2008) e designa o diretor de obra nos termos da Lei n.º 31/2009."]),
        ("Segurança e saúde no trabalho", [
            "Nos termos do Decreto-Lei n.º 273/2003, o empreiteiro desenvolve e cumpre o Plano de Segurança e Saúde para a "
            "fase de obra, segue as determinações do coordenador de segurança em obra quando designado e assegura as "
            "fichas de procedimentos de segurança dos trabalhos com riscos especiais. A comunicação prévia de abertura de "
            "estaleiro é efetuada quando exigida."]),
        ("Estaleiro", [
            "A montagem, manutenção e desmontagem do estaleiro, as vedações, os acessos e as ligações provisórias de água e "
            "eletricidade ficam a cargo do empreiteiro, de acordo com o capítulo respetivo das condições técnicas."]),
        ("Prazos", [
            f"O prazo de execução da empreitada é de {projet['delai']}." if projet.get("delai") else
            "O prazo de execução e os prazos parciais são fixados no contrato e no plano de trabalhos aprovado.",
            "As multas por incumprimento de prazos, quando previstas, são fixadas no contrato."]),
        ("Alterações e trabalhos a mais ou a menos", [
            "Nenhuma alteração ao projeto nem trabalho a mais será executado sem ordem escrita do dono de obra, com preço e "
            "prazo acordados previamente, nos termos dos artigos 1214.º e 1216.º do Código Civil. Os trabalhos a menos são "
            "deduzidos ao preço com base nos preços unitários da proposta."]),
        ("Medições e pagamentos", [
            "Os trabalhos são medidos em autos de medição contraditórios, com a periodicidade fixada no contrato, e pagos "
            "com base nos preços unitários da proposta. A retenção ou caução de garantia, quando prevista, é fixada no "
            "contrato."]),
        ("Aprovação de materiais", [
            "As fichas técnicas, declarações de desempenho e amostras dos materiais e equipamentos são submetidas à "
            "fiscalização e à escolha do dono de obra antes de qualquer encomenda."]),
        ("Gestão de resíduos e limpeza", [
            "O empreiteiro cumpre o Plano de Prevenção e Gestão de Resíduos de Construção e Demolição e o Decreto-Lei "
            "n.º 102-D/2020, encaminha os resíduos para operadores licenciados com as guias de acompanhamento e entrega a "
            "obra limpa."]),
        ("Receção provisória", [
            "Concluídos os trabalhos, é realizada vistoria conjunta e lavrado auto de receção provisória, com ou sem "
            "reservas. Os defeitos registados são corrigidos pelo empreiteiro no prazo acordado. Antes da vistoria, o "
            "empreiteiro terá realizado os ensaios exigidos e entregue os respetivos relatórios e certificados."]),
        ("Garantia e receção definitiva", [
            "O empreiteiro responde pelos defeitos da obra nos termos do Código Civil ; tratando-se de imóvel destinado a "
            "longa duração, o prazo de garantia é de cinco anos a contar da entrega (artigo 1225.º do Código Civil), salvo "
            "prazo superior fixado no contrato. Findo o prazo de garantia e corrigidos os defeitos, é lavrado auto de "
            "receção definitiva."]),
        ("Habilitação e seguros", [
            "O empreiteiro é titular de alvará ou certificado emitido pelo IMPIC adequado à natureza e ao valor da obra "
            "(Lei n.º 41/2015), e mantém em vigor o seguro de acidentes de trabalho (Lei n.º 98/2009) e um seguro de "
            "responsabilidade civil, comprovados antes da consignação."]),
        ("Telas finais e compilação técnica", [
            "No final da obra, o empreiteiro entrega as telas finais, as fichas técnicas dos produtos aplicados, as "
            "instruções de utilização e manutenção, os termos de responsabilidade e certificados (instalações elétricas, "
            "ITED, gás quando exista) e os elementos para a compilação técnica da obra e para a ficha técnica da habitação "
            "(Decreto-Lei n.º 68/2004), quando aplicável."]),
    ]
    for i, (titre, paras) in enumerate(seccoes, 1):
        doc.add_heading(f"Cláusula {i}.ª — {titre}", 2)
        for x in paras:
            if titre == "Capítulos da empreitada":
                doc.add_paragraph(x, style="List Bullet")
            else:
                _p(doc, x)
    return _save(doc)


# ---------------------------------------------------------------------------------------------
def rc_docx(projet: dict, lots: list[dict], branding: dict | None = None) -> bytes:
    """Programa de concurso (consulta para obra particular)."""
    rc = projet.get("consultation") or {}
    doc = _base(projet, "Programa de concurso")
    _entete(doc, projet, "PROGRAMA DE CONCURSO", "Consulta para empreitada", branding)
    doc.add_heading("Artigo 1.º — Objeto do concurso", 2)
    _p(doc, f"O presente concurso tem por objeto a adjudicação da empreitada de {_nome_obra(projet)}.")
    doc.add_heading("Artigo 2.º — Intervenientes", 2)
    _tableau(doc, _acteurs(projet))
    doc.add_heading("Artigo 3.º — Organização dos trabalhos", 2)
    _p(doc, "A empreitada é organizada nos capítulos seguintes" + (" ; cada lote pode ser adjudicado separadamente, "
            "devendo o concorrente apresentar proposta distinta por lote :" if projet.get("par_lots") else " :"))
    for l in lots:
        doc.add_paragraph(f"Capítulo {l['numero']:02d} — {l['titre']}", style="List Bullet")
    doc.add_heading("Artigo 4.º — Peças do processo", 2)
    for groupe, items in liste_pieces(projet, lots):
        doc.add_paragraph(groupe).runs[0].bold = True
        for it in items:
            doc.add_paragraph(it, style="List Bullet")
    doc.add_heading("Artigo 5.º — Esclarecimentos e erros ou omissões", 2)
    _p(doc, "Os pedidos de esclarecimento e a lista de erros e omissões detetados são apresentados por escrito ao autor do "
            "projeto" + (f" ({projet['maitre_oeuvre']})" if projet.get("maitre_oeuvre") else "") +
            " ; as respostas são comunicadas a todos os concorrentes e passam a integrar o processo.")
    doc.add_heading("Artigo 6.º — Visita ao local", 2)
    _p(doc, rc.get("visite") or "É recomendada a visita ao local, a combinar com o autor do projeto. Não é aceite qualquer "
                                "reclamação baseada no desconhecimento do local.")
    doc.add_heading("Artigo 7.º — Documentos que constituem a proposta", 2)
    for x in ["Declaração de aceitação do conteúdo do caderno de encargos, assinada pelo concorrente",
              "Mapa de quantidades de trabalho integralmente preenchido (preços unitários e totais), datado e assinado",
              "Plano de trabalhos e cronograma financeiro",
              "Memória descritiva e justificativa do modo de execução da obra, com as fichas técnicas dos materiais propostos",
              "Alvará ou certificado do IMPIC adequado à obra (Lei n.º 41/2015)",
              "Certidões de situação contributiva regularizada perante a Segurança Social e a Autoridade Tributária",
              "Apólices ou certificados dos seguros de acidentes de trabalho e de responsabilidade civil",
              "Lista de obras semelhantes realizadas"]:
        doc.add_paragraph(x, style="List Bullet")
    doc.add_heading("Artigo 8.º — Prazo e modo de entrega das propostas", 2)
    prazo = (f"As propostas são entregues até ao dia {rc['date_limite']}" if rc.get("date_limite")
             else "As propostas são entregues até à data indicada no convite")
    _p(doc, prazo + (f", {rc['remise']}." if rc.get("remise") else ", por via eletrónica ao autor do projeto."))
    doc.add_heading("Artigo 9.º — Prazo de validade das propostas", 2)
    _p(doc, f"Os concorrentes ficam obrigados a manter as suas propostas durante {int(rc.get('validite_jours') or 90)} dias a "
            "contar do termo do prazo de entrega.")
    doc.add_heading("Artigo 10.º — Variantes", 2)
    _p(doc, "São admitidas propostas variantes, desde que acompanhadas da proposta base e devidamente justificadas e "
            "orçamentadas em separado." if rc.get("variantes", True) else "Não são admitidas propostas variantes.")
    doc.add_heading("Artigo 11.º — Critério de adjudicação", 2)
    crit = rc.get("criteres") or [("Preço", None), ("Prazo de execução", None), ("Valia técnica da proposta", None)]
    _p(doc, "A adjudicação é feita à proposta economicamente mais vantajosa, tendo em conta os fatores seguintes :")
    for c in crit:
        nom, poids = (c if isinstance(c, (list, tuple)) else (c.get("nom"), c.get("poids")))
        doc.add_paragraph(f"{nom}" + (f" : {poids} %" if poids else ""), style="List Bullet")
    if not any((c[1] if isinstance(c, (list, tuple)) else c.get("poids")) for c in crit):
        _p(doc, "A ponderação dos fatores é fixada pelo dono de obra, que se reserva o direito de negociar com os "
                "concorrentes cujas propostas se revelem mais vantajosas e de não adjudicar.")
    return _save(doc)
