import { useCallback, useEffect, useState } from "react";
import { RefreshCw, Users, Activity, Building2, CreditCard, Route, HelpCircle } from "lucide-react";
import { Button } from "@/components/ui/button";
import { api } from "@/lib/api";

/** Affiche « non mesurable » plutôt qu'un zéro inventé. */
const Value = ({ v, suffix = "" }) =>
  v === null || v === undefined ? (
    <span className="text-sm font-normal text-amber-500">não mensurável</span>
  ) : (
    <span className="num">{typeof v === "number" ? v.toLocaleString("fr-FR") : v}{suffix}</span>
  );

const Metric = ({ label, value, suffix, note, testId }) => (
  <div className="surface rounded-md p-4" data-testid={testId}>
    <p className="text-[11px] uppercase tracking-widest text-muted-foreground">{label}</p>
    <p className="font-display text-2xl font-extrabold mt-1">
      <Value v={value} suffix={suffix} />
    </p>
    {note && <p className="text-[11px] text-muted-foreground mt-1 leading-snug">{note}</p>}
  </div>
);

const Block = ({ icon: Icon, title, children, testId }) => (
  <section className="grid gap-3" data-testid={testId}>
    <p className="font-semibold flex items-center gap-2 text-sm">
      <Icon className="h-4 w-4 text-primary" /> {title}
    </p>
    <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-3">{children}</div>
  </section>
);

