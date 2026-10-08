const CACHE_NAME = 'nba-stables-v4';
const SHELL_ASSETS = [
  '/',
  '/web/index.html',
  '/web/app.js',
];

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => cache.addAll(SHELL_ASSETS))
  );
  self.skipWaiting();
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((k) => k !== CACHE_NAME).map((k) => caches.delete(k)))
    ).then(() => clients.claim())
  );
});

self.addEventListener('fetch', (event) => {
  const url = new URL(event.request.url);

  if (url.origin !== self.location.origin || url.pathname.startsWith('/api/')) {
    return;
  }

  const reqPath = url.pathname;
  const isShellAsset = SHELL_ASSETS.includes(reqPath);

  event.respondWith(
    fetch(event.request)
      .then((response) => {
        if (response.ok && isShellAsset) {
          const clone = response.clone();
          caches.open(CACHE_NAME).then((cache) => cache.put(reqPath, clone));
        }
        return response;
      })
      .catch(async () => {
        const cached = await caches.match(isShellAsset ? reqPath : event.request);
        if (cached) return cached;
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
