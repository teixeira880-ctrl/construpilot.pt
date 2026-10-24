"""Motor de processos completos (.pt): ZIP seguro, classificação por especialidade/piso no contexto português, codificação dos
gabinetes, lista de desenhos — porta dos testes .fr de tests/test_coffrage_dossier.py (parte «dossier / ZIP») + casos PT.
Nomes de ficheiros fictícios (XYZ), sem dados de clientes."""
import io
import zipfile

import pytest

from engines import dossier as D


def _zip(entries):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for n, d in entries:
            z.writestr(n, d)
    return buf.getvalue()


def test_zip_expansion_is_safe_and_flattens_one_level():
    inner = _zip([("COF_Piso2.dxf", b"0\nSECTION\n")])
    data = _zip([("pe/ARQ_RC.pdf", b"%PDF-1.4 x"), ("__MACOSX/._ARQ_RC.pdf", b"x"), (".DS_Store", b"x"), ("../mau.pdf", b"%PDF"),
                 ("notas.exe", b"MZ"), ("especialidades/inner.zip", inner)] + [(f"p/{i}_COF_Piso{i}.dwg", b"AC1024" + bytes(10)) for i in range(25)])
    files, skipped = D.expand("processo.zip", data)
    names = [n for n, _ in files]
    assert "pe/ARQ_RC.pdf" in names and "especialidades/COF_Piso2.dxf" in names
    assert len([n for n in names if n.endswith(".dwg")]) == 25
    assert not any("MACOSX" in n or "DS_Store" in n or "mau" in n or n.endswith(".exe") for n in names)
    assert any("caminho recusado" in s for s in skipped) and any("notas.exe" in s and "não suportado" in s for s in skipped)


def test_nested_zip_beyond_one_level_is_skipped():
    deep = _zip([("a.pdf", b"%PDF")])
    mid = _zip([("deep.zip", deep)])
    files, skipped = D.expand("top.zip", _zip([("mid.zip", mid)]))
    assert files == [] and any("mais de um nível" in s for s in skipped)


def test_zip_bomb_and_corrupt_archives_are_refused():
    bomb = _zip([("a.pdf", b"0" * (30 * 1024 * 1024))])
    files, skipped = D.expand("b.zip", bomb)
    assert not files and "compressão anómala" in skipped[0]
    with pytest.raises(D.DossierError, match="ilegível"):
        D.expand("x.zip", b"PK\x03\x04garbage")
    files, skipped = D.expand("virus.exe", b"MZ")
    assert files == [] and "não suportado" in skipped[0]


@pytest.mark.parametrize("name,disc", [
    ("Projeto de Arquitetura - Plantas.pdf", "arquitetura"),
    ("Alçados e Cortes.dwg", "arquitetura"),
    ("Estabilidade/Planta de fundações.dwg", "estabilidade"),
    ("Caderno de Encargos - AVAC.pdf", "caderno_encargos"),
    ("Mapa_Quantidades.xlsx", "mapa_quantidades"),
    ("MQ_Especialidades.xls", "mapa_quantidades"),
    ("Estudo Geotécnico.pdf", "geotecnia"),
    ("Comunicação Prévia - requerimento.pdf", "licenciamento"),
    ("Termo de responsabilidade do técnico.pdf", "licenciamento"),
    ("PSS_obra.pdf", "seguranca_saude"),
    ("Ficha de SCIE.pdf", "scie"),
    ("Projeto ITED.pdf", "eletricidade"),
    ("REH_pre-certificado.pdf", "termica"),
    ("Projeto acustico RRAE.pdf", "acustica"),
    ("Redes prediais de aguas e esgotos.pdf", "aguas_esgotos"),
    ("Projeto de Gás.pdf", "gas"),
    ("Levantamento topografico.dwg", "topografia"),
    ("Memoria descritiva.docx", "memoria_descritiva"),
    ("Lista de desenhos.pdf", "lista_desenhos"),
    ("foto_fachada.jpg", "fotografia"),
    # codificações francesas continuam reconhecidas
    ("EXE_BET_FER_PH_SS1.pdf", "armaduras"),
    ("G2_AVP_rapport.pdf", "geotecnia"),
    ("DPGF GO.xlsx", "mapa_quantidades"),
    ("notas.txt", "outro"),
])
def test_classification_pt(name, disc):
    assert D.classify(name)["discipline"] == disc


