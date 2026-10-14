"""Testes do motor de regras do módulo «Autorização de obras» (RJUE / DL 555/99)."""

from engines.autorizacao_obras_pt.rules import diagnosticar


def test_anexo_escassa_relevancia():
    r = diagnosticar({
        "tipo_obra": "anexo",
        "altura_m": 2.0,
        "area_implantacao_m2": 8.0,
        "confina_via_publica": False,
        "zona_protegida": False,
        "imovel_classificado": False,
    })
    assert r["procedimento"] == "isento"
    assert "6.º-A" in r["fundamento_legal"]
    assert r["regra_aplicada"] == "ESCASSA_RELEVANCIA_ANEXO"
    # tem pelo menos uma referência legal com url DRE/PGDL
    assert any("6.º-A" in ref["artigo"] for ref in r["referencias_legais"])


def test_anexo_confinar_via_publica_nao_escassa_relevancia():
    r = diagnosticar({
        "tipo_obra": "anexo",
        "altura_m": 2.0,
        "area_implantacao_m2": 8.0,
        "confina_via_publica": True,
    })
    # falha a condição "não confina com a via pública" → cai no fallback
    assert r["procedimento"] in ("licenciamento", "comunicacao_previa")


def test_ampliacao_comunicacao_previa_com_pdm():
    r = diagnosticar({
        "tipo_obra": "ampliacao",
        "area_construcao_criada_m2": 40.0,
        "altura_m": 3.0,
        "tem_pdm_com_parametros": True,
    })
    assert r["procedimento"] == "comunicacao_previa"
    assert "arquiteto" in r["tecnicos_obrigatorios"]
    assert "4.º" in r["fundamento_legal"]


def test_ampliacao_sem_pdm_vai_para_licenciamento():
    r = diagnosticar({
        "tipo_obra": "ampliacao",
        "area_construcao_criada_m2": 40.0,
        "altura_m": 3.0,
        "tem_pdm_com_parametros": False,
    })
    assert r["procedimento"] == "licenciamento"
    assert r["regra_aplicada"] == "AMPLIACAO_LICENCIAMENTO"


def test_moradia_nova_licenciamento():
    r = diagnosticar({
        "tipo_obra": "moradia_nova",
        "area_construcao_total_m2": 200.0,
    })
    assert r["procedimento"] == "licenciamento"
    assert set(r["tecnicos_obrigatorios"]) >= {"arquiteto", "engenheiro_estruturas"}
    assert any("4.º" in ref["artigo"] for ref in r["referencias_legais"])


def test_obras_interiores_isentas():
    r = diagnosticar({
        "tipo_obra": "interiores",
        "altera_fachada": False,
        "altera_cobertura": False,
        "altera_uso": False,
    })
    assert r["procedimento"] == "isento"
    assert "6.º" in r["fundamento_legal"]


def test_obras_interiores_com_alteracao_de_uso_nao_isentas():
    r = diagnosticar({
        "tipo_obra": "interiores",
        "altera_uso": True,
    })
    # alteração de uso NÃO é isenta → cai no fallback
    assert r["procedimento"] in ("licenciamento", "comunicacao_previa")


def test_piscina_lugar_escassa_relevancia():
    # Piscina pequena associada a edificação principal maior
    r = diagnosticar({
        "tipo_obra": "piscina",
        "tem_edificacao_principal": True,
        "area_implantacao_m2": 15.0,
        "area_construcao_total_m2": 160.0,
    })
    assert r["procedimento"] == "isento"
    assert r["regra_aplicada"] == "PISCINA_ESCASSA_RELEVANCIA"


def test_piscina_sem_edificacao_principal_vai_para_cp():
    r = diagnosticar({
        "tipo_obra": "piscina",
        "tem_edificacao_principal": False,
        "area_implantacao_m2": 30.0,
    })
    assert r["procedimento"] == "comunicacao_previa"
    assert r["regra_aplicada"] == "PISCINA_COMUNICACAO_PREVIA"


def test_zona_protegida_forca_licenciamento():
    r = diagnosticar({
        "tipo_obra": "anexo",
        "altura_m": 2.0,
        "area_implantacao_m2": 8.0,
        "confina_via_publica": False,
        "zona_protegida": True,
    })
    assert r["procedimento"] == "licenciamento"
    assert r["regra_aplicada"] == "ZONA_PROTEGIDA_IMOVEL_CLASSIFICADO"
    assert any("zona" in a.lower() or "classificado" in a.lower() for a in r["avisos"])


def test_imovel_classificado_forca_licenciamento():
    r = diagnosticar({
        "tipo_obra": "interiores",
        "imovel_classificado": True,
    })
    assert r["procedimento"] == "licenciamento"
    assert r["regra_aplicada"] == "ZONA_PROTEGIDA_IMOVEL_CLASSIFICADO"


def test_muro_vedacao_escassa_relevancia():
    r = diagnosticar({
        "tipo_obra": "muro",
        "subtipo_muro": "vedacao",
        "altura_m": 1.6,
        "confina_via_publica": False,
    })
    assert r["procedimento"] == "isento"
    assert r["regra_aplicada"] == "ESCASSA_RELEVANCIA_MURO"


def test_controlo_pdm_altura_excedida_gera_aviso():
    r = diagnosticar({
        "tipo_obra": "moradia_nova",
        "altura_m": 10.0,
        "pdm_altura_max_m": 7.5,
    })
    assert r["controlos_pdm"]["altura_ok"] is False
    assert any("altura" in a.lower() for a in r["avisos"])


def test_resposta_contem_url_fonte_oficial():
    r = diagnosticar({"tipo_obra": "moradia_nova"})
    # Pelo menos uma das referências legais tem URL para o PGDL / DR
    assert any("pgdlisboa" in (ref.get("url") or "") or "diariodarepublica" in (ref.get("url") or "")
               for ref in r["referencias_legais"])
    assert r["lei_base"]["codigo"] == "DL 555/99"
