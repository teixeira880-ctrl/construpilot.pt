"""Gestão de obra: diário, qualidade e segurança, pedidos de esclarecimento, stock, curva S, alertas, webhooks.

Execução isolada: MongoDB simulada (mongomock_motor), armazenamento em memória, nenhuma chamada de rede nem de IA.
"""
import asyncio
import base64
import os
import struct
import zlib
from datetime import date, timedelta

import pytest

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "cp_test")
os.environ.setdefault("JWT_SECRET", "test-secret-not-used-in-prod")
os.environ.setdefault("FRONTEND_URL", "https://example.test")

mm = pytest.importorskip("mongomock_motor")

from fastapi import FastAPI, HTTPException, Request  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from engines import obra_gestao as og  # noqa: E402
from engines import webhooks_saida as wh  # noqa: E402

HOJE = date(2026, 11, 25)
CID, REF = "cht_g", "CP-GEST-0001"
PARTS = {
    "dono": {"role": "client", "colab_role": "dono_obra", "name": "Dono"},
    "fiscal": {"role": "client", "colab_role": "fiscalizacao", "name": "Fiscal"},
    "arq": {"role": "client", "colab_role": "arquiteto", "name": "Arquiteta"},
    "empA": {"role": "subcontractor", "colab_role": "empresa", "name": "Empresa A", "lot": "Estrutura"},
    "empB": {"role": "subcontractor", "colab_role": "empresa", "name": "Empresa B", "lot": "Canalização"},
}


def run(c):
    return asyncio.run(c)


def png(w=40, h=20) -> bytes:
    raw = b"".join(b"\x00" + bytes([0, 0, 0, 255]) * w for _ in range(h))

    def chunk(t, d):
        return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xFFFFFFFF)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 6, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))


# ====================================================================== regras puras
def test_5w2h_campos_obrigatorios_e_quanto_facultativo():
    assert set(og.acao_faltas({})) >= {"o quê", "porquê", "quem", "onde", "quando", "como"}
    ok = {"o_que": "Colocar guarda-corpo", "porque": "Queda em altura", "quem": "Empresa A", "onde": "Piso 2",
          "quando": "2026-11-30", "como": "Guarda-corpo metálico"}
    assert og.acao_faltas(ok) == []
    assert og.acao_faltas({**ok, "quanto": -1}) == ["quanto custa"]
    assert og.acao_faltas({**ok, "quando": "30/11"}) == ["quando"]


def test_ciclo_da_acao():
    assert og.acao_transicao("aberta", "feita", gestao=False, responsavel=True)
    assert not og.acao_transicao("feita", "verificada", gestao=False, responsavel=True)   # a empresa não se verifica a si própria
    assert og.acao_transicao("feita", "verificada", gestao=True, responsavel=False)
    assert og.acao_transicao("feita", "em_curso", gestao=True, responsavel=False)          # devolvida: eficácia não comprovada
    assert not og.acao_transicao("verificada", "aberta", gestao=True, responsavel=False)
    assert not og.acao_transicao("aberta", "feita", gestao=False, responsavel=False)


def test_fecho_de_nc_exige_acoes_verificadas_ou_justificacao():
    nc = {"tipo": "nao_conformidade", "acoes": [{"estado": "feita"}]}
    assert not og.pode_fechar(nc)
    assert og.pode_fechar(nc, "Aceite pelo dono de obra em ata n.º 4")
    assert og.pode_fechar({"tipo": "nao_conformidade", "acoes": [{"estado": "verificada"}]})
    assert og.pode_fechar({"tipo": "dialogo_seguranca"})


def test_stock_saldos_e_minimo():
    movs = [{"tipo": "entrada", "material": "Cimento CEM II", "unidade": "saco", "quantidade": 40, "data": "2026-11-01"},
            {"tipo": "saida", "material": "cimento  cem ii", "unidade": "Saco", "quantidade": 35, "data": "2026-11-03"},
            {"tipo": "ajuste", "material": "Cimento CEM II", "unidade": "saco", "quantidade": -1, "data": "2026-11-04"}]
    s = og.stock_saldos(movs, {"cimento cem ii|saco": 10})
    assert len(s) == 1 and s[0]["saldo"] == 4 and s[0]["abaixo_minimo"]


