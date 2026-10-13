import { useEffect, useState } from "react";
import { toast } from "sonner";
import { Plus, Wand2, PenLine, ShieldCheck, Send, CheckCircle2, RotateCcw, Archive, ExternalLink, Search, Bot } from "lucide-react";
import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { useApi, err, dt, STATUS_FR } from "./lib";
import { Empty, ErrorBox } from "./Bits";

const STATE_CLS = { published: "bg-emerald-500/15 text-emerald-700", approved: "bg-emerald-500/10", scheduled: "bg-sky-500/15", review: "bg-amber-500/15 text-amber-700", failed: "bg-red-500/15 text-red-700", archived: "opacity-50" };
const FORMATS = ["guide pratique", "página de funcionalidade", "FAQ", "tutoriel", "comparativo factual", "caso de uso documentado"];

function Editor({ contentId, canEdit, isAdmin, onClose, onChanged }) {
  const [c, setC] = useState(null);
  const [busy, setBusy] = useState("");
  const load = () => api.get(`/growth/contents/${contentId}`).then((r) => setC(r.data)).catch(() => toast.error("Conteúdo não encontrado"));
  useEffect(() => { load(); }, [contentId]); // eslint-disable-line react-hooks/exhaustive-deps
  const act = async (label, fn) => { setBusy(label); try { await fn(); await load(); onChanged(); } catch (e) { toast.error(err(e)); } finally { setBusy(""); } };
  if (!c) return null;
  const save = () => act("save", async () => { await api.put(`/growth/contents/${contentId}`, { topic: c.topic, intent: c.intent, audience: c.audience || "", format: c.format || "", scheduled_for: c.scheduled_for || "", title: c.title || "", slug: c.slug || "", description: c.description || "", body_markdown: c.body_markdown || "", cta: c.cta || "" }); toast.success("Guardado"); });
  const chk = c.checks;
  const stale = chk && c.updated_at && chk.checked_at < c.updated_at;
  return <div className="surface p-4 space-y-3 text-sm" data-testid="growth-content-editor">
    <div className="flex flex-wrap items-center gap-2"><Badge className={`rounded-sm border-0 ${STATE_CLS[c.status] || "bg-muted"}`}>{STATUS_FR[c.status] || c.status}</Badge><span className="num text-xs text-muted-foreground">v{c.version} · {c.intent} · {c.format}</span>
      {c.published_url && <a className="text-xs underline flex items-center gap-1" href={c.published_url} target="_blank" rel="noreferrer">{c.published_url} <ExternalLink className="h-3 w-3" /></a>}
      <Button size="sm" variant="ghost" className="ml-auto" onClick={onClose}>Fechar</Button></div>
    <div className="grid sm:grid-cols-2 gap-2">
      <Input placeholder="Assunto" value={c.topic || ""} onChange={(e) => setC({ ...c, topic: e.target.value })} disabled={!canEdit} data-testid="growth-content-topic" />
      <Input placeholder="Público" value={c.audience || ""} onChange={(e) => setC({ ...c, audience: e.target.value })} disabled={!canEdit} />
      <Input placeholder="Título" value={c.title || ""} onChange={(e) => setC({ ...c, title: e.target.value })} disabled={!canEdit} data-testid="growth-content-title" />
      <Input placeholder="Slug" value={c.slug || ""} onChange={(e) => setC({ ...c, slug: e.target.value })} disabled={!canEdit} data-testid="growth-content-slug" />
      <Input className="sm:col-span-2" placeholder="Descrição (140–160 car.)" value={c.description || ""} onChange={(e) => setC({ ...c, description: e.target.value })} disabled={!canEdit} />
      <Input placeholder="Chamada à ação" value={c.cta || ""} onChange={(e) => setC({ ...c, cta: e.target.value })} disabled={!canEdit} />
      <Input type="datetime-local" value={(c.scheduled_for || "").slice(0, 16)} onChange={(e) => setC({ ...c, scheduled_for: e.target.value ? new Date(e.target.value).toISOString() : "" })} disabled={!canEdit} data-testid="growth-content-schedule" />
    </div>
    {c.research && <details className="text-xs" data-testid="growth-content-research" open><summary className="cursor-pointer">Fontes verificadas: {c.research.sources.length} ({c.research.trusted_count} oficiais) · rejeitadas: {c.research.rejected.length} · {dt(c.research.searched_at)}</summary>
      <ul className="mt-1 space-y-0.5">{c.research.sources.map((s) => <li key={s.url} className="truncate">{s.trusted ? "🏛 " : "· "}<a className="underline" href={s.url} target="_blank" rel="noreferrer">{s.title}</a> <span className="text-muted-foreground">— {s.publisher}{s.date ? ` · ${s.date}` : ""} · HTTP {s.http_status}</span></li>)}</ul>
      {c.research.rejected.length > 0 && <p className="text-muted-foreground mt-1">Rejeitadas: {c.research.rejected.map((r) => `${r.url} (${r.error})`).join(" ; ")}</p>}</details>}
    {c.autopilot_log?.length > 0 && <details className="text-xs"><summary className="cursor-pointer">Journal auto-pilote ({c.autopilot_log.length})</summary>{c.autopilot_log.map((l, i) => <p key={i} className={l.ok ? "" : "text-red-700"}>{dt(l.at)} · {l.step} · {l.ok ? "ok" : "falha"} · {l.note}</p>)}</details>}
    {c.outline?.length > 0 && <details className="text-xs"><summary className="cursor-pointer">Structure ({c.outline.length} secções) · ligações internas: {(c.internal_links || []).length} · fontes a verificar: {(c.sources_to_check || []).length}</summary><ol className="list-decimal ml-5 mt-1">{c.outline.map((o, i) => <li key={i}>{o}</li>)}</ol>{c.internal_links?.map((l) => <p key={l} className="truncate">{l}</p>)}</details>}
    <textarea className="w-full min-h-[280px] rounded-md border bg-background p-2 text-xs font-mono" value={c.body_markdown || ""} onChange={(e) => setC({ ...c, body_markdown: e.target.value })} disabled={!canEdit} placeholder="Texto em Markdown — gerado por «Redigir» ou introduzido à mão" data-testid="growth-content-body" />
    {c.claims_about_construpilot?.length > 0 && <p className="text-xs text-muted-foreground">Afirmações sobre o ConstruPilot a verificar contra a ficha de marca: {c.claims_about_construpilot.length}</p>}
    {chk && <div className={`rounded-md p-2 text-xs ${chk.passed ? "bg-emerald-500/10" : "bg-red-500/10"}`} data-testid="growth-content-checks">
      <p className="font-medium">Controlos de qualidade {chk.passed ? "bem-sucedidos" : "BLOQUEANTES"} · {chk.word_count} palavras · {dt(chk.checked_at)}{stale && <span className="text-amber-700"> — obsoletos: o texto mudou, volte a lançar</span>}</p>
      {chk.blocking.map((b, i) => <p key={i} className="text-red-700">✕ {b.kind} : {b.text} → {b.fix}</p>)}{chk.warnings.map((w, i) => <p key={i} className="text-amber-700">⚠ {w.kind} : {w.text} → {w.fix}</p>)}
    </div>}
    {c.publications?.length > 0 && <details className="text-xs"><summary className="cursor-pointer">Publications ({c.publications.length}) e verificação pós-publicação</summary>{c.publications.map((p, i) => <p key={i}>{dt(p.published_at)} → {p.target} · HTTP {p.verification?.http_status ?? "?"} · título {p.verification?.title_tag_present ? "presente" : "não detetado"} · sitemap {p.verification?.in_blog_sitemap ? "oui" : "non"} · indexation : {p.verification?.indexation}</p>)}</details>}
    {c.versions?.length > 0 && <details className="text-xs"><summary className="cursor-pointer">Versões ({c.versions.length})</summary>{c.versions.map((v) => <p key={v.version} className="flex gap-2 items-center">v{v.version} · {dt(v.at)} · {v.title}{canEdit && <button className="underline" onClick={() => act("rb", async () => { await api.post(`/growth/contents/${contentId}/rollback/${v.version}`); toast.success("Versão restaurada"); })}><RotateCcw className="inline h-3 w-3" /> restaurer</button>}</p>)}</details>}
    {canEdit && <div className="flex flex-wrap gap-2">
      <Button size="sm" variant="outline" onClick={save} disabled={!!busy} data-testid="growth-content-save">Guardar</Button>
      {isAdmin && c.status === "published" && <Button size="sm" variant="outline" onClick={() => { const target = window.prompt("URL da publicação alvo (produção ou .pt)", "https://construpilot.fr"); if (target) act("push", async () => { const r = await api.post(`/growth/contents/${contentId}/push`, { target_url: target }); toast.success(`Artigo enviado: ${r.data.url}`); }); }} disabled={!!busy} data-testid="growth-content-push"><Send className="h-4 w-4" /> Enviar para outra publicação</Button>}
      <Button size="sm" variant="outline" onClick={() => act("research", async () => { const r = await api.post(`/growth/contents/${contentId}/research`); toast.success(`${r.data.sources.length} fonte(s) verificada(s)`); })} disabled={!!busy} data-testid="growth-content-research-btn"><Search className="h-4 w-4" /> {busy === "research" ? "A pesquisar…" : "Pesquisar as fontes"}</Button>
      <Button size="sm" variant="outline" onClick={() => act("auto", async () => { await api.post(`/growth/contents/${contentId}/auto`); toast.success("Pipeline lançado: pesquisa → brief → redação → controlos (alguns minutos)"); })} disabled={!!busy || ["published", "archived"].includes(c.status)} data-testid="growth-content-auto"><Bot className="h-4 w-4" /> Automatizar tudo</Button>
      <Button size="sm" variant="outline" onClick={() => act("brief", async () => { await api.post(`/growth/contents/${contentId}/brief`); toast.success("Brief preparado"); })} disabled={!!busy} data-testid="growth-content-brief"><Wand2 className="h-4 w-4" /> {busy === "brief" ? "A pesquisar…" : "Preparar o brief"}</Button>
      <Button size="sm" variant="outline" onClick={() => act("draft", async () => { await api.post(`/growth/contents/${contentId}/draft`); toast.success("Rascunho redigido"); })} disabled={!!busy || !c.outline?.length} data-testid="growth-content-draft"><PenLine className="h-4 w-4" /> {busy === "draft" ? "A redigir…" : "Redigir"}</Button>
      <Button size="sm" variant="outline" onClick={() => act("check", async () => { const r = await api.post(`/growth/contents/${contentId}/check`); toast[r.data.passed ? "success" : "error"](r.data.passed ? "Controlos bem-sucedidos" : `${r.data.blocking.length} blocage(s)`); })} disabled={!!busy || !c.body_markdown} data-testid="growth-content-check"><ShieldCheck className="h-4 w-4" /> Verificar</Button>
      <Button size="sm" onClick={() => act("approve", async () => { await api.post(`/growth/contents/${contentId}/status`, { status: c.scheduled_for ? "scheduled" : "approved", scheduled_for: c.scheduled_for || "" }); toast.success(c.scheduled_for ? "Agendado" : "Aprovado"); })} disabled={!!busy || !chk?.passed || stale || ["approved", "scheduled", "published"].includes(c.status)} data-testid="growth-content-approve"><CheckCircle2 className="h-4 w-4" /> Aprovar{c.scheduled_for ? " e agendar" : ""}</Button>
      <Button size="sm" onClick={() => act("publish", async () => { const r = await api.post(`/growth/contents/${contentId}/publish`); toast.success(`Publicado: ${r.data.published_url}`); })} disabled={!!busy || !["approved", "scheduled", "failed"].includes(c.status)} data-testid="growth-content-publish"><Send className="h-4 w-4" /> {busy === "publish" ? "Publication…" : "Publicar agora"}</Button>
      {c.status !== "archived" && <Button size="sm" variant="ghost" className="text-destructive" onClick={() => act("arch", async () => { await api.delete(`/growth/contents/${contentId}`); onClose(); })}><Archive className="h-4 w-4" /></Button>}
    </div>}
    {!isAdmin && c.status === "published" && <p className="text-xs text-muted-foreground">A alteração de um artigo publicado requer a função admin.</p>}
  </div>;
}

