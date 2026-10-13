import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { Brain, Check, Download, Pencil, Plus, Power, Trash2, X } from "lucide-react";
import { toast } from "sonner";
import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { useAuth } from "@/context/AuthContext";

const SCOPE = { user: "Moi", project: "Chantier", company: "Entreprise" };
const SOURCE = { automatic_style: "Habitude automatique", style_proposal: "Habitude proposée", assistant_proposal: "Proposition à valider", assistant: "Assistant (avec accord)", manual: "Saisie manuelle" };
const fmt = (d) => (d ? new Date(d).toLocaleDateString("fr-FR", { day: "2-digit", month: "2-digit", year: "numeric" }) : "—");

function PrefRow({ p, onChange }) {
  const [edit, setEdit] = useState(false);
  const [cat, setCat] = useState(p.category);
  const [val, setVal] = useState(p.value);
  const save = async () => {
    try { const r = await api.patch(`/assistant/preferences/${p.pref_id}`, { category: cat, value: val }); onChange(r.data); setEdit(false); toast.success("Préférence modifiée"); }
    catch (e) { toast.error(e?.response?.data?.detail || "Modification impossible"); }
  };
  const toggle = async () => {
    try { const r = await api.patch(`/assistant/preferences/${p.pref_id}`, { active: !p.active }); onChange(r.data); }
    catch (e) { toast.error(e?.response?.data?.detail || "Action impossible"); }
  };
  const del = async () => {
    if (!window.confirm("Supprimer définitivement cette préférence ?")) return;
    try { await api.delete(`/assistant/preferences/${p.pref_id}`); onChange(null, p.pref_id); toast.success("Préférence supprimée"); }
    catch (e) { toast.error(e?.response?.data?.detail || "Suppression impossible"); }
  };
  return (
    <tr className={`border-t text-sm ${p.active ? "" : "opacity-50"}`} data-testid={`pref-row-${p.pref_id}`}>
      <td className="px-3 py-2 align-top">
        {edit ? <input className="w-full border rounded-sm px-2 py-1 text-sm bg-background" value={cat} onChange={(e) => setCat(e.target.value)} data-testid={`pref-edit-category-${p.pref_id}`} /> : <b data-testid={`pref-category-${p.pref_id}`}>{p.category}</b>}
      </td>
      <td className="px-3 py-2 align-top">
        {edit ? <textarea className="w-full border rounded-sm px-2 py-1 text-sm bg-background" rows={2} value={val} onChange={(e) => setVal(e.target.value)} data-testid={`pref-edit-value-${p.pref_id}`} /> : <span data-testid={`pref-value-${p.pref_id}`}>{p.value}</span>}
      </td>
      <td className="px-3 py-2 align-top text-xs"><span className="px-1.5 py-0.5 rounded-sm border bg-muted/40">{SCOPE[p.scope] || p.scope}</span></td>
      <td className="px-3 py-2 align-top text-xs text-muted-foreground">{SOURCE[p.source] || p.source}<br />{fmt(p.created_at)}{p.last_used_at && <><br /><span>utilisée le</span> {fmt(p.last_used_at)}</>}</td>
      <td className="px-3 py-2 align-top text-xs"><span className={`px-1.5 py-0.5 rounded-sm ${p.active ? "bg-emerald-500/15 text-emerald-700 dark:text-emerald-400" : "bg-muted text-muted-foreground"}`} data-testid={`pref-status-${p.pref_id}`}>{p.active ? "Active" : "Désactivée"}</span></td>
      <td className="px-3 py-2 align-top">
        <div className="flex gap-1 justify-end">
          {edit ? (<>
            <Button size="icon" variant="outline" className="h-7 w-7 rounded-sm" onClick={save} data-testid={`pref-save-btn-${p.pref_id}`} aria-label="Enregistrer la préférence"><Check className="h-3.5 w-3.5" /></Button>
            <Button size="icon" variant="ghost" className="h-7 w-7 rounded-sm" onClick={() => { setEdit(false); setCat(p.category); setVal(p.value); }} data-testid={`pref-cancel-btn-${p.pref_id}`} aria-label="Annuler la modification"><X className="h-3.5 w-3.5" /></Button>
          </>) : (<>
            <Button size="icon" variant="ghost" className="h-7 w-7 rounded-sm" title="Modifier" onClick={() => setEdit(true)} data-testid={`pref-edit-btn-${p.pref_id}`}><Pencil className="h-3.5 w-3.5" /></Button>
            <Button size="icon" variant="ghost" className="h-7 w-7 rounded-sm" title={p.active ? "Désactiver" : "Réactiver"} onClick={toggle} data-testid={`pref-toggle-btn-${p.pref_id}`}><Power className="h-3.5 w-3.5" /></Button>
            <Button size="icon" variant="ghost" className="h-7 w-7 rounded-sm text-red-600" title="Supprimer" onClick={del} data-testid={`pref-delete-btn-${p.pref_id}`}><Trash2 className="h-3.5 w-3.5" /></Button>
          </>)}
        </div>
      </td>
    </tr>
  );
}

