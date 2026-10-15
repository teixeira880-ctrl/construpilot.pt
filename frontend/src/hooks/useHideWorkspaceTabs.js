import { useEffect } from "react";

/**
 * Enquanto `active` for true, adiciona a classe `wizard-hides-tabs` ao <body>.
 * O CSS global (workspace.css) usa essa classe para esconder:
 *   - `.workspace-mobile-tabs` (MobileTabBar PWA/workspace)
 *   - `[data-testid="bottom-tabs"]` (BottomTabBar global)
 *
 * Serve para evitar sobreposição entre a nav fixa de um wizard mobile (ex.
 * StairCalculator Lote S2) e a tab bar global, ambas em `z-index:40` + `bottom:0`.
 *
 * Limpa a classe no unmount ou quando `active` passar a false.
 */
export function useHideWorkspaceTabs(active) {
  useEffect(() => {
    if (typeof document === "undefined") return undefined;
    if (!active) {
      document.body.classList.remove("wizard-hides-tabs");
      return undefined;
    }
    document.body.classList.add("wizard-hides-tabs");
    return () => {
      document.body.classList.remove("wizard-hides-tabs");
    };
  }, [active]);
}

export default useHideWorkspaceTabs;
