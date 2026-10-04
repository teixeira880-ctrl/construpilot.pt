import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { motion } from "framer-motion";
import {
  Network, PlugZap, Unplug, Inbox, Check, X, Loader2, RefreshCw,
  ShieldCheck, Building2, ArrowLeft, Info, FileText, GitCompareArrows, AlertTriangle, Unlink,
  Wallet, HardHat, CalendarClock, TrendingDown, TrendingUp,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter,
} from "@/components/ui/dialog";
import { SectionTitle } from "@/components/Bits";
import { api, eur } from "@/lib/api";
import { toast } from "sonner";

const STATUS_CFG = {
  received: { label: "Reçue", cls: "bg-blue-500/15 text-blue-600 dark:text-blue-400" },
  accepted: { label: "Aceite", cls: "bg-emerald-500/15 text-emerald-600 dark:text-emerald-400" },
  refused: { label: "Recusada", cls: "bg-red-500/15 text-red-600 dark:text-red-400" },
};

const StatusPill = ({ s }) => {
  const cfg = STATUS_CFG[s] || STATUS_CFG.received;
  return <span className={`px-2.5 py-1 rounded-sm text-[11px] font-semibold uppercase tracking-wide ${cfg.cls}`} data-testid={`einv-status-${s}`}>{cfg.label}</span>;
};

