import { useEffect, useState } from "react";
import { useParams, Link } from "react-router-dom";
import { toast } from "sonner";
import { Loader2, HardHat, ArrowRight, FileDown } from "lucide-react";
import { api, eur, eur2, num } from "@/lib/api";

export default function SharedCalc() {
  const { shareId } = useParams();
  const [data, setData] = useState(null);
  const [error, setError] = useState(false);
  const [busyPdf, setBusyPdf] = useState(false);

  useEffect(() => {
    api.get(`/calculators-shared/${shareId}`)
      .then(({ data }) => setData(data))
      .catch(() => setError(true));
  }, [shareId]);

  const downloadPdf = async () => {
    setBusyPdf(true);
    try {
      const { data: pdf } = await api.post("/calculators-pdf", {
        name: data.name, inputs: data.inputs, results: data.results,
        materials: data.materials, estimated_budget: data.estimated_budget,
        priced_lines: data.priced_lines || [], priced_total: data.priced_total ?? null,
      }, { responseType: "blob" });
      const url = URL.createObjectURL(new Blob([pdf], { type: "application/pdf" }));
      const a = document.createElement("a");
      a.href = url; a.download = "fiche-calcul-construpilot.pdf";
      document.body.appendChild(a); a.click(); a.remove();
      URL.revokeObjectURL(url);
    } catch { toast.error("Descarga impossível"); }
    finally { setBusyPdf(false); }
  };

  if (error) {
    return (
      <div className="min-h-screen grid place-items-center bg-background text-center px-6">
        <div>
          <p className="font-display text-2xl font-bold">Ficha não encontrada</p>
          <p className="text-muted-foreground mt-2">Este link pode ter expirado.</p>
          <Link to="/" className="text-primary mt-4 inline-block">Ir para o ConstruPilot →</Link>
        </div>
      </div>
    );
  }

  if (!data) {
    return <div className="min-h-screen grid place-items-center bg-background"><Loader2 className="h-8 w-8 animate-spin text-primary" /></div>;
  }

  return (
    <div className="min-h-screen bg-background text-foreground" data-testid="shared-calc-page">
      <header className="border-b border-border">
        <div className="max-w-3xl mx-auto px-6 py-4 flex items-center gap-3">
          <span className="h-9 w-9 rounded-md grid place-items-center text-white font-display font-extrabold"
                style={{ background: "linear-gradient(135deg,#22c55e,#a3e635)" }}>C</span>
          <span className="font-display font-extrabold text-lg">Constru<span className="text-primary">Pilot</span></span>
        </div>
      </header>

      <main className="max-w-3xl mx-auto px-6 py-10 grid gap-8">
        <div>
          <p className="text-xs uppercase tracking-widest text-primary font-semibold">Ficha de cálculo</p>
          <h1 className="font-display text-3xl font-bold mt-2">{data.name}</h1>
          {data.contractor ? (
            <p className="text-sm text-muted-foreground mt-2 inline-flex items-center gap-2">
              <HardHat className="h-4 w-4 text-primary" /> Preparada por {data.contractor}
            </p>
          ) : null}
          <div className="mt-5">
            <button onClick={downloadPdf} disabled={busyPdf} data-testid="shared-pdf-btn"
              className="inline-flex items-center gap-2 rounded-sm border border-primary/40 text-primary px-4 py-2.5 text-sm font-medium hover:bg-primary hover:text-primary-foreground transition-colors">
              {busyPdf ? <Loader2 className="h-4 w-4 animate-spin" /> : <FileDown className="h-4 w-4" />} Descarregar em PDF
            </button>
          </div>
        </div>

        {data.inputs?.length > 0 && (
          <section>
            <p className="overline mb-3">Parâmetros</p>
            <div className="grid sm:grid-cols-2 gap-2">
              {data.inputs.map((i, k) => (
                <div key={k} className="flex justify-between border border-border rounded-sm px-4 py-2.5 text-sm">
                  <span className="text-muted-foreground">{i.label}</span>
                  <span className="font-medium">{i.value}</span>
                </div>
              ))}
            </div>
          </section>
        )}

        {data.results?.length > 0 && (
          <section>
            <p className="overline mb-3">Resultados</p>
            <div className="grid sm:grid-cols-2 gap-3" data-testid="shared-results">
              {data.results.map((r, k) => (
                <div key={k} className="p-4 border border-border rounded-sm">
                  <p className="text-xs text-muted-foreground">{r.label}</p>
                  <p className="num mt-1 text-lg font-bold">{num(r.value, 2)} <span className="text-sm font-normal text-muted-foreground">{r.unit}</span></p>
                </div>
              ))}
            </div>
          </section>
        )}

        {data.priced_lines?.length > 0 ? (
          <section>
            <p className="overline mb-3">Orçamento de materiais — preços fornecedores</p>
            <div className="border border-border rounded-sm overflow-x-auto">
              <table className="w-full text-sm">
                <thead className="bg-secondary/60">
                  <tr>
                    <th className="text-left px-4 py-2.5">Produto</th>
                    <th className="text-right px-4 py-2.5">Qtd.</th>
                    <th className="text-left px-4 py-2.5">Fornecedor</th>
                    <th className="text-right px-4 py-2.5">Total</th>
                  </tr>
                </thead>
                <tbody>
                  {data.priced_lines.map((l, k) => (
                    <tr key={k} className="even:bg-muted/30 border-t border-border">
                      <td className="px-4 py-2.5">{l.name}</td>
                      <td className="px-4 py-2.5 num text-right">{l.quantity}</td>
                      <td className="px-4 py-2.5">{l.supplier}</td>
                      <td className="px-4 py-2.5 num text-right font-semibold text-primary">{eur2(l.total)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <p className="num mt-4 text-right">Total: <span className="text-primary font-bold text-lg">{eur(data.priced_total)}</span></p>
          </section>
        ) : (
          <section>
            <p className="overline mb-3">Lista de compras — materiais</p>
            <div className="border border-border rounded-sm overflow-x-auto">
              <table className="w-full text-sm">
                <thead className="bg-secondary/60">
                  <tr>
                    <th className="text-left px-4 py-2.5">Material</th>
                    <th className="text-right px-4 py-2.5">Quantidade</th>
                    <th className="text-left px-4 py-2.5">Unidade</th>
                  </tr>
                </thead>
                <tbody>
                  {(data.materials || []).map((m, k) => (
                    <tr key={k} className="even:bg-muted/30 border-t border-border">
                      <td className="px-4 py-2.5 font-medium">{m.name}</td>
                      <td className="px-4 py-2.5 num text-right">{num(m.quantity, 2)}</td>
                      <td className="px-4 py-2.5 text-muted-foreground">{m.unit}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <p className="num mt-4 text-right">Orçamento de materiais estimado: <span className="text-primary font-bold text-lg">{eur(data.estimated_budget)}</span></p>
          </section>
        )}

        <p className="text-xs text-muted-foreground border-t border-border pt-6">
          Estimativa indicativa, com margens de segurança incluídas. As quantidades podem variar consoante a execução.
        </p>

        <Link to="/calculadoras" className="surface p-5 rounded-md flex items-center justify-between group hover:border-primary/50 transition-colors" data-testid="shared-cta">
          <div>
            <p className="font-display font-semibold">Estime o seu projeto gratuitamente</p>
            <p className="text-sm text-muted-foreground">Calculadoras de materiais, orçamentos e preços — com o ConstruPilot.</p>
          </div>
          <ArrowRight className="h-5 w-5 text-primary group-hover:translate-x-1 transition-transform" />
        </Link>
      </main>
    </div>
  );
}