def test_meteo_nunca_inventada():
    daily = {"time": ["2026-11-24"], "weather_code": [63], "temperature_2m_min": [8.1], "temperature_2m_max": [13.0],
             "precipitation_sum": [12.4], "wind_speed_10m_max": [22.0]}
    assert og.meteo_do_dia(daily, date(2026, 11, 25)) is None
    m = og.meteo_do_dia(daily, date(2026, 11, 24))
    assert m["codigo"] == 63 and m["precipitacao_mm"] == 12.4 and m["alerta"]


def _sched():
    return {"tasks": [
        {"id": "t1", "name": "Obra grossa", "resource": "Obra grossa", "duration": 10, "start_date": "2026-11-02",
         "end_date": "2026-11-13", "progress": 100, "critical": True},
        {"id": "t2", "name": "Canalização", "resource": "Canalização", "duration": 10, "start_date": "2026-11-16",
         "end_date": "2026-11-27", "progress": 20, "critical": True}]}


def test_curva_s_ponderada_pelo_custo_e_sem_inventar_o_real():
    lotes = [{"lot": "Obra grossa", "cost_prev_ht": 30000, "coverage": {"complete": True}},
             {"lot": "Canalização", "cost_prev_ht": 10000, "coverage": {"complete": True}}]
    c = og.curva_s(_sched(), None, lotes, HOJE, snapshots=[{"data": "2026-11-10", "avanco_pct": 40}])
    assert c["disponivel"] and c["ponderacao"] == "custo"
    assert c["real_hoje_pct"] == 80.0                    # 0,75 × 100 + 0,25 × 20
    primeira = c["pontos"][0]
    assert primeira["real_pct"] is None                   # antes do 1.º registo: desconhecido, não zero
    assert c["pontos"][1]["real_pct"] == 40               # instantâneo registado
    assert c["pontos"][-1]["previsto_pct"] == 100
    assert "custo_real" in primeira and primeira["custo_real"] is None


def test_curva_s_sem_planeamento_e_custos_incompletos():
    assert not og.curva_s(None, None, [], HOJE, [])["disponivel"]
    c = og.curva_s(_sched(), None, [], HOJE, [], {"completo": False, "orcamento_custo": None, "pontos": [("2026-11-03", 500)]})
    assert c["ponderacao"] == "duracao" and all(p["custo_real"] is None for p in c["pontos"])
    assert any("incompletos" in n for n in c["notas"])


def test_alertas():
    qse = [{"item_id": "q1", "numero": 1, "tipo": "nao_conformidade", "titulo": "Recobrimento", "gravidade": "critica", "estado": "aberto",
            "acoes": [{"o_que": "Refazer", "quando": "2026-11-20", "estado": "aberta"}]},
           {"item_id": "q2", "numero": 2, "tipo": "incidente", "titulo": "Corte na mão", "estado": "aberto", "data": "2026-11-24"}]
    al = og.alertas(hoje=HOJE, schedule={"tasks": [{"id": "t", "name": "Lajes", "end_date": "2026-11-20", "progress": 50, "critical": True}]},
                    lotes=[{"lot": "Estrutura", "cost_prev_ht": 1000, "real_cost_ht": 1200}], qse=qse,
                    rfis=[{"rfi_id": "r", "numero": "PE-001", "assunto": "Cota", "estado": "aberto", "prazo": "2026-11-20"}],
                    stock=[{"material": "Areia", "saldo": 1, "minimo": 5, "abaixo_minimo": True, "chave": "a"}],
                    ultimo_diario="2026-11-10", diario_ativo=True)
    tipos = [a["tipo"] for a in al]
    assert {"tarefa_atraso", "lote_derrapagem", "nc_critica", "nc_atraso", "acidente", "rfi_atraso", "stock_minimo",
            "diario_em_falta"} <= set(tipos)
    assert al[0]["severidade"] == "critica"


