"""Project state of a conversation: current decisions (with their source), documents set aside (with reason), open points.
Kept outside the chat history so a later correction changes only the entry concerned; editable by the user and by the assistant."""
import uuid
from datetime import datetime, timezone

SECTIONS = ("decisions", "discarded_documents", "open_points")
STATUS = ("current", "superseded", "to_confirm")

STATE_TOOL = {"type": "function", "name": "update_project_state", "strict": True,
              "description": "Met à jour l'état du dossier de la conversation (décisions courantes avec leur source, documents écartés avec motif, points ouverts). "
                             "Une entrée par fait ; pour corriger, reprends le même entry_id — les autres entrées ne changent pas. remove=true retire l'entrée.",
              "parameters": {"type": "object", "properties": {
                  "section": {"type": "string", "enum": list(SECTIONS)},
                  "entry_id": {"type": ["string", "null"], "description": "identifiant d'une entrée existante à corriger, null pour une nouvelle"},
                  "statement": {"type": "string", "description": "décision, document écarté ou point ouvert, en une phrase factuelle"},
                  "source": {"type": "string", "description": "pièce, page, cote, message de l'utilisateur ou référence qui fonde l'entrée"},
                  "status": {"type": "string", "enum": list(STATUS)},
                  "kind": {"type": "string", "enum": ["schema_de_principe", "validation_execution", "fait", "hypothese", "action"],
                           "description": "nature : un schéma de principe n'est jamais une validation technique d'exécution"},
                  "owner": {"type": ["string", "null"], "description": "responsable de l'action ou du point (nom / rôle), null si inconnu"},
                  "deadline": {"type": ["string", "null"], "description": "échéance (ex. 22/09/2026 ou « avant coulage »), null si inconnue"},
                  "remove": {"type": "boolean"}},
                  "required": ["section", "entry_id", "statement", "source", "status", "kind", "owner", "deadline", "remove"], "additionalProperties": False}}

PROTOCOL = """
Méthode pour un problème de chantier (photo, mail, plan joints) : 1) lis réellement chaque pièce jointe (images fournies, read_document /
inspect_document_region pour les plans) et cite ce que tu y vois avec la page ou la zone ; 2) relève les faits observés puis, séparément,
les incertitudes ; 3) consulte les références nécessaires (DTU, avis technique, fiche fabricant) seulement si la recherche est active et cite-les ;
4) propose une solution argumentée avec options, limites et contrôles ; 5) produis le livrable demandé (courrier, compte rendu, schéma, PDF) ;
6) contrôle la cohérence entre pièces, état du dossier et livrable. Pour un schéma de coupe / raccord de paroi, utilise draw_section_schema (dessin coté lisible depuis les cotes du dossier) plutôt qu'une illustration IA ; réserve create_downloadable_file JPG aux ambiances. Ne réponds jamais de façon générique quand une pièce est jointe : si la
pièce ne permet pas de conclure, dis précisément ce qui manque. Un schéma de principe (JPG/PDF produit) illustre une intention ; il n'est
jamais une validation technique d'exécution, qui relève du BET ou du contrôleur — écris-le sur le livrable et dans l'état du dossier.
État du dossier : après chaque décision, document écarté ou point ouvert, appelle update_project_state (une entrée par fait, source
obligatoire) ; une correction de l'utilisateur met à jour l'entrée concernée (même entry_id) et relance uniquement le résultat qui en dépend.
L'état du dossier joint au message est la référence courante : ne contredis pas une décision « current » sans l'annoncer et la mettre à jour.
"""


def _now():
    return datetime.now(timezone.utc).isoformat()


def empty_state(conversation_id: str, user_id: str) -> dict:
    return {"conversation_id": conversation_id, "user_id": user_id, **{s: [] for s in SECTIONS}, "revision": 0, "updated_at": _now()}


async def get_state(db, conversation_id: str, user_id: str) -> dict:
    doc = await db.assistant_project_state.find_one({"conversation_id": conversation_id, "user_id": user_id}, {"_id": 0})
    return doc or empty_state(conversation_id, user_id)


