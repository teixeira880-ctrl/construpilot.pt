"""Ferramentas do Assistente (PT): esquemas estritos e execução de cada motor."""
import json

import pytest

from engines.calc_lots import outils as O


def _check_strict(s, path):
    if "anyOf" in s:
        for i, sub in enumerate(s["anyOf"]):
            _check_strict(sub, f"{path}.anyOf[{i}]")
        return
    t = s.get("type")
    types = t if isinstance(t, list) else [t]
    if "enum" in s and "null" in types:
        assert None in s["enum"], f"{path}: enum anulável sem None"
    if "object" in types:
        assert s.get("additionalProperties") is False, f"{path}: additionalProperties"
        assert sorted(s.get("required", [])) == sorted(s["properties"]), f"{path}: required != properties"
        for k, v in s["properties"].items():
            _check_strict(v, f"{path}.{k}")
    if "array" in types:
        _check_strict(s["items"], f"{path}[]")


@pytest.mark.parametrize("tool", O.CALC_TOOLS, ids=lambda t: t["name"])
def test_esquema_estrito(tool):
    assert tool["type"] == "function" and tool["strict"] is True and tool["description"]
    assert tool["parameters"]["type"] == "object"
    _check_strict(tool["parameters"], tool["name"])
    json.dumps(tool)


def test_nomes_e_rotulos():
    assert len(O.CALC_TOOL_NAMES) == len(O.CALC_TOOLS)
    assert set(O.PROGRESS_LABELS) == O.CALC_TOOL_NAMES
    assert all(n in O.PROTOCOL_PT for n in O.CALC_TOOL_NAMES) and "os motores calculam, tu restituis" in O.PROTOCOL_PT


def _nulls(s):
    """Objeto com todas as propriedades presentes (null quando anulável); objetos obrigatórios preenchidos recursivamente."""
    if "anyOf" in s:
        return None
    t = s.get("type")
    types = t if isinstance(t, list) else [t]
    if "null" in types:
        return None
    if "object" in types:
        return {k: _nulls(v) for k, v in s["properties"].items()}
    if "array" in types:
        return []
    return None


def _schema(name):
    return next(t for t in O.CALC_TOOLS if t["name"] == name)["parameters"]


def _sub(s, *keys):
    for k in keys:
        s = s["properties"][k]
        if "anyOf" in s:
            s = s["anyOf"][0]
        if s.get("type") in ("array", ["array", "null"]):
            s = s["items"]
    return s


def _fill(name, **over):
    args = _nulls(_schema(name))
    args.update(over)
    return args


def _o(name, *keys, **over):
    d = _nulls(_sub(_schema(name), *keys))
    d.update(over)
    return d


