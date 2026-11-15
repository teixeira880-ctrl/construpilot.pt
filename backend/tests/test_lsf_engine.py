"""Motor LSF (engines/lsf): contagens verificadas à mão, leitura de planta real, ferramenta do Assistente, dossier, Excel, 3D.
Sem Mongo, sem IA, sem rede."""
import io
import json
import os

import pytest

from engines.lsf import estudo
from engines.lsf.adapter import from_mep_input
from engines.lsf.defaults import base, exemplo
from engines.lsf.engine import calcular
from engines.lsf.geom import kg_per_m, plano_corte

FIX = os.path.join(os.path.dirname(__file__), "fixtures", "mep_moradia_exemplo.json")


def _parede(L, H, vaos, tipo="EXT", **T):
    p = base("PT")
    p["tiposParede"]["EXT"].update(T)
    p["paredes"] = [{"id": "W", "tipo": tipo, "z0": 0, "altura": H, "a": [0, 0], "b": [L, 0], "alinhamento": "eixo", "vaos": vaos}]
    return calcular(p)


def _M(r, tp):
    return [m for m in r["membros"] if m["tipoPeca"] == tp]


# ------------------------------------------------------------------------------------------------ parede 3000 × 2700 com janela
@pytest.fixture(scope="module")
def r1():
    return _parede(3000, 2700, [{"id": "J", "tipo": "janela", "x": 1000, "largura": 900, "altura": 1200, "peitoril": 900}])


def test_montantes_inteiros(r1):
    full = [m for m in r1["membros"] if m["tipoPeca"] in ("Montante", "Montante de extremo", "Montante rei")]
    assert len(full) == 6 and all(m["L"] == 2697.6 for m in full)          # 2700 − 2 × 1,2 (alma das guias)


def test_vao(r1):
    assert [m["L"] for m in _M(r1, "Montante de apoio")] == [2098.8, 2098.8]     # topo do vão 2100 − 1,2
    assert [m["L"] for m in _M(r1, "Montante curto (sobre verga)")] == [446.4, 446.4]   # 2700 − 1,2 − (2100 + 2,4 + 150)
    assert [m["L"] for m in _M(r1, "Montante curto (sob peitoril)")] == [897.6, 897.6]  # 900 − 2,4
    assert len(_M(r1, "Verga")) == 2 and _M(r1, "Verga")[0]["L"] == 986.0            # 900 + 2 × 43
    assert _M(r1, "Guia de peitoril")[0]["L"] == 900.0


def test_bloqueadores_e_parafusos(r1):
    bl = [m for m in r1["membros"] if m["tipoPeca"].startswith("Bloqueador")]
    assert len(bl) == 8                       # 2 filas (meia altura + junta OSB a 2500) × 4 vãos entre montantes inteiros
    aco = next(p for p in r1["parafusos"] if "aço/aço" in p["nome"])
    # 12 montantes × 4 + caixões 2 × 2 × 7 + verga 16 + guias da verga 16 + peitoril 4 + bloqueadores 8 × 4
    assert aco["qtd"] == 48 + 28 + 32 + 4 + 32


def test_massa_linear_pela_seccao():
    c = {"tipo": "C", "h": 90, "b": 43, "c": 10, "t": 1.2}
    area = 1.2 * (90 + 2 * 43 + 2 * 10) - 4 * 1.2 * 1.2      # contorno de parede fina, cantos vivos
    assert abs(kg_per_m(c) - area * 7850e-6) < 1e-9


def test_ancoragens(r1):
    assert next(a for a in r1["ancoragens"] if "Bucha" in a["nome"])["qtd"] == 6     # 3000: extremos 150, passo ≤ 600


