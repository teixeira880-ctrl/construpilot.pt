"""Execução de obra: assessor de voz, mapa de avanço por zona, tesouraria da obra e câmaras.

Execução isolada: MongoDB simulada (mongomock_motor), armazenamento em memória, nenhuma chamada de rede nem de IA.
"""
import asyncio
import os
import struct
import sys
import types
import zlib
from datetime import date

import pytest

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "cp_test")
os.environ.setdefault("JWT_SECRET", "test-secret-not-used-in-prod")
os.environ.setdefault("FRONTEND_URL", "https://example.test")

mm = pytest.importorskip("mongomock_motor")

from fastapi import FastAPI, HTTPException, Request  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from engines import obra_execucao as ox  # noqa: E402

HOJE = date(2026, 11, 25)
CID, REF = "cht_x", "CP-EXEC-0001"
PARTS = {
    "dono": {"role": "client", "colab_role": "dono_obra", "name": "Dono"},
    "fiscal": {"role": "client", "colab_role": "fiscalizacao", "name": "Fiscal"},
    "empA": {"role": "subcontractor", "colab_role": "empresa", "name": "Empresa A", "lot": "Estrutura"},
}
ZONAS = [{"zona_id": "z1", "piso_id": "p1", "nome": "Cozinha"}, {"zona_id": "z2", "piso_id": "p1", "nome": "Quarto 1"}]


def run(c):
    return asyncio.run(c)


def png(w=200, h=100) -> bytes:
    raw = b"".join(b"\x00" + bytes([255, 255, 255, 255]) * w for _ in range(h))

    def chunk(t, d):
        return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xFFFFFFFF)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 6, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))


def _tipos(r):
    return [p["tipo"] for p in r["propostas"]]


# ====================================================================== assessor (interpretação local)
def test_assessor_stock_entrada_saida_com_material_conhecido():
    mats = [{"material": "Cimento CEM II 42,5", "unidade": "saco"}]
    r = ox.interpretar_local("Chegaram quarenta sacos de cimento e 3 paletes de tijolo. Gastámos 12 sacos de cimento no reboco.", mats)
    st = [p for p in r["propostas"] if p["tipo"] == "stock"]
    assert [(p["mov"], p["material"], p["unidade"], p["quantidade"]) for p in st] == [
        ("entrada", "Cimento CEM II 42,5", "saco", 40), ("entrada", "Tijolo", "palete", 3), ("saida", "Cimento CEM II 42,5", "saco", 12)]
    assert st[0]["material_conhecido"] and not st[1]["material_conhecido"]
    diario = r["propostas"][0]
    assert diario["tipo"] == "diario" and "40 saco Cimento CEM II 42,5" in diario["campos"]["entregas"]


def test_assessor_decimais_e_nome_original_do_material():
    r = ox.interpretar_local("Recebemos 2,5 m3 de areia. Betonámos 12 m3 de betão C25/30 na laje.")
    st = [(p["mov"], p["material"], p["unidade"], p["quantidade"]) for p in r["propostas"] if p["tipo"] == "stock"]
    assert ("entrada", "Areia", "m³", 2.5) in st and ("saida", "Betão C25/30", "m³", 12) in st
    assert "Betonámos" in r["propostas"][0]["campos"]["trabalhos"]          # a betonagem é também um trabalho do dia


def test_assessor_efetivos_qse_rfi_visitas_ocorrencias():
    t = ("Estiveram 4 pessoas da equipa do Rui e 2 eletricistas. O João trabalhou sem capacete no andaime. "
         "Temos uma dúvida para o arquiteto sobre a cota da soleira. Veio o fiscal às 15h. Choveu à tarde e parámos uma hora.")
    r = ox.interpretar_local(t)
    d = r["propostas"][0]["campos"]
    assert d["efetivos"] == [{"equipa": "Rui", "n": 4}, {"equipa": "Eletricistas", "n": 2}]
    assert "Veio o fiscal" in d["visitas"] and "Choveu" in d["ocorrencias"] and "sem capacete" in d["ocorrencias"]
    qse = next(p for p in r["propostas"] if p["tipo"] == "qse")
    assert qse["qse_tipo"] == "epi"
    rfi = next(p for p in r["propostas"] if p["tipo"] == "rfi")
    assert rfi["destinatario_perfil"] == "arquiteto"
    assert "Estiveram 4 pessoas" not in d["trabalhos"]


