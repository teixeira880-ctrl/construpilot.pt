import { useEffect, useState } from "react";
import { toast } from "sonner";
import { Plus, Trash2, Check, Loader2 } from "lucide-react";
import { api } from "@/lib/api";
import { WaIcon } from "./WhatsAppButton";
import { WA } from "./txt";

/** Configuração do botão WhatsApp da empresa: gerente e colaboradores, sítio a sítio. */
export default function WhatsAppSettings() {
  const [cfg, setCfg] = useState(null);
  const [busy, setBusy] = useState(false);
  useEffect(() => { api.get("/company/whatsapp").then(({ data }) => setCfg(data)).catch(() => setCfg(false)); }, []);
  if (cfg === null || cfg === false) return null;
  const set = (i, patch) => setCfg((c) => ({ ...c, contactos: c.contactos.map((x, j) => (j === i ? { ...x, ...patch } : x)) }));
  const novo = (s = {}) => setCfg((c) => ({ ...c, contactos: [...c.contactos, { nome: s.nome || "", funcao: s.funcao || "", telefone: s.telefone || "", user_id: s.user_id || null,
    locais: { pagina: c.contactos.length === 0, orcamentos: c.contactos.length === 0, portal: true, operarios: true } }] }));
  const livres = cfg.sugestoes.filter((s) => !cfg.contactos.some((c) => c.user_id && c.user_id === s.user_id));
  const guardar = async () => {
    setBusy(true);
    try { const { data } = await api.put("/company/whatsapp", { ativo: cfg.ativo, contactos: cfg.contactos.filter((c) => c.nome.trim()) }); setCfg(data); toast.success(WA.guardado); }
    catch (e) { toast.error(e?.response?.data?.detail || WA.erro); } finally { setBusy(false); }
  };
  const field = "w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900 focus:outline-none focus:ring-2 focus:ring-emerald-600";
  return (
    <section className="rounded-xl border p-5 space-y-4" data-testid="whatsapp-settings">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0"><h2 className="font-semibold flex items-center gap-2"><WaIcon className="h-5 w-5 text-[#25D366]" /> {WA.titulo}</h2>
          <p className="text-xs text-muted-foreground max-w-2xl mt-1">{WA.sub}</p></div>
        <label className="flex items-center gap-2 text-sm font-medium min-h-10"><input type="checkbox" checked={cfg.ativo} onChange={(e) => setCfg((c) => ({ ...c, ativo: e.target.checked }))} data-testid="whatsapp-ativo" /> {WA.ativo}</label>
      </div>
      {cfg.contactos.length === 0 && <p className="text-sm text-muted-foreground">{WA.vazio}</p>}
      <div className="space-y-3">{cfg.contactos.map((c, i) => (
        <div key={i} className="rounded-lg border p-3 grid gap-2" data-testid={`whatsapp-linha-${i}`}>
          <div className="grid sm:grid-cols-[1fr_1fr_1fr_auto] gap-2">
            <input className={field} placeholder={WA.nome} value={c.nome} onChange={(e) => set(i, { nome: e.target.value })} maxLength={80} aria-label={WA.nome} />
            <input className={field} placeholder={WA.funcao} value={c.funcao} onChange={(e) => set(i, { funcao: e.target.value })} maxLength={60} aria-label={WA.funcao} />
            <input className={field} type="tel" inputMode="tel" placeholder={WA.ph_telefone} value={c.telefone} onChange={(e) => set(i, { telefone: e.target.value })} maxLength={30} aria-label={WA.telefone} />
            <button type="button" className="inline-flex items-center justify-center rounded-lg border px-3 min-h-10 text-slate-600 hover:text-red-700" onClick={() => setCfg((x) => ({ ...x, contactos: x.contactos.filter((_, j) => j !== i) }))} aria-label={WA.remover}><Trash2 className="h-4 w-4" /></button>
          </div>
          <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs">{cfg.locais.map((l) => (
            <label key={l} className="flex items-center gap-1.5 min-h-8" title={WA.locais[l]}><input type="checkbox" checked={!!c.locais?.[l]} onChange={(e) => set(i, { locais: { ...c.locais, [l]: e.target.checked } })} /> {WA.locais[l]}</label>))}</div>
        </div>))}</div>
      <div className="flex flex-wrap gap-2 items-center">
        {cfg.contactos.length < cfg.max && <button type="button" className="inline-flex items-center gap-1.5 rounded-lg border px-3 py-2 text-sm min-h-10 hover:bg-slate-50" onClick={() => novo()}><Plus className="h-4 w-4" /> {WA.adicionar}</button>}
        {cfg.contactos.length < cfg.max && livres.length > 0 && <select className={`${field} w-auto`} value="" onChange={(e) => { const s = livres[Number(e.target.value)]; if (s) novo(s); }} aria-label={WA.da_equipa}>
          <option value="">{WA.da_equipa}</option>{livres.map((s, i) => <option key={s.user_id} value={i}>{s.nome} · {s.funcao}{s.telefone ? "" : ` (${WA.sem_telefone})`}</option>)}</select>}
        <button type="button" className="inline-flex items-center gap-1.5 rounded-lg bg-emerald-700 text-white px-4 py-2 text-sm font-medium min-h-10 hover:bg-emerald-800 disabled:opacity-50" disabled={busy} onClick={guardar} data-testid="whatsapp-guardar">{busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Check className="h-4 w-4" />} {WA.guardar}</button>
      </div>
      <p className="text-[11px] text-muted-foreground">{WA.consentimento}</p>
    </section>
  );
}
