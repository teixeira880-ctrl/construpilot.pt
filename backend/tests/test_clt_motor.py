"""Motor CLT (engines.clt): painéis com geometria real, vãos recortados, plano de prensa, ligações contadas, livrables."""
import json
import os

import pytest

from engines.clt import adapter, calcular, defaults, estudo
from engines.clt.engine import n_linha
from engines.clt.note import note
from engines.clt.pdf import dossier
from engines.clt.viewer import html_viewer
from engines.clt.xlsx import xlsx

FIX = os.path.join(os.path.dirname(__file__), "fixtures", "mep_moradia_exemplo.json")


@pytest.fixture(scope="module")
def ex():
    return calcular(defaults.exemplo())


def test_exemplo_geometria(ex):
    e = ex["estudo"]
    assert e["nPaineis"] == 26
    pw = {p["id"]: p for p in ex["paineis"]}
    # canto convexo: cada parede começa no seu canto e para à espessura da seguinte (10 000 − 100)
    assert pw["RC-1A"]["L"] == 9900 and pw["RC-2A"]["L"] == 7900
    # parede interior cortada nas faces das paredes que encontra (10 000 − 2 × 100)
    assert pw["I1A"]["L"] == 9800 and pw["I2A"]["L"] == 3850
    # recortes dos vãos no painel, às cotas do projeto
    rec = {r["id"]: r for r in pw["RC-1A"]["recortes"]}
    assert rec["J1"] == {"id": "J1", "tipo": "janela", "x0": 1500, "x1": 2700, "z0": 900, "z1": 2100}
    assert rec["P1"]["z0"] == 0 and rec["P1"]["z1"] == 2100
    # volume líquido = envolvente − vãos
    p = pw["RC-1A"]
    assert p["volLiq"] == pytest.approx((9.9 * 2.7 - 1.2 * 1.2 * 2 - 1.0 * 2.1) * 0.1)


def test_volumes_coerentes(ex):
    for r in ex["paineisResumo"]:
        assert r["volLiq"] <= r["volBruto"] + 1e-9 <= r["volPrensa"] + 1e-6
        assert 0 <= r["desperdicio"] < 0.5
    e = ex["estudo"]
    assert e["m3Liq"] == pytest.approx(sum(p["volLiq"] for p in ex["paineis"]))
    assert e["m3Vaos"] == pytest.approx(sum(v["m3Recorte"] for v in ex["vaos"]))
    # todos os painéis estão em exatamente um bruto do plano de prensa
    refs = [x["ref"] for pl in ex["planosPrensa"] for f in pl["folhas"] for x in f["pecas"]]
    assert sorted(refs) == sorted(p["id"] for p in ex["paineis"])


def test_lajes_esbelteza(ex):
    for f in ex["lajes"]:
        assert f["S"] / f["esp"] <= ex["regras"]["esbelteza"] + 1e-9
    assert ex["coberturas"][0]["esbelteza"] <= ex["regras"]["esbeltezaCobertura"]


def test_ligacoes_contadas(ex):
    con = {c["nome"]: c["qtd"] for c in ex["conectores"]}
    nomes = defaults.CONECTORES
    # esquadros e hold-downs: conferidos painel a painel
    esq_b = sum(p["esquadros"] for p in ex["paineis"] if p["tipo"] == "parede" and next(w for w in ex["paredes"] if w["id"] == p["ref"])["apoio"] == "betao")
    assert con[nomes["esquadroBetao"]["nome"]] == esq_b
    hd = sum(p["holdDowns"] for p in ex["paineis"] if p["tipo"] == "parede")
    assert con[nomes["holdDownBetao"]["nome"]] + con[nomes["holdDownMadeira"]["nome"]] == hd
    # pontos de elevação: 2 por painel de parede / empena, 4 por laje / cobertura
    n_el = sum(2 if p["tipo"] in ("parede", "empena") else 4 for p in ex["paineis"])
    assert con[nomes["elevacao"]] == n_el
    anc = {a["nome"]: a["qtd"] for a in ex["ancoragens"]}
    assert anc[nomes["esquadroBetao"]["ancora"]] == esq_b
    # parafusos de canto: 8 cantos × n_linha(altura)
    canto = sum(p["origens"].get("Cantos entre paredes exteriores", 0) for p in ex["parafusos"])
    assert canto == 4 * n_linha(2700, 300, 100) + 4 * n_linha(2600, 300, 100)


