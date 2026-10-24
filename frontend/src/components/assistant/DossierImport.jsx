import { useRef, useState } from "react";
import { FolderArchive, Loader2, X } from "lucide-react";
import { toast } from "sonner";
import JSZip from "jszip";
import { api } from "@/lib/api";

// Importação de um PROCESSO completo: um ZIP, uma pasta ou dezenas de ficheiros (PDF, DWG, DXF, XLSX…).
// Um ZIP é descomprimido NO NAVEGADOR (JSZip) e cada ficheiro segue num envio HTTP separado: nunca se ultrapassa
// o limite de 100 MB por pedido do Cloudflare (produção). O Assistente recebe o inventário via `dossier_ids`.
// Porta de components/assistant/DossierImport.jsx do .fr (textos PT-PT).
const ALLOWED = new Set(["pdf", "dwg", "dxf", "xls", "xlsx", "csv", "docx", "txt", "png", "jpg", "jpeg", "webp"]);
const MAX_FILE = 95 * 1024 * 1024;                     // o Cloudflare corta a 100 MB/pedido
const ext = (n) => (n.split(".").pop() || "").toLowerCase();
const isJunk = (p) => p.split("/").some((s) => s.startsWith(".") || s === "__MACOSX");
const TOO_BIG = "demasiado pesado para um envio (> 95 MB): exporte-o em vários PDF";

export function useDossierImport() {
  const [dossiers, setDossiers] = useState([]);          // [{dossier_id, name, count, total, done, busy, skipped}]
  const busy = useRef(false);

  // Descomprime um ZIP (e um nível de ZIP aninhado) no navegador → [{path, blob}] dos ficheiros autorizados.
  const expandZip = async (blob, base, skipped, depth = 0) => {
    const out = [];
    let zip;
    try {
      zip = await JSZip.loadAsync(blob);
    } catch {
      skipped.push(`${base}: arquivo ilegível`);
      return out;
    }
    const entries = Object.values(zip.files).filter((e) => !e.dir && !isJunk(e.name));
    for (const e of entries) {
      const name = e.name;
      if (ext(name) === "zip") {                         // ZIP aninhado: um só nível
        if (depth >= 1) { skipped.push(`${name}: ZIP aninhado em mais de um nível`); continue; }
        out.push(...(await expandZip(await e.async("blob"), name, skipped, depth + 1)));
        continue;
      }
      if (!ALLOWED.has(ext(name))) { skipped.push(`${name}: tipo não suportado`); continue; }
      const b = await e.async("blob");
      if (b.size === 0) continue;
      if (b.size > MAX_FILE) { skipped.push(`${name}: ${TOO_BIG}`); continue; }
      out.push({ path: name, blob: b });
    }
    return out;
  };

  const importFiles = async (fileList, name) => {
    if (busy.current) return null;
    const picked = Array.from(fileList || []).filter((f) => f.size > 0 && !f.name.startsWith("."));
    if (!picked.length) return null;
    busy.current = true;
    const skipped = [];
    const entries = [];
    for (const f of picked) {
      if (ext(f.name) === "zip") {
        if (f.size <= 140) {                             // ZIP vazio (OneDrive/Drive não sincronizado)
          toast.error("Este ZIP não contém ficheiros: verifique que estão descarregados no computador (OneDrive: «Manter sempre neste dispositivo»).");
          busy.current = false;
          return null;
        }
        entries.push(...(await expandZip(f, f.name, skipped)));
      } else if (ALLOWED.has(ext(f.name))) {
        if (f.size > MAX_FILE) { skipped.push(`${f.name}: ${TOO_BIG}`); continue; }
        entries.push({ path: f.webkitRelativePath || f.name, blob: f });
      } else {
        skipped.push(`${f.name}: tipo não suportado`);
      }
    }
    if (!entries.length) {
      toast.error(skipped[0] || "Nenhum ficheiro utilizável");
      busy.current = false;
      return null;
    }
    const label = name || guessName(picked);
    let d;
    try {
      d = (await api.post("/assistant/dossiers", { name: label })).data;
    } catch (e) {
      busy.current = false;
      const detail = e?.response?.data?.detail;
      toast.error(typeof detail === "string" ? detail : "Não foi possível criar o processo");
      return null;
    }
    const entry = { dossier_id: d.dossier_id, name: label, count: 0, total: entries.length, done: 0, busy: true, skipped: [...skipped] };
    setDossiers((x) => [...x, entry]);
    const update = (patch) => setDossiers((x) => x.map((o) => (o.dossier_id === d.dossier_id ? { ...o, ...patch(o) } : o)));
    let next = 0;
    const worker = async () => {
      while (next < entries.length) {
        const { path, blob } = entries[next++];
        const fd = new FormData();
        fd.append("file", blob, path);
        try {
          const r = (await api.post(`/assistant/dossiers/${d.dossier_id}/files`, fd)).data;
          update((o) => ({ count: o.count + r.added.length, done: o.done + 1, skipped: [...o.skipped, ...r.skipped] }));
        } catch (e) {
          const detail = e?.response?.data?.detail;
          update((o) => ({ done: o.done + 1, skipped: [...o.skipped, `${path}: ${typeof detail === "string" ? detail : "falha no envio"}`] }));
        }
      }
    };
    await Promise.all([worker(), worker(), worker()]);   // no máximo 3 envios em paralelo
    update(() => ({ busy: false }));
    busy.current = false;
    toast.success("Processo importado");
    return d.dossier_id;
  };

  const remove = (id) => setDossiers((x) => x.filter((o) => o.dossier_id !== id));
  const reset = () => setDossiers([]);
  return { dossiers, importFiles, remove, reset, uploading: dossiers.some((o) => o.busy), ids: dossiers.filter((o) => !o.busy).map((o) => o.dossier_id) };
}

function guessName(files) {
  const dir = files[0]?.webkitRelativePath?.split("/")[0];
  if (dir) return dir;
  const zip = files.find((f) => f.name.toLowerCase().endsWith(".zip"));
  if (zip) return zip.name.replace(/\.zip$/i, "");
  return `Processo (${files.length} ficheiros)`;
}

export function DossierChips({ dossiers, onRemove, disabled }) {
  if (!dossiers.length) return null;
  return dossiers.map((o) => (
    <div key={o.dossier_id} className="assistant-file-chip" data-testid={`assistant-dossier-${o.dossier_id}`}
         title={o.skipped.length ? o.skipped.slice(0, 8).join("\n") : o.name}>
      {o.busy ? <Loader2 size={13} className="animate-spin" aria-hidden="true" /> : <FolderArchive size={13} aria-hidden="true" />}
      <span>{o.name} — {o.busy ? `${o.done}/${o.total}` : `${o.count} ficheiros`}{!o.busy && o.skipped.length ? ` · ${o.skipped.length} ignorados` : ""}</span>
      <button type="button" disabled={disabled || o.busy} aria-label="Retirar o processo" onClick={() => onRemove(o.dossier_id)}
              data-testid={`assistant-remove-dossier-${o.dossier_id}`}><X size={14} /></button>
    </div>
  ));
}
