import { useEffect, useMemo, useState } from "react";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter,
} from "@/components/ui/dialog";
import {
  Select, SelectTrigger, SelectValue, SelectContent, SelectItem,
} from "@/components/ui/select";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Checkbox } from "@/components/ui/checkbox";
import { api } from "@/lib/api";
import { toast } from "sonner";
import { Loader2, Download, Search, Users, Mail, Filter, X } from "lucide-react";

const DAY = 24 * 60 * 60 * 1000;

function fmtCell(key, val) {
  if (val == null || val === "") return "—";
  if (key.includes("created_at") || key.includes("granted_at") || key.includes("last_seen") || key === "created_at") {
    try { return new Date(val).toLocaleDateString("pt-PT"); } catch { return String(val); }
  }
  if (key.includes("value_eur") || key.includes("amount_eur")) {
    return (Number(val) || 0).toLocaleString("pt-PT", { minimumFractionDigits: 2, maximumFractionDigits: 2 }) + " €";
  }
  return String(val);
}

function toCSV(columns, rows) {
  const esc = (v) => `"${String(v ?? "").replace(/"/g, '""')}"`;
  const head = columns.map((c) => esc(c.label)).join(",");
  const body = rows.map((r) => columns.map((c) => esc(r[c.key])).join(",")).join("\n");
  return head + "\n" + body;
}

