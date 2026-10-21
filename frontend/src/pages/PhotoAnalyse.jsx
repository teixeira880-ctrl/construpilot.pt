import { useState } from "react";
import { toast } from "sonner";
import { Camera, Upload, Sparkles, AlertTriangle, Info } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { api, num } from "@/lib/api";
import { EstimationView } from "@/components/EstimationView";
import { SectionTitle } from "@/components/Bits";
import { SEO } from "@/components/SEO";

export default function PhotoAnalyse() {
  const [preview, setPreview] = useState(null);
  const [b64, setB64] = useState(null);
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState(null);
  const [dims, setDims] = useState({ length_m: "", width_m: "", height_m: "" });

  const onFile = (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    if (!/image\/(jpeg|png|webp|jpg)/.test(file.type)) {
      toast.error("Formatos aceites: JPEG, PNG, WEBP");
      return;
    }
    const reader = new FileReader();
    reader.onload = () => {
      setPreview(reader.result);
      setB64(String(reader.result).split(",")[1]);
      setResult(null);
    };
    reader.readAsDataURL(file);
  };

  const analyse = async () => {
    if (!b64) return toast.error("Importe uma foto");
    setBusy(true);
    try {
      const { data } = await api.post("/vision/photo", { image_base64: b64, note });
      setResult(data);
      const d = data.analysis.estimated_dimensions || {};
      setDims({ length_m: d.length_m || "", width_m: d.width_m || "", height_m: d.height_m || "" });
    } catch {
      toast.error("Análise impossível");
    } finally {
      setBusy(false);
    }
  };

  const recompute = async () => {
    const area = Number(dims.length_m) * Number(dims.width_m);
    if (!area) return toast.error("Indique comprimento e largura");
    setBusy(true);
    try {
      const room = (result.analysis.room_type || "").toLowerCase();
      const type = room.includes("bain") ? "salle_de_bain" : room.includes("cuisine") ? "cuisine" : "renovation_appartement";
      const { data } = await api.post("/estimation/compute", {
        project_type: type, surface: area, finish_level: "standard",
        condition: result.analysis.general_condition || "moyen",
        lots: (result.analysis.recommended_works || []).map((w) => w.lot).filter(Boolean),
      });
      setResult({ ...result, estimation: data, confirmed: true });
      toast.success("Estimativa recalculada com as suas dimensões confirmadas");
    } catch { toast.error("Recálculo impossível"); }
    finally { setBusy(false); }
  };

  return (
    <div className="grid gap-10">
      <SEO title="Análise fotografia obra IA" description="Tire uma foto da sua divisão: a IA ConstruPilot identifica o estado, os trabalhos necessários e orçamenta a renovação em 30 segundos. Gratuito." keywords="análise de fotografias de obras, estimativa por fotografia, IA remodelação fotografia, estimativa de obra por fotografia" canonical="/photo" />
      <SectionTitle as="h1" over="Estimativa por IA a partir de fotos" title="Fotografe, a IA identifica os trabalhos">
        Paredes, pavimentos, tetos, aberturas, sanitários, estado geral: a IA propõe os trabalhos prováveis. As medições são aproximadas — confirme-as antes de qualquer cálculo definitivo.
      </SectionTitle>

      <div className="grid lg:grid-cols-2 gap-6">
        <div className="surface p-6 grid gap-5">
          <div className="grid gap-2">
            <Label>Foto da divisão</Label>
            <label
              htmlFor="photo-input"
              className="border border-dashed border-border rounded-sm p-8 text-center cursor-pointer hover:border-primary transition-colors"
              data-testid="photo-dropzone"
            >
              {preview ? (
                <img src={preview} alt="Pré-visualização" className="max-h-64 mx-auto rounded-sm object-contain" />
              ) : (
                <>
                  <Upload className="h-7 w-7 mx-auto text-muted-foreground" />
                  <p className="mt-3 text-sm text-muted-foreground">Clique para importar ou tirar uma foto</p>
                  <p className="text-xs text-muted-foreground mt-1">JPEG, PNG ou WEBP</p>
                </>
              )}
            </label>
            <input id="photo-input" type="file" accept="image/jpeg,image/png,image/webp" capture="environment" onChange={onFile} className="hidden" data-testid="photo-input" />
          </div>
          <div className="grid gap-2">
            <Label>Precisão (opcional)</Label>
            <Input value={note} onChange={(e) => setNote(e.target.value)} placeholder="Ex: a divisão mede cerca de 8 m²" data-testid="photo-note-input" className="rounded-sm" />
          </div>
          <Button onClick={analyse} disabled={busy || !b64} data-testid="analyse-photo-btn" className="rounded-sm gap-2 hover:bg-orange-600 hover:text-white">
            <Sparkles className="h-4 w-4" /> {busy ? "Análise em curso…" : "Analisar a foto"}
          </Button>
        </div>

        {result && (
          <div className="surface p-6 grid gap-5" data-testid="photo-analysis-result">
            <div>
              <p className="overline">Divisão identificada</p>
              <p className="mt-2 font-display text-xl font-semibold">{result.analysis.room_type}</p>
              <div className="mt-3 flex flex-wrap gap-2">
                <Badge variant="outline" className="rounded-sm">Estado: {result.analysis.general_condition}</Badge>
                <Badge variant="outline" className="rounded-sm">Confiança: {result.analysis.confidence}</Badge>
                <Badge variant="outline" className="rounded-sm num">
                  ≈ {num(result.analysis.estimated_dimensions?.floor_area_m2, 1)} m²
                </Badge>
              </div>
            </div>

            {result.analysis.elements && (
              <div className="grid sm:grid-cols-2 gap-2 text-sm">
                {Object.entries(result.analysis.elements).map(([k, v]) => (
                  <p key={k} className="flex gap-2">
                    <span className="text-muted-foreground capitalize">{k} :</span>
                    <span>{String(v)}</span>
                  </p>
                ))}
              </div>
            )}

            <div>
              <p className="overline">Trabalhos recomendados</p>
              <ul className="mt-3 grid gap-2 text-sm" data-testid="recommended-works">
                {(result.analysis.recommended_works || []).map((w, i) => (
                  <li key={i}>
                    <span className="font-medium">{w.name}</span>
                    <span className="text-muted-foreground"> — {w.reason}</span>
                  </li>
                ))}
              </ul>
            </div>

            {result.analysis.risks?.length > 0 && (
              <div className="p-4 rounded-sm border border-amber-500/40 bg-amber-500/5">
                <p className="overline text-amber-500 flex items-center gap-2"><AlertTriangle className="h-4 w-4" /> Riscos visíveis</p>
                <ul className="mt-2 text-sm text-muted-foreground grid gap-1">
                  {result.analysis.risks.map((r, i) => <li key={i}>• {r}</li>)}
                </ul>
              </div>
            )}

            <Alert className="rounded-sm border-primary/40">
              <Info className="h-4 w-4 text-primary" />
              <AlertDescription className="text-xs">{result.analysis.disclaimer}</AlertDescription>
            </Alert>

            <div>
              <p className="overline">Confirme as dimensões</p>
              <div className="mt-3 grid grid-cols-3 gap-3">
                {["length_m", "width_m", "height_m"].map((k) => (
                  <Input
                    key={k} type="number" step="any" value={dims[k]}
                    onChange={(e) => setDims({ ...dims, [k]: e.target.value })}
                    placeholder={k === "length_m" ? "Comprimento" : k === "width_m" ? "Largura" : "Altura"}
                    data-testid={`dim-${k}`} className="rounded-sm num"
                  />
                ))}
              </div>
              <Button onClick={recompute} disabled={busy} variant="outline" data-testid="confirm-dims-btn" className="mt-4 rounded-sm w-full">
                Recalcular com estas dimensões
              </Button>
            </div>
          </div>
        )}
      </div>

      {result?.estimation && (
        <>
          <div className="flex items-center gap-3">
            <Camera className="h-5 w-5 text-primary" />
            <h2 className="font-display text-2xl font-bold tracking-tight">
              Estimativa {result.confirmed ? "confirmada" : "preliminar"}
            </h2>
          </div>
          <EstimationView est={result.estimation} />
        </>
      )}
    </div>
  );
}
