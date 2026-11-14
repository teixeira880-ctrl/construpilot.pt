"""14/11: «max» chegava à API OpenAI (gpt-5.5) → 400 «Unsupported value: 'max'». Convertido para xhigh."""
from engines.openai_studies import effort_api


def test_max_vira_xhigh():
    assert effort_api("max") == "xhigh"
    assert effort_api("high") == "high" and effort_api("xhigh") == "xhigh"
    assert effort_api("") == "high" and effort_api("qualquer") == "high"
