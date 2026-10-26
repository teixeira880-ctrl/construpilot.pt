import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { FileDown, ShieldCheck, Loader2, CheckCircle2, XCircle } from "lucide-react";
import { toast } from "sonner";
import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

// Página pública (sem conta) onde o engenheiro consulta o anteprojeto do autopiloto BET e o visa ou emite reservas.
export default function VistoBet() {
  const { token } = useParams();
  const [data, setData] = useState(null);
  const [err, setErr] = useState(null);
  const [busy, setBusy] = useState(false);
  const [form, setForm] = useState({ signatory: "", title: "", ordem_numero: "", decision: "visar", comment: "" });

  const load = () => api.get(`/publico/bet-visto/${token}`).then((r) => setData(r.data)).catch(() => setErr("Ligação de visto inválida ou expirada."));
  useEffect(() => { load(); /* eslint-disable-next-line */ }, [token]);

  const pdf = async () => {
    setBusy(true);
    try {
      const { data: blob } = await api.get(`/publico/bet-visto/${token}/cofragem.pdf`, { responseType: "blob", timeout: 120000 });
      const u = URL.createObjectURL(blob);
      window.open(u, "_blank", "noopener");
      setTimeout(() => URL.revokeObjectURL(u), 60000);
    } catch { toast.error("PDF indisponível de momento."); }
    finally { setBusy(false); }
  };

  const submit = async () => {
    if (form.signatory.trim().length < 2) return toast.error("Indique o seu nome.");
    if (form.decision === "recusar" && !form.comment.trim()) return toast.error("Indique o motivo ou as reservas.");
    setBusy(true);
    try {
      const { data: r } = await api.post(`/publico/bet-visto/${token}/assinar`, form);
      toast.success(r.status === "visado" ? "Visto registado. Obrigado." : "Reservas enviadas.");
      await load();
    } catch (e) { toast.error(e?.response?.data?.detail || "Envio impossível."); }
    finally { setBusy(false); }
  };

  const s = data?.summary || {};
  const done = data && data.status !== "pendente";
  return (
    <div className="min-h-screen bg-background" data-testid="visto-bet-page">
      <header className="border-b bg-card"><div className="max-w-3xl mx-auto px-4 py-4 flex items-center gap-3">
        <Link to="/" className="font-bold text-lg">ConstruPilot</Link>
        <span className="text-xs text-muted-foreground flex items-center gap-1"><ShieldCheck size={14} /> Visto do engenheiro — anteprojeto de estrutura</span>
      </div></header>
      <main className="max-w-3xl mx-auto px-4 py-8 grid gap-6">
        {err && <p className="text-sm text-red-600" data-testid="visto-bet-error">{err}</p>}
        {!data && !err && <div className="flex items-center gap-2 text-sm text-muted-foreground"><Loader2 className="h-4 w-4 animate-spin" /> A carregar…</div>}
        {data && (<>
          <div className="grid gap-1">
            <div className="text-xs uppercase tracking-widest text-primary font-semibold">Pedido de visto</div>
            <h1 className="text-2xl sm:text-3xl font-bold tracking-tight" data-testid="visto-bet-title">{data.project_name}</h1>
            <p className="text-sm text-muted-foreground">Engenheiro solicitado: {data.engineer_name}{data.engineer_title ? ` · ${data.engineer_title}` : ""}</p>
          </div>
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 text-xs">
            <div className="border rounded-md p-2"><span className="text-muted-foreground">Elementos</span><p className="text-base font-semibold">{s.total_elements ?? "—"}</p></div>
            <div className="border rounded-md p-2"><span className="text-muted-foreground">Sapatas</span><p className="text-base font-semibold">{s.n_footings ?? "—"}{s.footing_type ? ` ${s.footing_type}` : ""}</p></div>
            <div className="border rounded-md p-2"><span className="text-muted-foreground">Laje</span><p className="text-base font-semibold">{s.floor_system || "—"}</p></div>
            <div className="border rounded-md p-2"><span className="text-muted-foreground">Estudo geotécnico</span><p className="text-base font-semibold">{data.soil_confirmed ? "confirmado" : "a confirmar"}</p></div>
          </div>
          <Button variant="outline" onClick={pdf} disabled={busy} className="w-fit gap-2" data-testid="visto-bet-pdf"><FileDown className="h-4 w-4" /> Plantas de cofragem e armaduras (PDF)</Button>
          {data.reserva && <p className="text-xs italic text-muted-foreground border-l-2 border-amber-400 pl-3" data-testid="visto-bet-reserva">{data.reserva}</p>}
          {done ? (
            <div className={`rounded-md border p-4 ${data.status === "visado" ? "border-emerald-400 bg-emerald-50 dark:bg-emerald-950/20" : "border-red-400 bg-red-50 dark:bg-red-950/20"}`} data-testid="visto-bet-decision">
              <p className="font-semibold flex items-center gap-2">{data.status === "visado" ? <><CheckCircle2 className="h-4 w-4 text-emerald-600" /> Anteprojeto visado</> : <><XCircle className="h-4 w-4 text-red-600" /> Visto recusado — reservas</>}</p>
              <p className="text-sm mt-1">Por {data.signatory}{data.title ? ` · ${data.title}` : ""}{data.ordem_numero ? ` · ${data.ordem_numero}` : ""} em {data.decided_at ? new Date(data.decided_at).toLocaleDateString("pt-PT") : ""}</p>
              {data.comment && <p className="text-sm mt-2 italic">«{data.comment}»</p>}
            </div>
          ) : (
            <div className="rounded-md border p-4 grid gap-3" data-testid="visto-bet-form">
              <p className="text-sm font-medium">Visar ou emitir reservas</p>
              <div className="grid sm:grid-cols-2 gap-3">
                <label className="grid gap-1 text-xs">Nome completo<Input value={form.signatory} onChange={(e) => setForm({ ...form, signatory: e.target.value })} data-testid="visto-signatory" /></label>
                <label className="grid gap-1 text-xs">Qualidade (engenheiro civil…)<Input value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} /></label>
                <label className="grid gap-1 text-xs">N.º de membro da Ordem (facultativo)<Input value={form.ordem_numero} onChange={(e) => setForm({ ...form, ordem_numero: e.target.value })} data-testid="visto-ordem" /></label>
                <label className="grid gap-1 text-xs">Decisão
                  <select className="h-9 rounded-md border bg-background px-2 text-sm" value={form.decision} onChange={(e) => setForm({ ...form, decision: e.target.value })} data-testid="visto-decision">
                    <option value="visar">Viso o anteprojeto</option>
                    <option value="recusar">Recuso / emito reservas</option>
                  </select>
                </label>
              </div>
              <label className="grid gap-1 text-xs">Comentário / reservas {form.decision === "recusar" && <span className="text-red-600">(obrigatório)</span>}
                <textarea rows={3} className="rounded-md border bg-background p-2 text-sm" value={form.comment} onChange={(e) => setForm({ ...form, comment: e.target.value })} data-testid="visto-comment" />
              </label>
              <p className="text-[11px] text-muted-foreground">Ao visar, confirma ter verificado as hipóteses e o pré-dimensionamento deste anteprojeto sob a sua responsabilidade profissional.</p>
              <Button onClick={submit} disabled={busy} className="w-full sm:w-auto" data-testid="visto-submit">{busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <ShieldCheck className="h-4 w-4" />} {form.decision === "visar" ? "Assinar e visar" : "Enviar reservas"}</Button>
            </div>
          )}
        </>)}
      </main>
    </div>
  );
}
