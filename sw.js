// MINE:D offline support.
// Pages: from the network when it answers (so a new deploy shows up at once), from the cache when it doesn't.
// Icons and the manifest: from the cache first. Other sites (web fonts) are left alone; offline the page falls
// back to system fonts. Bump CACHE when the list below changes.
const CACHE = "mined-v1";
const PAGES = ["/", "/en/", "/ja/", "/zh/"];
const ASSETS = ["/manifest.webmanifest", "/favicon.svg", "/favicon.ico", "/icon-192.png", "/icon-512.png", "/apple-touch-icon.png"];

self.addEventListener("install", e => {
  e.waitUntil(caches.open(CACHE).then(c => c.addAll([...PAGES, ...ASSETS])).then(() => self.skipWaiting()));
});

self.addEventListener("activate", e => {
  e.waitUntil(caches.keys()
    .then(keys => Promise.all(keys.filter(k => k !== CACHE).map(k => caches.delete(k))))
    .then(() => self.clients.claim()));
});

self.addEventListener("fetch", e => {
  const req = e.request, url = new URL(req.url);
  if (req.method !== "GET" || url.origin !== location.origin) return;
  if (req.mode === "navigate") {
    e.respondWith(fetch(req).then(res => {
      if (res.ok) { const copy = res.clone(); caches.open(CACHE).then(c => c.put(url.pathname, copy)); }
      return res;
    }).catch(() => caches.match(url.pathname).then(hit => hit || caches.match("/"))));
    return;
  }
  e.respondWith(caches.match(req, { ignoreSearch: true }).then(hit => hit || fetch(req)));
});
