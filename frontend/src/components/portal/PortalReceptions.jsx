import { useEffect, useState } from "react";
import { toast } from "sonner";
import { ClipboardCheck, Download, PenLine, Check, Loader2, CircleCheck, Circle } from "lucide-react";

const BASE = process.env.REACT_APP_BACKEND_URL;
const DECISIONS = { sans_reserve: "Receção sem reservas", avec_reserve: "Receção com reservas", refus: "Receção recusada" };

export function PortalReceptions({ portalApi, chantierRef, accent }) {
  const [data, setData] = useState(null);
  const [signing, setSigning] = useState(null);
  const [name, setName] = useState("");
  const [busy, setBusy] = useState(false);
  const [lifting, setLifting] = useState(null);

  const load = () => portalApi.get(`/${chantierRef}/receptions`).then(({ data }) => setData(data)).catch(() => setData({ receptions: [], can_sign: false }));
  useEffect(() => { load(); /* eslint-disable-next-line */ }, [chantierRef]);

  const sign = async (id) => {
    if (name.trim().length < 2) { toast.error("Introduza o seu nome para assinar"); return; }
    setBusy(true);
    try {
      await portalApi.post(`/${chantierRef}/reception/${id}/sign`, { signature: name.trim() });
      toast.success("Auto assinado — a empresa foi avisada");
      setSigning(null); setName(""); load();
    } catch (e) { toast.error(e?.response?.data?.detail || "Assinatura impossível"); }
    finally { setBusy(false); }
  };

  const toggleReserve = async (pvId, reserve) => {
    const resolved = !reserve.lifted_at;
    setLifting(reserve.id);
    try {
      await portalApi.post(`/${chantierRef}/reception/${pvId}/reserve/${reserve.id}/lift`, { resolved });
      toast.success(resolved ? "Reserva marcada como resolvida — a empresa foi avisada" : "Marcação anulada");
      load();
    } catch (e) { toast.error(e?.response?.data?.detail || "Ação impossível"); }
    finally { setLifting(null); }
  };

  if (!data) return <section className="rounded-2xl border bg-white p-5"><p className="text-sm text-slate-500">A carregar…</p></section>;
  const { receptions = [], can_sign } = data;

  return (
    <section className="rounded-2xl border bg-white p-5" data-testid="portal-receptions">
      <h2 className="font-semibold flex items-center gap-2"><ClipboardCheck className="h-4 w-4" /> Receção da obra ({receptions.length})</h2>
      {receptions.length === 0 ? <p className="text-sm text-slate-500 mt-2">Nenhum auto partilhado por agora.</p> : (
        <div className="mt-2 divide-y">
          {receptions.map((pv) => (
            <article key={pv.pv_id} className="py-3" data-testid={`portal-pv-${pv.pv_id}`}>
              <div className="flex flex-wrap items-center gap-2">
                <div className="min-w-0 flex-1">
                  <p className="text-sm font-medium">{pv.ref} · {DECISIONS[pv.decision] || pv.decision}</p>
                  <p className="text-xs text-slate-500">Receção {(pv.date_reception || "").slice(0, 10)} · {pv.reserve_count} reserva(s){pv.reserve_count ? ` · ${pv.reserve_lifted}/${pv.reserve_count}levantada(s)` : ""}{pv.client_signature?.name ? `· assinado:${pv.client_signature.name}` : ""}</p>
                </div>
                {pv.signed_client && <span className="text-[10px] font-bold uppercase px-2 py-0.5 rounded-full bg-emerald-100 text-emerald-700" data-testid={`portal-pv-signed-${pv.pv_id}`}>Assinado</span>}
                <a href={`${BASE}/api/portal/${chantierRef}/reception/${pv.pv_id}/pdf`} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 rounded-lg border px-2.5 py-1.5 text-xs hover:bg-slate-50" data-testid={`portal-pv-pdf-${pv.pv_id}`}><Download className="h-3.5 w-3.5" /> PDF</a>
              </div>

              {(pv.reserves || []).length > 0 && (
                <div className="mt-3 rounded-lg border bg-slate-50 p-3" data-testid={`portal-pv-reserves-${pv.pv_id}`}>
                  <p className="text-xs font-semibold text-slate-600 mb-2">Reservas — assinale as que foram resolvidas</p>
                  <ul className="grid gap-1.5">
                    {(pv.reserves || []).map((r) => {
                      const done = !!r.lifted_at;
                      return (
                        <li key={r.id} className="flex items-start gap-2" data-testid={`portal-reserve-${r.id}`}>
                          <button type="button" disabled={lifting === r.id || (pv.signed_client && done)} onClick={() => toggleReserve(pv.pv_id, r)}
                                  className="mt-0.5 shrink-0 disabled:opacity-60" title={done ? "Marcar como não resolvida" : "Marcar como resolvida"}
                                  data-testid={`portal-reserve-toggle-${r.id}`}>
                            {lifting === r.id ? <Loader2 className="h-4 w-4 animate-spin text-slate-400" />
                              : done ? <CircleCheck className="h-4 w-4" style={{ color: accent }} />
                              : <Circle className="h-4 w-4 text-slate-300" />}
                          </button>
                          <div className="min-w-0">
                            <p className={`text-xs ${done ? "line-through text-slate-400" : "text-slate-700"}`}>{r.lot ? <span className="font-medium">{r.lot} · </span> : null}{r.description}</p>
                            {done && <p className="text-[10px] text-emerald-600">Resolvida{r.lifted_by ? `— confirmado por${r.lifted_by}` : ""}</p>}
                          </div>
                        </li>
                      );
                    })}
                  </ul>
                </div>
              )}

              {can_sign && !pv.signed_client && (
                <div className="mt-2">
                  {signing === pv.pv_id ? (
                    <div className="rounded-lg border bg-slate-50 p-3 grid gap-2" data-testid={`portal-pv-sign-box-${pv.pv_id}`}>
                      <p className="text-xs text-slate-600 flex items-center gap-1"><PenLine className="h-3.5 w-3.5" /> Apto para receção — introduza o seu nome para assinar o auto.</p>
                      <input value={name} onChange={(e) => setName(e.target.value)} placeholder="Nome e apelido" className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm" autoFocus data-testid={`portal-pv-name-${pv.pv_id}`} />
                      <div className="flex gap-2">
                        <button type="button" disabled={busy} onClick={() => sign(pv.pv_id)} className="inline-flex items-center gap-1 rounded-lg px-3 py-2 text-sm font-medium text-white disabled:opacity-60" style={{ background: accent }} data-testid={`portal-pv-confirm-${pv.pv_id}`}>{busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Check className="h-4 w-4" />} Assinar o auto</button>
                        <button type="button" onClick={() => { setSigning(null); setName(""); }} className="text-sm text-slate-500 underline">Cancelar</button>
                      </div>
                    </div>
                  ) : (
                    <button type="button" onClick={() => setSigning(pv.pv_id)} className="inline-flex items-center gap-1 rounded-lg px-3 py-1.5 text-xs font-medium text-white" style={{ background: accent }} data-testid={`portal-pv-signbtn-${pv.pv_id}`}><PenLine className="h-3.5 w-3.5" /> Signer en ligne</button>
                  )}
                </div>
              )}
            </article>
          ))}
        </div>
      )}
    </section>
  );
}