CASOS = {
    "pre_certificado_reh": lambda: _fill("pre_certificado_reh", area_util_m2=110, concelho="Porto", obra="existente", ano_construcao=1985,
                                         aquecimento=_o("pre_certificado_reh", "aquecimento", tipo="bomba_calor")),
    "calcul_instalacoes": lambda: _fill("calcul_instalacoes",
                                        eletricidade=_o("calcul_instalacoes", "eletricidade", divisoes=[
                                            _o("calcul_instalacoes", "eletricidade", "divisoes", tipo="sala", area_m2=28),
                                            _o("calcul_instalacoes", "eletricidade", "divisoes", tipo="quarto", area_m2=12),
                                            _o("calcul_instalacoes", "eletricidade", "divisoes", tipo="cozinha", area_m2=10)],
                                            equipamentos=_o("calcul_instalacoes", "eletricidade", "equipamentos", placa="trifasica", carregamento_ve_kw=7.4)),
                                        canalizacao=_o("calcul_instalacoes", "canalizacao", dispositivos=[
                                            _o("calcul_instalacoes", "canalizacao", "dispositivos", tipo="lavatorio", quantidade=2),
                                            _o("calcul_instalacoes", "canalizacao", "dispositivos", tipo="autoclismo", quantidade=1),
                                            _o("calcul_instalacoes", "canalizacao", "dispositivos", tipo="chuveiro")])),
    "calcul_aquecimento": lambda: _fill("calcul_aquecimento", concelho="Braga", divisoes=[
        _o("calcul_aquecimento", "divisoes", tipo="sala", area_m2=25, paredes=[
            _o("calcul_aquecimento", "divisoes", "paredes", area_m2=20, U=0.45), _o("calcul_aquecimento", "divisoes", "paredes", area_m2=4, U=2.4)]),
        _o("calcul_aquecimento", "divisoes", tipo="casa_de_banho", area_m2=5, paredes=[_o("calcul_aquecimento", "divisoes", "paredes", area_m2=6, U=0.45)])],
        bomba_calor=_o("calcul_aquecimento", "bomba_calor")),
    "calcul_isolamento": lambda: _fill("calcul_isolamento", sistema="etics", concelho="Guarda", area_m2=80),
    "calcul_photovoltaique": lambda: _fill("calcul_photovoltaique", puissance_kwc=4, code_postal="4000-123", consommation_kwh=4000, module=None),
    "calcul_redes": lambda: _fill("calcul_redes",
                                  aguas_pluviais=_o("calcul_redes", "aguas_pluviais", vertentes=[_o("calcul_redes", "aguas_pluviais", "vertentes", area_planta_m2=60)]),
                                  fossa_septica=_o("calcul_redes", "fossa_septica", tipologia=3, solo="areia_fina"),
                                  ventilacao=_o("calcul_redes", "ventilacao", compartimentos=[
                                      _o("calcul_redes", "ventilacao", "compartimentos", tipo="sala", area_m2=30),
                                      _o("calcul_redes", "ventilacao", "compartimentos", tipo="cozinha", area_m2=10)])),
    "calcul_couverture": lambda: _fill("calcul_couverture", vent=_o("calcul_couverture", "vent", hauteur_m=8),
                                       neige=_o("calcul_couverture", "neige", zona_neve="Z1", altitude_m=800),
                                       tuiles=_o("calcul_couverture", "tuiles", type_tuile="canal", pente_pct=30)),
    "verifier_accessibilite": lambda: _fill("verifier_accessibilite", contexte="pt",
                                            mesures=_o("verifier_accessibilite", "mesures", pente_rampe_pct=7, longueur_rampe_m=4, porte_entree_utile_m=0.9)),
    "calcul_structure": lambda: _fill("calcul_structure", element="poutre_ba", portee_m=5.0, b_m=0.25, h_m=0.45, g_kn_m=12.0, q_kn_m=6.0),
}


def test_todos_os_casos_cobertos():
    assert set(CASOS) == O.CALC_TOOL_NAMES


@pytest.mark.parametrize("name", sorted(CASOS))
def test_run(name):
    args = CASOS[name]()
    assert set(args) == set(_schema(name)["properties"])
    r = O.run(name, args)
    assert r["pdf"][:4] == b"%PDF" and r["png"][:4] == b"\x89PNG"
    assert r["titre"] and r["resume"].strip()
    assert r["resume"].splitlines()[-1] == O.FIM
    assert all(not ln.startswith("??") for ln in r["resume"].splitlines())
    json.dumps(r["data"])


def test_valores_impostos_reh_e_placa():
    r = O.run("pre_certificado_reh", CASOS["pre_certificado_reh"]())
    assert "Classe " in r["resume"] and "Hipótese: " in r["resume"] and r["data"]["nuts"] == "Grande Porto"
    sem = O.run("calcul_instalacoes", _fill("calcul_instalacoes", eletricidade=_o("calcul_instalacoes", "eletricidade", divisoes=[
        _o("calcul_instalacoes", "eletricidade", "divisoes", tipo="sala", area_m2=20)],
        equipamentos=_o("calcul_instalacoes", "eletricidade", "equipamentos", placa="sem_placa"))))
    assert "Placa" not in sem["resume"]


def test_erros():
    with pytest.raises(ValueError):
        O.run("calcul_instalacoes", _fill("calcul_instalacoes"))
    with pytest.raises(ValueError):
        O.run("pre_certificado_reh", _fill("pre_certificado_reh", area_util_m2=100, concelho="Paris"))
    with pytest.raises(ValueError):
        O.run("ferramenta_inexistente", {})
