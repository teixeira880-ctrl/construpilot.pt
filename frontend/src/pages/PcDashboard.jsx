import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";
import { FileSearch, HardHat, CheckCircle2, CreditCard, Eye, BellRing, Send, FileStack, Users, Mail, BadgeCheck } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { api, eur, num } from "@/lib/api";

const STATUS_STYLE = {
  "soldée": "bg-emerald-600/20 text-emerald-700 border-emerald-600/50",
  "acompte versé": "bg-violet-500/15 text-violet-600 border-violet-500/40",
  "acceptée": "bg-emerald-500/15 text-emerald-600 border-emerald-500/40",
  "ouverte": "bg-sky-500/15 text-sky-600 border-sky-500/40",
  "relancée": "bg-amber-500/15 text-amber-600 border-amber-500/40",
  "envoyée": "bg-primary/10 text-primary border-primary/40",
  "générée": "bg-muted text-muted-foreground border-border",
};
const STATUS_LABEL = {
  "soldée": "liquidada", "acompte versé": "adiantamento pago", "acceptée": "aceite", "ouverte": "aberta",
  "relancée": "relançada", "envoyée": "enviada", "générée": "gerada",
};
const STATUS_ICON = {
  "soldée": BadgeCheck, "acompte versé": CreditCard, "acceptée": CheckCircle2, "ouverte": Eye,
  "relancée": BellRing, "envoyée": Send, "générée": FileStack,
};

export default function PcDashboard() {
  const nav = useNavigate();
  const [studies, setStudies] = useState(null);
  const [reportBusy, setReportBusy] = useState(false);

  useEffect(() => {
    api.get("/pc/dashboard")
      .then(({ data }) => setStudies(data.studies || []))
      .catch(() => setStudies([]));
  }, []);

  const sendReportNow = async () => {
    setReportBusy(true);
    try {
      const { data } = await api.post("/pc/weekly-report/send-me");
      toast.success(`Relatório enviado a ${data.sent_to} (${data.studies} estudos)`);
    } catch (e) { toast.error(e?.response?.data?.detail || "Envio impossível"); }
    finally { setReportBusy(false); }
  };

  const list = studies || [];
  const totalTtc = list.reduce((s, x) => s + (x.ttc || 0), 0);
  const accepted = list.filter((x) => ["acceptée", "acompte versé", "soldée"].includes(x.status)).length;
  const deposits = list.reduce((s, x) => s + (x.deposit_amount || 0), 0);

  return (
    <div className="max-w-5xl mx-auto px-5 py-8 space-y-6" data-testid="pc-dashboard">
      <header className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <p className="overline flex items-center gap-2 text-primary">
            <HardHat className="h-4 w-4" /> Estudos Licença de Construção
          </p>
          <h1 className="font-display text-3xl font-extrabold" title="Licença de construção">
            Painel dos estudos de licenciamento <span className="text-muted-foreground font-normal text-lg">— Licença de construção</span>
          </h1>
          <p className="text-sm text-muted-foreground">
            Todos os estudos de estrutura da sua equipa e o seu estado cliente, no mesmo lugar.
          </p>
        </div>
        <Button variant="outline" size="sm" onClick={sendReportNow} disabled={reportBusy}
                className="rounded-sm gap-2" data-testid="pc-dash-weekly-report-btn">
          <Mail className="h-3.5 w-3.5" />
          {reportBusy ? "A enviar…" : "Enviar-me o relatório semanal"}
        </Button>
      </header>

      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        {[["Estudos", list.length], ["Montante acumulado c/ IVA", eur(totalTtc)],
          ["Aceites", `${accepted} / ${list.length}`],
          ["Adiantamentos recebidos", eur(deposits)]].map(([k, v]) => (
          <div key={k} className="surface p-4">
            <p className="text-[10px] text-muted-foreground">{k}</p>
            <p className="font-display text-xl font-extrabold num">{v}</p>
          </div>
        ))}
      </div>

      {studies === null ? (
        <p className="text-muted-foreground animate-pulse">A carregar…</p>
      ) : list.length === 0 ? (
        <div className="surface p-8 text-center space-y-2" data-testid="pc-dashboard-empty">
          <FileSearch className="h-8 w-8 mx-auto text-muted-foreground" />
          <p className="text-sm text-muted-foreground">
            Nenhum estudo de licenciamento por enquanto — abra uma planta e clique em «Estudo do projeto de licenciamento».
          </p>
          <Button onClick={() => nav("/plan")} className="rounded-sm" data-testid="pc-dashboard-goto-plan">
            Abrir Medir
          </Button>
        </div>
      ) : (
        <table className="w-full text-sm border border-border">
          <thead>
            <tr className="bg-muted text-left text-xs">
              <th className="p-2">Obra</th>
              <th className="p-2">Gerada a</th>
              <th className="p-2 text-right">Betão</th>
              <th className="p-2 text-right">Total c/ IVA</th>
              <th className="p-2">Estado</th>
              <th className="p-2 text-right">Envios / BC</th>
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
                    {s.owner_name && (
                      <p className="text-[10px] text-sky-600 flex items-center gap-1 truncate"
                         data-testid={`pc-dash-row-${i}-owner`}>
                        <Users className="h-3 w-3" /> Estudo de {s.owner_name}
                      </p>
                    )}
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
                      <Icon className="h-3 w-3" /> {STATUS_LABEL[s.status] || s.status}
                    </Badge>
                  </td>
                  <td className="p-2 text-right num text-xs">{s.sends} / {s.orders}</td>
                  <td className="p-2 text-right">
                    <Button variant="outline" size="sm" className="rounded-sm h-7 text-xs"
                            onClick={() => nav(`/plan?open=${s.plan_id}`)}
                            data-testid={`pc-dash-row-${i}-open`}>
                      Abrir
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
