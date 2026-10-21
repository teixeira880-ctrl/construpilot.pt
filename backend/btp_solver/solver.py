"""Cœur du solveur BTP.

Cascade multi-provider :
  1. **Perplexity** avec recherche web filtrée (Legifrance/CSTB/DTU) →
     obtient les références réglementaires et les prix de marché actuels.
  2. **Anthropic Claude Sonnet** (via Emergent) → structure la réponse
     dans le schéma :class:`SolverResponse`.
  3. Fallback **OpenAI GPT-5.6** si Claude indisponible.

Le solveur *toujours* :
  - renvoie un chiffrage provisionnel (fourchette min/max)
  - propose 2 à 4 solutions triées par pertinence
  - joint au moins un graphique comparatif des solutions
"""
from __future__ import annotations

import json
import os
import re
import uuid
from datetime import datetime, timezone

from btp_solver.schema import (Cause, Chart, ChartSeries, Reference, Solution,
                                SolutionStep, SolverResponse)
from perplexity_plus import client as pplx

# ─────────────────────────────────────────────────────────────────────────────
# Prompts
# ─────────────────────────────────────────────────────────────────────────────
_RESEARCH_SYSTEM = (
    "És especialista em patologia da construção em Portugal (fissuras, humidade, térmica, estrutura). A partir da descrição de um problema, identificas as causas prováveis, citas as normas aplicáveis (NP EN, Eurocódigos com Anexos Nacionais, especificações LNEC, RGEU, REH) e dás ordens de grandeza de custo (preços do mercado português 2026). Responde em português europeu, estrutura a resposta em 3 secções: 1) Causas prováveis (numeradas, com indicadores clínicos) 2) Soluções técnicas (2-4 opções, com intervalo de custo €, duração em dias, nível de risco, garantia eventual) 3) Referências regulamentares (NP EN, LNEC, decretos-lei com ligação para o Diário da República)"
)

_STRUCTURATION_SYSTEM = (
    "És um extrator de JSON. É-te fornecida uma análise de um problema de construção em texto livre + fontes web. Convertes em JSON estrito que respeita este esquema. Não devolvas NENHUM texto fora do JSON.\n\nESQUEMA:\n{\n  \"domain\": \"fissures|humidite|thermique|structure|sinistre|reception|autre\",\n  \"urgency\": \"informative|planned|urgent|immediate\",\n  \"summary\": str (3-5 linhas, em português europeu),\n  \"causes\": [ { \"label\": str, \"confidence\": \"low|medium|high\",\n                \"explanation\": str, \"indicators_matched\": [str] } ],\n  \"solutions\": [ { \"id\": str (slug),\n                   \"label\": str, \"description\": str,\n                   \"cost_min_eur\": number|null, \"cost_max_eur\": number|null,\n                   \"duration_days_min\": number|null, \"duration_days_max\": number|null,\n                   \"risk\": \"low|medium|high|critical\",\n                   \"warranty_years\": integer|null,\n                   \"steps\": [ { \"order\": int, \"text\": str,\n                                \"duration_hours\": number|null,\n                                \"materials\": [str] } ],\n                   \"references\": [ { \"kind\": \"dtu|nf|code|web|cctp\",\n                                     \"code\": str, \"title\": str|null,\n                                     \"url\": str|null } ],\n                   \"recommended\": bool } ],\n  \"references\": [ ... mesmo esquema que acima ... ],\n  \"action_plan\": [ { \"order\": int, \"text\": str,\n                     \"duration_hours\": number|null,\n                     \"materials\": [str] } ]\n}\nMarca `recommended: true` na solução que oferece o melhor compromisso custo / durabilidade / rapidez. Ordena as causas da mais provável para a menos provável. Todos os textos em português europeu."
)


# ─────────────────────────────────────────────────────────────────────────────
# Providers de structuration
# ─────────────────────────────────────────────────────────────────────────────
async def _structure_with_claude(context: str) -> dict | None:
    """Fallback Claude via Emergent (déjà présent dans l'app)."""
    if not os.environ.get("EMERGENT_LLM_KEY"):
        return None
    try:
        from emergentintegrations.llm.chat import LlmChat, UserMessage
        chat = LlmChat(
            api_key=os.environ["EMERGENT_LLM_KEY"],
            session_id=f"btp-solver-{uuid.uuid4().hex[:8]}",
            system_message=_STRUCTURATION_SYSTEM,
        ).with_model("anthropic", "claude-sonnet-4-6")
        raw = await chat.send_message(UserMessage(text=context))
        text = raw if isinstance(raw, str) else str(raw)
        return _extract_json(text)
    except Exception:
        return None


