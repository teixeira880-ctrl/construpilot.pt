"""Terrenos PT — geometria PT-TM06, importação/exportação e análise com transporte HTTP simulado (sem rede)."""
import asyncio
import io
import json
import math
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
