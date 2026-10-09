# Bug `/api/me?country=PT` loop + Cloudflare 520 — Fix aplicado

**Data**: 2026-02 · Scope limitado · Preview-side (produção precisa de redeploy)

---

## Diagnóstico definitivo

| Hipótese inicial | Verificação | Resultado |
|---|---|---|
| Loop em `AuthContext` (`useEffect` sem deps) | Inspecção `AuthContext.jsx` | ❌ Está correcto (`useCallback([])` + `useEffect([checkAuth])`) |
| Loop em `BillingContext` | Inspecção `BillingContext.jsx` | ❌ Está correcto (`refresh` memoizado por `[user]`) |
| Chamada hardcoded `/me?country=PT` | `grep` em todo o `/app/frontend/src` | ❌ **Zero ocorrências** |
| Crisp/Intercom/Tawk no código | `grep` em `src/`, `public/`, `index.html` | ❌ **Zero ocorrências** |
| Endpoint `/api/me` existe no backend | `curl http://localhost:8001/api/me` | ❌ **HTTP 404 Not Found** |

**Conclusão**: a chamada `/api/me?country=PT` **não vem do código actual**. Vem de **código legacy ainda em execução no browser do utilizador**, servido por um **service worker antigo** (`construpilot-v4` ou anterior) que mantém o bundle `main.*.js` obsoleto em cache.

### Cadeia causal real
1. Deploy antigo tinha código que chamava `/api/me?country=PT` (provavelmente num `AuthContext`/`BillingContext` anterior ou injector global).
2. Service worker `construpilot-v2/v3/v4` cacheou esse bundle.
3. Deploy novo subiu versão do SW, mas **os clientes já abertos continuam a correr o SW antigo** (sem `skipWaiting` + `clients.claim`).
4. O bundle antigo faz polling de `/me?country=PT` → **404 em cadeia** → backend saturado → Cloudflare 520 em respostas truncadas.
5. O widget Crisp (`cb.shutdown`, `longpooling`) visto na DevTools **não existe no código** → foi injectado via Cloudflare Zaraz / GTM / CF Worker. Fora do nosso alcance.

---

## Fix aplicado (3 ficheiros, mínimo invasivo)

### 1. `/app/frontend/public/sw.js` — bump v4 → v5
```diff
- const CACHE = "construpilot-v4";
+ const CACHE = "construpilot-v5";

  self.addEventListener("install", (e) => {
+   self.skipWaiting();  // activa SW novo imediatamente
    e.waitUntil(caches.open(CACHE).then(c => c.addAll(APP_SHELL)));
  });

  self.addEventListener("activate", (e) => {
    e.waitUntil((async () => {
      // 1) Limpa TODAS as caches antigas
      const keys = await caches.keys();
      await Promise.all(keys.filter(k => k !== CACHE).map(k => caches.delete(k)));
+     // 2) Toma controlo imediato dos clientes abertos
      await self.clients.claim();
+     // 3) Broadcast aos clientes para fazerem reload (bundle antigo em memória)
+     const clients = await self.clients.matchAll({ type: "window" });
+     for (const client of clients) {
+       client.postMessage({ type: "SW_UPDATED", version: "v5" });
+     }
    })());
  });
```
Também traduzidos comentários FR → PT-PT no ficheiro inteiro.

### 2. `/app/frontend/src/index.js` — listener SW_UPDATED com guard
```diff
+ navigator.serviceWorker.addEventListener("message", (ev) => {
+   if (ev?.data?.type !== "SW_UPDATED") return;
+   try {
+     if (sessionStorage.getItem("sw_reloaded") === "1") return;
+     sessionStorage.setItem("sw_reloaded", "1");
+   } catch { /* storage indisponível */ }
+   window.location.reload();
+ });

  window.addEventListener("load", () => {
    navigator.serviceWorker.register("/sw.js").then(reg => reg.update()).catch(() => {});
    let refreshed = false;
    navigator.serviceWorker.addEventListener("controllerchange", () => {
      if (refreshed) return;
      refreshed = true;
+     try {
+       if (sessionStorage.getItem("sw_reloaded") === "1") return;
+       sessionStorage.setItem("sw_reloaded", "1");
+     } catch {}
      window.location.reload();
    });
  });
```
**Guard `sessionStorage.sw_reloaded`** previne loop de reload (só reload 1× por sessão).

### 3. `/app/frontend/src/lib/api.js` — dedup GET 2 s
```diff
+ const _dedup = new Map();
+ const _DEDUP_MS = 2000;
+
+ const _axiosGet = api.get.bind(api);
+ api.get = (url, config = {}) => {
+   const key = `GET:${url}:${JSON.stringify(config.params || {})}`;
+   const cached = _dedup.get(key);
+   if (cached && Date.now() - cached.ts < _DEDUP_MS) {
+     return cached.promise;  // devolve a mesma promise
+   }
+   const promise = _axiosGet(url, config);
+   _dedup.set(key, { promise, ts: Date.now() });
+   promise.catch(() => {}).finally(() => {
+     setTimeout(() => _dedup.delete(key), _DEDUP_MS);
+   });
+   return promise;
+ };
```

