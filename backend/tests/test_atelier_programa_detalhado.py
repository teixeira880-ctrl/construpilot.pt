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


def test_verificacao_regulamentar_e_programa():
    from engines import estudio_projeto as EP
    from engines.atelier_archi import verificacao as V
    p = P.programme(PROMPT)
    r = G.generer(p)
    v = V.verificar(r["modelo"], EP.derivar(r["modelo"]), p)
    fontes = {x["fonte"] for x in v["resultados"]}
    assert {"RGEU art. 65.º, n.º 1", "RGEU art. 66.º", "RGEU art. 68.º", "RGEU art. 69.º", "RGEU art. 71.º"} <= fontes
    assert v["resumo"]["falha"] == 0                     # a moradia gerada cumpre as regras verificadas
    assert any(x["regra"] == "Área por piso" for x in v["resultados"])
    assert "técnico habilitado" in v["nota"]


def test_verificacao_detecta_quarto_pequeno():
    """O gerador já respeita os mínimos; a verificação tem de apanhar um quarto reduzido depois, no Estúdio."""
    from engines import estudio_projeto as EP
    from engines.atelier_archi import verificacao as V
    r = G.generer(P.programme(PROMPT))
    d = EP.derivar(r["modelo"])
    for dv in d["divisoes"]:
        if dv["nome"] == "Quarto 3":
            dv["area_m2"] = 6.0
    v = V.verificar(r["modelo"], d)
    falhas = [x for x in v["resultados"] if x["estado"] == "falha"]
    assert any("Quarto 3" in x["msg"] and x["fonte"] == "RGEU art. 66.º" for x in falhas), falhas


def test_gerador_nunca_desce_dos_minimos_mesmo_com_programa_pequeno():
    from engines import estudio_projeto as EP
    from engines.atelier_archi import verificacao as V
    r = G.generer(P.programme(PROMPT.replace("Quarto 3: 15 m²", "Quarto 3: 6 m²")))
    v = V.verificar(r["modelo"], EP.derivar(r["modelo"]))
    assert not [x for x in v["resultados"] if x["estado"] == "falha" and x["fonte"] == "RGEU art. 69.º"]


def test_estagio_recuado_gera_terraco_sem_divisao_a_definir():
    from engines import estudio_projeto as EP
    r = G.generer(P.programme(PROMPT))
    d = EP.derivar(r["modelo"])
    assert not [x for x in d["divisoes"] if "definir" in x["nome"]]
    assert d["medicoes"]["terracos"]
    assert any("terraço" in a for a in r["avisos"])


def test_exteriores_do_prompt_sao_objetos_editaveis_e_medidos():
    from engines import estudio_projeto as EP
    p = P.programme(PROMPT)
    assert p["exteriores"]["piscina"] == [8.0, 4.0] and p["exteriores"]["piscina_medidas_dadas"]
    r = G.generer(p)
    tipos = {o["tipo"] for o in r["modelo"]["objetos"]}
    assert {"piscina", "terraco_pedra", "pergola", "relvado"} <= tipos
    d = EP.derivar(r["modelo"])
    ext = {e["tipo"]: e for e in d["medicoes"]["exteriores"]}
    assert ext["piscina"]["area_m2"] == 32.0 and ext["piscina"]["perimetro_m"] == 24.0
    assert d["limites"][3] > 20                                   # a planta enquadra o jardim e a piscina
    piscina = next(x for x in p["pedidos"] if x["titulo"].startswith("Piscina"))
    assert piscina["estado"] == "gerado"
    # editável: mudar as medidas da piscina no modelo muda a medição
    m = dict(r["modelo"])
    m["objetos"] = [dict(o, largura_m=10.0, prof_m=5.0) if o["tipo"] == "piscina" else o for o in m["objetos"]]
    d2 = EP.derivar(EP.normalizar(m))
    assert next(e for e in d2["medicoes"]["exteriores"] if e["tipo"] == "piscina")["area_m2"] == 50.0


def test_verificacao_explica_circulacao_e_paredes():
    from engines import estudio_projeto as EP
    from engines.atelier_archi import verificacao as V
    p = P.programme(PROMPT)
    r = G.generer(p)
    v = V.verificar(r["modelo"], EP.derivar(r["modelo"]), p)
    assert any(x["regra"] == "Circulações e paredes" for x in v["resultados"])


def test_sem_exteriores_no_prompt_nao_ha_objetos():
    r = G.generer(P.programme("Moradia T3 de 120 m² com garagem"))
    assert not r["modelo"].get("objetos")


