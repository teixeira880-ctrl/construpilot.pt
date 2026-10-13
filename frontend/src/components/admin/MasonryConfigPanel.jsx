import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { Loader2, Save, RotateCcw, Plus, Trash2, Blocks } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { toast } from "sonner";

const RATIOS = [
  { key: "loss_pct", label: "Perdas / quebras", unit: "%", step: 0.5 },
  { key: "cement_kg_per_m2", label: "Cimento (argamassa tradicional)", unit: "kg / m²", step: 0.5 },
  { key: "sand_m3_per_m2", label: "Areia (argamassa tradicional)", unit: "m³ / m²", step: 0.005 },
  { key: "glue_kg_per_m2", label: "Argamassa-cola junta fina", unit: "kg / m²", step: 0.5 },
  { key: "foam_m2_per_can", label: "Espuma PU — rendimento", unit: "m² / cartucho", step: 0.5 },
  { key: "gobetis_kg_per_m2", label: "Chapisco de aderência", unit: "kg / m²", step: 0.5 },
  { key: "render_kg_per_m2", label: "Corpo de reboco de fachada", unit: "kg / m²", step: 0.5 },
];

const EMPTY_BLOCK = { key: "", label: "", material: "parpaing", blocks_per_m2: 10, price: 1, search: "" };