async def apply_entry(db, conversation_id: str, user_id: str, args: dict, author: str) -> dict:
    state = await get_state(db, conversation_id, user_id)
    section = args["section"]
    entries = state[section]
    entry_id = args.get("entry_id") or f"st_{uuid.uuid4().hex[:8]}"
    idx = next((i for i, e in enumerate(entries) if e["entry_id"] == entry_id), None)
    if args.get("remove"):
        if idx is None:
            return {"ok": False, "error": "Entrée introuvable"}
        removed = entries.pop(idx)
        change = {"op": "remove", "entry": removed}
    else:
        entry = {"entry_id": entry_id, "statement": args["statement"].strip()[:600], "source": args["source"].strip()[:400],
                 "status": args.get("status", "current"), "kind": args.get("kind", "fait"), "owner": (args.get("owner") or "").strip()[:80] or None,
                 "deadline": (args.get("deadline") or "").strip()[:60] or None, "author": author, "updated_at": _now()}
        if idx is None:
            entry["created_at"] = entry["updated_at"]
            entries.append(entry)
            change = {"op": "add", "entry": entry}
        else:
            entry["created_at"] = entries[idx].get("created_at", entry["updated_at"])
            entries[idx] = entry
            change = {"op": "update", "entry": entry, "previous": {k: entries[idx].get(k) for k in ("statement", "source", "status")}}
    state["revision"] = state.get("revision", 0) + 1
    state["updated_at"] = _now()
    history = {"conversation_id": conversation_id, "user_id": user_id, "revision": state["revision"], "section": section, **change, "at": state["updated_at"]}
    await db.assistant_project_state.update_one({"conversation_id": conversation_id, "user_id": user_id}, {"$set": state}, upsert=True)
    await db.assistant_project_state_log.insert_one(history)
    return {"ok": True, "section": section, "entry_id": entry_id, "op": change["op"], "revision": state["revision"], "state": public_state(state)}


def public_state(state: dict) -> dict:
    return {k: state[k] for k in (*SECTIONS, "revision", "updated_at", "conversation_id")}


def state_for_model(state: dict) -> str:
    if not any(state[s] for s in SECTIONS):
        return "État du dossier : vide (aucune décision enregistrée)."
    lines = ["État du dossier (référence courante, à mettre à jour avec update_project_state) :"]
    labels = {"decisions": "Décisions", "discarded_documents": "Documents écartés", "open_points": "Points ouverts"}
    for s in SECTIONS:
        for e in state[s]:
            extra = "".join(f" — {k} : {e[f]}" for k, f in (("responsable", "owner"), ("échéance", "deadline")) if e.get(f))
            lines.append(f"- [{labels[s]} · {e['entry_id']} · {e['status']} · {e['kind']}] {e['statement']} — source : {e['source']}{extra}")
    return "\n".join(lines)


