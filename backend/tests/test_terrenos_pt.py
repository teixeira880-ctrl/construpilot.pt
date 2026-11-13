"""Terrenos PT — geometria PT-TM06, importação/exportação e análise com transporte HTTP simulado (sem rede)."""
import asyncio
import io
import json
import math
import sys
import os
import zipfile

import pytest

from engines.terrenos_pt import analise as A
from engines.terrenos_pt import bupi as B
from engines.terrenos_pt import geometria as GM
from engines.urbanismo_pt.auto import dgt_cache as CACHE
from engines.urbanismo_pt.auto import geo as G

LAT, LON = 41.5402, -8.4786


def quadrado(lado_m=40.0, lat=LAT, lon=LON):
    x0, y0 = GM.tm06(lat, lon)
    pts = [(x0, y0), (x0 + lado_m, y0), (x0 + lado_m, y0 + lado_m), (x0, y0 + lado_m)]
    return [list(GM.tm06_inv(x, y)) for x, y in pts]


def ring_lonlat(anel):
    return [[lo, la] for la, lo in anel + [anel[0]]]


@pytest.fixture(autouse=True)
def _isolado(tmp_path):
    CACHE.usar_pasta(str(tmp_path / "dgt_cache"))
    G._COLLECTIONS.update(t=0.0, list=[])
    yield
    G.set_transport(None)
    G._COLLECTIONS.update(t=0.0, list=[])


# ------------------------------------------------------------------ geometria
def test_tm06_pontos_de_referencia():
    # origem da projeção PT-TM06 → (0, 0)
    x, y = GM.tm06(39.66825833333333, -8.133108333333334)
    assert abs(x) < 1e-6 and abs(y) < 1e-6
    # ida e volta < 1 mm em todo o continente
    for la, lo in [(41.54, -8.48), (37.02, -7.93), (42.1, -6.2), (38.7, -9.5)]:
        a, b = GM.tm06_inv(*GM.tm06(la, lo))
        assert abs(a - la) * 111_000 < 1e-3 and abs(b - lo) * 111_000 < 1e-3


def test_tm06_coincide_com_pyproj_se_existir():
    pyproj = pytest.importorskip("pyproj")
    t = pyproj.Transformer.from_crs(4326, 3763, always_xy=True)
    for la, lo in [(41.54, -8.48), (37.02, -7.93), (38.7, -9.5)]:
        x, y = GM.tm06(la, lo)
        X, Y = t.transform(lo, la)
        assert abs(x - X) < 0.001 and abs(y - Y) < 0.001


def test_medir_area_perimetro_e_sentido():
    m = GM.medir(quadrado(40.0))
    assert abs(m["area_m2"] - 1600.0) < 0.05
    assert abs(m["perimetro_m"] - 160.0) < 0.05
    assert m["area_ha"] == pytest.approx(0.16, abs=1e-4)
    assert len(m["vertices_tm06"]) == 4
    assert all(abs(v["lado_m"] - 40.0) < 0.02 for v in m["vertices_tm06"])
    # sentido horário (como a RGG)
    assert not GM.poligono_m(m["anel_latlon"]).exterior.is_ccw


def test_medir_recusa_invalidos():
    q = quadrado(40.0)
    with pytest.raises(GM.GeometriaInvalida):
        GM.medir(q[:2])
    with pytest.raises(GM.GeometriaInvalida):        # laço (vértices cruzados)
        GM.medir([q[0], q[2], q[1], q[3]])
    with pytest.raises(GM.GeometriaInvalida):        # lat/lon trocadas → fora de Portugal
        GM.medir([[p[1], p[0]] for p in q])
    with pytest.raises(GM.GeometriaInvalida):
        GM.medir([["a", 1], [1, 2], [3, 4]])


def test_medir_remove_fecho_e_duplicados():
    q = quadrado(20.0)
    m = GM.medir([q[0], q[0], q[1], q[2], q[3], q[0]])
    assert len(m["anel_latlon"]) == 4


# ------------------------------------------------------------------ importação / exportação
def test_kml_ida_e_volta_e_kmz():
    q = quadrado(30.0)
    kml = GM.para_kml("Leira <do> Monte & Cª", q, "teste")
    assert "&lt;do&gt;" in kml and "&amp;" in kml
    lidos = GM.ler_ficheiro("t.kml", kml.encode())
    assert len(lidos) == 1 and abs(lidos[0]["area_m2"] - 900) < 0.1
    assert lidos[0]["nome"].startswith("Leira")
    b = io.BytesIO()
    with zipfile.ZipFile(b, "w") as z:
        z.writestr("doc.kml", kml)
    assert abs(GM.ler_ficheiro("t.kmz", b.getvalue())[0]["area_m2"] - 900) < 0.1


