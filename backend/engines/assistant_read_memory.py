"""Mémoire de lecture de l'Assistant BTP (09/11/2026).

Évite qu'à chaque message (ou après « Reprendre la demande ») l'assistant relise les documents
depuis le début : les pages lues par read_document sont journalisées dans assistant_actions
(doc_id, pages_read, total_pages) et redonnées au modèle comme « déjà lues ».
"""


async def pages_read_map(db, conversation_id: str, uid: str) -> dict:
    """{doc_id: {"pages": set[int], "total": int|None}} pour une conversation."""
    seen: dict = {}
    async for a in db.assistant_actions.find(
            {"conversation_id": conversation_id, "user_id": uid, "tool": "read_document", "pages_read": {"$exists": True}},
            {"_id": 0, "doc_id": 1, "pages_read": 1, "total_pages": 1}):
        entry = seen.setdefault(a.get("doc_id"), {"pages": set(), "total": None})
        entry["pages"].update(int(p) for p in a.get("pages_read") or [] if isinstance(p, int))
        entry["total"] = a.get("total_pages") or entry["total"]
    return seen


def ranges(pages) -> str:
    """{1,2,3,5} → "1–3, 5"."""
    out, run = [], []
    for p in sorted(pages):
        if run and p == run[-1] + 1:
            run.append(p)
            continue
        if run:
            out.append(f"{run[0]}–{run[-1]}" if len(run) > 1 else str(run[0]))
        run = [p]
    if run:
        out.append(f"{run[0]}–{run[-1]}" if len(run) > 1 else str(run[0]))
    return ", ".join(out)
