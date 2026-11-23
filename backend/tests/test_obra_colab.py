"""Obra colaborativa (assinatura por obra) : matriz de acessos, visto, subempreiteiros, autos, planeamento, atas.

Execução isolada: MongoDB simulada (mongomock_motor), armazenamento em memória, nenhuma chamada de rede.
"""
import asyncio
import os
from datetime import date, timedelta

import pytest

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "cp_test")
os.environ.setdefault("JWT_SECRET", "test-secret-not-used-in-prod")
os.environ.setdefault("FRONTEND_URL", "https://example.test")

mm = pytest.importorskip("mongomock_motor")

from fastapi import FastAPI, HTTPException, Request  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from engines import obra_colab as oc  # noqa: E402

HOJE = date(2026, 11, 23)
PDF = b"%PDF-1.4\n%demo\n"
CID, REF = "cht_demo", "CP-TEST-0001"
PARTS = {
    "dono": {"role": "client", "colab_role": "dono_obra", "name": "Dono"},
    "fiscal": {"role": "client", "colab_role": "fiscalizacao", "name": "Fiscal"},
    "arq": {"role": "client", "colab_role": "arquiteto", "name": "Arquiteta"},
    "empA": {"role": "subcontractor", "name": "Empresa A", "lot": "Estrutura"},      # perfil herdado do portal
    "empB": {"role": "subcontractor", "colab_role": "empresa", "name": "Empresa B", "lot": "Canalização"},
    "outra": {"role": "subcontractor", "name": "Empresa de outra obra"},
}


def run(c):
    return asyncio.run(c)


# ====================================================================== regras puras
def test_matriz_empresa_so_consulta_ou_carrega_planos():
    assert oc.can(oc.EMPRESA, "planos.ver") and oc.can(oc.EMPRESA, "planos.carregar")
    for cap in ("planos.modificar", "planos.anotar", "planos.visto", "subs.decidir", "autos.validar_fiscal",
                "autos.validar_dono", "atas.editar", "cronograma.registar_avanco", "contratos.gerir"):
        assert not oc.can(oc.EMPRESA, cap), cap


def test_matriz_visto_so_fiscalizacao_e_arquiteto():
    assert {r for r in (*oc.ROLES, oc.GESTOR) if oc.can(r, "planos.visto")} == {oc.FISCAL, oc.ARQUITETO}
    assert {r for r in (*oc.ROLES, oc.GESTOR) if oc.can(r, "subs.decidir")} == {oc.DONO}
    assert not oc.can(oc.ARQUITETO, "autos.ver") and not oc.can(oc.ARQUITETO, "subs.ver")


def test_filtro_empresa_nunca_fica_vazio():
    assert oc.scope_filter(oc.EMPRESA, "autos", None) == {"empresa_id": "__nenhuma__"}
    assert oc.scope_filter(oc.EMPRESA, "autos", "p1") == {"empresa_id": "p1"}
    assert oc.scope_filter(oc.FISCAL, "autos", None) is None
    assert oc.scope_filter(oc.EMPRESA, "planos", "p1") is None
    assert not oc.may_see_record(oc.EMPRESA, "autos", "p1", {"empresa_id": "p2"})


def _docs(**over):
    base = {i["key"]: {"key": i["key"], "validade": (HOJE + timedelta(days=200)).isoformat()} for i in oc.DEFAULT_REGULAMENTO}
    base.update(over)
    return [d for d in base.values() if d]


def test_sub_conforme():
    r = oc.check_sub_request({"documentos": _docs(), "valor": 1000}, oc.DEFAULT_REGULAMENTO, hoje=HOJE)
    assert r["conforme"] and r["sugestao"] == "aprovar" and not r["motivos"]


def test_sub_em_falta_expirado_e_sem_validade():
    docs = _docs(seguro_rc=None,
                 nao_divida_at={"key": "nao_divida_at", "validade": (HOJE - timedelta(days=3)).isoformat()},
                 seguro_at={"key": "seguro_at", "validade": ""},
                 alvara_impic={"key": "alvara_impic", "validade": (HOJE + timedelta(days=10)).isoformat()},
                 aptidao_medica=None)
    r = oc.check_sub_request({"documentos": docs}, oc.DEFAULT_REGULAMENTO, hoje=HOJE)
    estados = {p["key"]: p["estado"] for p in r["pontos"]}
    assert estados["seguro_rc"] == "em_falta"
    assert estados["nao_divida_at"] == "expirado"
    assert estados["seguro_at"] == "sem_validade"
    assert estados["alvara_impic"] == "a_expirar"            # avisa, não bloqueia
    assert estados["aptidao_medica"] == "opcional_em_falta"  # opcional, não bloqueia
    assert not r["conforme"] and len(r["motivos"]) == 3


