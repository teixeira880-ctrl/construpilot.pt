import { useEffect, useRef, useState } from "react";
import { toast } from "sonner";
import { Loader2, Sparkles, ImagePlus, Upload, Trash2, Download, Wand2, X, FileText, Globe, Info } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { PrivateImage, downloadAssistantFile } from "@/components/assistant/PrivateMedia";
import { useConfirm } from "@/components/ConfirmProvider";
import { api } from "@/lib/api";

// Estúdio de imagens IA (porta de pages/ImageStudio.jsx do .fr). Geração só a pedido (botão «Gerar»);
// cada imagem traz no próprio ficheiro a faixa «Ilustração IA não contratual».
const LABEL = "Ilustração IA não contratual";
const PROVIDERS = [
  { id: "openai", label: "GPT Image 1", hint: "Texto → imagem, alta qualidade" },
  { id: "gemini", label: "Nano Banana", hint: "Edição a partir de uma fotografia de referência" },
];
const detailOf = (e, fallback) => {
  const d = e?.response?.data?.detail;
  return typeof d === "string" ? d : fallback;
};

export default function EstudioImagens() {
  const confirm = useConfirm();
  const [prompt, setPrompt] = useState("");
  const [provider, setProvider] = useState("openai");
  const [refImage, setRefImage] = useState(null); // {b64, name, preview}
  const [busy, setBusy] = useState(false);
  const [gallery, setGallery] = useState([]);
  const [loading, setLoading] = useState(true);
  const fileRef = useRef();

  const load = async () => {
    try { const { data } = await api.get("/image-studio/images"); setGallery(data.images || []); }
    catch { /* silencioso: galeria vazia */ } finally { setLoading(false); }
  };
  useEffect(() => { load(); }, []);

  const pickRef = (e) => {
    const f = e.target.files?.[0];
    if (!f) return;
    if (f.size > 10 * 1024 * 1024) { toast.error("Imagem de referência demasiado volumosa (máx. 10 MB)."); return; }
    const reader = new FileReader();
    reader.onload = () => { setRefImage({ b64: reader.result, name: f.name, preview: reader.result }); setProvider("gemini"); };
    reader.readAsDataURL(f);
  };

  const generate = async () => {
    if (prompt.trim().length < 3) { toast.error("Descreva a imagem a gerar."); return; }
    setBusy(true);
    try {
      const { data } = await api.post("/image-studio/generate", {
        prompt: prompt.trim(),
        provider: refImage ? "gemini" : provider,
        number: 1,
        reference_image_b64: refImage?.b64 || null,
      }, { timeout: 180000 });
      if (data.images?.length) { toast.success(`Imagem gerada — ${LABEL.toLowerCase()}.`); await load(); }
      else toast.error("Nenhuma imagem devolvida: reformule o pedido.");
    } catch (e) {
      toast.error(detailOf(e, "Geração impossível."));
    } finally { setBusy(false); }
  };

  const remove = async (id) => {
    if (!(await confirm({ title: "Eliminar esta imagem?", description: "A imagem deixa de aparecer na sua galeria.", confirmLabel: "Eliminar", destructive: true }))) return;
    setGallery((g) => g.filter((x) => x.image_id !== id));
    try { await api.delete(`/image-studio/images/${id}`); } catch { toast.error("Eliminação impossível."); load(); }
  };

  const reuseImage = async (id, target) => {
    try {
      await api.post(`/image-studio/images/${id}/use`, { target });
      toast.success(target === "quote_header" ? "Definida como cabeçalho dos seus orçamentos." : "Acrescentada à sua página pública.");
    } catch (e) { toast.error(detailOf(e, "Ação impossível.")); }
  };

  const activeProvider = refImage ? "gemini" : provider;

  return (
    <div className="max-w-5xl mx-auto px-4 py-6 space-y-6" data-testid="image-studio-page">
      <header className="space-y-1">
        <h1 className="text-3xl sm:text-4xl font-semibold tracking-tight flex items-center gap-2">
          <Sparkles className="h-7 w-7 text-primary" aria-hidden="true" /> Estúdio de imagens IA
        </h1>
        <p className="text-sm text-muted-foreground max-w-2xl">
          Crie visuais a partir de um texto (GPT Image 1) ou transforme uma fotografia de referência — terreno, fachada, divisão —
          numa ilustração realista (Nano Banana). Útil para apresentações de projeto, inserções e comunicação.
        </p>
      </header>

      <div className="flex items-start gap-2 rounded-lg border border-amber-300 bg-amber-50 px-3 py-2 text-sm text-amber-900" role="note" data-testid="image-studio-disclaimer">
        <Info className="h-4 w-4 mt-0.5 shrink-0" aria-hidden="true" />
        <p><strong>{LABEL}.</strong> As imagens são geradas por IA apenas quando clica em «Gerar», trazem esta menção no próprio ficheiro e
          não substituem plantas, projetos de especialidades nem fotografias reais da obra. Cada geração é contabilizada nos custos de IA.</p>
      </div>

      <section className="rounded-2xl border bg-card p-4 sm:p-6 space-y-4 shadow-sm">
        <div className="flex flex-wrap gap-2" data-testid="provider-toggle" role="radiogroup" aria-label="Motor de imagem">
          {PROVIDERS.map((p) => (
            <button key={p.id} type="button" role="radio" aria-checked={activeProvider === p.id}
              onClick={() => { if (p.id === "openai") setRefImage(null); setProvider(p.id); }}
              className={`flex-1 min-w-[150px] text-left px-4 py-3 rounded-xl border transition-colors ${activeProvider === p.id ? "border-primary bg-primary/5 ring-1 ring-primary" : "hover:bg-secondary/50"}`}
              data-testid={`provider-${p.id}`}>
              <div className="font-medium text-sm flex items-center gap-1.5"><Wand2 className="h-4 w-4" aria-hidden="true" /> {p.label}</div>
              <div className="text-xs text-muted-foreground mt-0.5">{p.hint}</div>
            </button>
          ))}
        </div>

        <Textarea value={prompt} onChange={(e) => setPrompt(e.target.value)} rows={4} aria-label="Descrição da imagem"
          placeholder={activeProvider === "gemini" ? "Ex.: acrescente uma moradia contemporânea de cobertura plana neste terreno, à escala, com sombras coerentes" : "Ex.: banner para o site de uma empresa de construção, obra moderna ao pôr do sol, estilo limpo"}
          className="resize-none" data-testid="prompt-input" />

        <div className="flex flex-wrap items-center gap-3">
          <input ref={fileRef} type="file" accept="image/png,image/jpeg,image/webp" className="hidden" onChange={pickRef} data-testid="ref-image-input" />
          {refImage ? (
            <div className="flex items-center gap-2 rounded-lg border px-2 py-1.5" data-testid="ref-image-chip">
              <img src={refImage.preview} alt="Fotografia de referência" className="h-9 w-9 rounded object-cover" />
              <span className="text-xs max-w-[140px] truncate">{refImage.name}</span>
              <button type="button" aria-label="Retirar a fotografia de referência" onClick={() => { setRefImage(null); if (fileRef.current) fileRef.current.value = ""; }} data-testid="ref-image-clear"><X className="h-4 w-4 text-muted-foreground" /></button>
            </div>
          ) : (
            <Button type="button" variant="outline" onClick={() => fileRef.current?.click()} data-testid="ref-image-btn">
              <Upload className="h-4 w-4" /> Fotografia de referência (opcional)
            </Button>
          )}
          <Button onClick={generate} disabled={busy} className="ml-auto" data-testid="generate-btn">
            {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <ImagePlus className="h-4 w-4" />}
            {busy ? "A gerar…" : "Gerar a imagem"}
          </Button>
        </div>
        <p className="text-[11px] text-muted-foreground">A geração pode demorar até cerca de 1 minuto. Limite: 30 imagens por 24 h.</p>
      </section>

      <section className="space-y-3">
        <h2 className="text-base font-medium">As minhas imagens ({gallery.length})</h2>
        {loading ? (
          <div className="flex items-center gap-2 text-sm text-muted-foreground" role="status"><Loader2 className="h-4 w-4 animate-spin" /> A carregar…</div>
        ) : gallery.length === 0 ? (
          <p className="text-sm text-muted-foreground" data-testid="gallery-empty">Ainda não há imagens — lance a primeira geração acima.</p>
        ) : (
          <div className="grid grid-cols-1 min-[420px]:grid-cols-2 sm:grid-cols-3 gap-3" data-testid="gallery-grid">
            {gallery.map((img) => (
              <div key={img.image_id} className="rounded-xl border overflow-hidden bg-card" data-testid={`gallery-item-${img.image_id}`}>
                <PrivateImage path={img.url} title={img.prompt || LABEL} testId={`gallery-img-${img.image_id}`} />
                <div className="px-2 pt-1.5 text-[10px] font-medium text-amber-800" data-testid={`gallery-label-${img.image_id}`}>{LABEL}</div>
                <div className="flex items-center justify-between px-2 py-1.5 border-t mt-1">
                  <span className="text-[10px] uppercase tracking-wide text-muted-foreground">{img.provider === "gemini" ? "Nano Banana" : "GPT Image 1"}</span>
                  <div className="flex gap-0.5">
                    <button type="button" onClick={() => reuseImage(img.image_id, "quote_header")} title="Usar como cabeçalho dos orçamentos" aria-label="Usar como cabeçalho dos orçamentos" data-testid={`gallery-use-quote-${img.image_id}`} className="p-2 rounded hover:bg-secondary"><FileText className="h-4 w-4" /></button>
                    <button type="button" onClick={() => reuseImage(img.image_id, "public_page")} title="Acrescentar à minha página pública" aria-label="Acrescentar à minha página pública" data-testid={`gallery-use-page-${img.image_id}`} className="p-2 rounded hover:bg-secondary"><Globe className="h-4 w-4" /></button>
                    <button type="button" onClick={() => downloadAssistantFile(img.url, `Ilustracao-IA-${img.image_id}.jpg`).catch(() => toast.error("Descarga impossível."))} title="Descarregar" aria-label="Descarregar" data-testid={`gallery-download-${img.image_id}`} className="p-2 rounded hover:bg-secondary"><Download className="h-4 w-4" /></button>
                    <button type="button" onClick={() => remove(img.image_id)} title="Eliminar" aria-label="Eliminar" data-testid={`gallery-delete-${img.image_id}`} className="p-2 rounded hover:bg-secondary text-red-600"><Trash2 className="h-4 w-4" /></button>
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </section>
    </div>
  );
}
