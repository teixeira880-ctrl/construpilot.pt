import React, { useEffect, useState, useCallback } from "react";
import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { toast } from "sonner";
import {
  Zap, Droplets, Network, Plus, Trash2, ArrowLeft, Loader2, FileDown, AlertTriangle,
  CheckCircle2, ShieldAlert, Info, Calculator, Gauge, ListChecks, Table2, MapPin, FlaskConical,
} from "lucide-react";
// Nome do ficheiro devolvido pelo servidor (Content-Disposition), com recurso a um nome local.
function filenameFromResponse(res, fallback) {
  const cd = res?.headers?.["content-disposition"] || "";
  const m = /filename\*=UTF-8''([^;]+)|filename="?([^";]+)"?/i.exec(cd);
  try { return m ? decodeURIComponent(m[1] || m[2]) : fallback; } catch { return fallback; }
}
function nomDocument(tipo, titulo) {
  const slug = (titulo || "").normalize("NFD").replace(/[\u0300-\u036f]/g, "").replace(/[^A-Za-z0-9]+/g, "-").replace(/^-|-$/g, "").slice(0, 60);
  return `ConstruPilot_${tipo}${slug ? "_" + slug : ""}_${new Date().toISOString().slice(0, 10)}.pdf`;
}

const DISCLAIMER = "Pré-estudo gerado automaticamente, a verificar e validar por um técnico qualificado antes da execução.";
const CONSUEL = "Lembrete: a instalação elétrica exige projeto com termo de responsabilidade e certificação (DGEG / entidade inspetora) antes da ligação à rede.";

// Defesa em profundidade: o SVG vem do nosso backend e o texto já está escapado,
// mas retira-se por precaução qualquer script / handler de evento / URL javascript.
function sanitizeSvg(svg) {
  if (typeof svg !== "string") return "";
  return svg
    .replace(/<script[\s\S]*?<\/script>/gi, "")
    .replace(/\son\w+\s*=\s*"[^"]*"/gi, "")
    .replace(/\son\w+\s*=\s*'[^']*'/gi, "")
    .replace(/javascript:/gi, "");
}

const POINT_KINDS = [
  "prise", "prise_plan_travail", "prise_specialisee", "point_lumineux", "interrupteur",
  "rj45", "tv", "tableau", "daaf", "applique", "chauffage", "vmc",
];
const POINT_LABEL = {
  prise: "Tomada 16 A", prise_plan_travail: "Tomada de bancada", prise_specialisee: "Tomada dedicada",
  point_lumineux: "Ponto de luz", interrupteur: "Interruptor", rj45: "RJ45", tv: "TV",
  tableau: "Quadro elétrico", daaf: "Detetor de fumo", applique: "Aplique", chauffage: "Aquecimento", vmc: "Ventilação",
};
const WATER_HEATERS = [
  { v: "ballon_electrique", l: "Termoacumulador elétrico" },
  { v: "thermodynamique", l: "Bomba de calor para AQS" },
  { v: "chaudiere", l: "Caldeira" },
  { v: "pac", l: "Bomba de calor" },
  { v: "aucun", l: "Nenhum" },
];

const CHECK_STYLE = {
  error: { cls: "bg-red-500/15 text-red-700 border-red-300", Icon: ShieldAlert, label: "Erro" },
  warning: { cls: "bg-amber-500/15 text-amber-700 border-amber-300", Icon: AlertTriangle, label: "A verificar" },
  info: { cls: "bg-sky-500/15 text-sky-700 border-sky-300", Icon: Info, label: "Info" },
  ok: { cls: "bg-emerald-500/15 text-emerald-700 border-emerald-300", Icon: CheckCircle2, label: "OK" },
};

function Banner() {
  return (
    <div className="rounded-md border border-amber-300 bg-amber-50 p-3 text-[13px] text-amber-900 flex gap-2"
      data-testid="mep-disclaimer">
      <AlertTriangle className="h-4 w-4 shrink-0 mt-0.5" />
      <span><b>{DISCLAIMER}</b><br /><span className="text-amber-800">{CONSUEL}</span></span>
    </div>
  );
}