function AddPref({ canCompany, onAdded }) {
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState({ category: "", value: "", scope: "user" });
  const submit = async () => {
    if (!form.category.trim() || !form.value.trim()) return toast.error("Catégorie et règle obligatoires");
    try { const r = await api.post("/assistant/preferences", form); onAdded(r.data); setForm({ category: "", value: "", scope: "user" }); setOpen(false); toast.success("Préférence ajoutée"); }
    catch (e) { toast.error(e?.response?.data?.detail || "Ajout impossible"); }
  };
  if (!open) return <Button size="sm" className="rounded-sm gap-1" onClick={() => setOpen(true)} data-testid="pref-add-btn"><Plus className="h-4 w-4" /> Ajouter une règle</Button>;
  return (
    <div className="grid gap-2 sm:grid-cols-[1fr_2fr_auto_auto] items-end border rounded-sm p-3 bg-muted/30" data-testid="pref-add-form">
      <label className="grid gap-1 text-xs">Catégorie<input className="border rounded-sm px-2 py-1.5 text-sm bg-background" placeholder="ex. Carrelage" value={form.category} onChange={(e) => setForm({ ...form, category: e.target.value })} data-testid="pref-add-category" /></label>
      <label className="grid gap-1 text-xs">Règle<input className="border rounded-sm px-2 py-1.5 text-sm bg-background" placeholder="ex. Toujours 10 % de perte sur le carrelage" value={form.value} onChange={(e) => setForm({ ...form, value: e.target.value })} data-testid="pref-add-value" /></label>
      <label className="grid gap-1 text-xs">Portée
        <select className="border rounded-sm px-2 py-1.5 text-sm bg-background h-[34px]" value={form.scope} onChange={(e) => setForm({ ...form, scope: e.target.value })} data-testid="pref-add-scope">
          <option value="user">Moi</option>{canCompany && <option value="company">Entreprise</option>}
        </select>
      </label>
      <div className="flex gap-1"><Button size="sm" className="rounded-sm" onClick={submit} data-testid="pref-add-submit">Enregistrer</Button><Button size="sm" variant="ghost" className="rounded-sm" onClick={() => setOpen(false)} data-testid="pref-add-cancel">Annuler</Button></div>
    </div>
  );
}

