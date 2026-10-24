import { useEffect, useState } from "react";
import { toast } from "sonner";
import { FileSearch, Upload, Sparkles, Scale, Trophy } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Badge } from "@/components/ui/badge";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { api, eur, eur2, num } from "@/lib/api";
import { SectionTitle } from "@/components/Bits";
import { SEO } from "@/components/SEO";
import { LeadDialog } from "@/components/LeadDialog";
import { useAuth } from "@/context/AuthContext";

const VERDICT = {
  bas: { label: "Preço baixo", cls: "border-emerald-500/40 text-emerald-600 dark:text-emerald-400" },
  correct: { label: "Preço correto", cls: "border-sky-500/40 text-sky-600 dark:text-sky-400" },
  eleve: { label: "Preço elevado", cls: "border-amber-500/40 text-amber-600 dark:text-amber-400" },
  tres_eleve: { label: "Muito elevado", cls: "border-red-500/40 text-red-600 dark:text-red-400" },
};

export default function QuoteScanner() {
  const { user } = useAuth();
  const [company, setCompany] = useState("");
  const [text, setText] = useState("");
  const [b64, setB64] = useState(null);
  const [pdfB64, setPdfB64] = useState(null);
  const [pdfName, setPdfName] = useState("");
  const [preview, setPreview] = useState(null);
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState(null);
  const [saved, setSaved] = useState([]);
  const [selected, setSelected] = useState([]);
  const [comparison, setComparison] = useState(null);

  const loadSaved = () => {
    if (!user) return;
    api.get("/quotes").then(({ data }) => setSaved(data)).catch(() => {});
  };
  useEffect(loadSaved, [user]);

  const onFile = (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    const isPdf = file.type === "application/pdf" || file.name.toLowerCase().endsWith(".pdf");
    const isImg = /image\/(jpeg|png|webp|jpg)/.test(file.type);
    if (!isPdf && !isImg) return toast.error("Formatos aceites: JPEG, PNG, WEBP ou PDF");
    if (file.size > 15 * 1024 * 1024) return toast.error("Ficheiro demasiado pesado (máx. 15 MB)");
    const reader = new FileReader();
    reader.onload = () => {
      const b64only = String(reader.result).split(",")[1];
      if (isPdf) {
        setPdfB64(b64only);
        setPdfName(file.name);
        setPreview(null);
        setB64(null);
      } else {
        setPreview(reader.result);
        setB64(b64only);
        setPdfB64(null);
        setPdfName("");
      }
    };
    reader.readAsDataURL(file);
  };

  const analyse = async () => {
    if (!b64 && !pdfB64 && text.trim().length < 20) {
      return toast.error("Importe uma foto, um PDF ou cole o texto do orçamento");
    }
    setBusy(true);
    try {
      const { data } = await api.post("/quotes/analyse", {
        text, image_base64: b64, pdf_base64: pdfB64, company,
      });
      setResult(data);
      loadSaved();
      toast.success("Orçamento analisado");
    } catch (err) {
      toast.error(err?.response?.data?.detail || "Análise impossível");
    } finally {
      setBusy(false);
    }
  };

  const compare = async () => {
    if (selected.length < 2) return toast.error("Selecione pelo menos 2 orçamentos");
    setBusy(true);
    try {
      const { data } = await api.post("/quotes/compare", { quote_ids: selected });
      setComparison(data);
    } catch { toast.error("Comparação impossível"); }
    finally { setBusy(false); }
  };

  const a = result?.analysis;
  const v = a ? VERDICT[a.verdict] || VERDICT.correct : null;

  return (
    <div className="grid gap-10">
      <SEO title="Digitalizador de orçamentos IA" description="Carregue o seu orçamento PDF: ConstruPilot compara cada linha com os preços de referência 2026 e indica se o orçamento é baixo, correto ou demasiado elevado. Gratuito e sem registo." keywords="análise orçamento obras, verificar preço orçamento, comparador orçamentos, orçamento demasiado caro, IA análise orçamento" canonical="/scanner-devis" />
      <SectionTitle as="h1" over="Digitalizador de faturas e orçamentos" title="Este preço está correto?">
        A IA lê o orçamento, extrai as linhas e compara com a base de preços ConstruPilot: preço baixo, correto, elevado ou muito elevado, com os elementos potencialmente esquecidos.
      </SectionTitle>

      <div className="grid lg:grid-cols-2 gap-6">
        <div className="surface p-6 grid gap-5">
          <div className="grid gap-2">
            <Label>Empresa</Label>
            <Input value={company} onChange={(e) => setCompany(e.target.value)} placeholder="Nome da empresa" data-testid="quote-company-input" className="rounded-sm" />
          </div>
          <div className="grid gap-2">
            <Label>Foto, PDF ou captura do orçamento</Label>
            <label htmlFor="quote-file" className="border border-dashed border-border rounded-sm p-6 text-center cursor-pointer hover:border-primary transition-colors" data-testid="quote-dropzone">
              {preview ? (
                <img src={preview} alt="Orçamento" className="max-h-52 mx-auto object-contain rounded-sm" />
              ) : pdfB64 ? (
                <div className="flex items-center justify-center gap-3 text-sm">
                  <FileSearch className="h-6 w-6 text-primary" />
                  <span className="font-medium">{pdfName || "Orcamento.pdf"}</span>
                  <Badge variant="outline" className="rounded-sm">PDF</Badge>
                </div>
              ) : (
                <>
                  <Upload className="h-6 w-6 mx-auto text-muted-foreground" />
                  <p className="mt-2 text-sm text-muted-foreground">Importar uma imagem ou um PDF do orçamento</p>
                  <p className="mt-1 text-[11px] text-muted-foreground">JPEG · PNG · WEBP · PDF · 15 MB máx</p>
                </>
              )}
            </label>
            <input id="quote-file" type="file" accept="image/jpeg,image/png,image/webp,application/pdf,.pdf" onChange={onFile} className="hidden" data-testid="quote-file-input" />
          </div>
          <div className="grid gap-2">
            <Label>Ou cole o texto do orçamento</Label>
            <Textarea rows={6} value={text} onChange={(e) => setText(e.target.value)} data-testid="quote-text-input" className="rounded-sm" placeholder="Prestação, quantidades, preços unitários, total…" />
          </div>
          <Button onClick={analyse} disabled={busy} data-testid="analyse-quote-btn" className="rounded-sm gap-2 hover:bg-orange-600 hover:text-white">
            <Sparkles className="h-4 w-4" /> {busy ? "Análise…" : "Analisar este orçamento"}
          </Button>
        </div>

        {a && (
          <div className="surface p-6 grid gap-5" data-testid="quote-analysis-result">
            <div className="flex items-start justify-between gap-4">
              <div>
                <p className="overline">{a.company || company || "Empresa"}</p>
                <p className="num mt-2 text-2xl font-bold">{eur(a.total_ttc || a.total_ht)}</p>
              </div>
              <Badge variant="outline" className={`rounded-sm ${v.cls}`} data-testid="quote-verdict">{v.label}</Badge>
            </div>
            <p className="text-sm text-muted-foreground">{a.verdict_label}</p>
            {a.delta_vs_reference_pct !== undefined && a.delta_vs_reference_pct !== null && (
              <p className="num text-sm">
                Desvio vs preço de referência ConstruPilot:{" "}
                <span className={a.delta_vs_reference_pct > 0 ? "text-red-500 font-semibold" : "text-emerald-500 font-semibold"}>
                  {a.delta_vs_reference_pct > 0 ? "+" : ""}{num(a.delta_vs_reference_pct, 1)} %
                </span>
              </p>
            )}
            {a.lines?.length > 0 && (
              <div className="overflow-x-auto border border-border rounded-sm">
                <Table>
                  <TableHeader>
                    <TableRow className="bg-secondary/60 hover:bg-secondary/60">
                      <TableHead>Prestação</TableHead>
                      <TableHead className="text-right">Qtd.</TableHead>
                      <TableHead className="text-right">PU</TableHead>
                      <TableHead className="text-right">Total</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {a.lines.map((l, i) => (
                      <TableRow key={i} className="even:bg-muted/30">
                        <TableCell>{l.label}</TableCell>
                        <TableCell className="num text-right">{num(l.quantity, 2)} {l.unit}</TableCell>
                        <TableCell className="num text-right">{eur2(l.unit_price)}</TableCell>
                        <TableCell className="num text-right font-semibold">{eur2(l.total)}</TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </div>
            )}
            {[["Elementos potencialmente esquecidos", a.missing_items], ["Exclusões", a.exclusions],
              ["Garantias", a.warranties], ["Conselhos de negociação", a.negotiation_tips]].map(([label, arr]) =>
              arr?.length > 0 ? (
                <div key={label}>
                  <p className="overline text-muted-foreground">{label}</p>
                  <ul className="mt-2 grid gap-1 text-sm text-muted-foreground">
                    {arr.map((x, i) => <li key={i}>• {x}</li>)}
                  </ul>
                </div>
              ) : null
            )}
            <LeadDialog label="Comparar com uma proposta ConstruPilot" budget={a.total_ttc || a.total_ht} />
          </div>
        )}
      </div>

      {saved.length > 0 && (
        <div className="grid gap-4">
          <div className="flex flex-wrap items-center gap-3">
            <h2 className="font-display text-xl font-bold tracking-tight flex items-center gap-2">
              <Scale className="h-5 w-5 text-primary" /> Comparação de orçamentos
            </h2>
            <Button variant="outline" size="sm" onClick={compare} disabled={busy} data-testid="compare-quotes-btn" className="rounded-sm ml-auto">
              Comparar a seleção ({selected.length})
            </Button>
          </div>
          <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-3" data-testid="saved-quotes">
            {saved.map((q) => {
              const on = selected.includes(q.quote_id);
              return (
                <button
                  key={q.quote_id} data-testid={`select-quote-${q.quote_id}`}
                  onClick={() => setSelected(on ? selected.filter((x) => x !== q.quote_id) : [...selected, q.quote_id])}
                  className={`surface p-5 text-left transition-colors ${on ? "border-primary bg-primary/5" : "hover:border-primary/50"}`}
                >
                  <p className="overline text-muted-foreground">{q.company || "Empresa"}</p>
                  <p className="num mt-2 text-lg font-bold">{eur(q.analysis?.total_ttc || q.analysis?.total_ht)}</p>
                  <Badge variant="outline" className={`mt-3 rounded-sm ${(VERDICT[q.analysis?.verdict] || VERDICT.correct).cls}`}>
                    {(VERDICT[q.analysis?.verdict] || VERDICT.correct).label}
                  </Badge>
                </button>
              );
            })}
          </div>

          {comparison && (
            <div className="surface p-6 grid gap-5" data-testid="quote-comparison-result">
              <div>
                <p className="overline flex items-center gap-2"><Trophy className="h-4 w-4" /> Classificação</p>
                <div className="mt-4 grid gap-3">
                  {(comparison.ranking || []).map((r, i) => (
                    <div key={i} className="flex flex-wrap items-center gap-4 border-b border-border pb-3">
                      <span className="num text-primary font-bold">#{i + 1}</span>
                      <span className="font-medium">{r.company}</span>
                      <span className="num ml-auto font-semibold">{eur(r.total)}</span>
                      <Badge variant="outline" className="rounded-sm num">{r.score}/100</Badge>
                      <p className="w-full text-xs text-muted-foreground">{r.comment}</p>
                    </div>
                  ))}
                </div>
              </div>
              {comparison.best_value && (
                <p className="text-sm">
                  <span className="text-muted-foreground">Melhor relação qualidade/preço: </span>
                  <span className="font-semibold text-primary">{comparison.best_value}</span>
                </p>
              )}
              {[["Diferenças importantes", comparison.differences], ["Elementos esquecidos", comparison.missing_items]]
                .map(([label, arr]) => arr?.length > 0 ? (
                  <div key={label}>
                    <p className="overline text-muted-foreground">{label}</p>
                    <ul className="mt-2 grid gap-1 text-sm text-muted-foreground">
                      {arr.map((x, i) => <li key={i}>• {x}</li>)}
                    </ul>
                  </div>
                ) : null)}
              {comparison.recommendation && (
                <div className="p-4 rounded-sm border border-primary/40 bg-primary/5">
                  <p className="overline">Recomendação ConstruPilot</p>
                  <p className="mt-2 text-sm">{comparison.recommendation}</p>
                </div>
              )}
            </div>
          )}
        </div>
      )}

      {!user && (
        <p className="text-xs text-muted-foreground flex items-center gap-2">
          <FileSearch className="h-4 w-4" /> Ligue-se para guardar e comparar vários orçamentos.
        </p>
      )}
    </div>
  );
}
