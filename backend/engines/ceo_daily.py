"""Agente CEO — produção diária de artigos (PT-PT, profissionais + particulares).

- run_daily()   : todos os dias às 06:00 (Europe/Lisbon) gera N rascunhos (por defeito 10),
                  metade para profissionais e metade para particulares.
- publish_due() : de 15 em 15 min, se a publicação automática estiver ligada, publica os
                  rascunhos cuja hora agendada já passou (máx. N/dia, espaçados entre 08h e 20h).

Sem duplicados: os temas vêm de `ceo_topics` (banco inicial + novos temas propostos pela IA)
e são comparados com TODOS os títulos já existentes em `autoseo_articles` (CEO, BabyLoveGrowth,
AutoSEO). Um lock diário em `ceo_daily_runs` impede execuções duplicadas (vários workers).
"""
from __future__ import annotations

import difflib
import logging
import random
import re
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from pymongo.errors import DuplicateKeyError

from core.db import db
from engines import ceo_blog
from engines.ai import _complete, _json

log = logging.getLogger("ceo.daily")
LISBON = ZoneInfo("Europe/Lisbon")
SETTINGS_KEY = "ceo_daily_settings"
DEFAULTS = {"enabled": True, "count": 10, "auto_publish": False, "max_auto_per_day": 10,
            "with_image": True, "publish_window": [8, 20]}
SIMILARITY = 0.82

