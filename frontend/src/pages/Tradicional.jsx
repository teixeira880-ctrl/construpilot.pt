import { useCallback, useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { toast } from "sonner";
import { Hammer, Loader2, Ruler, Sparkles } from "lucide-react";
import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import EstudoWorkbench from "@/components/estudo/EstudoWorkbench";

// Construção tradicional: alvenaria assente unidade a unidade (engines/tradicional). O tipo de cada parede escolhe-se aqui.
const TIPOS = { EXT: "Exterior · tijolo 30×20×22", INT: "Interior · tijolo 30×20×11", EXT_BLOCO: "Exterior · bloco 50×20×20", INT_BLOCO: "Interior · bloco 50×20×10" };
const n2 = (x) => Number(x).toLocaleString("pt-PT", { minimumFractionDigits: 2, maximumFractionDigits: 2 });

export default function Tradicional() {
  const [sp] = useSearchParams();
  const planId = sp.get("plan");
  const page = Number(sp.get("page") || 0);
  const [projeto, setProjeto] = useState(null);
  const [modelo, setModelo] = useState(null);
  const [hipoteses, setHipoteses] = useState([]);
  const [busy, setBusy] = useState(false);

  const calcular = useCallback(async (p) => {
    setBusy(true);
    try { setModelo((await api.post("/tradicional/modelo", { projeto: p })).data); }
    catch (e) { setModelo(null); toast.error(e?.response?.data?.detail || "Não foi possível calcular."); }
    finally { setBusy(false); }
  }, []);
  const abrir = useCallback(async (url) => {
    setBusy(true);
    try {
      const { data } = await api.get(url);
      setProjeto(data.projeto); setHipoteses(data.hipoteses || []);
      await calcular(data.projeto);
    } catch (e) { toast.error(e?.response?.data?.detail || "Não foi possível abrir o projeto."); setBusy(false); }
  }, [calcular]);
  useEffect(() => { if (planId) abrir(`/tradicional/da-planta/${encodeURIComponent(planId)}/${page}`); }, [planId, page, abrir]);

  const mudarTipo = (pi, wi, tipo) => {
    const p = { ...projeto, pisos: projeto.pisos.map((ps, i) => (i !== pi ? ps : { ...ps, paredes: ps.paredes.map((w, k) => (k !== wi ? w : { ...w, tipo })) })) };
    setProjeto(p);
    calcular(p);
  };
  const todas = (bloco) => {
    const p = { ...projeto, pisos: projeto.pisos.map((ps) => ({ ...ps, paredes: ps.paredes.map((w) => ({ ...w, tipo: (w.tipo || "EXT").replace("_BLOCO", "") + (bloco ? "_BLOCO" : "") })) })) };
    setProjeto(p);
    calcular(p);
  };

  return (
    <div className="max-w-6xl mx-auto px-4 py-8 space-y-5" data-testid="tradicional-page">
      <header className="space-y-2">
        <div className="flex items-center gap-2">
          <Hammer className="h-6 w-6 text-primary" />
          <h1 className="text-3xl font-bold tracking-tight">Construção tradicional</h1>
          <Badge variant="outline" className="ml-1">Pro</Badge>
        </div>
        <p className="text-sm text-muted-foreground max-w-3xl">
          Alvenaria assente unidade a unidade, fiada a fiada: cada tijolo ou bloco, cada corte, a argamassa das juntas, o reboco e os lintéis dos vãos.
          A estrutura de betão armado ainda não entra neste cálculo.
        </p>
      </header>
      <div className="rounded-md border border-amber-300 bg-amber-50 p-3 text-[13px] text-amber-900">
        <b>Quantidades geradas automaticamente a partir da geometria das paredes — a verificar por um técnico antes da encomenda e da execução.</b>
      </div>
      <Card className="p-4 space-y-3">
        <div className="flex flex-wrap gap-2">
          <Button onClick={() => abrir("/tradicional/exemplo")} disabled={busy} data-testid="trad-exemplo">
            {busy ? <Loader2 className="h-4 w-4 animate-spin mr-1" /> : <Sparkles className="h-4 w-4 mr-1" />}Experimentar com a moradia exemplo
          </Button>
          {projeto && <Button variant="outline" onClick={() => todas(false)} disabled={busy}>Tudo em tijolo</Button>}
          {projeto && <Button variant="outline" onClick={() => todas(true)} disabled={busy}>Tudo em bloco de betão</Button>}
        </div>
        {!projeto && <p className="text-sm text-muted-foreground">Abra o exemplo, ou venha do modelo BIM de uma planta lida («Calcular alvenaria» no /bim) para usar as suas paredes.</p>}
        {hipoteses.map((h) => <p key={h} className="text-xs text-amber-800">{h}</p>)}
        {projeto && projeto.pisos.map((ps, pi) => (
          <div key={ps.nome} className="space-y-1">
            <h2 className="text-sm font-semibold flex items-center gap-1"><Ruler className="h-4 w-4" />{ps.nome} · {ps.paredes.length} paredes</h2>
            <div className="overflow-x-auto rounded-md border max-h-72">
              <table className="w-full text-xs">
                <thead className="bg-muted/50 text-muted-foreground"><tr><th className="px-2 py-1 text-left">Parede</th><th className="px-2 py-1 text-right">Comp. (m)</th><th className="px-2 py-1 text-right">Altura (m)</th><th className="px-2 py-1 text-right">Vãos</th><th className="px-2 py-1 text-left">Tipo</th></tr></thead>
                <tbody>
                  {ps.paredes.map((w, wi) => (
                    <tr key={w.id} className="border-t">
                      <td className="px-2 py-1">{w.id}</td>
                      <td className="px-2 py-1 text-right tabular-nums">{n2(Math.hypot(w.x2 - w.x1, w.y2 - w.y1))}</td>
                      <td className="px-2 py-1 text-right tabular-nums">{n2(w.altura_m)}</td>
                      <td className="px-2 py-1 text-right tabular-nums">{(w.vaos || []).length}</td>
                      <td className="px-2 py-1">
                        <select className="h-7 rounded border bg-background px-1" value={w.tipo || "EXT"} disabled={busy} onChange={(e) => mudarTipo(pi, wi, e.target.value)} aria-label={`Tipo da parede ${w.id}`}>
                          {Object.entries(TIPOS).map(([k, n]) => <option key={k} value={k}>{n}</option>)}
                        </select>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        ))}
      </Card>
      {modelo && <EstudoWorkbench modelo={modelo} />}
    </div>
  );
}
