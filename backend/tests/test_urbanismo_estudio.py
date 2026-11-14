"""Estúdio de Projeto (14/11): vãos editados são limpos; materiais válidos passam ao processo."""
from routes.urbanismo import EstudioIn, _clean_vaos


def test_vaos_limpos():
    out = _clean_vaos([{"fachada": "frente", "tipo": "janela", "piso": 1, "x0": 2, "x1": 3.2, "z0": 3.9, "z1": 5.3, "compartimento": "Quarto"},
                       {"fachada": "telhado", "tipo": "janela", "x0": 0, "x1": 1, "z0": 0, "z1": 1},
                       {"fachada": "frente", "tipo": "<script>", "x0": 0, "x1": 1, "z0": 0, "z1": 1},
                       {"fachada": "esquerda", "tipo": "porta", "x0": 3, "x1": 2, "z0": 0, "z1": 2}])
    assert out == [{"fachada": "frente", "tipo": "janela", "piso": 1, "compartimento": "Quarto", "x0": 2.0, "x1": 3.2, "z0": 3.9, "z1": 5.3}]


def test_estudio_valida_cores_e_telhado():
    import pytest
    from pydantic import ValidationError
    assert EstudioIn(telhado="quatro_aguas", cor_fachada="#e6d6b8").telhado == "quatro_aguas"
    with pytest.raises(ValidationError):
        EstudioIn(cor_fachada="red; drop")
    with pytest.raises(ValidationError):
        EstudioIn(telhado="cupula")
