"""MDT Portugal: projeção PT-TM06, GeoTIFF, mosaico de folhas LiDAR DGT (simuladas), análises e saídas."""
import asyncio
import math
import os

import numpy as np
import pytest

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "cp_test")
os.environ.setdefault("JWT_SECRET", "test-secret-not-used-in-prod")

from engines.mdt_pt import analise as AN, cdd, geotiff as G, grelha as GR, pttm06 as TM, servico as SV

LAT, LON = 38.7876, -9.3906          # Sintra


def _terreno(x, y):
    """Encosta a 8 % para sul + vale (talvegue) ao longo de x = x_c."""
    xc, yc = TM.ponto_tm(LAT, LON)
    return 150.0 + 0.08 * (y - yc) + 3.0 * (1 - np.exp(-((x - xc) / 25.0) ** 2))


def _folha(ix, iy, res):
    n = int(1000 / res)
    x0, y0 = ix * 1000.0, (iy + 1) * 1000.0
    xc = x0 + (np.arange(n) + 0.5) * res
    yc = y0 - (np.arange(n) + 0.5) * res
    X, Y = np.meshgrid(xc, yc)
    return G.escrever(G.Raster(_terreno(X, Y).astype(np.float32), x0, y0, res, res))


@pytest.fixture
def dgt_falso(monkeypatch):
    pedidos = []

    async def pesquisar(bbox, colecao):
        res = 0.5 if colecao == "MDT-50cm" else 2.0
        lo0, la0, lo1, la1 = bbox
        xs, ys = TM.para_tm(np.array([la0, la0, la1, la1]), np.array([lo0, lo1, lo0, lo1]))
        out = []
        for ix in range(int(math.floor(xs.min() / 1000)), int(math.floor(xs.max() / 1000)) + 1):
            for iy in range(int(math.floor(ys.min() / 1000)), int(math.floor(ys.max() / 1000)) + 1):
                out.append({"id": f"{colecao}-{ix}_{iy}", "url": f"x://{ix}/{iy}/{res}"})
        return out

    async def folha(colecao, iid, url):
        pedidos.append(iid)
        ix, iy, res = url[4:].split("/")
        return _folha(int(ix), int(iy), float(res))

    monkeypatch.setattr(cdd, "configurado", lambda: True)
    monkeypatch.setattr(cdd, "pesquisar", pesquisar)
    monkeypatch.setattr(cdd, "folha", folha)
    SV._CACHE.clear()
    return pedidos


def test_pttm06_ida_e_volta():
    lat = np.linspace(37.0, 42.1, 50)
    lon = np.linspace(-9.5, -6.2, 50)
    x, y = TM.para_tm(lat, lon)
    a, b = TM.para_ll(x, y)
    assert np.abs(a - lat).max() < 1e-9 and np.abs(b - lon).max() < 1e-9
    # origem da projeção
    x0, y0 = TM.ponto_tm(TM.LAT0, TM.LON0)
    assert abs(x0) < 1e-6 and abs(y0) < 1e-6


def test_geotiff_ida_e_volta():
    z = np.random.rand(40, 30).astype(np.float32) * 100
    z[3, 4] = np.nan
    r = G.ler(G.escrever(G.Raster(z, 1000.0, 2000.0, 2.0, 2.0)))
    assert (r.x0, r.y0, r.px) == (1000.0, 2000.0, 2.0)
    assert np.isnan(r.z[3, 4]) and np.nanmax(np.abs(r.z - z)) < 1e-4


def _poligono(meio_lado=40.0):
    x, y = TM.ponto_tm(LAT, LON)
    pts = [(x - meio_lado, y - meio_lado), (x + meio_lado, y - meio_lado), (x + meio_lado, y + meio_lado), (x - meio_lado, y + meio_lado)]
    la, lo = TM.para_ll(np.array([p[0] for p in pts]), np.array([p[1] for p in pts]))
    return [[float(a), float(b)] for a, b in zip(la, lo)]


def test_analise_completa_dgt(dgt_falso):
    res = asyncio.run(SV.analisar({"poligono": _poligono()}))
    assert res["meta"]["oficial"] and res["meta"]["colecao"] == "MDT-50cm"
    est = res["estatisticas"]
    # encosta a 8 %: declive médio próximo de 8 % (vale suave acrescenta um pouco)
    assert 7.5 <= est["declive_medio_pct"] <= 12.5
    assert est["exposicao"] in ("S", "SE", "SO")
    assert est["tem_desnivel"] and est["desnivel"] > 5.5
    assert res["curvas"] and all(len(c["ll"]) >= 2 for c in res["curvas"])
    assert sum(c["pct"] for c in res["classes_declive"]) == pytest.approx(100, abs=0.5)
    for k in ("hipsometria", "declives", "sombreado"):
        assert res["camadas"][k]["png"].startswith("data:image/png;base64,")
    mt = res["movimento_terras"]
    assert mt["ok"] and abs(mt["escavacao_m3"] - mt["aterro_m3"]) < 0.02 * max(mt["escavacao_m3"], 1)