def test_sub_limite_de_subcontratacao():
    r = oc.check_sub_request({"documentos": _docs(), "valor": 40000}, oc.DEFAULT_REGULAMENTO, hoje=HOJE,
                             valor_contrato_empresa=100000, limite_subcontratacao_pct=30)
    assert not r["conforme"] and any("40.0 %" in m for m in r["motivos"])
    r = oc.check_sub_request({"documentos": _docs(), "valor": 30000}, oc.DEFAULT_REGULAMENTO, hoje=HOJE,
                             valor_contrato_empresa=100000, limite_subcontratacao_pct=30)
    assert r["conforme"]


def test_decisao_de_sub_exige_justificacao():
    assert oc.validate_sub_decision("aprovado", "", "") is None
    assert oc.validate_sub_decision("aprovado_com_reservas", " ", "")
    assert oc.validate_sub_decision("recusado", "", "")
    assert oc.validate_sub_decision("recusado", "", "seguro expirado") is None
    assert oc.validate_sub_decision("talvez", "", "")


CONTRATO = {"linhas": [
    {"ref": "1.1", "designacao": "Betão C25/30 em fundações", "unidade": "m³", "quantidade": 100, "preco_unitario": 120.0},
    {"ref": "1.2", "designacao": "Aço A500 NR", "unidade": "kg", "quantidade": 8000, "preco_unitario": 1.35},
    {"ref": "2.1", "designacao": "Cofragem", "unidade": "m²", "quantidade": 400, "preco_unitario": 22.5},
]}  # total = 12000 + 10800 + 9000 = 31800


def test_auto_conforme_e_totais_exatos():
    auto = {"numero": 1, "periodo": "2026-10", "total_declarado": 6000 + 2700 + 2250,
            "linhas": [{"ref": "1.1", "quantidade_periodo": 50}, {"ref": "1.2", "quantidade_periodo": 2000},
                       {"ref": "2.1", "quantidade_periodo": 100, "valor": 2250.0}]}
    r = oc.check_auto(auto, CONTRATO, [], avanco_registado_pct=35)
    assert r["total_periodo"] == 10950.0 and r["total_contrato"] == 31800.0
    assert r["pct_financeiro"] == round(100 * 10950 / 31800, 2) == 34.43
    assert r["conforme"] and not r["incoerencias"]


def test_auto_incoerencias_contra_orcamento():
    anteriores = [{"numero": 1, "periodo": "2026-10", "linhas": [{"ref": "1.1", "quantidade_periodo": 80}]}]
    auto = {"numero": 3, "periodo": "2026-10", "total_declarado": 9999,
            "linhas": [{"ref": "1.1", "quantidade_periodo": 30},                       # 80 + 30 > 100
                       {"ref": "1.2", "quantidade_periodo": 100, "preco_unitario": 1.5},   # preço ≠ contrato
                       {"ref": "9.9", "quantidade_periodo": 5, "preco_unitario": 10},      # fora do contrato
                       {"ref": "2.1", "quantidade_periodo": 10, "valor": 300},             # 10 × 22,5 = 225
                       {"ref": "2.1", "quantidade_periodo": 1}]}                           # duplicado
    r = oc.check_auto(auto, CONTRATO, anteriores, avanco_registado_pct=90)
    cods = {i["codigo"] for i in r["incoerencias"]}
    assert {"excede_contrato", "preco_diferente", "fora_contrato", "valor_linha", "linha_duplicada", "total_auto",
            "periodo_repetido", "numeracao"} <= cods
    assert not r["conforme"]
    l11 = next(l for l in r["linhas"] if l["ref"] == "1.1")
    assert l11["quantidade_anterior"] == 80 and l11["quantidade_acumulada"] == 110 and l11["valor_periodo"] == 3600.0