export default function PlansExecution() {
  const [studies, setStudies] = useState([]);
  const [active, setActive] = useState(null);

  const loadList = useCallback(async () => {
    try { const { data } = await api.get("/mep/studies"); setStudies(data.studies || []); }
    catch { /* ignore */ }
  }, []);
  useEffect(() => { loadList(); }, [loadList]);

  const open = async (id) => {
    try { const { data } = await api.get(`/mep/studies/${id}`); setActive(data); }
    catch { toast.error("Não foi possível abrir"); }
  };
  const remove = async (id) => {
    try { await api.delete(`/mep/studies/${id}`); if (active?.study_id === id) setActive(null); await loadList(); }
    catch { toast.error("Não foi possível apagar"); }
  };

  if (active) return <StudyDetail study={active} setStudy={setActive} onBack={() => { setActive(null); loadList(); }} />;

  return (
    <div className="max-w-5xl mx-auto px-4 py-8 space-y-6" data-testid="mep-page">
      <header className="space-y-2">
        <div className="flex items-center gap-2">
          <Zap className="h-6 w-6 text-[#F97316]" />
          <h1 className="text-3xl font-bold tracking-tight" style={{ color: "#0F172A" }}>Planos de execução — Eletricidade &amp; Canalização</h1>
          <Badge variant="outline" className="ml-1">Pro</Badge>
        </div>
        <p className="text-sm text-muted-foreground max-w-2xl">
          A partir de uma planta já lida e calibrada, o motor determinístico implanta os pontos (RTIEBT),
          dimensiona as redes de água e esgotos (DR 23/95), verifica a conformidade e prepara as quantidades.
          Pode alterar a implantação antes de exportar.
        </p>
      </header>

      <Banner />
      <NewStudy onCreated={async (id) => { await loadList(); await open(id); }} />

      <section className="space-y-2">
        <h2 className="text-sm font-semibold text-muted-foreground">Os meus estudos ({studies.length})</h2>
        {studies.length === 0 && <p className="text-sm text-muted-foreground">Ainda não há estudos.</p>}
        <div className="grid gap-2">
          {studies.map((s) => (
            <Card key={s.study_id} className="p-3 flex items-center justify-between hover:border-slate-400 transition-colors"
              data-testid={`mep-study-${s.study_id}`}>
              <button className="text-left flex-1" onClick={() => open(s.study_id)} data-testid={`mep-open-${s.study_id}`}>
                <div className="font-medium">{s.title}</div>
                <div className="text-xs text-muted-foreground">
                  {(s.country || "pt").toUpperCase()} · {s.summary?.points ?? 0} points · {s.summary?.circuits ?? 0} circuits
                  {s.summary?.status && <StatusDot status={s.summary.status} />}
                </div>
              </button>
              <Button size="icon" variant="ghost" onClick={() => remove(s.study_id)} data-testid={`mep-delete-${s.study_id}`}>
                <Trash2 className="h-4 w-4 text-muted-foreground" />
              </Button>
            </Card>
          ))}
        </div>
      </section>
    </div>
  );
}

function StatusDot({ status }) {
  const c = status === "error" ? "bg-red-500" : status === "warning" ? "bg-amber-500" : "bg-emerald-500";
  return <span className={`inline-block h-2 w-2 rounded-full ml-2 ${c}`} />;
}

