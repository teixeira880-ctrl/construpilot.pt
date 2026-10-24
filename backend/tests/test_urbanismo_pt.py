"""Motor de urbanismo PT (porta do «Éditeur de volumes v2» francês): geometria, quadro de áreas,
verificação dos parâmetros do PDM introduzidos pelo utilizador, RGEU / Código Civil, enquadramento RJUE
(motor existente) e desenhos / PDFs em português. Dados fictícios, sem rede, sem IA."""
import io
import zipfile

import pytest
from pypdf import PdfReader

from engines.urbanismo_pt import exemplo, pdf as UP, regras as R, volumes as V

PNG = b"\x89PNG\r\n\x1a\n"


def _proc(**kw):
    base = {"title": "Teste", "tipo_obra": "moradia_nova", "terreno": {}, "enquadramento": {}, "pdm": {}, "parametros": {},
            "volume": {"plot_l_m": 20, "plot_w_m": 15, "footprint_l_m": 8, "footprint_w_m": 6, "levels": 2,
                       "storey_h_m": 2.8, "setback_front_m": 5, "setback_side_m": 3, "roof_type": "duas_aguas"}}
    for k, v in kw.items():
        if isinstance(v, dict) and isinstance(base.get(k), dict):
            base[k] = {**base[k], **v}
        else:
            base[k] = v
    return base


def _item(verif, code):
    return next(i for i in verif["verificacoes"] if i["codigo"] == code)


# ------------------------------------------------------------------ geometria / quadro ----
def test_quadro_retangulo():
    q = R.quadro_areas(_proc()["volume"])
    assert q["area_terreno_m2"] == 300 and q["area_implantacao_m2"] == 48
    assert q["area_construcao_m2"] == 96                       # 48 × 2 pisos
    assert q["indice_ocupacao_pct"] == 16.0 and q["indice_utilizacao"] == 0.32
    assert q["afastamentos_m"] == {"frontal": 5, "lateral_esquerdo": 3, "lateral_direito": 9, "tardoz": 4}
    assert q["altura_fachada_m"] == 5.6 and q["altura_total_m"] == 7.6
    assert q["pe_direito_livre_m"] == 2.5                       # 2,80 − 0,30


def test_area_terreno_indicada_prevalece():
    q = R.quadro_areas(_proc()["volume"], {"area_terreno_m2": 400})
    assert q["area_terreno_m2"] == 400 and q["indice_ocupacao_pct"] == 12.0
    assert "indicada" in q["area_terreno_origem"]


def test_forma_L_e_T_area():
    vol = {**_proc()["volume"], "shape": "L", "footprint_l_m": 12, "footprint_w_m": 10, "wing_l_m": 5, "wing_w_m": 4}
    assert R.quadro_areas(vol)["area_implantacao_m2"] == 100     # 120 − 20
    volt = {**vol, "shape": "T", "wing_l_m": 4, "wing_w_m": 4}
    assert R.quadro_areas(volt)["area_implantacao_m2"] == 12 * 4 + 4 * 6
    assert len(V.main_rects(vol)) == 2 and len(V.main_rects(volt)) == 2


def test_anexo_sobreposto_contado_uma_vez():
    vol = {**_proc()["volume"], "blocks": [{"l_m": 4, "w_m": 3, "x_m": 3, "y_m": 5}]}   # dentro da construção
    q = R.quadro_areas(vol)
    assert q["area_implantacao_m2"] == 48


def test_altura_total_nunca_inferior_a_fachada():
    h = V.heights({"levels": 2, "storey_h_m": 3, "total_h_m": 4, "roof_type": "plana"})
    assert h["altura_total_m"] == 6.0


# ------------------------------------------------------------------ PDM (valores do utilizador) ----
def test_sem_pdm_nada_e_inventado():
    v = R.verificar(_proc())
    for code in ("PDM_IU", "PDM_IO", "PDM_ALTURA_FACHADA", "PDM_N_PISOS", "PDM_AFAST_FRONTAL"):
        it = _item(v, code)
        assert it["resultado"] == "sem_dados" and it["limite"] is None
        assert it["fonte"]["status"] == "parametro_utilizador"
    assert "Índice de utilização do solo máximo (Iu)" in v["parametros_em_falta"]


