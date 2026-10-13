import { useEffect, useRef, useState } from "react";
import { toast } from "sonner";
import { Ruler, FileDown, Loader2, Image as ImageIcon, Pencil, EyeOff, Eye, Check, X, RefreshCw, Mail, FileText } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from "@/components/ui/dialog";
import { api } from "@/lib/api";
import GeometryReport, { StudiesPanel } from "@/components/planTakeoff/GeometryReport";
import { runCotesJob } from "@/lib/cotesJobs";

const LABEL = { ok: "OK", warn: "A verificar", ko: "Incoerência", ignored: "Ignorada", nd: "Não determinado" };
const CLS = {
  ok: "bg-emerald-100 text-emerald-800 border-emerald-300",
  warn: "bg-orange-100 text-orange-800 border-orange-300",
  ko: "bg-red-100 text-red-800 border-red-300",
  ignored: "bg-slate-100 text-slate-500 border-slate-300",
  nd: "bg-slate-200 text-slate-600 border-slate-400",
};
const RANK = { ko: 0, warn: 1, nd: 2, ok: 3, ignored: 4 };

async function authedBlob(path) {
  const res = await fetch(`${process.env.REACT_APP_BACKEND_URL}/api${path}`, {
    
    credentials: "include",
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || "Erro do servidor");
  }
  return res.blob();
}

function Summary({ s }) {
  return (
    <div className="flex flex-wrap items-center gap-1.5" data-testid="cotes-summary">
      <Badge className={`rounded-sm border ${CLS[s.verdict]}`} data-testid="cotes-verdict">{LABEL[s.verdict]}</Badge>
      <span className="text-[11px] text-muted-foreground">
        {s.total} cotes · {s.ok} OK · {s.warn} a verificar · <b className="text-red-700">{s.ko} incoerência(s)</b>
        {s.ignored > 0 && ` · ${s.ignored}ignorada(s)`}
        {s.chains_total > 0 && ` · ${s.chains_total}cadeia(s) (${s.chains_ko} KO)`}
        {s.facades_total > 0 && ` · ${s.facades_total}fachada(s) oposta(s) (${s.facades_ko} KO)`}
        {s.elements_total > 0 && ` · ${s.elements_total}elemento(s) (${s.elements_ko} KO)`}
        {(s.anchors_ko > 0 || s.anchors_warn > 0) && ` · ${s.anchors_ko + s.anchors_warn}cota(s) não associada(s)`} · diferença máx. {s.max_delta_cm} cm
      </span>
      {s.conclusion && (
        <p className={`w-full text-[11px] px-1.5 py-1 rounded-sm border ${CLS[s.verdict]}`} data-testid="cotes-conclusion">
          <b>Conclusion rapide :</b> {s.conclusion}
        </p>
      )}
    </div>
  );
}

function Facades({ facades }) {
  if (!facades?.length) return null;
  return (
    <div className="grid gap-1" data-testid="cotes-facades">
      <p className="text-[11px] font-medium">Fachadas opostas (dimensões gerais)</p>
      {facades.map((f, i) => (
        <div key={i} className={`text-[11px] px-1.5 py-1 rounded-sm border ${CLS[f.status]}`} data-testid={`cotes-facade-${i}`}>
          #{f.a_index} {f.a_m.toFixed(2)} m ({f.a_side}) ↔ #{f.b_index} {f.b_m.toFixed(2)} m ({f.b_side}) : diferença {f.delta_cm > 0 ? "+" : ""}{f.delta_cm} cm — {f.niveau}
          {f.status === "ko" && "· implantação não confirmada como retangular, a esclarecer (cota única / diagonal / planta de eixos)"}
          {f.diag && (
            <div className="mt-0.5 font-mono" data-testid={`cotes-facade-diag-${i}`}>
              Esquadria: diagonais ≈ {f.diag.d1_m.toFixed(2)} m / {f.diag.d2_m.toFixed(2)} m → diferença ≈ {Math.abs(f.diag.diff_cm)} cm · desvio angular ≈ {f.diag.angle_deg}° (L {f.diag.L_m.toFixed(2)} × W {f.diag.W_m.toFixed(2)} m, desfasamento {f.diag.offset_cm} cm)
            </div>
          )}
        </div>
      ))}
    </div>
  );
}