def test_auto_contra_avanco_da_obra():
    auto = {"numero": 1, "periodo": "2026-10", "linhas": [{"ref": "1.1", "quantidade_periodo": 100}]}   # 37,74 % do contrato
    r = oc.check_auto(auto, CONTRATO, [], avanco_registado_pct=20, tolerancia_avanco_pct=5)
    assert any(i["codigo"] == "avanco" and i["gravidade"] == "bloqueante" for i in r["incoerencias"])
    r = oc.check_auto(auto, CONTRATO, [], avanco_registado_pct=35, tolerancia_avanco_pct=5)
    assert r["conforme"]
    r = oc.check_auto(auto, CONTRATO, [], avanco_registado_pct=None)
    assert r["conforme"] and any(i["codigo"] == "sem_avanco" and i["gravidade"] == "aviso" for i in r["incoerencias"])


def test_circuito_de_validacao_do_auto():
    assert oc.next_auto_state("submetido", oc.DONO, True) is None            # o dono não passa à frente da fiscalização
    assert oc.next_auto_state("submetido", oc.FISCAL, True) == "validado_fiscalizacao"
    assert oc.next_auto_state("submetido", oc.FISCAL, False) == "rejeitado_fiscalizacao"
    assert oc.next_auto_state("validado_fiscalizacao", oc.DONO, True) == "validado"
    assert oc.next_auto_state("validado_fiscalizacao", oc.FISCAL, True) is None
    assert oc.next_auto_state("validado", oc.DONO, False) is None
    assert oc.next_auto_state("submetido", oc.EMPRESA, True) is None


def test_cronograma_atraso():
    tarefas = [{"titulo": "Fundações", "inicio": "2026-10-01", "fim": "2026-10-31", "avanco_pct": 80},
               {"titulo": "Pilares", "inicio": "2026-11-01", "fim": "2026-12-31", "avanco_pct": 40},
               {"titulo": "Lajes", "inicio": "2027-01-01", "fim": "2027-01-31", "avanco_pct": 0}]
    s = oc.cronograma_summary(tarefas, HOJE)
    assert [t["em_atraso"] for t in s["tarefas"]] == [True, False, False]
    assert s["tarefas"][0]["atraso_dias"] == 23 and s["em_atraso"] == 1


def test_rascunho_da_ata_e_separacao_por_empresa():
    anterior = {"numero": 3, "linhas": [{"empresa_id": "A", "ponto": "Entregar plano de cofragem", "ata_origem": 2, "estado": "importante"},
                                        {"empresa_id": "B", "ponto": "Fechado", "ata_origem": 3, "fechado": True}]}
    cron = {"A": {"tarefas": [{"titulo": "Fundações", "em_atraso": True, "atraso_dias": 5, "avanco_pct": 80}]}}
    linhas = oc.draft_ata(4, anterior, [{"empresa_id": "A"}, {"empresa_id": "B"}], cron, {"B": ["Rede de esgotos"]}, {"A": 2})
    assert linhas[0]["ata_origem"] == 2 and linhas[0]["fonte"] == "ata_anterior"       # conserva a ata de origem
    assert not any(l["ponto"] == "Fechado" for l in linhas)
    assert {l["fonte"] for l in linhas} == {"ata_anterior", "cronograma", "caixa_planos", "autos"}
    ata = {"numero": 4, "linhas": linhas + [{"empresa_id": None, "ponto": "Próxima reunião dia 30"}]}
    vista_b = oc.ata_for_role(ata, oc.EMPRESA, "B")["linhas"]
    assert all(l["empresa_id"] in (None, "B") for l in vista_b) and len(vista_b) == 2
    assert len(oc.ata_for_role(ata, oc.FISCAL, None)["linhas"]) == len(ata["linhas"])


