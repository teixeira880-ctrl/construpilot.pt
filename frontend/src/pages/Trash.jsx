import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { ArchiveRestore, BellRing, DatabaseBackup, History, Loader2, Trash2 } from "lucide-react";
import { toast } from "sonner";
import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { useConfirm } from "@/components/ConfirmProvider";
import { useAuth } from "@/context/AuthContext";

const KIND = { document: "Documents", project: "Projets", client: "Clients", conversation: "Conversations", plan: "Plans" };
const STATUS = { signed: "signé", draft: "brouillon", sent: "envoyé", accepted: "accepté", refused: "refusé", paid: "payée", issued: "émise" };

function SnapshotBar({ isAdmin }) {
  const [st, setSt] = useState(null);
  const [busy, setBusy] = useState(false);
  const load = useCallback(() => api.get("/trash/snapshots/status").then((r) => setSt(r.data)).catch(() => setSt({ error: true })), []);
  useEffect(() => { load(); }, [load]);
  const run = async () => {
    setBusy(true);
    try { const { data } = await api.post("/trash/snapshots/run"); toast.success(`Sauvegarde effectuée : ${data.documents} document(s)`); load(); }
    catch (e) { toast.error(e?.response?.data?.detail || "Sauvegarde impossible"); } finally { setBusy(false); }
  };
  if (!st) return null;
  return <div className="flex flex-wrap items-center gap-2 rounded-md border bg-muted/40 px-3 py-2 text-xs mb-4" data-testid="trash-snapshot-bar">
    <DatabaseBackup className="h-4 w-4 text-primary shrink-0" />
    <span className="flex-1 min-w-[220px]">
      Sauvegarde quotidienne des devis et factures (lignes incluses, {st.retention_days} j) —
      {st.last_run ? <> dernière : <strong data-testid="trash-snapshot-last">{new Date(st.last_run).toLocaleString("fr-FR", { dateStyle: "short", timeStyle: "short" })}</strong> · {st.documents} document(s)</> : <strong data-testid="trash-snapshot-last"> aucune encore (chaque nuit à 03:00 UTC)</strong>}
    </span>
    {isAdmin && <Button size="sm" variant="outline" onClick={run} disabled={busy} data-testid="trash-snapshot-run">{busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <DatabaseBackup className="h-4 w-4" />} Sauvegarder maintenant</Button>}
  </div>;
}

