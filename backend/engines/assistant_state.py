"""Project state of a conversation: current decisions (with their source), documents set aside (with reason), open points.
Kept outside the chat history so a later correction changes only the entry concerned; editable by the user and by the assistant."""
import uuid
from datetime import datetime, timezone

SECTIONS = ("decisions", "discarded_documents", "open_points")
STATUS = ("current", "superseded", "to_confirm")

STATE_TOOL = {"type": "function", "name": "update_project_state", "strict": True,
              "description": "Atualiza o estado do processo da conversa (decisões em vigor com a sua fonte, documentos afastados com motivo, pontos em aberto). Uma entrada por facto; para corrigir, retoma o mesmo entry_id — as outras entradas não mudam. remove=true retira a entrada.",
              "parameters": {"type": "object", "properties": {
                  "section": {"type": "string", "enum": list(SECTIONS)},
                  "entry_id": {"type": ["string", "null"], "description": "identificador de uma entrada existente a corrigir, null para uma nova"},
                  "statement": {"type": "string", "description": "decisão, documento afastado ou ponto em aberto, numa frase factual"},
                  "source": {"type": "string", "description": "peça, página, cota, mensagem do utilizador ou referência que fundamenta a entrada"},
                  "status": {"type": "string", "enum": list(STATUS)},
                  "kind": {"type": "string", "enum": ["schema_de_principe", "validation_execution", "fait", "hypothese", "action"],
                           "description": "natureza: um esquema de princípio nunca é uma validação técnica de execução"},
                  "owner": {"type": ["string", "null"], "description": "responsável pela ação ou pelo ponto (nome / função), null se desconhecido"},
                  "deadline": {"type": ["string", "null"], "description": "prazo (ex.: 22/09/2026 ou «antes da betonagem»), null se desconhecido"},
                  "remove": {"type": "boolean"}},
                  "required": ["section", "entry_id", "statement", "source", "status", "kind", "owner", "deadline", "remove"], "additionalProperties": False}}

