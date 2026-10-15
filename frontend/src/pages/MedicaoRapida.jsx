import { useState } from "react";
import { toast } from "sonner";
import { Ruler, Calculator } from "lucide-react";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Button } from "@/components/ui/button";
import PromptBar from "@/components/PromptBar";
import { useSwipeBack } from "@/hooks/useSwipeBack";
import { useHaptic } from "@/hooks/useHaptic";

/**
 * Medição Rápida — divisão retangular. Preenchimento manual OU por prompt IA
 * (`/api/prompt-fill/medicoes`). Cálculo totalmente determinístico no cliente:
 *  - paredes_m2  = perímetro × pé-direito
 *  - teto_m2     = L × W
 *  - pavimento_m2 = L × W
 *  - rodapes_m   = perímetro
 *  - volume_m3   = L × W × pé-direito
 */
export default function MedicaoRapida() {
  useSwipeBack();
  const haptic = useHaptic();
  const [form, setForm] = useState({
    divisao: "",
    comprimento_m: "",
    largura_m: "",
    pe_direito_m: "2.60",
  });
  const [res, setRes] = useState(null);

  const applyFill = ({ params = {} }) => {
    setForm((prev) => ({
      ...prev,
      divisao: params.divisao ?? prev.divisao,
      comprimento_m: params.comprimento_m != null ? String(params.comprimento_m) : prev.comprimento_m,
      largura_m: params.largura_m != null ? String(params.largura_m) : prev.largura_m,
      pe_direito_m: params.pe_direito_m != null ? String(params.pe_direito_m) : prev.pe_direito_m,
    }));
  };

  const calcular = () => {
    const L = parseFloat(form.comprimento_m);
    const W = parseFloat(form.largura_m);
    const H = parseFloat(form.pe_direito_m);
    if (!(L > 0 && W > 0 && H > 0)) {
      haptic.error();
      toast.error("Preencha comprimento, largura e pé-direito.");
      return;
    }
    const perim = 2 * (L + W);
    const area = L * W;
    setRes({
      paredes_m2: +(perim * H).toFixed(2),
      teto_m2: +area.toFixed(2),
      pavimento_m2: +area.toFixed(2),
      rodapes_m: +perim.toFixed(2),
      volume_m3: +(area * H).toFixed(2),
    });
    haptic.success();
    toast.success("Medição calculada.");
  };

  return (
    <div className="mx-auto max-w-2xl px-4 py-8" data-testid="medicao-rapida">
      <header className="mb-5">
        <h1 className="text-2xl sm:text-3xl font-bold text-foreground flex items-center gap-2">
          <Ruler className="h-6 w-6 text-primary" aria-hidden="true" /> Medição rápida
        </h1>
        <p className="text-sm text-muted-foreground mt-1">
          Áreas, perímetro e volume de uma divisão retangular. Diga à IA ou preencha à mão.
        </p>
      </header>

      <PromptBar
        appKey="medicoes"
        context={form}
        placeholder="Ex.: «sala de 5 por 4 metros com pé-direito 2,70 m»"
        examples="A IA preenche o form; depois carregue em «Calcular»."
        onFill={applyFill}
      />

      <section className="rounded-xl border border-border bg-card p-4 space-y-3" data-testid="medicao-form">
        <div>
          <Label className="text-xs">Divisão</Label>
          <Input
            value={form.divisao}
            onChange={(e) => setForm((p) => ({ ...p, divisao: e.target.value }))}
            placeholder="Sala, quarto, cozinha…"
            data-testid="medicao-divisao"
          />
        </div>
        <div className="grid grid-cols-2 gap-3">
          <div>
            <Label className="text-xs">Comprimento (m)</Label>
            <Input
              type="number"
              inputMode="decimal"
              step="0.01"
              value={form.comprimento_m}
              onChange={(e) => setForm((p) => ({ ...p, comprimento_m: e.target.value }))}
              placeholder="5.20"
              data-testid="medicao-comprimento"
            />
          </div>
          <div>
            <Label className="text-xs">Largura (m)</Label>
            <Input
              type="number"
              inputMode="decimal"
              step="0.01"
              value={form.largura_m}
              onChange={(e) => setForm((p) => ({ ...p, largura_m: e.target.value }))}
              placeholder="3.80"
              data-testid="medicao-largura"
            />
          </div>
        </div>
        <div>
          <Label className="text-xs">Pé-direito (m)</Label>
          <Input
            type="number"
            inputMode="decimal"
            step="0.01"
            value={form.pe_direito_m}
            onChange={(e) => setForm((p) => ({ ...p, pe_direito_m: e.target.value }))}
            placeholder="2.60"
            data-testid="medicao-pe-direito"
          />
        </div>
        <Button
          onClick={calcular}
          className="w-full min-h-[44px]"
          data-testid="medicao-calcular"
        >
          <Calculator className="h-4 w-4 mr-2" /> Calcular
        </Button>
      </section>

      {res && (
        <section
          className="mt-5 rounded-xl border border-border bg-card p-4"
          data-testid="medicao-resultado"
        >
          <h2 className="font-semibold mb-3">Resultado</h2>
          <ul className="grid grid-cols-2 gap-2 text-sm">
            <li className="bg-muted rounded-md p-2">Paredes <strong className="block text-base">{res.paredes_m2} m²</strong></li>
            <li className="bg-muted rounded-md p-2">Teto <strong className="block text-base">{res.teto_m2} m²</strong></li>
            <li className="bg-muted rounded-md p-2">Pavimento <strong className="block text-base">{res.pavimento_m2} m²</strong></li>
            <li className="bg-muted rounded-md p-2">Rodapés <strong className="block text-base">{res.rodapes_m} m</strong></li>
            <li className="bg-muted rounded-md p-2 col-span-2">Volume <strong className="block text-base">{res.volume_m3} m³</strong></li>
          </ul>
        </section>
      )}
    </div>
  );
}