# ====================================================================== API
@pytest.fixture()
def api(monkeypatch):
    db = mm.AsyncMongoMockClient()["t_colab"]
    from engines import storage
    from routes import chantiers, obra_colab, portal
    for mod in (chantiers, obra_colab, portal):
        monkeypatch.setattr(mod, "db", db)
    blobs: dict[str, tuple[bytes, str]] = {}
    monkeypatch.setattr(storage, "put_object", lambda path, data, ct: blobs.__setitem__(path, (data, ct)) or {"path": path})
    monkeypatch.setattr(storage, "get_object", lambda path: blobs[path])
    monkeypatch.setattr(obra_colab, "_today", lambda: HOJE)

    async def seed():
        await db.chantiers.insert_one({"chantier_id": CID, "user_id": "u_owner", "name": "Moradia Demo", "ref": REF})
        await db.chantiers.insert_one({"chantier_id": "cht_outra", "user_id": "u_owner", "name": "Outra", "ref": "CP-OUTR-0002"})
        for key, p in PARTS.items():
            outra = key == "outra"
            await db.chantier_participants.insert_one({"participant_id": key, "chantier_id": "cht_outra" if outra else CID,
                                                       "chantier_ref": "CP-OUTR-0002" if outra else REF,
                                                       "owner_user_id": "u_owner", "email": f"{key}@example.com",
                                                       "status": "active", "session_version": 0, "lot": "", **p})
    run(seed())

    async def fake_user(request: Request):
        uid = request.headers.get("X-User")
        if not uid:
            raise HTTPException(401, "Não autenticado")
        return {"user_id": uid, "name": "Titular", "role": "user"}

    async def fake_participant(request: Request):
        pid = request.headers.get("X-Part")
        p = await db.chantier_participants.find_one({"participant_id": pid}, {"_id": 0})
        if not p:
            raise HTTPException(401, "Sessão de convidado necessária")
        return p

    from core import security
    app = FastAPI()
    app.include_router(obra_colab.pro_router, prefix="/api")
    app.include_router(obra_colab.portal_router, prefix="/api")
    app.dependency_overrides[security.current_user] = fake_user
    app.dependency_overrides[security.pro_required] = fake_user
    app.dependency_overrides[portal.current_participant] = fake_participant
    client = TestClient(app)

    class Api:
        def __init__(self):
            self.db = db

        def call(self, who, method, path, **kw):
            if who == "owner":
                return client.request(method, f"/api/chantiers/{CID}/colab{path}", headers={"X-User": "u_owner"}, **kw)
            return client.request(method, f"/api/portal/{REF}/colab{path}", headers={"X-Part": who}, **kw)

        def raw(self, method, url, **kw):
            return client.request(method, url, **kw)

    return Api()


def _upload(api, who, titulo="Planta de fundações", tipo="execucao"):
    return api.call(who, "POST", "/planos", files={"file": ("planta.pdf", PDF, "application/pdf")},
                    data={"titulo": titulo, "tipo": tipo, "especialidade": "Estrutura"})


def test_api_perfis_e_capacidades(api):
    eu = api.call("empA", "GET", "").json()
    assert eu["eu"]["perfil"] == "empresa" and eu["eu"]["empresa_id"] == "empA"      # perfil herdado do convite «subcontractor»
    assert eu["capacidades"]["planos.carregar"] and not eu["capacidades"]["planos.anotar"]
    assert "email" not in eu["intervenientes"][0] and eu["definicoes"] is None      # e-mails só para o gestor
    assert api.call("fiscal", "GET", "").json()["eu"]["perfil"] == "fiscalizacao"
    dono = api.call("owner", "GET", "").json()
    assert dono["eu"]["gestor"] and "email" in dono["intervenientes"][0]
    assert len(dono["intervenientes"]) == 5                                          # a «outra» obra não aparece


def test_api_sessao_de_outra_obra_e_recusada(api):
    assert api.raw("GET", f"/api/portal/{REF}/colab", headers={"X-Part": "outra"}).status_code == 403
    assert api.raw("GET", f"/api/portal/{REF}/colab/autos", headers={"X-Part": "outra"}).status_code == 403
    assert api.raw("GET", f"/api/chantiers/{CID}/colab", headers={"X-User": "u_intruso"}).status_code == 404
    assert api.raw("GET", f"/api/chantiers/{CID}/colab").status_code == 401