PROTOCOL = "\nMétodo para um problema de obra (fotografia, e-mail, planta anexados): 1) lê realmente cada anexo (imagens fornecidas, read_document /\ninspect_document_region para as plantas) e cita o que lá vês com a página ou a zona; 2) regista os factos observados e depois, separadamente,\nas incertezas; 3) consulta as referências necessárias (NP EN, especificações LNEC, ficha do fabricante) apenas se a pesquisa estiver ativa e cita-as;\n4) propõe uma solução fundamentada com opções, limites e controlos; 5) produz o entregável pedido (carta, ata, esquema, PDF);\n6) controla a coerência entre peças, estado do processo e entregável. CÁLCULOS: os motores determinísticos calculam, tu restituis. Para o pré-certificado / classe energética (REH) usa pre_certificado_reh; perdas de calor por divisão ou bomba de calor: calcul_aquecimento; piso radiante: calcul_piso_radiante (só com as perdas por divisão) ou calcul_lotes_tecnicos para a cadeia completa (isolamento → perdas → piso radiante → bomba de calor → eletricidade → canalização → solar); isolamento de paredes (ETICS, U, Umáx, condensações): calcul_isolamento; eletricidade (RTIEBT) ou canalização e esgotos (DR 23/95): calcul_instalacoes; fotovoltaico: calcul_photovoltaique; solar térmico: verificar_solar_termico; caleiras, tubos de queda, fossa séptica, ventilação: calcul_redes; pátio rebaixado / pátio inglês: calcul_patio_pluvial; vento, neve, inclinação de telhas: calcul_couverture; acessibilidade (DL 163/2006): verifier_accessibilite; viga, pilar, laje, lintel, sapata, punçoamento ou escada: calcul_structure; pormenor de janela / porta-janela / estore / caixa: draw_window_detail. NUNCA faças à mão (nem num PDF create_downloadable_file) um cálculo que um destes motores faz, nem uma «planta cotada» desenhada com texto ou caracteres: se faltarem dados essenciais (dimensões, U, divisões), pergunta-os de forma precisa ou chama o motor com null nos campos desconhecidos (o motor assinala as hipóteses). Para um esquema de corte / ligação de parede, utiliza draw_section_schema (desenho cotado legível a partir das cotas do processo) em vez de uma ilustração IA; reserva create_downloadable_file JPG para ambientes. Nunca respondas de forma genérica quando uma peça estiver anexada: se a\npeça não permitir concluir, diz com precisão o que falta. Um esquema de princípio (JPG/PDF produzido) ilustra uma intenção; nunca é\numa validação técnica de execução, que cabe ao gabinete de projeto ou à fiscalização — escreve-o no entregável e no estado do processo.\nEstado do processo: após cada decisão, documento afastado ou ponto em aberto, chama update_project_state (uma entrada por facto, fonte\nobrigatória); uma correção do utilizador atualiza a entrada em causa (mesmo entry_id) e relança apenas o resultado que dela depende.\nO estado do processo anexado à mensagem é a referência atual: não contradigas uma decisão «current» sem o anunciar e a atualizar.\n"


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
            return {"ok": False, "error": "Entrada não encontrada"}
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
        return "Estado do processo: vazio (nenhuma decisão registada)."
    lines = ["Estado do processo (referência atual, a atualizar com update_project_state):"]
    labels = {"decisions": "Decisões", "discarded_documents": "Documentos afastados", "open_points": "Pontos em aberto"}
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
    status = {"current": "courante", "superseded": "remplacée", "to_confirm": "a confirmar"}
    kind = {"schema_de_principe": "esquema de princípio", "validation_execution": "validação de execução", "fait": "fait", "hypothese": "hypothèse", "action": "action"}
    story = [Paragraph("ConstruPilot — Estado do processo", t), Paragraph(escape(title), base)]
    sub = f"Revisão {state.get('revision', 0)} · atualizado em {str(state.get('updated_at', ''))[:16].replace('T', ' ')}"
    if meeting:
        sub += f' · Reunião de obra: {escape(meeting)}'
    story += [Paragraph(sub, small), Spacer(1, 4)]
    def section(label, entries, empty):
        story.append(Paragraph(f"{label} ({len(entries)})", h))
        if not entries:
            story.append(Paragraph(empty, small)); return
        has_photos = any(thumbs(e) for e in entries)
        rows = [[Paragraph("<b>Enunciado</b>", small), Paragraph("<b>Source</b>", small), Paragraph("<b>Estado</b>", small)] + ([Paragraph("<b>Fotografias antes / depois</b>", small)] if has_photos else [])]
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
    section("Decisões em vigor", [e for e in state["decisions"] if e["status"] != "superseded"], "Nenhuma decisão registada.")
    section("Pontos em aberto", state["open_points"], "Nenhum ponto em aberto.")
    section("Documentos afastados", state["discarded_documents"], "Nenhum documento afastado.")
    superseded = [e for e in state["decisions"] if e["status"] == "superseded"]
    if superseded:
        story.append(Paragraph("Decisões substituídas: " + " ; ".join(escape(e["statement"]) for e in superseded), small))
    story += [Spacer(1, 6), Paragraph("Documento de apoio à decisão proveniente do assistente e das correções do utilizador. Um esquema de princípio ilustra uma intenção; não vale como validação técnica de execução (gabinete de projeto / fiscalização).", small)]
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
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=14 * mm, rightMargin=14 * mm, topMargin=12 * mm, bottomMargin=12 * mm, title="Ordem de trabalhos")
    base = ParagraphStyle("b", fontName="Helvetica", fontSize=8.4, leading=10.8)
    small = ParagraphStyle("s", parent=base, fontSize=7, leading=8.6, textColor=colors.HexColor("#555555"))
    h = ParagraphStyle("h", parent=base, fontName="Helvetica-Bold", fontSize=10, leading=13, spaceBefore=6, spaceAfter=2, textColor=colors.HexColor("#137566"))
    t = ParagraphStyle("t", parent=base, fontName="Helvetica-Bold", fontSize=14, leading=17)
    story = [Paragraph("Ordem de trabalhos — reunião de obra", t), Paragraph(escape(title), base),
             Paragraph(f"Data / hora: {escape(meeting or 'a fixar')} · Participants : {escape(attendees or 'Dono de obra, projetista/arquiteto, empresa, gabinete de projeto se necessário')}", small), Spacer(1, 4)]
    def table(rows_data, cols, widths):
        rows = [[Paragraph(f"<b>{c}</b>", small) for c in cols]] + rows_data
        tbl = Table(rows, colWidths=widths, repeatRows=1)
        tbl.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#cccccc")), ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#eef5f3")), ("VALIGN", (0, 0), (-1, -1), "TOP"),
                                 ("LEFTPADDING", (0, 0), (-1, -1), 3), ("RIGHTPADDING", (0, 0), (-1, -1), 3), ("TOPPADDING", (0, 0), (-1, -1), 2), ("BOTTOMPADDING", (0, 0), (-1, -1), 2)]))
        story.append(tbl)
    n = 0
    opens = state["open_points"]
    story.append(Paragraph(f'1. Pontos a decidir ({len(opens)})', h))
    if opens:
        rows = []
        for e in opens:
            n += 1
            rows.append([Paragraph(str(n), small), Paragraph(escape(e["statement"]) + f"<br/><font color='#555555' size='7'>Source : {escape(e['source'])}</font>", base),
                         Paragraph(escape(e.get("owner") or "a designar"), base), Paragraph(escape(e.get("deadline") or "a fixar"), base), Paragraph("", base)])
        table(rows, ["#", "Point / question", "Responsável", "Vencimento", "Decisão em reunião"], [7 * mm, 88 * mm, 28 * mm, 24 * mm, 35 * mm])
    else:
        story.append(Paragraph("Nenhum ponto em aberto.", small))
    confirm = [e for e in state["decisions"] if e["status"] == "to_confirm"]
    story.append(Paragraph(f'2. Decisões a confirmar ({len(confirm)})', h))
    if confirm:
        table([[Paragraph(escape(e["statement"]), base), Paragraph(escape(e["source"]), small), Paragraph(escape(e.get("owner") or "—"), base), Paragraph("", base)] for e in confirm],
              ["Decisão proposta", "Fonte", "Responsável", "Confirmada? (S/N)"], [90 * mm, 44 * mm, 24 * mm, 24 * mm])
    else:
        story.append(Paragraph("Nenhuma.", small))
    current = [e for e in state["decisions"] if e["status"] == "current"]
    story.append(Paragraph(f'3. Decisões adquiridas a registar na ata ({len(current)})', h))
    for e in current:
        tag = " <font color=\'#8a6d00\'>[esquema de princípio — não é uma validação de execução]</font>" if e.get("kind") == "schema_de_principe" else ""
        story.append(Paragraph(f"• {escape(e['statement'])}{tag} <font color='#555555' size='7'>({escape(e['source'])})</font>", base))
    disc = state["discarded_documents"]
    if disc:
        story.append(Paragraph(f'4. Documentos afastados ({len(disc)})', h))
        for e in disc:
            story.append(Paragraph(f"• {escape(e['statement'])} <font color='#555555' size='7'>({escape(e['source'])})</font>", base))
    story += [Spacer(1, 6), Paragraph("Ordem de trabalhos preparada a partir do estado do processo ConstruPilot (revisão " + str(state.get("revision", 0)) + "). As decisões de execução cabem ao projetista / gabinete de projeto / fiscalização.", small)]
    doc.build([KeepInFrame(A4[0] - 28 * mm, A4[1] - 24 * mm, story, mode="shrink")])
    return buf.getvalue()


