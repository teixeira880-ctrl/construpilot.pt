"""Obra colaborativa (assinatura por obra) — regras puras, sem base de dados nem rede.

Quatro intervenientes por obra: dono de obra, fiscalização, arquiteto e empresas.
Este módulo concentra:
  * a matriz de acessos (quem pode fazer o quê, e o que cada um vê);
  * o controlo de um pedido de aprovação de subempreiteiro face ao regulamento do dono de obra;
  * o controlo de um auto de medição face ao contrato, aos autos anteriores e ao avanço registado;
  * o rascunho da ata semanal (pontos em aberto retomados, atrasos e vistos pendentes).

Todas as verificações aqui são determinísticas e explicadas ponto a ponto: nenhum valor é
estimado. As comparações por IA (documento contra documento) vivem na rota e só acrescentam
observações; nunca substituem estes controlos.
"""
from __future__ import annotations

from datetime import date
from typing import Iterable, Optional

# ------------------------------------------------------------------ perfis
DONO = "dono_obra"
FISCAL = "fiscalizacao"
ARQUITETO = "arquiteto"
EMPRESA = "empresa"
GESTOR = "gestor"  # titular da conta ConstruPilot que abriu a obra

ROLES = (DONO, FISCAL, ARQUITETO, EMPRESA)
ADMIN_ROLES = (DONO, FISCAL, ARQUITETO, GESTOR)
ROLE_LABELS = {DONO: "Dono de obra", FISCAL: "Fiscalização", ARQUITETO: "Arquiteto",
               EMPRESA: "Empresa", GESTOR: "Gestor da obra"}

# Papel herdado do portal existente (convites «client» / «subcontractor»).
LEGACY_ROLE = {"client": DONO, "subcontractor": EMPRESA}


def role_of_participant(p: dict) -> str:
    r = p.get("colab_role")
    if r in ROLES:
        return r
    return LEGACY_ROLE.get(p.get("role"), EMPRESA)


# ------------------------------------------------------------------ matriz de acessos
# Cada capacidade lista os perfis autorizados. «own» = a empresa só atua/vê o que é seu.
CAPS: dict[str, tuple[str, ...]] = {
    # caixa de planos
    "planos.ver": (DONO, FISCAL, ARQUITETO, EMPRESA, GESTOR),
    "planos.carregar": (DONO, FISCAL, ARQUITETO, EMPRESA, GESTOR),
    "planos.modificar": (DONO, FISCAL, ARQUITETO, GESTOR),
    "planos.anotar": (DONO, FISCAL, ARQUITETO, GESTOR),
    "planos.visto": (FISCAL, ARQUITETO),
    "planos.comparar": (DONO, FISCAL, ARQUITETO, GESTOR),
    # aprovação de subempreiteiros
    "subs.submeter": (EMPRESA,),
    "subs.ver": (DONO, FISCAL, EMPRESA, GESTOR),
    "subs.decidir": (DONO,),
    "subs.regulamento": (DONO, GESTOR),
    # autos de medição
    "autos.carregar": (EMPRESA,),
    "autos.ver": (DONO, FISCAL, EMPRESA, GESTOR),
    "autos.validar_fiscal": (FISCAL,),
    "autos.validar_dono": (DONO,),
    "contratos.gerir": (DONO, GESTOR),
    "contratos.ver": (DONO, FISCAL, EMPRESA, GESTOR),
    # planeamento
    "cronograma.carregar": (EMPRESA,),
    "cronograma.ver": (DONO, FISCAL, ARQUITETO, EMPRESA, GESTOR),
    "cronograma.registar_avanco": (FISCAL,),
    # atas
    "atas.ver": (DONO, FISCAL, ARQUITETO, EMPRESA, GESTOR),
    "atas.editar": (FISCAL,),
    # intervenientes
    "intervenientes.gerir": (GESTOR,),
}

# Recursos em que uma empresa só vê os seus próprios registos (ponto crítico do caderno).
OWN_ONLY_FOR_EMPRESA = ("subs", "autos", "contratos", "cronograma")


def can(role: str, cap: str) -> bool:
    return role in CAPS.get(cap, ())


