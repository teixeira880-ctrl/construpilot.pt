"""Gestão de obra — regras puras (sem base de dados nem rede).

Completa a «Obra colaborativa» (engines/obra_colab.py) com o que faltava ao acompanhamento no terreno:
  * diário de obra (entrada diária, assinatura, visto da fiscalização, aditamentos imutáveis);
  * qualidade, segurança e ambiente (inspeções por lista de verificação, não conformidades com plano
    de ação 5W2H, acidentes, quase-acidentes, diálogos de segurança, verificação de EPI);
  * pedidos de esclarecimento (RFI) com destinatário, prazo e respostas;
  * stock de materiais da obra (receções de encomendas, saídas, ajustes, mínimos);
  * curva S (prevista × avanço real × custos reais), alertas e resumo semanal.

Os perfis são os da obra colaborativa (dono de obra, fiscalização, arquiteto, empresa, gestor).
Nenhum valor é estimado: quando faltam dados, a função devolve «indisponível» com o motivo.
O mesmo ficheiro serve o .pt e o .fr; os textos e referenciais de cada país estão em obra_gestao_txt.py.
"""
from __future__ import annotations

import re
import unicodedata
from datetime import date, timedelta
from typing import Iterable, Optional

from engines import obra_colab as oc
from engines import obra_gestao_txt as TX

DONO, FISCAL, ARQUITETO, EMPRESA, GESTOR = oc.DONO, oc.FISCAL, oc.ARQUITETO, oc.EMPRESA, oc.GESTOR
TODOS = (DONO, FISCAL, ARQUITETO, EMPRESA, GESTOR)

# ------------------------------------------------------------------ matriz de acessos
CAPS: dict[str, tuple[str, ...]] = {
    # diário de obra: escrito pela direção de obra, visado pela fiscalização, lido pelo dono e pelo arquiteto
    "diario.ver": (DONO, FISCAL, ARQUITETO, GESTOR),
    "diario.editar": (GESTOR,),
    "diario.visar": (FISCAL,),
    # qualidade, segurança e ambiente
    "qse.ver": (DONO, FISCAL, EMPRESA, GESTOR),
    "qse.criar": (FISCAL, EMPRESA, GESTOR),
    "qse.gerir": (FISCAL, GESTOR),
    # pedidos de esclarecimento
    "rfi.ver": TODOS,
    "rfi.criar": TODOS,
    "rfi.fechar": (FISCAL, GESTOR),
    # indicadores (curva S e alertas) — leitura
    "indicadores.ver": (DONO, FISCAL, GESTOR),
}

QSE_TIPOS = tuple(TX.QSE_TIPOS)
GRAVIDADES = ("baixa", "media", "alta", "critica")
ACAO_ESTADOS = ("aberta", "em_curso", "feita", "verificada")
CAMPOS_5W2H_OBRIGATORIOS = ("o_que", "porque", "quem", "onde", "quando", "como")


def can(roles: Iterable[str], cap: str) -> bool:
    allowed = CAPS.get(cap, ())
    return any(r in allowed for r in roles)


def capabilities(roles: Iterable[str]) -> dict[str, bool]:
    roles = tuple(roles)
    return {cap: can(roles, cap) for cap in CAPS}


def _impossivel(empresa_id: Optional[str]) -> str:
    return empresa_id or "__nenhuma__"


def qse_scope(roles: Iterable[str], empresa_id: Optional[str]) -> Optional[dict]:
    """Uma empresa só vê os registos que a envolvem (autora, visada ou responsável por uma ação)."""
    roles = set(roles)
    if roles & {GESTOR, DONO, FISCAL}:
        return None
    eid = _impossivel(empresa_id)
    return {"$or": [{"empresa_id": eid}, {"autor.empresa_id": eid}, {"acoes.quem_empresa_id": eid}]}


def qse_visivel(roles: Iterable[str], empresa_id: Optional[str], item: dict) -> bool:
    if qse_scope(roles, empresa_id) is None:
        return True
    eid = _impossivel(empresa_id)
    return (item.get("empresa_id") == eid or (item.get("autor") or {}).get("empresa_id") == eid
            or any(a.get("quem_empresa_id") == eid for a in item.get("acoes") or []))


