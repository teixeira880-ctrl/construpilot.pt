import { useEffect, useState } from "react";
import { toast } from "sonner";
import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { ListChecks, Loader2, RotateCcw, Save } from "lucide-react";

// Fichas do « Programa IA de opções »: prompt preparado de cada opção e ativação.
// Um programa já validado mantém a versão do prompt que recebeu.
export default function MissionOptionsPanel() {
  const [options, setOptions] = useState([]);
  const [drafts, setDrafts] = useState({});
  const [saving, setSaving] = useState("");

  const load = async () => {
    try {
      const { data } = await api.get("/missions/admin/options");
      setOptions(data.options || []);
      setDrafts(Object.fromEntries((data.options || []).map((o) => [o.key, o.prompt])));
    } catch { toast.error("Opções indisponíveis"); }
  };
  useEffect(() => { load(); }, []);

  const save = async (key, body) => {
    setSaving(key);
    try { await api.put(`/missions/admin/options/${key}`, body); toast.success("Opção guardada"); await load(); }
    catch (e) { toast.error(e?.response?.data?.detail || "Gravação impossível"); }
    finally { setSaving(""); }
  };
  const reset = async (key) => {
    setSaving(key);
    try { await api.delete(`/missions/admin/options/${key}/prompt`); toast.success("Prompt original reposto"); await load(); }
    catch { toast.error("Reposição impossível"); }
    finally { setSaving(""); }
  };

  return (
    <div className="space-y-4" data-testid="mission-options-panel">
      <div>
        <h2 className="font-display text-xl font-bold flex items-center gap-2"><ListChecks className="h-5 w-5 text-primary" /> Programa IA de opções</h2>
        <p className="text-sm text-muted-foreground">O prompt de cada opção redige a síntese do entregável. Os números vêm sempre dos motores de cálculo.</p>
      </div>
      {options.map((o) => (
        <div key={o.key} className="rounded-xl border border-border bg-card p-4 space-y-2" data-testid={`mission-option-${o.key}`}>
          <div className="flex items-center gap-3 flex-wrap">
            <p className="font-semibold">{o.name}</p>
            <span className="text-[11px] text-muted-foreground">{o.group} · version {o.prompt_version}</span>
            <label className="ml-auto flex items-center gap-2 text-sm">
              <input type="checkbox" checked={o.enabled} disabled={saving === o.key} onChange={(e) => save(o.key, { enabled: e.target.checked })} />
              Proposta aos clientes
            </label>
          </div>
          <p className="text-xs text-muted-foreground">{o.desc}</p>
          <Textarea rows={3} value={drafts[o.key] || ""} onChange={(e) => setDrafts((d) => ({ ...d, [o.key]: e.target.value }))} />
          <div className="flex gap-2">
            <Button size="sm" disabled={saving === o.key || drafts[o.key] === o.prompt} onClick={() => save(o.key, { prompt: drafts[o.key] })}>
              {saving === o.key ? <Loader2 className="h-3.5 w-3.5 mr-1 animate-spin" /> : <Save className="h-3.5 w-3.5 mr-1" />} Guardar
            </Button>
            {o.prompt !== o.default_prompt && (
              <Button size="sm" variant="ghost" disabled={saving === o.key} onClick={() => reset(o.key)}><RotateCcw className="h-3.5 w-3.5 mr-1" /> Prompt original</Button>
            )}
          </div>
        </div>
      ))}
    </div>
  );
}
