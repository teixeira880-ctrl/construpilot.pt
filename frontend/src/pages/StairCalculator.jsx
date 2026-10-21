import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";
import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { Textarea } from "@/components/ui/textarea";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import Stair3D from "@/components/planTakeoff/Stair3D";
import {
  Footprints, Calculator, Sparkles, FileDown, Save, FolderOpen, Plus,
  Trash2, Bot, Send, Loader2, CheckCircle2, AlertTriangle, XCircle, Building2, FileText,
} from "lucide-react";

const STAIR_TYPES = [
  { key: "straight", label: "Escada reta", api: "straight" },
  { key: "quarter_turn_bottom", label: "Quarto de volta em baixo", api: "quarter-turn-bottom" },
  { key: "quarter_turn_top", label: "Quarto de volta em cima", api: "quarter-turn-top" },
  { key: "half_turn", label: "Meia volta", api: "half-turn" },
  { key: "helicoidal", label: "Helicoidal (caracol)", api: "helicoidal" },
];
const TYPE_LABEL = Object.fromEntries(STAIR_TYPES.map((t) => [t.key, t.label]));

const DEFAULT_FORM = {
  floor_height_mm: "2700",
  available_length_mm: "4000",
  available_width_mm: "1000",
  stair_width_mm: "900",
  slab_thickness_mm: "200",
  ceiling_height_mm: "",
  tread_thickness_mm: "30",
  has_risers: true,
  direction: "right",
  balancing: "balanced",
  num_winders: "auto",
  walkline_offset_mm: "500",
  inner_radius_mm: "0",
  landing_length_mm: "",
  landing_width_mm: "",
  steps_before_landing: "0",
  outer_radius_mm: "900",
  sweep_angle_deg: "360",
};

const n = (v) => { const x = parseFloat(String(v).replace(",", ".")); return Number.isFinite(x) ? x : null; };
const mm = (v) => (v == null ? "—" : `${Math.round(v)} mm`);
const ALERT_META = {
  red: { icon: XCircle, cls: "text-red-600 bg-red-50 border-red-200" },
  orange: { icon: AlertTriangle, cls: "text-amber-700 bg-amber-50 border-amber-200" },
  green: { icon: CheckCircle2, cls: "text-emerald-700 bg-emerald-50 border-emerald-200" },
};

function AlertRow({ a }) {
  const meta = ALERT_META[a.level] || ALERT_META.orange;
  const Icon = meta.icon;
  return (
    <div className={`flex items-start gap-2 rounded-md border p-2 text-sm ${meta.cls}`} data-testid={`stair-alert-${a.code}`}>
      <Icon className="h-4 w-4 mt-0.5 shrink-0" />
      <div>
        <span className="font-medium">{a.code}</span> — {a.message || a.message_fr}
        {a.value != null && a.threshold != null && (
          <span className="opacity-70"> ({Math.round(a.value)} / limite {Math.round(a.threshold)})</span>
        )}
      </div>
    </div>
  );
}

function ResultDetail({ r }) {
  if (!r) return null;
  const rows = [
    ["Número de degraus (espelhos)", r.num_steps],
    ["Número de cobertores", r.num_treads],
    ["Altura do espelho", mm(r.riser_height_mm)],
    ["Cobertor (linha de passagem)", mm(r.tread_depth_mm)],
    ["Blondel (2h + g)", `${Math.round(r.blondel_value_mm)} mm`],
    ["Inclinação", `${r.slope_deg?.toFixed(1)}°`],
    ["Desenvolvimento (projeção horizontal)", mm(r.stair_run_mm)],
    ["Comprimento desenvolvido", mm(r.stair_length_mm)],
    ["Pé-direito livre (headroom)", mm(r.headroom_mm)],
  ];
  return (
    <div className="space-y-3" data-testid="stair-result-detail">
      <div className="flex items-center gap-2">
        <Badge variant={r.is_buildable ? "default" : "destructive"} data-testid="stair-buildable-badge">
          {r.is_buildable ? "Conforme" : "Não conforme"}
        </Badge>
        <span className="text-xs text-muted-foreground">{TYPE_LABEL[r.stair_type] || r.stair_type}</span>
      </div>
      {!r.is_buildable && (
        <div className="rounded-md border border-red-300 bg-red-50 px-3 py-2 text-sm font-semibold text-red-700" data-testid="stair-nonconforming-banner">
          Solução não conforme (RGEU / boas práticas) — não utilizar em habitação. Ver alertas vermelhos.
        </div>
      )}
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
        {rows.map(([k, v]) => (
          <div key={k} className="flex justify-between rounded-md border border-border bg-muted/30 px-3 py-2 text-sm">
            <span className="text-muted-foreground">{k}</span>
            <span className="font-semibold num">{typeof v === "number" ? v : v}</span>
          </div>
        ))}
      </div>
      {r.alerts?.length > 0 && (
        <div className="space-y-1.5">
          {r.alerts.map((a, i) => <AlertRow key={i} a={a} />)}
        </div>
      )}
    </div>
  );
}

