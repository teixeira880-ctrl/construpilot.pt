import { useState } from "react";
import { toast } from "sonner";
import { Megaphone, Mail, Check, X, Download, Send, Eye, Wand2, Upload, ExternalLink as ExternalLinkIcon, KeyRound } from "lucide-react";
import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { useApi, err, dt } from "./lib";
import { Empty, ErrorBox } from "./Bits";

const ST = { published: ["publicada", "bg-emerald-500/15 text-emerald-700"], proposed: ["a aprovar", "bg-amber-500/15 text-amber-700"], approved: ["aprovada", "bg-emerald-500/15 text-emerald-700"], rejected: ["recusada", "bg-muted"], sent: ["enviada", "bg-emerald-500/15 text-emerald-700"], sending: ["envoi…", "bg-sky-500/15"] };
const Status = ({ s }) => <Badge className={`rounded-sm border-0 ${(ST[s] || ["", "bg-muted"])[1]}`}>{(ST[s] || [s])[0]}</Badge>;
const dl = async (path, name) => { const r = await api.get(path, { responseType: "blob" }); const u = URL.createObjectURL(r.data); const a = document.createElement("a"); a.href = u; a.download = name; a.click(); URL.revokeObjectURL(u); };

function AdCard({ ad, canEdit, isAdmin, connectors, onChange }) {
  const g = ad.platforms.google, m = ad.platforms.meta, li = ad.platforms.linkedin;
  const decide = async (status) => { try { await api.put(`/growth/ads/${ad.ad_id}`, { status }); toast.success(status === "approved" ? "Anúncios aprovados" : "Anúncios recusados"); onChange(); } catch (e) { toast.error(err(e)); } };
  const publish = async (platform) => {
    const b = window.prompt(`Orçamento diário (€) para a campanha ${platform === "google" ? "Google Ads" : "Meta"} — criada EM PAUSA, a ativar depois no ${platform === "google" ? "Google Ads" : "Gestor de anúncios"}`, "10");
    if (b === null) return;
    try { const r = await api.post(`/growth/ads/${ad.ad_id}/publish`, { platform, daily_budget_eur: Number(b) || 10 }); toast.success(`Campanha criada em pausa — ${r.data.manage_url ? "abra a ligação de gestão para a ativar" : "ok"}`); onChange(); } catch (e) { toast.error(err(e)); }
  };
  const pubs = ad.publications || [];
  return <li className="surface p-3 text-sm space-y-2" data-testid={`growth-ad-${ad.ad_id}`}>
    <div className="flex flex-wrap items-center gap-2"><Status s={ad.status} /><strong className="flex-1 min-w-[200px]">{ad.title}</strong><span className="text-xs text-muted-foreground">{dt(ad.created_at)}</span></div>
    {ad.missing?.length > 0 && <p className="text-xs text-red-700">{ad.missing.join(" · ")}</p>}
    <div className="grid md:grid-cols-3 gap-3 text-xs">
      <div><p className="font-semibold mb-1">Google Ads (RSA) · {g.headlines.length} títulos · {g.descriptions.length} descriptions</p><ul className="space-y-0.5">{g.headlines.map((h) => <li key={h} className="flex justify-between gap-2"><span>{h}</span><span className="num text-muted-foreground">{h.length}</span></li>)}</ul><p className="mt-1 text-muted-foreground">{g.descriptions.map((d) => <span key={d} className="block">— {d} <span className="num">({d.length})</span></span>)}</p><p className="mt-1 text-muted-foreground">Palavras-chave: {g.keywords.join(", ")}</p></div>
      <div><p className="font-semibold mb-1">Meta / Instagram · CTA {m.cta}</p>{m.primary_texts.map((t) => <p key={t} className="mb-1">{t} <span className="num text-muted-foreground">({t.length})</span></p>)}<p className="text-muted-foreground">Títulos: {m.headlines.join(" · ")}</p><p className="text-muted-foreground">Descrições: {m.descriptions.join(" · ")}</p></div>
      <div><p className="font-semibold mb-1">LinkedIn</p>{li.intros.map((t) => <p key={t} className="mb-1">{t}</p>)}<p className="text-muted-foreground">Títulos: {li.headlines.join(" · ")}</p></div>
    </div>
    <div className="flex flex-wrap gap-2 items-center">
      {canEdit && ad.status === "proposed" && <><Button size="sm" className="h-7 text-xs" onClick={() => decide("approved")} data-testid={`growth-ad-approve-${ad.ad_id}`}><Check className="h-3.5 w-3.5" /> Aprovar</Button><Button size="sm" variant="ghost" className="h-7 text-xs" onClick={() => decide("rejected")}><X className="h-3.5 w-3.5" /> Recusar</Button></>}
      {ad.status === "approved" && <>
        <Button size="sm" variant="outline" className="h-7 text-xs" onClick={() => dl(`/growth/ads/${ad.ad_id}/export.csv?platform=google`, `google-${ad.ad_id}.csv`)} data-testid={`growth-ad-csv-google-${ad.ad_id}`}><Download className="h-3.5 w-3.5" /> CSV Google Ads Editor</Button>
        <Button size="sm" variant="outline" className="h-7 text-xs" onClick={() => dl(`/growth/ads/${ad.ad_id}/export.csv?platform=meta`, `meta-${ad.ad_id}.csv`)} data-testid={`growth-ad-csv-meta-${ad.ad_id}`}><Download className="h-3.5 w-3.5" /> CSV Meta</Button>
        {isAdmin && ["google", "meta"].map((p) => { const done = pubs.find((x) => x.platform === p && !x.validate_only); return done
          ? <a key={p} className="text-xs underline inline-flex items-center gap-1" href={done.manage_url} target="_blank" rel="noreferrer" data-testid={`growth-ad-manage-${p}-${ad.ad_id}`}><ExternalLinkIcon /> Campanha {p === "google" ? "Google Ads" : "Meta"} criada (em pausa) — gerir</a>
          : <Button key={p} size="sm" variant="outline" className="h-7 text-xs" disabled={!connectors?.[p]?.configured} title={connectors?.[p]?.configured ? "" : `Conector não configurado: ${(connectors?.[p]?.missing || []).join(", ")}`} onClick={() => publish(p)} data-testid={`growth-ad-publish-${p}-${ad.ad_id}`}><Upload className="h-3.5 w-3.5" /> Publicar via API {p === "google" ? "Google Ads" : "Meta"}</Button>; })}
      </>}
      <a className="text-xs underline ml-auto" href={ad.final_url} target="_blank" rel="noreferrer">{ad.final_url}</a>
    </div>
  </li>;
}

