import { useMemo, useState } from "react";
import { toast } from "sonner";
import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Calculator, Download, TrendingDown, Users, Mail, ArrowRight, ShieldCheck, CheckCircle2,
} from "lucide-react";

const BACKEND = process.env.REACT_APP_BACKEND_URL;
const eur = (n) => new Intl.NumberFormat("pt-PT", { style: "currency", currency: "EUR", maximumFractionDigits: 0 }).format(Math.round(Number(n) || 0));
const fteFor = (ca) => (ca < 300000 ? 0.4 : ca < 750000 ? 0.75 : ca < 1500000 ? 1.25 : ca < 3000000 ? 2.0 : 2.5);

export default function SavingsCalculator() {
  const [ca, setCa] = useState(500000);
  const [brut, setBrut] = useState(2900);
  const [charges, setCharges] = useState(42);
  const [frais, setFrais] = useState(450);
  const [lead, setLead] = useState({ email: "", company: "", phone: "", website: "", sent: false, loading: false });

  const r = useMemo(() => {
    const nCa = Number(ca) || 0, nBrut = Number(brut) || 0, nCh = Number(charges) || 0, nFr = Number(frais) || 0;
    const month = nCa / 12;
    const charges_eur = nBrut * nCh / 100;
    const loaded = nBrut + charges_eur + nFr;
    const fte = fteFor(nCa);
    const A = month * 0.02, Alow = month * 0.013, Ahigh = month * 0.035;
    const B = fte * loaded;
    return { month, charges_eur, loaded, fte, A, Alow, Ahigh, B, total: A + B, totalLow: Alow + B, totalHigh: Ahigh + B };
  }, [ca, brut, charges, frais]);

  const pdfUrl = `${BACKEND}/api/roi/pdf?ca=${Number(ca) || 0}&salaire_brut=${Number(brut) || 0}&charges_pct=${Number(charges) || 0}&frais_generes=${Number(frais) || 0}`;

  const sendLead = async () => {
    if (!lead.email) return toast.error("Indique o seu e-mail");
    setLead((l) => ({ ...l, loading: true }));
    try {
      await api.post("/roi/lead", {
        email: lead.email, company: lead.company, phone: lead.phone, website: lead.website,
        ca_annual: Number(ca) || 0, estimated_monthly: Math.round(r.total),
      });
      setLead((l) => ({ ...l, sent: true, loading: false }));
      toast.success("Obrigado! Um consultor volta a contactá-lo muito em breve.");
    } catch (e) {
      setLead((l) => ({ ...l, loading: false }));
      toast.error(e?.response?.data?.detail || "Envio impossível");
    }
  };

  const NumField = ({ id, label, val, set, suffix, step }) => (
    <div>
      <label className="text-xs font-semibold text-muted-foreground">{label}</label>
      <div className="relative mt-1">
        <Input type="number" inputMode="numeric" step={step || 1} value={val}
          onChange={(e) => set(e.target.value)} data-testid={id} className="pr-12" />
        {suffix && <span className="absolute right-3 top-1/2 -translate-y-1/2 text-xs text-muted-foreground">{suffix}</span>}
      </div>
    </div>
  );

  const Stat = ({ icon: Icon, label, value, sub, accent }) => (
    <div className={`rounded-xl border p-4 ${accent ? "border-primary/40 bg-primary/5" : "border-border bg-card"}`}>
      <p className="text-xs text-muted-foreground flex items-center gap-1.5"><Icon className="h-3.5 w-3.5" /> {label}</p>
      <p className={`font-display font-extrabold mt-1 ${accent ? "text-3xl text-primary" : "text-2xl"}`}>{value}</p>
      {sub && <p className="text-[11px] text-muted-foreground mt-0.5">{sub}</p>}
    </div>
  );

  return (
    <div className="mx-auto max-w-6xl px-5 py-10" data-testid="savings-calculator">
      <header className="max-w-3xl">
        <p className="text-xs uppercase tracking-widest text-primary font-semibold flex items-center gap-2">
          <Calculator className="h-4 w-4" /> Calculadora de poupanças
        </p>
        <h1 className="font-display text-4xl sm:text-5xl font-extrabold mt-2 leading-tight">
          Quanto faz o ConstruPilot <span className="text-primary">poupar</span> à sua empresa?
        </h1>
        <p className="mt-3 text-base text-muted-foreground">
          Somamos duas alavancas: <strong>(A)</strong> as perdas evitadas (materiais, margem, litígios) em % do volume de negócios, e <strong>(B)</strong> o pessoal e o tempo que a IA automatiza (medição, orçamentos, cálculos, orçamentação, administração) — em custo real para o empregador, encargos sociais (Segurança Social) incluídos.
        </p>
      </header>

      <div className="mt-8 grid lg:grid-cols-5 gap-6">
        {/* Entrées */}
        <div className="lg:col-span-2 rounded-2xl border border-border bg-card p-6 h-fit">
          <h2 className="font-display text-lg font-bold mb-4">Os seus números</h2>
          <div className="space-y-4">
            <NumField id="input-ca" label="Volume de negócios anual" val={ca} set={setCa} suffix="€/an" step={10000} />
            <div className="h-px bg-border my-1" />
            <p className="text-xs font-semibold text-foreground">Custo de um perfil de estudos / orçamentos / medições</p>
            <NumField id="input-brut" label="Salário bruto mensal" val={brut} set={setBrut} suffix="€" step={100} />
            <NumField id="input-charges" label="Encargos patronais (Segurança Social…)" val={charges} set={setCharges} suffix="%" />
            <NumField id="input-frais" label="Custos gerados (posto, software, seguros…)" val={frais} set={setFrais} suffix="€" step={50} />
            <div className="rounded-lg bg-secondary/50 p-3 text-sm">
              <div className="flex items-center justify-between"><span className="text-muted-foreground">Salário bruto</span><span className="num">{eur(brut)}</span></div>
              <div className="flex items-center justify-between"><span className="text-muted-foreground">+ Encargos {charges || 0}%</span><span className="num">+ {eur(r.charges_eur)}</span></div>
              <div className="flex items-center justify-between"><span className="text-muted-foreground">+ Custos gerados</span><span className="num">+ {eur(frais)}</span></div>
              <div className="flex items-center justify-between font-bold text-primary mt-1 pt-1 border-t border-border">
                <span>= Custo para o empregador / mês</span><span className="num">{eur(r.loaded)}</span>
              </div>
            </div>
            <p className="text-[11px] text-muted-foreground flex items-center gap-1"><ShieldCheck className="h-3.5 w-3.5 text-emerald-600" /> Parte automatizada: {r.fte.toFixed(2).replace(".", ",")} ETI (segundo a dimensão)</p>
          </div>
        </div>

        {/* Résultats */}
        <div className="lg:col-span-3">
          <div className="grid sm:grid-cols-3 gap-3">
            <Stat icon={TrendingDown} label="A · Perdas evitadas (2% do volume de negócios)" value={eur(r.A)} sub={`${eur(r.Alow)} – ${eur(r.Ahigh)}/mois`} />
            <Stat icon={Users} label="B · Pessoal automatizado" value={eur(r.B)} sub={`${r.fte.toFixed(2).replace(".", ",")} ETI × ${eur(r.loaded)}`} />
            <Stat icon={Calculator} label="TOTAL estimado / mês" value={eur(r.total)} sub={`${eur(r.totalLow)} – ${eur(r.totalHigh)}`} accent />
          </div>

          <div className="mt-4 rounded-2xl border border-primary/30 bg-gradient-to-br from-primary/10 to-transparent p-6">
            <p className="text-sm text-muted-foreground">Poupança estimada num ano</p>
            <p className="font-display text-4xl sm:text-5xl font-extrabold text-primary mt-1" data-testid="result-total">{eur(r.total * 12)}</p>
            <p className="text-sm text-muted-foreground mt-1">ou seja, cerca de <strong>{eur(r.total)}/mois</strong> (cenário típico)</p>
            <div className="mt-4 flex flex-wrap gap-3">
              <a href={pdfUrl} target="_blank" rel="noreferrer" data-testid="download-pdf-btn">
                <Button size="lg" className="rounded-full gap-2 font-bold"><Download className="h-5 w-5" /> Descarregar o PDF</Button>
              </a>
            </div>
          </div>

          {/* Capture lead */}
          <div className="mt-4 rounded-2xl border border-border bg-card p-6" data-testid="lead-card">
            {lead.sent ? (
              <div className="flex items-center gap-3 text-emerald-600">
                <CheckCircle2 className="h-6 w-6" />
                <p className="font-semibold">Obrigado! A sua análise personalizada está a caminho — um consultor volta a contactá-lo em breve.</p>
              </div>
            ) : (
              <>
                <h3 className="font-display text-lg font-bold flex items-center gap-2"><Mail className="h-4 w-4 text-primary" /> Receber a minha análise e ser contactado</h3>
                <p className="text-sm text-muted-foreground mt-1">Deixe os seus contactos: enviamos-lhe o detalhe e respondemos às suas perguntas.</p>
                <div className="mt-3 grid sm:grid-cols-3 gap-3">
                  <Input type="email" placeholder="E-mail profissional*" value={lead.email} onChange={(e) => setLead((l) => ({ ...l, email: e.target.value }))} data-testid="lead-email" />
                  <Input placeholder="Empresa" value={lead.company} onChange={(e) => setLead((l) => ({ ...l, company: e.target.value }))} data-testid="lead-company" />
                  <Input placeholder="Telefone" value={lead.phone} onChange={(e) => setLead((l) => ({ ...l, phone: e.target.value }))} data-testid="lead-phone" />
                </div>
                <input type="text" tabIndex={-1} autoComplete="off" value={lead.website} onChange={(e) => setLead((l) => ({ ...l, website: e.target.value }))} className="hidden" aria-hidden />
                <Button onClick={sendLead} disabled={lead.loading} className="mt-3 rounded-full gap-2" data-testid="lead-send-btn">
                  {lead.loading ? "A enviar…" : <>Enviar <ArrowRight className="h-4 w-4" /></>}
                </Button>
              </>
            )}
          </div>

          <p className="mt-4 text-xs text-muted-foreground">
            ⚠ Modelo de estimativa com hipóteses explícitas (ajustáveis acima), não uma garantia. O resultado depende do volume de orçamentos, do peso dos materiais no volume de negócios e da adesão das equipas. ConstruPilot — números provenientes de motores determinísticos, nunca inventados.
          </p>
        </div>
      </div>
    </div>
  );
}
