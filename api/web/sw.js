// Service Worker for NBA Stables PWA
const CACHE_NAME = 'nba-stables-v1';
const SHELL_ASSETS = [
  '/web/index.html',
  '/web/app.js',
  '/web/overrides.js',
  '/web/module-header.js',
  '/web/legal.js',
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
  // Skip API calls - always fetch fresh
  if (event.request.url.includes('/api/')) {
    return;
  }

  const isShellAsset = SHELL_ASSETS.some((asset) => event.request.url.endsWith(asset));

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
      .catch(() => caches.match(event.request))
  );
});
