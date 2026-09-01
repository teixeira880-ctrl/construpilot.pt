import { useState, useEffect, useRef, useCallback } from "react";
import { toast } from "sonner";
import {
  Sparkles, Upload, Image as ImageIcon, Video, Loader2, Trash2,
  Download, Wand2, Info,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Badge } from "@/components/ui/badge";
import { api } from "@/lib/api";
import { SEO } from "@/components/SEO";

const RATIOS = [
  { v: "1280:720", label: "Paysage 16:9" },
  { v: "720:1280", label: "Portrait 9:16" },
  { v: "960:960", label: "Carré 1:1" },
];

async function fetchBlobUrl(renderId, which) {
  const res = await api.get(`/runway/renders/${renderId}/file`, {
    params: { which },
    responseType: "blob",
  });
  return URL.createObjectURL(res.data);
}

function ResultViewer({ render }) {
  const [url, setUrl] = useState(null);
  useEffect(() => {
    let revoked = false;
    let created = null;
    if (render?.status === "done" && render?.has_output) {
      fetchBlobUrl(render.render_id, "output")
        .then((u) => { if (!revoked) { created = u; setUrl(u); } })
        .catch(() => {});
    }
    return () => { revoked = true; if (created) URL.revokeObjectURL(created); };
  }, [render?.render_id, render?.status, render?.has_output]);

  if (!url) return null;
  return render.kind === "video" ? (
    <video src={url} controls className="w-full rounded-lg border border-border" data-testid="render-output-video" />
  ) : (
    <img src={url} alt="Rendu après travaux" className="w-full rounded-lg border border-border" data-testid="render-output-image" />
  );
}

function HistoryThumb({ render }) {
  const [beforeUrl, setBeforeUrl] = useState(null);
  const [afterUrl, setAfterUrl] = useState(null);
  useEffect(() => {
    let dead = false; const urls = [];
    if (render.has_input) fetchBlobUrl(render.render_id, "input").then((u) => { if (!dead) { urls.push(u); setBeforeUrl(u); } }).catch(() => {});
    if (render.status === "done" && render.has_output) fetchBlobUrl(render.render_id, "output").then((u) => { if (!dead) { urls.push(u); setAfterUrl(u); } }).catch(() => {});
    return () => { dead = true; urls.forEach((u) => URL.revokeObjectURL(u)); };
  }, [render.render_id, render.status]);
  return (
    <div className="grid grid-cols-2 gap-1">
      <div className="relative">
        {beforeUrl ? <img src={beforeUrl} alt="avant" className="h-24 w-full object-cover rounded-md" /> : <div className="h-24 w-full rounded-md bg-muted" />}
        <span className="absolute top-1 left-1 text-[10px] px-1.5 py-0.5 rounded bg-black/60 text-white">Avant</span>
      </div>
      <div className="relative">
        {render.status === "done" && afterUrl ? (
          render.kind === "video"
            ? <video src={afterUrl} className="h-24 w-full object-cover rounded-md" muted />
            : <img src={afterUrl} alt="après" className="h-24 w-full object-cover rounded-md" />
        ) : (
          <div className="h-24 w-full rounded-md bg-muted grid place-items-center text-xs text-muted-foreground">
            {render.status === "processing" ? <Loader2 className="h-4 w-4 animate-spin" /> : render.status === "failed" ? "Échec" : "—"}
          </div>
        )}
        <span className="absolute top-1 left-1 text-[10px] px-1.5 py-0.5 rounded bg-primary/80 text-primary-foreground">Après</span>
      </div>
    </div>
  );
}

