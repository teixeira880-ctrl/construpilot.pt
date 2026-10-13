import { useState } from "react";
import { FileDown, FileText, Link2, GripVertical } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter,
} from "@/components/ui/dialog";

export function MultiPlanDialog({
  open, onOpenChange,
  multiProjectName, setMultiProjectName,
  multiSelected, setMultiSelected,
  allPlans, plan,
  quoteFinish, quoteFloor,
  multiBusy, downloadMultiQuote,
  downloadMultiMetre = () => {},
  subcontractSel = [], setSubcontractSel = () => {},
  consolidatedBusy = false, createConsolidatedQuote = () => {},
  linkFerraillage = () => {},
}) {
  const [linkOpenFor, setLinkOpenFor] = useState(null);
  const [query, setQuery] = useState("");
  const [dragIdx, setDragIdx] = useState(null);

  const planName = (pid) => {
    const p = allPlans.find((x) => x.plan_id === pid);
    return p?.filename || pid;
  };
  const moveItem = (from, to) => {
    if (from == null || to == null || from === to) return;
    setMultiSelected((prev) => {
      const arr = [...prev];
      const [it] = arr.splice(from, 1);
      arr.splice(to, 0, it);
      return arr;
    });
  };

  const toggleSel = (pid, on) =>
    setMultiSelected((prev) => (on ? [...prev, pid] : prev.filter((id) => id !== pid)));
  const toggleSub = (pid, on) =>
    setSubcontractSel((prev) => (on ? [...prev, pid] : prev.filter((id) => id !== pid)));

  const visiblePlans = query.trim()
    ? allPlans.filter((p) => (p.filename || p.plan_id).toLowerCase().includes(query.trim().toLowerCase()))
    : allPlans;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="rounded-sm max-w-lg" data-testid="multi-quote-dialog">
        <DialogHeader>
          <DialogTitle>Projeto multiplanta</DialogTitle>
          <DialogDescription>
            Combine várias plantas (estrutura, pisos da moradia, ampliações…) num único documento.
            <br /><b>Medição agrupada</b> = apenas as cotas calculadas (m² / ml), sem preço nem IVA.
            <br /><b>Orçamento</b> = medição + orçamentação (IVA por linha: 23 % estrutura, 6 % reabilitação de habitação, 0 % subempreitada — autoliquidação).
          </DialogDescription>
        </DialogHeader>
        <div className="grid gap-3">
          <div className="grid gap-1">
            <Label className="text-xs">Nome do projeto (opcional)</Label>
            <Input value={multiProjectName} onChange={(e) => setMultiProjectName(e.target.value)}
                   placeholder="Ex.: Residência Os Pinheiros — R/C + 1.º andar"
                   maxLength={160}
                   data-testid="multi-project-name" className="rounded-sm h-10" />
          </div>
          {multiSelected.length > 1 && (
            <div>
              <p className="overline mb-2">Ordem de exportação (arrastar para reordenar)</p>
              <div className="grid gap-1" data-testid="multi-order-list">
                {multiSelected.map((pid, i) => (
                  <div key={pid} draggable
                       onDragStart={() => setDragIdx(i)}
                       onDragOver={(e) => e.preventDefault()}
                       onDrop={() => { moveItem(dragIdx, i); setDragIdx(null); }}
                       onDragEnd={() => setDragIdx(null)}
                       data-testid={`multi-order-item-${pid}`}
                       className={`flex items-center gap-2 rounded-sm border px-2 py-1.5 cursor-grab active:cursor-grabbing text-sm ${dragIdx === i ? "border-primary bg-primary/10" : "border-border bg-secondary/40"}`}>
                    <GripVertical className="h-4 w-4 text-muted-foreground shrink-0" />
                    <span className="num text-xs text-muted-foreground w-5">{i + 1}.</span>
                    <span className="truncate flex-1">{planName(pid)}</span>
                  </div>
                ))}
              </div>
            </div>
          )}
          <div>
            <p className="overline mb-2">Plantas a incluir ({multiSelected.length} selecionado{multiSelected.length > 1 ? "s" : ""})</p>
            {allPlans.length > 6 && (
              <Input value={query} onChange={(e) => setQuery(e.target.value)}
                     placeholder="Pesquisar uma planta…" data-testid="multi-plans-search"
                     className="rounded-sm h-9 mb-2 text-sm" />
            )}
            <div className="grid gap-1 max-h-72 overflow-y-auto border border-border rounded-sm p-2"
                 data-testid="multi-plans-list">
              {allPlans.length === 0 ? (
                <p className="text-xs text-muted-foreground text-center py-4">
                  Nenhum plano disponível. Carregue pelo menos 2 planos a partir da página /plan.
                </p>
              ) : visiblePlans.map((p) => {
                const on = multiSelected.includes(p.plan_id);
                const sub = subcontractSel.includes(p.plan_id);
                const isGros = !!p.structural_metre;
                const kindLbl = isGros ? "🏢 Estrutura" : (p.rooms?.length ? "🏠 Maison" : "Planta");
                const linkedCount = (p.ferraillage_plan_ids || []).length;
                return (
                  <div key={p.plan_id}
                       className={`rounded-sm border ${on ? "border-primary bg-primary/5" : "border-transparent hover:bg-secondary/40"}`}
                       data-testid={`multi-plan-item-${p.plan_id}`}>
                    <label className="flex items-center gap-2 p-2 cursor-pointer">
                      <input type="checkbox" checked={on}
                             onChange={(e) => toggleSel(p.plan_id, e.target.checked)}
                             data-testid={`multi-plan-checkbox-${p.plan_id}`}
                             className="accent-primary h-4 w-4" />
                      <div className="min-w-0 flex-1">
                        <p className="text-sm font-bold truncate">
                          {p.filename || p.plan_id}
                          {p.plan_id === plan?.plan_id && <span className="text-primary ml-1 text-[10px]">(em curso)</span>}
                        </p>
                        <p className="text-[10px] text-muted-foreground num">
                          {kindLbl} · {p.rooms?.length || 0} divisões · {(p.rooms?.reduce((s, r) => s + (r.surface_m2 || 0), 0) || 0).toFixed(1)} m²
                          {linkedCount > 0 && <span className="text-primary ml-1">· {linkedCount} armadura associada{linkedCount > 1 ? "s" : ""}</span>}
                        </p>
                      </div>
                    </label>
                    {on && (
                      <div className="flex items-center gap-3 px-2 pb-2 pl-8 flex-wrap">
                        <label className="flex items-center gap-1 text-[11px] cursor-pointer text-muted-foreground">
                          <input type="checkbox" checked={sub}
                                 onChange={(e) => toggleSub(p.plan_id, e.target.checked)}
                                 data-testid={`multi-subcontract-${p.plan_id}`}
                                 className="accent-primary h-3.5 w-3.5" />
                          Subempreitada (IVA 0 %)
                        </label>
                        {isGros && (
                          <button type="button"
                                  onClick={() => setLinkOpenFor(linkOpenFor === p.plan_id ? null : p.plan_id)}
                                  data-testid={`multi-link-ferraillage-${p.plan_id}`}
                                  className="flex items-center gap-1 text-[11px] text-primary hover:underline">
                            <Link2 className="h-3 w-3" /> Associar armaduras
                          </button>
                        )}
                      </div>
                    )}
                    {isGros && linkOpenFor === p.plan_id && (
                      <div className="mx-2 mb-2 ml-8 border border-primary/30 rounded-sm p-2 grid gap-1 bg-secondary/40"
                           data-testid={`ferraillage-picker-${p.plan_id}`}>
                        <p className="text-[10px] text-muted-foreground mb-1">
                          Assinale os planos de armação a orçamentar com esta cofragem:
                        </p>
                        {allPlans.filter((q) => q.plan_id !== p.plan_id).map((q) => {
                          const linked = (p.ferraillage_plan_ids || []).includes(q.plan_id);
                          return (
                            <label key={q.plan_id} className="flex items-center gap-2 text-[11px] cursor-pointer">
                              <input type="checkbox" checked={linked}
                                     onChange={(e) => {
                                       const cur = p.ferraillage_plan_ids || [];
                                       const next = e.target.checked
                                         ? [...cur, q.plan_id]
                                         : cur.filter((id) => id !== q.plan_id);
                                       linkFerraillage(p.plan_id, next);
                                     }}
                                     data-testid={`ferraillage-opt-${p.plan_id}-${q.plan_id}`}
                                     className="accent-primary h-3.5 w-3.5" />
                              {q.filename || q.plan_id}
                            </label>
                          );
                        })}
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          </div>
        </div>
        <DialogFooter className="flex-col sm:flex-row gap-2">
          <Button variant="outline" onClick={() => onOpenChange(false)} className="rounded-sm">
            Cancelar
          </Button>
          <Button variant="outline" onClick={downloadMultiMetre}
                  disabled={multiBusy || multiSelected.length === 0}
                  data-testid="multi-metre-download-btn"
                  className="rounded-sm gap-2 border-primary/50 text-primary hover:bg-primary hover:text-white">
            <FileDown className="h-4 w-4" />
            {multiBusy ? "Geração…" : "Medição agrupada (sem preços)"}
          </Button>
          <Button variant="outline" onClick={downloadMultiQuote}
                  disabled={multiBusy || multiSelected.length === 0}
                  data-testid="multi-quote-download-btn"
                  className="rounded-sm gap-2">
            <FileDown className="h-4 w-4" />
            {multiBusy ? "Geração…" : "Orçamento PDF agrupado"}
          </Button>
          <Button onClick={createConsolidatedQuote}
                  disabled={consolidatedBusy || multiSelected.length === 0}
                  data-testid="multi-consolidated-btn"
                  className="rounded-sm gap-2 hover:bg-orange-600 hover:text-white">
            <FileText className="h-4 w-4" />
            {consolidatedBusy ? "A criar…" : `Orçamento consolidado (${multiSelected.length})`}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