function NewStudy({ onCreated }) {
  const [plans, setPlans] = useState([]);
  const [loadingPlans, setLoadingPlans] = useState(true);
  const [planId, setPlanId] = useState("");
  const [country, setCountry] = useState("pt");
  const [levels, setLevels] = useState([]);
  const [opts, setOpts] = useState({
    water_heater: "ballon_electrique", dishwasher: true, oven: true, dryer: false, vmc: null, ev_charger: false,
  });
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    setLoadingPlans(true);
    api.get("/takeoffs").then(({ data }) => setPlans(data.plans || [])).catch(() => {}).finally(() => setLoadingPlans(false));
  }, []);

  const selectPlan = (id) => {
    setPlanId(id);
    const p = plans.find((x) => x.plan_id === id);
    const pageCount = Math.max(1, (p?.pages?.length) || (p?.page_count) || 1);
    const names = ["Rés-do-chão", "Piso 1", "Piso 2", "Piso 3"];
    setLevels(Array.from({ length: pageCount }, (_, i) => ({
      page_index: i, name: names[i] || `Piso ${i}`, elevation_m: 2.8 * i, height_m: 2.5,
    })));
  };

  const patchLevel = (i, patch) => setLevels((ls) => ls.map((l, k) => (k === i ? { ...l, ...patch } : l)));

  const create = async () => {
    if (!planId) { toast.error("Escolha uma planta já lida e calibrada"); return; }
    setBusy(true);
    try {
      const { data } = await api.post("/mep/studies", {
        plan_id: planId, country,
        levels: levels.map((l) => ({
          page_index: Number(l.page_index), name: l.name,
          elevation_m: Number(l.elevation_m), height_m: Number(l.height_m),
        })),
        options: opts,
      });
      toast.success("Planos de execução gerados");
      onCreated(data.study_id);
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Não foi possível gerar");
    } finally { setBusy(false); }
  };

  return (
    <Card className="p-5 space-y-4" data-testid="mep-new-card">
      <h2 className="text-sm font-semibold">Novo estudo a partir de uma planta</h2>

      <div className="grid gap-3 sm:grid-cols-2">
        <label className="text-xs space-y-1">
          <span className="font-semibold text-muted-foreground">Planta (já lida &amp; calibrada)</span>
          <select className="h-9 w-full border rounded-md px-2 text-sm bg-background" value={planId}
            onChange={(e) => selectPlan(e.target.value)} disabled={loadingPlans} data-testid="mep-plan-select">
            <option value="">{loadingPlans ? "A carregar as plantas…" : "— Escolher uma planta —"}</option>
            {plans.map((p) => <option key={p.plan_id} value={p.plan_id}>{p.filename || p.plan_id}</option>)}
          </select>
        </label>
        <label className="text-xs space-y-1">
          <span className="font-semibold text-muted-foreground">País / regulamentação</span>
          <select className="h-9 w-full border rounded-md px-2 text-sm bg-background" value={country}
            onChange={(e) => setCountry(e.target.value)} data-testid="mep-country-select">
            <option value="pt">Portugal — RTIEBT / DR 23/95</option>
            <option value="fr">França — NF C 15-100 / DTU 60.11</option>
          </select>
        </label>
      </div>

      {levels.length > 0 && (
        <div className="space-y-2" data-testid="mep-levels">
          <div className="text-xs font-semibold text-muted-foreground">Pisos (página → piso)</div>
          {levels.map((l, i) => (
            <div key={i} className="flex flex-wrap items-center gap-2" data-testid={`mep-level-${i}`}>
              <Badge variant="outline" className="text-[10px]">página {l.page_index + 1}</Badge>
              <Input className="h-8 w-40 text-xs" value={l.name} onChange={(e) => patchLevel(i, { name: e.target.value })}
                placeholder="Nome do piso" data-testid={`mep-level-name-${i}`} />
              <div className="flex items-center gap-1">
                <Input className="h-8 w-24 text-xs" type="number" step="0.1" value={l.elevation_m}
                  onChange={(e) => patchLevel(i, { elevation_m: e.target.value })} data-testid={`mep-level-elev-${i}`} />
                <span className="text-[11px] text-muted-foreground">m cota</span>
              </div>
              <div className="flex items-center gap-1">
                <Input className="h-8 w-20 text-xs" type="number" step="0.1" value={l.height_m}
                  onChange={(e) => patchLevel(i, { height_m: e.target.value })} data-testid={`mep-level-h-${i}`} />
                <span className="text-[11px] text-muted-foreground">m pé-direito</span>
              </div>
            </div>
          ))}
        </div>
      )}

      <div className="space-y-2">
        <div className="text-xs font-semibold text-muted-foreground">Opções da instalação</div>
        <div className="flex flex-wrap items-center gap-3 text-xs">
          <label className="flex items-center gap-1">
            Produção de AQS
            <select className="h-8 border rounded-md px-2 bg-background" value={opts.water_heater}
              onChange={(e) => setOpts({ ...opts, water_heater: e.target.value })} data-testid="mep-opt-ecs">
              {WATER_HEATERS.map((w) => <option key={w.v} value={w.v}>{w.l}</option>)}
            </select>
          </label>
          <Toggle label="Máquina de lavar loiça" checked={opts.dishwasher} onChange={(v) => setOpts({ ...opts, dishwasher: v })} tid="mep-opt-dishwasher" />
          <Toggle label="Forno" checked={opts.oven} onChange={(v) => setOpts({ ...opts, oven: v })} tid="mep-opt-oven" />
          <Toggle label="Máquina de secar" checked={opts.dryer} onChange={(v) => setOpts({ ...opts, dryer: v })} tid="mep-opt-dryer" />
          <Toggle label="Ventilação mecânica" checked={opts.vmc ?? (country === "fr")} onChange={(v) => setOpts({ ...opts, vmc: v })} tid="mep-opt-vmc" />
          <Toggle label="Carregamento de veículo elétrico" checked={opts.ev_charger} onChange={(v) => setOpts({ ...opts, ev_charger: v })} tid="mep-opt-irve" />
        </div>
      </div>

      <Button onClick={create} disabled={busy || !planId} className="gap-1 bg-[#F97316] hover:bg-[#ea6a0c]" data-testid="mep-generate-btn">
        {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Zap className="h-4 w-4" />} Gerar os planos de execução
      </Button>
    </Card>
  );
}