def scope_filter(role: str, resource: str, empresa_id: Optional[str]) -> Optional[dict]:
    """Filtro a aplicar à listagem de um recurso. None = tudo; dict = filtro Mongo.

    Uma empresa sem identificador nunca recebe um filtro vazio: devolve-se um filtro impossível.
    """
    if role != EMPRESA or resource not in OWN_ONLY_FOR_EMPRESA:
        return None
    return {"empresa_id": empresa_id or "__nenhuma__"}


def may_see_record(role: str, resource: str, empresa_id: Optional[str], record: dict) -> bool:
    f = scope_filter(role, resource, empresa_id)
    return f is None or record.get("empresa_id") == f["empresa_id"]


def capabilities(role: str) -> dict[str, bool]:
    return {cap: can(role, cap) for cap in CAPS}


# ------------------------------------------------------------------ regulamento de subempreiteiros
# Modelo de partida (Portugal). O dono de obra pode ativar/desativar, tornar obrigatório e acrescentar.
DEFAULT_REGULAMENTO = [
    {"key": "alvara_impic", "label": "Alvará ou certificado IMPIC válido", "obrigatorio": True, "tem_validade": True},
    {"key": "nao_divida_at", "label": "Certidão de não dívida à Autoridade Tributária", "obrigatorio": True, "tem_validade": True},
    {"key": "nao_divida_ss", "label": "Certidão de não dívida à Segurança Social", "obrigatorio": True, "tem_validade": True},
    {"key": "seguro_at", "label": "Seguro de acidentes de trabalho (apólice e recibo)", "obrigatorio": True, "tem_validade": True},
    {"key": "seguro_rc", "label": "Seguro de responsabilidade civil", "obrigatorio": True, "tem_validade": True},
    {"key": "lista_trabalhadores", "label": "Lista de trabalhadores afetos à obra", "obrigatorio": True, "tem_validade": False},
    {"key": "aptidao_medica", "label": "Fichas de aptidão médica dos trabalhadores", "obrigatorio": False, "tem_validade": True},
    {"key": "adesao_pss", "label": "Declaração de adesão ao Plano de Segurança e Saúde", "obrigatorio": True, "tem_validade": False},
    {"key": "contrato_subempreitada", "label": "Contrato de subempreitada assinado", "obrigatorio": False, "tem_validade": False},
]


def _as_date(s: Optional[str]) -> Optional[date]:
    try:
        return date.fromisoformat((s or "")[:10])
    except ValueError:
        return None


