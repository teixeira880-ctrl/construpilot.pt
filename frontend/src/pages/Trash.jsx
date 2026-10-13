import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { ArchiveRestore, BellRing, DatabaseBackup, History, Loader2, Trash2 } from "lucide-react";
import { toast } from "sonner";
import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { useConfirm } from "@/components/ConfirmProvider";
import { useAuth } from "@/context/AuthContext";

const KIND = { document: "Documents", project: "Projets", client: "Clients", conversation: "Conversations", plan: "Plans" };
const STATUS = { signed: "assinado", draft: "brouillon", sent: "enviado", accepted: "aceite", refused: "recusado", paid: "paga", issued: "emitida" };

function SnapshotBar({ isAdmin }) {
  const [st, setSt] = useState(null);
  const [busy, setBusy] = useState(false);
  const load = useCallback(() => api.get("/trash/snapshots/status").then((r) => setSt(r.data)).catch(() => setSt({ error: true })), []);
  useEffect(() => { load(); }, [load]);
  const run = async () => {
    setBusy(true);
    try { const { data } = await api.post("/trash/snapshots/run"); toast.success(`Cópia de segurança efetuada:${data.documents} document(s)`); load(); }
    catch (e) { toast.error(e?.response?.data?.detail || "Não foi possível guardar"); } finally { setBusy(false); }
  };
  if (!st) return null;
  return <div className="flex flex-wrap items-center gap-2 rounded-md border bg-muted/40 px-3 py-2 text-xs mb-4" data-testid="trash-snapshot-bar">
    <DatabaseBackup className="h-4 w-4 text-primary shrink-0" />
    <span className="flex-1 min-w-[220px]">
      Cópia de segurança diária dos orçamentos e faturas (linhas incluídas, {st.retention_days} j) —
      {st.last_run ? <> última: <strong data-testid="trash-snapshot-last">{new Date(st.last_run).toLocaleString("fr-FR", { dateStyle: "short", timeStyle: "short" })}</strong> · {st.documents} document(s)</> : <strong data-testid="trash-snapshot-last"> ainda nenhuma (todas as noites às 03:00 UTC)</strong>}
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
      toast.success(r.restored_from?.startsWith("snapshot") ? `Restaurado integralmente a partir da cópia de segurança:${i.label}` : `Restaurado:${i.label}`);
      await load();
    } catch (e) { toast.error(e?.response?.data?.detail || "Restauro impossível"); } finally { setBusy(null); }
  };
  const purge = async (i) => {
    if (!(await confirm({ title: "Eliminar definitivamente?", description: `${i.label}não poderá voltar a ser recuperado.`, confirmLabel: "Eliminar definitivamente" }))) return;
    try { await api.delete(`/trash/${i.kind}/${i.item_id}`); toast.success("Eliminado definitivamente"); await load(); } catch { toast.error("Não foi possível eliminar"); }
  };
  const empty = async () => {
    if (!(await confirm({ title: "Esvaziar o lixo?", description: `${data.count}elemento(s) serão eliminados definitivamente.`, confirmLabel: "Vider" }))) return;
    try { await api.delete("/trash"); toast.success("Lixo esvaziado"); await load(); } catch { toast.error("Ação impossível"); }
  };
  const restoreAll = async () => {
    if (!(await confirm({ title: "Restaurar tudo?", description: `Les ${data.count}elemento(s) recuperáveis serão repostos no seu lugar.`, confirmLabel: "Restaurar tudo" }))) return;
    setBusy("restore-all");
    try { const { data: r } = await api.post("/trash/restore-all"); toast.success(`${r.restored}elemento(s) restaurado(s)${r.failed ? ` · ${r.failed}falha(s)` : ""}`); await load(); }
    catch { toast.error("Restauro impossível"); } finally { setBusy(null); }
  };
  const recover = async () => {
    setBusy("recover");
    try {
      const { data: r } = await api.post("/trash/recover-history");
      toast.success(r.recovered ? `${r.recovered}documento(s) recuperado(s) —${r.full} complet(s), ${r.partial} partiel(s)` : "Nada de novo a recuperar");
      await load();
    } catch { toast.error("Recuperação impossível"); } finally { setBusy(null); }
  };
  const days = (i) => Math.max(0, Math.ceil((new Date(i.purge_after) - Date.now()) / 86400000));
  if (!data) return <div className="p-6"><Loader2 className="h-5 w-5 animate-spin" /></div>;
  const kinds = [...new Set(data.items.map((i) => i.kind))];
  return <div className="p-4 sm:p-6 max-w-5xl" data-testid="trash-page">
    <div className="flex flex-wrap items-center justify-between gap-2 mb-4">
      <div><h1 className="text-2xl font-bold flex items-center gap-2"><Trash2 className="h-6 w-6" /> Corbeille</h1>
        <p className="text-sm text-muted-foreground">Orçamentos, faturas, projetos, clientes, conversas e plantas eliminados continuam recuperáveis durante {data.retention_days} dias e depois são apagados.</p></div>
      <div className="flex gap-2">
        <Button variant="outline" onClick={recover} disabled={busy === "recover"} data-testid="trash-recover-history">{busy === "recover" ? <Loader2 className="h-4 w-4 animate-spin" /> : <History className="h-4 w-4" />} Recuperar o histórico</Button>
        {data.count > 0 && <Button variant="outline" onClick={restoreAll} disabled={busy === "restore-all"} data-testid="trash-restore-all">{busy === "restore-all" ? <Loader2 className="h-4 w-4 animate-spin" /> : <ArchiveRestore className="h-4 w-4" />} Restaurar tudo ({data.count})</Button>}
        {data.count > 0 && <Button variant="outline" onClick={empty} data-testid="trash-empty">Esvaziar o lixo ({data.count})</Button>}
      </div>
    </div>
    <SnapshotBar isAdmin={isAdmin} />
    <p className="text-xs text-muted-foreground mb-1">«Recuperar o histórico» reconstitui os orçamentos e faturas apagados antes do lixo: integralmente se constarem da cópia de segurança diária, caso contrário parcialmente (designação, cliente, montante c/ IVA, assinatura).</p>
    <p className="text-xs text-muted-foreground mb-3 flex items-center gap-1" data-testid="trash-alert-info"><BellRing className="h-3.5 w-3.5" /> Uma notificação avisa-o {data.alert_days_before_purge} dias antes da eliminação definitiva de um elemento.</p>
    {data.count === 0 && <p className="text-sm text-muted-foreground" data-testid="trash-empty-state">O lixo está vazio.</p>}
    {kinds.map((k) => <section key={k} className="mb-5" data-testid={`trash-section-${k}`}>
      <h2 className="font-semibold text-base mb-1">{KIND[k] || k}</h2>
      <ul className="divide-y border rounded-md">
        {data.items.filter((i) => i.kind === k).map((i) => <li key={i.item_id} className="flex flex-wrap items-center gap-2 px-3 py-2 text-sm" data-testid={`trash-item-${i.item_id}`}>
          <div className="flex-1 min-w-[200px]">
            <div className="font-medium">{i.label}
              {i.partial && !i.full_backup && <span className="ml-2 rounded-sm px-1 text-xs bg-amber-500/15" title="Reconstituído a partir do histórico: conteúdo detalhado não recuperável">partiel</span>}
              {i.partial && i.full_backup && <span className="ml-2 rounded-sm px-1 text-xs bg-sky-500/15" title={`Cópia de segurança completa de${i.full_backup_day}: restauro integral, linhas incluídas`} data-testid={`trash-full-backup-${i.item_id}`}>cópia de segurança completa</span>}
              {i.recovered_from?.includes("snapshot") && !i.partial && <span className="ml-2 rounded-sm px-1 text-xs bg-sky-500/15" title={`Recuperado da cópia de segurança de${i.snapshot_day}`}>da cópia de segurança</span>}
              {i.status && <span className={`ml-2 rounded-sm px-1 text-xs ${i.status === "signed" ? "bg-emerald-500/15" : "bg-muted"}`}>{STATUS[i.status] || i.status}</span>}
              {i.message_count > 0 && <span className="ml-2 text-xs text-muted-foreground">{i.message_count} message(s)</span>}
            </div>
            <div className="text-xs text-muted-foreground">Eliminado em {new Date(i.deleted_at).toLocaleString("fr-FR", { dateStyle: "short", timeStyle: "short" })} · encore {days(i)} j{days(i) <= data.alert_days_before_purge && <span className="ml-1 text-amber-600 font-medium" data-testid={`trash-soon-${i.item_id}`}>· effacement imminent</span>}</div>
          </div>
          <Button size="sm" onClick={() => restore(i)} disabled={busy === i.item_id} data-testid={`trash-restore-${i.item_id}`}>{busy === i.item_id ? <Loader2 className="h-4 w-4 animate-spin" /> : <ArchiveRestore className="h-4 w-4" />} Restaurer</Button>
          <Button size="sm" variant="ghost" className="text-destructive" onClick={() => purge(i)} data-testid={`trash-purge-${i.item_id}`}><Trash2 className="h-4 w-4" /></Button>
        </li>)}
      </ul>
    </section>)}
    <p className="text-xs text-muted-foreground mt-6">Após o restauro, o elemento reaparece no seu lugar: <Link className="underline" to="/devis">Acompanhamento de orçamentos</Link>, <Link className="underline" to="/factures">Factures</Link>, <Link className="underline" to="/clients">Clients</Link>, <Link className="underline" to="/assistant">Assistant</Link>, <Link className="underline" to="/plan">Plans</Link>.</p>
  </div>;
}
