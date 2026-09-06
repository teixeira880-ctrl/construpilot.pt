import { useState, useEffect, useRef, useCallback } from "react";
import { toast } from "sonner";
import {
  Sparkles, Upload, Image as ImageIcon, Video, Loader2, Trash2,
  Download, Wand2, Info, Share2, Copy, Check, FolderOpen, X,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Badge } from "@/components/ui/badge";
import { api } from "@/lib/api";
import { SEO } from "@/components/SEO";

const RATIOS = [
  { v: "1280:720", label: "Paisagem 16:9" },
  { v: "720:1280", label: "Portrait 9:16" },
  { v: "960:960", label: "Carré 1:1" },
];

const STYLES = [
  { key: "moderne", label: "Moderne", suffix: "style moderne, lignes épurées, matériaux contemporains, tons neutres et lumineux" },
  { key: "classique", label: "Classique", suffix: "style classique et chaleureux, matériaux traditionnels, finitions élégantes et intemporelles" },
  { key: "economique", label: "Économique", suffix: "finitions simples et économiques, matériaux standard d'entrée de gamme, budget maîtrisé" },
];

async function fetchBlobUrl(path, params) {
  const res = await api.get(path, { params, responseType: "blob" });
  return URL.createObjectURL(res.data);
}

function AuthImg({ path, params, alt, className, selected, onClick }) {
  const [url, setUrl] = useState(null);
  useEffect(() => {
    let dead = false; let created = null;
    fetchBlobUrl(path, params).then((u) => { if (!dead) { created = u; setUrl(u); } }).catch(() => {});
    return () => { dead = true; if (created) URL.revokeObjectURL(created); };
  }, [path]); // eslint-disable-line
  return (
    <button type="button" onClick={onClick}
      className={`relative rounded-md overflow-hidden border-2 transition-colors ${selected ? "border-primary" : "border-transparent hover:border-border"}`}>
      {url ? <img src={url} alt={alt} className={className} /> : <div className={`bg-muted ${className}`} />}
      {selected && <span className="absolute inset-0 bg-primary/10 grid place-items-center"><Check className="h-5 w-5 text-primary" /></span>}
    </button>
  );
}

function ResultViewer({ render }) {
  const [url, setUrl] = useState(null);
  useEffect(() => {
    let revoked = false; let created = null;
    if (render?.status === "done" && render?.has_output) {
      fetchBlobUrl(`/runway/renders/${render.render_id}/file`, { which: "output" })
        .then((u) => { if (!revoked) { created = u; setUrl(u); } }).catch(() => {});
    }
    return () => { revoked = true; if (created) URL.revokeObjectURL(created); };
  }, [render?.render_id, render?.status, render?.has_output]);
  if (!url) return null;
  return render.kind === "video" ? (
    <video src={url} controls className="w-full rounded-lg border border-border" data-testid="render-output-video" />
  ) : (
    <img src={url} alt="Render après travaux" className="w-full rounded-lg border border-border" data-testid="render-output-image" />
  );
}