def test_api_caixa_de_planos_e_visto(api):
    r = _upload(api, "empA")
    assert r.status_code == 201, r.text
    pid = r.json()["plano_id"]
    assert r.json()["visto_estado"] == "pendente" and r.json()["empresa_id"] == "empA"
    # todas as empresas consultam a caixa de planos
    assert [p["plano_id"] for p in api.call("empB", "GET", "/planos").json()["planos"]] == [pid]
    assert api.call("empB", "GET", f"/planos/{pid}/ficheiro").content == PDF
    # empresa: só consulta ou carrega
    assert api.call("empA", "POST", f"/planos/{pid}/anotacoes", json={"texto": "x"}).status_code == 403
    assert api.call("empA", "PUT", f"/planos/{pid}", json={"titulo": "y"}).status_code == 403
    assert api.call("empA", "DELETE", f"/planos/{pid}").status_code == 403
    assert api.call("empA", "POST", f"/planos/{pid}/visto", json={"decisao": "visto"}).status_code == 403
    assert api.call("empB", "POST", f"/planos/{pid}/versoes", files={"file": ("b.pdf", PDF, "application/pdf")}).status_code == 403
    # visto: fiscalização ou arquiteto — não o dono de obra nem o gestor
    assert api.call("dono", "POST", f"/planos/{pid}/visto", json={"decisao": "visto"}).status_code == 403
    assert api.call("owner", "POST", f"/planos/{pid}/visto", json={"decisao": "visto"}).status_code == 403
    assert api.call("fiscal", "POST", f"/planos/{pid}/visto", json={"decisao": "recusado"}).status_code == 400   # sem observações
    v = api.call("arq", "POST", f"/planos/{pid}/visto", json={"decisao": "visto_com_observacoes", "observacoes": "Cotar o eixo 3"})
    assert v.status_code == 200 and v.json()["visto_estado"] == "visto_com_observacoes" and v.json()["vistos"][0]["versao"] == 1
    assert api.call("dono", "POST", f"/planos/{pid}/anotacoes", json={"texto": "Confirmar com o projetista"}).status_code == 200
    # nova versão pelo autor: o visto volta a pendente
    n = api.call("empA", "POST", f"/planos/{pid}/versoes", files={"file": ("v2.pdf", PDF + b"2", "application/pdf")})
    assert n.status_code == 200 and n.json()["versao_atual"] == 2 and n.json()["visto_estado"] == "pendente"
    assert api.call("fiscal", "GET", f"/planos/{pid}/ficheiro", params={"versao": 1}).content == PDF
    # o visto só existe para planos de execução
    arq = _upload(api, "arq", "Planta de arquitetura", "arquitetura").json()
    assert arq["visto_estado"] == "nao_aplicavel"
    assert api.call("fiscal", "POST", f"/planos/{arq['plano_id']}/visto", json={"decisao": "visto"}).status_code == 400


def test_api_tipo_de_ficheiro_recusado(api):
    r = api.call("empA", "POST", "/planos", files={"file": ("x.exe", b"MZ", "application/x-msdownload")}, data={"tipo": "execucao"})
    assert r.status_code == 400


def _sub_completo(api, who, validade="2027-06-30", skip=()):
    sid = api.call(who, "POST", "/subs", json={"nome": "Cofragens do Norte", "nif": "599999993", "valor": 5000}).json()["sub_id"]
    for item in oc.DEFAULT_REGULAMENTO:
        if item["key"] in skip:
            continue
        r = api.call(who, "POST", f"/subs/{sid}/documentos", files={"file": ("d.pdf", PDF, "application/pdf")},
                     data={"key": item["key"], "validade": validade if item["tem_validade"] else ""})
        assert r.status_code == 200, r.text
    assert api.call(who, "POST", f"/subs/{sid}/submeter").status_code == 200
    return sid


def test_api_aprovacao_de_subempreiteiros(api):
    sid = _sub_completo(api, "empA", skip=("seguro_rc",))
    # separação: a empresa B não vê nem lê o pedido da empresa A
    assert api.call("empB", "GET", "/subs").json()["pedidos"] == []
    assert api.call("empB", "GET", f"/subs/{sid}/documentos/alvara_impic").status_code == 404
    assert api.call("empB", "POST", f"/subs/{sid}/submeter").status_code == 404
    assert api.call("arq", "GET", "/subs").status_code == 403
    # o dono de obra vê logo se cumpre o regulamento
    ped = api.call("dono", "GET", "/subs").json()["pedidos"][0]
    assert not ped["controlo"]["conforme"] and ped["controlo"]["em_falta"] == ["Seguro de responsabilidade civil"]
    # só o dono de obra decide
    for who in ("fiscal", "empA", "owner"):
        assert api.call(who, "POST", f"/subs/{sid}/decisao", json={"decisao": "recusado", "motivos": "x"}).status_code == 403
    assert api.call("dono", "POST", f"/subs/{sid}/decisao", json={"decisao": "aprovado"}).status_code == 409     # não conforme
    assert api.call("dono", "POST", f"/subs/{sid}/decisao", json={"decisao": "aprovado_com_reservas"}).status_code == 400
    r = api.call("dono", "POST", f"/subs/{sid}/decisao", json={"decisao": "aprovado_com_reservas", "reservas": "Seguro RC até 30/11"})
    assert r.status_code == 200 and r.json()["estado"] == "aprovado_com_reservas"
    assert r.json()["decisao"]["controlo_no_momento"]["conforme"] is False        # o controlo fica arquivado com a decisão
    # a empresa completa o que falta, o dono levanta a reserva
    api.call("empA", "POST", f"/subs/{sid}/documentos", files={"file": ("rc.pdf", PDF, "application/pdf")},
             data={"key": "seguro_rc", "validade": "2027-06-30"})
    r = api.call("dono", "POST", f"/subs/{sid}/decisao", json={"decisao": "aprovado"})
    assert r.status_code == 200 and r.json()["estado"] == "aprovado" and r.json()["controlo"]["conforme"]
    assert api.call("dono", "POST", f"/subs/{sid}/decisao", json={"decisao": "recusado", "motivos": "x"}).status_code == 409


