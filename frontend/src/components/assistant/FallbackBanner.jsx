import { useEffect, useState } from "react";
import { AlertTriangle } from "lucide-react";
import { api } from "@/lib/api";

/* Shown while the account's OpenAI key is in fallback (credits / quota): the assistant runs on the universal key. */
export const FallbackBanner = ({ refreshKey }) => {
  const [rt, setRt] = useState(null);
  useEffect(() => { api.get("/assistant/runtime").then(({ data }) => setRt(data)).catch(() => setRt(null)); }, [refreshKey]);
  if (!rt?.openai_degraded) return null;
  const until = rt.openai_degraded.until ? new Date(rt.openai_degraded.until).toLocaleTimeString("fr-FR", { hour: "2-digit", minute: "2-digit" }) : null;
  return <div className="mx-3 mb-2 flex items-start gap-2 rounded-md border border-amber-500/40 bg-amber-500/10 px-3 py-2 text-xs" role="status" data-testid="fallback-banner">
    <AlertTriangle size={14} className="mt-0.5 shrink-0 text-amber-600" />
    <div>
      <b>Chave OpenAI indisponível</b> — o assistente responde com a chave universal (Claude){until ? `; nova tentativa OpenAI após${until}` : ""}.
      <div className="text-muted-foreground">{rt.openai_degraded.reason?.replace(/https?:\S+/g, "").slice(0, 140)} Recarregue os seus créditos em platform.openai.com → Billing.</div>
    </div>
  </div>;
};
