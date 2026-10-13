import { useEffect, useState } from "react";
import { Loader2, RefreshCw, Newspaper, Trash2, ExternalLink, Copy, Check } from "lucide-react";
import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { toast } from "sonner";

export default function SeoBlogPanel() {
  const [st, setSt] = useState(null);
  const [nl, setNl] = useState(null);
  const [busy, setBusy] = useState(false);
  const [copied, setCopied] = useState(false);

  const load = () => {
    api.get("/admin/babylovegrowth/status").then(({ data }) => setSt(data)).catch(() => setSt({ error: true }));
    api.get("/newsletter/admin/stats").then(({ data }) => setNl(data)).catch(() => {});
  };
  useEffect(() => { load(); }, []);

  const sync = async (force = false) => {
    setBusy(true);
    try {
      const { data } = await api.post(`/admin/babylovegrowth/sync?force=${force}`, {}, { timeout: 300000 });
      const parts = [`${data.created} artigo(s) publicado(s)`, `${data.skipped} já presentes`];
      if (data.skipped_lang) parts.push(`${data.skipped_lang} ignorado(s) por idioma`);
      if (data.errors) parts.push(`${data.errors} erro(s)`);
      toast.success(parts.join(" · "));
      load();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Sincronização impossível");
    } finally { setBusy(false); }
  };

  const del = async (slug) => {
    if (!window.confirm(`Remover « ${slug} » do blogue?`)) return;
    await api.delete(`/admin/babylovegrowth/articles/${slug}`);
    toast.success("Artigo removido"); load();
  };

  const copy = () => { navigator.clipboard?.writeText(st.webhook_url); setCopied(true); setTimeout(() => setCopied(false), 1500); };

  if (!st) return <div className="flex items-center gap-2 text-sm text-muted-foreground"><Loader2 className="h-4 w-4 animate-spin" /> A carregar…</div>;

  return (
    <div className="space-y-6" data-testid="admin-seo-blog-panel">
      <div className="flex items-start justify-between gap-4 flex-wrap">
        <div>
          <h3 className="font-display font-bold text-lg flex items-center gap-2"><Newspaper className="h-5 w-5 text-primary" /> SEO & Blogue — BabyLoveGrowth</h3>
          <p className="text-sm text-muted-foreground">Os artigos em português (pt-PT) gerados por BabyLoveGrowth são publicados automaticamente em <b>/blog</b>. Artigos noutros idiomas são ignorados.</p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" size="sm" className="rounded-sm gap-2" onClick={() => sync(true)} disabled={busy} data-testid="admin-blg-resync">
            Ressincronizar tudo
          </Button>
          <Button size="sm" className="rounded-sm gap-2" onClick={() => sync(false)} disabled={busy} data-testid="admin-blg-sync">
            {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <RefreshCw className="h-4 w-4" />} Sincronizar agora
          </Button>
        </div>
      </div>

      <div className="grid sm:grid-cols-4 gap-3">
        <div className="surface p-4 rounded-md"><p className="overline text-[10px]">Ligação API</p>
          <p className="font-bold mt-1" data-testid="admin-blg-configured">{st.configured ? <span className="text-emerald-500">Configurado ✓</span> : <span className="text-red-500">Chave API em falta — configure BABYLOVEGROWTH_API_KEY nas variáveis de ambiente</span>}</p></div>
        <div className="surface p-4 rounded-md"><p className="overline text-[10px]">Artigos publicados</p>
          <p className="font-bold text-2xl num mt-1" data-testid="admin-blg-count">{st.count}</p></div>
        <div className="surface p-4 rounded-md"><p className="overline text-[10px]">Subscritores newsletter</p>
          <p className="font-bold text-2xl num mt-1" data-testid="admin-newsletter-active">{nl ? nl.active : "…"}</p>
          {nl?.recent_sends?.[0] && <p className="text-[11px] text-muted-foreground truncate">Último envio: {nl.recent_sends[0].title} ({nl.recent_sends[0].sent})</p>}</div>
        <div className="surface p-4 rounded-md"><p className="overline text-[10px]">Última sincronização</p>
          <p className="text-sm mt-1" data-testid="admin-blg-last-sync">{st.last_sync?.at ? new Date(st.last_sync.at).toLocaleString("pt-PT") : "nunca"}</p>
          {st.last_sync && <p className="text-[11px] text-muted-foreground">+{st.last_sync.created} novos · {st.last_sync.skipped} existentes · {st.last_sync.skipped_lang || 0} ignorados por idioma · {st.last_sync.errors} erro(s)</p>}</div>
      </div>

      <div className="surface p-4 rounded-md text-xs space-y-2">
        <p className="overline text-[10px]">Webhook tempo real (opcional)</p>
        <p className="text-muted-foreground">Em BabyLoveGrowth → Settings → Integrations → Webhook, cole este URL e o segredo (Authorization: Bearer) presente em <code>BABYLOVEGROWTH_WEBHOOK_SECRET</code>.</p>
        <div className="flex items-center gap-2">
          <code className="flex-1 truncate bg-secondary/40 px-2 py-1 rounded" data-testid="admin-blg-webhook-url">{st.webhook_url}</code>
          <Button variant="ghost" size="icon" className="h-7 w-7" onClick={copy} data-testid="admin-blg-copy-webhook">{copied ? <Check className="h-3.5 w-3.5 text-emerald-500" /> : <Copy className="h-3.5 w-3.5" />}</Button>
        </div>
      </div>

      <div className="surface p-4 rounded-md">
        <p className="overline text-[10px] mb-2">Últimos artigos</p>
        {!st.recent?.length && <p className="text-sm text-muted-foreground">Nenhum artigo ainda sincronizado.</p>}
        <ul className="divide-y divide-border/50">
          {(st.recent || []).map((a) => (
            <li key={a.slug} className="flex items-center gap-3 py-2 text-sm" data-testid={`admin-blg-article-${a.slug}`}>
              {a.hero_image_url && <img src={a.hero_image_url} alt="" className="h-10 w-16 object-cover rounded-sm shrink-0" />}
              <div className="flex-1 min-w-0">
                <p className="font-medium truncate">{a.title}</p>
                <p className="text-[11px] text-muted-foreground truncate">{a.seed_keyword} · {a.published_at ? new Date(a.published_at).toLocaleDateString("pt-PT") : ""}</p>
              </div>
              <Badge variant="outline" className="rounded-sm text-[10px] uppercase">{a.language_code}</Badge>
              <a href={`/blog/${a.slug}`} target="_blank" rel="noreferrer" className="text-primary" data-testid={`admin-blg-open-${a.slug}`}><ExternalLink className="h-4 w-4" /></a>
              <Button variant="ghost" size="icon" className="h-7 w-7 text-red-500" onClick={() => del(a.slug)} data-testid={`admin-blg-delete-${a.slug}`}><Trash2 className="h-4 w-4" /></Button>
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}
