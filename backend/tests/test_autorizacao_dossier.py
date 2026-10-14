"""Testes de geração do processo de autorização de obras (Lote N2)."""

import asyncio
import os
import zipfile
from io import BytesIO
from unittest.mock import patch

from engines.autorizacao_obras_pt.dossier import (
    MEMORIA_FALLBACK,
    checklist_pecas,
    construir_estimativa_pdf,
    construir_ficha_estatistica_pdf,
    construir_memoria_pdf,
    construir_requerimento_pdf,
    estimativa_e_calendario,
    gerar_dossier,
    gerar_memoria_descritiva,
)
from engines.autorizacao_obras_pt.rules import diagnosticar


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


# ------- Checklist por procedimento ----------------------------------------

def test_checklist_isento():
    diag = {"procedimento": "isento", "pecas_necessarias": []}
    cl = checklist_pecas(diag, [])
    assert cl["procedimento"] == "isento"
    assert cl["total"] >= 2
    assert any("início dos trabalhos" in p["peca"].lower() for p in cl["pecas"])


def test_checklist_licenciamento_tem_memoria_e_estabilidade():
    diag = {"procedimento": "licenciamento", "pecas_necessarias": []}
    cl = checklist_pecas(diag, [])
    nomes = [p["peca"].lower() for p in cl["pecas"]]
    assert any("memória descritiva" in n for n in nomes)
    assert any("estabilidade" in n for n in nomes)


def test_checklist_cp_marca_carregadas():
    diag = {"procedimento": "comunicacao_previa", "pecas_necessarias": []}
    cl = checklist_pecas(diag, ["memoria descritiva"])
    carregadas = [p for p in cl["pecas"] if p["carregada"]]
    assert len(carregadas) >= 1


# ------- Estimativa + calendário -------------------------------------------

def test_estimativa_moradia_nova_tem_faixa():
    e = estimativa_e_calendario(
        {"tipo_obra": "moradia_nova", "area_construcao_total_m2": 150},
        {"procedimento": "licenciamento"},
    )
    assert e["custo_min_eur"] > 0 and e["custo_max_eur"] >= e["custo_min_eur"]
    assert e["calendario"]["obra_semanas_min"] >= 1


def test_estimativa_isento_tem_prazo_curto():
    e = estimativa_e_calendario({"tipo_obra": "anexo"}, {"procedimento": "isento"})
    assert e["calendario"]["instrucao_semanas"] <= 3


# ------- PDFs individuais ---------------------------------------------------

def test_pdf_requerimento_valido():
    diag = diagnosticar({"tipo_obra": "moradia_nova", "area_construcao_total_m2": 200})
    pdf = construir_requerimento_pdf({"tipo_obra": "moradia_nova", "concelho": "Lisboa"}, diag,
                                     {"nome": "Ana Silva", "nif": "123456789"})
    assert pdf.startswith(b"%PDF")
    assert len(pdf) > 2000


def test_pdf_memoria_valido():
    pdf = construir_memoria_pdf("Texto de teste.\n\n1. Secção um\nParágrafo.", {})
    assert pdf.startswith(b"%PDF")


def test_pdf_ficha_estatistica_valido():
    diag = diagnosticar({"tipo_obra": "moradia_nova"})
    pdf = construir_ficha_estatistica_pdf({"tipo_obra": "moradia_nova"}, diag)
    assert pdf.startswith(b"%PDF")


def test_pdf_estimativa_valido():
    e = estimativa_e_calendario({"tipo_obra": "ampliacao", "area_construcao_criada_m2": 50},
                                {"procedimento": "comunicacao_previa"})
    pdf = construir_estimativa_pdf(e)
    assert pdf.startswith(b"%PDF")


# ------- Dossier completo — 6 cenários do brief ----------------------------

CENARIOS = [
    ("anexo_escassa_relevancia", {"tipo_obra": "anexo", "altura_m": 2.0, "area_implantacao_m2": 8}),
    ("ampliacao_comunicacao_previa", {"tipo_obra": "ampliacao", "area_construcao_criada_m2": 40,
                                       "tem_pdm_com_parametros": True}),
    ("moradia_nova_licenciamento", {"tipo_obra": "moradia_nova", "area_construcao_total_m2": 200}),
    ("obras_interiores", {"tipo_obra": "interiores"}),
    ("piscina", {"tipo_obra": "piscina", "tem_edificacao_principal": True,
                 "area_implantacao_m2": 15, "area_construcao_total_m2": 160}),
    ("zona_protegida", {"tipo_obra": "anexo", "altura_m": 2.0, "area_implantacao_m2": 8,
                        "zona_protegida": True}),
]


def test_gerar_dossier_para_todos_os_cenarios():
    for codigo, respostas in CENARIOS:
        diag = diagnosticar(respostas)
        # memoria mock: evita chamada LLM
        with patch.dict(os.environ, {}, clear=False):
            # força fallback: remove a chave temporariamente
            key = os.environ.pop("EMERGENT_LLM_KEY", None)
            try:
                out = _run(gerar_dossier(respostas, diag,
                                         pecas_carregadas=[{"nome": "planta.pdf", "bytes": b"%PDF-1.4\n%fake\n"}]))
            finally:
                if key is not None:
                    os.environ["EMERGENT_LLM_KEY"] = key
        assert out["pdf_unico"].startswith(b"%PDF"), f"PDF inválido em {codigo}"
        assert len(out["pdf_unico"]) > 5_000, f"PDF demasiado pequeno em {codigo}"
        # ZIP: validar que inclui os 4 PDFs base + a peça carregada
        z = zipfile.ZipFile(BytesIO(out["zip"]))
        nomes = z.namelist()
        assert any("requerimento" in n for n in nomes), f"requerimento ausente em {codigo}"
        assert any("memoria_descritiva" in n for n in nomes), f"memória ausente em {codigo}"
        assert any("ficha_estatistica" in n for n in nomes), f"ficha ausente em {codigo}"
        assert any("estimativa" in n for n in nomes), f"estimativa ausente em {codigo}"
        assert any("planta.pdf" in n for n in nomes), f"peça carregada ausente em {codigo}"
        # Memória não vazia (fallback ativo)
        assert out["memoria_texto"], f"memória vazia em {codigo}"
        # Checklist conta pelo menos as peças base
        assert out["checklist"]["total"] >= 2


def test_memoria_fallback_quando_sem_chave_llm():
    key = os.environ.pop("EMERGENT_LLM_KEY", None)
    try:
        texto = _run(gerar_memoria_descritiva({"tipo_obra": "moradia_nova"}, {"procedimento": "licenciamento"}))
    finally:
        if key is not None:
            os.environ["EMERGENT_LLM_KEY"] = key
    assert texto == MEMORIA_FALLBACK
