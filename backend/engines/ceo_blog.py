"""Agente CEO — geração de um artigo de blogue SEO (PT-PT).

Usado pelo gerador manual (POST /api/ceo/blog/draft) e pela produção diária
(engines/ceo_daily.py). O artigo é guardado em `autoseo_articles` com
source="ceo_agent" e status="draft"; só é publicado após validação (ou pela
publicação automática, se o administrador a ativar).
"""
from __future__ import annotations

import logging
import os
import re
import secrets
from datetime import datetime, timezone

from starlette.concurrency import run_in_threadpool

from core.db import db
from engines import ceo_media, storage
from engines.ai import _complete, _json
from engines.expenses import cap

log = logging.getLogger("ceo.blog")

SITE_URL = "https://construpilot.pt"
CEO_IMAGE_COST_EUR = float(os.environ.get("CEO_IMAGE_COST_EUR", "0.05"))
CEO_TEXT_COST_EUR = float(os.environ.get("CEO_TEXT_COST_EUR", "0.02"))
MIN_WORDS = int(os.environ.get("CEO_MIN_WORDS", "1100"))

AUDIENCE_LABEL = {"particuliers": "particulares (proprietários e famílias que fazem obras em casa)",
                  "pros": "empreiteiros, técnicos e empresas de construção em Portugal"}

# Ligações internas sugeridas ao modelo (caminhos atuais do site).
INTERNAL_LINKS = {
    "particuliers": [("/estimation", "estimativa gratuita de obras"), ("/coach", "coach IA de obras"),
                     ("/photo", "estimativa a partir de uma fotografia"), ("/calculateurs", "calculadoras de obra"),
                     ("/particuliers", "ConstruPilot para particulares")],
    "pros": [("/pro", "ConstruPilot Pro"), ("/metre", "medições automáticas de plantas"),
             ("/devis", "orçamentos de obra com IVA"), ("/escaliers", "cálculo de escadas"),
             ("/plans-pro", "análise de plantas"), ("/structuro-bet", "pré-dimensionamento estrutural")],
}

# Termos que denunciam conteúdo francês / não aplicável a Portugal.
_FR_TERMS = re.compile(
    r"\b(RE ?2020|DPE|CEE|MaPrimeR[ée]nov|DTU|K-?bis|SIRET|SIREN|d[ée]cennale|TVA|URSSAF|"
    r"permis de construire|devis|chantier|travaux|artisan|Factur-X|Chorus)\b", re.I)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def slugify(text: str) -> str:
    text = (text or "").lower().strip()
    for pat, rep in ((r"[àáâãä]", "a"), (r"[éèêë]", "e"), (r"[íìîï]", "i"), (r"[óòôõö]", "o"),
                     (r"[úùûü]", "u"), (r"ç", "c"), (r"ñ", "n")):
        text = re.sub(pat, rep, text)
    text = re.sub(r"[^a-z0-9]+", "-", text).strip("-")
    return text[:70].strip("-") or "artigo"


async def unique_slug(base: str) -> str:
    slug = base
    if await db.autoseo_articles.find_one({"slug": slug}, {"_id": 1}):
        slug = f"{base}-{secrets.token_hex(3)}"
    return slug


def word_count(html: str) -> int:
    return len(re.sub(r"<[^>]+>", " ", html or "").split())


async def budget_allows() -> tuple[bool, str | None]:
    """Bloqueia só a imagem (não essencial) se o teto de 500 € estiver congelado/ultrapassado."""
    try:
        st = await cap.status()
    except Exception:  # noqa: BLE001
        return True, None
    if st.get("state") in ("exceeded", "frozen"):
        return False, st.get("blocking_reason") or "teto de custos atingido"
    return True, None


