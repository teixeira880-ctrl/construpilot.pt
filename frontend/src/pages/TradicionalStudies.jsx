import React, { useEffect, useState, useCallback, useMemo } from "react";
import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { toast } from "sonner";
import { Link } from "react-router-dom";
import {
  Boxes, Trash2, ArrowLeft, Loader2, FileDown, AlertTriangle, Info, FileSpreadsheet, Box, Coins, Globe, Save, Sparkles, Ruler, Camera,
} from "lucide-react";

// Construção tradicional (betão armado + alvenarias): motor determinístico engines/tradicional — a geometria vem da planta lida no ConstruPilot.
const DISCLAIMER = "Pré-dimensionamento e quantidades gerados automaticamente a partir da geometria da planta — a verificar e assinar por um engenheiro de estruturas antes da execução.";
const fmt = (x, d = 0) => (x == null ? "—" : Number(x).toLocaleString("pt-PT", { minimumFractionDigits: d, maximumFractionDigits: d }));
const ORIGEM = { biblioteca: "Biblioteca", projeto: "Projeto", mercado: "Mercado — a analisar" };

function filenameFromResponse(res, fallback) {
  const cd = res?.headers?.["content-disposition"] || "";
  const m = /filename\*=UTF-8''([^;]+)|filename="?([^";]+)"?/i.exec(cd);
  try { return m ? decodeURIComponent(m[1] || m[2]) : fallback; } catch { return fallback; }
}
async function download(url, fallback) {
  const res = await api.get(url, { responseType: "blob" });
  const href = URL.createObjectURL(res.data);
  const a = document.createElement("a");
  a.href = href; a.download = filenameFromResponse(res, fallback); a.click();
  setTimeout(() => URL.revokeObjectURL(href), 5000);
}

function Banner() {
  return (
    <div className="rounded-md border border-amber-300 bg-amber-50 p-3 text-[13px] text-amber-900 flex gap-2" data-testid="trad-disclaimer">
      <AlertTriangle className="h-4 w-4 shrink-0 mt-0.5" /><b>{DISCLAIMER}</b>
    </div>
  );
}

export default function TradicionalStudies() {
  const [studies, setStudies] = useState([]);
  const [active, setActive] = useState(null);
  const loadList = useCallback(async () => {
    try { const { data } = await api.get("/tradicional/estudo/studies"); setStudies(data.studies || []); } catch { /* ignore */ }
  }, []);
  useEffect(() => { loadList(); }, [loadList]);
  const open = async (id) => {
    try { const { data } = await api.get(`/tradicional/estudo/studies/${id}`); setActive(data); } catch { toast.error("Não foi possível abrir o estudo"); }
  };
  const remove = async (id) => {
    try { await api.delete(`/tradicional/estudo/studies/${id}`); if (active?.study_id === id) setActive(null); await loadList(); }
    catch { toast.error("Não foi possível apagar"); }
  };
  if (active) return <StudyDetail study={active} setStudy={setActive} onBack={() => { setActive(null); loadList(); }} />;
  return (
    <div className="max-w-5xl mx-auto px-4 py-8 space-y-6" data-testid="trad-page">
      <header className="space-y-2">
        <Link to="/construcao-tradicional" className="inline-flex items-center gap-1 text-xs text-muted-foreground hover:underline"><ArrowLeft className="h-3 w-3" />Construção tradicional — alvenaria unidade a unidade</Link>
        <div className="flex items-center gap-2">
          <Boxes className="h-6 w-6 text-primary" />
          <h1 className="text-3xl font-bold tracking-tight">Construção tradicional (betão armado + alvenarias)</h1>
          <Badge variant="outline" className="ml-1">Pro</Badge>
        </div>
        <p className="text-sm text-muted-foreground max-w-3xl">
          A partir da planta já lida, o motor dimensiona sapatas, vigas de fundação, pilares, vigas, lajes e cobertura elemento a elemento
          (cargas descidas piso a piso), mede betão, cofragem e aço pelos varões calculados, conta as alvenarias fiada a fiada parede a parede e dá o
          mapa de quantidades por piso, das fundações à cobertura; preços da biblioteca da empresa; dossier PDF com plantas e alçados numerados,
          Excel, visualizador 3D e render fotorrealista.
        </p>
      </header>
      <Banner />
      <NewStudy onCreated={async (id) => { await loadList(); await open(id); }} />
      <section className="space-y-2">
        <h2 className="text-sm font-semibold text-muted-foreground">Os meus estudos ({studies.length})</h2>
        {studies.length === 0 && <p className="text-sm text-muted-foreground">Ainda não há estudos.</p>}
        <div className="grid gap-2">
          {studies.map((s) => (
            <Card key={s.study_id} className="p-3 flex items-center justify-between" data-testid={`trad-study-${s.study_id}`}>
              <button className="text-left flex-1" onClick={() => open(s.study_id)}>
                <div className="font-medium">{s.title}</div>
                <div className="text-xs text-muted-foreground">
                  {fmt(s.summary?.m3_betao, 1)} m³ betão · {fmt(s.summary?.kg_aco)} kg aço · {fmt(s.summary?.unidades_alvenaria)} unidades de alvenaria
                  {s.summary?.avisos ? ` · ${s.summary.avisos} a verificar` : ""}
                </div>
              </button>
              <Button size="icon" variant="ghost" onClick={() => remove(s.study_id)} aria-label="Apagar"><Trash2 className="h-4 w-4 text-muted-foreground" /></Button>
            </Card>
          ))}
        </div>
      </section>
    </div>
  );
}

