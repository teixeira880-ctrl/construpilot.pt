"""Redator de Caderno de Encargos / processo de concurso — ConstruPilot Portugal.

Produz um Caderno de Encargos (cláusulas técnicas) completo, por capítulos, à maneira portuguesa : capa com o logótipo,
índice, condições técnicas gerais, condições de execução de cada capítulo, descrição dos trabalhos com localização e
artigos quantificáveis ; mais o Mapa de Quantidades de Trabalho em Excel com a mesma numeração, e as peças do concurso
(capa e índice do processo, programa de concurso, cláusulas gerais), reunidos num ZIP.

Modos : « empreitada geral » (um só caderno com todos os capítulos, prática corrente em Portugal) ou
« empreitada por lotes » (um caderno por capítulo / lote).

Fiabilidade :
- a base (condições, documentos de referência, artigos tipo) é determinística : cctp_catalogue ;
- a IA (Claude) adapta e completa os artigos ao projeto, em JSON estrito, em português europeu ;
- verificação após redação : qualquer norma / diploma citado que não esteja na lista branca do catálogo é retirado
  e assinalado ; nenhuma quantidade é aceite se não vier dos dados introduzidos ou do orçamento ;
- se a IA falhar, o caderno é redigido só a partir do catálogo (nunca uma página em branco).
"""
from __future__ import annotations

import base64
import io
import json
import logging
import re
import unicodedata
import zipfile
from datetime import date

from engines.cctp_catalogue import A_CHARGE, COMMUNES, LOTS, LOTS_PAR_CODE, RENOVATION
from engines.cctp_pieces import articles_par_piece

logger = logging.getLogger(__name__)

VERT = "1F4E4A"
CUIVRE = "B87333"
CREME = "F7F1E8"
IA_TIMEOUT_S = 150.0          # por capítulo : acima disto, redação a partir do catálogo


# ---------------------------------------------------------------------------------------------
# Utilitários de texto
# ---------------------------------------------------------------------------------------------
def _fold(s: str) -> str:
    return unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode().lower()


def _num(x) -> float | None:
    try:
        v = float(str(x).replace(",", ".").replace(" ", ""))
    except (TypeError, ValueError):
        return None
    return round(v, 2) if v > 0 else None


# Normas (NP, NP EN, EN, ISO), diplomas (Decreto-Lei, Decreto Regulamentar, Portaria, Lei, Regulamento UE) e Eurocódigos.
_REF_RE = re.compile(
    r"\b(?:NP\s+)?EN(?:\s+ISO)?\s+\d+(?:-\d+)*|\bNP\s+\d+(?:-\d+)*|\bISO\s+\d+(?:-\d+)*"
    r"|\b(?:Decreto-Lei|Decreto\s+Regulamentar|Portaria|Lei)\s+n\.?\s*[º°o]\s*\d+(?:-[A-Z])?/\d{2,4}"
    r"|\bRegulamento\s+\(UE\)\s+(?:n\.?\s*[º°o]\s*)?\d+/\d+|\bEuroc[óo]digo\s+\d+|\bLNEC\s+E\s*\d+", re.I)


def _norm_ref(r: str) -> str:
    r = _fold(r)
    for a, b in (("n.o", ""), ("no ", ""), ("n.", ""), (" ", ""), ("-", ""), ("np", "")):
        r = r.replace(a, b)
    return r


def _whitelist() -> set[str]:
    out = set()
    textos = [ref for lot in LOTS for ref in lot["refs"]] + [t for _, t in COMMUNES] + [RENOVATION[1]]
    textos += [t for lot in LOTS for _, items in lot["prescriptions"] for _, t in items]
    for ref in textos:
        for m in _REF_RE.finditer(ref):
            out.add(_norm_ref(m.group(0)))
    return out


WHITELIST = _whitelist()


def verifier_references(texte: str) -> tuple[str, list[str]]:
    """Retira as normas / diplomas ausentes da lista branca. Devolve (texto corrigido, referências retiradas)."""
    retirees: list[str] = []

    def _sub(m):
        ref = m.group(0)
        if _norm_ref(ref) in WHITELIST:
            return ref
        retirees.append(ref.strip())
        return "a regulamentação aplicável"
    return _REF_RE.sub(_sub, texte or ""), retirees


# ---------------------------------------------------------------------------------------------
# Seleção : capítulo e artigo para uma linha livre ou uma linha de orçamento
# ---------------------------------------------------------------------------------------------
def _score(txt: str, mots: list[str]) -> int:
    best = 0
    for k in mots:
        kk = _fold(k)
        if re.search(r"\b" + re.escape(kk), txt):
            best = max(best, len(kk))
    return best


def lot_pour(designation: str, description: str = "") -> str | None:
    txt = _fold(f"{designation} {description}")
    best, code = 0, None
    for lot in LOTS:
        mots = list(lot["motscles"]) + [m for o in lot["ouvrages"] for m in o["motscles"]]
        s = _score(txt, mots)
        if lot["code"] == "gros_oeuvre":        # « parede » aparece também em « azulejo em paredes », « pintura de paredes »…
            s -= 1
        if s > best:
            best, code = s, lot["code"]
    return code


def ouvrage_pour(lot: dict, designation: str, description: str = "") -> str | None:
    txt = _fold(f"{designation} {description}")
    best, code = 0, None
    for o in lot["ouvrages"]:
        s = _score(txt, o["motscles"] + [o["titre"]])
        if s > best:
            best, code = s, o["code"]
    return code


