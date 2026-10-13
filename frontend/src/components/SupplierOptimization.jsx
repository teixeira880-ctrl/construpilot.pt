import { ShoppingCart } from "lucide-react";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { eur, eur2 } from "@/lib/api";

export const SupplierOptimization = ({ optim }) => {
  if (!optim) return null;
  return (
    <div className="grid gap-4" data-testid="supplier-optimization">
      <div className="grid sm:grid-cols-3 gap-4">
        <div className="surface p-6">
          <p className="overline text-muted-foreground">Tudo em {optim.best_single?.supplier}</p>
          <p className="num mt-3 text-xl font-bold">{eur(optim.best_single?.total)}</p>
        </div>
        <div className="surface p-6 border-primary">
          <p className="overline">Multi-fornecedores</p>
          <p className="num mt-3 text-xl font-bold text-primary">{eur(optim.multi_supplier?.total)}</p>
        </div>
        <div className="surface p-6">
          <p className="overline text-muted-foreground">Poupança</p>
          <p className="num mt-3 text-xl font-bold text-emerald-500">{eur(optim.savings)}</p>
        </div>
      </div>
      <div className="surface overflow-x-auto">
        <Table>
          <TableHeader>
            <TableRow className="bg-secondary/60 hover:bg-secondary/60">
              <TableHead>Artigo</TableHead>
              <TableHead className="text-right">Qtd.</TableHead>
              <TableHead>Fornecedor</TableHead>
              <TableHead className="text-right">PU</TableHead>
              <TableHead className="text-right">Total</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {(optim.lines || []).map((l, i) => (
              <TableRow key={i} className="even:bg-muted/30">
                <TableCell>{l.name}</TableCell>
                <TableCell className="num text-right">{l.quantity}</TableCell>
                <TableCell>{l.supplier}</TableCell>
                <TableCell className="num text-right">{eur2(l.unit_price)}</TableCell>
                <TableCell className="num text-right font-semibold text-primary">{eur2(l.total)}</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>
      <p className="text-xs text-muted-foreground flex items-center gap-2">
        <ShoppingCart className="h-3 w-3" /> Modo {optim.mode} — preço de demonstração, ligue as API de fornecedores para preços reais.
      </p>
    </div>
  );
};

export default SupplierOptimization;
