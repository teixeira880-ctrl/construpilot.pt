"""Plantas sem materiais → cartões de escolha (ask_user_choices) antes do estudo/orçamento; modo «sem perguntas» → decide só."""
import os

os.environ.setdefault("STUDIES_MODEL_ANALYSIS", "x")
os.environ.setdefault("STUDIES_MODEL_LIGHT", "x")


def test_choice_cards_are_asked_for_missing_materials_except_in_no_question_mode():
    from routes import assistant as A
    from engines.bet_core import assistant_tool as BT
    desc = next(t["description"] for t in A.TOOLS if t.get("name") == "ask_user_choices")
    low = desc.lower()
    assert ("antes de um estudo" in low or "avant une étude" in low) and "multi=true" in low
    assert "nunca antes" not in low and "jamais avant" not in low
    assert "ask_user_choices" in BT.INSTRUCTIONS and ("MATÉRIAUX MANQUANTS" in BT.INSTRUCTIONS)
    assert "MODE SANS QUESTIONS" in BT.INSTRUCTIONS
