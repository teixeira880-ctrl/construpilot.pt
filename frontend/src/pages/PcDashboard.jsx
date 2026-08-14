import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { FileSearch, HardHat, CheckCircle2, Eye, BellRing, Send, FileStack } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { api, eur, num } from "@/lib/api";

const STATUS_STYLE = {
  "acceptée": "bg-emerald-500/15 text-emerald-600 border-emerald-500/40",
  "ouverte": "bg-sky-500/15 text-sky-600 border-sky-500/40",
  "relancée": "bg-amber-500/15 text-amber-600 border-amber-500/40",
  "envoyée": "bg-primary/10 text-primary border-primary/40",
  "générée": "bg-muted text-muted-foreground border-border",
};
const STATUS_ICON = {
  "acceptée": CheckCircle2, "ouverte": Eye, "relancée": BellRing,
  "envoyée": Send, "générée": FileStack,
};

export default function PcDashboard() {
  const nav = useNavigate();
  const [studies, setStudies] = useState(null);

  useEffect(() => {
    api.get("/pc/dashboard")
      .then(({ data }) => setStudies(data.studies || []))
      .catch(() => setStudies([]));
  }, []);

  const list = studies || [];
  const totalTtc = list.reduce((s, x) => s + (x.ttc || 0), 0);
  const accepted = list.filter((x) => x.status === "acceptée").length;

  return (
    <div className="max-w-5xl mx-auto px-5 py-8 space-y-6" data-testid="pc-dashboard">
      <header>
        <p className="overline flex items-center gap-2 text-primary">
          <HardHat className="h-4 w-4" /> Études Permis de Construire
        </p>
        <h1 className="font-display text-3xl font-extrabold">Tableau de bord PC</h1>
        <p className="text-sm text-muted-foreground">
          Toutes vos études gros œuvre et leur statut client, au même endroit.
        </p>
      </header>

      <div className="grid grid-cols-3 gap-3">
        {[["Études", list.length], ["Montant cumulé TTC", eur(totalTtc)],
          ["Acceptées", `${accepted} / ${list.length}`]].map(([k, v]) => (
          <div key={k} className="surface p-4">
            <p className="text-[10px] text-muted-foreground">{k}</p>
            <p className="font-display text-xl font-extrabold num">{v}</p>
          </div>
        ))}
      </div>

      {studies === null ? (
        <p className="text-muted-foreground animate-pulse">Chargement…</p>
      ) : list.length === 0 ? (
        <div className="surface p-8 text-center space-y-2" data-testid="pc-dashboard-empty">
          <FileSearch className="h-8 w-8 mx-auto text-muted-foreground" />
          <p className="text-sm text-muted-foreground">
            Aucune étude PC pour l'instant — ouvrez un plan et cliquez « Étude PC ».
          </p>
          <Button onClick={() => nav("/plan")} className="rounded-sm" data-testid="pc-dashboard-goto-plan">
            Ouvrir le Plan 2D
          </Button>
        </div>
      ) : (
        <table className="w-full text-sm border border-border">
          <thead>
            <tr className="bg-muted text-left text-xs">
              <th className="p-2">Chantier</th>
              <th className="p-2">Générée le</th>
              <th className="p-2 text-right">Béton</th>
              <th className="p-2 text-right">Total TTC</th>
              <th className="p-2">Statut</th>
              <th className="p-2 text-right">Envois / BC</th>
              <th className="p-2"></th>
            </tr>
          </thead>
          <tbody>
            {list.map((s, i) => {
              const Icon = STATUS_ICON[s.status] || FileStack;
              return (
                <tr key={s.plan_id} className="border-t border-border hover:bg-muted/30 transition-colors"
                    data-testid={`pc-dash-row-${i}`}>
                  <td className="p-2">
                    <p className="font-medium truncate max-w-[220px]">{s.filename || s.plan_id}</p>
                    {s.last_sent_to && (
                      <p className="text-[10px] text-muted-foreground truncate">→ {s.last_sent_to}</p>
                    )}
                  </td>
                  <td className="p-2 num text-xs">{String(s.generated_at || "").slice(0, 10)}</td>
                  <td className="p-2 text-right num text-xs">{num(s.beton_m3, 1)} m³</td>
                  <td className="p-2 text-right num font-semibold">{eur(s.ttc)}</td>
                  <td className="p-2">
                    <Badge className={`rounded-sm gap-1 text-[10px] border hover:bg-transparent ${STATUS_STYLE[s.status]}`}
                           data-testid={`pc-dash-row-${i}-status`}>
                      <Icon className="h-3 w-3" /> {s.status}
                    </Badge>
                  </td>
                  <td className="p-2 text-right num text-xs">{s.sends} / {s.orders}</td>
                  <td className="p-2 text-right">
                    <Button variant="outline" size="sm" className="rounded-sm h-7 text-xs"
                            onClick={() => nav(`/plan?open=${s.plan_id}`)}
                            data-testid={`pc-dash-row-${i}-open`}>
                      Ouvrir
                    </Button>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      )}
    </div>
  );
}
