import { useEffect, useState } from "react";
import { Star, ShieldCheck, CreditCard, Globe, Sparkles, MessageSquarePlus } from "lucide-react";
import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter,
} from "@/components/ui/dialog";
import { toast } from "sonner";
import { useI18n } from "@/context/I18nContext";

const BADGES_FR = [
  { icon: ShieldCheck, label: "Conforme Factur-X", sub: "Facture électronique 2026" },
  { icon: CreditCard, label: "Paiements sécurisés", sub: "Propulsé par Stripe" },
  { icon: Globe, label: "Hébergé en Europe", sub: "Conforme RGPD" },
  { icon: Sparkles, label: "IA dernière génération", sub: "Assistant BTP · Vision · Voix" },
];
const BADGES_PT = [
  { icon: ShieldCheck, label: "Faturação conforme", sub: "e-Fatura / IVA 2026" },
  { icon: CreditCard, label: "Pagamentos seguros", sub: "Powered by Stripe" },
  { icon: Globe, label: "Alojado na Europa", sub: "Conforme RGPD" },
  { icon: Sparkles, label: "IA de última geração", sub: "Assistente BTP · Vision · Voz" },
];

const ReviewDialog = ({ open, onOpenChange }) => {
  const { lang } = useI18n();
  const pt = lang === "pt";
  const [form, setForm] = useState({ name: "", role: "", rating: 5, comment: "" });
  const [busy, setBusy] = useState(false);
  const set = (k) => (e) => setForm((f) => ({ ...f, [k]: e.target.value }));

  const submit = async (e) => {
    e.preventDefault();
    if (form.name.length < 2 || form.comment.length < 5) {
      toast.error(pt ? "Indique o seu nome e um comentário." : "Merci d'indiquer votre nom et un commentaire.");
      return;
    }
    setBusy(true);
    try {
      await api.post("/reviews/site", form);
      toast.success(pt ? "Obrigado! A sua avaliação será publicada após validação." : "Merci ! Votre avis sera publié après validation.");
      onOpenChange(false);
      setForm({ name: "", role: "", rating: 5, comment: "" });
    } catch {
      toast.error(pt ? "Envio impossível, tente novamente." : "Envoi impossible, réessayez.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent data-testid="review-dialog">
        <DialogHeader>
          <DialogTitle>{pt ? "Deixar uma avaliação" : "Laisser un avis"}</DialogTitle>
          <DialogDescription>{pt ? "Partilhe a sua experiência com o ConstruPilot." : "Partagez votre expérience avec ConstruPilot."}</DialogDescription>
        </DialogHeader>
        <form onSubmit={submit} className="grid gap-4">
          <div className="grid gap-1.5">
            <Label>{pt ? "A sua nota" : "Votre note"}</Label>
            <div className="flex gap-1" data-testid="review-stars">
              {[1, 2, 3, 4, 5].map((n) => (
                <button key={n} type="button" onClick={() => setForm((f) => ({ ...f, rating: n }))}
                        data-testid={`review-star-${n}`} className="p-0.5">
                  <Star className={`h-6 w-6 ${n <= form.rating ? "fill-primary text-primary" : "text-muted-foreground/40"}`} />
                </button>
              ))}
            </div>
          </div>
          <div className="grid gap-1.5">
            <Label htmlFor="rv-name">{pt ? "Nome *" : "Nom *"}</Label>
            <Input id="rv-name" value={form.name} onChange={set("name")} placeholder={pt ? "O seu nome" : "Votre nom"} data-testid="review-name" />
          </div>
          <div className="grid gap-1.5">
            <Label htmlFor="rv-role">{pt ? "Profissão / cidade" : "Métier / ville"}</Label>
            <Input id="rv-role" value={form.role} onChange={set("role")} placeholder={pt ? "Ex.: Empreiteiro, Lisboa" : "Ex : Artisan peintre, Lyon"} data-testid="review-role" />
          </div>
          <div className="grid gap-1.5">
            <Label htmlFor="rv-comment">{pt ? "A sua avaliação *" : "Votre avis *"}</Label>
            <Textarea id="rv-comment" value={form.comment} onChange={set("comment")} rows={4}
                      placeholder={pt ? "O que o ConstruPilot lhe trouxe…" : "Ce que ConstruPilot vous a apporté…"} data-testid="review-comment" />
          </div>
          <DialogFooter>
            <Button type="submit" disabled={busy} className="rounded-full" data-testid="review-submit">
              {busy ? (pt ? "A enviar…" : "Envoi…") : (pt ? "Publicar a minha avaliação" : "Publier mon avis")}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
};

export function TrustSection() {
  const { lang } = useI18n();
  const pt = lang === "pt";
  const BADGES = pt ? BADGES_PT : BADGES_FR;
  const [reviews, setReviews] = useState([]);
  const [open, setOpen] = useState(false);

  const load = () => api.get("/reviews/site").then(({ data }) => setReviews(data.reviews || [])).catch(() => {});
  useEffect(() => { load(); }, []);

  return (
    <section className="border-y border-border bg-secondary/30" id="trust">
      <ReviewDialog open={open} onOpenChange={(v) => { setOpen(v); if (!v) load(); }} />
      <div className="mx-auto max-w-[1500px] px-5 lg:px-8 py-12 lg:py-16 grid gap-10">
        {/* Badges de confiance neutres */}
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4" data-testid="trust-badges">
          {BADGES.map((b) => (
            <div key={b.label} className="surface p-4 flex items-center gap-3"
                 data-testid={`trust-badge-${b.label.toLowerCase().replace(/[^a-z]+/g, "-")}`}>
              <span className="h-10 w-10 shrink-0 grid place-items-center rounded-sm bg-primary/15 text-primary">
                <b.icon className="h-5 w-5" />
              </span>
              <div className="min-w-0">
                <p className="text-sm font-bold leading-tight">{b.label}</p>
                <p className="text-[11px] text-muted-foreground">{b.sub}</p>
              </div>
            </div>
          ))}
        </div>

        {/* Avis clients */}
        <div className="grid gap-4">
          <div className="flex items-center justify-between">
            <p className="overline">{pt ? "Usam o ConstruPilot" : "Ils utilisent ConstruPilot"}</p>
            <Button size="sm" variant="outline" className="rounded-full gap-2"
                    onClick={() => setOpen(true)} data-testid="leave-review-btn">
              <MessageSquarePlus className="h-4 w-4" /> {pt ? "Deixar uma avaliação" : "Laisser un avis"}
            </Button>
          </div>
          <div className="grid md:grid-cols-3 gap-4" data-testid="testimonials">
            {reviews.length === 0 ? (
              <div className="md:col-span-3 surface p-8 grid place-items-center text-center gap-2" data-testid="testimonials-empty">
                <div className="flex gap-0.5 text-primary/40">
                  {Array.from({ length: 5 }).map((_, i) => <Star key={i} className="h-4 w-4 fill-current" />)}
                </div>
                <p className="text-sm text-muted-foreground max-w-md">
                  {pt ? "Seja o primeiro a partilhar a sua experiência — a sua avaliação aparecerá aqui." : "Soyez le premier à partager votre expérience — votre avis apparaîtra ici."}
                </p>
              </div>
            ) : reviews.map((r) => (
              <blockquote key={r.review_id} data-testid={`testimonial-${r.review_id}`} className="surface p-5 grid gap-3">
                <div className="flex gap-0.5 text-primary" aria-label={`Note : ${r.rating} sur 5`}>
                  {Array.from({ length: r.rating }).map((_, i) => <Star key={i} className="h-3.5 w-3.5 fill-current" />)}
                </div>
                <p className="text-sm leading-relaxed">« {r.comment} »</p>
                <footer className="text-[11px] uppercase tracking-widest">
                  <span className="font-bold">{r.name}</span>
                  {r.role ? <span className="text-muted-foreground"> · {r.role}</span> : null}
                </footer>
              </blockquote>
            ))}
          </div>
        </div>
      </div>
    </section>
  );
}
