import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { HardHat, ArrowLeft, User } from "lucide-react";
import { api } from "@/lib/api";

/** Lit `?chantier=<id>` (ou l'identifiant fourni) et charge le dossier ; renvoie { chantierId, chantier }. */
export function useChantierContext(explicitId = "") {
  const [sp] = useSearchParams();
  const chantierId = explicitId || sp.get("chantier") || "";
  const [chantier, setChantier] = useState(null);
  useEffect(() => {
    if (!chantierId) { setChantier(null); return; }
    api.get(`/chantiers/${chantierId}`).then(({ data }) => setChantier(data)).catch(() => setChantier(null));
  }, [chantierId]);
  return { chantierId, chantier };
}

/** Bandeau « Vous travaillez dans le dossier … » affiché en tête des outils quand un chantier est en contexte. */
export function ChantierContextBar({ chantier, chantierId }) {
  if (!chantierId) return null;
  return (
    <div className="flex flex-wrap items-center gap-3 rounded-lg border border-primary/30 bg-primary/5 px-4 py-2.5 text-sm" data-testid="chantier-context-bar">
      <HardHat className="h-4 w-4 text-primary shrink-0" />
      <span className="min-w-0">
        <span className="text-muted-foreground">Dossier chantier : </span>
        <strong data-testid="chantier-context-name">{chantier?.name || "chargement…"}</strong>
        {chantier?.client_name && <span className="text-muted-foreground"> · <User className="inline h-3.5 w-3.5 -mt-0.5" /> {chantier.client_name}</span>}
      </span>
      <span className="text-xs text-muted-foreground hidden sm:inline">Le résultat sera rattaché automatiquement au dossier.</span>
      <Link to={`/chantiers/${chantierId}`} className="ms-auto inline-flex items-center gap-1 text-primary text-xs font-semibold hover:underline" data-testid="chantier-context-back">
        <ArrowLeft className="h-3 w-3" /> Revenir au dossier
      </Link>
    </div>
  );
}