def test_planta_aberta_no_rc_reduz_o_corredor_sem_perder_acessos():
    from engines import estudio_projeto as EP
    r = G.generer(P.programme(PROMPT))
    d = EP.derivar(r["modelo"])
    assert d["ok"]
    hall = [x for x in d["divisoes"] if x["piso"] == "p0" and x["nome"] == "Hall"]
    assert not hall or hall[0]["area_m2"] < 12                     # antes: ~20 m² de corredor a todo o comprimento
    assert not [a for a in r["avisos"] if "não colocados" in a]     # todas as portas couberam
    sala = next(x for x in d["divisoes"] if x["nome"].startswith("Sala de estar"))
    assert 30 <= sala["area_m2"] <= 45


def test_ajuste_a_area_pretendida():
    from engines import estudio_projeto as EP
    from engines.atelier_archi import verificacao as V
    p = P.programme(PROMPT)
    pg, r = G.ajustar_area(p, 200.0)
    d = EP.derivar(r["modelo"])
    b = d["medicoes"]["totais"]["area_bruta_construcao_m2"] - pg["garage"]["surface"]
    assert abs(b - 200) / 200 <= 0.05
    assert V.verificar(r["modelo"], d, pg)["resumo"]["falha"] == 0
    assert any("ajustadas para 200" in a for a in r["avisos"])


def test_ajuste_nunca_desce_dos_minimos():
    pg, _ = G.ajustar_area(P.programme(PROMPT), 60.0)
    por = {x["nom"]: x["surface"] for x in pg["pieces"]}
    assert por["Suite principal"] >= 11.0 and por["Quarto 2"] >= 9.5 and por["Sala de estar e jantar em open space"] >= 16.0


def test_edicao_por_frase():
    from engines import estudio_projeto as EP
    from engines.atelier_archi import edicao as ED
    m = G.generer(P.programme(PROMPT))["modelo"]
    a = ED.interpretar("aumenta a sala 2 metros; põe janelas maiores no quarto 2; piscina de 10 x 5", m)
    assert [x["acao"] for x in a] == ["esticar", "vaos_maiores", "objeto_medidas"]
    assert a[1]["metros"] == 0.4                                      # «quarto 2» não é lido como 2 m
    m2, feitos, falhas = ED.executar(m, a)
    assert len(feitos) == 3 and not falhas
    d0, d2 = EP.derivar(m), EP.derivar(m2)
    sala0 = next(x for x in d0["divisoes"] if x["nome"].startswith("Sala"))["area_m2"]
    sala2 = next(x for x in d2["divisoes"] if x["nome"].startswith("Sala"))["area_m2"]
    assert sala2 > sala0 + 3 and d2["ok"]
    assert next(e for e in d2["medicoes"]["exteriores"] if e["tipo"] == "piscina")["area_m2"] == 50.0


def test_edicao_reduzir_e_materiais_e_recusas():
    from engines.atelier_archi import edicao as ED
    m = G.generer(P.programme(PROMPT))["modelo"]
    _, feitos, falhas = ED.executar(m, ED.interpretar("pavimento da suite em soalho de carvalho", m))
    assert feitos and not falhas
    _, feitos, falhas = ED.executar(m, ED.interpretar("diminui o escritório 20 metros", m))
    assert not feitos and falhas                                       # nunca parte o modelo
    assert ED.interpretar("olá, tudo bem?", m) == []


def test_frase_forma_em_l_e_estilo_editaveis():
    """«Faz a moradia em L com vários recortes e o interior provençal»: forma e estilo aplicados, maqueta válida."""
    from engines import estudio_projeto as EP
    from engines.atelier_archi import edicao as ED
    from engines.atelier_archi import forma as FO
    from engines.atelier_archi import generateur as GEN
    from engines.atelier_archi import programme as PROG
    for txt in ("moradia térrea T3 com suite, garagem, piscina", "moradia de 2 pisos T4 160 m2"):
        m = GEN.generer(PROG.programme(txt, "pt"))["modelo"]
        acoes, sobras = ED.interpretar_partes("Faz a moradia em L com vários recortes e o interior provençal", m)
        assert [a["acao"] for a in acoes] == ["forma", "estilo"] and sobras == []
        m2, feitos, falhas = ED.executar(m, acoes)
        assert not falhas, falhas
        assert not EP.derivar(m2)["erros"]
        assert any(w["id"] == "ala_galeria" for w in m2["paredes"])
        assert m2["materiais"]["pavimento"] == "tijoleira"
        m3, _ = FO.retangular(m2)
        assert not EP.derivar(m3)["erros"]


def test_acoes_ia_normalizadas():
    from engines.atelier_archi import edicao as ED
    assert ED.normalizar_acao({"acao": "op", "op": {"tipo": "quatro_aguas"}})["op"]["op"] == "cobertura"
    assert ED.normalizar_acao({"acao": "op", "op": {"x": 1}}) is None