export default function Trash() {
  const [data, setData] = useState(null);
  const [busy, setBusy] = useState(null);
  const confirm = useConfirm();
  const { user } = useAuth();
  const isAdmin = user?.role === "admin";
  const load = useCallback(async () => { try { const r = await api.get("/trash"); setData(r.data); } catch { toast.error("Corbeille indisponible"); } }, []);
  useEffect(() => { load(); }, [load]);
  const restore = async (i) => {
    setBusy(i.item_id);
    try {
      const { data: r } = await api.post(`/trash/${i.kind}/${i.item_id}/restore`);
      toast.success(r.restored_from?.startsWith("snapshot") ? `Restauré intégralement depuis la sauvegarde : ${i.label}` : `Restauré : ${i.label}`);
      await load();
    } catch (e) { toast.error(e?.response?.data?.detail || "Restauration impossible"); } finally { setBusy(null); }
  };
  const purge = async (i) => {
    if (!(await confirm({ title: "Supprimer définitivement ?", description: `${i.label} ne pourra plus être récupéré.`, confirmLabel: "Supprimer définitivement" }))) return;
    try { await api.delete(`/trash/${i.kind}/${i.item_id}`); toast.success("Supprimé définitivement"); await load(); } catch { toast.error("Suppression impossible"); }
  };
  const empty = async () => {
    if (!(await confirm({ title: "Vider la corbeille ?", description: `${data.count} élément(s) seront supprimés définitivement.`, confirmLabel: "Vider" }))) return;
    try { await api.delete("/trash"); toast.success("Corbeille vidée"); await load(); } catch { toast.error("Action impossible"); }
  };
  const restoreAll = async () => {
    if (!(await confirm({ title: "Tout restaurer ?", description: `Les ${data.count} élément(s) récupérables seront remis à leur place.`, confirmLabel: "Tout restaurer" }))) return;
    setBusy("restore-all");
    try { const { data: r } = await api.post("/trash/restore-all"); toast.success(`${r.restored} élément(s) restauré(s)${r.failed ? ` · ${r.failed} échec(s)` : ""}`); await load(); }
    catch { toast.error("Restauration impossible"); } finally { setBusy(null); }
  };
  const recover = async () => {
    setBusy("recover");
    try {
      const { data: r } = await api.post("/trash/recover-history");
      toast.success(r.recovered ? `${r.recovered} document(s) récupéré(s) — ${r.full} complet(s), ${r.partial} partiel(s)` : "Rien de nouveau à récupérer");
      await load();
    } catch { toast.error("Récupération impossible"); } finally { setBusy(null); }
  };
  const days = (i) => Math.max(0, Math.ceil((new Date(i.purge_after) - Date.now()) / 86400000));
  if (!data) return <div className="p-6"><Loader2 className="h-5 w-5 animate-spin" /></div>;
  const kinds = [...new Set(data.items.map((i) => i.kind))];
  return <div className="p-4 sm:p-6 max-w-5xl" data-testid="trash-page">
    <div className="flex flex-wrap items-center justify-between gap-2 mb-4">
      <div><h1 className="text-2xl font-bold flex items-center gap-2"><Trash2 className="h-6 w-6" /> Corbeille</h1>
        <p className="text-sm text-muted-foreground">Devis, factures, projets, clients, conversations et plans supprimés restent récupérables {data.retention_days} jours, puis sont effacés.</p></div>
      <div className="flex gap-2">
        <Button variant="outline" onClick={recover} disabled={busy === "recover"} data-testid="trash-recover-history">{busy === "recover" ? <Loader2 className="h-4 w-4 animate-spin" /> : <History className="h-4 w-4" />} Récupérer l'historique</Button>
        {data.count > 0 && <Button variant="outline" onClick={restoreAll} disabled={busy === "restore-all"} data-testid="trash-restore-all">{busy === "restore-all" ? <Loader2 className="h-4 w-4 animate-spin" /> : <ArchiveRestore className="h-4 w-4" />} Tout restaurer ({data.count})</Button>}
        {data.count > 0 && <Button variant="outline" onClick={empty} data-testid="trash-empty">Vider la corbeille ({data.count})</Button>}
      </div>
    </div>
    <SnapshotBar isAdmin={isAdmin} />
    <p className="text-xs text-muted-foreground mb-1">« Récupérer l'historique » reconstitue les devis et factures effacés avant la corbeille : intégralement s'ils figurent dans la sauvegarde quotidienne, sinon partiellement (intitulé, client, montant TTC, signature).</p>
    <p className="text-xs text-muted-foreground mb-3 flex items-center gap-1" data-testid="trash-alert-info"><BellRing className="h-3.5 w-3.5" /> Une notification vous prévient {data.alert_days_before_purge} jours avant l'effacement définitif d'un élément.</p>
    {data.count === 0 && <p className="text-sm text-muted-foreground" data-testid="trash-empty-state">La corbeille est vide.</p>}
    {kinds.map((k) => <section key={k} className="mb-5" data-testid={`trash-section-${k}`}>
      <h2 className="font-semibold text-base mb-1">{KIND[k] || k}</h2>
      <ul className="divide-y border rounded-md">
        {data.items.filter((i) => i.kind === k).map((i) => <li key={i.item_id} className="flex flex-wrap items-center gap-2 px-3 py-2 text-sm" data-testid={`trash-item-${i.item_id}`}>
          <div className="flex-1 min-w-[200px]">
            <div className="font-medium">{i.label}
              {i.partial && !i.full_backup && <span className="ml-2 rounded-sm px-1 text-xs bg-amber-500/15" title="Reconstitué depuis l'historique : contenu détaillé non récupérable">partiel</span>}
              {i.partial && i.full_backup && <span className="ml-2 rounded-sm px-1 text-xs bg-sky-500/15" title={`Sauvegarde complète du ${i.full_backup_day} : restauration intégrale, lignes incluses`} data-testid={`trash-full-backup-${i.item_id}`}>sauvegarde complète</span>}
              {i.recovered_from?.includes("snapshot") && !i.partial && <span className="ml-2 rounded-sm px-1 text-xs bg-sky-500/15" title={`Récupéré depuis la sauvegarde du ${i.snapshot_day}`}>depuis sauvegarde</span>}
              {i.status && <span className={`ml-2 rounded-sm px-1 text-xs ${i.status === "signed" ? "bg-emerald-500/15" : "bg-muted"}`}>{STATUS[i.status] || i.status}</span>}
              {i.message_count > 0 && <span className="ml-2 text-xs text-muted-foreground">{i.message_count} message(s)</span>}
            </div>
            <div className="text-xs text-muted-foreground">Supprimé le {new Date(i.deleted_at).toLocaleString("fr-FR", { dateStyle: "short", timeStyle: "short" })} · encore {days(i)} j{days(i) <= data.alert_days_before_purge && <span className="ml-1 text-amber-600 font-medium" data-testid={`trash-soon-${i.item_id}`}>· effacement imminent</span>}</div>
          </div>
          <Button size="sm" onClick={() => restore(i)} disabled={busy === i.item_id} data-testid={`trash-restore-${i.item_id}`}>{busy === i.item_id ? <Loader2 className="h-4 w-4 animate-spin" /> : <ArchiveRestore className="h-4 w-4" />} Restaurer</Button>
          <Button size="sm" variant="ghost" className="text-destructive" onClick={() => purge(i)} data-testid={`trash-purge-${i.item_id}`}><Trash2 className="h-4 w-4" /></Button>
        </li>)}
      </ul>
    </section>)}
    <p className="text-xs text-muted-foreground mt-6">Après restauration, l'élément réapparaît à sa place : <Link className="underline" to="/devis">Suivi devis</Link>, <Link className="underline" to="/factures">Factures</Link>, <Link className="underline" to="/clients">Clients</Link>, <Link className="underline" to="/assistant">Assistant</Link>, <Link className="underline" to="/plan">Plans</Link>.</p>
  </div>;
}
