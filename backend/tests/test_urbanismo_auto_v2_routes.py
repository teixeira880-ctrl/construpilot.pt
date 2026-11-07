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

    async def gemini_falso(prompt, ref, sessao, extra=None):   # devolve a própria referência «texturada»: geometria preservada
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
        im = await UA.gerar_imagens(pid, USER, None, True)      # conjunto completo por omissão
        tipos = [i["tipo"] for i in im["imagens"]]
        vistas = {i["vista"] for i in im["imagens"] if i["tipo"] == "fotorrealista"}
        assert vistas == set(UA.VISTAS_PADRAO)                  # exteriores, piscina, entardecer e 4 interiores
        assert tipos.count("exata") == 9                         # o entardecer reutiliza a vista exata da perspetiva
        assert {"antes", "depois_esquema", "depois", "implantacao"} <= set(tipos)
        assert all(i["verificada"] for i in im["imagens"])
        from engines.urbanismo_pt.auto import imagens as IM
        assert chamadas["n"] == 10 * IM.CANDIDATOS + 1           # N candidatos por vista (aprovados à 1.ª) + aérea
        doc = await db.urbanismo_processos.find_one({"processo_id": pid})
        # qualidade de entrega: ≥ 1920 px, e a ampliação fica registada (nunca passa por resolução nativa)
        fotos = [i for i in doc["imagens"] if i["tipo"] == "fotorrealista"]
        assert all(i["qualidade"]["largura"] >= 1920 for i in fotos)
        assert all(i["qualidade"]["ampliada"] == (i["qualidade"]["largura_nativa"] < 1920) for i in fotos)
        assert next(i for i in doc["imagens"] if i["vista"] == "perspetiva_entardecer")["iluminacao"] == "entardecer"
        assert {i.get("compartimento") for i in fotos if i["vista"].startswith("interior_")} >= {"Sala de estar e jantar", "Suite"}
        assert all(k.startswith(f"urbanismo-auto/{USER['user_id']}/{pid}/") for k in store)
        # imagens no PDF de peças desenhadas e no ZIP
        pdf = await UA.pecas_pdf(pid, USER)
        assert pdf.body[:4] == b"%PDF"
        sims = await UA.simulacoes(doc)
        assert len(sims) == 10 + 1 + 2 and sims[0]["title"].startswith("Simulação 3D")
        assert any("implantação humanizada" in x["title"] for x in sims)
        z = await UA.exportar(pid, USER)
        nomes = zipfile.ZipFile(io.BytesIO(z.body)).namelist()
        assert sum("SIMULACOES_3D" in n for n in nomes) == 13
        # imagem servida só ao dono
        iid = im["imagens"][0]["id"]
        assert (await UA.obter_imagem(pid, iid, USER)).body[:2] == b"\xff\xd8"
        with pytest.raises(Exception):
            await UA.obter_imagem(pid, iid, {"user_id": "outro"})
    run(go())


def test_geometria_alterada_e_rejeitada_e_cai_para_vista_exata(env, monkeypatch):
    from engines.urbanismo_pt.auto import imagens as IM

    async def gemini_inventa(prompt, ref, sessao, extra=None):   # devolve OUTRA vista: geometria diferente
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
        assert len(reg["tentativas"]) == 2 * IM.CANDIDATOS and reg["tentativas"][-1]["estrito"] is True
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


