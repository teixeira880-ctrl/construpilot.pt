/* ConstruPilot Service Worker — v8 identidade-pt-fusao
   - HTML / navegação : NETWORK-FIRST (garante que a última versão é sempre servida)
   - Assets estáticos (JS/CSS/img) : cache-first (bundles hashed pelo build)
   - API : rede obrigatória, nunca cache (dados privados / permissões)
   - LOTE 2 WebSummit : pré-cache do app shell + rotas demo + ficheiros estáticos
     para funcionamento 100% offline no stand (modo avião após 1ª carga).
   IMPORTANTE : bumpar CACHE a cada deploy para purgar o cache antigo. */
const CACHE = "construpilot-v8-identidade-pt-fusao";

// App shell + manifest + ícones (sempre em pré-cache)
const APP_SHELL = [
  "/manifest.json",
  "/logo192.png",
  "/logo512.png",
  "/icons/icon-192.png",
  "/icons/icon-512.png",
  "/icons/icon-512-maskable.png",
  "/construpilot-icon.png",
  "/construpilot-logo.png",
  "/favicon.ico",
];

// Rotas da demo WebSummit pré-visitadas em install para permitir modo avião total.
// `fetch` com `redirect:"follow"` para capturar o SPA fallback (`/index.html`).
const DEMO_ROUTES = [
  "/",
  "/demo/entrar",
  "/dashboard",
  "/assistant",
  "/smart",
  "/chantiers",
  "/devis",
];

// Ficheiros estáticos da demo Moradia Martins (gerados em 2c pelos motores).
// Não falha o install se algum ainda não existir — adição best-effort.
const DEMO_ASSETS = [
  "/demo-assets/Projeto_arquitetura_Moradia_Martins_DEMO.pdf",
  "/demo-assets/Estudo_geotecnico_Moradia_Martins_DEMO.pdf",
  "/demo-assets/Dossier_BET_Moradia_Martins.pdf",
  "/demo-assets/Desenhos_BET_Moradia_Martins.zip",
  "/demo-assets/Orcamento_Moradia_Martins.xlsx",
  "/demo-assets/Nota_calculo_sismica_Moradia_Martins.pdf",
];

async function _precacheBestEffort(cache, urls) {
  await Promise.all(urls.map(async (u) => {
    try {
      const r = await fetch(u, { credentials: "same-origin" });
      if (r.ok) await cache.put(u, r.clone());
    } catch (_) { /* best-effort — ignora falhas de rede ou 404 */ }
  }));
}

self.addEventListener("install", (e) => {
  e.waitUntil((async () => {
    const cache = await caches.open(CACHE);
    // 1) App shell : addAll strict (falha instalação se faltar algo crítico)
    await cache.addAll(APP_SHELL);
    // 2) Rotas demo + assets : best-effort (não bloqueia activação do SW)
    await _precacheBestEffort(cache, DEMO_ROUTES);
    await _precacheBestEffort(cache, DEMO_ASSETS);
    await self.skipWaiting();
  })());
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

  // API : sempre rede, nunca cache (dados privados, permissões).
  // A versão do cache muda a cada deploy, o que também apaga quaisquer entradas
  // API escritas por workers mais antigos.
  if (url.pathname === "/api" || url.pathname.startsWith("/api/")) {
    e.respondWith(fetch(new Request(req, { cache: "no-store" })));
    return;
  }

  // Só gerir pedidos same-origin
  if (url.origin !== self.location.origin) return;

  // 1) Navegação / HTML : network-first, fallback cache (modo offline WebSummit)
  if (req.mode === "navigate" || (req.headers.get("accept") || "").includes("text/html")) {
    e.respondWith(
      fetch(req)
        .then((r) => {
          const clone = r.clone();
          caches.open(CACHE).then((c) => {
            // Guarda a rota exacta e também "/" para fallback geral SPA
            c.put(req, clone.clone());
            c.put("/", clone);
          });
          return r;
        })
        .catch(() => caches.match(req).then((c) => c || caches.match("/")))
    );
    return;
  }

  // 2) Assets estáticos (JS/CSS/imagens hashed) : cache-first
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
  try { data = { ...data, ...(e.data && e.data.json()) }; } catch { /* noop */ }
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
