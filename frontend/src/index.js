import React from "react";
import ReactDOM from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { HelmetProvider } from "react-helmet-async";
import "@/index.css";
import App from "@/App";

// Neutralise l'erreur bénigne "ResizeObserver loop ..." qui déclenche l'overlay
// d'erreur CRA en dev et bloque parfois les clics (aucun impact fonctionnel).
if (typeof window !== "undefined") {
  const RO_MSG = /ResizeObserver loop (limit exceeded|completed with undelivered notifications)/;
  window.addEventListener("error", (e) => {
    if (e?.message && RO_MSG.test(e.message)) {
      e.stopImmediatePropagation();
      e.preventDefault();
    }
  }, true);
}

// Force non-www (construpilot.fr) : aligne avec le canonical/sitemap ET garantit que
// les appels API restent same-origin (évite les blocages CORS www -> non-www).
if (typeof window !== "undefined" && window.location.hostname.startsWith("www.")) {
  const target = new URL(window.location.href);
  target.hostname = target.hostname.replace(/^www\./, "");
  window.location.replace(target.toString());
}

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 60_000,
      refetchOnWindowFocus: false,
    },
  },
});

const root = ReactDOM.createRoot(document.getElementById("root"));
root.render(
  <React.StrictMode>
    <HelmetProvider>
      <QueryClientProvider client={queryClient}>
        <App />
      </QueryClientProvider>
    </HelmetProvider>
  </React.StrictMode>,
);

// PWA : registo do service worker (necessário para push notifications
// + força reload quando o SW nova versão (v5+) toma controlo, para
// eliminar bundles main.*.js antigos em cache que ainda executam
// código legacy — ex. loops `/api/me?country=PT` do deploy anterior).
if ("serviceWorker" in navigator) {
  // Listener de mensagens do SW: quando o SW novo activa e envia
  // SW_UPDATED, forçamos reload (guard sessionStorage evita loop).
  navigator.serviceWorker.addEventListener("message", (ev) => {
    if (ev?.data?.type !== "SW_UPDATED") return;
    try {
      if (sessionStorage.getItem("sw_reloaded") === "1") return;
      sessionStorage.setItem("sw_reloaded", "1");
    } catch { /* storage indisponível */ }
    window.location.reload();
  });

  window.addEventListener("load", () => {
    navigator.serviceWorker.register("/sw.js").then((reg) => {
      // Força verificação de nova versão a cada load
      reg.update();
    }).catch(() => {});
    // Quando um novo SW toma o controlo (controllerchange), recarrega 1×
    let refreshed = false;
    navigator.serviceWorker.addEventListener("controllerchange", () => {
      if (refreshed) return;
      refreshed = true;
      try {
        if (sessionStorage.getItem("sw_reloaded") === "1") return;
        sessionStorage.setItem("sw_reloaded", "1");
      } catch { /* storage indisponível */ }
      window.location.reload();
    });
  });
}