def test_assessor_avanco_so_com_zona_atividade_e_percentagem_ditas():
    atv = ox.modelo_atividades("acabamentos")
    r = ox.interpretar_local("O reboco da cozinha está a 60%. A pintura do quarto 1 está concluída. A pintura está a correr bem.", (), ZONAS, atv)
    av = [(p["zona"], p["atividade"], p["pct"]) for p in r["propostas"] if p["tipo"] == "avanco"]
    assert av == [("Cozinha", "Reboco / estuque", 60), ("Quarto 1", "Pintura", 100)]   # a 3.ª frase não tem zona nem %


def test_assessor_nao_inventa_nada():
    r = ox.interpretar_local("Bom dia, tudo normal.")
    assert _tipos(r) == ["diario"] and not any(p["tipo"] in ("stock", "qse", "rfi", "avanco") for p in r["propostas"])
    assert ox.interpretar_local("")["propostas"] == []


def test_normalizar_rejeita_resposta_ia_invalida():
    ia = {"diario": {"trabalhos": "Alvenaria piso 1", "efetivos": [{"equipa": "A", "n": -3}, {"equipa": "B", "n": 2.5}]},
          "stock": [{"mov": "entrada", "material": "Areia", "quantidade": -5}, {"mov": "roubo", "material": "X", "quantidade": 1},
                    {"mov": "saida", "material": "cimento cem 2 42.5", "quantidade": 3}],
          "qse": [{"tipo": "inventado", "titulo": "x"}], "rfi": [{"pergunta": "?"}],
          "avanco": [{"zona": "Garagem", "atividade": "Pintura", "pct": 50}, {"zona": "Cozinha", "atividade": "Pintura", "pct": 140},
                     {"zona": "Cozinha", "atividade": "pintura", "pct": 30}]}
    r = ox.normalizar(ia, [{"material": "Cimento CEM II 42,5", "unidade": "saco"}], ZONAS, ox.modelo_atividades("acabamentos"))
    assert r["propostas"][0]["campos"]["efetivos"] == []
    st = [p for p in r["propostas"] if p["tipo"] == "stock"]
    assert len(st) == 1 and st[0]["material"] == "Cimento CEM II 42,5" and st[0]["unidade"] == "saco"
    assert not [p for p in r["propostas"] if p["tipo"] in ("qse", "rfi")]
    av = [p for p in r["propostas"] if p["tipo"] == "avanco"]
    assert [(p["zona"], p["pct"]) for p in av] == [("Cozinha", 30)]       # zona inexistente e % > 100 descartadas


def test_juntar_texto_sem_repetir():
    assert ox.juntar_texto("Alvenaria piso 1", "alvenaria piso 1\nReboco", 100) == "Alvenaria piso 1\nReboco"


# ====================================================================== mapa
def test_estrutura_valida_e_resumo_ponderado():
    erro, est = ox.estrutura_valida([{"piso_id": "p1", "nome": "R/C"}],
                                    [{"zona_id": "z1", "piso_id": "p1", "nome": "Sala", "area_m2": 30, "ret": {"x": 0, "y": 0, "w": 50, "h": 50}},
                                     {"zona_id": "z2", "piso_id": "p1", "nome": "WC", "area_m2": 10}],
                                    [{"atividade_id": "a1", "nome": "Reboco", "peso": 3}, {"atividade_id": "a2", "nome": "Pintura", "peso": 1}])
    assert erro is None
    m = {**est, "progresso": {"z1|a1": {"pct": 100}, "z1|a2": {"pct": 0}, "z2|a1": {"pct": 100}, "z2|a2": {"pct": 100}}}
    r = ox.resumo_mapa(m)
    zs = {z["nome"]: z["avanco"] for z in r["zonas"]}
    assert zs == {"Sala": 75.0, "WC": 100.0}
    assert r["base"] == "area" and r["global"] == 81.2          # (75×30 + 100×10) / 40
    assert r["concluidas"] == 1


