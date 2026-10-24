"""Assistente ↔ motor IA de opções (programa /missions), versão PT.

Três ferramentas dão ao Assistente o controlo do motor: ler as opções e as peças da conta, lançar um
programa (resumo + fila, executado em segundo plano pelo worker dos agentes) e acompanhar o seu progresso.
O pedido do profissional na conversa vale como validação da seleção; o motor só executa as opções
passadas, não acrescenta nenhuma dependência, e nenhuma opção envia, paga ou expede o que quer que seja
(os orçamentos ficam em rascunho).
"""
from __future__ import annotations

from fastapi import HTTPException

from core.db import db

_S = {"type": "string"}
_IDS = {"type": "array", "items": _S}

MISSION_TOOLS = [
    {"type": "function", "name": "programme_ia_options", "strict": True,
     "description": "Lista as opções do motor IA de opções acessíveis a esta conta (plantas, medição, plantas de eletricidade RTIEBT / canalização DR 23/95, "
                    "orçamento em rascunho, planeamento, processo PDF, ligação de partilha inativa), com as dependências e as peças exigidas, bem como as plantas e "
                    "os processos de obra da conta (identificadores a passar a lancer_programme_ia). Chamar antes de lançar um programa.",
     "parameters": {"type": "object", "additionalProperties": False, "properties": {"chantier_id": {"type": ["string", "null"],
                    "description": "limitar as plantas a este processo de obra"}}, "required": ["chantier_id"]}},
    {"type": "function", "name": "lancer_programme_ia", "strict": True,
     "description": "Lança em segundo plano um programa do motor IA de opções nas plantas / no processo indicados. Usa só "
                    "opções pedidas ou aceites pelo profissional nesta conversa, e assinala tu mesmo as dependências "
                    "que ele aceitou (ex. medição antes do orçamento). Os entregáveis são produzidos sem ação dele; nada é enviado "
                    "ao cliente (orçamento em rascunho). Devolve o identificador do programa e a ligação de acompanhamento.",
     "parameters": {"type": "object", "additionalProperties": False, "properties": {
         "options": _IDS, "plan_ids": _IDS, "chantier_id": {"type": ["string", "null"]},
         "note": {"type": "string", "description": "instrução livre do profissional, copiada para o programa"}},
         "required": ["options", "plan_ids", "chantier_id", "note"]}},
    {"type": "function", "name": "suivre_programme_ia", "strict": True,
     "description": "Dá o estado de um programa do motor IA (em fila, em curso, terminado), o estado de cada opção, a sua síntese e "
                    "as ligações dos entregáveis. Sem identificador: os últimos programas da conta.",
     "parameters": {"type": "object", "additionalProperties": False, "properties": {"run_id": {"type": ["string", "null"]}},
                    "required": ["run_id"]}},
]
MISSION_TOOL_NAMES = {t["name"] for t in MISSION_TOOLS}

MISSION_INSTRUCTIONS = (
    "Motor IA de opções: quando o profissional pede uma análise de plantas, uma medição, plantas de eletricidade / canalização, "
    "um orçamento em rascunho, um planeamento, um processo PDF ou uma ligação de partilha nas suas plantas, chama programme_ia_options e depois lancer_programme_ia sem "
    "voltar a pedir confirmação se o pedido for claro (o pedido vale como validação); se faltar uma planta ou uma dependência, "
    "propõe-na numa frase. Acompanha depois o programa com suivre_programme_ia e apresenta as sínteses e as ligações. "
    "Encadeia por iniciativa própria os cálculos úteis (ferramentas de notas de cálculo) sobre os resultados, mas nunca envias, assinas, pagas nem "
    "expedes nada: essas ações ficam um clique do profissional. A ligação de partilha é criada inativa: diz-lhe que "
    "a ative ele próprio na página do programa, e nunca transmitas o endereço a terceiros."
)


def _link(run_id: str) -> str:
    return f"/missions?run={run_id}"