def check_sub_request(pedido: dict, regulamento: Iterable[dict], *, hoje: date,
                      valor_contrato_empresa: Optional[float] = None,
                      limite_subcontratacao_pct: Optional[float] = None) -> dict:
    """Confronta um pedido com o regulamento do dono de obra.

    pedido = {documentos: [{key, validade}], valor}
    Devolve {conforme, pontos: [{key, label, estado, detalhe}], em_falta, expirados, a_expirar}.
    Estados de um ponto: ok | em_falta | expirado | a_expirar | sem_validade | opcional_em_falta | excede_limite.
    """
    docs = {d.get("key"): d for d in (pedido.get("documentos") or []) if d.get("key")}
    pontos: list[dict] = []
    for req in regulamento:
        if req.get("ativo") is False:
            continue
        key, label = req["key"], req.get("label") or req["key"]
        obrig = bool(req.get("obrigatorio"))
        d = docs.get(key)
        if not d:
            pontos.append({"key": key, "label": label, "obrigatorio": obrig,
                           "estado": "em_falta" if obrig else "opcional_em_falta",
                           "detalhe": "Documento não entregue."})
            continue
        if req.get("tem_validade"):
            val = _as_date(d.get("validade"))
            if not val:
                pontos.append({"key": key, "label": label, "obrigatorio": obrig, "estado": "sem_validade",
                               "detalhe": "Documento entregue sem data de validade."})
                continue
            dias = (val - hoje).days
            if dias < 0:
                pontos.append({"key": key, "label": label, "obrigatorio": obrig, "estado": "expirado",
                               "detalhe": f"Validade terminada em {val.isoformat()} (há {-dias} dia(s))."})
                continue
            if dias <= 30:
                pontos.append({"key": key, "label": label, "obrigatorio": obrig, "estado": "a_expirar",
                               "detalhe": f"Válido até {val.isoformat()} ({dias} dia(s))."})
                continue
            pontos.append({"key": key, "label": label, "obrigatorio": obrig, "estado": "ok",
                           "detalhe": f"Válido até {val.isoformat()}."})
        else:
            pontos.append({"key": key, "label": label, "obrigatorio": obrig, "estado": "ok", "detalhe": "Entregue."})

    if limite_subcontratacao_pct is not None and valor_contrato_empresa:
        valor = float(pedido.get("valor") or 0)
        pct = round(100 * valor / float(valor_contrato_empresa), 2)
        if pct > float(limite_subcontratacao_pct):
            pontos.append({"key": "limite_subcontratacao", "label": "Limite de subcontratação", "obrigatorio": True,
                           "estado": "excede_limite",
                           "detalhe": f"Subempreitada de {valor:.2f} € = {pct} % do contrato da empresa "
                                      f"(limite do regulamento: {float(limite_subcontratacao_pct):g} %)."})
        else:
            pontos.append({"key": "limite_subcontratacao", "label": "Limite de subcontratação", "obrigatorio": True,
                           "estado": "ok", "detalhe": f"{pct} % do contrato (limite {float(limite_subcontratacao_pct):g} %)."})

    bloqueantes = {"em_falta", "expirado", "sem_validade", "excede_limite"}
    falhas = [p for p in pontos if p["obrigatorio"] and p["estado"] in bloqueantes]
    return {
        "conforme": not falhas,
        "pontos": pontos,
        "em_falta": [p["label"] for p in pontos if p["estado"] == "em_falta"],
        "expirados": [p["label"] for p in pontos if p["estado"] == "expirado"],
        "a_expirar": [p["label"] for p in pontos if p["estado"] == "a_expirar"],
        "motivos": [f"{p['label']}: {p['detalhe']}" for p in falhas],
        "sugestao": "aprovar" if not falhas else "aprovar_com_reservas_ou_recusar",
    }


SUB_DECISIONS = ("aprovado", "aprovado_com_reservas", "recusado")


def validate_sub_decision(decisao: str, reservas: str, motivos: str) -> Optional[str]:
    """Devolve a mensagem de erro, ou None se a decisão estiver completa."""
    if decisao not in SUB_DECISIONS:
        return "Decisão desconhecida."
    if decisao == "aprovado_com_reservas" and not (reservas or "").strip():
        return "Indique as reservas (o que falta e até quando)."
    if decisao == "recusado" and not (motivos or "").strip():
        return "Indique os motivos da recusa."
    return None


# ------------------------------------------------------------------ autos de medição
TOL_EUR = 0.01       # tolerância de arredondamento por linha
TOL_QTD = 1e-6


def _r2(x: float) -> float:
    return round(float(x) + 1e-9, 2)