def state_pdf(state: dict, *, title: str, meeting: str | None = None, photo_bytes: dict | None = None) -> bytes:
    """One-page A4 « état du dossier » for a site meeting: decisions + sources, open points, discarded documents, disclaimer."""
    import io
    from xml.sax.saxutils import escape
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.platypus import Image as RLImage, KeepInFrame, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=14 * mm, rightMargin=14 * mm, topMargin=12 * mm, bottomMargin=12 * mm, title=title)
    photo_bytes = photo_bytes or {}
    def thumbs(entry):
        cells = []
        for p in (entry.get("photos") or [])[:2]:
            raw = photo_bytes.get(p["doc_id"])
            if not raw:
                continue
            im = RLImage(io.BytesIO(raw)); ratio = im.imageHeight / float(im.imageWidth)
            im.drawWidth, im.drawHeight = 22 * mm, 22 * mm * ratio if ratio <= 1 else 22 * mm
            if ratio > 1: im.drawWidth = 22 * mm / ratio
            cap = f"{'avant' if p.get('phase') == 'before' else 'après'} · {(p.get('taken_at') or '')[:10]}"
            cells.append([im, Paragraph(cap, small)])
        return cells
    base = ParagraphStyle("b", fontName="Helvetica", fontSize=8.2, leading=10.5)
    small = ParagraphStyle("s", parent=base, fontSize=7, leading=8.5, textColor=colors.HexColor("#555555"))
    h = ParagraphStyle("h", parent=base, fontName="Helvetica-Bold", fontSize=10, leading=13, spaceBefore=5, spaceAfter=2, textColor=colors.HexColor("#137566"))
    t = ParagraphStyle("t", parent=base, fontName="Helvetica-Bold", fontSize=14, leading=17)
    status = {"current": "courante", "superseded": "remplacée", "to_confirm": "à confirmer"}
    kind = {"schema_de_principe": "schéma de principe", "validation_execution": "validation d'exécution", "fait": "fait", "hypothese": "hypothèse", "action": "action"}
    story = [Paragraph("ConstruPilot — État du dossier", t), Paragraph(escape(title), base)]
    sub = f"Révision {state.get('revision', 0)} · mis à jour le {str(state.get('updated_at', ''))[:16].replace('T', ' ')}"
    if meeting:
        sub += f" · Réunion de chantier : {escape(meeting)}"
    story += [Paragraph(sub, small), Spacer(1, 4)]
    def section(label, entries, empty):
        story.append(Paragraph(f"{label} ({len(entries)})", h))
        if not entries:
            story.append(Paragraph(empty, small)); return
        has_photos = any(thumbs(e) for e in entries)
        rows = [[Paragraph("<b>Énoncé</b>", small), Paragraph("<b>Source</b>", small), Paragraph("<b>État</b>", small)] + ([Paragraph("<b>Photos avant / après</b>", small)] if has_photos else [])]
        for e in entries:
            st = f"{status.get(e['status'], e['status'])}<br/>{kind.get(e.get('kind'), e.get('kind', ''))}"
            row = [Paragraph(escape(e["statement"]), base), Paragraph(escape(e["source"]), small), Paragraph(st, small)]
            if has_photos:
                th = thumbs(e)
                row.append(Table([[c[0] for c in th], [c[1] for c in th]], colWidths=[24 * mm] * len(th)) if th else Paragraph("", small))
            rows.append(row)
        tbl = Table(rows, colWidths=[52 * mm, 44 * mm, 26 * mm, 60 * mm] if has_photos else [102 * mm, 52 * mm, 28 * mm], repeatRows=1)
        tbl.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#cccccc")), ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#eef5f3")),
                                 ("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 3), ("RIGHTPADDING", (0, 0), (-1, -1), 3), ("TOPPADDING", (0, 0), (-1, -1), 2), ("BOTTOMPADDING", (0, 0), (-1, -1), 2)]))
        story.append(tbl)
    section("Décisions courantes", [e for e in state["decisions"] if e["status"] != "superseded"], "Aucune décision enregistrée.")
    section("Points ouverts", state["open_points"], "Aucun point ouvert.")
    section("Documents écartés", state["discarded_documents"], "Aucun document écarté.")
    superseded = [e for e in state["decisions"] if e["status"] == "superseded"]
    if superseded:
        story.append(Paragraph("Décisions remplacées : " + " ; ".join(escape(e["statement"]) for e in superseded), small))
    story += [Spacer(1, 6), Paragraph("Document d'aide à la décision issu de l'assistant et des corrections de l'utilisateur. Un schéma de principe illustre une intention ; "
                                       "il ne vaut pas validation technique d'exécution (BET / contrôleur technique).", small)]
    frame_w, frame_h = A4[0] - 28 * mm, A4[1] - 24 * mm
    doc.build([KeepInFrame(frame_w, frame_h, story, mode="shrink")])
    return buf.getvalue()


def agenda_pdf(state: dict, *, title: str, meeting: str | None, attendees: str | None = None) -> bytes:
    """One-page agenda for the site meeting: open points (owner, deadline), decisions to confirm, decisions to record."""
    import io
    from xml.sax.saxutils import escape
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.platypus import KeepInFrame, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=14 * mm, rightMargin=14 * mm, topMargin=12 * mm, bottomMargin=12 * mm, title="Ordre du jour")
    base = ParagraphStyle("b", fontName="Helvetica", fontSize=8.4, leading=10.8)
    small = ParagraphStyle("s", parent=base, fontSize=7, leading=8.6, textColor=colors.HexColor("#555555"))
    h = ParagraphStyle("h", parent=base, fontName="Helvetica-Bold", fontSize=10, leading=13, spaceBefore=6, spaceAfter=2, textColor=colors.HexColor("#137566"))
    t = ParagraphStyle("t", parent=base, fontName="Helvetica-Bold", fontSize=14, leading=17)
    story = [Paragraph("Ordre du jour — réunion de chantier", t), Paragraph(escape(title), base),
             Paragraph(f"Date / heure : {escape(meeting or 'à fixer')} · Participants : {escape(attendees or 'MOA, MOE/architecte, entreprise, BET si requis')}", small), Spacer(1, 4)]
    def table(rows_data, cols, widths):
        rows = [[Paragraph(f"<b>{c}</b>", small) for c in cols]] + rows_data
        tbl = Table(rows, colWidths=widths, repeatRows=1)
        tbl.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#cccccc")), ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#eef5f3")), ("VALIGN", (0, 0), (-1, -1), "TOP"),
                                 ("LEFTPADDING", (0, 0), (-1, -1), 3), ("RIGHTPADDING", (0, 0), (-1, -1), 3), ("TOPPADDING", (0, 0), (-1, -1), 2), ("BOTTOMPADDING", (0, 0), (-1, -1), 2)]))
        story.append(tbl)
    n = 0
    opens = state["open_points"]
    story.append(Paragraph(f"1. Points à trancher ({len(opens)})", h))
    if opens:
        rows = []
        for e in opens:
            n += 1
            rows.append([Paragraph(str(n), small), Paragraph(escape(e["statement"]) + f"<br/><font color='#555555' size='7'>Source : {escape(e['source'])}</font>", base),
                         Paragraph(escape(e.get("owner") or "à désigner"), base), Paragraph(escape(e.get("deadline") or "à fixer"), base), Paragraph("", base)])
        table(rows, ["#", "Point / question", "Responsable", "Échéance", "Décision en réunion"], [7 * mm, 88 * mm, 28 * mm, 24 * mm, 35 * mm])
    else:
        story.append(Paragraph("Aucun point ouvert.", small))
    confirm = [e for e in state["decisions"] if e["status"] == "to_confirm"]
    story.append(Paragraph(f"2. Décisions à confirmer ({len(confirm)})", h))
    if confirm:
        table([[Paragraph(escape(e["statement"]), base), Paragraph(escape(e["source"]), small), Paragraph(escape(e.get("owner") or "—"), base), Paragraph("", base)] for e in confirm],
              ["Décision proposée", "Source", "Responsable", "Confirmée ? (O/N)"], [90 * mm, 44 * mm, 24 * mm, 24 * mm])
    else:
        story.append(Paragraph("Aucune.", small))
    current = [e for e in state["decisions"] if e["status"] == "current"]
    story.append(Paragraph(f"3. Décisions acquises à acter au compte rendu ({len(current)})", h))
    for e in current:
        tag = " <font color='#8a6d00'>[schéma de principe — pas une validation d'exécution]</font>" if e.get("kind") == "schema_de_principe" else ""
        story.append(Paragraph(f"• {escape(e['statement'])}{tag} <font color='#555555' size='7'>({escape(e['source'])})</font>", base))
    disc = state["discarded_documents"]
    if disc:
        story.append(Paragraph(f"4. Documents écartés ({len(disc)})", h))
        for e in disc:
            story.append(Paragraph(f"• {escape(e['statement'])} <font color='#555555' size='7'>({escape(e['source'])})</font>", base))
    story += [Spacer(1, 6), Paragraph("Ordre du jour préparé depuis l'état du dossier ConstruPilot (révision " + str(state.get("revision", 0)) + "). Les décisions d'exécution relèvent de la MOE / du BET / du contrôleur technique.", small)]
    doc.build([KeepInFrame(A4[0] - 28 * mm, A4[1] - 24 * mm, story, mode="shrink")])
    return buf.getvalue()