# ------------------------------------------------------------------ banco inicial de temas
TOPICS_PROS = [
    ("Como fazer um orçamento de obra com IVA a 23 % e a 6 % sem erros", ["orçamento de obra", "IVA 6% obras", "IVA 23%"]),
    ("Quando se aplica o IVA a 6 % em empreitadas de reabilitação", ["IVA 6% reabilitação", "empreitada", "verba 2.27"]),
    ("Alvará de construção IMPIC: classes, categorias e como manter em dia", ["alvará IMPIC", "classes de alvará", "empreiteiro"]),
    ("Autos de medição: como preparar e faturar por fases", ["auto de medição", "faturação por fases", "obra"]),
    ("Faturação certificada AT para empresas de construção", ["faturação certificada", "AT", "software certificado"]),
    ("Retenção na fonte e autoliquidação do IVA na construção civil", ["autoliquidação IVA", "construção civil", "subempreitada"]),
    ("Gestão de subempreiteiros: contratos, prazos e responsabilidades", ["subempreiteiros", "contrato de subempreitada", "gestão de obra"]),
    ("Como calcular a margem de lucro numa obra de remodelação", ["margem de lucro", "preço de venda", "obra"]),
    ("Medições a partir de plantas em PDF: método rápido e fiável", ["medições", "plantas PDF", "mapa de quantidades"]),
    ("Mapa de quantidades: estrutura e erros mais comuns", ["mapa de quantidades", "medições", "concurso"]),
    ("Plano de segurança e saúde em obra: o que tem de conter", ["plano de segurança e saúde", "PSS", "coordenação de segurança"]),
    ("Comunicação prévia de abertura de estaleiro: quando e como", ["abertura de estaleiro", "ACT", "segurança em obra"]),
    ("Livro de obra eletrónico: obrigações do diretor de obra", ["livro de obra", "diretor de obra", "licenciamento"]),
    ("Licença ou comunicação prévia: guia RJUE para empreiteiros", ["RJUE", "comunicação prévia", "licença de construção"]),
    ("Trabalhos a mais e a menos: como os orçamentar e documentar", ["trabalhos a mais", "adenda", "empreitada"]),
    ("Planeamento de obra com diagrama de Gantt: passo a passo", ["planeamento de obra", "Gantt", "prazos"]),
    ("Controlo de custos em obra: indicadores que contam", ["controlo de custos", "obra", "rentabilidade"]),
    ("Revisão de preços em empreitadas: princípios e cuidados", ["revisão de preços", "empreitada", "inflação materiais"]),
    ("Como responder a um caderno de encargos de uma obra particular", ["caderno de encargos", "proposta", "obra"]),
    ("Betão armado em moradias: pré-dimensionamento de lajes e vigas", ["betão armado", "laje", "viga", "Eurocódigo 2"]),
    ("Eurocódigos com Anexo Nacional português: o que muda no cálculo", ["Eurocódigos", "Anexo Nacional", "NP EN"]),
    ("Ação sísmica em Portugal: noções essenciais para pequenas obras", ["ação sísmica", "NP EN 1998", "zonas sísmicas"]),
    ("Escadas em betão: regras de conforto e dimensionamento", ["escadas betão", "espelho e cobertor", "Blondel"]),
    ("Fundações superficiais: quando pedir estudo geotécnico", ["estudo geotécnico", "sapatas", "fundações"]),
    ("Impermeabilização de coberturas planas: soluções e garantias", ["impermeabilização", "cobertura plana", "telas"]),
    ("ETICS (capoto): execução correta e patologias a evitar", ["ETICS", "capoto", "isolamento exterior"]),
    ("Reabilitação de edifícios antigos: paredes de alvenaria e tabiques", ["reabilitação", "alvenaria antiga", "tabique"]),
    ("Como reduzir desperdícios e resíduos de construção (RCD)", ["RCD", "resíduos de construção", "gestão de resíduos"]),
    ("Plano de prevenção e gestão de RCD: obrigações do empreiteiro", ["PPG RCD", "resíduos", "licenciamento"]),
    ("Seguros obrigatórios para empresas de construção", ["seguro acidentes de trabalho", "responsabilidade civil", "construção"]),
    ("Como captar clientes particulares para obras de remodelação", ["angariar clientes", "remodelação", "marketing empreiteiro"]),
    ("Apresentar orçamentos profissionais que fecham negócio", ["proposta comercial", "orçamento profissional", "conversão"]),
    ("Digitalizar a empresa de construção: por onde começar", ["digitalização", "software de obra", "produtividade"]),
    ("Fotografias de obra e relatórios ao cliente: boas práticas", ["relatório de obra", "acompanhamento", "cliente"]),
    ("Gestão de equipas em obra: picagem de ponto e horas", ["gestão de equipas", "registo de horas", "obra"]),
    ("Encomendas de materiais: como evitar ruturas e excessos", ["encomendas materiais", "aprovisionamento", "obra"]),
    ("Comparar preços de materiais de construção em Portugal", ["preços materiais", "fornecedores", "comparação"]),
    ("Receção provisória e definitiva da obra: o que verificar", ["receção da obra", "garantia", "empreitada"]),
    ("Garantias legais da obra em Portugal: prazos e defeitos", ["garantia da obra", "defeitos de construção", "prazos"]),
    ("Telas finais e documentação de fim de obra", ["telas finais", "fim de obra", "licença de utilização"]),
    ("Ficha técnica da habitação: o que é e quem a prepara", ["ficha técnica da habitação", "habitação nova", "documentação"]),
    ("Certificado energético em obras novas e grandes remodelações", ["certificado energético", "SCE", "REH"]),
    ("Acústica em edifícios de habitação: requisitos e soluções", ["acústica", "RRAE", "isolamento sonoro"]),
    ("Instalações elétricas em remodelações: certificação e regras", ["instalação elétrica", "certificação", "remodelação"]),
    ("Redes de águas e esgotos em reabilitação: erros a evitar", ["canalização", "esgotos", "reabilitação"]),
    ("Caixilharia eficiente: classes térmicas e montagem correta", ["caixilharia", "janelas eficientes", "montagem"]),
    ("Obras em condomínio: autorizações e comunicação com vizinhos", ["obras em condomínio", "assembleia de condóminos", "autorizações"]),
    ("Como calcular o preço por m² de uma remodelação total", ["preço por m2", "remodelação total", "estimativa"]),
    ("Contrato de empreitada com particulares: cláusulas essenciais", ["contrato de empreitada", "cláusulas", "particulares"]),
    ("Pagamentos faseados em obra: como proteger a tesouraria", ["tesouraria", "pagamentos faseados", "obra"]),
    ("Inteligência artificial na construção: usos práticos hoje", ["inteligência artificial construção", "IA", "produtividade"]),
    ("Leitura de plantas de arquitetura para orçamentar", ["leitura de plantas", "arquitetura", "orçamentar"]),
    ("Cofragem e armaduras: como estimar quantidades de aço", ["armaduras", "aço", "cofragem", "quantidades"]),
    ("Pavimentos cerâmicos: quantidades, desperdícios e assentamento", ["pavimentos cerâmicos", "quantidades", "assentamento"]),
    ("Pinturas interiores e exteriores: rendimentos e orçamento", ["pintura", "rendimento tinta", "orçamento"]),
    ("Pladur e tetos falsos: medição e preço por m²", ["pladur", "teto falso", "medição"]),
    ("Demolições interiores: segurança, licenças e resíduos", ["demolição", "paredes interiores", "segurança"]),
    ("Paredes resistentes: quando é preciso engenheiro de estruturas", ["parede resistente", "engenheiro de estruturas", "remodelação"]),
    ("Indicadores de desempenho para empresas de construção", ["KPI construção", "indicadores", "gestão"]),
    ("Como preparar a empresa para concursos de obras particulares", ["concursos", "obras particulares", "proposta"]),
]