def check_auto(auto: dict, contrato: dict, anteriores: list[dict], *,
               avanco_registado_pct: Optional[float] = None, tolerancia_avanco_pct: float = 5.0) -> dict:
    """Controla um auto de medição.

    contrato = {linhas: [{ref, designacao, unidade, quantidade, preco_unitario}]}
    auto     = {numero, periodo, linhas: [{ref, quantidade_periodo, preco_unitario?, valor?}], total_declarado?}
    anteriores = autos já validados (ou em validação) da mesma empresa, mesma estrutura.

    Devolve as linhas recalculadas, os totais e a lista de incoerências, cada uma com gravidade
    «bloqueante» ou «aviso» e a explicação em português.
    """
    linhas_contrato = {str(l.get("ref")): l for l in (contrato.get("linhas") or [])}
    acumulado_anterior: dict[str, float] = {}
    for a in anteriores:
        for l in a.get("linhas") or []:
            ref = str(l.get("ref"))
            acumulado_anterior[ref] = acumulado_anterior.get(ref, 0.0) + float(l.get("quantidade_periodo") or 0)

    incoerencias: list[dict] = []

    def inc(gravidade: str, codigo: str, texto: str, ref: Optional[str] = None) -> None:
        incoerencias.append({"gravidade": gravidade, "codigo": codigo, "ref": ref, "texto": texto})

    vistos: set[str] = set()
    linhas_out: list[dict] = []
    total_periodo = 0.0
    for l in auto.get("linhas") or []:
        ref = str(l.get("ref"))
        qtd = float(l.get("quantidade_periodo") or 0)
        if ref in vistos:
            inc("bloqueante", "linha_duplicada", f"O artigo {ref} aparece mais de uma vez no auto.", ref)
            continue
        vistos.add(ref)
        c = linhas_contrato.get(ref)
        if not c:
            inc("bloqueante", "fora_contrato", f"O artigo {ref} não existe no orçamento contratado "
                "(trabalho a mais: exige adicional aprovado).", ref)
            pu = float(l.get("preco_unitario") or 0)
            valor = _r2(qtd * pu)
            linhas_out.append({"ref": ref, "designacao": l.get("designacao") or "", "unidade": l.get("unidade") or "",
                               "quantidade_contrato": None, "preco_unitario": pu, "quantidade_anterior": 0.0,
                               "quantidade_periodo": qtd, "quantidade_acumulada": qtd, "pct_acumulado": None,
                               "valor_periodo": valor, "fora_contrato": True})
            total_periodo += valor
            continue
        pu_c = float(c.get("preco_unitario") or 0)
        q_c = float(c.get("quantidade") or 0)
        if l.get("preco_unitario") is not None and abs(float(l["preco_unitario"]) - pu_c) > 1e-9:
            inc("bloqueante", "preco_diferente", f"Artigo {ref}: preço unitário {float(l['preco_unitario']):.2f} € "
                f"diferente do contratado ({pu_c:.2f} €).", ref)
        if qtd < -TOL_QTD:
            inc("aviso", "quantidade_negativa", f"Artigo {ref}: quantidade negativa no período ({qtd:g}) — "
                "confirmar se é uma correção de auto anterior.", ref)
        ant = acumulado_anterior.get(ref, 0.0)
        acum = ant + qtd
        if acum > q_c + TOL_QTD:
            inc("bloqueante", "excede_contrato", f"Artigo {ref}: acumulado {acum:g} {c.get('unidade') or ''} "
                f"excede a quantidade contratada ({q_c:g}). Excesso: {acum - q_c:g}.", ref)
        valor = _r2(qtd * pu_c)
        if l.get("valor") is not None and abs(float(l["valor"]) - valor) > TOL_EUR:
            inc("bloqueante", "valor_linha", f"Artigo {ref}: valor declarado {float(l['valor']):.2f} € ≠ "
                f"quantidade × preço = {valor:.2f} €.", ref)
        linhas_out.append({"ref": ref, "designacao": c.get("designacao") or "", "unidade": c.get("unidade") or "",
                           "quantidade_contrato": q_c, "preco_unitario": pu_c, "quantidade_anterior": ant,
                           "quantidade_periodo": qtd, "quantidade_acumulada": acum,
                           "pct_acumulado": round(100 * acum / q_c, 2) if q_c else None,
                           "valor_periodo": valor, "fora_contrato": False})
        total_periodo += valor

    total_periodo = _r2(total_periodo)
    if auto.get("total_declarado") is not None and abs(float(auto["total_declarado"]) - total_periodo) > TOL_EUR:
        inc("bloqueante", "total_auto", f"Total declarado {float(auto['total_declarado']):.2f} € ≠ soma das linhas "
            f"{total_periodo:.2f} €.")

    total_contrato = _r2(sum(float(l.get("quantidade") or 0) * float(l.get("preco_unitario") or 0)
                             for l in linhas_contrato.values()))
    total_anterior = _r2(sum(float(l.get("quantidade_periodo") or 0)
                             * float((linhas_contrato.get(str(l.get("ref"))) or {}).get("preco_unitario") or 0)
                             for a in anteriores for l in (a.get("linhas") or [])))
    total_acumulado = _r2(total_anterior + sum(x["valor_periodo"] for x in linhas_out if not x["fora_contrato"]))
    pct_financeiro = round(100 * total_acumulado / total_contrato, 2) if total_contrato else None

    if not (auto.get("linhas") or []):
        inc("bloqueante", "auto_vazio", "O auto não tem nenhuma linha.")
    if any(str(a.get("periodo") or "") == str(auto.get("periodo") or "") and a.get("periodo") for a in anteriores):
        inc("bloqueante", "periodo_repetido", f"Já existe um auto desta empresa para o período {auto.get('periodo')}.")
    numeros = sorted(int(a.get("numero") or 0) for a in anteriores)
    esperado = (numeros[-1] + 1) if numeros else 1
    if auto.get("numero") is not None and int(auto["numero"]) != esperado:
        inc("aviso", "numeracao", f"Numeração: este auto tem o n.º {auto['numero']}, o seguinte esperado é o n.º {esperado}.")

    if avanco_registado_pct is not None and pct_financeiro is not None:
        desvio = round(pct_financeiro - float(avanco_registado_pct), 2)
        if desvio > tolerancia_avanco_pct:
            inc("bloqueante", "avanco", f"Faturação acumulada de {pct_financeiro} % do contrato, mas o avanço físico "
                f"registado pela fiscalização é de {float(avanco_registado_pct):g} % (desvio de {desvio} pontos, "
                f"tolerância {tolerancia_avanco_pct:g}).")
        elif desvio < -3 * tolerancia_avanco_pct:
            inc("aviso", "subfaturacao", f"Faturação acumulada ({pct_financeiro} %) muito abaixo do avanço físico "
                f"registado ({float(avanco_registado_pct):g} %).")
    elif avanco_registado_pct is None:
        inc("aviso", "sem_avanco", "A fiscalização ainda não registou o avanço desta empresa: "
            "a conformidade com o avanço da obra não pôde ser verificada.")

    bloqueantes = [i for i in incoerencias if i["gravidade"] == "bloqueante"]
    return {
        "linhas": linhas_out,
        "total_periodo": total_periodo,
        "total_anterior": total_anterior,
        "total_acumulado": total_acumulado,
        "total_contrato": total_contrato,
        "pct_financeiro": pct_financeiro,
        "avanco_registado_pct": avanco_registado_pct,
        "incoerencias": incoerencias,
        "conforme": not bloqueantes,
        "resumo": ("Auto conforme com o orçamento contratado." if not incoerencias else
                   f"{len(bloqueantes)} incoerência(s) bloqueante(s) e "
                   f"{len(incoerencias) - len(bloqueantes)} aviso(s)."),
    }