def test_escopo_rfi_e_qse_para_empresa():
    sc = og.rfi_scope({og.EMPRESA}, "empA", "empA")
    assert {"visibilidade": "todos"} in sc["$or"] and {"destinatario.id": "empA"} in sc["$or"]
    assert og.rfi_scope({og.GESTOR}, None, "u") is None
    assert og.qse_scope({og.EMPRESA}, None) == {"$or": [{"empresa_id": "__nenhuma__"}, {"autor.empresa_id": "__nenhuma__"},
                                                         {"acoes.quem_empresa_id": "__nenhuma__"}]}
    assert not og.qse_visivel({og.EMPRESA}, "empB", {"empresa_id": "empA", "autor": {"empresa_id": "empA"}, "acoes": []})


def test_webhook_url_anti_ssrf():
    assert wh.url_valida("https://erp.exemplo.pt/hooks/cp")
    for u in ("http://erp.exemplo.pt", "https://127.0.0.1/x", "https://10.0.0.5/x", "https://localhost/x",
              "https://169.254.169.254/latest", "https://user:pw@erp.exemplo.pt", "https://intranet.local/x", "ftp://a.b",
              "https://100.64.0.1/x", "https://[::ffff:10.0.0.1]/x"):
        assert not wh.url_valida(u), u
    assert wh.assinatura("s", b"{}").startswith("sha256=")


# ====================================================================== API
@pytest.fixture()
def api(monkeypatch):
    db = mm.AsyncMongoMockClient()["t_gestao"]
    from engines import chantier_costs, storage, usage_meter
    from routes import chantiers, obra_colab, obra_gestao, portal
    for mod in (chantiers, obra_colab, obra_gestao, portal, chantier_costs):
        monkeypatch.setattr(mod, "db", db)

    async def sem_limite(user_id):   # o orçamento IA da conta é testado no seu próprio módulo
        return None
    monkeypatch.setattr(usage_meter, "check_ai_budget", sem_limite)
    blobs: dict = {}
    monkeypatch.setattr(storage, "put_object", lambda path, data, ct: blobs.__setitem__(path, (data, ct)) or {"path": path})
    monkeypatch.setattr(storage, "get_object", lambda path: blobs[path])
    monkeypatch.setattr(obra_gestao, "_today", lambda: HOJE)
    monkeypatch.setattr(obra_colab, "_today", lambda: HOJE)

    async def no_meteo(ctx, dia):
        return None
    monkeypatch.setattr(obra_gestao, "_meteo", no_meteo)

    async def no_branding(ctx):
        return {"company_name": "Construtora Teste"}
    monkeypatch.setattr(obra_gestao, "_branding", no_branding)
    sent = []

    async def fake_disparar(_db, owner, evento, dados):
        sent.append((owner, evento, dados))
    monkeypatch.setattr(wh, "disparar", fake_disparar)

    async def seed():
        await db.chantiers.insert_one({"chantier_id": CID, "user_id": "u_owner", "name": "Moradia Gestão", "ref": REF, "status": "en_cours"})
        for key, p in PARTS.items():
            await db.chantier_participants.insert_one({"participant_id": key, "chantier_id": CID, "chantier_ref": REF,
                                                       "owner_user_id": "u_owner", "email": f"{key}@example.com",
                                                       "status": "active", "session_version": 0, "lot": "", **p})
        await db.projects.insert_one({"project_id": "prj1", "user_id": "u_owner", "chantier_id": CID, "name": "Moradia Gestão"})
        await db.hr_timesheets.insert_many([
            {"entry_id": "ts1", "employer_id": "u_owner", "worker_id": "w1", "worker_name": "Rui", "project_id": "prj1",
             "clock_in": "2026-11-24T08:00:00", "hours": 8, "status": "validated"},
            {"entry_id": "ts2", "employer_id": "u_owner", "worker_id": "w2", "worker_name": "Ana", "project_id": "prj1",
             "clock_in": "2026-11-24T08:30:00", "hours": 7.5, "status": "pending"}])
        await db.hr_notes.insert_one({"note_id": "n1", "employer_id": "u_owner", "worker_id": "w1", "worker_name": "Rui",
                                      "project_id": "prj1", "type": "incident", "message": "Guarda-corpo solto no piso 1",
                                      "created_at": "2026-11-24T10:00:00"})
        await db.material_orders.insert_one({"order_id": "o1", "user_id": "u_owner", "chantier_id": CID, "status": "confirmé",
                                             "supplier": {"name": "Materiais Lda"},
                                             "items": [{"designation": "Cimento CEM II", "unit": "saco", "qty": 40, "unit_price": 5}]})
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
    for r in (obra_gestao.pro_router, obra_gestao.portal_router, obra_gestao.webhooks_router):
        app.include_router(r, prefix="/api")
    app.dependency_overrides[security.current_user] = fake_user
    app.dependency_overrides[security.pro_required] = fake_user
    app.dependency_overrides[portal.current_participant] = fake_participant
    client = TestClient(app)

    class Api:
        def __init__(self):
            self.db, self.sent = db, sent

        def call(self, who, method, path, **kw):
            if who == "owner":
                return client.request(method, f"/api/chantiers/{CID}/gestao{path}", headers={"X-User": "u_owner"}, **kw)
            return client.request(method, f"/api/portal/{REF}/gestao{path}", headers={"X-Part": who}, **kw)

        def raw(self, method, url, **kw):
            return client.request(method, url, headers={"X-User": "u_owner"}, **kw)

    return Api()