export default function RenderStudio() {
  const [file, setFile] = useState(null);
  const [preview, setPreview] = useState(null);
  const [prompt, setPrompt] = useState("");
  const [kind, setKind] = useState("image");
  const [ratio, setRatio] = useState("1280:720");
  const [duration, setDuration] = useState(5);
  const [busy, setBusy] = useState(false);
  const [current, setCurrent] = useState(null);
  const [history, setHistory] = useState([]);
  const pollRef = useRef(null);
  const fileInput = useRef(null);

  const loadHistory = useCallback(async () => {
    try {
      const { data } = await api.get("/runway/renders");
      setHistory(data.renders || []);
    } catch { /* ignore */ }
  }, []);

  useEffect(() => { loadHistory(); return () => clearInterval(pollRef.current); }, [loadHistory]);

  const onFile = (f) => {
    if (!f) return;
    if (!/image\/(jpeg|png|webp|jpg|heic|heif)/.test(f.type) && !/\.(jpe?g|png|webp|heic|heif)$/i.test(f.name)) {
      toast.error("Formats acceptés : JPEG, PNG, WEBP, HEIC");
      return;
    }
    setFile(f);
    const reader = new FileReader();
    reader.onload = () => setPreview(reader.result);
    reader.readAsDataURL(f);
  };

  const poll = (renderId) => {
    clearInterval(pollRef.current);
    pollRef.current = setInterval(async () => {
      try {
        const { data } = await api.get(`/runway/renders/${renderId}`);
        setCurrent(data);
        if (data.status !== "processing") {
          clearInterval(pollRef.current);
          setBusy(false);
          loadHistory();
          if (data.status === "done") toast.success("Rendu généré !");
          else toast.error(data.error || "La génération a échoué");
        }
      } catch { /* keep polling */ }
    }, 3000);
  };

  const generate = async () => {
    if (!file) return toast.error("Importez une photo du chantier");
    setBusy(true);
    setCurrent(null);
    try {
      const fd = new FormData();
      fd.append("file", file);
      fd.append("prompt", prompt);
      fd.append("kind", kind);
      fd.append("ratio", ratio);
      fd.append("duration", String(duration));
      const { data } = await api.post("/runway/generate", fd, { headers: { "Content-Type": "multipart/form-data" } });
      setCurrent(data);
      toast.info(kind === "video" ? "Génération vidéo lancée (1 à 3 min)…" : "Génération en cours…");
      poll(data.render_id);
    } catch (e) {
      setBusy(false);
      toast.error(e?.response?.data?.detail || "Erreur lors du lancement");
    }
  };

  const downloadCurrent = async () => {
    if (!current?.render_id) return;
    try {
      const url = await fetchBlobUrl(current.render_id, "output");
      const a = document.createElement("a");
      a.href = url;
      a.download = `rendu-${current.render_id}.${current.kind === "video" ? "mp4" : "jpg"}`;
      a.click();
      URL.revokeObjectURL(url);
    } catch { toast.error("Téléchargement impossible"); }
  };

  const remove = async (id) => {
    try { await api.delete(`/runway/renders/${id}`); loadHistory(); if (current?.render_id === id) setCurrent(null); }
    catch { toast.error("Suppression impossible"); }
  };

  return (
    <div className="max-w-6xl mx-auto px-4 py-8" data-testid="render-studio-page">
      <SEO title="Rendu IA avant/après — ConstruPilot" description="Générez une photo ou vidéo du chantier après rénovation grâce à l'IA." />

      <div className="flex items-center gap-3 mb-2">
        <span className="h-10 w-10 grid place-items-center rounded-xl bg-primary/10">
          <Wand2 className="h-5 w-5 text-primary" />
        </span>
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Rendu IA — Avant / Après</h1>
          <p className="text-sm text-muted-foreground">Transformez une photo du chantier actuel en rendu « après travaux » (image ou vidéo).</p>
        </div>
        <Badge variant="secondary" className="ml-auto hidden sm:inline-flex">Pro / Business</Badge>
      </div>

      <div className="grid lg:grid-cols-2 gap-6 mt-6">
        {/* Colonne gauche : entrée */}
        <div className="space-y-4">
          <div
            className="border-2 border-dashed border-border rounded-xl p-4 hover:border-primary/50 transition-colors cursor-pointer bg-card"
            onClick={() => fileInput.current?.click()}
            onDragOver={(e) => e.preventDefault()}
            onDrop={(e) => { e.preventDefault(); onFile(e.dataTransfer.files?.[0]); }}
            data-testid="render-dropzone"
          >
            <input ref={fileInput} type="file" accept="image/*" className="hidden"
                   onChange={(e) => onFile(e.target.files?.[0])} data-testid="render-file-input" />
            {preview ? (
              <img src={preview} alt="chantier actuel" className="w-full rounded-lg max-h-72 object-contain" />
            ) : (
              <div className="py-12 text-center text-muted-foreground">
                <Upload className="h-8 w-8 mx-auto mb-2" />
                <p className="text-sm font-medium">Importez une photo du chantier</p>
                <p className="text-xs">JPEG, PNG, WEBP · glissez-déposez ou cliquez</p>
              </div>
            )}
          </div>

          <div>
            <label className="text-sm font-medium">Prompt (optionnel)</label>
            <Textarea
              value={prompt}
              onChange={(e) => setPrompt(e.target.value)}
              maxLength={1000}
              rows={3}
              placeholder="Ex : cuisine moderne terminée, sol en parquet clair, murs peints en blanc, plan de travail en quartz…"
              className="mt-1"
              data-testid="render-prompt-input"
            />
          </div>

          <div className="flex gap-2">
            <Button
              variant={kind === "image" ? "default" : "outline"}
              onClick={() => setKind("image")}
              className="flex-1"
              data-testid="render-kind-image"
            >
              <ImageIcon className="h-4 w-4 mr-1.5" /> Photo
            </Button>
            <Button
              variant={kind === "video" ? "default" : "outline"}
              onClick={() => setKind("video")}
              className="flex-1"
              data-testid="render-kind-video"
            >
              <Video className="h-4 w-4 mr-1.5" /> Vidéo
            </Button>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="text-sm font-medium">Format</label>
              <select value={ratio} onChange={(e) => setRatio(e.target.value)}
                      className="mt-1 w-full h-10 rounded-md border border-border bg-background px-3 text-sm"
                      data-testid="render-ratio-select">
                {RATIOS.map((r) => <option key={r.v} value={r.v}>{r.label}</option>)}
              </select>
            </div>
            {kind === "video" && (
              <div>
                <label className="text-sm font-medium">Durée</label>
                <select value={duration} onChange={(e) => setDuration(Number(e.target.value))}
                        className="mt-1 w-full h-10 rounded-md border border-border bg-background px-3 text-sm"
                        data-testid="render-duration-select">
                  <option value={5}>5 secondes</option>
                  <option value={10}>10 secondes</option>
                </select>
              </div>
            )}
          </div>

          <Button onClick={generate} disabled={busy || !file} className="w-full" size="lg" data-testid="render-generate-btn">
            {busy ? <><Loader2 className="h-4 w-4 mr-2 animate-spin" /> Génération…</> : <><Sparkles className="h-4 w-4 mr-2" /> Générer le rendu</>}
          </Button>

          <p className="text-xs text-muted-foreground flex items-start gap-1.5">
            <Info className="h-3.5 w-3.5 mt-0.5 shrink-0" />
            Le rendu IA est une visualisation indicative, sans valeur contractuelle ni technique.
          </p>
        </div>

        {/* Colonne droite : résultat */}
        <div className="space-y-3">
          <div className="rounded-xl border border-border bg-card p-4 min-h-[300px]">
            <div className="text-sm font-medium mb-3">Résultat</div>
            {!current && <div className="h-56 grid place-items-center text-sm text-muted-foreground">Le rendu apparaîtra ici</div>}
            {current?.status === "processing" && (
              <div className="h-56 grid place-items-center text-sm text-muted-foreground" data-testid="render-processing">
                <div className="text-center">
                  <Loader2 className="h-7 w-7 mx-auto mb-2 animate-spin" />
                  Génération {current.kind === "video" ? "vidéo" : "image"} en cours…
                </div>
              </div>
            )}
            {current?.status === "failed" && (
              <div className="h-56 grid place-items-center text-sm text-destructive" data-testid="render-failed">
                {current.error || "La génération a échoué"}
              </div>
            )}
            {current?.status === "done" && (
              <div className="space-y-3">
                <ResultViewer render={current} />
                <Button variant="outline" onClick={downloadCurrent} className="w-full" data-testid="render-download-btn">
                  <Download className="h-4 w-4 mr-2" /> Télécharger
                </Button>
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Historique */}
      {history.length > 0 && (
        <div className="mt-10">
          <h2 className="text-lg font-semibold mb-3">Historique</h2>
          <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-4" data-testid="render-history">
            {history.map((r) => (
              <div key={r.render_id} className="rounded-xl border border-border bg-card p-3 space-y-2">
                <HistoryThumb render={r} />
                <div className="flex items-center justify-between">
                  <Badge variant={r.status === "done" ? "default" : r.status === "failed" ? "destructive" : "secondary"} className="text-[10px]">
                    {r.kind === "video" ? "Vidéo" : "Photo"} · {r.status === "done" ? "Prêt" : r.status === "failed" ? "Échec" : "En cours"}
                  </Badge>
                  <Button variant="ghost" size="icon" className="h-7 w-7" onClick={() => remove(r.render_id)} data-testid={`render-delete-${r.render_id}`}>
                    <Trash2 className="h-3.5 w-3.5" />
                  </Button>
                </div>
                {r.prompt && <p className="text-xs text-muted-foreground line-clamp-2">{r.prompt}</p>}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
