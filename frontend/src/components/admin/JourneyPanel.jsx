import { useCallback, useEffect, useState } from "react";
import { RefreshCw, Users, Activity, Building2, CreditCard, Route, HelpCircle } from "lucide-react";
import { Button } from "@/components/ui/button";
import { api } from "@/lib/api";

/** Affiche « non mesurable » plutôt qu'un zéro inventé. */
const Value = ({ v, suffix = "" }) =>
  v === null || v === undefined ? (
    <span className="text-sm font-normal text-amber-500">non mesurable</span>
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
    return <p className="text-sm text-muted-foreground" data-testid="journey-loading">Chargement des chiffres réels…</p>;
  }

  const a = data.accounts, act = data.activity, j = data.journey;

  return (
    <div className="grid gap-8" data-testid="journey-panel">
      <div className="flex flex-wrap items-center gap-3">
        <div className="flex-1 min-w-0">
          <h2 className="font-display text-xl font-extrabold">Comptes réels & parcours</h2>
          <p className="text-xs text-muted-foreground">
            Fenêtre : {data.window_days} jours · Généré le {new Date(data.generated_at).toLocaleString("fr-FR")} ·
            Instrumentation démarrée : {data.instrumentation_started_at
              ? new Date(data.instrumentation_started_at).toLocaleString("fr-FR")
              : "aucun événement enregistré pour l'instant"}
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
                note="hors comptes de test et adresses internes" testId="journey-existing" />
        <Metric label="Dont pros" value={a.pros} testId="journey-pros" />
        <Metric label="Dont particuliers" value={a.particuliers} testId="journey-particuliers" />
        <Metric label="Comptes de test / internes" value={a.test_or_internal}
                note={`${a.admins} admin(s) · exclus du total ci-dessus`} testId="journey-tests" />
        <Metric label="Entreprises (SIRET distinct)" value={a.companies_with_siret}
                note="déclaratif, saisi par l'utilisateur" testId="journey-companies" />
        <Metric label="Organisations" value={a.organizations} testId="journey-orgs" />
        <Metric label="Comptes supprimés" value={a.deleted_since_tracking}
                note="depuis la mise en place du suivi" testId="journey-deleted" />
        <Metric label="Lignes brutes en base" value={a.all_rows_in_db} testId="journey-raw" />
      </Block>

      <Block icon={Activity} title="Activité et clients payants" testId="journey-activity">
        <Metric label={`Actifs sur ${data.window_days} j`} value={act.active_users_window}
                note={act.active_definition} testId="journey-active" />
        <Metric label="Déjà connectés au moins une fois" value={act.ever_connected}
                note="comptes existants ayant ouvert une session" testId="journey-ever" />
        <Metric label="Clients payants" value={act.paying_customers}
                note={act.paying_note} testId="journey-paying" />
        <Metric label="Sessions non rattachables" value={act.session_holders_not_countable}
                note="sessions de comptes supprimés ou de tests : exclues des actifs"
                testId="journey-orphans" />
      </Block>

      <Block icon={Route} title="Parcours instrumenté" testId="journey-funnel">
        <Metric label="Inscriptions (fenêtre)" value={j.signups_window}
                note={data.instrumentation_started_at
                  ? "inscriptions enregistrées par l'instrumentation sur la fenêtre"
                  : "l'instrumentation vient d'être activée : ce compteur démarre à la prochaine inscription"}
                testId="journey-signups" />
        <Metric label="Première valeur atteinte" value={j.first_value_window}
                note={j.first_value_definition} testId="journey-firstvalue" />
        <Metric label="Taux d'activation" value={j.activation_rate_pct} suffix=" %"
                note="première valeur / inscriptions de la fenêtre" testId="journey-activation" />
        <Metric label="Comptes antérieurs au suivi" value={j.accounts_before_instrumentation}
                note="provenance non résolue : ces comptes existaient avant l'instrumentation"
                testId="journey-before" />
      </Block>

      <Block icon={Building2} title="Provenance des inscriptions" testId="journey-acquisition">
        {data.acquisition.length === 0 ? (
          <div className="surface rounded-md p-4 sm:col-span-2 lg:col-span-4 flex items-start gap-2"
               data-testid="journey-acquisition-empty">
            <HelpCircle className="h-4 w-4 text-amber-500 shrink-0 mt-0.5" />
            <p className="text-sm text-muted-foreground">
              Aucune inscription enregistrée par l'instrumentation sur cette fenêtre. Les inscriptions
              antérieures n'ont pas de provenance rattachée : elles resteront comptées séparément.
            </p>
          </div>
        ) : data.acquisition.map((c) => (
          <Metric key={c.channel} label={c.channel} value={c.signups} testId={`journey-channel-${c.channel}`} />
        ))}
      </Block>

      <section className="grid gap-3" data-testid="journey-events">
        <p className="font-semibold flex items-center gap-2 text-sm">
          <CreditCard className="h-4 w-4 text-primary" /> Derniers événements enregistrés
        </p>
        {events.length === 0 ? (
          <p className="text-sm text-muted-foreground" data-testid="journey-events-empty">
            Aucun événement pour l'instant. Ils apparaîtront dès la prochaine inscription ou estimation.
          </p>
        ) : (
          <div className="surface rounded-md overflow-x-auto">
            <table className="w-full text-sm min-w-[620px]">
              <thead>
                <tr className="text-left text-[11px] uppercase tracking-wider text-muted-foreground border-b border-border">
                  <th className="px-4 py-2.5">Date</th>
                  <th className="px-4 py-2.5">Événement</th>
                  <th className="px-4 py-2.5">Canal</th>
                  <th className="px-4 py-2.5">Détails</th>
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
