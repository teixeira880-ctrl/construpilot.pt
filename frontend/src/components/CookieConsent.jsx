import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { Cookie } from "lucide-react";
import { Button } from "@/components/ui/button";

const KEY = "cp_cookie_consent";

export default function CookieConsent() {
  const [show, setShow] = useState(false);

  useEffect(() => {
    if (!localStorage.getItem(KEY)) setShow(true);
  }, []);

  const decide = (value) => {
    localStorage.setItem(KEY, value);
    window.dispatchEvent(new CustomEvent("cp-cookie-consent", { detail: value }));
    setShow(false);
  };

  if (!show) return null;

  return (
    <div
      className="fixed bottom-0 inset-x-0 z-[100] p-3 sm:p-4"
      data-testid="cookie-consent-banner"
      role="dialog"
      aria-label="Consentement aux cookies"
    >
      <div className="mx-auto max-w-3xl rounded-xl border border-border bg-background/95 backdrop-blur shadow-2xl p-4 sm:p-5 flex flex-col sm:flex-row sm:items-center gap-4">
        <div className="flex items-start gap-3 flex-1">
          <div className="h-9 w-9 shrink-0 rounded-lg bg-primary/10 grid place-items-center">
            <Cookie className="h-5 w-5 text-primary" />
          </div>
          <p className="text-sm text-foreground/90 leading-relaxed">
            Nous utilisons des cookies nécessaires au fonctionnement du site et, avec votre accord,
            des cookies de mesure d'audience et publicité. En savoir plus dans notre{" "}
            <Link to="/confidentialite" className="text-primary underline underline-offset-2">
              politique de confidentialité
            </Link>.
          </p>
        </div>
        <div className="flex gap-2 shrink-0">
          <Button
            variant="outline"
            className="rounded-sm flex-1 sm:flex-none"
            onClick={() => decide("refused")}
            data-testid="cookie-refuse-btn"
          >
            Refuser
          </Button>
          <Button
            className="rounded-sm flex-1 sm:flex-none"
            onClick={() => decide("accepted")}
            data-testid="cookie-accept-btn"
          >
            Tout accepter
          </Button>
        </div>
      </div>
    </div>
  );
}