def _sig():
    return "data:image/png;base64," + base64.b64encode(png()).decode()


def test_api_diario_completo(api):
    prep = api.call("owner", "GET", "/diario/preparar", params={"data": "2026-11-24"}).json()
    assert prep["efetivo_auto"]["trabalhadores"] == 2 and prep["efetivo_auto"]["horas"] == 15.5 and prep["meteo"] is None
    assert api.call("owner", "POST", "/diario", json={"data": "2026-11-26", "trabalhos": "x"}).status_code == 400   # dia futuro
    d = api.call("owner", "POST", "/diario", json={"data": "2026-11-24", "trabalhos": "Betonagem da laje do piso 1"}).json()
    assert d["estado"] == "rascunho" and d["meteo"] is None
    assert api.call("owner", "POST", "/diario", json={"data": "2026-11-24"}).status_code == 409                    # um por dia
    r = api.call("owner", "POST", f"/diario/{d['diario_id']}/fotos", files={"file": ("f.png", png(), "image/png")})
    assert r.status_code == 201 and len(r.json()["fotos"]) == 1
    up = api.call("owner", "PUT", f"/diario/{d['diario_id']}", json={"ocorrencias": "Atraso do camião", "expected_version": 0})
    assert up.status_code == 200 and up.json()["ocorrencias"] == "Atraso do camião"
    assert api.call("owner", "PUT", f"/diario/{d['diario_id']}", json={"ocorrencias": "y", "expected_version": 0}).status_code == 409
    # visto antes da assinatura: recusado; sem traço de assinatura: recusado
    assert api.call("fiscal", "POST", f"/diario/{d['diario_id']}/visto", json={}).status_code == 404               # ainda não publicado
    assert api.call("owner", "POST", f"/diario/{d['diario_id']}/assinar", json={"nome": "Eng. Silva", "imagem": "data:image/png;base64,AAAA"}).status_code == 400
    s = api.call("owner", "POST", f"/diario/{d['diario_id']}/assinar", json={"nome": "Eng. Silva", "imagem": _sig()})
    assert s.status_code == 200 and s.json()["estado"] == "assinado" and "imagem" not in s.json()["assinatura"]
    # imutável depois de assinado; só aditamentos
    assert api.call("owner", "PUT", f"/diario/{d['diario_id']}", json={"trabalhos": "alterado", "expected_version": 1}).status_code == 409
    assert api.call("owner", "POST", f"/diario/{d['diario_id']}/fotos", files={"file": ("g.png", png(), "image/png")}).status_code == 409
    ad = api.call("owner", "POST", f"/diario/{d['diario_id']}/aditamento", json={"texto": "Correção: 3 m³ e não 2 m³"}).json()
    assert ad["trabalhos"] == "Betonagem da laje do piso 1" and len(ad["aditamentos"]) == 1
    # portal: a empresa nunca vê o diário; o dono só vê o que foi publicado
    assert api.call("empA", "GET", "/diario").status_code == 403
    assert api.call("dono", "GET", "/diario").json()["itens"] == []
    api.call("owner", "POST", f"/diario/{d['diario_id']}/publicar", json={"publicado": True})
    assert len(api.call("dono", "GET", "/diario").json()["itens"]) == 1
    assert api.call("dono", "POST", f"/diario/{d['diario_id']}/visto", json={}).status_code == 403
    v = api.call("fiscal", "POST", f"/diario/{d['diario_id']}/visto", json={"observacao": "Visto."}).json()
    assert v["visto_fiscal"]["nome"] == "Fiscal"
    pdf = api.call("dono", "GET", f"/diario/{d['diario_id']}/pdf")
    assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF")
    assert api.call("dono", "GET", f"/diario/{d['diario_id']}/assinatura").status_code == 200
    assert ("u_owner", "diario.assinado") in [(o, e) for o, e, _ in api.sent]
    hist = api.call("owner", "GET", "/historico").json()["itens"]
    assert {h["acao"] for h in hist} >= {"diario.criar", "diario.assinar", "diario.aditamento", "diario.visto"}
    assert api.call("dono", "GET", "/historico").status_code in (403, 404)