async def apply_meeting(db, conversation_id: str, user_id: str, *, meeting: str, attendees: str | None, items: list[dict], remarks: str | None, title: str, photo_bytes: dict | None = None) -> dict:
    """Meeting outcome → dossier: each item closes/postpones/drops an open point or confirms a decision; then a one-page report PDF (+ annexe photos épinglées)."""
    state = await get_state(db, conversation_id, user_id)
    source = f"Réunion de chantier {meeting}"
    decided, postponed, dropped = [], [], []
    by_id = {e["entry_id"]: (s, e) for s in SECTIONS for e in state[s]}
    for it in items:
        found = by_id.get(it["entry_id"])
        if not found:
            continue
        section, entry = found
        outcome = it.get("outcome")
        if outcome == "decided":
            text = (it.get("decision_taken") or "").strip()
            if not text:
                continue
            if section == "decisions":
                await apply_entry(db, conversation_id, user_id, {"section": "decisions", "entry_id": entry["entry_id"], "statement": entry["statement"], "source": f"{entry['source']} ; confirmée en {source}",
                                                                  "status": "current", "kind": entry.get("kind", "fait"), "owner": it.get("owner") or entry.get("owner"), "deadline": it.get("deadline") or entry.get("deadline")}, author="user")
            else:
                await apply_entry(db, conversation_id, user_id, {"section": "decisions", "entry_id": None, "statement": text, "source": f"{source} — tranche : {entry['statement'][:120]}",
                                                                  "status": "current", "kind": "action" if it.get("owner") else "fait", "owner": it.get("owner"), "deadline": it.get("deadline")}, author="user")
                await apply_entry(db, conversation_id, user_id, {"section": section, "entry_id": entry["entry_id"], "statement": entry["statement"], "source": entry["source"], "remove": True}, author="user")
            decided.append({"point": entry["statement"], "decision": text or entry["statement"], "owner": it.get("owner") or entry.get("owner"), "deadline": it.get("deadline") or entry.get("deadline"), "photos": entry.get("photos") or []})
        elif outcome == "postponed":
            await apply_entry(db, conversation_id, user_id, {"section": section, "entry_id": entry["entry_id"], "statement": entry["statement"], "source": f"{entry['source']} ; reporté en {source}",
                                                              "status": entry.get("status", "to_confirm"), "kind": entry.get("kind", "hypothese"), "owner": it.get("owner") or entry.get("owner"), "deadline": it.get("deadline") or entry.get("deadline")}, author="user")
            postponed.append({"point": entry["statement"], "owner": it.get("owner") or entry.get("owner"), "deadline": it.get("deadline") or entry.get("deadline"), "note": it.get("decision_taken"), "photos": entry.get("photos") or []})
        elif outcome == "dropped":
            await apply_entry(db, conversation_id, user_id, {"section": section, "entry_id": entry["entry_id"], "statement": entry["statement"], "source": entry["source"], "remove": True}, author="user")
            dropped.append({"point": entry["statement"], "note": it.get("decision_taken"), "photos": entry.get("photos") or []})
    state = await get_state(db, conversation_id, user_id)
    pdf = meeting_report_pdf(state, title=title, meeting=meeting, attendees=attendees, decided=decided, postponed=postponed, dropped=dropped, remarks=remarks, photo_bytes=photo_bytes)
    await db.assistant_project_state_log.insert_one({"conversation_id": conversation_id, "user_id": user_id, "op": "meeting_report", "meeting": meeting, "decided": len(decided),
                                                     "postponed": len(postponed), "dropped": len(dropped), "at": _now()})
    return {"state": public_state(state), "pdf": pdf, "counts": {"decided": len(decided), "postponed": len(postponed), "dropped": len(dropped)}}


