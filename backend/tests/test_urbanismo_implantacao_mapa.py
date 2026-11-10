"""Editor de implantação no mapa: parcela desenhada pelo requerente, frente escolhida e posição da casa."""
import math

from engines.urbanismo_pt.auto import terreno as T
from tests.test_urbanismo_auto import LAT, LON, run

KX = 111_320.0 * math.cos(math.radians(LAT))
KY = 111_320.0


def ll(e, n):
    return [LAT + n / KY, LON + e / KX]


# terreno em L de ~1 150 m², frente (limite 0→1) a sul, junto à via do teste
PARCELA = [ll(-20, 8), ll(20, 8), ll(20, 40), ll(0, 40), ll(0, 26), ll(-20, 26)]


def test_parcela_invalida_e_rejeitada():
    assert T.anel_utilizador([[LAT, LON], [LAT, LON], [LAT, LON]], 0) is None            # área nula
    laco = [ll(0, 0), ll(30, 30), ll(30, 0), ll(0, 30)]                                     # limites cruzados
    assert T.anel_utilizador(laco, 0) is None
    assert T.anel_utilizador(PARCELA, 0)["frente_idx"] == 0


def test_parcela_do_mapa_substitui_a_hipotese():
    r = run({"morada": "Rua do Monte 7, Padim da Graça, Braga", "tipologia": "T2", "pisos": 1, "garagem": False,
             "parcela_latlon": PARCELA, "frente_idx": 0})
    assert r["ok"], r
    ter = r["processo"]["auto"]["terreno"]
    assert abs(ter["area_m2"] - (40 * 18 + 20 * 14)) < 15
    assert ter["area_origem"].startswith("limites indicados")
    assert ter["frente_fonte"] == "frente indicada pelo requerente"
    assert 160 <= ter["azimutes"]["frente"] <= 200         # frente virada a sul, como desenhado
    assert r["coerencia"]["ok"], r["coerencia"]["falhas"]
    assert any("ortofotomapa" in x for x in r["pressupostos"])


def test_posicao_escolhida_e_respeitada_ou_explicada():
    base = {"morada": "Rua do Monte 7, Padim da Graça, Braga", "tipologia": "T2", "pisos": 1, "garagem": False,
            "parcela_latlon": PARCELA, "frente_idx": 0}
    # casa encostada à via: viola o afastamento frontal → o motor explica, não move a casa às escondidas
    r = run({**base, "casa_centro_latlon": ll(-6, 15)})
    assert not r["ok"] and r["estado"] == "posicao_invalida"
    assert "frente" in r["motivo"] and "mínimo 5" in r["motivo"]
    # casa na parte larga do L, dentro dos afastamentos
    r = run({**base, "casa_centro_latlon": ll(10, 25)})
    assert r["ok"], r
    assert any("escolhida pelo requerente" in x for x in r["processo"]["auto"]["implantacao"]["decisoes"])
    q = r["verificacao"]["quadro"]["afastamentos_m"]
    assert q["frontal"] >= 5 - 1e-6 and min(q["lateral_esquerdo"], q["lateral_direito"]) >= 3 - 1e-6
    # [] repõe a posição automática
    r = run({**base, "casa_centro_latlon": []})
    assert r["ok"] and not any("escolhida pelo requerente" in x for x in r["processo"]["auto"]["implantacao"]["decisoes"])


def test_rota_zona_igual_ao_motor():
    import asyncio
    import os
    os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
    os.environ.setdefault("DB_NAME", "test_urbanismo_auto")
    os.environ.setdefault("JWT_SECRET", "test")
    from routes.urbanismo_auto import ZonaIn, zona
    r = asyncio.new_event_loop().run_until_complete(zona(ZonaIn(parcela_latlon=PARCELA, frente_idx=0), user={"user_id": "t"}))
    assert r["zona_latlon"] and 0 < r["area_m2"] < r["area_terreno_m2"]
    # parte larga: 40 − 2×3 = 34 m de largura útil; parte estreita até ao tardoz
    assert 300 < r["area_m2"] < 700
