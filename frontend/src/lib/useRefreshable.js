import { useEffect, useRef } from "react";

// Rafraîchissement ciblé (tirer-pour-rafraîchir) sans reload complet.
// Les pages appellent useRefreshable(loadFn) ; MobileGestures émet "cp-refresh".
let handlerCount = 0;
export const hasRefreshHandler = () => handlerCount > 0;

export function useRefreshable(fn) {
  const ref = useRef(fn);
  ref.current = fn;
  useEffect(() => {
    handlerCount += 1;
    const onRefresh = () => { try { ref.current?.(); } catch { /* noop */ } };
    window.addEventListener("cp-refresh", onRefresh);
    return () => { handlerCount -= 1; window.removeEventListener("cp-refresh", onRefresh); };
  }, []);
}