function NewsletterCard({ nl, canEdit, isAdmin, subscribers, onChange }) {
  const [subject, setSubject] = useState(nl.subject);
  const [busy, setBusy] = useState("");
  const act = async (label, fn, ok) => { setBusy(label); try { await fn(); if (ok) toast.success(ok); onChange(); } catch (e) { toast.error(err(e)); } finally { setBusy(""); } };
  const editable = canEdit && nl.status === "proposed";
  return <li className="surface p-3 text-sm space-y-2" data-testid={`growth-newsletter-${nl.newsletter_id}`}>
    <div className="flex flex-wrap items-center gap-2"><Status s={nl.status} /><span className="text-xs text-muted-foreground">{nl.lang.toUpperCase()} · {nl.items.length} article(s) · {dt(nl.created_at)}</span>{nl.result && <span className="text-xs">enviada para {nl.result.sent}/{nl.result.recipients} subscritor(es)</span>}</div>
    {editable ? <Input value={subject} maxLength={60} onChange={(e) => setSubject(e.target.value)} onBlur={() => subject !== nl.subject && act("subj", () => api.put(`/growth/newsletters/${nl.newsletter_id}`, { subject }), "Assunto guardado")} data-testid={`growth-newsletter-subject-${nl.newsletter_id}`} /> : <p className="font-semibold">{nl.subject}</p>}
    <p className="text-xs text-muted-foreground">{nl.preheader}</p>
    <ul className="text-xs list-disc ml-5">{nl.items.map((i) => <li key={i.url}><a className="underline" href={i.url} target="_blank" rel="noreferrer">{i.title}</a> — {i.blurb}</li>)}</ul>
    <div className="flex flex-wrap gap-2 items-center">
      <Button size="sm" variant="outline" className="h-7 text-xs" onClick={() => act("prev", async () => { const r = await api.get(`/growth/newsletters/${nl.newsletter_id}/preview`, { responseType: "text" }); const w = window.open("", "_blank"); w.document.write(r.data); w.document.close(); })} data-testid={`growth-newsletter-preview-${nl.newsletter_id}`}><Eye className="h-3.5 w-3.5" /> Pré-visualização</Button>
      {canEdit && <Button size="sm" variant="outline" className="h-7 text-xs" disabled={!!busy} onClick={() => act("test", () => api.post(`/growth/newsletters/${nl.newsletter_id}/send`, { test: true }), "E-mail de teste enviado para o seu endereço")} data-testid={`growth-newsletter-test-${nl.newsletter_id}`}><Mail className="h-3.5 w-3.5" /> Enviar-me um teste</Button>}
      {editable && <><Button size="sm" className="h-7 text-xs" disabled={!!busy} onClick={() => act("ok", () => api.put(`/growth/newsletters/${nl.newsletter_id}`, { status: "approved" }), "Newsletter aprovada")} data-testid={`growth-newsletter-approve-${nl.newsletter_id}`}><Check className="h-3.5 w-3.5" /> Aprovar</Button>
        <Button size="sm" variant="ghost" className="h-7 text-xs" disabled={!!busy} onClick={() => act("ko", () => api.put(`/growth/newsletters/${nl.newsletter_id}`, { status: "rejected" }))}><X className="h-3.5 w-3.5" /> Recusar</Button></>}
      {isAdmin && nl.status === "approved" && <Button size="sm" className="h-7 text-xs" disabled={!!busy || !subscribers} onClick={() => window.confirm(`Enviar para ${subscribers} subscritor(es) ${nl.lang.toUpperCase()} ?`) && act("send", () => api.post(`/growth/newsletters/${nl.newsletter_id}/send`, { test: false }), "Envio efetuado")} data-testid={`growth-newsletter-send-${nl.newsletter_id}`}><Send className="h-3.5 w-3.5" /> Enviar aos {subscribers} subscritor(es)</Button>}
    </div>
  </li>;
}

