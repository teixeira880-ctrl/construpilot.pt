import { useEffect, useRef, useState } from "react";
import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Label } from "@/components/ui/label";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import { toast } from "sonner";
import PromptBar from "@/components/PromptBar";
import {
  Upload, Loader2, FileDown, Save, Trash2, AlertTriangle, CheckCircle2,
  Ruler, Layers, Boxes, ArrowLeft, HardHat,
} from "lucide-react";

const TYPE_OPTIONS = [
  { v: "semelle_isolee", l: "Sapata isolada" },
  { v: "semelle_filante", l: "Sapata contínua" },
  { v: "longrine", l: "Longrine" },
  { v: "chainage", l: "Lintel de travamento" },
  { v: "poteau", l: "Pilar" },
];
const TYPE_LABEL = Object.fromEntries(TYPE_OPTIONS.map((t) => [t.v, t.l]));
const RATIO_TYPES = ["semelle_isolee", "semelle_filante", "longrine", "chainage", "poteau"];

const num = (v) => (v === "" || v === null || v === undefined ? null : Number(v));

export default function PlanReader() {
  const [reads, setReads] = useState([]);
  const [read, setRead] = useState(null);
  const [uploading, setUploading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [title, setTitle] = useState("");
  const [ratios, setRatios] = useState({});
  const fileRef = useRef(null);

  const loadList = () => api.get("/structuro/plan/list").then(({ data }) => setReads(data.reads || [])).catch(() => {});
  useEffect(() => { loadList(); }, []);

  const applyRead = (d) => {
    setRead(d);
    setTitle(d.title || "");
    const r = {};
    (d.steel_ratios_input || "").split(",").forEach((p) => {
      const [k, v] = p.split(":"); if (k && v) r[k.trim()] = v.trim();
    });
    setRatios(r);
  };

  const analyze = async (file) => {
    if (!file) return;
    if (!file.name.toLowerCase().endsWith(".pdf")) { toast.error("Forneça um PDF (de preferência vetorial)."); return; }
    setUploading(true);
    const fd = new FormData();
    fd.append("file", file);
    fd.append("title", title || file.name);
    try {
      const { data } = await api.post("/structuro/plan/read", fd, {
        headers: { "Content-Type": "multipart/form-data" }, timeout: 180000,
      });
      applyRead(data);
      loadList();
      toast.success(data.complete ? "Planta lida — medição completa." : "Planta lida — complete as cotas pedidas.");
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Leitura impossível");
    } finally { setUploading(false); if (fileRef.current) fileRef.current.value = ""; }
  };

  const open = async (id) => {
    try { const { data } = await api.get(`/structuro/plan/${id}`); applyRead(data); }
    catch { toast.error("Abertura impossível"); }
  };

  const remove = async (id) => {
    if (!window.confirm("Eliminar esta leitura?")) return;
    try { await api.delete(`/structuro/plan/${id}`); if (read?.read_id === id) setRead(null); loadList(); }
    catch { toast.error("Não foi possível eliminar"); }
  };

  const editFond = (i, field, value) => {
    setRead((r) => {
      const fondations = [...r.fondations];
      fondations[i] = { ...fondations[i], [field]: field === "nombre" ? (parseInt(value || "1", 10) || 1) : (["type", "repere"].includes(field) ? value : num(value)) };
      return { ...r, fondations };
    });
  };
  const editMur = (i, field, value) => {
    setRead((r) => {
      const murs = [...r.murs];
      murs[i] = { ...murs[i], [field]: ["materiau", "repere"].includes(field) ? value : num(value) };
      return { ...r, murs };
    });
  };
  const delFond = (i) => setRead((r) => ({ ...r, fondations: r.fondations.filter((_, k) => k !== i) }));
  const delMur = (i) => setRead((r) => ({ ...r, murs: r.murs.filter((_, k) => k !== i) }));
  // Pilotagem por prompt: acrescenta um elemento ditado/escrito («3 sapatas S1 de 80x80, altura 40 cm»), sempre «a verificar».
  const addFondFromPrompt = (data) => {
    const p = data?.params || {};
    if (!p.type) return;
    setRead((r) => ({ ...r, fondations: [...(r.fondations || []), {
      type: p.type, repere: p.repere || "", nombre: p.nombre || 1,
      longueur_m: p.longueur_m ?? null, largeur_m: p.largeur_m ?? null, hauteur_m: p.hauteur_m ?? null,
      a_verifier: true, confidence: 1,
    }] }));
    toast.success("Elemento acrescentado — verifique as cotas e depois «Recalcular / Guardar».");
  };
  const addFond = () => setRead((r) => ({ ...r, fondations: [...r.fondations, { type: "semelle_isolee", repere: "", nombre: 1, a_verifier: true, confidence: 1 }] }));

  const save = async () => {
    if (!read) return;
    setSaving(true);
    const steel_ratios = {};
    Object.entries(ratios).forEach(([k, v]) => { if (v !== "" && v != null) steel_ratios[k] = Number(v); });
    try {
      const { data } = await api.put(`/structuro/plan/${read.read_id}`, {
        title, fondations: read.fondations, murs: read.murs, steel_ratios,
      });
      applyRead(data);
      loadList();
      toast.success(data.complete ? "Guardado — medição completa." : "Guardado — ainda faltam cotas.");
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Não foi possível guardar");
    } finally { setSaving(false); }
  };

  const exportPdf = async () => {
    try {
      const res = await api.get(`/structuro/plan/${read.read_id}/pdf`, { responseType: "blob" });
      const url = URL.createObjectURL(res.data);
      const a = document.createElement("a");
      a.href = url; a.download = `medicao-${read.read_id}.pdf`; a.click();
      URL.revokeObjectURL(url);
    } catch { toast.error("Impossível exportar"); }
  };

  const m = read?.metre || {};

  return (
    <div className="max-w-6xl mx-auto px-4 py-8 space-y-6" data-testid="plan-reader-page">
      <div className="flex items-center gap-3">
        <a href="/structuro" className="text-muted-foreground hover:text-foreground" data-testid="back-structuro"><ArrowLeft className="h-5 w-5" /></a>
        <HardHat className="h-7 w-7 text-primary" />
        <div>
          <h1 className="text-2xl font-display font-bold">Leitura de planta — medição da estrutura</h1>
          <p className="text-sm text-muted-foreground">Sapatas, pilares, vigas de fundação, paredes resistentes. A IA lê, calcula o betão/aço e <b>pede</b> qualquer cota em falta (zero invenções).</p>
        </div>
      </div>

      {/* Upload */}
      <Card className="p-5 rounded-md space-y-3" data-testid="plan-upload-card">
        <div className="grid sm:grid-cols-[1fr_auto] gap-3 items-end">
          <div className="space-y-1.5">
            <Label className="text-xs">Título</Label>
            <Input value={title} onChange={(e) => setTitle(e.target.value)} placeholder="Ex.: Fundação moradia Sintra" className="rounded-sm h-10" data-testid="plan-title-input" />
          </div>
          <div>
            <input ref={fileRef} type="file" accept=".pdf" className="hidden" onChange={(e) => analyze(e.target.files?.[0])} data-testid="plan-file-input" />
            <Button className="rounded-sm gap-2 h-10" disabled={uploading} onClick={() => fileRef.current?.click()} data-testid="plan-analyze-btn">
              {uploading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Upload className="h-4 w-4" />}
              {uploading ? "Leitura do plano…" : "Analisar um PDF"}
            </Button>
          </div>
        </div>
        {uploading && <p className="text-xs text-muted-foreground">Leitura vetorial + Assistente Construção… ~30 a 60 s. Os PDF vetoriais (exportados do CAD) dão os melhores resultados.</p>}
      </Card>

      {read && (
        <div className="space-y-5" data-testid="plan-results">
          {/* Barre d'état */}
          <div className="flex flex-wrap items-center gap-2">
            <Badge variant="outline" className="rounded-sm">Escala {read.scale_detected || "?"}</Badge>
            <Badge variant="outline" className="rounded-sm">{read.vector ? "PDF vetorial" : "PDF image"}</Badge>
            {read.complete
              ? <Badge className="rounded-sm bg-emerald-600 gap-1" data-testid="plan-complete-badge"><CheckCircle2 className="h-3 w-3" /> Medição completa</Badge>
              : <Badge className="rounded-sm bg-amber-500 gap-1" data-testid="plan-incomplete-badge"><AlertTriangle className="h-3 w-3" /> Cotas a completar</Badge>}
            <div className="ml-auto flex gap-2">
              <Button variant="outline" size="sm" className="rounded-sm gap-1" onClick={exportPdf} data-testid="plan-export-btn"><FileDown className="h-4 w-4" /> Export PDF</Button>
              <Button size="sm" className="rounded-sm gap-1" onClick={save} disabled={saving} data-testid="plan-save-btn">{saving ? <Loader2 className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4" />} Recalcular / Guardar</Button>
            </div>
          </div>

          {/* Métré */}
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
            {[
              { icon: Boxes, label: "Betão total", value: `${m.beton_total_m3 ?? 0} m³` },
              { icon: Ruler, label: `Aço${m.acier_complet ? "" : " (incompleto)"}`, value: `${m.acier_total_kg ?? 0} kg` },
              { icon: Layers, label: "Sapatas", value: m.nb_semelles ?? 0 },
              { icon: Layers, label: "Pilares", value: m.nb_poteaux ?? 0 },
            ].map((c, i) => (
              <Card key={i} className="p-4 rounded-md" data-testid={`metre-card-${i}`}>
                <c.icon className="h-4 w-4 text-primary mb-1" />
                <div className="text-xl font-bold num">{c.value}</div>
                <div className="text-xs text-muted-foreground">{c.label}</div>
              </Card>
            ))}
          </div>

          {/* Déductions */}
          {(read.deductions || []).length > 0 && (
            <Card className="p-4 rounded-md bg-primary/5 border-primary/20">
              <div className="text-xs font-semibold text-primary mb-1">Deduções automáticas</div>
              {read.deductions.map((d, i) => <p key={i} className="text-xs text-foreground/80">➤ {d}</p>)}
            </Card>
          )}

          {/* Données manquantes */}
          {(read.missing_data || []).length > 0 && (
            <Card className="p-4 rounded-md border-amber-400 bg-amber-50" data-testid="plan-missing-data">
              <div className="flex items-center gap-2 text-amber-700 font-semibold text-sm mb-2"><AlertTriangle className="h-4 w-4" /> Informações a fornecer ({read.missing_data.length}) — a IA não adivinha</div>
              <ul className="space-y-1">
                {read.missing_data.map((q, i) => <li key={i} className="text-sm text-amber-900">• {q.question}</li>)}
              </ul>
            </Card>
          )}

          {/* Ratios d'acier */}
          <Card className="p-4 rounded-md space-y-2">
            <Label className="text-xs font-semibold">Rácios de aço por tipo (kg/m³) — introduza os seus valores para calcular a tonelagem</Label>
            <div className="grid grid-cols-2 sm:grid-cols-5 gap-2">
              {RATIO_TYPES.map((t) => (
                <div key={t} className="space-y-1">
                  <Label className="text-[10px] text-muted-foreground">{TYPE_LABEL[t]}</Label>
                  <Input type="number" value={ratios[t] || ""} onChange={(e) => setRatios((r) => ({ ...r, [t]: e.target.value }))} placeholder="kg/m³" className="rounded-sm h-9 text-sm" data-testid={`ratio-${t}`} />
                </div>
              ))}
            </div>
          </Card>

          {/* Fondations */}
          <Card className="p-4 rounded-md overflow-x-auto" data-testid="fondations-table">
            <div className="flex items-center justify-between mb-2">
              <h3 className="font-semibold text-sm">Elementos de fundação / estrutura</h3>
              <Button variant="outline" size="sm" className="rounded-sm" onClick={addFond} data-testid="add-fondation-btn">+ Linha</Button>
            </div>
            <PromptBar appKey="fundacao" onFill={addFondFromPrompt}
              placeholder="Acrescente um elemento: «3 sapatas isoladas S1 de 80x80 cm, altura 40 cm»"
              examples="Escreva ou dite: o elemento é acrescentado como «a verificar»." />
            <table className="w-full text-sm">
              <thead><tr className="text-left text-xs text-muted-foreground border-b">
                <th className="py-1 pr-2">Tipo</th><th className="pr-2">Referência</th><th className="pr-2">L (m)</th><th className="pr-2">l (m)</th><th className="pr-2">h (m)</th><th className="pr-2">Nb</th><th className="pr-2">Betão m³</th><th className="pr-2">Aço kg</th><th className="pr-2">Conf.</th><th></th>
              </tr></thead>
              <tbody>
                {(read.fondations || []).map((f, i) => (
                  <tr key={i} className="border-b last:border-0" data-testid={`fond-row-${i}`}>
                    <td className="py-1 pr-2 min-w-[120px]">
                      <Select value={f.type} onValueChange={(v) => editFond(i, "type", v)}>
                        <SelectTrigger className="h-8 rounded-sm text-xs"><SelectValue /></SelectTrigger>
                        <SelectContent>{TYPE_OPTIONS.map((o) => <SelectItem key={o.v} value={o.v}>{o.l}</SelectItem>)}</SelectContent>
                      </Select>
                    </td>
                    <td className="pr-2"><Input value={f.repere ?? ""} onChange={(e) => editFond(i, "repere", e.target.value)} className="h-8 rounded-sm text-xs w-24" /></td>
                    <td className="pr-2"><Input type="number" value={f.longueur_m ?? ""} onChange={(e) => editFond(i, "longueur_m", e.target.value)} className={`h-8 rounded-sm text-xs w-20 ${f.longueur_m == null ? "border-amber-400 bg-amber-50" : ""}`} /></td>
                    <td className="pr-2"><Input type="number" value={f.largeur_m ?? ""} onChange={(e) => editFond(i, "largeur_m", e.target.value)} className={`h-8 rounded-sm text-xs w-20 ${f.largeur_m == null ? "border-amber-400 bg-amber-50" : ""}`} /></td>
                    <td className="pr-2"><Input type="number" value={f.hauteur_m ?? ""} onChange={(e) => editFond(i, "hauteur_m", e.target.value)} className={`h-8 rounded-sm text-xs w-20 ${f.hauteur_m == null ? "border-amber-400 bg-amber-50" : ""}`} /></td>
                    <td className="pr-2"><Input type="number" value={f.nombre ?? 1} onChange={(e) => editFond(i, "nombre", e.target.value)} className="h-8 rounded-sm text-xs w-14" /></td>
                    <td className="pr-2 num text-xs">{f.volume_beton_m3 ?? "—"}</td>
                    <td className="pr-2 num text-xs">{f.armature?.total_kg ?? "—"}</td>
                    <td className="pr-2">{f.a_verifier ? <Badge variant="outline" className="rounded-sm text-[10px] border-amber-400 text-amber-600">⚠</Badge> : <Badge variant="outline" className="rounded-sm text-[10px] border-emerald-400 text-emerald-600">✓</Badge>}</td>
                    <td><button onClick={() => delFond(i)} className="text-red-500 hover:text-red-700" data-testid={`del-fond-${i}`}><Trash2 className="h-4 w-4" /></button></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </Card>

          {/* Murs */}
          {(read.murs || []).length > 0 && (
            <Card className="p-4 rounded-md overflow-x-auto" data-testid="murs-table">
              <h3 className="font-semibold text-sm mb-2">Muros de embasamento</h3>
              <table className="w-full text-sm">
                <thead><tr className="text-left text-xs text-muted-foreground border-b">
                  <th className="py-1 pr-2">Referência</th><th className="pr-2">Material</th><th className="pr-2">Espes. (m)</th><th className="pr-2">Long. (m)</th><th className="pr-2">Alt. (m)</th><th className="pr-2">Superfície m²</th><th></th>
                </tr></thead>
                <tbody>
                  {read.murs.map((w, i) => (
                    <tr key={i} className="border-b last:border-0" data-testid={`mur-row-${i}`}>
                      <td className="pr-2"><Input value={w.repere ?? ""} onChange={(e) => editMur(i, "repere", e.target.value)} className="h-8 rounded-sm text-xs w-20" /></td>
                      <td className="pr-2"><Input value={w.materiau ?? ""} onChange={(e) => editMur(i, "materiau", e.target.value)} className="h-8 rounded-sm text-xs w-40" /></td>
                      <td className="pr-2"><Input type="number" value={w.epaisseur_m ?? ""} onChange={(e) => editMur(i, "epaisseur_m", e.target.value)} className="h-8 rounded-sm text-xs w-20" /></td>
                      <td className="pr-2"><Input type="number" value={w.longueur_m ?? ""} onChange={(e) => editMur(i, "longueur_m", e.target.value)} className="h-8 rounded-sm text-xs w-20" /></td>
                      <td className="pr-2"><Input type="number" value={w.hauteur_m ?? ""} onChange={(e) => editMur(i, "hauteur_m", e.target.value)} className={`h-8 rounded-sm text-xs w-20 ${w.hauteur_deduite ? "border-primary/40 bg-primary/5" : ""}`} title={w.hauteur_deduite ? "Altura deduzida automaticamente" : ""} /></td>
                      <td className="pr-2 num text-xs">{w.surface_m2 ?? "—"}</td>
                      <td><button onClick={() => delMur(i)} className="text-red-500 hover:text-red-700"><Trash2 className="h-4 w-4" /></button></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </Card>
          )}
        </div>
      )}

      {/* Historique */}
      {reads.length > 0 && (
        <Card className="p-4 rounded-md" data-testid="plan-history">
          <h3 className="font-semibold text-sm mb-2">Leituras guardadas</h3>
          <div className="divide-y">
            {reads.map((r) => (
              <div key={r.read_id} className="flex items-center gap-2 py-2 text-sm">
                <button className="flex-1 text-left hover:text-primary" onClick={() => open(r.read_id)} data-testid={`open-read-${r.read_id}`}>
                  {r.title} <span className="text-muted-foreground text-xs">· {r.metre?.beton_total_m3 ?? 0} m³ · {r.complete ? "complet" : "a completar"}</span>
                </button>
                <button onClick={() => remove(r.read_id)} className="text-red-500 hover:text-red-700"><Trash2 className="h-4 w-4" /></button>
              </div>
            ))}
          </div>
        </Card>
      )}
    </div>
  );
}
