"""Fio do projeto: o projeto do Ateliê é a fonte única; cada etapa ligada guarda a geometria em que foi feita;
o dossier final junta medições exatas, imagens e peças desenhadas."""
import asyncio
import copy
import os

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "test_fio_projeto")
os.environ.setdefault("JWT_SECRET", "test-secret")

import pytest

from engines.fio_projeto import servico as S
from engines.fio_projeto import tools as FT

USER = {"user_id": "u_fio"}


# ------------------------------------------------------------------ base de dados mínima (só o que o fio usa)
def _casa(doc, flt):
    return all(doc.get(k) == v for k, v in flt.items())


class _Cur:
    def __init__(self, docs):
        self.docs = docs

    def __aiter__(self):
        self._it = iter(self.docs)
        return self

    async def __anext__(self):
        try:
            return next(self._it)
        except StopIteration:
            raise StopAsyncIteration


class _Res:
    def __init__(self, n):
        self.deleted_count = n


class _Col:
    def __init__(self):
        self.docs = []

    @staticmethod
    def _proj(d, proj):
        d = copy.deepcopy(d)
        for k, v in (proj or {}).items():
            if v == 0:
                d.pop(k, None)
        return d

    async def find_one(self, flt, proj=None):
        for d in self.docs:
            if _casa(d, flt):
                return self._proj(d, proj)
        return None

    def find(self, flt, proj=None):
        return _Cur([self._proj(d, proj) for d in self.docs if _casa(d, flt)])

    async def insert_one(self, doc):
        self.docs.append(copy.deepcopy(doc))

    async def count_documents(self, flt):
        return sum(1 for d in self.docs if _casa(d, flt))

    async def delete_one(self, flt):
        for i, d in enumerate(self.docs):
            if _casa(d, flt):
                del self.docs[i]
                return _Res(1)
        return _Res(0)

    async def update_one(self, flt, upd, upsert=False):
        alvo = next((d for d in self.docs if _casa(d, flt)), None)
        if alvo is None:
            if not upsert:
                return
            alvo = dict(flt)
            alvo.update(upd.get("$setOnInsert") or {})
            self.docs.append(alvo)
        for k, v in (upd.get("$set") or {}).items():
            alvo[k] = v
        for k, cond in (upd.get("$pull") or {}).items():
            alvo[k] = [x for x in alvo.get(k) or [] if not _casa(x, cond)]
        for k, v in (upd.get("$push") or {}).items():
            alvo.setdefault(k, []).append(v)


class _DB(dict):
    def __getitem__(self, k):
        return self.setdefault(k, _Col())


# ------------------------------------------------------------------ projeto real do Ateliê (motor verdadeiro)
def _modelo(largura=10.0):
    from routes import atelier_archi as AA
    base = AA.EP.modelo_vazio()
    tipos = base["tipos_parede"]
    ext = next(k for k, v in tipos.items() if v.get("exterior"))
    L, P = largura, 8.0
    pts = [(0, 0), (L, 0), (L, P), (0, P)]
    paredes = [{"id": f"w{i}", "piso": "p0", "tipo": ext, "a": list(pts[i]), "b": list(pts[(i + 1) % 4])} for i in range(4)]
    return AA.EP.normalizar({**base, "pisos": base["pisos"], "paredes": paredes, "vaos": []})


@pytest.fixture
def projeto(monkeypatch):
    from routes import atelier_archi as AA
    p = {"projet_id": "arch_teste", "user_id": USER["user_id"], "titre": "Casa Teste", "adresse": "Rua do Monte 7",
         "maitre_ouvrage": "Dono", "programme": "T3", "modelo": _modelo(), "updated_at": "2026-11-28T00:00:00Z"}

    async def fake_projet(pid, uid):
        from fastapi import HTTPException
        if pid != p["projet_id"] or uid != p["user_id"]:
            raise HTTPException(404, "x")
        return p
    monkeypatch.setattr(AA, "_projet", fake_projet)
    return p


def run(c):
    return asyncio.run(c)


def _png():
    import fitz
    pix = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 40, 30), 0)
    pix.clear_with(200)
    return pix.tobytes("png")


def test_quantidades_vem_do_motor_do_atelier(projeto):
    from routes import atelier_archi as AA
    est = run(S.estado(_DB(), USER, "arch_teste"))
    der = AA.EP.derivar(AA._modele(projeto))
    assert est["projeto"]["totais"]["area_bruta_construcao_m2"] == der["medicoes"]["totais"]["area_bruta_construcao_m2"] > 0
    assert est["projeto"]["fachada"]["area_bruta_m2"] == der["medicoes"]["fachada"]["area_bruta_m2"]
    assert est["projeto"]["paredes_por_tipo"] and est["projeto"]["paredes_por_tipo"][0]["exterior"] is True
    assert [e["etapa"] for e in est["etapas"]][0] == "desenho" and est["proxima_etapa"] == "bim"


