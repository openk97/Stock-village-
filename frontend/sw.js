/**
 * sw.js — Service Worker (PWA app-shell offline).
 *
 * Strategy (tech-lead decision — robust untuk dev & build Vite):
 * - API (/api/*)         : NETWORK ONLY — tidak pernah di-cache (data live;
 *                          cache hanya di backend dengan TTL jujur).
 * - Navigasi (index.html): NETWORK FIRST, fallback ke cache shell saat offline.
 * - Aset statis (css/js/icons/manifest): CACHE FIRST + update di latar
 *   (stale-while-revalidate). Precache MINIMAL (hanya path yang pasti ada di
 *   source MAUPUN dist — nama file di dist di-hash oleh Vite, jadi tidak
 *   di-hardcode); sisanya masuk cache otomatis saat pertama dimuat.
 * - INSTALL FAIL-FAST: precache dibatasi waktu (3s) & error ditelan; SW
 *   SELALU lanjut ke activate (jangan biarkan instalasi memblokir aktivasi —
 *   offline tetap berfungsi via runtime cache walau precache parsial).
 *
 * Saat offline: shell aplikasi tetap bisa dibuka (UI + komponen), panel data
 * menampilkan status "Disconnected" + fallback yang jujur — sesuai desain app.
 */
const CACHE_NAME = 'stockvillage-shell-v1';
const SHELL_ASSETS = ['./index.html', './manifest.webmanifest', './sw.js'];

function cacheWithTimeout(cache, url, ms) {
  return Promise.race([
    cache.add(url),
    new Promise((resolve) => setTimeout(resolve, ms)),
  ]);
}

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME)
      .then((cache) => Promise.all(SHELL_ASSETS.map((a) => cacheWithTimeout(cache, a, 3000))))
      .catch(() => {})   // precache parsial tetap boleh lanjut
      .then(() => self.skipWaiting())
  );
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(
        keys.filter((k) => k !== CACHE_NAME && k.startsWith('stockvillage')).map((k) => caches.delete(k))
      ))
      .catch(() => {})
      .then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', (event) => {
  const url = new URL(event.request.url);
  const isSameOrigin = url.origin === self.location.origin;

  // 1) API: network only (data harus live)
  if (url.pathname.startsWith('/api/')) return;

  // 2) Navigasi: network-first, fallback shell (offline)
  if (event.request.mode === 'navigate') {
    event.respondWith(
      fetch(event.request)
        .then((resp) => {
          const copy = resp.clone();
          caches.open(CACHE_NAME).then((c) => c.put('./index.html', copy)).catch(() => {});
          return resp;
        })
        .catch(() => caches.match('./index.html'))
    );
    return;
  }

  // 3) Aset statis same-origin: cache-first + update latar
  if (isSameOrigin) {
    event.respondWith(
      caches.match(event.request).then((cached) => {
        const network = fetch(event.request)
          .then((resp) => {
            if (resp && resp.ok) {
              const copy = resp.clone();
              caches.open(CACHE_NAME).then((c) => c.put(event.request, copy)).catch(() => {});
            }
            return resp;
          })
          .catch(() => cached);
        return cached || network;
      })
    );
  }
});