TOPICS_PART = [
    ("Quanto custa remodelar uma casa de banho em Portugal", ["remodelar casa de banho", "preço", "Portugal"]),
    ("Remodelar a cozinha: etapas, prazos e orçamento", ["remodelar cozinha", "orçamento", "etapas"]),
    ("Preço por m² de uma remodelação total de apartamento", ["remodelação total", "preço m2", "apartamento"]),
    ("IVA a 6 % nas obras de casa: quando tem direito", ["IVA 6% obras", "reabilitação", "habitação"]),
    ("Precisa de licença para fazer obras em casa? Guia simples", ["licença de obras", "comunicação prévia", "câmara municipal"]),
    ("Obras isentas de licença: o que pode fazer sem pedir à câmara", ["obras isentas", "escassa relevância urbanística", "câmara"]),
    ("Como escolher um bom empreiteiro e evitar surpresas", ["escolher empreiteiro", "orçamento", "contrato"]),
    ("Como comparar orçamentos de obras ponto por ponto", ["comparar orçamentos", "obras", "proposta"]),
    ("Contrato de obras com o empreiteiro: o que deve constar", ["contrato de obras", "empreiteiro", "cláusulas"]),
    ("Humidade nas paredes: causas e soluções definitivas", ["humidade paredes", "bolor", "infiltrações"]),
    ("Infiltrações no telhado: como detetar e reparar", ["infiltrações telhado", "reparação telhado", "telhas"]),
    ("Isolamento térmico da casa: por onde começar", ["isolamento térmico", "eficiência energética", "conforto"]),
    ("Janelas eficientes: vale a pena trocar?", ["janelas eficientes", "vidro duplo", "caixilharia"]),
    ("Certificado energético: o que é e quando é obrigatório", ["certificado energético", "ADENE", "venda casa"]),
    ("Bomba de calor ou ar condicionado: o que escolher", ["bomba de calor", "ar condicionado", "aquecimento"]),
    ("Painéis solares em casa: custos e cuidados na instalação", ["painéis solares", "autoconsumo", "fotovoltaico"]),
    ("Aquecimento central em casas portuguesas: opções", ["aquecimento central", "radiadores", "piso radiante"]),
    ("Piso radiante: vantagens, custos e quando compensa", ["piso radiante", "aquecimento", "remodelação"]),
    ("Pintar a casa por dentro: quantidades de tinta e preço", ["pintar casa", "tinta", "preço"]),
    ("Pintura da fachada: quando fazer e quanto custa", ["pintura fachada", "reabilitação fachada", "preço"]),
    ("Trocar o pavimento: cerâmico, vinílico ou madeira?", ["pavimento", "vinílico", "flutuante", "cerâmico"]),
    ("Derrubar uma parede em casa: o que verificar antes", ["derrubar parede", "parede resistente", "engenheiro"]),
    ("Ampliar a casa: licenciamento, prazos e custos", ["ampliação casa", "licenciamento", "custos"]),
    ("Construir uma moradia em Portugal: as fases do processo", ["construir moradia", "fases", "licenciamento"]),
    ("Comprar casa para remodelar: como estimar as obras", ["casa para remodelar", "estimativa obras", "compra"]),
    ("Remodelar casa antiga: surpresas comuns e como as evitar", ["casa antiga", "remodelação", "surpresas"]),
    ("Obras num apartamento em condomínio: regras e horários", ["obras condomínio", "horários obras", "vizinhos"]),
    ("Terraço e varanda: impermeabilizar e aproveitar", ["terraço", "varanda", "impermeabilização"]),
    ("Telhado novo: tipos de telha e manutenção", ["telhado", "telha cerâmica", "manutenção"]),
    ("Casa de banho pequena: ideias para ganhar espaço", ["casa de banho pequena", "ideias", "remodelação"]),
    ("Substituir banheira por base de duche: passo a passo", ["banheira por duche", "base de duche", "obra"]),
    ("Cozinha em open space: o que considerar antes de abrir", ["cozinha open space", "paredes", "remodelação"]),
    ("Remodelar sem sair de casa: como organizar a obra", ["organizar obra", "remodelar a viver em casa", "planeamento"]),
    ("Quanto tempo demora uma remodelação total", ["prazo obra", "remodelação total", "planeamento"]),
    ("Pedir orçamentos de obras online: vantagens e cuidados", ["orçamento obras online", "estimativa", "empreiteiro"]),
    ("Estimar o custo de uma obra a partir de uma fotografia", ["estimativa por foto", "IA", "custo obra"]),
    ("Instalação elétrica antiga: sinais de que precisa de remodelação", ["instalação elétrica antiga", "segurança", "quadro elétrico"]),
    ("Canalização antiga: quando substituir os tubos", ["canalização antiga", "tubos", "fugas de água"]),
    ("Isolamento acústico entre vizinhos: soluções práticas", ["isolamento acústico", "ruído vizinhos", "soluções"]),
    ("Garagem convertida em habitação: é possível?", ["converter garagem", "licença de utilização", "habitação"]),
    ("Anexo ou casa de jardim: licença e regras", ["anexo jardim", "licença", "câmara municipal"]),
    ("Piscina em casa: licenciamento e custos de construção", ["piscina", "licenciamento", "custo construção"]),
    ("Muro de vedação: regras municipais e preço", ["muro de vedação", "regras", "preço"]),
    ("Remodelar para vender: obras que valorizam a casa", ["valorizar casa", "obras para vender", "remodelação"]),
    ("Obras para arrendamento: o mínimo para arrendar bem", ["obras arrendamento", "senhorio", "remodelação"]),
    ("Acessibilidade em casa para idosos: adaptações essenciais", ["acessibilidade", "idosos", "adaptações casa"]),
    ("Caixilharia de alumínio ou PVC: diferenças reais", ["alumínio ou PVC", "janelas", "caixilharia"]),
    ("Bolor no teto: porque aparece e como acabar com ele", ["bolor teto", "condensação", "ventilação"]),
    ("Ventilação da casa: VMC e soluções simples", ["ventilação", "VMC", "qualidade do ar"]),
    ("Fissuras nas paredes: quando são perigosas", ["fissuras paredes", "estrutura", "diagnóstico"]),
    ("Revestimentos de parede: azulejo, microcimento ou tinta", ["revestimentos parede", "microcimento", "azulejo"]),
    ("Escadas interiores: tipos, espaço necessário e segurança", ["escadas interiores", "dimensões", "segurança"]),
    ("Mezanino em casa: regras e viabilidade", ["mezanino", "pé-direito", "estrutura"]),
    ("Faça você mesmo: pequenas reparações que pode fazer sozinho", ["faça você mesmo", "reparações", "casa"]),
    ("Orçamento de obras: como não ultrapassar o valor previsto", ["orçamento obras", "derrapagem", "controlo custos"]),
    ("Garantia das obras feitas em casa: os seus direitos", ["garantia obras", "defeitos", "direitos consumidor"]),
    ("Conflito com o empreiteiro: como resolver", ["conflito empreiteiro", "reclamação", "resolução"]),
    ("Livro de reclamações e obras: quando usar", ["livro de reclamações", "obras", "consumidor"]),
    ("Reabilitação urbana: benefícios em áreas ARU", ["ARU", "reabilitação urbana", "benefícios fiscais"]),
    ("Checklist antes de começar obras em casa", ["checklist obras", "preparar obra", "remodelação"]),
]