export default function JourneyPanel() {
  const [data, setData] = useState(null);
  const [events, setEvents] = useState([]);
  const [days, setDays] = useState(30);
  const [busy, setBusy] = useState(false);

  const load = useCallback(() => {
    setBusy(true);
    Promise.all([
      api.get(`/admin/journey/metrics?days=${days}`),
      api.get("/admin/journey/events?limit=25"),
    ]).then(([m, e]) => { setData(m.data); setEvents(e.data.events || []); })
      .finally(() => setBusy(false));
  }, [days]);

  useEffect(() => { load(); }, [load]);

  if (!data) {
    return <p className="text-sm text-muted-foreground" data-testid="journey-loading">A carregar os números reais…</p>;
  }

  const a = data.accounts, act = data.activity, j = data.journey;

  return (
    <div className="grid gap-8" data-testid="journey-panel">
      <div className="flex flex-wrap items-center gap-3">
        <div className="flex-1 min-w-0">
          <h2 className="font-display text-xl font-extrabold">Contas reais e percurso</h2>
          <p className="text-xs text-muted-foreground">
            Janela: {data.window_days} dias · Gerado em {new Date(data.generated_at).toLocaleString("fr-FR")} · Instrumentação iniciada: {data.instrumentation_started_at
              ? new Date(data.instrumentation_started_at).toLocaleString("fr-FR")
              : "nenhum evento registado por agora"}
          </p>
        </div>
        {[7, 30, 90].map((d) => (
          <Button key={d} size="sm" variant={days === d ? "default" : "outline"} className="rounded-sm"
                  onClick={() => setDays(d)} data-testid={`journey-window-${d}`}>{d} j</Button>
        ))}
        <Button size="sm" variant="outline" className="rounded-sm gap-1" onClick={load}
                disabled={busy} data-testid="journey-refresh">
          <RefreshCw className={`h-3.5 w-3.5 ${busy ? "animate-spin" : ""}`} /> Actualiser
        </Button>
      </div>

      <Block icon={Users} title="Comptes" testId="journey-accounts">
        <Metric label="Comptes existants" value={a.existing_excluding_tests}
                note="excluindo contas de teste e endereços internos" testId="journey-existing" />
        <Metric label="Dos quais profissionais" value={a.pros} testId="journey-pros" />
        <Metric label="Dos quais particulares" value={a.particuliers} testId="journey-particuliers" />
        <Metric label="Contas de teste / internas" value={a.test_or_internal}
                note={`${a.admins}admin(s) · excluídos do total acima`} testId="journey-tests" />
        <Metric label="Entreprises (SIRET distinct)" value={a.companies_with_siret}
                note="declarativo, introduzido pelo utilizador" testId="journey-companies" />
        <Metric label="Organisations" value={a.organizations} testId="journey-orgs" />
        <Metric label="Contas eliminadas" value={a.deleted_since_tracking}
                note="desde a implementação do acompanhamento" testId="journey-deleted" />
        <Metric label="Lignes brutes en base" value={a.all_rows_in_db} testId="journey-raw" />
      </Block>

      <Block icon={Activity} title="Atividade e clientes pagantes" testId="journey-activity">
        <Metric label={`Ativos em${data.window_days} j`} value={act.active_users_window}
                note={act.active_definition} testId="journey-active" />
        <Metric label="Já ligados pelo menos uma vez" value={act.ever_connected}
                note="contas existentes que iniciaram sessão" testId="journey-ever" />
        <Metric label="Clients payants" value={act.paying_customers}
                note={act.paying_note} testId="journey-paying" />
        <Metric label="Sessões não associáveis" value={act.session_holders_not_countable}
                note="sessões de contas eliminadas ou de testes: excluídas dos ativos"
                testId="journey-orphans" />
      </Block>

      <Block icon={Route} title="Percurso instrumentado" testId="journey-funnel">
        <Metric label="Inscrições (janela)" value={j.signups_window}
                note={data.instrumentation_started_at
                  ? "inscrições registadas pela instrumentação na janela"
                  : "a instrumentação acabou de ser ativada: este contador começa na próxima inscrição"}
                testId="journey-signups" />
        <Metric label="Primeiro valor atingido" value={j.first_value_window}
                note={j.first_value_definition} testId="journey-firstvalue" />
        <Metric label="Taux d'activation" value={j.activation_rate_pct} suffix=" %"
                note="primeiro valor / inscrições da janela" testId="journey-activation" />
        <Metric label="Contas anteriores ao acompanhamento" value={j.accounts_before_instrumentation}
                note="proveniência não resolvida: estas contas existiam antes da instrumentação"
                testId="journey-before" />
      </Block>

      <Block icon={Building2} title="Proveniência das inscrições" testId="journey-acquisition">
        {data.acquisition.length === 0 ? (
          <div className="surface rounded-md p-4 sm:col-span-2 lg:col-span-4 flex items-start gap-2"
               data-testid="journey-acquisition-empty">
            <HelpCircle className="h-4 w-4 text-amber-500 shrink-0 mt-0.5" />
            <p className="text-sm text-muted-foreground">
              Nenhuma inscrição registada pela instrumentação nesta janela. As inscrições anteriores não têm proveniência associada: continuarão a ser contadas separadamente.
            </p>
          </div>
        ) : data.acquisition.map((c) => (
          <Metric key={c.channel} label={c.channel} value={c.signups} testId={`journey-channel-${c.channel}`} />
        ))}
      </Block>

      <section className="grid gap-3" data-testid="journey-events">
        <p className="font-semibold flex items-center gap-2 text-sm">
          <CreditCard className="h-4 w-4 text-primary" /> Últimos eventos registados
        </p>
        {events.length === 0 ? (
          <p className="text-sm text-muted-foreground" data-testid="journey-events-empty">
            Nenhum evento por agora. Aparecerão na próxima inscrição ou estimativa.
          </p>
        ) : (
          <div className="surface rounded-md overflow-x-auto">
            <table className="w-full text-sm min-w-[620px]">
              <thead>
                <tr className="text-left text-[11px] uppercase tracking-wider text-muted-foreground border-b border-border">
                  <th className="px-4 py-2.5">Date</th>
                  <th className="px-4 py-2.5">Evento</th>
                  <th className="px-4 py-2.5">Canal</th>
                  <th className="px-4 py-2.5">Detalhes</th>
                </tr>
              </thead>
              <tbody>
                {events.map((e, i) => (
                  <tr key={i} className="border-b border-border/40" data-testid={`journey-event-${i}`}>
                    <td className="px-4 py-2 whitespace-nowrap">{new Date(e.occurred_at).toLocaleString("fr-FR")}</td>
                    <td className="px-4 py-2 font-semibold">{e.event}</td>
                    <td className="px-4 py-2">{e.channel}</td>
                    <td className="px-4 py-2 text-xs text-muted-foreground">
                      {Object.entries(e.props || {}).map(([k, v]) => `${k}=${v}`).join(" · ") || "—"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  );
}
