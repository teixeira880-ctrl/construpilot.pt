import { useEffect, useRef, useState } from "react";
import { api } from "@/lib/api";
import {
  Loader2, Plus, Trash2, Save, GraduationCap, Pencil, X, Check,
  Upload, FileUp, Eye, Layers, BarChart3,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import { toast } from "sonner";

const SCOPE_LABELS = {
  global: "Todos os módulos (global)",
  devis: "Orçamento / orçamentação",
  analyse: "Análise de problemas",
  coach: "Coach IA",
  plan: "Plantas / medições",
};

const EMPTY = { scope: "global", title: "", context: "", content: "", approved: true };

function ScopeSelect({ value, onChange, scopes, testid }) {
  return (
    <Select value={value} onValueChange={onChange}>
      <SelectTrigger className="rounded-sm h-9 text-sm" data-testid={testid}><SelectValue /></SelectTrigger>
      <SelectContent>
        {scopes.map((s) => <SelectItem key={s} value={s}>{SCOPE_LABELS[s] || s}</SelectItem>)}
      </SelectContent>
    </Select>
  );
}

export default function LearningPanel() {
  const [examples, setExamples] = useState([]);
  const [scopes, setScopes] = useState(["global", "devis", "analyse", "coach", "plan"]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [form, setForm] = useState(EMPTY);
  const [editId, setEditId] = useState(null);

  // Import en lot
  const [showImport, setShowImport] = useState(false);
  const [bulkScope, setBulkScope] = useState("devis");
  const [bulkText, setBulkText] = useState("");
  const [bulkBusy, setBulkBusy] = useState(false);
  const fileRef = useRef(null);

  // Aperçu du prompt
  const [previewScope, setPreviewScope] = useState("devis");
  const [previewText, setPreviewText] = useState(null);
  const [previewBusy, setPreviewBusy] = useState(false);

  const load = () => {
    setLoading(true);
    api.get("/admin/learning")
      .then(({ data }) => { setExamples(data.examples || []); setScopes(data.scopes || scopes); })
      .catch(() => toast.error("Não foi possível carregar"))
      .finally(() => setLoading(false));
  };
  useEffect(() => { load(); /* eslint-disable-next-line */ }, []);

  const resetForm = () => { setForm(EMPTY); setEditId(null); };

  const startEdit = (ex) => {
    setEditId(ex.id);
    setForm({ scope: ex.scope, title: ex.title || "", context: ex.context || "", content: ex.content || "", approved: ex.approved });
    window.scrollTo({ top: 0, behavior: "smooth" });
  };

  const save = async () => {
    if (!form.content.trim()) { toast.error("O conteúdo do exemplo é obrigatório"); return; }
    setBusy(true);
    try {
      if (editId) {
        await api.put(`/admin/learning/${editId}`, form);
        toast.success("Exemplo atualizado — aplicado às próximas gerações IA.");
      } else {
        await api.post("/admin/learning", form);
        toast.success("Exemplo adicionado — a IA vai inspirar-se nele a partir de agora.");
      }
      resetForm();
      load();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Não foi possível guardar");
    } finally { setBusy(false); }
  };

  const toggleApproved = async (ex) => {
    try {
      await api.put(`/admin/learning/${ex.id}`, { approved: !ex.approved });
      setExamples((xs) => xs.map((x) => x.id === ex.id ? { ...x, approved: !ex.approved } : x));
    } catch { toast.error("Não foi possível atualizar"); }
  };

  const remove = async (ex) => {
    if (!window.confirm("Eliminar este exemplo de referência?")) return;
    try {
      await api.delete(`/admin/learning/${ex.id}`);
      setExamples((xs) => xs.filter((x) => x.id !== ex.id));
      if (editId === ex.id) resetForm();
      toast.success("Exemplo eliminado");
    } catch { toast.error("Não foi possível eliminar"); }
  };

  // Import en lot (colle plusieurs exemples séparés par une ligne ---)
  const runBulkPaste = async () => {
    const blocks = bulkText.split(/\n-{3,}\n/).map((b) => b.trim()).filter(Boolean);
    if (!blocks.length) { toast.error("Cole pelo menos um exemplo (separados por uma linha «---»)."); return; }
    const items = blocks.map((b) => {
      const nl = b.indexOf("\n");
      const first = (nl === -1 ? b : b.slice(0, nl)).trim();
      const title = first.length <= 120 ? first : "";
      return { title, content: b };
    });
    setBulkBusy(true);
    try {
      const { data } = await api.post("/admin/learning/bulk", { scope: bulkScope, approved: true, items });
      toast.success(`${data.created}exemplo(s) importado(s).`);
      setBulkText("");
      load();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Não foi possível importar");
    } finally { setBulkBusy(false); }
  };

  const runFileImport = async (ev) => {
    const files = Array.from(ev.target.files || []);
    if (!files.length) return;
    setBulkBusy(true);
    let ok = 0;
    for (const f of files) {
      const fd = new FormData();
      fd.append("file", f);
      try {
        await api.post(`/admin/learning/import-file?scope=${bulkScope}`, fd, { headers: { "Content-Type": "multipart/form-data" } });
        ok += 1;
      } catch (e) {
        toast.error(`${f.name} : ${e?.response?.data?.detail || "importação impossível"}`);
      }
    }
    setBulkBusy(false);
    if (fileRef.current) fileRef.current.value = "";
    if (ok) { toast.success(`${ok}ficheiro(s) importado(s) como exemplo(s).`); load(); }
  };

  const loadPreview = async (scope) => {
    setPreviewScope(scope);
    setPreviewBusy(true);
    try {
      const { data } = await api.get(`/admin/learning/preview?scope=${scope}`);
      setPreviewText(data.empty ? "" : data.preview);
    } catch { toast.error("Pré-visualização impossível"); }
    finally { setPreviewBusy(false); }
  };

  const fmtDate = (d) => d ? new Date(d).toLocaleDateString("fr-FR", { day: "2-digit", month: "short", year: "2-digit" }) : "—";

  return (
    <div className="space-y-5" data-testid="admin-learning-panel">
      <div className="flex items-start gap-3">
        <GraduationCap className="h-6 w-6 text-primary mt-0.5" />
        <div className="flex-1">
          <h3 className="font-display font-bold text-lg">Aprendizagem IA — exemplos de referência</h3>
          <p className="text-sm text-muted-foreground max-w-3xl">
            Adicione exemplos validados (orçamentos bem-sucedidos, análises de problemas, instruções de método). Os exemplos <b>aprovados</b> são injetados como referências em todos os módulos IA (orçamentos, análises, coach, plantas) para que o assistente produza com o mesmo nível de qualidade. Os preços e as quantidades continuam calculados pelo motor determinístico.
          </p>
        </div>
        <Button variant="outline" size="sm" className="rounded-sm gap-2 shrink-0" onClick={() => setShowImport((v) => !v)} data-testid="learning-toggle-import">
          <Layers className="h-4 w-4" /> Importer en lot
        </Button>
      </div>

      {/* Import en lot (paste + fichiers) */}
      {showImport && (
        <div className="surface rounded-md p-5 space-y-4 border border-primary/30" data-testid="learning-import">
          <div className="flex flex-wrap items-end gap-4">
            <div className="space-y-1.5 w-full sm:w-72">
              <Label className="text-xs">Módulo dos exemplos importados</Label>
              <ScopeSelect value={bulkScope} onChange={setBulkScope} scopes={scopes} testid="learning-bulk-scope" />
            </div>
            <div className="flex-1" />
            <input ref={fileRef} type="file" multiple accept=".pdf,.xlsx,.xls,.csv,.docx,.txt" className="hidden" onChange={runFileImport} data-testid="learning-file-input" />
            <Button variant="outline" size="sm" className="rounded-sm gap-2" disabled={bulkBusy} onClick={() => fileRef.current?.click()} data-testid="learning-file-btn">
              {bulkBusy ? <Loader2 className="h-4 w-4 animate-spin" /> : <FileUp className="h-4 w-4" />} Importar ficheiros (PDF, Excel…)
            </Button>
          </div>
          <div className="space-y-1.5">
            <Label className="text-xs">Colar vários exemplos — separe cada exemplo por uma linha «---»</Label>
            <Textarea value={bulkText} onChange={(e) => setBulkText(e.target.value)} rows={8}
                      placeholder={"Orçamento exemplo 1… --- Orçamento exemplo 2… --- Análise exemplo 3…"}
                      className="rounded-sm text-sm font-mono resize-y" data-testid="learning-bulk-text" />
            <div className="flex justify-end">
              <Button variant="default" size="sm" className="rounded-sm gap-2" disabled={bulkBusy} onClick={runBulkPaste} data-testid="learning-bulk-save">
                {bulkBusy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Upload className="h-4 w-4" />} Importar o texto colado
              </Button>
            </div>
          </div>
        </div>
      )}

      {/* Formulaire ajout / édition */}
      <div className="surface rounded-md p-5 space-y-4" data-testid="learning-form">
        <div className="flex items-center justify-between">
          <h4 className="font-semibold text-sm">{editId ? "Editar o exemplo" : "Nouvel exemple"}</h4>
          {editId && (
            <Button variant="ghost" size="sm" className="rounded-sm gap-1" onClick={resetForm} data-testid="learning-cancel-edit">
              <X className="h-4 w-4" /> Cancelar
            </Button>
          )}
        </div>
        <div className="grid sm:grid-cols-2 gap-4">
          <div className="space-y-1.5">
            <Label className="text-xs">Módulo em causa</Label>
            <ScopeSelect value={form.scope} onChange={(v) => setForm({ ...form, scope: v })} scopes={scopes} testid="learning-scope-select" />
          </div>
          <div className="space-y-1.5">
            <Label className="text-xs">Titre (court)</Label>
            <Input value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })}
                   placeholder="Ex.: Orçamento remodelação casa de banho 6 m²" className="rounded-sm h-9 text-sm"
                   data-testid="learning-title-input" />
          </div>
        </div>
        <div className="space-y-1.5">
          <Label className="text-xs">Situação / pedido (opcional — o contexto de partida)</Label>
          <Textarea value={form.context} onChange={(e) => setForm({ ...form, context: e.target.value })} rows={3}
                    placeholder="Ex.: O cliente descreve: «remodelar a minha casa de banho, substituir a banheira por um duche de nível»…"
                    className="rounded-sm text-sm resize-y" data-testid="learning-context-input" />
        </div>
        <div className="space-y-1.5">
          <Label className="text-xs">Resposta / método de referência (o que a IA deve reproduzir em qualidade)</Label>
          <Textarea value={form.content} onChange={(e) => setForm({ ...form, content: e.target.value })} rows={8}
                    placeholder="Cole aqui um orçamento exemplar, uma análise detalhada ou as suas instruções de estilo/método…"
                    className="rounded-sm text-sm resize-y" data-testid="learning-content-input" />
        </div>
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex items-center gap-2">
            <Switch checked={form.approved} onCheckedChange={(v) => setForm({ ...form, approved: v })} data-testid="learning-approved-switch" />
            <Label className="text-sm">Aprovado (utilizado pela IA)</Label>
          </div>
          <Button variant="default" size="sm" className="rounded-sm gap-2" onClick={save} disabled={busy} data-testid="learning-save-btn">
            {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : (editId ? <Save className="h-4 w-4" /> : <Plus className="h-4 w-4" />)}
            {editId ? "Guardar" : "Adicionar"}
          </Button>
        </div>
      </div>

      {/* Aperçu du prompt injecté */}
      <div className="surface rounded-md p-5 space-y-3" data-testid="learning-preview">
        <div className="flex flex-wrap items-center gap-3">
          <Eye className="h-4 w-4 text-primary" />
          <h4 className="font-semibold text-sm">Pré-visualização — o que a IA recebe</h4>
          <div className="w-56"><ScopeSelect value={previewScope} onChange={loadPreview} scopes={scopes} testid="learning-preview-scope" /></div>
          <Button variant="outline" size="sm" className="rounded-sm gap-2" onClick={() => loadPreview(previewScope)} disabled={previewBusy} data-testid="learning-preview-btn">
            {previewBusy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Eye className="h-4 w-4" />} Afficher
          </Button>
        </div>
        {previewText !== null && (
          previewText === "" ? (
            <p className="text-sm text-muted-foreground" data-testid="learning-preview-empty">Nenhum exemplo aprovado para este âmbito — a IA não acrescenta nada.</p>
          ) : (
            <pre className="text-xs bg-muted/50 rounded-sm p-3 overflow-x-auto whitespace-pre-wrap max-h-80" data-testid="learning-preview-text">{previewText}</pre>
          )
        )}
      </div>

      {/* Liste */}
      <div className="flex items-center justify-between pt-2">
        <h4 className="font-semibold text-sm">Exemples ({examples.length})</h4>
      </div>
      {loading ? (
        <div className="flex items-center gap-2 text-sm text-muted-foreground"><Loader2 className="h-4 w-4 animate-spin" /> A carregar…</div>
      ) : examples.length === 0 ? (
        <p className="text-sm text-muted-foreground">Nenhum exemplo por agora. Adicione alguns para treinar a IA.</p>
      ) : (
        <div className="grid gap-2" data-testid="learning-list">
          {examples.map((ex) => (
            <div key={ex.id} className="surface rounded-sm p-3 flex flex-col gap-2" data-testid={`learning-item-${ex.id}`}>
              <div className="flex flex-wrap items-center gap-2">
                <span className="text-[11px] px-2 py-0.5 rounded-full bg-primary/10 text-primary font-medium">{SCOPE_LABELS[ex.scope] || ex.scope}</span>
                <span className="font-medium text-sm">{ex.title || "(sem título)"}</span>
                <span className={`text-[11px] px-2 py-0.5 rounded-full ${ex.approved ? "bg-emerald-500/15 text-emerald-600" : "bg-muted text-muted-foreground"}`}>
                  {ex.approved ? "Aprovado" : "Brouillon"}
                </span>
                <span className="text-[11px] text-muted-foreground flex items-center gap-1" title="Número de gerações IA que utilizaram este exemplo" data-testid={`learning-usage-${ex.id}`}>
                  <BarChart3 className="h-3 w-3" /> {ex.used_count || 0} usage(s){ex.last_used_at ? ` · dernier ${fmtDate(ex.last_used_at)}` : ""}
                </span>
                <div className="flex items-center gap-1 ml-auto">
                  <Button variant="ghost" size="icon" className="h-7 w-7 rounded-sm" onClick={() => toggleApproved(ex)}
                          title={ex.approved ? "Desativar" : "Approuver"} data-testid={`learning-toggle-${ex.id}`}>
                    <Check className={`h-4 w-4 ${ex.approved ? "text-emerald-600" : "text-muted-foreground"}`} />
                  </Button>
                  <Button variant="ghost" size="icon" className="h-7 w-7 rounded-sm" onClick={() => startEdit(ex)}
                          title="Editar" data-testid={`learning-edit-${ex.id}`}>
                    <Pencil className="h-4 w-4" />
                  </Button>
                  <Button variant="ghost" size="icon" className="h-7 w-7 rounded-sm text-red-600" onClick={() => remove(ex)}
                          title="Eliminar" data-testid={`learning-delete-${ex.id}`}>
                    <Trash2 className="h-4 w-4" />
                  </Button>
                </div>
              </div>
              {ex.context && <p className="text-xs text-muted-foreground line-clamp-2"><b>Situation :</b> {ex.context}</p>}
              <p className="text-xs text-foreground/80 line-clamp-3 whitespace-pre-wrap">{ex.content}</p>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