def _system(audience: str) -> str:
    aud = AUDIENCE_LABEL.get(audience, AUDIENCE_LABEL["particuliers"])
    return (
        "És o editor-chefe SEO do ConstruPilot, um SaaS de construção para o mercado PORTUGUÊS. "
        f"Escreves para {aud}. Escreves SEMPRE em português europeu (nunca brasileiro: 'casa de banho', "
        "'equipa', 'telemóvel', 'fatura', 'obra', 'empreiteiro', 'orçamento').\n"
        "REGRAS ABSOLUTAS:\n"
        "1. Contexto exclusivamente português: IVA 23 % (taxa normal) e 6 % (empreitadas de reabilitação "
        "elegíveis), licenciamento municipal (RJUE: licença / comunicação prévia), alvará/IMPIC, faturação "
        "certificada AT, certificado energético (SCE/ADENE), Eurocódigos com Anexos Nacionais (NP EN). "
        "NUNCA cites normas, apoios ou siglas francesas (RE2020, DPE, CEE, MaPrimeRénov, DTU, SIRET, TVA…).\n"
        "2. NÃO inventes estatísticas, percentagens, números de leis/artigos, montantes de apoios nem preços "
        "exatos. Se deres ordens de grandeza de preço, usa intervalos largos e escreve 'valores indicativos, "
        "variam com a região, os materiais e o empreiteiro'. Convida a confirmar junto das entidades oficiais.\n"
        "3. Conteúdo útil e concreto: passos, checklists, erros a evitar, exemplos práticos. Nada de "
        "enchimento nem frases genéricas de IA.")


def _prompt(topic: str, keywords: list[str], audience: str, extra: str = "") -> str:
    kw = ", ".join(keywords) if keywords else "(livre)"
    links = "\n".join(f"- {p} — {label}" for p, label in INTERNAL_LINKS.get(audience, INTERNAL_LINKS["particuliers"]))
    return (
        f"Tema: {topic}\nPalavras-chave alvo: {kw}\n\n"
        f"Escreve um artigo de blogue completo com {MIN_WORDS + 100} a 1800 palavras, em HTML semântico "
        "(<h2>, <h3>, <p>, <ul><li>, <ol><li>, <table> se útil) SEM <html>/<head>/<body>, SEM <h1> e sem estilos "
        "inline. Estrutura: introdução que responde logo à pergunta principal, 5 a 8 secções <h2> com "
        "subsecções <h3>, uma checklist prática, uma secção final de conclusão com apelo à ação para o "
        "ConstruPilot.\n"
        "Inclui no texto 2 a 4 ligações internas (<a href=\"/caminho\">texto natural</a>) escolhidas desta lista:\n"
        f"{links}\n"
        "NÃO incluas a FAQ no content_html (vai no campo faq).\n"
        f"{extra}\n"
        "Responde APENAS em JSON válido: {\"title\": \"título SEO ≤ 65 caracteres\", "
        "\"slug\": \"curto-em-minusculas-com-hifens\", \"meta_description\": \"≤ 155 caracteres\", "
        "\"keywords\": [\"...\"], \"content_html\": \"...\", "
        "\"faq\": [{\"question\": \"...\", \"answer\": \"...\"}] (4 a 6 perguntas reais de pesquisa), "
        "\"hero_image_prompt\": \"descrição EM INGLÊS de uma fotografia realista de obra/reabilitação em "
        "Portugal (arquitetura portuguesa, azulejos, telhados de telha cerâmica quando fizer sentido), sem texto\"}")


def _faq_html(faq: list[dict]) -> str:
    items = [f for f in faq if isinstance(f, dict) and f.get("question") and f.get("answer")]
    if not items:
        return ""
    parts = ["<h2>Perguntas frequentes</h2>"]
    for f in items:
        parts.append(f"<h3>{f['question']}</h3><p>{f['answer']}</p>")
    return "".join(parts)


def quality_issues(data: dict) -> list[str]:
    issues = []
    html = data.get("content_html") or ""
    if word_count(html) < MIN_WORDS:
        issues.append(f"curto ({word_count(html)} palavras < {MIN_WORDS})")
    text = re.sub(r"<[^>]+>", " ", html) + " " + (data.get("title") or "")
    fr = sorted({m.group(0) for m in _FR_TERMS.finditer(text)})
    if fr:
        issues.append("termos franceses/não aplicáveis: " + ", ".join(fr[:6]))
    if html.count("<h2") < 3:
        issues.append("estrutura insuficiente (< 3 secções H2)")
    return issues


