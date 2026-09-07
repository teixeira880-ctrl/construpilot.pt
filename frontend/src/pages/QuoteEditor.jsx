import { useEffect, useMemo, useState, useCallback, useRef } from "react";
import { useParams, useNavigate, useSearchParams } from "react-router-dom";
import { toast } from "sonner";
import {
  Plus, Trash2, Download, Save, BookOpen, Loader2, Search, ArrowLeft, User, Sparkles, Ruler, Video, Send, X,
  Images, Camera, Square, Clock, FileVideo, AlertTriangle, Mic, Music, Eye, Layers, Paperclip,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Badge } from "@/components/ui/badge";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription,
} from "@/components/ui/dialog";
import { SectionTitle } from "@/components/Bits";
import { api } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { VerifiedProBadge } from "@/components/VerifiedProBadge";
import { useI18n } from "@/context/I18nContext";
import { OuvrageComposeDialog } from "@/components/OuvrageComposeDialog";

const UNITS = ["u", "m²", "ml", "m³", "forfait", "ens", "h", "j", "kg", "L"];
const VAT_RATES = [0, 5.5, 10, 20];
const VAT_RATES_PT = [0, 6, 13, 23];
const STATUSES = [
  ["draft", "crm.st_e_draft"], ["sent", "crm.st_e_sent"], ["signed", "crm.st_e_signed"], ["refused", "crm.st_e_refused"],
];
const eur = (n) => (Number(n) || 0).toLocaleString("pt-PT", { minimumFractionDigits: 2, maximumFractionDigits: 2 }) + " €";
const blankLine = (vat = 10) => ({
  designation: "", description: "", unit: "u", qty: 1, unit_price_ht: 0, vat_rate: vat, category: "", _saveToLib: true,
});

