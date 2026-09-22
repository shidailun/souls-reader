# -*- coding: utf-8 -*-
"""Publish the reader to Cloudflare, SEALED: https://souls-reader.shidailun.com/

The page is public; the book is not. Every data file - chapter packs, the
dictionary, the cover, the narration - is encrypted with AES-256-GCM under a key
derived from a password (PBKDF2-SHA256, 600,000 rounds), and only the ciphertext
goes online. Without the password the site is a lock screen and a folder of
noise. The reader (public/index.html) asks for the password once and can keep
the derived key on her device.

    python scripts/publish.py                  # encrypt + deploy
    python scripts/publish.py --dry-run        # build build_data/site/, deploy nothing
    python scripts/publish.py --show-password  # print the password and exit
    python scripts/publish.py --new-password   # rotate: she will need the new one

The password and salt live in build_data/site_secret.json, which is gitignored
and never leaves this machine. The salt is kept across publishes, so a device
that remembered the key keeps working after you update the audio or the text.

Updating the audio: replace public/audio/soulsNN.mp3 (or rerun narrate.py),
run align.py and segment.py for that chapter, then run this. A file whose
content has not changed keeps its previous ciphertext, byte for byte, and
wrangler uploads assets by content hash, so a text fix uploads a few hundred
KB, not the whole audiobook.

It used to go to GitHub Pages (gh-pages). It left on 22 Sep 2026: the book
should not sit in a GitHub repository at all, even sealed. Cloudflare's asset
limit is 25 MiB a file; the longest chapter's mp3 is under 10 MB.
"""
import base64, hashlib, json, secrets, shutil, subprocess, sys, io
from pathlib import Path
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
ROOT = Path(__file__).resolve().parents[1]
PUB = ROOT / 'public'
SITE = ROOT / 'build_data' / 'site'
SECRET = ROOT / 'build_data' / 'site_secret.json'
URL = 'https://souls-reader.shidailun.com/'
ITER = 600_000
ALPHABET = 'abcdefghjkmnpqrstuvwxyz23456789'     # no 0/o, 1/l/i to misread


def new_password():
    return '-'.join(''.join(secrets.choice(ALPHABET) for _ in range(4)) for _ in range(4))


def secret(rotate=False):
    s = json.loads(SECRET.read_text(encoding='utf-8')) if SECRET.exists() else {}
    if rotate or not s.get('password'):
        s = {'password': new_password(), 'salt': base64.b64encode(secrets.token_bytes(16)).decode()}
        SECRET.parent.mkdir(parents=True, exist_ok=True)
        SECRET.write_text(json.dumps(s, indent=1), encoding='utf-8')
    return s


def derive(password, salt):
    return PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt,
                      iterations=ITER).derive(password.encode('utf-8'))


def seal(aes, data):
    nonce = secrets.token_bytes(12)
    return nonce + aes.encrypt(nonce, data, None)


def files():
    """Everything the reader reads through getBytes(), by published path."""
    out = [PUB / 'texts' / 'registry.json', PUB / 'dict.json', PUB / 'cover.jpg']
    out += sorted((PUB / 'texts').glob('souls*.json'))
    out += sorted((PUB / 'audio').glob('*.mp3'))
    return [f for f in out if f.exists()]


def build(s):
    aes = AESGCM(derive(s['password'], base64.b64decode(s['salt'])))
    # Sealing is randomised (a fresh nonce each time), so resealing an unchanged
    # mp3 would give wrangler a "new" 8 MB file on every publish. Instead keep the
    # last build's ciphertext wherever its tag still matches; the tag hashes the
    # salt too, so a new password reseals everything.
    old, keep = {}, {}
    try:
        if json.loads((SITE / 'sealed.json').read_text(encoding='utf-8'))['salt'] == s['salt']:
            old = json.loads((SITE / 'data' / 'index.json').read_text(encoding='utf-8'))
    except (OSError, ValueError, KeyError):
        pass
    for rel in old:
        p = SITE / 'data' / (rel + '.bin')
        if p.exists():
            keep[rel] = p.read_bytes()
    if SITE.exists():
        shutil.rmtree(SITE)
    SITE.mkdir(parents=True)
    shutil.copyfile(PUB / 'index.html', SITE / 'index.html')
    # The installable app: manifest, offline worker, home-screen icons. Only
    # the icons are images: the book's cover, padded square, shown unsealed.
    for name in ('manifest.webmanifest', 'sw.js'):
        shutil.copyfile(PUB / name, SITE / name)
    shutil.copytree(PUB / 'icons', SITE / 'icons')
    (SITE / 'robots.txt').write_text('User-agent: *\nDisallow: /\n', encoding='utf-8')
    (SITE / 'sealed.json').write_text(json.dumps({
        'salt': s['salt'], 'iter': ITER,
        'check': base64.b64encode(seal(aes, b'souls-ok')).decode(),
    }), encoding='utf-8')
    total, index = 0, {}
    for f in files():
        rel = f.relative_to(PUB).as_posix()
        dest = SITE / 'data' / (rel + '.bin')
        dest.parent.mkdir(parents=True, exist_ok=True)
        data = f.read_bytes()
        # A version tag per file: sw.js caches data/<path>.bin?v=<tag> for good,
        # so the tag must change exactly when the content (or password) does.
        index[rel] = hashlib.sha256(s['salt'].encode() + data).hexdigest()[:12]
        dest.write_bytes(keep[rel] if rel in keep and old.get(rel) == index[rel] else seal(aes, data))
        total += dest.stat().st_size
    (SITE / 'data' / 'index.json').write_text(json.dumps(index), encoding='utf-8')
    # Stamp the page with this build, so an installed copy can tell it is stale.
    page = (PUB / 'index.html').read_text(encoding='utf-8')
    stamp = hashlib.sha256((page + json.dumps(index, sort_keys=True)).encode()).hexdigest()[:12]
    (SITE / 'index.html').write_text(
        page.replace('<meta name="build" content="dev">', f'<meta name="build" content="{stamp}">'),
        encoding='utf-8')
    n = len(files())
    print(f'sealed {n} files, {total / 1e6:.1f} MB -> {SITE.relative_to(ROOT)}')


def deploy():
    # wrangler.jsonc at the repo root points its assets at build_data/site/.
    # shell=True: on Windows npx is npx.cmd, which a bare subprocess cannot find.
    subprocess.run('npx wrangler deploy', cwd=ROOT, shell=True, check=True)
    print(f'live at {URL}')


def main():
    argv = sys.argv[1:]
    s = secret(rotate='--new-password' in argv)
    if '--show-password' in argv:
        print(s['password'])
        return
    build(s)
    if '--dry-run' not in argv:
        deploy()
    if '--new-password' in argv:
        print(f'NEW password: {s["password"]}  (the old one no longer works)')


if __name__ == '__main__':
    main()
