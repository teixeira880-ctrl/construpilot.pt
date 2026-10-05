"""Núcleo do solver BTP · versão PT.

Cascade AI:
  1. **Perplexity** (opcional, só se o texto tiver gatilhos de atualidade)
     obtém preços actuais e referências normativas recentes.
  2. **Claude Opus 5.5** (primário) devolve JSON estruturado.
  3. **OpenAI gpt-4o** (fallback) se Claude falhar.

Todos os preços retornados são indicativos para o mercado PT continental 2026
sem IVA (23 %). As normas são portuguesas (RGEU/RJUE/EC/NP EN/LNEC).
"""
from __future__ import annotations

import json
import logging
import re
import uuid
from datetime import datetime, timezone

from engines.ai_providers.router import ai_router
from engines.btp_solver.schema import (
    Cause,
    Chart,
    ChartSeries,
    Reference,
    Solution,
    SolutionStep,
    SolverResponse,
)
from engines.web_search_router import should_use_web_search
from core.rate_limit import WEB_LIMITS, web_search_hit, web_search_remaining

logger = logging.getLogger("btp_solver")


# ─────────────────────────────────────────────────────────────────────────────
# System prompt PT-PT com normativa portuguesa
# ─────────────────────────────────────────────────────────────────────────────
_SOLVER_SYSTEM = (
    "És um especialista em patologia de edifícios em Portugal (fissuras, "
    "humidade, estrutura, térmico, sinistros, receção de obra). A partir da "
    "descrição textual de um problema, diagnosticas as causas prováveis, "
    "citas a normativa portuguesa aplicável e devolves soluções com custos "
    "indicativos para o mercado PT continental em 2026 (sem IVA 23 %).\n\n"
    "Devolves EXCLUSIVAMENTE um JSON estrito que respeita o esquema abaixo. "
    "Nunca escrevas texto fora do JSON. Nunca uses blocos de código markdown.\n\n"
    "ESQUEMA:\n"
    "{\n"
    '  "domain": "fissuras|humidade|termico|estrutura|sinistro|recepcao|outro",\n'
    '  "urgency": "informative|planned|urgent|immediate",\n'
    '  "summary": "3-5 linhas em PT-PT",\n'
    '  "causes": [ { "label": "...", "confidence": "low|medium|high",\n'
    '                "explanation": "...", "indicators_matched": ["..."] } ],\n'
    '  "solutions": [ { "id": "slug", "label": "...", "description": "...",\n'
    '                   "cost_min_eur": number|null, "cost_max_eur": number|null,\n'
    '                   "duration_days_min": number|null, "duration_days_max": number|null,\n'
    '                   "risk": "low|medium|high|critical",\n'
    '                   "warranty_years": integer|null,\n'
    '                   "steps": [ { "order": int, "text": "...",\n'
    '                                "duration_hours": number|null,\n'
    '                                "materials": ["..."],\n'
    '                                "biblioteca_pt_ref": "ALV_TIJ_11|null" } ],\n'
    '                   "references": [ { "kind": "rgeu|rjue|ec|np_en|lnec|dl|web|cctp",\n'
    '                                     "code": "RGEU art. 65º|EN 1992-1-1|NP EN 206|DL 101-D/2020",\n'
    '                                     "title": "...", "url": "..." } ],\n'
    '                   "recommended": true|false } ],\n'
    '  "references": [ ... mesmo schema ... ],\n'
    '  "action_plan": [ { "order": int, "text": "...",\n'
    '                     "duration_hours": number|null,\n'
    '                     "materials": ["..."] } ]\n'
    "}\n\n"
    "Regras obrigatórias:\n"
    " - Marca `recommended: true` na solução com melhor relação custo / durabilidade / rapidez.\n"
    " - Ordena causas da mais provável à menos provável.\n"
    " - Sempre que possível indica a chave da Biblioteca PT 2026 em `biblioteca_pt_ref` (ex: `ALV_TIJ_11`, `BET_C25_30`).\n"
    " - Normativa prioritária PT: RGEU (edifícios), RJUE (urbanístico), REH (térmico habitação), RSCIE (segurança incêndio), RECS (comerciais/serviços), NP EN e LNEC (materiais), DL 101-D/2020 (energia), Portaria 349-A/2013 (CE).\n"
    " - Eurocódigos aceites: EC0 (NP EN 1990) a EC7 (NP EN 1997) com anexos nacionais.\n"
    " - Preços em EUR sem IVA, mercado PT continental 2026 (IVA aplicável: 23 % continental · 22 % Madeira · 16 % Açores).\n"
    " - Nunca inventes URLs; se não conheces uma fonte oficial, deixa `url: null`.\n"
    " - Em caso de dúvida estrutural, menciona a necessidade de parecer de engenheiro inscrito na Ordem dos Engenheiros (OE)."
)


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────
def _extract_json(text: str) -> dict | None:
    """Extrai o primeiro objeto JSON válido do texto."""
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```\s*$", "", text)
    try:
        return json.loads(text)
    except Exception:
        pass
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1:
        return None
    try:
        return json.loads(text[start:end + 1])
    except Exception:
        return None


def _build_comparison_chart(solutions: list[Solution]) -> Chart | None:
    subset = [s for s in solutions if s.cost_min_eur is not None]
    if len(subset) < 2:
        return None
    return Chart(
        id="cost_comparison",
        type="bar",
        title="Comparativo de custo (intervalo mín. / máx.)",
        x_labels=[s.label[:40] for s in subset],
        series=[
            ChartSeries(name="Custo mín. (€)",
                        data=[float(s.cost_min_eur or 0) for s in subset]),
            ChartSeries(name="Custo máx. (€)",
                        data=[float(s.cost_max_eur or s.cost_min_eur or 0) for s in subset]),
        ],
        unit="€ (sem IVA)",
        caption="Preços indicativos para Portugal continental em 2026. Orçamento local necessário.",
    )


def _build_duration_chart(solutions: list[Solution]) -> Chart | None:
    subset = [s for s in solutions if s.duration_days_min is not None]
    if len(subset) < 2:
        return None
    return Chart(
        id="duration_comparison",
        type="bar",
        title="Comparativo de duração da obra",
        x_labels=[s.label[:40] for s in subset],
        series=[
            ChartSeries(name="Duração mín. (dias)",
                        data=[float(s.duration_days_min or 0) for s in subset]),
            ChartSeries(name="Duração máx. (dias)",
                        data=[float(s.duration_days_max or s.duration_days_min or 0) for s in subset]),
        ],
        unit="dias",
    )


def _build_confidence_pie(causes: list[Cause]) -> Chart | None:
    if not causes:
        return None
    _cw = {"low": 1, "medium": 2, "high": 3}
    return Chart(
        id="causes_confidence",
        type="pie",
        title="Causas prováveis (por nível de confiança)",
        x_labels=[c.label[:40] for c in causes],
        series=[ChartSeries(name="Confiança", data=[float(_cw.get(c.confidence, 1)) for c in causes])],
        caption="Soma ponderada; normaliza para 100 % na UI.",
    )


# ─────────────────────────────────────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────────────────────────────────────
async def solve(
    *,
    description: str,
    context: dict | None = None,
    use_web_search: bool | None = None,
    user_id: str | None = None,
    plan: str = "free",
) -> SolverResponse:
    """Resolve um problema BTP e devolve diagnóstico + soluções + gráficos.

    ``description`` : o que o utilizador vê/descreve (obrigatório).
    ``context`` : {region, surface_m2, idade_anos, tipo_edificio, urgencia, orcamento_max_eur}
    ``use_web_search`` : toggle UI (True=sempre, False=nunca, None=auto)
    ``user_id`` / ``plan`` : usados para o sub-bucket web-search soft limit
    """
    ctx_txt = ""
    if context:
        parts = []
        if context.get("region"):
            parts.append(f"Região: {context['region']}")
        if context.get("tipo_edificio"):
            parts.append(f"Tipo de edifício: {context['tipo_edificio']}")
        if context.get("surface_m2"):
            parts.append(f"Área: {context['surface_m2']} m²")
        if context.get("idade_anos"):
            parts.append(f"Idade do edificado: {context['idade_anos']} anos")
        if context.get("orcamento_max_eur"):
            parts.append(f"Orçamento máx. previsto: {context['orcamento_max_eur']} €")
        if context.get("urgencia"):
            parts.append(f"Urgência percebida: {context['urgencia']}")
        if parts:
            ctx_txt = "\n\nContexto:\n" + "\n".join(f"- {p}" for p in parts)

    user_prompt = f"Problema descrito:\n{description}{ctx_txt}"

    # Decidir web search (contexto do projeto inclui região para localização PT)
    want_web, web_mode, web_reason = should_use_web_search(
        description, project_context=context, user_override=use_web_search,
    )
    web_budget = WEB_LIMITS.get("btp_solver", {}).get(plan, 0)
    web_fallback = False
    if want_web and user_id:
        if not web_search_hit(user_id, plan, "btp_solver", web_budget):
            want_web = False
            web_fallback = True
            web_mode = "budget_exhausted"
    remaining = (
        web_search_remaining(user_id, plan, "btp_solver", web_budget)
        if user_id else web_budget
    )

    logger.info(
        "flow=btp_solver user=%s web_search=%s mode=%s reason=%s "
        "budget=%d/%d plan=%s",
        (user_id or "?")[:12], want_web, web_mode, web_reason,
        remaining, web_budget, plan,
    )

    # Tentativa 1: temperature baixa (determinístico)
    r = await ai_router.coach_ask(
        prompt=user_prompt,
        system=_SOLVER_SYSTEM,
        history=None,
        max_tokens=6000,
        temperature=0.2,
        enrich_with_web=want_web,
    )
    data = _extract_json(r.text) or {}

    # Retry 1x com temperature=0.0 se o parse falhou ou veio sem causas/soluções
    if not data or (not data.get("causes") and not data.get("solutions")):
        logger.info("btp_solver: parse falhou/vazio, retry com temperature=0.0")
        r = await ai_router.coach_ask(
            prompt=user_prompt + "\n\nIMPORTANTE: começa a resposta EXCLUSIVAMENTE pelo caracter '{' e termina em '}'. Nenhuma frase antes ou depois.",
            system=_SOLVER_SYSTEM,
            history=None,
            max_tokens=6000,
            temperature=0.0,
            enrich_with_web=want_web,
        )
        data = _extract_json(r.text) or data

    if not data:
        logger.warning("btp_solver: LLM output não parseável após retry, devolvendo stub")
        data = {
            "domain": "outro",
            "urgency": "planned",
            "summary": (r.text[:600] or "Análise temporariamente indisponível."),
            "causes": [], "solutions": [], "references": [], "action_plan": [],
        }

    # Reconstrução tipada
    causes = []
    for c in data.get("causes", []) or []:
        try:
            causes.append(Cause(**c))
        except Exception:
            continue

    solutions: list[Solution] = []
    for i, s in enumerate(data.get("solutions", []) or []):
        try:
            s.setdefault("id", f"sol_{i + 1}")
            s["steps"] = [SolutionStep(**st) for st in s.get("steps", []) or []]
            s["references"] = [Reference(**ref) for ref in s.get("references", []) or []]
            solutions.append(Solution(**s))
        except Exception as e:  # noqa: BLE001
            logger.warning("btp_solver: skip solution #%d (%s)", i, type(e).__name__)
            continue

    references: list[Reference] = []
    for ref in data.get("references", []) or []:
        try:
            references.append(Reference(**ref))
        except Exception:
            continue

    action_plan: list[SolutionStep] = []
    for st in data.get("action_plan", []) or []:
        try:
            action_plan.append(SolutionStep(**st))
        except Exception:
            continue

    # Enriquecimento com citações Perplexity (se existentes)
    seen = {r_.url for r_ in references if r_.url}
    for cit in (r.citations or []):
        url = getattr(cit, "url", None)
        if url and url not in seen:
            references.append(Reference(
                kind="web",
                code=(getattr(cit, "title", None) or "Fonte web")[:80],
                title=getattr(cit, "title", None),
                url=url,
            ))
            seen.add(url)

    # Charts
    charts: list[Chart] = []
    if (ch := _build_comparison_chart(solutions)):
        charts.append(ch)
    if (ch := _build_duration_chart(solutions)):
        charts.append(ch)
    if (ch := _build_confidence_pie(causes)):
        charts.append(ch)

    return SolverResponse(
        problem_id=f"bps_{uuid.uuid4().hex[:10]}",
        domain=data.get("domain", "outro"),
        urgency=data.get("urgency", "planned"),
        summary=data.get("summary", ""),
        causes=causes,
        solutions=solutions,
        charts=charts,
        references=references,
        action_plan=action_plan,
        generated_at_iso=datetime.now(timezone.utc).isoformat(),
        model_used=r.model,
        web_enriched=bool(r.citations) and want_web,
        web_search_mode=web_mode,
        web_search_reason=web_reason,
        web_search_fallback=web_fallback,
        web_remaining=remaining,
        web_limit=web_budget,
    )
