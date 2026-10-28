import { lazy } from "react";

const RELOAD_KEY = "cp_chunk_reload_at";

// React.lazy com recuperação de "ChunkLoadError": depois de um novo deploy, os
// ficheiros JS antigos deixam de existir no servidor. Um separador aberto antes
// do deploy falharia ao abrir uma página nova — recarregamos uma única vez
// (no máximo a cada 30 s) para obter a versão atual.
export function lazyPage(factory) {
  return lazy(() =>
    factory().catch((err) => {
      const chunkError = err?.name === "ChunkLoadError" || /Loading (CSS )?chunk/i.test(err?.message || "");
      if (chunkError && typeof window !== "undefined" && navigator.onLine !== false) {
        let last = 0;
        try { last = Number(sessionStorage.getItem(RELOAD_KEY) || 0); } catch { /* noop */ }
        if (Date.now() - last > 30_000) {
          try { sessionStorage.setItem(RELOAD_KEY, String(Date.now())); } catch { /* noop */ }
          window.location.reload();
          return new Promise(() => {});
        }
      }
      throw err;
    })
  );
}