def test_pdm_conforme_e_nao_conforme():
    v = R.verificar(_proc(pdm={"io_max_pct": 15, "iu_max": 0.5, "altura_fachada_max_m": 6.5, "n_pisos_max": 1,
                               "afastamento_frontal_min_m": 5, "afastamento_lateral_min_m": 3, "afastamento_tardoz_min_m": 6}))
    assert _item(v, "PDM_IO")["resultado"] == "nao_conforme"        # 16 % > 15 %
    assert _item(v, "PDM_IU")["resultado"] == "conforme"
    assert _item(v, "PDM_ALTURA_FACHADA")["resultado"] == "conforme"
    assert _item(v, "PDM_N_PISOS")["resultado"] == "nao_conforme"   # 2 > 1
    assert _item(v, "PDM_AFAST_FRONTAL")["resultado"] == "conforme"   # limite igual
    assert _item(v, "PDM_AFAST_LATERAL")["resultado"] == "conforme"
    assert _item(v, "PDM_AFAST_TARDOZ")["resultado"] == "nao_conforme"  # 4 < 6
    assert v["resumo"]["nao_conforme"] == 3


def test_pdm_valores_invalidos_ignorados():
    pdm = R.normalizar_pdm({"iu_max": "abc", "io_max_pct": -3, "n_pisos_max": "2", "altura_fachada_max_m": 0})
    assert pdm["iu_max"] is None and pdm["io_max_pct"] is None and pdm["altura_fachada_max_m"] is None
    assert pdm["n_pisos_max"] == 2


def test_estacionamento():
    base = _proc(pdm={"lugares_por_fogo": 2})
    assert _item(R.verificar(base), "PDM_ESTACIONAMENTO")["resultado"] == "sem_dados"    # n.º de fogos em falta
    v = R.verificar(_proc(pdm={"lugares_por_fogo": 2}, volume={"n_fogos": 1, "lugares_previstos": 1}))
    it = _item(v, "PDM_ESTACIONAMENTO")
    assert it["limite"] == 2 and it["resultado"] == "nao_conforme"
    v2 = R.verificar(_proc(pdm={"lugares_por_100m2": 1.5}, volume={"lugares_previstos": 2}))
    assert _item(v2, "PDM_ESTACIONAMENTO")["limite"] == 2                               # ceil(1,5 × 96 / 100)
    assert _item(v2, "PDM_ESTACIONAMENTO")["resultado"] == "conforme"
    assert not any("Lugares" in x for x in v2["parametros_em_falta"])


# ------------------------------------------------------------------ normas nacionais ----
def test_rgeu_piso_a_piso_e_pe_direito():
    ok = R.verificar(_proc(volume={"storey_h_m": 2.7, "espessura_laje_m": 0.3}))
    assert _item(ok, "RGEU_65_PISO_A_PISO")["resultado"] == "conforme"
    assert _item(ok, "RGEU_65_PE_DIREITO")["resultado"] == "conforme"            # 2,40 no limite
    ko = R.verificar(_proc(volume={"storey_h_m": 2.6, "espessura_laje_m": 0.25}))
    assert _item(ko, "RGEU_65_PISO_A_PISO")["resultado"] == "nao_conforme"
    assert _item(ko, "RGEU_65_PE_DIREITO")["resultado"] == "nao_conforme"         # 2,35 < 2,40
    it = _item(ko, "RGEU_65_PE_DIREITO")
    assert it["limite"] == 2.40 and it["fonte"]["status"] == "confirmado" and "65.º" in it["fonte"]["artigo"]


def test_rgeu_uso_apoio_e_comercio():
    v = R.verificar(_proc(tipo_obra="anexo", volume={"levels": 1, "storey_h_m": 2.2}))
    assert _item(v, "RGEU_65_NA")["resultado"] == "informativo"
    c = R.verificar(_proc(volume={"uso": "comercio", "storey_h_m": 3.2}))
    it = _item(c, "RGEU_65_COMERCIO")
    assert it["fonte"]["status"] == "a_confirmar" and it["resultado"] == "nao_conforme"   # 2,90 < 3,00
    assert any("65.º, n.º 3" in x for x in c["valores_a_confirmar"])


