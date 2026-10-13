import { useEffect, useState } from "react";
import { useParams, Link } from "react-router-dom";
import { api } from "@/lib/api";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { BadgeCheck, MapPin, Star, ShieldCheck, Loader2, ArrowRight, Award } from "lucide-react";

const CERT_LABELS = {
  qualibat: "Qualibat", rge: "RGE", qualipac: "QualiPAC",
  qualifelec: "Qualifelec", qualibois: "Qualibois",
};

function Stars({ value }) {
  return (
    <span className="inline-flex items-center gap-0.5" data-testid="pv-stars">
      {[1, 2, 3, 4, 5].map((i) => (
        <Star key={i} className={`h-4 w-4 ${i <= Math.round(value) ? "fill-amber-400 text-amber-400" : "text-muted-foreground/30"}`} />
      ))}
    </span>
  );
}

export default function ProVerified() {
  const { userId } = useParams();
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState(false);

  useEffect(() => {
    (async () => {
      try {
        const { data } = await api.get(`/reviews/pro-verified/${userId}`);
        setData(data);
      } catch {
        setErr(true);
      } finally { setLoading(false); }
    })();
  }, [userId]);

  if (loading) {
    return (
      <div className="min-h-[60vh] grid place-items-center" data-testid="pv-loading">
        <Loader2 className="h-8 w-8 animate-spin text-primary" />
      </div>
    );
  }
  if (err || !data) {
    return (
      <div className="min-h-[60vh] grid place-items-center text-center px-4" data-testid="pv-error">
        <div>
          <p className="text-lg font-semibold">Perfil não encontrado</p>
          <p className="text-sm text-muted-foreground mt-1">Este link de verificação já não é válido.</p>
          <Link to="/"><Button variant="outline" className="mt-4">Voltar ao início</Button></Link>
        </div>
      </div>
    );
  }

  const reviews = data.reviews || { count: 0, average: 0, items: [] };
  return (
    <div className="max-w-2xl mx-auto px-4 py-10 space-y-6" data-testid="pro-verified-page">
      {/* En-tête confiance */}
      <Card className="p-8 text-center relative overflow-hidden">
        <div className="absolute inset-x-0 top-0 h-1.5 bg-primary" />
        <div className="mx-auto h-16 w-16 rounded-full bg-primary/10 grid place-items-center mb-4">
          {data.verified
            ? <BadgeCheck className="h-9 w-9 text-primary" data-testid="pv-verified-icon" />
            : <ShieldCheck className="h-9 w-9 text-muted-foreground" />}
        </div>
        <h1 className="text-2xl font-bold" data-testid="pv-company">{data.company_name}</h1>
        {data.verified ? (
          <div className="mt-3 inline-flex items-center gap-2 bg-primary/10 text-primary font-semibold text-sm px-4 py-1.5 rounded-full"
               data-testid="pv-verified-chip">
            <BadgeCheck className="h-4 w-4" /> Pro verificado por ConstruPilot
          </div>
        ) : (
          <p className="mt-3 text-sm text-muted-foreground">Verificação em curso</p>
        )}
        {data.city && (
          <p className="mt-3 text-sm text-muted-foreground flex items-center justify-center gap-1">
            <MapPin className="h-4 w-4" /> {data.city}
          </p>
        )}
        {data.verified && (
          <p className="text-xs text-muted-foreground mt-4 max-w-md mx-auto">
            A identidade (NIPC), a certidão permanente e o alvará/seguro RC desta empresa foram verificados por ConstruPilot.
          </p>
        )}
      </Card>

      {/* Identité vérifiée */}
      {(data.siret || (data.certifications && data.certifications.length > 0)) && (
        <Card className="p-6 space-y-3" data-testid="pv-identity">
          <h2 className="text-sm font-semibold text-muted-foreground uppercase tracking-wide">Elementos verificados</h2>
          {data.siret && (
            <div className="flex items-center justify-between text-sm">
              <span className="flex items-center gap-2"><ShieldCheck className="h-4 w-4 text-primary" /> NIF</span>
              <span className="font-mono">{data.siret}</span>
            </div>
          )}
          {data.certifications && data.certifications.map((c, i) => (
            <div key={i} className="flex items-center justify-between text-sm">
              <span className="flex items-center gap-2"><Award className="h-4 w-4 text-primary" /> Certificação</span>
              <span className="font-semibold">
                {CERT_LABELS[c.code] || (c.code || "").toUpperCase()}
                {c.number ? ` (n° ${c.number})` : ""}
              </span>
            </div>
          ))}
        </Card>
      )}

      {/* Avis clients */}
      <Card className="p-6 space-y-4" data-testid="pv-reviews">
        <div className="flex items-center justify-between">
          <h2 className="text-sm font-semibold text-muted-foreground uppercase tracking-wide">Opiniões de clientes</h2>
          {reviews.count > 0 && (
            <span className="flex items-center gap-2 text-sm font-semibold" data-testid="pv-rating">
              <Stars value={reviews.average} /> {reviews.average}/5 · {reviews.count} avis
            </span>
          )}
        </div>
        {reviews.count === 0 ? (
          <p className="text-sm text-muted-foreground">Ainda sem avaliações publicadas.</p>
        ) : reviews.items.length === 0 ? (
          <p className="text-sm text-muted-foreground">{reviews.count} avaliação(ões) recolhida(s).</p>
        ) : (
          <div className="space-y-3">
            {reviews.items.map((r, i) => (
              <div key={i} className="border border-border rounded-md p-3" data-testid={`pv-review-${i}`}>
                <div className="flex items-center gap-2 mb-1">
                  <Stars value={r.rating} />
                  <span className="text-xs font-semibold">{r.author_name || "Cliente"}</span>
                </div>
                <p className="text-sm text-muted-foreground">{r.comment}</p>
              </div>
            ))}
          </div>
        )}
      </Card>

      {/* CTA */}
      <Card className="p-6 text-center bg-primary/5">
        <p className="text-sm font-semibold">É artesão ou empresa de construção?</p>
        <p className="text-xs text-muted-foreground mt-1 mb-3">
          Faça verificar a sua empresa e tranquilize os seus clientes logo no orçamento.
        </p>
        <Link to="/inscription">
          <Button className="gap-2" data-testid="pv-cta">
            Tornar-se Pro verificado <ArrowRight className="h-4 w-4" />
          </Button>
        </Link>
      </Card>
    </div>
  );
}
