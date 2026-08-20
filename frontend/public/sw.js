/* ConstruPilot Service Worker
   - HTML / navigation : NETWORK-FIRST (garantit que la dernière version s'affiche toujours)
   - Assets statiques (JS/CSS/img) : cache-first (les bundles sont hashés par le build)
   - API : network-first, fallback cache
   IMPORTANT : bumper CACHE à chaque déploiement pour purger l'ancien cache. */
const CACHE = "construpilot-v4";
const APP_SHELL = ["/manifest.json", "/logo192.png", "/logo512.png"];

self.addEventListener("install", (e) => {
  e.waitUntil(
    caches.open(CACHE).then((c) => c.addAll(APP_SHELL)).then(() => self.skipWaiting())
  );
});

self.addEventListener("activate", (e) => {
  e.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k)))
    ).then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", (e) => {
  const req = e.request;
  if (req.method !== "GET") return;
  const url = new URL(req.url);

  // Ne gérer que les requêtes same-origin
  if (url.origin !== self.location.origin) return;

  // 1) Navigation / HTML : network-first pour toujours servir la dernière version
  if (req.mode === "navigate" || (req.headers.get("accept") || "").includes("text/html")) {
    e.respondWith(
      fetch(req)
        .then((r) => {
          const clone = r.clone();
          caches.open(CACHE).then((c) => c.put("/", clone));
          return r;
        })
        .catch(() => caches.match(req).then((c) => c || caches.match("/")))
    );
    return;
  }

  // 2) API : network-first, fallback cache
  if (url.pathname.startsWith("/api/")) {
    e.respondWith(
      fetch(req)
        .then((r) => {
          if (r.ok) {
            const clone = r.clone();
            caches.open(CACHE).then((c) => c.put(req, clone));
          }
          return r;
        })
        .catch(() => caches.match(req))
    );
    return;
  }

  // 3) Assets statiques (JS/CSS/images hashés) : cache-first
  e.respondWith(
    caches.match(req).then((c) =>
      c ||
      fetch(req).then((r) => {
        if (r.ok) {
          const clone = r.clone();
          caches.open(CACHE).then((cache) => cache.put(req, clone));
        }
        return r;
      })
    )
  );
});

// PUSH notifications
self.addEventListener("push", (e) => {
  let data = { title: "ConstruPilot", body: "Nouvelle notification", url: "/" };
  try { data = { ...data, ...(e.data && e.data.json()) }; } catch {}
  e.waitUntil(self.registration.showNotification(data.title, {
    body: data.body, icon: data.icon || "/logo192.png",
    badge: "/logo192.png", data: { url: data.url }, tag: "construpilot",
  }));
});

self.addEventListener("notificationclick", (e) => {
  e.notification.close();
  const url = (e.notification.data && e.notification.data.url) || "/";
  e.waitUntil(self.clients.matchAll({ type: "window" }).then((list) => {
    for (const c of list) { if (c.url.includes(url) && "focus" in c) return c.focus(); }
    return self.clients.openWindow(url);
  }));
});
