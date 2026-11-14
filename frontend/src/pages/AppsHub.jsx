import { Link } from "react-router-dom";
import { Camera } from "lucide-react";
import { APP_SUITES, suiteLabel, suiteDesc } from "@/components/workspace/suites";
import { useI18n } from "@/context/I18nContext";
import { useState } from "react";
import CameraCapture from "@/components/CameraCapture";
import BottomSheet from "@/components/mobile/BottomSheet";

// Uma app por função: as ferramentas idênticas estão fusionadas em suites.
const APPS_FOR = (lang) => APP_SUITES.map(f => ({
  to: f.to, icon: f.icon, title: suiteLabel(f, lang), desc: suiteDesc(f, lang), testId: `apps-${f.id}`,
}));

export default function AppsHub() {
  const { lang } = useI18n();
  const APPS = APPS_FOR(lang);
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
