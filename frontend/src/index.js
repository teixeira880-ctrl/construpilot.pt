import React from "react";
import ReactDOM from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { HelmetProvider } from "react-helmet-async";
import "@/index.css";
import App from "@/App";

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
