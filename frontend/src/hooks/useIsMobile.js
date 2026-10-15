import { useEffect, useState } from "react";

/**
 * Hook SSR-safe que devolve `true` abaixo do breakpoint md do Tailwind (<768 px).
 * Reage a mudanças de orientação / resize.
 */
export function useIsMobile(breakpointPx = 767.98) {
  const query = `(max-width: ${breakpointPx}px)`;
  const [isMobile, setIsMobile] = useState(() => {
    if (typeof window === "undefined") return false;
    return window.matchMedia(query).matches;
  });

  useEffect(() => {
    if (typeof window === "undefined") return undefined;
    const mq = window.matchMedia(query);
    const handler = (e) => setIsMobile(e.matches);
    // Compat: Safari antigo usa addListener
    if (mq.addEventListener) mq.addEventListener("change", handler);
    else mq.addListener(handler);
    return () => {
      if (mq.removeEventListener) mq.removeEventListener("change", handler);
      else mq.removeListener(handler);
    };
  }, [query]);

  return isMobile;
}

export default useIsMobile;
