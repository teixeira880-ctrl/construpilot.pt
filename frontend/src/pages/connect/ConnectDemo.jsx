import { Link, useNavigate, useParams } from "react-router-dom";
import { ArrowRight } from "lucide-react";
import { tr, useConnectLang } from "@/connect/i18n";
import { ConnectShell, usePageMeta } from "@/connect/components";
import DemoPlayer from "@/connect/DemoPlayer";
import { DEMOS } from "@/connect/engine";

/** Demonstração pública (sem dados pessoais): /connect/demo/:id */
export default function ConnectDemo() {
  const { id } = useParams();
  const navigate = useNavigate();
  const { lang, setLang, t } = useConnectLang();
  const demo = DEMOS[id];
  usePageMeta(demo ? tr(demo.title, lang) : t("watch"), t("home_promise"));
  return (
    <ConnectShell lang={lang} setLang={setLang} t={t} wide>
      {demo ? (
        <>
          <DemoPlayer demoId={id} lang={lang} t={t} onSwitch={(d) => navigate(`/connect/demo/${d}`)}
            alternatives={["demo_takeoff", "demo_quote", "demo_margin", "demo_painting", "demo_documents", "demo_billing"].filter((d) => d !== id)} />
          <div className="mt-8 rounded-2xl border border-border bg-card p-6 text-center">
            <p className="font-display text-xl font-semibold">{t("home_promise")}</p>
            <Link to="/connect/client" className="mt-4 inline-flex items-center gap-2 rounded-xl bg-primary px-5 py-3 font-semibold text-primary-foreground" data-testid="demo-start-diagnosis">
              {t("start")} <ArrowRight className="h-4 w-4" aria-hidden />
            </Link>
          </div>
        </>
      ) : (
        <p data-testid="demo-not-found">404 — <Link to="/connect" className="underline">{t("restart")}</Link></p>
      )}
    </ConnectShell>
  );
}