export default function Preferences() {
  const { user } = useAuth();
  const [settings, setSettings] = useState(null);
  const saveSettings = async next => { try { const r = await api.put("/assistant/settings", next); setSettings(r.data); toast.success("Réglages enregistrés"); } catch { toast.error("Réglages non enregistrés"); } };
  const [prefs, setPrefs] = useState(null);
  const load = () => api.get("/assistant/preferences").then((r) => setPrefs(r.data)).catch(() => setPrefs([]));
  useEffect(() => { load(); api.get("/assistant/settings").then(r => setSettings(r.data)).catch(() => {}); }, []);

  const onChange = (updated, deletedId) => setPrefs((cur) => deletedId ? cur.filter((p) => p.pref_id !== deletedId) : cur.map((p) => (p.pref_id === updated.pref_id ? updated : p)));
  const exportJson = async () => {
    const res = await fetch(`${process.env.REACT_APP_BACKEND_URL}/api/assistant/preferences/export`, {  credentials: "include" });
    if (!res.ok) return toast.error("Export impossible");
    const url = URL.createObjectURL(await res.blob()); const el = document.createElement("a"); el.href = url; el.download = "construpilot-preferences.json"; el.click(); URL.revokeObjectURL(url);
  };
  const clearAll = async () => {
    if (!window.confirm("Effacer TOUTE la mémoire de l'assistant pour votre compte ? Cette action est irréversible.")) return;
    const r = await api.delete("/assistant/preferences"); toast.success(`${r.data.deleted} préférence(s) effacée(s)`); load();
  };
  const canCompany = !!user?.organization_id && user?.account_type !== "particulier" && ["admin", "owner", "manager"].includes(user?.role);
  const active = (prefs || []).filter((p) => p.active).length;

  return (
    <div className="max-w-6xl mx-auto px-4 py-8 grid gap-6" data-testid="preferences-page">
      <header className="grid gap-2">
        <div className="flex items-center gap-2 text-xs text-muted-foreground"><Link to="/assistant" className="underline" data-testid="prefs-back-assistant">Assistant BTP</Link> / Mémoire et préférences</div>
        <h1 className="text-2xl sm:text-3xl font-bold tracking-tight flex items-center gap-2"><Brain className="h-7 w-7 text-primary" /> Mémoire et préférences</h1>
        <p className="text-sm text-muted-foreground max-w-3xl">
          Ce que l'assistant a retenu de vos habitudes (uniquement avec votre accord) et vos règles saisies à la main. Une règle active est
          appliquée à chaque réponse sauf instruction contraire ponctuelle. Vous pouvez la modifier, la désactiver, la supprimer ou tout effacer.
        </p>
      </header>
      {settings && <section className="border rounded-md p-4 grid gap-3" aria-label="Apprentissage">
        <label className="text-sm">Apprentissage de mes habitudes <select className="mt-1 w-full sm:w-auto max-w-full border bg-background rounded-sm p-2" value={settings.learning_mode} onChange={e => saveSettings({ ...settings, learning_mode: e.target.value })} data-testid="prefs-learning-mode">
          <option value="off">Désactivé</option><option value="suggest">Me proposer les habitudes à retenir</option><option value="automatic">Mémoriser automatiquement le ton, la langue et la longueur</option>
        </select></label>
        <p className="text-xs text-muted-foreground">Le mode automatique retient les préférences simples que vous formulez explicitement dans le chat. Les règles métier sont proposées pour validation. Les données clients et les documents ne servent pas à cet apprentissage. Vos réglages restent propres à votre compte ; les règles d'entreprise sont gérées par ses administrateurs.</p>
        <label className="text-sm flex gap-2"><input type="checkbox" checked={settings.web_enabled} onChange={e => saveSettings({ ...settings, web_enabled: e.target.checked })} data-testid="prefs-web-enabled" /> Autoriser les recherches Internet</label>
      </section>}
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-sm" data-testid="prefs-count">{prefs ? `${active} active(s) · ${prefs.length} au total` : "Chargement…"}</span>
        <div className="ml-auto flex flex-wrap gap-2">
          <AddPref canCompany={canCompany} onAdded={(p) => setPrefs((cur) => [p, ...(cur || [])])} />
          <Button size="sm" variant="outline" className="rounded-sm gap-1" onClick={exportJson} data-testid="prefs-export-btn"><Download className="h-4 w-4" /> Exporter (JSON)</Button>
          <Button size="sm" variant="outline" className="rounded-sm gap-1 text-red-600 border-red-300" onClick={clearAll} disabled={!prefs?.length} data-testid="prefs-clear-btn"><Trash2 className="h-4 w-4" /> Tout effacer</Button>
        </div>
      </div>
      <div className="border rounded-sm overflow-x-auto bg-card">
        <table className="w-full text-left" data-testid="prefs-table">
          <thead className="bg-muted/40 text-xs uppercase tracking-wide"><tr><th className="px-3 py-2">Catégorie</th><th className="px-3 py-2">Règle mémorisée</th><th className="px-3 py-2">Portée</th><th className="px-3 py-2">Source / dates</th><th className="px-3 py-2">État</th><th className="px-3 py-2" /></tr></thead>
          <tbody>
            {prefs?.length === 0 && <tr><td colSpan={6} className="px-3 py-8 text-center text-sm text-muted-foreground" data-testid="prefs-empty">Aucune préférence mémorisée. Dites par exemple à l'assistant : « Retiens que je compte toujours 10 % de perte sur le carrelage ».</td></tr>}
            {(prefs || []).map((p) => <PrefRow key={p.pref_id} p={p} onChange={onChange} />)}
          </tbody>
        </table>
      </div>
    </div>
  );
}
