import { useEffect, useState } from "react";
import { toast } from "sonner";
import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Share2, Megaphone, Loader2, OctagonX, Play, CheckCircle2, AlertTriangle } from "lucide-react";

const NET_LABEL = { facebook: "Facebook", instagram: "Instagram", linkedin: "LinkedIn" };
const ACTION_LABEL = { pause: "Pausada", enable: "Ativada", budget: "Orçamento" };
const eur = (v) => `${Number(v || 0).toLocaleString("pt-PT", { minimumFractionDigits: 2, maximumFractionDigits: 2 })} €`;

export default function CeoChannelsPanel() {
  const [social, setSocial] = useState(null);
  const [ads, setAds] = useState(null);
  const [cap, setCap] = useState("");
  const [busy, setBusy] = useState("");

  const load = async () => {
    try { const { data } = await api.get("/ceo/social"); setSocial(data); } catch { /* */ }
    try {
      const { data } = await api.get("/ceo/ads");
      setAds(data);
      setCap(String(data?.settings?.monthly_cap_eur ?? ""));
    } catch { /* */ }
  };
  useEffect(() => { load(); }, []);

  const saveSocial = async (patch) => {
    try { await api.put("/ceo/social/settings", patch); toast.success("Definições guardadas"); load(); }
    catch (e) { toast.error(e?.response?.data?.detail || "Impossível guardar"); }
  };
  const saveAds = async (patch) => {
    try { await api.put("/ceo/ads/settings", patch); toast.success("Definições guardadas"); load(); }
    catch (e) { toast.error(e?.response?.data?.detail || "Impossível guardar"); }
  };
  const runAds = async () => {
    setBusy("run");
    try {
      const { data } = await api.post("/ceo/ads/run");
      if (data.skipped) toast.info(`Não executado: ${data.skipped}`);
      else toast.success(`Piloto executado: ${data.actions} ação(ões)`);
      load();
    } catch (e) { toast.error(e?.response?.data?.detail || "Falhou"); }
    finally { setBusy(""); }
  };
  const stopAds = async () => {
    if (!window.confirm("Pausar TODAS as campanhas Google Ads ativas e desligar o piloto automático?")) return;
    setBusy("stop");
    try { const { data } = await api.post("/ceo/ads/stop"); toast.success(`${data.paused} campanha(s) pausada(s)`); load(); }
    catch (e) { toast.error(e?.response?.data?.detail || "Falhou"); }
    finally { setBusy(""); }
  };

  const st = social?.status || {};
  const ss = social?.settings || {};
  const as = ads?.settings || {};
  const last = ads?.last_run;

  return (
    <div className="grid lg:grid-cols-2 gap-5" data-testid="ceo-channels">
      {/* Redes sociais */}
      <div className="rounded-xl border border-border bg-card p-5" data-testid="ceo-social">
        <h3 className="font-semibold flex items-center gap-2"><Share2 className="h-4 w-4 text-primary" /> Redes sociais</h3>
        <p className="text-xs text-muted-foreground mt-1">Cada novo artigo publicado no blogue é partilhado na Página Facebook, no Instagram e na página LinkedIn da empresa, com um texto curto em PT-PT.</p>
        <div className="mt-3 space-y-1.5 text-sm">
          {Object.keys(NET_LABEL).map((n) => (
            <div key={n} className="flex items-center justify-between gap-2">
              <span className="flex items-center gap-2">
                {st[n]?.configured ? <CheckCircle2 className="h-4 w-4 text-emerald-600" /> : <AlertTriangle className="h-4 w-4 text-amber-500" />}
                {NET_LABEL[n]}
              </span>
              <span className="text-[11px] text-muted-foreground">{st[n]?.configured ? "ligado" : `em falta: ${(st[n]?.missing || []).join(", ")}`}</span>
            </div>
          ))}
        </div>
        <div className="flex items-center gap-4 flex-wrap mt-4 text-sm">
          <label className="flex items-center gap-2 font-medium cursor-pointer">
            <input type="checkbox" checked={!!ss.auto_share} onChange={(e) => saveSocial({ auto_share: e.target.checked })} data-testid="ceo-social-auto" /> Partilha automática
          </label>
          <label className="flex items-center gap-2 text-xs">Máx./dia
            <Input type="number" min={0} max={20} defaultValue={ss.max_per_day} key={ss.max_per_day}
              onBlur={(e) => saveSocial({ max_per_day: Number(e.target.value) })} className="h-8 w-16" />
          </label>
        </div>
        <p className="text-[11px] text-muted-foreground mt-2">Ao ligar, só os artigos novos são partilhados (os antigos não são despejados de uma vez).</p>
        {(social?.posts || []).length > 0 && (
          <div className="mt-3 border-t border-border pt-3 space-y-1">
            <p className="text-[10px] uppercase text-muted-foreground">Últimas partilhas</p>
            {social.posts.slice(0, 5).map((p, i) => (
              <p key={i} className="text-xs truncate">
                <span className="font-medium">{p.slug}</span> — {Object.entries(p.results || {}).map(([n, r]) => `${NET_LABEL[n] || n}: ${r.ok ? "ok" : r.skipped || "erro"}`).join(" · ")}
              </p>
            ))}
          </div>
        )}
      </div>

      {/* Google Ads */}
      <div className="rounded-xl border border-border bg-card p-5" data-testid="ceo-ads">
        <h3 className="font-semibold flex items-center gap-2"><Megaphone className="h-4 w-4 text-primary" /> Google Ads e YouTube — piloto automático</h3>
        <p className="text-xs text-muted-foreground mt-1">Duas vezes por dia a IA ajusta orçamentos, pausa campanhas que gastam sem converter e ativa as campanhas preparadas, sempre abaixo do teto mensal. Se o teto for atingido, pausa tudo.</p>
        <div className="grid grid-cols-2 gap-3 mt-3 text-sm">
          <div className="rounded-lg border border-border p-3">
            <p className="text-[10px] uppercase text-muted-foreground">Teto mensal (obrigatório)</p>
            <div className="flex items-center gap-2 mt-1">
              <Input type="number" min={0} value={cap} onChange={(e) => setCap(e.target.value)} className="h-9" data-testid="ceo-ads-cap" />
              <Button size="sm" variant="outline" onClick={() => saveAds({ monthly_cap_eur: Number(cap) || 0 })}>OK</Button>
            </div>
          </div>
          <div className="rounded-lg border border-border p-3">
            <p className="text-[10px] uppercase text-muted-foreground">Este mês</p>
            <p className="font-semibold mt-1">{last ? `${eur(last.month_spend_eur)} / ${eur(last.cap_eur)}` : "—"}</p>
            <p className="text-[11px] text-muted-foreground">{last ? `${last.enabled}/${last.campaigns} campanhas ativas` : "Ainda sem execução"}</p>
          </div>
        </div>
        <div className="flex items-center gap-2 flex-wrap mt-3 text-sm">
          <label className="flex items-center gap-2 font-medium cursor-pointer mr-2">
            <input type="checkbox" checked={!!as.enabled} onChange={(e) => saveAds({ enabled: e.target.checked })} data-testid="ceo-ads-enabled" /> Piloto automático ligado
          </label>
          <Button size="sm" variant="outline" onClick={runAds} disabled={busy === "run"} className="gap-1">
            {busy === "run" ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Play className="h-3.5 w-3.5" />} Executar agora
          </Button>
          <Button size="sm" variant="destructive" onClick={stopAds} disabled={busy === "stop"} className="gap-1" data-testid="ceo-ads-stop">
            <OctagonX className="h-3.5 w-3.5" /> Parar tudo
          </Button>
        </div>
        {ads && (!ads.configured?.customer_id || !ads.configured?.oauth) && (
          <p className="text-[11px] text-amber-600 mt-2">Falta ligar o Google Ads: {!ads.configured?.customer_id ? "GOOGLE_ADS_CUSTOMER_ID; " : ""}{!ads.configured?.oauth ? "autorização (Growth → «Autorizar Google Ads»)" : ""}</p>
        )}
        {(ads?.actions || []).length > 0 && (
          <div className="mt-3 border-t border-border pt-3 space-y-1 max-h-48 overflow-auto">
            <p className="text-[10px] uppercase text-muted-foreground">Últimas ações</p>
            {ads.actions.slice(0, 12).map((a, i) => (
              <p key={i} className={`text-xs ${a.ok ? "" : "text-destructive"}`}>
                {new Date(a.at).toLocaleString("pt-PT")} · <strong>{ACTION_LABEL[a.type] || a.type}</strong> {a.campaign || a.campaign_id}
                {a.type === "budget" ? ` ${eur(a.from)} → ${eur(a.to)}/dia` : ""} — {a.reason}{a.error ? ` (erro: ${a.error})` : ""}
              </p>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
