"""Rappels d'échéances de l'état du dossier (assistant) : cloche + e-mail la veille."""
import logging
import re
import unicodedata
import uuid
from datetime import date, datetime, timedelta, timezone

from core.db import db
from engines.emailer import send_email

logger = logging.getLogger(__name__)

_MONTHS = {"janvier": 1, "fevrier": 2, "mars": 3, "avril": 4, "mai": 5, "juin": 6, "juillet": 7, "aout": 8,
           "septembre": 9, "octobre": 10, "novembre": 11, "decembre": 12,
           "janeiro": 1, "fevereiro": 2, "marco": 3, "maio": 5, "junho": 6, "julho": 7, "agosto": 8, "setembro": 9, "outubro": 10, "dezembro": 12}


def _fold(s: str) -> str:
    return unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode().lower()


def parse_deadline(text: str | None, today: date) -> date | None:
    """Date reconnaissable dans une échéance libre : 22/09/2026, 22-09-26, 2026-09-22, « 22 septembre (2026) ». Sinon None."""
    if not text:
        return None
    t = _fold(text)
    m = re.search(r"\b(\d{1,2})[/.-](\d{1,2})[/.-](\d{2,4})\b", t)
    if m:
        d, mo, y = int(m[1]), int(m[2]), int(m[3])
        y = y + 2000 if y < 100 else y
        try:
            return date(y, mo, d)
        except ValueError:
            return None
    m = re.search(r"\b(\d{4})-(\d{2})-(\d{2})\b", t)
    if m:
        try:
            return date(int(m[1]), int(m[2]), int(m[3]))
        except ValueError:
            return None
    m = re.search(r"\b(\d{1,2})(?:er)?\s+(" + "|".join(_MONTHS) + r")(?:\s+(\d{4}))?\b", t)
    if m:
        y = int(m[3]) if m[3] else today.year
        try:
            d = date(y, _MONTHS[m[2]], int(m[1]))
        except ValueError:
            return None
        if not m[3] and d < today - timedelta(days=30):
            d = d.replace(year=y + 1)
        return d
    return None


def _entries_due(state: dict, target: date, today: date) -> list[dict]:
    out = []
    for section in ("open_points", "decisions"):
        for e in state.get(section) or []:
            if e.get("status") == "superseded" or not e.get("deadline"):
                continue
            if parse_deadline(e["deadline"], today) == target:
                out.append({**e, "section": section})
    return out


async def _recipients(owner: dict, owner_names: set[str]) -> list[dict]:
    """Propriétaire du dossier + membres de son organisation dont le nom correspond au responsable nommé."""
    recips = [owner]
    if not owner.get("organization_id") or not owner_names:
        return recips
    async for m in db.users.find({"organization_id": owner["organization_id"], "user_id": {"$ne": owner["user_id"]}, "active": {"$ne": False}},
                                 {"_id": 0, "user_id": 1, "email": 1, "name": 1}):
        name = _fold(m.get("name") or "")
        tokens = [tok for tok in re.split(r"\W+", name) if len(tok) >= 3]
        if name and any(name in o or o in name or any(tok in o for tok in tokens) for o in owner_names):
            recips.append(m)
    return recips


def _email_html(title: str, conv_id: str, entries: list[dict], target: date, base_url: str) -> str:
    rows = "".join(f"<li><b>{e.get('statement', '')}</b>" + (f" — responsable : {e['owner']}" if e.get("owner") else "") + f" — prazo: {e.get('deadline')}</li>" for e in entries)
    return (f'''<p>Olá,</p><p>Lembrete: {len(entries)} prazo(s) do processo «{title}» termina(m) amanhã ({target.strftime('%d/%m/%Y')}).</p><ul>{rows}</ul><p><a href="{base_url}/assistant?conversation={conv_id}">Abrir o processo no ConstruPilot</a></p><p><small>Lembrete automático ConstruPilot — estado do processo Assistente Construção.</small></p>''')


async def run_deadline_reminders(now: datetime | None = None) -> dict:
    import os
    now = now or datetime.now(timezone.utc)
    today = now.date()
    target = today + timedelta(days=1)
    base_url = (os.environ.get("FRONTEND_URL") or "").rstrip("/")
    notified = emails = 0
    async for state in db.assistant_project_state.find({"$or": [{"open_points.deadline": {"$ne": None}}, {"decisions.deadline": {"$ne": None}}]}, {"_id": 0}):
        due = _entries_due(state, target, today)
        if not due:
            continue
        conv_id, uid = state["conversation_id"], state["user_id"]
        key = f"{conv_id}:{target.isoformat()}"
        already = await db.deadline_reminders.find_one({"key": key, "entry_ids": {"$all": [e["entry_id"] for e in due]}}, {"_id": 1})
        if already:
            continue
        owner = await db.users.find_one({"user_id": uid}, {"_id": 0, "user_id": 1, "email": 1, "name": 1, "organization_id": 1})
        if not owner:
            continue
        conv = await db.assistant_convs.find_one({"conversation_id": conv_id}, {"_id": 0, "title": 1}) or {}
        title = conv.get("title") or "Dossier"
        owner_names = {_fold(e["owner"]) for e in due if e.get("owner")}
        recips = await _recipients(owner, owner_names)
        labels = "; ".join((e.get("statement") or "")[:80] for e in due[:3]) + (" …" if len(due) > 3 else "")
        msg = f"Prazo amanhã ({target.strftime('%d/%m')}) — « {title[:50]} » : {labels}"
        for r in recips:
            await db.notifications.insert_one({"notif_id": "n_" + uuid.uuid4().hex[:10], "user_id": r["user_id"], "type": "deadline_reminder",
                                               "url": f"/assistant?conversation={conv_id}", "message": msg, "conversation_id": conv_id,
                                               "entry_ids": [e["entry_id"] for e in due], "created_at": now.isoformat(), "read": False})
            notified += 1
            if r.get("email"):
                try:
                    await send_email(r["email"], f"Lembrete de prazo — {title[:60]} — demain {target.strftime('%d/%m/%Y')}", _email_html(title, conv_id, due, target, base_url))
                    emails += 1
                except Exception as exc:  # noqa: BLE001 — l'e-mail ne doit pas bloquer la cloche
                    logger.warning("deadline reminder email failed for %s: %s", r.get("user_id"), exc)
        await db.deadline_reminders.insert_one({"key": key, "conversation_id": conv_id, "user_id": uid, "target": target.isoformat(),
                                                "entry_ids": [e["entry_id"] for e in due], "recipients": [r["user_id"] for r in recips],
                                                "sent_at": now.isoformat()})
    await db.trash_jobs.update_one({"job": "deadline_reminders"}, {"$set": {"job": "deadline_reminders", "last_run": now.isoformat(), "notified": notified, "emails": emails}}, upsert=True)
    return {"notified": notified, "emails": emails, "target": target.isoformat()}
