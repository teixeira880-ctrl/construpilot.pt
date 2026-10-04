import { useEffect, useState } from "react";
import { Star, MessageSquare, Clock, Eye, EyeOff } from "lucide-react";
import { toast } from "sonner";
import { api } from "@/lib/api";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { SectionTitle } from "@/components/Bits";
import { useAuth } from "@/context/AuthContext";

const Stars = ({ n }) => (
  <span className="inline-flex" data-testid="review-rating-stars">
    {[1, 2, 3, 4, 5].map((i) => (
      <Star
        key={i}
        className="h-4 w-4"
        style={{
          fill: i <= n ? "hsl(var(--primary))" : "transparent",
          color: i <= n ? "hsl(var(--primary))" : "#64748b",
        }}
      />
    ))}
  </span>
);

export default function MyReviews() {
  const { user } = useAuth();
  const [data, setData] = useState(null);

  const load = () =>
    api
      .get("/reviews/me")
      .then(({ data }) => setData(data))
      .catch(() => toast.error("Impossível carregar as suas avaliações"));

  useEffect(() => {
    if (user) load();
  }, [user]);

  const togglePublish = async (r) => {
    try {
      await api.patch(`/reviews/${r.review_id}/publish`, { published: !r.published });
      toast.success(!r.published ? "Avaliação apresentada nos seus orçamentos" : "Avis masqué");
      load();
    } catch {
      toast.error("Ação impossível");
    }
  };

  if (!user) return <div className="surface p-10 text-center">Connectez-vous.</div>;
  if (!data) return <div className="surface p-10 text-center animate-pulse">Chargement…</div>;

  const submitted = (data.reviews || []).filter((r) => r.submitted);
  const pending = (data.reviews || []).filter((r) => !r.submitted);

  return (
    <div className="grid gap-8">
      <SectionTitle over="Avis Clients" title="Ce que disent vos clients">
        Les avis vérifiés — collectés automatiquement à la fin de chaque chantier — sont
        affichés sur vos futurs devis PDF pour rassurer vos prospects.
      </SectionTitle>

      <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
        <div className="surface p-5" data-testid="reviews-kpi-average">
          <p className="overline">Note moyenne</p>
          <div className="flex items-center gap-2 mt-1">
            <p className="num font-display text-3xl font-extrabold text-primary">
              {data.average || 0}
            </p>
            <span className="text-sm text-muted-foreground">/5</span>
          </div>
          <div className="mt-1"><Stars n={Math.round(data.average || 0)} /></div>
        </div>
        <div className="surface p-5" data-testid="reviews-kpi-count">
          <p className="overline">Avis reçus</p>
          <p className="num font-display text-3xl font-extrabold mt-1">{data.count || 0}</p>
        </div>
        <div className="surface p-5" data-testid="reviews-kpi-pending">
          <p className="overline">En attente</p>
          <p className="num font-display text-3xl font-extrabold mt-1">{data.pending || 0}</p>
          <p className="text-[10px] text-muted-foreground">demandes envoyées non répondues</p>
        </div>
      </div>

      {submitted.length === 0 && pending.length === 0 && (
        <div className="surface p-10 text-center space-y-3" data-testid="reviews-empty">
          <MessageSquare className="h-10 w-10 mx-auto text-muted-foreground" />
          <p className="font-display font-bold">Aucun avis pour l'instant</p>
          <p className="text-sm text-muted-foreground">
            Dans <b>Suivi Devis</b>, marquez un devis signé comme
            <b> «Obra concluída»</b> para enviar automaticamente um pedido de avaliação
            à votre client.
          </p>
        </div>
      )}

      {submitted.length > 0 && (
        <div className="grid gap-3">
          <p className="font-display font-bold text-sm">Avis reçus</p>
          {submitted.map((r) => (
            <div key={r.review_id} className="surface p-5 flex flex-col gap-2"
                 data-testid={`review-item-${r.review_id}`}>
              <div className="flex items-center justify-between gap-3 flex-wrap">
                <div className="flex items-center gap-3">
                  <Stars n={r.rating || 0} />
                  <span className="font-bold text-sm">{r.author_name || "Client"}</span>
                  {r.published ? (
                    <Badge variant="outline" className="rounded-sm border-primary/50 text-primary">
                      Affiché
                    </Badge>
                  ) : (
                    <Badge variant="outline" className="rounded-sm text-muted-foreground">
                      Masqué
                    </Badge>
                  )}
                </div>
                <Button size="sm" variant="outline" className="rounded-sm gap-2"
                        onClick={() => togglePublish(r)}
                        data-testid={`review-toggle-${r.review_id}`}>
                  {r.published ? <EyeOff className="h-3.5 w-3.5" /> : <Eye className="h-3.5 w-3.5" />}
                  {r.published ? "Masquer" : "Mostrar"}
                </Button>
              </div>
              {r.comment && (
                <p className="text-sm text-muted-foreground italic">« {r.comment} »</p>
              )}
              <p className="text-[10px] num text-muted-foreground">
                {(r.submitted_at || "").slice(0, 10)}
              </p>
            </div>
          ))}
        </div>
      )}

      {pending.length > 0 && (
        <div className="grid gap-3">
          <p className="font-display font-bold text-sm text-muted-foreground">
            Demandes en attente de réponse
          </p>
          {pending.map((r) => (
            <div key={r.review_id}
                 className="border border-dashed border-border rounded-sm p-4 flex items-center gap-3"
                 data-testid={`review-pending-${r.review_id}`}>
              <Clock className="h-4 w-4 text-muted-foreground" />
              <span className="text-sm">{r.client_name || r.client_email}</span>
              <span className="text-[10px] text-muted-foreground num ml-auto">
                demandé le {(r.requested_at || "").slice(0, 10)}
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
