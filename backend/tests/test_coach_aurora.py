"""Testes do Coach IA (Aurora exclusivo).

Corre: `cd /app/backend && python -m pytest tests/test_coach_aurora.py -v -s`
"""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from engines.aurora_contract import AURORA_ANSWER_SCHEMA, AuroraCompanyAnswer
from engines.coach_aurora import (
    CoachAuroraError,
    _build_prompt,
    _format_history,
    _project_brief,
    coach_ask,
)


def _answer(text: str, model: str = "gpt-5.6-luna", route: str = "openai/gpt-5.6-luna",
            mode: str = "reasoning") -> AuroraCompanyAnswer:
    return AuroraCompanyAnswer(
        schema=AURORA_ANSWER_SCHEMA, text=text, model=model, route=route, mode=mode,
    )


SAMPLE_PROJECT = {
    "project_id": "prj_coach_test",
    "user_id": "user_coach",
    "name": "Moradia T3 Cascais",
    "city": "Cascais",
    "estimation": {
        "project_type_name": "Construção nova",
        "surface": 180,
        "total_avg": 245000,
        "finish_level_name": "Standard",
    },
}


# ---------------- Helpers ---------------------------------------------------
def test_project_brief_full():
    brief = _project_brief(SAMPLE_PROJECT)
    assert "Moradia T3 Cascais" in brief
    assert "180 m²" in brief
    assert "Cascais" in brief
    assert "€" in brief
    assert "Standard" in brief


def test_project_brief_none():
    assert _project_brief(None) == "(sem projeto associado)"
    assert _project_brief({}) == "(sem projeto associado)"


def test_format_history_limits_to_last_n():
    hist = [{"role": "user" if i % 2 == 0 else "assistant", "content": f"msg{i}"}
            for i in range(15)]
    out = _format_history(hist, limit=5)
    lines = out.split("\n")
    assert len(lines) == 5
    assert "msg14" in out  # última incluída
    assert "msg0" not in out  # primeira cortada


def test_format_history_empty():
    assert _format_history([], limit=5) == ""


def test_build_prompt_contains_all_sections():
    prompt = _build_prompt(
        user_message="Qual o preço do betão C25?",
        project=SAMPLE_PROJECT,
        history=[{"role": "user", "content": "hello"}],
        history_limit=5,
    )
    assert "[SISTEMA]" in prompt
    assert "[PROJETO_ATUAL]" in prompt
    assert "[HISTÓRICO_RECENTE]" in prompt
    assert "[PERGUNTA]" in prompt
    assert "Moradia T3 Cascais" in prompt
    assert "Qual o preço do betão C25?" in prompt
    assert "PT-PT" in prompt or "Português" in prompt


def test_build_prompt_mode_hint():
    prompt = _build_prompt(
        user_message="ola", project=None, history=[], history_limit=5,
        mode_hint="bullet points",
    )
    assert "[MODO_SUGERIDO]" in prompt
    assert "bullet points" in prompt


