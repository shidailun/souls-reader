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
// No new secret of any kind: the only binding is D1, and every statement below
// is a SELECT except the one in beat(). (D1 has no read-only binding; that is a
// promise of this file, not of the platform.)
//
// READING TIME. He asked for "the same log in and tracking" in every reader.
// POST /api/beat {lesson, secs, open?, words?} adds secs to one unit_time row: sid from
// the cookie (re-checked exactly as for a file), unit 'fr:<app>:<lesson>',
// course 'fr' - the rows TRA503's Free reading mark already sums (frQuery in
// tra503/web/worker/index.js). That is the only write in this file.
//   - <app> is not sent by the page. It comes from the host the Worker answers
//     on, brownlee-reader.shidailun.com -> "brownlee", so a page cannot file
//     its minutes under another reader's name, and no reader needs its own
//     copy of this file. Off the domain there is no app, and no write.
//     A book reader not called <x>-reader is filed under its host as it
//     stands (dancing-english), and Key to Happiness, which answers on two
//     hosts, under one name whichever was used (ALIAS): one book, one app.
//   - ms is ADDED to, not MAX()ed as tra503's mirror does. There the client
//     sends a running total and a stale device must not lower it; here each
//     beat is a fresh slice of at most two minutes, so the sum is the total.
//     A beat lost on a dead connection is time not counted, never double.
//   - first_open and last_touch are epoch milliseconds, as tra503 writes them.
//     opens counts lesson visits: the page says {open:true} on the first beat
//     of each one.
//   - Four beats a minute per student number, per isolate. The page sends one a
//     minute and one more when it is hidden; anything faster is not a reader.
//
// WORD REVIEW. He asked for every app on 503's "More parallel" shelf to report
// "time and words reviewed". Review belongs to no lesson, so its beats say
// lesson "review" and land on one row per app and student, 'fr:<app>:review'
// (no lesson is called that: lesson codes are letters and two digits).
//   - ms is the time on the Review screen, counted by the page exactly as
//     reading is: on screen, and sound playing or a touch in the last 90 s.
//     It is real time spent on the book's own sentences, so it counts toward
//     Free reading like any other 'fr' row - but only while cards are being
//     graded. "They actually have to do something" (23 Sep): a review beat
//     with no card graded adds no time, and one with cards adds at most 30 s a
//     card, so the screen left open with a finger on it earns nothing. 30 s is
//     a sentence read, heard and graded without hurry. Reading is not held to
//     this: there, playing the video or scrolling is the doing. A report that wants reading alone
//     leaves out unit LIKE 'fr:%:review'.
//   - items_done is the number of cards graded: each press of Forgot, Hard,
//     Good or Easy is one, so a word forgotten and seen again in the same
//     sitting counts twice, because it was reviewed twice. The beat carries it
//     as {words}; on any lesson but "review" words is ignored, and it never
//     touches ms, so a fast thumb adds no minutes.
//   - items_done because unit_time already has a count column that is not
//     time, and the register already reads it that way (wib:ai's turns).
//     items stays 0, so nothing takes the row for a finished unit. Rejected:
//     a second row per app, 'fr:<app>:words' with ms 0 - two rows for one
//     screen, and one whose ms nothing may ever write; a new table or column -
//     a migration on the shared D1 for one integer; opens - it counts visits.
//   - At most 120 words a beat, as secs is at most 120: a card a second is
//     faster than anyone grades.
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
// Let in to this reader only, with no roll row: Rexa (4282462) is the one this
// app was made for. Not STAFF, because STAFF is copied into every reader's gate;
// not a 503/506 roll row, because that would put her on a register.
const READERS = ["4282462"];
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
  if (!row.enrolled && !STAFF.includes(row.sid) && !READERS.includes(row.sid)) return null;
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

// ---- reading time (see READING TIME above) ----
const HOST_RE = /^([a-z0-9-]+)\.shidailun\.com$/;
const ALIAS = { "psycho-memoir": "key-to-happiness" };
const appOf = (host) => {
  const m = host.match(HOST_RE);
  if (!m) return "";
  const name = m[1].replace(/-reader$/, "");
  return ALIAS[name] || name;
};
const LESSON_RE = /^[a-z0-9]{2,12}$/;
const BEATS_PER_MIN = 4;
const beats = new Map(); // sid -> recent beat times
function beatLimited(sid) {
  const now = Date.now();
  const arr = (beats.get(sid) || []).filter((t) => now - t < RATE_WINDOW_MS);
  arr.push(now);
  beats.set(sid, arr);
  if (beats.size > 5000) beats.clear();
  return arr.length > BEATS_PER_MIN;
}

async function beat(req, env) {
  if (req.method !== "POST") return json({ error: "POST only" }, 405);
  if (!OPEN) return json({ error: "closed" }, 403);
  const app = appOf(new URL(req.url).hostname);
  if (!app) return json({ error: "not found" }, 404);

  const value = readCookie(req);
  const v = await cookieVerdict(env, value);
  if (v === "down") return json({ error: "store" }, 503);
  if (v !== "yes") return json({ error: "sign in" }, 401);
  const hit = verdicts.get(value);
  const sid = hit && hit.who && hit.who.sid;
  if (!sid) return json({ error: "sign in" }, 401);

  // sendBeacon posts its Blob as text; parse it by hand rather than trusting a
  // Content-Type header.
  let body;
  try { body = JSON.parse(await req.text()); } catch { return json({ error: "bad json" }, 400); }
  const lesson = String((body && body.lesson) || "");
  if (!LESSON_RE.test(lesson)) return json({ error: "lesson" }, 400);
  const n = Number(body.secs);
  let secs = Number.isFinite(n) ? Math.round(Math.min(120, Math.max(0, n))) : 0;
  const open = body.open === true ? 1 : 0;
  // cards graded, on the Review row only (see WORD REVIEW above)
  const w = lesson === "review" ? Number(body.words) : 0;
  const words = Number.isFinite(w) ? Math.round(Math.min(120, Math.max(0, w))) : 0;
  if (lesson === "review") secs = Math.min(secs, 30 * words);
  if (!secs && !open && !words) return new Response(null, { status: 204 });
  if (beatLimited(sid)) return json({ error: "slow down" }, 429);

  const now = Date.now();
  try {
    await env.DB.prepare(
      `INSERT INTO unit_time (sid, unit, course, ms, first_open, last_touch, opens, items_done)
       VALUES (?1, ?2, 'fr', ?3, ?4, ?4, ?5, ?6)
       ON CONFLICT(sid, unit) DO UPDATE SET
         ms         = unit_time.ms + ?3,
         last_touch = MAX(unit_time.last_touch, ?4),
         opens      = unit_time.opens + ?5,
         items_done = unit_time.items_done + ?6`
    ).bind(sid, `fr:${app}:${lesson}`, secs * 1000, now, open, words).run();
  } catch { return json({ error: "store" }, 503); }
  return new Response(null, { status: 204 });
}

export default {
  async fetch(req, env) {
    const path = new URL(req.url).pathname;
    if (path === "/api/signin") return signin(req, env);
    if (path === "/api/beat") return beat(req, env);
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
