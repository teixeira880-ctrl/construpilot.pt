import { useRef, useState } from "react";
import { Plus, Minus, RotateCcw } from "lucide-react";

/**
 * Pinch-to-zoom sem dependências. Suporta:
 *   - pinch (2 dedos) em mobile
 *   - duplo-clique em desktop para zoom in/out
 *   - botões +/-/reset sempre visíveis (acessibilidade desktop + mobile)
 *   - pan via drag quando ampliado
 *
 * `touch-action: none` no container evita scroll da página durante o gesto.
 */
export default function PinchZoom({
  children,
  maxScale = 4,
  minScale = 1,
  className = "",
  testId = "pinch-zoom",
  showControls = true,
}) {
  const [scale, setScale] = useState(1);
  const [tx, setTx] = useState(0);
  const [ty, setTy] = useState(0);
  const stateRef = useRef({ pinching: false, initDist: 0, initScale: 1, panning: false, px: 0, py: 0 });

  const distance = (touches) => {
    const [a, b] = touches;
    return Math.hypot(a.clientX - b.clientX, a.clientY - b.clientY);
  };

  const clamp = (v) => Math.max(minScale, Math.min(maxScale, v));

  const onTouchStart = (e) => {
    if (e.touches.length === 2) {
      stateRef.current.pinching = true;
      stateRef.current.initDist = distance(e.touches);
      stateRef.current.initScale = scale;
    } else if (e.touches.length === 1) {
      stateRef.current.panning = true;
      stateRef.current.px = e.touches[0].clientX - tx;
      stateRef.current.py = e.touches[0].clientY - ty;
    }
  };
  const onTouchMove = (e) => {
    if (stateRef.current.pinching && e.touches.length === 2) {
      const d = distance(e.touches);
      setScale(clamp((stateRef.current.initScale * d) / stateRef.current.initDist));
    } else if (stateRef.current.panning && e.touches.length === 1 && scale > 1) {
      setTx(e.touches[0].clientX - stateRef.current.px);
      setTy(e.touches[0].clientY - stateRef.current.py);
    }
  };
  const onTouchEnd = (e) => {
    if (e.touches.length === 0) {
      stateRef.current.pinching = false;
      stateRef.current.panning = false;
      if (scale <= 1.01) {
        setScale(1);
        setTx(0);
        setTy(0);
      }
    }
  };
  const onDblClick = () => {
    if (scale > 1) {
      setScale(1); setTx(0); setTy(0);
    } else {
      setScale(2);
    }
  };

  const zoomIn = () => setScale((s) => clamp(s * 1.25));
  const zoomOut = () => {
    const next = clamp(scale / 1.25);
    setScale(next);
    if (next <= 1.01) { setTx(0); setTy(0); }
  };
  const reset = () => { setScale(1); setTx(0); setTy(0); };

  return (
    <div
      className={`relative overflow-hidden select-none ${className}`}
      style={{ touchAction: "none" }}
      onTouchStart={onTouchStart}
      onTouchMove={onTouchMove}
      onTouchEnd={onTouchEnd}
      onDoubleClick={onDblClick}
      data-testid={testId}
    >
      <div
        style={{
          transform: `translate(${tx}px, ${ty}px) scale(${scale})`,
          transformOrigin: "center center",
          transition: stateRef.current.pinching || stateRef.current.panning ? "none" : "transform 0.2s ease-out",
        }}
      >
        {children}
      </div>

      {showControls && (
        <div
          className="absolute top-2 right-2 z-10 flex flex-col gap-1 rounded-md border border-border bg-background/90 backdrop-blur p-1 shadow dark:bg-neutral-900/90 dark:border-neutral-700"
          data-testid={`${testId}-controls`}
        >
          <button
            type="button"
            onClick={zoomIn}
            disabled={scale >= maxScale}
            aria-label="Ampliar"
            data-testid={`${testId}-in`}
            className="h-9 w-9 inline-flex items-center justify-center rounded-sm hover:bg-primary/10 disabled:opacity-40 disabled:pointer-events-none dark:text-neutral-200"
          >
            <Plus className="h-4 w-4" />
          </button>
          <button
            type="button"
            onClick={zoomOut}
            disabled={scale <= minScale}
            aria-label="Reduzir"
            data-testid={`${testId}-out`}
            className="h-9 w-9 inline-flex items-center justify-center rounded-sm hover:bg-primary/10 disabled:opacity-40 disabled:pointer-events-none dark:text-neutral-200"
          >
            <Minus className="h-4 w-4" />
          </button>
          <button
            type="button"
            onClick={reset}
            disabled={scale === 1 && tx === 0 && ty === 0}
            aria-label="Repor zoom"
            data-testid={`${testId}-reset`}
            className="h-9 w-9 inline-flex items-center justify-center rounded-sm hover:bg-primary/10 disabled:opacity-40 disabled:pointer-events-none dark:text-neutral-200"
          >
            <RotateCcw className="h-4 w-4" />
          </button>
        </div>
      )}
    </div>
  );
}
