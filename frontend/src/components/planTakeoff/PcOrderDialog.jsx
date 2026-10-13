import { useState } from "react";
import { toast } from "sonner";
import { FileDown, Send } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter,
} from "@/components/ui/dialog";
import { api } from "@/lib/api";

export default function PcOrderDialog({ open, onClose, planId, levelIndex, levelName }) {
  const [supplier, setSupplier] = useState("");
  const [email, setEmail] = useState("");
  const [notes, setNotes] = useState("");
  const [busy, setBusy] = useState(false);

  const download = async () => {
    setBusy(true);
    try {
      const base = process.env.REACT_APP_BACKEND_URL;
      const qs = new URLSearchParams({ level: levelIndex, supplier, notes }).toString();
      const res = await fetch(`${base}/api/takeoffs/${planId}/pc-study/purchase-order?${qs}`,
        { credentials: "include" });
      if (!res.ok) throw new Error((await res.json())?.detail || "Impossível gerar");
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url; a.download = `bon-commande-${levelName}.pdf`;
      document.body.appendChild(a); a.click(); a.remove();
      URL.revokeObjectURL(url);
      toast.success("Ordem de encomenda descarregada");
    } catch (e) { toast.error(e.message || "Impossível gerar"); }
    finally { setBusy(false); }
  };

  const send = async () => {
    if (!email.trim()) return toast.error("Introduza o email do armazenista");
    setBusy(true);
    try {
      const { data } = await api.post(`/takeoffs/${planId}/pc-study/purchase-order/send`, {
        level_index: levelIndex, supplier_email: email.trim(),
        supplier_name: supplier, notes,
      });
      toast.success(`Nota de encomenda${data.ref}enviado para${data.sent_to} — ${data.total_ht} € HT`);
      onClose();
    } catch (e) { toast.error(e?.response?.data?.detail || "Envio impossível"); }
    finally { setBusy(false); }
  };

  return (
    <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="rounded-sm" data-testid="pc-order-dialog">
        <DialogHeader>
          <DialogTitle>Ordem de compra — {levelName}</DialogTitle>
          <DialogDescription>
            Materiais do nível (+5 % de desperdícios, arredondados à embalagem) prontos a enviar ao seu fornecedor. Preços indicativos do seu estudo.
          </DialogDescription>
        </DialogHeader>
        <div className="grid gap-3">
          <div className="grid gap-1.5">
            <Label htmlFor="pc-order-supplier">Nome do fornecedor (opcional)</Label>
            <Input id="pc-order-supplier" placeholder="Ex : Point.P Marseille"
                   value={supplier} onChange={(e) => setSupplier(e.target.value)}
                   data-testid="pc-order-supplier-input" className="rounded-sm" />
          </div>
          <div className="grid gap-1.5">
            <Label htmlFor="pc-order-email">Email do armazém (para envio direto)</Label>
            <Input id="pc-order-email" type="email" placeholder="commandes@negoce.fr"
                   value={email} onChange={(e) => setEmail(e.target.value)}
                   data-testid="pc-order-email-input" className="rounded-sm" />
          </div>
          <div className="grid gap-1.5">
            <Label htmlFor="pc-order-notes">Notas (entrega, acesso à obra…)</Label>
            <Textarea id="pc-order-notes" rows={3}
                      placeholder="Entrega desejada semana 37, camião-grua necessário…"
                      value={notes} onChange={(e) => setNotes(e.target.value)}
                      data-testid="pc-order-notes-input" className="rounded-sm" />
          </div>
        </div>
        <DialogFooter className="gap-2">
          <Button variant="outline" onClick={download} disabled={busy}
                  className="rounded-sm gap-2 mr-auto" data-testid="pc-order-download-btn">
            <FileDown className="h-3.5 w-3.5" /> Descarregar o PDF
          </Button>
          <Button variant="outline" onClick={onClose} className="rounded-sm"
                  data-testid="pc-order-cancel">Fechar</Button>
          <Button onClick={send} disabled={busy || !email.trim()} className="rounded-sm gap-2"
                  data-testid="pc-order-send-btn">
            <Send className="h-3.5 w-3.5" /> {busy ? "…" : "Enviar ao armazenista"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