def selection_depuis_devis(lines: list[dict]) -> list[dict]:
    """Converte as linhas de um orçamento ConstruPilot em seleção de capítulos / artigos, com quantidades."""
    lots: dict[str, dict] = {}
    for ln in lines or []:
        if ln.get("kind", "line") != "line" or not ln.get("designation"):
            continue
        code = lot_pour(ln.get("designation", ""), ln.get("description") or "")
        if not code:
            continue
        sel = lots.setdefault(code, {"code": code, "ouvrages": [], "lignes": []})
        sel["lignes"].append({"designation": str(ln["designation"])[:200], "detail": str(ln.get("description") or "")[:400],
                              "unite": str(ln.get("unit") or "")[:10], "quantite": _num(ln.get("qty")),
                              "localisation": ""})
    order = [l["code"] for l in LOTS]
    return [lots[c] for c in order if c in lots]


# ---------------------------------------------------------------------------------------------
# Artigos
# ---------------------------------------------------------------------------------------------
def _article_catalogue(o: dict, localisation: str = "") -> dict:
    return {"chapitre": o["chapitre"], "titre": o["titre"], "description": o["description"],
            "localisation": localisation or "Conforme peças desenhadas.", "code": o["code"], "source": "catalogue",
            "variantes": [{"libelle": v, "unite": o["unite"], "quantite": None} for v in o["variantes"]]}


# Artigos tipo substituídos pelos artigos « por divisão » quando é fornecido um programa de divisões.
REMPLACES_PAR_PIECES = {"prises", "eclairage", "tableau", "rj45", "wc", "lavabo", "douche", "evier"}


def articles_de_base(lot: dict, sel: dict, exclure: set[str] | None = None) -> list[dict]:
    """Artigos determinísticos : artigos tipo escolhidos + linhas introduzidas (ligadas a um artigo tipo quando possível)."""
    arts: dict[str, dict] = {}
    for code in sel.get("ouvrages") or []:
        o = next((x for x in lot["ouvrages"] if x["code"] == code), None)
        if o:
            arts[code] = _article_catalogue(o)
    libres: list[dict] = []
    for ln in sel.get("lignes") or []:
        des = (ln.get("designation") or "").strip()
        if not des:
            continue
        var = {"libelle": des, "unite": (ln.get("unite") or "").strip() or "un", "quantite": _num(ln.get("quantite"))}
        oc = ln.get("ouvrage") or ouvrage_pour(lot, des, ln.get("detail") or "")
        o = next((x for x in lot["ouvrages"] if x["code"] == oc), None)
        if o:
            art = arts.get(oc)
            if not art:
                art = _article_catalogue(o, ln.get("localisation") or "")
                art["variantes"] = []
                art["source"] = "devis"
                arts[oc] = art
            elif ln.get("localisation") and art["localisation"] == "Conforme peças desenhadas.":
                art["localisation"] = ln["localisation"]
            art["variantes"].append(var)
        else:
            libres.append({"chapitre": "Trabalhos complementares", "titre": des.upper()[:120],
                           "description": (ln.get("detail") or "").strip() or
                           f"Fornecimento e aplicação de : {des}, de acordo com os documentos de referência do capítulo e as "
                           "instruções dos fabricantes, incluindo todos os trabalhos acessórios de execução e acabamento.",
                           "localisation": ln.get("localisation") or "Conforme peças desenhadas.", "code": None, "source": "saisie",
                           "variantes": [var]})
    order = {o["code"]: i for i, o in enumerate(lot["ouvrages"])}
    out = sorted(arts.values(), key=lambda a: order.get(a["code"], 999)) + libres
    if not out:                                 
        out = [_article_catalogue(o) for o in lot["ouvrages"] if o["code"] not in (exclure or set())]
    return out


def lot_compose(sel: dict) -> dict:
    """Capítulo do catálogo, ou capítulo agrupado (ex. « Acabamentos interiores » = gesso cartonado + carpintarias + pinturas + pavimentos)."""
    codes = [sel["code"]] + [c for c in (sel.get("inclure") or []) if c in LOTS_PAR_CODE and c != sel["code"]]
    lots = [LOTS_PAR_CODE[c] for c in codes]
    base = lots[0]
    if len(lots) == 1:
        return {**base, "titre": (sel.get("titre") or base["titre"]).strip(), "codes": codes,
                "a_charge": list(A_CHARGE.get(base["code"], []))}
    refs, presc, ouvrages, mots, charge = [], [], [], [], []
    for l in lots:
        refs += [r for r in l["refs"] if r not in refs]
        presc += [(f"{chap} — {l['titre']}", items) for chap, items in l["prescriptions"]]
        ouvrages += l["ouvrages"]
        mots += l["motscles"]
        charge += [x for x in A_CHARGE.get(l["code"], []) if x not in charge]
    return {"code": base["code"], "numero": base["numero"], "codes": codes, "refs": refs, "prescriptions": presc,
            "ouvrages": ouvrages, "motscles": mots, "a_charge": charge,
            "titre": (sel.get("titre") or " – ".join(l["titre"].split(" – ")[0] for l in lots)).strip()}


def _quantites_saisies(sel: dict) -> set[float]:
    return {q for q in (_num(l.get("quantite")) for l in sel.get("lignes") or []) if q}