AUD_KEYS = ("pros", "particuliers")


# ------------------------------------------------------------------ definições
async def get_settings() -> dict:
    doc = await db.app_settings.find_one({"key": SETTINGS_KEY}, {"_id": 0}) or {}
    out = {**DEFAULTS, **{k: v for k, v in doc.items() if k in DEFAULTS}}
    return out


async def save_settings(patch: dict) -> dict:
    cur = await get_settings()
    if "count" in patch:
        cur["count"] = max(0, min(30, int(patch["count"])))
    if "max_auto_per_day" in patch:
        cur["max_auto_per_day"] = max(0, min(30, int(patch["max_auto_per_day"])))
    for k in ("enabled", "auto_publish", "with_image"):
        if k in patch:
            cur[k] = bool(patch[k])
    await db.app_settings.update_one({"key": SETTINGS_KEY}, {"$set": {"key": SETTINGS_KEY, **cur}}, upsert=True)
    return cur


# ------------------------------------------------------------------ temas
def _norm(t: str) -> str:
    return re.sub(r"\s+", " ", ceo_blog.slugify(t).replace("-", " ")).strip()


def is_duplicate(title: str, existing: list[str]) -> bool:
    n = _norm(title)
    if not n:
        return True
    for e in existing:
        if n == e or difflib.SequenceMatcher(None, n, e).ratio() >= SIMILARITY:
            return True
    return False


