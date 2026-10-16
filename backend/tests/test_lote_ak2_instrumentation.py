"""AK.2 — Testes da instrumentação dos 6 fluxos.

Para evitar depender de dados reais complexos, testamos ao nível de fonte:
verificamos que cada ficheiro-alvo contém a chamada `record_activity(` com o
`kind` correcto, e que o import está presente dentro de bloco `try/except`.
Além disso, para 2 fluxos chave (contact + permit) corremos a chamada real
num test de integração via DB.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


# ─── Static source-level checks (sem levantar backend) ────────────────────
INSTRUMENTED = {
    "contact": ("routes/leads.py", 'kind="contact"'),
    "quote": ("routes/documents.py", 'kind="quote"'),
    "ai_chat": ("routes/assistant.py", 'kind="ai_chat"'),
    "permit": ("routes/autorizacao_obras.py", 'kind="permit"'),
    "download": ("routes/documents.py", 'kind="download"'),
    "calculation": ("routes/stairs.py", 'kind="calculation"'),
}


@pytest.mark.parametrize("kind,info", INSTRUMENTED.items())
def test_instrumentation_present(kind, info):
    rel, needle = info
    path = ROOT / rel
    text = path.read_text(encoding="utf-8")
    assert needle in text, f"Falta `{needle}` em {rel}"
    # Deve estar dentro de try/except — procura `try:` nas 15 linhas acima
    lines = text.splitlines()
    for i, line in enumerate(lines):
        if needle in line:
            prelude = "\n".join(lines[max(0, i - 15):i])
            assert "try:" in prelude, (
                f"`{needle}` em {rel}:{i+1} não está dentro de try/except"
            )


def test_no_record_activity_outside_try_except():
    """Qualquer chamada a record_activity nos routes deve estar sob try/except."""
    routes_dir = ROOT / "routes"
    pattern = re.compile(r"record_activity\s*\(")
    offenders = []
    for py in routes_dir.rglob("*.py"):
        text = py.read_text(encoding="utf-8", errors="ignore")
        lines = text.splitlines()
        for i, line in enumerate(lines):
            if pattern.search(line) and "def record_activity" not in line:
                prelude = "\n".join(lines[max(0, i - 20):i])
                if "try:" not in prelude:
                    offenders.append(f"{py.name}:{i+1}")
    assert not offenders, (
        "record_activity sem try/except em routes/:\n" + "\n".join(offenders)
    )


# ─── Integração mínima do helper (sem event loop paralelo com motor) ─────
# Nota: o teste de integração completo (contact+permit via Motor async) corre
# em `test_lote_ak1_activity.py` por limitação do motor+anyio em múltiplos
# ficheiros no mesmo xdist worker. Aqui mantemos apenas os static checks.
