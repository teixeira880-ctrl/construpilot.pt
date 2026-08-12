/* ConstruPilot Service Worker — cache first pour l'app shell, network first pour l'API. */
const CACHE = "construpilot-v1";
const APP_SHELL = ["/", "/manifest.json", "/logo192.png", "/logo512.png"];

self.addEventListener("install", (e) => {
  e.waitUntil(caches.open(CACHE).then((c) => c.addAll(APP_SHELL)).then(() => self.skipWaiting()));
});

self.addEventListener("activate", (e) => {
  e.waitUntil(caches.keys().then((keys) =>
    Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k)))
  ).then(() => self.clients.claim()));
});

self.addEventListener("fetch", (e) => {
  const url = new URL(e.request.url);
  // API : network first, fallback cache (utile pour /api/projects, /api/plans quand offline)
  if (url.pathname.startsWith("/api/")) {
    e.respondWith(
      fetch(e.request).then((r) => {
        // Cache seulement les GET réussis
        if (e.request.method === "GET" && r.ok) {
          const clone = r.clone();
          caches.open(CACHE).then((c) => c.put(e.request, clone));
        }
        return r;
      }).catch(() => caches.match(e.request))
    );
    return;
  }
  // App shell : cache first
  if (e.request.method === "GET") {
    e.respondWith(
      caches.match(e.request).then((c) => c || fetch(e.request).then((r) => {
        if (r.ok) {
          const clone = r.clone();
          caches.open(CACHE).then((cache) => cache.put(e.request, clone));
        }
        return r;
      }).catch(() => caches.match("/")))
    );
  }
});
