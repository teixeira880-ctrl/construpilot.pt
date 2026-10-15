import { useRef, useState } from "react";

/**
 * Pinch-to-zoom simples sem dependências. Suporta: pinch (2 dedos) e scroll-wheel
 * (desktop). Pan via drag.
 *
 * `touch-action: none` no container evita que o browser scrolle a página
 * durante o gesto. Para que o scroll normal da página continue a funcionar
 * fora da imagem, o componente é usado só em contentor de altura fixa.
 */
export default function PinchZoom({ children, maxScale = 4, minScale = 1, className = "", testId = "pinch-zoom" }) {
  const [scale, setScale] = useState(1);
  const [tx, setTx] = useState(0);
  const [ty, setTy] = useState(0);
  const stateRef = useRef({ pinching: false, initDist: 0, initScale: 1, panning: false, px: 0, py: 0 });

  const distance = (touches) => {
    const [a, b] = touches;
    return Math.hypot(a.clientX - b.clientX, a.clientY - b.clientY);
  };

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
      const next = Math.max(minScale, Math.min(maxScale, (stateRef.current.initScale * d) / stateRef.current.initDist));
      setScale(next);
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
      setScale(1);
      setTx(0);
      setTy(0);
    } else {
      setScale(2);
    }
  };

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
    </div>
  );
}