def meeting_report_pdf(state, *, title, meeting, attendees, decided, postponed, dropped, remarks, photo_bytes: dict | None = None) -> bytes:
    import io
    from xml.sax.saxutils import escape
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.platypus import Image as RLImage, KeepInFrame, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
    photo_bytes = photo_bytes or {}
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=14 * mm, rightMargin=14 * mm, topMargin=12 * mm, bottomMargin=12 * mm, title="Compte rendu de réunion")
    base = ParagraphStyle("b", fontName="Helvetica", fontSize=8.4, leading=10.8)
    small = ParagraphStyle("s", parent=base, fontSize=7, leading=8.6, textColor=colors.HexColor("#555555"))
    h = ParagraphStyle("h", parent=base, fontName="Helvetica-Bold", fontSize=10, leading=13, spaceBefore=6, spaceAfter=2, textColor=colors.HexColor("#137566"))
    t = ParagraphStyle("t", parent=base, fontName="Helvetica-Bold", fontSize=14, leading=17)
    story = [Paragraph("Compte rendu de réunion de chantier", t), Paragraph(escape(title), base),
             Paragraph(f"Réunion : {escape(meeting)} · Participants : {escape(attendees or '—')} · Rédigé le {_now()[:10]}", small), Spacer(1, 4)]
    def table(rows_data, cols, widths):
        rows = [[Paragraph(f"<b>{c}</b>", small) for c in cols]] + rows_data
        tbl = Table(rows, colWidths=widths, repeatRows=1)
        tbl.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#cccccc")), ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#eef5f3")), ("VALIGN", (0, 0), (-1, -1), "TOP"),
                                 ("LEFTPADDING", (0, 0), (-1, -1), 3), ("RIGHTPADDING", (0, 0), (-1, -1), 3), ("TOPPADDING", (0, 0), (-1, -1), 2), ("BOTTOMPADDING", (0, 0), (-1, -1), 2)]))
        story.append(tbl)
    story.append(Paragraph(f"1. Décisions prises ({len(decided)})", h))
    if decided:
        table([[Paragraph(escape(d["point"]), small), Paragraph(escape(d["decision"]), base), Paragraph(escape(d.get("owner") or "—"), base), Paragraph(escape(d.get("deadline") or "—"), base)] for d in decided],
              ["Point traité", "Décision", "Responsable", "Échéance"], [58 * mm, 76 * mm, 26 * mm, 22 * mm])
    else:
        story.append(Paragraph("Aucune.", small))
    story.append(Paragraph(f"2. Points reportés ({len(postponed)})", h))
    if postponed:
        table([[Paragraph(escape(p["point"]), base), Paragraph(escape(p.get("note") or "—"), small), Paragraph(escape(p.get("owner") or "—"), base), Paragraph(escape(p.get("deadline") or "—"), base)] for p in postponed],
              ["Point", "Motif / suite", "Responsable", "Nouvelle échéance"], [76 * mm, 58 * mm, 26 * mm, 22 * mm])
    else:
        story.append(Paragraph("Aucun.", small))
    if dropped:
        story.append(Paragraph(f"3. Points abandonnés ({len(dropped)})", h))
        for p in dropped:
            story.append(Paragraph(f"• {escape(p['point'])}" + (f" — {escape(p['note'])}" if p.get("note") else ""), base))
    if remarks:
        story.append(Paragraph("Remarques", h))
        story.append(Paragraph(escape(remarks).replace("\n", "<br/>"), base))
    remaining = state["open_points"]
    story.append(Paragraph(f"État du dossier après réunion : {len([e for e in state['decisions'] if e['status'] == 'current'])} décisions courantes, {len(remaining)} point(s) encore ouvert(s) (révision {state.get('revision', 0)}).", small))
    story += [Spacer(1, 6), Paragraph("Compte rendu établi depuis l'état du dossier ConstruPilot. Les décisions d'exécution relèvent de la MOE / du BET / du contrôleur technique.", small)]
    annex = []
    with_photos = [("Décision", d) for d in decided if d.get("photos")] + [("Point reporté", p) for p in postponed if p.get("photos")] + [("Point abandonné", p) for p in dropped if p.get("photos")]
    if with_photos and photo_bytes:
        annex += [Paragraph("Annexe — photos épinglées des points traités", h), Paragraph("Photos issues de l'état du dossier (avant / après), telles qu'épinglées sur chaque point.", small), Spacer(1, 4)]
        for label, item in with_photos:
            cells = []
            for p in (item.get("photos") or [])[:2]:
                raw = photo_bytes.get(p.get("doc_id"))
                if not raw:
                    continue
                im = RLImage(io.BytesIO(raw)); ratio = im.imageHeight / float(im.imageWidth)
                w = 80 * mm; hgt = w * ratio
                if hgt > 70 * mm: hgt = 70 * mm; w = hgt / ratio
                im.drawWidth, im.drawHeight = w, hgt
                cells.append([im, Paragraph(f"{'avant' if p.get('phase') == 'before' else 'après'} · {(p.get('taken_at') or '')[:10]}", small)])
            if not cells:
                continue
            annex.append(Paragraph(f"<b>{escape(label)}</b> — {escape(item['point'])}", base))
            tbl = Table([cells], colWidths=[85 * mm] * len(cells))
            tbl.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0), ("BOTTOMPADDING", (0, 0), (-1, -1), 6)]))
            annex += [tbl, Spacer(1, 4)]
    flow = [KeepInFrame(A4[0] - 28 * mm, A4[1] - 24 * mm, story, mode="shrink")]
    if len(annex) > 3:
        flow += [PageBreak(), *annex]
    doc.build(flow)
    return buf.getvalue()


