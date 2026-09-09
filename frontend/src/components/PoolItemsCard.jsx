import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";
import { Waves, FileText, Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { api } from "@/lib/api";

const eur = (n) => `${Number(n || 0).toLocaleString("fr-FR", { minimumFractionDigits: 2, maximumFractionDigits: 2 })} €`;

export const PoolItemsCard = ({ pool, isPro, title }) => {
  const nav = useNavigate();
  const [busy, setBusy] = useState(false);
  if (!pool?.lines?.length) return null;
  const g = pool.geometry || {};

  const createQuote = async () => {
    setBusy(true);
    try {
      const lines = pool.lines.map((l) => ({
        designation: l.designation, description: "", unit: l.unit, qty: l.qty,
        unit_price_ht: l.unit_price_ht, cost_price_ht: l.cost_price_ht || 0, vat_rate: l.vat_rate || 20, category: "Piscine",
      }));
      const { data } = await api.post("/documents", { doc_type: "quote", title: title || `Piscine ${g.length} × ${g.width} m`, lines });
      toast.success("Devis piscine créé");
      nav(`/devis-editeur/${data.doc_id}`);
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Création du devis impossible");
    } finally { setBusy(false); }
  };

  return (
    <div className="surface p-5 rounded-xl" data-testid="pool-items-card">
      <div className="flex flex-wrap items-center gap-3">
        <Waves className="h-5 w-5 text-primary" />
        <h3 className="font-display font-bold text-lg">Ouvrages piscine proposés (bibliothèque ConstruPilot)</h3>
        <span className="text-xs text-muted-foreground" data-testid="pool-geometry">
          Bassin ≈ {g.length} × {g.width} m · profondeur {g.depth} m · {g.perim} ml de margelles · {g.walls} m² de parois · fouille {g.excav_m3} m³
        </span>
        {isPro && (
          <Button size="sm" onClick={createQuote} disabled={busy} className="rounded-sm gap-2 ml-auto" data-testid="pool-create-quote-btn">
            {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <FileText className="h-4 w-4" />} Créer le devis ({pool.lines.length} lignes)
          </Button>
        )}
      </div>
      <div className="mt-4 overflow-x-auto">
        <table className="w-full text-sm" data-testid="pool-items-table">
          <thead className="text-[11px] uppercase tracking-wide text-muted-foreground">
            <tr className="border-b border-border/60">
              <th className="text-left py-2 pr-2">Ouvrage</th>
              <th className="text-right py-2 px-2">Qté</th>
              <th className="text-left py-2 px-2">Unité</th>
              <th className="text-right py-2 px-2">PU HT</th>
              <th className="text-right py-2 pl-2">Total HT</th>
            </tr>
          </thead>
          <tbody>
            {pool.lines.map((l, i) => (
              <tr key={i} className="border-b border-border/30" data-testid={`pool-item-${i}`}>
                <td className="py-1.5 pr-2">{l.designation}</td>
                <td className="py-1.5 px-2 text-right num">{l.qty}</td>
                <td className="py-1.5 px-2 text-muted-foreground">{l.unit}</td>
                <td className="py-1.5 px-2 text-right num">{eur(l.unit_price_ht)}</td>
                <td className="py-1.5 pl-2 text-right num font-medium">{eur(l.total_ht)}</td>
              </tr>
            ))}
          </tbody>
          <tfoot>
            <tr>
              <td colSpan={4} className="py-2 text-right font-semibold">Total bordereau HT</td>
              <td className="py-2 pl-2 text-right num font-bold text-primary" data-testid="pool-items-total">{eur(pool.total_ht)}</td>
            </tr>
          </tfoot>
        </table>
      </div>
      <p className="mt-2 text-[11px] text-muted-foreground">Quantités calculées pour un bassin rectangulaire 2:1 à partir de la surface saisie — ajustez-les dans l'éditeur de devis.</p>
    </div>
  );
};