export default function EInvoicing() {
  const nav = useNavigate();
  const [status, setStatus] = useState(null);
  const [inbox, setInbox] = useState([]);
  const [loading, setLoading] = useState(true);
  const [siret, setSiret] = useState("");
  const [platform, setPlatform] = useState("Iopole");
  const [busy, setBusy] = useState(false);
  const [simBusy, setSimBusy] = useState(false);
  const [decideOn, setDecideOn] = useState(null); // {inv, decision}
  const [reason, setReason] = useState("");
  const [decideBusy, setDecideBusy] = useState(false);
  const [orders, setOrders] = useState([]);
  const [reconOn, setReconOn] = useState(null); // invoice being reconciled
  const [reconOrderId, setReconOrderId] = useState("");
  const [reconExpected, setReconExpected] = useState("");
  const [reconBusy, setReconBusy] = useState(false);
  const [threshold, setThreshold] = useState(5);
  const [savingThreshold, setSavingThreshold] = useState(false);
  const [projects, setProjects] = useState([]);
  const [decisionProject, setDecisionProject] = useState("");
  const [expenseOn, setExpenseOn] = useState(null); // invoice for standalone expense dialog
  const [expenseProject, setExpenseProject] = useState("");
  const [expenseBusy, setExpenseBusy] = useState(false);
  const [monthly, setMonthly] = useState(null);
  const [monthlyOpen, setMonthlyOpen] = useState(false);

  const loadStatus = async () => {
    try {
      const { data } = await api.get("/einvoicing/status");
      setStatus(data);
      if (data?.overspend_threshold_pct != null) setThreshold(data.overspend_threshold_pct);
      return data;
    } catch { return null; }
  };
  const loadInbox = async () => {
    try {
      const { data } = await api.get("/einvoicing/inbox");
      setInbox(data.invoices || []);
    } catch { /* noop */ }
  };
  const loadOrders = async () => {
    try {
      const { data } = await api.get("/einvoicing/orders");
      setOrders(data.orders || []);
    } catch { /* noop */ }
  };
  const loadProjects = async () => {
    try {
      const { data } = await api.get("/einvoicing/projects");
      setProjects(data.projects || []);
    } catch { /* noop */ }
  };
  const loadAll = async () => {
    setLoading(true);
    const st = await loadStatus();
    if (st?.connected) { await loadInbox(); await loadOrders(); await loadProjects(); }
    setLoading(false);
  };
  useEffect(() => { loadAll(); }, []); // eslint-disable-line

  const connect = async () => {
    setBusy(true);
    try {
      await api.post("/einvoicing/connect", { siret, platform });
      toast.success("Plateforme connectée (mode simulé)");
      await loadAll();
    } catch (e) { toast.error(e?.response?.data?.detail || "Ligação impossível"); }
    finally { setBusy(false); }
  };
  const disconnect = async () => {
    setBusy(true);
    try {
      await api.post("/einvoicing/disconnect");
      toast.success("Plateforme déconnectée");
      setInbox([]);
      await loadStatus();
    } catch { toast.error("Encerramento de sessão impossível"); }
    finally { setBusy(false); }
  };
  const simulate = async () => {
    setSimBusy(true);
    try {
      const { data } = await api.post("/einvoicing/inbox/simulate");
      toast.success(`Nova fatura recebida · ${data.invoice.supplier}`);
      await loadInbox();
    } catch (e) { toast.error(e?.response?.data?.detail || "Simulation impossível"); }
    finally { setSimBusy(false); }
  };
  const submitDecision = async () => {
    if (!decideOn) return;
    setDecideBusy(true);
    try {
      const { data } = await api.post(`/einvoicing/inbox/${decideOn.inv.inv_id}/decision`, {
        decision: decideOn.decision, reason,
        project_id: decideOn.decision === "accepted" && decisionProject ? decisionProject : null,
      });
      if (data?.expense) {
        toast.success(`Fatura aceite · despesa de ${eur(data.expense.amount)} adicionada à obra ${data.expense.project_name}`);
      } else {
        toast.success(decideOn.decision === "accepted" ? "Fatura acceptée (transmise à l'administration — simulé)" : "Fatura refusée (transmise à l'administration — simulé)");
      }
      setDecideOn(null); setReason(""); setDecisionProject("");
      await loadInbox();
    } catch (e) { toast.error(e?.response?.data?.detail || "Décision impossível"); }
    finally { setDecideBusy(false); }
  };
  const submitExpense = async () => {
    if (!expenseOn || !expenseProject) return;
    setExpenseBusy(true);
    try {
      const { data } = await api.post(`/einvoicing/inbox/${expenseOn.inv_id}/expense`, { project_id: expenseProject });
      toast.success(`Despesa de ${eur(data.expense.amount)} adicionada à obra ${data.expense.project_name}`);
      setExpenseOn(null); setExpenseProject("");
      await loadInbox();
    } catch (e) { toast.error(e?.response?.data?.detail || "Action impossível"); }
    finally { setExpenseBusy(false); }
  };
  const removeExpense = async (inv) => {
    try {
      await api.post(`/einvoicing/inbox/${inv.inv_id}/expense/remove`);
      toast.success("Despesa removida da obra");
      await loadInbox();
    } catch { toast.error("Action impossível"); }
  };
  const openMonthly = async () => {
    try {
      const { data } = await api.post("/einvoicing/reports/monthly/preview");
      setMonthly(data); setMonthlyOpen(true);
    } catch { toast.error("Pré-visualização indisponível"); }
  };

  const openReconcile = (inv) => {
    setReconOn(inv);
    setReconOrderId(inv.reconciliation?.order_id || "");
    setReconExpected(inv.reconciliation?.expected_ht != null ? String(inv.reconciliation.expected_ht) : "");
  };
  const onPickOrder = (oid) => {
    setReconOrderId(oid);
    const o = orders.find((x) => x.order_id === oid);
    if (o && o.est_ht > 0 && !reconExpected) setReconExpected(String(o.est_ht));
  };
  const submitReconcile = async () => {
    if (!reconOn || !reconOrderId) return;
    setReconBusy(true);
    try {
      const { data } = await api.post(`/einvoicing/inbox/${reconOn.inv_id}/reconcile`, {
        order_id: reconOrderId,
        expected_ht: reconExpected === "" ? null : Number(reconExpected),
      });
      if (data?.alert?.overspend) {
        toast.warning(`Surcoût detetado : +${data.alert.gap_pct}% au-dessus du nota de encomenda (seuil ${data.alert.threshold_pct}%). Vous avez été alerté par e-mail.`);
      } else {
        toast.success("Fatura reconciliada com a nota de encomenda");
      }
      setReconOn(null); setReconOrderId(""); setReconExpected("");
      await loadInbox();
    } catch (e) { toast.error(e?.response?.data?.detail || "Rapprochement impossível"); }
    finally { setReconBusy(false); }
  };
  const removeReconcile = async (inv) => {
    try {
      await api.post(`/einvoicing/inbox/${inv.inv_id}/unreconcile`);
      toast.success("Rapprochement removido");
      await loadInbox();
    } catch { toast.error("Action impossível"); }
  };
  const saveThreshold = async () => {
    setSavingThreshold(true);
    try {
      await api.post("/einvoicing/settings", { overspend_threshold_pct: Number(threshold) });
      toast.success(`Seuil d'alerte surcoût réglé à ${threshold}%`);
    } catch { toast.error("Não foi possível guardar"); }
    finally { setSavingThreshold(false); }
  };

  const pending = inbox.filter((i) => i.status === "received");
  const treated = inbox.filter((i) => i.status !== "received");

  return (
    <div className="max-w-5xl mx-auto px-4 py-10" data-testid="einvoicing-page">
      <button onClick={() => nav("/factures")} className="inline-flex items-center gap-1.5 text-sm text-muted-foreground hover:text-primary transition-colors mb-4" data-testid="einv-back-btn">
        <ArrowLeft className="h-4 w-4" /> Voltar aux factures
      </button>

      <div className="flex flex-wrap items-end justify-between gap-4 mb-6">
        <SectionTitle over="Rede national · PDP" title="Faturação eletrónica" />
        <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-sm text-[11px] font-semibold bg-amber-500/15 text-amber-600 dark:text-amber-400" data-testid="einv-mock-badge">
          <Info className="h-3.5 w-3.5" /> Mode simulé (démo)
        </span>
      </div>

      <div className="surface rounded-sm p-4 mb-6 flex items-start gap-3 border-amber-500/20 bg-amber-500/[0.04]" data-testid="einv-info-banner">
        <Info className="h-5 w-5 text-amber-500 shrink-0 mt-0.5" />
        <p className="text-sm text-muted-foreground">
          À partir de 2026, les entreprises reçoivent leurs factures fournisseurs via une <b className="text-foreground">Plateforme Agréée (PDP)</b> raccordée au rede national. Cet espace simule ce raccordement (receção, acceptation/rejeição, transmission du statut à l'administração). Nenhuma ligação real n'est établie — pronto à brancher l'API PDP (Iopole n°0018) dès que disponível.
        </p>
      </div>

      {loading ? (
        <div className="flex items-center gap-2 text-muted-foreground py-16 justify-center"><Loader2 className="h-5 w-5 animate-spin" /> Chargement…</div>
      ) : !status?.connected ? (
        <div className="surface rounded-sm p-8 max-w-lg mx-auto" data-testid="einv-connect-card">
          <div className="h-12 w-12 rounded-xl bg-primary/10 grid place-items-center mb-4"><Network className="h-6 w-6 text-primary" /></div>
          <h2 className="font-display text-xl font-bold">Raccorder ma plateforme</h2>
          <p className="text-sm text-muted-foreground mt-2 mb-5">Renseignez le SIRET de votre entreprise et la plateforme agréée qui vous représente.</p>
          <div className="space-y-3">
            <div>
              <label className="text-xs font-semibold text-muted-foreground">SIRET (14 chiffres)</label>
              <Input value={siret} onChange={(e) => setSiret(e.target.value)} placeholder="542 109 227 00018" className="rounded-sm mt-1 num" data-testid="einv-siret-input" />
            </div>
            <div>
              <label className="text-xs font-semibold text-muted-foreground">Plateforme (PDP)</label>
              <Input value={platform} onChange={(e) => setPlatform(e.target.value)} placeholder="Iopole" className="rounded-sm mt-1" data-testid="einv-platform-input" />
            </div>
            <Button className="rounded-sm gap-2 w-full" disabled={busy || siret.replace(/\D/g, "").length !== 14} onClick={connect} data-testid="einv-connect-btn">
              {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <PlugZap className="h-4 w-4" />} Connecter (simulé)
            </Button>
          </div>
        </div>
      ) : (
        <>
          <div className="surface rounded-sm p-4 mb-6 flex flex-wrap items-center gap-4" data-testid="einv-connected-bar">
            <div className="h-10 w-10 rounded-lg bg-emerald-500/10 grid place-items-center"><ShieldCheck className="h-5 w-5 text-emerald-500" /></div>
            <div>
              <p className="font-semibold text-sm flex items-center gap-2"><Building2 className="h-4 w-4 text-muted-foreground" /> Raccordé à <b>{status.platform}</b></p>
              <p className="text-xs text-muted-foreground num">SIRET {status.siret}</p>
            </div>
            <div className="flex items-center gap-2 sm:ml-4" data-testid="einv-threshold-control">
              <AlertTriangle className="h-4 w-4 text-amber-500" />
              <label className="text-xs text-muted-foreground">Alerte surcoût &gt;</label>
              <Input type="number" value={threshold} onChange={(e) => setThreshold(e.target.value)} className="rounded-sm h-8 w-16 num text-center" data-testid="einv-threshold-input" />
              <span className="text-xs text-muted-foreground">%</span>
              <Button size="sm" variant="outline" className="rounded-sm h-8" disabled={savingThreshold} onClick={saveThreshold} data-testid="einv-threshold-save">
                {savingThreshold ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : "OK"}
              </Button>
            </div>
            <div className="ml-auto flex gap-2">
              <Button size="sm" variant="outline" className="rounded-sm gap-1.5" onClick={openMonthly} data-testid="einv-monthly-btn">
                <CalendarClock className="h-4 w-4" /> Résumé du mois
              </Button>
              <Button variant="outline" size="sm" className="rounded-sm gap-1.5" disabled={simBusy} onClick={simulate} data-testid="einv-simulate-btn">
                {simBusy ? <Loader2 className="h-4 w-4 animate-spin" /> : <RefreshCw className="h-4 w-4" />} Simuler une receção
              </Button>
              <Button variant="ghost" size="sm" className="rounded-sm gap-1.5 text-muted-foreground" disabled={busy} onClick={disconnect} data-testid="einv-disconnect-btn">
                <Unplug className="h-4 w-4" /> Déconnecter
              </Button>
            </div>
          </div>

          <div className="grid grid-cols-3 gap-3 mb-6">
            <div className="surface p-4 rounded-sm"><p className="num text-2xl font-extrabold">{inbox.length}</p><p className="text-xs text-muted-foreground mt-1">Faturas reçues</p></div>
            <div className="surface p-4 rounded-sm border-blue-500/20"><p className="num text-2xl font-extrabold text-blue-600 dark:text-blue-400">{pending.length}</p><p className="text-xs text-muted-foreground mt-1">À traiter</p></div>
            <div className="surface p-4 rounded-sm border-emerald-500/20"><p className="num text-2xl font-extrabold text-emerald-600 dark:text-emerald-400">{treated.length}</p><p className="text-xs text-muted-foreground mt-1">Traitées</p></div>
          </div>

          <div className="flex items-center gap-2 mb-3"><Inbox className="h-4 w-4 text-primary" /><h3 className="font-display font-bold">Boîte de receção fournisseurs</h3></div>

          {inbox.length === 0 ? (
            <div className="surface rounded-sm p-12 text-center" data-testid="einv-empty">
              <FileText className="h-10 w-10 mx-auto text-muted-foreground/50" />
              <p className="mt-4 font-semibold">Nenhuma facture reçue</p>
              <p className="text-sm text-muted-foreground mt-1">Clique sur « Simuler une receção » pour recevoir une facture de démonstration.</p>
            </div>
          ) : (
            <div className="grid gap-3" data-testid="einv-inbox-list">
              {inbox.map((inv, idx) => (
                <motion.div key={inv.inv_id} initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: idx * 0.03 }}
                  className="surface rounded-sm p-4" data-testid={`einv-row-${inv.inv_id}`}>
                  <div className="flex flex-wrap items-center gap-4">
                    <div className="min-w-0 flex-1">
                      <p className="font-display font-semibold">{inv.supplier}</p>
                      <p className="text-xs text-muted-foreground num">N° {inv.number} · SIRET {inv.supplier_siret} · émise le {inv.issued_at}</p>
                      {inv.status === "refused" && inv.reason && (
                        <p className="text-xs text-red-500 mt-1">Motivo de rejeição : {inv.reason}</p>
                      )}
                    </div>
                    <StatusPill s={inv.status} />
                    <div className="text-right">
                      <p className="num text-lg font-bold text-primary">{eur(inv.amount_ttc)}</p>
                      <p className="text-[11px] text-muted-foreground num">HT {eur(inv.amount_ht)} · TVA {eur(inv.vat)}</p>
                    </div>
                    <div className="flex gap-2">
                      {inv.status === "received" && (
                        <>
                          <Button size="sm" className="rounded-sm gap-1.5 bg-emerald-600 hover:bg-emerald-700" onClick={() => { setDecideOn({ inv, decision: "accepted" }); setReason(""); }} data-testid={`einv-accept-${inv.inv_id}`}>
                            <Check className="h-4 w-4" /> Accepter
                          </Button>
                          <Button size="sm" variant="outline" className="rounded-sm gap-1.5 text-red-600 border-red-500/30 hover:bg-red-500/10" onClick={() => { setDecideOn({ inv, decision: "refused" }); setReason(""); }} data-testid={`einv-refuse-${inv.inv_id}`}>
                            <X className="h-4 w-4" /> Refuser
                          </Button>
                        </>
                      )}
                      <Button size="sm" variant="ghost" className="rounded-sm gap-1.5" onClick={() => openReconcile(inv)} data-testid={`einv-reconcile-btn-${inv.inv_id}`}>
                        <GitCompareArrows className="h-4 w-4" /> {inv.reconciliation ? "Écart" : "Rapprocher"}
                      </Button>
                      {inv.status === "accepted" && !inv.expense && (
                        <Button size="sm" variant="ghost" className="rounded-sm gap-1.5 text-primary" onClick={() => { setExpenseOn(inv); setExpenseProject(""); }} data-testid={`einv-expense-btn-${inv.inv_id}`}>
                          <HardHat className="h-4 w-4" /> Obra
                        </Button>
                      )}
                    </div>
                  </div>
                  {inv.expense && (
                    <div className="mt-3 rounded-sm p-3 flex flex-wrap items-center gap-3 text-sm border border-primary/30 bg-primary/5" data-testid={`einv-expense-${inv.inv_id}`}>
                      <Wallet className="h-4 w-4 text-primary shrink-0" />
                      <span className="text-muted-foreground">
                        Despesa de <b className="num text-foreground">{eur(inv.expense.amount)}</b> HT imputée au chantier <b className="text-foreground">{inv.expense.project_name}</b>
                      </span>
                      <Button size="sm" variant="ghost" className="rounded-sm h-7 gap-1 ml-auto text-muted-foreground" onClick={() => removeExpense(inv)} data-testid={`einv-remove-expense-${inv.inv_id}`}>
                        <Unlink className="h-3.5 w-3.5" /> Remover
                      </Button>
                    </div>
                  )}
                  {inv.reconciliation && (
                    <div className={`mt-3 rounded-sm p-3 flex flex-wrap items-center gap-3 text-sm border ${inv.reconciliation.gap_flag === "ok" ? "border-emerald-500/30 bg-emerald-500/5" : "border-amber-500/30 bg-amber-500/5"}`} data-testid={`einv-recon-${inv.inv_id}`}>
                      {inv.reconciliation.gap_flag === "ok"
                        ? <ShieldCheck className="h-4 w-4 text-emerald-500 shrink-0" />
                        : <AlertTriangle className="h-4 w-4 text-amber-500 shrink-0" />}
                      <span className="text-muted-foreground">
                        Encomenda <b className="text-foreground">{inv.reconciliation.order_type || "materiais"}</b> · prévu <b className="num text-foreground">{eur(inv.reconciliation.expected_ht)}</b> HT · facturé <b className="num text-foreground">{eur(inv.reconciliation.invoice_ht)}</b> HT
                      </span>
                      <span className={`num font-bold ${inv.reconciliation.gap_flag === "over" ? "text-red-600 dark:text-red-400" : inv.reconciliation.gap_flag === "under" ? "text-blue-600 dark:text-blue-400" : "text-emerald-600 dark:text-emerald-400"}`} data-testid={`einv-recon-gap-${inv.inv_id}`}>
                        {inv.reconciliation.gap_ht > 0 ? "+" : ""}{eur(inv.reconciliation.gap_ht)} ({inv.reconciliation.gap_pct > 0 ? "+" : ""}{inv.reconciliation.gap_pct}%)
                      </span>
                      <span className="text-[11px] uppercase font-semibold tracking-wide">
                        {inv.reconciliation.gap_flag === "ok" ? "Conforme" : inv.reconciliation.gap_flag === "over" ? "Surcoût" : "Économie"}
                      </span>
                      <Button size="sm" variant="ghost" className="rounded-sm h-7 gap-1 ml-auto text-muted-foreground" onClick={() => removeReconcile(inv)} data-testid={`einv-unreconcile-${inv.inv_id}`}>
                        <Unlink className="h-3.5 w-3.5" /> Délier
                      </Button>
                    </div>
                  )}
                </motion.div>
              ))}
            </div>
          )}
        </>
      )}

      <Dialog open={!!decideOn} onOpenChange={(o) => { if (!o) setDecideOn(null); }}>
        <DialogContent className="max-w-md" data-testid="einv-decision-dialog">
          <DialogHeader>
            <DialogTitle>{decideOn?.decision === "accepted" ? "Aceitar a fatura" : "Rejeitar a fatura"}</DialogTitle>
          </DialogHeader>
          {decideOn && (
            <div className="space-y-3">
              <p className="text-sm text-muted-foreground">
                {decideOn.inv.supplier} · {decideOn.inv.number} · <b className="text-foreground">{eur(decideOn.inv.amount_ttc)}</b> TTC
              </p>
              <div>
                <label className="text-xs font-semibold text-muted-foreground">{decideOn.decision === "refused" ? "Motivo da rejeição (obrigatório)" : "Commentaire (opcional)"}</label>
                <Textarea value={reason} onChange={(e) => setReason(e.target.value)} rows={3} className="rounded-sm mt-1" placeholder={decideOn.decision === "refused" ? "Ex.: quantidades não conformes com a guia de remessa" : ""} data-testid="einv-reason-input" />
              </div>
              {decideOn.decision === "accepted" && (
                <div>
                  <label className="text-xs font-semibold text-muted-foreground flex items-center gap-1.5"><HardHat className="h-3.5 w-3.5" /> Imputer sur un chantier (despesa auto)</label>
                  <Select value={decisionProject} onValueChange={setDecisionProject}>
                    <SelectTrigger className="rounded-sm mt-1" data-testid="einv-decision-project-select"><SelectValue placeholder="Nenhum (opcional)…" /></SelectTrigger>
                    <SelectContent>
                      {projects.length === 0 && <div className="px-3 py-2 text-sm text-muted-foreground">Nenhum chantier</div>}
                      {projects.map((p) => (
                        <SelectItem key={p.project_id} value={p.project_id} data-testid={`einv-decision-project-${p.project_id}`}>{p.name}</SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                  <p className="text-[11px] text-muted-foreground mt-1">Le montant HT sera ajouté aux dépenses du chantier pour suivre votre marge en temps réel.</p>
                </div>
              )}
              <p className="text-[11px] text-muted-foreground flex items-start gap-1.5"><Info className="h-3.5 w-3.5 mt-px shrink-0" /> Le statut sera transmis à l'administration via la plateforme (simulé).</p>
            </div>
          )}
          <DialogFooter>
            <Button variant="ghost" className="rounded-sm" onClick={() => setDecideOn(null)} data-testid="einv-decision-cancel">Cancelar</Button>
            <Button
              className={`rounded-sm gap-2 ${decideOn?.decision === "refused" ? "bg-red-600 hover:bg-red-700" : "bg-emerald-600 hover:bg-emerald-700"}`}
              disabled={decideBusy || (decideOn?.decision === "refused" && !reason.trim())}
              onClick={submitDecision} data-testid="einv-decision-confirm">
              {decideBusy ? <Loader2 className="h-4 w-4 animate-spin" /> : (decideOn?.decision === "refused" ? <X className="h-4 w-4" /> : <Check className="h-4 w-4" />)}
              {decideOn?.decision === "refused" ? "Confirmar a rejeição" : "Confirmar a aceitação"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={!!reconOn} onOpenChange={(o) => { if (!o) setReconOn(null); }}>
        <DialogContent className="max-w-md" data-testid="einv-reconcile-dialog">
          <DialogHeader>
            <DialogTitle>Rapprocher de mon nota de encomenda</DialogTitle>
          </DialogHeader>
          {reconOn && (
            <div className="space-y-3">
              <p className="text-sm text-muted-foreground">
                Fatura {reconOn.supplier} · {reconOn.number} · <b className="text-foreground num">{eur(reconOn.amount_ht)}</b> HT
              </p>
              <div>
                <label className="text-xs font-semibold text-muted-foreground">Nota de encomenda matériaux</label>
                <Select value={reconOrderId} onValueChange={onPickOrder}>
                  <SelectTrigger className="rounded-sm mt-1" data-testid="einv-recon-order-select"><SelectValue placeholder="Selecionar uma encomenda…" /></SelectTrigger>
                  <SelectContent>
                    {orders.length === 0 && <div className="px-3 py-2 text-sm text-muted-foreground">Nenhum nota de encomenda</div>}
                    {orders.map((o) => (
                      <SelectItem key={o.order_id} value={o.order_id} data-testid={`einv-recon-order-${o.order_id}`}>
                        {(o.type || "Encomenda")} · {o.item_count} ligne(s){o.est_ht > 0 ? ` · ~${eur(o.est_ht)} HT` : ""}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div>
                <label className="text-xs font-semibold text-muted-foreground">Montante encomenda estimé HT (€)</label>
                <Input type="number" value={reconExpected} onChange={(e) => setReconExpected(e.target.value)} placeholder="Ex : 1200" className="rounded-sm mt-1 num" data-testid="einv-recon-expected-input" />
                <p className="text-[11px] text-muted-foreground mt-1">Pré-rempli desde la encomenda si des prix unitaires sont connus, sinon saisissez le montant attendu.</p>
              </div>
            </div>
          )}
          <DialogFooter>
            <Button variant="ghost" className="rounded-sm" onClick={() => setReconOn(null)} data-testid="einv-recon-cancel">Cancelar</Button>
            <Button className="rounded-sm gap-2" disabled={reconBusy || !reconOrderId} onClick={submitReconcile} data-testid="einv-recon-confirm">
              {reconBusy ? <Loader2 className="h-4 w-4 animate-spin" /> : <GitCompareArrows className="h-4 w-4" />} Rapprocher
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={!!expenseOn} onOpenChange={(o) => { if (!o) setExpenseOn(null); }}>
        <DialogContent className="max-w-md" data-testid="einv-expense-dialog">
          <DialogHeader>
            <DialogTitle>Imputer la facture sur un chantier</DialogTitle>
          </DialogHeader>
          {expenseOn && (
            <div className="space-y-3">
              <p className="text-sm text-muted-foreground">
                {expenseOn.supplier} · {expenseOn.number} · <b className="text-foreground num">{eur(expenseOn.amount_ht)}</b> HT
              </p>
              <div>
                <label className="text-xs font-semibold text-muted-foreground">Obra</label>
                <Select value={expenseProject} onValueChange={setExpenseProject}>
                  <SelectTrigger className="rounded-sm mt-1" data-testid="einv-expense-project-select"><SelectValue placeholder="Selecionar uma obra…" /></SelectTrigger>
                  <SelectContent>
                    {projects.length === 0 && <div className="px-3 py-2 text-sm text-muted-foreground">Nenhum chantier</div>}
                    {projects.map((p) => (
                      <SelectItem key={p.project_id} value={p.project_id} data-testid={`einv-expense-project-${p.project_id}`}>{p.name}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                <p className="text-[11px] text-muted-foreground mt-1">Le montant HT sera ajouté aux dépenses du chantier (suivi de marge).</p>
              </div>
            </div>
          )}
          <DialogFooter>
            <Button variant="ghost" className="rounded-sm" onClick={() => setExpenseOn(null)} data-testid="einv-expense-cancel">Cancelar</Button>
            <Button className="rounded-sm gap-2" disabled={expenseBusy || !expenseProject} onClick={submitExpense} data-testid="einv-expense-confirm">
              {expenseBusy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Wallet className="h-4 w-4" />} Adicionar la despesa
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={monthlyOpen} onOpenChange={setMonthlyOpen}>
        <DialogContent className="max-w-md" data-testid="einv-monthly-dialog">
          <DialogHeader>
            <DialogTitle>Résumé fournisseurs — {monthly?.month || ""}</DialogTitle>
          </DialogHeader>
          {monthly && (
            <div className="space-y-4">
              <div className="grid grid-cols-2 gap-3">
                <div className="rounded-sm p-4 border border-red-500/30 bg-red-500/5">
                  <div className="flex items-center gap-1.5 text-red-600 dark:text-red-400"><TrendingUp className="h-4 w-4" /><span className="num text-xl font-extrabold" data-testid="einv-monthly-overspend">+{eur(monthly.overspend_total)}</span></div>
                  <p className="text-xs text-muted-foreground mt-1">Surcoûts detetados ({monthly.over_count})</p>
                </div>
                <div className="rounded-sm p-4 border border-emerald-500/30 bg-emerald-500/5">
                  <div className="flex items-center gap-1.5 text-emerald-600 dark:text-emerald-400"><TrendingDown className="h-4 w-4" /><span className="num text-xl font-extrabold" data-testid="einv-monthly-savings">{eur(monthly.savings_total)}</span></div>
                  <p className="text-xs text-muted-foreground mt-1">Économies réalisées ({monthly.under_count})</p>
                </div>
              </div>
              {monthly.over_items?.length > 0 ? (
                <div className="space-y-1.5">
                  <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wide">Principaux surcoûts</p>
                  {monthly.over_items.map((i, k) => (
                    <div key={k} className="flex items-center justify-between text-sm">
                      <span className="text-muted-foreground truncate">{i.supplier} · {i.number}</span>
                      <span className="num font-semibold text-red-600 dark:text-red-400">+{eur(i.gap_ht)} ({i.gap_pct}%)</span>
                    </div>
                  ))}
                </div>
              ) : (
                <p className="text-sm text-emerald-600 dark:text-emerald-400">Nenhum surcoût ce mois-ci 🎉</p>
              )}
              <p className="text-[11px] text-muted-foreground flex items-start gap-1.5"><Info className="h-3.5 w-3.5 mt-px shrink-0" /> Ce résumé vous est envoyé automatiquement par e-mail le 1er de chaque mois.</p>
            </div>
          )}
          <DialogFooter>
            <Button variant="outline" className="rounded-sm" onClick={() => setMonthlyOpen(false)} data-testid="einv-monthly-close">Fermer</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
