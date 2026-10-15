import { Link } from "react-router-dom";
import {
  Footprints, Ruler, Receipt, FileCheck2, HardHat, Calculator, Hammer, Camera,
} from "lucide-react";
import { useState } from "react";
import CameraCapture from "@/components/CameraCapture";
import BottomSheet from "@/components/mobile/BottomSheet";

const APPS = [
  {
    to: "/escaliers",
    icon: Footprints,
    title: "Escadas",
    desc: "Calcular escada em betão armado — RGEU, Blondel.",
    testId: "apps-escadas",
  },
  {
    to: "/medicao-rapida",
    icon: Ruler,
    title: "Medição rápida",
    desc: "Áreas, perímetro e volume de uma divisão — por prompt ou à mão.",
    testId: "apps-medicao-rapida",
  },
  {
    to: "/plan",
    icon: Ruler,
    title: "Medições",
    desc: "Medir divisões, áreas e perímetros a partir de plantas.",
    testId: "apps-medicoes",
  },
  {
    to: "/devis",
    icon: Receipt,
    title: "Orçamentos",
    desc: "Preparar orçamentos profissionais com IVA PT.",
    testId: "apps-orcamentos",
  },
  {
    to: "/particulares/autorizacao-obras",
    icon: FileCheck2,
    title: "Autorização de Obras",
    desc: "Diagnóstico e dossier RJUE para a Câmara Municipal.",
    testId: "apps-autorizacao",
  },
  {
    to: "/estudo-moradia",
    icon: HardHat,
    title: "Estudo de Moradia",
    desc: "Análise estrutural, fundações e escadas.",
    testId: "apps-estudo-moradia",
  },
  {
    to: "/calculadoras",
    icon: Calculator,
    title: "Calculadoras",
    desc: "Cálculos rápidos de construção (betão, armaduras, cargas).",
    testId: "apps-calculadoras",
  },
];

export default function AppsHub() {
  const [showCam, setShowCam] = useState(false);
  const [preview, setPreview] = useState(null);
  const onFile = (f) => {
    const url = URL.createObjectURL(f);
    setPreview({ name: f.name, size: Math.round(f.size / 1024), url });
    setShowCam(false);
  };
  return (
    <div className="mx-auto max-w-5xl px-4 py-8" data-testid="apps-hub">
      <header className="mb-6 flex items-start justify-between gap-3 flex-wrap">
        <div>
          <h1 className="text-2xl sm:text-3xl font-bold text-foreground">Apps</h1>
          <p className="text-sm text-muted-foreground mt-1">
            Todas as ferramentas ConstruPilot num só sítio.
          </p>
        </div>
        <button
          type="button"
          onClick={() => setShowCam(true)}
          className="inline-flex items-center gap-2 px-3 py-2 rounded-lg bg-primary text-primary-foreground font-medium min-h-[44px] md:hidden"
          data-testid="apps-hub-quick-camera"
        >
          <Camera className="h-4 w-4" aria-hidden /> Tirar foto
        </button>
      </header>
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
        {APPS.map(({ to, icon: Icon, title, desc, testId }) => (
          <Link
            key={to}
            to={to}
            data-testid={testId}
            className="group flex items-start gap-3 rounded-xl border border-border bg-card p-4 shadow-sm hover:shadow-md hover:border-primary/30 transition-all touch-target"
          >
            <div className="h-11 w-11 rounded-lg bg-primary/10 flex items-center justify-center shrink-0">
              <Icon className="h-5 w-5 text-primary" aria-hidden="true" />
            </div>
            <div className="min-w-0">
              <h2 className="font-semibold text-foreground group-hover:text-primary transition-colors">
                {title}
              </h2>
              <p className="text-xs text-muted-foreground mt-0.5 leading-relaxed">
                {desc}
              </p>
            </div>
          </Link>
        ))}
      </div>
      <BottomSheet open={showCam} onClose={() => setShowCam(false)} title="Nova medição por foto" testId="apps-hub-cam-sheet">
        <p className="text-sm text-muted-foreground mb-3">Tire uma foto ou carregue uma imagem; vamos usá-la para medir uma divisão (brevemente).</p>
        <CameraCapture onFile={onFile} />
        {preview && (
          <div className="mt-4 flex items-center gap-3" data-testid="apps-hub-cam-preview">
            <img src={preview.url} alt={preview.name} loading="lazy" className="h-16 w-16 object-cover rounded-md border border-border" />
            <div className="min-w-0">
              <p className="text-sm font-medium truncate">{preview.name}</p>
              <p className="text-xs text-muted-foreground">{preview.size} KB</p>
            </div>
          </div>
        )}
      </BottomSheet>
    </div>
  );
}
