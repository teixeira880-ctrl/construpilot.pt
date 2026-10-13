import { useState } from "react";
import { toast } from "sonner";
import { Building2, ShieldCheck, Server, Zap, Send, ArrowRight, Users } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { api } from "@/lib/api";
import { SectionTitle } from "@/components/Bits";

export default function Enterprise() {
  const [form, setForm] = useState({
    company_name: "", contact_name: "", contact_email: "", contact_phone: "",
    company_size: "50-200", role: "", use_case: "",
    volume_estimate: "", sso_required: false, sla_required: false, message: "",
  });
  const [busy, setBusy] = useState(false);
  const [ok, setOk] = useState(false);

  const submit = async (e) => {
    e.preventDefault();
    setBusy(true);
    try {
      await api.post("/enterprise/contact", form);
      setOk(true);
      toast.success("Merci — notre équipe vous recontacte sous 48 h");
    } catch (err) { toast.error(err?.response?.data?.detail || "Envoi impossible"); }
    finally { setBusy(false); }
  };

  if (ok) {
    return (
      <div className="max-w-lg mx-auto surface p-10 text-center mt-10" data-testid="enterprise-success">
        <ShieldCheck className="h-12 w-12 mx-auto text-emerald-500" />
        <p className="font-display text-3xl font-extrabold mt-4">Demande reçue</p>
        <p className="text-sm text-muted-foreground mt-2">
          Notre équipe vous contactera sous 48 h ouvrées avec une proposition détaillée.
        </p>
      </div>
    );
  }

  return (
    <div className="grid gap-10">
      <SectionTitle as="h1" over="ConstruPilot Enterprise" title="Parlez à notre équipe pour votre organisation">
        SSO, SLA, API dédiée, intégrations sur mesure, reporting avancé.
        Pour les promoteurs, distributeurs, assureurs et réseaux d'artisans.
      </SectionTitle>

      <div className="grid md:grid-cols-3 gap-4">
        {[
          { icon: Building2, title: "Grands comptes", desc: "Promoteurs, assureurs, franchisés, groupes immobiliers." },
          { icon: Server, title: "SSO & API dédiée", desc: "Authentification centralisée, endpoints privés, sandbox." },
          { icon: Zap, title: "Engagement de service", desc: "Niveau de disponibilité, support prioritaire et interlocuteur dédié définis au contrat." },
        ].map((f, i) => (
          <div key={i} className="surface p-6 grid gap-3">
            <span className="h-10 w-10 grid place-items-center rounded-sm bg-primary/15 text-primary">
              <f.icon className="h-5 w-5" />
            </span>
            <p className="font-display font-bold">{f.title}</p>
            <p className="text-sm text-muted-foreground">{f.desc}</p>
          </div>
        ))}
      </div>

      <form onSubmit={submit} className="surface p-6 grid gap-4" data-testid="enterprise-form">
        <div className="grid sm:grid-cols-2 gap-4">
          <div className="grid gap-2">
            <Label>Entreprise *</Label>
            <Input required value={form.company_name} onChange={(e) => setForm({ ...form, company_name: e.target.value })} data-testid="ent-company" className="rounded-sm h-11" />
          </div>
          <div className="grid gap-2">
            <Label>Vos nom & prénom *</Label>
            <Input required value={form.contact_name} onChange={(e) => setForm({ ...form, contact_name: e.target.value })} data-testid="ent-name" className="rounded-sm h-11" />
          </div>
          <div className="grid gap-2">
            <Label>Email professionnel *</Label>
            <Input type="email" required value={form.contact_email} onChange={(e) => setForm({ ...form, contact_email: e.target.value })} data-testid="ent-email" className="rounded-sm h-11" />
          </div>
          <div className="grid gap-2">
            <Label>Téléphone</Label>
            <Input value={form.contact_phone} onChange={(e) => setForm({ ...form, contact_phone: e.target.value })} data-testid="ent-phone" className="rounded-sm h-11" />
          </div>
          <div className="grid gap-2">
            <Label>Fonction</Label>
            <Input value={form.role} onChange={(e) => setForm({ ...form, role: e.target.value })} placeholder="Direction, CTO, achats…" className="rounded-sm h-11" />
          </div>
          <div className="grid gap-2">
            <Label>Taille de l'entreprise</Label>
            <Select value={form.company_size} onValueChange={(v) => setForm({ ...form, company_size: v })}>
              <SelectTrigger className="rounded-sm h-11" data-testid="ent-size"><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="< 50">Moins de 50</SelectItem>
                <SelectItem value="50-200">50 à 200</SelectItem>
                <SelectItem value="200-1000">200 à 1 000</SelectItem>
                <SelectItem value="> 1000">Plus de 1 000</SelectItem>
              </SelectContent>
            </Select>
          </div>
        </div>
        <div className="grid gap-2">
          <Label>Décrivez votre cas d'usage *</Label>
          <Textarea rows={4} required value={form.use_case} onChange={(e) => setForm({ ...form, use_case: e.target.value })} data-testid="ent-usecase" className="rounded-sm"
                    placeholder="Ex : nous souhaitons intégrer un simulateur de rénovation sur notre parc immobilier de 12 000 logements pour piloter les rénovations énergétiques…" />
        </div>
        <div className="grid sm:grid-cols-2 gap-4">
          <div className="grid gap-2">
            <Label>Volume mensuel estimé</Label>
            <Input value={form.volume_estimate} onChange={(e) => setForm({ ...form, volume_estimate: e.target.value })} placeholder="Ex : 5 000 estimations / mois" className="rounded-sm h-11" />
          </div>
          <div className="flex flex-col gap-2 pt-6">
            <label className="flex items-center gap-2 text-sm">
              <input type="checkbox" checked={form.sso_required} onChange={(e) => setForm({ ...form, sso_required: e.target.checked })} data-testid="ent-sso" />
              SSO requis (SAML / OIDC)
            </label>
            <label className="flex items-center gap-2 text-sm">
              <input type="checkbox" checked={form.sla_required} onChange={(e) => setForm({ ...form, sla_required: e.target.checked })} data-testid="ent-sla" />
              SLA 99,9 % avec pénalités
            </label>
          </div>
        </div>
        <div className="grid gap-2">
          <Label>Message complémentaire</Label>
          <Textarea rows={3} value={form.message} onChange={(e) => setForm({ ...form, message: e.target.value })} className="rounded-sm" />
        </div>
        <Button type="submit" disabled={busy} data-testid="ent-submit" className="rounded-sm gap-2 justify-self-start hover:bg-orange-600 hover:text-white">
          <Send className="h-4 w-4" /> {busy ? "Envoi…" : "Envoyer ma demande"}
          <ArrowRight className="h-4 w-4" />
        </Button>
        <p className="text-xs text-muted-foreground">
          <Users className="inline h-3 w-3 mr-1" /> Vos données ne sont utilisées que pour vous
          recontacter — jamais partagées.
        </p>
      </form>
    </div>
  );
}
