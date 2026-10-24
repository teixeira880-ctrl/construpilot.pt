import { AssistantMark } from "@/components/assistant/AssistantMark";
import { useStudioCopy } from "@/components/assistant/studioCopy";
import { lastConversation, rememberConversation, submittedJob } from "@/components/assistant/jobActivity";
import "@/components/assistant/AssistantStudio.css";
import { useEffect, useRef, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { Brain, FileText, Loader2, Mic, Paperclip, Plus, Send, Square, Search, History, SlidersHorizontal, X, Mail, Ruler, ClipboardList, Wrench, ArrowDown, ImagePlus, ChevronDown, Trash2, MessageSquare, ArrowUpRight, Globe, FolderArchive } from "lucide-react";
import { toast } from "sonner";
import { api, uploadPlan } from "@/lib/api";
import { Dialog, DialogContent, DialogTitle, DialogDescription } from "@/components/ui/dialog";
import { useI18n } from "@/context/I18nContext";
import { normalizeSearch, useWorkspaceCopy } from "@/components/workspace/copy";
import { Button } from "@/components/ui/button";
import { ConversationJobs, useConversationJobs } from "@/components/assistant/ConversationJobs";
import { CalculationsPanel } from "@/components/assistant/CalculationsPanel";
import { ProjectStatePanel } from "@/components/assistant/ProjectStatePanel";
import { FallbackBanner } from "@/components/assistant/FallbackBanner";
import { DocumentViewerProvider } from "@/components/assistant/DocumentViewer";
import { PrivateImage } from "@/components/assistant/PrivateMedia";
import { useBackgroundCopy } from "@/components/assistant/backgroundCopy";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger, DropdownMenuSeparator } from "@/components/ui/dropdown-menu";
import { useQuoteCopy } from "@/components/assistant/quoteCopy";

import { CadImportInfo, CadUnitPicker } from "@/components/planTakeoff/CadImportInfo";
import { useAuth } from "@/context/AuthContext";
import { useConfirm } from "@/components/ConfirmProvider";
import { usePermissions } from "@/context/PermissionContext";
import { isProfessional } from "@/components/workspace/navigation";
import { ChantierContextBar, useChantierContext } from "@/components/chantiers/ChantierContextBar";
import { useDossierImport, DossierChips } from "@/components/assistant/DossierImport";