def test_api_qse_separacao_e_plano_de_acao(api):
    acao = {"o_que": "Fixar guarda-corpo", "porque": "Risco de queda", "quem": "Empresa A", "onde": "Piso 1",
            "quando": "2026-11-27", "como": "Abraçadeiras e rodapé"}
    nc = api.call("empA", "POST", "/qse", json={"tipo": "nao_conformidade", "titulo": "Guarda-corpo incompleto",
                                                "gravidade": "alta", "acoes": [acao]})
    assert nc.status_code == 201
    nc = nc.json()
    assert nc["empresa_id"] == "empA" and nc["acoes"][0]["quem_empresa_id"] == "empA" and nc["numero"] == 1
    assert api.call("empB", "GET", f"/qse/{nc['item_id']}").status_code == 404           # outra empresa não vê
    assert api.call("empB", "GET", "/qse").json()["itens"] == []
    assert len(api.call("dono", "GET", "/qse").json()["itens"]) == 1
    assert api.call("arq", "GET", "/qse").status_code == 403
    assert api.call("owner", "POST", "/qse", json={"tipo": "nao_conformidade", "titulo": "x y", "acoes": [{"o_que": "a"}]}).status_code == 400
    aid = nc["acoes"][0]["acao_id"]
    assert api.call("empA", "PATCH", f"/qse/{nc['item_id']}/acoes/{aid}", json={"estado": "verificada"}).status_code == 409
    assert api.call("empA", "PATCH", f"/qse/{nc['item_id']}/acoes/{aid}", json={"estado": "feita"}).status_code == 200
    # a NC só fecha com a ação verificada (ou justificação); a empresa nunca fecha
    assert api.call("fiscal", "POST", f"/qse/{nc['item_id']}/fechar", json={}).status_code == 409
    assert api.call("empA", "POST", f"/qse/{nc['item_id']}/fechar", json={"justificacao": "ok"}).status_code == 403
    assert api.call("fiscal", "POST", f"/qse/{nc['item_id']}/fechar", json={"justificacao": "Aceite em ata n.º 5"}).json()["estado"] == "fechado"
    nc2 = api.call("owner", "POST", "/qse", json={"tipo": "nao_conformidade", "titulo": "Recobrimento insuficiente", "acoes": [acao]}).json()
    assert api.call("owner", "POST", f"/qse/{nc2['item_id']}/fechar", json={}).status_code == 409
    a2 = nc2["acoes"][0]["acao_id"]
    api.call("owner", "PATCH", f"/qse/{nc2['item_id']}/acoes/{a2}", json={"estado": "feita"})
    api.call("fiscal", "PATCH", f"/qse/{nc2['item_id']}/acoes/{a2}", json={"estado": "verificada"})
    f = api.call("fiscal", "POST", f"/qse/{nc2['item_id']}/fechar", json={})
    assert f.status_code == 200 and f.json()["estado"] == "fechado"
    assert api.call("owner", "POST", f"/qse/{nc2['item_id']}/acoes", json=acao).status_code == 409   # fechado