def test_estrutura_recusa_erros():
    assert ox.estrutura_valida([{"nome": "P1", "piso_id": "p1"}], [{"piso_id": "pX", "nome": "Z"}], [])[0]
    assert ox.estrutura_valida([{"nome": "P1", "piso_id": "p1"}], [{"piso_id": "p1", "nome": "Z", "ret": {"x": 80, "y": 0, "w": 40, "h": 10}}], [])[0]
    assert ox.estrutura_valida([], [], [{"nome": "A"}, {"nome": "a"}])[0]
    _, est = ox.estrutura_valida([{"nome": "P1", "piso_id": "p.$1"}], [], [])
    assert "." not in est["pisos"][0]["piso_id"] and "$" not in est["pisos"][0]["piso_id"]


# ====================================================================== tesouraria
def test_tesouraria_realizado_previsto_vencido_e_pior_saldo():
    faturas = [{"number": "FT 1", "status": "sent", "payments": [{"amount": 5000, "date": "2026-10-05"}], "remaining_due": 5000,
                "due_date": "2026-11-10"},
               {"number": "FT 2", "status": "sent", "payments": [], "remaining_due": 20000, "due_date": "2027-01-15"},
               {"number": "RASC", "status": "draft", "remaining_due": 99999}]
    enc = [{"order_id": "o1", "supplier": "Materiais Lda", "amount": 8000, "sent_at": "2026-11-01"},
           {"order_id": "o2", "supplier": "Ferro SA", "amount": 12000, "delivery": {"expected_date": "2026-12-10"}}]
    horas = [{"hours": 100, "date": "2026-11-03", "status": "validated"}, {"hours": 50, "date": "2026-11-04", "status": "pending"}]
    man = [{"mov_id": "m1", "tipo": "saida", "valor": 3000, "data": "2026-12-20", "categoria": "subempreiteiro", "descricao": "Canalizador"}]
    r = ox.tesouraria(faturas, enc, horas, man, HOJE, taxa_horaria=20, prazo_fornecedor=30)
    k = r["kpis"]
    assert k["recebido"] == 5000 and k["pago"] == 0                    # o1 vence a 01/12 (envio + 30 dias): ainda previsto
    assert k["vencido"] == 5000 and k["faturas_vencidas"] == 1
    assert k["por_receber"] == 25000 and k["por_pagar"] == 8000 + 12000 + 2000 + 3000
    assert k["saldo_final_previsto"] == 30000 - 25000
    assert k["pior_saldo"] == 5000 + 5000 - 2000 - 8000 - 12000 - 3000 and k["pior_saldo_data"] == "2026-12-20"
    assert any("negativa" in a for a in r["alertas"]) and any("vencida" in a for a in r["alertas"])
    assert [m["mes"] for m in r["meses"]] == ["2026-10", "2026-11", "2026-12", "2027-01"]


def test_tesouraria_sem_taxa_horaria_nao_inventa_mao_de_obra():
    r = ox.tesouraria([], [], [{"hours": 8, "date": "2026-11-03", "status": "validated"}], [], HOJE, taxa_horaria=None)
    assert r["eventos"] == [] and any("sem taxa" in n.lower() for n in r["notas"])


# ====================================================================== câmaras
def test_camaras_so_https_e_servicos_reconhecidos():
    assert ox.camara_valida({"url": "http://cam.local/snap.jpg"})[0]
    assert ox.camara_valida({"url": "https://user:pw@cam.example.com/snap.jpg"})[0]
    assert ox.camara_valida({"url": "https://evil.example.com/x", "tipo": "embed"})[0]
    erro, c = ox.camara_valida({"url": "https://www.youtube.com/embed/abc", "tipo": "embed", "atualizar_s": 1})
    assert erro is None and c["atualizar_s"] == 5


