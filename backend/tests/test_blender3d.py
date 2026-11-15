"""Modelo 3D georreferenciado e renders Blender do licenciamento automático."""
import asyncio
import importlib.util
import json
import math

import pytest
from mongomock_motor import AsyncMongoMockClient

from engines.urbanismo_pt.auto import blender3d as B
from engines.urbanismo_pt.auto import blender_job as BJ
from engines.urbanismo_pt.auto import dgt_cache as CACHE
from engines.urbanismo_pt.auto import geo as G
from engines.urbanismo_pt.auto import pecas_auto as PA
from engines.urbanismo_pt.auto import pipeline as P
from tests.test_urbanismo_auto import fake

TEXTO = "casa de 200m2 num terreno de 1500m2 casa térrea em granito e madeira na rua do monte nº7 padim da graça municipio de braga"


@pytest.fixture(scope="module")
def processo(tmp_path_factory):
    CACHE.usar_pasta(str(tmp_path_factory.mktemp("dgt")))
    G.set_transport(fake())
    G._COLLECTIONS.update(t=0.0, list=[])
    try:
        r = asyncio.new_event_loop().run_until_complete(P.executar({"texto": TEXTO}))
    finally:
        G.set_transport(None)
        G._CACHE_EM_TESTE["on"] = False
    assert r["ok"]
    return json.loads(json.dumps(r["processo"], default=list))


def test_pt_tm06_igual_ao_proj():
    # valores de referência do PROJ (pyproj 3, EPSG:4326 → EPSG:3763)
    assert B.pt_tm06(41.5402, -8.4786) == pytest.approx((-28829.405, 207929.803), abs=0.002)
    assert B.pt_tm06(38.7223, -9.1393) == pytest.approx((-87503.439, -104538.892), abs=0.002)


def test_posicao_do_sol():
    az, el = B.posicao_sol(41.54, -8.48)          # 21 de abril, 16h30 em Braga
    assert 235 < az < 255 and 35 < el < 47


def test_granito_e_madeira():
    assert PA.material_fachada("fachadas em granito e madeira") == "misto_granito_madeira"
    m = B.materiais_paredes("misto_granito_madeira", "frente", 1)
    assert m["principal"]["frente"] == "madeira" and m["principal"]["tardoz"] == "granito" and m["anexo"] == "madeira"


def test_georreferencia_bate_com_o_terreno(processo):
    ter = processo["auto"]["terreno"]
    g = B.Georef(ter["poligono_m"], ter["poligono_latlon"])
    assert g.residuo_m < 0.01
    for (x, y), (la, lo) in zip(ter["poligono_m"], ter["poligono_latlon"]):
        la2, lo2 = g.ll(x, y)
        assert abs(la2 - la) < 1e-7 and abs(lo2 - lo) < 1e-7
        x2, y2 = g.de_ll(la, lo)
        assert math.hypot(x2 - x, y2 - y) < 0.01


def test_especificacao_usa_a_geometria_exata(processo):
    s = B.especificacao(processo, [], "teste")
    vol = processo["volume"]
    casa = next(v for v in s["volumes"] if not v["anexo"])
    xs = [p[0] for p in casa["pts"]]
    ys = [p[1] for p in casa["pts"]]
    assert max(xs) - min(xs) == pytest.approx(vol["footprint_l_m"], abs=0.01)
    assert max(ys) - min(ys) == pytest.approx(vol["footprint_w_m"], abs=0.01)
    assert casa["h"] == pytest.approx(vol["levels"] * vol["storey_h_m"], abs=0.01)
    assert len(s["vaos"]) == len(processo["auto"]["vaos"])
    assert s["paredes"]["principal"]["frente"] in ("madeira", "granito")
    assert s["georef"]["origem_pt_tm06"] == list(B.pt_tm06(*processo["auto"]["terreno"]["poligono_latlon"][0]))
    # plataforma da casa à cota da soleira; malha do chão com UV do ortofotomapa
    assert all(0 <= u <= 1 and 0 <= v <= 1 for u, v in s["chao"]["uvs"])
    assert len(s["chao"]["verts"]) == len(s["chao"]["uvs"])
    assert {c["id"] for c in s["camaras"]} >= {"aerea", "drone", "rua", "topo"}
    assert s["relva"]["faces"] and s["pavimentos_malha"]