def test_projeto_de_outro_utilizador_recusado(projeto):
    with pytest.raises(S.ErroFio) as e:
        run(S.estado(_DB(), {"user_id": "intruso"}, "arch_teste"))
    assert e.value.status == 404


def test_ligacao_guarda_geometria_e_detecta_desenho_alterado(projeto):
    db = _DB()
    run(S.ligar(db, USER, "arch_teste", "quote_id", "dev_1"))
    est = run(S.estado(db, USER, "arch_teste"))
    orc = next(e for e in est["etapas"] if e["etapa"] == "orcamento")
    assert orc["feito"] and not orc["desatualizado"] and orc["ref"] == "dev_1"
    projeto["modelo"] = _modelo(12.0)                       # o desenho muda depois do orçamento
    est = run(S.estado(db, USER, "arch_teste"))
    orc = next(e for e in est["etapas"] if e["etapa"] == "orcamento")
    assert orc["desatualizado"] and est["proxima_etapa"] in {"bim", "orcamento", "termica"}
    run(S.ligar(db, USER, "arch_teste", "quote_id", "dev_2"))   # refeito: fica atual, o anterior continua guardado
    est = run(S.estado(db, USER, "arch_teste"))
    orc = next(e for e in est["etapas"] if e["etapa"] == "orcamento")
    assert orc["ref"] == "dev_2" and not orc["desatualizado"]
    assert {l["valor"] for l in est["ligacoes"] if l["campo"] == "quote_id"} == {"dev_1", "dev_2"}


def test_ligacao_desconhecida_recusada(projeto):
    with pytest.raises(S.ErroFio) as e:
        run(S.ligar(_DB(), USER, "arch_teste", "qualquer", "x"))
    assert e.value.status == 422


def test_imagens_sem_duplicados_e_formato_verificado(projeto):
    db = _DB()
    png = _png()
    a = run(S.adicionar_imagem(db, USER, "arch_teste", png, "bim", "Vista 3D"))
    b = run(S.adicionar_imagem(db, USER, "arch_teste", png, "bim", "Vista 3D"))
    assert a["imagem_id"] == b["imagem_id"] and a["mime"] == "image/png"
    assert len(run(S.listar_imagens(db, USER, "arch_teste"))) == 1
    with pytest.raises(S.ErroFio) as e:
        run(S.adicionar_imagem(db, USER, "arch_teste", b"isto nao e imagem", "foto"))
    assert e.value.status == 415


def test_dossier_final_junta_tudo(projeto, monkeypatch):
    import fitz
    db = _DB()
    run(S.adicionar_imagem(db, USER, "arch_teste", _png(), "render", "Render real"))
    run(S.ligar(db, USER, "arch_teste", "quote_id", "dev_9"))
    pdf, est = run(S.dossier(db, USER, "arch_teste"))
    assert pdf[:4] == b"%PDF"
    doc = fitz.open(stream=pdf, filetype="pdf")
    texto = "".join(p.get_text() for p in doc)
    assert "Casa Teste" in texto and "Render real" in texto and "dev_9" in texto
    assert doc.page_count >= 3
    assert sum(len(p.get_images()) for p in doc) >= 1
    est2 = run(S.estado(db, USER, "arch_teste"))
    assert next(e for e in est2["etapas"] if e["etapa"] == "dossier")["feito"]


def test_ferramentas_do_assistente(projeto):
    nomes = {t["name"] for t in FT.FIO_TOOLS}
    assert nomes == {"fio_ler_projeto", "fio_ligar", "fio_dossier_final"}
    db = _DB()
    r = run(FT.run_fio_tool("fio_ler_projeto", {"projet_id": "arch_teste"}, USER, db))
    assert r["ok"] and r["projeto"]["geometria"] and r["dossier_url"].endswith("/dossier.pdf")
    r = run(FT.run_fio_tool("fio_ligar", {"projet_id": "arch_teste", "campo": "thermal_study_id", "valor": "th_1", "nota": ""}, USER, db))
    assert r["ok"]
    r = run(FT.run_fio_tool("fio_ler_projeto", {"projet_id": "arch_inexistente"}, USER, db))
    assert r["ok"] is False


def test_rotas_registadas():
    from routes import fio_projeto as R
    caminhos = {r.path for r in R.router.routes}
    assert {"/fio-projeto/{pid}", "/fio-projeto/{pid}/ligar", "/fio-projeto/{pid}/imagens",
            "/fio-projeto/{pid}/imagens/{iid}", "/fio-projeto/{pid}/dossier.pdf"} <= caminhos
