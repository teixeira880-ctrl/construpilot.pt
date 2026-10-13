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
      toast.success(`Conta final criada — fatura ${data.number}`);
      await loadMarche(marcheId);
      loadRetentions();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Impossível gerar");
    } finally { setBusy(false); }
  };

  const cancelDgd = async () => {
    try {
      await api.delete(`/situations/dgd/${marcheId}`);
      toast.success("Conta final anulada");
      await loadMarche(marcheId);
    } catch (e) { toast.error(e?.response?.data?.detail || "Anulação impossível"); }
  };

  const dgdPdf = async () => {
    try {
      const { data } = await api.get(`/situations/dgd-pdf?marche_id=${marcheId}`, { responseType: "blob" });
      const url = URL.createObjectURL(data);
      const a = document.createElement("a");
      a.href = url; a.download = "decompte-general-definitif.pdf"; a.click();
      URL.revokeObjectURL(url);
    } catch { toast.error("PDF indisponível"); }
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
      toast.success(`Auto de medição n.º${data.seq} criada — fatura ${data.invoice_number}`
        + (data.deposit_imputed_ht ? ` · adiantamento deduzido ${data.deposit_imputed_ht} € HT` : ""));
      await refreshMarche(); loadRetentions();
    } catch (e) { toast.error(e?.response?.data?.detail || "Criação impossível"); }
    finally { setBusy(false); }
  };
  const del = async (id) => {
    try { await api.delete(`/situations/${id}`); toast.success("Auto de medição eliminado"); refreshMarche(); loadRetentions(); }
    catch { toast.error("Não foi possível eliminar"); }
  };
  const downloadSituationPdf = async (s) => {
    try {
      const { data } = await api.get(`/situations/${s.situation_id}/pdf`, { responseType: "blob" });
      const url = URL.createObjectURL(new Blob([data], { type: "application/pdf" }));
      const a = document.createElement("a");
      a.href = url; a.download = `decompte-situation-${s.seq}.pdf`; a.click();
      URL.revokeObjectURL(url);
    } catch { toast.error("Impossível gerar o desdobramento"); }
  };
  const downloadCertificate = async (s) => {
    try {
      const { data } = await api.get(`/situations/${s.situation_id}/certificate`, { responseType: "blob" });
      const url = URL.createObjectURL(new Blob([data], { type: "application/pdf" }));
      const a = document.createElement("a");
      a.href = url; a.download = `certificat-paiement-${s.seq}.pdf`; a.click();
      URL.revokeObjectURL(url);
    } catch { toast.error("Impossível gerar o certificado"); }
  };

  // ---- Prorata ----
  const saveProrata = async (cfg) => {
    try {
      const { data } = await api.put(`/situations/${marcheId}/prorata`, cfg);
      setProrata(data); toast.success("Conta pro rata guardada");
    } catch { toast.error("Erro"); }
  };
  const addExpense = () => setProrata({ ...prorata, expenses: [...(prorata.expenses || []), { label: "", amount: 0 }] });
  const updExpense = (i, k, v) => {
    const ex = [...prorata.expenses]; ex[i] = { ...ex[i], [k]: k === "amount" ? v : v }; setProrata({ ...prorata, expenses: ex });
  };
  const rmExpense = (i) => setProrata({ ...prorata, expenses: prorata.expenses.filter((_, x) => x !== i) });

  // ---- Retenues ----
  const setReception = async (mid, date) => {
    if (!date) return;
    try { await api.post(`/situations/${mid}/reception`, { reception_date: date }); toast.success("Data de receção guardada"); loadRetentions(); }
    catch { toast.error("Erro"); }
  };
  const releaseRet = async (mid) => {
    try { await api.post(`/situations/retentions/${mid}/release`); toast.success("Retenção libertada"); loadRetentions(); }
    catch { toast.error("Erro"); }
  };
  const remindRet = async (mid) => {
    try { const { data } = await api.post(`/situations/retentions/${mid}/remind`); toast[data.emails_sent ? "success" : "message"](data.emails_sent ? `Lembrete enviado para ${data.to}` : "E-mail não enviado (cliente sem e-mail ou serviço indisponível)"); }
    catch (e) { toast.error(e?.response?.data?.detail || "Erro"); }
  };

  if (in_org && !can("situations")) return <NoAccess title="Autos de medição não autorizados" />;
  if (!isProBusiness) {
    return (
      <div className="max-w-2xl mx-auto px-6 py-24 text-center" data-testid="situations-locked">
        <div className="h-14 w-14 rounded-xl bg-primary/10 grid place-items-center mx-auto mb-5"><Lock className="h-7 w-7 text-primary" /></div>
        <h1 className="font-display text-3xl font-bold">Faturação progressiva</h1>
        <p className="text-muted-foreground mt-3">Autos de medição, progresso acumulado, retenção de garantia e conta prorata — reservado ao <b>pack Business</b>.</p>
        <Button className="rounded-sm mt-6 gap-2" onClick={() => nav("/planos")} data-testid="situations-upgrade-btn">Passar ao pack Business <ArrowRight className="h-4 w-4" /></Button>
      </div>
    );
  }

  const RetStatus = ({ s }) => {
    const map = { released: ["Liberada", "text-muted-foreground border-border"], due: ["A libertar", "text-red-500 border-red-500/30"], pending: ["Em curso", "text-amber-500 border-amber-500/30"], held: ["Detida", "text-primary border-primary/30"] };
    const [l, c] = map[s] || map.held;
    return <Badge variant="outline" className={`rounded-sm ${c}`}>{l}</Badge>;
  };

  return (
    <div className="max-w-5xl mx-auto px-4 py-10 space-y-6" data-testid="situations-page">
      <SectionTitle over="Pack Business" title="Autos de medição">
        Fature as suas empreitadas por autos, controle o acumulado, a retenção de garantia e a conta de rateio.
      </SectionTitle>

      <div className="grid gap-1.5 max-w-md">
        <label className="text-xs text-muted-foreground">Mercado de referência (orçamento ou fatura)</label>
        <Select value={marcheId} onValueChange={loadMarche}>
          <SelectTrigger className="rounded-sm" data-testid="situation-marche-select"><SelectValue placeholder="Escolher um mercado…" /></SelectTrigger>
          <SelectContent>
            {marches.map((m) => (
              <SelectItem key={m.doc_id} value={m.doc_id} data-testid={`marche-opt-${m.doc_id}`}>
                {(m.number || "Rascunho")} · {m.title || "Sem título"} — {eur(m.total_ht)} HT
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      {summary && (
        <div className="grid grid-cols-2 md:grid-cols-5 gap-3" data-testid="marche-banner">
          <Kpi label="Montante contrato s/ IVA" value={eur(summary.totals.contract_ht)} />
          <Kpi label="Adiantamento recebido c/ IVA" value={eur(summary.totals.deposit_paid_ttc)} />
          <Kpi label="Faturado até à data s/ IVA" value={eur(summary.totals.billed_ht)} accent />
          <Kpi label="Retenção detida" value={eur(summary.totals.retention_held)} />
          <Kpi label="Por faturar s/ IVA" value={eur(summary.totals.remaining_ht)} />
        </div>
      )}
      {summary && dep && (dep.invoiced_ttc > 0) && (
        <p className="text-xs text-muted-foreground" data-testid="marche-deposit-note">
          Adiantamento faturado {eur(dep.invoiced_ttc)} c/ IVA · recebido {eur(dep.paid_ttc)} c/ IVA
          {dep.unpaid_ttc > 0 ? ` · não recebido ${eur(dep.unpaid_ttc)} (não dedutível)` : ""}
          {" "}· já imputado {eur(dep.imputed_ht)} s/ IVA · disponível {eur(dep.available_ht)} HT
        </p>
      )}

      <Tabs defaultValue="situation" className="w-full">
        <TabsList className="rounded-sm flex-wrap h-auto" data-testid="situations-tabs">
          <TabsTrigger value="situation" data-testid="tab-situation">Nova situação</TabsTrigger>
          <TabsTrigger value="avancement" data-testid="tab-avancement">Avanço</TabsTrigger>
          <TabsTrigger value="prorata" data-testid="tab-prorata">Conta pro rata</TabsTrigger>
          <TabsTrigger value="retenue" data-testid="tab-retenue">Retenção de garantia</TabsTrigger>
          <TabsTrigger value="dgd" data-testid="tab-dgd">Conta final</TabsTrigger>
        </TabsList>

        {/* ---------- Nouvelle situation ---------- */}
        <TabsContent value="situation" className="space-y-4 mt-4">
          {!marcheId ? <Empty text="Escolha uma empreitada para criar um auto de medição." /> : (
            <>
              <div className="surface rounded-md overflow-hidden" data-testid="situation-lines">
                <table className="w-full text-sm">
                  <thead><tr className="border-b border-border text-left text-xs text-muted-foreground">
                    <th className="p-3">Artigo</th><th className="p-3 text-right">Valor s/ IVA</th>
                    <th className="p-3 text-center">% ant.</th><th className="p-3 text-center">% acumulado</th>
                    <th className="p-3 text-right">Este auto s/ IVA</th></tr></thead>
                  <tbody>
                    {baseLines.map((l, i) => (
                      <tr key={i} className="border-b border-border/50" data-testid={`sit-line-${i}`}>
                        <td className="p-3">{l.designation || `Linha ${i + 1}`}</td>
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
                  <label className="text-xs text-muted-foreground flex items-center gap-1"><Percent className="h-3 w-3" /> Retenção de garantia</label>
                  <div className="flex items-center gap-2">
                    <Input type="number" min={0} max={10} step={0.5} value={retention} onChange={(e) => setRetention(e.target.value)} className="rounded-sm h-10 w-24 num" data-testid="situation-retention" />
                    <span className="text-sm text-muted-foreground">% · {eur(retentionAmt)}</span>
                    <Button variant="ghost" size="sm" className="rounded-sm text-xs" onClick={() => setRetention(5)} data-testid="retention-5">5%</Button>
                  </div>
                </div>
                <div className="grid gap-1.5">
                  <label className="text-xs text-muted-foreground flex items-center gap-1"><Wallet className="h-3 w-3" /> Adiantamento já pago</label>
                  <div className="flex items-center gap-2">
                    <Select value={depMode} onValueChange={setDepMode}>
                      <SelectTrigger className="rounded-sm h-10 w-52" data-testid="situation-deposit-mode"><SelectValue /></SelectTrigger>
                      <SelectContent>
                        <SelectItem value="prorata" data-testid="dep-mode-prorata">Proporcionalmente ao avanço</SelectItem>
                        <SelectItem value="full" data-testid="dep-mode-full">Na totalidade agora</SelectItem>
                        <SelectItem value="manual" data-testid="dep-mode-manual">Montante manual</SelectItem>
                        <SelectItem value="none" data-testid="dep-mode-none">Não deduzir</SelectItem>
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
                      ? <>Disponível: {eur(depAvailable)} s/ IVA · dedução: <b className="text-foreground">-{eur(depDeduct)}</b></>
                      : "Nenhum adiantamento recebido a deduzir nesta empreitada."}
                  </p>
                </div>
                <div className="text-right">
                  <p className="text-xs text-muted-foreground">Obras {eur(totalHT)} HT</p>
                  <p className="num text-2xl font-extrabold text-primary" data-testid="situation-total-ht">{eur(invoiceHt)}</p>
                  <p className="text-[11px] text-muted-foreground">Fatura s/ IVA após adiantamento</p>
                </div>
                <Button className="rounded-sm gap-2" disabled={busy || totalHT <= 0} onClick={submit} data-testid="situation-create-btn">
                  <Plus className="h-4 w-4" /> Criar o auto de medição n.º{situations.length + 1}
                </Button>
              </div>
              {situations.length > 0 && (
                <div className="space-y-2" data-testid="situations-history">
                  <p className="overline">Histórico</p>
                  {situations.map((s) => (
                    <div key={s.situation_id} className="surface rounded-sm p-4 flex flex-wrap items-center gap-4" data-testid={`situation-row-${s.situation_id}`}>
                      <div className="h-9 w-9 rounded-lg bg-primary/10 grid place-items-center"><TrendingUp className="h-4 w-4 text-primary" /></div>
                      <div>
                        <p className="font-semibold">Auto de medição n.º{s.seq} · {s.invoice_number}</p>
                        <p className="text-xs text-muted-foreground">{eur(s.total_ttc)} c/ IVA{s.deposit_imputed_ht ? ` · adiantamento deduzido ${eur(s.deposit_imputed_ht)} HT` : ""}{s.retention_amount ? ` · retenção ${eur(s.retention_amount)} · net ${eur(s.net_due)}` : ""}</p>
                      </div>
                      <div className="ml-auto flex gap-2">
                        <Button size="sm" variant="outline" className="rounded-sm gap-1.5 text-primary border-primary/30" onClick={() => downloadSituationPdf(s)} data-testid={`situation-pdf-${s.situation_id}`}><FileText className="h-4 w-4" /> Auto PDF</Button>
                        <Button size="sm" variant="outline" className="rounded-sm gap-1.5" onClick={() => downloadCertificate(s)} data-testid={`situation-cert-${s.situation_id}`}><ShieldCheck className="h-4 w-4" /> Certificado</Button>
                        <Button size="sm" variant="outline" className="rounded-sm gap-1.5" onClick={() => nav(`/devis-editeur/${s.invoice_doc_id}`)} data-testid={`situation-open-${s.situation_id}`}><FileText className="h-4 w-4" /> Fatura</Button>
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
          {!summary ? <Empty text="Escolha uma empreitada para ver o seu avanço." /> : (
            <>
              <div className="grid grid-cols-2 md:grid-cols-4 gap-3" data-testid="avancement-kpis">
                <Kpi label="Montante contrato s/ IVA" value={eur(summary.totals.contract_ht)} />
                <Kpi label="Já faturado s/ IVA" value={eur(summary.totals.billed_ht)} accent />
                <Kpi label="Restante a faturar" value={eur(summary.totals.remaining_ht)} />
                <Kpi label="Retenção detida" value={eur(summary.totals.retention_held)} />
              </div>
              <div className="surface rounded-md p-5">
                <div className="flex items-center justify-between text-sm mb-2">
                  <span className="text-muted-foreground">Avanço global</span>
                  <span className="num font-bold text-primary">{summary.totals.pct_global}%</span>
                </div>
                <div className="h-3 rounded-full bg-secondary overflow-hidden">
                  <div className="h-full bg-primary rounded-full transition-all" style={{ width: `${Math.min(summary.totals.pct_global, 100)}%` }} data-testid="avancement-bar" />
                </div>
                <p className="text-xs text-muted-foreground mt-2">{summary.totals.situations_count} auto(s) de medição emitido(s) · {eur(summary.totals.billed_ttc)} c/ IVA faturados</p>
              </div>
              <div className="surface rounded-md overflow-hidden" data-testid="avancement-lines">
                <table className="w-full text-sm">
                  <thead><tr className="border-b border-border text-left text-xs text-muted-foreground">
                    <th className="p-3">Lote</th><th className="p-3 text-right">Valor s/ IVA</th>
                    <th className="p-3 text-center">Avanço</th><th className="p-3 text-right">Faturado s/ IVA</th>
                    <th className="p-3 text-right">Restante s/ IVA</th></tr></thead>
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
          {!prorata ? <Empty text="Escolha uma empreitada para gerir a sua conta de despesas comuns." /> : (
            <>
              <div className="surface rounded-md p-4 flex flex-wrap items-end gap-4">
                <div className="grid gap-1.5">
                  <label className="text-xs text-muted-foreground">Taxa pro rata (% do contrato)</label>
                  <div className="flex items-center gap-2">
                    <Input type="number" min={0} max={20} step={0.5} value={prorata.rate_pct} onChange={(e) => setProrata({ ...prorata, rate_pct: Number(e.target.value) })} className="rounded-sm h-10 w-24 num" data-testid="prorata-rate" />
                    <span className="text-sm text-muted-foreground">% = {eur(prorata.rate_total)}</span>
                  </div>
                </div>
                <div className="text-right ml-auto">
                  <p className="text-xs text-muted-foreground">Bónus pro rata total</p>
                  <p className="num text-2xl font-extrabold text-primary" data-testid="prorata-pot">{eur(prorata.pot)}</p>
                </div>
                <Button className="rounded-sm gap-2" onClick={() => saveProrata({ rate_pct: prorata.rate_pct, expenses: prorata.expenses })} data-testid="prorata-save"><CheckCircle2 className="h-4 w-4" /> Guardar</Button>
              </div>

              <div className="surface rounded-md p-4 space-y-2" data-testid="prorata-expenses">
                <div className="flex items-center justify-between"><p className="overline">Despesas comuns</p>
                  <Button size="sm" variant="outline" className="rounded-sm gap-1.5" onClick={addExpense} data-testid="prorata-add-expense"><Plus className="h-4 w-4" /> Adicionar</Button></div>
                {(prorata.expenses || []).map((e, i) => (
                  <div key={i} className="flex items-center gap-2" data-testid={`prorata-exp-${i}`}>
                    <Input value={e.label} onChange={(ev) => updExpense(i, "label", ev.target.value)} placeholder="Ex. contentor, limpeza, vigilância" className="rounded-sm h-9 flex-1" />
                    <Input type="number" value={e.amount} onChange={(ev) => updExpense(i, "amount", Number(ev.target.value))} className="rounded-sm h-9 w-28 num" />
                    <Button size="icon" variant="ghost" className="h-9 w-9 text-red-500" onClick={() => rmExpense(i)}><Trash2 className="h-4 w-4" /></Button>
                  </div>
                ))}
                <p className="text-xs text-muted-foreground">Despesas manuais: {eur(prorata.manual_total)}. O fundo comum = despesas + taxa da empreitada, distribuído abaixo proporcionalmente ao montante de cada capítulo.</p>
              </div>

              <div className="surface rounded-md overflow-hidden" data-testid="prorata-participants">
                <table className="w-full text-sm">
                  <thead><tr className="border-b border-border text-left text-xs text-muted-foreground">
                    <th className="p-3">Lote</th><th className="p-3 text-right">Montante lote s/ IVA</th>
                    <th className="p-3 text-center">Quota-parte</th><th className="p-3 text-right">Contribuição proporcional</th></tr></thead>
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
          {retentions.length === 0 ? <Empty text="Nenhuma retenção de garantia detida. Aparecem assim que for criado um auto de medição com retenção." /> : (
            retentions.map((r) => (
              <div key={r.marche_id} className="surface rounded-md p-4 flex flex-wrap items-center gap-4" data-testid={`retenue-${r.marche_id}`}>
                <div className="h-10 w-10 rounded-lg bg-primary/10 grid place-items-center"><ShieldCheck className="h-5 w-5 text-primary" /></div>
                <div className="min-w-0">
                  <p className="font-semibold">{r.label} <RetStatus s={r.status} /></p>
                  <p className="text-xs text-muted-foreground">Retenção detida: <b className="text-foreground num">{eur(r.held)}</b>{r.release_due ? ` · libertação prevista em ${r.release_due}` : " · receção não preenchida"}</p>
                </div>
                <div className="ml-auto flex flex-wrap items-center gap-2">
                  {!r.released && (
                    <div className="flex items-center gap-1">
                      <CalendarClock className="h-4 w-4 text-muted-foreground" />
                      <Input type="date" defaultValue={r.reception_date || ""} onChange={(e) => setReception(r.marche_id, e.target.value)} className="rounded-sm h-9 w-40 num" data-testid={`retenue-reception-${r.marche_id}`} title="Data de receção dos trabalhos" />
                    </div>
                  )}
                  {!r.released && r.client?.email && (
                    <Button size="sm" variant="outline" className="rounded-sm gap-1.5" onClick={() => remindRet(r.marche_id)} data-testid={`retenue-remind-${r.marche_id}`}><Bell className="h-4 w-4" /> Relançar</Button>
                  )}
                  {!r.released ? (
                    <Button size="sm" className="rounded-sm gap-1.5" onClick={() => releaseRet(r.marche_id)} data-testid={`retenue-release-${r.marche_id}`}><CheckCircle2 className="h-4 w-4" /> Liberar</Button>
                  ) : (
                    <Badge variant="outline" className="rounded-sm text-muted-foreground">Libertada a {(r.released_at || "").slice(0, 10)}</Badge>
                  )}
                </div>
              </div>
            ))
          )}
        </TabsContent>

        {/* ---------- Décompte général définitif ---------- */}
        <TabsContent value="dgd" className="space-y-4 mt-4">
          {!marcheId ? <Empty text="Escolha uma empreitada para elaborar a sua conta final." /> : !dgd ? <Empty text="A carregar…" /> : (
            <div className="surface rounded-md p-5 space-y-4" data-testid="dgd-panel">
              <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                <Kpi label="Montante contrato s/ IVA" value={eur(dgd.totals.contract_ht)} />
                <Kpi label="Já faturado s/ IVA" value={eur(dgd.totals.billed_ht)} />
                <Kpi label="Saldo dos trabalhos s/ IVA" value={eur(dgd.totals.remaining_ht)} accent />
                <Kpi label="Retenção detida" value={eur(dgd.totals.retention_held)} />
              </div>
              <div className="text-sm space-y-1">
                <p>Adiantamento recebido por imputar: <b className="num">{eur(dgd.totals.deposit_available_ht)}</b> HT</p>
                <p>Saldo a faturar: <b className="num text-primary">{eur(dgd.totals.dgd_ht)}</b> HT
                  {" · "}{eur(dgd.totals.dgd_ttc)} c/ IVA (IVA {dgd.totals.vat_rate}%)</p>
                <p>Total devido a título da conta final: <b className="num">{eur(dgd.totals.dgd_due)}</b></p>
              </div>
              {dgd.dgd_doc_id ? (
                <div className="flex flex-wrap items-center gap-2" data-testid="dgd-done">
                  <Badge variant="outline" className="rounded-sm">Conta final elaborada em {(dgd.dgd_at || "").slice(0, 10)}</Badge>
                  <Button size="sm" variant="outline" className="rounded-sm" onClick={() => nav(`/devis-editeur/${dgd.dgd_doc_id}`)} data-testid="dgd-open-invoice">Abrir a fatura final</Button>
                  <Button size="sm" variant="outline" className="rounded-sm gap-1.5" onClick={dgdPdf} data-testid="dgd-pdf-btn"><Download className="h-4 w-4" /> Auto PDF</Button>
                  <Button size="sm" variant="ghost" className="rounded-sm text-destructive" onClick={cancelDgd} data-testid="dgd-cancel-btn">Anular a conta final</Button>
                </div>
              ) : (
                <div className="flex flex-wrap items-end gap-4">
                  <label className="flex items-center gap-2 text-xs text-muted-foreground">
                    <Switch checked={dgdDeposit} onCheckedChange={setDgdDeposit} data-testid="dgd-deposit-switch" /> Deduzir o adiantamento restante
                  </label>
                  <label className="flex items-center gap-2 text-xs text-muted-foreground">
                    <Switch checked={dgdRelease} onCheckedChange={setDgdRelease} data-testid="dgd-release-switch" /> Libertar a retenção de garantia
                  </label>
                  <Button size="sm" variant="outline" className="rounded-sm gap-1.5" onClick={dgdPdf} data-testid="dgd-preview-pdf"><Download className="h-4 w-4" /> Pré-visualização PDF</Button>
                  <Button className="rounded-sm gap-2 ml-auto" onClick={createDgd} disabled={busy} data-testid="dgd-create-btn">
                    <FileCheck className="h-4 w-4" /> Gerar a conta final
                  </Button>
                </div>
              )}
              <p className="text-[11px] text-muted-foreground">
                A conta final salda a empreitada: trabalhos restantes, adiantamento já pago deduzido e, se o escolher, libertação da retenção de garantia. Uma única fatura final por empreitada.
              </p>
            </div>
          )}
        </TabsContent>
      </Tabs>

      {marches.length === 0 && (
        <div className="surface rounded-md p-10 text-center">
          <Layers className="h-10 w-10 mx-auto text-muted-foreground/50" />
          <p className="mt-4 font-semibold">Nenhum mercado disponível</p>
          <p className="text-sm text-muted-foreground mt-1">Crie primeiro um orçamento ou uma fatura com linhas.</p>
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
