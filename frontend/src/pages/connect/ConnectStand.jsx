import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { Expand, HardHat, Building2, Handshake, RotateCcw, Timer } from "lucide-react";
import { useConnectLang } from "@/connect/i18n";
import { ConnectShell, usePageMeta } from "@/connect/components";
import { clearAll, flushOutbox, outboxSize } from "@/connect/api";

const IDLE_MS = 3 * 60 * 1000;
const QS = "source=websummit2026&utm_source=websummit2026&utm_medium=screen";

/**
 * Modo stand Web Summit (/connect/stand): três QR Codes para os telemóveis dos visitantes
 * e uma demonstração rápida no ecrã do stand (tablet/monitor), com reinício entre visitantes.
 * Funciona sem rede: diagnóstico e demos usam o motor local e os instantâneos do motor real.
 */
export default function ConnectStand() {
  const { lang, setLang, t } = useConnectLang();
  const navigate = useNavigate();
  const [pending, setPending] = useState(outboxSize());
  usePageMeta(t("stand_title"), t("home_promise"));

  useEffect(() => {
    flushOutbox().then(() => setPending(outboxSize()));
    let timer = setTimeout(() => { clearAll(); }, IDLE_MS);
    const reset = () => { clearTimeout(timer); timer = setTimeout(() => clearAll(), IDLE_MS); };
    ["pointerdown", "keydown"].forEach((e) => window.addEventListener(e, reset));
    const iv = setInterval(() => flushOutbox().then(() => setPending(outboxSize())), 30000);
    return () => { clearTimeout(timer); clearInterval(iv); ["pointerdown", "keydown"].forEach((e) => window.removeEventListener(e, reset)); };
  }, []);

  const full = () => { try { document.documentElement.requestFullscreen(); } catch { /* noop */ } };
  const profiles = [
    { id: "client", icon: HardHat, label: t("profile_client") },
    { id: "investor", icon: Building2, label: t("profile_investor") },
    { id: "partner", icon: Handshake, label: t("profile_partner") },
  ];
  return (
    <ConnectShell lang={lang} setLang={setLang} t={t} stand wide>
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="text-xs font-mono uppercase tracking-[0.18em] text-[#8a5524] dark:text-[#e0a46a]">Web Summit 2026 · Lisboa</p>
          <h1 className="mt-2 font-display text-4xl sm:text-5xl font-bold tracking-tight">{t("home_title")}</h1>
          <p className="mt-2 text-lg text-muted-foreground">{t("stand_scan")}</p>
        </div>
        <div className="flex gap-2">
          <button type="button" onClick={full} className="inline-flex items-center gap-2 rounded-xl border border-border px-4 py-2.5 text-sm"><Expand className="h-4 w-4" aria-hidden />{t("demo_fullscreen")}</button>
          <button type="button" onClick={() => { clearAll(); navigate(0); }} className="inline-flex items-center gap-2 rounded-xl border border-border px-4 py-2.5 text-sm" data-testid="stand-reset-top"><RotateCcw className="h-4 w-4" aria-hidden />{t("stand_reset")}</button>
        </div>
      </div>

      <div className="mt-8 grid gap-5 md:grid-cols-3">
        {profiles.map(({ id, icon: Icon, label }) => (
          <figure key={id} className="flex flex-col items-center rounded-2xl border border-border bg-card p-6 text-center shadow-sm" data-testid={`stand-qr-${id}`}>
            <img src={`/connect/qr-${id}.svg`} alt={`QR — ${label}`} className="h-48 w-48 sm:h-56 sm:w-56" width="224" height="224" />
            <figcaption className="mt-4 flex items-center gap-2 font-display text-lg font-semibold"><Icon className="h-5 w-5 text-primary" aria-hidden />{label}</figcaption>
            <Link to={`/connect/${id}?${QS}&mode=stand`} className="mt-4 w-full rounded-xl bg-primary px-4 py-3 font-semibold text-primary-foreground" data-testid={`stand-quick-${id}`}>
              {t("stand_quick")}
            </Link>
          </figure>
        ))}
      </div>
      <p className="mt-6 flex items-center gap-2 text-xs text-muted-foreground"><Timer className="h-3.5 w-3.5" aria-hidden />{t("stand_qr_note")} · reset 3 min{pending ? ` · ${pending} ⇡` : ""}</p>
    </ConnectShell>
  );
}