def test_api_recusa_e_regulamento_proprio(api):
    # cada promotor tem as suas regras: o dono de obra reduz o regulamento a dois requisitos
    itens = [{"key": "alvara_impic", "label": "Alvará", "obrigatorio": True, "tem_validade": True},
             {"key": "carta_conforto", "label": "Carta de conforto bancária", "obrigatorio": True, "tem_validade": False}]
    assert api.call("empA", "PUT", "/regulamento", json={"itens": itens}).status_code == 403
    assert api.call("dono", "PUT", "/regulamento", json={"itens": itens}).status_code == 200
    sid = api.call("empB", "POST", "/subs", json={"nome": "Sub X", "valor": 100}).json()["sub_id"]
    assert api.call("empB", "POST", f"/subs/{sid}/documentos", files={"file": ("d.pdf", PDF, "application/pdf")},
                    data={"key": "seguro_rc"}).status_code == 400                   # já não consta do regulamento
    # os rascunhos não são visíveis para o dono de obra
    assert api.call("dono", "GET", "/subs").json()["pedidos"] == []
    api.call("empB", "POST", f"/subs/{sid}/submeter")
    assert api.call("dono", "POST", f"/subs/{sid}/decisao", json={"decisao": "recusado"}).status_code == 400
    r = api.call("dono", "POST", f"/subs/{sid}/decisao", json={"decisao": "recusado", "motivos": "Sem alvará nem carta de conforto"})
    assert r.json()["estado"] == "recusado" and len(r.json()["decisao"]["controlo_no_momento"]["motivos"]) == 2


LINHAS = [dict(l) for l in CONTRATO["linhas"]]


