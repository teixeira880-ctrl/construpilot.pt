import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "@/lib/api";
import { toast } from "sonner";
import { Loader2, Trash2, FileText, Users, ExternalLink } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useConfirm } from "@/components/ConfirmProvider";

const eur = (n) => Math.round(Number(n) || 0).toLocaleString("pt-PT") + " €";

export default function DataManagementPanel() {
  const [clients, setClients] = useState([]);
  const [quotes, setQuotes] = useState([]);
  const [loading, setLoading] = useState(true);
  const nav = useNavigate();
  const confirm = useConfirm();

  const load = async () => {
    setLoading(true);
    try {
      const [c, d] = await Promise.all([
        api.get("/clients"),
        api.get("/documents?doc_type=quote"),
      ]);
      setClients(c.data.clients || []);
      setQuotes(d.data.documents || []);
    } catch { /* noop */ } finally { setLoading(false); }
  };
  useEffect(() => { load(); }, []);

  const delClient = async (cl) => {
    if (!(await confirm({
      title: "Eliminar este cliente?",
      description: `${cl.company || cl.name || "Este cliente"} será eliminado. Impossível se tiver orçamentos/faturas associados.`,
      confirmLabel: "Eliminar",
    }))) return;
    try {
      await api.delete(`/clients/${cl.client_id}`);
      setClients((xs) => xs.filter((x) => x.client_id !== cl.client_id));
      toast.success("Cliente eliminado");
    } catch (e) { toast.error(e?.response?.data?.detail || "Não foi possível eliminar"); }
  };
  const delQuote = async (q) => {
    if (!(await confirm({
      title: "Eliminar este orçamento?",
      description: `O orçamento ${q.number || ""} será eliminado definitivamente.`,
      confirmLabel: "Eliminar",
    }))) return;
    try {
      await api.delete(`/documents/${q.doc_id}`);
      setQuotes((xs) => xs.filter((x) => x.doc_id !== q.doc_id));
      toast.success("Orçamento eliminado");
    } catch (e) { toast.error(e?.response?.data?.detail || "Não foi possível eliminar"); }
  };

  return (
    <div className="surface rounded-md p-5" data-testid="entreprise-data-management">
      <div className="flex items-center justify-between mb-4">
        <div>
          <p className="overline">Gestão de dados</p>
          <p className="text-sm text-muted-foreground mt-1">Elimine os orçamentos e clientes guardados.</p>
        </div>
      </div>
      {loading ? (
        <div className="h-24 grid place-items-center"><Loader2 className="h-5 w-5 animate-spin text-primary" /></div>
      ) : (
        <div className="grid md:grid-cols-2 gap-6">
          {/* Devis */}
          <div>
            <p className="text-sm font-semibold flex items-center gap-2 mb-2">
              <FileText className="h-4 w-4 text-primary" /> Orçamentos ({quotes.length})
            </p>
            <div className="space-y-1 max-h-64 overflow-auto">
              {quotes.length === 0 && <p className="text-xs text-muted-foreground">Nenhum orçamento.</p>}
              {quotes.map((q) => (
                <div key={q.doc_id} className="flex items-center gap-2 border border-border rounded-sm px-2 py-1.5"
                     data-testid={`mgmt-quote-${q.doc_id}`}>
                  <button onClick={() => nav(`/devis-editeur/${q.doc_id}`)} className="min-w-0 flex-1 text-left">
                    <p className="text-xs font-medium truncate">{q.number || "Rascunho"} · {eur(q.totals?.ttc)}</p>
                    <p className="text-[10px] text-muted-foreground truncate">{q.client_name || q.client?.name || "—"} · {q.status || "draft"}</p>
                  </button>
                  <button onClick={() => delQuote(q)} className="text-muted-foreground hover:text-red-600 shrink-0"
                          data-testid={`mgmt-quote-del-${q.doc_id}`}><Trash2 className="h-4 w-4" /></button>
                </div>
              ))}
            </div>
          </div>
          {/* Clients */}
          <div>
            <div className="flex items-center justify-between mb-2">
              <p className="text-sm font-semibold flex items-center gap-2">
                <Users className="h-4 w-4 text-primary" /> Clientes ({clients.length})
              </p>
              <button onClick={() => nav("/clients")} className="text-xs text-primary inline-flex items-center gap-1">
                Gerir <ExternalLink className="h-3 w-3" />
              </button>
            </div>
            <div className="space-y-1 max-h-64 overflow-auto">
              {clients.length === 0 && <p className="text-xs text-muted-foreground">Nenhum cliente.</p>}
              {clients.map((c) => (
                <div key={c.client_id} className="flex items-center gap-2 border border-border rounded-sm px-2 py-1.5"
                     data-testid={`mgmt-client-${c.client_id}`}>
                  <button onClick={() => nav(`/clients/${c.client_id}`)} className="min-w-0 flex-1 text-left">
                    <p className="text-xs font-medium truncate">{c.company || `${c.first_name || ""} ${c.last_name || ""}`.trim() || "Cliente"}</p>
                    <p className="text-[10px] text-muted-foreground truncate">{c.email || c.phone || "—"}</p>
                  </button>
                  <button onClick={() => delClient(c)} className="text-muted-foreground hover:text-red-600 shrink-0"
                          data-testid={`mgmt-client-del-${c.client_id}`}><Trash2 className="h-4 w-4" /></button>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