def rfi_scope(roles: Iterable[str], empresa_id: Optional[str], actor_id: str) -> Optional[dict]:
    """Empresa: os seus pedidos, os que lhe são dirigidos e os partilhados com todos. Outros perfis: tudo,
    exceto os pedidos restritos entre uma empresa e outro destinatário que não os envolve."""
    roles = set(roles)
    if GESTOR in roles:
        return None
    if EMPRESA in roles:
        eid = _impossivel(empresa_id)
        return {"$or": [{"autor.empresa_id": eid}, {"destinatario.id": eid}, {"visibilidade": "todos"}]}
    perfis = [r for r in roles if r in (DONO, FISCAL, ARQUITETO)]
    return {"$or": [{"visibilidade": "todos"}, {"autor.id": actor_id}, {"destinatario.perfil": {"$in": perfis}},
                    {"destinatario.id": actor_id}]}


def rfi_pode_responder(roles: Iterable[str], empresa_id: Optional[str], actor_id: str, rfi: dict) -> bool:
    roles = set(roles)
    if GESTOR in roles or FISCAL in roles:
        return True
    dest = rfi.get("destinatario") or {}
    if dest.get("id") and dest["id"] in (actor_id, empresa_id):
        return True
    return bool(dest.get("perfil")) and dest["perfil"] in roles


# ------------------------------------------------------------------ utilitários
def norm(s: Optional[str]) -> str:
    s = unicodedata.normalize("NFKD", str(s or "")).encode("ascii", "ignore").decode().lower()
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", s)).strip()


def parse_date(s: Optional[str]) -> Optional[date]:
    try:
        return date.fromisoformat(str(s or "")[:10])
    except ValueError:
        return None


def semana_de(d: date) -> tuple[date, date]:
    inicio = d - timedelta(days=d.weekday())
    return inicio, inicio + timedelta(days=6)


def dias_uteis_entre(a: date, b: date) -> int:
    """Número de dias úteis (seg-sex) estritamente depois de a e até b inclusive."""
    n, d = 0, a
    while d < b:
        d += timedelta(days=1)
        if d.weekday() < 5:
            n += 1
    return n


# ------------------------------------------------------------------ meteorologia
def meteo_do_dia(daily: dict, dia: date) -> Optional[dict]:
    """Extrai o dia pedido da resposta «daily» do Open-Meteo. None se o dia não constar (nunca se inventa)."""
    times = daily.get("time") or []
    alvo = dia.isoformat()
    if alvo not in times:
        return None
    i = times.index(alvo)

    def col(k):
        v = daily.get(k) or []
        return v[i] if i < len(v) else None

    codigo = col("weather_code")
    out = {"fonte": "Open-Meteo", "codigo": codigo, "descricao": TX.METEO.get(codigo, "—") if codigo is not None else "—",
           "tmin": col("temperature_2m_min"), "tmax": col("temperature_2m_max"),
           "precipitacao_mm": col("precipitation_sum"), "vento_max_kmh": col("wind_speed_10m_max")}
    chuva = (out["precipitacao_mm"] or 0) >= 5
    vento = (out["vento_max_kmh"] or 0) >= 50
    gelo = out["tmin"] is not None and out["tmin"] <= 0
    trovoada = codigo in (95, 96, 99)
    out["alerta"] = TX.METEO_ALERTA if (chuva or vento or gelo or trovoada) else None
    return out


# ------------------------------------------------------------------ QSE
def acao_faltas(acao: dict) -> list[str]:
    """Campos 5W2H obrigatórios em falta (o «quanto» é facultativo mas, se indicado, tem de ser ≥ 0)."""
    faltas = [TX.CAMPOS_5W2H[k] for k in CAMPOS_5W2H_OBRIGATORIOS if not str(acao.get(k) or "").strip()]
    if acao.get("quando") and not parse_date(acao["quando"]):
        faltas.append(TX.CAMPOS_5W2H["quando"])
    q = acao.get("quanto")
    if q is not None and (not isinstance(q, (int, float)) or q < 0):
        faltas.append(TX.CAMPOS_5W2H["quanto"])
    return list(dict.fromkeys(faltas))


def acao_transicao(atual: str, novo: str, *, gestao: bool, responsavel: bool) -> bool:
    """Ciclo de uma ação: aberta → em curso → feita → verificada.

    O responsável (empresa) avança até «feita»; só a gestão (direção de obra / fiscalização) verifica,
    e pode devolver uma ação «feita» para «em curso» se a eficácia não for comprovada.
    """
    if atual == novo or novo not in ACAO_ESTADOS:
        return False
    if novo == "verificada":
        return gestao and atual == "feita"
    if atual == "verificada":
        return False
    if atual == "feita" and novo in ("em_curso", "aberta"):
        return gestao
    ordem = {"aberta": 0, "em_curso": 1, "feita": 2}
    return (gestao or responsavel) and ordem.get(novo, -1) > ordem.get(atual, -1)


