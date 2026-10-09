/* ConstruPilot Service Worker — v5
   - HTML / navegação : NETWORK-FIRST (garante que a última versão é sempre entregue)
   - Assets estáticos (JS/CSS/img) : cache-first (os bundles são hashed pelo build)
   - API : network-first, fallback cache
   IMPORTANTE : bumpar CACHE a cada deploy para purgar cache antigo. */
const CACHE = "construpilot-v5";
const APP_SHELL = ["/manifest.json", "/logo192.png", "/logo512.png"];

self.addEventListener("install", (e) => {
  // Força activação imediata (não espera que todos os tabs fechem).
  // Combinado com `clients.claim()` em activate + broadcast SW_UPDATED,
  // garante que clientes com bundle antigo em cache saltam para a v5.
  self.skipWaiting();
  e.waitUntil(
    caches.open(CACHE).then((c) => c.addAll(APP_SHELL))
  );
});

self.addEventListener("activate", (e) => {
  e.waitUntil(
    (async () => {
      // 1) Limpa TODAS as caches antigas (v2, v3, v4, ou qualquer outra)
      const keys = await caches.keys();
      await Promise.all(
        keys.filter((k) => k !== CACHE).map((k) => caches.delete(k))
      );
      // 2) Toma controlo imediato dos clientes abertos (tabs já carregados)
      await self.clients.claim();
      // 3) Notifica os clientes para fazerem reload (bundle main.*.js antigo
      //    em memória deve ser substituído pelo novo).
      const clients = await self.clients.matchAll({ type: "window" });
      for (const client of clients) {
        client.postMessage({ type: "SW_UPDATED", version: "v5" });
      }
    })()
  );
});

self.addEventListener("fetch", (e) => {
  const req = e.request;
  if (req.method !== "GET") return;
  const url = new URL(req.url);

  // Só gere pedidos same-origin
  if (url.origin !== self.location.origin) return;

  // 1) Navegação / HTML : network-first para servir sempre a última versão
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

  // 3) Assets estáticos (JS/CSS/imagens hashed) : cache-first
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
  let data = { title: "ConstruPilot", body: "Nova notificação", url: "/" };
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
