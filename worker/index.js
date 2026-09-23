// The reader gate: Lingnan student number + Lingnan email, checked against D1.
//
// Written once here, in _tools/reader-gate/gate.js, and copied unchanged into
// each reader as worker/index.js. Edit it here and copy it out again; a copy
// edited in place drifts, and the next reader to be cloned inherits the drift.
//
// WHY A GATE AT ALL. The readers publish other people's work - a channel's audio,
// an author's recording, a book in translation - for one class. Until now each
// one was either wide open or sealed with a shared password baked into the page.
// A shared password leaks the day one student posts it, and it has to be handed
// out, remembered and re-typed on every phone. He said what he wanted instead:
// "just student num and email". Two things nobody in 503 or 506 can mislay, and
// the university's own identity rather than one these apps invented.
//
// WHO GETS IN. Anyone with a present row on the 503 or 506 roll, and him. He is
// on no roll - a prof is not a student - but he reads these apps as a student
// too, so his number is on STAFF. Same email check as everybody else: being on
// STAFF is not a way in without one.
//
// THE PAIR IS A WEAK CREDENTIAL AND IS MEANT TO BE, exactly as in parallel-texts
// (whoIsSid, which this check copies). Anyone who knows both could read as that
// student; what they get is a reading app. The point is that the texts are not
// on the open web, not that a classmate cannot borrow a login.
//
// ONE SIGN-IN FOR ALL THE READERS. He asked for it in those words: "they
// should have to sign in exactly once". Every reader is a <name>.shidailun.com,
// so the cookie is set on Domain=shidailun.com rather than on the one reader's
// host, and whichever reader a student signs in to, she is signed in to all of
// them - and for a year. Each Worker still checks D1 itself; there is no login
// server and no shared secret, only a cookie the other readers can also see.
// His other apps on the domain (503, the register, shilaoshi) are sent it too
// and have no idea what it is, which costs a header and nothing else.
//
// THE COOKIE IS THE PAIR ITSELF: rg=<sid>~<base64url(email)>, HttpOnly, a year
// long, and re-checked against D1 on every request (the verdict cached ten
// minutes per isolate). So a student who drops the course is out within ten
// minutes of the roll saying so, with nothing to revoke. Rejected:
//   - a signed token (sid + HMAC), as parallel-texts does. It needs a signing
//     secret on every reader Worker, and a secret has to be made, stored and
//     kept off this laptop's screen - for a credential no stronger than the
//     pair it would stand in for.
//   - keeping the AES seal and handing out the key after sign-in. The server
//     would then have to hold the key, which is the password again with extra
//     steps, and the page would still carry the unseal code. With the gate in
//     front, ciphertext protects nothing the gate does not.
// No new secret of any kind: the only binding is D1, and the only statements
// below are SELECTs. (D1 has no read-only binding; that is a promise of this
// file, not of the platform.)
//
// WHAT IS OPEN. The shell, so the installed app can draw its sign-in screen and
// register its service worker with no cookie: /, index.html, sw.js, the
// manifest, icons/ and robots.txt. Everything else - texts, audio, dictionary,
// covers, files.json - needs the cookie.
//
// FAIL CLOSED. If D1 cannot be reached or the lookup throws, the answer is no
// (503), never "let them through this once". A signed-in student who is offline
// still reads, because the service worker answers from its cache before this
// Worker is ever asked.
//
// KILL SWITCH. OPEN = false makes every data path and the sign-in answer 403
// "closed": one line and a deploy shuts an app, and one more opens it again.
const OPEN = true;

const COURSES = ["503", "506"];
const STAFF = ["029962"];
const SID_RE = /^[0-9A-Za-z]{4,16}$/;
const COOKIE = "rg";
const DOMAIN = "shidailun.com";        // every reader is a subdomain of it
const YEAR = 365 * 24 * 3600;

// No cookie needed. Exact paths, plus the icons folder.
const SHELL = new Set(["/", "/index.html", "/sw.js", "/manifest.webmanifest", "/robots.txt"]);
const isShell = (p) => SHELL.has(p) || p.startsWith("/icons/");

// Per-isolate memory, as in parallel-texts: good enough to stop a script
// guessing at sign-in, and costs no storage.
const RATE_WINDOW_MS = 60_000;
const SIGNIN_PER_MIN = 10;
const hits = new Map();
function rateLimited(ip) {
  const now = Date.now();
  const arr = (hits.get(ip) || []).filter((t) => now - t < RATE_WINDOW_MS);
  arr.push(now);
  hits.set(ip, arr);
  if (hits.size > 5000) hits.clear();
  return arr.length > SIGNIN_PER_MIN;
}

const VERDICT_TTL_MS = 600_000;
const verdicts = new Map(); // cookie value -> { at, who }  (who null = refused)

const clean = (s, n) => String(s == null ? "" : s).trim().slice(0, n);

// base64url of the UTF-8 email, both ways. Only ever our own cookie, but a
// mangled one must come back as "" rather than throw.
function b64u(s) {
  let bin = "";
  for (const b of new TextEncoder().encode(s)) bin += String.fromCharCode(b);
  return btoa(bin).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}