async def existing_titles() -> list[str]:
    docs = await db.autoseo_articles.find({"status": {"$ne": "rejected"}}, {"_id": 0, "title": 1, "topic": 1}
                                          ).to_list(20000)
    out = set()
    for d in docs:
        for k in ("title", "topic"):
            if d.get(k):
                out.add(_norm(d[k]))
    return list(out)


async def seed_topics() -> int:
    n = 0
    for audience, items in (("pros", TOPICS_PROS), ("particuliers", TOPICS_PART)):
        for title, kws in items:
            tid = ceo_blog.slugify(title)
            res = await db.ceo_topics.update_one(
                {"topic_id": tid},
                {"$setOnInsert": {"topic_id": tid, "title": title, "audience": audience, "keywords": kws,
                                  "status": "new", "source": "seed", "created_at": ceo_blog.now_iso()}},
                upsert=True)
            n += 1 if res.upserted_id is not None else 0
    # Migração: rascunhos/artigos antigos do agente gravados como "fr" passam a "pt".
    await db.autoseo_articles.update_many({"source": "ceo_agent", "language_code": "fr"},
                                          {"$set": {"language_code": "pt"}})
    return n


async def _ideate(audience: str, n: int, existing: list[str]) -> int:
    """Pede à IA novos temas PT (quando o banco está a esgotar-se)."""
    aud = ceo_blog.AUDIENCE_LABEL[audience]
    sample = "; ".join(random.sample(existing, min(60, len(existing))))
    raw = await _complete(
        ceo_blog._system(audience),
        f"Propõe {n} temas NOVOS de artigos de blogue SEO para {aud}, sobre obras, construção e "
        "remodelação em PORTUGAL (pesquisas reais que as pessoas fazem no Google em Portugal). "
        f"Evita temas parecidos com estes já publicados: {sample}.\n"
        'Responde APENAS em JSON: {"topics": [{"title": "...", "keywords": ["...", "..."]}]}',
        feature="ceo_topics")
    data = _json(raw, {}) or {}
    added = 0
    for t in data.get("topics") or []:
        title = (t or {}).get("title")
        if not title or is_duplicate(title, existing):
            continue
        tid = ceo_blog.slugify(title)
        res = await db.ceo_topics.update_one(
            {"topic_id": tid},
            {"$setOnInsert": {"topic_id": tid, "title": title, "audience": audience,
                              "keywords": [k for k in (t.get("keywords") or []) if isinstance(k, str)][:6],
                              "status": "new", "source": "ai", "created_at": ceo_blog.now_iso()}},
            upsert=True)
        if res.upserted_id is not None:
            added += 1
            existing.append(_norm(title))
    return added


async def pick_topics(audience: str, n: int, existing: list[str]) -> list[dict]:
    picked: list[dict] = []
    for attempt in range(3):
        cands = await db.ceo_topics.find({"audience": audience, "status": "new"}, {"_id": 0}).to_list(2000)
        random.shuffle(cands)
        for t in cands:
            if len(picked) >= n:
                break
            if is_duplicate(t["title"], existing):
                await db.ceo_topics.update_one({"topic_id": t["topic_id"]}, {"$set": {"status": "duplicate"}})
                continue
            picked.append(t)
            existing.append(_norm(t["title"]))
        if len(picked) >= n:
            break
        try:
            await _ideate(audience, max(20, (n - len(picked)) * 3), existing)
        except Exception as e:  # noqa: BLE001
            log.error("CEO ideation failed: %s", e)
            break
    return picked


def split_counts(total: int) -> dict:
    pros = total // 2
    return {"pros": pros, "particuliers": total - pros}


def _schedule_times(n: int, day: datetime, window: list[int]) -> list[str]:
    """n horas espaçadas na janela [h0, h1] (Lisboa) do dia indicado, em UTC ISO."""
    h0, h1 = window
    start = day.astimezone(LISBON).replace(hour=h0, minute=0, second=0, microsecond=0)
    span = (h1 - h0) * 60
    step = span / max(1, n)
    return [(start + timedelta(minutes=round(i * step + step / 2))).astimezone(timezone.utc).isoformat()
            for i in range(n)]


