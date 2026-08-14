import { useState } from "react";
import { toast } from "sonner";
import { PackageCheck, Save, Trophy } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { api, eur, num } from "@/lib/api";

const STATUS_LABELS = { en_attente: "En attente", recu: "Devis reçu", retenu: "Retenu ✓" };

export default function PcOrdersTracking({ planId, orders, onSaved }) {
  const [edits, setEdits] = useState({});
  const setE = (ref, field, val) =>
    setEdits((p) => ({ ...p, [ref]: { ...p[ref], [field]: val } }));

  const save = async (o) => {
    const e = edits[o.ref] || {};
    const quoted = e.quoted_ht !== undefined ? parseFloat(e.quoted_ht) : o.quoted_ht;
    const status = e.status || o.status || "en_attente";
    try {
      await api.post(`/takeoffs/${planId}/purchase-orders/response`, {
        ref: o.ref, status,
        quoted_ht: Number.isFinite(quoted) ? quoted : null,
        notes: e.notes ?? o.response_notes ?? "",
      });
      toast.success(`Réponse enregistrée — ${o.ref}`);
      onSaved?.();
    } catch (err) { toast.error(err?.response?.data?.detail || "Enregistrement impossible"); }
  };

  const quotedVals = orders.map((o) => {
    const e = edits[o.ref] || {};
    const q = e.quoted_ht !== undefined ? parseFloat(e.quoted_ht) : o.quoted_ht;
    return Number.isFinite(q) && q > 0 ? q : null;
  });
  const best = Math.min(...quotedVals.filter((q) => q !== null));

  return (
    <section data-testid="pc-orders-tracking">
      <h3 className="text-sm font-semibold mb-1 flex items-center gap-1.5">
        <PackageCheck className="h-4 w-4 text-primary" /> Bons de commande — réponses négoces
      </h3>
      <table className="w-full text-xs border border-border">
        <thead>
          <tr className="bg-muted text-left">
            <th className="p-1.5">Réf / Négoce</th>
            <th className="p-1.5">Phase</th>
            <th className="p-1.5 text-right">Indicatif HT</th>
            <th className="p-1.5 text-right">Devis reçu €</th>
            <th className="p-1.5">Statut</th>
            <th className="p-1.5"></th>
          </tr>
        </thead>
        <tbody>
          {orders.map((o, i) => {
            const e = edits[o.ref] || {};
            const quoted = e.quoted_ht !== undefined ? parseFloat(e.quoted_ht) : o.quoted_ht;
            const hasQuote = Number.isFinite(quoted) && quoted > 0;
            const delta = hasQuote && o.total_ht ? ((quoted - o.total_ht) / o.total_ht) * 100 : null;
            const isBest = hasQuote && quotedVals.filter((q) => q !== null).length > 1 && quoted === best;
            return (
              <tr key={o.ref} className="border-t border-border align-top" data-testid={`pc-order-row-${i}`}>
                <td className="p-1.5">
                  <p className="font-medium num">{o.ref}</p>
                  <p className="text-[10px] text-muted-foreground truncate">{o.to_email}</p>
                </td>
                <td className="p-1.5">{o.level}</td>
                <td className="p-1.5 text-right num">{eur(o.total_ht)}</td>
                <td className="p-1.5">
                  <div className="flex flex-col items-end gap-0.5">
                    <Input type="number" min="0" step="0.01"
                           value={e.quoted_ht ?? o.quoted_ht ?? ""}
                           onChange={(ev) => setE(o.ref, "quoted_ht", ev.target.value)}
                           placeholder="—" data-testid={`pc-order-${i}-quote-input`}
                           className="rounded-sm h-7 w-28 text-right num text-xs" />
                    {delta !== null && (
                      <span className={`text-[10px] num ${delta > 0 ? "text-red-500" : "text-emerald-600"}`}>
                        {delta > 0 ? "+" : ""}{num(delta, 1)} % vs étude
                      </span>
                    )}
                    {isBest && (
                      <Badge className="rounded-sm gap-1 text-[9px] bg-emerald-500/15 text-emerald-600 border border-emerald-500/40 hover:bg-emerald-500/15"
                             data-testid={`pc-order-${i}-best`}>
                        <Trophy className="h-2.5 w-2.5" /> Meilleure offre
                      </Badge>
                    )}
                  </div>
                </td>
                <td className="p-1.5">
                  <select value={e.status || o.status || "en_attente"}
                          onChange={(ev) => setE(o.ref, "status", ev.target.value)}
                          data-testid={`pc-order-${i}-status-select`}
                          className="h-7 rounded-sm border border-input bg-background px-1 text-xs">
                    {Object.entries(STATUS_LABELS).map(([k, v]) => (
                      <option key={k} value={k}>{v}</option>
                    ))}
                  </select>
                </td>
                <td className="p-1.5">
                  <button onClick={() => save(o)}
                          className="inline-flex items-center gap-1 text-[10px] text-primary hover:text-orange-600 underline underline-offset-2"
                          data-testid={`pc-order-${i}-save-btn`}>
                    <Save className="h-3 w-3" /> Enregistrer
                  </button>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </section>
  );
}
