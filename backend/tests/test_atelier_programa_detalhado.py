"""Ateliê Arquiteto: prompt longo com lista de divisões por piso → áreas respeitadas, coerência verificada, pedidos registados."""
from pathlib import Path

from engines.atelier_archi import programme as P, generateur as G

PROMPT = (Path(__file__).parent / "fixtures_prompt_moradia_200.txt").read_text(encoding="utf-8")


def test_lista_detalhada_respeita_areas_e_pisos():
    p = P.programme(PROMPT)
    assert p["detalhado"] and p["niveaux"] == 2
    por_nome = {x["nom"]: x for x in p["pieces"]}
    assert por_nome["Sala de estar e jantar em open space"]["surface"] == 35.0
    assert por_nome["Suite principal"]["niveau"] == 1 and por_nome["Suite principal"]["cle"] == "suite"
    assert por_nome["Casa de banho da suite"]["cle"] == "sde"
    assert por_nome["Closet privativo"]["cle"] == "dressing"
    assert por_nome["Escritório ou quarto de hóspedes"]["cle"] == "bureau"
    assert sum(x["surface"] for x in p["pieces"] if x["niveau"] == 0) == 88.0   # 110 − 22 de circulação
    assert sum(x["surface"] for x in p["pieces"] if x["niveau"] == 1) == 75.0   # 90 − 15 de circulação
    assert p["garage"]["largeur"] == 6.0          # garagem para dois automóveis
    assert p["toiture"] == "plana"
    assert any("coerente com os 110" in h for h in p["hypotheses"])
    assert any("200 m² = área anunciada" in h for h in p["hypotheses"])


def test_nada_do_prompt_fica_ignorado():
    p = P.programme(PROMPT)
    titulos = " | ".join(x["titulo"] for x in p["pedidos"])
    for esperado in ("Piscina 8 × 4 m", "Estrutura", "Térmica", "Bomba de calor", "Fotovoltaico", "BIM", "Mapa de quantidades",
                     "Planeamento", "Renders", "Conformidade"):
        assert esperado in titulos, esperado
    rotas = {x["rota"] for x in p["pedidos"] if x["estado"] == "continuar"}
    assert {"/estudos-engenharia", "/planos-execucao", "/bim", "/assistant", "/planning", "/estudio-imagens"} <= rotas


def test_gera_modelo_com_o_programa_detalhado():
    r = G.generer(P.programme(PROMPT))
    assert r["modelo"]["pisos"] and len(r["modelo"]["pisos"]) == 2
    assert r["modelo"]["paredes"]


def test_coerencia_detecta_diferenca():
    txt = PROMPT.replace("Despensa: 3 m²", "Despensa: 9 m²")
    p = P.programme(txt)
    assert any("≠ 110 m² indicados" in h for h in p["hypotheses"])


def test_prompt_curto_mantem_comportamento_anterior():
    p = P.programme("Moradia T3 de 120 m² com garagem")
    assert not p.get("detalhado") and p["chambres"] == 3 and p["garage"]
