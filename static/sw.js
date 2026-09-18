const CACHE_NAME = 'mediahub-v1';

self.addEventListener('install', (event) => {
  self.skipWaiting();
});

self.addEventListener('activate', (event) => {
  event.waitUntil(clients.claim());
});

self.addEventListener('fetch', (event) => {
  // Let network handle dynamic conversion requests
  event.respondWith(fetch(event.request).catch(() => caches.match(event.request)));
});