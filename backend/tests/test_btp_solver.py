"""Testes unit do solver BTP (sem chamadas reais a LLM — tudo mockado)."""
from __future__ import annotations

from unittest.mock import patch, AsyncMock

import pytest
from dataclasses import dataclass, field


@dataclass
class _FakeAIResp:
    text: str
    provider: str = "claude"
    model: str = "claude-opus-5-5"
    latency_ms: int = 1000
    citations: list = field(default_factory=list)
    stop_reason: str | None = "end_turn"

    @property
    def is_empty(self):
        return not (self.text and self.text.strip())


_SAMPLE_JSON = """{
  "domain": "fissuras",
  "urgency": "planned",
  "summary": "Fissura diagonal em parede exterior de moradia dos anos 80.",
  "causes": [
    {"label": "Assentamento diferencial das fundações", "confidence": "high",
     "explanation": "Movimento do solo após chuva.", "indicators_matched": ["diagonal", "após chuva"]},
    {"label": "Movimentos térmicos", "confidence": "medium",
     "explanation": "Expansão/contração sazonal.", "indicators_matched": []}
  ],
  "solutions": [
    {"id": "monitor", "label": "Monitorizar com fissurómetros", "description": "Instalação e medição mensal.",
     "cost_min_eur": 450, "cost_max_eur": 1500, "duration_days_min": 1, "duration_days_max": 2,
     "risk": "low", "warranty_years": null,
     "steps": [{"order": 1, "text": "Colocar 3 fissurómetros", "duration_hours": 2,
                "materials": ["fissurómetro"], "biblioteca_pt_ref": null}],
     "references": [{"kind": "lnec", "code": "LNEC ITE 50", "title": null, "url": null}],
     "recommended": true},
    {"id": "reparar", "label": "Reparação completa", "description": "Cosedura + injecção.",
     "cost_min_eur": 2500, "cost_max_eur": 8000, "duration_days_min": 5, "duration_days_max": 10,
     "risk": "medium", "warranty_years": 10,
     "steps": [{"order": 1, "text": "Preparar substrato", "duration_hours": 8,
                "materials": ["betão C25/30"], "biblioteca_pt_ref": "BET_C25_30"}],
     "references": [{"kind": "ec", "code": "NP EN 1996-1-1", "title": null, "url": null}],
     "recommended": false}
  ],
  "references": [{"kind": "rgeu", "code": "RGEU art. 10º", "title": "Diploma", "url": null}],
  "action_plan": [
    {"order": 1, "text": "Chamar engenheiro inscrito na OE", "duration_hours": 1, "materials": []}
  ]
}"""


@pytest.mark.anyio
async def test_solve_devolve_schema_valido():
    from engines.btp_solver import solve
    with patch("engines.btp_solver.solver.ai_router.coach_ask", new=AsyncMock(return_value=_FakeAIResp(text=_SAMPLE_JSON))):
        r = await solve(description="Fissura diagonal numa parede exterior.",
                        context={"region": "Porto", "idade_anos": 40})
    assert r.problem_id.startswith("bps_")
    assert r.domain == "fissuras"
    assert r.urgency in ("informative", "planned", "urgent", "immediate")
    assert len(r.causes) == 2
    assert r.causes[0].confidence in ("low", "medium", "high")
    assert len(r.solutions) == 2
    recommended = [s for s in r.solutions if s.recommended]
    assert len(recommended) == 1
    assert recommended[0].id == "monitor"
    # Biblioteca PT ref no step
    bpt_refs = [st.biblioteca_pt_ref for s in r.solutions for st in s.steps]
    assert "BET_C25_30" in bpt_refs
    # Charts gerados automaticamente
    chart_ids = {c.id for c in r.charts}
    assert "cost_comparison" in chart_ids
    assert "duration_comparison" in chart_ids
    # Modelo registado
    assert r.model_used == "claude-opus-5-5"


@pytest.mark.anyio
async def test_solve_urgency_valida_sempre():
    from engines.btp_solver import solve
    bad_json = '{"domain":"outro","urgency":"planned","summary":"x","causes":[],"solutions":[],"references":[],"action_plan":[]}'
    with patch("engines.btp_solver.solver.ai_router.coach_ask", new=AsyncMock(return_value=_FakeAIResp(text=bad_json))):
        r = await solve(description="Teste minimal.")
    assert r.urgency in ("informative", "planned", "urgent", "immediate")
    assert r.disclaimer.startswith("Diagnóstico provisório")


@pytest.mark.anyio
async def test_solve_fallback_stub_quando_llm_devolve_lixo():
    from engines.btp_solver import solve
    with patch("engines.btp_solver.solver.ai_router.coach_ask",
               new=AsyncMock(return_value=_FakeAIResp(text="texto que não é JSON de todo"))):
        r = await solve(description="Problema qualquer para testar fallback.")
    # Não deve falhar; stub retorna domain=outro, causas vazias
    assert r.domain == "outro"
    assert r.causes == []
    assert r.solutions == []


@pytest.mark.anyio
async def test_solve_referencias_citacoes_perplexity_agregadas():
    from engines.btp_solver import solve
    from engines.ai_providers.base import Citation
    cits = [Citation(url="https://dre.pt/x", title="DRE artigo"),
            Citation(url="https://lnec.pt/y", title="LNEC guia")]
    with patch("engines.btp_solver.solver.ai_router.coach_ask",
               new=AsyncMock(return_value=_FakeAIResp(text=_SAMPLE_JSON, citations=cits))):
        r = await solve(description="Teste de enriquecimento.")
    urls = [ref.url for ref in r.references if ref.url]
    assert "https://dre.pt/x" in urls
    assert "https://lnec.pt/y" in urls
    assert r.web_enriched is True