def pode_fechar(item: dict, justificacao: str = "") -> bool:
    acoes = item.get("acoes") or []
    if item.get("tipo") in ("nao_conformidade", "incidente", "quase_acidente", "ambiente"):
        if acoes:
            return all(a.get("estado") == "verificada" for a in acoes) or bool(justificacao.strip())
        return bool(justificacao.strip())
    return True


def acoes_em_atraso(item: dict, hoje: date) -> list[dict]:
    out = []
    for a in item.get("acoes") or []:
        q = parse_date(a.get("quando"))
        if q and q < hoje and a.get("estado") not in ("feita", "verificada"):
            out.append(a)
    return out


def inspecao_resultado(checklist: list[dict]) -> dict:
    ok = sum(1 for c in checklist if c.get("resultado") == "ok")
    nok = [c for c in checklist if c.get("resultado") == "nok"]
    na = sum(1 for c in checklist if c.get("resultado") == "na")
    pendentes = sum(1 for c in checklist if c.get("resultado") not in ("ok", "nok", "na"))
    avaliados = ok + len(nok)
    return {"ok": ok, "nok": len(nok), "na": na, "pendentes": pendentes,
            "conformidade_pct": round(ok * 100 / avaliados, 1) if avaliados else None,
            "pontos_nok": [c.get("item") for c in nok]}


def checklist_modelo(chave: str) -> Optional[list[dict]]:
    m = TX.CHECKLISTS.get(chave)
    if not m:
        return None
    return [{"item": i, "resultado": None, "obs": ""} for i in m["itens"]]


# ------------------------------------------------------------------ stock
def stock_saldos(movimentos: Iterable[dict], minimos: Optional[dict] = None) -> list[dict]:
    minimos = minimos or {}
    g: dict[tuple[str, str], dict] = {}
    for m in movimentos:
        key = (norm(m.get("material")), norm(m.get("unidade")))
        r = g.setdefault(key, {"chave": "|".join(key), "material": m.get("material"), "unidade": m.get("unidade"),
                               "entradas": 0.0, "saidas": 0.0, "ajustes": 0.0, "saldo": 0.0, "ultimo": None})
        q = float(m.get("quantidade") or 0)
        tipo = m.get("tipo")
        if tipo == "entrada":
            r["entradas"] += q
            r["saldo"] += q
        elif tipo == "saida":
            r["saidas"] += q
            r["saldo"] -= q
        elif tipo == "ajuste":
            r["ajustes"] += q
            r["saldo"] += q
        d = m.get("data") or ""
        if not r["ultimo"] or d > r["ultimo"]:
            r["ultimo"] = d
    out = []
    for r in g.values():
        for k in ("entradas", "saidas", "ajustes", "saldo"):
            r[k] = round(r[k], 3)
        mn = minimos.get(r["chave"])
        r["minimo"] = mn
        r["abaixo_minimo"] = mn is not None and r["saldo"] < mn
        out.append(r)
    out.sort(key=lambda r: norm(r["material"]))
    return out


# ------------------------------------------------------------------ curva S
def _frac(d: date, ini: date, fim: date) -> float:
    if d < ini:
        return 0.0
    if d >= fim:
        return 1.0
    total = (fim - ini).days + 1
    return ((d - ini).days + 1) / total