/** Drill-down d'un indicateur admin : liste + filtres + sélection + e-mail groupé + export CSV. */
export default function AdminDrillDialog({ metric, onClose, inbox = false, hours }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [q, setQ] = useState("");
  const [planFilter, setPlanFilter] = useState("all");
  const [cityFilter, setCityFilter] = useState("");
  const [inactiveOnly, setInactiveOnly] = useState(false);
  const [selected, setSelected] = useState(() => new Set());
  const [compose, setCompose] = useState(false);
  const [subject, setSubject] = useState("");
  const [message, setMessage] = useState("");
  const [sending, setSending] = useState(false);

  useEffect(() => {
    if (!metric) { setData(null); return; }
    setLoading(true);
    setQ(""); setPlanFilter("all"); setCityFilter(""); setInactiveOnly(false); setSelected(new Set());
    api.get(inbox ? `/admin/drill-inbox/${metric}` : `/admin/drill/${metric}`, { params: inbox && hours ? { hours } : undefined })
      .then(({ data }) => setData(data))
      .catch(() => toast.error("Detalhes indisponíveis"))
      .finally(() => setLoading(false));
  }, [metric, inbox, hours]);

  const emailKey = useMemo(() => {
    if (!data) return null;
    const keys = data.columns.map((c) => c.key);
    return keys.includes("user_email") ? "user_email" : keys.includes("email") ? "email" : null;
  }, [data]);
  const hasPlan = data?.columns.some((c) => c.key === "user_plan");
  const hasCity = data?.columns.some((c) => c.key === "city" || c.key === "address");
  const hasInactive = data?.columns.some((c) => c.key === "last_seen");

  const planOptions = useMemo(() => {
    if (!data || !hasPlan) return [];
    return Array.from(new Set(data.rows.map((r) => r.user_plan).filter(Boolean)));
  }, [data, hasPlan]);

  const rows = useMemo(() => {
    if (!data) return [];
    const needle = q.trim().toLowerCase();
    const city = cityFilter.trim().toLowerCase();
    const cutoff = Date.now() - 30 * DAY;
    return data.rows.filter((r) => {
      if (needle && !Object.values(r).some((v) => String(v ?? "").toLowerCase().includes(needle))) return false;
      if (hasPlan && planFilter !== "all" && r.user_plan !== planFilter) return false;
      if (hasCity && city) {
        const hay = `${r.city ?? ""} ${r.address ?? ""}`.toLowerCase();
        if (!hay.includes(city)) return false;
      }
      if (hasInactive && inactiveOnly) {
        const t = r.last_seen ? Date.parse(r.last_seen) : NaN;
        if (!(isNaN(t) || t < cutoff)) return false;
      }
      return true;
    });
  }, [data, q, planFilter, cityFilter, inactiveOnly, hasPlan, hasCity, hasInactive]);

  const emailsInView = useMemo(
    () => (emailKey ? rows.map((r) => r[emailKey]).filter((e) => e && e !== "—") : []),
    [rows, emailKey]);
  const selectedEmails = useMemo(
    () => emailsInView.filter((e) => selected.has(e)), [emailsInView, selected]);
  const allSelected = emailsInView.length > 0 && selectedEmails.length === emailsInView.length;

  const toggleAll = () => {
    setSelected((prev) => {
      const n = new Set(prev);
      if (allSelected) emailsInView.forEach((e) => n.delete(e));
      else emailsInView.forEach((e) => n.add(e));
      return n;
    });
  };
  const toggleOne = (email) => {
    setSelected((prev) => { const n = new Set(prev); n.has(email) ? n.delete(email) : n.add(email); return n; });
  };

  const exportCSV = () => {
    if (!data || !rows.length) return;
    const csv = toCSV(data.columns, rows);
    const blob = new Blob(["\uFEFF" + csv], { type: "text/csv;charset=utf-8;" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `construpilot-${metric}-${new Date().toISOString().slice(0, 10)}.csv`;
    a.click();
    URL.revokeObjectURL(url);
    toast.success(`${rows.length} linha(s) exportada(s)`);
  };

  const sendBulk = async () => {
    if (selectedEmails.length === 0) { toast.error("Nenhum destinatário selecionado"); return; }
    if (!subject.trim() || !message.trim()) { toast.error("Assunto e mensagem obrigatórios"); return; }
    setSending(true);
    try {
      const { data: res } = await api.post("/admin/bulk-email", {
        recipients: selectedEmails, subject, message,
      });
      toast.success(`${res.sent}/${res.total} e-mail(s) enviado(s)${res.failed ? ` · ${res.failed} falha(s)` : ""}`);
      setCompose(false); setSubject(""); setMessage(""); setSelected(new Set());
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Envio impossível");
    } finally { setSending(false); }
  };

  return (
    <>
      <Dialog open={!!metric && !compose} onOpenChange={(o) => { if (!o) onClose(); }}>
        <DialogContent className="max-w-[95vw] w-[1100px] max-h-[88vh] flex flex-col" data-testid="admin-drill-dialog">
          <DialogHeader>
            <DialogTitle data-testid="admin-drill-title">{data?.title || "Detalhes"}</DialogTitle>
            <DialogDescription>{data?.description || "A carregar…"}</DialogDescription>
          </DialogHeader>
          {data?.conditions?.length > 0 && (
            <div className="rounded-sm border border-border bg-secondary/40 px-3 py-2" data-testid="admin-drill-conditions">
              <p className="text-[10px] uppercase tracking-wide text-muted-foreground flex items-center gap-1"><Filter className="h-3 w-3" /> Condições de contagem</p>
              <ul className="mt-1 grid gap-0.5 text-xs">
                {data.conditions.map((c, i) => <li key={i} className="flex gap-1.5"><span className="text-primary">•</span><span>{c}</span></li>)}
              </ul>
            </div>
          )}

          {/* Recherche + actions */}
          <div className="flex flex-wrap items-center gap-2">
            <div className="relative flex-1 min-w-[220px]">
              <Search className="h-4 w-4 absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" />
              <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Pesquisar (nome, e-mail, cidade…)"
                     className="rounded-sm h-9 pl-9" data-testid="admin-drill-search" />
            </div>
            <span className="text-xs text-muted-foreground whitespace-nowrap flex items-center gap-1" data-testid="admin-drill-count">
              <Users className="h-3.5 w-3.5" /> {rows.length} resultado(s)
            </span>
            {emailKey && (
              <Button size="sm" variant="outline" className="rounded-sm gap-2"
                      disabled={selectedEmails.length === 0} onClick={() => setCompose(true)}
                      data-testid="admin-drill-email-btn">
                <Mail className="h-4 w-4" /> E-mail ({selectedEmails.length})
              </Button>
            )}
            <Button size="sm" className="rounded-sm gap-2" onClick={exportCSV} disabled={!rows.length}
                    data-testid="admin-drill-export">
              <Download className="h-4 w-4" /> Exportar CSV
            </Button>
          </div>

          {/* Filtres cible pub */}
          {(hasPlan || hasCity || hasInactive) && (
            <div className="flex flex-wrap items-center gap-2 text-sm" data-testid="admin-drill-filters">
              <span className="text-muted-foreground flex items-center gap-1"><Filter className="h-3.5 w-3.5" /> Filtros:</span>
              {hasPlan && (
                <Select value={planFilter} onValueChange={setPlanFilter}>
                  <SelectTrigger className="rounded-sm h-8 w-[160px]" data-testid="admin-drill-plan-filter">
                    <SelectValue placeholder="Planta" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="all">Todos os planos</SelectItem>
                    {planOptions.map((p) => <SelectItem key={p} value={p}>{p}</SelectItem>)}
                  </SelectContent>
                </Select>
              )}
              {hasCity && (
                <Input value={cityFilter} onChange={(e) => setCityFilter(e.target.value)}
                       placeholder="Cidade / morada" className="rounded-sm h-8 w-[180px]"
                       data-testid="admin-drill-city-filter" />
              )}
              {hasInactive && (
                <label className="flex items-center gap-2 cursor-pointer" data-testid="admin-drill-inactive-filter">
                  <Checkbox checked={inactiveOnly} onCheckedChange={(v) => setInactiveOnly(!!v)} />
                  Inativos (+30 d)
                </label>
              )}
              {(planFilter !== "all" || cityFilter || inactiveOnly) && (
                <button className="text-xs text-muted-foreground underline flex items-center gap-1"
                        onClick={() => { setPlanFilter("all"); setCityFilter(""); setInactiveOnly(false); }}
                        data-testid="admin-drill-clear-filters">
                  <X className="h-3 w-3" /> Reiniciar
                </button>
              )}
            </div>
          )}

          <div className="overflow-auto border border-border rounded-sm flex-1" data-testid="admin-drill-table-wrap">
            {loading ? (
              <div className="h-40 grid place-items-center"><Loader2 className="h-6 w-6 animate-spin text-primary" /></div>
            ) : !data ? null : rows.length === 0 ? (
              <p className="p-6 text-sm text-muted-foreground text-center">Nenhum dado.</p>
            ) : (
              <table className="w-full text-sm">
                <thead className="sticky top-0 bg-muted/95 backdrop-blur">
                  <tr>
                    {emailKey && (
                      <th className="px-3 py-2 border-b border-border w-8">
                        <Checkbox checked={allSelected} onCheckedChange={toggleAll} data-testid="admin-drill-select-all" />
                      </th>
                    )}
                    {data.columns.map((c) => (
                      <th key={c.key} className="text-left font-semibold px-3 py-2 whitespace-nowrap border-b border-border">
                        {c.label}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {rows.map((r, i) => {
                    const em = emailKey ? r[emailKey] : null;
                    const selectable = em && em !== "—";
                    return (
                      <tr key={i} className="border-b border-border/50 hover:bg-muted/40" data-testid={`admin-drill-row-${i}`}>
                        {emailKey && (
                          <td className="px-3 py-2">
                            {selectable && (
                              <Checkbox checked={selected.has(em)} onCheckedChange={() => toggleOne(em)}
                                        data-testid={`admin-drill-row-check-${i}`} />
                            )}
                          </td>
                        )}
                        {data.columns.map((c) => (
                          <td key={c.key} className="px-3 py-2 align-top max-w-[280px] truncate" title={fmtCell(c.key, r[c.key])}>
                            {fmtCell(c.key, r[c.key])}
                          </td>
                        ))}
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            )}
          </div>
        </DialogContent>
      </Dialog>

      {/* Composer e-mail groupé */}
      <Dialog open={compose} onOpenChange={(o) => { if (!o) setCompose(false); }}>
        <DialogContent className="max-w-lg" data-testid="admin-bulk-email-dialog">
          <DialogHeader>
            <DialogTitle>E-mail promocional</DialogTitle>
            <DialogDescription>
              Envio a {selectedEmails.length} destinatário(s) selecionado(s).
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-3">
            <Input value={subject} onChange={(e) => setSubject(e.target.value)} placeholder="Assunto do e-mail"
                   className="rounded-sm" data-testid="admin-bulk-email-subject" />
            <Textarea value={message} onChange={(e) => setMessage(e.target.value)} rows={7}
                      placeholder="A sua mensagem… (as quebras de linha são conservadas)"
                      className="rounded-sm" data-testid="admin-bulk-email-message" />
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setCompose(false)} data-testid="admin-bulk-email-cancel">Cancelar</Button>
            <Button onClick={sendBulk} disabled={sending} className="gap-2" data-testid="admin-bulk-email-send">
              {sending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Mail className="h-4 w-4" />} Enviar
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}
