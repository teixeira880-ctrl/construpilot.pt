import { useEffect, useState } from "react";
import { toast } from "sonner";
import { ClipboardCheck, Plus, Trash2, Download, PenLine, Send, Loader2, CheckCircle2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { api } from "@/lib/api";

const BASE = process.env.REACT_APP_BACKEND_URL;
const DECISIONS = [
  ["sans_reserve", "Sem reservas"],
  ["avec_reserve", "Com reservas"],
  ["refus", "Receção recusada"],
];
const STATUS = { draft: ["Rascunho", "bg-slate-100 text-slate-600"], published: ["Partilhado com o cliente", "bg-sky-100 text-sky-700"], signed: ["Assinado pelo cliente", "bg-emerald-100 text-emerald-700"] };

export function ReceptionPanel({ chantierId }) {
  const [list, setList] = useState([]);
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [form, setForm] = useState({ decision: "sans_reserve", date_reception: "", notes: "", reserves: [], import_open_reserves: true });

  const load = () => api.get(`/chantiers/${chantierId}/receptions`).then(({ data }) => setList(data)).catch(() => {});
  useEffect(() => { load(); /* eslint-disable-next-line */ }, [chantierId]);

  const create = async () => {
    setBusy(true);
    try {
      await api.post(`/chantiers/${chantierId}/receptions`, {
        ...form, reserves: form.reserves.filter((r) => (r.description || "").trim()),
      });
      toast.success("Auto de receção criado");
      setOpen(false); setForm({ decision: "sans_reserve", date_reception: "", notes: "", reserves: [], import_open_reserves: true });
      load();
    } catch (e) { toast.error(e?.response?.data?.detail || "Criação impossível"); }
    finally { setBusy(false); }
  };

  const sign = async (pv) => {
    const name = window.prompt("O seu nome para assinar o auto (do lado da empresa)", "");
    if (!name || name.trim().length < 2) return;
    try { await api.post(`/chantiers/receptions/${pv.pv_id}/sign`, { signature: name.trim() }); toast.success("Assinado do lado da empresa"); load(); }
    catch { toast.error("Assinatura impossível"); }
  };
  const publish = async (pv) => {
    try { await api.post(`/chantiers/receptions/${pv.pv_id}/publish`); toast.success("Partilhado com o cliente no seu portal"); load(); }
    catch { toast.error("Partilha impossível"); }
  };
  const remove = async (pv) => {
    if (!window.confirm("Eliminar este auto?")) return;
    try { await api.delete(`/chantiers/receptions/${pv.pv_id}`); load(); }
    catch (e) { toast.error(e?.response?.data?.detail || "Não foi possível eliminar"); }
  };

  return (
    <section className="surface" data-testid="chantier-receptions">
      <div className="flex items-center justify-between p-4 border-b border-border">
        <p className="font-display font-bold text-sm flex items-center gap-2"><ClipboardCheck className="h-4 w-4 text-primary" /> Receção da obra <span className="text-muted-foreground font-normal">({list.length})</span></p>
        <Button size="sm" variant="ghost" className="h-7 gap-1" onClick={() => setOpen(true)} data-testid="pv-new-btn"><Plus className="h-3.5 w-3.5" /> Novo auto</Button>
      </div>
      <div className="divide-y divide-border">
        {list.length === 0 && <p className="p-4 text-sm text-muted-foreground">Nenhum auto. Crie um para formalizar a receção e as reservas, e depois mande-o assinar online.</p>}
        {list.map((pv) => {
          const [label, cls] = STATUS[pv.status] || ["—", "bg-slate-100"];
          return (
            <div key={pv.pv_id} className="p-4 flex flex-wrap items-center gap-2" data-testid={`pv-row-${pv.pv_id}`}>
              <div className="min-w-0 flex-1">
                <p className="text-sm font-medium">{pv.ref} · {DECISIONS.find((d) => d[0] === pv.decision)?.[1]}</p>
                <p className="text-xs text-muted-foreground">
                  Receção {(pv.date_reception || "").slice(0, 10)} · {(pv.reserves || []).length} reserva(s)
                  {pv.pro_signature?.name ? ` · empresa: ${pv.pro_signature.name}` : ""}
                  {pv.client_signature?.name ? ` · cliente: ${pv.client_signature.name}` : ""}
                </p>
              </div>
              <span className={`text-[10px] font-bold uppercase px-2 py-0.5 rounded-full ${cls}`}>{label}</span>
              {!pv.pro_signature && <Button size="sm" variant="outline" className="h-7 rounded-sm text-[11px] gap-1" onClick={() => sign(pv)} data-testid={`pv-sign-${pv.pv_id}`}><PenLine className="h-3 w-3" /> Assinar</Button>}
              {pv.status === "draft" && <Button size="sm" variant="outline" className="h-7 rounded-sm text-[11px] gap-1" onClick={() => publish(pv)} data-testid={`pv-publish-${pv.pv_id}`}><Send className="h-3 w-3" /> Partilhar</Button>}
              <a href={`${BASE}/api/chantiers/receptions/${pv.pv_id}/pdf`} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 rounded-sm border px-2.5 py-1.5 text-[11px] hover:bg-secondary" data-testid={`pv-pdf-${pv.pv_id}`}><Download className="h-3 w-3" /> PDF</a>
              {!pv.client_signature && <button onClick={() => remove(pv)} className="text-muted-foreground hover:text-red-500" data-testid={`pv-delete-${pv.pv_id}`}><Trash2 className="h-3.5 w-3.5" /></button>}
              {pv.client_signature && <CheckCircle2 className="h-4 w-4 text-emerald-600" title="Assinado pelo cliente" />}
            </div>
          );
        })}
      </div>

      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="max-w-lg" data-testid="pv-create-dialog">
          <DialogHeader><DialogTitle>Novo auto de receção</DialogTitle></DialogHeader>
          <div className="grid gap-3">
            <div>
              <Label className="text-xs">Decisão</Label>
              <div className="flex gap-1 mt-1">
                {DECISIONS.map(([k, l]) => (
                  <Button key={k} type="button" size="sm" variant={form.decision === k ? "default" : "outline"} className="rounded-sm h-8 text-xs"
                          onClick={() => setForm((f) => ({ ...f, decision: k }))} data-testid={`pv-decision-${k}`}>{l}</Button>
                ))}
              </div>
            </div>
            <div>
              <Label className="text-xs">Data de receção</Label>
              <Input type="date" value={form.date_reception} onChange={(e) => setForm((f) => ({ ...f, date_reception: e.target.value }))} className="rounded-sm mt-1 max-w-[200px]" data-testid="pv-date" />
            </div>
            <label className="flex items-center gap-2 text-xs text-muted-foreground">
              <input type="checkbox" checked={form.import_open_reserves} onChange={(e) => setForm((f) => ({ ...f, import_open_reserves: e.target.checked }))} data-testid="pv-import-reserves" />
              Retomar automaticamente as reservas em aberto da obra
            </label>
            <div>
              <div className="flex items-center justify-between">
                <Label className="text-xs">Reservas adicionadas manualmente</Label>
                <Button type="button" size="sm" variant="ghost" className="h-7 text-xs gap-1 px-2" onClick={() => setForm((f) => ({ ...f, reserves: [...f.reserves, { lot: "", description: "" }] }))} data-testid="pv-add-reserve"><Plus className="h-3.5 w-3.5" /> Adicionar</Button>
              </div>
              {form.reserves.map((r, i) => (
                <div key={i} className="flex items-center gap-2 mt-1" data-testid={`pv-reserve-row-${i}`}>
                  <Input value={r.lot} placeholder="Lote" onChange={(e) => setForm((f) => ({ ...f, reserves: f.reserves.map((x, j) => j === i ? { ...x, lot: e.target.value } : x) }))} className="rounded-sm h-8 w-28 text-sm" />
                  <Input value={r.description} placeholder="Descrição da reserva" onChange={(e) => setForm((f) => ({ ...f, reserves: f.reserves.map((x, j) => j === i ? { ...x, description: e.target.value } : x) }))} className="rounded-sm h-8 flex-1 text-sm" data-testid={`pv-reserve-desc-${i}`} />
                  <button type="button" onClick={() => setForm((f) => ({ ...f, reserves: f.reserves.filter((_, j) => j !== i) }))} className="text-muted-foreground hover:text-red-500"><Trash2 className="h-3.5 w-3.5" /></button>
                </div>
              ))}
            </div>
            <div>
              <Label className="text-xs">Observações</Label>
              <Textarea value={form.notes} onChange={(e) => setForm((f) => ({ ...f, notes: e.target.value }))} rows={2} className="rounded-sm mt-1 resize-none" placeholder="ex.: Reservas a levantar em 30 dias" data-testid="pv-notes" />
            </div>
            <Button onClick={create} disabled={busy} className="rounded-sm gap-2" data-testid="pv-create-confirm">{busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <ClipboardCheck className="h-4 w-4" />} Criar o auto</Button>
          </div>
        </DialogContent>
      </Dialog>
    </section>
  );
}