export default function Assistant() {
  const ui = useWorkspaceCopy();
  const studio = useStudioCopy();
  const quoteText = useQuoteCopy();
  const bg = useBackgroundCopy();
  const [searchParams, setSearchParams] = useSearchParams();
  const { lang } = useI18n();
  const confirm = useConfirm();
  const { user } = useAuth();
  const chantierParam = searchParams.get("chantier") || "";
  const requestedConversation = searchParams.get("conversation") || (!chantierParam && lastConversation(user?.user_id));
  const { can } = usePermissions();
  const canPlan = isProfessional(user) && can("dashboard");
  const canQuote = isProfessional(user) && can("devis");
  const [transcribing, setTranscribing] = useState(false);
  const [historyOpen, setHistoryOpen] = useState(false);
  const [optionsOpen, setOptionsOpen] = useState(false);
  const [historyQuery, setHistoryQuery] = useState("");
  const [historyError, setHistoryError] = useState(false);
  const [loadingConversation, setLoadingConversation] = useState(false);
  const [showJump, setShowJump] = useState(false);
  const textareaRef = useRef(null);
  const uploadRef = useRef(null);
  const dossierRef = useRef(null);
  const folderRef = useRef(null);
  const dossierImport = useDossierImport();
  const uploadKind = useRef("doc");
  const activeConversation = useRef(null);
  const mounted = useRef(true);
  const messagesRef = useRef(null);
  const historyButtonRef = useRef(null);
  const navigationLock = useRef(false);
  const textDrafts = useRef({});
  const followMessages = useRef(true);
  const [cadFile, setCadFile] = useState(null);
  const [mode, setMode] = useState("thorough");
  const [webEnabled, setWebEnabled] = useState(true);
  const sendLock = useRef(false);
  const retrySubmission = useRef(null);
  const handledReplies = useRef(new Set());
  const recorderRef = useRef(null);
  const [convs, setConvs] = useState([]);
  const [conv, setConv] = useState(null);
  const [plans, setPlans] = useState([]);
  const [activePlans, setActivePlans] = useState([]);
  const [pending, setPending] = useState([]);
  const [docs, setDocs] = useState([]);
  const [activeDocs, setActiveDocs] = useState([]);
  const [pickFile, setPickFile] = useState(null);
  const [prefs, setPrefs] = useState([]);
  const [text, setText] = useState(() => searchParams.get("resumeQuote")
    ? `Retoma o orçamento existente (doc_id: ${searchParams.get("resumeQuote")}): relê-o com read_quote_draft e depois aplica as seguintes alterações — `
    : searchParams.get("intent") === "supervise" ? "Verifica os dados do meu processo, identifica as incoerências e corrige automaticamente os valores recalculáveis. O meu pedido: " : searchParams.get("intent") === "quote" ? quoteText("quotePrompt") : searchParams.get("intent") === "research" ? "Pesquisa documental técnica (com fontes verificáveis) — país da obra: PT. Pergunta: " : "");
  const [busy, setBusy] = useState(false);
  const [rec, setRec] = useState(null);
  const [uploading, setUploading] = useState(false);
  

  const loadConvs = () => api.get("/assistant/conversations").then((r) => { setConvs(r.data); setHistoryError(false); }).catch(() => setHistoryError(true));
  const activeChantierId = conv?.chantier_id || chantierParam;
  const { chantier: activeChantier } = useChantierContext(activeChantierId);
  const convParams = (conversationId) => (activeChantierId ? { conversation: conversationId, chantier: activeChantierId } : { conversation: conversationId });
  useEffect(() => {
    if (!chantierParam || searchParams.get("conversation")) return;
    let active = true;
    (async () => {
      try {
        const { data: list } = await api.get("/assistant/conversations");
        let target = list.find((c) => c.chantier_id === chantierParam);
        if (!target) target = (await api.post("/assistant/conversations", { chantier_id: chantierParam })).data;
        if (active) setSearchParams({ conversation: target.conversation_id, chantier: chantierParam }, { replace: true });
      } catch { if (active) toast.error("Processo de obra inacessível"); }
    })();
    return () => { active = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [chantierParam]);
  useEffect(() => {
    if (!requestedConversation || requestedConversation === activeConversation.current) return;
    let active = true;
    setLoadingConversation(true);
    api.get(`/assistant/conversations/${encodeURIComponent(requestedConversation)}`).then(({ data }) => {
      if (!active) return;
      activeConversation.current = data.conversation_id;
      setConv(data); setActivePlans(data.active_plans || []); setActiveDocs(data.active_docs || []); setPending([]); dossierImport.reset();
    }).catch(() => { if (active) setHistoryError(true); }).finally(() => { if (active) setLoadingConversation(false); });
    return () => { active = false; };
  }, [requestedConversation]);
  useEffect(() => {
    loadConvs();
    api.get("/assistant/settings").then(r => setWebEnabled(r.data.web_enabled)).catch(() => {});
    api.get("/assistant/preferences").then((r) => setPrefs(r.data)).catch(() => {});
    api.get("/assistant/documents").then((r) => setDocs(r.data)).catch(() => {});
  }, []);
  useEffect(() => {
    if (!canPlan) { setPlans([]); return; }
    let current = true;
    api.get("/takeoffs").then(r => { if (current) setPlans(r.data.plans || r.data.items || (Array.isArray(r.data) ? r.data : [])); }).catch(() => {});
    return () => { current = false; };
  }, [canPlan]);
  useEffect(() => {
    mounted.current = true;
    return () => { mounted.current = false; if (recorderRef.current) { recorderRef.current.onstop = null; recorderRef.current.stream.getTracks().forEach(t => t.stop()); } };
  }, []);
  useEffect(() => { rememberConversation(user?.user_id, conv?.conversation_id); }, [conv?.conversation_id, user?.user_id]);
  const jobFollow = useConversationJobs(conv?.conversation_id, (data) => {
    if (activeConversation.current !== data.conversation_id) return;
    setConv(data);
    let refreshPreferences = false, received = false;
    for (const message of data.messages || []) {
      if (message.role !== "assistant" || handledReplies.current.has(message.message_id)) continue;
      handledReplies.current.add(message.message_id); received = true;
      for (const action of message.actions || []) {
        if (action.tool === "update_work_draft" && action.result?.ok) window.dispatchEvent(new CustomEvent("construpilot:draft-updated", { detail: action.result.draft }));
        if (action.tool === "save_user_preference" && action.result?.ok) refreshPreferences = true;
      }
    }
    if (refreshPreferences) api.get("/assistant/preferences").then(({ data: preferences }) => setPrefs(preferences)).catch(() => {});
    if (received) loadConvs();
  });
  const running = conv?.jobs?.some((job) => ["queued", "running", "preparing"].includes(job.status));
  useEffect(() => {
    const area = messagesRef.current;
    if (area && followMessages.current) area.scrollTop = area.scrollHeight;
  }, [conv?.messages?.length, conv?.conversation_id, conv?.jobs]);
  useEffect(() => { const input = textareaRef.current; if (input) { input.style.height = "auto"; input.style.height = `${Math.min(input.scrollHeight, 140)}px`; } }, [text]);
  const seedText = (value) => { setText(value); requestAnimationFrame(() => textareaRef.current?.focus()); };
  const open = async (id) => {
    if (sendLock.current || navigationLock.current || uploading || rec || transcribing || pickFile || cadFile) return;
    navigationLock.current = true; setLoadingConversation(true);
    textDrafts.current[conv?.conversation_id || "new"] = text;
    try {
      const r = await api.get(`/assistant/conversations/${id}`);
      if (!mounted.current) return;
      followMessages.current = true; setShowJump(false);
      activeConversation.current = id;
      setConv(r.data); setActivePlans(r.data.active_plans || []); setActiveDocs(r.data.active_docs || []); setPending([]); dossierImport.reset();
      setSearchParams({ conversation: id }, { replace: true });
      setText(textDrafts.current[id] || ""); setHistoryOpen(false);
    } catch { toast.error(ui("chatError")); }
    finally { navigationLock.current = false; setLoadingConversation(false); }
  };
  const create = async () => {
    if (sendLock.current || navigationLock.current || uploading || rec || transcribing || pickFile || cadFile) return;
    navigationLock.current = true; setLoadingConversation(true);
    textDrafts.current[conv?.conversation_id || "new"] = text;
    try {
      const r = await api.post("/assistant/conversations", activeChantierId ? { chantier_id: activeChantierId } : {});
      if (!mounted.current) return;
      followMessages.current = true; setShowJump(false);
      activeConversation.current = r.data.conversation_id;
      setConv({ ...r.data, messages: [] }); setActivePlans([]); setActiveDocs([]); setPending([]); dossierImport.reset(); setText(""); setHistoryOpen(false); loadConvs();
      setSearchParams(convParams(r.data.conversation_id), { replace: true });
    } catch { toast.error(ui("chatError")); }
    finally { navigationLock.current = false; setLoadingConversation(false); }
  };
  const nameOf = (id) => plans.find((p) => p.plan_id === id)?.filename || docs.find((d) => d.doc_id === id)?.filename || id;
  const removeConv = async (c) => {
    const pt = lang === "pt";
    const ok = await confirm({ title: pt ? "Mover esta conversa para a reciclagem?" : "Mover esta conversa para o lixo?", description: pt ? `« ${c.title} » ficará recuperável durante 30 dias.` : `« ${c.title} » continuará recuperável durante 30 dias no lixo.`, confirmLabel: pt ? "Mover" : "Mover para o lixo" });
    if (!ok) return;
    try {
      await api.delete(`/assistant/conversations/${c.conversation_id}`);
      toast.success(pt ? "Conversa movida para a reciclagem" : "Conversa movida para o lixo — recuperável durante 30 dias", { action: { label: pt ? "Reciclagem" : "Lixo", onClick: () => window.location.assign("/corbeille") } });
      if (conv?.conversation_id === c.conversation_id) { activeConversation.current = null; setConv(null); setActivePlans([]); setActiveDocs([]); setPending([]); dossierImport.reset(); setSearchParams({}, { replace: true }); }
      loadConvs();
    } catch (e) { toast.error(e?.response?.data?.detail || ui("chatError")); }
  };

  const send = async () => {
    if ((!text.trim() && !pending.length && !dossierImport.ids.length) || sendLock.current || navigationLock.current || uploading || dossierImport.uploading || rec || transcribing || cadFile) return;
    if (activeDocs.length > 10 || activePlans.length > 5) return toast.error(bg("maxFiles"));
    followMessages.current = true; setShowJump(false);
    sendLock.current = true; setBusy(true);
    let c = conv;
    if (!c) { try { const r = await api.post("/assistant/conversations", activeChantierId ? { chantier_id: activeChantierId } : {}); c = { ...r.data, messages: [] }; activeConversation.current = c.conversation_id; setConv(c); } catch { sendLock.current = false; setBusy(false); toast.error(ui("chatError")); return; } }
    const content = text.trim() || (dossierImport.ids.length ? "Faça o inventário deste processo." : bg("defaultPhoto"));
    const payload = { conversation_id: c.conversation_id, text: content, response_mode: mode, web_enabled: webEnabled, plan_ids: activePlans, doc_ids: activeDocs, dossier_ids: dossierImport.ids, attachments: pending };
    const fingerprint = JSON.stringify(payload);
    if (retrySubmission.current?.fingerprint !== fingerprint) retrySubmission.current = { fingerprint, requestId: crypto.randomUUID() };
    const requestId = retrySubmission.current.requestId;
    let accepted = false;
    try {
      await api.post("/assistant/jobs", { ...payload, request_id: requestId });
      accepted = true; retrySubmission.current = null;
      submittedJob(user?.user_id, c.conversation_id);
      if (!mounted.current) return;
      textDrafts.current[c.conversation_id] = ""; setText(""); setPending([]);
      setSearchParams(convParams(c.conversation_id), { replace: true });
      const { data } = await api.get(`/assistant/conversations/${c.conversation_id}`);
      if (activeConversation.current === c.conversation_id) setConv(data);
      jobFollow.refresh(); loadConvs();
    } catch (e) {
      const detail = e.response?.data?.detail;
      if (!accepted) setText((draft) => draft || content);
      else jobFollow.refresh();
      toast.error(accepted ? bg("offline") : typeof detail === "string" ? detail : ui("assistantError"));
    } finally { sendLock.current = false; setBusy(false); }
  };

  const stop = async (jobId) => {
    try { await api.post(`/assistant/jobs/${jobId}/cancel`); jobFollow.refresh(); }
    catch { toast.error(ui("assistantError")); }
  };

  const toggleMic = async () => {
    if (rec) { rec.stop(); return; }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const mr = new MediaRecorder(stream); const chunks = [];
      mr.ondataavailable = (e) => chunks.push(e.data);
      mr.onstop = async () => {
        setRec(null); setTranscribing(true); stream.getTracks().forEach((t) => t.stop());
        const fd = new FormData(); fd.append("file", new Blob(chunks, { type: "audio/webm" }), "dictee.webm");
        try { const r = await api.post("/assistant/transcribe", fd); setText((t) => (t ? t + " " : "") + r.data.text); } catch { toast.error(ui("transcriptionError")); } finally { setTranscribing(false); }
      };
      mr.start(); recorderRef.current = mr; setRec(mr);
    } catch { toast.error(ui("microphoneError")); }
  };

  const upload = async (file, as, cadUnit) => {
    if (as === "plan" && !canPlan) { toast.error(ui("accessDenied")); return; }
    const fd = new FormData(); fd.append("file", file); if (cadUnit) fd.append("cad_unit", cadUnit); setUploading(true); setPickFile(null); setCadFile(null);
    try {
      if (as === "plan") { const r = { data: await uploadPlan(fd) }; setPlans((p) => [r.data, ...p]); setActivePlans((a) => [...a, r.data.plan_id]); setPending((a) => [...a, r.data.plan_id]); }
      else { const r = await api.post("/assistant/documents", fd); setDocs((d) => [r.data, ...d]); setActiveDocs((a) => [...a, r.data.doc_id]); setPending((a) => [...a, r.data.doc_id]); }
      toast.success(ui("documentAdded"));
    } catch (e) { const detail = e?.response?.data?.detail; if (typeof detail === "string" && detail.includes("CAD_UNIT_REQUIRED")) setCadFile(file); else toast.error(typeof detail === "string" ? detail : ui("importError")); }
    finally { setUploading(false); }
  };
  const onPick = (file) => {
    const ext = file.name.toLowerCase().split(".").pop();
    const kind = ["dxf", "dwg"].includes(ext) ? "plan" : uploadKind.current;
    uploadKind.current = "doc";
    if (kind === "plan" ? activePlans.length >= 5 : activeDocs.length >= 10) return toast.error(bg("maxFiles"));
    upload(file, kind);
  };
  const onPickMany = async (files) => {
    const list = Array.from(files || []);
    const hasZip = list.some((f) => f.name.toLowerCase().endsWith(".zip"));
    if (hasZip || list.length > 10) { await dossierImport.importFiles(list); return; }   // processo completo (ZIP / dezenas de ficheiros)
    if (list.length <= 1) { if (list[0]) onPick(list[0]); return; }
    const room = 10 - activeDocs.length;
    if (list.length > room) toast.error(bg("maxFiles"));
    uploadKind.current = "doc";
    for (const f of list.slice(0, Math.max(0, room))) {
      if (["dxf", "dwg"].includes(f.name.toLowerCase().split(".").pop())) continue;
      await upload(f, "doc");
    }
  };

  const activePrefs = prefs.filter((p) => p.active);
  const locked = busy || loadingConversation || uploading || !!rec || transcribing;
  const matchingConvs = convs.filter(c => normalizeSearch(c.title).includes(normalizeSearch(historyQuery)));
  const history = (scope) => <div className="assistant-history">
    <div className="assistant-history-heading"><strong>{ui("history")}</strong><span>{convs.length}</span></div>
    <p className="assistant-history-hint">{studio("historyHint")}</p>
    <Button className="assistant-new-button justify-start h-11 text-xs" disabled={locked || !!pickFile || !!cadFile} onClick={create} data-testid={`assistant-new-${scope}`}><Plus size={16} />{ui("newChat")}</Button>
    <div className="workspace-search-field"><Search size={15} aria-hidden="true" /><input data-testid={`assistant-history-search-${scope}`} placeholder={ui("historySearch")} aria-label={ui("historySearch")} value={historyQuery} onChange={e => setHistoryQuery(e.target.value)} /></div>
    <div className="assistant-history-list">
      {historyError && <p role="alert" data-testid={`assistant-history-error-${scope}`}>{ui("historyError")} <button type="button" className="underline" onClick={loadConvs} data-testid={`assistant-history-retry-${scope}`}>{ui("retry")}</button></p>}
      {!historyError && !matchingConvs.length && <p data-testid={`assistant-history-empty-${scope}`}>{ui(historyQuery ? "noHistoryMatch" : "noHistory")}</p>}
      {matchingConvs.map(c => <div key={c.conversation_id} className="assistant-history-row"><button disabled={locked || !!pickFile || !!cadFile} onClick={() => open(c.conversation_id)} aria-current={conv?.conversation_id === c.conversation_id ? "true" : undefined} title={c.title} data-conversation-id={c.conversation_id} data-testid={`assistant-conv-${scope}-${c.conversation_id}`}><MessageSquare size={14} aria-hidden="true" /><span>{c.title}</span></button>
        <button type="button" className="assistant-history-delete" disabled={locked} aria-label={lang === "pt" ? "Mover para a reciclagem" : "Mover para o lixo"} title={lang === "pt" ? "Mover para a reciclagem" : "Mover para o lixo"} onClick={() => removeConv(c)} data-testid={`assistant-conv-delete-${scope}-${c.conversation_id}`}><Trash2 size={14} /></button></div>)}
    </div>
    <Link to="/preferences" className="text-xs flex items-center gap-2 border-t pt-3 min-h-11" data-testid={`assistant-prefs-link-${scope}`}><Brain size={16} className="text-primary shrink-0" /><span>{ui("preferences")}</span><span className="ms-auto text-muted-foreground" data-testid={`assistant-prefs-count-${scope}`}>{activePrefs.length}</span></Link>
  </div>;
  const prompts = lang === "pt" ? [
    "Prepara uma resposta profissional a este email. Destinatário e objetivo: \nEmail recebido: ",
    "Analisa as medidas interiores entre as faces dos muros da planta anexa. Verifica as cotas e indica o que precisa de confirmação. Âmbito: ",
    "Redige um relatório de obra com factos, decisões, ações, responsáveis e datas conhecidas. As minhas notas: ",
    "Ajuda-me a resolver este problema na obra. Verifica os documentos e propõe as próximas ações: ",
  ] : lang === "en" ? [
    "Draft a professional reply to this email. Recipient and goal: \nReceived email: ",
    "Analyse the internal face-to-face wall dimensions in the attached plan. Check dimensions and identify what needs confirmation. Scope: ",
    "Write a site report with observed facts, decisions, actions, owners and known dates. My notes: ",
    "Help me solve this site problem. Check the documents and suggest the next actions: ",
  ] : [
    "Prepara uma resposta profissional a este e-mail. Destinatário e objetivo: E-mail recebido: ",
    "Analisa as paredes interiores parede a parede da planta anexa. Identifica as faces, verifica as cotas e indica o que falta confirmar. Âmbito: ",
    "Redige uma ata com os factos constatados, decisões, ações, responsáveis e datas conhecidas. As minhas notas: ",
    "Ajuda-me a resolver este problema de obra. Verifica as peças, explica as causas possíveis e propõe as próximas ações: ",
  ];
  const removeContext = (id, kind) => {
    if (kind === "plan") setActivePlans(a => a.filter(x => x !== id)); else setActiveDocs(a => a.filter(x => x !== id));
    setPending(a => a.filter(x => x !== id));
  };
  return <DocumentViewerProvider><div className="assistant-workspace assistant-studio" data-testid="assistant-page">
    {history("desktop")}
    <Dialog open={historyOpen} onOpenChange={setHistoryOpen}>
      <DialogContent className="assistant-history-dialog assistant-studio" data-testid="assistant-history-dialog" onCloseAutoFocus={e => { e.preventDefault(); historyButtonRef.current?.focus(); }}>
        <DialogTitle>{ui("history")}</DialogTitle><DialogDescription className="sr-only">{ui("historySearch")}</DialogDescription>{historyOpen && history("mobile")}
      </DialogContent>
    </Dialog>
    <section className="assistant-conversation" aria-label={ui("assistant")}>
      <header className="assistant-topbar">
        <AssistantMark size={42} className="shrink-0" />
        <div className="assistant-brand-text"><h1>{ui("assistant")}</h1><p title={conv?.title}>{conv?.title || studio("subtitle")}</p></div>
        <div className="assistant-topbar-actions">
          <Button ref={historyButtonRef} variant="ghost" className="assistant-mobile-history" onClick={() => setHistoryOpen(true)} aria-label={ui("history")} data-testid="assistant-history-open"><History size={17} /><span>{ui("history")}</span></Button>
          <Button variant="outline" onClick={() => setOptionsOpen(v => !v)} aria-expanded={optionsOpen} aria-controls="assistant-options" aria-label={studio("contextTitle")} data-testid="assistant-options-toggle"><SlidersHorizontal size={16} /><span>{studio("context")}</span>{activePlans.length + activeDocs.length > 0 && <span className="assistant-context-count">{activePlans.length + activeDocs.length}</span>}</Button>
        </div>
      </header>
      {activeChantierId && <div className="px-3 pt-3"><ChantierContextBar chantierId={activeChantierId} chantier={activeChantier} /></div>}
      {running && <p role="status" className="px-4 py-2 text-xs text-primary border-b flex items-center gap-2" data-testid="assistant-background-status"><Loader2 size={14} className="animate-spin shrink-0" />{studio("backgroundHint")}</p>}
      {jobFollow.error && <p role="alert" className="px-4 py-2 text-xs text-amber-700" data-testid="assistant-background-error">{bg("offline")} <button className="underline" onClick={jobFollow.refresh} data-testid="assistant-background-refresh">{bg("refresh")}</button></p>}
      {optionsOpen && <div id="assistant-options" className="assistant-context-settings" data-testid="assistant-context">
        <div className="assistant-context-heading"><div><h2>{studio("contextTitle")}</h2><p>{studio("contextHint")}</p></div><button type="button" onClick={() => setOptionsOpen(false)} aria-label={ui("close")} data-testid="assistant-options-close"><X size={16} /></button></div>
        <div className="assistant-options-grid"><label className="flex items-center gap-2">{ui("response")}<select data-testid="assistant-response-mode" aria-label={ui("response")} disabled={locked} value={mode} onChange={e => setMode(e.target.value)}><option value="thorough">{ui("thorough")}</option><option value="fast">{ui("fast")}</option></select></label>
          <label className="flex gap-2 items-center min-h-10"><input data-testid="assistant-web-enabled" type="checkbox" checked={webEnabled} disabled={locked} onChange={e => setWebEnabled(e.target.checked)} />{ui("web")}</label>
        </div>
        <div className="assistant-document-pickers">
          {canPlan && <label>{ui("choosePlan")}<select value="" aria-label={ui("choosePlan")} disabled={locked} onChange={e => { const id = e.target.value; if(id) setActivePlans(a => a.includes(id) ? a : [...a,id]); }} data-testid="assistant-plan-select"><option value="">{ui("choosePlan")}</option>{plans.map(p => <option key={p.plan_id} value={p.plan_id} disabled={activePlans.includes(p.plan_id) || activePlans.length >= 5}>{p.filename}</option>)}</select></label>}
          <label>{ui("chooseDoc")}<select value="" aria-label={ui("chooseDoc")} disabled={locked} onChange={e => { const id = e.target.value; if(id) setActiveDocs(a => a.includes(id) ? a : [...a,id]); }} data-testid="assistant-doc-select"><option value="">{ui("chooseDoc")}</option>{docs.map(d => <option key={d.doc_id} value={d.doc_id} disabled={activeDocs.includes(d.doc_id) || activeDocs.length >= 10}>{d.filename}</option>)}</select></label>
        </div>
        {activePrefs.length > 0 && <div className="mt-3 flex flex-wrap items-center gap-2 text-xs text-muted-foreground" data-testid="assistant-active-prefs"><Brain size={14} />{ui("appliedPrefs")} : {activePrefs.slice(0,4).map(p => <span key={p.pref_id} title={p.value} data-testid={`assistant-pref-${p.pref_id}`}>{p.category}</span>)}<Link to="/preferences" className="underline" data-testid="assistant-options-preferences">{ui("preferences")}</Link></div>}
      </div>}
      {(activePlans.length > 0 || activeDocs.length > 0 || dossierImport.dossiers.length > 0) && <div className="assistant-file-chips" data-testid="assistant-pending-files">
        <DossierChips dossiers={dossierImport.dossiers} onRemove={dossierImport.remove} disabled={locked} />
        {[[activePlans, "plan"], [activeDocs, "doc"]].flatMap(([ids,kind]) => ids.map(id => <div key={id} className="assistant-file-chip" data-testid={`assistant-active-${kind}-${id}`}>{kind === "doc" && docs.find((d) => d.doc_id === id)?.kind === "photo" ? <PrivateImage path={`/assistant/documents/${id}/preview`} title={nameOf(id)} testId={`assistant-selected-photo-${id}`} small /> : <FileText size={13} aria-hidden="true" />}<span title={nameOf(id)}>{nameOf(id)}</span><button type="button" disabled={locked} data-testid={`assistant-remove-${kind}-${id}`} aria-label={`${ui("removeFile")} : ${nameOf(id)}`} onClick={() => removeContext(id,kind)}><X size={14} /></button></div>))}
      </div>}
      <div ref={messagesRef} className="assistant-messages" data-testid="assistant-messages" onScroll={e => { const el = e.currentTarget; followMessages.current = el.scrollHeight - el.scrollTop - el.clientHeight < 100; setShowJump(!followMessages.current); }}>
        {activePlans.map(id => <CadImportInfo key={id} info={plans.find(p => p.plan_id === id)?.cad_import} />)}
        {loadingConversation && <div className="assistant-loading" role="status" data-testid="assistant-loading"><Loader2 size={18} className="animate-spin" />{studio("loading")}</div>}
        {!loadingConversation && !conv?.messages?.length && !running && <div className="assistant-welcome">
          <div className="assistant-welcome-brand"><AssistantMark size={64} data-testid="assistant-mark" /><span>{studio("eyebrow")}</span></div>
          <h2>{studio("title")}</h2><p>{studio("intro")}</p>
          <div className="assistant-prompts">
            {(canQuote ? [["quote", FileText, quoteText("quotePrompt")]] : [["solve", Wrench, prompts[3]]]).concat([["análise", Ruler, prompts[1]], ["report", ClipboardList, prompts[2]], ["mail", Mail, prompts[0]]]).map(([key, Icon, value]) =>
              <button key={key} type="button" onClick={() => seedText(value)} data-testid={`assistant-prompt-${key}`}>
                <Icon size={19} aria-hidden="true" /><span className="assistant-prompt-text"><strong>{studio(key)}</strong><small>{studio(`${key}Desc`)}</small></span><ArrowUpRight className="assistant-prompt-arrow" aria-hidden="true" />
              </button>)}
          </div>
          {canQuote && <button type="button" className="assistant-technical-prompt" onClick={() => seedText(prompts[3])} data-testid="assistant-prompt-solve"><Wrench size={14} />{studio("solve")}<ArrowUpRight size={13} /></button>}
          <p className="assistant-prompt-hint">{studio("draftHint")}</p>
        </div>}
        <ConversationJobs conversation={conv} onCancel={stop} onResume={seedText} onCorrect={(m) => seedText(`${ui("correct")} — « ${m.content.slice(0,120)}… » : `)} />
        <div className="assistant-dossier-results">
      <ProjectStatePanel conversationId={conv?.conversation_id} refreshKey={conv?.messages?.length || 0} />
      <CalculationsPanel conversationId={conv?.conversation_id} refreshKey={conv?.messages?.length || 0} onCorrected={() => conv?.conversation_id && open(conv.conversation_id)} />
        </div>
      </div>
      {showJump && <button type="button" className="mx-auto text-xs flex items-center gap-2 px-3 min-h-9 border rounded-md" data-testid="assistant-latest-reply" aria-label={ui("latest")} onClick={() => { followMessages.current = true; setShowJump(false); const el = messagesRef.current; if(el) el.scrollTop = el.scrollHeight; }}><ArrowDown size={15} />{ui("latest")}</button>}
      <FallbackBanner refreshKey={conv?.messages?.length || 0} />
      <div className="assistant-composer">
        {cadFile && <CadUnitPicker file={cadFile} onChoose={unit => upload(cadFile,"plan",unit)} onCancel={() => setCadFile(null)} />}
        {pickFile && <div className="mb-3 p-3 bg-muted/50 rounded-md text-xs" data-testid="assistant-pick-kind"><p className="break-words mb-2"><b>{pickFile.name}</b> · {ui("addAs")}</p><div className="flex flex-wrap gap-2">
          {canPlan && <Button size="sm" variant="outline" onClick={() => upload(pickFile,"plan")} data-testid="assistant-pick-plan">{ui("planKind")}</Button>}<Button size="sm" onClick={() => upload(pickFile,"doc")} data-testid="assistant-pick-doc">{ui("docKind")}</Button><Button size="sm" variant="ghost" onClick={() => setPickFile(null)} data-testid="assistant-pick-cancel">{ui("cancel")}</Button>
        </div></div>}
        <div className="assistant-input-box">
          <textarea ref={textareaRef} disabled={loadingConversation} rows={2} placeholder={ui("message")} aria-label={ui("message")} value={text} onChange={e => setText(e.target.value)} onKeyDown={e => { if(e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing && window.matchMedia("(min-width: 768px)").matches) { e.preventDefault(); send(); } }} data-testid="assistant-input" />
          <div className="assistant-composer-actions">
            <input ref={uploadRef} type="file" multiple className="hidden" accept=".zip,.pdf,.dxf,.dwg,.png,.jpg,.jpeg,.webp,.xlsx,.xls,.csv,.docx,.txt" disabled={locked} onChange={e => { onPickMany(e.target.files); e.target.value = ""; }} data-testid="assistant-upload-input" />
            <input ref={dossierRef} type="file" multiple className="hidden" accept=".zip,.pdf,.dxf,.dwg,.png,.jpg,.jpeg,.webp,.xlsx,.xls,.csv,.docx,.txt" disabled={locked} onChange={e => { dossierImport.importFiles(e.target.files); e.target.value = ""; }} data-testid="assistant-dossier-input" />
            <input ref={folderRef} type="file" multiple webkitdirectory="" directory="" className="hidden" disabled={locked} onChange={e => { dossierImport.importFiles(e.target.files); e.target.value = ""; }} data-testid="assistant-folder-input" />
            <DropdownMenu><DropdownMenuTrigger asChild>
              <Button variant="ghost" disabled={locked} aria-label={ui("attach")} data-testid="assistant-attach-btn">{uploading || dossierImport.uploading ? <Loader2 size={16} className="animate-spin" /> : <Paperclip size={16} />}<span>{studio("attach")}</span><ChevronDown size={13} /></Button>
            </DropdownMenuTrigger><DropdownMenuContent align="start" className="assistant-studio-menu">
              <DropdownMenuItem data-testid="assistant-import-document" onSelect={() => { uploadKind.current = "doc"; uploadRef.current?.click(); }}><Paperclip size={16} />{ui("docKind")}</DropdownMenuItem>
              {canPlan && <DropdownMenuItem data-testid="assistant-import-measurement-plan" onSelect={() => { uploadKind.current = "plan"; uploadRef.current?.click(); }}><Ruler size={16} />{bg("plan")}</DropdownMenuItem>}
              <DropdownMenuItem data-testid="assistant-import-dossier" onSelect={() => dossierRef.current?.click()}><FolderArchive size={16} />Processo completo (ZIP ou vários ficheiros)</DropdownMenuItem>
              <DropdownMenuItem data-testid="assistant-import-folder" onSelect={() => folderRef.current?.click()}><FolderArchive size={16} />Pasta inteira</DropdownMenuItem>
              <DropdownMenuItem data-testid="assistant-existing-files" onSelect={() => setOptionsOpen(true)}><FileText size={16} />{studio("existing")}</DropdownMenuItem>
              <DropdownMenuSeparator />
              <DropdownMenuItem data-testid="assistant-image-prompt" onSelect={() => seedText(text ? `${text}\n${bg("jpgPrompt")}` : bg("jpgPrompt"))}><ImagePlus size={16} />{studio("image")}</DropdownMenuItem>
            </DropdownMenuContent></DropdownMenu>
            <Button variant={rec ? "destructive" : "ghost"} size="icon" disabled={busy || loadingConversation || uploading || transcribing} onClick={toggleMic} aria-label={ui(rec ? "stopMic" : "mic")} title={ui(rec ? "stopMic" : "mic")} data-testid="assistant-mic-btn">{rec ? <Square /> : <Mic />}</Button>
            {rec && <span className="text-xs text-destructive" role="status" data-testid="assistant-recording">{ui("recording")}</span>}
            <Button disabled={(!text.trim() && !pending.length && !dossierImport.ids.length) || locked || dossierImport.uploading || !!cadFile} onClick={send} data-testid="assistant-send-btn">{busy ? <Loader2 size={16} className="animate-spin" /> : <Send size={16} />}{ui("send")}</Button>
          </div>
        </div>
        <div className="assistant-composer-footer">
          <button type="button" className="assistant-mode-summary" onClick={() => setOptionsOpen(v => !v)} aria-expanded={optionsOpen} aria-controls="assistant-options" data-testid="assistant-mode-summary"><SlidersHorizontal size={12} />{ui(mode)}<span aria-hidden="true">·</span><Globe size={12} />{studio(webEnabled ? "webOn" : "webOff")}<ChevronDown size={12} /></button>
          <p className="assistant-keyboard-hint">{ui("keyboard")}</p>
        </div>
        <span className="sr-only" role="status" data-testid="assistant-announcement">{loadingConversation || transcribing ? ui("loading") : running ? bg("background") : ""}</span>
      </div>
    </section>
  </div></DocumentViewerProvider>;
}