def pesos_tarefas(tarefas: list[dict], lotes: list[dict]) -> tuple[dict, str]:
    """Peso de cada tarefa. Pelo custo previsto (ou venda) do lote correspondente se TODAS as tarefas
    têm um lote com valor; senão pela duração. Um lote partilhado por várias tarefas é dividido por igual."""
    por_lote = {}
    for lt in lotes or []:
        val = lt.get("cost_prev_ht") if lt.get("coverage", {}).get("complete") else None
        if val is None:
            val = lt.get("vente_ht")
        if val:
            por_lote[norm(lt.get("lot"))] = float(val)
    ligadas: dict[str, list[str]] = {}
    for t in tarefas:
        for chave in (norm(t.get("resource")), norm(t.get("name"))):
            if chave in por_lote:
                ligadas.setdefault(chave, []).append(t["id"])
                t["_lote"] = chave
                break
    if tarefas and por_lote and all(t.get("_lote") for t in tarefas):
        pesos = {t["id"]: por_lote[t["_lote"]] / len(ligadas[t["_lote"]]) for t in tarefas}
        modo = "custo"
    else:
        pesos = {t["id"]: float(max(1, int(t.get("duration") or 1))) for t in tarefas}
        modo = "duracao"
    tot = sum(pesos.values()) or 1.0
    for t in tarefas:
        t.pop("_lote", None)
    return {k: v / tot for k, v in pesos.items()}, modo


def curva_s(schedule: Optional[dict], baseline: Optional[dict], lotes: list[dict], hoje: date,
            snapshots: list[dict], custos: Optional[dict] = None) -> dict:
    """Curva S semanal.

    schedule = resultado de planning.compute_schedule (tarefas com start_date/end_date/progress);
    baseline = {"tasks": {id: end_date}} congelado no planeamento (se existir, a curva prevista usa-o);
    snapshots = [{data, avanco_pct}] avanço real registado dia a dia;
    custos = {"completo": bool, "orcamento_custo": float|None, "pontos": [(data, valor)]} custos reais datados.
    """
    if not schedule or not schedule.get("tasks"):
        return {"disponivel": False, "motivo": TX.CURVA["sem_planeamento"]}
    tarefas = [dict(t) for t in schedule["tasks"]]
    if not all(parse_date(t.get("start_date")) and parse_date(t.get("end_date")) for t in tarefas):
        return {"disponivel": False, "motivo": TX.CURVA["sem_datas"]}
    pesos, modo = pesos_tarefas(tarefas, lotes)
    base = (baseline or {}).get("tasks") or {}
    prev = {}
    for t in tarefas:
        ini, fim = parse_date(t["start_date"]), parse_date(t["end_date"])
        bf = parse_date(base.get(t["id"]))
        if bf:  # mantém a duração em dias de calendário e alinha o fim com a referência congelada
            ini, fim = bf - (fim - ini), bf
        prev[t["id"]] = (ini, fim)
    inicio = min(i for i, _ in prev.values())
    fim_prev = max(f for _, f in prev.values())
    fim_real = max(parse_date(t["end_date"]) for t in tarefas)
    ate = max(fim_prev, fim_real, hoje)
    avanco_hoje = round(sum(pesos[t["id"]] * min(100, max(0, float(t.get("progress") or 0))) for t in tarefas), 2)

    snaps = sorted(((parse_date(s.get("data")), float(s.get("avanco_pct") or 0)) for s in snapshots if parse_date(s.get("data"))),
                   key=lambda x: x[0])
    pts_custo = sorted(((parse_date(d), float(v)) for d, v in (custos or {}).get("pontos") or [] if parse_date(d)),
                       key=lambda x: x[0])
    bac = (custos or {}).get("orcamento_custo")
    custos_ok = bool(custos and custos.get("completo"))

    pontos = []
    d = inicio - timedelta(days=inicio.weekday())
    while True:
        dia = min(d + timedelta(days=6), ate)
        p = round(sum(pesos[tid] * _frac(dia, i, f) for tid, (i, f) in prev.items()) * 100, 2)
        real = None  # avanço real: só o que foi registado (instantâneos diários); nunca interpolado
        if d <= hoje <= d + timedelta(days=6):
            real = avanco_hoje
        elif dia < hoje:
            ant = [v for sd, v in snaps if sd <= dia]
            real = ant[-1] if ant else None
        custo = None
        if custos_ok and d <= hoje:
            limite = min(dia, hoje)
            custo = round(sum(v for cd, v in pts_custo if cd <= limite), 2)
        pontos.append({"semana": d.isoformat(), "data": dia.isoformat(), "previsto_pct": p, "real_pct": real,
                       "custo_real": custo,
                       "custo_real_pct": round(custo * 100 / bac, 2) if custo is not None and bac else None})
        if dia >= ate:
            break
        d += timedelta(days=7)

    previsto_hoje = round(sum(pesos[tid] * _frac(hoje, i, f) for tid, (i, f) in prev.items()) * 100, 2)
    spi = round(avanco_hoje / previsto_hoje, 2) if previsto_hoje > 0 else None
    custo_hoje = round(sum(v for cd, v in pts_custo if cd <= hoje), 2) if custos_ok else None
    cpi = None
    if custos_ok and bac and custo_hoje:
        cpi = round((avanco_hoje / 100 * bac) / custo_hoje, 2)
    notas = [TX.CURVA["ponderacao_custo"] if modo == "custo" else TX.CURVA["ponderacao_duracao"]]
    if custos is not None and not custos_ok:
        notas.append(TX.CURVA["custos_incompletos"])
    if custos_ok and not bac:
        notas.append(TX.CURVA["sem_orcamento"])
    return {"disponivel": True, "ponderacao": modo, "usa_referencia": bool(base), "inicio": inicio.isoformat(),
            "fim_previsto": fim_prev.isoformat(), "fim_atual": fim_real.isoformat(), "hoje": hoje.isoformat(),
            "previsto_hoje_pct": previsto_hoje, "real_hoje_pct": avanco_hoje,
            "desvio_pp": round(avanco_hoje - previsto_hoje, 2), "spi": spi, "cpi": cpi,
            "custo_real_hoje": custo_hoje, "orcamento_custo": bac, "pontos": pontos, "notas": notas}


