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
const FORMATS = ["guide pratique", "page fonctionnalité", "FAQ", "tutoriel", "comparatif factuel", "cas d'usage documenté"];

function Editor({ contentId, canEdit, isAdmin, onClose, onChanged }) {
  const [c, setC] = useState(null);
  const [busy, setBusy] = useState("");
  const load = () => api.get(`/growth/contents/${contentId}`).then((r) => setC(r.data)).catch(() => toast.error("Contenu introuvable"));
  useEffect(() => { load(); }, [contentId]); // eslint-disable-line react-hooks/exhaustive-deps
  const act = async (label, fn) => { setBusy(label); try { await fn(); await load(); onChanged(); } catch (e) { toast.error(err(e)); } finally { setBusy(""); } };
  if (!c) return null;
  const save = () => act("save", async () => { await api.put(`/growth/contents/${contentId}`, { topic: c.topic, intent: c.intent, audience: c.audience || "", format: c.format || "", scheduled_for: c.scheduled_for || "", title: c.title || "", slug: c.slug || "", description: c.description || "", body_markdown: c.body_markdown || "", cta: c.cta || "" }); toast.success("Enregistré"); });
  const chk = c.checks;
  const stale = chk && c.updated_at && chk.checked_at < c.updated_at;
  return <div className="surface p-4 space-y-3 text-sm" data-testid="growth-content-editor">
    <div className="flex flex-wrap items-center gap-2"><Badge className={`rounded-sm border-0 ${STATE_CLS[c.status] || "bg-muted"}`}>{STATUS_FR[c.status] || c.status}</Badge><span className="num text-xs text-muted-foreground">v{c.version} · {c.intent} · {c.format}</span>
      {c.published_url && <a className="text-xs underline flex items-center gap-1" href={c.published_url} target="_blank" rel="noreferrer">{c.published_url} <ExternalLink className="h-3 w-3" /></a>}
      <Button size="sm" variant="ghost" className="ml-auto" onClick={onClose}>Fermer</Button></div>
    <div className="grid sm:grid-cols-2 gap-2">
      <Input placeholder="Sujet" value={c.topic || ""} onChange={(e) => setC({ ...c, topic: e.target.value })} disabled={!canEdit} data-testid="growth-content-topic" />
      <Input placeholder="Public" value={c.audience || ""} onChange={(e) => setC({ ...c, audience: e.target.value })} disabled={!canEdit} />
      <Input placeholder="Titre" value={c.title || ""} onChange={(e) => setC({ ...c, title: e.target.value })} disabled={!canEdit} data-testid="growth-content-title" />
      <Input placeholder="Slug" value={c.slug || ""} onChange={(e) => setC({ ...c, slug: e.target.value })} disabled={!canEdit} data-testid="growth-content-slug" />
      <Input className="sm:col-span-2" placeholder="Description (140–160 car.)" value={c.description || ""} onChange={(e) => setC({ ...c, description: e.target.value })} disabled={!canEdit} />
      <Input placeholder="Appel à l'action" value={c.cta || ""} onChange={(e) => setC({ ...c, cta: e.target.value })} disabled={!canEdit} />
      <Input type="datetime-local" value={(c.scheduled_for || "").slice(0, 16)} onChange={(e) => setC({ ...c, scheduled_for: e.target.value ? new Date(e.target.value).toISOString() : "" })} disabled={!canEdit} data-testid="growth-content-schedule" />
    </div>
    {c.research && <details className="text-xs" data-testid="growth-content-research" open><summary className="cursor-pointer">Sources vérifiées : {c.research.sources.length} ({c.research.trusted_count} officielles) · rejetées : {c.research.rejected.length} · {dt(c.research.searched_at)}</summary>
      <ul className="mt-1 space-y-0.5">{c.research.sources.map((s) => <li key={s.url} className="truncate">{s.trusted ? "🏛 " : "· "}<a className="underline" href={s.url} target="_blank" rel="noreferrer">{s.title}</a> <span className="text-muted-foreground">— {s.publisher}{s.date ? ` · ${s.date}` : ""} · HTTP {s.http_status}</span></li>)}</ul>
      {c.research.rejected.length > 0 && <p className="text-muted-foreground mt-1">Rejetées : {c.research.rejected.map((r) => `${r.url} (${r.error})`).join(" ; ")}</p>}</details>}
    {c.autopilot_log?.length > 0 && <details className="text-xs"><summary className="cursor-pointer">Journal auto-pilote ({c.autopilot_log.length})</summary>{c.autopilot_log.map((l, i) => <p key={i} className={l.ok ? "" : "text-red-700"}>{dt(l.at)} · {l.step} · {l.ok ? "ok" : "échec"} · {l.note}</p>)}</details>}
    {c.outline?.length > 0 && <details className="text-xs"><summary className="cursor-pointer">Structure ({c.outline.length} sections) · liens internes : {(c.internal_links || []).length} · sources à vérifier : {(c.sources_to_check || []).length}</summary><ol className="list-decimal ml-5 mt-1">{c.outline.map((o, i) => <li key={i}>{o}</li>)}</ol>{c.internal_links?.map((l) => <p key={l} className="truncate">{l}</p>)}</details>}
    <textarea className="w-full min-h-[280px] rounded-md border bg-background p-2 text-xs font-mono" value={c.body_markdown || ""} onChange={(e) => setC({ ...c, body_markdown: e.target.value })} disabled={!canEdit} placeholder="Texte en Markdown — généré par « Rédiger » ou saisi à la main" data-testid="growth-content-body" />
    {c.claims_about_construpilot?.length > 0 && <p className="text-xs text-muted-foreground">Affirmations sur ConstruPilot à vérifier contre la fiche de marque : {c.claims_about_construpilot.length}</p>}
    {chk && <div className={`rounded-md p-2 text-xs ${chk.passed ? "bg-emerald-500/10" : "bg-red-500/10"}`} data-testid="growth-content-checks">
      <p className="font-medium">Contrôles qualité {chk.passed ? "réussis" : "BLOQUANTS"} · {chk.word_count} mots · {dt(chk.checked_at)}{stale && <span className="text-amber-700"> — obsolètes : le texte a changé, relancez</span>}</p>
      {chk.blocking.map((b, i) => <p key={i} className="text-red-700">✕ {b.kind} : {b.text} → {b.fix}</p>)}{chk.warnings.map((w, i) => <p key={i} className="text-amber-700">⚠ {w.kind} : {w.text} → {w.fix}</p>)}
    </div>}
    {c.publications?.length > 0 && <details className="text-xs"><summary className="cursor-pointer">Publications ({c.publications.length}) et vérification post-publication</summary>{c.publications.map((p, i) => <p key={i}>{dt(p.published_at)} → {p.target} · HTTP {p.verification?.http_status ?? "?"} · titre {p.verification?.title_tag_present ? "présent" : "non détecté"} · sitemap {p.verification?.in_blog_sitemap ? "oui" : "non"} · indexation : {p.verification?.indexation}</p>)}</details>}
    {c.versions?.length > 0 && <details className="text-xs"><summary className="cursor-pointer">Versions ({c.versions.length})</summary>{c.versions.map((v) => <p key={v.version} className="flex gap-2 items-center">v{v.version} · {dt(v.at)} · {v.title}{canEdit && <button className="underline" onClick={() => act("rb", async () => { await api.post(`/growth/contents/${contentId}/rollback/${v.version}`); toast.success("Version restaurée"); })}><RotateCcw className="inline h-3 w-3" /> restaurer</button>}</p>)}</details>}
    {canEdit && <div className="flex flex-wrap gap-2">
      <Button size="sm" variant="outline" onClick={save} disabled={!!busy} data-testid="growth-content-save">Enregistrer</Button>
      {isAdmin && c.status === "published" && <Button size="sm" variant="outline" onClick={() => { const target = window.prompt("URL du déploiement cible (production ou .pt)", "https://construpilot.fr"); if (target) act("push", async () => { const r = await api.post(`/growth/contents/${contentId}/push`, { target_url: target }); toast.success(`Article poussé : ${r.data.url}`); }); }} disabled={!!busy} data-testid="growth-content-push"><Send className="h-4 w-4" /> Pousser vers un autre déploiement</Button>}
      <Button size="sm" variant="outline" onClick={() => act("research", async () => { const r = await api.post(`/growth/contents/${contentId}/research`); toast.success(`${r.data.sources.length} source(s) vérifiée(s)`); })} disabled={!!busy} data-testid="growth-content-research-btn"><Search className="h-4 w-4" /> {busy === "research" ? "Recherche…" : "Rechercher les sources"}</Button>
      <Button size="sm" variant="outline" onClick={() => act("auto", async () => { await api.post(`/growth/contents/${contentId}/auto`); toast.success("Pipeline lancé : recherche → brief → rédaction → contrôles (quelques minutes)"); })} disabled={!!busy || ["published", "archived"].includes(c.status)} data-testid="growth-content-auto"><Bot className="h-4 w-4" /> Tout automatiser</Button>
      <Button size="sm" variant="outline" onClick={() => act("brief", async () => { await api.post(`/growth/contents/${contentId}/brief`); toast.success("Brief préparé"); })} disabled={!!busy} data-testid="growth-content-brief"><Wand2 className="h-4 w-4" /> {busy === "brief" ? "Recherche…" : "Préparer le brief"}</Button>
      <Button size="sm" variant="outline" onClick={() => act("draft", async () => { await api.post(`/growth/contents/${contentId}/draft`); toast.success("Brouillon rédigé"); })} disabled={!!busy || !c.outline?.length} data-testid="growth-content-draft"><PenLine className="h-4 w-4" /> {busy === "draft" ? "Rédaction…" : "Rédiger"}</Button>
      <Button size="sm" variant="outline" onClick={() => act("check", async () => { const r = await api.post(`/growth/contents/${contentId}/check`); toast[r.data.passed ? "success" : "error"](r.data.passed ? "Contrôles réussis" : `${r.data.blocking.length} blocage(s)`); })} disabled={!!busy || !c.body_markdown} data-testid="growth-content-check"><ShieldCheck className="h-4 w-4" /> Vérifier</Button>
      <Button size="sm" onClick={() => act("approve", async () => { await api.post(`/growth/contents/${contentId}/status`, { status: c.scheduled_for ? "scheduled" : "approved", scheduled_for: c.scheduled_for || "" }); toast.success(c.scheduled_for ? "Programmé" : "Approuvé"); })} disabled={!!busy || !chk?.passed || stale || ["approved", "scheduled", "published"].includes(c.status)} data-testid="growth-content-approve"><CheckCircle2 className="h-4 w-4" /> Approuver{c.scheduled_for ? " et programmer" : ""}</Button>
      <Button size="sm" onClick={() => act("publish", async () => { const r = await api.post(`/growth/contents/${contentId}/publish`); toast.success(`Publié : ${r.data.published_url}`); })} disabled={!!busy || !["approved", "scheduled", "failed"].includes(c.status)} data-testid="growth-content-publish"><Send className="h-4 w-4" /> {busy === "publish" ? "Publication…" : "Publier maintenant"}</Button>
      {c.status !== "archived" && <Button size="sm" variant="ghost" className="text-destructive" onClick={() => act("arch", async () => { await api.delete(`/growth/contents/${contentId}`); onClose(); })}><Archive className="h-4 w-4" /></Button>}
    </div>}
    {!isAdmin && c.status === "published" && <p className="text-xs text-muted-foreground">La modification d'un article publié requiert le rôle admin.</p>}
  </div>;
}

export function ContentsPanel({ projectId, canEdit, isAdmin, openId, onOpen }) {
  const { data, error, reload } = useApi(`/growth/projects/${projectId}/contents`, [projectId]);
  const [draft, setDraft] = useState({ topic: "", intent: "découverte", format: FORMATS[0] });
  const add = async () => { try { const r = await api.post(`/growth/projects/${projectId}/contents`, draft); setDraft({ ...draft, topic: "" }); reload(); onOpen(r.data.content_id); } catch (e) { toast.error(err(e)); } };
  if (error) return <ErrorBox error={error} onRetry={reload} />;
  if (!data) return null;
  const upcoming = data.calendar.filter((d) => d.items.length);
  return <div className="space-y-4" data-testid="growth-contents">
    <p className="text-sm text-muted-foreground">Idée → recherche de sources vérifiées → brief → brouillon → relecture (contrôles : affirmations, doublons, liens, sources) → approbation → publication sur le blog. « Tout automatiser » enchaîne les étapes jusqu'à la relecture. Mode « validation avant publication » par défaut ; la publication automatique se règle dans Intégrations.</p>
    {canEdit && <div className="surface p-3 flex flex-wrap gap-2 items-center" data-testid="growth-content-form">
      <Input className="flex-1 min-w-[240px]" placeholder="Sujet / intention de recherche…" value={draft.topic} onChange={(e) => setDraft({ ...draft, topic: e.target.value })} data-testid="growth-content-new-topic" />
      <select className="h-9 rounded-md border bg-background px-2 text-sm" value={draft.intent} onChange={(e) => setDraft({ ...draft, intent: e.target.value })}>{["découverte", "comparaison", "achat", "besoin métier", "marque"].map((i) => <option key={i}>{i}</option>)}</select>
      <select className="h-9 rounded-md border bg-background px-2 text-sm" value={draft.format} onChange={(e) => setDraft({ ...draft, format: e.target.value })}>{FORMATS.map((f) => <option key={f}>{f}</option>)}</select>
      <Button size="sm" onClick={add} disabled={draft.topic.trim().length < 4} data-testid="growth-content-add"><Plus className="h-4 w-4" /> Nouvelle idée</Button></div>}
    {openId && <Editor contentId={openId} canEdit={canEdit} isAdmin={isAdmin} onClose={() => onOpen(null)} onChanged={reload} />}
    <div className="grid lg:grid-cols-[1fr_280px] gap-4">
      <ul className="divide-y border rounded-md">{data.contents.map((c) => <li key={c.content_id} className="px-3 py-2 text-sm flex flex-wrap items-center gap-2 cursor-pointer hover:bg-muted/40" onClick={() => onOpen(c.content_id)} data-testid={`growth-content-${c.content_id}`}>
        <Badge className={`rounded-sm border-0 ${STATE_CLS[c.status] || "bg-muted"}`}>{STATUS_FR[c.status] || c.status}</Badge><span className="flex-1 min-w-[200px]">{c.title || c.topic}</span><span className="text-xs text-muted-foreground">{c.intent} · {c.format} · v{c.version}{c.scheduled_for ? ` · ${dt(c.scheduled_for)}` : ""}</span></li>)}
        {data.contents.length === 0 && <li className="p-4 text-sm text-muted-foreground" data-testid="growth-contents-empty">Aucun contenu. Créez une idée ou partez d'une action du plan.</li>}</ul>
      <div className="surface p-3 text-xs" data-testid="growth-calendar"><p className="overline mb-1">Calendrier 30 jours</p>{upcoming.length === 0 && <p className="text-muted-foreground">Rien de programmé.</p>}{upcoming.map((d) => <div key={d.date} className="border-t py-1"><p className="num font-medium">{d.date}</p>{d.items.map((i) => <p key={i.content_id} className="truncate">· {i.title || i.topic} <span className="text-muted-foreground">({STATUS_FR[i.status]})</span></p>)}</div>)}</div>
    </div>
    {!openId && <Empty>Cliquez sur un contenu pour ouvrir l'éditeur (brief, rédaction, contrôles, versions, publication).</Empty>}
  </div>;
}
