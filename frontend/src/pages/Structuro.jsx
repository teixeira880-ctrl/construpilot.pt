import React, { useEffect, useState, useCallback } from "react";
import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Label } from "@/components/ui/label";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter, DialogDescription,
} from "@/components/ui/dialog";
import { toast } from "sonner";
import {
  Building2, Plus, Trash2, AlertTriangle, ShieldAlert, HelpCircle, Lock, HardHat,
  CheckCircle2, Loader2, FlaskConical, Ruler, ArrowLeft, FileWarning, FileDown, Upload, FileText, Calculator,
} from "lucide-react";

const VERIF_STYLE = {
  bloquee: { label: "Bloqueada (dados em falta)", cls: "bg-red-500/15 text-red-600", Icon: ShieldAlert },
  en_attente_moteur: { label: "A aguardar o motor (indisponível)", cls: "bg-amber-500/15 text-amber-700", Icon: Lock },
  hors_domaine: { label: "Fora do âmbito", cls: "bg-slate-500/15 text-slate-600", Icon: FileWarning },
  non_calculee: { label: "Não calculada", cls: "bg-slate-500/15 text-slate-600", Icon: HelpCircle },
  perimee: { label: "Desatualizada", cls: "bg-orange-500/15 text-orange-600", Icon: AlertTriangle },
};
const ELEMENT_LABEL = {
  mur_porteur: "Parede resistente", poutre: "Viga", poteau: "Pilar", plancher: "Pavimento / laje", appui: "Apoio",
  fondation_semelle: "Sapata / fundação", linteau: "Padieira", chevetre: "Viga de cabeceira", ouverture: "Abertura", etai: "Escoramento",
};
const LIFECYCLE_LABEL = {
  brouillon: "rascunho", donnees_a_confirmer: "dados a confirmar", calcule: "calculado", a_revoir: "a rever", approuve: "aprovado",
};
const SOURCE_LABEL = {
  mesure: "medição", document: "documento", essai: "ensaio", observation: "observação", declaration: "declaração", inconnu: "desconhecido",
};
const MISSING_LABEL = {
  "charges.exploitation": "sobrecargas de utilização", "charges.permanentes": "cargas permanentes", "charges.sur_appuis": "cargas nos apoios",
  "etai.charges_reprises": "cargas no escoramento", "etai.hauteur": "altura do escoramento", "etai.materiel": "material de escoramento",
  "fondation.geometrie": "geometria da fundação", "fondation.niveau_assise": "cota de assentamento", "geometrie.niveaux": "pisos (geometria)",
  "mur.epaisseur": "espessura da parede", "mur.materiau_resistance": "material/resistência da parede", "niveau_inferieur.capacite": "capacidade do piso inferior",
  "ouverture.charges_reprises": "cargas sobre a abertura", "ouverture.portee": "vão da abertura", "ouverture.position": "posição da abertura",
  "plancher.entraxe": "afastamento das vigas do pavimento", "plancher.etat_abouts": "estado dos apoios do pavimento", "plancher.portee": "vão do pavimento",
  "plancher.section": "secção das vigas do pavimento", "plancher.sens_porteur": "direção resistente do pavimento", "poutre.appuis": "apoios da viga",
  "poutre.maintien_lateral": "travamento lateral da viga", "sol.portance": "capacidade resistente do solo",
};
const LEVEL_LABEL = {
  exploration: "Exploração", preliminaire: "Estudo preliminar", calculee: "Estudo calculado",
};

