"""Boundary PT: tradução FR→PT dos campos humanos devolvidos pelo bet_core.

Garante que, quando o estudo é PT, as perguntas e anomalias chegam ao
Assistente em português europeu, sem alterar código do fetch
(`engines/bet_core/`). Testa `_translate_pt_output` do wrapper
`engines/assistant_bet_core_tool.py`.
"""
import copy

from engines.assistant_bet_core_tool import _tr_pt, _translate_pt_output


def test_pass_through_when_country_fr():
    """Country FR → nenhum campo é alterado."""
    payload = {
        "ok": True,
        "country": "FR",
        "status": "questions",
        "step": "Questions à l'utilisateur",
        "questions": ["Quelle est la portée réelle du plancher ?"],
        "anomalies": [{"code": "GEO-04", "level": "bloquant", "message": "Escalier impossible", "fix": "à préciser"}],
        "points": ["mur épais à vérifier"],
    }
    frozen = copy.deepcopy(payload)
    out = _translate_pt_output(payload)
    assert out == frozen, "country=FR não deve traduzir nada"


def test_translates_step_label_pt():
    out = _translate_pt_output({"country": "PT", "step": "Questions à l'utilisateur"})
    assert out["step"] == "Questões ao utilizador"
    out2 = _translate_pt_output({"country": "PT", "step": "Terminé"})
    assert out2["step"] == "Concluído"


def test_translates_questions_terms_pt():
    """Verifica termos técnicos chave aparecem em PT."""
    fr_qs = [
        "Épaisseur des murs extérieurs non cotée.",
        "Portée du plancher à confirmer.",
        "Escalier impossible : abertura 1,20 m, delta_h 3,00 m.",
    ]
    out = _translate_pt_output({"country": "PT", "questions": fr_qs})
    joined = " ".join(out["questions"]).lower()
    # Esperamos ver pelo menos "parede" (murs), "laje" (plancher), "escada"
    assert "parede" in joined, f"'parede' em falta: {out['questions']}"
    assert "laje" in joined, f"'laje' em falta: {out['questions']}"
    assert "escada" in joined, f"'escada' em falta: {out['questions']}"


def test_preserves_anomaly_structure():
    an = [
        {"code": "GEO-04", "level": "bloquant", "message": "Baie dépassant le mur.",
         "fix": "Vérifier la portée."},
        {"code": "SEM-02", "level": "info", "message": "Comble aménagé non précisé.", "fix": None},
    ]
    out = _translate_pt_output({"country": "PT", "anomalies": an})
    assert len(out["anomalies"]) == 2
    for i in range(2):
        assert out["anomalies"][i]["code"] == an[i]["code"]
        assert out["anomalies"][i]["level"] == an[i]["level"]
    # fix=None preservado
    assert out["anomalies"][1]["fix"] is None
    # message traduzida: termos técnicos chave devem aparecer em PT
    msgs = " ".join(a["message"].lower() for a in out["anomalies"])
    assert ("parede" in msgs) or ("vão" in msgs) or ("sótão" in msgs), (
        f"nenhum termo PT em anomalies.message: {[a['message'] for a in out['anomalies']]}"
    )


def test_translates_points_list_pt():
    out = _translate_pt_output({"country": "PT", "points": [
        "Vérifier la portée du plancher et la section du linteau.",
    ]})
    joined = out["points"][0].lower()
    assert ("laje" in joined) or ("lintel" in joined), f"nenhum termo PT em points: {out['points']}"


def test_non_pt_country_no_mutation():
    """Country ausente ou falsy → pass-through estrito."""
    for p in [{}, {"country": None}, {"country": ""}, {"country": "fr"}]:
        frozen = copy.deepcopy(p)
        out = _translate_pt_output(dict(p))
        # pode acrescentar nada; valores iguais
        assert out == frozen or out == p


def test_tr_pt_safe_on_empty_and_none():
    assert _tr_pt("") == ""
    assert _tr_pt(None) is None
    assert _tr_pt(42) == 42