def test_api_autos_de_medicao(api):
    auto = {"periodo": "2026-10", "linhas": [{"ref": "1.1", "quantidade_periodo": 50}], "total_declarado": 6000}
    assert api.call("empA", "POST", "/autos", json=auto).status_code == 409                 # sem orçamento contratado
    assert api.call("fiscal", "PUT", "/contratos/empA", json={"linhas": LINHAS}).status_code == 403
    assert api.call("empA", "PUT", "/contratos/empA", json={"linhas": LINHAS}).status_code == 403
    assert api.call("dono", "PUT", "/contratos/xxx", json={"linhas": LINHAS}).status_code == 404
    c = api.call("dono", "PUT", "/contratos/empA", json={"linhas": LINHAS})
    assert c.status_code == 200 and c.json()["total"] == 31800.0
    api.call("owner", "PUT", "/contratos/empB", json={"linhas": LINHAS})
    assert [x["empresa_id"] for x in api.call("empB", "GET", "/contratos").json()["contratos"]] == ["empB"]

    a1 = api.call("empA", "POST", "/autos", json=auto)
    assert a1.status_code == 201 and a1.json()["numero"] == 1 and a1.json()["controlo"]["total_periodo"] == 6000.0
    aid = a1.json()["auto_id"]
    # ponto crítico: uma empresa não vê os autos de outra
    assert api.call("empB", "GET", "/autos").json()["autos"] == []
    assert api.call("empB", "POST", f"/autos/{aid}/decisao", json={"aprovar": True}).status_code == 404
    assert api.call("empB", "GET", f"/autos/{aid}/ficheiro").status_code == 404
    assert api.call("arq", "GET", "/autos").status_code == 403
    assert len(api.call("fiscal", "GET", "/autos").json()["autos"]) == 1
    # ordem: fiscalização, depois dono de obra
    assert api.call("dono", "POST", f"/autos/{aid}/decisao", json={"aprovar": True}).status_code == 403
    assert api.call("empA", "POST", f"/autos/{aid}/decisao", json={"aprovar": True}).status_code == 403
    assert api.call("owner", "POST", f"/autos/{aid}/decisao", json={"aprovar": True}).status_code == 403
    assert api.call("fiscal", "POST", f"/autos/{aid}/decisao", json={"aprovar": False}).status_code == 400    # sem motivo
    assert api.call("fiscal", "POST", f"/autos/{aid}/decisao", json={"aprovar": True}).json()["estado"] == "validado_fiscalizacao"
    assert api.call("fiscal", "POST", f"/autos/{aid}/decisao", json={"aprovar": True}).status_code == 403
    assert api.call("dono", "POST", f"/autos/{aid}/decisao", json={"aprovar": True}).json()["estado"] == "validado"
    # o segundo auto acumula sobre o primeiro e deteta o excesso face ao orçamento
    a2 = api.call("empA", "POST", "/autos", json={"periodo": "2026-11", "linhas": [{"ref": "1.1", "quantidade_periodo": 60}]}).json()
    assert a2["numero"] == 2 and not a2["controlo"]["conforme"]
    assert {i["codigo"] for i in a2["controlo"]["incoerencias"]} >= {"excede_contrato"}
    assert a2["controlo"]["linhas"][0]["quantidade_anterior"] == 50
    r = api.call("fiscal", "POST", f"/autos/{a2['auto_id']}/decisao", json={"aprovar": False, "motivo": "Excede o contrato"})
    assert r.json()["estado"] == "rejeitado_fiscalizacao"
    # um auto rejeitado deixa de contar no acumulado
    a3 = api.call("empA", "POST", "/autos", json={"periodo": "2026-11", "linhas": [{"ref": "1.1", "quantidade_periodo": 40}]}).json()
    assert a3["controlo"]["linhas"][0]["quantidade_acumulada"] == 90
    assert not any(i["gravidade"] == "bloqueante" for i in a3["controlo"]["incoerencias"])
    # com autos, o contrato já não pode ser substituído
    assert api.call("dono", "PUT", "/contratos/empA", json={"linhas": LINHAS}).status_code == 409


def test_api_planeamento_e_avanco(api):
    tarefas = [{"titulo": "Fundações", "inicio": "2026-10-01", "fim": "2026-10-31"},
               {"titulo": "Pilares", "inicio": "2026-11-01", "fim": "2026-12-31"}]
    assert api.call("fiscal", "PUT", "/cronograma", json={"tarefas": tarefas}).status_code == 403     # cada empresa carrega o seu
    c = api.call("empA", "PUT", "/cronograma", json={"tarefas": tarefas})
    # Fundações terminava a 31/10 e está a 0 %; Pilares devia ir a ~37 % e está a 0 %
    assert c.status_code == 200 and c.json()["em_atraso"] == 2
    t1, t2 = (t["tarefa_id"] for t in c.json()["tarefas"])
    assert api.call("empB", "GET", "/cronogramas").json()["cronogramas"] == []
    assert api.call("empA", "POST", "/cronogramas/empA/avanco",
                    json={"data_reuniao": "2026-11-23", "tarefas": [{"tarefa_id": t1, "avanco_pct": 100}]}).status_code == 403
    assert api.call("fiscal", "POST", "/cronogramas/empB/avanco",
                    json={"data_reuniao": "2026-11-23", "tarefas": [{"tarefa_id": t1, "avanco_pct": 100}]}).status_code == 404
    r = api.call("fiscal", "POST", "/cronogramas/empA/avanco", json={"data_reuniao": "2026-11-23", "tarefas": [
        {"tarefa_id": t1, "avanco_pct": 100}, {"tarefa_id": t2, "avanco_pct": 30, "nota": "2 pilares por betonar"}]})
    assert r.status_code == 200 and r.json()["em_atraso"] == 0 and len(r.json()["avancos"]) == 1
    # a empresa atualiza o cronograma sem perder o avanço registado pela fiscalização
    c2 = api.call("empA", "PUT", "/cronograma", json={"tarefas": [{"tarefa_id": t2, "titulo": "Pilares e vigas",
                                                                 "inicio": "2026-11-01", "fim": "2027-01-15"}]}).json()
    assert c2["tarefas"][0]["avanco_pct"] == 30 and c2["tarefas"][0]["tarefa_id"] == t2
    # o avanço registado passa a servir de referência para os autos
    api.call("dono", "PUT", "/contratos/empA", json={"linhas": LINHAS})
    a = api.call("empA", "POST", "/autos", json={"periodo": "2026-11", "linhas": [{"ref": "1.1", "quantidade_periodo": 100},
                                                                               {"ref": "1.2", "quantidade_periodo": 8000}]}).json()
    assert a["controlo"]["avanco_registado_pct"] == 30.0 and a["controlo"]["pct_financeiro"] == 71.7
    assert any(i["codigo"] == "avanco" for i in a["controlo"]["incoerencias"])