function Toggle({ label, checked, onChange, tid }) {
  return (
    <label className="flex items-center gap-1 cursor-pointer select-none">
      <input type="checkbox" checked={!!checked} onChange={(e) => onChange(e.target.checked)} data-testid={tid} />
      {label}
    </label>
  );
}

function StudyDetail({ study, setStudy, onBack }) {
  const s = study;
  const [tab, setTab] = useState("plan");
  const [layer, setLayer] = useState("elec");
  const [levelId, setLevelId] = useState(s.levels?.[0]?.id || "");
  const [svg, setSvg] = useState("");
  const [loadingSvg, setLoadingSvg] = useState(false);
  const [points, setPoints] = useState(s.points || []);
  const [pricing, setPricing] = useState(s.pricing || null);
  const [busy, setBusy] = useState(false);

  useEffect(() => { setPoints(s.points || []); setPricing(s.pricing || null); }, [s]);

  const loadSvg = useCallback(async () => {
    setLoadingSvg(true);
    try {
      const params = layer === "unifilar" ? { layer } : { layer, level: levelId };
      const { data } = await api.get(`/mep/studies/${s.study_id}/svg`, { params, responseType: "text" });
      setSvg(typeof data === "string" ? sanitizeSvg(data) : "");
    } catch { setSvg(""); toast.error("Pré-visualização indisponível"); }
    finally { setLoadingSvg(false); }
  }, [s.study_id, layer, levelId]);
  useEffect(() => { if (tab === "plan") loadSvg(); }, [tab, loadSvg]);

  const saveLayout = async (nextPoints) => {
    setBusy(true);
    try {
      const { data } = await api.put(`/mep/studies/${s.study_id}/layout`, { points: nextPoints });
      setStudy(data); setStudy((d) => ({ ...data }));
      toast.success("Implantação recalculada e reverificada");
    } catch (e) { toast.error(e?.response?.data?.detail || "Não foi possível recalcular"); }
    finally { setBusy(false); }
  };

  const priceWithLibrary = async () => {
    setBusy(true);
    try {
      const { data } = await api.post(`/mep/studies/${s.study_id}/price`);
      setPricing(data.pricing);
      setStudy({ ...s, quantities: data.quantities, pricing: data.pricing });
      toast.success(`Orçamentação: ${data.pricing?.priced_lines ?? 0} linha(s) com preço encontrado`);
    } catch (e) { toast.error(e?.response?.data?.detail || "Não foi possível orçamentar"); }
    finally { setBusy(false); }
  };

  const exportPdf = async () => {
    try {
      const res = await api.get(`/mep/studies/${s.study_id}/pdf`, { responseType: "blob" });
      const url = URL.createObjectURL(res.data);
      const a = document.createElement("a");
      a.href = url; a.download = filenameFromResponse(res, nomDocument("Planos-execucao-instalacoes", s.title)); a.click();
      URL.revokeObjectURL(url);
    } catch { toast.error("Não foi possível exportar o PDF"); }
  };

  const sum = s.summary || {};
  const TABS = [
    { k: "plan", l: "Planta", Icon: MapPin },
    { k: "points", l: "Pontos", Icon: ListChecks },
    { k: "circuits", l: "Circuitos", Icon: Gauge },
    { k: "quantites", l: "Quantidades", Icon: Table2 },
    { k: "controles", l: `Controlos (${(sum.errors || 0) + (sum.warnings || 0)})`, Icon: ShieldAlert },
  ];

  return (
    <div className="max-w-5xl mx-auto px-4 py-8 space-y-5" data-testid="mep-detail">
      <button onClick={onBack} className="text-sm text-muted-foreground flex items-center gap-1 hover:text-foreground" data-testid="mep-back">
        <ArrowLeft className="h-4 w-4" /> Voltar aos estudos
      </button>

      <header className="space-y-2">
        <h1 className="text-2xl font-bold" style={{ color: "#0F172A" }}>{s.title}</h1>
        <div className="flex flex-wrap items-center gap-2 text-xs">
          <Badge variant="outline">{s.norms}</Badge>
          <Badge variant="outline">{sum.habitable_m2} m² úteis</Badge>
          <Badge variant="outline">{sum.points} pontos</Badge>
          <Badge variant="outline">{sum.circuits} circuitos · {sum.rcds} diferenciais</Badge>
          <SummaryBadge status={sum.status} errors={sum.errors} warnings={sum.warnings} />
        </div>
      </header>

      <Banner />

      <div className="flex flex-wrap gap-2">
        <Button size="sm" variant="outline" onClick={exportPdf} className="gap-1" data-testid="mep-pdf-btn">
          <FileDown className="h-4 w-4" /> Exportar PDF (A3)
        </Button>
      </div>

      <div className="flex flex-wrap gap-1 border-b border-border" data-testid="mep-tabs">
        {TABS.map(({ k, l, Icon }) => (
          <button key={k} onClick={() => setTab(k)} data-testid={`mep-tab-${k}`}
            className={`px-3 py-2 text-sm font-medium border-b-2 -mb-px flex items-center gap-1 transition-colors ${
              tab === k ? "border-[#F97316] text-[#F97316]" : "border-transparent text-muted-foreground hover:text-foreground"}`}>
            <Icon className="h-4 w-4" /> {l}
          </button>
        ))}
      </div>

      {tab === "plan" && (
        <div className="space-y-3" data-testid="mep-plan-view">
          <div className="flex flex-wrap items-center gap-2">
            <div className="flex rounded-md border border-border overflow-hidden">
              {[["elec", "Eletricidade", Zap], ["plumb", "Canalização", Droplets], ["unifilar", "Esquema unifilar", Network]].map(([k, l, Icon]) => (
                <button key={k} onClick={() => setLayer(k)} data-testid={`mep-layer-${k}`}
                  className={`px-3 py-1.5 text-xs font-medium flex items-center gap-1 ${layer === k ? "bg-[#0F172A] text-white" : "bg-background text-muted-foreground hover:bg-muted"}`}>
                  <Icon className="h-3.5 w-3.5" /> {l}
                </button>
              ))}
            </div>
            {layer !== "unifilar" && (
              <select className="h-8 border rounded-md px-2 text-xs bg-background" value={levelId}
                onChange={(e) => setLevelId(e.target.value)} data-testid="mep-level-select">
                {(s.levels || []).map((lv) => <option key={lv.id} value={lv.id}>{lv.name}</option>)}
              </select>
            )}
          </div>
          <Card className="p-2 overflow-auto bg-white" data-testid="mep-svg-wrap" style={{ minHeight: 320 }}>
            {loadingSvg ? <div className="flex items-center justify-center h-80 text-muted-foreground"><Loader2 className="h-5 w-5 animate-spin" /></div>
              : svg ? <div className="mep-svg [&_svg]:w-full [&_svg]:h-auto" dangerouslySetInnerHTML={{ __html: svg }} />
              : <div className="flex items-center justify-center h-80 text-muted-foreground text-sm">Pré-visualização indisponível</div>}
          </Card>
        </div>
      )}

      {tab === "points" && (
        <PointsEditor points={points} setPoints={setPoints} levels={s.levels || []} busy={busy}
          onSave={() => saveLayout(points)} onReset={() => setPoints(s.points || [])} />
      )}

      {tab === "circuits" && <Circuits electrical={s.electrical || {}} plumbing={s.plumbing || {}} />}

      {tab === "quantites" && (
        <Quantities quantities={s.quantities || []} pricing={pricing} busy={busy} onPrice={priceWithLibrary} />
      )}

      {tab === "controles" && <Controls checks={s.checks || []} />}
    </div>
  );
}