async def rediger_lot_ia(lot: dict, projet: dict, sel: dict, articles: list[dict]) -> tuple[list[dict], list[tuple[str, str]], list[str]]:
    """O Claude adapta os artigos ao projeto. Devolve (artigos, condições complementares, pontos a verificar)."""
    from engines import ai
    system = (ai.BRAND + " És medidor-orçamentista e redator de cadernos de encargos em Portugal. Redige artigos de "
              "caderno de encargos precisos, em português europeu (norma de Portugal, nunca do Brasil), no futuro, no estilo "
              "das condições técnicas portuguesas (« Fornecimento e aplicação de … », « Inclui … », « Localização : … »), "
              "com a terminologia portuguesa da construção (betonilha, caixilharia, alvenaria, laje, rodapé, azulejo…). "
              "Devolve APENAS JSON válido.")
    base = [{k: a[k] for k in ("chapitre", "titre", "description", "localisation", "variantes")} for a in articles]
    prompt = (
        f"PROJETO : {json.dumps({k: projet.get(k) for k in ('nom', 'adresse', 'nature', 'description')}, ensure_ascii=False)}\n"
        f"CAPÍTULO {sel.get('numero') or lot['numero']} — {lot['titre']}\n"
        f"Documentos de referência AUTORIZADOS (não cites nenhum outro) : {json.dumps(lot['refs'], ensure_ascii=False)}\n"
        f"Instruções do redator para este capítulo : {(sel.get('notes') or 'nenhuma')[:2000]}\n\n"
        f"ARTIGOS DE BASE (a manter, adaptar ao projeto e completar) :\n{json.dumps(base, ensure_ascii=False)[:30000]}\n\n"
        "Devolve APENAS este JSON : {\n"
        '  "articles": [ { "chapitre": "subcapítulo", "titre": "TÍTULO EM MAIÚSCULAS", "description": "texto completo do artigo : '
        'materiais, características, execução, trabalhos incluídos", "localisation": "…",\n'
        '      "variantes": [ { "libelle": "…", "unite": "m2|ml|m3|un|vg", "quantite": número ou null } ] } ],\n'
        '  "prescriptions_complementaires": [ { "titre": "…", "texte": "…" } ],\n'
        '  "points_a_verifier": [ "informação em falta ou hipótese assumida, a validar pela fiscalização" ]\n'
        "}\n"
        "Regras : mantém TODOS os artigos de base e as suas variantes (mesmas designações e quantidades). Não cries "
        "quantidades : deixa null se não forem fornecidas. Não inventes marcas, preços nem desempenhos numéricos que "
        "dependam de um projeto (térmico, acústico, estabilidade) : escreve « conforme projeto de … ». As condições "
        "complementares (0 a 4) dizem respeito apenas a este projeto e não repetem as generalidades. Português europeu "
        "profissional, sem markdown, unidades portuguesas (m2, ml, m3, un, vg)."
    )
    data = ai._json(await ai._complete(system, prompt, feature="cctp_redaction"), {})
    if not isinstance(data, dict) or not data.get("articles"):
        raise ValueError("resposta IA vazia")
    permises = _quantites_saisies(sel)
    out = []
    for a in data["articles"][:60]:
        titre = str(a.get("titre") or "").strip()[:160]
        desc = str(a.get("description") or "").strip()[:4000]
        if not titre or len(desc) < 30:
            continue
        vars_ = []
        for v in (a.get("variantes") or [])[:15]:
            lib = str(v.get("libelle") or "").strip()[:200]
            if not lib:
                continue
            q = _num(v.get("quantite"))
            vars_.append({"libelle": lib, "unite": str(v.get("unite") or "un")[:10], "quantite": q if q in permises else None})
        out.append({"chapitre": str(a.get("chapitre") or "Trabalhos")[:120], "titre": titre.upper(), "description": desc,
                    "localisation": str(a.get("localisation") or "Conforme peças desenhadas.")[:600], "source": "ia", "code": None,
                    "variantes": vars_ or [{"libelle": titre.capitalize(), "unite": "un", "quantite": None}]})
    # Salvaguarda : um artigo de base perdido pela IA é reintegrado tal como está.
    titres = {_fold(a["titre"]) for a in out}
    for a in articles:
        if _fold(a["titre"]) not in titres:
            out.append(a)
    presc = [(str(p.get("titre") or "")[:120], str(p.get("texte") or "")[:2000])
             for p in (data.get("prescriptions_complementaires") or [])[:4] if p.get("titre") and p.get("texte")]
    points = [str(p)[:300] for p in (data.get("points_a_verifier") or [])[:15] if p]
    return out, presc, points


def _verifier_articles(articles: list[dict], presc: list[tuple[str, str]]) -> tuple[list[dict], list[tuple[str, str]], list[str]]:
    retirees: list[str] = []
    for a in articles:
        for k in ("description", "localisation"):
            a[k], r = verifier_references(a[k])
            retirees += r
    out_p = []
    for t, x in presc:
        x, r = verifier_references(x)
        retirees += r
        out_p.append((t, x))
    msgs = [f"Referência não verificada retirada do texto : « {r} »" for r in dict.fromkeys(retirees)]
    return articles, out_p, msgs