def test_n_linha():
    assert n_linha(0, 300, 100) == 0 and n_linha(150, 300, 100) == 1 and n_linha(800, 300, 100) == 3 and n_linha(2700, 300, 100) == 10


def test_deterministico():
    a = estudo(defaults.exemplo())
    b = estudo(defaults.exemplo())
    assert json.dumps(a["linhas"], sort_keys=True) == json.dumps(b["linhas"], sort_keys=True)


def test_mapa_completo(ex):
    st = estudo(defaults.exemplo())
    cats = {l["cat"].split(" ", 1)[1] for l in st["linhas"]}
    assert {"Painéis CLT", "Fabrico", "Parafusos e pregos", "Conectores metálicos", "Ancoragens", "Bandas e fitas"} <= cats
    assert all(l["qtd"] > 0 for l in st["linhas"])
    # sem biblioteca: nenhum preço inventado
    assert st["totais"]["total"] == 0 and st["totais"]["linhas_sem_preco"] == len(st["linhas"])


def test_so_clt():
    p = defaults.exemplo()
    p["soClt"] = True
    r = calcular(p)
    assert not any(e["cat"] in ("Membranas", "Isolamento exterior", "Cobertura") for e in r["extras"])
    assert r["estudo"]["m2Vaos"] > 0                       # os vãos continuam medidos (m² exatos e perdas)


def test_planta_real():
    p = adapter.from_mep_input(json.load(open(FIX)))
    r = calcular(p)
    e = r["estudo"]
    assert e["nPaineis"] > 50 and e["m3Liq"] > 40
    # cota superior de cada piso mantida: paredes de baixo acabam na face inferior da laje
    for f in r["lajes"]:
        assert any(abs(w["z0"] + w["H"] - f["z"]) < 1 for w in r["paredes"])
    assert not any("nenhuma parede de apoio" in a for a in r["avisos"])


def test_retangulo_e_note():
    a = {"implantacao": {"comprimento_m": 9, "largura_m": 7, "pisos": 2}, "render": False,
         "vaos": [{"piso": 0, "fachada": "frente", "tipo": "porta", "x_m": 4, "largura_m": 1}]}
    r = note(a)
    assert r["pdf"][:4] == b"%PDF" and r["png"][:4] == b"\x89PNG"
    assert [x[3] for x in r["files_extra"]] == ["xlsx", "html"]
    assert r["data"]["paineis"] > 10 and "a orçamentar" in r["resume"]


def test_livrables(ex):
    st = estudo(defaults.exemplo())
    pdf = dossier(st["resultado"], st["linhas"], st["totais"], "pt", {"company_name": "Construtora Teste, Lda"}, [])
    import pymupdf
    d = pymupdf.open(stream=pdf, filetype="pdf")
    txt = "".join(pg.get_text() for pg in d)
    assert d.page_count >= 20 and "RC-1A" in txt and "Plano de prensa" in txt and "Construtora Teste" in txt
    assert xlsx(st["resultado"], st["linhas"], st["totais"])[:2] == b"PK"
    vw = html_viewer(st["resultado"], "Ex")
    assert b"window.CLT={" in vw and b"RC-1A" in vw


def test_lsf_inalterado():
    """O adaptador partilhado com o LSF só muda com as opções CLT: o exemplo LSF dá os mesmos números."""
    from engines.lsf import calcular as lsf_calc, defaults as lsf_def
    assert lsf_calc(lsf_def.exemplo())["estudo"]["nMembros"] == 720