def test_codigo_civil_1360_vaos():
    v = R.verificar(_proc(volume={"setback_side_m": 1.0}))
    it = _item(v, "CC_1360_LATERAL_ESQUERDO")
    assert it["resultado"] == "atencao" and it["limite"] == 1.5 and "1363" in it["nota"]
    assert not any(i["codigo"] == "CC_1360_LATERAL_DIREITO" for i in v["verificacoes"])


def test_regra_45_graus_opcional():
    assert not any(i["codigo"] == "RGEU_59_45GRAUS" for i in R.verificar(_proc())["verificacoes"])
    v = R.verificar(_proc(volume={"distancia_alinhamento_fronteiro_m": 5}))
    it = _item(v, "RGEU_59_45GRAUS")
    assert it["resultado"] == "nao_conforme" and it["fonte"]["status"] == "a_confirmar"


def test_construcao_fora_do_terreno():
    v = R.verificar(_proc(volume={"footprint_l_m": 19}))     # 3 + 19 > 20
    assert _item(v, "GEOM_DENTRO_TERRENO")["resultado"] == "nao_conforme"


def test_volume_por_definir_sem_valores_por_defeito():
    v = R.verificar(_proc(volume=None))
    assert v["quadro"] is None
    assert [i["codigo"] for i in v["verificacoes"]] == ["VOLUME_POR_DEFINIR"]


# ------------------------------------------------------------------ RJUE (motor existente) ----
def test_rjue_moradia_licenciamento():
    v = R.verificar(_proc())
    assert v["rjue"]["procedimento"] == "licenciamento"
    assert v["rjue"]["regra_aplicada"] == "MORADIA_NOVA_LICENCIAMENTO"
    assert v["rjue"]["respostas"]["area_construcao_total_m2"] == 96


def test_rjue_anexo_escassa_relevancia():
    vol = {"plot_l_m": 20, "plot_w_m": 15, "footprint_l_m": 3, "footprint_w_m": 3, "levels": 1, "storey_h_m": 2.1,
           "total_h_m": 2.1, "roof_type": "plana", "setback_front_m": 10, "setback_side_m": 2}
    v = R.verificar(_proc(tipo_obra="anexo", volume=vol, enquadramento={"confina_via_publica": False}))
    assert v["rjue"]["procedimento"] == "isento" and v["rjue"]["regra_aplicada"] == "ESCASSA_RELEVANCIA_ANEXO"
    alto = R.verificar(_proc(tipo_obra="anexo", volume={**vol, "storey_h_m": 2.5, "total_h_m": 2.5}))
    assert alto["rjue"]["procedimento"] != "isento"                    # 2,5 m > 2,2 m


def test_rjue_ampliacao_cp_e_zona_protegida():
    v = R.verificar(_proc(tipo_obra="ampliacao", enquadramento={"tem_pdm_com_parametros": True, "area_construcao_existente_m2": 60}))
    assert v["rjue"]["procedimento"] == "comunicacao_previa"
    assert v["quadro"]["area_construcao_criada_m2"] == 36
    p = R.verificar(_proc(tipo_obra="ampliacao", enquadramento={"tem_pdm_com_parametros": True, "zona_protegida": True}))
    assert p["rjue"]["procedimento"] == "licenciamento"


def test_rjue_piscina_e_muro():
    pis = R.verificar({"tipo_obra": "piscina", "parametros": {"comprimento_m": 8, "largura_m": 4},
                       "enquadramento": {"tem_edificacao_principal": True, "area_construcao_existente_m2": 150}})
    assert pis["rjue"]["procedimento"] == "isento" and pis["rjue"]["respostas"]["area_implantacao_m2"] == 32
    muro = R.verificar({"tipo_obra": "muro", "parametros": {"altura_m": 1.6, "implantacao": "laterais"}})
    assert muro["rjue"]["procedimento"] == "isento"
    frente = R.verificar({"tipo_obra": "muro", "parametros": {"altura_m": 1.6, "implantacao": "frente"}})
    assert frente["rjue"]["respostas"]["confina_via_publica"] is True and frente["rjue"]["procedimento"] != "isento"
    alto = R.verificar({"tipo_obra": "muro", "parametros": {"altura_m": 2.5}, "pdm": {"altura_muro_max_m": 2}})
    assert _item(alto, "PDM_ALTURA_MURO")["resultado"] == "nao_conforme"


