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

const BADGES = [
  { icon: ShieldCheck, label: "Conforme Factur-X", sub: "Facture électronique 2026" },
  { icon: CreditCard, label: "Paiements sécurisés", sub: "Propulsé par Stripe" },
  { icon: Globe, label: "Hébergé en Europe", sub: "Conforme RGPD" },
  { icon: Sparkles, label: "IA dernière génération", sub: "Gemini · Claude · Whisper" },
];

const ReviewDialog = ({ open, onOpenChange }) => {
  const [form, setForm] = useState({ name: "", role: "", rating: 5, comment: "" });
  const [busy, setBusy] = useState(false);
  const set = (k) => (e) => setForm((f) => ({ ...f, [k]: e.target.value }));

  const submit = async (e) => {
    e.preventDefault();
    if (form.name.length < 2 || form.comment.length < 5) {
      toast.error("Merci d'indiquer votre nom et un commentaire.");
      return;
    }
    setBusy(true);
    try {
      await api.post("/reviews/site", form);
      toast.success("Merci ! Votre avis sera publié après validation.");
      onOpenChange(false);
      setForm({ name: "", role: "", rating: 5, comment: "" });
    } catch {
      toast.error("Envoi impossible, réessayez.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent data-testid="review-dialog">
        <DialogHeader>
          <DialogTitle>Laisser un avis</DialogTitle>
          <DialogDescription>Partagez votre expérience avec ConstruPilot.</DialogDescription>
        </DialogHeader>
        <form onSubmit={submit} className="grid gap-4">
          <div className="grid gap-1.5">
            <Label>Votre note</Label>
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
            <Label htmlFor="rv-name">Nom *</Label>
            <Input id="rv-name" value={form.name} onChange={set("name")} placeholder="Votre nom" data-testid="review-name" />
          </div>
          <div className="grid gap-1.5">
            <Label htmlFor="rv-role">Métier / ville</Label>
            <Input id="rv-role" value={form.role} onChange={set("role")} placeholder="Ex : Artisan peintre, Lyon" data-testid="review-role" />
          </div>
          <div className="grid gap-1.5">
            <Label htmlFor="rv-comment">Votre avis *</Label>
            <Textarea id="rv-comment" value={form.comment} onChange={set("comment")} rows={4}
                      placeholder="Ce que ConstruPilot vous a apporté…" data-testid="review-comment" />
          </div>
          <DialogFooter>
            <Button type="submit" disabled={busy} className="rounded-full" data-testid="review-submit">
              {busy ? "Envoi…" : "Publier mon avis"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
};

export function TrustSection() {
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
            <p className="overline">Ils utilisent ConstruPilot</p>
            <Button size="sm" variant="outline" className="rounded-full gap-2"
                    onClick={() => setOpen(true)} data-testid="leave-review-btn">
              <MessageSquarePlus className="h-4 w-4" /> Laisser un avis
            </Button>
          </div>
          <div className="grid md:grid-cols-3 gap-4" data-testid="testimonials">
            {reviews.length === 0 ? (
              <div className="md:col-span-3 surface p-8 grid place-items-center text-center gap-2" data-testid="testimonials-empty">
                <div className="flex gap-0.5 text-primary/40">
                  {Array.from({ length: 5 }).map((_, i) => <Star key={i} className="h-4 w-4 fill-current" />)}
                </div>
                <p className="text-sm text-muted-foreground max-w-md">
                  Soyez le premier à partager votre expérience — votre avis apparaîtra ici.
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
