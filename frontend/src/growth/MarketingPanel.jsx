import { useState } from "react";
import { toast } from "sonner";
import { Megaphone, Mail, Check, X, Download, Send, Eye, Wand2, Upload, ExternalLink as ExternalLinkIcon, KeyRound } from "lucide-react";
import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { useApi, err, dt } from "./lib";
import { Empty, ErrorBox } from "./Bits";

const ST = { published: ["publiée", "bg-emerald-500/15 text-emerald-700"], proposed: ["à approuver", "bg-amber-500/15 text-amber-700"], approved: ["approuvée", "bg-emerald-500/15 text-emerald-700"], rejected: ["refusée", "bg-muted"], sent: ["envoyée", "bg-emerald-500/15 text-emerald-700"], sending: ["envoi…", "bg-sky-500/15"] };
const Status = ({ s }) => <Badge className={`rounded-sm border-0 ${(ST[s] || ["", "bg-muted"])[1]}`}>{(ST[s] || [s])[0]}</Badge>;
const dl = async (path, name) => { const r = await api.get(path, { responseType: "blob" }); const u = URL.createObjectURL(r.data); const a = document.createElement("a"); a.href = u; a.download = name; a.click(); URL.revokeObjectURL(u); };

function AdCard({ ad, canEdit, isAdmin, connectors, onChange }) {
  const g = ad.platforms.google, m = ad.platforms.meta, li = ad.platforms.linkedin;
  const decide = async (status) => { try { await api.put(`/growth/ads/${ad.ad_id}`, { status }); toast.success(status === "approved" ? "Annonces approuvées" : "Annonces refusées"); onChange(); } catch (e) { toast.error(err(e)); } };
  const publish = async (platform) => {
    const b = window.prompt(`Budget quotidien (€) pour la campagne ${platform === "google" ? "Google Ads" : "Meta"} — créée EN PAUSE, à activer ensuite dans ${platform === "google" ? "Google Ads" : "le Gestionnaire de publicités"}`, "10");
    if (b === null) return;
    try { const r = await api.post(`/growth/ads/${ad.ad_id}/publish`, { platform, daily_budget_eur: Number(b) || 10 }); toast.success(`Campagne créée en pause — ${r.data.manage_url ? "ouvrez le lien de gestion pour l'activer" : "ok"}`); onChange(); } catch (e) { toast.error(err(e)); }
  };
  const pubs = ad.publications || [];
  return <li className="surface p-3 text-sm space-y-2" data-testid={`growth-ad-${ad.ad_id}`}>
    <div className="flex flex-wrap items-center gap-2"><Status s={ad.status} /><strong className="flex-1 min-w-[200px]">{ad.title}</strong><span className="text-xs text-muted-foreground">{dt(ad.created_at)}</span></div>
    {ad.missing?.length > 0 && <p className="text-xs text-red-700">{ad.missing.join(" · ")}</p>}
    <div className="grid md:grid-cols-3 gap-3 text-xs">
      <div><p className="font-semibold mb-1">Google Ads (RSA) · {g.headlines.length} titres · {g.descriptions.length} descriptions</p><ul className="space-y-0.5">{g.headlines.map((h) => <li key={h} className="flex justify-between gap-2"><span>{h}</span><span className="num text-muted-foreground">{h.length}</span></li>)}</ul><p className="mt-1 text-muted-foreground">{g.descriptions.map((d) => <span key={d} className="block">— {d} <span className="num">({d.length})</span></span>)}</p><p className="mt-1 text-muted-foreground">Mots-clés : {g.keywords.join(", ")}</p></div>
      <div><p className="font-semibold mb-1">Meta / Instagram · CTA {m.cta}</p>{m.primary_texts.map((t) => <p key={t} className="mb-1">{t} <span className="num text-muted-foreground">({t.length})</span></p>)}<p className="text-muted-foreground">Titres : {m.headlines.join(" · ")}</p><p className="text-muted-foreground">Descriptions : {m.descriptions.join(" · ")}</p></div>
      <div><p className="font-semibold mb-1">LinkedIn</p>{li.intros.map((t) => <p key={t} className="mb-1">{t}</p>)}<p className="text-muted-foreground">Titres : {li.headlines.join(" · ")}</p></div>
    </div>
    <div className="flex flex-wrap gap-2 items-center">
      {canEdit && ad.status === "proposed" && <><Button size="sm" className="h-7 text-xs" onClick={() => decide("approved")} data-testid={`growth-ad-approve-${ad.ad_id}`}><Check className="h-3.5 w-3.5" /> Approuver</Button><Button size="sm" variant="ghost" className="h-7 text-xs" onClick={() => decide("rejected")}><X className="h-3.5 w-3.5" /> Refuser</Button></>}
      {ad.status === "approved" && <>
        <Button size="sm" variant="outline" className="h-7 text-xs" onClick={() => dl(`/growth/ads/${ad.ad_id}/export.csv?platform=google`, `google-${ad.ad_id}.csv`)} data-testid={`growth-ad-csv-google-${ad.ad_id}`}><Download className="h-3.5 w-3.5" /> CSV Google Ads Editor</Button>
        <Button size="sm" variant="outline" className="h-7 text-xs" onClick={() => dl(`/growth/ads/${ad.ad_id}/export.csv?platform=meta`, `meta-${ad.ad_id}.csv`)} data-testid={`growth-ad-csv-meta-${ad.ad_id}`}><Download className="h-3.5 w-3.5" /> CSV Meta</Button>
        {isAdmin && ["google", "meta"].map((p) => { const done = pubs.find((x) => x.platform === p && !x.validate_only); return done
          ? <a key={p} className="text-xs underline inline-flex items-center gap-1" href={done.manage_url} target="_blank" rel="noreferrer" data-testid={`growth-ad-manage-${p}-${ad.ad_id}`}><ExternalLinkIcon /> Campagne {p === "google" ? "Google Ads" : "Meta"} créée (en pause) — gérer</a>
          : <Button key={p} size="sm" variant="outline" className="h-7 text-xs" disabled={!connectors?.[p]?.configured} title={connectors?.[p]?.configured ? "" : `Connecteur non configuré : ${(connectors?.[p]?.missing || []).join(", ")}`} onClick={() => publish(p)} data-testid={`growth-ad-publish-${p}-${ad.ad_id}`}><Upload className="h-3.5 w-3.5" /> Publier via API {p === "google" ? "Google Ads" : "Meta"}</Button>; })}
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
    <div className="flex flex-wrap items-center gap-2"><Status s={nl.status} /><span className="text-xs text-muted-foreground">{nl.lang.toUpperCase()} · {nl.items.length} article(s) · {dt(nl.created_at)}</span>{nl.result && <span className="text-xs">envoyée à {nl.result.sent}/{nl.result.recipients} abonné(s)</span>}</div>
    {editable ? <Input value={subject} maxLength={60} onChange={(e) => setSubject(e.target.value)} onBlur={() => subject !== nl.subject && act("subj", () => api.put(`/growth/newsletters/${nl.newsletter_id}`, { subject }), "Objet enregistré")} data-testid={`growth-newsletter-subject-${nl.newsletter_id}`} /> : <p className="font-semibold">{nl.subject}</p>}
    <p className="text-xs text-muted-foreground">{nl.preheader}</p>
    <ul className="text-xs list-disc ml-5">{nl.items.map((i) => <li key={i.url}><a className="underline" href={i.url} target="_blank" rel="noreferrer">{i.title}</a> — {i.blurb}</li>)}</ul>
    <div className="flex flex-wrap gap-2 items-center">
      <Button size="sm" variant="outline" className="h-7 text-xs" onClick={() => act("prev", async () => { const r = await api.get(`/growth/newsletters/${nl.newsletter_id}/preview`, { responseType: "text" }); const w = window.open("", "_blank"); w.document.write(r.data); w.document.close(); })} data-testid={`growth-newsletter-preview-${nl.newsletter_id}`}><Eye className="h-3.5 w-3.5" /> Aperçu</Button>
      {canEdit && <Button size="sm" variant="outline" className="h-7 text-xs" disabled={!!busy} onClick={() => act("test", () => api.post(`/growth/newsletters/${nl.newsletter_id}/send`, { test: true }), "E-mail de test envoyé à votre adresse")} data-testid={`growth-newsletter-test-${nl.newsletter_id}`}><Mail className="h-3.5 w-3.5" /> M'envoyer un test</Button>}
      {editable && <><Button size="sm" className="h-7 text-xs" disabled={!!busy} onClick={() => act("ok", () => api.put(`/growth/newsletters/${nl.newsletter_id}`, { status: "approved" }), "Newsletter approuvée")} data-testid={`growth-newsletter-approve-${nl.newsletter_id}`}><Check className="h-3.5 w-3.5" /> Approuver</Button>
        <Button size="sm" variant="ghost" className="h-7 text-xs" disabled={!!busy} onClick={() => act("ko", () => api.put(`/growth/newsletters/${nl.newsletter_id}`, { status: "rejected" }))}><X className="h-3.5 w-3.5" /> Refuser</Button></>}
      {isAdmin && nl.status === "approved" && <Button size="sm" className="h-7 text-xs" disabled={!!busy || !subscribers} onClick={() => window.confirm(`Envoyer à ${subscribers} abonné(s) ${nl.lang.toUpperCase()} ?`) && act("send", () => api.post(`/growth/newsletters/${nl.newsletter_id}/send`, { test: false }), "Envoi effectué")} data-testid={`growth-newsletter-send-${nl.newsletter_id}`}><Send className="h-3.5 w-3.5" /> Envoyer aux {subscribers} abonné(s)</Button>}
    </div>
  </li>;
}

export function MarketingPanel({ projectId, canEdit, isAdmin }) {
  const ads = useApi(`/growth/projects/${projectId}/ads`, [projectId]);
  const nls = useApi(`/growth/projects/${projectId}/newsletters`, [projectId]);
  const [busy, setBusy] = useState(false);
  const authGoogleAds = async () => { try { const r = await api.post("/growth/integrations/google/start", { project_id: projectId, provider: "google_ads" }); window.location.href = r.data.url; } catch (e) { toast.error(err(e)); } };
  const testMeta = async () => { try { const r = await api.post(`/growth/projects/${projectId}/ads/connectors/meta/test`); toast.success(`Meta OK : ${r.data.account?.name} (${r.data.account?.currency})${r.data.missing_scopes?.length ? " — permissions manquantes : " + r.data.missing_scopes.join(", ") : ""}`); } catch (e) { toast.error(err(e)); } };
  const genNl = async () => { setBusy(true); try { await api.post(`/growth/projects/${projectId}/newsletters/generate`, { content_ids: [] }); toast.success("Newsletter proposée"); nls.reload(); } catch (e) { toast.error(err(e)); } finally { setBusy(false); } };
  if (ads.error) return <ErrorBox error={ads.error} onRetry={ads.reload} />;
  if (!ads.data || !nls.data) return null;
  const c = ads.data.connectors;
  return <div className="space-y-6" data-testid="growth-marketing">
    <section className="space-y-2">
      <div className="flex flex-wrap items-center gap-2"><h3 className="font-semibold flex items-center gap-2"><Megaphone className="h-4 w-4" /> Publicités ({ads.data.ads.length})</h3>
        <p className="text-xs text-muted-foreground flex-1">Générées automatiquement à chaque article publié (Google Ads RSA 15×30 / 4×90, Meta, LinkedIn). Approuvez puis exportez en CSV ou publiez via API.</p></div>
      <div className="surface p-3 text-xs space-y-2" data-testid="growth-ads-connectors">
        <p className="font-semibold flex items-center gap-1"><KeyRound className="h-3.5 w-3.5" /> Connecteurs de publication directe (campagnes créées EN PAUSE, activation manuelle sur la plateforme)</p>
        <div className="flex flex-wrap items-center gap-2">Google Ads <Badge variant="outline" className="rounded-sm">{c.google.configured ? "prêt" : `non configuré (${c.google.missing.join(", ")})`}</Badge>
          {isAdmin && <Button size="sm" variant="outline" className="h-7 text-xs" onClick={authGoogleAds} data-testid="growth-ads-google-auth">{c.google.oauth_connected ? "Ré-autoriser Google Ads" : "Autoriser Google Ads"}</Button>}
          {c.google.customer_id && <span className="text-muted-foreground">compte {c.google.customer_id}</span>}</div>
        <p className="text-muted-foreground">{c.google.how_to}</p>
        <div className="flex flex-wrap items-center gap-2">Meta <Badge variant="outline" className="rounded-sm">{c.meta.configured ? "prêt" : `non configuré (${c.meta.missing.join(", ")})`}</Badge>
          {isAdmin && c.meta.configured && <Button size="sm" variant="outline" className="h-7 text-xs" onClick={testMeta} data-testid="growth-ads-meta-test">Tester le jeton Meta</Button>}
          {c.meta.ad_account_id && <span className="text-muted-foreground">{c.meta.ad_account_id} · page {c.meta.page_id}</span>}</div>
        <p className="text-muted-foreground">{c.meta.how_to}</p>
      </div>
      {ads.data.ads.length === 0 && <Empty testid="growth-ads-empty">Aucune annonce : publiez un article (ou lancez un cycle auto-pilote) pour en générer.</Empty>}
      <ul className="space-y-2">{ads.data.ads.map((a) => <AdCard key={a.ad_id} ad={a} canEdit={canEdit} isAdmin={isAdmin} connectors={c} onChange={ads.reload} />)}</ul>
    </section>
    <section className="space-y-2">
      <div className="flex flex-wrap items-center gap-2"><h3 className="font-semibold flex items-center gap-2"><Mail className="h-4 w-4" /> Newsletters ({nls.data.newsletters.length}) · {nls.data.subscribers} abonné(s)</h3>
        <p className="text-xs text-muted-foreground flex-1">Digest proposé chaque lundi à partir des articles publiés ; envoi via Resend après approbation (lien de désabonnement inclus).</p>
        {canEdit && <Button size="sm" variant="outline" onClick={genNl} disabled={busy} data-testid="growth-newsletter-generate"><Wand2 className="h-4 w-4" /> Proposer une newsletter</Button>}</div>
      {nls.data.newsletters.length === 0 && <Empty testid="growth-newsletters-empty">Aucune newsletter proposée pour l'instant.</Empty>}
      <ul className="space-y-2">{nls.data.newsletters.map((n) => <NewsletterCard key={n.newsletter_id} nl={n} canEdit={canEdit} isAdmin={isAdmin} subscribers={nls.data.subscribers} onChange={nls.reload} />)}</ul>
    </section>
  </div>;
}