# ====================================================================== API
@pytest.fixture()
def api(monkeypatch):
    db = mm.AsyncMongoMockClient()["t_exec"]
    from engines import chantier_costs, storage, usage_meter
    from routes import chantiers, obra_colab, obra_execucao, obra_gestao, portal
    for mod in (chantiers, obra_colab, obra_gestao, obra_execucao, portal, chantier_costs):
        monkeypatch.setattr(mod, "db", db)

    async def sem_limite(user_id):
        return None
    monkeypatch.setattr(usage_meter, "check_ai_budget", sem_limite)
    blobs: dict = {}
    monkeypatch.setattr(storage, "put_object", lambda path, data, ct: blobs.__setitem__(path, (data, ct)) or {"path": path})
    monkeypatch.setattr(storage, "get_object", lambda path: blobs[path])
    monkeypatch.setattr(obra_execucao, "_today", lambda: HOJE)
    monkeypatch.setattr(obra_gestao, "_today", lambda: HOJE)

    async def seed():
        await db.chantiers.insert_one({"chantier_id": CID, "user_id": "u_owner", "name": "Moradia Execução", "ref": REF,
                                       "status": "en_cours", "cost_settings": {"labor_rate": 20}})
        for key, p in PARTS.items():
            await db.chantier_participants.insert_one({"participant_id": key, "chantier_id": CID, "chantier_ref": REF,
                                                       "owner_user_id": "u_owner", "email": f"{key}@example.com",
                                                       "status": "active", "session_version": 0, "lot": "", **p})
        await db.pro_documents.insert_one({"doc_id": "f1", "user_id": "u_owner", "chantier_id": CID, "doc_type": "invoice",
                                           "number": "FT 2026/1", "status": "sent", "trashed_at": None,
                                           "payments": [{"amount": 3000, "date": "2026-11-02"}], "remaining_due": 7000,
                                           "due_date": "2026-12-02", "totals": {"ttc": 10000}})
        await db.material_orders.insert_one({"order_id": "o1", "user_id": "u_owner", "chantier_id": CID, "status": "confirmé",
                                             "supplier": {"name": "Materiais Lda"}, "sent_at": "2026-11-01T10:00:00",
                                             "items": [{"designation": "Cimento", "unit": "saco", "qty": 40, "unit_price": 5}]})
        await db.obra_stock.insert_one({"mov_id": "s1", "chantier_id": CID, "tipo": "entrada", "material": "Cimento CEM II",
                                        "unidade": "saco", "quantidade": 10, "data": "2026-11-20"})
    run(seed())

    async def fake_user(request: Request):
        uid = request.headers.get("X-User")
        if not uid:
            raise HTTPException(401, "Não autenticado")
        return {"user_id": uid, "name": "Diretor de obra", "role": "user"}

    async def fake_participant(request: Request):
        p = await db.chantier_participants.find_one({"participant_id": request.headers.get("X-Part")}, {"_id": 0})
        if not p:
            raise HTTPException(401, "Sessão de convidado necessária")
        return p

    from core import security
    app = FastAPI()
    for r in (obra_execucao.pro_router, obra_execucao.portal_router, obra_gestao.pro_router, obra_gestao.portal_router):
        app.include_router(r, prefix="/api")
    app.dependency_overrides[security.current_user] = fake_user
    app.dependency_overrides[security.pro_required] = fake_user
    app.dependency_overrides[portal.current_participant] = fake_participant
    client = TestClient(app)

    class Api:
        def __init__(self):
            self.db = db

        def call(self, who, method, path, **kw):
            if who == "owner":
                return client.request(method, f"/api/chantiers/{CID}/execucao{path}", headers={"X-User": "u_owner"}, **kw)
            return client.request(method, f"/api/portal/{REF}/execucao{path}", headers={"X-Part": who}, **kw)

        def other(self, method, path, **kw):
            return client.request(method, f"/api/chantiers/{CID}/execucao{path}", headers={"X-User": "u_intruso"}, **kw)

    return Api()