async def apply_meeting(db, conversation_id: str, user_id: str, *, meeting: str, attendees: str | None, items: list[dict], remarks: str | None, title: str, photo_bytes: dict | None = None) -> dict:
    """Meeting outcome → dossier: each item closes/postpones/drops an open point or confirms a decision; then a one-page report PDF (+ annexe photos épinglées)."""
    state = await get_state(db, conversation_id, user_id)
    source = f'Reunião de obra {meeting}'
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
                await apply_entry(db, conversation_id, user_id, {"section": "decisions", "entry_id": entry["entry_id"], "statement": entry["statement"], "source": f"{entry['source']} ; confirmada em {source}",
                                                                  "status": "current", "kind": entry.get("kind", "fait"), "owner": it.get("owner") or entry.get("owner"), "deadline": it.get("deadline") or entry.get("deadline")}, author="user")
            else:
                await apply_entry(db, conversation_id, user_id, {"section": "decisions", "entry_id": None, "statement": text, "source": f"{source} — tranche : {entry['statement'][:120]}",
                                                                  "status": "current", "kind": "action" if it.get("owner") else "fait", "owner": it.get("owner"), "deadline": it.get("deadline")}, author="user")
                await apply_entry(db, conversation_id, user_id, {"section": section, "entry_id": entry["entry_id"], "statement": entry["statement"], "source": entry["source"], "remove": True}, author="user")
            decided.append({"point": entry["statement"], "decision": text or entry["statement"], "owner": it.get("owner") or entry.get("owner"), "deadline": it.get("deadline") or entry.get("deadline"), "photos": entry.get("photos") or []})
        elif outcome == "postponed":
            await apply_entry(db, conversation_id, user_id, {"section": section, "entry_id": entry["entry_id"], "statement": entry["statement"], "source": f"{entry['source']} ; adiado em {source}",
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
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=14 * mm, rightMargin=14 * mm, topMargin=12 * mm, bottomMargin=12 * mm, title="Ata de reunião")
    base = ParagraphStyle("b", fontName="Helvetica", fontSize=8.4, leading=10.8)
    small = ParagraphStyle("s", parent=base, fontSize=7, leading=8.6, textColor=colors.HexColor("#555555"))
    h = ParagraphStyle("h", parent=base, fontName="Helvetica-Bold", fontSize=10, leading=13, spaceBefore=6, spaceAfter=2, textColor=colors.HexColor("#137566"))
    t = ParagraphStyle("t", parent=base, fontName="Helvetica-Bold", fontSize=14, leading=17)
    story = [Paragraph("Ata de reunião de obra", t), Paragraph(escape(title), base),
             Paragraph(f"Reunião: {escape(meeting)} · Participants : {escape(attendees or '—')} · Redigida em {_now()[:10]}", small), Spacer(1, 4)]
    def table(rows_data, cols, widths):
        rows = [[Paragraph(f"<b>{c}</b>", small) for c in cols]] + rows_data
        tbl = Table(rows, colWidths=widths, repeatRows=1)
        tbl.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#cccccc")), ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#eef5f3")), ("VALIGN", (0, 0), (-1, -1), "TOP"),
                                 ("LEFTPADDING", (0, 0), (-1, -1), 3), ("RIGHTPADDING", (0, 0), (-1, -1), 3), ("TOPPADDING", (0, 0), (-1, -1), 2), ("BOTTOMPADDING", (0, 0), (-1, -1), 2)]))
        story.append(tbl)
    story.append(Paragraph(f'1. Decisões tomadas ({len(decided)})', h))
    if decided:
        table([[Paragraph(escape(d["point"]), small), Paragraph(escape(d["decision"]), base), Paragraph(escape(d.get("owner") or "—"), base), Paragraph(escape(d.get("deadline") or "—"), base)] for d in decided],
              ["Ponto tratado", "Decisão", "Responsável", "Vencimento"], [58 * mm, 76 * mm, 26 * mm, 22 * mm])
    else:
        story.append(Paragraph("Nenhuma.", small))
    story.append(Paragraph(f'2. Pontos adiados ({len(postponed)})', h))
    if postponed:
        table([[Paragraph(escape(p["point"]), base), Paragraph(escape(p.get("note") or "—"), small), Paragraph(escape(p.get("owner") or "—"), base), Paragraph(escape(p.get("deadline") or "—"), base)] for p in postponed],
              ["Point", "Motif / suite", "Responsável", "Novo prazo"], [76 * mm, 58 * mm, 26 * mm, 22 * mm])
    else:
        story.append(Paragraph("Nenhum.", small))
    if dropped:
        story.append(Paragraph(f'3. Pontos abandonados ({len(dropped)})', h))
        for p in dropped:
            story.append(Paragraph(f"• {escape(p['point'])}" + (f" — {escape(p['note'])}" if p.get("note") else ""), base))
    if remarks:
        story.append(Paragraph("Observações", h))
        story.append(Paragraph(escape(remarks).replace("\n", "<br/>"), base))
    remaining = state["open_points"]
    story.append(Paragraph(f"Estado do processo após a reunião: {len([e for e in state['decisions'] if e['status'] == 'current'])} decisões em vigor, {len(remaining)} ponto(s) ainda em aberto (revisão {state.get('revision', 0)}).", small))
    story += [Spacer(1, 6), Paragraph("Ata elaborada a partir do estado do processo ConstruPilot. As decisões de execução cabem ao projetista / gabinete de projeto / fiscalização.", small)]
    annex = []
    with_photos = [("Decisão", d) for d in decided if d.get("photos")] + [("Ponto adiado", p) for p in postponed if p.get("photos")] + [("Ponto abandonado", p) for p in dropped if p.get("photos")]
    if with_photos and photo_bytes:
        annex += [Paragraph("Anexo — fotografias fixadas dos pontos tratados", h), Paragraph("Fotografias provenientes do estado do processo (antes / depois), tal como fixadas em cada ponto.", small), Spacer(1, 4)]
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
    return {"ok": False, "error": "Entrada não encontrada"}


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
    return {"ok": False, "error": "Fotografia não encontrada nesta entrada"}
