import { useState } from "react";
import { toast } from "sonner";
import { HardHat } from "lucide-react";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger, DialogDescription,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { api } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";

export const LeadDialog = ({ projectId, budget, description, trigger, label = "Receber uma proposta ConstruPilot" }) => {
  const { user } = useAuth();
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [form, setForm] = useState({
    name: user?.name || "", email: user?.email || "", phone: "", address: "",
    availability: "", budget: budget || "", description: description || "",
  });
  const set = (k) => (e) => setForm({ ...form, [k]: e.target.value });

  const submit = async (e) => {
    e.preventDefault();
    setBusy(true);
    try {
      await api.post("/leads", {
        ...form,
        budget: form.budget ? Number(form.budget) : null,
        project_id: projectId || null,
      });
      toast.success("Pedido transmitido ao ConstruPilot — um consultor contacta-o em 48 h.");
      setOpen(false);
    } catch (err) {
      toast.error(err?.response?.data?.detail || "Envio impossível");
    } finally {
      setBusy(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        {trigger || (
          <Button data-testid="open-lead-dialog-btn" className="rounded-sm gap-2 hover:bg-orange-600 hover:text-white">
            <HardHat className="h-4 w-4" /> {label}
          </Button>
        )}
      </DialogTrigger>
      <DialogContent className="rounded-md max-w-lg max-h-[90vh] overflow-y-auto" data-testid="lead-dialog">
        <DialogHeader>
          <DialogTitle className="font-display text-xl">Mandar executar estes trabalhos pela ConstruPilot</DialogTitle>
          <DialogDescription>
            O seu projeto, as suas superfícies e a estimativa gerada são transmitidos automaticamente à nossa equipa.
          </DialogDescription>
        </DialogHeader>
        <form onSubmit={submit} className="grid gap-4">
          <div className="grid sm:grid-cols-2 gap-4">
            <div className="grid gap-2">
              <Label>Nome completo</Label>
              <Input required value={form.name} onChange={set("name")} data-testid="lead-name-input" className="rounded-sm" />
            </div>
            <div className="grid gap-2">
              <Label>Email</Label>
              <Input required type="email" value={form.email} onChange={set("email")} data-testid="lead-email-input" className="rounded-sm" />
            </div>
            <div className="grid gap-2">
              <Label>Telefone</Label>
              <Input required value={form.phone} onChange={set("phone")} data-testid="lead-phone-input" className="rounded-sm" />
            </div>
            <div className="grid gap-2">
              <Label>Orçamento (€)</Label>
              <Input type="number" value={form.budget} onChange={set("budget")} data-testid="lead-budget-input" className="rounded-sm num" />
            </div>
          </div>
          <div className="grid gap-2">
            <Label>Morada da obra</Label>
            <Input value={form.address} onChange={set("address")} data-testid="lead-address-input" className="rounded-sm" />
          </div>
          <div className="grid gap-2">
            <Label>Disponibilidades</Label>
            <Input placeholder="Ex: em dias de semana após as 17 h" value={form.availability} onChange={set("availability")} data-testid="lead-availability-input" className="rounded-sm" />
          </div>
          <div className="grid gap-2">
            <Label>Descrição dos trabalhos</Label>
            <Textarea rows={4} value={form.description} onChange={set("description")} data-testid="lead-description-input" className="rounded-sm" />
          </div>
          <Button type="submit" disabled={busy} data-testid="submit-lead-btn" className="rounded-sm hover:bg-orange-600 hover:text-white">
            {busy ? "A enviar…" : "Enviar o meu pedido"}
          </Button>
        </form>
      </DialogContent>
    </Dialog>
  );
};