export default function Structuro() {
  const [studies, setStudies] = useState([]);
  const [active, setActive] = useState(null);
  const [desc, setDesc] = useState("");
  const [busy, setBusy] = useState(false);

  const loadList = useCallback(async () => {
    try { const { data } = await api.get("/structuro/studies"); setStudies(data.studies || []); }
    catch { /* ignore */ }
  }, []);
  useEffect(() => { loadList(); }, [loadList]);

  const open = async (id) => {
    try { const { data } = await api.get(`/structuro/studies/${id}`); setActive(data); }
    catch { toast.error("Abertura impossível"); }
  };

  const createStudy = async () => {
    if (!desc.trim()) { toast.error("Descreva a casa e as obras pretendidas"); return; }
    setBusy(true);
    try {
      const { data } = await api.post("/structuro/studies", { description: desc });
      setDesc(""); await loadList(); await open(data.study_id);
      toast.success("Estudo criado — factos extraídos, responda ao questionário");
    } catch (e) { toast.error(e?.response?.data?.detail || "Criação impossível"); }
    finally { setBusy(false); }
  };

  const createDemo = async () => {
    setBusy(true);
    try { const { data } = await api.post("/structuro/studies/demo"); await loadList(); await open(data.study_id); }
    catch { toast.error("Demonstração indisponível"); } finally { setBusy(false); }
  };

  const removeStudy = async (id) => {
    try { await api.delete(`/structuro/studies/${id}`); if (active?.study_id === id) setActive(null); await loadList(); }
    catch { toast.error("Não foi possível eliminar"); }
  };

  if (active) return <StudyDetail study={active} setStudy={setActive} onBack={() => { setActive(null); loadList(); }} />;

  return (
    <div className="max-w-5xl mx-auto px-4 py-8 space-y-8" data-testid="structuro-page">
      <header className="space-y-2">
        <div className="flex items-center gap-2">
          <Building2 className="h-6 w-6 text-slate-700" />
          <h1 className="text-3xl font-bold tracking-tight">StructuroPilot</h1>
          <Badge variant="outline" className="ml-1">Capítulo A · estudo autónomo</Badge>
        </div>
        <p className="text-sm text-muted-foreground max-w-2xl">
          Comece um estudo estrutural a partir de uma simples descrição — sem processo de engenharia. A ferramenta extrai os factos, faz as perguntas certas e rastreia cada dado.
        </p>
      </header>

      <a href="/structuro/calcul" data-testid="link-structure-calc" className="block rounded-md border border-emerald-700/30 bg-emerald-50 p-4 hover:bg-emerald-100 transition-colors">
        <div className="font-semibold text-sm">Projeto de licenciamento → modelo estrutural, cálculo gravítico e plantas de princípio</div>
        <div className="text-xs text-muted-foreground mt-1">Paredes, vigas, pilares, lajes e sapatas. Esforços rastreáveis e exportações PDF/DXF; dimensionamento resistente a completar.</div>
      </a>
      <a href="/structuro/lecture-plan" data-testid="link-plan-reader"
         className="flex items-center gap-3 rounded-md border border-primary/30 bg-primary/5 p-4 hover:bg-primary/10 transition-colors">
        <div className="rounded-sm bg-primary/15 p-2"><HardHat className="h-5 w-5 text-primary" /></div>
        <div className="flex-1">
          <div className="font-semibold text-sm">Leitura de planta — medição da estrutura (sapatas, pilares, paredes de betão)</div>
          <div className="text-xs text-muted-foreground">Importe um PDF de fundações/estrutura: a IA identifica os elementos, calcula o betão/aço e pede qualquer cota em falta.</div>
        </div>
        <span className="text-primary text-sm font-medium">Abrir →</span>
      </a>

      <div className="rounded-md border border-amber-300 bg-amber-50 p-3 text-[13px] text-amber-800 flex gap-2" data-testid="structuro-disclaimer">
        <AlertTriangle className="h-4 w-4 shrink-0 mt-0.5" />
        <span>
          <b>Ferramenta de recolha e esboço</b> — não realiza <b>nenhum cálculo estrutural quantificado</b> e não substitui a verificação de um engenheiro. O nível «Estudo calculado» está <b>bloqueado</b>
          (textos normativos dos Eurocódigos não licenciados). Nenhum documento é «apto para execução».
        </span>
      </div>

      <Card className="p-5 space-y-3">
        <label className="text-sm font-semibold">Criar um estudo a partir de uma descrição</label>
        <Textarea value={desc} onChange={(e) => setDesc(e.target.value)} rows={3}
          placeholder="Ex.: Casa de cerca de 1850, dois pisos sobre cave, paredes de pedra ~50 cm, pavimentos de madeira. Abertura de ~2,40 m entre a sala e a cozinha."
          data-testid="structuro-desc-input" />
        <div className="flex flex-wrap gap-2">
          <Button onClick={createStudy} disabled={busy} data-testid="structuro-create-btn" className="gap-1">
            {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Plus className="h-4 w-4" />} Criar o estudo
          </Button>
          <Button variant="outline" onClick={createDemo} disabled={busy} data-testid="structuro-demo-btn" className="gap-1">
            <FlaskConical className="h-4 w-4" /> Carregar a demonstração «Casa 1850»
          </Button>
        </div>
      </Card>

      <section className="space-y-2">
        <h2 className="text-sm font-semibold text-muted-foreground">Os meus estudos ({studies.length})</h2>
        {studies.length === 0 && <p className="text-sm text-muted-foreground">Nenhum estudo por agora.</p>}
        <div className="grid gap-2">
          {studies.map((s) => (
            <Card key={s.study_id} className="p-3 flex items-center justify-between hover:border-slate-400 transition-colors"
              data-testid={`structuro-study-${s.study_id}`}>
              <button className="text-left flex-1" onClick={() => open(s.study_id)}>
                <div className="font-medium">{s.title}</div>
                <div className="text-xs text-muted-foreground">
                  rev. {s.revision} · {LEVEL_LABEL[s.output_level] || s.output_level} · {LIFECYCLE_LABEL[s.lifecycle] || s.lifecycle}
                </div>
              </button>
              <Button size="icon" variant="ghost" onClick={() => removeStudy(s.study_id)}
                data-testid={`structuro-delete-${s.study_id}`}>
                <Trash2 className="h-4 w-4 text-muted-foreground" />
              </Button>
            </Card>
          ))}
        </div>
      </section>
    </div>
  );
}

const SOURCE_OPTS = [
  { v: "mesure", l: "Medição / levantamento cotado" },
  { v: "document", l: "Documento / planta verificado" },
  { v: "essai", l: "Ensaio / sondagem" },
  { v: "observation", l: "Observação no local" },
  { v: "declaration", l: "Declaração (a confirmar)" },
  { v: "inconnu", l: "Não sei" },
];