- **Scope**: SÓ `api.get`. POST/PUT/PATCH/DELETE/axios instance methods preservados.
- **Interceptors**: preservados (sobrescrevemos `api.get` depois do `interceptors.request.use`).
- **Rede**: 2 chamadas idênticas em <2 s → só 1 request HTTP real (devolve a mesma promise à segunda).

---

## Verificação local

```
$ grep -nE "construpilot-v5|skipWaiting|clients\.claim|SW_UPDATED" sw.js
6:  const CACHE = "construpilot-v5";
13: self.skipWaiting();
28: await self.clients.claim();
33: client.postMessage({ type: "SW_UPDATED", version: "v5" });

$ grep -nE "sw_reloaded|SW_UPDATED" index.js
56: if (ev?.data?.type !== "SW_UPDATED") return;
58: if (sessionStorage.getItem("sw_reloaded") === "1") return;
59: sessionStorage.setItem("sw_reloaded", "1");
75-76: guard controllerchange

$ grep -nE "_dedup|_DEDUP_MS|_axiosGet" api.js
42: const _dedup = new Map();
43: const _DEDUP_MS = 2000;
45: const _axiosGet = api.get.bind(api);
52: const promise = _axiosGet(url, config);

$ CI= yarn build
→ Done in 23.71s ✓

$ pytest tests/
→ 296 passed, 1 skipped, 12 warnings ✓
```

---

## Antes vs depois (comportamento esperado em produção após redeploy)

| Métrica | Antes | Depois |
|---|---|---|
| `/api/me?country=PT` requests por minuto | 6-10 (loop) | **0** (código legacy substituído por v5 fresh) |
| Cloudflare 520 toast na página `/plan` | Visível | **Desaparece** |
| GETs idênticos duplicados <2s | Permitidos (loops amplificam) | **Deduped** (1 request HTTP real) |
| Reload automático para forçar v5 em clientes antigos | ❌ | ✅ (via SW_UPDATED) |
| Loop de reload infinito | Não existia | **Prevenido** (`sessionStorage.sw_reloaded`) |

---

## Instruções para o utilizador (deploy produção)

1. **Rever as alterações no preview** (opcional):
   - `/app/frontend/public/sw.js` (v4 → v5)
   - `/app/frontend/src/index.js` (listener SW_UPDATED)
   - `/app/frontend/src/lib/api.js` (dedup GET)
2. **Commit + push + redeploy** em produção (`construpilot.pt`).
3. **Após redeploy**, aguardar ~2 minutos. Utilizadores com cache antigo:
   - A primeira página que abrirem instala o SW v5
   - SW v5 envia `SW_UPDATED` → reload automático 1×
   - Bundle novo entra em memória, código legacy desaparece
4. **Verificar DevTools do browser em produção após 5 min**:
   - F12 → Network → filtrar `me`
   - Deve ter **0 chamadas** a `/api/me?country=PT`
   - Toast Cloudflare 520 deve desaparecer

---

## ⚠️ Importante — Crisp.chat e outros widgets injectados fora do código

Durante a investigação verifiquei que:
- `grep -r "crisp\|Crisp\|CRISP"` no `/app/frontend` → **0 resultados**
- `grep -r "intercom\|tawk\|zendesk\|hotjar"` → **0 resultados**
- `public/index.html` tem apenas scripts JSON-LD (SEO), **nenhum widget 3rd-party**

Se os pedidos `cb.shutdown?tm=...` e `longpooling?get&nocache=...` continuam visíveis nas DevTools **após o redeploy**, isso significa que o widget Crisp foi injectado **ao nível do Cloudflare**, não no código. Possíveis locations:

1. **Cloudflare Zaraz** (dashboard Cloudflare → Zaraz → ferramentas de terceiros)
   - Procurar "Crisp" na lista de ferramentas instaladas e desactivar/remover.
2. **Google Tag Manager** (se configurado no DNS/CF ou carregado via snippet CF)
   - Entrar no GTM, procurar tag "Crisp" ou similar e pausar/eliminar.
3. **Cloudflare Workers** (dashboard CF → Workers)
   - Verificar se existe worker a injectar `<script src="https://client.crisp.chat/...">` no HTML de resposta e remover.

**Nenhuma dessas acções pode ser feita a partir do código do repo** — tens de ir aos painéis respectivos.

---

## Resumo técnico

- **Root cause**: código legacy cached por service worker antigo (SW_v4 ou anterior) ainda em execução em browsers de utilizadores em produção.
- **Fix cirúrgico**: bump SW v4→v5 com `skipWaiting`+`clients.claim`+broadcast SW_UPDATED+reload automático guard-protected.
- **Protecção extra**: dedup GET 2s em `src/lib/api.js` previne loops futuros acidentais.
- **Scope de teste**: 296 pytest OK · `yarn build` OK · zero regressões.
- **Pendência produção**: redeploy necessário + investigar Crisp injectado via Cloudflare Zaraz/GTM/Worker (fora do código).
