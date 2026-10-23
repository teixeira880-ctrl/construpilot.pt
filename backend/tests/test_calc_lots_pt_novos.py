"""Motores PT acrescentados (paridade com o .fr): piso radiante, solar térmico, pátio rebaixado, especialidades encadeadas + ferramentas."""
import pytest

pytest.importorskip("reportlab")

from engines.calc_lots import lotes_tecnicos, outils, patio_pluviais, piso_radiante, solar_termico  # noqa: E402

NOVAS = ("calcul_lotes_tecnicos", "calcul_piso_radiante", "verificar_solar_termico", "calcul_patio_pluvial")

DIV = [{"nome": "Sala", "tipo": "sala", "area_m2": 28, "paredes": [{"area_m2": 14}, {"tipo": "envidracado", "area_m2": 5}]},
       {"nome": "Quarto 1", "tipo": "quarto", "area_m2": 12, "paredes": [{"area_m2": 9}, {"tipo": "envidracado", "area_m2": 2}]},
       {"nome": "Cozinha", "tipo": "cozinha", "area_m2": 10, "paredes": [{"area_m2": 7}, {"tipo": "envidracado", "area_m2": 1.5}]},
       {"nome": "WC", "tipo": "casa_de_banho", "area_m2": 5, "paredes": [{"area_m2": 4}]}]


def _strict(sch, path="$"):
    if isinstance(sch, dict):
        if sch.get("type") == "object" or (isinstance(sch.get("type"), list) and "object" in sch["type"]):
            props = sch.get("properties", {})
            assert sch.get("additionalProperties") is False, path
            assert sorted(sch.get("required", [])) == sorted(props), path
        for k, v in sch.items():
            _strict(v, f"{path}.{k}")
    elif isinstance(sch, list):
        for i, v in enumerate(sch):
            _strict(v, f"{path}[{i}]")


def _nulls(sch):
    """Argumentos como o modo estrito os envia: todas as chaves, null onde não há valor."""
    return {k: None for k in sch["parameters"]["properties"]}


def test_tools_registadas_e_estritas():
    names = {t["name"] for t in outils.CALC_TOOLS}
    for n in NOVAS:
        assert n in names and n in outils.PROGRESS_LABELS and n in outils.PROTOCOL_PT
    for t in outils.CALC_TOOLS:
        _strict(t["parameters"], t["name"])


def test_piso_radiante_limites_en1264():
    r = piso_radiante.calcular({"divisoes": [{"nome": "Sala", "tipo": "sala", "area_m2": 30, "phi_w": 1500},
                                             {"nome": "WC", "tipo": "casa_de_banho", "area_m2": 5, "phi_w": 900}]})
    wc = next(x for x in r["divisoes"] if x["nome"] == "WC")
    assert wc["tf_lim"] == 33 and r["divisoes"][0]["tf_lim"] == 29
    assert wc["apoio_w"] > 0                       # 180 W/m² > limite → apoio
    assert 25 < r["theta_ida"] < 60 and r["circuitos"] >= 2
    assert all(x["comprimento_circuito_m"] <= piso_radiante.L_CIRCUITO_MAX + 1e-6 for x in r["divisoes"])


def test_solar_termico_criterios():
    r = solar_termico.calcular({"tipologia": 3, "coletor": {"numero": 2, "area_m2": 2.0, "eta0": 0.78, "a1": 3.5, "t_estagnacao_c": 190},
                                "deposito": {"volume_l": 200, "ua_w_k": 3.0}, "permutador": {"ua_w_k": 200}, "isolamento": {"tipo": "epdm"},
                                "tubagem": {"material": "aco_galvanizado"}})
    assert r["dimensionamento"]["ocupantes"] == 4
    assert abs(r["ua_permutador_min_w_k"] - 0.78 * 4 * 3.5 / 0.1) < 1e-9
    assert abs(r["ua_deposito_max_w_k"] - 0.16 * 200 ** 0.5) < 1e-9
    ko = {c["ref"].split(" — ")[0] for c in r["controles"] if c["ok"] is False}
    assert any("deposito" in k or "(UA)" in k or "§8" in k for k in ko)      # 3,0 > 2,26 W/K
    assert any(c["ok"] is False and "EPDM" in c["exigencia"] for c in r["controles"])   # 190 °C > 150 °C
    assert any(c["ok"] is False and "cobre" in c["exigencia"] for c in r["controles"])  # galvanizado


