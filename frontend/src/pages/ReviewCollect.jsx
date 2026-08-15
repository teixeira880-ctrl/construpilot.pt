import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { Star, CheckCircle2, Loader2 } from "lucide-react";
import { toast } from "sonner";
import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";

export default function ReviewCollect() {
  const { token } = useParams();
  const [meta, setMeta] = useState(null);
  const [error, setError] = useState(null);
  const [rating, setRating] = useState(0);
  const [hover, setHover] = useState(0);
  const [comment, setComment] = useState("");
  const [name, setName] = useState("");
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState(false);

  useEffect(() => {
    api
      .get(`/reviews/collect/${token}`)
      .then(({ data }) => {
        setMeta(data);
        setName(data.client_name || "");
        if (data.submitted) setDone(true);
      })
      .catch(() => setError("Ce lien d'avis est invalide ou a expiré."));
  }, [token]);

  const submit = async () => {
    if (!rating) return toast.error("Choisissez une note de 1 à 5 étoiles");
    setBusy(true);
    try {
      await api.post(`/reviews/collect/${token}`, {
        rating,
        comment,
        author_name: name,
      });
      setDone(true);
      toast.success("Merci pour votre avis !");
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Envoi impossible");
    } finally {
      setBusy(false);
    }
  };

  const company = meta?.company_name || "ConstruPilot";

  return (
    <div className="min-h-screen bg-background text-foreground grid place-items-center px-4 py-10">
      <div className="w-full max-w-md surface p-8" data-testid="review-collect-card">
        <div className="text-center mb-6">
          <div className="inline-grid h-12 w-12 place-items-center rounded-md bg-primary text-primary-foreground font-display text-xl font-extrabold">
            {company.slice(0, 1).toUpperCase()}
          </div>
          <h1 className="mt-4 font-display text-2xl font-bold tracking-tight">
            Votre avis sur {company}
          </h1>
        </div>

        {error && (
          <p className="text-center text-sm text-destructive" data-testid="review-error">
            {error}
          </p>
        )}

        {!error && !meta && (
          <p className="text-center text-sm text-muted-foreground animate-pulse">
            Chargement…
          </p>
        )}

        {!error && done && (
          <div className="text-center space-y-3 py-6" data-testid="review-thanks">
            <CheckCircle2 className="h-12 w-12 mx-auto text-primary" />
            <p className="font-display text-lg font-bold">Merci pour votre retour !</p>
            <p className="text-sm text-muted-foreground">
              Votre avis a bien été enregistré. Il aide {company} à progresser.
            </p>
          </div>
        )}

        {!error && meta && !done && (
          <div className="space-y-5" data-testid="review-form">
            <div>
              <p className="text-sm text-muted-foreground text-center mb-2">
                Comment s'est passé votre chantier ?
              </p>
              <div className="flex justify-center gap-1" data-testid="review-stars">
                {[1, 2, 3, 4, 5].map((n) => (
                  <button
                    key={n}
                    type="button"
                    data-testid={`review-star-${n}`}
                    onMouseEnter={() => setHover(n)}
                    onMouseLeave={() => setHover(0)}
                    onClick={() => setRating(n)}
                    className="p-1 transition-transform hover:scale-110"
                    aria-label={`${n} étoile${n > 1 ? "s" : ""}`}
                  >
                    <Star
                      className="h-9 w-9"
                      style={{
                        fill: (hover || rating) >= n ? "hsl(var(--primary))" : "transparent",
                        color: (hover || rating) >= n ? "hsl(var(--primary))" : "#64748b",
                      }}
                    />
                  </button>
                ))}
              </div>
            </div>

            <div>
              <label className="text-xs text-muted-foreground">Votre nom</label>
              <input
                value={name}
                onChange={(e) => setName(e.target.value)}
                data-testid="review-name-input"
                className="mt-1 w-full rounded-sm border border-border bg-background px-3 py-2 text-sm outline-none focus:border-primary"
                placeholder="Ex : Marie D."
              />
            </div>

            <div>
              <label className="text-xs text-muted-foreground">
                Votre commentaire (optionnel)
              </label>
              <textarea
                value={comment}
                onChange={(e) => setComment(e.target.value)}
                data-testid="review-comment-input"
                rows={4}
                className="mt-1 w-full rounded-sm border border-border bg-background px-3 py-2 text-sm outline-none focus:border-primary resize-none"
                placeholder="Qualité du travail, respect des délais, propreté du chantier…"
              />
            </div>

            <Button
              onClick={submit}
              disabled={busy}
              data-testid="review-submit-btn"
              className="w-full rounded-sm gap-2"
            >
              {busy && <Loader2 className="h-4 w-4 animate-spin" />}
              Envoyer mon avis
            </Button>
            <p className="text-[11px] text-muted-foreground text-center">
              Votre avis pourra être affiché sur les futurs devis de {company}.
            </p>
          </div>
        )}
      </div>
    </div>
  );
}
