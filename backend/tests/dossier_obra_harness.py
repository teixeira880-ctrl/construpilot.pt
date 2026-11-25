"""Banco de ensaio do Dossier de Obra (NÃO é produção): rotas reais /api/dossier-obra + Mongo em memória (mongomock-motor)
+ assistente SIMULADO (sem IA). Usado por frontend/scripts/test-dossier-obra.cjs."""
import asyncio, os, sys, json
BACK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BACK)
for k, v in {"MONGO_URL": "mongodb://x", "DB_NAME": "t", "JWT_SECRET": "t", "STUDIES_MODEL_ANALYSIS": "t", "STUDIES_MODEL_LIGHT": "t"}.items():
    os.environ.setdefault(k, v)
os.environ["MONGO_URL"] = "mongodb://localhost:1/?serverSelectionTimeoutMS=200"
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
USER = {"user_id": "u_a", "account_type": "pro_business", "active": True, "name": "Martinho (teste)", "email": "teste@exemplo.pt"}
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


@api.get("/auth/me")
async def me():
    return {**USER, "account_type": "pro_business", "role": "user", "nav_favorites": []}


@api.api_route("/{rest:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE"])
async def not_here(rest: str):
    from fastapi import HTTPException
    raise HTTPException(404, "fora do âmbito do banco de ensaio")
app.include_router(api)
app.dependency_overrides[S.current_user] = lambda: USER
app.dependency_overrides[S.pro_required] = lambda: USER
PUBLIC = os.path.join(os.path.dirname(BACK), "frontend", "public")


@app.get("/construpilot-icon.png")
async def icon():
    from fastapi.responses import FileResponse
    return FileResponse(os.path.join(PUBLIC, "construpilot-icon.png"))


app.mount("/static", StaticFiles(directory=os.environ["DOSSIER_E2E_STATIC"]), name="static")
STATE = {}

@app.on_event("startup")
async def seed():
    import core.db as CDB
    import routes.documents, engines.monetization, engines.access  # noqa: F401,E401
    for mod in list(sys.modules.values()):   # nenhum módulo toca numa base real
        if getattr(mod, "db", None) is CDB.db and mod is not CDB:
            mod.db = db
    await db.users.insert_one({"user_id": "u_a", "name": USER["name"]})
    STATE["cid"] = (await R.create_demo(user=USER))["chantier_id"]
    # registo antigo, por classificar
    await db.plans_takeoff.insert_one({"plan_id": "pl_old", "user_id": "u_a", "chantier_id": STATE["cid"], "filename": "Levantamento_2024.pdf", "trashed_at": None, "created_at": "2024-03-02"})

@app.get("/{path:path}", response_class=HTMLResponse)
async def spa(path: str):
    return f"""<!doctype html><html lang="pt-PT"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<link rel="stylesheet" href="/static/main.css"><link rel="stylesheet" href="/static/entry.css"><title>Dossier de obra</title></head>
<body><div id="root"></div><script>window.__CID__="{STATE['cid']}"</script><script src="/static/entry.js"></script></body></html>"""