async def pin_photo(db, conversation_id: str, user_id: str, entry_id: str, photo: dict) -> dict:
    """Attach a dated site photo (existing assistant document) to an entry: phase before/after a decision."""
    state = await get_state(db, conversation_id, user_id)
    for section in SECTIONS:
        for e in state[section]:
            if e["entry_id"] == entry_id:
                photos = [p for p in e.get("photos", []) if p["doc_id"] != photo["doc_id"]]
                photos.append(photo)
                e["photos"] = sorted(photos, key=lambda p: (p.get("taken_at") or "", p["doc_id"]))[:12]
                e["updated_at"] = _now()
                state["revision"] += 1
                state["updated_at"] = _now()
                await db.assistant_project_state.update_one({"conversation_id": conversation_id, "user_id": user_id}, {"$set": state}, upsert=True)
                await db.assistant_project_state_log.insert_one({"conversation_id": conversation_id, "user_id": user_id, "revision": state["revision"], "section": section,
                                                                 "op": "pin_photo", "entry": {"entry_id": entry_id}, "photo": photo, "at": state["updated_at"]})
                return {"ok": True, "section": section, "entry_id": entry_id, "photos": e["photos"], "revision": state["revision"]}
    return {"ok": False, "error": "Entrée introuvable"}


async def unpin_photo(db, conversation_id: str, user_id: str, entry_id: str, doc_id: str) -> dict:
    state = await get_state(db, conversation_id, user_id)
    for section in SECTIONS:
        for e in state[section]:
            if e["entry_id"] == entry_id and any(p["doc_id"] == doc_id for p in e.get("photos", [])):
                e["photos"] = [p for p in e["photos"] if p["doc_id"] != doc_id]
                state["revision"] += 1
                state["updated_at"] = _now()
                await db.assistant_project_state.update_one({"conversation_id": conversation_id, "user_id": user_id}, {"$set": state})
                await db.assistant_project_state_log.insert_one({"conversation_id": conversation_id, "user_id": user_id, "revision": state["revision"], "section": section,
                                                                 "op": "unpin_photo", "entry": {"entry_id": entry_id}, "photo": {"doc_id": doc_id}, "at": state["updated_at"]})
                return {"ok": True, "photos": e["photos"], "revision": state["revision"]}
    return {"ok": False, "error": "Photo introuvable sur cette entrée"}
