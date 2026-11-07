"""Rotas v2: dossier completo de uma frase, edição livre do projeto, imagens realistas (fornecedores simulados),
inclusão das imagens no PDF/ZIP e ferramentas do Assistente/Aurora. Sem rede nem chaves reais."""
import io
import zipfile

import pytest

import test_urbanismo_auto_routes as BR   # coleções em memória e serviços oficiais simulados
from test_urbanismo_auto_v2 import PEDIDO_CLIENTE

UA = BR.UA
USER = BR.USER


@pytest.fixture()
def env(monkeypatch, tmp_path):
    db = BR.DB()
    monkeypatch.setattr(UA, "db", db)
    BR.G.set_transport(BR.TU.fake())
    BR.G._COLLECTIONS.update(t=0.0, list=[])
    store = {}
    import engines.object_storage as OS
    monkeypatch.setattr(OS, "put_object", lambda k, data, ct: store.__setitem__(k, data) or {"path": k})
    monkeypatch.setattr(OS, "get_object", lambda k: (store[k], "image/jpeg"))
    from engines.urbanismo_pt.auto import imagens as IM
    chamadas = {"n": 0}

    async def gemini_falso(prompt, ref, sessao):   # devolve a própria referência «texturada»: geometria preservada
        chamadas["n"] += 1
        from PIL import Image, ImageEnhance
        im = ImageEnhance.Color(Image.open(io.BytesIO(ref)).convert("RGB")).enhance(1.4)
        b = io.BytesIO()
        im.save(b, "PNG")
        return b.getvalue()
    monkeypatch.setattr(IM, "_gemini", gemini_falso)
    yield db, store, chamadas
    BR.G.set_transport(None)


def run(c):
    return BR.run(c)


def test_uma_frase_dossier_completo_com_imagens(env):
    db, store, chamadas = env

    async def go():
        r = await UA.executar_e_gravar({"texto": PEDIDO_CLIENTE}, USER)
        assert r["ok"] and r["estado"] == "pronto", r
        pid = r["processo_id"]
        im = await UA.gerar_imagens(pid, USER, ["perspetiva", "frente", "tardoz", "aerea"], True)
        tipos = [i["tipo"] for i in im["imagens"]]
        assert tipos.count("exata") == 4 and tipos.count("fotorrealista") == 4
        assert {"antes", "depois_esquema", "depois"} <= set(tipos)
        assert all(i["verificada"] for i in im["imagens"])
        assert chamadas["n"] == 4 + 1      # 4 vistas (geometria aprovada à 1.ª) + aérea
        doc = await db.urbanismo_processos.find_one({"processo_id": pid})
        assert all(k.startswith(f"urbanismo-auto/{USER['user_id']}/{pid}/") for k in store)
        # imagens no PDF de peças desenhadas e no ZIP
        pdf = await UA.pecas_pdf(pid, USER)
        assert pdf.body[:4] == b"%PDF"
        sims = await UA.simulacoes(doc)
        assert len(sims) == 6 and sims[0]["title"].startswith("Simulação 3D")
        z = await UA.exportar(pid, USER)
        nomes = zipfile.ZipFile(io.BytesIO(z.body)).namelist()
        assert sum("SIMULACOES_3D" in n for n in nomes) == 6
        # imagem servida só ao dono
        iid = im["imagens"][0]["id"]
        assert (await UA.obter_imagem(pid, iid, USER)).body[:2] == b"\xff\xd8"
        with pytest.raises(Exception):
            await UA.obter_imagem(pid, iid, {"user_id": "outro"})
    run(go())


def test_geometria_alterada_e_rejeitada_e_cai_para_vista_exata(env, monkeypatch):
    from engines.urbanismo_pt.auto import imagens as IM

    async def gemini_inventa(prompt, ref, sessao):   # devolve OUTRA vista: geometria diferente
        from PIL import Image
        im = Image.open(io.BytesIO(ref)).convert("RGB").transpose(Image.FLIP_LEFT_RIGHT).rotate(8)
        b = io.BytesIO()
        im.save(b, "PNG")
        return b.getvalue()
    monkeypatch.setattr(IM, "_gemini", gemini_inventa)

    async def go():
        r = await UA.executar_e_gravar({"texto": PEDIDO_CLIENTE}, USER)
        im = await UA.gerar_imagens(r["processo_id"], USER, ["perspetiva"], False)
        foto = next(i for i in im["imagens"] if i["tipo"] == "fotorrealista")
        assert foto["verificada"] is False
        doc = await env[0].urbanismo_processos.find_one({"processo_id": r["processo_id"]})
        reg = next(i for i in doc["imagens"] if i["tipo"] == "fotorrealista")
        assert len(reg["tentativas"]) == 2 and reg["tentativas"][1]["estrito"] is True
        assert "ATENÇÃO" in reg["nota"]
        sims = await UA.simulacoes(doc)   # o dossier usa a vista EXATA, nunca a imagem não verificada
        assert sims and sims[0]["data"] == next(
            env[1][k] for k in env[1] if next(i for i in doc["imagens"] if i["tipo"] == "exata")["id"] in k)
    run(go())


def test_editar_projeto_em_linguagem_simples(env):
    async def go():
        r = await UA.executar_e_gravar({"texto": PEDIDO_CLIENTE}, USER)
        pid = r["processo_id"]
        await UA.gerar_imagens(pid, USER, ["perspetiva"], False)
        r2 = await UA.editar_projeto(pid, UA.ProjetoIn(texto="afinal quero estilo alentejano e sem piscina"), USER)
        assert r2["ok"] and r2["processo_id"] == pid
        doc = await env[0].urbanismo_processos.find_one({"processo_id": pid})
        assert doc["auto"]["estilo"]["id"] == "alentejano" and not doc["auto"].get("piscina")
        assert doc["auto"]["forma"] == "l"                       # o resto do pedido mantém-se
        assert doc["imagens_desatualizadas"] is True and await UA.simulacoes(doc) == []
        lst = await UA.listar_imagens(pid, USER)
        assert lst["desatualizadas"] is True
        est = await UA.estilos(USER)
        assert any(e["id"] == "minhoto_granito" for e in est["estilos"])
    run(go())


def test_ferramentas_assistente_e_aurora(env):
    from engines.assistant_autorizacao_tool import AUTORIZACAO_TOOL_NAMES, run_autorizacao_tool

    async def go():
        assert {"licenciamento_imagens", "licenciamento_estilos"} <= AUTORIZACAO_TOOL_NAMES
        r = await run_autorizacao_tool("licenciamento_automatico", {"texto": PEDIDO_CLIENTE}, USER, {})
        assert r["ok"] and r["estado"] == "pronto"
        u = await run_autorizacao_tool("licenciamento_atualizar", {"processo_id": r["processo_id"],
                                                                   "texto": "quero 2 pisos e estilo minhoto"}, USER, {})
        assert u["ok"] and u["casa"]["pisos"] == 2
        im = await run_autorizacao_tool("licenciamento_imagens", {"processo_id": r["processo_id"], "vistas": ["aerea"]}, USER, {})
        assert im["ok"] and any(i["tipo"] == "fotorrealista" for i in im["imagens"])
        e = await run_autorizacao_tool("licenciamento_estilos", {}, USER, {})
        assert len(e["estilos"]) >= 8
        mau = await run_autorizacao_tool("licenciamento_imagens", {"processo_id": "nao_existe"}, USER, {})
        assert mau["ok"] is False
    run(go())