def test_folder_gives_the_specialty_when_the_name_is_generic():
    assert D.classify("03_Especialidades/Estabilidade/Desenho 01.pdf")["discipline"] == "estabilidade"
    assert D.classify("01_Arquitetura/Desenho 01.pdf")["discipline"] == "arquitetura"


def test_first_page_text_classifies_unnamed_pdf():
    assert D.classify("scan_001.pdf", "CADERNO DE ENCARGOS — Cláusulas técnicas gerais")["discipline"] == "caderno_encargos"
    assert D.classify("scan_002.pdf", "LISTA DE DESENHOS do projeto de execução")["discipline"] == "lista_desenhos"


@pytest.mark.parametrize("name,level", [
    ("Planta R-C.pdf", "R/C"), ("Planta_RC.pdf", "R/C"), ("Planta Piso 0.pdf", "R/C"), ("Plan_RDC.pdf", "R/C"),
    ("Planta Piso 1.pdf", "Piso 1"), ("1.º Piso - Arquitetura.pdf", "Piso 1"), ("2o andar.pdf", "Piso 2"), ("COF_PH_R+2.dxf", "Piso 2"),
    ("Planta Piso -1.pdf", "Cave -1"), ("Planta Cave.pdf", "Cave -1"), ("Cave 2.pdf", "Cave -2"), ("SS1.pdf", "Cave -1"),
    ("Planta de Cobertura.pdf", "Cobertura"), ("Sotao.pdf", "Sótão"), ("Planta fundacoes.dwg", "Fundações"),
    ("Pormenor S1.pdf", None), ("Planta R1.pdf", None),     # S1 = sapata, R1 = revisão: não são pisos
])
def test_levels_pt(name, level):
    assert D.classify(name)["level"] == level


def test_level_order():
    levels = ["Piso 2", "R/C", "Cave -1", "Piso 1", None, "Cobertura", "Fundações", "Cave -2"]
    assert sorted(levels, key=D.level_key) == ["Fundações", "Cave -2", "Cave -1", "R/C", "Piso 1", "Piso 2", "Cobertura", None]


def test_office_codes_give_zone_level_nature_and_revision():
    c = D.classify("XYZ_PE_EST_Z1_P2_ARM_0171_-_Armaduras_Vigas_-_rev_B.pdf")
    assert (c["discipline"], c["level"], c["zone"], c["plan_key"], c["indice"], c["phase"], c["element"]) == \
        ("armaduras", "Piso 2", "Z1", "Z1-ARM-0171", "B", "PE", "vigas")
    c = D.classify("XYZ_EXE_BET_TZ_R1_COF_0100_-_Planta_cofragem_-_A.dwg")
    assert (c["discipline"], c["level"], c["zone"], c["plan_key"], c["indice"], c["cad"]) == ("cofragem", "Piso 1", "TZ", "TZ-COF-0100", "A", True)
    assert D.classify("XYZ_EXE_BET__Z1_SS1_COF_5101_ind C.dxf")["level"] == "Cave -1"
    assert D.classify("XYZ_EXE_BET_Z1_FON_ARM_5281.pdf")["level"] == "Fundações"
    assert D.classify("EXE_XYZ_BET_GEN_NDC_4000.pdf")["discipline"] == "nota_calculo"
    assert "plan_key" not in D.classify("COF_PH_R+2.dxf")


def _rows(rev_p1, date_p1):
    return [["LISTA DE DESENHOS — ESTABILIDADE"], ["PISO", "NATUREZA", "Zona", "TIPO", "N.º", "NOME", "DESCRIÇÃO", "Rev.", "Data"],
            ["Piso 1", "Cofragem", "", "COF", "0100", "XYZ_PE_EST_TZ_P1_COF_0100", "Planta de cofragem - Piso 1", rev_p1, date_p1],
            ["", "", "", "CPE", "0110", "XYZ_PE_EST_TZ_P1_COF_0110", "Cortes de cofragem - Piso 1", "A", 44524.0],
            ["Piso 2", "Cofragem", "", "COF", "0200", "XYZ_PE_EST_TZ_P2_COF_0200", "Planta de cofragem - Piso 2", "A", "22/10/2021"],
            ["", "Armaduras", "", "ARM", "0271", "XYZ_PE_EST_Z1_P2_ARM_0271", "Armaduras de vigas - Piso 2", "", ""],
            ["DIVERSOS", "", "", "NDC", "4000", "XYZ_PE_EST_GEN_NDC_4000", "Memória de cálculo geral", 0.0, 44488.0]]