# Circuito de validação: empresa submete → fiscalização → dono de obra.
AUTO_STATES = ("submetido", "validado_fiscalizacao", "rejeitado_fiscalizacao", "validado", "rejeitado_dono")


def next_auto_state(estado: str, role: str, aprovar: bool) -> Optional[str]:
    """Estado seguinte, ou None se este perfil não pode decidir neste momento."""
    if role == FISCAL and estado == "submetido":
        return "validado_fiscalizacao" if aprovar else "rejeitado_fiscalizacao"
    if role == DONO and estado == "validado_fiscalizacao":
        return "validado" if aprovar else "rejeitado_dono"
    return None


AUTOS_QUE_CONTAM = ("submetido", "validado_fiscalizacao", "validado")  # entram no acumulado anterior


# ------------------------------------------------------------------ planeamento
def task_delay_days(tarefa: dict, hoje: date) -> int:
    """Dias de atraso de uma tarefa face ao seu fim previsto, com base no avanço registado."""
    fim = _as_date(tarefa.get("fim"))
    pct = float(tarefa.get("avanco_pct") or 0)
    if not fim or pct >= 100:
        return 0
    return max(0, (hoje - fim).days)


def expected_pct(tarefa: dict, hoje: date) -> Optional[float]:
    ini, fim = _as_date(tarefa.get("inicio")), _as_date(tarefa.get("fim"))
    if not ini or not fim or fim < ini:
        return None
    if hoje <= ini:
        return 0.0
    if hoje >= fim:
        return 100.0
    return round(100 * (hoje - ini).days / max(1, (fim - ini).days), 1)