# ---------------------------------------------------------------------------------------------
# Redação de um processo
# ---------------------------------------------------------------------------------------------
async def rediger(projet: dict, selection: list[dict], ia: bool = True) -> list[dict]:
    """Redige cada capítulo. Devolve a lista dos capítulos redigidos (estrutura pronta para DOCX / mapa de quantidades)."""
    fusion: dict[str, dict] = {}
    hote = {c: s_["code"] for s_ in selection for c in (s_.get("inclure") or [])}   # capítulo incluído → capítulo agrupado
    for sel in sorted(selection, key=lambda x: 0 if x.get("inclure") else 1):
        code = hote.get(sel.get("code"), sel.get("code"))   # o mesmo capítulo escolhido duas vezes (orçamento + introdução) é fundido
        if code not in fusion:
            fusion[code] = {**sel, "ouvrages": list(sel.get("ouvrages") or []), "lignes": list(sel.get("lignes") or [])}
        else:
            f = fusion[code]
            f["ouvrages"] += [o for o in sel.get("ouvrages") or [] if o not in f["ouvrages"]]
            f["lignes"] += list(sel.get("lignes") or [])
            f["notes"] = "\n".join(x for x in (f.get("notes"), sel.get("notes")) if x)
            f["numero"] = f.get("numero") or sel.get("numero")
    import asyncio
    sem = asyncio.Semaphore(4)

    pieces = projet.get("pieces") or []

    async def _un(sel: dict) -> dict | None:
        if sel.get("code") not in LOTS_PAR_CODE:
            return None
        lot = lot_compose(sel)
        numero = int(sel.get("numero") or lot["numero"])
        par_piece = bool(pieces) and any(c in lot["codes"] for c in ("electricite", "plomberie"))
        articles = articles_de_base(lot, sel, REMPLACES_PAR_PIECES if par_piece else None)
        presc: list[tuple[str, str]] = []
        points: list[str] = []
        mode = "catalogue"
        if ia and articles:
            try:
                async with sem:
                    articles, presc, points = await asyncio.wait_for(
                        rediger_lot_ia(lot, projet, {**sel, "numero": numero}, articles), IA_TIMEOUT_S)
                mode = "ia"
            except Exception as exc:  # noqa: BLE001 — repli catalogue, jamais de CCTP vide
                logger.warning("caderno: redação IA indisponível para %s (%s), recurso ao catálogo", lot["code"], exc)
                points.append("Redação assistida indisponível : caderno elaborado a partir dos artigos tipo ConstruPilot.")
        articles, presc, msgs = _verifier_articles(articles, presc)
        # Equipamento por divisão (quantidades por regra, fora da IA) para eletricidade e águas e esgotos.
        for code in lot["codes"]:
            articles += articles_par_piece(code, pieces)
        sans_qte = sum(1 for a in articles for v in a["variantes"] if v["quantite"] is None)
        if sans_qte:
            points.append(f"{sans_qte} linha(s) do mapa de quantidades sem quantidade : a medir ou a deixar à medição dos concorrentes.")
        if par_piece:
            points.append("Equipamento por divisão : base estabelecida a partir do programa introduzido, a confrontar com os projetos de eletricidade / águas e esgotos.")
        return {"code": lot["code"], "codes": lot["codes"], "numero": numero, "titre": lot["titre"], "refs": lot["refs"],
                "prescriptions": lot["prescriptions"], "a_charge": lot["a_charge"], "complementaires": presc,
                "articles": articles, "points": points + msgs, "mode": mode}

    rediges = [r for r in await asyncio.gather(*(_un(s) for s in fusion.values())) if r]
    rediges.sort(key=lambda r: r["numero"])
    if not any(s_.get("numero") for s_ in selection):     # sem numeração imposta : capítulos numerados seguidos (1, 2, 3…)
        for i, r in enumerate(rediges, 1):
            r["numero"] = i
    return rediges


# ---------------------------------------------------------------------------------------------
# Numeração comum caderno de encargos / mapa de quantidades
# ---------------------------------------------------------------------------------------------
def numeroter(lot: dict) -> list[dict]:
    """Subcapítulos de descrição (N.2, N.3…), artigos N.c.a, variantes N.c.a.v."""
    n = lot["numero"]
    chapitres: dict[str, list[dict]] = {}
    for a in lot["articles"]:
        chapitres.setdefault(a["chapitre"], []).append(a)
    out = []
    for ci, (chap, arts) in enumerate(chapitres.items(), 2):
        c = {"num": f"{n}.{ci}", "titre": chap, "articles": []}
        for ai_, a in enumerate(arts, 1):
            num_a = f"{c['num']}.{ai_}"
            c["articles"].append({**a, "num": num_a,
                                  "variantes": [{**v, "num": f"{num_a}.{vi}"} for vi, v in enumerate(a["variantes"], 1)]})
        out.append(c)
    return out


# ---------------------------------------------------------------------------------------------
# DOCX
# ---------------------------------------------------------------------------------------------
def _field(run, instr: str):
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn
    for kind, text in (("begin", None), (None, instr), ("separate", None), (None, "…"), ("end", None)):
        if kind:
            el = OxmlElement("w:fldChar")
            el.set(qn("w:fldCharType"), kind)
            run._r.append(el)
        elif text == instr:
            el = OxmlElement("w:instrText")
            el.set(qn("xml:space"), "preserve")
            el.text = instr
            run._r.append(el)
        else:
            el = OxmlElement("w:t")
            el.text = text
            run._r.append(el)


def _shade(cell, hex_):
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn
    tc = cell._tc.get_or_add_tcPr()
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:color"), "auto")
    shd.set(qn("w:fill"), hex_)
    tc.append(shd)


def _logo(branding: dict | None):
    raw = (branding or {}).get("logo_b64")
    if not raw:
        return None
    try:
        return io.BytesIO(base64.b64decode(raw.split(",", 1)[-1]))
    except Exception:  # noqa: BLE001
        return None


INTERVENANTS = [("architecte", "Arquiteto / coordenador de projeto"), ("bet_structure", "Projeto de estabilidade"),
                ("bet_fluides", "Projetos de redes e instalações"), ("bet_thermique", "Projeto de comportamento térmico"),
                ("coordonnateur_sps", "Coordenador de segurança em obra"), ("controleur_technique", "Fiscalização")]

NATUREZA = {"neuf": "Construção nova", "renovation": "Reabilitação / remodelação"}
NATUREZA_DE = {"neuf": "a construção", "renovation": "a reabilitação"}
LIMITE_FICHEIRO = "Clique com o botão direito no índice e escolha « Atualizar campo » para atualizar a paginação."


def intervenants(projet: dict) -> list[tuple[str, str]]:
    iv = projet.get("intervenants") or {}
    return [(lib, str(iv[k]).strip()) for k, lib in INTERVENANTS if str(iv.get(k) or "").strip()]