def test_kml_sem_entidades_externas():
    evil = ('<?xml version="1.0"?><!DOCTYPE kml [<!ENTITY x SYSTEM "file:///etc/passwd">]>'
            '<kml><Placemark><name>&x;</name><Polygon><outerBoundaryIs><LinearRing><coordinates>'
            '-8.4786,41.5402 -8.4780,41.5402 -8.4780,41.5406 -8.4786,41.5402</coordinates></LinearRing>'
            '</outerBoundaryIs></Polygon></Placemark></kml>')
    out = GM.ler_ficheiro("e.kml", evil.encode())
    assert "root:" not in out[0]["nome"]


def test_geojson_e_gpx():
    q = quadrado(25.0)
    gj = GM.para_geojson("T", q)
    assert abs(GM.ler_ficheiro("t.geojson", gj.encode())[0]["area_m2"] - 625) < 0.1
    trk = "".join(f'<trkpt lat="{la}" lon="{lo}"/>' for la, lo in q + [q[0]])
    gpx = f'<?xml version="1.0"?><gpx version="1.1"><trk><trkseg>{trk}</trkseg></trk></gpx>'
    assert abs(GM.ler_ficheiro("t.gpx", gpx.encode())[0]["area_m2"] - 625) < 0.5


def test_importacao_recusa_formatos_estranhos():
    with pytest.raises(GM.GeometriaInvalida):
        GM.ler_ficheiro("x.txt", b"ola")
    with pytest.raises(GM.GeometriaInvalida):
        GM.ler_ficheiro("x.geojson", b'{"type":"Point","coordinates":[1,2]}')


def test_csv_tm06():
    csv = GM.para_csv_tm06(quadrado(10.0)).splitlines()
    assert csv[0].startswith("vertice;M_PTTM06") and len(csv) == 5


# ------------------------------------------------------------------ BUPi
def test_bupi_servico_por_regiao():
    assert B.wms_para(41.5, -8.4) == B.WMS_CONTINENTE
    assert B.wms_para(32.7, -16.9) == B.WMS_MADEIRA
    assert B.wms_para(37.7, -25.6) is None


def test_bupi_parametros_crs84():
    p = B._params(41.5, -8.4)
    assert p["CRS"] == "CRS:84" and p["BBOX"].startswith("-8.4")
    assert p["INFO_FORMAT"] == "application/geo+json"


# ------------------------------------------------------------------ análise com rede simulada
def _servidor(q, rgg_props=None, ran=True, cadastro=True, bupi_ok=True):
    """Transporte falso: DGT OGC API + WMS do BUPi + altimetria."""
    terreno = ring_lonlat(q)
    # metade este do terreno em RAN
    x0, y0 = GM.tm06(*q[0])
    meia = [list(GM.tm06_inv(x0 + 20, y0 - 5)), list(GM.tm06_inv(x0 + 60, y0 - 5)),
            list(GM.tm06_inv(x0 + 60, y0 + 45)), list(GM.tm06_inv(x0 + 20, y0 + 45))]
    cols = [{"id": "freguesias", "title": "CAOP Freguesias"}, {"id": "crus", "title": "CRUS"},
            {"id": "cadastro", "title": "Cadastro Predial"},
            {"id": "srup_ran", "title": "Reserva Agrícola Nacional"},
            {"id": "srup_dph", "title": "Domínio Hídrico"}]

    async def t(method, url, params=None, headers=None, want="json"):
        if url.endswith("/collections"):
            return 200, {"collections": cols}
        if "/collections/freguesias/items" in url:
            return 200, {"features": [{"properties": {"freguesia": "Padim da Graça", "municipio": "Braga", "distrito": "Braga",
                                                      "dtmnfr": "030341"},
                                       "geometry": {"type": "Polygon", "coordinates": [[[-9, 41], [-8, 41], [-8, 42], [-9, 42], [-9, 41]]]}}]}
        if "/collections/crus/items" in url:
            return 200, {"features": [{"properties": {"classe": "Solo Rústico", "categoria": "Espaços Agrícolas"},
                                       "geometry": {"type": "Polygon", "coordinates": [terreno]}}]}
        if "/collections/cadastro/items" in url:
            return 200, {"features": ([{"properties": {"nic": "AB123"}, "geometry": {"type": "Polygon", "coordinates": [terreno]}}]
                                      if cadastro else [])}
        if "/collections/srup_ran/items" in url:
            return 200, {"features": ([{"properties": {}, "geometry": {"type": "Polygon", "coordinates": [ring_lonlat(meia)]}}]
                                      if ran else [])}
        if "/collections/srup_dph/items" in url:
            return 404, None
        if "geo.bupi.gov.pt" in url:
            if not bupi_ok:
                return 503, None
            feats = [{"properties": rgg_props}] if rgg_props else []
            return 200, {"type": "FeatureCollection", "features": feats}
        if "opentopodata" in url:
            locs = params["locations"].split("|")
            out = []
            for l in locs:
                la, lo = map(float, l.split(","))
                x, y = GM.tm06(la, lo)
                out.append({"elevation": 100 + (x - x0) * 0.10})    # 10 % a subir para este
            return 200, {"status": "OK", "results": out}
        return 404, None

    return t