def test_api_ata_semanal(api):
    api.call("empA", "PUT", "/cronograma", json={"tarefas": [{"titulo": "Fundações", "inicio": "2026-10-01", "fim": "2026-10-31"}]})
    _upload(api, "empB", "Rede de esgotos")
    assert api.call("dono", "POST", "/atas/rascunho").status_code == 403           # a ata é da fiscalização
    d = api.call("fiscal", "POST", "/atas/rascunho").json()
    assert d["numero"] == 1 and {l["fonte"] for l in d["linhas"]} == {"cronograma", "caixa_planos"}
    linhas = [{k: l[k] for k in ("empresa_id", "ponto", "estado")} for l in d["linhas"]]
    linhas.append({"empresa_id": None, "ponto": "Próxima reunião: 30/11 às 10h", "estado": "memoria"})
    assert api.call("fiscal", "POST", "/atas", json={"data": "2026-11-23", "linhas": [{"empresa_id": "zzz", "ponto": "x"}]}).status_code == 400
    ata = api.call("fiscal", "POST", "/atas", json={"data": "2026-11-23", "presentes": "Todos", "linhas": linhas}).json()
    assert ata["numero"] == 1 and all(l["ata_origem"] == 1 for l in ata["linhas"])
    # não publicada: invisível para os outros
    assert api.call("empA", "GET", "/atas").json()["atas"] == []
    assert api.call("dono", "GET", "/atas").json()["atas"] == []
    assert api.call("fiscal", "POST", f"/atas/{ata['ata_id']}/publicar").status_code == 200
    assert api.call("fiscal", "PUT", f"/atas/{ata['ata_id']}", json={"data": "2026-11-23"}).status_code == 409
    # cada empresa lê os pontos gerais e os seus
    va = api.call("empA", "GET", "/atas").json()["atas"][0]["linhas"]
    vb = api.call("empB", "GET", "/atas").json()["atas"][0]["linhas"]
    assert {l["empresa_nome"] for l in va} == {"Empresa A", "Geral"} and {l["empresa_nome"] for l in vb} == {"Empresa B", "Geral"}
    assert len(api.call("dono", "GET", "/atas").json()["atas"][0]["linhas"]) == 3
    assert next(l for l in va if l["estado"] == "atraso")["estado_label"] == "Atraso"
    # a ata seguinte retoma os pontos em aberto com a ata de origem
    d2 = api.call("fiscal", "POST", "/atas/rascunho").json()
    assert d2["numero"] == 2 and all(l["ata_origem"] == 1 for l in d2["linhas"] if l["fonte"] == "ata_anterior")


def test_api_titular_com_perfil_declarado(api):
    # sem perfil declarado, o titular gere mas não dá visto nem decide
    pid = _upload(api, "empA").json()["plano_id"]
    assert api.call("owner", "POST", f"/planos/{pid}/visto", json={"decisao": "visto"}).status_code == 403
    assert api.call("owner", "PUT", "/definicoes", json={"owner_role": "fiscalizacao", "limite_subcontratacao_pct": 30}).status_code == 200
    assert api.call("owner", "POST", f"/planos/{pid}/visto", json={"decisao": "visto"}).json()["visto_estado"] == "visto"
    o = api.call("owner", "GET", "").json()
    assert o["eu"]["perfil"] == "fiscalizacao" and o["eu"]["gestor"] and o["definicoes"]["limite_subcontratacao_pct"] == 30
    assert api.call("empA", "PUT", "/definicoes", json={}).status_code in (404, 405)       # rota inexistente no portal
    # mudar o perfil de um interveniente
    assert api.call("owner", "PUT", "/intervenientes/arq", json={"perfil": "fiscalizacao"}).status_code == 200
    assert api.call("arq", "GET", "").json()["eu"]["perfil"] == "fiscalizacao"
