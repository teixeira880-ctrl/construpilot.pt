import { useRef } from "react";
import { Camera, Upload } from "lucide-react";

/**
 * Captura por câmara (mobile) com fallback para upload de ficheiro (desktop).
 * O browser abre a câmara em mobile quando o input tem o atributo
 * `capture="environment"` (câmara traseira).
 *
 * Props:
 *  - accept: default "image/*"
 *  - onFile: (file: File) => void
 *  - labelCamera, labelUpload: textos dos botões
 *  - testId: prefixo
 */
export default function CameraCapture({
  accept = "image/*",
  onFile,
  labelCamera = "Tirar foto",
  labelUpload = "Carregar ficheiro",
  testId = "camera-capture",
}) {
  const camRef = useRef(null);
  const upRef = useRef(null);
  const hasCamera =
    typeof navigator !== "undefined" &&
    (navigator.mediaDevices?.getUserMedia || /iphone|ipad|android/i.test(navigator.userAgent));

  const handle = (e) => {
    const f = e.target.files?.[0];
    if (f && onFile) onFile(f);
    e.target.value = "";
  };

  return (
    <div className="flex flex-wrap gap-2" data-testid={testId}>
      {hasCamera && (
        <>
          <input
            ref={camRef}
            type="file"
            accept={accept}
            capture="environment"
            className="sr-only"
            onChange={handle}
            data-testid={`${testId}-input-camera`}
          />
          <button
            type="button"
            onClick={() => camRef.current?.click()}
            className="inline-flex items-center gap-2 px-3 py-2 rounded-md bg-primary text-primary-foreground font-medium min-h-[44px]"
            data-testid={`${testId}-btn-camera`}
          >
            <Camera className="h-4 w-4" aria-hidden="true" /> {labelCamera}
          </button>
        </>
      )}
      <input
        ref={upRef}
        type="file"
        accept={accept}
        className="sr-only"
        onChange={handle}
        data-testid={`${testId}-input-upload`}
      />
      <button
        type="button"
        onClick={() => upRef.current?.click()}
        className="inline-flex items-center gap-2 px-3 py-2 rounded-md border border-border bg-card text-foreground font-medium min-h-[44px]"
        data-testid={`${testId}-btn-upload`}
      >
        <Upload className="h-4 w-4" aria-hidden="true" /> {labelUpload}
      </button>
    </div>
  );
}