def test_analise_completa():
    q = quadrado(40.0)
    G.set_transport(_servidor(q, rgg_props={"N_PROCESSO": "3504983", "ESTADO": "Concluída"}))
    res = asyncio.run(A.analisar(q, prazo_s=20))
    assert abs(res["geometria"]["area_m2"] - 1600) < 0.1
    caop = res["caop"]["data"]["principal"]
    assert caop["freguesia"] == "Padim da Graça" and caop["dicofre"] == "030341" and caop["fracao"] == pytest.approx(1.0, abs=1e-3)
    cad = res["cadastro"]["data"]
    assert cad["melhor_correspondencia"]["referencia"] == "AB123" and cad["melhor_correspondencia"]["iou"] > 0.99
    assert res["pdm"]["data"]["classes"][0]["solo"] == "rustico"
    ran = res["servidoes"]["data"]["ran"]
    assert len(ran) == 1 and ran[0]["fracao"] == pytest.approx(0.5, abs=0.01)
    assert res["servidoes"]["data"]["incompleta"] is True          # domínio hídrico não respondeu → por confirmar
    assert any(p["tipo"] == "recursos_hidricos" for p in res["servidoes"]["data"]["por_confirmar"])
    rg = res["bupi"]["data"]["rgg"]
    assert rg and rg[0]["id"] == "3504983" and rg[0]["fracao_amostras"] == 1.0
    d = res["declives"]["data"]
    assert d["declive_medio_pct"] == pytest.approx(10.0, abs=0.5) and d["exposicao"] == "O" and d["com_desnivel"]
    niveis = [a["nivel"] for a in res["alertas"]]
    assert niveis[0] == "critico"
    textos = " ".join(a["texto"] for a in res["alertas"])
    assert "3504983" in textos and "Reserva Agrícola" in textos and "por confirmar" in textos
    assert res["estado"]["servidoes"] == "parcial"


def test_analise_servicos_em_baixo_nunca_diz_sem_restricoes():
    q = quadrado(40.0)

    async def morto(*a, **k):
        return 0, None

    G.set_transport(morto)
    res = asyncio.run(A.analisar(q, prazo_s=15))
    assert res["geometria"]["area_m2"] > 0
    for tema in ("caop", "cadastro", "bupi", "pdm", "servidoes", "declives"):
        assert res[tema]["ok"] is False, tema
        assert res["estado"][tema] == "por_confirmar"
    assert not any(a["nivel"] == "critico" for a in res["alertas"])


def test_analise_sem_rgg_nem_ran():
    q = quadrado(40.0)
    G.set_transport(_servidor(q, rgg_props=None, ran=False))
    res = asyncio.run(A.analisar(q, prazo_s=20))
    assert res["bupi"]["ok"] and res["bupi"]["data"]["rgg"] == []
    assert res["servidoes"]["data"]["ran"] == []


# ------------------------------------------------------------------ rotas (base de dados em memória)
class _Cur:
    def __init__(self, docs):
        self.docs = docs

    def sort(self, k, d):
        self.docs.sort(key=lambda x: x.get(k) or "", reverse=d < 0)
        return self

    def limit(self, n):
        self.docs = self.docs[:n]
        return self

    def __aiter__(self):
        self._it = iter(self.docs)
        return self

    async def __anext__(self):
        try:
            return dict(next(self._it))
        except StopIteration:
            raise StopAsyncIteration


class _Col:
    def __init__(self):
        self.d = []

    def _m(self, q):
        return [x for x in self.d if all(x.get(k) == v for k, v in q.items())]

    async def find_one(self, q, proj=None):
        r = self._m(q)
        return dict(r[0]) if r else None

    def find(self, q, proj=None):
        return _Cur([dict(x) for x in self._m(q)])

    async def insert_one(self, doc):
        self.d.append(dict(doc))

    async def update_one(self, q, upd):
        for x in self._m(q):
            x.update(upd["$set"])

    async def delete_one(self, q):
        r = self._m(q)
        for x in r:
            self.d.remove(x)

        class R:
            deleted_count = len(r)
        return R()

    async def count_documents(self, q):
        return len(self._m(q))


