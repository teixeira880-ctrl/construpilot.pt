import { useCallback, useEffect, useRef, useState } from "react";
import { toast } from "sonner";
import { Leaf, Upload, Download, FileSpreadsheet, Loader2, Trash2, Save, AlertTriangle, CheckCircle2, Info, FileText, RotateCcw } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { api, API } from "@/lib/api";

const NIV = {
  bloquant: ["Bloqueante", "bg-red-100 text-red-800 border-red-200", AlertTriangle],
  alerte: ["Fora do imperativo", "bg-orange-100 text-orange-800 border-orange-200", AlertTriangle],
  manquant: ["Informação em falta", "bg-amber-50 text-amber-800 border-amber-200", Info],
  info: ["Info", "bg-sky-50 text-sky-800 border-sky-200", Info],
};
const STATUT = { "Conforme": "bg-emerald-100 text-emerald-800", "Em curso": "bg-sky-100 text-sky-800", "A iniciar": "bg-amber-100 text-amber-800", "Não conforme": "bg-red-100 text-red-800", "Não aplicável": "bg-slate-100 text-slate-600" };
const n = (v, d = 0) => (v === null || v === undefined || v === "" ? "—" : Number(v).toLocaleString("pt-PT", { maximumFractionDigits: d, minimumFractionDigits: 0 }));
const numOrNull = (v) => (v === "" || v === null || v === undefined ? null : Number(String(v).replace(",", ".")));

const Card = ({ title, icon: Icon, action, children, testId }) => (
  <section className="surface" data-testid={testId}>
    <div className="flex items-center justify-between gap-2 p-4 border-b border-border flex-wrap">
      <p className="font-display font-bold text-sm flex items-center gap-2">{Icon && <Icon className="h-4 w-4 text-primary" />}{title}</p>
      {action}
    </div>
    <div className="p-4">{children}</div>
  </section>
);

