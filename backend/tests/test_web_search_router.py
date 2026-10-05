"""Testes unitários do web_search_router (deteção inteligente)."""
import pytest

from engines.web_search_router import should_use_web_search


def test_user_override_true_forces_web():
    enabled, mode, reason = should_use_web_search("qualquer coisa simples", user_override=True)
    assert enabled is True
    assert mode == "forced"
    assert reason == "user_override_true"


def test_user_override_false_disables_web_even_with_keywords():
    enabled, mode, _ = should_use_web_search(
        "Qual o preço do cimento em Lisboa hoje?", user_override=False,
    )
    assert enabled is False
    assert mode == "disabled"


def test_empty_query_is_skipped():
    enabled, mode, _ = should_use_web_search("")
    assert enabled is False
    assert mode == "skipped"


def test_technical_eurocode_question_is_skipped():
    enabled, mode, _ = should_use_web_search(
        "O que diz o Eurocode 2 sobre dobragem de armaduras?",
    )
    assert enabled is False, "Pergunta técnica estável não deve chamar Perplexity"
    assert mode == "skipped"


@pytest.mark.parametrize("query", [
    "Qual o preço do cimento em Lisboa hoje?",
    "Quais os incentivos atuais para reabilitação urbana?",
    "Nova portaria RGEU 2026?",
    "Qual a última decreto-lei sobre térmica?",
])
def test_actuality_keywords_trigger_web(query):
    enabled, mode, reason = should_use_web_search(query)
    assert enabled is True, f"Esperava web search para: {query!r}"
    assert mode == "auto"
    assert reason.startswith("actuality_keyword") or reason.startswith("location_keyword")


def test_supplier_keyword_triggers_web():
    enabled, _, reason = should_use_web_search("Qual o melhor fornecedor de isolamento XPS?")
    assert enabled is True
    assert "supplier_keyword" in reason or "comparative" in reason


def test_pt_location_in_query_triggers_web():
    enabled, _, reason = should_use_web_search("Fissura num prédio antigo no Porto")
    assert enabled is True
    assert reason.startswith("location_keyword:porto")


def test_pt_location_in_project_context_triggers_web():
    enabled, _, reason = should_use_web_search(
        "Mancha de humidade recorrente numa parede exterior.",
        project_context={"region": "Lisboa"},
    )
    assert enabled is True
    assert "location_context" in reason


def test_long_query_triggers_web():
    long_q = (
        "Tenho uma moradia unifamiliar antiga com paredes de alvenaria tradicional "
        "que apresenta fissuração horizontal junto ao pavimento e eflorescência "
        "generalizada em várias divisões ao longo da fachada principal"
    )
    enabled, _, reason = should_use_web_search(long_q)
    assert enabled is True
    # pode fazer trigger por long_query ou por keyword inferida (não é importante aqui)
    assert reason in {
        "actuality_keyword:nova", "actuality_keyword:novo",
    } or reason.startswith("long_query") or reason.startswith("location_keyword")


def test_year_mention_triggers_web():
    enabled, _, reason = should_use_web_search("Mudou a lei do IVA desde 2025?")
    assert enabled is True
    # pode disparar por actuality_keyword (iva/lei) OU year_mention
    assert reason in {"year_mention"} or reason.startswith("actuality_keyword")


def test_comparative_triggers_web():
    enabled, _, reason = should_use_web_search("Qual o melhor cimento branco para fachada?")
    assert enabled is True
    assert reason.startswith("comparative") or reason.startswith("supplier_keyword")
