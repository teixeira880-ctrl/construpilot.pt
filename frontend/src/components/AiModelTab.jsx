import { useEffect, useState } from "react";
import { toast } from "sonner";
import { Cpu, Check, Loader2, Gauge, Coins, Sparkles } from "lucide-react";
import { api, num } from "@/lib/api";
import { SectionTitle } from "@/components/Bits";

function Rating({ icon: Icon, label, value }) {
  return (
    <div className="flex items-center gap-1.5" title={`${label}: ${value}/3`}>
      <Icon className="h-3.5 w-3.5 text-muted-foreground" />
      <div className="flex gap-0.5">
        {[1, 2, 3].map((i) => (
          <span
            key={i}
            className={`h-1.5 w-3 rounded-sm ${i <= value ? "bg-primary" : "bg-border"}`}
          />
        ))}
      </div>
    </div>
  );
}

export default function AiModelTab() {
  const [data, setData] = useState(null);
  const [usage, setUsage] = useState(null);
  const [saving, setSaving] = useState("");

  const load = () => {
    api.get("/admin/ai-model").then(({ data }) => setData(data));
    api.get("/admin/ai-usage").then(({ data }) => setUsage(data)).catch(() => {});
  };

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
    <div className="max-w-3xl space-y-8" data-testid="admin-ai-section">
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
              <div className="mt-4 space-y-1.5">
                <Rating icon={Sparkles} label="Qualité" value={o.quality || 1} />
                <Rating icon={Gauge} label="Vitesse" value={o.speed || 1} />
                <Rating icon={Coins} label="Coût relatif" value={o.cost || 1} />
              </div>
              <p className="text-[11px] text-muted-foreground/70 mt-3 font-mono">{o.model}</p>
            </button>
          );
        })}
      </div>

      <p className="text-xs text-muted-foreground" data-testid="admin-ai-current">
        Modèle actif : <strong>{data.options.find((o) => o.tier === data.current)?.label}</strong>.
        La modification est immédiate pour toutes les prochaines requêtes IA.
      </p>

      {/* --- Suivi des coûts / usage IA --- */}
      <div className="space-y-4" data-testid="admin-ai-usage">
        <SectionTitle over="Consommation" title="Suivi des appels IA">
          Nombre d'appels au modèle par fonctionnalité et par modèle. Total :{" "}
          <strong data-testid="admin-ai-usage-total">{num(usage?.total_calls || 0)}</strong> appels.
        </SectionTitle>

        {(!usage || usage.total_calls === 0) ? (
          <p className="text-sm text-muted-foreground" data-testid="admin-ai-usage-empty">
            Aucun appel IA enregistré pour l'instant. Les compteurs se rempliront dès la prochaine
            estimation, analyse ou conversation avec le coach.
          </p>
        ) : (
          <div className="grid md:grid-cols-2 gap-6">
            <div className="surface p-4 rounded-sm" data-testid="admin-ai-by-feature">
              <p className="text-[11px] font-bold uppercase tracking-widest text-primary mb-3">
                Par fonctionnalité
              </p>
              <div className="space-y-2">
                {usage.by_feature.map((f) => (
                  <div key={f.feature} className="flex items-center justify-between text-sm">
                    <span>{f.feature_label}</span>
                    <span className="num font-bold">{num(f.calls)}</span>
                  </div>
                ))}
              </div>
            </div>
            <div className="surface p-4 rounded-sm" data-testid="admin-ai-by-model">
              <p className="text-[11px] font-bold uppercase tracking-widest text-primary mb-3">
                Par modèle
              </p>
              <div className="space-y-2">
                {usage.by_model.map((m) => (
                  <div key={m.model} className="flex items-center justify-between text-sm">
                    <span className="font-mono text-xs">{m.model}</span>
                    <span className="num font-bold">{num(m.calls)}</span>
                  </div>
                ))}
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
