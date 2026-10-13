import React from "react";
import ReactDOM from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { SeoProvider } from "@/components/SEO";
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

// Premier contact (attribution des inscriptions : page d'entrée, referrer, UTM) — conservé jusqu'à l'inscription
try {
  if (!localStorage.getItem("cp_first_touch")) {
    const q = new URLSearchParams(window.location.search);
    localStorage.setItem("cp_first_touch", JSON.stringify({ landing_path: window.location.pathname, referrer: document.referrer || "", utm_source: q.get("utm_source") || "", utm_medium: q.get("utm_medium") || "", utm_campaign: q.get("utm_campaign") || "", qr: q.get("qr") || q.get("lot") || "", ref: q.get("ref") || "", first_seen: new Date().toISOString() }));
  }
} catch { /* noop */ }
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
    <SeoProvider>
      <QueryClientProvider client={queryClient}>
        <App />
      </QueryClientProvider>
    </SeoProvider>
  </React.StrictMode>,
);

// PWA : enregistrement du service worker (requis pour les push notifications)
if ("serviceWorker" in navigator) {
  window.addEventListener("load", () => {
    navigator.serviceWorker.register("/sw.js").then((reg) => {
      // Force la vérification d'une nouvelle version à chaque chargement
      reg.update();
    }).catch(() => {});
    // Quand un nouveau SW prend le contrôle, recharge une fois pour afficher la dernière version
    let refreshed = false;
    navigator.serviceWorker.addEventListener("controllerchange", () => {
      if (refreshed) return;
      refreshed = true;
      window.location.reload();
    });
  });
}
