import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { motion } from "framer-motion";
import {
  Network, PlugZap, Unplug, Inbox, Check, X, Loader2, RefreshCw,
  ShieldCheck, Building2, ArrowLeft, Info, FileText,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter,
} from "@/components/ui/dialog";
import { SectionTitle } from "@/components/Bits";
import { api, eur } from "@/lib/api";
import { toast } from "sonner";

const STATUS_CFG = {
  received: { label: "Reçue", cls: "bg-blue-500/15 text-blue-600 dark:text-blue-400" },
  accepted: { label: "Acceptée", cls: "bg-emerald-500/15 text-emerald-600 dark:text-emerald-400" },
  refused: { label: "Refusée", cls: "bg-red-500/15 text-red-600 dark:text-red-400" },
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

  const loadStatus = async () => {
    try {
      const { data } = await api.get("/einvoicing/status");
      setStatus(data);
      return data;
    } catch { return null; }
  };
  const loadInbox = async () => {
    try {
      const { data } = await api.get("/einvoicing/inbox");
      setInbox(data.invoices || []);
    } catch { /* noop */ }
  };
  const loadAll = async () => {
    setLoading(true);
    const st = await loadStatus();
    if (st?.connected) await loadInbox();
    setLoading(false);
  };
  useEffect(() => { loadAll(); }, []); // eslint-disable-line

  const connect = async () => {
    setBusy(true);
    try {
      await api.post("/einvoicing/connect", { siret, platform });
      toast.success("Plateforme connectée (mode simulé)");
      await loadAll();
    } catch (e) { toast.error(e?.response?.data?.detail || "Connexion impossible"); }
    finally { setBusy(false); }
  };
  const disconnect = async () => {
    setBusy(true);
    try {
      await api.post("/einvoicing/disconnect");
      toast.success("Plateforme déconnectée");
      setInbox([]);
      await loadStatus();
    } catch { toast.error("Déconnexion impossible"); }
    finally { setBusy(false); }
  };
  const simulate = async () => {
    setSimBusy(true);
    try {
      const { data } = await api.post("/einvoicing/inbox/simulate");
      toast.success(`Nouvelle facture reçue · ${data.invoice.supplier}`);
      await loadInbox();
    } catch (e) { toast.error(e?.response?.data?.detail || "Simulation impossible"); }
    finally { setSimBusy(false); }
  };
  const submitDecision = async () => {
    if (!decideOn) return;
    setDecideBusy(true);
    try {
      await api.post(`/einvoicing/inbox/${decideOn.inv.inv_id}/decision`, {
        decision: decideOn.decision, reason,
      });
      toast.success(decideOn.decision === "accepted" ? "Facture acceptée (transmise à l'administration — simulé)" : "Facture refusée (transmise à l'administration — simulé)");
      setDecideOn(null); setReason("");
      await loadInbox();
    } catch (e) { toast.error(e?.response?.data?.detail || "Décision impossible"); }
    finally { setDecideBusy(false); }
  };

  const pending = inbox.filter((i) => i.status === "received");
  const treated = inbox.filter((i) => i.status !== "received");

  return (
    <div className="max-w-5xl mx-auto px-4 py-10" data-testid="einvoicing-page">
      <button onClick={() => nav("/factures")} className="inline-flex items-center gap-1.5 text-sm text-muted-foreground hover:text-primary transition-colors mb-4" data-testid="einv-back-btn">
        <ArrowLeft className="h-4 w-4" /> Retour aux factures
      </button>

      <div className="flex flex-wrap items-end justify-between gap-4 mb-6">
        <SectionTitle over="Réseau national · PDP" title="Facturation électronique" />
        <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-sm text-[11px] font-semibold bg-amber-500/15 text-amber-600 dark:text-amber-400" data-testid="einv-mock-badge">
          <Info className="h-3.5 w-3.5" /> Mode simulé (démo)
        </span>
      </div>

      <div className="surface rounded-sm p-4 mb-6 flex items-start gap-3 border-amber-500/20 bg-amber-500/[0.04]" data-testid="einv-info-banner">
        <Info className="h-5 w-5 text-amber-500 shrink-0 mt-0.5" />
        <p className="text-sm text-muted-foreground">
          À partir de 2026, les entreprises reçoivent leurs factures fournisseurs via une <b className="text-foreground">Plateforme Agréée (PDP)</b> raccordée au réseau national. Cet espace simule ce raccordement (réception, acceptation/refus, transmission du statut à l'administration). Aucune connexion réelle n'est établie — prêt à brancher l'API PDP (Iopole n°0018) dès que disponible.
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
            <div className="ml-auto flex gap-2">
              <Button variant="outline" size="sm" className="rounded-sm gap-1.5" disabled={simBusy} onClick={simulate} data-testid="einv-simulate-btn">
                {simBusy ? <Loader2 className="h-4 w-4 animate-spin" /> : <RefreshCw className="h-4 w-4" />} Simuler une réception
              </Button>
              <Button variant="ghost" size="sm" className="rounded-sm gap-1.5 text-muted-foreground" disabled={busy} onClick={disconnect} data-testid="einv-disconnect-btn">
                <Unplug className="h-4 w-4" /> Déconnecter
              </Button>
            </div>
          </div>

          <div className="grid grid-cols-3 gap-3 mb-6">
            <div className="surface p-4 rounded-sm"><p className="num text-2xl font-extrabold">{inbox.length}</p><p className="text-xs text-muted-foreground mt-1">Factures reçues</p></div>
            <div className="surface p-4 rounded-sm border-blue-500/20"><p className="num text-2xl font-extrabold text-blue-600 dark:text-blue-400">{pending.length}</p><p className="text-xs text-muted-foreground mt-1">À traiter</p></div>
            <div className="surface p-4 rounded-sm border-emerald-500/20"><p className="num text-2xl font-extrabold text-emerald-600 dark:text-emerald-400">{treated.length}</p><p className="text-xs text-muted-foreground mt-1">Traitées</p></div>
          </div>

          <div className="flex items-center gap-2 mb-3"><Inbox className="h-4 w-4 text-primary" /><h3 className="font-display font-bold">Boîte de réception fournisseurs</h3></div>

          {inbox.length === 0 ? (
            <div className="surface rounded-sm p-12 text-center" data-testid="einv-empty">
              <FileText className="h-10 w-10 mx-auto text-muted-foreground/50" />
              <p className="mt-4 font-semibold">Aucune facture reçue</p>
              <p className="text-sm text-muted-foreground mt-1">Cliquez sur « Simuler une réception » pour recevoir une facture de démonstration.</p>
            </div>
          ) : (
            <div className="grid gap-3" data-testid="einv-inbox-list">
              {inbox.map((inv, idx) => (
                <motion.div key={inv.inv_id} initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: idx * 0.03 }}
                  className="surface rounded-sm p-4 flex flex-wrap items-center gap-4" data-testid={`einv-row-${inv.inv_id}`}>
                  <div className="min-w-0 flex-1">
                    <p className="font-display font-semibold">{inv.supplier}</p>
                    <p className="text-xs text-muted-foreground num">N° {inv.number} · SIRET {inv.supplier_siret} · émise le {inv.issued_at}</p>
                    {inv.status === "refused" && inv.reason && (
                      <p className="text-xs text-red-500 mt-1">Motif de refus : {inv.reason}</p>
                    )}
                  </div>
                  <StatusPill s={inv.status} />
                  <div className="text-right">
                    <p className="num text-lg font-bold text-primary">{eur(inv.amount_ttc)}</p>
                    <p className="text-[11px] text-muted-foreground num">HT {eur(inv.amount_ht)} · TVA {eur(inv.vat)}</p>
                  </div>
                  {inv.status === "received" ? (
                    <div className="flex gap-2">
                      <Button size="sm" className="rounded-sm gap-1.5 bg-emerald-600 hover:bg-emerald-700" onClick={() => { setDecideOn({ inv, decision: "accepted" }); setReason(""); }} data-testid={`einv-accept-${inv.inv_id}`}>
                        <Check className="h-4 w-4" /> Accepter
                      </Button>
                      <Button size="sm" variant="outline" className="rounded-sm gap-1.5 text-red-600 border-red-500/30 hover:bg-red-500/10" onClick={() => { setDecideOn({ inv, decision: "refused" }); setReason(""); }} data-testid={`einv-refuse-${inv.inv_id}`}>
                        <X className="h-4 w-4" /> Refuser
                      </Button>
                    </div>
                  ) : (
                    <span className="text-[11px] text-muted-foreground italic" data-testid={`einv-admin-status-${inv.inv_id}`}>{inv.admin_status || "transmis (simulé)"}</span>
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
            <DialogTitle>{decideOn?.decision === "accepted" ? "Accepter la facture" : "Refuser la facture"}</DialogTitle>
          </DialogHeader>
          {decideOn && (
            <div className="space-y-3">
              <p className="text-sm text-muted-foreground">
                {decideOn.inv.supplier} · {decideOn.inv.number} · <b className="text-foreground">{eur(decideOn.inv.amount_ttc)}</b> TTC
              </p>
              <div>
                <label className="text-xs font-semibold text-muted-foreground">{decideOn.decision === "refused" ? "Motif du refus (obligatoire)" : "Commentaire (facultatif)"}</label>
                <Textarea value={reason} onChange={(e) => setReason(e.target.value)} rows={3} className="rounded-sm mt-1" placeholder={decideOn.decision === "refused" ? "Ex : quantités non conformes au bon de livraison" : ""} data-testid="einv-reason-input" />
              </div>
              <p className="text-[11px] text-muted-foreground flex items-start gap-1.5"><Info className="h-3.5 w-3.5 mt-px shrink-0" /> Le statut sera transmis à l'administration via la plateforme (simulé).</p>
            </div>
          )}
          <DialogFooter>
            <Button variant="ghost" className="rounded-sm" onClick={() => setDecideOn(null)} data-testid="einv-decision-cancel">Annuler</Button>
            <Button
              className={`rounded-sm gap-2 ${decideOn?.decision === "refused" ? "bg-red-600 hover:bg-red-700" : "bg-emerald-600 hover:bg-emerald-700"}`}
              disabled={decideBusy || (decideOn?.decision === "refused" && !reason.trim())}
              onClick={submitDecision} data-testid="einv-decision-confirm">
              {decideBusy ? <Loader2 className="h-4 w-4 animate-spin" /> : (decideOn?.decision === "refused" ? <X className="h-4 w-4" /> : <Check className="h-4 w-4" />)}
              {decideOn?.decision === "refused" ? "Confirmer le refus" : "Confirmer l'acceptation"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