def test_foto_do_terreno_montagem_so_entra_aprovada(env, monkeypatch):
    from engines.urbanismo_pt.auto import imagens as IM
    from PIL import Image
    db, store, _ = env
    recebidas = {}

    async def montagem_falsa(proc, foto, ref, sessao):
        recebidas["n_refs"] = (foto[:2], ref[:4])
        return ref
    monkeypatch.setattr(IM, "montagem", montagem_falsa)

    class Up:   # UploadFile mínimo
        def __init__(self, data):
            self.data = data

        async def read(self, n=-1):
            return self.data
    b = io.BytesIO()
    Image.new("RGB", (1200, 800), (120, 160, 90)).save(b, "PNG")

    async def go():
        r = await UA.executar_e_gravar({"texto": PEDIDO_CLIENTE}, USER)
        pid = r["processo_id"]
        with pytest.raises(Exception):
            await UA.enviar_foto_terreno(pid, Up(b"<script>nao e imagem</script>"), USER)
        ok = await UA.enviar_foto_terreno(pid, Up(b.getvalue()), USER)
        assert ok["ok"] and store[f"urbanismo-auto/{USER['user_id']}/{pid}/foto-terreno.jpg"][:2] == b"\xff\xd8"
        im = await UA.gerar_imagens(pid, USER, ["perspetiva"], True)
        mont = next(i for i in im["imagens"] if i["tipo"] == "montagem")
        assert mont["verificada"] is False and recebidas["n_refs"][0] == b"\xff\xd8"
        doc = await db.urbanismo_processos.find_one({"processo_id": pid})
        assert not any("fotografia do terreno" in x["title"] for x in await UA.simulacoes(doc))   # não aprovada → fora
        with pytest.raises(Exception):
            await UA.aprovar_imagem(pid, im["imagens"][0]["id"], UA.AprovarIn(), USER)        # só montagens
        await UA.aprovar_imagem(pid, mont["id"], UA.AprovarIn(aprovada=True), USER)
        doc = await db.urbanismo_processos.find_one({"processo_id": pid})
        assert any("fotografia do terreno" in x["title"] for x in await UA.simulacoes(doc))
        # a fotografia continua associada depois de alterar o projeto
        await UA.editar_projeto(pid, UA.ProjetoIn(texto="estilo minimalista"), USER)
        doc = await db.urbanismo_processos.find_one({"processo_id": pid})
        assert doc.get("foto_terreno")
    run(go())


def test_interiores_e_implantacao_sao_exatos(env, tmp_path):
    from PIL import Image
    import test_urbanismo_auto as B
    from engines.urbanismo_pt.auto import dgt_cache as CACHE, imagens as IM, interiores as INT
    CACHE.usar_pasta(str(tmp_path / "dgt"))
    d = B.run({"texto": PEDIDO_CLIENTE})["processo"]
    esc = INT.escolher(d)
    assert [n for n, *_ in esc] == ["interior_sala", "interior_cozinha", "interior_suite", "interior_wc"]
    for nome, c, piso in esc:
        v = INT.vista(d, nome, c, piso)
        vaos = [x for x in d["auto"]["vaos"] if x["compartimento"] == c["nome"]]
        assert v["n_vaos"] == len(vaos) >= 1 and v["cobertura_mascara"] > 0.005   # os vãos reais estão visíveis
        assert "EXACTLY" in INT.prompt_interior(d, nome, c) and c["nome"] in INT.prompt_interior(d, nome, c)
    # implantação humanizada: a cobertura da casa aparece no sítio certo
    m = UA.modelo3d(d)
    im = Image.open(io.BytesIO(IM.implantacao_humanizada(m, 1000))).convert("RGB")
    assert im.size == (1000, 1000)
    # nitidez: uma imagem desfocada tem nitidez muito menor
    from PIL import ImageFilter
    b1, b2 = io.BytesIO(), io.BytesIO()
    im.save(b1, "PNG")
    im.filter(ImageFilter.GaussianBlur(6)).save(b2, "PNG")
    assert IM.nitidez(b1.getvalue()) > 3 * IM.nitidez(b2.getvalue())
    jpeg, q = IM.acabar(b2.getvalue(), 1920)
    assert q["ampliada"] and q["largura"] == 1920 and q["largura_nativa"] == 1000


