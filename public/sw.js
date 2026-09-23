// Offline support for the installed app (iPhone: Share > Add to Home Screen).
//
// Data files (texts, audio, dict, cover) are requested as <path>?v=<hash>, the
// hash from files.json, which publish.py rewrites on every publish. A given URL
// therefore never changes content, so it is served from the cache once it has
// been fetched; a republished chapter or re-recorded mp3 gets a new hash, hence
// a new URL, hence a fresh download. Everything else (the page, files.json) is
// network first, falling back to the cache when offline, so an update shows up
// the next time she opens the app with a connection.
//
// A signed-in student's cache is her own browser's, as it was when the files
// were sealed: the gate (worker/index.js) is what keeps them off the open web,
// and it marks every one private so no shared cache can hold one.
const DATA = 'souls-data', SHELL = 'souls-shell';

self.addEventListener('install', () => self.skipWaiting());
self.addEventListener('activate', e => e.waitUntil(self.clients.claim()));

self.addEventListener('fetch', e => {
  const u = new URL(e.request.url);
  if (e.request.method !== 'GET' || u.origin !== location.origin) return;
  e.respondWith(u.searchParams.has('v')
    ? cacheFirst(e.request) : networkFirst(e.request));
});

async function cacheFirst(req) {
  const c = await caches.open(DATA);
  const hit = await c.match(req);
  if (hit) return hit;
  const r = await fetch(req);
  if (r.ok) await c.put(req, r.clone());
  return r;
}

async function networkFirst(req) {
  const c = await caches.open(SHELL);
  try {
    const r = await fetch(req, {cache: 'no-cache'});   // revalidate: no stale page from the HTTP cache
    if (r.ok) await c.put(req.url, r.clone());
    return r;
  } catch (e) {
    const hit = await c.match(req.url, {ignoreSearch: true});
    if (hit) return hit;
    throw e;
  }
}

// The page sends the current file list after each start; drop superseded files.
self.addEventListener('message', e => {
  if (!e.data || !e.data.keep) return;
  e.waitUntil((async () => {
    const keep = new Set(e.data.keep.map(p => new URL(p, self.registration.scope).href));
    const c = await caches.open(DATA);
    for (const k of await c.keys()) if (!keep.has(k.url)) await c.delete(k);
  })());
});