def _estrutura(api, versao=0):
    atv = api.call("owner", "GET", "/mapa/modelo/acabamentos").json()["atividades"]
    body = {"pisos": [{"piso_id": "p1", "nome": "Piso 1"}],
            "zonas": [{"zona_id": "z1", "piso_id": "p1", "nome": "Cozinha", "ret": {"x": 5, "y": 5, "w": 40, "h": 40}},
                      {"zona_id": "z2", "piso_id": "p1", "nome": "Quarto 1", "ret": {"x": 50, "y": 5, "w": 40, "h": 40}}],
            "atividades": atv, "expected_version": versao}
    return api.call("owner", "PUT", "/mapa/estrutura", json=body)


def test_api_mapa_completo_e_perfis(api):
    r = _estrutura(api)
    assert r.status_code == 200 and r.json()["versao"] == 1
    assert _estrutura(api, 0).status_code == 409                                    # versão desatualizada
    av = api.call("owner", "POST", "/mapa/avanco", json={"itens": [{"zona_id": "z1", "atividade_id": "atv_09", "pct": 100}]})
    assert av.status_code == 200
    res = av.json()["resumo"]
    assert next(z for z in res["zonas"] if z["zona_id"] == "z1")["avanco"] == round(100 * 1 / 13, 1)
    assert api.call("owner", "POST", "/mapa/avanco", json={"itens": [{"zona_id": "zX", "atividade_id": "atv_09", "pct": 10}]}).status_code == 404
    assert api.call("owner", "POST", "/mapa/avanco", json={"itens": [{"zona_id": "z1", "atividade_id": "atv_09", "pct": 120}]}).status_code == 422
    up = api.call("owner", "POST", "/mapa/planta/p1", files={"file": ("planta.png", png(), "image/png")})
    assert up.status_code == 201 and up.json()["pisos"][0]["tem_planta"]
    pdf = api.call("owner", "GET", "/mapa.pdf")
    assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF")
    # retirar uma zona apaga o seu avanço, mantém a planta
    est = api.call("owner", "GET", "/mapa").json()
    body = {"pisos": [{"piso_id": "p1", "nome": "Piso 1"}], "zonas": [z for z in est["zonas"] if z["zona_id"] == "z2"],
            "atividades": est["atividades"], "expected_version": est["versao"]}
    r2 = api.call("owner", "PUT", "/mapa/estrutura", json=body).json()
    assert r2["progresso"] == {} and r2["pisos"][0]["tem_planta"]
    # portal: dono e fiscal leem, a empresa não; ninguém escreve
    assert api.call("dono", "GET", "/mapa").status_code == 200
    assert api.call("dono", "GET", "/mapa/planta/p1").status_code == 200
    assert api.call("empA", "GET", "/mapa").status_code == 403
    assert api.call("dono", "POST", "/mapa/avanco", json={"itens": []}).status_code in (404, 405)
    assert api.other("GET", "/mapa").status_code == 404                             # outra conta não vê a obra
    assert len(run(api.db.obra_mapa_registos.find({}).to_list(10))) == 1


def test_api_assessor_local_quando_ia_cai(api, monkeypatch):
    import engines

    async def boom(*a, **k):
        raise RuntimeError("sem IA")
    fake = types.ModuleType("engines.ai")
    fake._complete = boom
    fake._json = lambda raw, fb: fb
    monkeypatch.setitem(sys.modules, "engines.ai", fake)
    monkeypatch.setattr(engines, "ai", fake, raising=False)
    _estrutura(api)
    r = api.call("owner", "POST", "/assessor/interpretar", json={"texto": "Gastámos 4 sacos de cimento. A pintura da cozinha está a 50%.", "data": "2026-11-24"})
    assert r.status_code == 200
    j = r.json()
    assert j["fonte"] == "local" and j["diario_existente"] is None
    st = next(p for p in j["propostas"] if p["tipo"] == "stock")
    assert st["material"] == "Cimento CEM II" and st["material_conhecido"]
    av = next(p for p in j["propostas"] if p["tipo"] == "avanco")
    assert (av["zona_id"], av["pct"]) == ("z1", 50)
    assert run(api.db.obra_stock.count_documents({})) == 1                          # nada gravado sem confirmação
    assert api.call("owner", "POST", "/assessor/interpretar", json={"texto": "   "}).status_code == 400
    assert api.call("dono", "POST", "/assessor/interpretar", json={"texto": "x"}).status_code in (404, 405)