export default function QuoteEditor() {
  const { docId: paramDocId } = useParams();
  const [sp] = useSearchParams();
  const nav = useNavigate();
  const { user } = useAuth();
  const { t, lang } = useI18n();
  const isPT = lang === "pt";
  const vatRates = isPT ? VAT_RATES_PT : VAT_RATES;
  const defVat = isPT ? 23 : 10;

  const [docId, setDocId] = useState(paramDocId || null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [clients, setClients] = useState([]);
  const [library, setLibrary] = useState([]);
  const [pickerOpen, setPickerOpen] = useState(false);
  const [pickerQ, setPickerQ] = useState("");

  const [clientId, setClientId] = useState(sp.get("client") || "");
  const [srcPlanId, setSrcPlanId] = useState(sp.get("plan") || "");
  // P2 — création d'un client à la volée desde l'editor de devis
  const [newClientOpen, setNewClientOpen] = useState(false);
  const [ncBusy, setNcBusy] = useState(false);
  const [nc, setNc] = useState({ first_name: "", last_name: "", company: "", email: "", phone: "", address: "" });
  const [title, setTitle] = useState("");
  const [notes, setNotes] = useState("");
  const [depositPct, setDepositPct] = useState(0);
  const [status, setStatus] = useState("draft");
  const [number, setNumber] = useState(null);
  const [lines, setLines] = useState([blankLine(isPT ? 23 : 10)]);
  const [aiLineBusy, setAiLineBusy] = useState(null);
  const [planBusy, setPlanBusy] = useState(false);
  const [videoBusy, setVideoBusy] = useState(false);
  const [photoBusy, setPhotoBusy] = useState(false);
  const [photoPreviews, setPhotoPreviews] = useState([]);

  // Photo → devis : lit une ou plusieurs photos EN PARALLÈLE via l'IA et ajoute les lignes
  const addPhotosFromFiles = async (fileList) => {
    const files = Array.from(fileList || []).filter((f) => f && f.type.startsWith("image/"));
    if (!files.length) { toast.error(t("crm.t_need_photo")); return; }
    setPhotoBusy(true);
    const tid = toast.loading(files.length > 1 ? t("crm.t_reading_photos").replace("{n}", files.length) : t("crm.t_reading_photo"));
    try {
      const b64s = await Promise.all(files.map((file) => new Promise((res, rej) => {
        const r = new FileReader();
        r.onload = () => res(r.result);
        r.onerror = rej;
        r.readAsDataURL(file);
      })));
      const results = await Promise.all(b64s.map(async (b64) => {
        try {
          const { data } = await api.post("/quotes/análise", { image_base64: b64 });
          return { src: b64, found: (data?.analysis?.lines) || [] };
        } catch {
          return { src: b64, found: [] };
        }
      }));
      setPhotoPreviews((prev) => [...prev, ...results.map((r) => ({ src: r.src, count: r.found.length }))]);
      const allFound = results.flatMap((r) => r.found);
      if (allFound.length) {
        setLines((ls) => {
          const cleaned = ls.filter((l) => (l.designation || "").trim() || (l.qty || 0));
          const mapped = allFound.map((l) => ({
            ...blankLine(),
            designation: l.label || "",
            unit: l.unit || "u",
            qty: Number(l.quantity) || 1,
            unit_price_ht: Number(l.unit_price) || 0,
            category: "Lu desde photo",
          }));
          return [...cleaned, ...mapped];
        });
        const okCount = results.filter((r) => r.found.length).length;
        toast.success(t("crm.t_lines_from_photos").replace("{n}", allFound.length).replace("{p}", okCount), { id: tid });
      } else {
        toast.error(t("crm.t_no_prestation"), { id: tid });
      }
    } finally { setPhotoBusy(false); }
  };
  const [transcriptDialog, setTranscriptDialog] = useState(false);
  const [transcript, setTranscript] = useState("");
  const [transcriptBusy, setTranscriptBusy] = useState(false);
  const [transcriptPhotos, setTranscriptPhotos] = useState([]);
  const [docType, setDocType] = useState(
    ["invoice", "credit_note"].includes(sp.get("type")) ? sp.get("type") : "quote");

  const applyDoc = useCallback((d) => {
    setDocId(d.doc_id);
    setClientId(d.client_id || "");
    if (d.plan_id) setSrcPlanId(d.plan_id);
    setTitle(d.title || "");
    setNotes(d.notes || "");
    setDepositPct(d.deposit_pct || 0);
    setStatus(d.status || "draft");
    setNumber(d.number || null);
    setDocType(d.doc_type || "quote");
    setLines((d.lines || []).map((l) => ({ ...blankLine(), ...l, _saveToLib: false })));
  }, []);

  // Bootstrap: existing doc, from-plan, or blank
  useEffect(() => {
    if (!user) return;
    (async () => {
      setLoading(true);
      try {
        const [{ data: cl }, { data: lib }] = await Promise.all([
          api.get("/clients"), api.get("/library"),
        ]);
        setClients(cl.clients || []);
        setLibrary(lib.items || []);
        if (paramDocId) {
          const { data } = await api.get(`/documents/${paramDocId}`);
          applyDoc(data);
        } else if (sp.get("plan")) {
          const q = sp.get("client") ? `?client_id=${sp.get("client")}` : "";
          const { data } = await api.post(`/documents/from-plan/${sp.get("plan")}${q}`);
          applyDoc(data);
          nav(`/devis-editeur/${data.doc_id}`, { replace: true });
        }
        const pend = sessionStorage.getItem("construpilot_pending_ouvrages");
        if (pend) {
          try {
            const arr = JSON.parse(pend);
            if (Array.isArray(arr) && arr.length) {
              setLines((ls) => {
                const base = ls.filter((l) => (l.designation || "").trim() || (Number(l.unit_price_ht) || 0));
                return [...base, ...arr.map((l) => ({ ...blankLine(), ...l, _saveToLib: false }))];
              });
              toast.success(t("crm.t_ouvrages_from_plan").replace("{n}", arr.length));
            }
          } catch { /* ignore */ }
          sessionStorage.removeItem("construpilot_pending_ouvrages");
        }
      } catch (e) {
        toast.error(e?.response?.data?.detail || t("crm.load_fail"));
      } finally { setLoading(false); }
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [user, paramDocId]);

  const totals = useMemo(() => {
    let ht = 0; const tva = {};
    lines.forEach((l) => {
      const lh = (Number(l.qty) || 0) * (Number(l.unit_price_ht) || 0);
      ht += lh;
      const r = Number(l.vat_rate) || 0;
      tva[r] = (tva[r] || 0) + lh * r / 100;
    });
    const tvaTotal = Object.values(tva).reduce((a, b) => a + b, 0);
    const ttc = ht + tvaTotal;
    const dep = ttc * (Number(depositPct) || 0) / 100;
    return { ht, tva, tvaTotal, ttc, dep, remaining: ttc - dep };
  }, [lines, depositPct]);

  const lotSubtotals = useMemo(() => {
    const map = new Map();
    for (const l of lines) {
      const cat = (l.category || "").trim();
      if (!cat) continue;
      const lh = (Number(l.qty) || 0) * (Number(l.unit_price_ht) || 0);
      map.set(cat, (map.get(cat) || 0) + lh);
    }
    return [...map.entries()].map(([cat, ht]) => ({ cat, ht }));
  }, [lines]);

  const knownLots = useMemo(() => {
    const s = new Set();
    lines.forEach((l) => { const c = (l.category || "").trim(); if (c) s.add(c); });
    ["Estrutura", "Cobertura", "Canalização", "Eletricidade", "Pintura", "Caixilharia",
     "Revestimento cerâmico", "Isolamento", "Pavimento", "Gesso cartonado", "Infraestruturas"].forEach((c) => s.add(c));
    return [...s];
  }, [lines]);

  const setLine = (i, k, v) => setLines((ls) => ls.map((l, idx) => idx === i ? { ...l, [k]: v } : l));
  const setAllVat = (rate) => {
    setLines((ls) => ls.map((l) => ({ ...l, vat_rate: rate })));
    toast.success(t("crm.t_vat_applied").replace("{r}", rate));
  };
  const addLine = () => setLines((ls) => [...ls, blankLine(defVat)]);
  const delLine = (i) => setLines((ls) => ls.filter((_, idx) => idx !== i));

  const suggestDescription = async (i) => {
    const l = lines[i];
    if (!l?.designation.trim()) return toast.error(t("crm.t_need_desig"));
    setAiLineBusy(i);
    try {
      const { data } = await api.post("/documents/ai/describe", {
        designation: l.designation, context: title || "",
      });
      const suggestion = (data.description || "").trim();
      if (!suggestion) return toast.error(t("crm.t_no_suggest"));
      setLines((ls) => ls.map((ln, idx) => idx === i
        ? { ...ln, description: ln.description?.trim() ? ln.description + "\n" + suggestion : suggestion }
        : ln));
      toast.success(t("crm.t_suggest_added"));
    } catch (e) {
      toast.error(e?.response?.data?.detail || t("crm.t_suggest_unavailable"));
    } finally { setAiLineBusy(null); }
  };
  const addFromLib = (it) => {
    setLines((ls) => [...ls, {
      designation: it.designation, unit: it.unit, qty: 1,
      unit_price_ht: it.unit_price_ht, vat_rate: it.vat_rate, category: it.category, _saveToLib: false,
    }]);
    setPickerOpen(false);
    toast.success(t("crm.line_added"));
  };

  const payload = () => ({
    doc_type: docType, client_id: clientId || null, title, notes,
    deposit_pct: Number(depositPct) || 0, status,
    lines: lines.filter((l) => l.designation.trim()).map((l) => ({
      designation: l.designation, description: l.description || "", unit: l.unit, qty: Number(l.qty) || 0,
      unit_price_ht: Number(l.unit_price_ht) || 0, vat_rate: Number(l.vat_rate) || 10,
      category: l.category || "",
    })),
  });

  const autoSaveLibrary = async () => {
    const known = new Set(library.map((i) => i.designation.trim().toLowerCase()));
    const toSave = lines.filter((l) => l._saveToLib && l.designation.trim()
      && !known.has(l.designation.trim().toLowerCase()));
    for (const l of toSave) {
      try {
        await api.post("/library", {
          type: "ouvrage", category: l.category || "Orçamento", designation: l.designation,
          unit: l.unit, unit_price_ht: Number(l.unit_price_ht) || 0, vat_rate: Number(l.vat_rate) || 10,
        });
      } catch { /* ignore */ }
    }
    if (toSave.length) toast.success(t("crm.lib_added").replace("{n}", toSave.length));
  };

  const save = async () => {
    if (!lines.some((l) => l.designation.trim())) return toast.error(t("crm.need_line"));
    setSaving(true);
    try {
      let d;
      if (docId) ({ data: d } = await api.put(`/documents/${docId}`, payload()));
      else ({ data: d } = await api.post("/documents", payload()));
      applyDoc(d);
      if (!paramDocId && d.doc_id) nav(`/devis-editeur/${d.doc_id}`, { replace: true });
      await autoSaveLibrary();
      toast.success(t("crm.saved"));
      return d;
    } catch (e) { toast.error(e?.response?.data?.detail || t("crm.save_fail")); }
    finally { setSaving(false); }
  };

  const createClientInline = async () => {
    if (!(nc.first_name || nc.last_name || nc.company || nc.email)) {
      toast.error(t("crm.t_need_client_identity")); return;
    }
    setNcBusy(true);
    try {
      const { data } = await api.post("/clients", nc);
      setClients((prev) => [data, ...prev]);
      setClientId(data.client_id);
      setNewClientOpen(false);
      setNc({ first_name: "", last_name: "", company: "", email: "", phone: "", address: "" });
      toast.success(t("crm.t_client_added"));
    } catch (e) {
      toast.error(e?.response?.data?.detail || t("crm.t_client_create_fail"));
    } finally { setNcBusy(false); }
  };

  const addPlanFromFile = async (file) => {
    if (!file) return;
    if (file.size > 20 * 1024 * 1024) { toast.error(t("crm.t_file_too_big20")); return; }
    setPlanBusy(true);
    try {
      const fd = new FormData();
      fd.append("file", file);
      const { data } = await api.post("/takeoffs/upload", fd, { headers: { "Content-Type": "multipart/form-data" } });
      toast.success(t("crm.t_plan_imported"));
      nav(`/plan?open=${data.plan_id}&auto=1`);
    } catch (e) {
      toast.error(e?.response?.data?.detail || t("crm.t_plan_import_fail"));
    } finally { setPlanBusy(false); }
  };

  // --- Enregistreur vidéo intégré basse résolution (480p) ---
  const [recOpen, setRecOpen] = useState(false);
  const [recording, setRecording] = useState(false);
  const [recSecs, setRecSecs] = useState(0);
  const [recMode, setRecMode] = useState("video");
  const [streamReady, setStreamReady] = useState(false);
  const streamRef = useRef(null);
  const recorderRef = useRef(null);
  const chunksRef = useRef([]);
  const timerRef = useRef(null);
  const videoElRef = useRef(null);

  const closeRecorder = () => {
    if (timerRef.current) { clearInterval(timerRef.current); timerRef.current = null; }
    if (recorderRef.current && recorderRef.current.state !== "inactive") { try { recorderRef.current.stop(); } catch {} }
    recorderRef.current = null;
    if (streamRef.current) { streamRef.current.getTracks().forEach((tr) => tr.stop()); streamRef.current = null; }
    if (videoElRef.current) videoElRef.current.srcObject = null;
    setStreamReady(false);
    setRecording(false);
    setRecSecs(0);
    setRecOpen(false);
  };

  const openRecorder = async (mode = "video") => {
    if (!navigator.mediaDevices?.getUserMedia) { toast.error(t("crm.t_mic_cam_unsupported")); return; }
    setRecMode(mode);
    setStreamReady(false);
    setRecOpen(true);
    try {
      const constraints = mode === "audio"
        ? { audio: true }
        : { audio: true, video: { facingMode: { ideal: "environment" }, width: { ideal: 640 }, height: { ideal: 480 }, frameRate: { ideal: 24, max: 30 } } };
      const stream = await navigator.mediaDevices.getUserMedia(constraints);
      streamRef.current = stream;
      if (mode !== "audio" && videoElRef.current) { videoElRef.current.srcObject = stream; videoElRef.current.play().catch(() => {}); }
      setStreamReady(true);
    } catch {
      toast.error(mode === "audio" ? t("crm.t_mic_denied") : t("crm.t_cam_denied"));
      closeRecorder();
    }
  };

  const startRec = () => {
    const stream = streamRef.current;
    if (!stream) return;
    chunksRef.current = [];
    const cand = recMode === "audio"
      ? ["audio/webm;codecs=opus", "audio/webm", "audio/mp4"]
      : ["video/webm;codecs=vp8,opus", "video/webm", "video/mp4"];
    const mime = cand.find((m) => window.MediaRecorder && MediaRecorder.isTypeSupported(m)) || "";
    const opts = mime ? { mimeType: mime, ...(recMode === "audio" ? { audioBitsPerSecond: 96000 } : { videoBitsPerSecond: 600000 }) } : {};
    const rec = new MediaRecorder(stream, opts);
    rec.ondataavailable = (e) => { if (e.data && e.data.size) chunksRef.current.push(e.data); };
    rec.onstop = () => {
      const blob = new Blob(chunksRef.current, { type: rec.mimeType || (recMode === "audio" ? "audio/webm" : "video/webm") });
      const isMp4 = (rec.mimeType || "").includes("mp4");
      const ext = recMode === "audio" ? (isMp4 ? "m4a" : "webm") : (isMp4 ? "mp4" : "webm");
      const file = new File([blob], `chantier-${Date.now()}.${ext}`, { type: blob.type });
      closeRecorder();
      if (blob.size > 0) reviewVideo(file);
    };
    rec.start();
    recorderRef.current = rec;
    setRecording(true);
    setRecSecs(0);
    timerRef.current = setInterval(() => setRecSecs((s) => s + 1), 1000);
  };

  const stopRec = () => {
    if (timerRef.current) { clearInterval(timerRef.current); timerRef.current = null; }
    if (recorderRef.current && recorderRef.current.state !== "inactive") recorderRef.current.stop();
    setRecording(false);
  };

  const fmtSecs = (s) => `${String(Math.floor(s / 60)).padStart(2, "0")}:${String(s % 60).padStart(2, "0")}`;

  useEffect(() => () => { closeRecorder(); }, []);

  // --- Revue de la vidéo (taille / durée) avant transcription ---
  const [reviewOpen, setReviewOpen] = useState(false);
  const [reviewFile, setReviewFile] = useState(null);
  const [reviewInfo, setReviewInfo] = useState({ sizeMB: 0, duration: 0, url: null });

  const reviewVideo = (file) => {
    if (!file) return;
    if (file.size > 80 * 1024 * 1024) { toast.error(t("crm.t_video_too_big")); return; }
    const url = URL.createObjectURL(file);
    const sizeMB = file.size / (1024 * 1024);
    let done = false;
    const finalize = (duration) => {
      if (done) return;
      done = true;
      setReviewFile(file);
      setReviewInfo({ sizeMB, duration: isFinite(duration) && duration > 0 ? duration : 0, url });
      setReviewOpen(true);
    };
    // Garde-fou : certains navigateurs (webm MediaRecorder) ne fournissent jamais
    // les métadonnées de durée → on ouvre quand même la revue après 2,5 s.
    const guard = setTimeout(() => finalize(0), 2500);
    const v = document.createElement("video");
    v.preload = "metadata";
    v.muted = true;
    v.onloadedmetadata = () => {
      if (v.duration === Infinity || isNaN(v.duration)) {
        v.currentTime = 1e101;
        v.ontimeupdate = () => { v.ontimeupdate = null; clearTimeout(guard); finalize(v.duration); };
      } else { clearTimeout(guard); finalize(v.duration); }
    };
    v.onerror = () => { clearTimeout(guard); finalize(0); };
    v.src = url;
  };

  const closeReview = () => {
    if (reviewInfo.url) URL.revokeObjectURL(reviewInfo.url);
    setReviewOpen(false);
    setReviewFile(null);
    setReviewInfo({ sizeMB: 0, duration: 0, url: null });
  };

  const confirmTranscribe = () => {
    const f = reviewFile;
    if (reviewInfo.url) URL.revokeObjectURL(reviewInfo.url);
    setReviewOpen(false);
    setReviewFile(null);
    setReviewInfo({ sizeMB: 0, duration: 0, url: null });
    if (f) transcribeVideo(f);
  };

  const transcribeVideo = async (file) => {
    if (!file) return;
    if (file.size > 80 * 1024 * 1024) { toast.error(t("crm.t_video_too_big")); return; }
    setVideoBusy(true);
    const tid = toast.loading(t("crm.t_transcribing"));
    try {
      const fd = new FormData();
      fd.append("file", file);
      const { data } = await api.post("/documents/video-transcribe", fd, {
        headers: { "Content-Type": "multipart/form-data" }, timeout: 180000,
      });
      toast.success(t("crm.t_transcript_ready"), { id: tid });
      setTranscript(data.transcript || "");
      setTranscriptPhotos([]);
      setTranscriptDialog(true);
    } catch (e) {
      toast.error(e?.response?.data?.detail || t("crm.t_transcript_fail"), { id: tid });
    } finally { setVideoBusy(false); }
  };

  const addTranscriptPhotos = (files) => {
    const list = Array.from(files || []).slice(0, 6 - transcriptPhotos.length);
    list.forEach((f) => {
      if (!f.type.startsWith("image/") || f.size > 8 * 1024 * 1024) return;
      const reader = new FileReader();
      reader.onload = () => setTranscriptPhotos((p) => (p.length >= 6 ? p : [...p, reader.result]));
      reader.readAsDataURL(f);
    });
  };

  const generateFromTranscript = async () => {
    if (!transcript.trim()) { toast.error(t("crm.t_transcript_empty")); return; }
    setTranscriptBusy(true);
    const tid = toast.loading(t("crm.t_generating_quote"));
    try {
      const { data } = await api.post("/documents/from-text", { text: transcript, images: transcriptPhotos });
      toast.success(
        data.priced_lines > 0
          ? t("crm.t_quote_created_lines").replace("{n}", data.priced_lines)
          : t("crm.t_quote_created"), { id: tid });
      setTranscriptDialog(false);
      nav(`/devis-editeur/${data.doc_id}`);
    } catch (e) {
      toast.error(e?.response?.data?.detail || t("crm.t_gen_quote_fail"), { id: tid });
    } finally { setTranscriptBusy(false); }
  };

  const downloadPdf = async () => {
    const d = docId ? { doc_id: docId } : await save();
    if (!d) return;
    try {
      const res = await api.get(`/documents/${d.doc_id}/pdf?lang=${lang}`, { responseType: "blob" });
      const url = URL.createObjectURL(res.data);
      const a = document.createElement("a");
      a.href = url; a.download = `devis.pdf`; a.click();
      URL.revokeObjectURL(url);
      toast.success(t("crm.pdf_ok"));
    } catch { toast.error(t("crm.pdf_fail")); }
  };

  const [sendOpen, setSendOpen] = useState(false);
  const [sending, setSending] = useState(false);
  const [sendEmail, setSendEmail] = useState("");
  const [sendName, setSendName] = useState("");
  const [sendMsg, setSendMsg] = useState("");
  const [attach3d, setAttach3d] = useState(true);
  const [preview3d, setPreview3d] = useState(null);
  const [pdfPreviewUrl, setPdfPreviewUrl] = useState(null);
  const [emailPreviewHtml, setEmailPreviewHtml] = useState(null);
  const [loadingEmailPreview, setLoadingEmailPreview] = useState(false);
  const [renderUrl, setRenderUrl] = useState("");
  const [doneRenders, setDoneRenders] = useState([]);
  const [sendFiles, setSendFiles] = useState([]);

  const fileToB64 = (file) => new Promise((resolve, reject) => {
    const r = new FileReader();
    r.onload = () => resolve(String(r.result).split(",", 2)[1] || "");
    r.onerror = reject;
    r.readAsDataURL(file);
  });

  const addSendFiles = (fileList) => {
    const incoming = Array.from(fileList || []);
    if (!incoming.length) return;
    setSendFiles((prev) => {
      const merged = [...prev, ...incoming].slice(0, 5);
      const total = merged.reduce((s, f) => s + f.size, 0);
      if (total > 15 * 1024 * 1024) {
        toast.error(t("crm.t_attach_too_big"));
        return prev;
      }
      if (prev.length + incoming.length > 5) toast.error(t("crm.t_attach_max5"));
      return merged;
    });
  };
  const removeSendFile = (idx) => setSendFiles((prev) => prev.filter((_, i) => i !== idx));

  const pickRender = async (rid) => {
    if (!rid) { setRenderUrl(""); return; }
    try {
      const { data } = await api.post(`/runway/renders/${rid}/share`);
      setRenderUrl(data.share_url || "");
      toast.success(t("crm.t_render_attached"));
    } catch { toast.error(t("crm.t_render_attach_fail")); }
  };

  const loadEmailPreview = async () => {
    let id = docId;
    if (!id) { const d = await save(); if (!d) return; id = d.doc_id; }
    setLoadingEmailPreview(true);
    try {
      const { data } = await api.post(`/documents/${id}/email-preview`, {
        message: sendMsg, client_name: sendName, render_url: renderUrl,
      });
      setEmailPreviewHtml(data?.html || "");
    } catch (e) {
      toast.error(e?.response?.data?.detail || t("crm.t_preview_unavailable"));
    } finally { setLoadingEmailPreview(false); }
  };

  const openSend = async () => {
    const c = clients.find((x) => x.client_id === clientId);
    const nm = [c?.first_name, c?.last_name].filter(Boolean).join(" ") || c?.company || c?.name || "";
    setSendEmail(c?.email || "");
    setSendName(nm);
    setSendMsg("");
    setPreview3d(null);
    setPdfPreviewUrl(null);
    setEmailPreviewHtml(null);
    setRenderUrl("");
    setSendFiles([]);
    setSendOpen(true);
    let id = docId;
    if (!id) { const d = await save(); if (!d) return; id = d.doc_id; }
    // Message type pré-rempli (selon type de document + taux de TVA)
    api.get(`/documents/${id}/email-template`, { params: { client_name: nm } })
      .then(({ data }) => { if (data?.message) setSendMsg(data.message); })
      .catch(() => {});
    // Renders IA avant/après disponíveis (prêts) à joindre
    api.get("/runway/renders")
      .then(({ data }) => setDoneRenders((data.renders || []).filter((r) => r.status === "done")))
      .catch(() => {});
    // Pré-visualização de render 3D
    api.get(`/documents/${id}`).then(({ data }) => {
      if (data?.attachment_image_b64) setPreview3d(data.attachment_image_b64);
    }).catch(() => {});
    // Pré-visualização PDF
    api.get(`/documents/${id}/pdf?lang=${lang}`, { responseType: "blob" })
      .then((res) => setPdfPreviewUrl(URL.createObjectURL(res.data)))
      .catch(() => {});
  };

  const closeSend = (v) => {
    setSendOpen(v);
    if (!v && pdfPreviewUrl) { URL.revokeObjectURL(pdfPreviewUrl); setPdfPreviewUrl(null); }
  };

  const sendNow = async () => {
    if (!/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(sendEmail)) {
      toast.error(t("crm.t_email_invalid")); return;
    }
    setSending(true);
    try {
      let id = docId;
      if (!id) { const d = await save(); if (!d) { setSending(false); return; } id = d.doc_id; }
      const attachments = await Promise.all(sendFiles.map(async (f) => ({
        filename: f.name, content_type: f.type || "application/octet-stream",
        content_b64: await fileToB64(f),
      })));
      await api.post(`/documents/${id}/send`, { client_email: sendEmail, client_name: sendName, message: sendMsg, attach_3d: attach3d, render_url: renderUrl, attachments })
        .then(({ data }) => {
          toast.success(data?.attached_3d ? t("crm.t_quote_sent_3d") : t("crm.t_quote_sent"));
        });
      closeSend(false);
      setStatus("sent");
    } catch (e) {
      toast.error(e?.response?.data?.detail || t("crm.t_send_fail"));
    } finally { setSending(false); }
  };

  if (!user) return <div className="surface p-10 text-center">{t("crm.login")}</div>;
  if (loading) return <div className="surface p-10 text-center animate-pulse">{t("crm.loading")}</div>;

  const filteredLib = library.filter((i) =>
    !pickerQ.trim() || (i.designation + " " + i.category).toLowerCase().includes(pickerQ.toLowerCase()));

  return (
    <div className="grid gap-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="flex items-center gap-3 mb-2">
            <button onClick={() => nav("/devis")} className="text-xs text-muted-foreground hover:text-foreground flex items-center gap-1" data-testid="editor-back">
              <ArrowLeft className="h-3 w-3" /> {t("crm.ed_back")}
            </button>
            {srcPlanId && (
              <button onClick={() => nav(`/plan?open=${srcPlanId}&auto=1`)}
                      className="text-xs text-primary hover:underline flex items-center gap-1 font-medium"
                      data-testid="editor-back-to-plan">
                <Ruler className="h-3 w-3" /> {t("crm.ed_back_plan")}
              </button>
            )}
          </div>
          <SectionTitle
            over={number
              ? `${{ quote: t("crm.doc_quote"), invoice: t("crm.doc_invoice"), credit_note: t("crm.doc_credit") }[docType]} ${number}`
              : `${t("crm.ed_new")} ${{ quote: t("crm.doc_quote"), invoice: t("crm.doc_invoice"), credit_note: t("crm.doc_credit") }[docType]}`}
            title={`${t("crm.ed_editor")} ${{ quote: t("crm.doc_quote"), invoice: t("crm.doc_invoice"), credit_note: t("crm.doc_credit") }[docType]}`}>
            {t("crm.ed_sub")}
          </SectionTitle>
          <div className="mt-2"><VerifiedProBadge status={user?.kyc_status} /></div>
        </div>
        <div className="flex gap-2">
          <input type="file" accept="image/*,application/pdf,.dxf" className="hidden" id="qe-plan-input"
                 onChange={(e) => { addPlanFromFile(e.target.files?.[0]); e.target.value = ""; }}
                 data-testid="editor-add-plan-input" />
          <Button variant="outline" onClick={() => document.getElementById("qe-plan-input").click()}
                  disabled={planBusy} className="rounded-sm gap-2 text-primary border-primary/40" data-testid="editor-add-plan-btn">
            {planBusy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Ruler className="h-4 w-4" />} {t("crm.ed_add_plan")}
          </Button>
          <input type="file" accept="image/*" multiple className="hidden" id="qe-photo-input"
                 onChange={(e) => { addPhotosFromFiles(e.target.files); e.target.value = ""; }}
                 data-testid="editor-photo-input" />
          <Button variant="outline" onClick={() => document.getElementById("qe-photo-input").click()}
                  disabled={photoBusy} className="rounded-sm gap-2 text-primary border-primary/40" data-testid="editor-photo-gallery-btn">
            {photoBusy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Images className="h-4 w-4" />} {t("crm.ed_photos_gallery")}
          </Button>
          <input type="file" accept="image/*" capture="environment" multiple className="hidden" id="qe-photo-cam-input"
                 onChange={(e) => { addPhotosFromFiles(e.target.files); e.target.value = ""; }}
                 data-testid="editor-photo-cam-input" />
          <Button variant="outline" onClick={() => document.getElementById("qe-photo-cam-input").click()}
                  disabled={photoBusy} className="rounded-sm gap-2 text-primary border-primary/40" data-testid="editor-photo-cam-btn">
            {photoBusy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Camera className="h-4 w-4" />} {t("crm.ed_photo_to_quote")}
          </Button>
          <input type="file" accept="video/*" className="hidden" id="qe-video-input"
                 onChange={(e) => { reviewVideo(e.target.files?.[0]); e.target.value = ""; }}
                 data-testid="editor-video-input" />
          <Button variant="outline" onClick={() => document.getElementById("qe-video-input").click()}
                  disabled={videoBusy} className="rounded-sm gap-2 text-primary border-primary/40" data-testid="editor-video-gallery-btn">
            {videoBusy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Images className="h-4 w-4" />} {t("crm.ed_video_gallery")}
          </Button>
          <Button variant="outline" onClick={() => openRecorder("video")}
                  disabled={videoBusy} className="rounded-sm gap-2 text-primary border-primary/40" data-testid="editor-video-record-btn">
            {videoBusy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Video className="h-4 w-4" />} {t("crm.ed_film_to_quote")}
          </Button>
          <input type="file" accept="audio/*" className="hidden" id="qe-audio-input"
                 onChange={(e) => { reviewVideo(e.target.files?.[0]); e.target.value = ""; }}
                 data-testid="editor-audio-input" />
          <Button variant="outline" onClick={() => document.getElementById("qe-audio-input").click()}
                  disabled={videoBusy} className="rounded-sm gap-2 text-primary border-primary/40" data-testid="editor-audio-gallery-btn">
            {videoBusy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Music className="h-4 w-4" />} {t("crm.ed_audio_gallery")}
          </Button>
          <Button variant="outline" onClick={() => openRecorder("audio")}
                  disabled={videoBusy} className="rounded-sm gap-2 text-primary border-primary/40" data-testid="editor-audio-record-btn">
            {videoBusy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Mic className="h-4 w-4" />} {t("crm.ed_dictate")}
          </Button>
          <Button variant="outline" onClick={downloadPdf} className="rounded-sm gap-2" data-testid="editor-pdf-btn">
            <Download className="h-4 w-4" /> {t("crm.pdf")}
          </Button>
          <Button onClick={save} disabled={saving} variant="outline" className="rounded-sm gap-2" data-testid="editor-save-btn">
            {saving ? <Loader2 className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4" />} {t("crm.save")}
          </Button>
          <Button onClick={openSend} disabled={saving} className="rounded-sm gap-2 bg-primary" data-testid="editor-send-btn">
            <Send className="h-4 w-4" /> {docType === "invoice" ? t("crm.ed_send_invoice") : docType === "credit_note" ? t("crm.ed_send_credit") : t("crm.ed_send_quote")}
          </Button>
        </div>
      </div>

      <Dialog open={sendOpen} onOpenChange={closeSend}>
        <DialogContent data-testid="send-quote-dialog">
          <DialogHeader>
            <DialogTitle>{docType === "invoice" ? t("crm.ed_send_invoice_to") : docType === "credit_note" ? t("crm.ed_send_credit_to") : t("crm.ed_send_quote_to")}</DialogTitle>
          </DialogHeader>
          <div className="grid gap-4 max-h-[70vh] overflow-y-auto pr-1">
            {(pdfPreviewUrl || preview3d) && (
              <div className="grid gap-2" data-testid="send-preview">
                <p className="text-xs font-semibold text-muted-foreground">{t("crm.ed_preview_before")}</p>
                <div className="grid grid-cols-2 gap-2">
                  {pdfPreviewUrl ? (
                    <iframe title="Pré-visualização PDF" src={pdfPreviewUrl} data-testid="send-preview-pdf"
                            className="w-full h-40 rounded-sm border border-border bg-white" />
                  ) : (
                    <div className="w-full h-40 rounded-sm border border-border grid place-items-center text-[10px] text-muted-foreground">PDF…</div>
                  )}
                  {preview3d ? (
                    <img src={preview3d} alt="Render 3D" data-testid="send-preview-3d"
                         className="w-full h-40 object-contain rounded-sm border border-border bg-secondary/30" />
                  ) : (
                    <div className="w-full h-40 rounded-sm border border-dashed border-border grid place-items-center text-[10px] text-muted-foreground text-center px-2">{t("crm.ed_no_render3d")}</div>
                  )}
                </div>
              </div>
            )}
            <div className="grid gap-1.5">
              <Label htmlFor="send-name">{t("crm.ed_client_name")}</Label>
              <Input id="send-name" value={sendName} onChange={(e) => setSendName(e.target.value)}
                     placeholder={t("crm.ed_client_name")} data-testid="send-quote-name" />
            </div>
            <div className="grid gap-1.5">
              <Label htmlFor="send-email">{t("crm.ed_client_email_req")}</Label>
              <Input id="send-email" type="email" value={sendEmail} onChange={(e) => setSendEmail(e.target.value)}
                     placeholder="client@email.com" data-testid="send-quote-email" />
            </div>
            <div className="grid gap-1.5">
              <Label htmlFor="send-msg">{t("crm.ed_msg_optional")}</Label>
              <Textarea id="send-msg" rows={3} value={sendMsg} onChange={(e) => setSendMsg(e.target.value)}
                        placeholder={t("crm.ed_msg_ph")} data-testid="send-quote-msg" />
            </div>
            <div className="grid gap-2">
              <Button type="button" variant="outline" size="sm"
                      className="rounded-sm gap-2 justify-self-start"
                      onClick={loadEmailPreview} disabled={loadingEmailPreview}
                      data-testid="send-email-preview-btn">
                {loadingEmailPreview ? <Loader2 className="h-4 w-4 animate-spin" /> : <Eye className="h-4 w-4" />}
                {t("crm.ed_email_preview_btn")}
              </Button>
              {emailPreviewHtml && (
                <div className="rounded-sm border border-border overflow-hidden" data-testid="send-email-preview">
                  <iframe title="Pré-visualização de email" srcDoc={emailPreviewHtml}
                          className="w-full h-72 bg-white" />
                </div>
              )}
            </div>
            <label className="flex items-center gap-2 text-sm cursor-pointer" data-testid="send-quote-attach3d">
              <input type="checkbox" checked={attach3d} onChange={(e) => setAttach3d(e.target.checked)}
                     className="h-4 w-4 rounded border-input accent-primary" />
              {t("crm.ed_attach_3d")}
            </label>
            <div className="grid gap-1.5" data-testid="send-attachments-block">
              <Label className="flex items-center gap-1.5"><Paperclip className="h-3.5 w-3.5" /> {t("crm.ed_attachments")}</Label>
              <input type="file" multiple
                     onChange={(e) => { addSendFiles(e.target.files); e.target.value = ""; }}
                     className="block w-full text-sm text-muted-foreground file:mr-3 file:rounded-sm file:border-0 file:bg-secondary file:px-3 file:py-1.5 file:text-sm file:cursor-pointer hover:file:bg-secondary/80"
                     data-testid="send-attachments-input" />
              {sendFiles.length > 0 && (
                <ul className="grid gap-1 mt-1">
                  {sendFiles.map((f, i) => (
                    <li key={i} className="flex items-center justify-between gap-2 text-xs surface px-2.5 py-1.5 rounded-sm"
                        data-testid={`send-attachment-item-${i}`}>
                      <span className="truncate">{f.name} · {(f.size / 1024).toFixed(0)} Ko</span>
                      <button type="button" onClick={() => removeSendFile(i)}
                              className="text-muted-foreground hover:text-destructive shrink-0"
                              data-testid={`send-attachment-remove-${i}`}><X className="h-3.5 w-3.5" /></button>
                    </li>
                  ))}
                </ul>
              )}
            </div>
            {doneRenders.length > 0 && (
              <div className="grid gap-1.5" data-testid="send-quote-render-block">
                <Label htmlFor="send-render">{t("crm.ed_ai_render_opt")}</Label>
                <select id="send-render" onChange={(e) => pickRender(e.target.value)}
                        className="rounded-sm border border-border bg-background px-3 py-2 text-sm outline-none focus:border-primary"
                        data-testid="send-quote-render-select">
                  <option value="">{t("crm.ed_none")}</option>
                  {doneRenders.map((r) => (
                    <option key={r.render_id} value={r.render_id}>
                      {(r.kind === "video" ? "🎬 " : "🖼️ ") + (r.prompt ? r.prompt.slice(0, 40) : "Render") + " · " + new Date(r.created_at).toLocaleDateString("pt-PT")}
                    </option>
                  ))}
                </select>
                {renderUrl && <p className="text-[11px] text-primary">{t("crm.ed_link_added")}</p>}
              </div>
            )}
            <div className="flex justify-end gap-2">
              <Button variant="outline" onClick={() => closeSend(false)} className="rounded-sm" data-testid="send-quote-cancel">{t("crm.cancel")}</Button>
              <Button onClick={sendNow} disabled={sending} className="rounded-sm gap-2" data-testid="send-quote-confirm">
                {sending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />} {t("crm.ed_send")}
              </Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>

      {/* Meta : client, titre, statut */}
      <div className="surface p-4 grid md:grid-cols-3 gap-3">
        <div>
          <Label className="flex items-center gap-1"><User className="h-3 w-3" /> {t("crm.client_lbl")}</Label>
          <div className="flex gap-2 mt-1">
            <select value={clientId} onChange={(e) => setClientId(e.target.value)} data-testid="editor-client-select"
                    className="flex-1 rounded-sm border border-border bg-background px-3 py-2 text-sm outline-none focus:border-primary">
              <option value="">{t("crm.no_client")}</option>
              {clients.map((c) => (
                <option key={c.client_id} value={c.client_id}>
                  {[c.first_name, c.last_name].filter(Boolean).join(" ") || c.company || c.email}
                </option>
              ))}
            </select>
            <Button type="button" variant="outline" size="sm"
                    onClick={() => setNewClientOpen(true)} data-testid="editor-new-client-btn"
                    className="rounded-sm gap-1 whitespace-nowrap" title={t("crm.ed_add_unreg_title")}>
              <Plus className="h-3.5 w-3.5" /> {t("crm.ed_new")}
            </Button>
          </div>
        </div>
        <div>
          <Label>{t("crm.title_lbl")}</Label>
          <Input value={title} onChange={(e) => setTitle(e.target.value)} className="rounded-sm mt-1"
                 placeholder={t("crm.title_ph")} data-testid="editor-title" />
        </div>
        <div>
          <Label>{t("crm.status_lbl")}</Label>
          <select value={status} onChange={(e) => setStatus(e.target.value)} data-testid="editor-status"
                  className="mt-1 w-full rounded-sm border border-border bg-background px-3 py-2 text-sm outline-none focus:border-primary">
            {STATUSES.map(([v, l]) => <option key={v} value={v}>{t(l)}</option>)}
          </select>
        </div>
      </div>

      {/* P2 — Dialog création client à la volée */}
      <Dialog open={newClientOpen} onOpenChange={setNewClientOpen}>
        <DialogContent className="max-w-md" data-testid="new-client-dialog">
          <DialogHeader>
            <DialogTitle>{t("crm.new_client")}</DialogTitle>
            <DialogDescription>{t("crm.ed_new_client_desc")}</DialogDescription>
          </DialogHeader>
          <div className="grid gap-3">
            <div className="grid grid-cols-2 gap-3">
              <div>
                <Label>{t("crm.firstname")}</Label>
                <Input value={nc.first_name} onChange={(e) => setNc({ ...nc, first_name: e.target.value })}
                       className="rounded-sm mt-1" data-testid="nc-first-name" placeholder="Jean" />
              </div>
              <div>
                <Label>{t("crm.lastname")}</Label>
                <Input value={nc.last_name} onChange={(e) => setNc({ ...nc, last_name: e.target.value })}
                       className="rounded-sm mt-1" data-testid="nc-last-name" placeholder="Dupont" />
              </div>
            </div>
            <div>
              <Label>{t("crm.ed_company_opt")}</Label>
              <Input value={nc.company} onChange={(e) => setNc({ ...nc, company: e.target.value })}
                     className="rounded-sm mt-1" data-testid="nc-company" placeholder="SCI Dupont" />
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <Label>{t("crm.email")}</Label>
                <Input value={nc.email} onChange={(e) => setNc({ ...nc, email: e.target.value })}
                       className="rounded-sm mt-1" data-testid="nc-email" placeholder="jean@email.com" />
              </div>
              <div>
                <Label>{t("crm.phone")}</Label>
                <Input value={nc.phone} onChange={(e) => setNc({ ...nc, phone: e.target.value })}
                       className="rounded-sm mt-1" data-testid="nc-phone" placeholder="06 12 34 56 78" />
              </div>
            </div>
            <div>
              <Label>{t("crm.address")}</Label>
              <Input value={nc.address} onChange={(e) => setNc({ ...nc, address: e.target.value })}
                     className="rounded-sm mt-1" data-testid="nc-address" placeholder="Rua das Obras 12, 1000-000 Lisboa" />
            </div>
            <div className="flex justify-end gap-2 pt-1">
              <Button variant="outline" onClick={() => setNewClientOpen(false)} className="rounded-sm" data-testid="nc-cancel">
                {t("crm.cancel")}
              </Button>
              <Button onClick={createClientInline} disabled={ncBusy} className="rounded-sm gap-1" data-testid="nc-save">
                {ncBusy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Plus className="h-4 w-4" />} {t("crm.ed_add")}
              </Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>

      {photoPreviews.length > 0 && (
        <div className="surface p-3" data-testid="photo-preview">
          <div className="flex items-center justify-between mb-2">
            <div className="min-w-0">
              <p className="text-xs font-semibold">{t("crm.ed_photos_read").replace("{n}", photoPreviews.length)}</p>
              <p className="text-[11px] text-muted-foreground">{t("crm.ed_photos_read_sub")}</p>
            </div>
            <button onClick={() => setPhotoPreviews([])} className="text-muted-foreground hover:text-foreground" data-testid="photo-preview-close">
              <X className="h-4 w-4" />
            </button>
          </div>
          <div className="flex flex-wrap gap-2">
            {photoPreviews.map((p, i) => (
              <div key={i} className="relative" data-testid={`photo-thumb-${i}`}>
                <img src={p.src} alt={`Photo ${i + 1}`} className="h-16 w-16 object-cover rounded-sm border border-border" />
                <span className="absolute bottom-0 right-0 bg-primary text-primary-foreground text-[10px] px-1 rounded-tl-sm">
                  {p.count}
                </span>
                <button onClick={() => setPhotoPreviews((prev) => prev.filter((_, j) => j !== i))}
                        className="absolute -top-1 -right-1 bg-background border border-border rounded-full h-4 w-4 flex items-center justify-center text-muted-foreground hover:text-foreground"
                        data-testid={`photo-thumb-remove-${i}`}>×</button>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Lignes */}
      <div className="surface p-4 grid gap-3">
        <div className="flex items-center justify-between">
          <p className="font-display font-bold text-sm">{t("crm.lines_title")}</p>
          <div className="flex gap-2 items-center">
            <div className="flex items-center gap-1 mr-1" data-testid="bulk-vat-control">
              <span className="text-[10px] uppercase tracking-wider text-muted-foreground font-bold whitespace-nowrap">{isPT ? "IVA todas as linhas" : "TVA toutes lignes"}</span>
              <select
                value=""
                onChange={(e) => { if (e.target.value !== "") setAllVat(Number(e.target.value)); }}
                data-testid="bulk-vat-select"
                className="rounded-sm border border-border bg-background px-2 h-8 text-sm">
                <option value="">{isPT ? "Aplicar…" : "Appliquer…"}</option>
                {vatRates.map((r) => <option key={r} value={r}>{r === 0 ? (isPT ? "0 % (subcontratação)" : "0 % (sous-traitance)") : `${r}%`}</option>)}
              </select>
            </div>
            <OuvrageComposeDialog onAdd={(line) => setLines((ls) => [...ls, { ...blankLine(), ...line, _saveToLib: false }])} />
            <Button size="sm" variant="outline" className="rounded-sm gap-1" onClick={() => setPickerOpen(true)} data-testid="editor-add-from-lib">
              <BookOpen className="h-3.5 w-3.5" /> {t("crm.from_lib")}
            </Button>
            <Button size="sm" variant="outline" className="rounded-sm gap-1" onClick={addLine} data-testid="editor-add-line">
              <Plus className="h-3.5 w-3.5" /> {t("crm.add_line")}
            </Button>
          </div>
        </div>

        {isPT && (
          <div className="flex items-start gap-2 rounded-sm border border-primary/30 bg-primary/5 px-3 py-2 text-xs" data-testid="pt-iva6-hint">
            <span className="text-base leading-none">💡</span>
            <div className="flex-1">
              <b>Reabilitação de habitação?</b> Obras em imóveis de habitação com mais de 2 anos podem beneficiar do <b>IVA reduzido de 6%</b> (Verba 2.27 do CIVA). Caso contrário, aplica-se a taxa normal de 23%.
            </div>
            <Button size="sm" variant="outline" onClick={() => setAllVat(6)}
                    className="rounded-sm h-7 text-xs shrink-0 text-primary border-primary/40" data-testid="pt-apply-iva6">
              Aplicar 6%
            </Button>
          </div>
        )}

        <div className="hidden md:grid grid-cols-12 gap-2 text-[10px] uppercase tracking-wider text-muted-foreground font-bold px-1">
          <span className="col-span-5">{t("crm.col_designation")}</span>
          <span className="col-span-1 text-center">{t("crm.col_qty")}</span>
          <span className="col-span-1 text-center">{t("crm.col_unit")}</span>
          <span className="col-span-2 text-right">{t("crm.col_price")}</span>
          <span className="col-span-1 text-center">{t("crm.col_vat")}</span>
          <span className="col-span-1 text-right">{t("crm.col_total")}</span>
          <span className="col-span-1" />
        </div>

        {lines.map((l, i) => (
          <div key={i} className="space-y-1.5 border-b border-border/40 pb-2" data-testid={`editor-line-${i}`}>
            <div className="grid grid-cols-2 md:grid-cols-12 gap-2 items-center">
            <Input value={l.designation} onChange={(e) => setLine(i, "designation", e.target.value)}
                   placeholder={t("crm.col_designation")} className="rounded-sm col-span-2 md:col-span-5 h-9"
                   data-testid={`editor-line-designation-${i}`} />
            <Input type="number" step="0.01" value={l.qty} onChange={(e) => setLine(i, "qty", e.target.value)}
                   className="rounded-sm num h-9 md:col-span-1 text-right" data-testid={`editor-line-qty-${i}`} />
            <select value={l.unit} onChange={(e) => setLine(i, "unit", e.target.value)}
                    className="rounded-sm border border-border bg-background px-2 h-9 text-sm md:col-span-1">
              {UNITS.map((u) => <option key={u} value={u}>{u}</option>)}
            </select>
            <Input type="number" step="0.01" value={l.unit_price_ht} onChange={(e) => setLine(i, "unit_price_ht", e.target.value)}
                   className="rounded-sm num h-9 md:col-span-2 text-right" data-testid={`editor-line-price-${i}`} />
            <select value={l.vat_rate} onChange={(e) => setLine(i, "vat_rate", e.target.value)}
                    className="rounded-sm border border-border bg-background px-2 h-9 text-sm md:col-span-1">
              {vatRates.map((r) => <option key={r} value={r}>{r === 0 ? "0 %" : `${r}%`}</option>)}
            </select>
            <span className="md:col-span-1 text-right num text-sm font-bold">
              {eur((Number(l.qty) || 0) * (Number(l.unit_price_ht) || 0))}
            </span>
            <div className="md:col-span-1 flex justify-end">
              <Button size="icon" variant="ghost" className="h-8 w-8 text-destructive"
                      onClick={() => delLine(i)} data-testid={`editor-line-del-${i}`}>
                <Trash2 className="h-4 w-4" />
              </Button>
            </div>
            </div>
            <textarea value={l.description || ""} onChange={(e) => setLine(i, "description", e.target.value)}
                   placeholder={t("crm.ed_desc_ph")}
                   rows={2}
                   className="rounded-sm text-sm w-full bg-background border border-input px-3 py-2 resize-y focus:outline-none focus:ring-1 focus:ring-primary" data-testid={`editor-line-desc-${i}`} />
            <div className="flex items-center justify-between gap-2 flex-wrap">
              <div className="flex items-center gap-1.5">
                <Layers className="h-3.5 w-3.5 text-muted-foreground" />
                <Input list="qe-lots" value={l.category || ""} onChange={(e) => setLine(i, "category", e.target.value)}
                       placeholder={t("crm.ed_lot_ph")} className="rounded-sm h-7 text-xs w-44"
                       data-testid={`editor-line-lot-${i}`} />
              </div>
              <Button size="sm" variant="outline" disabled={aiLineBusy === i || !l.designation.trim()}
                      onClick={() => suggestDescription(i)} data-testid={`editor-line-ai-${i}`}
                      className="rounded-sm gap-1 h-7 text-xs text-primary border-primary/40">
                <Sparkles className={`h-3.5 w-3.5 ${aiLineBusy === i ? "animate-pulse" : ""}`} />
                {aiLineBusy === i ? t("crm.ed_ai_suggesting") : t("crm.ed_ai_suggest")}
              </Button>
            </div>
          </div>
        ))}
        {lines.length === 0 && (
          <p className="text-sm text-muted-foreground text-center py-4">{t("crm.no_lines")}</p>
        )}
        <datalist id="qe-lots">
          {knownLots.map((c) => <option key={c} value={c} />)}
        </datalist>
      </div>

      {/* Récap + sinal + notes */}
      <div className="grid md:grid-cols-2 gap-4">
        <div className="surface p-4 grid gap-3">
          <Label>{t("crm.notes_cond")}</Label>
          <Textarea value={notes} onChange={(e) => setNotes(e.target.value)} rows={4}
                    className="rounded-sm resize-none" placeholder={t("crm.notes_ph")}
                    data-testid="editor-notes" />
          <div>
            <Label>{t("crm.deposit_pct")}</Label>
            <Input type="number" step="1" min="0" max="100" value={depositPct}
                   onChange={(e) => setDepositPct(e.target.value)} className="rounded-sm num mt-1 max-w-[120px]"
                   data-testid="editor-deposit" />
          </div>
        </div>
        <div className="surface p-5 grid gap-2 content-start" data-testid="editor-totals">
          {lotSubtotals.length > 0 && (
            <div className="mb-1 pb-2 border-b border-border" data-testid="editor-lot-subtotals">
              <p className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground mb-1.5 flex items-center gap-1.5">
                <Layers className="h-3.5 w-3.5" /> {t("crm.ed_lot_subtotals")}
              </p>
              {lotSubtotals.map(({ cat, ht }) => (
                <div key={cat} className="flex justify-between text-xs py-0.5" data-testid={`editor-lot-subtotal-${cat}`}>
                  <span className="text-muted-foreground truncate">{cat}</span>
                  <span className="num font-semibold">{eur(ht)}</span>
                </div>
              ))}
            </div>
          )}
          <div className="flex justify-between text-sm"><span className="text-muted-foreground">{t("crm.total_ht")}</span><span className="num font-bold">{eur(totals.ht)}</span></div>
          {Object.entries(totals.tva).sort((a, b) => a[0] - b[0]).map(([r, v]) => (
            <div key={r} className="flex justify-between text-xs"><span className="text-muted-foreground">{t("crm.col_vat")} {r}%</span><span className="num">{eur(v)}</span></div>
          ))}
          <div className="flex justify-between text-lg border-t border-border pt-2 mt-1">
            <span className="font-display font-bold">{t("crm.total_ttc")}</span>
            <span className="num font-extrabold text-primary" data-testid="editor-ttc">{eur(totals.ttc)}</span>
          </div>
          {Number(depositPct) > 0 && (
            <>
              <div className="flex justify-between text-sm"><span className="text-muted-foreground">{t("crm.deposit")} {depositPct}%</span><span className="num">{eur(totals.dep)}</span></div>
              <div className="flex justify-between text-sm"><span className="text-muted-foreground">{t("crm.remaining")}</span><span className="num font-bold">{eur(totals.remaining)}</span></div>
            </>
          )}
        </div>
      </div>

      {/* Library picker */}
      <Dialog open={pickerOpen} onOpenChange={setPickerOpen}>
        <DialogContent className="max-w-xl" data-testid="editor-library-picker">
          <DialogHeader><DialogTitle>{t("crm.add_from_lib_title")}</DialogTitle></DialogHeader>
          <div className="relative">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
            <Input value={pickerQ} onChange={(e) => setPickerQ(e.target.value)} autoFocus
                   placeholder={t("crm.picker_ph")} className="pl-9 rounded-sm"
                   data-testid="editor-picker-search" />
          </div>
          <div className="max-h-[50vh] overflow-y-auto divide-y divide-border mt-2">
            {filteredLib.map((it) => (
              <button key={it.item_id} onClick={() => addFromLib(it)}
                      className="w-full text-left px-2 py-2.5 hover:bg-secondary/30 flex items-center justify-between gap-2"
                      data-testid={`editor-picker-item-${it.item_id}`}>
                <span className="min-w-0">
                  <span className="text-sm font-medium truncate block">{it.designation}</span>
                  <span className="text-[11px] text-muted-foreground">{it.category} · {it.unit}</span>
                </span>
                <Badge variant="outline" className="rounded-sm num shrink-0">{eur(it.unit_price_ht)}</Badge>
              </button>
            ))}
            {filteredLib.length === 0 && <p className="text-sm text-muted-foreground text-center py-6">{t("crm.no_result")}</p>}
          </div>
        </DialogContent>
      </Dialog>

      <Dialog open={reviewOpen} onOpenChange={(v) => { if (!v) closeReview(); }}>
        <DialogContent className="max-w-md" data-testid="video-review-dialog">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2"><FileVideo className="h-5 w-5 text-primary" /> {t("crm.ed_check_video")}</DialogTitle>
          </DialogHeader>
          {reviewInfo.url && (
            <video src={reviewInfo.url} controls playsInline className="w-full rounded-sm bg-black aspect-video object-contain" data-testid="video-review-preview" />
          )}
          <div className="grid grid-cols-2 gap-3">
            <div className="rounded-sm border border-border p-3">
              <p className="text-[11px] uppercase tracking-wide text-muted-foreground flex items-center gap-1"><FileVideo className="h-3 w-3" /> {t("crm.ed_size")}</p>
              <p className="text-lg font-semibold" data-testid="video-review-size">{reviewInfo.sizeMB.toFixed(1)} Mo</p>
            </div>
            <div className="rounded-sm border border-border p-3">
              <p className="text-[11px] uppercase tracking-wide text-muted-foreground flex items-center gap-1"><Clock className="h-3 w-3" /> {t("crm.ed_duration")}</p>
              <p className="text-lg font-semibold" data-testid="video-review-duration">
                {reviewInfo.duration > 0 ? fmtSecs(Math.round(reviewInfo.duration)) : "—"}
              </p>
            </div>
          </div>
          <p className="text-xs text-muted-foreground -mt-1" data-testid="video-review-esttime">
            <Clock className="h-3 w-3 inline mr-1" />
            {t("crm.ed_est_time").replace("{s}", Math.max(12, Math.round((reviewInfo.duration || reviewInfo.sizeMB * 5) * 0.8) + 8))}
          </p>
          {(reviewInfo.duration > 90 || reviewInfo.sizeMB > 30) && (
            <div className="rounded-sm border border-amber-500/40 bg-amber-500/10 p-2.5 text-xs text-amber-600 flex gap-2" data-testid="video-review-warning">
              <AlertTriangle className="h-4 w-4 shrink-0 mt-0.5" />
              <span>{t("crm.ed_video_warn")}</span>
            </div>
          )}
          <div className="flex justify-end gap-2">
            <Button variant="outline" onClick={closeReview} className="rounded-sm" data-testid="video-review-restart">{t("crm.ed_change_video")}</Button>
            <Button onClick={confirmTranscribe} disabled={videoBusy} className="rounded-sm gap-2 bg-primary" data-testid="video-review-transcribe">
              {videoBusy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Sparkles className="h-4 w-4" />} {t("crm.ed_transcribe_now")}
            </Button>
          </div>
        </DialogContent>
      </Dialog>

      <Dialog open={recOpen} onOpenChange={(v) => { if (!v) closeRecorder(); }}>
        <DialogContent className="max-w-lg" data-testid="video-recorder-dialog">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              {recMode === "audio" ? <Mic className="h-5 w-5 text-primary" /> : <Camera className="h-5 w-5 text-primary" />}
              {recMode === "audio" ? t("crm.ed_dictate_quote") : t("crm.ed_film_site")}
            </DialogTitle>
          </DialogHeader>
          <p className="text-xs text-muted-foreground -mt-1">
            {recMode === "audio"
              ? t("crm.ed_audio_hint")
              : t("crm.ed_video_hint")}
          </p>
          {recMode === "audio" ? (
            <div className="relative bg-secondary/40 rounded-sm overflow-hidden h-40 flex flex-col items-center justify-center gap-3" data-testid="audio-recorder-visual">
              <Mic className={`h-12 w-12 ${recording ? "text-red-500 animate-pulse" : "text-muted-foreground"}`} />
              <div className="text-sm font-mono" data-testid="audio-recorder-timer">{fmtSecs(recSecs)}</div>
              {recording && <div className="text-xs text-muted-foreground">{t("crm.ed_saving")}</div>}
            </div>
          ) : (
            <div className="relative bg-black rounded-sm overflow-hidden aspect-video">
              <video ref={videoElRef} muted playsInline autoPlay className="w-full h-full object-contain" data-testid="video-recorder-preview" />
              {recording && (
                <div className="absolute top-2 left-2 flex items-center gap-1.5 bg-black/60 text-white text-xs px-2 py-1 rounded-full" data-testid="video-recorder-timer">
                  <span className="h-2 w-2 rounded-full bg-red-500 animate-pulse" /> {fmtSecs(recSecs)}
                </div>
              )}
            </div>
          )}
          <div className="flex justify-end gap-2">
            <Button variant="outline" onClick={closeRecorder} className="rounded-sm" data-testid="video-recorder-cancel">{t("crm.cancel")}</Button>
            {!recording ? (
              <Button onClick={startRec} disabled={!streamReady} className="rounded-sm gap-2 bg-red-600 hover:bg-red-700" data-testid="video-recorder-start">
                {recMode === "audio" ? <Mic className="h-4 w-4" /> : <Video className="h-4 w-4" />} {streamReady ? t("crm.ed_start") : t("crm.ed_initializing")}
              </Button>
            ) : (
              <Button onClick={stopRec} className="rounded-sm gap-2 bg-primary" data-testid="video-recorder-stop">
                <Square className="h-4 w-4" /> {t("crm.ed_stop_gen")}
              </Button>
            )}
          </div>
        </DialogContent>
      </Dialog>

      <Dialog open={transcriptDialog} onOpenChange={setTranscriptDialog}>
        <DialogContent className="max-w-xl" data-testid="video-transcript-dialog">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2"><Video className="h-5 w-5 text-primary" /> {t("crm.ed_reread_transcript")}</DialogTitle>
          </DialogHeader>
          <p className="text-xs text-muted-foreground -mt-1">
            {t("crm.ed_transcript_hint")}
          </p>
          <Textarea value={transcript} onChange={(e) => setTranscript(e.target.value)} rows={7}
                    data-testid="video-transcript-text" className="rounded-sm text-sm" />
          <div>
            <div className="flex items-center justify-between mb-1">
              <Label className="text-xs">{t("crm.ed_site_photos")}</Label>
              <input type="file" accept="image/*" capture="environment" multiple className="hidden" id="qe-transcript-photos"
                     onChange={(e) => { addTranscriptPhotos(e.target.files); e.target.value = ""; }}
                     data-testid="video-transcript-photo-input" />
              <Button size="sm" variant="outline" onClick={() => document.getElementById("qe-transcript-photos").click()}
                      disabled={transcriptPhotos.length >= 6} className="rounded-sm h-7 text-xs gap-1"
                      data-testid="video-transcript-add-photo">
                <Plus className="h-3 w-3" /> {t("crm.ed_add_photos")}
              </Button>
            </div>
            {transcriptPhotos.length > 0 && (
              <div className="flex flex-wrap gap-2" data-testid="video-transcript-photos">
                {transcriptPhotos.map((src, i) => (
                  <div key={i} className="relative">
                    <img src={src} alt={`photo-${i}`} className="h-14 w-14 object-cover rounded-sm border border-border" />
                    <button onClick={() => setTranscriptPhotos((p) => p.filter((_, k) => k !== i))}
                            className="absolute -top-1.5 -right-1.5 bg-destructive text-white rounded-full h-4 w-4 grid place-items-center text-[10px]"
                            data-testid={`video-transcript-photo-remove-${i}`}>×</button>
                  </div>
                ))}
              </div>
            )}
          </div>
          <div className="flex justify-end gap-2">
            <Button variant="outline" onClick={() => setTranscriptDialog(false)}
                    className="rounded-sm" data-testid="video-transcript-cancel">{t("crm.cancel")}</Button>
            <Button onClick={generateFromTranscript} disabled={transcriptBusy || !transcript.trim()}
                    className="rounded-sm gap-2" data-testid="video-transcript-generate">
              {transcriptBusy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Sparkles className="h-4 w-4" />} {t("crm.ed_gen_quote")}
            </Button>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}