def test_register_from_sheet_and_merge_keeps_the_latest_revision():
    old = D.register_from_rows(_rows("A", 44491.0), "LD - 211115.xls")
    new = D.register_from_rows(_rows("B", "24/11/2021"), "LD - 211129.xls")
    assert len(new) == 5 and new[0]["date"] == "2021-11-24" and old[0]["date"] == "2021-10-22"
    assert new[-1]["indice"] == "0" and new[3]["indice"] is None and new[3]["element"] == "vigas" and new[0]["level"] == "Piso 1"
    reg = D.merge_registers([new, old])
    assert next(r for r in reg if r["key"] == "TZ-COF-0100")["indice"] == "B"


def test_register_from_pdf_text():
    text = ("LISTA DE DESENHOS Fase: PE PISO NATUREZA TIPO N.º NOME DESCRIÇÃO Rev. Data "
            "COF 0100 XYZ_PE_EST_TZ_P1_COF_0100 Planta de cofragem - Piso 1 B 24/11/2021 "
            "CPE 0110 XYZ_PE_EST_TZ_P1_COF_0110 Cortes de cofragem - Piso 1 A 24/11/2021 "
            "COF 0200 XYZ_PE_EST_TZ_P2_COF_0200 Planta de cofragem - Piso 2 "
            "ARM 0271 XYZ_PE_EST_Z1_P2_ARM_0271 Armaduras de vigas - Piso 2 0 30/11/2021")
    reg = {r["key"]: r for r in D.register_from_text(text)}
    assert reg["TZ-COF-0100"]["indice"] == "B" and reg["TZ-COF-0100"]["date"] == "2021-11-24"
    assert reg["TZ-COF-0200"]["indice"] is None and reg["Z1-ARM-0271"]["indice"] == "0"
    assert reg["TZ-COF-0110"]["description"].startswith("Cortes")
    assert D.register_from_text("Planta de implantação sem lista") == []


def test_check_register_flags_missing_outdated_and_extra():
    reg = D.merge_registers([D.register_from_rows(_rows("B", "24/11/2021"))])
    files = [{**D.classify(n), "filename": n} for n in ("XYZ_PE_EST_TZ_P1_COF_0100_-_A.dwg", "XYZ_PE_EST_TZ_P1_COF_0100_-_B.dwg",
                                                         "XYZ_PE_EST_TZ_P2_COF_0200_-_A.dwg", "XYZ_PE_EST_Z3_P5_COF_0500.dwg")]
    ck = D.check_register(files, reg)
    assert {m["code"] for m in ck["em_falta"]} == {"XYZ_PE_EST_TZ_P1_COF_0110", "XYZ_PE_EST_GEN_NDC_4000"}   # 0271: ainda não emitido
    assert ck["revisoes_desatualizadas"] == [] and ck["varias_revisoes"][0]["considerado"].endswith("_B.dwg")
    assert ck["fora_da_lista"] == ["XYZ_PE_EST_Z3_P5_COF_0500.dwg"] and ck["pisos"] == ["Piso 1", "Piso 2"]
    ck2 = D.check_register(files[:1], reg)
    assert ck2["revisoes_desatualizadas"][0]["revisao_lista"] == "B" and ck2["revisoes_desatualizadas"][0]["revisao_ficheiro"] == "A"
    assert [f["filename"] for f in D.latest_per_plan(files) if f.get("plan_key") == "TZ-COF-0100"] == ["XYZ_PE_EST_TZ_P1_COF_0100_-_B.dwg"]


def test_inventory_groups_and_usual_missing_pieces():
    names = ["Arquitetura/Planta Piso 1.pdf", "Arquitetura/Planta R-C.pdf", "Estabilidade/Planta fundacoes.dwg", "Caderno de encargos.pdf",
             "foto.jpg"]
    files = [{**D.classify(n), "filename": n} for n in names]
    inv = D.inventory(files)
    assert inv["total"] == 5 and inv["plantas_cad"] == 1 and inv["pdf"] == 3
    assert inv["por_especialidade"]["arquitetura"]["pisos"] == ["R/C", "Piso 1"]
    assert inv["por_especialidade"]["arquitetura"]["rotulo"] == "Projeto de arquitetura"
    assert inv["por_grupo"] == {"Elementos de base (geotecnia, topografia, fotografias)": 1, "Peças escritas": 1,
                                "Projeto de arquitetura": 2, "Projetos de especialidades": 1}
    missing = D.missing_pieces(files)
    assert "mapa de quantidades" in missing and "estudo geotécnico" in missing
    assert "projeto de arquitetura" not in missing and "projeto de estabilidade" not in missing