function Row({ it, selected, onFocus, onEdit, onToggleIgnore, busy }) {
  const [editing, setEditing] = useState(false);
  const [val, setVal] = useState(it.indicated_m);
  const ref = useRef(null);
  useEffect(() => { if (editing) ref.current?.focus(); }, [editing]);
  const save = async () => {
    const v = Number(String(val).replace(",", "."));
    if (!v || v <= 0) return toast.error("Valeur invalide");
    await onEdit(it.index, v);
    setEditing(false);
  };
  return (
    <tr className={`border-t whitespace-nowrap cursor-pointer ${selected ? "bg-amber-100 text-slate-900" : "hover:bg-muted/60"} ${it.ignored ? "opacity-50" : ""}`}
        data-testid={`cotes-row-${it.index}`} onClick={() => onFocus(it)}>
      <td className="px-1 num">{it.index}<sup className="text-[8px] text-muted-foreground ml-0.5" title={SRC_TITLE[it.source] || ""}>{SRC[it.source] || ""}</sup></td>
      <td className="px-1 truncate max-w-[110px]" title={`${it.location || ""}${it.edited ? `(corrigida, lida${it.original_m})` : ""}`}>
        {it.location || "—"}{it.edited && <span className="text-amber-700"> ✎</span>}
      </td>
      <td className="px-1 text-right num" onClick={(e) => { if (editing) e.stopPropagation(); }}>
        {editing ? (
          <span className="inline-flex items-center gap-0.5">
            <Input ref={ref} value={val} onChange={(e) => setVal(e.target.value)}
                   onKeyDown={(e) => { if (e.key === "Enter") save(); if (e.key === "Escape") setEditing(false); }}
                   className="h-5 w-14 px-1 text-[11px] rounded-sm num" data-testid={`cotes-edit-input-${it.index}`} />
            <button onClick={save} className="text-emerald-700" data-testid={`cotes-edit-save-${it.index}`}><Check className="h-3 w-3" /></button>
            <button onClick={() => setEditing(false)} className="text-muted-foreground"><X className="h-3 w-3" /></button>
          </span>
        ) : it.indicated_m.toFixed(2)}
      </td>
      <td className="px-1 text-right num">{it.measured_m.toFixed(2)}</td>
      <td className="px-1 text-right num">{it.delta_cm > 0 ? "+" : ""}{it.delta_cm}</td>
      <td className="px-1">
        <span className={`inline-block h-2.5 w-2.5 rounded-full border ${CLS[it.status]}`} title={LABEL[it.status]} data-testid={`cotes-status-${it.index}`} />
      </td>
      <td className="px-1" onClick={(e) => e.stopPropagation()}>
        <span className="inline-flex gap-1">
          <button disabled={busy || it.ignored} onClick={() => { setVal(it.indicated_m); setEditing(true); }}
                  className="text-muted-foreground hover:text-foreground disabled:opacity-30" title="Corrigir a cota lida"
                  data-testid={`cotes-edit-btn-${it.index}`}><Pencil className="h-3 w-3" /></button>
          <button disabled={busy} onClick={() => onToggleIgnore(it)} className="text-muted-foreground hover:text-foreground"
                  title={it.ignored ? "Reintegrar a cota" : "Ignorar a cota"} data-testid={`cotes-ignore-btn-${it.index}`}>
            {it.ignored ? <Eye className="h-3 w-3" /> : <EyeOff className="h-3 w-3" />}
          </button>
        </span>
      </td>
    </tr>
  );
}

const SRC = { pdf: "V", dxf: "D", ai: "IA" };
const SRC_TITLE = { pdf: "Cote vectorielle PDF (mesure exacte)", dxf: "Cote DXF (mesure exacte)", ai: "Cote lue par l'IA (mesure pixel)" };

function Reading({ r, calib }) {
  if (!r || r.source === "ai" || !r.source) return null;
  const cross = r.cross;
  const eff = calib?.effective_scale_denominator;
  return (
    <div className="text-[11px] border border-sky-300 bg-sky-50 text-sky-900 rounded-sm px-1.5 py-1 grid gap-0.5" data-testid="cotes-reading">
      <div>
        <b>Lecture {r.source === "dxf" ? "DXF exacte" : "vectorielle PDF + IA (hybride)"}</b>
        {r.source === "pdf_vector+ai" && cross && (
          <> : {cross.vector} cota(s) medidas ao mm no PDF · {cross.confirmed} confirmada(s) pela IA
            {cross.ai_only > 0 && ` · ${cross.ai_only}lida(s) só pela IA (não verificadas, nunca KO)`}</>
        )}
        {eff && <> · escala efetiva 1/{eff}{calib?.scale_denominator && Math.abs(eff - calib.scale_denominator) > 0.5 ? `(declarada 1/${calib.scale_denominator}— PDF reduzido)` : ""}</>}
      </div>
      {cross?.divergences?.length > 0 && (
        <div data-testid="cotes-divergences">
          <b>Divergência(s) de leitura</b> (o texto vetorial prevalece):{" "}
          {cross.divergences.map((d, i) => `« ${d.vector_text} » lu « ${d.ai_text} » par l'IA`).join(" ; ")}
        </div>
      )}
      {r.vector?.partial_vectors && <div>⚠ Vetores parciais (planta importada antes da leitura vetorial) — volte a importar o PDF para uma cobertura completa.</div>}
    </div>
  );
}