def test_patio_elevatoria():
    r = patio_pluviais.calcular({"area_m2": 18, "profundidade_m": 1.2})
    assert r["solucao"] == "elevatoria" and r["Q"] > 0.5 and r["bomba_m3h"] * 1 / 3.6 >= r["Q"]
    assert 0.7 <= r["v_imp"] <= 2.0 and r["V10"] < r["V100"]


def test_cadeia_completa_e_pdf():
    o = lotes_tecnicos.note({"concelho": "Porto", "obra": "nova", "divisoes": DIV, "solar_termico": {},
                             "isolamento_paredes": {"sistema": "etics", "suporte": [{"material": "tijolo_furado", "ep_mm": 150}]}})
    for k in lotes_tecnicos.LOTES:
        assert k in o, k
    assert o["bomba_calor"]["temperatura_ida"] == round(o["piso_radiante"]["theta_ida"] * 2) / 2
    assert any(c["nome"].startswith("Bomba de calor") for c in o["eletricidade"]["circuitos"])
    assert o["pdf"][:4] == b"%PDF" and o["png"][:4] == b"\x89PNG"


@pytest.mark.parametrize("name,args", [
    ("calcul_lotes_tecnicos", {"divisoes": DIV, "concelho": "Évora"}),
    ("calcul_piso_radiante", {"divisoes": [{"nome": "Sala", "tipo": "sala", "area_m2": 25, "phi_w": 1200}]}),
    ("verificar_solar_termico", {"tipologia": 2}),
    ("calcul_patio_pluvial", {"area_m2": 12, "profundidade_m": 0.9}),
])
def test_run_com_args_estritos(name, args):
    tool = next(t for t in outils.CALC_TOOLS if t["name"] == name)
    full = {**_nulls(tool), **args}
    out = outils.run(name, full)
    assert out["pdf"][:4] == b"%PDF" and out["resume"] and out["data"] is not None


class _Coll:
    def __init__(self):
        self.docs = []

    async def find_one(self, q, proj=None):
        return next((d for d in self.docs if all(d.get(k) == v for k, v in q.items())), None)

    async def update_one(self, q, upd, upsert=False):
        if not await self.find_one(q):
            self.docs.append(dict(upd.get("$setOnInsert") or {}))


def test_ponte_assistente_guarda_artefactos():
    import asyncio
    from engines.calc_lots import assistant_bridge as B

    class DB:
        assistant_artifacts = _Coll()
    db = DB()
    user, conv = {"user_id": "u1"}, {"conversation_id": "c1", "_quote_request_id": "r1"}
    out = asyncio.run(B.execute_calc_tool("calcul_patio_pluvial", {"area_m2": 15, "profundidade_m": 1.0}, user, conv, db))
    assert out["ok"] and out["artifact"]["format"] == "pdf" and out["preview_artifact"]["format"] == "png"
    assert len(db.assistant_artifacts.docs) == 2 and db.assistant_artifacts.docs[0]["data_b64"]
    again = asyncio.run(B.execute_calc_tool("calcul_patio_pluvial", {"area_m2": 15, "profundidade_m": 1.0}, user, conv, db))
    assert again["ok"] and len(db.assistant_artifacts.docs) == 2              # idempotente
    bad = asyncio.run(B.execute_calc_tool("calcul_piso_radiante", {"divisoes": []}, user, conv, db))
    assert bad["ok"] is False and "divisões" in bad["error"]
    assert set(B.CALC_STATUS) == B.CALC_TOOL_NAMES and "calcul_lotes_tecnicos" in B.CALC_INSTRUCTIONS