export default function StairCalculator() {
  const nav = useNavigate();
  const [stairType, setStairType] = useState("straight");
  const [form, setForm] = useState(DEFAULT_FORM);
  const [projectName, setProjectName] = useState("Escada sem nome");
  const [projectId, setProjectId] = useState(null);
  const [projects, setProjects] = useState([]);
  const [showProjects, setShowProjects] = useState(false);

  const [result, setResult] = useState(null);
  const [optimizeResult, setOptimizeResult] = useState(null);
  const [concrete, setConcrete] = useState(null);
  const [loading, setLoading] = useState("");
  const [tab, setTab] = useState("calc");

  // Assistant
  const [chat, setChat] = useState([]);
  const [chatInput, setChatInput] = useState("");
  const [convId, setConvId] = useState(null);
  const [chatLoading, setChatLoading] = useState(false);
  const [detailedSteel, setDetailedSteel] = useState(true);
  const chatEndRef = useRef(null);

  const set = (k, v) => setForm((f) => ({ ...f, [k]: v }));

  useEffect(() => { loadProjects(); }, []);
  useEffect(() => { chatEndRef.current?.scrollIntoView({ behavior: "smooth" }); }, [chat]);

  const loadProjects = async () => {
    try { const { data } = await api.get("/stairs/projects"); setProjects(data.projects || []); }
    catch { /* noop */ }
  };

  const buildPayload = (type) => {
    const base = {
      floor_height_mm: n(form.floor_height_mm),
      available_length_mm: n(form.available_length_mm),
      available_width_mm: n(form.available_width_mm),
      stair_width_mm: n(form.stair_width_mm),
      slab_thickness_mm: n(form.slab_thickness_mm) ?? 200,
      tread_thickness_mm: n(form.tread_thickness_mm) ?? 30,
      has_risers: !!form.has_risers,
      direction: form.direction,
    };
    if (n(form.ceiling_height_mm)) base.ceiling_height_mm = n(form.ceiling_height_mm);
    if (type === "helicoidal") {
      return {
        floor_height_mm: base.floor_height_mm,
        inner_radius_mm: n(form.inner_radius_mm) || 200,
        outer_radius_mm: n(form.outer_radius_mm) || 900,
        sweep_angle_deg: n(form.sweep_angle_deg) || 360,
        walkline_offset_mm: n(form.walkline_offset_mm) || 500,
        slab_thickness_mm: base.slab_thickness_mm,
        ceiling_height_mm: base.ceiling_height_mm,
        tread_thickness_mm: base.tread_thickness_mm,
        has_risers: base.has_risers,
      };
    }
    if (type === "quarter_turn_bottom" || type === "quarter_turn_top" || type === "half_turn") {
      const turn = { ...base, balancing: form.balancing, walkline_offset_mm: n(form.walkline_offset_mm) || 500, inner_radius_mm: n(form.inner_radius_mm) || 0 };
      if (form.balancing === "balanced") {
        turn.num_winders = form.num_winders === "auto" ? "auto" : (parseInt(form.num_winders) || 3);
      } else {
        if (n(form.landing_length_mm)) turn.landing_length_mm = n(form.landing_length_mm);
        if (n(form.landing_width_mm)) turn.landing_width_mm = n(form.landing_width_mm);
        turn.steps_before_landing = parseInt(form.steps_before_landing) || 0;
      }
      return turn;
    }
    return base;
  };

  const doCalculate = async () => {
    const t = STAIR_TYPES.find((x) => x.key === stairType);
    setLoading("calc");
    setConcrete(null);
    try {
      const { data } = await api.post(`/stairs/calculate/${t.api}`, buildPayload(stairType));
      setResult(data);
      setTab("calc");
      if (data.is_buildable) toast.success("Escada calculada — conforme");
      else toast.warning("Escada calculada — NÃO conforme (ver alertas vermelhos)");
    } catch (e) {
      toast.error(e?.response?.data?.detail?.[0]?.msg || e?.response?.data?.detail || "Cálculo impossível");
    }
    setLoading("");
  };

  const doOptimize = async () => {
    setLoading("optimize");
    try {
      const p = {
        floor_height_mm: n(form.floor_height_mm),
        available_length_mm: n(form.available_length_mm),
        available_width_mm: n(form.available_width_mm),
        stair_width_mm: n(form.stair_width_mm),
        slab_thickness_mm: n(form.slab_thickness_mm) ?? 200,
        tread_thickness_mm: n(form.tread_thickness_mm) ?? 30,
        has_risers: !!form.has_risers,
        max_solutions: 5,
      };
      if (n(form.ceiling_height_mm)) p.ceiling_height_mm = n(form.ceiling_height_mm);
      const { data } = await api.post("/stairs/optimize", p);
      setOptimizeResult(data);
      setTab("optimize");
      if (!data.solutions?.length) toast.warning("Nenhuma solução exequível — alargue as restrições");
      else toast.success(`${data.solutions.length} solução(ões) proposta(s)`);
    } catch (e) {
      toast.error(e?.response?.data?.detail?.[0]?.msg || e?.response?.data?.detail || "Otimização impossível");
    }
    setLoading("");
  };

  const applySolution = (sol) => {
    setStairType(sol.type);
    setResult(sol.result);
    setConcrete(null);
    setTab("calc");
    setProjectName((prev) => (!prev || prev === "Escada sem nome")
      ? `Escada ${TYPE_LABEL[sol.type] || sol.type}` : prev);
    toast.success(`Solução ${TYPE_LABEL[sol.type] || sol.type} carregada`);
  };

  const doConcrete = async () => {
    if (!result) return toast.error("Calcule primeiro uma escada");
    setLoading("concrete");
    try {
      const { data } = await api.post("/stairs/concrete/analyze", { stair_result: result, stair_type: result.stair_type });
      setConcrete(data);
      setTab("concrete");
      toast.success("Análise de betão armado pronta (NP EN 1992)");
    } catch (e) {
      toast.error(e?.response?.data?.detail?.[0]?.msg || e?.response?.data?.detail || "Análise do betão impossível");
    }
    setLoading("");
  };

  const createQuote = async () => {
    if (!result) return toast.error("Calcule primeiro uma escada");
    setLoading("quote");
    try {
      const { data } = await api.post("/stairs/to-quote", {
        project_name: projectName || "Escada",
        stair_result: result,
        concrete_analysis: concrete,
        detailed_steel: detailedSteel,
      });
      toast.success("Orçamento criado — complete os preços unitários");
      nav(`/devis-editeur/${data.doc_id}`);
    } catch (e) {
      toast.error(e?.response?.data?.detail?.[0]?.msg || e?.response?.data?.detail || "Não foi possível criar o orçamento");
    }
    setLoading("");
  };

  const downloadPdf = async () => {
    if (!result) return toast.error("Calcule primeiro uma escada");
    setLoading("pdf");
    try {
      const res = await api.post("/stairs/dossier/generate", {
        project_name: projectName || "Escada",
        stair_input: buildPayload(stairType),
        stair_result: result,
        concrete_analysis: concrete,
      }, { responseType: "blob" });
      const url = URL.createObjectURL(new Blob([res.data], { type: "application/pdf" }));
      const a = document.createElement("a");
      const safe = (projectName || "escalier").replace(/[^a-zA-Z0-9-_]/g, "_").slice(0, 60) || "escalier";
      a.href = url; a.download = `${safe}.pdf`; document.body.appendChild(a); a.click(); a.remove();
      URL.revokeObjectURL(url);
      toast.success("Processo PDF transferido");
    } catch { toast.error("Geração do PDF impossível"); }
    setLoading("");
  };

  const saveProject = async () => {
    const body = { name: projectName || "Escada sem nome", stair_type: stairType, input: form, result, concrete_analysis: concrete };
    try {
      if (projectId) {
        await api.put(`/stairs/projects/${projectId}`, body);
        toast.success("Projeto guardado");
      } else {
        const { data } = await api.post("/stairs/projects", body);
        setProjectId(data.project.project_id);
        toast.success("Projeto criado");
      }
      loadProjects();
    } catch { toast.error("Não foi possível guardar"); }
  };

  const openProject = async (p) => {
    try {
      const { data } = await api.get(`/stairs/projects/${p.project_id}`);
      setProjectId(data.project_id);
      setProjectName(data.name);
      setStairType(data.stair_type || "straight");
      setForm({ ...DEFAULT_FORM, ...(data.input || {}) });
      setResult(data.result || null);
      setConcrete(data.concrete_analysis || null);
      setShowProjects(false);
      toast.success(`Projet « ${data.name} » aberto`);
    } catch { toast.error("Abertura impossível"); }
  };

  const deleteProject = async (id, e) => {
    e.stopPropagation();
    try { await api.delete(`/stairs/projects/${id}`); if (id === projectId) newProject(); loadProjects(); toast.success("Projeto eliminado"); }
    catch { toast.error("Não foi possível eliminar"); }
  };

  const newProject = () => {
    setProjectId(null); setProjectName("Escada sem nome"); setStairType("straight");
    setForm(DEFAULT_FORM); setResult(null); setConcrete(null); setOptimizeResult(null); setShowProjects(false);
  };

  const sendChat = async () => {
    const msg = chatInput.trim();
    if (!msg) return;
    setChat((c) => [...c, { role: "user", content: msg }]);
    setChatInput(""); setChatLoading(true);
    try {
      const { data } = await api.post("/stairs/assistant/chat", { message: msg, conversation_id: convId });
      setConvId(data.conversation_id);
      setChat((c) => [...c, { role: "assistant", content: data.reply_text }]);
    } catch { setChat((c) => [...c, { role: "assistant", content: "Lamentamos, o assistente está indisponível de momento." }]); }
    setChatLoading(false);
  };

  const isTurn = ["quarter_turn_bottom", "quarter_turn_top", "half_turn"].includes(stairType);

  return (
    <div className="max-w-7xl mx-auto px-4 py-6 space-y-5" data-testid="stair-calculator-page">
      {/* Header */}
      <div className="flex flex-wrap items-center gap-3 justify-between">
        <div className="flex items-center gap-3 min-w-0">
          <div className="h-10 w-10 rounded-lg bg-primary/10 flex items-center justify-center shrink-0">
            <Footprints className="h-5 w-5 text-primary" />
          </div>
          <div className="min-w-0">
            <h1 className="text-xl font-bold leading-tight">Cálculo de escadas</h1>
            <p className="text-xs text-muted-foreground">Motor determinístico · RGEU / DL 163/2006 / NP EN 1992 · betão armado</p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <Input value={projectName} onChange={(e) => setProjectName(e.target.value)}
                 data-testid="stair-project-name" className="h-9 w-56" placeholder="Nome do projeto (retomado no PDF)" />
          <Button size="sm" variant="outline" onClick={saveProject} data-testid="stair-save-project" className="rounded-sm gap-1">
            <Save className="h-4 w-4" /> Guardar
          </Button>
          <div className="relative">
            <Button size="sm" variant="outline" onClick={() => setShowProjects((s) => !s)} data-testid="stair-projects-toggle" className="rounded-sm gap-1">
              <FolderOpen className="h-4 w-4" /> Projetos
            </Button>
            {showProjects && (
              <div className="absolute right-0 mt-1 w-72 max-h-80 overflow-auto rounded-md border border-border bg-background shadow-lg z-50 p-1" data-testid="stair-projects-list">
                <button onClick={newProject} className="w-full text-left px-3 py-2 text-sm rounded-sm hover:bg-muted flex items-center gap-2">
                  <Plus className="h-4 w-4" /> Novo projeto
                </button>
                {projects.length === 0 && <p className="px-3 py-2 text-xs text-muted-foreground">Nenhum projeto guardado.</p>}
                {projects.map((p) => (
                  <div key={p.project_id} onClick={() => openProject(p)}
                       className="group flex items-center justify-between px-3 py-2 text-sm rounded-sm hover:bg-muted cursor-pointer"
                       data-testid={`stair-project-${p.project_id}`}>
                    <span className="truncate">{p.name} <span className="text-[10px] text-muted-foreground">· {TYPE_LABEL[p.stair_type] || p.stair_type}</span></span>
                    <button onClick={(e) => deleteProject(p.project_id, e)} className="opacity-0 group-hover:opacity-100 text-muted-foreground hover:text-destructive">
                      <Trash2 className="h-3.5 w-3.5" />
                    </button>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-[380px_1fr] gap-5">
        {/* Input form */}
        <Card className="rounded-lg h-fit">
          <CardHeader className="pb-3">
            <CardTitle className="text-base">Restrições</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            <div className="grid gap-1">
              <Label className="text-xs">Tipo de escada</Label>
              <Select value={stairType} onValueChange={(v) => { setStairType(v); }}>
                <SelectTrigger className="h-9" data-testid="stair-type-select"><SelectValue /></SelectTrigger>
                <SelectContent>
                  {STAIR_TYPES.map((t) => <SelectItem key={t.key} value={t.key}>{t.label}</SelectItem>)}
                </SelectContent>
              </Select>
            </div>

            <div className="grid grid-cols-2 gap-2">
              <Field label="Altura a vencer (mm)" k="floor_height_mm" form={form} set={set} testid="floor-height" />
              {stairType !== "helicoidal" && <Field label="Desenvolvimento disponível (mm)" k="available_length_mm" form={form} set={set} testid="avail-length" />}
              {stairType !== "helicoidal" && <Field label="Largura disponível (mm)" k="available_width_mm" form={form} set={set} testid="avail-width" />}
              {stairType !== "helicoidal" && <Field label="Largura da escada (mm)" k="stair_width_mm" form={form} set={set} testid="stair-width" />}
              <Field label="Espessura da laje (mm)" k="slab_thickness_mm" form={form} set={set} testid="slab-thickness" />
              <Field label="Altura sob a laje (mm)" k="ceiling_height_mm" form={form} set={set} placeholder="auto" testid="ceiling-height" />
            </div>

            {stairType === "helicoidal" && (
              <div className="grid grid-cols-2 gap-2 rounded-md border border-dashed border-border p-2">
                <Field label="Raio interior (mm)" k="inner_radius_mm" form={form} set={set} testid="inner-radius" />
                <Field label="Raio exterior (mm)" k="outer_radius_mm" form={form} set={set} testid="outer-radius" />
                <Field label="Ângulo varrido (°)" k="sweep_angle_deg" form={form} set={set} testid="sweep-angle" />
                <Field label="Linha de passagem (mm)" k="walkline_offset_mm" form={form} set={set} testid="walkline" />
              </div>
            )}

            {isTurn && (
              <div className="space-y-2 rounded-md border border-dashed border-border p-2">
                <div className="grid gap-1">
                  <Label className="text-xs">Modo</Label>
                  <Select value={form.balancing} onValueChange={(v) => set("balancing", v)}>
                    <SelectTrigger className="h-9" data-testid="stair-balancing-select"><SelectValue /></SelectTrigger>
                    <SelectContent>
                      <SelectItem value="balanced">Degraus compensados</SelectItem>
                      <SelectItem value="straight">Com patamar</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
                {form.balancing === "balanced" ? (
                  <div className="grid grid-cols-2 gap-2">
                    <div className="grid gap-1">
                      <Label className="text-xs">N.º de degraus compensados</Label>
                      <Input value={form.num_winders} onChange={(e) => set("num_winders", e.target.value)}
                             placeholder="auto" data-testid="stair-num-winders" className="h-9" />
                    </div>
                    <Field label="Linha de passagem (mm)" k="walkline_offset_mm" form={form} set={set} testid="turn-walkline" />
                    <Field label="Raio interior (mm)" k="inner_radius_mm" form={form} set={set} testid="turn-inner-radius" />
                  </div>
                ) : (
                  <div className="grid grid-cols-2 gap-2">
                    <Field label="Comprimento do patamar (mm)" k="landing_length_mm" form={form} set={set} testid="landing-length" />
                    <Field label="Largura do patamar (mm)" k="landing_width_mm" form={form} set={set} testid="landing-width" />
                    <Field label="Degraus antes do patamar" k="steps_before_landing" form={form} set={set} testid="steps-before" />
                  </div>
                )}
              </div>
            )}

            <div className="flex items-center gap-4 text-sm">
              <label className="flex items-center gap-2" data-testid="stair-has-risers">
                <input type="checkbox" checked={form.has_risers} onChange={(e) => set("has_risers", e.target.checked)} /> Com espelhos
              </label>
              {stairType !== "helicoidal" && (
                <div className="flex items-center gap-2">
                  <Label className="text-xs">Direção</Label>
                  <Select value={form.direction} onValueChange={(v) => set("direction", v)}>
                    <SelectTrigger className="h-8 w-24" data-testid="stair-direction"><SelectValue /></SelectTrigger>
                    <SelectContent>
                      <SelectItem value="right">Direita</SelectItem>
                      <SelectItem value="left">Esquerda</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
              )}
            </div>

            <div className="flex gap-2 pt-1">
              <Button onClick={doCalculate} disabled={!!loading} data-testid="stair-calculate-btn" className="flex-1 rounded-sm gap-2">
                {loading === "calc" ? <Loader2 className="h-4 w-4 animate-spin" /> : <Calculator className="h-4 w-4" />} Calcular
              </Button>
              <Button onClick={doOptimize} disabled={!!loading} variant="secondary" data-testid="stair-optimize-btn" className="flex-1 rounded-sm gap-2">
                {loading === "optimize" ? <Loader2 className="h-4 w-4 animate-spin" /> : <Sparkles className="h-4 w-4" />} Otimizar
              </Button>
            </div>
          </CardContent>
        </Card>

        {/* Results */}
        <Card className="rounded-lg">
          <CardContent className="pt-5">
            <Tabs value={tab} onValueChange={setTab}>
              <TabsList className="mb-4">
                <TabsTrigger value="calc" data-testid="tab-calc">Resultado</TabsTrigger>
                <TabsTrigger value="view3d" data-testid="tab-view3d">Vista 3D</TabsTrigger>
                <TabsTrigger value="optimize" data-testid="tab-optimize">Otimizador</TabsTrigger>
                <TabsTrigger value="concrete" data-testid="tab-concrete">Betão armado</TabsTrigger>
                <TabsTrigger value="assistant" data-testid="tab-assistant">Assistente IA</TabsTrigger>
              </TabsList>

              <TabsContent value="calc">
                {result ? (
                  <div className="space-y-4">
                    <ResultDetail r={result} />
                    <div className="flex flex-wrap gap-2">
                      <Button size="sm" variant="outline" onClick={doConcrete} disabled={!!loading} data-testid="stair-concrete-btn" className="rounded-sm gap-2">
                        {loading === "concrete" ? <Loader2 className="h-4 w-4 animate-spin" /> : <Building2 className="h-4 w-4" />} Análise de betão armado
                      </Button>
                      <Button size="sm" onClick={downloadPdf} disabled={!!loading} data-testid="stair-pdf-btn" className="rounded-sm gap-2">
                        {loading === "pdf" ? <Loader2 className="h-4 w-4 animate-spin" /> : <FileDown className="h-4 w-4" />} Dossier PDF
                      </Button>
                      <Button size="sm" variant="outline" onClick={createQuote} disabled={!!loading} data-testid="stair-quote-btn" className="rounded-sm gap-2">
                        {loading === "quote" ? <Loader2 className="h-4 w-4 animate-spin" /> : <FileText className="h-4 w-4" />} Criar um orçamento
                      </Button>
                    </div>
                    <label className="flex items-center gap-2 text-xs text-muted-foreground" data-testid="stair-detailed-steel">
                      <input type="checkbox" checked={detailedSteel} onChange={(e) => setDetailedSteel(e.target.checked)} />
                      Armaduras detalhadas no orçamento (uma linha por marca: Ø, comprimento, peso)
                    </label>
                  </div>
                ) : (
                  <EmptyState text="Indique as restrições e depois clique em «Calcular» ou «Otimizar»." />
                )}
              </TabsContent>

              <TabsContent value="view3d">
                {result ? (
                  <Stair3D result={result} stairWidthMm={n(form.stair_width_mm) || 1000} />
                ) : (
                  <EmptyState text="Calcule uma escada para apresentar a pré-visualização 3D interativa." />
                )}
              </TabsContent>

              <TabsContent value="optimize">
                {optimizeResult ? (
                  <div className="space-y-3">
                    {optimizeResult.solutions?.length ? optimizeResult.solutions.map((s) => (
                      <div key={s.rank} className="rounded-lg border border-border p-3 hover:border-primary/50 transition-colors" data-testid={`stair-solution-${s.rank}`}>
                        <div className="flex items-center justify-between">
                          <div className="flex items-center gap-2">
                            <Badge className="rounded-full">#{s.rank}</Badge>
                            <span className="font-semibold text-sm">{TYPE_LABEL[s.type] || s.type}</span>
                            <span className="text-[11px] text-muted-foreground">{variantLabel(s.variant)}</span>
                          </div>
                          <span className="text-sm font-bold text-primary num">{Math.round(s.score_global)}/100</span>
                        </div>
                        <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted-foreground">
                          <span>{s.result.num_steps} degraus</span>
                          <span>H. {Math.round(s.result.riser_height_mm)} mm</span>
                          <span>Cobertor {Math.round(s.result.tread_depth_mm)} mm</span>
                          <span>Blondel {Math.round(s.result.blondel_value_mm)}</span>
                          <span>Inclinação {s.result.slope_deg?.toFixed(1)}°</span>
                        </div>
                        <div className="mt-2 flex flex-wrap gap-3 text-[11px]">
                          <ScorePill label="Conforto" v={s.scores.confort} />
                          <ScorePill label="Atravancamento" v={s.scores.encombrement} />
                          <ScorePill label="Exequibilidade" v={s.scores.faisabilite} />
                          <ScorePill label="Estética" v={s.scores.esthetique} />
                        </div>
                        <Button size="sm" variant="outline" onClick={() => applySolution(s)} data-testid={`use-solution-${s.rank}`} className="mt-2 rounded-sm h-7 text-xs">
                          Utilizar esta solução
                        </Button>
                      </div>
                    )) : <EmptyState text="Nenhuma solução exequível com estas restrições." />}
                    {optimizeResult.excluded?.length > 0 && (
                      <details className="text-xs text-muted-foreground">
                        <summary className="cursor-pointer">{optimizeResult.excluded.length} variante(s) afastada(s)</summary>
                        <ul className="mt-1 space-y-0.5 pl-4 list-disc">
                          {optimizeResult.excluded.map((x, i) => <li key={i}>{TYPE_LABEL[x.type] || x.type} ({variantLabel(x.variant)}) — {x.reason}</li>)}
                        </ul>
                      </details>
                    )}
                  </div>
                ) : (
                  <EmptyState text="Lance «Otimizar» para comparar várias soluções ordenadas por pertinência." />
                )}
              </TabsContent>

              <TabsContent value="concrete">
                {concrete ? (
                  <div className="space-y-4" data-testid="stair-concrete-result">
                    <Section title="Medição / quantidades">
                      <KeyVals obj={concrete.quantities} unitHint />
                    </Section>
                    <Section title="Cargas (kN/m²)">
                      <KeyVals obj={concrete.load_breakdown_kN_m2} />
                    </Section>
                    <Section title="Pré-dimensionamento do lanço">
                      <KeyVals obj={concrete.paillasse} />
                    </Section>
                    <Section title="Armaduras indicativas">
                      <KeyVals obj={concrete.reinforcement} />
                    </Section>
                    {concrete.nomenclature?.length > 0 && (
                      <Section title="Lista de armaduras">
                        <div className="rounded border border-border overflow-hidden">
                          <table className="w-full text-xs">
                            <thead className="bg-muted/50"><tr>{Object.keys(concrete.nomenclature[0]).map((h) => <th key={h} className="p-2 text-left">{KV_LABEL[h] || h.replace(/_/g, " ")}</th>)}</tr></thead>
                            <tbody>
                              {concrete.nomenclature.map((row, i) => (
                                <tr key={i} className="border-t border-border">
                                  {Object.values(row).map((v, j) => <td key={j} className="p-2 num">{String(v)}</td>)}
                                </tr>
                              ))}
                            </tbody>
                          </table>
                        </div>
                      </Section>
                    )}
                    {concrete.alerts?.length > 0 && <div className="space-y-1.5">{concrete.alerts.map((a, i) => <AlertRow key={i} a={a} />)}</div>}
                    {concrete.disclaimer && (
                      <p className="text-[11px] text-muted-foreground italic border-t border-border pt-2">
                        {concrete.disclaimer.text || concrete.disclaimer.fr || Object.values(concrete.disclaimer)[0]}
                      </p>
                    )}
                  </div>
                ) : (
                  <EmptyState text="Calcule uma escada e depois lance a análise de betão armado (NP EN 1992)." />
                )}
              </TabsContent>

              <TabsContent value="assistant">
                <div className="flex flex-col h-[520px]">
                  <div className="flex-1 overflow-auto space-y-3 pr-1" data-testid="stair-chat-messages">
                    {chat.length === 0 && (
                      <div className="text-sm text-muted-foreground flex items-start gap-2 rounded-md border border-dashed border-border p-3">
                        <Bot className="h-4 w-4 mt-0.5" />
                        <span>Faça uma pergunta: «Calcula uma escada reta para 2,80 m, desenvolvimento 3,5 m» ou «Que espessura de lanço para esta escada?». O assistente utiliza o motor determinístico.</span>
                      </div>
                    )}
                    {chat.map((m, i) => (
                      <div key={i} className={`flex ${m.role === "user" ? "justify-end" : "justify-start"}`}>
                        <div className={`max-w-[80%] rounded-lg px-3 py-2 text-sm whitespace-pre-wrap ${m.role === "user" ? "bg-primary text-primary-foreground" : "bg-muted"}`}>
                          {m.content}
                        </div>
                      </div>
                    ))}
                    {chatLoading && <div className="flex justify-start"><div className="bg-muted rounded-lg px-3 py-2"><Loader2 className="h-4 w-4 animate-spin" /></div></div>}
                    <div ref={chatEndRef} />
                  </div>
                  <div className="flex gap-2 pt-3 border-t border-border mt-3">
                    <Textarea value={chatInput} onChange={(e) => setChatInput(e.target.value)}
                              onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); sendChat(); } }}
                              placeholder="A sua pergunta…" data-testid="stair-chat-input" className="min-h-[44px] max-h-24 resize-none" />
                    <Button onClick={sendChat} disabled={chatLoading || !chatInput.trim()} data-testid="stair-chat-send" className="rounded-sm self-end gap-1">
                      <Send className="h-4 w-4" />
                    </Button>
                  </div>
                </div>
              </TabsContent>
            </Tabs>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}

function Field({ label, k, form, set, placeholder, testid }) {
  return (
    <div className="grid gap-1">
      <Label className="text-xs">{label}</Label>
      <Input type="number" value={form[k]} onChange={(e) => set(k, e.target.value)}
             placeholder={placeholder} data-testid={`stair-field-${testid}`} className="h-9" />
    </div>
  );
}

function EmptyState({ text }) {
  return <div className="text-sm text-muted-foreground py-12 text-center">{text}</div>;
}

function ScorePill({ label, v }) {
  return <span className="rounded-full bg-muted px-2 py-0.5">{label} <b className="num">{Math.round(v)}</b></span>;
}

function Section({ title, children }) {
  return (
    <div>
      <h3 className="text-sm font-semibold mb-2">{title}</h3>
      {children}
    </div>
  );
}

const variantLabel = (v) => ({ balanced: "degraus em leque", straight: "patamar reto", default: "padrão" }[v]
  || (String(v).startsWith("sweep_") ? `rotação ${String(v).slice(6)}°` : v));
const KV_LABEL = {
  concrete_volume_m3: "Volume de betão (m³)", paillasse_volume_m3: "Volume do lanço (m³)", tread_volume_m3: "Volume dos degraus (m³)",
  formwork_area_m2: "Área de cofragem (m²)", paillasse_area_m2: "Área do lanço (m²)", tread_count: "N.º de cobertores",
  riser_count: "N.º de espelhos", landing_count: "N.º de patamares", landing_area_m2: "Área de patamares (m²)",
  paillasse_length_mm: "Comprimento do lanço (mm)", paillasse_thickness_mm: "Espessura do lanço (mm)", width_mm: "Largura (mm)",
  live_load: "Sobrecarga (kN/m²)", dead_load_extra: "Restantes cargas permanentes (kN/m²)", self_weight: "Peso próprio (kN/m²)",
  total_ELS: "Total ELS (kN/m²)", total_ELU: "Total ELU (kN/m²)",
  thickness_recommended_mm: "Espessura recomendada (mm)", thickness_min_L25_mm: "Espessura mínima L/25 (mm)", span_mm: "Vão (mm)",
  abaque_used: "Ábaco utilizado", concrete_class: "Classe de betão", steel_grade: "Classe de aço", exposure_class: "Classe de exposição",
  support_type: "Tipo de apoio", main_bars: "Armadura principal", distribution_bars: "Armadura de distribuição",
  upper_bars: "Armadura superior (apoios)", tread_bars: "Armadura dos degraus", starter_bars: "Armaduras de espera",
  anchor_length_mm: "Comprimento de amarração (mm)", cover_mm: "Recobrimento (mm)", total_steel_kg: "Aço total (kg)",
  As_computed_mm2_per_m: "As calculada (mm²/m)", utile_height_d_mm: "Altura útil d (mm)", M_ELU_kNm_per_m: "M ELU (kNm/m)",
  repere: "Marca", Repere: "Marca", designation: "Designação", Designation: "Designação", diameter: "Ø", Diameter: "Ø",
  length_m: "Comprimento (m)", Length_m: "Comprimento (m)", count: "Quantidade", Count: "Quantidade",
  total_length_m: "Comprimento total (m)", Total_length_m: "Comprimento total (m)", weight_kg: "Peso (kg)", Weight_kg: "Peso (kg)",
};
const KV_VALUE = { out_of_range: "fora do ábaco", simple: "simplesmente apoiado", encastree_haut: "encastrado em cima", encastree_bas: "encastrado em baixo", bi_encastree: "bi-encastrado" };
const fmtBars = (v) => {
  if (Array.isArray(v)) return v.join(", ");
  const parts = [];
  if (v.diameter_mm) parts.push(`Ø${v.diameter_mm}`);
  if (v.spacing_mm) parts.push(`a cada ${v.spacing_mm} mm`);
  if (v.count) parts.push(`${v.count} un.`);
  if (v.count_per_riser) parts.push(`${v.count_per_riser} por degrau`);
  if (v.length_mm) parts.push(`L = ${v.length_mm} mm`);
  return parts.length ? parts.join(" · ") : JSON.stringify(v);
};

function KeyVals({ obj, unitHint }) {
  if (!obj || typeof obj !== "object") return null;
  const fmt = (v) => (typeof v === "number" ? (Number.isInteger(v) ? v : v.toFixed(2)) : String(v));
  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
      {Object.entries(obj).map(([k, v]) => (
        <div key={k} className="flex justify-between rounded-md border border-border bg-muted/30 px-3 py-1.5 text-xs">
          <span className="text-muted-foreground">{KV_LABEL[k] || k.replace(/_/g, " ")}</span>
          <span className="font-semibold num">{typeof v === "object" && v !== null ? fmtBars(v) : (KV_VALUE[v] || fmt(v))}</span>
        </div>
      ))}
    </div>
  );
}