def test_api_inspecao_gera_nc_e_alerta_de_operario(api):
    insp = api.call("fiscal", "POST", "/qse", json={"tipo": "inspecao", "titulo": "Inspeção de estaleiro", "checklist_modelo": "estaleiro"}).json()
    assert len(insp["checklist"]) > 5 and insp["resultado"]["pendentes"] == len(insp["checklist"])
    ck = insp["checklist"]
    ck[0]["resultado"], ck[1]["resultado"], ck[2]["resultado"] = "ok", "nok", "nok"
    up = api.call("fiscal", "PUT", f"/qse/{insp['item_id']}", json={"checklist": ck}).json()
    assert up["resultado"]["nok"] == 2 and up["resultado"]["conformidade_pct"] == 33.3
    g = api.call("fiscal", "POST", f"/qse/{insp['item_id']}/gerar-nc").json()
    assert len(g["criadas"]) == 2
    assert api.call("fiscal", "POST", f"/qse/{insp['item_id']}/gerar-nc").json()["criadas"] == []   # não duplica
    ops = api.raw("GET", f"/api/chantiers/{CID}/gestao/qse-operarios").json()["itens"]
    assert len(ops) == 1
    q = api.raw("POST", f"/api/chantiers/{CID}/gestao/qse-operarios/n1", json={"tipo": "quase_acidente", "gravidade": "alta"})
    assert q.status_code == 201
    assert api.raw("GET", f"/api/chantiers/{CID}/gestao/qse-operarios").json()["itens"] == []
    pdf = api.call("dono", "GET", "/qse/registo.pdf")
    assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF")


def test_api_rfi_visibilidade_e_resposta(api):
    r = api.call("empA", "POST", "/rfi", json={"assunto": "Cota da soleira", "pergunta": "Qual a cota da soleira da porta P3?",
                                               "destinatario_perfil": "arquiteto", "prazo": "2026-11-20", "visibilidade": "restrito"}).json()
    assert r["numero"] == "PE-001" and r["em_atraso"]
    assert api.call("empB", "GET", f"/rfi/{r['rfi_id']}").status_code == 404           # restrito: outra empresa não vê
    assert api.call("empB", "POST", f"/rfi/{r['rfi_id']}/respostas", json={"texto": "x"}).status_code == 404
    assert api.call("dono", "POST", f"/rfi/{r['rfi_id']}/respostas", json={"texto": "x"}).status_code == 404   # não é destinatário
    resp = api.call("arq", "POST", f"/rfi/{r['rfi_id']}/respostas", json={"texto": "Cota +0,15 m (planta A-02 rev. C)."})
    assert resp.status_code == 201 and resp.json()["estado"] == "respondido"
    pub = api.call("owner", "POST", "/rfi", json={"assunto": "Horário de betonagem", "pergunta": "Pode começar às 7h?"}).json()
    assert pub["numero"] == "PE-002"
    assert {x["numero"] for x in api.call("empB", "GET", "/rfi").json()["itens"]} == {"PE-002"}
    assert api.call("empB", "POST", f"/rfi/{pub['rfi_id']}/fechar").status_code == 403
    assert api.call("owner", "POST", f"/rfi/{pub['rfi_id']}/fechar").json()["estado"] == "fechado"
    an = api.call("empA", "POST", f"/rfi/{r['rfi_id']}/anexos", files={"file": ("p.png", png(), "image/png")})
    assert an.status_code == 201 and api.call("arq", "GET", f"/rfi/{r['rfi_id']}/anexos/0").status_code == 200


