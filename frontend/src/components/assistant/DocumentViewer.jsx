import { createContext, useContext, useEffect, useState } from "react";
import { Download, Loader2, X } from "lucide-react";
import { toast } from "sonner";
import { api } from "@/lib/api";
import { Dialog, DialogContent, DialogTitle, DialogDescription } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";

const ViewerContext = createContext(() => {});

/* In-app viewer: the chat stays underneath; « Fermer » always visible, download is a separate explicit action. */
export const DocumentViewerProvider = ({ children }) => {
  const [doc, setDoc] = useState(null);
  const [url, setUrl] = useState(null);
  const [blob, setBlob] = useState(null);
  const [error, setError] = useState(false);
  const [pages, setPages] = useState(null);
  useEffect(() => {
    if (!doc) return undefined;
    let active = true, objectUrl;
    setUrl(null); setBlob(null); setError(false); setPages(null);
    api.get(doc.path, { responseType: "blob" }).then(async ({ data }) => {
      if (!active) return;
      objectUrl = URL.createObjectURL(data); setBlob(data); setUrl(objectUrl);
      if (data.type === "application/pdf" || /\.pdf$/i.test(doc.filename || "")) {
        const fd = new FormData(); fd.append("file", data, doc.filename || "document.pdf");
        try { const r = await api.post("/assistant/pdf-pages", fd); if (active) setPages(r.data); } catch { if (active) setPages({ pages: [], total_pages: 0, failed: true }); }
      }
    }).catch(() => { if (active) setError(true); });
    return () => { active = false; if (objectUrl) URL.revokeObjectURL(objectUrl); };
  }, [doc]);
  const close = () => { setDoc(null); setUrl(null); setBlob(null); setPages(null); };
  const download = () => {
    if (!blob) return;
    const link = document.createElement("a"); link.href = url; link.download = doc.filename || "document"; link.click();
  };
  const isPdf = doc && (blob?.type === "application/pdf" || /\.pdf$/i.test(doc.filename || ""));
  return <ViewerContext.Provider value={setDoc}>
    {children}
    <Dialog open={!!doc} onOpenChange={(o) => { if (!o) close(); }}>
      <DialogContent className="max-w-5xl w-[96vw] h-[92vh] flex flex-col p-3 gap-2" data-testid="document-viewer">
        <DialogTitle className="text-sm break-words pr-8" data-testid="document-viewer-title">{doc?.title || doc?.filename}</DialogTitle>
        <DialogDescription className="sr-only">Visualizador de documentos</DialogDescription>
        <div className="flex-1 min-h-0 rounded-md border bg-muted/30 overflow-auto grid place-items-center">
          {error ? <p className="text-sm p-4" data-testid="document-viewer-error">Documento indisponível. Feche e tente novamente.</p>
            : !url || !doc || (isPdf && !pages) ? <Loader2 className="h-5 w-5 animate-spin" />
            : isPdf ? <div className="w-full grid gap-3 p-2" data-testid="document-viewer-pdf">
                {pages.pages.map((p, i) => <img key={i} src={`data:image/jpeg;base64,${p}`} alt={`Page ${i + 1}`} className="w-full bg-white shadow-sm" data-testid={`document-viewer-pdf-page-${i + 1}`} />)}
                {pages.failed && <p className="text-sm p-4">Pré-visualização indisponível: utilize «Transferir».</p>}
                {pages.total_pages > pages.pages.length && <p className="text-xs text-muted-foreground px-2">Pré-visualização das {pages.pages.length} primeiras páginas de {pages.total_pages} — o PDF completo pode ser transferido.</p>}
              </div>
            : <img src={url} alt={doc?.title || doc?.filename || "document"} className="max-w-full max-h-full object-contain" data-testid="document-viewer-image" />}
        </div>
        <div className="flex flex-wrap justify-end gap-2">
          <Button variant="outline" size="sm" disabled={!blob} onClick={download} data-testid="document-viewer-download"><Download size={15} /> Descarregar</Button>
          <Button size="sm" onClick={close} data-testid="document-viewer-close-btn"><X size={15} /> Fechar e voltar ao chat</Button>
        </div>
      </DialogContent>
    </Dialog>
  </ViewerContext.Provider>;
};

export const useDocumentViewer = () => {
  const setDoc = useContext(ViewerContext);
  return (path, filename, title) => { if (!path) return toast.error("Document indisponible"); setDoc({ path, filename, title }); };
};
