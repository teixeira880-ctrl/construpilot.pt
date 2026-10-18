"""Testes do parsing de brief e lógica de prioridade utilizador vs defaults."""
from __future__ import annotations

import pytest

from engines.bet_agent.brief import BriefError, hypotheses_used, parse_user_brief
from engines.bet_agent.models.brief import ConcreteClass, SlabType


def test_parse_minimal_brief_returns_empty_user_brief() -> None:
    ub = parse_user_brief({})
    assert ub.materials.slab_type is None
    assert ub.materials.concrete_class is None
    assert ub.requested_deliverables == set()


def test_parse_full_brief_preserves_user_values() -> None:
    ub = parse_user_brief({
        "materials": {
            "slab_type": "aligeirada_vigotas_abobadilhas",
            "concrete_class": "C30/37",
        },
        "requested_deliverables": [
            "planta_fundacoes",
            "verificacao_sismica_np_en_1998_1",
        ],
        "notes": "moradia reticulada",
    })
    assert ub.materials.slab_type == SlabType.ALIGEIRADA_VIGOTAS_ABOBADILHAS
    assert ub.materials.concrete_class == ConcreteClass.C30_37
    assert "planta_fundacoes" in [d.value for d in ub.requested_deliverables]


def test_parse_rejects_unknown_slab_type() -> None:
    with pytest.raises(BriefError):
        parse_user_brief({"materials": {"slab_type": "nao_existente"}})


def test_parse_rejects_non_dict_input() -> None:
    with pytest.raises(BriefError):
        parse_user_brief("not a dict")  # type: ignore[arg-type]


def test_hypotheses_user_imposed_wins_over_default() -> None:
    ub = parse_user_brief({"materials": {"slab_type": "macica", "concrete_class": "C30/37"}})
    hyp = hypotheses_used(ub)
    user_slab = [h for h in hyp if h.key == "slab_type"][0]
    assert user_slab.user_imposed is True
    assert user_slab.default_used is False
    assert user_slab.value == "macica"


def test_hypotheses_default_used_when_user_omits() -> None:
    ub = parse_user_brief({})
    hyp = hypotheses_used(ub)
    default_slab = [h for h in hyp if h.key == "slab_type"][0]
    assert default_slab.user_imposed is False
    assert default_slab.default_used is True
    assert default_slab.value == SlabType.ALIGEIRADA_VIGOTAS_ABOBADILHAS.value


def test_hypotheses_seismic_only_present_when_user_provides() -> None:
    ub = parse_user_brief({})
    hyp = hypotheses_used(ub)
    keys = [h.key for h in hyp]
    assert "seismic.zone" not in keys  # não aparece se utilizador não deu

    ub2 = parse_user_brief({"seismic": {"zone": "1.3", "soil_class": "C"}})
    hyp2 = hypotheses_used(ub2)
    keys2 = {h.key: h for h in hyp2}
    assert keys2["seismic.zone"].user_imposed is True
    assert keys2["seismic.soil_class"].user_imposed is True