@pytest.mark.skipif(importlib.util.find_spec("bpy") is None, reason="Blender (bpy) não instalado")
def test_render_blender_real(processo):
    r = B.renderizar(processo, [], "teste", prazo_s=600)
    assert r["ok"], r.get("log")
    f = r["ficheiros"]
    for nome in ("aerea_antes.jpg", "aerea_depois.jpg", "rua_depois.jpg", "topo_depois.jpg", "modelo.glb", "cena.blend", "georreferencia.json"):
        assert nome in f and len(f[nome]) > 500, nome
    assert f["aerea_antes.jpg"][:3] == b"\xff\xd8\xff" and f["modelo.glb"][:4] == b"glTF"
    assert f["aerea_antes.jpg"] != f["aerea_depois.jpg"]
    geo = json.loads(f["georreferencia.json"])
    assert geo["crs"].startswith("EPSG:3763") and r["manifesto"]["motor"].startswith("Cycles")


def test_trabalho_com_acabamento_e_pdf(processo, monkeypatch):
    """O trabalho guarda os renders, acaba as vistas «depois» com a 1.ª como referência e entrega-as ao PDF."""
    db = AsyncMongoMockClient()["t"]
    jpg = b"\xff\xd8\xff" + b"0" * 600
    man = {"imagens": [{"ficheiro": f"{c}_{e}.jpg", "camara": c, "titulo": c, "estado": e, "segundos": 1}
                       for c in ("aerea", "drone") for e in ("antes", "depois")] +
                      [{"ficheiro": "topo_depois.jpg", "camara": "topo", "titulo": "topo", "estado": "depois", "segundos": 1}],
           "blender": "5.3.0", "motor": "Cycles (CPU, path tracing)", "amostras": 4, "resolucao": [320, 180]}
    ficheiros = {i["ficheiro"]: jpg for i in man["imagens"]} | {"modelo.glb": b"glTF0000", "georreferencia.json": b"{}"}

    async def fake_render(proc, q):
        return {"ok": True, "manifesto": man, "ficheiros": ficheiros, "georef": {"crs": "EPSG:3763"}, "sol": {}, "segundos": 1.0}
    chamadas = []

    async def fake_photo(base, prompt, style_ref=None, **kw):
        chamadas.append((prompt, style_ref))
        assert kw["engines"][0] == "gpt_image_2" and kw["timeout"] >= 300     # qualidade máxima primeiro, para o dossier
        return b"\xff\xd8\xffFOTO" + b"1" * 600, "nano_banana_3.1"
    monkeypatch.setattr(B, "renderizar_async", fake_render)
    import engines.photoreal as PR
    monkeypatch.setattr(PR, "render", fake_photo)

    async def go():
        await db.urbanismo_processos.insert_one({"processo_id": "p1", "user_id": "u1", **processo})
        await BJ.executar(db, "p1", "u1", "teste", True)
        return await BJ.estado(db, "p1", "u1"), await BJ.desenhos_para_pdf(db, "p1", "u1")
    st, sims = asyncio.new_event_loop().run_until_complete(go())
    assert st["estado"] == "pronto" and st["n_fotos"] == 4                     # 2 depois + 2 antes; topo não
    assert chamadas[0][1] is None and "low drone photograph" in chamadas[0][0]     # vista principal primeiro, sem referência
    depois = [c for c in chamadas[1:] if "finished single-family house" in c[0]]
    assert depois and all(c[1] is not None for c in depois)                   # alinhadas com a 1.ª
    antes = [c for c in chamadas if "Do NOT add any new house" in c[0]]
    assert len(antes) == 2 and all(c[1] is None for c in antes)
    assert len(sims) == 5 and all(s["png"] for s in sims)
    assert sum("acabamento fotográfico" in s["title"] for s in sims) == 4
    assert "modelo.glb" in st["ficheiros"]
