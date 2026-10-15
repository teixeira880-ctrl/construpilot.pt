import { useRef, useState } from "react";
import { Loader2 } from "lucide-react";

/**
 * Pull-to-refresh — só touch devices. Em desktop a função é no-op.
 *
 * Props:
 *  - onRefresh: () => Promise<void>
 *  - threshold?: number (px, default 70)
 *  - children: ReactNode
 */
export default function PullToRefresh({ onRefresh, threshold = 70, children }) {
  const [pull, setPull] = useState(0);
  const [refreshing, setRefreshing] = useState(false);
  const startY = useRef(null);
  const scrollerRef = useRef(null);

  const isTouch = typeof window !== "undefined" && "ontouchstart" in window;

  const onTouchStart = (e) => {
    if (!isTouch || refreshing) return;
    const scroller = scrollerRef.current || window;
    const atTop = (scroller.scrollTop ?? window.scrollY) <= 0;
    if (!atTop) return;
    startY.current = e.touches[0].clientY;
  };

  const onTouchMove = (e) => {
    if (startY.current == null) return;
    const dy = e.touches[0].clientY - startY.current;
    if (dy > 0) setPull(Math.min(dy, threshold * 1.5));
  };

  const onTouchEnd = async () => {
    if (startY.current == null) return;
    startY.current = null;
    if (pull >= threshold && onRefresh) {
      setRefreshing(true);
      try {
        await onRefresh();
      } finally {
        setRefreshing(false);
      }
    }
    setPull(0);
  };

  const progress = Math.min(pull / threshold, 1);

  return (
    <div
      ref={scrollerRef}
      onTouchStart={onTouchStart}
      onTouchMove={onTouchMove}
      onTouchEnd={onTouchEnd}
      className="relative"
      data-testid="pull-to-refresh"
    >
      <div
        className="pointer-events-none flex items-center justify-center overflow-hidden transition-[height] duration-150"
        style={{ height: refreshing ? 48 : pull }}
        data-testid="pull-to-refresh-indicator"
      >
        {refreshing ? (
          <Loader2 className="h-5 w-5 animate-spin text-primary" aria-hidden="true" />
        ) : (
          <div
            className="h-5 w-5 rounded-full border-2 border-primary border-t-transparent transition-transform"
            style={{ transform: `rotate(${progress * 360}deg)`, opacity: progress }}
          />
        )}
      </div>
      {children}
    </div>
  );
}
