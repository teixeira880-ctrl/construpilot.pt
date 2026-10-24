import { useEffect } from "react";
import { Link, useLocation } from "react-router-dom";
import { ListChecks, RotateCcw } from "lucide-react";
import { STAND_IDLE_MS, isStandMode, resetStand } from "@/lib/standMode";

/**
 * Barra discreta do modo stand: volta ao guia, recomeça para o visitante seguinte e
 * reinicia sozinha a demo após 3 minutos sem utilização. Invisível fora do modo stand.
 */
export default function StandBar() {
  const { pathname } = useLocation();
  const on = isStandMode();

  useEffect(() => {
    if (!on) return undefined;
    let timer;
    const arm = () => {
      clearTimeout(timer);
      timer = setTimeout(() => {
        // Só recomeça se o visitante saiu do guia (no guia já está tudo limpo).
        if (window.location.pathname !== "/stand") resetStand();
      }, STAND_IDLE_MS);
    };
    const evs = ["pointerdown", "keydown", "wheel", "touchstart"];
    evs.forEach((e) => window.addEventListener(e, arm, { passive: true }));
    arm();
    return () => { clearTimeout(timer); evs.forEach((e) => window.removeEventListener(e, arm)); };
  }, [on]);

  if (!on || pathname === "/stand") return null;
  return (
    <div className="fixed bottom-4 left-4 z-[60] flex items-center gap-1 rounded-full border border-border bg-card/95 px-2 py-1 shadow-md backdrop-blur" data-testid="stand-bar">
      <Link to="/stand" className="inline-flex items-center gap-1 rounded-full px-3 py-1.5 text-xs font-medium text-primary hover:bg-primary/10" data-testid="stand-bar-guide">
        <ListChecks className="h-4 w-4" /> Guia da demo
      </Link>
      <button type="button" onClick={resetStand} className="inline-flex items-center gap-1 rounded-full px-3 py-1.5 text-xs text-muted-foreground hover:bg-muted" data-testid="stand-bar-reset">
        <RotateCcw className="h-4 w-4" /> Recomeçar
      </button>
    </div>
  );
}