export function BasCarbonePanel({ chantierId }) {
  const [data, setData] = useState(null);
  const [mats, setMats] = useState([]);
  const [dirty, setDirty] = useState(false);
  const [busy, setBusy] = useState("");
  const [lus, setLus] = useState([]);
  const [etudes, setEtudes] = useState([]);
  const [filtre, setFiltre] = useState("ouverts");
  const fileRef = useRef(null);
  const xlsRef = useRef(null);
  const base = `/chantiers/${chantierId}/bas-carbone`;

  const apply = useCallback((d) => { setData(d); setMats(d.dossier.materiaux); setDirty(false); }, []);
  const load = useCallback(() => api.get(base).then(({ data: d }) => apply(d)).catch(() => toast.error("Não foi possível carregar")), [base, apply]);
  useEffect(() => { load(); api.get(`${base}/etudes`).then(({ data: d }) => setEtudes(d)).catch(() => {}); }, [load, base]);

  const run = async (label, fn) => {
    setBusy(label);
    try { const { data: d } = await fn(); apply(d); return d; }
    catch (e) { toast.error(e?.response?.data?.detail || "Operação impossível"); }
    finally { setBusy(""); }
  };
  const put = (body, msg) => run("save", () => api.put(base, body)).then((d) => d && msg && toast.success(msg));

  const upload = async (files) => {
    if (!files?.length) return;
    const fd = new FormData();
    [...files].forEach((f) => fd.append("files", f));
    const d = await run("upload", () => api.post(`${base}/documents`, fd, { headers: { "Content-Type": "multipart/form-data" } }));
    if (d) { setLus(d.lus || []); toast.success(`${(d.lus || []).length} documento(s) lido(s) e integrado(s) no quadro`); }
    if (fileRef.current) fileRef.current.value = "";
  };
  const importXls = async (file) => {
    if (!file) return;
    const fd = new FormData();
    fd.append("file", file);
    const d = await run("xls", () => api.post(`${base}/importer-excel`, fd, { headers: { "Content-Type": "multipart/form-data" } }));
    if (d) toast.success((d.import || []).join(" · ") || "Quadro importado");
    if (xlsRef.current) xlsRef.current.value = "";
  };

  if (!data) return <div className="surface p-6 text-sm text-muted-foreground flex items-center gap-2"><Loader2 className="h-4 w-4 animate-spin" /> A carregar a carta de baixo carbono…</div>;
  const { dossier, resultats: r, referentiel: ref } = data;
  const t = r.totaux, pj = r.projet;
  const ctrls = r.controles.filter((c) => (filtre === "tous" ? true : c.niveau !== "info"));
  const statut = t.conforme === true ? ["Cumpre a meta", "text-emerald-700"] : t.conforme === false ? ["Acima da meta", "text-red-700"] : ["Impossível avaliar (dados em falta)", "text-amber-700"];
  const setMat = (i, k, v) => { setMats((m) => m.map((x, j) => (j === i ? { ...x, [k]: v } : x))); setDirty(true); };
  const res = (id) => r.materiaux.find((x) => x.id === id) || {};

  return (
    <div className="space-y-4" data-testid="chantier-bas-carbone">
      <section className="surface p-4">
        <div className="flex items-start justify-between gap-3 flex-wrap">
          <div>
            <p className="font-display font-bold flex items-center gap-2"><Leaf className="h-5 w-5 text-primary" /> Carta de obra de baixo carbono</p>
            <p className="text-xs text-muted-foreground mt-1 max-w-2xl">As empresas depositam as DAP, fichas técnicas, guias de remessa, e-GAR e faturas de gasóleo : o quadro preenche-se sozinho e cada resultado é comparado com os imperativos da obra.</p>
          </div>
          <div className="flex flex-wrap gap-2">
            <a className="inline-flex items-center gap-1.5 rounded-md border px-3 h-9 text-sm hover:bg-secondary" href={`${API}${base}/export.xlsx`} data-testid="bc-export-xlsx"><FileSpreadsheet className="h-4 w-4" /> Excel</a>
            <a className="inline-flex items-center gap-1.5 rounded-md border px-3 h-9 text-sm hover:bg-secondary" href={`${API}${base}/export.pdf`} target="_blank" rel="noreferrer" data-testid="bc-export-pdf"><Download className="h-4 w-4" /> PDF</a>
          </div>
        </div>
        <div className="grid grid-cols-2 lg:grid-cols-5 gap-3 mt-4" data-testid="bc-kpis">
          {[["Balanço real", `${n(t.total_reel / 1000, 1)} tCO2e`], ["Rácio real", `${n(t.ic_reel)} kgCO2e/m²`], ["Meta (dono de obra)", t.seuil ? `${n(t.seuil)} kgCO2e/m²` : "a definir"],
            ["Ganho materiais", `${n(t.gain / 1000, 1)} t (${Math.round((t.reduction || 0) * 100)} %)`], ["Linhas com DAP", `${r.completude.avec_fdes} / ${r.completude.lignes}`]].map(([l, v]) => (
            <div key={l} className="rounded-xl border p-3"><p className="text-[11px] uppercase tracking-wide text-muted-foreground">{l}</p><p className="font-display font-bold num">{v}</p></div>))}
        </div>
        <p className={`text-sm font-semibold mt-3 ${statut[1]}`}>{statut[0]}</p>
      </section>

      <Card title="Depositar documentos" icon={Upload} testId="bc-upload">
        <label className="flex flex-col items-center justify-center gap-2 rounded-xl border-2 border-dashed p-6 text-center cursor-pointer hover:border-primary/60"
          onDragOver={(e) => e.preventDefault()} onDrop={(e) => { e.preventDefault(); upload(e.dataTransfer.files); }}>
          {busy === "upload" ? <Loader2 className="h-6 w-6 animate-spin text-primary" /> : <Upload className="h-6 w-6 text-primary" />}
          <span className="text-sm font-medium">{busy === "upload" ? "A ler os documentos…" : "Arraste para aqui as DAP, fichas técnicas, guias de remessa, e-GAR, faturas de gasóleo / HVO"}</span>
          <span className="text-xs text-muted-foreground">PDF ou fotografias · máx. 25 ficheiros · cada valor lido tem de figurar no documento</span>
          <input ref={fileRef} type="file" multiple accept=".pdf,.png,.jpg,.jpeg,.webp,.txt" className="hidden" onChange={(e) => upload(e.target.files)} data-testid="bc-file-input" />
        </label>
        <div className="flex flex-wrap gap-2 mt-3">
          {etudes.length > 0 && (
            <select className="h-9 rounded-md border px-2 text-sm bg-background" defaultValue="" onChange={(e) => e.target.value && run("etude", () => api.post(`${base}/importer-etude`, { job_id: e.target.value })).then((d) => d && toast.success("Quantidades da medição do estudo retomadas"))} data-testid="bc-import-etude">
              <option value="">Retomar a medição de um estudo completo…</option>
              {etudes.map((e) => <option key={e.job_id} value={e.job_id}>{e.nom || e.job_id} · {String(e.created_at || "").slice(0, 10)}</option>)}
            </select>)}
          <Button variant="outline" size="sm" className="gap-1.5 h-9" onClick={() => xlsRef.current?.click()} disabled={!!busy} data-testid="bc-import-xlsx"><FileSpreadsheet className="h-4 w-4" /> Importar um quadro Excel</Button>
          <input ref={xlsRef} type="file" accept=".xlsx" className="hidden" onChange={(e) => importXls(e.target.files?.[0])} />
          <Button variant="ghost" size="sm" className="gap-1.5 h-9 ms-auto" onClick={() => window.confirm("Recomeçar com um quadro vazio ? Os documentos e dados introduzidos serão apagados.") && run("reset", () => api.post(`${base}/reinitialiser`))} data-testid="bc-reset"><RotateCcw className="h-4 w-4" /> Reiniciar</Button>
        </div>
        {lus.length > 0 && (
          <ul className="mt-3 space-y-1 text-xs" data-testid="bc-lus">
            {lus.map((x) => <li key={x.doc_id} className="rounded-md bg-secondary/50 px-3 py-2"><b>{x.nom}</b> — {x.type} · {x.statut}{x.decisions?.length ? ` · ${x.decisions.join(" ; ")}` : ""}{x.notes?.length ? ` · ⚠ ${x.notes.join(" ; ")}` : ""}</li>)}
          </ul>)}
      </Card>

      <Card title={`Controlos (${r.controles.length})`} icon={AlertTriangle} testId="bc-controles"
        action={<div className="flex gap-1">{["ouverts", "tous"].map((f) => <Button key={f} size="sm" variant={filtre === f ? "default" : "ghost"} className="h-7" onClick={() => setFiltre(f)}>{f === "ouverts" ? "A tratar" : "Todos"}</Button>)}</div>}>
        <div className="flex flex-wrap gap-2 mb-3">{Object.entries(NIV).map(([k, [l, cls]]) => <span key={k} className={`rounded-full border px-2.5 py-0.5 text-xs font-semibold ${cls}`}>{l} : {r.compte_controles[k]}</span>)}</div>
        {ctrls.length === 0 ? <p className="text-sm text-emerald-700 flex items-center gap-2"><CheckCircle2 className="h-4 w-4" /> Nada a assinalar : tudo preenchido e dentro dos imperativos.</p> : (
          <ul className="space-y-1.5 max-h-80 overflow-y-auto">{ctrls.map((c, i) => { const [l, cls, I] = NIV[c.niveau]; return (
            <li key={i} className={`rounded-lg border px-3 py-2 text-sm ${cls}`}><p className="flex items-start gap-2"><I className="h-4 w-4 mt-0.5 shrink-0" /><span><b>{l}</b> · {c.message}</span></p>{c.action && <p className="text-xs ms-6 opacity-80">→ {c.action}</p>}</li>); })}</ul>)}
      </Card>

      <Card title="Projeto & meta de carbono" icon={Leaf} testId="bc-projet">
        <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-3 text-sm">
          <label className="space-y-1"><span className="text-xs text-muted-foreground">Tipologia</span>
            <select className="w-full h-9 rounded-md border px-2 bg-background" value={pj.typologie || ""} onChange={(e) => put({ projet: { typologie: e.target.value } })}>{ref.typologies.map((x) => <option key={x}>{x}</option>)}</select></label>
          <label className="space-y-1"><span className="text-xs text-muted-foreground">Área útil de referência (m²)</span>
            <Input type="number" defaultValue={pj.sref_m2 ?? ""} key={`s${pj.sref_m2}`} onBlur={(e) => put({ projet: { sref_m2: numOrNull(e.target.value) } })} /></label>
          <label className="space-y-1 lg:col-span-2"><span className="text-xs text-muted-foreground">Meta de carbono do dono de obra (kgCO2e/m²)</span>
            <Input type="number" placeholder="a definir (sem valor-limite legal em Portugal)" defaultValue={dossier.projet.seuil_ic ?? ""} key={`i${dossier.projet.seuil_ic}`} onBlur={(e) => put({ projet: { seuil_ic: numOrNull(e.target.value) } })} /></label>
        </div>
        <p className="text-xs text-muted-foreground mt-2">Fonte da meta : {pj.seuil_source || "a introduzir"}. O rácio do quadro é um indicador de pilotagem ; o PAG do ciclo de vida (Diretiva (UE) 2024/1275) resulta de uma ACV completa.</p>
      </Card>

      <Card title="Acompanhamento dos materiais" icon={FileText} testId="bc-materiaux"
        action={<div className="flex gap-2">
          <select className="h-8 rounded-md border px-2 text-xs bg-background" value="" onChange={(e) => { const f = ref.familles.find((x) => x.code === e.target.value); if (f) { setMats((m) => [...m, { code: f.code, lot: f.lot, famille: f.famille, unite: f.unite, typologie: "Standard", quantite_prevue: 0 }]); setDirty(true); } }} data-testid="bc-add-line">
            <option value="">+ Adicionar uma família…</option>{ref.familles.map((f) => <option key={f.code} value={f.code}>{f.famille}</option>)}</select>
          <Button size="sm" className="h-8 gap-1" disabled={!dirty || !!busy} onClick={() => put({ materiaux: mats }, "Quadro guardado")} data-testid="bc-save"><Save className="h-3.5 w-3.5" /> Guardar</Button></div>}>
        <div className="overflow-x-auto -mx-4">
          <table className="w-full text-xs min-w-[1050px]">
            <thead><tr className="text-left text-muted-foreground border-b">{["Capítulo / família", "Tipologia", "Qtd. prevista", "Qtd. entregue (guias)", "U", "FE ref.", "FE DAP", "Ref. DAP (registo)", "Dist. km", "Peso real kgCO2e", "Ganho", "Controlo", ""].map((h) => <th key={h} className="px-2 py-2 font-medium">{h}</th>)}</tr></thead>
            <tbody>{mats.map((m, i) => { const x = res(m.id); const worst = ["bloquant", "alerte", "manquant"].find((k) => (x.controles || []).some((c) => c.niveau === k)); return (
              <tr key={m.id || `new${i}`} className="border-b align-top">
                <td className="px-2 py-1.5 min-w-[200px]"><p className="text-[10px] text-muted-foreground">{m.lot}</p><p className="font-medium">{m.famille}</p>{m.solution && <p className="text-[10px] text-muted-foreground">{m.solution}</p>}</td>
                <td className="px-2 py-1.5"><select className="h-7 rounded border px-1 bg-background" value={m.typologie} onChange={(e) => setMat(i, "typologie", e.target.value)}>{ref.typologies_materiau.map((y) => <option key={y}>{y}</option>)}</select></td>
                {["quantite_prevue", "quantite_livree"].map((k) => <td key={k} className="px-2 py-1.5"><input className="w-20 h-7 rounded border px-1 num" value={m[k] ?? ""} onChange={(e) => setMat(i, k, numOrNull(e.target.value))} /></td>)}
                <td className="px-2 py-1.5">{m.unite}</td>
                {["fe_ref", "fe_fdes"].map((k) => <td key={k} className="px-2 py-1.5"><input className="w-16 h-7 rounded border px-1 num" value={m[k] ?? ""} onChange={(e) => setMat(i, k, numOrNull(e.target.value))} /></td>)}
                <td className="px-2 py-1.5"><input className="w-28 h-7 rounded border px-1" value={m.ref_fdes ?? ""} onChange={(e) => setMat(i, "ref_fdes", e.target.value)} /></td>
                <td className="px-2 py-1.5"><input className="w-14 h-7 rounded border px-1 num" title={m.distance_source || ""} value={m.distance_km ?? ""} onChange={(e) => setMat(i, "distance_km", numOrNull(e.target.value))} /></td>
                <td className="px-2 py-1.5 num">{n(x.poids_reel)}</td>
                <td className="px-2 py-1.5 num">{x.poids_ref ? `${Math.round((x.reduction || 0) * 100)} %` : "—"}</td>
                <td className="px-2 py-1.5">{worst ? <span title={(x.controles || []).map((c) => c.message).join("\n")} className={`rounded-full border px-2 py-0.5 text-[10px] font-semibold ${NIV[worst][1]}`}>{(x.controles || []).length} pt</span> : x.id ? <CheckCircle2 className="h-4 w-4 text-emerald-600" /> : null}</td>
                <td className="px-2 py-1.5"><button type="button" title="Apagar a linha" onClick={() => { setMats((mm) => mm.filter((_, j) => j !== i)); setDirty(true); }}><Trash2 className="h-3.5 w-3.5 text-muted-foreground hover:text-red-600" /></button></td>
              </tr>); })}</tbody>
          </table>
        </div>
      </Card>

      <div className="grid lg:grid-cols-2 gap-4">
        <Card title="Emissões da fase de obra" icon={Leaf} testId="bc-emissions">
          <table className="w-full text-xs"><tbody>{r.emissions.map((e) => (
            <tr key={e.id} className="border-b"><td className="py-1.5 pe-2"><p className="font-medium">{e.ressource}</p><p className="text-[10px] text-muted-foreground">{e.poste} · {e.fe} {e.unite_fe}</p></td>
              <td className="py-1.5"><input className="w-24 h-7 rounded border px-1 num" defaultValue={e.quantite || ""} key={`${e.id}${e.quantite}`} onBlur={(ev) => numOrNull(ev.target.value) !== e.quantite && put({ emissions: { [e.id]: numOrNull(ev.target.value) || 0 } })} /> <span className="text-muted-foreground">{e.unite}</span></td>
              <td className="py-1.5 text-right num">{n(e.total)} kg</td></tr>))}</tbody></table>
          <p className="text-xs font-semibold text-right mt-2">Total : {n(t.chantier / 1000, 2)} tCO2e</p>
        </Card>
        <Card title="Compromissos da carta" icon={CheckCircle2} testId="bc-charte">
          <ul className="space-y-2">{r.charte.map((c) => (
            <li key={c.id} className="rounded-lg border p-2 text-xs">
              <div className="flex items-start justify-between gap-2"><p className="font-medium">{c.kpi}</p><Badge className={`rounded-sm text-[10px] shrink-0 ${STATUT[c.statut]}`} variant="outline">{c.statut}</Badge></div>
              <div className="flex items-center gap-2 mt-1 flex-wrap text-muted-foreground">
                <span>Objetivo {c.op === ">=" ? "≥" : "≤"} {c.cible} {c.unite}</span>
                <span>· Realizado</span><input className="w-16 h-6 rounded border px-1 num text-foreground" defaultValue={dossier.charte.find((x) => x.id === c.id)?.realise ?? ""} placeholder={c.realise ?? ""} key={`${c.id}${c.realise}`} onBlur={(e) => put({ charte: { [c.id]: { realise: numOrNull(e.target.value) } } })} />
                {c.source_realise === "calculado ConstruPilot" && <span className="text-primary">calculado</span>}
                <select className="h-6 rounded border px-1 bg-background ms-auto" value={c.statut_force || ""} onChange={(e) => put({ charte: { [c.id]: { statut_force: e.target.value || null } } })}><option value="">Estado automático</option>{ref.statuts.map((s) => <option key={s}>{s}</option>)}</select>
              </div>
              <p className="text-[10px] mt-1">Prova : {c.preuve} · {c.pieces?.length || 0} documento(s)</p>
            </li>))}</ul>
        </Card>
      </div>

      <Card title={`Documentos justificativos (${dossier.documents.length})`} icon={FileText} testId="bc-pieces">
        {dossier.documents.length === 0 ? <p className="text-sm text-muted-foreground">Nenhum documento depositado.</p> : (
          <ul className="space-y-1.5">{dossier.documents.map((d) => (
            <li key={d.doc_id} className="flex items-center gap-2 flex-wrap rounded-lg border px-3 py-2 text-xs">
              <span className="font-medium">{d.nom}</span><Badge variant="outline" className="rounded-sm text-[10px]">{d.type_libelle || d.type}</Badge>
              {d.statut !== "lido" && <Badge variant="outline" className="rounded-sm text-[10px] bg-red-50 text-red-700">{d.statut}</Badge>}
              <select className="h-7 rounded border px-1 bg-background ms-auto max-w-[240px]" value={d.rattache_a && mats.some((m) => m.id === d.rattache_a) ? d.rattache_a : ""} onChange={(e) => e.target.value && run("att", () => api.post(`${base}/documents/${d.doc_id}/rattacher`, { ligne_id: e.target.value }))} disabled={["bsd", "carburant"].includes(d.type)}>
                <option value="">{d.rattache_a ? (["dechets", "gnr", "hvo"].includes(d.rattache_a) ? "Resíduos / combustíveis" : "Associado") : "Não associado — escolher a linha"}</option>
                {mats.filter((m) => m.id).map((m) => <option key={m.id} value={m.id}>{m.famille}</option>)}</select>
              <button type="button" title="Retirar o documento (os seus contributos são anulados)" onClick={() => window.confirm(`Retirar « ${d.nom} » ? Os seus contributos ao quadro serão anulados.`) && run("del", () => api.delete(`${base}/documents/${d.doc_id}`))}><Trash2 className="h-3.5 w-3.5 text-muted-foreground hover:text-red-600" /></button>
              {d.notes?.length > 0 && <p className="basis-full text-[10px] text-amber-700">⚠ {d.notes.join(" ; ")}</p>}
            </li>))}</ul>)}
      </Card>
      {busy && busy !== "upload" && <div className="fixed bottom-4 right-4 surface px-3 py-2 text-xs flex items-center gap-2 shadow-lg"><Loader2 className="h-3.5 w-3.5 animate-spin" /> A atualizar…</div>}
    </div>
  );
}