def _novo_doc():
    from docx import Document
    from docx.shared import Cm, Pt, RGBColor
    doc = Document()
    sec = doc.sections[0]
    sec.page_height, sec.page_width = Cm(29.7), Cm(21.0)
    sec.left_margin = sec.right_margin = Cm(2.0)
    sec.top_margin, sec.bottom_margin = Cm(2.0), Cm(1.8)
    st = doc.styles["Normal"]
    st.font.name, st.font.size = "Calibri", Pt(10)
    st.paragraph_format.space_after = Pt(4)
    for lvl, size, color in ((1, 14, VERT), (2, 12, VERT), (3, 11, CUIVRE), (4, 10, VERT)):
        h = doc.styles[f"Heading {lvl}"]
        h.font.name, h.font.size, h.font.bold = "Calibri", Pt(size), True
        h.font.color.rgb = RGBColor.from_string(color)
        h.paragraph_format.space_before = Pt(10 if lvl < 3 else 6)
        h.paragraph_format.keep_with_next = True
    return doc


def _capa(doc, projet: dict, subtitulo: str, branding: dict | None):
    """Capa, índice e secção do corpo com cabeçalho / rodapé."""
    from docx.enum.section import WD_SECTION
    from docx.enum.table import WD_TABLE_ALIGNMENT
    from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_BREAK
    from docx.shared import Cm, Pt, RGBColor

    vert = RGBColor.from_string(VERT)
    societe = (branding or {}).get("company_name") or projet.get("redacteur") or ""
    logo = _logo(branding)
    if logo:
        try:
            doc.add_picture(logo, height=Cm(2.2))
        except Exception:  # noqa: BLE001 — logótipo ilegível : continua sem ele
            pass
    for _ in range(3):
        doc.add_paragraph()
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r = p.add_run((projet.get("nom") or "Projeto").upper())
    r.bold, r.font.size, r.font.color.rgb = True, Pt(20), vert
    if projet.get("adresse"):
        doc.add_paragraph(projet["adresse"]).alignment = WD_ALIGN_PARAGRAPH.CENTER
    doc.add_paragraph()
    t = doc.add_table(rows=1, cols=1)
    t.alignment = WD_TABLE_ALIGNMENT.CENTER
    c = t.rows[0].cells[0]
    _shade(c, VERT)
    cp = c.paragraphs[0]
    cp.alignment = WD_ALIGN_PARAGRAPH.CENTER
    rr = cp.add_run("CADERNO DE ENCARGOS")
    rr.bold, rr.font.size, rr.font.color.rgb = True, Pt(26), RGBColor(0xFF, 0xFF, 0xFF)
    cp2 = c.add_paragraph()
    cp2.alignment = WD_ALIGN_PARAGRAPH.CENTER
    rr = cp2.add_run("Cláusulas técnicas — Condições técnicas especiais")
    rr.font.size, rr.font.color.rgb = Pt(13), RGBColor(0xFF, 0xFF, 0xFF)
    cp3 = c.add_paragraph()
    cp3.alignment = WD_ALIGN_PARAGRAPH.CENTER
    rr = cp3.add_run(subtitulo.upper())
    rr.bold, rr.font.size, rr.font.color.rgb = True, Pt(14), RGBColor.from_string(CREME)
    doc.add_paragraph()
    info = [("Dono de obra", projet.get("maitre_ouvrage")), ("Autor do projeto", projet.get("maitre_oeuvre")),
            ("Natureza da obra", NATUREZA.get(projet.get("nature"), projet.get("nature"))),
            *intervenants(projet),
            ("Fase", projet.get("phase") or "Concurso"), ("Revisão", projet.get("indice") or "A"),
            ("Data", projet.get("date") or date.today().strftime("%d/%m/%Y")), ("Elaborado por", societe)]
    info = [(k, v) for k, v in info if v]
    tb = doc.add_table(rows=len(info), cols=2)
    tb.style = "Table Grid"
    tb.alignment = WD_TABLE_ALIGNMENT.CENTER
    for i, (k, v) in enumerate(info):
        a, b = tb.rows[i].cells
        a.width, b.width = Cm(5.5), Cm(10)
        _shade(a, CREME)
        a.paragraphs[0].add_run(k).bold = True
        b.paragraphs[0].add_run(str(v))
    doc.add_paragraph().add_run().add_break(WD_BREAK.PAGE)
    doc.add_heading("ÍNDICE", 1)
    _field(doc.add_paragraph().add_run(), 'TOC \\o "1-3" \\h \\z \\u')
    doc.add_paragraph(LIMITE_FICHEIRO).runs[0].italic = True
    body = doc.add_section(WD_SECTION.NEW_PAGE)
    body.header.is_linked_to_previous = False
    body.footer.is_linked_to_previous = False
    hr = body.header.paragraphs[0].add_run(f"{projet.get('nom') or 'Projeto'} — Caderno de Encargos — {subtitulo}")
    hr.font.size, hr.font.color.rgb = Pt(8), vert
    fp = body.footer.paragraphs[0]
    fp.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    pe = f"Documento elaborado por {societe} — " if societe and projet.get("style") == "architecte" else ""
    fr = fp.add_run(f"{pe}{projet.get('phase') or 'Concurso'} — Revisão {projet.get('indice') or 'A'}    Página ")
    fr.font.size = Pt(8)
    _field(fp.add_run(), "PAGE")
    fp.add_run(" / ").font.size = Pt(8)
    _field(fp.add_run(), "NUMPAGES")