function NewStudy({ onCreated }) {
  const [plans, setPlans] = useState([]);
  const [loading, setLoading] = useState(true);
  const [planId, setPlanId] = useState("");
  const [levels, setLevels] = useState([]);
  const [opts, setOpts] = useState({ cobertura: "auto", inclinacao: 30, beiral: 500 });
  const [qadm, setQadm] = useState("");
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    api.get("/takeoffs").then(({ data }) => setPlans(data.plans || [])).catch(() => {}).finally(() => setLoading(false));
  }, []);
  const selectPlan = (id) => {
    setPlanId(id);
    const p = plans.find((x) => x.plan_id === id);
    const n = Math.max(1, (p?.pages?.length) || (p?.page_count) || 1);
    const names = ["R/C", "1.º andar", "2.º andar", "3.º andar"];
    setLevels(Array.from({ length: n }, (_, i) => ({ page_index: i, name: names[i] || `Piso ${i}`, elevation_m: 2.8 * i, height_m: 2.7 })));
  };
  const patch = (i, p) => setLevels((ls) => ls.map((l, k) => (k === i ? { ...l, ...p } : l)));
  const create = async () => {
    if (!planId) { toast.error("Escolha uma planta já lida e calibrada"); return; }
    setBusy(true);
    try {
      const { data } = await api.post("/tradicional/estudo/studies", {
        plan_id: planId, country: "pt", q_adm_kpa: qadm ? Number(qadm) : null, options: { ...opts, inclinacao: Number(opts.inclinacao), beiral: Number(opts.beiral) },
        levels: levels.map((l) => ({ page_index: Number(l.page_index), name: l.name, elevation_m: Number(l.elevation_m), height_m: Number(l.height_m) })),
      });
      toast.success("Estudo calculado");
      onCreated(data.study_id);
    } catch (e) { toast.error(e?.response?.data?.detail || "Não foi possível calcular"); } finally { setBusy(false); }
  };
  const exemplo = async () => {
    setBusy(true);
    try {
      const { data: ex } = await api.get("/tradicional/estudo/exemplo");
      const { data } = await api.post("/tradicional/estudo/studies/from-input", { input: ex, title: "Moradia exemplo — construção tradicional" });
      onCreated(data.study_id);
    } catch (e) { toast.error(e?.response?.data?.detail || "Não foi possível calcular"); } finally { setBusy(false); }
  };
  return (
    <Card className="p-5 space-y-4" data-testid="trad-new-card">
      <h2 className="text-sm font-semibold">Novo estudo a partir de uma planta</h2>
      <label className="text-xs space-y-1 block">
        <span className="font-semibold text-muted-foreground">Planta (já lida &amp; calibrada)</span>
        <select className="h-9 w-full border rounded-md px-2 text-sm bg-background" value={planId} onChange={(e) => selectPlan(e.target.value)}
          disabled={loading} data-testid="trad-plan-select">
          <option value="">{loading ? "A carregar as plantas…" : "— Escolher uma planta —"}</option>
          {plans.map((p) => <option key={p.plan_id} value={p.plan_id}>{p.filename || p.plan_id}</option>)}
        </select>
      </label>
      {levels.length > 0 && (
        <div className="space-y-2">
          <div className="text-xs font-semibold text-muted-foreground">Pisos (uma página = um piso)</div>
          {levels.map((l, i) => (
            <div key={i} className="grid grid-cols-4 gap-2 text-xs">
              <input className="h-8 border rounded px-2" value={l.name} onChange={(e) => patch(i, { name: e.target.value })} aria-label="Nome do piso" />
              <label className="flex items-center gap-1">Cota <input type="number" step="0.05" className="h-8 w-full border rounded px-2" value={l.elevation_m}
                onChange={(e) => patch(i, { elevation_m: e.target.value })} /> m</label>
              <label className="flex items-center gap-1">Pé-direito <input type="number" step="0.05" className="h-8 w-full border rounded px-2" value={l.height_m}
                onChange={(e) => patch(i, { height_m: e.target.value })} /> m</label>
              <span className="text-muted-foreground self-center">página {Number(l.page_index) + 1}</span>
            </div>
          ))}
        </div>
      )}
      <div className="grid grid-cols-3 gap-3 text-xs">
        <label className="space-y-1"><span className="font-semibold text-muted-foreground">Cobertura</span>
          <select className="h-9 w-full border rounded-md px-2 bg-background" value={opts.cobertura} onChange={(e) => setOpts({ ...opts, cobertura: e.target.value })}>
            <option value="auto">Automática</option><option value="duas_aguas">Duas águas (lajes inclinadas + empenas)</option><option value="plana">Plana</option>
          </select></label>
        <label className="space-y-1"><span className="font-semibold text-muted-foreground">Inclinação (°)</span>
          <input type="number" className="h-9 w-full border rounded-md px-2" value={opts.inclinacao} onChange={(e) => setOpts({ ...opts, inclinacao: e.target.value })} /></label>
        <label className="space-y-1"><span className="font-semibold text-muted-foreground">Beiral (mm)</span>
          <input type="number" className="h-9 w-full border rounded-md px-2" value={opts.beiral} onChange={(e) => setOpts({ ...opts, beiral: e.target.value })} /></label>
      </div>
      <label className="text-xs space-y-1 block max-w-xs"><span className="font-semibold text-muted-foreground">Tensão admissível do terreno (kPa, estudo geotécnico)</span>
        <input type="number" className="h-9 w-full border rounded-md px-2" placeholder="200 (hipótese se vazio)" value={qadm} onChange={(e) => setQadm(e.target.value)} data-testid="trad-qadm" /></label>
      <div className="flex flex-wrap gap-2">
        <Button onClick={create} disabled={busy} data-testid="trad-create">{busy ? <Loader2 className="h-4 w-4 animate-spin mr-1" /> : <Ruler className="h-4 w-4 mr-1" />}Calcular a construção tradicional</Button>
        <Button variant="outline" onClick={exemplo} disabled={busy} data-testid="trad-example"><Sparkles className="h-4 w-4 mr-1" />Experimentar com a moradia exemplo</Button>
      </div>
    </Card>
  );
}

