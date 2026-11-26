import { useState } from "react";
import { toast } from "sonner";
import { UserPlus } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Checkbox } from "@/components/ui/checkbox";
import {
  Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle, DialogTrigger,
} from "@/components/ui/dialog";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { api } from "@/lib/api";

const COPY = {
  pt: {
    button: "Criar conta", title: "Criar uma conta",
    desc: "A conta é criada com uma palavra-passe provisória. No primeiro início de sessão, o cliente escolhe a sua palavra-passe e acrescenta o telefone.",
    email: "E-mail", company: "Empresa", name: "Nome do contacto (opcional)",
    phone: "Telefone (opcional)", nif: "NIF / NIPC (opcional)", pwd: "Palavra-passe provisória (mín. 8)",
    type: "Tipo de conta", plan: "Plano", particulier: "Particular", pro: "Pro", business: "Business",
    welcome: "Enviar e-mail ao cliente a avisar que a conta está pronta (sem a palavra-passe)",
    cancel: "Cancelar", create: "Criar a conta", created: "Conta criada", mailed: "e-mail enviado",
    mailFail: "e-mail não enviado", fail: "Criação impossível",
  },
  fr: {
    button: "Créer un compte", title: "Créer un compte",
    desc: "Le compte est créé avec un mot de passe provisoire. À la première connexion, le client choisit son mot de passe et ajoute son téléphone.",
    email: "E-mail", company: "Entreprise", name: "Nom du contact (optionnel)",
    phone: "Téléphone (optionnel)", nif: "SIRET (optionnel)", pwd: "Mot de passe provisoire (min. 8)",
    type: "Type de compte", plan: "Formule", particulier: "Particulier", pro: "Pro", business: "Business",
    welcome: "Envoyer un e-mail au client pour l'avertir que son compte est prêt (sans le mot de passe)",
    cancel: "Annuler", create: "Créer le compte", created: "Compte créé", mailed: "e-mail envoyé",
    mailFail: "e-mail non envoyé", fail: "Création impossible",
  },
};

const EMPTY = { email: "", company_name: "", name: "", phone: "", siret: "", temp_password: "",
  account_type: "pro_business", plan: "pro", send_welcome_email: false };

export default function CreateAccountDialog({ onCreated, lang = "pt" }) {
  const c = COPY[lang] || COPY.pt;
  const [open, setOpen] = useState(false);
  const [f, setF] = useState(EMPTY);
  const [busy, setBusy] = useState(false);
  const set = (k) => (e) => setF({ ...f, [k]: e?.target ? e.target.value : e });

  const submit = async (e) => {
    e.preventDefault();
    setBusy(true);
    try {
      const { data } = await api.post("/admin/users", { ...f, lang });
      const mail = f.send_welcome_email ? ` · ${data.email_sent ? c.mailed : c.mailFail}` : "";
      toast.success(`${c.created} : ${data.user.email}${mail}`);
      setF(EMPTY);
      setOpen(false);
      onCreated?.(data.user);
    } catch (err) {
      const d = err?.response?.data?.detail;
      toast.error(typeof d === "string" ? d : c.fail);
    } finally {
      setBusy(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button className="rounded-sm gap-2" data-testid="admin-create-user-btn">
          <UserPlus className="h-4 w-4" /> {c.button}
        </Button>
      </DialogTrigger>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>{c.title}</DialogTitle>
          <DialogDescription>{c.desc}</DialogDescription>
        </DialogHeader>
        <form onSubmit={submit} className="space-y-3" data-testid="admin-create-user-form" autoComplete="off">
          <div className="grid gap-1">
            <Label htmlFor="cu-email" className="text-xs">{c.email}</Label>
            <Input id="cu-email" type="email" required value={f.email} onChange={set("email")}
                   data-testid="admin-create-user-email" autoComplete="off" />
          </div>
          <div className="grid gap-1">
            <Label htmlFor="cu-company" className="text-xs">{c.company}</Label>
            <Input id="cu-company" value={f.company_name} onChange={set("company_name")} maxLength={120}
                   data-testid="admin-create-user-company" />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div className="grid gap-1">
              <Label htmlFor="cu-name" className="text-xs">{c.name}</Label>
              <Input id="cu-name" value={f.name} onChange={set("name")} maxLength={120} />
            </div>
            <div className="grid gap-1">
              <Label htmlFor="cu-phone" className="text-xs">{c.phone}</Label>
              <Input id="cu-phone" type="tel" value={f.phone} onChange={set("phone")} maxLength={20} />
            </div>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div className="grid gap-1">
              <Label htmlFor="cu-nif" className="text-xs">{c.nif}</Label>
              <Input id="cu-nif" value={f.siret} onChange={set("siret")} maxLength={20} />
            </div>
            <div className="grid gap-1">
              <Label htmlFor="cu-pwd" className="text-xs">{c.pwd}</Label>
              <Input id="cu-pwd" type="text" required minLength={8} value={f.temp_password}
                     onChange={set("temp_password")} autoComplete="new-password"
                     data-testid="admin-create-user-password" />
            </div>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div className="grid gap-1">
              <Label className="text-xs">{c.type}</Label>
              <Select value={f.account_type} onValueChange={set("account_type")}>
                <SelectTrigger className="rounded-sm" data-testid="admin-create-user-type"><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="particulier">{c.particulier}</SelectItem>
                  <SelectItem value="pro">{c.pro}</SelectItem>
                  <SelectItem value="pro_business">{c.business}</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="grid gap-1">
              <Label className="text-xs">{c.plan}</Label>
              <Select value={f.plan} onValueChange={set("plan")}>
                <SelectTrigger className="rounded-sm" data-testid="admin-create-user-plan"><SelectValue /></SelectTrigger>
                <SelectContent>
                  {["free", "premium", "pro"].map((p) => <SelectItem key={p} value={p}>{p}</SelectItem>)}
                </SelectContent>
              </Select>
            </div>
          </div>
          <label className="flex items-start gap-2 text-xs cursor-pointer">
            <Checkbox checked={f.send_welcome_email}
                      onCheckedChange={(v) => setF({ ...f, send_welcome_email: v === true })}
                      data-testid="admin-create-user-welcome" />
            <span>{c.welcome}</span>
          </label>
          <DialogFooter>
            <Button type="button" variant="outline" className="rounded-sm" onClick={() => setOpen(false)}>{c.cancel}</Button>
            <Button type="submit" className="rounded-sm" disabled={busy} data-testid="admin-create-user-submit">{c.create}</Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