function Elements({ elements }) {
  if (!elements?.length) return null;
  const bad = elements.filter((e) => e.status !== "ok");
  const n = { ok: elements.length - bad.length, ko: bad.filter((e) => e.status === "ko").length, warn: bad.filter((e) => e.status === "warn").length };
  return (
    <div className="grid gap-1" data-testid="cotes-elements">
      <p className="text-[11px] font-medium">Elementos desenhados (sapatas, vigas, paredes etiquetadas): largura desenhada vs etiqueta — {elements.length} controlado(s) · {n.ok} OK · {n.warn} a verificar · {n.ko} KO</p>
      {bad.length === 0 && <div className={`text-[11px] px-1.5 py-1 rounded-sm border ${CLS.ok}`}>Todas as larguras desenhadas correspondem às etiquetas (≤ 10 mm).</div>}
      {bad.map((e, i) => (
        <div key={i} className={`text-[11px] px-1.5 py-1 rounded-sm border ${CLS[e.status]}`} data-testid={`cotes-element-${i}`}>
          « {e.label} » : desenhado {(e.measured_w_m * 100).toFixed(1)} cm para {e.w_cm} cm anunciados ({e.delta_mm > 0 ? "+" : ""}{Math.round(e.delta_mm)} mm) — {e.niveau}
        </div>
      ))}
    </div>
  );
}

function Anchors({ items }) {
  const bad = (items || []).filter((it) => !it.ignored && (it.anchor_status === "warn" || it.anchor_status === "ko"));
  if (!bad.length) return null;
  return (
    <div className="grid gap-1" data-testid="cotes-anchors">
      <p className="text-[11px] font-medium">Cotas provavelmente erradas: extremidades não alinhadas com uma face ou um eixo de parede desenhado (projeção perpendicular &gt; 10 mm)</p>
      {bad.map((it) => (
        <div key={it.index} className={`text-[11px] px-1.5 py-1 rounded-sm border ${CLS[it.anchor_status]}`}>
          #{it.index} {it.indicated_m.toFixed(2)} m : extremidades a {it.anchor_mm.map((a) => (a == null ? "—" : `${Math.round(a)} mm`)).join(" / ")} do traço mais próximo
        </div>
      ))}
    </div>
  );
}