async def _write(topic: str, keywords: list[str], audience: str) -> tuple[dict, list[str]]:
    """Gera o texto; 1 nova tentativa se a qualidade não passar."""
    raw = await _complete(_system(audience), _prompt(topic, keywords, audience), feature="ceo_blog")
    data = _json(raw, {}) or {}
    issues = quality_issues(data) if data.get("content_html") else ["resposta vazia"]
    if issues:
        extra = ("ATENÇÃO — a versão anterior foi recusada por: " + "; ".join(issues) +
                 ". Corrige isso: texto mais longo e aprofundado, apenas contexto português.")
        raw = await _complete(_system(audience), _prompt(topic, keywords, audience, extra), feature="ceo_blog")
        data2 = _json(raw, {}) or {}
        if data2.get("content_html"):
            data, issues = data2, quality_issues(data2)
    return data, issues


async def generate_article(topic: str, keywords: list[str] | None = None, audience: str = "particuliers",
                           with_image: bool = True, created_by: str | None = None,
                           origin: str = "manual", extra_fields: dict | None = None) -> dict:
    """Gera e guarda um rascunho. Levanta ValueError se o texto não puder ser gerado."""
    keywords = keywords or []
    audience = audience if audience in AUDIENCE_LABEL else "particuliers"
    data, issues = await _write(topic, keywords, audience)
    if not data.get("content_html") or not data.get("title"):
        raise ValueError("Geração do artigo impossível")

    article_id = "ceo_" + secrets.token_hex(8)
    slug = await unique_slug(slugify(data.get("slug") or data["title"]))
    warnings: list[str] = [f"Qualidade a rever: {i}" for i in issues]
    hero_storage = hero_url = None
    cost = CEO_TEXT_COST_EUR

    if with_image and data.get("hero_image_prompt"):
        ok, reason = await budget_allows()
        if not ok:
            warnings.append(f"Imagem principal não gerada: {reason}")
        else:
            try:
                img_prompt = ("Realistic professional editorial photograph for a Portuguese construction and "
                              f"renovation blog. {data['hero_image_prompt']}. Landscape 16:9, natural light, "
                              "no text, no logo, no watermark.")
                img_bytes, ctype = await ceo_media.generate_image(img_prompt, session_id=article_id)
                ext = "png" if "png" in ctype else "jpg"
                hero_storage = f"{storage.APP_NAME}/ceo/{article_id}/hero.{ext}"
                await run_in_threadpool(storage.put_object, hero_storage, img_bytes, ctype)
                hero_url = f"/api/blog/media/{article_id}/hero"
                cost += CEO_IMAGE_COST_EUR
            except Exception as exc:  # noqa: BLE001
                log.error("CEO hero image failed (%s)", type(exc).__name__)
                warnings.append("Imagem principal não gerada (erro do gerador).")

    faq = [f for f in (data.get("faq") or []) if isinstance(f, dict) and f.get("question") and f.get("answer")]
    content_html = data["content_html"] + _faq_html(faq)
    doc = {
        "autoseo_id": article_id, "source": "ceo_agent", "status": "draft", "origin": origin,
        "title": data["title"][:120], "slug": slug,
        "published_url": f"{SITE_URL}/blog/{slug}",
        "meta_description": (data.get("meta_description") or "")[:160],
        "excerpt": (data.get("meta_description") or "")[:200],
        "content_html": content_html, "content_markdown": None,
        "faq_schema": faq,
        "hero_image_url": hero_url, "hero_image_storage": hero_storage,
        "hero_image_alt": data.get("title"),
        "keywords": data.get("keywords") or keywords,
        "language_code": "pt", "audience": audience, "topic": topic,
        "word_count": word_count(content_html), "quality_issues": issues,
        "cost_eur": round(cost, 4),
        "reading_minutes": max(1, round(word_count(content_html) / 200)),
        "created_at": now_iso(), "created_by": created_by,
        "published_at": None, "received_at": now_iso(),
        **(extra_fields or {}),
    }
    await db.autoseo_articles.insert_one(dict(doc))
    doc.pop("_id", None)
    doc["warnings"] = warnings
    return doc
