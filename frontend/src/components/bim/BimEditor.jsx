import { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import { Loader2, Pencil, RotateCcw, Send, Trash2, Undo2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { api } from "@/lib/api";

/**
 * Editor do modelo BIM de um piso: as mesmas operações do servidor (engines/bim_core/edicao.py) por opções
 * (tabelas de paredes e vãos) ou por pedido em texto. Cada alteração é guardada e o IFC é gerado de novo.
 */
const n2 = (x) => Number(x).toLocaleString("pt-PT", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const VAO = { porte: "Porta", fenetre: "Janela", baie: "Vão" };
const EXEMPLOS = ["muda a espessura da parede w1 para 25 cm", "acrescenta uma janela de 1,20 m na parede w2 a 2 m do início", "pé-direito 2,80"];

export default function BimEditor({ planId, page, disabled, onChanged }) {
  const base = `/bim/takeoffs/${encodeURIComponent(planId)}/${page}/modelo`;
  const [estado, setEstado] = useState(null);
  const [texto, setTexto] = useState("");
  const [busy, setBusy] = useState(false);
  const [resultado, setResultado] = useState(null);
  const [aberto, setAberto] = useState(false);

  const carregar = useCallback(async () => {
    try { setEstado((await api.get(base)).data); } catch { setEstado(null); }
  }, [base]);
  useEffect(() => { if (aberto) carregar(); }, [aberto, carregar]);

  const enviar = async (payload) => {
    setBusy(true);
    try {
      const { data } = await api.post(`${base}/ops`, payload);
      setResultado(data);
      if (data.feito?.length) {
        if (payload.texto) setTexto("");
        await carregar();
        onChanged?.();
      }
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Não foi possível aplicar a alteração.");
    } finally { setBusy(false); }
  };
  const op = (o) => enviar({ ops: [o] });
  const desfazer = async () => {
    setBusy(true);
    try { await api.post(`${base}/desfazer`); setResultado(null); await carregar(); onChanged?.(); }
    catch (e) { toast.error(e?.response?.data?.detail || "Nada para desfazer."); }
    finally { setBusy(false); }
  };
  const repor = async () => {
    if (!window.confirm("Apagar todas as edições deste piso e voltar à planta lida?")) return;
    setBusy(true);
    try { await api.delete(base); setResultado(null); await carregar(); onChanged?.(); }
    catch { toast.error("Não foi possível repor a planta lida."); }
    finally { setBusy(false); }
  };

  const m = estado?.modelo;
  const off = busy || disabled;
  return (
    <section className="rounded-md border p-2 space-y-2" data-testid="bim-editor">
      <button type="button" className="flex w-full items-center gap-2 font-semibold" onClick={() => setAberto(!aberto)} aria-expanded={aberto}>
        <Pencil className="h-4 w-4 text-primary" /> Editar o modelo
        {estado?.editado && <span className="ml-auto rounded bg-amber-100 px-1.5 py-0.5 text-[10px] font-normal text-amber-900">editado</span>}
      </button>
      {aberto && (
        <>
          <form className="space-y-1" onSubmit={(e) => { e.preventDefault(); if (texto.trim()) enviar({ texto }); }}>
            <textarea className="w-full rounded border bg-background p-2 text-xs" rows={3} value={texto} onChange={(e) => setTexto(e.target.value)}
                      placeholder={`Peça em texto, uma alteração por frase. Ex.: ${EXEMPLOS[0]}`} data-testid="bim-editor-prompt" />
            <div className="flex flex-wrap gap-1">
              <Button type="submit" size="sm" className="h-7 gap-1 text-xs" disabled={off || !texto.trim()}>
                {busy ? <Loader2 className="h-3 w-3 animate-spin" /> : <Send className="h-3 w-3" />} Aplicar
              </Button>
              <Button type="button" size="sm" variant="outline" className="h-7 gap-1 text-xs" disabled={off || !estado?.pode_desfazer} onClick={desfazer}>
                <Undo2 className="h-3 w-3" /> Desfazer
              </Button>
              <Button type="button" size="sm" variant="outline" className="h-7 gap-1 text-xs" disabled={off || !estado?.editado} onClick={repor}>
                <RotateCcw className="h-3 w-3" /> Planta lida
              </Button>
            </div>
          </form>
          {resultado && (
            <ul className="space-y-0.5 text-[11px]" data-testid="bim-editor-result">
              {(resultado.feito || []).map((f, i) => <li key={`f${i}`} className="text-emerald-700 dark:text-emerald-400">{f}</li>)}
              {(resultado.erros || []).map((f, i) => <li key={`e${i}`} className="text-red-700 dark:text-red-400">Recusado — {f}</li>)}
              {(resultado.nao_percebido || []).map((f, i) => <li key={`n${i}`} className="text-amber-700 dark:text-amber-400">Não percebi: «{f}»</li>)}
            </ul>
          )}
          {m && (
            <>
              <label className="flex items-center gap-2 text-xs">Pé-direito (m)
                <input type="number" step="0.05" min="1.5" max="12" className="h-7 w-20 rounded border bg-background px-1 text-right" disabled={off}
                       defaultValue={m.params?.wall_height ?? ""} key={`h${m.params?.wall_height}`}
                       onBlur={(e) => { const v = Number(e.target.value); if (v && v !== m.params?.wall_height) op({ op: "pe_direito", altura: v }); }} />
              </label>
              <div>
                <h3 className="text-xs font-semibold mb-1">Paredes ({m.walls.length})</h3>
                <div className="max-h-56 overflow-y-auto">
                  <table className="w-full text-[11px]">
                    <thead className="text-muted-foreground"><tr><th className="text-left">Id</th><th className="text-right">Comp. (m)</th><th className="text-right">Esp. (cm)</th><th>Resist.</th><th /></tr></thead>
                    <tbody>
                      {m.walls.map((w) => (
                        <tr key={w.source_id} className="border-t">
                          <td className="py-0.5">{w.source_id}</td>
                          <td className="text-right tabular-nums">{n2(Math.hypot(w.x2 - w.x1, w.y2 - w.y1))}</td>
                          <td className="text-right">
                            <input type="number" step="1" min="3" max="100" className="h-6 w-14 rounded border bg-background px-1 text-right" disabled={off}
                                   defaultValue={Math.round(w.thickness * 1000) / 10} key={`${w.source_id}-${w.thickness}`}
                                   onBlur={(e) => { const v = Number(e.target.value) / 100; if (v && Math.abs(v - w.thickness) > 1e-6) op({ op: "parede_alterar", id: w.source_id, espessura: v }); }} />
                          </td>
                          <td className="text-center">
                            <input type="checkbox" checked={!!w.load_bearing} disabled={off} aria-label={`Parede ${w.source_id} resistente`}
                                   onChange={(e) => op({ op: "parede_alterar", id: w.source_id, resistente: e.target.checked })} />
                          </td>
                          <td className="text-right">
                            <button type="button" disabled={off} aria-label={`Apagar a parede ${w.source_id}`} onClick={() => op({ op: "parede_apagar", id: w.source_id })}>
                              <Trash2 className="h-3 w-3 text-muted-foreground" />
                            </button>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
              {m.openings.length > 0 && (
                <div>
                  <h3 className="text-xs font-semibold mb-1">Vãos ({m.openings.length})</h3>
                  <div className="max-h-40 overflow-y-auto">
                    <table className="w-full text-[11px]">
                      <thead className="text-muted-foreground"><tr><th className="text-left">Id</th><th className="text-left">Tipo</th><th className="text-left">Parede</th><th className="text-right">Larg. (m)</th><th /></tr></thead>
                      <tbody>
                        {m.openings.map((v) => (
                          <tr key={v.source_id} className="border-t">
                            <td className="py-0.5">{v.source_id}</td><td>{VAO[v.kind] || v.kind}</td><td>{v.wall_id}</td>
                            <td className="text-right">
                              <input type="number" step="0.05" min="0.3" max="12" className="h-6 w-14 rounded border bg-background px-1 text-right" disabled={off}
                                     defaultValue={v.width} key={`${v.source_id}-${v.width}`}
                                     onBlur={(e) => { const x = Number(e.target.value); if (x && Math.abs(x - v.width) > 1e-6) op({ op: "vao_alterar", id: v.source_id, largura: x }); }} />
                            </td>
                            <td className="text-right">
                              <button type="button" disabled={off} aria-label={`Apagar o vão ${v.source_id}`} onClick={() => op({ op: "vao_apagar", id: v.source_id })}>
                                <Trash2 className="h-3 w-3 text-muted-foreground" />
                              </button>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}
              <p className="text-[11px] text-muted-foreground">Cada alteração é guardada e o IFC é gerado de novo. Outros exemplos: «{EXEMPLOS[1]}», «{EXEMPLOS[2]}».</p>
            </>
          )}
        </>
      )}
    </section>
  );
}
