/* Calorie Ledger service worker: shell cache + Web Push. Bump VERSION on deploy. */
const VERSION = 'ledger-v1';
const SHELL = [
  '/', '/index.html', '/manifest.webmanifest', '/css/app.css',
  '/js/app.js', '/js/api.js', '/js/idb.js', '/js/util.js', '/js/calc.js',
  '/js/mealwindows.js', '/js/charts.js', '/js/scanner.js', '/js/store.js', '/js/sheets.js',
  '/js/tabs/today.js', '/js/tabs/scan.js', '/js/tabs/log.js',
  '/js/tabs/progress.js', '/js/tabs/settings.js',
  '/icons/icon-192.png', '/icons/icon-512.png', '/icons/apple-touch-icon.png',
];

self.addEventListener('install', (e) => {
  e.waitUntil(caches.open(VERSION).then((c) => c.addAll(SHELL)).then(() => self.skipWaiting()));
});

self.addEventListener('activate', (e) => {
  e.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(keys.filter((k) => k !== VERSION).map((k) => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', (e) => {
  const url = new URL(e.request.url);
  if (e.request.method !== 'GET' || url.pathname.startsWith('/api/')) return; // network only
  if (e.request.mode === 'navigate') {
    e.respondWith(fetch(e.request).catch(() => caches.match('/index.html')));
    return;
  }
  e.respondWith(
    caches.match(e.request).then((hit) => hit || fetch(e.request).then((res) => {
      if (res.ok && url.origin === self.location.origin) {
        const copy = res.clone();
        caches.open(VERSION).then((c) => c.put(e.request, copy));
      }
      return res;
    }))
  );
});

self.addEventListener('push', (e) => {
  let data = {};
  try { data = e.data ? e.data.json() : {}; } catch (_) { /* ignore */ }
  e.waitUntil(self.registration.showNotification(data.title || 'Calorie Ledger', {
    body: data.body || '',
    tag: data.tag || 'ledger',
    icon: '/icons/icon-192.png',
    badge: '/icons/icon-192.png',
    data: { url: data.url || '/' },
  }));
});

self.addEventListener('notificationclick', (e) => {
  e.notification.close();
  const url = (e.notification.data && e.notification.data.url) || '/';
  e.waitUntil(self.clients.matchAll({ type: 'window', includeUncontrolled: true }).then((list) => {
    for (const client of list) {
      if ('focus' in client) {
        client.focus();
        client.postMessage({ type: 'navigate', url });
        return;
      }
    }
    return self.clients.openWindow(url);
  }));
});