def _comuns(projet: dict) -> list[tuple[str, str]]:
    communes = list(COMMUNES)
    if projet.get("nature") == "renovation":
        communes.insert(2, RENOVATION)
    if projet.get("tce"):
        communes.insert(0, ("Cláusulas gerais",
                            "O empreiteiro é considerado conhecedor e aceita sem reservas as Cláusulas gerais do caderno de "
                            "encargos e o Programa de concurso que integram o processo, os quais completam as presentes "
                            "condições técnicas."))
    return communes


def _par(doc, texto: str):
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    doc.add_paragraph(texto).alignment = WD_ALIGN_PARAGRAPH.JUSTIFY


def _corpo_capitulo(doc, projet: dict, lot: dict, com_comuns: bool = True):
    """Condições do capítulo (N.1) e descrição dos trabalhos (N.2 …)."""
    from docx.enum.text import WD_BREAK
    from docx.shared import Pt, RGBColor

    n = lot["numero"]
    archi = projet.get("style") == "architecte"
    if not com_comuns:                      # caderno único : título do capítulo
        doc.add_heading(f"{n}. {lot['titre'].upper()}", 1)
    doc.add_heading(f"{n}.1 {'GENERALIDADES' if archi else 'CONDIÇÕES TÉCNICAS ESPECIAIS'}", 1 if com_comuns else 2)
    lvl2, lvl3 = (2, 3) if com_comuns else (3, 4)
    doc.add_heading(f"{n}.1.1 {'OBJETO E ÂMBITO DOS TRABALHOS' if archi else 'GENERALIDADES'}", lvl2)
    k = 1
    doc.add_heading(f"{n}.1.1.{k} Objeto", lvl3)
    lugar = f", sita em {projet['adresse']}" if projet.get("adresse") else ""
    titulo = lot["titre"] if lot["titre"][1:2].isupper() else lot["titre"][:1].lower() + lot["titre"][1:]   # mantém siglas (AVAC)
    _par(doc, f"O presente capítulo descreve os trabalhos de {titulo} a executar no âmbito de "
              f"{NATUREZA_DE.get(projet.get('nature'), 'a execução')} da obra « {projet.get('nom') or 'Projeto'} »{lugar}.")
    if com_comuns and projet.get("description"):
        _par(doc, projet["description"])
    pieces = projet.get("pieces") or []
    if com_comuns and pieces:
        _par(doc, "O programa compreende : " + ", ".join(p.get("nom") or "" for p in pieces if p.get("nom")) + ".")
    if com_comuns and projet.get("maitre_oeuvre"):
        _par(doc, f"Os trabalhos serão executados de acordo com o projeto de : {projet['maitre_oeuvre']}.")
    k += 1
    doc.add_heading(f"{n}.1.1.{k} Natureza dos trabalhos", lvl3)
    doc.add_paragraph("Os trabalhos do presente capítulo compreendem, nomeadamente :")
    for chap in dict.fromkeys(a_["chapitre"] for a_ in lot["articles"]):
        doc.add_paragraph(chap, style="List Bullet")
    if com_comuns:
        for titre, texte in _comuns(projet):
            k += 1
            doc.add_heading(f"{n}.1.1.{k} {titre}", lvl3)
            _par(doc, texte)
    k += 1
    doc.add_heading(f"{n}.1.1.{k} Documentos de referência do capítulo", lvl3)
    doc.add_paragraph("Além dos documentos referidos nas condições gerais, os trabalhos do presente capítulo cumprirão, nomeadamente :")
    for ref in lot["refs"]:
        doc.add_paragraph(ref, style="List Bullet")
    if lot.get("a_charge"):
        k += 1
        doc.add_heading(f"{n}.1.1.{k} Trabalhos incluídos no presente capítulo", lvl3)
        doc.add_paragraph("Ficam a cargo do presente capítulo, incluídos nos respetivos preços :")
        for x in lot["a_charge"]:
            doc.add_paragraph(x, style="List Bullet")
    if lot["complementaires"]:
        k += 1
        doc.add_heading(f"{n}.1.1.{k} Disposições próprias do projeto", lvl3)
        for titre, texte in lot["complementaires"]:
            pp = doc.add_paragraph()
            pp.add_run(f"{titre}. ").bold = True
            pp.add_run(texte)
    for ci, (chap, items) in enumerate(lot["prescriptions"], 2):
        doc.add_heading(f"{n}.1.{ci} {chap.upper()}", lvl2)
        for ii, (titre, texte) in enumerate(items, 1):
            doc.add_heading(f"{n}.1.{ci}.{ii} {titre}", lvl3)
            _par(doc, texte)

    label = "Localização : "
    cuivre = RGBColor.from_string(CUIVRE)
    for ci, chap in enumerate(numeroter(lot)):
        if archi and com_comuns and ci == 0:
            doc.add_paragraph().add_run().add_break(WD_BREAK.PAGE)
            r_ = doc.add_paragraph().add_run("DESCRIÇÃO DOS TRABALHOS")
            r_.bold, r_.font.size, r_.font.color.rgb = True, Pt(16), RGBColor.from_string(VERT)
        doc.add_heading(f"{chap['num']} {chap['titre'].upper()}", 1 if com_comuns else 2)
        for a in chap["articles"]:
            doc.add_heading(f"{a['num']} {a['titre']}", 2 if com_comuns else 3)
            for ligne in a["description"].split("\n"):
                if ligne.startswith("- "):
                    doc.add_paragraph(ligne[2:], style="List Bullet")
                elif ligne.strip():
                    _par(doc, ligne)
            pl = doc.add_paragraph()
            pl.add_run(label).bold = True
            pl.add_run(a["localisation"])
            for v in ([] if a.get("source") == "pieces" else a["variantes"]):   # por divisão : a lista basta, o mapa detalha
                hv = doc.add_heading(f"{v['num']} {v['libelle']}", 4)
                hv.runs[0].font.size = Pt(10)
                q = f"{v['quantite']:g} {v['unite']}" if v["quantite"] else v["unite"]
                rm = doc.add_paragraph().add_run(f"Quantidade = {q}" if v["quantite"] else f"Unidade de medição : {q}")
                rm.italic, rm.font.size, rm.font.color.rgb = True, Pt(9), cuivre