export default function MasonryConfigPanel() {
  const [cfg, setCfg] = useState(null);
  const [saving, setSaving] = useState(false);

  const load = () => api.get("/estimation/masonry-config").then(({ data }) => setCfg(data))
    .catch(() => toast.error("Configuração de alvenaria indisponível"));
  useEffect(() => { load(); }, []);

  const setRatio = (k, v) => setCfg((c) => ({ ...c, ratios: { ...c.ratios, [k]: v } }));
  const setBlock = (i, patch) => setCfg((c) => ({
    ...c, blocks: c.blocks.map((b, j) => (j === i ? { ...b, ...patch } : b)),
  }));
  const addBlock = () => setCfg((c) => ({ ...c, blocks: [...c.blocks, { ...EMPTY_BLOCK, key: `bloc_${Date.now()}` }] }));
  const delBlock = (i) => setCfg((c) => ({ ...c, blocks: c.blocks.filter((_, j) => j !== i) }));

  const save = async () => {
    const bad = cfg.blocks.find((b) => !b.label.trim() || !(Number(b.blocks_per_m2) > 0));
    if (bad) { toast.error("Cada bloco deve ter uma designação e um número de blocos/m² > 0"); return; }
    setSaving(true);
    try {
      const body = {
        ratios: Object.fromEntries(Object.entries(cfg.ratios).map(([k, v]) => [k, Number(v)])),
        blocks: cfg.blocks.map((b) => ({
          ...b, key: b.key || b.label.toLowerCase().replace(/[^a-z0-9]+/g, "_"),
          blocks_per_m2: Number(b.blocks_per_m2), price: Number(b.price) || 0,
          search: b.search || b.label.toLowerCase(),
        })),
      };
      const { data } = await api.put("/estimation/masonry-config", body);
      setCfg(data);
      toast.success("Rácios de alvenaria guardados");
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Não foi possível guardar");
    } finally { setSaving(false); }
  };

  const reset = async () => {
    if (!window.confirm("Voltar aos rácios e blocos predefinidos?")) return;
    try {
      const { data } = await api.post("/estimation/masonry-config/reset");
      setCfg(data);
      toast.success("Valores predefinidos restaurados");
    } catch { toast.error("Reinício impossível"); }
  };

  if (!cfg) return <div className="flex items-center gap-2 text-sm text-muted-foreground"><Loader2 className="h-4 w-4 animate-spin" /> A carregar…</div>;

  return (
    <div className="space-y-6" data-testid="admin-masonry-panel">
      <div className="flex items-center justify-between gap-4">
        <div>
          <h3 className="font-display font-bold text-lg flex items-center gap-2"><Blocks className="h-5 w-5 text-primary" /> Alvenaria — rácios e blocos</h3>
          <p className="text-sm text-muted-foreground">Estes valores controlam os cálculos de bloco / tijolo, ligantes e reboco de fachada no orçamento por divisão e no cesto de materiais.</p>
        </div>
        <div className="flex gap-2 shrink-0">
          <Button variant="outline" size="sm" className="rounded-sm gap-2" onClick={reset} data-testid="admin-masonry-reset">
            <RotateCcw className="h-4 w-4" /> Defeitos
          </Button>
          <Button size="sm" className="rounded-sm gap-2" onClick={save} disabled={saving} data-testid="admin-masonry-save">
            {saving ? <Loader2 className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4" />} Guardar
          </Button>
        </div>
      </div>

      <div className="surface p-5 rounded-md">
        <p className="overline text-[10px] mb-3">Rácios por m² de parede</p>
        <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {RATIOS.map((r) => (
            <label key={r.key} className="text-xs">
              <span className="block text-muted-foreground mb-1">{r.label} <span className="opacity-70">({r.unit})</span></span>
              <Input type="number" step={r.step} min={0} value={cfg.ratios[r.key] ?? ""}
                onChange={(e) => setRatio(r.key, e.target.value)}
                data-testid={`admin-masonry-ratio-${r.key}`} className="h-9 num" />
            </label>
          ))}
        </div>
      </div>

      <div className="surface p-5 rounded-md">
        <div className="flex items-center justify-between mb-3">
          <p className="overline text-[10px]">Blocos disponíveis (dimensões propostas ao utilizador)</p>
          <Button variant="outline" size="sm" className="rounded-sm gap-2" onClick={addBlock} data-testid="admin-masonry-add-block">
            <Plus className="h-4 w-4" /> Adicionar um bloco
          </Button>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-xs">
            <thead>
              <tr className="text-left text-muted-foreground border-b border-border">
                <th className="py-2 pr-3 font-medium">Descrição</th>
                <th className="py-2 pr-3 font-medium">Material</th>
                <th className="py-2 pr-3 font-medium">Blocos / m²</th>
                <th className="py-2 pr-3 font-medium">Preço unit. (€)</th>
                <th className="py-2 pr-3 font-medium">Pesquisa de fornecedor</th>
                <th className="py-2" />
              </tr>
            </thead>
            <tbody>
              {cfg.blocks.map((b, i) => (
                <tr key={b.key || i} className="border-b border-border/40" data-testid={`admin-masonry-block-row-${i}`}>
                  <td className="py-1.5 pr-3 min-w-[200px]">
                    <Input value={b.label} onChange={(e) => setBlock(i, { label: e.target.value })}
                      placeholder="Bloco furado 20×20×50" className="h-8" data-testid={`admin-masonry-block-label-${i}`} />
                  </td>
                  <td className="py-1.5 pr-3">
                    <select value={b.material} onChange={(e) => setBlock(i, { material: e.target.value })}
                      className="h-8 rounded-md border border-border bg-background px-2" data-testid={`admin-masonry-block-material-${i}`}>
                      <option value="parpaing">Bloco de betão</option>
                      <option value="brique">Tijolo</option>
                    </select>
                  </td>
                  <td className="py-1.5 pr-3 w-28">
                    <Input type="number" step={0.5} min={0} value={b.blocks_per_m2}
                      onChange={(e) => setBlock(i, { blocks_per_m2: e.target.value })} className="h-8 num" data-testid={`admin-masonry-block-per-m2-${i}`} />
                  </td>
                  <td className="py-1.5 pr-3 w-28">
                    <Input type="number" step={0.05} min={0} value={b.price}
                      onChange={(e) => setBlock(i, { price: e.target.value })} className="h-8 num" data-testid={`admin-masonry-block-price-${i}`} />
                  </td>
                  <td className="py-1.5 pr-3 min-w-[200px]">
                    <Input value={b.search || ""} onChange={(e) => setBlock(i, { search: e.target.value })}
                      placeholder="bloco furado 20x20x50" className="h-8" data-testid={`admin-masonry-block-search-${i}`} />
                  </td>
                  <td className="py-1.5">
                    <Button variant="ghost" size="icon" className="h-8 w-8 text-red-500" onClick={() => delBlock(i)} data-testid={`admin-masonry-block-delete-${i}`}>
                      <Trash2 className="h-4 w-4" />
                    </Button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="text-[10px] text-muted-foreground mt-3">
          Referências: bloco furado 20×20×50 ≈ 10 blocos/m² · tijolo vermelho 22×10,5×6 ≈ 48/m² · tijolo monomuro 50×20×30 ≈ 16/m².
        </p>
      </div>
    </div>
  );
}
