import { useEffect, useState } from "react";
import { TrendingUp, Loader2, Clock, ShoppingCart, Info } from "lucide-react";
import { api } from "@/lib/api";
import { CostForecast, PurchaseDeliveries } from "./CostForecast";
import { toast } from "sonner";

const eur = (n) => (n == null ? "—" : (Number(n) || 0).toLocaleString("fr-FR", { minimumFractionDigits: 2, maximumFractionDigits: 2 }) + " €");

export function ChantierCostsPanel({ chantierId }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [showAffect, setShowAffect] = useState(false);

  const load = () => {
    setLoading(true);
    api.get(`/chantiers/${chantierId}/costs`)
      .then(({ data }) => { setData(data); setError(""); }).catch(() => setError("Coûts indisponibles. Réessayez ou vérifiez vos droits.")).finally(() => setLoading(false));
  };
  useEffect(() => { load(); /* eslint-disable-next-line */ }, [chantierId]);

  const assign = async (type, id, lot) => {
    const path = type === "labor" ? `/chantiers/${chantierId}/costs/labor/${id}` : `/chantiers/${chantierId}/costs/purchase/${id}`;
    try { await api.patch(path, { lot: lot || null }); load(); }
    catch { toast.error("Affectation impossible"); }
  };

  if (loading && !data) return <section className="surface p-4" data-testid="chantier-costs"><p className="text-sm text-muted-foreground flex items-center gap-2"><Loader2 className="h-4 w-4 animate-spin" /> Calcul des coûts…</p></section>;
  if (!data) return <section className="surface p-4" role="alert">{error} <button className="underline" onClick={load}>Réessayer</button></section>;
  const { totals, budget_by_lot = [], labor, purchases, scope, notes = [], lots = [], labor_entries = [], purchase_entries = [], unaffected = {} } = data;

  return (
    <section className="surface min-w-0" data-testid="chantier-costs">
      <div className="flex flex-wrap items-center gap-2 px-4 py-3 border-b border-border">
        <TrendingUp className="h-4 w-4 text-primary" />
        <p className="font-display font-bold text-sm">Coûts & marge</p>
        <span className="text-[11px] text-muted-foreground">
          {scope.using_signed_only ? `${scope.signed} devis signé(s)` : `${scope.quotes} devis lié(s)`}
        </span>

      </div>

      <div className="p-4 grid grid-cols-1 min-w-0 gap-4">
        {error && <p role="alert" className="text-sm text-destructive">{error} <button className="underline" onClick={load}>Réessayer</button></p>}
        <CostForecast chantierId={chantierId} data={data} onSaved={setData} onReload={load} />
        {/* Synthèse */}
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
          {[["Vente HT (budget)", eur(totals.vente_ht), ""],
            ["Coût prévisionnel", eur(totals.cost_prev_ht), totals.coverage.complete ? "" : "partiel"],
            ["Marge prévisionnelle", eur(totals.margin_ht), totals.margin_pct != null ? `${totals.margin_pct}%` : "non vérifiable"],
            ["Coûts enregistrés connus", eur(data.real_cost_known_ht), ""]].map(([lbl, val, sub], i) => (
            <div key={i} className="rounded-sm border border-border/60 bg-secondary/20 px-3 py-2">
              <p className="text-[10px] uppercase tracking-wide text-muted-foreground">{lbl}</p>
              <p className="text-sm font-bold num">{val}</p>
              {sub && <p className="text-[10px] text-muted-foreground">{sub}</p>}
            </div>
          ))}
        </div>

        {/* Marge prévisionnelle par lot */}
        {budget_by_lot.length > 0 && (
          <div className="overflow-x-auto">
            <table className="w-full text-sm" data-testid="chantier-costs-lots">
              <thead>
                <tr className="text-[10px] uppercase tracking-wide text-muted-foreground border-b border-border">
                  <th className="text-left py-1.5">Lot</th>
                  <th className="text-right">Vente HT</th>
                  <th className="text-right">Coût prév.</th>
                  <th className="text-right">Engagé connu</th>
                  <th className="text-right">Marge</th>
                  <th className="text-right">% vente</th>
                </tr>
              </thead>
              <tbody>
                {budget_by_lot.map((l) => (
                  <tr key={l.lot} className="border-b border-border/40" data-testid={`chantier-costs-lot-${l.lot}`}>
                    <td className="py-1.5 font-medium">{l.lot}
                      {!l.coverage.complete && <span className="ml-1 text-[10px] text-amber-600">({l.coverage.known}/{l.coverage.total} chiffrés)</span>}
                    </td>
                    <td className="text-right num">{eur(l.vente_ht)}</td>
                    <td className="text-right num">{eur(l.cost_prev_ht)}</td>
                    <td className="text-right num" title={`${l.real_hours || 0} h · achats ${eur(l.real_purchases_ht)}`}>{eur(l.real_cost_ht)}</td>
                    <td className={`text-right num font-semibold ${l.margin_ht != null && l.margin_ht < 0 ? "text-red-600" : ""}`}>{eur(l.margin_ht)}</td>
                    <td className="text-right num">{l.margin_pct != null ? `${l.margin_pct}%` : "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {/* Réel : heures + achats */}
        <div className="grid sm:grid-cols-2 gap-2">
          <div className="rounded-sm border border-border/60 px-3 py-2 flex items-center gap-2" data-testid="chantier-costs-labor">
            <Clock className="h-4 w-4 text-primary shrink-0" />
            <div className="min-w-0">
              <p className="text-sm font-medium">{labor.hours_validated} h pointées</p>
              <p className="text-[11px] text-muted-foreground">
                {labor.cost_est != null ? `≈ ${eur(labor.cost_est)} de main d'œuvre (${labor.rate_used} €/h)` : "coût MO non chiffré (définir un taux)"}
                {labor.hours_total > labor.hours_validated ? ` · ${labor.hours_total - labor.hours_validated} h en attente` : ""}
              </p>
            </div>
          </div>
          <div className="rounded-sm border border-border/60 px-3 py-2 flex items-center gap-2" data-testid="chantier-costs-purchases">
            <ShoppingCart className="h-4 w-4 text-primary shrink-0" />
            <div className="min-w-0">
              <p className="text-sm font-medium">{purchases.orders} commande(s) · {purchases.items} article(s)</p>
              <p className="text-[11px] text-muted-foreground">
                {purchases.priced_total != null ? `≈ ${eur(purchases.priced_total)} d'achats chiffrés` : "achats non chiffrés"}
                {purchases.unpriced_items ? ` · ${purchases.unpriced_items} sans prix` : ""}
              </p>
            </div>
          </div>
        </div>

        {(labor_entries.length > 0 || purchase_entries.length > 0) && (
          <div className="rounded-sm border border-border/60" data-testid="chantier-costs-affectation">
            <button type="button" onClick={() => setShowAffect((s) => !s)} className="w-full flex items-center gap-2 px-3 py-2 text-sm font-medium hover:bg-secondary/30" data-testid="chantier-costs-affect-toggle">
              <span>Affectation aux lots</span>
              {(unaffected.labor_hours > 0 || unaffected.purchases_ht) ? (
                <span className="text-[10px] rounded-full bg-amber-100 text-amber-700 px-2 py-0.5">à affecter</span>
              ) : null}
              <span className="ms-auto text-xs text-muted-foreground">{showAffect ? "masquer" : "afficher"}</span>
            </button>
            {showAffect && (
              <div className="px-3 pb-3 grid gap-3">
                {labor_entries.length > 0 && (
                  <div>
                    <p className="text-[11px] font-semibold text-muted-foreground mb-1">Heures pointées</p>
                    <div className="grid gap-1">
                      {labor_entries.map((e) => (
                        <div key={e.entry_id} className="flex items-center gap-2 text-xs" data-testid={`labor-entry-${e.entry_id}`}>
                          <span className="flex-1 truncate">{e.date} · {e.worker_name} · {e.hours} h {e.status !== "validated" && <em className="text-amber-600">(non validé)</em>}</span>
                          <select value={e.lot || ""} onChange={(ev) => assign("labor", e.entry_id, ev.target.value)}
                                  className="rounded-sm border border-input bg-background px-2 h-7 text-xs max-w-[160px]" data-testid={`labor-lot-${e.entry_id}`}>
                            <option value="">— non affecté —</option>
                            {lots.map((lo) => <option key={lo} value={lo}>{lo}</option>)}
                          </select>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
                {purchase_entries.length > 0 && (
                  <div>
                    <p className="text-[11px] font-semibold text-muted-foreground mb-1">Commandes d'achat</p>
                    <div className="grid gap-1">
                      {purchase_entries.map((e) => (
                        <div key={e.order_id} className="flex items-center gap-2 text-xs" data-testid={`purchase-entry-${e.order_id}`}>
                          <span className="flex-1 truncate">{e.supplier} · {e.items} article(s) {e.amount != null ? `· ${eur(e.amount)}` : "· non chiffré"}</span>
                          <select value={e.lot || ""} onChange={(ev) => assign("purchase", e.order_id, ev.target.value)}
                                  className="rounded-sm border border-input bg-background px-2 h-7 text-xs max-w-[160px]" data-testid={`purchase-lot-${e.order_id}`}>
                            <option value="">— non affecté —</option>
                            {lots.map((lo) => <option key={lo} value={lo}>{lo}</option>)}
                          </select>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
                {(unaffected.labor_hours > 0 || unaffected.purchases_ht) && (
                  <p className="text-[11px] text-amber-700">Non affecté : {unaffected.labor_hours || 0} h{unaffected.labor_cost != null ? ` (${eur(unaffected.labor_cost)})` : ""}{unaffected.purchases_ht ? ` · achats ${eur(unaffected.purchases_ht)}` : ""}.</p>
                )}
              </div>
            )}
          </div>
        )}

        <PurchaseDeliveries chantierId={chantierId} orders={purchase_entries} onSaved={load} />
        {notes.length > 0 && (
          <div className="rounded-sm bg-sky-50 border border-sky-200 px-3 py-2" data-testid="chantier-costs-notes">
            {notes.map((n, i) => (
              <p key={i} className="text-xs text-sky-800 flex items-start gap-1.5"><Info className="h-3.5 w-3.5 mt-0.5 shrink-0" /> {n}</p>
            ))}
          </div>
        )}
      </div>
    </section>
  );
}
