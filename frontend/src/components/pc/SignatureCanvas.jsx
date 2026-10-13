import { useEffect, useRef, useState } from "react";
import { Eraser } from "lucide-react";
import { Button } from "@/components/ui/button";

export const SignatureCanvas = ({ onChange }) => {
  const ref = useRef(null);
  const drawing = useRef(false);
  const hasInk = useRef(false);
  const [, force] = useState(0);

  useEffect(() => {
    const ctx = ref.current.getContext("2d");
    ctx.lineWidth = 2.4;
    ctx.lineCap = "round";
    ctx.lineJoin = "round";
    ctx.strokeStyle = "#0A0D14";
  }, []);

  const pos = (e) => {
    const r = ref.current.getBoundingClientRect();
    return {
      x: (e.clientX - r.left) * (ref.current.width / r.width),
      y: (e.clientY - r.top) * (ref.current.height / r.height),
    };
  };
  const start = (e) => {
    e.preventDefault();
    ref.current.setPointerCapture(e.pointerId);
    drawing.current = true;
    const ctx = ref.current.getContext("2d");
    const { x, y } = pos(e);
    ctx.beginPath();
    ctx.moveTo(x, y);
  };
  const move = (e) => {
    if (!drawing.current) return;
    e.preventDefault();
    const ctx = ref.current.getContext("2d");
    const { x, y } = pos(e);
    ctx.lineTo(x, y);
    ctx.stroke();
    if (!hasInk.current) { hasInk.current = true; force((n) => n + 1); }
  };
  const end = () => {
    if (!drawing.current) return;
    drawing.current = false;
    onChange?.(hasInk.current ? ref.current.toDataURL("image/png") : null);
  };
  const clear = () => {
    const c = ref.current;
    c.getContext("2d").clearRect(0, 0, c.width, c.height);
    hasInk.current = false;
    force((n) => n + 1);
    onChange?.(null);
  };

  return (
    <div className="space-y-1.5">
      <p className="text-xs text-muted-foreground">
        Desenhe a sua assinatura abaixo (dedo ou rato) — facultativo:
      </p>
      <canvas
        ref={ref} width={560} height={150}
        onPointerDown={start} onPointerMove={move}
        onPointerUp={end} onPointerLeave={end}
        className="w-full h-32 bg-white border-2 border-dashed border-border rounded-sm touch-none cursor-crosshair"
        data-testid="pc-signature-canvas"
      />
      {hasInk.current && (
        <Button type="button" variant="ghost" size="sm" onClick={clear}
                className="h-7 text-xs gap-1.5 rounded-sm" data-testid="pc-signature-clear-btn">
          <Eraser className="h-3 w-3" /> Apagar a assinatura
        </Button>
      )}
    </div>
  );
};
