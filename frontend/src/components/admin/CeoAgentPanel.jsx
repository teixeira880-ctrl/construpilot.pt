import { useEffect, useState } from "react";
import { toast } from "sonner";
import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import {
  Bot, FileText, ImageIcon, CalendarDays, Loader2, Check, X, Eye, Sparkles, ShieldCheck,
  Mail, Megaphone, Copy, Send, Video, Clapperboard,
} from "lucide-react";

const BACKEND = process.env.REACT_APP_BACKEND_URL;
const AUDIENCES = [{ k: "particuliers", label: "Particuliers" }, { k: "pros", label: "Pros / artisans" }];
const FORMATS = [{ k: "flyer", label: "Flyer A4" }, { k: "social", label: "Redes (quadrado)" }, { k: "ad_banner", label: "Banner publicitário" }];
const EMAIL_TYPES = [{ k: "promo", label: "Promo" }, { k: "newsletter", label: "Newsletter" }, { k: "nurture", label: "Sequência (3)" }];
const EMAIL_TYPE_LABEL = { promo: "Promotionnel", newsletter: "Newsletter", nurture: "Sequência nurture" };
const STATUS_CLS = {
  draft: "bg-amber-500/15 text-amber-600 border-amber-500/30",
  published: "bg-emerald-500/15 text-emerald-600 border-emerald-500/30",
  approved: "bg-emerald-500/15 text-emerald-600 border-emerald-500/30",
  rejected: "bg-destructive/15 text-destructive border-destructive/30",
};

const Seg = ({ value, onChange, options, testid }) => (
  <div className="inline-flex rounded-md border border-border overflow-hidden" data-testid={testid}>
    {options.map((o) => (
      <button key={o.k} type="button" onClick={() => onChange(o.k)}
        className={`px-3 py-1.5 text-xs font-semibold ${value === o.k ? "bg-primary text-primary-foreground" : "bg-card hover:bg-secondary/50"}`}>
        {o.label}
      </button>
    ))}
  </div>
);

const Badge = ({ s }) => (
  <span className={`inline-flex items-center rounded-full border px-2 py-0.5 text-[10px] font-semibold uppercase ${STATUS_CLS[s] || "bg-muted text-muted-foreground border-border"}`}>{s}</span>
);

const copyText = (txt) => {
  try { navigator.clipboard.writeText(txt); toast.success("Copiado"); } catch { /* */ }
};