def test_cadeia_runway_openai_emergent_com_juiz_claude(env, monkeypatch):
    """Ordem automática: Runway → OpenAI → Emergent; Claude julga; defeitos passam à ronda seguinte; nada é perguntado."""
    from PIL import Image
    from engines.urbanismo_pt.auto import imagens as IM
    monkeypatch.setenv("RUNWAYML_API_SECRET", "x")
    monkeypatch.setenv("OPENAI_API_KEY", "x")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "x")
    import engines.llm_keys as LK
    monkeypatch.setattr(LK, "openai_direct_active", lambda: True)
    visto = {"ordem": [], "prompts": {}}

    def igual(ref):
        b = io.BytesIO()
        Image.open(io.BytesIO(ref)).convert("RGB").save(b, "PNG")
        return b.getvalue()

    async def runway(prompt, ref, sessao, extra=None):
        visto["ordem"].append("runway")
        visto["prompts"]["runway"] = prompt
        assert Image.open(io.BytesIO(ref)).size[0] / Image.open(io.BytesIO(ref)).size[1] > 1.7   # referência alargada a 16:9
        im = Image.open(io.BytesIO(ref)).convert("RGB").transpose(Image.FLIP_LEFT_RIGHT).rotate(8)
        b = io.BytesIO()
        im.save(b, "PNG")
        return b.getvalue()

    async def openai_(prompt, ref, sessao, extra=None):
        visto["ordem"].append("openai")
        return igual(ref)

    async def gemini(prompt, ref, sessao, extra=None):
        visto["ordem"].append("gemini")
        visto["prompts"]["gemini"] = prompt
        return igual(ref)
    chamadas = {"n": 0}

    async def juiz(ref, img):
        chamadas["n"] += 1
        # 1.º juízo (OpenAI): parece CGI; depois (Emergent): aprovado
        return ({"realismo": 4.0, "geometria": True, "defeitos": ["plastic CGI look on the stone"]}
                if visto["ordem"][-1] == "openai" else {"realismo": 8.5, "geometria": True, "defeitos": []})
    monkeypatch.setattr(IM, "_runway", runway)
    monkeypatch.setattr(IM, "_openai", openai_)
    monkeypatch.setattr(IM, "_gemini", gemini)
    monkeypatch.setattr(IM, "juiz_claude", juiz)
    monkeypatch.setattr(IM, "CANDIDATOS", 1)

    async def go():
        r = await UA.executar_e_gravar({"texto": PEDIDO_CLIENTE}, USER)
        im = await UA.gerar_imagens(r["processo_id"], USER, ["perspetiva"], False)
        foto = next(i for i in im["imagens"] if i["tipo"] == "fotorrealista")
        assert foto["fornecedor"] == "gemini" and foto["verificada"]
        assert visto["ordem"] == ["runway", "openai", "gemini"]
        assert len(visto["prompts"]["runway"]) <= 990 and "@Projeto" in visto["prompts"]["runway"]
        assert "plastic CGI look" in visto["prompts"]["gemini"]          # o Claude corrige a ronda seguinte
        doc = await env[0].urbanismo_processos.find_one({"processo_id": r["processo_id"]})
        reg = next(i for i in doc["imagens"] if i["tipo"] == "fotorrealista")
        assert reg["qualidade"]["realismo_claude"] == 8.5
        assert [t["fornecedor"] for t in reg["tentativas"]] == ["runway", "openai", "gemini"]
    run(go())


def test_fornecedor_que_nao_responde_nao_bloqueia(env, monkeypatch):
    import asyncio
    from engines.urbanismo_pt.auto import imagens as IM
    monkeypatch.setenv("RUNWAYML_API_SECRET", "x")
    monkeypatch.setattr(IM, "TEMPO_MAX_S", {"runway": 0.2, "openai": 0.2, "gemini": 5})
    monkeypatch.setattr(IM, "ORDEM_FORNECEDORES", ["runway", "gemini"])

    async def runway_parado(prompt, ref, sessao, extra=None):
        await asyncio.sleep(30)
    monkeypatch.setattr(IM, "_runway", runway_parado)

    async def go():
        r = await UA.executar_e_gravar({"texto": PEDIDO_CLIENTE}, USER)
        im = await UA.gerar_imagens(r["processo_id"], USER, ["perspetiva"], False)
        foto = next(i for i in im["imagens"] if i["tipo"] == "fotorrealista")
        assert foto["fornecedor"] == "gemini"
        doc = await env[0].urbanismo_processos.find_one({"processo_id": r["processo_id"]})
        reg = next(i for i in doc["imagens"] if i["tipo"] == "fotorrealista")
        assert reg["tentativas"][0]["fornecedor"] == "runway" and reg["tentativas"][0]["erro"] == "TimeoutError"
        assert IM._erro_curto(RuntimeError("Bearer sk-abcdef123456 inválida")) == "RuntimeError: *** inválida"
    run(go())