export function MarketingPanel({ projectId, canEdit, isAdmin }) {
  const ads = useApi(`/growth/projects/${projectId}/ads`, [projectId]);
  const nls = useApi(`/growth/projects/${projectId}/newsletters`, [projectId]);
  const [busy, setBusy] = useState(false);
  const authGoogleAds = async () => { try { const r = await api.post("/growth/integrations/google/start", { project_id: projectId, provider: "google_ads" }); window.location.href = r.data.url; } catch (e) { toast.error(err(e)); } };
  const testMeta = async () => { try { const r = await api.post(`/growth/projects/${projectId}/ads/connectors/meta/test`); toast.success(`Meta OK : ${r.data.account?.name} (${r.data.account?.currency})${r.data.missing_scopes?.length ? " — permissões em falta: " + r.data.missing_scopes.join(", ") : ""}`); } catch (e) { toast.error(err(e)); } };
  const genNl = async () => { setBusy(true); try { await api.post(`/growth/projects/${projectId}/newsletters/generate`, { content_ids: [] }); toast.success("Newsletter proposta"); nls.reload(); } catch (e) { toast.error(err(e)); } finally { setBusy(false); } };
  if (ads.error) return <ErrorBox error={ads.error} onRetry={ads.reload} />;
  if (!ads.data || !nls.data) return null;
  const c = ads.data.connectors;
  return <div className="space-y-6" data-testid="growth-marketing">
    <section className="space-y-2">
      <div className="flex flex-wrap items-center gap-2"><h3 className="font-semibold flex items-center gap-2"><Megaphone className="h-4 w-4" /> Anúncios ({ads.data.ads.length})</h3>
        <p className="text-xs text-muted-foreground flex-1">Gerados automaticamente em cada artigo publicado (Google Ads RSA 15×30 / 4×90, Meta, LinkedIn). Aprove e depois exporte em CSV ou publique via API.</p></div>
      <div className="surface p-3 text-xs space-y-2" data-testid="growth-ads-connectors">
        <p className="font-semibold flex items-center gap-1"><KeyRound className="h-3.5 w-3.5" /> Conectores de publicação direta (campanhas criadas EM PAUSA, ativação manual na plataforma)</p>
        <div className="flex flex-wrap items-center gap-2">Google Ads <Badge variant="outline" className="rounded-sm">{c.google.configured ? "pronto" : `não configurado (${c.google.missing.join(", ")})`}</Badge>
          {isAdmin && <Button size="sm" variant="outline" className="h-7 text-xs" onClick={authGoogleAds} data-testid="growth-ads-google-auth">{c.google.oauth_connected ? "Reautorizar Google Ads" : "Autorizar Google Ads"}</Button>}
          {c.google.customer_id && <span className="text-muted-foreground">compte {c.google.customer_id}</span>}</div>
        <p className="text-muted-foreground">{c.google.how_to}</p>
        <div className="flex flex-wrap items-center gap-2">Meta <Badge variant="outline" className="rounded-sm">{c.meta.configured ? "pronto" : `não configurado (${c.meta.missing.join(", ")})`}</Badge>
          {isAdmin && c.meta.configured && <Button size="sm" variant="outline" className="h-7 text-xs" onClick={testMeta} data-testid="growth-ads-meta-test">Testar o token Meta</Button>}
          {c.meta.ad_account_id && <span className="text-muted-foreground">{c.meta.ad_account_id} · page {c.meta.page_id}</span>}</div>
        <p className="text-muted-foreground">{c.meta.how_to}</p>
      </div>
      {ads.data.ads.length === 0 && <Empty testid="growth-ads-empty">Nenhum anúncio: publique um artigo (ou lance um ciclo de piloto automático) para os gerar.</Empty>}
      <ul className="space-y-2">{ads.data.ads.map((a) => <AdCard key={a.ad_id} ad={a} canEdit={canEdit} isAdmin={isAdmin} connectors={c} onChange={ads.reload} />)}</ul>
    </section>
    <section className="space-y-2">
      <div className="flex flex-wrap items-center gap-2"><h3 className="font-semibold flex items-center gap-2"><Mail className="h-4 w-4" /> Newsletters ({nls.data.newsletters.length}) · {nls.data.subscribers} subscritor(es)</h3>
        <p className="text-xs text-muted-foreground flex-1">Resumo proposto todas as segundas-feiras a partir dos artigos publicados; envio via Resend após aprovação (ligação de cancelamento incluída).</p>
        {canEdit && <Button size="sm" variant="outline" onClick={genNl} disabled={busy} data-testid="growth-newsletter-generate"><Wand2 className="h-4 w-4" /> Propor uma newsletter</Button>}</div>
      {nls.data.newsletters.length === 0 && <Empty testid="growth-newsletters-empty">Nenhuma newsletter proposta por agora.</Empty>}
      <ul className="space-y-2">{nls.data.newsletters.map((n) => <NewsletterCard key={n.newsletter_id} nl={n} canEdit={canEdit} isAdmin={isAdmin} subscribers={nls.data.subscribers} onChange={nls.reload} />)}</ul>
    </section>
  </div>;
}