function StudyDetail({ study, setStudy, onBack }) {
  const [answers, setAnswers] = useState({});
  const [approveOpen, setApproveOpen] = useState(false);
  const [form, setForm] = useState({ role: "", scope: "", reservations: "" });
  const [newLevel, setNewLevel] = useState({ name: "", elevation_m: "" });
  const [newEl, setNewEl] = useState({ type: "mur_porteur", ref: "", label: "", level: "" });
  const [lintel, setLintel] = useState({ permanent_line_kn_m: 0, variable_line_kn_m: 0, material: "both", masonry_unit_weight_kn_m3: 20, load_model: "arching" });
  const [lintelBusy, setLintelBusy] = useState(false);
  const s = study;

  const setA = (qid, patch) => setAnswers((p) => ({ ...p, [qid]: { ...(p[qid] || {}), ...patch } }));

  const submit = async (q) => {
    const a = answers[q.id] || {};
    const source = a.source || (q.requires_essai ? "essai" : "mesure");
    const body = { datum_key: q.datum_key, source,
      value: source === "inconnu" ? null : (a.value ?? null), unit: a.unit || null };
    try {
      const { data } = await api.post(`/structuro/studies/${s.study_id}/answer`, body);
      data.meta = s.meta; setStudy(data);
      toast.success(source === "inconnu" ? "Dado marcado como desconhecido (resultados dependentes desatualizados)" : "Dado guardado");
    } catch (e) { toast.error(e?.response?.data?.detail || "Falha"); }
  };

  const downloadSheets = async () => {
    try {
      const res = await api.get(`/structuro/studies/${s.study_id}/sheets.pdf`, { responseType: "blob" });
      const url = URL.createObjectURL(res.data);
      const a = document.createElement("a");
      a.href = url; a.download = `structuro-${s.study_id}-esquisses.pdf`; a.click();
      URL.revokeObjectURL(url);
      toast.success("Folhas de estudo (esboços) transferidas");
    } catch { toast.error("Geração das folhas impossível"); }
  };

  const downloadNote = async () => {
    try {
      const res = await api.get(`/structuro/studies/${s.study_id}/note.pdf`, { responseType: "blob" });
      const url = URL.createObjectURL(res.data);
      const a = document.createElement("a");
      a.href = url; a.download = `structuro-${s.study_id}-note.pdf`; a.click();
      URL.revokeObjectURL(url);
      toast.success("Nota de estudo preliminar transferida");
    } catch { toast.error("Geração da nota impossível"); }
  };

  const applyUpdate = (data) => { data.meta = s.meta; setStudy(data); };

  const computeLintel = async () => {
    setLintelBusy(true);
    try {
      const { data } = await api.post(`/structuro/studies/${s.study_id}/lintel`, lintel);
      applyUpdate(data);
      toast.success("Padieira dimensionada (indicativo) — visível na nota");
    } catch (e) { toast.error(e?.response?.data?.detail || "Cálculo impossível — documente o vão da abertura"); }
    finally { setLintelBusy(false); }
  };

  const addLevel = async () => {
    if (!newLevel.name.trim()) { toast.error("Nome do piso obrigatório"); return; }
    try {
      const body = { name: newLevel.name.trim(),
        elevation_m: newLevel.elevation_m === "" ? null : parseFloat(newLevel.elevation_m) };
      const { data } = await api.post(`/structuro/studies/${s.study_id}/levels`, body);
      applyUpdate(data); setNewLevel({ name: "", elevation_m: "" });
      toast.success("Piso adicionado");
    } catch (e) { toast.error(e?.response?.data?.detail || "Falha"); }
  };
  const patchLevel = async (lvl, patch) => {
    try {
      const { data } = await api.patch(`/structuro/studies/${s.study_id}/levels/${lvl.id}`, patch);
      applyUpdate(data);
    } catch { toast.error("Falha na atualização do piso"); }
  };
  const deleteLevel = async (lvl) => {
    try {
      const { data } = await api.delete(`/structuro/studies/${s.study_id}/levels/${lvl.id}`);
      applyUpdate(data);
    } catch { toast.error("Não foi possível eliminar"); }
  };
  const addElement = async () => {
    if (!newEl.type) { toast.error("Tipo de elemento obrigatório"); return; }
    try {
      const { data } = await api.post(`/structuro/studies/${s.study_id}/elements`, {
        type: newEl.type, ref: newEl.ref.trim() || null,
        label: newEl.label.trim() || null, level: newEl.level.trim() || null });
      applyUpdate(data); setNewEl({ type: "mur_porteur", ref: "", label: "", level: "" });
      toast.success("Elemento adicionado");
    } catch (e) { toast.error(e?.response?.data?.detail || "Falha"); }
  };
  const patchElement = async (el, patch) => {
    try {
      const { data } = await api.patch(`/structuro/studies/${s.study_id}/elements/${el.id}`, patch);
      applyUpdate(data);
    } catch { toast.error("Falha na atualização do elemento"); }
  };
  const deleteElement = async (el) => {
    try {
      const { data } = await api.delete(`/structuro/studies/${s.study_id}/elements/${el.id}`);
      applyUpdate(data);
    } catch { toast.error("Não foi possível eliminar"); }
  };
  const elementTypes = s.meta?.element_types || [];

  const [plan, setPlan] = useState({ file: null, level: "", kind: "existant", scale_note: "" });
  const [uploading, setUploading] = useState(false);
  const uploadPlan = async () => {
    if (!plan.file) { toast.error("Escolha um ficheiro (PDF, DXF, imagem)"); return; }
    const fd = new FormData();
    fd.append("file", plan.file);
    fd.append("level", plan.level); fd.append("kind", plan.kind); fd.append("scale_note", plan.scale_note);
    setUploading(true);
    try {
      const { data } = await api.post(`/structuro/studies/${s.study_id}/plans`, fd,
        { headers: { "Content-Type": "multipart/form-data" } });
      data.meta = s.meta; setStudy(data);
      setPlan({ file: null, level: "", kind: "existant", scale_note: "" });
      toast.success("Planta importada e guardada");
    } catch (e) { toast.error(e?.response?.data?.detail || "Não foi possível importar"); }
    finally { setUploading(false); }
  };
  const downloadPlan = async (p) => {
    try {
      const res = await api.get(`/structuro/studies/${s.study_id}/plans/${p.id}/file`, { responseType: "blob" });
      const url = URL.createObjectURL(res.data);
      const a = document.createElement("a"); a.href = url; a.download = p.original_filename || "plan"; a.click();
      URL.revokeObjectURL(url);
    } catch { toast.error("Transferência impossível"); }
  };
  const setPlanLevel = async (p, level) => {
    try {
      const { data } = await api.patch(`/structuro/studies/${s.study_id}/plans/${p.id}`, { level });
      data.meta = s.meta; setStudy(data); toast.success("Piso reatribuído (reajuste)");
    } catch { toast.error("Falha"); }
  };
  const deletePlan = async (p) => {
    try {
      const { data } = await api.delete(`/structuro/studies/${s.study_id}/plans/${p.id}`);
      data.meta = s.meta; setStudy(data);
    } catch { toast.error("Não foi possível eliminar"); }
  };
  const activePlans = (s.plans || []).filter((p) => !p.is_deleted);

  const doApprove = async () => {
    if (!form.role.trim()) { toast.error("Indique a sua função"); return; }
    try {
      const { data } = await api.post(`/structuro/studies/${s.study_id}/approve`, {
        role: form.role.trim(), scope: form.scope.trim(), reservations: form.reservations.trim() || null });
      data.meta = s.meta; setStudy(data); setApproveOpen(false);
      setForm({ role: "", scope: "", reservations: "" });
      toast.success("Estudo preliminar aprovado (não válido para execução)");
    } catch (e) { toast.error(e?.response?.data?.detail || "Aprovação impossível"); }
  };

  const blockedCount = (s.verifications || []).filter((v) => v.status === "bloquee").length;

  return (
    <div className="max-w-5xl mx-auto px-4 py-8 space-y-6" data-testid="structuro-detail">
      <button onClick={onBack} className="text-sm text-muted-foreground flex items-center gap-1 hover:text-foreground">
        <ArrowLeft className="h-4 w-4" /> Voltar aos estudos
      </button>

      <header className="space-y-2">
        <h1 className="text-2xl font-bold">{s.title}</h1>
        <div className="flex flex-wrap items-center gap-2 text-xs">
          <Badge variant="outline">Revisão {s.revision}</Badge>
          <Badge variant="outline">Piso: {LEVEL_LABEL[s.output_level] || s.output_level}</Badge>
          <Badge variant="outline">Ciclo: {LIFECYCLE_LABEL[s.lifecycle] || s.lifecycle}</Badge>
          {s.ai_engine && <Badge variant="outline">Lecture IA : {s.ai_engine}</Badge>}
        </div>
      </header>

      <div className="flex flex-wrap gap-2">
        <Button size="sm" variant="outline" onClick={downloadSheets} className="gap-1" data-testid="structuro-sheets-btn">
          <FileDown className="h-4 w-4" /> Folhas de estudo EXI/STR (PDF)
        </Button>
        <Button size="sm" variant="outline" onClick={downloadNote} className="gap-1" data-testid="structuro-note-btn">
          <FileText className="h-4 w-4" /> Nota de estudo (PDF)
        </Button>
      </div>

      <div className="rounded-md border border-slate-300 bg-slate-50 p-3 text-xs text-slate-600 flex gap-2" data-testid="structuro-calc-lock">
        <Lock className="h-4 w-4 shrink-0 mt-0.5" />
        <span>Motor de verificação Eurocódigos <b>indisponível</b> ({s.meta?.rulepack?.note}). Nenhuma secção, carga ou resistência é produzida.</span>
      </div>

      {/* Linteau — dé-verrouillage par le moteur BET déterministe */}
      <Card className="p-4 space-y-3" data-testid="structuro-lintel-card">
        <h2 className="text-sm font-semibold flex items-center gap-1"><Ruler className="h-4 w-4" /> Dimensionamento indicativo da padieira (NP EN 1992/1993)</h2>
        <p className="text-xs text-muted-foreground">Cálculo determinístico da viga de reforço acima da abertura (vão e espessura da parede retomados dos dados documentados). Propõe aço e/ou betão armado, a solução mais económica, flecha e apoio na alvenaria. <b>Indicativo, não executório.</b></p>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-xs">
          <label className="block">Cargas permanentes G (kN/m)<input type="number" step="any" className="border rounded-md p-2 bg-background w-full mt-1" value={lintel.permanent_line_kn_m} onChange={e => setLintel({ ...lintel, permanent_line_kn_m: Number(e.target.value) })} data-testid="structuro-lintel-perm" /></label>
          <label className="block">Sobrecargas Q (kN/m)<input type="number" step="any" className="border rounded-md p-2 bg-background w-full mt-1" value={lintel.variable_line_kn_m} onChange={e => setLintel({ ...lintel, variable_line_kn_m: Number(e.target.value) })} data-testid="structuro-lintel-var" /></label>
          <label className="block">Peso da alvenaria (kN/m³)<input type="number" step="any" className="border rounded-md p-2 bg-background w-full mt-1" value={lintel.masonry_unit_weight_kn_m3} onChange={e => setLintel({ ...lintel, masonry_unit_weight_kn_m3: Number(e.target.value) })} /></label>
          <label className="block">Material<select className="border rounded-md p-2 bg-background w-full mt-1" value={lintel.material} onChange={e => setLintel({ ...lintel, material: e.target.value })} data-testid="structuro-lintel-material"><option value="both">Aço + betão</option><option value="steel">Aço</option><option value="rc">Betão armado</option></select></label>
        </div>
        <Button size="sm" onClick={computeLintel} disabled={lintelBusy} data-testid="structuro-lintel-btn" className="gap-1"><Calculator className="h-4 w-4" />{lintelBusy ? "Cálculo…" : "Calcular a padieira"}</Button>
        {s.lintel?.result && <div className="text-xs border-t pt-2 space-y-1" data-testid="structuro-lintel-result">
          <p>Âmbito {s.lintel.result.clear_span_m} m · modelo « {s.lintel.result.load_model} » · M_Ed {s.lintel.result.actions.m_ed_knm} kN·m · V_Ed {s.lintel.result.actions.v_ed_kn} kN</p>
          {s.lintel.result.steel?.status === "ok" && <p>Aço: <b>{s.lintel.result.steel.label}</b> — {s.lintel.result.steel.cost_eur} € ({s.lintel.result.steel.mass_kg} kg)</p>}
          {s.lintel.result.rc?.status === "ok" && <p>Betão armado: <b>{s.lintel.result.rc.label}</b> — {s.lintel.result.rc.cost_eur} €</p>}
          {s.lintel.result.recommendation && <p className="text-emerald-800 font-medium">Mais económico: {s.lintel.result.recommendation.material === "steel" ? "Aço" : "Betão armado"} — {s.lintel.result.recommendation.label} ({s.lintel.result.recommendation.cost_eur} €)</p>}
          <p className={s.lintel.result.bearing.status === "ok" ? "text-emerald-700" : "text-red-700"}>Apoio na alvenaria: {s.lintel.result.bearing.sigma_kpa} ≤ {s.lintel.result.bearing.allow_kpa} kPa → {s.lintel.result.bearing.status === "ok" ? "OK" : "A REVER"}</p>
        </div>}
      </Card>

      {/* Faits déclarés */}
      <Card className="p-4 space-y-2">
        <h2 className="text-sm font-semibold flex items-center gap-1"><Ruler className="h-4 w-4" /> Factos declarados (a confirmar)</h2>
        <ul className="text-sm space-y-1">
          {(s.facts || []).map((f) => (
            <li key={f.id} className="flex items-start gap-2" data-testid={`structuro-fact-${f.id}`}>
              <span className="text-muted-foreground">•</span>{f.text}
              <Badge variant="outline" className="text-[10px]">{SOURCE_LABEL[f.source] || f.source}</Badge>
            </li>
          ))}
          {(!s.facts || s.facts.length === 0) && <li className="text-muted-foreground">Nenhum facto extraído.</li>}
        </ul>
      </Card>

      {/* Éditeur niveaux & éléments porteurs */}
      <Card className="p-4 space-y-4" data-testid="structuro-editor-card">
        <h2 className="text-sm font-semibold flex items-center gap-1"><Building2 className="h-4 w-4" /> Pisos & elementos estruturais</h2>

        {/* Niveaux */}
        <div className="space-y-2">
          <div className="text-xs font-semibold text-muted-foreground">Pisos ({(s.levels || []).length})</div>
          <div className="grid gap-2">
            {(s.levels || []).map((lv) => (
              <div key={lv.id} className="flex flex-wrap items-center gap-2 border border-border rounded-md p-2" data-testid={`structuro-level-${lv.id}`}>
                <Input className="h-8 w-44 text-xs" defaultValue={lv.name}
                  onBlur={(e) => { if (e.target.value.trim() && e.target.value !== lv.name) patchLevel(lv, { name: e.target.value.trim() }); }}
                  data-testid={`structuro-level-name-${lv.id}`} />
                <div className="flex items-center gap-1">
                  <Input className="h-8 w-24 text-xs" type="number" step="0.01"
                    defaultValue={(lv.elevation_m?.value ?? "")}
                    placeholder="±0.00"
                    onBlur={(e) => { const v = e.target.value; if (v !== "" && parseFloat(v) !== (lv.elevation_m?.value ?? null)) patchLevel(lv, { elevation_m: parseFloat(v) }); }}
                    data-testid={`structuro-level-elev-${lv.id}`} />
                  <span className="text-[11px] text-muted-foreground">m</span>
                  {lv.elevation_m?.source && lv.elevation_m.source !== "inconnu" && (
                    <Badge variant="outline" className="text-[10px]">{SOURCE_LABEL[lv.elevation_m.source] || lv.elevation_m.source}</Badge>
                  )}
                </div>
                <Button size="icon" variant="ghost" className="h-7 w-7 ml-auto" onClick={() => deleteLevel(lv)} data-testid={`structuro-level-delete-${lv.id}`}>
                  <Trash2 className="h-3.5 w-3.5 text-muted-foreground" />
                </Button>
              </div>
            ))}
            {(s.levels || []).length === 0 && <p className="text-xs text-muted-foreground">Nenhum piso definido.</p>}
          </div>
          <div className="flex flex-wrap items-end gap-2">
            <Input className="h-8 w-44 text-xs" placeholder="Nome (ex.: Rés do chão)"
              value={newLevel.name} onChange={(e) => setNewLevel((p) => ({ ...p, name: e.target.value }))}
              data-testid="structuro-newlevel-name" />
            <Input className="h-8 w-24 text-xs" type="number" step="0.01" placeholder="cota (m)"
              value={newLevel.elevation_m} onChange={(e) => setNewLevel((p) => ({ ...p, elevation_m: e.target.value }))}
              data-testid="structuro-newlevel-elev" />
            <Button size="sm" className="h-8 gap-1" onClick={addLevel} data-testid="structuro-newlevel-add">
              <Plus className="h-4 w-4" /> Adicionar um piso
            </Button>
          </div>
        </div>

        {/* Éléments */}
        <div className="space-y-2 pt-2 border-t border-border">
          <div className="text-xs font-semibold text-muted-foreground">Elementos estruturais ({(s.elements || []).length})</div>
          <div className="grid gap-2">
            {(s.elements || []).map((el) => (
              <div key={el.id} className="flex flex-wrap items-center gap-2 border border-border rounded-md p-2" data-testid={`structuro-element-${el.id}`}>
                <Input className="h-8 w-16 text-xs" defaultValue={el.ref || ""} placeholder="ref."
                  onBlur={(e) => { if (e.target.value !== (el.ref || "")) patchElement(el, { ref: e.target.value }); }}
                  data-testid={`structuro-element-ref-${el.id}`} />
                <select className="h-8 text-xs border border-border rounded-sm px-2" value={el.type}
                  onChange={(e) => patchElement(el, { type: e.target.value })}
                  data-testid={`structuro-element-type-${el.id}`}>
                  {elementTypes.map((t) => <option key={t} value={t}>{ELEMENT_LABEL[t] || t}</option>)}
                </select>
                <Input className="h-8 flex-1 min-w-[140px] text-xs" defaultValue={el.label || ""} placeholder="designação"
                  onBlur={(e) => { if (e.target.value !== (el.label || "")) patchElement(el, { label: e.target.value }); }}
                  data-testid={`structuro-element-label-${el.id}`} />
                <Input className="h-8 w-32 text-xs" defaultValue={el.level || ""} placeholder="piso"
                  onBlur={(e) => { if (e.target.value !== (el.level || "")) patchElement(el, { level: e.target.value }); }}
                  data-testid={`structuro-element-level-${el.id}`} />
                <Button size="icon" variant="ghost" className="h-7 w-7" onClick={() => deleteElement(el)} data-testid={`structuro-element-delete-${el.id}`}>
                  <Trash2 className="h-3.5 w-3.5 text-muted-foreground" />
                </Button>
              </div>
            ))}
            {(s.elements || []).length === 0 && <p className="text-xs text-muted-foreground">Nenhum elemento.</p>}
          </div>
          <div className="flex flex-wrap items-end gap-2">
            <select className="h-8 text-xs border border-border rounded-sm px-2" value={newEl.type}
              onChange={(e) => setNewEl((p) => ({ ...p, type: e.target.value }))} data-testid="structuro-newel-type">
              {elementTypes.map((t) => <option key={t} value={t}>{ELEMENT_LABEL[t] || t}</option>)}
            </select>
            <Input className="h-8 w-16 text-xs" placeholder="ref." value={newEl.ref}
              onChange={(e) => setNewEl((p) => ({ ...p, ref: e.target.value }))} data-testid="structuro-newel-ref" />
            <Input className="h-8 w-48 text-xs" placeholder="designação" value={newEl.label}
              onChange={(e) => setNewEl((p) => ({ ...p, label: e.target.value }))} data-testid="structuro-newel-label" />
            <Input className="h-8 w-28 text-xs" placeholder="piso" value={newEl.level}
              onChange={(e) => setNewEl((p) => ({ ...p, level: e.target.value }))} data-testid="structuro-newel-level" />
            <Button size="sm" className="h-8 gap-1" onClick={addElement} data-testid="structuro-newel-add">
              <Plus className="h-4 w-4" /> Adicionar um elemento
            </Button>
          </div>
        </div>
      </Card>

      {/* Couverture des vérifications */}
      <Card className="p-4 space-y-2">
        <h2 className="text-sm font-semibold">Cobertura das verificações</h2>
        <div className="grid gap-2">
          {(s.verifications || []).map((v) => {
            const st = VERIF_STYLE[v.status] || VERIF_STYLE.non_calculee;
            const Icon = st.Icon;
            return (
              <div key={v.key} className="border border-border rounded-md p-2" data-testid={`structuro-verif-${v.key}`}>
                <div className="flex items-center justify-between">
                  <span className="text-sm font-medium">{v.label}</span>
                  <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-sm text-[11px] font-semibold ${st.cls}`}>
                    <Icon className="h-3.5 w-3.5" /> {st.label}
                  </span>
                </div>
                {v.missing_inputs?.length > 0 && (
                  <div className="text-[11px] text-red-600 mt-1">Em falta: {v.missing_inputs.map((k) => MISSING_LABEL[k] || k).join(", ")}</div>
                )}
              </div>
            );
          })}
        </div>
      </Card>

      {/* Questionnaire adaptatif */}
      <Card className="p-4 space-y-3">
        <h2 className="text-sm font-semibold flex items-center gap-1"><HelpCircle className="h-4 w-4" /> Perguntas a documentar ({(s.questionnaire || []).length})</h2>
        {(s.questionnaire || []).length === 0 && (
          <p className="text-sm text-emerald-600 flex items-center gap-1"><CheckCircle2 className="h-4 w-4" /> Todos os dados críticos estão documentados.</p>
        )}
        <div className="space-y-3">
          {(s.questionnaire || []).map((q) => (
            <div key={q.id} className="border border-border rounded-md p-3 space-y-2" data-testid={`structuro-question-${q.datum_key}`}>
              <div className="text-sm font-medium flex items-center gap-2">
                {q.question}
                {q.requires_essai && <Badge className="bg-amber-100 text-amber-800 text-[10px]"><FlaskConical className="h-3 w-3 mr-1" />ensaio necessário</Badge>}
              </div>
              <div className="text-[11px] text-muted-foreground">Desbloqueia: {q.blocks.join(", ")} — {q.how_to_document}</div>
              <div className="flex flex-wrap gap-2 items-center">
                <Input className="h-8 w-40 text-xs" placeholder="valeur"
                  value={answers[q.id]?.value ?? ""} onChange={(e) => setA(q.id, { value: e.target.value })}
                  data-testid={`structuro-answer-value-${q.datum_key}`} />
                <Input className="h-8 w-20 text-xs" placeholder="unidade"
                  value={answers[q.id]?.unit ?? ""} onChange={(e) => setA(q.id, { unit: e.target.value })} />
                <select className="h-8 text-xs border border-border rounded-sm px-2"
                  value={answers[q.id]?.source ?? (q.requires_essai ? "essai" : "mesure")}
                  onChange={(e) => setA(q.id, { source: e.target.value })}
                  data-testid={`structuro-answer-source-${q.datum_key}`}>
                  {SOURCE_OPTS.map((o) => <option key={o.v} value={o.v}>{o.l}</option>)}
                </select>
                <Button size="sm" className="h-8" onClick={() => submit(q)} data-testid={`structuro-answer-submit-${q.datum_key}`}>
                  Guardar
                </Button>
              </div>
            </div>
          ))}
        </div>
      </Card>

      {/* Plans importés */}
      <Card className="p-4 space-y-3" data-testid="structuro-plans-card">
        <h2 className="text-sm font-semibold flex items-center gap-1"><Upload className="h-4 w-4" /> Plantas importadas ({activePlans.length})</h2>
        <p className="text-[11px] text-muted-foreground">
          PDF, DXF ou imagem. Os DXF dão um inventário de entidades (reconhecimento não verificado); os PDF/imagens são guardados como referência (ajuste a escala com uma cota conhecida). Atribua cada planta a um piso (reajuste).
        </p>
        <div className="flex flex-wrap items-end gap-2">
          <input type="file" accept=".pdf,.dxf,.dwg,.ifc,.png,.jpg,.jpeg,.webp"
            onChange={(e) => setPlan((p) => ({ ...p, file: e.target.files?.[0] || null }))}
            className="text-xs" data-testid="structuro-plan-file" />
          <Input className="h-8 w-36 text-xs" placeholder="Piso (ex.: R/C)"
            value={plan.level} onChange={(e) => setPlan((p) => ({ ...p, level: e.target.value }))}
            data-testid="structuro-plan-level" />
          <select className="h-8 text-xs border border-border rounded-sm px-2" value={plan.kind}
            onChange={(e) => setPlan((p) => ({ ...p, kind: e.target.value }))} data-testid="structuro-plan-kind">
            <option value="existant">Existente</option>
            <option value="projet">Projeto</option>
            <option value="bet">Dossier BET</option>
          </select>
          <Input className="h-8 w-40 text-xs" placeholder="Escala / cota de ref."
            value={plan.scale_note} onChange={(e) => setPlan((p) => ({ ...p, scale_note: e.target.value }))} />
          <Button size="sm" className="h-8 gap-1" onClick={uploadPlan} disabled={uploading} data-testid="structuro-plan-upload-btn">
            {uploading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Upload className="h-4 w-4" />} Importar
          </Button>
        </div>
        <div className="grid gap-2">
          {activePlans.map((p) => (
            <div key={p.id} className="border border-border rounded-md p-2 text-xs" data-testid={`structuro-plan-${p.id}`}>
              <div className="flex items-center justify-between gap-2">
                <button className="flex items-center gap-1 text-left font-medium hover:underline" onClick={() => downloadPlan(p)}>
                  <FileText className="h-3.5 w-3.5" /> {p.original_filename}
                </button>
                <div className="flex items-center gap-1">
                  <Badge variant="outline" className="text-[10px]">{p.kind}</Badge>
                  <Input className="h-6 w-28 text-[11px]" defaultValue={p.level || ""} placeholder="piso"
                    onBlur={(e) => { if (e.target.value !== (p.level || "")) setPlanLevel(p, e.target.value); }}
                    data-testid={`structuro-plan-level-${p.id}`} />
                  <Button size="icon" variant="ghost" className="h-6 w-6" onClick={() => deletePlan(p)} data-testid={`structuro-plan-delete-${p.id}`}>
                    <Trash2 className="h-3.5 w-3.5 text-muted-foreground" />
                  </Button>
                </div>
              </div>
              <div className="text-[10px] text-muted-foreground mt-1">
                {(p.size / 1024).toFixed(0)} KB · {p.recognition?.kind?.toUpperCase()}
                {p.recognition?.objects_detected && p.recognition?.summary?.entities_total != null
                  ? ` · ${p.recognition.summary.entities_total} entidades, ${p.recognition.summary.layers_count} calques` : ""}
                {p.scale_note ? ` · ${p.scale_note}` : ""}
              </div>
              <div className="text-[10px] text-amber-700 mt-0.5">{p.recognition?.note}</div>
            </div>
          ))}
          {activePlans.length === 0 && <p className="text-xs text-muted-foreground">Nenhuma planta importada.</p>}
        </div>
      </Card>

      {/* Approbation */}
      <Card className="p-4 space-y-2">
        <h2 className="text-sm font-semibold">Aprovação (estudo preliminar)</h2>
        {s.approvals?.length > 0 ? (
          <ul className="text-sm space-y-1">
            {s.approvals.map((a) => (
              <li key={a.id} className="flex items-center gap-2" data-testid={`structuro-approval-${a.id}`}>
                <CheckCircle2 className="h-4 w-4 text-emerald-600" />
                <span>{a.name} — {a.role} (rev. {a.revision})</span>
                <Badge variant="outline" className="text-[10px]">não válido para execução</Badge>
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-xs text-muted-foreground">
            {blockedCount > 0
              ? `Aprovação indisponível: ${blockedCount} verificação(ões) bloqueada(s) por dados em falta.`
              : "Dados suficientes para uma aprovação de estudo preliminar (nunca para execução)."}
          </p>
        )}
        <Button size="sm" variant="outline" disabled={blockedCount > 0} onClick={() => setApproveOpen(true)} data-testid="structuro-approve-btn">
          Aprovar o estudo preliminar
        </Button>
      </Card>

      <Dialog open={approveOpen} onOpenChange={setApproveOpen}>
        <DialogContent data-testid="structuro-approve-dialog">
          <DialogHeader>
            <DialogTitle>Aprovar o estudo preliminar</DialogTitle>
            <DialogDescription>
              Aprovação nominativa (revisão {s.revision}). <b>Não válido para execução</b> : a verificação estrutural por um engenheiro continua a ser obrigatória.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-3 py-1">
            <div className="space-y-1">
              <Label className="text-xs">A sua função *</Label>
              <Input value={form.role} onChange={(e) => setForm((f) => ({ ...f, role: e.target.value }))}
                placeholder="Ex.: Projetista, Chefe de projeto" data-testid="structuro-approve-role" />
            </div>
            <div className="space-y-1">
              <Label className="text-xs">Âmbito (opcional)</Label>
              <Input value={form.scope} onChange={(e) => setForm((f) => ({ ...f, scope: e.target.value }))}
                placeholder="Ex.: esboço abertura R/C" data-testid="structuro-approve-scope" />
            </div>
            <div className="space-y-1">
              <Label className="text-xs">Reservas (opcional)</Label>
              <Input value={form.reservations} onChange={(e) => setForm((f) => ({ ...f, reservations: e.target.value }))}
                placeholder="Ex.: sob reserva do levantamento cotado" data-testid="structuro-approve-reservations" />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setApproveOpen(false)}>Cancelar</Button>
            <Button onClick={doApprove} data-testid="structuro-approve-confirm">Aprovar</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
