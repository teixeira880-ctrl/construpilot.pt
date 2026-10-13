import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { FileDown, Hammer } from "lucide-react";
import { api, eur } from "@/lib/api";

const List = ({ title, items, testid }) => items?.length > 0 && (
  <section className="grid gap-1.5" data-testid={testid}>
    <h2 className="text-base md:text-lg font-semibold">{title}</h2>
    <ul className="list-disc ml-5 text-sm grid gap-0.5">{items.map((x, i) => <li key={i}>{x}</li>)}</ul>
  </section>
);

export default function SharedEstimate() {
  const { token } = useParams();
  const [data, setData] = useState(null);
  const [err, setErr] = useState(null);
  useEffect(() => { api.get(`/public/estimations/${token}`).then((r) => setData(r.data)).catch(() => setErr("Estimativa não encontrada ou ligação expirada.")); }, [token]);
  const e = data?.estimate;
  return (
    <div className="min-h-screen bg-background" data-testid="shared-estimate-page">
      <header className="border-b bg-card"><div className="max-w-4xl mx-auto px-4 py-4 flex items-center gap-3"><Link to="/" className="font-bold text-lg"><span className="text-[#FF5A00]">Constru</span>Pilot</Link><span className="text-xs text-muted-foreground">Estimativa orçamental indicativa</span></div></header>
      <main className="max-w-4xl mx-auto px-4 py-10 grid gap-8">
        {err && <p className="text-sm text-red-600" data-testid="shared-estimate-error">{err}</p>}
        {e && (<>
          <div className="grid gap-2">
            <div className="text-xs uppercase tracking-widest text-[#FF5A00] font-semibold">Intervalo de orçamento de obras</div>
            <h1 className="text-3xl sm:text-4xl font-bold tracking-tight" data-testid="shared-estimate-title">{e.project}</h1>
            <p className="text-sm text-muted-foreground">Referência {data.ref} · {e.reference_region} · preço {e.price_date} · niveau : {e.finish_level}</p>
          </div>
          <div className="grid grid-cols-3 gap-3">
            <div className="rounded-sm border border-emerald-500/40 bg-emerald-500/10 p-4 text-center"><div className="text-[11px] uppercase tracking-wide text-muted-foreground">Preço baixo</div><div className="text-2xl sm:text-3xl font-bold" data-testid="shared-estimate-low">{eur(e.low_estimate)}</div></div>
            <div className="rounded-sm border border-amber-500/40 bg-amber-500/10 p-4 text-center"><div className="text-[11px] uppercase tracking-wide text-muted-foreground">Central</div><div className="text-2xl sm:text-3xl font-bold">{eur(e.central_estimate)}</div></div>
            <div className="rounded-sm border border-orange-500/40 bg-orange-500/10 p-4 text-center"><div className="text-[11px] uppercase tracking-wide text-muted-foreground">Preço alto</div><div className="text-2xl sm:text-3xl font-bold" data-testid="shared-estimate-high">{eur(e.high_estimate)}</div></div>
          </div>
          <p className="text-sm text-muted-foreground">Amplitude {e.range_percentage} % · confiance {Math.round((e.confidence || 0) * 100)} % · source : {e.price_source}</p>
          <div className="grid sm:grid-cols-2 gap-6">
            <List title="Incluído na estimativa" items={e.included_items} testid="shared-estimate-included" />
            <List title="Não incluído" items={e.excluded_items} testid="shared-estimate-excluded" />
            <List title="Hipóteses adotadas" items={e.assumptions} />
            <List title="Facteurs d'incertitude" items={e.uncertainty_factors} />
            <List title="Informations manquantes" items={e.missing_information} />
            <List title="Perguntas a colocar às empresas" items={e.recommended_questions_for_contractors} testid="shared-estimate-questions" />
          </div>
          <p className="text-sm italic border-l-4 border-[#FF5A00] pl-3 py-1 bg-muted/40" data-testid="shared-estimate-notice">{e.mandatory_notice}</p>
          <div className="flex flex-wrap gap-3">
            <a className="inline-flex items-center gap-2 px-4 py-2 rounded-sm bg-primary text-primary-foreground text-sm hover:opacity-90 transition-opacity" href={`${process.env.REACT_APP_BACKEND_URL}/api/public/estimations/${token}/pdf`} target="_blank" rel="noreferrer" data-testid="shared-estimate-pdf"><FileDown className="h-4 w-4" /> Descarregar o PDF</a>
            <Link className="inline-flex items-center gap-2 px-4 py-2 rounded-sm border text-sm hover:bg-muted transition-colors" to="/estimation" data-testid="shared-estimate-cta"><Hammer className="h-4 w-4" /> Fazer a minha própria estimativa gratuita</Link>
          </div>
        </>)}
      </main>
    </div>
  );
}
