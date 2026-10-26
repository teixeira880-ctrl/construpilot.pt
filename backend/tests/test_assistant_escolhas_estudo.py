"""Paridade com o .fr : perguntas em cartões clicáveis, um só caminho de estudo BET, acompanhamento do estudo."""
from fastapi.routing import APIRoute

from routes import assistant as A

PRO = {"user_id": "u1", "account_type": "professionnel", "role": "user"}
PART = {"user_id": "u2", "account_type": "particulier", "role": "user"}


def _names(user):
    return {t.get("name") for t in A.tools_for(user)}


def test_pro_um_so_caminho_de_estudo_e_cartoes():
    n = _names(PRO)
    assert {"ask_user_choices", "generate_full_bet_study", "read_full_bet_study"} <= n
    assert not (n & A.BET_SUPERSEDED_TOOL_NAMES)


def test_particular_tem_cartoes():
    assert "ask_user_choices" in _names(PART)


def test_cartoes_validados_e_limitados():
    args = {"intro": "Antes do estudo", "submit_label": "Lançar o estudo", "questions": [
        {"id": "lajes", "label": "Lajes", "multi": False, "allow_other": True, "default_option_id": "macica",
         "options": [{"id": "macica", "label": "Laje maciça (recomendado)", "hint": None}] + [{"id": f"o{i}", "label": f"O{i}", "hint": "x"} for i in range(9)]},
        {"id": "vazia", "label": "Sem opções", "multi": False, "allow_other": False, "default_option_id": None, "options": []},
    ]}
    r = A.user_choices(args)
    assert r["ok"] and r["kind"] == "user_choices" and r["submit_label"] == "Lançar o estudo"
    assert len(r["questions"]) == 1 and len(r["questions"][0]["options"]) == 6
    assert "hint" not in r["questions"][0]["options"][0] and r["questions"][0]["options"][1]["hint"] == "x"
    assert A.user_choices({"questions": []})["ok"] is False


def test_estudo_publico_em_portugues_sem_campos_pesados():
    j = A._bet_public({"job_id": "b1", "status": "running", "step": "Lecture des plans par IA et relevé du modèle bâtiment",
                       "model": {"x": 1}, "pages": [1], "questions": ["à préciser"]})
    assert "model" not in j and "pages" not in j
    assert j["step"].startswith("Leitura") and j["pct"] == 32
    assert A._bet_public({"status": "done"})["pct"] == 100


def test_rotas_de_acompanhamento():
    paths = {r.path for r in A.bet_studies_router.routes if isinstance(r, APIRoute)}
    assert {"/bet-studies", "/bet-studies/{job_id}"} <= paths
    assert any(isinstance(r, APIRoute) and r.path == "/assistant/bet-progress/{conversation_id}" for r in A.router.routes)
    assert "ask_user_choices" in A.TOOL_STATUS_PT


def test_instrucoes_pro_sem_caminhos_concorrentes():
    assert "ask_user_choices" in A.CHOICES_AND_STUDY_PT and "generate_full_bet_study" in A.CHOICES_AND_STUDY_PT
