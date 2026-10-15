import { useEffect } from "react";
import { useNavigate } from "react-router-dom";

/**
 * Swipe-to-go-back — ouve touchstart/move/end na borda esquerda (<20px) e
 * chama navigate(-1) após threshold horizontal (80px) e sem muito deslocamento
 * vertical (<60px) para evitar falsos positivos durante scroll.
 */
export function useSwipeBack({ enabled = true, edgePx = 20, thresholdX = 80, maxDy = 60 } = {}) {
  const nav = useNavigate();
  useEffect(() => {
    if (!enabled) return;
    if (typeof window === "undefined" || !("ontouchstart" in window)) return;

    let startX = null;
    let startY = null;

    const onStart = (e) => {
      const x = e.touches[0].clientX;
      const y = e.touches[0].clientY;
      if (x <= edgePx) {
        startX = x;
        startY = y;
      }
    };
    const onMove = (e) => {
      /* não é necessário fazer nada aqui; mantemos leve */
    };
    const onEnd = (e) => {
      if (startX == null) return;
      const touch = e.changedTouches?.[0];
      if (!touch) {
        startX = null;
        return;
      }
      const dx = touch.clientX - startX;
      const dy = Math.abs(touch.clientY - startY);
      if (dx >= thresholdX && dy <= maxDy) {
        nav(-1);
      }
      startX = null;
      startY = null;
    };

    window.addEventListener("touchstart", onStart, { passive: true });
    window.addEventListener("touchmove", onMove, { passive: true });
    window.addEventListener("touchend", onEnd, { passive: true });
    return () => {
      window.removeEventListener("touchstart", onStart);
      window.removeEventListener("touchmove", onMove);
      window.removeEventListener("touchend", onEnd);
    };
  }, [enabled, edgePx, thresholdX, maxDy, nav]);
}
