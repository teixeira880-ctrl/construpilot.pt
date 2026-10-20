import { useEffect, useState } from "react";

// Fundo suave: base marfim quente com halos cobre e sálvia desfocados, em deriva lenta.
// Fica parado quando o separador está oculto ou quando o sistema pede menos movimento (CSS).
export function WorkspaceBackdrop() {
  const [hidden, setHidden] = useState(() => (typeof document !== "undefined" ? document.hidden : false));
  useEffect(() => {
    const update = () => setHidden(document.hidden);
    document.addEventListener("visibilitychange", update);
    return () => document.removeEventListener("visibilitychange", update);
  }, []);
  return (
    <div className="workspace-backdrop" data-testid="workspace-backdrop" data-paused={hidden} aria-hidden="true">
      <span className="workspace-halo workspace-halo-copper" />
      <span className="workspace-halo workspace-halo-sage" />
    </div>
  );
}
