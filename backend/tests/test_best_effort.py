"""Palavra «teste» em qualquer língua / «faz o melhor que puderes» → o assistente faz o estudo, sem recusar, e termina com
«o que está correto» + «o que precisa de verificação»."""
import asyncio

from engines import best_effort
from engines.bet_core import reader


async def _stub(system, text, images=None, model=None, max_tokens=0):
    return "{}"


def test_detect_test_word_all_languages():
    cases = {"é um teste faz um estudo o melhor que poderes": "pt", "( é um texte faz um estudo o melhor que poderes )": "pt",
             "isto é um teste": "pt", "faz o melhor que puderes": "pt", "ce un test fait le melleur que tu peut": "fr",
             "c'est un test, fais le meilleur que tu peux": "fr", "c'est un test": "fr", "fais du mieux possible": "fr",
             "this is a test, do the full study": "en", "es una prueba": "en", "це тест": "en", "Testing the study": "en"}
    for t, lang in cases.items():
        assert best_effort.detect(t) == lang, t


def test_no_false_positive():
    for t in ["qual a melhor solução para as fundações?", "quelle est la meilleure solution pour les fondations ?",
              "faz um orçamento da cozinha", "le meilleur prix pour le béton", "contestação do orçamento", ""]:
        assert best_effort.detect(t) is None, t
        assert best_effort.directive(t) == ""


def test_directive_forbids_refusal_and_asks_correct_vs_to_verify():
    pt = best_effort.directive("é um teste")
    assert "PROIBIDO" in pt and "O que está correto" in pt and "O que precisa de verificação" in pt
    fr = best_effort.directive("c'est un test")
    assert "INTERDIT" in fr and "Ce qui est correct" in fr and "Ce qui doit être vérifié" in fr
    assert "What needs verification" in best_effort.directive("it's a test")


def test_study_decides_alone_on_test_word():
    for t in ["é um texte faz um estudo o melhor que poderes", "ce un test fait le melleur que tu peut", "this is a test"]:
        assert asyncio.run(reader.intends_decide_alone(t, llm=_stub)) is True, t