export default function CeoAgentPanel() {
  const [blog, setBlog] = useState({ topic: "", audience: "particuliers", keywords: "", with_image: true, loading: false });
  const [creative, setCreative] = useState({ brief: "", format: "flyer", audience: "particuliers", loading: false });
  const [email, setEmail] = useState({ topic: "", email_type: "promo", audience: "particuliers", loading: false });
  const [ad, setAd] = useState({ brief: "", audience: "particuliers", loading: false });
  const [video, setVideo] = useState({ brief: "", audience: "particuliers", duration: 30, loading: false });
  const [calendar, setCalendar] = useState([]);
  const [drafts, setDrafts] = useState({ blog: [], assets: [], emails: [], ads: [], videos: [] });
  const [preview, setPreview] = useState(null);     // blog article
  const [copyPreview, setCopyPreview] = useState(null); // email / ad
  const [busy, setBusy] = useState("");

  const load = async () => {
    try {
      const [d, c] = await Promise.all([api.get("/ceo/drafts"), api.get("/ceo/calendar")]);
      setDrafts({ blog: [], assets: [], emails: [], ads: [], videos: [], ...(d.data || {}) });
      setCalendar(c.data?.slots || []);
    } catch { /* */ }
  };
  useEffect(() => { load(); }, []);

  const genBlog = async (override) => {
    const payload = override || { topic: blog.topic, audience: blog.audience,
      keywords: blog.keywords ? blog.keywords.split(",").map((s) => s.trim()).filter(Boolean) : [], with_image: blog.with_image };
    if (!payload.topic || payload.topic.length < 3) return toast.error("Indique um assunto");
    setBlog((b) => ({ ...b, loading: true }));
    try {
      const { data } = await api.post("/ceo/blog/draft", payload);
      toast.success("Rascunho de artigo gerado", { description: data.warnings?.length ? data.warnings.join(" ") : "Pronto a rever e publicar." });
      if (!override) setBlog((b) => ({ ...b, topic: "", keywords: "" }));
      load();
    } catch (e) { toast.error(e?.response?.data?.detail || "Impossível gerar"); }
    finally { setBlog((b) => ({ ...b, loading: false })); }
  };

  const genCreative = async () => {
    if (!creative.brief || creative.brief.length < 3) return toast.error("Descreva o visual pretendido");
    setCreative((c) => ({ ...c, loading: true }));
    try {
      await api.post("/ceo/creative", { brief: creative.brief, format: creative.format, audience: creative.audience });
      toast.success("Visual gerado", { description: "A rever e aprovar abaixo." });
      setCreative((c) => ({ ...c, brief: "" }));
      load();
    } catch (e) { toast.error(e?.response?.data?.detail || "Impossível gerar"); }
    finally { setCreative((c) => ({ ...c, loading: false })); }
  };

  const genEmail = async () => {
    if (!email.topic || email.topic.length < 3) return toast.error("Indique o assunto da campanha");
    setEmail((s) => ({ ...s, loading: true }));
    try {
      await api.post("/ceo/email/draft", { topic: email.topic, email_type: email.email_type, audience: email.audience });
      toast.success("Rascunho de e-mail gerado", { description: "A rever e aprovar abaixo." });
      setEmail((s) => ({ ...s, topic: "" }));
      load();
    } catch (e) { toast.error(e?.response?.data?.detail || "Impossível gerar"); }
    finally { setEmail((s) => ({ ...s, loading: false })); }
  };

  const genAd = async () => {
    if (!ad.brief || ad.brief.length < 3) return toast.error("Descreva o anúncio pretendido");
    setAd((s) => ({ ...s, loading: true }));
    try {
      await api.post("/ceo/ad/draft", { brief: ad.brief, audience: ad.audience });
      toast.success("Textos de anúncios gerados", { description: "A rever e aprovar abaixo." });
      setAd((s) => ({ ...s, brief: "" }));
      load();
    } catch (e) { toast.error(e?.response?.data?.detail || "Impossível gerar"); }
    finally { setAd((s) => ({ ...s, loading: false })); }
  };

  const genVideo = async () => {
    if (!video.brief || video.brief.length < 3) return toast.error("Descreva o vídeo pretendido");
    setVideo((s) => ({ ...s, loading: true }));
    try {
      await api.post("/ceo/video/draft", { brief: video.brief, audience: video.audience, duration: video.duration });
      toast.success("Guião trilingue gerado", { description: "Storyboard (4 imagens) a ser gerado…" });
      setVideo((s) => ({ ...s, brief: "" }));
      load(); setTimeout(load, 8000); setTimeout(load, 18000);
    } catch (e) { toast.error(e?.response?.data?.detail || "Impossível gerar"); }
    finally { setVideo((s) => ({ ...s, loading: false })); }
  };

  const sendTest = async (id) => {
    setBusy(id);
    try { const { data } = await api.post(`/ceo/email/${id}/test`, {}); toast.success("E-mail de teste enviado", { description: `À ${data.to}` }); }
    catch (e) { toast.error(e?.response?.data?.detail || "Envio do teste impossível"); }
    finally { setBusy(""); }
  };

  const sendCampaign = async (id) => {
    if (!window.confirm("Enviar esta campanha a todos os subscritores ativos da newsletter?")) return;
    setBusy(id);
    try {
      const { data } = await api.post(`/ceo/email/${id}/send`);
      toast.success("Envio lançado", { description: `${data.total} destinataire(s) — suivi ci-dessous.` });
      load(); setTimeout(load, 4000); setTimeout(load, 10000);
    } catch (e) { toast.error(e?.response?.data?.detail || "Envio impossível"); }
    finally { setBusy(""); }
  };

  const act = async (url, okMsg) => {
    setBusy(url);
    try { await api.post(url); toast.success(okMsg); load(); }
    catch (e) { toast.error(e?.response?.data?.detail || "Ação impossível"); }
    finally { setBusy(""); }
  };

  const AdBlock = ({ title, groups }) => (
    <div className="rounded-lg border border-border p-3">
      <p className="text-xs font-bold uppercase tracking-wide text-primary mb-2">{title}</p>
      {Object.entries(groups || {}).filter(([, v]) => Array.isArray(v) && v.length).map(([key, arr]) => (
        <div key={key} className="mb-2">
          <p className="text-[10px] uppercase text-muted-foreground mb-1">{key}</p>
          <ul className="space-y-1">
            {arr.map((line, i) => (
              <li key={i} className="flex items-start gap-2 text-sm">
                <button type="button" onClick={() => copyText(line)} className="mt-0.5 text-muted-foreground hover:text-primary shrink-0"><Copy className="h-3 w-3" /></button>
                <span>{line}</span>
              </li>
            ))}
          </ul>
        </div>
      ))}
    </div>
  );

  return (
    <div className="space-y-8" data-testid="ceo-agent-panel">
      <div className="flex items-start gap-3">
        <span className="h-11 w-11 rounded-lg bg-primary/10 grid place-items-center shrink-0"><Bot className="h-6 w-6 text-primary" /></span>
        <div>
          <h2 className="font-display text-2xl font-bold">Agent CEO — Marketing</h2>
          <p className="text-sm text-muted-foreground max-w-2xl">
            O agente redige <strong>brouillons</strong> (artigos de blogue SEO, visuais, folhetos, e-mails e anúncios) a partir de um simples assunto. Modo supervisionado: nada é publicado enquanto não validar.
          </p>
          <p className="text-xs text-muted-foreground mt-1 flex items-center gap-1"><ShieldCheck className="h-3.5 w-3.5 text-emerald-600" /> Geração de imagens sujeita ao teto de custos (500 €).</p>
        </div>
      </div>

      {/* Générateurs */}
      <div className="grid lg:grid-cols-2 gap-5">
        <div className="rounded-xl border border-border bg-card p-5" data-testid="ceo-blog-generator">
          <h3 className="font-semibold flex items-center gap-2 mb-3"><FileText className="h-4 w-4 text-primary" /> Artigo de blogue</h3>
          <Input value={blog.topic} onChange={(e) => setBlog((b) => ({ ...b, topic: e.target.value }))} placeholder="Assunto — ex.: Remodelar uma casa de banho de 6 m²" className="mb-2" data-testid="ceo-blog-topic" />
          <Input value={blog.keywords} onChange={(e) => setBlog((b) => ({ ...b, keywords: e.target.value }))} placeholder="Palavras-chave (separadas por vírgulas)" className="mb-3" data-testid="ceo-blog-keywords" />
          <div className="flex items-center justify-between gap-3 flex-wrap">
            <Seg value={blog.audience} onChange={(k) => setBlog((b) => ({ ...b, audience: k }))} options={AUDIENCES} testid="ceo-blog-audience" />
            <label className="flex items-center gap-2 text-xs font-medium cursor-pointer">
              <input type="checkbox" checked={blog.with_image} onChange={(e) => setBlog((b) => ({ ...b, with_image: e.target.checked }))} data-testid="ceo-blog-withimage" /> Image hero
            </label>
          </div>
          <Button onClick={() => genBlog()} disabled={blog.loading} className="mt-4 gap-2" data-testid="ceo-blog-generate">
            {blog.loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Sparkles className="h-4 w-4" />} Gerar o rascunho
          </Button>
        </div>

        <div className="rounded-xl border border-border bg-card p-5" data-testid="ceo-creative-generator">
          <h3 className="font-semibold flex items-center gap-2 mb-3"><ImageIcon className="h-4 w-4 text-primary" /> Visuel / Flyer</h3>
          <Textarea rows={2} value={creative.brief} onChange={(e) => setCreative((c) => ({ ...c, brief: e.target.value }))} placeholder="Brief — ex.: Promoção estimativa de obras gratuita, tom tranquilizador" className="mb-3" data-testid="ceo-creative-brief" />
          <div className="flex items-center gap-3 flex-wrap">
            <Seg value={creative.format} onChange={(k) => setCreative((c) => ({ ...c, format: k }))} options={FORMATS} testid="ceo-creative-format" />
            <Seg value={creative.audience} onChange={(k) => setCreative((c) => ({ ...c, audience: k }))} options={AUDIENCES} testid="ceo-creative-audience" />
          </div>
          <Button onClick={genCreative} disabled={creative.loading} className="mt-4 gap-2" data-testid="ceo-creative-generate">
            {creative.loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Sparkles className="h-4 w-4" />} Gerar o visual
          </Button>
        </div>

        <div className="rounded-xl border border-border bg-card p-5" data-testid="ceo-email-generator">
          <h3 className="font-semibold flex items-center gap-2 mb-3"><Mail className="h-4 w-4 text-primary" /> Campagne e-mail</h3>
          <Input value={email.topic} onChange={(e) => setEmail((s) => ({ ...s, topic: e.target.value }))} placeholder="Assunto — ex.: Lançar a estimativa de obras gratuita" className="mb-3" data-testid="ceo-email-topic" />
          <div className="flex items-center gap-3 flex-wrap">
            <Seg value={email.email_type} onChange={(k) => setEmail((s) => ({ ...s, email_type: k }))} options={EMAIL_TYPES} testid="ceo-email-type" />
            <Seg value={email.audience} onChange={(k) => setEmail((s) => ({ ...s, audience: k }))} options={AUDIENCES} testid="ceo-email-audience" />
          </div>
          <Button onClick={genEmail} disabled={email.loading} className="mt-4 gap-2" data-testid="ceo-email-generate">
            {email.loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Sparkles className="h-4 w-4" />} Gerar os e-mails
          </Button>
        </div>

        <div className="rounded-xl border border-border bg-card p-5" data-testid="ceo-ad-generator">
          <h3 className="font-semibold flex items-center gap-2 mb-3"><Megaphone className="h-4 w-4 text-primary" /> Textes d'annonces</h3>
          <Textarea rows={2} value={ad.brief} onChange={(e) => setAd((s) => ({ ...s, brief: e.target.value }))} placeholder="Brief — ex.: Orçamentos de construção em 30 s, público profissionais" className="mb-3" data-testid="ceo-ad-brief" />
          <div className="flex items-center gap-3 flex-wrap">
            <Seg value={ad.audience} onChange={(k) => setAd((s) => ({ ...s, audience: k }))} options={AUDIENCES} testid="ceo-ad-audience" />
            <span className="text-[11px] text-muted-foreground">Google · Meta · LinkedIn</span>
          </div>
          <Button onClick={genAd} disabled={ad.loading} className="mt-4 gap-2" data-testid="ceo-ad-generate">
            {ad.loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Sparkles className="h-4 w-4" />} Gerar os anúncios
          </Button>
        </div>

        <div className="rounded-xl border border-border bg-card p-5" data-testid="ceo-video-generator">
          <h3 className="font-semibold flex items-center gap-2 mb-3"><Video className="h-4 w-4 text-primary" /> Guião de vídeo (PT/FR/EN)</h3>
          <Textarea rows={2} value={video.brief} onChange={(e) => setVideo((s) => ({ ...s, brief: e.target.value }))} placeholder="Brief — ex.: Anúncio 30s: estime as suas obras gratuitamente em 30 segundos" className="mb-3" data-testid="ceo-video-brief" />
          <div className="flex items-center gap-3 flex-wrap">
            <Seg value={video.audience} onChange={(k) => setVideo((s) => ({ ...s, audience: k }))} options={AUDIENCES} testid="ceo-video-audience" />
            <Seg value={video.duration} onChange={(k) => setVideo((s) => ({ ...s, duration: k }))} options={[{ k: 15, label: "15s" }, { k: 30, label: "30s" }, { k: 45, label: "45s" }, { k: 60, label: "60s" }]} testid="ceo-video-duration" />
            <span className="text-[11px] text-muted-foreground">+ 4 storyboards</span>
          </div>
          <Button onClick={genVideo} disabled={video.loading} className="mt-4 gap-2" data-testid="ceo-video-generate">
            {video.loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Clapperboard className="h-4 w-4" />} Gerar o guião
          </Button>
        </div>
      </div>

      {/* Calendrier éditorial */}
      <div>
        <h3 className="font-semibold flex items-center gap-2 mb-3"><CalendarDays className="h-4 w-4 text-primary" /> Calendário editorial</h3>
        <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-3" data-testid="ceo-calendar">
          {calendar.map((s, i) => (
            <div key={i} className="rounded-lg border border-border bg-card p-3">
              <p className="text-[10px] uppercase tracking-wide text-muted-foreground">{s.period} · {s.audience}</p>
              <p className="text-sm font-semibold mt-0.5">{s.title}</p>
              <Button size="sm" variant="outline" className="mt-2 gap-1" disabled={blog.loading}
                onClick={() => genBlog({ topic: s.title, audience: s.audience, keywords: s.keywords, with_image: true })}
                data-testid={`ceo-calendar-gen-${i}`}>
                <Sparkles className="h-3.5 w-3.5" /> Gerar o rascunho
              </Button>
            </div>
          ))}
        </div>
      </div>

      {/* Brouillons blog à valider */}
      <div>
        <h3 className="font-semibold mb-3">Artigos — rascunhos &amp; publicados</h3>
        {drafts.blog.length === 0 ? (
          <p className="text-sm text-muted-foreground rounded-lg border border-dashed border-border p-6 text-center">Nenhum artigo por agora.</p>
        ) : (
          <div className="space-y-2" data-testid="ceo-blog-list">
            {drafts.blog.map((a) => (
              <div key={a.autoseo_id} className="rounded-lg border border-border bg-card p-3 flex items-center gap-3 flex-wrap" data-testid={`ceo-blog-${a.autoseo_id}`}>
                {a.hero_image_url && <img src={`${BACKEND}${a.hero_image_url}`} alt="" className="h-12 w-20 object-cover rounded border border-border" />}
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2"><p className="font-semibold text-sm truncate">{a.title}</p><Badge s={a.status} /></div>
                  <p className="text-xs text-muted-foreground truncate">{a.meta_description}</p>
                </div>
                <Button size="sm" variant="ghost" onClick={() => setPreview(a)} data-testid={`ceo-blog-preview-${a.autoseo_id}`}><Eye className="h-3.5 w-3.5 mr-1" /> Relire</Button>
                {a.status !== "published" && (
                  <Button size="sm" onClick={() => act(`/ceo/blog/${a.autoseo_id}/publish`, "Artigo publicado no blogue")} disabled={busy.includes(a.autoseo_id)} data-testid={`ceo-blog-publish-${a.autoseo_id}`}>
                    <Check className="h-3.5 w-3.5 mr-1" /> Publier
                  </Button>
                )}
                {a.status !== "rejected" && (
                  <Button size="sm" variant="outline" onClick={() => act(`/ceo/blog/${a.autoseo_id}/reject`, "Rascunho rejeitado")} disabled={busy.includes(a.autoseo_id)} data-testid={`ceo-blog-reject-${a.autoseo_id}`}>
                    <X className="h-3.5 w-3.5" />
                  </Button>
                )}
              </div>
            ))}
          </div>
        )}
      </div>

      {/* E-mails à valider */}
      <div>
        <h3 className="font-semibold mb-3 flex items-center gap-2"><Mail className="h-4 w-4 text-primary" /> Campagnes e-mail — brouillons</h3>
        {drafts.emails.length === 0 ? (
          <p className="text-sm text-muted-foreground rounded-lg border border-dashed border-border p-6 text-center">Nenhuma campanha de e-mail por agora.</p>
        ) : (
          <div className="space-y-2" data-testid="ceo-email-list">
            {drafts.emails.map((a) => (
              <div key={a.copy_id} className="rounded-lg border border-border bg-card p-3 flex items-center gap-3 flex-wrap" data-testid={`ceo-email-${a.copy_id}`}>
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2 flex-wrap">
                    <p className="font-semibold text-sm truncate">{a.campaign_name}</p>
                    <Badge s={a.status} />
                    <span className="text-[10px] uppercase text-muted-foreground">{EMAIL_TYPE_LABEL[a.email_type] || a.email_type} · {a.audience}</span>
                  </div>
                  <p className="text-xs text-muted-foreground truncate">{(a.payload?.emails?.[0]?.subjects || [])[0] || ""} · {(a.payload?.emails || []).length} e-mail(s)</p>
                  {a.send_status && (
                    <p className="text-[11px] mt-0.5 font-medium text-emerald-600" data-testid={`ceo-email-sendstatus-${a.copy_id}`}>
                      {a.send_status === "sending" ? `Envoi en cours… ${a.send_count || 0}/${a.send_total || 0}`
                        : `Enviado a${a.send_count || 0}subscritor(es)${a.send_failed ? ` · ${a.send_failed}falha(s)` : ""}`}
                    </p>
                  )}
                </div>
                <Button size="sm" variant="ghost" onClick={() => setCopyPreview(a)} data-testid={`ceo-email-preview-${a.copy_id}`}><Eye className="h-3.5 w-3.5 mr-1" /> Relire</Button>
                {a.status !== "approved" && (
                  <Button size="sm" onClick={() => act(`/ceo/copy/${a.copy_id}/publish`, "E-mail aprovado")} disabled={busy.includes(a.copy_id)} data-testid={`ceo-email-approve-${a.copy_id}`}>
                    <Check className="h-3.5 w-3.5 mr-1" /> Approuver
                  </Button>
                )}
                {a.status === "approved" && (
                  <>
                    <Button size="sm" variant="outline" onClick={() => sendTest(a.copy_id)} disabled={busy.includes(a.copy_id)} data-testid={`ceo-email-test-${a.copy_id}`}>
                      <Send className="h-3.5 w-3.5 mr-1" /> Test
                    </Button>
                    <Button size="sm" onClick={() => sendCampaign(a.copy_id)} disabled={busy.includes(a.copy_id) || a.send_status === "sending"} data-testid={`ceo-email-send-${a.copy_id}`}>
                      {a.send_status === "sending" ? <Loader2 className="h-3.5 w-3.5 mr-1 animate-spin" /> : <Send className="h-3.5 w-3.5 mr-1" />}
                      {a.send_status === "sent" ? "Renvoyer" : "Enviar"}
                    </Button>
                  </>
                )}
                {a.status !== "rejected" && (
                  <Button size="sm" variant="outline" onClick={() => act(`/ceo/copy/${a.copy_id}/reject`, "Rascunho rejeitado")} disabled={busy.includes(a.copy_id)} data-testid={`ceo-email-reject-${a.copy_id}`}>
                    <X className="h-3.5 w-3.5" />
                  </Button>
                )}
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Annonces à valider */}
      <div>
        <h3 className="font-semibold mb-3 flex items-center gap-2"><Megaphone className="h-4 w-4 text-primary" /> Annonces — brouillons</h3>
        {drafts.ads.length === 0 ? (
          <p className="text-sm text-muted-foreground rounded-lg border border-dashed border-border p-6 text-center">Nenhum anúncio por agora.</p>
        ) : (
          <div className="space-y-2" data-testid="ceo-ad-list">
            {drafts.ads.map((a) => (
              <div key={a.copy_id} className="rounded-lg border border-border bg-card p-3 flex items-center gap-3 flex-wrap" data-testid={`ceo-ad-${a.copy_id}`}>
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2 flex-wrap">
                    <p className="font-semibold text-sm truncate">{a.campaign_name}</p>
                    <Badge s={a.status} />
                    <span className="text-[10px] uppercase text-muted-foreground">{a.audience}</span>
                  </div>
                  <p className="text-xs text-muted-foreground truncate">{a.brief}</p>
                </div>
                <Button size="sm" variant="ghost" onClick={() => setCopyPreview(a)} data-testid={`ceo-ad-preview-${a.copy_id}`}><Eye className="h-3.5 w-3.5 mr-1" /> Relire</Button>
                {a.status !== "approved" && (
                  <Button size="sm" onClick={() => act(`/ceo/copy/${a.copy_id}/publish`, "Anúncio aprovado")} disabled={busy.includes(a.copy_id)} data-testid={`ceo-ad-approve-${a.copy_id}`}>
                    <Check className="h-3.5 w-3.5 mr-1" /> Approuver
                  </Button>
                )}
                {a.status !== "rejected" && (
                  <Button size="sm" variant="outline" onClick={() => act(`/ceo/copy/${a.copy_id}/reject`, "Rascunho rejeitado")} disabled={busy.includes(a.copy_id)} data-testid={`ceo-ad-reject-${a.copy_id}`}>
                    <X className="h-3.5 w-3.5" />
                  </Button>
                )}
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Roteiros vidéo à valider */}
      <div>
        <h3 className="font-semibold mb-3 flex items-center gap-2"><Video className="h-4 w-4 text-primary" /> Guiões de vídeo — rascunhos</h3>
        {drafts.videos.length === 0 ? (
          <p className="text-sm text-muted-foreground rounded-lg border border-dashed border-border p-6 text-center">Nenhum guião de vídeo por agora.</p>
        ) : (
          <div className="space-y-2" data-testid="ceo-video-list">
            {drafts.videos.map((a) => {
              const sb = a.payload?.storyboard || [];
              const ready = sb.filter((f) => f.status === "ready").length;
              return (
                <div key={a.copy_id} className="rounded-lg border border-border bg-card p-3" data-testid={`ceo-video-${a.copy_id}`}>
                  <div className="flex items-center gap-3 flex-wrap">
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-2 flex-wrap">
                        <p className="font-semibold text-sm truncate">{a.campaign_name}</p>
                        <Badge s={a.status} />
                        <span className="text-[10px] uppercase text-muted-foreground">{a.payload?.duration_seconds || "?"}s · {(a.payload?.scenes || []).length} cenas · {a.audience}</span>
                      </div>
                      <p className="text-xs text-muted-foreground truncate">{a.brief} · storyboard {ready}/{sb.length || 4}</p>
                    </div>
                    <Button size="sm" variant="ghost" onClick={() => setCopyPreview(a)} data-testid={`ceo-video-preview-${a.copy_id}`}><Eye className="h-3.5 w-3.5 mr-1" /> Relire</Button>
                    {a.status !== "approved" && (
                      <Button size="sm" onClick={() => act(`/ceo/copy/${a.copy_id}/publish`, "Guião aprovado")} disabled={busy.includes(a.copy_id)} data-testid={`ceo-video-approve-${a.copy_id}`}>
                        <Check className="h-3.5 w-3.5 mr-1" /> Approuver
                      </Button>
                    )}
                    {a.status !== "rejected" && (
                      <Button size="sm" variant="outline" onClick={() => act(`/ceo/copy/${a.copy_id}/reject`, "Rascunho rejeitado")} disabled={busy.includes(a.copy_id)} data-testid={`ceo-video-reject-${a.copy_id}`}>
                        <X className="h-3.5 w-3.5" />
                      </Button>
                    )}
                  </div>
                  {sb.some((f) => f.url) && (
                    <div className="flex gap-2 mt-3 overflow-x-auto">
                      {sb.filter((f) => f.url).map((f) => (
                        <img key={f.index} src={`${BACKEND}${f.url}`} alt={`frame ${f.index + 1}`} className="h-16 w-28 object-cover rounded border border-border shrink-0" />
                      ))}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        )}
      </div>

      {/* Visuels à valider */}
      <div>
        <h3 className="font-semibold mb-3">Visuels &amp; flyers</h3>
        {drafts.assets.length === 0 ? (
          <p className="text-sm text-muted-foreground rounded-lg border border-dashed border-border p-6 text-center">Nenhum visual por agora.</p>
        ) : (
          <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-4" data-testid="ceo-assets-list">
            {drafts.assets.map((a) => (
              <div key={a.asset_id} className="rounded-lg border border-border bg-card overflow-hidden" data-testid={`ceo-asset-${a.asset_id}`}>
                <img src={`${BACKEND}/api/ceo/asset/${a.asset_id}`} alt={a.brief} className="w-full aspect-[4/3] object-cover bg-secondary" />
                <div className="p-3">
                  <div className="flex items-center gap-2 mb-1"><span className="text-[10px] uppercase text-muted-foreground">{a.format}</span><Badge s={a.status} /></div>
                  <p className="text-xs text-muted-foreground line-clamp-2">{a.brief}</p>
                  <div className="flex items-center gap-2 mt-2">
                    {a.status !== "approved" && <Button size="sm" onClick={() => act(`/ceo/creative/${a.asset_id}/publish`, "Visual aprovado")} disabled={busy.includes(a.asset_id)} data-testid={`ceo-asset-approve-${a.asset_id}`}><Check className="h-3.5 w-3.5 mr-1" /> Approuver</Button>}
                    {a.status !== "rejected" && <Button size="sm" variant="outline" onClick={() => act(`/ceo/creative/${a.asset_id}/reject`, "Visual rejeitado")} disabled={busy.includes(a.asset_id)} data-testid={`ceo-asset-reject-${a.asset_id}`}><X className="h-3.5 w-3.5" /></Button>}
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Preview article blog */}
      {preview && (
        <div className="fixed inset-0 z-[60] bg-black/50 flex items-center justify-center p-4" onClick={() => setPreview(null)} data-testid="ceo-preview-overlay">
          <div className="bg-background rounded-xl max-w-2xl w-full max-h-[85vh] overflow-y-auto p-6" onClick={(e) => e.stopPropagation()}>
            <div className="flex items-center justify-between mb-3">
              <h3 className="font-display text-xl font-bold">{preview.title}</h3>
              <Button size="icon" variant="ghost" onClick={() => setPreview(null)}><X className="h-4 w-4" /></Button>
            </div>
            {preview.hero_image_url && <img src={`${BACKEND}${preview.hero_image_url}`} alt="" className="w-full rounded-lg mb-4" />}
            <div className="prose prose-sm max-w-none" dangerouslySetInnerHTML={{ __html: preview.content_html || "" }} />
          </div>
        </div>
      )}

      {/* Preview e-mail / annonce */}
      {copyPreview && (
        <div className="fixed inset-0 z-[60] bg-black/50 flex items-center justify-center p-4" onClick={() => setCopyPreview(null)} data-testid="ceo-copy-preview-overlay">
          <div className="bg-background rounded-xl max-w-2xl w-full max-h-[85vh] overflow-y-auto p-6" onClick={(e) => e.stopPropagation()}>
            <div className="flex items-center justify-between mb-4">
              <h3 className="font-display text-xl font-bold">{copyPreview.campaign_name}</h3>
              <Button size="icon" variant="ghost" onClick={() => setCopyPreview(null)}><X className="h-4 w-4" /></Button>
            </div>

            {copyPreview.kind === "email" && (
              <div className="space-y-5">
                {(copyPreview.payload?.emails || []).map((em, i) => (
                  <div key={i} className="rounded-lg border border-border p-4">
                    <p className="text-xs font-bold uppercase tracking-wide text-primary mb-2">E-mail {em.step || i + 1} {em.send_hint ? `· ${em.send_hint}` : ""}</p>
                    <div className="space-y-1 mb-3">
                      {(em.subjects || []).map((sub, j) => (
                        <p key={j} className="text-sm flex items-start gap-2">
                          <button type="button" onClick={() => copyText(sub)} className="mt-0.5 text-muted-foreground hover:text-primary shrink-0"><Copy className="h-3 w-3" /></button>
                          <span><strong>Objet {String.fromCharCode(65 + j)} :</strong> {sub}</span>
                        </p>
                      ))}
                      {em.preheader && <p className="text-xs text-muted-foreground">Pré-cabeçalho: {em.preheader}</p>}
                    </div>
                    <div className="prose prose-sm max-w-none border-t border-border pt-3" dangerouslySetInnerHTML={{ __html: em.body_html || "" }} />
                    {em.cta_label && <p className="mt-3"><span className="inline-block rounded-md bg-primary px-3 py-1.5 text-xs font-semibold text-primary-foreground">{em.cta_label}</span></p>}
                  </div>
                ))}
              </div>
            )}

            {copyPreview.kind === "ad" && (
              <div className="space-y-4">
                <AdBlock title="Google Ads" groups={copyPreview.payload?.google} />
                <AdBlock title="Meta (Facebook / Instagram)" groups={copyPreview.payload?.meta} />
                <AdBlock title="LinkedIn" groups={copyPreview.payload?.linkedin} />
              </div>
            )}

            {copyPreview.kind === "video" && (
              <div className="space-y-4">
                <p className="text-xs text-muted-foreground">
                  {copyPreview.payload?.duration_seconds}s · Ambiance : {copyPreview.payload?.music_mood || "—"}
                </p>
                {(copyPreview.payload?.storyboard || []).some((f) => f.url) && (
                  <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
                    {(copyPreview.payload?.storyboard || []).filter((f) => f.url).map((f) => (
                      <img key={f.index} src={`${BACKEND}${f.url}`} alt={`frame ${f.index + 1}`} className="w-full aspect-video object-cover rounded border border-border" />
                    ))}
                  </div>
                )}
                <div className="space-y-3">
                  {(copyPreview.payload?.scenes || []).map((sc, i) => (
                    <div key={i} className="rounded-lg border border-border p-3">
                      <p className="text-xs font-bold uppercase tracking-wide text-primary mb-1">
                        Cena {sc.n || i + 1} {sc.t_start != null ? `· ${sc.t_start}-${sc.t_end}s` : ""}
                      </p>
                      <p className="text-xs text-muted-foreground mb-2"><strong>Visuel :</strong> {sc.visual}</p>
                      <div className="grid sm:grid-cols-3 gap-2 text-sm">
                        <p><span className="text-[10px] font-bold uppercase text-muted-foreground block">🇫🇷 FR</span>{sc.fr}</p>
                        <p><span className="text-[10px] font-bold uppercase text-muted-foreground block">🇵🇹 PT</span>{sc.pt}</p>
                        <p><span className="text-[10px] font-bold uppercase text-muted-foreground block">🇬🇧 EN</span>{sc.en}</p>
                      </div>
                      {sc.on_screen && <p className="text-xs mt-2"><strong>Texto no ecrã:</strong> {sc.on_screen}</p>}
                    </div>
                  ))}
                </div>
                {copyPreview.payload?.cta && (
                  <div className="rounded-lg border border-primary/30 bg-primary/5 p-3 text-sm">
                    <p className="text-[10px] font-bold uppercase text-primary mb-1">CTA</p>
                    <p>🇫🇷 {copyPreview.payload.cta.fr}</p>
                    <p>🇵🇹 {copyPreview.payload.cta.pt}</p>
                    <p>🇬🇧 {copyPreview.payload.cta.en}</p>
                  </div>
                )}
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