function Kpi({ label, value, unit }) {
  return (
    <div className="rounded-lg border bg-card p-3">
      <div className="text-xs text-muted-foreground">{label}</div>
      <div className="text-xl font-bold tabular-nums">{value}{unit && <span className="text-xs font-normal text-muted-foreground ml-1">{unit}</span>}</div>
    </div>
  );
}

function StudyDetail({ study, setStudy, onBack }) {
  const [busy, setBusy] = useState("");
  const [viewer, setViewer] = useState(null);
  const [json, setJson] = useState(() => JSON.stringify(study.project, null, 2));
  const s = study.summary || {};
  const cats = useMemo(() => {
    const out = {};
    for (const l of study.lines || []) (out[l.cat] = out[l.cat] || []).push(l);
    return out;
  }, [study.lines]);
  const run = async (key, fn) => { setBusy(key); try { await fn(); } catch (e) { toast.error(e?.response?.data?.detail || "Operação falhou"); } finally { setBusy(""); } };
  const openViewer = () => run("viewer", async () => {
    const { data } = await api.get(`/tradicional/estudo/studies/${study.study_id}/viewer`, { responseType: "text" });
    setViewer(data);
  });
  const [foto, setFoto] = useState(null);
  const photo = () => run("foto", async () => {
    const res = await api.post(`/tradicional/estudo/studies/${study.study_id}/photo`, {}, { responseType: "blob" });
    setFoto(URL.createObjectURL(res.data));
    toast.success("Render fotorrealista pronto — também incluído no dossier PDF");
  });
  const price = (mercado) => run(mercado ? "mercado" : "preco", async () => {
    const { data } = await api.post(`/tradicional/estudo/studies/${study.study_id}/price`, { mercado });
    setStudy({ ...study, lines: data.lines, totals: data.totals });
    toast.success(mercado ? "Preços de mercado procurados — linhas assinaladas a analisar" : "Preços da biblioteca aplicados");
  });
  const save = () => run("save", async () => {
    let project;
    try { project = JSON.parse(json); } catch { toast.error("JSON inválido"); return; }
    const { data } = await api.put(`/tradicional/estudo/studies/${study.study_id}/project`, { project });
    setStudy(data); toast.success("Projeto recalculado");
  });
  const t = study.totals || {};
  return (
    <div className="max-w-6xl mx-auto px-4 py-6 space-y-5" data-testid="trad-detail">
      <button className="text-sm text-muted-foreground flex items-center gap-1" onClick={onBack}><ArrowLeft className="h-4 w-4" />Estudos</button>
      <h1 className="text-2xl font-bold">{study.title}</h1>
      <Banner />
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
        <Kpi label="Betão armado" value={fmt(s.m3_betao, 2)} unit="m³" />
        <Kpi label="Aço A500" value={fmt(s.kg_aco)} unit="kg" />
        <Kpi label="Alvenaria" value={fmt(s.unidades_alvenaria)} unit={`unidades · ${fmt(s.m2_alvenaria, 1)} m²`} />
        <Kpi label={t.total ? "Total com preço" : "Pilares / vigas / sapatas"} value={t.total ? fmt(t.total, 2) : `${s.pilares} / ${s.vigas} / ${s.sapatas}`} unit={t.total ? "€" : ""} />
      </div>
      <div className="flex flex-wrap gap-2">
        <Button onClick={() => run("pdf", () => download(`/tradicional/estudo/studies/${study.study_id}/pdf`, "Construcao-tradicional.pdf"))} disabled={!!busy} data-testid="trad-pdf">
          {busy === "pdf" ? <Loader2 className="h-4 w-4 animate-spin mr-1" /> : <FileDown className="h-4 w-4 mr-1" />}Dossier PDF</Button>
        <Button variant="outline" onClick={() => run("xlsx", () => download(`/tradicional/estudo/studies/${study.study_id}/xlsx`, "Mapa-tradicional.xlsx"))} disabled={!!busy}>
          {busy === "xlsx" ? <Loader2 className="h-4 w-4 animate-spin mr-1" /> : <FileSpreadsheet className="h-4 w-4 mr-1" />}Excel</Button>
        <Button variant="outline" onClick={openViewer} disabled={!!busy} data-testid="trad-3d">
          {busy === "viewer" ? <Loader2 className="h-4 w-4 animate-spin mr-1" /> : <Box className="h-4 w-4 mr-1" />}Visualizador 3D</Button>
        <Button variant="outline" onClick={photo} disabled={!!busy} data-testid="trad-photo">
          {busy === "foto" ? <Loader2 className="h-4 w-4 animate-spin mr-1" /> : <Camera className="h-4 w-4 mr-1" />}Render fotorrealista</Button>
        <Button variant="outline" onClick={() => price(false)} disabled={!!busy}><Coins className="h-4 w-4 mr-1" />Preços da biblioteca</Button>
        <Button variant="outline" onClick={() => price(true)} disabled={!!busy}><Globe className="h-4 w-4 mr-1" />Procurar preços de mercado</Button>
      </div>
      {foto && <img src={foto} alt="Render fotorrealista da estrutura" className="w-full rounded-lg border" />}
      {viewer && (
        <div className="rounded-lg border overflow-hidden" style={{ height: "70vh" }}>
          <iframe title="Visualizador 3D" srcDoc={viewer} sandbox="allow-scripts" className="w-full h-full border-0" />
        </div>
      )}
      {(study.warnings || []).length > 0 && (
        <Card className="p-4 space-y-1">
          <h2 className="text-sm font-semibold flex items-center gap-1 text-amber-700"><AlertTriangle className="h-4 w-4" />A verificar ({study.warnings.length})</h2>
          {study.warnings.map((w, i) => <p key={i} className="text-xs text-amber-800">• {w}</p>)}
        </Card>
      )}
      <Card className="p-4 space-y-1">
        <h2 className="text-sm font-semibold flex items-center gap-1"><Info className="h-4 w-4" />Hipóteses (a validar)</h2>
        {(study.assumptions || []).map((h, i) => <p key={i} className="text-xs text-muted-foreground">• {h}</p>)}
        {study.reading?.pisos && <p className="text-xs pt-1">Leitura da planta: {study.reading.pisos.map((p) => `${p.nivel}: ${p.divisoes} divisões, ${p.paredes_interiores} paredes interiores, ${p.vaos_exteriores + p.vaos_interiores} vãos`).join(" · ")}</p>}
      </Card>
      <section className="space-y-3">
        <h2 className="text-lg font-semibold">Mapa de quantidades</h2>
        {t.linhas_sem_preco > 0 && <p className="text-xs text-muted-foreground">{t.linhas_sem_preco} de {t.linhas} linhas sem preço na biblioteca da empresa: ficam « a orçamentar » (nenhum preço é inventado).</p>}
        {Object.entries(cats).map(([cat, lines]) => (
          <Card key={cat} className="p-0 overflow-x-auto">
            <div className="px-4 py-2 text-sm font-semibold border-b">{cat.replace(/^\d+\s/, "")}</div>
            <table className="w-full text-xs">
              <thead><tr className="text-left text-muted-foreground"><th className="px-4 py-1.5">Designação</th><th>Un.</th><th className="text-right">Quantidade</th><th className="text-right">P. unit.</th><th className="text-right pr-4">Total</th></tr></thead>
              <tbody>
                {lines.map((l) => (
                  <tr key={l.code} className="border-t align-top">
                    <td className="px-4 py-1.5"><div className="font-medium">{l.designacao}</div><div className="text-muted-foreground">{l.detalhe}</div></td>
                    <td>{l.un}</td>
                    <td className="text-right tabular-nums">{fmt(l.qtd, l.un === "un" ? 0 : 2)}</td>
                    <td className="text-right tabular-nums">{l.preco ? <>{fmt(l.preco.unit, 2)} <span className={l.preco.origem === "mercado" ? "text-amber-700" : "text-muted-foreground"}>{ORIGEM[l.preco.origem]}</span></> : <span className="text-muted-foreground">a orçamentar</span>}</td>
                    <td className="text-right tabular-nums pr-4">{l.total != null ? fmt(l.total, 2) : "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </Card>
        ))}
      </section>
      <details className="rounded-lg border p-4">
        <summary className="text-sm font-semibold cursor-pointer">Projeto (unidades de alvenaria, vãos, cargas, terreno, preços) — editar e recalcular</summary>
        <textarea className="mt-3 w-full h-96 font-mono text-xs border rounded p-2" value={json} onChange={(e) => setJson(e.target.value)} spellCheck={false} />
        <Button className="mt-2" onClick={save} disabled={!!busy}>{busy === "save" ? <Loader2 className="h-4 w-4 animate-spin mr-1" /> : <Save className="h-4 w-4 mr-1" />}Recalcular</Button>
      </details>
    </div>
  );
}