def test_parafusos_osb_linha_a_linha():
    p = base("PT")
    p["tiposParede"]["EXT"].update(interior=[], bloqueadores=0, etics=None, isolamento=None)
    p["paredes"] = [{"id": "W", "tipo": "EXT", "z0": 0, "altura": 2500, "a": [0, 0], "b": [2400, 0], "alinhamento": "eixo", "vaos": []}]
    r = calcular(p)
    osb = [x for x in r["placas"] if x["placa"] == "OSB12"]
    assert [x["cell"]["x1"] - x["cell"]["x0"] for x in osb] == [1200, 1200]       # cortadas à modulação (juntas sobre montante)
    # montantes x=21,5 (bordo) 600 (interior) 1200 (bordo) em 2497,6 mm: 17 + 9 + 17 ; guias: 2 × (3 + 3)
    assert osb[0]["parafusos"] == 43 + 12


def test_ombreira_partilhada_e_extremo():
    r = _parede(4000, 2700, [{"id": "P1", "tipo": "porta", "x": 100, "largura": 800, "altura": 2100},
                             {"id": "P2", "tipo": "porta", "x": 1000, "largura": 800, "altura": 2100}])
    # P1 encosta ao extremo (sem montante rei à esquerda); P1/P2 a 100 mm: ombreira partilhada (só os 2 montantes de apoio)
    assert len(_M(r, "Montante rei")) == 1
    assert len(_M(r, "Montante de apoio")) == 4
    assert not any("sobrepostos" in a for a in r["avisos"])


# ------------------------------------------------------------------------------------------------ moradia exemplo
@pytest.fixture(scope="module")
def rx():
    return estudo(exemplo())


def test_exemplo_sem_avisos_e_coerente(rx):
    r = rx["resultado"]
    assert r["avisos"] == []
    assert all(m["L"] > 0 for m in r["membros"])
    assert len(r["membros"]) == 720
    assert abs(r["estudo"]["kgAco"] - 3008) < 5


def test_determinismo(rx):
    r2 = estudo(exemplo())
    assert json.dumps(r2["linhas"], sort_keys=True) == json.dumps(rx["linhas"], sort_keys=True)


def test_parede_interior_cortada_na_face_do_gesso(rx):
    w = next(x for x in rx["resultado"]["paredes"] if x["id"] == "I1")
    assert round(w["L"], 1) == 10000 - 2 * (92.4 + 12.5)


def test_asnas(rx):
    d = [m for m in rx["resultado"]["membros"] if m["tipoPeca"] == "Diagonal"]
    assert d and all(300 < m["L"] < 4000 for m in d)
    bi = [m for m in rx["resultado"]["membros"] if m["tipoPeca"] == "Banzo inferior"]
    assert bi and all(m["L"] == 8000 for m in bi)


def test_plano_corte_valido(rx):
    for c in rx["resultado"]["planosCorte"]:
        for f in c["folhas"]:
            for p in f:
                assert p["x"] + p["w"] <= c["W"] + 1e-6 and p["y"] + p["h"] <= c["H"] + 1e-6
            for i in range(len(f)):
                for j in range(i + 1, len(f)):
                    a, b = f[i], f[j]
                    assert a["x"] + a["w"] <= b["x"] + 1e-6 or b["x"] + b["w"] <= a["x"] + 1e-6 or a["y"] + a["h"] <= b["y"] + 1e-6 \
                        or b["y"] + b["h"] <= a["y"] + 1e-6
    for p in rx["resultado"]["placasResumo"]:
        assert p["desperdicio"] >= 0


def test_plano_corte_reaproveita_sobras():
    r = plano_corte([{"w": 1200, "h": 2700}] * 4 + [{"w": 1200, "h": 200}] * 4, 1200, 3000)
    assert len(r["folhas"]) == 4                                         # as faixas de 200 saem das sobras de 300