def test_pecas_exigidas_por_procedimento():
    lic = {p["code"] for p in R.pecas_exigidas("licenciamento", "moradia_nova")}
    assert {"PLANTA_IMPLANTACAO", "CORTES", "ALCADOS", "PLANTAS_PISOS", "FICHA_ESTATISTICA", "TERMOS_RESPONSABILIDADE"} <= lic
    cp = {p["code"] for p in R.pecas_exigidas("comunicacao_previa", "piscina")}
    assert "ALCADOS" not in cp and "FICHA_ESTATISTICA" not in cp
    iso = {p["code"] for p in R.pecas_exigidas("isento", "muro")}
    assert iso == {"INICIO_TRABALHOS", "FOTOGRAFIAS"}


# ------------------------------------------------------------------ desenhos e PDFs ----
@pytest.mark.parametrize("shape", ["rectangle", "L", "T"])
@pytest.mark.parametrize("roof", ["duas_aguas", "uma_agua", "plana"])
def test_desenhos_edificio(shape, roof):
    vol = {**_proc()["volume"], "shape": shape, "roof_type": roof, "blocks": [{"name": "Garagem", "l_m": 4, "w_m": 5, "x_m": 14, "y_m": 2}]}
    for fn in (V.planta_implantacao, V.corte, V.alcado, V.axonometria):
        data = fn(vol)
        assert data[:8] == PNG and len(data) > 3000


def test_desenhos_muro_piscina():
    mu = {"parametros": {"comprimento_m": 22, "altura_m": 1.6, "implantacao": "frente_e_laterais", "capeamento": True,
                         "portao": True, "portao_largura_m": 4, "portao_posicao_m": 3, "subtipo": "suporte"}}
    pi = {"parametros": {"comprimento_m": 8, "largura_m": 4, "profundidade_m": 1.5, "distancia_limites_m": 3,
                         "cobertura": True, "cobertura_h_m": 1.2}}
    for data in (V.muro_planta(mu), V.muro_alcado(mu), V.muro_corte(mu), V.piscina_planta(pi), V.piscina_corte(pi)):
        assert data[:8] == PNG and len(data) > 2000
    assert [d["code"] for d in UP.desenhos({"tipo_obra": "piscina", **pi})] == ["PLANTA_IMPLANTACAO", "CORTES"]


def test_compat_cobertura_formato_frances():
    assert V.roof_type({"roof_type": "deux_pentes"}) == "duas_aguas"
    assert V.roof_type({"roof_type": "toit_plat"}) == "plana"


def _pdf_text(data: bytes) -> str:
    return "\n".join(p.extract_text() or "" for p in PdfReader(io.BytesIO(data)).pages)


def test_quadro_pdf_em_portugues():
    p = exemplo.processo_exemplo()
    v = R.verificar(p)
    data = UP.quadro_pdf(p, v)
    assert data[:4] == b"%PDF"
    txt = _pdf_text(data)
    for s in ("Quadro de áreas", "Índice de ocupação", "Altura da fachada", "RJUE", "Licença", "RGEU"):
        assert s in txt, s
    for fr in ("Plan de masse", "Emprise", "Cerfa", "PLU", "permis"):
        assert fr not in txt, fr


def test_exemplo_conforme_e_export_zip():
    p = exemplo.processo_exemplo()
    v = R.verificar(p)
    assert v["resumo"]["nao_conforme"] == 0
    z = zipfile.ZipFile(io.BytesIO(UP.export_zip(p, v, [{"code": "FOTOGRAFIAS", "filename": "foto.png", "data": V.corte(p["volume"])}])))
    names = set(z.namelist())
    assert {"00_quadro_areas_verificacao.pdf", "01_pecas_desenhadas.pdf", "02_requerimento.pdf", "03_memoria_descritiva.pdf",
            "processo_completo.pdf", "LEIA-ME.txt", "desenhos/planta_implantacao.png", "pecas/10_FOTOGRAFIAS.png"} <= names
    leia = z.read("LEIA-ME.txt").decode("utf-8")
    assert "Termos de responsabilidade" in leia and "Fotografias" not in leia.split("Lista indicativa")[0]
    assert len(PdfReader(io.BytesIO(z.read("01_pecas_desenhadas.pdf"))).pages) == 4