async def _options(args: dict, user: dict) -> dict:
    from routes.agents import _authorize_agent
    from routes.missions import _allowed_catalog, _public_option
    await _authorize_agent("mission", user)
    uid = user["user_id"]
    catalog = await _allowed_catalog(user)
    q = {"user_id": uid, "trashed_at": None}
    if args.get("chantier_id"):
        q["chantier_id"] = args["chantier_id"]
    plans = await db.plans_takeoff.find(q, {"_id": 0, "plan_id": 1, "filename": 1, "chantier_id": 1, "created_at": 1}) \
        .sort("created_at", -1).to_list(30)
    chantiers = await db.chantiers.find({"user_id": uid}, {"_id": 0, "chantier_id": 1, "name": 1, "city": 1, "status": 1}) \
        .sort("updated_at", -1).to_list(20)
    return {"ok": True, "options": [_public_option(s) for s in catalog.values()], "plans": plans, "chantiers": chantiers}


async def _launch(args: dict, user: dict) -> dict:
    from routes.agents import ExecIn, launch_run
    from routes.missions import MissionIn, propose
    body = MissionIn(options=args["options"], plan_ids=args.get("plan_ids") or [], chantier_id=args.get("chantier_id") or None,
                     note=(args.get("note") or "")[:1000])
    try:
        run = (await propose(body, user=user))["run"]
        await launch_run(run["run_id"], ExecIn(), user=user)
    except HTTPException as exc:
        return {"ok": False, "error": str(exc.detail)}
    return {"ok": True, "run_id": run["run_id"], "status": "queued", "options": run["mission"]["options"],
            "warnings": run.get("warnings") or [], "link": _link(run["run_id"]),
            "rappel": "Execução em segundo plano; acompanhar com suivre_programme_ia. Nenhum envio automático."}


def _step(s: dict) -> dict:
    res = s.get("result") or {}
    links = [v for k, v in res.items() if k in ("link", "pdf") and isinstance(v, str)]
    for coll in ("plans", "studies", "notes", "files"):
        links += [r.get("pdf") or r.get("link") or r.get("url") for r in res.get(coll) or []
                  if isinstance(r, dict) and (r.get("pdf") or r.get("link") or r.get("url"))]
    return {"option": s.get("key"), "nom": s.get("name") or s.get("label"), "statut": s.get("status"), "erreur": s.get("error"),
            "synthese": s.get("synthese"), "livrable": s.get("deliverable"), "liens": links[:10]}


async def _follow(args: dict, user: dict) -> dict:
    uid = user["user_id"]
    if not args.get("run_id"):
        rows = await db.agent_runs.find({"user_id": uid, "agent": "mission"},
                                        {"_id": 0, "run_id": 1, "status": 1, "created_at": 1, "mission.options": 1}) \
            .sort("created_at", -1).to_list(10)
        return {"ok": True, "programmes": [{"run_id": r["run_id"], "statut": r.get("status"), "cree_le": r.get("created_at"),
                                            "options": (r.get("mission") or {}).get("options"), "link": _link(r["run_id"])} for r in rows]}
    run = await db.agent_runs.find_one({"run_id": args["run_id"], "user_id": uid, "agent": "mission"}, {"_id": 0})
    if not run:
        return {"ok": False, "error": "Programa não encontrado"}
    res = run.get("result") if isinstance(run.get("result"), dict) else run.get("partial_result") or {}
    steps = res.get("steps") or (run.get("mission") or {}).get("steps") or []
    return {"ok": True, "run_id": run["run_id"], "statut": run.get("status"), "erreur": run.get("error"),
            "options": [_step(s) for s in steps], "link": _link(run["run_id"])}


async def run_mission_tool(name: str, args: dict, user: dict) -> dict:
    try:
        return await _dispatch(name, args, user)
    except HTTPException as exc:
        return {"ok": False, "error": str(exc.detail)}


async def _dispatch(name: str, args: dict, user: dict) -> dict:
    if name == "programme_ia_options":
        return await _options(args, user)
    if name == "lancer_programme_ia":
        return await _launch(args, user)
    if name == "suivre_programme_ia":
        return await _follow(args, user)
    raise HTTPException(422, "Ferramenta desconhecida")