def test_rotas_ciclo_completo(monkeypatch):
    import os
    os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
    os.environ.setdefault("DB_NAME", "test_terrenos")
    os.environ.setdefault("JWT_SECRET", "test")
    from fastapi import HTTPException
    from routes import terrenos as RT

    class _DB:
        terrenos = _Col()
    monkeypatch.setattr(RT, "db", _DB())
    q = quadrado(40.0)
    G.set_transport(_servidor(q, rgg_props=None, ran=True))
    u, outro = {"user_id": "u1"}, {"user_id": "u2"}
    loop = asyncio.new_event_loop()
    run = loop.run_until_complete
    try:
        t = run(RT.criar(RT.TerrenoIn(nome="Leira", anel_latlon=q), user=u))
        tid = t["terreno_id"]
        assert abs(t["area_m2"] - 1600) < 0.1
        with pytest.raises(HTTPException) as e:          # isolamento entre contas
            run(RT.obter(tid, user=outro))
        assert e.value.status_code == 404
        r = run(RT.analisar(tid, user=u))
        assert r["analise"]["servidoes"]["data"]["ran"]
        lst = run(RT.listar(user=u))["terrenos"]
        assert lst[0]["freguesia"] == "Padim da Graça" and lst[0]["alertas_criticos"] >= 1
        # mudar os limites apaga a análise antiga
        t2 = run(RT.atualizar(tid, RT.TerrenoPatch(anel_latlon=quadrado(30.0)), user=u))
        assert t2["analise"] is None and abs(t2["area_m2"] - 900) < 0.1
        kml = run(RT.exportar(tid, "kml", user=u))
        assert b"<coordinates>" in kml.body and "attachment" in kml.headers["content-disposition"]
        with pytest.raises(HTTPException):
            run(RT.exportar(tid, "exe", user=u))
        with pytest.raises(HTTPException) as e:
            run(RT.criar(RT.TerrenoIn(anel_latlon=[q[0], q[2], q[1], q[3]]), user=u))
        assert e.value.status_code == 422
        assert run(RT.apagar(tid, user=u))["ok"]
        assert run(RT.listar(user=u))["terrenos"] == []
    finally:
        loop.close()


# ------------------------------------------------------------------ Copernicus DEM GLO-30 (2.ª fonte, depois do LiDAR DGT)
def _geotiff(x0, y0, sx, sy, w, h, f, nodata=None):
    """GeoTIFF float32 sintético: valor = f(x, y) no centro de cada píxel."""
    import numpy as np
    from PIL import Image, TiffImagePlugin
    a = np.array([[f(x0 + (c + .5) * sx, y0 - (r + .5) * sy) for c in range(w)] for r in range(h)], dtype="float32")
    im = Image.fromarray(a, mode="F")
    ifd = TiffImagePlugin.ImageFileDirectory_v2()
    ifd[33550] = (float(sx), float(sy), 0.0)
    ifd.tagtype[33550] = 12
    ifd[33922] = (0.0, 0.0, 0.0, float(x0), float(y0), 0.0)
    ifd.tagtype[33922] = 12
    if nodata is not None:
        ifd[42113] = str(nodata)
        ifd.tagtype[42113] = 2
    b = io.BytesIO()
    im.save(b, "TIFF", tiffinfo=ifd, compression="tiff_deflate")
    return b.getvalue()


def test_nome_quadricula_copernicus():
    from engines.terrenos_pt import copernicus as C
    assert C.nome(41.54, -8.48) == "Copernicus_DSM_COG_10_N41_00_W009_00_DEM"
    assert C.nome(32.7, -16.9) == "Copernicus_DSM_COG_10_N32_00_W017_00_DEM"


def test_elevacoes_usa_copernicus_sem_dgt(monkeypatch, tmp_path):
    from engines.terrenos_pt import copernicus as C
    monkeypatch.setenv("MDT_CACHE_DIR", str(tmp_path / "mdt"))
    monkeypatch.delenv("DGT_CDD_USER", raising=False)
    C._RAM.clear()
    tif = _geotiff(-9.0, 42.0, 0.01, 0.01, 100, 100, lambda lo, la: 100 + 1000 * (la - 41))
    pedidos = []

    async def t(method, url, params=None, headers=None, want="json"):
        pedidos.append(url)
        if "copernicus-dem-30m" in url and "N41_00_W009" in url:
            return 200, tif
        return 404, None

    G.set_transport(t)
    r = asyncio.run(G.elevacoes([(41.5, -8.5), (41.6, -8.4)]))
    assert r["ok"] and "Copernicus" in r["fonte"] and r["data"]["tipo"] == "DSM"
    assert r["data"]["z"][0] == pytest.approx(600.0, abs=1.0) and r["data"]["z"][1] == pytest.approx(700.0, abs=1.0)
    n = len(pedidos)                      # segunda chamada: quadrícula já em cache
    asyncio.run(G.elevacoes([(41.5, -8.5)]))
    assert not [p for p in pedidos[n:] if "copernicus" in p]


