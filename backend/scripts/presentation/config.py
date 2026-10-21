"""One-off presentation tools; no application configuration or credentials are changed."""
import json
import os
import re
import sys
from pathlib import Path

from dotenv import dotenv_values, load_dotenv

ROOT = Path(__file__).resolve().parents[3]
BACKEND = ROOT / "backend"
sys.path.insert(0, str(BACKEND))
load_dotenv(BACKEND / ".env")
load_dotenv(Path(__file__).with_name(".env"))
BASE = dotenv_values(ROOT / "frontend/.env")["REACT_APP_BACKEND_URL"].rstrip("/")
WORK = Path(os.environ["PRESENTATION_WORK_DIR"])
WORK.mkdir(parents=True, exist_ok=True)
VOICE = os.environ["PRESENTATION_VOICE_ID"]
MODEL = os.environ["PRESENTATION_VOICE_MODEL"]


def credentials(role="pro"):
    text = (ROOT / "memory/test_credentials.md").read_text()
    marker = "### Pro / Owner" if role == "pro" else "## Administrateur (back-office"
    block = text.split(marker, 1)[1].split("## ", 1)[0]
    return {key: re.search(pattern, block).group(1) for key, pattern in {
        "email": r"\*\*Email\*\*\s*:\s*`([^`]+)`",
        "password": r"\*\*Password\*\*\s*:\s*`([^`]+)`",
    }.items()}


def read_state():
    path = WORK / "state.json"
    return json.loads(path.read_text()) if path.exists() else {}


def save_state(state):
    (WORK / "state.json").write_text(json.dumps(state, ensure_ascii=False, indent=2))


def api_session(role="pro"):
    import requests
    session = requests.Session()
    response = session.post(BASE + "/api/auth/login", json=credentials(role), timeout=30)
    response.raise_for_status()
    payload = response.json()
    session.headers["Authorization"] = "Bearer " + payload["token"]
    return session, payload