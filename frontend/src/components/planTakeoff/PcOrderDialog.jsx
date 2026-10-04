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
      const token = localStorage.getItem("construpilot_token");
      const qs = new URLSearchParams({ level: levelIndex, supplier, notes }).toString();
      const res = await fetch(`${base}/api/takeoffs/${planId}/pc-study/purchase-order?${qs}`,
        { headers: { Authorization: `Bearer ${token}` }, credentials: "include" });
      if (!res.ok) throw new Error((await res.json())?.detail || "Impossível gerar");
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url; a.download = `nota-de-encomenda-${levelName}.pdf`;
      document.body.appendChild(a); a.click(); a.remove();
      URL.revokeObjectURL(url);
      toast.success("Ordem de encomenda descarregada");
    } catch (e) { toast.error(e.message || "Impossível gerar"); }
    finally { setBusy(false); }
  };

  const send = async () => {
    if (!email.trim()) return toast.error("Saisissez l'email du négoce");
    setBusy(true);
    try {
      const { data } = await api.post(`/takeoffs/${planId}/pc-study/purchase-order/send`, {
        level_index: levelIndex, supplier_email: email.trim(),
        supplier_name: supplier, notes,
      });
      toast.success(`Nota de encomenda ${data.ref} enviada para ${data.sent_to} — ${data.total_ht} € s/ IVA`);
      onClose();
    } catch (e) { toast.error(e?.response?.data?.detail || "Impossível enviar"); }
    finally { setBusy(false); }
  };

  return (
    <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="rounded-sm" data-testid="pc-order-dialog">
        <DialogHeader>
          <DialogTitle>Bon de commande — {levelName}</DialogTitle>
          <DialogDescription>
            Matériaux du niveau (+5 % de chutes, arrondis au conditionnement) prêts
            à envoyer à votre négoce. Prix indicatifs de votre étude.
          </DialogDescription>
        </DialogHeader>
        <div className="grid gap-3">
          <div className="grid gap-1.5">
            <Label htmlFor="pc-order-supplier">Nom du négoce (optionnel)</Label>
            <Input id="pc-order-supplier" placeholder="Ex : Point.P Marseille"
                   value={supplier} onChange={(e) => setSupplier(e.target.value)}
                   data-testid="pc-order-supplier-input" className="rounded-sm" />
          </div>
          <div className="grid gap-1.5">
            <Label htmlFor="pc-order-email">Email du négoce (pour l'envoi direct)</Label>
            <Input id="pc-order-email" type="email" placeholder="commandes@negoce.fr"
                   value={email} onChange={(e) => setEmail(e.target.value)}
                   data-testid="pc-order-email-input" className="rounded-sm" />
          </div>
          <div className="grid gap-1.5">
            <Label htmlFor="pc-order-notes">Notes (livraison, accès chantier…)</Label>
            <Textarea id="pc-order-notes" rows={3}
                      placeholder="Livraison souhaitée semaine 37, camion-grue nécessaire…"
                      value={notes} onChange={(e) => setNotes(e.target.value)}
                      data-testid="pc-order-notes-input" className="rounded-sm" />
          </div>
        </div>
        <DialogFooter className="gap-2">
          <Button variant="outline" onClick={download} disabled={busy}
                  className="rounded-sm gap-2 mr-auto" data-testid="pc-order-download-btn">
            <FileDown className="h-3.5 w-3.5" /> Télécharger le PDF
          </Button>
          <Button variant="outline" onClick={onClose} className="rounded-sm"
                  data-testid="pc-order-cancel">Fermer</Button>
          <Button onClick={send} disabled={busy || !email.trim()} className="rounded-sm gap-2"
                  data-testid="pc-order-send-btn">
            <Send className="h-3.5 w-3.5" /> {busy ? "…" : "Envoyer au négoce"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
