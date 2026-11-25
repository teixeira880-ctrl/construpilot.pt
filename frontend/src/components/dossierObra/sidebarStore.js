import { useSyncExternalStore } from "react";

// Partilha a árvore do dossier aberto com o menu lateral global (sem pedidos duplicados à API).
let state = null;
const listeners = new Set();
export const setDossierSidebar = (next) => { state = next; listeners.forEach((l) => l()); };
export const useDossierSidebar = () => useSyncExternalStore((cb) => { listeners.add(cb); return () => listeners.delete(cb); }, () => state, () => null);
