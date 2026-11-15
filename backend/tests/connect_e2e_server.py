"""Servidor local SÓ PARA TESTES E2E do Discovery Engine (não é importado pela aplicação).

Serve o build do frontend + as rotas reais /api/connect com Mongo em memória, e-mails falsos
e um utilizador admin fictício. Uso:
    REACT_APP_BACKEND_URL=http://127.0.0.1:8011 yarn build   (em frontend/)
    python3 backend/tests/connect_e2e_server.py               (porta 8011)
"""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "connect_e2e")
os.environ.setdefault("JWT_SECRET", "e2e-only")
os.environ["CONNECT_ENABLED"] = "1"
os.environ["RATE_LIMIT_ENABLED"] = "0"

from fastapi import FastAPI  # noqa: E402
from fastapi.responses import FileResponse, JSONResponse  # noqa: E402
from mongomock_motor import AsyncMongoMockClient  # noqa: E402
from slowapi.errors import RateLimitExceeded  # noqa: E402

import engines.activity_crm.record as REC  # noqa: E402
import engines.emailer as EM  # noqa: E402
from core import rate_limit  # noqa: E402
from core.security import admin_user  # noqa: E402
from routes import connect as RC  # noqa: E402

DB = AsyncMongoMockClient().connect_e2e
RC.db = DB
SENT = []
ADMIN = {"user_id": "adm", "email": "admin@construpilot.pt", "role": "admin", "name": "Admin E2E", "account_type": "pro"}


async def fake_send(to, subject, html, **kw):
    SENT.append({"to": to, "subject": subject})
    return {"id": "e2e"}


async def fake_record(**kw):
    return "x"

EM.send_email = fake_send
REC.record_activity = fake_record

app = FastAPI()
app.state.limiter = rate_limit.limiter
app.add_exception_handler(RateLimitExceeded, rate_limit.rate_limit_exceeded_handler)
app.include_router(RC.router, prefix="/api")
app.dependency_overrides[admin_user] = lambda: ADMIN


@app.get("/api/auth/me")
async def me():
    return ADMIN


@app.get("/api/__e2e/sent")
async def sent():
    return SENT


@app.api_route("/api/{rest:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE"])
async def other_api(rest: str):
    return JSONResponse({}, status_code=200) if rest.endswith(("me", "status")) else JSONResponse([], status_code=200)

BUILD = ROOT / "frontend/build"


@app.get("/{path:path}")
async def spa(path: str):
    f = BUILD / path
    if path and f.is_file():
        return FileResponse(f)
    return FileResponse(BUILD / "index.html")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8011, log_level="warning")
