import { useEffect, useMemo, useRef, useState } from "react";
import { toast } from "sonner";
import { Camera, Trash2, Upload, ImageIcon, GitCompareArrows, CloudOff } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import { api, API } from "@/lib/api";
import { compressImage } from "@/lib/imageCompress";
import { useAuth } from "@/context/AuthContext";
import { uploadProjectPhoto } from "@/lib/offlineProjects";

const KIND_LABEL = { before: "Avant", after: "Après", progress: "Chantier" };
const KIND_STYLE = {
  before: "border-slate-500/40 text-slate-600 dark:text-slate-300",
  after: "border-emerald-500/40 text-emerald-600 dark:text-emerald-400",
  progress: "border-orange-500/40 text-orange-600 dark:text-orange-400",
};

const usePhotoBlob = (projectId, photo) => {
  const [src, setSrc] = useState(null);
  useEffect(() => {
    if (!photo) return;
    let url;
    let alive = true;
    api.get(`/projects/${projectId}/photos/${photo.photo_id}/download`, { responseType: "blob" })
      .then((res) => {
        if (!alive) return;
        url = URL.createObjectURL(res.data);
        setSrc(url);
      })
      .catch(() => setSrc(null));
    return () => { alive = false; if (url) URL.revokeObjectURL(url); };
  }, [projectId, photo?.photo_id]);
  return src;
};

const PhotoThumb = ({ projectId, photo, onDelete }) => {
  const src = usePhotoBlob(projectId, photo);
  return (
    <div className="surface overflow-hidden group relative" data-testid={`photo-${photo.photo_id}`}>
      <div className="aspect-[4/3] bg-secondary/40 grid place-items-center">
        {src ? (
          <img src={src} alt={photo.caption || photo.kind} className="w-full h-full object-cover" />
        ) : (
          <ImageIcon className="h-8 w-8 text-muted-foreground animate-pulse" />
        )}
      </div>
      <div className="p-3 flex items-start justify-between gap-2">
        <div className="min-w-0">
          <Badge variant="outline" className={`rounded-sm text-[10px] uppercase tracking-wider ${KIND_STYLE[photo.kind]}`}>
            {KIND_LABEL[photo.kind] || photo.kind}
            {photo.lot ? ` · ${photo.lot}` : ""}
          </Badge>
          {photo.caption && <p className="mt-2 text-xs text-muted-foreground line-clamp-2">{photo.caption}</p>}
        </div>
        <button
          onClick={() => onDelete(photo)}
          data-testid={`photo-delete-${photo.photo_id}`}
          className="opacity-0 group-hover:opacity-100 transition-opacity text-muted-foreground hover:text-red-500 shrink-0"
          aria-label="Supprimer"
        >
          <Trash2 className="h-4 w-4" />
        </button>
      </div>
    </div>
  );
};

const CompareSlider = ({ projectId, before, after }) => {
  const [pos, setPos] = useState(50);
  const beforeSrc = usePhotoBlob(projectId, before);
  const afterSrc = usePhotoBlob(projectId, after);
  const wrapRef = useRef(null);

  if (!before || !after) return null;

  return (
    <div className="surface overflow-hidden" data-testid="compare-slider">
      <div
        ref={wrapRef}
        className="relative aspect-[16/10] select-none cursor-col-resize bg-secondary/40"
      >
        {afterSrc && (
          <img src={afterSrc} alt="Après"
               className="absolute inset-0 w-full h-full object-cover" draggable={false} />
        )}
        {beforeSrc && (
          <div className="absolute inset-0 overflow-hidden"
               style={{ width: `${pos}%` }}>
            <img src={beforeSrc} alt="Avant" draggable={false}
                 className="absolute inset-0 h-full object-cover"
                 style={{ width: wrapRef.current?.offsetWidth || "auto", maxWidth: "none" }} />
          </div>
        )}
        <div className="absolute top-3 left-3 px-2 py-1 text-[10px] uppercase tracking-wider bg-black/60 text-white rounded-sm">
          Avant
        </div>
        <div className="absolute top-3 right-3 px-2 py-1 text-[10px] uppercase tracking-wider bg-primary text-primary-foreground rounded-sm">
          Après
        </div>
        <div
          className="absolute top-0 bottom-0 w-[3px] bg-primary shadow-[0_0_16px_rgba(255,90,0,0.6)] pointer-events-none"
          style={{ left: `calc(${pos}% - 1.5px)` }}
        />
        <div
          className="absolute top-1/2 -translate-y-1/2 h-9 w-9 rounded-full bg-primary text-primary-foreground grid place-items-center shadow-lg pointer-events-none"
          style={{ left: `calc(${pos}% - 18px)` }}
        >
          <GitCompareArrows className="h-4 w-4" />
        </div>
        <input
          type="range" min={0} max={100} value={pos}
          onChange={(e) => setPos(Number(e.target.value))}
          data-testid="compare-slider-range"
          className="absolute inset-0 w-full h-full opacity-0 cursor-col-resize"
          aria-label="Comparer avant/après"
        />
      </div>
    </div>
  );
};