function SummaryBadge({ status, errors, warnings }) {
  if (status === "error") return <Badge className="bg-red-500/15 text-red-700 border border-red-300">{errors} erro(s)</Badge>;
  if (status === "warning") return <Badge className="bg-amber-500/15 text-amber-700 border border-amber-300">{warnings} a verificar</Badge>;
  return <Badge className="bg-emerald-500/15 text-emerald-700 border border-emerald-300">Conforme</Badge>;
}

function PointsEditor({ points, setPoints, levels, busy, onSave, onReset }) {
  const [add, setAdd] = useState({ kind: "prise", level_id: levels[0]?.id || "", room_id: "", x: 0, y: 0 });
  const patch = (idx, p) => setPoints((ps) => ps.map((pt, i) => (i === idx ? { ...pt, ...p } : pt)));
  const del = (idx) => setPoints((ps) => ps.filter((_, i) => i !== idx));
  const addPoint = () => {
    setPoints((ps) => [...ps, { ...add, x: Number(add.x), y: Number(add.y), source: "user" }]);
    toast.message("Ponto acrescentado — guarde para recalcular");
  };
  return (
    <div className="space-y-3" data-testid="mep-points-editor">
      <p className="text-xs text-muted-foreground">
        Mova (altere X/Y em metros), acrescente ou apague pontos. « Guardar » recalcula circuitos, proteções e controlos sobre a SUA implantação.
      </p>
      <div className="flex flex-wrap gap-2">
        <Button size="sm" onClick={onSave} disabled={busy} className="gap-1 bg-[#F97316] hover:bg-[#ea6a0c]" data-testid="mep-points-save">
          {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <CheckCircle2 className="h-4 w-4" />} Guardar a implantação
        </Button>
        <Button size="sm" variant="outline" onClick={onReset} data-testid="mep-points-reset">Anular as alterações</Button>
      </div>

      <Card className="p-3 flex flex-wrap items-end gap-2" data-testid="mep-point-add">
        <select className="h-8 text-xs border rounded-md px-2 bg-background" value={add.kind}
          onChange={(e) => setAdd({ ...add, kind: e.target.value })} data-testid="mep-add-kind">
          {POINT_KINDS.map((k) => <option key={k} value={k}>{POINT_LABEL[k] || k}</option>)}
        </select>
        <select className="h-8 text-xs border rounded-md px-2 bg-background" value={add.level_id}
          onChange={(e) => setAdd({ ...add, level_id: e.target.value })} data-testid="mep-add-level">
          {levels.map((lv) => <option key={lv.id} value={lv.id}>{lv.name}</option>)}
        </select>
        <Input className="h-8 w-28 text-xs" placeholder="divisão (id)" value={add.room_id}
          onChange={(e) => setAdd({ ...add, room_id: e.target.value })} data-testid="mep-add-room" />
        <Input className="h-8 w-20 text-xs" type="number" step="0.1" placeholder="X" value={add.x}
          onChange={(e) => setAdd({ ...add, x: e.target.value })} data-testid="mep-add-x" />
        <Input className="h-8 w-20 text-xs" type="number" step="0.1" placeholder="Y" value={add.y}
          onChange={(e) => setAdd({ ...add, y: e.target.value })} data-testid="mep-add-y" />
        <Button size="sm" className="h-8 gap-1" onClick={addPoint} data-testid="mep-add-btn"><Plus className="h-4 w-4" /> Acrescentar</Button>
      </Card>

      <div className="text-xs font-semibold text-muted-foreground">Pontos ({points.length})</div>
      <div className="grid gap-1 max-h-[480px] overflow-auto pr-1">
        {points.map((p, i) => (
          <div key={i} className="flex flex-wrap items-center gap-2 border border-border rounded-md p-2 text-xs" data-testid={`mep-point-${i}`}>
            <Badge variant="outline" className="text-[10px]">{POINT_LABEL[p.kind] || p.kind}</Badge>
            <span className="text-muted-foreground w-28 truncate">{p.room_id || "—"}</span>
            <Badge variant="outline" className="text-[10px]">{p.level_id}</Badge>
            {p.source === "user" && <Badge className="bg-sky-500/15 text-sky-700 text-[10px]">alterado</Badge>}
            <div className="flex items-center gap-1 ml-auto">
              <span className="text-muted-foreground">X</span>
              <Input className="h-7 w-16 text-xs" type="number" step="0.1" value={p.x}
                onChange={(e) => patch(i, { x: Number(e.target.value), source: "user" })} data-testid={`mep-point-x-${i}`} />
              <span className="text-muted-foreground">Y</span>
              <Input className="h-7 w-16 text-xs" type="number" step="0.1" value={p.y}
                onChange={(e) => patch(i, { y: Number(e.target.value), source: "user" })} data-testid={`mep-point-y-${i}`} />
              <Button size="icon" variant="ghost" className="h-6 w-6" onClick={() => del(i)} data-testid={`mep-point-del-${i}`}>
                <Trash2 className="h-3.5 w-3.5 text-muted-foreground" />
              </Button>
            </div>
          </div>
        ))}
        {points.length === 0 && <p className="text-xs text-muted-foreground">Nenhum ponto.</p>}
      </div>
    </div>
  );
}

