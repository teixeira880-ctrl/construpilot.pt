import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { Ruler } from "lucide-react";
import { api } from "@/lib/api";

const VERDICT = {
  ok: { label: "Conforme", cls: "text-emerald-700 bg-emerald-500/10 border-emerald-500/30" },
  warn: { label: "À vérifier", cls: "text-orange-700 bg-orange-500/10 border-orange-500/30" },
  ko: { label: "Incohérences", cls: "text-red-700 bg-red-500/10 border-red-500/30" },
};

export const CotesTile = () => {
  const [data, setData] = useState(null);
  useEffect(() => {
    api.get("/cotes/latest").then(({ data }) => setData(data)).catch(() => setData({ latest: null }));
  }, []);
  const last = data?.latest;
  const v = last ? VERDICT[last.verdict] || VERDICT.ok : null;
  const to = last ? `/controle-cotes?plan=${last.plan_id}` : "/controle-cotes";
  return (
    <Link to={to} data-testid="cotes-tile" className="block surface p-6 border-2 border-sky-500/30 hover:border-sky-500 transition-colors">
      <div className="flex items-center justify-between gap-4">
        <div className="min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <Ruler className="h-4 w-4 text-sky-600" />
            <span className="font-display font-bold text-lg">Analyser cotes des plans</span>
            <span className="text-[10px] font-bold uppercase bg-sky-500/10 text-sky-700 px-2 py-0.5 rounded-full">Nouveau</span>
          </div>
          {last ? (
            <p className="text-sm text-muted-foreground mt-1" data-testid="cotes-tile-last">
              Dernier contrôle : <b className="text-foreground">{last.filename || last.plan_id}</b>
              {last.pages_checked > 1 ? ` (${last.pages_checked} pages)` : ""} ·{" "}
              {last.summary?.total} cotes · <b className="text-red-700">{last.summary?.ko} incohérence(s)</b> ·{" "}
              {new Date(last.checked_at).toLocaleDateString("fr-FR")}
            </p>
          ) : (
            <p className="text-sm text-muted-foreground mt-1">
              Relecture de toutes les cotes d'un plan, mesure à l'échelle, incohérences et chaînes de cotes signalées — rapport PDF et plan annoté.
            </p>
          )}
        </div>
        <div className="shrink-0 flex flex-col items-end gap-1">
          {v && <span className={`text-xs font-bold px-2 py-0.5 rounded-full border ${v.cls}`} data-testid="cotes-tile-verdict">{v.label}</span>}
          <span className="text-sky-700 font-bold">{last ? "Voir →" : "Ouvrir →"}</span>
        </div>
      </div>
    </Link>
  );
};
