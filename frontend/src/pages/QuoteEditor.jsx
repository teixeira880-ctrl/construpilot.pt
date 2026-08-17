import { useEffect, useMemo, useState, useCallback } from "react";
import { useParams, useNavigate, useSearchParams } from "react-router-dom";
import { toast } from "sonner";
import {
  Plus, Trash2, Download, Save, BookOpen, Loader2, Search, ArrowLeft, User, Sparkles,
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
  const { t } = useI18n();

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

  const downloadPdf = async () => {
    const d = docId ? { doc_id: docId } : await save();
    if (!d) return;
    try {
      const res = await api.get(`/documents/${d.doc_id}/pdf`, { responseType: "blob" });
      const url = URL.createObjectURL(res.data);
      const a = document.createElement("a");
      a.href = url; a.download = `devis.pdf`; a.click();
      URL.revokeObjectURL(url);
      toast.success(t("crm.pdf_ok"));
    } catch { toast.error(t("crm.pdf_fail")); }
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
          <Button variant="outline" onClick={downloadPdf} className="rounded-sm gap-2" data-testid="editor-pdf-btn">
            <Download className="h-4 w-4" /> {t("crm.pdf")}
          </Button>
          <Button onClick={save} disabled={saving} className="rounded-sm gap-2" data-testid="editor-save-btn">
            {saving ? <Loader2 className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4" />} {t("crm.save")}
          </Button>
        </div>
      </div>

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
    </div>
  );
}