def test_mapa_sem_rácios_e_precos(rx):
    lin = rx["linhas"]
    assert any(l["code"] == "LSF-C90X43X10X1.2" for l in lin)
    assert rx["totais"]["total"] == 0 and rx["totais"]["linhas_sem_preco"] == len(lin)        # sem biblioteca: nada inventado
    p = exemplo()
    p["precos"] = {"PL-OSB12": 15.0}
    st = estudo(p, [{"designation": "OSB/3 22 mm macho-fêmea", "unit": "un", "unit_price": 30.0}])
    l22 = next(l for l in st["linhas"] if l["code"] == "PL-OSB22")
    l12 = next(l for l in st["linhas"] if l["code"] == "PL-OSB12")
    assert l22["preco"]["origem"] == "biblioteca" and l12["preco"]["origem"] == "projeto"
    assert st["totais"]["total"] == round(l22["qtd"] * 30 + l12["qtd"] * 15, 2)


# ------------------------------------------------------------------------------------------------ planta real (entrada MEP)
@pytest.fixture(scope="module")
def planta():
    d = json.load(open(FIX))
    p = from_mep_input(d)
    return p, calcular(p)


def test_leitura_da_planta(planta):
    p, r = planta
    lv = p["leitura"]["pisos"]
    assert [x["divisoes"] for x in lv] == [10, 6]
    assert lv[0]["paredes_interiores"] >= 12 and lv[1]["paredes_interiores"] >= 5
    assert sum(x["vaos_exteriores"] + x["vaos_interiores"] for x in lv) >= 30
    assert any("Alturas dos vãos" in h for h in p["hipoteses"])
    assert p["coberturas"] and p["pisos"]


def test_planta_calcula(planta):
    p, r = planta
    assert len(r["membros"]) > 1000 and all(m["L"] > 0 for m in r["membros"])
    assert r["estudo"]["nParafusos"] > 10000


# ------------------------------------------------------------------------------------------------ saídas
def test_dossier_excel_visualizador(rx):
    from engines.lsf.pdf import dossier
    from engines.lsf.viewer import html_viewer
    from engines.lsf.xlsx import xlsx
    r = rx["resultado"]
    pdf = dossier(r, rx["linhas"], rx["totais"], "pt", {"company_name": "Construtora X", "accent_color": "#1f4e79"}, None, "Teste")
    assert pdf[:4] == b"%PDF"
    import pymupdf
    d = pymupdf.open(stream=pdf, filetype="pdf")
    assert d.page_count >= 15
    txt = "".join(d[i].get_text() for i in range(d.page_count))
    assert "Construtora X" in txt and "RC-1-M03" in txt
    x = xlsx(r, rx["linhas"], rx["totais"])
    from openpyxl import load_workbook
    wb = load_workbook(io.BytesIO(x))
    assert wb.sheetnames[:2] == ["Mapa de quantidades", "Lista de corte"]
    assert wb["Lista de corte"].max_row == len(r["membros"]) + 2
    h = html_viewer(r, "Teste")
    assert b"window.LSF=" in h and b"three" in h.lower() and len(h) > 300_000


@pytest.mark.parametrize("lang", ["fr", "en", "uk"])
def test_dossier_linguas(rx, lang):
    from engines.lsf.pdf import dossier
    pdf = dossier(rx["resultado"], rx["linhas"], rx["totais"], lang, None, None, "Test")
    assert pdf[:4] == b"%PDF"


def test_ferramenta_assistente():
    from engines.calc_lots.outils import CALC_TOOL_NAMES, LSF_TOOL, run
    assert "calcul_lsf" in CALC_TOOL_NAMES and LSF_TOOL["strict"] is True
    o = run("calcul_lsf", {"implantacao": {"comprimento_m": 9, "largura_m": 7, "pisos": 1, "pe_direito_m": None},
                           "vaos": [{"piso": 0, "fachada": "frente", "tipo": "porta", "x_m": 4, "largura_m": 1, "altura_m": None, "peitoril_m": None}],
                           "titulo": "Teste LSF", "_render": None, "render": False})
    assert o["pdf"][:4] == b"%PDF" and o["png"][:4] == b"\x89PNG"
    assert {f[3] for f in o["files_extra"]} == {"xlsx", "html"}
    assert "parafusos" in o["resume"] and o["data"]["pecas"] > 100
