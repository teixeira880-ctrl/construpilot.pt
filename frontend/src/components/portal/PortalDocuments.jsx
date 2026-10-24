import { useEffect, useState } from "react";
import { FileText, FileCheck2, Download, Check, X, Loader2, PenLine } from "lucide-react";
import { toast } from "sonner";

const BASE = process.env.REACT_APP_BACKEND_URL;
const eur = (n) => (Number(n) || 0).toLocaleString("pt-PT", { style: "currency", currency: "EUR", maximumFractionDigits: 2 });

const STATUS = {
  sent: ["Enviado", "bg-sky-100 text-sky-700"],
  accepted: ["Aceite", "bg-emerald-100 text-emerald-700"],
  signed: ["Assinado", "bg-emerald-100 text-emerald-700"],
  refused: ["Recusado", "bg-red-100 text-red-700"],
  invoiced: ["Faturado", "bg-violet-100 text-violet-700"],
  paid: ["Paga", "bg-emerald-100 text-emerald-700"],
  overdue: ["Em atraso", "bg-red-100 text-red-700"],
};

const Badge = ({ status, accepted, declined }) => {
  let key = status;
  if (accepted && !["signed", "invoiced", "paid"].includes(status)) key = "accepted";
  if (declined) key = "refused";
  const [label, cls] = STATUS[key] || [status || "—", "bg-slate-100 text-slate-600"];
  return <span className={`text-[10px] font-bold uppercase px-2 py-0.5 rounded-full ${cls}`} data-testid="portal-doc-status">{label}</span>;
};