export const PhotosGallery = ({ projectId, lots = [] }) => {
  const { user } = useAuth();
  const [photos, setPhotos] = useState([]);
  const [kind, setKind] = useState("before");
  const [lot, setLot] = useState("");
  const [caption, setCaption] = useState("");
  const [uploading, setUploading] = useState(false);
  const [pairLot, setPairLot] = useState("");
  const [pendingPhotos, setPendingPhotos] = useState([]);
  const inputRef = useRef(null);

  const load = async () => {
    try {
      const { data } = await api.get(`/projects/${projectId}/photos`);
      setPhotos(data.photos || []);
    } catch { /* ignore (offline) */ }
  };
  useEffect(() => { load(); }, [projectId]);
  useEffect(() => {
    const onSynced = () => { setPendingPhotos([]); load(); };
    window.addEventListener("construpilot-offline-synced", onSynced);
    return () => window.removeEventListener("construpilot-offline-synced", onSynced);
    /* eslint-disable-next-line */
  }, [projectId]);

  const upload = async (rawFile) => {
    if (!rawFile) return;
    if (rawFile.size > 25 * 1024 * 1024) {
      toast.error("Fichier trop lourd (max 25 Mo avant compression)");
      return;
    }
    setUploading(true);
    try {
      const file = await compressImage(rawFile);
      const gain = rawFile.size > file.size
        ? ` (compressée : ${Math.round((1 - file.size / rawFile.size) * 100)} %)`
        : "";
      const { queued } = await uploadProjectPhoto(user?.user_id, projectId, file, { kind, lot, caption });
      setCaption("");
      if (queued) {
        setPendingPhotos((p) => [...p, { tmp: `tmp_${Date.now()}`, url: URL.createObjectURL(file), kind, lot, caption }]);
        toast.info("Photo enregistrée hors connexion — sera envoyée au retour du réseau.");
      } else {
        toast.success(`Photo ajoutée${gain}`);
        load();
      }
    } catch {
      toast.error("Upload impossible");
    } finally {
      setUploading(false);
      if (inputRef.current) inputRef.current.value = "";
    }
  };

  const remove = async (photo) => {
    if (!confirm("Supprimer cette photo ?")) return;
    try {
      await api.delete(`/projects/${projectId}/photos/${photo.photo_id}`);
      setPhotos((p) => p.filter((x) => x.photo_id !== photo.photo_id));
    } catch { toast.error("Suppression impossible"); }
  };

  const lotOptions = useMemo(() => {
    const inPhotos = [...new Set(photos.map((p) => p.lot).filter(Boolean))];
    const inLots = lots.map((l) => l.name);
    return [...new Set([...inPhotos, ...inLots])];
  }, [photos, lots]);

  const pairLots = useMemo(() => {
    const withBoth = {};
    photos.forEach((p) => {
      const k = p.lot || "Global";
      withBoth[k] = withBoth[k] || { before: null, after: null };
      if (p.kind === "before" && !withBoth[k].before) withBoth[k].before = p;
      if (p.kind === "after" && !withBoth[k].after) withBoth[k].after = p;
    });
    return Object.entries(withBoth).filter(([, v]) => v.before && v.after);
  }, [photos]);

  useEffect(() => {
    if (!pairLot && pairLots.length) setPairLot(pairLots[0][0]);
  }, [pairLots, pairLot]);

  const active = pairLots.find(([k]) => k === pairLot)?.[1];

  return (
    <div className="grid gap-6">
      <div className="surface p-6 grid gap-4">
        <div className="flex items-center gap-2">
          <Camera className="h-4 w-4 text-primary" />
          <p className="overline">Ajouter des photos</p>
        </div>
        <div className="grid sm:grid-cols-3 gap-4">
          <div className="grid gap-2">
            <Label>Type</Label>
            <Select value={kind} onValueChange={setKind}>
              <SelectTrigger className="rounded-sm h-10" data-testid="photo-kind"><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="before">Avant</SelectItem>
                <SelectItem value="after">Après</SelectItem>
                <SelectItem value="progress">Chantier (en cours)</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <div className="grid gap-2">
            <Label>Lot (optionnel)</Label>
            <Input list="photo-lots" value={lot} onChange={(e) => setLot(e.target.value)}
                   data-testid="photo-lot" placeholder="ex : Salle de bain"
                   className="rounded-sm h-10" />
            <datalist id="photo-lots">
              {lotOptions.map((n) => <option key={n} value={n} />)}
            </datalist>
          </div>
          <div className="grid gap-2">
            <Label>Légende (optionnelle)</Label>
            <Input value={caption} onChange={(e) => setCaption(e.target.value)}
                   data-testid="photo-caption" className="rounded-sm h-10" />
          </div>
        </div>
        <div className="flex flex-wrap gap-3">
          <input ref={inputRef} type="file" accept="image/*" hidden data-testid="photo-file-input"
                 onChange={(e) => upload(e.target.files?.[0])} />
          <Button onClick={() => inputRef.current?.click()} disabled={uploading}
                  data-testid="photo-upload-btn"
                  className="rounded-sm gap-2 hover:bg-orange-600 hover:text-white">
            <Upload className="h-4 w-4" /> {uploading ? "Envoi…" : "Choisir une photo"}
          </Button>
          <p className="text-xs text-muted-foreground self-center">
            JPG, PNG, WEBP · compressé automatiquement (~150 Ko) · associez un lot pour comparer avant/après
          </p>
        </div>
      </div>

      <Tabs defaultValue="gallery">
        <TabsList className="rounded-sm">
          <TabsTrigger value="gallery" className="rounded-sm" data-testid="photos-tab-gallery">Galerie</TabsTrigger>
          <TabsTrigger value="compare" className="rounded-sm" data-testid="photos-tab-compare"
                       disabled={pairLots.length === 0}>
            Comparer avant/après {pairLots.length ? `(${pairLots.length})` : ""}
          </TabsTrigger>
        </TabsList>

        <TabsContent value="gallery" className="mt-6">
          {pendingPhotos.length > 0 && (
            <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-4 mb-4" data-testid="photos-pending-grid">
              {pendingPhotos.map((pp) => (
                <div key={pp.tmp} className="relative rounded-lg overflow-hidden border border-dashed border-amber-500/60" data-testid="photo-pending">
                  <img src={pp.url} alt="" className="w-full h-44 object-cover opacity-80" />
                  <span className="absolute top-2 left-2 inline-flex items-center gap-1 text-[11px] font-semibold px-2 py-1 rounded-full bg-amber-500 text-white">
                    <CloudOff className="h-3 w-3" /> En attente
                  </span>
                </div>
              ))}
            </div>
          )}
          {photos.length === 0 && pendingPhotos.length === 0 ? (
            <div className="surface p-10 text-center text-muted-foreground text-sm" data-testid="photos-empty">
              Aucune photo pour l'instant. Ajoutez des photos « Avant » puis « Après » pour construire un comparatif de votre chantier.
            </div>
          ) : (
            <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-4" data-testid="photos-grid">
              {photos.map((p) => (
                <PhotoThumb key={p.photo_id} projectId={projectId} photo={p} onDelete={remove} />
              ))}
            </div>
          )}
        </TabsContent>

        <TabsContent value="compare" className="mt-6 grid gap-4">
          {pairLots.length > 1 && (
            <div className="flex flex-wrap gap-2" data-testid="compare-lot-picker">
              {pairLots.map(([k]) => (
                <button
                  key={k} onClick={() => setPairLot(k)}
                  data-testid={`compare-lot-${k}`}
                  className={`px-3 py-2 text-xs rounded-sm border transition-colors ${
                    pairLot === k ? "border-primary bg-primary/15 text-primary"
                      : "border-border text-muted-foreground hover:border-primary/50"
                  }`}
                >
                  {k}
                </button>
              ))}
            </div>
          )}
          {active && (
            <CompareSlider projectId={projectId} before={active.before} after={active.after} />
          )}
        </TabsContent>
      </Tabs>
    </div>
  );
};
