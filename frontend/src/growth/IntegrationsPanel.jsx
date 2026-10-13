import { useEffect, useState } from "react";
import { toast } from "sonner";
import { CheckCircle2, XCircle, RefreshCw, Plus, Trash2 } from "lucide-react";
import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { useApi, err, dt } from "./lib";
import { ErrorBox } from "./Bits";

const Dot = ({ ok }) => ok ? <CheckCircle2 className="h-4 w-4 text-emerald-600" /> : <XCircle className="h-4 w-4 text-red-500" />;

export function IntegrationsPanel({ projectId, isAdmin, project, onSaved }) {
  const { data, error, reload } = useApi("/growth/integrations", [projectId]);
  const gsc = useApi(`/growth/projects/${projectId}/search-console`, [projectId]);
  const [members, setMembers] = useState(null);
  const [m, setM] = useState({ email: "", role: "reader" });
  const [site, setSite] = useState("");
  const [busy, setBusy] = useState(false);
  const [settings, setSettings] = useState(project?.settings || {});
  useEffect(() => { if (isAdmin) api.get("/growth/members").then((r) => setMembers(r.data.members)).catch(() => {}); }, [isAdmin]);
  useEffect(() => { setSettings(project?.settings || {}); }, [project]);
  const google = async () => { try { const r = await api.post("/growth/integrations/google/start", { project_id: projectId }); window.location.assign(r.data.url); } catch (e) { toast.error(err(e, "Cliente OAuth Google não configurado")); } };
  const sync = async () => { setBusy(true); try { const r = await api.post("/growth/integrations/google/sync", { project_id: projectId, site_url: site }); if (r.data.ok) toast.success("Search Console sincronizada"); else toast.error(r.data.reason); gsc.reload(); } catch (e) { toast.error(err(e)); } finally { setBusy(false); } };
  const addMember = async () => { try { await api.put("/growth/members", m); const r = await api.get("/growth/members"); setMembers(r.data.members); setM({ ...m, email: "" }); } catch (e) { toast.error(err(e)); } };
  const saveSettings = async () => { try { await api.put(`/growth/projects/${projectId}/settings`, { settings: { publish_mode: settings.publish_mode, max_pages: Number(settings.max_pages) || 50, crawl_cadence_days: Number(settings.crawl_cadence_days) || 0 } }); toast.success("Definições guardadas"); onSaved?.(); } catch (e) { toast.error(err(e)); } };
  if (error) return <ErrorBox error={error} onRetry={reload} />;
  if (!data) return null;
  const conn = gsc.data?.connection;
  return <div className="space-y-4 text-sm" data-testid="growth-integrations">
    <section className="surface p-3 space-y-2" data-testid="growth-int-providers"><p className="overline">Fornecedores IA (medição de visibilidade)</p>
      {Object.entries(data.providers).map(([k, v]) => <div key={k} className="flex flex-wrap items-center gap-2"><Dot ok={v.configured} /><span className="font-medium">{v.label}</span><span className="text-xs text-muted-foreground">variable {v.env} · recherche web : {v.web_search ? "oui" : "non"} · citações observáveis: {v.citations_observable ? "oui" : "non"}</span>{!v.configured && <Badge variant="outline" className="rounded-sm text-red-600">ligação em falta</Badge>}</div>)}
      <p className="text-xs text-muted-foreground">Os resultados são testes via API e não reproduzem necessariamente o ChatGPT, Gemini, Claude ou Perplexity para o grande público.</p></section>
    <section className="surface p-3 space-y-2" data-testid="growth-int-google"><p className="overline">Google Search Console</p>
      <div className="flex flex-wrap items-center gap-2"><Dot ok={data.google.client_configured} /><span>Cliente OAuth {data.google.client_configured ? "configurado" : "não configurado"}</span>{data.google.project_id_hint && <span className="text-xs text-muted-foreground">projet GCP : {data.google.project_id_hint}</span>}</div>
      {!data.google.client_configured && <div className="text-xs bg-amber-500/10 rounded-md p-2 space-y-1"><p><strong>Bloqueado:</strong> variáveis em falta {data.google.missing.join(", ")}.</p><p>{data.google.how_to}</p><p>URI de redirecionamento a autorizar: <code className="num">{data.google.redirect_uri}</code></p></div>}
      <div className="flex flex-wrap items-center gap-2"><Dot ok={conn?.status === "connected"} /><span>Propriedade: {conn?.status === "connected" ? (conn.site_url || "a escolher") : "não ligada"}</span>{conn?.last_sync && <span className="text-xs text-muted-foreground">última sincronização {dt(conn.last_sync)}</span>}
        {isAdmin && <Button size="sm" variant="outline" onClick={google} disabled={!data.google.client_configured} data-testid="growth-google-connect">Ligar</Button>}
        {conn?.status === "connected" && <><select className="h-8 rounded-md border bg-background px-2 text-xs" value={site} onChange={(e) => setSite(e.target.value)}><option value="">Propriedade automática</option>{(conn.sites || []).map((s) => <option key={s}>{s}</option>)}</select><Button size="sm" onClick={sync} disabled={busy} data-testid="growth-google-sync"><RefreshCw className={`h-4 w-4 ${busy ? "animate-spin" : ""}`} /> Sincronizar</Button></>}</div>
      {gsc.data?.snapshot && <div className="text-xs space-y-1"><p className="num">{gsc.data.snapshot.start} → {gsc.data.snapshot.end} · {gsc.data.snapshot.totals.clicks} cliques · {gsc.data.snapshot.totals.impressions} impressions</p>
        <details><summary className="cursor-pointer">Pesquisas / páginas / países / dispositivos</summary>{["query", "page", "country", "device"].map((d) => <div key={d} className="mt-1"><p className="overline">{d}</p><table className="w-full"><tbody>{(gsc.data.snapshot.data[d] || []).slice(0, 15).map((r) => <tr key={r.key} className="border-t"><td className="truncate max-w-[300px]">{r.key}</td><td className="num">{r.clicks} clics</td><td className="num">{r.impressions} impr.</td><td className="num">{r.ctr} %</td><td className="num">pos. {r.position}</td></tr>)}</tbody></table></div>)}</details>
        <p className="text-muted-foreground">{gsc.data.snapshot.limits}</p></div>}
      <p className="text-xs text-muted-foreground">GA4 / conversões: {data.ga4.how_to} {gsc.data?.conversions?.note}</p></section>
    <section className="surface p-3 space-y-2" data-testid="growth-int-publish"><p className="overline">Publicação</p>
      <p className="flex items-center gap-2"><Dot ok /> Blogue construpilot.pt: conector nativo (coleção do blogue, apresentada em /blog/{"{slug}"}).</p>
      <p className="flex items-center gap-2"><Dot ok={data.pt_publish.configured} /> Blog construpilot.pt : {data.pt_publish.configured ? `API de publicação para ${data.pt_publish.site_url}` : "não configurado — os artigos PT são publicados nesta publicação (filtro de língua pt)"}</p>
      {!data.pt_publish.configured && <p className="text-xs text-muted-foreground">{data.pt_publish.how_to} Token de entrada definido aqui: {data.pt_publish.inbox_token_set ? "oui" : "non"}.</p>}
      {isAdmin && <div className="flex flex-wrap items-end gap-2 text-xs pt-1" data-testid="growth-settings-form">
        <label>Modo de publicação<select className="block h-8 rounded-md border bg-background px-2" value={settings.publish_mode || "review"} onChange={(e) => setSettings({ ...settings, publish_mode: e.target.value })} data-testid="growth-publish-mode"><option value="review">validation avant publication</option><option value="auto">automático (conteúdos aprovados e agendados)</option></select></label>
        <label>Páginas máx. por auditoria<Input type="number" className="num h-8" value={settings.max_pages ?? 50} onChange={(e) => setSettings({ ...settings, max_pages: e.target.value })} /></label>
        <label>Cadence audit (jours, 0 = manuel)<Input type="number" className="num h-8" value={settings.crawl_cadence_days ?? 7} onChange={(e) => setSettings({ ...settings, crawl_cadence_days: e.target.value })} /></label>
        <Button size="sm" onClick={saveSettings} data-testid="growth-settings-save">Guardar</Button></div>}
      <p className="text-xs text-muted-foreground">Os controlos de qualidade aplicam-se nos dois modos; uma afirmação não verificada bloqueia a publicação. Nenhuma posição na Google nem recomendação por uma IA é prometida.</p></section>
    {isAdmin && <section className="surface p-3 space-y-2" data-testid="growth-int-members"><p className="overline">Equipa de marketing (funções)</p>
      <div className="flex flex-wrap gap-2"><Input className="w-64" placeholder="e-mail de uma conta existente" value={m.email} onChange={(e) => setM({ ...m, email: e.target.value })} data-testid="growth-member-email" /><select className="h-9 rounded-md border bg-background px-2" value={m.role} onChange={(e) => setM({ ...m, role: e.target.value })} data-testid="growth-member-role"><option value="reader">lecteur</option><option value="editor">editor</option><option value="admin">administrateur</option></select><Button size="sm" onClick={addMember} disabled={!m.email} data-testid="growth-member-add"><Plus className="h-4 w-4" /></Button></div>
      <ul className="text-xs">{(members || []).map((x) => <li key={x.user_id} className="flex items-center gap-2 py-0.5">{x.email} <Badge variant="outline" className="rounded-sm">{x.role}</Badge><button className="text-destructive" onClick={async () => { await api.delete(`/growth/members/${x.user_id}`); setMembers(members.filter((y) => y.user_id !== x.user_id)); }}><Trash2 className="h-3 w-3" /></button></li>)}{members?.length === 0 && <li className="text-muted-foreground">Os administradores ConstruPilot têm acesso por omissão.</li>}</ul></section>}
  </div>;
}