# ------------------------------------------------------------------ alertas
def _fmt_eur(v: float) -> str:
    return f"{v:,.0f}".replace(",", " ")


def alertas(*, hoje: date, schedule: Optional[dict] = None, lotes: Optional[list[dict]] = None,
            qse: Iterable[dict] = (), rfis: Iterable[dict] = (), stock: Iterable[dict] = (),
            ultimo_diario: Optional[str] = None, diario_ativo: bool = False,
            docs_subs: Iterable[dict] = ()) -> list[dict]:
    A = TX.ALERTAS
    out: list[dict] = []

    def add(tipo, sev, texto, ref=None):
        out.append({"tipo": tipo, "severidade": sev, "severidade_label": TX.SEV[sev], "texto": texto, "ref": ref})

    for t in (schedule or {}).get("tasks") or []:
        fim, ini = parse_date(t.get("end_date")), parse_date(t.get("start_date"))
        prog = float(t.get("progress") or 0)
        if fim and fim < hoje and prog < 100:
            add("tarefa_atraso", "alta" if t.get("critical") else "media",
                A["tarefa_atraso"].format(nome=t.get("name"), dias=(hoje - fim).days), t.get("id"))
        elif t.get("critical") and ini and ini < hoje and prog == 0 and not t.get("actual_start"):
            add("tarefa_critica", "alta", A["tarefa_critica"].format(nome=t.get("name"), data=ini.isoformat()), t.get("id"))
    for lt in lotes or []:
        prev, real = lt.get("cost_prev_ht"), lt.get("real_cost_ht")
        if prev and real is not None and real > prev:
            pct = round((real - prev) * 100 / prev, 1)
            add("lote_derrapagem", "critica" if pct >= 15 else "alta",
                A["lote_derrapagem"].format(lote=lt.get("lot"), real=_fmt_eur(real), prev=_fmt_eur(prev), pct=pct), lt.get("lot"))
    for it in qse:
        if it.get("estado") == "fechado":
            continue
        if it.get("tipo") == "nao_conformidade" and it.get("gravidade") == "critica":
            add("nc_critica", "critica", A["nc_critica"].format(numero=it.get("numero"), titulo=it.get("titulo")), it.get("item_id"))
        for a in acoes_em_atraso(it, hoje):
            add("nc_atraso", "alta", A["nc_atraso"].format(numero=it.get("numero"), titulo=it.get("titulo"),
                                                          acao=a.get("o_que"), data=a.get("quando")), it.get("item_id"))
        d = parse_date(it.get("data"))
        if it.get("tipo") == "incidente" and d and (hoje - d).days <= 7:
            add("acidente", "critica", A["acidente"].format(data=d.isoformat(), titulo=it.get("titulo")), it.get("item_id"))
    for r in rfis:
        p = parse_date(r.get("prazo"))
        if r.get("estado") == "aberto" and p and p < hoje:
            add("rfi_atraso", "media", A["rfi_atraso"].format(numero=r.get("numero"), assunto=r.get("assunto"), prazo=p.isoformat()),
                r.get("rfi_id"))
    for s in stock:
        if s.get("abaixo_minimo"):
            add("stock_minimo", "media", A["stock_minimo"].format(material=s.get("material"), saldo=s.get("saldo"),
                                                                 unidade=s.get("unidade") or "", minimo=s.get("minimo")), s.get("chave"))
    if diario_ativo:
        ult = parse_date(ultimo_diario)
        if ult is None or dias_uteis_entre(ult, hoje) > 3:
            add("diario_em_falta", "info", A["diario_em_falta"].format(dias=3))
    for d in docs_subs:
        v = parse_date(d.get("validade"))
        if v and hoje <= v <= hoje + timedelta(days=15):
            add("doc_sub_expira", "media", A["doc_sub_expira"].format(doc=d.get("label"), empresa=d.get("empresa"), data=v.isoformat()))
    ordem = {"critica": 0, "alta": 1, "media": 2, "info": 3}
    out.sort(key=lambda a: ordem[a["severidade"]])
    return out


