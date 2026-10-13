import { useRef, useState, useCallback } from "react";

export function BeforeAfterSlider({ before, after, height = 380 }) {
  const [pos, setPos] = useState(50);
  const ref = useRef(null);
  const dragging = useRef(false);

  const move = useCallback((clientX) => {
    const el = ref.current;
    if (!el) return;
    const rect = el.getBoundingClientRect();
    const pct = ((clientX - rect.left) / rect.width) * 100;
    setPos(Math.max(0, Math.min(100, pct)));
  }, []);

  const onDown = (e) => { dragging.current = true; move(e.clientX ?? e.touches?.[0]?.clientX); };
  const onMove = (e) => { if (dragging.current) move(e.clientX ?? e.touches?.[0]?.clientX); };
  const stop = () => { dragging.current = false; };

  return (
    <div
      ref={ref}
      className="relative w-full select-none overflow-hidden rounded-lg border border-border bg-black touch-none"
      style={{ height }}
      onMouseMove={onMove}
      onMouseUp={stop}
      onMouseLeave={stop}
      onTouchMove={onMove}
      onTouchEnd={stop}
      data-testid="before-after-slider"
    >
      {/* Après (fond) */}
      <img src={after} alt="Após" className="absolute inset-0 h-full w-full object-contain" draggable={false} />
      <span className="absolute right-3 top-3 rounded-full bg-black/60 px-2 py-0.5 text-[11px] font-semibold text-white">Após</span>

      {/* Avant (clip à gauche du curseur) */}
      <div className="absolute inset-0 overflow-hidden" style={{ width: `${pos}%` }}>
        <img
          src={before}
          alt="Avant"
          className="absolute inset-0 h-full object-contain"
          style={{ width: ref.current ? ref.current.getBoundingClientRect().width : "100%", maxWidth: "none" }}
          draggable={false}
        />
        <span className="absolute left-3 top-3 rounded-full bg-primary px-2 py-0.5 text-[11px] font-semibold text-primary-foreground">Avant</span>
      </div>

      {/* Poignée */}
      <div
        className="absolute top-0 bottom-0 z-10 flex cursor-ew-resize items-center justify-center"
        style={{ left: `calc(${pos}% - 18px)`, width: 36 }}
        onMouseDown={onDown}
        onTouchStart={onDown}
        data-testid="before-after-handle"
      >
        <div className="absolute top-0 bottom-0 left-1/2 w-0.5 -translate-x-1/2 bg-white shadow" />
        <div className="relative flex h-9 w-9 items-center justify-center rounded-full bg-white shadow-lg ring-1 ring-black/10">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" className="text-slate-700">
            <path d="M8 7l-4 5 4 5M16 7l4 5-4 5" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
        </div>
      </div>
    </div>
  );
}