function Circuits({ electrical, plumbing }) {
  const circuits = electrical.circuits || [];
  const rcds = electrical.rcds || [];
  const panel = electrical.panel || {};
  return (
    <div className="space-y-4" data-testid="mep-circuits">
      <Card className="p-4 space-y-2">
        <h3 className="text-sm font-semibold flex items-center gap-1" style={{ color: "#0F172A" }}><Zap className="h-4 w-4 text-[#F97316]" /> Quadro elétrico</h3>
        <div className="text-xs text-muted-foreground">
          {panel.modules_used != null && <>Módulos utilizados: <b>{panel.modules_used}</b> · reserva: <b>{panel.modules_reserve}</b> · </>}
          Diferenciais 30 mA: <b>{rcds.length}</b>{panel.contactor_hc ? " · contactor bi-horário" : ""}
        </div>
        <div className="overflow-auto">
          <table className="w-full text-xs">
            <thead><tr className="text-left text-muted-foreground border-b">
              <th className="py-1 pr-2">Circuit</th><th className="pr-2">Tipo</th><th className="pr-2">Secção</th>
              <th className="pr-2">Proteção</th><th className="pr-2">Diferencial</th><th className="pr-2">Compr.</th><th>Pts</th>
            </tr></thead>
            <tbody>
              {circuits.map((c, i) => (
                <tr key={i} className="border-b border-border/50" data-testid={`mep-circuit-${i}`}>
                  <td className="py-1 pr-2 font-medium">{c.use || c.kind}</td>
                  <td className="pr-2">{c.kind}</td>
                  <td className="pr-2">{c.section_mm2} mm²</td>
                  <td className="pr-2">{c.breaker_a} A</td>
                  <td className="pr-2">{c.rcd_id}</td>
                  <td className="pr-2">{c.length_m} m</td>
                  <td>{Array.isArray(c.points) ? c.points.length : "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>

      <Card className="p-4 space-y-2">
        <h3 className="text-sm font-semibold flex items-center gap-1" style={{ color: "#0F172A" }}><Droplets className="h-4 w-4 text-sky-600" /> Redes de água e esgotos</h3>
        <PlumbTable title="Alimentação água fria / AQS" rows={(plumbing.supplies || []).map((x) => [x.fixture, x.net, `Ø ${x.diameter_mm} mm`, `${x.velocity_ms} m/s`])}
          head={["Aparelho", "Rede", "Diâmetro", "Velocidade"]} tid="supplies" />
        <PlumbTable title="Esgotos" rows={(plumbing.drains || []).map((x) => [x.fixture, x.net, `Ø ${x.diameter_mm} mm`, `desnível ${x.drop_m}/${x.available_m} m`])}
          head={["Aparelho", "Rede", "Diâmetro", "Desnível disp."]} tid="drains" />
        {plumbing.collector && <p className="text-xs text-muted-foreground">Coletor: Ø {plumbing.collector.diameter_mm} mm · saída {plumbing.exit}</p>}
      </Card>
    </div>
  );
}

function PlumbTable({ title, rows, head, tid }) {
  if (!rows.length) return null;
  return (
    <div className="space-y-1" data-testid={`mep-plumb-${tid}`}>
      <div className="text-xs font-semibold text-muted-foreground">{title}</div>
      <div className="overflow-auto">
        <table className="w-full text-xs">
          <thead><tr className="text-left text-muted-foreground border-b">{head.map((h) => <th key={h} className="py-1 pr-2">{h}</th>)}</tr></thead>
          <tbody>{rows.map((r, i) => <tr key={i} className="border-b border-border/50">{r.map((c, j) => <td key={j} className="py-1 pr-2">{c}</td>)}</tr>)}</tbody>
        </table>
      </div>
    </div>
  );
}

function Quantities({ quantities, pricing, busy, onPrice }) {
  return (
    <div className="space-y-3" data-testid="mep-quantities">
      <div className="flex flex-wrap items-center gap-2">
        <Button size="sm" onClick={onPrice} disabled={busy} className="gap-1 bg-[#F97316] hover:bg-[#ea6a0c]" data-testid="mep-price-btn">
          {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Calculator className="h-4 w-4" />} Orçamentar com a minha biblioteca
        </Button>
        {pricing && <span className="text-xs text-muted-foreground" data-testid="mep-price-summary">
          {pricing.priced_lines} linha(s) com preço, {pricing.unpriced_lines} a completar
          {pricing.total_eur != null && <> · total <b>{pricing.total_eur} €</b></>}
        </span>}
      </div>
      <p className="text-[11px] text-muted-foreground flex items-center gap-1">
        <Info className="h-3 w-3" /> Os preços vêm exclusivamente da biblioteca da sua empresa — nenhum preço é inventado pela IA.
      </p>
      <div className="overflow-auto">
        <table className="w-full text-xs">
          <thead><tr className="text-left text-muted-foreground border-b">
            <th className="py-1 pr-2">Code</th><th className="pr-2">Designação</th><th className="pr-2">Qtd.</th>
            <th className="pr-2">Unidade</th><th className="pr-2">P.U.</th><th>Total</th>
          </tr></thead>
          <tbody>
            {quantities.map((q, i) => (
              <tr key={i} className="border-b border-border/50" data-testid={`mep-qty-${i}`}>
                <td className="py-1 pr-2 font-mono text-[10px]">{q.code}</td>
                <td className="pr-2">{q.designation}</td>
                <td className="pr-2">{q.quantity}</td>
                <td className="pr-2">{q.unit}</td>
                <td className="pr-2">{q.unit_price != null ? `${q.unit_price} €` : <span className="text-amber-600">a orçamentar</span>}</td>
                <td>{q.unit_price != null ? `${(q.unit_price * q.quantity).toFixed(2)} €` : "—"}</td>
              </tr>
            ))}
            {quantities.length === 0 && <tr><td colSpan={6} className="py-2 text-muted-foreground">Nenhuma quantidade.</td></tr>}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function Controls({ checks }) {
  const order = { error: 0, warning: 1, info: 2, ok: 3 };
  const sorted = [...checks].sort((a, b) => (order[a.status] ?? 9) - (order[b.status] ?? 9));
  return (
    <div className="space-y-2" data-testid="mep-controls">
      {sorted.length === 0 && <p className="text-sm text-muted-foreground">Nenhum controlo.</p>}
      {sorted.map((c, i) => {
        const st = CHECK_STYLE[c.status] || CHECK_STYLE.info;
        const Icon = st.Icon;
        return (
          <div key={i} className={`flex items-start gap-2 rounded-md border p-2 text-sm ${st.cls}`} data-testid={`mep-check-${i}`}>
            <Icon className="h-4 w-4 shrink-0 mt-0.5" />
            <span>{c.message}</span>
          </div>
        );
      })}
    </div>
  );
}