function unb64u(s) {
  try {
    const bin = atob(s.replace(/-/g, "+").replace(/_/g, "/"));
    return new TextDecoder().decode(Uint8Array.from(bin, (c) => c.charCodeAt(0)));
  } catch { return ""; }
}

// One row, or nobody: { sid, name }, never the email back. Throws if D1 does,
// and every caller turns a throw into a refusal.
async function whoIs(env, sid, email) {
  sid = clean(sid, 24);
  email = clean(email, 120).toLowerCase();
  if (!SID_RE.test(sid) || !email) return null;
  if (!env.DB) throw new Error("no DB binding");
  const row = await env.DB.prepare(
    `SELECT p.sid, p.name_en, p.name,
            (SELECT COUNT(*) FROM roll r
              WHERE r.sid = p.sid AND r.course IN (${COURSES.map((c) => `'${c}'`).join(",")})
                AND r.left_ = 0) AS enrolled
       FROM people p
      WHERE p.sid = ?1 AND LOWER(TRIM(p.email)) = ?2`
  ).bind(sid, email).first();
  if (!row) return null;
  if (!row.enrolled && !STAFF.includes(row.sid)) return null;
  // name_en is what he calls them; the university spelling is the fallback.
  return { sid: row.sid, name: row.name_en || row.name || row.sid };
}

function readCookie(req) {
  for (const part of (req.headers.get("Cookie") || "").split(";")) {
    const i = part.indexOf("=");
    if (i > 0 && part.slice(0, i).trim() === COOKIE) return part.slice(i + 1).trim();
  }
  return "";
}

// "yes" | "no" | "down". Only a real answer from D1 is cached; "down" is asked
// again next time.
async function cookieVerdict(env, value) {
  if (!value || value.length > 300) return "no";
  const hit = verdicts.get(value);
  if (hit && Date.now() - hit.at < VERDICT_TTL_MS) return hit.who ? "yes" : "no";
  const t = value.indexOf("~");
  if (t < 1) return "no";
  let who;
  try { who = await whoIs(env, value.slice(0, t), unb64u(value.slice(t + 1))); }
  catch { return "down"; }
  if (verdicts.size > 5000) verdicts.clear();
  verdicts.set(value, { at: Date.now(), who });
  return who ? "yes" : "no";
}

const json = (body, status = 200, headers = {}) =>
  new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json", "Cache-Control": "no-store", ...headers },
  });

async function signin(req, env) {
  if (req.method !== "POST") return json({ error: "POST only" }, 405);
  if (!OPEN) return json({ error: "closed" }, 403);
  const ip = req.headers.get("CF-Connecting-IP") || "local";
  if (rateLimited(ip)) return json({ error: "slow down" }, 429);
  let body;
  try { body = await req.json(); } catch { return json({ error: "bad json" }, 400); }
  let who;
  try { who = await whoIs(env, body && body.sid, body && body.email); }
  catch { return json({ error: "store" }, 503); }
  // ONE MESSAGE FOR BOTH FAILURES, on purpose: "no such number" and "wrong
  // email" apart are an enumeration oracle, and to a student who mistyped
  // either one the useful sentence is the same.
  if (!who) return json({ error: "no" }, 401);
  const email = clean(body.email, 120).toLowerCase();
  const value = who.sid + "~" + b64u(email);
  verdicts.set(value, { at: Date.now(), who });
  // A browser throws away a Domain=shidailun.com cookie served from anywhere
  // else, so off the domain - localhost, a *.workers.dev try-out - it is left
  // host-only and the sign-in still takes. (Not visible under wrangler dev: it
  // rebuilds the URL from the configured custom_domain route, so the host there
  // is the live one however the dev server was addressed.)
  const host = new URL(req.url).hostname;
  const scope = host === DOMAIN || host.endsWith("." + DOMAIN) ? `; Domain=${DOMAIN}` : "";
  return json({ ok: true, name: who.name }, 200, {
    "Set-Cookie": `${COOKIE}=${value}; Max-Age=${YEAR}; Path=/${scope}; HttpOnly; Secure; SameSite=Lax`,
  });
}

export default {
  async fetch(req, env) {
    const path = new URL(req.url).pathname;
    if (path === "/api/signin") return signin(req, env);
    if (path.startsWith("/api/")) return json({ error: "not found" }, 404);
    if (isShell(path)) return env.ASSETS.fetch(req);
    if (!OPEN) return json({ error: "closed" }, 403);

    const v = await cookieVerdict(env, readCookie(req));
    if (v === "down") return json({ error: "store" }, 503);
    if (v !== "yes") return json({ error: "sign in" }, 401);

    // A signed-in file is for this browser only: no shared cache may keep it
    // and hand it to someone without a cookie.
    const r = await env.ASSETS.fetch(req);
    const out = new Response(r.body, r);
    out.headers.set("Cache-Control", "private, max-age=0, must-revalidate");
    return out;
  },
};
