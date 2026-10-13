import { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import { LifeBuoy, Send, Clock, CheckCircle2, MessageSquare, ChevronDown } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { api } from "@/lib/api";

const ST = { new: ["Novo", "bg-red-500/10 text-red-700 border-red-500/30"], in_progress: ["En cours", "bg-amber-500/10 text-amber-700 border-amber-500/30"], answered: ["Respondido", "bg-blue-500/10 text-blue-700 border-blue-500/30"], closed: ["Encerrado", "bg-muted text-muted-foreground"] };
const fmt = (iso) => (iso ? new Date(iso).toLocaleString("fr-FR", { dateStyle: "short", timeStyle: "short" }) : "—");
const hrs = (h) => (h == null ? "—" : h < 1 ? `${Math.round(h * 60)} min` : h < 48 ? `${h} h` : `${Math.round(h / 24)} j`);

function Stat({ label, value, testId }) {
  return <div className="surface p-4"><p className="text-[11px] uppercase tracking-wide text-muted-foreground">{label}</p><p className="font-display text-xl font-bold num" data-testid={testId}>{value}</p></div>;
}

function Ticket({ t, onChanged }) {
  const [open, setOpen] = useState(t.status === "new");
  const [reply, setReply] = useState("");
  const [busy, setBusy] = useState(false);
  const [label, cls] = ST[t.status] || ST.new;
  const setStatus = async (status) => { try { await api.put(`/admin/support/${t.ticket_id}`, { status }); onChanged(); } catch { toast.error("Não foi possível atualizar"); } };
  const send = async (close) => {
    setBusy(true);
    try {
      const { data } = await api.post(`/admin/support/${t.ticket_id}/reply`, { message: reply, close });
      if (data.email_status === "sent") { toast.success(close ? "Resposta enviada, pedido encerrado" : "Resposta enviada"); setReply(""); onChanged(); }
      else toast.error("E-mail não enviado (Resend) — o pedido continua aberto");
    } catch (e) { toast.error(e?.response?.data?.detail || "Envio impossível"); } finally { setBusy(false); }
  };
  return (
    <div className="surface" data-testid={`ticket-${t.ticket_id}`}>
      <button type="button" onClick={() => setOpen((o) => !o)} className="w-full text-left px-4 py-3 flex flex-wrap items-center gap-2" data-testid={`ticket-toggle-${t.ticket_id}`}>
        <span className="font-mono text-xs text-muted-foreground">{t.ticket_id}</span>
        <span className="font-semibold text-sm flex-1 min-w-[200px] truncate">{t.subject}</span>
        <Badge variant="outline" className={`rounded-sm text-[10px] ${cls}`} data-testid={`ticket-status-${t.ticket_id}`}>{label}</Badge>
        <span className="text-xs text-muted-foreground">{t.name} · {t.email}</span>
        <span className="text-xs text-muted-foreground inline-flex items-center gap-1" title="Prazo"><Clock className="h-3 w-3" /> {t.status === "closed" ? `resolvido em${hrs(t.resolution_hours)}` : t.first_response_hours != null ? `1.ª resposta${hrs(t.first_response_hours)}` : `attente ${hrs(t.waiting_hours)}`}</span>
        <ChevronDown className={`h-4 w-4 transition-transform ${open ? "rotate-180" : ""}`} />
      </button>
      {open && (
        <div className="px-4 pb-4 grid gap-3 border-t border-border pt-3">
          <p className="text-xs text-muted-foreground">Recebido em {fmt(t.created_at)}{t.page ? `· desde${t.page}` : ""} · aviso de receção: {t.email_status === "sent" ? "enviado" : "falha"}</p>
          <p className="text-sm whitespace-pre-wrap bg-muted/40 rounded-md p-3" data-testid={`ticket-message-${t.ticket_id}`}>{t.message}</p>
          {(t.replies || []).map((r, i) => <div key={i} className="text-sm rounded-md border border-primary/30 bg-primary/5 p-3"><p className="text-[11px] text-muted-foreground">{fmt(r.at)} · {r.by} · e-mail {r.email_status === "sent" ? "enviado" : "falha"}</p><p className="whitespace-pre-wrap mt-1">{r.message}</p></div>)}
          <div className="grid gap-2">
            <textarea value={reply} onChange={(e) => setReply(e.target.value)} rows={3} placeholder="Resposta rápida enviada por e-mail ao requerente…" className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm resize-none" data-testid={`ticket-reply-${t.ticket_id}`} />
            <div className="flex flex-wrap items-center gap-2">
              <select value={t.status} onChange={(e) => setStatus(e.target.value)} className="h-8 rounded-md border border-input bg-background px-2 text-xs" data-testid={`ticket-status-select-${t.ticket_id}`}>{Object.entries(ST).map(([v, [l]]) => <option key={v} value={v}>{l}</option>)}</select>
              <a href={`mailto:${t.email}?subject=${encodeURIComponent(`Re: [Assistance ${t.ticket_id}] ${t.subject}`)}`} className="text-xs text-primary underline">Responder a partir do meu e-mail</a>
              <div className="ms-auto flex gap-2">
                <Button size="sm" variant="outline" className="h-8 gap-1" disabled={busy || reply.trim().length < 2} onClick={() => send(false)} data-testid={`ticket-send-${t.ticket_id}`}><Send className="h-3.5 w-3.5" /> Enviar</Button>
                <Button size="sm" className="h-8 gap-1" disabled={busy || reply.trim().length < 2} onClick={() => send(true)} data-testid={`ticket-send-close-${t.ticket_id}`}><CheckCircle2 className="h-3.5 w-3.5" /> Enviar e encerrar</Button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export default function SupportTicketsPanel() {
  const [data, setData] = useState(null);
  const [filter, setFilter] = useState("");
  const load = useCallback(() => api.get("/admin/support", { params: filter ? { status: filter } : {} }).then(({ data }) => setData(data)).catch(() => toast.error("Não foi possível carregar")), [filter]);
  useEffect(() => { load(); }, [load]);
  if (!data) return <p className="text-sm text-muted-foreground">A carregar…</p>;
  const s = data.stats;
  return (
    <div className="grid gap-4" data-testid="admin-support">
      <div className="flex items-center gap-2"><LifeBuoy className="h-5 w-5 text-primary" /><h2 className="font-display text-lg font-bold">Demandes d'assistance</h2><span className="text-xs text-muted-foreground">formulário /ajuda</span></div>
      <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
        <Stat label="A tratar" value={s.counts.new + s.counts.in_progress} testId="support-open" />
        <Stat label="Respondidos" value={s.counts.answered} testId="support-answered" />
        <Stat label="Encerrados" value={s.counts.closed} testId="support-closed" />
        <Stat label="1.ª resposta (média)" value={hrs(s.avg_first_response_hours)} testId="support-avg-first" />
        <Stat label="Respondido < 24 h" value={s.answered_within_24h_pct == null ? "—" : `${s.answered_within_24h_pct} %`} testId="support-24h" />
      </div>
      <div className="flex flex-wrap gap-1">{[["", "Todos"], ...Object.entries(ST).map(([v, [l]]) => [v, l])].map(([v, l]) => <button key={v} type="button" onClick={() => setFilter(v)} aria-pressed={filter === v} className={`text-xs rounded-sm border px-2 py-1 ${filter === v ? "bg-primary/10 border-primary/40 text-primary font-semibold" : "hover:bg-muted"}`} data-testid={`support-filter-${v || "all"}`}>{l}{v && ` (${s.counts[v]})`}</button>)}</div>
      {data.tickets.length === 0 ? <p className="text-sm text-muted-foreground surface p-6 text-center" data-testid="support-empty"><MessageSquare className="h-5 w-5 mx-auto mb-2" />Nenhum pedido.</p>
        : <div className="grid gap-2">{data.tickets.map((t) => <Ticket key={t.ticket_id} t={t} onChanged={load} />)}</div>}
    </div>
  );
}