def test_api_stock_rececao_e_saida(api):
    enc = api.call("owner", "GET", "/stock/encomendas").json()["itens"]
    assert enc[0]["linhas"][0]["em_falta"] == 40
    assert api.call("owner", "POST", "/stock/rececao/o1", json={"linhas": [{"linha": 0, "quantidade": 50}]}).status_code == 400
    rec = api.call("owner", "POST", "/stock/rececao/o1", json={"linhas": [{"linha": 0, "quantidade": 30}], "guia_remessa": "GR 123"}).json()
    assert rec["estado_entrega"] == "partial" and rec["saldos"][0]["saldo"] == 30
    assert api.call("owner", "POST", "/stock/movimentos", json={"tipo": "saida", "material": "Cimento CEM II", "unidade": "saco",
                                                               "quantidade": 31}).status_code == 409
    assert api.call("owner", "POST", "/stock/movimentos", json={"tipo": "saida", "material": "cimento cem ii", "unidade": "saco",
                                                               "quantidade": 25}).status_code == 201
    api.call("owner", "PUT", "/stock/minimos", json={"chave": "cimento cem ii|saco", "minimo": 10})
    st = api.call("owner", "GET", "/stock").json()
    assert st["saldos"][0]["saldo"] == 5 and st["saldos"][0]["abaixo_minimo"]
    assert api.call("empA", "GET", "/stock").status_code == 404                        # stock: só o titular
    assert any(e == "stock.rececao" for _, e, _ in api.sent)


def test_api_curva_e_alertas_sem_custos_para_o_dono(api):
    run(api.db.chantier_plannings.insert_one({"chantier_id": CID, "user_id": "u_owner", "start_date": "2026-11-02",
                                              "tasks": [{"id": "t1", "name": "Estrutura", "resource": "Estrutura", "duration": 10, "progress": 60},
                                                        {"id": "t2", "name": "Redes", "resource": "Redes", "duration": 5, "progress": 0,
                                                         "predecessors": [{"id": "t1"}]}]}))
    c = api.call("owner", "GET", "/curva-s").json()
    assert c["disponivel"] and c["pontos"] and "orcamento_custo" in c
    d = api.call("dono", "GET", "/curva-s").json()
    assert d["disponivel"] and "orcamento_custo" not in d and all("custo_real" not in p for p in d["pontos"])
    assert run(api.db.obra_avanco_snapshots.count_documents({"chantier_id": CID})) == 1
    assert api.call("empA", "GET", "/curva-s").status_code == 403
    assert isinstance(api.call("fiscal", "GET", "/alertas").json()["itens"], list)


def test_api_copiloto_sem_ia_devolve_resumo_calculado(api, monkeypatch):
    import sys
    import types
    import engines

    async def boom(*a, **k):
        raise RuntimeError("sem IA")
    fake = types.ModuleType("engines.ai")     # simula a queda de todos os fornecedores de IA
    fake._complete = boom
    fake._json = lambda raw, fb: fb
    monkeypatch.setitem(sys.modules, "engines.ai", fake)
    monkeypatch.setattr(engines, "ai", fake, raising=False)
    r = api.call("owner", "POST", "/copiloto/pergunta", json={"pergunta": "O que está atrasado?"}).json()
    assert r["fonte"] == "calculo" and "Semana" in r["resposta"]
    s = api.call("owner", "POST", "/copiloto/resumo").json()
    assert s["fonte"] == "calculo"
    pdf = api.call("owner", "GET", "/relatorio-semanal.pdf")
    assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF")


def test_api_webhooks(api):
    assert api.raw("POST", "/api/webhooks-saida", json={"url": "https://10.0.0.1/x", "eventos": ["qse.criado"]}).status_code == 400
    h = api.raw("POST", "/api/webhooks-saida", json={"url": "https://erp.exemplo.pt/cp", "eventos": ["qse.criado", "inexistente"]}).json()
    assert h["eventos"] == ["qse.criado"] and h["segredo"].startswith("whsec_")
    lst = api.raw("GET", "/api/webhooks-saida").json()["itens"]
    assert "segredo" not in lst[0] and lst[0]["segredo_fim"] == h["segredo"][-4:]
    assert api.raw("DELETE", f"/api/webhooks-saida/{h['hook_id']}").json()["ok"]


