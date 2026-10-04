import { useEffect, useState } from "react";
import { toast } from "sonner";
import { Handshake, Send, Sparkles, Star, MapPin, Wrench } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Badge } from "@/components/ui/badge";
import { api, eur2 } from "@/lib/api";
import { SectionTitle } from "@/components/Bits";
import { useAuth } from "@/context/AuthContext";

export default function Marketplace() {
  const { user } = useAuth();
  const [pros, setPros] = useState([]);
  const [flags, setFlags] = useState({});
  const [form, setForm] = useState({
    name: "", email: "", phone: "", address: "",
    budget: "", surface: "", delay_days: "", description: "", trade: "",
  });
  const [busy, setBusy] = useState(false);
  const [preview, setPreview] = useState(null);

  useEffect(() => {
    api.get("/marketplace/pros").then(({ data }) => setPros(data.pros || [])).catch(() => {});
    api.get("/billing/flags").then(({ data }) => setFlags(data)).catch(() => {});
  }, []);

  const submit = async (e) => {
    e.preventDefault();
    if (!form.name || !form.email || !form.description) {
      return toast.error("Nome, email e descrição são obrigatórios");
    }
    setBusy(true);
    try {
      const payload = {
        ...form,
        budget: form.budget ? Number(form.budget) : null,
        surface: form.surface ? Number(form.surface) : null,
        delay_days: form.delay_days ? Number(form.delay_days) : null,
      };
      const { data } = await api.post("/marketplace/leads", payload);
      setPreview(data);
      toast.success("Pedido enviado — pontuação de qualidade: " + data.score + "/100");
      setForm({ name: user?.name || "", email: user?.email || "", phone: "", address: "",
                budget: "", surface: "", delay_days: "", description: "", trade: "" });
    } catch (err) {
      toast.error(err?.response?.data?.detail || "Impossível enviar o pedido");
    } finally { setBusy(false); }
  };

  return (
    <div className="grid gap-10">
      <SectionTitle over="Marketplace ConstruPilot" title="Trouvez un professionnel vérifié pour vos travaux">
        Décrivez votre projet — nous le transmettons à des artisans ConstruPilot Verified de votre
        région. Vous recevez les propositions directement dans votre boîte mail.
      </SectionTitle>

      {!flags.marketplace_enabled && (
        <div className="surface p-4 flex items-center gap-3 bg-amber-500/5 border-amber-500/40" data-testid="marketplace-beta-banner">
          <Sparkles className="h-4 w-4 text-amber-500" />
          <p className="text-sm">
            <b>Bêta</b> — le réseau ConstruPilot Pro est en cours d'ouverture. Votre demande sera traitée
            manuellement pendant la phase de lancement.
          </p>
        </div>
      )}

      <div className="grid md:grid-cols-3 gap-6">
        <form onSubmit={submit} className="md:col-span-2 surface p-6 grid gap-4" data-testid="marketplace-form">
          <div className="grid sm:grid-cols-2 gap-4">
            <div className="grid gap-2">
              <Label>Nom complet *</Label>
              <Input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })}
                     className="rounded-sm h-11" required data-testid="ld-name" />
            </div>
            <div className="grid gap-2">
              <Label>Email *</Label>
              <Input type="email" value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })}
                     className="rounded-sm h-11" required data-testid="ld-email" />
            </div>
            <div className="grid gap-2">
              <Label>Téléphone</Label>
              <Input value={form.phone} onChange={(e) => setForm({ ...form, phone: e.target.value })}
                     className="rounded-sm h-11" data-testid="ld-phone" />
            </div>
            <div className="grid gap-2">
              <Label>Adresse chantier</Label>
              <Input value={form.address} onChange={(e) => setForm({ ...form, address: e.target.value })}
                     className="rounded-sm h-11" placeholder="Rue, code postal, ville" data-testid="ld-address" />
            </div>
            <div className="grid gap-2">
              <Label>Budget approximatif €</Label>
              <Input type="number" value={form.budget} onChange={(e) => setForm({ ...form, budget: e.target.value })}
                     className="rounded-sm h-11 num" data-testid="ld-budget" />
            </div>
            <div className="grid gap-2">
              <Label>Surface m²</Label>
              <Input type="number" value={form.surface} onChange={(e) => setForm({ ...form, surface: e.target.value })}
                     className="rounded-sm h-11 num" data-testid="ld-surface" />
            </div>
            <div className="grid gap-2">
              <Label>Démarrage souhaité (jours)</Label>
              <Input type="number" value={form.delay_days} onChange={(e) => setForm({ ...form, delay_days: e.target.value })}
                     className="rounded-sm h-11 num" placeholder="ex : 60" data-testid="ld-delay" />
            </div>
            <div className="grid gap-2">
              <Label>Métier principal</Label>
              <Input value={form.trade} onChange={(e) => setForm({ ...form, trade: e.target.value })}
                     className="rounded-sm h-11" placeholder="Plomberie, électricité…" data-testid="ld-trade" />
            </div>
          </div>
          <div className="grid gap-2">
            <Label>Décrivez votre projet *</Label>
            <Textarea rows={4} value={form.description}
                      onChange={(e) => setForm({ ...form, description: e.target.value })}
                      required data-testid="ld-description" className="rounded-sm"
                      placeholder="Ex : rénovation complète appartement 65m² à Paris 11e — cuisine ouverte, salle de bain, peinture, sols. Démarrage souhaité en avril." />
          </div>
          <Button type="submit" disabled={busy} data-testid="ld-submit"
                  className="rounded-sm gap-2 hover:bg-orange-600 hover:text-white justify-self-start">
            <Send className="h-4 w-4" /> {busy ? "A enviar…" : "Enviar o pedido"}
          </Button>
        </form>

        <div className="surface p-6 grid gap-4">
          <div className="flex items-center gap-2">
            <Handshake className="h-4 w-4 text-primary" />
            <p className="overline">Professionnels vérifiés</p>
          </div>
          <p className="num text-3xl font-extrabold" data-testid="marketplace-pro-count">{pros.length}</p>
          <p className="text-xs text-muted-foreground">
            Artisans ConstruPilot Verified — identité, SIREN, assurance et avis vérifiés.
          </p>
          <ul className="grid gap-3 mt-2">
            {pros.slice(0, 5).map((p) => (
              <li key={p.user_id} className="border border-border rounded-sm p-3">
                <div className="font-display font-semibold text-sm flex items-center gap-2">
                  {p.company_name}
                  {p.badge && <Badge variant="outline" className="rounded-sm text-[10px]">{p.badge}</Badge>}
                </div>
                <p className="text-xs text-muted-foreground mt-1 flex items-center gap-2">
                  <Wrench className="h-3 w-3" /> {(p.trades || []).slice(0, 3).join(", ")}
                </p>
                {p.zones?.length > 0 && (
                  <p className="text-xs text-muted-foreground mt-1 flex items-center gap-2">
                    <MapPin className="h-3 w-3" /> {p.zones.slice(0, 3).join(", ")}
                  </p>
                )}
              </li>
            ))}
            {pros.length === 0 && (
              <p className="text-xs text-muted-foreground" data-testid="marketplace-pros-empty">
                Le réseau se construit — soyez parmi les premiers à publier une demande.
              </p>
            )}
          </ul>
        </div>
      </div>

      {preview && (
        <div className="surface p-6" data-testid="marketplace-preview">
          <div className="flex items-center gap-2">
            <Star className="h-4 w-4 text-primary" />
            <p className="overline">Votre demande — score qualité</p>
          </div>
          <p className="num font-display text-4xl font-extrabold mt-2">{preview.score}/100</p>
          <p className="text-sm text-muted-foreground mt-1">Avaliação: {preview.rating} · Categoria: {preview.tier}</p>
          <p className="text-xs text-muted-foreground mt-3">
            Les professionnels reçoivent une notification lorsque leur zone/métier correspond à votre projet.
          </p>
        </div>
      )}
    </div>
  );
}
