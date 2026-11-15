import { useEffect } from "react";
import { Link, useLocation } from "react-router-dom";
import { ArrowRight, Building2, Handshake, HardHat, Ruler } from "lucide-react";
import { useConnectLang } from "@/connect/i18n";
import { ConnectShell, usePageMeta } from "@/connect/components";
import { flushOutbox } from "@/connect/api";

const PROFILES = [
  { id: "client", icon: HardHat, title: "profile_client", desc: "profile_client_d" },
  { id: "investor", icon: Building2, title: "profile_investor", desc: "profile_investor_d" },
  { id: "partner", icon: Handshake, title: "profile_partner", desc: "profile_partner_d" },
];

export default function ConnectHome() {
  const { lang, setLang, t } = useConnectLang();
  const { search } = useLocation();
  useEffect(() => { flushOutbox(); }, []);
  const qs = search || "";
  usePageMeta(t("home_title"), t("home_promise"));
  return (
    <ConnectShell lang={lang} setLang={setLang} t={t}>
      <section className="relative">
        <p className="inline-flex items-center gap-2 rounded-full border border-border bg-card px-3 py-1 text-xs font-mono uppercase tracking-[0.16em] text-muted-foreground">
          <Ruler className="h-3.5 w-3.5 text-[#8a5524] dark:text-[#e0a46a]" aria-hidden /> {t("home_no_account")}
        </p>
        <h1 className="mt-5 max-w-3xl font-display text-4xl sm:text-6xl font-bold leading-[1.02] tracking-tight" data-testid="connect-title">
          {t("home_title")}
        </h1>
        <p className="mt-4 max-w-2xl text-lg text-muted-foreground">{t("home_sub")}</p>
        <p className="mt-2 max-w-2xl text-base">
          <span className="border-b-2 border-[#B87333]/60">{t("home_promise")}</span>
        </p>
      </section>
      <nav aria-label={t("start")} className="mt-10 grid gap-4 md:grid-cols-3">
        {PROFILES.map(({ id, icon: Icon, title, desc }, k) => (
          <Link key={id} to={`/connect/${id}${qs}`} data-testid={`connect-profile-${id}`}
            className="group relative flex flex-col rounded-2xl border border-border bg-card p-6 shadow-sm transition-all hover:-translate-y-0.5 hover:border-primary/60 hover:shadow-md focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring motion-reduce:transition-none motion-reduce:hover:translate-y-0">
            <span className="font-mono text-xs text-muted-foreground">{String.fromCharCode(65 + k)}</span>
            <span className="mt-3 grid h-11 w-11 place-items-center rounded-xl bg-accent text-primary"><Icon className="h-5 w-5" aria-hidden /></span>
            <span className="mt-4 font-display text-xl font-semibold tracking-tight">{t(title)}</span>
            <span className="mt-2 text-sm text-muted-foreground">{t(desc)}</span>
            <span className="mt-6 inline-flex items-center gap-1.5 text-sm font-semibold text-primary">
              {t("start")} <ArrowRight className="h-4 w-4 transition-transform group-hover:translate-x-0.5 motion-reduce:transition-none" aria-hidden />
            </span>
          </Link>
        ))}
      </nav>
    </ConnectShell>
  );
}