async def _structure_with_openai(context: str) -> dict | None:
    """Fallback OpenAI GPT-5.6 (via Emergent)."""
    if not os.environ.get("EMERGENT_LLM_KEY"):
        return None
    try:
        from emergentintegrations.llm.chat import LlmChat, UserMessage
        chat = LlmChat(
            api_key=os.environ["EMERGENT_LLM_KEY"],
            session_id=f"btp-solver-{uuid.uuid4().hex[:8]}",
            system_message=_STRUCTURATION_SYSTEM,
        ).with_model("openai", "gpt-5.6-terra")
        raw = await chat.send_message(UserMessage(text=context))
        text = raw if isinstance(raw, str) else str(raw)
        return _extract_json(text)
    except Exception:
        return None


def _extract_json(text: str) -> dict | None:
    """Extrait le premier objet JSON valide du texte."""
    text = text.strip()
    # Supprimer les fences éventuels
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```\s*$", "", text)
    try:
        return json.loads(text)
    except Exception:
        pass
    # Extraction gloutonne
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1:
        return None
    try:
        return json.loads(text[start:end + 1])
    except Exception:
        return None


# ─────────────────────────────────────────────────────────────────────────────
# Graphiques
# ─────────────────────────────────────────────────────────────────────────────
def _build_comparison_chart(solutions: list[Solution]) -> Chart | None:
    """Comparatif barres coût min/max par solution."""
    solutions_with_cost = [s for s in solutions if s.cost_min_eur is not None]
    if len(solutions_with_cost) < 2:
        return None
    labels = [s.label[:40] for s in solutions_with_cost]
    return Chart(
        id="cost_comparison",
        type="bar",
        title="Comparação de custos (intervalo mín. / máx.)",
        x_labels=labels,
        series=[
            ChartSeries(name="Custo mín. €", data=[float(s.cost_min_eur or 0) for s in solutions_with_cost]),
            ChartSeries(name="Custo máx. €", data=[float(s.cost_max_eur or s.cost_min_eur or 0) for s in solutions_with_cost]),
        ],
        unit="€ HT",
        caption="Intervalos indicativos (mercado português 2026). Continua a ser necessário um orçamento local.",
    )


def _build_duration_chart(solutions: list[Solution]) -> Chart | None:
    """Comparatif durées."""
    subset = [s for s in solutions if s.duration_days_min is not None]
    if len(subset) < 2:
        return None
    return Chart(
        id="duration_comparison",
        type="bar",
        title="Comparação da duração da obra",
        x_labels=[s.label[:40] for s in subset],
        series=[
            ChartSeries(name="Duração mín. (d)", data=[float(s.duration_days_min or 0) for s in subset]),
            ChartSeries(name="Duração máx. (d)", data=[float(s.duration_days_max or s.duration_days_min or 0) for s in subset]),
        ],
        unit="jours",
    )


def _build_risk_radar(solutions: list[Solution]) -> Chart | None:
    """Radar risque/durabilité par solution."""
    if len(solutions) < 2:
        return None
    _risk_score = {"low": 1, "medium": 2, "high": 3, "critical": 4}
    return Chart(
        id="risk_radar",
        type="radar",
        title="Perfil risco / garantia / rapidez",
        x_labels=["Risque (1-4)", "Garantia (anos)", "Rapidez (0-10)"],
        series=[
            ChartSeries(
                name=s.label[:30],
                data=[
                    float(_risk_score.get(s.risk, 2)),
                    float(s.warranty_years or 0),
                    float(10 - min(10, (s.duration_days_max or s.duration_days_min or 5))),
                ],
            )
            for s in solutions[:4]
        ],
    )


def _build_confidence_pie(causes: list[Cause]) -> Chart | None:
    """Répartition confiance des causes."""
    if not causes:
        return None
    _cw = {"low": 1, "medium": 2, "high": 3}
    return Chart(
        id="causes_confidence",
        type="pie",
        title="Causas prováveis (por nível de confiança)",
        x_labels=[c.label[:40] for c in causes],
        series=[ChartSeries(name="Confiança", data=[float(_cw.get(c.confidence, 1)) for c in causes])],
        caption="Soma ponderada normalizada a 100 % do lado do cliente.",
    )


# ─────────────────────────────────────────────────────────────────────────────
# Point d'entrée
# ─────────────────────────────────────────────────────────────────────────────
async def solve(
    *,
    description: str,
    photos_urls: list[str] | None = None,
    context: dict | None = None,
    photo_analysis: str | None = None,
) -> SolverResponse:
    """Résout un problème BTP et renvoie diagnostic + solutions + graphiques.

    - ``description`` : ce que voit / décrit l'utilisateur (obligatoire)
    - ``photos_urls`` : URLs de photos (optionnel, non exploité côté Perplexity mais transmis au LLM)
    - ``context`` : {region, surface_m2, age_annees, type_batiment, urgence_ressentie, budget_max_eur}
    - ``photo_analysis`` : lecture vision des photos jointes (texte), injectée dans la recherche et la structuration
    """
    ctx_txt = ""
    if context:
        parts = []
        if context.get("region"):
            parts.append(f"Região: {context['region']}")
        if context.get("type_batiment"):
            parts.append(f"Tipo de edifício: {context['type_batiment']}")
        if context.get("surface_m2"):
            parts.append(f"Área: {context['surface_m2']} m²")
        if context.get("age_annees"):
            parts.append(f"Idade do edifício: {context['age_annees']} ans")
        if context.get("budget_max_eur"):
            parts.append(f"Orçamento máximo previsto: {context['budget_max_eur']} €")
        if context.get("urgence_ressentie"):
            parts.append(f"Urgência sentida: {context['urgence_ressentie']}")
        if parts:
            ctx_txt = "\n\nContexte :\n" + "\n".join(f"- {p}" for p in parts)

    photos_txt = ""
    if photos_urls:
        photos_txt = "\n\nFotografias anexadas (URL):\n" + "\n".join(f"- {u}" for u in photos_urls[:5])
    if photo_analysis:
        photos_txt += "\n\nLeitura das fotografias anexadas pela IA de visão (apenas observações visíveis):\n" + photo_analysis.strip()

    research_question = f"{description}{ctx_txt}{photos_txt}"

    # Étape 1 : recherche web sourcée
    research_txt = ""
    citations: list[dict] = []
    total_cost = 0.0
    if pplx.configured():
        research = await pplx.ask(
            question=research_question,
            instructions=_RESEARCH_SYSTEM,
            preset="high",
            domain_filter=[
                "legifrance.gouv.fr", "cstb.fr", "afnor.org",
                "boutique.afnor.org", "batichoix.com", "batirama.com",
                "lemoniteur.fr", "service-public.fr", "qualibat.com",
                "ecologie.gouv.fr", "anah.gouv.fr",
            ],
            search_context_size="high",
            max_results=10,
            max_output_tokens=2500,
        )
        research_txt = research["text"]
        citations = research.get("citations", [])
        total_cost += research.get("cost_usd", 0) or 0

    # Étape 2 : structuration en JSON via Claude puis fallback GPT
    structuration_input = (
        f"Problema descrito pelo utilizador:\n{description}{ctx_txt}{photos_txt}\n\n---\nAnálise preliminar (com fontes):\n{research_txt or '(sem pesquisa preliminar)'}\n\n---\nFontes web disponíveis:\n"
        + "\n".join(f"- {c.get('title') or ''} → {c.get('url')}" for c in citations[:15])
    )

    data = await _structure_with_claude(structuration_input)
    if data is None:
        data = await _structure_with_openai(structuration_input)

    if data is None:
        # Dernier recours : réponse minimale texte-seule
        data = {
            "domain": "autre",
            "urgency": "planned",
            "summary": research_txt[:600] or "Análise momentaneamente indisponível.",
            "causes": [],
            "solutions": [],
            "references": [],
            "action_plan": [],
        }

    # Reconstruction typée
    causes = [Cause(**c) for c in data.get("causes", [])]
    solutions_raw = data.get("solutions", []) or []
    solutions = []
    for i, s in enumerate(solutions_raw):
        s.setdefault("id", f"sol_{i+1}")
        s["steps"] = [SolutionStep(**st) for st in s.get("steps", [])]
        s["references"] = [Reference(**r) for r in s.get("references", [])]
        solutions.append(Solution(**s))

    references = [Reference(**r) for r in data.get("references", [])]
    action_plan = [SolutionStep(**st) for st in data.get("action_plan", [])]

    # Enrichir avec les citations Perplexity si le LLM en a oublié
    seen_urls = {r.url for r in references if r.url}
    for c in citations[:10]:
        url = c.get("url")
        if url and url not in seen_urls:
            references.append(Reference(kind="web", code=(c.get("title") or "Source web")[:80], title=c.get("title"), url=url))
            seen_urls.add(url)

    # Graphiques
    charts: list[Chart] = []
    if (ch := _build_comparison_chart(solutions)):
        charts.append(ch)
    if (ch := _build_duration_chart(solutions)):
        charts.append(ch)
    if (ch := _build_risk_radar(solutions)):
        charts.append(ch)
    if (ch := _build_confidence_pie(causes)):
        charts.append(ch)

    return SolverResponse(
        problem_id=f"prob_{uuid.uuid4().hex[:10]}",
        domain=data.get("domain", "autre"),
        urgency=data.get("urgency", "planned"),
        summary=data.get("summary", ""),
        causes=causes,
        solutions=solutions,
        charts=charts,
        references=references,
        action_plan=action_plan,
        generated_at_iso=datetime.now(timezone.utc).isoformat(),
        cost_usd=total_cost,
    )