# ---------------- coach_ask integration (consolidado num só teste) ---------
# Motor client fica preso ao primeiro event loop, por isso agrupamos todos os
# cenários DB num único teste que corre no mesmo loop.
@pytest.mark.anyio
async def test_coach_ask_pipeline_full():
    from core.db import db

    # Cleanup inicial
    await db.coach_failures.delete_many(
        {"user_id": {"$in": ["user_coach", "user_coach_fail", "user_coach_email_fail"]}}
    )

    fake_projects = AsyncMock()

    # --- 1) Reasoning devolve texto → não chama fast ---------------------
    fake_projects.find_one = AsyncMock(return_value=SAMPLE_PROJECT)
    ok_meta = {"attempts": 1, "ok": True, "last_status": 200,
               "schema": AURORA_ANSWER_SCHEMA, "model": "gpt-5.6-luna",
               "route": "openai/gpt-5.6-luna", "mode": "reasoning"}
    fake_ask_ok = AsyncMock(return_value=(
        _answer("O preço do C25/30 anda entre 90 e 110 €/m³."), ok_meta,
    ))
    with patch("engines.coach_aurora.AuroraCompanyClient.ask_with_retry", fake_ask_ok), \
         patch.object(db, "projects", fake_projects):
        result = await coach_ask(
            project_id="prj_coach_test",
            user_message="Preço do betão C25?",
            conversation_history=[],
            user_id="user_coach",
            db=db,
        )
    assert result["text"].startswith("O preço")
    assert result["mode_used"] == "reasoning"
    assert result["model"] == "gpt-5.6-luna"
    assert fake_ask_ok.call_count == 1
    print(f"\n[OK-REASONING] mode={result['mode_used']} model={result['model']}")

    # --- 2) Reasoning vazio → fast responde -------------------------------
    fake_projects.find_one = AsyncMock(return_value=None)
    empty_meta = {"attempts": 3, "ok": False, "last_status": 200,
                  "error": "empty_text_after_retries"}
    fake_ask_fallback = AsyncMock(side_effect=[
        (None, empty_meta),
        (_answer("Resposta rápida em bullets.", mode="reasoning"), ok_meta),
    ])
    with patch("engines.coach_aurora.AuroraCompanyClient.ask_with_retry", fake_ask_fallback), \
         patch.object(db, "projects", fake_projects):
        result = await coach_ask(
            project_id=None,
            user_message="Explica RGEU",
            conversation_history=[],
            user_id="user_coach",
            db=db,
        )
    assert result["mode_used"] == "fast"
    assert result["text"] == "Resposta rápida em bullets."
    assert fake_ask_fallback.call_count == 2
    print(f"[OK-FALLBACK] reasoning→fast, attempts_total={fake_ask_fallback.call_count}")

    # --- 3) Ambos falham → CoachAuroraError + email admin + insert -------
    fake_send_email = AsyncMock(return_value={"ok": True, "id": "email_mock_id"})
    fake_wrap = lambda title, body, **kw: f"<html>{title}{body}</html>"  # noqa: E731
    fake_ask_all_empty = AsyncMock(return_value=(None, empty_meta))
    with patch("engines.coach_aurora.AuroraCompanyClient.ask_with_retry", fake_ask_all_empty), \
         patch.object(db, "projects", fake_projects), \
         patch("engines.emailer.send_email", fake_send_email), \
         patch("engines.emailer.wrap_html", fake_wrap):
        with pytest.raises(CoachAuroraError) as exc:
            await coach_ask(
                project_id=None,
                user_message="Pergunta que Aurora não vai responder",
                conversation_history=[],
                user_id="user_coach_fail",
                db=db,
            )
    assert exc.value.reasoning_meta["mode"] == "reasoning"
    assert exc.value.fast_meta["mode"] == "fast"
    assert fake_send_email.call_count == 1
    email_subject = fake_send_email.call_args.args[1]
    assert "Aurora Coach IA falhou" in email_subject
    assert "user_coach_fail"[:16] in email_subject
    print(f"[OK-BOTH-FAIL] email_sent=True subject={email_subject[:60]}...")

    # Confirmar registo em coach_failures
    doc = await db.coach_failures.find_one({"user_id": "user_coach_fail"}, {"_id": 0})
    assert doc is not None
    assert doc["message_snippet"].startswith("Pergunta")
    assert doc["reasoning_meta"]["mode"] == "reasoning"
    assert doc["fast_meta"]["mode"] == "fast"
    print(f"[OK-FAILURE-DB] failure_id={doc['failure_id']}")

    # --- 4) Falha do email admin não impede exceção ----------------------
    fake_email_broken = AsyncMock(side_effect=RuntimeError("Resend down"))
    with patch("engines.coach_aurora.AuroraCompanyClient.ask_with_retry", fake_ask_all_empty), \
         patch.object(db, "projects", fake_projects), \
         patch("engines.emailer.send_email", fake_email_broken):
        with pytest.raises(CoachAuroraError):
            await coach_ask(
                project_id=None,
                user_message="Q",
                conversation_history=[],
                user_id="user_coach_email_fail",
                db=db,
            )
    print("[OK-EMAIL-SILENT] CoachAuroraError levantada mesmo com Resend em falha")

    # Cleanup final
    await db.coach_failures.delete_many(
        {"user_id": {"$in": ["user_coach", "user_coach_fail", "user_coach_email_fail"]}}
    )
