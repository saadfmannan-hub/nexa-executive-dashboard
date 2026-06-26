const CACHE = "management-dashboard-v3-9-white-label";
const ASSETS = ["/", "/index.html", "/styles.css?v=3.9-white-label", "/i18n.js?v=3.8-branding", "/app.js?v=3.9-white-label", "/manifest.json", "/favicon.png", "/apple-touch-icon.png", "/icon-192.png", "/icon-512.png"];
self.addEventListener("install", event => event.waitUntil(caches.open(CACHE).then(cache => cache.addAll(ASSETS)).then(()=>self.skipWaiting())));
self.addEventListener("activate", event => event.waitUntil(caches.keys().then(keys => Promise.all(keys.filter(k=>k!==CACHE).map(k=>caches.delete(k)))).then(()=>self.clients.claim())));
self.addEventListener("fetch", event => {
  const url = new URL(event.request.url);
  if (event.request.method !== "GET" || url.pathname.startsWith("/api/")) return;
  event.respondWith(fetch(event.request).then(response => { const copy=response.clone(); caches.open(CACHE).then(c=>c.put(event.request,copy)); return response; }).catch(()=>caches.match(event.request).then(r=>r||caches.match("/"))));
});
