import { useMemo, useState } from "react";
import { toast } from "sonner";
import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Calculator, Download, TrendingDown, Users, Mail, ArrowRight, ShieldCheck, CheckCircle2,
} from "lucide-react";

const BACKEND = process.env.REACT_APP_BACKEND_URL;
const eur = (n) => new Intl.NumberFormat("fr-FR", { style: "currency", currency: "EUR", maximumFractionDigits: 0 }).format(Math.round(Number(n) || 0));
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
    if (!lead.email) return toast.error("Indiquez votre e-mail");
    setLead((l) => ({ ...l, loading: true }));
    try {
      await api.post("/roi/lead", {
        email: lead.email, company: lead.company, phone: lead.phone, website: lead.website,
        ca_annual: Number(ca) || 0, estimated_monthly: Math.round(r.total),
      });
      setLead((l) => ({ ...l, sent: true, loading: false }));
      toast.success("Merci ! Un conseiller vous recontacte très vite.");
    } catch (e) {
      setLead((l) => ({ ...l, loading: false }));
      toast.error(e?.response?.data?.detail || "Envoi impossible");
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
          <Calculator className="h-4 w-4" /> Calculateur d'économies
        </p>
        <h1 className="font-display text-4xl sm:text-5xl font-extrabold mt-2 leading-tight">
          Combien ConstruPilot fait <span className="text-primary">économiser</span> à votre entreprise ?
        </h1>
        <p className="mt-3 text-base text-muted-foreground">
          On additionne deux leviers : <strong>(A)</strong> les pertes évitées (matériaux, marge, litiges) en % du CA,
          et <strong>(B)</strong> le personnel et le temps que l'IA automatise (métré, devis, calculs, chiffrage, admin) —
          en coût employeur réel, charges patronales (URSSAF) comprises.
        </p>
      </header>

      <div className="mt-8 grid lg:grid-cols-5 gap-6">
        {/* Entrées */}
        <div className="lg:col-span-2 rounded-2xl border border-border bg-card p-6 h-fit">
          <h2 className="font-display text-lg font-bold mb-4">Vos chiffres</h2>
          <div className="space-y-4">
            <NumField id="input-ca" label="Chiffre d'affaires annuel" val={ca} set={setCa} suffix="€/an" step={10000} />
            <div className="h-px bg-border my-1" />
            <p className="text-xs font-semibold text-foreground">Coût d'un profil études / devis / métré</p>
            <NumField id="input-brut" label="Salaire brut mensuel" val={brut} set={setBrut} suffix="€" step={100} />
            <NumField id="input-charges" label="Charges patronales (URSSAF…)" val={charges} set={setCharges} suffix="%" />
            <NumField id="input-frais" label="Frais générés (poste, logiciels, mutuelle…)" val={frais} set={setFrais} suffix="€" step={50} />
            <div className="rounded-lg bg-secondary/50 p-3 text-sm">
              <div className="flex items-center justify-between"><span className="text-muted-foreground">Salaire brut</span><span className="num">{eur(brut)}</span></div>
              <div className="flex items-center justify-between"><span className="text-muted-foreground">+ Charges {charges || 0}%</span><span className="num">+ {eur(r.charges_eur)}</span></div>
              <div className="flex items-center justify-between"><span className="text-muted-foreground">+ Frais générés</span><span className="num">+ {eur(frais)}</span></div>
              <div className="flex items-center justify-between font-bold text-primary mt-1 pt-1 border-t border-border">
                <span>= Coût employeur / mois</span><span className="num">{eur(r.loaded)}</span>
              </div>
            </div>
            <p className="text-[11px] text-muted-foreground flex items-center gap-1"><ShieldCheck className="h-3.5 w-3.5 text-emerald-600" /> Part automatisée : {r.fte.toFixed(2).replace(".", ",")} ETP (selon la taille)</p>
          </div>
        </div>

        {/* Résultats */}
        <div className="lg:col-span-3">
          <div className="grid sm:grid-cols-3 gap-3">
            <Stat icon={TrendingDown} label="A · Pertes évitées (2% du CA)" value={eur(r.A)} sub={`${eur(r.Alow)} – ${eur(r.Ahigh)}/mois`} />
            <Stat icon={Users} label="B · Personnel automatisé" value={eur(r.B)} sub={`${r.fte.toFixed(2).replace(".", ",")} ETP × ${eur(r.loaded)}`} />
            <Stat icon={Calculator} label="TOTAL estimé / mois" value={eur(r.total)} sub={`${eur(r.totalLow)} – ${eur(r.totalHigh)}`} accent />
          </div>

          <div className="mt-4 rounded-2xl border border-primary/30 bg-gradient-to-br from-primary/10 to-transparent p-6">
            <p className="text-sm text-muted-foreground">Économie estimée sur un an</p>
            <p className="font-display text-4xl sm:text-5xl font-extrabold text-primary mt-1" data-testid="result-total">{eur(r.total * 12)}</p>
            <p className="text-sm text-muted-foreground mt-1">soit environ <strong>{eur(r.total)}/mois</strong> (scénario typique)</p>
            <div className="mt-4 flex flex-wrap gap-3">
              <a href={pdfUrl} target="_blank" rel="noreferrer" data-testid="download-pdf-btn">
                <Button size="lg" className="rounded-full gap-2 font-bold"><Download className="h-5 w-5" /> Télécharger le PDF</Button>
              </a>
            </div>
          </div>

          {/* Capture lead */}
          <div className="mt-4 rounded-2xl border border-border bg-card p-6" data-testid="lead-card">
            {lead.sent ? (
              <div className="flex items-center gap-3 text-emerald-600">
                <CheckCircle2 className="h-6 w-6" />
                <p className="font-semibold">Merci ! Votre analyse personnalisée arrive — un conseiller vous recontacte sous peu.</p>
              </div>
            ) : (
              <>
                <h3 className="font-display text-lg font-bold flex items-center gap-2"><Mail className="h-4 w-4 text-primary" /> Recevoir mon analyse & être recontacté</h3>
                <p className="text-sm text-muted-foreground mt-1">Laissez vos coordonnées : on vous envoie le détail et on répond à vos questions.</p>
                <div className="mt-3 grid sm:grid-cols-3 gap-3">
                  <Input type="email" placeholder="E-mail professionnel*" value={lead.email} onChange={(e) => setLead((l) => ({ ...l, email: e.target.value }))} data-testid="lead-email" />
                  <Input placeholder="Entreprise" value={lead.company} onChange={(e) => setLead((l) => ({ ...l, company: e.target.value }))} data-testid="lead-company" />
                  <Input placeholder="Téléphone" value={lead.phone} onChange={(e) => setLead((l) => ({ ...l, phone: e.target.value }))} data-testid="lead-phone" />
                </div>
                <input type="text" tabIndex={-1} autoComplete="off" value={lead.website} onChange={(e) => setLead((l) => ({ ...l, website: e.target.value }))} className="hidden" aria-hidden />
                <Button onClick={sendLead} disabled={lead.loading} className="mt-3 rounded-full gap-2" data-testid="lead-send-btn">
                  {lead.loading ? "Envoi…" : <>Envoyer <ArrowRight className="h-4 w-4" /></>}
                </Button>
              </>
            )}
          </div>

          <p className="mt-4 text-xs text-muted-foreground">
            ⚠ Modèle d'estimation avec hypothèses explicites (ajustables ci-dessus), pas une garantie. Le résultat dépend
            du volume de devis, de la part des matériaux dans le CA et de l'adhésion des équipes. ConstruPilot — des
            chiffres issus de moteurs déterministes, jamais inventés.
          </p>
        </div>
      </div>
    </div>
  );
}
