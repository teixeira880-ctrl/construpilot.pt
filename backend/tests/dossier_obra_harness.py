"""Banco de ensaio do Dossier de Obra (NÃO é produção): rotas reais /api/dossier-obra + Mongo em memória (mongomock-motor)
+ assistente SIMULADO (sem IA). Usado por frontend/scripts/test-dossier-obra.cjs."""
import asyncio, os, sys, json
BACK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BACK)
for k, v in {"MONGO_URL": "mongodb://x", "DB_NAME": "t", "JWT_SECRET": "t", "STUDIES_MODEL_ANALYSIS": "t", "STUDIES_MODEL_LIGHT": "t"}.items():
    os.environ.setdefault(k, v)
import mongomock_motor
from fastapi import FastAPI, APIRouter
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
import core.environment as E
import core.security as S
import routes.dossier_obra as R, routes.chantiers as CH, routes.plans_common as PC, routes.assistant as A
db = mongomock_motor.AsyncMongoMockClient()["t"]
R.db = CH.db = PC.db = A.db = db
E.ENVIRONMENT = "development"
USER = {"user_id": "u_a", "account_type": "pro", "active": True, "name": "Martinho (teste)", "email": "teste@exemplo.pt"}
app = FastAPI()
api = APIRouter(prefix="/api")
api.include_router(R.router)
stub = APIRouter(prefix="/assistant")

@stub.get("/conversations/{cid}")
async def conv(cid: str):
    msgs = [m async for m in db.stub_msgs.find({"conversation_id": cid}, {"_id": 0})]
    return {"conversation_id": cid, "messages": msgs}

@stub.post("/message")
async def message(body: dict):
    conv = await db.assistant_convs.find_one({"conversation_id": body["conversation_id"]}, {"_id": 0})
    ctx = await R.assistant_context(conv["chantier_id"], USER["user_id"], conv["dossier_context"])
    open_ = [r["titulo"] for r in ctx["registos"] if r.get("estado") in ("pendente", "bloqueado", "por_fazer")]
    conf = [f"camada {c['n']} ({c['camada']})" for r in ctx["registos"] for c in (r.get("camadas") or []) if c["validacao"] == "por_confirmar"]
    text = ("[SIMULAÇÃO DE ENSAIO — sem modelo de IA; mostra só o contexto que o Assistente BTP recebe]\n\n"
            f"Factos ({ctx['especialidade']} · {ctx.get('fase_selecionada') or 'todas as fases'}):\n- " + "\n- ".join(open_ or ["sem tarefas em aberto"]) +
            "\n\nInformação em falta:\n- " + "\n- ".join(conf or ["nenhuma camada por confirmar"]) +
            "\n\nDependências: " + "; ".join(d["relacao"] for d in ctx["dependencias"]))
    for role, content in (("user", body["text"]), ("assistant", text)):
        await db.stub_msgs.insert_one({"conversation_id": body["conversation_id"], "role": role, "content": content})
    return {"role": "assistant", "content": text}

api.include_router(stub)
app.include_router(api)
app.dependency_overrides[S.current_user] = lambda: USER
app.dependency_overrides[S.pro_required] = lambda: USER
app.mount("/static", StaticFiles(directory=os.environ["DOSSIER_E2E_STATIC"]), name="static")
STATE = {}

@app.on_event("startup")
async def seed():
    await db.users.insert_one({"user_id": "u_a", "name": USER["name"]})
    STATE["cid"] = (await R.create_demo(user=USER))["chantier_id"]
    # registo antigo, por classificar
    await db.plans_takeoff.insert_one({"plan_id": "pl_old", "user_id": "u_a", "chantier_id": STATE["cid"], "filename": "Levantamento_2024.pdf", "trashed_at": None, "created_at": "2024-03-02"})

@app.get("/{path:path}", response_class=HTMLResponse)
async def spa(path: str):
    return f"""<!doctype html><html lang="pt-PT"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<link rel="stylesheet" href="/static/main.css"><link rel="stylesheet" href="/static/entry.css"><title>Dossier de obra</title></head>
<body><div id="root"></div><script>window.__CID__="{STATE['cid']}"</script><script src="/static/entry.js"></script></body></html>"""
