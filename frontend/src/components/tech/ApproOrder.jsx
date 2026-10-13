import { useState } from "react";
import { Download, ShoppingCart, Euro, Mail, Loader2, MapPin } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter,
} from "@/components/ui/dialog";
import { api } from "@/lib/api";
import { toast } from "sonner";

const conf = (c) => (c >= 0.85 ? { cls: "bg-emerald-500/15 text-emerald-600", lbl: "🟢" }
  : c >= 0.6 ? { cls: "bg-amber-500/15 text-amber-600", lbl: "🟠" }
    : { cls: "bg-red-500/15 text-red-600", lbl: "🔴" });
const eur = (n) => (Number(n) || 0).toLocaleString("fr-FR", { minimumFractionDigits: 2, maximumFractionDigits: 2 });

export default function ApproOrder({ items, suppliers, csvName, createOrder, onHighlight }) {
  const [supplierId, setSupplierId] = useState("");
  const [priced, setPriced] = useState(null);      // {items, grand_total}
  const [overrides, setOverrides] = useState({});
  const [order, setOrder] = useState(null);
  const [emailOpen, setEmailOpen] = useState(false);
  const [ccSelf, setCcSelf] = useState(true);
  const [toEmail, setToEmail] = useState("");
  const [busy, setBusy] = useState(false);

  const supplier = suppliers.find((s) => s.supplier_id === supplierId);

  const estimate = async (ov = overrides) => {
    setBusy(true);
    try {
      const { data } = await api.post("/pro/appro/price", { items, supplier_id: supplierId || null, overrides: ov });
      setPriced(data);
    } catch (e) { toast.error(e?.response?.data?.detail || "Orçamentação impossível"); }
    finally { setBusy(false); }
  };

  const setPU = (i, val) => {
    const ov = { ...overrides, [i]: val };
    setOverrides(ov);
    // recalcul local immédiat
    if (priced) {
      const its = priced.items.map((it, k) => k === i
        ? { ...it, unit_price: parseFloat(val) || 0, line_total: Math.round((parseFloat(val) || 0) * (it.priced_qty || 0) * 100) / 100, price_source: "manuel" }
        : it);
      setPriced({ items: its, grand_total: Math.round(its.reduce((s, it) => s + (it.line_total || 0), 0) * 100) / 100 });
    }
  };

  const rows = priced?.items || items;

  const downloadCsv = () => {
    const priceCols = !!priced;
    const head = ["Designation", "Quantite", "Unite", "Commandable_qty", "Commandable_unite"].concat(priceCols ? ["PU_HT", "Total_HT"] : []);
    const lines = [head.join(";")].concat(rows.map((it) => {
      const base = [it.designation, it.qty, it.unit, it.commandable_qty ?? "", it.commandable_unit ?? ""];
      return base.concat(priceCols ? [it.unit_price ?? "", it.line_total ?? ""] : []).join(";");
    }));
    const blob = new Blob([lines.join("\n")], { type: "text/csv" });
    const a = document.createElement("a"); a.href = URL.createObjectURL(blob);
    a.download = csvName || "bon_commande.csv"; a.click();
  };

  const doCreateOrder = async () => {
    setBusy(true);
    try {
      const o = await createOrder(supplierId || null);
      setOrder(o);
      toast.success("Nota de encomenda criada (rascunho)");
    } catch (e) { toast.error(e?.response?.data?.detail || "Impossível criar a nota de encomenda"); }
    finally { setBusy(false); }
  };

  const openEmail = async () => {
    let o = order;
    if (!o) {
      setBusy(true);
      try { o = await createOrder(supplierId || null); setOrder(o); }
      catch (e) { toast.error(e?.response?.data?.detail || "Impossível criar a nota de encomenda"); setBusy(false); return; }
      setBusy(false);
    }
    setToEmail(supplier?.email || "");
    setEmailOpen(true);
  };

  const sendEmail = async () => {
    if (!toEmail) return toast.error("E-mail do fornecedor necessário");
    setBusy(true);
    try {
      await api.post(`/pro/appro/orders/${order.order_id}/email`, {
        to: toEmail, cc_self: ccSelf,
        priced_items: priced ? priced.items : null,
      });
      toast.success(`Nota de encomenda enviada para${toEmail}`);
      setEmailOpen(false);
    } catch (e) { toast.error(e?.response?.data?.detail || "Envio impossível"); }
    finally { setBusy(false); }
  };

  if (!items?.length) return null;

  return (
    <div className="surface p-4 space-y-3" data-testid="appro-order">
      <div className="flex flex-wrap items-end gap-3">
        <div className="min-w-[200px]">
          <label className="text-xs text-muted-foreground">Fornecedor</label>
          <select value={supplierId} onChange={(e) => { setSupplierId(e.target.value); setPriced(null); setOrder(null); }}
            className="w-full mt-1 rounded-sm border border-border bg-background px-3 py-2 text-sm" data-testid="appro-supplier-select">
            <option value="">— Nenhum —</option>
            {suppliers.map((s) => <option key={s.supplier_id} value={s.supplier_id}>{s.name}{s.agency ? ` (${s.agency})` : ""}</option>)}
          </select>
        </div>
        <Button variant="outline" onClick={() => estimate()} disabled={busy} className="gap-2 rounded-sm" data-testid="appro-estimate-btn">
          {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Euro className="h-4 w-4" />}Orçamentar (fornecedor / DPGF)
        </Button>
      </div>

      <div className="overflow-auto rounded-sm border border-border">
        <table className="w-full text-xs">
          <thead className="bg-secondary/40"><tr>
            <th className="text-left p-2">Designação</th>
            <th className="p-2 text-right">Qtd.</th><th className="p-2">Un.</th>
            <th className="p-2 text-right">Commandable</th><th className="p-2">Cond.</th>
            {priced && <th className="p-2 text-right">PU HT</th>}
            {priced && <th className="p-2 text-right">Total s/ IVA</th>}
            <th className="p-2">Conf.</th><th className="p-2"></th>
          </tr></thead>
          <tbody>
            {rows.map((it, i) => {
              const c = conf(it.confidence ?? 0.8);
              return (
                <tr key={i} className="border-t border-border/60 hover:bg-secondary/20" data-testid={`appro-row-${i}`}>
                  <td className="p-2">{it.designation}</td>
                  <td className="p-2 text-right num">{it.qty}</td>
                  <td className="p-2 text-center">{it.unit}</td>
                  <td className="p-2 text-right num font-semibold">{it.commandable_qty ?? "—"}</td>
                  <td className="p-2 text-center">{it.commandable_unit || "—"}</td>
                  {priced && <td className="p-1 text-right"><Input type="number" value={it.unit_price ?? 0} onChange={(e) => setPU(i, e.target.value)} className="h-7 w-20 text-xs text-right" data-testid={`appro-pu-${i}`} /></td>}
                  {priced && <td className="p-2 text-right num font-semibold">{eur(it.line_total)} €</td>}
                  <td className="p-2 text-center"><span className={`text-[10px] font-bold px-1.5 py-0.5 rounded-full ${c.cls}`}>{c.lbl} {Math.round((it.confidence ?? 0.8) * 100)}%</span></td>
                  <td className="p-2 text-center">
                    {it.bbox ? (
                      <button onClick={() => onHighlight?.(it.bbox)} title="Localizar na planta" data-testid={`appro-locate-${i}`}>
                        <MapPin className="h-3.5 w-3.5 text-primary hover:scale-125 transition-transform" />
                      </button>
                    ) : null}
                  </td>
                </tr>
              );
            })}
          </tbody>
          {priced && (
            <tfoot><tr className="border-t-2 border-border bg-secondary/30 font-bold">
              <td className="p-2" colSpan={priced ? 6 : 5}>Total estimado s/ IVA</td>
              <td className="p-2 text-right text-primary" data-testid="appro-grand-total">{eur(priced.grand_total)} €</td>
              <td colSpan={2}></td>
            </tr></tfoot>
          )}
        </table>
      </div>

      <div className="flex flex-wrap gap-2">
        <Button size="sm" variant="outline" onClick={downloadCsv} className="gap-2 rounded-sm" data-testid="appro-csv-btn"><Download className="h-4 w-4" />CSV</Button>
        <Button size="sm" variant="outline" onClick={doCreateOrder} disabled={busy} className="gap-2 rounded-sm" data-testid="appro-create-order-btn"><ShoppingCart className="h-4 w-4" />Criar o vale</Button>
        <Button size="sm" onClick={openEmail} disabled={busy} className="gap-2 rounded-sm" data-testid="appro-email-btn"><Mail className="h-4 w-4" />Enviar ao fornecedor</Button>
      </div>
      <p className="text-[11px] text-muted-foreground">Nenhuma encomenda é enviada sem a sua validação na pré-visualização.</p>

      <Dialog open={emailOpen} onOpenChange={setEmailOpen}>
        <DialogContent data-testid="appro-email-dialog">
          <DialogHeader><DialogTitle className="flex items-center gap-2"><Mail className="h-5 w-5 text-primary" />Enviar a nota de encomenda</DialogTitle></DialogHeader>
          <div className="space-y-3 text-sm">
            <div>
              <label className="text-xs text-muted-foreground">Destinatário (fornecedor)</label>
              <Input value={toEmail} onChange={(e) => setToEmail(e.target.value)} placeholder="email@fournisseur.fr" className="h-9" data-testid="appro-email-to" />
            </div>
            <label className="flex items-center gap-2 text-xs">
              <input type="checkbox" checked={ccSelf} onChange={(e) => setCcSelf(e.target.checked)} data-testid="appro-email-cc" />
              Me mettre en copie (CC)
            </label>
            <div className="rounded-sm border border-border p-3 bg-secondary/20 text-xs">
              <div className="font-semibold mb-1">Pré-visualização · {rows.length} ligne(s){priced ? `· Total${eur(priced.grand_total)} € HT` : ""}</div>
              <ul className="space-y-0.5 max-h-40 overflow-auto">
                {rows.slice(0, 12).map((it, i) => (
                  <li key={i} className="flex justify-between gap-2">
                    <span className="truncate">{it.designation}</span>
                    <span className="whitespace-nowrap num">{it.commandable_qty ?? it.qty} {it.commandable_unit || it.unit}{priced ? ` · ${eur(it.line_total)} €` : ""}</span>
                  </li>
                ))}
                {rows.length > 12 && <li className="text-muted-foreground">+ {rows.length - 12} autre(s)…</li>}
              </ul>
              <p className="text-[11px] text-muted-foreground mt-2">PDF + CSV joints automatiquement.</p>
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setEmailOpen(false)} className="rounded-sm">Cancelar</Button>
            <Button onClick={sendEmail} disabled={busy} className="gap-2 rounded-sm" data-testid="appro-email-send-btn">
              {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Mail className="h-4 w-4" />}Enviar
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