function AutoSpans({ spans }) {
  const [open, setOpen] = useState(false);
  if (!spans?.length) return null;
  return (
    <div className="grid gap-1" data-testid="cotes-auto-spans">
      <p className="text-[11px] font-medium">Mesures automatiques — {spans.length} distância(s) desenhada(s) sem cota na planta
        <button className="underline ml-2" onClick={() => setOpen(!open)} data-testid="cotes-auto-spans-toggle">{open ? "Reduzir" : "Afficher"}</button></p>
      {open && (
        <div className="text-[11px] grid grid-cols-2 sm:grid-cols-3 gap-1">
          {spans.map((sp) => (
            <div key={sp.index} className="px-1.5 py-0.5 rounded-sm border border-sky-300 bg-sky-50 text-sky-900 num">
              M{sp.index} · {sp.orientation === "h" ? "horiz." : "vert."} · <b>{sp.measured_m.toFixed(2)} m</b>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function Chains({ chains }) {
  if (!chains?.length) return null;
  return (
    <div className="grid gap-1" data-testid="cotes-chains">
      <p className="text-[11px] font-medium">Cadeias de cotas</p>
      {chains.map((c, i) => (
        <div key={i} className={`text-[11px] px-1.5 py-1 rounded-sm border ${CLS[c.status]}`}>
          #{c.total_index} = {c.total_m.toFixed(2)} m ↔ {c.part_indexes.map((p, j) => `#${p} ${c.parts_m[j].toFixed(2)}`).join(" + ")}
          {" "}= {c.sum_m.toFixed(2)} m ({c.delta_cm > 0 ? "+" : ""}{c.delta_cm} cm)
        </div>
      ))}
    </div>
  );
}

function SendDialog({ open, onClose, plan, pageIndex, report, onSent }) {
  const [email, setEmail] = useState("");
  const [message, setMessage] = useState("");
  const [copyMe, setCopyMe] = useState(true);
  const [busy, setBusy] = useState(false);
  const send = async () => {
    if (!/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(email)) return toast.error("Adresse e-mail invalide");
    setBusy(true);
    try {
      const { data } = await api.post(`/takeoffs/${plan.plan_id}/cotes/send`,
        { page_index: pageIndex, to_email: email, message, copy_me: copyMe });
      toast.success(`Relatório enviado a${data.sent_to}${data.copy_sent ? "(cópia recebida)" : ""}`, { duration: 7000 });
      onSent?.();
      onClose();
    } catch (e) { toast.error(e?.response?.data?.detail || "Envio impossível"); }
    finally { setBusy(false); }
  };
  return (
    <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="rounded-sm sm:max-w-md" data-testid="cotes-send-dialog">
        <DialogHeader>
          <DialogTitle>Enviar o relatório de controlo das cotas</DialogTitle>
          <DialogDescription>
            O PDF (síntese, todas as cotas, cadeias e planta anotada) segue em anexo no e-mail.
            {report && ` Verdict actuel : ${LABEL[report.summary.verdict]} — ${report.summary.ko}incoerência(s).`}
          </DialogDescription>
        </DialogHeader>
        <div className="grid gap-2">
          <Label className="text-xs">Destinatário (arquiteto, cliente, gabinete de projeto)</Label>
          <Input type="email" placeholder="architecte@exemple.fr" value={email} onChange={(e) => setEmail(e.target.value)}
                 className="rounded-sm" data-testid="cotes-send-email" />
          <Label className="text-xs">Message (optionnel)</Label>
          <Textarea rows={4} value={message} onChange={(e) => setMessage(e.target.value)} className="rounded-sm text-sm"
                    placeholder="Bom dia, junto envio o controlo das cotas da planta…" data-testid="cotes-send-message" />
          <label className="flex items-center gap-2 text-xs">
            <input type="checkbox" checked={copyMe} onChange={(e) => setCopyMe(e.target.checked)} data-testid="cotes-send-copy" />
            Enviar-me uma cópia
          </label>
        </div>
        <DialogFooter>
          <Button variant="outline" className="rounded-sm" onClick={onClose} disabled={busy}>Cancelar</Button>
          <Button className="rounded-sm gap-2" onClick={send} disabled={busy} data-testid="cotes-send-submit">
            {busy ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Mail className="h-3.5 w-3.5" />} Enviar
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

export default function CotesCheckPanel({ plan, pageIndex, refreshPlan, selectedIndex = null, onFocusCote }) {
  const [tolPct, setTolPct] = useState(2);
  const [tolCm, setTolCm] = useState(3);
  const [busy, setBusy] = useState(false);
  const [report, setReport] = useState(null);
  const [overlay, setOverlay] = useState(null);
  const [sendOpen, setSendOpen] = useState(false);
  const [study, setStudy] = useState(null);
  const storedRevision = plan?.cotes_checks?.[String(pageIndex)]?.revision;
  const currentStudy = report?.revision && study?.report_revision === report.revision ? study : null;

  useEffect(() => {
    if (!plan?.plan_id) return;
    let cancelled = false;
    setStudy(null);
    api.get(`/takeoffs/${plan.plan_id}/studies?page_index=${pageIndex}`)
      .then((r) => { if (!cancelled) setStudy(r.data?.analysis ? r.data : null); })
      .catch(() => { if (!cancelled) setStudy(null); });
    return () => { cancelled = true; };
  }, [plan?.plan_id, pageIndex, storedRevision]);

  useEffect(() => {
    const r = plan?.cotes_checks?.[String(pageIndex)] || null;
    setReport(r);
    setOverlay(null);
    if (r?.tolerance) { setTolPct(r.tolerance.pct); setTolCm(r.tolerance.cm); }
  }, [plan?.plan_id, plan?.cotes_checks, pageIndex]);

  const tolChanged = report && (Number(tolPct) !== report.tolerance?.pct || Number(tolCm) !== report.tolerance?.cm);

  const apply = async (fn, okMsg) => {
    setBusy(true);
    try {
      const res = await fn();
      const data = res?.data ?? res;
      setReport(data);
      setStudy(null);
      setOverlay(null);
      if (okMsg) toast.success(okMsg(data), { duration: 6000 });
      await refreshPlan?.();
    } catch (e) { toast.error(e?.response?.data?.detail || e?.message || "Operação impossível"); }
    finally { setBusy(false); }
  };

  const run = () => apply(
    () => runCotesJob(`/takeoffs/${plan.plan_id}/cotes/check`, { page_index: pageIndex, tol_pct: Number(tolPct) || 2, tol_cm: Number(tolCm) || 0 }),
    (d) => `${d.summary.total}cotas controladas —${d.summary.ko}incoerência(s)` + (d.auto_calibrated ? "· escala calibrada automaticamente" : ""));
  const recompute = () => apply(
    () => api.post(`/takeoffs/${plan.plan_id}/cotes/recompute`, { page_index: pageIndex, tol_pct: Number(tolPct) || 2, tol_cm: Number(tolCm) || 0 }),
    (d) => `Recalculado com ±${d.tolerance.pct} % / ${d.tolerance.cm} cm — ${d.summary.ko}incoerência(s)`);
  const editItem = (index, indicated_m) => apply(
    () => api.patch(`/takeoffs/${plan.plan_id}/cotes/items/${index}`, { page_index: pageIndex, indicated_m }),
    () => `Cote #${index}corrigida e relatório recalculado`);
  const toggleIgnore = (it) => apply(
    () => api.patch(`/takeoffs/${plan.plan_id}/cotes/items/${it.index}`, { page_index: pageIndex, ignored: !it.ignored }),
    () => (it.ignored ? `Cote #${it.index}reintegrada` : `Cote #${it.index}ignorada`));

  const showOverlay = async () => {
    try {
      const blob = await authedBlob(`/takeoffs/${plan.plan_id}/cotes/overlay.png?page_index=${pageIndex}`);
      setOverlay(URL.createObjectURL(blob));
    } catch (e) { toast.error(e.message); }
  };

  const downloadPdf = async () => {
    try {
      const blob = await authedBlob(`/takeoffs/${plan.plan_id}/cotes/report.pdf?page_index=${pageIndex}`);
      const a = document.createElement("a");
      a.href = URL.createObjectURL(blob);
      a.download = `controle-cotes-p${pageIndex + 1}.pdf`;
      a.click();
      toast.success("Relatório PDF descarregado");
    } catch (e) { toast.error(e.message); }
  };

  const downloadRapport = async () => {
    try {
      const blob = await authedBlob(`/takeoffs/${plan.plan_id}/cotes/rapport.pdf?page_index=${pageIndex}`);
      const a = document.createElement("a");
      a.href = URL.createObjectURL(blob);
      a.download = `rapport-controle-plan-p${pageIndex + 1}.pdf`;
      a.click();
      toast.success("Relatório de controlo da planta transferido");
    } catch (e) { toast.error(e.message); }
  };

  const sorted = report ? [...report.items].sort((a, b) => (RANK[a.status] - RANK[b.status]) || a.index - b.index) : [];

  return (
    <div className="border border-primary/30 bg-primary/5 p-2 rounded-sm grid gap-2" data-testid="cotes-check-panel">
      <p className="overline text-primary">Controlo das cotas</p>
      <p className="text-[11px] text-muted-foreground">
        Relê todas as cotas da planta, mede cada traço à escala e assinala as incoerências (cota indicada ≠ medição, cadeias de cotas que não somam). Clique numa linha para ampliar a cota.
      </p>
      <div className="flex items-center gap-2 text-[11px]">
        <span>Tolerância</span>
        <Input type="number" step="0.5" min="0.1" value={tolPct} onChange={(e) => setTolPct(e.target.value)}
               className="h-7 w-16 rounded-sm num" data-testid="cotes-tol-pct" /> %
        <span>ou</span>
        <Input type="number" step="1" min="0" value={tolCm} onChange={(e) => setTolCm(e.target.value)}
               className="h-7 w-16 rounded-sm num" data-testid="cotes-tol-cm" /> cm
      </div>
      <div className="flex gap-2">
        <Button size="sm" className="flex-1 justify-start gap-2 rounded-sm" disabled={busy} onClick={run} data-testid="cotes-check-btn">
          {busy ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Ruler className="h-3.5 w-3.5" />}
          {busy ? "A ler e medir as cotas…" : report ? "Relancer (relecture IA)" : "Controlar as cotas"}
        </Button>
        {tolChanged && (
          <Button size="sm" variant="outline" className="gap-1 rounded-sm" disabled={busy} onClick={recompute}
                  title="Recalcular com a nova tolerância, sem reler a planta" data-testid="cotes-recompute-btn">
            <RefreshCw className="h-3.5 w-3.5" /> Recalculer
          </Button>
        )}
      </div>
      {report && (
        <div className="grid gap-2" data-testid="cotes-report">
          <Summary s={report.summary} />
          <Reading r={report.reading} calib={report.calibration} />
          {report.abstention && (
            <p className="text-[11px] border border-slate-400 bg-slate-100 text-slate-700 rounded-sm px-1.5 py-1" data-testid="cotes-abstention">
              <b>Abstention ConstruPilot :</b> {report.abstention} ({report.summary.nd} cota(s) não determinada(s))
            </p>
          )}
          <div className="max-h-64 overflow-auto border rounded-sm" data-testid="cotes-table">
            <table className="w-full text-[11px]">
              <thead className="bg-muted sticky top-0">
                <tr><th className="px-1 text-left">#</th><th className="px-1 text-left">Localisation</th>
                  <th className="px-1 text-right">Cote (m)</th><th className="px-1 text-right">Medido (m)</th>
                  <th className="px-1 text-right">Diferença (cm)</th><th className="px-1"></th><th className="px-1"></th></tr>
              </thead>
              <tbody>
                {sorted.map((it) => (
                  <Row key={it.index} it={it} selected={selectedIndex === it.index} busy={busy}
                       onFocus={onFocusCote} onEdit={editItem} onToggleIgnore={toggleIgnore} />
                ))}
              </tbody>
            </table>
          </div>
          <Facades facades={report.facades} />
          <Elements elements={report.elements} />
          <Anchors items={report.items} />
          <AutoSpans spans={report.auto_spans} />
          <Chains chains={report.chains} />
          {report.surfaces?.matches?.length > 0 && (
            <p className="text-[11px] text-muted-foreground" data-testid="cotes-surfaces">
              Áreas escritas: {report.surfaces.matches.length} divisão(ões) comparada(s), diferença mediana {report.surfaces.deviation_pct} %.
            </p>
          )}
          <GeometryReport plan={plan} pageIndex={pageIndex} geo={report.geometry}
                          onUpdated={(geo) => { setReport({ ...report, geometry: geo }); refreshPlan?.(); }}
                          onFocusIndex={(i) => { const it = report.items.find((x) => x.index === i); if (it) onFocusCote?.(it); }} />
          <StudiesPanel plan={plan} pageIndex={pageIndex} study={currentStudy} onUpdated={(data) => { setStudy(data); refreshPlan?.(); }} />
          <div className="flex gap-2">
            <Button size="sm" variant="outline" className="flex-1 gap-2 rounded-sm" onClick={showOverlay} data-testid="cotes-overlay-btn">
              <ImageIcon className="h-3.5 w-3.5" /> Planta anotada
            </Button>
            <Button size="sm" variant="outline" className="flex-1 gap-2 rounded-sm" onClick={downloadPdf} data-testid="cotes-pdf-btn">
              <FileDown className="h-3.5 w-3.5" /> PDF
            </Button>
            <Button size="sm" className="flex-1 gap-2 rounded-sm" onClick={downloadRapport} title="Relatório de controlo da planta ConstruPilot (capa, resumo, cálculos, planta anotada CP-xx, fichas, checklist)" data-testid="cotes-rapport-btn">
              <FileText className="h-3.5 w-3.5" /> Rapport
            </Button>
            <Button size="sm" variant="outline" className="flex-1 gap-2 rounded-sm" onClick={() => setSendOpen(true)} data-testid="cotes-send-btn">
              <Mail className="h-3.5 w-3.5" /> Enviar
            </Button>
          </div>
          {report.last_sent && (
            <p className="text-[11px] text-muted-foreground" data-testid="cotes-last-sent">
              Dernier envoi : {report.last_sent.to_email} · {new Date(report.last_sent.sent_at).toLocaleString("fr-FR")}
            </p>
          )}
          <SendDialog open={sendOpen} onClose={() => setSendOpen(false)} plan={plan} pageIndex={pageIndex}
                      report={report} onSent={() => refreshPlan?.()} />
          {overlay && (
            <a href={overlay} target="_blank" rel="noreferrer" data-testid="cotes-overlay-link">
              <img src={overlay} alt="Planta anotada — cotas medidas" className="w-full border rounded-sm" data-testid="cotes-overlay-img" />
            </a>
          )}
        </div>
      )}
    </div>
  );
}
