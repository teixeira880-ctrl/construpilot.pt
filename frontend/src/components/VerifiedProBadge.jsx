import { ShieldCheck } from "lucide-react";

/**
 * Badge de confiance affiché pour les comptes pro dont le KYC est validé.
 * Rend null si le statut n'est pas "verified".
 */
export function VerifiedProBadge({ status, size = "sm", className = "" }) {
  if (status !== "verified") return null;
  const s = size === "lg" ? "text-sm px-3 py-1" : "text-[11px] px-2 py-0.5";
  return (
    <span
      data-testid="verified-pro-badge"
      title="Justificatifs professionnels (K-bis, assurance décennale) vérifiés par ConstruPilot"
      className={`inline-flex items-center gap-1 rounded-full font-bold bg-emerald-500/15 text-emerald-600 border border-emerald-500/30 ${s} ${className}`}
    >
      <ShieldCheck className={size === "lg" ? "h-4 w-4" : "h-3 w-3"} />
      Pro vérifié
    </span>
  );
}
