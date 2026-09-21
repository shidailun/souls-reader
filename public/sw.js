// Offline support for the installed app (iPhone: Share > Add to Home Screen).
//
// Sealed data files are requested as data/<path>.bin?v=<hash>, the hash from
// data/index.json, which publish.py rewrites on every publish. A given URL
// therefore never changes content, so it is served from the cache once it has
// been fetched; a republished chapter or re-recorded mp3 gets a new hash, hence
// a new URL, hence a fresh download. Everything else (the page, sealed.json,
// the index) is network first, falling back to the cache when offline, so an
// update shows up the next time she opens the app with a connection.
//
// The cache holds only what the server already serves: ciphertext. Nothing
// here can read it without the password.
const DATA = 'souls-data', SHELL = 'souls-shell';

self.addEventListener('install', () => self.skipWaiting());
self.addEventListener('activate', e => e.waitUntil(self.clients.claim()));

self.addEventListener('fetch', e => {
  const u = new URL(e.request.url);
  if (e.request.method !== 'GET' || u.origin !== location.origin) return;
  e.respondWith(u.pathname.includes('/data/') && u.searchParams.has('v')
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
    const r = await fetch(req);
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