def cctp_docx(projet: dict, lot: dict, branding: dict | None = None) -> bytes:
    """Caderno de encargos de um capítulo / lote (empreitada por lotes)."""
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    doc = _novo_doc()
    _capa(doc, projet, f"Capítulo {lot['numero']:02d} — {lot['titre']}", branding)
    _corpo_capitulo(doc, projet, lot, com_comuns=True)
    doc.add_paragraph()
    fim = doc.add_paragraph(f"Fim das condições técnicas do capítulo {lot['numero']:02d} — {lot['titre']}.")
    fim.alignment = WD_ALIGN_PARAGRAPH.CENTER
    fim.runs[0].italic = True
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


def caderno_docx(projet: dict, lots: list[dict], branding: dict | None = None) -> bytes:
    """Caderno de encargos único (empreitada geral) : condições técnicas gerais uma só vez, depois cada capítulo."""
    from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_BREAK
    doc = _novo_doc()
    _capa(doc, projet, "Empreitada geral — todos os capítulos", branding)
    doc.add_heading("0. CONDIÇÕES TÉCNICAS GERAIS", 1)
    doc.add_heading("0.1 Objeto do caderno de encargos", 2)
    lugar = f", sita em {projet['adresse']}" if projet.get("adresse") else ""
    _par(doc, f"O presente caderno de encargos define as condições técnicas de {NATUREZA_DE.get(projet.get('nature'), 'a execução')} "
              f"da obra « {projet.get('nom') or 'Projeto'} »{lugar}, executada em regime de empreitada geral.")
    if projet.get("description"):
        _par(doc, projet["description"])
    if projet.get("pieces"):
        _par(doc, "O programa compreende : " + ", ".join(p.get("nom") or "" for p in projet["pieces"] if p.get("nom")) + ".")
    if projet.get("maitre_oeuvre"):
        _par(doc, f"Os trabalhos serão executados de acordo com o projeto de : {projet['maitre_oeuvre']}.")
    doc.add_heading("0.2 Capítulos da empreitada", 2)
    for l in lots:
        doc.add_paragraph(f"Capítulo {l['numero']:02d} — {l['titre']}", style="List Bullet")
    for i, (titre, texte) in enumerate(_comuns(projet), 3):
        doc.add_heading(f"0.{i} {titre}", 2)
        _par(doc, texte)
    for l in lots:
        doc.add_paragraph().add_run().add_break(WD_BREAK.PAGE)
        _corpo_capitulo(doc, projet, l, com_comuns=False)
    doc.add_paragraph()
    fim = doc.add_paragraph("Fim do caderno de encargos — condições técnicas.")
    fim.alignment = WD_ALIGN_PARAGRAPH.CENTER
    fim.runs[0].italic = True
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


# ---------------------------------------------------------------------------------------------
# Mapa de quantidades de trabalho (mesma numeração)
# ---------------------------------------------------------------------------------------------
def dpgf_cadre_xlsx(projet: dict, lots: list[dict]) -> bytes:
    import openpyxl
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side

    wb = openpyxl.Workbook()
    wb.remove(wb.active)
    thin = Side(style="thin", color="BFBFBF")
    border = Border(left=thin, right=thin, top=thin, bottom=thin)
    head_fill, lot_fill, chap_fill = PatternFill("solid", fgColor=VERT), PatternFill("solid", fgColor=CREME), PatternFill("solid", fgColor="EFE7DA")
    eur = '#,##0.00 "€"'
    recap = []
    for lot in lots:
        ws = wb.create_sheet(f"Cap. {lot['numero']:02d}"[:31])
        ws.append([f"Mapa de quantidades de trabalho — {projet.get('nom') or 'Projeto'}"])
        ws["A1"].font = Font(bold=True, size=13, color=VERT)
        ws.append([f"Capítulo {lot['numero']:02d} — {lot['titre']}  ·  numeração do caderno de encargos"])
        ws.append(["As quantidades indicadas são estimativas : o concorrente verifica as medições sob sua responsabilidade."])
        ws["A3"].font = Font(italic=True, size=9)
        ws.append([])
        ws.append(["Art.º", "Designação", "Un.", "Quant.", "Preço unitário (€)", "Total (€)"])
        for c in ws[5]:
            c.font, c.fill, c.border = Font(bold=True, color="FFFFFF"), head_fill, border
        linhas = []
        for chap in numeroter(lot):
            ws.append([chap["num"], chap["titre"].upper()])
            for c in ws[ws.max_row]:
                c.fill, c.font = chap_fill, Font(bold=True)
            for a in chap["articles"]:
                ws.append([a["num"], a["titre"]])
                ws.cell(ws.max_row, 2).font = Font(bold=True, color=VERT)
                for v in a["variantes"]:
                    r = ws.max_row + 1
                    ws.append([v["num"], v["libelle"], v["unite"], v["quantite"], None, f"=IF(AND(ISNUMBER(D{r}),ISNUMBER(E{r})),D{r}*E{r},0)"])
                    ws.cell(r, 5).number_format = ws.cell(r, 6).number_format = eur
                    for c in ws[r]:
                        c.border = border
                    linhas.append(r)
        ws.append([])
        r = ws.max_row + 1
        soma = "+".join(f"F{x}" for x in linhas) or "0"
        ws.append(["", f"TOTAL DO CAPÍTULO {lot['numero']:02d} (sem IVA)", "", "", "", f"={soma}" if len(linhas) < 200 else f"=SUM(F6:F{r - 1})"])
        ws.cell(r, 2).font = ws.cell(r, 6).font = Font(bold=True)
        ws.cell(r, 6).number_format = eur
        for col, w in zip("ABCDEF", (11, 70, 8, 11, 16, 16)):
            ws.column_dimensions[col].width = w
        for row in ws.iter_rows(min_row=6, max_col=2, min_col=2):
            for c in row:
                c.alignment = Alignment(wrap_text=True, vertical="top")
        ws.freeze_panes = "A6"
        recap.append((lot, ws.title, r))
    rs = wb.create_sheet("Resumo", 0)
    rs.append([f"Resumo do mapa de quantidades — {projet.get('nom') or 'Projeto'}"])
    rs["A1"].font = Font(bold=True, size=13, color=VERT)
    rs.append([])
    rs.append(["Cap.", "Designação", "Total (€)"])
    for c in rs[3]:
        c.font, c.fill = Font(bold=True, color="FFFFFF"), head_fill
    for lot, title, r in recap:
        rs.append([f"{lot['numero']:02d}", lot["titre"], f"='{title}'!F{r}"])
        rs.cell(rs.max_row, 3).number_format = eur
        rs.cell(rs.max_row, 1).fill = lot_fill
    n = rs.max_row
    rs.append(["", "TOTAL (sem IVA)", f"=SUM(C4:C{n})"])
    rs.append(["", "IVA (taxa aplicável a indicar pelo concorrente)", None])
    rs.append(["", "TOTAL COM IVA", f"=C{n + 1}+C{n + 2}"])
    for i in (n + 1, n + 3):
        rs.cell(i, 2).font = rs.cell(i, 3).font = Font(bold=True)
    for i in (n + 1, n + 2, n + 3):
        rs.cell(i, 3).number_format = eur
    for col, w in zip("ABC", (8, 60, 18)):
        rs.column_dimensions[col].width = w
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