def test_elevacoes_recurso_antigo_quando_copernicus_falha(monkeypatch, tmp_path):
    monkeypatch.setenv("MDT_CACHE_DIR", str(tmp_path / "mdt2"))
    monkeypatch.delenv("DGT_CDD_USER", raising=False)

    async def t(method, url, params=None, headers=None, want="json"):
        if "opentopodata" in url:
            return 200, {"status": "OK", "results": [{"elevation": 77.0}]}
        return 404, None

    G.set_transport(t)
    r = asyncio.run(G.elevacoes([(41.5, -8.5)]))
    assert r["ok"] and "EU-DEM" in r["fonte"] and r["data"]["z"] == [77.0]


def test_verificacao_cruzada(monkeypatch, tmp_path):
    from engines.terrenos_pt import copernicus as C
    monkeypatch.setenv("MDT_CACHE_DIR", str(tmp_path / "mdt3"))
    C._RAM.clear()
    tif = _geotiff(-9.0, 42.0, 0.01, 0.01, 100, 100, lambda lo, la: 203.0)

    async def t(method, url, params=None, headers=None, want="json"):
        return (200, tif) if "copernicus" in url else (404, None)

    G.set_transport(t)
    v = asyncio.run(C.verificar([(41.5, -8.5), (41.6, -8.4)], [200.0, 201.0]))
    assert v["pontos"] == 2 and v["dif_media_m"] == pytest.approx(-2.5, abs=0.01) and v["dif_max_abs_m"] == pytest.approx(3.0, abs=0.01)


# ------------------------------------------------------------------ integração: licenciamento automático + Assistente BTP / Aurora
def _parcela_padim(lado=30.0):
    import test_urbanismo_auto as TU
    x0, y0 = GM.tm06(TU.LAT, TU.LON)
    return [list(GM.tm06_inv(x0 + dx, y0 + dy)) for dx, dy in ((-lado, -lado), (lado, -lado), (lado, lado), (-lado, lado))]


def _fake_com_bupi(rgg_id=None):
    import test_urbanismo_auto as TU
    base = TU.fake()

    async def t(method, url, params=None, headers=None, want="json"):
        if "geo.bupi.gov.pt" in url:
            return 200, {"type": "FeatureCollection", "features": [{"properties": {"N_PROCESSO": rgg_id}}] if rgg_id else []}
        if "/collections/freguesias/items" in url:
            return 200, {"features": [{"properties": {"freguesia": "Padim da Graça", "municipio": "Braga", "dtmnfr": "030330"},
                                       "geometry": {"type": "Polygon", "coordinates": [[[-9, 41], [-8, 41], [-8, 42], [-9, 42], [-9, 41]]]}}]}
        return await base(method, url, params, headers, want)
    return t


def _run_pipeline(pedido, transport):
    from engines.urbanismo_pt.auto import pipeline as P
    G.set_transport(transport)
    G._COLLECTIONS.update(t=0.0, list=[])
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(P.executar(pedido))
    finally:
        loop.close()
        G.set_transport(None)


def test_licenciamento_a_partir_do_terreno_sem_morada():
    parcela = _parcela_padim()
    r = _run_pipeline({"texto": "Quero uma moradia T3 de 2 pisos com garagem neste terreno.", "parcela_latlon": parcela},
                      _fake_com_bupi("3504983"))
    assert r["ok"], r
    a = r["processo"]["auto"]
    assert a["localizacao"]["precisao"] == "terreno"
    assert r["processo"]["terreno"]["concelho"] == "Braga"
    assert abs(a["terreno"]["area_m2"] - 3600) < 5
    assert not any("porta" in x for x in r["pressupostos"])
    assert a["bupi"]["rgg"][0]["id"] == "3504983"
    assert any("3504983" in x for x in r["avisos"])


def test_licenciamento_sem_morada_nem_terreno_pede_morada():
    r = _run_pipeline({"texto": "quero uma casa"}, _fake_com_bupi())
    assert r["ok"] is False and r["estado"] == "falta_morada"


