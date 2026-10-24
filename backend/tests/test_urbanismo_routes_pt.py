"""Rotas /urbanismo e /publico/urbanismo-validacao (.pt) — sem Mongo real, sem rede, sem IA (coleções em memória)."""
import asyncio
import io
import os
import zipfile

import pytest

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "test_urbanismo")
os.environ.setdefault("JWT_SECRET", "test")

M = pytest.importorskip("routes.urbanismo")
from fastapi import HTTPException, UploadFile  # noqa: E402
from starlette.datastructures import Headers  # noqa: E402


class _Cur:
    def __init__(self, docs):
        self.docs = docs

    def sort(self, key, direction=1):
        self.docs.sort(key=lambda d: d.get(key) or "", reverse=direction == -1)
        return self

    async def to_list(self, n):
        return self.docs[:n]


class _Coll:
    def __init__(self):
        self.docs = []

    @staticmethod
    def _match(d, q):
        return all(d.get(k) == v for k, v in q.items())

    async def insert_one(self, d):
        self.docs.append(dict(d))

    async def find_one(self, q, proj=None, **kw):
        d = next((d for d in self.docs if self._match(d, q)), None)
        return dict(d) if d else None

    def find(self, q, proj=None):
        return _Cur([dict(d) for d in self.docs if self._match(d, q)])

    async def update_one(self, q, upd, **kw):
        for d in self.docs:
            if self._match(d, q):
                assert not any("." in k for k in (upd.get("$set") or {})), "chaves com ponto não suportadas"
                d.update(upd.get("$set") or {})
                return

    async def delete_one(self, q):
        self.docs = [d for d in self.docs if not self._match(d, q)]

    async def delete_many(self, q):
        self.docs = [d for d in self.docs if not self._match(d, q)]


class _DB:
    def __init__(self):
        self.urbanismo_processos, self.urbanismo_validacoes, self.users = _Coll(), _Coll(), _Coll()


@pytest.fixture
def env(monkeypatch):
    db = _DB()
    store = {}
    monkeypatch.setattr(M, "db", db)
    monkeypatch.setattr(M.obj, "put_object", lambda path, data, ct: store.__setitem__(path, (data, ct)) or {"path": path})
    monkeypatch.setattr(M.obj, "get_object", lambda path: store[path])
    sent = []

    async def fake_send(to, subject, html, **kw):
        sent.append((to, subject))
        return {"ok": True}

    import engines.emailer as em
    monkeypatch.setattr(em, "send_email", fake_send)
    return db, store, sent


def _run(c):
    return asyncio.run(c)


U = {"user_id": "u1", "email": "pro@exemplo.pt"}


def test_fluxo_completo(env):
    db, store, sent = env
    p = _run(M.criar(M.ProcessoIn(title="Moradia teste", tipo_obra="moradia_nova",
                                  terreno=M.TerrenoIn(concelho="Concelho Exemplo", area_terreno_m2=300)), U))
    pid = p["processo_id"]
    assert p["verificacao"]["quadro"] is None and p["checklist"]["procedimento"] == "licenciamento"
    with pytest.raises(HTTPException) as e:
        _run(M.desenho_png(pid, "corte", U))
    assert e.value.status_code == 422 and "volumes" in e.value.detail

    out = _run(M.gravar_volume(pid, M.VolumeIn(levels=2, storey_h_m=2.8, n_fogos=1, lugares_previstos=1), U))
    assert out["volume"]["total_h_m"] == 7.6
    assert out["verificacao"]["quadro"]["area_construcao_m2"] == 96
    out = _run(M.atualizar(pid, M.ProcessoPatch(pdm=M.PdmIn(io_max_pct=15, lugares_por_fogo=2)), U))
    res = {i["codigo"]: i["resultado"] for i in out["verificacao"]["verificacoes"]}
    assert res["PDM_IO"] == "nao_conforme" and res["PDM_ESTACIONAMENTO"] == "nao_conforme" and res["PDM_IU"] == "sem_dados"

    for nome in ("planta-implantacao", "corte", "alcado", "axonometria"):
        r = _run(M.desenho_png(pid, nome, U))
        assert r.body[:8] == b"\x89PNG\r\n\x1a\n"
    q = _run(M.quadro_pdf(pid, U))
    assert q.body[:4] == b"%PDF" and "Quadro-de-areas" in q.headers["content-disposition"]
    pdp = _run(M.pecas_desenhadas_pdf(pid, U))
    assert pdp.body[:4] == b"%PDF"

    up = UploadFile(io.BytesIO(b"%PDF-1.4 fake"), filename="planta localizacao.pdf", headers=Headers({"content-type": "application/pdf"}))
    _run(M.carregar_peca(pid, "PLANTA_LOCALIZACAO", up, U))
    d = _run(M.obter(pid, U))
    items = {i["code"]: i for i in d["checklist"]["items"]}
    assert items["PLANTA_LOCALIZACAO"]["carregada"] and items["CORTES"]["gerada"]
    assert not items["TERMOS_RESPONSABILIDADE"]["ok"]
    assert d["pecas"][0]["code"] == "PLANTA_LOCALIZACAO" and "storage_path" not in d["pecas"][0]
    with pytest.raises(HTTPException):
        _run(M.carregar_peca(pid, "DESCONHECIDA", up, U))

    z = _run(M.exportar(pid, U))
    names = zipfile.ZipFile(io.BytesIO(z.body)).namelist()
    assert "pecas/10_PLANTA_LOCALIZACAO.pdf" in names and "00_quadro_areas_verificacao.pdf" in names
    assert db.urbanismo_processos.docs[0]["status"] == "exportado"

    lst = _run(M.listar(U))["processos"]
    assert lst[0]["procedimento_label"] == "Licença (licenciamento)"
    assert _run(M.eliminar(pid, U))["ok"] and not db.urbanismo_processos.docs