export function ContentsPanel({ projectId, canEdit, isAdmin, openId, onOpen }) {
  const { data, error, reload } = useApi(`/growth/projects/${projectId}/contents`, [projectId]);
  const [draft, setDraft] = useState({ topic: "", intent: "descoberta", format: FORMATS[0] });
  const add = async () => { try { const r = await api.post(`/growth/projects/${projectId}/contents`, draft); setDraft({ ...draft, topic: "" }); reload(); onOpen(r.data.content_id); } catch (e) { toast.error(err(e)); } };
  if (error) return <ErrorBox error={error} onRetry={reload} />;
  if (!data) return null;
  const upcoming = data.calendar.filter((d) => d.items.length);
  return <div className="space-y-4" data-testid="growth-contents">
    <p className="text-sm text-muted-foreground">Ideia → pesquisa de fontes verificadas → brief → rascunho → revisão (controlos: afirmações, duplicados, ligações, fontes) → aprovação → publicação no blogue. «Automatizar tudo» encadeia as etapas até à revisão. Modo «validação antes de publicar» por omissão; a publicação automática configura-se em Integrações.</p>
    {canEdit && <div className="surface p-3 flex flex-wrap gap-2 items-center" data-testid="growth-content-form">
      <Input className="flex-1 min-w-[240px]" placeholder="Assunto / intenção de pesquisa…" value={draft.topic} onChange={(e) => setDraft({ ...draft, topic: e.target.value })} data-testid="growth-content-new-topic" />
      <select className="h-9 rounded-md border bg-background px-2 text-sm" value={draft.intent} onChange={(e) => setDraft({ ...draft, intent: e.target.value })}>{["descoberta", "comparaison", "achat", "necessidade profissional", "marque"].map((i) => <option key={i}>{i}</option>)}</select>
      <select className="h-9 rounded-md border bg-background px-2 text-sm" value={draft.format} onChange={(e) => setDraft({ ...draft, format: e.target.value })}>{FORMATS.map((f) => <option key={f}>{f}</option>)}</select>
      <Button size="sm" onClick={add} disabled={draft.topic.trim().length < 4} data-testid="growth-content-add"><Plus className="h-4 w-4" /> Nova ideia</Button></div>}
    {openId && <Editor contentId={openId} canEdit={canEdit} isAdmin={isAdmin} onClose={() => onOpen(null)} onChanged={reload} />}
    <div className="grid lg:grid-cols-[1fr_280px] gap-4">
      <ul className="divide-y border rounded-md">{data.contents.map((c) => <li key={c.content_id} className="px-3 py-2 text-sm flex flex-wrap items-center gap-2 cursor-pointer hover:bg-muted/40" onClick={() => onOpen(c.content_id)} data-testid={`growth-content-${c.content_id}`}>
        <Badge className={`rounded-sm border-0 ${STATE_CLS[c.status] || "bg-muted"}`}>{STATUS_FR[c.status] || c.status}</Badge><span className="flex-1 min-w-[200px]">{c.title || c.topic}</span><span className="text-xs text-muted-foreground">{c.intent} · {c.format} · v{c.version}{c.scheduled_for ? ` · ${dt(c.scheduled_for)}` : ""}</span></li>)}
        {data.contents.length === 0 && <li className="p-4 text-sm text-muted-foreground" data-testid="growth-contents-empty">Nenhum conteúdo. Crie uma ideia ou parta de uma ação do plano.</li>}</ul>
      <div className="surface p-3 text-xs" data-testid="growth-calendar"><p className="overline mb-1">Calendário de 30 dias</p>{upcoming.length === 0 && <p className="text-muted-foreground">Nada agendado.</p>}{upcoming.map((d) => <div key={d.date} className="border-t py-1"><p className="num font-medium">{d.date}</p>{d.items.map((i) => <p key={i.content_id} className="truncate">· {i.title || i.topic} <span className="text-muted-foreground">({STATUS_FR[i.status]})</span></p>)}</div>)}</div>
    </div>
    {!openId && <Empty>Clique num conteúdo para abrir o editor (brief, redação, controlos, versões, publicação).</Empty>}
  </div>;
}