# ---------------------------------------------------------------------------------------------
# Processo de concurso
# ---------------------------------------------------------------------------------------------
def _slug(s: str) -> str:
    from engines.nom_fichier import ascii_texte
    s = re.sub(r"[^A-Za-z0-9]+", "-", ascii_texte(s)).strip("-")
    return s[:50] or "Projeto"


def note_verification(projet: dict, lots: list[dict]) -> str:
    lines = [f"Nota de verificação — Caderno de encargos {projet.get('nom') or 'Projeto'}", "",
             "Documento interno do redator (não juntar ao processo de concurso). O caderno de encargos deve ser revisto e "
             "validado pelo autor do projeto.", ""]
    for lot in lots:
        lines.append(f"Capítulo {lot['numero']:02d} — {lot['titre']} (redação : {'assistida por IA' if lot['mode'] == 'ia' else 'artigos tipo'})")
        lines += [f"  - {p}" for p in lot["points"]] or ["  - Nenhum ponto assinalado."]
        lines.append("")
    return "\n".join(lines)


def fichiers_dossier(projet: dict, lots: list[dict], branding: dict | None = None) -> list[tuple[str, bytes, str]]:
    """Ficheiros do processo : peças do concurso (se pedidas), caderno(s) de encargos .docx, mapa de quantidades .xlsx, nota."""
    from engines import dce_pieces as DP
    docx_mime = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    nom = _slug(projet.get("nom") or "Projeto")
    out = []
    if projet.get("tce"):
        out.append((f"00_Capa-e-indice-do-processo_{nom}.docx", DP.page_garde_docx(projet, lots, branding), docx_mime))
        out.append((f"PC_Programa-de-concurso_{nom}.docx", DP.rc_docx(projet, lots, branding), docx_mime))
        out.append((f"CE_Clausulas-gerais_{nom}.docx", DP.clauses_tce_docx(projet, lots, branding), docx_mime))
    if projet.get("par_lots"):
        for lot in lots:
            out.append((f"CE_Cap-{lot['numero']:02d}_{_slug(lot['titre'])}_{nom}.docx", cctp_docx(projet, lot, branding), docx_mime))
    else:
        out.append((f"CE_Condicoes-tecnicas_{nom}.docx", caderno_docx(projet, lots, branding), docx_mime))
    out.append((f"MQT_Mapa-de-quantidades_{nom}.xlsx", dpgf_cadre_xlsx(projet, lots),
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"))
    out.append(("Nota-de-verificacao.txt", note_verification(projet, lots).encode("utf-8"), "text/plain; charset=utf-8"))
    return out


def zip_dossier(projet: dict, fichiers: list[tuple[str, bytes, str]]) -> bytes:
    buf = io.BytesIO()
    raiz = f"Concurso_{_slug(projet.get('nom') or 'Projeto')}"
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for name, data, _ in fichiers:
            sub = ("" if name.startswith("Nota") else "1_Pecas-do-procedimento/" if name.startswith(("00_", "PC_"))
                   else "2_Caderno-de-encargos/" if name.startswith("CE_") else "3_Mapa-de-quantidades/")
            z.writestr(f"{raiz}/{sub}{name}", data)
    return buf.getvalue()


def catalogue_public() -> list[dict]:
    return [{"code": l["code"], "numero": l["numero"], "titre": l["titre"], "refs": l["refs"],
             "ouvrages": [{"code": o["code"], "chapitre": o["chapitre"], "titre": o["titre"], "unite": o["unite"]} for o in l["ouvrages"]]}
            for l in LOTS]