def test_isolamento_entre_utilizadores(env):
    p = _run(M.criar(M.ProcessoIn(title="Privado"), U))
    with pytest.raises(HTTPException) as e:
        _run(M.obter(p["processo_id"], {"user_id": "outro"}))
    assert e.value.status_code == 404 and e.value.detail == "Processo não encontrado."


def test_exemplo_offline_e_volume_recusado_para_muro(env):
    ex = _run(M.criar_exemplo(U))
    assert ex["title"].endswith("(exemplo fictício)") and ex["verificacao"]["resumo"]["nao_conforme"] == 0
    mu = _run(M.criar(M.ProcessoIn(title="Muro", tipo_obra="muro",
                                   parametros={"altura_m": 1.6, "implantacao": "laterais", "material": "xpto", "lixo": 1}), U))
    assert mu["parametros"] == {"altura_m": 1.6, "implantacao": "laterais"}     # chaves desconhecidas descartadas
    assert mu["verificacao"]["rjue"]["procedimento"] == "isento"
    with pytest.raises(HTTPException) as e:
        _run(M.gravar_volume(mu["processo_id"], M.VolumeIn(), U))
    assert e.value.status_code == 422
    r = _run(M.desenho_png(mu["processo_id"], "alcado", U))
    assert r.body[:8] == b"\x89PNG\r\n\x1a\n"
    with pytest.raises(HTTPException):
        _run(M.desenho_png(mu["processo_id"], "axonometria", U))


def test_volume_altura_incoerente(env):
    p = _run(M.criar(M.ProcessoIn(title="Moradia"), U))
    with pytest.raises(HTTPException) as e:
        _run(M.gravar_volume(p["processo_id"], M.VolumeIn(levels=2, storey_h_m=3, total_h_m=5), U))
    assert e.value.status_code == 422 and "altura total" in e.value.detail


def test_verificar_sem_gravar(env):
    v = _run(M.verificar_sem_gravar(M.ProcessoIn(title="Pré-visualização", volume=M.VolumeIn(), pdm=M.PdmIn(n_pisos_max=1)), U))
    assert v["quadro"]["n_pisos"] == 1 and v["country"] == "PT"


def test_memoria_texto_neutro_sem_ia(env, monkeypatch):
    monkeypatch.delenv("EMERGENT_LLM_KEY", raising=False)
    p = _run(M.criar_exemplo(U))
    out = _run(M.gerar_memoria(p["processo_id"], U))
    assert "memória descritiva" in out["memoria_texto"].lower()
    edit = _run(M.atualizar(p["processo_id"], M.ProcessoPatch(memoria_texto="1. Identificação\nTexto revisto."), U))
    assert edit["memoria_texto"].startswith("1. Identificação")


def test_validacao_por_tecnico(env):
    db, store, sent = env
    p = _run(M.criar_exemplo(U))
    pid = p["processo_id"]
    r = _run(M.pedir_validacao(pid, M.ValidacaoIn(tecnico_nome="Eng.ª Exemplo", tecnico_email="tecnica@exemplo.pt"), U))
    assert r["email_sent"] and sent[0][0] == "tecnica@exemplo.pt"
    token = r["share_url"].rsplit("/", 1)[-1]
    assert r["share_url"] == f"/urbanismo/validacao/{token}"
    pub = _run(M.ver_validacao(token))
    assert pub["status"] == "pendente" and pub["procedimento_label"] == "Licença (licenciamento)" and pub["quadro"]
    zz = _run(M.exportar_validacao(token))
    assert zz.body[:2] == b"PK"
    with pytest.raises(HTTPException) as e:
        _run(M.assinar_validacao(token, M.AssinarIn(signatario="Eng.ª Exemplo", decisao="reservas")))
    assert e.value.status_code == 422
    ok = _run(M.assinar_validacao(token, M.AssinarIn(signatario="Eng.ª Exemplo", ordem="OE", numero_inscricao="00000",
                                                     decisao="validar", comentario="Sem reservas.")))
    assert ok["status"] == "validado"
    with pytest.raises(HTTPException) as e:
        _run(M.assinar_validacao(token, M.AssinarIn(signatario="Outro", decisao="validar")))
    assert e.value.status_code == 409
    d = _run(M.obter(pid, U))
    assert d["validacao"]["status"] == "validado" and d["validacao"]["numero_inscricao"] == "00000"
    assert "token" not in d["validacao"]
    with pytest.raises(HTTPException) as e:
        _run(M.ver_validacao("token-invalido"))
    assert e.value.status_code == 404


def test_config_pt(env):
    c = _run(M.config(U))
    assert c["tipos_obra"]["muro"].startswith("Muro") and c["pagina_rjue"] == "/particulares/autorizacao-obras"
    assert any(f["key"] == "io_max_pct" for f in c["pdm_campos"])
    assert c["fontes"]["RGEU_65_1"]["status"] == "confirmado"
