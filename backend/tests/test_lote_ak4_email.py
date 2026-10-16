"""AK.4 — Testes do email automático: templates + helpers puros (sync).

O teste integração completo (envio real via mock Resend) está em
`test_lote_ak1_activity.py` para evitar conflitos motor+anyio entre workers.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from engines.activity_crm.email_notifications import (  # noqa: E402
    _STATE_SUBJECTS,
    _load_template,
    _render,
)


def test_ak4_templates_exist():
    """Os 6 templates (3 estados × 2 locales) devem existir."""
    base = ROOT / "templates" / "emails" / "activity"
    expected = [
        "state_em_curso.pt.html", "state_respondido.pt.html", "state_fechado.pt.html",
        "state_em_curso.fr.html", "state_respondido.fr.html", "state_fechado.fr.html",
    ]
    missing = [n for n in expected if not (base / n).exists()]
    assert not missing, f"Templates em falta: {missing}"


def test_ak4_pt_template_has_placeholders():
    base = ROOT / "templates" / "emails" / "activity"
    html = (base / "state_em_curso.pt.html").read_text(encoding="utf-8")
    assert "{{nome}}" in html
    assert "{{summary}}" in html


def test_ak4_fr_template_has_placeholders():
    base = ROOT / "templates" / "emails" / "activity"
    html = (base / "state_respondido.fr.html").read_text(encoding="utf-8")
    assert "{{nome}}" in html
    assert "{{summary}}" in html
    assert "{{custom_text}}" in html


def test_ak4_subjects_pt_fr():
    assert "ConstruPilot" in _STATE_SUBJECTS["pt"]["em_curso"]
    assert "ConstruPilot" in _STATE_SUBJECTS["fr"]["em_curso"]
    assert "em análise" in _STATE_SUBJECTS["pt"]["em_curso"]
    assert "cours d'analyse" in _STATE_SUBJECTS["fr"]["em_curso"]
    assert "respondido" not in _STATE_SUBJECTS["pt"]["respondido"]  # usa "Respondemos"
    assert "répondu" in _STATE_SUBJECTS["fr"]["respondido"]


def test_ak4_load_template_pt_fr():
    tpl_pt = _load_template("em_curso", "pt")
    tpl_fr = _load_template("em_curso", "fr")
    assert tpl_pt and "lang=\"pt-PT\"" in tpl_pt
    assert tpl_fr and "lang=\"fr-FR\"" in tpl_fr


def test_ak4_load_template_missing():
    assert _load_template("inexistente", "pt") is None
    assert _load_template("em_curso", "xx") is None


def test_ak4_render_substitutes_placeholders():
    tpl = "<p>Olá {{nome}}, resumo: {{summary}}, extra: {{custom_text}}</p>"
    out = _render(tpl, {"nome": "João", "summary": "pedido muro",
                        "custom_text": "resposta detalhada"})
    assert "Olá João" in out
    assert "pedido muro" in out
    assert "resposta detalhada" in out


def test_ak4_render_empty_values():
    """Valores None/vazios → string vazia, não a palavra 'None'."""
    tpl = "<p>Olá {{nome}}, extra={{custom_text}}</p>"
    out = _render(tpl, {"nome": "Teste", "custom_text": None})
    assert "None" not in out
    assert "extra=" in out
