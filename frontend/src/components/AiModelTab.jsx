import { useEffect, useState } from "react";
import { toast } from "sonner";
import { Cpu, Check, Loader2 } from "lucide-react";
import { api } from "@/lib/api";
import { SectionTitle } from "@/components/Bits";

export default function AiModelTab() {
  const [data, setData] = useState(null);
  const [saving, setSaving] = useState("");

  const load = () => api.get("/admin/ai-model").then(({ data }) => setData(data));

  useEffect(() => {
    load();
  }, []);

  const choose = async (tier) => {
    if (!data || tier === data.current || saving) return;
    setSaving(tier);
    try {
      const { data: res } = await api.put("/admin/ai-model", { tier });
      setData((d) => ({ ...d, current: res.current }));
      toast.success("Modèle IA mis à jour");
    } catch {
      toast.error("Échec de la mise à jour du modèle");
    } finally {
      setSaving("");
    }
  };

  if (!data) return null;

  return (
    <div className="max-w-2xl space-y-6" data-testid="admin-ai-section">
      <SectionTitle over="Intelligence artificielle" title="Sélecteur de modèle IA">
        Choisissez le modèle utilisé pour la génération de texte (estimation Smart Project,
        coach IA, analyses). L'analyse d'images utilise toujours un modèle vision dédié.
      </SectionTitle>

      <div className="grid sm:grid-cols-3 gap-4" data-testid="admin-ai-options">
        {data.options.map((o) => {
          const active = o.tier === data.current;
          return (
            <button
              key={o.tier}
              type="button"
              onClick={() => choose(o.tier)}
              data-testid={`admin-ai-option-${o.tier}`}
              className={`surface text-left p-5 rounded-sm border transition-colors relative
                ${active ? "border-primary ring-1 ring-primary/40" : "border-border hover:border-primary/40"}`}
            >
              <div className="flex items-center justify-between">
                <Cpu className="h-5 w-5 text-primary" />
                {saving === o.tier ? (
                  <Loader2 className="h-4 w-4 animate-spin text-primary" />
                ) : active ? (
                  <span className="inline-flex items-center gap-1 text-[11px] font-bold uppercase tracking-widest text-primary">
                    <Check className="h-3.5 w-3.5" /> Actif
                  </span>
                ) : null}
              </div>
              <p className="font-display font-extrabold tracking-tight mt-3">{o.label}</p>
              <p className="text-xs text-muted-foreground mt-1">{o.desc}</p>
              <p className="text-[11px] text-muted-foreground/70 mt-3 font-mono">{o.model}</p>
            </button>
          );
        })}
      </div>

      <p className="text-xs text-muted-foreground" data-testid="admin-ai-current">
        Modèle actif : <strong>{data.options.find((o) => o.tier === data.current)?.label}</strong>.
        La modification est immédiate pour toutes les prochaines requêtes IA.
      </p>
    </div>
  );
}
