// Service Worker for NBA Stables PWA
const CACHE_NAME = 'nba-stables-v2';
const SHELL_ASSETS = [
  '/',
  '/web/index.html',
  '/web/app.js',
  '/web/module-header.js',
  '/web/legal.js',
  '/web/widget.html',
  '/web/widget.js',
];

// Install - cache shell assets for offline fallback
self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => cache.addAll(SHELL_ASSETS))
  );
  self.skipWaiting();
});

// Activate - clean old caches
self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((k) => k !== CACHE_NAME).map((k) => caches.delete(k)))
    ).then(() => clients.claim())
  );
});

// Fetch - network first, cache fallback for shell assets only
self.addEventListener('fetch', (event) => {
  const url = new URL(event.request.url);

  // Leave cross-origin requests (Google Fonts) to the browser. Re-issuing them
  // from the worker counts as connect-src, which PAGE_CSP denies; loaded
  // directly they are allowed by style-src/font-src.
  // API calls are skipped too - always fetch fresh.
  if (url.origin !== self.location.origin || url.pathname.startsWith('/api/')) {
    return;
  }

  const reqPath = url.pathname;
  const isShellAsset = SHELL_ASSETS.includes(reqPath);

  event.respondWith(
    fetch(event.request)
      .then((response) => {
        // Only cache shell assets, not arbitrary GETs
        if (response.ok && isShellAsset) {
          const clone = response.clone();
          caches.open(CACHE_NAME).then((cache) => cache.put(event.request, clone));
        }
        return response;
      })
      .catch(async () => {
        const cached = await caches.match(event.request);
        if (cached) return cached;
        // Offline navigation to a non-cached URL falls back to the app shell.
        if (event.request.mode === 'navigate') {
          return (
            (await caches.match('/')) ||
            (await caches.match('/web/index.html')) ||
            Response.error()
          );
        }
        return Response.error();
      })
  );
});
