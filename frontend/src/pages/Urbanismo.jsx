import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { toast } from "sonner";
import { FileText, ArrowRight, Plus, Loader2, Building2, FlaskConical, Scale } from "lucide-react";
import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

const TIPOS_FALLBACK = {
  moradia_nova: "Construção nova (moradia / edifício)",
  ampliacao: "Ampliação de edifício existente",
  anexo: "Anexo / edificação de apoio",
  piscina: "Piscina",
  muro: "Muro de vedação ou de suporte",
};

export default function Urbanismo() {
  const nav = useNavigate();
  const [cfg, setCfg] = useState(null);
  const [list, setList] = useState(null);
  const [busy, setBusy] = useState("");
  const [form, setForm] = useState({ title: "", tipo_obra: "moradia_nova", concelho: "" });

  useEffect(() => {
    api.get("/urbanismo/config").then((r) => setCfg(r.data)).catch(() => {});
    api.get("/urbanismo/processos").then((r) => setList(r.data.processos || [])).catch(() => setList([]));
  }, []);

  const criar = async () => {
    if (form.title.trim().length < 2) return toast.error("Dê um nome ao processo.");
    setBusy("criar");
    try {
      const { data } = await api.post("/urbanismo/processos", { title: form.title.trim(), tipo_obra: form.tipo_obra, terreno: { concelho: form.concelho } });
      nav(`/urbanismo/${data.processo_id}`);
    } catch (e) { toast.error(e?.response?.data?.detail || "Criação impossível."); }
    finally { setBusy(""); }
  };

  const exemplo = async () => {
    setBusy("exemplo");
    try { const { data } = await api.post("/urbanismo/processos/exemplo"); nav(`/urbanismo/${data.processo_id}`); }
    catch { toast.error("Exemplo indisponível de momento."); }
    finally { setBusy(""); }
  };

  const tipos = cfg?.tipos_obra || TIPOS_FALLBACK;
  return (
    <div className="max-w-3xl mx-auto px-4 py-6 grid gap-5" data-testid="urbanismo-page">
      <header className="grid gap-1">
        <div className="text-xs uppercase tracking-widest text-primary font-semibold flex items-center gap-1"><Building2 size={14} /> Urbanismo</div>
        <h1 className="text-2xl sm:text-3xl font-bold tracking-tight">Editor de volumes e peças desenhadas</h1>
        <p className="text-sm text-muted-foreground">A partir de algumas dimensões, gere a planta de implantação, o corte, o alçado e o quadro de áreas, e verifique os parâmetros do plano municipal (PDM) que introduzir.</p>
      </header>

      <section className="border rounded-lg p-4 grid gap-3" data-testid="urb-novo">
        <h2 className="font-semibold flex items-center gap-2"><Plus className="h-4 w-4" /> Novo processo</h2>
        <div className="grid sm:grid-cols-3 gap-3">
          <label className="grid gap-1 text-sm sm:col-span-3">Nome do processo
            <Input value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} placeholder="Ex.: Moradia T3 — Rua das Oliveiras" data-testid="urb-title" />
          </label>
          <label className="grid gap-1 text-sm sm:col-span-2">Tipo de operação
            <select className="h-10 rounded-md border bg-background px-2" value={form.tipo_obra} onChange={(e) => setForm({ ...form, tipo_obra: e.target.value })} data-testid="urb-tipo">
              {Object.entries(tipos).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
            </select>
          </label>
          <label className="grid gap-1 text-sm">Concelho
            <Input value={form.concelho} onChange={(e) => setForm({ ...form, concelho: e.target.value })} data-testid="urb-concelho" />
          </label>
        </div>
        <div className="flex flex-wrap gap-2">
          <Button onClick={criar} disabled={!!busy} data-testid="urb-criar">{busy === "criar" ? <Loader2 className="h-4 w-4 animate-spin" /> : <Plus className="h-4 w-4" />} Criar processo</Button>
          <Button variant="outline" onClick={exemplo} disabled={!!busy} data-testid="urb-exemplo">{busy === "exemplo" ? <Loader2 className="h-4 w-4 animate-spin" /> : <FlaskConical className="h-4 w-4" />} Abrir um exemplo fictício</Button>
        </div>
      </section>

      <div className="rounded-md border border-primary/30 bg-primary/5 p-3 text-sm flex items-start gap-2">
        <Scale className="h-4 w-4 mt-0.5 text-primary shrink-0" />
        <p>Só precisa de saber se a obra é isenta, sujeita a comunicação prévia ou a licença? Use o <Link to={cfg?.pagina_rjue || "/particulares/autorizacao-obras"} className="underline font-medium">diagnóstico RJUE (Autorização de obras)</Link> — é o mesmo motor usado aqui.</p>
      </div>

      <section className="grid gap-2" data-testid="urb-lista">
        <h2 className="text-sm font-semibold text-muted-foreground">Os meus processos</h2>
        {list === null && <div className="flex items-center gap-2 text-sm text-muted-foreground"><Loader2 className="h-4 w-4 animate-spin" /> A carregar…</div>}
        {list?.length === 0 && <p className="text-sm text-muted-foreground">Ainda não tem processos de urbanismo.</p>}
        {list?.map((d) => (
          <button key={d.processo_id} onClick={() => nav(`/urbanismo/${d.processo_id}`)} className="text-left border rounded-lg p-3 hover:bg-muted flex items-center gap-3" data-testid={`urb-processo-${d.processo_id}`}>
            <FileText className="h-4 w-4 text-primary shrink-0" />
            <div className="flex-1 min-w-0"><p className="font-medium truncate">{d.title}</p>
              <p className="text-xs text-muted-foreground">{d.tipo_obra_label}{d.procedimento_label ? ` · ${d.procedimento_label}` : ""}{d.status === "exportado" ? " · exportado" : ""}</p></div>
            <ArrowRight className="h-4 w-4 text-muted-foreground shrink-0" />
          </button>
        ))}
      </section>
      {cfg?.aviso && <p className="text-[11px] text-muted-foreground border-l-2 border-amber-400 pl-3">{cfg.aviso}</p>}
    </div>
  );
}
