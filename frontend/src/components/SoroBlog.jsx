import { useEffect, useRef, useState } from "react";

const SORO_SRC = "https://app.trysoro.com/api/embed/5160a050-06b9-473f-aa12-4cd9a5150663";

export function SoroBlog() {
  const holder = useRef(null);
  const [hasContent, setHasContent] = useState(false);

  useEffect(() => {
    // Charge le script Soro une seule fois (compatible SPA React)
    let script = document.querySelector(`script[data-soro="1"]`);
    if (!script) {
      script = document.createElement("script");
      script.src = SORO_SRC;
      script.defer = true;
      script.setAttribute("data-soro", "1");
      document.body.appendChild(script);
    }

    // Détecte si l'embed a bien injecté du contenu dans #soro-blog
    let tries = 0;
    const timer = setInterval(() => {
      tries += 1;
      if (holder.current && holder.current.childNodes.length > 0) {
        setHasContent(true);
        clearInterval(timer);
      } else if (tries > 12) {
        clearInterval(timer);
      }
    }, 500);

    return () => clearInterval(timer);
  }, []);

  return (
    <section className="border-t border-border bg-secondary/20" id="blog" data-testid="blog-section">
      <div className="mx-auto max-w-[1100px] px-6 lg:px-10 py-24 lg:py-32">
        <div className="text-center mb-14">
          <p className="overline">Le blog ConstruPilot</p>
          <h2 className="mt-4 font-display text-3xl lg:text-4xl font-bold tracking-tight">
            Conseils, métré &amp; actualités du bâtiment
          </h2>
        </div>

        <div id="soro-blog" ref={holder} data-testid="soro-blog" />

        {!hasContent && (
          <p className="text-center text-muted-foreground text-sm" data-testid="blog-empty">
            Nos articles arrivent très bientôt.
          </p>
        )}
      </div>
    </section>
  );
}