# ------------------------------------------------------------------ execução
async def run_daily(force: bool = False, count: int | None = None) -> dict:
    settings = await get_settings()
    if not settings["enabled"] and not force:
        return {"skipped": "disabled"}
    today = datetime.now(LISBON).date().isoformat()
    run_id = today if not force else f"{today}-manual-{ceo_blog.now_iso()[11:19]}"
    try:
        await db.ceo_daily_runs.insert_one({"_id": run_id, "date": today, "status": "running",
                                            "started_at": ceo_blog.now_iso()})
    except DuplicateKeyError:
        return {"skipped": "already_ran", "date": today}

    total = settings["count"] if count is None else max(0, min(30, int(count)))
    await seed_topics()
    existing = await existing_titles()
    created, errors, articles = 0, 0, []
    for audience, n in split_counts(total).items():
        for t in await pick_topics(audience, n, existing):
            try:
                doc = await ceo_blog.generate_article(
                    t["title"], t.get("keywords") or [], audience, with_image=settings["with_image"],
                    created_by="ceo_daily", origin="daily",
                    extra_fields={"daily_date": today, "topic_id": t["topic_id"]})
                await db.ceo_topics.update_one({"topic_id": t["topic_id"]},
                                               {"$set": {"status": "used", "used_at": ceo_blog.now_iso(),
                                                         "article_id": doc["autoseo_id"]}})
                created += 1
                articles.append(doc["autoseo_id"])
            except Exception as e:  # noqa: BLE001
                errors += 1
                log.error("CEO daily article failed (%s): %s", t.get("title"), e)

    scheduled = 0
    if settings["auto_publish"] and articles:
        n_auto = min(len(articles), settings["max_auto_per_day"])
        times = _schedule_times(n_auto, datetime.now(timezone.utc), settings["publish_window"])
        for aid, when in zip(articles[:n_auto], times):
            await db.autoseo_articles.update_one({"autoseo_id": aid}, {"$set": {"scheduled_publish_at": when}})
            scheduled += 1

    res = {"date": today, "requested": total, "created": created, "errors": errors,
           "scheduled": scheduled, "finished_at": ceo_blog.now_iso(), "status": "done"}
    await db.ceo_daily_runs.update_one({"_id": run_id}, {"$set": res})
    log.info("CEO daily: %s", res)
    return res


async def publish_due() -> int:
    settings = await get_settings()
    if not settings["auto_publish"]:
        return 0
    today = datetime.now(LISBON).date().isoformat()
    published_today = await db.autoseo_articles.count_documents(
        {"source": "ceo_agent", "auto_published": True, "published_day": today})
    room = settings["max_auto_per_day"] - published_today
    if room <= 0:
        return 0
    now = ceo_blog.now_iso()
    due = await db.autoseo_articles.find(
        {"source": "ceo_agent", "status": "draft", "scheduled_publish_at": {"$lte": now}},
        {"_id": 0, "autoseo_id": 1}).sort("scheduled_publish_at", 1).to_list(room)
    for d in due:
        await db.autoseo_articles.update_one(
            {"autoseo_id": d["autoseo_id"], "status": "draft"},
            {"$set": {"status": "published", "published_at": now, "updated_at": now,
                      "auto_published": True, "published_day": today}})
    return len(due)


async def stats() -> dict:
    now = datetime.now(LISBON)
    today, month = now.date().isoformat(), now.strftime("%Y-%m")
    q = {"source": "ceo_agent", "origin": "daily"}
    docs = await db.autoseo_articles.find(q, {"_id": 0, "daily_date": 1, "status": 1, "cost_eur": 1,
                                              "audience": 1}).to_list(20000)
    def agg(prefix):
        sel = [d for d in docs if (d.get("daily_date") or "").startswith(prefix)]
        return {"articles": len(sel),
                "published": sum(1 for d in sel if d.get("status") == "published"),
                "drafts": sum(1 for d in sel if d.get("status") == "draft"),
                "pros": sum(1 for d in sel if d.get("audience") == "pros"),
                "particuliers": sum(1 for d in sel if d.get("audience") == "particuliers"),
                "cost_eur": round(sum(float(d.get("cost_eur") or 0) for d in sel), 2)}
    runs = await db.ceo_daily_runs.find({}, {"_id": 0}).sort("started_at", -1).to_list(7)
    topics_left = {a: await db.ceo_topics.count_documents({"audience": a, "status": "new"}) for a in AUD_KEYS}
    return {"today": agg(today), "month": agg(month), "runs": runs, "topics_left": topics_left}
