import { useEffect, useMemo, useState, useCallback, useRef } from "react";
import { useParams, useNavigate, useSearchParams } from "react-router-dom";
import { toast } from "sonner";
import {
  Plus, Trash2, Download, Save, BookOpen, Loader2, Search, ArrowLeft, User, Sparkles, Ruler, Video, Send,
  Images, Camera, Square, Clock, FileVideo, AlertTriangle,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Badge } from "@/components/ui/badge";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle,
} from "@/components/ui/dialog";
import { SectionTitle } from "@/components/Bits";
import { api } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { useI18n } from "@/context/I18nContext";

const UNITS = ["u", "m²", "ml", "m³", "forfait", "ens", "h", "j", "kg", "L"];
const VAT_RATES = [10, 20, 5.5];
const STATUSES = [
  ["draft", "crm.st_e_draft"], ["sent", "crm.st_e_sent"], ["signed", "crm.st_e_signed"], ["refused", "crm.st_e_refused"],
];
const eur = (n) => (Number(n) || 0).toLocaleString("fr-FR", { minimumFractionDigits: 2, maximumFractionDigits: 2 }) + " €";
const blankLine = () => ({
  designation: "", description: "", unit: "u", qty: 1, unit_price_ht: 0, vat_rate: 10, category: "", _saveToLib: true,
});