def test_api_assessor_ia_filtrada(api, monkeypatch):
    import engines

    async def ok(*a, **k):
        return '{"diario":{"trabalhos":"Reboco da cozinha"},"avanco":[{"zona":"Garagem","atividade":"Pintura","pct":40},{"zona_id":"z1","atividade":"Pintura","pct":40}],"stock":[]}'
    fake = types.ModuleType("engines.ai")
    fake._complete = ok
    import json
    fake._json = lambda raw, fb: json.loads(raw)
    monkeypatch.setitem(sys.modules, "engines.ai", fake)
    monkeypatch.setattr(engines, "ai", fake, raising=False)
    _estrutura(api)
    j = api.call("owner", "POST", "/assessor/interpretar", json={"texto": "Reboco da cozinha feito e pintura a 40%"}).json()
    assert j["fonte"] == "ia"
    av = [p for p in j["propostas"] if p["tipo"] == "avanco"]
    assert [(p["zona_id"], p["pct"]) for p in av] == [("z1", 40)]                    # a «Garagem» inventada é descartada


def test_api_tesouraria(api):
    r = api.call("owner", "GET", "/tesouraria")
    assert r.status_code == 200
    k = r.json()["kpis"]
    assert k["recebido"] == 3000 and k["por_receber"] == 7000 and k["por_pagar"] == 200       # o1: 40 × 5 €, paga a 01/12
    m = api.call("owner", "POST", "/tesouraria/movimentos", json={"tipo": "saida", "valor": 1500, "data": "2026-11-20", "realizado": True,
                                                                   "categoria": "subempreiteiro", "descricao": "Eletricista"})
    assert m.status_code == 201
    k = api.call("owner", "GET", "/tesouraria").json()["kpis"]
    assert k["pago"] == 1500 and k["saldo_atual"] == 1500
    mid = m.json()["mov_id"]
    assert api.call("owner", "PUT", f"/tesouraria/movimentos/{mid}", json={"tipo": "saida", "valor": 1000, "data": "2026-11-20", "realizado": True}).status_code == 200
    assert api.call("owner", "PUT", "/tesouraria/cfg", json={"prazo_fornecedor": 0, "saldo_inicial": 10000}).json()["kpis"]["saldo_atual"] == 10000 + 3000 - 1000 - 200
    assert api.call("owner", "DELETE", f"/tesouraria/movimentos/{mid}").status_code == 200
    assert api.call("dono", "GET", "/tesouraria").status_code in (404, 405)
    assert api.other("GET", "/tesouraria").status_code == 404


def test_api_camaras_partilha(api):
    body = {"camaras": [{"nome": "Grua", "url": "https://cam.example.com/snap.jpg", "tipo": "imagem", "partilhar": True},
                        {"nome": "Estaleiro", "url": "https://www.youtube.com/embed/xyz", "tipo": "embed", "partilhar": False}]}
    assert api.call("owner", "PUT", "/camaras", json=body).status_code == 200
    assert len(api.call("owner", "GET", "/camaras").json()["itens"]) == 2
    assert [c["nome"] for c in api.call("dono", "GET", "/camaras").json()["itens"]] == ["Grua"]
    assert api.call("empA", "GET", "/camaras").status_code == 403
    bad = {"camaras": [{"url": "http://192.168.1.10/snap.jpg"}]}
    assert api.call("owner", "PUT", "/camaras", json=bad).status_code == 422
    v = api.call("dono", "GET", "").json()["capacidades"]
    assert v["mapa.ver"] and v["camaras.ver"] and not v["tesouraria"] and not v["assessor"]