def cronograma_summary(tarefas: list[dict], hoje: date) -> dict:
    out = []
    for t in tarefas:
        esperado = expected_pct(t, hoje)
        real = float(t.get("avanco_pct") or 0)
        atraso = task_delay_days(t, hoje)
        em_atraso = atraso > 0 or (esperado is not None and real + 10 < esperado)
        out.append({**t, "esperado_pct": esperado, "atraso_dias": atraso, "em_atraso": bool(em_atraso)})
    pesos = [max(1, ((_as_date(t.get("fim")) or hoje) - (_as_date(t.get("inicio")) or hoje)).days) for t in tarefas]
    total = sum(pesos)
    avanco = round(sum(float(t.get("avanco_pct") or 0) * p for t, p in zip(tarefas, pesos)) / total, 1) if total else None
    return {"tarefas": out, "avanco_pct": avanco, "em_atraso": sum(1 for t in out if t["em_atraso"])}


# ------------------------------------------------------------------ ata semanal
ATA_ESTADOS = ("", "atraso", "importante", "memoria")
ATA_ESTADO_LABEL = {"": "", "atraso": "Atraso", "importante": "Ponto importante", "memoria": "Para memória"}


def draft_ata(numero: int, anterior: Optional[dict], empresas: list[dict], cronogramas: dict[str, dict],
              vistos_pendentes: dict[str, list[str]], autos_pendentes: dict[str, int]) -> list[dict]:
    """Linhas propostas para a ata n.º `numero`.

    - retoma os pontos em aberto da ata anterior (conservando a ata de origem);
    - acrescenta, por empresa, as tarefas em atraso, os planos à espera de visto e os autos por validar.
    Nada é inventado: cada linha automática indica a sua fonte em `fonte`.
    """
    linhas: list[dict] = []
    for l in (anterior or {}).get("linhas") or []:
        if l.get("fechado"):
            continue
        linhas.append({"empresa_id": l.get("empresa_id"), "ponto": l.get("ponto") or "",
                       "ata_origem": l.get("ata_origem") or (anterior or {}).get("numero"),
                       "estado": l.get("estado") or "", "fechado": False, "fonte": "ata_anterior"})
    for e in empresas:
        eid = e["empresa_id"]
        for t in (cronogramas.get(eid) or {}).get("tarefas") or []:
            if t.get("em_atraso"):
                dias = t.get("atraso_dias") or 0
                extra = f" ({dias} dia(s) após o fim previsto)" if dias else " (avanço abaixo do previsto)"
                linhas.append({"empresa_id": eid, "ponto": f"Tarefa «{t.get('titulo')}» em atraso{extra}: "
                               f"{float(t.get('avanco_pct') or 0):g} % realizado.",
                               "ata_origem": numero, "estado": "atraso", "fechado": False, "fonte": "cronograma"})
        for titulo in vistos_pendentes.get(eid) or []:
            linhas.append({"empresa_id": eid, "ponto": f"Plano «{titulo}» a aguardar visto.",
                           "ata_origem": numero, "estado": "importante", "fechado": False, "fonte": "caixa_planos"})
        n = autos_pendentes.get(eid) or 0
        if n:
            linhas.append({"empresa_id": eid, "ponto": f"{n} auto(s) de medição a aguardar validação.",
                           "ata_origem": numero, "estado": "memoria", "fechado": False, "fonte": "autos"})
    # sem duplicados (mesma empresa + mesmo texto)
    seen, unique = set(), []
    for l in linhas:
        k = (l["empresa_id"], l["ponto"])
        if k not in seen:
            seen.add(k)
            unique.append(l)
    return unique


def ata_for_role(ata: dict, role: str, empresa_id: Optional[str]) -> dict:
    """Uma empresa só lê os pontos gerais e os seus; os outros perfis leem tudo."""
    if role != EMPRESA:
        return ata
    linhas = [l for l in ata.get("linhas") or [] if l.get("empresa_id") in (None, "", empresa_id)]
    return {**ata, "linhas": linhas}