export default function QuoteEditor() {
  const { docId: paramDocId } = useParams();
  const [sp] = useSearchParams();
  const nav = useNavigate();
  const { user } = useAuth();
  const { t, lang } = useI18n();

  const [docId, setDocId] = useState(paramDocId || null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [clients, setClients] = useState([]);
  const [library, setLibrary] = useState([]);
  const [pickerOpen, setPickerOpen] = useState(false);
  const [pickerQ, setPickerQ] = useState("");

  const [clientId, setClientId] = useState(sp.get("client") || "");
  const [title, setTitle] = useState("");
  const [notes, setNotes] = useState("");
  const [depositPct, setDepositPct] = useState(0);
  const [status, setStatus] = useState("draft");
  const [number, setNumber] = useState(null);
  const [lines, setLines] = useState([blankLine()]);
  const [aiLineBusy, setAiLineBusy] = useState(null);
  const [planBusy, setPlanBusy] = useState(false);
  const [videoBusy, setVideoBusy] = useState(false);
  const [transcriptDialog, setTranscriptDialog] = useState(false);
  const [transcript, setTranscript] = useState("");
  const [transcriptBusy, setTranscriptBusy] = useState(false);
  const [transcriptPhotos, setTranscriptPhotos] = useState([]);
  const [docType, setDocType] = useState(
    ["invoice", "credit_note"].includes(sp.get("type")) ? sp.get("type") : "quote");

  const applyDoc = useCallback((d) => {
    setDocId(d.doc_id);
    setClientId(d.client_id || "");
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

  const setLine = (i, k, v) => setLines((ls) => ls.map((l, idx) => idx === i ? { ...l, [k]: v } : l));
  const addLine = () => setLines((ls) => [...ls, blankLine()]);
  const delLine = (i) => setLines((ls) => ls.filter((_, idx) => idx !== i));

  const suggestDescription = async (i) => {
    const l = lines[i];
    if (!l?.designation.trim()) return toast.error("Renseignez d'abord la désignation");
    setAiLineBusy(i);
    try {
      const { data } = await api.post("/documents/ai/describe", {
        designation: l.designation, context: title || "",
      });
      const suggestion = (data.description || "").trim();
      if (!suggestion) return toast.error("Aucune suggestion générée");
      setLines((ls) => ls.map((ln, idx) => idx === i
        ? { ...ln, description: ln.description?.trim() ? ln.description + "\n" + suggestion : suggestion }
        : ln));
      toast.success("Suggestions IA ajoutées à la description");
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Suggestion IA indisponible");
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
          type: "ouvrage", category: l.category || "Devis", designation: l.designation,
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

  const addPlanFromFile = async (file) => {
    if (!file) return;
    if (file.size > 20 * 1024 * 1024) { toast.error("Fichier trop volumineux (>20 Mo)"); return; }
    setPlanBusy(true);
    try {
      const fd = new FormData();
      fd.append("file", file);
      const { data } = await api.post("/takeoffs/upload", fd, { headers: { "Content-Type": "multipart/form-data" } });
      toast.success("Plan importé — ouverture de l'outil Mesurer");
      nav(`/plan?open=${data.plan_id}&auto=1`);
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Import du plan impossible");
    } finally { setPlanBusy(false); }
  };

  // --- Enregistreur vidéo intégré basse résolution (480p) ---
  const [recOpen, setRecOpen] = useState(false);
  const [recording, setRecording] = useState(false);
  const [recSecs, setRecSecs] = useState(0);
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
    setRecording(false);
    setRecSecs(0);
    setRecOpen(false);
  };

  const openRecorder = async () => {
    if (!navigator.mediaDevices?.getUserMedia) { toast.error("Caméra non supportée — utilisez la galerie"); return; }
    setRecOpen(true);
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: true,
        video: {
          facingMode: { ideal: "environment" },
          width: { ideal: 640 }, height: { ideal: 480 },
          frameRate: { ideal: 24, max: 30 },
        },
      });
      streamRef.current = stream;
      if (videoElRef.current) { videoElRef.current.srcObject = stream; videoElRef.current.play().catch(() => {}); }
    } catch {
      toast.error("Accès caméra refusé — utilisez la galerie");
      closeRecorder();
    }
  };

  const startRec = () => {
    const stream = streamRef.current;
    if (!stream) return;
    chunksRef.current = [];
    const cand = ["video/webm;codecs=vp8,opus", "video/webm", "video/mp4"];
    const mime = cand.find((m) => window.MediaRecorder && MediaRecorder.isTypeSupported(m)) || "";
    const rec = new MediaRecorder(stream, mime ? { mimeType: mime, videoBitsPerSecond: 600000 } : {});
    rec.ondataavailable = (e) => { if (e.data && e.data.size) chunksRef.current.push(e.data); };
    rec.onstop = () => {
      const blob = new Blob(chunksRef.current, { type: rec.mimeType || "video/webm" });
      const ext = (rec.mimeType || "").includes("mp4") ? "mp4" : "webm";
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
    if (file.size > 80 * 1024 * 1024) { toast.error("Vidéo trop volumineuse (>80 Mo) — filmez plus court"); return; }
    const url = URL.createObjectURL(file);
    const sizeMB = file.size / (1024 * 1024);
    const finalize = (duration) => {
      setReviewFile(file);
      setReviewInfo({ sizeMB, duration: isFinite(duration) && duration > 0 ? duration : 0, url });
      setReviewOpen(true);
    };
    const v = document.createElement("video");
    v.preload = "metadata";
    v.muted = true;
    v.onloadedmetadata = () => {
      if (v.duration === Infinity || isNaN(v.duration)) {
        v.currentTime = 1e101;
        v.ontimeupdate = () => { v.ontimeupdate = null; finalize(v.duration); };
      } else finalize(v.duration);
    };
    v.onerror = () => finalize(0);
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
    if (file.size > 80 * 1024 * 1024) { toast.error("Vidéo trop volumineuse (>80 Mo) — filmez plus court"); return; }
    setVideoBusy(true);
    const tid = toast.loading("Transcription de la vidéo…");
    try {
      const fd = new FormData();
      fd.append("file", file);
      const { data } = await api.post("/documents/video-transcribe", fd, {
        headers: { "Content-Type": "multipart/form-data" }, timeout: 180000,
      });
      toast.success("Transcription prête — relisez et corrigez avant de générer", { id: tid });
      setTranscript(data.transcript || "");
      setTranscriptPhotos([]);
      setTranscriptDialog(true);
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Transcription impossible", { id: tid });
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
    if (!transcript.trim()) { toast.error("La transcription est vide"); return; }
    setTranscriptBusy(true);
    const tid = toast.loading("Génération du devis…");
    try {
      const { data } = await api.post("/documents/from-text", { text: transcript, images: transcriptPhotos });
      toast.success(
        data.priced_lines > 0
          ? `Devis créé — ${data.priced_lines} ligne(s) chiffrée(s) depuis votre bibliothèque`
          : "Devis créé à partir de la description", { id: tid });
      setTranscriptDialog(false);
      nav(`/devis-editeur/${data.doc_id}`);
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Génération du devis impossible", { id: tid });
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

  const openSend = async () => {
    const c = clients.find((x) => x.client_id === clientId);
    const nm = [c?.first_name, c?.last_name].filter(Boolean).join(" ") || c?.company || c?.name || "";
    setSendEmail(c?.email || "");
    setSendName(nm);
    setSendMsg("");
    setPreview3d(null);
    setPdfPreviewUrl(null);
    setSendOpen(true);
    let id = docId;
    if (!id) { const d = await save(); if (!d) return; id = d.doc_id; }
    // Aperçu rendu 3D
    api.get(`/documents/${id}`).then(({ data }) => {
      if (data?.attachment_image_b64) setPreview3d(data.attachment_image_b64);
    }).catch(() => {});
    // Aperçu PDF
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
      toast.error("Email client invalide"); return;
    }
    setSending(true);
    try {
      let id = docId;
      if (!id) { const d = await save(); if (!d) { setSending(false); return; } id = d.doc_id; }
      await api.post(`/documents/${id}/send`, { client_email: sendEmail, client_name: sendName, message: sendMsg, attach_3d: attach3d })
        .then(({ data }) => {
          toast.success(data?.attached_3d ? "Devis envoyé (rendu 3D joint) ✅" : "Devis envoyé au client ✅");
        });
      closeSend(false);
      setStatus("sent");
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Envoi impossible");
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
          <button onClick={() => nav("/devis")} className="text-xs text-muted-foreground hover:text-foreground flex items-center gap-1 mb-2" data-testid="editor-back">
            <ArrowLeft className="h-3 w-3" /> {t("crm.ed_back")}
          </button>
          <SectionTitle
            over={number
              ? `${{ quote: t("crm.doc_quote"), invoice: t("crm.doc_invoice"), credit_note: t("crm.doc_credit") }[docType]} ${number}`
              : `${t("crm.ed_new")} ${{ quote: t("crm.doc_quote"), invoice: t("crm.doc_invoice"), credit_note: t("crm.doc_credit") }[docType]}`}
            title={`${t("crm.ed_editor")} ${{ quote: t("crm.doc_quote"), invoice: t("crm.doc_invoice"), credit_note: t("crm.doc_credit") }[docType]}`}>
            {t("crm.ed_sub")}
          </SectionTitle>
        </div>
        <div className="flex gap-2">
          <input type="file" accept="image/*,application/pdf,.dxf" className="hidden" id="qe-plan-input"
                 onChange={(e) => { addPlanFromFile(e.target.files?.[0]); e.target.value = ""; }}
                 data-testid="editor-add-plan-input" />
          <Button variant="outline" onClick={() => document.getElementById("qe-plan-input").click()}
                  disabled={planBusy} className="rounded-sm gap-2 text-primary border-primary/40" data-testid="editor-add-plan-btn">
            {planBusy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Ruler className="h-4 w-4" />} Ajouter un plan
          </Button>
          <input type="file" accept="video/*" className="hidden" id="qe-video-input"
                 onChange={(e) => { reviewVideo(e.target.files?.[0]); e.target.value = ""; }}
                 data-testid="editor-video-input" />
          <Button variant="outline" onClick={() => document.getElementById("qe-video-input").click()}
                  disabled={videoBusy} className="rounded-sm gap-2 text-primary border-primary/40" data-testid="editor-video-gallery-btn">
            {videoBusy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Images className="h-4 w-4" />} Vidéo galerie
          </Button>
          <Button variant="outline" onClick={openRecorder}
                  disabled={videoBusy} className="rounded-sm gap-2 text-primary border-primary/40" data-testid="editor-video-record-btn">
            {videoBusy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Video className="h-4 w-4" />} Filmer → devis
          </Button>
          <Button variant="outline" onClick={downloadPdf} className="rounded-sm gap-2" data-testid="editor-pdf-btn">
            <Download className="h-4 w-4" /> {t("crm.pdf")}
          </Button>
          <Button onClick={save} disabled={saving} variant="outline" className="rounded-sm gap-2" data-testid="editor-save-btn">
            {saving ? <Loader2 className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4" />} {t("crm.save")}
          </Button>
          <Button onClick={openSend} disabled={saving || docType !== "quote"} className="rounded-sm gap-2 bg-primary" data-testid="editor-send-btn">
            <Send className="h-4 w-4" /> Envoyer le devis
          </Button>
        </div>
      </div>

      <Dialog open={sendOpen} onOpenChange={closeSend}>
        <DialogContent data-testid="send-quote-dialog">
          <DialogHeader>
            <DialogTitle>Envoyer le devis au client</DialogTitle>
          </DialogHeader>
          <div className="grid gap-4 max-h-[70vh] overflow-y-auto pr-1">
            {(pdfPreviewUrl || preview3d) && (
              <div className="grid gap-2" data-testid="send-preview">
                <p className="text-xs font-semibold text-muted-foreground">Aperçu avant envoi</p>
                <div className="grid grid-cols-2 gap-2">
                  {pdfPreviewUrl ? (
                    <iframe title="Aperçu PDF" src={pdfPreviewUrl} data-testid="send-preview-pdf"
                            className="w-full h-40 rounded-sm border border-border bg-white" />
                  ) : (
                    <div className="w-full h-40 rounded-sm border border-border grid place-items-center text-[10px] text-muted-foreground">PDF…</div>
                  )}
                  {preview3d ? (
                    <img src={preview3d} alt="Rendu 3D" data-testid="send-preview-3d"
                         className="w-full h-40 object-contain rounded-sm border border-border bg-secondary/30" />
                  ) : (
                    <div className="w-full h-40 rounded-sm border border-dashed border-border grid place-items-center text-[10px] text-muted-foreground text-center px-2">Aucun rendu 3D pour ce devis</div>
                  )}
                </div>
              </div>
            )}
            <div className="grid gap-1.5">
              <Label htmlFor="send-name">Nom du client</Label>
              <Input id="send-name" value={sendName} onChange={(e) => setSendName(e.target.value)}
                     placeholder="Nom du client" data-testid="send-quote-name" />
            </div>
            <div className="grid gap-1.5">
              <Label htmlFor="send-email">Email du client *</Label>
              <Input id="send-email" type="email" value={sendEmail} onChange={(e) => setSendEmail(e.target.value)}
                     placeholder="client@email.com" data-testid="send-quote-email" />
            </div>
            <div className="grid gap-1.5">
              <Label htmlFor="send-msg">Message (optionnel)</Label>
              <Textarea id="send-msg" rows={3} value={sendMsg} onChange={(e) => setSendMsg(e.target.value)}
                        placeholder="Un mot pour votre client…" data-testid="send-quote-msg" />
            </div>
            <label className="flex items-center gap-2 text-sm cursor-pointer" data-testid="send-quote-attach3d">
              <input type="checkbox" checked={attach3d} onChange={(e) => setAttach3d(e.target.checked)}
                     className="h-4 w-4 rounded border-input accent-primary" />
              Joindre le rendu 3D du projet (si disponible)
            </label>
            <div className="flex justify-end gap-2">
              <Button variant="outline" onClick={() => closeSend(false)} className="rounded-sm" data-testid="send-quote-cancel">Annuler</Button>
              <Button onClick={sendNow} disabled={sending} className="rounded-sm gap-2" data-testid="send-quote-confirm">
                {sending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />} Envoyer
              </Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>

      {/* Meta : client, titre, statut */}
      <div className="surface p-4 grid md:grid-cols-3 gap-3">
        <div>
          <Label className="flex items-center gap-1"><User className="h-3 w-3" /> {t("crm.client_lbl")}</Label>
          <select value={clientId} onChange={(e) => setClientId(e.target.value)} data-testid="editor-client-select"
                  className="mt-1 w-full rounded-sm border border-border bg-background px-3 py-2 text-sm outline-none focus:border-primary">
            <option value="">{t("crm.no_client")}</option>
            {clients.map((c) => (
              <option key={c.client_id} value={c.client_id}>
                {[c.first_name, c.last_name].filter(Boolean).join(" ") || c.company || c.email}
              </option>
            ))}
          </select>
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

      {/* Lignes */}
      <div className="surface p-4 grid gap-3">
        <div className="flex items-center justify-between">
          <p className="font-display font-bold text-sm">{t("crm.lines_title")}</p>
          <div className="flex gap-2">
            <Button size="sm" variant="outline" className="rounded-sm gap-1" onClick={() => setPickerOpen(true)} data-testid="editor-add-from-lib">
              <BookOpen className="h-3.5 w-3.5" /> {t("crm.from_lib")}
            </Button>
            <Button size="sm" variant="outline" className="rounded-sm gap-1" onClick={addLine} data-testid="editor-add-line">
              <Plus className="h-3.5 w-3.5" /> {t("crm.add_line")}
            </Button>
          </div>
        </div>

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
              {VAT_RATES.map((r) => <option key={r} value={r}>{r}%</option>)}
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
                   placeholder="Description / détail de l'ouvrage (optionnel — archivé en bibliothèque)"
                   rows={2}
                   className="rounded-sm text-sm w-full bg-background border border-input px-3 py-2 resize-y focus:outline-none focus:ring-1 focus:ring-primary" data-testid={`editor-line-desc-${i}`} />
            <div className="flex justify-end">
              <Button size="sm" variant="outline" disabled={aiLineBusy === i || !l.designation.trim()}
                      onClick={() => suggestDescription(i)} data-testid={`editor-line-ai-${i}`}
                      className="rounded-sm gap-1 h-7 text-xs text-primary border-primary/40">
                <Sparkles className={`h-3.5 w-3.5 ${aiLineBusy === i ? "animate-pulse" : ""}`} />
                {aiLineBusy === i ? "Suggestion…" : "Suggestions IA"}
              </Button>
            </div>
          </div>
        ))}
        {lines.length === 0 && (
          <p className="text-sm text-muted-foreground text-center py-4">{t("crm.no_lines")}</p>
        )}
      </div>

      {/* Récap + acompte + notes */}
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
            <DialogTitle className="flex items-center gap-2"><FileVideo className="h-5 w-5 text-primary" /> Vérifier la vidéo</DialogTitle>
          </DialogHeader>
          {reviewInfo.url && (
            <video src={reviewInfo.url} controls playsInline className="w-full rounded-sm bg-black aspect-video object-contain" data-testid="video-review-preview" />
          )}
          <div className="grid grid-cols-2 gap-3">
            <div className="rounded-sm border border-border p-3">
              <p className="text-[11px] uppercase tracking-wide text-muted-foreground flex items-center gap-1"><FileVideo className="h-3 w-3" /> Taille</p>
              <p className="text-lg font-semibold" data-testid="video-review-size">{reviewInfo.sizeMB.toFixed(1)} Mo</p>
            </div>
            <div className="rounded-sm border border-border p-3">
              <p className="text-[11px] uppercase tracking-wide text-muted-foreground flex items-center gap-1"><Clock className="h-3 w-3" /> Durée</p>
              <p className="text-lg font-semibold" data-testid="video-review-duration">
                {reviewInfo.duration > 0 ? fmtSecs(Math.round(reviewInfo.duration)) : "—"}
              </p>
            </div>
          </div>
          <p className="text-xs text-muted-foreground -mt-1" data-testid="video-review-esttime">
            <Clock className="h-3 w-3 inline mr-1" />
            Temps de traitement estimé : ~{Math.max(12, Math.round((reviewInfo.duration || reviewInfo.sizeMB * 5) * 0.8) + 8)} s
          </p>
          {(reviewInfo.duration > 90 || reviewInfo.sizeMB > 30) && (
            <div className="rounded-sm border border-amber-500/40 bg-amber-500/10 p-2.5 text-xs text-amber-600 flex gap-2" data-testid="video-review-warning">
              <AlertTriangle className="h-4 w-4 shrink-0 mt-0.5" />
              <span>Cette vidéo est longue/lourde et la transcription sera plus lente. Pour aller plus vite, refilmez une séquence plus courte (30-60 s suffisent) en décrivant l'essentiel.</span>
            </div>
          )}
          <div className="flex justify-end gap-2">
            <Button variant="outline" onClick={closeReview} className="rounded-sm" data-testid="video-review-restart">Changer de vidéo</Button>
            <Button onClick={confirmTranscribe} disabled={videoBusy} className="rounded-sm gap-2 bg-primary" data-testid="video-review-transcribe">
              {videoBusy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Sparkles className="h-4 w-4" />} Transcrire maintenant
            </Button>
          </div>
        </DialogContent>
      </Dialog>

      <Dialog open={recOpen} onOpenChange={(v) => { if (!v) closeRecorder(); }}>
        <DialogContent className="max-w-lg" data-testid="video-recorder-dialog">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2"><Camera className="h-5 w-5 text-primary" /> Filmer le chantier</DialogTitle>
          </DialogHeader>
          <p className="text-xs text-muted-foreground -mt-1">
            Enregistrement en basse résolution (480p) pour un envoi rapide. Décrivez les travaux à voix haute.
          </p>
          <div className="relative bg-black rounded-sm overflow-hidden aspect-video">
            <video ref={videoElRef} muted playsInline autoPlay className="w-full h-full object-contain" data-testid="video-recorder-preview" />
            {recording && (
              <div className="absolute top-2 left-2 flex items-center gap-1.5 bg-black/60 text-white text-xs px-2 py-1 rounded-full" data-testid="video-recorder-timer">
                <span className="h-2 w-2 rounded-full bg-red-500 animate-pulse" /> {fmtSecs(recSecs)}
              </div>
            )}
          </div>
          <div className="flex justify-end gap-2">
            <Button variant="outline" onClick={closeRecorder} className="rounded-sm" data-testid="video-recorder-cancel">Annuler</Button>
            {!recording ? (
              <Button onClick={startRec} disabled={!streamRef.current} className="rounded-sm gap-2 bg-red-600 hover:bg-red-700" data-testid="video-recorder-start">
                <Video className="h-4 w-4" /> Démarrer
              </Button>
            ) : (
              <Button onClick={stopRec} className="rounded-sm gap-2 bg-primary" data-testid="video-recorder-stop">
                <Square className="h-4 w-4" /> Arrêter & générer
              </Button>
            )}
          </div>
        </DialogContent>
      </Dialog>

      <Dialog open={transcriptDialog} onOpenChange={setTranscriptDialog}>
        <DialogContent className="max-w-xl" data-testid="video-transcript-dialog">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2"><Video className="h-5 w-5 text-primary" /> Relire la transcription</DialogTitle>
          </DialogHeader>
          <p className="text-xs text-muted-foreground -mt-1">
            Corrigez la transcription si besoin, puis générez le devis (lignes chiffrées depuis votre bibliothèque).
          </p>
          <Textarea value={transcript} onChange={(e) => setTranscript(e.target.value)} rows={7}
                    data-testid="video-transcript-text" className="rounded-sm text-sm" />
          <div>
            <div className="flex items-center justify-between mb-1">
              <Label className="text-xs">Photos du chantier (optionnel, max 6)</Label>
              <input type="file" accept="image/*" capture="environment" multiple className="hidden" id="qe-transcript-photos"
                     onChange={(e) => { addTranscriptPhotos(e.target.files); e.target.value = ""; }}
                     data-testid="video-transcript-photo-input" />
              <Button size="sm" variant="outline" onClick={() => document.getElementById("qe-transcript-photos").click()}
                      disabled={transcriptPhotos.length >= 6} className="rounded-sm h-7 text-xs gap-1"
                      data-testid="video-transcript-add-photo">
                <Plus className="h-3 w-3" /> Ajouter des photos
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
                    className="rounded-sm" data-testid="video-transcript-cancel">Annuler</Button>
            <Button onClick={generateFromTranscript} disabled={transcriptBusy || !transcript.trim()}
                    className="rounded-sm gap-2" data-testid="video-transcript-generate">
              {transcriptBusy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Sparkles className="h-4 w-4" />} Générer le devis
            </Button>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}
