import { useEffect, useState, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";
import { Sparkles, HelpCircle, AlertTriangle, Save, Wrench, ShoppingCart, RefreshCw } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Input } from "@/components/ui/input";
import VoiceNoteButton from "@/components/VoiceNoteButton";
import { api, eur } from "@/lib/api";
import { EstimationView } from "@/components/EstimationView";
import { LeadDialog } from "@/components/LeadDialog";
import { useAuth } from "@/context/AuthContext";
import { SectionTitle } from "@/components/Bits";
import { SEO } from "@/components/SEO";

export default function SmartProject() {
  const [description, setDescription] = useState(sessionStorage.getItem("construpilot_description") || "");
  const [ceilingHeight, setCeilingHeight] = useState(2.5);
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState(null);
  const [name, setName] = useState("");
  const [saving, setSaving] = useState(false);
  const { user } = useAuth();
  const navigate = useNavigate();

  const run = useCallback(async (text, height) => {
    if (!text || text.trim().length < 10) {
      toast.error("Descreva o seu projeto em poucas palavras (10 caracteres mínimo)");
      return;
    }
    setLoading(true);
    setResult(null);
    try {
      const body = { description: text };
      if (height && height > 0) body.ceiling_height_m = height;
      const { data } = await api.post("/estimation/analyse", body);
      setResult(data);
      // Sync le champ hauteur avec ce que l'IA a détecté (ou reçu en override)
      if (data.analysis?.ceiling_height_m) setCeilingHeight(data.analysis.ceiling_height_m);
      setName(data.analysis?.summary?.slice(0, 48) || "O meu projeto");
    } catch (e) {
      toast.error("A análise IA falhou. Tente novamente.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    const stored = sessionStorage.getItem("construpilot_description");
    if (stored) {
      sessionStorage.removeItem("construpilot_description");
      run(stored, ceilingHeight);
    }
  }, [run]);

  const save = async () => {
    if (!user) {
      sessionStorage.setItem("construpilot_description", description);
      navigate("/login");
      return;
    }
    setSaving(true);
    try {
      const a = result.analysis;
      const { data } = await api.post("/projects", {
        name: name || "Mon projet", description,
        project_type: a.project_type, surface: a.surface, finish_level: a.finish_level,
        building_type: a.building_type, condition: a.condition, lots: a.lots,
        estimation: result.estimation,
      });
      toast.success("Projeto guardado");
      navigate(`/projet/${data.project_id}`);
    } catch (e) {
      toast.error("Não foi possível guardar");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="grid gap-12">
      <div>
        <SEO title="Smart Project IA — Orçamento valorizado em 30 s" description="Descreva o seu projeto em 2 linhas: ConstruPilot decompõe-no em especialidades, calcula as áreas, orçamenta cada artigo e encontra os melhores preços de materiais. Gratuito." keywords="orçamento IA, smart project construção, estimativa automática, projeto de remodelação IA, orçamentação instantânea" canonical="/smart-project" />
        <SectionTitle as="h1" over="ConstruPilot Smart Project" title="Descreva o seu projeto, a IA faz o resto">
          Lista dos trabalhos, ordem de execução, orçamento, quantidades, duração, o que pode fazer você mesmo, riscos e economias possíveis.
        </SectionTitle>
        <div className="surface p-2 relative">
          <Textarea
            data-testid="smart-project-input" rows={4} value={description}
            onChange={(e) => setDescription(e.target.value)}
            placeholder="Ex: Quero renovar completamente esta casa de 120 m²…"
            className="resize-none border-0 bg-transparent focus-visible:ring-0 text-base"
          />
          <div className="p-2 pt-0 flex gap-3 items-center flex-wrap">
            <Button
              onClick={() => run(description, ceilingHeight)} disabled={loading} data-testid="smart-project-submit-btn"
              className="rounded-sm gap-2 hover:bg-orange-600 hover:text-white"
            >
              {loading ? <RefreshCw className="h-4 w-4 animate-spin" /> : <Sparkles className="h-4 w-4" />}
              {loading ? "Analyse en cours…" : "Analisar o meu projeto"}
            </Button>
            <VoiceNoteButton label="Ditar a minha obra"
              onText={(txt) => setDescription((d) => (d?.trim() ? `${d.trim()}\n${txt}` : txt))} />
            <div className="inline-flex items-center gap-2 rounded-sm border border-border px-3 py-1.5 bg-background">
              <span className="text-xs text-muted-foreground">Pé-direito</span>
              <Input
                type="number" step="0.05" min="2.0" max="5.0"
                value={ceilingHeight}
                onChange={(e) => setCeilingHeight(Math.max(2.0, Math.min(5.0, Number(e.target.value) || 2.5)))}
                data-testid="smart-project-height-input"
                className="w-20 h-7 text-xs num text-center border-0 shadow-none"
              />
              <span className="text-xs text-muted-foreground">m</span>
            </div>
          </div>
        </div>
      </div>

      {loading && (
        <div className="surface p-12 text-center" data-testid="smart-project-loading">
          <div className="h-8 w-8 mx-auto border-2 border-primary border-t-transparent rounded-full animate-spin" />
          <p className="mt-6 text-sm text-muted-foreground">
            ConstruPilot analisa o seu projeto, decompõe as especialidades e lança o motor de cálculo…
          </p>
        </div>
      )}

      {result && (
        <>
          <div className="grid lg:grid-cols-3 gap-4" data-testid="analysis-block">
            <div className="surface p-6 lg:col-span-2">
              <p className="overline">O que ConstruPilot compreendeu</p>
              <p className="mt-3 text-sm">{result.analysis.summary}</p>
              {result.analysis.diy_advice && (
                <p className="mt-4 text-sm text-muted-foreground flex gap-2">
                  <Wrench className="h-4 w-4 text-primary shrink-0 mt-0.5" />
                  {result.analysis.diy_advice}
                </p>
              )}
              {result.analysis.levels?.length > 0 && (
                <div className="mt-4 pt-4 border-t border-border" data-testid="analysis-levels">
                  <p className="text-xs text-muted-foreground mb-2">
                    Níveis detetados (altura ponderada: <span className="num font-medium">
                    {result.estimation.ceiling_height_m?.toFixed(2)} m</span>)
                  </p>
                  <div className="flex flex-wrap gap-2">
                    {result.analysis.levels.map((lvl, i) => (
                      <span
                        key={i}
                        data-testid={`analysis-level-${i}`}
                        className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-sm border border-border text-xs"
                      >
                        <span className="font-medium">{lvl.label}</span>
                        <span className="num text-muted-foreground">
                          {lvl.surface_m2} m² · {lvl.ceiling_height_m} m
                        </span>
                      </span>
                    ))}
                  </div>
                </div>
              )}
            </div>
            <div className="surface p-6">
              <p className="overline flex items-center gap-2"><HelpCircle className="h-4 w-4" /> Questões a precisar</p>
              <ul className="mt-3 grid gap-2 text-sm text-muted-foreground" data-testid="dynamic-questions">
                {(result.analysis.questions || []).map((q, i) => <li key={i}>• {q}</li>)}
              </ul>
            </div>
            {result.analysis.risks?.length > 0 && (
              <div className="surface p-6 lg:col-span-3 border-amber-500/40">
                <p className="overline flex items-center gap-2 text-amber-500">
                  <AlertTriangle className="h-4 w-4" /> Pontos de atenção
                </p>
                <ul className="mt-3 grid sm:grid-cols-2 gap-2 text-sm text-muted-foreground">
                  {result.analysis.risks.map((r, i) => <li key={i}>• {r}</li>)}
                </ul>
              </div>
            )}
          </div>

          <EstimationView est={result.estimation} />

          <div className="surface p-6 flex flex-col lg:flex-row gap-4 lg:items-center">
            <div className="flex-1">
              <p className="overline">Guardar esta obra</p>
              <Input
                value={name} onChange={(e) => setName(e.target.value)} data-testid="project-name-input"
                placeholder="Nome do projeto" className="mt-3 rounded-sm"
              />
            </div>
            <div className="flex flex-wrap gap-3">
              <Button onClick={save} disabled={saving} data-testid="save-project-btn" className="rounded-sm gap-2 hover:bg-orange-600 hover:text-white">
                <Save className="h-4 w-4" /> {user ? "Guardar o meu projeto" : "Entrar e guardar"}
              </Button>
              <Button
                variant="outline"
                className="rounded-sm gap-2"
                data-testid="goto-prices-btn"
                onClick={async () => {
                  try {
                    // Récupérer les matériaux liés à l'estimation en cours
                    const lots = (result?.estimation?.lots || [])
                      .map((l) => ({ key: l.key, quantity: l.quantity }));
                    if (lots.length === 0) { navigate("/prix"); return; }
                    const { data } = await api.post("/estimation/materials", { lots });
                    // Empiler les termes de recherche pour PriceSearch
                    sessionStorage.setItem(
                      "construpilot_price_search_batch",
                      JSON.stringify({
                        items: data.items || [],
                        source: "smart_project",
                        project_name: name || result?.analysis?.summary?.slice(0, 40) || "Mon projet",
                        total_avg: result?.estimation?.total_avg || 0,
                        ts: Date.now(),
                      })
                    );
                    navigate("/prix?from=smart-project");
                  } catch (e) {
                    toast.error("Impossível recuperar os materiais");
                    navigate("/prix");
                  }
                }}
              >
                <ShoppingCart className="h-4 w-4" /> Comparar os preços materiais
              </Button>
              <LeadDialog budget={result.estimation.total_avg} description={description} />
            </div>
          </div>
          <p className="text-xs text-muted-foreground -mt-8">
            Estimation moyenne : <span className="num">{eur(result.estimation.total_avg)}</span> — indicativa, calculada pelo motor determinista ConstruPilot (preços de referência regionais).
          </p>
        </>
      )}
    </div>
  );
}