def test_assistente_terrenos_e_licenciamento(monkeypatch):
    import os
    os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
    os.environ.setdefault("DB_NAME", "test_terrenos")
    os.environ.setdefault("JWT_SECRET", "test")
    from engines import assistant_terrenos_tool as AT
    from engines.assistant_autorizacao_tool import AUTORIZACAO_TOOLS, run_autorizacao_tool
    from routes import urbanismo_auto as UA

    class _DB:
        terrenos = _Col()
        urbanismo_processos = _Col()
    fdb = _DB()
    monkeypatch.setattr(UA, "db", fdb)
    u = {"user_id": "u1"}
    # esquemas válidos para o modelo (todas as propriedades em required, sem extras)
    for t in AT.TERRENOS_TOOLS:
        assert set(t["parameters"]["required"]) == set(t["parameters"]["properties"])
    assert "terreno_id" in next(t for t in AUTORIZACAO_TOOLS if t["name"] == "licenciamento_automatico")["parameters"]["properties"]

    loop = asyncio.new_event_loop()
    run = loop.run_until_complete
    try:
        parcela = _parcela_padim()
        g = run(AT.run_terrenos_tool("terreno_gravar", {"nome": "Leira", "anel_latlon": parcela, "artigo_matricial": "R-123",
                                                          "lat": None, "lon": None}, u, fdb))
        assert g["ok"] and abs(g["area_m2"] - 3600) < 1
        tid = g["terreno_id"]
        # ficha do terreno gravado
        G.set_transport(_servidor(parcela, rgg_props={"N_PROCESSO": "999"}))
        G._COLLECTIONS.update(t=0.0, list=[])
        f = run(AT.run_terrenos_tool("terreno_ficha", {"terreno_id": tid}, u, fdb))
        assert f["ok"] and f["origem_limite"] == "terreno_gravado"
        assert f["freguesias"][0]["dicofre"] == "030341" and f["ran"] and f["bupi_rgg"][0]["id"] == "999"
        assert f["paginas"]["terrenos"] == "/terrenos"
        lst = run(AT.run_terrenos_tool("terrenos_listar", {}, u, fdb))
        assert lst["terrenos"][0]["terreno_id"] == tid and lst["terrenos"][0]["alertas_criticos"] >= 1
        # outra conta não vê o terreno
        assert run(AT.run_terrenos_tool("terreno_ficha", {"terreno_id": tid}, {"user_id": "u2"}, fdb))["ok"] is False
        # licenciamento automático com terreno_id: limites, área e artigo vêm do terreno
        G.set_transport(_fake_com_bupi())
        G._COLLECTIONS.update(t=0.0, list=[])
        r = run(run_autorizacao_tool("licenciamento_automatico", {"texto": "moradia T3 neste terreno", "terreno_id": tid}, u, {}))
        assert r["ok"], r
        doc = fdb.urbanismo_processos.d[0]
        ped = doc["auto"]["pedido"]
        assert ped["terreno_origem"] == tid and ped["artigo_matricial"] == "R-123" and abs(ped["area_terreno_m2"] - 3600) < 1
        assert doc["auto"]["localizacao"]["precisao"] == "terreno"
    finally:
        loop.close()
        G.set_transport(None)


def test_licenciamento_terreno_sem_morada_com_caop_lenta():
    """A CAOP/DGT lenta não pode fazer falhar a localização: a posição vem do próprio terreno."""
    import test_urbanismo_auto as TU
    from engines.urbanismo_pt.auto import pipeline as P
    parcela = _parcela_padim()

    async def morto(*a, **k):
        await asyncio.sleep(0)
        return 0, None

    G.set_transport(morto)
    loop = asyncio.new_event_loop()
    try:
        g = loop.run_until_complete(P._geo_da_parcela(parcela))
    finally:
        loop.close()
        G.set_transport(None)
    assert g["ok"] and g["data"]["precisao"] == "terreno"
    assert abs(g["data"]["lat"] - TU.LAT) < 1e-4 and abs(g["data"]["lon"] - TU.LON) < 1e-4
    assert g["data"]["concelho"] is None