def test_linha_de_agua_no_vale(dgt_falso):
    res = asyncio.run(SV.analisar({"centro": [LAT, LON], "raio_m": 250}))
    assert res["meta"]["colecao"] == "MDT-50cm"
    assert res["linhas_agua"], "o vale deve gerar pelo menos um talvegue"
    xc, _ = TM.ponto_tm(LAT, LON)
    principal = max(res["linhas_agua"], key=lambda l: l["bacia_m2"])
    xs = [TM.ponto_tm(a, b)[0] for a, b in principal["ll"]]
    assert abs(float(np.median(xs)) - xc) < 15, "o talvegue principal segue o fundo do vale"


def test_perfil_e_3d_e_exportacoes(dgt_falso):
    x, y = TM.ponto_tm(LAT, LON)
    a = TM.ponto_ll(x, y - 100)
    b = TM.ponto_ll(x, y + 100)
    pf = asyncio.run(SV.perfil({}, [a, b]))
    assert pf["comprimento_m"] == pytest.approx(200, abs=1)
    assert pf["declive_medio_pct"] == pytest.approx(8.0, abs=0.3)
    p = {"poligono": _poligono(60)}
    m = asyncio.run(SV.malha3d(p))
    assert len(m["z"]) == m["nx"] * m["ny"] and m["textura"].startswith("data:image/png")
    for fmt, magic in (("tif", (b"II", b"MM")), ("pdf", (b"%P",)), ("dxf", (b"  ", b"0\n", b" 0")), ("geojson", (b"{",))):
        dados, mime, nome = asyncio.run(SV.exportar(p, fmt, "Sintra"))
        assert len(dados) > 200 and dados[:2] in magic or dados[:1] in magic, fmt


def test_sem_dgt_usa_recurso_indicativo(monkeypatch):
    from engines.urbanismo_pt.auto import geo
    monkeypatch.setattr(cdd, "configurado", lambda: False)

    async def elev(pts):
        return {"ok": True, "data": {"z": [100.0 + 0.001 * i for i in range(len(pts))], "resolucao_m": 25},
                "fonte": "EU-DEM 25 m (teste)", "nota": "indicativo"}

    monkeypatch.setattr(geo, "elevacoes", elev)
    SV._CACHE.clear()
    res = asyncio.run(SV.analisar({"centro": [LAT, LON], "raio_m": 80}))
    assert res["meta"]["oficial"] is False and res["meta"]["avisos"]


def test_fora_de_portugal():
    with pytest.raises(GR.MdtErro):
        asyncio.run(GR.obter([(48.85, 2.35)]))


def test_cotas_dgt_para_licenciamento(dgt_falso):
    x, y = TM.ponto_tm(LAT, LON)
    pts = [TM.ponto_ll(x, y), TM.ponto_ll(x, y + 50)]
    r = asyncio.run(GR.cotas(pts))
    assert r and r["z"][1] - r["z"][0] == pytest.approx(4.0, abs=0.1)


def test_rotas_api(dgt_falso, monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from core.security import current_user
    from routes import mdt as rotas
    import routes.plans_common as pc

    async def sem_marca(uid):
        return None

    monkeypatch.setattr(pc, "_resolve_branding", sem_marca)
    app = FastAPI()
    app.include_router(rotas.router, prefix="/api")
    app.dependency_overrides[current_user] = lambda: {"user_id": "u1"}
    c = TestClient(app)
    assert c.get("/api/mdt/estado").json()["lidar_dgt"] is True
    body = {"poligono": _poligono(), "local": "Sintra"}
    r = c.post("/api/mdt/analise", json=body)
    assert r.status_code == 200 and r.json()["estatisticas"]["ok"]
    assert c.post("/api/mdt/3d", json=body).status_code == 200
    x, y = TM.ponto_tm(LAT, LON)
    r = c.post("/api/mdt/perfil", json={"linha": [list(TM.ponto_ll(x, y)), list(TM.ponto_ll(x + 50, y + 50))]})
    assert r.status_code == 200 and r.json()["pontos"]
    r = c.post("/api/mdt/exportar/pdf", json=body)
    assert r.status_code == 200 and r.content[:4] == b"%PDF" and "attachment" in r.headers["content-disposition"]
    assert c.post("/api/mdt/exportar/xyz", json=body).status_code == 404
    assert c.post("/api/mdt/analise", json={"centro": [48.85, 2.35], "raio_m": 50}).status_code == 422