function HistoryThumb({ render }) {
  const [beforeUrl, setBeforeUrl] = useState(null);
  const [afterUrl, setAfterUrl] = useState(null);
  useEffect(() => {
    let dead = false; const urls = [];
    if (render.has_input) fetchBlobUrl(`/runway/renders/${render.render_id}/file`, { which: "input" }).then((u) => { if (!dead) { urls.push(u); setBeforeUrl(u); } }).catch(() => {});
    if (render.status === "done" && render.has_output) fetchBlobUrl(`/runway/renders/${render.render_id}/file`, { which: "output" }).then((u) => { if (!dead) { urls.push(u); setAfterUrl(u); } }).catch(() => {});
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
  const [source, setSource] = useState("upload"); // upload | project
  const [file, setFile] = useState(null);
  const [preview, setPreview] = useState(null);
  const [prompt, setPrompt] = useState("");
  const [kind, setKind] = useState("image");
  const [ratio, setRatio] = useState("1280:720");
  const [duration, setDuration] = useState(5);
  const [busy, setBusy] = useState(false);
  const [current, setCurrent] = useState(null);
  const [history, setHistory] = useState([]);
  const [quota, setQuota] = useState(null);
  const [shareUrl, setShareUrl] = useState("");
  const [copied, setCopied] = useState(false);
  const [variants, setVariants] = useState([]);
  // Source projet
  const [projects, setProjects] = useState([]);
  const [selProject, setSelProject] = useState("");
  const [projPhotos, setProjPhotos] = useState([]);
  const [selPhoto, setSelPhoto] = useState(null); // {photo_id, path}
  const pollRef = useRef(null);
  const fileInput = useRef(null);

  const loadHistory = useCallback(async () => {
    try { const { data } = await api.get("/runway/renders"); setHistory(data.renders || []); } catch { /* */ }
  }, []);
  const loadQuota = useCallback(async () => {
    try { const { data } = await api.get("/runway/quota"); setQuota(data); } catch { /* */ }
  }, []);

  useEffect(() => { loadHistory(); loadQuota(); return () => clearInterval(pollRef.current); }, [loadHistory, loadQuota]);

  // Charge les projets quand on passe en mode "projet"
  useEffect(() => {
    if (source === "project" && projects.length === 0) {
      api.get("/projects").then(({ data }) => setProjects(data || [])).catch(() => {});
    }
  }, [source]); // eslint-disable-line

  const pickProject = async (pid) => {
    setSelProject(pid); setSelPhoto(null); setProjPhotos([]);
    if (!pid) return;
    try {
      const { data } = await api.get(`/projects/${pid}/photos`);
      setProjPhotos(data.photos || []);
    } catch { toast.error("Fotografias indisponíveis"); }
  };

  const onFile = (f) => {
    if (!f) return;
    if (!/image\/(jpeg|png|webp|jpg|heic|heif)/.test(f.type) && !/\.(jpe?g|png|webp|heic|heif)$/i.test(f.name)) {
      toast.error("Formats acceptés : JPEG, PNG, WEBP, HEIC"); return;
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
          clearInterval(pollRef.current); setBusy(false); loadHistory(); loadQuota();
          if (data.status === "done") toast.success("Render gerado!");
          else toast.error(data.error || "A geração falhou");
        }
      } catch { /* keep polling */ }
    }, 3000);
  };

  const canGenerate = source === "upload" ? !!file : !!selPhoto;

  const buildInputForm = () => {
    const fd = new FormData();
    if (source === "upload") fd.append("file", file);
    else { fd.append("project_id", selProject); fd.append("photo_id", selPhoto.photo_id); }
    return fd;
  };

  const pollVariants = (ids) => {
    clearInterval(pollRef.current);
    pollRef.current = setInterval(async () => {
      const updated = await Promise.all(ids.map((id) =>
        api.get(`/runway/renders/${id}`).then((r) => r.data).catch(() => null)));
      setVariants((prev) => prev.map((v, i) => (updated[i] ? { ...updated[i], style: v.style } : v)));
      if (updated.every((u) => u && u.status !== "processing")) {
        clearInterval(pollRef.current); setBusy(false); loadHistory(); loadQuota();
        toast.success("3 variantes prontas!");
      }
    }, 3000);
  };

  const generateVariants = async () => {
    if (!canGenerate) return toast.error(source === "upload" ? "Importe uma foto" : "Escolha uma foto do projeto");
    if (quota && !quota.unlimited && quota.remaining < 3) return toast.error("São necessários pelo menos 3 renders disponíveis este mês para as 3 variantes");
    setBusy(true); setCurrent(null); setShareUrl(""); setVariants([]);
    try {
      const results = [];
      for (const st of STYLES) {
        const fd = buildInputForm();
        fd.append("prompt", (prompt ? prompt.trim() + ", " : "") + st.suffix);
        fd.append("kind", "image");
        fd.append("ratio", ratio);
        const { data } = await api.post("/runway/generate", fd, { headers: { "Content-Type": "multipart/form-data" } });
        results.push({ ...data, style: st.label });
      }
      setVariants(results);
      toast.info("3 variantes en geração…");
      pollVariants(results.map((r) => r.render_id));
    } catch (e) {
      setBusy(false);
      toast.error(e?.response?.data?.detail || "Erro ao iniciar");
    }
  };

  const generate = async () => {
    if (!canGenerate) return toast.error(source === "upload" ? "Importe uma foto" : "Escolha uma foto do projeto");
    if (quota && !quota.unlimited && quota.remaining <= 0) return toast.error("Quota mensuel atteint");
    setBusy(true); setCurrent(null); setShareUrl(""); setVariants([]);
    try {
      const fd = new FormData();
      if (source === "upload") fd.append("file", file);
      else { fd.append("project_id", selProject); fd.append("photo_id", selPhoto.photo_id); }
      fd.append("prompt", prompt);
      fd.append("kind", kind);
      fd.append("ratio", ratio);
      fd.append("duration", String(duration));
      const { data } = await api.post("/runway/generate", fd, { headers: { "Content-Type": "multipart/form-data" } });
      setCurrent(data);
      toast.info(kind === "video" ? "Geração vidéo lancée (1 à 3 min)…" : "Geração en cours…");
      poll(data.render_id);
    } catch (e) {
      setBusy(false);
      toast.error(e?.response?.data?.detail || "Erro ao iniciar");
    }
  };

  const downloadCurrent = async () => {
    if (!current?.render_id) return;
    try {
      const url = await fetchBlobUrl(`/runway/renders/${current.render_id}/file`, { which: "output" });
      const a = document.createElement("a");
      a.href = url; a.download = `rendu-${current.render_id}.${current.kind === "video" ? "mp4" : "jpg"}`; a.click();
      URL.revokeObjectURL(url);
    } catch { toast.error("Descarga impossível"); }
  };

  const share = async (id) => {
    try {
      const { data } = await api.post(`/runway/renders/${id}/share`);
      setShareUrl(data.share_url);
      try { await navigator.clipboard.writeText(data.share_url); setCopied(true); setTimeout(() => setCopied(false), 2000); toast.success("Link copiado — pronto para enviar ao cliente"); }
      catch { toast.success("Lien de partage créé"); }
      loadHistory();
    } catch { toast.error("Partage impossível"); }
  };

  const copyLink = async () => {
    try { await navigator.clipboard.writeText(shareUrl); setCopied(true); setTimeout(() => setCopied(false), 2000); toast.success("Lien copiado"); } catch { /* */ }
  };

  const remove = async (id) => {
    try { await api.delete(`/runway/renders/${id}`); loadHistory(); loadQuota(); if (current?.render_id === id) setCurrent(null); }
    catch { toast.error("Suppression impossível"); }
  };

  return (
    <div className="max-w-6xl mx-auto px-4 py-8" data-testid="render-studio-page">
      <SEO title="Render IA avant/après — ConstruPilot" description="Gere uma foto ou vídeo da obra após reabilitação através da IA." />

      <div className="flex items-center gap-3 mb-2">
        <span className="h-10 w-10 grid place-items-center rounded-xl bg-primary/10"><Wand2 className="h-5 w-5 text-primary" /></span>
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Render IA — Avant / Après</h1>
          <p className="text-sm text-muted-foreground">Transformez une photo du chantier actuel en rendu « après travaux » (image ou vidéo).</p>
        </div>
        <div className="ml-auto flex items-center gap-2">
          {quota && (
            <Badge variant="secondary" data-testid="render-quota-badge">
              {quota.unlimited ? "Renders illimités" : `${quota.used}/${quota.limit} ce mois`}
            </Badge>
          )}
          <Badge variant="outline" className="hidden sm:inline-flex">Pro / Business</Badge>
        </div>
      </div>

      <div className="grid lg:grid-cols-2 gap-6 mt-6">
        {/* Colonne gauche : entrée */}
        <div className="space-y-4">
          {/* Sélecteur de source */}
          <div className="flex gap-2">
            <Button variant={source === "upload" ? "default" : "outline"} onClick={() => setSource("upload")} className="flex-1" data-testid="render-source-upload">
              <Upload className="h-4 w-4 mr-1.5" /> Importer
            </Button>
            <Button variant={source === "project" ? "default" : "outline"} onClick={() => setSource("project")} className="flex-1" data-testid="render-source-project">
              <FolderOpen className="h-4 w-4 mr-1.5" /> Desde un projet
            </Button>
          </div>

          {source === "upload" ? (
            <div
              className="border-2 border-dashed border-border rounded-xl p-4 hover:border-primary/50 transition-colors cursor-pointer bg-card"
              onClick={() => fileInput.current?.click()}
              onDragOver={(e) => e.preventDefault()}
              onDrop={(e) => { e.preventDefault(); onFile(e.dataTransfer.files?.[0]); }}
              data-testid="render-dropzone">
              <input ref={fileInput} type="file" accept="image/*" className="hidden" onChange={(e) => onFile(e.target.files?.[0])} data-testid="render-file-input" />
              {preview ? <img src={preview} alt="chantier actuel" className="w-full rounded-lg max-h-72 object-contain" /> : (
                <div className="py-12 text-center text-muted-foreground">
                  <Upload className="h-8 w-8 mx-auto mb-2" />
                  <p className="text-sm font-medium">Importe uma foto du chantier</p>
                  <p className="text-xs">JPEG, PNG, WEBP · glissez-déposez ou cliquez</p>
                </div>
              )}
            </div>
          ) : (
            <div className="rounded-xl border border-border bg-card p-4 space-y-3" data-testid="render-project-picker">
              <select value={selProject} onChange={(e) => pickProject(e.target.value)}
                      className="w-full h-10 rounded-md border border-border bg-background px-3 text-sm" data-testid="render-project-select">
                <option value="">— Escolher un projet —</option>
                {projects.map((p) => <option key={p.project_id} value={p.project_id}>{p.name || "Projeto sem nome"}</option>)}
              </select>
              {selProject && (projPhotos.length === 0 ? (
                <p className="text-xs text-muted-foreground py-4 text-center">Nenhuma photo dans ce projet. Adicione-en desde le suivi de chantier.</p>
              ) : (
                <div className="grid grid-cols-3 gap-2 max-h-72 overflow-auto" data-testid="render-project-photos">
                  {projPhotos.map((ph) => (
                    <AuthImg key={ph.photo_id}
                      path={`/projects/${selProject}/photos/${ph.photo_id}/download`}
                      alt={ph.caption || ph.kind} className="h-20 w-full object-cover"
                      selected={selPhoto?.photo_id === ph.photo_id}
                      onClick={() => setSelPhoto({ photo_id: ph.photo_id })} />
                  ))}
                </div>
              ))}
            </div>
          )}

          <div>
            <label className="text-sm font-medium">Prompt (optionnel)</label>
            <Textarea value={prompt} onChange={(e) => setPrompt(e.target.value)} maxLength={1000} rows={3}
              placeholder="Ex : cuisine moderne terminée, sol en parquet clair, paredes peints en blanc, plan de travail en quartz…"
              className="mt-1" data-testid="render-prompt-input" />
          </div>

          <div className="flex gap-2">
            <Button variant={kind === "image" ? "default" : "outline"} onClick={() => setKind("image")} className="flex-1" data-testid="render-kind-image">
              <ImageIcon className="h-4 w-4 mr-1.5" /> Photo
            </Button>
            <Button variant={kind === "video" ? "default" : "outline"} onClick={() => setKind("video")} className="flex-1" data-testid="render-kind-video">
              <Video className="h-4 w-4 mr-1.5" /> Vidéo
            </Button>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="text-sm font-medium">Format</label>
              <select value={ratio} onChange={(e) => setRatio(e.target.value)} className="mt-1 w-full h-10 rounded-md border border-border bg-background px-3 text-sm" data-testid="render-ratio-select">
                {RATIOS.map((r) => <option key={r.v} value={r.v}>{r.label}</option>)}
              </select>
            </div>
            {kind === "video" && (
              <div>
                <label className="text-sm font-medium">Durée</label>
                <select value={duration} onChange={(e) => setDuration(Number(e.target.value))} className="mt-1 w-full h-10 rounded-md border border-border bg-background px-3 text-sm" data-testid="render-duration-select">
                  <option value={5}>5 secondes</option>
                  <option value={10}>10 secondes</option>
                </select>
              </div>
            )}
          </div>

          <Button onClick={generate} disabled={busy || !canGenerate} className="w-full" size="lg" data-testid="render-generate-btn">
            {busy ? <><Loader2 className="h-4 w-4 mr-2 animate-spin" /> Geração…</> : <><Sparkles className="h-4 w-4 mr-2" /> Gerar le rendu</>}
          </Button>

          {kind === "image" && (
            <Button onClick={generateVariants} disabled={busy || !canGenerate} variant="outline" className="w-full" data-testid="render-variants-btn">
              <Sparkles className="h-4 w-4 mr-2" /> 3 variantes de style (Moderne · Classique · Éco)
            </Button>
          )}

          <p className="text-xs text-muted-foreground flex items-start gap-1.5">
            <Info className="h-3.5 w-3.5 mt-0.5 shrink-0" />
            Le rendu IA est une visualisation indicative, sans valeur contractuelle ni technique.
          </p>
        </div>

        {/* Colonne droite : résultat */}
        <div className="space-y-3">
          <div className="rounded-xl border border-border bg-card p-4 min-h-[300px]">
            <div className="text-sm font-medium mb-3">Résultat</div>
            {variants.length > 0 ? (
              <div className="grid gap-3" data-testid="render-variants">
                {variants.map((v) => (
                  <div key={v.render_id} className="rounded-lg border border-border p-2">
                    <div className="flex items-center justify-between mb-2">
                      <Badge variant="secondary" className="text-[10px]">{v.style}</Badge>
                      {v.status === "done" && (
                        <Button variant="ghost" size="icon" className="h-6 w-6" onClick={() => share(v.render_id)} data-testid={`variant-share-${v.render_id}`}>
                          <Share2 className="h-3.5 w-3.5" />
                        </Button>
                      )}
                    </div>
                    {v.status === "processing" && <div className="h-32 grid place-items-center text-xs text-muted-foreground"><Loader2 className="h-5 w-5 animate-spin" /></div>}
                    {v.status === "failed" && <div className="h-32 grid place-items-center text-xs text-destructive">Échec</div>}
                    {v.status === "done" && <ResultViewer render={v} />}
                  </div>
                ))}
              </div>
            ) : (
              <>
                {!current && <div className="h-56 grid place-items-center text-sm text-muted-foreground">Le rendu apparaîtra ici</div>}
                {current?.status === "processing" && (
                  <div className="h-56 grid place-items-center text-sm text-muted-foreground" data-testid="render-processing">
                    <div className="text-center"><Loader2 className="h-7 w-7 mx-auto mb-2 animate-spin" /> Geração {current.kind === "video" ? "vidéo" : "image"} en cours…</div>
                  </div>
                )}
                {current?.status === "failed" && <div className="h-56 grid place-items-center text-sm text-destructive" data-testid="render-failed">{current.error || "A geração falhou"}</div>}
                {current?.status === "done" && (
                  <div className="space-y-3">
                    <ResultViewer render={current} />
                    <div className="grid grid-cols-2 gap-2">
                      <Button variant="outline" onClick={downloadCurrent} data-testid="render-download-btn"><Download className="h-4 w-4 mr-2" /> Descarregar</Button>
                      <Button onClick={() => share(current.render_id)} data-testid="render-share-btn"><Share2 className="h-4 w-4 mr-2" /> Partager au client</Button>
                    </div>
                    {shareUrl && (
                      <div className="flex items-center gap-2 rounded-md border border-border bg-background p-2" data-testid="render-share-link">
                        <input readOnly value={shareUrl} className="flex-1 bg-transparent text-xs outline-none" />
                        <Button size="icon" variant="ghost" className="h-7 w-7" onClick={copyLink} data-testid="render-copy-link">
                          {copied ? <Check className="h-3.5 w-3.5 text-emerald-500" /> : <Copy className="h-3.5 w-3.5" />}
                        </Button>
                      </div>
                    )}
                  </div>
                )}
              </>
            )}
            {variants.length > 0 && shareUrl && (
              <div className="flex items-center gap-2 rounded-md border border-border bg-background p-2 mt-3" data-testid="render-share-link">
                <input readOnly value={shareUrl} className="flex-1 bg-transparent text-xs outline-none" />
                <Button size="icon" variant="ghost" className="h-7 w-7" onClick={copyLink} data-testid="render-copy-link">
                  {copied ? <Check className="h-3.5 w-3.5 text-emerald-500" /> : <Copy className="h-3.5 w-3.5" />}
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
                    {r.kind === "video" ? "Vidéo" : "Photo"} · {r.status === "done" ? "Pronto" : r.status === "failed" ? "Échec" : "Em curso"}
                  </Badge>
                  <div className="flex items-center gap-1">
                    {r.status === "done" && (
                      <Button variant="ghost" size="icon" className="h-7 w-7" onClick={() => share(r.render_id)} data-testid={`render-share-${r.render_id}`}>
                        <Share2 className="h-3.5 w-3.5" />
                      </Button>
                    )}
                    <Button variant="ghost" size="icon" className="h-7 w-7" onClick={() => remove(r.render_id)} data-testid={`render-delete-${r.render_id}`}>
                      <Trash2 className="h-3.5 w-3.5" />
                    </Button>
                  </div>
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
