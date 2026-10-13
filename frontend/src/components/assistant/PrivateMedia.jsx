import { useEffect, useId, useState } from "react";
import { Download, Eye, Loader2, X } from "lucide-react";
import { toast } from "sonner";
import { api } from "@/lib/api";
import { Dialog, DialogContent, DialogTitle } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { useDocumentViewer } from "./DocumentViewer";
import { useBackgroundCopy } from "./backgroundCopy";

export async function downloadAssistantFile(path, filename) {
  const { data } = await api.get(path, { responseType: "blob" });
  const url = URL.createObjectURL(data);
  const link = document.createElement("a");
  link.href = url; link.download = filename; link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

export const PrivateImage = ({ path, title, testId, small = false }) => {
  const copy = useBackgroundCopy();
  const instance = useId().replaceAll(":", "");
  const id = testId || `assistant-image-${instance}`;
  const [url, setUrl] = useState(null);
  const [error, setError] = useState(false);
  const [open, setOpen] = useState(false);
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    let active = true, objectUrl;
    setUrl(null); setError(false);
    api.get(path, { responseType: "blob" }).then(({ data }) => {
      if (active) { objectUrl = URL.createObjectURL(data); setUrl(objectUrl); }
    }).catch(() => { if (active) setError(true); });
    return () => { active = false; if (objectUrl) URL.revokeObjectURL(objectUrl); };
  }, [path, attempt]);
  return <>
    <button type="button" onClick={() => error ? setAttempt((n) => n + 1) : url && setOpen(true)} title={error ? copy("refresh") : title} aria-label={error ? copy("refresh") : `${copy("photo")} : ${title}`} data-testid={id}
      className={`relative border rounded-md overflow-hidden grid place-items-center bg-secondary/30 ${small ? "w-14 h-14 shrink-0" : "w-full max-w-xl aspect-[4/3]"}`}>
      {error ? <span className="text-xs p-2">{copy("imageError")}</span> : url ? <img src={url} alt={title} className="absolute inset-0 w-full h-full object-contain" data-testid={`${id}-img`} /> : <Loader2 className="h-4 w-4 animate-spin" />}
    </button>
    <Dialog open={open} onOpenChange={setOpen}><DialogContent data-testid={`${id}-dialog`} className="max-w-4xl max-h-[90vh]">
      <DialogTitle className="text-base break-words pr-8">{title}</DialogTitle>{url && <img src={url} alt={title} className="w-full max-h-[70vh] object-contain" data-testid={`${id}-full-image`} />}
      <div className="flex justify-end"><Button size="sm" onClick={() => setOpen(false)} data-testid={`${id}-close`}><X size={15} /> Fechar e voltar ao chat</Button></div>
    </DialogContent></Dialog>
  </>;
};

export const ArtifactCard = ({ artifact }) => {
  const copy = useBackgroundCopy();
  const view = useDocumentViewer();
  const instance = useId().replaceAll(":", "");
  const id = `assistant-file-${artifact.artifact_id}-${instance}`;
  return <div className="space-y-2 py-2" data-testid={id} data-artifact-id={artifact.artifact_id}>
    <p className="font-semibold text-sm break-words" data-testid={`${id}-title`}>{artifact.title}</p>
    {(artifact.mime === "image/jpeg" || artifact.mime === "image/png") && <PrivateImage path={artifact.download} title={artifact.title} testId={`${id}-preview`} />}
    {artifact.illustrative && <p className="text-xs text-muted-foreground" data-testid={`${id}-notice`}>{copy("illustrative")}</p>}
    <button className="inline-flex gap-2 items-center border rounded-md px-3 py-2 mr-2 hover:bg-secondary transition-colors" data-testid={`${id}-open`} onClick={() => view(artifact.download, artifact.filename, artifact.title)}><Eye size={15} />Ouvrir</button>
    <button className="inline-flex gap-2 items-center border rounded-md px-3 py-2 hover:bg-secondary transition-colors" data-testid={`${id}-download`} onClick={() => downloadAssistantFile(artifact.download, artifact.filename).catch(() => toast.error(copy("imageError")))}><Download size={15} />{copy("download")} {artifact.format.toUpperCase()}</button>
  </div>;
};