def test_enviar_webhook_assinado():
    capt = {}

    class FakeClient:
        async def post(self, url, content, headers):
            capt.update(url=url, content=content, headers=headers)

            class R:
                status_code = 204
            return R()

    async def go():
        import socket
        loop = asyncio.get_running_loop()

        async def fake_gai(host, port, type=0):
            return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", port))]
        loop.getaddrinfo = fake_gai
        return await wh.enviar({"url": "https://erp.exemplo.pt/cp", "segredo": "abc"}, "qse.criado", {"n": 1}, client=FakeClient())
    res = run(go())
    assert res["ok"] and capt["headers"]["X-ConstruPilot-Signature"] == wh.assinatura("abc", capt["content"])


def test_api_fotos_dos_operarios_no_diario(api):
    from engines import storage
    storage.put_object("cp/hr/u_owner/w1/f.png", png(), "image/png")
    run(api.db.hr_files.insert_one({"storage_path": "cp/hr/u_owner/w1/f.png", "content_type": "image/png", "employer_id": "u_owner",
                                    "worker_id": "w1", "is_deleted": False}))
    run(api.db.hr_photos.insert_one({"photo_id": "ph1", "employer_id": "u_owner", "worker_id": "w1", "worker_name": "Rui",
                                     "project_id": "prj1", "path": "cp/hr/u_owner/w1/f.png", "caption": "Cofragem",
                                     "created_at": "2026-11-24T11:00:00"}))
    run(api.db.hr_photos.insert_one({"photo_id": "ph_outra", "employer_id": "outro", "worker_id": "x", "project_id": "prjX",
                                     "path": "cp/hr/outro/x.png", "created_at": "2026-11-24T11:00:00"}))
    prep = api.call("owner", "GET", "/diario/preparar", params={"data": "2026-11-24"}).json()
    assert [f["photo_id"] for f in prep["operarios"]["fotos"]] == ["ph1"]
    d = api.call("owner", "POST", "/diario", json={"data": "2026-11-24", "fotos_operarios": ["ph1", "ph_outra"]}).json()
    assert len(d["fotos"]) == 1 and d["fotos"][0]["origem"] == "operario"          # a foto de outra empresa é ignorada
    r = api.call("owner", "GET", f"/diario/{d['diario_id']}/fotos/0")
    assert r.status_code == 200 and r.headers["content-type"].startswith("image/png")


def test_api_planeamento_nao_partilhado_e_quota_ia(api, monkeypatch):
    run(api.db.chantier_plannings.insert_one({"chantier_id": CID, "user_id": "u_owner", "start_date": "2026-11-02", "client_visible": False,
                                              "tasks": [{"id": "t1", "name": "Estrutura", "resource": "Estrutura", "duration": 5, "progress": 10}]}))
    assert api.call("owner", "GET", "/curva-s").json()["disponivel"]
    dono = api.call("dono", "GET", "/curva-s").json()
    assert not dono["disponivel"] and "pontos" not in dono
    assert all(a["tipo"] not in ("tarefa_atraso", "tarefa_critica") for a in api.call("fiscal", "GET", "/alertas").json()["itens"])
    from routes import obra_gestao
    monkeypatch.setitem(obra_gestao.IA_LIMITES, "copiloto", 1)
    import sys
    import types
    fake = types.ModuleType("engines.ai")

    async def ok(*a, **k):
        return "Resposta."
    fake._complete = ok
    fake._json = lambda raw, fb: fb
    monkeypatch.setitem(sys.modules, "engines.ai", fake)
    import engines
    monkeypatch.setattr(engines, "ai", fake, raising=False)
    assert api.call("owner", "POST", "/copiloto/pergunta", json={"pergunta": "Ponto da situação?"}).json()["resposta"] == "Resposta."
    assert api.call("owner", "POST", "/copiloto/pergunta", json={"pergunta": "Outra vez?"}).status_code == 429
    qse = api.call("empA", "POST", "/qse", json={"tipo": "quase_acidente", "titulo": "Escada sem guarda"}).json()
    api.call("empA", "POST", f"/qse/{qse['item_id']}/fotos", files={"file": ("f.png", png(), "image/png")})
    assert api.call("empA", "POST", f"/qse/{qse['item_id']}/analisar-foto/0").status_code == 403   # IA só para a gestão