# ------------------------------------------------------------------ limite a partir das RGG do BUPi (GeoPackage)
def _gpkg(caminho, poligonos_m, com_rtree=True):
    """GeoPackage mínimo em EPSG:3763 com polígonos (listas de (x, y)), com ou sem índice R-tree."""
    import sqlite3
    import struct
    from shapely.geometry import Polygon
    con = sqlite3.connect(caminho)
    con.execute("CREATE TABLE gpkg_geometry_columns (table_name TEXT, column_name TEXT, geometry_type_name TEXT, srs_id INT, z INT, m INT)")
    con.execute("INSERT INTO gpkg_geometry_columns VALUES ('rgg','geom','MULTIPOLYGON',3763,0,0)")
    con.execute("CREATE TABLE rgg (fid INTEGER PRIMARY KEY AUTOINCREMENT, geom BLOB, area REAL)")
    if com_rtree:
        con.execute("CREATE VIRTUAL TABLE rtree_rgg_geom USING rtree(id, minx, maxx, miny, maxy)")
    for pts in poligonos_m:
        g = Polygon(pts)
        minx, miny, maxx, maxy = g.bounds
        blob = b"GP" + bytes([0, 0b00000011]) + struct.pack("<i", 3763) + struct.pack("<4d", minx, maxx, miny, maxy) + g.wkb
        cur = con.execute("INSERT INTO rgg (geom, area) VALUES (?, ?)", (blob, g.area))
        if com_rtree:
            con.execute("INSERT INTO rtree_rgg_geom VALUES (?,?,?,?,?)", (cur.lastrowid, minx, maxx, miny, maxy))
    con.commit()
    con.close()


def test_rgg_limite_do_geopackage(tmp_path, monkeypatch):
    from engines.terrenos_pt import rgg_limite as RL
    x0, y0 = GM.tm06(LAT, LON)
    grande = [(x0 - 50, y0 - 50), (x0 + 50, y0 - 50), (x0 + 50, y0 + 50), (x0 - 50, y0 + 50)]
    pequeno = [(x0 - 10, y0 - 10), (x0 + 20, y0 - 10), (x0 + 20, y0 + 15), (x0 - 10, y0 + 15)]
    longe = [(x0 + 500, y0), (x0 + 520, y0), (x0 + 520, y0 + 20), (x0 + 500, y0 + 20)]
    gp = str(tmp_path / "rgg.gpkg")
    _gpkg(gp, [grande, pequeno, pequeno, longe])           # «pequeno» duplicado, como no conjunto real
    monkeypatch.setenv("BUPI_RGG_GPKG", gp)
    r = asyncio.run(RL.limite_no_ponto(LAT, LON))
    assert r["ok"] and r["data"]["origem"] == "gpkg"
    assert r["data"]["area_m2"] == pytest.approx(750.0, abs=0.5)        # escolhe a mais pequena
    assert r["data"]["sobreposicoes"] == 1                               # o duplicado não conta
    assert "2 RGG" in r["nota"]
    m = GM.medir(r["data"]["anel_latlon"])
    assert abs(m["area_m2"] - 750) < 0.5


def test_rgg_limite_sem_geopackage_nem_geometria_no_wms(monkeypatch):
    from engines.terrenos_pt import rgg_limite as RL
    monkeypatch.setenv("BUPI_RGG_GPKG", "/nao/existe.gpkg")

    async def t(method, url, params=None, headers=None, want="json"):
        if "geo.bupi.gov.pt" in url:
            return 200, {"type": "FeatureCollection", "features": [{"properties": {"N_PROCESSO": "1"}}]}
        return 404, None

    G.set_transport(t)
    r = asyncio.run(RL.limite_no_ponto(LAT, LON))
    assert r["ok"] is False and "não está instalado" in r["nota"]


