import { useState } from "react";
import { GitCompareArrows } from "lucide-react";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from "@/components/ui/dialog";
import { BeforeAfterSlider } from "@/components/chantiers/BeforeAfterSlider";

const FILE = process.env.REACT_APP_BACKEND_URL + "/api/site/file?path=";
const url = (p) => FILE + encodeURIComponent(p);

export function PhotoCompareDialog({ open, onOpenChange, photos = [] }) {
  const [before, setBefore] = useState(null);
  const [after, setAfter] = useState(null);

  const pick = (path) => {
    if (before === path) return setBefore(null);
    if (after === path) return setAfter(null);
    if (!before) return setBefore(path);
    if (!after) return setAfter(path);
    setAfter(path);
  };
  const roleOf = (path) => (before === path ? "Antes" : after === path ? "Após" : null);

  return (
    <Dialog open={open} onOpenChange={(v) => { onOpenChange(v); if (!v) { setBefore(null); setAfter(null); } }}>
      <DialogContent className="max-w-3xl" data-testid="photo-compare-dialog">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2"><GitCompareArrows className="h-4 w-4 text-primary" /> Comparador antes / depois</DialogTitle>
          <DialogDescription>Selecione uma fotografia «Antes» e depois uma fotografia «Depois», e arraste o cursor.</DialogDescription>
        </DialogHeader>

        {before && after ? (
          <div className="space-y-3">
            <BeforeAfterSlider before={url(before)} after={url(after)} />
            <button type="button" onClick={() => { setBefore(null); setAfter(null); }}
                    className="text-xs text-primary underline" data-testid="photo-compare-reset">
              Escolher outras fotografias
            </button>
          </div>
        ) : (
          <p className="text-sm text-muted-foreground">
            {!before ? "Clique na fotografia tirada no início da obra (Antes)." : "Clique agora na fotografia final (Depois)."}
          </p>
        )}

        <div className="grid grid-cols-3 sm:grid-cols-5 gap-2 max-h-[40vh] overflow-y-auto mt-1">
          {photos.map((p, i) => {
            const role = roleOf(p.path);
            return (
              <button key={i} type="button" onClick={() => pick(p.path)}
                      className={`relative rounded-md overflow-hidden border-2 transition ${role ? "border-primary" : "border-transparent hover:border-border"}`}
                      data-testid={`photo-compare-pick-${i}`}>
                <img src={url(p.path)} alt={p.title || "Fotografia"} loading="lazy" className="h-20 w-full object-cover" />
                {role && <span className="absolute left-1 top-1 rounded bg-primary px-1.5 py-0.5 text-[9px] font-bold text-primary-foreground">{role}</span>}
              </button>
            );
          })}
        </div>
      </DialogContent>
    </Dialog>
  );
}
