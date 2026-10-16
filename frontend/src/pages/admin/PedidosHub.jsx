// AK.3 — Hub admin de pedidos (CRM lite).
// Lista, filtra, pagina + modal detalhes + estado + notas + export CSV/XLSX.
import { useCallback, useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { api, API } from "@/lib/api";

const KIND_LABELS = {
  contact: "Contacto",
  quote: "Orçamento",
  ai_chat: "Chat IA",
  permit: "Autorização",
  download: "Download",
  calculation: "Cálculo",
};
const KIND_COLORS = {
  contact: "bg-sky-500/15 text-sky-700 border-sky-500/30",
  quote: "bg-emerald-500/15 text-emerald-700 border-emerald-500/30",
  ai_chat: "bg-purple-500/15 text-purple-700 border-purple-500/30",
  permit: "bg-amber-500/15 text-amber-700 border-amber-500/30",
  download: "bg-slate-500/15 text-slate-700 border-slate-500/30",
  calculation: "bg-indigo-500/15 text-indigo-700 border-indigo-500/30",
};
const STATES = ["novo", "em_curso", "respondido", "fechado"];
const STATE_LABELS = {
  novo: "Novo",
  em_curso: "Em curso",
  respondido: "Respondido",
  fechado: "Fechado",
};

function fmtDate(iso) {
  if (!iso) return "";
  try {
    return new Date(iso).toLocaleString("pt-PT", {
      day: "2-digit", month: "2-digit", year: "numeric",
      hour: "2-digit", minute: "2-digit",
    });
  } catch { return iso; }
}

function Chip({ kind }) {
  return (
    <span
      data-testid={`kind-chip-${kind}`}
      className={`px-2 py-0.5 rounded text-xs border ${KIND_COLORS[kind] || ""}`}
    >
      {KIND_LABELS[kind] || kind}
    </span>
  );
}

export default function PedidosHub({ fixedKind = null, pageTitle = "Pedidos" }) {
  const [params, setParams] = useSearchParams();
  const [items, setItems] = useState([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [pageSize] = useState(50);
  const [loading, setLoading] = useState(true);
  const [filters, setFilters] = useState({
    kind: fixedKind ? [fixedKind] : [],
    state: [],
    q: "",
  });
  const [selected, setSelected] = useState(null);

  const queryString = useMemo(() => {
    const sp = new URLSearchParams();
    (filters.kind || []).forEach((k) => sp.append("kind", k));
    (filters.state || []).forEach((s) => sp.append("state", s));
    if (filters.q) sp.set("q", filters.q);
    sp.set("page", page);
    sp.set("page_size", pageSize);
    return sp.toString();
  }, [filters, page, pageSize]);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const { data } = await api.get(`/admin/activity?${queryString}`);
      setItems(data.items || []);
      setTotal(data.total || 0);
    } catch (e) {
      console.error("activity load", e);
    } finally {
      setLoading(false);
    }
  }, [queryString]);

  useEffect(() => { load(); }, [load]);

  // Deep-link ?id=xxx abre modal
  useEffect(() => {
    const id = params.get("id");
    if (id && !selected) {
      api.get(`/admin/activity/${id}`).then(({ data }) => setSelected(data)).catch(() => {});
    }
  }, [params, selected]);

  const toggleKind = (k) => {
    if (fixedKind) return; // kind fixo nas páginas por tipo
    setFilters((f) => ({
      ...f,
      kind: f.kind.includes(k) ? f.kind.filter((x) => x !== k) : [...f.kind, k],
    }));
    setPage(1);
  };
  const toggleState = (s) => {
    setFilters((f) => ({
      ...f,
      state: f.state.includes(s) ? f.state.filter((x) => x !== s) : [...f.state, s],
    }));
    setPage(1);
  };

  const exportFile = async (format) => {
    const sp = new URLSearchParams();
    (filters.kind || []).forEach((k) => sp.append("kind", k));
    (filters.state || []).forEach((s) => sp.append("state", s));
    if (filters.q) sp.set("q", filters.q);
    sp.set("format", format);
    const url = `${API}/admin/activity/export?${sp.toString()}`;
    const r = await fetch(url, { credentials: "include" });
    const blob = await r.blob();
    const dl = document.createElement("a");
    dl.href = URL.createObjectURL(blob);
    dl.download = `pedidos.${format}`;
    dl.click();
    URL.revokeObjectURL(dl.href);
  };

  const updateItem = async (id, patch) => {
    const { data } = await api.patch(`/admin/activity/${id}`, patch);
    setItems((xs) => xs.map((x) => (x.id === id ? data : x)));
    if (selected?.id === id) setSelected(data);
  };

  return (
    <div data-testid="pedidos-hub" className="p-4 md:p-6 space-y-4">
      <header className="flex flex-col md:flex-row md:items-center md:justify-between gap-3">
        <h1 className="text-2xl md:text-3xl font-semibold tracking-tight">
          {pageTitle}
          <span className="ml-3 text-sm text-muted-foreground">
            ({total.toLocaleString("pt-PT")} registo{total === 1 ? "" : "s"})
          </span>
        </h1>
        <div className="flex gap-2">
          <button
            data-testid="export-csv-btn"
            onClick={() => exportFile("csv")}
            className="px-3 py-1.5 rounded border hover:bg-accent text-sm"
          >
            Exportar CSV
          </button>
          <button
            data-testid="export-xlsx-btn"
            onClick={() => exportFile("xlsx")}
            className="px-3 py-1.5 rounded border hover:bg-accent text-sm"
          >
            Exportar Excel
          </button>
        </div>
      </header>

      {/* Filtros */}
      <div className="flex flex-wrap gap-3 items-center bg-muted/30 p-3 rounded">
        {!fixedKind && (
          <div className="flex flex-wrap gap-1" data-testid="filter-kinds">
            {Object.keys(KIND_LABELS).map((k) => (
              <button
                key={k}
                data-testid={`filter-kind-${k}`}
                onClick={() => toggleKind(k)}
                className={`px-2 py-1 rounded text-xs border transition ${
                  filters.kind.includes(k) ? "bg-primary text-primary-foreground" : "hover:bg-accent"
                }`}
              >
                {KIND_LABELS[k]}
              </button>
            ))}
          </div>
        )}
        <div className="flex flex-wrap gap-1" data-testid="filter-states">
          {STATES.map((s) => (
            <button
              key={s}
              data-testid={`filter-state-${s}`}
              onClick={() => toggleState(s)}
              className={`px-2 py-1 rounded text-xs border transition ${
                filters.state.includes(s) ? "bg-primary text-primary-foreground" : "hover:bg-accent"
              }`}
            >
              {STATE_LABELS[s]}
            </button>
          ))}
        </div>
        <input
          data-testid="search-input"
          placeholder="Procurar email/nome/resumo…"
          value={filters.q}
          onChange={(e) => { setFilters((f) => ({ ...f, q: e.target.value })); setPage(1); }}
          className="flex-1 min-w-[180px] px-3 py-1.5 rounded border bg-background text-sm"
        />
      </div>

      {/* Tabela desktop / cards mobile */}
      <div className="rounded border bg-background overflow-hidden">
        <table className="hidden md:table w-full text-sm">
          <thead className="bg-muted/40">
            <tr className="text-left">
              <th className="p-2">Data</th>
              <th className="p-2">Cliente</th>
              <th className="p-2">Tipo</th>
              <th className="p-2">Resumo</th>
              <th className="p-2">Estado</th>
            </tr>
          </thead>
          <tbody data-testid="pedidos-rows">
            {loading && (
              <tr><td colSpan={5} className="p-6 text-center text-muted-foreground">A carregar…</td></tr>
            )}
            {!loading && items.length === 0 && (
              <tr><td colSpan={5} className="p-6 text-center text-muted-foreground">Sem pedidos nos filtros actuais.</td></tr>
            )}
            {items.map((it) => (
              <tr
                key={it.id}
                data-testid={`pedido-row-${it.id}`}
                onClick={() => setSelected(it)}
                className="border-t hover:bg-accent/40 cursor-pointer"
              >
                <td className="p-2 whitespace-nowrap">{fmtDate(it.created_at)}</td>
                <td className="p-2">
                  <div className="font-medium">{it.user_name || "—"}</div>
                  <div className="text-xs text-muted-foreground">{it.user_email}</div>
                </td>
                <td className="p-2"><Chip kind={it.kind} /></td>
                <td className="p-2 max-w-xs truncate" title={it.summary}>{it.summary}</td>
                <td className="p-2">
                  <select
                    data-testid={`state-select-${it.id}`}
                    value={it.state}
                    onClick={(e) => e.stopPropagation()}
                    onChange={(e) => updateItem(it.id, { state: e.target.value })}
                    className="px-2 py-1 rounded border bg-background text-xs"
                  >
                    {STATES.map((s) => <option key={s} value={s}>{STATE_LABELS[s]}</option>)}
                  </select>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        <div className="md:hidden divide-y">
          {items.map((it) => (
            <div
              key={it.id}
              data-testid={`pedido-card-${it.id}`}
              onClick={() => setSelected(it)}
              className="p-3 space-y-1"
            >
              <div className="flex items-center justify-between gap-2">
                <Chip kind={it.kind} />
                <span className="text-xs text-muted-foreground">{fmtDate(it.created_at)}</span>
              </div>
              <div className="text-sm font-medium">{it.user_name || it.user_email}</div>
              <div className="text-xs text-muted-foreground">{it.user_email}</div>
              <div className="text-sm truncate">{it.summary}</div>
              <div className="text-xs">
                Estado: <strong>{STATE_LABELS[it.state]}</strong>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Paginação */}
      <div className="flex items-center justify-between text-sm">
        <span className="text-muted-foreground">
          Página {page} de {Math.max(1, Math.ceil(total / pageSize))}
        </span>
        <div className="flex gap-2">
          <button
            data-testid="prev-page-btn"
            disabled={page <= 1}
            onClick={() => setPage((p) => Math.max(1, p - 1))}
            className="px-3 py-1 rounded border disabled:opacity-40"
          >Anterior</button>
          <button
            data-testid="next-page-btn"
            disabled={page * pageSize >= total}
            onClick={() => setPage((p) => p + 1)}
            className="px-3 py-1 rounded border disabled:opacity-40"
          >Seguinte</button>
        </div>
      </div>

      {/* Modal detalhe */}
      {selected && (
        <DetailModal
          activity={selected}
          onClose={() => { setSelected(null); setParams({}); }}
          onUpdate={(patch) => updateItem(selected.id, patch)}
        />
      )}
    </div>
  );
}

function DetailModal({ activity, onClose, onUpdate }) {
  const [note, setNote] = useState("");
  const [sending, setSending] = useState(false);
  const [sendEmail, setSendEmail] = useState(false);

  const addNote = async () => {
    if (!note.trim()) return;
    setSending(true);
    try {
      await api.post(`/admin/activity/${activity.id}/notes`, { text: note });
      setNote("");
      // reload do próprio
      const { data } = await api.get(`/admin/activity/${activity.id}`);
      onUpdate({ _reload: data });  // trigger re-render via parent (hack)
      Object.assign(activity, data);
    } finally { setSending(false); }
  };

  return (
    <div
      data-testid="detail-modal"
      className="fixed inset-0 z-50 bg-black/50 flex items-center justify-center p-4"
      onClick={onClose}
    >
      <div
        className="bg-background rounded-lg shadow-xl max-w-2xl w-full max-h-[90vh] overflow-y-auto"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="sticky top-0 bg-background border-b p-4 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Chip kind={activity.kind} />
            <strong>{activity.user_name || activity.user_email}</strong>
          </div>
          <button data-testid="close-modal-btn" onClick={onClose} className="text-xl leading-none">×</button>
        </div>
        <div className="p-4 space-y-4">
          <section>
            <h3 className="font-medium text-sm text-muted-foreground mb-1">Resumo</h3>
            <p className="text-sm">{activity.summary}</p>
            <p className="text-xs text-muted-foreground mt-1">
              {fmtDate(activity.created_at)} — {activity.user_email}
              {activity.user_phone ? ` · ${activity.user_phone}` : ""}
              {activity.source_url ? ` · ${activity.source_url}` : ""}
            </p>
          </section>

          <section className="grid grid-cols-2 gap-3">
            <label className="text-sm">
              <div className="text-xs text-muted-foreground mb-1">Estado</div>
              <select
                data-testid="modal-state-select"
                value={activity.state}
                onChange={(e) => onUpdate({ state: e.target.value, send_email: sendEmail || undefined })}
                className="w-full px-3 py-1.5 rounded border bg-background"
              >
                {STATES.map((s) => <option key={s} value={s}>{STATE_LABELS[s]}</option>)}
              </select>
            </label>
            <label className="text-sm flex items-center gap-2 mt-5">
              <input
                data-testid="send-email-checkbox"
                type="checkbox"
                checked={sendEmail}
                onChange={(e) => setSendEmail(e.target.checked)}
              />
              <span>Enviar email ao cliente</span>
            </label>
          </section>

          {activity.payload && Object.keys(activity.payload).length > 0 && (
            <section>
              <h3 className="font-medium text-sm text-muted-foreground mb-1">Metadados</h3>
              <pre className="text-xs bg-muted/40 p-2 rounded overflow-x-auto">
{JSON.stringify(activity.payload, null, 2)}
              </pre>
            </section>
          )}

          <section>
            <h3 className="font-medium text-sm text-muted-foreground mb-2">Histórico de estado</h3>
            {(activity.state_history || []).length === 0 ? (
              <p className="text-xs text-muted-foreground">Sem mudanças de estado.</p>
            ) : (
              <ul className="space-y-1 text-sm">
                {activity.state_history.map((h, i) => (
                  <li key={i} className="flex gap-2 items-start">
                    <span className="text-xs text-muted-foreground w-32">{fmtDate(h.created_at)}</span>
                    <span>
                      <strong>{h.author}</strong>: <em>{STATE_LABELS[h.from] || "—"} → {STATE_LABELS[h.to]}</em>
                      {h.note ? <> — <span className="text-muted-foreground">{h.note}</span></> : null}
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </section>

          <section>
            <h3 className="font-medium text-sm text-muted-foreground mb-2">Notas internas</h3>
            {(activity.internal_notes || []).length === 0 ? (
              <p className="text-xs text-muted-foreground">Sem notas.</p>
            ) : (
              <ul className="space-y-2 text-sm">
                {activity.internal_notes.map((n, i) => (
                  <li key={i} className="border-l-2 border-primary/40 pl-2">
                    <div className="text-xs text-muted-foreground">{n.author} · {fmtDate(n.created_at)}</div>
                    <div>{n.text}</div>
                  </li>
                ))}
              </ul>
            )}
            <div className="mt-2 flex gap-2">
              <input
                data-testid="note-input"
                value={note}
                onChange={(e) => setNote(e.target.value)}
                placeholder="Adicionar nota interna…"
                className="flex-1 px-3 py-1.5 rounded border bg-background text-sm"
              />
              <button
                data-testid="add-note-btn"
                onClick={addNote}
                disabled={sending || !note.trim()}
                className="px-3 py-1.5 rounded border bg-primary text-primary-foreground text-sm disabled:opacity-40"
              >Adicionar</button>
            </div>
          </section>
        </div>
      </div>
    </div>
  );
}