def test_script_cria_indice_no_geopackage_sem_rtree(tmp_path):
    import importlib.util
    import sqlite3
    spec = importlib.util.spec_from_file_location("bupi_dl", os.path.join(os.path.dirname(__file__), "..", "scripts", "bupi_rgg_descarregar.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    x0, y0 = GM.tm06(LAT, LON)
    gp = str(tmp_path / "sem_rtree.gpkg")
    _gpkg(gp, [[(x0, y0), (x0 + 30, y0), (x0 + 30, y0 + 30), (x0, y0 + 30)]], com_rtree=False)
    info = mod.verificar_e_indexar(gp)
    assert info == {"tabela": "rgg", "geometria": "geom", "elementos": 1, "srs": 3763, "indice_criado": True}
    con = sqlite3.connect(gp)
    assert con.execute("SELECT COUNT(*) FROM rtree_rgg_geom").fetchone()[0] == 1
    con.close()
    from engines.terrenos_pt import rgg_limite as RL
    assert RL.candidatos_gpkg(gp, x0 + 10, y0 + 10)[0]["area_m2"] == pytest.approx(900, abs=0.5)


# ------------------------------------------------------------------ RGG em mosaicos no Tigris (sem disco no servidor)
class _S3Falso:
    def __init__(self):
        self.obj = {}

    def put_object(self, Bucket, Key, Body, ContentType=None):
        self.obj[(Bucket, Key)] = Body

    def get_object(self, Bucket, Key):
        if (Bucket, Key) not in self.obj:
            raise KeyError("NoSuchKey")

        class B:
            def __init__(s, b):
                s.b = b

            def read(s):
                return s.b
        return {"Body": B(self.obj[(Bucket, Key)])}

    def list_objects_v2(self, **k):
        return {"KeyCount": 0}


def test_mosaicos_rgg_publicar_e_ler(tmp_path, monkeypatch):
    import importlib.util
    from engines.terrenos_pt import rgg_limite as RL
    from engines.terrenos_pt import rgg_mosaicos as MO
    s3 = _S3Falso()
    monkeypatch.setenv("TIGRIS_BUCKET", "cp-teste")
    monkeypatch.setenv("BUPI_RGG_GPKG", "/nao/existe.gpkg")
    monkeypatch.setattr(MO, "cliente", lambda: s3)
    MO._RAM.clear()
    MO._MANIFESTO.update(t=0.0, m=None)
    # codificação ida e volta
    itens = [(1, 10.5, b"\x01\x02"), (2, 0.0, b"")]
    assert MO.descodificar(MO.codificar(itens)) == [(1, 10.5, b"\x01\x02"), (2, 0.0, b"")]
    # GeoPackage sintético com um prédio a atravessar a fronteira entre dois mosaicos de 2 km
    x0, y0 = GM.tm06(LAT, LON)
    bx = math.floor(x0 / 2000) * 2000 + 2000          # fronteira de mosaico a leste do ponto
    pred = [(bx - 30, y0 - 20), (bx + 30, y0 - 20), (bx + 30, y0 + 20), (bx - 30, y0 + 20)]
    gp = str(tmp_path / "rgg.gpkg")
    _gpkg(gp, [pred, pred])                            # duplicado
    spec = importlib.util.spec_from_file_location("bupi_mos", os.path.join(os.path.dirname(__file__), "..", "scripts", "bupi_rgg_mosaicos.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    monkeypatch.setattr(mod.DL, "recursos", lambda: [{"titulo": "rgg", "formato": "gpkg.zip", "url": "x", "tamanho": 1,
                                                      "atualizado": "2026-11-01T00:00:00"}])
    monkeypatch.setattr(sys, "argv", ["x", "--gpkg", gp])
    assert mod.main() == 0
    assert os.path.exists(gp)                          # GeoPackage dado pelo utilizador nunca é apagado
    keys = sorted(k for _, k in s3.obj)
    assert "bupi/rgg/atual.json" in keys and sum(k.endswith(".bin.gz") for k in keys) == 2   # o prédio entra nos 2 mosaicos
    man = json.loads(s3.obj[("cp-teste", "bupi/rgg/atual.json")])
    assert man["versao"] == "2026-11-01" and man["mosaicos"] == 2
    # leitura pelo backend dos dois lados da fronteira
    for dx in (-10, 10):
        la, lo = GM.tm06_inv(bx + dx, y0)
        r = asyncio.run(RL.limite_no_ponto(la, lo))
        assert r["ok"] and r["data"]["origem"] == "mosaicos", r
        assert r["data"]["area_m2"] == pytest.approx(2400, abs=0.5) and r["data"]["sobreposicoes"] == 0
        assert r["data"]["versao_dados"] == "2026-11-01"
    # ponto sem prédio: sem resultado, sem erro
    la, lo = GM.tm06_inv(bx + 500, y0 + 500)

    async def t(method, url, params=None, headers=None, want="json"):
        return 200, {"type": "FeatureCollection", "features": []}
    G.set_transport(t)
    assert asyncio.run(RL.limite_no_ponto(la, lo))["ok"] is False


def test_mosaicos_sem_manifesto_cai_para_wms(monkeypatch):
    from engines.terrenos_pt import rgg_limite as RL
    from engines.terrenos_pt import rgg_mosaicos as MO
    s3 = _S3Falso()
    monkeypatch.setenv("TIGRIS_BUCKET", "cp-teste")
    monkeypatch.setenv("BUPI_RGG_GPKG", "/nao/existe.gpkg")
    monkeypatch.setattr(MO, "cliente", lambda: s3)
    MO._RAM.clear()
    MO._MANIFESTO.update(t=0.0, m=None)

    async def t(method, url, params=None, headers=None, want="json"):
        return 200, {"type": "FeatureCollection", "features": []}
    G.set_transport(t)
    r = asyncio.run(RL.limite_no_ponto(LAT, LON))
    assert r["ok"] is False
