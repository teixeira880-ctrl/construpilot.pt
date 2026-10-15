import { useEffect, useState } from "react";
import { Link, useLocation } from "react-router-dom";
import { Cookie } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useI18n } from "@/context/I18nContext";

const KEY = "cp_cookie_consent";

export default function CookieConsent() {
  const { t } = useI18n();
  const { pathname } = useLocation();
  const [show, setShow] = useState(false);

  useEffect(() => {
    if (!localStorage.getItem(KEY)) setShow(true);
  }, []);

  const decide = (value) => {
    localStorage.setItem(KEY, value);
    window.dispatchEvent(new CustomEvent("cp-cookie-consent", { detail: value }));
    setShow(false);
  };

  // No modo demo (Web Summit) o banner não aparece — a demo é ponto único de
  // contacto com visitantes e não deve interferir com a interação.
  if (!show || pathname === "/demo") return null;

  return (
    <div
      className="fixed inset-x-0 bottom-14 md:bottom-0 z-[100] p-3 sm:p-4 pointer-events-none"
      data-testid="cookie-consent-banner"
      role="dialog"
      aria-label="Consentimento de cookies"
    >
      <div className="mx-auto max-w-3xl rounded-xl border border-border bg-background/95 backdrop-blur shadow-2xl p-4 sm:p-5 flex flex-col sm:flex-row sm:items-center gap-4 pointer-events-none">
        <div className="flex items-start gap-3 flex-1">
          <div className="h-9 w-9 shrink-0 rounded-lg bg-primary/10 grid place-items-center">
            <Cookie className="h-5 w-5 text-primary" />
          </div>
          <p className="text-sm text-foreground/90 leading-relaxed">
            {t("cookie.text")}{" "}
            <Link to="/confidentialite" className="text-primary underline underline-offset-2 pointer-events-auto">
              {t("cookie.policy")}
            </Link>.
          </p>
        </div>
        <div className="flex gap-2 shrink-0 pointer-events-auto">
          <Button
            variant="outline"
            className="rounded-sm flex-1 sm:flex-none"
            onClick={() => decide("refused")}
            data-testid="cookie-refuse-btn"
          >
            {t("cookie.refuse")}
          </Button>
          <Button
            className="rounded-sm flex-1 sm:flex-none"
            onClick={() => decide("accepted")}
            data-testid="cookie-accept-btn"
          >
            {t("cookie.accept")}
          </Button>
        </div>
      </div>
    </div>
  );
}