# ------------------------------------------------------------------ resumo semanal (determinístico)
def dados_semana(diarios: list[dict], qse: list[dict], rfis: list[dict], de: date, ate: date, hoje: date) -> dict:
    sem = [d for d in diarios if de <= (parse_date(d.get("data")) or date.min) <= ate]
    horas = round(sum(float((d.get("efetivo_auto") or {}).get("horas") or 0) for d in sem), 1)
    fotos = sum(len(d.get("fotos") or []) for d in sem)
    trabalhos = [{"data": d["data"], "texto": d.get("trabalhos")} for d in sorted(sem, key=lambda x: x["data"]) if d.get("trabalhos")]
    q_sem = [q for q in qse if de <= (parse_date(q.get("data")) or date.min) <= ate]
    abertos = [q for q in qse if q.get("estado") != "fechado" and q.get("tipo") == "nao_conformidade"]
    r_abertos = [r for r in rfis if r.get("estado") == "aberto"]
    r_atraso = [r for r in r_abertos if (parse_date(r.get("prazo")) or date.max) < hoje]
    return {
        "de": de.isoformat(), "ate": ate.isoformat(), "dias_diario": len(sem), "horas": horas, "fotos": fotos,
        "trabalhos": trabalhos,
        "meteo": [{"data": d["data"], **(d.get("meteo") or {})} for d in sem if d.get("meteo")],
        "nc_abertas": len(abertos),
        "acidentes": sum(1 for q in q_sem if q.get("tipo") == "incidente"),
        "quase_acidentes": sum(1 for q in q_sem if q.get("tipo") == "quase_acidente"),
        "dds": sum(1 for q in q_sem if q.get("tipo") == "dialogo_seguranca"),
        "qse_semana": [{"numero": q.get("numero"), "tipo": TX.QSE_TIPOS.get(q.get("tipo"), q.get("tipo")),
                        "titulo": q.get("titulo"), "gravidade": q.get("gravidade"), "estado": q.get("estado")} for q in q_sem],
        "rfi_abertos": len(r_abertos), "rfi_atraso": len(r_atraso),
        "rfi_lista": [{"numero": r.get("numero"), "assunto": r.get("assunto"), "prazo": r.get("prazo")} for r in r_abertos],
    }


def resumo_texto(d: dict, alertas_: list[dict], curva: Optional[dict] = None) -> str:
    R = TX.RELATORIO
    linhas = [R["semana"].format(de=d["de"], ate=d["ate"]), ""]
    linhas.append(R["avanco"])
    if curva and curva.get("disponivel"):
        linhas.append(f"- {curva['real_hoje_pct']} % / {curva['previsto_hoje_pct']} % ({curva['desvio_pp']:+} pp)")
    linhas.append("- " + R["dias_diario"].format(n=d["dias_diario"], h=d["horas"], f=d["fotos"]))
    for t in d["trabalhos"][:7]:
        linhas.append(f"- {t['data']}: {str(t['texto']).strip()[:240]}")
    linhas += ["", R["qse"], "- " + R["nc_abertas"].format(n=d["nc_abertas"], i=d["acidentes"], q=d["quase_acidentes"], d=d["dds"])]
    linhas += ["", R["rfi"], "- " + R["rfi_abertos"].format(n=d["rfi_abertos"], a=d["rfi_atraso"])]
    if alertas_:
        linhas += ["", R["alertas"]] + [f"- [{a['severidade_label']}] {a['texto']}" for a in alertas_[:8]]
    return "\n".join(linhas)
