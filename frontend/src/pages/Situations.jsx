import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { motion } from "framer-motion";
import {
  Layers, Lock, ArrowRight, Plus, Trash2, FileText, Percent, TrendingUp,
  Wallet, ShieldCheck, Bell, CalendarClock, CheckCircle2, FileCheck, Download,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Switch } from "@/components/ui/switch";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { SectionTitle } from "@/components/Bits";
import { api, eur } from "@/lib/api";
import { useBilling } from "@/context/BillingContext";
import { usePermissions } from "@/context/PermissionContext";
import { useAuth } from "@/context/AuthContext";
import { NoAccess } from "@/pages/Invoices";
import { toast } from "sonner";

export default function Situations() {
  const nav = useNavigate();
  const { tier } = useBilling();
  const { user } = useAuth();
  const { can, in_org } = usePermissions();
  const isProBusiness = tier === "pro_business" || user?.role === "admin" || !!user?.invoicing_addon;

  const [marches, setMarches] = useState([]);
  const [marcheId, setMarcheId] = useState("");
  const [baseLines, setBaseLines] = useState([]);
  const [situations, setSituations] = useState([]);
  const [pcts, setPcts] = useState({});
  const [prevPct, setPrevPct] = useState({});
  const [retention, setRetention] = useState(0);
  const [depMode, setDepMode] = useState("prorata");
  const [depManual, setDepManual] = useState(0);
  const [busy, setBusy] = useState(false);
  const [summary, setSummary] = useState(null);
  const [prorata, setProrata] = useState(null);
  const [retentions, setRetentions] = useState([]);
  const [dgd, setDgd] = useState(null);
  const [dgdDeposit, setDgdDeposit] = useState(true);
  const [dgdRelease, setDgdRelease] = useState(false);

  useEffect(() => {
    if (!isProBusiness) return;
    api.get("/situations/marches").then(({ data }) => setMarches(data)).catch(() => {});
    loadRetentions();
  }, [isProBusiness]);

  const loadRetentions = () => api.get("/situations/retentions").then(({ data }) => setRetentions(data)).catch(() => {});

  const createDgd = async () => {
    setBusy(true);
    try {
      const { data } = await api.post("/situations/dgd", {
        marche_id: marcheId, impute_deposit: dgdDeposit, release_retention: dgdRelease,
      });
      toast.success(`Décompte général définitif créé — facture ${data.number}`);
      await loadMarche(marcheId);
      loadRetentions();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Génération impossible");
    } finally { setBusy(false); }
  };

  const cancelDgd = async () => {
    try {
      await api.delete(`/situations/dgd/${marcheId}`);
      toast.success("Décompte général annulé");
      await loadMarche(marcheId);
    } catch (e) { toast.error(e?.response?.data?.detail || "Annulation impossible"); }
  };

  const dgdPdf = async () => {
    try {
      const { data } = await api.get(`/situations/dgd-pdf?marche_id=${marcheId}`, { responseType: "blob" });
      const url = URL.createObjectURL(data);
      const a = document.createElement("a");
      a.href = url; a.download = "decompte-general-definitif.pdf"; a.click();
      URL.revokeObjectURL(url);
    } catch { toast.error("PDF indisponible"); }
  };

  const loadMarche = async (id) => {
    setMarcheId(id);
    setPcts({});
    if (!id) { setBaseLines([]); setSituations([]); setPrevPct({}); setSummary(null); setProrata(null); setDgd(null); return; }
    const [{ data: doc }, { data: sits }, { data: sum }, { data: pro }, { data: dg }] = await Promise.all([
      api.get(`/documents/${id}`),
      api.get(`/situations?marche_id=${id}`),
      api.get(`/situations/summary?marche_id=${id}`),
      api.get(`/situations/${id}/prorata`),
      api.get(`/situations/dgd?marche_id=${id}`),
    ]);
    setBaseLines(doc.lines || []);
    setSituations(sits);
    setSummary(sum);
    setProrata(pro);
    setDgd(dg);
    const last = sits.length ? sits[sits.length - 1] : null;
    const pp = {};
    if (last?.cumul_pct) Object.entries(last.cumul_pct).forEach(([k, v]) => { pp[k] = Number(v); });
    setPrevPct(pp);
    const init = {};
    (doc.lines || []).forEach((_, i) => { init[i] = pp[i] || 0; });
    setPcts(init);
  };

  const refreshMarche = () => loadMarche(marcheId);
  const lineContract = (l) => Math.round((l.qty || 0) * (l.unit_price_ht || 0) * 100) / 100;
  const lineSituation = (l, i) => {
    const cum = Math.max(Number(pcts[i] || 0), prevPct[i] || 0);
    const delta = cum - (prevPct[i] || 0);
    return Math.round(lineContract(l) * delta / 100 * 100) / 100;
  };
  const totalHT = baseLines.reduce((s, l, i) => s + lineSituation(l, i), 0);
  const dep = summary?.deposit || null;
  const depAvailable = dep ? Number(dep.available_ht || 0) : 0;
  const depPaidHt = dep ? Number(dep.paid_ht || 0) : 0;
  const depImputed = dep ? Number(dep.imputed_ht || 0) : 0;
  const contractHt = Number(summary?.totals?.contract_ht || 0);
  const billedBefore = Number(summary?.totals?.billed_ht || 0);
  const cumulRatio = contractHt ? Math.min((billedBefore + totalHT) / contractHt, 1) : 0;
  const depDeduct = (() => {
    if (!depAvailable || totalHT <= 0 || depMode === "none") return 0;
    let want;
    if (depMode === "full") want = depAvailable;
    else if (depMode === "manual") want = Number(depManual) || 0;
    else want = Math.round((depPaidHt * cumulRatio - depImputed) * 100) / 100;
    return Math.round(Math.max(0, Math.min(want, depAvailable, totalHT)) * 100) / 100;
  })();
  const invoiceHt = Math.round((totalHT - depDeduct) * 100) / 100;
  const retentionAmt = Math.round(totalHT * (retention || 0) / 100 * 100) / 100;

  const submit = async () => {
    const lines = baseLines.map((_, i) => ({ idx: i, pct: Math.max(Number(pcts[i] || 0), prevPct[i] || 0) }));
    setBusy(true);
    try {
      const { data } = await api.post("/situations", {
        marche_id: marcheId, lines, retention_pct: Number(retention) || 0,
        deposit_mode: depMode, deposit_amount_ht: Number(depManual) || 0,
      });
      toast.success(`Situation n°${data.seq} créée — facture ${data.invoice_number}`
        + (data.deposit_imputed_ht ? ` · acompte déduit ${data.deposit_imputed_ht} € HT` : ""));
      await refreshMarche(); loadRetentions();
    } catch (e) { toast.error(e?.response?.data?.detail || "Création impossible"); }
    finally { setBusy(false); }
  };
  const del = async (id) => {
    try { await api.delete(`/situations/${id}`); toast.success("Situation supprimée"); refreshMarche(); loadRetentions(); }
    catch { toast.error("Suppression impossible"); }
  };
  const downloadSituationPdf = async (s) => {
    try {
      const { data } = await api.get(`/situations/${s.situation_id}/pdf`, { responseType: "blob" });
      const url = URL.createObjectURL(new Blob([data], { type: "application/pdf" }));
      const a = document.createElement("a");
      a.href = url; a.download = `decompte-situation-${s.seq}.pdf`; a.click();
      URL.revokeObjectURL(url);
    } catch { toast.error("Génération du décompte impossible"); }
  };
  const downloadCertificate = async (s) => {
    try {
      const { data } = await api.get(`/situations/${s.situation_id}/certificate`, { responseType: "blob" });
      const url = URL.createObjectURL(new Blob([data], { type: "application/pdf" }));
      const a = document.createElement("a");
      a.href = url; a.download = `certificat-paiement-${s.seq}.pdf`; a.click();
      URL.revokeObjectURL(url);
    } catch { toast.error("Génération du certificat impossible"); }
  };

  // ---- Prorata ----
  const saveProrata = async (cfg) => {
    try {
      const { data } = await api.put(`/situations/${marcheId}/prorata`, cfg);
      setProrata(data); toast.success("Compte prorata enregistré");
    } catch { toast.error("Erreur"); }
  };
  const addExpense = () => setProrata({ ...prorata, expenses: [...(prorata.expenses || []), { label: "", amount: 0 }] });
  const updExpense = (i, k, v) => {
    const ex = [...prorata.expenses]; ex[i] = { ...ex[i], [k]: k === "amount" ? v : v }; setProrata({ ...prorata, expenses: ex });
  };
  const rmExpense = (i) => setProrata({ ...prorata, expenses: prorata.expenses.filter((_, x) => x !== i) });

  // ---- Retenues ----
  const setReception = async (mid, date) => {
    if (!date) return;
    try { await api.post(`/situations/${mid}/reception`, { reception_date: date }); toast.success("Date de réception enregistrée"); loadRetentions(); }
    catch { toast.error("Erreur"); }
  };
  const releaseRet = async (mid) => {
    try { await api.post(`/situations/retentions/${mid}/release`); toast.success("Retenue libérée"); loadRetentions(); }
    catch { toast.error("Erreur"); }
  };
  const remindRet = async (mid) => {
    try { const { data } = await api.post(`/situations/retentions/${mid}/remind`); toast[data.emails_sent ? "success" : "message"](data.emails_sent ? `Relance envoyée à ${data.to}` : "E-mail non envoyé (client sans e-mail ou service indispo)"); }
    catch (e) { toast.error(e?.response?.data?.detail || "Erreur"); }
  };

  if (in_org && !can("situations")) return <NoAccess title="Situations non autorisées" />;
  if (!isProBusiness) {
    return (
      <div className="max-w-2xl mx-auto px-6 py-24 text-center" data-testid="situations-locked">
        <div className="h-14 w-14 rounded-xl bg-primary/10 grid place-items-center mx-auto mb-5"><Lock className="h-7 w-7 text-primary" /></div>
        <h1 className="font-display text-3xl font-bold">Facturation à l'avancement</h1>
        <p className="text-muted-foreground mt-3">Situations de travaux, avancement cumulé, retenue de garantie et compte prorata — réservé au <b>pack Business</b>.</p>
        <Button className="rounded-sm mt-6 gap-2" onClick={() => nav("/tarifs")} data-testid="situations-upgrade-btn">Passer au pack Business <ArrowRight className="h-4 w-4" /></Button>
      </div>
    );
  }

  const RetStatus = ({ s }) => {
    const map = { released: ["Libérée", "text-muted-foreground border-border"], due: ["À libérer", "text-red-500 border-red-500/30"], pending: ["En cours", "text-amber-500 border-amber-500/30"], held: ["Détenue", "text-primary border-primary/30"] };
    const [l, c] = map[s] || map.held;
    return <Badge variant="outline" className={`rounded-sm ${c}`}>{l}</Badge>;
  };

  return (
    <div className="max-w-5xl mx-auto px-4 py-10 space-y-6" data-testid="situations-page">
      <SectionTitle over="Pack Business" title="Situations de travaux">
        Facturez vos marchés à l'avancement, pilotez le cumul, la retenue de garantie et le compte prorata.
      </SectionTitle>

      <div className="grid gap-1.5 max-w-md">
        <label className="text-xs text-muted-foreground">Marché de référence (devis ou facture)</label>
        <Select value={marcheId} onValueChange={loadMarche}>
          <SelectTrigger className="rounded-sm" data-testid="situation-marche-select"><SelectValue placeholder="Choisir un marché…" /></SelectTrigger>
          <SelectContent>
            {marches.map((m) => (
              <SelectItem key={m.doc_id} value={m.doc_id} data-testid={`marche-opt-${m.doc_id}`}>
                {(m.number || "Brouillon")} · {m.title || "Sans titre"} — {eur(m.total_ht)} HT
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      {summary && (
        <div className="grid grid-cols-2 md:grid-cols-5 gap-3" data-testid="marche-banner">
          <Kpi label="Montant marché HT" value={eur(summary.totals.contract_ht)} />
          <Kpi label="Acompte encaissé TTC" value={eur(summary.totals.deposit_paid_ttc)} />
          <Kpi label="Facturé à ce jour HT" value={eur(summary.totals.billed_ht)} accent />
          <Kpi label="Retenue détenue" value={eur(summary.totals.retention_held)} />
          <Kpi label="Reste à facturer HT" value={eur(summary.totals.remaining_ht)} />
        </div>
      )}
      {summary && dep && (dep.invoiced_ttc > 0) && (
        <p className="text-xs text-muted-foreground" data-testid="marche-deposit-note">
          Acompte facturé {eur(dep.invoiced_ttc)} TTC · encaissé {eur(dep.paid_ttc)} TTC
          {dep.unpaid_ttc > 0 ? ` · non encaissé ${eur(dep.unpaid_ttc)} (non déductible)` : ""}
          {" "}· déjà imputé {eur(dep.imputed_ht)} HT · disponible {eur(dep.available_ht)} HT
        </p>
      )}

      <Tabs defaultValue="situation" className="w-full">
        <TabsList className="rounded-sm flex-wrap h-auto" data-testid="situations-tabs">
          <TabsTrigger value="situation" data-testid="tab-situation">Nouvelle situation</TabsTrigger>
          <TabsTrigger value="avancement" data-testid="tab-avancement">Avancement</TabsTrigger>
          <TabsTrigger value="prorata" data-testid="tab-prorata">Compte prorata</TabsTrigger>
          <TabsTrigger value="retenue" data-testid="tab-retenue">Retenue de garantie</TabsTrigger>
          <TabsTrigger value="dgd" data-testid="tab-dgd">Décompte final</TabsTrigger>
        </TabsList>

        {/* ---------- Nouvelle situation ---------- */}
        <TabsContent value="situation" className="space-y-4 mt-4">
          {!marcheId ? <Empty text="Choisissez un marché pour créer une situation." /> : (
            <>
              <div className="surface rounded-md overflow-hidden" data-testid="situation-lines">
                <table className="w-full text-sm">
                  <thead><tr className="border-b border-border text-left text-xs text-muted-foreground">
                    <th className="p-3">Poste</th><th className="p-3 text-right">Marché HT</th>
                    <th className="p-3 text-center">% préc.</th><th className="p-3 text-center">% cumulé</th>
                    <th className="p-3 text-right">Cette situation HT</th></tr></thead>
                  <tbody>
                    {baseLines.map((l, i) => (
                      <tr key={i} className="border-b border-border/50" data-testid={`sit-line-${i}`}>
                        <td className="p-3">{l.designation || `Ligne ${i + 1}`}</td>
                        <td className="p-3 text-right num">{eur(lineContract(l))}</td>
                        <td className="p-3 text-center num text-muted-foreground">{(prevPct[i] || 0)}%</td>
                        <td className="p-3 text-center">
                          <Input type="number" min={prevPct[i] || 0} max={100} value={pcts[i] ?? 0}
                            onChange={(e) => setPcts({ ...pcts, [i]: e.target.value })}
                            className="rounded-sm h-9 w-20 num text-center mx-auto" data-testid={`sit-pct-${i}`} />
                        </td>
                        <td className="p-3 text-right num font-semibold text-primary">{eur(lineSituation(l, i))}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <div className="flex flex-wrap items-end justify-between gap-4 surface rounded-md p-4">
                <div className="grid gap-1.5">
                  <label className="text-xs text-muted-foreground flex items-center gap-1"><Percent className="h-3 w-3" /> Retenue de garantie</label>
                  <div className="flex items-center gap-2">
                    <Input type="number" min={0} max={10} step={0.5} value={retention} onChange={(e) => setRetention(e.target.value)} className="rounded-sm h-10 w-24 num" data-testid="situation-retention" />
                    <span className="text-sm text-muted-foreground">% · {eur(retentionAmt)}</span>
                    <Button variant="ghost" size="sm" className="rounded-sm text-xs" onClick={() => setRetention(5)} data-testid="retention-5">5%</Button>
                  </div>
                </div>
                <div className="grid gap-1.5">
                  <label className="text-xs text-muted-foreground flex items-center gap-1"><Wallet className="h-3 w-3" /> Acompte déjà versé</label>
                  <div className="flex items-center gap-2">
                    <Select value={depMode} onValueChange={setDepMode}>
                      <SelectTrigger className="rounded-sm h-10 w-52" data-testid="situation-deposit-mode"><SelectValue /></SelectTrigger>
                      <SelectContent>
                        <SelectItem value="prorata" data-testid="dep-mode-prorata">Au prorata de l'avancement</SelectItem>
                        <SelectItem value="full" data-testid="dep-mode-full">En totalité maintenant</SelectItem>
                        <SelectItem value="manual" data-testid="dep-mode-manual">Montant manuel</SelectItem>
                        <SelectItem value="none" data-testid="dep-mode-none">Ne pas déduire</SelectItem>
                      </SelectContent>
                    </Select>
                    {depMode === "manual" && (
                      <Input type="number" min={0} max={depAvailable} value={depManual}
                        onChange={(e) => setDepManual(e.target.value)}
                        className="rounded-sm h-10 w-28 num" data-testid="situation-deposit-manual" />
                    )}
                  </div>
                  <p className="text-[11px] text-muted-foreground" data-testid="situation-deposit-info">
                    {depAvailable > 0
                      ? <>Disponible : {eur(depAvailable)} HT · déduction : <b className="text-foreground">-{eur(depDeduct)}</b></>
                      : "Aucun acompte encaissé à déduire sur ce marché."}
                  </p>
                </div>
                <div className="text-right">
                  <p className="text-xs text-muted-foreground">Travaux {eur(totalHT)} HT</p>
                  <p className="num text-2xl font-extrabold text-primary" data-testid="situation-total-ht">{eur(invoiceHt)}</p>
                  <p className="text-[11px] text-muted-foreground">Facture HT après acompte</p>
                </div>
                <Button className="rounded-sm gap-2" disabled={busy || totalHT <= 0} onClick={submit} data-testid="situation-create-btn">
                  <Plus className="h-4 w-4" /> Créer la situation n°{situations.length + 1}
                </Button>
              </div>
              {situations.length > 0 && (
                <div className="space-y-2" data-testid="situations-history">
                  <p className="overline">Historique</p>
                  {situations.map((s) => (
                    <div key={s.situation_id} className="surface rounded-sm p-4 flex flex-wrap items-center gap-4" data-testid={`situation-row-${s.situation_id}`}>
                      <div className="h-9 w-9 rounded-lg bg-primary/10 grid place-items-center"><TrendingUp className="h-4 w-4 text-primary" /></div>
                      <div>
                        <p className="font-semibold">Situation n°{s.seq} · {s.invoice_number}</p>
                        <p className="text-xs text-muted-foreground">{eur(s.total_ttc)} TTC{s.deposit_imputed_ht ? ` · acompte déduit ${eur(s.deposit_imputed_ht)} HT` : ""}{s.retention_amount ? ` · retenue ${eur(s.retention_amount)} · net ${eur(s.net_due)}` : ""}</p>
                      </div>
                      <div className="ml-auto flex gap-2">
                        <Button size="sm" variant="outline" className="rounded-sm gap-1.5 text-primary border-primary/30" onClick={() => downloadSituationPdf(s)} data-testid={`situation-pdf-${s.situation_id}`}><FileText className="h-4 w-4" /> Décompte PDF</Button>
                        <Button size="sm" variant="outline" className="rounded-sm gap-1.5" onClick={() => downloadCertificate(s)} data-testid={`situation-cert-${s.situation_id}`}><ShieldCheck className="h-4 w-4" /> Certificat</Button>
                        <Button size="sm" variant="outline" className="rounded-sm gap-1.5" onClick={() => nav(`/devis-editeur/${s.invoice_doc_id}`)} data-testid={`situation-open-${s.situation_id}`}><FileText className="h-4 w-4" /> Facture</Button>
                        <Button size="sm" variant="ghost" className="rounded-sm text-red-500" onClick={() => del(s.situation_id)} data-testid={`situation-del-${s.situation_id}`}><Trash2 className="h-4 w-4" /></Button>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </>
          )}
        </TabsContent>

        {/* ---------- Avancement (cumulé) ---------- */}
        <TabsContent value="avancement" className="space-y-4 mt-4">
          {!summary ? <Empty text="Choisissez un marché pour voir son avancement." /> : (
            <>
              <div className="grid grid-cols-2 md:grid-cols-4 gap-3" data-testid="avancement-kpis">
                <Kpi label="Montant marché HT" value={eur(summary.totals.contract_ht)} />
                <Kpi label="Déjà facturé HT" value={eur(summary.totals.billed_ht)} accent />
                <Kpi label="Restant à facturer" value={eur(summary.totals.remaining_ht)} />
                <Kpi label="Retenue détenue" value={eur(summary.totals.retention_held)} />
              </div>
              <div className="surface rounded-md p-5">
                <div className="flex items-center justify-between text-sm mb-2">
                  <span className="text-muted-foreground">Avancement global</span>
                  <span className="num font-bold text-primary">{summary.totals.pct_global}%</span>
                </div>
                <div className="h-3 rounded-full bg-secondary overflow-hidden">
                  <div className="h-full bg-primary rounded-full transition-all" style={{ width: `${Math.min(summary.totals.pct_global, 100)}%` }} data-testid="avancement-bar" />
                </div>
                <p className="text-xs text-muted-foreground mt-2">{summary.totals.situations_count} situation(s) émise(s) · {eur(summary.totals.billed_ttc)} TTC facturés</p>
              </div>
              <div className="surface rounded-md overflow-hidden" data-testid="avancement-lines">
                <table className="w-full text-sm">
                  <thead><tr className="border-b border-border text-left text-xs text-muted-foreground">
                    <th className="p-3">Lot</th><th className="p-3 text-right">Marché HT</th>
                    <th className="p-3 text-center">Avancement</th><th className="p-3 text-right">Facturé HT</th>
                    <th className="p-3 text-right">Restant HT</th></tr></thead>
                  <tbody>
                    {summary.lines.map((l, i) => (
                      <tr key={i} className="border-b border-border/50">
                        <td className="p-3">{l.designation}</td>
                        <td className="p-3 text-right num">{eur(l.contract_ht)}</td>
                        <td className="p-3">
                          <div className="flex items-center gap-2">
                            <div className="h-2 flex-1 rounded-full bg-secondary overflow-hidden min-w-[60px]"><div className="h-full bg-primary" style={{ width: `${Math.min(l.cumul_pct, 100)}%` }} /></div>
                            <span className="num text-xs w-10 text-right">{l.cumul_pct}%</span>
                          </div>
                        </td>
                        <td className="p-3 text-right num text-primary">{eur(l.billed_ht)}</td>
                        <td className="p-3 text-right num text-muted-foreground">{eur(l.remaining_ht)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </>
          )}
        </TabsContent>

        {/* ---------- Compte prorata ---------- */}
        <TabsContent value="prorata" className="space-y-4 mt-4">
          {!prorata ? <Empty text="Choisissez un marché pour gérer son compte prorata." /> : (
            <>
              <div className="surface rounded-md p-4 flex flex-wrap items-end gap-4">
                <div className="grid gap-1.5">
                  <label className="text-xs text-muted-foreground">Taux prorata (% du marché)</label>
                  <div className="flex items-center gap-2">
                    <Input type="number" min={0} max={20} step={0.5} value={prorata.rate_pct} onChange={(e) => setProrata({ ...prorata, rate_pct: Number(e.target.value) })} className="rounded-sm h-10 w-24 num" data-testid="prorata-rate" />
                    <span className="text-sm text-muted-foreground">% = {eur(prorata.rate_total)}</span>
                  </div>
                </div>
                <div className="text-right ml-auto">
                  <p className="text-xs text-muted-foreground">Cagnotte prorata totale</p>
                  <p className="num text-2xl font-extrabold text-primary" data-testid="prorata-pot">{eur(prorata.pot)}</p>
                </div>
                <Button className="rounded-sm gap-2" onClick={() => saveProrata({ rate_pct: prorata.rate_pct, expenses: prorata.expenses })} data-testid="prorata-save"><CheckCircle2 className="h-4 w-4" /> Enregistrer</Button>
              </div>

              <div className="surface rounded-md p-4 space-y-2" data-testid="prorata-expenses">
                <div className="flex items-center justify-between"><p className="overline">Dépenses communes</p>
                  <Button size="sm" variant="outline" className="rounded-sm gap-1.5" onClick={addExpense} data-testid="prorata-add-expense"><Plus className="h-4 w-4" /> Ajouter</Button></div>
                {(prorata.expenses || []).map((e, i) => (
                  <div key={i} className="flex items-center gap-2" data-testid={`prorata-exp-${i}`}>
                    <Input value={e.label} onChange={(ev) => updExpense(i, "label", ev.target.value)} placeholder="Ex. benne, nettoyage, gardiennage" className="rounded-sm h-9 flex-1" />
                    <Input type="number" value={e.amount} onChange={(ev) => updExpense(i, "amount", Number(ev.target.value))} className="rounded-sm h-9 w-28 num" />
                    <Button size="icon" variant="ghost" className="h-9 w-9 text-red-500" onClick={() => rmExpense(i)}><Trash2 className="h-4 w-4" /></Button>
                  </div>
                ))}
                <p className="text-xs text-muted-foreground">Dépenses manuelles : {eur(prorata.manual_total)}. La cagnotte = dépenses + taux du marché, répartie ci-dessous au prorata du montant de chaque lot.</p>
              </div>

              <div className="surface rounded-md overflow-hidden" data-testid="prorata-participants">
                <table className="w-full text-sm">
                  <thead><tr className="border-b border-border text-left text-xs text-muted-foreground">
                    <th className="p-3">Lot</th><th className="p-3 text-right">Montant lot HT</th>
                    <th className="p-3 text-center">Quote-part</th><th className="p-3 text-right">Contribution prorata</th></tr></thead>
                  <tbody>
                    {prorata.participants.map((p, i) => (
                      <tr key={i} className="border-b border-border/50">
                        <td className="p-3">{p.designation}</td>
                        <td className="p-3 text-right num">{eur(p.lot_ht)}</td>
                        <td className="p-3 text-center num text-muted-foreground">{p.share_pct}%</td>
                        <td className="p-3 text-right num font-semibold text-primary">{eur(p.share_amount)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </>
          )}
        </TabsContent>

        {/* ---------- Retenue de garantie ---------- */}
        <TabsContent value="retenue" className="space-y-3 mt-4" data-testid="retenue-list">
          {retentions.length === 0 ? <Empty text="Aucune retenue de garantie détenue. Elles apparaissent dès qu'une situation avec retenue est créée." /> : (
            retentions.map((r) => (
              <div key={r.marche_id} className="surface rounded-md p-4 flex flex-wrap items-center gap-4" data-testid={`retenue-${r.marche_id}`}>
                <div className="h-10 w-10 rounded-lg bg-primary/10 grid place-items-center"><ShieldCheck className="h-5 w-5 text-primary" /></div>
                <div className="min-w-0">
                  <p className="font-semibold">{r.label} <RetStatus s={r.status} /></p>
                  <p className="text-xs text-muted-foreground">Retenue détenue : <b className="text-foreground num">{eur(r.held)}</b>{r.release_due ? ` · libération prévue le ${r.release_due}` : " · réception non renseignée"}</p>
                </div>
                <div className="ml-auto flex flex-wrap items-center gap-2">
                  {!r.released && (
                    <div className="flex items-center gap-1">
                      <CalendarClock className="h-4 w-4 text-muted-foreground" />
                      <Input type="date" defaultValue={r.reception_date || ""} onChange={(e) => setReception(r.marche_id, e.target.value)} className="rounded-sm h-9 w-40 num" data-testid={`retenue-reception-${r.marche_id}`} title="Date de réception des travaux" />
                    </div>
                  )}
                  {!r.released && r.client?.email && (
                    <Button size="sm" variant="outline" className="rounded-sm gap-1.5" onClick={() => remindRet(r.marche_id)} data-testid={`retenue-remind-${r.marche_id}`}><Bell className="h-4 w-4" /> Relancer</Button>
                  )}
                  {!r.released ? (
                    <Button size="sm" className="rounded-sm gap-1.5" onClick={() => releaseRet(r.marche_id)} data-testid={`retenue-release-${r.marche_id}`}><CheckCircle2 className="h-4 w-4" /> Libérer</Button>
                  ) : (
                    <Badge variant="outline" className="rounded-sm text-muted-foreground">Libérée le {(r.released_at || "").slice(0, 10)}</Badge>
                  )}
                </div>
              </div>
            ))
          )}
        </TabsContent>

        {/* ---------- Décompte général définitif ---------- */}
        <TabsContent value="dgd" className="space-y-4 mt-4">
          {!marcheId ? <Empty text="Choisissez un marché pour établir son décompte général définitif." /> : !dgd ? <Empty text="Chargement…" /> : (
            <div className="surface rounded-md p-5 space-y-4" data-testid="dgd-panel">
              <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                <Kpi label="Montant marché HT" value={eur(dgd.totals.contract_ht)} />
                <Kpi label="Déjà facturé HT" value={eur(dgd.totals.billed_ht)} />
                <Kpi label="Solde de travaux HT" value={eur(dgd.totals.remaining_ht)} accent />
                <Kpi label="Retenue détenue" value={eur(dgd.totals.retention_held)} />
              </div>
              <div className="text-sm space-y-1">
                <p>Acompte encaissé restant à imputer : <b className="num">{eur(dgd.totals.deposit_available_ht)}</b> HT</p>
                <p>Solde à facturer : <b className="num text-primary">{eur(dgd.totals.dgd_ht)}</b> HT
                  {" · "}{eur(dgd.totals.dgd_ttc)} TTC (TVA {dgd.totals.vat_rate}%)</p>
                <p>Total dû au titre du DGD : <b className="num">{eur(dgd.totals.dgd_due)}</b></p>
              </div>
              {dgd.dgd_doc_id ? (
                <div className="flex flex-wrap items-center gap-2" data-testid="dgd-done">
                  <Badge variant="outline" className="rounded-sm">DGD établi le {(dgd.dgd_at || "").slice(0, 10)}</Badge>
                  <Button size="sm" variant="outline" className="rounded-sm" onClick={() => nav(`/devis-editeur/${dgd.dgd_doc_id}`)} data-testid="dgd-open-invoice">Ouvrir la facture de solde</Button>
                  <Button size="sm" variant="outline" className="rounded-sm gap-1.5" onClick={dgdPdf} data-testid="dgd-pdf-btn"><Download className="h-4 w-4" /> Décompte PDF</Button>
                  <Button size="sm" variant="ghost" className="rounded-sm text-destructive" onClick={cancelDgd} data-testid="dgd-cancel-btn">Annuler le DGD</Button>
                </div>
              ) : (
                <div className="flex flex-wrap items-end gap-4">
                  <label className="flex items-center gap-2 text-xs text-muted-foreground">
                    <Switch checked={dgdDeposit} onCheckedChange={setDgdDeposit} data-testid="dgd-deposit-switch" /> Déduire l'acompte restant
                  </label>
                  <label className="flex items-center gap-2 text-xs text-muted-foreground">
                    <Switch checked={dgdRelease} onCheckedChange={setDgdRelease} data-testid="dgd-release-switch" /> Libérer la retenue de garantie
                  </label>
                  <Button size="sm" variant="outline" className="rounded-sm gap-1.5" onClick={dgdPdf} data-testid="dgd-preview-pdf"><Download className="h-4 w-4" /> Aperçu PDF</Button>
                  <Button className="rounded-sm gap-2 ml-auto" onClick={createDgd} disabled={busy} data-testid="dgd-create-btn">
                    <FileCheck className="h-4 w-4" /> Générer le décompte général
                  </Button>
                </div>
              )}
              <p className="text-[11px] text-muted-foreground">
                Le DGD solde le marché : travaux restants, acompte déjà versé déduit et, si vous le
                choisissez, libération de la retenue de garantie. Une seule facture de solde par marché.
              </p>
            </div>
          )}
        </TabsContent>
      </Tabs>

      {marches.length === 0 && (
        <div className="surface rounded-md p-10 text-center">
          <Layers className="h-10 w-10 mx-auto text-muted-foreground/50" />
          <p className="mt-4 font-semibold">Aucun marché disponible</p>
          <p className="text-sm text-muted-foreground mt-1">Créez d'abord un devis ou une facture avec des lignes.</p>
        </div>
      )}
    </div>
  );
}

const Kpi = ({ label, value, accent }) => (
  <div className="surface p-4 rounded-md">
    <p className="text-xs text-muted-foreground flex items-center gap-1"><Wallet className="h-3.5 w-3.5" /> {label}</p>
    <p className={`num mt-1.5 text-xl font-extrabold ${accent ? "text-primary" : ""}`}>{value}</p>
  </div>
);
const Empty = ({ text }) => (
  <div className="surface rounded-md p-10 text-center text-sm text-muted-foreground" data-testid="tab-empty">{text}</div>
);