export function PortalDocuments({ portalApi, chantierRef, accent }) {
  const [data, setData] = useState(null);
  const [signing, setSigning] = useState(null); // doc_id being accepted
  const [declining, setDeclining] = useState(null); // doc_id being refused
  const [name, setName] = useState("");
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);

  const load = () => portalApi.get(`/${chantierRef}/documents`).then(({ data }) => setData(data)).catch(() => setData({ quotes: [], invoices: [], can_sign: false }));
  useEffect(() => { load(); /* eslint-disable-next-line */ }, [chantierRef]);

  const pdfUrl = (id) => `${BASE}/api/portal/${chantierRef}/document/${id}/pdf`;

  const accept = async (id) => {
    if (name.trim().length < 2) { toast.error("Introduza o seu nome para validar o seu acordo"); return; }
    setBusy(true);
    try {
      await portalApi.post(`/${chantierRef}/document/${id}/accept`, { signature: name.trim() });
      toast.success("Orçamento aceite — a empresa foi avisada");
      setSigning(null); setName(""); load();
    } catch (e) { toast.error(e?.response?.data?.detail || "Ação impossível"); }
    finally { setBusy(false); }
  };

  const decline = async (id) => {
    setBusy(true);
    try {
      await portalApi.post(`/${chantierRef}/document/${id}/decline`, { reason: reason.trim() });
      toast.success("Orçamento recusado — a empresa foi avisada");
      setDeclining(null); setReason(""); load();
    } catch (e) { toast.error(e?.response?.data?.detail || "Ação impossível"); }
    finally { setBusy(false); }
  };

  if (!data) return <section className="rounded-2xl border bg-white p-5" data-testid="portal-documents-loading"><p className="text-sm text-slate-500">A carregar os documentos…</p></section>;

  const { quotes = [], invoices = [], can_sign } = data;

  const DocRow = ({ d, isQuote }) => (
    <article className="py-3" data-testid={`portal-doc-${d.doc_id}`}>
      <div className="flex flex-wrap items-center gap-2">
        <FileText className="h-4 w-4 text-slate-400 shrink-0" />
        <div className="min-w-0 flex-1">
          <p className="text-sm font-medium truncate">{d.title || d.number || (isQuote ? "Orçamento" : "Fatura")}</p>
          <p className="text-xs text-slate-500">
            {d.number ? `${d.number} · ` : ""}{(d.issue_date || d.created_at || "").slice(0, 10)}
            {d.accepted_name ? ` · assinado: ${d.accepted_name}` : ""}
          </p>
        </div>
        <span className="text-sm font-semibold num" data-testid={`portal-doc-total-${d.doc_id}`}>{eur(d.total_ttc)}</span>
        <Badge status={d.status} accepted={d.accepted} declined={!!d.declined_at} />
        <a href={pdfUrl(d.doc_id)} target="_blank" rel="noreferrer"
           className="inline-flex items-center gap-1 rounded-lg border px-2.5 py-1.5 text-xs hover:bg-slate-50"
           data-testid={`portal-doc-pdf-${d.doc_id}`}><Download className="h-3.5 w-3.5" /> PDF</a>
      </div>

      {isQuote && can_sign && !d.accepted && !d.declined_at && (
        <div className="mt-2 pl-6">
          {signing === d.doc_id ? (
            <div className="rounded-lg border bg-slate-50 p-3 grid gap-2" data-testid={`portal-sign-box-${d.doc_id}`}>
              <p className="text-xs text-slate-600 flex items-center gap-1"><PenLine className="h-3.5 w-3.5" /> Aceito — introduza o seu nome para validar a sua aceitação.</p>
              <input value={name} onChange={(e) => setName(e.target.value)} placeholder="Nome e apelido"
                     className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm" data-testid={`portal-sign-name-${d.doc_id}`} autoFocus />
              <div className="flex gap-2">
                <button type="button" disabled={busy} onClick={() => accept(d.doc_id)}
                        className="inline-flex items-center gap-1 rounded-lg px-3 py-2 text-sm font-medium text-white disabled:opacity-60"
                        style={{ background: accent }} data-testid={`portal-sign-confirm-${d.doc_id}`}>
                  {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Check className="h-4 w-4" />} Validar o meu acordo
                </button>
                <button type="button" onClick={() => { setSigning(null); setName(""); }} className="text-sm text-slate-500 underline" data-testid={`portal-sign-cancel-${d.doc_id}`}>Cancelar</button>
              </div>
            </div>
          ) : declining === d.doc_id ? (
            <div className="rounded-lg border bg-slate-50 p-3 grid gap-2" data-testid={`portal-decline-box-${d.doc_id}`}>
              <p className="text-xs text-slate-600">Recusar este orçamento — motivo opcional (transmitido à empresa).</p>
              <textarea value={reason} onChange={(e) => setReason(e.target.value)} rows={2} placeholder="Ex.: orçamento, prazos, escolha de outro prestador…"
                        className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm" data-testid={`portal-decline-reason-${d.doc_id}`} />
              <div className="flex gap-2">
                <button type="button" disabled={busy} onClick={() => decline(d.doc_id)}
                        className="inline-flex items-center gap-1 rounded-lg bg-red-600 px-3 py-2 text-sm font-medium text-white disabled:opacity-60" data-testid={`portal-decline-confirm-${d.doc_id}`}>
                  {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <X className="h-4 w-4" />} Confirmar a recusa
                </button>
                <button type="button" onClick={() => { setDeclining(null); setReason(""); }} className="text-sm text-slate-500 underline" data-testid={`portal-decline-cancel-${d.doc_id}`}>Cancelar</button>
              </div>
            </div>
          ) : (
            <div className="flex gap-2">
              <button type="button" onClick={() => { setSigning(d.doc_id); setDeclining(null); }}
                      className="inline-flex items-center gap-1 rounded-lg px-3 py-1.5 text-xs font-medium text-white"
                      style={{ background: accent }} data-testid={`portal-accept-${d.doc_id}`}><Check className="h-3.5 w-3.5" /> Aceitar</button>
              <button type="button" onClick={() => { setDeclining(d.doc_id); setSigning(null); }}
                      className="inline-flex items-center gap-1 rounded-lg border px-3 py-1.5 text-xs hover:bg-slate-50" data-testid={`portal-decline-${d.doc_id}`}><X className="h-3.5 w-3.5" /> Recusar</button>
            </div>
          )}
        </div>
      )}
    </article>
  );

  return (
    <>
      <section className="rounded-2xl border bg-white p-5" data-testid="portal-quotes">
        <h2 className="font-semibold flex items-center gap-2"><FileCheck2 className="h-4 w-4" /> Orçamentos ({quotes.length})</h2>
        {quotes.length === 0 ? <p className="text-sm text-slate-500 mt-2">Nenhum orçamento partilhado por agora.</p>
          : <div className="mt-2 divide-y">{quotes.map((d) => <DocRow key={d.doc_id} d={d} isQuote />)}</div>}
      </section>
      <section className="rounded-2xl border bg-white p-5" data-testid="portal-invoices">
        <h2 className="font-semibold flex items-center gap-2"><FileText className="h-4 w-4" /> Faturas ({invoices.length})</h2>
        {invoices.length === 0 ? <p className="text-sm text-slate-500 mt-2">Nenhuma fatura partilhada por agora.</p>
          : <div className="mt-2 divide-y">{invoices.map((d) => <DocRow key={d.doc_id} d={d} isQuote={false} />)}</div>}
      </section>
    </>
  );
}
